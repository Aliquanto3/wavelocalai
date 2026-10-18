# Committed results evidence

The reference bundle is five parts, handed to an auditor together: `runtime-reference.jsonl`,
`quality-reference.jsonl`, `fiches/` (the hardware/run fiches those rows cite by hash),
`aidd_docs/roster/models.json` (the models those rows cite by `roster_entry_id`), and
`suite-definitions/` (each suite's item set, cited by `suite_id`/`suite_version`
on every quality row -- `classification-support-routing.json` and, since 2026-09-06,
`translation-business-short-form.json`). No one file in this set is self-sufficient.

A row alone names its model, sampling, machine (by `fiche_hash`) and code `commit_sha` --
but resolving any of those to an actual artifact needs the rest of the bundle sitting
beside it: `fiche_hash` resolves only against `fiches/`, `roster_entry_id` only against
`aidd_docs/roster/models.json`, `suite_id`/`suite_version` (quality rows) only against
`suite-definitions/`. `tests/test_reference_bundle.py` asserts every pointer on every
row of the current-schema bundle resolves.

The bundle is derived, never hand-edited. This replaces the earlier rule that the
`*-reference.jsonl` files were curated snapshots no CLI ever writes to. Each declared
machine owns one tracked location, `machines/<machine_id>/` (`runtime.jsonl`,
`quality.jsonl`, `refusals.jsonl`); the operator promotes named runs from the machine's
live stores into it (`wave-local-ai-v2-promote`), each machine through its own pull
request, and `wave-local-ai-v2-merge-bundle` writes `runtime-reference.jsonl`,
`quality-reference.jsonl` and `refusals-reference.jsonl` from every location, refusing a
fiche-hash collision between two machines, an undeclared machine id, a misfiled row and
a run promoted by two machines. CI runs `wave-local-ai-v2-merge-bundle --check` and fails
when the committed bundle differs from what the merge derives. The loop, and the
operator-carried fallback for a machine that cannot push, are `docs/setup.md` section 6.

The first bundle derived this way is the laptop's republication of 2026-10-04 (see
"This regeneration (the laptop, both modes, 2026-10-04)" below), from
`machines/laptop-mobile-gpu/`. The schema-"7" curated snapshot of 2026-08-27 it replaced,
whose rows predate `machine_id` and so could never be derived, is kept unedited as
`runtime-reference.schema-7.jsonl` and `quality-reference.schema-7.jsonl`, and the
comparison and leader-set records computed over it as `comparisons.schema-7/` and
`leader-sets.schema-7/`.

The two files the CLIs actually append to, `runtime.jsonl` and `quality.jsonl`, are
per-machine output and stay untracked (`.gitignore`). Tracking them instead would dirty
the working tree on every run and would ship rows that do not belong to any acceptance
criterion.

## Drawn items: MInDS-14 on the permissive rung (2026-10-04)

The bundle is no longer hand-written items only. The publication-level classification
suite `classification-banking-intents-minds14` (snapshot
`suite-definitions/classification-banking-intents-minds14@1.json`) holds 300 items drawn
from MInDS-14, `PolyAI/minds14` at revision `40ce77cb32a384e4d50a568e1ec39ac804019d33`
(https://huggingface.co/datasets/PolyAI/minds14/tree/40ce77cb32a384e4d50a568e1ec39ac804019d33), configs `en-US`, `fr-FR` and
`de-DE`: 100 per language, 7 or 8 per intent, each marked `provenance` `public` and
contamination-risk (Methodology 5), each naming its licence, source, source revision and
content hash, under the selection rule its definition records.

- **Rung applied: permissive.** MInDS-14 is CC BY 4.0, so its items and the rows carrying
  them ship unchanged in this bundle: no segregation, no redaction (the epic's three-rung
  ladder, applied as written in advance).
- **The licence rests on the card.** The Hugging Face dataset card at the pinned revision
  is the licence of record (`license: cc-by-4.0`; "All datasets are licensed under the
  Creative Commons license (CC-BY)"). The loader read the revision's file list: it ships
  no licence file (`source_table.licence_file_at_revision` is `false`), and the original
  `MInDS-14.zip` release was not fetched. A licence file at that revision naming anything
  other than CC BY 4.0 would reopen the licence spike.
- **Attribution, as CC BY 4.0 requires.** Creator: PolyAI (Gerz et al., "Multilingual and
  Cross-Lingual Intent Detection from Spoken Data", 2021,
  https://arxiv.org/abs/2104.08524). Copyright notice: the card states none; the work is
  attributed to its creator. Licence: CC BY 4.0,
  https://creativecommons.org/licenses/by/4.0/. Source: https://huggingface.co/datasets/PolyAI/minds14,
  revision `40ce77cb32a384e4d50a568e1ec39ac804019d33`. Changes: each transcription was wrapped in a prompt template (an
  instruction naming the fourteen intents) and each intent mapped from its class index to
  its name. `LICENSE-DATA` section 2 states the same terms.
- **How the items were picked** is the recorded rule, checked by replaying it. CI replays
  the draw over a constructed table (`tests/test_minds14_suite.py`). The operator replay
  re-fetches the source table from the pinned revision, checks its SHA-256 against the one
  the definition records (`source_table.sha256`), then replays the rule over it:
  `uv run --group loaders python scripts/minds14_suite.py verify` (exit 0 only when both
  hold). The loader's parquet reader, pyarrow, sits in the locked `loaders` dependency
  group, never in the runtime dependencies.
- **Never averaged with the 20-item score.** The hand-written `classification-support-routing`
  stays the development-level score and leads; the MInDS-14 score sits beside it as the
  scale check, on its own suite id and level, and no table here averages the two
  (Methodology 4). Their label sets differ (four routing queues against fourteen banking
  intents), so the two accuracies are not on one scale either.

### Both levels on one subject: Granite 4.0 H 350M (2026-10-04)

One bench session on `laptop-mobile-gpu` (`gpu`), from commit `95040a7` with no tracked
change, so every row carries `tree_dirty: false`: one development-level batch of the
hand-written suite and one publication-level batch over MInDS-14, on the same subject.
Rows carry no session id, so the pair is defined by the three fields both batches share,
checkable from the rows (`tests/test_reference_bundle.py`): `roster_entry_id`
`granite-4.0-h-350m-q8`, `fiche_hash` `5ce2bf21...` (the fiche its earlier batches
cite) and `engine_build` `b10537`. The development score leads; the publication score
sits beside it as the scale check. The two are never averaged, and they are not on one
scale: four routing queues against fourteen banking intents.

| Level | Suite | run_id | Items | Accuracy | 95% interval | Minimum detectable effect |
| ----- | ----- | ------ | ----- | -------- | ------------ | ------------------------- |
| development (leads) | `classification-support-routing@5` | `1c5a5471245e458d80dea8393383b59e` | 20 | 0.50 | [0.30, 0.70] | 0.200 |
| publication (beside it) | `classification-banking-intents-minds14@1` | `7b8f2569a2044a9e9f8f62a0b7770098` | 300 | 0.227 | [0.180, 0.277] | 0.048 |

Per language, the publication batch holds 100 items in each cell: EN [0.20, 0.37], FR
[0.11, 0.26], DE [0.15, 0.30], each with a minimum detectable effect of 0.075 to 0.085;
the development batch's cells hold 10, 5 and 5 items, with minimum detectable effects of
0.30 to 0.40. At 20 items nothing under 20 points is resolvable; at 300, about 5 points
is, which is the scale the epic asks the publication level to reach.

Read the publication score with its failure shape. The subject named an intent on 294 of
300 items (6 `unparseable`, no truncation), and 143 of those answers were `app_error`:
a 0.34B model collapsing onto a few labels, not a scoring artefact. Every intent it did
name, `app_error`, `business_loan` and `cash_deposit` among them, parsed to itself
through the multi-word label match. The development batch repeats this subject's earlier
published 0.50 on the same suite version.

Commands, logs and the live stores: `aidd_docs/tasks/2026_10/2026_10_04_publication-classification-suite/evidence/`.

## Drawn items: WMT24++ on the permissive rung (2026-10-04)

The publication-level translation suite `translation-mixed-domain-wmt24pp` (snapshot
`suite-definitions/translation-mixed-domain-wmt24pp@1.json`) holds 300 segments drawn from
WMT24++, `google/wmt24pp` at revision `fd7405c06494bc66a57b25f55d217a72f96e60dc`
(https://huggingface.co/datasets/google/wmt24pp/tree/fd7405c06494bc66a57b25f55d217a72f96e60dc), pair files `en-fr_FR.jsonl` and
`en-de_DE.jsonl`: 100 per direction (EN->FR, FR->DE, DE->EN, the hand-written suite's
three), each marked `provenance` `public` and contamination-risk (Methodology 5), each
naming its licence, source, source revision, content hash and WMT24++ `domain`, under the
selection rule its definition records.

- **Rung applied: permissive.** WMT24++ is Apache-2.0 at its publisher, and the owner
  accepted Google's label over the WMT24 source text (owner answer Q106 (a)), so its items
  and the rows carrying them ship unchanged in this bundle: no segregation, no redaction
  (the epic's three-rung ladder, applied as written in advance). Each item carries
  `licence` `Apache-2.0`. The dataset card at the pinned revision is the licence of record
  (`license: apache-2.0`); the revision ships no licence or NOTICE file
  (`source_table.licence_file_at_revision` is `false`). A copy of the Apache-2.0 text,
  `LICENSE-APACHE-2.0.txt`, sits in each directory holding drawn WMT24++ items: this one
  (the bundle rows), `machines/` (the per-machine rows), `suite-definitions/` and
  `src/wave_local_ai_v2/suite_data/`. The change
  made: each segment's source text is wrapped in the suite's prompt template, the
  hand-written suite's instruction shell; the reference is unchanged.
- **The English sources are WMT24's**, which WMT released for research use; the items
  rest on Google's Apache-2.0 label, disclosed as a declaration in `LICENSE-DATA`
  section 3. Attribution: WMT24++ by Google (Deutsch et al., 2025,
  https://arxiv.org/abs/2502.12404), Apache-2.0; `LICENSE-DATA` section 2.2 states the
  terms.
- **Two directions translate translations.** The FR->DE and DE->EN source texts are
  themselves translations from English (WMT24++'s French and German post-edited
  references), and DE->EN's reference is the original English. Only EN->FR translates an
  original text (spike assumption A4).
- **How the items were picked** is the recorded rule, checked by replaying it. The loader
  (`scripts/wmt24pp_suite.py`, standard library only) joins the two pair files on
  `segment_id`, drops every segment with `is_bad_source` true (the canary and 37 social
  segments: 38 of 998), and assigns each remaining segment to exactly one direction by
  `segment_id` modulo 3 (0 EN->FR, 1 FR->DE, 2 DE->EN), so no segment is drawn in two
  directions and the items stay independent for the bootstrap (owner answer Q133 (a)).
  The post-filter pool per direction: EN->FR 315, FR->DE 322, DE->EN 323 (960 segments, the
  source table's `row_count`). The draw is stratified by language only, under sampler
  version "1", seed 20261004, accepted on the first attempt. CI replays the draw over a
  constructed table (`tests/test_wmt24pp_suite.py`). The operator replay re-fetches the
  two files from the pinned revision (each checked against the git object id the Hub
  lists), checks the table's SHA-256 against `source_table.sha256`
  (`db57a8a457dce9ae2f38e0b4595a582bf9bf471475dc545b3b4bc89e2546f4ed`), then replays the rule over it:
  `uv run python scripts/wmt24pp_suite.py verify` (exit 0 only when both hold).
- **The output cap is derived from the references.** `max_output_tokens` is 608, twice
  the longest drawn reference (304 tokens, `google/wmt24pp:805`) as the tokenizer of
  `granite-4.0-h-350m-q8`, the model the published batches run, counts it
  (`llama-server` b10537 `/tokenize`, no special tokens); the definition records the
  basis (`max_output_tokens_basis`) and each item its `reference_tokens`. It does not
  inherit the hand-written suite's 128 (owner answer Q118 (a)).
- **Never averaged with the 21-item score.** The hand-written
  `translation-business-short-form` stays the development-level score and leads; the
  WMT24++ score sits beside it as the scale check, on its own suite id and level, and no
  table here averages the two (Methodology 4). Their items differ in length and register
  (one business sentence against paragraph-level news, social, literary and speech
  segments), so the two chrF scores are not on one scale either.

The draw's per-domain counts (owner answer Q119 (a)), recomputed from the suite
definition by `tests/test_wmt24pp_suite.py`:

| Domain | EN->FR | FR->DE | DE->EN | Total |
| ------ | ------ | ------ | ------ | ----- |
| literary | 12 | 21 | 28 | 61 |
| news | 19 | 16 | 14 | 49 |
| social | 55 | 53 | 50 | 158 |
| speech | 14 | 10 | 8 | 32 |
| all | 100 | 100 | 100 | 300 |

### Both levels on one subject: Granite 4.0 H 350M, translation (2026-10-04)

One bench session on `laptop-mobile-gpu` (`gpu`), from commit `0f69b60` with no tracked
change, so every row carries `tree_dirty: false`: one publication-level batch over
WMT24++ and one development-level batch of the hand-written suite, on the same subject.
Rows carry no session id, so the pair is defined by the fields both batches share,
checkable from the rows (`tests/test_reference_bundle.py`): `roster_entry_id`
`granite-4.0-h-350m-q8`, `fiche_hash` `5ce2bf21...` (the fiche its earlier batches cite),
`engine_build` `b10537` and `commit_sha` `0f69b60`. The development score leads; the
publication score sits beside it as the scale check. The two are never averaged, and they
are not on one scale: one business sentence against paragraph-level segments in four
domains, with two directions translating translations.

| Level | Suite | run_id | Items | chrF | 95% interval | Minimum detectable effect |
| ----- | ----- | ------ | ----- | ---- | ------------ | ------------------------- |
| development (leads) | `translation-business-short-form@4` | `da8737246ed54cbf88ddce02e1d1d26b` | 21 | 0.484 | [0.358, 0.614] | 0.128 |
| publication (beside it) | `translation-mixed-domain-wmt24pp@1` | `525734d8b1a44d3681a77aed5b3baee2` | 300 | 0.367 | [0.347, 0.387] | 0.020 |

Per direction, the publication batch holds 100 items in each cell: EN->FR [0.32, 0.40],
FR->DE [0.28, 0.34], DE->EN [0.40, 0.46], each with a minimum detectable effect of 0.030
to 0.039; the development batch's cells hold 7 items each, with minimum detectable effects
of 0.14 to 0.15. At 21 items nothing under about 13 chrF points is resolvable; at 300,
about 2 points is. The development batch repeats this subject's earlier published 0.484
on the same suite version (`be0dda5e...`), interval for interval.

Read the publication score with its failure shape. The cap held: 0 rows failed
`truncated_max_tokens` (the longest completion was 320 tokens against the cap of 608),
and one row failed `empty` (`google/wmt24pp:118`, FR->DE), scored 0. By domain, the mean
item chrF is social 0.339 (158 items), literary 0.385 (61), news 0.410 (49) and speech
0.408 (32); these are descriptive means, not intervals.

The heading "The translation suite's first live run (2026-09-06)" further down predates
this bundle: its statement that the committed `quality-reference.jsonl` holds no
translation row is no longer true, and the section stands as the record of that day.

Commands, logs and the live stores: `aidd_docs/tasks/2026_10/2026_10_04_publication-translation-suite/evidence/`.

## The client-session record (`client-sessions.jsonl`)

`client-sessions.jsonl` is not part of the bundle: it records how the results were
received. Each line is one session in which a benchmark result was shown to a client or
their engineer, appended by hand the same day: the release shown, whether the audience
was outside the consultant's own firm, the outcome, and per challenge the challenger's
role, the criterion disputed, the claims it bears on and the evidence that resolved it,
under a pseudonymous client id only. The file is tracked, append-only (a test walks its
committed history), and holds no real session yet; it ships empty.
`wave-local-ai-v2-client-sessions` checks it, refusing a malformed record by line and
field and reporting an incomplete one. The procedure that takes a consultant from the
end of a session to a committed record, with a worked example, is
[`docs/client-session-record.md`](../../docs/client-session-record.md).

## The published bundle's schema, and why it can lag the code

The bundle's rows carry `schema_version` `"30"`, the code's own since the 2026-10-04
republication. Before it, they carried `"7"` while the code moved to `"30"`: the bytes
were **not** back-filled, because adding fields to rows produced on 2026-08-27 would make
them rows no harness ever wrote, which is the discipline this file states twice below and
which Story 19's acceptance requires. `tests/test_reference_bundle.py` therefore asserts
the bundle against its own `PUBLISHED_BUNDLE_SCHEMA_VERSION` rather than the live
constant, and separately that the published version is never *ahead* of the code. The
next schema bump puts the bundle behind again until a bench-time regeneration on the same
protocol (two runtime runs in a quiet thermal window, two quality runs, the validator
proof, this README's tables rebuilt) moves that constant.

## The bundle as five flat tables (`wave-local-ai-v2-export`)

`uv run wave-local-ai-v2-export --output-dir <dir>` reads the five parts above plus the
analysis records in `comparisons/` and `leader-sets/` (by default the committed reference
files and directories, never the untracked `runtime.jsonl` / `quality.jsonl` unless
`--runtime-rows` / `--quality-rows` point at them; `--comparisons-dir` / `--leader-sets-dir`
name other record directories) and writes seven CSV files into `<dir>`. It
runs no benchmark, changes no bundle file, refuses to write into a bundle directory, and
uses the standard library alone.

| File | One row per | What it holds |
| ---- | ----------- | ------------- |
| `quality_items.csv` | quality row | every row field, nested blocks as named columns (`sampling_seed`, `language_breakdown_en_accuracy`, `failure_counts_unparseable`, `verdict_verdict`, ...), the cited fiche as `fiche_*`, the cited roster entry's model fields as `roster_entry_*` plus `roster_file_version`, the cited suite definition as `suite_definition_*`, and each item's terms (`item_content_hash`, `item_source_key`, `item_redaction`, `item_licence_file`; `LICENSE-DATA` section 2) |
| `runtime_aggregates.csv` | runtime row | the same, minus the suite; the per-repetition arrays (`repetitions`, `warmup_repetitions`, `verdict.reference_repetitions`) stay in the bundle |
| `fiches.csv` | stored fiche | `fiche_hash` (the file name) and every fiche field |
| `roster.csv` | roster entry | every entry field, launch flags, validated host, licence block and language claim included |
| `comparison_records.csv` | comparison-family record, comparison, leader-set record, leader-set subject | `record_kind` names which and `record_file` the record's file; the family record's fields as `family_*` (on its comparisons' rows too, so each comparison carries its family), the comparison's as `comparison_*` (`result_*` for the test block), the leader-set record's as `leader_set_*` (on its subjects' rows too), the subject's as `subject_*` |
| `column_dictionary.csv` | column | `table`, `column`, `carried`, `source`, `meaning`, `unit`, `empty_cell`, `owner` |
| `bundle_manifest.csv` | bundle part | the path read, entries read, and the version values the part carries (`record_version` for the two record directories) |

Read one table with no join: every pointer a row cites is resolved into columns of that row.

**The schema it declares is the one it read.** `bundle_manifest.csv` states the distinct
`schema_version` values each row file carries -- `7` for both today -- read from the bytes,
not from `row_contract.SCHEMA_VERSION`; each row also keeps its own `schema_version` column.
A regenerated bundle declares its own version with no code change. The roster gap is shown,
not reconciled: rows state `roster_version` `1`, the roster file they resolve against is
`roster_file_version` `4`.

**Absence stays absence.** An empty cell is either a recorded `null` or a field the source
does not carry; the row's last column, `fields_not_carried`, lists the columns whose
emptiness means "not carried", so the two stay apart without a `null` token turning a numeric
column into text. Each dictionary entry states what an empty cell means in that column.

**The dictionary and the tables agree both ways.** Every `carried=true` entry is a header of
its table and every header has one entry (`tests/test_bundle_export.py`). `carried=false`
entries name what the bundle read does not hold, with an owner: the row-contract fields
added after `"7"` (`retries`, `resumed`, `thinking_policy`, the prompt-variant, graded and
judge blocks, the energy-window fields, the suite level and the item licence, source and
source revision, the subject egress, and `score_interval` from `"21"`, whose owner cell names
`a-score-is-published-with-its-interval-a-difference-with-its-test`), the per-repetition
arrays, and each record kind (`comparison_family`, `comparison`, `leader_set`) the record
directories read do not hold. A bundle whose rows carry the interval has its block as
`score_interval_*` columns (header, then `suite_*` and `by_language_<lang>_*` cells); a row
written before `"21"` shows them empty and listed in its `fields_not_carried`, a partial or
judge-probe row shows them empty as a recorded null: never a zero, never back-filled.
A row field the dictionary does not describe, an unresolved pointer or a non-finite float
refuses the whole export before anything is written.

**The fifth table flattens the analysis records and computes nothing.** Every cell of
`comparison_records.csv` is a value a record in `comparisons/` or `leader-sets/` holds, at
the path the dictionary's `source` names; no p-value, adjustment or leader set is derived
during the export. A refused comparison is a row with its `comparison_refusal` cell and,
from `record_version` `2`, `comparison_adjusted_p_value_null_reason` `comparison_refused`;
a leader-set subject not compared is a row with its `subject_not_compared_reason`. A
superseded family record stays a row: the record superseding it lists its id in
`family_supersedes`, and the current family is the one no row lists there. Lists
(`refusal`, `paired_values`, `supersedes`, ...) are compact JSON cells; columns a row's kind
does not carry are empty and listed in its `fields_not_carried`. The meaning, unit and null
reasons of the record fields are defined by the statistics epic beside the code that writes
the records (`comparison.FAMILY_RECORD_FIELDS`, `comparison.COMPARISON_RECORD_FIELDS`,
`leader_set.LEADER_SET_RECORD_FIELDS`, `leader_set.SUBJECT_RECORD_FIELDS`) and read by the
export, never redefined there: each record column's `owner` cell names that epic and module,
and its `empty_cell` states the row-kind case followed by the field's own null reasons
(`tests/test_bundle_export.py` fails on a dictionary entry that differs from the
definition). A record citing a `run_id` the quality rows
read do not hold, a leader set citing a family record not read, a `supersedes` id naming no
record read, a malformed record, or a file in a record directory that is not a record of that
directory's type refuses the export. A record directory that does not exist holds no record
of its kind: the table is written as its header, the kinds are named `carried=false`, and
the manifest lists the path with 0 entries. Over the committed bundle: 14 rows (4 family records, 7 comparisons, 1
leader set, 2 subjects), 96 columns; the run is in
`aidd_docs/tasks/2026_10/2026_10_01_comparison-and-leader-records-fifth-table/evidence/`.

**The format is pinned.** UTF-8 without a byte-order mark; `,` delimiter; `"` quoting,
minimal, a quote inside a quoted cell doubled; CRLF record terminator (RFC 4180), with line
breaks inside quoted cells kept as written; floats as Python's shortest round-trip `repr`
(`8.553058931896319e-05` reads back as the same double); booleans `true`/`false`; lists, and
the judge block's nested records, as compact JSON. Two runs over the same bundle are byte
identical.

### Recomputing the intervals and the paired tests from the tables alone (2026-10-02)

`scripts/recompute_from_export.py <export-dir>` is a third party holding only the download:
standard library, nothing imported from this project, reading `quality_items.csv` and
`comparison_records.csv`. It recomputes every batch's interval block (suite and language
cells) from the per-item `correct` / `item_score` columns with the block's own seed,
resample count and confidence level, drawing as the dictionary entry of
`score_interval_draw_procedure_id` states; every `mcnemar_exact` comparison's contingency,
paired n and exact p from the two sides' per-item columns joined on `item_id`; and each
family's Holm-adjusted p from its raw p-values. It prints each value beside the published
cell and exits `1` on any difference.

Over the committed bundle it has nothing to recompute (`0 values recomputed`): the rows are
at `"7"`, before `score_interval`, and all four family records refuse on `thinking_policy`.
So the check was run against ourselves over a bundle built from the committed rows by the
writers' own code (`tests/published_bundle_fixtures.py`: `thinking_policy` set,
`score_interval.interval_block` per batch, one family of both local-vs-cloud pairs from
`comparison`), exported by `wave-local-ai-v2-export`:

| Batch or comparison | Published = recomputed |
| ------------------- | ---------------------- |
| `5e13166d...` `Qwen3.6-35B-A3B`, suite | [0.6, 0.95], MDE 0.175 |
| `5e13166d...` `mistral-small-2603`, suite | [0.85, 1.0], MDE 0.07500000000000001 |
| `d20afbda...` `Qwen3.6-35B-A3B`, suite | [0.6, 0.95], MDE 0.175 |
| `d20afbda...` `mistral-small-2603`, suite | [0.75, 1.0], MDE 0.125 |
| McNemar, run `5e13166d...`, local vs cloud | b=1, c=4, n=20, p=0.375, Holm-adjusted 0.75 |
| McNemar, run `d20afbda...`, local vs cloud | b=2, c=4, n=20, p=0.6875, Holm-adjusted 0.75 |

96 values in all (every language cell's `n`, bounds, MDE and null reason included), 0
differ, exit `0`. These intervals are not published results: the committed rows carry
none. The check is re-run as it stands once a schema-21 batch and a tested comparison are
committed. Commands and full output:
`aidd_docs/tasks/2026_10/2026_10_01_tabular-export-carries-interval-and-comparison/evidence/`.

### Recomputation from the quality table alone (2026-10-01)

Each published run's `suite_accuracy` and per-language accuracy, recomputed from the
exported `quality_items.csv` with Python's `csv` module and nothing else (mean of the
per-item `correct` column, grouped by `run_id`, `provider`, `model_id`, then by `language`):

| `run_id` | Provider | Model | n | `correct` | Recomputed | Published | `en` / `fr` / `de` recomputed | Match |
| -------- | -------- | ----- | - | --------- | ---------- | --------- | ----------------------------- | ----- |
| `5e13166d...` | local | `Qwen3.6-35B-A3B` | 20 | 16 | 0.8 | 0.8 | 0.6 / 1.0 / 1.0 | yes |
| `5e13166d...` | mistral | `mistral-small-2603` | 20 | 19 | 0.95 | 0.95 | 1.0 / 1.0 / 0.8 | yes |
| `d20afbda...` | local | `Qwen3.6-35B-A3B` | 20 | 16 | 0.8 | 0.8 | 0.6 / 1.0 / 1.0 | yes |
| `d20afbda...` | mistral | `mistral-small-2603` | 20 | 18 | 0.9 | 0.9 | 1.0 / 1.0 / 0.6 | yes |

Every recomputed value equals the published one exactly, per-language `n` included (10 / 5 /
5). The script and its raw output are in
`aidd_docs/tasks/2026_10/2026_10_01_the-published-bundle-reads-as-four-flat-tables/evidence/`.

## Runtime energy window changed underfoot the rows already in this file (2026-09-22)

As of this increment's commit (`row_contract.SCHEMA_VERSION` `"12"`, see its numbered
comment for the full field list), a runtime row's `energy_kwh` and its three per-channel
siblings (`cpu_energy_kwh`, `gpu_energy_kwh`, `ram_energy_kwh`) are measured **per counted
repetition** -- the CodeCarbon tracker starts and stops around each generation only,
excluding the fixed cooldown between repetitions -- and the row states the method
(`energy_window_method`) plus the two window sizes it measured and excluded
(`active_window_s`, `idle_window_s`).

Every runtime row produced before this commit -- **including every runtime table already
in this file** -- measured the whole counted-repetition span instead, cooldowns included,
per the superseded `aggregation.AGGREGATION_LABELS` value
`"total_over_counted_repetitions_including_cooldowns"`. Idle cooldown was 43-89% of that
measured window (audit finding C3, `aidd_docs/tasks/2026_09/2026_09_22_audit/report.md`),
biasing every fast model's energy, emissions and cost-per-token figures upward relative to
a slower one. Those rows and tables are **not edited**: this file's "superseded, never
edited" discipline (see "Dense versus MoE" below) applies to every energy-bearing number
already published here, not only to full-row regenerations. A reader can tell which stored
rows are affected by `schema_version` alone: any row below `"12"` measured the whole
window.

## Before/after: the active-window fix on a fast dense model and the MoE flagship (2026-09-22)

Live re-run of the two models at either end of the audit's idle-share range, same default
protocol (1 warm-up, 5 counted repetitions, 10 s cooldown, pinned seed, 128-token cap):
`Qwen3-0.6B` (idle share 0.89 -- the model the C3 bug hit hardest) and `Qwen3.6-35B-A3B`
(idle share 0.43 -- the comparison anchor, least affected). "Before" is the existing
`### Runtime` table's row for each model (`run_id` `68a5e1df...`, `schema_version` `"10"`,
`commit_sha` `feb0d892...`, live store; and `run_id` `f7faeef7...`, `schema_version` `"7"`,
`commit_sha` `9bc9da88...`, committed `runtime-reference.jsonl`). "After" is a fresh run on
this commit (`commit_sha` `5d9a0044...`, `schema_version` `"12"`), fiches
`f804bee0d215c89c05289907fd2573fa722d290896775749f3c6d16329efca18` (0.6B) and
`b9d1af56db2b6a26bfb265842bfd757dc78ed2d95e4ad3fce0088b8396d9003a` (MoE).

| Model | `run_id` (after) | Energy before (kWh) | Energy after (kWh) | Cost/M tokens before (EUR) | Cost/M tokens after (EUR) | `active_window_s` | `idle_window_s` | `energy_window_method` |
| ----- | ----------------- | -------------------- | -------------------- | ---------------------------- | ---------------------------- | ------------------ | ---------------- | ----------------------- |
| `Qwen3-0.6B` | `45d2bf7d...` | 0.00078053 | 0.00015809 | 0.018775 | 0.003803 | 5.281 | 40.0 | `per_repetition_tasks` |
| `Qwen3.6-35B-A3B` | `cc1efa34...` | 0.00264222 | 0.00182048 | 0.063361 | 0.043656 | 52.719 | 40.0 | `per_repetition_tasks` |

The 0.6B-to-MoE cost-per-token ratio (0.6B's `cost_per_million_tokens` divided by the MoE's)
went from **0.2963** before (0.018775 / 0.063361) to **0.0871** after (0.003803 / 0.043656)
-- the same direction the energy ratio moves (0.2954 before, 0.0868 after). The gap between
the two models **widens**, not narrows, once the whole-window bug is fixed: the audit's
0.89 idle share for the 0.6B means the fixed 40 s cooldown -- the same absolute amount of
idle draw the MoE run also carried -- was a large constant added on top of the 0.6B's own
tiny 5.28 s active window, pulling its reported figure up toward the MoE's and compressing
the true ratio toward 1. Removing that constant does not narrow the models' apparent
difference; it reveals how much larger it actually is. A reader should expect this same
direction (ratios moving further from 1, not closer) on any other fast-versus-slow
comparison this bundle publishes below, since every one of them was measured under the
superseded whole-window method.

Caveat, same as every other before/after section in this file: `commit_sha` and
`schema_version` differ between the before and after rows (feature-branch commits and
schema "10"/"7" versus "12"), so the comparison is a same-hardware, same-protocol
before/after on this method change specifically, not a byte-identical row diff.

## What the dashboard withholds, and why

The three pitch screens (`frontend/src/views/quality/`, `views/runtime/`,
`views/energy/`) render every field the read model resolves, but three
constructs are deliberately shown as a declared absence rather than as a
value on day one -- documented evidence of honest withholding against this
bundle's real state, not an apparent gap in what those screens ship.

- **A judged score.** `read_model.QUALITY_JUDGE_FIELDS` (`row_contract.
  JUDGED_FIELDS`) resolves against every row in this bundle -- no store,
  reference or live, holds a judged row today. `QualityView`'s judge column
  (`renderJudgeBlock` in `frontend/src/views/quality/QualityView.tsx`)
  renders `DeclaredAbsenceLabel` naming `judged-score-withheld` on every
  entry until a row carries either an agreement figure over two judges or
  the `single_judge` flag; Methodology 11 forbids a plain `judged_headline_score`
  number without one. The owning epic is the judge machinery this repo has
  already built (`judge.py`, `judge_protocol.py`, `agreement.py`) but has not
  yet run against either suite.
- **The energy headline, when a channel's label is missing.**
  `read_model._energy_entry` withholds `energy_headline` outright -- never
  publishing a composite `energy_kwh`/`emissions_kg` without all three
  per-channel `*_energy_method` labels beside it -- and states which channel
  is missing via `missing_labels`. `EnergyView`'s `HeadlineBlock` renders
  that as `DeclaredAbsenceLabel` per missing channel rather than a number
  with an unlabelled method. Every row in this bundle carries all three
  labels; the mechanism is exercised in tests against a hand-edited fixture
  entry (`frontend/src/views/energy/fixtures/energyView.fixture.ts`), not
  against a real gap in the committed bundle.
- **The coverage record.** No store, route, or `read_model` field carries a
  coverage record (exercised/covered-by-dimension/out-of-scope) today --
  it is owned and built by a sibling epic, per that epic's own boundary
  ("this epic excludes showing any of this to a human"). `QualityView`'s
  `CoverageRecord` component renders a static `DeclaredAbsenceLabel` naming
  `no-use-case-is-silently-absent`, wired to no API field, rather than
  fabricating an entry this story's own scope does not build.

## What the overview withholds on day one, and why

The pitch overview (`views/overview/`, `GET /api/overview/quality`,
`GET /api/overview/runtime`) is the routed root, composing one card per
`task_suite` present in the quality store. Two of the three constructs above
carry through to it unchanged; a third is specific to the overview's own
leader-set mechanism.

- **The leader set.** Read from the current leader-set record of the card's suites
  (`leader-sets/`, see "The leader set" below), never from a row field: its members
  are rendered from the store's own rows, and `leader.leader_sets` names each record
  read with its machine class and whether it is `incomplete`. A suite with no record
  resolves to the ordinary `pointer_unresolved` absence naming `leader_set`, and
  `overview/quality/QualityPanel.tsx` renders `DeclaredAbsenceLabel` naming "no
  leader set published for this suite and machine class" rather than a substituted
  highest score. In this bundle the classification card names one member
  (`5e13166d`, from an incomplete record). `cloud_comparators` is not part of this --
  the reference bundle does carry `provider != "local"` rows (a real mistral
  comparator alongside the local ones), so every card's cloud-comparator list is
  populated, not empty. The frontend does not show `incomplete` yet.
- **The runtime/energy headline, following from the leader.**
  `overview/runtime/RuntimeEnergyPanel.tsx` receives `leaderRosterEntryIds`
  from `OverviewView`, derived from `leader.members` when a leader set
  exists. With no leader set, that list is empty and the panel renders the
  same class of `DeclaredAbsenceLabel` ("no model to take a headline from")
  rather than guessing a headline from an unranked row.
- **The coverage record.** `overview/CoverageAbsence.tsx` is the same
  `no-use-case-is-silently-absent` declared absence as `QualityView`'s
  `CoverageRecord`, rendered once at the overview page level rather than
  once per card.

## Suite levels, and what an item's licence and source do not prove (2026-10-02)

Every suite declares the level it is built to, and every quality row from schema `"15"`
names the level its suite was certified at (`suite_level`). A `development` suite is gated
as before: at least 20 items and at least 25% of items in each of EN, FR and DE, else its
score is published marked indicative. A `publication` suite is certified or refused: at
least 100 items and at least the size target it declares (300 where its public source
supplies them, the 100-item floor where it does not, with the reason recorded beside the
target), the same 25% share, and a licence, a source and that source's revision on every
item. A publication suite that falls short is refused at load, naming every shortfall; it
never passes quietly as a development one, so no row of it can be written.

Both shipped suites are `development`: `classification-support-routing@4` and
`translation-business-short-form@3` carry `level` and, on every item, `licence`
`CC-BY-4.0` -- the repository's hand-written items -- and no source, since nothing was
drawn. Their rows carry `item_licence` `CC-BY-4.0` and `item_source` /
`item_source_revision` as `null`. No item text changed and neither `prompt_set_hash`
moved; the versions bumped because a published snapshot is never rewritten under its own
version (`suite_snapshot` now refuses to overwrite one with different content), and
`@3` / `@2` stay beside them. The cost: a row written under the new versions is
`not_comparable` to any row written under `@3` / `@2`, although the subject is sent
identical text. No committed row cites `@3` / `@2` today.

**The licence and the source are author declarations, and nothing verifies them.** The
gate checks that a publication item declares a licence, a source and a revision, and that
each is a non-empty string; it does not check that the licence is the source's actual
licence, that the item came from that source, or that the revision exists.
`contamination_risk` stays forced to `provenance == "public"` and is likewise a
declaration. A reader who needs the claim checked has to check it against the named source.

## Where a row's subject prompt went (2026-10-02)

From schema `"16"` every runtime and quality row carries `subject_egress`: `none` when the
subject prompt was served on the machine, else the id of the cloud provider that received
it (`mistral`, `google`). A runtime row always records `none`, since the runtime benchmark
serves its prompt from the local llama-server only. The writer gate refuses a row without
the field or with it `null`, refuses a runtime row recording anything but `none`, and
refuses a quality row whose value contradicts its
`provider`: a `local` row recording a provider, a cloud row recording `none` or another
provider's id.

The field describes the subject call alone. A judged row also sends its item and the
subject's output to the judges, and that is recorded, unchanged, in its `judge_egress`
block: a local subject judged by two cloud judges carries `subject_egress` `none` beside a
`judge_egress` saying the item left the machine. Read both before calling a row
"nothing left the machine".

No committed row carries the field: every row in this directory predates `"16"`, is read
under its own version and is never back-filled with `none`. The reference rows carry it
from their next regeneration, which nothing has scheduled yet.

## A batch's retry budget, and partial batches (2026-10-02)

From schema `"17"` every quality row carries `retry_budget`, the retry total each cloud
provider's calls in its batch drew from (derived from the batch's item count, `{}` for a
batch with no cloud call), and `partial_failure`: `null` on a row whose batch was complete
when it was written, else the provider, item and reason of the call that stopped it. A
partial row carries no suite-level score. A batch completed by `--resume` holds its partial
rows from the failed invocation beside the completing rows, which carry the whole batch's
score; read the score off a row whose `partial_failure` is `null`. Cost and token totals on
each segment cover that invocation's calls only.

No committed row carries either field: every row in this directory predates `"17"`, is read
under its own version and is never back-filled.

## Each item's own tokens and first-token time (2026-10-02)

From schema `"18"` every quality row carries its item's own generation figures:
`item_tokens_in`, `item_tokens_out`, `item_ttft_ms` (the engine's `timings.prompt_ms` for
that one request, `item_ttft_source: server_reported`) and `item_prompt_tokens_cached`
(the engine's `timings.cache_n`). Each is a value or null with its `*_null_reason`, never
a zero: `not_reported_by_engine`, `not_reported_by_provider` (a cloud row has its
provider's token counts but no TTFT) or `no_generation_call`.

Read them as what they are. `item_measurement_kind: single_generation` says each is one
generation of one item, not the runtime protocol's Methodology 6 figure: no warm-up
exclusion, no repetitions, and a different prompt per item; compare it only with another
row's `item_ttft_ms`, never with a runtime row's `ttft_ms`. llama-server reuses a prompt
prefix shared with the previous request, so `item_ttft_ms` covers only the uncached tokens;
a variant that adds a fixed instruction has it cached after the first item, and
`item_prompt_tokens_cached` shows it. `item_first_in_batch` marks the batch's first
generation, served by a freshly launched server; exclude it with
`--reference-where item_first_in_batch=false --candidate-where item_first_in_batch=false`.

`wave-local-ai-v2-compare --quantity item_tokens_out` (or `item_tokens_in`, `item_ttft_ms`)
runs the Wilcoxon signed-rank test over the same item ids. Energy stays per batch:
`--quantity energy_kwh` publishes the two batch values and their difference as an
observation, because per-item energy on items of a few dozen tokens is below what the
tracker can resolve, so there is nothing to pair (owner decision Q24 (a)).

No committed row carries these fields: every row in this directory predates `"18"`, is read
under its own version and is never back-filled; a per-item comparison over them is refused
naming the absent field.

## Each batch's interval and what it could resolve (2026-10-02)

From schema `"21"` every quality row carries `score_interval`, one block per batch and
identical on every row of it: a 95% percentile bootstrap interval over 10 000 resamples on
the suite score (`suite`, resampled unstratified) and on each language cell (`by_language`,
resampled within its language), for the exact-match and graded scorers alike. Beside each
interval sits its minimum detectable effect, the interval's half-width read off the same
resample: the smallest difference that suite and scoring kind could have told from noise,
so "not distinguishable" is never read as "the same". A cell is its three values or none of
them and one reason: `zero_width` when every item scored the same (a suite at 1.0 or 0.0,
whose `[1.0, 1.0]` would read as certainty), `no_items` for an empty language cell. A failed
generation resamples as its zero. The block records the seed, the generator (`CPython
random.Random`, major.minor version) and the draw procedure
`stdlib-getrandbits-percentile/1`, defined in `score_interval.py` (items by `item_id`, one
freshly seeded generator per cell, `getrandbits` draws with rejection, `math.fsum` means,
type-7 percentile interpolation), so `score_interval.replay` reproduces it bit for bit from
the rows alone. A partial batch and a judge-probe row carry `null`, as their scores are.

No committed row carries the block: every row here predates `"21"` and is never
back-filled. The figures below are an analysis over the committed
`classification-support-routing` rows of `quality-reference.jsonl`, computed by the new code
(seed `20261002`) and not written onto them; the computation, which also checks the three
batch invariants and the replay on an in-memory copy, is
`aidd_docs/tasks/2026_10/2026_10_01_quality-batch-interval-and-what-it-could-resolve/evidence/`.

| Run | Model | Accuracy (n=20) | 95% interval | Minimum detectable effect |
| --- | ----- | --------------- | ------------ | ------------------------- |
| `5e13166d` | Qwen3.6-35B-A3B (local) | 0.80 | [0.600, 0.950] | 0.175 |
| `5e13166d` | mistral-small-2603 | 0.95 | [0.850, 1.000] | 0.075 |
| `d20afbda` | Qwen3.6-35B-A3B (local) | 0.80 | [0.600, 0.950] | 0.175 |
| `d20afbda` | mistral-small-2603 | 0.90 | [0.750, 1.000] | 0.125 |

Per language the cells hold 10, 5 and 5 items (EN, FR, DE). Of the twelve cells, eight
scored 1.0 and publish `zero_width` rather than an interval; the four defined ones are wide:
Qwen3.6 EN 0.60 [0.300, 0.900] in both runs, mistral DE 0.80 [0.400, 1.000] and 0.60
[0.200, 1.000]. On 20 items the local model's interval spans 35 points, and the two
models' intervals overlap in both runs. The interval qualifies each score on its own;
whether two scores differ is the paired test's question, not the overlap's, and the next
section explains why the committed pairs publish no paired test.
## Every row names its engine, and the fiche hashes it (2026-10-02)

From schema `"22"` every runtime row and every local quality row carries `engine_id` and
`engine_build`: the inference engine that produced it, as the tracked engine registry
(`aidd_docs/roster/engines.json`) names it, and the build the binary reported at launch
(a live probe; `null` when it cannot be read). A cloud subject's quality row carries
`engine_id` `not_applicable` and a null build: no local engine produced it. The registry
holds one engine today, `llama.cpp`, the reference; its configuration defaults are each
marked `declared` (read off `llama-server --help` for b10537) or `engine_reported` (read
off `/props`).

The fiche those rows cite is hashed under a second projection. Projection `"1"` is the
one every committed fiche was written under (`llama_cpp_build` among its ten keys);
projection `"2"` replaces it with `engine_id`, `engine_build` and `engine_config_hash`,
the SHA-256 of the launch flag list with the model path replaced by `roster:<entry id>`
and `--host` / `--port` removed. The raw `flags` stay on the fiche as evidence, outside
both projections. Which projection a fiche is verified under is decided by the
`schema_version` of the row citing it (`row_contract.fiche_projection_for`), never by a
key the fiche happens to lack: the committed fiches keep verifying under `"1"` with no
file edited, and a new fiche missing an engine key is `edited`, not an old fiche.

The engine fields replace `llama_cpp_build` among the runtime verdict's blocking fields.
A committed reference fiche carries no engine field, so a run today against
`runtime-reference.jsonl` is `not_comparable` naming `engine_build` and `engine_id`,
never `reproduced` on a `llama_cpp_build` no row tied to an engine. That holds until the
bundle is republished under this epic's final schema; it is not back-filled.

## Paired comparisons: both committed pairs are refused (2026-10-02)

Superseded on 2026-10-04 with the schema-"7" rows they compare: the records named here
are now in `comparisons.schema-7/`, unedited, and their rows in
`quality-reference.schema-7.jsonl` (the `rows_source` they record,
`aidd_docs/results/quality-reference.jsonl`, is where those rows were published then).

`comparisons/` holds the comparison records `wave-local-ai-v2-compare` writes over this
bundle. They are derived artifacts, not a sixth input, and none is ever rewritten. The two
records below are `record_version` `"1"`: each is a family of one comparison (its
Holm-adjusted p stated equal to its raw p), names its reference and candidate by `run_id`
plus the row field that selects each side within the run, and holds either a paired test
chosen by scoring kind (McNemar's exact test for `correct`, Wilcoxon signed-rank for
`item_score`) or a refusal naming every field that makes the sides incomparable. Both are
now superseded by the family record of the next section and kept unchanged;
`tests/test_comparison.py` checks each still hashes to its own `family_id`.

The bundle holds two pairable comparisons, each `Qwen3.6-35B-A3B` (reference) against
`mistral-small-2603` (candidate) over the same 20 items of
`classification-support-routing@2`, both sides sharing one `run_id`:

```
uv run wave-local-ai-v2-compare --reference <run_id> --reference-where model_id=Qwen3.6-35B-A3B \
    --candidate <run_id> --candidate-where model_id=mistral-small-2603
```

| Run | Record | Comparison | Verdict |
| --- | --- | --- | --- |
| `5e13166d` | `classification-support-routing@2.model.d4641d06a525.json` | refused: `thinking_policy` absent on both sides | `not comparable` |
| `d20afbda` | `classification-support-routing@2.model.2ef9fd3581d2.json` | refused: `thinking_policy` absent on both sides | `not comparable` |

**No p-value is published for either pair, and that refusal is the evidence.** These rows
are `schema_version` `"7"` and predate `thinking_policy`, one of the four generation
constraints Methodology 3 requires identical across compared models. Two unknown values
never count as a match (Methodology 8, applied to comparability by the owner's answer on
2026-10-01), so the command refuses rather than assume both batches ran under the same
policy. Each record still carries the fields on which the two sides actually differ,
computed from the rows: `endpoint`, `model_id`, `prompt_template_hash`,
`prompt_template_id`, `provider` and `sampling`, all of them the `model` dimension's own.

The arithmetic the epic states for these pairs is reproduced, but by a test, not by a
published record: with `thinking_policy` supplied to the same rows, run `5e13166d` gives 1
item only Qwen got right and 4 only mistral got right, McNemar exact p = 0.375, and run
`d20afbda` gives 2 and 4, p = 0.6875 (published as 0.688 in the epic). Both read `not
distinguishable` at alpha 0.05: a 15-point accuracy gap on 20 items is not
distinguishable from noise. Once the bundle is regenerated with `thinking_policy` on
every row, the same command over the new pairs publishes their tests.

### One family record holds both pairs (2026-10-02)

A multiplicity correction means nothing until the family is declared, so the unit published
is the family, not the pair (PRD Methodology 24). One invocation of the command writes one
immutable record holding every comparison it ran, the family definition (one suite crossed
with one compared dimension, closed at analysis time), its size, how many members were
tested and how many refused, and each member's Holm-adjusted p computed over exactly those
members, with the raw p beside it and the verdict read against the adjusted p. Holm runs
over every member that was not refused, so `multiplicity_correction.adjustment_size`
equals `tested_count`: a tested member whose p is left null with a named reason enters as
p = 1 (it can only raise the others' adjusted p) and keeps its own adjusted p null; a
refused member carries no p and enters no count. A family that grows is a new record
listing the ids it `supersedes`; the command finds the current record of the same
definition in `comparisons/` itself. A family only grows: a declaration that leaves out
any comparison the current record holds is refused (exit 1, nothing written, the missing
comparisons named), so no pair can be re-published alone, outside the adjustment it was
first counted in. A re-run over the same bundle and declaration returns the published
record byte for byte, and says which record supersedes it if it is no longer current. A
change of `--alpha` alone, over the same comparisons, also writes a superseding record:
the family is the same comparisons, read at a different level.

```
uv run wave-local-ai-v2-compare --comparisons <declaration.json>
```

The declaration is a JSON array of `{"reference": {"run_id", "where"}, "candidate": {...}}`;
the one used here is
`aidd_docs/tasks/2026_10/2026_10_01_comparison-family-adjusted-and-superseded/evidence/classification-support-routing@2.model.comparisons.json`.

| Record | Family | Size | Tested | Refused | Holm over | Supersedes |
| --- | --- | --- | --- | --- | --- | --- |
| `classification-support-routing@2.model.1e1658cbe073.json` | `classification-support-routing@2` x `model` | 2 | 0 | 2 | 0 | `d4641d06a525`, `2ef9fd3581d2` |

Both members are still refused on `thinking_policy`, for the reason above, so the record
adjusts nothing: it publishes the family, not a finding. `tests/test_comparison.py`
recomputes it from `quality-reference.jsonl` with only the two records it supersedes on
file and requires identical bytes.

## The leader set: the local models not distinguishable from the best (2026-10-02)

Superseded on 2026-10-04 with the schema-"7" rows it was derived from: the records named
here are now in `leader-sets.schema-7/` and `comparisons.schema-7/`, unedited. No leader
set has been derived from the republished bundle yet.

The leader set of a suite on a machine class is a published derived output (PRD Non-goals,
owner answer Q42 (a)): the best local subject plus every local subject the paired tests
cannot tell from it. It is its own record in `leader-sets/`, written by the analysis
command, never a row field and never computed at read time, so no published row is
rewritten when a set changes.

```
uv run wave-local-ai-v2-compare --leader-sets
```

The command groups the local subjects (a `run_id` and its `model_id`; cloud subjects are
never members) by suite id and version and by machine class, read from each row's fiche:
`machine_id`, `compute_mode`, `cpu`, `ram_gb`, `gpu_name`, `os`. A field the fiche does not
carry is listed in `grouping_not_recorded`; today's fiches carry neither `machine_id` nor
`compute_mode` (story `a-gpu-run-and-a-cpu-only-run-never-share-a-fiche` adds them), so a
`gpu` and a `cpu_only` fiche of one machine fall into two groups as soon as fiches record
the mode. The reference is the subject with the highest published suite score
(`suite_accuracy` or `suite_score`); a tie names the subject whose `(run_id, model_id)`
sorts first, and the record states the rule and every subject tied at the top. Every other
local subject is compared against it inside the suite's `model` family, which the command
grows by those comparisons (keeping every comparison it already held), so Holm runs over
the whole closed family. A subject reads `member` on `not distinguishable`, `excluded` on
`distinguishable`, and `not compared` on any `not comparable` (a refusal, naming the
refused fields, or an observation, naming its reason); one `not compared` subject makes
the record `incomplete`. A group of one local subject is a set of one stating that no
comparison ran. A changed group is a new record superseding the old by
`leader_set_id`; a re-run over the same bundle reports every record `unchanged`.

| Record | Group | Reference | Members | Excluded | Not compared | Family |
| --- | --- | --- | --- | --- | --- | --- |
| `leader-sets.schema-7/classification-support-routing@2.053c65354ff8.json` | `classification-support-routing@2`, the RTX 3060 laptop (`machine_id`, `compute_mode` not recorded) | `5e13166d` `Qwen3.6-35B-A3B`, 0.8 (tied with `d20afbda`) | 1 | 0 | 1 (`thinking_policy` absent) | `837e5355b954` |
| `comparisons.schema-7/classification-support-routing@2.model.837e5355b954.json` | the family grown by the leader comparison: 3 members, 0 tested, 3 refused | | | | | supersedes `1e1658cbe073` |

The bundle's two local batches are the same model at the same score, and their comparison
is refused on `thinking_policy` like both committed pairs, so the first real leader set
names one member and says it is incomplete. The three earlier family records are
unchanged. `tests/test_leader_set.py` recomputes the leader-set record from
`quality-reference.jsonl` with the family it cites removed from file and requires
identical bytes. Command output:
`aidd_docs/tasks/2026_10/2026_10_01_local-models-not-distinguishable-from-the-best/evidence/leader-sets-output.txt`.
The export flattens these records into its fifth table, `comparison_records.csv` (see "The
bundle as five flat tables" above).

## Terse output against baseline: not distinguishable, and no shorter (2026-10-03)

One campaign cell pair on the laptop (`laptop-mobile-gpu`, `gpu`, pinned
build `b10537`, `llama.cpp`), campaign `terse-output-laptop`: roster entry
`qwen3-0.6b-q8`, suite `classification-support-routing@4`, `baseline` v1
(run `9a68cbaf`) against `output_compressed` v1 (run `13ade3c5`), local only,
schema "27". Both cells filled, all 20 items in each, every
`output_compressed` row `prompt_variant_noop: false`.

| Arm | Accuracy | Mean output tokens per item | Unparseable |
| --- | --- | --- | --- |
| `baseline` | 0.45 (9/20) | 2.0 | 0 |
| `output_compressed` | 0.30 (6/20) | 2.0 | 0 |

`wave-local-ai-v2-compare --dimension prompt_variant`: McNemar exact, 6 both
right, 11 both wrong, 3 right under `baseline` only, 0 under the variant
only, p = 0.25, direction `reference_higher`, **verdict `not
distinguishable`**; differing fields `prompt_variant_id` alone (both arms are
version "1"), no confound. The output-token comparison
(`--quantity item_tokens_out`, Wilcoxon) is `not distinguishable` with all 20
differences zero: this model already answers with one label word, so the
instruction had nothing to cut. The three lost items (`account-02`,
`account-de-02`, `other-01`) were each relabelled `technical`, not left
unparseable. Read it as: on this suite and model, a terse-output instruction
saves no tokens and, if anything, costs accuracy, at a sample too small to
say so. The records, rows, fiche and logs are in
`aidd_docs/tasks/2026_10/2026_10_02_terse-output-variant/evidence/`; no row
here entered a committed store.

The first run of this pair also surfaced a defect, fixed in the same change:
`comparison.py` counted `score_interval` as a configuration field, so any two
batches that scored differently were published as an observation naming it.

## A grammar-constrained output against baseline: identical answers (2026-10-03)

One campaign cell pair on the laptop (`laptop-mobile-gpu`, `gpu`, pinned
build `b10537`, `llama.cpp`), campaign `constrained-output-laptop`: roster
entry `qwen3-0.6b-q8`, suite `classification-support-routing@4`, `baseline`
v1 (run `962f939a`) against `constrained_output` v1 (run `6d162577`), local
only, schema "28". Both cells filled, 20 items each. Every
`constrained_output` row names `constraint_mechanism: gbnf` and
`constraint_grammar_hash` `302f90eb...` (the grammar
`root ::= "account" | "billing" | "other" | "technical"`); every `baseline`
row names `none`. A live request on the same build first showed the
per-request `grammar` field is applied on `/v1/chat/completions`: a grammar
admitting only `billing` turned a `technical` answer into `billing`.

| Arm | Accuracy | Mean output tokens per item | Unparseable |
| --- | --- | --- | --- |
| `baseline` | 0.45 (9/20) | 2.0 | 0 |
| `constrained_output` | 0.45 (9/20) | 2.0 | 0 |

**Share of baseline outputs outside the declared format: 0 of 20 (0%).** A
classification row does not carry the raw answer, so the baseline requests
were replayed on the same build, model, launch flags and sampling: every
answer was a bare lowercase label, each equal to its row's
`predicted_label`. `wave-local-ai-v2-compare --dimension prompt_variant`:
McNemar exact, 9 both right, 11 both wrong, no discordant item (p null,
reason `no_discordant_pairs`), **verdict `not distinguishable`**;
differing fields `constraint_grammar_hash`, `constraint_mechanism` and
`prompt_variant_id`, no confound. Read it as: this model already answers
inside the format, so a grammar on this suite has nothing to correct; the
variant's effect, if any, needs a model or a suite where baseline strays. The
records, rows, replay and logs are in
`aidd_docs/tasks/2026_10/2026_10_02_constrained-output-variant/evidence/`;
the run's fiche is byte-identical to `73ec536e...` already tracked by the
named-run-profiles evidence. No row here entered a committed store.

## The use-case coverage record, and why it is not here yet

`use-case-coverage.json` is the published coverage record: one entry for each
of the PRD's nine task use cases and one for multilingual EN/FR/DE coverage,
each in exactly one declared state -- `exercised` (naming the suite ids that
exercise it), `covered-by-dimension` (naming the suite ids that carry it;
multilingual is a language dimension of the classification, translation and
rewriting suites) or `out-of-scope-this-release` (with its reason). The record
is declared as data in `src/wave_local_ai_v2/use_case_coverage.json`; a state
is never inferred from which suites happen to be registered.

`uv run python -m wave_local_ai_v2.use_case_coverage` writes it here, and only
when every entry resolves: an entry missing, an entry with no state, a named
suite id the suite registry does not resolve, or an out-of-scope entry with no
reason refuses the whole record, names every failing entry on stderr, exits
`1` and writes nothing. No partial record is ever published.

The file is therefore absent today, deliberately. Run against the committed
record, the command refuses naming eight entries: the six use cases with no
suite yet (document comparison, code generation, agentic planning, agentic
tool calling, web research, RAG answer generation), text rewriting, whose
`rewriting-business-email` suite is not registered yet, and multilingual,
which names that same suite. That refusal is the current coverage reading
(`aidd_docs/tasks/2026_10/2026_10_01_use-case-coverage-state-or-refusal/evidence/coverage-refusal.txt`);
the record appears here once the last entry resolves, and until then the
overview's coverage absence above stays true.

## Roster composition: every class spans two families (2026-10-04)

Methodology 13's composition rule is a command, not prose:
`uv run wave-local-ai-v2-composition-check [--roster <models.json>]`
(`composition_check.py`). It reads the roster, classes every entry by its
declared `size_class`, and reports per class the families it spans
(`roster.family_of`, so the flagship resolves through the in-code fallback
like any row does), whether dense and MoE are both present, the
single-family-ladder label and the MoE declaration; then per entry its total
parameters, its bytes on disk, its licence id, whether client-side commercial
use is permitted and the date the terms were read.

**What a size class is.** Four classes, banded on total parameters (owner
answer Q10 (a)): below 1B is `~0.5B`, 1B to below 3B is `~2B`, 3B to below 6B
is `~4B`, 6B and up is `~8B-and-up`. The edges are configuration
(`roster.SIZE_CLASS_BANDS`) and revisable after the first full-roster run;
moving one is a re-class, not a rewrite of the check. Bytes on disk are the
footprint published beside the class and are never banded: whether an entry
fits a given machine is the machine epic's profiles' to say, not the class's.
Each entry declares its class, `architecture.total_params` (read off the
GGUF's tensors) and `bytes_on_disk` (read off the file), so the classing is
checked against the entry rather than asserted by its author. The roster's
`size_classes` block carries one declaration per class: whether it is a
single-family ladder, whether a MoE was sought, which entry represents it,
and the reason when none does.

**What it refuses: silence, not a single-family roster.** It exits `1`
naming the class or the entry when a class spans one family without the
ladder label, when a class has no MoE and no recorded reason, when an entry
has no resolvable family, no size class, no total parameters, no bytes on
disk or no licence block, or when an entry's declared class disagrees with
the band its total parameters fall in. It also names a ladder label on a
class spanning two families and a MoE declaration that disagrees with the
class's entries. A class spanning two families passes; a labelled
single-family ladder passes; a class with no entries publishes nothing and
is not failed. Exit `2` means the roster file could not be loaded at all.

**It failed at first, which was the honest state.** Run on the shipped roster
(`roster_version` 4) before any new entry was authored, it reported four
classes, each spanning exactly one family (`qwen`), none labelled, and the
three dense classes with no MoE searched for and no reason recorded. The
roster is deliberately not labelled here: the search that would justify a
ladder label or a MoE absence is the per-class stories' work. A check that
passed on this roster would not be checking the rule. Since `roster_version` 7
the `~0.5B` class passes, since `roster_version` 8 the `~2B` class, and since
`roster_version` 9 the `~4B` class, and since `roster_version` 10 the top
class (their sections below): the check now passes on the shipped roster.
`tests/test_composition_check.py` fails when the block below drifts from the
command's output.

<!-- composition-check:start -->
```text
Roster composition: aidd_docs/roster/models.json (roster_version 10)
Size classes, banded on total parameters: ~0.5B < 1,000,000,000 <= ~2B < 3,000,000,000 <= ~4B < 6,000,000,000 <= ~8B-and-up
  ~0.5B: 2 entries; families: ibm, qwen; dense: yes; MoE: no; label: none; MoE sought: yes; MoE absence reason: sought, none found: no MoE GGUF below 1B total parameters in the epic's candidate families (Granite, LFM2, Gemma 4, Ministral, Phi); the smallest MoE the search found is Granite 3.1 1B-A400M (1,334,628,352 total, ~2B) (GGUF spike which-candidate-ggufs-exist-per-size-class-and-does-the-pinned-build-load-them, read 2026-10-02)
  ~2B: 3 entries; families: ibm, liquid, qwen; dense: yes; MoE: yes (granite-3.1-1b-a400m-instruct-q8); label: none; MoE sought: yes; MoE absence reason: n/a
  ~4B: 2 entries; families: ibm, qwen; dense: yes; MoE: yes (granite-3.1-3b-a800m-instruct-q4km); label: none; MoE sought: yes; MoE absence reason: n/a
  ~8B-and-up: 2 entries; families: google, qwen; dense: yes; MoE: yes (qwen3.6-35b-a3b-ud-iq4xs); label: none; MoE sought: yes; MoE absence reason: n/a
Entries
  qwen3.6-35b-a3b-ud-iq4xs: ~8B-and-up; family qwen; moe; 34,660,610,688 total params; 17,730,509,792 bytes on disk; licence Apache-2.0, client commercial use yes, read 2026-10-02
  qwen3-0.6b-q8: ~0.5B; family qwen; dense; 596,049,920 total params; 639,446,688 bytes on disk; licence Apache-2.0, client commercial use yes, read 2026-10-02
  qwen3-1.7b-q8: ~2B; family qwen; dense; 1,720,574,976 total params; 1,834,426,016 bytes on disk; licence Apache-2.0, client commercial use yes, read 2026-10-02
  qwen3-4b-q4km: ~4B; family qwen; dense; 4,022,468,096 total params; 2,497,280,256 bytes on disk; licence Apache-2.0, client commercial use yes, read 2026-10-02
  granite-4.0-h-350m-q8: ~0.5B; family ibm; dense; 340,332,224 total params; 366,195,616 bytes on disk; licence apache-2.0, client commercial use yes, read 2026-10-04
  lfm2.5-1.2b-instruct-q8: ~2B; family liquid; dense; 1,170,340,608 total params; 1,246,253,888 bytes on disk; licence lfm1.0, client commercial use no, read 2026-10-04
  granite-3.1-1b-a400m-instruct-q8: ~2B; family ibm; moe; 1,334,628,352 total params; 1,422,239,776 bytes on disk; licence apache-2.0, client commercial use yes, read 2026-10-04
  granite-3.1-3b-a800m-instruct-q4km: ~4B; family ibm; moe; 3,298,793,472 total params; 2,016,888,384 bytes on disk; licence apache-2.0, client commercial use yes, read 2026-10-04
  gemma-4-12b-it-iq4xs: ~8B-and-up; family google; dense; 11,907,350,576 total params; 6,375,734,080 bytes on disk; licence apache-2.0, client commercial use yes, read 2026-10-04
PASS: every published size class spans two families or says it does not
```
<!-- composition-check:end -->

**When to run it.** Before a roster table is published, run the check and
publish its output beside the table; a class it names is either fixed in the
roster or published with the failure stated. It is not part of the merge gate
or CI: it was kept out while the shipped roster was expected to fail it, and
wiring it in now that it passes (`roster_version` 10) is open work, not done
here.

### The ~0.5B class: Granite 4.0 H 350M beside Qwen3-0.6B (2026-10-04)

**The class spans two families.** `granite-4.0-h-350m-q8` (IBM, `granitehybrid`,
dense, 340,332,224 total parameters, 366,195,616 bytes on disk) entered the roster
at `roster_version` 7 from its candidate-gate pass record
(`aidd_docs/roster/candidate-records.jsonl`, 2026-10-04) beside `qwen3-0.6b-q8`, and
completed both suites on the laptop. The search stops there (owner answer Q127 (a)):
one non-Qwen entry that passed the gate and completed both suites suffices, so the
class seeks no third family and is not a single-family ladder.

| Candidate, in gate order | Pin | Outcome |
| --- | --- | --- |
| Granite 4.0 H 350M (`granitehybrid`) | `ibm-granite/granite-4.0-h-350m-GGUF@a864f823cce6e6048b5752e2816fe7a23987d790`, `granite-4.0-h-350m-Q8_0.gguf` | **passed** every step; entered |
| Granite 4.0 350M (`granite`) | `ibm-granite/granite-4.0-350m-GGUF@b8208a86a58427e1739265318028eb5895b74bf2` | not reached: class stopped at `granite-4.0-h-350m-q8` |
| LFM2.5-350M (`lfm2`) | `LiquidAI/LFM2.5-350M-GGUF@657e078c94084481950a2d555a941481f715536b` | not reached: class stopped at `granite-4.0-h-350m-q8` |

No candidate was refused or deferred, so the pinned build `b10537` held and no
build-upgrade question arises. `LFM2.5-230M` was never a candidate (owner answer
Q107 (a)).

**Quant.** Both entries are `Q8_0`: IBM ships the class's Qwen quant, so the
class compares families, not quants.

**Licences.** Granite 4.0 H 350M: `apache-2.0` (the hub's identifier, read off the
GGUF repository's card at its pinned revision, which carries no LICENSE file),
client-side commercial use permitted. Had LFM2.5-350M been reached, it would have
entered with `client_commercial_use: false` (its declaration says so): section 5 of
the LFM Open License v1.0 conditions commercial use on a legal entity below USD 10M
annual revenue, read against a user above that threshold; the licence bans no
publication of benchmark results, so the gate's licence step would pass either way.

**MoE.** Sought, none found: the GGUF spike's search found no MoE GGUF below 1B
total parameters in the epic's candidate families; the smallest it found is
Granite 3.1 1B-A400M, in `~2B`. The class's declaration records that reason, so the
class is dense-only by nature, not by omission.

**The GGUF spike's architectures at this class** (owner answer Q125 (a)):

- `granitehybrid`: loaded under `b10537`; closed by the pass record of
  `granite-4.0-h-350m-q8` (`observed`: `llama_cpp_build` `b10537`,
  `chat_template_hash` `9524df67b77a7b25a2dfee898f75b316a157eb9d855b51e32aeac79d7c8a83ce`,
  `thinking` `{"declared": "none", "verified": true}`).
- `granite`: not reached: class stopped at `granite-4.0-h-350m-q8`.
- `lfm2`: not reached: class stopped at `granite-4.0-h-350m-q8`.

**The new rows.** Both runs on `laptop-mobile-gpu`, `compute_mode` `gpu`, profile
`granite-4.0-h-350m-q8@laptop-mobile-gpu/gpu` (`-ngl 99`, the declared value,
launched; `-t 8`; no override), `thinking_policy` `disabled` with the entry's `none`
control (no switch sent), fiche `5ce2bf21...`. They ran from the commit that added
the entry, on a clean tree: every row carries `commit_sha`
`8852bf0252cd90ca08a6e0473d998c282b60dc34` (`tree_dirty: false`).

| Suite | `run_id` | Rows | Score [95% interval] | `en` | `fr` | `de` |
| --- | --- | --- | --- | --- | --- | --- |
| `classification-support-routing@5` | `cb8cb4ffa7754de4b567e3f901953706` | 20 | accuracy **0.50** [0.30, 0.70] | 0.50 (n=10) | 0.40 * (n=5) | 0.60 * (n=5) |
| `translation-business-short-form@4` | `be0dda5eeaa24862ad4ffbd11d10d61e` | 21 | chrF **0.484** [0.358, 0.614] | 0.328 * (EN->FR) | 0.326 * (FR->DE) | 0.799 * (DE->EN) |

`*` = `indicative`. The bundle now holds 121 quality rows: the 80 of the 2026-10-04
regeneration and these 41, promoted into `machines/laptop-mobile-gpu/` and merged.
Every classification answer parsed; nine of the ten misrouted items were answered
`account`, and no item was routed to `billing`. No `Qwen3-0.6B` quality row at these
suite versions is in the bundle, so the class's side-by-side reading rests on the
earlier, superseded tables below (classification `@3` 0.45, translation `@2` 0.5121),
not on rows of the same suite version.

**Finding: the rows contradict the EN/FR/DE claim on output into French and German.**
The entry claims `en`, `fr` and `de` (the base model card's "English, German, Spanish,
French, ..."). Translating into French, 4 of 7 items (`en-fr-01`, `-02`, `-03`, `-07`)
came back in English; translating into German, none of 7 items is German alone: two
came back in English (`fr-de-02`, `-05`), one is the single word "Not" (`fr-de-06`),
and four mix French words into German (`fr-de-01`, `-03`, `-04`, `-07`). Into English
it scores 0.799. The claim stays on the entry, as the epic decides; this is a finding
about the model at this size, not a reason to remove it.

### The ~2B class: LFM2.5-1.2B-Instruct and Granite 3.1 1B-A400M beside Qwen3-1.7B (2026-10-04)

**The class spans three families, dense and MoE.** `lfm2.5-1.2b-instruct-q8`
(Liquid, `lfm2`, dense, 1,170,340,608 total parameters, 1,246,253,888 bytes on disk)
and `granite-3.1-1b-a400m-instruct-q8` (IBM, `granitemoe`, MoE of 32 experts,
1,334,628,352 total parameters, 1,422,239,776 bytes on disk) entered the roster at
`roster_version` 8 from their candidate-gate pass records
(`aidd_docs/roster/candidate-records.jsonl`, 2026-10-04) beside `qwen3-1.7b-q8`.
LFM2.5-1.2B-Instruct, the first candidate in gate order, passed, so no further dense
candidate was tried (owner answer Q127 (a): one non-Qwen family suffices); the MoE
candidate was still taken through the gate, because the story's MoE question is
answered only by its outcome. It passed too, so the class holds a MoE and is not a
single-family ladder.

| Candidate, in gate order | Pin | Outcome |
| --- | --- | --- |
| LFM2.5-1.2B-Instruct (`lfm2`) | `LiquidAI/LFM2.5-1.2B-Instruct-GGUF@8ed288026e23958ad9dfa92d53ed773a8eee7125`, `LFM2.5-1.2B-Instruct-Q8_0.gguf` | **passed** every step; entered |
| Granite 3.1 1B-A400M Instruct (`granitemoe`, MoE) | `bartowski/granite-3.1-1b-a400m-instruct-GGUF@940d2e1f9f65330615c7c8e980e6c5ac73d3360c`, `granite-3.1-1b-a400m-instruct-Q8_0.gguf` | **passed** every step; entered as the class's MoE |
| Granite 4.0 H 1B (`granitehybrid`) | `ibm-granite/granite-4.0-h-1b-GGUF@c2cb1972f511add21f3bae244990b8ff3a3ffb23` | not tried: a non-Qwen family had passed, so further dense candidates are skipped |
| Granite 4.0 1B (`granite`) | `ibm-granite/granite-4.0-1b-GGUF@b27c2fe3f211b7f44e80fa620177aea371099aaa` | not tried: as above |

No candidate was refused or deferred, so the pinned build `b10537` held and no
build-upgrade question arises. `LFM2.5-2.6B` was never a candidate: it always thinks
and its template has no switch (owner answer Q107 (a)).

**Quant.** All three entries are `Q8_0`: both publishers' files ship the class's Qwen
quant, so the class compares families, not quants. IBM ships no GGUF of Granite 3.1
1B-A400M; the file is bartowski's quantization of IBM's weights (made with llama.cpp
`b4381`, per its card), a packager difference stated here rather than a quant one.

**Licences.** LFM2.5-1.2B-Instruct: `lfm1.0` (the LFM Open License v1.0, read off the
GGUF repository's LICENSE at its pinned revision), published with
`client_commercial_use: false`: section 5 conditions commercial use on a legal entity
below USD 10M annual revenue, read against a user above that threshold. The licence
bans no publication of benchmark results, so the gate's licence step passed either
way. Granite 3.1 1B-A400M: `apache-2.0` (the hub's identifier, read off bartowski's
card at its pinned revision, which carries no LICENSE file), client-side commercial
use permitted.

**MoE.** Present: the gate read `granitemoe.expert_count` 32 off the file's header, so
the entry is `moe`, and the class's declaration names it (`moe_sought: true`,
`moe_entry: granite-3.1-1b-a400m-instruct-q8`). It fits the laptop's 6 GB GPU whole
and launches with no `--n-cpu-moe`.

**The GGUF spike's architectures at this class** (owner answer Q125 (a)):

- `granitemoe`: loaded under `b10537`; closed by the pass record of
  `granite-3.1-1b-a400m-instruct-q8` (`observed`: `llama_cpp_build` `b10537`,
  `chat_template_hash` `22da301945ac6b617a8835d435cbbdc780c0ac08d69c07e1e17e6c6799eed800`,
  `thinking` `{"declared": "none", "verified": true}`).
- `lfm2`: loaded under `b10537`; closed by the pass record of
  `lfm2.5-1.2b-instruct-q8` (`observed`: `llama_cpp_build` `b10537`,
  `chat_template_hash` `f05bf4b967dc993bdc7a2fe6e43759ee218eb0eb340d68b063e1c4f8ad148176`,
  `thinking` `{"declared": "none", "verified": true}`).
- `granitehybrid`: already closed at `~0.5B` (pass record of `granite-4.0-h-350m-q8`).
- `granite`: not reached: class stopped at `granite-3.1-1b-a400m-instruct-q8`.

**The new rows.** All four runs on `laptop-mobile-gpu`, `compute_mode` `gpu`, each
under its entry's profile (`<entry_id>@laptop-mobile-gpu/gpu`: `-ngl 99`, the declared
value, launched; `-t 8`; no override; no `--n-cpu-moe` for the MoE),
`thinking_policy` `disabled` with each entry's `none` control (no switch sent). They
ran from the commit that added the entries, on a clean tree: every row carries
`commit_sha` `5fc6901d573ad10848e03309ad1d6c44e1179f4b` (`tree_dirty: false`) and
`roster_version` 8. Fiches `53fa3307...` (LFM2.5) and `add6a317...` (Granite). Both
entries completed both suites with no failed item, so the search's stop condition
(owner answer Q127 (a)) holds.

| Entry | Suite | `run_id` | Rows | Score [95% interval] | `en` | `fr` | `de` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `lfm2.5-1.2b-instruct-q8` | `classification-support-routing@5` | `02d855b6b1b24edab26b6e32e59a9e26` | 20 | accuracy **0.85** [0.70, 1.00] | 0.80 (n=10) | 1.00 * (n=5) | 0.80 * (n=5) |
| `lfm2.5-1.2b-instruct-q8` | `translation-business-short-form@4` | `e6acc5a1051745ae80c325b3ce61fb32` | 21 | chrF **0.723** [0.647, 0.799] | 0.777 * (EN->FR) | 0.602 * (FR->DE) | 0.791 * (DE->EN) |
| `granite-3.1-1b-a400m-instruct-q8` | `classification-support-routing@5` | `7122bd3e67624735aad92dbcdb82f5be` | 20 | accuracy **0.60** [0.40, 0.80] | 0.70 (n=10) | 0.40 * (n=5) | 0.60 * (n=5) |
| `granite-3.1-1b-a400m-instruct-q8` | `translation-business-short-form@4` | `4db0b4be4cb54e43a16e2ecffa927387` | 21 | chrF **0.561** [0.497, 0.631] | 0.547 * (EN->FR) | 0.432 * (FR->DE) | 0.703 * (DE->EN) |

`*` = `indicative`. The bundle now holds 203 quality rows: the 121 before and these
82, promoted into `machines/laptop-mobile-gpu/` and merged. Every classification
answer parsed. LFM2.5-1.2B-Instruct misrouted three items (`billing-03` as
`account`, `technical-03` and `account-de-01` as `other`); Granite 3.1 1B-A400M
misrouted eight, four of them as `account`. No `Qwen3-1.7B` quality row at these
suite versions is in the bundle, so the class's side-by-side reading rests on the
earlier, superseded tables below (classification `@3` 0.60, translation `@2` 0.7107),
not on rows of the same suite version.

**No row contradicts the EN/FR/DE claims.** Both entries claim `en`, `fr` and `de`.
Every translation output of both is in its target language (French for EN->FR,
German for FR->DE, English for DE->EN); Granite's `fr-de-07` keeps one English
compound ("signed-document") inside a German sentence. The weakest reading is
Granite's French classification, 0.40 on five items, an indicative figure rather
than a contradiction. The claims stay on the entries either way, as the epic decides.

### The ~4B class: Granite 3.1 3B-A800M beside Qwen3-4B (2026-10-04)

**The class spans two families, dense and MoE.** `granite-3.1-3b-a800m-instruct-q4km`
(IBM, `granitemoe`, MoE of 40 experts, 3,298,793,472 total parameters, 2,016,888,384
bytes on disk) entered the roster at `roster_version` 9 from its candidate-gate pass
record (`aidd_docs/roster/candidate-records.jsonl`, 2026-10-04) beside `qwen3-4b-q4km`.
It was the first candidate in gate order (smallest download first) and is non-Qwen and
MoE at once, so its pass ends the search (owner answers Q127 (a) and Q128 (a)): no
further candidate was tried, and `mistral3`, `phi3` and `phimoe` were not reached.
Ministral and Phi stay the families Q12 names for the shortlist, not a requirement on
the class.

| Candidate, in gate order | Pin | Outcome |
| --- | --- | --- |
| Granite 3.1 3B-A800M Instruct (`granitemoe`, MoE) | `bartowski/granite-3.1-3b-a800m-instruct-GGUF@be9a36f042806cb586bc65556c527079782b78e0`, `granite-3.1-3b-a800m-instruct-Q4_K_M.gguf` | **passed** every step; entered as the class's second family and its MoE |
| Ministral 3 3B Instruct 2512 (`mistral3`) | `mistralai/Ministral-3-3B-Instruct-2512-GGUF@eb599d408350ea2bb60452cb86be7c7b2fc28227`, `Ministral-3-3B-Instruct-2512-Q4_K_M.gguf` | not tried: a non-Qwen MoE had passed, which answers both stop conditions |
| Phi-4-mini-instruct (`phi3`) | `unsloth/Phi-4-mini-instruct-GGUF@78eb92a46fc37e6b524df991ed9aca9bc6aa7b80`, `Phi-4-mini-instruct-Q4_K_M.gguf` | not tried: as above |
| Phi-tiny-MoE-instruct (`phimoe`, MoE) | `tripathyShaswata/Phi-tiny-MoE-instruct-GGUF@873ccb08cd3380ee2c08573d45267fac9a6cc81b`, `Phi-tiny-MoE-instruct-Q8_0.gguf` | not tried: the class's MoE question was already answered |

No candidate was refused or deferred, so the pinned build `b10537` held and no
build-upgrade question arises.

**Quant.** Both entries are `Q4_K_M`: bartowski ships the class's Qwen quant, so the
class compares families, not quants. IBM ships no GGUF of Granite 3.1 3B-A800M; the
file is bartowski's quantization of IBM's weights, a packager difference stated here
rather than a quant one.

**Licence.** `apache-2.0` (the hub's identifier, read off bartowski's card at its
pinned revision, which carries no LICENSE file), client-side commercial use permitted.

**MoE.** Present: the gate read `granitemoe.expert_count` 40 off the file's header, so
the entry is `moe`, and the class's declaration names it (`moe_sought: true`,
`moe_entry: granite-3.1-3b-a800m-instruct-q4km`). Its gate load ran with the declared
launch block (`-ngl 99`, 32,768-token context, no `--n-cpu-moe`) on the laptop's 6 GB
GPU.

**The GGUF spike's architectures at this class** (owner answer Q125 (a)):

- `granitemoe`: already closed at `~2B` (pass record of
  `granite-3.1-1b-a400m-instruct-q8`); loaded again here (pass record of
  `granite-3.1-3b-a800m-instruct-q4km`: `llama_cpp_build` `b10537`,
  `chat_template_hash` `22da301945ac6b617a8835d435cbbdc780c0ac08d69c07e1e17e6c6799eed800`,
  `thinking` `{"declared": "none", "verified": true}`).
- `mistral3`: not reached: class stopped at `granite-3.1-3b-a800m-instruct-q4km`.
- `phi3`: not reached: class stopped at `granite-3.1-3b-a800m-instruct-q4km`.
- `phimoe`: not reached: class stopped at `granite-3.1-3b-a800m-instruct-q4km`.

**The new rows.** Both runs on `laptop-mobile-gpu`, `compute_mode` `gpu`, under the
entry's profile (`granite-3.1-3b-a800m-instruct-q4km@laptop-mobile-gpu/gpu`: `-ngl 99`,
the declared value, launched; `-c 32768`; `-t 8`; no override; no `--n-cpu-moe`),
`thinking_policy` `disabled` with the entry's `none` control (no switch sent). They ran
from the commit that added the entry, on a clean tree: every row carries `commit_sha`
`3008ef92fa86b203d633815f154f2d329b8f1d66` (`tree_dirty: false`) and `roster_version`
9. Fiche `6159f6b5...`. The entry completed both suites with no failed item, so the
search's stop condition (owner answers Q127 (a), Q128 (a)) holds.

| Entry | Suite | `run_id` | Rows | Score [95% interval] | `en` | `fr` | `de` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `granite-3.1-3b-a800m-instruct-q4km` | `classification-support-routing@5` | `6630e70b3bf842d2820b8dfa5acab5dd` | 20 | accuracy **0.75** [0.55, 0.90] | 0.70 (n=10) | 0.80 * (n=5) | 0.80 * (n=5) |
| `granite-3.1-3b-a800m-instruct-q4km` | `translation-business-short-form@4` | `316508c8f6ad4ff3a899b4341f481a9a` | 21 | chrF **0.710** [0.627, 0.792] | 0.659 * (EN->FR) | 0.566 * (FR->DE) | 0.904 * (DE->EN) |

`*` = `indicative`. The bundle now holds 244 quality rows: the 203 before and these
41, promoted into `machines/laptop-mobile-gpu/` and merged. Every classification
answer parsed. Granite 3.1 3B-A800M misrouted five items: `account-01`,
`billing-03` and `account-de-01` as `technical`, `technical-03` and `account-fr-01`
as `other`. No `Qwen3-4B` quality row at these suite versions is in the bundle, so the
class's side-by-side reading rests on the earlier, superseded tables below
(chat-templated classification `@3` 0.70, translation `@2` 0.7252), not on rows of the
same suite version.

**No row contradicts the EN/FR/DE claim.** The entry claims `en`, `fr` and `de`. Every
translation output is in its target language (French for EN->FR, German for FR->DE,
English for DE->EN). Two outputs carry errors inside the right language: `fr-de-06`
opens its German sentence with the French article "Un", and `en-fr-05` writes
"L'bureau". The weakest reading is FR->DE at 0.566 on seven items, an indicative figure
rather than a contradiction. The claim stays on the entry either way, as the epic
decides.

### The top class: Gemma 4 12B beside Qwen3.6-35B-A3B (2026-10-04)

**The class spans two families, dense and MoE.** `gemma-4-12b-it-iq4xs` (Google,
`gemma4`, dense, 11,907,350,576 total parameters, 6,375,734,080 bytes on disk) entered
the roster at `roster_version` 10 from its candidate-gate pass record
(`aidd_docs/roster/candidate-records.jsonl`, 2026-10-04) beside the MoE flagship
`qwen3.6-35b-a3b-ud-iq4xs`. It was the first candidate in gate order (smallest download
first). It is non-Qwen and dense, and the flagship already represents MoE, so its pass
ends the search (owner answers Q127 (a) and Q129 (a)): the Gemma 4 26B-A4B was not
tried.

| Candidate, in gate order | Pin | Outcome |
| --- | --- | --- |
| Gemma 4 12B it (`gemma4`, dense) | `unsloth/gemma-4-12b-it-GGUF@fc034cfff751157913579611efad8462ac1be606`, `gemma-4-12b-it-IQ4_XS.gguf` | **passed** every step; entered as the class's second family and its dense model |
| Gemma 4 26B-A4B it (`gemma4`, MoE) | `unsloth/gemma-4-26B-A4B-it-GGUF@c099eb48e663fd284577b04978a94ffccb261841`, `gemma-4-26B-A4B-it-UD-IQ4_XS.gguf` | not tried: a non-Qwen dense model had passed and the flagship represents MoE (Q129 (a)) |

No candidate was refused or deferred, so the pinned build `b10537` held and no
build-upgrade question arises. GPT-OSS 20B, Qwen3-Coder-30B-A3B and Mellum2-12B-A2.5B
stay out of the shortlist, being outside the epic's families (Q12).

**Quant: not the flagship's.** The flagship is `UD-IQ4_XS`; no packager ships
`UD-IQ4_XS` for the Gemma 4 12B (unsloth's repository at its pinned revision lists
`IQ4_XS`, `IQ4_NL` and `UD-*` files at other bit widths only), so the 12B is taken at
`IQ4_XS`, the nearest: the same `IQ4_XS` base type without Unsloth Dynamic's per-layer
upcasting. A gap between the two entries is therefore a family, size and dense-versus-MoE
difference read through a small quant difference, not a family difference alone.
Google ships no `IQ4_XS` GGUF; the file is unsloth's quantization of Google's weights.

**Licence.** `apache-2.0` (the hub's identifier, read off unsloth's card at its pinned
revision, which carries no LICENSE file; the card links Google's Gemma 4 licence page,
Apache 2.0), client-side commercial use permitted.

**Dense and MoE.** Dense: the gate found no `gemma4.expert_count` key in the file's
header, so the entry is `dense` and launches with no `--n-cpu-moe` and `load_mode`
`auto`, as the dense Qwen entries do. MoE: the flagship, so the class's declaration is
unchanged (`moe_sought: true`, `moe_entry: qwen3.6-35b-a3b-ud-iq4xs`). The flagship's
entry is untouched: it keeps its `revision: "main"` pin and its byte-identical launch
(the tech-debt row owns that fix), and its hand-written `expert_count: 40` (its layer
count; its header says 256 experts) stays the open point it was.

**Launch on the laptop's 6 GB GPU: the declared value launched, on a full GPU.** The
gate's load ran the declared block (`-ngl 99`, 32,768-token context, `-t 8`, no
`--n-cpu-moe`) and the server came up and answered `/props` and the thinking probe, so
no load refusal occurred and no stepped-down `-ngl` was needed: 99 is the value that
launched. The weights are 6,080 MiB (6,375,734,080 B), which alone would fit under the
GPU's 6,144 MiB, but a full offload also places the KV cache for the 32,768-token
context and the compute buffers on the GPU. Dedicated memory plateaued at 5,959 MiB
while the server was up (sampled every 2 s, `gate-gemma-4-12b-it-iq4xs.vram.csv` in the
story's evidence) and at 5,973 MiB during the suites, below what weights, cache and
buffers together need. So part of the model most likely sits outside dedicated VRAM,
in the shared system memory the Windows driver falls back to; this is inferred, since
the logs hold no llama-server buffer lines. The model loads and answers; its speed on
this laptop is, by the same inference, not a full-offload figure.

**The GGUF spike's architecture at this class** (owner answer Q125 (a)):

- `gemma4`: loaded, closed by the pass record of `gemma-4-12b-it-iq4xs`
  (`llama_cpp_build` `b10537`, `chat_template_hash`
  `aa3185dfc65051046349995de1cfc2fbb275491b9a3832b71595f1ff5b31d61b`, `thinking`
  declared `{"chat_template_kwargs": {"enable_thinking": false}}` and verified: the
  template renders differently with and without it). The 12B also exercised the
  `gemma4_unified` conversion path.

**Untested: whether the tower holds a Gemma-4-class 26B-A4B MoE at a usable quant.**
The 26B-A4B was not run (owner answer Q129 (a)), so the epic's closing record lists
that dependency as untested; the epic asks it of the tower, not of this laptop.

**Language claim.** Gemma 4's card names no language, only counts ("Out-of-the-box
support for 35+ languages, pre-trained on 140+ languages.", unsloth's card l.157 at the
pinned revision), so the entry's claim lists none, as the flagship's does.

**The new rows.** Both runs on `laptop-mobile-gpu`, `compute_mode` `gpu`, under the
entry's profile (`gemma-4-12b-it-iq4xs@laptop-mobile-gpu/gpu`: `-ngl 99`, the declared
value, launched; `-c 32768`; `-t 8`; no override; no `--n-cpu-moe`), `thinking_policy`
`disabled` with the entry's switch, verified before the first item of each run (the
two renders differ). They ran from the commit that added the entry, on a clean tree:
every row carries `commit_sha` `6de6888a08be48a40da297e287b7bcd8e9ded324`
(`tree_dirty: false`) and `roster_version` 10. Fiche `c9db1dea...`. Dedicated GPU
memory peaked at 5,973 of 6,144 MiB during the runs, the same
dedicated-memory plateau the gate showed (not evidence of a full offload). The entry completed both suites with no failed item, so the search's stop
condition (owner answers Q127 (a), Q129 (a)) holds and the 26B-A4B stays untried.

| Entry | Suite | `run_id` | Rows | Score [95% interval] | `en` | `fr` | `de` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gemma-4-12b-it-iq4xs` | `classification-support-routing@5` | `51bcde3e05814d2097a6be81a83d1e54` | 20 | accuracy **1.00** (interval `zero_width`) | 1.00 (n=10) | 1.00 * (n=5) | 1.00 * (n=5) |
| `gemma-4-12b-it-iq4xs` | `translation-business-short-form@4` | `ff30926f02184ff387c08e5dfafa0ac9` | 21 | chrF **0.866** [0.803, 0.921] | 0.893 * (EN->FR) | 0.785 * (FR->DE) | 0.920 * (DE->EN) |

`*` = `indicative`. The bundle now holds 285 quality rows: the 244 before and these
41, promoted into `machines/laptop-mobile-gpu/` and merged. Every classification
answer parsed and every item was routed correctly. The flagship's local rows at the
same suite version (`classification-support-routing@5`, runs `acb6e894...` and
`68ac4f21...`, `disabled`, same laptop) also score 1.00, so on this suite the dense
12B and the MoE flagship cannot be told apart: both intervals are zero-width, and the
suite cannot separate them. No flagship row at `translation-business-short-form@4` is
in the bundle, so the translation figure has no same-version counterpart in its class
yet.

**Language claim against the rows.** The claim names no language, so no row can
contradict it. The rows themselves are all in the target language (French for
EN->FR, German for FR->DE, English for DE->EN). The weakest direction is FR->DE at
0.785 on seven items, an indicative figure whose lowest items are paraphrases rather
than errors (`fr-de-04` 0.453, "nennen Sie uns einen verfügbaren Zeitraum";
`fr-de-05` 0.625, "in unseren Räumlichkeiten").

Every quality row written from schema `"19"` on carries `family` (its
subject's: the local entry's, or a cloud model's own) and `size_class` (the
local entry's; `null` on a cloud row, whose model is not banded). Rows below
`"19"` are not back-filled.

Every quality row written from schema `"20"` on names the agentic harness it
ran under (`harness_id`, one of `direct`, `smolagents`, `langgraph`,
`pydantic-ai`, `llamaindex`), that harness's installed version read when the
row was written (`harness_version`; for `direct`, the `requests` client its
calls go through), and its per-call prompt overhead
(`harness_prompt_overhead`: `tokens`, the engine's prompt-token count minus
the item's own rendered prompt with its tool definitions, or `null` with a
`null_reason` -- `unmeasurable`, `item_prompt_not_counted` on a cloud row, or
the engine count's own reason). Only `direct` is written today. Rows below
`"20"` are not back-filled.

## This regeneration (the laptop, both modes, 2026-10-04)

The bundle was regenerated under the code's schema (`schema_version` `"30"`) in one bench
session on the laptop (`machine_id` `laptop-mobile-gpu`), from a fresh clone that followed
`docs/setup.md` alone, and returned the way every machine returns rows: the eight runs
were promoted into `machines/laptop-mobile-gpu/` (`wave-local-ai-v2-promote`) and the
bundle derived from it (`wave-local-ai-v2-merge-bundle`, then `--check`). Every row carries
`commit_sha` `32da6f9709738426f3a7d34abdcf79275c4091ec` with `tree_dirty: false` (the
clone's tree was clean), engine `llama.cpp` build `b10537`, and its run's declared profile
with no operator override. The quality pair runs `classification-support-routing@5`.

**The quiet thermal window was asserted, not confirmed.** No operator was present (an
unattended run under the owner's instruction), so the window rests on the machine state
captured before the session
(`aidd_docs/tasks/2026_10/2026_10_04_laptop-republishes-bundle/evidence/machine-state.txt`):
on mains power, power plan "Turbo", GPU at 0 MiB used and 40 C, no `llama-server`
running, 19.3 GB of 32.9 GB RAM free, total CPU load 6%. Other user processes were
running. Each step ran alone, with no `llama-server` process and the GPU at 0 MiB before
it. The GPU was not unthrottled: the capture's active clock-event reasons read `0x24`
(`sw_power_cap` and `sw_thermal_slowdown`) at idle, and every repetition of every `gpu`
run in this bundle (and some repetitions of both `cpu_only` runs) records the same two in
`machine_state.gpu_throttle_reasons`, where both schema-7 runtime rows record only
`gpu_idle`. An owner who does not accept the asserted window re-runs the session.

### `runtime-reference.jsonl`: the flagship pair and Qwen3-0.6B in both modes

| Model | Mode | Run | `run_id` | `gen_tok_per_s` | `prompt_tok_per_s` | `ttft_ms` | `vram_used_mib` | `verdict` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen3.6-35B-A3B` | `gpu` | 1 | `78e5d7ef9a6f4743b5c4985d9a79b590` | 21.200 | 264.917 | 5624.4 | 4548.7 | `not_comparable` (no reference) |
| `Qwen3.6-35B-A3B` | `gpu` | 2 | `12d19a0cdede4fda9512c57885d826d2` | 21.118 | 260.446 | 5721.0 | 4548.7 | `reproduced` against run 1 |
| `Qwen3-0.6B` | `gpu` | 1 | `49d99f73e09e4291be3ca78bcd324082` | 125.168 | 4070.779 | 364.8 | 4526.7 | `not_comparable` (no reference) |
| `Qwen3-0.6B` | `gpu` | 2 | `a05834da5c31407db755bdd6d0223387` | 127.865 | 3741.374 | 396.9 | 4526.7 | `reproduced` against `gpu` run 1 |
| `Qwen3-0.6B` | `cpu_only` | 1 | `e4a0ef9fb77b474b9b81c0f729d22a5a` | 32.048 | 202.670 | 7327.2 | `not_applicable` | `not_comparable` (no reference) |
| `Qwen3-0.6B` | `cpu_only` | 2 | `1212b9b15c68476ea95a449eeeb8137d` | 32.159 | 203.346 | 7302.8 | `not_applicable` | `reproduced` against `cpu_only` run 1 |

The throughput figures are the medians over each run's five counted repetitions. Each run 1
was decided against an empty reference file and each run 2 against a file holding only its
own run 1 (`docs/setup.md` section 4.2), so no second run was decided against the
superseded bundle or the other mode. The `gen_tok_per_s` deltas the verdicts judge against
the 10% tolerance: flagship **0.39%**, Qwen3-0.6B `gpu` **2.15%**, Qwen3-0.6B `cpu_only`
**0.35%**; every run's own `unreliable` is `false`. The three configurations are three
fiches (`1463d39d...`, `73ec536e...`, `d8524577...`): the `gpu` and the `cpu_only` runs of
Qwen3-0.6B do not share one, so no verdict reads one mode against the other. A `cpu_only`
row's `vram_used_mib` is `not_applicable` on the row and on every repetition, never a
number; the GPU fields stay on its fiche, since the laptop has a GPU and the run chose not
to use it.

**Observation, not a verdict: `cpu_only` against `gpu` on the laptop, Qwen3-0.6B.** Over
the two runs of each mode, `cpu_only` generates at **0.254x** the `gpu` rate (32.10 against
126.52 tok/s, the GPU 3.9x faster) and processes the prompt at **0.052x** (203.0 against
3906.1 tok/s, 19.2x), and its first token arrives 19.2x later (7315 against 381 ms). The
two modes are different measurements of one model on one machine, not a reproduction of
each other, and this ratio is never a verdict.

Two further observations. The flagship's `gen_tok_per_s` (21.2) sits below the schema-7
bundle's 25.4 of 2026-08-27; the two runs share no fiche (the identity now carries the
engine, the machine and the mode), so nothing decides between them. The throttle
reasons above differ too: `sw_power_cap` and `sw_thermal_slowdown` on every repetition
now, `gpu_idle` alone then. This pair cannot say which difference, if either, is the
cause. The `cpu_only` peak `process_rss_bytes` (4872921088 and 4873011200,
4.87 GB) sits above the `cpu_only` RAM minimum the roster declares for Qwen3-0.6B (4.77
GB, `docs/setup.md` section 1.2): the declaration is about 2% low, filed in
`aidd_docs/backlog/tech-debt.md`.

### `quality-reference.jsonl`: two runs, local + mistral each, second against the first

| Model | Provider | `run_id` | Accuracy | `de` accuracy | `verdict` |
| --- | --- | --- | --- | --- | --- |
| `Qwen3.6-35B-A3B` | local | `acb6e89475f740508b3e07b6707d2930` | 1.00 | 1.00 | `not_comparable` (run 1) |
| `mistral-small-2603` | mistral | `acb6e89475f740508b3e07b6707d2930` | 0.90 | 0.60 | `not_comparable` (run 1) |
| `Qwen3.6-35B-A3B` | local | `68ac4f21b11d4e4fad5675bba7fb8836` | 1.00 | 1.00 | `reproduced` against run 1, identical on every item |
| `mistral-small-2603` | mistral | `68ac4f21b11d4e4fad5675bba7fb8836` | 0.95 | 0.80 | `reproduced` against run 1, divergence 0.05 (`account-de-01`) within the suite's 0.10 |

Both subjects score 1.00 on `en` and `fr` in both runs. The local flagship now answers all
20 items: the four `unparseable` EN completions of the schema-7 runs are gone (the local
writers have since moved to the chat endpoint under `thinking_policy: disabled`; this
pair does not isolate which change did it). The Mistral batches are seeded
(`random_seed` 20260821, `temperature` 0), took no retry, and cost 0.000231 USD each
(`cost_currency` `USD`, never converted against the local rows' EUR). They are this
bundle's only paid calls: 40 chat completions, plus one model-catalog pre-flight per
batch; no Google and no judge call was made.

**The German routing item, deferred again by name.** The 2026-08-27 tech-debt row defers
rewording `account-de-01` "to the next regeneration", which this is. It is **not**
reworded here: rewording moves `prompt_set_hash` and forces
`classification-support-routing@6`, outside the owner's paid scope for this session (two
Mistral batches on `@5`) and under every record and campaign that cites `@5`. The new runs
sharpen the finding instead of closing it: `mistral-small-2603` routed `account-de-01` to
`technical` in run 1 and to `account` in run 2, and `other-de-01` to `technical` in both,
so both German items the schema-7 rows flagged still misroute, one of them only in one
run. The rewording of both items, with the re-run it forces, is deferred again to the
first regeneration that bumps the suite.

### Superseded files and records: kept, not edited

| Superseded | Replaced by | Why kept |
| --- | --- | --- |
| `runtime-reference.schema-7.jsonl` (2 rows, schema `"7"`) | `runtime-reference.jsonl` (6 rows, schema `"30"`) | a reader following an old citation still finds the row |
| `quality-reference.schema-7.jsonl` (80 rows, schema `"7"`) | `quality-reference.jsonl` (80 rows, schema `"30"`) | same |
| `comparisons.schema-7/` (4 family records) | none yet over the new rows | computed over the schema-7 rows; the export reads only records whose runs the bundle holds |
| `leader-sets.schema-7/` (1 leader-set record) | none yet over the new rows | same |

Unlike `.schema-1` (a count of bundle generations, see below), `.schema-7` is the
`schema_version` the superseded rows carry. All are `git mv`-renamed, never back-filled.
`refusals-reference.jsonl` is new and empty: no run of this session was refused. The
export (`wave-local-ai-v2-export`) refused the republished bundle at first, because a
cloud row's `retry_budget` (keyed by provider) and a suite definition's `level` and
`divergence_tolerance` had no column-dictionary entry; both are now described, and the
interval blocks the new rows carry recompute from the tables alone
(`scripts/recompute_from_export.py`, every value equal).

### Validator proof (this regeneration)

`uv run wave-local-ai-v2-validate aidd_docs/results/runtime-reference.jsonl
aidd_docs/results/quality-reference.jsonl`:

| Run | Result |
| --- | --- |
| Clean pass over the merged bundle | `checked 86 row(s)`, exit **0** |
| One fiche field hand-edited (`gpu_name` of the Qwen3-0.6B `gpu` fiche `73ec536e...`) | exit **1**, `edited (2)` naming both rows citing it (`49d99f73...`, `a05834da...`); `changed_fields` reads "unavailable" because the fiche was not yet committed for `git show HEAD:` to diff against |
| Edit reverted (byte-identical to the live fiche) | `checked 86 row(s)`, exit **0** again |

### Setup gaps the fresh-clone walk found

Both are now in `docs/setup.md`; the walk is logged in
`aidd_docs/tasks/2026_10/2026_10_04_laptop-republishes-bundle/evidence/setup-walk.md`.

- `.env.example` ships placeholder cloud keys that the quality CLI reads as real keys, so a
  key-less walk sends them to the providers: section 4 now says to empty both lines until
  real keys are set.
- Deciding a second run against its own first needs the reference path pointed at the
  first run's rows (and the first run at an empty file): section 4.2 now says how.

## The schema-7 regeneration (Story 19 + Story 20, 2026-08-27)

Superseded on 2026-10-04: these rows are now `runtime-reference.schema-7.jsonl` and
`quality-reference.schema-7.jsonl`, unedited.

Both files were regenerated from scratch under the current schema (`schema_version` `"7"`),
against the 20-item suite (`suite_version` `"2"`, `en`/`fr`/`de` all >=25% share) Story 20
added. Produced on 2026-08-27 by `uv run wave-local-ai-v2` and `uv run
wave-local-ai-v2-quality` against a local llama-server (build `b10537`,
`Qwen3.6-35B-A3B-UD-IQ4_XS`) and `mistral-small-2603`.

Read the code state from the rows, not from this paragraph: every one of the 82 rows
carries `commit_sha` `9bc9da88cf6c450e8f9d086d853b5ee73f55cbd7` (the suite-snapshot
commit, branch `feat/trilingual-suite-and-reference-bundle`) with `tree_dirty: true` --
the runs were taken mid-branch, before the commit that added these files. The dirty
flag is on the rows and is not back-filled away: it says the `commit_sha` alone does not
pin the exact working tree that produced the numbers.

### `runtime-reference.jsonl`: two runs, second against the first

| Run | `run_id` | `gen_tok_per_s` (published) | `prompt_tok_per_s` (published) | `verdict` |
| --- | -------- | --------------------------- | ------------------------------ | --------- |
| 1 | `f5f78c79...` | 25.408 | 272.643 | `not_comparable` (no reference configured yet) |
| 2 | `f7faeef7...` | 24.802 | 273.302 | `reproduced` against run 1 |

The published `gen_tok_per_s` / `prompt_tok_per_s` are the medians over each run's five
counted repetitions, and they are what the tolerance is judged on: `verdict.py` compares
`RUNTIME_REPRODUCTION_TOLERANCE` (10%) against the `*_delta` fields run 2's own verdict
block carries. Observed on those rows: `gen_tok_per_s_delta` **2.39%**,
`prompt_tok_per_s_delta` **0.24%**, `ttft_ms_delta` **0.24%** -- all inside the 10%
tolerance, so no finding for the PRD on this axis. (The repetition *means* are 25.329 and
24.826, a 1.98% spread; they are not the figures the threshold judges and are given here
only so the two do not get confused.) Run 2's verdict carries `reference_run_id` naming
run 1's `run_id` and an empty `differing_fields`.

### `quality-reference.jsonl`: two runs, local + mistral each, second against the first

| Model | Provider | `run_id` | Accuracy | `verdict` |
| ----- | -------- | -------- | -------- | --------- |
| `Qwen3.6-35B-A3B` | local | `5e13166d...` | 0.80 | `not_comparable` (run 1) |
| `mistral-small-2603` | mistral | `5e13166d...` | 0.95 | `not_comparable` (run 1) |
| `Qwen3.6-35B-A3B` | local | `d20afbda...` | 0.80 | `reproduced` against run 1 |
| `mistral-small-2603` | mistral | `d20afbda...` | 0.90 | `not_reproduced` against run 1 |

The local model reproduced exactly (0.80 both runs). The Mistral cloud model did not:
0.95 -> 0.90 across two runs sent with the same pinned sampler (`temperature=0`,
`random_seed=20260821`) -- an observed cloud-side finding for the PRD (the provider does
not guarantee bit-identical output at temperature 0), not a defect in this harness's
verdict logic, which correctly flagged the divergence rather than silently reporting
`reproduced`.

The divergence is one item, and every German misroute in the bundle lands on the same
label, which is a second finding and about the suite rather than the provider:

| Item | Expected | `mistral-small-2603` predicted | Runs affected |
| ---- | -------- | ------------------------------- | -------------- |
| `account-de-01` ("Zwei-Faktor-Authentifizierung deaktivieren, finde aber die Option nicht") | `account` | `technical` | both |
| `other-de-01` ("Zeitplan für die nächste Feature-Ankündigung") | `other` | `technical` | run 2 only (`differing_fields: ["other-de-01"]`) |

`account-de-01` is the stable one: a two-factor setting is an `account` subject, but
"I cannot find the option" reads as a `technical` complaint, and the strongest model in
the roster picks `technical` deterministically both times. Story 20 requires the four
labels to stay semantically disjoint in each language; this item is recorded here as
evidence they are not yet, in German. The item text is **not** edited in place: editing
a prompt moves `PROMPT_SET_HASH`, which would invalidate every row in this bundle. The
revision belongs to the next regeneration and is filed as such.

The local model's four wrong answers per run are all `unparseable` completions on EN
items (`technical-01`, `technical-02`, `billing-03`, `technical-03`), identical across
both runs -- a generation-failure mode named by `failure_reason` on the row, not a
routing ambiguity.

Per-language breakdown (`language_breakdown`, both providers, both runs -- accuracy /
n / indicative):

| Language | n | local accuracy | mistral accuracy | indicative |
| -------- | - | --------------- | ------------------ | ---------- |
| `en` | 10 | 0.60 | 1.00 | **false** (n >= 10) |
| `fr` | 5 | 1.00 | 1.00 | **true** (n < 10) |
| `de` | 5 | 1.00 | 0.80 (run 1) / 0.60 (run 2) | **true** (n < 10) |

`fr` and `de` sit at n=5, below `MIN_PER_LANGUAGE_CELL_ITEMS` (10): an observed
consequence of the 25%-share split at 20 total items (plan.md's Decisions), not a defect.
The suite-level gate (`gate_suite`) is not indicative -- item count and every language's
25% share both pass -- but the per-language cells for `fr`/`de` are, and every row says so
via `language_breakdown[lang].indicative`.

## The translation suite's first live run (2026-09-06)

Not part of the committed bundle. These rows live in the untracked live store
(`aidd_docs/results/quality.jsonl`) at `schema_version` `"10"`; this section records
what the run produced so the numbers are citable and the absences are named. The
committed `quality-reference.jsonl` is still classification-only and is not touched --
regenerating the bundle is a separate, protocol-bound job (see the tech-debt entry the
schema note above refers to).

Suite: `translation-business-short-form`, `suite_version` `"1"`, `prompt_set_hash`
`16150e4406042a89...`, exported item-for-item to
`suite-definitions/translation-business-short-form@1.json`. 21 hand-written items in three
directions, seven each: `en->fr`, `fr->de`, `de->en`. Caps: 128 output tokens, no stop
sequence, 32768 context.

Metric: `chrf` version `"1"` (`chrf.py`), parameters as published on every row --
`char_order` 6, `beta` 2, `whitespace` false, `scale` `"0..1"`. Every row carries
`reference_output` beside `subject_output`, so any number below can be recomputed from
the row alone with `sacrebleu` (multiply by 100 to compare against its printout).

Two runs, the second scored against the first (run 1's rows copied to a scratch file and
handed to the second run as `QUALITY_REFERENCE_PATH`):

| Model | Provider | `run_id` | `suite_score` | `verdict` |
| ----- | -------- | -------- | ------------- | --------- |
| `Qwen3.6-35B-A3B` | local | `80803767...` | 0.7691 | `not_comparable` (run 1: no reference) |
| `gemini-3.5-flash-lite` | google | `80803767...` | 0.8400 | `not_comparable` (run 1: no reference) |
| `mistral-small-2603` | mistral | `80803767...` | — | absent, see below |
| `Qwen3.6-35B-A3B` | local | `696b5376...` | 0.7691 | `reproduced` against run 1, on `item_score` |
| `gemini-3.5-flash-lite` | google | `696b5376...` | 0.8400 | `reproduced` against run 1, on `item_score` |

Both reproduced item for item: `differing_fields` empty on both, and every verdict block
names `compared_field: "item_score"` -- the field the batch was actually decided on,
since a translation row carries no `predicted_label` for the old comparison to read.
Google honouring its seed here is worth recording beside the classification bundle's
opposite finding above, where `mistral-small-2603` moved 0.95 -> 0.90 across two runs at
`temperature=0`: cloud reproducibility is a per-provider observation, not a property of
the harness.

`wave-local-ai-v2-validate` exits `0` over the live store (306 rows at the time of
writing); every row's `fiche_hash` resolves against `fiches/`.

Full-run cost: the local batch produced 422 output tokens for €0.000272 (kWh-derived,
Scope 2); the google batch 714 in / 295 out for $0.000952 (list-price-derived, Scope 3).
The two are not directly comparable and every Scope-3 row says so in
`scope_comparability`. Wall clock: ~1 minute local, ~3 minutes google (21 items x two
paced calls at `GOOGLE_REQUEST_PACING_S` 4.1).

Per-language breakdown (`score_breakdown`, by **source** language -- score / n /
indicative):

| Source language | n | local | google | indicative |
| --------------- | - | ----- | ------ | ---------- |
| `en` (-> `fr`) | 7 | 0.7962 | 0.8671 | **true** (n < 10) |
| `fr` (-> `de`) | 7 | 0.6878 | 0.7700 | **true** (n < 10) |
| `de` (-> `en`) | 7 | 0.8233 | 0.8829 | **true** (n < 10) |

All three cells are marked indicative: seven items per direction against
`MIN_PER_LANGUAGE_CELL_ITEMS` (10). The suite-level gate is *not* indicative -- 21 items
and each source language at 33% both pass -- and the mark is on the cells, where it
belongs. Clearing it needs nine more hand-authored reference translations, including
German ones nobody in-project can natively verify; the mark is the honest report of that
limitation rather than a set inflated to hide it.

No item failed on either provider: `failure_counts` is all-zero on every row.
`unparseable` is structurally unreachable on this suite (no closed set to parse into, and
nothing is extracted from a completion before scoring), which is stated on
`translation_suite.py` rather than left to look like a suite that never fails to parse.

### What was absent, and why

`mistral-small-2603` produced no rows in either run. The batch was attempted three times
under run 1 -- once in the first invocation, twice more under `--resume 80803767...` so
the batches already on disk were never re-paid for -- and each ended with `mistral
skipped: retry budget exhausted after 4 retries`. A single hand-issued request confirms
the cause is not a burst:

```
Mistral request failed with status 429: {"object":"error","message":"Rate limit
exceeded","type":"rate_limited","param":null,"code":"1300","raw_status_code":429}
```

The model catalog answered `200` on the same key at the same moment, so this is the
workspace's Free-tier rate floor rather than a credential, a DNS or a retired-model
problem. A documented absence, not a blocked run: the local and google batches persisted
and the CLI exited `0`, which is the skip-not-abort contract behaving as designed.

### The `<think>` block, a finding rather than a fix

Every local completion opens with an empty `<think>\n\n</think>` envelope (the server runs
with `--jinja` and this roster entry emits reasoning tags). Exact-match scoring never saw
it -- `normalize_label` finds the first label token past it -- but chrF scores the raw
completion, so the envelope adds ~15 characters of non-reference n-grams to every local
hypothesis and costs the local subject precision that google does not pay. The
local-vs-google gap above is therefore an upper bound on the real one. This is filed in
`aidd_docs/backlog/tech-debt.md` rather than patched here: stripping it would need either
a "remove a provider's reasoning envelope" scoring rule (a choice sacreBLEU would not
reproduce, which the plan rejected on purpose) or a server/roster flag change. Either is
a decision, not a patch, and inventing one mid-run would have made these numbers
unreproducible from the code that wrote them.

### Reading these scores

chrF here is measured against **one** reference translation, so it penalises a valid
alternative wording. The lowest local scores are exactly that case rather than errors.
The completion column below is the row's `subject_output` **with the `<think>\n\n</think>`
envelope trimmed for reading**, so the two score columns are both given: `item_score` is
the number actually published on the row (scored on the full `subject_output`, envelope
included), and the last column is what the trimmed text alone scores. The gap between
them is the envelope's cost on that item, and it is why recomputing from the text printed
here does not land on the published number.

| Item | Reference | `Qwen3.6-35B-A3B` (envelope trimmed) | `item_score` (as published) | trimmed text alone |
| ---- | --------- | ------------------------------------ | --------------------------- | ------------------ |
| `fr-de-03` | "Der Kostenvoranschlag, den Sie uns übermittelt haben, übersteigt unser Jahresbudget." | "Das von Ihnen übermittelte Angebot übersteigt unser jährliches Budget." | 0.4078 | 0.4205 |
| `fr-de-05` | "Das Auftaktgespräch findet um zehn Uhr in unseren Räumen statt." | "Der Kick-off-Meeting findet um 10 Uhr in unseren Räumlichkeiten statt." | 0.4759 | 0.4997 |
| `en-fr-05` | "Nos bureaux seront fermés lundi prochain en raison d'un jour férié." | "Notre bureau sera fermé lundi prochain pour un jour férié." | 0.5135 | 0.5333 |

All three are defensible translations scored down for choosing different words than the
reference on file. A published `suite_score` is defensible as a **comparison between
models measured against identical references**. It is not an absolute measure of
translation quality, and no claim of that kind should be built on it.

### Superseded files: kept, not deleted

`runtime-reference.schema-1.jsonl` and `quality-reference.schema-1.jsonl` are this
regeneration's predecessors, `git mv`-renamed rather than overwritten. The `.schema-<N>`
suffix counts superseded bundle generations -- this is generation 1, the first bundle
this repo published -- and is deliberately **not** a `schema_version` value: no row in
either file carries `schema_version` `"1"`. What they actually carry is
`schema_version` `"2"` on one row of `runtime-reference.schema-1.jsonl` and no
`schema_version` key at all on its other two rows and on all 40 rows of
`quality-reference.schema-1.jsonl`, because the key postdates them. They were produced
against the 10-item, EN-only suite. They
are kept for published-evidence continuity across the epic's duration (`every-published-
row-explains-and-reproduces-itself`'s Boundaries) -- a reader following an old citation
still finds the row it pointed at. `tests/test_reference_bundle.py` names them explicitly
as the superseded set and never folds them into the current-schema bundle checks.

### Validator proof (this regeneration)

`uv run wave-local-ai-v2-validate aidd_docs/results/runtime-reference.jsonl
aidd_docs/results/quality-reference.jsonl`:

| Run | Result |
| --- | ------ |
| Clean pass over the assembled bundle | `checked 82 row(s)`, exit **0** |
| One fiche field hand-edited (`gpu_name`) | exit **1**, `edited (82)` naming every row citing that fiche and `changed_fields: ['gpu_name']` -- all 82 rows share one fiche (same machine/flag configuration across all four runs) |
| Edit reverted (`git checkout --`) | `checked 82 row(s)`, exit **0** again |

## Dense versus MoE, side by side (2026-09-06)

> **Superseded, and kept.** Every local number in this section was produced by
> posting the item text raw to `/completion`, so a chat-tuned model was asked to
> continue it rather than answer it. These are real measurements of the wrong
> thing, and the subsection below, "What the dense rows are actually measuring",
> is where that was first written down. They are **not edited**: the rows exist
> on disk and still say what they said. Read them beside "The same eight
> batches, chat-templated" further down, which re-runs all four models under
> bumped suite versions. The defect is
> `aidd_docs/backlog/defects/local-subject-prompts-are-never-chat-templated.md`.

The three dense models' rows were produced today and are not part of the committed
bundle: they live in the untracked live stores (`aidd_docs/results/runtime.jsonl`,
`aidd_docs/results/quality.jsonl`) at `schema_version` `"10"`. This section records what
they produced so the numbers are citable. The committed reference bundle is frozen one
schema behind for the reason its own section above gives, and is **not** touched. What
*is* committed is the three fiches the dense rows cite -- `f804bee0...` (0.6B),
`067530ef...` (1.7B), `dfd5a5ea...` (4B) -- so every dense number below resolves to a
stored hardware-and-flags record and a roster entry.

The comparator rows in the tables below are older and are cited, not re-run, so they do
not all share that provenance. Where each one lives:

| Cited row | `run_id` | Where it lives | `schema_version` |
| --------- | -------- | -------------- | ---------------- |
| `Qwen3.6-35B-A3B` runtime | `f7faeef7...` | committed `runtime-reference.jsonl` (also in the live store) | `"7"` |
| `Qwen3.6-35B-A3B` + `gemini-3.5-flash-lite` classification | `1f3c94b9...` | untracked `quality.jsonl` only | `"8"` |
| `Qwen3.6-35B-A3B` + `gemini-3.5-flash-lite` translation | `80803767...` | untracked `quality.jsonl` only | `"10"` |

All four cite fiche `b9d1af56...`, which is committed, so those numbers resolve too.

The model set is the roster's four entries, unchanged since `roster_version` 2 (version 3
adds licence and language metadata only, version 4 size classes and their figures): the MoE flagship plus a dense Qwen3 size ladder. The
dense/MoE distinction is what the section is for, so it is in the table rather than in a
footnote:

| Model | Entry id | Arch | Quant | `-ngl` | `--n-cpu-moe` | `--load-mode` |
| ----- | -------- | ---- | ----- | ------ | ------------- | ------------- |
| `Qwen3.6-35B-A3B` | `qwen3.6-35b-a3b-ud-iq4xs` | MoE, 40 experts, 3.1B active | `UD-IQ4_XS` | 99 | **37** | `none` |
| `Qwen3-4B` | `qwen3-4b-q4km` | dense, 4.0B | `Q4_K_M` | 99 | *absent* | `auto` |
| `Qwen3-1.7B` | `qwen3-1.7b-q8` | dense, 1.7B | `Q8_0` | 99 | *absent* | `auto` |
| `Qwen3-0.6B` | `qwen3-0.6b-q8` | dense, 0.6B | `Q8_0` | 99 | *absent* | `auto` |

All three dense entries held every layer on the GPU at 32768 context on a 6144 MiB
RTX 3060 Laptop. The plan expected the 4B to need a step-down and it did not, with under
200 MiB to spare -- a probe result, not an estimate.

### Classification

Suite `classification-support-routing`, `suite_version` `"2"`, 20 items, 32-token cap.
The `gemini-3.5-flash-lite` row is cited from the run that already paid for it rather
than re-run: same suite, same version, same items, already on disk.

| Model | Provider | `run_id` | Accuracy | `empty` | `unparseable` | `truncated_max_tokens` | `en` (n=10) | `fr` (n=5) | `de` (n=5) |
| ----- | -------- | -------- | -------- | ------- | ------------- | ---------------------- | ----------- | ---------- | ---------- |
| `gemini-3.5-flash-lite` | google | `1f3c94b9...` | **1.00** | 0 | 0 | 0 | 1.00 | 1.00 * | 1.00 * |
| `Qwen3.6-35B-A3B` | local | `1f3c94b9...` | **0.80** | 0 | 4 | 0 | 0.60 | 1.00 * | 1.00 * |
| `Qwen3-4B` | local | `d7f08b1a...` | **0.45** | 0 | 9 | 0 | 0.50 | 0.40 * | 0.40 * |
| `Qwen3-0.6B` | local | `c836bacc...` | **0.45** | 0 | 6 | 0 | 0.50 | 0.40 * | 0.40 * |
| `Qwen3-1.7B` | local | `9dd45420...` | **0.25** | 0 | 14 | 0 | 0.30 | 0.20 * | 0.20 * |

`*` = `indicative`: the cell holds 5 items against `MIN_PER_LANGUAGE_CELL_ITEMS` (10).
The suite-level number is not indicative on any row.

The ladder does not rank by size. The 1.7B is the worst of the four and the 4B ties the
0.6B. Every dense row's `tokens_out_total` is 640 -- 20 items x the full 32-token cap --
so all three ran the cap dry on every single item, while the MoE flagship spent 240 and
`gemini-3.5-flash-lite` spent 20. That is the whole story of this table, and the next
section is what it actually means.

### Translation

Suite `translation-business-short-form`, `suite_version` `"1"`, 21 items in three
directions, 128-token cap, chrF against **one** reference on the `0..1` scale.

| Model | Provider | `run_id` | `suite_score` | `en`->`fr` (n=7) | `fr`->`de` (n=7) | `de`->`en` (n=7) |
| ----- | -------- | -------- | ------------- | ---------------- | ---------------- | ---------------- |
| `gemini-3.5-flash-lite` | google | `80803767...` | **0.8400** | 0.8671 * | 0.7700 * | 0.8829 * |
| `Qwen3.6-35B-A3B` | local | `808037675130` | **0.7691** | 0.7962 * | 0.6878 * | 0.8233 * |
| `Qwen3-4B` | local | `350cac2f...` | **0.2005** | 0.2128 * | 0.1990 * | 0.1896 * |
| `Qwen3-0.6B` | local | `c370c862...` | **0.1867** | 0.2096 * | 0.1909 * | 0.1595 * |
| `Qwen3-1.7B` | local | `80eec0cd...` | **0.1742** | 0.1774 * | 0.2124 * | 0.1328 * |

`*` = `indicative` on every cell: seven items per direction against the 10-item floor.
`failure_counts` is all-zero on every translation row, on every model -- `unparseable` is
structurally unreachable on this suite.

The single-reference caveat applies here exactly as it does above: chrF against one
reference compares models on identical references and is not an absolute measure of
translation quality.

### What the dense rows are actually measuring

A ~0.19 chrF reads like "these models cannot translate". Read one completion and that is
not what happened. `Qwen3-4B`, item `fr-de-03`, `item_score` 0.2157, the row's
`subject_output` in full -- it ran the 128-token cap dry, so it ends mid-sentence where
the row itself ends:

```
 Nous ne pouvons donc pas vous aider à réaliser ce projet. Nous vous remercions de
votre compréhension.
Answer:

Der von Ihnen übermittelte Angebot überschreitet unseren jährlichen Budget. Daher
können wir Ihnen nicht helfen, dieses Projekt umzusetzen. Vielen Dank für Ihr
Verständnis.  
**Note:** The translation provided is accurate and maintains the formal tone of the
original French text. The key terms like "dévis" (offer), "budget annuel" (annual
budget), and "projet" (project) are correctly translated. The sentence structure is
adapted
```

The German in the middle is a good translation of the reference sentence. The model
reached it only after first **continuing the French source text**, and then spent the
rest of its cap reviewing its own work in English. chrF scores the full raw completion,
so the continuation and the `**Note:` commentary together drown the answer.

The classification rows fail the same way. `Qwen3-0.6B`, item `billing-02`, expected
`billing`, running the 32-token cap dry:

```
 

The message is about the currency of the invoice. The message is about the amount owed.
The message is about the payment method. The message is about the
```

That completion is **not** quoted from a row: a classification row carries
`predicted_label` and `failure_reason`, never the raw text (`subject_output` is `null` on
every classification row this project has written, these three included). It comes from
the direct `/completion` probe against `qwen3-0.6b-q8` described in the truncation-
reporting section below, replaying the same item at the same cap. What the rows
themselves carry for this batch is `failure_reason: "unparseable"` on 6 of 20 items and
`tokens_out_total` 640 -- 20 × the full cap -- which is the evidence for the paragraph
that follows; the text above only shows what running the cap dry looks like.

The local quality path posts a **raw prompt to `/completion`**, with no chat template
applied. These Qwen3 releases treat that as text to continue rather than as an
instruction to follow. The MoE flagship, on the same endpoint with the same `--jinja`,
opens with a `<think>` envelope and then obeys -- it costs that model ~15 characters of
chrF precision (the finding recorded in the translation section above) and costs these
three models the entire answer.

So the honest reading of both tables is: they measure **instruction-following on a raw
completion endpoint**, and on that axis the dense Qwen3 ladder loses badly to the MoE
flagship and to the cloud comparator. They do not establish that a 4B dense model cannot
classify or translate. Separating the two needs a chat-templated local path, which is a
suite-level decision and is filed as tech debt, not patched between two measured runs.

The plan's stated risk was the opposite failure -- that a thinking-by-default model would
spend its cap on a reasoning block and land as `truncated_max_tokens`. It did not: no
dense row reasons first. See the truncation-reporting defect below for why that field
reads `0` regardless.

### Runtime

One `wave-local-ai-v2` invocation per entry at default protocol: 1 warm-up, 5 counted
repetitions, 10 s cooldown, pinned seed, `cache_prompt: false`, 128-token cap.

| Model | Quant | `-ngl` | `--n-cpu-moe` | `run_id` | `gen_tok_per_s` | `prompt_tok_per_s` | `ttft_ms` | gen / ttft / prompt spread | `unreliable` | RSS | VRAM | Energy (kWh) | Cost (EUR) | `verdict` |
| ----- | ----- | ------ | ------------- | -------- | --------------- | ------------------ | --------- | -------------------------- | ------------ | --- | ---- | ------------ | ---------- | --------- |
| `Qwen3-0.6B` | `Q8_0` | 99 | *absent* | `68a5e1df...` | **207.8** | **4117.8** | **360.6** | 0.005 / 0.078 / 0.093 | false | 1078 MB | 4527 MiB | 0.00078 | 0.000151 | `not_comparable` |
| `Qwen3-1.7B` | `Q8_0` | 99 | *absent* | `e5714fcb...` | 116.0 | 3091.9 | 480.3 | 0.002 / 0.083 / 0.100 | false | 2277 MB | 5689 MiB | 0.00090 | 0.000174 | `not_comparable` |
| `Qwen3-4B` | `Q4_K_M` | 99 | *absent* | `f8678fe0...` | 33.6 | 275.2 | 5396.4 | 0.001 / 0.003 / 0.003 | false | 4275 MB | **6115 MiB** | 0.00214 | 0.000414 | `not_comparable` |
| `Qwen3.6-35B-A3B` | `UD-IQ4_XS` | 99 | **37** | `f7faeef7...` | 24.8 | 273.3 | 5451.9 | 0.005 / 0.004 / 0.004 | false | 15226 MB | 4549 MiB | 0.00264 | 0.000513 | `reproduced` |

The two memory columns are not in the same unit, because the two fields are not: `RSS` is
`process_rss_bytes` in decimal MB (10^6 B, the unit this project's earlier records use for
that field), `VRAM` is `vram_used_mib` in MiB (2^20 B, the unit NVML reports). Both are
peaks over the counted repetitions, not point samples.

Every dense `verdict` is `not_comparable`, and that is the honest first-run state rather
than a gap: the verdict blocked on `llama_cpp_build` / `quant` / `gpu_name` / `flags` (since
schema `"22"`: `engine_id` / `engine_build` in place of the first), and
no reference row shares a new quant and a flag set with no `--n-cpu-moe` in it. The
flagship's `reproduced` is its own earlier pair, unaffected by this increment.

Two things in that table are worth naming:

- **The 4B's prompt throughput collapses to the flagship's.** 275 vs 3092 tok/s for the
  1.7B, an 11x drop for a 2.4x model, and its TTFT (5396 ms) lands within about 1% of
  the flagship's (5452 ms) despite the flagship offloading 37 expert layers to CPU. Its
  `vram_used_mib` is 6115 of 6144 -- 99.5% of the card. Fitting at `-ngl 99` and running
  well at `-ngl 99` are not the same thing, and this row is what the difference looks
  like.
- **The dense ladder's cost advantage is real and large.** The 0.6B does the same 640
  output tokens for €0.000151 against the flagship's €0.000513, at 8.4x the generation
  rate and 1/14th the host RAM.

`machine_state`: no repetition on any of the three reported `sw_thermal_slowdown`. GPU
temperatures stayed at 60-65 °C on the two small models and 71-75 °C on the 4B, and the
throttle reason on all three counted sets is `sw_power_cap`, which is this laptop GPU's
ordinary behaviour under load, not a thermal event. No run was repeated to improve a
number.

### The truncation-reporting defect, filed rather than fixed

`failure_counts.truncated_max_tokens` reads `0` on every row in both tables above,
including the rows whose `tokens_out_total` proves every item ran the cap dry. The rows
are wrong, and the cause is not the models.

On llama.cpp `b10537` the `/completion` response carries **no `stopped_limit` key**. It
reports `stop_type: "limit"` instead. `quality_cli._run_local_suite` reads
`response_json.get("stopped_limit", False)`, so a cap-exhausted completion is published
as not-truncated and its failure is attributed to `unparseable`. Probed directly on this
build against `Qwen3-0.6B` item `billing-02`: `tokens_predicted: 32` (the cap),
`stop_type: "limit"`, and `stopped_limit` absent from the response entirely.

Every local row this project has ever published is affected, the flagship's included.
**The scores are not**: a truncated completion and an unparseable one both score the same,
so accuracy, `suite_score` and every per-language cell stand exactly as published. Only
the failure label moves. Filed in `aidd_docs/backlog/tech-debt.md`; not patched here,
because changing the harness between the pilot and the matrix would have made these rows
unreproducible from the code that wrote them.

### The two caveats this comparison genuinely carries

- **The architecture comparison spans a model generation.** The dense ladder is Qwen3
  (May 2025); the flagship is Qwen3.6 (2026). Size is controlled *within* the ladder, so
  the 0.6B/1.7B/4B rows compare cleanly against each other. Dense-vs-MoE across the two
  is confounded by ~18 months of post-training, and the raw-completion behaviour above is
  most likely a generation difference rather than an architecture one.
- **The quants are not uniform.** `Q8_0` at 0.6B and 1.7B, `Q4_K_M` at 4B,
  `UD-IQ4_XS` on the flagship. That is what each vendor repo publishes -- the 0.6B and
  1.7B GGUF repos contain exactly one quant each -- and forcing uniformity would have
  meant leaving the vendor's own artifact for a repackager.

### Cost of reproducing this

The whole live session -- pilot, three runtime runs, six quality batches -- ran
12:04:13 to 12:13:07 UTC on 2026-09-06, **under 9 minutes of wall clock**, on one machine,
with no cloud quota spent (the `google` comparator rows were cited, not re-run). The
downloads are 4.63 GiB total. `wave-local-ai-v2-validate` exits `0` over both live stores,
`checked 432 row(s)`, every `fiche_hash` resolving.

> **This table now renders live.** `GET /api/comparisons` (the store-wide,
> quality-only comparison route) and the dashboard's "Compare dense and MoE"
> screen build the tables below from the same live store, one column per
> roster model, so a reader can check these numbers against the running
> service instead of trusting the transcript.

## The same eight batches, chat-templated (2026-09-06, later the same day)

The four models above, re-run on both suites after the local subject path moved
to llama-server's `/v1/chat/completions`. Same machine, same four committed
fiches, same items, same caps, same pinned sampler. What changed is what the
model was sent: each item is now rendered through the loaded model's own chat
template and answered on the chat endpoint, under a suite-declared
`thinking_policy` of `disabled`.

These rows live in the untracked live store at `schema_version` `"11"`, under
`suite_version` `"3"` (classification) and `"2"` (translation). Their
predecessors above are `"2"` and `"1"`, and `verdict.select_quality_references`
keys on `suite_version`, so every new batch reports `not_comparable` against
them by construction. Nothing was edited to achieve that. Both suites'
`prompt_set_hash` is **unchanged** -- no item text moved -- and each version's
definition is committed beside its predecessor at
`suite-definitions/<suite_id>@<suite_version>.json`.

### Classification

Suite `classification-support-routing`, `suite_version` `"3"`, 20 items,
32-token cap, `thinking_policy: disabled`.

| Model | `run_id` | Accuracy | was | `tokens_out_total` | was | failures | `en` (n=10) | `fr` (n=5) | `de` (n=5) |
| ----- | -------- | -------- | --- | ------------------ | --- | -------- | ----------- | ---------- | ---------- |
| `gemini-3.5-flash-lite` | `1f3c94b9...` | **1.00** | 1.00 | 20 | 20 | 0 | 1.00 | 1.00 * | 1.00 * |
| `Qwen3.6-35B-A3B` | `d4d2e0d5...` | **1.00** | 0.80 | 40 | 240 | 0 | 1.00 | 1.00 * | 1.00 * |
| `Qwen3-4B` | `ebce4da6...` | **0.70** | 0.45 | 40 | 640 | 0 | 0.80 | 0.60 * | 0.60 * |
| `Qwen3-1.7B` | `91ee67b1...` | **0.60** | 0.25 | 40 | 640 | 0 | 0.70 | 0.40 * | 0.60 * |
| `Qwen3-0.6B` | `e716ce86...` | **0.45** | 0.45 | 40 | 640 | 0 | 0.50 | 0.40 * | 0.40 * |

`*` = `indicative`: the cell holds 5 items against `MIN_PER_LANGUAGE_CELL_ITEMS`
(10). The suite-level number is not indicative on any row. The `gemini` row is
the same cited row as above, restated for comparison; see the version caveat
below.

### Translation

Suite `translation-business-short-form`, `suite_version` `"2"`, 21 items,
128-token cap, chrF against **one** reference on the `0..1` scale,
`thinking_policy: disabled`.

| Model | `run_id` | `suite_score` | was | `en`->`fr` (n=7) | `fr`->`de` (n=7) | `de`->`en` (n=7) |
| ----- | -------- | ------------- | --- | ---------------- | ---------------- | ---------------- |
| `gemini-3.5-flash-lite` | `80803767...` | **0.8400** | 0.8400 | 0.8671 * | 0.7700 * | 0.8829 * |
| `Qwen3.6-35B-A3B` | `79e95271...` | **0.8002** | 0.7691 | 0.8226 * | 0.7004 * | 0.8775 * |
| `Qwen3-4B` | `42bd9d8b...` | **0.7252** | 0.2005 | 0.7169 * | 0.6184 * | 0.8405 * |
| `Qwen3-1.7B` | `41ac932a...` | **0.7107** | 0.1742 | 0.6409 * | 0.6399 * | 0.8513 * |
| `Qwen3-0.6B` | `108fc07e...` | **0.5121** | 0.1867 | 0.4846 * | 0.3852 * | 0.6664 * |

`*` = `indicative` on every cell: seven items per direction against the 10-item
floor. `failure_counts` is all-zero on every row of both tables.

### What moved, and what did not

**The ladder ranks by size now, on both suites.** 0.45 < 0.60 < 0.70 < 1.00 on
classification and 0.5121 < 0.7107 < 0.7252 < 0.8002 on translation, monotonic
in parameter count. The untemplated tables rank it differently and
inconsistently -- the 1.7B was the worst of the four on classification and the
4B only tied the 0.6B -- which is the clearest single sign that those numbers
were not measuring model capability.

**The models stop on their own.** Every dense classification batch above spent
`tokens_out_total` 640, twenty items times the full 32-token cap, never
finishing an answer. All three now spend **40**: two tokens per item, the label
and its stop. The flagship went 240 -> 40. `failure_counts` is all-zero
everywhere, and the six `unparseable` items the 0.6B published and the fourteen
the 1.7B published are gone, because there is now an answer to parse.

**The 0.6B did not improve on classification.** 0.45 before and 0.45 after. It
is the one number in these tables that did not move, and it deserves saying
plainly: this model answers the routing task cleanly and gets it wrong, 15 of
its 20 answers being `technical`. That is a capability result, and it is exactly
what the untemplated run could not have told anyone. Its translation score moved
0.1867 -> 0.5121 in the same session, so the flat classification figure is about
this model on this task, not about this model.

**The flagship reaches the cloud comparator on classification.** 0.80 -> 1.00,
level with `gemini-3.5-flash-lite` on all twenty items. On translation it closes
roughly a third of the gap (0.7691 -> 0.8002 against 0.8400) and does not close
it.

**The `<think>` envelope left the completions.** No `subject_output` in any of
the 84 new translation rows contains `<think>`: with thinking disabled the
template prefills an empty block into the *prompt*, where it costs no score. The
earlier finding said the local-versus-google gap was "an upper bound on the real
one" because the envelope added ~15 characters of non-reference n-grams to every
local hypothesis. That is now measured rather than argued. The flagship's
`fr-de-03` translation is **byte-identical** across the two runs -- "Das von Ihnen
übermittelte Angebot übersteigt unser jährliches Budget." -- and the envelope is
the whole difference between the two stored completions: the superseded row's
`subject_output` carries `\n\n<think>\n\n</think>\n\n` in front of that sentence
and the new one does not. It scores 0.4078 on the old row and **0.4205** here.
0.4205 is exactly the "trimmed text alone" figure the "Reading these scores"
table above predicted for that item, so the prediction and the measurement
agree. The tech-debt row that recorded the envelope stays open for the raw
`/completion` path, which still emits it into the completion.

### The three caveats these numbers carry

- **The cloud comparator sits at the previous suite versions.** The
  `gemini-3.5-flash-lite` rows are cited, not re-run: classification at
  `suite_version` `"2"` and translation at `"1"`, against the new local rows'
  `"3"` and `"2"`. The items, the caps and both `prompt_set_hash` values are
  identical across the bump -- nothing about what the cloud model was asked
  changed -- so the scores stay comparable, and a side-by-side table will
  nevertheless show two different version numbers in one column. Re-running
  Google would pay cloud quota to regenerate identical answers to identical
  prompts. Stated here rather than left for a reader to discover.
- **`thinking_policy: disabled` measures a narrower model than the vendor
  ships.** These are Qwen3 models with reasoning switched off at the request
  level, which is what makes a 32-token label task and a 128-token sentence task
  answerable at all: probed on this build, every one of these models with
  thinking allowed spends its entire cap in `reasoning_content` and returns an
  empty string. A thinking-allowed run with caps sized for deliberation is a
  different measurement, and this project has not made it. Read a routing score
  as a routing score, never as the model's ceiling. Publishing both policies
  side by side is recorded on the defect as deferred on run cost.
- **Everything the untemplated tables say about the comparison's shape still
  holds.** The dense ladder is Qwen3 (May 2025) and the flagship is Qwen3.6
  (2026), so dense-versus-MoE across the two stays confounded by a model
  generation; the quants are still not uniform; and chrF against one reference
  still compares models on identical references rather than measuring
  translation quality absolutely.

### Cost of reproducing this

Eight local batches, one `wave-local-ai-v2-quality` invocation per (model,
suite) at `QUALITY_PROVIDERS=local`, on 2026-09-06. No cloud quota spent. Every
row cites one of the four fiches already committed for the untemplated runs
(`f804bee0...`, `067530ef...`, `dfd5a5ea...`, `b9d1af56...`): same machine, same
flags, so no new hardware record was created and every number here resolves
against the bundle as it already stands. `uv run wave-local-ai-v2-validate` over
both live stores exits `0`, `checked 596 row(s)`.

## Earlier increments' evidence (predates this regeneration)

The sections below describe rows this regeneration **replaced**. They are kept as a
record of what earlier increments validated at the time; the bytes they describe now
live only in the `*.schema-1.jsonl` files above, not in the live `*-reference.jsonl`
files this README's own head section describes.

### `runtime-reference.jsonl` (schema-1, superseded)

Three rows. Rows 1 and 2 are the throughput evidence, copied from lines 4 and
5 of this machine's `runtime.jsonl`. Row 3 is field-shape evidence for the
machine-state/TTFT-provenance increment and is **not** a throughput claim —
see its own block below.

| Claim rows 1-2 support | Value |
| ---------------------- | ----- |
| Generation throughput | `gen_tok_per_s` 26.046 and 25.484 |
| Prompt throughput | `prompt_tok_per_s` 255.93 and 259.25 |

Produced on 2026-08-21 (file written 18:14 local time), on branch
`feat/runtime-measurement-harness` at tip `597596f`, by
`uv run wave-local-ai-v2` against a local llama-server (build `b10537`,
`Qwen3.6-35B-A3B-UD-IQ4_XS`). Every row carries its own hardware fiche and flag
list, so the numbers are falsifiable against the machine that produced them.

**Deliberately excluded**: rows 6 to 9 of the live store. They come from the
reverted streaming experiment, and their `gen_tok_per_s` of 17-18 was measured
while this machine's GPU was in `sw_thermal_slowdown`. Keeping them next to the
acceptance rows with nothing to distinguish them would misrepresent the spread.
Rows 1 to 3 predate the fixed prompt's final length and are excluded for the
same reason: their `prompt_tok_per_s` (76 to 233) was measured at a different
prompt length and is not comparable.

**Row 3 of this file** (added by the machine-state/TTFT-provenance
increment): one full row from `uv run wave-local-ai-v2` at default settings
(`RUNTIME_REPETITIONS=5`, `RUNTIME_COOLDOWN_S=10.0`,
`RUNTIME_SPREAD_THRESHOLD=0.10`), produced on 2026-08-22 (`captured_at`
21:21:58 UTC) on branch `feat/machine-state-and-ttft-provenance` at tip
`ab9280d` (`tree_dirty: true` -- the branch's own uncommitted work). Carries
every field this increment added: per-repetition `machine_state`, the three
`*_spread` fields, `unreliable`, `thermal_posture`, `ttft_source`.

Its `gen_tok_per_s` is **15.256**, far below rows 1-2 (26.0 / 25.5), and it is
kept here as field-shape evidence only. Every one of its repetitions reports
`sw_thermal_slowdown` and `sw_power_cap` in `gpu_throttle_reasons`: this row
was measured on a thermally suppressed GPU, the same condition that excludes
the streaming rows above. Unlike those rows, it says so on its own face --
which is the point of the fields this increment adds -- so it is kept and
labelled rather than dropped. Read the throughput claim from rows 1-2.

| Field | Observed value |
| ----- | --------------- |
| `gen_tok_per_s` | 15.256 -- thermally suppressed, not a throughput claim |
| `gen_tok_per_s_spread` | 0.0518 (5.2%), against the 0.10 threshold -- did not flag |
| `ttft_ms_spread` | 0.0125 |
| `prompt_tok_per_s_spread` | 0.0127 |
| `unreliable` | `false` |
| `thermal_posture` | `"fixed_cooldown"` |
| `ttft_source` | `"server_reported"` |
| `gpu_temp_c` (repetition range) | 66.0-68.0 |
| `gpu_throttle_reasons` (union across repetitions) | `sw_power_cap`, `sw_thermal_slowdown` -- this machine's GPU was throttling during the run; the spread stayed under threshold anyway |
| `cpu_temp_c` / `cpu_temp_source` | `null` / `"unavailable"` -- confirms phase 1's spike conclusion on this Windows build |

### `quality-reference.jsonl` (schema-1, superseded)

All 40 rows of this machine's `quality.jsonl`: two consecutive runs per model,
ten classification items each.

| Model | Provider | Accuracy, run 1 | Accuracy, run 2 |
| ----- | -------- | --------------- | --------------- |
| `Qwen3.6-35B-A3B` | local | 0.60 | 0.60 |
| `mistral-small-2603` | mistral | 1.00 | 1.00 |

Produced on 2026-08-21 (file written 21:56 local time), on branch
`feat/runtime-measurement-harness` at tip `77a1c2e`, by
`uv run wave-local-ai-v2-quality`.

These rows support the reproducibility claim, not an accuracy claim: across the
two runs, every item's `predicted_label` is identical for both models, which is
what a pinned sampler (temperature 0, fixed seed) is there to guarantee. The
local model's four wrong answers per run are wrong in the same way both times.

### What was deliberately absent from the schema-1 rows

Both files predate the `run_id` / `captured_at` provenance keys added by a later
increment. They were **not** back-filled. A hand-edited row is no longer the row
the harness wrote; the absence of those keys is the honest signal that these rows
were produced before the change.

The same applies to the four local-model rows in the schema-1 `quality-reference`
file that carry `"predicted_label": null, "correct": false` with no reason —
`technical-01`, `technical-02`, `billing-03` and `technical-03`, plus their
run-2 duplicates (8 rows total). The harness as it stands today always writes a
`failure_reason` naming why a generation failed (`empty`, `unparseable`,
`truncated_max_tokens` or `truncated_context`); a row with a bare null and no
reason could not be produced by this code path. These rows are **not
back-filled** either: same discipline as above, a hand-edited row is no longer
the row the harness wrote, so the honest signal is left in place rather than
reconstructed.

The only edit ever applied to copied bytes is the line terminator: the live stores
are written in Windows text mode and use CRLF, and these snapshots use LF like
the rest of the repository. Every JSON payload is verbatim, byte for byte.

### Fiche hash, invalidation validator, and reproduction verdict (superseded rows)

Both schema-1 files predate `fiche_hash` and `verdict` entirely -- neither key exists
on any row in either file. `row_contract.FICHE_HASH_SCHEMA_VERSION` ("3") is the
version that introduced them; every row in both files carries a `schema_version` below
it (or none at all), so `wave-local-ai-v2-validate` reports all of them under
its non-fatal `legacy` class rather than `missing`.
