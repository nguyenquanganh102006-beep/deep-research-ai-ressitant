# Tiến độ benchmark local LLM

Cập nhật: 15/11/2026. Phase 0–5 đã có artifact; Phase 6 đang chuẩn bị candidate/freeze v2 sau khi packet builder v1 vấp giới hạn PDF dài. Benchmark-only page override đã triển khai và qua regression tập trung 43/43 cùng full suite 86/86. Chưa chạy inference hoặc scoring. Snapshot chi tiết cũ hơn bên dưới là nhật ký lịch sử; bảng này là trạng thái mới nhất.

## Task và gate

| Task | Trạng thái | Bằng chứng |
|---|---|---|
| 1. Foundation và framework | PASS | 32 candidate có trạng thái; runner Track A/B/C, scoring, reports và regression hiện có. Cập nhật runner đã thêm đường test chỉ sau freeze. |
| 2. Screen và full dev | PASS, AI-only review | 12-model shortlist; full Track A/B và paired comparisons theo cùng ID. Human/expert audit chưa có. |
| 3. Phase 5 repeats/ablation | PASS cho repeat và vision ablation | 4 model lặp seed 42/43/44 trên Track A/B; Track C vision/text paired 98 câu. Q4/Q8 và context/thinking phụ không chạy. |
| 4. Candidate | CHỐT TRƯỚC TEST | `qwen2.5:3b` Q4_K_M candidate; `qwen3.5:2b` Q8_0 baseline; hash, retrieval protocol, rubric và thresholds ở `docs/BENCHMARK_CANDIDATE_SELECTION.md` và `configs/benchmark/final_candidate_v1.json`. |
| 5. Phase 6 frozen test | CHỜ COMMIT/FREEZE V2 | Freeze v1 (`caa1d64`) được giữ làm lịch sử nhưng đã lỗi thời sau khi packet builder dừng ở PDF 75 trang. Override tối đa 200 trang chỉ cho benchmark đã qua 43 focused tests và full suite 86/86; app mặc định vẫn 50. Chưa chạy inference/score; cần commit/push code/config/docs/log rồi tạo freeze v2. |

### Pretest snapshot 2026-11-15

- Protocol text-only Track B SHA-256 `9df24203808769302467709910d7e30522cac119cf7df83756a3c073d08dedb9`; prompt SHA `36a4ef28b0c7977d3ccb32d3d90e87a553f8e2259af5e7e7fb56743468e22cb6`; judge protocol v2 SHA `4aa5f3d910ecdf312b15d082f506f4e92a435f46df6a43fbe8f734db4ed9030a`.
- Current resources: RAM available 4,85 GiB; GPU RTX 4050 Laptop, 5.345 MiB free VRAM; C: free 246 GiB; Ollama 0.40.16. Both selected models are installed; `ollama ps` was empty at snapshot.
- Hash capture after commit `caa1d64`: **268** rows, test SHA-256 `ea5fa56c6af74ec77f50da7c3dbaa986f138fc08c02dc9bba195956fb410dc40`. The packet builder used the held-out question fields after freeze but stopped at a 75-page PDF; it wrote no packet and ran no model. It did not expose answer labels to model/reviewer or output them.
- The 75-page paper exceeds the app's 50-page upload default. The benchmark packet builder now admits at most 200 source pages; the default app limit, parser extraction, chunking, embedding and retrieval ranking remain unchanged. This limit is in the candidate config and pipeline-code hashes and will be bound to freeze v2 before inference. The failed build may have created local parsed caches in `data/papers`; they are retained.
- Regressions after the change: focused benchmark + pipeline suite **43/43 PASS**; full suite **86/86 PASS**. Freeze v1 recorded test SHA-256 `ea5fa56c6af74ec77f50da7c3dbaa986f138fc08c02dc9bba195956fb410dc40` for 268 rows. Packet construction read the held-out question records, then stopped at the 75-page admission check; it wrote no packets and ran no inference or scoring. Answer labels were not printed or forwarded to a model/reviewer.
- Next: commit/push code/config/docs/log only; create `final_test_freeze_v2.json` bound to the final candidate commit; capture and verify the same dataset hash; build all 268 packets; run candidate and baseline once; blind AI review and score.

Regression hiện tại: **60 tests PASS** (36 cũ + 24 benchmark), log `data/benchmark/local_llm_runs/foundation_stable_v1/regression.log`. Test 120 case dùng mock, không được xem là 120 lượt model thật.

## Snapshot và phạm vi

- Python 3.11.9 trong `.venv-sanity311`, Ollama 0.40.16, RTX 4050 Laptop 6GB / driver 536.52.
- Dev: Math 40, Code 27, Table 31, Negative 22; SHA `d2482ab73c5068b078e6cdef2b40136d7e0bba4a62446d8024f7f74c461b14ff`.
- Đã khóa `configs/benchmark/dev_screen12.json`: 3 câu/category, 11 paper, 3 easy/6 medium/3 hard, 10 VI/2 EN. Math trong sample đều medium; không đổi sample theo output.
- Hai ID smoke `math-0064`, `code-0065` đã chọn trước generation, là subset của screen12.
- Config dùng JSON thay YAML để không cần thêm dependency; protocol: context 4096, output512, temperature0, seed42, prompt chung. Seed không đảm bảo deterministic tuyệt đối.
- UI browser chưa verified được ghi riêng; không chặn benchmark batch headless theo plan.

## Evidence và chống leakage

Quote/page/hash validation không tự xác minh công thức. Đã nhìn toàn trang PDF render cho đủ 12 câu screen (2 smoke foundation và 10 câu review tiếp), lưu receipt AI/provenance/image SHA. Quote Math có lỗi extraction dấu căn; bản chép được sửa đúng nguồn trong sidecar evaluation-only, không sửa dataset gốc hoặc nhét reference answer vào packet.

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

Artifacts: `framework_acceptance_gold_v1/`, `framework_acceptance_rag_v1/`, `framework_acceptance_status.json` dưới `data/benchmark/local_llm_runs/`. Scoring và template đã xuất; correctness vẫn null. Bổ sung sau acceptance: log mọi transient retry, giữ số failed attempts và total wall time để không che lỗi sau retry thành công; regression 55 pass. Acceptance cuối sau hardening bị dừng ở preflight vì chỉ 2B ready; xem `framework_final_status.json`. Không tạo run 1-model rồi gọi là acceptance 2-model. Các run a772079 vẫn là bằng chứng smoke tại đúng commit đó, không resume chúng từ code mới.

## Chạy acceptance từ code đã khóa

```powershell
.\.venv-sanity311\Scripts\python.exe scripts/benchmark_local_llms.py --packets data/benchmark/local_llm_packets/gold_smoke2_verified_v1.jsonl --models qwen3.5:2b qwen3.5:4b --run-dir data/benchmark/local_llm_runs/framework_acceptance_gold_v1
# Sau đó chạy lại đúng lệnh với --resume: phải tạo 0 dòng mới
.\.venv-sanity311\Scripts\python.exe scripts/score_benchmark.py --run-dir data/benchmark/local_llm_runs/framework_acceptance_gold_v1
```

Bộ screen12 đã review đủ. Bước tiếp theo: kiểm lại tài nguyên, hoàn thiện model discovery/batch đầu và rubric review trước matrix screening. Chưa đủ căn cứ chọn default/math/code/vision specialist. Full120 dev và268 frozen chưa chạy.

API tham chiếu: [Ollama chat](https://docs.ollama.com/api/chat), [model list](https://docs.ollama.com/api/tags), [running model metadata](https://docs.ollama.com/api/ps). Capability được lấy từ `/api/show` thực tế trên bản Ollama cài local; lỗi docs URL show đã gặp404 khi tra cứu, không dùng làm bằng chứng capability.


Preflight đã ghi nhận một lần 4B bị `resource_ineligible` khi RAM available giảm sau smoke 2B; snapshot giữ tại `preflight_resource_limited_v1.json`. Sau unload đã đo lại ~3,5GiB available. Metadata installed/digest/quant được giữ ngay cả khi smoke bị chặn; không đồng nhất “installed” với “ready”. Code đã có regression cho trường hợp này.


## Trạng thái cuối lượt foundation

- Preflight mới (`preflight_refreshed_v2/`) đã qua integrity/disk/RAM gate lúc bắt đầu nhưng chặn 4B ở gate RAM trước smoke; 2B ready, 4B installed nhưng chưa ready ở snapshot này, 30 tag khác chưa installed. Không suy rằng 4B không thể chạy trên6GB: acceptance trước đó đã quan sát GPU-only thành công, tài nguyên RAM available thay đổi theo thời điểm.
- `framework_final_status.json` ghi `resource_or_preflight_pending`; chưa chạy matrix screening12 hoặc full120.
- 55 tests đạt, gồm kiểm 120-case mock, retry history, giữ metadata model khi RAM fail và dựng leaderboard không reset metrics/review. CLI leaderboard thực đã giữ nguyên hash metrics khi render lại.
- Code đã commit local theo các bước foundation/hardening; chưa push. Dataset/model weights/packet/output vẫn ở ngoài Git. Run mới phải dùng baseline/hash mới, không nối vào các run từ code cũ.
- Việc tiếp theo là có snapshot RAM ổn định đủ cho batch, rồi model discovery/screening; review evidence cho screen12 đã hoàn tất. Chưa có điểm correctness để chọn model thắng.


## Review evidence screen12 hoàn tất — 13/11/2026

Đã tự đối chiếu 10 câu còn lại với đúng PDF version/hash và trang, nâng tổng screen lên **12/12 receipt AI**. Đây là review fidelity của evidence và kiểm tra tính nhất quán với nguồn; không phải human/expert gold hoặc chấm output model.

| ID bổ sung | Kết quả review |
|---|---|
| math-0122 | Đối chiếu định nghĩa reliability diagram/identity; chuẩn hóa ligature |
| math-0139 | Đối chiếu cả hai đoạn MNIST/norm/test-error trên trang9; nối line wrap |
| code-0041 | Khôi phục dòng pseudocode, spelling Initialize và walk[-1] |
| code-0093 | Giữ đúng actor loop và subscript theta_old |
| table-0011 | Chép đầy đủ headers và cả3 hàng Table3, giữ phép đo/caption |
| table-0059 | Chép toàn bộ panel FFHQ Table1, tất cả hàng/cột; không trộn các dataset khác |
| table-0099 | Chép đầy đủ hai hàng và mọi metric Table6; không thêm phép trừ đáp án vào evidence |
| negative-0037 | Khôi phục cấu trúc TableA1; kiểm phạm vi dataset/cutoff/snapshot trong PDF |
| negative-0039 | Đối chiếu warning leakage, tìm kiếm toàn bộ PDF theo thuật ngữ liên quan |
| negative-0058 | Đối chiếu Section2.2 và AppendixD; bỏ fragment/heading thừa, giữ các câu nguồn hoàn chỉnh |

Keyword search bổ trợ phủ 36 trang Chinchilla và48 trang CLIP; log lưu kèm hash receipt. Đây là tìm kiếm có phạm vi để phát hiện mâu thuẫn, không phải bằng chứng hình thức rằng một thông tin tuyệt đối không tồn tại. Model chỉ được kỳ vọng từ chối theo evidence được cung cấp.

Artifacts mới (local, không Git):

- `data/benchmark/local_llm_packets/reviews/screen12_v1.jsonl`: 12 receipt, gồm2 receipt smoke cũ và10 mới.
- `data/benchmark/local_llm_packets/gold_screen12_verified_v1.jsonl`: 12 packet đã review; SHA-256 `bd7d8ad88e205552bbabf7a56235ea339d4ded822e25c4e33e5d1e232651cd84`.
- `data/benchmark/local_llm_packets/gold_text_verified_v2.jsonl`: full dev version mới, 12 reviewed/108 unverified. File v1 vẫn giữ nguyên.
- `reviews/screen12_context_validation.json`, `reviews/screen12_review_summary.json`: cả12 packet qua budget context hiện tại, không cắt gold text.
- `review_images/screen12/`, `reviews/screen12_absence_search.json`: source render và keyword-search evidence.

Khi screening, truyền rõ `--packets data/benchmark/local_llm_packets/gold_screen12_verified_v1.jsonl`; không dùng nhầm file v1 cũ chỉ có2 receipt. Đã kiểm hash PDF/image, receipt source/corrected evidence, packet checksum, đúng12 ID/category và prompt whitelist. Hash dev/papers gốc không đổi. Không chạy model hoặc test frozen trong lượt review; không đổi code/protocol hoặc chạy lại unit suite vốn đã pass55 tests.


## Screening và RAM — cập nhật 2026-11-13 15:31 +0700

Đã chạy Gold screen12 với cùng protocol/context 4096 và packet đã verified trên Qwen3.5 2B Q8_0 / 4B Q4_K_M. Lần đầu hoàn thành 18/24 case; 6 case 4B bị RAM guard chặn. Sau unload/nạp lại model và retry đúng 6 case còn thiếu, trạng thái mới nhất là **24/24 completed**. Lịch sử giữ nguyên **30 records: 24 completed + 6 resource_ineligible**. Resume cuối tạo 0 case mới; scorer/leaderboard exit 0. Correctness vẫn chưa chấm rubric; không dùng completion để kết luận chất lượng hay chọn model thắng.

Máy có 15,71 GiB RAM, RTX4050 6 GiB. RAM available ban đầu 4,08 GiB; monitor quan sát thấp nhất 0,462 GiB ở đợt đầu và 0,464 GiB ở retry. Đây là mẫu đo định kỳ, không bảo đảm bắt được đáy tuyệt đối. 2B chạy đủ 12 case trong lượt đầu; 4B có thể chạy nhưng sát giới hạn RAM, chưa đủ bằng chứng ổn định cho full120. Không hạ ngưỡng RAM/context và không đóng ứng dụng của người dùng.

Đã kiểm chứng 12 input hashes giống nhau giữa hai model, packet SHA giữ nguyên và mỗi model đủ 12 case duy nhất. Artifacts: `data/benchmark/local_llm_runs/screen12_20261113_151744/` (status, resource samples, integrity); output/report ở `gold_screen12/`. Review template và bản trộn theo review_id đã tạo, chưa có receipt chấm output.

Batch đầu 6 model đang được chuẩn bị tuần tự dưới disk budget 40 GiB: gemma3:4b và qwen3:4b đã tải thành công; qwen2.5-coder:3b và phi4-mini:3.8b còn trong job tải/preflight khi ghi cập nhật này. Installed không đồng nghĩa ready; cần xem `batch6_preflight/preflight.json` khi job kết thúc. Không chạy download song song với lượt screening đã đo. Full120 và frozen chưa chạy; chưa push.


## Goal tiếp tục plan — batch6 đã chấm, mở rộng discovery

Screen12 batch đầu: 72 case duy nhất, 60 completed đã có receipt AI rubric và 12 empty_output của Qwen3:4b. Nguồn Qwen2B/4B giữ thêm6 record RAM skips trước retry, không xóa lịch sử. Hai run dùng cùng packet/prompt/protocol và code baseline776b0dc; kiểm tra model names ẩn ở review template, trộn thứ tự theo review_id. Judge không phải chuyên gia độc lập; không thay human spot-check trong plan.

| Model | Rubric mean/12 (AI) | Completed | Latency p50 (s) |
|---|---:|---:|---:|
| qwen3.5:2b | 0.333 | 12/12 | 4.70365 |
| qwen3.5:4b | 0.667 | 12/12 | 4.2848 |
| gemma3:4b | 0.708 | 12/12 | 2.78095 |
| qwen3:4b | 0.000 | 0/12 | N/A |
| qwen2.5-coder:3b | 0.458 | 12/12 | 1.5596 |
| phi4-mini:3.8b | 0.458 | 12/12 | 1.4039 |

Đây là screening12, không phải xếp hạng cuối. Mean gồm partial0.5 và technical failure0; mỗi category chỉ3 câu, chưa đủ chọn default. Native-only thinking của Qwen3:4b không xuất nội dung cuối trong budget512 ở12case; không tự tăng budget riêng. Chi tiết/error notes ở ai_reviews_v1.jsonl từng run; screen12_initial6_summary.json tổng hợp local.

Đã probe32 manifest registry: tất cả tag available. Tổng dung lượng nhóm A dự kiến37,94GiB; job discovery32_20261113/continue_batch.py tải tuần tự phần A còn thiếu, giữ40GiB model budget/30GiB disk free, sau đó smoke toàn registry và chạy screen12 cho model mới ready. Nhóm B được ghi resource_ineligible nếu không còn budget; không bắt buộc32 model đều chạy. Job dùng cùng OS runtime lock, tránh download/inference chồng nhau; chưa coi job hoàn thành.

Evidence full dev: đã đối chiếu thêm9 câu BatchNorm trên6 trang và29 câu node2vec/TRPO/PPO trên6 trang render, gồm restoring formula/pseudocode và scoped Negative context. Packet gold_text_verified_v4.jsonl có50 verified/70 unverified;50/50 qua context guard. Receipt dev50_v1.jsonl và source image hashes đã lưu; giữ v1/v2/v3 bất biến, không sửa dataset gốc. Negative search bổ trợ lưu code29_absence_search.json; PPO có công thức bootstrap hữu hạn nhưng không đặc tả riêng env time-limit terminal mask; không biến chi tiết thiếu thành khẳng định không có bootstrap.


Cập nhật tiếp 2026-11-13T15:52:30.159508+07:00: thêm9 câu calibration được đối chiếu4 trang PDF; phục hồi ECE/MCE/NLL, binning, scaling và toàn bộ Table1 (không thêm đáp án tính toán). dev59_v1.jsonl / gold_text_verified_v5.jsonl hiện59 verified,61 unverified;59/59 fit context. Kiểm chứng72 case screening duy nhất,12 input hashes giống nhau giữa6 model và screen packet SHA giữ nguyên. Discovery job tiếp tục, chưa full dev/frozen.


## Full dev evidence v? discovery32 ?? kh?a ? 2026-11-13T16:07:45.619451+07:00

- ?? review to?n b?120 dev: b? sung13 c?u RoBERTa/ALBERT tr?n8 trang,8 c?u Chinchilla tr?n5 trang + t?i d?ng TableA1 verified,10 c?u LDM tr?n7 trang v?11 c?u CLIP tr?n10 trang. Gi? ?? c?c b?ng li?n quan; t?ch Table10 nhi?u kh?i Table9 LDM. C?ng th?c/algorithm/table ???c ch?p l?i t? ?nh; kh?ng t?nh ??p ?n ho?c d?ng c?c chi ti?t ngu?n kh?ng n?u. Negative gi? gi?i h?n c?a ki?m tra absence; keyword search to?n PDF ch? h? tr? ??i chi?u.
- Packet ch?nh cho full dev: `data/benchmark/local_llm_packets/gold_dev120_verified_v1.jsonl`, SHA `5b211c812a637199ad5aeb0a82bf9dc31fa34de31619bf0cbca9c64b2eed8f3c`. Receipt `reviews/dev120_v1.jsonl`; validation `reviews/dev120_validation.json`:120/120 verified v? eligible, kh?ng l?i context, PDF/?nh/receipt hashes kh?p. ??y l? AI fidelity review, kh?ng ph?i human audit. Packet screen12 c? gi? nguy?n ?? kh?ng ??i ?i?u ki?n screening.
- Discovery32:23 installed,22 smoke-ready,1 empty_output ? smoke;9 B resource_ineligible do budget40GiB model disk sau ?u ti?n A. Metadata/checksum/quant v? policy l? do ri?ng ???c gi? trong `discovery32_20261113/discovery32_final_status.json`; kh?ng g?i c?c B l? thi?u RAM hay tag kh?ng t?n t?i.
- Job19359 ?ang screening16 model m?i ready (192 case d? ki?n), ch?a g?i screening ho?n t?t. Job15075 ?? x?p h?ng b?ng OS runtime lock: sau screening s? freeze retrieval120 m?t l?n v? render ?nh ??ng trang retrieval. Kh?ng ch?y CPU retrieval/download ??ng th?i timed inference.
- Ch?a ch?n finalists, ch?a ch?y full120 inference/ablation/frozen. Gate ti?p theo: ch?m screening m? r?ng, ch?n8?12 finalist v?i baseline/role coverage, r?i A/B full dev; image-token eligibility c?n ch?t tr??c TrackC. Human spot-check ch?a c?, kh?ng thay nh?n AI th?nh human.


## Screening mở rộng và sửa tách final answer — 2026-11-13T16:22:36.983850+07:00

Screening16 model mới kết thúc exit0 với192 raw completed. Đã chấm mù120 output của10 model đầu; receipt `screen12_new/ai_reviews_first120_v1.jsonl` SHA `9de43afde18203a8a3da84b650f700eb6abdc114e53dfa6f68f6796810be8c9b`. Chưa chốt finalist.

Trong72 output còn lại phát hiện12 content bắt đầu bằng inline `<think>`: chỉ2 có thẻ đóng và câu trả lời cuối;10 chỉ reasoning. Adapter trước đó coi toàn content là answer. Đã sửa extractor để chỉ chấm phần sau các khối think ở đầu; khối chưa đóng/không có final là empty_output. Raw output và usage khi lỗi được giữ trong diagnostics. Đây là lỗi postprocessing, không tăng token budget hoặc đổi input model.

Tạo analysis-only view `discovery32_20261113/screen12_final_content_v2/` bằng `scripts/normalize_benchmark_answers.py`:192 records gồm182 completed+10 empty_output. Source predictions/manifest giữ nguyên và hash được dẫn trong manifest mới; analysis-only view không được resume inference.120 receipt đã chấm vẫn khớp vì không thuộc12 output inline; còn62 final answers cần review. Template remaining72 raw là bản superseded, không dùng để chấm. Batch đầu6 model không có inline think nên điểm trước giữ nguyên. Trên toàn screening22 model:264 unique cases,242 final completed+22 empty_output; giữ thêm6 resource skips cũ của4B trong raw history.

Regression59 tests PASS sau sửa, gồm không chấm citation trong reasoning, reasoning-only tính failure/giữ usage, analysis view giữ nguyên source và failure denominator, chặn resume analysis. Mock runner tests dùng runtime lock riêng để không tranh lock job thật. Logs `regression_final_content_v2_complete.log`; diff-check đạt. Job retrieval15075 vẫn đang chạy trên CPU, inference đã dừng đúng lock; chưa full120 inference/frozen.


Cập nhật 2026-11-13T16:23:47.972386+07:00: job retrieval15075 đã kết thúc exit0; khóa120 TrackB text và120 packet ảnh TrackC. Validation retrieval120_validation.json xác nhận ID/hash/content/order và ảnh chỉ từ trangretrieval,120text fit context. Chưa xác lập image-token eligibility hoặc chạy inferencevision. Baseline code sửa inline thinking đã commitlocal e80f9b1;59testsPASS; chưa push.


## Screening chấm đủ và khóa shortlist12 — 2026-11-13T16:32:39.822242+07:00

Đã lưu62 receipt final-content-only còn lại, kết hợp182 receipts cho16 model mới; scorer exit0. Toàn screening22 model:264case,242 completed đã cóAI rubric review,22empty_output; giữ6resource skips cũ trong lịch sử. Cùng12ID/prompt/protocol/packet, input hash từngID giống nhau. Tổng hợp tại data/benchmark/local_llm_runs/screening22_final_v2/: leaderboardCSV,summaryJSON,paired bootstrap CI thăm dò và reviewed_predictions.

Đã khóa configs/benchmark/finalists.json gồm12model trước khi xem full dev outputs. Chọn theo category/latency/VRAM/role coverage và luôn giữQwen2B; không lấy điểm tổng12câu làm kết luận thắng. Qwen3hybrid/Granite/Qwen2.5 là ứng viên math; không gọi Phi reasoning specialist vì10/12thinking-only failures trong budget512. Báo cáo đầy đủ: LOCAL_LLM_SCREENING_REPORT.md. RAMavailable snapshot5,29GiB,VRAMfree5932MiB; đủ bắt đầu acceptance nhỏ rồi fullA/B tuần tự với guard. Human spot-check chưa có.


Trước full dev 2026-11-13T16:34:42.748910+07:00: sửa scorer để resource_ineligible ở case đã chọn vẫn thuộc eligible/technical_failure và tính missed task, không làm mẫu số nhỏ đi. Candidate bị preflight loại không có case nên vẫn được tách khỏi leaderboard. Regression60testsPASS; screening latest không cònresource skip nên điểm quality shortlist giữ nguyên,6historical skips đã báo riêng. Shortlist đã commit49c504f; chuẩn bị baseline mới với scorer sửa này.
