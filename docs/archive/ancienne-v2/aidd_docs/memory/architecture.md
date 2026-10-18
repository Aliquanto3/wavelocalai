# Architecture

The macro technical shape: the stack, how the pieces fit, and the decisions behind them.

## Stack

- Python, managed by uv (lockfile, fast installs, editable dev install)
- FastAPI + uvicorn (plain `uvicorn`, not `uvicorn[standard]`) for the
  read-only results service — the first runtime dependencies added since the
  five benchmark-side ones, and the only HTTP *server* in the project
- pytest for tests, mypy for type checking, ruff for linting and formatting
- The fast gate (ruff, mypy, detect-secrets) is enforced by a local
  `pre-commit` hook (`.pre-commit-config.yaml`, `repo: local`,
  `language: system`); every entry resolves through `uv run`, so `uv.lock` is
  the single version source. `uv run pre-commit install` wires both the
  `pre-commit` and `pre-push` stages in one command; see `coding-assertions.md`
  for the commands. CI now runs the same gate server-side on every push and
  pull request, on a two-OS matrix, behind one required check — see
  `.github/workflows/ci.yml`.

## How it fits together

```mermaid
flowchart LR
    CLI["CLI benchmark runner"]
    Llama["llama.cpp server\n(localhost:8080)"]
    Cloud["Cloud APIs\n(Mistral · Google AI)"]
    Results["Results store\n(quality · runtime)"]
    HF["Hugging Face\n(model download)"]

    CLI --> Llama
    CLI --> Cloud
    CLI --> Results
    HF --> Llama
```

## Key decisions

- **llama.cpp over Ollama**: direct control over inference flags (`--n-cpu-moe`, `-fa`, `--jinja`, etc.), quantization choice, and memory layout; Ollama abstracts these away.
- **uv over pip**: reproducible installs via lockfile, faster CI, single tool for venv + deps + scripts.
- **Two cloud providers for LLM-as-a-judge**: Mistral and Google AI are from different model families; inter-judge agreement is reported alongside judged scores, making them defensible to clients.
- **Quality / runtime split**: quality scores are reproducible (model + prompt + seed); runtime metrics are hardware-bound and must be tagged with a signed hardware fiche. The two are never merged into a single table.
- **English in the repo, French for clients**: code, identifiers, docstrings, comments,
  commits, README and technical docs are English. French is reserved for pitch and
  restitution material produced outside the repo.

## Gotchas

- The results service publishes a **declared-absent contract**: every field a
  view names comes back as a value or as a marked absence
  (`{"absent": true, "reason": ..., "detail": {...}}`), over exactly four
  reasons — the row's `schema_version` predates the field
  (`predates_schema`), the row carries the key as `null` (`null_in_row`), a
  pointer it cites did not resolve (`pointer_unresolved`), or the row states
  the measurement does not apply (`not_applicable`: a `cpu_only` runtime
  row's `vram_used_mib` is the string `"not_applicable"` on the row and every
  repetition from schema "25", never a number; `null` stays a failed read on
  a `gpu` row). Pointers resolved: `fiche_hash`, `roster_entry_id`,
  `suite_id`+`suite_version`, and a runtime row's `machine_id` against the
  machine registry. Nothing is
  defaulted, zero-filled, back-filled or inferred anywhere in `read_model.py`,
  and a row below the service's schema floor is counted in an `unreadable`
  entry naming its version rather than rendered half-populated or dropped.
  Which fields each view renders is *partitioned* against
  `row_contract.REQUIRED_FIELDS` and asserted set-equal in
  `tests/test_read_model.py` — so a field added to the contract fails the
  build naming itself instead of appearing as a silently blank column.
  The "the two stores are never merged" rule below is now enforced by there
  being **no endpoint that could** merge them, not by a convention about how a
  table is laid out: each route reads exactly one store, and the run index
  answers two separately named collections that are never joined, ordered
  against each other or summed.
- One quality store now holds **two score shapes**. A classification row is
  an exact-match row (`correct`, `suite_accuracy`, `language_breakdown`); a
  translation row is a graded row (`item_score`, `suite_score`,
  `score_breakdown`, `metric_id`/`metric_version`/`metric_params`,
  `reference_output` beside `subject_output`) and nulls all three exact-match
  fields. `row_contract` refuses a row carrying both, so `task_suite` — or
  the presence of the graded block — is the discriminator, and a reader must
  select by suite before comparing any score column. Averaging a chrF mean
  and an exact-match rate into one number is the mistake the two shapes exist
  to make impossible. chrF itself is in-repo (`chrf.py`, sacreBLEU's
  defaults, published on `0..1` where sacreBLEU prints `0..100`), and a
  single-reference chrF compares models against identical references rather
  than measuring translation quality absolutely.
- The published reference bundle is five parts handed to an auditor together,
  not any one file alone: `runtime-reference.jsonl` + `quality-reference.jsonl`
  + `refusals-reference.jsonl` (derived by `wave-local-ai-v2-merge-bundle`
  from each machine's tracked location `machines/<machine_id>/`, never
  hand-edited, checked in CI; the schema-"7" curated snapshot it replaced is
  kept as `*-reference.schema-7.jsonl`) + `fiches/` (cited by
  `fiche_hash`) + `aidd_docs/roster/models.json` (cited by `roster_entry_id`)
  + `suite-definitions/` (cited by `suite_id`/`suite_version` on quality
  rows, `suite_snapshot.py` — see `cli.md`). `tests/test_reference_bundle.py`
  asserts every row's pointers resolve inside that set. A superseded
  reference file (schema or item-set change) is `git mv`-renamed to
  `*-reference.schema-<N>.jsonl` and kept, never deleted — published-evidence
  continuity for the epic's duration — with a `.gitignore` negation
  (`!aidd_docs/results/*-reference.schema-*.jsonl`) so the rename does not
  silently drop it from tracking, and `aidd_docs/results/README.md` names
  each superseded file and why it is kept.
- The model roster (`aidd_docs/roster/models.json`, parsed by `roster.py`) is
  now the source of truth for a model's identity (repo, revision, file,
  checksum, architecture) and its full launch flag set. `server.py`,
  `__init__.py` and `quality_cli.py` no longer hardcode these as source
  constants — they resolve everything through `roster.resolve_entry` plus
  the run profile of the (entry x machine x mode) triple
  (`aidd_docs/roster/profiles.json`, `profiles.py`: `-ngl` override,
  `--n-cpu-moe`, `-t`), with `SERVER_N_CPU_MOE` / `SERVER_THREADS` as
  operator overrides applied last (see `cli.md`). The profile id is on every
  row and, outside the hashed projection, on every fiche. The engine is data too: the engine
  registry (`aidd_docs/roster/engines.json`, parsed by `engines.py`) holds
  one entry per engine (`llama.cpp`, the reference) with its live build
  probe, endpoints, lifecycle, host and port, thinking-switch field, the
  path-free normalisation its launch flags are hashed under, and its
  configuration defaults, each marked `declared` or `engine_reported`.
  `server.py` reads host, port and the health path from it; the build is a
  live probe of the running binary (`build_probe.py` through the entry),
  never a constant string.
- A dense roster entry carries **no** `--n-cpu-moe` and **no** `--load-mode
  none` — the two flags that exist only to make an MoE offload work. That is
  enforced, not conventional: the entry's `architecture` block
  (`kind: "dense"`, `expert_count: 0`) is what makes it checkable, and
  `roster.validate_host_fit` *refuses* a dense entry handed any offload
  value rather than dropping the flag quietly. So the seam that lets a dense
  entry launch is a resolution change, not a `kind == "dense"` branch in
  `server.build_flags`: the run profile (`profiles.py`) resolves no
  `n_cpu_moe` for a dense entry, and `validate_host_fit` runs on the resolved
  profile, operator override included, so the check always sees the value
  that will reach the command line. `0` is an explicit instruction to
  offload no experts and still refuses; `None` is the absence of an
  instruction. The
  committed fiche for each run records the launched flag list, so "this row
  carried no MoE offload" is checkable after the fact and not just at launch.
- `detect-secrets` opens files with the locale default encoding and silently skips any it cannot decode ("we flat out ignore binary files"), so on Windows (cp1252) a doc containing `✏️`, `‌` or `←` is never scanned at all — always invoke it in UTF-8 mode (`python -X utf8 -m detect_secrets...`), on every OS.
- Regenerate `.secrets.baseline` **only** with the same `--exclude-files` pattern the hook in `.pre-commit-config.yaml` uses. A plain `detect-secrets scan` baselines the fiches and suite-definition snapshots that pattern exists to skip, and the hook then trims them back out on its next run (`pre_commit_hook.main` → `SecretsCollection.trim`: an entry whose file is in the passed filelist but yields no scan result is dropped), rewriting the file and exiting 3. It fails on Linux only: `load_from_baseline` runs each key through `convert_local_os_path`, so a baseline written on Windows has its `\` keys normalised to `/` on the runner and they finally match pre-commit's forward-slash filelist — on Windows they never match and the stale entries survive. A green local gate therefore proves nothing about CI here; the baseline's `results` must hold only files the hook actually scans.
- That `--exclude-files` pattern is coupled to the **filenames**, so renaming an excluded artifact silently un-excludes it. Suite snapshots moved to `<suite_id>@<suite_version>.json` and the pattern's `[a-z0-9-]+` stopped matching, so the hook flagged three public `prompt_set_hash` values as secrets. Widen the character class with the filename; never answer this by baselining the hash, which puts back exactly the entries the row above says the baseline must not hold.
- Runtime metrics are NOT reproducible across machines. Every result row must cite its hardware fiche by `fiche_hash` (CPU, RAM, GPU, driver, engine id + build + configuration hash, quant, roster entry + its sha256, and the raw flags as evidence); the fiche itself is stored write-once under `aidd_docs/results/fiches/<hash>.json` (`fiche_registry.py`) rather than flattened onto the row, and `wave-local-ai-v2-validate` proves a cited fiche was neither edited nor lost. A number without a fiche is meaningless.
- The fiche hash has **versioned projections** (`hardware.FICHE_PROJECTIONS`): `"1"` (with `llama_cpp_build`) for every fiche cited by a row below schema `"22"`, `"2"` (with `engine_id`, `engine_build`, `engine_config_hash`) from it, `"3"` (adding the declared `machine_id` and the `compute_mode`) from schema `"23"`. The citing row's `schema_version` picks the projection (`row_contract.fiche_projection_for`), never a key the fiche lacks, so changing the projection never rewrites a committed fiche; a story adding a projection key adds a projection version and rebases onto the latest one.
- A run names its **declared machine and compute mode** (`MACHINE_ID`, `COMPUTE_MODE`; no default, checked by `settings.require_run_profile` before any server starts). The machine is an entry of `aidd_docs/roster/machines.json` (`machines.py`), keyed by an id that names a declared configuration (a RAM upgrade is a new id), with every fact `{value, source, read_from}` marked `declared` or `not_yet_declared`. `cpu_only` launches `-ngl 0 --device none` and no `--n-cpu-moe`: with `-ngl 0` alone the CUDA build still drives the GPU during prompt processing. Both fields are inside projection `"3"`, so a `gpu` and a `cpu_only` run of one model on one machine are two fiches, and `compute_mode` is a runtime verdict-blocking field. PRD alignment: Methodology 14's "the same configuration hashes identically on a second machine" holds because the id names a configuration, not a box; Methodology 8's "shares the re-run's normalised fiche hash" still diverges from the code's blocking-field match (CPU, RAM, OS, driver and the machine id do not block), with `compute_mode` now in both.
- llama.cpp has architecture-specific flags that are not optional: `--load-mode none` is required when `--n-cpu-moe` is set (otherwise mmap pages from disk), `--jinja` is required for `<think>` tag parsing, `-np 1` avoids the 4-slot default allocation.
- MoE models (e.g. Qwen3) have a fixed number of experts; `--n-cpu-moe` has a hard ceiling and sweep gains are typically within measurement noise.
- Energy and carbon figures are ESTIMATES, not measurements, except GPU energy. Every
  result row carries three independently-labelled channels: `cpu_energy_kwh`/
  `cpu_energy_method` (always `estimated_tdp` — on Windows, CodeCarbon has no RAPL
  access and falls back to TDP-based estimation, which can be off by a factor of 2-3
  on a laptop under thermal throttling), `ram_energy_kwh`/`ram_energy_method` (always
  `estimated_constant` — a fixed W-per-8GB rule, never a measured channel on any
  platform), and `gpu_energy_kwh`/`gpu_energy_method` (`measured_nvml` only when
  CodeCarbon's `gpu_count` confirms NVML found a GPU, else `null`/`unavailable` — an
  *availability* check, never a magnitude check, so a GPU that genuinely drew ~0W in a
  short run stays distinguishable from no GPU present). `measure_energy` uses
  `codecarbon.OfflineEmissionsTracker` (declared `country_iso_code`, no live
  geolocation call). A local run's emissions are Scope 2 (`emissions_scope`
  `"scope_2"`, measured on this machine via `emissions.local_emissions`); a Mistral
  quality batch's emissions are Scope 3 (`"scope_3"`, estimated from a
  Wh-per-token formula since no on-machine energy exists to attribute to a network
  call) — the two are not directly comparable, and every Scope-3 row states that in
  its own `scope_comparability` field. See `docs/setup.md` section 5.
- Egress is recorded per call, not per row. `subject_egress` (schema "16", both
  row kinds) says where the subject prompt went: `none`, or the cloud provider
  id, held equal to `row_contract.subject_egress_for(provider)` on quality
  rows. A judged row's `judge_egress` separately records that the item and the
  subject output left the machine for judging. "Nothing left the machine"
  holds for a row only when both say so; the two are never merged.
