"""Ollama adapter with explicit capability/digest/error handling."""
from __future__ import annotations

import base64
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import OLLAMA_HOST
from src.benchmark.local_common import file_hash


class ModelError(RuntimeError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


class OllamaAdapter:
    def __init__(self, host=OLLAMA_HOST, timeout=180, session=None):
        address = urlparse(host)
        if address.scheme not in {'http', 'https'} or address.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('Local benchmark requires a loopback Ollama endpoint')
        self.host = host.rstrip('/')
        self.timeout = timeout
        self.session = session or requests.Session()
        if session is None:
            self.session.trust_env = False

    def request(self, method, endpoint, payload=None, timeout=None):
        try:
            response = self.session.request(method, self.host + endpoint, json=payload,
                                            timeout=timeout or self.timeout)
            if response.status_code >= 400:
                detail = response.text
                lowered = detail.lower()
                status = ('model_not_found' if response.status_code == 404 else
                          'oom' if any(w in lowered for w in ('out of memory', 'not enough memory', 'cuda error')) else
                          'unsupported_protocol' if any(w in lowered for w in ('does not support', 'unsupported', 'think')) else
                          'runtime_error')
                raise ModelError(status, detail)
            return response.json()
        except requests.Timeout as exc:
            raise ModelError('timeout', str(exc)) from exc
        except requests.RequestException as exc:
            raise ModelError('endpoint_error', str(exc)) from exc

    def installed(self):
        return self.request('GET', '/api/tags').get('models', [])

    def inspect(self, tag):
        item = next((m for m in self.installed() if m.get('name', m.get('model')) == tag), None)
        if item is None:
            raise ModelError('not_installed', tag)
        info = self.request('POST', '/api/show', {'model': tag})
        if not item.get('digest'):
            raise ModelError('unsupported_protocol', 'Missing full model digest')
        capabilities = info.get('capabilities', [])
        thinking = info.get('thinking', {})
        supported = thinking.get('values') if isinstance(thinking, dict) else None
        can_disable = 'thinking' in capabilities and (supported is None or False in supported)
        contexts = [value for key, value in info.get('model_info', {}).items()
                    if key.endswith('.context_length') and isinstance(value, int)]
        return {'model_tag': tag, 'model_digest': item['digest'], 'size': item.get('size'),
                'quantization': info.get('details', {}).get('quantization_level'),
                'capabilities': capabilities, 'vision': 'vision' in capabilities,
                'thinking_mode': 'off_supported' if can_disable else 'native',
                'maximum_context': max(contexts) if contexts else None,
                'thinking_metadata': thinking, 'details': info.get('details'),
                'model_info': info.get('model_info'), 'license': info.get('license')}

    def running(self):
        return self.request('GET', '/api/ps').get('models', [])

    def unload(self, tag):
        return self.request('POST', '/api/generate', {'model': tag, 'keep_alive': 0})

    def chat(self, model, messages, protocol, images=None):
        current = self.inspect(model['model_tag'])
        if current['model_digest'] != model['model_digest']:
            raise ModelError('model_changed', 'Model digest changed during run')
        if model.get('maximum_context') and model['maximum_context'] < protocol['num_ctx']:
            raise ModelError('context_ineligible', 'Model maximum context is below protocol context')
        if images and not model['vision']:
            raise ModelError('not_applicable', 'Text-only model cannot enter vision condition')
        sent = [dict(message) for message in messages]
        if images:
            encoded = []
            for image in images:
                path = Path(image['absolute_path'])
                if file_hash(path) != image['sha256']:
                    raise ModelError('input_changed', 'Image checksum changed')
                encoded.append(base64.b64encode(path.read_bytes()).decode('ascii'))
            sent[-1]['images'] = encoded
        payload = {'model': model['model_tag'], 'messages': sent, 'stream': False,
                   'keep_alive': protocol['keep_alive'],
                   'options': {k: protocol[k] for k in ('num_ctx', 'num_predict', 'temperature', 'seed')}}
        if model['thinking_mode'] == 'off_supported':
            payload['think'] = False
        started = time.perf_counter()
        response = self.request('POST', '/api/chat', payload)
        answer = str(response.get('message', {}).get('content') or '').strip()
        if not answer:
            raise ModelError('empty_output', 'Model returned no answer text')
        return {'answer': answer, 'raw_answer': response.get('message', {}).get('content'),
                'thinking_present': bool(response.get('message', {}).get('thinking')),
                'output_truncated': response.get('done_reason') == 'length',
                'decode_tokens_per_second': response.get('eval_count', 0) * 1e9 / response['eval_duration']
                    if response.get('eval_duration') else None,
                'latency_seconds': round(time.perf_counter() - started, 4),
                **{k: response.get(k) for k in ('done_reason', 'total_duration', 'load_duration',
                    'prompt_eval_count', 'prompt_eval_duration', 'eval_count', 'eval_duration')}}
