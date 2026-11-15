# KẾ HOẠCH BENCHMARK NHIỀU LOCAL LLM CHO DEEPRESEARCH AI RESEARCH ASSISTANT

**Phiên bản:** 1.0  
**Ngày lập:** 12/11/2026  
**Repo:** `nguyenquanganh102006-beep/deep-research-ai-ressitant`  
**Định hướng:** Benchmark trước, phân tích lỗi, tối ưu có kiểm soát, rồi benchmark lại.  
**Trạng thái:** Phase 6 đã hoàn tất lượt đánh giá frozen. Candidate `qwen2.5:3b` không đạt toàn bộ gate vì điểm Code 0,311 thấp hơn ngưỡng 0,35; paired gain so với baseline vẫn dương. Kết quả là AI-reviewed, chưa phải human/expert gold. Xem `docs/LOCAL_LLM_BENCHMARK_PROGRESS.md` và `docs/BENCHMARK_CANDIDATE_SELECTION.md`.

> **Mục tiêu cốt lõi:** Tìm được các LLM local phù hợp nhất cho QA trên paper khoa học, đặc biệt **Math, Code/Algorithm, Table/Result và Unanswerable**, dưới giới hạn **RTX 4050 Laptop 6 GB VRAM** (RAM khả dụng và dung lượng ổ phải đo lại). Chọn theo **độ đúng, độ tin cậy của bằng chứng, tốc độ và khả năng thực sự chạy local**, không chỉ số tham số.

---

## 0. ĐIỂM XUẤT PHÁT VÀ RANH GIỚI

### 0.1. Hiện trạng đã có (theo `PIPELINE_SANITY_REPORT.md` ngày 12/11/2026)

- Sanity được báo cáo: Python 3.11.9, Ollama 0.40.16, RTX 4050 6 GB; Qwen3.5 2B Q8_0, `num_ctx=4096`, `num_predict=220`, `temperature=0.15`, `think=False`.
- Báo cáo có **36/36 unit tests PASS**; standalone generation **30/30 output không rỗng**; retrieval **25/26 Hit@5** trên fixture có trang ground truth.
- Có **17/30 output thiếu citation** trong lượt standalone. Đây là **cảnh báo kỹ thuật**, không phải đánh giá answer correctness.
- UI browser thật chưa được xác minh. Code sửa trong lượt sanity đang ở local tại thời điểm báo cáo; GitHub `main` lúc đó vẫn là `25180cb`.
- Các con số trên **không được dùng làm kết quả benchmark nhiều LLM**; một số câu fixture đã được dùng để thử prompt.

### 0.2. Dataset sử dụng

Nguồn chính: `data/benchmark/curated_v1/` **trên máy local** (dataset không được push lên GitHub).

| Split | Math | Code/Algorithm | Table/Result | Unanswerable/Ambiguous | Tổng |
|---|---:|---:|---:|---:|---:|
| Train | 20 | 57 | 11 | 24 | 112 |
| **Dev** | **40** | **27** | **31** | **22** | **120** |
| **Test frozen** | **90** | **66** | **58** | **54** | **268** |
| Tổng | 150 | 150 | 100 | 100 | 500 |

- QA là **AI-reviewed**, không phải human/expert gold. Khi chấm cần có audit thủ công mẫu sai/đúng và lưu provenance.
- Trong các vòng chọn model, prompt, retrieval hay quantization: **chỉ dùng dev 120 câu**. Không xem đáp án, không chạy test frozen để quyết định cải tiến.
- QASPER: 5.049 QA, dùng **track riêng để đánh giá paragraph retrieval hoặc text QA** khi có protocol phù hợp. Không gộp với PDF QA.
- LitQA2 199 QA và SciCode 80 bài: chỉ là **mở rộng sau**; runner hiện chưa tích hợp đầy đủ. SciCode là code generation có harness, khác code understanding.
- Corpus C V1 2.000 PDF: dùng sau cho **cross-paper retrieval**, không tự biến nó thành QA có nhãn.

### 0.3. Không làm ở giai đoạn này

- Không fine-tune/LoRA, không thay parser, reranker, chunking, embedding, model embedding trong lúc so sánh LLM.
- Không đổi prompt theo từng model để “cứu điểm” cho model đó.
- Không download hàng chục model cùng lúc; không cài/đổi driver, CUDA, Ollama giữa một vòng chạy đã khóa cấu hình.
- Không tuyên bố model nào tốt nhất khi chưa có kết quả chạy thật và chấm rubric.
- Không dùng test frozen như dev; không index reference answer, rubric, evidence gold vào kho retrieval.

---

## 1. CÂU HỎI NGHIÊN CỨU CẦN TRẢ LỜI

1. Với **cùng câu hỏi + cùng evidence đúng**, LLM nào trả lời chính xác nhất từng loại Math/Code/Table/Negative?
2. Với **evidence lấy từ pipeline thật**, độ chính xác giảm bao nhiêu so với gold evidence? Lỗi nằm ở retrieval/parser hay LLM?
3. Với model vision, **đưa ảnh trang gốc** có cải thiện math/code/table so với text-only không?
4. Model nào tạo câu trả lời **có citation thực sự hỗ trợ kết luận** và biết từ chối khi thiếu bằng chứng?
5. Model nào cho trade-off tốt nhất giữa **correctness / latency / VRAM / throughput** khi chạy local 6 GB?
6. Các kết luận có ổn định qua nhiều lần chạy, seed và thay đổi quantization hay không?

---

## 2. DANH SÁCH MODEL: 32 ỨNG VIÊN, KHÔNG CHẠY 32 MODEL FULL NGAY

**Nguyên tắc:** Model trong cùng họ nhưng size khác nhau được tính là ứng viên riêng. Tag Ollama được kiểm tra trước khi pull, và **pin model digest, quantization, size, vision capability** khi benchmark. Kích thước file model **khác VRAM thực tế** (còn KV cache, vision encoder và runtime). Các model >4 GB hoặc có offload CPU chỉ được thử khi qua preflight. Tag có thể thay đổi theo thời gian.

### 2.1. Nhóm A: 23 model nhỏ/trung bình, ưu tiên vòng sàng lọc

| # | Tag Ollama | Input dự kiến | Vai trò | Nhóm |
|---:|---|---|---|---|
| 1 | `qwen3.5:0.8b` | Text + Image | Qwen mới, cực nhỏ | A |
| 2 | `qwen3.5:2b` | Text + Image | **Baseline đang dùng** | A |
| 3 | `qwen3.5:4b` | Text + Image | Ứng viên nâng baseline | A |
| 4 | `gemma3:1b` | Text | Đối chứng nhỏ | A |
| 5 | `gemma3:4b` | Text + Image | Đối chứng vision | A |
| 6 | `ministral-3:3b` | Text + Image | Đối chứng vision/edge | A |
| 7 | `qwen3:0.6b` | Text | Đối chứng cực nhỏ | A |
| 8 | `qwen3:1.7b` | Text | Đối chứng reasoning nhỏ | A |
| 9 | `qwen3:4b` | Text | Đối chứng Qwen text-only | A |
| 10 | `qwen2.5:0.5b` | Text | Floor baseline | A |
| 11 | `qwen2.5:1.5b` | Text | Model nhỏ phổ biến | A |
| 12 | `qwen2.5:3b` | Text | General LLM | A |
| 13 | `qwen2.5-coder:0.5b` | Text | Floor code | A |
| 14 | `qwen2.5-coder:1.5b` | Text | Code-focused nhỏ | A |
| 15 | `qwen2.5-coder:3b` | Text | Code-focused | A |
| 16 | `phi4-mini:3.8b` | Text | Math/reasoning đối chứng | A |
| 17 | `phi4-mini-reasoning:3.8b` | Text | Math-reasoning đối chứng | A |
| 18 | `llama3.2:1b` | Text | General nhỏ | A |
| 19 | `llama3.2:3b` | Text | General/agent-friendly | A |
| 20 | `deepseek-r1:1.5b` | Text | Reasoning nhỏ | A |
| 21 | `granite4:3b` | Text | RAG/instruction | A |
| 22 | `granite3.3:2b` | Text | QA/RAG nhỏ | A |
| 23 | `granite3.2:2b` | Text | Reasoning control | A |

**Chú ý:** Đối với `granite4` và các reasoning model, behavior của reasoning/thinking khác nhau. Không mặc định truyền `think=False` cho mọi model; phải đọc capability/metadata và ghi cấu hình thực thi. `gemma3:1b` **không phải vision**; các phiên bản `gemma3:4b` trở lên mới hỗ trợ ảnh theo model card.

### 2.2. Nhóm B: 9 model lớn, chỉ sàng lọc nếu tài nguyên cho phép

| # | Tag Ollama | Input | Rủi ro trên 6 GB | Chính sách |
|---:|---|---|---|---|
| 24 | `qwen2.5:7b` | Text | ~4.7 GB weights + KV | Preflight VRAM |
| 25 | `qwen2.5-coder:7b` | Text | ~4.7 GB weights + KV | Preflight VRAM |
| 26 | `qwen3:8b` | Text | ~5.2 GB weights + KV | Có thể offload |
| 27 | `deepseek-r1:7b` | Text | ~4.7 GB weights + KV | Preflight VRAM |
| 28 | `mistral:7b` | Text | ~4.4 GB weights + KV | Preflight VRAM |
| 29 | `granite3.3:8b` | Text | ~4.9 GB weights + KV | Preflight VRAM |
| 30 | `olmo-3:7b-instruct` | Text | ~4.5 GB weights + KV | Preflight VRAM |
| 31 | `ministral-3:8b` | Text + Image | ~6 GB weights trước KV | Khả năng offload cao |
| 32 | `qwen3.5:9b` | Text + Image | >6 GB weights ở tag thường | **Chỉ thử offload/quant phù hợp**, loại khỏi bảng GPU-only nếu không fit |

- Nếu model không chạy được ở `num_ctx=4096`, ghi **`resource_ineligible`**, không âm thầm hạ context rồi so điểm ngang hàng. Có thể chạy *nhánh resource-constrained* `num_ctx=2048` và báo riêng.
- Nếu CPU offload đáng kể: vẫn có thể đo **best achievable local** nhưng không được so latency như model 100% GPU. Ghi `processor`, `size_vram`, resident memory, token/s và latency.
- Không kéo các model 12B/14B/27B+ vào GPU-6GB primary leaderboard. Nếu có máy khác thì tạo một hardware leaderboard riêng.

### 2.3. Lệnh chuẩn bị model (chạy theo batch, KHÔNG chạy tất cả cùng lúc)

```powershell
ollama --version
ollama list
ollama show qwen3.5:2b
ollama ps

# Batch khởi đầu 6 model đa dạng:
ollama pull qwen3.5:2b
ollama pull qwen3.5:4b
ollama pull gemma3:4b
ollama pull qwen3:4b
ollama pull qwen2.5-coder:3b
ollama pull phi4-mini:3.8b
```

**Sau khi chạy preflight và có dung lượng trống**, script quản lý model tải từng tag còn lại; hỗ trợ `--batch-size`, `--max-disk-gb`, `--skip-existing`, `--unload-after`, `--retry` và chỉ xóa model khi người dùng đồng ý. Không tải đồng thời vì vừa tốn ổ, vừa làm nhiễu VRAM/cache.

### 2.4. Nguồn model/card được xác nhận khi lập plan

- Qwen3.5: <https://ollama.com/library/qwen3.5>
- Qwen3: <https://ollama.com/library/qwen3>
- Qwen2.5: <https://ollama.com/library/qwen2.5>
- Qwen2.5 Coder: <https://ollama.com/library/qwen2.5-coder>
- Gemma3: <https://ollama.com/library/gemma3>
- Phi4 Mini / Reasoning: <https://ollama.com/library/phi4-mini> ; <https://ollama.com/library/phi4-mini-reasoning>
- DeepSeek R1: <https://ollama.com/library/deepseek-r1>
- Llama 3.2: <https://ollama.com/library/llama3.2>
- Mistral: <https://ollama.com/library/mistral>
- Ministral 3: <https://ollama.com/library/ministral-3>
- Granite: <https://ollama.com/library/granite4> ; <https://ollama.com/library/granite3.3> ; <https://ollama.com/library/granite3.2>
- OLMo3: <https://ollama.com/library/olmo-3>

---

## 3. BA TRACK BENCHMARK BẮT BUỘC PHẢI TÁCH BIỆT

### TRACK A — LLM-ONLY / GOLD-EVIDENCE TEXT (so model thuần, ưu tiên số 1)

```text
QA Dev + Paper ID + Gold evidence coordinates/quotes
       -> Load đúng PDF version/hash
       -> Verify page/quote + build stable text evidence packet
       -> SAME system prompt + SAME user prompt + SAME evidence/order
       -> Local model adapter (Ollama)
       -> Raw answer + log + rubric scoring
```

- **Mọi model dùng cùng evidence packet bằng text**, không ảnh.
- Nếu parser text hỏng math/code, ưu tiên bản evidence **đã được xác minh trực quan/được chép lại chuẩn** vào sidecar *evaluation-only*, giữ rõ provenance. Nếu chưa xác minh, gắn `gold_evidence_status=unverified` và tách khỏi điểm chính.
- `oracle` hiện có trong `src/benchmark/run_pdf.py` chỉ đọc `page.get_text()` từ trang gold; **chưa phải evidence text được chứng thực**. Cần bổ sung track `gold_text_verified`, không gọi kết quả thô này là LLM-only sạch.
- Reference answer, reasoning checks và rubric **chỉ đưa cho evaluator**, tuyệt đối không đưa trong input model.
- Đầu ra: model nào tốt nhất **khi có bằng chứng đúng**.

### TRACK B — FIXED-RETRIEVAL RAG (so generation với điều kiện RAG cố định)

```text
PDF -> Parser/Chunker/E5/BM25/RRF (chỉ chạy 1 lần)
      -> Freeze retrieved chunk_ids, scores, content, source page, ordering
      -> SAME context packet cho mọi model
      -> Local model adapter
      -> Answer/citation correctness + latency
```

- **Precompute evidence** một lần trên bộ dev, hash cả nội dung/order/format của packet.
- Tránh để mỗi lượt model chạy retrieval lại khác do cache/parser/embedding đổi ngầm.
- Không cho renderer tìm thêm **gold page bằng anchor** rồi làm retrieval miss có vẻ được cứu: nếu thêm ảnh, log chính xác trang do retrieval chọn và trang đưa vào LLM.
- So sánh Track A với B bằng **cùng question ID** để phát hiện `oracle_correct && rag_wrong`.
- Đầu ra: năng lực model khi ghép RAG hiện tại, tách được lỗi LLM vs retrieval/evidence.

### TRACK C — RETRIEVED TEXT + VISION (chỉ model hỗ trợ ảnh)

- Chỉ chạy đối với các model **đã pass capability vision**; dùng ảnh cùng trang retrieval, cùng giới hạn số ảnh, cùng DPI/crop và cùng thứ tự.
- `text-only` và `text+image` là **hai điều kiện input khác nhau**, không xếp vào cùng một leaderboard overall.
- Đo `vision_gain = score(visual) - score(text)` trên **cùng câu hỏi, cùng model**, kèm latency/VRAM chênh lệch.
- Text-only models được `not_applicable`, **không bị gán 0 điểm** ở Vision.
- Với ảnh công thức/code, phải giữ nguyên nguồn PDF, số trang thực được render, checksum ảnh; không chọn trang gold trong chế độ retrieved-vision.

### TRACK D (SAU) — MULTI-PAPER / DEEP RESEARCH

Chỉ khởi động sau khi app hỗ trợ multi-paper thật sự. Corpus C chỉ là kho paper chưa có QA gold; cần dữ liệu nhiều tài liệu riêng. Không trá hình single-paper QA thành DeepResearch benchmark.

---

## 4. CẤU HÌNH CHẠY CÔNG BẰNG

**Config v1 (đề xuất, chưa benchmark):**

| Yếu tố | Giá trị/Quy tắc |
|---|---|
| Hardware | RTX 4050 Laptop 6 GB; ghi driver, RAM, GPU power, Windows version |
| Ollama | Giữ version cố định trong một vòng; ghi model **digest/quantization** |
| `num_ctx` | 4096 chính; mọi prompt packet phải fit và không bị truncate |
| `temperature` | 0, hỗ trợ tái lập hơn (không bảo đảm deterministic tuyệt đối) |
| `seed` | 42 nếu model/adapter hỗ trợ; ghi khi không hỗ trợ |
| `num_predict` | 512 cho thí nghiệm *detailed short reasoning*; không ép 1 câu như MVP |
| `stream` | `false` để thu raw output và usage metrics ổn định |
| `think` | Track chính: *no-reasoning nếu model hỗ trợ*; nếu không hỗ trợ, ghi `native` riêng; không drop thinking text tùy tiện |
| Prompt | 1 system prompt chung + 1 user template versioned; không per-model prompt tuning |
| Evidence | Chunk/quote + paper_id + page/section; hash packet; không đưa reference answer/rubric |
| Output | Tiếng Việt, giữ nguyên công thức/identifier/code, citation `[Trang N]`; cho phép nhiều câu khi cần |
| Concurrency | 1 model/1 request tại một thời điểm; không chạy indexing/OCR song song |
| Timeout | Cấu hình rõ cho stage A/B; timeout, OOM, unsupported là trạng thái riêng |
| Image | Track C: thống nhất số ảnh, render DPI và thứ tự; lưu hash ảnh |
| Warm/cold | Tách đo; có warm-up trước recorded runs, cold load riêng |

**Quan trọng:** Với model suy luận, các cờ `think` và template không thống nhất. Đọc `/api/show` trước khi chạy. Nếu không tắt được thinking thì phải ghi điều kiện `native-thinking`, không tuyên bố cùng chính sách suy luận. Báo cáo **hai view**: chung theo input/output policy và phụ theo `thinking_mode`.

**Input length:** Log `prompt_eval_count`, actual context window và số ký tự/tokens. Nếu packet vượt context của ứng viên, đánh dấu `context_ineligible` hoặc chạy protocol riêng. **Không cắt context riêng cho một model** trong leaderboard chính.

**Quantization:** Bảng chính dùng tag/quantization cố định đã pin. Sau khi chọn finalists, mới làm nghiên cứu phụ Q4 vs Q8 **trong cùng model**, không trộn tác động model family với tác động quantization.

---

## 5. CÁC GIAI ĐOẠN THỰC HIỆN VÀ GATE

### Phase 0 — Khóa môi trường và baseline (P0)

- [x] Commit code sau sanity và regression tests (không commit dataset/model weights); baseline benchmark được commit riêng.
- [x] `git status --short` sạch cho file code/config cần benchmark ở baseline; ghi commit SHA.
- [x] Chạy `python -m unittest discover -s tests -p 'test_*.py' -v` và regression sau các thay đổi.
- [x] Chạy smoke E2E Adam và FlashAttention; artifacts/nguồn và kết quả ghi trong `docs/PIPELINE_SANITY_REPORT.md`.
- [x] Lưu `pip freeze`, Ollama, model, GPU/OS/RAM/disk snapshots ở artifacts local.
- [x] Validate local dev 120 câu, papers/PDF path-hash và evidence/rubric; không mở test ở giai đoạn này.
- [x] Preflight API, tài nguyên, GPU placement và model capability; policy tài nguyên ghi trong progress report.
- [x] UI browser giữ là gate sản phẩm riêng; benchmark headless chạy với `browser_ui_unverified`, không gọi toàn sản phẩm ready.

**PASS khi:** commit/hash môi trường được cố định, runner có thể đọc dev QA/PDF mà không thất bại hàng loạt. **FAIL:** mismatch hash hoặc missing dataset/model. **Không tự chữa bằng tải test frozen.**

### Phase 1 — Xây Benchmark Framework v1 (P0)

- [x] `configs/benchmark/models.json` khai báo 32 model, stage/capability và pull policy.
- [x] Adapter có preflight Ollama, digest/quant/capability, `content`/`thinking` extraction và retry có ghi log.
- [x] Evidence builder tách `gold_text_verified` và `retrieved_text_frozen`, giữ provenance/hash.
- [x] Prompt QA chung có citation, abstention và đủ chỗ cho Math/Code.
- [x] Runner hỗ trợ model/track/split, limit, resume/retry/dry-run; frozen test chỉ cho phép sau freeze manifest.
- [x] Resource monitor ghi RAM/GPU/placement, latency/tokens và Ollama state.
- [x] Scorer tách correctness khỏi citation syntax, giữ review-required và failure denominator.
- [x] Xuất predictions/summary/CSV/Markdown và category/failure breakdown.
- [x] Mock-based regression cho adapter failures, vision/think, resume, scoring denominator và leakage.

**PASS khi:** `--dry-run` xác nhận một model × một câu hỏi có packet + digest; run 2 model × 2 câu lưu đủ output, run lại `--resume` không sinh trùng.

### Phase 2 — Model discovery / smoke test tất cả 32 model (P1)

- [x] Duyệt 32 registry tags và pull tuần tự theo budget ổ đĩa.
- [x] Smoke text/Math/Code cho ứng viên khả dụng; output rỗng/crash được giữ thành trạng thái lỗi.
- [x] Kiểm tra capability vision/thinking, protocol và placement.
- [x] Ghi preflight status cho đủ 32 model; nhóm không cài/chạy được giữ lý do.
- [x] Ghi processor/VRAM và unload trước model tiếp theo.
- [x] Áp dụng disk/RAM policy, không ép tải/chạy nhóm vượt budget.

**PASS khi:** tất cả **32 model có trạng thái preflight rõ ràng**; các model `ready` có ít nhất một câu trả lời lưu thành công. **Không bắt buộc tất cả 32 chạy được.**

### Phase 3 — Sàng lọc rộng trên 12 câu dev (P1)

Chọn **12 câu cố định** từ 120 dev: 3 Math, 3 Code, 3 Table, 3 Negative; trải đều độ khó, ngôn ngữ, paper; **công bố manifest ID/hash trước khi chạy** để tránh chọn câu có lợi cho model nào.

- [x] Chạy Track A `gold_text_verified` text-only trên screen12 cho model ready.
- [x] Giữ evidence verification/context gate; `evidence_unverified` không lẫn vào điểm chính.
- [x] Thu latency, output, citation syntax, empty/refusal và status.
- [x] Chấm screen bằng rubric AI blind và giữ raw predictions/receipts.
- [x] Chọn 12 finalist từ registry, giữ baseline Qwen 2B trong shortlist.
- [x] Chọn shortlist theo category, quality/latency và nguồn lặp, không chỉ theo một điểm screen.

**Dự kiến workload tối đa:** 32 × 12 = **384 outputs** nếu tất cả đều chạy được, không phải 32 × 120 ngay vòng đầu.

### Phase 4 — Benchmark chính trên toàn bộ 120 dev (P1)

- [x] Chạy Track A cho finalist với evidence đã chuẩn hóa; không đưa đáp án/rubric vào model input.
- [x] Chạy Track B fixed retrieval với cùng packet cho finalist.
- [x] Chạy Track C trên subset đủ điều kiện, cùng VLM và cùng text control.
- [x] Chấm blind bằng rubric versioned với AI agents theo yêu cầu người dùng; **không có human/expert spot check, nên kết quả vẫn AI-only và không phải gold độc lập**.
- [x] Báo category accuracy, abstention, citations, claim support, latency/VRAM/failures và confidence intervals.
- [x] Phân tích paired differences trên cùng question IDs.

**Dự kiến số lượng:** 8–12 × 120 = 960–1440 câu trả lời **mỗi track A hoặc B**, chưa tính Track C và reruns. Dùng checkpoint/resume bắt buộc.

### Phase 5 — Đối chứng ablation/quantization (P2)

- [x] Top 3–5 model: chạy 2–3 seed/repeats theo cùng config để ước lượng variability. Bốn model có seed 42/43/44 cho cả Track A/B; seed 43/44 là cùng code/input. Seed 42 có code-hash caveat được audit trong report.
- [x] Text-only vs text+image trong cùng VLM: paired Track C trên 98 câu, cùng model/input/evidence, một ảnh trang retrieval ở 96 DPI; kết quả và giới hạn ở `docs/TRACK_C_PAIRED_COMPARISON.md`.
- [ ] Q4-vs-Q8, `num_ctx=8192` và thinking native/on không chạy vì không cần thiết cho lựa chọn Track B trong vòng này; nếu làm sau, lập leaderboard phụ riêng.
- [x] Chọn vai trò trước test: `default_local=qwen2.5:3b`; giữ `qwen3.5:2b` làm baseline. Không chọn math/code specialist hoặc vision fallback cho candidate chính do chưa có lợi ích đủ chắc cho nhánh triển khai này.

### Phase 6 — Freeze candidate, test cuối (P3)

- Lịch sử: freeze v1 (`caa1d64`) bị supersede khi builder gặp PDF 75 trang vượt upload default 50. Benchmark-only admission limit 200 trang đã được thêm trước freeze v2; app default, parser/chunker/embed/rank không đổi. Focused regression 43/43 và full suite 86/86 PASS trước khi freeze. Freeze v2 giữ nguyên test SHA, 268 packet đã build và verify. Lượt inference đầu tạm dừng an toàn khi RAM chạm guard; checkpoint được resume cùng freeze khi đủ tài nguyên.
- [x] Khóa commit, prompt hash, model digest/quantization, retrieval config, hardware, judge rubric và thresholds trước test. Freeze/packet manifest bind commit/config/protocol/test hash.
- [x] Chạy duy nhất một lượt final test frozen 268 câu cho candidate và baseline, không tune trên test: cả hai model hoàn tất 268/268, không có lỗi kỹ thuật. Candidate 0,453 overall, baseline 0,343; paired gain +0,110, bootstrap CI 95% [+0,062, +0,159].
- [x] Ghi gate: overall, paired gain và paired CI đạt; category Code của candidate 0,311 < 0,35 nên **candidate FAIL toàn gate**. Các category khác: Math 0,428; Table 0,422; Unanswerable 0,704.
- [x] Xuất report và review receipts: 536 receipts, 113 lượt cross-audit độc lập, 28 bất đồng correctness adjudicate; kết quả AI-only, chưa có human/expert audit. Chi tiết tại `docs/BENCHMARK_CANDIDATE_SELECTION.md` và artifact local `data/benchmark/local_llm_runs/final_test_v1/`.
- [x] Giữ nguyên held-out: không tuning theo 268 câu. Mọi thay đổi tiếp theo cần version mới và một held-out split mới.

---

## 6. METRICS VÀ CHẤM ĐIỂM

### 6.1. Metric phân loại

| Nhóm | Metric | Diễn giải |
|---|---|---|
| Answer | **Rubric correctness** | 0/0.5/1 theo checklist đúng từng ý; ưu tiên accuracy strict song song |
| Evidence | **Citation support** | Claim quan trọng có được trang/quote hỗ trợ thật không, đánh giá claim-level |
| Evidence | Citation presence / valid page | Có citation và trang có trong evidence; **không đồng nghĩa đúng nội dung** |
| Math | Formula fidelity | Ký hiệu, dấu ngoặc, căn, index, dimension, biến/hyperparameter đúng |
| Code | Algorithm reasoning | Input/output, thứ tự, điều kiện, complexity, map với equation đúng |
| Table | Numeric/protocol accuracy | Số liệu, dataset, metric, hàng/cột, setting không bị trộn |
| Negative | Correct abstention | Từ chối khi thiếu nguồn và không từ chối sai ở case answerable |
| Hallucination | Unsupported claims | Số claim tự bịa hoặc không được bằng chứng hỗ trợ |
| Runtime | Completion/timeout/OOM rate | Tỷ lệ chạy kỹ thuật thành công, tách khỏi correctness |
| Runtime | Latency p50/p95, tokens/s | Tốc độ inference warm/cold được đo riêng |
| Resource | GPU/CPU placement, VRAM/RAM | Phù hợp local và cost, lưu device/quant/context |

**Rubric đề xuất:** correctness 1.0 khi đầy đủ ý chính và đúng nguồn; 0.5 khi một phần đúng nhưng thiếu ý quan trọng (không có lỗi định lượng/nghiêm trọng); 0 khi sai trọng tâm, bịa, thay đổi công thức/setting hoặc trả lời thiếu bằng chứng. Với Negative, chấm riêng correct abstention và false refusal.

**Khuyến nghị chấm:** Auto-score được syntax/citation existence, page-hit, một số numerical checks; **Math/Code/claim support vẫn cần rubric + review**. Nếu sử dụng local LLM-as-a-judge, phải lưu judge model/digest/prompt, blind model names, audit một mẫu ngẫu nhiên + mẫu bất đồng; không coi model judge như chuyên gia độc lập.

### 6.2. Leaderboard và chọn model

Không dùng một con số “Accuracy tổng” làm chân lý. Report ít nhất:

1. **Quality leaderboard:** điểm chung + 4 category, macro trung bình trên **cùng tập question IDs đã chấm**.
2. **Citation/hallucination leaderboard:** claim support, correct abstention, missing citation.
3. **Deployment leaderboard:** p50/p95 latency, GPU percentage, RAM/VRAM, context, OOM/timeouts.
4. **Pareto frontier:** accuracy vs latency vs memory. Một model nhanh/rẻ nhưng đủ đúng có thể là default; model tốt cho math có thể là specialist.

Đề xuất trọng số nghiên cứu sơ bộ cho dashboard **chỉ để tham khảo**: Math 30%, Code 30%, Table 20%, Negative 20%. **Báo điểm từng nhóm và macro không trọng số cùng lúc**; tuyệt đối không dùng trọng số để che lỗi trong một category. Không gộp nhiều track khác protocol vào một điểm.

**Denominator:** mọi case chạy thất bại phải hiện trong `technical_failure_count`; khi báo accuracy cần công bố cả *accuracy over all eligible cases* (failure xử lý như missed task cho deployment) và *conditional correctness among completed cases*; không âm thầm bỏ case khó.

### 6.3. Template error analysis

Mỗi câu sai phải gắn `primary_error` và có thể thêm `secondary_errors`:

- `evidence_missing`, `parser_corruption`, `wrong_chunk`, `truncation`, `math_symbol_error`, `code_logic_error`, `table_numeric_error`, `false_abstention`, `hallucination`, `citation_unsupported`, `language_instruction`, `format_error`, `timeout`, `oom`.
- Với Track A đúng / Track B sai: ưu tiên xem retrieval/parse/truncation.
- Với A sai / B sai: kiểm model understanding, prompt, reasoning và quality of gold evidence.
- Với B text sai / C vision đúng: visual grounding là hướng cải thiện có bằng chứng.
- Mỗi cải tiến sau này là một experiment ID riêng (`E0`, `E1`, ...), chỉ đổi **một nhóm biến**.

---

## 7. CẤU TRÚC CODE CẦN BỔ SUNG (KHÔNG PHÁ APP MVP)

```text
configs/
  benchmark/
    models.yaml                 # 32 ứng viên + stage + capability/preflight overrides
    protocol_v1.yaml           # seed/temperature/context/vision/timeout/rubric
    prompt_v1.txt              # cùng prompt cho tất cả model trong cùng track
scripts/
  preflight_models.py           # registry/model/digest/VRAM check; batch pull policy
  build_evidence_packets.py     # validated gold vs frozen RAG evidence
  benchmark_local_llms.py       # run --track --models --split dev --resume
  score_benchmark.py           # rubric + auto metrics; no gold leak
  build_leaderboard.py         # per-category, aggregate, Pareto, error cases
src/
  benchmark/
    local_llm_adapter.py        # Ollama API adapter, think/vision capabilities
    evidence_packets.py        # stable input packets, provenance and hashes
    scoring_local.py           # schema + metrics + review states
    runner_local.py            # sequential, checkpoint, retry, resource capture
tests/
  test_local_benchmark.py       # mock + fixtures; skip GPU/network

data/benchmark/local_llm_runs/   # gitignored; runtime only
  <run_id>/
    manifest.json              # git_sha + hardware + dataset/prompt/model hashes
    preflight.jsonl
    predictions.jsonl          # per-model per-question raw answer + status
    usage.jsonl                # Ollama timing/tokens + ps/nvidia metrics
    review_template.jsonl      # human/AI review, reviewer provenance
    metrics.json
    leaderboard.csv
    report.md
    errors.csv
```

**Giữ nguyên** `src/benchmark/run_pdf.py` và `src/benchmark/run_qasper.py` để tránh làm hỏng baseline cũ; chỉ refactor phần dùng chung khi đã có unit tests so sánh output. Tích hợp runner CLI trước, UI dashboard là việc sau.

### 7.1. Output schema tối thiểu từng prediction

```json
{
  "run_id": "20261112_protocol_v1",
  "track": "gold_text_verified",
  "split": "dev",
  "question_id": "<from_dataset>",
  "paper_ids": ["<paper_id>"],
  "model_tag": "qwen3.5:2b",
  "model_digest": "<resolved_SHA256_or_model_ID>",
  "quantization": "Q8_0",
  "thinking_mode": "off_supported",
  "prompt_sha256": "<sha256>",
  "evidence_sha256": "<sha256>",
  "answer": "<raw_model_answer>",
  "thinking": null,
  "status": "completed",
  "citations": [3],
  "citation_presence": true,
  "invalid_page_citations": [],
  "correctness": null,
  "citation_supported": null,
  "review_status": "pending",
  "total_duration_ns": null,
  "load_duration_ns": null,
  "prompt_eval_count": null,
  "eval_count": null,
  "eval_duration_ns": null,
  "gpu_memory_mib": null,
  "processor": null,
  "error": null
}
```

- `null` = chưa đo/chưa review; không biến `null` thành 0.
- `model_digest`, `think_mode`, prompt/evidence hash là điều kiện cần để tái lập.
- `thinking` có thể được tách riêng khỏi `answer` tùy model/adapter; **không đưa hidden thinking vào câu trả lời cuối hoặc điểm citation**.
- Tránh lưu hidden chain-of-thought từ bên thứ ba nếu không cần; với local model chỉ lưu những trường API thực sự trả và có chính sách phù hợp.

---

## 8. CLI MONG MUỐN SAU KHI CODE (LỆNH CHƯA TỒN TẠI)

> Những lệnh dưới đây là interface mục tiêu để agent lập trình triển khai. **Không chạy nguyên xi trên repo hiện tại trước khi tạo script.**

```powershell
# 1) Kiểm tra môi trường và dataset
.\.venv-sanity311\Scripts\python.exe scripts/preflight_models.py --check-env --check-dataset --split dev

# 2) Liệt kê và probe 32 model; chưa pull tất cả
.\.venv-sanity311\Scripts\python.exe scripts/preflight_models.py --config configs/benchmark/models.yaml --stage all --dry-run

# 3) Pull batch đầu rồi smoke
.\.venv-sanity311\Scripts\python.exe scripts/preflight_models.py --stage A --pull-batch 6 --smoke

# 4) Build evidence packet (chỉ dev)
.\.venv-sanity311\Scripts\python.exe scripts/build_evidence_packets.py --split dev --track gold_text_verified
.\.venv-sanity311\Scripts\python.exe scripts/build_evidence_packets.py --split dev --track retrieved_text_frozen

# 5) Screening 12 câu, tất cả model ready
.\.venv-sanity311\Scripts\python.exe scripts/benchmark_local_llms.py --split dev --track gold_text_verified --model-set all-ready --sample-manifest configs/benchmark/dev_screen12.json --resume

# 6) Finalists full dev
.\.venv-sanity311\Scripts\python.exe scripts/benchmark_local_llms.py --split dev --track gold_text_verified --model-set finalists --resume
.\.venv-sanity311\Scripts\python.exe scripts/benchmark_local_llms.py --split dev --track retrieved_text_frozen --model-set finalists --resume

# 7) Scoring/report
.\.venv-sanity311\Scripts\python.exe scripts/score_benchmark.py --run-dir data/benchmark/local_llm_runs/<run_id>
.\.venv-sanity311\Scripts\python.exe scripts/build_leaderboard.py --run-dir data/benchmark/local_llm_runs/<run_id>
```

### Lệnh runner **đang có** để smoke thủ công (không thay framework mới)

```powershell
# runner cũ: chỉ dùng để xem luồng chạy; method oracle hiện không tương đương gold-text-verified
.\.venv-sanity311\Scripts\python.exe -m src.benchmark.run_pdf --split dev --method oracle --limit 3 --answer --model qwen3.5:2b
```

Chạy lệnh này chỉ khi local `data/benchmark/curated_v1` đầy đủ, và phải xác nhận Python env có mọi dependency. Không coi kết quả 3 câu là final benchmark.

---

## 9. QUY TẮC CHỐNG SAI LỆCH / LEAKAGE / TỐN TÀI NGUYÊN

1. **Giữ paper-group split**: cùng paper và version không tách qua train/dev/test. Không dùng test-frozen trong loop.
2. **Eval-only gold evidence**: nhãn, answer, rubric, evidence gold phải nằm ngoài index và ngoài prompt; chỉ phần evidence text được phép đưa cho LLM ở Track A.
3. **Prompt chung**: không chỉnh theo model khi xem điểm. Có thay prompt thì tất cả model chạy lại với `prompt_version` mới.
4. **Khác protocol**: reasoning on/off, text/image, Q4/Q8, context 2K/4K/8K đều phải có ID khác; không trộn điểm.
5. **Hardware reproducibility**: cùng GPU/driver/Ollama version, GPU power, chế độ nguồn điện; mỗi model chạy tuần tự, warm-up và unload.
6. **Resource failures**: skip OOM/timeout có lý do, không thay model lén, không tự nới timeouts giữa batch.
7. **QA annotation quality**: một ít gold AI-reviewed có thể sai; tạo `review_receipt` khi phát hiện; không sửa nhãn test ngầm hoặc sửa sau freeze mà không tạo version mới.
8. **Citations**: kiểm page presence riêng với claim support; thiếu citation không có nghĩa answer hoàn toàn sai, có citation đúng trang không có nghĩa claim đúng.
9. **Vietnamese**: ghi compliance tiếng Việt vì ứng dụng trả lời tiếng Việt; model English-only hoặc thiếu tiếng Việt có thể bất lợi theo yêu cầu sản phẩm thật.
10. **No benchmarking inflation**: không dùng số liệu từ bài test Adam/FlashAttention đã tune prompt làm held-out model leaderboard.
11. **Question coverage**: chấm cùng danh sách question IDs; trường hợp thiếu evidence hoặc không đủ context phải xuất nguyên nhân.
12. **Lưu provenance**: giữ raw model responses, error logs, seed, code SHA, dataset SHA, parser/index SHA, prompt/evidence hash và metric calculation version.

---

## 10. TIÊU CHÍ NGHIỆM THU FRAMEWORK V1

- [ ] Có **32 ứng viên được khai báo**, mỗi ứng viên có tag/capability, trạng thái có thể kiểm tra; không yêu cầu 32/32 chạy tốt.
- [ ] Runner có thể chạy **>=2 model** qua cùng Track A, dùng cùng packet, không nhầm quant/digest.
- [ ] Runner xử lý được tối thiểu **12 câu screen** và **120 dev cases** không cần thao tác thủ công từng câu.
- [ ] Có **resume/checkpoint**, retry kỹ thuật mà không nhân đôi mẫu, log mọi error/skip.
- [ ] Có kiểm tra model hỗ trợ vision/think, lỗi context/timeout/OOM, lưu khác biệt hợp lệ.
- [ ] Có cùng manifest input cho mọi model và chứng cứ không chứa `reference_answer`/rubric.
- [ ] Có leaderboard theo **Math, Code, Table, Negative**, cùng `accuracy`, `citation`, `latency`, `VRAM`, `failure`.
- [ ] Có danh sách case model sai và mẫu để người duyệt đánh giá; **không tự nhận AI-judge là human gold**.
- [ ] Có bảng so sánh **Track A vs B** theo `question_id` để tìm bottleneck.
- [ ] Có Markdown report chứa model digest/quantization/config và 5–10 ví dụ lỗi điển hình.
- [ ] **Không sử dụng test frozen** cho đến khi cấu hình finalist freeze.

### Deliverables dự kiến

1. `configs/benchmark/models.yaml` + `protocol_v1.yaml` + `prompt_v1.txt`.
2. Bộ 5 CLI scripts ở Section 7 và unit tests.
3. `dev_screen12.json` (12 IDs đã khóa), `evidence_packets` và manifest hash.
4. `leaderboard.csv`, `report.md`, `errors.csv`, `review_template.jsonl` sau khi chạy.
5. Đề xuất `default_local`, `math_specialist`, `code_specialist`, `vision_fallback` **dựa trên kết quả chứ không chọn sẵn**.

---

## 11. THỨ TỰ GIAO VIỆC CHO CODING AGENT (LÀM LẦN LƯỢT)

**Task 1 — Foundation:** commit sanity changes, chạy regression, khóa SHA / phiên bản; đọc `data/benchmark/curated_v1` và xác minh 120 dev; không sửa corpus/benchmark gold.  
**Task 2 — Config + adapter:** `models.yaml`, Ollama adapter và preflight, tests mock.  
**Task 3 — Evidence:** build/freeze two text tracks, zero leakage, verify gold quotes/pages, lưu manifest.  
**Task 4 — Runner:** sequential, resume/checkpoint, timeout/errors, usage/VRAM; smoke 2×2.  
**Task 5 — Scorer + report:** rubric review template, per-category metrics, leaderboard, error taxonomy.  
**Task 6 — Screening:** chọn 12 dev IDs, probe 32 ứng viên, chạy model ready, chọn finalists.  
**Task 7 — Full dev:** run Track A/B 120 dev, Track C VLM subset, báo cáo so sánh, không tune test.  
**Task 8 — Final eval:** freeze rồi chỉ mới chạy 268 test frozen.

**Quy tắc báo cáo tiến độ:** Sau mỗi task, agent trả `Files changed / Commands run / PASS-FAIL / Paths of outputs / Known blockers / Next task`. Không được ghi “đã benchmark” khi mới tạo code hoặc chỉ mới pull model.

---

## 12. TÀI LIỆU THAM CHIẾU

- Repo: <https://github.com/nguyenquanganh102006-beep/deep-research-ai-ressitant>
- `README.md`, `docs/BENCHMARK_DATASET_SUMMARY.md`, `docs/CORPUS_V1.md`, `src/benchmark/run_pdf.py`, `src/llm.py` trong repo.
- Báo cáo user upload `PIPELINE_SANITY_REPORT.md`, 12/11/2026; các kết quả môi trường/sanity chỉ trích theo báo cáo.
- Ollama API usage, times/tokens: <https://github.com/ollama/ollama/blob/main/docs/api/usage.mdx>
- Ollama thinking policy: <https://github.com/ollama/ollama/blob/main/docs/capabilities/thinking.mdx>
- Model registry sources: link ở Section 2.4.

**Tóm tắt quyết định:** Quét rộng **32 ứng viên** bằng preflight và screening **12 dev**, chọn **8–12 finalists** chạy **120 dev** trên hai protocol tách biệt, thêm vision condition riêng, làm error analysis trước khi tối ưu. Chỉ sau khi freeze mới chạy test frozen. Bảo toàn tính tái lập, không đánh đổi độ đúng lấy một bảng điểm đẹp nhưng vô nghĩa.
