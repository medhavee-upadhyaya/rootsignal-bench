from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RetrievalStrategy = Literal["lexical", "semantic", "hybrid", "reranked"]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    source: str
    content: str
    score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rerank_score: float = 0.0


def chunk_text(text: str, size: int = 700, overlap: int = 100) -> list[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            boundary = clean.rfind(" ", start, end)
            end = boundary if boundary > start else end
        chunks.append(clean[start:end])
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


class KnowledgeBase:
    """Persistent hybrid knowledge base with provenance and deterministic ranking."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    source,
                    content,
                    tokenize='porter unicode61'
                );
                """
            )

    def ingest(self, source: str, text: str) -> dict[str, int | str]:
        digest = hashlib.sha256(text.encode()).hexdigest()
        document_id = digest[:16]
        chunks = chunk_text(text)
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT id FROM documents WHERE content_sha256 = ?", (digest,)
            ).fetchone()
            if exists:
                return {"document_id": str(exists["id"]), "chunks": 0, "status": "unchanged"}
            connection.execute(
                "INSERT INTO documents(id, source, content, content_sha256) VALUES (?, ?, ?, ?)",
                (document_id, source, text, digest),
            )
            connection.executemany(
                "INSERT INTO chunks(chunk_id, document_id, source, content) VALUES (?, ?, ?, ?)",
                [(f"{document_id}:{index}", document_id, source, content) for index, content in enumerate(chunks)],
            )
        return {"document_id": document_id, "chunks": len(chunks), "status": "indexed"}

    def search(
        self, query: str, limit: int = 6, strategy: RetrievalStrategy = "reranked"
    ) -> list[RetrievedChunk]:
        if strategy not in {"lexical", "semantic", "hybrid", "reranked"}:
            raise ValueError(f"Unknown retrieval strategy: {strategy}")
        terms = re.findall(r"[a-zA-Z0-9_.-]+", query)
        if not terms:
            return []
        fts_query = " OR ".join(f'"{term}"' for term in terms[:64])
        with self._connect() as connection:
            lexical_rows = connection.execute(
                """
                SELECT chunk_id, source, content, bm25(chunks) AS rank
                FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?
                """,
                (fts_query, max(limit * 4, 20)),
            ).fetchall()
            all_rows = connection.execute("SELECT chunk_id, source, content FROM chunks").fetchall()

        lexical_rank = {row["chunk_id"]: index for index, row in enumerate(lexical_rows, 1)}
        lexical_raw = {row["chunk_id"]: 1 / (1 + abs(row["rank"])) for row in lexical_rows}
        lexical_order = {chunk_id: 1 / rank for chunk_id, rank in lexical_rank.items()}
        query_vector = _hashed_vector(query)
        semantic = {
            row["chunk_id"]: _cosine(query_vector, _hashed_vector(row["content"])) for row in all_rows
        }
        semantic_rank = {
            chunk_id: index
            for index, (chunk_id, _) in enumerate(
                sorted(semantic.items(), key=lambda item: (-item[1], item[0])), 1
            )
        }
        rows_by_id = {row["chunk_id"]: row for row in all_rows}
        # Reciprocal-rank fusion remains stable across lexical score scales and
        # gives semantic matches a path into the candidate set.
        fused = {
            chunk_id: (2 / (60 + lexical_rank.get(chunk_id, 10_000)))
            + (1 / (60 + semantic_rank[chunk_id]))
            for chunk_id in rows_by_id
        }
        reranked = {
            chunk_id: _rerank(query, rows_by_id[chunk_id]["content"], fused[chunk_id])
            for chunk_id in rows_by_id
        }
        scores = {
            "lexical": lexical_order,
            "semantic": semantic,
            "hybrid": fused,
            "reranked": reranked,
        }[strategy]
        selected = sorted(
            rows_by_id,
            key=lambda chunk_id: (-scores.get(chunk_id, 0.0), chunk_id),
        )[:limit]
        return [
            RetrievedChunk(
                chunk_id,
                rows_by_id[chunk_id]["source"],
                rows_by_id[chunk_id]["content"],
                round(scores.get(chunk_id, 0.0), 6),
                round(lexical_raw.get(chunk_id, 0.0), 6),
                round(semantic[chunk_id], 6),
                round(reranked[chunk_id], 6),
            )
            for chunk_id in selected
        ]

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            documents = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
            chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
        return {"documents": documents, "chunks": chunks}


def _hashed_vector(text: str, dimensions: int = 256) -> dict[int, float]:
    vector: dict[int, float] = {}
    tokens = re.findall(r"[a-z0-9_.-]+", text.lower())
    features = [*tokens, *(f"{a}:{b}" for a, b in zip(tokens, tokens[1:]))]
    for feature in features:
        digest = hashlib.blake2b(feature.encode(), digest_size=4).digest()
        index = int.from_bytes(digest, "big") % dimensions
        vector[index] = vector.get(index, 0.0) + 1.0
    return vector


def _cosine(left: dict[int, float], right: dict[int, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(index, 0.0) for index, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _rerank(query: str, content: str, fused_score: float) -> float:
    query_tokens = re.findall(r"[a-z0-9_.-]+", query.lower())
    content_tokens = re.findall(r"[a-z0-9_.-]+", content.lower())
    if not content_tokens:
        return 0.0
    query_terms = set(query_tokens)
    content_terms = set(content_tokens)
    term_coverage = len(query_terms & content_terms) / len(content_terms)
    query_bigrams = set(zip(query_tokens, query_tokens[1:]))
    content_bigrams = set(zip(content_tokens, content_tokens[1:]))
    bigram_coverage = len(query_bigrams & content_bigrams) / max(len(content_bigrams), 1)
    return (100 * fused_score) + (0.55 * term_coverage) + (0.25 * bigram_coverage)
