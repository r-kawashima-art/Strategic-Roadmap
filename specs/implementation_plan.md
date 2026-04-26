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

- Create a frontend using **Mermaid.js** script to render the `scenarios.json` as a flow/roadmap.
- Implementation of "Hover effects" to show details of "Turning Points".

### Phase 4: Verification & Feedback

- Conduct "War-gaming" tests to ensure scenario paths are logically consistent with industry trends (NDC, GenAI).
- User review of the "Turning Points" clarity.
- The data of OTA should be realistic and based on real data (e.g. market share, revenue, tech adoption rate).

### Phase 5: Interactive Future Prediction (FR-5)

FR-5 adds a conversational layer so that strategy planners can interrogate scenarios in natural language and revise them without touching JSON or Python directly.

#### 5.1 API Backend (`src/api/server.py`)

Build a lightweight **FastAPI** server that acts as the bridge between the UI, the simulation engine, and the Claude API.

- **`POST /chat`** — Accepts a user message and the current `scenario_id`. Loads the matching scenario from `scenarios.json`, injects it as structured context into a Claude API call, and streams the response back via Server-Sent Events (SSE). The system prompt instructs Claude to answer strictly from the provided scenario data and flag when a question implies a revision.
- **`POST /revise`** — Accepts a natural-language revision instruction (e.g. *"increase the probability of 'Embrace NDC' to 75%"* or *"add a new turning point in 2026 for EU AI regulation"*). A Claude API call with tool use translates the instruction into a structured diff (`{node_id, field, new_value}`). The server applies the diff to `scenarios.json`, re-runs `Simulator.generate_scenarios()`, and returns the updated scenario list.
- **`GET /scenarios`** — Serves `data/scenarios.json` so the UI can fetch live data without a file-system dependency.

Authentication: a single bearer token configured via environment variable (`ROADMAP_API_KEY`) is sufficient for internal/demo use.

#### 5.2 Claude API Integration

- Use **`claude-sonnet-4-6`** for chat (latency-sensitive) and **`claude-opus-4-7`** for revision translation (accuracy-sensitive, less frequent).
- Enable **prompt caching** on the scenario context block, which is large and static between messages in the same session — this avoids re-tokenising the full JSON on every turn.
- For `/revise`, expose a `apply_scenario_diff` tool so Claude returns a machine-readable patch rather than prose, keeping the revision path deterministic and auditable.

#### 5.3 UI Chat Panel

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

## 5. Risk Management

| Risk | Mitigation Strategy |
|---|---|
| Strategy logic is too simple | Incorporate more features from PESTEL/Porter's frameworks into the simulation engine. |
| Hard to maintain Mermaid syntax | Use an abstraction layer (e.g., a Python helper) to generate Mermaid code from JSON. |
| Missing OTA current data | Use the target company profiles (Kiwi, eDreams) as baseline templates. |
| LLM produces an invalid scenario revision | The `/revise` endpoint uses Claude tool use (`apply_scenario_diff`) to return a structured patch; the server validates the patch against the schema before writing it. Invalid patches are rejected and the error is surfaced in the chat UI. |
| Prompt injection via user chat input | The system prompt instructs Claude to treat user messages as questions about the data only. The `/revise` path uses tool use exclusively — Claude never writes raw JSON; the server applies and validates the diff. |
| Scenario context too large for efficient chat | Enable Anthropic prompt caching on the scenario context block. Because the scenario JSON is static within a session, cache hit rate will be high, reducing both latency and cost. |
| API key exposure in the browser | The Claude API key is held server-side only (`ROADMAP_API_KEY` env var). The browser communicates with `src/api/server.py` only, never with the Anthropic API directly. |
