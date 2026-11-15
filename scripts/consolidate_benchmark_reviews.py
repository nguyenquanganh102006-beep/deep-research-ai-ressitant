"""Create an append-only-overlay-aware review view for the frozen dev A/B run."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.benchmark.scoring_local import citation_metrics


BASE_FILES = {
    'math': ('queue_math.jsonl', 'reviews_math_luna_v3.jsonl'),
    'code': ('queue_code.jsonl', 'reviews_code_luna_v3.jsonl'),
    'table_negative': ('queue_table_negative.jsonl', 'reviews_table_negative_luna_v2.jsonl'),
}
AUDIT_FILES = ('primary_audit_v2.jsonl', 'primary_audit_code_agent_v1.jsonl',
               'primary_audit_table_negative_agent_v1.jsonl')


def read_jsonl(path: Path):
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    rows = [json.loads(line) for line in lines if line.strip()]
    return rows, lines, hashlib.sha256(raw).hexdigest()


def _unique_by(rows, key, label):
    result = {}
    for row in rows:
        value = row.get(key)
        if not value or value in result:
            raise ValueError(f'{label}: missing or duplicate {key}: {value!r}')
        result[value] = row
    return result


def _line_hash(line: bytes):
    return hashlib.sha256(line).hexdigest()


def _normalize_citation_receipts(effective, queue_by_id):
    counts = defaultdict(int)
    for rid, receipt in effective.items():
        queue_row = queue_by_id[rid]
        metrics = citation_metrics(queue_row.get('model_answer') or '', queue_row.get('allowed_pages') or [])
        old = receipt.get('citation_supported')
        if metrics['unresolved_citation_placeholder'] or metrics['invalid_page_citations']:
            new = False
            reason = 'unresolved placeholder or out-of-evidence page citation'
        elif not metrics['citation_presence']:
            new = None
            reason = 'no concrete page citation; rubric support is not inferred from source support'
        else:
            new = old
            reason = 'retained reviewer claim-support judgment for concrete page citations'
        if old is not new:
            receipt['citation_supported'] = new
            counts['receipts_normalized'] += 1
            if new is False:
                counts['receipts_set_false'] += 1
            elif new is None:
                counts['receipts_set_null'] += 1
        receipt['_citation_normalization'] = {
            'citation_presence': metrics['citation_presence'],
            'citations': metrics['citations'],
            'invalid_page_citations': metrics['invalid_page_citations'],
            'unresolved_citation_placeholder': metrics['unresolved_citation_placeholder'],
            'reason': reason,
        }
        cited_pages_changed = False
        for claim in receipt.get('claims') or []:
            pages = claim.get('cited_pages')
            if not isinstance(pages, list):
                continue
            actual_pages = set(metrics['citations'])
            corrected = [p for p in pages if p in actual_pages]
            if corrected != pages:
                claim['cited_pages'] = corrected
                cited_pages_changed = True
        if cited_pages_changed:
            counts['claim_cited_pages_normalized'] += 1
    return dict(counts)


def _build_effective_primary_receipts(judging_dir, queue_by_id, corrections):
    raw_by_file = {}
    raw_hash_by_file_id = {}
    effective_by_file = {}
    source_lines = {}
    for filename in AUDIT_FILES:
        path = judging_dir / filename
        if not path.exists():
            continue
        rows, lines, _ = read_jsonl(path)
        by_id = _unique_by(rows, 'review_id', filename)
        raw_by_file[filename] = by_id
        effective_by_file[filename] = dict(by_id)
        raw_hash_by_file_id[filename] = {}
        source_lines[filename] = {i: (line, json.loads(line))
                                  for i, line in enumerate(lines, 1) if line.strip()}
        for line_no, (line, row) in source_lines[filename].items():
            rid = row['review_id']
            raw_hash_by_file_id[filename][rid] = {
                'line_with_ending': _line_hash(line),
                'line_without_ending': _line_hash(line.rstrip(b'\r\n')),
                'line_no': line_no,
            }

    invalidated = defaultdict(set)
    replacements = defaultdict(dict)
    for correction in corrections:
        filename = correction.get('source_file')
        if filename not in source_lines:
            continue
        line_no = correction.get('source_line_number')
        if not isinstance(line_no, int) or line_no not in source_lines[filename]:
            raise ValueError(f'Primary overlay has invalid source line: {filename}:{line_no}')
        line, raw_receipt = source_lines[filename][line_no]
        expected = correction.get('source_line_sha256_including_line_ending')
        if not expected or _line_hash(line) != expected:
            raise ValueError(f'Primary overlay source hash mismatch: {filename}:{line_no}')
        source_id = correction.get('source_review_id')
        if source_id != raw_receipt.get('review_id'):
            raise ValueError(f'Primary overlay source review_id mismatch: {filename}:{line_no}')
        if correction.get('source_receipt_invalidated'):
            invalidated[filename].add(source_id)
        replacement = correction.get('replacement_receipt')
        if not isinstance(replacement, dict) or not replacement.get('review_id'):
            raise ValueError(f'Primary overlay lacks replacement receipt: {filename}:{line_no}')
        replacement_id = replacement['review_id']
        queue_row = queue_by_id.get(replacement_id)
        if queue_row is None:
            raise ValueError(f'Primary overlay points outside review queues: {replacement_id}')
        expected_question = correction.get('replacement_question_id') or correction.get('question_id')
        if expected_question and queue_row.get('question_id') != expected_question:
            raise ValueError(f'Primary overlay queue question mismatch: {replacement_id}')
        expected_input = correction.get('replacement_queue_input_sha256')
        superseded_ids = {c.get('corrects_correction_id') for c in corrections if c.get('corrects_correction_id')}
        is_superseded = correction.get('correction_id') in superseded_ids
        if expected_input and queue_row.get('input_sha256') != expected_input and not is_superseded:
            raise ValueError(f'Primary overlay queue input mismatch: {replacement_id}')
        replacements[filename][replacement_id] = replacement

    for filename, receipts in effective_by_file.items():
        for rid in invalidated[filename]:
            receipts.pop(rid, None)
        receipts.update(replacements[filename])
    by_id = defaultdict(list)
    for filename, receipts in effective_by_file.items():
        for rid, receipt in receipts.items():
            by_id[rid].append((filename, receipt))
    return by_id, raw_hash_by_file_id


def _adjudication_fields(adjudication):
    result = {}
    score_key = 'adjudicated_correctness' if 'adjudicated_correctness' in adjudication else 'correctness'
    if score_key in adjudication:
        result['correctness'] = adjudication[score_key]
    citation_key = ('adjudicated_citation_supported' if 'adjudicated_citation_supported' in adjudication
                    else 'citation_supported')
    if citation_key in adjudication:
        result['citation_supported'] = adjudication[citation_key]
    for field in ('primary_error', 'claims', 'formula_fidelity', 'algorithm_reasoning',
                  'numeric_protocol_accuracy', 'correct_abstention', 'false_refusal'):
        if field in adjudication:
            result[field] = adjudication[field]
    score = result.get('correctness')
    if score is not None and (isinstance(score, bool) or score not in (0, 0.5, 1)):
        raise ValueError(f'Invalid adjudicated correctness: {score!r}')
    if result.get('citation_supported') is not None and not isinstance(result['citation_supported'], bool):
        raise ValueError('Invalid adjudicated citation support')
    return result


def _apply_adjudications(judging_dir, effective, queue_by_id, queue_line_hashes, corrections, adjudication_paths):
    if not adjudication_paths:
        return {'files': [], 'applied': 0, 'stale_legacy': []}
    base_effective = copy.deepcopy(effective)
    primary_by_id, primary_raw_hashes = _build_effective_primary_receipts(
        judging_dir, queue_by_id, corrections)
    raw_luna_hashes = defaultdict(set)
    for _, review_file in BASE_FILES.values():
        rows, lines, _ = read_jsonl(judging_dir / review_file)
        for line in lines:
            if not line.strip():
                continue
            row = json.loads(line)
            raw_luna_hashes[row['review_id']].add((_line_hash(line), _line_hash(line.rstrip(b'\r\n'))))
    # Older receipts cite the superseded v2 Math/Code/negative review files.
    for path in judging_dir.glob('reviews_*_luna_v2.jsonl'):
        _, lines, _ = read_jsonl(path)
        for line in lines:
            if not line.strip():
                continue
            row = json.loads(line)
            raw_luna_hashes[row['review_id']].add((_line_hash(line), _line_hash(line.rstrip(b'\r\n'))))

    applied = {}
    stale = []
    source_hashes = {}
    for path in adjudication_paths:
        rows, _, digest = read_jsonl(path)
        source_hashes[str(path)] = digest
        seen = set()
        for adjudication in rows:
            rid = adjudication.get('review_id')
            if not rid or rid in seen:
                raise ValueError(f'{path.name}: missing or duplicate adjudication review_id {rid!r}')
            seen.add(rid)
            if rid not in effective or rid not in queue_by_id:
                raise ValueError(f'{path.name}: adjudication outside review queue: {rid}')
            qrow = queue_by_id[rid]
            qid = adjudication.get('question_id')
            if qid and qid != qrow.get('question_id'):
                raise ValueError(f'{path.name}: question_id mismatch: {rid}')
            input_hash = adjudication.get('queue_input_sha256') or adjudication.get('input_sha256')
            if input_hash and input_hash != qrow.get('input_sha256'):
                raise ValueError(f'{path.name}: queue input hash mismatch: {rid}')
            queue_line_hash = adjudication.get('queue_line_sha256_including_line_ending')
            if queue_line_hash and queue_line_hashes.get(rid) != queue_line_hash:
                raise ValueError(f'{path.name}: queue line hash mismatch: {rid}')

            clean_luna = {k: v for k, v in base_effective[rid].items() if not k.startswith('_')}
            expected_luna = adjudication.get('effective_luna_receipt_sha256')
            if expected_luna and hashlib.sha256(json.dumps(clean_luna, sort_keys=True, ensure_ascii=False,
                                                             separators=(',', ':')).encode('utf-8')).hexdigest() != expected_luna:
                raise ValueError(f'{path.name}: effective Luna receipt hash mismatch: {rid}')
            luna_line_hash = (adjudication.get('luna_receipt_line_sha256_including_line_ending')
                              or adjudication.get('luna_receipt_line_sha256'))
            if luna_line_hash and not any(luna_line_hash in pair for pair in raw_luna_hashes.get(rid, set())):
                raise ValueError(f'{path.name}: source Luna line hash mismatch: {rid}')

            candidates = primary_by_id.get(rid, [])
            expected_primary = adjudication.get('effective_primary_receipt_sha256')
            primary_line_hash = (adjudication.get('primary_receipt_line_sha256_including_line_ending')
                                 or adjudication.get('primary_receipt_line_sha256'))
            if primary_line_hash:
                raw_primary_matches = [fn for fn, hashes in primary_raw_hashes.items()
                                       if hashes.get(rid) and primary_line_hash in
                                       (hashes[rid]['line_with_ending'], hashes[rid]['line_without_ending'])]
                if not raw_primary_matches:
                    raise ValueError(f'{path.name}: source primary line hash mismatch: {rid}')
            if expected_primary:
                matched = [r for _, r in candidates if hashlib.sha256(
                    json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest() == expected_primary]
                if not matched:
                    raise ValueError(f'{path.name}: effective primary receipt hash mismatch: {rid}')
                primary_current = matched[0]
            else:
                if primary_line_hash:
                    matching_files = [fn for fn, hashes in primary_raw_hashes.items()
                                      if hashes.get(rid) and primary_line_hash in
                                      (hashes[rid]['line_with_ending'], hashes[rid]['line_without_ending'])]
                    primary_current = next((r for fn, r in candidates if fn in matching_files), None)
                else:
                    primary_current = candidates[0][1] if candidates else None

            # Reuse legacy consensus only while the compared current receipts still match.
            if 'primary_correctness' in adjudication or 'luna_correctness' in adjudication:
                primary_matches = (primary_current is not None
                                   and primary_current.get('correctness') == adjudication.get('primary_correctness')
                                   and primary_current.get('citation_supported') == adjudication.get('primary_citation_supported'))
                luna_matches = (base_effective[rid].get('correctness') == adjudication.get('luna_correctness')
                                and base_effective[rid].get('citation_supported') == adjudication.get('luna_citation_supported'))
                if not (primary_matches and luna_matches):
                    stale.append({'file': path.name, 'review_id': rid,
                                  'primary_matches': primary_matches, 'luna_matches': luna_matches})
                    continue

            fields = _adjudication_fields(adjudication)
            if not fields:
                continue
            supersedes = applied.get(rid)
            effective[rid].update(fields)
            applied[rid] = {'fields': fields, 'file': path.name,
                            'adjudicator': adjudication.get('reviewer') or adjudication.get('adjudicator'),
                            'reviewed_at': adjudication.get('reviewed_at') or adjudication.get('adjudicated_at'),
                            'reason': adjudication.get('notes') or adjudication.get('adjudication_reason'),
                            'provenance': adjudication.get('provenance'),
                            'supersedes': supersedes}
    for rid, metadata in applied.items():
        effective[rid]['_audit_adjudication'] = metadata
    return {'files': source_hashes, 'applied': len(applied), 'stale_legacy': stale}


def build_effective_reviews(judging_dir: Path, adjudication_paths=()):
    queue_by_id = {}
    queue_line_hashes = {}
    raw_reviews = {}
    review_sources = {}
    source_line_lookup = {}
    source_hashes = {}

    for category, (queue_name, review_name) in BASE_FILES.items():
        queue_rows, queue_lines, queue_hash = read_jsonl(judging_dir / queue_name)
        queue_map = _unique_by(queue_rows, 'review_id', queue_name)
        for line in queue_lines:
            if line.strip():
                row = json.loads(line)
                queue_line_hashes[row['review_id']] = _line_hash(line)
        for rid, row in queue_map.items():
            if rid in queue_by_id:
                raise ValueError(f'review_id appears in multiple queues: {rid}')
            queue_by_id[rid] = row

        review_rows, lines, review_hash = read_jsonl(judging_dir / review_name)
        review_map = _unique_by(review_rows, 'review_id', review_name)
        for rid, row in review_map.items():
            if rid not in queue_map:
                raise ValueError(f'{review_name}: receipt outside its queue: {rid}')
            raw_reviews[rid] = row
            review_sources[rid] = review_name
        source_line_lookup[review_name] = {
            i: (line, json.loads(line)) for i, line in enumerate(lines, 1) if line.strip()
        }
        source_hashes[queue_name] = queue_hash
        source_hashes[review_name] = review_hash

    correction_path = judging_dir / 'receipt_corrections_v1.jsonl'
    corrections, _, correction_hash = read_jsonl(correction_path)
    superseded_correction_ids = {r.get('corrects_correction_id') for r in corrections if r.get('corrects_correction_id')}
    invalidated = set()
    replacements = defaultdict(list)
    overlay_rows = 0
    raw_source_hashes = defaultdict(set)
    for correction in corrections:
        if correction.get('source_review_id') and correction.get('source_line_sha256_including_line_ending'):
            raw_source_hashes[correction['source_review_id']].add(correction['source_line_sha256_including_line_ending'])
    for correction in corrections:
        source_file = correction.get('source_file')
        if source_file in source_line_lookup:
            overlay_rows += 1
            source_line_number = correction.get('source_line_number')
            if not isinstance(source_line_number, int) or source_line_number not in source_line_lookup[source_file]:
                raise ValueError(f'Overlay has invalid source line: {source_file}:{source_line_number}')
            source_line, source_row = source_line_lookup[source_file][source_line_number]
            expected_hash = correction.get('source_line_sha256_including_line_ending')
            if not expected_hash or _line_hash(source_line) != expected_hash:
                raise ValueError(f'Overlay source line hash mismatch: {source_file}:{source_line_number}')
            source_id = correction.get('source_review_id')
            if source_id != source_row.get('review_id'):
                raise ValueError(f'Overlay source review_id mismatch: {source_file}:{source_line_number}')
            if source_id not in raw_reviews or review_sources.get(source_id) != source_file:
                raise ValueError(f'Overlay source receipt is not in expected raw file: {source_id}')
        elif (not source_file
              and correction.get('correction_type') == 'replacement_receipt_for_invalidated_source_id'):
            # This legacy continuation is anchored to the hash of an earlier
            # line-verified invalidation; keep that chain explicit.
            source_id = correction.get('review_id')
            expected_hash = correction.get('supersedes_invalidated_source_line_sha256_including_line_ending')
            if (source_id not in raw_reviews or not expected_hash
                    or expected_hash not in raw_source_hashes.get(source_id, set())):
                raise ValueError(f'Unanchored invalidated-source replacement: {source_id}')
            overlay_rows += 1
        else:
            continue
        if correction.get('source_receipt_invalidated'):
            invalidated.add(source_id)
        receipt = correction.get('replacement_receipt')
        if not isinstance(receipt, dict) or not receipt.get('review_id'):
            raise ValueError(f'Overlay lacks a replacement receipt: {correction.get("correction_type")}')
        replacement_id = receipt['review_id']
        if correction.get('replacement_review_id') and correction['replacement_review_id'] != replacement_id:
            raise ValueError(f'Overlay replacement review_id mismatch: {replacement_id}')
        queue_row = queue_by_id.get(replacement_id)
        if queue_row is None:
            raise ValueError(f'Overlay replacement is outside all queues: {replacement_id}')
        replacement_question_id = correction.get('replacement_question_id') or correction.get('question_id')
        if replacement_question_id and queue_row.get('question_id') != replacement_question_id:
            raise ValueError(f'Overlay replacement question mismatch: {replacement_id}')
        replacement_input_hash = correction.get('replacement_queue_input_sha256')
        is_superseded = correction.get('correction_id') in superseded_correction_ids
        if (replacement_input_hash and queue_row.get('input_sha256') != replacement_input_hash
                and not is_superseded):
            raise ValueError(f'Overlay replacement input hash mismatch: {replacement_id}')
        replacements[replacement_id].append((correction, receipt))

    effective = {rid: row for rid, row in raw_reviews.items() if rid not in invalidated}
    for rid, entries in replacements.items():
        correction, receipt = entries[-1]
        replacement = dict(receipt)
        replacement['_overlay_provenance'] = {
            'correction_type': correction.get('correction_type'),
            'correction_ids': [entry[0].get('correction_id') for entry in entries],
            'source_file': correction.get('source_file'),
            'source_review_id': correction.get('source_review_id'),
            'source_line_sha256_including_line_ending': correction.get('source_line_sha256_including_line_ending'),
        }
        effective[rid] = replacement

    missing = set(queue_by_id) - set(effective)
    outside = set(effective) - set(queue_by_id)
    if missing or outside:
        raise ValueError(f'Effective review coverage mismatch: missing={len(missing)} {sorted(missing)[:5]}, outside={len(outside)} {sorted(outside)[:5]}')
    adjudication_manifest = _apply_adjudications(
        judging_dir, effective, queue_by_id, queue_line_hashes, corrections, adjudication_paths)
    citation_normalization = _normalize_citation_receipts(effective, queue_by_id)
    ordered = [effective[rid] for rid in queue_by_id]
    manifest = {
        'schema_version': 'effective_benchmark_reviews_v1',
        'queue_review_ids': len(queue_by_id),
        'effective_receipts': len(ordered),
        'correctness_scored': sum(r.get('correctness') is not None for r in ordered),
        'correctness_pending': sum(r.get('correctness') is None for r in ordered),
        'citation_support_rated': sum(isinstance(r.get('citation_supported'), bool) for r in ordered),
        'citation_normalization': citation_normalization,
        'adjudications': adjudication_manifest,
        'correction_rows_targeting_base_reviews': overlay_rows,
        'source_sha256': {**source_hashes, 'receipt_corrections_v1.jsonl': correction_hash},
    }
    return ordered, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--judging-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--adjudication', type=Path, action='append', default=None,
                        help='Adjudication JSONL, repeatable; defaults to known primary audit adjudication files.')
    args = parser.parse_args()
    if args.adjudication is None:
        adjudication_paths = []
        legacy = args.judging_dir / 'primary_audit_adjudications_v2.jsonl'
        if legacy.exists():
            adjudication_paths.append(legacy)
        adjudication_paths.extend(sorted(args.judging_dir.glob('*adjudications*agent_v1.jsonl')))
    else:
        adjudication_paths = args.adjudication
    rows, manifest = build_effective_reviews(args.judging_dir, adjudication_paths)
    if args.output.exists() or args.manifest.exists():
        raise SystemExit('Refusing to overwrite an existing review artifact.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(b''.join((json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8') for row in rows))
    manifest['output_sha256'] = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
