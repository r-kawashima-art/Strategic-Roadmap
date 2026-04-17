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

## 4. Key Milestones

1. **M1: Data Layer**: `scenarios.json` schema finalized.
2. **M2: Simulation Alpha**: Engine produces logically valid JSON branches.
3. **M3: UI Prototype**: Mermaid diagram renders in the browser.
4. **M4: Final Delivery**: Integrated dashboard ready for strategic planning.

## 5. Risk Management

| Risk | Mitigation Strategy |
|---|---|
| Strategy logic is too simple | Incorporate more features from PESTEL/Porter's frameworks into the simulation engine. |
| Hard to maintain Mermaid syntax | Use an abstraction layer (e.g., a Python helper) to generate Mermaid code from JSON. |
| Missing OTA current data | Use the target company profiles (Kiwi, eDreams) as baseline templates. |
