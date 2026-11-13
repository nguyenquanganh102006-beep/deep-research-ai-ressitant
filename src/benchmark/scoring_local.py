"""Automatic diagnostics plus explicit blind rubric review. Never infer correctness."""
from __future__ import annotations

import csv
import re
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np

from src.benchmark.local_common import (read_rows, load_dev, fingerprint, write_json,
                                        canonical)

# A selected case blocked by runtime RAM/disk is a deployment failure, not a
# reason to shrink the eligible denominator. Preflight-excluded models have no cases.
EXCLUDED = {'evidence_unverified', 'not_applicable', 'context_ineligible', 'not_installed'}


def citation_metrics(answer, pages):
    citations = sorted(set(map(int, re.findall(r'\[(?:Trang|Page)\s+(\d+)\]', answer, re.I))))
    return {'citations': citations, 'citation_presence': bool(citations),
            'invalid_page_citations': sorted(set(citations) - set(pages))}


def review_id(row):
    return fingerprint({k: row.get(k) for k in ('run_id', 'track', 'question_id', 'model_digest', 'answer', 'evidence_sha256')})


def summarize(rows: list[dict], reviews: list[dict] = ()):
    receipts = {}
    for r in reviews:
        if r['review_id'] in receipts:
            raise ValueError('Duplicate review receipt')
        if (isinstance(r.get('correctness'), bool) or r.get('correctness') not in (0, 0.5, 1)
                or not r.get('reviewer') or not r.get('provenance')):
            raise ValueError('Invalid score or missing reviewer provenance')
        receipts[r['review_id']] = r
    known = {review_id(r) for r in rows if r['status'] == 'completed'}
    if set(receipts) - known:
        raise ValueError('Stale/unknown review receipts')
    groups = defaultdict(list)
    for row in rows:
        groups[(row['model_tag'], row['track'], row['category'])].append(row)
        groups[(row['model_tag'], row['track'], 'all')].append(row)
    metrics = []
    for (tag, track, category), group in groups.items():
        eligible = [r for r in group if r['status'] not in EXCLUDED]
        completed = [r for r in eligible if r['status'] == 'completed']
        scored = [receipts[review_id(r)] for r in completed if review_id(r) in receipts]
        missing = len(completed) - len(scored)
        latency = [r['latency_seconds'] for r in completed]
        throughput = [r['decode_tokens_per_second'] for r in completed if r.get('decode_tokens_per_second') is not None]
        metrics.append({'model_tag': tag, 'track': track, 'category': category,
                        'model_digest': group[0].get('model_digest'),
                        'quantization': group[0].get('quantization'),
                        'thinking_mode': group[0].get('thinking_mode'),
                        'cases': len(group), 'eligible_cases': len(eligible), 'completed': len(completed),
                        'technical_failure_count': len(eligible) - len(completed),
                        'excluded_statuses': dict(Counter(r['status'] for r in group if r['status'] in EXCLUDED)),
                        'reviewed_completed': len(scored), 'unreviewed_completed': missing,
                        'correctness_reviewed_completed': float(np.mean([r['correctness'] for r in scored])) if scored else None,
                        'correctness_all_eligible': sum(r['correctness'] for r in scored) / len(eligible) if not missing and eligible else None,
                        'citation_presence_rate': float(np.mean([r.get('citation_presence', False) for r in completed])) if completed else None,
                        'invalid_page_citation_count': sum(bool(r.get('invalid_page_citations')) for r in completed),
                        'truncated_output_count': sum(bool(r.get('output_truncated')) for r in completed),
                        'placement_classes': sorted({
                            'gpu_only' if p.get('size') and p.get('size_vram', 0) / p['size'] >= 0.99 else 'cpu_offload_or_unknown'
                            for r in completed for p in r.get('placement', [])}),
                        'latency_p50_seconds': float(np.percentile(latency, 50)) if latency else None,
                        'latency_p95_seconds': float(np.percentile(latency, 95)) if latency else None})
        metrics[-1]['decode_tokens_per_second_p50'] = float(np.median(throughput)) if throughput else None
        metrics[-1]['model_size_vram_bytes_max'] = max((p.get('size_vram', 0) for r in completed for p in r.get('placement', [])), default=None)
    return metrics


def score_run(run_dir: Path, review_path: Path | None = None):
    # Latest attempt per digest/question; preserve earlier attempts in predictions.jsonl.
    latest = {}
    history = read_rows(run_dir / 'predictions.jsonl')
    for row in history:
        latest[(row['model_digest'], row['question_id'])] = row
    rows = list(latest.values())
    reviews = read_rows(review_path) if review_path else []
    metrics = summarize(rows, reviews)
    for m in metrics:
        attempts = [r for r in history if r['model_tag'] == m['model_tag'] and r['track'] == m['track']
                    and (m['category'] == 'all' or r['category'] == m['category'])]
        m['recorded_attempts'] = len(attempts)
        m['failed_attempts'] = sum(r['status'] not in EXCLUDED and r['status'] != 'completed' for r in attempts)
        m['transport_retries'] = sum(r.get('transport_retries', 0) for r in attempts)
        m['total_case_wall_seconds'] = sum(r.get('case_wall_seconds', 0) for r in attempts)
    write_json(run_dir / 'metrics.json', metrics)
    cases, _ = load_dev()
    labels = {q['question_id']: q for q in cases}
    template = []
    for row in rows:
        if row['status'] != 'completed':
            continue
        q = labels[row['question_id']]
        template.append({'review_id': review_id(row), 'question_id': row['question_id'],
                         'category': q['category'], 'question': q['question'], 'answer': row['answer'],
                         'reference_answer': q['reference_answer'], 'rubric': q['expected_reasoning_checks'],
                         'correctness': None, 'citation_supported': None, 'primary_error': None,
                         'reviewer': None, 'provenance': None,
                         'note': 'Evaluator-only blind review; never index or send this file to the tested model.'})
    # Do not overwrite a reviewer-edited template.
    target = run_dir / 'review_template.jsonl'
    existing_ids = {r['review_id'] for r in read_rows(target)} if target.exists() else set()
    with target.open('ab') as f:
        f.write(b''.join(canonical(r) + b'\n' for r in template if r['review_id'] not in existing_ids))
    export_metrics(metrics, run_dir)
    with (run_dir / 'errors.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['model_tag', 'question_id', 'status', 'error'])
        writer.writeheader()
        writer.writerows({k: r.get(k) for k in writer.fieldnames} for r in rows if r['status'] != 'completed')
    return metrics


def export_metrics(metrics: list[dict], run_dir: Path):
    """Render already-scored metrics without touching reviews or scores."""
    with (run_dir / 'leaderboard.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics[0]) if metrics else ['model_tag'])
        writer.writeheader()
        writer.writerows(metrics)
    text = ['# Local LLM run report', '',
            'Correctness remains null until explicit rubric review. Citation format is a separate automatic diagnostic.', '',
            '| Model | Track | Eligible | Completed | Technical failures | Reviewed | Citation presence |',
            '|---|---|---:|---:|---:|---:|---:|']
    for m in metrics:
        if m['category'] == 'all':
            text.append(f"| {m['model_tag']} | {m['track']} | {m['eligible_cases']} | {m['completed']} | {m['technical_failure_count']} | {m['reviewed_completed']} | {m['citation_presence_rate']} |")
    text += ['', 'No winner is selected automatically from unreviewed outputs. Full digest, protocol and hashes: manifest.json.']
    (run_dir / 'report.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
