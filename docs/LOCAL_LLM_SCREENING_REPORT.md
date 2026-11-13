# Screening local LLM — 22 model

Khóa shortlist: 2026-11-13T16:29:56.562875+07:00. AI rubric review; không phải human/expert gold.

264 case:242 final completed đã review,22 empty_output. Lịch sử còn6 resource skips của4B trước retry. Cùng12ID/prompt/protocol/evidence; không dùng frozen.

| Model | Rubric/12 | Strict | Math | Code | Table | Negative | p50(s) | Fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|gemma3:4b|0.708|0.667|0.500|1.000|0.667|0.667|2.78095|0|
|qwen3.5:4b|0.667|0.667|0.333|0.333|1.000|1.000|4.2848|0|
|ministral-3:3b|0.625|0.583|0.333|0.333|0.833|1.000|7.126200000000001|0|
|qwen2.5:1.5b|0.625|0.500|0.333|0.667|0.667|0.833|0.9294499999999999|0|
|qwen3:1.7b|0.625|0.500|0.667|0.833|0.167|0.833|2.6576500000000003|0|
|granite4:3b|0.583|0.417|0.667|0.333|0.667|0.667|4.1541|0|
|qwen2.5:3b|0.583|0.583|0.667|0.667|0.333|0.667|2.8001|0|
|qwen3:0.6b|0.583|0.500|0.333|1.000|0.667|0.333|0.4879|0|
|llama3.2:3b|0.500|0.417|0.000|0.333|0.667|1.000|2.6395|0|
|qwen3.5:0.8b|0.500|0.417|0.000|1.000|0.667|0.333|2.00855|0|
|phi4-mini:3.8b|0.458|0.333|0.333|0.333|0.833|0.333|1.4039|0|
|qwen2.5-coder:3b|0.458|0.333|0.667|0.333|0.667|0.167|1.5596|0|
|gemma3:1b|0.375|0.250|0.500|0.500|0.333|0.167|0.8562|0|
|qwen2.5:0.5b|0.375|0.333|0.667|0.667|0.000|0.167|1.3934|0|
|granite3.3:2b|0.333|0.250|0.500|0.167|0.333|0.333|2.79505|0|
|qwen2.5-coder:1.5b|0.333|0.167|0.333|0.333|0.500|0.167|2.4638999999999998|0|
|qwen3.5:2b|0.333|0.333|0.333|0.333|0.667|0.000|4.70365|0|
|llama3.2:1b|0.292|0.250|0.000|0.333|0.333|0.500|1.3353000000000002|0|
|granite3.2:2b|0.250|0.083|0.333|0.167|0.333|0.167|2.8966000000000003|0|
|qwen2.5-coder:0.5b|0.208|0.167|0.333|0.333|0.167|0.000|0.309|0|
|phi4-mini-reasoning:3.8b|0.167|0.167|0.000|0.667|0.000|0.000|11.01545|10|
|qwen3:4b|0.000|0.000|0.000|0.000|0.000|0.000|N/A|12|

## Shortlist12

- `qwen3.5:2b`: Mandatory existing application baseline,retained regardless screening score.
- `gemma3:4b`: Highest exploratory overall; code coverage; VLM.
- `qwen3.5:4b`: Table/Negative coverage; VLM; retain RAM retry history.
- `ministral-3:3b`: Distinct general/VLM family and Negative coverage despite slower latency.
- `qwen3:1.7b`: Hybrid reasoning architecture; math/code candidate under common thinking policy.
- `qwen2.5:1.5b`: Quality/latency lightweight candidate.
- `granite4:3b`: Distinct general family with math/table coverage.
- `qwen3:0.6b`: Fast low-resource candidate with code coverage.
- `qwen2.5:3b`: Math/code candidate; compare scale within Qwen2.5 family.
- `qwen2.5-coder:3b`: Explicit coder representative; math coverage and fast inference.
- `phi4-mini:3.8b`: Distinct compact Phi family/table coverage and fast stable finals.
- `qwen3.5:0.8b`: Low-VRAM VLM candidate for paired vision condition; no math strength claimed.

Không chọn winner từ12câu. AI review có sai số/ranh giới partial; human audit chưa có. Bootstrap paired CI theo category được lưu trong summary.json, chỉ thăm dò. Không suy riêng effect size/quant giữa architecture khác nhau. Phi reasoning giữ failure record; không đưa reasoning text vào đáp án.

Bước tiếp: acceptance baseline mới rồi full120 TrackA/B cho cùng shortlist; TrackC cần image-token policy; ablation và freeze/test cuối chưa chạy.
