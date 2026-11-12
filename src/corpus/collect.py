"""Select metadata, resolve versions, and collect licensed PDFs resumably."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import time
import unicodedata
import xml.etree.ElementTree as ET

import pymupdf
import requests

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / 'data/corpus'
QUOTAS = {'ai_ml': 500, 'computer_vision': 300, 'nlp_llm': 300, 'information_retrieval': 200, 'math_stats': 450, 'systems_algorithms': 250}
PILOT = {'ai_ml': 25, 'computer_vision': 15, 'nlp_llm': 15, 'information_retrieval': 10, 'math_stats': 23, 'systems_algorithms': 12}
ATOM = '{http://www.w3.org/2005/Atom}'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # OneDrive scanners/readers can briefly hold the destination open on Windows.
    # Give each writer its own temp file, then retry the atomic replace on that lock.
    tmp = path.with_name(path.name + f'.tmp-{time.time_ns()}')
    try:
        tmp.write_text(value, encoding='utf-8')
        for attempt in range(8):
            try:
                tmp.replace(path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(min(0.1 * (2 ** attempt), 2.0))
    finally:
        tmp.unlink(missing_ok=True)


def topic(categories):
    for category, label in [('cs.IR', 'information_retrieval'), ('cs.CV', 'computer_vision'), ('cs.CL', 'nlp_llm')]:
        if category in categories:
            return label
    if any(c in categories for c in ('cs.AI', 'cs.LG', 'stat.ML')):
        return 'ai_ml'
    if any(c.startswith(('math.', 'stat.')) for c in categories):
        return 'math_stats'
    return 'systems_algorithms' if any(c.startswith('cs.') for c in categories) else None


def allowed_license(url):
    return bool(url and re.fullmatch(r'https?://creativecommons\.org/(?:licenses/(?:by|by-sa)/(?:3\.0|4\.0)/?|publicdomain/zero/1\.0/?)', url))


def id_year(identifier):
    match = re.match(r'(?:[a-z.-]+/)?(\d{2})\d{2}', identifier)
    if not match:
        raise ValueError('Unrecognized arXiv ID')
    year = int(match[1])
    return (1900 if year >= 91 else 2000) + year


def retryable_download_error(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (404, 410):
        return False
    return isinstance(exc, requests.RequestException)


def connect(root=ROOT):
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'corpus.sqlite', timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''CREATE TABLE IF NOT EXISTS papers(paper_id TEXT PRIMARY KEY,canonical_group_id TEXT UNIQUE,primary_topic TEXT,state TEXT,metadata_json TEXT,pdf_sha256 TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,paper_id TEXT,event TEXT,detail TEXT,at TEXT);
    CREATE INDEX IF NOT EXISTS papers_state ON papers(state);''')
    return db


def seed(db):
    catalog = PROJECT / 'data/catalog/v1/catalog.sqlite'
    source = sqlite3.connect(f'file:{catalog.as_posix()}?mode=ro', uri=True)
    pools = {label: [] for label in QUOTAS}
    catalog_sha = sha(PROJECT / 'data/catalog/v1/manifest.json')
    for payload, in source.execute('SELECT metadata_json FROM works'):
        record = json.loads(payload)
        label = topic(record['categories'])
        if label and allowed_license(record['pdf_license']):
            record['catalog_release_sha256'] = catalog_sha
            record['corpus_primary_topic'] = label
            record['id_year_hint'] = id_year(record['arxiv_id'])
            pools[label].append(record)
    source.close()
    inserted = Counter()
    seen_titles = set()
    for label, records in pools.items():
        old = sorted((r for r in records if r['id_year_hint'] < 2024), key=lambda r: hashlib.sha256(r['paper_id'].encode()).hexdigest())
        recent = sorted((r for r in records if r['id_year_hint'] >= 2024), key=lambda r: hashlib.sha256(r['paper_id'].encode()).hexdigest())
        mixed = [r for pair in __import__('itertools').zip_longest(recent, old) for r in pair if r]
        with db:
            for record in mixed:
                title = ' '.join(unicodedata.normalize('NFKC', record['title']).casefold().split())
                if title in seen_titles:
                    continue
                seen_titles.add(title)
                db.execute('INSERT OR IGNORE INTO papers VALUES(?,?,?,?,?,NULL)', (record['paper_id'], record['canonical_group_id'], label, 'candidate', json.dumps(record, ensure_ascii=False)))
                inserted[label] += 1
    print('Candidate pools:', dict(db.execute('SELECT primary_topic,count(*) FROM papers GROUP BY primary_topic')), flush=True)


class Network:
    def __init__(self, root):
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'DeepResearchCorpus/1.0 (local research; sequential, rate-limited)'
        self.last = 0
        self.root = root

    def get(self, url, **kwargs):
        for attempt in range(5):
            time.sleep(max(0, 3.2 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            try:
                response = self.session.get(url, timeout=(20, 90), **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt >= 4:
                    raise
                wait = 30 * (attempt + 1)
                print('Source connection backoff', type(exc).__name__, wait, flush=True)
                while wait > 0:
                    step = min(30, wait); time.sleep(step); wait -= step
                continue
            if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                try:
                    wait = max(30, int(response.headers.get('Retry-After', str(30 * (attempt + 1)))))
                except ValueError:
                    from email.utils import parsedate_to_datetime
                    try:
                        wait = max(30, (parsedate_to_datetime(response.headers['Retry-After']) - datetime.now(timezone.utc)).total_seconds())
                    except (ValueError, KeyError):
                        wait = 60
                print('Source backoff', response.status_code, wait, flush=True)
                response.close()
                while wait > 0:
                    step = min(30, wait); time.sleep(step); wait -= step
                continue
            response.raise_for_status()
            return response

    def resolve(self, records):
        ids = ','.join(r['arxiv_id'] for r in records)
        response = self.get('https://export.arxiv.org/api/query', params={'id_list': ids, 'max_results': len(records)})
        payload = response.content
        path = self.root / 'discovery' / (hashlib.sha256(payload).hexdigest() + '.atom.xml')
        atomic(path, payload.decode('utf-8'))
        found = {}
        for entry in ET.fromstring(payload).findall(ATOM + 'entry'):
            raw_id = entry.findtext(ATOM + 'id') or ''
            match = re.search(r'/abs/(.+?)(v\d+)$', raw_id)
            if not match:
                continue
            identifier, version = match.groups()
            published = entry.findtext(ATOM + 'published')
            assert published, 'Atom published date missing'
            found['arxiv:' + identifier] = {'version': version, 'versioned_id': identifier + version, 'published': published, 'updated': entry.findtext(ATOM + 'updated'), 'resolved_title': ' '.join((entry.findtext(ATOM + 'title') or '').split()), 'resolved_authors': [a.findtext(ATOM + 'name') for a in entry.findall(ATOM + 'author')], 'resolver_path': str(path.relative_to(PROJECT)), 'resolver_sha256': sha(path), 'resolved_at': now()}
        return found


def download(network, record):
    identifier = record['versioned_id']
    safe = hashlib.sha256(record['paper_id'].encode()).hexdigest()[:24]
    target = network.root / 'raw' / safe / record['version'] / 'paper.pdf'
    target.parent.mkdir(parents=True, exist_ok=True)
    url = 'https://arxiv.org/pdf/' + identifier
    if not target.exists():
        part = target.with_suffix('.part')
        offset = part.stat().st_size if part.exists() else 0
        response = network.get(url, headers={'Range': f'bytes={offset}-'} if offset else {}, stream=True)
        append = offset and response.status_code == 206
        if append:
            assert response.headers.get('Content-Range', '').startswith(f'bytes {offset}-')
        with response, part.open('ab' if append else 'wb') as output:
            for block in response.iter_content(1024 * 1024):
                output.write(block)
                if output.tell() > 50 * 1024**2:
                    raise ValueError('PDF exceeds 50 MiB candidate limit')
                if shutil.disk_usage(network.root).free < 30 * 2**30:
                    raise RuntimeError('Disk free guard')
        with pymupdf.open(part, filetype='pdf') as pdf:
            if pdf.needs_pass or not 1 <= len(pdf) <= 200:
                raise ValueError('Unsupported encrypted/page count PDF')
        part.replace(target)
    with pymupdf.open(target) as pdf:
        pages = len(pdf)
        first = pdf[0].get_text()
    stamp = re.search(r'arXiv:\s*(\d{4}\.\d{4,5}v\d+)', first)
    if stamp and stamp[1] != identifier:
        raise ValueError('PDF visible arXiv stamp does not match pinned version')
    return {**record, 'catalog_primary_topic': record.get('catalog_primary_topic', record['primary_topic']), 'primary_topic': record['corpus_primary_topic'], 'catalog_title': record['title'], 'catalog_publication_year': record['publication_year'], 'title': record['resolved_title'], 'publication_year': int(record['published'][:4]), 'safe_paper_id': safe, 'download_url': url, 'source_url': 'https://arxiv.org/abs/' + identifier, 'local_pdf_path': str(target.relative_to(PROJECT)), 'pdf_sha256': sha(target), 'pdf_bytes': target.stat().st_size, 'page_count': pages, 'fetched_at': now(), 'license': record['pdf_license'], 'license_provenance': 'catalog V1 OAI metadata; local use, no public redistribution performed', 'access_status': 'open_access_downloaded_metadata_license_checked', 'pdf_header_version_visible': identifier in re.sub(r'\s+', '', first), 'parse_status': 'pending', 'index_status': 'pending'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=[100, 500, 2000], default=100)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    import msvcrt
    lock = (ROOT / 'collect.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    db = connect()
    try:
        if not db.execute('SELECT count(*) FROM papers').fetchone()[0]:
            seed(db)
        quotas = PILOT if args.target == 100 else {k: int(v * args.target / 2000) for k, v in QUOTAS.items()}
        if args.target == 500:
            quotas['systems_algorithms'] += 1
        network = Network(ROOT)
        for label, quota in quotas.items():
            while db.execute("SELECT count(*) FROM papers WHERE primary_topic=? AND state IN ('downloaded','parsed','indexed')", (label,)).fetchone()[0] < quota:
                if shutil.disk_usage(ROOT).free < 30 * 2**30 or sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()) > 60 * 2**30 or sum(p.stat().st_size for p in (ROOT / 'raw').rglob('*') if p.is_file()) > 25 * 2**30:
                    raise RuntimeError('Corpus storage budget guard')
                candidates = db.execute("SELECT metadata_json FROM papers WHERE primary_topic=? AND state IN ('candidate','resolved') ORDER BY rowid LIMIT 20", (label,)).fetchall()
                if not candidates:
                    raise RuntimeError('No candidates left for ' + label)
                records = [json.loads(row[0]) for row in candidates]
                unresolved = [r for r in records if not r.get('versioned_id')]
                if unresolved:
                    found = network.resolve(unresolved)
                    with db:
                        for record in unresolved:
                            if record['paper_id'] not in found:
                                db.execute('UPDATE papers SET state=? WHERE paper_id=?', ('resolve_missing', record['paper_id']))
                                continue
                            record.update(found[record['paper_id']])
                            db.execute('UPDATE papers SET state=?,metadata_json=? WHERE paper_id=?', ('resolved', json.dumps(record, ensure_ascii=False), record['paper_id']))
                    records = [r for r in records if r.get('versioned_id')]
                for record in records:
                    try:
                        result = download(network, record)
                        with db:
                            db.execute('UPDATE papers SET state=?,metadata_json=?,pdf_sha256=? WHERE paper_id=?', ('downloaded', json.dumps(result, ensure_ascii=False), result['pdf_sha256'], record['paper_id']))
                            db.execute('INSERT INTO events(paper_id,event,detail,at) VALUES(?,?,?,?)', (record['paper_id'], 'downloaded', result['pdf_sha256'], now()))
                        print(record['paper_id'], label, result['page_count'], result['pdf_bytes'], flush=True)
                    except (requests.RequestException, ValueError, sqlite3.IntegrityError, pymupdf.FileDataError) as exc:
                        with db:
                            # Network interruption stays resumable; permanent invalid PDF is replaced.
                            state = 'resolved' if retryable_download_error(exc) else 'rejected_download'
                            db.execute('UPDATE papers SET state=? WHERE paper_id=?', (state, record['paper_id']))
                            db.execute('INSERT INTO events(paper_id,event,detail,at) VALUES(?,?,?,?)', (record['paper_id'], 'error', str(exc), now()))
                        print('ERROR', record['paper_id'], type(exc).__name__, flush=True)
                        if retryable_download_error(exc):
                            raise
                    count = db.execute("SELECT count(*) FROM papers WHERE primary_topic=? AND state IN ('downloaded','parsed','indexed')", (label,)).fetchone()[0]
                    counts = dict(db.execute("SELECT primary_topic,count(*) FROM papers WHERE state IN ('downloaded','parsed','indexed') GROUP BY primary_topic"))
                    atomic(ROOT / 'status.json', json.dumps({'updated_at': now(), 'stage': 'collecting', 'target': args.target, 'downloaded': sum(counts.values()), 'topic_counts': counts}, indent=2))
                    if count >= quota:
                        break
        manifest = [json.loads(row[0]) for row in db.execute("SELECT metadata_json FROM papers WHERE state IN ('downloaded','parsed','indexed') ORDER BY paper_id")]
        atomic(PROJECT / 'data/manifests' / f'corpus_{args.target}.jsonl', ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in manifest))
        print('DOWNLOAD STAGE COMPLETE', len(manifest), flush=True)
    except BaseException as exc:
        atomic(ROOT / 'status.json', json.dumps({'updated_at': now(), 'stage': 'stopped_with_error', 'target': args.target, 'error': type(exc).__name__}, indent=2))
        raise
    finally:
        db.close()
        lock.close()


if __name__ == '__main__':
    main()
