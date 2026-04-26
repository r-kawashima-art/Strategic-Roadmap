"""Shared test helpers for Phase 4 verification.

Puts `src/engine/` on sys.path so `simulator.py` and `schema.py` can be
imported without a package layout change, and exposes a fresh Scenario
builder plus a canonical Simulator for each test case.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = PROJECT_ROOT / "src" / "engine"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from schema import (  # noqa: E402
    BranchOutcome,
    MatrixPosition,
    MetricSnapshot,
    Scenario,
    StrategicProfile,
    StrategicStance,
    TurningPointNode,
    build_sample_scenario,
)
from simulator import FitEngine, MatrixEngine, Simulator  # noqa: E402


def fresh_scenario() -> Scenario:
    return build_sample_scenario()


def fresh_simulator() -> Simulator:
    return Simulator(build_sample_scenario())


__all__ = [
    "BranchOutcome",
    "FitEngine",
    "MatrixEngine",
    "MatrixPosition",
    "MetricSnapshot",
    "PROJECT_ROOT",
    "Scenario",
    "Simulator",
    "StrategicProfile",
    "StrategicStance",
    "TurningPointNode",
    "fresh_scenario",
    "fresh_simulator",
]
