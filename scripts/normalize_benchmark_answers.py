"""Create an analysis-only run view; never rewrite inference artifacts."""
import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.local_common import canonical, file_hash, read_json, read_rows, write_json
from src.benchmark.local_llm_adapter import extract_final_answer
from src.benchmark.scoring_local import citation_metrics


def normalize(source: Path, output: Path):
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError('Use a new analysis directory; source artifacts must stay immutable')
    rows = copy.deepcopy(read_rows(source / 'predictions.jsonl'))
    changed = 0
    for row in rows:
        if row['status'] != 'completed':
            continue
        raw = row.get('raw_answer')
        if raw is None:
            raw = row['answer']
        answer, inline = extract_final_answer(raw)
        if inline:
            changed += 1
            row.update(original_status=row['status'], raw_answer=raw, answer=answer,
                       inline_thinking_present=True, thinking_present=True)
            if not answer:
                row.update(status='empty_output', error='No final answer after inline reasoning')
            row.update(citation_metrics(answer, row.get('allowed_pages', [])))
    output.mkdir(parents=True)
    (output / 'predictions.jsonl').write_bytes(b''.join(canonical(row) + b'\n' for row in rows))
    manifest = read_json(source / 'manifest.json')
    manifest.update(analysis_only=True, derivation={
        'policy': 'final_content_v2; remove only leading inline think blocks; no generation rerun',
        'source_run': str(source.resolve()),
        'source_predictions_sha256': file_hash(source / 'predictions.jsonl'),
        'source_manifest_sha256': file_hash(source / 'manifest.json'),
        'adapter_sha256': file_hash(Path(__file__).resolve().parents[1] / 'src/benchmark/local_llm_adapter.py'),
        'normalizer_sha256': file_hash(Path(__file__)),
        'changed_records': changed})
    write_json(output / 'manifest.json', manifest)
    return {'records': len(rows), 'changed_records': changed, 'analysis_only': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(normalize(args.source_run, args.output))
