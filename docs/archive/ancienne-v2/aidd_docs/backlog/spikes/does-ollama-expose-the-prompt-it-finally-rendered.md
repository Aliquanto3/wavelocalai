---
type: spike
status: resolved
source: aidd_docs/backlog/epics/the-engine-and-the-prompt-variant-are-measured-not-assumed.md
parents:
  - aidd_docs/backlog/stories/ollama-quality-rows-pass-a-prompt-parity-gate-or-publish-as-observations.md
---

# Spike: Does Ollama expose the prompt it finally rendered

## Question

Can the harness obtain, from a running Ollama instance, the exact string the model received after Ollama's own chat templating, by a documented or observable path, so that it can be published under Methodology 2 and compared byte for byte with llama.cpp's `/apply-template` output for the same model and item?

## Decision

Whether Ollama's quality rows (order 7) can carry a rendered prompt at all, and with which `prompt_capture` value: `captured` (the engine returns what it received), `reconstructed` (rendered by a separate call on the same template, as llama.cpp's path does today), or an explicit absence. The answer decides whether cross-engine quality cells can be paired comparisons or only observations, under the epic's prompt-parity decision. It also decides how the Ollama thinking switch is verified: by comparing a render with the switch against one without it, or not at all.

## Bounds

- Evidence needed: against a running pinned Ollama instance (the same one spike `can-a-pinned-ollama-build-serve-the-roster-gguf-under-the-runtime-protocol` installs), for `qwen3-0.6b-q8` and two classification items, one EN and one FR: every candidate path tried and its captured output (a render or template endpoint if one exists, the template the server reports for the model, a raw or pre-templated request mode, server debug logging), and for each the string obtained; the same items rendered by llama.cpp's `/apply-template` on the same GGUF; the byte-level diff between the two; whether the path still reflects the thinking switch when it is set. A path that requires logging the prompt to a file is recorded with where that file lives, because rows and logs have different retention rules.
- Stop when: one path is shown to return the rendered string with its capture kind named, and the diff against llama.cpp is recorded, or every candidate path is shown to fail, which is recorded as "no rendered prompt available" with the attempts.

## Investigation

Desk research only, on 2026-10-02: no Ollama binary was executed. Source citations are to tag `v0.35.1` (commit `b0c1ca4f7549d7acdfa52a7dcffc934bc63a43ce`, latest stable on 2026-10-02) of `github.com/ollama/ollama`, read at `https://github.com/ollama/ollama/blob/v0.35.1/<path>` (read 2026-10-02). How the imported roster GGUF is routed (native mode, rendered by the bundled llama.cpp `b11232` `llama-server` from the GGUF's own jinja template) is recorded in spike `can-a-pinned-ollama-build-serve-the-roster-gguf-under-the-runtime-protocol.md`.

| Attempt | Evidence | Result |
| ------- | -------- | ------ |
| Searched the API types for a field returning the rendered prompt | `api/types.go` (lines 119-121, 168-170, 541-553, 947) | `ChatRequest` and `GenerateRequest` accept `_debug_render_only` (bool, documented in source as "a debug option that ... returns the rendered template instead of calling the model"); `ChatResponse` and `GenerateResponse` carry `_debug_info.rendered_template` and `image_count`. No other response field carries a prompt. The field is absent from `docs/api.md` and the other docs at the tag: undocumented, underscore-prefixed, so not a stable contract. |
| Read where `_debug_info` is filled | `server/routes.go` (lines 659-670 generate, 2911-2921 Go-rendered chat, 3100-3120 native chat) | `_debug_info` is set only in the `_debug_render_only` branches, which return before any generation. A real generation never returns the string the model received: no `captured` path exists. |
| Read what the native-mode render call does | `server/routes.go` `handleNativeChat` (lines 3076-3120); `llm/llama_server.go` `ApplyChatTemplate` (lines 1944-1988), `llamaServerChatRequest` (lines 2240-2295) | For a native-mode model, `_debug_render_only` builds the same request body the generation would send (messages, `chat_template_kwargs` from `think`, tools, format) and posts it to the bundled `llama-server`'s own `/apply-template`, returning its `prompt`. The generation itself posts that body to `/v1/chat/completions`, which renders inside llama-server. The render is therefore a separate call on the same template and the same server process: `prompt_capture: reconstructed`, the same kind the llama.cpp rows carry today. |
| Read the `/api/generate` native path | `server/routes.go` `GenerateHandler` (lines 585-670) | On `/api/generate` (non-raw) a native-mode model's prompt is rendered by `ApplyChatTemplate` and the resulting string is what is sent to `/completion`; `_debug_render_only` returns that same string. |
| Read the thinking switch on the render path | `llm/llama_server.go` `llamaServerChatTemplateKwargs` (lines 2296-2310) | `think: false` / `true` becomes `chat_template_kwargs: {"enable_thinking": false/true}` in the body sent to both `/apply-template` and `/v1/chat/completions`; Qwen3's template renders differently under the two values, so the switch can be verified by comparing two renders. |
| Read the raw (pre-templated) mode | `docs/api.md` (lines 57, 331); `llm/llama_server.go` `completionPrompt` (lines 246-257) | `/api/generate` with `raw: true` sends the caller's string without templating, so the harness could send llama.cpp's `/apply-template` output verbatim. Ollama strips one leading BOS text from it when the tokenizer adds BOS itself. This bypasses Ollama's templating: parity by construction, at the cost of not measuring the prompt an Ollama user's chat call would get, and the thinking switch is then whatever the string contains. |
| Read `/api/show` and the debug logging options | `api/types.go` `ShowResponse` (lines 742-761); `envconfig/config.go` (lines 199-220, 315-316); `docs/windows.mdx` (lines 66-69) | `/api/show` returns `template` (the Go TEMPLATE, expected empty for a native-mode import), `renderer`, `parser`, `model_info`. `OLLAMA_DEBUG_LOG_REQUESTS` logs inference request bodies and replay curl commands to a temp directory (request JSON, not the rendered prompt). `OLLAMA_DEBUG=1` raises log level; server logs go to `%LOCALAPPDATA%\Ollama\server.log` for the app or stderr for `ollama serve`. Whether either log holds the rendered prompt is not shown by source. |

Evidence, decisions and assumptions:

- Evidence: the Result column above.
- Decisions already taken: the epic's decision "Prompt parity across engines is a gate, not an assumption" and its current llama.cpp path (`/apply-template`, `prompt_capture: reconstructed`) (`aidd_docs/backlog/epics/the-engine-and-the-prompt-variant-are-measured-not-assumed.md`).
- Assumptions: (1) the imported Qwen3 GGUF runs in native mode (verified live by `/api/show` returning empty `template`, `renderer`, `parser`); (2) llama-server's `/apply-template` and `/v1/chat/completions` render one body identically inside the same process, which is how llama.cpp's own reconstructed path is already treated; (3) the b11232 jinja engine may render differently from b10537 on the same template, which only the byte diff shows.

### Live session on Ollama v0.35.1, 2026-10-04

Run by the execution spike `aidd_docs/backlog/spikes/are-the-three-ollama-spikes-live-captures-obtainable-in-one-ollama-v0-35-1-session.md` (runbook steps 3, 7, 10 and 12, 2026-10-04 00:20 to 00:22, reference laptop). Evidence folder `aidd_docs/tasks/2026_10/2026_10_04_local-spike-runs/ollama-v0.35.1/`, written `E/` below: the cited files copied from the capture folder `D:\ia\ollama-v0.35.1-captures`, under their original names; `33-show.excerpt.json` is a labelled excerpt. Items: `billing-01` (first EN) and `billing-fr-01` (first FR) of `classification-support-routing` version 4.

| Attempt | Evidence | Result |
| ------- | -------- | ------ |
| `_debug_render_only: true` on `POST /api/chat`, two items, `think` false and true | `E/50-ollama-render-*.json` and their `.body.json`; `E/http-status.txt` | All four HTTP 200. Each returns `_debug_info.rendered_template` with an empty `message` and `done: false`: a render without a generation. The JSON escapes the turn markers' angle brackets as `\u003c` and `\u003e`. |
| llama.cpp b10537 `/apply-template` on the same GGUF and the same bodies | `E/21-llamacpp-render-*.json` and their `.body.json`; `E/00-llama-server-version.txt`; `E/20-llamacpp-serve.log` | Server `version: 0.1.2-dev (build 10537, commit bf0040e15)`, loading `Qwen3-0.6B-Q8_0.gguf`; four `prompt` strings. |
| Byte-level diff, and the thinking switch on each engine | `E/A0-render-diff.txt` | Identical on all four: `billing-01` 319 bytes (`think` false) and 300 bytes (true), `billing-fr-01` 364 and 345 bytes, first difference `identical`. The `think` on and off renders differ on both engines for both items. |
| `_debug_render_only` on `POST /api/generate` (templated) | `E/51-ollama-generate-render-billing-01-think-false.json` and its `.body.json` | Same string as the chat render and the llama.cpp render for `billing-01`, `think: false` (checked by string equality, 319 bytes). |
| Raw pre-templated mode fed llama.cpp's own render | `E/52-ollama-raw-billing-01.json` and its `.body.json`, `E/62-unconstrained-billing-01.json`, last line of `E/A0-render-diff.txt` | HTTP 200, output `technical`, `prompt_eval_count` 61; the templated chat call on the same item and sampling also counts 61 prompt tokens and answers `technical`. |
| Template and routing the server reports | `E/33-show.excerpt.json`; `E/30-serve-roster.log` lines 268, 273 | `/api/show` returns the GGUF's own jinja template, no `renderer`, no `parser`; the log shows `selected=gguf_chat_template` and each generation sent as a `llama-server chat request` to the bundled runner, which renders it there. The `_debug_render_only` string is therefore a separate render of the same body, not the string the generation received. |
| Server debug log and request logs searched for a rendered prompt | `E/80-log-rendered-prompt.txt`, `E/80-request-logs.txt`, `E/RUN-NOTES.md` (section "Runbook gaps observed") | The turn-marker hits in the server log are the GGUF template (template detection and the GGUF metadata line) and the runner's `example_format` init line: no rendered request prompt. The request logs, written to `%TEMP%\ollama-request-logs-*` (deleted by the runbook's cleanup), hold the client request bodies, with angle brackets escaped, so they record requests, not a rendered prompt. No log yields a `captured` prompt. |

Desk assumptions checked: (1) native mode holds (log line 268), although `/api/show` `template` carries the GGUF template rather than being empty; (2) not observable: no captured path exposes the string the runner rendered inside the generation, only the token count, which matches; (3) b11232 (bundled) and b10537 render these four bodies identically.

## Outcome

- Result: resolved. Ollama v0.35.1 exposes a rendered prompt of kind `reconstructed`, never `captured`: `POST /api/chat` with `_debug_render_only: true` returns `_debug_info.rendered_template`, rendered by the bundled llama-server from the same request body the generation would send. For `qwen3-0.6b-q8` on `billing-01` and `billing-fr-01`, `think` false and true, that string is byte-identical to llama.cpp b10537's `/apply-template` output, so the parity record for these items is `identical`. The thinking switch is verifiable by comparing two renders: they differ on both engines. No generation response or log carries the prompt the model received. The field is undocumented and underscore-prefixed, so the engine entry pins the Ollama version it was verified on (`0.35.1`). Fallback, not needed here: `raw: true` with llama.cpp's render (parity by construction). Decisive evidence: `aidd_docs/tasks/2026_10/2026_10_04_local-spike-runs/ollama-v0.35.1/A0-render-diff.txt`.
- Confidence: high for the four renders on this version and model; parity is shown on two items and a single user message only.
- Remaining uncertainty: parity on other items, other roster models, and bodies with a system message or tools is not shown; that the runner's in-generation render equals its `/apply-template` render stays an assumption, consistent with the equal 61-token prompt counts of the raw and templated calls.

## Follow-up

- `aidd_docs/backlog/stories/ollama-quality-rows-pass-a-prompt-parity-gate-or-publish-as-observations.md`: no longer blocked by this spike; blocked through `depends_on` on order 6 only. Captured answer: Ollama rows carry `prompt_capture: reconstructed` through `_debug_render_only`; the parity command's record for `qwen3-0.6b-q8` on these two items would read `identical`; the `think` switch is verifiable by render comparison.
