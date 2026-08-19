from __future__ import annotations

import unittest

from incidentlab.observability import Metrics


class MetricsTests(unittest.TestCase):
    def test_exports_counter_gauge_and_histogram(self) -> None:
        metrics = Metrics()
        with metrics.investigation():
            pass
        payload = metrics.prometheus()
        self.assertIn("rootsignal_investigations_total 1", payload)
        self.assertIn("rootsignal_investigations_active 0", payload)
        self.assertIn("rootsignal_investigation_duration_seconds_bucket", payload)


if __name__ == "__main__":
    unittest.main()
