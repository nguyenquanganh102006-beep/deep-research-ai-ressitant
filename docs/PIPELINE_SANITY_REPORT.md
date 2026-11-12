# Báo cáo kiểm tra pipeline MVP

Ngày kiểm tra: 12/11/2026 22:03, Asia/Saigon. Baseline Git: `25180cb96b1722b1e227c83a8ff760676ab3cfc7` cộng thay đổi local trong lượt sanity; chưa tạo commit baseline mới. Hash code thực thi được lưu tại `data/pipeline_sanity/execution_code_hashes.json`.

**Kết luận: các gate tự động đạt có cảnh báo; kiểm tra browser/native UI bị chặn do thiếu kết nối. Chưa gắn nhãn “Pipeline Ready for Benchmark” hoặc freeze `pipeline_baseline_v1`.**

## Môi trường

- Python 3.11.9 tại `.venv-sanity311/`; tạo riêng, không thay venv Python 3.10.11 cũ. `pip check`: không có dependency bị hỏng.
- RTX 4050 Laptop 6 GB, driver 536.52; khác RTX 2060 ghi trong plan cũ.
- Ollama 0.40.16; `qwen3.5:2b`, model ID `0689d44085e0`, Q8_0, hỗ trợ vision. `num_ctx=4096`, `num_predict=220`, temperature 0.15, `think=False`.
- torch 2.15.0+cpu, streamlit 1.67.0, pymupdf4llm 0.3.4, pymupdf 1.28.2, sentence-transformers 5.7.0, transformers 5.22.2, numpy 2.4.6, ollama 0.6.3.
- Toàn bộ artifacts sanity ở `data/pipeline_sanity/`, được Git ignore. Run 3.11 nằm riêng trong `py311/`; dữ liệu benchmark/corpus khác được giữ nguyên.

## Kết quả gate

| Gate | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| 0. Môi trường | PASS | Python 3.11.9, model tải thành công, pip check đạt; package freeze ở `environment311.txt` |
| 1. Tests | PASS | 36 tests, 0 FAIL/ERROR; `unit311.log`; gồm 10 regression sanity mới |
| 2. Ollama độc lập | PASS | Math/code đều trả lời; smoke 3.11 warm 0,57s/0,56s, VRAM sau ~2940 MiB, 100% GPU; `ollama311.log`. Lượt cold sơ bộ 3.10 là 23,18s/0,63s, không so trực tiếp |
| 3. Ingestion/index | PASS tự động; browser BLOCKED | Hai PDF đúng 15/34 trang, vector float32 hữu hạn và chuẩn hóa, chunk/page mapping hợp lệ; lần lặp dùng cache. Upload handler, preview/reload đã kiểm qua AppTest; browser thật chưa kiểm |
| 4. Retrieval-only | PASS | 30 câu fixture hoàn tất; 26 câu có page ground truth; JSON evaluator và console log được lưu |
| 5. E2E | PASS luồng API/headless có cảnh báo; browser BLOCKED | 30/30 câu không rỗng, 0 citation ngoài context, 17 câu thiếu citation được cảnh báo. AppTest chạy 6 câu text/math/code và lỗi rồi phục hồi |
| 6. Lỗi/phục hồi | PASS tự động | Fake/empty PDF, >50 MB, >50 trang, encrypted PDF; cache corrupt/mismatch; parser failure rồi retry; endpoint timeout/model 404; UI index dở/hỏng và QA recovery |

## Kết quả từng PDF — run standalone E2E Python 3.11

| PDF | Trang | Chunks × vector dim | Parser warnings | Hit@5 có GT | Answer không rỗng | Thiếu citation | Citation ngoài context |
|---|---:|---:|---:|---:|---:|---:|---:|
| flashattention-2205.14135v2.pdf | 34 | 76 × 384 | 8 | 12/13 | 15/15 | 8 | 0 |
| adam-1412.6980v9.pdf | 15 | 39 × 384 | 9 | 13/13 | 15/15 | 9 | 0 |

Adam SHA-256: `eab9c73ae2ceda884b94830bda99312254bac4806f6c9f045cbab90721ecda31`.
FlashAttention SHA-256: `ca7f9fda10b90fc05dd291a3accc85e9c1a4a860b99b31928dab03ed3fcb14e4`.

Metadata cả hai có trạng thái `warning`, không bị che cảnh báo. Mỗi thư mục paper chứa PDF, pages, Markdown, chunks, vectors, metadata, `retrieval_log.jsonl`, `qa_log.jsonl`, `sanity_report.json` và evaluations. Những câu thiếu page ground truth không được tính vào mẫu số Hit@5. Các câu fixture đã dùng trước đây để thử prompt; kết quả này chỉ là sanity, không phải held-out score.

Cần phân biệt `retrieved_pages`, `visual_evidence_pages` và `evidence_pages`: renderer có thể chọn trang ảnh theo anchor câu hỏi. Citation được so với nguồn thực sự gửi vào model; không suy từ trang ảnh đúng rằng retrieval đã thành công. Chưa chấm correctness/claim support bằng chuyên gia. Các run generation/API/AppTest có lúc chồng lấp nên không dùng latency ở đây để so hiệu năng model.

Evaluator CLI `src.evaluate` đã chạy retrieval-only và `--answer` cho cả hai PDF: mọi tiến trình exit 0, 30 output generation không rỗng, 0 lỗi kỹ thuật và 0 citation ngoài context. Run CLI riêng có 10/30 output thiếu citation (Adam 5, FlashAttention 5), đều cảnh báo; không gộp với 17/30 của run standalone. JSON trong `py311/papers/<sha>/evaluations/`; mã thoát ở `evaluator311_exit_codes.json` và log Adam generation riêng `adam_evaluator311.log`.

Các ca cache/parser lỗi, index dở và UI endpoint lỗi được mô phỏng trong fixture/mock cô lập; endpoint timeout và model 404 đã gọi thực. Upload handler AppTest dùng fixture inject, không thay thế browser file chooser. `ui311.json` ghi 6 ca QA thực và recovery; `ui_upload311.json` ghi handler/cache/artifact cho cả hai PDF.

## Các sửa P0/P1

- Cache kiểm fingerprint parser/package/chunk config và embedding model/revision/library/prefix; kiểm SHA PDF, page/chunk IDs/ranges, vector shape/dtype/norm/finiteness; cache cũ hoặc hỏng được rebuild khi upload lại.
- Encoder output và retrieval từ chối vector sai; query dimension mismatch có thông báo rõ.
- Readiness trả thất bại khi model tag thiếu. Output LLM rỗng trở thành lỗi rõ.
- UI dừng có thông báo khi index đang dở hoặc thiếu/hỏng, thay vì đọc artifact gây crash.
- Log trang retrieval và ảnh riêng; citation kiểm theo context thực. Evaluator phân loại retrieval/visual/generation error và trả exit code khác 0 khi có lỗi kỹ thuật.
- Bổ sung `tests/test_pipeline_sanity.py` và `scripts/smoke_e2e.py`.

## Hạn chế và việc còn lại

Native Computer Use báo `native pipe unavailable`; browser inventory rỗng. Opera connector yêu cầu reauthentication. Vì vậy thao tác upload bằng browser, bố cục preview/ảnh trên màn hình, và reload bằng browser chưa được xác nhận. AppTest là bằng chứng headless, không thay thế các bước này.

17/30 output của run E2E 3.11 thiếu citation đúng mẫu; checker đều cảnh báo. Một số đáp án có thể sai hoặc thiếu ý; chưa chấm rubric và chưa sửa prompt/ranking để tối ưu điểm. Run sơ bộ 3.10 có kết quả khác và không được trộn với baseline 3.11. Gate UI phải hoàn tất sau khi browser kết nối lại rồi mới freeze baseline.

Server sanity đang phục vụ tại `http://127.0.0.1:8502`; health endpoint trả `ok`, dùng Python 3.11, Qwen 2B và dữ liệu sanity riêng.

## Chạy lại

```powershell
$env:DEEPRESEARCH_DATA_DIR = "data/pipeline_sanity/py311"
$env:DEEPRESEARCH_MODEL = "qwen3.5:2b"
$env:HF_HUB_OFFLINE = "1" # Chỉ sau khi embedding đã có cache
.\.venv-sanity311\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.\.venv-sanity311\Scripts\python.exe scripts/smoke_e2e.py --pdf tests/papers/adam-1412.6980v9.pdf --questions tests/adam.questions.json --model qwen3.5:2b --all-answers
.\.venv-sanity311\Scripts\python.exe scripts/smoke_e2e.py --pdf tests/papers/flashattention-2205.14135v2.pdf --questions tests/flashattention.questions.json --model qwen3.5:2b --all-answers
```

Không dùng bộ 500 QA hay test-frozen trong lượt sanity này. Dataset và model weights không được đưa vào Git.
