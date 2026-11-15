"""Compare matched local-LLM benchmark repeats without changing source runs."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import EXCLUDED, review_id


SEEDS = (42, 43, 44)
TRACKS = ("gold_text_verified", "retrieved_text_frozen")
SEED_PAIRS = ((42, 43), (42, 44), (43, 44))
# These three files changed after the seed-42 run. They were audited: the
# CLI change exposes the same explicit protocol path, scoring changes are
# post-inference, and the prompt-render change removes an image-page note.
# Exact per-question input hashes below must still match for these text tracks.
AUDITED_CODE_SHA_CHANGES = {
    "src\\benchmark\\local_cli.py",
    "src\\benchmark\\runner_local.py",
    "src\\benchmark\\scoring_local.py",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _latest_predictions(run_dir: Path):
    latest = {}
    for row in _read_jsonl(run_dir / "predictions.jsonl"):
        latest[(row["model_digest"], row["question_id"])] = row
    return latest


def _review_map(path: Path):
    result = {}
    for row in _read_jsonl(path):
        rid = row["review_id"]
        if rid in result:
            raise ValueError(f"Duplicate review receipt: {rid}")
        result[rid] = row
    return result


def _score(row, receipts):
    status = row.get("status")
    if status in EXCLUDED:
        return None
    if status != "completed":
        return 0.0
    receipt = receipts.get(review_id(row))
    if receipt is None:
        raise ValueError(f"Missing review receipt: {row.get('model_tag')} {row.get('track')} {row.get('question_id')}")
    score = receipt.get("correctness")
    if isinstance(score, bool) or score not in (0, 0.5, 1):
        raise ValueError(f"Invalid or pending correctness receipt: {receipt.get('review_id')}")
    return float(score)


def _mean(values):
    values = [value for value in values if value is not None]
    return float(np.mean(values)) if values else None


def _paired_delta(left_rows, right_rows, conditional=False, seed=20261115):
    differences, left_scores, right_scores = [], [], []
    for qid in sorted(left_rows):
        left, right = left_rows[qid], right_rows[qid]
        if conditional and (left["status"] != "completed" or right["status"] != "completed"):
            continue
        a, b = left["score"], right["score"]
        if a is None or b is None:
            continue
        differences.append(b - a)
        left_scores.append(a)
        right_scores.append(b)
    if not differences:
        return {"n": 0, "left_mean": None, "right_mean": None, "delta_right_minus_left": None,
                "ci95_delta": None, "wins_right": 0, "ties": 0, "losses_right": 0}
    values = np.asarray(differences, dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(10000, len(values)), replace=True).mean(axis=1)
    return {
        "n": len(values), "left_mean": _mean(left_scores), "right_mean": _mean(right_scores),
        "delta_right_minus_left": float(values.mean()),
        "ci95_delta": [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))],
        "wins_right": int(np.sum(values > 0)), "ties": int(np.sum(values == 0)),
        "losses_right": int(np.sum(values < 0)),
    }


def _seed_summary(rows):
    eligible = [row["score"] for row in rows.values() if row["score"] is not None]
    completed = [row["score"] for row in rows.values() if row["status"] == "completed"]
    categories = defaultdict(list)
    citations = {"true": 0, "false": 0, "null": 0}
    review_counts = {"transferred_from_seed42": 0, "fresh_or_other": 0}
    failures = 0
    for row in rows.values():
        if row["category"]:
            if row["score"] is not None:
                categories[row["category"]].append(row["score"])
        if row["status"] not in EXCLUDED and row["status"] != "completed":
            failures += 1
        receipt = row.get("receipt")
        if receipt:
            supported = receipt.get("citation_supported")
            citations["true" if supported is True else "false" if supported is False else "null"] += 1
            provenance = receipt.get("provenance") or {}
            if provenance.get("transfer_source_seed") == 42:
                review_counts["transferred_from_seed42"] += 1
            else:
                review_counts["fresh_or_other"] += 1
    return {
        "questions": len(rows), "completed": sum(r["status"] == "completed" for r in rows.values()),
        "technical_failures": failures,
        "excluded": sum(r["score"] is None for r in rows.values()),
        "all_eligible_mean_correctness": _mean(eligible),
        "completed_mean_correctness": _mean(completed),
        "category_all_eligible_mean_correctness": {k: _mean(v) for k, v in sorted(categories.items())},
        "citation_supported_true_false_null": citations,
        "review_receipts_transferred_fresh": review_counts,
    }


def _manifest_projection(run_dir: Path):
    manifest = _read_json(run_dir / "manifest.json")
    return manifest, {
        "git_sha": manifest.get("git_sha"), "code_sha256": manifest.get("code_sha256"),
        "prompt_sha256": manifest.get("prompt_sha256"), "packets_sha256": manifest.get("packets_sha256"),
        "track": manifest.get("track"),
        "protocol_without_seed": {k: v for k, v in (manifest.get("protocol") or {}).items() if k != "seed"},
    }


def _code_sha_diff(reference: dict, current: dict, seed: int):
    reference_files = reference.get("code_sha256") or {}
    current_files = current.get("code_sha256") or {}
    if reference_files == current_files:
        return {}
    if not isinstance(reference_files, dict) or not isinstance(current_files, dict):
        raise ValueError("Run manifest code_sha256 must be a file-to-hash mapping")
    differences = {
        path: {"seed42": reference_files.get(path), f"seed{seed}": current_files.get(path)}
        for path in sorted(set(reference_files) | set(current_files))
        if reference_files.get(path) != current_files.get(path)
    }
    unexpected = set(differences) - AUDITED_CODE_SHA_CHANGES
    if unexpected:
        raise ValueError(f"Seed {seed}: code hashes differ outside audited files: {sorted(unexpected)}")
    return differences


def _load_run(run_dir: Path, reviews_path: Path, seed: int, expected_track: str):
    manifest, projection = _manifest_projection(run_dir)
    protocol = manifest.get("protocol") or {}
    if protocol.get("seed") != seed:
        raise ValueError(f"{run_dir}: manifest protocol seed {protocol.get('seed')} != {seed}")
    predictions, receipts = _latest_predictions(run_dir), _review_map(reviews_path)
    if not predictions:
        raise ValueError(f"No predictions in {run_dir}")
    rows_by_model = defaultdict(dict)
    model_configs = {}
    for (digest, qid), pred in predictions.items():
        if pred.get("track") != expected_track:
            raise ValueError(f"{run_dir}/{qid}: unexpected track {pred.get('track')}")
        model_key = (pred["model_tag"], digest)
        rows_by_model[model_key][qid] = {
            **pred, "score": _score(pred, receipts),
            "receipt": receipts.get(review_id(pred)) if pred.get("status") == "completed" else None,
        }
        config = {k: pred.get(k) for k in ("model_tag", "model_digest", "quantization")}
        previous = model_configs.setdefault(model_key, config)
        if previous != config:
            raise ValueError(f"{run_dir}: model configuration changes within {model_key}")
    return {"manifest": manifest, "projection": projection, "models": rows_by_model,
            "model_configs": model_configs, "reviews_path": str(reviews_path)}


def _verify_repeats(runs, expected_questions: int):
    base = runs[42]
    repeat_model_sets = [set(runs[seed]["models"]) for seed in SEEDS[1:]]
    models = set.intersection(set(base["models"]), *repeat_model_sets)
    if not models:
        raise ValueError("No baseline model runs")
    for seed in SEEDS[1:]:
        if set(runs[seed]["models"]) != models:
            raise ValueError(f"Seed {seed}: repeat model tag/digest set differs from other repeats")
    ref_projection = base["projection"]
    code_sha_differences = {}
    for seed in SEEDS[1:]:
        projection = runs[seed]["projection"]
        for key in ("git_sha", "prompt_sha256", "packets_sha256", "track", "protocol_without_seed"):
            if projection.get(key) != ref_projection.get(key):
                raise ValueError(f"Seed {seed}: frozen run field differs: {key}")
        code_sha_differences[str(seed)] = _code_sha_diff(
            base["manifest"], runs[seed]["manifest"], seed
        )
    for model_key in models:
        reference_ids = set(base["models"][model_key])
        if len(reference_ids) != expected_questions:
            raise ValueError(f"{model_key}: expected {expected_questions} baseline qids, found {len(reference_ids)}")
        for seed in SEEDS:
            if runs[seed]["model_configs"][model_key] != base["model_configs"][model_key]:
                raise ValueError(f"{model_key}, seed {seed}: model digest/quantization differs")
            rows = runs[seed]["models"][model_key]
            if set(rows) != reference_ids:
                raise ValueError(f"{model_key}, seed {seed}: question IDs differ")
            for qid in reference_ids:
                original, current = base["models"][model_key][qid], rows[qid]
                for field in ("input_sha256", "evidence_sha256", "prompt_sha256", "packet_sha256", "track", "category"):
                    if current.get(field) != original.get(field):
                        raise ValueError(f"{model_key}/{qid}, seed {seed}: {field} differs")
    return models, code_sha_differences


def compare_track(track: str, run_dirs: dict[int, Path], review_paths: dict[int, Path], expected_questions=120):
    runs = {seed: _load_run(run_dirs[seed], review_paths[seed], seed, track) for seed in SEEDS}
    model_keys, code_sha_differences = _verify_repeats(runs, expected_questions)
    models = []
    for model_key in sorted(model_keys):
        seed_rows = {seed: runs[seed]["models"][model_key] for seed in SEEDS}
        summaries = {str(seed): _seed_summary(seed_rows[seed]) for seed in SEEDS}
        qids = sorted(seed_rows[42])
        pairwise = {}
        exact_repeat = {}
        for left_seed, right_seed in SEED_PAIRS:
            left, right = seed_rows[left_seed], seed_rows[right_seed]
            key = f"{left_seed}_vs_{right_seed}"
            pairwise[key] = {
                "all_eligible": _paired_delta(left, right, conditional=False,
                                                seed=20261115 + left_seed * 100 + right_seed),
                "both_completed": _paired_delta(left, right, conditional=True,
                                                  seed=20261115 + right_seed * 100 + left_seed),
            }
            common = [qid for qid in qids if left[qid]["status"] == "completed" and
                      right[qid]["status"] == "completed"]
            exact_repeat[key] = {
                "n_both_completed": len(common),
                "exact_answer_matches": sum(left[qid].get("answer") == right[qid].get("answer") for qid in common),
                "exact_answer_match_rate": _mean([left[qid].get("answer") == right[qid].get("answer")
                                                   for qid in common]),
            }
        complete_three = [qid for qid in qids if all(seed_rows[s][qid]["status"] == "completed" for s in SEEDS)]
        stable = sum(len({seed_rows[s][qid]["score"] for s in SEEDS}) == 1 for qid in complete_three)
        models.append({
            "model_tag": model_key[0], "model_digest": model_key[1],
            "quantization": runs[42]["model_configs"][model_key].get("quantization"),
            "seed_metrics": summaries,
            "mean_across_seeds_all_eligible": _mean([summaries[str(s)]["all_eligible_mean_correctness"]
                                                       for s in SEEDS]),
            "population_std_across_seed_means": (float(np.std([summaries[str(s)]["all_eligible_mean_correctness"]
                                                                for s in SEEDS], ddof=0))
                                                  if all(summaries[str(s)]["all_eligible_mean_correctness"] is not None
                                                         for s in SEEDS) else None),
            "pairwise_seed_score_deltas": pairwise,
            "pairwise_exact_answer_repeat": exact_repeat,
            "all_three_seed_correctness_stable_cases": {"n_all_completed": len(complete_three), "n_stable": stable,
                                                          "rate": stable / len(complete_three) if complete_three else None},
        })
    return {
        "track": track,
        "run_manifests": {str(seed): {"run_dir": str(run_dirs[seed]),
                                       "reviews": str(review_paths[seed]),
                                       "git_sha": runs[seed]["projection"].get("git_sha"),
                                       "prompt_sha256": runs[seed]["projection"].get("prompt_sha256"),
                                       "packets_sha256": runs[seed]["projection"].get("packets_sha256")}
                           for seed in SEEDS},
        "code_sha256_differences_vs_seed42": code_sha_differences,
        "models": models,
    }


def build_report(run_dirs: dict[str, Path], review_paths: dict[str, Path], expected_questions=120):
    results = {}
    for track, suffix in (("gold_text_verified", "a"), ("retrieved_text_frozen", "b")):
        dirs = {seed: run_dirs[f"{seed}_{suffix}"] for seed in SEEDS}
        reviews = {seed: review_paths[f"{seed}_{suffix}"] for seed in SEEDS}
        results[track] = compare_track(track, dirs, reviews, expected_questions)
    return {
        "schema_version": "local_llm_repeat_seeds_v1",
        "seed_protocol": "42, 43, 44; protocol fields except seed, prompt, packet, model digest/quant, and per-question input/evidence/prompt hashes are verified identical. Code hash differences are accepted only for the three audited CLI/scoring/prompt-render files and are listed per track.",
        "scoring": "AI-only review; eligible runtime failures score 0; excluded rows are reported separately; bootstrap intervals describe paired dev variation and are not held-out inference",
        "question_count_per_model_track": expected_questions,
        "tracks": results,
    }


def write_markdown(report: dict, path: Path):
    lines = ["# Local LLM repeat-seed stability", "",
             "Three same-config seeds are compared on the matched 120-question dev split. Prompt, packet, model digest/quantization, protocol (except seed), IDs, and per-question input/evidence/prompt hashes must match. Code hash differences are accepted only in the audited CLI, scoring, and prompt-render files; the exact differences are listed below and in the JSON report.",
             "",
             "All scores use AI-only review receipts, not human/expert gold. Runtime failures score 0 in all-eligible metrics; completed-only results are shown separately. Pairwise bootstrap intervals describe this dev sample and do not establish generalization.", ""]
    for track, result in report["tracks"].items():
        lines += [f"## {track}", "", "### Code hash differences vs seed 42", "",
                  "| Repeat seed | File | Seed 42 SHA-256 | Repeat SHA-256 |", "|---:|---|---|---|"]
        code_diffs = result.get("code_sha256_differences_vs_seed42", {})
        emitted = False
        for seed, differences in code_diffs.items():
            for filename, hashes in differences.items():
                emitted = True
                lines.append(f"| {seed} | `{filename}` | `{hashes['seed42']}` | `{hashes[f'seed{seed}']}` |")
        if not emitted:
            lines.append("| — | No differences | — | — |")
        lines += ["", "| Model | Quant. | Seed 42 | Seed 43 | Seed 44 | Mean | Across-seed SD | Failures 42/43/44 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
        for model in result["models"]:
            means = [model["seed_metrics"][str(seed)]["all_eligible_mean_correctness"] for seed in SEEDS]
            fails = [model["seed_metrics"][str(seed)]["technical_failures"] for seed in SEEDS]
            lines.append(f"| {model['model_tag']} | {model['quantization']} | " +
                         " | ".join(f"{value:.3f}" if value is not None else "n/a" for value in means) +
                         f" | {model['mean_across_seeds_all_eligible']:.3f} | {model['population_std_across_seed_means']:.3f} | " +
                         "/".join(str(x) for x in fails) + " |")
        lines += ["", "### Category scores by seed", "", "| Model | Category | Seed 42 | Seed 43 | Seed 44 |", "|---|---|---:|---:|---:|"]
        for model in result["models"]:
            categories = sorted(set().union(*(model["seed_metrics"][str(seed)]["category_all_eligible_mean_correctness"].keys()
                                             for seed in SEEDS)))
            for category in categories:
                values = [model["seed_metrics"][str(seed)]["category_all_eligible_mean_correctness"].get(category)
                          for seed in SEEDS]
                lines.append(f"| {model['model_tag']} | {category} | " +
                             " | ".join(f"{v:.3f}" if v is not None else "n/a" for v in values) + " |")
        lines += ["", "### Pairwise seed deltas", "", "| Model | Pair | All-eligible Δ | 95% CI | Completed-only Δ | Exact answer repeat |", "|---|---|---:|---|---:|---:|"]
        for model in result["models"]:
            for pair, stats in model["pairwise_seed_score_deltas"].items():
                eligible = stats["all_eligible"]
                complete = stats["both_completed"]
                ci = eligible["ci95_delta"]
                ci_s = "n/a" if ci is None else f"[{ci[0]:.3f}, {ci[1]:.3f}]"
                exact = model["pairwise_exact_answer_repeat"][pair]["exact_answer_match_rate"]
                lines.append(f"| {model['model_tag']} | {pair.replace('_vs_', ' vs ')} | "
                             f"{eligible['delta_right_minus_left']:.3f} | {ci_s} | "
                             f"{complete['delta_right_minus_left']:.3f} | "
                             f"{exact:.3f}" if exact is not None else
                             f"| {model['model_tag']} | {pair.replace('_vs_', ' vs ')} | "
                             f"{eligible['delta_right_minus_left']:.3f} | {ci_s} | "
                             f"{complete['delta_right_minus_left']:.3f} | n/a |")
        lines.append("")
    lines.append("Review-transfer counts, citation coverage, complete-only values, and failure details are in the JSON report.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--seed43-a", type=Path, required=True)
    parser.add_argument("--seed43-b", type=Path, required=True)
    parser.add_argument("--seed44-a", type=Path, required=True)
    parser.add_argument("--seed44-b", type=Path, required=True)
    parser.add_argument("--seed43-reviews-a", type=Path, required=True)
    parser.add_argument("--seed43-reviews-b", type=Path, required=True)
    parser.add_argument("--seed44-reviews-a", type=Path, required=True)
    parser.add_argument("--seed44-reviews-b", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    parser.add_argument("--expected-questions", type=int, default=120)
    args = parser.parse_args()
    run_dirs = {
        "42_a": args.baseline_root / "gold_full120", "42_b": args.baseline_root / "rag_full120",
        "43_a": args.seed43_a, "43_b": args.seed43_b, "44_a": args.seed44_a, "44_b": args.seed44_b,
    }
    review_paths = {
        "42_a": args.baseline_root / "judging/effective_reviews_ai_gold_full120_v1.jsonl",
        "42_b": args.baseline_root / "judging/effective_reviews_ai_rag_full120_v1.jsonl",
        "43_a": args.seed43_reviews_a, "43_b": args.seed43_reviews_b,
        "44_a": args.seed44_reviews_a, "44_b": args.seed44_reviews_b,
    }
    if args.output_json.exists() or args.output_md.exists():
        raise SystemExit("Refusing to overwrite existing repeat-seed report artifacts.")
    report = build_report(run_dirs, review_paths, args.expected_questions)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, args.output_md)
    print(json.dumps({"tracks": list(report["tracks"]), "models_per_track":
                      {k: len(v["models"]) for k, v in report["tracks"].items()},
                      "output_json": str(args.output_json), "output_md": str(args.output_md)}, indent=2))


if __name__ == "__main__":
    main()
