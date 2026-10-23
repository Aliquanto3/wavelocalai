"""The local llama-server chat path, as a client beside `mistral_client` and
`google_client`.

Three calls against one running server: read the loaded model's chat template
(`/props`), render an item's prompt through it (`/apply-template`), and ask for
the answer (`/v1/chat/completions`). The two suites' subject generation goes
through here; the runtime benchmark deliberately does not, because its number is
raw generation throughput against a fixed prompt reproduced from
`context_input/baseline_qwen36.md`, and templating it would change the token
count it measures and break its reproduction verdict against every published
runtime row.

Why the chat endpoint at all: `/completion` sends a prompt byte-for-byte, so a
chat-tuned model is asked to *continue* the item text rather than answer it.
That is the local-subject-prompts-are-never-chat-templated defect, and this
module is its fix.

Why `thinking_policy` is a parameter and not a default: probed live on
`b10537-bf0040e15`, both `Qwen3-0.6B` and `Qwen3.6-35B-A3B` spend their entire
generation cap in `reasoning_content` and return `content: ""` when asked
through their own template with no policy sent. The same call with
`chat_template_kwargs: {"enable_thinking": false}` answers in two tokens. So
the argument decides whether a score exists, which makes it the suite's to
declare rather than this module's to assume.

Which request arguments disable reasoning is the roster entry's declaration
(`thinking_control`), not this module's: a Jinja chat template either declares
a kwarg or silently ignores it, so a spelling that works for one family renders
nothing for another while the row still publishes `thinking_policy:
"disabled"`. The four shipped Qwen entries declare `chat_template_kwargs:
{"enable_thinking": false}`, and that choice was evidence-backed: of the four
reasoning controls b10537 documents, `reasoning_budget: 0` had no effect as a
request parameter, `reasoning_format: "none"` only stops the envelope being
parsed out of `content`, and `reasoning_effort: "none"` worked on both models
tested while their own `chat_template_caps` reports
`supports_reasoning_effort: false` -- a benchmark should not rest on a
capability the server says is absent. `verify_thinking_control` is what makes
a declaration more than a claim: it renders one fixed message with and without
the control and refuses when the two strings are byte-identical.

Which request field carries that control is the engine's spelling, not the
model's: the engine registry entry (`engines.py`) declares it as its
`thinking_switch` (llama.cpp: `chat_template_kwargs`), and a roster control
spelled in any other field is refused rather than sent to an engine that would
drop it. An engine declaring no switch at all (`none`) cannot carry an object
control, so a `disabled` batch whose entry declares one is refused before any
generation rather than published as `disabled` under an engine that never sent
anything; only an entry declaring `none` (a model that does not reason) runs a
`disabled` batch there.

No retry logic lives here. The local path has no retryable error type, and a
second retry policy beside `retry.py` would be one too many.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

import requests

from wave_local_ai_v2 import (
    engines,
    prompt_provenance,
    roster,
    row_contract,
    timings,
)

# `finish_reason` values that mean the answer was cut short rather than
# completed. Named here for the same reason `mistral_client` and
# `google_client` name their own: the truncation decision is read off the
# provider's own field, never inferred from a token count.
TRUNCATING_FINISH_REASONS = frozenset({"length"})

# Where the loaded model's own tokenizer counts a string. `add_special: true`
# tokenizes the way the chat endpoint does its rendered prompt: verified live
# on b10537 (2026-10-02), `/tokenize` over the `/apply-template` string
# returns exactly the chat call's `usage.prompt_tokens`, with and without
# tool definitions.
LOCAL_TOKENIZE_ENDPOINT = "/tokenize"


# The one message `verify_thinking_control` renders. Fixed, so the two strings
# a verification records are comparable across entries and runs; never an
# item, so no suite content leaks into a check that precedes the suite.
THINKING_PROBE_MESSAGE = "Reply with the single word: ready."


class LocalRequestError(RuntimeError):
    """Raised when a local llama-server response has no usable content."""


class ThinkingControlRefused(LocalRequestError):
    """Raised when an entry's declared thinking control changes nothing.

    A `LocalRequestError` so every caller that already turns a local failure
    into a one-line refusal does the same here, before any item is generated.
    """


class ThinkingControlProbe(TypedDict):
    """The two renders one verification compared, for the evidence it leaves."""

    with_control: str
    without_control: str


class LocalCompletion(TypedDict):
    """One item's generation from the local chat endpoint."""

    content: str
    finish_reason: str | None
    generated_tokens: int
    prompt_tokens: int
    endpoint: str
    # This item's own engine-reported figures, each null with its reason when
    # the response did not carry it (schema "18").
    measurement: timings.ItemMeasurement


def thinking_kwargs(
    thinking_policy: str, entry: roster.RosterEntry, engine: engines.EngineEntry
) -> dict[str, Any]:
    """The request arguments `thinking_policy` maps to under `entry`'s template.

    Resolved once per batch and sent on both call shapes, so a prompt can never
    be rendered under one control and answered under another. `allowed` sends
    nothing, which is the server's own default, rather than an explicit
    "think" argument a template might not declare. `disabled` sends the
    entry's declared control, nothing for a `none` declaration, and refuses an
    entry that declares neither -- there is no spelling to fall back on.

    The control must be spelled in `engine`'s switch field, read from the
    engine registry rather than assumed here. An engine with no switch has no
    field to carry an object control in, so such an entry is refused under
    `disabled` instead of running with nothing sent.
    """
    if thinking_policy == row_contract.THINKING_POLICY_ALLOWED:
        return {}
    if thinking_policy != row_contract.THINKING_POLICY_DISABLED:
        raise LocalRequestError(
            f"unknown thinking_policy {thinking_policy!r}: expected one of "
            f"{sorted(row_contract.THINKING_POLICIES)}"
        )
    control = entry.thinking_control
    if control is None:
        raise LocalRequestError(
            f"roster entry {entry.entry_id!r} declares no thinking_control: it "
            f"cannot run under thinking_policy {thinking_policy!r} (declare the "
            "request arguments that disable reasoning under its template, or "
            f"{roster.THINKING_CONTROL_NONE!r} for a model that does not reason)"
        )
    if control == roster.THINKING_CONTROL_NONE:
        return {}
    if isinstance(control, dict) and control:
        check_engine_carries(entry.entry_id, control, engine)
        # A copy: the roster entry is shared, and a request body is not its to
        # own.
        return copy.deepcopy(control)
    # `load_roster` refuses this already; an entry built in code is not
    # exempt from the same shape.
    raise LocalRequestError(
        f"roster entry {entry.entry_id!r}: malformed thinking_control {control!r}"
    )


def check_engine_carries(
    entry_id: str, control: Mapping[str, Any], engine: engines.EngineEntry
) -> None:
    """Refuse an object `control` that `engine`'s thinking switch cannot carry.

    An engine declaring no switch (`engines.THINKING_SWITCH_NONE`) carries no
    control at all; any other engine carries one only in its declared request
    field. Shared by every batch (through `thinking_kwargs`) and by the
    candidate gate, so a control the run would refuse never enters the roster.
    """
    spelled = json.dumps(dict(control), sort_keys=True)
    if engine.thinking_switch == engines.THINKING_SWITCH_NONE:
        raise LocalRequestError(
            f"roster entry {entry_id!r} declares thinking_control {spelled}, but "
            f"engine {engine.engine_id!r} declares no thinking switch "
            f"({engines.THINKING_SWITCH_NONE!r}): nothing could carry it, so a "
            "thinking_policy 'disabled' batch is refused before any generation"
        )
    field = engine.thinking_switch["request_field"]  # type: ignore[index]
    if set(control) != {field}:
        raise LocalRequestError(
            f"roster entry {entry_id!r}: thinking_control {spelled} is not "
            f"spelled in engine {engine.engine_id!r}'s thinking switch field "
            f"{field!r}"
        )


def verify_thinking_control(
    base_url: str,
    entry: roster.RosterEntry,
    *,
    chat_template: str,
    timeout: float,
) -> ThinkingControlProbe:
    """Prove `entry`'s declared control changes the prompt its template renders.

    Renders `THINKING_PROBE_MESSAGE` through `/apply-template` with the control
    and without it. Two byte-identical strings mean the template ignores the
    control, so a row would publish `thinking_policy: "disabled"` for a model
    that reasoned anyway: `ThinkingControlRefused` names the entry, the control
    and the template's hash. Needs a running server but no generation, which is
    why a batch can afford it before its first item and the candidate gate can
    reuse it on an entry not yet in the roster.

    Only an object control is verifiable; `none` and an undeclared entry are
    refused here because there is nothing to render with.
    """
    control = entry.thinking_control
    if not isinstance(control, dict):
        raise LocalRequestError(
            f"roster entry {entry.entry_id!r} declares thinking_control "
            f"{control!r}: there are no request arguments to verify"
        )
    with_control = render_prompt(
        base_url,
        THINKING_PROBE_MESSAGE,
        thinking_kwargs=copy.deepcopy(control),
        timeout=timeout,
    )
    without_control = render_prompt(
        base_url, THINKING_PROBE_MESSAGE, thinking_kwargs={}, timeout=timeout
    )
    if with_control == without_control:
        raise ThinkingControlRefused(
            f"roster entry {entry.entry_id!r}: its thinking_control "
            f"{json.dumps(control, sort_keys=True)} leaves the prompt "
            "/apply-template renders byte-identical under chat template "
            f"{prompt_provenance.template_hash(chat_template)}, so the template "
            "ignores it; refusing a thinking_policy 'disabled' batch before "
            "any generation"
        )
    return ThinkingControlProbe(
        with_control=with_control, without_control=without_control
    )


def probe_reasoning(base_url: str, *, max_tokens: int, timeout: float) -> str:
    """The reasoning one generation of `THINKING_PROBE_MESSAGE` produced, or "".

    Sends no thinking argument at all, so it is the check behind a `none`
    declaration: a model that does not reason returns no `reasoning_content`
    and no `<think>` block in `content`. Returns whichever of the two carries
    reasoning, verbatim, so a refusal can quote it.
    """
    payload = _post_json(
        f"{base_url}{prompt_provenance.LOCAL_CHAT_ENDPOINT}",
        {
            "messages": [{"role": "user", "content": THINKING_PROBE_MESSAGE}],
            "max_tokens": max_tokens,
        },
        timeout,
    )
    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else None
    message = choice.get("message") if isinstance(choice, dict) else None
    if not isinstance(message, dict):
        raise LocalRequestError(
            f"unexpected /v1/chat/completions response shape: {payload!r}"
        )
    reasoning = message.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    content = message.get("content")
    if isinstance(content, str) and "<think>" in content:
        return content
    return ""


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    response = requests.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    payload: Any = response.json()
    if not isinstance(payload, dict):
        raise LocalRequestError(f"unexpected response shape from {url}: {payload!r}")
    return payload


def chat_template(base_url: str, *, timeout: float) -> str:
    """Return the loaded model's own Jinja chat template, from `/props`.

    This string is what `prompt_template_hash` is taken over, so a row states
    which template rendered it and the hash moves when the model does.
    """
    response = requests.get(f"{base_url}/props", timeout=timeout)
    response.raise_for_status()
    payload: Any = response.json()
    template = payload.get("chat_template") if isinstance(payload, dict) else None
    if not isinstance(template, str) or not template:
        raise LocalRequestError(f"/props carries no usable chat_template: {template!r}")
    return template


def _tools_body(tools: Sequence[Mapping[str, Any]] | None) -> dict[str, Any]:
    """The `tools` key an item's own tool definitions travel under, if any."""
    return {} if tools is None else {"tools": [dict(tool) for tool in tools]}


def render_prompt(
    base_url: str,
    prompt: str,
    *,
    thinking_kwargs: Mapping[str, Any],
    timeout: float,
    tools: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Return `prompt` as the chat endpoint will render it, from `/apply-template`.

    The chat response echoes the rendered prompt nowhere, so the string a row
    publishes has to come from here. The thinking arguments are sent on this
    call too: with Qwen's thinking disabled the template appends an empty
    `<think></think>` block, so omitting them would store a string the
    answering call never used. That is
    also why the row records `prompt_capture` as reconstructed rather than
    captured -- same server, same template, same arguments, but a different
    request from the one that produced the answer.

    `/apply-template` honouring `chat_template_kwargs` is undocumented in
    b10537's server README (which lists `messages` as its only option) and was
    verified live against the binary.

    An item's own `tools` are sent here as on the answering call: the
    template renders them into the string, so they are part of the item's
    own prompt (owner answer Q33 (a)), never of a harness's overhead.
    """
    payload = _post_json(
        f"{base_url}{prompt_provenance.LOCAL_APPLY_TEMPLATE_ENDPOINT}",
        {
            "messages": [{"role": "user", "content": prompt}],
            **_tools_body(tools),
            **thinking_kwargs,
        },
        timeout,
    )
    rendered = payload.get("prompt")
    if not isinstance(rendered, str):
        raise LocalRequestError(
            f"unexpected /apply-template response shape: {payload!r}"
        )
    return rendered


def count_tokens(base_url: str, text: str, *, timeout: float) -> int:
    """How many tokens the loaded model's own tokenizer makes of `text`.

    Applied to an item's `render_prompt` string, this is the item's own
    prompt under the tokenizer the row names, which the harness overhead
    rule subtracts from what the engine reported receiving.
    """
    payload = _post_json(
        f"{base_url}{LOCAL_TOKENIZE_ENDPOINT}",
        {"content": text, "add_special": True},
        timeout,
    )
    tokens = payload.get("tokens")
    if not isinstance(tokens, list):
        raise LocalRequestError(f"unexpected /tokenize response shape: {payload!r}")
    return len(tokens)


def complete_chat(
    base_url: str,
    prompt: str,
    *,
    max_tokens: int,
    sampling: dict[str, Any],
    thinking_kwargs: Mapping[str, Any],
    timeout: float,
    tools: Sequence[Mapping[str, Any]] | None = None,
    constraint_body: Mapping[str, str] | None = None,
) -> LocalCompletion:
    """Ask the loaded model to answer `prompt` through its own chat template.

    `constraint_body` is a decoding constraint already spelled in the
    engine's request field (llama.cpp: `{"grammar": <GBNF>}`), sent as is.
    """
    payload = _post_json(
        f"{base_url}{prompt_provenance.LOCAL_CHAT_ENDPOINT}",
        {
            "messages": [{"role": "user", "content": prompt}],
            **_tools_body(tools),
            "max_tokens": max_tokens,
            **sampling,
            **thinking_kwargs,
            **(constraint_body or {}),
        },
        timeout,
    )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LocalRequestError(
            f"unexpected /v1/chat/completions response shape: {payload!r}"
        )
    choice = choices[0]
    message = choice.get("message") if isinstance(choice, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        # A thinking model that spent its whole cap reasoning returns an empty
        # string here, which is a valid response and scores as `empty`. Only a
        # missing or non-text content is a malformed body.
        raise LocalRequestError(f"unexpected chat content type: {content!r}")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise LocalRequestError(f"chat response carries no usage block: {payload!r}")
    return LocalCompletion(
        content=content,
        finish_reason=choice.get("finish_reason"),
        generated_tokens=usage.get("completion_tokens", 0),
        prompt_tokens=usage.get("prompt_tokens", 0),
        endpoint=prompt_provenance.LOCAL_CHAT_ENDPOINT,
        measurement=timings.parse_item_measurement(payload),
    )
