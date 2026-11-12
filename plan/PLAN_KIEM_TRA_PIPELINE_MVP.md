# PLAN — Kiểm tra & ổn định pipeline MVP trước khi benchmark LLM

**Dự án:** DeepResearch AI Research Assistant  
**Repository:** https://github.com/nguyenquanganh102006-beep/deep-research-ai-ressitant  
**Baseline kiểm tra:** `main` tại commit `25180cb96b1722b1e227c83a8ff760676ab3cfc7` (12/11/2026)  
**Môi trường mục tiêu:** Windows + RTX 2060 (6 GB), Python 3.11+, Ollama, Streamlit  
**Ưu tiên:** P0 — xác nhận pipeline chạy được, sửa lỗi kỹ thuật nghiêm trọng. **Chưa tối ưu chất lượng.**

---

## 1. Chốt phạm vi

### Mục tiêu

Xác nhận luồng hiện tại hoạt động ổn định:

`PDF → validate/upload → parse → chunk → embedding → lưu index → hybrid retrieval → Ollama/Qwen → câu trả lời + citation`

Sau bước này phải có **một baseline chạy lại được** để các vòng benchmark nhiều LLM tiếp theo dùng chung đầu vào và không bị lỗi hạ tầng làm nhiễu.

### Không làm trong đợt này

- Không fine-tune/đổi LLM chỉ để tăng accuracy; giữ mặc định `qwen3.5:2b` cho smoke test.
- Không thêm agent, planner, reranker, OCR/MER, multi-paper RAG hay web search.
- Không chạy benchmark 500 câu, không dùng test-frozen để tối ưu prompt/model.
- Không cố đạt ngưỡng answer accuracy. Đây là **functional sanity check**, không phải chấm năng lực LLM.
- Không push `data/`, model weights, PDF corpus hoặc dataset local lên GitHub.

### Các file có sẵn để tận dụng

| Phần | Code/fixture hiện có |
|---|---|
| UI và upload | `app.py`, `src/ingest.py`, `src/storage.py` |
| Parser/chunking | `src/parser.py`, `src/chunker.py`, `src/representations.py` |
| Embedding/retrieval | `src/embeddings.py`, `src/retriever.py` |
| LLM/citation | `src/llm.py`, `config.py`, `smoke_test.py` |
| Unit tests | `tests/test_benchmark.py`, `tests/test_catalog.py`, `tests/test_corpus.py`, `tests/test_representations.py` |
| PDF fixture | `tests/papers/adam-1412.6980v9.pdf` (**15 trang**), `tests/papers/flashattention-2205.14135v2.pdf` (**34 trang**) |
| QA fixture | `tests/adam.questions.json`, `tests/flashattention.questions.json` (**15 câu/file**) |
| Evaluator | `src/evaluate.py` |

> **Lưu ý:** `smoke_test.py` hiện chỉ thử Qwen trên prompt math/code. Nó **không** tự kiểm tra ingest → retrieval → answer. Phải bổ sung kiểm tra tích hợp bên dưới.

---

## 2. Trình tự thực hiện nhanh (checklist)

### Gate 0 — Cố định môi trường và phiên bản

- [ ] Ghi lại commit, các thay đổi local, Python, GPU, driver, Ollama và model tag.
- [ ] Cài đủ dependency cho cả app và các unit tests; không sửa môi trường âm thầm khi test lỗi.
- [ ] Xác nhận Ollama đang phục vụ `qwen3.5:2b` trước khi test tích hợp.

Chạy trong PowerShell tại thư mục repo:

```powershell
git status --short
git rev-parse HEAD
python --version
nvidia-smi
ollama list
ollama ps

# Nếu chưa có virtual environment:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt -r requirements-catalog.txt

# Nếu thiếu model:
ollama pull qwen3.5:2b
```

**PASS khi:** môi trường sẵn sàng, model tồn tại, log rõ commit/model/hardware. **FAIL khi:** thiếu dependency, Ollama không kết nối, sai model hoặc lỗi môi trường chưa giải thích được.

### Gate 1 — Chạy unit tests hiện có

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

- [ ] Test collection/import thành công.
- [ ] Không có `ERROR` hoặc `FAIL`.
- [ ] Nếu lỗi: phân loại **thiếu dependency / import / lỗi logic / lỗi fixture**; sửa đúng nguyên nhân, chạy lại.
- [ ] Lưu console output và số test PASS/FAIL vào báo cáo.

**Không cần GPU/Ollama** cho gate này. Nếu test có phụ thuộc mạng hoặc model không chủ đích, phải tách/mock để unit tests ổn định.

### Gate 2 — Kiểm tra Ollama độc lập

```powershell
python smoke_test.py
```

- [ ] Prompt Math trả lời có nội dung, không rỗng.
- [ ] Prompt Code trả lời có nội dung, không rỗng.
- [ ] Không bị exception/timeout/Out-of-Memory.
- [ ] Ghi latency, `ollama ps` và VRAM/RAM (nếu hệ thống cung cấp).

**PASS khi:** cả hai prompt hoàn tất với model được cấu hình. Đây mới chứng minh **LLM endpoint hoạt động**, chưa chứng minh hệ thống RAG đúng.

### Gate 3 — Kiểm tra ingestion từ PDF đến index

Dùng hai file fixture, trước tiên **Adam**, sau đó **FlashAttention**.

```powershell
streamlit run app.py --server.address 127.0.0.1
```

Trong UI: **Thêm PDF → Xử lý tài liệu → Chọn PDF đã lưu → Parser Preview**.

- [ ] Upload PDF hợp lệ thành công; trạng thái `ok` hoặc `warning` có lý do rõ.
- [ ] Số trang Adam = **15**, FlashAttention = **34**.
- [ ] `chunk_count > 0`, có `pages.json`, `parsed.md`, `chunks.json`, `embeddings.npy`, `metadata.json`, `source.pdf` trong `data/papers/<sha256>/`.
- [ ] Chunks chứa `chunk_id`, `page_start/page_end`, `type`, `content`; trang nằm trong `[1, page_count]`.
- [ ] `embeddings.npy` có `shape[0] == len(chunks)`, `shape[1] > 0`, không NaN/Inf; vector gần chuẩn L2 = 1.
- [ ] Parser Preview hiện Markdown và ảnh đúng trang; lưu ý math/code có thể bị parse sai ký hiệu dù không có warning.
- [ ] Upload lại **chính xác cùng file**: dùng lại index, không tạo một bộ dữ liệu mới.

**PASS khi:** tất cả artifact tồn tại và nhất quán; warning được hiển thị, không bị che giấu. **FAIL khi:** crash, mất trang, lệch vector/chunk, index không đọc được, tái-upload hỏng cache.

### Gate 4 — Retrieval độc lập (không gọi Qwen)

Từ file đã ingest, tính SHA-256 và chạy evaluator **không có `--answer`**:

```powershell
$ADAM_ID = (Get-FileHash tests/papers/adam-1412.6980v9.pdf -Algorithm SHA256).Hash.ToLower()
$FLASH_ID = (Get-FileHash tests/papers/flashattention-2205.14135v2.pdf -Algorithm SHA256).Hash.ToLower()

python -m src.evaluate --document-id $ADAM_ID --questions tests/adam.questions.json
python -m src.evaluate --document-id $FLASH_ID --questions tests/flashattention.questions.json
```

- [ ] Không có lỗi đọc index, tính embedding truy vấn hoặc dựng BM25.
- [ ] Mỗi câu trả về danh sách chunk/page hợp lệ; không có page vượt giới hạn PDF.
- [ ] Kết quả có `retrieved_ids`, `retrieved_pages`, `hit_at_5` cho các câu có ground-truth page.
- [ ] Ghi lại Hit@5 **chỉ làm mốc kỹ thuật**; không sửa retriever để chạy theo điểm trong bước này.

**PASS khi:** retrieval hoàn tất, đúng schema, có thể tái chạy mà không lỗi. Hit@5 thấp **không tự động là lỗi kỹ thuật**, mà được đưa vào danh sách cải tiến sau.

### Gate 5 — End-to-end: từ câu hỏi đến câu trả lời

Trong UI đã chạy:

- [ ] Hỏi **1 câu text**, **1 câu math**, **1 câu algorithm/code** trên Adam.
- [ ] Hỏi tương tự trên FlashAttention; có ít nhất một câu yêu cầu nguồn từ ảnh PDF nếu model hỗ trợ visual.
- [ ] Không có exception, câu trả lời không rỗng và được trả về từ Ollama local.
- [ ] Câu có thông tin từ paper có citation đúng mẫu `[Trang N]`.
- [ ] Không có citation dẫn đến trang **ngoài** evidence được cấp cho model.
- [ ] UI hiển thị nguồn và các parser warnings; có `qa_log.jsonl`, `retrieval_log.jsonl`.
- [ ] Sau khi reload app, tài liệu và index vẫn tồn tại; hỏi lại được.

Chạy evaluator có generation để lưu thêm bản ghi kỹ thuật:

```powershell
python -m src.evaluate --document-id $ADAM_ID --questions tests/adam.questions.json --answer
python -m src.evaluate --document-id $FLASH_ID --questions tests/flashattention.questions.json --answer
```

**Quan trọng:** evaluator có thể gắn ảnh trang theo anchor câu hỏi. Khi đọc báo cáo, phân biệt rõ `retrieved_pages` với các trang ảnh thực tế được gửi vào LLM. Citation hợp lệ về số trang **không chứng minh nội dung câu trả lời đúng**.

**PASS khi:** API/pipeline không lỗi, output và log có cấu trúc, nguồn có thể kiểm tra. Những câu sai kiến thức được ghi lại cho benchmark, **không bắt buộc sửa prompt ngay**.

### Gate 6 — Test lỗi đầu vào và khả năng phục hồi

- [ ] File giả `.pdf`/byte không đúng định dạng → bị từ chối với thông báo rõ.
- [ ] PDF rỗng, bị khóa hoặc vượt giới hạn 50 trang/50 MB → báo lỗi thích hợp (có thể dùng fixture bổ sung).
- [ ] Tắt Ollama hoặc dùng tag model không tồn tại → UI báo lỗi rõ, không hiển thị câu trả lời giả.
- [ ] Một lượt QA thất bại không phá index hoặc khiến các câu sau không thể chạy.
- [ ] Không có dataset local nào bị xóa/sửa ngoài những artifact test có chủ đích.

**PASS khi:** hệ thống fail gracefully thay vì crash/mất dữ liệu. Tạm hoãn test tải lớn, concurrency và bảo mật nâng cao sang vòng sau.

---

## 3. Các lỗi kỹ thuật P0/P1 cần rà soát và cách xử lý

| Ưu tiên | Nguy cơ trong code hiện tại | Kiểm tra và hướng sửa tối thiểu |
|---|---|---|
| **P0** | Tái sử dụng embedding cache chỉ dựa vào parser version và sự tồn tại file (`src/ingest.py`) | Kiểm tra thêm embedding model/fingerprint, số chunk, shape, dtype; khác cấu hình thì rebuild an toàn |
| **P0** | `embeddings.npy` hoặc `chunks.json` thiếu/corrupt | Validate artifact khi load; báo lý do, cho phép re-index thay vì lỗi khó hiểu |
| **P0** | Ollama reachable nhưng model tag chưa tồn tại | Kiểm tra model cụ thể trước khi bắt đầu QA, hiển thị lệnh pull/cấu hình rõ |
| **P0** | PDF parse/index lỗi để lại trạng thái dở dang | Đảm bảo `parse_status=error`, log error, retry không phá bản gốc |
| **P1** | Citation checker chỉ so số trang với retrieved context | Trong vòng này ghi `citation_valid_format` và `citation_page_in_context`; **không gọi đó là claim correctness** |
| **P1** | Ảnh trang neo theo câu hỏi có thể khác trang retrieval | Log riêng `retrieved_pages` và `visual_evidence_pages`; không diễn giải đây là retrieval thành công |
| **P1** | Unit tests hiện chưa bao phủ toàn bộ ingest/retrieval/LLM route | Thêm test nhỏ có fixture/mock cho invalid PDF, cache reuse/invalidation, vector alignment và parser/chunker |

**Quy tắc sửa:** chỉ fix lỗi gây crash, sai đường đi dữ liệu, sai mapping, dùng cache sai, lỗi không kiểm soát hoặc log sai. Các lỗi trả lời thiếu/sai do năng lực model, math OCR, ranking thấp hoặc prompt chưa tốt được **ghi nhận**, không tối ưu trong sprint này.

---

## 4. Tự động hóa tối thiểu nên bổ sung

**Không cần xây một test framework mới từ đầu.** Nên bổ sung hai thứ nhỏ:

1. **`tests/test_pipeline_sanity.py`**: unit/integration tests không cần GPU, mock Ollama/embedding khi cần. Bao phủ định dạng PDF, chunk ID/page mapping, vector/chunk alignment, cache reuse/invalidation và xử lý citation.
2. **`scripts/smoke_e2e.py`** (nếu muốn tự động hóa tiếp): nhận `--pdf`, `--question`, `--model`; gọi `ingest_pdf_bytes()` → `retrieve()` → `answer_question()`; xuất JSON gồm commit, model, document ID, số trang/chunks, retrieved pages, cited pages, invalid citations, latency, trạng thái PASS/FAIL. Script này **cần Ollama local**, không đưa vào unit-test CI thông thường.

Ưu tiên viết script E2E sau khi manual UI pass một lần. Không thay đổi kiến trúc sản phẩm để phục vụ test.

---

## 5. Báo cáo bắt buộc sau khi chạy

Tạo **`docs/PIPELINE_SANITY_REPORT.md`** với bảng ngắn:

| Test/Gate | PASS/FAIL | Bằng chứng | Lỗi hoặc ghi chú |
|---|---|---|---|
| 0. Env + version | ☐ | Commit, model, Python, GPU | |
| 1. Unit tests | ☐ | Test count + console log | |
| 2. Ollama smoke | ☐ | Prompt output, latency | |
| 3. PDF ingestion | ☐ | Metadata, pages, chunks, vector shape | |
| 4. Retrieval-only | ☐ | File `evaluations/*.json` | |
| 5. E2E answer | ☐ | `qa_log.jsonl` + câu hỏi mẫu | |
| 6. Error handling | ☐ | Thông báo lỗi/retry | |

Ghi riêng các trường sau cho **từng PDF**:

- `pdf_name`, `sha256`, `page_count`, `chunk_count`, `parse_status`, warnings.
- `embedding_model`, embedding shape, cache reused/rebuilt.
- `llm_model`, `num_ctx`, latency, VRAM/RAM nếu có.
- `retrieved_pages`, `visual_evidence_pages` (nếu có), `cited_pages`, `invalid_citations`.
- Danh sách lỗi: `P0_blocker`, `P1_fix_next`, `quality_issue_for_benchmark`.
- Commit trước/sau sửa và test đã chạy lại.

## 6. Definition of Done (điều kiện chốt P0)

Chỉ đánh dấu **Pipeline Ready for Benchmark** khi:

- [ ] Unit tests đang có đều PASS; test mới cho lỗi P0 cũng PASS.
- [ ] Cả Adam và FlashAttention ingest được, tạo index có mapping trang/chunk/vector nhất quán.
- [ ] Retrieval-only chạy được cho cả hai bộ fixture, không crash/lệch định danh.
- [ ] Qwen local trả lời được các câu text/math/code trong UI, không lỗi endpoint/OOM bất thường.
- [ ] Citation/page diagnostics và logs được lưu; không có citation sai trang mà hệ thống không cảnh báo.
- [ ] Upload lại PDF dùng cache đúng; thay embedding config không tái sử dụng cache không tương thích.
- [ ] Input lỗi được xử lý an toàn; không mất dữ liệu PDF/index hiện có.
- [ ] Báo cáo PASS/FAIL ghi rõ số đo, hạn chế và commit đã kiểm tra.

**Kết quả bàn giao:** pipeline một-PDF hoạt động ổn định + log và báo cáo kiểm thử + các lỗi P0 đã sửa. **Không tuyên bố hệ thống trả lời chính xác** cho đến khi bắt đầu benchmark LLM và chấm answer correctness riêng.

---

## 7. Việc thực hiện tiếp theo sau khi hoàn thành

1. Freeze `pipeline_baseline_v1`: parser/chunker/embedding/retrieval/prompt/config + commit.
2. Dùng 120 câu **dev** thuộc bộ PDF QA đã chuẩn bị để benchmark Qwen/Gemma/Phi trong chế độ **LLM-only** (gold evidence) và **RAG end-to-end**.
3. Báo riêng correctness (theo rubric), Hit/Recall, citation support, math/code quality, latency, GPU/RAM. Chỉ cải tiến từng thành phần sau khi đã thấy lỗi thật.

> **Tóm tắt:** Chốt môi trường → unit tests → Ollama smoke → ingest 2 PDF → retrieval-only → E2E QA → negative tests → fix P0 → báo cáo. Không lan sang tối ưu model trong bước này.


## 8. Kết quả thực thi ngày 12/11/2026

Xem [PIPELINE_SANITY_REPORT.md](../docs/PIPELINE_SANITY_REPORT.md). Môi trường thực tế: RTX 4050 Laptop 6 GB, Python 3.11.9, Qwen 2B. 36 tests pass; ingestion/cache, retrieval, generation và headless UI đã kiểm tra. Native/browser UI chưa xác minh do helper không kết nối và Opera cần reauthentication. Chưa freeze baseline hoặc đánh dấu Pipeline Ready; cần hoàn tất bước browser thực trong checklist.
