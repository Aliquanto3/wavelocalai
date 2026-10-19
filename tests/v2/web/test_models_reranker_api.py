"""Récupérer le reranker depuis l'écran Modèles (story 5.5, AD-17) : run `pull`, progression, échec,
annulation, un seul `pull` à la fois, aucun téléchargement sans l'extra. L'app est la vraie ; le
téléchargement est factice (`POST /api/test/reranker-install`, `FakeFetcher`) : aucun réseau, aucun
modèle, jamais un vrai téléchargement."""

from __future__ import annotations

import asyncio
import socket

from wavelocalai.rag import rerank_pull

from .conftest import parse_sse, served  # noqa: F401 - fixture

URL = "/api/models/reranker/pull"


async def _install(client, **body):
    response = await client.post("/api/test/reranker-install", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _events(client, run_id):
    response = await client.get(f"/api/runs/{run_id}/events")
    return [frame["data"] for frame in parse_sse(response.text)[0]]


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def _reranker_settings(client):
    return (await client.get("/api/rag/settings")).json()["reranker"]


async def test_settings_say_whether_the_extra_is_installed_and_why_the_model_is_missing(served):
    _, client = served
    await _install(client, extra=False)
    off = await _reranker_settings(client)
    assert off["available"] is False and off["extra_installed"] is False and off["reason"]
    await _install(client, extra=True)
    missing = await _reranker_settings(client)
    assert missing["available"] is False and missing["extra_installed"] is True
    assert "dossier de cache" in missing["reason"]


async def test_without_the_extra_nothing_is_started_and_nothing_is_downloaded(served, monkeypatch):
    app, client = served
    service = app.state.reranker
    service.extra_override = False

    async def no_process(*args, **kwargs):
        raise AssertionError("un processus de téléchargement a été lancé")

    def no_network(*args, **kwargs):
        raise AssertionError("accès réseau sans l'extra")

    monkeypatch.setattr(rerank_pull.asyncio, "create_subprocess_exec", no_process)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    response = await client.post(URL)  # le vrai service, son vrai téléchargeur
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "invalid_request" and "uv sync --extra rerank" in str(body["detail"])
    assert (await _reranker_settings(client))["extra_installed"] is False


async def test_the_pull_reports_bytes_and_ends_ok_then_the_reranker_serves_without_restart(served):
    app, client = served
    await _install(client, total_bytes=2_000_000_000, steps=4, step_delay_s=0.03)
    started = await client.post(URL)
    assert started.status_code == 200
    run_id = started.json()["run_id"]
    snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "ok" and snapshot["kind"] == "pull"

    events = await _events(client, run_id)
    progress = [e["data"] for e in events if e["type"] == "pull_progress"]
    model = app.state.settings.rag.reranker_model
    assert progress and all(p["reranker"] is True and p["tag"] == model for p in progress)
    assert progress[0]["phase"] == "preparing"
    assert {p["phase"] for p in progress} <= {"preparing", "downloading", "verifying"}
    assert progress[-1]["percent"] == 100 and progress[-1]["total_bytes"] == 2_000_000_000
    received = [p["received_bytes"] for p in progress]
    assert received == sorted(received)  # les octets ne reculent jamais
    assert events[-1]["type"] == "run_ended" and events[-1]["data"]["status"] == "ok"

    after = await _reranker_settings(client)  # relu aussitôt : installé, sans redémarrage
    assert after["available"] is True and after["reason"] is None
    scores = await app.state.reranker.score("chat", ["un chat", "une voiture"])
    assert scores is not None and len(scores) == 2
    again = await client.post(URL)  # déjà installé : refusé, rien n'est relancé
    assert again.status_code == 422 and "déjà installé" in str(again.json()["detail"])
    assert (await client.get("/api/test/reranker-install")).json() == {"downloads": 1}


async def test_a_pull_in_progress_refuses_another_pull_of_either_kind(served):
    _, client = served
    await _install(client, mode="hang", step_delay_s=0.01)
    run_id = (await client.post(URL)).json()["run_id"]
    other_model = await client.post("/api/models/pull", json={"tag": "mid:7b"})
    second = await client.post(URL)
    for refused in (other_model, second):
        assert refused.status_code == 409
        assert refused.json()["code"] == "run_busy"
        assert refused.json()["detail"]["run_id"] == run_id
    await client.post(f"/api/runs/{run_id}/cancel")
    assert (await _ended(client, run_id))["status"] == "cancelled"


async def test_cancelling_stops_the_download_and_leaves_the_reranker_not_installed(served):
    app, client = served
    await _install(client, mode="hang", step_delay_s=0.01)
    run_id = (await client.post(URL)).json()["run_id"]
    service = app.state.reranker
    folder = rerank_pull.model_folder(service.cache, service.model)
    async with asyncio.timeout(5):
        while not folder.exists():
            await asyncio.sleep(0.01)
    await client.post(f"/api/runs/{run_id}/cancel")
    assert (await _ended(client, run_id))["status"] == "cancelled"
    async with asyncio.timeout(5):
        while folder.exists():  # le dossier partiel est retiré : « non installé » reste vrai
            await asyncio.sleep(0.01)
    assert (await _reranker_settings(client))["available"] is False


async def test_a_failed_download_ends_in_pull_failed_and_nothing_is_installed(served):
    app, client = served
    await _install(client, mode="fail", reason="espace disque insuffisant")
    run_id = (await client.post(URL)).json()["run_id"]
    snapshot = await _ended(client, run_id)
    assert snapshot["status"] == "error"
    error = (await _events(client, run_id))[-1]["data"]["error"]
    assert error["code"] == "pull_failed" and error["detail"]["cause"] == "reranker_failed"
    assert app.state.settings.rag.reranker_model in error["message"]
    assert "espace disque insuffisant" in str(error["detail"])
    assert (await _reranker_settings(client))["available"] is False
    retry = await client.post(URL)  # on peut relancer
    assert retry.status_code == 200
    await _ended(client, retry.json()["run_id"])


async def test_a_loading_failure_is_forgotten_once_the_model_is_installed(served):
    app, client = served
    service = app.state.reranker
    await _install(client)
    service.preset(None, "chargement impossible (fichier tronqué)")  # un échec retenu
    assert (await _reranker_settings(client))["available"] is False
    run_id = (await client.post(URL)).json()["run_id"]
    assert (await _ended(client, run_id))["status"] == "ok"
    assert (await _reranker_settings(client))["available"] is True
