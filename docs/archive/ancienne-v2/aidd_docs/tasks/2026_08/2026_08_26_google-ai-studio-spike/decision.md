# Decision: Google AI Studio's API surface, confirmed live

- **Spike**: `aidd_docs/backlog/spikes/google-ai-studio-api-surface-is-confirmed-live.md`
- **Epic**: `aidd_docs/backlog/epics/any-open-ended-output-carries-two-judges-or-an-honest-flag.md`
- **Investigated**: 2026-08-27
- **Method**: live HTTP calls with `requests` only, no SDK, using `GOOGLE_API_KEY` from `.env`; plus the live discovery document and the official documentation pages fetched the same day. Every fact below cites either a captured request/response or a URL. The API key is redacted as `<REDACTED>` throughout.
- **Outcome**: resolved. Free-tier access on terms comparable to Mistral's is **confirmed**. Go for order 2.

> **This file is the evidence record.** The durable facts it establishes — the pinned id, the endpoints, the sampling block, the `finishReason` mapping, the rate limits and the price — are carried in `aidd_docs/memory/external/google-ai-studio-api.md`, which is what `google_client.py` cites and what gets updated when the API moves. Read that one to write code; read this one to see what proves it.

## Decision

| Item | Value |
| --- | --- |
| Model id to pin | `gemini-3.5-flash-lite` |
| Snapshot marker to record on the row | the entry's `version` field, `3.5-flash-lite-07-2026` today, re-read at pre-flight |
| API version for the row | `v1` (path segment) |
| Base URL | `https://generativelanguage.googleapis.com/v1` |
| Catalog endpoint | `GET /v1/models` and `GET /v1/models/gemini-3.5-flash-lite` |
| Generation endpoint | `POST /v1/models/gemini-3.5-flash-lite:generateContent` |
| Token pre-flight endpoint | `POST /v1/models/gemini-3.5-flash-lite:countTokens` |
| Auth | header `x-goog-api-key: <key>` |
| Seed | exposed, accepted, and honoured — `generationConfig.seed` |
| List price (paid, Standard tier) | $0.30 / 1M input, $2.50 / 1M output |
| Free-tier price | $0.00, with prompts and responses used to train Google's products |

Rationale for the id, in one line each:

- It is callable. `gemini-2.5-flash`, the obvious analogue of `mistral-small`, is **listed on the catalog but 404s on `generateContent`** for this key (evidence Q1.3) — catalog presence is not availability on this provider.
- It is the id the floating alias resolves to today: `gemini-flash-lite-latest` answered with `"modelVersion": "gemini-3.5-flash-lite"` (evidence Q1.4), the same relationship `mistral-small-latest` → `mistral-small-2603` records.
- It emits no thinking tokens by default, so `candidatesTokenCount` is the whole billable output and the row's token accounting stays honest (evidence Q2.6). `gemini-3.6-flash` and `gemini-3.5-flash` both spent 84-88 hidden `thoughtsTokenCount` on a one-word answer.
- It is the cheapest text model on the live listing that answers, which is the role `mistral-small-2603` plays in the existing suite.

## Evidence

### Q1 — Live catalog, and the shape of its ids

**Q1.1 The endpoint exists, on both API versions, and requires a key.**

```
GET https://generativelanguage.googleapis.com/v1beta/models?pageSize=200
    header  x-goog-api-key: <REDACTED>
-> 200, 52 models, nextPageToken: null

GET https://generativelanguage.googleapis.com/v1/models?pageSize=200
    header  x-goog-api-key: <REDACTED>
-> 200, 19 models, nextPageToken: null

GET https://generativelanguage.googleapis.com/v1beta/models?key=<REDACTED>   -> 200
GET https://generativelanguage.googleapis.com/v1beta/models   (no auth)      -> 403
{
  "error": {
    "code": 403,
    "message": "Method doesn't allow unregistered callers (callers without established identity). Please use API Key or other form of API consumer identity to call this API.",
    "status": "PERMISSION_DENIED"
  }
}
```

Both the `x-goog-api-key` header and the `?key=` query parameter authenticate. The header is chosen so the key never reaches a URL, a log line, or a redirect.

**Q1.2 The ids are release ids, not dated snapshots. The date lives in a `version` field.**

```
GET https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash-lite
    header  x-goog-api-key: <REDACTED>
-> 200
{
  "name": "models/gemini-3.5-flash-lite",
  "version": "3.5-flash-lite-07-2026",
  "displayName": "Gemini 3.5 Flash Lite",
  "description": "Gemini 3.5 Flash Lite",
  "inputTokenLimit": 1048576,
  "outputTokenLimit": 65536,
  "supportedGenerationMethods": [
    "generateContent", "countTokens", "createCachedContent", "batchGenerateContent"
  ],
  "temperature": 1,
  "topP": 0.95,
  "topK": 64,
  "maxTemperature": 2,
  "thinking": true
}
```

No dated id is addressable. Every plausible dated form 404s:

```
GET /v1beta/models/gemini-2.5-flash-001            -> 404 "Model is not found: models/gemini-2.5-flash-001 for api version v1beta"
GET /v1beta/models/gemini-2.5-flash-002            -> 404 (same shape)
GET /v1beta/models/gemini-2.5-flash-lite-001       -> 404 (same shape)
GET /v1beta/models/gemini-3.7-flash-08-2026        -> 404 (same shape)
GET /v1beta/models/gemini-2.5-flash-preview-05-20  -> 404 (same shape)
```

**This is a weaker pin than `mistral-small-2603`, and the difference has to be recorded rather than smoothed over.** Mistral publishes an id that is itself the snapshot; Google publishes a release id whose snapshot is a separate, read-only `version` string. Pinning `gemini-3.5-flash-lite` pins a release, not a build. The pre-flight must therefore read `version` and the row must publish it, so that a silent rotation from `3.5-flash-lite-07-2026` to a later build is visible as a changed field on the row instead of being invisible the way a `-latest` alias would be.

The catalog carries no deprecation or retirement field at all — there is no `deprecation` or `deprecation_replacement_model` equivalent to the one `mistral_client._deprecation_notice` reads. Retirement surfaces only as the 404 in Q1.3, that is, after it has already broken the call.

**Q1.3 Listed does not mean callable. The 2.5 family is on the catalog and refuses generation.**

```
POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent
    header  x-goog-api-key: <REDACTED>
    {"contents": [{"parts": [{"text": "Classify the sentiment ..."}]}]}
-> 404
{
  "error": {
    "code": 404,
    "message": "This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.6-flash for the latest features and improvements.",
    "status": "NOT_FOUND"
  }
}
```

The same 404 came back for `gemini-2.5-flash-lite` (pointing at `gemini-3.5-flash-lite`) and `gemini-2.5-pro` (pointing at `gemini-3.1-pro-preview`), while `GET /v1beta/models/gemini-2.5-flash` returned 200 with a full entry. **A `check_model_available` written the way the Mistral one is — presence on `GET /models` — would pass on `gemini-2.5-flash` and then fail on every generation.** The Google pre-flight has to be a real `generateContent` call, or the catalog check has to be understood as necessary and not sufficient.

**Q1.4 Which ids actually answer, and what an alias resolves to.**

One `POST .../{id}:generateContent` per row, body `{"contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}], "generationConfig": {"temperature": 0, "maxOutputTokens": 512}}`:

| id | status | `modelVersion` in the response | `thoughtsTokenCount` |
| --- | --- | --- | --- |
| `gemini-2.5-flash` | 404 | — | — |
| `gemini-2.5-flash-lite` | 404 | — | — |
| `gemini-2.5-pro` | 404 | — | — |
| `gemini-3.1-flash-lite` | 200 | `gemini-3.1-flash-lite` | absent |
| `gemini-3.5-flash` | 200 | `gemini-3.5-flash` | 84 |
| `gemini-3.5-flash-lite` | 200 | `gemini-3.5-flash-lite` | absent |
| `gemini-3.6-flash` | 200 | `gemini-3.6-flash` | 88 |
| `gemini-3.7-flash` | 503 | — | — |
| `gemini-flash-latest` | 503 | — | — |
| `gemini-flash-lite-latest` | 200 | **`gemini-3.5-flash-lite`** | absent |
| `gemma-4-31b-it` | 200 | `gemma-4-31b-it` | 58 |

The response's `modelVersion` field is what makes the alias relationship checkable: `gemini-flash-lite-latest` served `gemini-3.5-flash-lite`. It is also a per-response record of what actually ran, which the row should carry alongside the pinned id.

The 503s on `gemini-3.7-flash` and `gemini-flash-latest` (`"This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later."`) are a second reason not to pin the newest release: it is the one under load.

### Q2 — The generateContent request and response shape

**Q2.1 The request body, confirmed field by field.** Each row is one `POST /v1beta/models/gemini-3.5-flash-lite:generateContent` carrying only that `generationConfig` field:

| Field sent | Status | Note |
| --- | --- | --- |
| `temperature: 0` | 200 | |
| `temperature: 2` | 200 | upper bound accepted |
| `temperature: 5` | 400 | `"* GenerateContentRequest.generation_config.temperature: temperature must be in the range [0.0, 2.0].\n"` |
| `topP: 1` | 200 | |
| `topK: 1` | 200 | |
| `topK: 0` | 200 | |
| `maxOutputTokens: 64` | 200 | |
| `stopSequences: ["\n\n"]` | 200 | up to 5 sequences, per the discovery doc |
| `candidateCount: 1` | 200 | |
| `seed: 42` | 200 | |
| `thinkingConfig: {thinkingBudget: 0}` | 400 | `"Request contains an invalid argument."` — do not send |
| `thinkingConfig: {thinkingBudget: -1}` | 200 | |
| `thinkingConfig: {thinkingLevel: "LOW"}` | 200 | |
| all of the above at once, minus `thinkingConfig` | 200 | this is the block the client will send |
| `notAField: 1` | 400 | `"Invalid JSON payload received. Unknown name \"notAField\" at 'generation_config': Cannot find field."` |

The last row is the control: unknown `generationConfig` keys are rejected, so a 200 on `seed` is real acceptance and not a silently dropped field.

System instruction is a sibling of `contents`, and both spellings work:

```
POST /v1beta/models/gemini-3.5-flash-lite:generateContent
{
  "systemInstruction": {"parts": [{"text": "Reply with one lowercase word only."}]},
  "contents": [{"role": "user", "parts": [{"text": "Reply with the single word: ok"}]}]
}
-> 200
```

`system_instruction` (snake_case) also returned 200.

**Q2.2 Defaults when a field is omitted are published per model**, on the catalog entry in Q1.2: `temperature: 1`, `topP: 0.95`, `topK: 64`, `maxTemperature: 2`. `maxOutputTokens` defaults to the entry's `outputTokenLimit` (65536), per the discovery doc: *"The default value varies by model, see the `Model.output_token_limit` attribute"*. This is exactly the reason `mistral_client.complete_prompt` makes sampling a required keyword argument, and the same rule applies here.

**Q2.3 `seed` is a documented, first-class field.** From the live discovery document `GET https://generativelanguage.googleapis.com/$discovery/rest?version=v1beta`, revision `20260823`, `schemas.GenerationConfig.properties.seed`:

> `seed` — *"Optional. Seed used in decoding. If not set, the request uses a randomly generated seed."*

Present and identical on the `v1` discovery document, same revision.

**Q2.4 The response shape.** A full 200 body, verbatim:

```
POST /v1beta/models/gemini-3.5-flash-lite:generateContent
{"contents": [{"parts": [{"text": "Classify the sentiment of this sentence as exactly one word, positive or negative: 'The delivery arrived three days late and the box was crushed.'"}]}]}
-> 200   (header  X-Gemini-Service-Tier: standard)
{
  "candidates": [
    {
      "content": {
        "parts": [
          {
            "text": "Negative",
            "thoughtSignature": "El4KXAERTTIPPQqmWDQJ8VOuSf6j3zga...<truncated>"
          }
        ],
        "role": "model"
      },
      "finishReason": "STOP",
      "index": 0
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 29,
    "candidatesTokenCount": 1,
    "totalTokenCount": 30,
    "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 29}],
    "serviceTier": "standard"
  },
  "modelVersion": "gemini-3.5-flash-lite",
  "responseId": "A9aPatCfJsysjrEPrMTAwQg"
}
```

The generated text is `candidates[0].content.parts[*].text` — a **list**, so the client concatenates rather than indexing `parts[0]`. `modelVersion` and `responseId` are per-response provenance the row should carry.

**Q2.5 Two response shapes that will break a client copied from `mistral_client`.**

`candidatesTokenCount` is *absent*, not zero, when nothing was generated:

```
{"generationConfig": {"temperature": 0, "maxOutputTokens": 1, "seed": 42}}   prompt: "Write a 500 word essay about the sea."
-> 200
{
  "candidates": [{"content": {"parts": [{"text": ""}]}, "finishReason": "MAX_TOKENS", "index": 0}],
  "usageMetadata": {"promptTokenCount": 13, "totalTokenCount": 13,
                    "promptTokensDetails": [...], "serviceTier": "standard"},
  "modelVersion": "gemini-3.5-flash-lite",
  "responseId": "3tePasXkHLuV_uMP0omP4QM"
}
```

`mistral_client` reads `usage["completion_tokens"]` with `[...]` and raises on a missing key, because Mistral always sends it. Google does not. The Google client must read `candidatesTokenCount` with a default of `0`, or a legitimate empty completion becomes a request error.

And `content` can be an empty object with no `parts` key at all:

```
{"generationConfig": {"temperature": 0, "maxOutputTokens": 64, "seed": 42, "stopSequences": ["The"]}}
-> 200
{
  "candidates": [{"content": {}, "finishReason": "STOP", "index": 0}],
  "usageMetadata": {"promptTokenCount": 15, "totalTokenCount": 15, ...},
  "modelVersion": "gemini-3.5-flash-lite",
  "responseId": "5NePatf2Jpul1MkPtru3yQ8"
}
```

Text extraction must tolerate a missing `content` and a missing `parts`, and yield `""` rather than raising.

**Q2.6 Thinking tokens.** The catalog entry declares `"thinking": true` for `gemini-3.5-flash-lite`, but no response in any probe carried a `thoughtsTokenCount`, and `totalTokenCount` always equalled `promptTokenCount + candidatesTokenCount`. On `gemini-3.6-flash` and `gemini-3.5-flash` the same one-word prompt returned `thoughtsTokenCount` of 88 and 84 with `candidatesTokenCount: 1` and `totalTokenCount` of 97 and 93 — thinking tokens are billed and are invisible in the output. Pinning the lite model avoids having to reconcile that against the suite's `max_tokens` disclosure.

**Q2.7 The full `finishReason` enum**, from the live discovery document (revision `20260823`), `schemas.Candidate.properties.finishReason`, described as *"Optional. Output only. The reason why the model stopped generating tokens. If empty, the model has not stopped generating tokens."*:

| Value | Documented meaning | Class |
| --- | --- | --- |
| `FINISH_REASON_UNSPECIFIED` | "Default value. This value is unused." | other |
| `STOP` | "Natural stop point of the model or provided stop sequence." | completed |
| `MAX_TOKENS` | "The maximum number of tokens as specified in the request was reached." | caller's cap reached |
| `SAFETY` | "The response candidate content was flagged for safety reasons." | blocked |
| `RECITATION` | "The response candidate content was flagged for recitation reasons." | blocked |
| `LANGUAGE` | "The response candidate content was flagged for using an unsupported language." | blocked |
| `OTHER` | "Unknown reason." | other |
| `BLOCKLIST` | "Token generation stopped because the content contains forbidden terms." | blocked |
| `PROHIBITED_CONTENT` | "Token generation stopped for potentially containing prohibited content." | blocked |
| `SPII` | "Token generation stopped because the content potentially contains Sensitive Personally Identifiable Information (SPII)." | blocked |
| `MALFORMED_FUNCTION_CALL` | "The function call generated by the model is invalid." | other |
| `IMAGE_SAFETY` | "Token generation stopped because generated images contain safety violations." | blocked |
| `IMAGE_PROHIBITED_CONTENT` | "Image generation stopped because generated images has other prohibited content." | blocked |
| `IMAGE_OTHER` | "Image generation stopped because of other miscellaneous issue." | other |
| `NO_IMAGE` | "The model was expected to generate an image, but none was generated." | other |
| `IMAGE_RECITATION` | "Image generation stopped due to recitation." | blocked |
| `UNEXPECTED_TOOL_CALL` | "Model generated a tool call but no tools were enabled in the request." | other |
| `TOO_MANY_TOOL_CALLS` | "Model called too many tools consecutively, thus the system exited execution." | other |
| `MISSING_THOUGHT_SIGNATURE` | "Request has at least one thought signature missing." | other |
| `MALFORMED_RESPONSE` | "Finished due to malformed response." | other |
| `ESCALATION` | "Request was filtered by an escalation rule." | blocked |

**No value means the model's own context limit was reached.** That is the finding Methodology 9 asked for, and it is settled in the mapping section below.

`MAX_TOKENS` observed live:

```
{"contents": [{"role": "user", "parts": [{"text": "Write a 500 word essay about the sea."}]}],
 "generationConfig": {"temperature": 0, "maxOutputTokens": 8}}
-> 200  finishReason="MAX_TOKENS"  text="The sea is perhaps"
        usageMetadata: {"promptTokenCount": 13, "candidatesTokenCount": 4, "totalTokenCount": 17, ...}
```

Note `candidatesTokenCount: 4` against a cap of 8. **Google reports fewer output tokens than the cap it enforced.** `scoring.score_item` separates the two truncation causes with `generated_tokens >= max_output_tokens`; fed those numbers it would return `truncated_context` for a plainly cap-truncated generation. The Google path must not re-derive the cause from token counts.

### Q3 — Determinism at temperature 0, with and without seed

Twelve live calls, same prompt each time, `gemini-3.5-flash-lite`, paced under the rate limit. Prompt: *"In exactly three sentences, explain to a small business owner why a locally hosted language model can be cheaper than a cloud API. Do not use bullet points."*

**Without a seed — `{"temperature": 0, "topP": 1, "topK": 1, "maxOutputTokens": 512}` — 5 runs, 5 distinct outputs:**

```
run 1: sha256=cb10f205f73475f6 len=543 candidatesTokenCount=93 finishReason=STOP
run 2: sha256=22391e57d7f255ec len=538 candidatesTokenCount=91 finishReason=STOP
run 3: sha256=fa2dead4bea178aa len=428 candidatesTokenCount=75 finishReason=STOP
run 4: sha256=f701f012f9314713 len=470 candidatesTokenCount=79 finishReason=STOP
run 5: sha256=501d2777d05153b4 len=476 candidatesTokenCount=79 finishReason=STOP
```

They diverge at the first character:

```
run 1: 'Using a locally hosted language model eliminates the per-tok...'
run 2: 'Cloud APIs charge you continuously based on the volume of wo...'
```

**With `seed: 42` added and nothing else changed — 5 runs, 1 distinct output:**

```
run 1..5: sha256=53bc5b35cb82c7bf len=452 candidatesTokenCount=77 finishReason=STOP
```

**With `seed: 1234` — 2 runs, 1 distinct output, and different text from `seed: 42`:**

```
run 1..2: sha256=d2173ca6c1566cc6 len=455 candidatesTokenCount=82 finishReason=STOP
```

Three conclusions, all load-bearing:

1. **Temperature 0 alone is not deterministic on this provider.** `temperature: 0`, `topP: 1` and `topK: 1` together still produced five different answers. A judge pinned only by temperature would not be reproducible.
2. **The seed is honoured.** Byte-identical output across five calls, and identical again on a second seed.
3. **The seed changes the output.** Different seeds gave different text, so the field is doing decoding work rather than being accepted and ignored.

The epic's fallback clause — "if no per-request seed exists, judge determinism degrades to temperature 0" — does not need to be exercised. It is worth recording that had it been, the fallback would not have worked either: temperature 0 is not deterministic here.

### Q4 — Free-tier rate limits, and what a breach returns

The documentation no longer publishes a per-model free-tier table. `https://ai.google.dev/gemini-api/docs/rate-limits`, fetched 2026-08-27, says only: *"Rate limits depend on a variety of factors (such as your usage tier) and can be viewed in Google AI Studio."* The live 429 bodies are therefore the source.

**Requests per minute — 15, hit after 16 successes in 16.8 seconds:**

```
POST /v1beta/models/gemini-3.5-flash-lite:generateContent   (17th call in ~17s)
-> 429
{
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 15, model: gemini-3.5-flash-lite\nPlease retry in 38.292227434s.",
    "status": "RESOURCE_EXHAUSTED",
    "details": [
      {"@type": "type.googleapis.com/google.rpc.Help", "links": [...]},
      {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
       "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                       "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier",
                       "quotaDimensions": {"location": "global", "model": "gemini-3.5-flash-lite"},
                       "quotaValue": "15"}]},
      {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "38s"}
    ]
  }
}
```

**Input tokens per minute — 250 000:**

```
POST /v1beta/models/gemini-3.5-flash-lite:generateContent   (one 1 500 002-token prompt, alone in its quota minute)
-> 429
  message: "... Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_input_token_count, limit: 250000, model: gemini-3.5-flash-lite\nPlease retry in 55.978958196s."
  status: "RESOURCE_EXHAUSTED"
  QuotaFailure.violations[0].quotaId: "GenerateContentInputTokensPerModelPerMinute-FreeTier"
  QuotaFailure.violations[0].quotaValue: "250000"
  RetryInfo.retryDelay: "55s"
```

**What the caller gets, precisely:**

- HTTP status `429`, body `error.status: "RESOURCE_EXHAUSTED"`.
- **No `Retry-After` header.** The complete response header set on a 429 was `X-Gemini-Service-Tier`, `Vary`, `Content-Type`, `Content-Encoding`, `Date`, `Server`, `X-XSS-Protection`, `X-Frame-Options`, `X-Content-Type-Options`, `Server-Timing`, `Alt-Svc`, `Transfer-Encoding` — none of them a rate-limit hint. There is no `X-RateLimit-*` family either.
- The hint is **in the body**: `error.details[]` contains an entry with `"@type": "type.googleapis.com/google.rpc.RetryInfo"` whose `retryDelay` is a duration string (`"38s"`, `"55s"`). The prose `message` carries the same figure at sub-second precision.
- The **quota that was hit is named**: `details[].@type == ".../google.rpc.QuotaFailure"` → `violations[0].quotaId` and `quotaValue`.

Requests per day was not observed; no probe exhausted it, and the documentation no longer publishes it. It would surface the same way, as a third `quotaId` on the same 429 shape, and the backoff below handles it without knowing the number in advance.

**Free-tier access on terms comparable to Mistral's is confirmed**: the quota metric names are literally `generate_content_free_tier_requests` and `generate_content_free_tier_input_token_count`, so this key is on the free tier and it works.

### Q5 — List price

From `https://ai.google.dev/gemini-api/docs/pricing`, fetched 2026-08-27, the Gemini 3.5 Flash-Lite **Standard** table — which is the tier this key is served on, per the `X-Gemini-Service-Tier: standard` response header and `usageMetadata.serviceTier: "standard"` on every 200 above:

| Row | Free Tier | Paid Tier |
| --- | --- | --- |
| Input price | "Free of charge" | "$0.30 (text / image / video / audio)" |
| Output price | "Free of charge" | "$2.50" |
| Context caching price | "Not available" | "$0.03" + storage |
| Used to improve our products | "Yes" | "No" |

Batch and Flex tiers are half the Standard rate ($0.15 / $1.25); Priority is $0.54 / $4.50. The client sends no `serviceTier`, so Standard is what applies.

For context in the cost table, `mistral-small-2603` is $0.15 / $0.60. The Google judge is 2x the input rate and 4.2x the output rate of the existing Mistral subject.

### Q6 — Data-use terms of the free tier

From `https://ai.google.dev/gemini-api/terms`, fetched 2026-08-27.

**Unpaid Services** — *"Google uses the content you submit to the Services and any generated responses to provide, improve, and develop Google products and services."* Human review is explicit: *"human reviewers may read, annotate, and process your API input and output"*, with the mitigation that Google is *"disconnecting this data from your Google Account, API key, and Cloud project before reviewers see or annotate it"*. And the direct instruction: *"Do not submit sensitive, confidential, or personal information to the Unpaid Services."*

**Paid Services** — *"Google doesn't use your prompts (including associated system instructions, cached content, and files such as images, videos, or documents) or responses to improve our products."*

**Bearing on the PRD's data-egress non-goal.** The non-goal scopes egress to the repo's own suite items and forbids client-provided documents and prompts. That boundary already covers this: every item and every judged output sent to Google originates in this repo's suites and reference files. But the terms make the consequence sharper than "the prompt left the machine" — on the free tier, the prompt and the model's output **enter Google's training data and may be read by a human**. Two things follow, and belong to the client story rather than to this spike:

- The egress field the epic already requires must record the provider *and* that the free tier's terms apply, because the same call under a billing account has materially different terms.
- Any future decision to judge a client document is not merely an egress question but a confidentiality one, and the terms page forbids it in Google's own words.

## What the client will send

```json
POST https://generativelanguage.googleapis.com/v1/models/gemini-3.5-flash-lite:generateContent
Header: x-goog-api-key: <key>
Header: Content-Type: application/json

{
  "systemInstruction": {"parts": [{"text": "<judge system prompt, per item language>"}]},
  "contents": [{"role": "user", "parts": [{"text": "<prompt>"}]}],
  "generationConfig": {
    "temperature": 0,
    "topP": 1,
    "topK": 1,
    "seed": <the run's pinned seed>,
    "maxOutputTokens": <classification_suite.MAX_OUTPUT_TOKENS>,
    "candidateCount": 1
  }
}
```

Every sampling field is a required argument of the client function, never defaulted — the same rule and the same reason as `mistral_client.complete_prompt`: the provider's own defaults are `temperature: 1`, `topP: 0.95`, `topK: 64` and an output cap of 65 536, and a row that inherits them is not reproducible and does not run under the cap it publishes.

`thinkingConfig` is deliberately absent: `thinkingBudget: 0` is rejected on this model, and the model emits no thinking tokens without it.

`stopSequences` is deliberately absent from the default block. It works, but a stop sequence that fires immediately returns `finishReason: "STOP"` with `content: {}` and no parts, which is indistinguishable on the row from a model that chose to say nothing. If a judge template ever needs one, it is passed explicitly by that caller.

## `finishReason` mapped onto the failure taxonomy

The taxonomy is `scoring.FAILURE_REASON_*`: `empty`, `unparseable`, `truncated_max_tokens`, `truncated_context`.

| Google outcome | Taxonomy | Why |
| --- | --- | --- |
| `STOP`, text non-blank, label parses | *no failure* | the healthy path |
| `STOP`, text non-blank, label does not parse | `unparseable` | decided by `normalize_label`, not by the provider |
| `STOP`, text blank or `content.parts` absent | `empty` | `score_item` checks blankness first, so this is already correct |
| `MAX_TOKENS` | `truncated_max_tokens` | the enum says "as specified in the request"; this value can only mean the caller's cap |
| `MAX_TOKENS` with blank text | `empty` | `score_item`'s existing precedence; observed live at `maxOutputTokens: 1` |
| model's own context limit | **`truncated_context` — unreachable** | see below |
| `SAFETY`, `RECITATION`, `LANGUAGE`, `BLOCKLIST`, `PROHIBITED_CONTENT`, `SPII`, `ESCALATION`, `IMAGE_*` | **no taxonomy value fits** | see below |
| `OTHER`, `FINISH_REASON_UNSPECIFIED`, `MALFORMED_RESPONSE`, `MALFORMED_FUNCTION_CALL`, `MISSING_THOUGHT_SIGNATURE`, `UNEXPECTED_TOOL_CALL`, `TOO_MANY_TOOL_CALLS` | **no taxonomy value fits** | see below |

**`truncated_max_tokens` must be read off `finishReason` directly.** `scoring.score_item` currently separates the two truncation causes with `generated_tokens >= max_output_tokens`. On Google that test is wrong: a generation capped at 8 reported `candidatesTokenCount: 4` (Q2.7), so the comparison fails and the item would be scored `truncated_context`. The Google client therefore passes `truncated=(finishReason == "MAX_TOKENS")` **and** a `generated_tokens` value equal to the cap when that reason is set, or `score_item` gains a provider-supplied reason. That choice belongs to the client story; what this spike settles is that the token comparison cannot be reused as-is.

**`truncated_context` is unreachable on this provider's free tier, and is not a gap in the mapping.** Methodology 9 requires the two truncation causes to be distinguishable. They are, because only one of them can occur:

- No `finishReason` value denotes the model's context window (Q2.7).
- A prompt over the window would have to exceed 1 048 576 input tokens, and the free tier's input quota is 250 000 tokens per minute, so **the 429 always fires first** — proved by sending a single 1 500 002-token prompt alone in its quota minute and receiving `RESOURCE_EXHAUSTED` on `GenerateContentInputTokensPerModelPerMinute-FreeTier`, never a context error (Q4).
- The condition is instead detectable *before* the call: `POST :countTokens` returned `{"totalTokens": 1500002, ...}` on that same prompt with **HTTP 200 and no quota charge**, so the client can compare `countTokens.totalTokens` against the catalog entry's `inputTokenLimit` and refuse the item locally.

So on the Google path `truncated_context` is a pre-flight refusal, not a response classification. A row that ever carries it from this provider is a bug.

**The taxonomy has no value for a blocked or errored generation, and that is the finding.** Fifteen of the twenty-one enum values mean the provider stopped for a reason that is neither the caller's cap nor a parsing failure. Mapping them to `empty` would publish "the model said nothing" when the truth is "the provider refused", which is the exact class of dishonest row the taxonomy exists to prevent. The recommendation, for the client story to implement and the row epic to ratify: **raise a typed error naming the `finishReason` verbatim rather than coercing it into one of the four values**, mirroring `MistralRequestError`, so the run fails loudly with the provider's own word on the row instead of quietly scoring a zero. Adding a fifth `blocked` reason to `scoring._FAILURE_REASONS` is the alternative and is a row-schema change, which is the row epic's to make and not this spike's.

## Retry policy inputs

| Input | Value | Source |
| --- | --- | --- |
| Retryable status | `429` with `error.status == "RESOURCE_EXHAUSTED"` | Q4 |
| Also retryable | `503` (`"This model is currently experiencing high demand..."`) | Q1.4, observed on `gemini-3.7-flash` and `gemini-flash-latest` |
| Not retryable | `404` (model gone or retired), `400` (`INVALID_ARGUMENT`) | Q1.3, Q2.1 |
| Wait hint location | `error.details[]` entry with `@type == "type.googleapis.com/google.rpc.RetryInfo"`, field `retryDelay`, a duration string such as `"38s"` | Q4 |
| Header hint | **none** — no `Retry-After`, no `X-RateLimit-*` | Q4, full header set captured |
| Fallback when `RetryInfo` is absent | exponential backoff, because the hint is not contractually guaranteed on every 429 | — |
| Which quota was hit | `error.details[]` entry with `@type == ".../google.rpc.QuotaFailure"` → `violations[0].quotaId`, `violations[0].quotaValue` | Q4 |
| Steady-state pacing | 15 requests/minute and 250 000 input tokens/minute per model, per project | Q4 |
| Observed refill | requests refilled after the advertised delay; a 5-second inter-call spacing sustained 12 consecutive calls with no 429 | Q3 |
| Ceiling | cap the retries; a run that cannot proceed persists what it has and reports partial, per the epic's free-tier-survival boundary | epic |

Pacing at 4 seconds between calls (15/minute) is the cheapest way to avoid the limit entirely, and is what the determinism probe did. Backoff exists for the daily quota and for contention, not as the primary strategy.

## Cost-table entry

`cost.py` today keys `MISTRAL_PRICE_TABLE` by the literal dated model id and raises at import when `mistral_client.MODEL` is absent from it. The Google entry follows the same rule, keyed by the literal id:

```python
"gemini-3.5-flash-lite": {
    "input_per_million": 0.30,
    "output_per_million": 2.50,
    "currency": "USD",
    "retrieved_at": "2026-08-27",
}
```

Three notes for whoever writes it:

- The rate is the **paid Standard tier** rate. The runs this project makes are on the free tier and cost $0.00. The table exists so a row publishes what the generation *would* cost at list price, which is the only figure comparable across providers; a free-tier run costing literally nothing is not a comparable number. Whichever convention the row epic settles on, the free-tier fact has to be visible on the row rather than implied by a zero.
- `cost.cloud_cost` takes `prompt_tokens` and `completion_tokens`. On Google those are `usageMetadata.promptTokenCount` and `usageMetadata.candidatesTokenCount`, and `candidatesTokenCount` is **absent when zero** (Q2.5), so the client must default it to `0` before the total reaches `cost.total_or_none`.
- `thoughtsTokenCount` does not appear on this model but is billed as output on the thinking models. If the pin ever moves to `gemini-3.6-flash`, the cost input becomes `candidatesTokenCount + thoughtsTokenCount`, not `candidatesTokenCount`. Recording it now so a future pin change does not silently under-report.

The import-time guard in `cost.py` is keyed to `mistral_client.MODEL`. Adding a second provider means that guard needs a second arm, or a shared table keyed by provider — a small refactor the client story owns.

## What this spike does not settle

- **Whether `gemini-3.5-flash-lite` is good enough to judge.** This spike settled the API surface and picked the id on cost, callability and token-accounting honesty. Judge quality on the 1-5 rubric is the judge-protocol story's question, and if the lite model proves too weak the alternative is `gemini-3.6-flash` at $0.75 / $3.75 (Standard, through 2026-12-31; $1.50 / $7.50 from 2027-01-01) with thinking tokens billed as output and invisible in the text.
- **Requests per day on the free tier.** Unobserved and unpublished. It will appear as a third `quotaId` on the same 429 shape.
- **How a run resumes without re-paying for judge calls already made.** The epic's boundary; nothing here constrains it.
- **Whether Google and Mistral count as independent families for the epic's collision rule.** They plainly are, but the rule is enforced against a roster field that does not exist yet.

## Reproducing this

Every probe was a standalone `requests` script; none of it is production code and none of it was committed. The calls, in order, were: `GET /v1beta/models` and `GET /v1/models`; `GET /v1beta/models/{id}` across nine candidate ids; `POST {id}:generateContent` across eleven ids; per-field `generationConfig` acceptance on `gemini-3.5-flash-lite`; twelve paced determinism calls; a 40-call burst to force the RPM 429; a single oversized prompt to force the token 429; `POST :countTokens`; and `GET /$discovery/rest?version=v1` and `?version=v1beta`. The `version` and `modelVersion` values quoted here are what the API returned on 2026-08-27 and are expected to move; the pre-flight exists so that movement is visible.
