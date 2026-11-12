# Nhật ký công việc của agent

Ghi nối tiếp các công việc từ khi áp dụng `AGENTS.md`. Thời gian dùng múi giờ Asia/Saigon. Các công việc trước đó xem thêm `WORKLOG-2026-10-20.md` và lịch sử hội thoại; file này không ghi hồi tố các thao tác chưa có log.

## 2026-10-22 — Tạo quy tắc agent và log chung

- **Yêu cầu:** Tạo bộ rule đơn giản và bắt buộc ghi mọi công việc vào một file Markdown.
- **Đã làm:** Kiểm tra vị trí project và tài liệu log hiện có; tạo `AGENTS.md` tại workspace root để áp dụng cho toàn bộ project; tạo `deep-research-ai-ressitant/docs/AGENT_LOG.md` làm log chung.
- **Kiểm tra:** Chưa có `AGENTS.md` tại workspace root và project root trước khi tạo. Đã đọc lại hai file sau khi tạo để xác nhận đường dẫn và nội dung quy định.
- **Kết quả:** Các công việc tiếp theo phải được ghi nối tiếp vào file này, gồm cả kết quả thất bại và việc chưa hoàn tất.

## 2026-10-22 — Triển khai benchmark (đang thực hiện)

- **Yêu cầu:** Hoàn thành phần A benchmark theo plan; người dùng cho phép dùng agent Luna max thay công việc tạo/duyệt dữ liệu.
- **Đã làm:** Đọc rule/plan và evaluator cũ; kiểm tra ổ C còn khoảng 358 GiB; tra dataset card và loader chính thức QASPER; nhập archive QASPER v0.3 từ URL chính thức, lưu SHA-256, toàn bộ 5.049 QA/1.585 paper và mọi annotation; tách nội dung retrieval khỏi nhãn; giữ split gốc. Tạo importer, integrity validator và BM25 baseline. Tạo gói review 30 QA legacy với PDF hash, ảnh trang/text và template quyết định; giữ dev vì đã dùng tuning. Đọc skill PDF và xem ảnh Adam trang 2. Khởi động 3 agent Luna max phụ trách 150 math, 150 algorithm/code, 100 table + 100 negative.
- **File:** `src/benchmark/`, `tests/test_benchmark.py`, `data/benchmark/README.md`, `data/benchmark/external/qasper/`, `data/benchmark/gold_v1/`.
- **Kiểm tra đã chạy:** Import + validate đạt, không overlap paper giữa official split, không mất annotations; 427 evidence chưa mapping được được ghi rõ. BM25 chạy đủ 1.005 dev QA; đo trên 1.501 annotation đủ mapping (902 câu), Hit@5 46,30%; không phải answer accuracy. Gói legacy 30 câu/2 paper sinh thành công, chưa có human review.
- **Lỗi/giới hạn:** URL GitHub `allenai/qasper` trả 404; dùng loader chính thức trên Hugging Face để lấy URL archive. Không suy ra số trang PDF từ QASPER. Agent review sẽ được ghi là AI review, không giả mạo human/expert gold.
- **Còn lại:** Hoàn tất và kiểm định bộ PDF QA; split/freeze và báo cáo provenance; baseline mở rộng, kiểm tra tests, tài liệu sử dụng và audit cuối theo toàn bộ plan. Goal còn active.

### Cập nhật kiểm định và baseline (22/10/2026, Asia/Saigon)

- Chạy đủ 1.005 QASPER dev QA: BM25 Hit@5 46,30%; E5 dense 57,76%; hybrid RRF 57,96%, cùng mẫu số 1.501 annotation/902 câu đủ mapping. Cache E5 CPU giúp hybrid dùng lại embedding; không so cold/warm latency trực tiếp.
- Thêm runner generation QASPER (oracle/retrieved/no-retrieval), checkpoint theo hash config và mã runner, structured JSON output; smoke 3 câu mỗi chế độ. Giữ lần lỗi `Invalid evidence_ids` trong predictions cũ; sửa schema rồi chạy lại thành công, không xóa lịch sử lỗi.
- Thêm runner PDF cách ly cache/index khỏi app; nguồn ảnh chỉ từ trang thực sự truy xuất, tránh global equation-anchor làm đẹp điểm retrieval. Thêm JSON Schema, audit hash/trang/quote/encoding/split/quotas, downloader khôi phục nguồn đúng checksum, báo cáo chất lượng và 50 ca dev retrieval miss có nguồn rõ.
- Kiểm thử: 13 unit tests hiện tại đạt; compileall src/benchmark đạt; QASPER integrity audit đạt cả kiểm tra trùng full-text/tiêu đề giữa split.
- Kiểm tra batch agent bắt được lỗi encoding tiếng Việt/LaTeX, lỗi đặt field sửa ở sai cấp, schema difficulty/rubric sai kiểu, đường dẫn manifest sai gốc và quote không khớp nguồn. Đã yêu cầu agent sửa và xác minh lại; các lỗi chưa đạt không được freeze. Quote ngắn là dòng mã giả/hàng bảng hợp lệ được giữ với source context; không thêm text giả để đủ chiều dài.
- Snapshot audit sau sửa: 68 QA (20 math, 28 code, 20 table) đang ở staging; chưa có 100 negatives và chưa đủ quota 500. 2 quote FedProx cần sửa; không công bố hoàn tất. Người dùng đã cho phép agent Luna max thay vai trò duyệt; mọi nhãn tự xây vẫn ghi AI-reviewed, không giả human review.

### Chuyển trọng tâm hoàn toàn sang dữ liệu theo yêu cầu người dùng

- Người dùng yêu cầu tập trung xây data, các phần khác tính sau. Đã dừng mở rộng runner/benchmark model, chuyển toàn bộ agent sang tạo QA và kiểm tra nhãn/nguồn; không bắt đầu thêm job benchmark sau chỉ dẫn này.
- Agent thuật toán đã hoàn thành 150 QA code trên 16 paper và 30 câu unanswerable trên 15 paper; đang được giao kiểm tra chéo 6 câu root tạo và 20 câu toán khó chưa được reviewer khác kiểm tra.
- Root tạo thêm 6 câu negative có nguồn kiểm tra: số restart theo task Table 1 BERT không thể lấy từ Table 6; thiếu confusion matrix QNLI; xung đột BLEU EN-FR trong Transformer; p95 inference latency khác training cost; BLEU CI khác checkpoint averaging; CI FID khác dispersion của IS.
- Root đã ghi 65 bản ghi kiểm tra chéo vào `curated_v1/reviews/root_cross_review.jsonl`, đối chiếu các trang PDF và ảnh render thực tế. Ghi rõ AI review, snapshot hash và reviewer khác người tạo; các nhãn thay đổi sau review sẽ được kiểm tra lại trước phát hành.
- Phát hiện/sửa thêm lỗi ngữ nghĩa: CoLA không cần tự thêm nhãn accuracy khi câu chỉ hỏi điểm; LoRA 6.91/0.32 cho 21.59/21.6 khác con số mô tả ~21.5, không suy đoán nguyên nhân; BatchNorm invariance cần a>0 và bỏ qua epsilon, không đúng với mọi a khác 0; các bài tính BN bổ sung điều kiện epsilon rõ.
- Các file đang được ghi theo batch; chưa freeze khi thiếu quota. Snapshot kiểm tra trực tiếp trước batch code negatives: 318 QA/31 paper (80 math,150 code,58 table,30 unanswerable); sau đó agent báo đã ghi thêm 30 code negatives và batch LDM. Mục tiêu vẫn 500 QA PDF (150/150/100/100), cộng 5.049 QASPER đã nhập. Goal còn active.

### Tiếp tục xây và kiểm tra data (22/10/2026, Asia/Saigon)

- Giữ nguyên ưu tiên dữ liệu; không chạy thêm model benchmark. Snapshot tích hợp 379 QA/34 paper: 90 math,150 code,69 table,70 unanswerable. Agent math sau đó hoàn thành thêm GAT để đạt100 math; các batch còn lại tiếp tục song song.
- Điều phối algorithm agent nhận 20 câu math cuối (hai paper generalization/RNN), math agent giữ 130 câu đầu; tách file để tránh ghi đồng thời. Tiếp tục kiểm tra chéo nguồn và phát hiện negative-code0007/0008 có evidence paper ID không khớp, đã giao agent sửa.
- Root kiểm lại LoRA math0030 trên ảnh Table7, ký receipt mới sau khi sửa đáp án; duyệt thêm6 câu bảng LDM trên5 trang PDF thực tế. Sửa note table0060 ghi thừa FID ±0.31; nguồn chỉ ghi FID12.63, ±0.42 thuộc IS.
- Root duyệt10 câu HNSW trên PDF4–5; mở rộng quote code0126 bị cắt trước phép gán W và sửa code0130 để trả lời đúng ý nghĩa ef trong truy vấn thay vì lạc sang chèn node. Giữ primary author và ghi correction note; lưu helper sửa nhãn có thể xem lại.
- Thêm `reviews/check_reviews.py` để kiểm fingerprint/độ phủ của receipt so với annotation hiện hành. Freeze sẽ giữ `annotations.reviewed.jsonl` làm snapshot nguyên bản cho các receipt, riêng với metadata split/source-page thêm sau đó. Thêm dataset card mô tả nhãn, nguồn, quy trình và giới hạn AI review; chưa tuyên bố release hoàn tất.
- Kiểm tra độ giống câu hỏi trong cùng paper bằng SequenceMatcher: chưa có cặp trên0.8 tại snapshot kiểm tra. Một lệnh in text HNSW lỗi console cp1252 sau khi đã render thành công; chạy lại với PYTHONIOENCODING=utf-8 đọc được đầy đủ. Không mất dữ liệu.
- Còn lại: đủ quota từng loại, sửa mọi lỗi audit, hoàn tất kiểm tra chéo, chốt split/checksum và cập nhật tài liệu với số lượng cuối. Chưa freeze test, goal còn active.

- Root bổ sung10 QA bảng (table0091..0100) từ DistilBERT1910.01108v4 và ALBERT1909.11942v6; nguồn tải trực tiếp arXiv, xác nhận title/version/hash/page count và xem5 trang render. Câu hỏi gồm macro-score, giảm thời gian khác tăng throughput, đúng thứ tự EM/F1, ablation loss, chia sẻ trọng số, SOP, so sánh cùng thời gian và phản ví dụ thêm dữ liệu. Lưu `staging/table_root.jsonl`, `table_root_papers.jsonl` và builder; giao math agent kiểm tra chéo độc lập.
- Sửa2 evidence paper ID của negative-code0007/0008 từ prefix arxiv sang neurips đúng manifest. Audit sau sửa chỉ còn lỗi thiếu quota, không còn lỗi schema/hash/page/quote tại snapshot429 QA (120math150code84table75negative).
- Duyệt chéo thêm5 câu bảng DiT trên PDF5/9/13. Phát hiện negative0027 nhầm5000 mẫu ở Fig6/7/17 với50000 mẫu dùng Table1; đã giao agent sửa tiền đề và thêm bằng chứng E.3.1 PDF26. Root đọc thêm protocol inpainting/userstudy, rà45trang LDM cho seed/shard/manifest/license và xem ảnh PDF26–27; negative0025/26/28/29 phù hợp phạm vi PDF, đang chờ quote context bổ sung trước khi ký receipt.
- Tiếp tục giữ phân công tách file: math agent130 câu, algorithm agent20 câu math bổ sung; table agent90 bảng/64negative, root10 bảng/6negative, algorithm30negative. Không thay đổi mục tiêu500 hoặc ghi AI review thành human review.

- Math agent đã hoàn thành130 câu và duyệt chéo10 bảng root +6 negative root, lưu16 receipt. Root xác nhận thêm negative0004 là ambiguity hợp lệ vì ViT-L/16 có nhiều kết quả theo pretraining/protocol, không đổi nhãn chỉ vì tồn tại một vài số trong bảng; đã xem ảnh ViT PDF6/15 và ký receipt riêng.
- Table agent sửa4 quote PaLM/LLaMA/Mistral không exact; bổ sung DDPM table0090 để tổng bảng đạt100 và12 câu negative cụ thể về lọc/khử trùng lặp/tokenizer/prompt, đưa tổng negative lên87. Snapshot hiện467 QA, còn20 math supplement và13 negative.
- Root kiểm chặt hơn quote: NFKC/bỏ whitespace nhưng phân biệt hoa/thường vì W và w khác nhau. Chỉ phát sinh thêm math0008, đã giao sửa. Audit ghi phiên bản PyMuPDF và phép chuẩn hóa để tái lập kiểm tra.
- Rà math phát hiện một số quote chỉ có câu dẫn trước định nghĩa/công thức dù đúng trang; giao math agent mở rộng đúng block công thức và context thực tế trong130 câu trước freeze. Sáu quote calibration đã mở rộng; các nhóm còn lại đang sửa. Không đổi câu trả lời để né kiểm định. Receipt bị thay evidence sẽ được tính lại freshness và kiểm tra trước khi chốt.
- Algorithm agent được thu hẹp nhiệm vụ sang20 math supplement sau khi phần cross-review chưa ghi kéo dài; không có receipt chưa viết nào được tính vào độ phủ. Người dùng không bị yêu cầu duyệt hoặc chờ xác nhận để tiếp tục.

### Kiểm tra cuối và phục hồi staging (22/10/2026, Asia/Saigon)

- Math agent sửa33 quote thiếu block công thức/định nghĩa; audit130 câu strict giữ case đạt. Root xem lại DDPM PDF2/7 và DPO PDF4, ký lại5 receipt bị stale sau mở rộng quote. Git status/diff không chạy do executable không có trong PATH.
- Algorithm agent hoàn tất20 math supplement; math agent peer-review phát hiện/sửa0139 thiếu evidence các số1.2/0.6,0146 spectral radius không vượt1 thay vì dưới1,0150 suy luận không nguồn. Latest20 receipt đều pass; giữ3 needs_changes lịch sử, không ghi đè. Tổng math đủ150.
- Table agent đã tạo đủ90 bảng/64 negative; cộng10 bảng root,6 negative root,30 negative code thì quota tổng đủ500. Tuy nhiên thao tác bổ sung timestamp bị lỗi newline trong Python/PowerShell, mở file ghi trước khi ValueError làm trống `staging/table_negative.jsonl` (154 record). Chưa có bản phát hành/frozen nào bị ghi đè. Root đã báo người dùng và dừng ghi nguồn của agent.
- Đang phục hồi từ nhật ký thao tác của chính table agent: trích121 code input chỉ liên quan task vào `tmp/table_recovery/tool_inputs`, dùng Node vm với tool stub chỉ thu payload (không thực thi shell/Python), decode92 payload để kiểm tra và dựng lại trong isolated. Ba snapshot ViT/CLIP đã trích riêng. Chưa tuyên bố phục hồi thành công khi chưa đủ154 câu và audit.
- Các lỗi môi trường trong phục hồi: node không có trong PATH nên dùng node_repl sẵn có; module capture ban đầu gọi process không khả dụng sau khi đã ghi artifact, đã bỏ dòng đó; skip payload btoa cũ không phải UTF-8 và dùng bản sửa kế tiếp. Một lần in console lỗi cp1252, một lệnh Python có literal newline lỗi parse; chạy lại đúng UTF-8, không sửa source ở các lần lỗi. Agent báo Win32_ShadowCopy lỗi khởi tạo và không có backup tên khác.
- Đã sao lưu12 JSONL staging còn nguyên vào `tmp/data_backup_20261022_231914/` kèm SHA256. File bảng bị trống được giữ nguyên để tránh làm mất dấu vết; phục hồi chỉ ghi isolated trước rồi mới kiểm định/thay thế có kiểm soát. Goal còn active.
- 2026-10-22 23:06:26 +07:00 — Theo yêu cầu, tạo 20 câu math bổ sung math-0131..0150 trên hai PDF đã pin: arxiv:1611.03530v2 và arxiv:1211.5063v2. Đã đọc README/schema/manifest liên quan, kiểm hash PDF, trích evidence nguyên văn theo trang bằng PyMuPDF và kiểm ảnh render công thức/bảng; lưu staging/math_supplement.jsonl cùng staging/build_math_supplement.py. Kiểm tra cuối: đúng 20 ID duy nhất, không trùng math.jsonl, đúng 10 câu mỗi nguồn; mọi quote khớp PDF sau NFKC và bỏ khoảng trắng, hash/trang hợp lệ, không phát hiện ký tự thay thế hoặc lỗi mã hóa. Các bản ghi chỉ nhận AI review; còn chờ peer-review tích hợp của root/math agent.
- 2026-10-22 23:13:49 +07:00 — Theo phản hồi peer-review, sửa math-0139 bằng quote trang 9 chứa trực tiếp hai test error 1.2% và 0.6%; sửa math-0146 thành spectral radius không vượt quá 1; bỏ suy luận không có nguồn khỏi đáp án math-0150. Kiểm lại 20 dòng/21 evidence, mọi quote strict NFKC + bỏ whitespace và SHA-256 đều khớp PDF/manifest; gửi math agent re-audit để ký receipt.

- 2026-10-22 23:42:57 +07:00 — Theo yêu cầu phục hồi nhóm table-0053..0064 và negative-0020..0029, tạo riêng tmp/table_recovery/isolated/algorithm_repaired_22.jsonl từ bản ghi isolated và PDF arxiv:2005.14165v4/arxiv:2112.10752v2; khôi phục quote nguyên văn và sửa negative-0027 để phân biệt 50k mẫu cho Table 1/10 với 5k cho Fig. 6/17/7. Đã render kiểm tra các trang bảng/chú thích chính, đối chiếu 22 ID duy nhất, 30 evidence, hash PDF, quote exact sau NFKC+bỏ whitespace; không còn quote_tag hay lỗi. SHA-256 artifact 3A678944701903AB410A23ECEAC0BE6E825528F736154CC6EB070711F749F4AF. Còn lại: root merge và chạy audit tích hợp.

## 2026-10-23 10:11 +07:00 — Chốt bộ dữ liệu benchmark (Asia/Saigon)

- **Yêu cầu:** Tập trung hoàn thành dữ liệu benchmark; các công việc model/app để sau.
- **Phục hồi đã hoàn tất:** Khôi phục đủ 154 record bảng/negative trong isolated; đối chiếu thay đổi với payload gốc, giữ các sửa nguồn đã xác nhận và bản dịch rubric. Sửa lại ghi chú FID 12.63 (±0.42 thuộc IS 30.29), phạm vi negative-0027 50k/5k; ký lại receipt bị thay nội dung sau khi đọc nguồn. Candidate audit đạt rồi mới thay file staging bằng atomic replace, giữ artifact lỗi và backup. Không còn record mất hoặc lỗi phục hồi chưa xử lý.
- **Dữ liệu đã chốt:** 5.049 QASPER/1.585 paper giữ annotation gốc và 500 PDF QA/46 paper: 150 math, 150 code, 100 table, 100 unanswerable/ambiguous; 380 tiếng Việt, 120 tiếng Anh. PDF train/dev/test = 112/120/268, test đã freeze. Tổng hai track 5.549 QA/1.630 nhóm paper duy nhất, không rò rỉ nhóm paper giữa split kể cả hai track.
- **Kiểm định:** Audit PDF đủ 500 câu đạt, không lỗi schema/hash/trang/quote; matching NFKC bỏ whitespace giữ phân biệt hoa/thường. 128 câu (25,6%) có review AI độc lập hiện hành, 0 stale, 0 unresolved. Snapshot annotation khớp staging; 210 text sidecar đã kiểm hash byte thực tế. SHA-256 mọi file release và cả ba file receipt khớp audit/manifest tại lần kiểm cuối. Không có cặp câu cùng paper có độ giống SequenceMatcher >0,8; answerability đúng quota từng nhóm. Validator QASPER chạy lại đạt 5.049 QA; 7 test trong test_benchmark.py đạt.
- **File/công cụ:** Hoàn thiện README.md, data/benchmark/README.md, curated_v1/DATASET_CARD.md, dataset_manifest.json và reports/QUALITY_REPORT.md; audit_curated.py giữ audit frozen, snapshot review, sidecar UTF-8 ghi byte tránh CRLF; check_reviews.py kiểm freshness; tmp/release_dataset_manifest.py đối chiếu checksum, sidecar, snapshot và split. Thêm ignore tmp/recovery/render để tránh đưa artifact tạm vào Git. Báo cáo chỉ tổng hợp kết quả model đã có, không chạy thêm model.
- **Lỗi kiểm tra phụ:** Một số lệnh đọc của agent dùng Filter array hoặc tham số Get-Content không hợp lệ, console cp1252 không hiển thị tiếng Việt; đã sửa lệnh/đọc UTF-8. Lệnh rg tìm tên plan không có kết quả (exit 1), không phải lỗi dữ liệu. Git không có trong PATH nên chưa kiểm git diff/status; không commit hoặc upload dữ liệu.
- **Giới hạn và kết quả:** Bộ PDF là AI-reviewed theo quyền thay người duyệt bằng agent Luna max, không phải human/expert gold. Quyền phân phối PDF nguồn chưa xác lập nên PDF giữ local, manifest lưu URL/version/hash. Dữ liệu benchmark đã hoàn thành và sẵn sàng sử dụng; mở rộng đánh giá model để sau theo chỉ đạo người dùng. Không còn việc xây data bắt buộc đang dở.

## 2026-10-23 — Tải bổ sung nguồn 5.2–5.4 (Asia/Saigon, đang thực hiện)

- Yêu cầu: tải LitQA2, SPIQA và SciCode theo plan V2.1. Đã đọc plan/README, kiểm tra còn khoảng 349,8 GiB; đối chiếu dataset card và API chính thức.
- Thêm src/benchmark/download_extensions.py: cố định revision, giữ file gốc, SHA-256/size, retry/resume qua .part, atomic replace và manifest tiến độ; giữ ít nhất 30 GiB free. Thêm ignore raw/archive lớn.
- LitQA2 parquet và license/card đã tải đủ; SciCode đề dev/test và archive source đã tải. SPIQA nhãn test A/B/C, val và card đã tải; các archive ảnh/train đang tải trong phiên 36494. File test_data.h5 chính thức (1.049.345.865 byte) đang tải riêng trong phiên 46152; chưa chạy code upstream.
- Kiểm tra thống kê parquet/JSON còn đang chạy ở phiên 42050. Chưa tuyên bố tải đủ hoặc validation đạt; cần kiểm tra lại các process/session sống, hoàn tất tải, kiểm checksum/nội dung và cập nhật tài liệu/manifest. Lần in README đầu lỗi console cp1252, đã chạy lại UTF-8. Lượt bị ngắt khi các job còn chạy, không khởi động job trùng trước khi kiểm tra handle.

## 2026-10-23 10:20:08 +07:00 — Bỏ SPIQA (Asia/Saigon)
- Đã kiểm tra process thực tế, dừng đúng downloader SPIQA (23180/33604), không dừng job HDF5 SciCode. Bỏ lệnh tải SPIQA trong download_extensions.py, đánh dấu mục 5.3 plan đã loại khỏi phạm vi. py_compile đạt.
- Lệnh gộp dừng process và xóa thư mục tải bị policy từ chối trước khi chạy; chuyển sang dừng riêng an toàn. Giữ dữ liệu đã tải trên ổ, không dùng trong benchmark. LitQA2/SciCode giữ nguyên, kiểm định SciCode còn dở.


## 2026-10-23 10:21:37 +07:00 — Tiếp tục sau khi người dùng cho phép (Asia/Saigon)
- Thử xóa riêng thư mục SPIQA với xác minh đường dẫn trong external; công cụ từ chối blocked by policy trước thực thi. Không tìm cách lách cơ chế chặn; thư mục vẫn còn, downloader SPIQA đã dừng từ lượt trước.
- Kiểm tra process/session hiện hành: job SciCode HDF5 46152 vẫn sống, đã ghi 8 MiB, gặp IncompleteRead và ConnectTimeout rồi retry; không khởi động job trùng. Phiên kiểm metadata 42050 hoàn tất.
- Kiểm định LitQA2 parquet 199 ID duy nhất; đọc đủ JSONL SciCode 15 dev/65 test, 341 sub_steps thực tế. Checksum mọi file trong hai manifest đã tải khớp. Ghi external/extension_validation.json và cập nhật data/benchmark/README.md; chưa chạy upstream code hoặc benchmark model.
- Còn lại: file HDF5 SciCode đang tải, chưa xác nhận đủ/valid; SPIQA chưa xóa được do policy. Không tuyên bố các hạng mục này hoàn tất.


## 2026-10-23 10:26:16 +07:00 — Tổng hợp dataset benchmark (Asia/Saigon)
- Yêu cầu: một bản Markdown gồm toàn bộ thông tin dataset dùng benchmark. Đã đọc card/manifest/validation, schema và tham số runner hiện hành, dữ liệu nguồn bổ sung và trạng thái file local.
- Tạo docs/BENCHMARK_DATASET_SUMMARY.md (202 dòng): nguồn/license/revision, số lượng/split, schema, evidence/review, cấu trúc file, leakage, metric/protocol, lệnh chạy, giới hạn và phần chưa hoàn tất; thêm liên kết từ data/benchmark/README.md.
- Kiểm tra: toàn bộ liên kết local trong bản tổng hợp tồn tại; SHA256 tất cả file release trong manifest chính khớp; xác nhận 246 QASPER answerability bất đồng. SPIQA không còn trên ổ; SciCode HDF5 hoàn chỉnh chưa có (còn .part), ghi rõ chưa ready. LitQA2 199, SciCode 80/341 sub_steps theo dữ liệu đã kiểm trước đó. Không chạy model hoặc thay nhãn/split.
- Một lệnh rg tham chiếu nhầm common.py không tồn tại (exit 2); vẫn đọc được runner thực, không ảnh hưởng dữ liệu. Tests 7 pass được ghi rõ là kết quả lượt chốt trước, không nhận là vừa chạy lại. Tài liệu hoàn tất; tải/kiểm định numeric SciCode còn dở như mô tả.


## 2026-10-23 10:30:31 +07:00 — Tư vấn lưu catalog B và corpus C (Asia/Saigon)
- Đọc lại phần schema/pipeline của plan V2.1, kiểm thư mục data/src: hiện chưa có catalog/corpus riêng. Tham khảo tài liệu chính thức arXiv và OpenAlex; URL OpenAlex cũ không mở được, tìm tài liệu mới.
- Đề xuất metadata SQLite + snapshot Parquet/raw JSONL; PDF version/hash bất biến, parsed sidecar và index tách riêng, checkpoint/resume, pilot 100 rồi 500/2000, giữ guardrail storage và tách benchmark labels. Chỉ tư vấn, chưa tải hoặc triển khai B/C trong lượt này.


## 2026-10-23 10:36:51 +07:00 — Bắt đầu Catalog B V1 (Asia/Saigon)
- Yêu cầu: triển khai V1 catalog, tải nhiều metadata theo plan; giải thích storage. Đọc AGENTS/config/requirements/plan đã có, kiểm ổ C còn khoảng 347 GiB; không thấy OPENALEX_API_KEY cấu hình (chỉ kiểm tên biến, không in secrets). Tham khảo tài liệu chính thức arXiv OAI và rate limit, OpenAlex auth.
- Tạo src/catalog/harvest.py và __init__.py: metadata-only arXiv OAI-PMH CS/Math/Stat luân phiên, mục tiêu 100000, SQLite + raw XML gzip/hash + checkpoints/status. Transaction ghi records/cursor đồng thời, ID dedup/upsert, single-process OS lock, retry/backoff và expired cursor replay, một kết nối cách ít nhất 3,1 giây; guard 5 GiB catalog/30 GiB free. Không tải PDF hoặc chạm benchmark labels. Thêm ignore data/catalog/ và docs/CATALOG_V1.md mô tả nguồn, resume, giới hạn.
- Đã khởi động session 33217 và xác minh còn chạy bằng poll. SQL đọc thực tế lúc kiểm cuối có 2567 paper/2 batch, khoảng 12,14 MiB (có WAL/file tạm); quick_check SQLite và SHA256 raw giải nén đạt. Test metadata thăm dò session 37202 trả HTTP200; collector đã có batch thực CS và Math. Không coi mục tiêu 100000 đã hoàn tất.
- Tests tests/test_catalog.py: 3 pass, kiểm parser/deleted/error, source fields, replay dedup/upsert, cursor transaction. OpenAlex chưa thu vì thiếu key; canonical hiện theo arXiv ID, DOI giữ nguyên và có index nhưng chưa dedup liên nguồn; chưa xuất Parquet, chưa cân bằng năm/topic. OAI metadata không pin PDF version, ghi rõ version null.
- Còn lại: collector tiếp tục chạy tới target, cần kiểm tiến độ/status và audit sau khi đủ; metadata có dung lượng thực, không phải bằng 0. Hướng dẫn tại docs/CATALOG_V1.md; không có agent phụ hoặc dịch vụ model được khởi động.


## 2026-10-23 10:45:38 +07:00 — Tiếp tục Catalog B tới hoàn tất V1 (Asia/Saigon)
- Yêu cầu/goal: tiếp tục tới khi xong dataset Catalog B. Lượt trước là tiến bộ thực: collector có dữ liệu đã commit. Poll session 33217 xác nhận sống, tăng 6442 rồi 9025; kiểm phân phối thấy OAI trả nhiều paper cũ và classifier gom physics cross-list nhầm CS.
- Dừng có chủ đích session 33217 bằng Ctrl-C (kết thúc exit1; không mất transaction đã commit), sửa classifier chọn category CS/Math/Stat đầu tiên; sửa 2594 derived topic cũ bằng update có so sánh payload tránh đè bản ghi mới. Thêm --modified-since mặc định 2020-01-01, stream checkpoint riêng theo ngày; ghi rõ đây là modification date không phải publication year. Khởi động resume session 4529, vẫn sống và đã thu stream mới thực tế.
- Thêm src/catalog/release.py: lấy OS lock, audit toàn bộ raw hash/count và đối chiếu từng trường nguồn đã chọn, giữ arXiv ID, chuẩn hóa DOI/group/year/topic/author schema; xuất SQLite FTS5, Parquet, JSONL.gz; báo DOI/title collisions, audit/manifest; chỉ publish >=100000 và không ghi đè release. Thêm requirements-catalog.txt, cập nhật docs/CATALOG_V1.md. Chưa publish production snapshot vì chưa đủ quota.
- Kiểm tra: 5 unit/integration tests pass, gồm corrupt raw từ chối release, full release fixture/checksum, replay/cursor, DOI/cross-list. Probe Parquet round-trip toàn bộ 12329 metadata thực đạt; quick_check SQLite đạt; không thiếu authors/scope/year ở snapshot 11378. XML nguồn vẫn nguyên, chỉ sửa trường phân loại dẫn xuất. Dữ liệu thực đạt12329 (~44,8 MB theo status), job4529 còn chạy.
- Hỏi tùy chọn bổ sung OpenAlex qua async; chưa có key, vẫn tiếp tục arXiv độc lập. Không gửi email, không in secret, không tạo agent hoặc tải PDF. Goal còn active: phải đủ quota, audit và publish thực tế, cập nhật docs cuối; chưa gọi complete.


## 2026-10-23 10:49:56 +07:00 — Catalog B: kiểm provenance và chốt nguồn V1 (Asia/Saigon)
- Goal vẫn active, tiếp tục tải tới đủ và publish. Poll session4529 nhiều lần xác nhận sống; từ13373 tăng15661 paper, khoảng56,7MB theo status. Process OS19252/25628 xác nhận đúng collector; không khởi động job trùng.
- Đối chiếu toàn bộ13373 metadata với11raw batch trong một read transaction: hash giải nén/count và các trường nguồn đã chọn đều khớp; 4 nhóm DOI chung được phát hiện, giữ DOI nhiều giá trị chưa chuẩn hóa thay vì ép sai. Kiểm12batch request/header setSpec đều đúng CS/Math/Stat (1300/1300 mỗi batch), giải thích from trong body có thể dịch theo tiến độ server.
- Bổ sung output release tags, OA repository status, pdf_access_verified=false, pdf_status=not_downloaded; chưa có PDF nào tải bởi catalog. Kiểm OS lock đang được collector giữ: PASS, exporter không thể ghi đè khi đang thu.
- Người dùng trả lời chọn chốt V1 arXiv trước, OpenAlex sau; ghi rõ trong docs/CATALOG_V1.md, không chờ key và không đổi source âm thầm. Không có release V1 thực tế vì chưa đủ100000, chưa gọi goal complete; còn tải, audit/export cuối và cập nhật tài liệu.


## 2026-10-23 11:02:15 +07:00 — Catalog B: tải tiếp và tự động đóng gói (Asia/Saigon)
- Lượt trước có tiến bộ đã xác minh. Liên tục poll cùng session4529 (không restart) xác nhận collector sống; SQL/status tăng16648 ->20982 ->24214 ->30748, hiện khoảng108,7MB. Các lần poll chưa có output được xem là đang chờ, không suy rằng process đã dừng.
- Bổ sung release.py --wait-for để theo dõi đúng PID/cmdline/create_time rồi audit/publish khi collector kết thúc; nếu thiếu quota/raw sai thì dừng lỗi. Đã gắn watcher session23398 vào collector PID25628, trả Waiting for collector PID25628. Đây chỉ là bước chờ, chưa có release production.
- Release tự tạo README sử dụng và SQL FTS; cập nhật docs/CATALOG_V1.md. Bổ sung test SQL tìm kiếm fixture và chạy lại5 tests đều PASS, gồm manifest checksum/round-trip và từ chối raw hỏng. Không chạy thêm model hay tải PDF.
- Người dùng đã chốt V1 arXiv trước, OpenAlex sau. Hiện chưa đạt100000, còn collector/watcher đang sống; cần theo dõi 4529 và23398, audit snapshot cuối, cập nhật tài liệu/count/storage thực tế rồi mới complete goal. Không coi fixture pass hoặc watcher đang chờ là dataset đã xong.


## 2026-10-23 11:06:51 +07:00 — Catalog B: bổ sung metadata gần đây (Asia/Saigon)
- Goal còn active. Poll collector4529/watcher23398 xác nhận sống; SQL ở32839 paper không thiếu trường bắt buộc nhưng19763 thuộc năm arXiv2020, chưa có2021+. Đây là bằng chứng thiên lệch thời gian do thứ tự OAI, cần bổ sung cửa sổ mới trước chốt.
- Dừng có chủ đích watcher23398 trước, rồi collector4529 sau batch đã commit35363 (Ctrl-C exit1, không mất dữ liệu). Mở rộng --modified-since nhận danh sách, mặc định2026-01-01,2020-01-01; mỗi ngày có3set và checkpoint riêng, giữ toàn bộ metadata/cursor cũ. Restart collector session26719, PID thực32300; gắn watcher41842 --wait-for32300. Không chạy request arXiv đồng thời hoặc bỏ rate limit.
- Poll26719 tăng37787 paper (~140,8MB). Kiểm năm arXiv thực có54 paper2024,1154 paper2025,1142 paper2026;2stream2026 đã commit1300 record mỗi stream. Năm lấy created là năm preprint, không coi modified date hoặc năm journal là tương đương; ghi rõ trong docs/CATALOG_V1.md, cũng nêu DOI normalization không phải resolver verification.
- Một lệnh thống kê SQL trong PowerShell quote sai bị shell diễn giải ký tự*, không sửa dữ liệu; đã chạy lại đúng và lấy số liệu trên. Chưa có v1/manifest.json; còn tải tới100000 và chờ audit/publish rồi kiểm file thực tế. Không gọi complete.


## 2026-10-23 15:38:56 +07:00 — Hoàn tất và bàn giao Catalog B V1 (Asia/Saigon)
- Goal: tiếp tục đến khi xong Catalog B; phạm vi V1 arXiv trước, OpenAlex sau đã được người dùng chọn. Lượt theo dõi dài có tiến bộ thực: poll collector26719 từ39828 đến98565; watcher41842 vẫn chờ, không restart do các lần timeout/chưa có output. Kiểm ở49375 paper: không thiếu trường bắt buộc, quick_check đạt,5365 paper2026. Kiểm ở70480: không thiếu trường bắt buộc,14930 paper2026,256,38MiB. Chuẩn bị tmp/verify_catalog_v1.py để kiểm độc lập snapshot; thêm psutil vào requirements-catalog.txt cho chế độ chờ PID.
- Lần tool chờ cuối bị ngắt; sau continuation handle26719 báo Unknown process id, kiểm OS xác nhận cả collector/watcher không còn, chưa có v1. SQL vẫn98565 record/9checkpoint và quick_check đạt. Resume đúng checkpoint bằng session94176, không tải lại từ đầu; collector tăng99680 rồi100884, state target_reached, exit0. Không coi status cũ running là process sống.
- Chạy src.catalog.release session92563: audit nguồn và publish v1 thành công,100884 record arXiv/100841 canonical groups;48626CS,37602Math,14656Stat,87raw batches. Năm preprint1995–2026,29081 paper2026; phân phối còn nghiêng2020 (45270), công khai thiên lệch thay vì gọi mẫu cân bằng.81646 DOI thiếu,32 DOI nguồn chưa chuẩn hóa đơn,7928 license PDF thiếu; giữ nguyên và báo rõ.23 nhóm DOI chung,42 nhóm title collision được báo, không xóa record.
- Bản xuất gồm v1/catalog.sqlite có FTS5, works.parquet, works.jsonl.gz, README, audit, dedup_report, manifest. Tất cả record được so raw nguồn đã chọn; SHA256 từng raw XML, schema/scope, SQLite integrity, full round-trip JSONL/Parquet đạt. Version PDF vẫn null/ghi rõ chưa pin, metadata CC0 không chuyển thành quyền PDF.
- Kiểm độc lập session72450 exit0: SHA256/bytes mọi file release và87raw nén/giải nén đạt; từng100884 record khớp SQLite JSONL Parquet, đủ trường/ID duy nhất, không có nhãn QA/PDF, FTS tìm attention có kết quả. Report data/catalog/verification_v1.json passed=true; manifest SHA256 cddf0ee0ac8e9034ccb6d328ac927a3ce70fda121edfa4af301185b64620d197. Chạy lại5 test_catalog tests PASS, có test corrupt raw từ chối publish và FTS query.
- Dung lượng: release716835267 byte (~683,6MiB); toàn catalog kèm staging/raw/snapshot ~1087694768 byte (~1,01GiB, thay đổi vài KiB khi ghi status/report). Project logical3,714GiB, ổ còn348,96GiB: đạt guardrail70GiB project và30GiB free. Không tải PDF, chạy model, gửi email hoặc dùng thêm API có khóa.
- Cập nhật docs/CATALOG_V1.md với số liệu/file/cách tìm/giới hạn, liên kết từ README và cập nhật mục B trong plan V2.1. status.json được chốt released với đường dẫn v1 và verification. Kiểm link local tài liệu và gates cuối đều đạt. Không chỉnh snapshot đã freeze; metadata OpenAlex/Corpus C là các việc để sau, không còn hạng mục Catalog B V1 bắt buộc dở. Goal đủ điều kiện complete.


## 2026-10-23 16:00:31 +07:00 — Khởi động Corpus C V1 (Asia/Saigon)
- Yêu cầu/goal: tiếp tục Corpus C theo plan, mục tiêu2000PDF, pilot100 rồi500 có đo storage/parse/index. Đọc plan7–9, parser/chunker/representations/embeddings và downloader benchmark cũ; đọc lại skill PDF cho kiểm nguồn, chỉ read/render/extract nên không chạy marker authoring. Tra tài liệu chính thức arXiv terms/license và kiểm candidate/license trong catalog. Không tạo agent hoặc chạy Qwen/GPU.
- Phát hiện đính chính ngày nguồn: arxiv0705.4348 OAI created2026-02-18 nhưng Atom published2007-05-30, latestv2. Giá trị publication_year B đã copy theoOAI nên không bảo đảm năm đăng đầu. Giữ snapshot B/checksum bất biến, sửa docs/CATALOG_V1.md công khai ngữ nghĩa/đính chính; C lấy published vàversion từAtom, dùng nămID làm hint chọn cũ/mới. Lệnh SQL đầu query arxiv_id column không tồn tại lỗi read-only, đã sửa theo paper_id.
- Tạo src/corpus/collect.py: candidate6topic/quota100–500–2000, chọnCC BY/BY-SA3/4/CC0, canonicalgroup/title dedup, trộn ID cũ/mới; SQLite checkpoint/events; pin version qua Atom batch20 và giữXML/hash; downloadPDFexplicitversion, Range .part, SHA/size/page count, stamp nếu có, giới hạn50MiB/200trang, raw25GiB/corpus60GiB/diskfree30GiB, singleconnection3,2s. License lấymetadata/OAI, localuse chưaphânphốira ngoài. Candidatepool thực:5886AI,1466CV,1250NLP,330IR,7827Math,1851Systems.
- Tạo src/corpus/process.py: một workerCPU/subprocessPDFtimeout300s, backendPyMuPDF4LLM, fallbacktext cówarning, pages/source_text/blockbbox/chunks/page_signals/quality/MD vớisourcehash vàparserfingerprint. Chunks giữpaper/version/page/hash; quality đoảnhbáo/íttext/mathheuristic/time/RAM, không tự nhậnmath/code gold. Thêm tests/test_corpus.py, ignore corpus/manifests, docs/CORPUS_V1.md; cập nhật README vàplan mụcC đang pilot.
- Collector81751 tải5PDF rồi exit1 doPDF1908.11219v9 HTTP404; parser30446 đãparse5 rồi exit0 khicollector dừng. Sửa phânbiệt404/410permanent đểghi rejected_download vàlấyreplacement, khôngretryvôhạn/khôngđổiversion; thêmbackoffRetryAfter429/5xx. Chạy3test quota/license/year/errorclassification PASS. Resume collector99664 PIDthực32368, parser53674 --wait-for32368; cảhai handle pollxácnhậnsống. Không chạyjobtrùng khihandlecònsống.
- Mẫu2606.03553v1:40trang/80chunk, parse19,2s, peakprocess~106,7MB; đãrender/xemPDFtrang4 vàđối chiếuMD: côngthức3–6 mấtlayoutnorm/summation/bounds, cảnhbáo ký tựthaythế cósẵn. Ghi receiptAIvisual math_text_fidelity=failed,page_mapping_correct=true,ảnhnguồnrõ vào data/corpus/reviews/pilot_visual.jsonl vàảnhp4. Khônggọi texttoánverified; cần visualgrounding vàbáocáolỗipilot trước mởrộng. Một lần inMDconsolecp1252 lỗi saukhighirender, đãđọc lại UTF8; khôngmất dữliệu.
- SnapshotcuốiSQL:22PDF/640trang/~102,34MiB,8parsed tại lầnđọc (pollsauđó thêm1parsed); quick_check đạt;1rejecteddownload. Cácfileđangtăng nên khôngfreezecountnày. Cònlại:theodõicollector99664/parser53674, hoànthànhpilot100 vàkiểmảnhđủtopic, reportgates/resourcestats, bổsungindexCPU/dense+BM25 vớiPDFvisualfallback, rồi500→2000/auditmanifestV1. GoalC vẫnactive, chưahoànthànhV1.


## 2026-10-23 16:57:28 +07:00 — Corpus C: chốt pilot 100 và mở rộng 500 (Asia/Saigon)
- Goal vẫn là Corpus V1 2.000 PDF. Lượt trước có tiến bộ thật; poll đúng collector99664/parser53674 xác nhận đang sống, từ33 PDF lên100. Collector kết thúc exit0 đúng quota25/15/15/10/23/12; parser kết thúc exit0 đủ100, không có fallback/parse_failed trong pilot. Hai paper/version1908.11219v9 và2412.06528v5 trả404, giữ error/rejected ledger, lấy candidate khác, không đổi sang version cũ. Không chạy code từ PDF hoặc gọi Qwen/GPU.
- Tạo src/corpus/index.py: SQLite FTS5 BM25, E5 CPU dense và hybrid RRF; snapshot bất biến, chunks.parquet/papers/quality/manifest, memmap vector theo row ID, cache vector theo content+model fingerprint, lock builder. Kiểm PDF/resolver/sidecar SHA trước build; chuẩn hóa primary_topic Corpus và giữ catalog_primary_topic; cập nhật workflow sau publish có guard payload cũ để tránh đè thay đổi đồng thời. Thêm src/corpus/audit.py và smoke.py kiểm từng artifact/vector/page/metadata và truy vấn diagnostic.
- Probe model27699 chờ HEAD HF/config_sentence_transformers và retry server disconnect; đã dừng có chủ đích sau xác nhận weights có cache. Offline probe71962 load được nhưng model config _commit_hash=None nên assert thất bại; sửa xác định commit từ đường dẫn snapshot config cục bộ, kiểm không đổi main ref trong lúc nạp, fingerprint trọng số/tokenizer/modules/pooling/max_seq_length. Probe30134 offline thành công revision614241f622f53c4eeff9890bdc4f31cfecc418b3; không cần HF token. Snapshot dùng CPU float32 normalized, prefix passage/query đúng app.
- Các watcher chờ parser6284 lần lượt73901/92859 đã dừng có chủ đích trước build để cập nhật fingerprint/schema. Watcher86304 xây pilot100 đủ5.093 chunk rồi exit0 (lệnh Ctrl-C cuối tới sau khi job đã hoàn tất); giữ nguyên prototype, không ghi đè. Kiểm mẫu phát hiện NLP |x| bị heuristic nhận nhầm bảng và math không warning vẫn mất symbol; sửa visual policy dựa bảng Markdown thật/caption + PDF images/drawings/math/monospace fonts, query math/code/table/figure buộc nguồn ảnh. Build revision mới pilot100_visual session41204 bằng cache, exit0; giữ đầy đủ snapshot cũ.
- 5 tests corpus pass sau sửa fixture visual test quên clear parse_warning (một lần test fail do fixture, đã sửa). Source build xuất hiện MuPDF unsupported Screen annotation warnings, không bị che; raw PDF vẫn nguyên. Tạo active_100 pointer chỉ sau audit đạt. docs/CORPUS_V1.md, README, plan cập nhật milestone, cách query, giới hạn và phase500.
- Pilot thực:100 PDF/2.250 trang/5.093 chunk; raw313.860.452 byte, parsed65.883.171 byte, index56.826.544 byte. Peak parser tối đa1.004.830.720 byte (~0,94GiB), tổng parse~1.030s. 674 warnings/8.935 replacement characters;48 dense candidates là heuristic, không phải nhãn gold. Initial encode+build663,46s; visual revision cache rebuild45,26s, không nhận45s là encode mới.
- Visual AI review thêm5 topic pages và Algorithm1 page12: tổng7 trang/6 paper, source mapping/render rõ. CV bảng giữ số mẫu nhưng gộp hàng bằng br; NLP công thức trùng span và sai superscript không có warning; IR sơ đồ không nằm trong Markdown; Math mất phân biệt tilde sigma; pseudocode1–14 giữ line/branch text nhưng mất indentation/subscript. Đã lưu receipts và ảnh ở data/corpus/reviews. Tất cả chunk của5 page kiểm bổ sung được visual routed. Đây là spot-check AI, không suy tỷ lệ lỗi population; math text chưa verified.
- Audit40902 exit0: toàn bộ PDF/version/published Atom/sidecar/SQLite/Parquet/normalized vector/row mapping/quota/SHA đạt;4.608 chunk visual-source; dữ liệu không có QA label. Project~4,57GB, free~371,5GB. Dự phóng2.000:6,277GB raw +1,318GB parsed +1,137GB index, trong ngân sách; cần đo lại500. Report audit_pilot100_visual.json và active pointer manifest SHA ebd1c5615f0004a8fc171e40c0ca3c65a92c98cdcaadf264f7c505a332ff47a7.
- Smoke16687 exit0: ba vector encode lại cosine~1; BM25/dense/hybrid đều6/6 title-query hit@5 (first paper by ID mỗi topic). Đánh dấu diagnostic_only/not_qa_benchmark, không gọi official QA score. Lưu reports/smoke_pilot100_visual.json và pilot100_promotion.json với math/source limitations và near-text dedup còn phải kiểm trước V1 cuối. Kiểm liên kết local tài liệu đạt.
- Đã khởi động phase500 bằng Start-Process -WindowStyle Hidden, logs/registry bền qua lượt: collector PID28444, registry collect500-20261023T164846027.json; parser PID14540 --limit500 --wait-for28444, registry parse500-20261023T165127731.json. Registry có process_create_time; kiểm psutil đúng module/PID/create-time và cả hai sống. Snapshot lúc kiểm có154 PDF (100 indexed +4 parsed +50 downloaded), không coi là500 hoàn tất.
- Còn lại: theo dõi hai PID/logs phase500; có thể thêm embedding cache worker CPU batch nhỏ để chạy cùng parser một worker, giữ model fingerprint; audit/smoke/near-text duplicates và chất lượng500 rồi lên2.000. Cần final corpus manifest/audit/source visual review và đầy đủ retrieval index V1. Chưa complete goal, không thu hẹp thành chỉ pilot100.


## 2026-10-23 17:04:31 +07:00 — Đọc hiểu context dự án (Asia/Saigon)
- Yêu cầu: đọc hiểu context Deep Research AI Assistant. Đã đọc README, plan V2.1 (mục tiêu/pipeline/gates), docs/CORPUS_V1.md, CATALOG_V1.md, BENCHMARK_DATASET_SUMMARY.md và các mục log gần nhất; rà danh sách src, config, ingest/retriever và điểm gọi model/citation trong app/llm.
- Nắm kiến trúc local Streamlit → parse/chunk → E5 CPU + BM25/hybrid → Qwen/Ollama; phân biệt benchmark A, catalog B và corpus C. Theo tài liệu: A có 5.549 QA, B phát hành 100.884 record/100.841 canonical groups, C chốt pilot100 với 2.250 trang/5.093 chunk và đã khởi động phase500, mục tiêu cuối 2.000 PDF. Giữ rõ AI-review không phải expert gold; visual routing không chứng minh fidelity toán/code; không index nhãn benchmark.
- Kiểm tra: git status chỉ đọc cho thấy workspace có nhiều thay đổi sẵn, giữ nguyên. Một số lượt đọc bị cắt output và console hiển thị sai UTF-8; đã đọc lại phần cần thiết bằng UTF-8 và giới hạn đoạn. Không sửa code/dữ liệu, không cài đặt, không khởi động/dừng dịch vụ, không chạy tests/model hoặc audit lại số liệu. Chỉ nối log theo quy định.
- Còn lại: trạng thái phase500/process và SciCode numeric là thông tin lịch sử từ tài liệu, chưa kiểm tra live trong yêu cầu đọc context này; không tuyên bố corpus V1 hoàn tất. README/config hiện dùng RTX2060/Qwen2b trong khi plan ghi RTX4050 và runner có mặc định4b, cần đối chiếu môi trường thực khi triển khai tiếp.

## 2026-10-23 17:05:46 +07:00 — Xác nhận mô tả MVP (Asia/Saigon)
- Yêu cầu: xác nhận phát biểu hệ thống cơ bản nhận PDF và dùng LLM trả lời câu hỏi trên file được cung cấp. Đối chiếu README, app/config/ingest/retriever/llm đã đọc trong lượt trước: phát biểu phù hợp phạm vi single-PDF QA hiện có; đề xuất diễn đạt rõ tài liệu được tải lên và trích dẫn theo trang.
- Không sửa code/dữ liệu, không chạy app/model/tests trong lượt này; xác nhận phạm vi chức năng từ tài liệu/code, không chứng nhận độ chính xác mọi câu trả lời hay trạng thái runtime hiện tại.


## 2026-10-23 17:10:12 +07:00 — Tài liệu chi tiết MVP hỏi đáp PDF (Asia/Saigon)
- Yêu cầu: tạo một file Markdown hoàn toàn chi tiết về hệ thống cơ bản nhận PDF và LLM trả lời trên tài liệu được chọn. Đọc/đối chiếu app, llm, parser, ingest, embeddings, chunker, retriever, storage, evaluate, requirements và tests/README; sử dụng README/config/plan và docs đã đọc ở các lượt trước. Một output gộp bị cắt, đã đọc lại các đoạn luồng QA/parse/ingest cần thiết.
- Tạo docs/MVP_PDF_QA.md (344 dòng, 17 mục): phát biểu báo cáo/slide, phạm vi, Mermaid kiến trúc, UX, validation/SHA/cache/artifact, chunking/dense/BM25/RRF, ảnh nguồn, prompt, giới hạn hội thoại/citation, công nghệ/cấu hình, cài/chạy, protocol đánh giá/demo, giới hạn và roadmap, liên kết nguồn. Phân biệt code đã có với kết quả runtime chưa đo; không gọi AI-review là expert gold, không gán corpus vào UI single-PDF.
- Kiểm tra: toàn bộ liên kết local tồn tại; 10 code fences cân bằng theo số lượng; đọc lại retriever xác nhận topK/RRF/neighbor phù hợp cấu hình. Git status xác nhận tài liệu mới; giữ nguyên các thay đổi sẵn có. Không chạy app/model/tests, không cài hoặc điều khiển dịch vụ; không sửa code/dataset. Tài liệu đã hoàn tất trong phạm vi yêu cầu; demo và benchmark là hướng dẫn chưa thực hiện.


## 2026-10-23 17:24:47 +07:00 — Giải thích chi tiết pipeline PDF QA
- Yêu cầu: nói kỹ các bước parse, chunk, E5, hybrid retrieval, LLM, ảnh nguồn, Sources và citation trong MVP. Đối chiếu implementation src/parser.py, chunker.py, embeddings.py, retriever.py, llm.py, app.py và config.py.
- Mở rộng deep-research-ai-ressitant/docs/MVP_PDF_QA.md tại các mục 6.3–6.4, 7.1–7.3, 8.1–8.2, 9.1–9.2: mô tả input/output, cách tạo vector và cosine, top-12/RRF k=60/literal tie-break/top-4 + neighbor tới 6, giới hạn context, nhánh ảnh/anchor, nội dung Sources và giới hạn citation. Thêm ví dụ minh họa tìm kiếm; không thay code hoặc dataset.
- Kiểm tra tài liệu: 376 dòng, liên kết nội bộ đều tồn tại, code fences cân bằng. Không chạy tests/model/app; đây là cập nhật tài liệu. Còn giới hạn fidelity parser, heuristic ảnh, và citation semantic đã ghi rõ. Một lần append log đầu tiên dùng nhầm cwd project cha nên thất bại do không tìm thấy docs/AGENT_LOG.md; đã chạy lại bằng đường dẫn đúng và ghi mục này.



## 2026-10-23 17:27:48 +07:00 ? Ti?p t?c Corpus C: x? l? stage 500 (Asia/Saigon)
- Goal v?n l? Corpus C V1 ?? 2.000 PDF theo plan. ??c l?i ph?n C, quota/topic v? gate dung l??ng trong plan V2.1, ??i chi?u docs/CORPUS_V1.md v? quy t?c AGENTS.md do ng??i d?ng cung c?p.
- X?c minh process theo PID, create-time v? module: collector ?? k?t th?c v?i `DOWNLOAD STAGE COMPLETE 500`; parser, cache worker v? index waiter c?n s?ng ([('src.corpus.process', 14540, True), ('src.corpus.cache_embeddings', 2660, True), ('src.corpus.index', 15380, True)]). Kh?ng kh?i ??ng tr?ng. SQLite hi?n {'candidate': 18068, 'downloaded': 300, 'indexed': 100, 'parsed': 100, 'rejected_download': 3, 'resolved': 39}; theo topic quota ???c ch?t (ai_ml=125; computer_vision=75; nlp_llm=75; information_retrieval=50; math_stats=112; systems_algorithms=63); parse_failed=0. Ba PDF b? lo?i l? hai version arXiv tr?404 v? m?t file qu?50MiB.
- Cache ti?n tri?n ??n 195/500 paper (100 cache hits, 95 encode m?i), model fingerprint `f2c9907b816f792df8812908ef195140f87b234e80f56b85942e51c7e26becb9`, 4 thread, peak RSS 1574543360 byte. C?c l?n poll x?c nh?n log parser/cache t?ng v? ti?n tr?nh con CPU ?ang ch?y.
- ??c report dedup pilot100: 100 paper, 0 exact groups, 0 candidate near-duplicate, kh?ng auto-merge.
- C?p nh?t docs/CORPUS_V1.md: c?ch d?ng cache worker/index waiter/dedup, n?i l?u cache/report v? s? test corpus hi?n l?7; kh?ng ch?y l?i tests ? l??t n?y. Hai patch r?ng kh?ng kh?p context v? hai l?nh ??c ??u ch?y nh?m ? th? m?c project cha; ??u kh?ng s?a d? li?u, ?? ??c/?p d?ng l?i b?ng path/context ??ng. Kh?ng x?a d? li?u, kh?ng ch?y Qwen/GPU, kh?ng ghi secret.
- C?n l?i: ??i parser/cache ??500, index waiter build; audit d? li?u/ngu?n/hash/quota/row mapping/storage, smoke v? dedup/review visual tr??c khi n?ng l?n2.000. Goal ch?a ho?n t?t.
- B? sung c?ng y?u c?u: m?t l?n `apply_patch` ri?ng cho c?y th? m?c c?ng kh?ng kh?p context; script Python c? assertion kh?p ??ng m?t v? tr? ?? c?p nh?t th?nh c?ng. Kh?ng c? d? li?u n?o b? s?a b?i patch l?i.


## 2026-10-23 17:31:00 +07:00 ? Ti?p t?c Corpus C, theo d?i stage 500 (Asia/Saigon)
- Goal gi? nguy?n Corpus C V1 ??2.000 PDF. Ki?m tr?ng th?i SQLite v? x?c th?c PID/create-time/module c?a parser, cache v? index waiter; collector log c? DOWNLOAD STAGE COMPLETE 500. Tr?ng th?i th?t: ['src.corpus.process PID 14540: s?ng', 'src.corpus.cache_embeddings PID 2660: s?ng', 'src.corpus.index PID 15380: s?ng'].
- SQLite: {'candidate': 18068, 'downloaded': 288, 'indexed': 100, 'parsed': 112, 'rejected_download': 3, 'resolved': 39}; parse_failed=0. Cache worker ?? x? l? 212/500 paper (100 vector hit pilot, 112 paper encode m?i), model fingerprint `f2c9907b816f792df8812908ef195140f87b234e80f56b85942e51c7e26becb9`, 4 CPU threads, peak RSS 1580507136 byte. Cache ?? b?t k?p 112 paper parse m?i c?ng100 pilot; indexer ti?p t?c ch? cache worker.
- `status.json` v?n ghi stage collecting t? l?n c?p nh?t c?; kh?ng d?ng file n?y l?m b?ng ch?ng ti?n tr?nh. Log collector, SQLite v? ti?n tr?nh th?c x?c nh?n stage download ho?n t?t c?n parse/index ?ang ch?y.
- L??t n?y ch? ki?m tra tr?ng th?i v? ch? ti?n tr?nh t?ng t? 103 l?n112 parsed; kh?ng s?a file/dataset ho?c ch?y test. C?n l?i: ??500 parse+cache, index/audit/smoke/dedup v? ki?m sample PDF, sau ?? m?i m? r?ng l?n2.000. Goal ch?a ho?n t?t.

## 2026-10-23 17:32:03 +07:00 — Làm rõ xử lý code/math tại bước trích xuất PDF
- Yêu cầu: làm rõ ở bước 1 (parse PDF) code/math có khác văn xuôi không. Đối chiếu src/parser.py và chunker/representations: một lời gọi PyMuPDF4LLM trả Markdown theo trang; không có parser toán/code tách biệt trong bước này. Phân loại/biểu diễn phụ trợ ở chunking và ảnh nguồn ở QA.
- Cập nhật docs/MVP_PDF_QA.md mục 6.3–6.4: giải thích code/math cùng qua parser, Markdown/LaTeX có thể giữ một phần nhưng không bảo đảm fidelity, không gọi OCR riêng trong luồng này; phân biệt với heuristic nhận diện chunk sau parse.
- Không chạy app/model/tests; kiểm tra bằng đối chiếu mã nguồn. Việc còn lại: người dùng cần đối chiếu trang gốc khi độ chính xác công thức/code quan trọng.


## 2026-10-23 17:34:22 +07:00 — Đối chiếu log về model MER cho công thức
- Yêu cầu: kiểm tra log xem đã thử model MER cho toán/công thức hay chưa. Tìm trong AGENT_LOG.md, WORKLOG-2026-10-20.md và tài liệu/mã nguồn liên quan.
- AGENT_LOG không ghi đã chạy MER. WORKLOG-2026-10-20.md mục 7–8 ghi app gửi ảnh trang PDF cho Ollama khi hỏi toán/code (không phải MER/OCR chuyên dụng), đã tham khảo UniMERNet và PaddleOCR Formula Recognition, nhưng trong phiên đó chưa cài/chạy model MER trên hai PDF. LaTeX candidate chỉ heuristic trên text parser. Hit@5 retrieval 100% Adam và 92,3% FlashAttention được ghi là retrieval, không phải độ chính xác nhận dạng công thức.
- Chỉ đọc tài liệu và nối log; không cài/chạy model hoặc tests. Không còn việc kỹ thuật bắt buộc trong yêu cầu này.



## 2026-10-23 17:36:35 +07:00 ? Corpus C: x? l? PDF timeout trong stage 500 (Asia/Saigon)
- Revalidate process PID/create-time/module v? SQLite: collector ?? xong 500; ['src.corpus.process PID 14540: live', 'src.corpus.cache_embeddings PID 2660: live', 'src.corpus.index PID 15380: live']. DB hi?n {'candidate': 18068, 'downloaded': 269, 'indexed': 100, 'parsed': 131, 'rejected_download': 3, 'resolved': 39}; parse_failed=0; cache 230/500 (100 hit, 130 encode m?i).
- Parser g?p PDF `arxiv:2101.08345` v??t timeout300s. L?nh fallback ho?n t?t th?nh c?ng; quality ghi backend `pymupdf_sorted_text_fallback`, 15 trang/43 chunks, 15 warning v? l? do fallback layout math/table/code ch?a verified. Ki?m SHA sidecars c? trong `quality.json`; PDF/hash g?c gi? nguy?n. Process tree sau timeout kh?ng c?n worker m? c?i, parser ?? ti?p t?c paper k? ti?p.
- T? l?n ki?m tr??c stage ti?n t?112 l?n131 paper parsed v? cache t?212 l?n230; ch?a s?a code/dataset v? kh?ng ch?y test. C?n visual-review PDF fallback khi review m?u 500. C?n l?i: ?? parse/cache/index stage500, audit/smoke/dedup v? ki?m ngu?n ?nh, sau ?? m? r?ng t?i2.000. Goal v?n active.


## 2026-10-23 17:37:56 +07:00 ? Corpus C: ti?p t?c parse/cache stage 500 (Asia/Saigon)
- Ki?m l?i collector/parser/cache/index b?ng PID, create-time v? command line: collector ?? k?t th?c v?i complete marker; ['src.corpus.process 14540: live', 'src.corpus.cache_embeddings 2660: live', 'src.corpus.index 15380: live']. SQLite hi?n {'candidate': 18068, 'downloaded': 253, 'indexed': 100, 'parsed': 147, 'rejected_download': 3, 'resolved': 39}, parse_failed=0. Parser log m?i nh?t: `['arxiv:2512.04358 parsed 7 16 pymupdf4llm', 'arxiv:2003.06254 parsed 17 30 pymupdf4llm', 'arxiv:2511.21582 parsed 10 17 pymupdf4llm']`; cache event m?i nh?t `['{"paper_id": "arxiv:2512.04358", "pdf_sha256": "4e09dd2aa9485fa9153fa5ff15ba9b4e04919202be8c68999d19a3430de22328", "cache_hit": false, "seconds": 2.4261982000025455, "chunks": 16, "model_fingerprint": "f2c9907b816f792df8812908ef195140f87b234e80f56b85942e51c7e26becb9", "threads": 4, "completed": 245, "at": "2026-10-23T10:37:47.860510+00:00"}']`; cache progress 245/500, 100 hit v? 145 encode m?i.
- Theo d?i PDF `arxiv:2101.08345`: parse PyMuPDF4LLM v??t timeout300s, sau ?? fallback t?o 15 trang/43 chunks, backend `pymupdf_sorted_text_fallback`, SHA PDF/sidecars c? trong quality v? cache ghi vector. Kh?ng c?n worker m? c?i; parser ti?p t?c paper kh?c.
- ??c `process.py` v?ng parse_one/coordinator: `elapsed_seconds` trong fallback quality ?o ri?ng l?n fallback (~8.070709699997678 gi?y), ch?a c?ng l?n th? b? timeout300s. ??y l? sai l?ch metric t?i nguy?n ?? ph?t hi?n; gi? nguy?n d? li?u trong l?c pipeline ch?y, c?n b?o c?o/?i?u ch?nh minh b?ch tr??c gate500 v? b?o ??m telemetry ch?nh x?c cho batch2.000. Kh?ng s?a code/dataset v? kh?ng ch?y tests ? l??t n?y.
- C?n l?i: ho?n t?t500 parse+cache/index, audit quota/hash/sidecars/index/resources, smoke/dedup v? review PDF fallback/visual sample; sau ?? m? r?ng t?i2.000. Goal ch?a xong.


## 2026-10-23 17:38:54 +07:00 ? Corpus C: ti?p t?c stage 500 v? ghi ch? telemetry (Asia/Saigon)
- Revalidate process registry, log v? SQLite: collector complete=True; ['src.corpus.process 14540=live', 'src.corpus.cache_embeddings 2660=live', 'src.corpus.index 15380=live']. Tr?ng th?i paper={'candidate': 18068, 'downloaded': 246, 'indexed': 100, 'parsed': 154, 'rejected_download': 3, 'resolved': 39}, parse_failed=0. Cache progress 253/500 (100 vector pilot reuse, 153 encode m?i), model fingerprint `f2c9907b816f792df8812908ef195140f87b234e80f56b85942e51c7e26becb9`. Kh?ng restart worker ?ang s?ng.
- ??c `src/corpus/process.py` ?? ??i chi?u timeout=300 v?i `parse_one` v? quality timer; ??c quality sidecar c?a `arxiv:2101.08345`: timeout r?i fallback 15 trang/43 chunk, warning layout, sidecar checksums h?p l?, vector ?? cache. Theo d?i x?c nh?n parser ti?p t?c c?c PDF sau ??, kh?ng c?n worker con m? c?i.
- S?a `docs/CORPUS_V1.md` ?? c?ng khai `elapsed_seconds` c?a fallback kh?ng c?ng l??t b? timeout, kh?ng d?ng metric hi?n t?i l?m t?ng parse time; n?u paper c?n visual review. ?? ??c l?i t?i li?u x?c nh?n ?o?n ???c th?m. M?t l?n x?c nh?n ?o?n b?ng literal Unicode trong script th?t b?i do encoding ??u v?o; ki?m l?i b?ng `rg` v? ch?y ti?p kh?ng s?a d? li?u. Kh?ng s?a PDF/parsed sidecar, kh?ng ch?y tests.
- C?n l?i: ho?n t?t parse/cache/index500, audit hash/quota/storage, smoke/dedup v? visual review; x? l? telemetry minh b?ch tr??c khi m? r?ng ??n2.000. Goal ch?a ho?n t?t.


## 2026-10-23 17:41:16 +07:00 ? Corpus C: resource check trong l?c stage 500 ch?y (Asia/Saigon)
- Revalidate worker: ['src.corpus.process:14540=True', 'src.corpus.cache_embeddings:2660=True', 'src.corpus.index:15380=True']; SQLite={'candidate': 18068, 'downloaded': 223, 'indexed': 100, 'parsed': 177, 'rejected_download': 3, 'resolved': 39}, parse_failed=0; cache=277/500, 100 hit+177 new. Collector complete marker v?n c? trong log.
- ?o resource tr?c ti?p: raw 1410159117 B (1.313 GiB); parsed 183034109 B (0.170 GiB); index 113635481 B (0.106 GiB); embeddings 20527457 B (0.019 GiB); corpus 1813573256 B (1.689 GiB); project g?m venv 5804587526 B (5.406 GiB); disk free 363202838528 B (338.259 GiB). Guardrail 25GiB raw/15GiB parsed/7GiB index/70GiB project v?30GiB free hi?n ??t; parsed/index v?n l? s? gi?a ch?ng.
- Raw c? 501 file PDF/part; c?n `[('data\\corpus\\raw\\06abc583ec9ac1df7e3b0a88\\v1\\paper.part', 53477376)]` l? file `.part` ch?a ???c x?c minh li?n k?t t?i paper. Kh?ng x?a theo quy t?c gi? d? li?u. SQLite ghi m?t ?ng vi?n over50MiB b? reject, nh?ng collector stdout ch?a ch?ng minh `.part` ?? thu?c ?ng vi?n ?y.
- L?n ??u `psutil.disk_usage(Path)` l?i ki?u tham s? tr?n Windows; ch?y l?i v?i `str(Path)` th?nh c?ng, kh?ng s?a d? li?u. C?n l?i: ch? stage500 ho?n t?t, audit/smoke/dedup, x? l? telemetry timeout r?i m? r?ng ??n2.000. Goal ch?a xong.


## 2026-10-23 17:43:35 +07:00 ? Corpus C: verified wait tr?n stage 500 (Asia/Saigon)
- Ki?m l?i process registry/PID/create-time/cmdline v? SQLite; collector complete=True; worker=['src.corpus.process:14540=True', 'src.corpus.cache_embeddings:2660=True', 'src.corpus.index:15380=True']; paper state={'candidate': 18068, 'downloaded': 212, 'indexed': 100, 'parsed': 188, 'rejected_download': 3, 'resolved': 39}; parse_failed=0. Kh?ng d?ng status.json c? l?m b?ng ch?ng live.
- Poll parser/cache sau khi c? hai ???c x?c nh?n s?ng: parser ti?n t?177 l?n188 paper m?i; cache l?n287/500 (100 vector pilot cache hit + 187 encode m?i). Index waiter c?n ch? cache. Ch?a c?n restart hay thay ??i d? li?u.
- Kh?ng s?a code/dataset, kh?ng ch?y tests. C?n l?i: parser/cache ??500, index build, audit/smoke/dedup/visual review v? telemetry timeout, r?i m? r?ng t?i2.000. Goal ch?a xong.


## 2026-10-23 17:46:09 +07:00 ? Corpus C: theo d?i ti?p stage500 (Asia/Saigon)
- X?c minh l?i collector/parser/cache/index b?ng PID, create-time v? module; collector download complete=True; live=['src.corpus.process:14540=True', 'src.corpus.cache_embeddings:2660=True', 'src.corpus.index:15380=True']. SQLite states={'candidate': 18068, 'downloaded': 197, 'indexed': 100, 'parsed': 203, 'rejected_download': 3, 'resolved': 39}, parse_failed=0.
- Sau verified wait hai l?n parser t?ng t?189 l?n203 paper m?i; cache t?ng t?287 l?n303/500 (100 hit, 203 encode m?i). Indexer v?n ch? cache; kh?ng restart ho?c s?a d? li?u khi workers c?n s?ng.
- Kh?ng c? thay ??i code hay test trong l??t n?y. C?n l?i: ho?n th?nh parse/cache/index 500, audit d? li?u/ngu?n/quota/resources, smoke/dedup/visual review, sau ?? ti?p t?c corpus2.000. Goal ch?a ho?n t?t.

## 2026-10-23 17:48:37 +07:00 — Giải thích cách phân loại chunk math
- Yêu cầu: giải thích code hiện quyết định đoạn nào là math. Đọc src/chunker.py _classify, src/representations.py looks_like_math/uild_representations, nhánh needs_visual_evidence trong src/llm.py và test_representations.py.
- Xác nhận có hai heuristic: chunker hẹp gán type theo delimiter LaTeX/Equation/simple assignment, có kiểm code trước và fallback text; helper representations dò thêm Greek/Unicode math/subscript nhưng không đổi type. Nêu false positive/negative và phân biệt classification với MER. Bổ sung chi tiết này vào docs/MVP_PDF_QA.md mục 6.4.
- Kiểm tra Markdown: liên kết nội bộ đạt, 10 fence markers cân bằng. Lệnh rg ban đầu đưa đường dẫn tests/test_chunker.py không tồn tại nên trả exit 1; điều này chỉ là lỗi chọn file khi tìm, không chạy/thay đổi gì. Đã đọc test_representations.py đúng đường dẫn; không chạy tests/app/model.


## 2026-10-23 17:53:34 +07:00 — Đánh giá sơ đồ thêm UniMER cho math
- Yêu cầu: góp ý sơ đồ PDF→Markdown→chunk→text/code/math→embedding/data nếu chỉ thêm UniMER cho math. Đọc lại bối cảnh classifier hiện tại; tra README chính thức UniMERNet và PDF-Extract-Kit.
- Kết luận: hướng phân nhánh math hợp lý, nhưng UniMERNet nhận ảnh vùng công thức và xuất LaTeX, không tự định vị/crop toàn bộ công thức trong trang. Cần bước detect/crop (hoặc crop thủ công cho pilot), giữ page/bbox/hash và raw text+image, thêm LaTeX prediction vào embedding text, không thay nguồn gốc. PDF-Extract-Kit phân biệt formula detection và formula recognition. Model weights trong README có các mức 441MB/773MB/1.3GB; đây là dung lượng weights, chưa xác nhận VRAM/latency trên máy dự án. Chính thức khuyên môi trường Conda sạch Python3.10; chưa kiểm tra compatibility với env Python3.11/CPU torch của dự án.
- Không sửa repo, không cài hoặc chạy UniMER; không chạy tests. Tham chiếu: https://github.com/opendatalab/UniMERNet và https://github.com/opendatalab/PDF-Extract-Kit.


## 2026-10-23 17:55:43 +07:00 — Giải thích luồng xử lý một câu hỏi PDF
- Yêu cầu: diễn giải kỹ luồng từ lúc người dùng gửi một câu hỏi. Đọc đúng nhánh app.py, src/retriever.py, src/llm.py.
- Theo code: chat input lưu câu hỏi vào session display; retrieve trên PDF đang chọn nạp chunks/vectors, dựng BM25, embed query, kết hợp thứ hạng RRF, chọn top-K và neighbor; ghi retrieval log; chọn/render ảnh nguồn theo từ khóa/type/anchor; lọc context nếu có ảnh; tạo prompt và gọi Ollama; kiểm format/tập trang citation; hiển thị answer/source/warning/latency; ghi QA/resource log. Lịch sử chat cũ không truyền vào prompt model.
- Chỉ đọc source để giải thích, không sửa tài liệu/code, không chạy app/model/tests. Cần lưu ý: anchor equation/algorithm có thể tìm trang trực tiếp trong PDF; citation checker xác nhận trang trong evidence/images chứ không xác minh claim.



## 2026-10-23 18:01:57 +07:00 ? Corpus C: verified progress stage500 (Asia/Saigon)
- Collector end marker=True; parser/cache/index worker status by PID/create-time/module=['src.corpus.process:14540=True', 'src.corpus.cache_embeddings:2660=True', 'src.corpus.index:15380=True']. SQLite states={'candidate': 18068, 'downloaded': 114, 'indexed': 100, 'parsed': 286, 'rejected_download': 3, 'resolved': 39}, parse_failed=0.
- Trong c?c l?n poll ?? x?c nh?n worker s?ng, parse m?i t?ng t?203 l?n(286,) (100 paper pilot v?n indexed); cache t?ng t?303 l?n380/500, g?m100 reuse+280 encode. Indexer c?n ch? cache. Kh?ng restart worker v? kh?ng c? l?i parse.
- Kh?ng s?a code/d? li?u ho?c ch?y tests ? l??t n?y. C?n l?i: ho?n th?nh parse/cache500, index snapshot, audit quota/source/hash/storage, smoke/dedup/visual review, r?i ti?p t?c t?i2.000 PDF. Goal ch?a ho?n t?t.
- Ghi ch? ??nh d?ng c?ng m?c: gi? tr? `parsed` ???c in th?nh tuple `(286,)` do d?u ph?y trong f-string; s? SQLite ch?nh x?c l?286. Kh?ng ?nh h??ng tr?ng th?i ho?c d? li?u.

## 2026-10-23 18:04:11 +07:00 — Rà soát sơ đồ luồng câu hỏi của người dùng
- Yêu cầu: đánh giá sơ đồ Câu hỏi→embedding→4–6 chunk→Prompt→Qwen 3.5 4B→citation check. Đối chiếu config.py, README.md, MVP_PDF_QA và WORKLOG.
- Sơ đồ đúng khái quát nhưng nên thêm BM25 + dense/RRF, nêu 4 chunk chính và neighbor tối đa 6, chỉ rõ math/code là ảnh trang/crop từ PDF gốc, prompt gồm question+chunks+ảnh tùy điều kiện, và đầu ra UI answer+sources. config mặc định qwen3.5:2b; biến DEEPRESEARCH_MODEL hỗ trợ đặt 4b và WORKLOG ghi lượt thử 4B, nên ghi 4B nếu mô tả run cụ thể.
- Chỉ đọc tài liệu/cấu hình, không sửa hình/code, không chạy app/model/tests.


## 2026-10-23 18:07:53 +07:00 — Khởi chạy lại app để người dùng test Qwen 3.5 4B
- Yêu cầu: chạy lại app. Kiểm tra project config: port 8502, venv tồn tại, trước đó port chưa có listener. Ollama API local reachable, qwen3.5:4b đã có; không tải model.
- Lệnh Start-Process nền ban đầu bị policy chặn trước khi chạy. Dùng phiên terminal tool 84421 thay thế: đặt DEEPRESEARCH_MODEL=qwen3.5:4b cho process, chạy Streamlit trên 127.0.0.1:8502 headless. Phiên còn sống sau poll.
- Xác minh /_stcore/health trả 200 ok, / trả 200; model inference chưa được gọi để người dùng tự test. URL: http://127.0.0.1:8502. Không thay đổi code hoặc dataset.


## 2026-10-23 18:16:15 +07:00 — Chọn một paper để test truy xuất pseudocode
- Yêu cầu: chọn một paper phù hợp để người dùng thử app hỏi đáp trên nội dung code.
- Đã rà README bộ test và danh sách PDF/câu hỏi FlashAttention; xác nhận paper này chứa pseudocode thuật toán, không phải mã nguồn Python/CUDA có thể chạy trực tiếp. Đọc `tests/flashattention.questions.json`; lần lọc đầu dùng nhầm thuộc tính `.value` nên không ra câu hỏi, đã chạy lại trên mảng JSON và xác nhận có 5 câu `type=code`.
- Đề xuất `tests/papers/flashattention-2205.14135v2.pdf`; câu mẫu `flash-code-01` hỏi vòng lặp Algorithm 1 duyệt gì và khi nào nạp K_j,V_j, ground truth ở trang 5. Không sửa code/dataset, không chạy model; còn lại người dùng tải PDF lên app để test.

## 2026-10-23 19:26:02 +07:00 — Làm rõ số lượng paper của Catalog B và Corpus C (Asia/Saigon)
- Yêu cầu: xác minh vì sao người dùng thấy số 2.000 paper trong Catalog V1 trong khi lượt harvest đạt khoảng 100.000. Đọc README, CATALOG_V1.md, CORPUS_V1.md, WORKLOG-2026-10-20.md và các mục liên quan trong AGENT_LOG.md; kiểm tra release, status, SQLite và JSONL.
- Xác nhận: database thu thập và snapshot `data/catalog/v1/catalog.sqlite` đều có 100.884 record; snapshot có 100.841 nhóm canonical; `works.jsonl.gz` có 100.884 dòng; `status.json` ghi `released`, target 100.000, papers 100.884. Số 2.000 trong CORPUS_V1.md là mục tiêu PDF của Corpus C. Số 2.567 trong AGENT_LOG.md là lần kiểm tra trung gian khi Catalog mới có 2 batch, không phải release cuối. Catalog chứa metadata; Corpus chọn và tải PDF từ catalog.
- Đọc/đếm chỉ đọc, kết quả khớp giữa SQLite, JSONL và status. Không sửa dữ liệu/code/tài liệu sản phẩm; không chạy tests. Không còn việc kỹ thuật cần làm cho câu hỏi này.

## 2026-10-23 19:32:29 +07:00 — Làm rõ ý nghĩa một record trong Catalog B (Asia/Saigon)
- Yêu cầu: xác nhận một record trong Catalog V1 có tương ứng một paper không.
- Trả lời dựa trên schema và docs: một record là metadata entry của một arXiv ID duy nhất; các version của cùng ID không tách thành record riêng. Các arXiv ID riêng biệt có thể chia sẻ canonical group khi DOI chuẩn hóa trùng; vì vậy 100.884 record tương ứng 100.841 nhóm canonical, không đồng nghĩa có đúng từng ấy công trình học thuật hoàn toàn độc lập.
- Chỉ giải thích khái niệm; không sửa dữ liệu/code/tài liệu sản phẩm, không chạy tests. Không còn việc khác.


## 2026-10-23 19:33:20 +07:00 — Đề xuất tên cho bộ dữ liệu tra cứu hỗ trợ LLM (Asia/Saigon)
- Yêu cầu: đề xuất cách gọi chuyên nghiệp, dễ nhớ cho bộ dữ liệu phục vụ tra cứu hỗ trợ LLM.
- Đề xuất `Research RAG Corpus` (bộ ngữ liệu truy xuất tri thức nghiên cứu cho LLM) cho phần paper đã tải/parse/chunk/index dùng trong RAG. Phân biệt `Research Paper Discovery Catalog` cho catalog 100.884 record metadata-only; tên gọi cả hệ thống có thể là `Research Knowledge Base for RAG`.
- Chỉ tư vấn tên, không sửa tài liệu sản phẩm/code/dataset, không chạy tests. Không còn việc khác.


## 2026-10-23 19:41:29 +07:00 ? Tiếp tục xây Corpus C, chốt gate stage 500 và chạy cohort 2.000
- Yêu cầu: tiếp tục xây Corpus C V1 theo mốc 100 → 500 → 2.000; ưu tiên dữ liệu, giữ nguyên snapshot đã kiểm.
- Kiểm tra tiến trình, SQLite, log và tài liệu Corpus C. Ban đầu audit pilot500 dừng ở pages.jsonl của arxiv:2005.07297. Checksum file khớp quality sidecar; JSON hợp lệ theo delimiter LF, có ký tự Unicode U+2028. Root cause là str.splitlines() tách U+2028 như một dòng.
- Sửa reader JSONL ở src/corpus/audit.py, cache_embeddings.py, index.py và dedup.py sang tách LF tường minh. Audit pilot500 đạt: 500 PDF, 10.955 trang, 24.813 chunks; quota đủ; hash/source/SQLite/Parquet/vector/storage đạt. Active pointer vẫn trỏ pilot500.
- Smoke đạt cả 6/6 query trên BM25, dense và hybrid. Dedup không thấy exact group hoặc review candidate.
- Render Poppler và xem trực quan một trang mỗi topic (6 trang, sáu paper). Cả 6 trang nguồn được đánh dấu visual; mọi chunk phủ trang đều bật visual grounding. Receipt: data/corpus/reports/visual_review_pilot500.json. Giới hạn: đây là spot-check, không xác minh ký tự công thức/toán trên toàn corpus.
- Cài Poppler 25.07.0-0 user-scope bằng winget; hash gói được xác minh. File render tạm do lượt này tạo đã xóa, giữ nguyên thư mục và file khác.
- Sửa process.py để elapsed_seconds của fallback tương lai cộng cả thời gian parser subprocess đã timeout. py_compile và import đạt. Các sidecar stage500 giữ nguyên; số arxiv:2101.08345 trong đó vẫn chỉ ghi khoảng 8 giây fallback và còn thiếu lần thử 300 giây.
- Cập nhật docs/CORPUS_V1.md với kết quả/dự phóng stage500, delimiter LF/U+2028, caveat telemetry lịch sử và trạng thái pipeline. Ghi receipt visual riêng, không sửa dữ liệu trong snapshot.
- Khởi chạy collector/parser/cache/index cho target2000 ở hidden background. Lượt collector đầu PID28304 thoát do RemoteDisconnected khi gọi arXiv; parser/cache/index đã tiếp tục xử lý backlog an toàn. Khởi động lại collector PID21588, registry data/corpus/reports/pipeline2000_20261023_193915_resume1_registry.json. Parser PID8000, cache PID12952, index PID7760 còn chạy. Lỗi 404 arxiv:2007.10152 được ghi rejected_download và sẽ thay bằng candidate khác.
- Tại lần kiểm tra 2026-10-23 19:40 +07:00: indexed500, parsed36, downloaded131; tổng sẵn sàng667/2.000; cache đã xử lý536; đĩa trống359.104.860.160 byte. Log collector resumed chưa có stderr. Pipeline còn đang chạy.
- Một số lệnh dò/sửa ban đầu thất bại do output bị cắt, context patch không khớp, hoặc quote/path/PowerShell làm Unicode thành dấu hỏi; không để lại lỗi trong code/docs sau khi sửa. Đoạn docs mới đã được kiểm tra lại dạng Unicode escapes. Không chạy toàn bộ test suite; đã chạy các gate audit/smoke/dedup, py_compile và import.
- Việc còn lại: để cohort đạt đủ 2.000, xác nhận mọi quota/download/parse/cache/index, chạy audit, smoke, dedup và visual sample cuối, rồi chốt manifest/report V1.


## 2026-10-23 19:43:56 +07:00 ? Tiếp tục theo dõi cohort Corpus C 2.000
- Yêu cầu: tiếp tục dựng corpus đến đủ 2.000 PDF, giữ nguyên các gate và snapshot đã đạt.
- Đọc lại trạng thái trong docs/CORPUS_V1.md và plan/DeepResearch_Dataset_Corpus_Plan_V2.1.md. Gate liên quan: quota chính xác, tối thiểu 15% paper dense, dedup, job resume và còn ít nhất 30 GB trống.
- Xác minh PID bằng command line: collector 21588, parser 8000, cache 12952, index 7760 đều còn sống. Collector resumed không ghi stderr. Không restart tiến trình.
- SQLite tại 19:43:33 +07:00: indexed500, parsed50, downloaded158, tổng sẵn sàng708/2.000; quota hiện tại AI/ML333, CV75, IR50, Math/Stats112, NLP75, Systems63. Embedding cache đã xử lý545 paper (500 hit, 45 encode mới); còn358.957.899.776 byte trống. Một candidate mới trả 404 đã được loại để collector thay thế.
- Quét 44 hồ sơ parse mới: mọi sidecar hash, page mapping, chunk count và page span đều hợp lệ; chưa có fallback hoặc lỗi. Quét source xác nhận không còn reader splitlines() trong src/corpus.
- Cập nhật dòng trạng thái triển khai trong plan V2.1 để ghi stage500 đã đạt và liên kết audit, visual receipt, registry stage2000. Lệnh cập nhật đầu không khớp anchor Unicode; đã chạy lại trên anchor ASCII và xác minh nội dung.
- Các file chính liên quan: plan/DeepResearch_Dataset_Corpus_Plan_V2.1.md, docs/CORPUS_V1.md, src/corpus/audit.py, cache_embeddings.py, index.py, dedup.py, process.py, data/corpus/reports/visual_review_pilot500.json và các registry/log pipeline2000.
- Còn lại: để collector/parser/cache/index hoàn tất 2.000; xác minh quota/dense rate/dedup/storage; chạy audit, smoke, dedup và visual sample cuối; xuất manifest/report V1.


## 2026-10-23 19:45:31 +07:00 ? Tiếp tục chạy và kiểm định hồ sơ parse của Corpus C
- Yêu cầu: tiếp tục tới đủ 2.000 PDF; không thu hẹp tiêu chí hoàn tất.
- Đọc lại registry pipeline và kiểm tra tiến trình bằng PID/command line. Collector 21588, parser 8000, cache 12952, index 7760 đều sống; collector resumed stderr rỗng.
- Đối chiếu SQLite, status, topic counts, cache progress và disk. Tại 19:45:23 +07:00: 500 indexed, 57 parsed, 182 downloaded = 739 hồ sơ sẵn sàng / 2.000; quota hiện thời AI/ML364, CV75, IR50, Math/Stats112, NLP75, Systems63; cache553 hồ sơ (500 hit, 53 encode mới); còn358.903.279.616 byte.
- Quét lại sidecar cho các hồ sơ state=parsed: 57 hồ sơ, 1.480 trang, 3.647 chunks; checksum, mapping trang, số chunk, page span đều hợp lệ; không có fallback hoặc lỗi parse, không có U+2028 literal trong batch mới. Search toàn src/corpus xác nhận không còn JSONL reader dùng splitlines().
- Kiểm tra sự kiện 404 candidate arxiv:2007.10152 đã bị loại; trạng thái rejected_download=4, không làm thay đổi snapshot pilot500. Gate resource vẫn đạt.
- Việc còn lại: tiếp tục pipeline nền tới đủ quota 2.000, rồi audit snapshot, smoke, dedup, visual review và tạo manifest/report V1.


## 2026-10-23 19:46:29 +07:00 ? Theo dõi tiếp pipeline Corpus C 2.000
- Yêu cầu: tiếp tục xây corpus đầy đủ 2.000 PDF.
- Xác minh lại registry và command line; collector PID21588, parser PID8000, cache PID12952, index PID7760 đều còn sống.
- Đối chiếu SQLite/status/log lúc 19:45:48 +07:00: 500 indexed, 59 parsed, 187 downloaded, tổng 746/2.000 sẵn sàng; quota AI/ML371/500, các nhóm còn lại chưa tới lượt collector. Cache đã xử lý555 hồ sơ (500 hit, 55 encode mới); còn358.894.514.176 byte trống.
- Tiến độ tăng từ739 lên746 giữa hai lần kiểm tra cách nhau khoảng25 giây; collector resumed không ghi lỗi stderr mới. 404 candidate đã ghi trước đó vẫn là lỗi hồ sơ riêng, không ảnh hưởng snapshot500.
- Không restart worker vì PID đều sống và SQLite tiếp tục tăng. Việc còn lại: tiếp tục đủ quota 2.000 rồi chạy audit, smoke, dedup, visual review cuối và đóng gói manifest/report V1.


## 2026-10-23 19:48:01 +07:00 ? Tiếp tục theo dõi và kiểm tra cohort Corpus C
- Yêu cầu: tiếp tục toàn bộ Corpus C V1 tới 2.000 PDF.
- Xác minh lại tiến trình qua command line và log: collector21588, parser8000, cache12952, index7760 đều còn sống; log stderr collector vẫn rỗng. Không restart.
- Chờ xác minh thêm khoảng20 giây: SQLite tăng từ746 lên765 rồi770 hồ sơ sẵn sàng. Mốc 19:47:26 +07:00 là 500 indexed, 64 parsed, 206 downloaded = 770/2.000; quota AI/ML395/500, CV75, IR50, Math/Stats112, NLP75, Systems63; còn358.787.026.944 byte trống.
- Cache log tiếp tục tăng tới562 hồ sơ; process thực tế dùng CPU và khoảng1,4GB working set, không bị treo. Collector tiếp tục ghi các PDF mới, không có lỗi stderr mới.
- Quét một snapshot 63 hồ sơ parse: 1.618 trang, 4.086 chunks; sidecar checksum, page mapping, chunk count/span đều đạt; không fallback/lỗi.
- Không sửa dữ liệu hay code ở lượt này. Việc còn lại: tiếp tục thu/parse/index đủ quota 2.000 và thực hiện toàn bộ gate cuối trước khi chốt V1.


## 2026-10-23 19:48:55 +07:00 ? Tiếp tục chạy cohort Corpus C và rà sidecar parse
- Yêu cầu: tiếp tục corpus C V1 đầy đủ tới 2.000 PDF.
- Xác minh PID/command line của collector21588, parser8000, cache12952 và index7760: tất cả còn sống; log collector resumed không có stderr.
- SQLite lúc 19:48:45 +07:00: 500 indexed,71 parsed,220 downloaded = 791 hồ sơ sẵn sàng / 2.000. Quota AI/ML416/500, CV75, IR50, Math/Stats112, NLP75, Systems63. Cache569 hồ sơ (500 cache hit,69 encode mới); còn358.734.962.688 byte trống.
- Quét snapshot 69 hồ sơ parsed: 1.754 trang,4.373 chunks; provenance, checksum sidecar, 1-based page mapping, chunk count và page span hợp lệ; không fallback hoặc lỗi.
- Đã chờ xác minh thêm20 giây, số sẵn sàng tăng từ781 lên791. Không restart và không thay đổi code/dữ liệu trong lượt này.
- Còn lại: hoàn tất các quota tới2.000 rồi chạy audit/smoke/dedup/visual review cuối và xuất manifest/report V1.


## 2026-10-23 19:52:49 +07:00 ? Tiếp tục Corpus C, xác minh gate tài nguyên và retry collector
- Yêu cầu: tiếp tục dựng corpus C V1 đến đủ 2.000 PDF.
- Xác minh PID: collector21588, parser8000, cache12952, index7760 đều còn sống.
- Collector gặp HTTP500 (backoff30 giây) rồi HTTP429 (backoff60 giây); sau thời gian chờ đã tiếp tục tải PDF. Log resumed hiện không có stderr mới; không restart worker.
- Quét parsed sidecar snapshot gồm79 hồ sơ: 2.027 trang,4.998 chunks; provenance/hash, page mapping, chunk count/span đều đạt; không fallback.
- Đo resource tại checkpoint gần800 hồ sơ: raw hiện2.230.282.102 byte, parsed396.330.050 byte, index pilot500 280.450.385 byte; projection theo quota cho target2000 raw5.492.008.746, parsed1.336.189.134, index1.121.801.540 byte. Các ngưỡng 25/15/7 GiB đều đạt, đĩa trống trên358 GB. Dense candidate heuristic 291/577 =50,4%; đây chưa phải nhãn chuyên gia hoặc kiểm chứng transcription.
- Trạng thái lúc19:52:37 +07:00: 500 indexed,90 parsed,218 downloaded =808/2.000; quota AI/ML433/500, CV75, IR50, Math112, NLP75, Systems63; cache587 (500 hit,87 encode mới); còn357.585.969.152 byte.
- Chưa sửa code/dữ liệu lượt này. Còn lại: đủ 2.000, kiểm đủ quota và các gate, audit/smoke/dedup/visual review cuối rồi chốt manifest/report V1.


## 2026-10-23 19:53:47 +07:00 ? Tiếp tục cohort Corpus C sau retry nguồn
- Yêu cầu: tiếp tục dựng Corpus C V1 đầy đủ 2.000 PDF.
- Xác minh command line: collector21588, parser8000, cache12952, index7760 còn sống. Collector đã vượt backoff HTTP500/429 và tải tiếp; stderr mới rỗng.
- Kiểm sidecar snapshot 92 hồ sơ parsed: 2.310 trang,5.697 chunks; provenance, checksum mọi file, 1-based page mapping, số chunk và page span đạt; không fallback/lỗi.
- Đã chờ xác minh20 giây; SQLite tăng từ816 lên826 hồ sơ sẵn sàng. Lúc19:53:36 +07:00: 500 indexed,92 parsed,234 downloaded; quota AI/ML451/500, CV75, IR50, Math112, NLP75, Systems63. Embedding cache592 (500 hit,92 encode mới); còn357.551.796.224 byte trống.
- Không restart tiến trình vì mọi worker sống và tiến độ tiếp tục; không sửa code/dữ liệu ở lượt này.
- Còn lại: hoàn thành quota 2.000, rồi chạy audit/smoke/dedup/visual sample cuối và đóng gói manifest/report V1.

## 2026-10-23 19:58:41 +0700 — Xác nhận Catalog B V1 arXiv và checkpoint Corpus C
- Yêu cầu: người dùng chốt dùng arXiv cho Catalog B V1 trước, OpenAlex bổ sung sau; tiếp tục mục tiêu Corpus C V1 2.000 PDF.
- Catalog B đã phát hành: 100,884 record, 100,841 nhóm canonical; audit True, checksum manifest 6/6 khớp. Metadata-only, OAI các set CS/Math/Statistics (không phải toàn bộ arXiv), không có PDF. data/catalog/v1 chiếm 683.63 MiB; toàn data/catalog gồm SQLite làm việc và raw batches chiếm 1037.31 MiB; raw batches 87.
- Corpus C: 607/2.000 đã parse/index (indexed 500, parsed 107), 292 PDF đang chờ parse; còn 324.61 GiB trống. Worker còn sống: 7760, 8000, 12952, 21588.
- Parser PID 8000 vẫn chạy nhưng --wait-for trỏ collector cũ 28304, còn collector hiện tại là 21588. Queue downloaded vẫn dương và log parse có tiến triển; không ngắt giữa tác vụ. Theo dõi và nối lại an toàn nếu parser thoát trước khi collector hiện tại xong.
- Lượt này kiểm tra artifact/checksum/trạng thái và ghi log; không sửa code hoặc dữ liệu. Lệnh ghi log đầu tiên lỗi cú pháp PowerShell, không đổi file; lần ghi sau dùng here-string có thụt lề. Còn lại: hoàn thành quota 2.000 và chạy audit/smoke/dedup/visual review cuối cho Corpus C.

## 2026-10-23 20:02:44 +0700 — Tiếp tục tiến độ Corpus C V1
- Yêu cầu: tiếp tục xây Corpus C đủ 2.000 PDF.
- Workers còn sống: collector True, parser True, cache True, index True. Collector status báo 950 hồ sơ theo quota; topic counts {"ai_ml": 500, "computer_vision": 150, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}. SQLite: 613 đã parse/index (500 pilot indexed + 113 mới parsed), 337 PDF chờ parse, 6 bị loại tải, 27 đã resolve; còn 329.61 GiB trống.
- Đã xác minh bằng log và một lượt chờ có tiến trình thật: collector tiếp tục tăng, parser tăng từ 108 lên 113, cache tăng từ 608 lên 611; index chờ cache theo chuỗi hiện tại. PDF arxiv:2601.06938 mất lâu nhưng child parser dùng CPU, sau đó parse thành công; không dừng worker.
- Kiểm sidecar của snapshot 108 hồ sơ parsed tại thời điểm quét: 2.746 trang, 6.760 chunks, hash/provenance/page mapping/chunk spans đúng; 108/108 dùng pymupdf4llm, không fallback/lỗi. Đây chưa phải kiểm đủ sidecar mới thêm sau lần quét.
- Parser vẫn truyền --wait-for PID 28304 thay vì collector hiện tại 21588; hàng đợi downloaded còn dương lớn và worker parse đang hoạt động, nên chưa restart giữa tác vụ. Theo dõi khi collector xong để bảo đảm parser hoàn tất target.
- Lượt này chỉ kiểm tra trạng thái/sidecar và ghi log; không sửa code/dữ liệu. Còn lại: đủ quota 2.000, rồi audit/smoke/dedup/visual review và chốt manifest Corpus C V1.

## 2026-10-23 20:08:17 +0700 — Collector hồi phục sau HTTP 429, tiếp tục Corpus C
- Yêu cầu: tiếp tục xây Corpus C V1 đủ 2.000 PDF.
- Collector đã qua các backoff 429 (30/60/90 giây) và tải tiếp; status tăng từ 954 lên 974 hồ sơ theo quota, gồm {"ai_ml": 500, "computer_vision": 174, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}. SQLite: 637 parse/index (500 indexed + 137 parsed), 337 đang chờ parse, 6 rejected_download, 23 resolved. Cache đã mã hóa 636/2.000; index worker vẫn chờ cache. Còn 329.53 GiB trống.
- PIDs còn sống: 21588, 8000, 12952, 7760. Parser vẫn mang --wait-for PID 28304 trong khi collector đang chạy ở 21588; queue vẫn dương và parse tiếp tục, chưa restart giữa tiến trình.
- Đã quét 130 parsed sidecar: 3.208 trang, 7.846 chunks, checksum/provenance/page mapping/chunk span khớp; 130 dùng pymupdf4llm, không fallback/lỗi. Sau lượt quét parser đã tiến thêm nên đây là snapshot, không phải tổng số cuối.
- Một lệnh poll chờ trước đó vượt giới hạn trả kết quả nên output không hiện; đã poll trực tiếp lại và xác nhận worker/state/log, không coi timeout quan sát là tiến trình dừng.
- Lượt này không sửa code/dữ liệu; ghi log và để worker tiếp tục. Còn lại: thu đủ 2.000 theo quota, sau đó audit/smoke/dedup/visual review cuối và chốt manifest V1.

## 2026-10-23 20:09:08 +0700 — Collector Corpus C phục hồi; sidecar parse tiếp tục đạt
- Yêu cầu: tiếp tục xây Corpus C V1 đủ 2.000 PDF.
- Sau backoff arXiv HTTP429 30/60/90 giây, collector đã tải tiếp paper CV; active total tăng từ 954 lên 986. SQLite hiện 640 hồ sơ parse/index (500 indexed + 140 parsed), 346 chờ parse; topic counts {"ai_ml": 500, "computer_vision": 186, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}. Cache đạt 640, còn 329.45 GiB trống. Workers sống: 21588, 8000, 12952, 7760.
- Quét sidecar snapshot 140 hồ sơ: 3.409 trang, 8.337 chunks; checksum/provenance/page mapping/chunk span đúng; 140/140 pymupdf4llm, không fallback hay lỗi.
- Parser vẫn dùng --wait-for 28304 trong khi collector là 21588; hàng đợi dương và parser/cache tiến triển nên không restart giữa tiến trình. Index coordinator vẫn đợi cache.
- Một lệnh query đầu gặp ValueError do dùng dict cho các hàng topic ba cột; truy vấn đã chạy lại đúng. Một lệnh poll chờ không đưa output ra vì giới hạn shell; đã kiểm tra lại trực tiếp PID/state/log. Không suy ra worker dừng từ hai lỗi công cụ này.
- Không sửa code/dataset lượt này; log checkpoint và để worker tiếp tục. Còn lại: đủ quota 2.000, sau đó audit/smoke/dedup/visual review cuối và manifest V1.


## 2026-10-23 20:09:17 +07:00 — Giải thích cơ chế chia chunk PDF QA (Asia/Saigon)
- Yêu cầu: giải thích cách app chia nội dung PDF thành chunk.
- Đọc `src/chunker.py`, `src/representations.py`, README và các mục chunking/retrieval trong `docs/MVP_PDF_QA.md`; đối chiếu cấu hình target/max/overlap 340/480/60 từ.
- Kết luận: parse ra Markdown theo trang; chunker tách block theo dòng trống, giữ fenced code và môi trường công thức cùng block nếu vừa ngưỡng; ghép trong phạm vi từng trang, cập nhật heading/section và gán type text/code/math/mixed theo heuristic. Trên target thì flush chunk; overlap 60 từ chỉ cho văn xuôi. Code quá lớn chia giữa các dòng, block không-code quá lớn chia theo target words; chunk lưu page/section/type/warnings và representation để retrieval/citation.
- Không sửa code/tài liệu sản phẩm, không chạy tests. Giới hạn cần nêu: đếm từ bằng whitespace, không phải token; nhận diện type dựa regex; block lớn có thể bị chia và parser vẫn có thể làm mất cấu trúc.

## 2026-10-23 20:10:01 +0700 — Checkpoint Corpus C và xác minh uniqueness trước khi tiếp tục
- Yêu cầu: tiếp tục xây Corpus C V1 đủ 2.000 PDF.
- Collector đã tự hồi phục sau HTTP429/backoff và tiếp tục tải CV. SQLite hiện 997/2.000 ở các state downloaded/parsed/indexed: 640 đã parse/index (indexed 500, parsed 140), 357 đang chờ parse. Cache 640. Topic counts {"ai_ml": 500, "computer_vision": 197, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}. 4 worker live: 21588, 8000, 12952, 7760. Ổ còn 325.84 GiB.
- Gate uniqueness tạm thời trên 997 record: canonical groups 997 và PDF hashes 997 duy nhất; duplicate groups 0, duplicate hashes 0, null ID/hash 0. Quét sidecar snapshot 140 hồ sơ trước đó đạt 3.409 trang/8.337 chunks, hash/provenance/page mapping/chunk spans đúng, không fallback/lỗi.
- Parser vẫn tham chiếu --wait-for 28304 thay vì collector 21588; backlog còn dương, collector/parser/cache tiến triển, chưa restart. Index chờ cache.
- Lần query topic đầu trong lượt này lỗi ValueError do ép hàng ba cột thành dict; truy vấn lại đúng. Poll có sleep trước đó không hiện output do giới hạn shell; đã poll trực tiếp lại và xác nhận PID/trạng thái/log. Không coi lỗi công cụ là worker dừng.
- Không sửa code hoặc dataset lượt này; ghi log và tiếp tục pipeline. Còn quota 2.000 rồi audit/smoke/dedup/visual review cuối và manifest V1.

## 2026-10-23 20:11:04 +0700 — Tiếp tục Corpus C; parse, sidecar và uniqueness đạt
- Yêu cầu: tiếp tục xây Corpus C V1 đủ 2.000 PDF.
- Collector còn chạy và tiếp tục tải; SQLite hiện 1015 active record: 643 parse/index (indexed 500, parsed 143), 372 đang chờ parse. Cache 640. Topic counts {"ai_ml": 500, "computer_vision": 215, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}; ổ còn 325.78 GiB. Worker IDs còn sống: 21588, 8000, 12952, 7760.
- Quét sidecar snapshot 142 hồ sơ: 3459 trang, 8471 chunks; hash/provenance/page mapping/chunk span đúng, 142 backend pymupdf4llm, không fallback hay lỗi. Parser hoàn thành PDF đang chậm rồi chuyển sang paper tiếp theo.
- Gate uniqueness tạm trên 1015 hồ sơ: 1015 canonical group và 1015 PDF hash duy nhất; không duplicate group/hash hoặc null ID/hash.
- Parser vẫn tham chiếu --wait-for 28304 trong khi collector 21588; hàng đợi lớn và parser/cache tiến triển nên chưa restart. Index tiếp tục chờ cache.
- Lần truy vấn topic đầu vấp ValueError do ép dữ liệu ba cột thành dict; đã chạy truy vấn lại đúng. Một lệnh poll chờ không đưa output ra vì shell timeout; đã poll trực tiếp PID/state/log. Không có thay đổi dữ liệu do các lần lỗi công cụ.
- Không sửa code/dataset lượt này; ghi log và giữ worker chạy. Còn lại: đủ quota 2.000, audit/smoke/dedup/visual review cuối và manifest V1.

## 2026-10-23 20:12:31 +0700 — Tiến triển Corpus C, sidecar và uniqueness
- Yêu cầu: tiếp tục Corpus C V1 tới 2.000 PDF.
- Collector/parser/cache/index được xác minh bằng PID; collector tiếp tục tải sau backoff, các worker còn sống: 21588, 8000, 12952, 7760. SQLite hiện 1036 active hồ sơ: 647 parse/index (indexed 500, parsed 147), 389 downloaded chờ parse; cache 643; topic counts {"ai_ml": 500, "computer_vision": 236, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}; còn 325.64 GiB.
- Sidecar snapshot 146 hồ sơ đạt: 3548 trang, 8708 chunks; mọi hash/provenance/page mapping/chunk spans đều đúng, backend 146 pymupdf4llm, không fallback hay lỗi.
- Uniqueness trên 1036 active hồ sơ: 1036 canonical group, 1036 PDF hashes; duplicate group/hash 0/0, null ID/hash 0.
- Parser đang chạy với --wait-for PID 28304 trong khi collector hiện tại 21588; hàng đợi dương và parser tiến triển nên giữ nguyên. Index worker chờ cache.
- Trong lượt này, một truy vấn topic lỗi ValueError do đổi hàng ba cột sang dict; một lượt audit sidecar tính xong nhưng in JSON lỗi vì sqlite Row chưa chuyển tuple; cả hai đã chạy lại thành công. Poll chờ không hiện output do giới hạn shell, nên trạng thái được poll lại trực tiếp. Không có lỗi hoặc chỉnh sửa dữ liệu.
- Chỉ kiểm tra dữ liệu/worker và ghi log; tiếp tục để pipeline chạy. Còn quota 2.000 và gate audit/smoke/dedup/visual review cuối cùng.

## 2026-10-23 20:13:39 +0700 — Collector tiếp tục tăng sau poll; kiểm tra batch Corpus C
- Yêu cầu: tiếp tục Corpus C V1 tới 2.000 PDF.
- Đã chờ trực tiếp collector PID21588 trong 15 giây; PID vẫn sống và active count tăng từ 1.039 lên 1.046. Sau kiểm tra sidecar, SQLite lên 1052 active record: 648 parse/index (indexed 500, parsed 148), 404 downloaded chờ parse; cache 646. Topic counts {"ai_ml": 500, "computer_vision": 252, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}. Worker sống: 21588, 8000, 12952, 7760; ổ còn 325.50 GiB.
- Sidecar snapshot 148 hồ sơ đạt: 3.568 trang, 8.761 chunks; checksum/provenance/page mapping/chunk spans khớp, 148 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1052 active hồ sơ: 1052 canonical group và 1052 PDF hash; duplicate group/hash 0/0, null ID/hash 0.
- Collector đang tải CV sau backoff; parser vẫn --wait-for PID28304 trong khi collector hiện tại PID21588. Hàng đợi còn dương, parser/cache tiến triển; không restart giữa tác vụ. Index worker đợi cache.
- Lượt này không sửa code/dataset; log checkpoint, giữ workers chạy. Còn quota 2.000 và audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:14:57 +0700 — Corpus C tiếp tục tải và parse; kiểm sidecar/uniqueness
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Workers được xác minh còn sống: 21588, 8000, 12952, 7760. SQLite hiện 1072 active: 656 parse/index (indexed 500, parsed 156), 416 downloaded chờ parse; cache 654, topic counts {"ai_ml": 500, "computer_vision": 272, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}; còn 328.62 GiB trống. Collector tiếp tục tải CV, không còn dừng ở backoff.
- Quét đủ snapshot 154 parsed sidecar: 3747 trang, 9115 chunks; hash/provenance/page mapping/chunk span khớp; 154 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1072 active hồ sơ: 1072 canonical group, 1072 PDF hash; duplicate group/hash 0/0, null ID/hash 0.
- Parser vẫn --wait-for PID28304 trong khi collector hiện tại là PID21588; queue downloaded còn lớn, parser/cache tiếp tục tiến nên chưa restart. Index chờ cache.
- Lệnh poll chờ tuần tự ba process vượt giới hạn hiển thị; sau đó đã xác minh lại PID/DB/log trực tiếp, thấy worker còn sống và tiến độ tăng. Không coi lần poll thiếu output là dừng.
- Lượt này chỉ kiểm tra, không sửa code/dataset; ghi log và giữ pipeline chạy. Còn quota 2.000 và audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:15:54 +0700 — Poll collector và kiểm batch Corpus C mới
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Chờ trực tiếp collector PID21588 trong 15 giây: PID còn sống, status tăng 1.074 → 1.081; khi hoàn tất kiểm tra, active count đạt 1087. SQLite: 658 parse/index (indexed 500, parsed 158), 429 đang chờ parse; cache 657; topic counts {"ai_ml": 500, "computer_vision": 287, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}. Worker sống: 21588, 8000, 12952, 7760. Còn 328.85 GiB trống.
- Quét snapshot 157 sidecar: 3833 trang, 9251 chunks; file hashes/provenance/page mapping/chunk spans đạt; 157 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1087 active hồ sơ: 1087 canonical group / 1087 PDF hash duy nhất; duplicate group/hash 0/0; null ID/hash 0.
- Parser vẫn --wait-for PID28304 trong khi collector PID21588; queue lớn và worker parse/cache tiến triển, nên không restart giữa tác vụ. Index chờ cache.
- Lượt này kiểm tra trạng thái/sidecar/uniqueness, không sửa code/dataset; đã append log. Còn quota 2.000, audit/smoke/dedup/visual review cuối và manifest.

## 2026-10-23 20:16:55 +0700 — Collector tiếp tục tăng; kiểm tra 159 sidecar Corpus C
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Đã poll trực tiếp collector PID21588 trong 15 giây: PID vẫn sống, active tăng 1.074 → 1.093; lúc kiểm tra cuối đạt 1098. SQLite: 661 parse/index (indexed 500, parsed 161), 437 downloaded chờ parse; cache 658, topics {"ai_ml": 500, "computer_vision": 298, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 75, "systems_algorithms": 63}; còn 328.77 GiB. Workers live 21588, 8000, 12952, 7760.
- Quét snapshot 159 sidecar: 3980 trang, 9633 chunks; hash/provenance/page mapping/chunk spans đúng; 159 pymupdf4llm, không fallback hay lỗi.
- Uniqueness trên 1098 active: 1098 canonical group và 1098 PDF hash duy nhất; duplicate group/hash 0/0, null ID/hash 0.
- Parser --wait-for vẫn trỏ PID28304, collector hiện PID21588; downloaded queue còn lớn và parse/cache tiến triển, không restart giữa tác vụ. Index đang đợi cache.
- Không sửa code/dataset lượt này; append log và giữ pipeline chạy. Còn quota 2.000 và gate audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:18:42 +0700 — Theo dõi collector sau poll và kiểm batch mới
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Cấu hình quota source cộng đúng 2.000: AI/ML 500, CV 300, NLP 300, IR 200, Math/Stats 450, Systems 250. Collector đã đủ AI/ML và CV, hiện tải NLP.
- SQLite hiện 1129 active record: 671 parse/index (indexed 500, parsed 171), 458 chờ parse; cache 668; topic counts {"ai_ml": 500, "computer_vision": 300, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 104, "systems_algorithms": 63}. Workers hiện sống 21588, 20860, 8000, 23612, 12952, 33256, 7760, 15848; còn 328.71 GiB trống.
- Sidecar snapshot 169 hồ sơ đạt: 4221 trang, 10173 chunks; hash/provenance/page mapping/chunk spans khớp; 169 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1129 active: 1129 canonical group và 1129 PDF hash; không duplicate hoặc null ID/hash.
- Một psutil wait trả kết quả như thể PID21588 đã thoát; kiểm tra trực tiếp kế tiếp thấy PID21588, child20860, log và SQLite đều đang tiến triển. Không restart theo một quan sát mâu thuẫn; giữ pipeline đang chạy. Parser --wait-for vẫn PID28304, backlog lớn, parser/cache tiến triển.
- Lượt này đọc cấu hình, poll worker, kiểm sidecar/uniqueness; không sửa code/dataset. Đã ghi log; còn quota 2.000 và gate audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:19:51 +0700 — Collector tiếp tục NLP; xác nhận process và sidecar
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Sau khi collector nạp đủ AI/ML=500 và CV=300, đang tăng NLP. SQLite hiện 1149 active record: 676 parse/index (indexed 500, parsed 176), 473 downloaded chờ parse; cache 672; topics {"ai_ml": 500, "computer_vision": 300, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 124, "systems_algorithms": 63}. Worker IDs live 21588, 20860, 8000, 23612, 12952, 33256, 7760, 15848; ổ còn 328.68 GiB.
- Sidecar snapshot 173 hồ sơ đạt: 4399 trang, 10580 chunks; checksum/provenance/page mapping/chunk spans đúng; 173 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1149 active: 1149 canonical group và 1149 PDF hash duy nhất; duplicate/null 0/0.
- Một lần psutil wait trả kết quả exit trái với trạng thái; recheck WMI/psutil xác nhận PID21588 cùng creation time ban đầu, child20860 còn sống, log và DB tiếp tục tăng. Không restart. Parser vẫn chờ PID28304 cũ; downloaded queue lớn và parser/cache tiến triển.
- Lượt này chỉ kiểm tra/quét/ghi log; không sửa code/dataset. Còn quota 2.000 và audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:21:03 +0700 — Collector NLP tiến triển; process/sidecar xác minh
- Yêu cầu: tiếp tục Corpus C V1 tới 2.000 PDF.
- Poll process collector PID21588 bằng create_time trước/sau 15 giây: cùng tiến trình, còn sống; active status tăng 1.153 → 1.163, SQLite đạt 1171 sau khi quét. Topic counts {"ai_ml": 500, "computer_vision": 300, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 146, "systems_algorithms": 63}. SQLite: 680 parse/index (indexed 500, parsed 180), 491 downloaded chờ parse; cache 680; còn 328.66 GiB. Worker live 21588, 20860, 8000, 23612, 12952, 33256, 7760, 15848.
- Sidecar snapshot 180 hồ sơ đạt: 4547 trang, 10888 chunks; checksum/provenance/page mapping/chunk spans đúng; 180 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1171 active: 1171 canonical group và 1171 PDF hash; duplicate group/hash 0/0, null ID/hash 0.
- Quota source tổng 2.000; collector đã đủ AI/ML 500 và CV 300, hiện nạp NLP. Parser --wait-for vẫn PID28304 thay vì collector21588; downloaded queue lớn và parser/cache tiến triển nên không restart.
- Lượt này chỉ kiểm tra worker/DB/sidecar/uniqueness, không sửa code/dataset; append log. Còn quota và audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:22:01 +0700 — Poll collector xác nhận tiến triển; sidecar và uniqueness đạt
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Collector PID21588 cùng creation time, còn sống trước/sau poll 15 giây; active tăng 1.153 → 1.181, SQLite lên 1188 sau quét. Topic counts {"ai_ml": 500, "computer_vision": 300, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 163, "systems_algorithms": 63}. SQLite: 685 parse/index (indexed 500, parsed 185), 503 đang chờ parse; cache 683; còn 328.63 GiB. Workers live 21588, 20860, 8000, 23612, 12952, 33256, 7760, 15848.
- Quét sidecar snapshot 184 hồ sơ: 4641 trang, 11139 chunks; checksum/provenance/page mapping/chunk spans đúng; 184 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1188 active: 1188 canonical group/PDF hash; duplicate group/hash 0/0; null ID/hash 0.
- Collector đã xong AI/ML 500 và CV300, đang nạp NLP. Parser --wait-for vẫn PID28304 cũ; downloaded queue lớn, parser/cache đang tiến nên không restart. Index chờ cache.
- Lượt này chỉ poll worker và kiểm tra dữ liệu; không sửa code/dataset, log đã append. Còn quota 2.000 và audit/smoke/dedup/visual review cuối.

## 2026-10-23 20:22:38 +0700 — Tiếp tục Corpus C; kiểm sidecar và lỗi tải candidate
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF.
- Worker live 21588, 20860, 8000, 23612, 12952, 33256, 7760, 15848. SQLite hiện 1199 active: 688 parse/index (indexed 500, parsed 188), 511 downloaded chờ parse; cache 686; topic counts {"ai_ml": 500, "computer_vision": 300, "information_retrieval": 50, "math_stats": 112, "nlp_llm": 174, "systems_algorithms": 63}; còn 328.61 GiB trống. Collector vẫn tải NLP.
- Sidecar snapshot 185 hồ sơ đạt: 4667 trang, 11186 chunks; hash/provenance/page mapping/chunk spans khớp; 185 pymupdf4llm, không fallback/lỗi.
- Uniqueness trên 1199 active: 1199 canonical group và 1199 PDF hash, duplicate group/hash 0/0, null ID/hash 0. Một PDF candidate bị loại do encrypted/page-count unsupported; đó là lỗi candidate, collector tiếp tục quota bằng paper khác.
- Parser --wait-for còn trỏ PID28304, trong khi collector PID21588; downloaded backlog lớn, parser/cache tiếp tục tiến, không restart.
- Lượt này chỉ kiểm tra DB/log/sidecar và ghi log; không sửa code/dataset. Còn quota 2.000 và audit/smoke/dedup/visual review cuối.


## 2026-10-23 20:26:47 +0700 — Tiếp tục Corpus C V1; các worker vẫn chạy
- Yêu cầu: tiếp tục xây Corpus C đến 2.000 PDF. Lần truy vấn đầu dùng nhầm đường dẫn SQLite staging cũ nên báo không mở được DB; một lệnh inline SQL khác bị PowerShell diễn giải sai dấu ngoặc. Đã dò cấu trúc dự án và đọc được DB đúng tại data/corpus/corpus.sqlite. Sidecar nằm lồng trong thư mục hash/parser, nên đã đổi sang quét đệ quy.
- Collector PID 21588 và subprocess 20860, parser 8000/23612, cache 12952/33256, index 7760/15848 đều còn sống. PID collector và creation time giữ nguyên qua poll 15 giây; active records tăng 1.220 → 1.228 trong poll đó và tiếp tục lên 1.271 ở lần kiểm tra sau. DB mới nhất: 566 downloaded, 205 parsed, 500 indexed.
- Số active theo topic: ai_ml 500, computer_vision 300, nlp_llm 246, information_retrieval 50, math_stats 112, systems_algorithms 63; tổng 1.271/2.000, còn thiếu 729 theo quota. Collector và parser log tiếp tục có paper mới.
- Cache tiến tới 702/2.000 (500 cache hits, 202 encode mới); dung lượng trống khoảng 328,5 GiB.
- Kiểm sidecar ở snapshot parsed=201: đủ 201/201 sidecar; backend đều pymupdf4llm; 5.108 trang, 12.244 chunks; không fallback hay lỗi; hash file, PDF hash, page/chunk counts và chunk spans đều khớp. Snapshot uniqueness active=1.269: canonical_group_id và PDF SHA đều đủ, duy nhất, không trùng.
- Lượt này chỉ đọc DB/log/process và kiểm tra chất lượng; không sửa code hay dữ liệu. Còn quota 2.000, pipeline cache/index hoàn chỉnh và các gate audit/smoke/dedup/visual review cuối. Parser coordinator từng được xác nhận vẫn chờ PID collector cũ 28304; hiện worker vẫn tiến nhờ backlog, cần xử lý dependency này nếu nó ngăn pipeline kết thúc.


## 2026-10-23 20:31:59 +0700 — Tiếp tục Corpus C; NLP đủ quota, collector sang IR
- Yêu cầu: tiếp tục Corpus C V1 đến đủ 2.000 PDF. Lệnh kiểm tra đầu lượt dùng nhầm workdir (lặp tên thư mục project), đã chạy lại ở đúng thư mục. Một lần đọc parse.lock bị Windows từ chối do lock đang mở; lần đo CPU của tiến trình parse con gặp NoSuchProcess vì tiến trình vừa kết thúc. Đã xác nhận paper arxiv:2601.07760 chuyển sang state parsed và parser nhận paper kế tiếp; không restart worker.
- Poll 35 giây xác nhận collector PID21588 cùng creation time còn sống; active tăng 1.322 → 1.347. NLP đạt 300/300, collector chuyển sang IR; IR tăng 62 → 72 trong poll. Trạng thái mới nhất lúc 20:31:59: 1.361/2.000 active (644 downloaded, 217 parsed, 500 indexed), còn 639; quotas {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:86, math_stats:112, systems_algorithms:63}. Collector/parser/cache/index coordinators PID21588/8000/12952/7760 còn sống. Cache 714/2.000; disk trống 328,23 GiB.
- Đọc lại quota và điều kiện corpus trong plan; đã xác nhận mục tiêu 2.000, sáu quota và yêu cầu ít nhất 15% paper dense theo heuristic. Snapshot 713 quality sidecar của paper indexed/parsed có 383 dense candidates (53,7%), 1 fallback và 6 paper có trang text thấp; đây là heuristic/flag chất lượng, không phải nhãn visual gold.
- Parser coordinator được khởi động với --wait-for PID28304; PID đó hiện đã kết thúc, backlog vẫn được parse. Index coordinator đang chờ cache coordinator hoàn tất như thiết kế. Lần đọc report/rg rộng bị cắt output; đã chuyển sang excerpt plan và trạng thái DB có giới hạn.
- Lượt này đọc DB, process, logs, source code và plan; không sửa code hoặc corpus. Còn quota 639 và các gate cuối audit/smoke/dedup/visual review/manifest V1.


## 2026-10-23 20:33:31 +07:00 — Chỉ đường tải ba benchmark bên ngoài (Asia/Saigon)
- Yêu cầu: cho biết nơi tải ba dataset benchmark được nhắc tới và vị trí local trong project.
- Đối chiếu `docs/BENCHMARK_DATASET_SUMMARY.md`, README benchmark; mở trang nguồn chính thức Hugging Face/GitHub cho QASPER, LAB-Bench/LitQA2 và SciCode; kiểm tra các file local liên quan.
- Xác định ba nguồn bên ngoài là QASPER (`allenai/qasper`), subset LitQA2 của LAB-Bench (`futurehouse/lab-bench`) và SciCode (`SciCode1/SciCode`; harness tại GitHub `scicode-bench/SciCode`). Bản local QASPER ở `data/benchmark/external/qasper/`; LitQA2 Parquet ở `data/benchmark/external/litqa2/raw/LitQA2/`; SciCode problems/harness ở `data/benchmark/external/scicode/`, gồm `test_data.h5` 1,049,345,865 byte. PDF QA curated_v1 là dataset tự xây local, không phải nguồn upstream tải riêng.
- Links xác thực được trên nguồn chính thức; các file mục tiêu có mặt local. Chỉ đọc/tìm nguồn và liệt kê file, không tải lại hoặc chạy tests. Không còn việc cần làm.


## 2026-10-23 20:34:46 +07:00 — Kiểm tra Kaggle cho QASPER, LitQA2 và SciCode (Asia/Saigon)
- Yêu cầu: xác minh ba benchmark ngoài có thể tải từ Kaggle không.
- Tìm trên Kaggle theo QASPER, LitQA2, SciCode và đọc trang Kaggle Open Benchmarks/SciCode cùng tài liệu tải benchmark. Không thấy trang Kaggle dataset rõ ràng cho QASPER hoặc LitQA2; Kaggle có trang leaderboard/benchmark SciCode, và hướng dẫn Kaggle mô tả nút Download benchmark để tải dữ liệu leaderboard. Đối chiếu nguồn chính thức Hugging Face/GitHub đã nêu trong tài liệu dự án.
- Kết luận: không xác nhận được Kaggle là nguồn tải raw benchmark cho QASPER/LitQA2; trang SciCode trên Kaggle là benchmark/leaderboard, không thay thế gói dữ liệu SciCode chính thức. Không tải dữ liệu hoặc sửa project ngoài log; không chạy tests.


## 2026-10-23 20:35:33 +07:00 — Giải thích ý nghĩa ba benchmark ngoài (Asia/Saigon)
- Yêu cầu: giải thích QASPER, LitQA2 và SciCode dùng để đánh giá năng lực nào.
- Đối chiếu tài liệu benchmark đã đọc và nguồn chính thức: QASPER đo QA/evidence retrieval trên paper NLP; LitQA2 đo literature/science QA và tra cứu nguồn (thiên biology); SciCode đo suy luận khoa học và sinh code cho bài toán nghiên cứu. Nêu rõ SciCode khác hai bộ QA literature, không cộng điểm chung.
- Không sửa tài liệu sản phẩm hoặc chạy benchmark/tests; không còn việc khác.


## 2026-10-23 20:38:02 +0700 — Khôi phục collector sau lỗi mạng và tiếp tục Corpus C
- Yêu cầu: tiếp tục Corpus C V1 đến 2.000 PDF. Collector cũ PID21588 kết thúc với ConnectionError/RemoteDisconnected; log xác nhận lỗi phát sinh trong Network.get và status.json ghi stopped_with_error. Parser/cache/index vẫn sống và DB giữ checkpoint 1.383 active.
- Sửa src/corpus/collect.py: Network.get retry ConnectionError/Timeout tối đa 5 lần, backoff 30 giây tăng theo lần thử; thêm test transient disconnect vào tests/test_corpus.py. Toàn bộ 8 test test_corpus.py đạt, py_compile và git diff --check sạch.
- Resume từ checkpoint với --target 2000, log/registry mới pipeline2000_20261023_203546_resume2; collector PID31456 + child 7408 còn sống. Paper arxiv:2003.08052 gây lỗi trước đó đã tải thành công; err.log mới trống. Poll xác nhận worker thoát được khoảng chờ mạng và tiếp tục thêm paper.
- Trạng thái mới nhất: 1.404/2.000 active (663 downloaded, 241 parsed, 500 indexed), còn 596. Quotas {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:129, math_stats:112, systems_algorithms:63}. Cache 740/2.000; parser/cache/index coordinator 8000/12952/7760 và subprocesses còn sống; disk trống 328,13 GiB.
- Lượt này sửa code/test, chạy kiểm tra, resume collector và poll tiến độ. Lần gửi lệnh append log đầu bị lỗi cú pháp JS do backtick trong nội dung, chưa chạy lệnh shell; đã sửa và append ở lần kế tiếp. Còn quota, parse/cache/index đủ 2.000 và audit/smoke/dedup/visual review/manifest V1 cuối.


## 2026-10-23 20:38:40 +07:00 — Giải thích sâu hơn vai trò ba benchmark (Asia/Saigon)
- Yêu cầu: giải thích QASPER, LitQA2, SciCode khác nhau thế nào và có ý nghĩa gì cho đánh giá.
- Dựa trên docs/BENCHMARK_DATASET_SUMMARY.md cùng các nguồn chính thức đã tra: QASPER đo paper QA/evidence retrieval paragraph-level; LitQA2 đo literature/science QA và truy xuất nguồn; SciCode đo suy luận khoa học, sinh code và kiểm tra kết quả chạy. Nêu rõ chúng không phải ba bộ cùng loại, không gộp metric; phân biệt dữ liệu benchmark với corpus nguồn để RAG index, và nhắc runner LitQA2/SciCode chưa tích hợp/chạy trong project.
- Chỉ giải thích, không chạy benchmark/tests hoặc sửa nội dung sản phẩm. Không còn việc khác.


## 2026-10-23 20:41:46 +0700 — Tiếp tục poll Corpus C sau resume2
- Yêu cầu: tiếp tục xây Corpus C V1. Tại đầu lượt, SQLite đã tăng lên 1.419 active; collector PID31456/7408, parser 8000/23612, cache 12952/33256 và index 7760/15848 còn sống; log mới của collector tiếp tục nhận paper.
- Poll cùng collector PID31456 trong 30 giây xác nhận cùng creation time và tiến triển 1.443 → 1.452; poll tiếp theo tăng 1.460 → 1.467. Trạng thái cuối: 716 downloaded, 251 parsed, 500 indexed; quota theo topic {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:192, math_stats:112, systems_algorithms:63}, còn 533/2.000. Collector đang gần đủ IR quota 200.
- Cache tiến từ 745 lên 748/2.000; kiểm tra process cho thấy cache worker CPU hoạt động và cache JSONL thêm bản ghi. Parser đã hoàn tất paper dài arxiv:1509.07982 (52 trang/117 chunks) rồi tiếp tục queue. Index vẫn chờ cache coordinator theo thiết kế. Log resume2 err rỗng.
- Một poll nhắm child parser PID29260 thất bại vì child kết thúc trước khi được lấy; truy vấn ngay sau đó xác nhận parse log cập nhật và child mới đã được sinh, không cần restart.
- Lượt này kiểm tra DB/process/log và để pipeline tiếp tục; không sửa code/dữ liệu. Còn quota 533, hoàn tất parse/cache/index và audit/smoke/dedup/visual review/manifest V1.


## 2026-10-23 20:43:43 +0700 — Tiếp tục Corpus C; IR đủ quota, Math/Stats đang thu thập
- Yêu cầu: tiếp tục Corpus C V1 đến đủ 2.000 PDF. Đầu lượt DB ở 1.475 active; collector PID31456/7408 và parser/cache/index worker vẫn chạy. Poll cùng collector xác nhận tiến triển và chuyển topic khi quota IR đủ.
- Snapshot cuối: 1.498/2.000 active (742 downloaded, 256 parsed, 500 indexed), còn 502. Quotas {ai_ml:500/500, computer_vision:300/300, nlp_llm:300/300, information_retrieval:200/200, math_stats:135/450, systems_algorithms:63/250}. Collector resume2 PID31456 cùng creation time còn sống; stdout mới có Math/Stats, err.log vẫn 0 byte. Parser/cache/index đã xác nhận sống ở poll gần nhất; cache tăng 749 → 752.
- Parse dài arxiv:1509.07982 đã hoàn tất, sau đó parser tiếp tục xử lý. Một lần truy vấn child PID29260 gặp NoSuchProcess vì child kết thúc giữa các poll; đọc lại DB/log xác nhận parser hoàn tất paper và đã sinh child kế tiếp.
- Lượt này chỉ kiểm tra SQLite/process/log và poll tiến độ, không sửa code/dữ liệu hoặc chạy test. Còn quota 502, hoàn tất parse/cache/index và audit/smoke/dedup/visual review/manifest V1.


## 2026-10-23 20:44:45 +0700 — Tiếp tục Corpus C; Math/Stats đã lên 152
- Yêu cầu: tiếp tục corpus V1 đủ 2.000 PDF. Trạng thái đầu lượt 1.504 active; collector resume2 PID31456/7408 và parser/cache/index coordinators còn chạy.
- Poll cùng PID collector trong 30 giây xác nhận còn sống, active tăng lên 1.515. Trạng thái cuối: 757 downloaded, 258 parsed, 500 indexed; topic quota {ai_ml:500/500, computer_vision:300/300, nlp_llm:300/300, information_retrieval:200/200, math_stats:152/450, systems_algorithms:63/250}; còn 485. Cache 754/2.000. Collector log mới tiếp tục có Math/Stats, err.log 0 byte; parser/cache/index vẫn sống.
- Lượt này đọc DB/process/status/log và poll tiến độ; không sửa code/dữ liệu hay chạy test. Còn quota 485, các stage parse/cache/index và audit/smoke/dedup/visual review/manifest V1 cuối.


## 2026-10-23 20:46:04 +0700 — Tiếp tục Corpus C; Math/Stats lên 172
- Yêu cầu: tiếp tục xây Corpus C V1. Đầu lượt có 1.504 active; collector PID31456 và các stage downstream còn sống.
- Poll cùng collector trong 30 giây xác nhận tiến triển; tổng tiếp tục tăng. Trạng thái mới nhất: 1.535/2.000 active (773 downloaded, 262 parsed, 500 indexed), còn 465. Topic counts {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:200, math_stats:172, systems_algorithms:63}. Collector 31456/7408, parser 8000/23612, cache 12952/33256 và index 7760/15848 đều đang chạy.
- Cache đạt 756/2.000; CPU cache worker hoạt động mạnh trong poll. Collector tiếp tục tải Math/Stats; resume2 err.log không có lỗi mới.
- Lượt này chỉ đọc DB/process/log và poll tiến độ; không sửa code/dữ liệu hay chạy test. Còn quota 465, parse/cache/index và các gate audit/smoke/dedup/visual review/manifest cuối.

- Hiệu chỉnh 2026-10-23 20:46:21 +0700: dòng đầu mục này ghi nhầm checkpoint đầu lượt là 1.504; truy vấn đầu lượt thực tế lúc 20:45:10 cho 1.521. Mốc cuối 1.535 và phân bố topic cuối trong cùng mục vẫn đúng.


## 2026-10-23 20:47:12 +0700 — Tiếp tục Corpus C; Math/Stats lên 188
- Yêu cầu: tiếp tục Corpus C V1 đủ 2.000 PDF. Đầu lượt SQLite ở 1.543 active; mọi worker collector/parser/cache/index còn sống.
- Poll cùng collector PID31456 trong 30 giây xác nhận process giữ nguyên creation time và active tăng lên 1.551: 786 downloaded, 265 parsed, 500 indexed. Quota hiện {ai_ml:500/500, computer_vision:300/300, nlp_llm:300/300, information_retrieval:200/200, math_stats:188/450, systems_algorithms:63/250}; còn 449. Cache 758/2.000. Collector log đang có paper Math/Stats mới; err.log 0 byte. Parser/cache/index coordinators 8000/12952/7760 còn sống.
- Lượt này chỉ đọc trạng thái/log/process và poll; không sửa code/dataset hoặc chạy test. Còn quota 449, hoàn tất stage parse/cache/index và gate audit/smoke/dedup/visual review/manifest V1.


## 2026-10-23 20:48:17 +0700 — Tiếp tục Corpus C; Math/Stats lên 206
- Yêu cầu: tiếp tục Corpus C V1 đến đủ 2.000 PDF. Đầu lượt DB có 1.558 active, collector PID31456/7408 và các worker downstream đều đang chạy.
- Poll cùng collector 30 giây xác nhận process sống cùng creation time và tiến độ tăng. Trạng thái cuối: 803 downloaded, 266 parsed, 500 indexed = 1.569/2.000 active, còn 431. Quota {ai_ml:500/500, computer_vision:300/300, nlp_llm:300/300, information_retrieval:200/200, math_stats:206/450, systems_algorithms:63/250}. Cache 761/2.000.
- Collector stdout tiếp tục tải Math/Stats; err.log 0 byte. Parser/cache/index coordinators 8000/12952/7760 còn sống.
- Lượt này đọc trạng thái DB/process/log và poll; không sửa code/dữ liệu hoặc chạy test. Còn quota 431, hoàn tất stage parse/cache/index và audit/smoke/dedup/visual review/manifest V1.


## 2026-10-23 20:57:02 +0700 — Tiếp tục Corpus C; cache bắt kịp hồ sơ parse nặng
- Yêu cầu: tiếp tục Corpus C V1 đến 2.000 PDF. Đầu lượt SQLite ở 1.574 active, mọi collector/parser/cache/index process còn sống.
- Collector cùng PID31456 được poll và tiếp tục tăng quota Math/Stats. Trạng thái mới nhất: 919 downloaded, 284 parsed, 500 indexed = 1.703/2.000, còn 297. Topic counts {ai_ml:500/500, computer_vision:300/300, nlp_llm:300/300, information_retrieval:200/200, math_stats:340/450, systems_algorithms:63/250}. Cache 769/2.000.
- Parser xử lý thành công arxiv:2105.02180, 99 trang/403 chunks, bằng pymupdf4llm. Cache progress đứng ở 766 trong lúc worker CPU hoạt động; xác định record dài, sau đó log ghi CACHED và tiến lên 767 rồi 769. Không cần restart. Collector resume2 err.log vẫn 0 byte. PID collector 31456/7408, parser 8000/23612, cache 12952/33256, index 7760/15848 còn sống.
- Lượt này chỉ đọc DB/process/log và poll tiến độ; không sửa code/dataset hoặc chạy test. Còn quota 297, hoàn tất cache/index và gate audit/smoke/dedup/visual review/manifest V1.


## 2026-10-23 21:00:02 +0700 — Tiếp tục Corpus C; parser tiếp tục sau paper chậm
- Yêu cầu: tiếp tục Corpus C V1. Lúc đầu lượt DB ở 1.714 active; collector resume2, parser, cache và index workers đều sống.
- Poll collector xác nhận cùng PID31456 và tiến độ. Snapshot mới nhất: 960 downloaded, 287 parsed, 500 indexed = 1.747/2.000, còn 253. Quotas {ai_ml:500/500, computer_vision:300/300, nlp_llm:300/300, information_retrieval:200/200, math_stats:384/450, systems_algorithms:63/250}. Cache 775/2.000.
- Parser từng chưa cập nhật trong khoảng poll, nhưng truy vấn process cho thấy child mới được sinh; log sau đó xác nhận arxiv:2601.09018 (24 trang/54 chunks) và arxiv:2101.01407 (22 trang/58 chunks) parse thành công. Collector tiếp tục Math/Stats, err.log 0 byte. Parser/cache/index coordinators 8000/12952/7760 còn sống.
- Lượt này kiểm tra DB/process/log và poll; không sửa code/dataset hay chạy test. Còn quota 253, hoàn tất parse/cache/index và audit/smoke/dedup/visual review/manifest V1.


## 2026-10-25 22:54:49 +0700 ? X?c nh?n ch?t Catalog B V1 t? arXiv
- Y?u c?u: ch?t Catalog B V1 d?ng arXiv tr??c; OpenAlex ?? b? sung sau.
- ??c `AGENTS.md`, README, plan V2.1, `docs/CATALOG_V1.md`, README snapshot v? m? collector/exporter. T?i li?u hi?n c? ghi V1 ?? ph?t h?nh ng?y 23/10, m?c ti?u 100.000 metadata; quy?t ??nh arXiv-only/OpenAlex deferred ?? ???c ghi nh?n.
- ??i chi?u working DB v? release: m?i b?n c? 100.884 record thu?c CS/Math/Statistics (48.626/37.602/14.656), 100.841 canonical group; release SQLite `integrity_check=ok`. `verification_v1.json` b?o `passed=true`, 87 raw OAI batch v? ki?m tra round-trip SQLite/JSONL/Parquet. ?? so SHA-256 v? byte count theo manifest cho c? 6 file release; t?t c? kh?p. Kh?ng th?y ti?n tr?nh `src.catalog.harvest` ?ang ch?y.
- D? li?u l? metadata, kh?ng t?i PDF; v?n t?n dung l??ng. T?ng th? m?c catalog ?o ???c 1.087.694.952 byte (~1,01 GiB), g?m SQLite, c?c b?n xu?t v? raw XML n?n; ri?ng release kho?ng 683,6 MiB. Snapshot V1 ???c gi? nguy?n, kh?ng t?i l?i ho?c ghi ??. Kh?ng c? API key/secrets trong log.
- Ki?m tra ban ??u c? m?t truy v?n g?p kh?ng tr? output n?n ch?y l?i truy v?n SQLite/CIM; integrity check m?t h?n 10 gi?y nh?ng ho?n t?t `ok`. L?n ??u t?m `verification_v1.json` nh?m trong `v1/`; ???ng d?n ??ng n?m ? th? m?c `data/catalog/`, sau ?? ??c th?nh c?ng. Kh?ng s?a code/dataset trong l??t n?y; ch? n?i log.
- C?n l?i: OpenAlex s? l? b??c b? sung sau. N?u c?n thu v??t ph?m vi V1 100.000 record th? ph?t h?nh phi?n b?n m?i v? gi? nguy?n snapshot n?y.


## 2026-10-25 22:56:16 +0700 — Đính chính mã hóa mục Catalog B V1
- Bản ghi ngay phía trên bị mất dấu tiếng Việt khi PowerShell chuyển nội dung sang Python. Giữ nguyên lịch sử append-only; mục này ghi lại bản chính xác để làm căn cứ.
- Yêu cầu đã chốt: Catalog B V1 dùng arXiv trước, OpenAlex bổ sung sau. Đã đọc quy tắc agent, README, plan V2.1, tài liệu Catalog V1 và mã harvest/release.
- Xác minh working DB và snapshot cùng có 100.884 record (Computer Science 48.626, Mathematics 37.602, Statistics 14.656), 100.841 canonical group. Snapshot SQLite integrity là ok; verification_v1.json báo passed, gồm 87 raw batch. SHA-256 và kích thước của cả 6 file trong manifest đều khớp; không có tiến trình src.catalog.harvest.
- Dữ liệu chỉ gồm metadata, không tải PDF; thư mục catalog hiện chiếm 1.087.694.952 byte (~1,01 GiB), còn release khoảng 683,6 MiB. Collector báo đã release với mục tiêu 100.000. Không tải lại hay ghi đè snapshot; không sửa code/dataset, chỉ ghi log.
- Một lệnh kiểm tra gộp ban đầu không trả output; lệnh integrity check cần hơn 10 giây nhưng hoàn tất ok. Đã tìm verification_v1.json nhầm trong v1/ trước khi sửa đường dẫn về data/catalog/. Hai lần thử tạo payload Unicode bằng TextEncoder/btoa thất bại ngay trong exec vì runtime không có hai API này, chưa sửa file; lần này dùng mã hóa UTF-8/base64 thuần JS. OpenAlex là bước sau; muốn thu vượt V1 thì phát hành phiên bản mới và giữ nguyên snapshot hiện tại.


## 2026-10-25 23:09:15 +0700 — Tiếp tục hoàn tất Corpus C V1
- Yêu cầu: tiếp tục Corpus C theo quota V1 2.000 PDF và các bước parse/index/audit còn lại. Đọc lại docs/CORPUS_V1.md, mã parser/cache/index/audit/smoke/dedup, log và registry resume3.
- Xác minh cùng pipeline resume3: collector PID 30876 đã kết thúc với DOWNLOAD STAGE COMPLETE 2000; DB và status khớp đủ quota {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:200, math_stats:450, systems_algorithms:250}. Không khởi động lại collector.
- Parser PID 11388, cache PID 7020, index PID 17612 vẫn sống ở lần poll cuối. DB có 500 indexed, 335 parsed, 1.165 downloaded; tổng đủ 2.000. Cache đạt 834/2.000 (782 cache hit, 52 encode mới); index đang chờ cache như thiết kế. Parser đang xử lý arxiv:2506.17347; một paper chậm trước đó đã được xử lý xong. Kiểm tra CPU subprocess xác nhận parser hoạt động; đọc mã process.py xác nhận có parse lock đơn, không chạy parser thứ hai.
- Disk còn dồi dào ở poll trước (~348 GB). Không sửa dữ liệu/code, không xóa file, không chạy unit test; để parser/cache/index tiếp tục chạy nền.
- Còn lại: parse và cache 1.165 paper đã tải, chờ index snapshot 2.000, rồi chạy audit, smoke, dedup, xử lý/review candidate trùng, visual review theo gate và chốt manifest/tài liệu. Một lần đọc rg kết hợp cho output dài bị cắt; đã thu hẹp các đoạn tài liệu cần đọc. Hai lần thử nối log chưa chạy được: payload JS đầu có backtick lồng làm lỗi cú pháp; lần thử đầu tiên dùng tool không được hỗ trợ trong exec. Không lần nào chạm tới file; lần này append bằng UTF-8/base64. Pipeline vẫn đang chạy, nên chưa gọi V1 hoàn tất.


## 2026-10-25 23:11:14 +0700 — Tiếp tục parse/cache Corpus C
- Yêu cầu: tiếp tục tiến tới Corpus C V1 đầy đủ. Kiểm tra lại registry, DB, status và worker hiện tại trước khi hành động.
- Collector đã hoàn tất đúng 2.000/2.000; quota DB/status vẫn khớp {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:200, math_stats:450, systems_algorithms:250}. Không khởi chạy lại.
- Parser PID 11388, cache PID 7020, index PID 17612 đều còn sống cùng creation time/command line từ registry. Ở poll cuối DB có 500 indexed, 345 parsed, 1.155 downloaded; cache tiến từ 840 lên 843/2.000 (782 hit, 61 mới mã hóa). Parser tiếp tục ghi paper mới; index đang chờ cache. Không có lỗi worker mới trong log.
- Đã đọc quy trình gate trong docs/CORPUS_V1.md và mã audit/smoke/dedup/index; không chạy unit test hoặc sửa dữ liệu/code. Pipeline giữ nền để tiếp tục.
- Còn lại: parse/cache các paper đang chờ, index snapshot, rồi hoàn thành audit/smoke/dedup, review ứng viên trùng và visual review theo plan, sau đó cập nhật manifest/tài liệu. Goal chưa hoàn tất.


## 2026-10-25 23:14:49 +0700 — Tiếp tục theo dõi parser/cache Corpus C
- Yêu cầu: tiếp tục Corpus C V1. Kiểm tra lại trạng thái đang chạy từ registry resume3, status, SQLite và log trước khi can thiệp.
- Collector vẫn đã hoàn tất 2.000 PDF với quota đủ 6 chủ đề. Parser PID 11388, cache PID 7020 và index PID 17612 còn sống; PID collector 30876 đã kết thúc bình thường trước đó.
- DB tiến từ 340 lên 357 parsed; 500 indexed, 1.143 downloaded. Cache tiến từ 847 lên 856/2.000 (782 cache hit, 74 mới encode). Log parser/cache tiếp tục cập nhật; index vẫn đợi cache theo thiết kế. Không restart worker.
- Đọc docs và mã stage audit/index/smoke/dedup để xác định gate sau pipeline. Không sửa code/dataset và không chạy unit test.
- Còn lại: parse/cache 1.143 paper, index snapshot 2.000, audit, smoke, dedup và xử lý candidate cần review, visual review theo plan, rồi cập nhật manifest/tài liệu. Goal chưa hoàn tất.


## 2026-10-25 23:15:50 +0700 — Poll tiếp pipeline Corpus C
- Yêu cầu: tiếp tục xây Corpus C V1; đọc trạng thái process/DB/log hiện tại thay vì dựa vào checkpoint cũ.
- Giữ nguyên collector đã hoàn tất 2.000/2.000 và đủ quota sáu chủ đề. Parser PID 11388, cache PID 7020, index PID 17612 đều còn sống.
- Qua hai poll trong lượt, DB tăng từ 359 lên 364 parsed; cache từ 859 lên 862/2.000 (782 cache hit, 80 mới encode), số indexed giữ 500, còn 1.136 downloaded. Log parse/cache ghi paper mới; index đang chờ cache.
- Không restart, sửa code/dataset, xóa file hoặc chạy test. Để worker hiện tại tiếp tục.
- Còn parse/cache, build index 2.000, audit/smoke/dedup, review duplicate/visual gates và cập nhật manifest/tài liệu. Chưa hoàn tất V1.


## 2026-10-25 23:18:47 +0700 — Tiếp tục parse/cache Corpus C
- Yêu cầu: tiếp tục xây Corpus C V1. Xác minh lại worker/DB/cache progress hiện tại.
- Collector đã kết thúc với đủ 2.000; quota giữ nguyên đúng {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:200, math_stats:450, systems_algorithms:250}. Parser PID 11388, cache PID 7020, index PID 17612 còn sống.
- So với checkpoint trước, DB tăng từ 365 lên 370 parsed; cache tăng từ 865 lên 868/2.000 (782 hit, 86 encode mới); 500 indexed, 1.130 downloaded. Parser và cache log đã cập nhật lại. Khi cache chững trong hai poll, parser subprocess vẫn sống và dùng CPU; sau đó parser tiếp tục ghi paper và cache bắt kịp. Không restart worker.
- Không sửa code/dataset, không xóa file, không chạy unit test. Còn parse/cache, build index và các gate audit/smoke/dedup/visual review/manifest; V1 chưa hoàn tất.


## 2026-10-25 23:21:33 +0700 — Tiếp tục tiến độ Corpus C V1
- Yêu cầu: tiếp tục Corpus C. Kiểm tra process/DB/log hiện tại và theo dõi cùng pipeline resume3.
- Collector đã đạt đủ 2.000 PDF cùng quota sáu chủ đề. Parser PID 11388, cache PID 7020, index PID 17612 vẫn sống; không restart.
- Từ checkpoint trước, DB tăng 371 → 387 parsed; cache tăng 870 → 886/2.000 (782 hit, 104 mới encode); indexed vẫn 500 và downloaded còn 1.113. Các log parse/cache có record mới; index tiếp tục chờ cache.
- Không sửa code/dataset, không xóa dữ liệu và không chạy test. Còn parse/cache, build index, audit/smoke/dedup, review duplicate/visual gates và manifest cuối. V1 chưa hoàn tất.


## 2026-10-25 23:23:06 +0700 — Tiếp tục theo dõi Corpus C
- Yêu cầu: tiếp tục tiến tới Corpus C V1. Đã kiểm tra process handles, SQLite, status và log pipeline resume3.
- Collector hoàn tất đủ 2.000 và đủ quota sáu topic; parser PID 11388, cache PID 7020, index PID 17612 vẫn sống.
- DB tăng từ 389 lên 396 parsed; cache tăng từ 887 lên 896/2.000 (782 hit, 114 encode mới); 500 indexed, 1.104 downloaded. Parser/cache log có paper mới; index còn chờ cache.
- Không restart worker, không sửa code/dataset, không xóa file và không chạy unit test. Pipeline tiếp tục nền.
- Còn parse/cache, index snapshot, các gate audit/smoke/dedup/review/visual và manifest cuối; goal chưa hoàn tất.


## 2026-10-25 23:26:12 +0700 — Theo dõi Corpus C sau khi parse paper chậm
- Yêu cầu: tiếp tục Corpus C V1. Kiểm tra lại các process và SQLite so với checkpoint gần nhất.
- Collector đủ quota 2.000; parser PID 11388, cache PID 7020, index PID 17612 còn sống.
- DB tiến từ 396 lên 404 parsed; cache từ 896 lên 904/2.000 (782 hit, 122 mới encode), indexed 500, downloaded chờ parse 1.096. Index vẫn chờ cache.
- Trong poll cuối các số chưa đổi khoảng một phút; xác minh parser subprocess đang xử lý arxiv:1807.02504, còn sống và dùng CPU ~20%, chưa tới timeout 300 giây. Giữ worker nguyên trạng, không restart.
- Không sửa code/dataset, không xóa file, không chạy test. Còn parse/cache, index, audit/smoke/dedup/review và manifest; V1 chưa hoàn tất.


## 2026-10-25 23:28:33 +0700 — Tiếp tục parse/cache sau paper chậm
- Yêu cầu: tiếp tục Corpus C V1. Đã kiểm tra lại process handle, DB và log pipeline resume3.
- Collector đã hoàn tất 2.000 và quota không đổi. Parser PID 11388, cache PID 7020 và index PID 17612 còn sống.
- DB tăng từ 404 lên 411 parsed; cache tăng từ 904 lên 909/2.000 (782 hit, 127 mới encode), 500 indexed và 1.089 downloaded. Paper chậm arxiv:1807.02504 đã chuyển sang state parsed; parser tiếp tục paper kế tiếp. Không restart worker.
- Log parser/cache cập nhật; index vẫn chờ cache. Không sửa code/dataset, không xóa dữ liệu, không chạy test.
- Còn parse/cache, index snapshot, audit/smoke/dedup, duplicate/visual review và manifest/tài liệu cuối. Chưa hoàn tất V1.


## 2026-10-25 23:32:17 +0700 — Tiếp tục Corpus C, parser/cache tăng tiến độ
- Yêu cầu: tiếp tục Corpus C V1. Đọc registry resume3 và kiểm tra lại worker, DB, status và log tại máy.
- Collector vẫn hoàn tất 2.000 với đúng quota sáu topic. Parser PID 11388, cache PID 7020 và index PID 17612 còn sống.
- Từ checkpoint đầu lượt, DB tăng từ 411 lên 431 parsed; cache từ 909 lên 928/2.000 (782 hit, 146 mới encode); 500 indexed, 1.069 downloaded. Log parser/cache đều ghi paper mới; index chờ cache.
- Không restart worker, không sửa code/dataset, không xóa file, không chạy test.
- Còn parse/cache, index snapshot, audit/smoke/dedup và review duplicate/visual gate, rồi phát hành manifest/tài liệu. Chưa hoàn tất V1.


## 2026-10-25 23:35:09 +0700 — Tiếp tục Corpus C; parser/cache vẫn tiến
- Yêu cầu: tiếp tục corpus C V1; xác minh lại registry, process, SQLite và log.
- Collector đã kết thúc với đủ 2.000 và topic counts khớp quota. Parser PID 11388, cache PID 7020, index PID 17612 còn sống.
- DB tăng từ 431 lên 454 parsed; cache từ 928 lên 953/2.000 (782 hit, 171 mới encode); 500 indexed và 1.046 downloaded. Log parse/cache đều có paper mới; index chờ cache.
- Không restart worker, không sửa code/dataset, không xóa file, không chạy unit test.
- Còn parse/cache, index, audit/smoke/dedup, review duplicate và visual gate, manifest/tài liệu cuối. Corpus C V1 chưa hoàn tất.


## 2026-10-25 23:37:54 +0700 — Tiếp tục parse/cache Corpus C
- Yêu cầu: tiếp tục tiến tới Corpus C V1. Đã xác minh registry, process, SQLite và log resume3 trong lượt này.
- Collector hoàn tất 2.000 và quota sáu topic vẫn chính xác. Parser PID 11388, cache PID 7020, index PID 17612 tiếp tục sống.
- So với checkpoint 23:35, DB tăng 454 → 475 parsed; cache tăng 953 → 972/2.000 (782 hit, 190 encode mới); indexed 500, còn 1.025 downloaded. Log parser/cache có paper mới; index chờ cache.
- Không restart, không sửa code/dataset, không xóa file, không chạy unit test. Pipeline tiếp tục nền.
- Còn parse/cache, build index, audit/smoke/dedup, duplicate/visual review và manifest/tài liệu; chưa hoàn tất.


## 2026-10-25 23:40:05 +0700 — Tiếp tục pipeline Corpus C V1
- Yêu cầu: tiếp tục Corpus C. Đã đọc trạng thái process, DB, status và log của pipeline resume3.
- Collector hoàn tất 2.000/2.000 với quota {ai_ml:500, computer_vision:300, nlp_llm:300, information_retrieval:200, math_stats:450, systems_algorithms:250}. Parser PID 11388, cache PID 7020, index PID 17612 vẫn sống.
- Từ checkpoint 23:37, DB tăng 475 → 488 parsed; cache 972 → 983/2.000 (782 hit, 201 mới encode); indexed 500, downloaded chờ parse 1.012. Log parser/cache tiếp tục có record mới; index còn chờ cache.
- Không restart worker, không sửa code/dataset, không xóa dữ liệu, không chạy unit test.
- Còn parse/cache, index snapshot, audit/smoke/dedup, duplicate/visual review và manifest/tài liệu cuối. Chưa hoàn tất.


## 2026-10-26 09:20 +07:00 — Tiếp tục xây Corpus C V1

**Yêu cầu:** Tiếp tục hoàn thiện corpus 2.000 PDF arXiv; giữ đúng quota, parse, embedding/index và chốt các kiểm tra dữ liệu.

**Đã làm:** Đọc README, kế hoạch Corpus V2.1, `docs/CORPUS_V1.md` và các module collect/process/cache/index/audit/dedup/smoke; đọc PDF skill để chuẩn bị review mẫu. Kiểm tra lại lỗi resume4: cache dừng vì Windows/OneDrive từ chối thay `cache_progress_2000.json` qua tên tạm dùng chung; index coordinator chạy sớm rồi thoát vì Computer Vision mới có 283/300 bản parse. Không có snapshot `index/v1` hay pointer `active_2000.json` bị tạo ở lần đó.

Sửa `src/corpus/collect.py` để mỗi lần ghi atomic dùng file tạm riêng theo `time_ns`, retry PermissionError khi replace (tối đa 8 lần, backoff đến 2 giây). `py_compile` qua; không chạy test suite. Parser đang chạy từ trước và vẫn giữ nguyên; output của nó là đường dẫn riêng theo paper.

Nối lại pipeline: parser coordinator PID 20752; cache PID 19792; index PID 23420 chờ cache. Cache đã ghi checkpoint mới thành công. Tạo finalizer chạy ẩn PID 10736, đợi index `v1` rồi chạy audit, dedup, smoke; script và registry/log nằm dưới `data/corpus/reports/` với prefix `pipeline2000_20261026_085939_resume5`. Kiểm tra PDF: Poppler `pdftoppm` và PyMuPDF có sẵn để render trang mẫu về sau.

**Kết quả kiểm tra tại 09:20:** Collector registry/log xác nhận đủ 2.000 PDF với quota AI/ML 500, CV 300, NLP/LLM 300, IR 200, Math/Stats 450, Systems/Algorithms 250; không có collector chạy lại. SQLite: 647 parsed, 500 indexed từ snapshot trước, 853 downloaded, 0 parse_failed. Cache resume5: 1.113/2.000 lượt, 1.062 cache hit, 51 encode mới; fingerprint giữ nguyên. Đợt rà sidecar giữa chừng có 1.113 paper, 55.170 chunk, không thiếu quality.json, 2 fallback text; 49,9% dense-candidate theo heuristic, chưa phải nhãn duyệt. Còn hơn 337 GiB trống. `status.json` còn ghi stage `collecting` nhưng số tải là 2.000; stage này không dùng làm bằng chứng worker sống.

**Lỗi thao tác đã xử lý:** Một lần lọc tiến trình bắt nhầm PID PowerShell do command line chứa regex, đã lọc lại theo `python.exe`. Một lần đọc Unicode qua CP1252 và các thử giải mã trong JS thiếu API gây lỗi hiển thị; đọc lại nội dung bằng ASCII escape, không ảnh hưởng dữ liệu. Lần tạo finalizer đầu vướng nội suy `${prefix}` ở template JS trước khi chạy lệnh; đã sửa và khởi chạy thành công.

**Còn lại:** Parser, cache và index vẫn chạy nền; index chưa build. Finalizer sẽ chạy ba gate tự động sau khi index hoàn tất. Chưa render/duyệt mắt mẫu PDF của bản 2.000, chưa có audit/dedup/smoke cuối và chưa cập nhật trạng thái hoàn thành trong `docs/CORPUS_V1.md`.


## 2026-11-11 20:28 +07:00 — Nối lại Corpus C V1

**Yêu cầu:** Tiếp tục pipeline Corpus C sau lần chạy trước.

**Kiểm tra trạng thái cũ:** Không còn parser/cache/index/finalizer hoạt động. SQLite giữ nguyên dữ liệu: 500 indexed, 1.176 parsed, 324 downloaded, 0 parse_failed; quota collector vẫn đủ 2.000 PDF. Cache checkpoint cuối là 1.675/2.000 (1.062 hit, 613 encode mới). Log parser/cache dừng ở 26/10 mà không có dòng hoàn tất hoặc traceback; snapshot `index/v1` và pointer `active_2000.json` đều chưa có. Finalizer cũ cũng không còn chạy. Không tải lại PDF.

**Đã làm:** Nối lại từ SQLite/cache hiện có bằng resume6: parser PID 13148, cache PID 14028, index PID 19896; collector không khởi động lại. Finalizer ẩn PID 4020 chờ index rồi chạy audit, dedup, smoke; script, registry và log mới dùng prefix `pipeline2000_20261111_202636_resume6`.

**Kiểm tra sau khi nối:** Resume6 chạy được; tại khoảng 20:28 có 1.182 parsed, 500 indexed, 318 downloaded, 0 parse_failed. Cache mới đạt 89/2.000 lượt, cả 89 đều cache hit; fingerprint model giữ nguyên. Cache/index stderr chưa có lỗi; index chờ coordinator cache. Dung lượng trống tại preflight khoảng 307 GiB.

**Còn lại:** Còn 318 PDF parse; index chưa build. Finalizer sẽ chạy audit/dedup/smoke sau index. Chưa render và duyệt mắt mẫu PDF, chưa cập nhật trạng thái cuối trong `docs/CORPUS_V1.md`. Không chạy test suite.


## 2026-11-12 10:36 +07:00 — Hoàn tất Corpus C V1 stage 2.000

**Yêu cầu:** Tiếp tục xây Corpus C và chốt lại trạng thái V1 sau khi các bước pipeline hoàn thành.

**Đã làm:** Đọc trạng thái finalizer, audit, dedup, smoke, active pointer, manifest và visual-review receipt. Lần audit trước được ghi mã thoát `1073807364`; nguyên nhân cụ thể chưa xác định. Chạy retry finalizer `data/corpus/reports/finalize_pipeline2000_v1_retry1_20261112.ps1`; audit, dedup và smoke đều trả mã 0, trạng thái finalizer `complete`. Không tải lại hoặc xóa PDF. Snapshot `index/v1` có SHA-256 `fafa1ade7a8da933c7efe76a7c1c62e525adfdcce057c830f8bbd37cd861adf1`, khớp pointer `active_2000.json`.

**Kết quả kiểm tra:** Audit pass với 2.000 PDF, 41.936 trang, 96.922 chunk và quota topic 500/300/300/200/450/250; tổng corpus 8.405.842.007 byte, toàn project 12.409.094.350 byte. Dedup xét 3.366 cặp LSH, không có exact-text group hay near-duplicate candidate. Smoke title-query top 5 đạt 6/6 cho BM25, dense và hybrid; đây chỉ là kiểm tra chẩn đoán. Visual spot-check hoàn tất trên 6 paper/12 trang; paper đều có trong index và các chunk phủ trang đều bật visual grounding. Không còn corpus worker Python hoạt động.

Cập nhật `docs/CORPUS_V1.md` từ trạng thái đang chạy sang snapshot V1 đã audit; ghi quota, số trang/chunk, dung lượng, report links và giới hạn chất lượng. Tài liệu nêu rõ dense detection là heuristic, smoke không phải QA benchmark, math transcription chưa verified, visual review chỉ là spot-check, và snapshot không chứa nhãn QA. Lệnh sửa đầu tiên bị lỗi khớp chuỗi do encoding Unicode của pipeline shell; lệnh chưa ghi file. Đặt encoding UTF-8 rồi cập nhật thành công.

**File liên quan:** `docs/CORPUS_V1.md`; `data/corpus/reports/audit_v1.json`, `dedup_v1.json`, `smoke_v1.json`, `pipeline2000_20261112_v1_retry1_status.json`; `data/corpus/index/v1/manifest.json`, `data/corpus/index/active_2000.json`; `data/corpus/reviews/visual_review_v1.json` và `data/corpus/reviews/images/final2000_sample/`; finalizer script và log dưới `data/corpus/reports/`.

**Còn lại:** Pipeline Corpus C V1 đã chốt. Nếu tiếp tục dùng cho benchmark QA, cần tạo/duyệt nhãn QA và xác minh toán riêng; chưa làm các việc đó trong lượt này. Không chạy test suite.


## 2026-11-12 15:02 +07:00 — Rà soát kết quả toàn bộ dataset

**Yêu cầu:** Tổng hợp tình trạng và kết quả các bộ dữ liệu hiện có trong project.

**Đã kiểm tra:** Đọc README, tài liệu tổng hợp benchmark, Catalog B, Corpus C, benchmark README, kế hoạch liên quan và các manifest/audit/validation hiện hành. Benchmark chính có 5.549 QA (QASPER 5.049 và PDF QA 500), tổng 1.630 nhóm paper canonical, không chia nhóm paper qua split. QASPER validation pass; PDF QA audit pass, 500 câu/46 paper, 128 câu (25,6%) được AI khác đối chiếu, không có human/expert review. Legacy Gold còn 30 candidate dùng cho dev, không cộng vào 500 câu phát hành. LitQA2 có 199 câu. SciCode có 80 bài chính/341 sub_steps; `test_data.h5` (1.049.345.865 byte) và `source.zip` đều khớp byte count/SHA-256 manifest; HDF5 signature hợp lệ. Harness chưa chạy.

Catalog B snapshot audit và verification pass: 100.884 record / 100.841 canonical groups, arXiv metadata-only; release 716.835.267 byte, toàn catalog 1.087.693.746 byte. Corpus C V1 audit pass: 2.000 PDF, 41.936 trang, 96.922 chunk. Đã đọc QUALITY_REPORT: QASPER dev paragraph retrieval có 902/1.005 câu với evidence mapping đủ, 1.501 annotation đủ điều kiện; hybrid đạt Hit@5 57,96%, Hit@10 75,15%, MRR@10 0,3559. Đây là retrieval dev, không phải answer accuracy/test score.

Phát hiện tài liệu còn ghi trạng thái cũ: `docs/BENCHMARK_DATASET_SUMMARY.md` và `data/benchmark/README.md` nói file số SciCode còn tải; `README.md` nói Corpus C còn mở rộng lên 2.000. File thực tế đã hoàn tất SciCode data download và Corpus C V1 đã audit. Chỉ đối chiếu, chưa sửa các tài liệu đó trong lượt trả lời tình trạng. Không chạy test suite hoặc benchmark model.

**File liên quan:** `docs/BENCHMARK_DATASET_SUMMARY.md`, `docs/CATALOG_V1.md`, `docs/CORPUS_V1.md`, `README.md`, `data/benchmark/README.md`, manifests/audits/validation trong `data/benchmark/`, `data/catalog/v1/`, và `data/corpus/`.


## 2026-11-12 15:12 +07:00 — Cập nhật README dataset và push

**Yêu cầu:** Cập nhật README cẩn thận theo trạng thái dataset rồi push.

**Đã làm:** Đọc lại README, Catalog B, Corpus C, benchmark summary/README, các manifest, audit, validation và QUALITY_REPORT. Cập nhật README với tổng quan QA, LitQA2/SciCode, Catalog B, Corpus C, baseline QASPER dev và giới hạn của từng kết quả; bỏ trạng thái Corpus C cũ “đang mở rộng”. Kiểm tra diff whitespace, chuẩn hóa CRLF theo cấu hình Git Windows, rà lại nội dung staged.

Commit chỉ gồm `README.md`: `3e73b436e3b9e8c4c1a15b6b0a452ffde692881b` (`Update README with dataset status`). Push `origin main` thành công; `git ls-remote` xác nhận remote SHA khớp local. Không chạy test suite.

**Phạm vi giữ nguyên:** `.gitignore`, `requirements.txt`, thư mục data, docs, plan, source và test mới khác vẫn giữ nguyên trong worktree, không stage/commit/push ở lượt này.


## 2026-11-12 15:18 +07:00 — Push phần code và tài liệu, loại dataset

**Yêu cầu:** Push gần như toàn bộ thay đổi nhưng không đẩy dataset.

**Đã làm:** Stage có chọn lọc 34 file ngoài `data/`: `.gitignore`, requirements, công cụ `src/benchmark`, `src/catalog`, `src/corpus`, tests tương ứng, plan, docs và worklog. Không có đường dẫn `data/` trong index. Rà tên/nội dung staged và quét token/khóa phổ biến; không có match bí mật. Cập nhật `docs/BENCHMARK_DATASET_SUMMARY.md` để phản ánh `test_data.h5` và `source.zip` đã tải, checksum/size khớp manifest; SciCode harness vẫn chưa chạy. Không chạy test suite. `git diff --cached --check` báo hai trailing spaces ở dòng 5–6 của plan, là line break Markdown có sẵn trong tài liệu.

Commit `e49a9f3` (`Add benchmark and corpus tooling`) đã push thành công lên `origin/main`, sau commit README `3e73b43`. Các file dataset trong `data/` vẫn ở local và không bị xóa hoặc sửa. Lần đọc header plan đầu tiên bị lỗi xuất Unicode CP1252; đã đọc lại bằng UTF-8, không ảnh hưởng file.


## 2026-11-12 21:32 +0700 — Đọc plan kiểm tra pipeline MVP

Yêu cầu: đọc plan và xác định việc cần làm. Đã đọc plan/PLAN_KIEM_TRA_PIPELINE_MVP.md, đối chiếu ingest, Ollama check, evaluator và fixture. Xác nhận cache hiện chỉ kiểm parser/version và file tồn tại; check_ollama vẫn trả True khi thiếu model tag. Hai PDF fixture có sẵn; chưa có PIPELINE_SANITY_REPORT.md. Chưa chạy tests, ingestion hoặc generation trong lượt đánh giá này. Một lệnh liệt kê scripts báo thư mục chưa tồn tại; không ảnh hưởng dữ liệu. Cần Gate 0–6, test cache/artifact/model-tag và báo cáo; chưa triển khai sửa.


## 2026-11-12 21:44 +0700 — Thực hiện plan kiểm tra pipeline MVP

Đã đọc plan và code ingest/LLM/retrieval/evaluator/UI. Gate 0 xác nhận RTX 4050 Laptop 6GB, driver 536.52, Ollama 0.40.16; venv cũ Python 3.10.11. Đã tải qwen3.5:2b; smoke math/code hoàn tất, 100% GPU, không OOM. 26 unit tests ban đầu pass. Đang tạo venv Python 3.11 riêng theo plan, cài CPU torch và requirements, log tmp_sanity_install.log.

Đã sửa cache theo model/revision/config fingerprint, kiểm vector/chunk/page/dtype/norm và rebuild cache lỗi; kiểm readiness model tag; tách citation context và trang ảnh, từ chối câu trả lời rỗng; bổ sung script smoke_e2e và 7 regression tests. Adam 15 trang/39 chunks, FlashAttention 34 trang/76 chunks, ingest và repeat cache ban đầu đạt. Adam hoàn tất 15/15 generation; Flash đang chạy. Artifact sanity lưu riêng data/pipeline_sanity/, được ignore Git.

Đọc skill computer-use và thử native/browser: native pipe unavailable, browser inventory rỗng; chưa kiểm tra được UI bằng màn hình. AppTest render/preview/reload cả hai PDF không exception; lần assert đầu bị encoding chuỗi tiếng Việt trong shell, đã sửa cách assert và chạy lại pass. Endpoint không truy cập và model không tồn tại được kiểm thực tế, trả timeout/404 đúng. Không dừng Ollama đang phục vụ. Còn hoàn tất Python 3.11, Flash E2E, tests và báo cáo gate có giới hạn UI.


**Chốt kiểm tra tự động:** Đã cài xong `.venv-sanity311` Python 3.11.9; pip check không có dependency hỏng; freeze ở data/pipeline_sanity/environment311.txt. PowerShell wrapper install trả 1 do notice pip trên stderr (NativeCommandError), trong log có Successfully installed; xác minh lại bằng pip check và tests thành công. 36 tests pass (26 cũ + 10 sanity). Bổ sung kiểm source SHA, fingerprint parser/package/chunk config, guard UI index dở/hỏng, kiểm query/vector và evaluator exit code/class lỗi. Không tối ưu prompt/ranking/accuracy.

Run 3.11 tách data/pipeline_sanity/py311: Adam 15 trang/39 chunks, FlashAttention 34 trang/76 chunks, vector 384 float32 normalized, upload lại dùng cache. Standalone E2E 30 câu không rỗng, 17 thiếu citation được cảnh báo, 0 citation ngoài context; retrieval 13/13 và 12/13 câu có GT. Evaluator CLI retrieval và generation đều exit 0; run CLI riêng 30 output, 10 thiếu citation, 0 lỗi kỹ thuật/0 citation ngoài context. Các lần chạy riêng không gộp thành quality score. AppTest 3.11 render/preview/reload, 6 QA text/math/code, lỗi QA rồi phục hồi, upload handler fixture và cache đều đạt. Native browser vẫn không khả dụng; Opera connector yêu cầu reauthentication. Ollama smoke 3.11 warm math/code 0,57s/0,56s, 100% GPU ~2940MiB. Streamlit sanity chạy http://127.0.0.1:8502, health ok (session 4333).

Đã tạo docs/PIPELINE_SANITY_REPORT.md; cập nhật README phần cứng/report link và ghi kết quả thực thi vào plan. Những lệnh đọc JSON bằng encoding mặc định bị lỗi Unicode đã chạy lại UTF-8; không ảnh hưởng dữ liệu. Report phân biệt mock/headless/API và native UI chưa kiểm. Chưa gắn nhãn Pipeline Ready hoặc freeze pipeline_baseline_v1 vì bước browser thực còn chặn. Các thay đổi hiện local; không push hoặc đưa dataset/model weights vào Git trong lượt này.


## 2026-11-12 22:15 +0700 — Commit và push pipeline sanity

Yêu cầu: push thay đổi pipeline lên Git. Rà status/diff và chỉ chọn code, README, report, plan, script, tests và gitignore; loại toàn bộ data/ và venv/log local. Kết quả kiểm thử trước commit: 36 tests Python 3.11 pass; gate native UI vẫn blocked như report, chưa freeze baseline. Thực hiện commit/push main và đối chiếu SHA remote sau push; không chạy lại tests vì không có thay đổi implementation sau lần kiểm chứng cuối.


## 2026-11-12 22:28 +0700 — Đọc plan benchmark local LLM

Yêu cầu: đọc PLAN_BENCHMARK_LOCAL_LLM_DEEPRESEARCH.md. Đã đọc các track, 32 ứng viên, phase/gate, scoring, deliverables và đối chiếu runner PDF hiện tại/Git. Main thực tế đã là 44be0c4, khác ghi chú 25180cb trong plan. Browser UI được plan tách khỏi batch benchmark headless. Framework/config/packet mới chưa triển khai; oracle hiện tại chưa tương đương verified gold text. Chỉ đọc/đối chiếu; không pull model, chạy benchmark, đọc test frozen hoặc sửa dataset. Bước đầu phù hợp là Task 1 foundation/dev validation, sau đó config/adapter và evidence packets.


## 2026-11-12T23:08+07:00 — Bắt đầu plan benchmark local LLM

Đã thực hiện foundation: HEAD sanity44be0c4, đọc chỉ dev120 và manifest46paper, kiểm 12 PDF dùng trong dev và133 evidence sidecar SHA/quote/page; validation pass, không mở test_frozen. Smoke Adam/Flash chạy lại từ commit mới, exit0. Khóa screen12 trước output (3/category,11paper,3easy/6medium/3hard,10VI/2EN).

Tạo config32models/protocol/prompt chung JSON, adapter local loopback pin digest/quant/capability/context/think, error/empty/OOM/timeout, packet builder immutable, review receipts khớp source+correctedhash, frozen RAG và vision chỉtrangretrieval, runner tuần tự global lock/resume/retry, scorer null correctness/blind review/CSV/report. Không sửa run_pdf/run_qasper hoặc core parser/retriever. Đã đọc skill PDF, render/xem fullpage3 của2PDF cho2case smoke. Math quote hỏng dấu căn được chép lại đúng ảnh trong eval-only sidecar; receipt AI, không human/expert claim. Poppler có warningfont nhưng ảnh kiểm tra đọc được.

Preflight32 ứng viên có2installed (Qwen2B/4B); không pull thêm. Snapshot đầu khi index/smoke chạy cóRAM0,4GiB; sau process kết thúc snapshot ổn định qua guardRAM2GiB/disk30GiB. Thêm runtimeguard0,5GiB và modeldiskbudget40GiB. Framework smoke trước hardening4/4completed, resume0rows; scorer xuấtmetrics chưareview nêncorrectnessnull. Gold120packets có2receiptAI và118unverified; frozen RAG/vision2packet. 52tests PASS gồm16benchmarktests mới, có120case mockcheckpoint, resume/digest/context/vision/leakage/scoring/resources. Log/output trong data/benchmark/local_llm_runs/, packets ở data/benchmark/local_llm_packets/, tất cả ignoreGit.

Đã tạo docs/LOCAL_LLM_BENCHMARK_PROGRESS.md, cập nhật README link. Chuẩn bị commit local code/config/test/docs để khóa baseline rồi chạy acceptance Gold/RAG sau commit. Không có qualityleaderboard hoặc chọnwinner, không chạy268test. Docs URL Ollama show gặp404, dựa capability /api/show local thực; APIchat/tags/ps đối chiếu docs official. Cònreview10screen, modeldiscovery lớn vàrubric/pairedanalysis trướcfullbenchmark.


**Kết quả acceptance:** Commitlocal a772079 khóa22file code/config/test/docs, không data/venv. Tại commit đó Gold4/4 và Fixed-RAG4/4completed với2model×2case, inputhash mỗi question giống nhau giữa model; cả2track resume0, score/runner đềuexit0. Mỗi track có2missingcitation và1outputtruncated512, không tínhcorrectness. Đã bổ sung logging mọitransportretry, attemptfailure/walltime; thêmregressioncho successfulretrygiữerrorlog; tổng53testspass. Code/runtimepacket khônglộreference/rubric; nguồnparse/retriever/run_pdf/run_qaspergiữnguyên. Cómộtlầnsecret-scan globWindowskhônghợplệ; chạy lạibằngdirectoryscan khôngcómatchsecret. Chuẩnbịcommitlocalbổsunglogvàacceptancereport, rồi smokeGoldcodecuối. Chưa push.


**Preflight tài nguyên:** Smoke preflight giữ 2B ready nhưng đã chặn 4B một lần vì RAM giảm dưới 2GiB; không thay context hoặc xóa weights. Snapshot cũ lưu preflight_resource_limited_v1.json, sau unload RAM đo lại khoảng3,5GiB. Sửa việc mất digest/quant của model installed khi resource gate fail; regression mới kiểm metadata được giữ, tổng54tests PASS. Commit local b1c979f đã giữ log retries/attempt history và acceptance trước đó. Chuẩn bị khóa bản sửa preflight rồi chỉ chạy acceptance nhỏ ở snapshot mới. Không pull thêm model; không chạy screening12/full120/frozen.
