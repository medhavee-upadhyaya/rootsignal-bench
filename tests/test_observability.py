from __future__ import annotations

import unittest
import json
import logging
from io import StringIO

from incidentlab.observability import Metrics, log_event


class MetricsTests(unittest.TestCase):
    def test_exports_counter_gauge_and_histogram(self) -> None:
        metrics = Metrics()
        with metrics.investigation():
            pass
        payload = metrics.prometheus()
        self.assertIn("rootsignal_investigations_total 1", payload)
        self.assertIn("rootsignal_investigations_active 0", payload)
        self.assertIn("rootsignal_investigation_duration_seconds_bucket", payload)

    def test_exports_bounded_http_and_agent_metrics(self) -> None:
        metrics = Metrics()
        metrics.record_http("get", "/v1/investigations/unsafe-cardinality", 500, 0.25)
        metrics.record_agent_run(
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "retrieved_chunks": 2,
                "agent_steps": 4,
                "model_planned_steps": 3,
                "citation_validity": 0,
            }
        )
        payload = metrics.prometheus()
        self.assertIn('route="other",status_class="5xx"', payload)
        self.assertNotIn("unsafe-cardinality", payload)
        self.assertIn("rootsignal_model_prompt_tokens_total 100", payload)
        self.assertIn("rootsignal_policy_fallback_steps_total 1", payload)
        self.assertIn("rootsignal_invalid_citations_total 1", payload)

    def test_structured_event_is_machine_readable(self) -> None:
        stream = StringIO()
        logger = logging.getLogger("rootsignal.test.observability")
        logger.handlers = [logging.StreamHandler(stream)]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        log_event(logger, "investigation_completed", request_id="req-123", tokens=42)
        event = json.loads(stream.getvalue())
        self.assertEqual(event["event"], "investigation_completed")
        self.assertEqual(event["tokens"], 42)


if __name__ == "__main__":
    unittest.main()
