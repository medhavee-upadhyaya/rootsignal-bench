from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from .agent import Investigator
from .evaluation import score
from .fixtures import load_incident
from .knowledge import KnowledgeBase

MAX_KNOWLEDGE_FILE_BYTES = 1_000_000


def _read_knowledge_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError("knowledge path must be a readable file")
    if path.stat().st_size > MAX_KNOWLEDGE_FILE_BYTES:
        raise ValueError("knowledge file exceeds the 1 MB limit")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("knowledge file must be UTF-8 text") from exc
    if len(text.strip()) < 20:
        raise ValueError("knowledge file must contain at least 20 characters")
    return text


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="rootsignal")
    subparsers = parser.add_subparsers(dest="command", required=True)
    investigate = subparsers.add_parser("investigate")
    investigate.add_argument("fixture")
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("fixture")
    search = subparsers.add_parser(
        "search", help="inspect ranked evidence from a RootSignal knowledge index"
    )
    search.add_argument("query")
    search.add_argument(
        "--db",
        default=os.getenv("INCIDENTLAB_DB", "work/incidentlab.db"),
        help="path to the RootSignal SQLite database",
    )
    search.add_argument(
        "--strategy",
        choices=("lexical", "semantic", "hybrid", "reranked"),
        default="reranked",
    )
    search.add_argument("--collection", action="append", dest="collections")
    search.add_argument("--limit", type=int, choices=range(1, 21), default=6, metavar="1-20")
    ingest = subparsers.add_parser(
        "ingest", help="index a UTF-8 runbook in a scoped knowledge collection"
    )
    ingest.add_argument("file", type=Path)
    ingest.add_argument("--source", required=True, help="stable source provenance label")
    ingest.add_argument("--collection", default="incident-runbooks")
    ingest.add_argument(
        "--db",
        default=os.getenv("INCIDENTLAB_DB", "work/incidentlab.db"),
        help="path to the RootSignal SQLite database",
    )
    args = parser.parse_args(argv)

    if args.command == "ingest":
        if not 1 <= len(args.source.strip()) <= 200:
            parser.error("--source must contain 1 to 200 characters")
        try:
            text = _read_knowledge_file(args.file)
            result = KnowledgeBase(args.db).ingest(
                args.source.strip(), text, args.collection
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps(result, indent=2))
        return

    if args.command == "search":
        chunks = KnowledgeBase(args.db).search(
            args.query,
            limit=args.limit,
            strategy=args.strategy,
            collection_ids=args.collections,
        )
        print(json.dumps({
            "query": args.query,
            "strategy": args.strategy,
            "collections": args.collections or ["incident-runbooks"],
            "count": len(chunks),
            "results": [
                {
                    "rank": rank,
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "content": chunk.content,
                    "score": chunk.score,
                    "lexical_score": chunk.lexical_score,
                    "semantic_score": chunk.semantic_score,
                    "rerank_score": chunk.rerank_score,
                }
                for rank, chunk in enumerate(chunks, 1)
            ],
        }, indent=2))
        return

    incident = load_incident(args.fixture)
    result = Investigator().investigate(incident)
    payload = result.as_dict() if args.command == "investigate" else score(incident, result).as_dict()
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
