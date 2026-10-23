"""Port `Embedder` (AD-8) : adaptateur Ollama `/api/embed` (faux serveur), `fake` scriptable, fabrique."""

from __future__ import annotations

import json

import httpx
import pytest
from ollama import AsyncClient

from wavelocalai.errors import AppError, ProviderError
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.fake import (
    FAKE_EMBED_DIM,
    FAKE_EMBED_REF,
    FAKE_REF,
    FakeEmbedder,
    Sleep,
    fake_embedders,
    fake_models,
    fake_vector,
)
from wavelocalai.models.ollama_embed import OllamaEmbedder
from wavelocalai.models.port import Embedder, ModelRef

from ..conftest import make_settings

REF = ModelRef("nomic-embed-text:latest", "ollama", "local", "embedding")


def _client(handler) -> tuple[AsyncClient, list[dict]]:
    sent: list[dict] = []

    async def wrapped(request: httpx.Request) -> httpx.Response:
        sent.append({"path": request.url.path, "body": json.loads(request.content or b"{}")})
        return handler(request)

    return AsyncClient(host="http://127.0.0.1:11434", transport=httpx.MockTransport(wrapped)), sent


async def test_ollama_embed_sends_the_batch_and_returns_the_vectors():
    client, sent = _client(
        lambda r: httpx.Response(
            200, json={"model": REF.tag, "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]}
        )
    )
    embedder = OllamaEmbedder(REF, client)
    assert isinstance(embedder, Embedder)
    vectors = await embedder.embed(["un", "deux"])
    assert vectors == [pytest.approx([0.1, 0.2, 0.3]), pytest.approx([0.4, 0.5, 0.6])]
    assert [(s["path"], s["body"]["model"], s["body"]["input"]) for s in sent] == [
        ("/api/embed", REF.tag, ["un", "deux"])
    ]


async def test_ollama_embed_of_nothing_makes_no_call():
    client, sent = _client(lambda r: httpx.Response(500))
    assert await OllamaEmbedder(REF, client).embed([]) == []
    assert sent == []


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (lambda r: httpx.Response(404, json={"error": "model not found"}), "model_not_found"),
        (lambda r: httpx.Response(500, json={"error": "panne"}), "ollama_error"),
        (lambda r: httpx.Response(200, json={"embeddings": [[1.0]]}), "ollama_error"),  # 1 pour 2
        (lambda r: httpx.Response(200, json={"embeddings": [[1.0], [1.0, 2.0]]}), "ollama_error"),
        (lambda r: httpx.Response(200, json={"embeddings": [[], []]}), "ollama_error"),
    ],
)
async def test_ollama_embed_refusals_become_closed_provider_errors(handler, code):
    client, _ = _client(handler)
    with pytest.raises(ProviderError) as error:
        await OllamaEmbedder(REF, client).embed(["a", "b"])
    assert error.value.code == code


async def test_ollama_embed_with_ollama_down_says_so():
    def refuse(request: httpx.Request):
        raise httpx.ConnectError("refusé", request=request)

    client, _ = _client(refuse)
    with pytest.raises(ProviderError) as error:
        await OllamaEmbedder(REF, client).embed(["a"])
    assert error.value.code == "ollama_down"


# --- fake -----------------------------------------------------------------------------------------


def test_fake_vectors_are_deterministic_unit_vectors_of_a_fixed_dimension():
    a, b = fake_vector("Le chat dort"), fake_vector("le chat  DORT")
    assert a == b and len(a) == FAKE_EMBED_DIM
    assert sum(x * x for x in a) == pytest.approx(1.0)
    assert fake_vector("") == fake_vector("   ") and sum(x * x for x in fake_vector("")) == 1.0
    assert fake_vector("chat") != fake_vector("voiture")
    # d'un processus à l'autre : SHA-256 et non le `hash()` salé de Python (valeur figée)
    assert fake_vector("chat").index(max(fake_vector("chat"))) == 13


async def test_the_fake_embedder_follows_its_script_and_keeps_the_batches():
    embedder = FakeEmbedder([None, ProviderError("ollama_down", "x"), Sleep(0.0)])
    assert isinstance(embedder, Embedder)
    assert await embedder.embed(["a", "b"]) == [fake_vector("a"), fake_vector("b")]
    with pytest.raises(ProviderError):
        await embedder.embed(["c"])
    assert len(await embedder.embed(["d"])) == 1
    assert len(await embedder.embed(["e"])) == 1  # script épuisé : l'appel réussit
    assert embedder.texts == [["a", "b"], ["c"], ["d"], ["e"]] and embedder.calls == 4


def test_fake_embedders_only_exist_when_testing(tmp_path):
    assert fake_embedders(make_settings(tmp_path)) == {}
    on = fake_embedders(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}))
    assert list(on) == [FAKE_EMBED_REF.tag] and on[FAKE_EMBED_REF.tag].ref == FAKE_EMBED_REF
    assert FAKE_EMBED_REF.kind == "embedding" and FAKE_EMBED_REF.origin == "local"
    assert fake_models(make_settings(tmp_path)) == {}


def test_testing_no_fake_embedder_simulates_a_machine_without_any_embedding(tmp_path):
    # E2E (story 9.4) : l'encart « aucun modèle de représentation » sans toucher au `fake` du chat.
    settings = make_settings(
        tmp_path,
        environ={
            "WAVELOCALAI_TESTING": "1",
            "WAVELOCALAI_TESTING_NO_FAKE_EMBEDDER": "1",
        },
    )
    assert fake_embedders(settings) == {}
    assert list(fake_models(settings)) == [FAKE_REF.tag]  # le chat `fake` reste disponible


def test_the_factory_gives_the_fake_then_ollama_and_nothing_else():
    fake = FakeEmbedder()
    factory = ModelFactory(AsyncClient(), {}, {FAKE_EMBED_REF.tag: fake})
    assert factory.embedder(FAKE_EMBED_REF) is fake
    assert isinstance(factory.embedder(REF), OllamaEmbedder)
    with pytest.raises(AppError) as error:
        factory.embedder(ModelRef("openai/emb", "openai", "cloud", "embedding"))
    assert error.value.code == "internal"
