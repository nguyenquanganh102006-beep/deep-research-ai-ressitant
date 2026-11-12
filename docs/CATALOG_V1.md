# Catalog B V1 — metadata paper

**Đã phát hành và kiểm định ngày 23/10/2026:** **100.884 record arXiv / 100.841 nhóm canonical**. Chỉ metadata; OpenAlex bổ sung sau theo quyết định người dùng. Bản dùng trực tiếp nằm ở [data/catalog/v1](../data/catalog/v1/README.md).

| Nhóm chủ đề | Record |
|---|---:|
| Computer Science | 48.626 |
| Mathematics | 37.602 |
| Statistics | 14.656 |
| Tổng | 100.884 |

Trường năm lấy từ **OAI created** trải từ **1995–2026**, gồm **29.081 record có giá trị 2026**. Một số OAI created phản ánh bản thay thế, không bảo đảm là năm đăng đầu (xem đính chính bên dưới). Phân phối nghiêng về 2020 (45.270 record) do cửa sổ/thứ tự harvest; đây không phải mẫu ngẫu nhiên hoặc bộ đại diện cân bằng theo năm. Xem phân phối giá trị đầy đủ trong [audit.json](../data/catalog/v1/audit.json).

## File bàn giao

| File | Sử dụng | Dung lượng gần đúng |
|---|---|---:|
| [v1/catalog.sqlite](../data/catalog/v1/catalog.sqlite) | Database snapshot và FTS5 tìm title/abstract | 580,6 MiB |
| [v1/works.parquet](../data/catalog/v1/works.parquet) | Đọc/phân tích theo cột | 48,6 MiB |
| [v1/works.jsonl.gz](../data/catalog/v1/works.jsonl.gz) | Đọc tuần tự hoặc trao đổi dữ liệu | 54,4 MiB |
| [v1/manifest.json](../data/catalog/v1/manifest.json) | Nguồn và SHA-256 snapshot + 87 batch XML gốc | — |
| [v1/dedup_report.json](../data/catalog/v1/dedup_report.json) | 23 nhóm DOI chung, 42 nhóm title chuẩn hóa trùng | — |
| [verification_v1.json](../data/catalog/verification_v1.json) | Kiểm định độc lập sau phát hành | — |

Toàn bộ bản xuất khoảng **683,6 MiB**; cả catalog, raw nén và database thu thập khoảng **1,01 GiB**. Metadata nhẹ hơn PDF nhưng không phải không tốn dung lượng. Các định dạng là bản sao phục vụ cách dùng khác nhau, không phải các paper khác nhau để cộng số lượng.

Audit nguồn và kiểm độc lập đều đạt: checksum file, checksum XML nén/giải nén, trường metadata đối chiếu raw, schema/scope, SQLite integrity, đối chiếu **từng record** giữa SQLite/Parquet/JSONL, ID duy nhất và tìm kiếm FTS. 5 test catalog chạy lại đạt sau khi chốt.

81.646 record không có DOI; 32 record có DOI nguồn nhưng chưa chuẩn hóa thành một DOI đơn; 7.928 record chưa có license PDF. Giữ nguyên và báo thiếu, không tự tạo giá trị. Metadata được cấp CC0 theo arXiv; các thiếu hụt quyền PDF phải được xem lại ở bước Corpus C. Không loại hoặc gộp âm thầm các ID khác nhau; các ID chung DOI chuẩn hóa chia sẻ `canonical_group_id`.

## Tìm kiếm nhanh trên snapshot

Mở `v1/catalog.sqlite` ở chế độ chỉ đọc. Bảng `works` có các cột `paper_id`, `canonical_group_id`, `normalized_doi`, `title`, `publication_year`, `primary_topic`, `metadata_json`; JSON chứa đầy đủ abstract, tác giả, categories, URL và provenance. Bảng FTS5 `search` chỉ index title/abstract.

```sql
SELECT w.paper_id, w.title, w.publication_year
FROM search s JOIN works w ON w.paper_id = s.paper_id
WHERE search MATCH 'attention'
LIMIT 10;
```

Giữ nguyên thư mục `v1/`; không chạy lại exporter để ghi đè. `data/catalog/catalog.sqlite` ở thư mục cha là database thu thập có checkpoint, dùng để mở rộng sau; nó khác database snapshot đã chuẩn hóa trong `v1/`. Nếu tiếp tục thu thêm, phải phát hành phiên bản mới và giữ manifest V1 hiện tại.

## Quy trình đã dùng

Khởi tạo ngày 23/10/2026. Mục tiêu lượt thu thập đầu: ít nhất 100.000 paper duy nhất, không tải PDF. Metadata có title, abstract, authors, DOI nếu nguồn có, categories, ngày tạo/cập nhật, URL, license và provenance. V1 hiện thu arXiv OAI-PMH theo ba set `cs`, `math`, `stat`, luân phiên từng batch. Bao gồm paper cross-list; không phải một mẫu cân bằng theo năm hoặc topic. OAI có thể trả các paper cũ trước, không mặc định là 100.000 paper mới nhất.

**Phạm vi nguồn đã được người dùng chốt:** phát hành V1 từ arXiv trước; OpenAlex bổ sung ở phiên bản sau. Không cần chờ API key OpenAlex để hoàn thành V1 này.

Collector mặc định dùng `--modified-since 2026-01-01,2020-01-01`: xen kẽ ba nhóm theo hai cửa sổ cập nhật nhằm có cả dữ liệu gần đây và dữ liệu nền tảng. Đây là ngày sửa metadata OAI, **không phải năm xuất bản**; phân phối năm thực tế nằm trong audit cuối. Các batch lịch sử đã thu vẫn giữ nguyên, các stream có ngày lọc được checkpoint riêng. Có thể dùng một ngày duy nhất hoặc `--modified-since all` để tiếp tục ba stream lịch sử. `primary_topic` chọn category đầu tiên trong CS/Math/Stat để không gán paper physics cross-list thành CS; primary category gốc vẫn giữ trong snapshot phát hành.

## Nơi lưu

Mặc định `data/catalog/`, hoặc `<DEEPRESEARCH_DATA_DIR>/catalog/` nếu đã cấu hình biến môi trường:

- `catalog.sqlite`: bảng `works` chứa metadata chuẩn hóa, `checkpoints` chứa cursor theo set, `batches` chứa đường dẫn/SHA-256 XML gốc (trước nén).
- `raw/<set>/<sha256>.xml.gz`: phản hồi gốc nén gzip để truy vết và tái nhập.
- `status.json`: số paper thực tế, nhóm chủ đề, dung lượng, trạng thái/lỗi và thời điểm cập nhật. Đây là tiến độ, không phải bằng chứng process còn sống.
- `harvest.lock`: khóa hệ điều hành ngăn chạy hai collector cùng ghi; được giải phóng khi process kết thúc.
- `v1/` sau khi đủ quota và audit: SQLite có FTS5 tìm title/abstract, Parquet, JSONL.gz, báo cáo DOI/title collisions, audit và manifest checksum. Không ghi đè release đã tồn tại.

Metadata không miễn phí dung lượng: database, abstract, index SQLite và raw backup đều chiếm ổ. Collector đo dung lượng thực, dừng khi catalog vượt 5 GiB hoặc ổ còn dưới 30 GiB; lượng tăng có thể vượt ngưỡng tối đa một batch. Không nhân bản PDF hoặc label benchmark. Thư mục catalog bị loại khỏi Git. Hiện dùng đường dẫn trong workspace OneDrive; nếu muốn chuyển ra ngoài thì dừng collector, chuyển cả thư mục nguyên vẹn và đặt `DEEPRESEARCH_DATA_DIR` trước khi chạy tiếp.

## Chạy và tiếp tục

```powershell
.venv\Scripts\python.exe -u -m src.catalog.harvest --target 100000
# Tăng mục tiêu sau khi đo storage/chất lượng:
.venv\Scripts\python.exe -u -m src.catalog.harvest --target 200000
# Hoặc giới hạn batch cho một lần kiểm tra:
.venv\Scripts\python.exe -u -m src.catalog.harvest --target 100000 --max-batches 3
```

Mục tiêu tính theo ID arXiv duy nhất; có thể vượt nhẹ vì giữ nguyên cả batch. Resume dùng database cũ, không tải lại từ đầu nếu cursor còn hiệu lực. Record và checkpoint commit trong một transaction; replay không nhân đôi ID. Token OAI hết hạn hằng ngày thì collector chạy lại set từ đầu và dedup theo ID; giữ raw và tiến độ đã có. Retry/backoff khi mạng lỗi hoặc 429/503; một kết nối, ít nhất 3,1 giây giữa các lần gọi. Hết retry thì ghi lỗi và dừng, chạy lại cùng lệnh để tiếp tục.

## Nguồn và giới hạn

- [arXiv OAI-PMH](https://info.arxiv.org/help/oa/index.html): metadata format `arXiv`, hiện trạng mới nhất, không pin version PDF. `version=null` được ghi rõ; khi tải corpus phải cố định version/hash riêng.
- [Điều khoản arXiv](https://info.arxiv.org/help/api/tou.html): descriptive metadata CC0; quyền metadata khác quyền phân phối PDF. `pdf_license` lấy từ nguồn, không mặc định CC0 cho paper.
- OpenAlex chưa nhập vì chưa có API key cấu hình. Không gọi đây là catalog đã kết hợp OpenAlex. [Authentication](https://help.openalex.org/api/authentication/) yêu cầu key cho cursor sau trang đầu.
- Canonical hiện theo arXiv ID (mọi version chung nhóm), có index DOI để hỗ trợ ghép nguồn sau. Chưa dedup liên nguồn theo DOI/title, chưa tự gộp hai ID arXiv khác nhau có cùng DOI. DOI nguyên bản được giữ, không mặc định mọi chuỗi DOI đều đã chuẩn hóa.
- Snapshot phát hành bổ sung `normalized_doi`, `canonical_group_id`, `publication_year`, `author_names`, `primary_arxiv_category`, `scope_category` và đường dẫn raw. Các ID arXiv khác nhau cùng DOI chuẩn hóa chia sẻ group, nhưng không xóa record gốc; title collision được báo riêng. Không đồng nhất số record với số canonical group.
- **Đính chính khi bắt đầu Corpus C:** `publication_year` của snapshot lấy nguyên năm `created` từ OAI; một số record dùng ngày bản thay thế nên không bảo đảm là năm đăng đầu. Ví dụ `0705.4348`: OAI created=2026-02-18 nhưng Atom published=2007-05-30. Các thống kê năm ở trên là theo trường OAI này, không phải năm xuất bản đầu đã được kiểm chứng. Giữ nguyên snapshot/checksum; Corpus C đối chiếu Atom `published` và version trước khi lựa chọn/tải. Không dùng riêng `publication_year` của V1 để kết luận độ mới. DOI chuẩn hóa chỉ được kiểm cấu trúc, chưa xác thực qua DOI resolver. `oa_status` mô tả repository mở; `pdf_access_verified=false` ghi rõ chưa kiểm tải PDF.
- Catalog phục vụ discovery; không chứng minh PDF được tải, parse hoặc index. Không chứa đáp án benchmark, embeddings hay full text PDF.

## Kiểm tra

`python -m unittest discover -s tests -p test_catalog.py` kiểm parse/deleted record, giữ trạng thái chưa pin version, OAI error, replay dedup và checkpoint/update, phân loại cross-list và DOI, cùng quy trình xuất snapshot round-trip và từ chối raw sai hash.

Lệnh xuất đã dùng sau khi collector kết thúc và SQL count đủ quota (không chạy lại vào release V1 đã tồn tại):

```powershell
.venv\Scripts\python.exe -m src.catalog.release
# Hoặc gắn vào PID collector đang chạy để audit/publish sau khi nó kết thúc:
.venv\Scripts\python.exe -u -m src.catalog.release --wait-for <collector_pid>
```

Exporter kiểm toàn bộ raw checksum/số record, đối chiếu trường nguồn từng paper, schema/scope, tính toàn vẹn SQLite và round-trip JSONL/Parquet trước khi publish `v1/`. Exporter cũng lấy OS lock nên không chạy đè collector đang sống. Cần dependency bổ sung từ `requirements-catalog.txt`. Việc có công cụ export không đồng nghĩa đã phát hành snapshot: xem `v1/audit.json` thực tế. OpenAlex chưa tích hợp.

Chế độ `--wait-for` kiểm tra PID thuộc collector và theo dõi đúng thời điểm tạo process để tránh nhầm PID được tái sử dụng. Nó không khởi động lại collector. Khi process kết thúc, exporter vẫn kiểm quota và khóa thư mục; collector lỗi/dừng sớm thì không tự nhận hoàn tất. Snapshot thành công có README sử dụng và SQL tìm kiếm đi kèm.
