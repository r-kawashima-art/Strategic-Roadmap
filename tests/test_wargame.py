"""Phase 4 — War-gaming tests.

Each test encodes a piece of industry-analyst narrative and asserts that the
simulation engine behaves consistently with it. When a test fails, it means
either (a) the engine has drifted from the intended narrative, or (b) the
narrative itself needs to be updated — both warrant a conversation.

Narratives covered:
  - NDC adoption rewards efficiency-led, operationally-integrated players.
  - GenAI breakthroughs reward innovation-led, AI-biased players.
  - Airline direct-booking pressure erodes position faster for low-resilience
    competitors than for high-resilience ones.
  - "Build Proprietary AI" dominates "Wait and See" on tech adoption.
  - Industry tech-adoption velocity is non-decreasing across the baseline
    timeline (secular trend, not a cyclical metric).
  - Historical backtest MAE stays within tolerance vs. the 1990–2025 baseline.
  - Market share and tech-adoption velocity stay within [0, 1] across every
    generated scenario variant.
  - Branch probabilities at each turning point sum to 1.0.
"""

from __future__ import annotations

import unittest

try:
    from tests._helpers import (
        FitEngine,
        MatrixEngine,
        MatrixPosition,
        StrategicProfile,
        StrategicStance,
        fresh_scenario,
        fresh_simulator,
    )
except ImportError:  # allow direct `python tests/test_wargame.py` invocation
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tests._helpers import (  # type: ignore  # noqa: E402
        FitEngine,
        MatrixEngine,
        MatrixPosition,
        StrategicProfile,
        StrategicStance,
        fresh_scenario,
        fresh_simulator,
    )


NDC_TOLERANCE = {"revenue_index": 0.05, "market_share": 0.02, "tech_adoption_velocity": 0.05}


class NarrativeFitTests(unittest.TestCase):
    """Fit scoring must align with the documented driver narratives."""

    def _profile(self, name: str, ai_bias: float, resilience: float, stance: StrategicStance) -> StrategicProfile:
        return StrategicProfile(
            name=name,
            description="",
            ai_adoption_bias=ai_bias,
            direct_booking_resilience=resilience,
            strategic_stance=stance,
        )

    def test_ndc_favours_efficiency_led_over_innovation_led(self) -> None:
        """Under NDC adoption, an efficiency-led profile should out-fit an
        otherwise-identical innovation-led profile (operational integration
        matters more than AI flair for NDC pipelines).
        """
        pos = MatrixPosition(0.5, 0.5, StrategicStance.EFFICIENCY_LED)
        efficient = self._profile("E", ai_bias=0.5, resilience=0.7, stance=StrategicStance.EFFICIENCY_LED)
        innovative = self._profile("I", ai_bias=0.5, resilience=0.7, stance=StrategicStance.INNOVATION_LED)

        fit_e = FitEngine.calculate_fit(efficient, pos, "NDC adoption")
        fit_i = FitEngine.calculate_fit(innovative, pos, "NDC adoption")

        self.assertGreater(fit_e, fit_i, "NDC narrative should reward efficiency-led stance")

    def test_genai_favours_innovation_and_high_ai_bias(self) -> None:
        """Under a GenAI breakthrough, an innovation-led high-AI-bias profile
        must dominate a low-AI-bias efficiency-led one.
        """
        pos = MatrixPosition(0.3, 0.6, StrategicStance.INNOVATION_LED)
        innovator = self._profile("AI-Native", ai_bias=0.9, resilience=0.6, stance=StrategicStance.INNOVATION_LED)
        laggard = self._profile("Laggard", ai_bias=0.2, resilience=0.6, stance=StrategicStance.EFFICIENCY_LED)

        fit_inno = FitEngine.calculate_fit(innovator, pos, "GenAI breakthrough")
        fit_lag = FitEngine.calculate_fit(laggard, pos, "GenAI breakthrough")

        self.assertGreater(fit_inno, fit_lag + 0.2,
                           "GenAI narrative should strongly favour innovation-led AI-native profile")

    def test_fit_score_is_bounded(self) -> None:
        for driver in ("NDC adoption", "GenAI breakthrough", "Airline direct booking dominance", "Unknown"):
            for bias, res, stance in (
                (0.0, 0.0, StrategicStance.EFFICIENCY_LED),
                (1.0, 1.0, StrategicStance.INNOVATION_LED),
                (0.5, 0.5, StrategicStance.EFFICIENCY_LED),
            ):
                p = self._profile("P", ai_bias=bias, resilience=res, stance=stance)
                pos = MatrixPosition(res, bias, stance)
                fit = FitEngine.calculate_fit(p, pos, driver)
                self.assertGreaterEqual(fit, 0.0, f"fit < 0 for driver={driver}")
                self.assertLessEqual(fit, 1.0, f"fit > 1 for driver={driver}")


class BranchDominanceTests(unittest.TestCase):
    """Internal branch choices must preserve the narrative ordering."""

    def test_build_ai_beats_wait_and_see_on_tech_adoption(self) -> None:
        sim = fresh_simulator()
        build_path = {"tp-001": "tp-001-a", "tp-002": "tp-002-a", "tp-003": "tp-003-a"}
        wait_path = {"tp-001": "tp-001-a", "tp-002": "tp-002-c", "tp-003": "tp-003-a"}

        r_build = sim.run(build_path)
        r_wait = sim.run(wait_path)

        build_tav = r_build.projected_timeline[-1].metrics.tech_adoption_velocity
        wait_tav = r_wait.projected_timeline[-1].metrics.tech_adoption_velocity

        self.assertGreater(build_tav, wait_tav,
                           "'Build Proprietary AI' must outpace 'Wait and See' on tech adoption by 2040")

    def test_embrace_ndc_beats_resist_ndc_on_revenue(self) -> None:
        sim = fresh_simulator()
        embrace = sim.run({"tp-001": "tp-001-a", "tp-002": "tp-002-b", "tp-003": "tp-003-a"})
        resist = sim.run({"tp-001": "tp-001-b", "tp-002": "tp-002-b", "tp-003": "tp-003-a"})

        self.assertGreater(embrace.projected_timeline[-1].metrics.revenue_index,
                           resist.projected_timeline[-1].metrics.revenue_index,
                           "Embracing NDC should produce higher long-run revenue than resisting it")

    def test_consolidate_or_exit_is_worst_case(self) -> None:
        """tp-003-c ('Consolidate or Exit') carries the largest negative deltas
        and must be the worst revenue outcome when tp-001/tp-002 are held fixed.
        """
        sim = fresh_simulator()
        base = {"tp-001": "tp-001-a", "tp-002": "tp-002-a"}
        exit_run = sim.run({**base, "tp-003": "tp-003-c"})
        pivot_run = sim.run({**base, "tp-003": "tp-003-a"})
        platform_run = sim.run({**base, "tp-003": "tp-003-b"})

        exit_rev = exit_run.projected_timeline[-1].metrics.revenue_index
        self.assertLess(exit_rev, pivot_run.projected_timeline[-1].metrics.revenue_index)
        self.assertLess(exit_rev, platform_run.projected_timeline[-1].metrics.revenue_index)


class HistoricalBacktestTests(unittest.TestCase):
    """The engine must reproduce the 1990–2025 baseline within tight tolerance."""

    def test_backtest_mae_within_tolerance(self) -> None:
        sim = fresh_simulator()
        bt = sim.backtest(historical_cutoff=2025)
        for metric, mae in bt.mean_absolute_error.items():
            self.assertLessEqual(
                mae, NDC_TOLERANCE[metric],
                f"backtest MAE for {metric} = {mae} exceeds tolerance {NDC_TOLERANCE[metric]}",
            )

    def test_backtest_covers_at_least_eight_historical_points(self) -> None:
        sim = fresh_simulator()
        bt = sim.backtest(historical_cutoff=2025)
        self.assertGreaterEqual(bt.data_points_compared, 8,
                                "Need enough historical coverage to trust the backtest")


class IndustryTrendTests(unittest.TestCase):
    """Structural properties of the timeline and generated scenarios."""

    def test_tech_adoption_is_monotonic_non_decreasing(self) -> None:
        """Tech adoption is a secular trend — it shouldn't reverse in the baseline."""
        tl = fresh_scenario().timeline
        for a, b in zip(tl, tl[1:]):
            self.assertLessEqual(
                a.metrics.tech_adoption_velocity,
                b.metrics.tech_adoption_velocity + 1e-9,
                f"tech adoption reversed between {a.year} and {b.year}",
            )

    def test_all_generated_scenarios_stay_in_unit_interval(self) -> None:
        sim = fresh_simulator()
        generated = sim.generate_scenarios()
        self.assertGreater(len(generated), 0)
        for s in generated:
            for dp in s.timeline:
                self.assertGreaterEqual(dp.metrics.market_share, 0.0, f"{s.id} market_share<0 at {dp.year}")
                self.assertLessEqual(dp.metrics.market_share, 1.0, f"{s.id} market_share>1 at {dp.year}")
                self.assertGreaterEqual(dp.metrics.tech_adoption_velocity, 0.0)
                self.assertLessEqual(dp.metrics.tech_adoption_velocity, 1.0)

    def test_branch_probabilities_sum_to_one_per_node(self) -> None:
        for node in fresh_scenario().nodes:
            total = sum(b.probability for b in node.branches)
            self.assertAlmostEqual(total, 1.0, places=3,
                                   msg=f"Node {node.id} branch probabilities sum to {total}, not 1.0")

    def test_direct_booking_pressure_hurts_low_resilience_more(self) -> None:
        """Two identical competitors that differ only on direct_booking_resilience
        should separate on the airline-direct axis after the direct-booking
        turning point (tp-003). Low resilience must drift higher.
        """
        scenario = fresh_scenario()
        high = next(p for p in scenario.strategic_profiles if p.direct_booking_resilience >= 0.7)
        low = next(p for p in scenario.strategic_profiles if p.direct_booking_resilience <= 0.3)

        pos = MatrixPosition(0.3, 0.5, StrategicStance.EFFICIENCY_LED)
        tp003 = next(n for n in scenario.nodes if n.external_driver == "Airline direct booking dominance")
        branch = tp003.branches[0]

        new_high = MatrixEngine.evolve_position(pos, high, branch, tp003.external_driver)
        new_low = MatrixEngine.evolve_position(pos, low, branch, tp003.external_driver)

        self.assertGreater(
            new_low.airline_direct_booking_dominance,
            new_high.airline_direct_booking_dominance,
            "Low-resilience competitors must feel more direct-booking pressure than high-resilience ones",
        )


class MarketShareProjectionTests(unittest.TestCase):
    """FR-6 / Phase-5 narrative checks on the per-competitor market-share
    projection emitted by `Simulator.project_market_shares()`."""

    def setUp(self) -> None:
        self.sim = fresh_simulator()
        # Use the optimistic path — the narrative only holds under conditions
        # that reward high-AI-bias / high-resilience profiles.
        self.optimistic = {
            "tp-001": "tp-001-a",   # Embrace NDC
            "tp-002": "tp-002-a",   # Build Proprietary AI
            "tp-003": "tp-003-b",   # Become Aggregator Platform
        }
        self.result = self.sim.run(self.optimistic)
        self.projection = self.sim.project_market_shares(self.result)

    def test_projection_has_every_competitor_plus_other(self) -> None:
        names = {c.name for c in self.sim.scenario.competitors}
        self.assertTrue(names.issubset(self.projection.keys()),
                        f"projection missing competitors: {names - set(self.projection.keys())}")
        self.assertIn("Other", self.projection,
                      "'Other' bucket must be present so tracked + untracked sums to 1.0")

    def test_every_share_is_in_unit_interval(self) -> None:
        for name, series in self.projection.items():
            for pt in series:
                self.assertGreaterEqual(pt["share"], 0.0,
                                        f"{name}@{pt['year']} share < 0: {pt['share']}")
                self.assertLessEqual(pt["share"], 1.0,
                                     f"{name}@{pt['year']} share > 1: {pt['share']}")

    def test_shares_sum_to_one_at_every_year(self) -> None:
        years = [pt["year"] for pt in next(iter(self.projection.values()))]
        for idx, year in enumerate(years):
            total = sum(series[idx]["share"] for series in self.projection.values())
            self.assertAlmostEqual(
                total, 1.0, places=3,
                msg=f"year {year}: tracked + Other = {total}, expected 1.0 ± 0.001",
            )

    def test_strong_profile_ends_ahead_of_weak_profile(self) -> None:
        """Narrative consistency: at the end of the optimistic simulation, a
        Differentiator (high AI bias + high direct-booking resilience) should
        end with a *higher fit-weighted market share* than a Cost Leader
        (low AI bias + low resilience).

        We check this at the simulation level (pre-projection-normalization)
        because every competitor is seeded from the same aggregate baseline
        in `_init_competitor_states`. That makes absolute market_share at the
        final step a clean, fit-weighted ranking signal — whereas the
        post-normalization projection mixes in the initial-share base, which
        artificially favours small incumbents on relative-growth metrics.
        """
        scenario = self.sim.scenario
        profiles = {p.name: p for p in scenario.strategic_profiles}
        strong = next(c for c in scenario.competitors
                      if profiles[c.default_profile].ai_adoption_bias >= 0.8
                      and profiles[c.default_profile].direct_booking_resilience >= 0.6)
        weak = next(c for c in scenario.competitors
                    if profiles[c.default_profile].ai_adoption_bias <= 0.4
                    and profiles[c.default_profile].direct_booking_resilience <= 0.3)

        final_states = {cs.name: cs for cs in self.result.steps[-1].competitor_states}
        strong_ms = final_states[strong.name].metrics.market_share
        weak_ms   = final_states[weak.name].metrics.market_share

        self.assertGreater(
            strong_ms, weak_ms,
            f"Narrative broken: {strong.name} final ms={strong_ms:.3f} should exceed "
            f"{weak.name} ms={weak_ms:.3f} under the optimistic path",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
