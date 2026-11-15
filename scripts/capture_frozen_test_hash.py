"""Bind the held-out test corpus hash after code freeze and before any run."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from src.benchmark.local_common import CONFIG, DATA, file_hash, read_json


TEST_COUNT = 268
TEST_FILE = DATA / "test_frozen.jsonl"


def capture(freeze_path: Path, protocol_path: Path):
    freeze_path = freeze_path.resolve()
    protocol_path = protocol_path.resolve()
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    if freeze.get("status") != "frozen_before_test" or freeze.get("candidate_commit_sha") != head:
        raise ValueError("The candidate code is not frozen at the recorded commit")
    if freeze.get("expected_test_question_count") != TEST_COUNT:
        raise ValueError(f"Freeze manifest must require {TEST_COUNT} questions")
    if freeze.get("protocol_path") != protocol_path.relative_to(PROJECT_ROOT).as_posix():
        raise ValueError("Test protocol path differs from the freeze manifest")
    protocol = read_json(protocol_path)
    if protocol.get("split") != "test" or freeze.get("protocol_sha256") != file_hash(protocol_path):
        raise ValueError("Test protocol split/hash differs from the freeze manifest")
    candidate_config = PROJECT_ROOT / freeze.get("candidate_config_path", "")
    if (not freeze.get("candidate_config_sha256")
            or file_hash(candidate_config) != freeze.get("candidate_config_sha256")):
        raise ValueError("Candidate selection config differs from the freeze manifest")
    candidate = read_json(candidate_config)
    if (candidate.get("models") != freeze.get("models")
            or candidate.get("thresholds") != freeze.get("thresholds")
            or candidate.get("benchmark_code_sha256") != freeze.get("benchmark_code_sha256")
            or candidate.get("phase6_code_sha256") != freeze.get("phase6_code_sha256")
            or candidate.get("protocol_path") != freeze.get("protocol_path")
            or candidate.get("protocol_sha256") != freeze.get("protocol_sha256")):
        raise ValueError("Frozen models, thresholds, or protocol differ from candidate selection")
    phase6_code = {rel: file_hash(PROJECT_ROOT / rel) for rel in candidate.get("phase6_code_sha256", {})}
    if not phase6_code or phase6_code != freeze.get("phase6_code_sha256"):
        raise ValueError("Final test preparation/scoring code changed after freeze")
    current_code = {path.relative_to(PROJECT_ROOT).as_posix(): file_hash(path) for path in
                    sorted((PROJECT_ROOT / "src/benchmark").glob("*.py"))}
    if current_code != freeze.get("benchmark_code_sha256"):
        raise ValueError("Benchmark source code changed after candidate freeze")
    if freeze.get("prompt_sha256") != file_hash(CONFIG / "prompt_v1.txt"):
        raise ValueError("Prompt hash differs from the freeze manifest")
    judge_protocol_path = PROJECT_ROOT / freeze.get("judge_protocol_path", "")
    if file_hash(judge_protocol_path) != freeze.get("judge_protocol_sha256"):
        raise ValueError("Judge protocol hash differs from the freeze manifest")
    if candidate.get("prompt_sha256") != freeze.get("prompt_sha256") or candidate.get("judge_protocol_sha256") != freeze.get("judge_protocol_sha256"):
        raise ValueError("Prompt or judge protocol differs from candidate selection")
    models = freeze.get("models")
    if (not isinstance(models, list) or len(models) != 2
            or {model.get("role") for model in models} != {"candidate", "baseline"}):
        raise ValueError("Freeze must list exactly one candidate and one baseline")

    # Open only after the commit and protocol checks above pass.
    raw = TEST_FILE.read_bytes()
    rows = [json.loads(line.decode("utf-8")) for line in raw.splitlines() if line.strip()]
    qids = [row.get("question_id") for row in rows]
    if len(rows) != TEST_COUNT or len(set(qids)) != TEST_COUNT:
        raise ValueError(f"Expected {TEST_COUNT} unique rows in the frozen test corpus")
    if any(row.get("split") not in ("test", "test_frozen") for row in rows):
        raise ValueError("Frozen test file contains a non-test row")
    test_sha = hashlib.sha256(raw).hexdigest()
    existing = freeze.get("test_frozen_sha256")
    if existing and existing != test_sha:
        raise ValueError("Frozen test corpus changed after its hash was captured")
    if not existing:
        freeze["test_frozen_sha256"] = test_sha
        freeze["test_hash_captured_after_freeze"] = True
        freeze_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"questions": len(rows), "test_frozen_sha256": test_sha,
            "freeze_manifest_sha256": file_hash(freeze_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=CONFIG / "final_test_protocol_v1.json")
    args = parser.parse_args()
    print(json.dumps(capture(args.freeze_manifest, args.protocol), ensure_ascii=False))


if __name__ == "__main__":
    main()
