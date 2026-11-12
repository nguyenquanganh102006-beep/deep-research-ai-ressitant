"""Evaluate released PDF QA using production parsing/chunking and isolated caches.

python -m src.benchmark.run_pdf --method hybrid --split dev
Add --answer for Qwen generation. Answer correctness needs separate rubric review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pymupdf
from rank_bm25 import BM25Okapi

from config import PARSER_VERSION, PROJECT_ROOT
from src.benchmark.import_qasper import ROOT, digest, write_jsonl
from src.benchmark.run_qasper import metrics, tokens
from src.benchmark.validate import load


def parse_chunks(paper: dict) -> tuple[list[dict], Path]:
    from src.chunker import create_chunks
    from src.parser import parse_pdf
    pdf = PROJECT_ROOT / paper['pdf_path']
    if digest(pdf) != paper['pdf_sha256']:
        raise ValueError('Source PDF checksum mismatch')
    key = hashlib.sha256((paper['pdf_sha256'] + PARSER_VERSION).encode()).hexdigest()
    cache = ROOT / 'cache/pdf_parser' / key
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / 'chunks.json'
    if not path.exists():
        with pymupdf.open(pdf) as document:
            page_count = len(document)
        started = time.perf_counter()
        pages, markdown = parse_pdf(pdf, page_count)
        chunks = create_chunks(pages)
        if not chunks:
            raise ValueError('Parser returned no chunks')
        (cache / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
        (cache / 'parsed.md').write_text(markdown, encoding='utf-8')
        (cache / 'metadata.json').write_text(json.dumps({'paper_id': paper['paper_id'], 'pdf_sha256': paper['pdf_sha256'], 'parser_version': PARSER_VERSION, 'parse_and_chunk_seconds': time.perf_counter() - started, 'page_count': page_count}), encoding='utf-8')
        path.write_text(json.dumps(chunks, ensure_ascii=False), encoding='utf-8')
    return json.loads(path.read_text(encoding='utf-8')), cache


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['train', 'dev', 'test'], default='dev')
    parser.add_argument('--method', choices=['bm25', 'dense', 'hybrid', 'oracle', 'no_retrieval'], default='hybrid')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--answer', action='store_true')
    parser.add_argument('--model', default='qwen3.5:4b')
    args = parser.parse_args()
    os.environ['DEEPRESEARCH_MODEL'] = args.model
    from src.llm import answer_question, needs_visual_evidence, ollama_client
    from src.parser import render_page_png
    from src.metrics import capture_resource_metrics
    directory = ROOT / 'curated_v1'
    release = directory / ('test_frozen.jsonl' if args.split == 'test' else args.split + '.jsonl')
    cases = load(release)
    if args.limit is not None:
        if args.limit < 1:
            parser.error('--limit must be positive')
        cases = cases[:args.limit]
    if not cases:
        parser.error('Selected split has no cases')
    papers = {p['paper_id']: p for p in load(directory / 'papers.jsonl')}
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_pdf_' + args.method + '_' + args.split
    output = ROOT / 'evaluations' / run_id
    output.mkdir(parents=True)
    prepared = {}
    results = []
    started = time.perf_counter()
    resources_before = capture_resource_metrics()
    for case in cases:
        record = {'question_id': case['question_id'], 'category': case['category'], 'difficulty': case['difficulty'], 'paper_ids': case['paper_ids']}
        try:
            if len(case['paper_ids']) != 1:
                raise ValueError('Runner currently supports single-paper cases only')
            paper_id = case['paper_ids'][0]
            paper = papers[paper_id]
            if args.method not in ('oracle', 'no_retrieval'):
                if paper_id not in prepared:
                    chunks, cache = parse_chunks(paper)
                    sparse = BM25Okapi([tokens(c['content']) for c in chunks])
                    vectors = None
                    if args.method in ('dense', 'hybrid'):
                        from src.embeddings import embed_passages
                        from config import EMBEDDING_MODEL
                        vector_path = cache / (hashlib.sha256(EMBEDDING_MODEL.encode()).hexdigest()[:12] + '.npy')
                        if vector_path.exists():
                            vectors = np.load(vector_path, allow_pickle=False)
                        else:
                            vectors = embed_passages([c['content'] for c in chunks])
                            np.save(vector_path, vectors, allow_pickle=False)
                    prepared[paper_id] = (chunks, sparse, vectors)
                chunks, sparse, vectors = prepared[paper_id]
                sparse_scores = sparse.get_scores(tokens(case['question']))
                scores = sparse_scores
                if args.method in ('dense', 'hybrid'):
                    from src.embeddings import embed_query
                    scores = vectors @ embed_query(case['question'])
                    if args.method == 'hybrid':
                        fused = np.zeros(len(chunks))
                        for ranking in (np.argsort(-scores, kind='stable'), np.argsort(-sparse_scores, kind='stable')):
                            for rank, index in enumerate(ranking, 1):
                                fused[index] += 1 / (60 + rank)
                        scores = fused
                order = np.argsort(-scores, kind='stable')[:10]
                evidence = [chunks[i] for i in order]
            elif args.method == 'oracle':
                # Use only source pages, never reference answers or rubric checks.
                gold_pages = sorted({e['page'] for e in case.get('evidence', [])})
                with pymupdf.open(PROJECT_ROOT / paper['pdf_path']) as pdf:
                    evidence = [{'chunk_id': f'oracle_p{page}', 'page_start': page, 'page_end': page, 'type': 'text', 'content': pdf[page - 1].get_text()} for page in gold_pages]
            else:
                evidence = []
            ranked_pages = list(dict.fromkeys(page for e in evidence for page in range(e['page_start'], e['page_end'] + 1)))
            gold_pages = {str(e['page']) for e in case.get('evidence', [])}
            record.update({'retrieved_pages': ranked_pages, 'retrieved_chunks': [e['chunk_id'] for e in evidence], 'retrieval_metrics': {str(k): metrics([str(p) for p in ranked_pages], gold_pages, k) for k in (1, 5, 10)} if case['answerable'] and gold_pages and args.method not in ('oracle', 'no_retrieval') else None})
            if args.answer:
                # Do not let production's global equation-anchor search silently
                # supply an unretrieved page and turn a retrieval miss into an oracle.
                image_pages = list(dict.fromkeys(e['page_start'] for e in evidence[:5]))[:2]
                source_images = [(page, render_page_png(PROJECT_ROOT / paper['pdf_path'], page)) for page in image_pages] if evidence and needs_visual_evidence(case['question'], evidence[:5]) else None
                record['visual_evidence_pages'] = image_pages if source_images else []
                if args.method == 'no_retrieval':
                    response = ollama_client().chat(model=args.model, think=False, messages=[{'role': 'system', 'content': 'Trả lời câu hỏi bằng tiếng Việt từ kiến thức của bạn. Nếu không biết, nói không biết. Không tự tạo trích dẫn PDF.'}, {'role': 'user', 'content': case['question']}], options={'num_ctx': 4096, 'num_predict': 220, 'temperature': .15}, stream=False)
                    record['answer'] = response.message.content
                else:
                    generated = answer_question(case['question'], evidence[:5], source_images)
                    record.update(generated)
                record['answer_review_status'] = 'requires_rubric_review'
            record['error'] = None
        except Exception as exc:
            record['error'] = str(exc)
            if case['answerable'] and case.get('evidence') and args.method not in ('oracle', 'no_retrieval') and not record.get('retrieval_metrics'):
                record['retrieval_metrics'] = {str(k): {'hit': 0.0, 'recall': 0.0, 'mrr': 0.0, 'ndcg': 0.0} for k in (1, 5, 10)}
        results.append(record)
        # Atomic whole checkpoint; source/parse failures remain in denominator/report.
        write_jsonl(output / 'predictions.jsonl', results)
        print(case['question_id'], record['error'] or 'ok', flush=True)
    measurable = [r for r in results if r.get('retrieval_metrics')]
    summary = {'run_id': run_id, 'track': 'pdf_ai_reviewed', 'dataset_version': '1.0-ai-reviewed', 'split': args.split, 'method': args.method, 'answer_generation': args.answer, 'model': args.model if args.answer else None, 'parser_version': PARSER_VERSION, 'dataset_sha256': digest(release), 'papers_sha256': digest(directory / 'papers.jsonl'), 'questions': len(cases), 'completed': len(results), 'errors': sum(bool(r.get('error')) for r in results), 'measurable_retrieval_questions': len(measurable), 'metrics_at_k': {str(k): {key: sum(r['retrieval_metrics'][str(k)][key] for r in measurable) / len(measurable) if measurable else None for key in ('hit', 'recall', 'mrr', 'ndcg')} for k in (1, 5, 10)}, 'resources_before': resources_before, 'resources_after': capture_resource_metrics(), 'elapsed_seconds': time.perf_counter() - started, 'hardware': platform.platform(), 'limitations': ['AI-reviewed references, not human expert gold.', 'Answer correctness requires rubric review; citation checks do not prove claims.', 'Single-paper open-book; not multi-paper retrieval.', 'Retrieval metrics use unique PDF pages, not chunk ranks. Parse/retrieval failures reported separately; check errors before interpreting scores.', 'Oracle and no-retrieval scores do not measure retrieval.']}
    (output / 'metrics.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_jsonl(output / 'answer_review.template.jsonl', [{'question_id': r['question_id'], 'correctness': None, 'citation_supported': None, 'abstention_correct': None, 'reviewer_id': None, 'review_method': None, 'notes': ''} for r in results if 'answer' in r])
    print(output)


if __name__ == '__main__':
    main()
