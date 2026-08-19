from __future__ import annotations

import unittest

try:
    from fastapi import HTTPException
    from incidentlab.api import InvestigationRequest, deterministic_baseline
except ImportError:
    InvestigationRequest = None  # type: ignore[assignment,misc]


@unittest.skipIf(InvestigationRequest is None, "API dependencies are not installed")
class APITests(unittest.TestCase):
    def test_investigation_resolves_declared_fixture_id(self) -> None:
        response = deterministic_baseline(InvestigationRequest(incident_id="checkout-latency-001"))
        self.assertEqual(response["incident_id"], "checkout-latency-001")

    def test_unknown_incident_is_404(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            deterministic_baseline(InvestigationRequest(incident_id="missing"))
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
