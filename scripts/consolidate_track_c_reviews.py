"""Validate blind Track C reviews and materialize append-only overlays."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import review_id


CATEGORIES = ("math", "code", "table")
ASSESSMENT_FIELDS = (
    "correctness", "citation_supported", "primary_error", "notes", "claims",
    "formula_fidelity", "algorithm_reasoning", "numeric_protocol_accuracy",
    "correct_abstention", "false_refusal", "reviewer", "provenance", "reviewed_at",
    "allowed_pages", "output_truncated",
)
SCHEMA_FIELDS = {"correct_abstention", "false_refusal"}
PROTOCOL_FIELDS = {"algorithm_reasoning", "formula_fidelity", "numeric_protocol_accuracy"}
IDENTITY_FIELDS = (
    "review_id", "question_id", "input_sha256", "packet_sha256", "evidence_sha256",
    "source_prediction_line_sha256_including_line_ending",
)
PACKET_IDENTITY_FIELDS = {
    "source_prediction_line_sha256_including_line_ending": "prediction_line_sha256_including_line_ending",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_jsonl_bytes(path: Path):
    raw = path.read_bytes()
    rows, line_hashes = [], []
    for line_no, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.strip():
            continue
        rows.append(json.loads(line.decode("utf-8")))
        line_hashes.append((line_no, _sha(line)))
    return rows, line_hashes, _sha(raw)


def _write_canonical_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8", newline="\n")
    return _sha(path.read_bytes())


def _validate_review(review, packet, filename):
    for field in IDENTITY_FIELDS:
        packet_field = PACKET_IDENTITY_FIELDS.get(field, field)
        if review.get(field) != packet.get(packet_field):
            raise ValueError(f"{filename}: {field} mismatch for {packet.get('review_id')}")
    score = review.get("correctness")
    if score is not None and (isinstance(score, bool) or score not in (0, 0.5, 1)):
        raise ValueError(f"{filename}: invalid correctness for {packet['review_id']}")
    for field in ("citation_supported", "formula_fidelity", "algorithm_reasoning",
                  "numeric_protocol_accuracy", "correct_abstention", "false_refusal"):
        if field in review and review[field] is not None and not isinstance(review[field], bool):
            raise ValueError(f"{filename}: invalid {field} for {packet['review_id']}")
    if not review.get("reviewer") or not isinstance(review.get("provenance"), dict):
        raise ValueError(f"{filename}: missing reviewer provenance for {packet['review_id']}")
    if review.get("claims") is not None and not isinstance(review["claims"], list):
        raise ValueError(f"{filename}: claims must be a list for {packet['review_id']}")


def consolidate(run_dir: Path, output: Path | None = None, manifest_path: Path | None = None):
    judging = run_dir / "judging"
    packet_dir = judging / "blind_packets_v1"
    source_manifest_path = judging / "blind_review_manifest_v1.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))

    predictions_path = run_dir / "predictions.jsonl"
    prediction_rows, prediction_line_hashes, predictions_sha = _read_jsonl_bytes(predictions_path)
    latest = {}
    for row, (_, line_hash) in zip(prediction_rows, prediction_line_hashes):
        latest[(row.get("model_digest"), row.get("question_id"))] = (row, line_hash)
    completed = {review_id(row): (row, line_hash)
                 for row, line_hash in latest.values() if row.get("status") == "completed"}

    if source_manifest.get("prediction_history_sha256") != predictions_sha:
        raise ValueError("blind review manifest prediction history hash mismatch")

    packet_by_id, packet_file_meta = {}, {}
    for category in CATEGORIES:
        packet_path = packet_dir / f"{category}_v1.jsonl"
        packet_rows, _, packet_sha = _read_jsonl_bytes(packet_path)
        manifest_item = source_manifest.get("categories", {}).get(category, {})
        if packet_sha != manifest_item.get("sha256"):
            raise ValueError(f"blind packet hash mismatch: {category}")
        if len(packet_rows) != manifest_item.get("count"):
            raise ValueError(f"blind packet count mismatch: {category}")
        packet_file_meta[category] = {"path": str(packet_path), "sha256": packet_sha,
                                      "rows": len(packet_rows)}
        for packet in packet_rows:
            rid = packet.get("review_id")
            if not rid or rid in packet_by_id:
                raise ValueError(f"duplicate/missing blind review_id: {rid!r}")
            packet_by_id[rid] = packet
            prediction = completed.get(rid)
            if prediction is None:
                raise ValueError(f"blind packet points outside completed predictions: {rid}")
            pred_row, prediction_line_hash = prediction
            if (packet.get("question_id") != pred_row.get("question_id")
                    or packet.get("prediction_line_sha256_including_line_ending") != prediction_line_hash):
                raise ValueError(f"prediction source mismatch for {rid}")

    if len(packet_by_id) != source_manifest.get("effective_latest_cases"):
        raise ValueError("blind packet total does not match manifest effective case count")
    if set(packet_by_id) != set(completed):
        raise ValueError("blind packet IDs do not exactly match completed predictions")

    effective, base_line_hashes, base_line_numbers, source_files = {}, {}, {}, {}
    for category in CATEGORIES:
        path = judging / f"track_c_reviews_{category}_agent_v1.jsonl"
        rows, line_hashes, file_sha = _read_jsonl_bytes(path)
        source_files[str(path)] = file_sha
        line_hash_by_id, line_number_by_id = {}, {}
        for line, (line_no, line_sha) in zip(path.read_bytes().splitlines(keepends=True), line_hashes):
            if line.strip():
                rid = json.loads(line.decode("utf-8"))["review_id"]
                line_hash_by_id[rid] = line_sha
                line_number_by_id[rid] = line_no
        expected = {rid for rid, packet in packet_by_id.items() if packet.get("category") == category}
        by_id = {}
        for row in rows:
            rid = row.get("review_id")
            if not rid or rid in by_id:
                raise ValueError(f"{path.name}: duplicate/missing review_id {rid!r}")
            if rid not in expected:
                raise ValueError(f"{path.name}: receipt outside {category} queue: {rid}")
            _validate_review(row, packet_by_id[rid], path.name)
            by_id[rid] = row
            base_line_hashes[(path.name, rid)] = line_hash_by_id[rid]
            base_line_numbers[(path.name, rid)] = line_number_by_id[rid]
        if set(by_id) != expected:
            raise ValueError(f"{path.name}: incomplete coverage; missing={len(expected - set(by_id))}")
        effective.update(by_id)

    overlay_counts = {"corrections": 0, "schema_defaults": 0}
    correction_line_hashes = {}
    for category in CATEGORIES:
        main_path = judging / f"track_c_reviews_{category}_agent_v1.jsonl"
        correction_path = judging / f"track_c_reviews_{category}_agent_v1_corrections.jsonl"
        if not correction_path.exists():
            continue
        rows, line_hashes, file_sha = _read_jsonl_bytes(correction_path)
        source_files[str(correction_path)] = file_sha
        raw_lines = correction_path.read_bytes().splitlines(keepends=True)
        for row, line, (_, line_hash) in zip(rows, raw_lines, line_hashes):
            rid = row.get("review_id")
            if rid not in effective or rid not in packet_by_id:
                raise ValueError(f"{correction_path.name}: correction outside review queue: {rid}")
            _validate_review(row, packet_by_id[rid], correction_path.name)
            superseded_line = row.get("supersedes_receipt_line_sha256_including_line_ending")
            superseded_file = row.get("supersedes_sidecar_sha256")
            if superseded_line is not None:
                if superseded_line != base_line_hashes.get((main_path.name, rid)):
                    raise ValueError(f"{correction_path.name}: superseded source hash mismatch (line hash): {rid}")
            elif superseded_file is not None:
                if superseded_file != source_files[str(main_path)]:
                    raise ValueError(f"{correction_path.name}: superseded source file hash mismatch: {rid}")
                if row.get("source_prediction_line_sha256_including_line_ending") != packet_by_id[rid].get(
                        "prediction_line_sha256_including_line_ending"):
                    raise ValueError(f"{correction_path.name}: source prediction line mismatch: {rid}")
            else:
                raise ValueError(f"{correction_path.name}: missing correction source binding: {rid}")
            current = effective[rid]
            for field in ASSESSMENT_FIELDS:
                if field in row:
                    current[field] = row[field]
            correction_line_hashes[(correction_path.name, rid)] = line_hash
            overlay_counts["corrections"] += 1

    # Partial field overlays bind to the immutable raw sidecar SHA and to the
    # exact prediction line hash carried by the blind packet.
    for category in CATEGORIES:
        main_path = judging / f"track_c_reviews_{category}_agent_v1.jsonl"
        overlay_path = judging / f"track_c_reviews_{category}_agent_v1_overlay.jsonl"
        if not overlay_path.exists():
            continue
        rows, line_hashes, file_sha = _read_jsonl_bytes(overlay_path)
        source_files[str(overlay_path)] = file_sha
        allowed_fields = set(ASSESSMENT_FIELDS)
        for row, (_, overlay_line_hash) in zip(rows, line_hashes):
            rid = row.get("correction_of_review_id")
            if rid not in effective or rid not in packet_by_id:
                raise ValueError(f"{overlay_path.name}: correction outside review queue: {rid}")
            if row.get("source_raw_sidecar_sha256") != source_files[str(main_path)]:
                raise ValueError(f"{overlay_path.name}: raw sidecar hash mismatch: {rid}")
            packet = packet_by_id[rid]
            if row.get("source_prediction_line_sha256_including_line_ending") != packet.get(
                    "prediction_line_sha256_including_line_ending"):
                raise ValueError(f"{overlay_path.name}: source prediction line mismatch: {rid}")
            changes = row.get("corrections")
            if not isinstance(changes, dict) or not changes or set(changes) - allowed_fields:
                raise ValueError(f"{overlay_path.name}: invalid correction fields: {rid}")
            if "correctness" in changes and (isinstance(changes["correctness"], bool)
                                               or changes["correctness"] not in (0, 0.5, 1)):
                raise ValueError(f"{overlay_path.name}: invalid correctness: {rid}")
            if "claims" in changes and not isinstance(changes["claims"], list):
                raise ValueError(f"{overlay_path.name}: invalid claims: {rid}")
            current = effective[rid]
            current.update(changes)
            current.setdefault("effective_correction_overlays", []).append({
                "file": overlay_path.name, "overlay_file_sha256": file_sha,
                "overlay_line_sha256_including_line_ending": overlay_line_hash,
                "source_raw_sidecar_sha256": row["source_raw_sidecar_sha256"],
                "reviewer": row.get("reviewer"), "provenance": row.get("provenance"),
            })
            correction_line_hashes[(overlay_path.name, rid)] = overlay_line_hash
            overlay_counts["corrections"] += 1

    protocol_field_receipts = 0
    protocol_field_values = collections.Counter()
    for category in CATEGORIES:
        protocol_path = judging / f"track_c_reviews_{category}_agent_v1_protocol_fields_overlay_v1.jsonl"
        if not protocol_path.exists():
            continue
        rows, _, file_sha = _read_jsonl_bytes(protocol_path)
        source_files[str(protocol_path)] = file_sha
        for row in rows:
            rid = row.get("review_id")
            if rid not in effective or rid not in packet_by_id:
                raise ValueError(f"{protocol_path.name}: protocol overlay outside queue: {rid}")
            expected_file = f"track_c_reviews_{category}_agent_v1.jsonl"
            if row.get("source_file") != expected_file:
                raise ValueError(f"{protocol_path.name}: unexpected protocol source file for {rid}")
            if row.get("source_line_number") != base_line_numbers.get((expected_file, rid)):
                raise ValueError(f"{protocol_path.name}: source line number mismatch for {rid}")
            if row.get("source_line_sha256_including_line_ending") != base_line_hashes.get((expected_file, rid)):
                raise ValueError(f"{protocol_path.name}: source receipt hash mismatch for {rid}")
            packet = packet_by_id[rid]
            for field in IDENTITY_FIELDS:
                packet_field = PACKET_IDENTITY_FIELDS.get(field, field)
                if row.get(field) != packet.get(packet_field):
                    raise ValueError(f"{protocol_path.name}: {field} mismatch for {rid}")
            for field in PROTOCOL_FIELDS:
                if field in effective[rid]:
                    raise ValueError(f"{protocol_path.name}: protocol field would overwrite existing {field}: {rid}")
                value = row.get(field)
                if value is not None and not isinstance(value, bool):
                    raise ValueError(f"{protocol_path.name}: invalid {field}: {rid}")
                if not isinstance(row.get(f"{field}_rationale"), str) or not row[f"{field}_rationale"].strip():
                    raise ValueError(f"{protocol_path.name}: missing {field} rationale: {rid}")
                effective[rid][field] = value
                protocol_field_values[field + "=" + str(value)] += 1
            protocol_field_receipts += 1
            effective[rid]["protocol_field_overlay_source_sha256"] = file_sha

    for category in CATEGORIES:
        schema_path = judging / f"track_c_reviews_{category}_agent_v1_schema_overlay.jsonl"
        if not schema_path.exists():
            continue
        rows, line_hashes, file_sha = _read_jsonl_bytes(schema_path)
        source_files[str(schema_path)] = file_sha
        raw_lines = schema_path.read_bytes().splitlines(keepends=True)
        for row, line, (_, overlay_line_hash) in zip(rows, raw_lines, line_hashes):
            rid = row.get("review_id")
            if rid not in effective or rid not in packet_by_id:
                raise ValueError(f"{schema_path.name}: schema overlay outside queue: {rid}")
            source_name = row.get("source_receipt_file")
            source_hash = row.get("source_receipt_line_sha256_including_line_ending")
            main_hash = base_line_hashes.get((f"track_c_reviews_{category}_agent_v1.jsonl", rid))
            correction_hash = correction_line_hashes.get((f"track_c_reviews_{category}_agent_v1_corrections.jsonl", rid))
            if source_name == f"track_c_reviews_{category}_agent_v1.jsonl":
                valid_hash = main_hash
            elif source_name == f"track_c_reviews_{category}_agent_v1_corrections.jsonl":
                valid_hash = correction_hash
            else:
                raise ValueError(f"{schema_path.name}: unexpected schema source file for {rid}")
            if not source_hash or source_hash != valid_hash:
                raise ValueError(f"{schema_path.name}: source receipt hash mismatch: {rid}")
            packet = packet_by_id[rid]
            for field in IDENTITY_FIELDS:
                packet_field = PACKET_IDENTITY_FIELDS.get(field, field)
                if row.get(field) != packet.get(packet_field):
                    raise ValueError(f"{schema_path.name}: {field} mismatch for {rid}")
            fields = row.get("schema_fields_added")
            if not isinstance(fields, list) or not fields or set(fields) - SCHEMA_FIELDS:
                raise ValueError(f"{schema_path.name}: invalid schema_fields_added for {rid}")
            current = effective[rid]
            for field in fields:
                if field in current:
                    raise ValueError(f"{schema_path.name}: would overwrite existing field {field}: {rid}")
                if row.get(field) is not None:
                    raise ValueError(f"{schema_path.name}: only null defaults permitted: {rid}")
                current[field] = None
            overlay_counts["schema_defaults"] += len(fields)

    required = {"correctness", "citation_supported", "primary_error", "notes", "claims",
                "formula_fidelity", "algorithm_reasoning", "numeric_protocol_accuracy",
                "correct_abstention", "false_refusal", "reviewer", "provenance", "reviewed_at"}
    for rid, row in effective.items():
        missing = required - set(row)
        if missing:
            raise ValueError(f"schema incomplete for {rid}: {sorted(missing)}")
        _validate_review(row, packet_by_id[rid], "effective")

    ordered = sorted(effective.values(), key=lambda row: (row["question_id"], row["review_id"]))
    output = output or judging / "effective_reviews_ai_v1.jsonl"
    manifest_path = manifest_path or judging / "effective_reviews_ai_v1_manifest.json"
    output_sha = _write_canonical_jsonl(output, ordered)
    score_counts = collections.Counter(str(row.get("correctness")) for row in ordered)
    citation_counts = collections.Counter(str(row.get("citation_supported")) for row in ordered)
    manifest = {
        "schema_version": "track_c_effective_reviews_ai_v1",
        "provenance": "AI-only reviews; not human/expert gold",
        "source_manifest_sha256": _sha(source_manifest_path.read_bytes()),
        "prediction_history_sha256": predictions_sha,
        "protocol_sha256": source_manifest.get("reviewer_protocol_sha256"),
        "blind_packet_files": packet_file_meta,
        "review_files_sha256": source_files,
        "effective_review_count": len(ordered),
        "unique_review_ids": len({r["review_id"] for r in ordered}),
        "correctness_pending": sum(r.get("correctness") is None for r in ordered),
        "correctness_counts": dict(score_counts),
        "citation_supported_counts": dict(citation_counts),
        "overlay_counts": overlay_counts,
        "protocol_field_overlay_receipts": protocol_field_receipts,
        "protocol_field_values": dict(protocol_field_values),
        "output_sha256": output_sha,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    result = consolidate(args.run_dir, args.output, args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
