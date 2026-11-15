# Lựa chọn candidate trước frozen test

**Trạng thái:** lựa chọn được khóa trước test; kết quả gate frozen cuối cùng là **FAIL** do category Code dưới ngưỡng. Candidate selection bên dưới là cấu hình đã đem đi đánh giá, không phải xác nhận đạt gate.
**Track cuối:** `retrieved_text_frozen` (Track B), 268 câu.
**Nguồn chấm:** AI-only blind rubric review; chưa phải human/expert gold.

## Model đã chọn

| Vai trò | Tag | Digest | Quantization | Lý do |
|---|---|---|---|---|
| Candidate mặc định | `qwen2.5:3b` | `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b` | `Q4_K_M` | Điểm Track B ổn định qua seed 42/43/44, không có lỗi kỹ thuật; nhanh hơn baseline trên dev. |
| Baseline | `qwen3.5:2b` | `0689d44085e06d165161a8a9a1731344278cfb5aade63a3c3dbdb48ab54b130a` | `Q8_0` | Giữ baseline đang dùng để so cặp trên cùng 268 packet. |

### Căn cứ trên dev

- `qwen2.5:3b` Track B all-eligible mean theo seed 42/43/44: **0,463 / 0,458 / 0,463**, 0 lỗi kỹ thuật ở cả ba lượt. Hai seed 43/44 dùng cùng source code và cùng input.
- Baseline `qwen3.5:2b`: **0,200 / 0,329 / 0,333**; lượt seed 42 có 33 lỗi kỹ thuật. Seed 42 thuộc snapshot code cũ hơn; báo cáo repeat đã audit và chỉ cho phép khác hash ở `local_cli.py`, `runner_local.py`, `scoring_local.py`, trong khi per-question input/evidence hash giống nhau. Seed 43/44 dùng cùng code.
- Ở Track B seed 43/44, candidate đạt Math **0,438**, Code **0,426**, Table **0,371/0,387**, Unanswerable **0,659**. Không chọn math/code specialist: khác biệt theo nhóm chưa đủ cơ sở để thêm model và độ trễ granite4:3b cao hơn.
- `qwen3.5:2b` vision có paired gain dev **+0,133** trên 98 câu so với cùng model text-only (95% bootstrap CI **[+0,041, +0,224]**). Đây là ablation AI-reviewed, không phải test held-out. Nhánh vision không nằm trong candidate chính và không được chấm trong protocol Track B cuối.

Nguồn: [repeat seed report](PHASE5_REPEAT_SEED_COMPARISON.md), [paired vision/text report](TRACK_C_PAIRED_COMPARISON.md). Machine-readable selection và hash nằm ở [`final_candidate_v1.json`](../configs/benchmark/final_candidate_v1.json).

## Protocol và tiêu chí đã khóa

- Prompt chung: `configs/benchmark/prompt_v1.txt`, SHA-256 `36a4ef28b0c7977d3ccb32d3d90e87a553f8e2259af5e7e7fb56743468e22cb6`.
- Test protocol: `configs/benchmark/final_test_protocol_v1.json`, SHA-256 `9df24203808769302467709910d7e30522cac119cf7df83756a3c073d08dedb9`.
- Judge rubric: protocol v2, SHA-256 `4aa5f3d910ecdf312b15d082f506f4e92a435f46df6a43fbe8f734db4ed9030a`.
- Retrieval: pipeline hiện có, hybrid dense + BM25 / reciprocal-rank fusion, top-5, tối đa 5 context, không thêm neighbor; cùng text packet cho hai model. Packet builder cho benchmark được phép ingest PDF tối đa 200 trang để giữ nguyên toàn văn các paper; giới hạn upload app vẫn 50 trang. Parser, chunker, embedding và ranking không đổi.
- Scoring: correctness 0/0,5/1; citation support báo riêng. Lỗi kỹ thuật tính là 0 trong mẫu số eligible; không bỏ case lỗi để tăng điểm.
- Ngưỡng candidate: overall **≥0,40**; mỗi category **≥0,35**; tối đa **2/268** lỗi kỹ thuật; paired gain so với baseline **≥0,05** và cận dưới CI 95% **>0**. Bootstrap 10.000 lần, seed `20261115`.
- Không điều chỉnh prompt, retrieval, model, quantization hoặc ngưỡng sau khi xem kết quả test. Kết quả này không dùng để tuning.

## Kết quả frozen test v2

Scorer đã chạy một lần trên test 268 câu cho mỗi model; mọi prediction khớp freeze và có review receipt. Review mù và adjudication do AI thực hiện, chưa có human/expert audit.

| Chỉ số | Candidate `qwen2.5:3b` Q4_K_M | Baseline `qwen3.5:2b` Q8_0 |
|---|---:|---:|
| Overall | 0,453 | 0,343 |
| Math | 0,428 | 0,311 |
| Code | 0,311 | 0,273 |
| Table | 0,422 | 0,405 |
| Unanswerable | 0,704 | 0,417 |
| Lỗi kỹ thuật | 0/268 | 0/268 |

Candidate-minus-baseline paired gain **+0,110** trên 268 câu (bootstrap CI 95% **[+0,062, +0,159]**). Candidate đạt ngưỡng overall (≥0,40), technical failures (≤2), paired gain (≥0,05) và CI lower >0. Candidate **không đạt ngưỡng mỗi category ≥0,35** vì Code chỉ 0,311; do đó kết quả tổng thể theo gate đã khóa là **FAIL**.

Đã hợp nhất 536 review receipts: 113 lượt audit chéo độc lập thay cho bản review đầu, 28 bất đồng correctness được adjudicate; trạng thái citation được chuẩn hóa theo judge protocol và allowed pages. Toàn bộ quy trình vẫn là AI-only, không phải human/expert gold. Raw predictions, review sidecars, receipts và báo cáo máy ở `data/benchmark/local_llm_runs/final_test_v1/`; không đưa dataset/artifact data vào Git. Báo cáo final lưu local tại `data/benchmark/local_llm_runs/final_test_v1/final_test_report.md`; xem thêm [tiến độ](LOCAL_LLM_BENCHMARK_PROGRESS.md).

Không tune prompt, retrieval, model hoặc ngưỡng dựa trên kết quả này. Nếu muốn cải thiện candidate, làm trên dev theo version mới và dành một held-out split mới cho lượt đánh giá tiếp theo.

## Phạm vi và giới hạn

- Chỉ hai model text ở trên thuộc primary frozen evaluation; không có specialist hoặc vision fallback trong candidate cuối.
- Không chạy Q4-vs-Q8 cùng kiến trúc hay context 8K/native-thinking ablation: chúng không cần thiết để chọn Track B candidate trong vòng này.
- Phần cứng được ghi trước freeze trong machine-readable config. Snapshot trước test: Windows 10 build 26300, Python 3.11.9, Ollama 0.40.16, RTX 4050 Laptop 6 GB / driver 536.52, RAM khả dụng khoảng 4,85 GiB, VRAM trống 5.345 MiB.
- Một paper frozen có 75 trang, vượt admission cap mặc định 50 trang. Vì vậy chỉ benchmark builder dùng max 200; app production vẫn giữ MAX_PAGES=50. Giới hạn này đã được ghi trong candidate config và pipeline source hashes trước inference. Freeze v1 (`caa1d64`) không có override này và bị supersede sau khi builder dừng; freeze v2 đã bind giới hạn mới trước khi chạy model. Lần build v1 chưa ghi packet và chưa chạy inference/scoring.
- Corpus QA là AI-reviewed. AI agents hỗ trợ chấm mù, nhưng chưa có human/expert audit; không diễn giải điểm như xác nhận khoa học độc lập.

## Freeze và kết quả thực thi v2

Freeze v2 bind commit `39c79f372475dba7d892a49f7ef76935e7cf11b0`, page allowance 200, test SHA-256 `ea5fa56c6af74ec77f50da7c3dbaa986f138fc08c02dc9bba195956fb410dc40`, và packet SHA-256 `c5df1b6e6553d89730fd2ced1b166d91ed704a39ba941c48c09ce971f339f7b8`. 268 packet/evidence checksum, manifest, split/track và kiểm tra loại trừ answer/rubric đều đạt.

Lượt frozen sau đó hoàn tất 268/268 prediction cho mỗi model, không có lỗi kỹ thuật. Điểm và kết luận theo gate được ghi ở phần trên; candidate không đạt gate vì Code 0,311. Review được tổng hợp thành 536 receipt, gồm 113 audit chéo và 28 adjudication correctness. Chỉ số citation/claim-support và receipt chi tiết ở các artifact local dưới `data/benchmark/local_llm_runs/final_test_v1/`. AI review không thay thế human/expert gold. Không thay code, prompt hoặc ngưỡng sau khi mở test.
