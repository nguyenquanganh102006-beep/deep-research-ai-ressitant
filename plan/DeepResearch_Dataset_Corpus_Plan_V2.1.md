# DeepResearch AI Research Assistant

## Kế hoạch xây dựng Benchmark Dataset & Production Paper Corpus (V2.1)

**Ngày cập nhật:** 22/10/2026  
**Trạng thái:** Kế hoạch triển khai sau MVP  
**Định hướng:** Hệ thống AI Research Assistant chạy local, hỗ trợ đọc và hỏi đáp paper bao gồm **văn bản, code/pseudocode, công thức toán học** và trích dẫn đến nguồn.

> **Lưu ý:** Các số lượng, thời gian và dung lượng bên dưới là **mục tiêu đề xuất**, không phải dữ liệu đã thu thập hay kết quả benchmark đã đo. Trước khi mở rộng, phải xác nhận dung lượng đĩa khả dụng thực tế và đo thử trên khoảng 100 PDF.

---

## 1. Bối cảnh và mục tiêu

MVP hiện tại đã có khả năng tải một PDF, lưu tài liệu và dùng mô hình Qwen local để trả lời câu hỏi trong PDF. Bước tiếp theo gồm **hai hướng công việc độc lập nhưng chia sẻ chung định danh paper**:

1. **Research Benchmark Dataset:** Tập câu hỏi, đáp án chuẩn, bằng chứng và nhãn đánh giá để đo chất lượng PDF parser, retrieval, math/code understanding, generation và citation.
2. **Production Paper Corpus:** Kho tri thức paper đủ lớn để tra cứu khi dùng thật, gồm metadata, PDF/full-text hợp lệ, dữ liệu parse và chỉ mục retrieval.

Không đồng nhất **paper catalog** với **PDF corpus**: có thể lưu metadata của 100.000 paper nhưng chỉ cần giữ vài nghìn PDF trên máy. Tương tự, số lượng paper lớn không đồng nghĩa benchmark có ground truth tốt.

### 1.1. Phạm vi đã chốt

- **Lĩnh vực:** Artificial Intelligence / Machine Learning, Computer Science, Mathematics (bao gồm Optimization, Statistics liên quan ML).
- **Ngôn ngữ tài liệu:** Chủ yếu tiếng Anh; câu hỏi và phản hồi có thể bằng tiếng Việt hoặc tiếng Anh.
- **Năng lực trọng tâm:** Text QA, Code/Algorithm QA, Math/Equation QA, Table/Result QA, evidence retrieval, page-level citation và khả năng từ chối trả lời thiếu căn cứ.
- **Ngoài phạm vi V2.1:** Thu thập đại trà paper y sinh, hóa học, vật lý và các lĩnh vực xã hội; tái hiện toàn bộ thí nghiệm; chạy mã không tin cậy tự động; thu thập PDF có quyền truy cập hạn chế.

### 1.2. Tài nguyên triển khai

| Thành phần | Cấu hình đã biết | Tác động |
|---|---|---|
| GPU | NVIDIA RTX 4050 | Ưu tiên Qwen inference; hạn chế OCR/VLM chạy đồng thời |
| RAM | 16 GB | Ingest theo batch nhỏ; không tải toàn bộ metadata và embeddings vào RAM không cần thiết |
| Lưu trữ | Ngân sách 100 GB | Duy trì dự phòng tối thiểu 30 GB; giảm quota khi thực tế không đủ |
| Mô hình | Qwen local từ MVP | Benchmark nguyên model/quantization đang dùng; không cần fine-tune để xây dataset |

**Điều kiện cần kiểm tra:** 100 GB là dung lượng **còn trống và dành riêng cho dự án** hay là dung lượng tổng của ổ đĩa? Kế hoạch dưới đây dùng 100 GB làm trần ngân sách dự án và yêu cầu kiểm tra dung lượng trống thực tế bằng hệ điều hành.

---

## 2. Quy mô mục tiêu

| Nhóm | Pilot | V1 | Mở rộng có điều kiện |
|---|---:|---:|---:|
| Catalog metadata | 10.000–30.000 | **100.000 paper** | 500.000–1.000.000 metadata |
| PDF full-text lưu local | 100 → 500 | **2.000 PDF** | **3.000 PDF** nếu đủ disk/RAM |
| Benchmark được kiểm duyệt trực tiếp từ PDF | **300 QA** | **500 QA** | Thêm multi-paper và QA khó |
| Benchmark public QASPER | Chuẩn bị import | **Khoảng 1.500 QA** | Mở rộng, luôn báo cáo riêng |
| Tổng QA báo cáo ở V1 | 300 | **Khoảng 2.000 QA** | 5.000+ câu khi có đủ ground truth |

**Quyết định:** Không tải 10.000 PDF ngay trên máy 100 GB. Mục tiêu 10.000–50.000 full-text chỉ phù hợp khi có storage ngoài như NAS/S3/MinIO hoặc chính sách archive theo nhu cầu.

---

## 3. Phân tách ba không gian dữ liệu

### A. `benchmark/` — Tập đánh giá

Chứa câu hỏi, câu trả lời chuẩn, evidence, nhãn loại câu hỏi, độ khó, split, phiên bản dataset và log dự đoán. Không lẫn ground-truth answer của tập test vào chỉ mục cho ứng dụng thực tế.

### B. `catalog/` — Metadata để khám phá paper

**Cập nhật thực tế 23/10/2026:** V1 arXiv đã hoàn tất, 100.884 record / 100.841 nhóm canonical; có SQLite tìm kiếm, Parquet, JSONL.gz, raw provenance và kiểm định checksum. [Bản bàn giao Catalog V1](../docs/CATALOG_V1.md). Người dùng chốt arXiv trước, OpenAlex sau; đây không phải corpus PDF.

Chứa canonical ID, title, authors, DOI, arXiv ID, năm, chủ đề, abstract, OA link, license/provenance, phiên bản. Dùng tìm paper trước khi quyết định tải full-text.

### C. `corpus/` — Tài liệu dùng để QA

**Cập nhật triển khai ngày 23/10/2026:** pilot100 PDF đã audit; stage500 đã qua audit với 500 PDF / 10.955 trang / 24.813 chunk và đủ quota. Stage2.000 PDF đang chạy nền; xem [CORPUS_V1.md](../docs/CORPUS_V1.md), [audit pilot500](../data/corpus/reports/audit_pilot500.json), [visual review](../data/corpus/reports/visual_review_pilot500.json) và [registry pipeline](../data/corpus/reports/pipeline2000_20261023_193915_resume1_registry.json). Math text chưa verified; V1 chưa hoàn tất.

Chứa PDF gốc, Markdown/text và dữ liệu có cấu trúc sau parse, metadata vị trí nguồn, chunks, embeddings/search index. Đây là phần cần nhiều dung lượng nhất.

> Metadata tìm được paper không chứng minh có quyền tải, index hoặc tái phân phối PDF. Quyền sử dụng phải được lưu và kiểm tra cho từng tài liệu.

---

## 4. Phân bổ ngân sách lưu trữ 100 GB

| Thành phần | Giới hạn dự kiến |
|---|---:|
| PDF gốc (raw) | 25 GB |
| Parsed Markdown/JSON/LaTeX và sidecars | 15 GB |
| Catalog metadata, embeddings và search index | 7 GB |
| Ollama models, môi trường Python | 8 GB |
| Benchmark, evaluations, logs | 5 GB |
| Staging, cache và file tạm | 10 GB |
| **Dự phòng** | **30 GB** |
| **Tổng** | **100 GB** |

Các giới hạn là **ngân sách**, không phải dự báo dung lượng chính xác. Cần đo bytes/PDF, bytes/parsed page, số chunks/PDF và embedding bytes trên 100 PDF đầu tiên, sau đó đo lại trên 500 PDF.

**Storage guardrails:**

1. Giữ **ít nhất 30 GB trống thực tế** trên ổ chứa dữ liệu; nếu 100 GB là toàn bộ dung lượng ổ, phải dành riêng thêm không gian cho Windows, ứng dụng và dữ liệu khác.
2. Không cho thư mục dự án vượt **70 GB dung lượng sử dụng chủ động** khi ngân sách 100 GB dành riêng cho dự án.
3. Tạm dừng tải/parse khi chạm **một trong hai** giới hạn trên.
4. Dọn cache tạm đã được kiểm chứng an toàn; **không xóa PDF, phiên bản hoặc ground truth không có backup**.
5. Giữ job resumable để không phải tải lại từ đầu sau lỗi mạng/thiếu dung lượng.

---

## 5. Nguồn cho Benchmark Dataset

### 5.1. QASPER — public QA chính

- Nguồn: <https://huggingface.co/datasets/allenai/qasper>
- Bộ QA học thuật trên nội dung paper, phù hợp document question answering và evidence retrieval.
- Mục tiêu V1: khoảng **1.500 QA** sử dụng split chính thức, có lưu `source_dataset`, `source_question_id` và evidence gốc.
- **Cảnh báo:** Bằng chứng của QASPER chủ yếu dựa vào cấu trúc/đoạn văn; không được giả định có **PDF page number** chuẩn nếu chưa tìm PDF và đối chiếu mapping.
- Không dùng gold answers từ held-out test để tối ưu prompt, chunking, retrieval.

### 5.2. LitQA2 — dùng ở giai đoạn multi-paper

- Nguồn: <https://huggingface.co/datasets/futurehouse/lab-bench>
- Phù hợp nghiên cứu literature retrieval và đánh giá trả lời câu hỏi khoa học cần tìm kiếm.
- Không gộp điểm với QASPER vì tính chất và nguồn bằng chứng khác nhau.

### 5.3. SPIQA — benchmark mở rộng cho tables/figures

**Đã bỏ khỏi phạm vi theo yêu cầu người dùng ngày 23/10/2026. Không tải hoặc đưa vào bộ benchmark hiện tại.** Thông tin nguồn dưới đây giữ lại để tham khảo lịch sử kế hoạch.

- Nguồn: <https://huggingface.co/datasets/google/spiqa>
- Dùng cho paper multimodal, bảng, hình và biểu đồ.
- Tách riêng bài toán figure/table QA với text/math/code; không mặc định model text-only trên RTX 4050 đọc được hình ảnh khó.

### 5.4. SciCode — benchmark mở rộng cho scientific coding

- Nguồn: <https://github.com/scicode-bench/SciCode>
- Phù hợp **sinh chương trình khoa học** và kiểm thử code; khác với việc **đọc và giải thích pseudocode trong PDF**.
- Chỉ đưa vào khi có sandbox, harness chạy test an toàn và mục tiêu code generation rõ ràng.

### 5.5. DeepResearch-Gold (tự xây, bắt buộc)

Cần tạo bộ QA có **bằng chứng kiểm duyệt trực tiếp trên PDF gốc**, đặc biệt cho equation, math reasoning và algorithm/code. Đây là phần benchmark sát nhất với sản phẩm hiện tại.

**Phân phối V1 của 500 QA gold:**

| Category | Số câu | Ví dụ |
|---|---:|---|
| Math / Equation | 150 | Ý nghĩa ký hiệu, loss, tensor shape, giả định, biến đổi |
| Code / Algorithm | 150 | Input/output, vòng lặp, pseudocode, mapping với equation |
| Table / Result | 100 | Metric, dataset, experimental setting, con số trong bảng |
| Unanswerable / Ambiguous | 100 | Thông tin không công bố, mâu thuẫn, thiếu bằng chứng |
| **Tổng** | **500** | |

**Pilot 300 QA:** 80 text, 90 math, 90 code, 20 table, 20 unanswerable. Pilot là một bộ phát triển/đánh giá ban đầu; khi mở rộng lên 500 gold, có thể giữ tập text pilot để chẩn đoán nhưng tổng chính thức V1 sẽ phân bổ theo bảng trên. **Không được gọi kết quả sinh tự động chưa duyệt là gold**.

### 5.6. Hai track đánh giá tách biệt

- **Track A — QASPER / Paper Text QA:** QA/evidence ở cấp đoạn/section từ dataset công khai.
- **Track B — DeepResearch Gold PDF QA:** Có PDF hash, số trang thực (1-based), element/section/equation/algorithm ID và evidence được xác nhận thủ công.

Báo cáo riêng từng track; không tuyên bố mô hình đạt page citation chính xác chỉ dựa vào nhãn QASPER không có đối chiếu PDF.

---

## 6. Thiết kế và kiểm duyệt Benchmark

### 6.1. Các trường bắt buộc

```json
{
  "question_id": "drqa_math_000123",
  "dataset_source": "deepresearch_gold_v1",
  "split": "test",
  "paper_ids": ["arxiv:XXXX.XXXXX:v1"],
  "category": "math",
  "subtype": "loss_term_explanation",
  "question": "Ý nghĩa của lambda trong Equation (3) là gì?",
  "reference_answer": "<đáp án được xác minh từ PDF>",
  "answerable": true,
  "evidence": [
    {
      "paper_id": "arxiv:XXXX.XXXXX:v1",
      "pdf_sha256": "<checksum>",
      "page": 5,
      "section": "Method",
      "element_id": "eq_3",
      "quote": "<đoạn chứng cứ nguyên gốc>"
    }
  ],
  "difficulty": "medium",
  "review_status": "verified",
  "reviewer_id": "<mã người duyệt>",
  "dataset_version": "1.0"
}
```

> Đây chỉ là **schema minh họa**, không phải sample có nhãn thật.

Các trường bổ sung: `latex_gold`, `symbol_definitions`, `algorithm_id`, `language`, `table_id`, `expected_reasoning_checks`, `parser_warning`, `license`, `source_url`.

### 6.2. Quy trình tạo câu hỏi gold

1. Chọn paper AI/ML–CS–Math hợp lệ, cố định PDF version và SHA-256.
2. Chọn đoạn văn/công thức/code/algorithm/bảng có thể xác nhận bằng mắt hoặc parser.
3. Đề xuất câu hỏi thủ công hoặc dùng LLM để tạo **ứng viên**, không mặc định nhận đáp án tự sinh.
4. Người duyệt đối chiếu trực tiếp PDF: ký hiệu, shape, vị trí trang, đáp án, giả định.
5. Đánh dấu `verified`, `ambiguous`, `rejected`; loại câu không đủ chứng cứ.
6. Kiểm tra chéo mẫu khoảng 10–20% bởi reviewer thứ hai, ưu tiên tất cả câu toán/code khó.
7. Đóng băng `test_frozen.jsonl`, lưu manifest/changelog khi thay đổi.

### 6.3. Tránh data leakage và benchmark sai

- **Split theo paper/group DOI hoặc arXiv versions**, không split ngẫu nhiên câu hỏi thuộc cùng một paper.
- Tách `train`, `dev`, `test_frozen`; không tuning prompt bằng kết quả test frozen.
- Dữ liệu benchmark có thể chứa paper trong index ở chế độ **open-book retrieval**; nhưng **không được đưa gold answers và nhãn evidence của test vào prompt/index**.
- Log rõ chế độ test: paper đã có trong corpus, chỉ có một PDF hay cả kho multi-paper, retrieval oracle hay retrieval thực tế.
- Dedup bằng DOI/arXiv ID, normalized title, version, SHA-256 và gần-trùng văn bản.

---

## 7. Nguồn thu thập Production Paper Corpus

| Nguồn | Vai trò | Ghi chú |
|---|---|---|
| [OpenAlex](https://docs.openalex.org/) | Metadata backbone, discovery và OA links | Truy vấn API có lọc subject/year/OA; không tải toàn snapshot |
| [arXiv](https://info.arxiv.org/help/bulk_data/index.html) | PDF và nguồn LaTeX nếu hợp lệ, ưu tiên AI/ML/CS/Math | Tuân thủ API/bulk access, license paper và rate limit |
| [S2ORC / Semantic Scholar](https://github.com/allenai/s2orc) | Bổ sung text có cấu trúc, section/citation | Kiểm tra phiên bản/cơ chế truy cập và quyền sử dụng; không thay thế mặc định PDF gốc |
| [ar5iv](https://sigmathling.kwarc.info/resources/ar5iv-dataset-2024/) | HTML/MathML tham khảo cho công thức | Chỉ dùng subset khi phù hợp điều kiện truy cập và license |

**Không đưa PMC OA thành nguồn chính** vì scope đã chốt không bao gồm biomedical đại trà.

### 7.1. Topic taxonomy và quota corpus 2.000 PDF

| `primary_topic` | Số PDF mục tiêu |
|---|---:|
| AI/ML General | 500 |
| Computer Vision | 300 |
| NLP / LLM | 300 |
| Information Retrieval / RAG | 200 |
| Mathematics / Optimization / Statistics | 450 |
| Systems / Algorithms / Software | 250 |
| **Tổng** | **2.000** |

Quy tắc: Mỗi paper chỉ có **một `primary_topic`** dùng tính quota, nhưng có thể có nhiều `tags`. Mục tiêu giữ **ít nhất 15% corpus** chứa equation hoặc algorithm dày đặc để stress-test (đây là thuộc tính của paper đã đếm, **không cộng thêm** số lượng). Cân bằng paper nền tảng và paper mới, 1-cột/2-cột, appendix, table, code và độ dài PDF.

### 7.2. Điều kiện nhập corpus

- **Metadata:** canonical ID, title, authors, year, source, DOI/arXiv, subject/tags và OA status.
- **Nguồn và quyền:** source URL, download URL, license/terms, fetched timestamp, trạng thái sử dụng/hiển thị.
- **File:** PDF mở được, page count hợp lệ, SHA-256, kích thước trong giới hạn tải.
- **Parse:** text order, số lượng code/equation/table blocks, lỗi OCR/LaTeX/indentation, trang có warning.
- **Dedup:** loại duplicate và theo dõi phiên bản khác nhau.
- **Index:** mỗi chunk giữ paper ID, page, section, content type, parser version, text/hash và embedding version.

---

## 8. Data schema và cấu trúc thư mục

```text
data/
├── benchmark/
│   ├── external/
│   │   ├── qasper/
│   │   ├── litqa2/
│   │   └── spiqa/
│   ├── gold_v1/
│   │   ├── train.jsonl
│   │   ├── dev.jsonl
│   │   └── test_frozen.jsonl
│   └── manifests/
│       └── benchmark_manifest.json
├── catalog/
│   ├── works.parquet
│   └── source_registry.jsonl
├── corpus/
│   ├── raw/<safe_paper_id>/paper.pdf
│   ├── parsed/<safe_paper_id>/
│   │   ├── paper.md
│   │   ├── blocks.jsonl
│   │   └── quality.json
│   └── index/
│       ├── chunks.parquet
│       └── embeddings/
├── manifests/
│   └── corpus_v1.jsonl
└── evaluations/
    └── runs/<run_id>/
        ├── predictions.jsonl
        ├── metrics.json
        └── errors.csv
```

`safe_paper_id` phải tương thích tên file trên Windows (ví dụ hash của canonical paper ID), không dùng trực tiếp DOI có dấu `/`. Nên giữ raw PDF để parse lại khi nâng parser và lưu version riêng cho index.

### 8.1. Paper manifest khuyến nghị

```json
{
  "paper_id": "arxiv:XXXX.XXXXX:v1",
  "safe_paper_id": "<stable_hash>",
  "title": "<paper title>",
  "primary_topic": "machine_learning",
  "authors": [],
  "publication_year": 2025,
  "doi": null,
  "source_provider": "arxiv",
  "source_url": "<canonical_url>",
  "download_url": "<allowed_pdf_url>",
  "license": "<license_or_unknown>",
  "access_status": "open_access_reviewed",
  "local_pdf_path": "corpus/raw/<safe_paper_id>/paper.pdf",
  "pdf_sha256": "<checksum>",
  "page_count": 0,
  "parse_status": "pending",
  "parser_version": null,
  "index_status": "pending",
  "fetched_at": "<ISO8601 timestamp>"
}
```

---

## 9. Pipeline triển khai

### 9.1. Catalog ingestion (chủ yếu CPU/network)

```text
OpenAlex / arXiv metadata
      ↓
Topic / year / OA filters
      ↓
Normalize DOI, arXiv ID, authors, topics
      ↓
Deduplicate + version resolution
      ↓
Catalog Parquet / SQLite + source registry
      ↓
Select eligible PDF download candidates
```

### 9.2. Full-text ingestion (resumable)

```text
Candidate paper + rights check
      ↓
Rate-limited PDF downloader (1–2 concurrent jobs)
      ↓
SHA-256, PDF validation, dedup
      ↓
Structure-aware parser (text / equations / code / tables)
      ↓
Page & quality validation; warnings/fallback when needed
      ↓
Chunking preserving equations and code blocks
      ↓
CPU embeddings + BM25 / FAISS CPU
      ↓
Index + provenance + metadata status
```

- Giữ GPU RTX 4050 chủ yếu cho Qwen inference.
- Parser và embeddings chạy CPU, batch nhỏ; chỉ một worker parser nặng tại một thời điểm.
- Không chạy đồng thời Qwen inference nặng và nhiều OCR/VLM jobs trên máy RAM 16 GB.
- Có retry/backoff khi network gặp 429/5xx, checksum cho resume và trạng thái `pending/processing/ready/failed`.
- Corpus 500 PDF có thể test bằng NumPy/FAISS CPU; 2.000–3.000 PDF thử FAISS CPU/SQLite trước khi cân nhắc Qdrant on-disk nếu latency/truy cập nhiều người cần thiết.

---

## 10. Benchmark theo ba tầng

### 10.1. Parser Quality

Mục tiêu: PDF → nội dung có cấu trúc đúng.

- Reading order trên PDF nhiều cột.
- Trích phương trình đúng chỉ số trên/dưới, ký hiệu, ngoặc, ma trận, LaTeX tương đương.
- Code giữ đúng dấu, thụt lề, lệnh, pseudocode và thứ tự dòng.
- Bảng giữ chính xác hàng/cột/metric/unit và page alignment.
- Báo cáo parser failure thay vì loại âm thầm paper khó.

### 10.2. Retrieval Quality

Mục tiêu: câu hỏi → lấy đúng bằng chứng.

- Hit@1/5/10, Recall@K, MRR, nDCG; page accuracy khi có gold page.
- So sánh BM25, dense retrieval, hybrid retrieval.
- Log top-K: paper_id, chunk_id, page, section, score, parser warning.
- Truy xuất bổ sung chunk lân cận khi phương trình và phần định nghĩa ký hiệu nằm ở các đoạn khác nhau.

### 10.3. End-to-End QA Quality

Mục tiêu: bằng chứng → câu trả lời chính xác và có citation.

- Answer correctness theo rubric/expert verification; không chỉ dùng ROUGE/F1 cho math/code.
- Citation precision, tỷ lệ claim thiếu bằng chứng, tỷ lệ abstention đúng.
- Đánh giá riêng Text, Math, Code, Table, Unanswerable.
- **Oracle evidence test:** Đưa gold context trực tiếp vào Qwen, để đo khả năng reasoning mà không bị lỗi retrieval che lấp.
- **No-retrieval baseline:** Phát hiện model đang đoán từ kiến thức có sẵn thay vì chứng cứ.
- Với code sinh ra, chỉ báo pass rate nếu thật sự chạy unit test trong sandbox thích hợp; không tuyên bố đã verify nếu chỉ đọc tĩnh.

### 10.4. Báo cáo reproducible

Mỗi lần chạy cần ghi:

`run_id`, `git_commit`, `dataset_version`, `model_name`, `quantization`, `prompt_version`, `parser_version`, `embedding_model`, `retrieval_config`, `top_k`, `hardware`, `latency`, `RAM/VRAM peak`, `predictions`, `retrieved_chunks`, `citations`.

Tập test đóng băng không dùng để liên tục tinh chỉnh. Report tách public QASPER (paragraph evidence) và PDF Gold (page evidence), cũng như tách kết quả theo category/difficulty.

---

## 11. Roadmap triển khai thực tế

| Giai đoạn | Thời gian dự kiến | Việc chính | Deliverable |
|---|---|---|---|
| 1. Data contract & calibration | Tuần 1 | Schema; 100 PDF; kiểm tra parse và bytes/paper | Data contract v1; storage estimate; parser error report |
| 2. Benchmark pilot | Tuần 2–3 | Xây/kiểm duyệt 300 QA; chạy Qwen baseline, oracle/retrieval | `gold_pilot.jsonl`; benchmark baseline |
| 3. OA Collector | Tuần 3–4 | OpenAlex/arXiv; 10–30k metadata; 500 PDF | Downloader resumable; corpus 500 PDF; manifest |
| 4. Local Corpus V1 | Tuần 5–6 | Catalog hướng tới 100k metadata; index 2k PDF | Corpus v1; quality/storage metrics |
| 5. Benchmark V1 | Tuần 7–9 | 500 PDF gold + 1.500 QASPER; 4 retrieval/QA baselines | 2-track benchmark; metrics; error analysis |
| 6. Production Integration | Từ tuần 10 | Multi-paper retrieval; filter; incremental ingest | Search + QA trên corpus; cập nhật định kỳ |

Thời gian trên **không phải cam kết**: phụ thuộc tốc độ gắn nhãn thủ công, Internet, CPU, tốc độ parser và tỉ lệ PDF khó. Nếu nguồn lực hạn chế, giảm số gold câu hỏi thay vì giả vờ chúng đã được xác minh.

---

## 12. Gates trước khi mở rộng

**Gate A — Data quality:** Paper có canonical ID và provenance rõ; QA Gold đều có trạng thái kiểm duyệt; math/code quan trọng có evidence chính xác từ PDF.

**Gate B — Parser:** Có report tỷ lệ parse đúng và loại lỗi; bảo toàn page mapping. Không xóa hoặc bỏ qua âm thầm paper thất bại.

**Gate C — Retrieval:** Có Hit@K, page accuracy theo category trên dev. Mục tiêu tham khảo Hit@5 ≥ 80% cho những câu có evidence rõ, nhưng phải hiệu chỉnh sau pilot; không phải SLA đã xác minh.

**Gate D — Generation:** Kiểm soát unsupported claims và citation; tách lỗi retrieval với lỗi Qwen reasoning bằng oracle evidence.

**Gate E — Resources:** Disk free luôn ≥30 GB trong phạm vi ngân sách; job resume sau lỗi; đủ không gian dựng lại index và giữ dữ liệu gốc. Không nâng corpus vượt 2.000–3.000 PDF nếu gate tài nguyên không đạt.

**Gate F — Compliance:** Không tự tải bulk từ nguồn cấm; quyền xử lý, hiển thị và phân phối lại lưu riêng cho từng paper và dataset.

---

## 13. Rủi ro và biện pháp xử lý

| Rủi ro | Biện pháp |
|---|---|
| PDF scan hoặc nhiều cột làm sai thứ tự đọc | Review preview/page; dùng parser fallback cho subset khó; log warning |
| Công thức mất ký hiệu, code sai indentation | Giữ nguồn PDF, crop/page evidence, đối chiếu thủ công; không tự điền mà không ghi chú |
| QASPER không có ground-truth số trang PDF | Giữ track paragraph-level; chỉ đánh giá page citation sau khi map/verify PDF |
| Test leakage từ cùng paper/phiên bản | Split theo group paper ID; freeze test; dedup DOI/arXiv/version |
| Benchmark nghiêng về một lĩnh vực | Quota theo AI/ML, CV, NLP, RAG, Math, Systems; báo cáo theo topic |
| 16 GB RAM thiếu khi embedding/parse | Worker/batch nhỏ, CPU-based embeddings, chỉ mở index/shard cần thiết |
| 100 GB nhanh đầy | Pilot 100 PDF, guardrail 70 GB active + ≥30 GB free, tăng từng batch |
| PDF open-access nhưng license hạn chế | Kiểm tra source/terms/license, không mặc định có quyền tái phân phối |
| Qwen tự sinh câu trả lời thiếu bằng chứng | Grounded prompt, abstention tests, citation validation, oracle-context diagnostics |

---

## 14. Việc cần triển khai ngay (ưu tiên)

1. **Đo ổ đĩa:** xác nhận 100 GB là disk free hay tổng dung lượng; đo dung lượng hiện tại của thư mục model, cache và data.
2. **Chốt data contract:** schema chuẩn cho `paper`, `chunk`, `evidence`, `benchmark QA`, `manifest` và version.
3. **Thu 100 PDF mẫu:** đúng lĩnh vực, đa dạng math/code, 1-cột/2-cột; đo ingest success, PDF sizes, storage sau parse và số chunks.
4. **Khởi tạo benchmark pilot:** 300 QA có evidence kiểm duyệt; không tối ưu Qwen trên test frozen.
5. **Import QASPER:** giữ nhãn gốc và official split, lập script chạy baseline riêng.
6. **Xây OpenAlex + arXiv collector:** batch metadata rồi tải 500 PDF hợp lệ, có resume/dedup/license checks.
7. **Nâng corpus theo gate:** 500 → 1.000 → 2.000 PDF, stretch 3.000 chỉ nếu số liệu RAM/SSD cho phép.
8. **Báo cáo lỗi:** xuất parser/retrieval/generation/citation metrics và 50 case lỗi tiêu biểu phục vụ tối ưu.

**Thứ tự ưu tiên tổng thể:** Chất lượng evidence và benchmark → bộ thu thập paper bền vững → corpus đủ lớn → nhiều paper retrieval. Không chạy đua số PDF trước khi biết parser thực sự đọc đúng math/code.

---

## 15. Nguồn tài liệu kỹ thuật

- [QASPER](https://huggingface.co/datasets/allenai/qasper)
- [LitQA2 / LAB-Bench](https://huggingface.co/datasets/futurehouse/lab-bench)
- [SPIQA](https://huggingface.co/datasets/google/spiqa)
- [SciCode](https://github.com/scicode-bench/SciCode)
- [OpenAlex documentation](https://docs.openalex.org/)
- [OpenAlex — Open Access](https://help.openalex.org/data/works/open-access/)
- [arXiv bulk data](https://info.arxiv.org/help/bulk_data/index.html)
- [S2ORC](https://github.com/allenai/s2orc)
- [ar5iv dataset](https://sigmathling.kwarc.info/resources/ar5iv-dataset-2024/)

---

## 16. Các quyết định và mặc định

**Đã chốt:** AI/ML + Computer Science + Mathematics; RTX 4050; RAM 16 GB; ngân sách lưu trữ 100 GB; benchmark 2-track; corpus metadata lớn nhưng full-text có quota.

**Mặc định triển khai:** Offline/local cho Qwen inference và embedding, nguồn public cho metadata/PDF có quyền sử dụng; single-paper PDF QA là trọng tâm benchmark pilot, multi-paper QA ở bước mở rộng.

**Chưa xác nhận:** 100 GB là free space hay tổng dung lượng ổ; có dùng API thương mại để hỗ trợ đề xuất câu hỏi/gắn nhãn không (kế hoạch mặc định **không phụ thuộc API thương mại**). Những điểm này không cản trở triển khai pilot 100 PDF nhưng ảnh hưởng quy mô cuối.

**Kết luận:** Phiên bản có thể chạy thực tế trên máy này nên bắt đầu từ **100.000 metadata + 2.000 PDF chọn lọc + 2.000 QA tách track** (trong đó 500 gold PDF), với kiểm soát chất lượng và dung lượng chặt chẽ. Kho lớn hơn chỉ nên xây sau khi pipeline chứng minh hoạt động chính xác và tiết kiệm tài nguyên.
