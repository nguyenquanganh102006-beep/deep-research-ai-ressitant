# Track C paired comparison: vision vs fixed text control

- Questions: 98 paired cases (code=27, math=40, table=31)
- Same prompt/input hashes: True
- Prompt SHA-256: `36a4ef28b0c7977d3ccb32d3d90e87a553f8e2259af5e7e7fb56743468e22cb6`
- Scores use AI-only review receipts; they are not human/expert gold.

| Model | Scope | Category | n | Track B text | Track C vision | C − B | 95% paired bootstrap CI | C wins / ties / losses | B failures | C failures |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen3.5:2b (Q8_0) | All eligible (failures=0) | all | 98 | 0.337 | 0.469 | 0.133 | [+0.041, +0.224] | 31 / 53 / 14 | 0 | 0 |
| qwen3.5:2b (Q8_0) | Both completed | all | 98 | 0.337 | 0.469 | 0.133 | [+0.041, +0.224] | 31 / 53 / 14 | 0 | 0 |
| qwen3.5:2b (Q8_0) | All eligible (failures=0) | code | 27 | 0.426 | 0.519 | 0.093 | [-0.037, +0.241] | 6 / 18 / 3 | 0 | 0 |
| qwen3.5:2b (Q8_0) | Both completed | code | 27 | 0.426 | 0.519 | 0.093 | [-0.037, +0.241] | 6 / 18 / 3 | 0 | 0 |
| qwen3.5:2b (Q8_0) | All eligible (failures=0) | math | 40 | 0.388 | 0.425 | 0.037 | [-0.100, +0.163] | 12 / 20 / 8 | 0 | 0 |
| qwen3.5:2b (Q8_0) | Both completed | math | 40 | 0.388 | 0.425 | 0.037 | [-0.100, +0.163] | 12 / 20 / 8 | 0 | 0 |
| qwen3.5:2b (Q8_0) | All eligible (failures=0) | table | 31 | 0.194 | 0.484 | 0.290 | [+0.113, +0.484] | 13 / 15 / 3 | 0 | 0 |
| qwen3.5:2b (Q8_0) | Both completed | table | 31 | 0.194 | 0.484 | 0.290 | [+0.113, +0.484] | 13 / 15 / 3 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | All eligible (failures=0) | all | 98 | 0.235 | 0.347 | 0.112 | [+0.020, +0.204] | 30 / 51 / 17 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | Both completed | all | 98 | 0.235 | 0.347 | 0.112 | [+0.020, +0.204] | 30 / 51 / 17 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | All eligible (failures=0) | code | 27 | 0.296 | 0.315 | 0.019 | [-0.167, +0.185] | 9 / 11 / 7 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | Both completed | code | 27 | 0.296 | 0.315 | 0.019 | [-0.167, +0.185] | 9 / 11 / 7 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | All eligible (failures=0) | math | 40 | 0.212 | 0.362 | 0.150 | [+0.013, +0.287] | 13 / 21 / 6 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | Both completed | math | 40 | 0.212 | 0.362 | 0.150 | [+0.013, +0.287] | 13 / 21 / 6 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | All eligible (failures=0) | table | 31 | 0.210 | 0.355 | 0.145 | [+0.000, +0.306] | 8 / 19 / 4 | 0 | 0 |
| qwen3.5:0.8b (Q8_0) | Both completed | table | 31 | 0.210 | 0.355 | 0.145 | [+0.000, +0.306] | 8 / 19 / 4 | 0 | 0 |

## qwen3.5:2b examples

C wins (up to five): code-0039 (0.5→1.0), code-0042 (0.0→1.0), code-0060 (0.0→1.0), code-0093 (0.5→1.0), code-0096 (0.5→1.0)
C losses (up to five): code-0040 (0.5→0.0), code-0059 (0.5→0.0), code-0097 (0.5→0.0), math-0062 (0.5→0.0), math-0064 (0.5→0.0)

## qwen3.5:0.8b examples

C wins (up to five): code-0038 (0.0→0.5), code-0040 (0.0→0.5), code-0042 (0.0→0.5), code-0045 (0.5→1.0), code-0060 (0.0→0.5)
C losses (up to five): code-0041 (1.0→0.0), code-0044 (0.5→0.0), code-0058 (0.5→0.0), code-0059 (0.5→0.0), code-0064 (0.5→0.0)

## Reproducibility

- Vision packet SHA-256: `2abb83a00264f4ed0b8fce503705e6c7616d235663c1486ef72cefc3aaa6cd6c`
- Text control packet SHA-256: `769911083705efeafded7fdec7622c5de64a27a5313670cca46911ae0efb4af1`
- Track C prediction history SHA-256: `c1ce8e3bc4702619a7e75bfc9ec97b70d38ecf28a2b669fe6206c8d34697f1ee`
- Track B prediction history SHA-256: `3ae9b45d72730afee55c7fa833b0be823eb5ce2ef4c32cc6a6f5170a00b5107c`
- Track C reviews SHA-256: `bf6dbc073215f5da3b7efe2c85fb8350101b456f21a986c3fddb8cd96ed65b22`
- Track B reviews SHA-256: `0c03a5a06e27a05f0704e507d1741a2d25165d53ab532a011be838d65b199269`
- Track C run commit: `f2b5749acddcf9424a720c467b68cd08a7fe26e4`
- Track B run commit: `f2b5749acddcf9424a720c467b68cd08a7fe26e4`
