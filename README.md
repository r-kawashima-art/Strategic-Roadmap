# Strategic Roadmap OTA Visualizer

**Strategic Roadmap** is a programmable simulation and visualization system designed for decision-makers in the Online Travel Agency (OTA) industry. It models the impact of AI disruption, NDC (New Distribution Capability) adoption, and airline direct-booking trends, projecting industry evolution from 1990 to 2040.

---

## 🌟 Key Features

- **Strategic Simulation Engine**: A "Fit Engine" that calculates how different OTA archetypes (Cost Leader, Differentiator, Niche Search) respond to external market shocks.
- **2x2+S Matrix Logic**: Evolution of competitor positioning along three axes: Airline Direct Booking Dominance, AI Agent Adoption, and Strategic Orientation (Innovation-led vs. Efficiency-led).
- **Interactive Dashboard**: A high-fidelity visualization tool using [Mermaid.js](https://mermaid.js.org/) for decision trees and [Chart.js](https://www.chartjs.org/) for multi-metric timeline analysis.
- **Scenario Generation**: Automated generation of multiple strategic paths (18+ variants) ranked by composite probability and impact scores.
- **Historical Backtesting**: Validation of simulation logic against historical data (1990–2025) to ensure realistic projections.

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.9+** (No external dependencies required for the core engine)
- **Modern Web Browser** (Chrome, Edge, or Firefox)

### 1. Generate Scenarios

First, run the simulation engine to generate the scenario data:

```bash
cd src/engine
python simulator.py
```

This will update `data/scenarios.json` and generate all path variants in `data/scenarios_generated.json`.

### 2. Launch the Dashboard

From the project root, start a local development server to enable full feature support (live data fetching):

```bash
# From project root
python -m http.server 8080
```

Open your browser and navigate to:
**[http://localhost:8080/src/ui/index.html](http://localhost:8080/src/ui/index.html)**

> [!NOTE]
> You can also open `src/ui/index.html` directly in your browser. However, it will use embedded fallback data as browser security (CORS) prevents fetching local JSON files directly.

---

## 🏗️ Architecture

The system is built on a clean, layered architecture:

| Layer | Component | Description |
| :--- | :--- | :--- |
| **Data** | `data/scenarios.json` | The source of truth containing historical metrics, turning points, and branch outcomes. |
| **Engine** | `src/engine/` | Python-based logic including `FitEngine` (strategic fit) and `MatrixEngine` (positioning evolution). |
| **UI** | `src/ui/index.html` | A self-contained interactive dashboard using Mermaid.js and Chart.js. |

---

## 📂 Project Structure

```text
Strategic-Roadmap/
├── data/                 # Generated scenario JSON files
├── docs/                 # Detailed walkthroughs and progress logs
├── reference/            # Industry research (Porter's Five Forces, PESTEL)
├── specs/                # Requirements and implementation plans
└── src/
    ├── engine/           # Simulation engine (Python)
    │   ├── schema.py     # Data models and serialization
    │   └── simulator.py  # Simulation & scenario generation logic
    └── ui/               # Dashboard (HTML/CSS/JS)
```
