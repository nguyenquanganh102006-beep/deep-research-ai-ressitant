"""Build immutable CPU sparse/dense corpus indexes with visual source routing."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sqlite3
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from config import EMBEDDING_MODEL
from src.corpus.collect import PROJECT, ROOT, PILOT, QUOTAS, atomic, now, sha


def visual_required(chunk, quality):
    pages = set(range(chunk['page_start'], chunk['page_end'] + 1))
    table = bool(re.search(r'(?m)^\s*\|(?:\s*:?-{3,}:?\s*\|){2,}\s*$', chunk['content']))
    caption = bool(re.search(r'\b(?:Figure|Fig\.?|Table)\s+\d', chunk['content']))
    return bool(chunk.get('parse_warning') or chunk['type'] in ('math', 'code', 'mixed') or pages.intersection(quality['dense_page_candidates']) or table or caption)


def pdf_visual_pages(path):
    import pymupdf
    result = []
    math_fonts = re.compile(r'CMMI|CMSY|CMEX|MSBM|STIX.*Math|CambriaMath|LatinModernMath', re.I)
    with pymupdf.open(path) as pdf:
        for number, page in enumerate(pdf, 1):
            if page.get_images() or page.get_drawings():
                result.append(number)
                continue
            blocks = page.get_text('dict', flags=0)['blocks']
            spans = [s for b in blocks for line in b.get('lines', []) for s in line.get('spans', [])]
            if any(s.get('flags', 0) & 8 or math_fonts.search(s.get('font', '')) for s in spans):
                result.append(number)
    return result


def quotas_for(target):
    if target == 100:
        return dict(PILOT)
    values = {k: int(v * target / 2000) for k, v in QUOTAS.items()}
    if target == 500:
        values['systems_algorithms'] += 1
    return values


def model_info():
    # Corpus builds use the already cached model, avoiding remote metadata probes.
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
    from src.embeddings import _model
    from huggingface_hub import try_to_load_from_cache
    config_path = try_to_load_from_cache(EMBEDDING_MODEL, 'config.json', revision='main')
    assert isinstance(config_path, str) and Path(config_path).is_file(), 'Embedding cache config missing'
    cached_revision = Path(config_path).parent.name
    assert re.fullmatch(r'[a-f0-9]{40}', cached_revision), 'Cache snapshot revision is not a commit hash'
    model = _model()
    configuration = model._first_module().auto_model.config
    revision = getattr(configuration, '_commit_hash', None) or cached_revision
    assert revision == cached_revision
    assert try_to_load_from_cache(EMBEDDING_MODEL, 'config.json', revision='main') == config_path, 'Cache main revision changed during loading'
    files = {}
    for name in ('model.safetensors', 'pytorch_model.bin', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'sentencepiece.bpe.model', 'modules.json', 'sentence_bert_config.json', '1_Pooling/config.json', 'config_sentence_transformers.json'):
        path = try_to_load_from_cache(EMBEDDING_MODEL, name, revision=revision)
        if isinstance(path, str) and Path(path).is_file():
            files[name] = sha(Path(path))
    assert 'model.safetensors' in files or 'pytorch_model.bin' in files, 'No cached embedding weight file to fingerprint'
    info = {'model': EMBEDDING_MODEL, 'revision': revision, 'revision_source': 'local_HF_snapshot_config_path', 'weight_and_config_sha256': files, 'max_seq_length': model.max_seq_length, 'sentence_transformers_version': importlib.metadata.version('sentence-transformers'), 'device': 'cpu', 'dtype': 'float32', 'normalized': True, 'passage_prefix': 'passage: ', 'query_prefix': 'query: '}
    info['fingerprint'] = hashlib.sha256(json.dumps(info, sort_keys=True).encode()).hexdigest()
    return info


def embed_cached(record, chunks, info):
    from src.embeddings import embed_passages
    text_hash = hashlib.sha256(json.dumps([c['content'] for c in chunks], ensure_ascii=False).encode()).hexdigest()
    folder = ROOT / 'embeddings' / record['pdf_sha256'][:24] / info['fingerprint'][:16]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (text_hash + '.npy')
    metadata = path.with_suffix('.json')
    if path.exists() and metadata.exists():
        previous = json.loads(metadata.read_text(encoding='utf-8'))
        assert previous['sha256'] == sha(path) and previous['input_sha256'] == text_hash
        vectors = np.load(path, allow_pickle=False)
    else:
        vectors = embed_passages([c['content'] for c in chunks])
        temp = path.with_suffix('.tmp')
        with temp.open('wb') as stream:
            np.save(stream, vectors, allow_pickle=False)
        temp.replace(path)
        atomic(metadata, json.dumps({'sha256': sha(path), 'input_sha256': text_hash, 'model_fingerprint': info['fingerprint'], 'rows': len(chunks)}, indent=2))
    assert vectors.shape[0] == len(chunks) and vectors.ndim == 2 and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=.002)
    return vectors


def build(target, name=None):
    import msvcrt
    ROOT.mkdir(parents=True, exist_ok=True)
    lock = (ROOT / 'index.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        return _build(target, name)
    finally:
        lock.close()


def _build(target, name=None):
    started = time.perf_counter()
    label = name or ('v1' if target == 2000 else f'pilot{target}')
    assert re.fullmatch(r'[a-zA-Z0-9_-]+', label), 'Invalid snapshot name'
    destination = ROOT / 'index' / label
    assert not destination.exists(), 'Index snapshot already exists; do not overwrite'
    db = sqlite3.connect(f'file:{(ROOT / "corpus.sqlite").as_posix()}?mode=ro', uri=True)
    records = []
    original_payloads = {}
    for topic, quota in quotas_for(target).items():
        rows = db.execute("SELECT metadata_json FROM papers WHERE primary_topic=? AND state IN ('parsed','indexed') ORDER BY paper_id LIMIT ?", (topic, quota)).fetchall()
        assert len(rows) == quota, f'{topic}: only {len(rows)} parsed / {quota}'
        for payload, in rows:
            record = json.loads(payload)
            records.append(record)
            original_payloads[record['paper_id']] = payload
    db.close()
    records.sort(key=lambda r: r['paper_id'])
    assert len({r['pdf_sha256'] for r in records}) == len(records) == target
    assert len({r['canonical_group_id'] for r in records}) == target
    prepared = []
    quality_rows = []
    for record in records:
        record['catalog_primary_topic'] = record.get('catalog_primary_topic', record['primary_topic'])
        record['primary_topic'] = record['corpus_primary_topic']
        assert sha(PROJECT / record['local_pdf_path']) == record['pdf_sha256']
        assert sha(PROJECT / record['resolver_path']) == record['resolver_sha256']
        directory = PROJECT / record['parsed_path']
        quality = json.loads((directory / 'quality.json').read_text(encoding='utf-8'))
        assert quality['pdf_sha256'] == record['pdf_sha256']
        record['parse_quality_sha256'] = sha(directory / 'quality.json')
        record['index_status'] = 'ready'
        record['index_snapshot'] = label
        assert all(sha(directory / name) == expected for name, expected in quality['files'].items())
        record['visual_source_pages'] = pdf_visual_pages(PROJECT / record['local_pdf_path'])
        chunks = [json.loads(line) for line in (directory / 'chunks.jsonl').read_text(encoding='utf-8').split('\n') if line]
        assert len(chunks) == quality['chunks']
        for chunk in chunks:
            assert chunk['pdf_sha256'] == record['pdf_sha256'] and chunk['paper_id'] == record['paper_id']
            assert 1 <= chunk['page_start'] <= chunk['page_end'] <= record['page_count']
            assert not set(chunk) & {'reference_answer', 'question', 'annotations'}
            chunk['visual_grounding_required'] = visual_required(chunk, quality) or bool(set(range(chunk['page_start'], chunk['page_end'] + 1)).intersection(record['visual_source_pages']))
            chunk['local_pdf_path'] = record['local_pdf_path']
        prepared.append((record, chunks))
        quality_rows.append(quality)
    info = model_info()
    work = destination.with_name(destination.name + '.building-' + now().replace(':', '').replace('+', '_'))
    work.mkdir(parents=True)
    index_db = sqlite3.connect(work / 'search.sqlite')
    index_db.executescript('''CREATE TABLE papers(paper_id TEXT PRIMARY KEY,metadata_json TEXT);
    CREATE TABLE chunks(embedding_row INTEGER PRIMARY KEY,chunk_id TEXT UNIQUE,paper_id TEXT,page_start INTEGER,page_end INTEGER,metadata_json TEXT);
    CREATE INDEX chunk_paper ON chunks(paper_id);
    CREATE VIRTUAL TABLE search USING fts5(title,content);''')
    total = sum(len(chunks) for _, chunks in prepared)
    matrix = None
    offset = 0
    writer = None
    for record, chunks in prepared:
        vectors = embed_cached(record, chunks, info)
        if matrix is None:
            matrix = np.lib.format.open_memmap(work / 'embeddings.npy', mode='w+', dtype='float32', shape=(total, vectors.shape[1]))
        matrix[offset:offset + len(chunks)] = vectors
        export_rows = []
        with index_db:
            index_db.execute('INSERT INTO papers VALUES(?,?)', (record['paper_id'], json.dumps(record, ensure_ascii=False)))
            for relative, chunk in enumerate(chunks):
                row = offset + relative
                payload = json.dumps(chunk, ensure_ascii=False)
                index_db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)', (row, chunk['chunk_id'], record['paper_id'], chunk['page_start'], chunk['page_end'], payload))
                index_db.execute('INSERT INTO search(rowid,title,content) VALUES(?,?,?)', (row + 1, record['title'], chunk['content']))
                export_rows.append({'embedding_row': row, 'chunk_id': chunk['chunk_id'], 'paper_id': record['paper_id'], 'page_start': chunk['page_start'], 'page_end': chunk['page_end'], 'content': chunk['content'], 'metadata_json': payload})
        table = pa.Table.from_pylist(export_rows)
        if writer is None:
            writer = pq.ParquetWriter(work / 'chunks.parquet', table.schema, compression='zstd')
        writer.write_table(table)
        offset += len(chunks)
        print('EMBEDDED', record['paper_id'], offset, '/', total, flush=True)
    writer.close()
    matrix.flush()
    dimension = matrix.shape[1]
    del matrix
    assert index_db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert index_db.execute('SELECT count(*) FROM chunks').fetchone()[0] == total
    assert index_db.execute('SELECT count(*) FROM search').fetchone()[0] == total
    index_db.close()
    assert pq.ParquetFile(work / 'chunks.parquet').metadata.num_rows == total
    atomic(work / 'papers.jsonl', ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
    dense = sum(q['dense_candidate'] for q in quality_rows)
    quality_report = {'papers': target, 'pages': sum(r['page_count'] for r in records), 'chunks': total, 'topic_counts': dict(Counter(r['corpus_primary_topic'] for r in records)), 'publication_years_atom': dict(Counter(r['publication_year'] for r in records)), 'raw_pdf_bytes': sum(r['pdf_bytes'] for r in records), 'parser_backends': dict(Counter(q['backend'] for q in quality_rows)), 'warning_count': sum(q['warning_count'] for q in quality_rows), 'replacement_characters': sum(q['replacement_characters'] for q in quality_rows), 'low_text_pages': sum(len(q['empty_or_low_text_pages']) for q in quality_rows), 'dense_candidates': dense, 'dense_candidate_rate': dense / target, 'density_is_heuristic': True, 'math_transcription_verified': False, 'visual_source_routing': True, 'max_parser_peak_bytes': max(q['peak_process_bytes'] for q in quality_rows), 'parse_seconds_total': sum(q['elapsed_seconds'] for q in quality_rows), 'embedding_and_build_seconds': time.perf_counter() - started, 'limitations': ['Markdown math/code/table transcription is not gold; raw PDF page is authoritative.', 'Dense indicator is heuristic and requires source spot checks.', 'No model answer benchmark or production UI integration claimed.']}
    atomic(work / 'quality_report.json', json.dumps(quality_report, indent=2))
    manifest = {'version': label, 'created_at': now(), 'papers': target, 'chunks': total, 'embedding_dimension': dimension, 'embedding': info, 'metadata_and_pdf_only_no_qa_labels': True, 'files': {p.name: {'sha256': sha(p), 'bytes': p.stat().st_size} for p in work.iterdir() if p.is_file()}, 'source_pdf_sha256': {r['paper_id']: r['pdf_sha256'] for r in records}}
    atomic(work / 'manifest.json', json.dumps(manifest, indent=2))
    work.replace(destination)
    workflow = sqlite3.connect(ROOT / 'corpus.sqlite', timeout=30)
    with workflow:
        for record in records:
            workflow.execute('UPDATE papers SET state=?,metadata_json=? WHERE paper_id=? AND metadata_json=?', ('indexed', json.dumps(record, ensure_ascii=False), record['paper_id'], original_payloads[record['paper_id']]))
    workflow.close()
    print('INDEX COMPLETE', destination, flush=True)


def search(index, query, method='hybrid', k=5):
    manifest = json.loads((index / 'manifest.json').read_text(encoding='utf-8'))
    db = sqlite3.connect(f'file:{(index / "search.sqlite").as_posix()}?mode=ro', uri=True)
    terms = re.findall(r'\w+', query, flags=re.UNICODE)
    assert terms, 'Empty query'
    expression = ' OR '.join('"' + term + '"' for term in terms[:30])
    sparse = [row - 1 for row, in db.execute('SELECT rowid FROM search WHERE search MATCH ? ORDER BY bm25(search,2.0,1.0) LIMIT 100', (expression,))]
    dense = []
    if method in ('dense', 'hybrid'):
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
        os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
        from src.embeddings import _model, embed_query
        assert EMBEDDING_MODEL == manifest['embedding']['model'], 'Query embedding model differs from index'
        assert model_info()['fingerprint'] == manifest['embedding']['fingerprint'], 'Query embedding fingerprint differs from index'
        vector = embed_query(query)
        matrix = np.load(index / 'embeddings.npy', mmap_mode='r', allow_pickle=False)
        scores = matrix @ vector
        dense = np.argsort(-scores, kind='stable')[:100].tolist()
    if method == 'bm25':
        ranking = sparse
    elif method == 'dense':
        ranking = dense
    else:
        fused = Counter()
        for ranking in (sparse, dense):
            for rank, row in enumerate(ranking, 1):
                fused[row] += 1 / (60 + rank)
        ranking = [row for row, _ in fused.most_common()]
    results = []
    force_visual = bool(re.search(r'equation|formula|algorithm|công thức|thuật toán|tensor|gradient|loss|shape|norm|table|figure|chart|bảng|hình|biểu đồ', query, re.I))
    for row in ranking[:k]:
        item = db.execute('SELECT metadata_json FROM chunks WHERE embedding_row=?', (int(row),)).fetchone()
        chunk = json.loads(item[0])
        chunk['visual_grounding_required'] = chunk['visual_grounding_required'] or force_visual
        results.append(chunk)
    db.close()
    return results


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=[100, 500, 2000], default=100)
    parser.add_argument('--query')
    parser.add_argument('--method', choices=['bm25', 'dense', 'hybrid'], default='hybrid')
    parser.add_argument('--index', type=Path)
    parser.add_argument('--name', help='New immutable snapshot name for a revised pilot')
    parser.add_argument('--wait-for', type=int, help='Wait for a parser/cache coordinator PID, then require all stage quotas')
    args = parser.parse_args()
    if args.query:
        active = ROOT / 'index' / f'active_{args.target}.json'
        if args.index:
            folder = args.index
        elif args.name:
            folder = ROOT / 'index' / args.name
        elif active.exists():
            pointer = json.loads(active.read_text(encoding='utf-8'))
            assert re.fullmatch(r'[a-zA-Z0-9_-]+', pointer['snapshot'])
            folder = ROOT / 'index' / pointer['snapshot']
            assert sha(folder / 'manifest.json') == pointer['manifest_sha256']
        else:
            folder = ROOT / 'index' / ('v1' if args.target == 2000 else f'pilot{args.target}')
        print(json.dumps(search(folder, args.query, args.method), ensure_ascii=False, indent=2))
    else:
        if args.wait_for:
            import psutil
            try:
                process = psutil.Process(args.wait_for)
                assert any(module in process.cmdline() for module in ('src.corpus.process', 'src.corpus.cache_embeddings')) and '--one' not in process.cmdline()
                print('Waiting for coordinator PID', args.wait_for, flush=True)
                while process.is_running():
                    time.sleep(15)
            except psutil.NoSuchProcess:
                pass
        build(args.target, args.name)
