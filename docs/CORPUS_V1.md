# Corpus C V1 — đã hoàn tất pipeline và audit

Khởi động ngày 23/10/2026 theo plan V2.1. V1 đã hoàn tất pipeline cho **2.000 PDF arXiv có provenance/version/hash, parse theo trang, chunks và chỉ mục retrieval** qua các mốc 100 → 500 → 2.000. Snapshot hiện hành là `index/v1`; trạng thái này xác nhận pipeline và các gate dữ liệu đã chạy, không phải benchmark QA hay kiểm định chuyên gia toàn corpus.

## Mốc pilot 100 đã đạt

Đã chốt snapshot **`pilot100_visual`**: **100 PDF / 2.250 trang / 5.093 chunk**, đúng quota sáu nhóm. Audit nguồn, version/ngày Atom, hash PDF/sidecar, mọi page mapping, SQLite/Parquet/vector row và chuẩn hóa vector đều đạt. [Audit pilot](../data/corpus/reports/audit_pilot100_visual.json), [manifest snapshot](../data/corpus/index/pilot100_visual/manifest.json).

- Raw PDF: 313.860.452 byte (~299,3 MiB); parsed sidecar ~62,8 MiB; index ~54,2 MiB.
- Pilot không có trang ít text theo ngưỡng đo; cả 100 dùng PyMuPDF4LLM. Peak parser lớn nhất ~0,94 GiB; tổng thời gian parse ~17,2 phút.
- 48/100 là dense candidates theo heuristic, không phải 48 nhãn được chuyên gia duyệt.
- Có 674 cảnh báo parser và 8.935 replacement characters; không coi Markdown toán là bản chép chuẩn. 4.608/5.093 chunk được gắn visual-source routing bằng warning, math/code, bảng/caption và tín hiệu hình/vẽ/font từ PDF.
- Đã xem nguồn 7 trang/6 paper đủ sáu topic bằng AI: bảng số giữ được các giá trị mẫu nhưng compact hàng; công thức có mất dấu/superscript; sơ đồ không nằm đầy đủ trong Markdown; pseudocode giữ thứ tự/line number nhưng không giữ nguyên indentation. Receipt tại `data/corpus/reviews/pilot_visual.jsonl`; đây là spot-check, không phải tỷ lệ lỗi đại diện toàn bộ.
- Smoke tiêu đề: BM25/dense/hybrid đều tìm đúng paper trong top5 cho 6/6 query. Encode lại ba chunk có cosine gần 1 so với vector index. **Đây không phải benchmark QA hoặc held-out retrieval score.** [Smoke report](../data/corpus/reports/smoke_pilot100_visual.json).

Stage 500 đã qua audit: **500 PDF / 10.955 trang / 24.813 chunk**, đúng quota (AI/ML 125, CV 75, NLP/LLM 75, IR 50, Math/Stats 112, Systems 63). Raw 1.356.681.741 byte, parsed 331.876.708 byte, index 280.450.385 byte, toàn project 6.251.712.662 byte; dung lượng trống 362.087.190.528 byte. Phép chiếu theo stage 500 tại 2.000 là ~5,1 GiB raw + 1,24 GiB parsed + 1,04 GiB index, trong ngân sách hiện tại; đây vẫn là ước tính. [Audit pilot500](../data/corpus/reports/audit_pilot500.json), [quyết định mở rộng pilot100](../data/corpus/reports/pilot100_promotion.json). Đã spot-check một trang mỗi topic; receipt ở [visual review pilot500](../data/corpus/reports/visual_review_pilot500.json). Math text vẫn chưa được xác minh chuẩn ký tự.

## Mốc Corpus C V1: stage 2.000 đã chốt

Snapshot `v1` có **2.000 PDF / 41.936 trang / 96.922 chunk**. Audit ngày 12/11/2026 đạt; quota đúng cho cả sáu topic. Manifest SHA-256 là `fafa1ade7a8da933c7efe76a7c1c62e525adfdcce057c830f8bbd37cd861adf1`; pointer [`active_2000.json`](../data/corpus/index/active_2000.json) trỏ tới manifest này.

| Topic | PDF |
|---|---:|
| AI/ML | 500 |
| Computer Vision | 300 |
| NLP/LLM | 300 |
| Information Retrieval | 200 |
| Math/Stats | 450 |
| Systems/Algorithms | 250 |
| **Tổng** | **2.000** |

Raw PDF **5.345.044.384 byte**, parsed sidecar **1.258.290.108 byte**, chỉ mục **1.091.941.748 byte**, toàn project **12.409.094.350 byte**; dung lượng trống tại audit **323.802.853.376 byte**. Các số lưu trữ là số đo snapshot, không phải dự báo.

- Parser: 1.998 paper dùng PyMuPDF4LLM, 2 fallback text theo trang; có 11.466 cảnh báo, 143.870 replacement characters và 34 trang ít text. PDF vẫn là nguồn chuẩn khi parse mất layout.
- Có 86.416 chunk bật `visual_grounding_required`. Dense candidates là 969/2.000 (48,45%) theo heuristic, không phải nhãn người duyệt. Math transcription chưa được xác minh.
- Visual spot-check đã xem 6 paper thuộc đủ sáu topic, tổng 12 trang (trang đầu và trang dense candidate); cả 6 paper có trong index và các chunk phủ 12 trang đều bật visual grounding. Receipt và ảnh tại [visual review](../data/corpus/reviews/visual_review_v1.json).
- Dedup screen xét 3.366 cặp LSH, thấy 0 exact-text group và 0 near-duplicate candidate. Đây là màn sàng candidate, không chứng minh hết trùng ngữ nghĩa. [Dedup report](../data/corpus/reports/dedup_v1.json).
- Smoke truy vấn tiêu đề trong top 5 đạt BM25 6/6, dense 6/6, hybrid 6/6; encode lại ba vector có cosine xấp xỉ 1. Đây là kiểm tra chẩn đoán, **không phải QA benchmark hoặc held-out retrieval score**. [Smoke report](../data/corpus/reports/smoke_v1.json).

Bằng chứng chính: [audit](../data/corpus/reports/audit_v1.json), [manifest](../data/corpus/index/v1/manifest.json), [visual review](../data/corpus/reviews/visual_review_v1.json), và trạng thái pipeline cuối tại `data/corpus/reports/pipeline2000_20261112_v1_retry1_status.json`. Audit xác nhận 2.000 paper, page/chunk mapping, checksum, quota, vector và giới hạn lưu trữ; không có nhãn QA trong snapshot.

`index/pilot100/` là prototype; `pilot100_visual` là pilot đã audit và `index/active_100.json` vẫn trỏ tới pilot đó. Corpus C V1 stage 2.000 nằm riêng trong `index/v1/`, được chọn bởi `index/active_2000.json`. Hai snapshot không ghi đè nhau. Bản visual pilot tái dùng vector cache: lần encode/build đầu ~663 giây, rebuild có cache ~45 giây; không diễn giải 45 giây là tốc độ encode mới 5.093 chunk.

## Phạm vi và lựa chọn

Nguồn metadata: `data/catalog/v1/`, giữ checksum manifest catalog trong mỗi candidate. Chỉ dùng paper có license nguồn CC BY/CC BY-SA 3.0/4.0 hoặc CC0 rõ ràng cho lượt đầu; không tự coi metadata CC0 là quyền đối với PDF. Giữ PDF local, chưa phân phối lại. Các record không có license rõ hoặc có NC/ND/nonexclusive không được chọn trong policy hiện tại.

| Chủ đề tính quota duy nhất | Pilot | V1 |
|---|---:|---:|
| AI/ML | 25 | 500 |
| Computer Vision | 15 | 300 |
| NLP/LLM | 15 | 300 |
| IR/RAG | 10 | 200 |
| Math/Optimization/Statistics | 23 | 450 |
| Systems/Algorithms/Software | 12 | 250 |
| Tổng | 100 | 2.000 |

Category ưu tiên IR → CV → NLP → AI/ML → Math/Stat → Systems; mỗi paper có một quota topic, giữ mọi category nguồn làm tags. Trộn ID arXiv gần đây (từ 2024) và ID cũ, thứ tự hash ổn định; canonical DOI/arXiv group và title chuẩn hóa được dedup khi lập candidate. Đây không phải lấy mẫu đại diện toàn lĩnh vực hoặc khẳng định paper cũ nào cũng là nền tảng nổi tiếng.

**Đính chính nguồn ngày:** OAI `created` trong catalog có thể là ngày bản thay thế. Corpus lấy version từ Atom `entry/id` và ngày đăng đầu từ Atom `published`, không mặc định `created` OAI là ngày đăng đầu. Giữ cả giá trị catalog gốc và metadata resolver để truy vết; snapshot catalog không bị sửa.

## Thu thập

`python -m src.corpus.collect --target 100` (sau pilot có target 500 hoặc 2000).

- Resolve version theo batch Atom API; lưu XML gốc và checksum.
- Tải URL explicit `.../pdf/<id>vN`, không dùng URL latest cho file đã chốt.
- Một kết nối, cách tối thiểu 3,2 giây giữa request; retry/backoff theo Retry-After khi 429/5xx.
- `.part` hỗ trợ Range resume; chỉ chuyển thành `paper.pdf` sau khi mở được PDF, không mã hóa, 1–200 trang, tối đa 50 MiB/file.
- Lưu SHA-256, byte count, trang, phiên bản, URL, license/provenance và timestamp. Nếu thấy stamp arXiv trên PDF thì kiểm đúng version.
- HTTP404/410 ở version đã pin được ghi lỗi rồi lấy candidate thay thế; không âm thầm chuyển sang version khác. Lỗi mạng tạm giữ trạng thái resumable; không tính file dở vào quota.
- PDF hash unique trong database; trùng byte được ghi lỗi, không cộng thành paper khác.
- Giữ tối thiểu 30 GiB trống; giới hạn raw 25 GiB và corpus 60 GiB. Không chạy GPU/inference trong bước thu thập.

## Parse

`python -m src.corpus.process --limit 100 --wait-for <collector_pid>`: theo dõi collector đang sống và parse các file đã tải. Một worker parser CPU; mỗi PDF chạy subprocess riêng, timeout 300 giây. PyMuPDF4LLM là backend chính; lỗi/timeout có fallback text theo trang với cảnh báo rõ. PDF gốc vẫn là bằng chứng chuẩn.

- `pages.jsonl`: Markdown và warning từng trang 1-based.
- `source_text.jsonl`: text PyMuPDF theo trang để đối chiếu.
- `blocks.jsonl`: block/bbox nguồn, không tự coi là nhãn equation/code/table gold.
- `chunks.jsonl`: chunk ID toàn corpus, paper/version/hash, trang, section, content type, parser ID và text hash; giữ representations của parser hiện có.
- `quality.json`: checksum sidecar, backend/package version, thời gian/RAM, trang ít text, replacement characters, cảnh báo và dense-page candidates.
- `paper.md`, `page_signals.jsonl`: nội dung tổng hợp và chỉ báo cấu trúc.
- JSONL được phân tách bằng LF (`\n`); nội dung có thể chứa Unicode U+2028, nên reader phải tách LF tường minh, không dùng `str.splitlines()`.

**Giới hạn đo thời gian lịch sử ở stage 500:** với `arxiv:2101.08345`, lượt PyMuPDF4LLM chạm timeout 300 giây rồi fallback text thành công. `quality.json.elapsed_seconds` đã ghi lúc đó chỉ đo lượt fallback (~8 giây), không cộng lần thử bị timeout; không dùng số của paper này như tổng thời gian parse. Parser worker hiện tại cộng thời gian chờ subprocess timeout vào lượt fallback cho hồ sơ parse mới. Hồ sơ 500 cũ giữ nguyên sidecar/hash và vẫn cần review nội dung trang của paper fallback.

**Kết quả kiểm mẫu ban đầu:** `2606.03553v1` được parse 40 trang/80 chunks; trang 4 có công thức (3)–(6) bị mất cấu trúc norm/summation/bounds trong Markdown. Đã xem PDF render và lưu receipt ở `data/corpus/reviews/pilot_visual.jsonl`. Mapping trang đúng, ảnh nguồn rõ; **math text không đạt transcription fidelity**. Vì vậy chưa được gọi công thức đã verified hoặc dùng quote-match để tuyên bố parser math đúng. Cần visual grounding từ PDF cho trang toán/code và báo lỗi trong gate pilot trước mở rộng.

Dense detection hiện là heuristic số ký hiệu hoặc heading Algorithm/Input/Output, chưa phải nhãn duyệt bằng mắt. Mục tiêu ≥15% PDF math/algorithm dày phải được kiểm tra khi chốt, không suy từ tên chủ đề hoặc số candidate.

## Nơi lưu và trạng thái

```text
data/corpus/
  corpus.sqlite                       # candidate, downloaded, parsed, errors/events
  status.json                         # trạng thái tải gần nhất, không chứng minh process sống
  discovery/<sha>.atom.xml             # resolver gốc
  raw/<safe_paper_id>/<version>/paper.pdf
  parsed/<pdf_hash_prefix>/<parser_id>/
  embeddings/<pdf_hash_prefix>/<model_fingerprint>/<content_hash>.npy
  dedup_cache/                         # fingerprint text ?? resume ki?m tra tr?ng
  reports/                             # audit, smoke, dedup v? ti?n ?? cache
  reviews/                            # receipt/ảnh kiểm mẫu
data/manifests/corpus_100.jsonl         # tạo khi đủ download stage, chưa đồng nghĩa index ready
```

Chỉ mục chứa tài liệu nguồn; không nhập câu hỏi, đáp án, rubric hoặc receipt benchmark. Nhãn QA A và snapshot catalog B không bị sửa. V1 hiện không có nhãn QA; các kết quả retrieval hiện có chỉ là kiểm tra vận hành.

## Chỉ mục CPU (snapshot V1 đã chốt)

```powershell
# Chỉ chạy khi đủ parsed theo quota của stage, hoặc chờ đúng PID parser coordinator:
.venv\Scripts\python.exe -u -m src.corpus.index --target 100 --wait-for <parser_pid>
# Tìm kiếm sau khi snapshot tồn tại:
.venv\Scripts\python.exe -m src.corpus.index --target 100 --query "attention retrieval" --method hybrid
```

Stage 100/500 xuất `data/corpus/index/pilot100/` hoặc `pilot500/`; stage 2000 xuất `index/v1/`. Mỗi snapshot bất biến gồm SQLite FTS5 BM25, dense matrix `.npy`, `chunks.parquet`, `papers.jsonl`, `quality_report.json` và manifest SHA-256. Mỗi vector có embedding row ánh xạ đúng chunk/paper/page; PDF, resolver XML và sidecar được kiểm checksum trước build. Có lock ngăn hai builder chạy đồng thời; vector cache theo hash nội dung + model fingerprint giúp resume mà không encode lại paper đã xong.

Parser và embedding chạy đồng thời ở stage lớn: `src.corpus.cache_embeddings --target 500 --wait-for <parser_pid> --threads 4` xử lý mỗi paper đã parse, dùng lại vector đúng nội dung/model fingerprint, ghi sự kiện ở `reports/cache500-<pid>.jsonl` và tiến độ ở `reports/cache_progress_500.json`. Tiến trình index chờ cache worker bằng `src.corpus.index --target 500 --wait-for <cache_pid>`; khi đủ quota, builder giữ lock chung và tạo snapshot. Tiến độ cache hoặc manifest tải xuống riêng lẻ không có nghĩa snapshot đã sẵn sàng.

`src.corpus.dedup --target 500` kiểm tra nội dung sau khi bỏ banner arXiv/số trang, exact hash và candidate near-duplicate bằng SimHash/LSH cùng Jaccard shingles. Báo cáo tại `reports/dedup_snapshot.json` giữ cặp ứng viên để duyệt; công cụ **không tự gộp, sửa hoặc xóa paper**. Trước khi chốt 2.000, mọi cặp bị gắn cờ cần có quyết định/receipt review; thuật toán này là màn sàng candidate, không chứng minh toàn bộ corpus không có trùng ngữ nghĩa. Pilot100 hiện có 0 exact group và 0 near-duplicate candidate.

Khi sửa policy trong pilot, dùng `--name <snapshot_mới>` thay vì ghi đè; ví dụ `--name pilot100_visual`. Audit snapshot cụ thể bằng `python -m src.corpus.audit --target 100 --index data/corpus/index/pilot100_visual`; chỉ sau audit đạt mới ghi active pointer. Smoke bằng `python -m src.corpus.smoke --target 100`. Các record snapshot dùng `primary_topic` theo taxonomy Corpus, giữ `catalog_primary_topic` riêng.

Dense dùng `intfloat/multilingual-e5-small`, float32 chuẩn hóa và prefix passage/query của app, hoàn toàn CPU. Đã nạp offline thành công model cache revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, kiểm SHA trọng số/config/tokenizer. Builder/query khóa fingerprint; không mặc định `_commit_hash` luôn có ở model config vì bản thư viện hiện tại không trả trường này khi load offline. Trọng số phải có trong cache, không gọi inference GPU hoặc dịch vụ thương mại.

Chunk toán/code/mixed, trang có cảnh báo/dense heuristic, bảng Markdown thật, caption hình/bảng và trang có PDF image/drawing/font toán/monospace được gắn `visual_grounding_required`; query công thức/thuật toán/hình/bảng cũng ép xem nguồn PDF. Dấu `|` trong công thức không được coi riêng là bảng. Mọi kết quả giữ đường dẫn PDF, version, hash và trang. Đây là routing về bằng chứng ảnh nguồn, không phải tuyên bố model text đã đọc công thức đúng. Smoke pilot đã chạy như trên; unit test và title-query smoke chưa chứng minh quality QA toàn corpus.

## Kiểm tra đã có

`python -m unittest discover -s tests -p test_corpus.py`: 7 test về quota/classification, license policy, năm từ ID, lỗi version PDF không có để tránh retry vô hạn, cờ visual source/quota, kiểm vector cache (reuse và từ chối SHA sai), và candidate exact duplicate chỉ được báo chứ không tự gộp. Các kiểm tra chức năng chưa thay kiểm định toàn corpus. Xem `docs/AGENT_LOG.md` cho số thực tế/process và việc còn dở mới nhất.
