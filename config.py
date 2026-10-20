"""Small, local-first configuration for DeepResearch Lite."""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("DEEPRESEARCH_DATA_DIR", PROJECT_ROOT / "data"))
PAPERS_DIR = DATA_ROOT / "papers"

MODEL_NAME = os.getenv("DEEPRESEARCH_MODEL", "qwen3.5:2b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("DEEPRESEARCH_OLLAMA_TIMEOUT", "600"))
NUM_CTX = int(os.getenv("DEEPRESEARCH_NUM_CTX", "4096"))
TEMPERATURE = float(os.getenv("DEEPRESEARCH_TEMPERATURE", "0.15"))
NUM_PREDICT = int(os.getenv("DEEPRESEARCH_NUM_PREDICT", "220"))

EMBEDDING_MODEL = os.getenv(
    "DEEPRESEARCH_EMBEDDING_MODEL", "intfloat/multilingual-e5-small"
)
MAX_UPLOAD_BYTES = int(os.getenv("DEEPRESEARCH_MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_PAGES = int(os.getenv("DEEPRESEARCH_MAX_PAGES", "50"))

# E5's default input limit is 512 tokens. Whitespace word counts are an
# inexpensive approximation here; the encoder remains responsible for its
# tokenizer's exact limit.
CHUNK_TARGET_WORDS = int(os.getenv("DEEPRESEARCH_CHUNK_TARGET_WORDS", "340"))
CHUNK_MAX_WORDS = int(os.getenv("DEEPRESEARCH_CHUNK_MAX_WORDS", "480"))
CHUNK_OVERLAP_WORDS = int(os.getenv("DEEPRESEARCH_CHUNK_OVERLAP_WORDS", "60"))
RETRIEVAL_TOP_K = int(os.getenv("DEEPRESEARCH_TOP_K", "4"))
RETRIEVAL_MAX_CONTEXTS = int(os.getenv("DEEPRESEARCH_MAX_CONTEXTS", "6"))
MAX_EVIDENCE_CHARS = max(4000, NUM_CTX * 2)

PARSER_VERSION = "pymupdf4llm-loss-aware-representations-v2"
