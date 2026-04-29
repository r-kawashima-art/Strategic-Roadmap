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


if __name__ == "__main__":
    unittest.main(verbosity=2)
