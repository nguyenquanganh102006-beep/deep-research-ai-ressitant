"""Create blind AI review packets for the once-only frozen test run."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import PROJECT_ROOT
from scripts.prepare_repeat_blind_reviews import prepare as prepare_blind
from src.benchmark.local_common import DATA, file_hash, read_json, read_rows
from src.benchmark.scoring_local import review_id


def _write_or_verify(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n" for row in rows).encode("utf-8")
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"Refusing to overwrite frozen review input: {path}")
    else:
        path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def prepare(run_dir: Path, packet_path: Path, freeze_path: Path):
    run_dir, packet_path, freeze_path = (path.resolve() for path in (run_dir, packet_path, freeze_path))
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    if freeze.get("status") != "frozen_before_test" or freeze.get("candidate_commit_sha") != head:
        raise ValueError("Current code does not equal the frozen candidate commit")
    if not freeze.get("test_frozen_sha256") or file_hash(DATA / "test_frozen.jsonl") != freeze["test_frozen_sha256"]:
        raise ValueError("Frozen test corpus hash mismatch")
    protocol_path = PROJECT_ROOT / freeze["protocol_path"]
    if file_hash(protocol_path) != freeze.get("protocol_sha256"):
        raise ValueError("Frozen protocol hash mismatch")
    run_manifest = read_json(run_dir / "manifest.json")
    candidate_config = PROJECT_ROOT / freeze.get("candidate_config_path", "")
    candidate_doc = read_json(candidate_config)
    if (file_hash(candidate_config) != freeze.get("candidate_config_sha256")
            or candidate_doc.get("models") != freeze.get("models")
            or candidate_doc.get("thresholds") != freeze.get("thresholds")
            or candidate_doc.get("phase6_code_sha256") != freeze.get("phase6_code_sha256")
            or candidate_doc.get("protocol_path") != freeze.get("protocol_path")
            or candidate_doc.get("protocol_sha256") != freeze.get("protocol_sha256")
            or candidate_doc.get("prompt_sha256") != freeze.get("prompt_sha256")
            or candidate_doc.get("judge_protocol_path") != freeze.get("judge_protocol_path")
            or candidate_doc.get("judge_protocol_sha256") != freeze.get("judge_protocol_sha256")):
        raise ValueError("Candidate selection config differs from the freeze")
    phase6_code = {rel: file_hash(PROJECT_ROOT / rel) for rel in candidate_doc.get("phase6_code_sha256", {})}
    if not phase6_code or phase6_code != freeze.get("phase6_code_sha256"):
        raise ValueError("Final test preparation/scoring code changed after freeze")
    current_code = {path.relative_to(PROJECT_ROOT).as_posix(): file_hash(path) for path in
                    sorted((PROJECT_ROOT / "src/benchmark").glob("*.py"))}
    if current_code != freeze.get("benchmark_code_sha256"):
        raise ValueError("Benchmark source code changed after candidate freeze")
    judge_protocol_path = PROJECT_ROOT / freeze.get("judge_protocol_path", "")
    if file_hash(judge_protocol_path) != freeze.get("judge_protocol_sha256"):
        raise ValueError("Judge protocol differs from the freeze")
    if (run_manifest.get("git_sha") != head
            or run_manifest.get("protocol_sha256") != freeze["protocol_sha256"]
            or run_manifest.get("freeze_manifest_sha256") != file_hash(freeze_path)
            or run_manifest.get("test_frozen_sha256") != freeze["test_frozen_sha256"]
            or run_manifest.get("prompt_sha256") != freeze["prompt_sha256"]
            or run_manifest.get("split") != "test"
            or run_manifest.get("track") != "retrieved_text_frozen"):
        raise ValueError("Run manifest does not match the frozen commit/protocol")
    if run_manifest.get("packets_sha256") != file_hash(packet_path):
        raise ValueError("Run packet hash differs from predictions manifest")
    packet_manifest = read_json(packet_path.with_suffix(".manifest.json"))
    if (packet_manifest.get("freeze_manifest_sha256") != file_hash(freeze_path)
            or packet_manifest.get("test_frozen_sha256") != freeze["test_frozen_sha256"]):
        raise ValueError("Final test packet manifest is not bound to this freeze")

    # Read held-out labels only after commit, protocol, packet and dataset hashes pass.
    test_rows = read_rows(DATA / "test_frozen.jsonl")
    labels = {row["question_id"]: row for row in test_rows}
    if len(labels) != freeze["expected_test_question_count"]:
        raise ValueError("Frozen test question count changed")
    packets = read_rows(packet_path)
    packet_by_qid = {row["question_id"]: row for row in packets}
    if set(packet_by_qid) != set(labels):
        raise ValueError("Final test packet IDs differ from frozen test IDs")
    if any({"reference_answer", "expected_reasoning_checks", "rubric", "answer"} & set(p)
           for p in packets):
        raise ValueError("Frozen test labels leaked into model packets")

    predictions_path = run_dir / "predictions.jsonl"
    prediction_raw = predictions_path.read_bytes()
    latest, line_hashes = {}, {}
    for line in prediction_raw.splitlines(keepends=True):
        if not line.strip():
            continue
        pred = json.loads(line.decode("utf-8"))
        rid = review_id(pred)
        latest[(pred["model_digest"], pred["question_id"])] = pred
        line_hashes[rid] = hashlib.sha256(line).hexdigest()
    completed = [pred for pred in latest.values() if pred.get("status") == "completed"]
    templates, pending = [], []
    for pred in completed:
        qid = pred["question_id"]
        label = labels.get(qid)
        packet = packet_by_qid.get(qid)
        if label is None or packet is None:
            raise ValueError(f"Prediction is outside frozen test packets: {qid}")
        if (pred.get("packet_sha256") != packet.get("packet_sha256")
                or pred.get("evidence_sha256") != packet.get("evidence_sha256")
                or pred.get("input_sha256") is None):
            raise ValueError(f"Prediction input/evidence identity mismatch: {qid}")
        if (pred.get("question") != packet.get("question")
                or pred.get("category") != label.get("category")
                or pred.get("question") != label.get("question")):
            raise ValueError(f"Prediction question/category mismatch: {qid}")
        if not label.get("reference_answer") or not label.get("expected_reasoning_checks"):
            raise ValueError(f"Frozen test reference/rubric missing: {qid}")
        rid = review_id(pred)
        templates.append({
            "review_id": rid, "question_id": qid, "category": label["category"],
            "question": label["question"], "answer": pred.get("answer", ""),
            "reference_answer": label["reference_answer"],
            "rubric": label["expected_reasoning_checks"],
            "correctness": None, "citation_supported": None, "primary_error": None,
            "reviewer": None, "provenance": None,
            "note": "Evaluator-only blind final-test review; never expose to the tested model.",
        })
        pending.append({"review_id": rid, "question_id": qid, "category": label["category"],
                        "answer": pred.get("answer", "")})

    judging = run_dir / "judging"
    template_path = run_dir / "review_template.jsonl"
    pending_path = judging / "pending_reviews_final_v1.jsonl"
    _write_or_verify(template_path, templates)
    _write_or_verify(pending_path, pending)
    blind_manifest = prepare_blind(
        run_dir, packet_path, pending_path, judging / "blind_packets_v1", 20261115
    )
    return {"completed_predictions": len(completed), "pending_reviews": len(pending),
            "template_sha256": file_hash(template_path),
            "blind_review_count": blind_manifest["blind_review_count"],
            "blind_manifest": str(judging / "blind_packets_v1" / "blind_review_manifest_v1.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.run_dir, args.packets, args.freeze_manifest), ensure_ascii=False))


if __name__ == "__main__":
    main()
