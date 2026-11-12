"""Audit all harvested metadata against raw XML and publish a V1 snapshot."""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import unicodedata

from src.catalog.harvest import now, parse


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def normalized_doi(value):
    if not value:
        return None
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', value.strip(), flags=re.I)
    return value.casefold() if re.fullmatch(r'10\.\d{4,9}/\S+', value) else None


def normalize(record):
    output = dict(record)
    categories = record['categories']
    category = next((c for c in categories if c.startswith(('cs.', 'math.', 'stat.'))), None)
    output['primary_topic'] = 'computer_science' if category and category.startswith('cs.') else 'mathematics' if category and category.startswith('math.') else 'statistics' if category and category.startswith('stat.') else 'other_crosslisted'
    output['primary_arxiv_category'] = categories[0] if categories else None
    output['scope_category'] = category
    output['tags'] = list(categories)
    output['oa_status'] = 'open_access_repository'
    output['pdf_access_verified'] = False
    output['pdf_status'] = 'not_downloaded'
    output['publication_year'] = int(record['created'][:4]) if record.get('created') and re.match(r'^\d{4}-', record['created']) else None
    output['normalized_doi'] = normalized_doi(record.get('doi'))
    output['canonical_group_id'] = 'doi:' + output['normalized_doi'] if output['normalized_doi'] else output['paper_id']
    output['author_names'] = [' '.join(a[k] for k in ('forenames', 'keyname', 'suffix') if a.get(k)) for a in record['authors']]
    # Fixed nested schema avoids Parquet adding absent keys during round trip.
    output['authors'] = [{key: author.get(key) for key in ('keyname', 'forenames', 'suffix', 'affiliation')} for author in record['authors']]
    return output


def publish(root, minimum=100000):
    import msvcrt
    lock = (root / 'harvest.lock').open('r+b')
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        db = sqlite3.connect(f'file:{(root / "catalog.sqlite").as_posix()}?mode=ro', uri=True)
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        staged = {pid: json.loads(payload) for pid, payload in db.execute('SELECT paper_id,metadata_json FROM works')}
        assert len(staged) >= minimum, f'Not enough metadata: {len(staged)} / {minimum}'
        provenance = {}
        batch_files = []
        for expected_sha, group, filename, expected_records in db.execute('SELECT sha256,source_set,path,records FROM batches ORDER BY rowid'):
            path = root / filename
            assert path.resolve().is_relative_to(root.resolve())
            payload = gzip.decompress(path.read_bytes())
            assert hashlib.sha256(payload).hexdigest() == expected_sha
            records, _ = parse(payload)
            assert len(records) == expected_records
            for record in records:
                provenance[record['paper_id']] = (record, filename)
            batch_files.append({'path': filename, 'xml_sha256': expected_sha, 'gzip_sha256': sha(path), 'source_set': group, 'records': len(records)})
        assert set(staged) == set(provenance), 'Source preservation mismatch'
        rows = []
        for pid in sorted(staged):
            record, filename = provenance[pid]
            # Fetch timestamp and derived topic are not upstream source fields.
            source_fields = set(record) - {'fetched_at', 'primary_topic'}
            assert all(staged[pid].get(k) == record[k] for k in source_fields), f'Upstream fields changed: {pid}'
            item = normalize(staged[pid])
            item['raw_source_path'] = filename
            assert item['scope_category'] and item['authors'] and item['publication_year']
            assert item['title'] and item['abstract'] and item['source_url']
            assert item['version'] is None and item['pdf_downloaded'] is False
            rows.append(item)
        db.close()
        destination = root / 'v1'
        assert not destination.exists(), 'Release exists: validate it, do not overwrite'
        work = root / ('release_staging_' + now().replace(':', '').replace('+', '_'))
        work.mkdir()
        with gzip.open(work / 'works.jsonl.gz', 'wt', encoding='utf-8', newline='\n') as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, work / 'works.parquet', compression='zstd')
        assert pq.read_table(work / 'works.parquet').to_pylist() == rows
        with gzip.open(work / 'works.jsonl.gz', 'rt', encoding='utf-8') as stream:
            assert [json.loads(line) for line in stream] == rows
        release_db = sqlite3.connect(work / 'catalog.sqlite')
        release_db.executescript('''CREATE TABLE works(paper_id TEXT PRIMARY KEY,canonical_group_id TEXT,normalized_doi TEXT,title TEXT,publication_year INTEGER,primary_topic TEXT,metadata_json TEXT);
        CREATE INDEX works_doi ON works(normalized_doi); CREATE INDEX works_year ON works(publication_year); CREATE INDEX works_topic ON works(primary_topic);
        CREATE VIRTUAL TABLE search USING fts5(paper_id UNINDEXED,title,abstract);''')
        with release_db:
            release_db.executemany('INSERT INTO works VALUES(?,?,?,?,?,?,?)', [(r['paper_id'], r['canonical_group_id'], r['normalized_doi'], r['title'], r['publication_year'], r['primary_topic'], json.dumps(r, ensure_ascii=False)) for r in rows])
            release_db.executemany('INSERT INTO search VALUES(?,?,?)', [(r['paper_id'], r['title'], r['abstract']) for r in rows])
        assert release_db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert release_db.execute('SELECT count(*) FROM works').fetchone()[0] == len(rows)
        assert release_db.execute('SELECT count(*) FROM search').fetchone()[0] == len(rows)
        release_db.close()
        title_groups = defaultdict(list)
        doi_groups = defaultdict(list)
        for row in rows:
            title_groups[' '.join(unicodedata.normalize('NFKC', row['title']).casefold().split())].append(row['paper_id'])
            if row['normalized_doi']:
                doi_groups[row['normalized_doi']].append(row['paper_id'])
        duplicates = {'normalized_title_collisions': [v for v in title_groups.values() if len(v) > 1], 'shared_doi_groups': {k: v for k, v in doi_groups.items() if len(v) > 1}, 'policy': 'Preserve distinct arXiv works; same normalized DOI shares canonical_group_id. Title collisions flagged, not silently merged.'}
        (work / 'dedup_report.json').write_text(json.dumps(duplicates, indent=2), encoding='utf-8')
        audit = {'passed': True, 'checked_at': now(), 'papers': len(rows), 'canonical_groups': len({r['canonical_group_id'] for r in rows}), 'primary_topic_counts': dict(Counter(r['primary_topic'] for r in rows)), 'publication_year_counts': dict(sorted(Counter(r['publication_year'] for r in rows).items())), 'missing_doi': sum(not r['doi'] for r in rows), 'unparsed_doi': sum(bool(r['doi']) and not r['normalized_doi'] for r in rows), 'missing_pdf_license': sum(not r['pdf_license'] for r in rows), 'metadata_license': 'CC0-1.0', 'metadata_only': True, 'raw_batches': len(batch_files), 'checks': ['SQLite integrity', 'unique arXiv IDs', 'every raw batch checksum and record count', 'all selected source fields preserved against raw', 'scope/categories/authors/year/title/abstract', 'JSONL full round trip', 'Parquet full round trip', 'search row count', 'DOI group and normalized title collision report']}
        (work / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
        readme = f'''# Catalog B V1

Published: {audit['checked_at']} (UTC).

- {len(rows):,} distinct arXiv records; {audit['canonical_groups']:,} canonical DOI/arXiv groups.
- Source: arXiv OAI-PMH CS/Math/Statistics. Metadata CC0-1.0; PDF licenses are separate.
- Metadata only. No PDF downloads or benchmark labels. OpenAlex is deferred by user decision.
- `catalog.sqlite`: metadata in `works`, full-text title/abstract search in FTS5 `search`.
- `works.parquet` and `works.jsonl.gz`: equivalent normalized records, fully round-trip checked.
- `audit.json`: counts, missing fields and checks. `dedup_report.json`: shared DOI/title collisions retained.
- `manifest.json`: SHA-256 for release files and compressed/raw source batches under the parent directory.

Example SQL:

```sql
SELECT w.paper_id, w.title FROM search s JOIN works w ON w.paper_id=s.paper_id
WHERE search MATCH 'attention' LIMIT 10;
```

This is a subset, not all arXiv. Modification-date harvesting does not filter publication year.
Exact PDF version is not pinned. Distinct arXiv IDs sharing a DOI remain separate records with one group ID.
Preserve this release; collect more metadata in the parent database and publish a new version.
'''
        (work / 'README.md').write_text(readme, encoding='utf-8')
        manifest = {'name': 'Catalog B V1', 'version': '1.0', 'created_at': now(), 'papers': len(rows), 'canonical_groups': audit['canonical_groups'], 'source': 'arxiv OAI-PMH', 'openalex_included': False, 'raw_files_relative_to': '..', 'raw_files': batch_files, 'files': {p.name: {'sha256': sha(p), 'bytes': p.stat().st_size} for p in work.iterdir() if p.is_file()}, 'limitations': ['Current OAI metadata, exact PDF version not pinned.', 'Subset of CS/Math/Statistics, not all arXiv.', 'Modified-date streams do not filter publication year.', 'No OpenAlex enrichment; metadata only, no PDFs.', 'PDF licenses separate from metadata CC0.']}
        (work / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        work.replace(destination)
        print(json.dumps(audit, indent=2))
    finally:
        lock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2] / 'data/catalog')
    parser.add_argument('--minimum', type=int, default=100000)
    parser.add_argument('--wait-for', type=int, help='Wait for this existing collector PID to exit before auditing; never restarts it')
    args = parser.parse_args()
    if args.wait_for:
        import psutil
        try:
            process = psutil.Process(args.wait_for)
            assert 'src.catalog.harvest' in process.cmdline(), 'PID is not the expected collector'
            started = process.create_time()
            print(f'Waiting for collector PID {args.wait_for}', flush=True)
            while process.is_running() and process.create_time() == started:
                time.sleep(20)
        except psutil.NoSuchProcess:
            pass
    publish(args.root, args.minimum)
