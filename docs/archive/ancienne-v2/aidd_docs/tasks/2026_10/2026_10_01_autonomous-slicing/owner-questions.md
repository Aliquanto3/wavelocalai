# Owner questions: autonomous slicing run (2026-10-01)

Questions this unattended run could not decide under its bounded authority. Each entry names the artifact, the question, the options, the recommended default with its reason, and what it blocks.


## Interval and paired test

Epic: `aidd_docs/backlog/epics/a-score-is-published-with-its-interval-a-difference-with-its-test.md`. The epic's open "percentile or BCa", "which level carries the headline number" and "default comparison family" rows are not repeated here: PRD Methodology 4 and 24 now settle all three (percentile; the development-level score leads; one suite by one compared dimension), and the stories follow the PRD.

### Q1. Does the suite seam become one story both epics declare, and do 100-plus item suites live as data?

- Artifact: `aidd_docs/backlog/stories/a-publication-level-classification-suite-stands-beside-the-hand-written-one.md`, `aidd_docs/backlog/stories/a-publication-level-translation-suite-stands-beside-the-hand-written-one.md` (and transitively `the-threshold-review-is-written-from-the-first-publication-run.md`).
- Question: the suite definition shape, the registry resolving a suite id, and where a publication suite's items are stored belong to `no-use-case-is-silently-absent`, which has no stories yet. Does that seam become one story in that epic which both epics declare in `depends_on`, or does the edge stay epic-wide? And are 100 to 300 drawn items stored as data or as generated Python source like today's `_item(...)` literals?
- Options: (a) one seam story in `no-use-case-is-silently-absent`, declared by both epics, items stored as data; (b) keep the epic-wide `depends_on` and let the first suite story settle storage; (c) this epic builds the seam itself.
- Recommended default: (a). The epic itself says only the seam is on its path and the epic-wide edge overstates it; storing a seeded subset as generated source makes the selection-rule replay a code-generation step.
- Blocks: orders 7 and 8 (both `proposed`), hence order 9.
- Owner answer: (a), the recommended default (2026-10-01).

### Q2. Confirm the tabular-export split, and whether comparison records get their own export table

- Artifact: `aidd_docs/backlog/stories/the-tabular-export-carries-the-interval-and-the-comparison-record.md`.
- Question: `one-download-holds-the-tables-their-licences-and-how-to-cite-them` states a split (export mechanism, schema, column dictionary and release asset there; existence and correctness of the statistical columns here), while this epic records the boundary as open and unowned. That epic's four tables have no place for a comparison or family record. Is the split confirmed, and do comparison and family records become a fifth export table?
- Options: (a) accept the stated split; the bundle epic adds a fifth table for comparison and family records, with the column definitions supplied from this epic; (b) this epic ships its own export of the statistics; (c) the bundle epic owns everything including the statistical columns' definitions.
- Recommended default: (a). It matches the split one sibling has already written down and avoids two exporters over one bundle.
- Blocks: order 6 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

### Q3. Who owns the cloud retry budget and per-item resume at publication scale?

- Artifact: orders 7 and 8 (cloud batches only).
- Question: `DEFAULT_CLOUD_RETRY_MAX_ATTEMPTS = 4` is a batch total and `--resume` re-runs an incomplete batch from item 1; a 100-item Google batch is 200 paced requests. The epic names `a-rate-limited-run-persists-resumes-and-never-re-pays` as the likely owner, but that story is `done` and parented to `any-open-ended-output-carries-two-judges-or-an-honest-flag`, not to the row epic the epic text suggests. Which epic gets a new story for a budget that scales with item count or for per-item resume?
- Options: (a) a new story under `any-open-ended-output-carries-two-judges-or-an-honest-flag`, beside the done one; (b) a new story under `every-published-row-explains-and-reproduces-itself`; (c) a new story under this epic.
- Recommended default: (a). The done story is never reopened (a changed need is a new story), and its parent already owns the retry and resume behaviour.
- Blocks: a cloud batch on either publication suite. Not the one required published batch per suite, which can be local.
- Owner answer: (a), the recommended default (2026-10-01).

### Q4. Is a comparability field absent on both sides a refusal, or an observation naming the absence?

- Artifact: `aidd_docs/backlog/stories/two-configurations-on-the-same-items-receive-a-paired-test-or-a-refusal.md`.
- Question: the committed quality rows are `schema_version` `"7"` and carry no `thinking_policy`, one of the four Methodology 3 constraints. Should a comparison whose two sides both lack it be refused naming the field, or published as an observation naming the absence?
- Options: (a) refuse, applying Methodology 8's "two unknown values never count as a match"; (b) publish as an observation, never as a test, naming the absent field.
- Recommended default: (a). It is the rule the PRD already applies to comparability, and the bundle regeneration (`the-laptop-proves-both-modes-and-republishes-the-bundle-once`) removes the case. Cost: until then, the epic's zero-cost demonstration on the two committed pairs publishes refusals, not p-values.
- Blocks: nothing. Order 2 is written to the default and is `ready`; a different answer changes one Evidence bullet.
- Owner answer: (a), the recommended default (2026-10-01).

### Q5. One epic with two done gates, or two epics?

- Artifact: the epic, and `the-engine-and-the-prompt-variant-are-measured-not-assumed` (which declares `depends_on` on the whole of this epic).
- Question: the inferential half (orders 1, 2, 3, and 6 once unblocked) needs no licence, no public benchmark and no new item; the publication half (orders 4, 5, 7, 8, 9) waits on two spikes and a real run. Does the done gate split?
- Options: (a) one epic, two gates, with the downstream epic depending on gate one; (b) split into two epics; (c) one gate.
- Recommended default: (a), the epic's own recommendation; it unblocks the engine and variant epic without waiting on a licence answer.
- Blocks: no story here; it decides when the downstream epic may start.
- Owner answer: (a), the recommended default (2026-10-01).

## Judge amendment

Epic: `aidd_docs/backlog/epics/any-open-ended-output-carries-two-judges-or-an-honest-flag.md`. New stories are orders 7 to 11; the three API-surface unknowns (Z.ai, DeepSeek, the calibration endpoint) are open spikes under `aidd_docs/backlog/spikes/`, not questions here.

### Q6. What happens to the judged probe story written for the retired Mistral and Google judges?

- Artifact: `aidd_docs/backlog/stories/the-judged-probe-runs-both-paths-in-three-languages.md` (order 6, `ready`), and transitively `aidd_docs/backlog/stories/glm-and-deepseek-are-the-only-judges-and-mistral-and-google-never-judge-again.md` (order 10).
- Question: order 6 is `ready` but cannot produce a row: its acceptance binds Mistral and Google as judges and requires one cloud-subject row judged by the other family alone and flagged single-judge, a path the new pair leaves with no live trigger. Its runner `judge_probe.py` exists and imports both retired judge backends, so retiring them (order 10) and rebinding the probe land together. The epic says order 6's acceptance "is rewritten with it, as a story change". Is it rewritten in place, cancelled and superseded, or left as it is?
- Options: (a) rewrite order 6 in place: two-judge rows under GLM and DeepSeek for every item, the single-judge path proven by order 10's forced collision rather than by a row, one item in ten also calibrated once order 11 lands, its `depends_on` moved to orders 10 and 11, and its README answers extended to the calibration figure and the actual campaign cost; (b) cancel order 6 with the reason recorded and create a new story that `supersedes` it with that acceptance; (c) leave order 6 unchanged and blocked until the owner revisits.
- Recommended default: (a). The epic already states the acceptance is rewritten as a story change, the story is not `done` so no completed work is overwritten, and its runner and ten items are provider-agnostic and survive. Cost: order 6's history no longer shows the single-judge row it once promised; the epic's success check 2 already replaces it with the forced collision.
- Blocks: order 6, order 10 (`proposed`), and through them order 11 and the epic's Success Evidence run.
- Owner answer: (a), the recommended default (2026-10-01).

### Q7. Which endpoint serves the calibration judge, GPT-5.6 Luna?

- Artifact: `aidd_docs/backlog/stories/a-calibration-judge-scores-one-judged-item-in-ten-and-never-moves-a-score.md` (order 11), and its spike `aidd_docs/backlog/spikes/which-endpoint-serves-gpt-5-6-luna-as-a-pinned-calibration-judge-and-on-what-terms.md`.
- Question: Methodology 11 names the pair's providers and requires each to be called through its own direct API, but names only the calibration model, not its provider; its router clause ("where a router is used its provider order is fixed, fallbacks disabled") leaves a router open. Is GPT-5.6 Luna called through its vendor's direct API, or through a router?
- Options: (a) the vendor's direct API (OpenAI), the same rule the pair follows; (b) a router with a fixed provider order, fallbacks disabled and the answering provider on the row; (c) whichever the spike finds cheaper.
- Recommended default: (a). It matches the pair's rule, keeps the calibration judge at one egress destination rather than a router plus an upstream, and makes "the provider that actually answered" true by construction. Cost: one more provider account and key to hold.
- Blocks: order 11 (`proposed`); the spike can investigate the direct API first under this default.
- Owner answer: (a), the recommended default (2026-10-01).

### Q8. How is the 10% calibration subsample drawn, and what is its floor?

- Artifact: `aidd_docs/backlog/stories/a-calibration-judge-scores-one-judged-item-in-ten-and-never-moves-a-score.md` (order 11).
- Question: Methodology 11 sets "a 10% subsample of judged items" to test for a shared bias "in particular on FR and DE items", but not the unit (per batch, per suite, per campaign), the draw, or a floor. A plain 10% of the ten-item probe is one item, which cannot carry an agreement figure nor an EN versus FR/DE split, and a uniform draw over a small suite can contain no FR or DE item at all.
- Options: (a) per suite and batch, a seeded draw stratified by language, rounded up, with at least one item per language present; the n is published beside each figure and an undefined statistic publishes a null with its reason (on the probe this is 3 items of 10, above 10%); (b) a plain seeded 10% rounded up, uniform over the items, accepting that a small suite may calibrate no FR or DE item; (c) a fixed minimum count per language (for example 5) regardless of suite size, at a higher calibration cost.
- Recommended default: (a). It is the smallest rule that can answer the FR/DE question the PRD gives the calibration judge, and it keeps the 10% rate on publication-size suites where stratified rounding is negligible. Cost: a deviation above 10% on small suites, which the PRD's revisable-threshold clause allows but only the owner can accept.
- Blocks: order 11 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

### Q9. What happens when the found catalogue prices put a judged campaign over the ten-dollar estimate?

- Artifact: orders 8, 9 and 11, and the spikes behind them, which each return a list price.
- Question: the PRD accepts "a small judging budget, on the order of ten dollars per campaign at catalogue rates" and states cost is reported, never optimised. Nothing says what a run does if the projected or actual spend exceeds it, for example if the calibration judge's rate is far above the pair's.
- Options: (a) no cap: every judged row reports its judge cost, the first campaign's actual total is compared against the estimate in the results README, and the owner revisits the budget then; (b) a per-campaign spend ceiling that stops issuing paid calls when reached and marks the run partial, through the shipped partial-and-resume machinery; (c) shrink the calibration subsample when its share of the budget passes a set fraction.
- Recommended default: (a). It follows the PRD's "reported, never optimised" rule and the epic's own closing question about actual versus estimated cost; (b) is a budget control the PRD does not ask for, and (c) changes a methodology threshold for cost reasons. Cost: a mispriced campaign is noticed after it is paid for, bounded by one campaign.
- Blocks: nothing today. Answering (b) or (c) adds a story under this epic.
- Owner answer: (a), the recommended default (2026-10-01).

## Size-class families

Epic: `aidd_docs/backlog/epics/every-size-class-spans-two-families-or-says-it-does-not.md`. New stories are orders 1 to 8; which candidate GGUFs exist per class and whether the pinned build loads them is an open spike (`aidd_docs/backlog/spikes/which-candidate-ggufs-exist-per-size-class-and-does-the-pinned-build-load-them.md`), not a question here. The licence policy, the defer-by-default rule for an unsupported architecture and the per-entry thinking control are decided by the epic and are not repeated.

### Q10. Which figure do the four size-class bands read, and where are the edges?

- Artifact: `aidd_docs/backlog/stories/the-composition-check-names-every-size-class-and-refuses-an-unlabelled-single-family-one.md` (order 3), and transitively orders 5 to 8.
- Question: the epic fixes four classes "roughly ~0.5B, ~2B, ~4B and ~8B-and-up by nominal size", and in the same decision bounds them "by the footprint bands the 16 GB no-GPU PC, the 6 GB-VRAM laptop and the 8 GB-VRAM tower separate", while rejecting classing by total parameters alone. At the quants in use the two readings disagree: the three dense Qwen files are 0.60, 1.71 and 2.33 GiB and fit every machine, so machine-derived bands would put the bottom three nominal classes into one, and the order 3 check cannot tell a declared class from a wrong one until one measure is chosen.
- Options: (a) the class is banded on total parameters, with edges at 1B, 3B and 6B (which yields the epic's four nominal classes and places every shipped entry where its name suggests), and bytes on disk is recorded and published beside it as the footprint figure without banding; per-machine fit stays with the machine epic's profiles; (b) the class is banded on bytes on disk, with edges where the machines separate (about 5 GB allocatable laptop VRAM, 8 GB tower VRAM, about 12 GB usable RAM on the 16 GB PC), accepting that the nominal names no longer describe the classes; (c) both: a nominal class banded as (a) plus a separate machine-fit band per entry, checked independently.
- Recommended default: (a). It is the only option that keeps the four classes the epic and the gap brief name, it is checkable from the entry, and the epic itself excludes per-machine fit ("the per-machine decision of whether a given entry runs is not taken here"). Cost: the epic's "bounded in practice by the footprint bands" clause becomes descriptive rather than the measure, which only the owner can accept; edges stay revisable after the first full-roster run.
- Blocks: order 3 (`proposed`), hence orders 5 to 8.
- Owner answer: (a), the recommended default (2026-10-01).

### Q11. Is a model family its vendor lineage or its model line?

- Artifact: `aidd_docs/backlog/stories/every-roster-entry-states-its-family-its-licence-and-its-language-claim.md` (order 1).
- Question: this epic lists the families `KNOWN_FAMILIES` must accept as `gemma`, `granite`, `ministral`, `lfm2` and `phi`, while the judge epic reads Gemma as sharing Google's family ("Google cannot judge a Gemma row") and Ministral as making `mistral` a local subject family. One attribute serves both the composition rule and the judge-independence guard, so it needs one meaning.
- Options: (a) vendor lineage, reusing the existing values: Gemma resolves to `google`, Ministral to `mistral`, and `ibm` (Granite), `liquid` (LFM2) and `microsoft` (Phi) are added; `display_id` keeps the model line visible; (b) model line: `gemma`, `granite`, `ministral`, `lfm2`, `phi`, with a separate vendor mapping for the independence guard; (c) model line for the composition rule and vendor for judging, as two fields.
- Recommended default: (a). It matches the judge epic's reading, keeps one field with one meaning, and needs no second mapping; for the composition rule, two vendors are two families either way. Cost: a published family column reads `google` beside a Gemma model, which the `display_id` column beside it disambiguates.
- Blocks: nothing. Order 1 is written to the default and is `ready`; a different answer changes literal family values before any non-Qwen row is published, which is when changing them is still free.
- Owner answer: (a), the recommended default (2026-10-01).

### Q12. Which candidate models does each size class take, in which order, and at which quant?

- Artifact: orders 5 to 8 (`the-half-billion-class-...`, `the-two-billion-class-...`, `the-four-billion-class-...`, `the-top-class-spans-two-families-with-dense-and-moe-or-says-why-not.md`).
- Question: the epic names the families (Gemma 4 including the 26B-A4B MoE, Granite at 350M and 1B, Ministral, LFM2, Phi) and a stopping rule ("pursued until the rule is satisfied in every class the machines can hold, not pursued as a fixed shopping list"), and the PRD defers "which specific dense and MoE models make the initial roster" as a model-selection decision. Neither names the exact model per class, the order candidates are tried in, or the quant, and quants differ today within the Qwen ladder (`Q8_0` at 0.6B and 1.7B, `Q4_K_M` at 4B, `UD-IQ4_XS` for the MoE). `context_input/model_candidates.md` also lists GPT-OSS 20B, Qwen3-Coder-30B-A3B and Mellum2-12B-A2.5B, which are outside the epic's family list.
- Options: (a) take the spike's per-class shortlist, restricted to the epic's families: Granite 350M and the smallest LFM2 at ~0.5B; Granite 1B and LFM2 at ~2B; Ministral 3B and the Phi mini model at ~4B; Gemma 4 26B-A4B (MoE) and Gemma 4 12B (dense) at the top; any sub-4B MoE the spike finds is taken at its class; candidates tried smallest download first; one passing non-Qwen family per class suffices; each taken at the quant matching the Qwen entry of its class where its publisher ships it, otherwise the nearest one with the difference stated; (b) the same shortlist, but every passing candidate enters rather than stopping at the first second family; (c) (a) plus GPT-OSS 20B and Mellum2 at the top class as further MoE families.
- Recommended default: (a). It is the epic's own stopping rule applied literally (the outcome is the composition, not a count of models), it bounds bench time and disk, and quant matching keeps a family comparison from being read as a quant comparison, the confusion this epic exists to remove. Cost: a class satisfied by its first passing family reports one rival, not the best one; (b) is the option that answers "which small model is best", at several times the bench cost.
- Blocks: orders 5 to 8 (`proposed`), together with the spike.
- Owner answer: (a), the recommended default (2026-10-01).

## Engine and prompt variant

Epic: `aidd_docs/backlog/epics/the-engine-and-the-prompt-variant-are-measured-not-assumed.md`. The epic's four Ollama and compressor unknowns that evidence can settle are open spikes under `aidd_docs/backlog/spikes/`, not questions here. This epic depends on the interval and paired-test epic through its stories orders 1, 2 and 3 only, which is Q5's option (a) taken as the working assumption.

### Q20. Does llama.cpp's own configuration hash enter the fiche's hashed projection in this epic?

- Artifact: `aidd_docs/backlog/stories/every-row-names-the-engine-that-produced-it-and-the-fiche-hashes-it.md` (order 1).
- Question: the epic decides that "the engine's effective configuration carries a content hash over a path-free normalisation, and that hash enters the projection", and its Boundaries name llama.cpp's normalisation (the flag list with the absolute model path replaced by the roster entry reference). The same decision row then hands "whether llama.cpp's own flags should therefore be hashed through a normalised digest" back to the row epic, unanswered. Applied to llama.cpp, the first sentence answers the handed-back question. Which reading holds?
- Options: (a) the engine configuration hash enters the projection for both engines now, llama.cpp's computed over its normalised flag list; the raw `flags` stay outside the projection as evidence; (b) only the comparator's configuration hash enters the projection, llama.cpp's is recorded on the fiche as evidence until the row epic decides; (c) neither enters the projection; both are evidence only.
- Recommended default: (a). It is the epic's own decision applied without exception, and Methodology 8 already lists "the server flag set" as verdict-blocking (`verdict._RUNTIME_BLOCKING_FIELDS` carries `flags`), so hashing the normalised set aligns the hash with the verdict instead of creating a new rule. Cost: an operator thread-count override moves the fiche hash, so a re-run under a different override becomes `not comparable` rather than `reproduced`, which is the M8 reading anyway; and (b) would make the two engines' identities asymmetric.
- Blocks: nothing. Order 1 is written to the default and is `ready`; a different answer changes one acceptance bullet.
- Owner answer: (a), the recommended default (2026-10-01).

### Q21. Which roster model does the "what the defaults cost" side-run use?

- Artifact: `aidd_docs/backlog/stories/what-a-default-ollama-install-costs-is-published-as-its-own-figure.md` (order 11).
- Question: the epic fixes the side-run to "one named roster model" and does not name it. The choice decides what the figure can say: a small dense entry is cheap and fits any machine; the MoE flagship is where Ollama's own offload and context defaults would cost a laptop user the most, but whether the Ollama library carries a matching tag is unverified.
- Options: (a) `qwen3-0.6b-q8` (roster quant `Q8_0`), the machine epic's proving model; (b) the MoE flagship `qwen3.6-35b-a3b-ud-iq4xs`; (c) `qwen3-4b-q4km` (roster quant `Q4_K_M`).
- Recommended default: (a). Cheapest to run under the full runtime protocol, runnable on every reference-machine candidate, and its roster quant is pinned explicitly so any different quant Ollama chooses is readable on the figure. Cost: the figure says nothing about MoE offload defaults, the case a consultant is most likely asked about; (b) can follow as a second side-run if spike `can-a-pinned-ollama-build-serve-the-roster-gguf-under-the-runtime-protocol` finds a matching library tag.
- Blocks: order 11 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

### Q22. Which machine is the campaign's declared reference machine?

- Artifact: `aidd_docs/backlog/stories/the-campaign-answers-whether-each-variant-helps-or-hurts-a-small-model.md` (order 12), and the bounds of spike `which-llmlingua-2-class-compressor-fits-the-reference-machine-and-in-which-placement`.
- Question: the epic runs the full 2 engines x 4 variants campaign "on one declared reference machine" and every claim names it, but never names the machine; its compressor unknown reasons about "a 6 GB laptop", which implies the laptop without stating it.
- Options: (a) the laptop (RTX 3060 Laptop, 6 GB VRAM, about 5.1 GB allocatable, per `context_input/hardware.md`), in its `gpu` mode; (b) the tower (RTX 3050, 8 GB VRAM); (c) the laptop in `cpu_only` mode.
- Recommended default: (a). It is the development machine where every command is agent-executable, the existing bundle and the machine epic's proving runs are taken there, and it is the machine the epic's VRAM-pressure reasoning names. Cost: the tightest VRAM of the GPU machines, so the compressor's placement is most likely forced to CPU or a separate phase.
- Blocks: order 12 (`proposed`); the compressor spike can proceed on the laptop under this default.
- Owner answer: (a), the recommended default (2026-10-01).

### Q23. May the input compressor bring a heavy ML dependency into the project, and how?

- Artifact: `aidd_docs/backlog/stories/the-input-compression-variant-records-its-compressor-as-a-step-of-its-own.md` (order 9).
- Question: an LLMLingua-2-class compressor is a neural token classifier; the reference implementation's package depends on a deep-learning runtime that the project does not carry today. The container image ships no weights and the reproduction path is documented around llama.cpp alone. How may the compressor enter the project?
- Options: (a) an optional, pinned dependency group used only by the `input_compressed` variant, excluded from the default install and the published container, its weights downloaded by revision with a checksum like a roster entry; (b) the compressor runs out of process in its own pinned environment, called by the harness through a narrow interface; (c) a required dependency of the project.
- Recommended default: (a). It keeps the default install and the container unchanged for every reader who does not reproduce the compression cells, and reuses the pin-and-checksum discipline the roster already applies. Cost: a reproduction of the `input_compressed` cells needs one extra documented install step, and the dependency scan must cover the optional group.
- Blocks: order 9 (`proposed`), together with its spike.
- Owner answer: (a), the recommended default (2026-10-01).

### Q24. How are TTFT, tokens and energy measured per variant and per task family?

- Artifact: `aidd_docs/backlog/stories/each-quality-item-records-the-tokens-and-the-first-token-time-its-generation-took.md` (order 10), and order 12.
- Question: the epic's statement reports each variant's effect "per task family, on quality, TTFT, tokens and energy", each difference carrying a paired test. Today a quality row is per item but carries tokens and energy only as batch totals and no TTFT, and the runtime protocol (Methodology 6) measures TTFT and energy on one fixed prompt, not on suite items. No row today could supply a per-item paired test on any of the three.
- Options: (a) quality rows gain per-item engine-reported TTFT (with its `ttft_source`) and per-item tokens in and out, so TTFT and tokens get paired tests over items; energy stays measured per batch, and per-variant energy differences are published as observations; (b) as (a), plus the energy tracker started and stopped around each item so energy is paired too; (c) per-item tokens on quality rows, while TTFT and energy come from the runtime protocol run per variant on a declared representative item per task family, with no paired test on either.
- Recommended default: (a). Paired tests need per-item values, the engine already reports per-generation timings, and per-item energy on items of a few dozen tokens sits below what the tracker can resolve, so (b) would publish noise as a paired result. Cost: per-item TTFT on a quality batch is not the Methodology 6 runtime figure (no warm-up exclusion, no repetitions) and must be labelled as a distinct measurement; no paired energy claim is possible.
- Blocks: order 10 (`proposed`) and through it order 12.
- Owner answer: (a), the recommended default (2026-10-01).

## No use case silently absent

Epic: `aidd_docs/backlog/epics/no-use-case-is-silently-absent.md`. New stories are orders 1 to 10, plus one task (`aidd_docs/backlog/tasks/register-the-closed-harness-candidate-set-and-its-three-row-fields.md`). The epic's two named spikes (tool-calling maturity per model and harness; search-tool selection) are open spikes under `aidd_docs/backlog/spikes/`, not questions here. Q1's recommended default (a) is written as order 1, `a-suite-is-data-resolved-by-its-id-not-an-import-in-the-cli.md`: the epic's own Boundaries already state a suite is "data plus a named scoring rule", so the story stores items as data. Which harnesses a campaign compares, and whether the comparison runs on every agentic model, are not repeated here: the epic defers both to the campaign declaration of `the-engine-and-the-prompt-variant-are-measured-not-assumed`.

### Q30. Is an incomplete coverage record ever published, or only refused until every entry resolves?

- Artifact: `aidd_docs/backlog/stories/every-prd-use-case-carries-a-coverage-state-or-the-record-refuses-to-publish.md` (order 2).
- Question: the epic says a record with a use case missing or stateless "is not a shape the harness can publish". Read strictly, no coverage record is published until the last of the six new suites lands (or is marked out of scope), and until then the pitch overview states the record's absence. Should interim bundles instead publish a partial record?
- Options: (a) strict: the record is refused until every entry resolves, and the refusal output is the interim coverage reading; (b) interim entries are published as `out-of-scope-this-release` with the reason "not yet built" and the owning story, flipped as suites land; (c) add a fourth state such as `planned`.
- Recommended default: (a). It is the epic's own wording, and (b) puts an "out of scope this release" label on use cases the epic intends to ship, which a reader cannot tell from a real scoping decision; (c) widens a three-state set the epic and PRD fix. Cost: the pitch shows no coverage card state until the epic is nearly done.
- Blocks: nothing. Order 2 is written to the default and is `ready`; (b) or (c) changes one acceptance bullet and the pitch epic's rendering.
- Owner answer: (a), the recommended default (2026-10-01).

### Q31. What sandbox posture runs model-generated code?

- Artifact: `aidd_docs/backlog/stories/generated-code-is-scored-by-its-tests-in-a-sandbox-or-not-run-at-all.md` (order 4).
- Question: the epic's Sequence makes "sandbox posture decided" the gate before the code-generation story, and its unknowns table recommends one posture without deciding it. Which posture is adopted?
- Options: (a) container-based, no network, no host mount, wall-clock and memory caps, refusing to run where no container runtime is present, sharing the runtime the published image already uses; (b) a host subprocess under OS-level limits, with no container dependency; (c) a WebAssembly or language-level sandbox per programming language.
- Recommended default: (a), the epic's recommendation. The project already ships a container image, so the runtime is not a new dependency, and refusing rather than falling back is the only posture that never runs untrusted code on the host. Cost: an operator must have a container runtime on each bench machine for this suite, and the no-GPU professional PC may not.
- Blocks: order 4 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

### Q32. Which programming language joins Python in the code-generation suite?

- Artifact: `aidd_docs/backlog/stories/generated-code-is-scored-by-its-tests-in-a-sandbox-or-not-run-at-all.md` (order 4).
- Question: the epic requires "Python plus at least one other language, named on the item and on the row" and names none. Which one?
- Options: (a) JavaScript (Node, its built-in test runner); (b) TypeScript; (c) a compiled language such as Java, C# or Go; (d) more than one.
- Recommended default: (a). It is the most common second language in client codebases, needs no compile step in the sandbox, and its test runner ships with the runtime. Cost: no claim about a typed or compiled language is publishable; (b) or (c) adds a compile step and a build failure mode to the scoring.
- Blocks: order 4 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

### Q33. How is a harness's per-call prompt overhead measured?

- Artifact: `aidd_docs/backlog/tasks/register-the-closed-harness-candidate-set-and-its-three-row-fields.md`, and through it orders 5, 6, 7, 8 and 9.
- Question: Methodology 23 requires every agentic row to report "the tokens the framework adds around the user prompt" but does not define the subtraction; the epic records a recommendation open to contradiction. Which rule is adopted, and are an item's own tool definitions part of the item or of the overhead?
- Options: (a) per call, the token count of what the engine finally received minus the token count of the item's own rendered prompt (including the item's tool definitions as rendered under `direct`), under the tokenizer the row already names; a framework that rewrites rather than wraps the item's prompt is recorded unmeasurable, not zero; (b) the framework's own reported prompt-token count minus `direct`'s for the same item; (c) report the total only and drop the separate field.
- Recommended default: (a), the epic's recommendation. It reads what the engine actually received rather than trusting a framework's self-report, and counting tool definitions as item content keeps `direct`'s overhead from being inflated by the task itself. Cost: it needs the engine-side prompt to be readable per call, which the tool-calling spike checks per framework; (c) contradicts the PRD acceptance criterion.
- Blocks: the harness task (`proposed`), hence orders 5, 6, 7, 8 and 9.
- Owner answer: (a), the recommended default (2026-10-01).

### Q34. Is web research a retrieve-then-answer pipeline, or agentic tool use?

- Artifact: `aidd_docs/backlog/stories/a-web-research-score-recomputes-offline-from-its-archived-search-responses.md` (order 9), and order 10.
- Question: the epic recommends pipeline-first, open to contradiction: the harness issues the search, archives the response, and the model answers over it. The alternative lets the model decide when and what to search through a tool call.
- Options: (a) pipeline-first: web research is independent of the tool-calling spike, sits outside the harness comparison this release, and records harness `direct`; an agentic variant is deferred until the tool-calling spike reports; (b) agentic from the start, sharing order 6's transcript capture and the spike's risk; (c) both, as two scoring rules over one query set.
- Recommended default: (a). It keeps the heaviest suite off the riskiest gate and makes every archived response a function of the query alone, which is what makes offline recompute straightforward. Cost: the suite measures answer writing over search results, not a model's search strategy.
- Blocks: orders 9 and 10 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

## Bundle, licences and citation

Epic: `aidd_docs/backlog/epics/one-download-holds-the-tables-their-licences-and-how-to-cite-them.md`. New stories are orders 1 to 7. Whether model outputs in the rows may be redistributed is an open spike (`aidd_docs/backlog/spikes/may-the-model-outputs-in-the-published-rows-be-redistributed-and-on-what-terms.md`), not a question here. A fifth export table for comparison and family records is Q2's; no story here duplicates it. The `CITATION.cff` author identity is deferred by the epic to the owner at release and is not asked here.

### Q40. Is the Zenodo procedure proven against the Zenodo sandbox or by a real deposit?

- Artifact: `aidd_docs/backlog/stories/the-zenodo-deposit-is-a-written-optional-procedure-proven-once.md` (order 6).
- Question: the epic resolves Zenodo's metadata and licence vocabulary "by performing the deposit once against a real release rather than describing it from memory". A real deposit mints a permanent public DOI, which the PRD makes optional and the epic keeps manual. Is the one proving run a real deposit of the next release, or a deposit on the Zenodo sandbox of that release's archive?
- Options: (a) the sandbox, with the real deposit left to the day a venue asks for a DOI; (b) a real deposit of the next release, so the first release carrying the archive also carries a DOI; (c) write the procedure without performing it.
- Recommended default: (a). It exercises the same form without a permanent public act the PRD calls optional; (c) contradicts the epic's own resolution of the unknown. Cost: the sandbox may differ from production in small ways, so the first real deposit can still need one correction.
- Blocks: order 6 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

### Q41. What does the download give a reader for a drawn item whose text may not be redistributed?

- Artifact: `aidd_docs/backlog/stories/a-drawn-item-reaches-the-download-under-its-own-terms-or-as-a-visible-hole.md` (order 7).
- Question: this epic still writes "the statistics epic's manifest-plus-fetch-script fallback" and a "fetch instruction". The interval epic has since replaced the manifest with a three-rung ladder: on the no-redistribution rung the rows carry `prompt`, `expected_label` and `reference_output` redacted to the per-item content hash, and it names no fetch mechanism. What does the exported row give the reader to obtain the text?
- Options: (a) per item the source, its revision and the stable source key, plus one written instruction per source in the archive README; the content hash proves a fetched item is the scored one; (b) a fetch script shipped in the archive that downloads the source and verifies each item by hash; (c) the source identity and the hash only, no instruction.
- Recommended default: (a). It meets the epic's "visible absence with its source and a fetch instruction" without the repository shipping code that pulls a third party's corpus, which a no-redistribution licence may itself restrict; (c) falls short of the epic's success check 5. Cost: the reader performs the join to the source by hand.
- Blocks: order 7 (`proposed`), together with the two public-benchmark spikes.
- Owner answer: (a), the recommended default (2026-10-01).

### Q42. Who computes the published leader set, given the PRD names the export tooling?

- Artifact: the epic, and `aidd_docs/backlog/stories/the-pitch-opens-on-one-card-per-use-case-read-from-published-rows.md` (which shows a stated absence until a leader set is published).
- Question: the PRD Non-goals say the leader set "is a published derived output, computed from the reference bundle by the export tooling and recomputable by anyone holding that bundle". This epic's export "computes no number the rows do not already carry", and the interval epic records the derivation as unowned. Which epic computes it, and is it a table in the download?
- Options: (a) the interval epic computes the leader set into the bundle as its own records beside the comparison records, and this export flattens them like any other record (which then falls under Q2's table split); (b) a story here derives it in the export as an extra table, which amends this epic's "computes no number" boundary; (c) leave it unowned for this release.
- Recommended default: (a). It keeps the export a pure projection, the epic's "derived, never authoritative" decision, and puts a statistical derivation with the epic that owns the paired tests; it still satisfies the PRD's "recomputable by anyone holding that bundle". Cost: the PRD's literal wording ("by the export tooling") is read loosely, which only the owner can accept.
- Blocks: no story in this epic. It decides whether the pitch's leader-set cards can ever show a model.
- Owner answer: (a), the recommended default (2026-10-01).

### Q43. Do the hand-written item literals inside `src/` also fall under `LICENSE-DATA`?

- Artifact: `aidd_docs/backlog/stories/the-data-is-cc-by-4-0-the-code-stays-mit-and-each-says-so-where-it-lives.md` (order 1).
- Question: the hand-written items live as `_item(...)` literals in `src/wave_local_ai_v2/classification_suite.py` and `translation_suite.py`, files `LICENSE` covers as MIT code. Order 1 covers the items as published (suite-definition snapshots and rows) and leaves the source files as they are. Should `LICENSE-DATA` also claim the literals in `src/`?
- Options: (a) yes: a header notice in each suite module states the item literals are CC-BY 4.0 while the code around them is MIT; (b) no: the literals stay MIT as part of the code, so the items are effectively available under both; (c) wait for Q1's answer and move the items out of `src/` into data first.
- Recommended default: (a). The PRD AC says the suite items carry CC-BY 4.0 while the code stays MIT, and under (b) anyone can take the items under MIT without the attribution CC-BY requires. Cost: two files with mixed terms until Q1 moves items into data.
- Blocks: nothing `ready`. Answering (a) or (c) adds one acceptance line to order 1 or a later story.
- Owner answer: (a), the recommended default (2026-10-01). Consequence: the story gains one acceptance line: each suite module in `src/` that holds hand-written item literals carries a header notice stating the items are CC-BY 4.0 (see `LICENSE-DATA`) while the surrounding code is MIT.

## Quality-scored first three use cases

Epic: `aidd_docs/backlog/epics/quality-scored-comparison-first-three-use-cases.md`. Orders 1, 3 and 4 are `done`; order 2 (`judge-scoring-with-inter-judge-agreement-proves-judged-machinery`) is the epic's only open story and was checked against the amended judge epic (`any-open-ended-output-carries-two-judges-or-an-honest-flag`, PRD Methodology 10 and 11). It was not rewritten: Q50 to Q56 are its mismatches, each logged for the owner. New stories are orders 5 and 6. The chat-template finding in the epic's Progress section is closed by the `done` defect `local-subject-prompts-are-never-chat-templated` and is not asked here. The calibration draw and the judge budget are Q8 and Q9 and are not repeated.

### Q50. How is order 2 brought in line with the amended judge pair?

- Artifact: `aidd_docs/backlog/stories/judge-scoring-with-inter-judge-agreement-proves-judged-machinery.md` (order 2, `ready`).
- Question: its first acceptance bullet names the judges as "two independent cloud judges (e.g. Mistral + Google AI)". Methodology 11 now fixes the pair as Z.ai's GLM and DeepSeek, each through its own direct API, and states that Google and Mistral "are benchmark subjects and are never judges". The judge epic says order 2 "is `ready` and still cannot start" for exactly this reason. Q51 to Q56 list the story's other mismatches; this question decides how all of them are applied: in place, by supersession, or not yet.
- Options: (a) rewrite order 2 in place under the amended methodology, folding in the answers to Q51 to Q56 (the same route Q6 recommends for the judged probe), and keep its subject scope at one local and one cloud subject so the roster-wide rewriting run stays with order 5; (b) cancel order 2 with its reason recorded and create a new story that `supersedes` it; (c) leave order 2 unchanged until the judge epic's orders 8 to 10 are `done`, then revisit.
- Recommended default: (a). Order 2 is not `done`, so no completed work is overwritten; the judge epic already treats it as the rewriting suite's owner and the machinery's first consumer, and Q6 recommends the same in-place route for the sibling story, so the two judged stories stay consistent. Cost: order 2's history no longer shows its Mistral and Google wording, and its slug keeps "proves judged machinery", which Q56 questions.
- Blocks: order 2, and through it orders 5 and 6 (`proposed`) and the epic's done gate.
- Owner answer: (a), the recommended default (2026-10-01).

### Q51. Order 2 is `ready` with no declared predecessor on the judge pair: does it return to `proposed` with `depends_on`?

- Artifact: order 2.
- Question: order 2 carries no `depends_on`. It cannot produce a judged row until the GLM and DeepSeek judges exist and the retired bindings are gone (judge epic orders 8, 9 and 10, all `proposed` and blocked on two spikes and Q6), and its rows will carry the per-call fields of judge epic order 7. Its `ready` status therefore overstates readiness, the condition the readiness rule refuses ("relations are known, and no blocking question remains").
- Options: (a) declare `depends_on` on judge epic orders 7 and 10 (order 10 already depends on 8 and 9) and move order 2 from `ready` to `proposed`, a transition the lifecycle allows, until they are `done`; (b) declare the `depends_on` but keep `ready`, reading the edge as sequencing only; (c) leave the relation epic-wide, as today.
- Recommended default: (a). It makes the blocker visible on the story a delivery agent would pick up, instead of only in the judge epic's prose. Cost: one more `proposed` story in this epic until the judge pair answers a live call.
- Blocks: whether order 2 can be picked up for delivery today; nothing else.
- Owner answer: (a), the recommended default (2026-10-01).

### Q52. Order 2 forbids any judged score without agreement; the PRD keeps a flagged single-judge branch

- Artifact: order 2, second acceptance bullet.
- Question: order 2 says "Every judged result is shown with both judges' scores and their agreement level, never a judged score without it." The PRD AC has two branches: a subject independent of both judge families carries both scores and agreement; a subject sharing a family with one judge carries the other judge's score only, "visibly flagged single-judge". No subject on today's roster collides with `glm` or `deepseek`, so the branch has no live trigger, but the story as written would make a future colliding subject unpublishable rather than flagged.
- Options: (a) restate the bullet as the PRD AC's two branches, adding that on the current roster every rewriting row is a two-judge row; (b) keep the stricter wording, so a colliding subject is excluded from the rewriting suite rather than flagged; (c) drop the bullet and rely on the row contract's `JUDGED_FIELDS` alone.
- Recommended default: (a). It is the PRD's own wording and the judge epic's shipped invariant (the writer refuses a judged row carrying neither an agreement figure nor the flag). Cost: none on the current roster.
- Blocks: nothing beyond Q50.
- Owner answer: (a), the recommended default (2026-10-01).

### Q53. Order 2 is silent on the per-judge-call fields and on judge cost

- Artifact: order 2.
- Question: Methodology 11 and the PRD AC require every judged item's row to name the provider that actually answered, the reasoning effort issued and reasoning tokens apart from output tokens (judge epic order 7), and the judge epic keeps `judge_cost` apart from `cost_total`. Order 2 names none of these. Once order 7 lands, the row contract refuses a judged row missing them, so the rewriting rows inherit them either way; the question is whether order 2 states them.
- Options: (a) cite them in order 2's "Maps to" line and its `depends_on` (Q51) without new acceptance bullets, since the contract enforces them; (b) add one acceptance bullet per field to order 2; (c) leave order 2 silent.
- Recommended default: (a). The contract is the enforcement point and order 7 owns it; repeating its bullets would put the same rule in two stories. Cost: a reader of order 2 alone has to follow the link to see the per-call fields.
- Blocks: nothing beyond Q50.
- Owner answer: (a), the recommended default (2026-10-01).

### Q54. Must the rewriting suite's first published batch carry the calibration judge?

- Artifact: order 2, and `aidd_docs/backlog/stories/a-calibration-judge-scores-one-judged-item-in-ten-and-never-moves-a-score.md` (judge epic order 11, `proposed`).
- Question: Methodology 11 has GPT-5.6 Luna score "a 10% subsample of judged items", and the rewriting suite is the first real suite whose items are judged. Order 2 does not mention calibration, and order 11 is blocked on a spike, Q7 and Q8. Does order 2's `done` wait for the calibration figure on the rewriting batch?
- Options: (a) no: order 2 publishes its rewriting batch under the pair alone, its results README section states that the calibration subsample has not yet run, and order 11's first figure is computed over that batch's judged items once it lands; (b) yes: order 2 declares `depends_on` on order 11 and its batch is published with the calibration figure; (c) calibration is exercised on the judged probe only, and never on a suite batch this release.
- Recommended default: (a). Methodology 11 forbids folding the calibration result into any suite score, so the rewriting score does not depend on it, and making it wait would put a third provider's spike on the critical path of the epic's last use case. Cost: the first rewriting publication carries a stated absence where its calibration figure belongs; (c) contradicts Methodology 11's "judged items".
- Blocks: order 2's dependency set; nothing else.
- Owner answer: (a), the recommended default (2026-10-01).

### Q55. Order 2 does not state its rubric, its contested threshold or the judge prompt's language

- Artifact: order 2.
- Question: the judge epic excludes "the rewriting suite's items and its rubric text" because order 2 owns them, sets the contested default (more than 1 point on a 1-5 rubric) as "configured per suite", and the `no-use-case-is-silently-absent` epic copies that split for its three judged suites. Order 2's acceptance names no rubric, no rubric kind or version, no contested threshold, nothing about contested items being excluded from the headline (PRD AC), and nothing about the judge prompt being issued in the item's own language (Methodology 10). The probe's code says the same: "The rewriting suite owns its own" rubric.
- Options: (a) order 2's rewrite adds its own versioned rubric (1-5 ordinal, so quadratic-weighted kappa with raw agreement beside it, the epic's decision), the shipped default threshold of more than 1 point unless the suite argues otherwise in writing, contested items kept visible and excluded from the headline with their count, and judge prompts in the item's language; (b) the rewriting suite reuses the probe's generic shipped rubric; (c) a separate story under this epic authors the rubric before order 2.
- Recommended default: (a). It is the ownership the judge epic already wrote, and the probe's own source refuses to be a draft of the rewriting rubric. Cost: order 2 grows by four acceptance bullets; it stays one story because rubric and suite are versioned together.
- Blocks: nothing beyond Q50.
- Owner answer: (a), the recommended default (2026-10-01).

### Q56. Does order 2 still prove the judged machinery, or only consume it?

- Artifact: order 2 (title and "So that"), and the epic's Progress section, which says order 2 carries "both the rewriting task suite ... and the two-independent-judge machinery".
- Question: order 2's outcome is "proof the open-ended judging path works before extending it to more use cases". Under the amended judge epic that proof is the judged probe's (judge epic order 6, "exists to drive the machinery end to end"), and the machinery is built by judge epic orders 1 to 11; order 2 is called the machinery's "first real consumer". The two epics now describe order 2 differently.
- Options: (a) order 2's rewrite restates its value as the third use case's quality score (a consultant compares local and cloud rewriting quality under two independent judges), with `depends_on` on the probe, and the epic's Progress text is updated by the owner to match; (b) keep "proves the machinery" as order 2's outcome and treat the probe as a rehearsal; (c) leave both texts as they are.
- Recommended default: (a). It removes a double claim to the same proof, and it is the reading the judge epic's Boundaries already state. Cost: the story's slug no longer describes its outcome; renaming a file is the owner's call.
- Blocks: nothing beyond Q50.
- Owner answer: (a), the recommended default (2026-10-01).

### Q57. Does order 2 have to be born compliant with Methodology 2 to 5, and as a data-defined suite?

- Artifact: order 2.
- Question: the row epic excludes authoring the translation and rewriting suites because "their stories cite criteria 4 and 5 as acceptance and are born compliant". Order 2 cites neither: nothing about at least 20 items, each of EN, FR and DE at 25% or more with per-language n and indicative marks (Methodology 4), per-item provenance (5), suite id, version and prompt-set hash (2), or caps and `thinking_policy` declared by the suite (3), the field the done chat-template defect made required. Separately, `a-suite-is-data-resolved-by-its-id-not-an-import-in-the-cli.md` (`no-use-case-is-silently-absent` order 1, `ready`) makes a suite data resolved by id; a rewriting suite written as `_item(...)` source before it lands would be migrated right after.
- Options: (a) order 2's rewrite cites Methodology 2 to 5 as acceptance and declares `depends_on` on the suite-as-data story, so the rewriting suite is born as data and gate-compliant; (b) as (a) without the suite-as-data dependency, migrating later; (c) a separate story under this epic, mirroring `the-classification-suite-reaches-twenty-items-across-three-languages`, brings the suite to compliance after order 2.
- Recommended default: (a). It is what the row epic already expects, and it avoids authoring the third suite in a shape the next story replaces. Cost: order 2 waits on one more `ready` story in another epic.
- Blocks: nothing beyond Q50.
- Owner answer: (a), the recommended default (2026-10-01).

### Q58. The epic's own Boundaries and Dependencies still name Mistral and Google as judges on the free tier

- Artifact: `aidd_docs/backlog/epics/quality-scored-comparison-first-three-use-cases.md` (Boundaries, Dependencies and Unknowns, Progress).
- Question: the epic includes "two independent cloud judges, e.g. Mistral + Google AI" and lists "Free-tier access to ≥2 independent cloud LLM judges (Mistral, Google AI Studio)" as a dependency "already assumed available". Methodology 11 retires both as judges and the PRD Dependencies now accept a paid judging budget for Z.ai, DeepSeek and the calibration judge's provider. Its Progress section also still describes the chat-template finding as open, though the defect is `done`. This run may not edit an epic's Boundaries or Dependencies.
- Options: (a) the owner amends those two rows and appends a dated Progress note (via `aidd-pm:07-epic`), leaving Success Evidence untouched; (b) leave the epic as history and let the judge epic's text govern; (c) cancel this epic and move order 2 and the new stories under the judge epic.
- Recommended default: (a). An epic that names retired judges invites a delivery agent to wire them back, which is the exact failure Methodology 11 forbids. Cost: one owner edit.
- Blocks: nothing directly.
- Owner answer: (a), the recommended default (2026-10-01).

### Q59. What is the reproduction verdict of a judged score, and which epic owns it?

- Artifact: `aidd_docs/backlog/stories/a-judged-re-run-receives-a-reproduction-verdict-that-separates-the-subject-from-its-judges.md` (order 6, new, `proposed`).
- Question: the epic's Success Evidence asks that a client's engineer "rerun the ... rewriting suites ... get the same quality scores back" and "record ... whether reproduction actually held". Methodology 8 decides quality reproduction on identical per-item labels or scores, with a per-item divergence tolerance for a cloud subject, and says nothing about a judged score: a local subject can reproduce its output byte for byte while either cloud judge scores it differently on the re-run. In code, `verdict.quality_verdict` compares `item_score` when no label exists, and `judge_probe.py` writes `not_comparable` by hand. The row epic owns Methodology 8 but excludes criteria 10 and 11; the judge epic excludes criteria 1 to 9; no story owns this. Related and outside this epic: Methodology 8's cloud-subject branch (per-item divergence tolerance, single-run indicative) has no story in any epic either.
- Options: (a) a two-part verdict under this epic: the subject component compares the subject's per-item outputs (local: identical; cloud: Methodology 8's tolerance), the judged component recomputes scores, agreement, contested set and headline offline from the recorded judge records and must match exactly, and a live re-judge is compared per item under a suite-declared judge tolerance defaulting to the contested threshold (1 point on a 1-5 rubric), naming divergent items and judges; a changed judge model id, judge prompt hash or rubric version makes the pair not comparable naming the field; (b) one verdict on the per-item judged score under the suite's tolerance only, with no subject component; (c) every judged row is published single-run indicative and never reproduced; (d) the row epic owns it as a Methodology 8 amendment.
- Recommended default: (a), owned here. It is the only option that tells a reader whether a non-reproduction came from the model or from a judge, and the offline recompute is the same property Methodology 17 demands of web research. Cost: one more verdict shape in `verdict.py` and a tolerance figure the PRD does not state yet, which only the owner can accept; the Z.ai and DeepSeek spikes' determinism answers are the evidence for whether 1 point is too loose or too tight.
- Blocks: order 6 (`proposed`).
- Owner answer: (a), the recommended default (2026-10-01).

## Result reception log epic

Epic: `aidd_docs/backlog/epics/a-release-is-called-credible-only-by-its-logged-client-sessions.md` (`proposed`, no stories). It owns the PRD acceptance criterion "Given a benchmark result shown to a client or their engineer, the consultant logs in a tracked file whether it was challenged, dismissed, or accepted...", which no epic or story owned before this step. The epic stays `proposed` until the questions marked as blocking slicing are answered.

### Q60. Where does the tracked reception record live, and in what form?

- Artifact: the epic's reception record boundary.
- Question: the PRD says only "a tracked file", and the PRD shadow scan flagged the log as "never named or located". Which path, and is it prose or structured data?
- Options: (a) one append-only structured file (one record per session, for example JSONL or YAML) under `aidd_docs/results/`, beside the result stores it judges; (b) one Markdown file with a table per release under `aidd_docs/`; (c) a file outside the public repo, referenced from it.
- Recommended default: (a). A structured record lets the verdict be recomputed rather than counted by hand, and sitting next to the results makes "which release did this judge" a local lookup. Cost: a schema to maintain.
- Blocks: every story of the epic.
- Owner answer: (a), the recommended default (2026-10-01).

### Q61. May a client organisation be named in the tracked record?

- Artifact: the epic's reception record and its client-identity success check.
- Question: the repo is published (MIT code, CC-BY results), so a tracked file is public. The PRD requires the challenger's role, not the client's identity. Is the client named, pseudonymised, or omitted?
- Options: (a) no client name; role plus an opaque session id only; (b) a pseudonymous client id, with the mapping kept outside the repo; (c) the client named, with their consent.
- Recommended default: (b). It keeps the record confidential while still letting "three sessions" be told apart from "one client seen three times", which (a) cannot. Cost: a private mapping the consultant must keep.
- Blocks: the record's schema (Q60) and the epic's client-identity check.
- Owner answer: (b), the recommended default (2026-10-01).

### Q62. Who decides that a challenge was "resolved by evidence within that session"?

- Artifact: the epic's sustained rule.
- Question: the shadow scan calls the consultant "the weakest possible arbiter for a credibility claim". The PRD defines sustained by evidence but names no arbiter.
- Options: (a) the consultant records the resolution and must name the evidence that resolved it, so it is checkable afterwards; (b) a resolution counts only if the challenger agreed in the session, recorded as such; (c) a second consultant reviews each record before it counts.
- Recommended default: (a). It is the PRD's own definition made auditable and needs nothing from the client. Cost: still self-reported; the epic records that limit as an accepted assumption.
- Blocks: the sustained rule and the verdict.
- Owner answer: (a), the recommended default (2026-10-01).

### Q63. What counts as a session toward the three?

- Artifact: the epic's validation verdict.
- Question: the PRD says "shown to a client or their engineer". Does an internal Wavestone review count, and do repeat showings to the same client count separately?
- Options: (a) only showings to a party outside the consultant's own firm count; repeats with one client count, and the verdict also states the number of distinct clients; (b) only distinct clients count; (c) any showing, internal or external, counts.
- Recommended default: (a). It follows the PRD's wording literally and surfaces the distinct-client count instead of hiding it. Cost: three sessions with one client can validate a release, which (b) would forbid.
- Blocks: the verdict.
- Owner answer: (a), the recommended default (2026-10-01).

### Q64. How does a sustained challenge interact with a release's verdict?

- Artifact: the epic's validation verdict.
- Question: "After at least 3 such logged sessions with no sustained challenge" is ambiguous once a sustained challenge to fiche disclosure, table separation or judge agreement occurs. Does it block that release for good, reset its count, or revoke a verdict already reached?
- Options: (a) it blocks that release's verdict permanently and revokes one already reached; the fix ships in a later release whose count starts at zero; (b) it resets the count within the same release; (c) it only blocks if it happens before the third clean session.
- Recommended default: (a). The PRD scopes the verdict "for that release", and a sustained challenge to one of the three claims means that release's artifact failed on it. Cost: a single bad session can cost a release its verdict.
- Blocks: the verdict.
- Owner answer: (a), the recommended default (2026-10-01).

### Q65. Where does a sustained challenge's follow-up item live?

- Artifact: the epic's follow-up obligation.
- Question: the PRD requires a sustained challenge to be "logged as a follow-up item rather than silently accepted", but not where.
- Options: (a) a backlog item under `aidd_docs/backlog/` (a defect when a claim is shown wrong, a spike when it is merely unresolved), linked from the record; (b) an entry in `aidd_docs/backlog/tech-debt.md`; (c) an open/closed state inside the record itself.
- Recommended default: (a). It puts the follow-up in the flow that already gets worked and gives the owning epic a link to it. Cost: client-session context becomes a backlog item, which must respect Q61.
- Blocks: the follow-up story.
- Owner answer: (a), the recommended default (2026-10-01).

### Q66. Is the verdict computed by a check or written by hand, and where is it published?

- Artifact: the epic's validation verdict.
- Question: a derived verdict needs a small tool or test reading the record; a hand-written one needs none but can drift from the records.
- Options: (a) a check reads the record and states each release's verdict, and the verdict is published in that release's `CHANGELOG.md` entry; (b) the consultant writes the verdict by hand in the record; (c) a check, published in `aidd_docs/results/README.md`.
- Recommended default: (a). Derived from the records it cannot contradict them, and the changelog is where a client already reads "which version produced the numbers". Cost: this epic then ships code and a test, not only a document.
- Blocks: whether the epic has a code story at all.
- Owner answer: (a), the recommended default (2026-10-01).

### Q67. Are showings that happened before the record existed backfilled?

- Artifact: the reception record.
- Question: results may already have been shown to a client (the brief's "first time results are shown" note). Do such showings count?
- Options: (a) backfill only showings that can still name the release, the challenger's role, the evidence offered and the criterion disputed; others are not counted; (b) no backfill, counting starts with the record; (c) backfill everything from memory.
- Recommended default: (a). It keeps every counted record held to the same fields without throwing away a showing that can meet them. Cost: a memory-based record looks like a contemporaneous one unless marked as backfilled.
- Blocks: the first verdict, not the record.
- Owner answer: (a), the recommended default (2026-10-01).

### Q68. Is a product-wide check-in cadence added beyond the per-session log?

- Artifact: the epic, and the PRD Open Question "Whether 'credible artifact' validation ... needs a firmer, product-wide check-in cadence beyond the per-session log" (also the brief's Open Decision on staying unmeasured).
- Question: with no showing in a period, the release stays not validated indefinitely. Is a periodic review added?
- Options: (a) no cadence this release; an unvalidated release simply reads as unvalidated; (b) a review at each release cut that states the count reached; (c) a fixed calendar review.
- Recommended default: (b). It costs nothing new (a release is cut anyway), keeps the count visible, and never validates by elapsed time, which the PRD forbids. Cost: a line per release in the release procedure.
- Blocks: nothing in slicing; it adds at most one acceptance line.
- Owner answer: (b), the recommended default (2026-10-01).

### Q69. When is this epic `done`?

- Artifact: the epic's lifecycle.
- Question: the record and rule can work on one real session, but a validated release depends on client access the project does not control.
- Options: (a) done once the record, rule and verdict work and one real session is logged and read back; (b) done only once a release is actually validated; (c) done once the mechanism works on planted records, before any real session.
- Recommended default: (a). One real session proves the record survives contact with reality; tying `done` to three sessions would leave the epic open on a calendar outside the project. Cost: the epic can close with no release yet validated, which its done note must then say.
- Blocks: the epic's done gate, not its slicing.
- Owner answer: (a), the recommended default (2026-10-01).

## Backlog health pass (read-only)

Read-only review of `aidd_docs/backlog/` (12 epics, 107 stories, 14 spikes, 1 task, 1 defect) after this run's slicing steps. Nothing under `aidd_docs/backlog/` was changed. Checked: frontmatter parses for every artifact; no frontmatter relation path and no backlog path cited in a body is dangling; no relation is stored on both ends and no `depends_on` duplicates a spike's `parents`; story orders are unique within every epic; every `Blocked:` line that cites a Q number cites one that exists here; no `ready` story or task carries a frontmatter `depends_on` chain reaching a `proposed` story, a `proposed` task or an open spike. Two `ready` stories are blocked in prose only and are already logged: `the-judged-probe-runs-both-paths-in-three-languages.md` (Q6) and `judge-scoring-with-inter-judge-agreement-proves-judged-machinery.md` (Q51). The engine and use-case harness split is consistent: `a-campaign-is-declared-as-data-and-an-empty-cell-fails-it.md` adds no harness field and `the-same-tool-calling-items-run-under-each-compared-harness.md` adds the list and the three-harness refusal; only the harness task's wording disagrees (see Mechanical findings).

### Q70. Does the interval epic wire its suite stories to the suite seam story that now exists?

- Artifact: `aidd_docs/backlog/stories/a-suite-is-data-resolved-by-its-id-not-an-import-in-the-cli.md` (`no-use-case-is-silently-absent` order 1, `ready`); interval epic orders 4, 7 and 8; the interval epic's epic-wide `depends_on` on `no-use-case-is-silently-absent`.
- Question: Q1 was asked before the seam story existed; it now implements Q1's default (a). Orders 7 and 8 cite "an owner question" without its number and declare no edge to the seam story. Order 4 (`a-suite-is-certified-to-its-declared-level-and-every-item-names-its-licence-and-source.md`, `ready`) adds the level and per-item licence as literals in `classification_suite.py` and `translation_suite.py`, the same files the seam story turns into data; neither declares the other, so whichever lands second rewrites the first's change.
- Options: (a) if Q1 is answered (a): orders 4, 7 and 8 declare `depends_on` on the seam story, the interval epic's epic-wide `depends_on` on `no-use-case-is-silently-absent` is dropped, and the `Blocked:` lines of 7 and 8 cite Q1 and Q3 by number; (b) only orders 7 and 8 declare the edge, and order 4 lands on literals and is migrated by the seam story; (c) leave relations as they are until Q1 is answered.
- Recommended default: (a). It replaces an epic-wide edge that overstates the coupling with the one story-level edge the work needs, and avoids writing order 4's fields twice. Cost: order 4 waits on one `ready`, unblocked story in another epic.
- Blocks: nothing new; it settles the edges Q1 leaves implicit.
- Owner answer: (a), the recommended default (2026-10-01). Consequence: interval orders 4, 7 and 8 declare `depends_on` on the seam story; the interval epic's epic-wide edge to `no-use-case-is-silently-absent` is dropped; the `Blocked:` lines of 7 and 8 cite Q1 and Q3.

### Q71. Who owns Methodology 8's cloud-subject branch for deterministic batches?

- Artifact: PRD Methodology 8 (per-item divergence tolerance, "single-run indicative") and PRD AC "Given a cloud subject re-run, its quality reproduction verdict is decided per item under the declared divergence tolerance ...; given a cloud subject that cannot be re-run deterministically, its row is marked single-run indicative"; `aidd_docs/backlog/stories/a-judged-re-run-receives-a-reproduction-verdict-that-separates-the-subject-from-its-judges.md` (quality epic order 6, `proposed`).
- Question: the judged re-run story is the only artifact that maps this AC, and only for judged batches; it states "a deterministic quality batch's verdict is unchanged". A cloud subject on the classification or translation suite (Mistral, Google today) therefore has no owner for the per-item tolerance, the diverging-item list or the single-run-indicative mark, and no story adds the suite-declared tolerance field. Q59 noted the gap; it is still open.
- Options: (a) a new story under `every-published-row-explains-and-reproduces-itself` (the Methodology 8 owner) adding the suite-declared per-item tolerance and the cloud-subject verdict to every quality batch, which the judged re-run story's subject component then reuses through `depends_on`; (b) widen the judged re-run story to all quality batches; (c) a new story under `quality-scored-comparison-first-three-use-cases`.
- Recommended default: (a). It keeps one verdict rule for all batches in the epic that owns Methodology 8, and keeps the judged story to its judged component. Cost: a new story under an epic whose existing stories are all `done` (see Q75), and a tolerance value the PRD does not state.
- Blocks: the AC above; quality epic order 6 under option (a).
- Owner answer: (a), the recommended default (2026-10-01).

### Q72. Who owns "every row records whether its prompt left the machine"?

- Artifact: PRD AC "Given no client-provided document or prompt in a suite, no request leaving the machine ever contains one, and every row records whether its prompt left the machine."
- Question: egress is recorded only per surface: judged rows (`judge_egress` in `row_contract.py`, shipped), and the planned web-research and RAG rows. Local subject rows, cloud-subject quality rows and runtime rows carry no egress field, and no epic or story maps this AC.
- Options: (a) a new story under `every-published-row-explains-and-reproduces-itself`: a row-contract field on every row (subject egress: none, or the provider), the writer gate refusing a row without it, the judge and search egress blocks kept as they are; (b) treat the cloud-subject `provider` field as the record and amend nothing; (c) a story under `any-open-ended-output-carries-two-judges-or-an-honest-flag`, which already owns judge egress.
- Recommended default: (a). The AC says "every row", and the row contract is where "every row" is enforced. Cost: one more `SCHEMA_VERSION` bump.
- Blocks: the AC above.
- Owner answer: (a), the recommended default (2026-10-01).

### Q73. Must each new use-case suite publish a MoE and a tiny dense model side by side?

- Artifact: PRD AC "Given the model roster, for each in-scope use case it includes at least one MoE candidate and at least one tiny dense candidate, run over the same items with results shown side by side"; the six suite stories of `no-use-case-is-silently-absent` (orders 3, 4, 5, 6, 8, 9).
- Question: the AC is owned for classification and translation (`tiny-dense-models-compared-alongside-moe.md`, `done`) and rewriting (`the-rewriting-suite-scores-dense-and-moe-side-by-side-under-the-judge-pair.md`). None of the six new suite stories, and not their epic, mentions MoE or dense.
- Options: (a) each new suite story's published evidence requires one MoE and one tiny dense roster entry over the same items, side by side, or a recorded refusal (for example a model the tool-calling spike finds unable to emit tool calls); (b) one closing story under `no-use-case-is-silently-absent` runs the dense and MoE pair across all six suites; (c) the AC is met by roster composition alone.
- Recommended default: (a). It matches the route the first three use cases took and keeps the evidence with the suite that produces it. Cost: two batches per suite instead of one; the MoE flagship is the slowest entry on the laptop.
- Blocks: the AC above; adds one evidence bullet to each of the six stories.
- Owner answer: (a), the recommended default (2026-10-01).

### Q74. Engine order 1 and machine order 1 both change the fiche's hashed projection with no relation between them

- Artifact: `aidd_docs/backlog/stories/every-row-names-the-engine-that-produced-it-and-the-fiche-hashes-it.md` (engine order 1, `ready`) and `aidd_docs/backlog/stories/a-gpu-run-and-a-cpu-only-run-never-share-a-fiche.md` (machine order 1, `ready`).
- Question: both add keys to `hardware._NORMALISED_KEYS`, both keep a legacy projection selected by the citing row's `schema_version`, and both bump the schema. Only `a-campaign-is-declared-as-data-and-an-empty-cell-fails-it.md` depends on both. Built in parallel they produce two independent projection versions over one file.
- Options: (a) `related_to` on `a-gpu-run-and-a-cpu-only-run-never-share-a-fiche.md` (the path that sorts first), and the second to land rebases onto the first's projection version; (b) engine order 1 `depends_on` machine order 1; (c) machine order 1 `depends_on` engine order 1.
- Recommended default: (a). Neither needs the other's fields, and (b) would hold a code-only story behind machine order 0, which needs operator access to the professional PC. Cost: whoever lands second does the rebase.
- Blocks: nothing; it prevents a projection conflict.
- Owner answer: (a), the recommended default (2026-10-01). Consequence: `related_to` on `a-gpu-run-and-a-cpu-only-run-never-share-a-fiche.md`; whichever story lands second rebases onto the first's projection version.

### Q75. Two epics have every story `done` but stay `ready`, and other epics depend on them

- Artifact: `aidd_docs/backlog/epics/every-published-row-explains-and-reproduces-itself.md` (20 of 20 stories `done`; six epics declare `depends_on` on it) and `aidd_docs/backlog/epics/clean-machine-runs-it-and-nothing-reaches-main-unchecked.md` (6 of 6 `done`; two epics depend on it).
- Question: a child status never completes an epic without success evidence, and neither epic records whether its Success Evidence held. Until each is closed or explicitly kept open, every epic-level `depends_on` on it reads as an open blocker.
- Options: (a) the owner checks each epic's Success Evidence and closes it with its done note (via `aidd-pm:07-epic`), with Q71 and Q72 adding new stories under a follow-up home; (b) keep both `ready` and read the epic-level edges as ordering only; (c) keep both open as the home for Q71 and Q72.
- Recommended default: (a). It turns eight epic-level edges into satisfied ones and leaves no ambiguity about whether the row contract is finished. Cost: Q71 and Q72, if answered (a), then need a home: a new story under a `done` epic is a lifecycle question only the owner can settle.
- Blocks: the meaning of eight epic-level `depends_on` edges.
- Owner answer: split, diverging from the recommended default (2026-10-01). `clean-machine-runs-it-and-nothing-reaches-main-unchecked` is closed under option (a) with its done note; `every-published-row-explains-and-reproduces-itself` stays open under option (c) as the home of the Q71 and Q72 stories, since an acceptance criterion it owns is not yet met.

### Q76. Which story waits on the model-output redistribution spike?

- Artifact: `aidd_docs/backlog/spikes/may-the-model-outputs-in-the-published-rows-be-redistributed-and-on-what-terms.md` (open; `parents`: the bundle epic only).
- Question: the spike blocks the bundle epic as a whole, while all five of that epic's `ready` stories can proceed. No story names the release at which its answer must be in.
- Options: (a) keep it epic-level, and state in `each-release-attaches-one-archive-that-needs-no-clone.md`'s scope that the first archive carrying open-ended model output (rewriting, document comparison) waits on the spike; (b) add `each-release-attaches-one-archive-that-needs-no-clone.md` to the spike's `parents`, which moves that story off `ready`; (c) leave it as is.
- Recommended default: (a). Today's rows carry only `predicted_label`, which the licence story already scopes out as a separate part; the risk starts with open-ended output. Cost: one scope line.
- Blocks: nothing `ready` under (a).
- Owner answer: (a), the recommended default (2026-10-01).

### Mechanical findings

- `aidd_docs/backlog/stories/the-tabular-export-carries-the-interval-and-the-comparison-record.md`: the `Blocked:` line says the bundle epic "has no story"; it now has seven. Rewrite it to cite Q2 and `the-published-bundle-reads-as-four-flat-tables-and-their-column-dictionary.md`.
- `aidd_docs/backlog/stories/a-publication-level-classification-suite-stands-beside-the-hand-written-one.md` and `a-publication-level-translation-suite-stands-beside-the-hand-written-one.md`: the `Blocked:` lines cite unnumbered owner questions; name Q1 (suite seam) and Q3 (retry budget).
- This file, Q1: says `no-use-case-is-silently-absent` "has no stories yet"; annotate that its order 1 now implements option (a) (see Q70).
- `aidd_docs/backlog/tasks/register-the-closed-harness-candidate-set-and-its-three-row-fields.md`: Scope Excludes gives "the three-harness cap's declaration" to the engine epic's campaign declaration, but `a-campaign-is-declared-as-data-and-an-empty-cell-fails-it.md` adds no harness field and `the-same-tool-calling-items-run-under-each-compared-harness.md` adds the list and the cap refusal; point the Excludes at the latter.
- `aidd_docs/backlog/tasks/register-the-closed-harness-candidate-set-and-its-three-row-fields.md`: no `order`; add `order: 1` (the only task under its parent).
- `aidd_docs/backlog/epics/the-pitch-runs-from-a-browser-and-only-with-the-key.md`: its three `related_to` entries sit on the end whose path sorts later; move each to `clean-machine-runs-it-and-nothing-reaches-main-unchecked.md`, `every-published-row-explains-and-reproduces-itself.md` and `quality-scored-comparison-first-three-use-cases.md` respectively.
- `aidd_docs/backlog/epics/quality-scored-comparison-first-three-use-cases.md`: a `ready` epic with no `goal`; add `goal: aidd_docs/product/wave-local-ai-v2.md`, as every sibling epic has.
- `aidd_docs/backlog/spikes/google-ai-studio-api-surface-is-confirmed-live.md`: a `done` spike filed under `stories/` with story fields `parent` and `order: 1`; move it to `spikes/`, replace `parent` with `parents`, drop `order`, and update the `depends_on` path in `a-second-cloud-provider-answers-suite-items-as-a-subject.md`.
