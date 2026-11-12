"""Regression checks for benchmark scoring and evidence eligibility."""
import unittest

from src.benchmark.run_qasper import metrics
from src.benchmark.generate_qasper import token_f1, paragraph_f1
from src.benchmark.audit_curated import assigned_split, group_id


class RetrievalMetricsTests(unittest.TestCase):
    def test_rank_and_recall_are_distinct(self):
        result = metrics(['wrong', 'gold1', 'gold2'], {'gold1', 'gold2'}, 2)
        self.assertEqual(result['hit'], 1)
        self.assertEqual(result['recall'], .5)
        self.assertEqual(result['mrr'], .5)
        self.assertLess(result['ndcg'], 1)

    def test_relevant_below_cutoff_is_miss(self):
        result = metrics(['wrong', 'gold'], {'gold'}, 1)
        self.assertEqual(result, {'hit': 0.0, 'recall': 0.0, 'mrr': 0.0, 'ndcg': 0.0})

    def test_perfect_ranking(self):
        result = metrics(['a', 'b', 'wrong'], {'a', 'b'}, 5)
        self.assertTrue(all(value == 1 for value in result.values()))


class AnswerScoringTests(unittest.TestCase):
    def test_normalization_matches_qasper_convention(self):
        self.assertEqual(token_f1('The, Adam optimizer!', 'Adam optimizer'), 1)
        self.assertEqual(token_f1('No', 'Yes'), 0)
        self.assertEqual(token_f1('', ''), 0)

    def test_multiple_evidence_and_abstention(self):
        self.assertEqual(paragraph_f1([], []), 1)
        self.assertEqual(paragraph_f1(['a'], []), 0)
        self.assertAlmostEqual(paragraph_f1(['a', 'b'], ['a']), 2 / 3)


class PaperSplitTests(unittest.TestCase):
    def test_versions_share_split(self):
        self.assertEqual(group_id('arxiv:1706.03762v7'), 'arxiv:1706.03762')
        self.assertEqual(assigned_split('arxiv:1706.03762v1', {}), assigned_split('arxiv:1706.03762v7', {}))

    def test_public_split_overrides_hash_and_legacy_cannot_be_test(self):
        self.assertEqual(assigned_split('arxiv:1234.56789v2', {'arxiv:1234.56789': 'train'}), 'train')
        self.assertEqual(assigned_split('arxiv:1412.6980v9', {}), 'dev')
        self.assertEqual(assigned_split('arxiv:2205.14135v2', {}), 'dev')


if __name__ == '__main__':
    unittest.main()
