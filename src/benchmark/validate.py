"""Audit imported benchmark integrity, including source-label preservation."""
from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from pathlib import Path

from src.benchmark.import_qasper import ROOT, digest


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def validate_qasper() -> dict:
    directory = ROOT / 'external' / 'qasper'
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    errors, ids, paper_splits, report = [], set(), {}, {}
    content_fingerprints, title_fingerprints = {}, {}
    title_collisions = []
    for file in manifest['files']:
        if digest(ROOT / file['path']) != file['sha256']:
            errors.append('Checksum mismatch: ' + file['path'])
    for source in manifest['sources']:
        if digest(directory / 'raw' / source['url'].rsplit('/', 1)[-1]) != source['sha256']:
            errors.append('Source checksum mismatch')
    for split in ('train', 'dev', 'test'):
        documents = {d['paper_id']: d for d in load(directory / f'documents_{split}.jsonl')}
        original = json.loads((directory / 'raw' / f'qasper-{split}-v0.3.json').read_text(encoding='utf-8'))
        original_qas = {q['question_id']: q for p in original.values() for q in p['qas']}
        cases = load(directory / f'{split}.jsonl')
        if len(cases) != len(original_qas):
            errors.append(f'{split}: source question count differs')
        for paper_id, document in documents.items():
            if paper_id in paper_splits:
                errors.append(f'Paper leakage {paper_id}')
            paper_splits[paper_id] = split
            text = ' '.join(p['text'] for p in document['paragraphs'])
            fingerprint = hashlib.sha256(re.sub(r'\s+', '', text).encode()).hexdigest()
            if fingerprint in content_fingerprints and content_fingerprints[fingerprint]['split'] != split:
                errors.append(f'Identical paper content crosses splits: {paper_id}')
            content_fingerprints[fingerprint] = {'paper_id': paper_id, 'split': split}
            title = re.sub(r'\W+', '', document['title']).casefold()
            if title in title_fingerprints and title_fingerprints[title]['split'] != split:
                title_collisions.append([paper_id, title_fingerprints[title]['paper_id']])
            title_fingerprints[title] = {'paper_id': paper_id, 'split': split}
            if any(key in document for key in ('qas', 'annotations', 'reference_answer')):
                errors.append('Gold labels in retrieval document')
        for case in cases:
            qid = case['question_id']
            if qid in ids:
                errors.append('Duplicate question ID: ' + qid)
            ids.add(qid)
            source = original_qas[case['source_question_id']]
            if source['question'] != case['question'] or not case['question'].strip():
                errors.append('Question mismatch: ' + qid)
            if len(source['answers']) != len(case['annotations']):
                errors.append('Lost reference: ' + qid)
            doc = documents[case['paper_ids'][0]]
            elements = {p['element_id']: p['text'] for p in doc['paragraphs']}
            for actual, expected in zip(case['annotations'], source['answers']):
                if actual['original_answer'] != expected['answer']:
                    errors.append('Changed annotation: ' + qid)
                if not actual['reference_answer'].strip():
                    errors.append('Empty reference: ' + qid)
                for evidence in actual['evidence']:
                    if evidence['page'] is not None or evidence['pdf_sha256'] is not None:
                        errors.append('Invented PDF mapping: ' + qid)
                    quote = evidence['quote'].removeprefix('FLOAT SELECTED:').lstrip() if evidence['match_status'] == 'float_prefix_removed' else evidence['quote']
                    if any(elements[eid] != quote for eid in evidence['element_ids']):
                        errors.append('Evidence mismatch: ' + qid)
        report[split] = {'questions': len(cases), 'papers': len(documents), 'evidence_mapping': dict(Counter(e['match_status'] for c in cases for a in c['annotations'] for e in a['evidence']))}
    result = {'passed': not errors, 'errors': errors, 'cross_split_normalized_title_collisions': title_collisions, 'splits': report, 'total_questions': len(ids), 'total_papers': len(paper_splits), 'checks': ['file and archive SHA-256', 'official split paper disjointness', 'identical normalized paper content across splits', 'normalized title collision report', 'unique question IDs', 'original question and all annotations preserved', 'nonempty references', 'mapped evidence equals source document', 'no fabricated PDF pages', 'no QA labels in document index input']}
    (directory / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    result = validate_qasper()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
