"""Apply structured diffs to scenario JSON (Phase 8 / FR-5).

The `/revise` endpoint asks Claude to translate a natural-language revision
into a structured patch via the `apply_scenario_diff` tool. This module
validates and applies those patches.

Supported operations:
  - set_node_field   {node_id, field, value}
  - set_branch_field {node_id, branch_id, field, value}
  - add_branch       {node_id, branch}
  - add_node         {node}

Every patch is validated against an allowlist of mutable fields before it can
touch the scenarios list. IDs, `next_node_id` edges, and the timeline itself
are not patchable — those require a deliberate code change, not an LLM diff.
"""

from __future__ import annotations

from typing import Any, Dict, List


class DiffError(ValueError):
    """Raised when a diff operation is malformed or references unknown entities."""


# Fields Claude is allowed to set. Anything else raises DiffError.
ALLOWED_NODE_FIELDS = {"title", "description", "external_driver", "year"}
ALLOWED_BRANCH_FIELDS = {
    "label",
    "description",
    "probability",
    "metric_delta.revenue_index",
    "metric_delta.market_share",
    "metric_delta.tech_adoption_velocity",
}


def apply_diff(scenarios: List[Dict[str, Any]], diff: Dict[str, Any]) -> None:
    """Apply a single diff op to `scenarios` in place.

    Raises DiffError on invalid / unknown input.
    """
    op = diff.get("op")
    if op not in {"set_node_field", "set_branch_field", "add_branch", "add_node"}:
        raise DiffError(f"Unknown op: {op!r}")

    scenario_id = diff.get("scenario_id", "scenario-001")
    target = next((s for s in scenarios if s.get("id") == scenario_id), None)
    if target is None:
        raise DiffError(f"Unknown scenario_id: {scenario_id!r}")

    if op == "set_node_field":
        _set_node_field(target, diff)
    elif op == "set_branch_field":
        _set_branch_field(target, diff)
    elif op == "add_branch":
        _add_branch(target, diff)
    elif op == "add_node":
        _add_node(target, diff)


def _set_node_field(scenario: Dict[str, Any], diff: Dict[str, Any]) -> None:
    node_id = _require(diff, "node_id")
    field = _require(diff, "field")
    if field not in ALLOWED_NODE_FIELDS:
        raise DiffError(
            f"Field {field!r} not allowed on node; allowed: {sorted(ALLOWED_NODE_FIELDS)}"
        )
    value = diff.get("value")
    node = _find_node(scenario, node_id)
    node[field] = value


def _set_branch_field(scenario: Dict[str, Any], diff: Dict[str, Any]) -> None:
    node_id = _require(diff, "node_id")
    branch_id = _require(diff, "branch_id")
    field = _require(diff, "field")
    if field not in ALLOWED_BRANCH_FIELDS:
        raise DiffError(
            f"Field {field!r} not allowed on branch; allowed: {sorted(ALLOWED_BRANCH_FIELDS)}"
        )
    value = diff.get("value")

    node = _find_node(scenario, node_id)
    branch = next((b for b in node["branches"] if b["id"] == branch_id), None)
    if branch is None:
        raise DiffError(f"Unknown branch_id: {branch_id!r} on node {node_id!r}")

    # Probability bounds
    if field == "probability":
        try:
            p = float(value)
        except (TypeError, ValueError):
            raise DiffError(f"probability must be numeric, got {value!r}")
        if not (0.0 <= p <= 1.0):
            raise DiffError(f"probability must be in [0, 1], got {p}")
        value = p

    # Metric delta fields live under metric_delta.*; split on the dot.
    if "." in field:
        top, sub = field.split(".", 1)
        branch.setdefault(top, {})[sub] = value
    else:
        branch[field] = value


def _add_branch(scenario: Dict[str, Any], diff: Dict[str, Any]) -> None:
    node_id = _require(diff, "node_id")
    branch = _require(diff, "branch")
    if not isinstance(branch, dict):
        raise DiffError("`branch` must be an object")
    for req in ("id", "label", "description", "metric_delta", "probability"):
        if req not in branch:
            raise DiffError(f"New branch missing required field: {req!r}")
    md = branch["metric_delta"]
    if not isinstance(md, dict):
        raise DiffError("`branch.metric_delta` must be an object")
    for req in ("revenue_index", "market_share", "tech_adoption_velocity"):
        if req not in md:
            raise DiffError(f"New branch.metric_delta missing: {req!r}")

    node = _find_node(scenario, node_id)
    if any(b["id"] == branch["id"] for b in node["branches"]):
        raise DiffError(f"Branch id {branch['id']!r} already exists on {node_id!r}")
    node["branches"].append(branch)


def _add_node(scenario: Dict[str, Any], diff: Dict[str, Any]) -> None:
    node = _require(diff, "node")
    if not isinstance(node, dict):
        raise DiffError("`node` must be an object")
    for req in ("id", "year", "title", "description", "external_driver", "branches"):
        if req not in node:
            raise DiffError(f"New node missing required field: {req!r}")
    if not isinstance(node["branches"], list) or not node["branches"]:
        raise DiffError("new node must carry at least one branch")
    if any(n["id"] == node["id"] for n in scenario["nodes"]):
        raise DiffError(f"Node id {node['id']!r} already exists")
    scenario["nodes"].append(node)


# -------- helpers ----------------------------------------------------------


def _require(diff: Dict[str, Any], key: str) -> Any:
    if key not in diff or diff[key] in (None, ""):
        raise DiffError(f"Missing required field: {key!r}")
    return diff[key]


def _find_node(scenario: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    node = next((n for n in scenario["nodes"] if n["id"] == node_id), None)
    if node is None:
        raise DiffError(f"Unknown node_id: {node_id!r}")
    return node
