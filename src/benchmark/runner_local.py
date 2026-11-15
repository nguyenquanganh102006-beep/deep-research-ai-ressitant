"""Sequential, hash-locked local model comparisons. No reference labels enter prompts."""
from __future__ import annotations

import subprocess
import time
import platform
import importlib.metadata
import psutil
from pathlib import Path

from config import PROJECT_ROOT
from src.benchmark.local_common import (CONFIG, canonical, fingerprint, file_hash, read_rows,
                                        read_json, write_json, append_jsonl, pipeline_code_hashes)
from src.benchmark.local_llm_adapter import OllamaAdapter, ModelError
from src.metrics import capture_resource_metrics as _capture_resource_metrics
from src.benchmark.local_common import file_lock, RUNS


def capture_resource_metrics():
    return {**_capture_resource_metrics(), 'ram_available_bytes': psutil.virtual_memory().available}


def messages_for(packet: dict, prompt: str, protocol: dict) -> tuple[list, list[int]]:
    if (protocol['max_input_utf8_bytes'] + protocol['num_predict']
            + protocol['template_token_reserve'] > protocol['num_ctx']):
        raise ValueError('Protocol text/output/template budgets exceed context')
    # Whitelist fields; never serialize a QA/evaluator record into the model input.
    remaining = protocol['max_evidence_utf8_bytes']
    sections, pages = [], set()
    for e in packet['evidence']:
        header = f"Paper {e['paper_id']} | Trang {e['page_start']}-{e['page_end']}\n"
        budget = remaining - len(header.encode('utf-8'))
        if budget <= 0:
            if packet['track'] == 'gold_text_verified':
                raise ModelError('context_ineligible', 'Gold evidence cannot be silently truncated')
            break
        original = e['content'].encode('utf-8')
        if len(original) > budget and packet['track'] == 'gold_text_verified':
            raise ModelError('context_ineligible', 'Gold evidence cannot be silently truncated')
        text = original[:budget].decode('utf-8', errors='ignore')
        if not text:
            continue
        sections.append(header + text + ('\n[truncated]' if len(original) > budget else ''))
        remaining -= len((sections[-1] + '\n').encode('utf-8'))
        pages.update(range(e['page_start'], e['page_end'] + 1))
    image_pages = [i['page'] for i in packet.get('images', [])]
    pages.update(image_pages)
    user = 'QUESTION\n' + packet['question'] + '\n\nEVIDENCE\n' + '\n\n'.join(sections)
    messages = [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': user}]
    size = sum(len(m['content'].encode('utf-8')) for m in messages)
    # Conservative byte budget; retain actual prompt_eval_count too. No per-model trimming.
    if size > protocol['max_input_utf8_bytes']:
        raise ModelError('context_ineligible', f'Common prompt byte budget exceeded: {size}')
    return messages, sorted(pages)


def run(*args, **kwargs):
    with file_lock(RUNS / '.runtime.lock'):
        return _run(*args, **kwargs)


def _validate_test_freeze(freeze_path: Path, packets_path: Path, protocol_path: Path,
                          *, head: str | None = None):
    """Validate the committed test freeze without opening the sealed QA file."""
    freeze_path = freeze_path.resolve()
    packets_path = packets_path.resolve()
    protocol_path = protocol_path.resolve()
    freeze = read_json(freeze_path)
    head = head or subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT, text=True
    ).strip()
    protocol_rel = protocol_path.relative_to(PROJECT_ROOT).as_posix()
    if freeze.get('status') != 'frozen_before_test' or freeze.get('candidate_commit_sha') != head:
        raise ValueError('Current HEAD does not match the pretest freeze commit')
    if freeze.get('protocol_path') != protocol_rel or freeze.get('protocol_sha256') != file_hash(protocol_path):
        raise ValueError('Test protocol path/hash differs from the pretest freeze')
    candidate_config = PROJECT_ROOT / freeze.get('candidate_config_path', '')
    if (not freeze.get('candidate_config_sha256')
            or file_hash(candidate_config) != freeze.get('candidate_config_sha256')):
        raise ValueError('Candidate selection config differs from the pretest freeze')
    candidate_doc = read_json(candidate_config)
    if (candidate_doc.get('models') != freeze.get('models')
            or candidate_doc.get('thresholds') != freeze.get('thresholds')
            or candidate_doc.get('benchmark_code_sha256') != freeze.get('benchmark_code_sha256')
            or candidate_doc.get('pipeline_code_sha256') != freeze.get('pipeline_code_sha256')
            or candidate_doc.get('phase6_code_sha256') != freeze.get('phase6_code_sha256')
            or candidate_doc.get('retrieval') != freeze.get('retrieval')
            or candidate_doc.get('protocol_path') != protocol_rel
            or candidate_doc.get('protocol_sha256') != freeze.get('protocol_sha256')):
        raise ValueError('Frozen models, thresholds, or code differ from the committed candidate selection')
    phase6_code = {rel: file_hash(PROJECT_ROOT / rel) for rel in candidate_doc.get('phase6_code_sha256', {})}
    if not phase6_code or phase6_code != freeze.get('phase6_code_sha256'):
        raise ValueError('Final test preparation/scoring code differs from the pretest freeze')
    if pipeline_code_hashes() != freeze.get('pipeline_code_sha256'):
        raise ValueError('PDF ingestion/retrieval pipeline differs from the pretest freeze')
    if (freeze.get('prompt_sha256') != file_hash(CONFIG / 'prompt_v1.txt')
            or candidate_doc.get('prompt_sha256') != freeze.get('prompt_sha256')
            or freeze.get('judge_protocol_sha256') is None
            or candidate_doc.get('judge_protocol_sha256') != freeze.get('judge_protocol_sha256')):
        raise ValueError('Prompt or judge protocol identity is missing/stale')
    judge_protocol_path = PROJECT_ROOT / freeze.get('judge_protocol_path', '')
    if file_hash(judge_protocol_path) != freeze.get('judge_protocol_sha256'):
        raise ValueError('Judge protocol differs from the pretest freeze')
    if (freeze.get('track') != 'retrieved_text_frozen'
            or freeze.get('expected_test_question_count') != 268
            or not freeze.get('test_frozen_sha256')):
        raise ValueError('Pretest freeze must specify Track B and exactly 268 test questions')
    protocol = read_json(protocol_path)
    if protocol.get('split') != 'test':
        raise ValueError('A frozen test run requires protocol split=test')

    packet_manifest = read_json(packets_path.with_suffix('.manifest.json'))
    if (packet_manifest.get('split') != 'test'
            or packet_manifest.get('track') != 'retrieved_text_frozen'
            or packet_manifest.get('freeze_manifest_sha256') != file_hash(freeze_path)
            or packet_manifest.get('test_frozen_sha256') != freeze.get('test_frozen_sha256')
            or packet_manifest.get('protocol_sha256') != freeze.get('protocol_sha256')
            or packet_manifest.get('label_fields_excluded') is not True
            or packet_manifest.get('packets') != 268
            or packet_manifest.get('sha256') != file_hash(packets_path)):
        raise ValueError('Final test packet manifest is not fully bound to the freeze')
    qids = packet_manifest.get('question_ids')
    if not isinstance(qids, list) or len(qids) != 268 or len(set(qids)) != 268:
        raise ValueError('Final test packet manifest must list 268 unique question IDs')
    models = freeze.get('models')
    if (not isinstance(models, list) or len(models) != 2
            or {model.get('role') for model in models} != {'candidate', 'baseline'}):
        raise ValueError('Freeze must pin exactly one candidate and one baseline')
    return freeze, protocol, packet_manifest


def _run(packets_path: Path, tags: list[str], run_dir: Path, *, resume=False,
        retry_failed=False, dry_run=False, adapter=None, protocol_path: Path | None = None,
        test_freeze_path: Path | None = None):
    adapter = adapter or OllamaAdapter()
    if len(set(tags)) != len(tags):
        raise ValueError('Duplicate model tags')
    protocol_path = (protocol_path or (CONFIG / 'protocol_v1.json')).resolve()
    protocol = read_json(protocol_path)
    test_freeze = None
    if protocol.get('split') == 'test':
        if test_freeze_path is None:
            raise ValueError('Frozen test runs require --freeze-manifest')
        test_freeze, protocol, _ = _validate_test_freeze(
            test_freeze_path, packets_path, protocol_path
        )
    elif test_freeze_path is not None:
        raise ValueError('A test freeze manifest cannot be used for a dev run')
    packets = read_rows(packets_path)
    split = protocol.get('split')
    if split not in {'dev', 'test'} or not packets or any(p.get('split') != split for p in packets):
        raise ValueError(f'Only nonempty {split!r} packet files are supported')
    tracks = {p['track'] for p in packets}
    if len(tracks) != 1 or not tracks <= {'gold_text_verified', 'retrieved_text_frozen', 'retrieved_vision'}:
        raise ValueError('One supported track per run is required')
    if split == 'test' and tracks != {'retrieved_text_frozen'}:
        raise ValueError('The frozen final run is limited to retrieved_text_frozen')
    if len({p['question_id'] for p in packets}) != len(packets):
        raise ValueError('Duplicate question IDs')
    for p in packets:
        expected = p['packet_sha256']
        if fingerprint({k: v for k, v in p.items() if k != 'packet_sha256'}) != expected:
            raise ValueError('Packet hash mismatch')
        if p['evidence_sha256'] != fingerprint({'evidence': p['evidence'], 'images': p['images']}):
            raise ValueError('Evidence hash mismatch')
        if p['track'] == 'gold_text_verified' and p['gold_evidence_status'] != 'unverified':
            receipt = p.get('verification_receipt') or {}
            if (receipt.get('verified') is not True
                    or receipt.get('evidence_sha256') != p['evidence_sha256']
                    or receipt.get('source_evidence_sha256') != p.get('source_evidence_sha256')
                    or not all(receipt.get(k) for k in ('reviewer', 'method', 'reviewed_at', 'provenance'))):
                raise ValueError('Missing/stale verification provenance')
    prompt = (CONFIG / 'prompt_v1.txt').read_text(encoding='utf-8')
    models = [adapter.inspect(tag) for tag in tags]
    if len({m['model_digest'] for m in models}) != len(models):
        raise ValueError('Model aliases resolve to the same digest')
    if split == 'test':
        frozen = {m['model_tag']: m for m in test_freeze['models']}
        if set(frozen) != set(tags):
            raise ValueError('Test model tags must exactly match the pretest candidate and baseline')
        for model in models:
            expected = frozen[model['model_tag']]
            if (model['model_digest'] != expected['model_digest']
                    or model['quantization'] != expected['quantization']):
                raise ValueError(f"Model digest/quantization differs from freeze: {model['model_tag']}")
    try:
        gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version,memory.total',
                                       '--format=csv,noheader'], text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError):
        gpu = None
    environment = {'python': platform.python_version(), 'os': platform.platform(), 'gpu': gpu,
                   'ollama': adapter.request('GET', '/api/version') if hasattr(adapter, 'request') else 'mock',
                   'packages': {p: importlib.metadata.version(p) for p in ('requests', 'numpy', 'ollama')}}
    prompt_hash = file_hash(CONFIG / 'prompt_v1.txt')
    code_sha256 = {p.relative_to(PROJECT_ROOT).as_posix(): file_hash(p) for p in
                   sorted((PROJECT_ROOT / 'src/benchmark').glob('*.py'))}
    if test_freeze is not None and code_sha256 != test_freeze.get('benchmark_code_sha256'):
        raise ValueError('Benchmark source code differs from the pretest freeze')
    retrieval_code_sha256 = pipeline_code_hashes()
    if test_freeze is not None and retrieval_code_sha256 != test_freeze.get('pipeline_code_sha256'):
        raise ValueError('PDF ingestion/retrieval code differs from the pretest freeze')
    lock = {'schema_version': 1, 'packets_sha256': file_hash(packets_path), 'environment': environment,
            'protocol_path': str(protocol_path), 'protocol_sha256': file_hash(protocol_path),
            'protocol': protocol, 'prompt_sha256': prompt_hash,
            'split': split, 'track': next(iter(tracks)),
            'pipeline_code_sha256': retrieval_code_sha256,
            'models': models,
            'git_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=PROJECT_ROOT, text=True).strip(),
            'code_sha256': code_sha256}
    if test_freeze is not None:
        lock.update(test_freeze_manifest_path=str(test_freeze_path.resolve()),
                    freeze_manifest_sha256=file_hash(test_freeze_path),
                    test_frozen_sha256=test_freeze['test_frozen_sha256'])
    lock_hash = fingerprint(lock)
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / 'manifest.json'
    if manifest_path.exists():
        existing_manifest = read_json(manifest_path)
        if existing_manifest.get('analysis_only'):
            raise ValueError('Analysis-only views cannot be resumed as inference runs')
        if not resume or existing_manifest['lock_sha256'] != lock_hash:
            raise ValueError('Existing run or changed inputs/config/model/code; use a new run ID')
    else:
        write_json(manifest_path, {'lock_sha256': lock_hash, **lock,
                                  'resource_snapshot': capture_resource_metrics(),
                                  'context_policy_note': 'Conservative common UTF-8 text byte guard plus observed prompt_eval_count; image token count is not pretokenized.'})
    predictions = run_dir / 'predictions.jsonl'
    previous = {(r['model_digest'], r['question_id']): r for r in read_rows(predictions)} if predictions.exists() else {}
    if dry_run:
        preview = []
        for packet in packets:
            try:
                messages, pages = messages_for(packet, prompt, protocol)
                preview.append({'id': packet['question_id'], 'input_sha256': fingerprint(messages),
                                'allowed_pages': pages, 'gold_status': packet['gold_evidence_status']})
            except ModelError as exc:
                preview.append({'id': packet['question_id'], 'status': exc.status})
        write_json(run_dir / 'dry_run.json', preview)
        return preview
    # OS advisory lock stops concurrent runners sharing one run directory.
    with file_lock(run_dir / '.run.lock'):
        rows = []
        for model in models:
            tag, digest = model['model_tag'], model['model_digest']
            pending = [p for p in packets if (digest, p['question_id']) not in previous
                       or (retry_failed and previous[(digest, p['question_id'])]['status'] not in
                           {'completed', 'evidence_unverified', 'not_applicable', 'context_ineligible'})]
            if not pending:
                continue
            # Unload other models before warmup; never delete weights.
            for running in adapter.running():
                if running.get('name', running.get('model')) != tag:
                    adapter.unload(running.get('name', running.get('model')))
            warm_error = None
            eligible = [p for p in pending if not
                        (p['track'] == 'gold_text_verified' and p['gold_evidence_status'] == 'unverified')
                        and not (p['track'] == 'retrieved_vision' and not model['vision'])]
            if eligible:
                try:
                    resources = capture_resource_metrics()
                    if resources.get('ram_available_bytes', float('inf')) < protocol['minimum_ram_gb'] * 1024**3:
                        raise ModelError('resource_ineligible', 'Insufficient available RAM before model load')
                    warm = adapter.chat(model, [{'role': 'user', 'content': 'Reply OK.'}], protocol)
                    append_jsonl(run_dir / 'usage.jsonl', {'model_tag': tag, 'phase': 'warmup', **warm})
                except ModelError as exc:
                    warm_error = exc
            try:
                for packet in pending:
                    case_started = time.perf_counter()
                    row = {'run_id': run_dir.name, 'track': packet['track'], 'split': split,
                           'question_id': packet['question_id'], 'category': packet['category'],
                           'paper_ids': packet['paper_ids'], 'model_tag': tag, 'model_digest': digest,
                           'quantization': model['quantization'], 'thinking_mode': model['thinking_mode'],
                           'prompt_sha256': prompt_hash, 'evidence_sha256': packet['evidence_sha256'],
                           'packet_sha256': packet['packet_sha256'], 'correctness': None,
                           'citation_supported': None, 'review_status': 'pending', 'answer': None,
                           'attempt': previous.get((digest, packet['question_id']), {}).get('attempt', 0) + 1,
                           'transport_retries': 0}
                    try:
                        if packet['track'] == 'gold_text_verified' and packet['gold_evidence_status'] == 'unverified':
                            raise ModelError('evidence_unverified', 'Explicit matching evidence review receipt required')
                        if packet['track'] == 'retrieved_vision' and not model['vision']:
                            raise ModelError('not_applicable', 'No vision capability')
                        if warm_error:
                            raise warm_error
                        messages, pages = messages_for(packet, prompt, protocol)
                        row['input_sha256'] = fingerprint(messages)
                        row['allowed_pages'] = pages
                        row['resources_before'] = capture_resource_metrics()
                        if row['resources_before'].get('ram_available_bytes', float('inf')) < protocol['minimum_runtime_ram_gb'] * 1024**3:
                            raise ModelError('resource_ineligible', 'Available RAM fell below runtime safety budget')
                        images = [{**i, 'absolute_path': str(PROJECT_ROOT / i['path'])} for i in packet['images']]
                        for attempt in range(protocol['retry'] + 1):
                            try:
                                output = adapter.chat(model, messages, protocol, images)
                                break
                            except ModelError as exc:
                                if exc.status != 'endpoint_error' or attempt >= protocol['retry']:
                                    raise
                                append_jsonl(run_dir / 'retry_errors.jsonl', {
                                    'model_tag': tag, 'question_id': packet['question_id'],
                                    'attempt': row['attempt'], 'retry_index': attempt + 1,
                                    'status': exc.status, 'error': str(exc)})
                                row['transport_retries'] += 1
                                time.sleep(1)
                        if (output.get('prompt_eval_count') or 0) + protocol['num_predict'] > protocol['num_ctx']:
                            raise ModelError('context_ineligible', 'Observed prompt plus reserved output exceeds context')
                        row.update(output)
                        row['status'] = 'completed'
                        row['resources_after'] = capture_resource_metrics()
                        row['placement'] = adapter.running()
                        append_jsonl(run_dir / 'usage.jsonl', {
                            'model_tag': tag, 'question_id': packet['question_id'], 'phase': 'recorded',
                            **{k: row.get(k) for k in ('latency_seconds', 'total_duration', 'load_duration',
                               'prompt_eval_count', 'eval_count', 'eval_duration', 'placement',
                               'resources_before', 'resources_after')}})
                        from src.benchmark.scoring_local import citation_metrics
                        row.update(citation_metrics(row['answer'], pages))
                    except ModelError as exc:
                        row.update(exc.diagnostics)
                        row.update(status=exc.status, error=str(exc))
                    row['case_wall_seconds'] = round(time.perf_counter() - case_started, 4)
                    append_jsonl(predictions, row)
                    rows.append(row)
            finally:
                adapter.unload(tag)
        return rows
