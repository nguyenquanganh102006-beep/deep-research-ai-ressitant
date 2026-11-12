"""Restore pinned local-only benchmark PDFs using manifest hashes and safe paths."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

import pymupdf
import requests

from config import PROJECT_ROOT
from src.benchmark.import_qasper import ROOT, digest
from src.benchmark.validate import load

ALLOWED_HOSTS = {'arxiv.org', 'export.arxiv.org', 'proceedings.neurips.cc', 'papers.nips.cc', 'jmlr.org', 'www.jmlr.org', 'aclanthology.org', 'proceedings.mlr.press', 'openreview.net'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'curated_v1/papers.jsonl')
    args = parser.parse_args()
    session = requests.Session()
    session.headers['User-Agent'] = 'DeepResearchBenchmark/1.0 (local research dataset; sequential downloads)'
    for paper in load(args.manifest):
        path = (PROJECT_ROOT / paper['pdf_path']).resolve()
        if not path.is_relative_to(PROJECT_ROOT.resolve()):
            raise ValueError('Manifest PDF path outside project')
        if path.exists() and digest(path) == paper['pdf_sha256']:
            print(paper['paper_id'], 'cached', flush=True)
            continue
        if path.exists():
            raise ValueError('Existing PDF has different hash; will not overwrite: ' + str(path))
        url = paper.get('download_url') or paper['source_url'].replace('/abs/', '/pdf/')
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError('Unsupported source host: ' + url)
        path.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(path.parent).free < 30 * 1024**3:
            raise RuntimeError('Storage guard: less than 30 GiB free')
        part = path.with_suffix(f'.{os.getpid()}.part')
        error = None
        for attempt in range(3):
            try:
                h = hashlib.sha256()
                with session.get(url, stream=True, timeout=(15, 90)) as response:
                    response.raise_for_status()
                    with part.open('wb') as stream:
                        for chunk in response.iter_content(1024 * 1024):
                            stream.write(chunk)
                            h.update(chunk)
                if h.hexdigest() != paper['pdf_sha256']:
                    raise ValueError('Downloaded PDF hash differs from pinned release')
                with pymupdf.open(part, filetype='pdf') as pdf:
                    if len(pdf) != paper['page_count']:
                        raise ValueError('Downloaded PDF page count differs')
                part.replace(path)
                error = None
                break
            except (requests.RequestException, ValueError, pymupdf.FileDataError) as exc:
                error = exc
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        if error:
            raise RuntimeError(f'{paper["paper_id"]}: {error}')
        print(paper['paper_id'], 'verified', flush=True)
        time.sleep(3)


if __name__ == '__main__':
    main()
