from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from incidentlab.fixtures import load_incident
from incidentlab.knowledge import KnowledgeBase

STRATEGIES = ("lexical", "semantic", "hybrid", "reranked")


def evaluate(knowledge: KnowledgeBase, incidents: list[object], k: int, strategy: str) -> dict[str, object]:
    rows = []
    for incident in incidents:
        telemetry = json.dumps(incident.telemetry, sort_keys=True)  # type: ignore[attr-defined]
        retrieved = knowledge.search(  # type: ignore[arg-type]
            incident.summary + " " + telemetry, limit=k, strategy=strategy  # type: ignore[attr-defined]
        )
        expected = f"runbook/{incident.runbooks[0]['id']}"  # type: ignore[attr-defined]
        rank = next((index for index, item in enumerate(retrieved, 1) if item.source == expected), None)
        rows.append(
            {
                "incident_id": incident.incident_id,  # type: ignore[attr-defined]
                "expected": expected,
                "retrieved": [item.source for item in retrieved],
                "rank": rank,
                "recall_at_k": float(rank is not None),
                "reciprocal_rank": round(1 / rank, 4) if rank else 0.0,
            }
        )
    return {
        "strategy": strategy,
        "incidents": rows,
        "aggregate": {
            "recall_at_k": round(sum(row["recall_at_k"] for row in rows) / len(rows), 4),
            "mrr": round(sum(row["reciprocal_rank"] for row in rows) / len(rows), 4),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate runbook retrieval on public observations")
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--strategy", choices=STRATEGIES, default="reranked")
    parser.add_argument("--ablation", action="store_true")
    parser.add_argument("--minimum-recall", type=float, default=1.0)
    args = parser.parse_args()
    paths = sorted([*args.fixtures.glob("*.yaml"), *args.fixtures.glob("*.json")])
    with tempfile.TemporaryDirectory() as directory:
        knowledge = KnowledgeBase(Path(directory) / "retrieval.db")
        incidents = [load_incident(path) for path in paths]
        for incident in incidents:
            for runbook in incident.runbooks:
                knowledge.ingest(f"runbook/{runbook['id']}", runbook["content"])
        strategies = STRATEGIES if args.ablation else (args.strategy,)
        results = {strategy: evaluate(knowledge, incidents, args.k, strategy) for strategy in strategies}
    selected = results[args.strategy]
    report: dict[str, object] = {
        "schema_version": "2",
        "k": args.k,
        "selected_strategy": args.strategy,
        **selected,
    }
    if args.ablation:
        report["ablation"] = {name: value["aggregate"] for name, value in results.items()}
    print(json.dumps(report, indent=2))
    if float(selected["aggregate"]["recall_at_k"]) < args.minimum_recall:  # type: ignore[index]
        raise SystemExit(1)


if __name__ == "__main__":
    main()
