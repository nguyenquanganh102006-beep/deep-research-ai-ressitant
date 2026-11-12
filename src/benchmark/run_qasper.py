"""Paragraph retrieval baseline; dev by default, never tune on frozen test.

python -m src.benchmark.run_qasper --split dev
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import re
import time
from datetime import datetime, timezone

import numpy as np
from rank_bm25 import BM25Okapi

from src.benchmark.import_qasper import ROOT, digest, write_jsonl
from src.benchmark.validate import load


def tokens(text: str) -> list[str]:
    return re.findall(r'\w+', text.casefold()) or ['__empty__']


def metrics(ranked: list[str], relevant: set[str], k: int) -> dict:
    hits = [int(item in relevant) for item in ranked[:k]]
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    return {'hit': float(any(hits)), 'recall': sum(hits) / len(relevant), 'mrr': next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0.0), 'ndcg': dcg / ideal if ideal else 0.0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['train', 'dev', 'test'], default='dev')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--method', choices=['bm25', 'dense', 'hybrid'], default='bm25')
    args = parser.parse_args()
    directory = ROOT / 'external' / 'qasper'
    cases = load(directory / f'{args.split}.jsonl')
    if args.limit is not None:
        if args.limit <= 0:
            parser.error('--limit must be positive')
        cases = cases[:args.limit]
    documents = {d['paper_id']: d for d in load(directory / f'documents_{args.split}.jsonl')}
    indexes = {}
    vectors_by_paper = {}
    query_vectors = None
    start = time.perf_counter()
    if args.method != 'bm25':
        from config import EMBEDDING_MODEL
        from src.embeddings import _model, embed_passages
        model_key = hashlib.sha256(EMBEDDING_MODEL.encode()).hexdigest()[:12]
        cache = ROOT / 'cache' / 'qasper_embeddings' / model_key
        cache.mkdir(parents=True, exist_ok=True)
        query_vectors = _model().encode(['query: ' + c['question'] for c in cases], batch_size=16, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    results = []
    for case_index, case in enumerate(cases):
        paper_id = case['paper_ids'][0]
        paragraphs = documents[paper_id]['paragraphs']
        if paper_id not in indexes:
            indexes[paper_id] = BM25Okapi([tokens(p['text']) for p in paragraphs])
        sparse_scores = indexes[paper_id].get_scores(tokens(case['question']))
        scores = sparse_scores
        if args.method != 'bm25':
            if paper_id not in vectors_by_paper:
                payload = json.dumps([p['text'] for p in paragraphs], ensure_ascii=False)
                cache_path = cache / (hashlib.sha256(payload.encode()).hexdigest() + '.npy')
                if cache_path.exists():
                    vectors = np.load(cache_path, allow_pickle=False)
                else:
                    vectors = embed_passages([p['text'] for p in paragraphs])
                    np.save(cache_path, vectors, allow_pickle=False)
                if vectors.shape[0] != len(paragraphs):
                    raise ValueError('Embedding cache shape mismatch')
                vectors_by_paper[paper_id] = vectors
            scores = vectors_by_paper[paper_id] @ query_vectors[case_index]
            if args.method == 'hybrid':
                fused = np.zeros(len(paragraphs), dtype=np.float64)
                for ranking in (np.argsort(-scores, kind='stable'), np.argsort(-sparse_scores, kind='stable')):
                    for rank, index in enumerate(ranking, 1):
                        fused[index] += 1 / (60 + rank)
                scores = fused
        order = np.argsort(-scores, kind='stable')[:10].tolist()
        ranked = [paragraphs[index]['element_id'] for index in order]
        annotations = []
        for annotation in case['annotations']:
            relevant = {eid for e in annotation['evidence'] for eid in e['element_ids']}
            has_unmapped = any(not e['element_ids'] for e in annotation['evidence'])
            # Report only fully mapped answerable annotations, not a distorted
            # recall denominator silently omitting unavailable gold evidence.
            eligible = annotation['answerable'] and bool(relevant) and not has_unmapped
            annotations.append({'annotation_id': annotation['annotation_id'], 'eligible': eligible, 'exclusion_reason': None if eligible else 'unanswerable' if not annotation['answerable'] else 'incomplete_or_missing_evidence_mapping', 'metrics': {str(k): metrics(ranked, relevant, k) for k in (1, 5, 10)} if eligible else None})
        results.append({'question_id': case['question_id'], 'paper_id': paper_id, 'retrieved': [{'element_id': paragraphs[i]['element_id'], 'score': float(scores[i])} for i in order], 'annotation_scores': annotations})
    measured = [a for r in results for a in r['annotation_scores'] if a['eligible']]
    aggregate = {str(k): {key: sum(a['metrics'][str(k)][key] for a in measured) / len(measured) if measured else None for key in ('hit', 'recall', 'mrr', 'ndcg')} for k in (1, 5, 10)}
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_qasper_' + args.method + '_' + args.split
    output = ROOT / 'evaluations' / run_id
    output.mkdir(parents=True)
    write_jsonl(output / 'predictions.jsonl', results)
    report = {'run_id': run_id, 'track': 'qasper_paragraph', 'dataset_version': '0.3', 'split': args.split, 'mode': 'single_paper_open_book_paragraph_retrieval', 'baseline': args.method, 'configuration': {'k1': 1.5, 'b': 0.75, 'epsilon': 0.25, 'tokenizer': 'unicode_word_casefold_v1', 'embedding_model': EMBEDDING_MODEL if args.method != 'bm25' else None, 'fusion': 'RRF_k60_all_paragraphs' if args.method == 'hybrid' else None}, 'questions': len(results), 'questions_with_measurable_annotation': sum(any(a['eligible'] for a in r['annotation_scores']) for r in results), 'eligible_annotations': len(measured), 'excluded_annotations': sum(not a['eligible'] for r in results for a in r['annotation_scores']), 'aggregation': 'macro over fully mapped answerable annotations; disagreements retained; not official QASPER answer score', 'metrics_at_k': aggregate, 'elapsed_seconds': round(time.perf_counter() - start, 3), 'hardware': platform.platform(), 'input_sha256': {name: digest(directory / name) for name in (f'{args.split}.jsonl', f'documents_{args.split}.jsonl')}, 'runner_sha256': hashlib.sha256(open(__file__, 'rb').read()).hexdigest(), 'limitations': ['No answer generation or correctness measurement.', 'No PDF page citation measurement.', 'Partially mapped annotations excluded with explicit reason and counts.']}
    (output / 'metrics.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
