from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from incidentlab.custom_incidents import CustomIncidentStore


class CustomIncidentStoreTests(unittest.TestCase):
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
