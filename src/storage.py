"""Filesystem persistence helpers. No database service is required."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PAPERS_DIR


def paper_dir(document_id: str) -> Path:
    # IDs are SHA-256 hex strings. Validate before constructing a path.
    if len(document_id) != 64 or any(c not in "0123456789abcdef" for c in document_id):
        raise ValueError("Invalid document ID")
    return PAPERS_DIR / document_id


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    _atomic_write_text(path, encoded + "\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, value)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def list_documents() -> list[dict[str, Any]]:
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    documents: list[dict[str, Any]] = []
    for metadata_path in PAPERS_DIR.glob("*/metadata.json"):
        try:
            metadata = read_json(metadata_path)
            if isinstance(metadata, dict) and metadata.get("document_id"):
                documents.append(metadata)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(documents, key=lambda item: item.get("created_at", ""), reverse=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_text(path: Path, contents: str) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
