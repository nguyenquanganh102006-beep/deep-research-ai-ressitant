"""One CPU parser worker with page provenance and explicit fallback warnings."""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

import pymupdf
import psutil

from src.corpus.collect import PROJECT, ROOT, atomic, connect, now, sha
from src.chunker import create_chunks
from src.parser import parse_pdf
from config import PARSER_VERSION


def parser_id():
    sources = ['src/parser.py', 'src/chunker.py', 'src/representations.py', 'src/corpus/process.py']
    fingerprint = hashlib.sha256(''.join(sha(PROJECT / p) for p in sources).encode()).hexdigest()[:12]
    return 'md-' + fingerprint


def parse_one(record, fallback=False, elapsed_offset=0.0):
    started = time.perf_counter()
    pdf_path = PROJECT / record['local_pdf_path']
    assert pdf_path.resolve().is_relative_to((ROOT / 'raw').resolve())
    assert sha(pdf_path) == record['pdf_sha256']
    pid = parser_id()
    out = ROOT / 'parsed' / record['pdf_sha256'][:24] / pid
    if out.exists():
        quality = json.loads((out / 'quality.json').read_text(encoding='utf-8'))
        assert quality['pdf_sha256'] == record['pdf_sha256']
        assert all(sha(out / name) == value for name, value in quality['files'].items())
        return quality
    work = out.with_name(out.name + f'.tmp-{os.getpid()}')
    work.mkdir(parents=True, exist_ok=True)
    errors = []
    with pymupdf.open(pdf_path) as pdf:
        plain = [{'page_number': i + 1, 'text': page.get_text(sort=True)} for i, page in enumerate(pdf)]
        geometry = []
        signals = []
        for index, page in enumerate(pdf):
            text = plain[index]['text']
            math_symbols = sum(c in '∑∫∂∇≤≥≠∈∼αβγδεθλμσφψωΓΔΣΩ' for c in text)
            algorithm = bool(re.search(r'\bAlgorithm\s+\d|\bInput:|\bOutput:', text))
            signals.append({'page_number': index + 1, 'math_symbol_count': math_symbols, 'algorithm_heading': algorithm})
            for number, block in enumerate(page.get_text('blocks', sort=True), 1):
                geometry.append({'page_number': index + 1, 'block_number': number, 'bbox': list(block[:4]), 'text': block[4], 'source_block_type': block[6]})
    if not fallback:
        try:
            pages, markdown = parse_pdf(pdf_path, record['page_count'])
            backend = 'pymupdf4llm'
        except Exception as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc))
            fallback = True
    if fallback:
        backend = 'pymupdf_sorted_text_fallback'
        errors.append('Fallback retains page text; math/table/code layout is not verified.')
        pages = [{'page_number': row['page_number'], 'title': '', 'markdown': row['text'], 'parser_warning': ['Text fallback: reading order, equations, tables and indentation require review.']} for row in plain]
        markdown = '\n\n'.join(f'<!-- Page {p["page_number"]} -->\n\n{p["markdown"]}' for p in pages)
    assert len(pages) == len(plain) == record['page_count']
    chunks = create_chunks(pages)
    assert chunks, 'No extracted chunks'
    for chunk in chunks:
        assert 1 <= chunk['page_start'] <= chunk['page_end'] <= record['page_count']
        chunk.update({'paper_id': record['paper_id'], 'version': record['version'], 'pdf_sha256': record['pdf_sha256'], 'parser_version': pid, 'chunk_id': record['safe_paper_id'] + '-' + record['version'] + '-' + chunk['chunk_id']})
        chunk['text_sha256'] = hashlib.sha256(chunk['content'].encode('utf-8')).hexdigest()
    for name, rows in [('pages.jsonl', pages), ('source_text.jsonl', plain), ('blocks.jsonl', geometry), ('chunks.jsonl', chunks), ('page_signals.jsonl', signals)]:
        atomic(work / name, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    atomic(work / 'paper.md', markdown)
    empty = [row['page_number'] for row in plain if len(row['text'].strip()) < 30]
    dense_pages = [row['page_number'] for row in signals if row['math_symbol_count'] >= 12 or row['algorithm_heading']]
    warnings = sum(len(p.get('parser_warning', [])) for p in pages)
    memory = psutil.Process().memory_info()
    quality = {'paper_id': record['paper_id'], 'pdf_sha256': record['pdf_sha256'], 'parser_version': pid, 'production_parser_version': PARSER_VERSION, 'pymupdf_version': pymupdf.VersionBind, 'pymupdf4llm_version': importlib.metadata.version('pymupdf4llm'), 'backend': backend, 'page_count': len(pages), 'chunks': len(chunks), 'chunk_types': dict(Counter(c['type'] for c in chunks)), 'empty_or_low_text_pages': empty, 'warning_count': warnings, 'errors_or_fallback_reasons': errors, 'dense_candidate': len(dense_pages) >= max(1, len(pages) // 5), 'dense_page_candidates': dense_pages, 'density_method': 'heuristic >=12 math symbols or Algorithm/Input/Output heading; not visual gold', 'table_syntax_pages': [p['page_number'] for p in pages if re.search(r'\|.+\|', p['markdown'])], 'replacement_characters': sum(p['markdown'].count('\ufffd') for p in pages), 'elapsed_seconds': elapsed_offset + time.perf_counter() - started, 'peak_process_bytes': getattr(memory, 'peak_wset', memory.rss), 'parsed_at': now(), 'parsed_path': str(out.relative_to(PROJECT)), 'visual_review_status': 'pending', 'files': {p.name: sha(p) for p in work.iterdir() if p.is_file()}}
    atomic(work / 'quality.json', json.dumps(quality, ensure_ascii=False, indent=2))
    work.replace(out)
    return quality


def load_record(db, paper_id):
    row = db.execute('SELECT metadata_json FROM papers WHERE paper_id=?', (paper_id,)).fetchone()
    assert row, paper_id
    return json.loads(row[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--one')
    parser.add_argument('--wait-for', type=int)
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    db = connect()
    if args.one:
        record = load_record(db, args.one)
        db.close()
        quality = parse_one(record)
        atomic(ROOT / 'jobs' / (record['safe_paper_id'] + '.json'), json.dumps(quality, ensure_ascii=False))
        return
    import msvcrt
    lock = (ROOT / 'parse.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    waiting = psutil.Process(args.wait_for) if args.wait_for else None
    if waiting:
        assert 'src.corpus.collect' in waiting.cmdline()
    try:
        while True:
            ready = db.execute("SELECT count(*) FROM papers WHERE state IN ('parsed','indexed')").fetchone()[0]
            if ready >= args.limit:
                break
            row = db.execute("SELECT paper_id FROM papers WHERE state='downloaded' ORDER BY rowid LIMIT 1").fetchone()
            if not row:
                if waiting and waiting.is_running():
                    time.sleep(15)
                    continue
                break
            record = load_record(db, row[0])
            try:
                command = [sys.executable, '-m', 'src.corpus.process', '--one', row[0]]
                parse_attempt_started = time.perf_counter()
                try:
                    result = subprocess.run(command, cwd=PROJECT, capture_output=True, encoding='utf-8', errors='replace', timeout=300, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode:
                        raise RuntimeError(result.stderr[-1500:])
                    quality = json.loads((ROOT / 'jobs' / (record['safe_paper_id'] + '.json')).read_text(encoding='utf-8'))
                except subprocess.TimeoutExpired:
                    quality = parse_one(record, fallback=True, elapsed_offset=time.perf_counter() - parse_attempt_started)
                record.update({'parse_status': 'ready', 'parsed_path': quality['parsed_path'], 'parser_version': quality['parser_version'], 'parser_backend': quality['backend'], 'chunk_count': quality['chunks'], 'parse_quality_path': quality['parsed_path'] + '/quality.json'})
                with db:
                    db.execute('UPDATE papers SET state=?,metadata_json=? WHERE paper_id=?', ('parsed', json.dumps(record, ensure_ascii=False), row[0]))
                print(row[0], 'parsed', quality['page_count'], quality['chunks'], quality['backend'], flush=True)
            except Exception as exc:
                with db:
                    db.execute('UPDATE papers SET state=? WHERE paper_id=?', ('parse_failed', row[0]))
                    db.execute('INSERT INTO events(paper_id,event,detail,at) VALUES(?,?,?,?)', (row[0], 'parse_failed', str(exc), now()))
                print(row[0], 'PARSE FAILED', type(exc).__name__, flush=True)
        print('PARSE STAGE COMPLETE', db.execute("SELECT count(*) FROM papers WHERE state IN ('parsed','indexed')").fetchone()[0], flush=True)
    finally:
        db.close()
        lock.close()


if __name__ == '__main__':
    main()
