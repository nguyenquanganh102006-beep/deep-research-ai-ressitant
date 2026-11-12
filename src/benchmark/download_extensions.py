"""Download pinned upstream benchmark artifacts without executing upstream code."""
import hashlib
import json
import shutil
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2] / 'data/benchmark/external'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fetch(url, path, size=None, sha=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (size is None or path.stat().st_size == size):
        actual = digest(path)
        if sha is None or actual == sha:
            return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': actual, 'url': url}
    part = path.with_name(path.name + '.part')
    for attempt in range(8):
        try:
            offset = part.stat().st_size if part.exists() else 0
            headers = {'Range': f'bytes={offset}-'} if offset else {}
            with requests.get(url, headers=headers, stream=True, timeout=(30, 90)) as response:
                response.raise_for_status()
                append = offset and response.status_code == 206
                if append:
                    assert response.headers['Content-Range'].startswith(f'bytes {offset}-')
                with part.open('ab' if append else 'wb') as output:
                    for block in response.iter_content(4 * 1024 * 1024):
                        if shutil.disk_usage(ROOT).free < 30 * 2**30:
                            raise RuntimeError('Storage guard: less than 30 GiB free')
                        output.write(block)
            assert size is None or part.stat().st_size == size, 'Size mismatch'
            actual = digest(part)
            assert sha is None or actual == sha, 'SHA256 mismatch'
            part.replace(path)
            print(f'DONE {path.relative_to(ROOT)} {path.stat().st_size}', flush=True)
            return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': actual, 'url': url}
        except (requests.RequestException, AssertionError) as exc:
            print(f'RETRY {path.name}: {type(exc).__name__}: {exc}', flush=True)
            if attempt == 7:
                raise
            time.sleep(min(2**attempt, 30))


def hf(repo, folder, prefix=None):
    info = requests.get(f'https://huggingface.co/api/datasets/{repo}', timeout=45)
    info.raise_for_status()
    revision = info.json()['sha']
    response = requests.get(f'https://huggingface.co/api/datasets/{repo}/tree/{revision}?recursive=true&limit=1000', timeout=45)
    response.raise_for_status()
    entries = [item for item in response.json() if item['type'] == 'file' and (prefix is None or item['path'].startswith(prefix) or item['path'] in ('README.md', 'LICENSE', '.gitattributes'))]
    remaining = sum(item['size'] for item in entries)
    assert remaining < 40 * 2**30, 'Unexpected upstream expansion'
    files = []
    for item in sorted(entries, key=lambda item: item['size']):
        files.append(fetch(f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{item['path']}", ROOT / folder / 'raw' / item['path'], item['size'], item.get('lfs', {}).get('oid')))
        manifest = {'source': repo, 'revision': revision, 'fetched_at': datetime.now(timezone.utc).isoformat(), 'complete': len(files) == len(entries), 'files': files}
        target = ROOT / folder / 'manifest.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        temporary.replace(target)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    hf('futurehouse/lab-bench', 'litqa2', 'LitQA2/')
    hf('SciCode1/SciCode', 'scicode')
    commit = requests.get('https://api.github.com/repos/scicode-bench/SciCode/commits/main', timeout=45).json()['sha']
    entry = fetch(f'https://codeload.github.com/scicode-bench/SciCode/zip/{commit}', ROOT / 'scicode' / 'source.zip')
    with zipfile.ZipFile(ROOT / 'scicode/source.zip') as archive:
        assert archive.testzip() is None
    (ROOT / 'scicode/source_manifest.json').write_text(json.dumps({'commit': commit, 'file': entry, 'executed': False}, indent=2), encoding='utf-8')
    print('ALL DOWNLOADS COMPLETE', flush=True)


if __name__ == '__main__':
    main()
