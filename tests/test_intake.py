from __future__ import annotations

import unittest

from incidentlab.intake import normalize_telemetry_intake


class TelemetryIntakeTests(unittest.TestCase):
    def test_normalizes_nested_structured_observations(self) -> None:
        fixture = normalize_telemetry_intake({
            "id": "checkout-live-001",
            "title": "Checkout latency",
            "summary": "Latency rose after deployment",
            "telemetry": {
                "metrics": {"latency_p95_ms": 2800},
                "logs": [{"level": "error", "message": "timeout"}, "pool wait"],
                "deployments": [{"service": "checkout", "version": "1.8.3"}],
            },
        })
        self.assertEqual(fixture["metadata"]["intake"], "telemetry-api")
        self.assertFalse(fixture["metadata"]["synthetic"])
        self.assertIn('"level": "error"', fixture["telemetry"]["logs"][0])
        self.assertNotIn("oracle", fixture)

    def test_rejects_oracle_and_incomplete_observations(self) -> None:
        with self.assertRaisesRegex(ValueError, "observations only"):
            normalize_telemetry_intake({"oracle": {}, "telemetry": {}})
        with self.assertRaisesRegex(ValueError, "at least 2"):
            normalize_telemetry_intake({
                "telemetry": {"metrics": {"errors": 4}, "logs": ["one"], "deployments": ["v2"]}
            })


if __name__ == "__main__":
    unittest.main()
