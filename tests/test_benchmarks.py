from __future__ import annotations

import unittest

from benchmarks.compare import compare_points
from benchmarks.inference import Sample, build_report, evaluate_slo, parse_sse


class Clock:
    def __init__(self, values: list[float]) -> None:
        self.values = iter(values)

    def __call__(self) -> float:
        return next(self.values)


class InferenceBenchmarkTests(unittest.TestCase):
    def test_stream_parser_measures_first_token_and_usage(self) -> None:
        lines = [
            b'data: {"choices":[{"delta":{"content":"hello"}}]}\n',
            b'data: {"choices":[],"usage":{"completion_tokens":7}}\n',
            b"data: [DONE]\n",
        ]
        sample = parse_sse(lines, 10.0, Clock([10.2, 11.0]))
        self.assertTrue(sample.ok)
        self.assertAlmostEqual(sample.ttft_ms or 0, 200)
        self.assertAlmostEqual(sample.latency_ms, 1000)
        self.assertEqual(sample.output_tokens, 7)

    def test_report_excludes_failures_from_latency(self) -> None:
        samples = [
            Sample(100, 20, 10, True),
            Sample(200, 40, 20, True),
            Sample(5, None, 0, False, "timeout"),
        ]
        report = build_report(samples, 2.0, 2, {"model": "test"})
        self.assertEqual(report["success_rate"], 0.6667)
        self.assertEqual(report["output_throughput_tokens_per_second"], 15.0)
        self.assertEqual(report["latency_ms"]["p95"], 200)
        self.assertEqual(len(report["errors"]), 1)

    def test_slo_is_an_enforced_conjunction(self) -> None:
        report = build_report([Sample(900, 100, 4, True)], 1.0, 1, {})
        self.assertTrue(evaluate_slo(report, 1000, 200, 1.0)["passed"])
        self.assertFalse(evaluate_slo(report, 800, 200, 1.0)["passed"])

    def test_comparison_reports_directional_changes(self) -> None:
        baseline = {
            "latency_ms": {"p95": 100}, "ttft_ms": {"p95": 50},
            "output_throughput_tokens_per_second": 20, "success_rate": 0.9,
        }
        candidate = {
            "latency_ms": {"p95": 80}, "ttft_ms": {"p95": 40},
            "output_throughput_tokens_per_second": 30, "success_rate": 1.0,
        }
        result = compare_points(baseline, candidate)
        self.assertEqual(result["latency_p95_change_percent"], -20.0)
        self.assertEqual(result["token_throughput_change_percent"], 50.0)
        self.assertEqual(result["success_rate_change"], 0.1)


if __name__ == "__main__":
    unittest.main()
