"""FastAPI backend for the Strategic Roadmap conversational layer (Phase 8 / FR-5).

Endpoints
---------
  GET  /healthz   — liveness probe (no auth)
  GET  /scenarios — returns data/scenarios.json (bearer)
  POST /chat      — streams Claude's answer as SSE, grounded in scenario (bearer)
  POST /revise    — translates NL into a structured diff via `apply_scenario_diff`
                    tool use, applies, persists, returns updated scenarios (bearer)

Authentication: bearer token via `Authorization: Bearer <ROADMAP_API_KEY>`.
Claude authentication: standard `ANTHROPIC_API_KEY` env var (server-side only;
never sent to the browser).

Prompt caching: the scenario JSON is placed in a cached system block — the
scenario is stable across a conversation, so cache-read hits should dominate
after the first turn.

Run locally:
    pip install -r requirements.txt
    export ROADMAP_API_KEY=...           # your bearer token
    export ANTHROPIC_API_KEY=sk-ant-...  # your Anthropic API key
    python3 -m uvicorn src.api.server:app --port 8787 --reload
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Import `apply_diff` — prefer the package form, fall back for direct-module execution.
try:
    from .scenario_patch import DiffError, apply_diff
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scenario_patch import DiffError, apply_diff  # type: ignore

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"

# Model choices come from §8.2 of the plan — do not change without a plan update.
CHAT_MODEL = "claude-sonnet-4-6"   # latency-sensitive
REVISE_MODEL = "claude-opus-4-7"   # accuracy-sensitive, lower frequency

ROADMAP_API_KEY = os.environ.get("ROADMAP_API_KEY", "")

# Shared Claude client (async). Constructed on first use so the process can
# start without ANTHROPIC_API_KEY and surface 503s on Claude-calling routes
# instead of crashing at import time.
_client: Optional[anthropic.AsyncAnthropic] = None


def _get_claude_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(
                status_code=503,
                detail="ANTHROPIC_API_KEY not set on server",
            )
        _client = anthropic.AsyncAnthropic()
    return _client


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Strategic Roadmap API", version="0.1.0")

# CORS is wide-open because this is a local-dev / internal-demo tool that will
# typically be served on one port while the UI is served on another (`python3
# -m http.server 8080`). Narrow `allow_origins` before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def require_bearer(authorization: Optional[str] = Header(None)) -> None:
    """Single-token bearer auth. Fails closed if the server key isn't set."""
    if not ROADMAP_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ROADMAP_API_KEY not configured on server",
        )
    expected = f"Bearer {ROADMAP_API_KEY}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    scenario_id: str = "scenario-001"
    message: str = Field(..., min_length=1, max_length=8000)
    history: List[ChatTurn] = Field(default_factory=list)


class ReviseRequest(BaseModel):
    scenario_id: str = "scenario-001"
    instruction: str = Field(..., min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Prompt plumbing
# ---------------------------------------------------------------------------

CHAT_SYSTEM_PREAMBLE = (
    "You are a strategic advisor for the Online Travel Agency (OTA) industry. "
    "Answer the user's questions strictly from the SCENARIO JSON block below — "
    "turning points, branches, competitor profiles, market-share projection, "
    "metric deltas, and probabilities. If the user asks about something the "
    "scenario does not cover, say so explicitly rather than speculating. "
    "Keep answers concise and reference node IDs / branch IDs when you cite "
    "them (e.g. 'tp-002-a Build Proprietary AI'). "
    "If the user's message sounds like a *revision* ('increase X to Y', "
    "'add a turning point', 'change the label'), do not describe the change "
    "in prose — respond: 'That sounds like a revision — switch to Revise mode "
    "so I can return a structured diff for confirmation.'"
)


REVISE_SYSTEM_PREAMBLE = (
    "You translate natural-language scenario revisions into a structured diff "
    "via the `apply_scenario_diff` tool. You must call the tool exactly once, "
    "even if the user instruction is ambiguous — prefer the smallest plausible "
    "change and flag uncertainty in the `summary` field. "
    "Never write the edit into prose: always route through the tool. "
    "Never invent node or branch IDs the scenario does not already contain "
    "(except when the op is `add_node` or `add_branch`, where you mint new "
    "IDs following the existing pattern like tp-004 or tp-002-d). "
    "Do not modify `next_node_id`, the `timeline` array, or any `metadata.*` "
    "field — those are out of scope for this tool."
)


APPLY_SCENARIO_DIFF_TOOL: Dict[str, Any] = {
    "name": "apply_scenario_diff",
    "description": (
        "Translate the user's natural-language revision instruction into a "
        "list of structured diff operations. Always include a one-sentence "
        "`summary` the UI will ask the user to confirm."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-sentence, plain-English description of the change.",
            },
            "operations": {
                "type": "array",
                "description": "Ordered list of diff operations to apply.",
                "items": {
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": [
                                "set_node_field",
                                "set_branch_field",
                                "add_branch",
                                "add_node",
                            ],
                        },
                        "scenario_id": {
                            "type": "string",
                            "description": "Optional. Defaults to the active scenario.",
                        },
                        "node_id": {"type": "string"},
                        "branch_id": {"type": "string"},
                        "field": {
                            "type": "string",
                            "description": (
                                "Dotted path for metric_delta.* fields "
                                "(e.g. 'metric_delta.probability')."
                            ),
                        },
                        "value": {
                            "description": "Any JSON value (string / number / bool / object)."
                        },
                        "branch": {
                            "type": "object",
                            "description": "Full new branch object (required for add_branch).",
                        },
                        "node": {
                            "type": "object",
                            "description": "Full new node object (required for add_node).",
                        },
                    },
                    "required": ["op"],
                },
            },
        },
        "required": ["summary", "operations"],
    },
}


def _load_scenarios() -> List[Dict[str, Any]]:
    if not SCENARIOS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"{SCENARIOS_PATH.name} not found. "
                "Generate it first: `cd src/engine && python3 simulator.py`"
            ),
        )
    try:
        return json.loads(SCENARIOS_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"scenarios.json is malformed: {exc}")


def _find_scenario(scenarios: List[Dict[str, Any]], scenario_id: str) -> Dict[str, Any]:
    target = next((s for s in scenarios if s.get("id") == scenario_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"scenario_id {scenario_id!r} not found")
    return target


def _scenario_system(preamble: str, scenario_json: str) -> List[Dict[str, Any]]:
    """System prompt with the scenario JSON cached via prompt-caching.

    Render order is `tools` -> `system` -> `messages`, so placing the scenario
    at the end of `system` with `cache_control` caches tools+system together.
    The preamble sits before the cached block so small edits to it don't
    invalidate the (much larger) scenario cache.
    """
    return [
        {"type": "text", "text": preamble},
        {
            "type": "text",
            "text": f"SCENARIO DATA (JSON):\n{scenario_json}",
            "cache_control": {"type": "ephemeral"},
        },
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "bearer_configured": bool(ROADMAP_API_KEY),
        "anthropic_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "scenarios_present": SCENARIOS_PATH.exists(),
    }


@app.get("/scenarios", dependencies=[Depends(require_bearer)])
async def get_scenarios() -> JSONResponse:
    return JSONResponse(_load_scenarios())


@app.post("/chat", dependencies=[Depends(require_bearer)])
async def post_chat(req: ChatRequest) -> StreamingResponse:
    scenarios = _load_scenarios()
    target = _find_scenario(scenarios, req.scenario_id)
    scenario_json = json.dumps(target, separators=(",", ":"))
    system = _scenario_system(CHAT_SYSTEM_PREAMBLE, scenario_json)

    messages: List[Dict[str, Any]] = [
        {"role": turn.role, "content": turn.content} for turn in req.history
    ]
    messages.append({"role": "user", "content": req.message})

    client = _get_claude_client()

    async def stream() -> AsyncIterator[bytes]:
        try:
            async with client.messages.stream(
                model=CHAT_MODEL,
                max_tokens=2048,
                system=system,
                messages=messages,
            ) as s:
                async for text_chunk in s.text_stream:
                    payload = json.dumps({"type": "delta", "text": text_chunk})
                    yield f"data: {payload}\n\n".encode()
                final = await s.get_final_message()
                done = json.dumps(
                    {
                        "type": "done",
                        "stop_reason": final.stop_reason,
                        "usage": {
                            "input_tokens": final.usage.input_tokens,
                            "output_tokens": final.usage.output_tokens,
                            "cache_read_input_tokens": getattr(
                                final.usage, "cache_read_input_tokens", 0
                            ),
                            "cache_creation_input_tokens": getattr(
                                final.usage, "cache_creation_input_tokens", 0
                            ),
                        },
                    }
                )
                yield f"data: {done}\n\n".encode()
        except anthropic.APIError as exc:
            err = json.dumps({"type": "error", "message": f"Claude API error: {exc}"})
            yield f"data: {err}\n\n".encode()
        except Exception as exc:  # pragma: no cover — last-resort error surface
            err = json.dumps({"type": "error", "message": str(exc)})
            yield f"data: {err}\n\n".encode()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/revise", dependencies=[Depends(require_bearer)])
async def post_revise(req: ReviseRequest) -> Dict[str, Any]:
    scenarios = _load_scenarios()
    target = _find_scenario(scenarios, req.scenario_id)
    scenario_json = json.dumps(target, separators=(",", ":"))
    system = _scenario_system(REVISE_SYSTEM_PREAMBLE, scenario_json)

    client = _get_claude_client()

    try:
        response = await client.messages.create(
            model=REVISE_MODEL,
            max_tokens=2048,
            system=system,
            tools=[APPLY_SCENARIO_DIFF_TOOL],
            tool_choice={"type": "tool", "name": "apply_scenario_diff"},
            messages=[{"role": "user", "content": req.instruction}],
        )
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    tool_use = next(
        (b for b in response.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_use is None:
        raise HTTPException(
            status_code=422,
            detail="Model did not return a structured diff (no tool_use block).",
        )

    tool_input = tool_use.input or {}
    operations = tool_input.get("operations") or []
    summary = tool_input.get("summary") or ""
    if not operations:
        raise HTTPException(status_code=422, detail="Model returned zero operations to apply.")

    # Dry-run on a deep copy before touching disk — a validation failure on
    # operation N must not leave operations 0..N-1 committed.
    draft = copy.deepcopy(scenarios)
    try:
        for op in operations:
            op.setdefault("scenario_id", req.scenario_id)
            apply_diff(draft, op)
    except DiffError as exc:
        raise HTTPException(status_code=422, detail=f"Diff rejected: {exc}")

    # Commit.
    SCENARIOS_PATH.write_text(json.dumps(draft, indent=2, ensure_ascii=False))

    return {
        "status": "applied",
        "summary": summary,
        "operations": operations,
        "scenarios": draft,
        "note": (
            "Diff applied to scenarios.json. The 18 auto-generated path "
            "variants in scenarios_generated.json are NOT re-computed — "
            "re-run `python3 src/engine/simulator.py` to refresh them."
        ),
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        },
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("src.api.server:app", host="127.0.0.1", port=8787, reload=True)
