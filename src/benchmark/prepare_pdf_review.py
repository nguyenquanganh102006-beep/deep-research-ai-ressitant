"""Migrate legacy QA into honest, reviewable PDF benchmark candidates."""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf

from config import PROJECT_ROOT
from src.benchmark.import_qasper import ROOT, digest, write_jsonl


def main() -> None:
    destination = ROOT / 'gold_v1'
    destination.mkdir(parents=True, exist_ok=True)
    candidates, papers = [], []
    for paper in json.loads((PROJECT_ROOT / 'tests/papers/manifest.json').read_text(encoding='utf-8')):
        pdf = PROJECT_ROOT / paper['pdf']
        if digest(pdf) != paper['sha256']:
            raise ValueError('PDF checksum differs from legacy manifest')
        version = paper['source_url'].rsplit('/', 1)[-1]
        paper_id = 'arxiv:' + version
        pages_needed = set()
        document = pymupdf.open(pdf)
        cases = json.loads((PROJECT_ROOT / paper['questions']).read_text(encoding='utf-8'))
        for case in cases:
            pages = case.get('page_ground_truth') or []
            evidence = []
            for page in pages:
                if not 1 <= page <= len(document):
                    raise ValueError('Invalid page number')
                pages_needed.add(page)
                evidence.append({'paper_id': paper_id, 'pdf_sha256': paper['sha256'], 'page': page, 'section': None, 'element_id': None, 'quote': None, 'page_text_sidecar': f'review/{paper["paper"]}/page-{page}.txt', 'page_image': f'review/{paper["paper"]}/page-{page}.png', 'quote_review_status': 'pending'})
            negative = case['type'] == 'negative'
            candidates.append({'question_id': case['id'], 'dataset_source': 'deepresearch_legacy_pdf_candidates', 'dataset_version': '1.0-candidate', 'track': 'pdf_gold', 'split': 'dev', 'paper_ids': [paper_id], 'category': 'unanswerable' if negative and not pages else case['type'] if not negative else 'math', 'subtype': 'false_premise' if negative and pages else 'missing_information' if negative else 'legacy_' + case['type'], 'question': case['question'], 'reference_answer': case['answer_ground_truth'], 'answerable': bool(pages), 'evidence': evidence, 'difficulty': 'not_reviewed', 'language': 'vi', 'review_status': 'pending_human_review', 'reviewer_id': None, 'second_reviewer_id': None, 'notes': case.get('notes', ''), 'split_reason': 'Legacy questions used in earlier tuning; never eligible for frozen test.', 'expected_reasoning_checks': [], 'absence_review': None})
        packet = destination / 'review' / paper['paper']
        packet.mkdir(parents=True, exist_ok=True)
        for page in sorted(pages_needed):
            (packet / f'page-{page}.txt').write_text(document[page - 1].get_text(), encoding='utf-8')
            document[page - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(packet / f'page-{page}.png')
        papers.append({**paper, 'paper_id': paper_id, 'canonical_group_id': 'arxiv:' + version.split('v')[0], 'split': 'dev', 'license': 'not_yet_reviewed', 'rights_review_status': 'pending', 'review_page_count': len(pages_needed)})
        document.close()
    write_jsonl(destination / 'candidates.jsonl', candidates)
    write_jsonl(destination / 'papers.jsonl', papers)
    write_jsonl(destination / 'review_decisions.template.jsonl', [{'question_id': c['question_id'], 'decision': 'pending', 'reviewer_id': None, 'reviewed_at': None, 'evidence_corrections': [], 'answer_correction': None, 'rubric_checks': [], 'notes': ''} for c in candidates])
    print(json.dumps({'candidates': len(candidates), 'papers': len(papers), 'verified_gold': 0, 'all_dev_due_to_prior_tuning': True}))


if __name__ == '__main__':
    main()
