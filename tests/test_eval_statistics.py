from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evals.compare import load_metric
from evals.statistics import bootstrap_mean_ci, paired_comparison


class EvaluationStatisticsTests(unittest.TestCase):
    def test_bootstrap_interval_is_deterministic_and_contains_mean(self) -> None:
        first = bootstrap_mean_ci([0.2, 0.4, 0.8, 1.0], samples=500, seed=9)
        second = bootstrap_mean_ci([0.2, 0.4, 0.8, 1.0], samples=500, seed=9)
        self.assertEqual(first, second)
        self.assertLessEqual(first.lower, first.mean)
        self.assertGreaterEqual(first.upper, first.mean)

    def test_paired_comparison_preserves_incident_identity(self) -> None:
        result = paired_comparison(
            {"a": 0.4, "b": 0.6, "c": 0.5},
            {"a": 0.5, "b": 0.6, "c": 0.8},
            samples=500,
        )
        self.assertEqual(result["wins"], 2)
        self.assertEqual(result["ties"], 1)
        self.assertEqual(result["losses"], 0)
        self.assertAlmostEqual(result["mean_delta"]["mean"], 0.133333, places=6)

    def test_mismatched_incidents_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "incident sets differ"):
            paired_comparison({"a": 0.5}, {"b": 0.5}, samples=100)

    def test_loader_requires_scorecard_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "3",
                        "incidents": [{"incident_id": "a", "overall": 0.7}],
                    }
                ),
                encoding="utf-8",
            )
            values, _ = load_metric(path, "overall")
            self.assertEqual(values, {"a": 0.7})


if __name__ == "__main__":
    unittest.main()
