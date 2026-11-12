"""Resumable arXiv OAI metadata collector. Never downloads PDFs."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

OAI = '{http://www.openarchives.org/OAI/2.0/}'
ARX = '{http://arxiv.org/OAI/arXiv/}'
ENDPOINT = 'https://oaipmh.arxiv.org/oai'


def now():
    return datetime.now(timezone.utc).isoformat()


def parse(payload):
    root = ET.fromstring(payload)
    error = root.find(OAI + 'error')
    if error is not None:
        if error.attrib.get('code') == 'noRecordsMatch':
            return [], None
        raise ValueError(f"OAI {error.attrib.get('code')}: {error.text}")
    records = []
    for record in root.findall('.//' + OAI + 'record'):
        header = record.find(OAI + 'header')
        if header.attrib.get('status') == 'deleted':
            continue
        item = record.find('./' + OAI + 'metadata/' + ARX + 'arXiv')
        if item is None:
            raise ValueError('Missing arXiv metadata')
        def field(name):
            return ' '.join((item.findtext(ARX + name) or '').split()) or None
        identifier = field('id')
        title, abstract = field('title'), field('abstract')
        if not identifier or not title or not abstract:
            raise ValueError('Missing ID/title/abstract')
        authors = [{name: author.findtext(ARX + name) for name in ('keyname', 'forenames', 'suffix', 'affiliation') if author.findtext(ARX + name)} for author in item.findall('./' + ARX + 'authors/' + ARX + 'author')]
        categories = (field('categories') or '').split()
        topic_category = next((c for c in categories if c.startswith(('cs.', 'math.', 'stat.'))), '')
        topic = 'mathematics' if topic_category.startswith('math.') else 'statistics' if topic_category.startswith('stat.') else 'computer_science' if topic_category.startswith('cs.') else 'other_crosslisted'
        records.append({'paper_id': 'arxiv:' + identifier, 'arxiv_id': identifier, 'doi': field('doi'), 'title': title, 'authors': authors, 'abstract': abstract, 'created': field('created'), 'updated': field('updated'), 'categories': categories, 'primary_topic': topic, 'source_provider': 'arxiv_oai', 'source_url': 'https://arxiv.org/abs/' + identifier, 'pdf_url': 'https://arxiv.org/pdf/' + identifier, 'pdf_license': field('license'), 'metadata_license': 'CC0-1.0', 'version': None, 'version_note': 'OAI arXiv format supplies current metadata; exact PDF version not pinned', 'oai_datestamp': header.findtext(OAI + 'datestamp'), 'fetched_at': now(), 'pdf_downloaded': False})
    return records, root.findtext('.//' + OAI + 'resumptionToken') or None


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS works(paper_id TEXT PRIMARY KEY, doi TEXT, title TEXT NOT NULL, primary_topic TEXT, created TEXT, metadata_json TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS works_doi ON works(doi);
    CREATE INDEX IF NOT EXISTS works_topic ON works(primary_topic);
    CREATE TABLE IF NOT EXISTS checkpoints(source_set TEXT PRIMARY KEY, token TEXT, done INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS batches(sha256 TEXT PRIMARY KEY, source_set TEXT, path TEXT, records INTEGER, fetched_at TEXT);
    ''')
    return db


def ingest(db, records, group, token, raw_path, sha):
    # Records and cursor commit together: crash/replay cannot skip a batch.
    with db:
        for item in records:
            db.execute('INSERT INTO works VALUES(?,?,?,?,?,?) ON CONFLICT(paper_id) DO UPDATE SET doi=excluded.doi,title=excluded.title,primary_topic=excluded.primary_topic,created=excluded.created,metadata_json=excluded.metadata_json', (item['paper_id'], item['doi'], item['title'], item['primary_topic'], item['created'], json.dumps(item, ensure_ascii=False)))
        db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)', (group, token, int(not token)))
        db.execute('INSERT OR IGNORE INTO batches VALUES(?,?,?,?,?)', (sha, group, raw_path, len(records), now()))


def status(db, directory, target, state, error=None):
    counts = dict(db.execute('SELECT primary_topic,count(*) FROM works GROUP BY primary_topic'))
    report = {'updated_at': now(), 'state': state, 'target': target, 'papers': sum(counts.values()), 'primary_topic_counts': counts, 'bytes_on_disk': sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()), 'free_bytes': shutil.disk_usage(directory).free, 'metadata_only': True, 'sources': ['arxiv_oai'], 'openalex': 'not harvested; no API key configured', 'error': error}
    temporary = directory / 'status.tmp'
    temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
    temporary.replace(directory / 'status.json')
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, default=100000)
    parser.add_argument('--max-batches', type=int)
    parser.add_argument('--modified-since', default='2026-01-01,2020-01-01', help='Comma-separated OAI modification dates, NOT publication dates; use all for full history')
    parser.add_argument('--root', type=Path, default=Path(os.getenv('DEEPRESEARCH_DATA_DIR', Path(__file__).resolve().parents[2] / 'data')) / 'catalog')
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    # Windows byte lock is released by the OS even if the process is interrupted.
    import msvcrt
    lock = (args.root / 'harvest.lock').open('a+b')
    lock.seek(0)
    if not lock.read(1):
        lock.write(b'0'); lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    db = connect(args.root / 'catalog.sqlite')
    session = requests.Session()
    session.headers['User-Agent'] = 'DeepResearchLocalCatalog/1.0 (metadata-only research harvester)'
    batches = 0
    try:
        while db.execute('SELECT count(*) FROM works').fetchone()[0] < args.target:
            progressed = False
            streams = [(group, since) for since in args.modified_since.split(',') for group in ('cs', 'math', 'stat')]
            for group, since in streams:
                stream = group if since == 'all' else group + '@' + since
                checkpoint = db.execute('SELECT token,done FROM checkpoints WHERE source_set=?', (stream,)).fetchone()
                if checkpoint and checkpoint[1]:
                    continue
                if shutil.disk_usage(args.root).free < 30 * 2**30 or sum(p.stat().st_size for p in args.root.rglob('*') if p.is_file()) > 5 * 2**30:
                    raise RuntimeError('Storage guard: 30 GiB free / 5 GiB catalog budget')
                token = checkpoint[0] if checkpoint else None
                params = {'verb': 'ListRecords', 'resumptionToken': token} if token else {'verb': 'ListRecords', 'metadataPrefix': 'arXiv', 'set': group}
                if not token and since != 'all':
                    params['from'] = since
                for attempt in range(6):
                    time.sleep(3.1)
                    try:
                        response = session.get(ENDPOINT, params=params, timeout=(20, 90))
                        if response.status_code in (429, 503):
                            delay = max(10, int(response.headers.get('Retry-After', '30')))
                            print(f'Backoff {response.status_code}: {delay}s', flush=True)
                            time.sleep(delay)
                        response.raise_for_status()
                        records, next_token = parse(response.content)
                        break
                    except (requests.RequestException, ValueError) as exc:
                        # Expired OAI cursor: replay this set from start, dedup by ID.
                        if 'badResumptionToken' in str(exc):
                            with db:
                                db.execute('DELETE FROM checkpoints WHERE source_set=?', (stream,))
                            records = None
                            break
                        status(db, args.root, args.target, 'retrying', type(exc).__name__)
                        if attempt == 5:
                            raise
                        time.sleep(min(30, 2**attempt))
                if records is None:
                    progressed = True
                    continue
                sha = hashlib.sha256(response.content).hexdigest()
                raw = args.root / 'raw' / stream / (sha + '.xml.gz')
                raw.parent.mkdir(parents=True, exist_ok=True)
                if not raw.exists():
                    temp = raw.with_suffix('.tmp')
                    temp.write_bytes(gzip.compress(response.content, mtime=0))
                    temp.replace(raw)
                ingest(db, records, stream, next_token, str(raw.relative_to(args.root)), sha)
                batches += 1
                progressed = True
                status(db, args.root, args.target, 'running')
                if db.execute('SELECT count(*) FROM works').fetchone()[0] >= args.target or args.max_batches and batches >= args.max_batches:
                    break
            if not progressed or args.max_batches and batches >= args.max_batches:
                break
        count = db.execute('SELECT count(*) FROM works').fetchone()[0]
        status(db, args.root, args.target, 'target_reached' if count >= args.target else 'batch_limit_or_source_exhausted')
    except BaseException as exc:
        status(db, args.root, args.target, 'stopped_with_error', type(exc).__name__)
        raise
    finally:
        db.close()
        lock.close()


if __name__ == '__main__':
    main()
