# Project Walkthrough: Strategic Roadmap OTA Visualizer

**Date:** 2026-04-17
**Status:** Phases 1–3 complete · Phase 4 in progress

---

## Overview

This project is a "programmable" strategic simulation and visualization system for the Online Travel Agency (OTA) industry. It models how AI disruption, NDC adoption, and airline direct-booking trends will reshape the competitive landscape from 1990 to 2040, and exposes the results as an interactive browser-based dashboard.

The system is split into three layers that mirror the plan's phases:

```text
data/scenarios.json          ← Phase 1: structured data layer
src/engine/
  schema.py                  ← Phase 1: typed data model
  simulator.py               ← Phase 2: simulation & scenario generation
src/ui/
  index.html                 ← Phase 3: interactive visualization
```

---

## Phase 1 — Data Schema

**File:** [src/engine/schema.py](../src/engine/schema.py)

### What was built

A fully-typed Python data model using `dataclasses` that defines every entity in the system. Key classes:

| Class | Purpose |
|---|---|
| `MetricSnapshot` | Three KPIs at a point in time: `revenue_index`, `market_share`, `tech_adoption_velocity` |
| `TimelineDataPoint` | A year + `MetricSnapshot` + optional milestone label |
| `BranchOutcome` | A strategic choice branching from a turning point, with metric deltas and probability |
| `TurningPointNode` | A decision node: year, external driver (e.g. "NDC adoption"), and list of `BranchOutcome`s |
| `StrategicProfile` | One of three OTA archetypes (Cost Leader, Differentiator, Niche Search) with AI adoption bias and direct-booking resilience |
| `MatrixPosition` | A competitor's live position in the 2x2+S matrix |
| `CompetitorProfile` | Baseline for a named OTA (Kiwi.com, eDreams ODIGEO) |
| `Scenario` | Top-level container: id, name, description, timeline, nodes, profiles, competitors, metadata |

`StrategicStance` is a `str`-based `Enum` with two values — `Innovation-led` and `Efficiency-led` — which serves as the third dimension of the 2x2+S matrix.

The module also provides `build_sample_scenario()` (the "AI Leapfrog" base scenario) and `save_scenarios()` / `load_scenarios()` helpers that serialize to/from `data/scenarios.json`.

### Milestone M1 — Data Layer ✅

`data/scenarios.json` is finalized. The schema supports adding new competitors (e.g. Trip.com, Hopper) by extending the `competitors` list, satisfying the scalability requirement from the user story.

---

## Phase 2 — Scenario Simulation Engine

**File:** [src/engine/simulator.py](../src/engine/simulator.py)

### What was built

Three collaborating classes orchestrated by a CLI `main()` entry point.

#### FitEngine

Calculates a strategic-fit score (0–1) for each competitor at every turning point. The score weights three profile traits differently per external driver:

| External Driver | Primary weight |
|---|---|
| NDC adoption | `direct_booking_resilience` (0.6) |
| GenAI breakthrough | `ai_adoption_bias` (0.6) |
| Airline direct booking dominance | `direct_booking_resilience` (0.5) |

The fit score then modulates how branch metric deltas are applied: high fit amplifies positive deltas and dampens negative ones; low fit does the reverse. This encodes the PESTEL/Porter logic as a numeric signal rather than a lookup table.

#### MatrixEngine

Evolves each competitor's 2x2+S position after every turning point:

- **AI adoption axis** — pulled toward the profile's `ai_adoption_bias`, accelerated by the branch's tech adoption delta.
- **Direct booking axis** — pushed upward by external pressure scaled by the driver; absorbed by the competitor's `direct_booking_resilience`.
- **Strategic stance** — can flip from Efficiency-led to Innovation-led if a branch's tech adoption delta exceeds 0.10 (forced innovation).

#### Simulator

Orchestrates full simulation runs over a `Scenario`:

- **`run(branch_choices)`** — accepts an explicit `{node_id: branch_id}` map, processes nodes in chronological order, and returns a `SimulationResult` with per-step competitor states and a projected timeline.
- **`backtest(historical_cutoff=2025)`** — auto-selects the highest-probability branch at each historical node, runs the simulation, and reports Mean Absolute Error per metric against the baseline timeline. This validates engine logic before projecting into the future.
- **`generate_scenarios(weights)`** — enumerates all 2×3×3 = 18 branch combinations, scores each with a composite weighted metric, and returns a ranked list of `Scenario` objects. Results are written to `data/scenarios_generated.json`.

### Output

Running `python simulator.py` produces:

1. A backtest report (MAE per metric against 1990–2025 historical data).
2. A detailed walk-through of an optimistic simulation path showing fit scores, metric evolution, and matrix positions for both competitors at each turning point.
3. `data/scenarios_generated.json` — all 18 generated path scenarios, ranked by composite score.
4. `data/scenarios.json` — updated to contain the base scenario plus the top-ranked generated scenario side-by-side, ready for the UI to consume.

### Milestone M2 — Simulation Alpha ✅

The engine produces logically valid JSON branches. The top-ranked generated path is:

> **"Embrace NDC → Build Proprietary AI → Become Aggregator Platform"** — composite score 125.3, combined probability 6.3%.

---

## Phase 3 — Interactive Visualization

**File:** [src/ui/index.html](../src/ui/index.html)

### What was built

A self-contained single-file dashboard (~800 lines) with no build step required. It loads two CDN libraries:

- **Mermaid.js v10** — renders the decision tree as a flowchart SVG.
- **Chart.js v4** — renders the metrics timeline as a dual-axis area chart.

#### Layout

```
┌──────────────────────────────────────────────┐
│ Header: title + scenario selector dropdown   │
├──────────────────────────────┬───────────────┤
│ Strategic Decision Tree      │ Detail Panel  │
│ (Mermaid.js flowchart)       │ (turning-pt   │
│                              │  details on   │
│                              │  hover/click) │
├──────────────────────────────┴───────────────┤
│ Metrics Timeline (Chart.js)                  │
│ [Revenue Index] [Market Share] [Tech Adopt.] │
└──────────────────────────────────────────────┘
```

#### Mermaid decision tree

The diagram is built programmatically from `scenarios.json` by `buildDef(scenario)`. It produces a left-to-right (`flowchart LR`) DAG:

1. **Historical chain** — labeled milestones from 1990 to 2023 rendered as rounded rectangles with a dark grey style.
2. **Turning point hexagons** — styled in purple (`⚡ year · title`), one per node in the scenario.
3. **Branch edges** — each carries the branch label and probability percentage as an edge label; edges from tp-001 and tp-002 converge on the next turning point node, while edges from tp-003 terminate at outcome nodes.
4. **Outcome nodes** — green for positive revenue delta, red for negative.

Node IDs in the generated Mermaid definition (e.g. `TP_tp_001`, `END_tp_003_b`) are mapped into a `nodeMap` object so that SVG elements can be linked back to their source data after rendering.

#### Hover effects on turning points

After Mermaid renders the SVG, `attachSvgHandlers()` queries all `g.node` elements. It strips Mermaid's `flowchart-` prefix and trailing `-N` suffix from each element's `id` attribute to recover the original node key, then looks it up in `nodeMap`.

Three events are attached to each matched element:

| Event | Behaviour |
|---|---|
| `mouseenter` | Shows a fixed-position tooltip (title + driver/description) and populates the detail panel (if unpinned) |
| `mousemove` | Repositions the tooltip, clamped to viewport edges |
| `mouseleave` | Hides the tooltip; clears the detail panel if unpinned |
| `click` | Pins/unpins the detail panel to that node |

#### Detail panel

Shows structured information for whichever node is active:

- **Turning points** — year badge, title, description, external driver tag, and a card per branch with its label, probability pill, description, and metric delta chips (Revenue Δ, Market Share Δ, Tech Adoption Δ) colour-coded green/red.
- **Historical milestones** — year, label, and the three KPI values at that point.
- **Outcome nodes** — 2040 label, outcome description, and metric delta chips.

#### Metrics timeline chart

A dual-axis area chart with smooth curves (`tension: 0.4`):

- **Left axis** — Revenue Index (absolute multiplier vs. 1990 baseline).
- **Right axis** — Market Share % and Tech Adoption %.
- Data points with milestone labels render with a larger radius (5 px); unlabelled points use 2 px.
- A custom `turningLinePlugin` draws dashed purple vertical reference lines at turning-point years (2025, 2028, 2032).
- Tooltips show the milestone label when the cursor aligns with a labelled year.

Three toggle buttons above the chart independently enable/disable each metric; at least one must always remain active.

#### Scenario selector

The dropdown is populated from all scenarios in `scenarios.json`. Switching it re-renders only the timeline chart — the decision tree always reflects the base scenario's full path space.

#### Data loading

On startup `init()` attempts `fetch('../../data/scenarios.json')`. This succeeds when the project is served over HTTP (e.g. `python -m http.server 8080`) and fails silently on `file://` — in which case the full base scenario is used from an embedded `FALLBACK` constant inside the script, keeping the tool functional without a server.

### Milestone M3 — UI Prototype ✅

The Mermaid diagram renders in the browser, hover effects expose turning-point details, and the Chart.js timeline shows the projected metrics for any selected scenario path.

---

## Phase 4 — Verification & Feedback

**Status:** In progress.

### What is ready for war-gaming

The `Simulator.backtest()` method provides the formal verification mechanism called for in the plan. On the "AI Leapfrog" base scenario it confirms that the engine's highest-probability projections align with the 1990–2025 historical baseline with low MAE, validating the PESTEL/Five Forces logic encoded in `FitEngine`.

The UI's scenario-comparison capability (switching between the 18 generated paths in the dropdown) enables informal war-gaming: a strategy team can walk through each path, observe how the decision tree and metrics diverge, and challenge whether the probability weights and metric deltas reflect real industry dynamics.

### Remaining work

- Gather structured feedback on the clarity of turning-point descriptions from strategy stakeholders.
- Adjust `FitEngine.DRIVER_WEIGHTS` and branch `probability` values based on war-gaming outcomes.
- Consider adding the remaining OTA competitors from the user story (Etraveli Group, Trip.com, Hopper) as `CompetitorProfile` entries in `schema.py`.

---

## Risk Mitigation — As Executed

| Risk (from plan) | Mitigation applied |
|---|---|
| Strategy logic too simple | `FitEngine` encodes driver-specific weights from PESTEL/Porter; `MatrixEngine` evolves competitor positions along all three 2x2+S axes per turning point |
| Hard to maintain Mermaid syntax | `buildDef()` in `index.html` generates all Mermaid syntax programmatically from `scenarios.json`; raw Mermaid is never hand-edited |
| Missing OTA current data | Kiwi.com and eDreams ODIGEO are used as baseline templates; `CompetitorProfile` is designed to accept additional entrants without schema changes |

---

## How to Run

### 1. Generate / refresh scenarios

```bash
cd src/engine
python simulator.py
# Writes data/scenarios.json and data/scenarios_generated.json
```

### 2. Open the dashboard

**Option A — with live data fetch (recommended):**

```bash
# From project root
python -m http.server 8080
# Open http://localhost:8080/src/ui/index.html
```

**Option B — directly (uses embedded fallback data):**
Open `src/ui/index.html` in any browser. The embedded `FALLBACK` constant mirrors the base "AI Leapfrog" scenario; generated paths will not appear in the scenario dropdown.

---

## File Index

| Path | Role |
|---|---|
| [data/scenarios.json](../data/scenarios.json) | Base scenario + top-ranked generated path (source of truth for the UI) |
| [data/scenarios_generated.json](../data/scenarios_generated.json) | All 18 generated scenario variants, ranked by composite score |
| [src/engine/schema.py](../src/engine/schema.py) | Typed data model — dataclasses, enums, JSON serialization |
| [src/engine/simulator.py](../src/engine/simulator.py) | FitEngine, MatrixEngine, Simulator, backtest, scenario generation |
| [src/ui/index.html](../src/ui/index.html) | Self-contained dashboard — Mermaid flowchart + Chart.js timeline |
| [specs/implementation_plan.md](../specs/implementation_plan.md) | Original implementation plan |
| [specs/user_story.md](../specs/user_story.md) | User story and acceptance criteria |
| [reference/scenario-analysis.md](../reference/scenario-analysis.md) | Background: Porter's Five Forces, PESTEL, algorithms, data sources |
