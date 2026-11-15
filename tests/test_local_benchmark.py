import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from src.benchmark.local_common import (CONFIG, PROJECT_ROOT, canonical, file_hash, fingerprint,
                                        pipeline_code_hashes, read_json, read_rows)
from src.benchmark.local_llm_adapter import OllamaAdapter, ModelError
from src.benchmark.runner_local import run, messages_for, _validate_test_freeze
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
    def setUp(self):
        # Mock inference tests must not contend with a real benchmark/ingestion job.
        runtime = tempfile.TemporaryDirectory()
        self.addCleanup(runtime.cleanup)
        isolation = patch('src.benchmark.runner_local.RUNS', Path(runtime.name))
        isolation.start()
        self.addCleanup(isolation.stop)

    def test_frozen_test_runner_requires_freeze_before_reading_packets(self):
        from src.benchmark.runner_local import _run
        with tempfile.TemporaryDirectory() as tmp, patch('src.benchmark.runner_local.read_rows') as read_packet_rows:
            with self.assertRaisesRegex(ValueError, 'require --freeze-manifest'):
                _run(Path(tmp) / 'missing.jsonl', ['candidate', 'baseline'], Path(tmp) / 'run',
                     adapter=FakeAdapter(), protocol_path=CONFIG / 'final_test_protocol_v1.json')
            read_packet_rows.assert_not_called()

    def test_frozen_test_manifest_binds_candidate_protocol_and_packets(self):
        candidate_path = CONFIG / 'final_candidate_v1.json'
        protocol_path = CONFIG / 'final_test_protocol_v1.json'
        candidate = read_json(candidate_path)
        code_hashes = {path.relative_to(PROJECT_ROOT).as_posix(): file_hash(path) for path in
                       sorted((PROJECT_ROOT / 'src/benchmark').glob('*.py'))}
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'tests') as tmp:
            root = Path(tmp)
            packets_path = root / 'packets.jsonl'
            packets_path.write_bytes(b'test packet fixture without labels\n')
            freeze_path = root / 'freeze.json'
            freeze = {
                'status': 'frozen_before_test', 'candidate_commit_sha': 'fixture-head',
                'candidate_config_path': candidate_path.relative_to(PROJECT_ROOT).as_posix(),
                'candidate_config_sha256': file_hash(candidate_path),
                'protocol_path': protocol_path.relative_to(PROJECT_ROOT).as_posix(),
                'protocol_sha256': file_hash(protocol_path),
                'judge_protocol_path': candidate['judge_protocol_path'],
                'judge_protocol_sha256': candidate['judge_protocol_sha256'],
                'prompt_sha256': candidate['prompt_sha256'],
                'track': 'retrieved_text_frozen', 'expected_test_question_count': 268,
                'test_frozen_sha256': 'a' * 64, 'models': candidate['models'],
                'thresholds': candidate['thresholds'], 'benchmark_code_sha256': code_hashes,
                'pipeline_code_sha256': candidate['pipeline_code_sha256'],
                'phase6_code_sha256': candidate['phase6_code_sha256'],
                'retrieval': candidate['retrieval'],
            }
            freeze_path.write_text(json.dumps(freeze), encoding='utf-8')
            manifest = {
                'split': 'test', 'track': 'retrieved_text_frozen',
                'freeze_manifest_sha256': file_hash(freeze_path),
                'test_frozen_sha256': freeze['test_frozen_sha256'],
                'protocol_sha256': freeze['protocol_sha256'],
                'label_fields_excluded': True, 'packets': 268,
                'question_ids': [f'q{i}' for i in range(268)],
                'sha256': file_hash(packets_path),
            }
            packets_path.with_suffix('.manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            verified, protocol, bound_manifest = _validate_test_freeze(
                freeze_path, packets_path, protocol_path, head='fixture-head'
            )
            self.assertEqual(verified['status'], 'frozen_before_test')
            self.assertEqual(protocol['split'], 'test')
            self.assertEqual(bound_manifest['packets'], 268)

    def test_frozen_test_scorer_enforces_gates_on_synthetic_packets(self):
        import subprocess
        from scripts.score_frozen_test import score

        candidate_path = CONFIG / 'final_candidate_v1.json'
        protocol_path = CONFIG / 'final_test_protocol_v1.json'
        candidate = read_json(candidate_path)
        code_hashes = {path.relative_to(PROJECT_ROOT).as_posix(): file_hash(path) for path in
                       sorted((PROJECT_ROOT / 'src/benchmark').glob('*.py'))}
        pipeline_hashes = pipeline_code_hashes()
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / 'tests') as tmp:
            root = Path(tmp)
            run_dir = root / 'run'
            run_dir.mkdir()
            packets_path = root / 'packets.jsonl'
            packets_path.write_bytes(b'synthetic packet payload\n')
            qids = [f'q{i:03}' for i in range(268)]
            freeze = {
                'status': 'frozen_before_test',
                'candidate_commit_sha': subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT, text=True
                ).strip(),
                'candidate_config_path': candidate_path.relative_to(PROJECT_ROOT).as_posix(),
                'candidate_config_sha256': file_hash(candidate_path),
                'protocol_path': candidate['protocol_path'],
                'protocol_sha256': candidate['protocol_sha256'],
                'judge_protocol_path': candidate['judge_protocol_path'],
                'judge_protocol_sha256': candidate['judge_protocol_sha256'],
                'prompt_sha256': candidate['prompt_sha256'],
                'track': 'retrieved_text_frozen',
                'expected_test_question_count': 268,
                'test_frozen_sha256': 'b' * 64,
                'models': candidate['models'],
                'thresholds': candidate['thresholds'],
                'benchmark_code_sha256': code_hashes,
                'pipeline_code_sha256': pipeline_hashes,
                'phase6_code_sha256': candidate['phase6_code_sha256'],
                'retrieval': candidate['retrieval'],
            }
            freeze_path = root / 'freeze.json'
            freeze_path.write_text(json.dumps(freeze), encoding='utf-8')
            packets_manifest = {
                'freeze_manifest_sha256': file_hash(freeze_path),
                'test_frozen_sha256': freeze['test_frozen_sha256'],
                'packets': 268, 'question_ids': qids,
            }
            packets_path.with_suffix('.manifest.json').write_text(
                json.dumps(packets_manifest), encoding='utf-8'
            )
            predictions, receipts = [], []
            categories = ['math', 'code', 'table', 'unanswerable']
            for model in candidate['models']:
                for index, qid in enumerate(qids):
                    row = {
                        'run_id': 'synthetic', 'track': 'retrieved_text_frozen', 'split': 'test',
                        'question_id': qid, 'category': categories[index % len(categories)],
                        'model_tag': model['model_tag'], 'model_digest': model['model_digest'],
                        'quantization': model['quantization'], 'status': 'completed',
                        'answer': 'synthetic answer', 'correctness': None,
                        'input_sha256': f'input-{qid}', 'packet_sha256': f'packet-{qid}',
                        'evidence_sha256': f'evidence-{qid}', 'latency_seconds': 0.1,
                    }
                    predictions.append(row)
                    receipts.append({
                        'review_id': review_id(row), 'question_id': qid,
                        'category': row['category'], 'correctness': 1 if model['role'] == 'candidate' else 0.5,
                        'input_sha256': row['input_sha256'], 'packet_sha256': row['packet_sha256'],
                        'evidence_sha256': row['evidence_sha256'],
                        'judge_protocol_sha256': freeze['judge_protocol_sha256'],
                        'reviewer': 'synthetic test fixture', 'provenance': 'unit test only',
                    })
            (run_dir / 'predictions.jsonl').write_text(
                ''.join(json.dumps(row) + '\n' for row in predictions), encoding='utf-8'
            )
            (run_dir / 'manifest.json').write_text(json.dumps({
                'git_sha': freeze['candidate_commit_sha'],
                'protocol_sha256': freeze['protocol_sha256'],
                'packets_sha256': file_hash(packets_path),
                'track': 'retrieved_text_frozen', 'split': 'test',
                'protocol': {'split': 'test'},
                'freeze_manifest_sha256': file_hash(freeze_path),
                'test_frozen_sha256': freeze['test_frozen_sha256'],
                'prompt_sha256': freeze['prompt_sha256'],
                'code_sha256': code_hashes,
                'pipeline_code_sha256': pipeline_hashes,
            }), encoding='utf-8')
            review_path = run_dir / 'reviews.jsonl'
            review_path.write_text(
                ''.join(json.dumps(row) + '\n' for row in receipts), encoding='utf-8'
            )
            report = score(
                run_dir, packets_path, freeze_path, review_path,
                root / 'report.json', root / 'report.md'
            )
            self.assertTrue(report['candidate_passes_all_thresholds'])
            self.assertEqual(report['candidate']['questions'], 268)
            self.assertAlmostEqual(report['paired_candidate_minus_baseline_all_eligible']['delta'], 0.5)

    def test_normalized_view_preserves_source_and_failure_denominator(self):
        from scripts.normalize_benchmark_answers import normalize
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'source', Path(tmp) / 'analysis'
            source.mkdir()
            base = {'run_id': 'r', 'track': 'gold_text_verified', 'model_tag': 'm',
                    'model_digest': 'digest', 'category': 'math', 'evidence_sha256': 'e',
                    'status': 'completed', 'latency_seconds': 1, 'allowed_pages': [1]}
            rows = [{**base, 'question_id': 'q1', 'answer': '<think>Wrong [Trang 99]</think>Fact [Trang 1]'},
                    {**base, 'question_id': 'q2', 'answer': '<think>Only reasoning [Trang 99]'}]
            original = b''.join(canonical(row) + b'\n' for row in rows)
            (source / 'predictions.jsonl').write_bytes(original)
            (source / 'manifest.json').write_text('{"git_sha":"inference-baseline"}')
            normalize(source, output)
            self.assertEqual((source / 'predictions.jsonl').read_bytes(), original)
            actual = read_rows(output / 'predictions.jsonl')
            self.assertEqual(actual[0]['answer'], 'Fact [Trang 1]')
            self.assertEqual(actual[0]['citations'], [1])
            self.assertEqual(actual[1]['status'], 'empty_output')
            self.assertEqual(actual[1]['raw_answer'], rows[1]['answer'])
            receipt = {'review_id': review_id(actual[0]), 'correctness': 1,
                       'reviewer': 'fixture', 'provenance': 'unit test'}
            metric = next(m for m in summarize(actual, [receipt]) if m['category'] == 'all')
            self.assertEqual(metric['technical_failure_count'], 1)
            self.assertEqual(metric['correctness_all_eligible'], 0.5)
            self.assertTrue(read_json(output / 'manifest.json')['analysis_only'])
            with self.assertRaises(ValueError):
                normalize(source, output)

    def test_inline_reasoning_cannot_supply_answer_or_citations(self):
        session = Mock()
        response = session.request.return_value
        response.status_code = 200
        raw = '<think>Wrong claim [Trang 99]</think>Final fact [Trang 1]'
        response.json.return_value = {'message': {'content': raw}, 'eval_count': 20,
                                      'eval_duration': 1000000, 'done_reason': 'stop'}
        adapter = OllamaAdapter(session=session)
        model = {'model_tag': 'test', 'model_digest': 'digest', 'vision': False,
                 'thinking_mode': 'native'}
        with patch.object(adapter, 'inspect', return_value=model):
            result = adapter.chat(model, [{'role': 'user', 'content': 'question'}], PROTOCOL)
        self.assertEqual(result['answer'], 'Final fact [Trang 1]')
        self.assertEqual(result['raw_answer'], raw)
        self.assertTrue(result['thinking_present'])
        self.assertEqual(citation_metrics(result['answer'], [1])['citations'], [1])

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={'ram_available_bytes': 3 * 1024**3})
    def test_analysis_view_cannot_be_resumed_as_inference(self, _resources):
        from scripts.normalize_benchmark_answers import normalize
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packets = root / 'packets.jsonl'
            packets.write_bytes(canonical(packet()) + b'\n')
            run(packets, ['a'], root / 'original', adapter=FakeAdapter())
            normalize(root / 'original', root / 'analysis')
            with self.assertRaisesRegex(ValueError, 'Analysis-only'):
                run(packets, ['a'], root / 'analysis', resume=True, adapter=FakeAdapter())

    def test_thinking_only_response_is_failure_with_usage_preserved(self):
        session = Mock()
        response = session.request.return_value
        response.status_code = 200
        adapter = OllamaAdapter(session=session)
        model = {'model_tag': 'test', 'model_digest': 'digest', 'vision': False,
                 'thinking_mode': 'native'}
        for raw in ('<think>Reasoning without final', '<think>Reasoning</think>'):
            response.json.return_value = {'message': {'content': raw},
                                          'eval_count': 512, 'done_reason': 'length'}
            with patch.object(adapter, 'inspect', return_value=model), self.assertRaises(ModelError) as ctx:
                adapter.chat(model, [{'role': 'user', 'content': 'question'}], PROTOCOL)
            self.assertEqual(ctx.exception.status, 'empty_output')
            self.assertEqual(ctx.exception.diagnostics['answer'], '')
            self.assertEqual(ctx.exception.diagnostics['raw_answer'], raw)
            self.assertEqual(ctx.exception.diagnostics['eval_count'], 512)
            self.assertTrue(ctx.exception.diagnostics['output_truncated'])

    def test_leaderboard_render_does_not_reset_reviewed_metrics(self):
        from src.benchmark.local_cli import leaderboard_main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = [{'model_tag': 'model', 'track': 'gold_text_verified', 'category': 'all',
                        'eligible_cases': 1, 'completed': 1, 'technical_failure_count': 0,
                        'reviewed_completed': 1, 'citation_presence_rate': 1,
                        'correctness_all_eligible': 1}]
            source = canonical(metrics)
            (root / 'metrics.json').write_bytes(source)
            (root / 'review_template.jsonl').write_text('keep reviewer edits', encoding='utf-8')
            with patch('sys.argv', ['leaderboard', '--run-dir', tmp]):
                self.assertEqual(leaderboard_main(), 0)
            self.assertEqual((root / 'metrics.json').read_bytes(), source)
            self.assertEqual((root / 'review_template.jsonl').read_text(encoding='utf-8'), 'keep reviewer edits')
            self.assertTrue((root / 'leaderboard.csv').exists())

    def test_preflight_preserves_installed_metadata_when_ram_gate_fails(self):
        from types import SimpleNamespace
        from src.benchmark.local_cli import preflight_main
        class MetadataAdapter(FakeAdapter):
            def installed(self): return [{'name': 'qwen3.5:2b', 'size': 1}]
            def inspect(self, tag):
                if tag != 'qwen3.5:2b': raise ModelError('not_installed', tag)
                return super().inspect(tag)
        with tempfile.TemporaryDirectory() as tmp:
            argv = ['preflight', '--smoke', '--output', tmp]
            with patch('sys.argv', argv), patch('src.benchmark.local_cli.OllamaAdapter', return_value=MetadataAdapter()), patch('src.benchmark.local_cli.command_snapshot', return_value={'stdout': '', 'exit_code': 0}), patch('src.benchmark.local_cli.psutil.virtual_memory', side_effect=[SimpleNamespace(available=10 * 1024**3), SimpleNamespace(available=0)]), patch('src.benchmark.local_cli.shutil.disk_usage', return_value=SimpleNamespace(free=100 * 1024**3)):
                self.assertEqual(preflight_main(), 0)
            row = next(r for r in read_json(Path(tmp) / 'preflight.json') if r['tag'] == 'qwen3.5:2b')
            self.assertEqual(row['status'], 'resource_ineligible')
            self.assertTrue(row['model_digest'])

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

    @patch('src.benchmark.runner_local.capture_resource_metrics', return_value={})
    def test_protocol_override_is_pinned_and_changed_seed_blocks_resume(self, _):
        from src.benchmark.local_common import file_hash
        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'packets.jsonl'
            source.write_bytes(canonical(packet()) + b'\n')
            protocol = {**PROTOCOL, 'seed': 43}
            protocol_path = root / 'protocol_seed43.json'
            protocol_path.write_text(json.dumps(protocol), encoding='utf-8')
            output = root / 'run'
            rows = run(source, ['model'], output, adapter=adapter, protocol_path=protocol_path)
            self.assertEqual(rows[0]['status'], 'completed')
            manifest = read_json(output / 'manifest.json')
            self.assertEqual(manifest['protocol']['seed'], 43)
            self.assertEqual(manifest['protocol_sha256'], file_hash(protocol_path))
            protocol_path.write_text(json.dumps({**PROTOCOL, 'seed': 44}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Existing run or changed inputs/config/model/code'):
                run(source, ['model'], output, adapter=adapter, protocol_path=protocol_path, resume=True)

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

    def test_vision_pair_keeps_text_prompt_identical_to_text_control(self):
        text_packet = packet()
        text_packet['track'] = 'retrieved_text_frozen'
        text_messages, text_pages = messages_for(text_packet, 'same system prompt', PROTOCOL)
        vision_packet = {**text_packet, 'track': 'retrieved_vision',
                         'images': [{'page': 1, 'sha256': 'image-hash'}]}
        vision_messages, vision_pages = messages_for(vision_packet, 'same system prompt', PROTOCOL)
        self.assertEqual(vision_messages, text_messages)
        self.assertEqual(vision_pages, text_pages)

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

    def test_page_ranges_and_unresolved_placeholders_are_detected(self):
        ranged = citation_metrics('Claim [Trang 3-5], then [Page 8-8].', [3, 4, 5, 8])
        self.assertEqual(ranged['citations'], [3, 4, 5, 8])
        self.assertTrue(ranged['citation_presence'])
        self.assertFalse(ranged['unresolved_citation_placeholder'])
        placeholder = citation_metrics('Unsupported claim [Trang N].', [1])
        self.assertTrue(placeholder['citation_presence'])
        self.assertTrue(placeholder['unresolved_citation_placeholder'])
        self.assertEqual(placeholder['citations'], [])

    def test_scoring_aggregates_review_support_abstention_and_claims(self):
        row = {'run_id': 'r', 'track': 'gold_text_verified', 'model_tag': 'm',
               'model_digest': 'digest', 'category': 'unanswerable', 'evidence_sha256': 'e',
               'latency_seconds': 1, 'answer': 'I cannot determine this from the excerpt.',
               'question_id': 'q1', 'status': 'completed'}
        receipt = {'review_id': review_id(row), 'correctness': 1, 'citation_supported': False,
                   'correct_abstention': True, 'false_refusal': False,
                   'reviewer': 'fixture', 'provenance': 'AI unit fixture',
                   'claims': [{'text': 'The excerpt omits the requested fact.', 'supported': True},
                              {'text': 'The paper contains no such result.', 'supported': False},
                              {'text': 'An unlabeled claim.', 'supported': None}]}
        metric = next(m for m in summarize([row], [receipt]) if m['category'] == 'all')
        self.assertEqual(metric['citation_supported_rate'], 0)
        self.assertEqual(metric['citation_supported_rated_count'], 1)
        self.assertEqual(metric['correct_abstention_rate'], 1)
        self.assertEqual(metric['false_refusal_rate'], 0)
        self.assertEqual(metric['claim_support_labeled_count'], 2)
        self.assertEqual(metric['claim_support_rate'], 0.5)
        self.assertEqual(metric['unsupported_claim_count'], 1)
        self.assertEqual(metric['unsupported_claims_per_reviewed_answer'], 1)

    def test_null_correctness_receipt_stays_pending_not_zero(self):
        row = {'run_id': 'r', 'track': 'retrieved_text_frozen', 'model_tag': 'm',
               'model_digest': 'digest', 'category': 'math', 'evidence_sha256': 'e',
               'latency_seconds': 1, 'answer': 'Partial answer.', 'question_id': 'q1',
               'status': 'completed'}
        receipt = {'review_id': review_id(row), 'correctness': None, 'citation_supported': True,
                   'reviewer': 'fixture', 'provenance': 'pending label conflict'}
        metric = next(m for m in summarize([row], [receipt]) if m['category'] == 'all')
        self.assertEqual(metric['review_receipts_completed'], 1)
        self.assertEqual(metric['pending_correctness_completed'], 1)
        self.assertEqual(metric['unreviewed_completed'], 1)
        self.assertIsNone(metric['correctness_reviewed_completed'])
        self.assertIsNone(metric['correctness_all_eligible'])
        self.assertEqual(metric['citation_supported_rate'], 1)

    def test_runtime_resource_failure_stays_in_deployment_denominator(self):
        base = {'run_id': 'r', 'track': 'gold_text_verified', 'model_tag': 'm',
                'model_digest': 'digest', 'category': 'math', 'evidence_sha256': 'e',
                'latency_seconds': 1, 'answer': 'Fact'}
        rows = [{**base, 'question_id': 'q1', 'status': 'completed'},
                {**base, 'question_id': 'q2', 'status': 'resource_ineligible'}]
        reviews = [{'review_id': review_id(rows[0]), 'correctness': 1,
                    'reviewer': 'fixture', 'provenance': 'unit test'}]
        metric = next(m for m in summarize(rows, reviews) if m['category'] == 'all')
        self.assertEqual(metric['eligible_cases'], 2)
        self.assertEqual(metric['technical_failure_count'], 1)
        self.assertEqual(metric['correctness_all_eligible'], 0.5)
        self.assertEqual(metric['excluded_statuses'], {})

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
