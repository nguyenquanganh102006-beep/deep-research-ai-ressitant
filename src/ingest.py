"""Upload, parse, chunk, embed and persist one PDF by its SHA-256 digest."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

from config import (
    EMBEDDING_MODEL,
    MAX_UPLOAD_BYTES,
    PARSER_VERSION,
)
from src.chunker import create_chunks
from src.embeddings import embed_passages
from src.metrics import capture_resource_metrics
from src.parser import PDFValidationError, parse_pdf, validate_pdf
from src.storage import paper_dir, read_json, utc_now_iso, write_json, write_text


class IngestionError(RuntimeError):
    def __init__(self, message: str, document_id: str | None = None):
        super().__init__(message)
        self.document_id = document_id


def ingest_pdf_bytes(data: bytes, filename: str) -> tuple[dict[str, Any], bool]:
    clean_name = _safe_filename(filename)
    if not data:
        raise PDFValidationError("File tải lên đang rỗng.")
    if len(data) > MAX_UPLOAD_BYTES:
        size_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise PDFValidationError(f"File vượt giới hạn {size_mb} MB.")
    info = validate_pdf(data, clean_name)
    document_id = hashlib.sha256(data).hexdigest()
    directory = paper_dir(document_id)
    metadata_path = directory / "metadata.json"
    if metadata_path.exists():
        try:
            existing = read_json(metadata_path)
            required = [
                directory / "source.pdf",
                directory / "pages.json",
                directory / "parsed.md",
                directory / "chunks.json",
                directory / "embeddings.npy",
            ]
            if (
                existing.get("parse_status") in {"ok", "warning"}
                and all(path.exists() for path in required)
            ):
                return existing, True
        except Exception:
            pass

    directory.mkdir(parents=True, exist_ok=True)
    source_path = directory / "source.pdf"
    _atomic_write_bytes(source_path, data)
    metadata: dict[str, Any] = {
        "document_id": document_id,
        "filename": clean_name,
        "sha256": document_id,
        "page_count": info["page_count"],
        "created_at": utc_now_iso(),
        "parser_version": PARSER_VERSION,
        "pymupdf4llm_version": _package_version("pymupdf4llm"),
        "embedding_model": EMBEDDING_MODEL,
        "chunk_count": 0,
        "parse_status": "processing",
        "parse_warnings": [],
    }
    write_json(metadata_path, metadata)
    ingestion_started = time.perf_counter()
    try:
        parse_started = time.perf_counter()
        pages, parsed_markdown = parse_pdf(source_path, info["page_count"])
        metadata["parse_seconds"] = round(time.perf_counter() - parse_started, 3)
        chunk_started = time.perf_counter()
        chunks = create_chunks(pages)
        metadata["chunking_seconds"] = round(time.perf_counter() - chunk_started, 3)
        if not chunks:
            raise RuntimeError("Không trích xuất được nội dung văn bản từ PDF.")

        write_json(directory / "pages.json", pages)
        write_text(directory / "parsed.md", parsed_markdown)
        write_json(directory / "chunks.json", chunks)

        embedding_started = time.perf_counter()
        vectors = embed_passages([chunk["content"] for chunk in chunks])
        metadata["embedding_seconds"] = round(time.perf_counter() - embedding_started, 3)
        _atomic_save_npy(directory / "embeddings.npy", vectors)

        warnings = [
            {"page_number": page["page_number"], "message": warning}
            for page in pages
            for warning in page.get("parser_warning", [])
        ]
        metadata.update(
            {
                "parse_status": "warning" if warnings else "ok",
                "parse_warnings": warnings,
                "chunk_count": len(chunks),
                "embedding_dimensions": int(vectors.shape[1]),
                "total_ingestion_seconds": round(time.perf_counter() - ingestion_started, 3),
                "resource_metrics_after_indexing": capture_resource_metrics(),
            }
        )
        write_json(metadata_path, metadata)
        return metadata, False
    except Exception as exc:
        metadata.update(
            {
                "parse_status": "error",
                "parse_error": str(exc),
            }
        )
        write_json(metadata_path, metadata)
        raise IngestionError(str(exc), document_id=document_id) from exc


def _safe_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    name = re.sub(r"[\x00-\x1f]", "", name).strip()
    return name or "uploaded.pdf"


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _atomic_save_npy(path: Path, array: np.ndarray) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".npy.tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            np.save(stream, array, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
