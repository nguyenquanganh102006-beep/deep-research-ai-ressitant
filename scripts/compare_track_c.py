"""Compare frozen Track C vision predictions with their matched Track B text controls."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import EXCLUDED, review_id


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest(path: Path):
    latest = {}
    for row in _read_jsonl(path):
        latest[(row["model_digest"], row["question_id"])] = row
    return latest


def _receipts(path: Path):
    result = {}
    for row in _read_jsonl(path):
        rid = row["review_id"]
        if rid in result:
            raise ValueError(f"duplicate effective review receipt: {rid}")
        result[rid] = row
    return result


def _score(row, receipts):
    if row.get("status") in EXCLUDED:
        return None
    if row.get("status") != "completed":
        return 0.0
    receipt = receipts.get(review_id(row))
    if receipt is None:
        raise ValueError(f"missing review receipt: {row['model_tag']} {row['question_id']}")
    score = receipt.get("correctness")
    if score is None:
        raise ValueError(f"pending correctness receipt: {row['model_tag']} {row['question_id']}")
    if isinstance(score, bool) or score not in (0, 0.5, 1):
        raise ValueError(f"invalid correctness score: {row['model_tag']} {row['question_id']}")
    return float(score)


def _paired_stats(pairs, seed=20261115):
    diffs = np.asarray([vision - text for text, vision in pairs], dtype=float)
    if not len(diffs):
        return {"n": 0, "mean_track_b": None, "mean_track_c": None,
                "mean_delta_c_minus_b": None, "wins_c": 0, "ties": 0,
                "losses_c": 0, "ci95_delta": None}
    rng = np.random.default_rng(seed)
    boot = rng.choice(diffs, size=(10000, len(diffs)), replace=True).mean(axis=1)
    return {
        "n": len(diffs),
        "mean_track_b": float(np.mean([text for text, _ in pairs])),
        "mean_track_c": float(np.mean([vision for _, vision in pairs])),
        "mean_delta_c_minus_b": float(diffs.mean()),
        "wins_c": int(np.sum(diffs > 0)), "ties": int(np.sum(diffs == 0)),
        "losses_c": int(np.sum(diffs < 0)),
        "ci95_delta": [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))],
    }


def compare(vision_run: Path, text_run: Path, vision_reviews: Path, text_reviews: Path,
            vision_packets: Path, text_packets: Path, subset_manifest: Path):
    vision_run = vision_run.resolve()
    text_run = text_run.resolve()
    vision_reviews = vision_reviews.resolve()
    text_reviews = text_reviews.resolve()
    vision_packets = vision_packets.resolve()
    text_packets = text_packets.resolve()
    subset_manifest = subset_manifest.resolve()

    subset = json.loads(subset_manifest.read_text(encoding="utf-8"))
    if _sha(vision_packets) != subset.get("vision_output", {}).get("sha256"):
        raise ValueError("Track C packet hash does not match frozen subset manifest")
    if _sha(text_packets) != subset.get("text_control_output", {}).get("sha256"):
        raise ValueError("Track B control packet hash does not match frozen subset manifest")
    if subset.get("paired_text_is_identical") is not True:
        raise ValueError("frozen subset manifest does not certify text-prompt parity")
    vision_packet_rows = _read_jsonl(vision_packets)
    text_packet_rows = _read_jsonl(text_packets)
    qids = {row["question_id"] for row in vision_packet_rows}
    if len(qids) != len(vision_packet_rows) or qids != {row["question_id"] for row in text_packet_rows}:
        raise ValueError("frozen Track C and text control packets have different question IDs")
    vision_by_qid = {row["question_id"]: row for row in vision_packet_rows}
    text_by_qid = {row["question_id"]: row for row in text_packet_rows}
    for qid in qids:
        vision_packet, text_packet = vision_by_qid[qid], text_by_qid[qid]
        if (vision_packet.get("source_evidence_sha256") != text_packet.get("evidence_sha256")
                or vision_packet.get("evidence") != text_packet.get("evidence")):
            raise ValueError(f"Track C text evidence differs from frozen Track B control for {qid}")
        images = vision_packet.get("images") or []
        expected_image = subset.get("image_sha256_by_question_id", {}).get(qid)
        if len(images) != 1 or (expected_image and images[0].get("sha256") != expected_image):
            raise ValueError(f"Track C image selection/hash mismatch for {qid}")

    vision_latest = _latest(vision_run / "predictions.jsonl")
    text_latest = _latest(text_run / "predictions.jsonl")
    vision_receipts = _receipts(vision_reviews)
    text_receipts = _receipts(text_reviews)
    vision_manifest = json.loads((vision_run / "manifest.json").read_text(encoding="utf-8"))
    text_manifest = json.loads((text_run / "manifest.json").read_text(encoding="utf-8"))
    if vision_manifest.get("prompt_sha256") != text_manifest.get("prompt_sha256"):
        raise ValueError("Track B and Track C prompt hashes differ")
    if vision_manifest.get("prompt_sha256") != subset.get("prompt_sha256"):
        raise ValueError("run prompt hash does not match frozen subset manifest")

    selected_digests = sorted({row["model_digest"] for row in vision_latest.values()
                               if row.get("question_id") in qids})
    model_results = []
    for digest in selected_digests:
        vision_rows = {qid: vision_latest[(digest, qid)] for qid in qids if (digest, qid) in vision_latest}
        text_rows = {qid: text_latest[(digest, qid)] for qid in qids if (digest, qid) in text_latest}
        if set(vision_rows) != qids or set(text_rows) != qids:
            raise ValueError(f"question coverage mismatch for digest {digest}")
        tags = {row.get("model_tag") for row in vision_rows.values()} | {row.get("model_tag") for row in text_rows.values()}
        if len(tags) != 1:
            raise ValueError(f"model tag mismatch for digest {digest}: {tags}")
        tag = next(iter(tags))
        for qid in qids:
            vr, tr = vision_rows[qid], text_rows[qid]
            if vr.get("model_digest") != tr.get("model_digest") or vr.get("quantization") != tr.get("quantization"):
                raise ValueError(f"model digest/quantization mismatch for {tag} {qid}")
            if vr.get("input_sha256") != tr.get("input_sha256"):
                raise ValueError(f"text prompt input hash mismatch for {tag} {qid}")
            if (vr.get("evidence_sha256") != vision_by_qid[qid].get("evidence_sha256")
                    or tr.get("evidence_sha256") != text_by_qid[qid].get("evidence_sha256")):
                raise ValueError(f"prediction evidence hash does not match frozen packet for {tag} {qid}")
            if vr.get("prompt_sha256") != tr.get("prompt_sha256"):
                raise ValueError(f"per-case prompt hash mismatch for {tag} {qid}")
            expected_prompt = subset.get("paired_prompt_sha256_by_question_id", {}).get(qid)
            if expected_prompt and (vr.get("input_sha256") != expected_prompt
                                    or tr.get("input_sha256") != expected_prompt):
                raise ValueError(f"per-question frozen prompt hash mismatch for {tag} {qid}")
        text_scores = {qid: _score(row, text_receipts) for qid, row in text_rows.items()}
        vision_scores = {qid: _score(row, vision_receipts) for qid, row in vision_rows.items()}
        if any(value is None for value in text_scores.values()) or any(value is None for value in vision_scores.values()):
            raise ValueError("matched dev subset contains a preflight-excluded case")
        paired = [(text_scores[qid], vision_scores[qid]) for qid in sorted(qids)]
        both_completed = [qid for qid in sorted(qids)
                          if text_rows[qid].get("status") == "completed"
                          and vision_rows[qid].get("status") == "completed"]
        completed_pairs = [(text_scores[qid], vision_scores[qid]) for qid in both_completed]
        categories = {}
        for category in sorted({row["category"] for row in vision_rows.values()}):
            category_ids = sorted(qid for qid in qids if vision_rows[qid]["category"] == category)
            complete_category_ids = [qid for qid in category_ids if qid in both_completed]
            categories[category] = {
                "all_eligible": _paired_stats([(text_scores[qid], vision_scores[qid]) for qid in category_ids]),
                "both_completed": _paired_stats([(text_scores[qid], vision_scores[qid])
                                                  for qid in complete_category_ids]),
                "track_b_failures": sum(text_rows[qid].get("status") != "completed" for qid in category_ids),
                "track_c_failures": sum(vision_rows[qid].get("status") != "completed" for qid in category_ids),
            }
        model_results.append({
            "model_tag": tag, "model_digest": digest,
            "quantization": vision_rows[next(iter(qids))].get("quantization"),
            "track_b_failures": sum(row.get("status") != "completed" for row in text_rows.values()),
            "track_c_failures": sum(row.get("status") != "completed" for row in vision_rows.values()),
            "track_b_status_counts": dict(collections.Counter(row.get("status") for row in text_rows.values())),
            "track_c_status_counts": dict(collections.Counter(row.get("status") for row in vision_rows.values())),
            "all_eligible": _paired_stats(paired), "both_completed": _paired_stats(completed_pairs),
            "by_category": categories,
            "examples_c_wins": [{"question_id": qid, "category": vision_rows[qid]["category"],
                                 "track_b": text_scores[qid], "track_c": vision_scores[qid]}
                                for qid in both_completed if vision_scores[qid] > text_scores[qid]][:5],
            "examples_c_losses": [{"question_id": qid, "category": vision_rows[qid]["category"],
                                   "track_b": text_scores[qid], "track_c": vision_scores[qid]}
                                  for qid in both_completed if vision_scores[qid] < text_scores[qid]][:5],
        })

    return {
        "schema_version": "track_c_paired_comparison_v1",
        "provenance": "AI-only reviews; not human/expert gold",
        "question_count": len(qids), "category_counts": dict(collections.Counter(
            row["category"] for row in vision_packet_rows)),
        "paired_input_hashes_match": True,
        "prompt_sha256": vision_manifest.get("prompt_sha256"),
        "vision_packet_sha256": _sha(vision_packets),
        "text_control_packet_sha256": _sha(text_packets),
        "vision_prediction_history_sha256": _sha(vision_run / "predictions.jsonl"),
        "text_prediction_history_sha256": _sha(text_run / "predictions.jsonl"),
        "vision_review_sha256": _sha(vision_reviews), "text_review_sha256": _sha(text_reviews),
        "vision_git_sha": vision_manifest.get("git_sha"), "text_git_sha": text_manifest.get("git_sha"),
        "models": model_results,
    }


def _markdown(report):
    fmt = lambda value: "n/a" if value is None else f"{value:.3f}"
    category_counts = ", ".join(f"{name}={count}" for name, count in sorted(report["category_counts"].items()))
    lines = ["# Track C paired comparison: vision vs fixed text control", "",
             f"- Questions: {report['question_count']} paired cases ({category_counts})",
             f"- Same prompt/input hashes: {report['paired_input_hashes_match']}",
             f"- Prompt SHA-256: `{report['prompt_sha256']}`",
             "- Scores use AI-only review receipts; they are not human/expert gold.", "",
             "| Model | Scope | Category | n | Track B text | Track C vision | C − B | 95% paired bootstrap CI | C wins / ties / losses | B failures | C failures |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for model in report["models"]:
        scopes = [("All eligible (failures=0)", "all_eligible"), ("Both completed", "both_completed")]
        rows = [("all", model["all_eligible"], model["track_b_failures"], model["track_c_failures"])]
        for category, details in model["by_category"].items():
            rows.append((category, details["all_eligible"], details["track_b_failures"], details["track_c_failures"]))
        for category, all_stats, b_fail, c_fail in rows:
            for scope_label, scope_key in scopes:
                stats = all_stats if scope_key == "all_eligible" else (
                    model["both_completed"] if category == "all" else model["by_category"][category]["both_completed"])
                ci = stats["ci95_delta"]
                ci_text = "n/a" if ci is None else f"[{ci[0]:+.3f}, {ci[1]:+.3f}]"
                lines.append(
                    f"| {model['model_tag']} ({model['quantization']}) | {scope_label} | {category} | {stats['n']} | "
                    f"{fmt(stats['mean_track_b'])} | {fmt(stats['mean_track_c'])} | "
                    f"{fmt(stats['mean_delta_c_minus_b'])} | {ci_text} | "
                    f"{stats['wins_c']} / {stats['ties']} / {stats['losses_c']} | {b_fail} | {c_fail} |")
    for model in report["models"]:
        lines.extend(["", f"## {model['model_tag']} examples", ""])
        lines.append("C wins (up to five): " + (
            ", ".join(f"{x['question_id']} ({x['track_b']}→{x['track_c']})" for x in model["examples_c_wins"])
            or "none"))
        lines.append("C losses (up to five): " + (
            ", ".join(f"{x['question_id']} ({x['track_b']}→{x['track_c']})" for x in model["examples_c_losses"])
            or "none"))
    lines.extend(["", "## Reproducibility", "",
                  f"- Vision packet SHA-256: `{report['vision_packet_sha256']}`",
                  f"- Text control packet SHA-256: `{report['text_control_packet_sha256']}`",
                  f"- Track C prediction history SHA-256: `{report['vision_prediction_history_sha256']}`",
                  f"- Track B prediction history SHA-256: `{report['text_prediction_history_sha256']}`",
                  f"- Track C reviews SHA-256: `{report['vision_review_sha256']}`",
                  f"- Track B reviews SHA-256: `{report['text_review_sha256']}`",
                  f"- Track C run commit: `{report['vision_git_sha']}`",
                  f"- Track B run commit: `{report['text_git_sha']}`", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vision-run", type=Path, required=True)
    parser.add_argument("--text-run", type=Path, required=True)
    parser.add_argument("--vision-reviews", type=Path, required=True)
    parser.add_argument("--text-reviews", type=Path, required=True)
    parser.add_argument("--vision-packets", type=Path, required=True)
    parser.add_argument("--text-packets", type=Path, required=True)
    parser.add_argument("--subset-manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.vision_run, args.text_run, args.vision_reviews, args.text_reviews,
                     args.vision_packets, args.text_packets, args.subset_manifest)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_markdown(result), encoding="utf-8")
    print(json.dumps({"question_count": result["question_count"], "models": len(result["models"]),
                      "output_json": str(args.output_json), "output_md": str(args.output_md)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
