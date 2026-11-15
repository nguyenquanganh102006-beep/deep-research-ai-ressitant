"""Transfer seed-42 AI review only to byte-identical answers on identical inputs."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import review_id


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def _canonical_hash(row):
    return _sha(json.dumps(row, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8"))


def _latest(path: Path):
    rows = {}
    for row in _read_jsonl(path):
        rows[(row["model_digest"], row["question_id"])] = row
    return rows


def _unique_receipts(path: Path):
    result = {}
    for row in _read_jsonl(path):
        rid = row.get("review_id")
        if not rid or rid in result:
            raise ValueError(f"missing/duplicate source review_id: {rid!r}")
        result[rid] = row
    return result


def _write_or_verify(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"refusing to replace non-identical generated file: {path}")
        return _sha(content)
    with path.open("xb") as stream:
        stream.write(content)
    return _sha(content)


def transfer(baseline_run: Path, baseline_reviews: Path, repeat_run: Path,
             output: Path, pending_output: Path, manifest_output: Path):
    baseline_run, repeat_run = baseline_run.resolve(), repeat_run.resolve()
    baseline_reviews = baseline_reviews.resolve()
    output, pending_output, manifest_output = output.resolve(), pending_output.resolve(), manifest_output.resolve()
    baseline_manifest_path, repeat_manifest_path = baseline_run / "manifest.json", repeat_run / "manifest.json"
    baseline_manifest = json.loads(baseline_manifest_path.read_text(encoding="utf-8"))
    repeat_manifest = json.loads(repeat_manifest_path.read_text(encoding="utf-8"))

    for field in ("git_sha", "prompt_sha256", "packets_sha256"):
        if baseline_manifest.get(field) != repeat_manifest.get(field):
            raise ValueError(f"seed-repeat run changed pinned {field}")
    base_protocol, repeat_protocol = dict(baseline_manifest["protocol"]), dict(repeat_manifest["protocol"])
    if "seed" not in base_protocol or "seed" not in repeat_protocol:
        raise ValueError("protocols do not pin a random seed")
    base_protocol.pop("seed"); repeat_protocol.pop("seed")
    if base_protocol != repeat_protocol:
        raise ValueError("protocols differ in fields other than seed")
    if baseline_manifest.get("prompt_sha256") != repeat_manifest.get("prompt_sha256"):
        raise ValueError("prompt hash mismatch")

    baseline = _latest(baseline_run / "predictions.jsonl")
    repeat = _latest(repeat_run / "predictions.jsonl")
    source_receipts = _unique_receipts(baseline_reviews)
    base_models = {row["model_digest"]: row for row in baseline_manifest.get("models", [])}
    repeat_models = {row["model_digest"]: row for row in repeat_manifest.get("models", [])}
    if not repeat_models or set(repeat_models) - set(base_models):
        raise ValueError("repeat run contains a model digest absent from seed-42 baseline")
    for digest, meta in repeat_models.items():
        if (meta.get("model_tag") != base_models[digest].get("model_tag")
                or meta.get("quantization") != base_models[digest].get("quantization")):
            raise ValueError(f"model tag/quantization changed for {digest}")

    keys = {key for key in repeat if key[0] in repeat_models}
    if not keys or any(key not in baseline for key in keys):
        raise ValueError("repeat question IDs do not match seed-42 baseline")
    baseline_keys = {key for key in baseline if key[0] in repeat_models}
    if keys != baseline_keys:
        raise ValueError("repeat and baseline question ID sets differ")

    template_rows = _read_jsonl(repeat_run / "review_template.jsonl")
    template_by_id = {row.get("review_id"): row for row in template_rows}
    transferred, pending = [], []
    statuses = collections.Counter()
    exact_equal = 0
    for key in sorted(keys):
        base_row, repeat_row = baseline[key], repeat[key]
        digest, qid = key
        for field in ("input_sha256", "evidence_sha256", "prompt_sha256", "quantization", "track"):
            if base_row.get(field) != repeat_row.get(field):
                raise ValueError(f"repeat input/config mismatch {field}: {repeat_row.get('model_tag')} {qid}")
        status = repeat_row.get("status")
        statuses[status] += 1
        if status != "completed":
            continue
        target_id = review_id(repeat_row)
        if target_id not in template_by_id:
            raise ValueError(f"repeat review template missing {target_id}")
        if (base_row.get("status") == "completed"
                and base_row.get("answer") == repeat_row.get("answer")):
            exact_equal += 1
            source_id = review_id(base_row)
            source = source_receipts.get(source_id)
            if source is None or source.get("correctness") is None:
                raise ValueError(f"seed-42 review missing/pending for {source_id}")
            copied = dict(source)
            copied["review_id"] = target_id
            copied["question_id"] = qid
            provenance = dict(copied.get("provenance") or {})
            provenance.update({
                "review_type": "AI-only identical-answer transfer; not human/expert gold",
                "transfer_source_review_id": source_id,
                "transfer_source_receipt_sha256": _canonical_hash(source),
                "transfer_source_seed": baseline_manifest["protocol"]["seed"],
                "transfer_target_seed": repeat_manifest["protocol"]["seed"],
                "transfer_answer_sha256": _sha(repeat_row["answer"].encode("utf-8")),
                "transfer_input_sha256": repeat_row.get("input_sha256"),
                "transfer_model_digest": digest,
                "transfer_track": repeat_row.get("track"),
            })
            copied["provenance"] = provenance
            copied["identical_answer_transfer"] = True
            transferred.append(copied)
        else:
            pending.append(template_by_id[target_id])

    transferred.sort(key=lambda row: (row.get("question_id", ""), row["review_id"]))
    pending.sort(key=lambda row: (row.get("question_id", ""), row["review_id"]))
    transferred_bytes = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n" for row in transferred).encode("utf-8")
    pending_bytes = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")) + "\n" for row in pending).encode("utf-8")
    transfer_sha = _write_or_verify(output, transferred_bytes)
    pending_sha = _write_or_verify(pending_output, pending_bytes)
    manifest = {
        "schema_version": "identical_answer_review_transfer_v1",
        "provenance": "AI-only transfer from seed 42; not human/expert gold",
        "baseline_seed": baseline_manifest["protocol"]["seed"],
        "repeat_seed": repeat_manifest["protocol"]["seed"],
        "baseline_prediction_history_sha256": _sha((baseline_run / "predictions.jsonl").read_bytes()),
        "repeat_prediction_history_sha256": _sha((repeat_run / "predictions.jsonl").read_bytes()),
        "baseline_review_sha256": _sha(baseline_reviews.read_bytes()),
        "repeat_template_sha256": _sha((repeat_run / "review_template.jsonl").read_bytes()),
        "baseline_git_sha": baseline_manifest.get("git_sha"),
        "repeat_git_sha": repeat_manifest.get("git_sha"),
        "prompt_sha256": repeat_manifest.get("prompt_sha256"),
        "packet_sha256": repeat_manifest.get("packets_sha256"),
        "repeat_status_counts": dict(statuses),
        "latest_repeat_cases": len(keys),
        "completed_repeat_cases": sum(status == "completed" for status in statuses.elements()),
        "identical_answer_reviews_transferred": len(transferred),
        "completed_different_or_unreviewed": len(pending),
        "failed_repeat_cases_not_reviewed": sum(count for status, count in statuses.items() if status != "completed"),
        "transfer_output_sha256": transfer_sha,
        "pending_review_queue_sha256": pending_sha,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_sha = _write_or_verify(manifest_output, manifest_bytes)
    manifest["manifest_sha256"] = manifest_sha
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--baseline-reviews", type=Path, required=True)
    parser.add_argument("--repeat-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pending-output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = transfer(args.baseline_run, args.baseline_reviews, args.repeat_run,
                      args.output, args.pending_output, args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
