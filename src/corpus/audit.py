"""Verify corpus snapshot provenance, page mappings, vector rows and storage."""
import argparse
from collections import Counter
import json
import re
from pathlib import Path
import shutil
import sqlite3
import xml.etree.ElementTree as ET

import numpy as np
import pyarrow.parquet as pq
import pymupdf

from src.corpus.collect import PROJECT, ROOT, ATOM, allowed_license, atomic, now, sha
from src.corpus.index import quotas_for, visual_required, pdf_visual_pages


def audit(target, index=None):
    label = 'v1' if target == 2000 else f'pilot{target}'
    folder = index or ROOT / 'index' / label
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    label = manifest['version']
    assert re.fullmatch(r'[a-zA-Z0-9_-]+', label)
    for name, item in manifest['files'].items():
        assert sha(folder / name) == item['sha256'] and (folder / name).stat().st_size == item['bytes'], name
    records = [json.loads(line) for line in (folder / 'papers.jsonl').read_text(encoding='utf-8').split('\n') if line]
    assert len(records) == target == manifest['papers']
    assert len({r['paper_id'] for r in records}) == target
    assert len({r['canonical_group_id'] for r in records}) == target
    assert len({r['pdf_sha256'] for r in records}) == target
    assert dict(Counter(r['primary_topic'] for r in records)) == quotas_for(target)
    qualities = {}
    page_total = 0
    for record in records:
        pdf_path = PROJECT / record['local_pdf_path']
        assert pdf_path.resolve().is_relative_to((ROOT / 'raw').resolve())
        assert sha(pdf_path) == record['pdf_sha256'] == manifest['source_pdf_sha256'][record['paper_id']]
        assert pdf_path.stat().st_size == record['pdf_bytes']
        assert record['visual_source_pages'] == pdf_visual_pages(pdf_path)
        with pymupdf.open(pdf_path) as pdf:
            assert not pdf.needs_pass and len(pdf) == record['page_count']
        assert allowed_license(record['license'])
        resolver = PROJECT / record['resolver_path']
        assert sha(resolver) == record['resolver_sha256']
        entries = ET.fromstring(resolver.read_bytes()).findall(ATOM + 'entry')
        matching = [e for e in entries if (e.findtext(ATOM + 'id') or '').endswith('/' + record['versioned_id'])]
        assert len(matching) == 1
        assert matching[0].findtext(ATOM + 'published') == record['published']
        assert int(record['published'][:4]) == record['publication_year']
        assert record['download_url'].endswith('/' + record['versioned_id'])
        directory = PROJECT / record['parsed_path']
        assert sha(directory / 'quality.json') == record['parse_quality_sha256']
        quality = json.loads((directory / 'quality.json').read_text(encoding='utf-8'))
        assert quality['pdf_sha256'] == record['pdf_sha256']
        assert all(sha(directory / name) == expected for name, expected in quality['files'].items())
        pages = [json.loads(line) for line in (directory / 'pages.jsonl').read_text(encoding='utf-8').split('\n') if line]
        assert [p['page_number'] for p in pages] == list(range(1, record['page_count'] + 1))
        qualities[record['paper_id']] = (record, quality)
        page_total += len(pages)
    db = sqlite3.connect(f'file:{(folder / "search.sqlite").as_posix()}?mode=ro', uri=True)
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('SELECT count(*) FROM papers').fetchone()[0] == target
    vectors = np.load(folder / 'embeddings.npy', mmap_mode='r', allow_pickle=False)
    assert vectors.shape == (manifest['chunks'], manifest['embedding_dimension'])
    assert vectors.dtype == np.float32
    for offset in range(0, len(vectors), 1024):
        batch = vectors[offset:offset + 1024]
        assert np.isfinite(batch).all() and np.allclose(np.linalg.norm(batch, axis=1), 1, atol=.002)
    count = 0
    visual = 0
    for batch in pq.ParquetFile(folder / 'chunks.parquet').iter_batches(batch_size=1024):
        for item in batch.to_pylist():
            assert item['embedding_row'] == count
            row = db.execute('SELECT chunk_id,paper_id,page_start,page_end,metadata_json FROM chunks WHERE embedding_row=?', (count,)).fetchone()
            assert row == tuple(item[k] for k in ('chunk_id', 'paper_id', 'page_start', 'page_end', 'metadata_json'))
            chunk = json.loads(row[4])
            record, quality = qualities[chunk['paper_id']]
            assert chunk['content'] == item['content']
            assert chunk['pdf_sha256'] == record['pdf_sha256']
            assert 1 <= chunk['page_start'] <= chunk['page_end'] <= record['page_count']
            if visual_required(chunk, quality):
                assert chunk['visual_grounding_required']
            if set(range(chunk['page_start'], chunk['page_end'] + 1)).intersection(record['visual_source_pages']):
                assert chunk['visual_grounding_required']
            visual += bool(chunk['visual_grounding_required'])
            assert not set(chunk) & {'question', 'reference_answer', 'annotations'}
            count += 1
    assert count == manifest['chunks'] == db.execute('SELECT count(*) FROM chunks').fetchone()[0]
    assert count == db.execute('SELECT count(*) FROM search').fetchone()[0]
    db.close()
    resource = json.loads((folder / 'quality_report.json').read_text(encoding='utf-8'))
    total_bytes = sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file())
    parsed_bytes = sum(sum(p.stat().st_size for p in (PROJECT / r['parsed_path']).iterdir() if p.is_file()) for r in records)
    index_bytes = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
    project_bytes = sum(p.stat().st_size for p in PROJECT.rglob('*') if p.is_file())
    disk_free = shutil.disk_usage(ROOT).free
    assert disk_free >= 30 * 2**30 and total_bytes <= 60 * 2**30 and project_bytes <= 70 * 2**30
    report = {'passed': True, 'audited_at': now(), 'stage': label, 'papers': target, 'pages': page_total, 'chunks': count, 'visual_grounding_chunks': visual, 'topic_counts': quotas_for(target), 'corpus_bytes': total_bytes, 'disk_free_bytes': disk_free, 'raw_pdf_bytes': resource['raw_pdf_bytes'], 'projected_raw_pdf_bytes_at_2000': resource['raw_pdf_bytes'] * 2000 / target, 'projection_is_estimate': True, 'math_text_verified': False, 'density_is_heuristic': True, 'dense_candidate_rate': resource['dense_candidate_rate'], 'checks': ['all index file SHA256 and bytes', 'unique paper/canonical/PDF IDs', 'exact topic quotas', 'PDF checksum size pages and readable', 'version and published date against original Atom', 'license selection policy', 'all parsed sidecar checksums', 'all pages 1-based and complete', 'every Parquet chunk equals SQLite with correct embedding row', 'all vectors finite normalized float32', 'visual source flags on lossy/math/code pages', 'no QA label keys', 'storage guardrails'], 'index_manifest_sha256': sha(folder / 'manifest.json'), 'audit_program_sha256': sha(Path(__file__))}
    report.update({'parsed_bytes': parsed_bytes, 'index_bytes': index_bytes, 'project_bytes': project_bytes, 'bytes_per_pdf': resource['raw_pdf_bytes'] / target, 'parsed_bytes_per_pdf': parsed_bytes / target, 'pages_per_pdf': page_total / target, 'chunks_per_pdf': count / target, 'embedding_bytes': (folder / 'embeddings.npy').stat().st_size, 'projected_parsed_bytes_at_2000': parsed_bytes * 2000 / target, 'projected_index_bytes_at_2000': index_bytes * 2000 / target, 'projection_within_raw_parsed_index_budgets': resource['raw_pdf_bytes'] * 2000 / target < 25 * 2**30 and parsed_bytes * 2000 / target < 15 * 2**30 and index_bytes * 2000 / target < 7 * 2**30})
    atomic(ROOT / 'reports' / ('audit_' + label + '.json'), json.dumps(report, indent=2))
    atomic(ROOT / 'index' / f'active_{target}.json', json.dumps({'snapshot': label, 'manifest_sha256': report['index_manifest_sha256'], 'audit': 'reports/audit_' + label + '.json'}, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=[100, 500, 2000], default=100)
    parser.add_argument('--index', type=Path)
    args = parser.parse_args()
    audit(args.target, args.index)
