# Project Walkthrough: Strategic Roadmap OTA Visualizer

**Date:** 2026-04-17
**Status:** Phases 1–4 complete · Phase 5 not started

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

A self-contained single-file dashboard (~1000 lines) with no build step required. It loads three CDN libraries:

- **Mermaid.js v10** — renders the decision tree as a flowchart SVG.
- **Chart.js v4** — renders the metrics timeline as a dual-axis area chart.
- **svg-pan-zoom v3.6.1** — wraps the rendered flowchart SVG in a pan/zoom viewport (added in the FR-3 navigability pass; see §3.3).

#### Layout

```
┌──────────────────────────────────────────────┐
│ Header: title + scenario selector dropdown   │
├──────────────────────────────┬───────────────┤
│ Strategic Decision Tree      │ Detail Panel  │
│ (Mermaid.js + svg-pan-zoom)  │ (turning-pt   │
│   ┌─────────────────────┐    │  details on   │
│   │ [−] [+] 100%  ⤢  ◎  │ ←  toolbar        │
│   └─────────────────────┘    │  hover/click) │
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

#### Navigability (FR-3) — pan / zoom / focus

Added in the FR-3 update. As the diagram grows (more turning points, more competitors, Phase 5/6 revisions), the viewport needs to scroll and magnify. Implementation:

- **`svg-pan-zoom` integration** — `initPanZoom()` runs *after* every Mermaid render. The previous instance (if any) is `.destroy()`-ed before the new SVG is inserted, and the `<svg>` element has its Mermaid-emitted inline width stripped (`removeAttribute('style')`) so the library can own sizing. Zoom is clamped to `[0.25×, 4×]`, double-click-zoom is disabled (reserved for Focus mode), and `preventMouseEventsDefault` stops page-level scroll during trackpad gestures.
- **Toolbar** — floating at the top-right of the flowchart pane: `−`, `+`, a live zoom-% readout (`aria-live="polite"`), `⤢` Reset, `◎` Focus. The Focus button stays disabled until a node is hovered.
- **Keyboard bindings** — scoped to `#diagram-container` (`role="application"`, `tabindex="0"`): `←↑↓→` pan by 40 px, `Shift+Arrow` by 200 px, `+`/`=` zoom in, `-`/`_` zoom out, `0` fits, `F` focuses the hovered node, `Esc` resets. Every hotkey calls `preventDefault()` to stop browser-level conflicts.
- **Touch** — single-finger drag pans, two-finger pinch zooms (handled by `svg-pan-zoom`). `touch-action: none` on the container prevents the browser from hijacking gestures for page scroll.
- **Focus mode** — `focusNode(el)` uses `zoomAtPoint` to scale to 150 % around the node's current screen position, then `panBy` to centre it. Double-clicking a turning-point hexagon or pressing `F` triggers it. A short CSS transition on `.svg-pan-zoom_viewport.animate` makes the jump smooth; the `.animate` class is only added when `prefers-reduced-motion: no-preference`, satisfying the reduced-motion acceptance item.
- **State preservation across scenario switches** — `onScenarioChange` now re-renders the flowchart too (not just the chart). It passes `preserveView: userZoomed` to `renderFlowchart()`: if the user has manually zoomed, pan/zoom state is captured and restored; otherwise the new diagram re-fits. The `userZoomed` flag is flipped on any programmatic or user-initiated zoom via `onZoom`, and cleared on `Reset`.
- **Hover handler rebinding** — `attachSvgHandlers()` now runs *after* `initPanZoom()` so it binds to the inner `<g.svg-pan-zoom_viewport>` that the library injects. This is critical: without the re-bind order, hover/click stop working the moment a pan or zoom is applied.

Non-pointer fallback: the keyboard arrow keys serve as the full-coverage alternative to gesture-based pan, so every part of the diagram remains reachable without a mouse or trackpad.

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

The dropdown is populated from all scenarios in `scenarios.json`. Switching it re-renders both the decision-tree flowchart (preserving pan/zoom state only if the user had manually zoomed — see §Navigability) and the metrics timeline chart, so the entire dashboard reflects the chosen scenario.

#### Data loading

On startup `init()` attempts `fetch('../../data/scenarios.json')`. This succeeds when the project is served over HTTP (e.g. `python -m http.server 8080`) and fails silently on `file://` — in which case the full base scenario is used from an embedded `FALLBACK` constant inside the script, keeping the tool functional without a server.

### Milestone M3 — UI Prototype ✅

The Mermaid diagram renders in the browser, hover effects expose turning-point details, the Chart.js timeline shows projected metrics for any selected scenario path, and the flowchart is fully navigable at any density — pan, zoom, fit, focus, and keyboard-only operation all supported (FR-3).

---

## Phase 4 — Verification & Feedback

**Files:** [tests/](../tests/) · [specs/verification_report.md](../specs/verification_report.md)

### What was built

A two-part verification harness that operationalizes both Phase-4 deliverables from the plan ("war-gaming tests" and "user review of turning-point clarity") as runnable artifacts.

#### War-gaming test suite

**File:** [tests/test_wargame.py](../tests/test_wargame.py) — 12 tests across four fixtures that each encode a piece of industry-analyst narrative and assert the engine honors it.

| Fixture | What it verifies |
|---|---|
| `NarrativeFitTests` | NDC adoption favours efficiency-led stances; GenAI breakthroughs reward innovation-led + high-AI-bias profiles; `FitEngine` scores stay in [0, 1] across all drivers and profile extremes. |
| `BranchDominanceTests` | "Build Proprietary AI" beats "Wait and See" on 2040 tech adoption; "Embrace NDC" beats "Resist NDC" on revenue; "Consolidate or Exit" is strictly the worst revenue outcome at tp-003. |
| `HistoricalBacktestTests` | `Simulator.backtest(2025)` MAE stays inside tolerance (≤ 0.05 rev / 0.02 ms / 0.05 tav) and covers at least 8 historical data points. |
| `IndustryTrendTests` | Baseline tech-adoption velocity is monotonically non-decreasing; all 18 generated scenarios keep market share and tech adoption in [0, 1]; branch probabilities sum to 1.0 per node; low-resilience competitors drift higher on the direct-booking axis than high-resilience ones. |

When any test fails, it means either the engine has drifted from its intended narrative or the narrative itself needs updating — both warrant a strategy conversation, which is exactly the feedback loop Phase 4 is meant to surface.

#### Turning-points clarity suite

**File:** [tests/test_turning_points.py](../tests/test_turning_points.py) — 11 structural tests that act as the machine-checkable proxy for the user-story acceptance criterion *"Each branch must have labeled Turning Points explaining the why of the divergence."*

The suite enforces that every node has non-empty core fields, a description long enough to review (≥ 40 chars), ≥ 2 branches with unique labels and globally-unique ids, a meaningful (non-zero) metric delta on every branch, valid probabilities, resolvable `next_node_id` references, and — importantly — that every `external_driver` is actually handled by `FitEngine.DRIVER_WEIGHTS` so no turning point silently falls through to defaults. Nodes must also be in chronological order so the Mermaid flowchart reads left-to-right.

#### Verification runner and generated report

**Files:** [tests/run_verification.py](../tests/run_verification.py) → [specs/verification_report.md](../specs/verification_report.md)

A single-command runner (`python3 -m tests.run_verification`) executes both suites and emits a self-contained markdown report for the strategy reviewer. The report contains:

1. **Overall PASS/FAIL banner** plus per-suite counts and expandable full logs.
2. **Historical backtest section** — current MAE is `0.0023` (revenue), `0.0009` (market share), `0.0045` (tech adoption) across 11 baseline points.
3. **Narrative spot-checks** — three canonical paths (optimistic, middle, pessimistic) materialized to their 2040 endpoint metrics so reviewers can sanity-check ordering without running Python.
4. **Turning Points — Clarity Review** — every node dumped with its external driver, description, and a full branch table (id, label, probability, all three metric deltas, rationale) so non-engineers can eyeball the "why" of each divergence.
5. **Reviewer Checklist** — six structured items covering driver plausibility, label realism, rationale quality, probability defensibility, metric delta sign/magnitude, and endpoint ordering.

### Verification results

All **23 tests pass** on the current "AI Leapfrog" base scenario. The historical backtest continues to confirm the engine reproduces 1990–2025 with tight error bounds, and the war-gaming suite demonstrates that the `FitEngine` driver weights and branch deltas encode the intended NDC / GenAI / direct-booking narratives consistently.

### One finding worth reviewer attention

The narrative spot-check surfaces a tuning signal: the optimistic and pessimistic paths end 2040 only `~0.5` apart on `revenue_index` (28.97 vs 28.43) despite dramatic differences on market share (46% vs 5%). This is because `Simulator._project_timeline` blends cumulative deltas against a dominant baseline timeline, which dampens revenue divergence at the tail. If strategy stakeholders expect the paths to diverge more on revenue specifically, the blending logic in [src/engine/simulator.py](../src/engine/simulator.py) is the point of adjustment — not the turning-point deltas.

### Milestone M4 — Dashboard Complete ✅

With Phases 1–3 shipped and Phase 4 verification green, the integrated dashboard is ready for strategic planning use. Phase 5 (conversational layer) can now be layered on top of a verified engine and scenario set.

### How to run verification

```bash
# From project root
python3 -m tests.run_verification
# → prints per-suite PASS/FAIL, writes specs/verification_report.md

# Or run individual suites directly
python3 -m unittest tests.test_wargame -v
python3 -m unittest tests.test_turning_points -v
```

### Follow-ups deferred from the original plan

- Gather structured strategy-stakeholder feedback against the generated `verification_report.md` reviewer checklist.
- If any checklist item comes back unchecked, adjust `FitEngine.DRIVER_WEIGHTS`, branch `probability`, or branch `metric_delta` in `schema.py` and re-run the verification suite.
- Consider adding the remaining OTA competitors from the user story (Etraveli Group, Trip.com, Hopper) as `CompetitorProfile` entries — the clarity suite will automatically extend its checks to cover them.

---

## Risk Mitigation — As Executed

| Risk (from plan) | Mitigation applied |
|---|---|
| Strategy logic too simple | `FitEngine` encodes driver-specific weights from PESTEL/Porter; `MatrixEngine` evolves competitor positions along all three 2x2+S axes per turning point |
| Hard to maintain Mermaid syntax | `buildDef()` in `index.html` generates all Mermaid syntax programmatically from `scenarios.json`; raw Mermaid is never hand-edited |
| Flowchart unreadable as nodes accumulate (FR-3) | `svg-pan-zoom` wraps every rendered Mermaid SVG, with toolbar + keyboard + touch controls (see Phase 3 §Navigability). Default view is fit-to-screen; zoom is clamped to [0.25×, 4×] so users can't lose the diagram. |
| Missing OTA current data | Kiwi.com and eDreams ODIGEO are used as baseline templates; `CompetitorProfile` is designed to accept additional entrants without schema changes |
| Narrative drift over time (Phase 4) | `tests/test_wargame.py` codifies NDC / GenAI / direct-booking narratives as executable assertions; `tests/run_verification.py` regenerates a reviewer-facing report on demand so stakeholders can re-validate turning-point clarity without reading code |

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
| [tests/test_wargame.py](../tests/test_wargame.py) | Phase 4 — 12 war-gaming narrative & trend tests |
| [tests/test_turning_points.py](../tests/test_turning_points.py) | Phase 4 — 11 turning-point clarity & structural tests |
| [tests/run_verification.py](../tests/run_verification.py) | Phase 4 — runner that executes both suites and generates the report |
| [specs/implementation_plan.md](../specs/implementation_plan.md) | Original implementation plan |
| [specs/user_story.md](../specs/user_story.md) | User story and acceptance criteria |
| [specs/verification_report.md](../specs/verification_report.md) | Phase 4 — generated verification & reviewer-checklist report |
| [reference/scenario-analysis.md](../reference/scenario-analysis.md) | Background: Porter's Five Forces, PESTEL, algorithms, data sources |
