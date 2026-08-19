from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from incidentlab.fixtures import load_incident
from incidentlab.knowledge import KnowledgeBase


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate runbook retrieval on public observations")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--k", type=int, default=2)
    args = parser.parse_args()
    paths = sorted([*args.fixtures.glob("*.yaml"), *args.fixtures.glob("*.json")])
    with tempfile.TemporaryDirectory() as directory:
        knowledge = KnowledgeBase(Path(directory) / "retrieval.db")
        incidents = [load_incident(path) for path in paths]
        for incident in incidents:
            for runbook in incident.runbooks:
                knowledge.ingest(f"runbook/{runbook['id']}", runbook["content"])
        rows = []
        for incident in incidents:
            telemetry = json.dumps(incident.telemetry, sort_keys=True)
            retrieved = knowledge.search(incident.summary + " " + telemetry, limit=args.k)
            expected = f"runbook/{incident.runbooks[0]['id']}"
            rank = next((index for index, item in enumerate(retrieved, 1) if item.source == expected), None)
            rows.append(
                {
                    "incident_id": incident.incident_id,
                    "expected": expected,
                    "retrieved": [item.source for item in retrieved],
                    "rank": rank,
                    "recall_at_k": float(rank is not None),
                    "reciprocal_rank": round(1 / rank, 4) if rank else 0.0,
                }
            )
    report = {
        "schema_version": "1",
        "k": args.k,
        "incidents": rows,
        "aggregate": {
            "recall_at_k": round(sum(row["recall_at_k"] for row in rows) / len(rows), 4),
            "mrr": round(sum(row["reciprocal_rank"] for row in rows) / len(rows), 4),
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
