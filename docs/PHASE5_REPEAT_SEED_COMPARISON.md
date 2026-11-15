# Local LLM repeat-seed stability

Three same-config seeds are compared on the matched 120-question dev split. Prompt, packet, model digest/quantization, protocol (except seed), IDs, and per-question input/evidence/prompt hashes must match. Code hash differences are accepted only in the audited CLI, scoring, and prompt-render files; the exact differences are listed below and in the JSON report.

All scores use AI-only review receipts, not human/expert gold. Runtime failures score 0 in all-eligible metrics; completed-only results are shown separately. Pairwise bootstrap intervals describe this dev sample and do not establish generalization.

## gold_text_verified

### Code hash differences vs seed 42

| Repeat seed | File | Seed 42 SHA-256 | Repeat SHA-256 |
|---:|---|---|---|
| 43 | `src\benchmark\local_cli.py` | `62c5dd120d99bc151945f7f17c0affbbb20447e00e856202058cbe8f9d5cd636` | `7652f916c82dd88442ca110788deae644c932e7befe925e9121fb8a58ee71e92` |
| 43 | `src\benchmark\runner_local.py` | `e98f320e8a99ea38b15909db674f52db0a60768461d4618af383a1ebb6089153` | `e5bdfe91ebe18f65dd6cc1a30ba4bda9796e7b009925be7423a374bd8d0989eb` |
| 43 | `src\benchmark\scoring_local.py` | `c9a813b730ddd1967b288bf7a676493fb067d654482aea9aa484516a9ac5c639` | `17ec0acf559822bbaa646733f378156f5c8f9f708248e45a9dd14d90963c5539` |
| 44 | `src\benchmark\local_cli.py` | `62c5dd120d99bc151945f7f17c0affbbb20447e00e856202058cbe8f9d5cd636` | `7652f916c82dd88442ca110788deae644c932e7befe925e9121fb8a58ee71e92` |
| 44 | `src\benchmark\runner_local.py` | `e98f320e8a99ea38b15909db674f52db0a60768461d4618af383a1ebb6089153` | `e5bdfe91ebe18f65dd6cc1a30ba4bda9796e7b009925be7423a374bd8d0989eb` |
| 44 | `src\benchmark\scoring_local.py` | `c9a813b730ddd1967b288bf7a676493fb067d654482aea9aa484516a9ac5c639` | `17ec0acf559822bbaa646733f378156f5c8f9f708248e45a9dd14d90963c5539` |

| Model | Quant. | Seed 42 | Seed 43 | Seed 44 | Mean | Across-seed SD | Failures 42/43/44 |
|---|---|---:|---:|---:|---:|---:|---:|
| granite4:3b | Q4_K_M | 0.575 | 0.588 | 0.592 | 0.585 | 0.007 | 0/0/0 |
| qwen2.5-coder:3b | Q4_K_M | 0.575 | 0.575 | 0.575 | 0.575 | 0.000 | 0/0/0 |
| qwen2.5:3b | Q4_K_M | 0.588 | 0.658 | 0.658 | 0.635 | 0.033 | 0/0/0 |
| qwen3.5:2b | Q8_0 | 0.579 | 0.621 | 0.604 | 0.601 | 0.017 | 1/0/0 |

### Category scores by seed

| Model | Category | Seed 42 | Seed 43 | Seed 44 |
|---|---|---:|---:|---:|
| granite4:3b | code | 0.481 | 0.481 | 0.481 |
| granite4:3b | math | 0.662 | 0.662 | 0.662 |
| granite4:3b | table | 0.629 | 0.677 | 0.629 |
| granite4:3b | unanswerable | 0.455 | 0.455 | 0.545 |
| qwen2.5-coder:3b | code | 0.667 | 0.667 | 0.667 |
| qwen2.5-coder:3b | math | 0.625 | 0.625 | 0.625 |
| qwen2.5-coder:3b | table | 0.645 | 0.645 | 0.645 |
| qwen2.5-coder:3b | unanswerable | 0.273 | 0.273 | 0.273 |
| qwen2.5:3b | code | 0.704 | 0.759 | 0.796 |
| qwen2.5:3b | math | 0.637 | 0.637 | 0.637 |
| qwen2.5:3b | table | 0.484 | 0.645 | 0.597 |
| qwen2.5:3b | unanswerable | 0.500 | 0.591 | 0.614 |
| qwen3.5:2b | code | 0.611 | 0.593 | 0.593 |
| qwen3.5:2b | math | 0.675 | 0.675 | 0.675 |
| qwen3.5:2b | table | 0.613 | 0.710 | 0.581 |
| qwen3.5:2b | unanswerable | 0.318 | 0.432 | 0.523 |

### Pairwise seed deltas

| Model | Pair | All-eligible Δ | 95% CI | Completed-only Δ | Exact answer repeat |
|---|---|---:|---|---:|---:|
| granite4:3b | 42 vs 43 | 0.013 | [-0.008, 0.037] | 0.013 | 0.842
| granite4:3b | 42 vs 44 | 0.017 | [-0.013, 0.046] | 0.017 | 0.800
| granite4:3b | 43 vs 44 | 0.004 | [-0.025, 0.029] | 0.004 | 0.842
| qwen2.5-coder:3b | 42 vs 43 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5-coder:3b | 42 vs 44 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5-coder:3b | 43 vs 44 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5:3b | 42 vs 43 | 0.071 | [0.025, 0.121] | 0.071 | 0.492
| qwen2.5:3b | 42 vs 44 | 0.071 | [0.029, 0.117] | 0.071 | 0.492
| qwen2.5:3b | 43 vs 44 | 0.000 | [-0.029, 0.029] | 0.000 | 1.000
| qwen3.5:2b | 42 vs 43 | 0.042 | [0.000, 0.083] | 0.042 | 0.630
| qwen3.5:2b | 42 vs 44 | 0.025 | [-0.013, 0.063] | 0.025 | 0.689
| qwen3.5:2b | 43 vs 44 | -0.017 | [-0.062, 0.025] | -0.017 | 0.708

## retrieved_text_frozen

### Code hash differences vs seed 42

| Repeat seed | File | Seed 42 SHA-256 | Repeat SHA-256 |
|---:|---|---|---|
| 43 | `src\benchmark\local_cli.py` | `62c5dd120d99bc151945f7f17c0affbbb20447e00e856202058cbe8f9d5cd636` | `7652f916c82dd88442ca110788deae644c932e7befe925e9121fb8a58ee71e92` |
| 43 | `src\benchmark\runner_local.py` | `e98f320e8a99ea38b15909db674f52db0a60768461d4618af383a1ebb6089153` | `e5bdfe91ebe18f65dd6cc1a30ba4bda9796e7b009925be7423a374bd8d0989eb` |
| 43 | `src\benchmark\scoring_local.py` | `c9a813b730ddd1967b288bf7a676493fb067d654482aea9aa484516a9ac5c639` | `17ec0acf559822bbaa646733f378156f5c8f9f708248e45a9dd14d90963c5539` |
| 44 | `src\benchmark\local_cli.py` | `62c5dd120d99bc151945f7f17c0affbbb20447e00e856202058cbe8f9d5cd636` | `7652f916c82dd88442ca110788deae644c932e7befe925e9121fb8a58ee71e92` |
| 44 | `src\benchmark\runner_local.py` | `e98f320e8a99ea38b15909db674f52db0a60768461d4618af383a1ebb6089153` | `e5bdfe91ebe18f65dd6cc1a30ba4bda9796e7b009925be7423a374bd8d0989eb` |
| 44 | `src\benchmark\scoring_local.py` | `c9a813b730ddd1967b288bf7a676493fb067d654482aea9aa484516a9ac5c639` | `17ec0acf559822bbaa646733f378156f5c8f9f708248e45a9dd14d90963c5539` |

| Model | Quant. | Seed 42 | Seed 43 | Seed 44 | Mean | Across-seed SD | Failures 42/43/44 |
|---|---|---:|---:|---:|---:|---:|---:|
| granite4:3b | Q4_K_M | 0.333 | 0.429 | 0.421 | 0.394 | 0.043 | 26/0/0 |
| qwen2.5-coder:3b | Q4_K_M | 0.342 | 0.342 | 0.342 | 0.342 | 0.000 | 0/0/0 |
| qwen2.5:3b | Q4_K_M | 0.463 | 0.458 | 0.463 | 0.461 | 0.002 | 0/0/0 |
| qwen3.5:2b | Q8_0 | 0.200 | 0.329 | 0.333 | 0.288 | 0.062 | 33/0/0 |

### Category scores by seed

| Model | Category | Seed 42 | Seed 43 | Seed 44 |
|---|---|---:|---:|---:|
| granite4:3b | code | 0.537 | 0.537 | 0.537 |
| granite4:3b | math | 0.375 | 0.375 | 0.375 |
| granite4:3b | table | 0.290 | 0.323 | 0.290 |
| granite4:3b | unanswerable | 0.068 | 0.545 | 0.545 |
| qwen2.5-coder:3b | code | 0.315 | 0.315 | 0.315 |
| qwen2.5-coder:3b | math | 0.400 | 0.400 | 0.400 |
| qwen2.5-coder:3b | table | 0.306 | 0.306 | 0.306 |
| qwen2.5-coder:3b | unanswerable | 0.318 | 0.318 | 0.318 |
| qwen2.5:3b | code | 0.426 | 0.426 | 0.426 |
| qwen2.5:3b | math | 0.438 | 0.438 | 0.438 |
| qwen2.5:3b | table | 0.387 | 0.371 | 0.387 |
| qwen2.5:3b | unanswerable | 0.659 | 0.659 | 0.659 |
| qwen3.5:2b | code | 0.296 | 0.370 | 0.407 |
| qwen3.5:2b | math | 0.312 | 0.300 | 0.300 |
| qwen3.5:2b | table | 0.113 | 0.226 | 0.177 |
| qwen3.5:2b | unanswerable | 0.000 | 0.477 | 0.523 |

### Pairwise seed deltas

| Model | Pair | All-eligible Δ | 95% CI | Completed-only Δ | Exact answer repeat |
|---|---|---:|---|---:|---:|
| granite4:3b | 42 vs 43 | 0.096 | [0.050, 0.150] | 0.000 | 1.000
| granite4:3b | 42 vs 44 | 0.087 | [0.042, 0.138] | 0.000 | 0.979
| granite4:3b | 43 vs 44 | -0.008 | [-0.029, 0.017] | -0.008 | 0.975
| qwen2.5-coder:3b | 42 vs 43 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5-coder:3b | 42 vs 44 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5-coder:3b | 43 vs 44 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5:3b | 42 vs 43 | -0.004 | [-0.013, 0.000] | -0.004 | 0.992
| qwen2.5:3b | 42 vs 44 | 0.000 | [0.000, 0.000] | 0.000 | 1.000
| qwen2.5:3b | 43 vs 44 | 0.004 | [0.000, 0.013] | 0.004 | 0.992
| qwen3.5:2b | 42 vs 43 | 0.129 | [0.075, 0.188] | 0.046 | 0.379
| qwen3.5:2b | 42 vs 44 | 0.133 | [0.079, 0.192] | 0.046 | 0.391
| qwen3.5:2b | 43 vs 44 | 0.004 | [-0.029, 0.042] | 0.004 | 0.742

Review-transfer counts, citation coverage, complete-only values, and failure details are in the JSON report.
