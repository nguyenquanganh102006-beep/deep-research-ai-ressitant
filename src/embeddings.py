"""CPU-only multilingual E5 embeddings."""

from __future__ import annotations

import os
import hashlib
import json
import importlib.metadata
from functools import lru_cache
from pathlib import Path
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


def embedding_fingerprint() -> str:
    from huggingface_hub import snapshot_download
    revision = Path(snapshot_download(EMBEDDING_MODEL, local_files_only=True)).name
    payload = {"model": EMBEDDING_MODEL, "revision": revision,
               "encoder_version": importlib.metadata.version("sentence-transformers"),
               "transformers_version": importlib.metadata.version("transformers"),
               "torch_version": importlib.metadata.version("torch"),
               "passage_prefix": "passage: ", "query_prefix": "query: ",
               "normalized": True, "dtype": "float32"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
