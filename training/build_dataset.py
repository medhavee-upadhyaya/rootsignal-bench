from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from incidentlab.fixtures import load_incident
from incidentlab.tools import TOOL_SCHEMAS


def build(fixtures: Path, output: Path) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    digest = hashlib.sha256()
    with output.open("w", encoding="utf-8") as target:
        for path in sorted([*fixtures.glob("*.yaml"), *fixtures.glob("*.json")]):
            incident = load_incident(path)
            for tool_name in incident.oracle["expected_tools"]:
                example = {
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
                line = json.dumps(example, sort_keys=True)
                target.write(line + "\n")
                digest.update(line.encode())
                count += 1
    return {"examples": count, "sha256": digest.hexdigest(), "output": str(output)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.fixtures, args.output), indent=2))


if __name__ == "__main__":
    main()
