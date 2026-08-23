from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evals.validate_fixtures import audit
from incidentlab.fixtures import validate_fixture


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/incidents"


class FixtureIntegrityTests(unittest.TestCase):
    def test_public_fixture_corpus_passes_integrity_audit(self) -> None:
        paths = sorted([*FIXTURES.glob("*.json"), *FIXTURES.glob("*.yaml")])
        report = audit(paths)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["fixture_count"], 26)
        self.assertEqual(len(report["failure_classes"]), 26)
        self.assertEqual(report["difficulties"], {"easy": 6, "hard": 10, "medium": 10})
        self.assertFalse(report["ungrounded_evidence"])
        self.assertFalse(report["unknown_expected_tools"])

    def test_exact_oracle_leak_and_duplicate_observation_are_detected(self) -> None:
        source = json.loads((FIXTURES / "auth_certificate_expiry.json").read_text())
        source["summary"] = source["oracle"]["root_cause"]
        duplicate = json.loads(json.dumps(source))
        duplicate["id"] = "duplicate-incident"
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            first.write_text(json.dumps(source), encoding="utf-8")
            second.write_text(json.dumps(duplicate), encoding="utf-8")
            report = audit([first, second])
        self.assertFalse(report["checks"]["no_exact_oracle_leakage"])
        self.assertFalse(report["checks"]["unique_public_observations"])

    def test_invalid_metadata_is_rejected(self) -> None:
        source = json.loads((FIXTURES / "auth_certificate_expiry.json").read_text())
        source["metadata"]["difficulty"] = "impossible"
        with self.assertRaisesRegex(ValueError, "difficulty"):
            validate_fixture(source)

    def test_ungrounded_evidence_and_unknown_tools_are_detected(self) -> None:
        source = json.loads((FIXTURES / "auth_certificate_expiry.json").read_text())
        source["oracle"]["required_evidence"].append("unobservable-marker-999")
        source["oracle"]["expected_tools"].append("delete_production")
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "invalid.json"
            fixture.write_text(json.dumps(source), encoding="utf-8")
            report = audit([fixture])
        self.assertFalse(report["checks"]["required_evidence_grounded"])
        self.assertFalse(report["checks"]["expected_tools_recognized"])


if __name__ == "__main__":
    unittest.main()
