"""Build source-verified effective review files for seed 43/44 repeats.

Raw review receipts are immutable. This tool copies them into a derived view,
then applies the recorded append-only correction overlays after verifying each
overlay against its original sidecar line and the completed predictions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import review_id


ROOT = Path("data/benchmark/local_llm_runs")
TRACK_RUNS = {
    43: {
        "a": "phase5_seed43_track_a_20261115",
        "b": "phase5_seed43_track_b_20261115",
    },
    44: {
        "a": "phase5_seed44_track_a_20261115_full",
        "b": "phase5_seed44_track_b_20261115_full",
    },
}
SIDECARS = {
    43: [
        "seed42_identical_answer_transfer_v1.jsonl",
        "seed43_repeat_reviews_code_v1.jsonl",
        "seed43_repeat_reviews_math_v1.jsonl",
        "seed43_repeat_reviews_table_v1.jsonl",
        "seed43_repeat_reviews_unanswerable_protocol_v2.jsonl",
    ],
    44: [
        "seed42_identical_answer_transfer_v1.jsonl",
        "seed44_repeat_reviews_code_v1.jsonl",
        "seed44_repeat_reviews_math_v1.jsonl",
        "seed44_repeat_reviews_table_v1.jsonl",
        "seed44_repeat_reviews_unanswerable_code_v1.jsonl",
        "seed44_repeat_reviews_unanswerable_noncode_v1.jsonl",
    ],
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_jsonl(path: Path):
    raw = path.read_bytes()
    rows = []
    for number, line in enumerate(raw.splitlines(keepends=True), start=1):
        if line.strip():
            rows.append((number, sha(line), json.loads(line.decode("utf-8"))))
    return raw, rows


def write_or_verify(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"Refusing to overwrite different derived file: {path}")
    else:
        path.write_bytes(content)
    return sha(content)


def materialize(seed: int, track: str):
    run_name = TRACK_RUNS[seed][track]
    run_dir = ROOT / run_name
    judging = run_dir / "judging"
    receipts = {}
    locations = {}
    source_hashes = {}
    for filename in SIDECARS[seed]:
        path = judging / filename
        raw, rows = read_jsonl(path)
        source_hashes[path.as_posix()] = sha(raw)
        for number, line_hash, receipt in rows:
            rid = receipt.get("review_id")
            if not rid or rid in receipts:
                raise ValueError(f"Duplicate/missing receipt in {filename}: {rid}")
            receipts[rid] = receipt
            locations[rid] = (filename, number, line_hash)

    corrections_applied = []
    if seed == 43:
        filename = "seed43_repeat_review_corrections_v1.jsonl"
        path = judging / filename
        raw, rows = read_jsonl(path)
        source_hashes[path.as_posix()] = sha(raw)
        for _, _, correction in rows:
            rid = correction["source_review_id"]
            location = locations.get(rid)
            expected = (correction["source_file"], correction["source_line_number"],
                        correction["source_line_sha256_including_line_ending"])
            if location != expected:
                raise ValueError(f"Seed 43 correction source mismatch: {rid}")
            replacement = correction["replacement_receipt"]
            if (replacement.get("review_id") != correction["replacement_review_id"]
                    or replacement.get("question_id") != correction["replacement_question_id"]
                    or replacement.get("input_sha256") != correction["replacement_queue_input_sha256"]):
                raise ValueError(f"Seed 43 replacement identity mismatch: {rid}")
            receipts.pop(rid)
            locations.pop(rid)
            new_id = replacement["review_id"]
            if new_id in receipts:
                raise ValueError(f"Seed 43 replacement ID already exists: {new_id}")
            receipts[new_id] = replacement
            locations[new_id] = (filename, 0, "replacement")
            corrections_applied.append(new_id)
    else:
        # Correction overlays for code only change explicitly listed fields.
        filename = "seed44_repeat_reviews_code_v1_corrections_agent.jsonl"
        path = judging / filename
        raw, rows = read_jsonl(path)
        source_hashes[path.as_posix()] = sha(raw)
        for _, _, overlay in rows:
            rid = overlay["review_id"]
            location = locations.get(rid)
            if (location is None or location[0] != overlay["source_sidecar"]
                    or location[2] != overlay["source_line_sha256_including_line_ending"]):
                raise ValueError(f"Seed 44 code correction source mismatch: {rid}")
            current = receipts[rid]
            for field in ("input_sha256", "packet_sha256", "evidence_sha256",
                          "source_prediction_line_sha256_including_line_ending"):
                if field in overlay and current.get(field) != overlay[field]:
                    raise ValueError(f"Seed 44 code correction {field} mismatch: {rid}")
            current.update(overlay["corrected_fields"])
            corrections_applied.append(rid)

        # Table overlays are complete replacement receipts. Later rows in the
        # append-only overlay intentionally supersede earlier rows by review ID.
        filename = "seed44_repeat_reviews_table_v1_corrections_agent.jsonl"
        path = judging / filename
        raw, rows = read_jsonl(path)
        source_hashes[path.as_posix()] = sha(raw)
        for _, _, overlay in rows:
            rid = overlay["source_review_id"]
            location = locations.get(rid)
            expected = (overlay["source_file"], overlay["source_line_number"],
                        overlay["source_line_sha256_including_line_ending"])
            if location != expected:
                raise ValueError(f"Seed 44 table correction source mismatch: {rid}")
            replacement = overlay["replacement_receipt"]
            if (replacement.get("review_id") != overlay["replacement_review_id"]
                    or replacement.get("question_id") != overlay["replacement_question_id"]):
                raise ValueError(f"Seed 44 table replacement identity mismatch: {rid}")
            receipts[rid] = replacement
            corrections_applied.append(rid)

        # The unanswerable non-code review has three field-level corrections.
        filename = "seed44_repeat_reviews_unanswerable_noncode_v1_corrections.jsonl"
        path = judging / filename
        raw, rows = read_jsonl(path)
        source_hashes[path.as_posix()] = sha(raw)
        for _, _, overlay in rows:
            rid = overlay["review_id"]
            sidecar = overlay["source_sidecar"]
            recorded_path = Path(sidecar)
            if recorded_path.is_absolute() or recorded_path.exists():
                sidecar_path = recorded_path
            else:
                sidecar_path = judging / recorded_path.name
            sidecar_raw, sidecar_rows = read_jsonl(sidecar_path)
            source_hashes[sidecar_path.as_posix()] = sha(sidecar_raw)
            location = locations.get(rid)
            expected = (recorded_path.name, overlay["source_sidecar_line_number"],
                        overlay["source_sidecar_line_sha256_including_line_ending"])
            if (sha(sidecar_raw) != overlay["source_sidecar_sha256"]
                    or location != expected):
                raise ValueError(f"Seed 44 unanswerable correction source mismatch: {rid}")
            current = receipts[rid]
            for field in ("input_sha256", "evidence_sha256"):
                if current.get(field) != overlay.get(field):
                    raise ValueError(f"Seed 44 unanswerable correction {field} mismatch: {rid}")
            current.update(overlay["replacement_fields"])
            corrections_applied.append(rid)

    # Check exact coverage and all review/prediction bindings before writing.
    raw, prediction_rows = read_jsonl(run_dir / "predictions.jsonl")
    latest = {}
    prediction_line_hashes = {}
    for _, line_hash, prediction in prediction_rows:
        rid = review_id(prediction)
        latest[(prediction["model_digest"], prediction["question_id"])] = prediction
        prediction_line_hashes[rid] = line_hash
    completed = {review_id(row): row for row in latest.values()
                 if row.get("status") == "completed"}
    if set(receipts) != set(completed):
        missing = set(completed) - set(receipts)
        extra = set(receipts) - set(completed)
        raise ValueError(f"Receipt coverage mismatch: missing={len(missing)}, extra={len(extra)}")
    for rid, prediction in completed.items():
        receipt = receipts[rid]
        if receipt.get("question_id") != prediction.get("question_id"):
            raise ValueError(f"Receipt question mismatch: {rid}")
        if (isinstance(receipt.get("correctness"), bool)
                or receipt.get("correctness") not in (0, 0.5, 1)):
            raise ValueError(f"Missing/invalid correctness: {rid}")
        if receipt.get("category") and receipt["category"] != prediction.get("category"):
            raise ValueError(f"Receipt category mismatch: {rid}")
        for field in ("input_sha256", "packet_sha256", "evidence_sha256"):
            if receipt.get(field) is not None and receipt[field] != prediction.get(field):
                raise ValueError(f"Receipt {field} mismatch: {rid}")
        source_hash = receipt.get("source_prediction_line_sha256_including_line_ending")
        if source_hash is not None and source_hash != prediction_line_hashes[rid]:
            raise ValueError(f"Receipt source prediction line mismatch: {rid}")

    protocol_hashes = {
        (receipt.get("provenance") or {}).get("judge_protocol_sha256")
        for receipt in receipts.values()
        if (receipt.get("provenance") or {}).get("judge_protocol_sha256")
    }
    if len(protocol_hashes) > 1:
        raise ValueError(f"Mixed review protocol hashes: {sorted(protocol_hashes)}")

    ordered = [receipts[rid] for rid in sorted(receipts)]
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n" for row in ordered).encode("utf-8")
    output = judging / f"effective_repeat_reviews_seed{seed}_track_{track}_v1.jsonl"
    output_hash = write_or_verify(output, content)
    manifest = {
        "schema_version": f"effective_repeat_reviews_seed{seed}_track_{track}_v1",
        "run_dir": run_dir.as_posix(),
        "prediction_history_sha256": sha((run_dir / "predictions.jsonl").read_bytes()),
        "source_sidecar_sha256": source_hashes,
        "completed_predictions": len(completed),
        "effective_receipts": len(ordered),
        "correction_applications": len(corrections_applied),
        "review_protocol_sha256": next(iter(protocol_hashes), None),
        "effective_reviews_sha256": output_hash,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path = judging / f"effective_repeat_reviews_seed{seed}_track_{track}_v1_manifest.json"
    write_or_verify(manifest_path, manifest_bytes)
    return {"run": run_name, "completed": len(completed), "receipts": len(ordered),
            "correction_applications": len(corrections_applied), "sha256": output_hash}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, choices=(43, 44), required=True)
    parser.add_argument("--track", choices=("a", "b", "both"), default="both")
    args = parser.parse_args()
    tracks = ("a", "b") if args.track == "both" else (args.track,)
    for track in tracks:
        print(json.dumps(materialize(args.seed, track), ensure_ascii=False))


if __name__ == "__main__":
    main()
