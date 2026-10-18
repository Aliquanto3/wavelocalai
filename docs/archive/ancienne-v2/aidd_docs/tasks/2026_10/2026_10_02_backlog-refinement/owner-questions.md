# Owner questions: backlog refinement run (2026-10-02)

Questions this unattended run could not decide under its bounded authority. Each entry names the artifact, the question, the options, the recommended default with its reason, and what it blocks. Numbering starts at Q100 to stay clear of `aidd_docs/tasks/2026_10/2026_10_01_autonomous-slicing/owner-questions.md`.

## Credible client sessions

Epic: `aidd_docs/backlog/epics/a-release-is-called-credible-only-by-its-logged-client-sessions.md` (`proposed`). Sliced in this run into orders 1 to 4 under the owner answers Q60 to Q69 of 2026-10-01; those are not repeated here.

### Q100. Does a dismissed session count toward a release's three?

- Artifact: `aidd_docs/backlog/stories/each-release-reads-its-credibility-verdict-from-its-records-in-its-changelog-entry.md` (order 3).
- Question: the PRD logs each session as "challenged, dismissed, or accepted" and validates a release after "at least 3 such logged sessions with no sustained challenge to fiche disclosure, table separation, or judge agreement". A dismissal carries no challenge, so read literally it counts toward the three, although a client who waved the result away has not found it credible. Which reading holds?
- Options: (a) the PRD's literal reading: a dismissed session with no sustained challenge to the three claims qualifies, and the verdict states how many of the counted sessions were dismissals; (b) a dismissal never qualifies: it is recorded and shown, but only `accepted` and `challenged` sessions count; (c) a dismissal must name its reason, and one whose reason bears on one of the three claims is treated as a sustained challenge to it.
- Recommended default: (a). It is the PRD's own text, and stating the dismissal count beside the verdict keeps a release validated mostly by dismissals visible rather than hidden. Cost: three dismissals could validate a release; (b) and (c) change the rule the PRD states, which only the owner can do.
- Blocks: order 3, and order 4 through its `depends_on`. Order 3 is written to the default and stays `proposed` until the answer; (b) or (c) changes one acceptance bullet and one test there, and (c) also adds a dismissal-reason field to order 1's record format.
- Owner answer: (a), the recommended default (2026-10-03).

### Q101. Does the epic move to `ready` now that it has stories?

- Artifact: the epic (`status: proposed`).
- Question: the epic was left `proposed` "until the owner moves it to ready" (commit `20eaa1f`). This run sliced it into four stories; an epic status change is the owner's. Is it moved to `ready`?
- Options: (a) move it to `ready`: its decisions are settled (Q60 to Q69) and its stories are written; (b) keep it `proposed` until order 1 is delivered; (c) keep it `proposed` until a real client session is in sight.
- Recommended default: (a). Nothing in it is undecided, and order 4 already carries the dependency on a real session. Cost: none beyond the edit.
- Blocks: nothing in delivery; a story may be `ready` under a `proposed` epic, but a delivery run picking it should know the owner has not accepted the epic yet.
- Owner answer: (a), the recommended default (2026-10-03).

## Judge providers

Spikes: `aidd_docs/backlog/spikes/is-deepseek-callable-as-a-pinned-judge-and-on-what-data-terms.md`, `aidd_docs/backlog/spikes/is-z-ai-glm-callable-as-a-pinned-judge-and-on-what-data-terms.md`, `aidd_docs/backlog/spikes/which-endpoint-serves-gpt-5-6-luna-as-a-pinned-calibration-judge-and-on-what-terms.md`. All three stay `blocked`: their Bounds require captured live calls, which this run may not make. Desk research found the same gap in all three, asked once here.

### Q102. How does Methodology 12 pin a judge whose provider publishes no dated model id?

- Artifact: PRD Methodology 12 ("A cloud row records the provider's dated model id, never a floating alias, and the API version; a run refuses to start when that id is absent from the provider's live model list"); `aidd_docs/backlog/stories/a-glm-judge-answers-through-z-ai-under-the-pinning-discipline.md` (order 8), `aidd_docs/backlog/stories/a-deepseek-judge-answers-through-deepseek-under-the-pinning-discipline.md` (order 9), `aidd_docs/backlog/stories/a-calibration-judge-scores-one-judged-item-in-ten-and-never-moves-a-score.md` (order 11).
- Question: none of the three judge providers documents a dated id for the candidate model. DeepSeek lists only names it repoints in place (`deepseek-v4-pro` received new weights on 2026-08-13 with "Model names remain unchanged"). Z.ai publishes release ids (`glm-5.2`) with no snapshot policy and documents no model-list endpoint at all. OpenAI lists `gpt-5.6-luna` as the model's only snapshot, undated. Read literally, Methodology 12 makes all three a no-go. The Google subject already runs on a release id plus the catalog's read-only `version` string (`aidd_docs/memory/external/google-ai-studio-api.md`), which is the closest precedent. How is Methodology 12 read for a judge?
- Options: (a) extend the Google precedent to judges: pin the provider's release or snapshot id; the pre-flight reads the live model list where one exists, and where none exists sends a one-token probe to the pinned id, recorded on the row as a probe; every row records each build marker the provider returns (listing `version`, `name` or `created`, response `system_fingerprint`), and a run refuses to start when a recorded marker differs from the pinned one; Methodology 12's text is amended to say so; (b) literal reading: every provider without a dated id is a no-go, the judge pair and the calibration judge are reopened, and new spikes look for families that publish dated ids; (c) decide per provider after the live calls, keeping the literal rule as the default.
- Recommended default: (a). It is the reading the project already applies to its Google subject, it keeps the pair and the calibration model the PRD names, and the live calls the spikes list still capture whatever marker each provider actually returns. Cost: a silent weight change under an unchanged name and marker (DeepSeek's 2026-08-13 update is one) is not detected; judged scores are then reproducible only within a dated window, and the inter-judge agreement and the calibration figure are the only drift signals. Only the owner can amend PRD text.
- Blocks: orders 8, 9 and 11 of `any-open-ended-output-carries-two-judges-or-an-honest-flag`, and through orders 8 and 9 every story that needs a judged score (order 10, the judged probe, the rewriting suite, document comparison, RAG, web research, and the judged re-run verdict).
- Owner answer: (a), the recommended default (2026-10-03).

### Q103. Is DeepSeek's training opt-out requested before the first paid call?

- Artifact: `aidd_docs/backlog/stories/a-deepseek-judge-answers-through-deepseek-under-the-pinning-discipline.md` (its egress acceptance bullet), and the results README's egress statement.
- Question: DeepSeek's Privacy Policy (last updated 2026-02-10) lets it use API inputs for training unless the user opts out by email to privacy@deepseek.com; inputs are processed and stored in the PRC with no fixed retention. This is compatible with the PRD egress non-goal (only the repo's own suite items and outputs derived from them leave the machine), but the suite items would then risk entering a training set. Is the opt-out requested?
- Options: (a) request it from the account owner's address before the first paid call, keep the reply, and state the opt-out and its date in the README; (b) do not opt out, and state in the README that suite items and local outputs sent to DeepSeek may be used for training; (c) send the request, and state in the README that it was sent and whether DeepSeek confirmed it.
- Recommended default: (c). One email lowers the contamination risk for the publication suites, and the policy promises no confirmation, so the README claims only what was sent and received. Cost: one owner email.
- Blocks: the wording of order 9's egress statement only, not its code.
- Owner answer: (c), the recommended default (2026-10-03).

### Q104. Does the calibration judge stay GPT-5.6 Luna now that GPT-6 Luna exists?

- Artifact: PRD Methodology 11 (names GPT-5.6 Luna) and `aidd_docs/backlog/stories/a-calibration-judge-scores-one-judged-item-in-ten-and-never-moves-a-score.md` (order 11).
- Question: OpenAI released `gpt-6-luna` on 2026-09-22 at about half the price of `gpt-5.6-luna` ($0.10 / $0.50 against $0.20 / $1.20 per 1M input / output tokens). GPT-5.6 Luna is not deprecated, and neither has a dated id. Which model calibrates?
- Options: (a) keep `gpt-5.6-luna`, as the PRD names it; (b) switch to `gpt-6-luna` and amend Methodology 11; (c) keep `gpt-5.6-luna` and switch only when OpenAI publishes a deprecation notice.
- Recommended default: (a). The PRD names it, it is not deprecated, the saving is about a dollar per large campaign (the spike's projection puts calibration well under the ten-dollar estimate either way), and switching changes nothing for Q102. Cost: a calibration judge one generation behind OpenAI's current Luna.
- Blocks: nothing; order 11 is written against the PRD's model.
- Owner answer: (a), the recommended default (2026-10-03).

## Publication suites

Spikes: `aidd_docs/backlog/spikes/which-public-classification-benchmark-seeds-the-publication-suite-and-on-what-terms.md`, `aidd_docs/backlog/spikes/which-public-translation-benchmark-seeds-the-publication-suite-and-on-what-terms.md`. Both licence rungs are settled from evidence (permissive in both cases); what remains in each is a choice only the owner can make.

### Q105. Which public benchmark seeds the classification publication suite?

- Artifact: the classification spike, and `aidd_docs/backlog/stories/a-publication-level-classification-suite-stands-beside-the-hand-written-one.md` (interval epic order 7).
- Question: two CC BY 4.0 sources meet the size and language bounds; the rung is permissive either way. MInDS-14 (`PolyAI/minds14` at `40ce77cb32a384e4d50a568e1ec39ac804019d33`) carries 14 e-banking customer-service intents, spoken natively in FR and DE and transcribed by ASR, 539 to 611 rows per language, licence stated on the card only. MASSIVE 1.1 (`AmazonScience/massive` at `ff6bd8e4b27c3543e4f8fe2108f32bb95a6f8740`), the epic's named lead, carries 18 voice-assistant scenarios translated in parallel, 2,974 test rows per language, licence in a LICENSE file and the publisher's NOTICE, loaded from a tarball because its HF loader is a script `datasets` 4.x cannot run. Which one seeds the suite?
- Options: (a) MInDS-14, 300 items, 100 per language, stratified by intent; (b) MASSIVE 1.1, `test` partition, `scenario` label, 300 items, stable key `locale/id`; (c) both, as two publication suites, at the cost of a second published batch.
- Recommended default: (a). The story's outcome is to show whether a finding on the hand-written support-routing suite survives at a scale where a 10-point gap can be resolved; MInDS-14 is the only candidate whose labels are customer-service routing, while a MASSIVE score would measure a different task. Cost: its licence evidence is the card's identifier and a prose line, not a licence file (the loader records any licence file the source ships, and a different licence reopens the spike); ASR noise lowers the exact-match ceiling; the pool is small enough that a later redraw overlaps.
- Blocks: interval epic order 7, hence order 9 (`the-threshold-review-is-written-from-the-first-publication-run.md`) and the bundle epic's order 7 (`a-drawn-item-reaches-the-download-under-its-own-terms-or-as-a-visible-hole.md`).
- Owner answer: (a), the recommended default (2026-10-03).

### Q106. Is Google's Apache-2.0 label over WMT24 source text accepted for the translation publication suite?

- Artifact: the translation spike, `aidd_docs/backlog/stories/a-publication-level-translation-suite-stands-beside-the-hand-written-one.md` (interval epic order 8), and `LICENSE-DATA` section 3.
- Question: the only candidate that meets size and the three directions without share-alike or no-redistribution terms is WMT24++ (`google/wmt24pp` at `fd7405c06494bc66a57b25f55d217a72f96e60dc`, 998 aligned segments per pair, Apache-2.0 on the card, ungated). Its English sources are the WMT24 test set's, which WMT released as "freely used for research purposes"; Google's Apache-2.0 label covers text Google did not author. FLORES+ is CC-BY-SA 4.0 and its gate forbids re-hosting where crawlers reach it; the original WMT sets are research-only; NTREX-128 is CC-BY-SA 4.0. Is the Apache-2.0 declaration accepted for 300 items published in a public repository?
- Options: (a) accept it on the permissive rung: items ship with `licence` `Apache-2.0`, the Apache-2.0 text ships beside them, and `LICENSE-DATA` section 3 discloses the WMT24 research-use origin as a declaration, on the same footing as the two declarations already there; (b) keep WMT24++ but publish its items on the no-redistribution rung: `prompt` and `reference_output` redacted to the per-item content hash, with source, revision and `segment_id` per item and one fetch instruction per source (Q41 (a)); (c) take NTREX-128 on the share-alike rung instead, segregated under its own licence file.
- Recommended default: (a). The dataset's publisher licenses it Apache-2.0 at a pinned revision, the repository already ships declarations of exactly this kind, and the disclosure makes the reliance visible to a reviewer rather than hidden. Cost: the published items rest on Google's declaration; if it is ever withdrawn, the items move to (b), which the supersede-don't-backfill discipline allows. (b) is the zero-risk option and costs readers a fetch step per item.
- Blocks: interval epic order 8, hence order 9 and the bundle epic's order 7.
- Owner answer: (a), the recommended default (2026-10-03).

## Size-class candidates

Spike: `aidd_docs/backlog/spikes/which-candidate-ggufs-exist-per-size-class-and-does-the-pinned-build-load-them.md` (`blocked`). Every shortlisted family has a pinnable GGUF in each class, and every architecture is in b10537's source table; what remains is one live load per architecture.

### Q107. Which LFM2 models stand for the LFM2 line at ~0.5B and ~2B?

- Artifact: `aidd_docs/backlog/stories/the-half-billion-class-spans-two-families-or-is-published-as-a-searched-single-family-ladder.md` (order 5) and `aidd_docs/backlog/stories/the-two-billion-class-spans-two-families-or-is-published-as-a-searched-single-family-ladder.md` (order 6).
- Question: Q12 names "the smallest LFM2" at ~0.5B and "LFM2" at ~2B. The hub now holds two LFM2 generations; the literal smallest is `LFM2.5-230M`, released after the epic was written and described by its card as distilled from the 350M and "not recommended for reasoning-heavy workloads". Which models stand for the line?
- Options: (a) the current generation at the size nearest the class's Qwen entry: `LFM2.5-350M` at ~0.5B and `LFM2.5-1.2B-Instruct` at ~2B; (b) the literal smallest: `LFM2.5-230M` at ~0.5B and `LFM2.5-1.2B-Instruct` at ~2B; (c) the first generation: `LFM2-350M` and `LFM2-1.2B`.
- Recommended default: (a). It keeps the comparison about the family rather than a 0.23B model against Qwen3-0.6B, takes Liquid's current release, and both templates carry no thinking switch, so `none` is verifiable. Cost: about 133 MB more than (b), and in strict smallest-download order Granite 4.0 H 350M is tried first anyway. `LFM2.5-2.6B` stays out under every option because it always thinks.
- Blocks: the LFM2 gate run in orders 5 and 6; the Granite runs are unaffected.
- Owner answer: (a), the recommended default (2026-10-03).

### Q108. Are the spike's remaining live loads folded into the class stories' gate runs?

- Artifact: the spike, and orders 5 to 8 of `every-size-class-spans-two-families-or-says-it-does-not`.
- Question: what the spike still needs is one `llama-server` load under b10537 per architecture, plus the `/props` template. That load is exactly what `wave-local-ai-v2-candidate-gate` does as the first step of each class story, and each story already handles both outcomes: a pass enters the roster, a refusal or a deferred architecture is recorded under the epic's defer-by-default rule. As written, the stories wait on the spike and the spike waits on the stories' commands. Does the spike close on the stories' first gate runs, so that the class stories can be `ready`?
- Options: (a) yes: the spike's Follow-up becomes the stories' first gate run per architecture; the spike is resolved by the first pass or refusal per architecture, and the stories drop it from their `Blocked:` lines once the owner answers; (b) no: an operator runs the eight loads as a separate session first, the spike closes, then the stories become `ready`; (c) re-scope the spike to existence only and resolve it now, leaving loading to the stories.
- Recommended default: (a). The load result changes no story's acceptance, since a refusal is already a recorded outcome, so a separate session repeats work. Cost: a class story's first run can end in a recorded refusal rather than a roster entry, which the epic allows.
- Blocks: orders 7 and 8 entirely (no other blocker), and orders 5 and 6 together with Q107.
- Owner answer: (a), the recommended default (2026-10-03).

## Tool calling and harnesses

Spike: `aidd_docs/backlog/spikes/does-each-roster-model-emit-parseable-tool-calls-through-llama-server-and-can-each-candidate-harness-drive-it.md` (`blocked` on live probes per roster entry and per framework). Desk research gives no framework an "unable" verdict.

### Q109. Do harness adapters keep each framework's request defaults, or align them with `direct`?

- Artifact: `aidd_docs/backlog/stories/the-same-tool-calling-items-run-under-each-compared-harness.md` (order 7), and through it order 8.
- Question: the frameworks send different requests for the same item by default: smolagents sends `tool_choice: required`, always adds a `final_answer` tool and its own system prompt of about 10 KB; LlamaIndex streams and sends `parallel_tool_calls: true`; pydantic-ai forces the tool choice only for structured output. Two open llama.cpp issues meet exactly these defaults: #27767 (a forced tool choice with thinking off yields prose, and every roster entry runs with thinking off) and #24807 (streamed Qwen3.6 tool calls dropped or misplaced). Does an adapter keep the defaults or align them?
- Options: (a) keep each framework's defaults, record on the row the `tool_choice`, `parallel_tool_calls` and `stream` actually sent (read from the captured request), and publish an engine-defect failure as a harness-by-engine finding; (b) align every adapter to `direct`'s settings and record the override; (c) run and publish both.
- Recommended default: (a). It measures each framework as a user runs it, and the captured request keeps the difference readable on the row. Cost: smolagents rows may measure llama.cpp #27767 rather than smolagents; the spike's attribution run shows whether it reproduces at b10537.
- Blocks: order 7's adapters and order 8's reuse of them, and the `llamaindex` adapter of `a-rag-answer-is-scored-over-a-local-corpus-under-a-named-harness.md` (order 5), since LlamaIndex streams by default (llama.cpp #24807).
- Owner answer: (a), the recommended default (2026-10-03).

### Q110. How does a row name the client package a framework reaches the engine through?

- Artifact: `aidd_docs/backlog/tasks/register-the-closed-harness-candidate-set-and-its-three-row-fields.md` (`done`; this run may not edit it), `src/wave_local_ai_v2/harness.py`, and order 7.
- Question: `harness_version` reads one installed distribution, but `langgraph` reaches the engine only through `langchain-openai`, and `llamaindex` only through `llama-index-llms-openai-like` (the task already flagged `llama-index-core` as the distribution to confirm). The package that builds the request is then not on the row. How is it named?
- Options: (a) keep the one field and rely on the published lockfile hash; (b) make `harness_version` a composite string naming both packages; (c) add a `harness_client_version` field, null for `direct`, `smolagents` and `pydantic-ai`.
- Recommended default: (c). It keeps the existing field's meaning and shows on the row which package built the request. Cost: one more row field and a schema bump, which a new story under order 7 (or order 7 itself) carries; the done task is not reopened.
- Blocks: order 7 rows for `langgraph` and `llamaindex`, and order 5's `llamaindex` rows. Related, for delivery: `harness.HARNESS_DISTRIBUTIONS` reads `pydantic-ai` while the slim install the spike probes is `pydantic-ai-slim`, which the order 7 adapter must reconcile.
- Owner answer: (c), the recommended default (2026-10-03).

## Model-output redistribution

Spike: `aidd_docs/backlog/spikes/may-the-model-outputs-in-the-published-rows-be-redistributed-and-on-what-terms.md` (`resolved`). Every model and provider whose output the bundle carries or will carry permits redistribution, on one condition the terms impose: the content is marked as AI-generated and names its model and provider. The licence-text change is a new task, `aidd_docs/backlog/tasks/the-model-output-fields-cite-the-terms-they-were-checked-against-and-carry-the-ai-generated-notice.md`.

### Q111. The bundle epic's assumption row on generated completions is now verified: will the owner update it?

- Artifact: `aidd_docs/backlog/epics/one-download-holds-the-tables-their-licences-and-how-to-cite-them.md` (`ready`; this run may not edit it), its Dependencies and Unknowns row "Whether generated completions may be redistributed under the bundle's terms".
- Question: the spike verified that row against each source's terms (read 2026-10-02), with the AI-generated marking as the condition; the row still reads as an open assumption, and the epic's falsification clause names it. Is the row updated?
- Options: (a) the owner rewrites the row as verified by the spike, names the marking condition and the new task, and leaves the hand-written-items declaration as the epic's only open licensing assumption; (b) leave the epic as written and let the spike and the task carry the finding.
- Recommended default: (a). An epic that still lists a settled question as open invites a later run to re-investigate it. Cost: one owner edit.
- Blocks: nothing; the task proceeds either way.
- Owner answer: (a), the recommended default (2026-10-03).

## Web research search tools

Spike: `aidd_docs/backlog/spikes/which-two-search-tools-are-obtainable-archivable-and-what-each-sends-upstream.md` (`blocked`). On desk evidence two tools pass, so the out-of-scope trigger in order 10 does not fire: SearXNG self-hosted (pinned at commit `783a094`, no account, but its default engines scrape DuckDuckGo, the Brave website and Google CSE from the instance's IP) and the Mojeek API (own index, one egress destination, "Full storage rights" on its Business plan). Brave's API, Exa and SerpApi forbid storing or republishing results; Google CSE is closed to new customers; Bing's API is retired. No provider grants republication of response text in a CC-BY bundle. Remaining live work: a pinned SearXNG instance and Mojeek queries in EN, FR and DE, captured with their upstream URLs (an install and a provider call this run may not make).

### Q112. Which hosted search tool is the second tool?

- Artifact: `aidd_docs/backlog/stories/two-search-tools-answer-the-same-queries-and-each-row-names-its-tool.md` (order 10) and the second adapter of `aidd_docs/backlog/stories/a-web-research-score-recomputes-offline-from-its-archived-search-responses.md` (order 9).
- Options: (a) the Mojeek API on its Business plan (storage rights stated, own index, about £2 to £3 per 1,000 queries, the owner opens the account and buys credits); (b) Tavily's free tier (no cost, terms silent on storage, keeps and may train on queries); (c) Serper or Jina (free credits, results scraped from Google or undisclosed backends, so egress is two-hop).
- Recommended default: (a). It is the only hosted option whose terms say storage is allowed, and its egress is one destination, so a row's egress field is exact. Cost: an account and a small prepaid amount, an owner act.
- Blocks: order 10, and order 9's second adapter.
- Owner answer: (a), the recommended default (2026-10-03).

### Q113. Which SearXNG engine set is pinned?

- Artifact: order 9 (its egress field) and order 10.
- Options: (a) the default set as shipped (DuckDuckGo, the Brave website, Google CSE through a hard-coded partner id, Wikipedia, Wikidata); (b) the default set minus `google cse`; (c) only engines with sanctioned access (Wikipedia, Wikidata, keyed API engines).
- Recommended default: (b). `google cse` reaches Google through a third party's partner id against Google's terms on automated access; dropping it removes the clearest terms problem and keeps a metasearch representative of a typical deployment. Cost: the remaining engines still scrape two websites, which the row's egress field names; (c) leaves no general web engine.
- Blocks: order 9's egress field and order 10.
- Owner answer: (b), the recommended default (2026-10-03).

### Q114. What does the bundle publish from the archived search responses?

- Artifact: order 9 (its archive format and publication), and the bundle epic's redistribution rules.
- Options: (a) keep each full response in the run archive, which the offline recompute reads, and publish per row only the result URLs, a content hash of the archived response, the tool, the egress destinations and the scores, without titles or snippets; (b) publish full responses in the bundle under a per-item third-party notice, outside CC-BY; (c) ask Mojeek for written permission to republish, publish its responses if granted, otherwise (a).
- Recommended default: (a). No provider's terms and no snippet author grants republication, and (a) still lets any holder of the archive reproduce the score with the network off. Cost: a bundle reader cannot recompute web-research scores without the archive, which the PRD's offline-recompute criterion then reaches only for the archive holder.
- Blocks: order 9's archive format and its publication.
- Owner answer: (a), the recommended default (2026-10-03).

## Input compressor

Spike: `aidd_docs/backlog/spikes/which-llmlingua-2-class-compressor-fits-the-reference-machine-and-in-which-placement.md` (`blocked` on a live CPU measurement). Reference compressor: `microsoft/llmlingua-2-xlm-roberta-large-meetingbank` (MIT, 559M parameters, 2,132 MiB of fp32 weights) through `llmlingua==0.2.2`; GPU co-residence beside any roster model is excluded by this repo's measured VRAM peaks (at most 1,617 MiB left on the laptop).

### Q115. Where does the input compressor run on the reference laptop?

- Artifact: `aidd_docs/backlog/stories/the-input-compression-variant-records-its-compressor-as-a-step-of-its-own.md` (order 9) and its optional dependency group (Q23 (a)).
- Question: two placements fit the hardware. Which does the `input_compressed` variant declare?
- Options: (a) CPU, in the same phase, per item just before the request, with the plain PyPI torch wheel (CPU-only on Windows, about 124 MB); (b) GPU, in a separate phase that compresses every item before the subject's server starts, with the CUDA torch build from the PyTorch `cu126` index (about 2.6 GB, an extra index in `uv.lock`); (c) GPU co-resident beside the subject, excluded by the measured headroom and listed only for completeness.
- Recommended default: (a). It keeps the optional group on plain PyPI, cannot touch the subject's VRAM profile, and counts tokens with the subject's own tokenizer while its server is up. Cost: the compressor's energy is mostly the estimated CPU channel rather than a measured GPU one, and each item takes longer (about 1 to 2 s per item, estimated, not measured).
- Blocks: order 9's declared placement and where its torch comes from; the live CPU measurement the spike lists can proceed under (a).
- Owner answer: (a), the recommended default (2026-10-03).

## Calibration agreement

### Q116. What is the calibration judge's agreement "with the pair" computed against?

- Artifact: `aidd_docs/backlog/stories/a-calibration-judge-scores-one-judged-item-in-ten-and-never-moves-a-score.md` (order 11, its acceptance bullet "The calibration judge's agreement with the pair is published as its own figure per suite, under the statistic Methodology 10 names for the rubric kind" and its `tests/test_agreement.py` value); the same wording in `the-judged-probe-runs-both-paths-in-three-languages.md` (order 6, calibration bullet) and in the epic `any-open-ended-output-carries-two-judges-or-an-honest-flag.md` (`ready`).
- Question: Methodology 10's statistics, as `agreement.py` implements them (quadratic-weighted and unweighted Cohen's kappa, exact-match and within-one rates), are defined between two raters; the pair is two raters already. Against what is the third judge's agreement computed?
- Options: (a) two two-rater figures, calibration against GLM and calibration against DeepSeek, each under the rubric kind's statistic, with n and the EN versus FR and DE split, published beside the pair's own figure; a shared bias then shows as the pair agreeing with each other more than either agrees with the calibrator; (b) one figure against the pair's per-item consensus (for example the rounded mean), undefined for a categorical rubric and sensitive to rounding half-points; (c) one three-rater statistic over all three judges (Fleiss' kappa or Krippendorff's alpha), a statistic Methodology 10 does not name and `agreement.py` does not have.
- Recommended default: (a). It reuses `agreement.agreement_for_rubric` unchanged, works for both rubric kinds, and lets the shared-bias reading the PRD asks of calibration come straight from published numbers. Cost: "its own figure" becomes two figures per suite and language group, a wording change to order 11, order 6's calibration bullet and the epic (an owner edit, since the epic is `ready`).
- Blocks: order 11. Order 6's calibration bullet takes the same wording but order 6 does not wait on order 11.
- Owner answer: (a), the recommended default (2026-10-03).

## Raised while refining proposed stories

### Q117. What does an Ollama quality batch do when its thinking switch is absent or cannot be verified?

- Artifact: `aidd_docs/backlog/stories/ollama-quality-rows-pass-a-prompt-parity-gate-or-publish-as-observations.md` (engine epic order 7), acceptance bullet 5; through it orders 8 and 12.
- Question: the bullet says that, without a verifiable switch, "its rows declare `thinking_policy: allowed`". The code publishes the suite's declared policy on every row (both suites declare `disabled`), and `local_client.thinking_kwargs` and `check_engine_carries` refuse a `disabled` batch an engine cannot carry, as the `done` engine-row story specifies. The bullet and the shipped rule disagree.
- Options: (a) follow the shipped rule: the batch is refused before any generation, and that suite's cross-engine quality cells are listed as refused with the render spike as their reason; (b) run Ollama on a new suite version declaring `allowed` and publish the cross-engine cells as observations; (c) keep the bullet and change what `thinking_policy` means, from the suite's declaration to a per-row report.
- Recommended default: (a). It applies a rule already `done` and keeps `thinking_policy` meaning one thing. Cost: if the live render fails, no cross-engine quality cell exists for that suite; the Ollama spike's desk finding (`think` exists and changes the render) suggests the branch is unlikely.
- Blocks: order 7, and orders 8 and 12 through it.
- Owner answer: (a), the recommended default (2026-10-03).

### Q118. What `max_output_tokens` does the WMT24++ publication suite declare?

- Artifact: `aidd_docs/backlog/stories/a-publication-level-translation-suite-stands-beside-the-hand-written-one.md` (interval epic order 8).
- Question: the hand-written translation suite declares 128 output tokens; WMT24++ segments run to paragraphs (around 150 words), so a cap of 128 truncates them and Methodology 9 scores a suite-cap truncation 0. What cap does the publication suite declare?
- Options: (a) a cap derived from the drawn references, for example at least twice the longest reference's token count, recorded with its reason in the suite definition; (b) keep 128 and let long segments fail as cap truncations; (c) exclude the long-segment domain from the pool so 128 suffices.
- Recommended default: (a). Methodology 9 makes the cap a suite-level choice that must be defensible; 128 would score long items 0 for a reason that is not translation quality, and (c) narrows the construct. Cost: longer generations on the bench.
- Blocks: order 8, hence order 9 and the bundle epic's order 7.
- Owner answer: (a), the recommended default (2026-10-03).

### Q119. Is the WMT24++ draw stratified by domain as well as by language?

- Artifact: the same story, and `src/wave_local_ai_v2/subset_sampler.py` (sampler version `"1"` accepts only `['language']` on a translation rule).
- Question: WMT24++ mixes four domains (news, social, speech, literary). Is the 300-item draw stratified by domain too?
- Options: (a) language only, sampler `"1"` unchanged, the draw's per-domain counts recorded in the results README; (b) language and domain, which needs sampler version `"2"` with a new rule shape and its own tests; (c) language only, with the pool restricted to chosen domains by the loader.
- Recommended default: (a). It needs no sampler change, keeps the replay contract, and discloses the domain mix rather than controlling it. Cost: a draw may skew by domain, visible in the counts.
- Blocks: order 8.
- Owner answer: (a), the recommended default (2026-10-03).

### Q120. Where does the threshold review's n=20 comparison point come from?

- Artifact: `aidd_docs/backlog/stories/the-threshold-review-is-written-from-the-first-publication-run.md` (interval epic order 9), first acceptance bullet ("the interval widths at n=100 ... against those at n=20 for the same use case", "from the published rows").
- Question: no committed row carries `score_interval` (the bundle is schema `"7"`), and the bundle holds no translation row at all; the n=20 classification widths exist only as an analysis in `aidd_docs/results/README.md`. No `depends_on` story publishes a development-level batch carrying an interval.
- Options: (a) orders 7 and 8 each also publish one development-level batch of the hand-written suite, same subject, same bench session, so both sizes carry `score_interval` in the bundle; (b) the review recomputes the n=20 side from committed rows where they exist (classification) and states the translation side absent; (c) wait for the bundle regeneration in `the-laptop-proves-both-modes-and-republishes-the-bundle-once.md` (`ready`), which re-runs only what the bundle already holds (classification).
- Recommended default: (a). One extra 20-item run per suite gives a same-subject, same-build comparison, which is what the bullet needs. Cost: two more local batches; (a) adds one acceptance line to orders 7 and 8.
- Blocks: order 9.
- Owner answer: (a), the recommended default (2026-10-03).

## Stale wording in done stories

From the 2026-10-01 implementation run log, "Code against the backlog". Its other "Needs an owner edit" items are already settled on `main`: both PR #54 story copies carry the amended acceptance, the interval epic's Success Evidence names the exact Binomial reference, and the engine epic's thinking-control row says a switchless engine declares `none`.

### Q121. Does the judge-call story's null rule cover a reasoning count derived from usage totals?

- Artifact: `aidd_docs/backlog/stories/every-judge-call-names-who-answered-its-reasoning-effort-and-its-reasoning-tokens.md` (`done`), acceptance bullet "A provider that does not report reasoning tokens yields an explicit null with the reason, never a zero."
- Question: Google reports no reasoning count of its own; `google_client._reasoning_tokens` derives one as `total - prompt - candidates` and the row says so (`reasoning_tokens_derived`, `reasoning_tokens_source`). Read literally the bullet asks for null. Changing it changes acceptance meaning, which this run may not do.
- Options: (a) amend the bullet to "a provider that reports reasoning tokens neither directly nor derivably from its usage totals yields an explicit null with the reason; a derived count names its derivation on the row", matching the code; (b) keep the bullet and change the code to publish null for Google; (c) leave both, since order 10 retires Google as a judge.
- Recommended default: (a). The derived count is exact arithmetic on the provider's own totals and is labelled as derived, so a reader loses nothing and gains a number. Cost: one owner edit to a `done` story.
- Blocks: nothing.
- Owner answer: (a), the recommended default (2026-10-03).

### Q122. The licence story's "today" list of item-literal modules is stale: will the owner update it?

- Artifact: `aidd_docs/backlog/stories/the-data-is-cc-by-4-0-the-code-stays-mit-and-each-says-so-where-it-lives.md` (`done`; read-only for this run), the bullet "Each module in `src/wave_local_ai_v2/` that holds hand-written item literals (today `classification_suite.py` and `translation_suite.py`) carries a header".
- Question: since `d66f760` the suite items live in `suite_data/*.json` and only `judge_probe.py` holds item literals; the rule itself (each such module carries the header) still holds and `tests/test_data_licence.py` enforces it through `item_literal_modules`. Only the parenthesis is stale.
- Options: (a) the owner replaces the parenthesis with "(`judge_probe.py` since the suites moved to `suite_data/`)"; (b) leave it as history.
- Recommended default: (a). Wording only; no acceptance meaning changes.
- Blocks: nothing.
- Owner answer: (a), the recommended default (2026-10-03).

