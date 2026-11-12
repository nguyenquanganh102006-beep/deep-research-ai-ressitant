"""CLI entry points for the isolated local LLM benchmark framework."""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import psutil
import requests

from config import PROJECT_ROOT
from src.benchmark.local_common import (CONFIG, RUNS, file_hash, read_json, read_rows,
                                        load_dev, write_json, fingerprint, append_jsonl, file_lock)
from src.benchmark.local_llm_adapter import OllamaAdapter, ModelError


def command_snapshot(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        return {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'error': str(exc)}


def preflight_main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=CONFIG / 'models.json')
    p.add_argument('--stage', choices=['A', 'B', 'all'], default='all')
    p.add_argument('--split', choices=['dev'], default='dev')
    p.add_argument('--check-env', action='store_true')
    p.add_argument('--check-dataset', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--pull-batch', type=int, default=0)
    p.add_argument('--max-disk-gb', type=float, default=40)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--output', type=Path, default=RUNS / 'preflight_current')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    protocol = read_json(CONFIG / 'protocol_v1.json')
    registry = read_json(args.config)['models']
    if len(registry) != 32 or len({m['tag'] for m in registry}) != 32:
        raise ValueError('Registry must contain 32 unique candidates')
    env = {'python': sys.version, 'platform': platform.platform(),
           'git': command_snapshot(['git', 'rev-parse', 'HEAD']),
           'status': command_snapshot(['git', 'status', '--short']),
           'ram_available_bytes': psutil.virtual_memory().available,
           'disk_free_bytes': shutil.disk_usage(PROJECT_ROOT).free,
           'gpu': command_snapshot(['nvidia-smi', '--query-gpu=name,driver_version,memory.total,memory.free', '--format=csv']),
           'ollama_version': command_snapshot(['ollama', '--version']),
           'browser_ui_unverified': True}
    resource_ok = (env['ram_available_bytes'] >= protocol['minimum_ram_gb'] * 1024**3
                   and env['disk_free_bytes'] >= protocol['minimum_free_disk_gb'] * 1024**3)
    env['resource_gate'] = {'passed': resource_ok, 'minimum_ram_gb': protocol['minimum_ram_gb'],
                            'minimum_free_disk_gb': protocol['minimum_free_disk_gb']}
    write_json(args.output / 'environment.json', env)
    if args.check_env:
        (args.output / 'pip-freeze.txt').write_text(command_snapshot([sys.executable, '-m', 'pip', 'freeze']).get('stdout', ''), encoding='utf-8')
    dataset_ok = True
    if args.check_dataset:
        from src.benchmark.evidence_packets import validate_dev
        validation = validate_dev()
        dataset_ok = validation['passed']
        write_json(args.output / 'dev_validation.json', validation)
    adapter = OllamaAdapter(timeout=protocol['timeout_seconds'])
    installed = {m.get('name', m.get('model')): m for m in adapter.installed()}
    candidates = [m for m in registry if args.stage == 'all' or m['stage'] == args.stage]
    if args.pull_batch and not args.dry_run:
        if not dataset_ok or not resource_ok:
            raise ValueError('Dataset/resource preflight failed; no pulls allowed')
        pool = [m for m in candidates if m['initial_batch']]
        with file_lock(RUNS / '.runtime.lock'):
            pulled = 0
            for model in pool:
                if model['tag'] in installed or pulled >= args.pull_batch:
                    continue
                base, tag = model['tag'].split(':', 1)
                response = requests.get(f'https://registry.ollama.ai/v2/library/{base}/manifests/{tag}',
                                        headers={'Accept': 'application/vnd.docker.distribution.manifest.v2+json'}, timeout=30)
                response.raise_for_status()
                size = sum(layer['size'] for layer in response.json().get('layers', []))
                if (sum(m['size'] for m in installed.values()) + size > args.max_disk_gb * 1024**3
                        or shutil.disk_usage(PROJECT_ROOT).free - size < protocol['minimum_free_disk_gb'] * 1024**3):
                    raise ModelError('resource_ineligible', 'Disk budget would be exceeded')
                result = adapter.request('POST', '/api/pull', {'model': model['tag'], 'stream': False}, timeout=1800)
                append_jsonl(args.output / 'pull_log.jsonl', {'tag': model['tag'], 'result': result})
                installed = {m.get('name', m.get('model')): m for m in adapter.installed()}
                pulled += 1
    rows = []
    for model in candidates:
        try:
            row = {'tag': model['tag'], 'status': 'metadata_ready_not_smoked', **adapter.inspect(model['tag'])}
            if args.smoke and not args.dry_run:
                if psutil.virtual_memory().available < protocol['minimum_ram_gb'] * 1024**3:
                    raise ModelError('resource_ineligible', 'Available RAM below preflight budget')
                with file_lock(RUNS / '.runtime.lock'):
                    for other in adapter.running():
                        adapter.unload(other.get('name', other.get('model')))
                    try:
                        outputs = [adapter.chat(row, [{'role': 'user', 'content': text}], protocol)
                                   for text in ('Reply OK.', 'What is the derivative of x squared?', 'Explain a for loop briefly.')]
                        row.update(status='ready', smoke=outputs, placement=adapter.running())
                    finally:
                        adapter.unload(model['tag'])
        except ModelError as exc:
            row = {'tag': model['tag'], 'status': exc.status, 'error': str(exc)}
        rows.append(row)
    write_json(args.output / 'preflight.json', rows)
    print({'environment': str(args.output), 'dataset_passed': dataset_ok, 'resource_passed': resource_ok,
           'candidates': len(rows), 'installed': sum('model_digest' in r for r in rows)})
    return 0 if dataset_ok and resource_ok else 1


def packets_main():
    p = argparse.ArgumentParser()
    p.add_argument('--split', choices=['dev'], default='dev')
    p.add_argument('--track', choices=['gold_text_verified', 'retrieved_text_frozen', 'retrieved_vision'], required=True)
    p.add_argument('--sample-manifest', type=Path)
    p.add_argument('--review-file', type=Path)
    p.add_argument('--source-text-packets', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    from src.benchmark.evidence_packets import validate_dev, build_packets, save_packets, add_vision
    if not validate_dev()['passed']:
        raise ValueError('Dev validation failed')
    ids = read_json(args.sample_manifest)['question_ids'] if args.sample_manifest else None
    with file_lock(RUNS / '.runtime.lock'):
        if args.track == 'retrieved_vision':
            if not args.source_text_packets:
                p.error('Vision requires --source-text-packets from frozen Track B')
            packets = add_vision(read_rows(args.source_text_packets))
        else:
            packets = build_packets(args.track, ids, args.review_file)
        print(save_packets(packets, args.output))
    return 0


def runner_main():
    p = argparse.ArgumentParser()
    p.add_argument('--split', choices=['dev'], default='dev')
    p.add_argument('--packets', type=Path)
    p.add_argument('--track', choices=['gold_text_verified', 'retrieved_text_frozen', 'retrieved_vision'])
    model_group = p.add_mutually_exclusive_group(required=True)
    model_group.add_argument('--models', nargs='+')
    model_group.add_argument('--model-set', choices=['all-ready', 'finalists'])
    p.add_argument('--run-dir', type=Path)
    p.add_argument('--sample-manifest', type=Path)
    p.add_argument('--limit', type=int)
    p.add_argument('--preflight-file', type=Path, default=RUNS / 'preflight_current/preflight.json')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--retry-failed', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if not args.packets:
        if not args.track:
            p.error('--packets or --track is required')
        args.packets = PROJECT_ROOT / f'data/benchmark/local_llm_packets/{args.track}_v1.jsonl'
    packets = read_rows(args.packets)
    if args.track and any(packet['track'] != args.track for packet in packets):
        raise ValueError('Track does not match frozen packet input')
    if args.model_set == 'all-ready':
        preflight = read_json(args.preflight_file)
        args.models = [r['tag'] for r in preflight if r['status'] == 'ready']
    elif args.model_set == 'finalists':
        args.models = read_json(CONFIG / 'finalists.json')['models']
    if not args.models:
        raise ValueError('No ready models; run model preflight smoke first')
    if args.sample_manifest:
        ids = read_json(args.sample_manifest)['question_ids']
        index = {packet['question_id']: packet for packet in packets}
        if len(set(ids)) != len(ids) or set(ids) - index.keys():
            raise ValueError('Sample IDs missing or duplicated')
        packets = [index[qid] for qid in ids]
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError('Limit must be positive')
        packets = packets[:args.limit]
    if not args.run_dir:
        args.run_dir = RUNS / ('run_' + fingerprint([packets, args.models])[:16])
    if args.sample_manifest or args.limit is not None:
        from src.benchmark.evidence_packets import save_packets
        selected = args.run_dir / 'selected_packets.jsonl'
        save_packets(packets, selected)
        args.packets = selected
    from src.benchmark.runner_local import run
    print({'new_rows': len(run(args.packets, args.models, args.run_dir,
                             resume=args.resume, retry_failed=args.retry_failed, dry_run=args.dry_run))})
    return 0


def score_main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-dir', type=Path, required=True)
    p.add_argument('--reviews', type=Path)
    args = p.parse_args()
    from src.benchmark.scoring_local import score_run
    print({'metric_groups': len(score_run(args.run_dir, args.reviews)), 'output': str(args.run_dir)})
    return 0
