import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_track_c_subset import prepare
from src.benchmark.local_common import CONFIG, fingerprint


class TrackCPreparationTests(unittest.TestCase):
    def test_freezes_one_retrieved_image_and_matching_text_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / 'retrieved-page.png'
            image.write_bytes(b'fixture image bytes')
            image_hash = hashlib.sha256(image.read_bytes()).hexdigest()
            text_packets, vision_packets = [], []
            for qid, category in [('math-1', 'math'), ('negative-1', 'unanswerable')]:
                evidence = [{'paper_id': 'paper:1', 'page_start': 2, 'page_end': 2,
                             'content': 'Verified retrieved text'}]
                control = {'schema_version': 'fixture', 'split': 'dev',
                           'track': 'retrieved_text_frozen', 'question_id': qid,
                           'category': category, 'question': 'Question?', 'evidence': evidence,
                           'images': [], 'gold_evidence_status': None,
                           'source_text_packet_sha256': None,
                           'evidence_sha256': fingerprint({'evidence': evidence, 'images': []})}
                control['packet_sha256'] = fingerprint(control)
                text_packets.append(control)
                vision = {**control, 'track': 'retrieved_vision',
                          'images': [{'page': 2, 'paper_id': 'paper:1', 'path': str(image),
                                      'sha256': image_hash}],
                          'source_text_packet_sha256': control['packet_sha256']}
                vision['evidence_sha256'] = fingerprint({'evidence': evidence, 'images': vision['images']})
                vision.pop('packet_sha256')
                vision['packet_sha256'] = fingerprint(vision)
                vision_packets.append(vision)

            vision_path, text_path, protocol_path = root/'vision.jsonl', root/'text.jsonl', root/'protocol.json'
            vision_path.write_text(''.join(json.dumps(p) + '\n' for p in vision_packets), encoding='utf-8')
            text_path.write_text(''.join(json.dumps(p) + '\n' for p in text_packets), encoding='utf-8')
            protocol_path.write_text((CONFIG / 'protocol_v1.json').read_text(encoding='utf-8'), encoding='utf-8')
            out_vision, out_text, manifest_path = root/'out'/'vision.jsonl', root/'out'/'text.jsonl', root/'out'/'manifest.json'

            manifest = prepare(vision_path, text_path, out_vision, out_text, manifest_path, protocol_path)
            derived = [json.loads(line) for line in out_vision.read_text(encoding='utf-8').splitlines()]
            controls = [json.loads(line) for line in out_text.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(manifest['selected_count'], 1)
            self.assertEqual(manifest['selected_by_category'], {'math': 1})
            self.assertEqual(manifest['exclusions'], {'category_not_visually_scored': 1})
            self.assertEqual(derived[0]['question_id'], 'math-1')
            self.assertEqual(len(derived[0]['images']), 1)
            self.assertEqual(derived[0]['images'][0]['page'], 2)
            self.assertEqual(derived[0]['parent_vision_packet_sha256'], vision_packets[0]['packet_sha256'])
            self.assertEqual(derived[0]['evidence'], controls[0]['evidence'])
            self.assertEqual(controls[0], text_packets[0])
            self.assertEqual(fingerprint({k: v for k, v in derived[0].items()
                                          if k != 'packet_sha256'}), derived[0]['packet_sha256'])


if __name__ == '__main__':
    unittest.main()
