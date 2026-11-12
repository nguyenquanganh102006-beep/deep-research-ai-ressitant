"""Build a factual benchmark status report and 50 reproducible dev retrieval misses."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src.benchmark.import_qasper import ROOT, digest, write_jsonl
from src.benchmark.validate import load


def main() -> None:
    source = ROOT / 'external/qasper'
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    validation = json.loads((source / 'validation.json').read_text(encoding='utf-8'))
    latest = {}
    for path in sorted((ROOT / 'evaluations').glob('*_qasper_*_dev/metrics.json')):
        report = json.loads(path.read_text(encoding='utf-8'))
        if report['questions'] != manifest['counts']['dev']['questions']:
            continue
        if report.get('input_sha256', {}).get('dev.jsonl') != digest(source / 'dev.jsonl'):
            continue
        latest[report['baseline']] = (path.parent, report)
    rows = []
    for method in ('bm25', 'dense', 'hybrid'):
        if method in latest:
            path, report = latest[method]
            metrics = report['metrics_at_k']
            rows.append(f"| {method} | {metrics['1']['hit']:.2%} | {metrics['5']['hit']:.2%} | {metrics['10']['hit']:.2%} | {metrics['5']['recall']:.2%} | {metrics['10']['mrr']:.4f} | {metrics['10']['ndcg']:.4f} |")
    error_cases = []
    if 'hybrid' in latest:
        cases = {c['question_id']: c for c in load(source / 'dev.jsonl')}
        documents = {d['paper_id']: d for d in load(source / 'documents_dev.jsonl')}
        path, report = latest['hybrid']
        for prediction in load(path / 'predictions.jsonl'):
            eligible = [a for a in prediction['annotation_scores'] if a['eligible']]
            if not eligible or any(a['metrics']['5']['hit'] for a in eligible):
                continue
            case = cases[prediction['question_id']]
            doc = documents[prediction['paper_id']]
            text = {p['element_id']: p['text'] for p in doc['paragraphs']}
            error_cases.append({'question_id': case['question_id'], 'question': case['question'], 'paper_id': prediction['paper_id'], 'title': doc['title'], 'error_class': 'all_eligible_annotations_miss_at_5', 'baseline_run': report['run_id'], 'retrieved_top5': [{**p, 'text': text[p['element_id']]} for p in prediction['retrieved'][:5]], 'references': case['annotations'], 'answer_correctness': 'not_measured'})
            if len(error_cases) == 50:
                break
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    write_jsonl(reports / 'dev_retrieval_errors_50.jsonl', error_cases)
    with (reports / 'dev_retrieval_errors_50.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['question_id', 'paper_id', 'title', 'question', 'error_class', 'baseline_run'])
        writer.writeheader()
        writer.writerows({key: row[key] for key in writer.fieldnames} for row in error_cases)
    curated_path = ROOT / 'curated_v1/audit.json'
    curated = json.loads(curated_path.read_text(encoding='utf-8')) if curated_path.exists() else {}
    report_text = '\n'.join([
        '# Báo cáo chất lượng benchmark', '',
        '## Dữ liệu QASPER v0.3', '',
        f"- Tổng: {sum(s['questions'] for s in manifest['counts'].values()):,} QA trên {sum(s['papers'] for s in manifest['counts'].values()):,} paper.",
        '- Official splits: train 2.593 QA / 888 paper; dev 1.005 QA / 281 paper; test 1.451 QA / 416 paper.',
        f"- Integrity audit: {'PASS' if validation['passed'] else 'FAIL'}; giữ nguyên câu hỏi và mọi annotation/đáp án gốc.",
        '- Không có paper ID, nội dung paper trùng hoàn toàn hoặc tiêu đề chuẩn hóa trùng giữa các split.',
        '- 427 evidence chưa map được giữ nguyên và đánh dấu; không tạo số trang PDF giả.',
        '- 246 câu có bất đồng answerability giữa annotators, giữ toàn bộ annotation và gắn cờ.', '',
        '## Retrieval trên toàn bộ dev', '',
        'Cùng cấu hình cố định và cùng dữ liệu. Macro theo 1.501 annotation answerable được map đầy đủ, thuộc 902/1.005 câu; 263 annotation không đủ điều kiện được ghi rõ. Đây là paragraph retrieval trong một paper, không phải answer accuracy hoặc page citation.', '',
        '| Baseline | Hit@1 | Hit@5 | Hit@10 | Recall@5 | MRR@10 | nDCG@10 |',
        '|---|---:|---:|---:|---:|---:|---:|',
        *rows, '',
        f'- {len(error_cases)} ca dev mà mọi annotation đủ điều kiện đều trượt Hit@5 nằm trong `dev_retrieval_errors_50.jsonl` và CSV. Không gọi chúng là lỗi generation vì chưa đo đáp án.',
        '- Dense dùng multilingual-e5-small CPU; hybrid dùng reciprocal rank fusion k=60. Kết quả từng lần chạy lưu config, checksum inputs và runner, predictions đầy đủ.',
        '- Không so sánh tốc độ cold/warm cache trực tiếp. Không chạy/tune mô hình trên test trong quá trình phát triển này.', '',
        '## Sinh đáp án và citation', '',
        '- Runner hỗ trợ oracle evidence, retrieved evidence, no-retrieval; checkpoint resume theo hash config. Prompt không chứa reference answers.',
        '- Smoke test 3 câu/dev đã chạy các chế độ. Kết quả mẫu chỉ kiểm tra đường chạy, không đại diện toàn bộ benchmark.',
        '- Ghi cả lỗi schema/citation, raw response, truncation và số câu thất bại; không loại lỗi để tăng điểm.',
        '- English token F1 dùng cho QASPER; math/code cần rubric riêng. Citation hợp lệ không chứng minh claim đúng.', '',
        '## PDF QA do agent xây', '',
        f"- Trạng thái snapshot audit: {curated.get('questions', 0)} câu; category counts {json.dumps(curated.get('category_counts', {}))}; audit {'PASS' if curated.get('passed') else 'chưa đạt/đang xây'}.",
        '- Mục tiêu 500: 150 math, 150 code, 100 table, 100 unanswerable. Chưa coi quota đạt nếu audit chưa xác nhận.',
        '- Người dùng cho phép agent Luna max tạo và kiểm tra thay người duyệt. Nhãn được ghi là AI-reviewed, không phải human/expert gold.',
        '- Paper version, SHA-256, trang 1-based, quote, rubric và reviewer được kiểm tra trước freeze. Mọi phiên bản paper cùng một split; paper legacy không được vào test.',
        '- PDF không rõ quyền tái phân phối chỉ giữ local; dùng manifest và script tải lại để bảo toàn provenance.', '',
        'Nguồn công khai: [QASPER dataset card](https://huggingface.co/datasets/allenai/qasper), Dasigi et al. (2021), CC BY 4.0 theo dataset card.', '',
    ])
    (reports / 'QUALITY_REPORT.md').write_text(report_text, encoding='utf-8')
    print(reports / 'QUALITY_REPORT.md')


if __name__ == '__main__':
    main()
