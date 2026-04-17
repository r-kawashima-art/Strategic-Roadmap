# Strategic-Roadmap

A programmable simulation and visualization system for the Online Travel Agency (OTA) industry. Models how AI disruption, NDC adoption, and airline direct-booking trends reshape the competitive landscape from 1990 to 2040, and renders the results as an interactive browser dashboard.

For the full design, see [docs/walkthrough.md](docs/walkthrough.md).

## Prerequisites

- Python 3.9+ (standard library only — no `pip install` required)
- A modern browser (Chrome, Firefox, Safari, Edge)

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

## Project layout

```text
data/                         Structured scenario data (JSON)
src/engine/schema.py          Typed data model (dataclasses)
src/engine/simulator.py       FitEngine, MatrixEngine, Simulator, backtest, scenario generation
src/ui/index.html             Self-contained dashboard — Mermaid flowchart + Chart.js timeline
tests/                        Phase 4 war-gaming & clarity tests + verification runner
specs/                        Implementation plan, user story, verification report
docs/walkthrough.md           Full project walkthrough
```
