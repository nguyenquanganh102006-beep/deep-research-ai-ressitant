"""Freeze a one-image retrieved-page Track C subset and its text controls."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import PROJECT_ROOT
from src.benchmark.runner_local import messages_for
from src.benchmark.local_common import CONFIG, file_hash, fingerprint, read_json, read_rows


VISUAL_CATEGORIES = {'math', 'code', 'table'}
POLICY_ID = 'track_c_one_retrieved_image_v1'


def prepare(vision_path: Path, text_path: Path, output_vision: Path, output_text: Path,
            manifest_path: Path, protocol_path: Path):
    vision = read_rows(vision_path)
    text = read_rows(text_path)
    protocol = read_json(protocol_path)
    prompt_path = CONFIG / 'prompt_v1.txt'
    prompt = prompt_path.read_text(encoding='utf-8')
    if len({p['question_id'] for p in vision}) != len(vision):
        raise ValueError('Duplicate vision packet question_id')
    if len({p['question_id'] for p in text}) != len(text):
        raise ValueError('Duplicate text packet question_id')
    text_by_id = {p['question_id']: p for p in text}
    eligible, controls, exclusions = [], [], Counter()
    image_hashes = {}
    prompt_hashes = {}
    for packet in vision:
        qid = packet['question_id']
        if (fingerprint({k: v for k, v in packet.items() if k != 'packet_sha256'})
                != packet.get('packet_sha256')):
            raise ValueError(f'Vision packet checksum mismatch: {qid}')
        if packet.get('evidence_sha256') != fingerprint({'evidence': packet['evidence'],
                                                         'images': packet.get('images', [])}):
            raise ValueError(f'Vision evidence checksum mismatch: {qid}')
        control = text_by_id.get(qid)
        if control is None:
            raise ValueError(f'Missing paired text packet: {qid}')
        if (fingerprint({k: v for k, v in control.items() if k != 'packet_sha256'})
                != control.get('packet_sha256')):
            raise ValueError(f'Text control packet checksum mismatch: {qid}')
        if control.get('evidence_sha256') != fingerprint({'evidence': control['evidence'], 'images': []}):
            raise ValueError(f'Text control evidence checksum mismatch: {qid}')
        if (packet.get('source_text_packet_sha256') != control.get('packet_sha256')
                or packet['question'] != control['question'] or packet['evidence'] != control['evidence']):
            raise ValueError(f'Text/image pair is not identical apart from images: {qid}')
        vision_messages, _ = messages_for(packet, prompt, protocol)
        text_messages, _ = messages_for(control, prompt, protocol)
        if vision_messages != text_messages:
            raise ValueError(f'Vision and text control prompt differ: {qid}')
        if packet.get('track') != 'retrieved_vision' or control.get('track') != 'retrieved_text_frozen':
            raise ValueError(f'Unexpected track labels: {qid}')
        images = packet.get('images') or []
        if packet['category'] not in VISUAL_CATEGORIES:
            exclusions['category_not_visually_scored'] += 1
            continue
        if not images:
            exclusions['no_retrieved_image'] += 1
            continue
        image = images[0]
        image_path = Path(image['path'])
        if not image_path.is_absolute():
            image_path = PROJECT_ROOT / image_path
        if not image_path.is_file() or file_hash(image_path) != image['sha256']:
            raise ValueError(f'First retrieved image missing/hash mismatch: {qid}')
        evidence_pages = {page for e in packet['evidence']
                          for page in range(int(e['page_start']), int(e['page_end']) + 1)}
        if int(image['page']) not in evidence_pages:
            exclusions['first_image_not_in_retrieved_text_evidence'] += 1
            continue

        derived = dict(packet)
        derived['parent_vision_packet_sha256'] = packet['packet_sha256']
        derived['track_c_policy_id'] = POLICY_ID
        derived['images'] = [dict(image)]
        derived['evidence_sha256'] = fingerprint({'evidence': derived['evidence'], 'images': derived['images']})
        derived.pop('packet_sha256', None)
        derived['packet_sha256'] = fingerprint(derived)
        eligible.append(derived)
        controls.append(control)
        image_hashes[qid] = image['sha256']
        prompt_hashes[qid] = fingerprint(text_messages)

    if not eligible:
        raise ValueError('Track C selected no cases')
    ids = [p['question_id'] for p in eligible]
    if len(set(ids)) != len(ids):
        raise ValueError('Track C subset contains duplicate questions')
    for path in (output_vision, output_text, manifest_path):
        if path.exists():
            raise FileExistsError(path)
    output_vision.parent.mkdir(parents=True, exist_ok=True)
    output_text.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    vision_bytes = b''.join((json.dumps(p, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
                            for p in eligible)
    text_bytes = b''.join((json.dumps(p, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
                          for p in controls)
    output_vision.write_bytes(vision_bytes)
    output_text.write_bytes(text_bytes)
    manifest = {
        'schema_version': 'track_c_one_image_subset_v1',
        'policy_id': POLICY_ID,
        'selection_rule': 'Keep math/code/table dev questions only when the first image in frozen retrieval order is a hashed retrieved page and overlaps the page span of retrieved text evidence. Exclude unanswerable questions. Keep one first-ordered retrieved image per question; never add gold pages.',
        'visual_category_scope': sorted(VISUAL_CATEGORIES),
        'image_policy': {'max_images_per_request': 1, 'selection': 'first image in frozen retrieval order',
                         'dpi': 96, 'crop_policy': 'unchanged frozen page render'},
        'source_vision_packet': str(vision_path),
        'source_vision_packet_sha256': file_hash(vision_path),
        'source_text_packet': str(text_path),
        'source_text_packet_sha256': file_hash(text_path),
        'protocol_sha256': file_hash(protocol_path),
        'prompt_sha256': file_hash(prompt_path),
        'selected_count': len(eligible),
        'selected_by_category': dict(Counter(p['category'] for p in eligible)),
        'excluded_count': sum(exclusions.values()),
        'exclusions': dict(exclusions),
        'question_ids': ids,
        'image_sha256_by_question_id': image_hashes,
        'paired_prompt_sha256_by_question_id': prompt_hashes,
        'paired_text_is_identical': True,
        'vision_output': {'path': str(output_vision), 'sha256': hashlib.sha256(vision_bytes).hexdigest()},
        'text_control_output': {'path': str(output_text), 'sha256': hashlib.sha256(text_bytes).hexdigest()},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vision-packets', type=Path, required=True)
    parser.add_argument('--text-packets', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output-vision', type=Path, required=True)
    parser.add_argument('--output-text', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.vision_packets, args.text_packets, args.output_vision,
                             args.output_text, args.manifest, args.protocol), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
