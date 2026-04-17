"""Phase 4 — Verification runner.

Runs the war-gaming and turning-point clarity suites, then writes a
human-readable markdown report to specs/verification_report.md so a strategy
reviewer can assess the turning points without running Python themselves.

Usage:
    python3 -m tests.run_verification
    python3 tests/run_verification.py
"""

from __future__ import annotations

import io
import sys
import unittest
from datetime import date
from pathlib import Path

try:
    from tests._helpers import FitEngine, PROJECT_ROOT, fresh_scenario, fresh_simulator
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tests._helpers import FitEngine, PROJECT_ROOT, fresh_scenario, fresh_simulator  # type: ignore  # noqa: E402


REPORT_PATH = PROJECT_ROOT / "specs" / "verification_report.md"


def _run_suite(module_name: str) -> tuple[unittest.TestResult, str]:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName(module_name)
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    return result, stream.getvalue()


def _format_result_block(title: str, result: unittest.TestResult, log: str) -> str:
    status = "PASS" if result.wasSuccessful() else "FAIL"
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed
    lines = [
        f"### {title} — **{status}**",
        "",
        f"- Tests run: {total}",
        f"- Passed: {passed}",
        f"- Failed/errored: {failed}",
        "",
    ]
    if result.failures or result.errors:
        lines.append("#### Failures")
        for case, tb in result.failures + result.errors:
            lines.append(f"- `{case}`")
            lines.append("")
            lines.append("  ```")
            for tb_line in tb.strip().splitlines():
                lines.append(f"  {tb_line}")
            lines.append("  ```")
    lines.append("<details><summary>Full log</summary>")
    lines.append("")
    lines.append("```")
    lines.append(log.strip())
    lines.append("```")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    return "\n".join(lines)


def _turning_point_review() -> str:
    """Human-oriented dump of every turning point with its branches, so that a
    strategy reviewer can eyeball the 'why' of each divergence (the
    user_story.md acceptance criterion) without reading source code.
    """
    scenario = fresh_scenario()
    lines = ["## Turning Points — Clarity Review", ""]
    lines.append(f"*Scenario under review:* **{scenario.name}** (`{scenario.id}`)")
    lines.append("")
    lines.append(scenario.description)
    lines.append("")
    for node in scenario.nodes:
        lines.append(f"### {node.year} — {node.title} (`{node.id}`)")
        lines.append("")
        lines.append(f"**External driver:** {node.external_driver}")
        lines.append("")
        lines.append(f"> {node.description}")
        lines.append("")
        lines.append("| Branch | Label | Probability | Δrev | Δms | Δtav | Rationale |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for b in node.branches:
            d = b.metric_delta
            lines.append(
                f"| `{b.id}` | **{b.label}** | {b.probability:.0%} | "
                f"{d.revenue_index:+.2f} | {d.market_share:+.2%} | {d.tech_adoption_velocity:+.2%} | "
                f"{b.description} |"
            )
        lines.append("")
        if node.external_driver not in FitEngine.DRIVER_WEIGHTS:
            lines.append(
                f"⚠️  Driver `{node.external_driver}` is not in `FitEngine.DRIVER_WEIGHTS`; "
                f"fit scoring will fall back to defaults for this node."
            )
            lines.append("")
    return "\n".join(lines)


def _narrative_spot_checks() -> str:
    """Materialize three canonical paths so reviewers can sanity-check the
    engine's projections against their own industry intuition.
    """
    sim = fresh_simulator()
    paths = {
        "Optimistic (Embrace NDC → Build AI → Become Platform)": {
            "tp-001": "tp-001-a", "tp-002": "tp-002-a", "tp-003": "tp-003-b",
        },
        "Pessimistic (Resist NDC → Wait and See → Consolidate/Exit)": {
            "tp-001": "tp-001-b", "tp-002": "tp-002-c", "tp-003": "tp-003-c",
        },
        "Middle path (Embrace NDC → Partner AI → Pivot Complex)": {
            "tp-001": "tp-001-a", "tp-002": "tp-002-b", "tp-003": "tp-003-a",
        },
    }
    lines = ["## Narrative Spot-Checks — Materialized Paths", ""]
    lines.append("For each canonical branch path, the 2040 endpoint metrics are:")
    lines.append("")
    lines.append("| Path | 2040 revenue idx | 2040 market share | 2040 tech adoption |")
    lines.append("|---|---:|---:|---:|")
    for label, choices in paths.items():
        result = sim.run(choices)
        final = result.projected_timeline[-1].metrics
        lines.append(
            f"| {label} | {final.revenue_index:.2f} | "
            f"{final.market_share:.2%} | {final.tech_adoption_velocity:.2%} |"
        )
    lines.append("")
    lines.append(
        "These endpoints should rank pessimistic < middle < optimistic on revenue. "
        "If they don't, either the branch deltas or the fit-engine weightings need "
        "to be re-examined."
    )
    lines.append("")
    return "\n".join(lines)


def _backtest_section() -> str:
    sim = fresh_simulator()
    bt = sim.backtest(historical_cutoff=2025)
    lines = ["## Historical Backtest (1990–2025)", ""]
    lines.append(f"- Data points compared: **{bt.data_points_compared}**")
    lines.append("- Mean absolute error vs. baseline timeline:")
    for k, v in bt.mean_absolute_error.items():
        lines.append(f"  - `{k}`: {v}")
    lines.append("")
    return "\n".join(lines)


def build_report(
    wargame: tuple[unittest.TestResult, str],
    turning: tuple[unittest.TestResult, str],
) -> str:
    overall_ok = wargame[0].wasSuccessful() and turning[0].wasSuccessful()
    banner = "PASS — scenario is ready for Phase 5" if overall_ok else "FAIL — fix the issues below before moving on"
    parts = [
        "# Phase 4 — Verification & Feedback Report",
        "",
        f"*Generated:* {date.today().isoformat()}",
        "",
        f"**Overall status:** {banner}",
        "",
        "This report is generated by `tests/run_verification.py` and exercises the "
        "two Phase-4 deliverables defined in `specs/implementation_plan.md`:",
        "",
        "1. **War-gaming tests** — assertions that the simulation engine's behavior "
        "matches the industry narratives around NDC adoption, GenAI breakthroughs, "
        "and airline direct-booking pressure.",
        "2. **Turning-point clarity review** — structural checks that every turning "
        "point is reviewable, plus a human-readable dump of the nodes and branches "
        "for the strategy reviewer.",
        "",
        "## Automated Test Results",
        "",
        _format_result_block("War-gaming suite (`tests.test_wargame`)", *wargame),
        _format_result_block("Turning-points clarity suite (`tests.test_turning_points`)", *turning),
        _backtest_section(),
        _narrative_spot_checks(),
        _turning_point_review(),
        "## Reviewer Checklist",
        "",
        "Please tick each item after reviewing the *Turning Points* section above:",
        "",
        "- [ ] Each turning point's **external driver** matches a real-world force "
        "the strategy team expects to shape OTA economics between 2025 and 2040.",
        "- [ ] Branch **labels** read like decisions a real exec committee would debate.",
        "- [ ] Branch **descriptions** explain *why* the path diverges, not just what happens.",
        "- [ ] **Probabilities** feel right (they sum to 100% — but is the split defensible?).",
        "- [ ] Metric deltas have the **right sign and magnitude** relative to the branch narrative.",
        "- [ ] The 2040 endpoints in *Narrative Spot-Checks* rank in the expected order "
        "(pessimistic < middle < optimistic on revenue).",
        "",
        "Any unchecked items should be fed back into `src/engine/schema.py::build_sample_scenario` "
        "before Phase 5 adds the conversational revision layer on top.",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    print("Running Phase 4 verification suites...")
    wargame = _run_suite("tests.test_wargame")
    turning = _run_suite("tests.test_turning_points")

    report = build_report(wargame, turning)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)

    wargame_ok = wargame[0].wasSuccessful()
    turning_ok = turning[0].wasSuccessful()
    print(f"  war-gaming:      {'PASS' if wargame_ok else 'FAIL'} ({wargame[0].testsRun} tests)")
    print(f"  turning-points:  {'PASS' if turning_ok else 'FAIL'} ({turning[0].testsRun} tests)")
    print(f"  report written:  {REPORT_PATH.relative_to(PROJECT_ROOT)}")
    return 0 if (wargame_ok and turning_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
