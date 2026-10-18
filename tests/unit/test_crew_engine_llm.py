"""
Routage du LLM de CrewAI par tag (hôte Ollama, Mistral cloud), sans réseau.

Usage: python -m pytest tests/unit/test_crew_engine_llm.py -q
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

from src.core import crew_engine
from src.core.crew_engine import CrewFactory

LOCAL_TAG = "qwen2.5:1.5b"


def test_ollama_llm_uses_ipv4_loopback_by_default():
    """L'hôte vient du provider Ollama : `localhost` y est déjà visé en 127.0.0.1."""
    llm = CrewFactory._get_native_llm(LOCAL_TAG)

    assert "127.0.0.1:11434" in llm.base_url
    assert "localhost" not in llm.base_url


def test_ollama_llm_follows_provider_host(monkeypatch):
    provider = SimpleNamespace(base_url="http://gpu-box:11500")
    factory = SimpleNamespace(get_provider_by_name=lambda name: provider)
    monkeypatch.setattr(crew_engine, "get_provider_factory", lambda: factory)

    llm = CrewFactory._get_native_llm(LOCAL_TAG)

    assert "gpu-box:11500" in llm.base_url


def test_ollama_base_url_falls_back_to_provider_default(monkeypatch):
    """Fabrique sans provider Ollama : hôte par défaut d'un OllamaProvider neuf."""
    factory = SimpleNamespace(get_provider_by_name=lambda name: None)
    monkeypatch.setattr(crew_engine, "get_provider_factory", lambda: factory)

    assert crew_engine._ollama_base_url() == "http://127.0.0.1:11434"


# --- Mistral cloud : API compatible OpenAI, sans LiteLLM ---

MISTRAL_TAG = "mistral-large-2512"


@pytest.fixture
def mistral_route(monkeypatch):
    monkeypatch.setattr(crew_engine, "is_api_model", lambda tag: tag == MISTRAL_TAG)
    monkeypatch.setattr(crew_engine, "MISTRAL_API_KEY", "cle-mistral-test")


def test_mistral_llm_uses_openai_compatible_endpoint(mistral_route):
    """`mistral/…` exigerait LiteLLM, absent : la route passe par le fournisseur OpenAI natif
    de CrewAI, vers l'API de Mistral."""
    llm = CrewFactory._get_native_llm(MISTRAL_TAG, temperature=0.3)

    assert type(llm).__name__ == "OpenAICompletion"
    assert llm.model == MISTRAL_TAG
    assert llm.base_url == crew_engine.MISTRAL_BASE_URL == "https://api.mistral.ai/v1"


def test_mistral_llm_requires_api_key(mistral_route, monkeypatch):
    monkeypatch.setattr(crew_engine, "MISTRAL_API_KEY", "")

    with pytest.raises(ValueError, match="Mistral"):
        CrewFactory._get_native_llm(MISTRAL_TAG)


def test_mistral_request_shape(mistral_route, monkeypatch):
    """Requête réellement émise, captée par un serveur local : chemin `/chat/completions`,
    clé en Bearer, tag exact, aucun paramètre propre à OpenAI que Mistral refuserait."""
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.update(path=self.path, auth=self.headers.get("Authorization"))
            seen["body"] = json.loads(body)
            reply = json.dumps(
                {
                    "id": "t",
                    "object": "chat.completion",
                    "created": 0,
                    "model": MISTRAL_TAG,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "bonjour"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(
            crew_engine, "MISTRAL_BASE_URL", f"http://127.0.0.1:{server.server_address[1]}/v1"
        )
        answer = CrewFactory._get_native_llm(MISTRAL_TAG, temperature=0.3).call("salut")
    finally:
        server.shutdown()
        server.server_close()

    assert answer == "bonjour"
    assert seen["path"] == "/v1/chat/completions"
    assert seen["auth"] == "Bearer cle-mistral-test"
    assert seen["body"]["model"] == MISTRAL_TAG
    assert seen["body"]["temperature"] == 0.3
    assert not {"max_completion_tokens", "store", "stream_options"} & set(seen["body"])
