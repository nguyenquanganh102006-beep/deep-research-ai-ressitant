# Tiến độ benchmark local LLM

Cập nhật: 2026-11-12T23:08+07:00. Đây là kết quả foundation/framework smoke, chưa phải leaderboard chất lượng nhiều LLM.

## Task và gate

| Task | Trạng thái | Bằng chứng |
|---|---|---|
| 1. Foundation | PASS integrity/API; snapshot tài nguyên có guard | Baseline sanity `44be0c4`; dev 120 câu/12 PDF, 133 evidence khớp sidecar SHA; Adam/Flash smoke từ commit mới đều exit 0 |
| 2. Config/adapter | Có bản đầu | Registry 32 tag (23 A/9 B), runtime mới có Qwen 2B/4B; digest/quant/capability/think/context và lỗi được log |
| 3. Evidence | Có packet và gate review | 120 gold packets: 2 có receipt AI, 118 unverified; 2 packet RAG đóng băng và vision dẫn xuất từ đúng packet text |
| 4. Runner | Smoke trước commit PASS | Acceptance tại `a772079`: Gold 4/4 và RAG 4/4 completed; mỗi track resume tạo 0 dòng mới. Bản bổ sung log retry được regression và smoke riêng sau commit |
| 5. Scoring/report | Có auto metrics và blind review | Correctness/citation support giữ null; CSV, report, template đã sinh; chưa có rubric score/paired quality/Pareto để chọn winner |
| 6–8. Screening/full dev/final test | Chưa chạy | Không dùng test frozen; chưa chọn finalist hoặc model thắng |

Regression hiện tại: **53 tests PASS** (36 cũ + 17 benchmark mới), log `data/benchmark/local_llm_runs/foundation_stable_v1/regression.log`. Test 120 case dùng mock, không được xem là 120 lượt model thật.

## Snapshot và phạm vi

- Python 3.11.9 trong `.venv-sanity311`, Ollama 0.40.16, RTX 4050 Laptop 6GB / driver 536.52.
- Dev: Math 40, Code 27, Table 31, Negative 22; SHA `d2482ab73c5068b078e6cdef2b40136d7e0bba4a62446d8024f7f74c461b14ff`.
- Đã khóa `configs/benchmark/dev_screen12.json`: 3 câu/category, 11 paper, 3 easy/6 medium/3 hard, 10 VI/2 EN. Math trong sample đều medium; không đổi sample theo output.
- Hai ID smoke `math-0064`, `code-0065` đã chọn trước generation, là subset của screen12.
- Config dùng JSON thay YAML để không cần thêm dependency; protocol: context 4096, output512, temperature0, seed42, prompt chung. Seed không đảm bảo deterministic tuyệt đối.
- UI browser chưa verified được ghi riêng; không chặn benchmark batch headless theo plan.

## Evidence và chống leakage

Quote/page/hash validation không tự xác minh công thức. Đã nhìn toàn trang PDF render cho 2 câu smoke và lưu receipt AI/provenance/image SHA. Quote Math có lỗi extraction dấu căn; bản chép được sửa đúng nguồn trong sidecar evaluation-only, không sửa dataset gốc hoặc nhét reference answer vào packet.

Gold packets chỉ eligible khi receipt khớp source hash và corrected-evidence hash. Model input dùng whitelist question/evidence/pages; reference answer/rubric chỉ nằm trong scorer/review template. Gold text không bị cắt ngầm: quá budget sẽ `context_ineligible`. RAG text có cắt theo budget chung, cùng input hash cho mọi model.

Vision packet copy đúng text packet đã freeze, render tối đa2 trang theo thứ tự retrieval, DPI96. Với câu Code smoke, ảnh là trang7/13 do retrieval chọn, không tự thêm trang gold3. Chưa chạy vision inference hoặc kết luận vision gain. Context có conservative UTF-8 text guard + actual usage; chưa có pretokenizer image-token proof, nên cần chốt thêm trước leaderboard vision.

## Tài nguyên và tính tái lập

Snapshot ban đầu lúc sanity/index chạy chỉ còn ~0,4GiB RAM; sau các process kết thúc, snapshot ổn định qua gate2GiB. Không được dùng snapshot ban đầu để tuyên bố đủ tài nguyên. Protocol chặn model load dưới2GiB available và chặn request dưới0,5GiB; disk phải còn30GiB, model download budget40GiB. Không xóa model hoặc đóng app khác của người dùng.

Runner khóa một runtime chung, chạy model/request tuần tự, warm-up riêng, unload khi xong; model digest, packet, prompt, protocol, code, Git SHA và phần cứng được khóa cho resume. Đổi đầu vào/code/model phải tạo run mới. Retry chỉ kỹ thuật; lịch sử attempt giữ lại, scorer dùng attempt cuối và không nhân đôi mẫu hoàn tất.

Preflight hiện ghi 32 ứng viên nhưng chỉ2 installed, không gọi đó là32 model đã smoke. Pull policy bản đầu chỉ batch6 model khởi đầu, tải tuần tự có kiểm size/disk; chưa pull thêm trong lượt foundation.

## File và artifact

Code mới: `local_common.py`, `local_llm_adapter.py`, `evidence_packets.py`, `runner_local.py`, `scoring_local.py`, `local_cli.py` dưới `src/benchmark/`; 5 CLI wrappers dưới `scripts/`; test `tests/test_local_benchmark.py`. Runner `run_pdf.py` và `run_qasper.py` giữ nguyên.

Artifact local, không commit:

- `data/benchmark/local_llm_runs/foundation_v1/`: snapshot đầu, dev validation, Adam/Flash smoke.
- `data/benchmark/local_llm_runs/foundation_stable_v1/`: snapshot resource gate và regression cuối.
- `data/benchmark/local_llm_runs/framework_smoke_v1/`: run phát triển 4 outputs, resume0, CSV/report/review template. Source hashes của run này khác code sau hardening; không tiếp tục vào cùng run ID.
- `data/benchmark/local_llm_packets/`: gold packets, receipt/ảnh review, frozen retrieval text/vision và manifest.

## Acceptance thực đã chạy

Tại baseline framework `a772079`, Gold và Fixed-RAG mỗi track chạy Qwen 2B Q8_0 / Qwen 4B Q4_K_M trên cùng 2 ID: 8/8 output completed, cùng input hash theo question ID, mọi CLI/score/resume exit 0, resume tạo 0 dòng mới. Mỗi track có 2 output thiếu citation và 1 output chạm giới hạn 512 token; giữ nguyên và flag, không sửa prompt riêng. GPU placement của các lượt đã quan sát là GPU-only ở context 4096. Không suy ra model thắng từ 8 output này hoặc trộn tác động size với quantization.

Artifacts: `framework_acceptance_gold_v1/`, `framework_acceptance_rag_v1/`, `framework_acceptance_status.json` dưới `data/benchmark/local_llm_runs/`. Scoring và template đã xuất; correctness vẫn null. Bổ sung sau acceptance: log mọi transient retry, giữ số failed attempts và total wall time để không che lỗi sau retry thành công; regression 53 pass. Acceptance cuối cho logging baseline dùng `framework_final_gold_v1/`.

## Chạy acceptance từ code đã khóa

```powershell
.\.venv-sanity311\Scripts\python.exe scripts/benchmark_local_llms.py --packets data/benchmark/local_llm_packets/gold_smoke2_verified_v1.jsonl --models qwen3.5:2b qwen3.5:4b --run-dir data/benchmark/local_llm_runs/framework_acceptance_gold_v1
# Sau đó chạy lại đúng lệnh với --resume: phải tạo 0 dòng mới
.\.venv-sanity311\Scripts\python.exe scripts/score_benchmark.py --run-dir data/benchmark/local_llm_runs/framework_acceptance_gold_v1
```

Bước tiếp theo: review 10 câu còn lại trong screen12, hoàn thiện model discovery/batch đầu và rubric review; chỉ khi đó mới chạy matrix screening. Chưa đủ căn cứ chọn default/math/code/vision specialist. Full120 dev và268 frozen chưa chạy.

API tham chiếu: [Ollama chat](https://docs.ollama.com/api/chat), [model list](https://docs.ollama.com/api/tags), [running model metadata](https://docs.ollama.com/api/ps). Capability được lấy từ `/api/show` thực tế trên bản Ollama cài local; lỗi docs URL show đã gặp404 khi tra cứu, không dùng làm bằng chứng capability.
