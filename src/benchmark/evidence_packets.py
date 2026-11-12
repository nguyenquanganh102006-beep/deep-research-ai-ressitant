"""Build provenance-preserving packets; verification requires an explicit receipt."""
from __future__ import annotations

import unicodedata
from collections import Counter
from pathlib import Path

import pymupdf

from config import PROJECT_ROOT
from src.benchmark.local_common import (DATA, CONFIG, file_hash, fingerprint, load_dev,
                                         read_rows, read_json, write_json)

TRACKS = ('gold_text_verified', 'retrieved_text_frozen', 'retrieved_vision')


def normalized(text: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', text).split())


def validate_dev(directory: Path = DATA) -> dict:
    cases, papers = load_dev(directory)
    errors, checked, mappings = [], {}, Counter()
    for q in cases:
        qid = q['question_id']
        if not q.get('reference_answer') or not q.get('expected_reasoning_checks'):
            errors.append({'id': qid, 'error': 'missing evaluator reference/rubric'})
        for pid in q['paper_ids']:
            if pid not in papers:
                errors.append({'id': qid, 'error': 'missing paper'})
                continue
            p = papers[pid]
            if pid not in checked:
                path = PROJECT_ROOT / p['pdf_path']
                try:
                    if file_hash(path) != p['pdf_sha256']:
                        raise ValueError('PDF hash mismatch')
                    with pymupdf.open(path) as pdf:
                        if pdf.is_encrypted or len(pdf) != p['page_count']:
                            raise ValueError('PDF encryption/page count mismatch')
                    checked[pid] = {'path': p['pdf_path'], 'sha256': p['pdf_sha256'], 'pages': p['page_count']}
                except Exception as exc:
                    errors.append({'id': qid, 'error': str(exc)})
        for e in q.get('evidence', []):
            try:
                p = papers[e['paper_id']]
                if e['pdf_sha256'] != p['pdf_sha256'] or not 1 <= e['page'] <= p['page_count']:
                    raise ValueError('Evidence PDF hash/page mismatch')
                sidecar = e.get('source_page_text_path')
                if sidecar:
                    path = PROJECT_ROOT / sidecar
                    if file_hash(path) != e['source_page_text_sha256']:
                        raise ValueError('Source page sidecar hash mismatch')
                    text = path.read_text(encoding='utf-8')
                    mapping = 'signed_sidecar'
                else:
                    with pymupdf.open(PROJECT_ROOT / p['pdf_path']) as pdf:
                        text = pdf[e['page'] - 1].get_text()
                    mapping = 'pdf_text'
                if normalized(e['quote']) not in normalized(text):
                    raise ValueError('Quote not found in page text')
                mappings[mapping] += 1
            except Exception as exc:
                errors.append({'id': qid, 'error': str(exc)})
    return {'passed': not errors, 'questions': len(cases), 'papers_checked': len(checked),
            'category_counts': dict(Counter(q['category'] for q in cases)),
            'evidence_mapping_counts': dict(mappings), 'errors': errors,
            'dev_sha256': file_hash(directory / 'dev.jsonl'),
            'papers_manifest_sha256': file_hash(directory / 'papers.jsonl'),
            'note': 'Quote/page integrity is not a mathematical or expert verification receipt.'}


def build_packets(track: str, question_ids=None, review_file: Path | None = None) -> list[dict]:
    if track not in TRACKS:
        raise ValueError('Unsupported track')
    if track == 'retrieved_vision':
        raise ValueError('Vision packets must be derived with add_vision from frozen text packets')
    cases, papers = load_dev()
    selected = set(question_ids) if question_ids else {q['question_id'] for q in cases}
    if selected - {q['question_id'] for q in cases}:
        raise ValueError('Unknown/non-dev question IDs')
    reviews = {r['question_id']: r for r in read_rows(review_file)} if review_file else {}
    packets, parsed = [], {}
    protocol = read_json(CONFIG / 'protocol_v1.json')
    for q in cases:
        if q['question_id'] not in selected:
            continue
        evidence = []
        if track == 'gold_text_verified':
            evidence = [{'paper_id': e['paper_id'], 'pdf_sha256': e['pdf_sha256'],
                         'page_start': e['page'], 'page_end': e['page'],
                         'section': e.get('section'), 'content': e['quote']}
                        for e in q.get('evidence', [])]
        else:
            # Production retrieval only. No question-anchor renderer or gold pages.
            from src.ingest import ingest_pdf_bytes
            from src.retriever import retrieve
            for pid in q['paper_ids']:
                if pid not in parsed:
                    source = PROJECT_ROOT / papers[pid]['pdf_path']
                    if file_hash(source) != papers[pid]['pdf_sha256']:
                        raise ValueError('PDF hash changed before ingestion')
                    parsed[pid], _ = ingest_pdf_bytes(source.read_bytes(), source.name)
                for chunk in retrieve(parsed[pid]['document_id'], q['question'],
                                      top_k=protocol['retrieval_top_k'],
                                      max_contexts=protocol['retrieval_top_k'], include_neighbors=False):
                    evidence.append({'paper_id': pid, 'pdf_sha256': papers[pid]['pdf_sha256'],
                                     'chunk_id': chunk['chunk_id'], 'page_start': chunk['page_start'],
                                     'page_end': chunk['page_end'], 'content': chunk['content'],
                                     'dense_score': chunk['dense_score'], 'bm25_score': chunk['bm25_score'],
                                     'rrf_score': chunk['rrf_score']})
        packet = {'schema_version': 1, 'track': track, 'split': 'dev', 'question_id': q['question_id'],
                  'question': q['question'], 'paper_ids': q['paper_ids'], 'category': q['category'],
                  'evidence': evidence, 'images': []}
        if track != 'gold_text_verified':
            packet['retrieval_provenance'] = {
                pid: {key: parsed[pid].get(key) for key in
                      ('document_id', 'parser_version', 'ingestion_fingerprint', 'embedding_model',
                       'embedding_fingerprint', 'embedding_dimensions')}
                for pid in q['paper_ids']}
        receipt = reviews.get(q['question_id'], {})
        packet['source_evidence_sha256'] = fingerprint({'evidence': evidence, 'images': []})
        if (track == 'gold_text_verified'
                and receipt.get('source_evidence_sha256') == packet['source_evidence_sha256']):
            for index, text in receipt.get('verified_text', {}).items():
                index = int(index)
                if not 0 <= index < len(evidence) or not isinstance(text, str) or not text.strip():
                    raise ValueError('Invalid verified text override')
                evidence[index]['content'] = text
        packet['evidence_sha256'] = fingerprint({'evidence': evidence, 'images': packet['images']})
        verified = (receipt.get('evidence_sha256') == packet['evidence_sha256']
                    and receipt.get('source_evidence_sha256') == packet['source_evidence_sha256']
                    and receipt.get('verified') is True and bool(receipt.get('reviewer'))
                    and bool(receipt.get('method')) and bool(receipt.get('reviewed_at'))
                    and bool(receipt.get('provenance')))
        packet['gold_evidence_status'] = ('verified_ai_or_human_receipt' if verified else 'unverified') if track == 'gold_text_verified' else 'not_applicable'
        packet['verification_receipt'] = receipt if verified else None
        packet['packet_sha256'] = fingerprint(packet)
        packets.append(packet)
    return packets


def add_vision(frozen_packets: list[dict]) -> list[dict]:
    from copy import deepcopy
    _, papers = load_dev()
    protocol = read_json(CONFIG / 'protocol_v1.json')
    packets = deepcopy(frozen_packets)
    for packet in packets:
        if fingerprint({k: v for k, v in packet.items() if k != 'packet_sha256'}) != packet['packet_sha256']:
            raise ValueError('Frozen text packet checksum mismatch')
        if packet['track'] != 'retrieved_text_frozen':
            raise ValueError('Vision requires frozen retrieval text input')
        packet['source_text_packet_sha256'] = packet['packet_sha256']
        packet['track'], packet['images'] = 'retrieved_vision', []
        for e in packet['evidence']:
            path = PROJECT_ROOT / papers[e['paper_id']]['pdf_path']
            if file_hash(path) != e['pdf_sha256']:
                raise ValueError('Source PDF checksum mismatch')
            for page in range(e['page_start'], e['page_end'] + 1):
                if (e['paper_id'], page) in {(i['paper_id'], i['page']) for i in packet['images']}:
                    continue
                with pymupdf.open(path) as pdf:
                    image = pdf[page - 1].get_pixmap(dpi=protocol['image_dpi'], alpha=False).tobytes('png')
                output = PROJECT_ROOT / 'data/benchmark/local_llm_packets/images' / (fingerprint([e['pdf_sha256'], page, protocol['image_dpi']]) + '.png')
                output.parent.mkdir(parents=True, exist_ok=True)
                if output.exists() and output.read_bytes() != image:
                    raise ValueError('Renderer output changed; use a new image policy/version')
                output.write_bytes(image)
                packet['images'].append({'paper_id': e['paper_id'], 'page': page,
                                         'path': str(output.relative_to(PROJECT_ROOT)), 'sha256': file_hash(output)})
                if len(packet['images']) == protocol['max_images']:
                    break
            if len(packet['images']) == protocol['max_images']:
                break
        packet['evidence_sha256'] = fingerprint({'evidence': packet['evidence'], 'images': packet['images']})
        packet.pop('packet_sha256')
        packet['packet_sha256'] = fingerprint(packet)
    return packets


def save_packets(packets: list[dict], path: Path) -> dict:
    if path.exists():
        old = read_rows(path)
        if old != packets:
            raise ValueError('Refusing to overwrite frozen packets; choose a new output path')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        from src.benchmark.local_common import canonical
        path.write_bytes(b''.join(canonical(p) + b'\n' for p in packets))
    manifest = {'schema_version': 1, 'packets': len(packets), 'sha256': file_hash(path),
                'question_ids': [p['question_id'] for p in packets],
                'track': packets[0]['track'] if packets else None,
                'gold_status_counts': dict(Counter(p['gold_evidence_status'] for p in packets))}
    write_json(path.with_suffix('.manifest.json'), manifest)
    return manifest
