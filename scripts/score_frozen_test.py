"""Score the one-time frozen-test run against its predeclared freeze."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import PROJECT_ROOT
from src.benchmark.local_common import file_hash, read_json, read_rows
from src.benchmark.scoring_local import EXCLUDED, export_metrics, review_id, summarize


def _latest(run_dir: Path):
    latest = {}
    for row in read_rows(run_dir / "predictions.jsonl"):
        latest[(row["model_digest"], row["question_id"])] = row
    return latest


def _receipt_map(path: Path, expected_protocol_sha256: str):
    receipts = {}
    for row in read_rows(path):
        rid = row.get("review_id")
        if not rid or rid in receipts:
            raise ValueError(f"Duplicate/missing review receipt: {rid}")
        if row.get("correctness") not in (0, 0.5, 1) or isinstance(row.get("correctness"), bool):
            raise ValueError(f"Invalid/pending correctness: {rid}")
        if row.get("judge_protocol_sha256") != expected_protocol_sha256:
            raise ValueError(f"Review protocol hash mismatch: {rid}")
        receipts[rid] = row
    return receipts


def _score(row, receipts):
    if row.get("status") in EXCLUDED:
        return None
    if row.get("status") != "completed":
        return 0.0
    receipt = receipts[review_id(row)]
    return float(receipt["correctness"])


def _bootstrap_delta(differences):
    if not differences:
        return {"n": 0, "delta": None, "ci95": None}
    values = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(20261115)
    draws = rng.choice(values, size=(10000, len(values)), replace=True).mean(axis=1)
    return {"n": len(values), "delta": float(values.mean()),
            "ci95": [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))]}


def score(run_dir: Path, packets_path: Path, freeze_path: Path, reviews_path: Path,
          output_json: Path, output_md: Path):
    run_dir, packets_path, freeze_path, reviews_path, output_json, output_md = (
        path.resolve() for path in (run_dir, packets_path, freeze_path, reviews_path, output_json, output_md)
    )
    if output_json.exists() or output_md.exists() or (run_dir / "metrics.json").exists():
        raise FileExistsError("Refusing to re-score or overwrite frozen-test reports")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    if freeze.get("status") != "frozen_before_test" or freeze.get("candidate_commit_sha") != head:
        raise ValueError("Current code is not at the frozen candidate commit")
    candidate_config = PROJECT_ROOT / freeze.get("candidate_config_path", "")
    candidate_doc = read_json(candidate_config)
    if (file_hash(candidate_config) != freeze.get("candidate_config_sha256")
            or candidate_doc.get("models") != freeze.get("models")
            or candidate_doc.get("thresholds") != freeze.get("thresholds")
            or candidate_doc.get("benchmark_code_sha256") != freeze.get("benchmark_code_sha256")
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
        raise ValueError("Judge protocol differs from the pretest freeze")
    protocol_path = PROJECT_ROOT / freeze.get("protocol_path", "")
    if file_hash(protocol_path) != freeze.get("protocol_sha256"):
        raise ValueError("Test protocol differs from the pretest freeze")
    run_manifest = read_json(run_dir / "manifest.json")
    packets_manifest = read_json(packets_path.with_suffix(".manifest.json"))
    if (run_manifest.get("git_sha") != head or run_manifest.get("protocol_sha256") != freeze.get("protocol_sha256")
            or run_manifest.get("packets_sha256") != file_hash(packets_path)
            or run_manifest.get("track") not in (None, "retrieved_text_frozen")
            or (run_manifest.get("protocol") or {}).get("split") != "test"
            or run_manifest.get("split") != "test"
            or run_manifest.get("freeze_manifest_sha256") != file_hash(freeze_path)
            or run_manifest.get("test_frozen_sha256") != freeze.get("test_frozen_sha256")
            or run_manifest.get("prompt_sha256") != freeze.get("prompt_sha256")
            or run_manifest.get("code_sha256") != freeze.get("benchmark_code_sha256")):
        raise ValueError("Run manifest differs from frozen commit/config/input")
    if (packets_manifest.get("freeze_manifest_sha256") != file_hash(freeze_path)
            or packets_manifest.get("test_frozen_sha256") != freeze.get("test_frozen_sha256")
            or packets_manifest.get("packets") != freeze.get("expected_test_question_count")):
        raise ValueError("Frozen packet manifest does not match the freeze")

    latest = _latest(run_dir)
    rows = list(latest.values())
    expected = {(m["model_digest"], qid) for m in freeze["models"]
                for qid in packets_manifest.get("question_ids", [])}
    if set(latest) != expected:
        raise ValueError(f"Final test prediction coverage mismatch: {len(expected - set(latest))} missing, "
                         f"{len(set(latest) - expected)} extra")
    model_rows = {}
    for model in freeze["models"]:
        key = (model["model_tag"], model["model_digest"])
        selected = {qid: row for (digest, qid), row in latest.items() if digest == model["model_digest"]}
        if any(row.get("model_tag") != model["model_tag"] or row.get("quantization") != model["quantization"]
               for row in selected.values()):
            raise ValueError(f"Model identity/quantization mismatch: {model['model_tag']}")
        model_rows[key] = selected

    receipts = _receipt_map(reviews_path, freeze["judge_protocol_sha256"])
    completed_ids = {review_id(row) for row in rows if row.get("status") == "completed"}
    if set(receipts) != completed_ids:
        raise ValueError(f"Review coverage mismatch: {len(completed_ids - set(receipts))} missing, "
                         f"{len(set(receipts) - completed_ids)} extra")
    for rid, receipt in receipts.items():
        pred = next(row for row in rows if review_id(row) == rid)
        for field in ("question_id", "input_sha256", "packet_sha256", "evidence_sha256"):
            if receipt.get(field) != pred.get(field):
                raise ValueError(f"Review identity mismatch in {field}: {rid}")

    metrics = summarize(rows, list(receipts.values()))
    export_metrics(metrics, run_dir)

    candidate = next(m for m in freeze["models"] if m["role"] == "candidate")
    baseline = next(m for m in freeze["models"] if m["role"] == "baseline")
    candidate_rows = model_rows[(candidate["model_tag"], candidate["model_digest"])]
    baseline_rows = model_rows[(baseline["model_tag"], baseline["model_digest"])]
    category_names = sorted({row["category"] for row in rows})

    def stats(by_qid):
        scores = {qid: _score(row, receipts) for qid, row in by_qid.items()}
        eligible = [value for value in scores.values() if value is not None]
        completed = [scores[qid] for qid, row in by_qid.items() if row.get("status") == "completed"]
        return {
            "questions": len(by_qid),
            "completed": sum(row.get("status") == "completed" for row in by_qid.values()),
            "technical_failures": sum(row.get("status") not in EXCLUDED and row.get("status") != "completed"
                                       for row in by_qid.values()),
            "excluded": sum(value is None for value in scores.values()),
            "all_eligible_mean_correctness": float(np.mean(eligible)) if eligible else None,
            "completed_mean_correctness": float(np.mean(completed)) if completed else None,
            "category_all_eligible_mean_correctness": {
                category: float(np.mean([scores[qid] for qid, row in by_qid.items()
                                         if row.get("category") == category and scores[qid] is not None]))
                if any(row.get("category") == category and scores[qid] is not None
                       for qid, row in by_qid.items()) else None
                for category in category_names
            },
        }

    candidate_stats, baseline_stats = stats(candidate_rows), stats(baseline_rows)
    paired_ids = sorted(set(candidate_rows) & set(baseline_rows))
    deltas = []
    for qid in paired_ids:
        a, b = _score(candidate_rows[qid], receipts), _score(baseline_rows[qid], receipts)
        if a is not None and b is not None:
            deltas.append(a - b)
    paired = _bootstrap_delta(deltas)
    thresholds = freeze["thresholds"]
    category_values = candidate_stats["category_all_eligible_mean_correctness"]
    checks = {
        "candidate_overall_min": candidate_stats["all_eligible_mean_correctness"] >= thresholds["overall_min"],
        "candidate_each_category_min": all(
            value is not None and value >= thresholds["category_min"] for value in category_values.values()
        ),
        "candidate_technical_failures_max": candidate_stats["technical_failures"] <= thresholds["technical_failures_max"],
        "candidate_paired_gain_min": paired["delta"] is not None and paired["delta"] >= thresholds["paired_gain_min"],
        "candidate_paired_ci_lower_gt_zero": paired["ci95"] is not None and paired["ci95"][0] > 0,
    }
    report = {
        "schema_version": "frozen_test_candidate_report_v1",
        "status": "final held-out test; no tuning permitted",
        "human_expert_gold": False,
        "judgment": "AI-only blind rubric reviews; not human/expert gold",
        "freeze_commit_sha": head,
        "freeze_manifest_sha256": file_hash(freeze_path),
        "test_frozen_sha256": freeze["test_frozen_sha256"],
        "packet_sha256": file_hash(packets_path),
        "protocol_sha256": freeze["protocol_sha256"],
        "judge_protocol_sha256": freeze["judge_protocol_sha256"],
        "candidate": {**candidate, **candidate_stats},
        "baseline": {**baseline, **baseline_stats},
        "paired_candidate_minus_baseline_all_eligible": paired,
        "thresholds": thresholds,
        "threshold_checks": checks,
        "candidate_passes_all_thresholds": all(checks.values()),
        "metrics_path": str(run_dir / "metrics.json"),
        "reviews_sha256": file_hash(reviews_path),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Frozen test result", "",
        "This report evaluates the already-frozen candidate and baseline once on the 268-question held-out split. It uses AI-only blind rubric reviews, not human/expert gold. No tuning may be based on this result.", "",
        f"- Freeze commit: `{head}`",
        f"- Test SHA-256: `{report['test_frozen_sha256']}`",
        f"- Packet SHA-256: `{report['packet_sha256']}`",
        f"- Protocol SHA-256: `{report['protocol_sha256']}`", "",
        "| Role | Model | Digest | Quant. | All-eligible mean | Completed-only mean | Failures |", "|---|---|---|---|---:|---:|---:|",
    ]
    for role, model, values in (("Candidate", candidate, candidate_stats), ("Baseline", baseline, baseline_stats)):
        mean = values["all_eligible_mean_correctness"]
        complete_mean = values["completed_mean_correctness"]
        lines.append(f"| {role} | {model['model_tag']} | `{model['model_digest']}` | {model['quantization']} | "
                     f"{mean:.3f} | {complete_mean:.3f} | {values['technical_failures']} |")
    lines += ["", f"Paired candidate-minus-baseline delta: **{paired['delta']:.3f}** over {paired['n']} eligible matched questions; 95% bootstrap CI `{paired['ci95']}`.", "",
              "| Gate | Threshold | Result |", "|---|---:|---|"]
    gate_values = [
        ("Candidate overall", thresholds["overall_min"], candidate_stats["all_eligible_mean_correctness"], "candidate_overall_min"),
        ("Each candidate category", thresholds["category_min"], min((v for v in category_values.values() if v is not None), default=None), "candidate_each_category_min"),
        ("Candidate technical failures", thresholds["technical_failures_max"], candidate_stats["technical_failures"], "candidate_technical_failures_max"),
        ("Paired candidate gain", thresholds["paired_gain_min"], paired["delta"], "candidate_paired_gain_min"),
        ("Paired CI lower bound", "> 0", paired["ci95"][0] if paired["ci95"] else None, "candidate_paired_ci_lower_gt_zero"),
    ]
    for label, threshold, value, key in gate_values:
        lines.append(f"| {label} | {threshold} | {value} — {'PASS' if checks[key] else 'FAIL'} |")
    lines += ["", "## Category scores", "", "| Category | Candidate | Baseline |", "|---|---:|---:|"]
    for category in category_names:
        a = candidate_stats["category_all_eligible_mean_correctness"][category]
        b = baseline_stats["category_all_eligible_mean_correctness"][category]
        lines.append(f"| {category} | {a if a is not None else 'n/a'} | {b if b is not None else 'n/a'} |")
    lines += ["", f"Overall threshold outcome: **{'PASS' if all(checks.values()) else 'FAIL'}**.",
              "This one-time held-out result is descriptive for the frozen benchmark only. If the candidate fails, issue a new version and use a new held-out split; do not tune against these 268 questions."]
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    report = score(args.run_dir, args.packets, args.freeze_manifest, args.reviews,
                   args.output_json, args.output_md)
    print(json.dumps({"candidate_passes_all_thresholds": report["candidate_passes_all_thresholds"],
                      "output_json": str(args.output_json), "output_md": str(args.output_md)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
