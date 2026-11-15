"""Build model-blind review packets for seed-repeat answers that changed."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import review_id


def _read(path: Path):
    raw = path.read_bytes()
    rows, hashes = [], {}
    for line_no, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.strip():
            continue
        row = json.loads(line.decode("utf-8"))
        rows.append(row)
        hashes[row.get("review_id")] = hashlib.sha256(line).hexdigest()
    return rows, hashes, hashlib.sha256(raw).hexdigest()


def _write_or_verify(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"refusing to replace existing review packet: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(content)
    return hashlib.sha256(content).hexdigest()


def prepare(run_dir: Path, packets_path: Path, pending_path: Path, output_dir: Path, random_seed: int):
    run_dir, packets_path, pending_path, output_dir = (p.resolve() for p in
                                                        (run_dir, packets_path, pending_path, output_dir))
    prediction_path = run_dir / "predictions.jsonl"
    predictions, line_hashes, prediction_sha = _read(prediction_path)
    latest = {}
    for row in predictions:
        latest[(row["model_digest"], row["question_id"])] = row
    completed = {review_id(row): row for row in latest.values() if row.get("status") == "completed"}
    packets, _, packet_file_sha = _read(packets_path)
    packet_by_qid = {row["question_id"]: row for row in packets}
    if len(packet_by_qid) != len(packets):
        raise ValueError("duplicate question_id in frozen packets")
    templates, _, template_sha = _read(run_dir / "review_template.jsonl")
    template_by_id = {row.get("review_id"): row for row in templates}
    pending, _, pending_sha = _read(pending_path)
    category_rows = collections.defaultdict(list)
    seen, source_line_hash_by_id = set(), {}

    raw_lines = prediction_path.read_bytes().splitlines(keepends=True)
    for line in raw_lines:
        if not line.strip():
            continue
        row = json.loads(line.decode("utf-8"))
        source_line_hash_by_id[review_id(row)] = hashlib.sha256(line).hexdigest()

    for item in pending:
        rid = item.get("review_id")
        if not rid or rid in seen:
            raise ValueError(f"missing/duplicate pending review_id: {rid!r}")
        seen.add(rid)
        pred = completed.get(rid)
        packet = packet_by_qid.get(item.get("question_id"))
        template = template_by_id.get(rid)
        if pred is None or packet is None or template is None:
            raise ValueError(f"pending review is not a completed packet case: {rid}")
        if (pred.get("question_id") != item.get("question_id")
                or packet.get("question_id") != pred.get("question_id")
                or template.get("question_id") != pred.get("question_id")):
            raise ValueError(f"question_id mismatch for {rid}")
        if pred.get("category") != packet.get("category") or template.get("category") != packet.get("category"):
            raise ValueError(f"category mismatch for {rid}")
        if (template.get("answer") != pred.get("answer") or item.get("answer") != pred.get("answer")
                or template.get("question") != packet.get("question")):
            raise ValueError(f"template/prediction mismatch for {rid}")
        if (pred.get("input_sha256") is None or pred.get("evidence_sha256") != packet.get("evidence_sha256")
                or pred.get("packet_sha256") != packet.get("packet_sha256")):
            raise ValueError(f"input/evidence/packet hash mismatch for {rid}")
        if item.get("answer") != pred.get("answer") or item.get("category") != pred.get("category"):
            raise ValueError(f"pending answer/category mismatch for {rid}")
        blind = {
            "review_id": rid,
            "question_id": pred["question_id"],
            "category": pred["category"],
            "question": pred.get("question") or packet.get("question"),
            "model_answer": pred.get("answer", ""),
            "reference_answer": template.get("reference_answer"),
            "rubric": template.get("rubric"),
            "allowed_pages": pred.get("allowed_pages", []),
            "retrieved_evidence": packet.get("evidence", []),
            "input_sha256": pred["input_sha256"],
            "packet_sha256": pred["packet_sha256"],
            "evidence_sha256": pred["evidence_sha256"],
            "source_prediction_line_sha256_including_line_ending": source_line_hash_by_id[rid],
            "output_truncated": bool(pred.get("output_truncated")),
        }
        category_rows[pred["category"]].append(blind)

    file_manifest = {}
    for category, rows in sorted(category_rows.items()):
        random.Random(random_seed + sum(category.encode("utf-8"))).shuffle(rows)
        path = output_dir / f"blind_{category}_v1.jsonl"
        content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n" for row in rows).encode("utf-8")
        file_manifest[category] = {"path": str(path), "count": len(rows),
                                   "sha256": _write_or_verify(path, content),
                                   "unique_review_ids": len({row["review_id"] for row in rows})}
    manifest = {
        "schema_version": "repeat_blind_review_packets_v1",
        "blind_model_names_or_digests_included": False,
        "random_seed": random_seed,
        "source_prediction_history_sha256": prediction_sha,
        "source_packet_sha256": packet_file_sha,
        "source_review_template_sha256": template_sha,
        "pending_queue_sha256": pending_sha,
        "pending_review_count": len(pending),
        "blind_review_count": sum(item["count"] for item in file_manifest.values()),
        "categories": file_manifest,
    }
    manifest_path = output_dir / "blind_review_manifest_v1.json"
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _write_or_verify(manifest_path, manifest_bytes)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--pending-reviews", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--random-seed", type=int, default=20261115)
    args = parser.parse_args()
    print(json.dumps(prepare(args.run_dir, args.packets, args.pending_reviews,
                             args.output_dir, args.random_seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
