"""Create a paired Track A vs Track B report from a frozen dev run."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import EXCLUDED, review_id


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def _sha256(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest_rows(path: Path):
    latest = {}
    for row in _read_jsonl(path):
        latest[(row['model_digest'], row['question_id'])] = row
    return latest


def _score(row, receipts):
    if row['status'] in EXCLUDED:
        return None
    if row['status'] != 'completed':
        return 0.0
    receipt = receipts.get(review_id(row))
    if receipt is None:
        raise ValueError(f"Missing review receipt: {row['model_tag']} {row['track']} {row['question_id']}")
    score = receipt.get('correctness')
    if score is None:
        raise ValueError(f"Pending correctness receipt: {row['model_tag']} {row['track']} {row['question_id']}")
    return float(score)


def _paired_stats(pairs):
    diffs = np.asarray([b - a for a, b in pairs], dtype=float)
    if not len(diffs):
        return {'n': 0, 'mean_track_a': None, 'mean_track_b': None, 'mean_delta_b_minus_a': None,
                'wins_b': 0, 'ties': 0, 'losses_b': 0, 'ci95_delta': None}
    rng = np.random.default_rng(42)
    boot = rng.choice(diffs, size=(10000, len(diffs)), replace=True).mean(axis=1)
    return {'n': len(diffs), 'mean_track_a': float(np.mean([a for a, _ in pairs])),
            'mean_track_b': float(np.mean([b for _, b in pairs])),
            'mean_delta_b_minus_a': float(diffs.mean()),
            'wins_b': int(np.sum(diffs > 0)), 'ties': int(np.sum(diffs == 0)),
            'losses_b': int(np.sum(diffs < 0)),
            'ci95_delta': [float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]}


def compare(run_root: Path, reviews_path: Path):
    reviews = _read_jsonl(reviews_path)
    receipts = {}
    for receipt in reviews:
        rid = receipt['review_id']
        if rid in receipts:
            raise ValueError(f'Duplicate effective review receipt: {rid}')
        receipts[rid] = receipt

    root_manifest = run_root / 'supervisor_manifest.json'
    root_data = json.loads(root_manifest.read_text(encoding='utf-8'))
    tracks = {}
    track_manifests = {}
    for name in ('gold_full120', 'rag_full120'):
        track_dir = run_root / name
        manifest_path = track_dir / 'manifest.json'
        track_manifests[name] = json.loads(manifest_path.read_text(encoding='utf-8'))
        tracks[name] = _latest_rows(track_dir / 'predictions.jsonl')

    a_manifest, b_manifest = track_manifests['gold_full120'], track_manifests['rag_full120']
    if a_manifest.get('git_sha') != root_data.get('baseline') or b_manifest.get('git_sha') != root_data.get('baseline'):
        raise ValueError('Track manifest Git SHA differs from the frozen supervisor baseline')
    if a_manifest.get('packets_sha256') != root_data.get('gold_sha256'):
        raise ValueError('Track A packet hash differs from the frozen supervisor manifest')
    if b_manifest.get('packets_sha256') != root_data.get('rag_sha256'):
        raise ValueError('Track B packet hash differs from the frozen supervisor manifest')
    for key in ('code_sha256', 'prompt_sha256', 'protocol'):
        if a_manifest.get(key) != b_manifest.get(key):
            raise ValueError(f'Track A/B {key} differs')
    def model_projection(manifest):
        return {model['model_tag']: {key: model.get(key) for key in
                ('model_digest', 'quantization', 'thinking_mode', 'vision')}
                for model in manifest['models']}
    root_models = root_data.get('models') or {}
    if model_projection(a_manifest) != root_models or model_projection(b_manifest) != root_models:
        raise ValueError('Model digest/quantization/capability differs from the frozen supervisor manifest')

    by_model = defaultdict(lambda: {'gold_full120': {}, 'rag_full120': {}})
    for track_name, rows in tracks.items():
        for (digest, qid), row in rows.items():
            by_model[(row['model_tag'], digest)][track_name][qid] = row

    report = {'schema_version': 'paired_local_tracks_v1',
              'run_id': root_data.get('run_id', 'full_dev_v2_20261113'),
              'baseline_commit': root_data.get('baseline'),
              'supervisor_manifest_sha256': _sha256(root_manifest),
              'track_manifest_sha256': {name: _sha256(run_root / name / 'manifest.json') for name in track_manifests},
              'packet_sha256': {'gold_full120': a_manifest.get('packets_sha256'),
                                'rag_full120': b_manifest.get('packets_sha256')},
              'prompt_sha256': a_manifest.get('prompt_sha256'),
              'protocol': a_manifest.get('protocol'),
              'environment': a_manifest.get('environment'),
              'code_sha256': a_manifest.get('code_sha256'),
              'effective_reviews_sha256': _sha256(reviews_path),
              'models': []}
    for (tag, digest), pair_rows in sorted(by_model.items()):
        a_rows = pair_rows['gold_full120']
        b_rows = pair_rows['rag_full120']
        if set(a_rows) != set(b_rows):
            raise ValueError(f'{tag}: Track A/B question ID sets differ ({len(a_rows)} vs {len(b_rows)})')
        if len(a_rows) != 120:
            raise ValueError(f'{tag}: expected 120 paired questions, found {len(a_rows)}')
        categories = defaultdict(list)
        all_pairs = []
        excluded = 0
        rows_for_examples = []
        for qid in sorted(a_rows):
            a, b = a_rows[qid], b_rows[qid]
            if a.get('category') != b.get('category'):
                raise ValueError(f'{tag}/{qid}: category differs across tracks')
            sa, sb = _score(a, receipts), _score(b, receipts)
            if sa is None or sb is None:
                excluded += 1
                continue
            pair = (sa, sb)
            all_pairs.append(pair)
            categories[a['category']].append(pair)
            rows_for_examples.append((qid, a['category'], sa, sb, a, b))
        model = {'model_tag': tag, 'model_digest': digest, 'quantization': a_rows[next(iter(a_rows))].get('quantization'),
                 'paired_question_ids': len(a_rows), 'excluded_pairs': excluded,
                 'overall': _paired_stats(all_pairs),
                 'categories': {category: _paired_stats(pairs) for category, pairs in sorted(categories.items())},
                 'track_failures': {
                     'A': sum(row['status'] not in EXCLUDED and row['status'] != 'completed' for row in a_rows.values()),
                     'B': sum(row['status'] not in EXCLUDED and row['status'] != 'completed' for row in b_rows.values())},
                 'track_completed': {'A': sum(row['status'] == 'completed' for row in a_rows.values()),
                                     'B': sum(row['status'] == 'completed' for row in b_rows.values())},
                 'latency_p50_seconds': {
                     'A': float(np.median([r['latency_seconds'] for r in a_rows.values() if r['status'] == 'completed']))
                          if any(r['status'] == 'completed' for r in a_rows.values()) else None,
                     'B': float(np.median([r['latency_seconds'] for r in b_rows.values() if r['status'] == 'completed']))
                          if any(r['status'] == 'completed' for r in b_rows.values()) else None}}
        # Representative paired disagreements, with compact answer excerpts for error review.
        losses = sorted((r for r in rows_for_examples if r[3] < r[2]), key=lambda r: (r[3] - r[2], r[0]))[:5]
        gains = sorted((r for r in rows_for_examples if r[3] > r[2]), key=lambda r: (-(r[3] - r[2]), r[0]))[:5]
        model['examples'] = {
            'track_b_lower': [_example(r) for r in losses],
            'track_b_higher': [_example(r) for r in gains]}
        report['models'].append(model)
    return report


def _example(row):
    qid, category, a_score, b_score, a, b = row
    return {'question_id': qid, 'category': category, 'track_a_score': a_score,
            'track_b_score': b_score, 'track_a_status': a['status'], 'track_b_status': b['status'],
            'track_a_answer_excerpt': (a.get('answer') or '')[:450],
            'track_b_answer_excerpt': (b.get('answer') or '')[:450]}


def write_report(report, output_json: Path, output_md: Path):
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# Paired Track A vs Track B — full dev 120', '',
             f"Baseline commit: `{report['baseline_commit']}`  ",
             f"Prompt SHA-256: `{report['prompt_sha256']}`  ",
             f"Track A packet SHA-256: `{report['packet_sha256']['gold_full120']}`  ",
             f"Track B packet SHA-256: `{report['packet_sha256']['rag_full120']}`  ",
             f"Protocol: `{json.dumps(report['protocol'], sort_keys=True, ensure_ascii=False)}`  ",
             f"Hardware/software: `{json.dumps(report['environment'], sort_keys=True, ensure_ascii=False)}`", '',
             'Rubric scores use AI review receipts; no human/expert gold is claimed. Eligible technical failures score 0; excluded pairs are omitted and counted. Positive delta favors Track B. Bootstrap 95% intervals are descriptive on this dev set; they do not establish statistical superiority.', '',
             '| Model | Digest | Quant. | A score | B score | B − A | Fail A/B | p50 s A/B |',
             '|---|---|---|---:|---:|---:|---:|---:|']
    for model in report['models']:
        s = model['overall']
        lines.append(f"| {model['model_tag']} | `{model['model_digest']}` | {model['quantization']} | {s['mean_track_a']:.3f} | {s['mean_track_b']:.3f} | {s['mean_delta_b_minus_a']:.3f} | {model['track_failures']['A']}/{model['track_failures']['B']} | {model['latency_p50_seconds']['A']} / {model['latency_p50_seconds']['B']} |")
    lines += ['', '## Paired category results', '',
              '| Model | Category | n | Track A | Track B | B − A | 95% CI | B win/tie/loss |',
              '|---|---|---:|---:|---:|---:|---|---:|']
    for model in report['models']:
        for category, stats in [('all', model['overall']), *model['categories'].items()]:
            ci = stats['ci95_delta']
            ci_text = 'n/a' if ci is None else f'[{ci[0]:.3f}, {ci[1]:.3f}]'
            lines.append(f"| {model['model_tag']} | {category} | {stats['n']} | {stats['mean_track_a']} | {stats['mean_track_b']} | {stats['mean_delta_b_minus_a']} | {ci_text} | {stats['wins_b']}/{stats['ties']}/{stats['losses_b']} |")
    examples = []
    for model in report['models']:
        for example in model['examples']['track_b_lower']:
            if example['track_a_score'] == 1.0 and example['track_b_score'] == 0.0:
                examples.append({'model_tag': model['model_tag'], **example})
    # Prefer distinct question IDs where several models show the same degradation.
    frequency = defaultdict(int)
    for example in examples:
        frequency[example['question_id']] += 1
    examples.sort(key=lambda x: (-frequency[x['question_id']], x['question_id'], x['model_tag']))
    selected = []
    seen_questions = set()
    for example in examples:
        if example['question_id'] in seen_questions:
            continue
        selected.append(example)
        seen_questions.add(example['question_id'])
        if len(selected) == 5:
            break
    lines += ['', '## Five paired error examples (Track A correct, Track B incorrect)', '',
              'These are examples of paired score disagreements, not a causal attribution to retrieval alone; the retrieved evidence packet can differ from gold evidence.', '']
    for example in selected:
        lines += [f"### {example['question_id']} — {example['category']} — {example['model_tag']}",
                  f"Track A: {example['track_a_answer_excerpt'][:240].replace(chr(10), ' ')}  ",
                  f"Track B: {example['track_b_answer_excerpt'][:240].replace(chr(10), ' ')}", '']
    lines += ['Model digests, per-category details, and up to five additional disagreements per model and direction are in the JSON file.', '']
    output_md.write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--reviews', type=Path, required=True)
    parser.add_argument('--output-json', type=Path, required=True)
    parser.add_argument('--output-md', type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.run_root, args.reviews)
    if args.output_json.exists() or args.output_md.exists():
        raise SystemExit('Refusing to overwrite existing paired-report artifacts.')
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, args.output_json, args.output_md)
    print(json.dumps({'models': len(report['models']),
                      'pairs': sum(m['overall']['n'] for m in report['models']),
                      'output_json': str(args.output_json), 'output_md': str(args.output_md)}, indent=2))


if __name__ == '__main__':
    main()
