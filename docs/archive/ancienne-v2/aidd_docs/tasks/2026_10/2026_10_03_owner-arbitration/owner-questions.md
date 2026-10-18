# Owner questions: owner arbitration session (2026-10-03)

Questions raised during this interactive session, after the owner answered Q100 to Q122 of `aidd_docs/tasks/2026_10/2026_10_02_backlog-refinement/owner-questions.md`. Each came out of the three-amigos readiness review of an item those answers unblocked. Numbering continues from Q122. The owner was present and answered each one in the session.

## Credible client sessions

### Q123. May an appended correcting record lift a release's block?

- Artifact: `aidd_docs/backlog/stories/each-release-reads-its-credibility-verdict-from-its-records-in-its-changelog-entry.md` (order 3).
- Question: Q64 makes a sustained challenge block a release permanently, and order 2 says evidence found after the session never resolves a challenge. Order 1 lets an appended correction replace a record, so a correction could add resolving evidence or recategorise a claim from `fiche_disclosure` to `other`. Does the verdict honour such a correction?
- Options: (a) never: a correction is read at its own append position, may add a block, never removes one already reached; (b) yes, visibly: the verdict line states how many blocking challenges were withdrawn by correction; (c) a correction may recategorise a claim with its reason recorded but never add resolving evidence.
- Recommended default: (a). It is the only reading consistent with both Q64 and order 2. Cost: a mis-recorded claim keeps its release blocked.
- Blocks: order 3's verdict rule and its correction tests.
- Owner answer: (a), the recommended default (2026-10-03).

## Judged reproduction verdict

### Q124. How are absent judge build markers compared?

- Artifact: `aidd_docs/backlog/stories/a-judged-re-run-receives-a-reproduction-verdict-that-separates-the-subject-from-its-judges.md` (quality epic order 6).
- Question: the story's "null on either side is not comparable" rule now covers the build markers that Methodology 12, as amended by Q102 (a), records only where the provider returns them. A provider that returns none would make every judged pair not comparable.
- Options: (a) compare only markers recorded on both sides; a marker absent on both sides is skipped and named as unchecked; one present on one side only is not comparable; (b) strict: any absent marker is not comparable; (c) record markers but compare only the pinned id.
- Recommended default: (a). The verdict stays usable and says what it did not check.
- Blocks: nothing new; settles one acceptance bullet and its test.
- Owner answer: (a), the recommended default (2026-10-03).

## Size-class candidates

Epic: `aidd_docs/backlog/epics/every-size-class-spans-two-families-or-says-it-does-not.md`, orders 5 to 8, and the spike `aidd_docs/backlog/spikes/which-candidate-ggufs-exist-per-size-class-and-does-the-pinned-build-load-them.md`.

### Q125. How does the GGUF spike close for an architecture no class story reaches?

- Question: each class stops at its first passing non-Qwen family (Q12 (a)), so some of the eight architectures (likely `granite`, `mistral3`, `phi3`, `phimoe`) may never be loaded under Q108 (a).
- Options: (a) when orders 5 to 8 are done, the spike resolves with each architecture recorded as loaded (pointer to its gate record) or "not reached: class stopped at <entry_id>", and no extra loads are owed; (b) any unreached architecture gets one extra gate load.
- Recommended default: (a). Cost: loadability of unreached architectures under b10537 stays unknown.
- Owner answer: (a), the recommended default (2026-10-03).

### Q126. Does a load-step refusal raise the one-time build-upgrade tradeoff?

- Question: the gate records `deferred` only on "unknown model architecture"; any other failure to load a file is `refused` at step `load`.
- Options: (a) only a `deferred` record raises it; a load-step refusal is named in the evidence with its verbatim line and the search moves on; (b) any load-step failure raises it.
- Recommended default: (a). A file defect is not a build question.
- Owner answer: (a), the recommended default (2026-10-03).

### Q127. What happens to a candidate that passes the gate but cannot complete both suites?

- Options: (a) the search stops only on a non-Qwen entry that passed the gate and completed both suites; one that fails the suites is withdrawn from `models.json` before merge, recorded with its reason, and the search continues; (b) the entry stays, its failed run is published as a finding, and its family counts.
- Recommended default: (a). The epic calls an entry authored but never run a claim, not evidence.
- Owner answer: (a), the recommended default (2026-10-03).

### Q128 and Q129. Does Q12 (a)'s stop rule stay literal at ~4B and at the top class?

- Question: at ~4B, Granite 3.1 3B-A800M is tried first and is both non-Qwen and MoE, so a pass ends the search before Ministral and Phi. At the top class, a passing Gemma 4 12B ends the search before the 26B-A4B MoE.
- Options: (a) keep Q12 (a) literal in both: order 7's outcome becomes "a second vendor, dense or MoE", and order 8 records the epic's 26B-A4B tower question as untested; (b) ~4B also continues to the first passing dense non-Qwen family; (c) (b) plus the 26B-A4B gated after the 12B.
- Recommended default: (a). Cost: no Ministral or Phi row at ~4B and no rival MoE at the top.
- Owner answer: (a), the recommended default (2026-10-03).

## Publication suites

Stories: interval epic orders 7 and 8 (`a-publication-level-classification-suite-stands-beside-the-hand-written-one.md`, `a-publication-level-translation-suite-stands-beside-the-hand-written-one.md`).

### Q130. Do orders 7 and 8 publish one subject or several?

- Question: both promise to show whether a finding survives at scale, but publish one subject per level, and absolute scores do not compare across suites with different label sets and text types; only a gap or rank between models can survive.
- Options: (a) narrow both to what epic check 12 asks (interval and detection limit at scale) and file the roster-wide rank comparison as a new proposed story; (b) require at least two subjects at both levels in each.
- Recommended default: (a).
- Owner answer: (a), the recommended default (2026-10-03).

### Q131. Is the MInDS-14 Hugging Face card the licence of record?

- Options: (a) yes: the loader records whether the pinned revision ships a licence file, `MInDS-14.zip` is not fetched, and the README states the licence rests on the card; (b) the loader also fetches the zip and reopens the spike on a differing licence file.
- Recommended default: (a). Q105 already accepted card-only evidence as a cost.
- Owner answer: (a), the recommended default (2026-10-03).

### Q132. Where does the loader-written source table live for replay?

- Options: (a) its SHA-256 is recorded in the suite definition; CI replays over a constructed fixture; a documented operator replay re-fetches the pinned revision; (b) the full table is committed beside the suite.
- Recommended default: (a). Cost: replay needs the hub.
- Owner answer: (a), the recommended default (2026-10-03).

### Q133. May one WMT24++ segment be drawn in more than one direction?

- Options: (a) no: the loader assigns each `segment_id` to one direction by a recorded rule before the draw; (b) yes, with the overlap count disclosed.
- Recommended default: (a). The bootstrap treats items as independent.
- Owner answer: (a), the recommended default (2026-10-03).

### Q134. Who moves the published bundle's schema when the publication batches land?

- Options: (a) orders 7 and 8 declare `depends_on` on `the-laptop-proves-both-modes-and-republishes-the-bundle-once.md` (`ready`), which moves it once; (b) whichever of 7 and 8 lands first moves it.
- Recommended default: (a). One owner of the regeneration protocol. Cost: 7 and 8 wait for the laptop runs.
- Owner answer: (a), the recommended default (2026-10-03).

### Q135. Where do the MInDS-14 loader and its parquet reader live?

- Options: (a) a script under `scripts/` with pyarrow pinned in a locked dependency group, never a runtime dependency, and the dependency audit extended to that group; (b) an ephemeral `uv run --with`; (c) a runtime dependency.
- Recommended default: (a).
- Owner answer: (a), the recommended default (2026-10-03).
