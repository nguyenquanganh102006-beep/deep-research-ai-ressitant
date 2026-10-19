"""CPU-only multilingual E5 embeddings."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import numpy as np

from config import EMBEDDING_MODEL


@lru_cache(maxsize=1)
def _model() -> Any:
    # Do not reserve VRAM for embeddings; Ollama is the only GPU consumer.
    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    return SentenceTransformer(EMBEDDING_MODEL, device="cpu")


def embed_passages(texts: list[str]) -> np.ndarray:
    model = _model()
    vectors = model.encode(
        [f"passage: {text}" for text in texts],
        batch_size=16,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        device="cpu",
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    model = _model()
    vector = model.encode(
        [f"query: {text}"],
        batch_size=1,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
        device="cpu",
    )
    return np.asarray(vector[0], dtype=np.float32)
