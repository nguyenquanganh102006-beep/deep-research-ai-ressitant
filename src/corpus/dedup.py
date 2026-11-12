"""Text-duplicate candidates; never silently merges or deletes source papers."""
import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import re
import unicodedata

import numpy as np

from src.corpus.collect import PROJECT, ROOT, atomic, now, sha

STOP = set('the of and to in for an is are this that with on by we as at be from our can a'.split())


def normalize_body(text):
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'(?mi)^\s*arxiv:.*$', '', text)
    return re.sub(r'(?m)^\s*\d{1,4}\s*$', '', text)


def tokens(text):
    return re.findall(r'[a-z0-9_]{3,}', normalize_body(text).casefold())


@lru_cache(maxsize=200000)
def word_hash(token):
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), 'little')


def simhash(words):
    counts = Counter(w for w in words if w not in STOP)
    if not counts:
        return 0
    hashes = np.asarray([word_hash(w) for w in counts], dtype=np.uint64)
    weights = np.asarray([min(c, 3) for c in counts.values()], dtype=np.int64)
    bits = ((hashes[:, None] >> np.arange(64, dtype=np.uint64)) & 1).astype(np.int64)
    scores = ((bits * 2 - 1) * weights[:, None]).sum(axis=0)
    return sum(1 << bit for bit, value in enumerate(scores) if value >= 0)


def source_body(path):
    return '\n'.join(json.loads(line)['text'] for line in path.read_text(encoding='utf-8').split('\n') if line)


@lru_cache(maxsize=16)
def shingles(path):
    words = tokens(source_body(Path(path)))
    return {word_hash(' '.join(words[i:i + 5])) for i in range(max(0, len(words) - 4))}


def check(target, index=None):
    if index is None:
        pointer = json.loads((ROOT / 'index' / f'active_{target}.json').read_text(encoding='utf-8'))
        assert re.fullmatch(r'[a-zA-Z0-9_-]+', pointer['snapshot'])
        index = ROOT / 'index' / pointer['snapshot']
        assert sha(index / 'manifest.json') == pointer['manifest_sha256']
    manifest = json.loads((index / 'manifest.json').read_text(encoding='utf-8'))
    records = [json.loads(line) for line in (index / 'papers.jsonl').read_text(encoding='utf-8').split('\n') if line]
    assert len(records) == target
    buckets = defaultdict(list)
    exact = defaultdict(list)
    fingerprints = []
    pairs = set()
    for offset, record in enumerate(records):
        path = PROJECT / record['parsed_path'] / 'source_text.jsonl'
        quality = json.loads((path.parent / 'quality.json').read_text(encoding='utf-8'))
        digest = sha(path)
        assert digest == quality['files']['source_text.jsonl']
        cache = ROOT / 'dedup_cache' / (digest + '-v1.json')
        if cache.exists():
            fp = json.loads(cache.read_text(encoding='utf-8'))
        else:
            body = source_body(path)
            words = tokens(body)
            fp = {'source_text_sha256': digest, 'body_sha256': hashlib.sha256(''.join(normalize_body(body).split()).encode()).hexdigest(), 'tokens': len(words), 'simhash64': simhash(words)}
            atomic(cache, json.dumps(fp))
        exact[fp['body_sha256']].append(offset)
        fingerprints.append({**fp, 'path': str(path)})
        if fp['tokens'] < 80:
            continue
        for band in range(4):
            key = (band, (fp['simhash64'] >> (16 * band)) & 65535)
            for previous in buckets[key]:
                pairs.add((previous, offset))
            buckets[key].append(offset)
    candidates = []
    exact_pairs = {tuple(pair) for group in exact.values() if len(group) > 1 for pair in itertools.combinations(group, 2)}
    for left, right in sorted(pairs | exact_pairs):
        a, b = fingerprints[left], fingerprints[right]
        distance = (a['simhash64'] ^ b['simhash64']).bit_count()
        if (left, right) not in exact_pairs and (distance > 3 or min(a['tokens'], b['tokens']) / max(a['tokens'], b['tokens'], 1) < .85):
            continue
        one, two = shingles(a['path']), shingles(b['path'])
        overlap = len(one & two) / max(1, len(one | two))
        if (left, right) in exact_pairs or overlap >= .85:
            candidates.append({'paper_ids': [records[left]['paper_id'], records[right]['paper_id']], 'pdf_sha256': [records[left]['pdf_sha256'], records[right]['pdf_sha256']], 'same_normalized_text': (left, right) in exact_pairs, 'simhash_hamming': distance, 'shingle_jaccard': overlap, 'review_status': 'pending'})
    report = {'checked_at': now(), 'stage': manifest['version'], 'papers': target, 'exact_normalized_text_groups': [[records[i]['paper_id'] for i in group] for group in exact.values() if len(group) > 1], 'lsh_pairs_considered': len(pairs), 'review_candidates': candidates, 'unresolved_candidates': len(candidates), 'no_automatic_merge': True, 'method': 'Case-sensitive NFKC/whitespace exact body hash excluding arXiv stamp/page-number lines; weighted 64-bit SimHash four16-bit bands; Hamming<=3 then 5-token shingle Jaccard>=0.85. Candidate screen, not proof of semantic uniqueness.', 'program_sha256': sha(Path(__file__)), 'index_manifest_sha256': sha(index / 'manifest.json')}
    atomic(ROOT / 'reports' / ('dedup_' + manifest['version'] + '.json'), json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=int, choices=[100, 500, 2000], default=100)
    parser.add_argument('--index', type=Path)
    args = parser.parse_args()
    check(args.target, args.index)
