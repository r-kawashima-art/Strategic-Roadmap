# Strategic-Roadmap

A programmable simulation and visualization system for the Online Travel Agency (OTA) industry. Models how AI disruption, NDC adoption, and airline direct-booking trends reshape the competitive landscape from 1990 to 2040, and renders the results as an interactive browser dashboard.

For the full design, see [docs/walkthrough.md](docs/walkthrough.md).

## Prerequisites

- Python 3.9+
- A modern browser (Chrome, Firefox, Safari, Edge)
- **For the conversational layer (Phase 8 / FR-5) only:** a small set of Python packages (`fastapi`, `uvicorn`, `anthropic`, `pydantic`) and an Anthropic API key. Phases 1–7 run on the standard library alone.

## How to run

All commands below assume you are in the **project root** (`Strategic-Roadmap/`). If you `cd` into a subdirectory for one step, `cd` back to the project root before running the next.

### 1. Generate scenario data

```bash
# From project root
(cd src/engine && python3 simulator.py)
```

The parentheses run `simulator.py` in a subshell so your working directory stays at the project root when the command finishes. `simulator.py` currently uses a sibling import (`from schema import ...`) that requires it to be executed from inside `src/engine/`, which is why the `cd` is needed.

This writes:

- `data/scenarios.json` — base "AI Leapfrog" scenario + top-ranked generated path (consumed by the UI)
- `data/scenarios_generated.json` — all 18 branch-combination variants, ranked by composite score

### 2. Open the dashboard

**Option A — with live data fetch (recommended):**

```bash
# From project root — this matters!
python3 -m http.server 8080
# Then open http://localhost:8080/src/ui/index.html
```

> **If you see a 404 for `/src/ui/index.html`**, the server was started from the wrong directory. `http.server` serves the current working directory as `/`, so it must be run from the project root. Run `pwd` — you should see a path ending in `Strategic-Roadmap`.

The scenario dropdown will list every scenario in `data/scenarios.json`.

**Option B — open the HTML file directly:**

Open [src/ui/index.html](src/ui/index.html) in any browser. The page falls back to an embedded copy of the base scenario when `fetch()` is blocked by the `file://` protocol, so the dashboard still works without a server — but generated paths won't appear in the dropdown.

### 3. Run Phase 4 verification

```bash
# From project root
python3 -m tests.run_verification
```

Executes both the war-gaming suite (12 tests) and the turning-point clarity suite (11 tests), then writes a reviewer-facing report to [specs/verification_report.md](specs/verification_report.md). Exits non-zero if any test fails.

To run a single suite:

```bash
python3 -m unittest tests.test_wargame -v
python3 -m unittest tests.test_turning_points -v
```

### 4. Conversational layer (Phase 8 / FR-5) — optional

The chat panel inside the dashboard talks to a small FastAPI backend that fronts the Claude API. It lets you (a) ask scenario-grounded questions with streaming responses, and (b) translate natural-language revisions into a structured diff that is applied to `data/scenarios.json` after you confirm.

**Install the backend dependencies** (one-time — a venv is recommended):

```bash
# From project root
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Export credentials** and start the API server:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # your Anthropic API key — server-side only
export ROADMAP_API_KEY="pick-a-token"    # bearer token that the UI will send back
.venv/bin/python -m uvicorn src.api.server:app --port 8787 --reload
```

Then in a second terminal, launch the dashboard as in step 2, open the UI, click **💬 Chat** in the header, paste your `ROADMAP_API_KEY` into ⚙ API settings, and start talking to the scenario.

**Endpoints**

| Method | Path         | Purpose |
|---|---|---|
| `GET`  | `/healthz`   | Liveness probe (no auth) |
| `GET`  | `/scenarios` | Returns `data/scenarios.json` (bearer) |
| `POST` | `/chat`      | Streams Claude's scenario-grounded answer as SSE (bearer; model: `claude-sonnet-4-6`) |
| `POST` | `/revise`    | Translates NL → structured diff via Claude tool use, validates, applies, persists (bearer; model: `claude-opus-4-7`) |

**Known scope trim**: `/revise` persists the edit to `scenarios.json` but does **not** re-run the 18-variant generator. The generated paths in `data/scenarios_generated.json` will drift out of sync until you re-run `python3 src/engine/simulator.py` manually. Auto-regeneration would require a dict→`Scenario` dataclass hydration path the codebase does not yet have — out of scope for Phase 8.

**Security posture:** the Claude API key stays on the server. The browser only ever holds the `ROADMAP_API_KEY` bearer token (single-token demo auth — narrow CORS and swap in a real auth system before any deployment beyond localhost).

## Project layout

```text
data/                         Structured scenario data (JSON)
src/engine/schema.py          Typed data model (dataclasses)
src/engine/simulator.py       FitEngine, MatrixEngine, Simulator, backtest, scenario generation
src/ui/index.html             Self-contained dashboard — Mermaid flowchart + market-share chart + chat panel
src/api/server.py             Phase 8 — FastAPI backend (/chat streaming, /revise tool-use)
src/api/scenario_patch.py     Phase 8 — diff validation + application to scenarios.json
tests/                        Phase 4 war-gaming & clarity tests + verification runner
specs/                        Implementation plan, user story, verification report
docs/walkthrough.md           Full project walkthrough
requirements.txt              Phase 8 dependencies (fastapi, uvicorn, anthropic, pydantic)
```
