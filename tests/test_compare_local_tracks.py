import json
import tempfile
import unittest
from pathlib import Path

from scripts.compare_local_tracks import compare
from src.benchmark.scoring_local import review_id


class PairedTrackComparisonTests(unittest.TestCase):
    def test_pairs_same_questions_and_counts_eligible_failure_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / 'run'
            run_root.mkdir()
            digest = {'model_digest': 'digest', 'quantization': 'Q4',
                      'thinking_mode': 'native', 'vision': False}
            manifest = {'baseline': 'fixture-commit', 'run_id': 'fixture-run',
                        'gold_sha256': 'gold-packet-hash', 'rag_sha256': 'rag-packet-hash',
                        'models': {'fixture:1b': digest}}
            raw_manifest = json.dumps(manifest, separators=(',', ':')) + '\n'
            (run_root / 'supervisor_manifest.json').write_text(raw_manifest, encoding='utf-8')
            all_rows = {'gold_full120': [], 'rag_full120': []}
            receipts = []
            for track_name, track in [('gold_full120', 'gold_text_verified'),
                                      ('rag_full120', 'retrieved_text_frozen')]:
                track_dir = run_root / track_name
                track_dir.mkdir()
                track_manifest = {'git_sha': 'fixture-commit',
                                  'packets_sha256': manifest['gold_sha256'] if track_name == 'gold_full120'
                                                    else manifest['rag_sha256'],
                                  'code_sha256': {'runner': 'code-hash'},
                                  'prompt_sha256': 'prompt-hash', 'protocol': {'seed': 42},
                                  'models': [{'model_tag': 'fixture:1b', **digest}]}
                (track_dir / 'manifest.json').write_text(json.dumps(track_manifest), encoding='utf-8')
                for i in range(120):
                    row = {'run_id': 'fixture-run', 'track': track, 'question_id': f'q-{i:03d}',
                           'model_digest': 'digest', 'model_tag': 'fixture:1b', 'quantization': 'Q4',
                           'category': 'math' if i < 40 else 'code' if i < 67 else 'table' if i < 98 else 'negative',
                           'answer': f'{track} answer {i}', 'evidence_sha256': f'{track}-{i}',
                           'status': 'completed', 'latency_seconds': 1.0}
                    if track_name == 'gold_full120' and i == 0:
                        row['status'] = 'runtime_error'
                    all_rows[track_name].append(row)
                    if row['status'] == 'completed':
                        receipts.append({'review_id': review_id(row),
                                         'correctness': 1.0 if track_name == 'gold_full120' else 0.5})
                (track_dir / 'predictions.jsonl').write_text(
                    ''.join(json.dumps(row) + '\n' for row in all_rows[track_name]), encoding='utf-8')
            reviews = root / 'effective_reviews.jsonl'
            reviews.write_text(''.join(json.dumps(r) + '\n' for r in receipts), encoding='utf-8')

            report = compare(run_root, reviews)
            model = report['models'][0]
            self.assertEqual(model['paired_question_ids'], 120)
            self.assertEqual(model['overall']['n'], 120)
            self.assertEqual(model['track_failures'], {'A': 1, 'B': 0})
            self.assertAlmostEqual(model['overall']['mean_track_a'], 119 / 120)
            self.assertEqual(model['overall']['mean_track_b'], 0.5)
            self.assertEqual(model['overall']['losses_b'], 119)
            self.assertEqual(model['overall']['wins_b'], 1)
            self.assertEqual(len(model['examples']['track_b_lower']), 5)


if __name__ == '__main__':
    unittest.main()
