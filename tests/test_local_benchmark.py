import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src.benchmark.local_common import CONFIG, fingerprint, read_json, read_rows, canonical
from src.benchmark.local_llm_adapter import OllamaAdapter, ModelError
from src.benchmark.runner_local import run, messages_for
from src.benchmark.scoring_local import summarize, review_id, citation_metrics

PROTOCOL = read_json(CONFIG / 'protocol_v1.json')


def packet(qid='q1', verified=True):
    evidence = [{'paper_id': 'paper', 'pdf_sha256': 'a' * 64, 'page_start': 1,
                 'page_end': 1, 'content': 'Source fact only.'}]
    h = fingerprint({'evidence': evidence, 'images': []})
    p = {'track': 'gold_text_verified', 'split': 'dev', 'question_id': qid,
         'paper_ids': ['paper'], 'category': 'math', 'question': 'What is the fact?',
         'evidence': evidence, 'images': [], 'evidence_sha256': h,
         'source_evidence_sha256': h,
         'gold_evidence_status': 'verified_ai_or_human_receipt' if verified else 'unverified',
         'verification_receipt': {'verified': True, 'evidence_sha256': h, 'source_evidence_sha256': h,
                                  'reviewer': 'test', 'provenance': 'unit fixture',
                                  'method': 'test fixture', 'reviewed_at': 'test'} if verified else None}
    p['packet_sha256'] = fingerprint(p)
    return p


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.fail_once = False
        self.changed = False

    def inspect(self, tag):
        return {'model_tag': tag, 'model_digest': fingerprint(tag + str(self.changed)),
                'quantization': 'test', 'thinking_mode': 'native', 'vision': False}

    def running(self): return []
    def unload(self, tag): pass

    def chat(self, model, messages, protocol, images=None):
        self.calls.append(copy.deepcopy(messages))
        if self.fail_once and messages[-1]['content'].startswith('QUESTION'):
            self.fail_once = False
            raise ModelError('oom', 'fixture OOM')
        return {'answer': 'Fact [Trang 1]', 'latency_seconds': 0.1, 'prompt_eval_count': 30,
                'eval_count': 5, 'eval_duration': 1000000}


class LocalBenchmarkTests(unittest.TestCase):
    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={})
    def test_successful_transport_retry_keeps_error_log(self, _):
        class TransientAdapter(FakeAdapter):
            transient = True

            def chat(self, model, messages, protocol, images=None):
                if self.transient and messages[-1]['content'].startswith('QUESTION'):
                    self.transient = False
                    raise ModelError('endpoint_error', 'transient fixture disconnect')
                return super().chat(model, messages, protocol, images)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_bytes(canonical(packet()) + b'\n')
            directory = Path(tmp) / 'run'
            rows = run(path, ['model'], directory, adapter=TransientAdapter())
            self.assertEqual(rows[0]['status'], 'completed')
            self.assertEqual(rows[0]['transport_retries'], 1)
            self.assertEqual(len(read_rows(directory / 'retry_errors.jsonl')), 1)
            self.assertGreaterEqual(rows[0]['case_wall_seconds'], 1)

    def test_remote_endpoint_is_not_a_local_benchmark(self):
        with self.assertRaises(ValueError):
            OllamaAdapter(host='https://example.com')

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={'ram_available_bytes': 0})
    def test_resource_budget_prevents_model_load(self, _):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_bytes(canonical(packet()) + b'\n')
            result = run(path, ['model'], Path(tmp) / 'run', adapter=adapter)
            self.assertEqual(result[0]['status'], 'resource_ineligible')
            self.assertEqual(adapter.calls, [])

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={})
    def test_120_case_checkpoint_and_resume_without_network(self, _):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'packets.jsonl'
            source.write_bytes(b''.join(canonical(packet(f'q{i}')) + b'\n' for i in range(120)))
            output = Path(tmp) / 'run'
            result = run(source, ['model'], output, adapter=adapter)
            self.assertEqual(len(result), 120)
            self.assertTrue(all(row['status'] == 'completed' for row in result))
            calls = len(adapter.calls)
            self.assertEqual(run(source, ['model'], output, adapter=adapter, resume=True), [])
            self.assertEqual(len(adapter.calls), calls)
            self.assertEqual(len(read_rows(output / 'predictions.jsonl')), 120)

    def test_verified_flag_without_receipt_is_rejected(self):
        source = packet()
        source['verification_receipt'] = None
        source.pop('packet_sha256')
        source['packet_sha256'] = fingerprint(source)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_bytes(canonical(source) + b'\n')
            adapter = FakeAdapter()
            with self.assertRaises(ValueError):
                run(path, ['model'], Path(tmp) / 'run', adapter=adapter)
            self.assertEqual(adapter.calls, [])

    def test_native_thinking_and_context_metadata(self):
        adapter = OllamaAdapter(session=Mock())
        info = {'capabilities': ['completion', 'thinking'],
                'thinking': {'values': ['low', 'high']}, 'details': {},
                'model_info': {'model.context_length': 2048}}
        with patch.object(adapter, 'installed', return_value=[{'name': 'model', 'digest': 'digest'}]), patch.object(adapter, 'request', return_value=info):
            model = adapter.inspect('model')
            self.assertEqual(model['thinking_mode'], 'native')
            with self.assertRaises(ModelError) as ctx:
                adapter.chat(model, [{'role': 'user', 'content': 'test'}], PROTOCOL)
            self.assertEqual(ctx.exception.status, 'context_ineligible')

    def test_vision_uses_only_frozen_retrieval_pages(self):
        import pymupdf
        from src.benchmark.evidence_packets import add_vision
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = pymupdf.open()
            for page in range(2):
                pdf.new_page().insert_text((50, 50), f'Page {page + 1}')
            path = root / 'source.pdf'
            pdf.save(path)
            pdf.close()
            from src.benchmark.local_common import file_hash
            source = packet()
            source['track'] = 'retrieved_text_frozen'
            source['evidence'][0]['pdf_sha256'] = file_hash(path)
            source['evidence_sha256'] = fingerprint({'evidence': source['evidence'], 'images': []})
            source.pop('packet_sha256')
            source['packet_sha256'] = fingerprint(source)
            papers = {'paper': {'pdf_path': 'source.pdf'}}
            with patch('src.benchmark.evidence_packets.PROJECT_ROOT', root), patch('src.benchmark.evidence_packets.load_dev', return_value=([], papers)):
                visual = add_vision([source])[0]
            self.assertEqual([i['page'] for i in visual['images']], [1])
            self.assertEqual(visual['evidence'], source['evidence'])
            self.assertEqual(visual['source_text_packet_sha256'], source['packet_sha256'])
            self.assertEqual(source['images'], [])

    def test_scoring_appends_new_review_cases_without_overwriting(self):
        from src.benchmark.scoring_local import score_run
        from src.benchmark.local_common import append_jsonl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = [{'question_id': q, 'category': 'math', 'question': 'question',
                       'reference_answer': 'reference', 'expected_reasoning_checks': ['rubric']} for q in ['q1', 'q2']]
            row = {'run_id': 'run', 'track': 'gold_text_verified', 'model_tag': 'model',
                   'model_digest': 'digest', 'question_id': 'q1', 'category': 'math',
                   'answer': 'answer', 'status': 'completed', 'latency_seconds': 1}
            append_jsonl(root / 'predictions.jsonl', row)
            with patch('src.benchmark.scoring_local.load_dev', return_value=(labels, {})):
                score_run(root)
                old = read_rows(root / 'review_template.jsonl')[0]
                old['reviewer'] = 'preserve this edit'
                (root / 'review_template.jsonl').write_bytes(canonical(old) + b'\n')
                append_jsonl(root / 'predictions.jsonl', {**row, 'question_id': 'q2'})
                score_run(root)
            actual = read_rows(root / 'review_template.jsonl')
            self.assertEqual(len(actual), 2)
            self.assertEqual(actual[0]['reviewer'], 'preserve this edit')

    def test_registry_and_screen_are_balanced(self):
        models = read_json(CONFIG / 'models.json')['models']
        self.assertEqual(len(models), 32)
        self.assertEqual(len({m['tag'] for m in models}), 32)
        self.assertEqual(sum(m['stage'] == 'A' for m in models), 23)
        self.assertEqual(len(read_json(CONFIG / 'dev_screen12.json')['question_ids']), 12)

    def test_prompt_whitelist_and_common_context_guard(self):
        p = packet()
        p.update(reference_answer='SECRET_REFERENCE', expected_reasoning_checks=['SECRET_RUBRIC'])
        messages, pages = messages_for(p, 'system', PROTOCOL)
        text = json.dumps(messages)
        self.assertNotIn('SECRET', text)
        self.assertEqual(pages, [1])
        p['evidence'][0]['content'] = 'x' * 4000
        with self.assertRaises(ModelError) as ctx:
            messages_for(p, 'system', PROTOCOL)
        self.assertEqual(ctx.exception.status, 'context_ineligible')

    def test_adapter_errors_and_thinking_policy(self):
        session = Mock()
        response = session.request.return_value
        response.status_code = 200
        response.json.return_value = {'message': {'content': 'answer'}}
        adapter = OllamaAdapter(session=session)
        model = {'model_tag': 'test', 'model_digest': 'digest', 'vision': False,
                 'thinking_mode': 'native'}
        with patch.object(adapter, 'inspect', return_value=model):
            adapter.chat(model, [{'role': 'user', 'content': 'test'}], PROTOCOL)
            self.assertNotIn('think', session.request.call_args.kwargs['json'])
            model['thinking_mode'] = 'off_supported'
            adapter.chat(model, [{'role': 'user', 'content': 'test'}], PROTOCOL)
            self.assertIs(session.request.call_args.kwargs['json']['think'], False)
            with self.assertRaises(ModelError) as ctx:
                adapter.chat(model, [], PROTOCOL, [{'absolute_path': 'absent'}])
            self.assertEqual(ctx.exception.status, 'not_applicable')
            response.json.return_value = {'message': {'content': ''}}
            with self.assertRaises(ModelError) as ctx:
                adapter.chat(model, [{'role': 'user', 'content': 'test'}], PROTOCOL)
            self.assertEqual(ctx.exception.status, 'empty_output')
        for status_code, detail, expected in [(404, 'not found', 'model_not_found'),
                                              (500, 'out of memory', 'oom'),
                                              (400, 'unsupported think', 'unsupported_protocol')]:
            response.status_code, response.text = status_code, detail
            with self.assertRaises(ModelError) as ctx:
                adapter.request('GET', '/test')
            self.assertEqual(ctx.exception.status, expected)
        session.request.side_effect = requests.Timeout('timeout')
        with self.assertRaises(ModelError) as ctx:
            adapter.request('GET', '/test')
        self.assertEqual(ctx.exception.status, 'timeout')

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={})
    def test_two_models_same_input_resume_and_digest_lock(self, _):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_bytes(b''.join(canonical(packet(q)) + b'\n' for q in ['q1', 'q2']))
            output = Path(tmp) / 'run'
            first = run(path, ['a', 'b'], output, adapter=adapter)
            self.assertEqual(len(first), 4)
            self.assertEqual(first[0]['input_sha256'], first[2]['input_sha256'])
            count = len(adapter.calls)
            self.assertEqual(run(path, ['a', 'b'], output, adapter=adapter, resume=True), [])
            self.assertEqual(len(adapter.calls), count)
            self.assertEqual(len(read_rows(output / 'predictions.jsonl')), 4)
            adapter.changed = True
            with self.assertRaises(ValueError):
                run(path, ['a', 'b'], output, adapter=adapter, resume=True)

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={})
    def test_unverified_evidence_never_calls_model(self, _):
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_bytes(canonical(packet(verified=False)) + b'\n')
            result = run(path, ['a'], Path(tmp) / 'run', adapter=adapter)
            self.assertEqual(result[0]['status'], 'evidence_unverified')
            self.assertEqual(adapter.calls, [])

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={})
    def test_retry_only_failed_case_and_preserve_attempt_history(self, _):
        adapter = FakeAdapter()
        adapter.fail_once = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.jsonl'
            path.write_bytes(b''.join(canonical(packet(q)) + b'\n' for q in ['q1', 'q2']))
            output = Path(tmp) / 'run'
            rows = run(path, ['a'], output, adapter=adapter)
            self.assertEqual([r['status'] for r in rows], ['oom', 'completed'])
            retry = run(path, ['a'], output, adapter=adapter, resume=True, retry_failed=True)
            self.assertEqual(len(retry), 1)
            self.assertEqual(retry[0]['question_id'], 'q1')
            self.assertEqual(retry[0]['status'], 'completed')
            self.assertEqual(retry[0]['attempt'], 2)
            self.assertEqual(len(read_rows(output / 'predictions.jsonl')), 3)

    def test_scoring_keeps_unreviewed_null_and_failures_in_denominator(self):
        base = {'run_id': 'r', 'track': 'gold_text_verified', 'model_tag': 'model',
                'model_digest': 'digest', 'category': 'math', 'evidence_sha256': 'e',
                'latency_seconds': 1, 'citation_presence': True, 'answer': 'answer'}
        rows = [{**base, 'question_id': 'q1', 'status': 'completed'},
                {**base, 'question_id': 'q2', 'status': 'oom'},
                {**base, 'question_id': 'q3', 'status': 'evidence_unverified'}]
        metrics = next(m for m in summarize(rows) if m['category'] == 'all')
        self.assertEqual(metrics['eligible_cases'], 2)
        self.assertEqual(metrics['technical_failure_count'], 1)
        self.assertIsNone(metrics['correctness_all_eligible'])
        receipt = {'review_id': review_id(rows[0]), 'correctness': 1, 'reviewer': 'reviewer', 'provenance': 'AI fixture'}
        metrics = next(m for m in summarize(rows, [receipt]) if m['category'] == 'all')
        self.assertEqual(metrics['correctness_all_eligible'], 0.5)
        self.assertEqual(metrics['correctness_reviewed_completed'], 1)
        with self.assertRaises(ValueError):
            summarize(rows, [{**receipt, 'review_id': 'stale'}])

    def test_page_citation_presence_is_not_support(self):
        result = citation_metrics('Claim [Trang 2]', [1])
        self.assertTrue(result['citation_presence'])
        self.assertEqual(result['invalid_page_citations'], [2])
        self.assertNotIn('citation_supported', result)

    def test_reviewed_transcription_requires_source_and_corrected_hash(self):
        from src.benchmark.evidence_packets import build_packets
        q = {'question_id': 'q', 'paper_ids': ['p'], 'category': 'math', 'question': 'question',
             'evidence': [{'paper_id': 'p', 'pdf_sha256': 'sha', 'page': 1, 'quote': 'broken root'}]}
        with patch('src.benchmark.evidence_packets.load_dev', return_value=([q], {})), tempfile.TemporaryDirectory() as tmp:
            original = build_packets('gold_text_verified')[0]
            corrected = copy.deepcopy(original['evidence'])
            corrected[0]['content'] = 'sqrt(x)'
            receipt = {'question_id': 'q', 'source_evidence_sha256': original['source_evidence_sha256'],
                       'evidence_sha256': fingerprint({'evidence': corrected, 'images': []}),
                       'verified_text': {'0': 'sqrt(x)'}, 'verified': True,
                       'reviewer': 'AI test fixture', 'method': 'visual', 'reviewed_at': 'test',
                       'provenance': 'unit fixture'}
            path = Path(tmp) / 'review.jsonl'
            path.write_bytes(canonical(receipt) + b'\n')
            actual = build_packets('gold_text_verified', review_file=path)[0]
            self.assertEqual(actual['gold_evidence_status'], 'verified_ai_or_human_receipt')
            self.assertEqual(actual['evidence'][0]['content'], 'sqrt(x)')
            receipt['source_evidence_sha256'] = 'stale'
            path.write_bytes(canonical(receipt) + b'\n')
            self.assertEqual(build_packets('gold_text_verified', review_file=path)[0]['gold_evidence_status'], 'unverified')
