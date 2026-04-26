# Strategic Roadmap: OTA Future Scenario Visualizer

## 1. User Story

**As a** Strategy Planner at an Online Traveling Agency,
**I want to** visualize divergent future scenarios based on AI adoption and market dynamics with interactive conversation with the Scenario system,
**So that** I can identify "Turning Points" where specific decisions lead to corporate success or failure.

## 2. Context & Objectives

The travel industry is facing massive disruption via AI (Generative AI, NDC, and personalized agents). This tool must model the strategic trajectories of leading OTAs such as **Kiwi.com**, **Etraveli Group**, and **eDreams Odigeo**, focusing on their financial resilience and technological adaptation.

## 3. Functional Requirements

- **FR-1: Scenario Divergence Engine**: Generate at least 4 distinct scenarios (e.g., Status Quo, AI-Dominant, Direct-Booking-Dominant, Disintermediated).
- **FR-2: Turning Point Logic**: Identify specific decision nodes (e.g., "Implement NDC Standard By 2025" or "Launch AI Concierge") and their impact on market share.
- **FR-3: Flowchart Visualization**: Render the roadmap as an interactive scenario-line-flowchart (Mermaid or D3.js). The flowchart should be scrollable both horizontally and vertically, and magnifiable to zoom in and out.
- **FR-4: Financial and Technological Linkage**: Correlate scenarios with key metrics (Revenue Growth, Market Share, and Technology Adoption and Strategic Positioning) on **Flowchart nodes**.
- **FR-5: Interactive Future Prediction**: Allow users to ask questions about the future scenarios and get answers based on the data and revise the scenarios based on user inputs.
- **FR-6: Comparison of the share of OTAs**: Display the top market shares of OTAs (Expedia, Booking.com, Trip.com, Agoda, Kiwi.com, eDreams Odigeo, etc.) and allow users to compare the market share of the OTAs in the scenarios.
- **FR-7: Scenario Management**: Allow users to create, edit, and delete scenarios. Allow users to save and load scenarios.

## 4. Technical Constraints

- **Analysis Frameworks**: Must utilize PESTEL and Porter's Five Forces.
- **Scalability**: The system should allow adding new OTA competitors as data becomes available.

## 5. Acceptance Criteria

Todos:

- [ ] Clear visualization of at least two branching paths starting from 1990 to 2040.
- [ ] Each branch must have labeled "Turning Points" explaining the *why* of the divergence.
- [ ] Scenario data is separable from the UI logic (Model/View separation).
- [ ] The layout of the UI should be flexible, and the size of each main UI division (e.g., scenario visualization, market share comparison, etc.) should be **adjustable** by the user.

Not Todos:

- [ ] Do NOT make a UI division of **Metrics Timeline**.
