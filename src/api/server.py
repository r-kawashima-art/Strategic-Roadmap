"""FastAPI backend for the Strategic Roadmap conversational layer (Phase 8 / FR-5).

Endpoints
---------
  GET  /healthz   — liveness probe (no auth)
  GET  /scenarios — returns data/scenarios.json (bearer)
  POST /chat      — streams Claude's answer as SSE, grounded in scenario (bearer)
  POST /revise    — translates NL into a structured diff via `apply_scenario_diff`
                    tool use, applies, persists, returns updated scenarios (bearer)
  POST /expand    — Phase 8. Takes a user *question* ("what if EU passes strict
                    AI regulation in 2026?") and uses Claude tool-use to mint a
                    new TurningPointNode that extends the scenario line, with
                    terminal branches rewired to flow into it.

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
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import anthropic
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Import `apply_diff` — prefer the package form, fall back for direct-module execution.
try:
    from .scenario_patch import KNOWN_EXTERNAL_DRIVERS, DiffError, apply_diff
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from scenario_patch import KNOWN_EXTERNAL_DRIVERS, DiffError, apply_diff  # type: ignore

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIOS_PATH = DATA_DIR / "scenarios.json"
UI_PATH = PROJECT_ROOT / "src" / "ui" / "index.html"

# Model choices come from §8.2 of the plan — do not change without a plan update.
CHAT_MODEL = "claude-sonnet-4-6"   # latency-sensitive
REVISE_MODEL = "claude-sonnet-4-6"   # accuracy-sensitive, lower frequency (e.g. claude-opus-4-7)

load_dotenv()
ROADMAP_API_KEY = os.getenv("ROADMAP_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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


class ExpandRequest(BaseModel):
    scenario_id: str = "scenario-001"
    question: str = Field(..., min_length=1, max_length=4000)


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
    "field — those are out of scope for this tool. "
    "When the op is `add_node`, the server auto-rewires every currently-terminal "
    "branch (branches whose `next_node_id` is null) into the new node so the "
    "DAG stays connected. Use the optional `rewire_from` list ONLY when the "
    "scenario has multiple terminal paths that serve different story lines and "
    "only one should flow into the new node — list the specific "
    "{node_id, branch_id} pairs to rewire and leave the rest terminal. "

    "Pick the wiring mode for `add_node` based on the user's framing: "
    "When the user describes a turning point that EXTENDS the storyline past "
    "its current end (cues like 'and after that…', 'in 2038…', "
    "'next decision…'), leave `fork_from` empty — either omit `rewire_from` "
    "for auto-rewire, or list specific terminal branches in `rewire_from`. "
    "When the user describes an ALTERNATIVE or DIVERGENT past decision "
    "(cues like 'what if instead', 'imagine that in 2028…', 'fork from', "
    "'diverge', 'counterfactual', or any 'instead of X, do Y' framing), use "
    "`fork_from` to attach the new node to the relevant past turning point(s). "
    "The existing branches at those nodes stay intact, so the original "
    "storyline remains explorable alongside the divergent one. Pick a "
    "`probability` that reflects the user's framing (e.g. 'a small chance' "
    "≈ 0.10–0.20); do NOT rebalance the existing branches — the simulator "
    "normalises at run time. "
    "Never set `next_node_id` on a `fork_from.branch` — the server sets it "
    "for you. Setting it manually will be rejected as out-of-scope. "

    "Pick the new node's `year` so that every predecessor that links INTO it "
    "is chronologically prior or simultaneous. Concretely: every `rewire_from` "
    "host node and every `fork_from.from_node_id` must have `year ≤ new_node.year`. "
    "When omitting `rewire_from` (auto-rewire), pick a `year` strictly later "
    "than every currently-terminal branch's host year — otherwise the server "
    "will reject the diff with a 'chronological contradiction' / 'unreachable' "
    "error because the only valid predecessors are in the past."
)


EXPAND_SYSTEM_PREAMBLE = (
    "You extend an OTA strategic-scenario DAG in response to a user question. "
    "The scenario currently ends at some latest turning-point year; the user "
    "has asked a 'what if' question that implies a NEW decision point the "
    "industry would face AFTER the current last node. Your job is to mint "
    "exactly one new TurningPointNode via the `expand_scenario_from_question` "
    "tool, with 2–3 well-reasoned branches, and rewire every currently "
    "terminal branch to flow into it.\n\n"
    "Hard constraints — violating any of these will cause the server to reject "
    "your output:\n"
    "  1. `new_node.year` MUST be strictly greater than every existing "
    "turning-point year in the scenario, and ≤ 2040.\n"
    f"  2. `new_node.external_driver` MUST be one of: "
    f"{sorted(KNOWN_EXTERNAL_DRIVERS)}. Pick the closest conceptual match — "
    f"e.g. an AI-regulation question maps to 'GenAI breakthrough'; a loyalty- "
    f"programme lock-in question maps to 'Airline direct booking dominance'.\n"
    "  3. `new_node.id` must follow the `tp-NNN` pattern (mint the next free "
    "integer — e.g. if tp-001..tp-003 exist, use tp-004).\n"
    "  4. Each branch `id` must follow `<node_id>-<letter>` (e.g. tp-004-a).\n"
    "  5. Every branch needs a `metric_delta` with numeric `revenue_index`, "
    "`market_share`, `tech_adoption_velocity` fields. Deltas in [-0.25, 0.25] "
    "for revenue_index and [-0.15, 0.15] for the two fractions are defensible; "
    "pick magnitudes consistent with the existing nodes.\n"
    "  6. Branch probabilities must sum to 1.0 ± 0.001.\n"
    "  7. `rewire_branches` must list EVERY currently-terminal branch "
    "(branches whose `next_node_id` is null in the scenario JSON). Non-terminal "
    "branches must NOT appear — rewiring mid-graph edges is out of scope.\n\n"
    "Write a one-sentence `summary` describing the expansion in plain English "
    "so the UI can ask the user to confirm."
)


EXPAND_SCENARIO_TOOL: Dict[str, Any] = {
    "name": "expand_scenario_from_question",
    "description": (
        "Extend the scenario DAG with a new turning-point node that answers "
        "the user's 'what if' question, and rewire terminal branches to flow "
        "into it. Always include a one-sentence `summary` for user confirmation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-sentence plain-English description of the expansion.",
            },
            "new_node": {
                "type": "object",
                "description": "A full TurningPointNode object for the expansion.",
                "properties": {
                    "id": {"type": "string"},
                    "year": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "external_driver": {
                        "type": "string",
                        "enum": sorted(KNOWN_EXTERNAL_DRIVERS),
                    },
                    "branches": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 4,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                                "probability": {"type": "number"},
                                "metric_delta": {
                                    "type": "object",
                                    "properties": {
                                        "revenue_index": {"type": "number"},
                                        "market_share": {"type": "number"},
                                        "tech_adoption_velocity": {"type": "number"},
                                    },
                                    "required": [
                                        "revenue_index",
                                        "market_share",
                                        "tech_adoption_velocity",
                                    ],
                                },
                            },
                            "required": [
                                "id",
                                "label",
                                "description",
                                "probability",
                                "metric_delta",
                            ],
                        },
                    },
                },
                "required": [
                    "id",
                    "year",
                    "title",
                    "description",
                    "external_driver",
                    "branches",
                ],
            },
            "rewire_branches": {
                "type": "array",
                "description": (
                    "Every currently-terminal branch in the scenario. Each "
                    "entry is {node_id, branch_id}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string"},
                        "branch_id": {"type": "string"},
                    },
                    "required": ["node_id", "branch_id"],
                },
            },
        },
        "required": ["summary", "new_node", "rewire_branches"],
    },
}


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
                        "rewire_from": {
                            "type": "array",
                            "description": (
                                "Specific terminal branches to rewire into the "
                                "new node. Omit to auto-rewire all terminal "
                                "branches. Only valid for `add_node`."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "node_id": {"type": "string"},
                                    "branch_id": {"type": "string"},
                                },
                                "required": ["node_id", "branch_id"],
                            },
                        },
                        "fork_from": {
                            "type": "array",
                            "description": (
                                "Past nodes that should sprout a NEW branch "
                                "pointing at the new node, modelling a divergent "
                                "storyline. Existing branches on those nodes are "
                                "preserved. Only valid for `add_node`."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from_node_id": {"type": "string"},
                                    "branch": {
                                        "type": "object",
                                        "description": (
                                            "Full new branch object — same shape "
                                            "as the `branch` field on `add_branch` "
                                            "(id, label, description, probability, "
                                            "metric_delta). Do NOT include "
                                            "next_node_id; the server sets it."
                                        ),
                                    },
                                },
                                "required": ["from_node_id", "branch"],
                            },
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
        raw = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"scenarios.json is malformed: {exc}")

    # Phase 10.1 layout: {base: [...], user: [...]}. Flat-list layout still
    # accepted for backwards compatibility with older fixtures.
    if isinstance(raw, dict):
        base_list = list(raw.get("base", []))
        user_list = list(raw.get("user", []))
    else:
        base_list = [s for s in raw if s.get("source") != "user"]
        user_list = [s for s in raw if s.get("source") == "user"]

    for s in base_list:
        s["source"] = "base"
    for s in user_list:
        s["source"] = "user"
    return base_list + user_list


def _save_scenarios(scenarios: List[Dict[str, Any]]) -> None:
    """Persist the scenario list back as the {base, user} layout (Phase 10.1).

    The on-disk layout splits read-only seed scenarios from mutable user
    variants so that simple file inspection makes the boundary obvious. The
    in-memory `source` key is stripped from each entry on the way out — the
    layout itself encodes provenance, and re-injection happens on load.
    """
    base_list: List[Dict[str, Any]] = []
    user_list: List[Dict[str, Any]] = []
    for s in scenarios:
        clean = {k: v for k, v in s.items() if k != "source"}
        if s.get("source") == "user":
            user_list.append(clean)
        else:
            base_list.append(clean)
    payload = {"base": base_list, "user": user_list}
    SCENARIOS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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


@app.get("/")
async def serve_ui() -> FileResponse:
    """Serve the single-page application so the UI and API share one origin."""
    if not UI_PATH.exists():
        raise HTTPException(status_code=404, detail=f"UI file not found at {UI_PATH}")
    return FileResponse(UI_PATH, media_type="text/html")


@app.get("/scenarios")
async def get_scenarios() -> JSONResponse:
    """Read-only: no bearer required so the SPA can initialise without credentials."""
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

    # Apply diff to a deep copy only — never write to disk here.
    # The caller (UI) previews the result and calls POST /scenarios to persist
    # it explicitly as a new named entry (Phase 9 §9.1).
    draft = copy.deepcopy(scenarios)
    try:
        for op in operations:
            op.setdefault("scenario_id", req.scenario_id)
            apply_diff(draft, op)
    except DiffError as exc:
        raise HTTPException(status_code=422, detail=f"Diff rejected: {exc}")

    preview_scenario = _find_scenario(draft, req.scenario_id)

    return {
        "status": "preview",
        "summary": summary,
        "operations": operations,
        "preview_scenario": preview_scenario,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
        },
    }


class SaveScenarioRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: Optional[str] = None
    scenario_data: Dict[str, Any]


@app.post("/scenarios", dependencies=[Depends(require_bearer)])
async def create_scenario(req: SaveScenarioRequest) -> Dict[str, Any]:
    """Save a user scenario (new or AI-revised) as a named, reusable entry."""
    scenarios = _load_scenarios()

    # Reject name collisions so the selector stays unambiguous.
    if any(s.get("name") == req.name for s in scenarios):
        raise HTTPException(status_code=409, detail=f"Scenario name {req.name!r} already exists.")

    new_id = f"user-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    new_scenario: Dict[str, Any] = {
        **req.scenario_data,
        "id": new_id,
        "name": req.name,
        "source": "user",
        "parent_id": req.parent_id,
        "created_at": now,
        "updated_at": now,
    }

    scenarios.append(new_scenario)
    _save_scenarios(scenarios)

    return {
        "id": new_id,
        "name": req.name,
        "source": "user",
        "parent_id": req.parent_id,
        "created_at": now,
    }


class UpdateScenarioRequest(BaseModel):
    """Phase 10.4: PUT is metadata-only. Graph keys are rejected up front.

    Pydantic's `model_config = {"extra": "forbid"}` makes any unknown field
    surface as a 422 from FastAPI; combined with the explicit guard below,
    this prevents in-place graph mutation on user scenarios.
    """

    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)


# Graph-shaped keys that must NEVER be mutated in place — see §10.4. Edits to
# these route through POST /scenarios with parent_id, producing a new variant.
_FORBIDDEN_GRAPH_KEYS = frozenset({
    "nodes",
    "timeline",
    "metrics",
    "strategic_profiles",
    "competitors",
    "market_share_projection",
})


@app.put("/scenarios/{scenario_id}", dependencies=[Depends(require_bearer)])
async def update_scenario(scenario_id: str, req: UpdateScenarioRequest) -> Dict[str, Any]:
    """Rename or update the description of a user-created scenario.

    Phase 10.4 contract: this endpoint is metadata-only. Any payload carrying
    `nodes`, `timeline`, `metrics`, etc. is rejected with HTTP 400. To change
    the visualizing graph, save a new variant via POST /scenarios with the
    current scenario as parent_id.
    """
    # Defence in depth — even if the schema were relaxed, this guard stays.
    raw_payload = req.model_dump(exclude_unset=True)
    bad = [k for k in raw_payload if k in _FORBIDDEN_GRAPH_KEYS]
    if bad:
        raise HTTPException(
            status_code=400,
            detail=(
                f"PUT /scenarios is metadata-only — fields {sorted(bad)} are not "
                "editable in place. To change the visualizing graph, save a new "
                "variant via POST /scenarios with parent_id set to this scenario."
            ),
        )

    scenarios = _load_scenarios()
    target = _find_scenario(scenarios, scenario_id)

    if target.get("source") != "user":
        raise HTTPException(status_code=403, detail="Base scenarios cannot be modified.")

    if req.name is not None:
        if any(s.get("name") == req.name and s.get("id") != scenario_id for s in scenarios):
            raise HTTPException(status_code=409, detail=f"Scenario name {req.name!r} already exists.")
        target["name"] = req.name

    if req.description is not None:
        target["description"] = req.description

    target["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_scenarios(scenarios)
    return {"id": scenario_id, "name": target["name"], "updated_at": target["updated_at"]}


@app.delete("/scenarios/{scenario_id}", dependencies=[Depends(require_bearer)], status_code=204)
async def delete_scenario(scenario_id: str) -> None:
    """Delete a user-created scenario. Returns 403 for base scenarios.

    Per Phase 10.4, deletion does NOT cascade to children: variants whose
    `parent_id` points at the deleted scenario keep that pointer, and the UI
    annotates them as "(deleted parent)" rather than purging them — so a
    single bad delete does not destroy a derived edit history.
    """
    scenarios = _load_scenarios()
    target = _find_scenario(scenarios, scenario_id)

    if target.get("source") != "user":
        raise HTTPException(status_code=403, detail="Base scenarios cannot be deleted.")

    _save_scenarios([s for s in scenarios if s.get("id") != scenario_id])


# ---------------------------------------------------------------------------
# Phase 10.1 — Export / Import (self-contained scenario files)
# ---------------------------------------------------------------------------

REQUIRED_IMPORT_KEYS = frozenset({"id", "name", "nodes", "timeline"})


def _slugify(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-_.")
    return s.lower() or "scenario"


def _suggest_rename(scenarios: List[Dict[str, Any]], name: str) -> str:
    """Append a suffix until the name is free — mirrors the UI's '(2)' pattern."""
    base = name
    n = 2
    while any(s.get("name") == name for s in scenarios):
        name = f"{base} ({n})"
        n += 1
    return name


@app.get("/scenarios/{scenario_id}/export", dependencies=[Depends(require_bearer)])
async def export_scenario(scenario_id: str) -> JSONResponse:
    """Return the scenario object as a downloadable `<slug>.scenario.json`.

    The export is self-contained: it carries the full `nodes`, `timeline`, and
    derived `market_share_projection` so it can be re-imported on a different
    instance without referencing the source scenarios.json.
    """
    scenarios = _load_scenarios()
    target = _find_scenario(scenarios, scenario_id)
    filename = f"{_slugify(target.get('name') or scenario_id)}.scenario.json"
    return JSONResponse(
        target,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/scenarios/import", dependencies=[Depends(require_bearer)])
async def import_scenario(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Accept a `.scenario.json` upload, validate, assign a fresh id, persist.

    Always saves into the `user` array — imports never become base scenarios.
    Duplicate-name conflicts surface as HTTP 409 with a `suggested_name` so
    the client can offer one-click rename + retry.
    """
    name = (file.filename or "").lower()
    if not (name.endswith(".scenario.json") or name.endswith(".json")):
        raise HTTPException(
            status_code=400,
            detail="Upload must be a .scenario.json (or .json) file.",
        )

    raw = await file.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse JSON: {exc}")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Top-level value must be a scenario object.")
    missing = REQUIRED_IMPORT_KEYS - set(payload.keys())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Imported scenario is missing required keys: {sorted(missing)}",
        )

    scenarios = _load_scenarios()
    requested_name = payload.get("name") or "Imported scenario"
    if any(s.get("name") == requested_name for s in scenarios):
        suggested = _suggest_rename(scenarios, requested_name)
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Scenario name {requested_name!r} already exists.",
                "suggested_name": suggested,
            },
        )

    new_id = f"user-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    # Strip identity / provenance fields so the import is treated as a fresh
    # user variant — the original `id`, `source`, and timestamps are replaced.
    cleaned = {
        k: v for k, v in payload.items()
        if k not in {"id", "source", "created_at", "updated_at"}
    }
    new_scenario = {
        **cleaned,
        "id": new_id,
        "name": requested_name,
        "source": "user",
        "parent_id": payload.get("parent_id"),
        "created_at": now,
        "updated_at": now,
    }
    scenarios.append(new_scenario)
    _save_scenarios(scenarios)

    return {
        "id": new_id,
        "name": requested_name,
        "source": "user",
        "parent_id": new_scenario.get("parent_id"),
        "created_at": now,
    }


@app.post("/expand", dependencies=[Depends(require_bearer)])
async def post_expand(req: ExpandRequest) -> Dict[str, Any]:
    """Phase 8 + Phase 10.6: extend the scenario line with a new TurningPoint
    in response to a user question and return a preview WITHOUT mutating
    ``data/scenarios.json``.

    The expansion is applied to a deep copy and surfaced to the client. The
    user explicitly saves the result as a NEW user scenario via
    ``POST /scenarios`` with ``parent_id`` set to the source — mirroring the
    ``/revise`` → Save-as-New flow from Phase 9.3 and matching the Phase 10.4
    non-destructive-edit invariant ("the source row is never mutated").
    """
    scenarios = _load_scenarios()
    target = _find_scenario(scenarios, req.scenario_id)
    scenario_json = json.dumps(target, separators=(",", ":"))
    system = _scenario_system(EXPAND_SYSTEM_PREAMBLE, scenario_json)

    client = _get_claude_client()
    try:
        response = await client.messages.create(
            model=REVISE_MODEL,  # expansion is accuracy-sensitive — use Opus
            max_tokens=2048,
            system=system,
            tools=[EXPAND_SCENARIO_TOOL],
            tool_choice={"type": "tool", "name": "expand_scenario_from_question"},
            messages=[{"role": "user", "content": req.question}],
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
            detail="Model did not return an expansion tool call.",
        )

    tool_input = tool_use.input or {}
    summary = tool_input.get("summary") or ""
    new_node = tool_input.get("new_node") or {}
    rewires = tool_input.get("rewire_branches") or []
    if not new_node or not rewires:
        raise HTTPException(
            status_code=422,
            detail="Expansion tool call missing `new_node` or `rewire_branches`.",
        )

    # Apply on a deep copy ONLY — Phase 10.6 makes /expand non-destructive.
    # The caller persists explicitly via POST /scenarios.
    draft = copy.deepcopy(scenarios)
    diff_op = {
        "op": "expand_scenario",
        "scenario_id": req.scenario_id,
        "source_question": req.question,
        "new_node": new_node,
        "rewire_branches": rewires,
    }
    try:
        apply_diff(draft, diff_op)
    except DiffError as exc:
        raise HTTPException(status_code=422, detail=f"Expansion rejected: {exc}")

    preview_scenario = _find_scenario(draft, req.scenario_id)

    return {
        "status": "preview",
        "summary": summary,
        "new_node": new_node,
        "rewire_branches": rewires,
        "preview_scenario": preview_scenario,
        "note": (
            "Expansion applied to a preview only — data/scenarios.json was NOT "
            "modified. Save as a new user scenario via the chat panel's "
            "'Save as new' button (POST /scenarios with parent_id set to the "
            "source scenario)."
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
