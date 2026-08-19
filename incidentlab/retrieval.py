from __future__ import annotations

import math
import re
from collections import Counter


TOKEN = re.compile(r"[a-z0-9_.-]+")


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def bm25_search(query: str, documents: list[dict[str, str]], k: int = 3) -> list[dict[str, str | float]]:
    """Small dependency-free BM25 implementation used as the local retrieval baseline."""
    if not documents:
        return []
    tokenized = [tokenize(f"{d.get('title', '')} {d.get('content', '')}") for d in documents]
    avg_len = sum(map(len, tokenized)) / len(tokenized)
    query_terms = set(tokenize(query))
    doc_freq = Counter(term for term in query_terms for doc in tokenized if term in doc)
    results: list[dict[str, str | float]] = []
    for document, terms in zip(documents, tokenized, strict=True):
        counts = Counter(terms)
        score = 0.0
        for term in query_terms:
            df = doc_freq[term]
            idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
            tf = counts[term]
            denominator = tf + 1.2 * (1 - 0.75 + 0.75 * len(terms) / max(avg_len, 1))
            score += idf * (tf * 2.2 / denominator if denominator else 0)
        results.append({**document, "score": round(score, 5)})
    return sorted(results, key=lambda item: float(item["score"]), reverse=True)[:k]
