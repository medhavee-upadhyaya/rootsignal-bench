from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from incidentlab.custom_incidents import CustomIncidentStore


class CustomIncidentStoreTests(unittest.TestCase):
    def test_existing_database_is_migrated_for_archival(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """
                    CREATE TABLE custom_incidents (
                        incident_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        fixture_sha256 TEXT NOT NULL,
                        fixture_json TEXT NOT NULL
                    )
                    """
                )
            CustomIncidentStore(path)
            with sqlite3.connect(path) as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(custom_incidents)")}
            self.assertIn("archived_at", columns)

    def test_observation_only_incident_persists_without_an_oracle(self) -> None:
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = "live-checkout"
        fixture["metadata"]["synthetic"] = False
        fixture["runbooks"] = []
        fixture.pop("oracle")
        with tempfile.TemporaryDirectory() as directory:
            store = CustomIncidentStore(Path(directory) / "incidents.db")
            store.save(fixture)
            incident = store.get("live-checkout")
            self.assertIsNotNone(incident)
            assert incident is not None
            self.assertIsNone(incident.oracle)
            self.assertEqual(incident.runbooks, [])

    def test_evaluation_incident_still_requires_a_runbook(self) -> None:
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = "evaluation-without-runbook"
        fixture["runbooks"] = []
        with tempfile.TemporaryDirectory() as directory:
            store = CustomIncidentStore(Path(directory) / "incidents.db")
            with self.assertRaisesRegex(ValueError, "requires at least one runbook"):
                store.save(fixture)

    def test_archived_incident_leaves_active_catalog_but_remains_resolvable(self) -> None:
        fixture = json.loads(
            Path("fixtures/incidents/checkout_latency.yaml").read_text(encoding="utf-8")
        )
        fixture["id"] = "archived-checkout"
        with tempfile.TemporaryDirectory() as directory:
            store = CustomIncidentStore(Path(directory) / "incidents.db")
            store.save(fixture)
            archived = store.archive(fixture["id"])
            self.assertEqual(archived["status"], "archived")
            self.assertNotIn(fixture["id"], [item.incident_id for item in store.list()])
            self.assertIsNotNone(store.get(fixture["id"]))
            self.assertIsNone(store.archive(fixture["id"]))

    def test_custom_incident_persists_without_public_oracle_projection(self) -> None:
        fixture = json.loads(Path("fixtures/incidents/checkout_latency.yaml").read_text())
        fixture["id"] = "custom-checkout"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "incidents.db"
            saved = CustomIncidentStore(path).save(fixture)
            reopened = CustomIncidentStore(path)
            incident = reopened.get("custom-checkout")
            self.assertIsNotNone(incident)
            assert incident is not None
            self.assertEqual(incident.oracle["root_cause"], fixture["oracle"]["root_cause"])
            self.assertEqual(len(reopened.digest("custom-checkout") or ""), 64)
            self.assertEqual(saved["incident_id"], "custom-checkout")
            with self.assertRaisesRegex(ValueError, "already exists"):
                reopened.save(fixture)

    def test_unsupported_expected_tool_is_rejected(self) -> None:
        fixture = json.loads(Path("fixtures/incidents/checkout_latency.yaml").read_text())
        fixture["id"] = "custom-unsupported-tool"
        fixture["oracle"]["expected_tools"].append("run_shell")
        with tempfile.TemporaryDirectory() as directory:
            store = CustomIncidentStore(Path(directory) / "incidents.db")
            with self.assertRaisesRegex(ValueError, "Unsupported expected tools"):
                store.save(fixture)


if __name__ == "__main__":
    unittest.main()
