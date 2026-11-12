"""Stable serialization and dev-only inputs for the local LLM protocol."""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path

from config import PROJECT_ROOT
from src.storage import write_json, append_jsonl

CONFIG = PROJECT_ROOT / 'configs/benchmark'
DATA = PROJECT_ROOT / 'data/benchmark/curated_v1'
RUNS = PROJECT_ROOT / 'data/benchmark/local_llm_runs'


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def fingerprint(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').split('\n') if line.strip()]


def load_dev(directory: Path = DATA) -> tuple[list[dict], dict]:
    # Deliberately never open train/test_frozen in model-selection tooling.
    cases = read_rows(directory / 'dev.jsonl')
    papers = {p['paper_id']: p for p in read_rows(directory / 'papers.jsonl')}
    if len(cases) != 120 or len({q['question_id'] for q in cases}) != 120:
        raise ValueError('Expected exactly 120 unique dev questions')
    if any(q.get('split') != 'dev' for q in cases):
        raise ValueError('Non-dev label in dev input')
    return cases, papers


def sample_ids(cases: list[dict]) -> dict:
    chosen, used_papers = [], set()
    for category in ('math', 'code', 'table', 'unanswerable'):
        candidates = sorted((q for q in cases if q['category'] == category),
                            key=lambda q: fingerprint(q['question_id']))
        group = []
        for q in candidates:
            if not set(q['paper_ids']) & used_papers:
                group.append(q)
                used_papers.update(q['paper_ids'])
            if len(group) == 3:
                break
        for q in candidates:
            if len(group) == 3:
                break
            if q not in group:
                group.append(q)
        if len(group) != 3:
            raise ValueError('Insufficient category coverage')
        chosen.extend(q['question_id'] for q in group)
    result = {'version': 1, 'split': 'dev', 'selection': 'SHA256 ID order; prefer distinct papers; 3 per category',
              'question_ids': chosen}
    result['selection_sha256'] = fingerprint(result)
    return result
