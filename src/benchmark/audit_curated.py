"""Audit AI-reviewed PDF QA; freeze only after all structural/source checks pass."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from jsonschema import Draft202012Validator

from config import PROJECT_ROOT
from src.benchmark.import_qasper import ROOT, digest, write_jsonl
from src.benchmark.validate import load

TARGETS = {'math': 150, 'code': 150, 'table': 100, 'unanswerable': 100}


def normalize(text: str) -> str:
    return normalize_source(text).casefold()


def normalize_source(text: str) -> str:
    # Formula symbols are case-sensitive: W and w must not be interchangeable.
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))


def group_id(paper_id: str) -> str:
    return re.sub(r'v\d+$', '', paper_id)


def assigned_split(paper_id: str, official_splits: dict[str, str]) -> str:
    group = group_id(paper_id)
    if group in {'arxiv:1412.6980', 'arxiv:2205.14135'}:
        return 'dev'
    if group in official_splits:
        return official_splits[group]
    bucket = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 10
    return 'train' if bucket < 2 else 'dev' if bucket < 5 else 'test'


def audit(freeze: bool = False, overrides: dict[str, Path] | None = None) -> dict:
    if freeze and overrides:
        raise ValueError('Candidate input overrides cannot be frozen')
    directory = ROOT / 'curated_v1'
    staging = directory / 'staging'
    cases, papers = [], {}
    errors, warnings = [], []
    for path in sorted(staging.glob('*_papers.jsonl')):
        for paper in load(path):
            paper_id = paper['paper_id']
            if paper_id in papers and paper.get('pdf_sha256') != papers[paper_id].get('pdf_sha256'):
                errors.append(f'Conflicting PDF hash: {paper_id}')
            papers[paper_id] = paper
    for name in ('math.jsonl', 'math_supplement.jsonl', 'code.jsonl', 'table_negative.jsonl', 'table_root.jsonl', 'negative_root.jsonl', 'code_negatives.jsonl'):
        path = (overrides or {}).get(name, staging / name)
        if path.exists():
            cases.extend(load(path))
    input_count = len(cases)
    reviewed_annotations = copy.deepcopy(cases)
    schema = json.loads((ROOT / 'schemas/pdf_qa.schema.json').read_text(encoding='utf-8'))
    validator = Draft202012Validator(schema)
    valid_cases = []
    for case in cases:
        schema_errors = list(validator.iter_errors(case))
        if schema_errors:
            label = case.get('question_id', 'unknown') if isinstance(case, dict) else 'unknown'
            errors.extend(f'{label}: schema {list(error.path)}: {error.message}' for error in schema_errors)
        else:
            valid_cases.append(case)
    cases = valid_cases
    referenced_papers = {paper_id for case in cases for paper_id in case['paper_ids']}
    unreferenced_papers = sorted(set(papers) - referenced_papers)
    papers = {paper_id: paper for paper_id, paper in papers.items() if paper_id in referenced_papers}
    for paper_id in sorted(referenced_papers - set(papers)):
        errors.append(f'Question references a paper missing from manifests: {paper_id}')
    official_splits = {}
    for split in ('train', 'dev', 'test'):
        for document in load(ROOT / 'external/qasper' / f'documents_{split}.jsonl'):
            official_splits[group_id(document['paper_id'])] = split
    pdfs, page_text, original_page_text = {}, {}, {}
    for paper_id, paper in papers.items():
        pdf_path = (PROJECT_ROOT / paper.get('pdf_path', '')).resolve()
        if not pdf_path.is_relative_to(PROJECT_ROOT.resolve()) or not pdf_path.is_file():
            errors.append(f'Missing/invalid PDF path: {paper_id}')
            continue
        if paper.get('pdf_sha256') != digest(pdf_path):
            errors.append(f'PDF checksum mismatch: {paper_id}')
        try:
            pdf = pymupdf.open(pdf_path)
            pdfs[paper_id] = pdf
            if paper.get('page_count') != len(pdf):
                errors.append(f'Page count mismatch: {paper_id}')
            original_page_text[paper_id] = [page.get_text() for page in pdf]
            page_text[paper_id] = [normalize_source(text) for text in original_page_text[paper_id]]
        except Exception as exc:
            errors.append(f'Invalid PDF {paper_id}: {exc}')
        if 'unknown' in paper.get('license', 'unknown').casefold() or paper.get('license') == 'not_yet_reviewed':
            warnings.append(f'License not established; local-only PDF, no redistribution: {paper_id}')
    seen_ids, seen_questions = set(), {}
    for case in cases:
        qid = case.get('question_id')
        if not qid or qid in seen_ids:
            errors.append(f'Missing/duplicate ID: {qid}')
        seen_ids.add(qid)
        required = ('question', 'reference_answer', 'paper_ids', 'category', 'difficulty', 'review_status', 'reviewer_id', 'expected_reasoning_checks')
        for key in required:
            if not case.get(key):
                errors.append(f'{qid}: missing {key}')
        normalized = normalize(case.get('question', ''))
        if normalized in seen_questions:
            errors.append(f'Duplicate question: {qid} and {seen_questions[normalized]}')
        seen_questions[normalized] = qid
        authored_text = ' '.join(str(case.get(key, '')) for key in ('question', 'reference_answer'))
        if '\ufffd' in authored_text or authored_text.count('?') > 3:
            errors.append(f'{qid}: corrupted authored text or excessive question marks')
        if '?' in ''.join(case.get('expected_reasoning_checks', [])) or '\ufffd' in ''.join(case.get('expected_reasoning_checks', [])):
            errors.append(f'{qid}: suspicious encoding in rubric')
        if case.get('category') not in TARGETS:
            errors.append(f'{qid}: unexpected category')
        if case.get('category') == 'unanswerable' and case.get('answerable') is not False:
            errors.append(f'{qid}: answerable false-premise correction must not count as unanswerable')
        if case.get('review_status') != 'ai_reviewed':
            errors.append(f'{qid}: missing honest AI review label')
        splits = {assigned_split(p, official_splits) for p in case.get('paper_ids', [])}
        if len(splits) != 1:
            errors.append(f'{qid}: cross-split multi-paper case')
        else:
            case['split'] = next(iter(splits))
        if case.get('answerable') is False:
            absence = case.get('absence_review')
            if not absence or not isinstance(absence, dict):
                errors.append(f'{qid}: missing absence review')
            elif not absence.get('searched_terms') or not (absence.get('examined_pages') or absence.get('page_range') or absence.get('examined_page_range')) or not (absence.get('reason') or absence.get('notes')):
                errors.append(f'{qid}: incomplete absence review scope')
        elif case.get('answerable') is not True:
            errors.append(f'{qid}: answerable must be boolean')
        elif not case.get('evidence'):
            errors.append(f'{qid}: missing evidence')
        for evidence in case.get('evidence', []):
            if '?' in str(evidence.get('latex_reference', '')) or str(evidence.get('evidence_note', '')).count('?') > 2:
                errors.append(f'{qid}: corrupted formula/evidence note')
            paper_id = evidence.get('paper_id')
            paper = papers.get(paper_id)
            page = evidence.get('page')
            if not paper or paper_id not in case.get('paper_ids', []):
                errors.append(f'{qid}: unknown evidence paper')
                continue
            if evidence.get('pdf_sha256') != paper.get('pdf_sha256'):
                errors.append(f'{qid}: wrong evidence PDF hash')
            if type(page) is not int or paper_id not in pdfs or not 1 <= page <= len(pdfs[paper_id]):
                errors.append(f'{qid}: invalid source page')
                continue
            quote = normalize_source(evidence.get('quote', ''))
            minimum_length = 40 if case['category'] == 'math' else 8
            if len(quote) < minimum_length:
                errors.append(f'{qid}: evidence quote too short/missing')
            elif quote not in page_text[paper_id][page - 1]:
                errors.append(f'{qid}: quote not found verbatim on page {page}')
            source_text = original_page_text[paper_id][page - 1]
            evidence['source_page_text_sha256'] = hashlib.sha256(source_text.encode()).hexdigest()
            evidence['source_page_text_path'] = f'data/benchmark/curated_v1/source_pages/{paper["pdf_sha256"]}/page-{page}.txt'
        case['dataset_version'] = '1.0-ai-reviewed'
        case['dataset_source'] = 'deepresearch_pdf_ai_reviewed'
        case['track'] = 'pdf_ai_reviewed'
        if case.get('notes') == 'Staging/dev record; keep all questions for this paper in one split.':
            case['notes'] = 'All questions for this paper share one split; see the assigned split field.'
        case.setdefault('curation_model', 'gpt-6-luna')
        if case['curation_model'] == 'gpt-6-luna':
            case['curation_reasoning_effort'] = 'max'
    counts = Counter(c.get('category') for c in cases)
    for category, target in TARGETS.items():
        if counts[category] < target:
            errors.append(f'Quota incomplete {category}: {counts[category]}/{target}')
    by_split = {split: [c for c in cases if c.get('split') == split] for split in ('train', 'dev', 'test')}
    # Identical answer within a paper/category may indicate template padding.
    answer_groups = defaultdict(list)
    for case in cases:
        if case.get('answerable'):
            answer_groups[(tuple(case.get('paper_ids', [])), normalize(case.get('reference_answer', '')))].append(case.get('question_id'))
    repeated = [ids for ids in answer_groups.values() if len(ids) > 1]
    warnings.extend('Repeated answer needs semantic review: ' + ', '.join(ids) for ids in repeated)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'passed': not errors, 'questions': len(cases), 'papers': len(papers), 'category_counts': dict(counts), 'target_counts': TARGETS, 'split_counts': {s: len(rows) for s, rows in by_split.items()}, 'difficulty_counts': dict(Counter(c.get('difficulty') for c in cases)), 'per_paper_counts': dict(Counter(p for c in cases for p in c.get('paper_ids', []))), 'category_by_split': {s: dict(Counter(c.get('category') for c in rows)) for s, rows in by_split.items()}, 'errors': errors, 'warnings': warnings, 'human_reviewed': False, 'freeze_requested': freeze, 'frozen': False}
    report['source_text_extractor'] = {
        'name': 'PyMuPDF', 'version': pymupdf.VersionBind,
        'quote_matching': 'case-sensitive NFKC with whitespace removed',
    }
    frozen_path = directory / 'test_frozen.jsonl'
    report['input_questions'] = input_count
    report['schema_invalid_questions'] = input_count - len(cases)
    report['unreferenced_staging_papers'] = unreferenced_papers
    if freeze and not errors and frozen_path.exists() and load(frozen_path) != by_split['test']:
        errors.append('Frozen test differs: create a new dataset version instead of overwriting it')
        report['passed'] = False
    if freeze and not errors:
        for case in cases:
            for evidence in case.get('evidence', []):
                path = PROJECT_ROOT / evidence['source_page_text_path']
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original_page_text[evidence['paper_id']][evidence['page'] - 1].encode('utf-8'))
        for split, rows in by_split.items():
            write_jsonl(directory / ('test_frozen.jsonl' if split == 'test' else split + '.jsonl'), rows)
        write_jsonl(directory / 'papers.jsonl', list(papers.values()))
        # Review fingerprints refer to these original annotation fields. Release
        # records additionally carry assigned splits and source-page sidecars.
        write_jsonl(directory / 'annotations.reviewed.jsonl', reviewed_annotations)
        report['frozen'] = True
        report['files'] = {name: digest(directory / name) for name in ('train.jsonl', 'dev.jsonl', 'test_frozen.jsonl', 'papers.jsonl', 'annotations.reviewed.jsonl')}
        report['review_receipt_files'] = {
            str(path.relative_to(directory)): digest(path)
            for path in sorted((directory / 'reviews').glob('*_cross_review.jsonl'))
        }
    for pdf in pdfs.values():
        pdf.close()
    directory.mkdir(parents=True, exist_ok=True)
    report_name = 'audit_candidate.json' if overrides else ('audit_latest.json' if frozen_path.exists() and not freeze else 'audit.json')
    (directory / report_name).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    result = audit(parser.parse_args().freeze)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
