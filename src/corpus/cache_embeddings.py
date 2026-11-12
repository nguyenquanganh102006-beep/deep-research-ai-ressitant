"""Fill resumable per-paper CPU vectors while a single parser is running."""
import argparse
import hashlib
import json
import os
import sqlite3
import time

import psutil

from src.corpus.collect import ROOT, PROJECT, atomic, now, sha
from src.corpus.index import model_info, embed_cached


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=[500, 2000], required=True)
    parser.add_argument('--wait-for', type=int, required=True)
    parser.add_argument('--threads', type=int, default=4)
    args = parser.parse_args()
    import msvcrt
    lock = (ROOT / 'index.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    db = sqlite3.connect(ROOT / 'corpus.sqlite', timeout=30)
    coordinator = psutil.Process(args.wait_for)
    assert 'src.corpus.process' in coordinator.cmdline() and '--one' not in coordinator.cmdline()
    completed = set()
    hits = 0
    new = 0
    started = time.perf_counter()
    try:
        info = model_info()
        import torch
        torch.set_num_threads(max(1, args.threads))
        log_path = ROOT / 'reports' / f'cache{args.target}-{os.getpid()}.jsonl'
        while len(completed) < args.target:
            pending = [(pid, payload) for pid, payload in db.execute("SELECT paper_id,metadata_json FROM papers WHERE state IN ('parsed','indexed') ORDER BY paper_id") if pid not in completed]
            if not pending:
                if coordinator.is_running():
                    time.sleep(15)
                    continue
                break
            for pid, payload in pending:
                record = json.loads(payload)
                directory = PROJECT / record['parsed_path']
                quality = json.loads((directory / 'quality.json').read_text(encoding='utf-8'))
                assert sha(directory / 'chunks.jsonl') == quality['files']['chunks.jsonl']
                chunks = [json.loads(line) for line in (directory / 'chunks.jsonl').read_text(encoding='utf-8').split('\n') if line]
                text_hash = hashlib.sha256(json.dumps([c['content'] for c in chunks], ensure_ascii=False).encode()).hexdigest()
                cache = ROOT / 'embeddings' / record['pdf_sha256'][:24] / info['fingerprint'][:16] / (text_hash + '.npy')
                reused = cache.exists() and cache.with_suffix('.json').exists()
                before = time.perf_counter()
                vectors = embed_cached(record, chunks, info)
                del vectors
                completed.add(pid)
                hits += int(reused)
                new += int(not reused)
                event = {'paper_id': pid, 'pdf_sha256': record['pdf_sha256'], 'cache_hit': reused, 'seconds': time.perf_counter() - before, 'chunks': len(chunks), 'model_fingerprint': info['fingerprint'], 'threads': torch.get_num_threads(), 'completed': len(completed), 'at': now()}
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(event) + '\n')
                memory = psutil.Process().memory_info()
                report = {'stage': 'caching_embeddings', 'target': args.target, 'pid': os.getpid(), 'parser_pid': args.wait_for, 'completed_papers': len(completed), 'cache_hits': hits, 'newly_encoded_papers': new, 'model_fingerprint': info['fingerprint'], 'threads': torch.get_num_threads(), 'peak_process_bytes': getattr(memory, 'peak_wset', memory.rss), 'elapsed_seconds': time.perf_counter() - started, 'updated_at': now()}
                atomic(ROOT / 'reports' / f'cache_progress_{args.target}.json', json.dumps(report, indent=2))
                print('CACHED', pid, len(completed), '/', args.target, 'hit' if reused else 'new', flush=True)
                if len(completed) >= args.target:
                    break
        assert len(completed) >= args.target, f'Parser ended before target: {len(completed)} / {args.target}'
        print('CACHE STAGE COMPLETE', len(completed), flush=True)
    finally:
        db.close()
        lock.close()


if __name__ == '__main__':
    main()
