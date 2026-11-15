# Local LLM Vision Track - Research Notes

Status: paired Track C dev pilot complete on a frozen 98-question one-image subset, with a matched text-only control. Settings and hashes are recorded below and in [TRACK_C_PAIRED_COMPARISON.md](TRACK_C_PAIRED_COMPARISON.md). Reviews are AI-only, not human/expert gold; this is not the frozen test result. Local image-token accounting remains unverified.

## Paired dev pilot results

| Model | Text control | Vision | Vision − text | Paired 95% bootstrap CI | Wins / ties / losses |
|---|---:|---:|---:|---:|---:|
| qwen3.5:2b (Q8_0) | 0.337 | 0.469 | +0.133 | [+0.041, +0.224] | 31 / 53 / 14 |
| qwen3.5:0.8b (Q8_0) | 0.235 | 0.347 | +0.112 | [+0.020, +0.204] | 30 / 51 / 17 |

The 98 cases are paired on the same question, retrieved text, prompt and model digest/quantization; the vision branch uses one first-ordered retrieved page at 96 DPI. All 196 text-control predictions and 196 vision predictions completed. For qwen3.5:2b, the largest category gain is Table (+0.290, CI [+0.113, +0.484]); Code (+0.093) and Math (+0.038) intervals include zero. The result supports a qwen3.5:2b vision fallback for image-eligible requests as a dev-stage candidate, with held-out confirmation still required.

## Track C requirements from the benchmark plan

- Compare visual and text-only conditions on the same questions and same vision-capable model.
- Use only pages from the frozen retrieval packet; never add a gold-evidence page to the retrieved-vision condition.
- Keep image count, DPI, crop/resize behavior, ordering, prompt, and answer budget fixed across the chosen VLMs.
- Choose the VLM after the full A/B quality results. Current candidates include Gemma 3 4B, Ministral 3 3B, Qwen 3.5 4B, and Qwen 3.5 0.8B; this is not a final selection.

## What the official sources establish

- The [Qwen3.5-4B preprocessor config](https://huggingface.co/Qwen/Qwen3.5-4B/blob/main/preprocessor_config.json) specifies patch size 16, temporal patch size 2, merge size 2, and a Qwen3VL processor. Those settings do not give the actual image-token count for the local Ollama build; do not infer tokens from DPI or page dimensions.
- Google's [Gemma vision guide](https://ai.google.dev/gemma/docs/capabilities/vision) says an image typically costs 256 tokens and Gemma 3 4B+ uses 896x896 with pan-and-scan options. Treat this as a model-family guide, then verify the count reported by the local runtime.
- [Mistral's vision guide](https://docs.mistral.ai/inference/conversations/vision) lists Ministral 3 3B as a vision model and demonstrates image inputs. Its [known-limitations page](https://docs.mistral.ai/resources/known-limitations) says maximum image size and request image count depend on model/context limits; it does not provide the local Ollama token cost.
- The [Ollama issue #17321](https://github.com/ollama/ollama/issues/17321) is a user report of two same-size images being merged as video frames in Ollama v0.32.1 with Qwen-VL models. It is not confirmation for this machine's Ollama version 0.40.16 or the shortlisted model sizes. Treat multi-image handling as an open runtime question.

## Pilot policy applied

1. Track A and B, including retries, score generation, receipt validation and model shortlist, were completed before this pilot.
2. Define a retrieved-page eligibility rule before seeing any Track C answer. Use only actual pages in the frozen retrieval result and preserve the retrieval order and image hashes.
3. Start with one image per request at the existing 96 DPI. One image avoids the reported multi-image merge path while remaining compatible with the plan's fixed image-count rule. Do not overwrite the frozen 120-image packet; create a versioned derived policy/packet if a one-image view is needed.
4. For the paired text control, use exactly the same selected question IDs, text, evidence order, prompt, and output budget as the visual condition; omit only the image. If text must be shortened for vision context, apply that same shortened text to its paired control and record both input hashes.
5. Before scoring C, make a small runtime eligibility probe using an actual retrieved image. Record prompt_eval_count, context fit, RAM, VRAM, model digest, image hash, and any runtime error. Gemma's published 256-token estimate is not a substitute for the local measurement. Never lower the existing context or RAM guards just to force a pass.
6. The eligible paired subset and policy were frozen before scored C answers. Non-vision models remain not_applicable, not zero.

## Remaining checks

- Whether local Ollama 0.40.16 reports image tokens in prompt_eval_count for each shortlisted VLM.
- Whether any chosen model expands one PDF page into multiple crops/patches and how that count is represented.
- Confirm on the frozen 268-question evaluation whether the visual fallback improves the paired score under the same one-image policy; do not tune against that held-out result.
- Local Ollama image-token accounting and crop/patch expansion remain unverified; do not infer image-token cost from DPI or page dimensions.
