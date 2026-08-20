from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from training.build_dataset import build_splits
from training.compare import compare
from training.validate_artifacts import directory_sha256, validate_dataset_manifest, validate_training_manifest


class TrainingArtifactsTests(unittest.TestCase):
    def test_template_isolated_split_is_reproducible_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = Path(first_dir)
            second = Path(second_dir)
            first_manifest = build_splits(Path("fixtures/incidents"), first, seed=17)
            second_manifest = build_splits(Path("fixtures/incidents"), second, seed=17)
            self.assertEqual(first_manifest, second_manifest)
            self.assertTrue(validate_dataset_manifest(first / "dataset_manifest.json")["valid"])
            self.assertTrue(
                set(first_manifest["train"]["incident_ids"]).isdisjoint(  # type: ignore[index]
                    first_manifest["eval"]["incident_ids"]  # type: ignore[index]
                )
            )

    def test_tampered_dataset_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_splits(Path("fixtures/incidents"), root)
            (root / "train.jsonl").write_text("tampered\n", encoding="utf-8")
            self.assertFalse(validate_dataset_manifest(root / "dataset_manifest.json")["valid"])

    def test_base_adapter_comparison_reports_measured_delta(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.jsonl"
            adapter = root / "adapter.jsonl"
            rows = [
                {"expected_tool": "query_logs", "predicted_tool": "query_metrics", "arguments": {}},
                {"expected_tool": "query_metrics", "predicted_tool": "query_metrics", "arguments": {}},
            ]
            base.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            rows[0]["predicted_tool"] = "query_logs"
            adapter.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            report = compare(base, adapter)
            self.assertEqual(report["delta"]["tool_accuracy"], 0.5)  # type: ignore[index]

    def test_training_manifest_binds_metrics_and_adapter_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "adapter.safetensors").write_bytes(b"adapter-weights")
            manifest = {
                "schema_version": "3",
                "base_model": "example/model",
                "base_model_revision": "abc123",
                "seed": 17,
                "dataset_sha256": "dataset-digest",
                "config_sha256": "config-digest",
                "split_isolation": "incident_template",
                "train_metrics": {"train_loss": 0.4},
                "eval_metrics": {"eval_loss": 0.5},
                "runtime": {"device": "test"},
                "adapter_sha256": directory_sha256(root),
            }
            path = root / "rootsignal_manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(validate_training_manifest(path)["valid"])
            (root / "adapter.safetensors").write_bytes(b"tampered")
            self.assertFalse(validate_training_manifest(path)["valid"])


if __name__ == "__main__":
    unittest.main()
