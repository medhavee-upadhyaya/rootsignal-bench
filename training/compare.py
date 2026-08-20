from __future__ import annotations

import argparse
import json
from pathlib import Path


def score_predictions(path: Path) -> dict[str, float | int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError("Prediction file is empty")
    accuracy = sum(row.get("predicted_tool") == row.get("expected_tool") for row in rows) / len(rows)
    validity = sum(isinstance(row.get("arguments"), dict) for row in rows) / len(rows)
    return {"examples": len(rows), "tool_accuracy": round(accuracy, 4), "argument_validity": round(validity, 4)}


def compare(base: Path, adapter: Path) -> dict[str, object]:
    base_metrics = score_predictions(base)
    adapter_metrics = score_predictions(adapter)
    if base_metrics["examples"] != adapter_metrics["examples"]:
        raise ValueError("Base and adapter predictions must cover the same held-out examples")
    return {
        "schema_version": "1",
        "base": base_metrics,
        "adapter": adapter_metrics,
        "delta": {
            "tool_accuracy": round(
                float(adapter_metrics["tool_accuracy"]) - float(base_metrics["tool_accuracy"]), 4
            ),
            "argument_validity": round(
                float(adapter_metrics["argument_validity"])
                - float(base_metrics["argument_validity"]),
                4,
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare base and adapter held-out predictions")
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = compare(args.base, args.adapter)
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
