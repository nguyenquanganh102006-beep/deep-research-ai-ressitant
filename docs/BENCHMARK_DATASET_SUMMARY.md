# Tổng hợp dataset benchmark

**Bản tổng hợp lập ngày 23/10/2026; trạng thái file SciCode được đối chiếu lại ngày 12/11/2026 — Asia/Saigon.** Các đường dẫn dữ liệu bên dưới tính từ project root `deep-research-ai-ressitant/`. Đây là bản tổng hợp dữ liệu và hướng dẫn sử dụng, không phải báo cáo điểm model.

## 1. Tổng quan và trạng thái

| Bộ dữ liệu | Quy mô local đã kiểm tra | Mục đích | Trạng thái |
|---|---|---|---|
| QASPER v0.3 | 5.049 QA / 1.585 paper | Paper text QA, paragraph evidence retrieval | Đã nhập, giữ annotation và split gốc; validation đạt |
| PDF QA `curated_v1` | 500 QA / 46 PDF | Math, algorithm/code, bảng, abstention, citation theo trang | Đã freeze; audit đạt; AI-reviewed |
| LitQA2 / LAB-Bench | 199 QA công khai | Literature retrieval và science QA | Đã tải đủ subset và kiểm checksum; chưa tích hợp runner |
| SciCode | 80 bài chính: 15 dev + 65 test; 341 `sub_steps` trong snapshot | Scientific code generation | Đề và source harness đã tải; file kiểm thử số chưa hoàn tất |
| SPIQA | Không sử dụng | — | Đã bỏ theo yêu cầu; thư mục local không còn tại lần kiểm tra này |

**Hai track chính đã chốt có 5.549 QA**, tương ứng 1.630 nhóm paper duy nhất. Có paper chung giữa hai track, nhưng không có nhóm paper bị chia sang nhiều split. Con số này không cộng LitQA2 hoặc SciCode. LitQA2 là nguồn bổ sung 199 QA; SciCode đếm theo bài chính/subproblem, không cộng thành một tổng QA chung hoặc gộp điểm với các track khác.

Manifest chính [dataset_manifest.json](../data/benchmark/dataset_manifest.json) chỉ mô tả hai track đã freeze. Nguồn bổ sung có manifest riêng. Không xem trường `complete: true` trong manifest đề SciCode là bằng chứng toàn bộ bộ kiểm thử SciCode đã sẵn sàng.

## 2. QASPER — paragraph-level paper QA

**Nguồn:** [allenai/qasper](https://huggingface.co/datasets/allenai/qasper), Dasigi et al., 2021. License theo dataset card: **CC BY 4.0**.

| Split chính thức | QA | Paper |
|---|---:|---:|
| Train | 2.593 | 888 |
| Dev | 1.005 | 281 |
| Test | 1.451 | 416 |
| Tổng | 5.049 | 1.585 |

- Paper NLP tiếng Anh; giữ câu hỏi, mọi annotation, đáp án và evidence gốc. Không chọn riêng annotation thuận lợi cho model.
- `answerable: null` ở cấp tổng hợp thể hiện bất đồng annotator; không đổi thành câu unanswerable. Có 246 câu bất đồng trong dữ liệu đã nhập.
- Evidence gắn với đoạn/element/section; **không có ground truth trang PDF**. `page` và `pdf_sha256` để null, không tự suy ra.
- 427 evidence chưa ghép được element được giữ nguyên và đánh dấu `unmapped`: train 142, dev 77, test 208. Đây là số evidence, không phải số câu bị loại.
- Marker `FLOAT SELECTED:` chỉ được bỏ khi đối chiếu caption; quote nguồn vẫn giữ. Baseline hiện chỉ tính retrieval trên annotation answerable có mapping evidence đầy đủ; phải báo mẫu số và số loại trừ.

**File dùng trực tiếp:**

| Đường dẫn dưới `data/benchmark/external/qasper/` | Nội dung |
|---|---|
| `train.jsonl`, `dev.jsonl`, `test.jsonl` | Nhãn QA và toàn bộ annotations cho evaluator |
| `documents_train.jsonl`, `documents_dev.jsonl`, `documents_test.jsonl` | Nội dung paper làm đầu vào retrieval; không chứa nhãn QA |
| `raw/` | Archive và JSON upstream gốc |
| `manifest.json` | Nguồn, số lượng, checksum |
| `validation.json` | Kiểm tra bảo toàn nguồn, split, ID, evidence mapping, checksum |

Chỉ index các file `documents_*.jsonl`; không index file nhãn QA. Runner hiện là single-paper open-book paragraph retrieval, chưa phải tìm paper trên toàn kho. Hit/Recall/MRR/nDCG của runner không phải official QASPER answer F1 và không đo citation theo trang.

## 3. PDF QA tự xây — `curated_v1`

**Phiên bản:** `1.0-ai-reviewed`. **Nguồn nhãn:** AI tạo và đối chiếu PDF; agent Luna max và agent điều phối có provenance riêng. **Không phải human-reviewed/expert gold.** Việc thay người duyệt bằng agent đã được người dùng cho phép; không xem đó là hoàn tất gate human review trong plan.

### Quy mô và split

| Category | Train | Dev | Test khóa | Tổng |
|---|---:|---:|---:|---:|
| Math/equation | 20 | 40 | 90 | 150 |
| Code/algorithm | 57 | 27 | 66 | 150 |
| Table/result | 11 | 31 | 58 | 100 |
| Unanswerable/ambiguous | 24 | 22 | 54 | 100 |
| Tổng | 112 | 120 | 268 | 500 |

46 PDF được cố định phiên bản/hash. Ngôn ngữ câu hỏi/đáp án: **380 tiếng Việt, 120 tiếng Anh**; paper nguồn chủ yếu tiếng Anh, tập trung ML và các phương pháp nổi tiếng. Không đại diện toàn bộ khoa học, PDF scan/OCR hoặc repository code.

### Nhãn và evidence

| Trường/nhóm trường | Ý nghĩa |
|---|---|
| `question_id`, `dataset_source`, `dataset_version`, `track`, `split` | Định danh và phiên bản đánh giá |
| `paper_ids` | Đúng paper/version được dùng |
| `category`, `subtype`, `difficulty`, `language` | Nhóm năng lực, dạng câu, độ khó, ngôn ngữ |
| `question`, `reference_answer`, `answerable` | Câu hỏi, đáp án tham chiếu, khả năng trả lời |
| `evidence[]` | Paper ID, SHA-256 PDF, trang PDF **1-based**, section/element, quote nguyên văn |
| `expected_reasoning_checks` | Rubric các ý cần kiểm tra; không thay bằng so khớp chuỗi đơn thuần |
| `review_status`, `reviewer_id`, provenance/thời gian | Lịch sử AI review và giới hạn xác minh |
| `absence_review` khi áp dụng | Phạm vi/từ khóa/phương pháp kiểm thông tin thiếu hoặc mơ hồ |
| `latex_reference`, metadata phụ khi có | Biểu diễn hỗ trợ; không mặc định là LaTeX do chuyên gia xác nhận |
| `source_page_text_path`, `source_page_text_sha256` trong evidence | Sidecar nguồn và checksum để tái kiểm tra |

Math kiểm công thức, ký hiệu, giả định và suy luận. Code kiểm pseudocode/thuật toán trong paper, **không chứng minh implementation chạy đúng**. Table kiểm hàng/cột, metric, đơn vị và protocol. Negative gồm thiếu thông tin hoặc nhiều setting khiến không có một đáp án duy nhất. Tiền đề sai nhưng sửa được bằng nguồn vẫn là answerable; thiếu thông tin không đồng nghĩa giá trị bằng 0.

### Review và kiểm định

- 500 câu có primary AI source review. **128/500 câu (25,6%)** có AI khác tác giả kiểm tra độc lập: 50 math, 38 code, 23 table, 17 negative.
- Receipt hiện hành đều pass, không stale/unresolved. Đây là mẫu kiểm tra có chủ đích, không phải mẫu ngẫu nhiên để ước lượng tỷ lệ lỗi toàn dataset.
- Kiểm schema, ID/câu hỏi trùng, hash/version PDF, số trang, quote khớp text đúng trang sau NFKC + bỏ whitespace **giữ phân biệt hoa/thường**; các kiểm tra này không tự bảo đảm mọi suy luận đều đúng.
- Có **210 text sidecar trang nguồn**, checksum byte đã đối chiếu. Text sidecar không thay ảnh PDF khi kiểm công thức hoặc bảng.
- Snapshot annotation khớp staging đã ký. Sự cố ghi file trong curation đã phục hồi đủ và kiểm lại trước freeze; lịch sử nằm trong [AGENT_LOG.md](AGENT_LOG.md).

### File dùng trực tiếp

Tất cả dưới `data/benchmark/curated_v1/`:

| File/thư mục | Vai trò |
|---|---|
| `train.jsonl`, `dev.jsonl`, `test_frozen.jsonl` | Bộ QA phát hành; dùng các file này để benchmark |
| `papers.jsonl` | URL nguồn, version, đường dẫn local PDF và SHA-256 |
| `source_pages/` | Text sidecar của trang evidence |
| `annotations.reviewed.jsonl` | Snapshot annotation gốc để đối chiếu fingerprint receipt |
| `reviews/*_cross_review.jsonl`, `reviews/coverage.json` | Receipt và độ phủ độc lập còn hiệu lực |
| `audit.json` | Audit frozen và SHA-256 file phát hành/receipt |
| `audit_latest.json` nếu có | Kết quả tái kiểm tra sau freeze, không thay audit phát hành |
| `staging/` | Nguồn curation, không dùng thay split phát hành |
| `DATASET_CARD.md` | Chi tiết provenance, phương pháp, giới hạn |

PDF gốc có thể nằm trong `papers/` hoặc `staging/papers/`; lấy đường dẫn thực từ `papers.jsonl`. Chưa xác lập quyền phân phối lại toàn bộ PDF, nên giữ local và lưu URL/version/hash; trước công bố cần xem quyền PDF/trích đoạn.

`data/benchmark/gold_v1/` là **30 câu legacy Adam/FlashAttention**, đã dùng thử prompt và giữ dev; không cộng thêm vào 500 câu phát hành, không gọi là human gold.

## 4. LitQA2 — nguồn bổ sung literature QA

**Nguồn:** [futurehouse/lab-bench](https://huggingface.co/datasets/futurehouse/lab-bench), chỉ tải subset `LitQA2`, không tải bảy subset khác. License: **CC BY-SA 4.0** theo upstream. Revision cố định: `5c77cec648430f30611808808861eb86f81d5eaa`.

- **199 câu** trong public snapshot, ID duy nhất; public release không bao gồm phần private của tác giả.
- Dữ liệu thuộc literature/science QA có thiên hướng biology theo LAB-Bench; báo cáo riêng, không xem là cùng phân phối AI/ML PDF QA.
- Giữ nguyên `id`, `question`, `ideal`, `distractors`, `source`/`sources`, `key-passage`, `tag`, `version`, `is_opensource`, `subtask` và canary upstream.
- File: `data/benchmark/external/litqa2/raw/LitQA2/train-00000-of-00001.parquet`; card/LICENSE trong `raw/`; URL/revision/checksum trong `manifest.json`.
- Tên split upstream là `train`, nhưng giữ nguồn này **chỉ để đánh giá**, không dùng huấn luyện hoặc tune bằng đáp án. Không xóa canary.
- Đã đọc parquet và kiểm checksum. Chưa có runner tích hợp, chưa xác nhận tải paper/evidence ngoài các trường upstream, chưa đo khả năng multi-paper search. Không tự gán PDF page ground truth.

## 5. SciCode — nguồn bổ sung scientific coding

**Nguồn:** [SciCode repository](https://github.com/scicode-bench/SciCode) và [SciCode1/SciCode](https://huggingface.co/datasets/SciCode1/SciCode). License snapshot: **Apache 2.0**. HF revision: `4510f6a6aa27c43fad7b43da2c59602a86e88480`; source harness commit: `e3158ea011d4235245a547460d3688d7ccbf9900`.

- **80 bài chính**, chia **15 dev / 65 test**. Đếm thực tế **341 phần tử `sub_steps`** trong snapshot đã tải; khác số 338 subproblem mô tả trong README upstream. Khi báo cáo ghi rõ revision và cách đếm, không âm thầm sửa dữ liệu để khớp README.
- Nội dung có đề chính, input/output, dependencies, background, substeps và tests; giữ đúng những trường upstream cung cấp, không suy rằng mọi split đều có gold solution.
- Phạm vi nhiều lĩnh vực khoa học; đây là sinh chương trình, khác đọc pseudocode trong PDF. Không gộp pass rate với QA accuracy/retrieval.

| Đường dẫn dưới `data/benchmark/external/scicode/` | Trạng thái |
|---|---|
| `raw/problems_dev.jsonl`, `raw/problems_test.jsonl` | Đã tải, parse và kiểm checksum |
| `manifest.json` | Manifest các file HF đã tải |
| `source.zip`, `source_manifest.json` | Harness upstream đã cố định commit; archive hợp lệ; **chưa thực thi** |
| `test_data.h5` | Đã tải đủ: 1.049.345.865 byte; kích thước và SHA-256 khớp `test_data_manifest.json` |
| `test_data_manifest.json` | URL, kích thước và SHA-256 đã pin của file numeric test |

File numeric test chính thức đã tải đủ **1.049.345.865 byte**; SHA-256 trong manifest khớp file và chữ ký HDF5 hợp lệ. Source harness cũng đã tải đúng checksum và pin theo commit nêu trên. Harness chưa được thực thi, chưa xác nhận sandbox và chưa có pass rate. Khi đánh giá code cần sandbox cô lập, giới hạn tài nguyên và log lỗi; không chạy code sinh ra trực tiếp trong môi trường ứng dụng.

## 6. Quy tắc benchmark và chống leakage

1. Giữ riêng từng nguồn và báo cáo riêng từng task. Không tạo một điểm trung bình chung giữa QASPER, PDF QA, LitQA2 và SciCode.
2. Với hai track chính, split theo nhóm paper/các phiên bản; paper đã có trong QASPER giữ official split. Hai paper legacy đã dùng prompt được giữ dev. Không chia ngẫu nhiên QA cùng paper sang nhiều split.
3. Chỉ index tài liệu nguồn. Không index câu hỏi test, đáp án, rubric, evidence labels hoặc receipt. Oracle evidence là chế độ chẩn đoán có chủ đích, phải ghi riêng.
4. Dùng dev chọn prompt/chunking/retrieval. Chỉ chạy held-out test sau khi chốt cấu hình; không dùng điểm test để lặp tuning. Sửa nhãn sau freeze phải phát hành version mới.
5. Phân biệt single-paper open-book với multi-paper retrieval; paper có sẵn trong index không đồng nghĩa evaluator được phép đưa đáp án vào context.
6. Giữ nguyên bất đồng annotator, unmapped evidence, lỗi parse/retrieval; báo rõ mẫu số và loại trừ, không bỏ âm thầm các ca khó.
7. Review AI và audit tự động không phải xác nhận chuyên gia. Khi dùng làm kết quả nghiên cứu cần công khai provenance và giới hạn nhãn.

## 7. Đo gì và bằng cách nào

| Năng lực | Dữ liệu phù hợp | Metric/đánh giá |
|---|---|---|
| Paragraph retrieval | QASPER | Hit@1/5/10, Recall@K, MRR, nDCG; macro theo annotation answerable mapping đầy đủ |
| Page retrieval/citation | PDF QA | Metric trên trang PDF unique, citation có thực sự hỗ trợ claim; tách theo category |
| Math/algorithm/table QA | PDF QA | Đối chiếu `reference_answer` + rubric + PDF; không chỉ ROUGE/F1 |
| Abstention | 100 PDF negative và annotation QASPER phù hợp | Đúng từ chối/nhận diện ambiguity; kiểm phạm vi nguồn |
| Literature retrieval/QA | LitQA2 | Cần runner riêng theo protocol nguồn; hiện chưa đo |
| Scientific code generation | SciCode | Chỉ báo pass rate sau chạy tests trong sandbox; hiện chưa đo |
| Parser math/code/table | PDF và ảnh trang nguồn | Cần chấm layout/ký hiệu/thụt lề/hàng cột; quote-match không thay parser quality score |

Runner PDF có `oracle` (trang nguồn) và `no_retrieval` để tách lỗi reasoning khỏi retrieval; hai chế độ này không đo retrieval. Đáp án sinh ra vẫn mang trạng thái cần review rubric. Khi báo cáo lưu run ID, dataset/model/version, quantization, prompt/parser/embedding/retrieval config, checksum đầu vào, hardware, latency, lỗi và mẫu số.

## 8. Lệnh sử dụng hiện có

Chạy từ project root trong PowerShell. Các lệnh dưới đây là hướng dẫn; **không chạy thêm benchmark model để viết bản tổng hợp này**.

```powershell
# Kiểm định, không gọi model
.venv\Scripts\python.exe -m src.benchmark.validate
.venv\Scripts\python.exe -m src.benchmark.audit_curated
.venv\Scripts\python.exe data/benchmark/curated_v1/reviews/check_reviews.py
.venv\Scripts\python.exe -m unittest discover -s tests -p test_benchmark.py

# Retrieval dev QASPER
.venv\Scripts\python.exe -m src.benchmark.run_qasper --split dev --method bm25
# Có thể thay bm25 bằng dense hoặc hybrid

# Retrieval dev PDF; bắt đầu ít câu để kiểm môi trường
.venv\Scripts\python.exe -m src.benchmark.run_pdf --split dev --method bm25 --limit 10

# Sinh đáp án dev: cần Ollama/model và review rubric sau chạy
.venv\Scripts\python.exe -m src.benchmark.run_pdf --split dev --method hybrid --answer
```

Không chạy lại `audit_curated --freeze` để thay bộ test đã khóa. Runner PDF dùng split `test` để đọc `test_frozen.jsonl`. `--model` của runner mặc định `qwen3.5:4b`, nhưng cần đối chiếu cấu hình thực của đường gọi generation trước khi công bố model; tên tham số không tự chứng minh model thực chạy. Dense/hybrid có thể cần tải embedding nếu cache chưa có.

Kết quả runner nằm dưới `data/benchmark/evaluations/<run_id>/`; báo cáo tổng hợp hiện có ở [QUALITY_REPORT.md](../data/benchmark/reports/QUALITY_REPORT.md). Điểm cũ chỉ áp dụng cho input/config/checksum của chính lần chạy, không tự coi là đánh giá đủ bộ mới.

## 9. Bằng chứng kiểm định và phần còn lại

| Bằng chứng | Nội dung |
|---|---|
| [Manifest chính](../data/benchmark/dataset_manifest.json) | Quy mô, split và SHA-256 của 5.549 QA hai track chính |
| [QASPER validation](../data/benchmark/external/qasper/validation.json) | Bảo toàn annotation, official split, checksum, mapping |
| [PDF audit frozen](../data/benchmark/curated_v1/audit.json) | 500 QA/46 paper, schema, nguồn, split, checksum |
| [AI review coverage](../data/benchmark/curated_v1/reviews/coverage.json) | 128 receipt còn hiệu lực, 0 stale/unresolved |
| [Extension validation](../data/benchmark/external/extension_validation.json) | Số lượng LitQA2/SciCode đã đọc thực tế |
| Manifest riêng `external/litqa2/` và `external/scicode/` | Revision, URL và checksum nguồn bổ sung |
| [Nhật ký agent](AGENT_LOG.md) | Thao tác, lỗi, phục hồi và các bước chưa hoàn tất |

Đã có kết quả kiểm định hai track chính đạt và 7 test benchmark đạt trong lượt chốt dữ liệu trước đó. Lượt viết tài liệu này đối chiếu lại file thực tế; không coi việc đọc báo cáo cũ là một lần chạy lại toàn bộ tests.

**Phần còn lại:** hoàn tất/kiểm file numeric SciCode, chuẩn bị sandbox và runner nếu benchmark code generation; tích hợp protocol LitQA2 khi đánh giá literature QA; chấm đáp án/citation bằng rubric và mở rộng human/expert review nếu cần kết quả nghiên cứu. Model benchmark và mở rộng production corpus nằm ngoài công việc chốt dataset hiện tại. Không có dữ liệu SPIQA trong phạm vi sử dụng.
