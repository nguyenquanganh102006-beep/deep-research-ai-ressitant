import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.consolidate_benchmark_reviews import build_effective_reviews, _normalize_citation_receipts


class ReviewConsolidationTests(unittest.TestCase):
    def test_line_bound_overlay_replaces_without_mutating_raw_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queues = {
                'math': ('queue_math.jsonl', 'reviews_math_luna_v3.jsonl'),
                'code': ('queue_code.jsonl', 'reviews_code_luna_v3.jsonl'),
                'table_negative': ('queue_table_negative.jsonl', 'reviews_table_negative_luna_v2.jsonl'),
            }
            receipts = {}
            queue_rows = {}
            for category, (queue_name, review_name) in queues.items():
                rid = f'{category}-review'
                qrow = {'review_id': rid, 'question_id': f'{category}-001',
                        'input_sha256': f'{category}-input'}
                receipt = {'review_id': rid, 'correctness': 1, 'reviewer': 'fixture',
                           'provenance': 'raw fixture'}
                queue_bytes = (json.dumps(qrow, separators=(',', ':')) + '\n').encode()
                review_bytes = (json.dumps(receipt, separators=(',', ':')) + '\n').encode()
                (root / queue_name).write_bytes(queue_bytes)
                (root / review_name).write_bytes(review_bytes)
                queue_rows[rid] = qrow
                receipts[rid] = receipt

            source_file = queues['math'][1]
            raw_line = (root / source_file).read_bytes()
            replacement = {**receipts['math-review'], 'correctness': 0.5,
                           'reviewer': 'correction fixture', 'provenance': 'overlay fixture'}
            correction = {
                'correction_id': 'math-fixture-overlay',
                'correction_type': 'replacement_receipt_for_invalidated_source_id',
                'source_file': source_file,
                'source_line_number': 1,
                'source_line_sha256_including_line_ending': hashlib.sha256(raw_line).hexdigest(),
                'source_review_id': 'math-review',
                'source_receipt_invalidated': True,
                'replacement_review_id': 'math-review',
                'replacement_question_id': 'math-001',
                'replacement_queue_input_sha256': 'math-input',
                'replacement_receipt': replacement,
            }
            (root / 'receipt_corrections_v1.jsonl').write_text(
                json.dumps(correction, separators=(',', ':')) + '\n', encoding='utf-8')

            effective, manifest = build_effective_reviews(root)
            by_id = {row['review_id']: row for row in effective}
            self.assertEqual(len(effective), 3)
            self.assertEqual(by_id['math-review']['correctness'], 0.5)
            self.assertEqual(by_id['math-review']['_overlay_provenance']['correction_ids'],
                             ['math-fixture-overlay'])
            self.assertEqual(receipts['math-review']['correctness'], 1)
            self.assertEqual(manifest['correction_rows_targeting_base_reviews'], 1)

    def test_citation_receipt_policy_keeps_presence_separate_from_support(self):
        cases = {
            'no-page-citation': ({'model_answer': 'A claim without page citation.', 'allowed_pages': [2]},
                                 {'citation_supported': False, 'claims': [{'cited_pages': [2]}]}, None, []),
            'placeholder': ({'model_answer': 'Claim [Trang N].', 'allowed_pages': [2]},
                            {'citation_supported': None, 'claims': []}, False, []),
            'invalid-page': ({'model_answer': 'Claim [Page 9].', 'allowed_pages': [2]},
                             {'citation_supported': True, 'claims': []}, False, []),
            'valid-page': ({'model_answer': 'Claim [Trang 2-2].', 'allowed_pages': [2]},
                           {'citation_supported': True, 'claims': [{'cited_pages': [2]}]}, True, [2]),
        }
        effective = {}
        queue = {}
        for rid, (qrow, receipt, expected_support, expected_claim_pages) in cases.items():
            effective[rid] = receipt
            queue[rid] = qrow
        counts = _normalize_citation_receipts(effective, queue)
        self.assertEqual(effective['no-page-citation']['citation_supported'], None)
        self.assertEqual(effective['no-page-citation']['claims'][0]['cited_pages'], [])
        self.assertEqual(effective['placeholder']['citation_supported'], False)
        self.assertEqual(effective['invalid-page']['citation_supported'], False)
        self.assertEqual(effective['valid-page']['citation_supported'], True)
        self.assertEqual(effective['valid-page']['claims'][0]['cited_pages'], [2])
        self.assertEqual(counts['receipts_normalized'], 3)


if __name__ == '__main__':
    unittest.main()
