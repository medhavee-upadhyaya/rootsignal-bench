from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from incidentlab.fixtures import load_incident
from incidentlab.tools import TOOL_SCHEMAS


def _examples(fixtures: Path) -> list[dict[str, object]]:
    examples = []
    for path in sorted([*fixtures.glob("*.yaml"), *fixtures.glob("*.json")]):
        incident = load_incident(path)
        for tool_name in incident.oracle["expected_tools"]:
            examples.append(
                {
                    "messages": [
                        {
                            "role": "system",
                            "content": "Select the next diagnostic tool. Return one JSON tool call only.",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"incident": incident.summary, "tools": TOOL_SCHEMAS}, sort_keys=True
                            ),
                        },
                        {"role": "assistant", "content": json.dumps({"name": tool_name, "arguments": {}})},
                    ],
                    "metadata": {"incident_id": incident.incident_id, "target_tool": tool_name},
                }
            )
    return examples


def _write(examples: list[dict[str, object]], output: Path) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(example, sort_keys=True) + "\n" for example in examples)
    output.write_text(payload, encoding="utf-8")
    return {"examples": len(examples), "sha256": hashlib.sha256(payload.encode()).hexdigest(), "path": output.name}


def build(fixtures: Path, output: Path) -> dict[str, object]:
    result = _write(_examples(fixtures), output)
    return {**result, "output": str(output)}


def build_splits(
    fixtures: Path, output_dir: Path, eval_fraction: float = 0.2, seed: int = 17
) -> dict[str, object]:
    if not 0 < eval_fraction < 1:
        raise ValueError("eval_fraction must be between 0 and 1")
    examples = _examples(fixtures)
    incident_ids = sorted({str(example["metadata"]["incident_id"]) for example in examples})  # type: ignore[index]
    if len(incident_ids) < 2:
        raise ValueError("At least two incident templates are required for an isolated split")
    shuffled = incident_ids[:]
    random.Random(seed).shuffle(shuffled)
    eval_count = max(1, min(len(shuffled) - 1, round(len(shuffled) * eval_fraction)))
    eval_ids = set(shuffled[:eval_count])
    train = [example for example in examples if example["metadata"]["incident_id"] not in eval_ids]  # type: ignore[index]
    evaluation = [example for example in examples if example["metadata"]["incident_id"] in eval_ids]  # type: ignore[index]
    output_dir.mkdir(parents=True, exist_ok=True)
    train_result = _write(train, output_dir / "train.jsonl")
    eval_result = _write(evaluation, output_dir / "eval.jsonl")
    source_digest = hashlib.sha256()
    for path in sorted([*fixtures.glob("*.yaml"), *fixtures.glob("*.json")]):
        source_digest.update(path.name.encode())
        source_digest.update(path.read_bytes())
    manifest = {
        "schema_version": "2",
        "seed": seed,
        "eval_fraction": eval_fraction,
        "source_sha256": source_digest.hexdigest(),
        "split_unit": "incident_template",
        "train": {**train_result, "incident_ids": sorted(set(incident_ids) - eval_ids)},
        "eval": {**eval_result, "incident_ids": sorted(eval_ids)},
        "incident_overlap": False,
    }
    (output_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path)
    destination.add_argument("--output-dir", type=Path)
    parser.add_argument("--eval-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()
    result = (
        build_splits(args.fixtures, args.output_dir, args.eval_fraction, args.seed)
        if args.output_dir
        else build(args.fixtures, args.output)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
