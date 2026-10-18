---
objective: "Give consultants defensible, hardware-bound evidence for on-prem vs cloud LLM deployment decisions."
revision: current
---

# Product Brief: wave_local_ai_v2

A reproducible benchmark bench that runs small language models locally via llama.cpp and cloud LLM APIs against identical task suites, producing separate quality and runtime scorecards a consultant can defend and a client can read. v2 is a from-scratch rewrite of a working v1 (Streamlit + Ollama, 118 tests), replacing the stack (llama.cpp, uv, FastAPI + React) while carrying forward the validated model-registry, Green IT, and LLM-as-judge patterns.

## Opportunity

Public leaderboards score full-precision weights on cloud hardware; none publish what a quantized MoE does on a consumer machine with CPU expert offload. The two models most relevant to this hardware class (Qwen3.6-35B-A3B, Gemma 4 26B-A4B) are unranked anywhere usable. Without that data, consultants advising on-prem vs cloud deployments argue from anecdote — a credibility gap that costs them the argument against incumbent cloud vendors, and costs clients a defensible basis for a real infrastructure decision. Now is the moment because the model class (MoE, ≤4B active) has only recently become viable on consumer hardware, so no existing benchmark corpus covers it.

## Audience and Context

- **Consultant (primary, first-party):** runs the benchmarks and needs the numbers to hold up under a client's technical scrutiny.
- **Client-side developers:** read the repo itself — engineering quality (test coverage, reproducibility, pinned deps) is part of the evidence.
- **Client decision makers:** see only the front end during a pitch; they judge the comparison, not the code.

All three are evidence-consumers of the same underlying data at different resolutions — this shapes what "credible" has to mean at each layer, not three separate products.

## Product Bet

If runtime numbers are always hardware-fiche-bound, quality numbers are always separated from runtime, and judged scores always carry inter-judge agreement, then the results are defensible enough to survive a client's or their engineer's challenge — which anecdote-based comparisons cannot. That defensibility, not any single benchmark number, is the product.

## Evidence and Assumptions

| Claim | Status | Basis or next check |
| --- | --- | --- |
| Neither flagship local candidate appears in BenchLM/Artificial Analysis/LMArena at the active-parameter grain used here | Evidence | Selection rationale in `context_input/model_candidates.md`; a genuine leaderboard gap |
| Quantized Q4 CPU-offload performance does not track full-precision cloud-hardware leaderboard rank | Assumption | Stated as the project's premise; the benchmark itself is the first check |
| CodeCarbon TDP-fallback energy estimates on Windows are accurate enough to be client-facing when labeled | Assumption | Mitigated by mandatory `energy_method` labelling; not fully resolved |
| Success is a credible, presentable artifact — not contingent on winning a specific deal | Decision | User, this session |
| v1's model-registry pattern, Green IT config, and LLM-as-judge approach are worth reusing wholesale | Evidence | v1 shipped with 118 tests / 86.5% coverage; carried forward by design |
| Consultants currently have no defensible alternative and are actually blocked by this, not merely inconvenienced | Assumption | Framed from the requester's own consulting practice; not independently corroborated with a second consultant or client |

## Boundaries

- Addresses: local SLM (MoE, ≤4B active, ≤20GB@Q4) vs cloud API comparison, on deterministic and LLM-judged task suites, with hardware-bound runtime and reproducible quality kept in separate tables.
- Leaves out: fine-tuning, model training, multi-GPU/datacenter models, production multi-tenant serving, mobile deployment, and any deal-outcome tracking.

## Success

The bench is credible evidence infrastructure: results a client's engineer can independently reproduce, hold up under scrutiny of methodology (fiche, separation of tables, judge agreement), and stand in for anecdote in a real conversation — whether or not any specific engagement is currently running. No earned-value metric is tracked; success is qualitative defensibility, confirmed by use rather than by a number.

## Validation and Feedback

Next validation targets the riskiest assumption — that this project's premise (quantization + CPU offload materially changes ranking) actually holds: ship Increment 1 (single-model, single-prompt runtime harness) and check whether the resulting numbers diverge meaningfully from the full-precision leaderboard baseline. If they don't diverge, the "gap" motivating the whole project is much thinner than framed.

Post-use signal: the first time results are shown to a client or their engineer, note what they challenge or dismiss — that's fed back into which claims move from "assumption" to "evidence" or get cut, and can change which task suites or metrics are prioritized in later work.

## Open Decisions

- Whether "credible artifact" success can stay unmeasured indefinitely, or needs a check-in point to convert to a harder signal.
- Whether the Windows/NVML energy-estimate caveat needs client-facing disclosure language decided now, or can wait.
- How many task suites ship in the first pass. Nine families is likely too wide for the earliest increments; narrowing to classification, translation, and rewriting first, then widening, is the safer path — not yet decided.
