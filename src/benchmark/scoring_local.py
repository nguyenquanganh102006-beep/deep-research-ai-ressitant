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
    citations = set()
    for match in re.finditer(r'\[(?:Trang|Page)\s+(\d+)(?:\s*[-–—]\s*(\d+))?\]', answer, re.I):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        citations.update(range(min(start, end), max(start, end) + 1))
    citations = sorted(citations)
    placeholder = bool(re.search(r'\[(?:Trang|Page)\s*N\]', answer, re.I))
    return {'citations': citations, 'citation_presence': bool(citations) or placeholder,
            'unresolved_citation_placeholder': placeholder,
            'invalid_page_citations': sorted(set(citations) - set(pages))}


def review_id(row):
    return fingerprint({k: row.get(k) for k in ('run_id', 'track', 'question_id', 'model_digest', 'answer', 'evidence_sha256')})


def _boolean_rate(receipts: list[dict], field: str):
    values = [r.get(field) for r in receipts if isinstance(r.get(field), bool)]
    return (sum(values) / len(values) if values else None), len(values)


def summarize(rows: list[dict], reviews: list[dict] = ()):
    receipts = {}
    for r in reviews:
        if r['review_id'] in receipts:
            raise ValueError('Duplicate review receipt')
        correctness = r.get('correctness')
        if (correctness is not None
                and (isinstance(correctness, bool) or correctness not in (0, 0.5, 1))):
            raise ValueError('Invalid correctness score')
        if not r.get('reviewer') or not r.get('provenance'):
            raise ValueError('Invalid score or missing reviewer provenance')
        for field in ('citation_supported', 'formula_fidelity', 'algorithm_reasoning',
                      'numeric_protocol_accuracy', 'correct_abstention', 'false_refusal'):
            if r.get(field) is not None and not isinstance(r.get(field), bool):
                raise ValueError(f'Invalid boolean review field: {field}')
        if r.get('claims') is not None and not isinstance(r.get('claims'), list):
            raise ValueError('Review claims must be a list')
        for claim in r.get('claims') or []:
            if (not isinstance(claim, dict)
                    or not any(claim.get('supported') is value for value in (True, False, None))):
                raise ValueError('Invalid claim support label')
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
        review_receipts = [receipts[review_id(r)] for r in completed if review_id(r) in receipts]
        scored = [r for r in review_receipts if r.get('correctness') is not None]
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
                        'reviewed_completed': len(scored), 'review_receipts_completed': len(review_receipts),
                        'pending_correctness_completed': sum(r.get('correctness') is None for r in review_receipts),
                        'unreviewed_completed': missing,
                        'correctness_reviewed_completed': float(np.mean([r['correctness'] for r in scored])) if scored else None,
                        'correctness_all_eligible': sum(r['correctness'] for r in scored) / len(eligible) if not missing and eligible else None,
                        'citation_presence_rate': float(np.mean([r.get('citation_presence', False) for r in completed])) if completed else None,
                        'invalid_page_citation_count': sum(bool(r.get('invalid_page_citations')) for r in completed),
                        'unresolved_citation_placeholder_count': sum(bool(r.get('unresolved_citation_placeholder')) for r in completed),
                        'truncated_output_count': sum(bool(r.get('output_truncated')) for r in completed),
                        'placement_classes': sorted({
                            'gpu_only' if p.get('size') and p.get('size_vram', 0) / p['size'] >= 0.99 else 'cpu_offload_or_unknown'
                            for r in completed for p in r.get('placement', [])}),
                        'latency_p50_seconds': float(np.percentile(latency, 50)) if latency else None,
                        'latency_p95_seconds': float(np.percentile(latency, 95)) if latency else None})
        metrics[-1]['decode_tokens_per_second_p50'] = float(np.median(throughput)) if throughput else None
        metrics[-1]['model_size_vram_bytes_max'] = max((p.get('size_vram', 0) for r in completed for p in r.get('placement', [])), default=None)
        for field in ('citation_supported', 'formula_fidelity', 'algorithm_reasoning',
                      'numeric_protocol_accuracy', 'correct_abstention', 'false_refusal'):
            rate, rated = _boolean_rate(review_receipts, field)
            metrics[-1][f'{field}_rate'] = rate
            metrics[-1][f'{field}_rated_count'] = rated
        claims = [claim for receipt in review_receipts for claim in (receipt.get('claims') or [])]
        labeled_claims = [claim for claim in claims if isinstance(claim.get('supported'), bool)]
        unsupported = sum(claim['supported'] is False for claim in labeled_claims)
        supported = sum(claim['supported'] is True for claim in labeled_claims)
        metrics[-1]['substantive_claim_count'] = len(claims)
        metrics[-1]['claim_support_labeled_count'] = len(labeled_claims)
        metrics[-1]['supported_claim_count'] = supported
        metrics[-1]['unsupported_claim_count'] = unsupported
        metrics[-1]['claim_support_rate'] = supported / len(labeled_claims) if labeled_claims else None
        metrics[-1]['unsupported_claim_rate'] = unsupported / len(labeled_claims) if labeled_claims else None
        metrics[-1]['unsupported_claims_per_reviewed_answer'] = unsupported / len(review_receipts) if review_receipts else None
    return metrics


def score_run(run_dir: Path, review_path: Path | None = None):
    # Latest attempt per digest/question; preserve earlier attempts in predictions.jsonl.
    latest = {}
    history = read_rows(run_dir / 'predictions.jsonl')
    for row in history:
        latest[(row['model_digest'], row['question_id'])] = row
    rows = list(latest.values())
    for row in rows:
        row.update(citation_metrics(row.get('answer') or '', row.get('allowed_pages') or []))
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
            'Rubric correctness and claim support come from explicit review receipts. Citation presence is separate from claim-level citation support. Unsupported-claim rate is a hallucination proxy, not an expert-gold label.', '',
            '| Model | Track | Category | Eligible | Completed | Failures | Reviewed | Rubric mean | Citation presence | Citation support | Claim support | Unsupported claims / answer | Correct abstention | Latency p50 / p95 (s) |',
            '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for m in metrics:
        text.append(f"| {m['model_tag']} | {m['track']} | {m['category']} | {m['eligible_cases']} | {m['completed']} | {m['technical_failure_count']} | {m['reviewed_completed']} | {m.get('correctness_all_eligible')} | {m.get('citation_presence_rate')} | {m.get('citation_supported_rate')} | {m.get('claim_support_rate')} | {m.get('unsupported_claims_per_reviewed_answer')} | {m.get('correct_abstention_rate')} | {m.get('latency_p50_seconds')} / {m.get('latency_p95_seconds')} |")
    text += ['', 'Metrics with no applicable or non-null receipt values remain null; rated counts are in metrics.json. Technical failures remain in the eligible denominator. No winner is selected automatically. Full digest, protocol and hashes: manifest.json.']
    (run_dir / 'report.md').write_text('\n'.join(text) + '\n', encoding='utf-8')
