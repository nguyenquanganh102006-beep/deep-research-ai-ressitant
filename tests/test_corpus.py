import unittest
from src.corpus.collect import allowed_license, id_year, topic, PILOT, QUOTAS, retryable_download_error
from src.corpus.index import visual_required, quotas_for
import requests
import json
from pathlib import Path
import tempfile
from unittest import mock
import numpy as np


class CorpusTests(unittest.TestCase):
    def test_one_topic_and_quota(self):
        self.assertEqual(sum(PILOT.values()), 100)
        self.assertEqual(sum(QUOTAS.values()), 2000)
        self.assertEqual(topic(['cs.LG', 'cs.IR']), 'information_retrieval')
        self.assertEqual(topic(['cs.CL', 'cs.LG']), 'nlp_llm')
        self.assertEqual(topic(['hep-th', 'math.PR']), 'math_stats')
        self.assertIsNone(topic(['physics.gen-ph']))

    def test_explicit_license_and_year(self):
        self.assertTrue(allowed_license('http://creativecommons.org/licenses/by/4.0/'))
        self.assertFalse(allowed_license(None))
        self.assertFalse(allowed_license('http://creativecommons.org/licenses/by-nc-nd/4.0/'))
        self.assertFalse(allowed_license('http://arxiv.org/licenses/nonexclusive-distrib/1.0/'))
        self.assertEqual(id_year('0705.4348'), 2007)
        self.assertEqual(id_year('cs/9901001'), 1999)
        self.assertEqual(id_year('2601.12345'), 2026)

    def test_unavailable_pinned_pdf_is_replaced_not_infinite_retry(self):
        response = requests.Response()
        response.status_code = 404
        self.assertFalse(retryable_download_error(requests.HTTPError(response=response)))
        response.status_code = 503
        self.assertTrue(retryable_download_error(requests.HTTPError(response=response)))
        self.assertTrue(retryable_download_error(requests.ConnectionError()))
        self.assertFalse(retryable_download_error(ValueError('invalid PDF')))

    def test_network_retries_transient_disconnect(self):
        from src.corpus.collect import Network
        network = Network(Path('.'))
        response = requests.Response()
        response.status_code = 200
        with mock.patch.object(network.session, 'get', side_effect=[requests.ConnectionError('remote reset'), response]) as get, mock.patch('src.corpus.collect.time.sleep') as sleep:
            self.assertIs(network.get('https://example.test/resource'), response)
        self.assertEqual(get.call_count, 2)
        self.assertIn(mock.call(30), sleep.call_args_list)

    def test_visual_source_is_required_for_lossy_or_math_pages(self):
        chunk = {'page_start': 4, 'page_end': 4, 'type': 'text', 'parse_warning': [], 'content': 'Plain prose.'}
        quality = {'dense_page_candidates': [4]}
        self.assertTrue(visual_required(chunk, quality))
        self.assertFalse(visual_required(chunk, {'dense_page_candidates': [5]}))
        chunk['parse_warning'] = ['Replacement character']
        self.assertTrue(visual_required(chunk, {'dense_page_candidates': []}))
        chunk['type'] = 'text'
        chunk['parse_warning'] = []
        chunk['content'] = '|Resolution|Time|\n|---|---|\n|64|81 h|'
        self.assertTrue(visual_required(chunk, {'dense_page_candidates': []}))
        chunk['content'] = 'A variable x|x| is not a Markdown table.'
        self.assertFalse(visual_required(chunk, {'dense_page_candidates': []}))
        chunk['parse_warning'] = []
        chunk['type'] = 'code'
        self.assertTrue(visual_required(chunk, {'dense_page_candidates': []}))

    def test_all_stage_quotas_sum_exactly(self):
        for target in (100, 500, 2000):
            self.assertEqual(sum(quotas_for(target).values()), target)
        self.assertEqual(quotas_for(500)['math_stats'], 112)
        self.assertEqual(quotas_for(500)['systems_algorithms'], 63)

    def test_embedding_cache_reuses_content_and_rejects_corruption(self):
        from src.corpus.index import embed_cached
        chunks = [{'content': 'first context'}, {'content': 'second context'}]
        vectors = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch('src.corpus.index.ROOT', Path(directory)), mock.patch('src.embeddings.embed_passages', return_value=vectors) as encoder:
                first = embed_cached({'pdf_sha256': 'a' * 64}, chunks, {'fingerprint': 'fixture-model'})
                self.assertTrue(np.array_equal(first, vectors))
                second = embed_cached({'pdf_sha256': 'a' * 64}, chunks, {'fingerprint': 'fixture-model'})
                self.assertTrue(np.array_equal(second, vectors))
                self.assertEqual(encoder.call_count, 1)
                path = next(Path(directory).rglob('*.npy'))
                path.write_bytes(path.read_bytes() + b'corrupted')
                with self.assertRaises(AssertionError):
                    embed_cached({'pdf_sha256': 'a' * 64}, chunks, {'fingerprint': 'fixture-model'})

    def test_duplicate_text_candidates_are_not_automatically_merged(self):
        from src.corpus.dedup import check, normalize_body
        from src.corpus.collect import sha
        self.assertNotEqual(''.join(normalize_body('A = b').split()), ''.join(normalize_body('a = b').split()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / 'index'
            index.mkdir()
            (index / 'manifest.json').write_text(json.dumps({'version': 'fixture'}), encoding='utf-8')
            records = []
            body = ' '.join('scientificword' + str(i) for i in range(100))
            for number in (1, 2):
                parsed = root / ('parsed' + str(number))
                parsed.mkdir()
                source = parsed / 'source_text.jsonl'
                source.write_text(json.dumps({'text': f'arXiv:2501.0000{number}v1\n{body}\n{number}\n'}) + '\n', encoding='utf-8')
                (parsed / 'quality.json').write_text(json.dumps({'files': {'source_text.jsonl': sha(source)}}), encoding='utf-8')
                records.append({'paper_id': 'fixture:' + str(number), 'pdf_sha256': str(number) * 64, 'parsed_path': str(parsed)})
            papers = index / 'papers.jsonl'
            papers.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
            original = papers.read_bytes()
            with mock.patch('src.corpus.dedup.ROOT', root):
                report = check(2, index)
            self.assertEqual(len(report['exact_normalized_text_groups']), 1)
            self.assertEqual(report['unresolved_candidates'], 1)
            self.assertTrue(report['no_automatic_merge'])
            self.assertEqual(papers.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
