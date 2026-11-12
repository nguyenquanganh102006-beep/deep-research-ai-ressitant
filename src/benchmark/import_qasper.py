"""Import the official QASPER v0.3 archives without executing dataset scripts.

Run: python -m src.benchmark.import_qasper
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import PROJECT_ROOT

ROOT = PROJECT_ROOT / 'data' / 'benchmark'
SOURCE = 'https://qasper-dataset.s3.us-west-2.amazonaws.com/'
ARCHIVES = ('qasper-train-dev-v0.3.tgz', 'qasper-test-and-evaluator-v0.3.tgz')


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    temporary.replace(path)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(stream.read()).hexdigest()


def import_dataset() -> dict:
    destination = ROOT / 'external' / 'qasper'
    raw = destination / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    provenance = []
    for filename in ARCHIVES:
        target = raw / filename
        if not target.exists():
            if shutil.disk_usage(raw).free < 30 * 1024**3:
                raise RuntimeError('Storage guard: less than 30 GiB free')
            print('Downloading', filename, flush=True)
            with requests.get(SOURCE + filename, stream=True, timeout=(15, 90)) as response:
                response.raise_for_status()
                with target.with_suffix('.part').open('wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
            target.with_suffix('.part').replace(target)
        provenance.append({'url': SOURCE + filename, 'sha256': digest(target), 'bytes': target.stat().st_size})
        with tarfile.open(target, 'r:gz') as archive:
            # Read only named JSON members; never extract paths or execute code.
            for member in archive.getmembers():
                if member.isfile() and member.name in {f'qasper-{split}-v0.3.json' for split in ('train', 'dev', 'test')}:
                    (raw / member.name).write_bytes(archive.extractfile(member).read())

    counts, papers_by_split, files = {}, {}, []
    for split in ('train', 'dev', 'test'):
        papers = json.loads((raw / f'qasper-{split}-v0.3.json').read_text(encoding='utf-8'))
        documents, cases = [], []
        for paper_id, paper in sorted(papers.items()):
            canonical = 'arxiv:' + paper_id
            paragraphs = [{'element_id': 'abstract', 'section': 'Abstract', 'text': paper['abstract'], 'page': None}]
            for section_index, section in enumerate(paper['full_text']):
                if section['section_name']:
                    paragraphs.append({'element_id': f's{section_index}_heading', 'section': section['section_name'], 'text': section['section_name'], 'page': None})
                for paragraph_index, text in enumerate(section['paragraphs']):
                    paragraphs.append({'element_id': f's{section_index}_p{paragraph_index}', 'section': section['section_name'], 'text': text, 'page': None})
            for index, figure in enumerate(paper.get('figures_and_tables', [])):
                paragraphs.append({'element_id': f'figure_table_{index}', 'section': 'figures_and_tables', 'text': figure['caption'], 'page': None})
            documents.append({'paper_id': canonical, 'source_paper_id': paper_id, 'split': split, 'title': paper['title'], 'abstract': paper['abstract'], 'paragraphs': paragraphs, 'source_url': f'https://arxiv.org/abs/{paper_id}', 'pdf_page_mapping': 'not_available'})
            for qa in paper['qas']:
                annotations = []
                for annotation in qa['answers']:
                    answer = annotation['answer']
                    if answer['unanswerable']:
                        reference = 'Unanswerable'
                    elif answer.get('extractive_spans'):
                        reference = ', '.join(answer['extractive_spans'])
                    elif answer.get('free_form_answer'):
                        reference = answer['free_form_answer']
                    elif answer.get('yes_no') is not None:
                        reference = 'Yes' if answer['yes_no'] else 'No'
                    else:
                        reference = answer.get('free_form_answer', '')
                    evidence = []
                    for quote in answer.get('evidence', []):
                        matches = [p['element_id'] for p in paragraphs if p['text'] == quote]
                        status = 'exact' if matches else 'unmapped'
                        if not matches:
                            # This prefix is a QASPER annotation marker, not paper text.
                            normalized = re.sub(r'^FLOAT SELECTED:\s*', '', quote)
                            matches = [p['element_id'] for p in paragraphs if p['text'] == normalized]
                            if matches:
                                status = 'float_prefix_removed'
                        evidence.append({'paper_id': canonical, 'quote': quote, 'element_ids': matches, 'page': None, 'pdf_sha256': None, 'match_status': status})
                    annotations.append({'annotation_id': annotation.get('annotation_id'), 'reference_answer': reference, 'answerable': not answer['unanswerable'], 'evidence': evidence, 'original_answer': answer})
                answerability = {a['answerable'] for a in annotations}
                cases.append({'question_id': 'qasper:' + qa['question_id'], 'source_question_id': qa['question_id'], 'dataset_source': 'allenai/qasper', 'dataset_version': '0.3', 'track': 'qasper_paragraph', 'split': split, 'paper_ids': [canonical], 'category': 'text', 'language': 'en', 'question': qa['question'], 'annotations': annotations, 'answerable': next(iter(answerability)) if len(answerability) == 1 else None, 'annotation_disagreement': len(answerability) > 1, 'review_status': 'source_human_annotated', 'reviewer_id': 'QASPER original annotators', 'license': 'CC-BY-4.0', 'difficulty': 'not_annotated'})
        for name, rows in ((f'{split}.jsonl', cases), (f'documents_{split}.jsonl', documents)):
            path = destination / name
            write_jsonl(path, rows)
            files.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': digest(path), 'rows': len(rows)})
        papers_by_split[split] = set(papers)
        counts[split] = {'papers': len(documents), 'questions': len(cases), 'answerability_disagreements': sum(c['annotation_disagreement'] for c in cases), 'answerability': dict(Counter(str(c['answerable']) for c in cases)), 'unmapped_evidence': sum(e['match_status'] == 'unmapped' for c in cases for a in c['annotations'] for e in a['evidence'])}
        print(split, counts[split], flush=True)
    overlaps = {f'{a}:{b}': sorted(papers_by_split[a] & papers_by_split[b]) for a, b in (('train', 'dev'), ('train', 'test'), ('dev', 'test'))}
    if any(overlaps.values()):
        raise RuntimeError(f'Cross-split paper leakage: {overlaps}')
    manifest = {'dataset': 'QASPER', 'version': '0.3', 'created_at': datetime.now(timezone.utc).isoformat(), 'source_card': 'https://huggingface.co/datasets/allenai/qasper', 'license': 'CC-BY-4.0', 'attribution': 'Dasigi et al. (2021), A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers', 'sources': provenance, 'counts': counts, 'paper_split_overlap': overlaps, 'files': files, 'limitations': ['No verified PDF page mapping; evaluate paragraph evidence only.', 'Original annotations may disagree; preserve all references.', 'Source labels are not newly human-reviewed by this project.', 'Documents contain paper content only, never QA gold labels.']}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    import_dataset()
