# Strategic-Roadmap

A programmable simulation and visualization system for the Online Travel Agency (OTA) industry. Models how AI disruption, NDC adoption, and airline direct-booking trends reshape the competitive landscape from 1990 to 2040, and renders the results as an interactive browser dashboard.

For the full design, see [docs/walkthrough.md](docs/walkthrough.md).

## Prerequisites

- Python 3.9+
- A modern browser (Chrome, Firefox, Safari, Edge)
- **For the full dashboard with the conversational layer (Phase 9 / FR-5):** a small set of Python packages (`fastapi`, `uvicorn`, `anthropic`, `pydantic`) and an Anthropic API key. Phases 1–7 run on the standard library alone.

## How to run

All commands below assume you are in the **project root** (`Strategic-Roadmap/`).

### 1. Generate scenario data

```bash
(cd src/engine && python3 simulator.py)
```

The parentheses run `simulator.py` in a subshell so your working directory stays at the project root. `simulator.py` uses a sibling import (`from schema import ...`) that requires it to run from inside `src/engine/`.

This writes:

- `data/scenarios.json` — base "AI Leapfrog" scenario + top-ranked generated path (consumed by the UI)
- `data/scenarios_generated.json` — all 18 branch-combination variants, ranked by composite score

### 2. Start the API server and open the dashboard

The FastAPI server serves both the dashboard UI and the API from the same port, so you only need one process.

**Install dependencies** (one-time — a venv is recommended):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Set up credentials.** Copy `.env.example` to `.env`, fill in the two values, then source it:

```bash
cp .env.example .env
# Edit .env — set ROADMAP_API_KEY and ANTHROPIC_API_KEY
source .env
```

These two credentials are not interchangeable:

| Credential | Where it comes from | Who sees it |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) — externally issued, pay-per-token | Server only; never sent to the browser |
| `ROADMAP_API_KEY` | **You pick it.** Any random string. Acts as a shared-secret bearer token. | The server env var **and** the browser ⚙ API settings — they must match |

To generate a strong `ROADMAP_API_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Start the server:**

```bash
.venv/bin/python -m uvicorn src.api.server:app --port 8787 --reload
```

Open [http://localhost:8787](http://localhost:8787) in your browser. The dashboard loads automatically. Click **💬 Chat** in the header, open ⚙ API settings, and paste your `ROADMAP_API_KEY`. The browser stores it in `localStorage` — you won't be asked again on the same browser.

**Offline fallback (no server):** open [src/ui/index.html](src/ui/index.html) directly as a file. The flowchart and market-share chart work, but the chat panel requires the server.

### 3. Run Phase 4 verification

```bash
python3 -m tests.run_verification
```

Executes both the war-gaming suite (12 tests) and the turning-point clarity suite (11 tests), then writes a reviewer-facing report to [specs/verification_report.md](specs/verification_report.md). Exits non-zero if any test fails.

To run a single suite:

```bash
python3 -m unittest tests.test_wargame -v
python3 -m unittest tests.test_turning_points -v
```

### 4. Using the conversational layer (Phase 9 / FR-5)

Once the server is running and your bearer token is entered in ⚙, the chat panel offers three modes:

- **Ask** — ask scenario-grounded questions; Claude answers from the loaded scenario data with streaming responses.
- **Revise** — describe a change in plain English ("bump tp-001-a probability to 75%"). Claude returns a structured diff, which previews **live in the flowchart** before you commit. Use **Save as new** to persist the revision as a named scenario in the dropdown; **Discard** restores the original.
- **Expand** — ask a "what if" question to extend the scenario line with a new turning point after the current last node.

#### API endpoints

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/healthz` | none | Liveness probe |
| `GET` | `/` | none | Serves `src/ui/index.html` |
| `GET` | `/scenarios` | none | Returns all scenarios (base + user-saved) |
| `POST` | `/chat` | bearer | Streams Claude's scenario-grounded answer as SSE (`claude-sonnet-4-6`) |
| `POST` | `/revise` | bearer | Translates NL → structured diff via Claude tool use; returns **preview only** — no write (`claude-opus-4-7`) |
| `POST` | `/scenarios` | bearer | Saves a new named scenario (AI-revised or blank) |
| `PUT` | `/scenarios/{id}` | bearer | Renames or updates description of a user scenario (403 for base) |
| `DELETE` | `/scenarios/{id}` | bearer | Deletes a user scenario (403 for base) |
| `POST` | `/expand` | bearer | Extends the scenario line with a new turning point from a "what if" question |

**Security posture:** the Anthropic API key stays on the server. The browser only holds the `ROADMAP_API_KEY` bearer token (single-token demo auth — narrow the CORS allowlist in `src/api/server.py` and replace with per-user auth before any deployment beyond localhost).

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
