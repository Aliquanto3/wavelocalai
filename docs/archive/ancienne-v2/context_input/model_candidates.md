# Model candidates

Scope filter for local models: MoE with <= 4B active parameters (throughput is
memory-bandwidth-bound, active params drive tokens/s) AND <= 20 GB at Q4 (32 GB
RAM minus Windows overhead, with --load-mode none keeping weights resident).
Dense models are included only where a small dense model is the better tool.

## Local — MoE, primary scope

| Model | Total / active | Q4 size | Notes |
|---|---|---|---|
| Qwen3.6-35B-A3B | 35B / 3.1B | 17.7 GB (UD-IQ4_XS) | Validated baseline, ~26 tok/s. See baseline_qwen36.md |
| Gemma 4 26B-A4B | 25.2B / 3.8B | ~16 GB | 128 small experts + 1 shared. 30 layers, hybrid sliding-window (1024) + global attention. 256K ctx, 140+ languages, Apache 2.0. Strongest candidate for translation |
| GPT-OSS 20B | 20B / ~3.6B | ~12 GB | Only sub-8B-active model with a public BenchLM score (42.12). Cheapest to test |
| Qwen3-Coder-30B-A3B | 30B / 3B | ~18 GB | Purpose-built for agentic coding and tool calling |
| Mellum2-12B-A2.5B-Thinking | 12B / 2.5B | ~7 GB | JetBrains, code-focused. Small enough to fit largely in VRAM — different runtime profile from the others, worth having as a contrast point |

## Local — dense, task-specific

Dense models enter the scope only where a 30B MoE is the wrong tool:

| Model | Size | Intended task |
|---|---|---|
| Gemma 4 12B | 12B dense, ~7 GB at Q4 | General baseline. BenchLM 47.21, highest in the 8-16 GB tier |
| A small dense classifier (3-4B class, e.g. Qwen3.5-4B or Ministral 3 3B) | ~2-3 GB | Classification. Loading 16 GB of weights to emit one label is the wrong architecture; a small dense model is faster and usually more accurate |
| An embedding model (separate, e.g. all-MiniLM-L6-v2 or a current MTEB pick) | < 1 GB | RAG retrieval. Not a generative model — do not benchmark it on generative task suites |

## Cloud — dual role

Both used symmetrically, neither is a fallback:

| Provider | Role 1 — benchmark subject | Role 2 — judge |
|---|---|---|
| Mistral (free tier) | Runs the same task suites as local SLMs, giving the on-prem vs cloud comparison point | Judge for open-ended tasks |
| Google AI Studio / Gemini (free tier) | Same | Second judge, different model family |

Two judges from different families is deliberate: it enables reporting
inter-judge agreement, which is what makes judged scores defensible.

## Selection rationale and its limits

The models above were selected from BenchLM, Artificial Analysis and vendor
model cards. An important caveat to carry into the design:

- No public leaderboard slices by ACTIVE parameters. BenchLM slices by VRAM tier,
  Artificial Analysis defines "small" as 4B-40B TOTAL parameters, LMArena has no
  size filter at all.
- Neither Qwen3.6-35B-A3B nor Gemma 4 26B-A4B appears in BenchLM's tables — only
  their dense siblings (27B, 31B) do. The two models at the centre of this project
  are effectively unranked anywhere usable.
- All leaderboard scores are measured at full precision on cloud hardware. This
  project measures Q4 quantized weights with CPU expert offload. Rankings do not
  transfer.

This gap is the project's reason to exist, and it should be stated as such to
clients rather than hidden.

## Deliberately out of scope

Frontier open-weight MoEs (GLM-5.2, Kimi K2.6, DeepSeek-V4, MiniMax-M3) are
multi-GPU or datacenter-class. They do not run on the target hardware and are not
candidates.