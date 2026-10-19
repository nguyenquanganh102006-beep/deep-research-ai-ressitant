"""Dense + BM25 retrieval with reciprocal-rank fusion and local neighbors."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from config import RETRIEVAL_MAX_CONTEXTS, RETRIEVAL_TOP_K
from src.embeddings import embed_query
from src.storage import paper_dir, read_json

_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[^\W_]", re.UNICODE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "the", "to", "what", "with", "which",
    "đâu", "được", "gì", "gồm", "là", "nào", "những", "theo", "trong", "và",
    "về", "các", "một", "như", "ra", "sao", "thế", "này", "nêu", "hãy",
}


def retrieve(
    document_id: str,
    question: str,
    *,
    top_k: int = RETRIEVAL_TOP_K,
    max_contexts: int = RETRIEVAL_MAX_CONTEXTS,
    include_neighbors: bool = True,
) -> list[dict[str, Any]]:
    directory = paper_dir(document_id)
    chunks = read_json(directory / "chunks.json")
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError("Tài liệu chưa có chunk để truy xuất.")
    embeddings_path = directory / "embeddings.npy"
    if not embeddings_path.exists():
        raise RuntimeError("Không tìm thấy embeddings.npy của tài liệu.")
    vectors = np.load(embeddings_path, allow_pickle=False).astype(np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
        raise RuntimeError("Embedding và danh sách chunk không khớp.")

    query_tokens = tokenize(question)
    corpus_tokens = [tokenize(chunk.get("content", "")) for chunk in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = np.asarray(bm25.get_scores(query_tokens), dtype=np.float32)

    query_vector = embed_query(question)
    dense_scores = vectors @ query_vector

    dense_order = np.argsort(-dense_scores)
    sparse_order = np.argsort(-bm25_scores)
    fused: dict[int, float] = {}
    for rank, index in enumerate(dense_order, start=1):
        if rank > max(top_k * 3, 12):
            break
        fused[int(index)] = fused.get(int(index), 0.0) + 1.0 / (60 + rank)
    for rank, index in enumerate(sparse_order, start=1):
        if rank > max(top_k * 3, 12) or bm25_scores[index] <= 0:
            break
        fused[int(index)] = fused.get(int(index), 0.0) + 1.0 / (60 + rank)

    # Exact identifiers and equation/algorithm numbers get a small tie-breaker.
    literals = _query_literals(question)
    for index, chunk in enumerate(chunks):
        content = str(chunk.get("content", "")).casefold()
        matches = sum(1 for literal in literals if literal.casefold() in content)
        if matches:
            fused[index] = fused.get(index, 0.0) + min(0.02, 0.005 * matches)

    ranked = sorted(fused, key=lambda index: fused[index], reverse=True)
    selected = ranked[:top_k]
    selected_set = set(selected)
    neighbor_sources: dict[int, int] = {}
    if include_neighbors:
        for index in selected[: min(2, len(selected))]:
            for neighbor in (index - 1, index + 1):
                if (
                    0 <= neighbor < len(chunks)
                    and neighbor not in selected_set
                    and len(selected_set) < max_contexts
                ):
                    selected_set.add(neighbor)
                    neighbor_sources[neighbor] = index

    # Keep primary matches first, then adjacent chunks, while retaining their
    # original document order for the evidence that is sent to the model.
    primary = selected
    extras = sorted(neighbor_sources, key=lambda i: neighbor_sources[i])
    chosen = primary + [i for i in extras if i not in primary]
    results: list[dict[str, Any]] = []
    for index in chosen[:max_contexts]:
        item = dict(chunks[index])
        item["dense_score"] = float(dense_scores[index])
        item["bm25_score"] = float(bm25_scores[index])
        item["rrf_score"] = float(fused.get(index, 0.0))
        item["neighbor_of"] = chunks[neighbor_sources[index]]["chunk_id"] if index in neighbor_sources else None
        results.append(item)
    return results


def tokenize(text: str) -> list[str]:
    normalized = text.replace("\u00a0", " ")
    output: list[str] = []
    for match in _TOKEN.finditer(normalized):
        token = match.group(0).casefold()
        if token in _STOP_WORDS or len(token) == 1 and not token.isdigit():
            continue
        output.append(token)
        # Index identifier components as well as the original identifier.
        for part in re.split(r"[_\W]+", token):
            if len(part) > 1 and part != token and part not in _STOP_WORDS:
                output.append(part)
        camel_parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", match.group(0)).casefold().split()
        output.extend(part for part in camel_parts if len(part) > 1 and part not in _STOP_WORDS)
    return output


def _query_literals(question: str) -> set[str]:
    literals: set[str] = set()
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*|\b\d+(?:\.\d+)?\b", question):
        value = match.group(0)
        if len(value) >= 3 and ("_" in value or any(char.isdigit() for char in value)):
            literals.add(value)
    return literals
