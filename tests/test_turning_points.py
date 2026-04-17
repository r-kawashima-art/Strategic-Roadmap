"""Phase 4 — Turning Points clarity tests.

User-story acceptance criterion:
    "Each branch must have labeled Turning Points explaining the *why* of the
    divergence."

These tests act as the structural proxy for that criterion. A human reviewer
still has to judge whether the prose is *actually* clear, but failing any of
these tests means a turning point is so thin it cannot even be reviewed.
"""

from __future__ import annotations

import unittest

try:
    from tests._helpers import FitEngine, fresh_scenario
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tests._helpers import FitEngine, fresh_scenario  # type: ignore  # noqa: E402


MIN_DESCRIPTION_CHARS = 40
MIN_BRANCH_DESCRIPTION_CHARS = 25


class TurningPointStructureTests(unittest.TestCase):

    def setUp(self) -> None:
        self.scenario = fresh_scenario()

    def test_every_node_has_nonempty_core_fields(self) -> None:
        for node in self.scenario.nodes:
            self.assertTrue(node.id.strip(), f"node missing id")
            self.assertTrue(node.title.strip(), f"{node.id} missing title")
            self.assertTrue(node.description.strip(), f"{node.id} missing description")
            self.assertTrue(node.external_driver.strip(), f"{node.id} missing external_driver")
            self.assertGreater(node.year, 1990, f"{node.id} year out of project range")
            self.assertLessEqual(node.year, 2040, f"{node.id} year past 2040 horizon")

    def test_node_descriptions_are_long_enough_to_review(self) -> None:
        for node in self.scenario.nodes:
            self.assertGreaterEqual(
                len(node.description), MIN_DESCRIPTION_CHARS,
                f"{node.id} '{node.title}' description too short for a reviewer to evaluate",
            )

    def test_every_node_has_at_least_two_branches(self) -> None:
        for node in self.scenario.nodes:
            self.assertGreaterEqual(len(node.branches), 2,
                                    f"{node.id} is not a real decision (needs >=2 branches)")

    def test_branch_labels_unique_within_node(self) -> None:
        for node in self.scenario.nodes:
            labels = [b.label for b in node.branches]
            self.assertEqual(len(labels), len(set(labels)),
                             f"{node.id} has duplicate branch labels: {labels}")

    def test_branch_ids_globally_unique(self) -> None:
        seen = set()
        for node in self.scenario.nodes:
            for b in node.branches:
                self.assertNotIn(b.id, seen, f"duplicate branch id {b.id}")
                seen.add(b.id)

    def test_every_branch_explains_its_why(self) -> None:
        for node in self.scenario.nodes:
            for b in node.branches:
                self.assertTrue(b.label.strip(), f"{b.id} missing label")
                self.assertGreaterEqual(
                    len(b.description), MIN_BRANCH_DESCRIPTION_CHARS,
                    f"{b.id} description too short — reviewer cannot assess the 'why'",
                )

    def test_every_branch_has_meaningful_metric_delta(self) -> None:
        """At least one of the three axes must be non-zero; otherwise the
        branch is decorative and not actually branching the scenario.
        """
        for node in self.scenario.nodes:
            for b in node.branches:
                d = b.metric_delta
                self.assertTrue(
                    abs(d.revenue_index) + abs(d.market_share) + abs(d.tech_adoption_velocity) > 0,
                    f"{b.id} has a zero metric_delta — it doesn't actually change anything",
                )

    def test_probabilities_are_valid(self) -> None:
        for node in self.scenario.nodes:
            for b in node.branches:
                self.assertGreaterEqual(b.probability, 0.0, f"{b.id} negative probability")
                self.assertLessEqual(b.probability, 1.0, f"{b.id} probability > 1.0")

    def test_next_node_references_exist_or_are_terminal(self) -> None:
        node_ids = {n.id for n in self.scenario.nodes}
        for node in self.scenario.nodes:
            for b in node.branches:
                if b.next_node_id is not None:
                    self.assertIn(b.next_node_id, node_ids,
                                  f"{b.id} points at unknown node {b.next_node_id}")

    def test_external_drivers_are_handled_by_fit_engine(self) -> None:
        """If a turning point references a driver FitEngine doesn't know about,
        the fit model silently falls through to DEFAULT_WEIGHTS — which means
        the scenario's own narrative isn't being scored. Catch that here.
        """
        known = set(FitEngine.DRIVER_WEIGHTS.keys())
        for node in self.scenario.nodes:
            self.assertIn(
                node.external_driver, known,
                f"{node.id} driver '{node.external_driver}' not in FitEngine.DRIVER_WEIGHTS — "
                f"either add it to DRIVER_WEIGHTS or reuse an existing driver",
            )

    def test_nodes_are_ordered_in_time(self) -> None:
        """Turning points should progress forward in time so the flowchart
        reads left-to-right without reordering.
        """
        years = [n.year for n in self.scenario.nodes]
        self.assertEqual(years, sorted(years),
                         f"nodes not in chronological order: {years}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
