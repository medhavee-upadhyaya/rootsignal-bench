from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def directory_sha256(path: Path, exclude: set[str] | None = None) -> str:
    digest = hashlib.sha256()
    excluded = exclude or set()
    for artifact in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = artifact.relative_to(path).as_posix()
        if relative in excluded:
            continue
        digest.update(relative.encode())
        digest.update(artifact.read_bytes())
    return digest.hexdigest()


def validate_dataset_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {
        "schema_supported": manifest.get("schema_version") == "2",
        "split_by_template": manifest.get("split_unit") == "incident_template",
        "overlap_declared_false": manifest.get("incident_overlap") is False,
    }
    train_ids = set(manifest.get("train", {}).get("incident_ids", []))
    eval_ids = set(manifest.get("eval", {}).get("incident_ids", []))
    checks["incident_ids_disjoint"] = bool(train_ids) and bool(eval_ids) and train_ids.isdisjoint(eval_ids)
    for split in ("train", "eval"):
        metadata = manifest.get(split, {})
        artifact = path.parent / str(metadata.get("path", ""))
        checks[f"{split}_exists"] = artifact.is_file()
        checks[f"{split}_digest_valid"] = artifact.is_file() and hashlib.sha256(
            artifact.read_bytes()
        ).hexdigest() == metadata.get("sha256")
        checks[f"{split}_nonempty"] = int(metadata.get("examples", 0)) > 0
    return {"valid": all(checks.values()), "checks": checks, "manifest": str(path)}


def validate_training_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "base_model",
        "base_model_revision",
        "seed",
        "dataset_sha256",
        "config_sha256",
        "train_metrics",
        "eval_metrics",
        "runtime",
        "adapter_sha256",
    }
    checks = {
        "schema_supported": manifest.get("schema_version") == "3",
        "required_fields_present": required.issubset(manifest),
        "template_isolated": manifest.get("split_isolation") == "incident_template",
        "metrics_recorded": bool(manifest.get("train_metrics")) and bool(manifest.get("eval_metrics")),
        "adapter_digest_valid": directory_sha256(path.parent, {path.name})
        == manifest.get("adapter_sha256"),
    }
    return {"valid": all(checks.values()), "checks": checks, "manifest": str(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate reproducible training artifacts")
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument("--training-manifest", type=Path)
    args = parser.parse_args()
    if not args.dataset_manifest and not args.training_manifest:
        parser.error("one manifest is required")
    report = (
        validate_dataset_manifest(args.dataset_manifest)
        if args.dataset_manifest
        else validate_training_manifest(args.training_manifest)
    )
    print(json.dumps(report, indent=2))
    if not report["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
