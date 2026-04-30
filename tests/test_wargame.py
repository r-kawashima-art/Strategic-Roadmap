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


class GraphConnectivityTests(unittest.TestCase):
    """Phase 9.5 — every node introduced via /revise must be reachable.

    Encodes the invariant from spec §9.5.1: every turning point (other than
    the earliest, which the renderer reaches via the implicit historical
    chain) must have at least one incoming edge from another node. Patched
    previews from `apply_diff` must satisfy the same invariant.
    """

    def setUp(self) -> None:
        # Late import so the war-gaming suite still runs if the FastAPI/
        # anthropic deps used by the rest of src.api are not installed.
        import dataclasses

        from src.api.scenario_patch import DiffError, apply_diff

        self._dataclasses = dataclasses
        self._apply_diff = apply_diff
        self._DiffError = DiffError

    def _scenario_dict(self):
        return self._dataclasses.asdict(fresh_scenario())

    def _assert_connectivity(self, scen) -> None:
        in_deg = {n["id"]: 0 for n in scen["nodes"]}
        for n in scen["nodes"]:
            for b in n["branches"]:
                tgt = b.get("next_node_id")
                if tgt and tgt in in_deg:
                    in_deg[tgt] += 1
        sorted_nodes = sorted(scen["nodes"], key=lambda n: n["year"])
        # Skip the earliest turning point — it is reached via the implicit
        # historical chain that the renderer synthesises from `timeline`.
        for n in sorted_nodes[1:]:
            self.assertGreaterEqual(
                in_deg[n["id"]], 1,
                f"Node {n['id']!r} is unreachable (in-degree 0)",
            )

    def _sample_new_node(self, node_id: str, year: int) -> dict:
        return {
            "id": node_id,
            "year": year,
            "title": "Sample expansion",
            "description": "Connectivity-test node.",
            "external_driver": "GenAI breakthrough",
            "branches": [
                {
                    "id": f"{node_id}-a",
                    "label": "Adapt",
                    "description": "lean in",
                    "probability": 0.6,
                    "metric_delta": {
                        "revenue_index": 0.05,
                        "market_share": 0.01,
                        "tech_adoption_velocity": 0.02,
                    },
                },
                {
                    "id": f"{node_id}-b",
                    "label": "Resist",
                    "description": "hold the line",
                    "probability": 0.4,
                    "metric_delta": {
                        "revenue_index": -0.05,
                        "market_share": -0.01,
                        "tech_adoption_velocity": -0.02,
                    },
                },
            ],
        }

    def test_every_node_is_reachable_in_baseline(self) -> None:
        self._assert_connectivity(self._scenario_dict())

    def test_add_node_auto_rewire_preserves_connectivity(self) -> None:
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2038)
        self._apply_diff(
            [scen],
            {"op": "add_node", "scenario_id": scen["id"], "node": new_node},
        )
        self.assertTrue(any(n["id"] == "tp-004" for n in scen["nodes"]))
        self._assert_connectivity(scen)

    def test_add_node_with_fork_from_preserves_existing_branches(self) -> None:
        scen = self._scenario_dict()
        target = next(n for n in scen["nodes"] if n["id"] == "tp-002")
        pre_branches = [
            {
                "id": b["id"],
                "next_node_id": b.get("next_node_id"),
                "probability": b["probability"],
                "label": b["label"],
            }
            for b in target["branches"]
        ]
        pre_count = len(target["branches"])

        new_node = self._sample_new_node("tp-004", year=2038)
        fork_branch = {
            "id": "tp-002-d",
            "label": "Cancel Prime, fund eDreams Lab",
            "description": "Counterfactual divergent fork.",
            "probability": 0.15,
            "metric_delta": {
                "revenue_index": -0.05,
                "market_share": 0.0,
                "tech_adoption_velocity": 0.10,
            },
        }
        self._apply_diff(
            [scen],
            {
                "op": "add_node",
                "scenario_id": scen["id"],
                "node": new_node,
                "fork_from": [{"from_node_id": "tp-002", "branch": fork_branch}],
            },
        )

        target_after = next(n for n in scen["nodes"] if n["id"] == "tp-002")
        self.assertEqual(
            len(target_after["branches"]), pre_count + 1,
            "fork_from should add exactly one branch to the targeted past node",
        )
        for orig in pre_branches:
            match = next(
                (b for b in target_after["branches"] if b["id"] == orig["id"]),
                None,
            )
            self.assertIsNotNone(match, f"Original branch {orig['id']!r} disappeared")
            self.assertEqual(match["next_node_id"], orig["next_node_id"],
                             "fork_from must not rewire existing edges")
            self.assertEqual(match["label"], orig["label"])

        fork = next(b for b in target_after["branches"] if b["id"] == "tp-002-d")
        self.assertEqual(fork["next_node_id"], "tp-004",
                         "server must stamp next_node_id on fork branches")
        # Fork branch keeps its supplied probability — only the *existing*
        # branches are rescaled by the PMF guard.
        self.assertAlmostEqual(fork["probability"], 0.15, places=6)

        # PMF invariant: the host node's branch probabilities sum to 1.0.
        host_total = sum(b["probability"] for b in target_after["branches"])
        self.assertAlmostEqual(host_total, 1.0, delta=1e-3)

        # Relative shape of the original branches is preserved (proportional
        # rescale, not uniform): the ratio between any two original branches
        # is unchanged from before the fork was added.
        orig_a, orig_b = pre_branches[0], pre_branches[1]
        post_a = next(b for b in target_after["branches"] if b["id"] == orig_a["id"])
        post_b = next(b for b in target_after["branches"] if b["id"] == orig_b["id"])
        if orig_b["probability"] > 0:
            self.assertAlmostEqual(
                post_a["probability"] / post_b["probability"],
                orig_a["probability"] / orig_b["probability"],
                places=6,
                msg="proportional rescale must preserve original branch ratios",
            )

        # Pure-divergence: fork_from set, rewire_from absent → previously-
        # terminal branches at tp-003 must remain terminal (no auto-rewire
        # should leak into the divergence path).
        terminal_node = next(n for n in scen["nodes"] if n["id"] == "tp-003")
        for b in terminal_node["branches"]:
            self.assertIsNone(
                b["next_node_id"],
                "fork_from-only revisions must not auto-rewire other terminals",
            )

        self._assert_connectivity(scen)

    def test_add_node_unreachable_raises(self) -> None:
        # Synthetic scenario with zero terminal branches: a 2-node cycle.
        cycle_scen = {
            "id": "scenario-cycle",
            "nodes": [
                {
                    "id": "x", "year": 2025, "title": "X",
                    "description": "", "external_driver": "GenAI breakthrough",
                    "branches": [{
                        "id": "x-a", "label": "to y", "description": "",
                        "probability": 1.0, "next_node_id": "y",
                        "metric_delta": {
                            "revenue_index": 0.0, "market_share": 0.0,
                            "tech_adoption_velocity": 0.0,
                        },
                    }],
                },
                {
                    "id": "y", "year": 2030, "title": "Y",
                    "description": "", "external_driver": "GenAI breakthrough",
                    "branches": [{
                        "id": "y-a", "label": "to x", "description": "",
                        "probability": 1.0, "next_node_id": "x",
                        "metric_delta": {
                            "revenue_index": 0.0, "market_share": 0.0,
                            "tech_adoption_velocity": 0.0,
                        },
                    }],
                },
            ],
        }
        new_node = self._sample_new_node("z", year=2035)
        with self.assertRaises(self._DiffError) as ctx:
            self._apply_diff(
                [cycle_scen],
                {"op": "add_node", "scenario_id": "scenario-cycle", "node": new_node},
            )
        self.assertIn("unreachable", str(ctx.exception))

    # ── Phase 10.5 — chronological-consistency guards ──────────────────────
    # Baseline turning-point years: tp-001 = 2025, tp-002 = 2028, tp-003 = 2032.
    # All three guards (rewire_from / fork_from / auto-rewire) must reject any
    # wiring that would create an arrow going backwards in time.

    def test_fork_from_rejects_future_predecessor(self) -> None:
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2030)
        fork_branch = {
            "id": "tp-003-d", "label": "Backwards fork", "description": "",
            "probability": 0.10,
            "metric_delta": {
                "revenue_index": 0.0, "market_share": 0.0,
                "tech_adoption_velocity": 0.0,
            },
        }
        with self.assertRaises(self._DiffError) as ctx:
            self._apply_diff([scen], {
                "op": "add_node",
                "scenario_id": scen["id"],
                "node": new_node,
                # tp-003 is at year 2032 — strictly after the new node's 2030.
                "fork_from": [{"from_node_id": "tp-003", "branch": fork_branch}],
            })
        self.assertIn("chronological contradiction", str(ctx.exception))
        # Atomicity: the rejected diff must not have appended the new node or
        # mutated tp-003's branches.
        self.assertFalse(any(n["id"] == "tp-004" for n in scen["nodes"]))
        tp003 = next(n for n in scen["nodes"] if n["id"] == "tp-003")
        self.assertFalse(any(b["id"] == "tp-003-d" for b in tp003["branches"]))

    def test_rewire_from_rejects_future_predecessor(self) -> None:
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2030)
        # tp-003-a is a terminal branch at year 2032 — rewiring it into a 2030
        # new node would point backwards in time.
        with self.assertRaises(self._DiffError) as ctx:
            self._apply_diff([scen], {
                "op": "add_node",
                "scenario_id": scen["id"],
                "node": new_node,
                "rewire_from": [{"node_id": "tp-003", "branch_id": "tp-003-a"}],
            })
        self.assertIn("chronological contradiction", str(ctx.exception))
        self.assertFalse(any(n["id"] == "tp-004" for n in scen["nodes"]))

    def test_auto_rewire_skips_future_terminals_yielding_unreachable(self) -> None:
        # New node year 2030. The baseline scenario's only terminal branches
        # live at tp-003 (year 2032). Auto-rewire must skip them — leaving the
        # rewire-target set empty — and the connectivity guard must fire.
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2030)
        with self.assertRaises(self._DiffError) as ctx:
            self._apply_diff([scen], {
                "op": "add_node",
                "scenario_id": scen["id"],
                "node": new_node,
            })
        self.assertIn("unreachable", str(ctx.exception))
        # tp-003's terminals must remain terminal — chronological guard
        # short-circuited the auto-rewire scan before any mutation.
        tp003 = next(n for n in scen["nodes"] if n["id"] == "tp-003")
        for b in tp003["branches"]:
            self.assertIsNone(b["next_node_id"])

    def test_fork_from_succeeds_when_predecessor_is_earlier(self) -> None:
        # tp-002 = 2028, new node = 2030 — the legitimate divergence path.
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2030)
        fork_branch = {
            "id": "tp-002-d", "label": "Legitimate fork", "description": "",
            "probability": 0.10,
            "metric_delta": {
                "revenue_index": 0.0, "market_share": 0.0,
                "tech_adoption_velocity": 0.0,
            },
        }
        self._apply_diff([scen], {
            "op": "add_node",
            "scenario_id": scen["id"],
            "node": new_node,
            "fork_from": [{"from_node_id": "tp-002", "branch": fork_branch}],
        })
        # New node is in scenario; fork branch on tp-002 points at it.
        self.assertTrue(any(n["id"] == "tp-004" for n in scen["nodes"]))
        tp002 = next(n for n in scen["nodes"] if n["id"] == "tp-002")
        fork = next(b for b in tp002["branches"] if b["id"] == "tp-002-d")
        self.assertEqual(fork["next_node_id"], "tp-004")
        self._assert_connectivity(scen)

    def test_auto_rewire_continuation_after_latest_year_still_works(self) -> None:
        # Regression guard: a new node strictly later than every existing TP
        # must still pull tp-003's terminals via auto-rewire (preserves the
        # 9.4.1 behaviour after Phase 10.5 was layered on).
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2035)
        self._apply_diff([scen], {
            "op": "add_node",
            "scenario_id": scen["id"],
            "node": new_node,
        })
        tp003 = next(n for n in scen["nodes"] if n["id"] == "tp-003")
        for b in tp003["branches"]:
            self.assertEqual(
                b["next_node_id"], "tp-004",
                "auto-rewire must still consume tp-003's terminals when the "
                "new node is strictly later than 2032",
            )
        self._assert_connectivity(scen)

    # ── Phase 10.5 — mergeability fallbacks ────────────────────────────────
    # The LLM occasionally emits a node without an explicit `branches` array,
    # or specifies a fork_from host_id that doesn't exist in the scenario.
    # These cases must still produce a valid merged scenario rather than
    # rejecting the whole diff outright.

    def test_add_node_synthesizes_default_branch_when_missing(self) -> None:
        # LLM returns a node with NO `branches` key at all. Server should
        # synthesize a single terminal "Continue" branch so the new node is
        # a valid leaf and the wiring (auto-rewire here) can complete.
        scen = self._scenario_dict()
        node_no_branches = {
            "id": "tp-004",
            "year": 2035,
            "title": "Auto-synthesized leaf",
            "description": "LLM omitted branches.",
            "external_driver": "GenAI breakthrough",
            # `branches` deliberately absent
        }
        self._apply_diff([scen], {
            "op": "add_node",
            "scenario_id": scen["id"],
            "node": node_no_branches,
        })

        added = next(n for n in scen["nodes"] if n["id"] == "tp-004")
        self.assertEqual(len(added["branches"]), 1)
        default = added["branches"][0]
        self.assertEqual(default["id"], "tp-004-a")
        self.assertEqual(default["label"], "Continue")
        self.assertAlmostEqual(default["probability"], 1.0)
        self.assertIsNone(default["next_node_id"], "default branch must be terminal")
        for k in ("revenue_index", "market_share", "tech_adoption_velocity"):
            self.assertEqual(default["metric_delta"][k], 0.0)
        self._assert_connectivity(scen)

    def test_add_node_synthesizes_default_branch_when_empty_list(self) -> None:
        # Same as above but with `branches: []` instead of missing key.
        scen = self._scenario_dict()
        node_empty_branches = {
            "id": "tp-004",
            "year": 2035,
            "title": "Auto-synthesized leaf",
            "description": "LLM emitted empty branches.",
            "external_driver": "GenAI breakthrough",
            "branches": [],
        }
        self._apply_diff([scen], {
            "op": "add_node",
            "scenario_id": scen["id"],
            "node": node_empty_branches,
        })
        added = next(n for n in scen["nodes"] if n["id"] == "tp-004")
        self.assertEqual(len(added["branches"]), 1)
        self.assertEqual(added["branches"][0]["id"], "tp-004-a")

    def test_fork_from_falls_back_to_predecessor_on_unknown_host(self) -> None:
        # LLM hallucinates an unknown host_id. The fallback resolves to the
        # nearest predecessor (year < new_year) so the merge still completes.
        scen = self._scenario_dict()
        new_node = self._sample_new_node("tp-004", year=2030)
        fork_branch = {
            "id": "tp-fallback-a",
            "label": "Hallucinated fork",
            "description": "LLM gave a bad host id.",
            "probability": 0.10,
            "metric_delta": {
                "revenue_index": 0.0, "market_share": 0.0,
                "tech_adoption_velocity": 0.0,
            },
        }
        self._apply_diff([scen], {
            "op": "add_node",
            "scenario_id": scen["id"],
            "node": new_node,
            "fork_from": [{"from_node_id": "tp-imaginary", "branch": fork_branch}],
        })
        # The fork branch must have landed on the nearest pre-2030 node,
        # which is tp-002 (year 2028) — strictly later than tp-001 (2025).
        tp002 = next(n for n in scen["nodes"] if n["id"] == "tp-002")
        fork = next(
            (b for b in tp002["branches"] if b["id"] == "tp-fallback-a"),
            None,
        )
        self.assertIsNotNone(fork, "fork must land on the fallback predecessor")
        self.assertEqual(fork["next_node_id"], "tp-004")
        self._assert_connectivity(scen)

    def test_strict_lookup_callers_still_error_on_unknown_id(self) -> None:
        # Regression guard: set_node_field uses _find_node WITHOUT fallback,
        # so a typo'd node_id must surface as DiffError rather than silently
        # routing to a different node.
        scen = self._scenario_dict()
        with self.assertRaises(self._DiffError) as ctx:
            self._apply_diff([scen], {
                "op": "set_node_field",
                "scenario_id": scen["id"],
                "node_id": "tp-imaginary",
                "field": "title",
                "value": "x",
            })
        self.assertIn("Unknown node_id", str(ctx.exception))

    # ── Phase 10.5 — ID coherence (chronological order ↔ tp-NNN suffix) ────
    # Baseline tp-001 / tp-002 / tp-003 → canonical next free id is tp-004.
    # The server overrides any LLM-supplied id that isn't tp-004 so the
    # numeric suffix tracks insertion order and id collisions never break
    # the merge.

    def test_add_node_overrides_misaligned_id(self) -> None:
        scen = self._scenario_dict()
        # LLM picked a far-future-looking id even though new_year=2035 is just
        # after tp-003. Server should rename to tp-004.
        misleading = self._sample_new_node("tp-099", year=2035)
        self._apply_diff([scen], {
            "op": "add_node", "scenario_id": scen["id"], "node": misleading,
        })
        self.assertTrue(any(n["id"] == "tp-004" for n in scen["nodes"]))
        self.assertFalse(any(n["id"] == "tp-099" for n in scen["nodes"]))
        # Branch ids prefixed with the original "tp-099-" must follow the
        # rename so the <node_id>-<letter> convention stays consistent.
        added = next(n for n in scen["nodes"] if n["id"] == "tp-004")
        self.assertTrue(any(b["id"] == "tp-004-a" for b in added["branches"]))
        self.assertTrue(any(b["id"] == "tp-004-b" for b in added["branches"]))
        self.assertFalse(any(b["id"].startswith("tp-099") for b in added["branches"]))

    def test_add_node_overrides_duplicate_id(self) -> None:
        # The LLM picked the id of an EXISTING node — would be a hard
        # duplicate failure under the old code. Server reassigns to tp-004.
        scen = self._scenario_dict()
        dup = self._sample_new_node("tp-002", year=2035)
        self._apply_diff([scen], {
            "op": "add_node", "scenario_id": scen["id"], "node": dup,
        })
        # Original tp-002 (year 2028) is intact; the new node landed at tp-004.
        original = next(n for n in scen["nodes"] if n["id"] == "tp-002")
        self.assertEqual(original["year"], 2028)
        self.assertTrue(any(n["id"] == "tp-004" for n in scen["nodes"]))
        added = next(n for n in scen["nodes"] if n["id"] == "tp-004")
        self.assertEqual(added["year"], 2035)
        # Branches re-prefixed from "tp-002-" → "tp-004-" so they don't
        # collide with the existing tp-002's branches.
        self.assertTrue(any(b["id"] == "tp-004-a" for b in added["branches"]))

    def test_add_node_keeps_aligned_id(self) -> None:
        # If the LLM follows the preamble and supplies the canonical next
        # id ("tp-004" when baseline has tp-001..tp-003), the server keeps
        # it as-is.
        scen = self._scenario_dict()
        canonical = self._sample_new_node("tp-004", year=2035)
        self._apply_diff([scen], {
            "op": "add_node", "scenario_id": scen["id"], "node": canonical,
        })
        added = next(n for n in scen["nodes"] if n["id"] == "tp-004")
        self.assertEqual(added["year"], 2035)
        # Branch ids (tp-004-a / tp-004-b) were already canonical so no rename.
        self.assertTrue(any(b["id"] == "tp-004-a" for b in added["branches"]))
        self.assertTrue(any(b["id"] == "tp-004-b" for b in added["branches"]))

    def test_add_node_override_updates_fork_branch_next_node_id(self) -> None:
        # Override happens upfront, so by the time fork_from is processed
        # the new branch's next_node_id is stamped with the canonical id.
        scen = self._scenario_dict()
        misleading = self._sample_new_node("tp-099", year=2030)
        fork_branch = {
            "id": "tp-002-d", "label": "Counterfactual",
            "description": "", "probability": 0.10,
            "metric_delta": {
                "revenue_index": 0.0, "market_share": 0.0,
                "tech_adoption_velocity": 0.0,
            },
        }
        self._apply_diff([scen], {
            "op": "add_node", "scenario_id": scen["id"], "node": misleading,
            "fork_from": [{"from_node_id": "tp-002", "branch": fork_branch}],
        })
        tp002 = next(n for n in scen["nodes"] if n["id"] == "tp-002")
        fork = next(b for b in tp002["branches"] if b["id"] == "tp-002-d")
        self.assertEqual(
            fork["next_node_id"], "tp-004",
            "fork branch must point at the canonical id, not the LLM's tp-099",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
