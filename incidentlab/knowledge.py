from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
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
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS document_collections (
                    document_id TEXT NOT NULL,
                    collection_id TEXT NOT NULL,
                    PRIMARY KEY(document_id, collection_id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_schema (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
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
            connection.execute(
                """
                INSERT OR IGNORE INTO collections(id, name, description, created_at)
                VALUES ('incident-runbooks', 'Incident runbooks',
                        'Built-in operational guidance', CURRENT_TIMESTAMP)
                """
            )
            migrated = connection.execute(
                "SELECT value FROM knowledge_schema WHERE key = 'collections-v1'"
            ).fetchone()
            if not migrated:
                document_count = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
                if document_count:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO collections(id, name, description, created_at)
                        VALUES ('legacy-imports', 'Legacy imports',
                                'Documents indexed before collection scoping', CURRENT_TIMESTAMP)
                        """
                    )
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO document_collections(document_id, collection_id)
                        SELECT id, 'legacy-imports' FROM documents
                        """
                    )
                    connection.execute(
                        "DELETE FROM document_collections WHERE collection_id = 'incident-runbooks'"
                    )
                connection.execute(
                    "INSERT INTO knowledge_schema(key, value) VALUES ('collections-v1', 'complete')"
                )

    def create_collection(self, collection_id: str, name: str, description: str = "") -> dict[str, str]:
        if not re.fullmatch(r"[a-z0-9-]+", collection_id):
            raise ValueError("Collection id must use lowercase letters, digits, and hyphens")
        if not name.strip():
            raise ValueError("Collection name is required")
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO collections(id, name, description, created_at) VALUES (?, ?, ?, ?)",
                    (collection_id, name.strip(), description.strip(), created_at),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Collection id already exists") from exc
        return {"id": collection_id, "name": name.strip(), "description": description.strip(), "created_at": created_at}

    def list_collections(self) -> list[dict[str, int | str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.name, c.description, c.created_at,
                       count(dc.document_id) AS documents
                FROM collections c
                LEFT JOIN document_collections dc ON dc.collection_id = c.id
                GROUP BY c.id ORDER BY c.created_at, c.id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def ingest(self, source: str, text: str, collection_id: str = "incident-runbooks") -> dict[str, int | str]:
        digest = hashlib.sha256(text.encode()).hexdigest()
        document_id = digest[:16]
        chunks = chunk_text(text)
        with self._connect() as connection:
            collection = connection.execute(
                "SELECT id FROM collections WHERE id = ?", (collection_id,)
            ).fetchone()
            if not collection:
                raise ValueError("Unknown knowledge collection")
            exists = connection.execute(
                "SELECT id FROM documents WHERE content_sha256 = ?", (digest,)
            ).fetchone()
            if exists:
                connection.execute(
                    "INSERT OR IGNORE INTO document_collections VALUES (?, ?)",
                    (str(exists["id"]), collection_id),
                )
                return {"document_id": str(exists["id"]), "collection_id": collection_id, "chunks": 0, "status": "unchanged"}
            connection.execute(
                "INSERT INTO documents(id, source, content, content_sha256) VALUES (?, ?, ?, ?)",
                (document_id, source, text, digest),
            )
            connection.executemany(
                "INSERT INTO chunks(chunk_id, document_id, source, content) VALUES (?, ?, ?, ?)",
                [(f"{document_id}:{index}", document_id, source, content) for index, content in enumerate(chunks)],
            )
            connection.execute(
                "INSERT INTO document_collections VALUES (?, ?)", (document_id, collection_id)
            )
        return {"document_id": document_id, "collection_id": collection_id, "chunks": len(chunks), "status": "indexed"}

    def search(
        self, query: str, limit: int = 6, strategy: RetrievalStrategy = "reranked",
        collection_ids: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        if strategy not in {"lexical", "semantic", "hybrid", "reranked"}:
            raise ValueError(f"Unknown retrieval strategy: {strategy}")
        terms = list(dict.fromkeys(re.findall(r"[a-zA-Z0-9_.-]+", query.lower())))
        if not terms:
            return []
        fts_query = " OR ".join(f'"{term}"' for term in terms[:128])
        selected_collections = collection_ids or ["incident-runbooks"]
        placeholders = ",".join("?" for _ in selected_collections)
        with self._connect() as connection:
            lexical_rows = connection.execute(
                f"""
                SELECT DISTINCT chunks.chunk_id, chunks.source, chunks.content,
                       bm25(chunks) AS rank
                FROM chunks
                JOIN document_collections dc ON dc.document_id = chunks.document_id
                WHERE chunks MATCH ? AND dc.collection_id IN ({placeholders})
                ORDER BY rank LIMIT ?
                """,
                (fts_query, *selected_collections, max(limit * 4, 20)),
            ).fetchall()
            all_rows = connection.execute(
                f"""
                SELECT DISTINCT chunks.chunk_id, chunks.source, chunks.content
                FROM chunks
                JOIN document_collections dc ON dc.document_id = chunks.document_id
                WHERE dc.collection_id IN ({placeholders})
                """,
                selected_collections,
            ).fetchall()

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
            chunk_id: _rerank(
                query,
                rows_by_id[chunk_id]["content"],
                lexical_order.get(chunk_id, 0.0),
                semantic[chunk_id],
                fused[chunk_id],
            )
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


def _rerank(
    query: str,
    content: str,
    lexical_score: float,
    semantic_score: float,
    fused_score: float,
) -> float:
    query_tokens = re.findall(r"[a-z0-9_.-]+", query.lower())
    content_tokens = re.findall(r"[a-z0-9_.-]+", content.lower())
    if not content_tokens:
        return 0.0
    query_terms = set(query_tokens)
    content_terms = set(content_tokens)
    term_coverage = len(query_terms & content_terms) / max(len(query_terms), 1)
    query_bigrams = set(zip(query_tokens, query_tokens[1:]))
    content_bigrams = set(zip(content_tokens, content_tokens[1:]))
    bigram_coverage = len(query_bigrams & content_bigrams) / max(len(query_bigrams), 1)
    # Preserve exact lexical evidence, then use semantic and phrase signals to
    # resolve close candidates. RRF remains visible as a small audit tie-breaker.
    return (
        (0.75 * lexical_score)
        + (0.15 * semantic_score)
        + (0.05 * term_coverage)
        + (0.03 * bigram_coverage)
        + (0.02 * min(100 * fused_score, 1.0))
    )
