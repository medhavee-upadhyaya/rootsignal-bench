from __future__ import annotations

import unittest

from incidentlab.alertmanager import normalize_alertmanager_webhook


class AlertmanagerTests(unittest.TestCase):
    def test_normalizes_alert_group_into_idempotent_live_workflow(self) -> None:
        payload = {
            "receiver": "platform-oncall",
            "status": "firing",
            "groupLabels": {"service": "checkout"},
            "commonLabels": {"alertname": "CheckoutLatencyHigh", "service": "checkout"},
            "commonAnnotations": {
                "summary": "Checkout latency is high",
                "description": "p95 exceeded two seconds after the latest release",
            },
            "externalURL": "https://alerts.example.test",
            "alerts": [{
                "status": "firing",
                "labels": {"service": "checkout", "version": "1.8.3"},
                "annotations": {"runbook_url": "https://runbooks.example.test/checkout"},
                "startsAt": "2026-10-03T12:00:00Z",
                "generatorURL": "https://prometheus.example.test/graph",
                "fingerprint": "abc123",
            }],
        }

        first = normalize_alertmanager_webhook(payload)
        second = normalize_alertmanager_webhook(payload)
        self.assertEqual(first["workflow_id"], second["workflow_id"])
        self.assertEqual(first["intake"]["id"], second["intake"]["id"])
        self.assertEqual(first["intake"]["telemetry"]["metrics"]["firing_alerts"], 1)
        self.assertIn("1.8.3", first["intake"]["telemetry"]["deployments"][0])
        self.assertEqual(len(first["intake"]["telemetry"]["logs"]), 2)

        changed = {**payload, "status": "resolved"}
        self.assertNotEqual(
            first["workflow_id"], normalize_alertmanager_webhook(changed)["workflow_id"]
        )

    def test_rejects_missing_or_malformed_alerts(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one alert"):
            normalize_alertmanager_webhook({"alerts": []})
        with self.assertRaisesRegex(ValueError, "must be an object"):
            normalize_alertmanager_webhook({"alerts": ["not-an-alert"]})
        with self.assertRaisesRegex(ValueError, "more than 100"):
            normalize_alertmanager_webhook({"alerts": [{}] * 101})


if __name__ == "__main__":
    unittest.main()
