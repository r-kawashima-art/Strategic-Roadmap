"""Phase 10 — Scenario and Data Management (FR-7).

Asserts the non-destructive-edit invariant and the export / import round-trip
contract from `specs/implementation_plan.md` §§10.1, 10.4:

  * Editing any existing scenario produces a NEW entry whose `parent_id`
    points to the source; the source row in `data/scenarios.json` is never
    mutated.
  * `PUT /scenarios/{id}` is metadata-only — payloads carrying `nodes`,
    `timeline`, `metrics`, etc. are rejected.
  * Base scenarios cannot be renamed (HTTP 403) or deleted (HTTP 403).
  * Deleting a user scenario does NOT cascade to children — orphan pointers
    are preserved so the planner's edit history survives a single bad delete.
  * Export → import round-trips a self-contained `.scenario.json` with no
    data loss; the import lands in the `user` array with a fresh `id`.
  * Duplicate-name imports surface as HTTP 409 with a `suggested_name`.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Set bearer auth env BEFORE importing the server module — `load_dotenv()`
# inside server.py would otherwise leave ROADMAP_API_KEY at whatever the
# developer's local .env has, which can drift from this test's expectation.
os.environ["ROADMAP_API_KEY"] = "test-bearer"


def _fixture_payload() -> dict:
    """One base + two user scenarios (B is a child of A)."""
    return {
        "base": [
            {
                "id": "scenario-001",
                "name": "Base scenario",
                "description": "fixture base",
                "timeline": [],
                "nodes": [],
                "metrics": {},
            }
        ],
        "user": [
            {
                "id": "user-aaa",
                "name": "Variant A",
                "description": "",
                "parent_id": "scenario-001",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "timeline": [],
                "nodes": [],
                "metrics": {},
            },
            {
                "id": "user-bbb",
                "name": "Variant B (child of A)",
                "description": "",
                "parent_id": "user-aaa",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "timeline": [],
                "nodes": [],
                "metrics": {},
            },
        ],
    }


class ScenarioManagementTests(unittest.TestCase):
    """End-to-end FastAPI tests covering Phase 10 endpoints."""

    def setUp(self) -> None:
        # Late imports — keeps the test file importable without FastAPI when
        # only the war-gaming suite is being run in isolation.
        from fastapi.testclient import TestClient

        from src.api import server

        self._server = server

        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        )
        json.dump(_fixture_payload(), self.tmp)
        self.tmp.close()

        # Redirect the server's scenario file to the fixture for the test
        # duration. SCENARIOS_PATH is a module-global Path, and every CRUD
        # endpoint reads it through _load_scenarios / _save_scenarios at
        # request time, so a single patch covers them all.
        self._patch = patch.object(server, "SCENARIOS_PATH", Path(self.tmp.name))
        self._patch.start()

        self.client = TestClient(server.app)
        self.bearer = {"Authorization": "Bearer test-bearer"}

    def tearDown(self) -> None:
        self._patch.stop()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _read_disk(self) -> dict:
        return json.loads(Path(self.tmp.name).read_text(encoding="utf-8"))

    # ── §10.4 — non-destructive edit semantics ─────────────────────────────

    def test_put_rejects_graph_keys(self) -> None:
        r = self.client.put(
            "/scenarios/user-aaa",
            json={"name": "x", "nodes": [{"id": "tp-x"}]},
            headers=self.bearer,
        )
        # FastAPI's `extra: forbid` short-circuits to 422 before our explicit
        # 400 guard fires. Either response satisfies the §10.4 contract:
        # "PUT rejects payloads containing nodes/timeline/metrics keys".
        self.assertIn(
            r.status_code, (400, 422),
            f"expected 400/422, got {r.status_code}: {r.text}",
        )
        # The original scenario must not have been mutated.
        on_disk = next(s for s in self._read_disk()["user"] if s["id"] == "user-aaa")
        self.assertEqual(on_disk["name"], "Variant A")
        self.assertEqual(on_disk["nodes"], [])

    def test_put_metadata_only_succeeds(self) -> None:
        r = self.client.put(
            "/scenarios/user-aaa",
            json={"name": "Variant A renamed", "description": "renamed in test"},
            headers=self.bearer,
        )
        self.assertEqual(r.status_code, 200, r.text)
        on_disk = next(s for s in self._read_disk()["user"] if s["id"] == "user-aaa")
        self.assertEqual(on_disk["name"], "Variant A renamed")
        self.assertEqual(on_disk["description"], "renamed in test")
        # Graph keys untouched.
        self.assertEqual(on_disk["nodes"], [])
        self.assertEqual(on_disk["timeline"], [])

    def test_put_on_base_returns_403(self) -> None:
        r = self.client.put(
            "/scenarios/scenario-001",
            json={"name": "should fail"},
            headers=self.bearer,
        )
        self.assertEqual(r.status_code, 403)

    def test_post_save_creates_variant_with_parent_id(self) -> None:
        seed = {
            "name": "New variant",
            "parent_id": "scenario-001",
            "scenario_data": {
                "description": "",
                "timeline": [],
                "nodes": [],
                "metrics": {},
            },
        }
        r = self.client.post("/scenarios", json=seed, headers=self.bearer)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["id"].startswith("user-"))
        self.assertEqual(body["parent_id"], "scenario-001")
        # The base scenario row must remain byte-for-byte intact.
        disk = self._read_disk()
        original_base = next(s for s in disk["base"] if s["id"] == "scenario-001")
        self.assertEqual(original_base["name"], "Base scenario")

    def test_delete_does_not_cascade_to_children(self) -> None:
        # user-bbb has parent_id == user-aaa. Deleting user-aaa must NOT
        # remove user-bbb; the orphan pointer is preserved so the UI can
        # surface a "(deleted parent)" annotation.
        r = self.client.delete("/scenarios/user-aaa", headers=self.bearer)
        self.assertEqual(r.status_code, 204)
        disk = self._read_disk()
        ids = [s["id"] for s in disk["user"]]
        self.assertNotIn("user-aaa", ids)
        self.assertIn("user-bbb", ids)
        b = next(s for s in disk["user"] if s["id"] == "user-bbb")
        self.assertEqual(
            b["parent_id"], "user-aaa",
            "Orphan parent_id pointer must survive a parent delete",
        )

    def test_delete_on_base_returns_403(self) -> None:
        r = self.client.delete("/scenarios/scenario-001", headers=self.bearer)
        self.assertEqual(r.status_code, 403)
        # And the file is unchanged.
        disk = self._read_disk()
        self.assertTrue(any(s["id"] == "scenario-001" for s in disk["base"]))

    # ── §10.1 — export / import round-trip ─────────────────────────────────

    def test_export_returns_self_contained_attachment(self) -> None:
        r = self.client.get("/scenarios/scenario-001/export", headers=self.bearer)
        self.assertEqual(r.status_code, 200)
        cd = r.headers.get("content-disposition", "")
        self.assertIn("attachment", cd)
        self.assertIn(".scenario.json", cd)
        body = r.json()
        for required in ("id", "name", "nodes", "timeline"):
            self.assertIn(required, body)

    def test_import_round_trips_with_fresh_id(self) -> None:
        export = self.client.get(
            "/scenarios/user-aaa/export", headers=self.bearer,
        )
        self.assertEqual(export.status_code, 200)
        payload = export.json()
        # Rename so the import doesn't 409 on duplicate name.
        payload["name"] = "Variant A (round-tripped)"
        files = {
            "file": (
                "variant.scenario.json",
                json.dumps(payload),
                "application/json",
            ),
        }
        r = self.client.post(
            "/scenarios/import", files=files, headers=self.bearer,
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertNotEqual(body["id"], "user-aaa", "import must mint a fresh id")
        self.assertEqual(body["source"], "user")

        ids = [s["id"] for s in self._read_disk()["user"]]
        self.assertIn("user-aaa", ids, "original survives the import")
        self.assertIn(body["id"], ids, "new entry persisted")

    def test_import_rejects_duplicate_name_with_suggestion(self) -> None:
        files = {
            "file": (
                "dup.scenario.json",
                json.dumps({
                    "id": "irrelevant",
                    "name": "Variant A",  # collides with user-aaa
                    "timeline": [],
                    "nodes": [],
                    "metrics": {},
                }),
                "application/json",
            ),
        }
        r = self.client.post("/scenarios/import", files=files, headers=self.bearer)
        self.assertEqual(r.status_code, 409)
        detail = r.json().get("detail")
        self.assertIsInstance(detail, dict)
        self.assertIn("suggested_name", detail)
        self.assertEqual(detail["suggested_name"], "Variant A (2)")


# ── Phase 10.6 — Turning Point Expansion Save Function ───────────────────


def _expandable_fixture() -> dict:
    """Fixture with terminal branches so /expand has something to rewire.

    Mirrors the smallest valid shape `_expand_scenario` accepts: one base
    scenario, one turning point (tp-001), two terminal branches.
    """
    return {
        "base": [
            {
                "id": "scenario-001",
                "name": "Base for expand",
                "description": "fixture for /expand tests",
                "timeline": [],
                "metrics": {},
                "nodes": [
                    {
                        "id": "tp-001",
                        "year": 2025,
                        "title": "NDC adoption",
                        "description": "",
                        "external_driver": "NDC adoption",
                        "branches": [
                            {
                                "id": "tp-001-a", "label": "Embrace",
                                "description": "", "probability": 0.6,
                                "next_node_id": None,
                                "metric_delta": {"revenue_index": 0.10,
                                                 "market_share": 0.02,
                                                 "tech_adoption_velocity": 0.05},
                            },
                            {
                                "id": "tp-001-b", "label": "Resist",
                                "description": "", "probability": 0.4,
                                "next_node_id": None,
                                "metric_delta": {"revenue_index": -0.05,
                                                 "market_share": -0.01,
                                                 "tech_adoption_velocity": -0.02},
                            },
                        ],
                    }
                ],
            }
        ],
        "user": [],
    }


class ExpandSaveSemanticsTests(unittest.TestCase):
    """Phase 10.6 — /expand is a non-destructive preview.

    The endpoint historically wrote the entire scenarios array back to
    `data/scenarios.json` before the user accepted, leaving "Reject" as a
    UI-only no-op. This suite locks in the new contract:

      * /expand returns ``status: "preview"`` and a ``preview_scenario``.
      * The on-disk file is byte-identical before and after the call.
      * Saving the preview via POST /scenarios produces a NEW user variant
        whose ``parent_id`` points at the source, leaving the source
        scenario row untouched (Phase 10.4 invariant).
    """

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from src.api import server

        self._server = server

        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8",
        )
        json.dump(_expandable_fixture(), self.tmp)
        self.tmp.close()

        self._patch = patch.object(server, "SCENARIOS_PATH", Path(self.tmp.name))
        self._patch.start()

        self.client = TestClient(server.app)
        self.bearer = {"Authorization": "Bearer test-bearer"}

    def tearDown(self) -> None:
        self._patch.stop()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _read_disk_bytes(self) -> bytes:
        return Path(self.tmp.name).read_bytes()

    def _fake_expand_response(self) -> object:
        """Build a stand-in for `client.messages.create()` returning a tool_use
        block that satisfies `_expand_scenario`'s validation contract."""
        from unittest.mock import MagicMock

        block = MagicMock()
        block.type = "tool_use"
        block.input = {
            "summary": "EU AI Act tightens, OTAs decide whether to comply",
            "new_node": {
                "id": "tp-002",
                "year": 2030,
                "title": "EU AI regulation",
                "description": "EU AI Act tightens",
                "external_driver": "GenAI breakthrough",
                "branches": [
                    {
                        "id": "tp-002-a", "label": "Comply",
                        "description": "", "probability": 0.6,
                        "metric_delta": {"revenue_index": 0.05,
                                         "market_share": 0.01,
                                         "tech_adoption_velocity": 0.02},
                    },
                    {
                        "id": "tp-002-b", "label": "Localise",
                        "description": "", "probability": 0.4,
                        "metric_delta": {"revenue_index": -0.05,
                                         "market_share": -0.01,
                                         "tech_adoption_velocity": -0.02},
                    },
                ],
            },
            "rewire_branches": [
                {"node_id": "tp-001", "branch_id": "tp-001-a"},
                {"node_id": "tp-001", "branch_id": "tp-001-b"},
            ],
        }
        response = MagicMock()
        response.content = [block]
        response.usage = MagicMock(
            input_tokens=1, output_tokens=1,
            cache_read_input_tokens=0, cache_creation_input_tokens=0,
        )
        return response

    def _patched_claude_client(self) -> object:
        """Return an AsyncMock-backed client compatible with `await
        client.messages.create(...)`."""
        from unittest.mock import AsyncMock, MagicMock

        client = MagicMock()
        client.messages = MagicMock()
        client.messages.create = AsyncMock(return_value=self._fake_expand_response())
        return client

    # ── Tests ──────────────────────────────────────────────────────────────

    def test_expand_returns_preview_without_writing_disk(self) -> None:
        before = self._read_disk_bytes()
        with patch.object(
            self._server, "_get_claude_client",
            return_value=self._patched_claude_client(),
        ):
            r = self.client.post(
                "/expand",
                json={"scenario_id": "scenario-001",
                      "question": "What if EU passes strict AI rules in 2030?"},
                headers=self.bearer,
            )
        after = self._read_disk_bytes()

        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["status"], "preview")
        self.assertIn("preview_scenario", body)
        self.assertNotIn("scenarios", body,
                         "destructive 'scenarios' array must NOT be in /expand response")
        # The disk file is byte-identical — Phase 10.6 non-destructive contract.
        self.assertEqual(before, after,
                         "/expand must not mutate data/scenarios.json")

    def test_expand_preview_contains_new_node(self) -> None:
        with patch.object(
            self._server, "_get_claude_client",
            return_value=self._patched_claude_client(),
        ):
            r = self.client.post(
                "/expand",
                json={"scenario_id": "scenario-001", "question": "what if?"},
                headers=self.bearer,
            )
        self.assertEqual(r.status_code, 200, r.text)
        preview = r.json()["preview_scenario"]
        node_ids = [n["id"] for n in preview["nodes"]]
        self.assertIn("tp-001", node_ids, "source node must survive in preview")
        self.assertIn("tp-002", node_ids, "new TP must appear in preview")
        # Terminal branches on tp-001 are now wired into tp-002.
        tp001 = next(n for n in preview["nodes"] if n["id"] == "tp-001")
        for b in tp001["branches"]:
            self.assertEqual(b["next_node_id"], "tp-002",
                             "rewire must redirect tp-001's terminals into tp-002")

    def test_expand_preview_save_round_trips_as_new_variant(self) -> None:
        # 1. /expand → preview only.
        with patch.object(
            self._server, "_get_claude_client",
            return_value=self._patched_claude_client(),
        ):
            r = self.client.post(
                "/expand",
                json={"scenario_id": "scenario-001", "question": "what if?"},
                headers=self.bearer,
            )
        self.assertEqual(r.status_code, 200)
        preview = r.json()["preview_scenario"]

        # 2. POST /scenarios with parent_id = source — emulates "Save as new".
        save = self.client.post(
            "/scenarios",
            json={
                "name": "Base for expand (expanded)",
                "parent_id": "scenario-001",
                "scenario_data": preview,
            },
            headers=self.bearer,
        )
        self.assertEqual(save.status_code, 200, save.text)
        saved = save.json()
        self.assertTrue(saved["id"].startswith("user-"))
        self.assertEqual(saved["parent_id"], "scenario-001")

        # 3. Source scenario row is intact — only tp-001 still, its branches
        #    still terminal (no in-place mutation from the expand path).
        disk = json.loads(Path(self.tmp.name).read_text(encoding="utf-8"))
        original = next(s for s in disk["base"] if s["id"] == "scenario-001")
        self.assertEqual([n["id"] for n in original["nodes"]], ["tp-001"])
        for b in original["nodes"][0]["branches"]:
            self.assertIsNone(
                b["next_node_id"],
                "source's terminal branches must not be rewired in place",
            )

        # 4. A user variant is now persisted with the expanded graph.
        variants = [s for s in disk["user"] if s["id"] == saved["id"]]
        self.assertEqual(len(variants), 1)
        variant_node_ids = [n["id"] for n in variants[0]["nodes"]]
        self.assertIn("tp-002", variant_node_ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
