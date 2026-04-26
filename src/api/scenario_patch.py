"""Apply structured diffs to scenario JSON (Phase 8 / FR-5).

The `/revise` endpoint asks Claude to translate a natural-language revision
into a structured patch via the `apply_scenario_diff` tool. This module
validates and applies those patches.

Supported operations:
  - set_node_field   {node_id, field, value}
  - set_branch_field {node_id, branch_id, field, value}
  - add_branch       {node_id, branch}
  - add_node         {node}
  - expand_scenario  {new_node, rewire_branches: [{node_id, branch_id}, ...],
                      source_question}   — Phase 8

Every patch is validated against an allowlist of mutable fields before it can
touch the scenarios list. IDs, `next_node_id` edges, and the timeline itself
are not patchable — those require a deliberate code change, not an LLM diff.
The ``expand_scenario`` op is the sole exception: it *does* rewire
``next_node_id`` on the targeted branches, because wiring terminal branches
into a newly-appended node is the whole point of the operation. The rewire is
validated to only touch terminal branches so an expansion can never silently
detach a mid-scenario edge.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Drivers the FitEngine knows how to score. New nodes minted via `/expand`
# must carry one of these so narrative consistency tests keep passing —
# otherwise `test_external_drivers_are_handled_by_fit_engine` would go red.
KNOWN_EXTERNAL_DRIVERS = frozenset({
    "NDC adoption",
    "GenAI breakthrough",
    "Airline direct booking dominance",
})


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
    if op not in {
        "set_node_field",
        "set_branch_field",
        "add_branch",
        "add_node",
        "expand_scenario",
    }:
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
    elif op == "expand_scenario":
        _expand_scenario(target, diff)


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


def _expand_scenario(scenario: Dict[str, Any], diff: Dict[str, Any]) -> None:
    """Add a new turning-point node AND rewire the listed terminal branches
    into it, atomically.

    Expected diff shape::

        {
            "op": "expand_scenario",
            "scenario_id": "...",
            "source_question": "...",        # the user's NL question
            "new_node": { ...TurningPointNode JSON... },
            "rewire_branches": [
                {"node_id": "tp-003", "branch_id": "tp-003-a"},
                ...
            ]
        }

    Constraints enforced here (any violation raises ``DiffError``):
      * ``new_node.external_driver`` must be in ``KNOWN_EXTERNAL_DRIVERS`` —
        the FitEngine only has weights for that short list.
      * ``new_node.year`` must be strictly after every existing node's year
        (expansion appends to the scenario line; it never inserts).
      * Every ``rewire_branches`` entry must reference an existing branch
        whose current ``next_node_id`` is null (i.e. terminal). Rewiring a
        mid-graph edge is out of scope — that would silently detach
        downstream structure and is better done via ``/revise`` by hand.
      * All new branches default to ``next_node_id: null`` (they become the
        new terminal frontier) unless the caller explicitly supplies one.
    """
    node = _require(diff, "new_node")
    rewires = diff.get("rewire_branches") or []
    source_question = diff.get("source_question") or ""

    if not isinstance(node, dict):
        raise DiffError("`new_node` must be an object")
    for req in ("id", "year", "title", "description", "external_driver", "branches"):
        if req not in node:
            raise DiffError(f"Expansion node missing required field: {req!r}")
    if not isinstance(node["branches"], list) or len(node["branches"]) < 2:
        raise DiffError("Expansion node must carry at least two branches (a real decision)")
    if node["external_driver"] not in KNOWN_EXTERNAL_DRIVERS:
        raise DiffError(
            f"external_driver {node['external_driver']!r} is not in the FitEngine's "
            f"known set {sorted(KNOWN_EXTERNAL_DRIVERS)} — pick the closest match."
        )

    existing_ids = {n["id"] for n in scenario["nodes"]}
    if node["id"] in existing_ids:
        raise DiffError(f"Expansion node id {node['id']!r} already exists")

    max_year = max((n.get("year", 0) for n in scenario["nodes"]), default=0)
    try:
        new_year = int(node["year"])
    except (TypeError, ValueError):
        raise DiffError(f"Expansion node year must be an integer, got {node['year']!r}")
    if new_year <= max_year:
        raise DiffError(
            f"Expansion year {new_year} must be strictly after the latest "
            f"existing turning point ({max_year}). Expansions append; they don't insert."
        )
    if new_year > 2040:
        raise DiffError(f"Expansion year {new_year} is past the 2040 horizon of the timeline")

    # Validate branches — reuse the add_branch field schema.
    seen_branch_ids = set()
    for b in node["branches"]:
        for req in ("id", "label", "description", "metric_delta", "probability"):
            if req not in b:
                raise DiffError(f"Expansion branch missing required field: {req!r}")
        if b["id"] in seen_branch_ids:
            raise DiffError(f"Duplicate branch id within expansion: {b['id']!r}")
        seen_branch_ids.add(b["id"])
        md = b["metric_delta"]
        if not isinstance(md, dict):
            raise DiffError("expansion branch.metric_delta must be an object")
        for k in ("revenue_index", "market_share", "tech_adoption_velocity"):
            if k not in md:
                raise DiffError(f"expansion branch.metric_delta missing {k!r}")
        # Terminal by default: the new node is the new end of the line.
        b.setdefault("next_node_id", None)

    # Validate rewire targets before mutating anything.
    rewire_plan: List[Dict[str, Any]] = []
    for item in rewires:
        if not isinstance(item, dict):
            raise DiffError("rewire_branches entries must be objects")
        rn_id = _require(item, "node_id")
        rb_id = _require(item, "branch_id")
        rn = _find_node(scenario, rn_id)
        rb = next((x for x in rn["branches"] if x["id"] == rb_id), None)
        if rb is None:
            raise DiffError(f"rewire target branch {rb_id!r} not on node {rn_id!r}")
        if rb.get("next_node_id") is not None:
            raise DiffError(
                f"rewire target {rn_id}/{rb_id} already points at "
                f"{rb['next_node_id']!r} — only terminal branches can be rewired."
            )
        rewire_plan.append({"branch_ref": rb})

    # Stamp provenance fields so the UI and downstream consumers can tell
    # expansion-source nodes apart from hand-authored seed nodes.
    node.setdefault("source", "expansion")
    if source_question:
        node["source_question"] = source_question
    node.setdefault(
        "parent_branch_ids",
        [item["branch_id"] for item in rewires],
    )

    scenario["nodes"].append(node)
    for step in rewire_plan:
        step["branch_ref"]["next_node_id"] = node["id"]


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
