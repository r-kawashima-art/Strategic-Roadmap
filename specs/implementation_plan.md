# Implementation Plan: Strategic Roadmap OTA Visualizer

## 1. Objective

Develop a "programmable" system that simulates and visualizes future strategic scenarios for the Online Travel Agency (OTA) industry, focusing on AI disruption and corporate decision-making.

## 2. Directory Structure

```text
Strategic-Roadmap/
├── data/
│   └── scenarios.json         # {base: [...], user: [...]} scenario arrays
├── src/
│   ├── engine/
│   │   ├── schema.py          # Pydantic models: Scenario, Node, CompetitorProfile…
│   │   └── simulator.py       # 2x2+S Fit Engine; project_market_shares()
│   ├── api/
│   │   └── server.py          # FastAPI: /chat (SSE), /revise, /scenarios CRUD
│   └── ui/
│       └── index.html         # Single-file SPA; served as static by FastAPI
├── tests/
│   ├── test_turning_points.py
│   └── test_wargame.py
├── specs/
│   ├── user_story.md          # Functional requirements
│   ├── implementation_plan.md # This document
│   └── design.md              # Architecture, data flow, LLM integration, GCP infra
├── docs/
│   └── walkthrough.md
├── Dockerfile                 # Cloud Run container image (Phase 11)
├── cloudbuild.yaml            # Cloud Build CI/CD pipeline (Phase 11)
└── .env.example               # Local dev env vars template
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
- The data of OTA should be realistic and based on real data (e.g. market share, revenue, tech adoption rate).

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
- **`POST /revise`** — Accepts a natural-language revision instruction (e.g. *"increase the probability of 'Embrace NDC' to 75%"* or *"add a new turning point in 2026 for EU AI regulation"*). A Claude API call with tool use translates the instruction into a structured diff (`{node_id, field, new_value}`). The server returns the **preview** of the revised scenario object **without persisting it** — persistence is a separate explicit user action via `POST /scenarios`. This separates the revision preview from the save decision so base scenarios are never silently overwritten.
- **`GET /scenarios`** — Lists all scenarios from `data/scenarios.json`, including user-saved variants alongside base scenarios. Each entry carries a `source` field (`"base"` or `"user"`) and an optional `parent_id` linking a saved variant back to its origin scenario.
- **`POST /scenarios`** — Saves a scenario (either a new one from scratch or a revision diff applied to a parent). Accepts `{name, parent_id?, scenario_data}`. Writes to `data/scenarios.json` as a new named entry with `source: "user"`. Rejects names that collide with base scenario names.
- **`PUT /scenarios/{id}`** — Renames or updates the metadata (`name`, `description`) of a user-created scenario. Returns `403` for base scenarios.
- **`DELETE /scenarios/{id}`** — Removes a user-created scenario from `data/scenarios.json`. Returns `403` for base scenarios to prevent accidental data loss.

Authentication: in local development a bearer token (`ROADMAP_API_KEY` env var) is sufficient. In production on Google Cloud, Cloud IAP replaces this — the token path is disabled unless `IAP_DISABLED=true` is explicitly set. See Phase 11 for the full auth design.

#### 9.2 Claude API Integration

- Use **`claude-sonnet-4-6`** for chat (latency-sensitive) and **`claude-opus-4-7`** for revision translation (accuracy-sensitive, less frequent).
- Enable **prompt caching** on the scenario context block, which is large and static between messages in the same session — this avoids re-tokenising the full JSON on every turn.
- For `/revise`, expose a `apply_scenario_diff` tool so Claude returns a machine-readable patch rather than prose, keeping the revision path deterministic and auditable.

#### 9.3 UI Chat Panel

Extend `src/ui/index.html` with a collapsible chat panel docked to the right side of the flowchart pane.

- **Input bar** — a textarea with a send button; supports `Enter` to submit, `Shift+Enter` for newline.
- **Message thread** — alternating user/assistant bubbles; assistant responses stream in token by token via the SSE connection.
- **Revision confirmation card** — when the backend detects a revision intent, the response includes a structured summary of the proposed change (field, old value, new value). The user confirms or cancels; on confirmation the UI calls `/revise`, which returns a **preview** of the revised scenario. The preview renders live in the flowchart and market-share chart so the planner can evaluate the change before committing. A **"Save as New Scenario"** button and name input field appear below the confirmation card — submitting calls `POST /scenarios` and adds the saved variant to the scenario selector dropdown. Cancelling discards the preview and restores the previous state.
- **Context indicator** — a badge showing which scenario is active in the chat session, updated when the user switches the scenario selector dropdown. Base scenarios display a lock icon; user-saved variants display a bookmark icon so the planner can distinguish seeded data from personal edits at a glance.

#### 9.4 Revision Connectivity and Visual Diff (Flowchart Integration)

Two gaps exist in the current `/revise` preview flow that make it hard for planners to evaluate proposed changes:

1. **Disconnected nodes** — when Claude returns an `add_node` operation, `scenario_patch.py` appends the new `TurningPointNode` to the scenario's `nodes` list but leaves all existing terminal branches pointing to `null`. The Mermaid renderer therefore draws the new node as a floating island with no incoming arrows, breaking the DAG and making the change unreadable.
2. **No visual diff** — the preview flowchart renders with the same styling as a normal scenario, so the planner cannot tell at a glance which nodes were modified, added, or had their branch probabilities changed by the revision.

##### 9.4.1 Auto-rewire on `add_node` (`src/api/scenario_patch.py`)

Extend the `apply_diff` handler for the `add_node` operation to replicate the rewiring logic already used by `expand_scenario`:

- After appending the new node to `scenario["nodes"]`, collect every branch across all existing nodes whose `next_node_id` is `null` (currently terminal).
- Set each terminal branch's `next_node_id` to the new node's `id`.
- If the `add_node` operation includes an explicit `rewire_from` list of `{node_id, branch_id}` pairs (optional field added to the `apply_scenario_diff` tool schema), honour that list instead of the auto-detect logic. This allows Claude to target specific branches rather than all terminals when the graph already has multiple endpoint paths.

##### 9.4.2 Visual Diff Overlay (`src/ui/index.html`)

When `renderRevisionCard` calls `renderFlowchart(previewScenario, ...)`, pass a second `diffContext` argument containing the sets of changed, added, and unchanged node IDs:

- **Changed nodes** (field values modified by `set_node_field` or `set_branch_field` operations) — render with an amber `stroke` on their Mermaid class definition instead of the default purple, so they stand out from unchanged turning points.
- **New nodes** (created by `add_node`) — render with a dashed amber border and a `✦` prefix on the label to signal that they did not exist in the base scenario.
- **Unchanged nodes** — render at reduced opacity (use Mermaid `classDef` with a lighter `color` value) so the planner's eye goes directly to what changed.
- Diff styling is applied only during an active preview; `clearPreview()` restores the standard class definitions on discard or save.

`buildDef(scenario, diffContext)` derives the diff context by comparing `previewScenario.nodes` against `previewSnapshot.nodes` at the time `renderRevisionCard` is called. No server change is needed — the comparison is purely client-side.

##### 9.4.3 Tool Schema Update

Add an optional `rewire_from` field to the `add_node` operation object in `APPLY_SCENARIO_DIFF_TOOL.input_schema`:

```json
"rewire_from": {
  "type": "array",
  "description": "Specific terminal branches to rewire into the new node. Omit to auto-rewire all terminal branches.",
  "items": {
    "type": "object",
    "properties": {
      "node_id":   { "type": "string" },
      "branch_id": { "type": "string" }
    },
    "required": ["node_id", "branch_id"]
  }
}
```

Update `REVISE_SYSTEM_PREAMBLE` to instruct Claude that `rewire_from` should be used when the scenario has multiple terminal paths that serve different story lines and only one should flow into the new node.

##### 9.4.4 Acceptance Criteria for Phase 9.4

- [ ] An `add_node` revision always produces a fully connected DAG — the new node has at least one incoming arrow from a previously-terminal branch.
- [ ] When `rewire_from` is specified by Claude, only the listed branches are rewired; other terminal branches remain terminal.
- [ ] During a live preview, nodes modified by the diff render in amber; new nodes render with a dashed border and `✦` prefix; unchanged nodes render at reduced opacity.
- [ ] Discarding the preview fully restores the original node styling — no amber or dashed borders remain.
- [ ] Saving the preview as a new scenario persists the standard (non-diff) styling in the selector and subsequent loads.

#### 9.5 Revision of Phase 9.4 — Divergent Branch Creation

Phase 9.4 closed the floating-island bug by auto-rewiring terminal branches into a newly-added node. That covers **continuation** — the new node extends the storyline past its current last endpoint. Real strategy questions, however, are usually divergent: *"what if, in 2028, eDreams had cancelled Prime instead of doubling down?"* The expected answer is a NEW path that sprouts off a **past, mid-graph turning point**, runs in parallel with the original storyline, and reaches its own 2040 outcomes — without overwriting the existing edges.

Phase 9.5 adds that second topology while keeping 9.4's continuation behaviour intact, and codifies a single connectivity invariant that both modes must satisfy.

##### 9.5.1 Connectivity Invariant

> Every node introduced via `/revise` MUST have at least one incoming edge from a node that already existed before the revision. The new node's outgoing branches MAY remain terminal — divergent storylines are not required to merge back into existing 2040 outcomes.

This invariant supersedes the looser 9.4.4 wording ("incoming arrow from a previously-terminal branch"): the incoming edge can now also come from a *new branch sprouted onto a past node*. Both 9.4 (continuation) and 9.5 (divergence) are special cases of this single rule.

##### 9.5.2 Two Wiring Modes on `add_node`

Extend `add_node` so the LLM picks the mode matching the user's intent:

| Mode | Field | Effect |
| --- | --- | --- |
| **Continuation** (9.4) | `rewire_from` (existing) | Redirects previously-terminal branches' `next_node_id` to the new node. The new node becomes the new tail. |
| **Continuation auto** (9.4) | *neither field set* | Auto-rewires every terminal branch. Convenient default when the scenario has a single tail. |
| **Divergence** (9.5, new) | `fork_from` (new) | ADDS a new branch onto each listed past node, pointing at the new node. Existing branches on those past nodes are preserved untouched. |

The two fields can co-exist (rare; see §9.5.4). The system preamble (§9.5.6) trains Claude to pick exactly one based on the user's phrasing.

##### 9.5.3 `fork_from` Field Shape

```json
"fork_from": [
  {
    "from_node_id": "tp-002",
    "branch": {
      "id": "tp-002-d",
      "label": "Cancel Prime, fund eDreams Lab",
      "description": "Counterfactual: redirect Prime budget into a GenAI R&D arm.",
      "probability": 0.15,
      "metric_delta": {
        "revenue_index": -0.05,
        "market_share": 0.00,
        "tech_adoption_velocity": 0.10
      }
    }
  }
]
```

Each entry describes a brand-new branch to be appended to `from_node_id.branches`, with `next_node_id` set automatically by the server to the new node's `id`. The branch object reuses the same shape `add_branch` already validates — no new field schema to learn.

##### 9.5.4 Server Implementation (`src/api/scenario_patch.py::_add_node`)

Extend `_add_node` after the existing `rewire_from` block, before the final mutation step:

1. Read `fork_from = diff.get("fork_from") or []`. Validate it is a list of objects.
2. For each entry:
    - Resolve `from_node_id` via `_find_node` (raise `DiffError` on unknown).
    - Validate `branch` carries the same required fields enforced by `_add_branch` (`id`, `label`, `description`, `metric_delta`, `probability`).
    - Reject if `branch.id` collides with any existing branch id on the target node (`DiffError`).
    - Stamp `branch["next_node_id"] = node["id"]` server-side. The LLM does NOT supply `next_node_id` — the preamble forbids it, and the server is the single source of truth for that edge.
3. **Buffer the planned mutations** (`fork_targets: List[Tuple[node_dict, branch_dict]]`) — do not append to any node yet. This keeps the operation atomic: if the connectivity check in step 5 fails, no partial state is written.
4. Compute the `rewire_targets` list as today (terminal branches when `rewire_from` is omitted; the validated subset when it is supplied).
5. **Connectivity check (the new invariant guard)** — count the post-mutation in-degree of the new node:

    ```python
    incoming = len(rewire_targets) + len(fork_targets)
    if incoming == 0:
        raise DiffError(
            f"add_node {node['id']!r} would leave the new node unreachable. "
            "Either supply `rewire_from` (continuation), `fork_from` (divergence), "
            "or ensure the scenario has at least one terminal branch for "
            "auto-rewire to use."
        )
    ```

6. Apply mutations atomically: append the new node, apply `rewire_targets[*].next_node_id = node["id"]`, then for each `(host_node, new_branch)` in `fork_targets` do `host_node["branches"].append(new_branch)`.

The behaviour for an `add_node` op carrying both `rewire_from` and `fork_from` is: apply both. Used when a divergent line is also designated as the new tail of the original storyline (uncommon; the preamble discourages it but the implementation should not reject it).

##### 9.5.5 Tool Schema Update (`src/api/server.py`)

Add `fork_from` alongside `rewire_from` in `APPLY_SCENARIO_DIFF_TOOL.input_schema.properties.operations.items.properties`:

```json
"fork_from": {
  "type": "array",
  "description": "Past nodes that should sprout a NEW branch pointing at the new node, modelling a divergent storyline. Existing branches on those nodes are preserved. Only valid for `add_node`.",
  "items": {
    "type": "object",
    "properties": {
      "from_node_id": { "type": "string" },
      "branch": {
        "type": "object",
        "description": "Full new branch object — same shape as the `branch` field on `add_branch` (id, label, description, probability, metric_delta). Do NOT include next_node_id; the server sets it."
      }
    },
    "required": ["from_node_id", "branch"]
  }
}
```

##### 9.5.6 System Preamble Update (`REVISE_SYSTEM_PREAMBLE`)

Append guidance that lets Claude pick the right mode from natural-language cues:

- *"When the user describes a turning point that EXTENDS the storyline past its current end ('and after that…', 'in 2038…', 'next decision…'), leave `fork_from` empty. Either omit `rewire_from` for auto-rewire, or list specific terminal branches in `rewire_from`."*
- *"When the user describes an ALTERNATIVE or DIVERGENT past decision — signalled by phrases like 'what if instead', 'imagine that in 2028…', 'fork from', 'diverge', 'counterfactual', or any 'instead of X, do Y' framing — use `fork_from` to attach the new node to the relevant past turning point(s). The existing branches at those nodes stay intact, so the original storyline remains explorable alongside the divergent one. Pick a `probability` that reflects the user's framing (e.g. 'a small chance' ≈ 0.10–0.20; do NOT rebalance the existing branches — the simulator normalises at run time)."*
- *"Never set `next_node_id` on a `fork_from.branch` — the server sets it for you. Setting it manually will be rejected as out-of-scope."*

##### 9.5.7 Test Coverage (`tests/test_wargame.py`)

Add `test_every_node_is_reachable` that asserts the connectivity invariant on every scenario the simulator emits AND every patched preview:

- Build the directed edge set from `nodes[*].branches[*].next_node_id` plus the implicit historical-chain edges that `buildDef` synthesises.
- For each turning-point node, assert `in_degree(node) >= 1`.
- Then exercise three `apply_diff` cases against `fresh_scenario()`:
  1. `add_node` with no `rewire_from`/`fork_from` → invariant holds via auto-rewire.
  2. `add_node` with `fork_from = [{from_node_id: "tp-002", branch: {...}}]` → invariant holds AND `tp-002`'s original branches are unchanged in count and content.
  3. `add_node` against a synthetic scenario with zero terminal branches and no `fork_from` → expects `DiffError`.

##### 9.5.8 UI Implications (No New Client Code)

The visual-diff overlay shipped in 9.4.2 already covers the divergence topology for free:

- The new node renders dashed amber + `✦` prefix (it is in `addedNodeIds`).
- The freshly-sprouted branch on the past node renders amber (its branch id is in `changedBranchIds` because it did not exist in `previewSnapshot`).
- The past node's original branches stay faded but visible — the planner sees both the original storyline and the divergent fork side-by-side.

The only documentation work is a short paragraph in `docs/walkthrough.md` (Phase 9 section) explaining "continuation vs. divergence" so non-engineer reviewers can read the flowchart correctly.

##### 9.5.9 Acceptance Criteria for Phase 9.5

- [ ] `add_node` with `fork_from` produces a graph in which every listed past node retains its original branches AND gains exactly one new branch pointing at the new node, with `next_node_id` set by the server.
- [ ] `add_node` with neither `rewire_from` nor `fork_from` still auto-rewires terminal branches (9.4.1 behaviour preserved — no regression).
- [ ] `add_node` that would leave the new node unreachable (zero rewire targets AND zero fork targets) raises `DiffError` with the new-message wording from §9.5.4 step 5.
- [ ] `test_every_node_is_reachable` passes on every base scenario and on all three `apply_diff` cases listed in §9.5.7.
- [ ] A `/revise` call seeded with *"what if instead, in 2028, eDreams had cancelled Prime?"* returns a tool call whose `add_node` operation uses `fork_from` (not `rewire_from`), and the resulting preview shows the past node with both its original branches and the new amber fork.
- [ ] Saving the preview as a new scenario persists both the new node AND the new fork branches; subsequent loads render the divergent topology correctly without diff styling.

### Phase 10: Scenario and Data Management (FR-7)

FR-7 delivers full lifecycle control over scenarios — create, rename, delete, export, and import — so that AI-generated variants and custom planners' edits become persistent, shareable artefacts rather than ephemeral session state.

#### 10.1 Data Layer

- `data/scenarios.json` is restructured into two top-level arrays: `base` (read-only seed scenarios) and `user` (mutable, user-created or AI-generated variants). The simulator always loads both; `GET /scenarios` merges them into a flat list tagged by `source`.
- Each user scenario carries: `id` (UUID), `name`, `description`, `parent_id` (optional), `created_at`, `updated_at`, `source: "user"`.
- **Export**: `GET /scenarios/{id}/export` returns the scenario object as a downloadable `{name}.scenario.json` file. The export format is self-contained — it includes the full `nodes`, `timeline`, and `metrics` so it can be re-imported on any instance.
- **Import**: `POST /scenarios/import` accepts a multipart upload of a `.scenario.json` file. The server validates the schema, assigns a fresh `id`, and saves it to the `user` array. Duplicate-name conflicts surface as a `409` with a suggested rename.

#### 10.2 UI: Scenario Manager

Add a **Scenario Manager** accessible from a gear icon next to the scenario selector dropdown. It opens as a slide-over panel (not a full modal) to keep the flowchart visible for context.

- **Library list** — rows for every user scenario showing name, parent scenario, created date, and three-dot menu (Rename, Export, Delete). Base scenarios appear at the top as read-only reference rows with an export-only menu.
- **Rename inline** — clicking a name in the list makes it an editable input; `Enter` commits, `Esc` cancels. Calls `PUT /scenarios/{id}`.
- **Delete with confirmation** — the three-dot menu delete action shows a one-line inline confirmation ("Delete «Optimistic NDC»? This cannot be undone.") before calling `DELETE /scenarios/{id}`.
- **Import button** — opens the native file picker filtered to `.scenario.json`; calls `POST /scenarios/import` and refreshes the list on success.
- **New blank scenario** — a "＋ New Scenario" button at the top of the list opens a name-input popover and seeds an empty scenario from the base "Status Quo" template. Calls `POST /scenarios`.

#### 10.3 Scenario Selector Update

The existing scenario selector dropdown gains two visual cues without a layout change:

- A **bookmark icon** prefix on user-saved variants (mirrors the chat-panel context indicator from Phase 9.3).
- An **"Unsaved changes" dot** while a `/revise` preview is active but not yet saved — a reminder to either save or discard.

#### 10.4 Non-Destructive Edit Semantics (FR-7 update)

User-story addition (§FR-7): *"You should update the data of visualizing graph, without deleting the original data."*

Every edit path — natural-language `/revise` (Phase 9.3) and direct manipulation via the Scenario Manager (§10.2) — produces a NEW scenario entry linked to its source via `parent_id`. The source row in `data/scenarios.json` is never mutated by an edit. This applies symmetrically to base **and** user scenarios:

- **Base scenarios** — already protected by the HTTP 403 returned from `PUT /scenarios/{id}` and `DELETE /scenarios/{id}` (Phase 9.1). The `/revise` → Save-as-New flow (Phase 9.3) is the only mutation path, and it always emits a new `source: "user"` entry whose `parent_id` points at the base scenario.
- **User scenarios** — `PUT /scenarios/{id}` is restricted to **metadata only** (`name`, `description`); it does not accept `nodes`, `timeline`, `metrics`, or any field that affects the visualizing graph. Payloads carrying graph keys are rejected with HTTP 400. Graph-level edits route through `POST /scenarios` with the user-scenario `id` as `parent_id`, producing a new variant alongside the original. This keeps the version chain auditable and lets the planner roll back by selecting the parent.
- **Preview lifecycle** — the Phase 9.5 preview/discard semantics already enforce the same invariant in-flight: a `/revise` preview lives only in client memory until the planner clicks **Save as New**; **Discard preview** restores the snapshot without ever calling a mutating endpoint, so an aborted edit cannot reach `data/scenarios.json`.

Version chain in the UI:

- The **Scenario Manager** library list (§10.2) renders each row's `parent_id` as a focus link; clicking it scrolls to and highlights the parent row, letting the planner walk the chain back to its base ancestor.
- The scenario selector dropdown (§10.3) indents variants under their parent so a forked tree of edits is visually obvious without opening the Manager.
- Deleting a user scenario (`DELETE /scenarios/{id}`) does NOT cascade to its children — orphaned variants keep their `parent_id` pointing at a now-missing record. The Manager surfaces this as a faded "(deleted parent)" annotation rather than purging the children, so the planner's edit history survives a single bad delete.

#### 10.5 Acceptance Criteria for Phase 10

- [ ] User-created scenarios persist across browser reloads and server restarts (backed by `data/scenarios.json`).
- [ ] Base scenarios cannot be renamed, edited metadata of, or deleted via the API (HTTP 403 enforced).
- [ ] **Editing any existing scenario produces a new entry whose `parent_id` points to the source; the source row in `data/scenarios.json` is never mutated.** Verified for both base scenarios (via `/revise` → Save as New) and user scenarios (via Scenario Manager edits and `/revise`).
- [ ] `PUT /scenarios/{id}` rejects payloads containing `nodes`, `timeline`, or `metrics` keys with HTTP 400 — metadata-only edits are the sole in-place mutation path for user scenarios.
- [ ] A scenario exported from one session and imported into another round-trips without data loss — the imported scenario renders identically in the flowchart and market-share chart.
- [ ] Renaming a scenario updates the selector dropdown in real time without a page reload.
- [ ] Deleting a scenario that is currently active in the chat session gracefully falls back to the first base scenario and shows a dismissible toast notification.
- [ ] Deleting a user scenario that has children leaves the children intact; the Manager flags them as "(deleted parent)" without auto-purging.
- [ ] The Scenario Manager panel is reachable via keyboard navigation and its controls carry `aria-label` attributes.

### Phase 11: Google Cloud Deployment (Internal Access)

Deploy the application to Google Cloud Platform so that any user authenticated via the company's Google Workspace account can reach it without managing credentials. This phase is infrastructure-only — no feature code changes.

#### 11.1 Containerization

Create `Dockerfile` at the project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY data/ data/

ENV PORT=8080
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8080"]
```

Production additions to `requirements.txt`:

```text
fastapi
uvicorn[standard]
anthropic
google-cloud-storage
google-auth
```

FastAPI serves `src/ui/index.html` as a static asset at `GET /`, so no separate static hosting is needed.

#### 11.2 Scenario Data on Cloud Storage

`data/scenarios.json` moves to a Cloud Storage bucket (`gs://ota-roadmap-data`) so it persists across Cloud Run container restarts. The API server reads and writes via the `google-cloud-storage` Python client. When `GCS_BUCKET` env var is unset (local dev), it falls back to the on-disk file — no code-path branching required beyond an env check at startup.

#### 11.3 Secret Management

The `ANTHROPIC_API_KEY` is stored in Secret Manager and injected into Cloud Run at deploy time via `--set-secrets`. It is never written to `cloudbuild.yaml` or any config file checked into source control.

#### 11.4 Identity-Aware Proxy (Internal Auth)

Cloud IAP fronts the Cloud Run service and validates the user's Google Workspace identity. Access is granted to the company domain (`domain:yourcompany.com`) via `roles/iap.httpsResourceAccessor`. No custom login page or token issuance is needed — employees authenticate with their existing Google account.

The `ROADMAP_API_KEY` bearer-token path in `server.py` is disabled in production: the server checks for `IAP_DISABLED=true` and only activates the token guard when that flag is set, preventing accidental auth bypass in a misconfigured deploy.

#### 11.5 CI/CD with Cloud Build

Create `cloudbuild.yaml` at the project root:

```yaml
steps:
  - name: gcr.io/cloud-builders/docker
    args: [build, -t, REGION-docker.pkg.dev/PROJECT/ota-roadmap/ota-roadmap:$COMMIT_SHA, .]

  - name: gcr.io/cloud-builders/docker
    args: [push, REGION-docker.pkg.dev/PROJECT/ota-roadmap/ota-roadmap:$COMMIT_SHA]

  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    args:
      - gcloud
      - run
      - deploy
      - ota-roadmap
      - --image=REGION-docker.pkg.dev/PROJECT/ota-roadmap/ota-roadmap:$COMMIT_SHA
      - --region=asia-northeast1
      - --no-allow-unauthenticated
      - --set-secrets=ANTHROPIC_API_KEY=anthropic-api-key:latest
      - --set-env-vars=GCS_BUCKET=ota-roadmap-data
```

`--no-allow-unauthenticated` enforces that all traffic routes through IAP; direct HTTP calls without an IAP session token return `403`.

#### 11.6 One-Time Setup

Run once per GCP project to wire up the required services (replace placeholders before running):

```bash
# Enable required APIs
gcloud services enable run.googleapis.com iap.googleapis.com \
    secretmanager.googleapis.com storage.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com

# Artifact Registry
gcloud artifacts repositories create ota-roadmap \
    --repository-format=docker --location=REGION

# Cloud Storage for scenario data
gsutil mb -l asia-northeast1 gs://ota-roadmap-data
gsutil cp data/scenarios.json gs://ota-roadmap-data/scenarios.json

# Anthropic API key in Secret Manager
echo -n "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key --data-file=-

# IAM grants for the Cloud Run service account
export SA=SA_EMAIL
gcloud storage buckets add-iam-policy-binding gs://ota-roadmap-data \
    --member="serviceAccount:$SA" --role="roles/storage.objectAdmin"
gcloud secrets add-iam-policy-binding anthropic-api-key \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"

# Enable IAP and restrict to company domain
gcloud iap web enable --resource-type=cloud-run --service=ota-roadmap
gcloud iap web add-iam-policy-binding \
    --resource-type=cloud-run --service=ota-roadmap \
    --member="domain:yourcompany.com" \
    --role="roles/iap.httpsResourceAccessor"
```

#### 11.7 Acceptance Criteria for Phase 11

- [ ] `docker build` succeeds locally and the container serves `index.html` at `http://localhost:8080`.
- [ ] `gcloud run deploy` succeeds; the Cloud Run URL redirects to Google sign-in for unauthenticated users.
- [ ] A user logged into `yourcompany.com` Google Workspace can open the app without entering a separate password or API key.
- [ ] A user outside the company domain receives `403 Forbidden`.
- [ ] `GET /scenarios`, `POST /chat`, and `POST /revise` all respond correctly from the deployed Cloud Run URL.
- [ ] Saving a user scenario via `POST /scenarios` persists in `gs://ota-roadmap-data/scenarios.json` and survives a Cloud Run instance restart.
- [ ] A new git push to `main` triggers Cloud Build, builds the image, and deploys the updated Cloud Run revision without manual steps.
- [ ] The `ANTHROPIC_API_KEY` is not present in any file committed to source control; it is sourced exclusively from Secret Manager at runtime.

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
10. **M10: Scenario Management Live**: Full FR-7 lifecycle complete — user-created and AI-revised scenarios persist in `data/scenarios.json`, are reachable from the selector dropdown with base/user visual distinction, and can be exported and re-imported as self-contained `.scenario.json` files.
11. **M11: Production on Google Cloud**: App deployed to Cloud Run behind Cloud IAP; any company Google Workspace user can access it without credentials; `scenarios.json` persists on Cloud Storage; CI/CD pipeline auto-deploys on push to `main`.
