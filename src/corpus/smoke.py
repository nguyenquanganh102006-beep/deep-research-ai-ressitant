"""Diagnostic corpus retrieval checks, not a QA benchmark score."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import time

import numpy as np

from src.corpus.collect import ROOT, atomic, now, sha
from src.corpus.index import model_info, search, quotas_for


def smoke(target, index=None):
    if index is None:
        pointer = json.loads((ROOT / 'index' / f'active_{target}.json').read_text(encoding='utf-8'))
        assert re.fullmatch(r'[a-zA-Z0-9_-]+', pointer['snapshot'])
        index = ROOT / 'index' / pointer['snapshot']
        assert sha(index / 'manifest.json') == pointer['manifest_sha256']
    manifest = json.loads((index / 'manifest.json').read_text(encoding='utf-8'))
    assert model_info()['fingerprint'] == manifest['embedding']['fingerprint']
    db = sqlite3.connect(f'file:{(index / "search.sqlite").as_posix()}?mode=ro', uri=True)
    matrix = np.load(index / 'embeddings.npy', mmap_mode='r', allow_pickle=False)
    indices = [0, len(matrix) // 2, len(matrix) - 1]
    texts = [json.loads(db.execute('SELECT metadata_json FROM chunks WHERE embedding_row=?', (row,)).fetchone()[0])['content'] for row in indices]
    from src.embeddings import embed_passages
    fresh = embed_passages(texts)
    similarities = [float(matrix[row] @ fresh[offset]) for offset, row in enumerate(indices)]
    assert min(similarities) > .999, 'Vector rows differ from fresh source embeddings'
    records = [json.loads(row[0]) for row in db.execute('SELECT metadata_json FROM papers ORDER BY paper_id')]
    db.close()
    selected = [next(r for r in records if r['primary_topic'] == label) for label in quotas_for(target)]
    results = []
    for record in selected:
        for method in ('bm25', 'dense', 'hybrid'):
            started = time.perf_counter()
            hits = search(index, record['title'], method, 5)
            results.append({'topic': record['primary_topic'], 'query': record['title'], 'expected_paper_id': record['paper_id'], 'method': method, 'hit_at_5': any(h['paper_id'] == record['paper_id'] for h in hits), 'elapsed_seconds': time.perf_counter() - started, 'retrieved': [{'paper_id': h['paper_id'], 'page_start': h['page_start'], 'page_end': h['page_end'], 'visual_required': h['visual_grounding_required']} for h in hits]})
            print(method, record['paper_id'], results[-1]['hit_at_5'], flush=True)
    report = {'checked_at': now(), 'stage': manifest['version'], 'diagnostic_only': True, 'not_qa_benchmark': True, 'selection': 'first paper by arXiv ID within each corpus topic; full title as query', 'fresh_embedding_rows': indices, 'fresh_embedding_cosines': similarities, 'title_query_hits_at_5': {method: {'hits': sum(r['hit_at_5'] for r in results if r['method'] == method), 'queries': len(selected)} for method in ('bm25', 'dense', 'hybrid')}, 'results': results, 'index_manifest_sha256': sha(index / 'manifest.json')}
    atomic(ROOT / 'reports' / ('smoke_' + manifest['version'] + '.json'), json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('fresh_embedding_cosines', 'title_query_hits_at_5')}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=[100, 500, 2000], default=100)
    parser.add_argument('--index', type=Path)
    args = parser.parse_args()
    smoke(args.target, args.index)
