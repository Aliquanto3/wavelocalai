# Audit: original expectations vs specs vs implementation

> **Revised 2026-08-21, later the same day.** Sections 1-3 record the state at audit time
> (branch tip `8357d3b`, working tree dirty). Between then and the revision, a review ->
> plan -> implement loop shipped 20 commits and opened PR #1, closing the audit's single
> most damaging finding. **[Section 4](#4-revision--after-the-review-loop-pr-1)** records
> what changed, what is still open, and the revised plan. Where the two disagree, section 4
> wins. Rows and steps superseded below are marked inline.

- **Date**: 2026-08-21
- **Source of truth for expectations**: the founding Claude Chat prompt (French), restated below as E1..E14.
- **Spec artifacts inspected**: `aidd_docs/product/wave-local-ai-v2.md` (product brief), `aidd_docs/tasks/2026_08/2026_08_21-wave-local-ai-v2-benchmark-suite-prd.md` (PRD), `aidd_docs/backlog/` (1 epic, 4 stories), both plans under `aidd_docs/tasks/2026_08/`, `aidd_docs/memory/*`.
- **Implementation inspected**: `src/wave_local_ai_v2/*` (13 modules), `tests/*` (55 tests), repo root, GitHub remote (`gh api`).
- **Gates re-run today**: `uv run pytest -q` -> 55 passed; `uv run ruff check .` -> all passed; `uv run ruff format --check .` -> 63 files formatted; `uv run mypy src` -> no issues (13 files).

## 1. Expectation coverage matrix

Legend: **Spec** = where the expectation is written down; **Impl** = what exists in code/repo; **Status**: done / partial / spec-only / missing.

| # | Expectation (from founding prompt) | Spec | Impl | Status |
| --- | --- | --- | --- | --- |
| E1 | Time to first token | PRD goals; brief domain table | `timings.py` parses llama-server `ttft_ms`; server-reported only, independent cross-check attempted and reverted (`__init__.py:178-193`) | partial (done, uncorroborated) |
| E2 | Tokens/second | PRD goals | `prompt_tok_per_s`, `gen_tok_per_s` from server timings; validated against baseline | done |
| E3 | Environmental impact: energy AND carbon | PRD goals + AC ("headline number + retrievable calculation"); brief gotcha on `energy_method` | `energy.py` stores `energy_kwh` + `energy_method` only. **Carbon (kg CO2e) is not stored** (`tracker.final_emissions_data.emissions` discarded). No Scope-3 estimate for cloud models (PRD Dependencies names it). No "headline vs detailed calculation" split | partial |
| E4 | Memory consumed (RAM/VRAM) | PRD goals | `gpu.py` (VRAM used MiB, GPU draw W), `timings.read_process_rss` (process RSS) | done |
| E5 | Task performance across 10 use cases: classification, translation, doc comparison, text rewriting, code, agentic planning, agentic tool calling, web search, RAG answer, multilingual EN/FR/DE | PRD goals + AC (each use case has a suite or is explicitly marked out of scope); epic 1 scopes classification + translation + rewriting only and defers the other 7 to "later epics" that do not exist | Classification only: 10 hand-written items, exact-label match, Qwen3.6 vs Mistral. Translation and rewriting: stories `ready`, no plan, no code. Remaining 7: no epic, no story, no code | partial (1/10 implemented, 2/10 storied, 7/10 PRD-only) |
| E6 | Dense models proposed where more relevant (e.g. classification) | PRD goal + AC; `context_input/model_candidates.md`; story 4 (`tiny-dense-models-compared-alongside-moe.md`, `ready`) | None. Both CLIs hardcode `Qwen3.6-35B-A3B` (`__init__.py:26`, `quality_cli.py:28-29`) | spec-only |
| E7 | Hosted on GitHub, presentable to clients in pitches | PRD overview; brief audience "client decision makers see only the front end" | Repo public at `github.com/Aliquanto3/wave_local_ai_v2`; `origin/main` holds docs-only commits (`e4c06b6`), feature branch **never pushed**; `README.md` is **0 bytes**; no front end | partial (hosted, not presentable) |
| E8 | Python back end + React front end; scripts first to get early results | Brief summary names FastAPI + React. **PRD has no goal, story, or AC for the API or the front end** | Scripts-first: yes (`wave-local-ai-v2`, `wave-local-ai-v2-quality` entry points). No FastAPI, no React, no `frontend/` dir | scripts done; API/front **missing from PRD and code** |
| E9 | SOTA on-prem gen-AI tooling (uv not pip, etc.) | Architecture memory (uv, llama.cpp, ruff, mypy) | uv 0.11.7 + `uv.lock`, llama.cpp b10537, ruff/mypy, `requests` only (no SDKs by decision) | done |
| E10 | Particular care on benchmark test design so results are truly relevant | PRD says "defensible" and "reproducible" but sets **no measurable rigor criterion** (no seed/temperature policy, no repetition count, no spread reporting, no minimum suite size, no prompt-versioning rule). No spec artifact | Local generation runs at `--temp 1.0 --top-p 0.95` with **no seed** (`server.py:30-34`); Mistral call sends **no temperature, no seed** (`mistral_client.py:35`). Brief's own definition ("quality score: reproducible given model + prompt + seed") is therefore not met. Runtime harness is single-shot while `context_input/baseline_qwen36.md` itself requires `-r 5` minimum and says nothing under 10% spread is reliable. Classification suite = 10 items | **missing in spec, weak in code** -- **quality-side half FIXED, see [4.1](#41-what-the-review-loop-closed); runtime repetitions and the spec gap remain open** |
| E11 | Reproducible on other machines when cloned from GitHub | PRD goal + AC (fresh clone or container image, documented setup, no manual fixes) | `uv.lock` present; `.env.example` present; `README.md` empty; no `Dockerfile`/compose; `N_CPU_MOE=37`, `THREADS=8`, model filename and `LLAMA_CPP_BUILD="b10537"` hardcoded for the laptop (`server.py:24-29`, `__init__.py:25-27`); llama-server binary is an external, undocumented download | partial |
| E12 | CI/CD best practices: automated tests, versioning, hooks, containerization | PRD goals + AC (check suite must pass before mergeable; tag + changelog per release; container image). Epic 1 **explicitly excludes** these and points to "a separate, parallel epic" that was never written | **0 GitHub Actions workflows** (`gh api .../actions/workflows` -> 0); **no `.pre-commit-config.yaml`**, no hooks in `.git/hooks` (memory `architecture.md:9` and `coding-assertions.md:7` claim pre-commit "wires the fast gate" - false); no `CHANGELOG.md`; no git tag; no `Dockerfile`; no Dependabot/pip-audit; `main` unprotected; `pre-commit` and `detect-secrets` are installed as dev deps but unwired | spec-only (PRD), no epic/story, **not implemented** |
| E13 | Security for on-prem hosting + API-key auth for the two-machine demo | PRD goal + AC + non-goals (API-key-gated demo only, no multi-tenant); brief open decision. No epic/story; no threat-model/spec | Nothing to secure yet (no server process of ours). Good hygiene present: `.env` gitignored and untracked, llama-server bound to `127.0.0.1`, `.secrets.baseline` exists (but hook unwired). No API key, no auth, no CORS/bind policy | spec-only |
| E14 | Internet: web-search tool(s); Mistral + Google AI Studio as judges and as benchmark subjects | PRD goal + AC (>=2 web-search tools compared; 2 judges + agreement); story 2 (`judge-scoring...`, `ready`) | Mistral as **subject**: done (`mistral_client.py`). Google AI: no client. Judge role + inter-judge agreement: not started. Web search: no story, no code | partial (1 of 4 roles) |
| E15 | Code architecture, modularity, documentation, maintainability; showcase AI-built code quality to developer clients | PRD goal ("repo demonstrates engineering quality"); memory files | Small clean modules with docstrings, typed, 55 stubbed tests, two AIDD reviews on file. Weak spots: `README.md` empty; `aidd_docs/GUIDELINES.md` and `CONTRIBUTING.md` still hold template placeholders; both CLIs are hardcoded single runs with duplicated model constants; no coverage tooling (v1 reported 86.5%); `cli.md` memory stale (does not list `wave-local-ai-v2-quality`, says "implementation in progress") | partial |
| E16 | Developed with the AIDD framework | Memory bank, brief, PRD, epic, stories, plans, reviews all present | No `spec` artifact (`aidd-pm:04-spec`) anywhere; backlog, PRD and full-branch review are **untracked** (never committed); `GUIDELINES.md` unfilled | partial |

Counts: done 3 (E2, E4, E9) / partial 8 / spec-only 3 (E6, E12, E13) / missing-from-spec 2 (E8 API+front, E10 rigor).

Your suspicion is half right: CI/CD and security **are** in the PRD (goals + acceptance criteria), but they were never decomposed into an epic/stories/plan and nothing is implemented. The two things that are genuinely **absent from the specs** are the API + React front end (only named in the brief's summary sentence) and a measurable benchmark-rigor policy.

## 2. Cross-cutting findings

### 2.1 Spec gaps (PRD level)

1. No goal/AC for the FastAPI back end or the React front end (only "client decision makers see only the front end" in the brief). The API-key demo AC implies an HTTP surface that is nowhere specified.
2. No measurable benchmark-rigor policy: seeds, temperature, repetitions (N >= 5 per the baseline note), spread reporting (mean +/- std), minimum items per suite, prompt versioning, contamination avoidance, judge prompt versioning, agreement metric definition (which statistic: Cohen's kappa? exact-match rate?).
3. Carbon is conflated with energy: PRD says "carbon/energy figure" but the implemented schema carries energy only. The Scope-3 cloud estimate is in Dependencies, not in an AC.
4. Web-search tool comparison has an AC but no candidate tools, query set, or scoring rule even at a sketch level (PRD open question; still open).
5. Multilingual EN/FR/DE is listed as a use case but has no definition (its own suite? a dimension of every suite?).

### 2.2 Decomposition gaps (PRD -> backlog)

Only one epic exists. Missing epics the PRD requires:

- Engineering credibility infrastructure: CI (lint/type/test/coverage/secrets/dependency scan), pre-commit, Dockerfile + compose, release tag + CHANGELOG, README/setup for fresh-machine reproduction, branch protection.
- Measurement methodology: seed/temperature pinning, repetitions + spread, suite sizing rules, carbon fields + cloud Scope-3 estimate, headline vs detailed calc, fiche completeness (RAM speed, build auto-detected, optional signature/hash).
- API + front end + API-key remote demo.
- Second cloud provider + judge machinery (Google AI client, judge prompts, agreement) - partly covered by story 2 but Google client is a prerequisite not spelled out.
- Remaining use cases: doc comparison, code generation, agentic planning, tool calling, web search (>=2 tools), RAG answer, multilingual.

### 2.3 Memory / doc drift

- `architecture.md:9` and `coding-assertions.md:5-15`: pre-commit "wires the fast gate" -> no config exists, no hook installed. Either wire it or reword.
- `cli.md`: missing `wave-local-ai-v2-quality`; says "implementation in progress".
- `codebase-map.md`: no `tests/`, no `aidd_docs/results/`, no `aidd_docs/backlog/`.
- `GUIDELINES.md`, `CONTRIBUTING.md`: template placeholders still in place.
- `pyproject.toml`: `description = "Add your description here"`.

### 2.4 Branch hygiene (blocks everything else)

- Uncommitted: the full-branch review's two warning fixes (`quality_cli.py` shape guard + early key check, already applied in the working tree and covered by `test_quality_cli.py`), `CLAUDE.md` rules, `.secrets.baseline` regeneration, the runtime review's extra section.
- Untracked: `aidd_docs/backlog/`, the PRD, the full-branch review.
- `feat/runtime-measurement-harness` not pushed; `origin/main` is docs-only.

### 2.5 Implementation correctness of what exists

Both plans were reviewed (`approve` for runtime harness; `changes-requested` for the full branch with 2 warnings, both now fixed in the working tree). Code matches its plans. The caveats that matter for the founding expectations:

- TTFT is server-reported, uncorroborated (documented, acceptable for now).
- Quality scores are not reproducible (temp 1.0, no seed) - contradicts the brief's definition of a quality score.
- Runtime is single-shot; no repetition/spread.
- Carbon not persisted.
- `LLAMA_CPP_BUILD` is a constant, not detected from the binary; a different binary silently mislabels the fiche.

## 3. Plan to close the gaps

Conventions used below:

- **Model/effort** follows `CLAUDE.md` tiers. Haiku 4.5 low = trivial; Sonnet 5 medium = routine; Opus 5 high/xhigh = design, ambiguity, independent review. Fable 5 is not needed for any step here.
- **/clear**: "yes" when the step only needs files on disk (plans, PRD, memory); "no" when it depends on decisions made in the same conversation.
- AIDD dev loop for every story: `aidd-dev:01-plan` -> /clear -> `aidd-dev:02-implement` -> (same context) `aidd-dev:03-assert` -> /clear -> `aidd-dev:05-review` -> `aidd-vcs:01-commit` -> `aidd-vcs:02-pull-request`. For small, well-bounded stories, `aidd-orchestrator:01-sdlc` runs that loop autonomously in one shot.

### Step 0 - Close the current branch (today) -- SUPERSEDED by [4.3](#43-revised-plan), steps 0.1-0.3 done, 0.4-0.6 added

| Sub-step | Skill | Prompt | Model / effort | /clear |
| --- | --- | --- | --- | --- |
| 0.1 Finish the runtime review file | none (manual edit or ask) | "In `aidd_docs/tasks/2026_08/2026_08_21_runtime-measurement-harness/review.md`, fold the `### Independent re-derivation` section into `## Verification` (row `Unplanned`) and fix the findings header count so the file matches the review template." | Haiku 4.5 low | yes |
| 0.2 Commit in atomic slices | `aidd-vcs:01-commit` | "Commit the working tree as separate conventional commits: (1) `fix(quality): guard /completion shape and check Mistral key before local suite` (quality_cli.py, tests), (2) `docs: add PRD, backlog epic and stories, branch review`, (3) `chore(claude): add model/effort and next-skill rules` (CLAUDE.md), (4) `chore: regenerate detect-secrets baseline`. Do not push yet." | Sonnet 5 medium | yes |
| 0.3 Push + PR + merge | `aidd-vcs:02-pull-request` | "Push `feat/runtime-measurement-harness` and open a draft PR to `main` summarizing the two implemented plans and the review verdicts." Then merge it yourself on GitHub (no CI yet to wait on). | Sonnet 5 medium | no |

### Step 1 - Repair the specs (PRD and memory), before any new code

| Sub-step | Skill | Prompt | Model / effort | /clear |
| --- | --- | --- | --- | --- |
| 1.1 Shadow scan the PRD | `aidd-refine:03-shadow-areas` | "Scan `aidd_docs/tasks/2026_08/2026_08_21-wave-local-ai-v2-benchmark-suite-prd.md` for blind spots. Known suspects: no API/front-end goal or AC, no measurable benchmark-rigor policy (seed, temperature, repetitions, spread, suite size, prompt versioning, judge agreement metric), carbon vs energy conflation, undefined multilingual use case, web-search tool set undefined." | Opus 5 high | yes |
| 1.2 Refine the PRD | `aidd-pm:03-prd` | "Refine the existing PRD using the shadow report at `<path from 1.1>`. Add: (a) a goal + AC for a FastAPI results API and a React front end used in pitches, (b) a Benchmark Methodology section with measurable AC: every generation pinned to seed + temperature recorded in the row; runtime rows carry N>=5 repetitions with mean and std; each suite has a minimum item count and a version id; judged scores define the agreement statistic; (c) carbon (kg CO2e) persisted next to energy, plus a Scope-3 estimate for cloud rows; (d) a definition of the multilingual use case. Keep everything else." | Opus 5 high | no (keep 1.1 context) |
| 1.3 Refresh memory + fill placeholders | `aidd-context:02-project-memory` | "Refresh `aidd_docs/memory/`: `cli.md` must list both entry points; `architecture.md` and `coding-assertions.md` must stop claiming pre-commit is wired until it is; `codebase-map.md` must add `tests/`, `aidd_docs/results/`, `aidd_docs/backlog/`. Fill `aidd_docs/GUIDELINES.md` and `CONTRIBUTING.md` placeholders with this repo's real rules (English only, stubbed tests only, quality/runtime split, conventional commits)." | Sonnet 5 medium | yes |
| 1.4 Commit | `aidd-vcs:01-commit` | "Commit as `docs(prd): add API/front-end and benchmark-methodology criteria` and `docs(memory): refresh memory bank and guidelines`." | Haiku 4.5 low | no |

### Step 2 - Write the missing epics and stories

Run `aidd-pm:07-epic` once per epic, /clear between each (they only need the PRD on disk). Then `aidd-pm:02-user-stories` per epic, /clear first. Suggested epics and the prompt for each:

| Epic | Prompt for `aidd-pm:07-epic` | Model / effort |
| --- | --- | --- |
| E-A Engineering credibility infrastructure | "Frame an epic from the PRD for the engineering-credibility infrastructure epic 1 explicitly deferred: GitHub Actions CI (ruff, ruff format, mypy, pytest with coverage, detect-secrets, pip-audit/uv audit), `.pre-commit-config.yaml` wired and installed, `Dockerfile` + compose for a reproducible run, release tagging + `CHANGELOG.md`, README with fresh-machine setup (including llama-server binary acquisition), branch protection requiring CI. Outcome: a client engineer clones or pulls the image and reproduces a run; every merge is CI-gated." | Opus 5 high |
| E-B Measurement methodology | "Frame an epic making benchmark results defensible per the PRD's new methodology section: seed + temperature pinned per request for local (llama-server `/completion` params) and cloud (Mistral `random_seed`/`temperature`) and recorded in every row; runtime runs repeated N>=5 with mean/std and a `thermal_state` hint; carbon persisted; cloud Scope-3 estimate; fiche carries RAM speed and auto-detected llama.cpp build; server flags (threads, n-cpu-moe, model) configurable, not hardcoded." | Opus 5 high |
| E-C Results API + front end + API-key demo | "Frame an epic for a FastAPI service exposing quality and runtime tables (read-only), a React dashboard presentable in a client pitch (quality table, runtime table tagged by fiche, energy headline with drill-down, judge agreement), and the two-machine demo: bind address configurable, API key required for non-loopback access, CORS restricted, `.env`-only secrets. Non-goal: user accounts." | Opus 5 high |
| E-D Second provider and judge machinery | "Frame an epic for Google AI Studio as a second cloud provider (subject + judge), the judge protocol (versioned judge prompts, rubric, two judges from different families), and inter-judge agreement reporting - the prerequisite for epic 1 story 2." | Opus 5 high |
| E-E Remaining use cases | "Frame an epic sequencing the seven deferred use cases: document comparison, code generation, agentic planning, agentic tool calling, web research with >=2 search tools, RAG answer generation, multilingual EN/FR/DE. Each must land as its own story with a suite definition, scoring rule (deterministic or judged), and harness capability needed (tool-call transcript, retrieval corpus, search tool adapter)." | Opus 5 high |

Then for each epic: `aidd-pm:02-user-stories` with prompt "Slice `<epic path>` into ordered stories, each with acceptance that maps to a PRD AC." Sonnet 5 medium, /clear yes. Optional but worthwhile on E-B: `aidd-pm:08-three-amigos` (Opus 5 high) to stress the methodology before building.

Commit after each epic/story batch with `aidd-vcs:01-commit` (Haiku 4.5 low).

### Step 3 - Implement, in this order

Each line = one story through the dev loop. Model/effort given per phase: plan / implement / review.

| Order | Story (epic) | Why this order | Skills + prompt seed | Model / effort |
| --- | --- | --- | --- | --- |
| 3.1 | Pre-commit config + hooks installed + memory claim made true (E-A) | 1-hour win; makes every later commit gated | `aidd-orchestrator:01-sdlc`: "Implement story `<path>`: add `.pre-commit-config.yaml` running ruff check, ruff format, mypy src, detect-secrets with the existing baseline; document `uv run pre-commit install` in README." | Sonnet 5 medium end to end |
| 3.2 | GitHub Actions CI on push/PR (E-A) | Unblocks branch protection and the PRD AC "must pass before mergeable" | `aidd-dev:01-plan` then `02-implement`: "Workflow `ci.yml`: uv setup, `uv sync`, ruff check, ruff format --check, mypy src, pytest with coverage artifact, detect-secrets, dependency audit. Windows and Ubuntu matrix for the pure-Python tests (no llama-server)." Then enable branch protection requiring it. | plan Sonnet 5 medium / implement Sonnet 5 medium / review Opus 5 high |
| 3.3 | README + setup doc + pyproject description (E-A) | Repo is currently not presentable (0-byte README) | `aidd-dev:02-implement` from a short plan: "README: what it is, hardware class, setup with uv, `.env` keys, llama-server acquisition, run the two CLIs, results layout, quality/runtime split, energy_method caveat." | Sonnet 5 medium |
| ~~3.4~~ | ~~Seed/temperature pinning + recorded in rows (E-B)~~ | **DONE 2026-08-21**, eight steps early, via `2026_08_21_quality-sampling-reproducibility/` and `2026_08_21_mistral-model-preflight/`. See [4.1](#41-what-the-review-loop-closed). | - | - |
| 3.5 | Repetitions + mean/std + configurable flags + carbon persisted (E-B) | Completes runtime defensibility and portability to the Tour machine | plan: "N repetitions per runtime row set (env `RUNTIME_REPETITIONS`, default 5), aggregate row with mean/std per metric plus raw rows; persist `emissions_kg`; move `THREADS`, `N_CPU_MOE`, model file into settings with current values as defaults; detect llama.cpp build from `llama-server --version`." | Opus 5 high / Sonnet 5 medium / Opus 5 high |
| 3.6 | Dockerfile + compose + tag v0.1.0 + CHANGELOG (E-A) | Closes the container and release ACs | `aidd-orchestrator:01-sdlc` for Docker; then `aidd-vcs:03-release-tag`: "Cut v0.1.0 with notes covering the runtime harness, classification scoring, CI, Docker." | Sonnet 5 medium; tag Haiku 4.5 low |
| 3.7 | Google AI client as subject (E-D) | Prerequisite for judge + second comparison point | dev loop; plan prompt: "Mirror `mistral_client.py` for Google AI Studio generateContent, same error type pattern, same stubbed tests, key in settings/.env.example." | Sonnet 5 medium / Sonnet 5 medium / Opus 5 high |
| 3.8 | Rewriting suite + two judges + agreement (epic 1 story 2 + E-D) | Proves judged path | dev loop; Opus for plan (judge rubric design is a tradeoff-heavy step) | Opus 5 xhigh / Sonnet 5 medium / Opus 5 high |
| 3.9 | Translation suite, deterministic (epic 1 story 3) | Second deterministic use case, uses the pinned seeds from 3.4 | dev loop | Sonnet 5 medium / Sonnet 5 medium / Opus 5 high |
| 3.10 | Dense roster across the three suites (epic 1 story 4) | Answers the founding "dense where relevant" question | dev loop; plan must include model download doc and per-model flag sets (dense = no `--n-cpu-moe`) | Opus 5 high / Sonnet 5 medium / Opus 5 high |
| 3.11 | FastAPI results API + API key + bind policy (E-C) | First externally reachable surface; run `/security-review` before merge | dev loop; add `security-review` skill on the PR, and `aidd-dev:07-refactor` security axis if it flags anything | Opus 5 high / Sonnet 5 medium / Opus 5 high + security-review |
| 3.12 | React dashboard (E-C) | Pitch artifact | dev loop + `aidd-dev:11-browser-qa` for evidence videos | Opus 5 high / Sonnet 5 medium / Opus 5 high |
| 3.13 | Remaining use cases (E-E), one story each | Widest scope, last | dev loop per story; web-search story needs a spike first: `aidd-pm:05-spike` "Compare candidate search tools (self-hosted e.g. SearXNG vs one hosted API) for cost, rate limits, determinism of results" | spike Opus 5 high; stories Sonnet 5 medium / Opus 5 high review |

Milestone checks: after 3.6 and after 3.12, run `aidd-dev:04-audit` ("Audit the codebase across all seven pillars, read-only") with Opus 5 high, /clear yes, and feed the report into `aidd-dev:07-refactor` if anything ranks high.

### Context hygiene rules for the whole plan

- /clear before every `01-plan`, every `05-review`, every `04-audit`, every epic/story generation: these must read from disk, not from conversation residue.
- Do not /clear between `02-implement` and `03-assert`, nor between 1.1 and 1.2 (the shadow report informs the PRD refine).
- After a `05-review` returns `changes-requested`, fix in the same context (the findings are live there), then /clear and re-run review.
- Keep `aidd_docs/memory/` current after any step that changes stack, CLI surface, or gates (1.3 is the first pass; repeat after 3.2, 3.6, 3.11).

## 4. Revision - after the review loop (PR #1)

Written 2026-08-21 evening, at branch tip `803672a`, working tree clean.

Between the audit and this revision, `aidd-dev:03-assert`, `05-review`, `01-plan`, `02-implement`
and `07-refactor` ran repeatedly, producing 20 commits, two new plans with their reviews, and
PR #1 (open, unmerged). Gates re-run at `803672a`: `uv run pytest -q` -> 78 passed;
`uv run ruff check .` -> all passed; `uv run mypy src` -> no issues.

### 4.1 What the review loop closed

| Audit item | Outcome |
| --- | --- |
| Step 0.1-0.3 (close the branch) | Done except the merge. `main` is still at `e4c06b6`, a docs-only commit. |
| **Step 3.4 (seed/temperature pinning)** | **Done, eight steps early.** Sampling is pinned per `/completion` request (`quality_cli.py:41-60`: `seed`, `temperature: 0`, `top_k: 0`, `top_p: 1.0`, `presence_penalty: 0`), Mistral gets `temperature: 0` + `random_seed`, and every quality row carries its own `sampling` block. `server.build_flags` is untouched, so the runtime benchmark still measures the flag set it was validated against. |
| Reproducibility evidence | Two consecutive real runs: 40 rows in `aidd_docs/results/quality.jsonl`, 20 `(provider, item_id)` pairs, 0 label mismatches; local `0.60`/`0.60`, cloud `1.00`/`1.00`. This is the E10 quality-side claim actually falsified-and-survived, not asserted. |
| Not in the audit's plan, shipped anyway | Mistral pinned to the dated id `mistral-small-2603` (alias rotation defeats reproducibility), with a live `GET /v1/models` pre-flight before the expensive local suite; test suite repaired against "tests that stub out what they verify" and mutation-checked, 58 -> 78 tests. |

The audit's 🔴-equivalent finding (E10, "quality scores are not reproducible") is closed on the
quality side. The runtime side (repetitions, spread) and the PRD-level rigor gap are not.

### 4.2 What is still open

**Nine 🟡 from `2026_08_21_full-branch-review/review.md`, each re-verified against source at `803672a`:**

| Location | Issue |
| --- | --- |
| `mistral_client.py:82` | Cloud `content` is annotated `str` and never checked. The local path got this guard (`quality_cli.py:148`); the cloud path did not. A `content: null` reaches `normalize_label` as an uncaught `AttributeError`. |
| `server.py:104` | Readiness polls `/health` without confirming the responder is the process just spawned. A stale llama-server on port 8080 makes a doomed handle look ready and misattributes every metric. |
| `server.py:84` | Child stderr writes to a `TemporaryFile` whose parent handle closes when `start_server` returns; a mid-run crash surfaces with no diagnostics. |
| `energy.py:34` | `tracker.stop()` is unguarded in the `finally`. A CodeCarbon teardown failure destroys a completed measurement and replaces whatever exception `fn()` raised. |
| `quality_cli.py:98-114` | Local completions are still held in memory until after the cloud suite returns. A 429 mid-cloud discards the whole multi-minute local run and writes zero rows. The pre-flight covers only the foreseeable-at-second-0 failures. |
| `timings.py:45` | `read_process_rss` raises `psutil.NoSuchProcess`/`AccessDenied`, neither in `main()`'s except tuple, after the measurement already succeeded. |
| `cli.md`, `codebase-map.md` | Memory drift, unchanged since the audit (section 2.3). |
| both row builders | No `run_id`, no `captured_at`. Confirmed absent (`grep` returns nothing). Two runs of the same model are indistinguishable in either store. |
| `CLAUDE.md:33-39` vs `:16` | The new rules contradict the Communication rules without the scope/priority carve-out `CLAUDE.md:31` itself demands. |

Also still open and directly against E11 (reproducibility): `.gitignore:19` hides
`aidd_docs/results/`, and `git ls-files aidd_docs/results/` returns nothing -- so the only
evidence for the branch's headline tok/s claim is invisible to anyone reading PR #1.

Sixteen 🟢 remain, mostly real but small (`timings.py` catching only `KeyError`, no `OSError`
in either CLI's except tuple, `mistral_api_key` printable in `Settings.__repr__`, `gpu.py`'s
single `except` discarding a good VRAM reading when the power query fails, the model
constant and `/completion` POST duplicated across both CLIs, the classification story still
`status: ready` while its code ships, the PRD filename's dash-vs-underscore).

The `2026_08_21_mistral-model-preflight/review.md` findings were applied in `803672a` and are
closed. `2026_08_21_quality-sampling-reproducibility/review.md`'s three 🟡 are closed.

### 4.3 The process finding

Three review rounds ran review -> plan -> implement -> review. The first full-branch pass found
6 items, the regenerated pass found 29, and round 3 is now producing findings about *tests
asserting a URL against the module constant that produced it*. The findings are real; the
returns are diminishing. Meanwhile the structural gaps the audit exists to name have not moved:
0 CI workflows, 0 pre-commit hooks, 0 container image, 0 release tags, a 0-byte README, and 1
of 10 use cases. **PR #1 grows with each round; `main` does not move.**

This needs a process fix, not only a code fix: **a severity gate in `aidd_docs/GUIDELINES.md`
(still template placeholders) -- 🔴 and 🟡 block a merge, 🟢 goes to a tech-debt list.**
Without it, every `aidd-dev:05-review` restarts the treadmill on a branch that is already
three increments wide.

### 4.4 Revised plan

Steps 1, 2 and 3 of section 3 stand as written, minus step 3.4. Step 0 is replaced by:

| Sub-step | Skill | Prompt | Model / effort | /clear |
| --- | --- | --- | --- | --- |
| 0.4 One consolidated hardening plan (not six small ones) | `aidd-dev:01-plan` | "Plan one hardening increment closing the nine open 🟡 listed in `aidd_docs/tasks/2026_08/2026_08_21_expectations-gap-audit/audit-and-plan.md` section 4.2, plus: add `run_id` and `captured_at` (UTC ISO-8601) to both row builders; un-gitignore `aidd_docs/results/` and commit the reference rows so the acceptance evidence survives outside this machine; add `OSError` to both CLIs' except tuples; declare `mistral_api_key` with `field(repr=False)`. Group phases by module, not by finding." | Opus 5 high | yes |
| 0.5 Implement and assert | `aidd-dev:02-implement` then `03-assert` | "Implement `<plan path>` phase by phase." | Sonnet 5 medium | no (keep 0.4) |
| 0.6 Review once, then merge | `aidd-dev:05-review` | "Review the hardening increment on all three axes." Any 🟢 it returns goes to `aidd_docs/backlog/tech-debt.md` -- do not open another plan. Then merge PR #1. | Opus 5 high | yes |
| 0.7 Write the severity gate | folded into step 1.3 | Add to `aidd_docs/GUIDELINES.md`'s "Validation depth": 🔴/🟡 block a merge, 🟢 is logged to `aidd_docs/backlog/tech-debt.md` and never blocks. | Haiku 4.5 low | no |

Two knock-on effects on section 3:

- Step 3.5 shrinks to repetitions + mean/std + carbon + configurable flags + build
  auto-detection. If 0.4 lands `run_id`, step 3.5 inherits the run-grouping key it needs.
- Step 3.4 is struck. Nothing else reorders.

Everything structural in section 1 is untouched by this revision: CI/CD (E12), security and
the API-key demo (E13), the API and front end (E8), the dense roster (E6), Google AI and the
judge machinery (E14), web search, and seven of ten use cases (E5). That remains the bulk of
the work.

## 5. Revision 2 - after the PR #1 hardening increment

Written 2026-08-21, at branch tip `da6c431`, working tree clean, branch pushed (origin matches
HEAD). Where this section disagrees with sections 1-4, this section wins.

Gates re-run at `da6c431`: `uv run pytest -q` -> 99 passed; `uv run ruff check .` -> all passed;
`uv run ruff format --check .` -> 81 files formatted; `uv run mypy src/` -> no issues (13 files).

### 5.1 What closed since section 4

| Section 4 item | Outcome at `da6c431` |
| --- | --- |
| 0.4 consolidated hardening plan | Done: `2026_08_21_pr1-hardening/plan.md`, 5 phases, marked implemented. |
| 0.5 implement + assert | Done: 9 commits `a0b7b1a..da6c431`; the nine 🟡 of section 4.2 are all closed (`run_id`/`captured_at` in both row builders, port-occupancy refusal, readable child stderr, guarded tracker teardown, `NoSuchProcess`/`AccessDenied` -> `None`, cloud `content: null` surfaced as `MistralRequestError`, local rows persisted before the cloud suite, `OSError` in both except tuples, `repr(Settings)` hides the key). |
| 0.6 review once | Done: `2026_08_21_pr1-hardening/review.md` -> **approve**, 15/15 verified, 1 🟢 (`server.py:191` stderr tail seek while child alive, deferred). |
| Results evidence (E11) | Done: `aidd_docs/results/{runtime,quality}-reference.jsonl` + README tracked; live stores ignored by `*.jsonl` / `!*-reference.jsonl`. |
| Memory drift (2.3) | Done for `cli.md`, `codebase-map.md`, `architecture.md`, `coding-assertions.md`. |
| `CLAUDE.md` contradiction | Done: Communication bullet names the two scoped exceptions. |
| **0.6 merge PR #1** | **Not done.** PR #1 `OPEN`, `mergeStateStatus: CLEAN`, `mergeable: MERGEABLE`, not draft, 43 commits, 75 files. `origin/main` still at `e4c06b6` (docs only). |
| **0.7 severity gate in `GUIDELINES.md`** | **Not done.** `aidd_docs/GUIDELINES.md` still holds the template placeholders verbatim. |
| `aidd_docs/backlog/tech-debt.md` | **Not created.** The 16 🟢 of the full-branch review and the 1 🟢 of the hardening review have no home. |
| Classification story status | Still `status: ready` while its code, evidence and review have shipped. |

### 5.2 Expectation matrix, current status

Only the status column is restated; the spec/impl columns of section 1 still describe the
artifacts accurately unless a note says otherwise.

| # | Expectation | Status at `da6c431` | Delta vs section 1 |
| --- | --- | --- | --- |
| E1 | TTFT | partial (server-reported, uncorroborated) | none |
| E2 | Tokens/s | done | none |
| E3 | Energy AND carbon | partial: `energy_kwh` + `energy_method` only; `emissions` still discarded (`energy.py:48-55`); no cloud Scope-3; no headline/detail split | none |
| E4 | RAM/VRAM | done | none |
| E5 | 10 use cases | partial: 1/10 implemented, 2/10 storied, 7/10 PRD-only | none |
| E6 | Dense where relevant | spec-only: both CLIs still hardcode `Qwen3.6-35B-A3B` | none |
| E7 | GitHub-hosted, pitchable | partial: branch pushed, PR #1 mergeable, `main` still docs-only, `README.md` 0 bytes, no front end | branch now on origin |
| E8 | Python back + React front, scripts first | scripts done; API/front absent from PRD Goals/AC and from code | none |
| E9 | SOTA on-prem tooling (uv...) | done | none |
| E10 | Benchmark rigor | quality side done (pinned sampler, reproduced twice, evidence committed); runtime side single-shot, no spread; no PRD rigor criterion | evidence now tracked |
| E11 | Reproducible on another machine | partial: lockfile, `.env.example`, reference rows tracked; README empty, no container, `N_CPU_MOE`/`THREADS`/model file/`LLAMA_CPP_BUILD` hardcoded | evidence now tracked |
| E12 | CI/CD: tests, versioning, hooks, containers | spec-only: 0 workflows, no `.pre-commit-config.yaml`, no tag, no `CHANGELOG.md`, no `Dockerfile`, `main` unprotected | none |
| E13 | On-prem security + API-key demo | spec-only; hygiene fine (loopback bind, `.env` ignored, key hidden from repr, port-occupancy refusal) | hygiene improved |
| E14 | Internet: web search, Mistral + Google as subjects and judges | partial: Mistral subject only | none |
| E15 | Architecture, modularity, docs, showcase quality | partial: 13 typed modules, 99 stubbed tests, 4 reviews on file; README 0 bytes, `pyproject` description placeholder, `GUIDELINES.md` placeholders, no coverage tooling | tests 55 -> 99, memory current |
| E16 | Built with AIDD | partial: full artifact chain except no `aidd-pm:04-spec`, `GUIDELINES.md` unfilled, classification story not transitioned | backlog/PRD now committed |

Counts: done 3 / partial 9 / spec-only 3 / missing-from-spec 2 (E8 API+front, E10 rigor). The
shape of the gap is unchanged: the branch is hardened; the product is 1 use case, 1 cloud
provider, 1 model, no front end, no CI.

### 5.3 Revised plan

Sections 3 and 4.4 stand, with these replacements. Conventions as in section 3.

**Step 0 (finish today, no new code review):**

| Sub-step | Skill | Prompt | Model / effort | /clear |
| --- | --- | --- | --- | --- |
| 0.8 Merge PR #1 | none (`gh pr merge 1 --merge`) | Merge commit, not squash: the 43 commits are the audit trail the reviews cite by hash. No CI to wait on. Then `git switch main && git pull`. | manual | - |
| 0.9 Severity gate + tech-debt log + story transition | `aidd-context:10-learn` then `aidd-vcs:01-commit` | "Fill `aidd_docs/GUIDELINES.md` with this repo's rules: English only; tests stub HTTP and never start llama-server; quality/runtime tables never merged; fast gate before commit, pytest before push; **severity gate: 🔴 and 🟡 block a merge, 🟢 goes to `aidd_docs/backlog/tech-debt.md` and never blocks, and a branch gets at most one post-implementation review**. Create `aidd_docs/backlog/tech-debt.md` seeded with the 16 🟢 of `2026_08_21_full-branch-review/review.md` and the 1 🟢 of `2026_08_21_pr1-hardening/review.md`, one line each with location. Set `status: done` on `deterministic-classification-scoring-proves-quality-table-split.md`. Set `pyproject.toml` description." Commit as `docs(guidelines): add severity gate and tech-debt log`. | Sonnet 5 medium | yes |

**Step 1 (PRD repair)**: unchanged from section 3, steps 1.1-1.4. Drop the memory-drift half
of 1.3 (done); keep the `GUIDELINES.md` half only if 0.9 was skipped.

**Step 2 (epics E-A..E-E)**: unchanged from section 3.

**Step 3 (implementation order)**: section 3 order with two changes:

- **3.3 README moves first**, before 3.1 and 3.2. A public repo with a 0-byte README is the
  single most visible failure of E7/E15 and needs no infrastructure to fix. Prompt stays as
  written; add "link the two reference JSONL files and the results README as the evidence".
- 3.4 stays struck; 3.5 stays shrunk as in section 4.4.

Resulting order: 3.3 README -> 3.1 pre-commit -> 3.2 CI + branch protection -> 3.5 repetitions
+ carbon + configurable flags -> 3.6 Docker + v0.1.0 tag -> 3.7 Google client -> 3.8 rewriting +
judges -> 3.9 translation -> 3.10 dense roster -> 3.11 FastAPI + API key -> 3.12 React ->
3.13 remaining use cases. Milestone audits after 3.6 and 3.12 as in section 3.

Context hygiene rules of section 3 stand. One addition from section 4.3: after any
`aidd-dev:05-review` that returns `approve`, merge; do not open another review on the same
branch.

## 6. Extension - research-publication ambitions (2026-09-06)

New objective set by the owner (source docs to land in `context_input/`): a publication-grade
benchmark across three machines (tower R5 7600/32GB DDR5/RTX 3050 8GB; laptop R7 5800H/32GB
DDR4/RTX 3060 6GB; pro PC 16GB RAM no GPU), multi-family roster (>=2 families per size class),
publication-level suites (public-benchmark subsets, contamination-marked), engine
(llama.cpp/Ollama) + prompt-variant (baseline/Caveman-style/GBNF-DSL/LLMLingua-2) + agentic
harness as row dimensions, bootstrap CI + paired Wilcoxon, judges re-targeted to Z.ai GLM +
DeepSeek (paid, ~$10 campaign; GPT-5.6 Luna calibration on 10%; Google/Mistral demoted to
subjects), CC-BY 4.0 on suite items + bundle (code stays MIT), tabular export; wattmeter
explicitly out of scope; venue: blog/Wavestone first, arXiv optional, JOSS later-optional.

Plan: Phase P (spec): P1 commit source docs; P2 PRD amendment; P3 new epics E-F machines,
E-G statistics+suite growth, E-H engine+variant matrix, E-J data publication; P4 amend E-D
(judges) and E-E (harness dimension); P5 three-amigos on E-G. Then: finish E-C stories 2-3
(hold 4 until dimensions land), audit + v0.2.0, E-F, E-G, E-D judged phase + rewriting,
E-H, E-E, E-J continuous. Decisions logged: public subsets per suite; providers/budget
confirmed; 3 machines ready.
