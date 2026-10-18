# Brief — gap between wave_local_ai_v2 and the publication goal

> Translated from the owner's French gap-analysis notes, with corrections from the owner's decisions taken 2026-09-06 (see inline amendments and the "Decisions taken 2026-09-06" section below). Kept as source material for AIDD framing, not a spec.

## Context
This repository must serve as the basis for a series of publications (blog/Wavestone article first; arXiv optional; JOSS later-optional) on running SLMs on personal and professional PCs. The audience is changing: in addition to the PRD's client-side engineer, there is now an academic reviewer. Whatever the PRD does not cover must be added as AIDD epics and stories, not implemented right away.

Do not code anything in this session. Read the existing PRD, epics, and stories, then produce with the aidd-pm plugin:
1. a gap-by-gap diagnosis (what already exists, what is missing, which existing epic carries the seam),
2. the new epics and stories, with their dependencies on current epics, and the existing stories to amend or remove,
3. the list of decisions for me to make before starting.
Ask questions before drafting if a point is ambiguous.

## Target ambition
Machines: three configurations that become first-class dimensions of the benchmark. All three are available now.
- Tower: Ryzen 5 7600, 32 GB DDR5-6000, RTX 3050 8 GB
- Laptop: Ryzen 7 5800H, 32 GB DDR4-3200, RTX 3060 Laptop 6 GB (~5.1 GB allocatable) — current dev machine
- Professional PC: 16 GB RAM, no GPU

Tasks: classification, translation, typo correction, rewriting, RAG answering, code generation, agentic planning and tool calling, web search. Languages EN/FR/DE, plus programming languages.
Metrics: quality, tokens/s, TTFT, tokens consumed, duration, energy, carbon, memory — already largely in place.
New comparison dimensions: inference engine, agentic harness, prompt variant.

## Identified gaps

### 1. Multi-machine
The hardware sheet exists and is hashed, but no story runs the same suite across N machines, and launch flags are roster-driven per model, not per (model × machine) pair. Need: a run profile per pair, with a declared minimum threshold that refuses the run (already planned by the PRD) rather than degrading it. The professional PC without a GPU is the most important case for the publication: it is nearly absent from the literature.

### 2. Single-family roster
Four Qwen models. For a publication, at least two families are needed per size class: Gemma 4 (including 26B-A4B), Granite (350M for the professional PC), Ministral, LFM2, Phi. The versioned roster exists; what is missing is the content and the composition rule (dense + MoE, ≥ 2 families per size class). Direct consequence on gap 9: Google and Mistral can no longer be judges.

### 3. Suite size
20 items per suite: one item is worth 5 precision points, no confidence interval is possible. Publication target: 100 to 200 items per suite. Suites grow via subsets of public benchmarks with the contamination marking already planned — not through mass hand-authoring. The threshold of 20 remains a configured constant; a second "publication" tier is needed.

### 4. Engine and prompt variant absent
No mention of Ollama, LangGraph, smolagents, prompt compression, or Caveman in aidd_docs or src. The harness calls llama-server's POST /completion directly. Need two row dimensions:
- `engine`: llama.cpp (reference) and Ollama, with build and default config recorded;
- `prompt_variant`: baseline, output compression (Caveman-style), grammar-constrained output format (GBNF/DSL), input compression (LLMLingua-2).
Limit to 2 engines × 3 or 4 variants to contain the number of runs. Research question to document in the epic: does prompt compression help or hurt an SLM, in quality and TTFT, given that on Claude Code JetBrains measured only an 8.5% saving with no quality loss.

### 5. Agentic suites undefined
The PRD lists planning and tool calling but no suite exists. Tool calling must not be scored by LLM judges: deterministic scoring (right tool, right arguments, number of calls, task success), BFCL-style. Also plan for the harness as a dimension (LangGraph, smolagents, direct call), and measure tokens, duration, and energy per complete agentic task, not per generation.

### 6. ~~CPU energy estimation~~ — dropped, out of scope
On Windows, the CPU channel remains `estimated_tdp`, with a possible error of a factor of 2-3: a weak point for a reviewer. **2026-09-06 decision: the `measured_wall` channel (wattmeter at the outlet) is out of scope. This gap is dropped.** Keep the honest, documented limitation that CPU energy is estimated, not measured.

### 7. Inferential statistics
The 10% reproduction verdict and the median over N=5 are not enough to publish. Add bootstrap confidence intervals on quality scores, and a paired test (Wilcoxon) between prompt variants, engines, and models on the same items.

### 8. Data publication
Suite items under an explicit license, reference bundle deposited on Zenodo with a DOI on each release tag, and a tabular export of results usable outside the repository. **2026-09-06 decision: code stays MIT; suite items and the reference bundle carry CC-BY 4.0.**

### 9. Judges: replace the Mistral + Google pair
The epic `any-open-ended-output-carries-two-judges-or-an-honest-flag` plans Google AI Studio as a second provider and judge, and Mistral as a judge from another family. With the roster from gap 2, the per-family independence rule disqualifies Google as judge for Gemma 4 rows and Mistral as judge for Ministral rows. Decision:
- Judge pair: GLM-5.3-Flash via the direct Z.ai API, and DeepSeek V4-Flash via the direct DeepSeek API. Both families are independent of every local subject in the target roster. Estimated cost for the whole campaign: on the order of $10 at catalog rates ($0.15/$0.50 and $0.14/$0.28 per million tokens); judge calls do not multiply per machine since quality is machine-independent. **2026-09-06: this ~$10 paid budget is confirmed.**
- Mistral and Google remain cloud subjects only, never judges again. The story `google-ai-studio-api-surface-is-confirmed-live` needs to be re-aimed: the spike ("API confirmed live, dated model id, seed or temperature 0") must be redone for Z.ai and DeepSeek, and Google becomes an optional subject.
- Calibration judge: GPT-5.6 Luna on a 10% subsample of judged items, to check that two judges of the same geographic origin do not introduce a common bias on FR/DE items. Result published as an agreement figure, not folded into the score.
- Row constraints for every judge call, in addition to what the epic already plans: real provider pinned (no OpenRouter fallback routing; if OpenRouter is used, `provider.order` fixed and `allow_fallbacks: false`, and the provider written into the row), `reasoning_effort` fixed at minimum or disabled and recorded, judge prompt + rubric placed as a stable prefix to benefit from input caching, reasoning tokens counted separately.
- Free-tier survival (retry, partial resume) stays in scope: rate limits exist on paid tiers too.
- README: one sentence explaining that only the repo's suite items leave the machine, sent to named providers, per the PRD's non-goal.

## Decisions already taken (challenge if you see a problem)
- Priority order: 1, 2, 3, and 9 first (they gate every published run), then 7, then 4, then 5; 8 continuous. (Gap 6 removed from the order — it is dropped.)
- Each new dimension is a row field and a suite or roster entry, never a fork of the harness.
- The "no cost optimization" non-goal stays; we add dimensions, not recommendations. A small paid API budget is accepted for judges.
- The Claude Code / AIDD lessons-learned (REX) is not part of this repository.
- Budget_Tags stays in its own repository.

## Decisions taken 2026-09-06
- Gap 3: suites grow via public-benchmark subsets (contamination-marked), not mass hand-authoring.
- Gap 6: `measured_wall` / wattmeter channel is out of scope — dropped. Keep the honest estimated-CPU-energy limitation documented.
- Gap 8: code stays MIT; suite items and the reference bundle gain CC-BY 4.0.
- Gap 9: judge pair is Z.ai GLM-5.3-Flash + DeepSeek V4-Flash via direct APIs; paid budget of ~$10 confirmed; GPT-5.6 Luna calibration judge on a 10% subsample published as an agreement figure. Google and Mistral become subjects only, never judges again.
- Venue: blog/Wavestone article first, arXiv optional, JOSS later-optional.
- All three machines (tower, laptop, professional PC) are available now.
