"""Reranker local (story 4.7) : règles de reclassement, chargement hors ligne, état et repli.

Aucun modèle n'est présent, aucun téléchargement n'est tenté : `fastembed` est remplacé par un faux
module, et une garde coupe toute connexion réseau ; seul
`test_the_real_fastembed_never_reaches_the_network_...` passe par le vrai fastembed, s'il est installé.
"""

from __future__ import annotations

import ast
import asyncio
import socket
import sys
import threading
import types
from pathlib import Path

import pytest

from wavelocalai.rag import rerank
from wavelocalai.rag.rerank import (
    FakeReranker,
    RerankerService,
    RerankerUnavailableError,
    cache_dir,
    load_fastembed,
)
from wavelocalai.rag.strategies import (
    RERANK_POOL_MAX,
    merge_best,
    rerank_pool,
    rerank_top,
)

MODEL = "jinaai/jina-reranker-v2-base-multilingual"


def item(chunk_id: int, distance: float, **extra):
    return {"chunk_id": chunk_id, "distance": distance, "text": f"extrait {chunk_id}", **extra}


# --- règles pures --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("top_k", "pool"), [(1, 3), (4, 12), (20, RERANK_POOL_MAX), (30, 60), (70, 70)]
)
def test_the_pool_is_three_times_top_k_within_the_cap(top_k, pool):
    assert rerank_pool(top_k) == pool  # jamais moins que top_k, même au-delà du plafond


def test_rerank_top_keeps_the_best_scores_and_breaks_ties_by_distance():
    found = [item(1, 0.1), item(2, 0.2), item(3, 0.3), item(4, 0.4)]
    top = rerank_top(found, [0.5, 9.0, 0.5, 2.0], 3)
    assert [i["chunk_id"] for i in top] == [2, 4, 1]  # 1 avant 3 : à égalité, le plus proche
    assert [i["rerank_score"] for i in top] == [9.0, 2.0, 0.5]
    assert top[0]["distance"] == 0.2  # la distance des vecteurs n'est pas touchée
    assert "rerank_score" not in found[0]  # l'entrée n'est pas modifiée


def test_merge_best_orders_by_rerank_score_when_every_item_has_one():
    rounds = [
        [item(1, 0.1, rerank_score=0.2), item(2, 0.2, rerank_score=0.9)],
        [item(1, 0.3, rerank_score=0.7), item(3, 0.4, rerank_score=0.5)],
    ]
    merged = merge_best(rounds, 2)
    assert [(i["chunk_id"], i["rerank_score"]) for i in merged] == [(2, 0.9), (1, 0.7)]


def test_merge_best_falls_back_to_the_distance_when_a_score_is_missing():
    rounds = [[item(1, 0.3, rerank_score=0.2)], [item(2, 0.1), item(1, 0.2)]]
    assert [i["chunk_id"] for i in merge_best(rounds, 5)] == [2, 1]
    assert merge_best([], 3) == []


# --- chargement : jamais de téléchargement -------------------------------------------------------


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("accès réseau")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def install_fake_fastembed(monkeypatch, encoder_class):
    """Un faux `fastembed.rerank.cross_encoder.TextCrossEncoder` à la place du vrai."""
    modules = {}
    for name in ("fastembed", "fastembed.rerank", "fastembed.rerank.cross_encoder"):
        modules[name] = types.ModuleType(name)
    modules["fastembed.rerank.cross_encoder"].TextCrossEncoder = encoder_class
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)


def test_the_model_is_loaded_offline_from_the_cache_after_the_telemetry_is_cut(
    monkeypatch, tmp_path, no_network
):
    order = []
    seen = {}

    class Encoder:
        def __init__(self, **kwargs):
            order.append("fastembed")
            seen.update(kwargs)

        def rerank(self, query, texts):
            return iter([1.5, 0.25])

    monkeypatch.setattr(rerank, "disable_telemetry", lambda env=None: order.append("telemetry"))
    install_fake_fastembed(monkeypatch, Encoder)
    reranker = load_fastembed(MODEL, tmp_path / "cache", ".env")
    assert order == ["telemetry", "fastembed"]
    assert seen == {
        "model_name": MODEL,
        "cache_dir": str(tmp_path / "cache"),
        "local_files_only": True,
    }
    assert reranker.score("q", ["a", "b"]) == [1.5, 0.25]


def test_a_value_error_at_load_is_an_unavailable_reranker_with_its_reason(
    monkeypatch, tmp_path, no_network
):
    class Encoder:
        def __init__(self, **kwargs):
            raise ValueError(f"Could not load model {kwargs['model_name']} from any source.\nsuite")

    install_fake_fastembed(monkeypatch, Encoder)
    with pytest.raises(RerankerUnavailableError) as raised:
        load_fastembed(MODEL, tmp_path)
    reason = str(raised.value)
    assert MODEL in reason and "Could not load model" in reason and "suite" not in reason


def test_the_real_fastembed_never_reaches_the_network_with_an_empty_or_partial_cache(
    monkeypatch, tmp_path
):
    """Le chemin réel de fastembed (dépendance de base depuis la story 9.5) : cache vide, puis dossier
    du modèle présent mais incomplet. Aucune connexion hors de la machine (le bouclage local d'asyncio
    reste permis) ; l'échec est une indisponibilité avec sa raison.
    """
    attempts = []
    connect, getaddrinfo = socket.socket.connect, socket.getaddrinfo
    local = ("127.0.0.1", "::1", "localhost")

    def guarded_connect(sock, address, *args):
        if isinstance(address, tuple) and address[0] in local:
            return connect(sock, address, *args)
        attempts.append(address)
        raise OSError("réseau coupé par le test")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host in local:
            return getaddrinfo(host, *args, **kwargs)
        attempts.append(host)
        raise OSError("réseau coupé par le test")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    cache = tmp_path / "cache"
    with pytest.raises(RerankerUnavailableError, match="n'a pas pu être chargé"):
        load_fastembed(MODEL, cache)
    snapshot = cache / "models--jinaai--jina-reranker-v2-base-multilingual" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RerankerUnavailableError, match="n'a pas pu être chargé"):
        load_fastembed(MODEL, cache)
    assert attempts == []


def test_fastembed_not_importable_is_an_unavailable_reranker(monkeypatch, tmp_path):
    """Cas défensif (environnement cassé) : fastembed est une dépendance de base depuis la story 9.5,
    donc n'arrive plus en usage normal, mais `load_fastembed` reste défensif sur `ImportError`."""
    monkeypatch.setitem(sys.modules, "fastembed", None)  # `import` lève ImportError
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", None)
    with pytest.raises(RerankerUnavailableError, match="fastembed n'est pas disponible"):
        load_fastembed(MODEL, tmp_path)


def test_the_cache_dir_is_in_the_data_dir():
    assert cache_dir(Path("data")) == Path("data/models/fastembed")


# --- l'état et le service ------------------------------------------------------------------------


def service(tmp_path, loader=None, **kwargs):
    return RerankerService(MODEL, cache_dir(tmp_path), loader=loader or (lambda *a: None), **kwargs)


def test_the_status_names_the_missing_model_and_its_cache(tmp_path):
    status = service(tmp_path).status()
    assert status.available is False
    assert MODEL in status.reason and str(cache_dir(tmp_path)) in status.reason


def test_a_model_folder_in_the_cache_makes_the_reranker_available_without_loading_it(tmp_path):
    loads = []
    svc = service(tmp_path, loader=lambda *a: loads.append(a))
    (cache_dir(tmp_path) / "models--jinaai--jina-reranker-v2-base-multilingual").mkdir(parents=True)
    assert svc.status().available is True and svc.status().reason is None
    assert loads == []  # l'état ne charge rien


async def test_the_model_is_loaded_once_in_a_thread_and_scores_come_back(monkeypatch, tmp_path):
    monkeypatch.setattr(rerank, "_model_in_cache", lambda model, cache: True)
    loads = []
    threads = []

    def loader(model, cache, env_file):
        loads.append((model, cache, env_file))
        return FakeReranker("reverse")

    svc = service(tmp_path, loader=loader, env_file=".env")
    original = asyncio.to_thread

    async def spy(func, *args, **kwargs):
        threads.append(getattr(func, "__name__", ""))
        return await original(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", spy)
    results = await asyncio.gather(svc.score("q", ["a", "b"]), svc.score("q", ["a", "b", "c"]))
    assert results == [[0.0, 1.0], [0.0, 1.0, 2.0]]
    assert loads == [(MODEL, cache_dir(tmp_path), ".env")]  # un seul chargement
    assert "loader" in threads and "score" in threads  # chargement et calcul hors de la boucle


async def test_a_load_failure_is_kept_and_never_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(rerank, "_model_in_cache", lambda model, cache: True)
    calls = []

    def loader(*args):
        calls.append(args)
        raise ValueError("fichier ONNX illisible\nsuite")

    svc = service(tmp_path, loader=loader)
    assert await svc.score("q", ["a"]) is None
    assert await svc.score("q", ["a"]) is None
    assert len(calls) == 1
    status = svc.status()
    assert status.available is False
    assert status.reason == "chargement impossible (fichier ONNX illisible)"


async def test_a_question_cancelled_during_the_first_load_does_not_start_a_second_one(
    monkeypatch, tmp_path
):
    # Revue 4.7 : le chargement (~1 Go) est partagé ; l'annulation de la question qui l'a lancé
    # ne l'interrompt pas, et la question suivante l'attend au lieu d'en lancer un second.
    monkeypatch.setattr(rerank, "_model_in_cache", lambda model, cache: True)
    loads = []
    release = threading.Event()

    def loader(*args):
        loads.append(args)
        release.wait(5)
        return FakeReranker("reverse")

    svc = service(tmp_path, loader=loader)
    first = asyncio.create_task(svc.score("q", ["a", "b"]))
    while not loads:
        await asyncio.sleep(0.01)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(svc.score("q", ["a", "b"]))
    await asyncio.sleep(0.05)
    release.set()
    assert await second == [0.0, 1.0]
    assert len(loads) == 1


async def test_a_scoring_failure_or_a_wrong_count_gives_none_without_losing_the_reranker():
    class Flaky:
        def __init__(self):
            self.n = 0

        def score(self, query, texts):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("panne")
            return [1.0] if self.n == 2 else [1.0] * len(texts)

    svc = RerankerService(MODEL, Path("absent"))
    svc.preset(Flaky())
    assert await svc.score("q", ["a", "b"]) is None  # le calcul échoue
    assert await svc.score("q", ["a", "b"]) is None  # le nombre de scores ne correspond pas
    assert await svc.score("q", ["a", "b"]) == [1.0, 1.0]  # le reranker reste chargé
    assert svc.status().available is True


async def test_an_unavailable_reranker_scores_nothing(tmp_path):
    svc = service(tmp_path)
    svc.preset(None, "cache vide")
    assert await svc.score("q", ["a"]) is None
    assert svc.status().reason == "cache vide"


# --- la discipline d'import (AD-21) --------------------------------------------------------------


def test_fastembed_is_imported_only_inside_a_function_after_the_telemetry_is_cut():
    """Le test AST de `test_telemetry.py` vérifie l'ordre ; celui-ci garantit qu'il n'est pas
    vide : `rag/rerank.py` importe bien fastembed, jamais au niveau du module."""
    source = Path(rerank.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "fastembed" in source
    top_level = [
        node
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
        and "fastembed" in ast.dump(node)
        and "importlib" not in ast.dump(node)
    ]
    assert top_level == []
    loader = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "load_fastembed"
    )
    lines = {
        "telemetry": min(
            n.lineno
            for n in ast.walk(loader)
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "disable_telemetry"
        ),
        "import": min(n.lineno for n in ast.walk(loader) if isinstance(n, ast.ImportFrom)),
    }
    assert lines["telemetry"] < lines["import"]
