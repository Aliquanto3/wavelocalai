"""Client Ollama natif, simulé par ``httpx2.MockTransport`` (AD-9, AD-13)."""

import json

import httpx2
import pytest

from scripts.quality_bench.ollama.client import (
    VERSION_TIMEOUT_S,
    OllamaClient,
    OllamaGoneError,
    OllamaRequestError,
    OllamaUnavailableError,
    OllamaVersionChangedError,
    wait_for_ollama,
)

THINKING_TOOLS = ["completion", "thinking", "tools"]
FINAL = {
    "done": True,
    "done_reason": "stop",
    "message": {"role": "assistant", "content": ""},
    "prompt_eval_count": 120,
    "prompt_eval_cached_count": 64,
    "eval_count": 7,
    "total_duration": 5_000,
    "load_duration": 1_000,
    "prompt_eval_duration": 2_000,
    "eval_duration": 1_500,
}


def _ndjson(*chunks):
    return "".join(json.dumps(chunk) + "\n" for chunk in chunks).encode("utf-8")


class Recorder:
    """Transport simulé : enregistre les requêtes et rend les réponses prévues."""

    def __init__(self, handler):
        self.requests = []
        self._handler = handler

    def __call__(self, request):
        self.requests.append(request)
        return self._handler(request)

    def bodies(self):
        return [json.loads(request.content) for request in self.requests]


def _client(handler):
    recorder = Recorder(handler)
    return (
        OllamaClient("http://127.0.0.1:11434", transport=httpx2.MockTransport(recorder)),
        recorder,
    )


def _stream_response(*chunks, status=200):
    return lambda request: httpx2.Response(status, content=_ndjson(*chunks))


def _chat(client, **overrides):
    kwargs = {
        "seed": 3,
        "num_ctx": 8192,
        "num_predict": 2048,
        "capabilities": ["completion"],
    }
    kwargs.update(overrides)
    return client.chat("qwen3.5:4b", [{"role": "user", "content": "Bonjour"}], **kwargs)


# -- Corps de requête ---------------------------------------------------------------------


def test_chat_body_fixes_every_parameter_without_think_or_tools():
    client, recorder = _client(_stream_response(FINAL))
    _chat(client)
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/chat"
    body = recorder.bodies()[0]
    assert body["stream"] is True
    assert body["options"] == {"seed": 3, "temperature": 0, "num_ctx": 8192, "num_predict": 2048}
    assert "format" in body and body["format"] is None
    assert "think" not in body and "tools" not in body
    assert body["messages"] == [{"role": "user", "content": "Bonjour"}]


def test_chat_body_with_capabilities_think_tools_and_schema():
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}}
    tools = [{"type": "function", "function": {"name": "ls", "parameters": {}}}]
    client, recorder = _client(_stream_response(FINAL))
    _chat(client, capabilities=THINKING_TOOLS, think=False, tools=tools, format=schema)
    body = recorder.bodies()[0]
    assert body["think"] is False
    assert body["tools"] == tools
    assert body["format"] == schema


@pytest.mark.parametrize(
    "overrides",
    [
        {"think": True},  # capacité thinking absente
        {"tools": [{"type": "function"}]},  # capacité tools absente
        {"capabilities": ["completion", "thinking"]},  # think implicite
        {"capabilities": ["completion", "thinking"], "think": "high"},  # chaîne non déclarée
        {"capabilities": ["completion", "tools"], "tools": []},
        {"capabilities": ["completion", "decision"]},
        {"seed": -1},
        {"num_ctx": 0},
        {"num_predict": -1},
        {"seed": 1.5},
        {"format": "yaml"},
    ],
)
def test_invalid_chat_sends_no_request(overrides):
    client, recorder = _client(_stream_response(FINAL))
    with pytest.raises(ValueError):
        _chat(client, **overrides)
    assert recorder.requests == []


def test_think_string_accepted_when_declared():
    client, recorder = _client(_stream_response(FINAL))
    _chat(
        client,
        capabilities=["completion", "thinking"],
        think="high",
        allowed_think_values=["low", "high"],
    )
    assert recorder.bodies()[0]["think"] == "high"


# -- Agrégation du flux -------------------------------------------------------------------


def test_stream_aggregated_with_counts_and_metrics():
    chunks = [
        {"message": {"role": "assistant", "content": "", "thinking": "Je "}, "done": False},
        {"message": {"role": "assistant", "content": "", "thinking": "réfléchis"}, "done": False},
        {"message": {"role": "assistant", "content": "Bon"}, "done": False},
        {"message": {"role": "assistant", "content": "jour"}, "done": False},
        {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "ls", "arguments": {"path": "/"}}},
                    {"function": {"name": "cd", "arguments": {"path": "/tmp"}}},
                ],
            },
            "done": False,
        },
        FINAL,
    ]
    client, _ = _client(_stream_response(*chunks))
    result = _chat(client, capabilities=THINKING_TOOLS, think=True)
    assert result.content == "Bonjour"
    assert result.thinking == "Je réfléchis"
    assert [call["function"]["name"] for call in result.tool_calls] == ["ls", "cd"]
    # Un fragment portant deux appels compte pour un fragment.
    assert result.chunks == {"content": 2, "thinking": 2, "tool_calls": 1}
    assert result.done_reason == "stop"
    assert result.prompt_eval_count == 120
    assert result.prompt_eval_cached_count == 64
    assert result.eval_count == 7
    assert result.durations_ns == {"total": 5000, "load": 1000, "prompt_eval": 2000, "eval": 1500}
    assert result.wall_s >= 0


def test_missing_cached_count_defaults_to_zero_and_length_reason_kept():
    final = {k: v for k, v in FINAL.items() if k != "prompt_eval_cached_count"}
    final["done_reason"] = "length"
    client, _ = _client(_stream_response({"message": {"content": "x"}, "done": False}, final))
    result = _chat(client)
    assert result.prompt_eval_cached_count == 0
    assert result.done_reason == "length"


# -- Pannes et erreurs --------------------------------------------------------------------


def test_connection_refused_is_unavailable():
    def refuse(request):
        raise httpx2.ConnectError("connexion refusée", request=request)

    client, _ = _client(refuse)
    with pytest.raises(OllamaUnavailableError):
        _chat(client)
    with pytest.raises(OllamaUnavailableError):
        client.version()


def test_read_timeout_is_unavailable():
    def timeout(request):
        raise httpx2.ReadTimeout("délai dépassé", request=request)

    client, _ = _client(timeout)
    with pytest.raises(OllamaUnavailableError):
        _chat(client)


def test_stream_cut_before_done_is_unavailable():
    client, _ = _client(_stream_response({"message": {"content": "Bon"}, "done": False}))
    with pytest.raises(OllamaUnavailableError, match="done"):
        _chat(client)


@pytest.mark.parametrize("status", [500, 502, 503])
def test_5xx_is_unavailable(status):
    client, _ = _client(lambda request: httpx2.Response(status, json={"error": "panne"}))
    with pytest.raises(OllamaUnavailableError, match=str(status)):
        _chat(client)
    with pytest.raises(OllamaUnavailableError):
        client.tags()


@pytest.mark.parametrize("status", [400, 404])
def test_4xx_is_request_error(status):
    client, _ = _client(lambda request: httpx2.Response(status, json={"error": "modèle absent"}))
    with pytest.raises(OllamaRequestError, match="modèle absent") as excinfo:
        _chat(client)
    assert excinfo.value.status_code == status
    assert not isinstance(excinfo.value, OllamaUnavailableError)


def test_error_inside_stream_is_request_error():
    client, _ = _client(_stream_response({"error": "llama runner process has terminated"}))
    with pytest.raises(OllamaRequestError, match="runner"):
        _chat(client)


def test_illegible_stream_line_is_request_error():
    client, _ = _client(lambda request: httpx2.Response(200, content=b"pas du json\n"))
    with pytest.raises(OllamaRequestError):
        _chat(client)


# -- Autres points d'accès ----------------------------------------------------------------


def test_version_show_tags_ps_unload():
    def handler(request):
        path = request.url.path
        if path == "/api/version":
            return httpx2.Response(200, json={"version": "0.40.2"})
        if path == "/api/show":
            body = json.loads(request.content)
            return httpx2.Response(
                200, json={"capabilities": ["completion"], "model": body["model"]}
            )
        if path == "/api/tags":
            return httpx2.Response(200, json={"models": [{"name": "m", "digest": "abc"}]})
        if path == "/api/ps":
            return httpx2.Response(200, json={"models": [{"name": "m", "size_vram": 1}]})
        if path == "/api/generate":
            return httpx2.Response(200, json={"done": True, "done_reason": "unload"})
        return httpx2.Response(404, json={"error": "inconnu"})

    client, recorder = _client(handler)
    assert client.version() == "0.40.2"
    assert client.show("m")["capabilities"] == ["completion"]
    assert client.tags() == [{"name": "m", "digest": "abc"}]
    assert client.ps() == [{"name": "m", "size_vram": 1}]
    client.unload("m")
    unload = recorder.requests[-1]
    assert unload.url.path == "/api/generate"
    assert json.loads(unload.content) == {"model": "m", "keep_alive": 0, "stream": False}
    assert all(not request.url.path.startswith("/v1") for request in recorder.requests)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.10:11434",
        "http://example.com",
        "http://localhost.evil.com:11434",
        "http://user:pw@localhost:11434",
        "http://localhost:11434/v1",
        "ftp://localhost:11434",
        "localhost:11434",
    ],
)
def test_remote_base_url_refused(url):
    with pytest.raises(ValueError):
        OllamaClient(url)


@pytest.mark.parametrize(
    "url", ["http://localhost:11434", "http://127.0.0.1:11434/", "http://localhost"]
)
def test_local_base_url_accepted(url):
    OllamaClient(url).close()


# -- Attente du service -------------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _version_sequence(*outcomes):
    """Client dont ``version()`` suit ``outcomes`` (une exception ou une version)."""
    calls = iter(outcomes)

    def handler(request):
        outcome = next(calls)
        if outcome == "down":
            raise httpx2.ConnectError("connexion refusée", request=request)
        return httpx2.Response(200, json={"version": outcome})

    return _client(handler)


def test_version_probe_uses_short_timeout():
    client, recorder = _client(lambda request: httpx2.Response(200, json={"version": "0.40.2"}))
    client.version()
    timeouts = recorder.requests[0].extensions["timeout"]
    assert timeouts["read"] == VERSION_TIMEOUT_S <= 10


def test_wait_for_ollama_returns_when_service_back():
    clock = FakeClock()
    client, recorder = _version_sequence("down", "down", "0.40.2")
    version = wait_for_ollama(client, 600, "0.40.2", poll_s=5, sleep=clock.sleep, clock=clock)
    assert version == "0.40.2"
    assert clock.now == 10
    assert all(request.url.path == "/api/version" for request in recorder.requests)


def test_wait_for_ollama_gone_after_wait():
    clock = FakeClock()
    client, recorder = _version_sequence(*["down"] * 100)
    with pytest.raises(OllamaGoneError):
        wait_for_ollama(client, 12, "0.40.2", poll_s=5, sleep=clock.sleep, clock=clock)
    assert clock.now == 12
    assert len(recorder.requests) == 4  # t = 0, 5, 10, 12


def test_wait_for_ollama_version_changed():
    clock = FakeClock()
    client, _ = _version_sequence("down", "0.40.3")
    with pytest.raises(OllamaVersionChangedError, match="0.40.3"):
        wait_for_ollama(client, 600, "0.40.2", sleep=clock.sleep, clock=clock)


def test_wait_for_ollama_without_expected_version():
    clock = FakeClock()
    client, _ = _version_sequence("0.40.2")
    assert wait_for_ollama(client, 0, None, sleep=clock.sleep, clock=clock) == "0.40.2"
