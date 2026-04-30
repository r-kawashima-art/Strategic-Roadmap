# Project Walkthrough: Strategic Roadmap OTA Visualizer

**Date:** 2026-04-22
**Status:** Phases 1–8 shipped · Phase 9 (FR-5 conversational `/chat` + `/revise` layer) ships alongside — see the Phase 8 section for the new `/expand` mode that sits on top of it

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
- **Chart.js v4** — renders the Market Share Comparison multi-series line chart. (Originally also rendered a Metrics Timeline dual-axis area chart; that division was removed in Phase 7 per the user-story *Not-Todos*.)
- **svg-pan-zoom v3.6.1** — wraps the rendered flowchart SVG in a pan/zoom viewport (added in the FR-3 navigability pass; see §3.3).

#### Layout

```
┌──────────────────────────────────────────────┐
│ Header: title + scenario selector + Reset    │
├──────────────────────────────┬───────────────┤
│ Strategic Decision Tree      │ Detail Panel  │
│ (Mermaid.js + svg-pan-zoom)  │ (turning-pt   │
│   ┌─────────────────────┐    │  details on   │
│   │ [−] [+] 100%  ⤢  ◎  │ ←  toolbar        │
│   └─────────────────────┘    │  hover/click) │
├──────────────────────────────┴───────────────┤
│ Market Share Comparison (Chart.js)           │
│ Booking / Expedia / Trip.com / Agoda / …     │
└──────────────────────────────────────────────┘
```

The Metrics Timeline division that originally sat between the main split and the Market Share panel was removed in Phase 7 — see the §Phase 7 section below.

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

#### Scenario selector

The dropdown is populated from all scenarios in `scenarios.json`. Switching it re-renders the decision-tree flowchart (preserving pan/zoom state only if the user had manually zoomed — see §Navigability) and the Market Share Comparison chart, so the dashboard reflects the chosen scenario end-to-end.

#### Data loading

On startup `init()` attempts `fetch('../../data/scenarios.json')`. This succeeds when the project is served over HTTP (e.g. `python -m http.server 8080`) and fails silently on `file://` — in which case the full base scenario is used from an embedded `FALLBACK` constant inside the script, keeping the tool functional without a server.

### Milestone M3 — UI Prototype ✅

The Mermaid diagram renders in the browser, hover effects expose turning-point details, and the flowchart is fully navigable at any density — pan, zoom, fit, focus, and keyboard-only operation all supported (FR-3). (The Metrics Timeline chart that originally accompanied the prototype has since been removed in Phase 7.)

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

## Phase 6 — UI Polish: On-Node Metrics (FR-4 update) + Adjustable Layout

**File:** [src/ui/index.html](../src/ui/index.html)

### What was built

A single UI-polish pass that bundles two user-story changes — the tightened FR-4 requirement ("metrics *on flowchart nodes*") and the new acceptance item for a user-resizable dashboard layout. Both landed in one pass because both touch the same file and serve the same planner-facing goal.

#### On-node KPI chips (FR-4 update)

`buildDef(scenario)` now injects KPI text into every Mermaid node label so a reader gets the key signal at a glance without hovering:

| Node type | What the label now shows |
|---|---|
| **Turning-point hexagon** | `year` + ⚡ title + chip row `▲R +0.05 · ▲M +2% · ▲T +10%` built from the primary (highest-probability) branch's `metric_delta` |
| **Outcome node** | `2040` + branch label + projected 2040 KPIs (`rev 40.0× · ms 47% · tav 100%` — baseline 2040 + branch delta, clamped to \[0, 1\] on share/tav) + stance glyph (⚡ Innovation-led if `Δtav > 0.08`, ⚙ Efficiency-led otherwise) |
| **Historical milestone** | `year` + label + KPI triple inline (`rev 4.5× · ms 30% · tav 58%`) |

Helper functions `glyph`, `signed`, `signedPct`, `deltaChips`, `milestoneKpis`, and `outcomeKpis` keep all formatting in one place. Chips use plain-text glyphs (▲ / ▼ / ·) rather than HTML `<span>`s with inline colour — this sidesteps Mermaid's label-parse pitfalls around nested quotes and lets the hexagon's own colour scheme carry the positive/negative framing.

#### Adjustable layout (new acceptance criterion)

The body switched from flexbox to CSS grid driven by three custom properties that the user's drag actions write to:

```css
body {
  --row-metrics: 220px;                       /* metrics timeline row */
  --row-market:  360px;                       /* market share row     */
  grid-template-rows: auto minmax(120px, 1fr) 6px var(--row-metrics) 6px var(--row-market);
}
.main-split {
  --col-detail: 300px;                        /* detail panel column  */
  grid-template-columns: minmax(240px, 1fr) 6px var(--col-detail);
}
```

Three drag handles sit on the seams — one column handle (flowchart ↔ detail) and two row handles (main-split ↔ metrics, metrics ↔ market). Each handle:

- Has `role="separator"`, `aria-orientation`, `tabindex="0"`, and an `aria-label` — keyboard users can focus it and nudge ±8 px (±32 px with `Shift`) via arrow keys.
- Uses `pointerdown` / `pointermove` / `pointerup` so mouse and touch behave identically.
- Clamps to a per-dimension `LAYOUT_MIN` floor (`col-detail`≥240 px, `row-metrics`≥140 px, `row-market`≥200 px) and a `LAYOUT_MAX` ceiling capped at 60 % of viewport.
- On `pointerup`, reads the computed CSS variable back out and writes it to `localStorage` under key `ota-roadmap-layout-v1`. Bumping the `v1` suffix on a future release invalidates stored sizes cleanly.
- Adds `body.resizing` during a drag so `user-select: none` prevents accidental text selection across the dashboard.

A **"Reset layout"** button in the header next to the scenario selector clears `localStorage` and removes the inline CSS variables, so the shipped defaults come back.

#### Chart and flowchart reflow

Any resize — whether a drag, a window-size change, or the `Reset layout` click — fires `notifyPanesResized()`, which calls `chart.resize()`, `msChart.resize()`, and `panZoom.resize()`. A `ResizeObserver` on `.diagram-wrap`, `.chart-wrap`, and `.market-chart-wrap` catches continuous reflow during a drag, debounced through `requestAnimationFrame` so Chart.js and svg-pan-zoom never re-layout more than once per frame.

#### Responsive fallbacks

- **≤ 1024 px viewport** — the grid drops to a stacked single column, the column handle is hidden, and the detail pane gains a top border so it still reads as a distinct section.
- **≤ 640 px viewport** — all resize handles are hidden; on phone-width screens, dragged splits are more annoying than useful.

### Milestone M8 — Dashboard Polish ✅

Every Mermaid node now carries the FR-4 data (Δrev / Δshare / Δtav chips on turning points, projected 2040 KPIs + stance glyph on outcomes, KPI triples on milestones), and all three main UI divisions are user-resizable with localStorage persistence, keyboard nudging, a Reset button, and clean responsive fallbacks below 1024 / 640 px.

### Verification

`python3 -m tests.run_verification` → **29/29 PASS** (Phase 6 is UI-only; no backend tests touched). HTML tag balance is clean; page serves over HTTP and contains all the expected new hooks (`resize-handle`, `LAYOUT_KEY`, `notifyPanesResized`, `deltaChips`, `outcomeKpis`, `reset-layout-btn`). Browser-side acceptance still requires manual walkthrough — see the Phase 6 §6.2 checklist in [specs/implementation_plan.md](../specs/implementation_plan.md).

### Known gap — FR-4 primary-branch assumption

The turning-point chips show the *highest-probability* branch's delta as a "primary signal." This is deliberately a single-signal summary, not a composite — if a turning point has a near-tied 40/40/20 probability split across three branches, the hexagon chip only represents the 40 % branch. Hovering (unchanged) still surfaces every branch in the Detail Panel, and for tightly-contested nodes a planner should treat the chip as directional, not definitive.

---

## Phase 7 — Remove Metrics Timeline UI Division (Scope Cut)

**File:** [src/ui/index.html](../src/ui/index.html)

### What was built (removed)

A purely subtractive refactor executed against `src/ui/index.html` after the user story added a *Not-Todos* entry: *"Do NOT make a UI division of Metrics Timeline."* Phase 7 retracts the dual-axis metrics chart that Phase 3 originally shipped, simplifying the dashboard to header + flowchart/detail split + Market Share Comparison.

### Deletions

- **HTML** — removed the `<div class="chart-section">` block (three metric toggle buttons + `<canvas id="timeline-chart">`) and the `data-resize="row-metrics"` resize handle that preceded it.
- **CSS** — removed the rule blocks for `.chart-section`, `.metric-toggles`, `.metric-btn`, `.metric-btn.on`, and `.chart-wrap`; dropped the `--row-metrics` custom property and shortened `body { grid-template-rows: … }` to `auto · main · handle · market`; cleaned the `.chart-section` reference out of the `@media (max-width: 1024px)` rule.
- **JavaScript** — deleted `COLORS`, `renderChart()`, the module-level `chart` variable, the `activeMetrics` `Set`, and `toggleMetric()`; removed every `renderChart()` / `chart.resize()` call site (in `init()`, `onScenarioChange()`, and `notifyPanesResized()`); removed `.chart-wrap` from the `ResizeObserver.observe()` target list.
- **Layout state** — removed the `row-metrics` key from `LAYOUT_MIN`, `LAYOUT_MAX`, and `LAYOUT_TARGET`; simplified `resetLayout()` to stop removing `--row-metrics`; stripped the `key === 'row-metrics'` branches from the drag + keyboard-nudge fallbacks.

### Kept intentionally

- `turningLinePlugin` and its `Chart.register(turningLinePlugin)` registration — the Market Share Comparison chart (Phase 5) still depends on it for the 2025 / 2028 / 2032 vertical reference lines. Removing the plugin would silently break that panel.
- The `.chart-header` CSS rule — even though the plan listed it for deletion, the Market Share panel's header also uses this selector. Deleting would have broken that layout. Left a brief comment above the rule noting the Phase 7 rationale. *This is a deliberate deviation from the plan's §7.1 deletion list.*

### Migration hygiene

`readLayout()` now filters to known keys (`col-detail`, `row-market`), so a legacy `row-metrics` entry carried forward from a user's pre-Phase-7 `ota-roadmap-layout-v1` `localStorage` payload is silently dropped on read and never rewritten. No forced layout reset is needed. Phase 6's drag-handle count therefore drops from three to two (flowchart ↔ detail + main-split ↔ market) — the `--row-metrics` variable and its handle are both gone.

### Milestone M9 — Scope Cut ✅

Dashboard now renders exactly the divisions listed in `user_story.md` after the Not-Todos update. Backend tests still pass (`python3 -m tests.run_verification` → 29/29) since Phase 7 is UI-only, and the served page shows zero residual tokens for `timeline-chart`, `chart-section`, `toggleMetric`, `renderChart`, or `activeMetrics`. Browser-side acceptance (console cleanliness on page load and layout drag, market-share chart still carrying the turning-point markers) still needs manual confirmation.

### File-size delta

`src/ui/index.html` shrank from ~68 KB to ~63 KB — a ~7 % cut without touching the schema, simulator, or test layer.

---

## Phase 8 — Improvements: OTA Data Refresh + Scenario-Line Expansion

**Files:** [src/engine/schema.py](../src/engine/schema.py) · [src/api/scenario_patch.py](../src/api/scenario_patch.py) · [src/api/server.py](../src/api/server.py) · [src/ui/index.html](../src/ui/index.html) · [data/scenarios.json](../data/scenarios.json)

### What was built

Phase 8 addresses both halves of the plan's §Phase 8 goal: *"Make the data about OTA more realistic, and add a function of expanding the scenario line when the user inputs a question for the dashboard. In addition, define the data structure of the nodes to be expanded."* Two related UI and engine changes land together because they share the same conversational surface and the same confirmation flow.

#### 8.1 OTA data refresh

The competitor roster was rebuilt against FY2024 public filings (FY2025 for eDreams, which reports on a March fiscal). Three things changed in [src/engine/schema.py](../src/engine/schema.py)::`build_sample_scenario`:

| Competitor | Previous seed | New seed (Phase 8) | Source |
|---|---|---|---|
| Booking Holdings | 28.0 % · 2023 10-K ($21.4B) | 27.8 % · **FY2024 10-K ($23.7B)** | NASDAQ: BKNG |
| Expedia Group | 16.0 % · 2023 10-K ($12.8B) | 16.0 % · **FY2024 10-K ($13.7B)** | NASDAQ: EXPE |
| Airbnb | 13.0 % · 2023 10-K ($9.9B) | 13.0 % · **FY2024 10-K ($11.1B)** | NASDAQ: ABNB |
| Trip.com Group | 9.0 % · 2023 ($6.3B) | 9.0 % · **FY2024 (¥53.4B ≈ $7.3B)** | NASDAQ/HK: TCOM |
| Agoda | 4.0 % · 2023 segment | 4.5 % · **FY2024 segment (~$3.8B)** | BKNG 10-K |
| **MakeMyTrip (new)** | — | 1.0 % · **FY2024 20-F ($782M)** | NASDAQ: MMYT |
| eDreams ODIGEO | 2.0 % · FY2024 (€610M) | 2.0 % · **FY2025 (€674M)** | BME: EDR |
| Etraveli Group | 1.5 % · 2023 | 0.5 % · 2023 (rebased to revenue proxy) | CVC Capital portfolio |
| Kiwi.com | 1.0 % · 2023 | 1.0 % · **2024 (~$1.8B GMV)** | General Atlantic-backed |

Every `CompetitorProfile.metadata` now also carries a `revenue_proxy_usd_bn` field, so the normalized share is traceable back to a specific USD-denominated revenue anchor rather than the bare source citation. The tracked set sums to **74.8 %** (previously 74.5 %), leaving a ~25.2 % "Other" bucket that the plan documents as Tripadvisor / Despegar / Yatra / Webjet / Wego / LY.com / Tongcheng / Skyscanner referral revenue / fragmented regional long-tail — making the bucket legible as a concrete set rather than an opaque residual.

**MakeMyTrip was added in Phase 8** because the prior roster had no Indian OTA representation. India's outbound travel book grew +32 % YoY 2023→2024, and MMT (with Goibibo and redBus) is the dominant Indian OTA by a factor of ~5× over the next-largest competitor. Skipping it would have understated the APAC competitive envelope by the fastest-growing regional book in the industry.

The timeline also picked up a **2024 anchor point** — `TimelineDataPoint(2024, MetricSnapshot(20.5, 0.36, 0.76), "Record year — BKNG $23.7B, EXPE $13.7B, ABNB $11.1B")` — so the historical chain now reads BKNG-acquires-Booking (2005) → iPhone (2007) → COVID (2020) → **Record year (2024)** → NDC / AI pilots (2025) without the 2023→2025 gap that made the pre-COVID-to-GenAI transition look cleaner than it actually was.

#### 8.2 Expandable-node data structure

`TurningPointNode` gained three optional provenance fields in [src/engine/schema.py](../src/engine/schema.py):

| Field | Purpose |
|---|---|
| `source` | `"seed"` (hand-authored in schema.py), `"expansion"` (added via `/expand`), or `"revision"` (added via `/revise`). Default `"seed"` so existing scenarios load unchanged. |
| `source_question` | The natural-language question the user asked that triggered this node. Only meaningful when `source == "expansion"`. |
| `parent_branch_ids` | The branch IDs that were rewired to flow INTO this node at expansion time — lets a reader see *why* the DAG points here. |

All three default to empty, so pre-Phase-8 `scenarios.json` files deserialize without change. The 29-test war-gaming + clarity suite still passes on the refreshed data (all 13 clarity assertions match the new 9-competitor roster automatically; MakeMyTrip is covered by `test_every_competitor_has_source_attribution` and `test_every_competitor_has_initial_market_share` without new test code).

#### 8.3 `/expand` endpoint and Claude tool-use

**Files:** [src/api/server.py](../src/api/server.py) · [src/api/scenario_patch.py](../src/api/scenario_patch.py)

A new FastAPI route, `POST /expand`, takes a user's "what if" question and mints a new turning-point node that extends the scenario line. It uses Claude Opus (`claude-opus-4-7`, accuracy-sensitive) with a dedicated `expand_scenario_from_question` tool whose schema hard-constrains the model's output:

- `new_node.year` must be strictly greater than every existing TP year and ≤ 2040.
- `new_node.external_driver` must be one of the three drivers `FitEngine.DRIVER_WEIGHTS` knows — *NDC adoption*, *GenAI breakthrough*, *Airline direct booking dominance*. The tool's `enum` surfaces this to the model so it picks the closest conceptual match rather than inventing a new driver (an EU AI-regulation question maps to *GenAI breakthrough*; a loyalty-lock-in question maps to *Airline direct booking dominance*). This is the narrow waist that keeps `test_external_drivers_are_handled_by_fit_engine` green after an expansion.
- `rewire_branches` must list **every** currently-terminal branch in the scenario (branches with `next_node_id: null`) — non-terminal branches are explicitly out of scope.
- Branches must carry numeric metric deltas and probabilities summing to 1.0 ± 0.001.

The server then applies the expansion atomically via the new `expand_scenario` op in [src/api/scenario_patch.py](../src/api/scenario_patch.py). The op:

1. Validates `new_node` structure (required fields, ≥ 2 branches, no duplicate IDs, year in future of all existing nodes, driver in the `KNOWN_EXTERNAL_DRIVERS` set, year ≤ 2040).
2. Validates every rewire target currently has `next_node_id: null` — so an expansion can never silently detach a mid-graph edge.
3. Stamps the provenance fields (`source="expansion"`, `source_question`, `parent_branch_ids`).
4. Appends the node and rewires the terminal branches in a single atomic step.

The whole validator is exercised as a unit on a deep copy before touching `data/scenarios.json`, so a failure on the rewire step cannot leave the on-disk file with a half-applied expansion.

#### 8.4 "Expand" chat mode in the UI

**File:** [src/ui/index.html](../src/ui/index.html)

The existing chat panel grew a third mode tab next to **Ask** and **Revise**:

```
┌─ Scenario Chat ─────────────────────────────────┐
│ [ Ask ] [ Revise ] [ Expand ]                    │
│ Active scenario: AI Leapfrog                     │
│ ...                                              │
│ Ask a "what if" that extends the scenario line…  │
└──────────────────────────────────────────────────┘
```

Submitting in Expand mode calls `POST /expand`. The response renders in a confirmation card showing:

- The model's one-sentence `summary` of the proposed extension.
- The new node's id, year, title, and external driver.
- Each proposed branch with its label, probability, and all three metric deltas (Δrev / Δms / Δtav).
- Which terminal branches will be rewired (e.g. `tp-003/tp-003-a, tp-003/tp-003-b, tp-003/tp-003-c`).

The user clicks **Apply & reload** to commit — at which point the UI re-renders the Mermaid diagram and the Market Share Comparison chart from the updated `scenarios` payload returned by the server. Nothing persists before the user approves.

Expanded nodes also carry a visible provenance marker in the **Detail Panel**: when the user clicks an expanded turning-point hexagon, a purple-bordered card reads *"✨ Added from question: '…'"* above the Branches list — so a reviewer can always distinguish seed nodes from nodes minted by a chat question.

### Why these two shipped together

Both changes serve the same planner-facing goal: *a scenario simulation that matches the real OTA market more tightly, and a mechanism to extend that simulation without editing JSON or Python.* The data refresh makes the starting state defensible; the `/expand` mode makes the future state steerable. Bundling avoids two rounds of UI review for the same right-hand chat panel.

### Milestone M10 — Phase 8 Improvements ✅

- OTA roster matches the top of the 2024 public-filings leaderboard; MakeMyTrip closes the India coverage gap; every seed share is traceable to a USD revenue proxy.
- `TurningPointNode` data structure supports non-seed provenance without breaking existing scenarios or tests.
- `POST /expand` + the Expand tab ship a user-driven scenario-line expansion path that cannot violate the FitEngine's driver contract or orphan existing edges.

### Verification

`python3 -m tests.run_verification` → **29 / 29 PASS** on the refreshed data (13 turning-points clarity + 16 war-gaming tests). The expansion code path was smoke-tested in isolation via `python3 -c` against `data/scenarios.json`, confirming both the happy path (3 terminal branches rewired into a new `tp-004`) and all four validation rejection paths (unknown driver, past year, non-terminal rewire, single-branch node). Browser-side acceptance for the new Expand tab still requires running the FastAPI server locally with `ANTHROPIC_API_KEY` set — see [specs/implementation_plan.md](../specs/implementation_plan.md) §8.

### Known gap — stale embedded fallback + stale generated variants

- The `FALLBACK` constant inside [src/ui/index.html](../src/ui/index.html) still mirrors the pre-Phase-8 roster. It only surfaces under `file://` browsing; served over HTTP the UI fetches `data/scenarios.json` and sees the refreshed data immediately. Syncing the embedded fallback is a mechanical one-line update left for a follow-up.
- `data/scenarios_generated.json` contains 18 auto-generated path variants computed from the seed scenario at simulator-run time. After a `/expand` call, those 18 variants no longer reflect the live `scenarios.json` structure — the server returns a note to that effect in the `/expand` response body, and the fix is simply `python3 src/engine/simulator.py` to refresh them.

---

## Risk Mitigation — As Executed

| Risk (from plan) | Mitigation applied |
|---|---|
| Strategy logic too simple | `FitEngine` encodes driver-specific weights from PESTEL/Porter; `MatrixEngine` evolves competitor positions along all three 2x2+S axes per turning point |
| Hard to maintain Mermaid syntax | `buildDef()` in `index.html` generates all Mermaid syntax programmatically from `scenarios.json`; raw Mermaid is never hand-edited |
| Flowchart unreadable as nodes accumulate (FR-3) | `svg-pan-zoom` wraps every rendered Mermaid SVG, with toolbar + keyboard + touch controls (see Phase 3 §Navigability). Default view is fit-to-screen; zoom is clamped to [0.25×, 4×] so users can't lose the diagram. |
| Missing OTA current data | Phase 8 refreshed every competitor to FY2024/FY2025 public filings, added MakeMyTrip to cover the Indian market, and stamped a `revenue_proxy_usd_bn` on each entry so seed shares are traceable. `CompetitorProfile` remains additive — new entrants land without schema changes. |
| LLM-generated scenario extensions silently break engine narratives | `POST /expand` constrains Claude's tool output to the three drivers `FitEngine.DRIVER_WEIGHTS` knows, strictly-future years, and terminal-branch-only rewires. Every expansion is dry-run against a deep copy before `scenarios.json` is touched, and the tool-use path routes through the same `scenario_patch.apply_diff` validator `/revise` uses — single validation surface for both conversational write paths. |
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
| [src/api/server.py](../src/api/server.py) | FastAPI backend — `/chat` (SSE), `/revise` (structured diff), `/expand` (Phase 8 scenario-line expansion) |
| [src/api/scenario_patch.py](../src/api/scenario_patch.py) | Structured-diff validator shared by `/revise` and `/expand`; Phase 8 added the `expand_scenario` op |
| [src/ui/index.html](../src/ui/index.html) | Self-contained dashboard — Mermaid flowchart + Market Share Comparison chart + chat panel with Ask / Revise / Expand modes |
| [tests/test_wargame.py](../tests/test_wargame.py) | Phase 4 — 12 war-gaming narrative & trend tests |
| [tests/test_turning_points.py](../tests/test_turning_points.py) | Phase 4 — 11 turning-point clarity & structural tests |
| [tests/run_verification.py](../tests/run_verification.py) | Phase 4 — runner that executes both suites and generates the report |
| [specs/implementation_plan.md](../specs/implementation_plan.md) | Original implementation plan |
| [specs/user_story.md](../specs/user_story.md) | User story and acceptance criteria |
| [specs/verification_report.md](../specs/verification_report.md) | Phase 4 — generated verification & reviewer-checklist report |
| [reference/scenario-analysis.md](../reference/scenario-analysis.md) | Background: Porter's Five Forces, PESTEL, algorithms, data sources |

## Phase 9

What was built:

- LLM integration to ask questions about the scenarios
- Add "Ask", "Revise", "Expand" buttons to the dashboard for allowing editing nodes and branches
- Tweaked scenario integration so that new added ones connect to the exisiting graph.
- In phase 9.5, we added a new logic to ensure that the total probability of branches on a node always sums to 1.0.

---

### Phase10

what was built:

- Scenario Storage Function
- Metrics Update Function
