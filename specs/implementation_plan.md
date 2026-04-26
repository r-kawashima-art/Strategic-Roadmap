# Implementation Plan: Strategic Roadmap OTA Visualizer

## 1. Objective

Develop a "programmable" system that simulates and visualizes future strategic scenarios for the Online Travel Agency (OTA) industry, focusing on AI disruption and corporate decision-making.

## 2. Directory Structure

```text
Strategic-Roadmap/
├── data/
│   └── scenarios.json         # Structured scenario data (Branches & Nodes)
├── src/
│   ├── engine/
│   │   └── simulator.py      # Logic to process PESTEL/Five Forces into scenarios
│   ├── api/
│   │   └── server.py         # FastAPI backend: chat endpoint + scenario revision (Phase 5)
│   └── ui/
│       └── index.html        # Interactive flowchart visualization
└──  specs/
　  ├── user_story.md         # Updated requirements
　  └── implementation_plan.md # This document
```

## 3. Implementation Steps

### Phase 1: Data Schema Definition

- Define a `Scenario` object that includes:
  - `id`: Unique identifier.
  - `name`: Scenario title (e.g., "AI Leapfrog").
  - `timeline`: Data points from 1990 to 2040.
  - `nodes`: List of decision points (Turning Points).
  - `strategic_profiles`: Definitions for "Cost Leader", "Differentiator", and "Niche Search".
  - `metrics`: Impact on Revenue, Market Share, and Tech Adoption Velocity.

### Phase 2: Scenario Simulation Engine

- **Strategic Positioning Logic**: Implement a "Fit Engine" that calculates how each OTA's positioning (e.g., Kiwi's Virtual Interlining vs. eDreams' Prime Subscription) responds to external shocks.
- **2x2+S Matrix**: Extend the 2x2 matrix with a 3rd dimension: **Strategic Stance**.
  - Axis 1: Airline Direct Booking Dominance.
  - Axis 2: AI Agent Adoption.
  - Dimension 3: Strategic Orientation (Innovation-led vs. Efficiency-led).
- **Historical Backtesting**: Validate the engine using historical 1990-2025 data before projecting to 2040.
- **Scenario Generation**: Create a script that generates `scenarios.json` dynamically based on input weights and competitor positioning.

### Phase 3: Interactive Visualization

As `scenarios.json` grows (more turning points, more competitors, more generated paths), the Mermaid flowchart quickly outgrows the viewport. Phase 3 is rewritten around **navigability as a first-class concern** so a strategy planner can fly over the 1990–2040 roadmap at any density without losing the ability to inspect a single decision node.

#### 3.1 Flowchart Rendering

- Use **Mermaid.js** (CDN, no build step) to render `scenarios.json` as a `flowchart LR` DAG — historical milestones → turning-point hexagons → outcome nodes.
- Node styling: purple hexagons for turning points (`⚡ year · title`), rounded grey rectangles for historical milestones, green/red terminal nodes keyed to the revenue sign of the final branch delta.
- Mermaid source is generated programmatically by `buildDef(scenario)` so raw Mermaid is never hand-edited (satisfies the "Mermaid maintainability" risk in §5).

#### 3.2 Detail Inspection (Hover + Click)

- `attachSvgHandlers()` binds `mouseenter` / `mousemove` / `mouseleave` / `click` to every `g.node` in the rendered SVG.
- Hover fills the right-hand **Detail Panel** (turning-point rationale, branch options with probability / Δrev / Δms / Δtav chips) and shows a cursor-tracking tooltip.
- Click pins the panel to a node; a second click unpins.

#### 3.3 Navigability (FR-3 update) — primary goal of this phase

The flowchart **must be scrollable horizontally and vertically and magnifiable in and out** (FR-3). The following interactions ship together — each one exists because the others aren't sufficient on their own:

| Capability | Mouse / trackpad | Keyboard | Touch | Notes |
|---|---|---|---|---|
| **Pan** | Click-drag anywhere on blank canvas | `←↑↓→` nudges 40 px; `Shift+Arrow` nudges 200 px | Single-finger drag | Nodes themselves stay clickable — panning starts from canvas background only. |
| **Zoom** | Wheel / pinch zooms toward the cursor | `+` / `=` to zoom in, `-` to zoom out, `0` to reset | Two-finger pinch | Zoom range clamped to `[0.25×, 4×]` so users can't lose the diagram. |
| **Fit-to-viewport** | `Reset` button in toolbar | `0` | Two-finger double-tap | Default view on initial load and after scenario switch (unless the user already manually zoomed). |
| **Focus mode** | Double-click a turning point | `F` while a node is hover-focused | Double-tap | Smoothly animates to centre the node at 150 % zoom. `Esc` exits focus. |
| **Scrollbars** | Appear automatically when zoom > 100 % | — | — | Non-pointer fallback so every region of the diagram is reachable without gesture-based pan. |

Supporting UI elements:

- **Toolbar** — small floating panel at the top-right of the flowchart pane with `+`, `−`, `Reset`, `Focus`, and a zoom-percentage readout. Stays within the flowchart pane so it doesn't overlap the Detail Panel.
- **Mini-map (optional)** — collapsible thumbnail in the bottom-right showing the full diagram with the current viewport rectangle; click-to-jump. Hidden by default; toggle lives in the toolbar. Kept optional because it's the largest addition to the visual surface and should ship only if user testing shows users get lost.
- **Accessibility** — the toolbar buttons have `aria-label`s; the SVG container has `role="application"` and `tabindex="0"` so keyboard focus lands on it; `prefers-reduced-motion` disables zoom and focus-mode animations.

Implementation notes (for the single-file `src/ui/index.html`):

- Use the **`svg-pan-zoom`** library via CDN. It handles wheel-zoom toward cursor, pan inertia, touch, and zoom bounds — reinventing these correctly is a multi-week project we should not take on.
- Initialise after every Mermaid render; keep the instance in a module-level variable so scenario switches can call `.destroy()` cleanly before re-initialising.
- `attachSvgHandlers()` runs **after** pan/zoom init, on the inner `<g>` that `svg-pan-zoom` creates, so hover events fire at every zoom level. Any re-render (scenario switch, `/revise` response in Phase 5) must rebind both pan/zoom and hover handlers in that order.
- Pan/zoom state is preserved across scenario switches **only** if the user has manually zoomed; otherwise the new scenario re-fits. This prevents users losing context after exploring, while keeping the default view sane.

#### 3.4 Acceptance for FR-3

- [ ] The flowchart is fully reachable — every node can be brought into view — when zoomed to 400 %.
- [ ] Hover detail fires correctly at every zoom level between 25 % and 400 %.
- [ ] Keyboard-only users can pan, zoom, reset, and enter/exit focus mode without a pointer.
- [ ] Touchpad users can pinch-zoom and two-finger-pan without triggering page zoom.
- [ ] Switching scenarios re-fits the new diagram unless the user had manually zoomed, in which case zoom state persists.
- [ ] Reduced-motion users see no zoom / focus animations.

### Phase 4: Verification & Feedback

- Conduct "War-gaming" tests to ensure scenario paths are logically consistent with industry trends (NDC, GenAI).
- User review of the "Turning Points" clarity.

### Phase 5: Market Share Comparison (FR-6)

FR-6 adds a cross-OTA market-share view so a strategy planner can compare how Expedia, Booking.com, Trip.com, Agoda, Kiwi.com, and eDreams Odigeo track against each other inside any given scenario.

#### 5.1 Data Layer Extension

- Extend `src/engine/schema.py::build_sample_scenario()` with `CompetitorProfile` entries for the additional top-share OTAs (**Expedia Group**, **Booking Holdings**, **Trip.com Group**, **Agoda**) in addition to the existing Kiwi.com and eDreams Odigeo. Each entry gets an `initial_position` consistent with its public strategic posture and its `default_profile` set to Cost Leader / Differentiator / Niche Search.
- Add an `initial_market_share: float` field to `CompetitorProfile` (0–1), seeded from the most recent public annual-report / 10-K filings. Record the source year in `CompetitorProfile.metadata` so the clarity suite can later assert every competitor is attributed.
- `Simulator.run()` already tracks per-competitor `CompetitorState.metrics.market_share`; add a helper `project_market_shares()` that reshapes the per-step competitor states into `{competitor_name: [(year, share)]}` and emits it on the generated scenario as `market_share_projection`. Normalize shares per year so the set of tracked OTAs plus an implicit "Other" bucket sums to 1.0 — otherwise stacked / comparative views will mislead.
- `FR-1` still requires ≥ 4 distinct scenarios; this phase does not alter scenario count.

#### 5.2 UI Comparison Panel

Extend `src/ui/index.html` with a new **"Market Share"** panel beneath the existing metrics timeline (or behind a tab, if vertical space becomes tight):

- **Multi-series line chart** — one Chart.js line per competitor, x-axis = year (1990–2040), y-axis = market share %. Reuses the existing `turningLinePlugin` so the 2025 / 2028 / 2032 vertical markers align with the upper chart.
- **Legend toggles** — click a competitor in the legend to hide/show its line; at least one must remain visible. Toggling persists across scenario switches.
- **Summary table** — below the chart, rows per competitor with 2025 / 2030 / 2040 share and the Δ vs. the base "AI Leapfrog" scenario for any selected path-comparison scenario. Green/red deltas match the existing colour tokens.
- **Scenario link-up** — the chart rebinds when the scenario dropdown changes, so the same panel serves every generated path.

#### 5.3 Reference Data Sourcing

- Seed values for Expedia, Booking Holdings, Trip.com Group, and Agoda come from each company's most recent 10-K / annual report. Because OTAs report revenue rather than "market share" directly, the seed is a normalized revenue-share proxy — defensible for strategy simulation but **not** a financial forecast.
- Every new `CompetitorProfile` must carry `metadata = {"source": "<filing>", "source_year": "<yyyy>"}`. Extend `tests/test_turning_points.py` with an assertion that every competitor has non-empty `source` and `source_year`, so the review report flags any undocumented entries.

#### 5.4 Test Extensions

- Add a test in `tests/test_wargame.py` that every generated scenario's `market_share_projection` keeps each competitor's share in `[0, 1]` and that the sum across tracked OTAs plus "Other" is `1.0 ± ε` at every year.
- Add a turning-point test that the stronger-resilience / higher-AI-bias competitors end 2040 with a higher share than weaker ones under the optimistic path (narrative consistency check, same shape as the existing Phase 4 tests).

### Phase 6: UI Polish — On-Node Metrics (FR-4 update) + Adjustable Layout

Two user-story changes land here because both touch `src/ui/index.html` and both serve the same goal — letting the strategy planner read richer at-a-glance information *and* control how the dashboard partitions screen real estate. Bundling them avoids re-opening Phase 3 and lets the team ship one coherent polish pass.

#### 6.1 Adjustable Layout (new acceptance criterion)

User-story acceptance addition: *"The layout of the UI should be flexible, and the size of each main UI division (e.g., scenario visualization, market share comparison, etc.) should be adjustable by the user."*

Today's layout is a fixed 3-zone grid: `(flowchart pane | detail panel)` over `(metrics timeline)` over `(market-share panel)`. Replace with user-adjustable splits:

- **Draggable dividers** on all three major seams:
  1. Flowchart pane ↔ Detail panel (horizontal).
  2. Main-split ↔ Turning-point timeline (vertical).
  3. Turning-point timeline ↔ Market-share panel (vertical).
- **Minimum sizes** — every division has an enforced `min-width` / `min-height` so a user can't collapse a pane out of existence. Handles clamp visibly at the limit.
- **Persistence** — serialize pane sizes to `localStorage` under key `ota-roadmap-layout-v1`. The planner's preferred layout survives reloads; bumping the version suffix forces a reset the next release.
- **Reset to default** — a small "Reset layout" control in the header (next to the scenario selector). Clearing `localStorage` and re-applying the baseline grid sizes restores the shipped defaults.
- **Responsive fallback** — below 1024 px viewport width, drop to a single-column stack (flowchart → detail → metrics → market share) with vertical-only resize handles. Below 640 px, disable resize handles entirely — the screen is too narrow for meaningful splits.
- **Implementation** — use native `resize: both` CSS where it fits, plus small custom drag-handle components for flex-child splits CSS can't express. No layout library: budget is **< 150 lines** of vanilla JS. Use a `ResizeObserver` on each pane to trigger `chart.resize()` on Chart.js instances and `panZoom.resize()` on svg-pan-zoom, so contents don't crop or leave empty space after a drag.

#### 6.2 Acceptance for Phase 6

- [ ] Every turning-point hexagon shows Δrev / Δshare / Δtav chips legible at the default fit-to-viewport zoom level.
- [ ] Every outcome node shows 2040 Revenue Index × market share % + dominant stance glyph.
- [ ] Every historical milestone shows its KPI triple inline.
- [ ] All three pane dividers are draggable on ≥ 1024 px viewports.
- [ ] Pane sizes persist across page reloads; "Reset layout" restores the default grid.
- [ ] Below 1024 px the layout stacks gracefully; below 640 px resize handles are disabled.
- [ ] Chart.js and svg-pan-zoom resize correctly when any divider is dragged — no cropping, no empty bands, no stale SVG viewport.

### Phase 7: Remove Metrics Timeline UI Division (Scope Cut)

The user story's new *Not-Todos* list explicitly opts the **Metrics Timeline** out of the UI:

> *"Do NOT make a UI division of Metrics Timeline."*

This phase retracts the Metrics Timeline that was introduced in Phase 3 (and included in the M3 / M4 milestones) so the shipped dashboard matches the revised scope. It is **purely subtractive** — no schema, simulator, data-layer, or test changes — and can execute independently of Phase 7 (FR-5) in either order. After Phase 8, the dashboard renders header + flowchart/detail split + market-share panel only, with **two** resize handles instead of the three described in Phase 6.

#### 7.1 Deletions in `src/ui/index.html`

- **HTML** — delete the `<div class="chart-section">` block entirely (metric toggle buttons for *Revenue Index / Market Share / Tech Adoption* plus `<canvas id="timeline-chart">`). Delete the resize handle `data-resize="row-metrics"` that sits between the main split and the timeline.
- **CSS** — delete the rule blocks for `.chart-section`, `.chart-header`, `.metric-toggles`, `.metric-btn`, `.metric-btn.on`, and `.chart-wrap`. Remove the `--row-metrics` CSS custom property and simplify `body { grid-template-rows: … }` to carry only *header + main-split + row-handle + market-section*.
- **JavaScript** —
  - Delete the `COLORS` token object used by the timeline chart.
  - Delete `renderChart()` and the module-level `chart` variable.
  - Delete `toggleMetric()` and the `activeMetrics` `Set`.
  - Remove every `renderChart()` / `chart.resize()` call site — currently in `init()`, `onScenarioChange()`, and `notifyPanesResized()`.
  - Remove the `'row-metrics'` key from `LAYOUT_MIN`, `LAYOUT_MAX`, and `LAYOUT_TARGET`. On `applyStoredLayout()`, silently ignore any `row-metrics` entry left over in `localStorage` from earlier releases — do not re-write it on next save.
  - Remove `.chart-wrap` from the `ResizeObserver.observe()` target list.
- **Keep** the `turningLinePlugin` registration and its reference to `baseScenario.nodes`. The **Market Share Comparison** chart (Phase 5) relies on this plugin to render the 2025 / 2028 / 2032 vertical markers; removing the plugin would silently break that panel.

#### 7.2 Migration hygiene

- Running `python3 src/engine/simulator.py` still emits `market_share_projection` for every scenario — the data layer is untouched. A clean reload after the cut should show zero network 404s and zero console errors about undefined handlers.
- Users carrying a stored layout under `ota-roadmap-layout-v1` with an orphaned `row-metrics` key see the rest of their persisted sizes honoured; the obsolete key is simply dropped on next write. No forced reset required.
- Update [docs/walkthrough.md](../docs/walkthrough.md): delete the *Metrics timeline chart* sub-section under Phase 3 and shrink the layout ASCII diagram to *header → main-split → market-share*. Note the scope cut in a new Phase 7 subsection for traceability.

#### 7.3 Acceptance for Phase 7

- [ ] `<canvas id="timeline-chart">` is no longer present in the rendered DOM.
- [ ] No CSS rules reference `.chart-section`, `.metric-toggles`, or `.chart-wrap`.
- [ ] Browser console shows no `ReferenceError` or `TypeError` on page load, scenario switch, layout drag, or `Reset layout` click.
- [ ] Dragging the remaining two handles (flowchart ↔ detail, main-split ↔ market) resizes cleanly; `Reset layout` still restores defaults.
- [ ] The Market Share Comparison chart still shows the 2025 / 2028 / 2032 vertical turning-point markers (confirms `turningLinePlugin` survived the cut).
- [ ] `python3 -m tests.run_verification` → 29/29 pass (no UI tests exist today, but the backend suite must stay green).

### Phase 8: Improvements

Goal: Make the data about of OTA more realistic and add a function of expanding the scenario line when the user inputs a question for the dashboard.

### Phase 9: Interactive Future Prediction (FR-5)

FR-5 adds a conversational layer so that strategy planners can interrogate scenarios in natural language and revise them without touching JSON or Python directly.

#### 9.1 API Backend (`src/api/server.py`)

Build a lightweight **FastAPI** server that acts as the bridge between the UI, the simulation engine, and the Claude API.

- **`POST /chat`** — Accepts a user message and the current `scenario_id`. Loads the matching scenario from `scenarios.json`, injects it as structured context into a Claude API call, and streams the response back via Server-Sent Events (SSE). The system prompt instructs Claude to answer strictly from the provided scenario data and flag when a question implies a revision.
- **`POST /revise`** — Accepts a natural-language revision instruction (e.g. *"increase the probability of 'Embrace NDC' to 75%"* or *"add a new turning point in 2026 for EU AI regulation"*). A Claude API call with tool use translates the instruction into a structured diff (`{node_id, field, new_value}`). The server applies the diff to `scenarios.json`, re-runs `Simulator.generate_scenarios()`, and returns the updated scenario list.
- **`GET /scenarios`** — Serves `data/scenarios.json` so the UI can fetch live data without a file-system dependency.

Authentication: a single bearer token configured via environment variable (`ROADMAP_API_KEY`) is sufficient for internal/demo use.

#### 9.2 Claude API Integration

- Use **`claude-sonnet-4-6`** for chat (latency-sensitive) and **`claude-opus-4-7`** for revision translation (accuracy-sensitive, less frequent).
- Enable **prompt caching** on the scenario context block, which is large and static between messages in the same session — this avoids re-tokenising the full JSON on every turn.
- For `/revise`, expose a `apply_scenario_diff` tool so Claude returns a machine-readable patch rather than prose, keeping the revision path deterministic and auditable.

#### 9.3 UI Chat Panel

Extend `src/ui/index.html` with a collapsible chat panel docked to the right side of the flowchart pane.

- **Input bar** — a textarea with a send button; supports `Enter` to submit, `Shift+Enter` for newline.
- **Message thread** — alternating user/assistant bubbles; assistant responses stream in token by token via the SSE connection.
- **Revision confirmation card** — when the backend detects a revision intent, the response includes a structured summary of the proposed change (field, old value, new value). The user confirms or cancels; on confirmation the UI calls `/revise`, then re-renders the Mermaid diagram and chart from the updated scenario data.
- **Context indicator** — a badge showing which scenario is active in the chat session, updated when the user switches the scenario selector dropdown.

## 4. Key Milestones

1. **M1: Data Layer**: `scenarios.json` schema finalized.
2. **M2: Simulation Alpha**: Engine produces logically valid JSON branches.
3. **M3: UI Prototype**: Mermaid diagram renders in the browser.
4. **M4: Dashboard Complete**: Integrated dashboard ready for strategic planning.
5. **M5: Interactive Prediction**: `/chat` endpoint live; users can ask questions and receive scenario-grounded answers via streaming.
6. **M6: Scenario Revision**: `/revise` endpoint live; natural-language edits round-trip through the engine and update the diagram without a page reload.
7. **M7: Market Share Comparison**: Multi-OTA market-share view live; scenario-linked Chart.js panel shows Expedia / Booking / Trip.com / Agoda / Kiwi / eDreams trajectories side by side with toggleable series and a delta-vs-baseline summary table.
8. **M8: Dashboard Polish**: Flowchart nodes carry revenue / share / tech-adoption chips plus stance glyphs at a glance (FR-4 update), and every main UI division is user-resizable with persistence and a reset-to-default control (new acceptance criterion).
9. **M9: Scope Cut — Metrics Timeline Removed**: The Metrics Timeline UI division is deleted per the user-story *Not-Todos*. The dashboard now renders header + flowchart/detail split + market-share panel only, with two resize handles instead of three; the `turningLinePlugin` is retained so the market-share chart keeps its turning-point markers.
