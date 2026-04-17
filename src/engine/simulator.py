"""Phase 2: Scenario Simulation Engine.

Provides:
- FitEngine:          strategic-fit scoring between competitor positioning and market forces
- MatrixEngine:       2x2+S matrix position tracking and evolution
- Simulator:          orchestrates full simulation runs, backtesting, and scenario generation
"""

from __future__ import annotations

import copy
import itertools
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from schema import (
    DATA_DIR,
    BranchOutcome,
    CompetitorProfile,
    MatrixPosition,
    MetricSnapshot,
    Scenario,
    StrategicProfile,
    StrategicStance,
    TimelineDataPoint,
    TurningPointNode,
    build_sample_scenario,
    save_scenarios,
)


# ---------------------------------------------------------------------------
# Data structures for simulation results
# ---------------------------------------------------------------------------


@dataclass
class CompetitorState:
    """Evolving state for one competitor during a simulation run."""

    name: str
    position: MatrixPosition
    profile_name: str
    metrics: MetricSnapshot
    fit_score: float = 0.0


@dataclass
class SimulationStep:
    """Snapshot after processing one turning-point node."""

    node_id: str
    year: int
    branch_chosen: str  # BranchOutcome.id
    competitor_states: List[CompetitorState]


@dataclass
class SimulationResult:
    """Complete output of a single simulation run."""

    scenario_id: str
    branch_path: List[str]  # ordered list of BranchOutcome.id chosen
    steps: List[SimulationStep]
    projected_timeline: List[TimelineDataPoint]


@dataclass
class BacktestResult:
    """Output of a historical backtest."""

    historical_cutoff: int
    mean_absolute_error: Dict[str, float]  # metric name -> MAE
    data_points_compared: int
    details: List[Dict]


# ---------------------------------------------------------------------------
# Fit Engine
# ---------------------------------------------------------------------------


class FitEngine:
    """Calculates how well a competitor's strategic positioning
    fits the current market environment defined by an external shock.

    Fit score (0-1) is higher when the competitor's profile traits
    align with the demands of the shock's external driver.
    """

    # Maps external_driver keywords to which profile traits matter most
    DRIVER_WEIGHTS: Dict[str, Dict[str, float]] = {
        "NDC adoption": {
            "direct_booking_resilience": 0.6,
            "ai_adoption_bias": 0.2,
            "stance_alignment": 0.2,
        },
        "GenAI breakthrough": {
            "ai_adoption_bias": 0.6,
            "direct_booking_resilience": 0.1,
            "stance_alignment": 0.3,
        },
        "Airline direct booking dominance": {
            "direct_booking_resilience": 0.5,
            "ai_adoption_bias": 0.3,
            "stance_alignment": 0.2,
        },
    }

    DEFAULT_WEIGHTS = {
        "direct_booking_resilience": 0.4,
        "ai_adoption_bias": 0.4,
        "stance_alignment": 0.2,
    }

    @classmethod
    def calculate_fit(
        cls,
        profile: StrategicProfile,
        position: MatrixPosition,
        external_driver: str,
    ) -> float:
        """Return a fit score in [0, 1]."""
        weights = cls.DRIVER_WEIGHTS.get(external_driver, cls.DEFAULT_WEIGHTS)

        # Stance alignment: Innovation-led scores higher for AI-heavy shocks
        if external_driver in ("GenAI breakthrough",):
            stance_score = 1.0 if profile.strategic_stance == StrategicStance.INNOVATION_LED else 0.4
        elif external_driver in ("NDC adoption",):
            # NDC favours efficiency (operational integration)
            stance_score = 1.0 if profile.strategic_stance == StrategicStance.EFFICIENCY_LED else 0.5
        else:
            stance_score = 0.5 + 0.5 * position.ai_agent_adoption

        fit = (
            weights["direct_booking_resilience"] * profile.direct_booking_resilience
            + weights["ai_adoption_bias"] * profile.ai_adoption_bias
            + weights["stance_alignment"] * stance_score
        )
        return round(min(max(fit, 0.0), 1.0), 4)

    @classmethod
    def apply_branch(
        cls,
        current_metrics: MetricSnapshot,
        branch: BranchOutcome,
        fit_score: float,
    ) -> MetricSnapshot:
        """Apply a branch's metric_delta scaled by the competitor's fit score.

        High fit amplifies positive deltas, dampens negative ones.
        Low fit dampens positive deltas, amplifies negative ones.
        """
        def scale(base: float, delta: float) -> float:
            if delta >= 0:
                return base + delta * fit_score
            else:
                # Negative deltas are worse when fit is low
                return base + delta * (2.0 - fit_score)

        return MetricSnapshot(
            revenue_index=round(scale(current_metrics.revenue_index, branch.metric_delta.revenue_index), 4),
            market_share=round(min(max(scale(current_metrics.market_share, branch.metric_delta.market_share), 0.0), 1.0), 4),
            tech_adoption_velocity=round(min(max(scale(current_metrics.tech_adoption_velocity, branch.metric_delta.tech_adoption_velocity), 0.0), 1.0), 4),
        )


# ---------------------------------------------------------------------------
# 2x2+S Matrix Engine
# ---------------------------------------------------------------------------


class MatrixEngine:
    """Tracks and evolves positions in the 2x2+S strategic matrix.

    Axis 1: Airline Direct Booking Dominance (0=low threat, 1=high threat)
    Axis 2: AI Agent Adoption (0=low, 1=high)
    Dimension 3: Strategic Orientation (Innovation-led / Efficiency-led)
    """

    DRIFT_RATE = 0.05  # Maximum position drift per turning-point step

    @classmethod
    def evolve_position(
        cls,
        position: MatrixPosition,
        profile: StrategicProfile,
        branch: BranchOutcome,
        external_driver: str,
    ) -> MatrixPosition:
        """Compute the new matrix position after a branch is taken."""

        # AI adoption axis: moves toward profile bias, accelerated by branch delta
        ai_pull = profile.ai_adoption_bias - position.ai_agent_adoption
        ai_shift = ai_pull * cls.DRIFT_RATE + branch.metric_delta.tech_adoption_velocity * 0.3
        new_ai = min(max(position.ai_agent_adoption + ai_shift, 0.0), 1.0)

        # Direct booking axis: external pressure pushes axis upward;
        # resilience determines how much the competitor absorbs
        if external_driver == "Airline direct booking dominance":
            db_pressure = 0.15
        elif external_driver == "NDC adoption":
            db_pressure = 0.08
        else:
            db_pressure = 0.03
        db_shift = db_pressure * (1.0 - profile.direct_booking_resilience)
        new_db = min(max(position.airline_direct_booking_dominance + db_shift, 0.0), 1.0)

        # Stance can flip if the branch's tech adoption delta is very high and
        # the competitor was Efficiency-led (forced innovation)
        new_stance = position.strategic_orientation
        if (
            branch.metric_delta.tech_adoption_velocity > 0.10
            and position.strategic_orientation == StrategicStance.EFFICIENCY_LED
        ):
            new_stance = StrategicStance.INNOVATION_LED

        return MatrixPosition(
            airline_direct_booking_dominance=round(new_db, 4),
            ai_agent_adoption=round(new_ai, 4),
            strategic_orientation=new_stance,
        )


# ---------------------------------------------------------------------------
# Simulator (orchestrator)
# ---------------------------------------------------------------------------


class Simulator:
    """Orchestrates simulation runs over a Scenario."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self._profiles_by_name: Dict[str, StrategicProfile] = {
            p.name: p for p in scenario.strategic_profiles
        }
        self._nodes_by_id: Dict[str, TurningPointNode] = {
            n.id: n for n in scenario.nodes
        }

    # ---- helpers ----------------------------------------------------------

    def _resolve_profile(self, profile_name: str) -> StrategicProfile:
        return self._profiles_by_name[profile_name]

    def _baseline_metrics(self, year: int) -> MetricSnapshot:
        """Interpolate baseline metrics at a given year from the timeline."""
        tl = self.scenario.timeline
        if year <= tl[0].year:
            return copy.deepcopy(tl[0].metrics)
        if year >= tl[-1].year:
            return copy.deepcopy(tl[-1].metrics)
        for i in range(len(tl) - 1):
            if tl[i].year <= year <= tl[i + 1].year:
                t = (year - tl[i].year) / (tl[i + 1].year - tl[i].year)
                m0, m1 = tl[i].metrics, tl[i + 1].metrics
                return MetricSnapshot(
                    revenue_index=round(m0.revenue_index + t * (m1.revenue_index - m0.revenue_index), 4),
                    market_share=round(m0.market_share + t * (m1.market_share - m0.market_share), 4),
                    tech_adoption_velocity=round(m0.tech_adoption_velocity + t * (m1.tech_adoption_velocity - m0.tech_adoption_velocity), 4),
                )
        return copy.deepcopy(tl[-1].metrics)

    def _init_competitor_states(self, start_year: int) -> List[CompetitorState]:
        """Create initial CompetitorState for each competitor at start_year."""
        baseline = self._baseline_metrics(start_year)
        states = []
        for c in self.scenario.competitors:
            states.append(
                CompetitorState(
                    name=c.name,
                    position=copy.deepcopy(c.initial_position),
                    profile_name=c.default_profile,
                    metrics=copy.deepcopy(baseline),
                )
            )
        return states

    # ---- main simulation --------------------------------------------------

    def run(self, branch_choices: Dict[str, str]) -> SimulationResult:
        """Run a simulation with explicit branch choices.

        Args:
            branch_choices: mapping of node_id -> branch_id
                e.g. {"tp-001": "tp-001-a", "tp-002": "tp-002-b", "tp-003": "tp-003-a"}

        Returns:
            SimulationResult with per-step competitor states and projected timeline.
        """
        sorted_nodes = sorted(self.scenario.nodes, key=lambda n: n.year)
        first_year = sorted_nodes[0].year if sorted_nodes else 2025
        comp_states = self._init_competitor_states(first_year)

        steps: List[SimulationStep] = []
        branch_path: List[str] = []

        for node in sorted_nodes:
            chosen_id = branch_choices.get(node.id)
            branch = next((b for b in node.branches if b.id == chosen_id), None)
            if branch is None:
                # Default: pick highest-probability branch
                branch = max(node.branches, key=lambda b: b.probability)
            branch_path.append(branch.id)

            new_states = []
            for cs in comp_states:
                profile = self._resolve_profile(cs.profile_name)
                fit = FitEngine.calculate_fit(profile, cs.position, node.external_driver)
                new_metrics = FitEngine.apply_branch(cs.metrics, branch, fit)
                new_position = MatrixEngine.evolve_position(
                    cs.position, profile, branch, node.external_driver
                )
                new_states.append(
                    CompetitorState(
                        name=cs.name,
                        position=new_position,
                        profile_name=cs.profile_name,
                        metrics=new_metrics,
                        fit_score=fit,
                    )
                )

            comp_states = new_states
            steps.append(
                SimulationStep(
                    node_id=node.id,
                    year=node.year,
                    branch_chosen=branch.id,
                    competitor_states=copy.deepcopy(comp_states),
                )
            )

        projected = self._project_timeline(steps)
        return SimulationResult(
            scenario_id=self.scenario.id,
            branch_path=branch_path,
            steps=steps,
            projected_timeline=projected,
        )

    def _project_timeline(self, steps: List[SimulationStep]) -> List[TimelineDataPoint]:
        """Build a projected timeline by blending baseline with simulation deltas."""
        baseline_tl = self.scenario.timeline
        if not steps:
            return copy.deepcopy(baseline_tl)

        projected: List[TimelineDataPoint] = []
        # Cumulative average delta across competitors at each step
        cumulative_delta = MetricSnapshot(0.0, 0.0, 0.0)
        step_idx = 0

        for dp in baseline_tl:
            # Accumulate deltas from steps whose year <= this data point
            while step_idx < len(steps) and steps[step_idx].year <= dp.year:
                step = steps[step_idx]
                avg_rev = sum(cs.metrics.revenue_index for cs in step.competitor_states) / len(step.competitor_states)
                avg_ms = sum(cs.metrics.market_share for cs in step.competitor_states) / len(step.competitor_states)
                avg_tav = sum(cs.metrics.tech_adoption_velocity for cs in step.competitor_states) / len(step.competitor_states)
                baseline_at_step = self._baseline_metrics(step.year)
                cumulative_delta = MetricSnapshot(
                    revenue_index=avg_rev - baseline_at_step.revenue_index,
                    market_share=avg_ms - baseline_at_step.market_share,
                    tech_adoption_velocity=avg_tav - baseline_at_step.tech_adoption_velocity,
                )
                step_idx += 1

            projected.append(
                TimelineDataPoint(
                    year=dp.year,
                    metrics=MetricSnapshot(
                        revenue_index=round(dp.metrics.revenue_index + cumulative_delta.revenue_index, 4),
                        market_share=round(min(max(dp.metrics.market_share + cumulative_delta.market_share, 0.0), 1.0), 4),
                        tech_adoption_velocity=round(min(max(dp.metrics.tech_adoption_velocity + cumulative_delta.tech_adoption_velocity, 0.0), 1.0), 4),
                    ),
                    label=dp.label,
                )
            )
        return projected

    # ---- historical backtesting -------------------------------------------

    def backtest(self, historical_cutoff: int = 2025) -> BacktestResult:
        """Validate engine against historical timeline data (years <= cutoff).

        Runs the simulation using the highest-probability branch at each node
        that falls within the historical window, then compares projected metrics
        against the scenario's baseline timeline.
        """
        # Auto-select highest-probability branches for historical nodes
        choices: Dict[str, str] = {}
        for node in self.scenario.nodes:
            if node.year <= historical_cutoff:
                best = max(node.branches, key=lambda b: b.probability)
                choices[node.id] = best.id

        result = self.run(choices)

        # Compare projected timeline against baseline for years <= cutoff
        baseline_by_year = {dp.year: dp.metrics for dp in self.scenario.timeline}
        projected_by_year = {dp.year: dp.metrics for dp in result.projected_timeline}

        errors_rev, errors_ms, errors_tav = [], [], []
        details = []

        for year in sorted(baseline_by_year.keys()):
            if year > historical_cutoff:
                break
            if year not in projected_by_year:
                continue
            b = baseline_by_year[year]
            p = projected_by_year[year]
            e_rev = abs(p.revenue_index - b.revenue_index)
            e_ms = abs(p.market_share - b.market_share)
            e_tav = abs(p.tech_adoption_velocity - b.tech_adoption_velocity)
            errors_rev.append(e_rev)
            errors_ms.append(e_ms)
            errors_tav.append(e_tav)
            details.append({
                "year": year,
                "baseline": asdict(b),
                "projected": asdict(p),
                "errors": {
                    "revenue_index": round(e_rev, 4),
                    "market_share": round(e_ms, 4),
                    "tech_adoption_velocity": round(e_tav, 4),
                },
            })

        n = len(errors_rev) or 1
        return BacktestResult(
            historical_cutoff=historical_cutoff,
            mean_absolute_error={
                "revenue_index": round(sum(errors_rev) / n, 4),
                "market_share": round(sum(errors_ms) / n, 4),
                "tech_adoption_velocity": round(sum(errors_tav) / n, 4),
            },
            data_points_compared=len(details),
            details=details,
        )

    # ---- scenario generation ----------------------------------------------

    def generate_scenarios(
        self,
        weights: Optional[Dict[str, float]] = None,
    ) -> List[Scenario]:
        """Dynamically generate scenario variants by enumerating all
        branch combinations and scoring them with optional axis weights.

        Args:
            weights: optional multipliers for the three metric axes:
                {"revenue": w, "market_share": w, "tech_adoption": w}
                Used to rank and name generated scenarios.

        Returns:
            List of Scenario objects with projected timelines baked in.
        """
        w = weights or {"revenue": 1.0, "market_share": 1.0, "tech_adoption": 1.0}
        sorted_nodes = sorted(self.scenario.nodes, key=lambda n: n.year)

        # Enumerate all branch combinations
        branch_lists = [node.branches for node in sorted_nodes]
        all_combos = list(itertools.product(*branch_lists))

        scenarios: List[Scenario] = []
        for idx, combo in enumerate(all_combos):
            choices = {
                node.id: branch.id
                for node, branch in zip(sorted_nodes, combo)
            }
            sim_result = self.run(choices)

            # Compute a composite score for ranking
            final = sim_result.projected_timeline[-1].metrics
            score = (
                w["revenue"] * final.revenue_index
                + w["market_share"] * final.market_share * 100  # normalize scale
                + w["tech_adoption"] * final.tech_adoption_velocity * 50
            )

            # Build descriptive name from chosen branch labels
            branch_labels = " → ".join(b.label for b in combo)
            path_probability = 1.0
            for b in combo:
                path_probability *= b.probability

            new_scenario = Scenario(
                id=f"gen-{idx + 1:03d}",
                name=f"Path: {branch_labels}",
                description=(
                    f"Auto-generated scenario following: {branch_labels}. "
                    f"Combined path probability: {path_probability:.1%}. "
                    f"Composite score: {score:.1f}."
                ),
                timeline=sim_result.projected_timeline,
                nodes=copy.deepcopy(self.scenario.nodes),
                strategic_profiles=copy.deepcopy(self.scenario.strategic_profiles),
                competitors=copy.deepcopy(self.scenario.competitors),
                metadata={
                    "source_scenario": self.scenario.id,
                    "branch_path": json.dumps(sim_result.branch_path),
                    "path_probability": f"{path_probability:.4f}",
                    "composite_score": f"{score:.2f}",
                    "weights": json.dumps(w),
                },
            )
            scenarios.append(new_scenario)

        # Sort by composite score descending
        scenarios.sort(
            key=lambda s: float(s.metadata.get("composite_score", "0")),
            reverse=True,
        )
        return scenarios


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    scenario = build_sample_scenario()
    sim = Simulator(scenario)

    print("=" * 60)
    print("Phase 2: Scenario Simulation Engine")
    print("=" * 60)

    # 1. Historical backtest
    print("\n--- Historical Backtest (up to 2025) ---")
    bt = sim.backtest(historical_cutoff=2025)
    print(f"Data points compared: {bt.data_points_compared}")
    print(f"Mean Absolute Errors: {bt.mean_absolute_error}")

    # 2. Single simulation run (optimistic path)
    print("\n--- Simulation: Optimistic Path ---")
    optimistic_choices = {
        "tp-001": "tp-001-a",  # Embrace NDC
        "tp-002": "tp-002-a",  # Build Proprietary AI
        "tp-003": "tp-003-b",  # Become Aggregator Platform
    }
    result = sim.run(optimistic_choices)
    for step in result.steps:
        print(f"\n  [{step.year}] Node {step.node_id} → Branch {step.branch_chosen}")
        for cs in step.competitor_states:
            print(f"    {cs.name}: fit={cs.fit_score:.2f}  rev={cs.metrics.revenue_index:.2f}  "
                  f"ms={cs.metrics.market_share:.2%}  tav={cs.metrics.tech_adoption_velocity:.2%}")
            print(f"      Matrix: db={cs.position.airline_direct_booking_dominance:.2f}  "
                  f"ai={cs.position.ai_agent_adoption:.2f}  stance={cs.position.strategic_orientation.value}")

    # 3. Generate all scenario variants and save
    print("\n--- Generating All Scenario Variants ---")
    generated = sim.generate_scenarios()
    print(f"Generated {len(generated)} scenario variants.")
    for s in generated[:3]:
        print(f"  [{s.id}] {s.name}")
        print(f"         Score: {s.metadata['composite_score']}  Probability: {s.metadata['path_probability']}")

    # Save to data/
    out_path = save_scenarios(generated, DATA_DIR / "scenarios_generated.json")
    print(f"\nSaved generated scenarios to {out_path}")

    # Also update the main scenarios.json with the top-ranked scenario
    top = generated[0]
    save_scenarios([scenario, top], DATA_DIR / "scenarios.json")
    print(f"Updated scenarios.json with base + top-ranked scenario.")


if __name__ == "__main__":
    main()
