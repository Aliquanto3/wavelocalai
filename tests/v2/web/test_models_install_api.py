"""Installer un modèle (story 5.3) : catalogue installable avec `fits`, run `pull`, progression,
annulation, échecs, reprise. L'app est la vraie (hub, registre, conseiller mémoire) ; Ollama est un
faux (`PullOllama`) et la mémoire du poste est simulée. Aucun vrai téléchargement."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path

import httpx
import pytest

from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.store.db import Store, db_path
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from ..pull_fake import GB, PullOllama, PullScript, download, layer, manifest, success
from .conftest import parse_sse

BASE = f"http://127.0.0.1:{TEST_PORT}"
CATALOG = {
    "models": {
        "Petit 1B": {"ollama_tag": "small:1b", "size_gb": "0.8 GB", "params_tot": "1B",
                     "params_act": "1B", "capabilities": ["chat"], "desc": "Un petit modèle."},
        "Moyen 7B": {"ollama_tag": "mid:7b", "size_gb": "4.7 GB", "params_tot": "7B",
                     "params_act": "7B", "capabilities": ["chat", "tools"],
                     "measured_loaded_gb": 5.0},
        "Gros 70B": {"ollama_tag": "big:70b", "size_gb": "40 GB", "params_tot": "70B",
                     "params_act": "70B", "capabilities": ["chat", "thinking"]},
        "MoE 30B": {"ollama_tag": "moe:30b", "size_gb": "18 GB", "params_tot": "30B",
                    "moe": True, "capabilities": ["chat"]},
        "Déjà là": {"ollama_tag": "here:2b", "size_gb": "1.5 GB", "params_tot": "2B",
                    "params_act": "2B", "capabilities": ["chat"]},
    }
}  # fmt: skip


def reading(available_gb: float):
    return lambda: MemoryReading(total_gb=32.0, available_gb=available_gb)


@contextlib.asynccontextmanager
async def install_app(tmp_path: Path, server: PullOllama, available_gb: float = 8.0):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(CATALOG), encoding="utf-8")
    config = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"})
    memory = reading(available_gb)
    registry = ModelRegistry(
        config,
        source=OllamaHttpSource(config.ollama.host, transport=server.transport),
        advisor=MemoryAdvisor(memory),
        catalog_path=catalog,
    )
    app = create_app(
        config,
        registry=registry,
        ollama_client=server.client(),
        ollama_transport=server.transport,
        memory_reader=memory,
    )
    server.on_success = server.tags.append  # le modèle installé apparaît dans `/api/tags`
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client, registry


def ollama(**fields) -> PullOllama:
    defaults = {"tags": ["here:2b"], "sizes": {"here:2b": int(1.5 * GB)}}
    return PullOllama(**{**defaults, **fields})


async def _pull(client, tag="mid:7b"):
    return await client.post("/api/models/pull", json={"tag": tag})


async def _events(client, run_id, after=0):
    response = await client.get(f"/api/runs/{run_id}/events", params={"after": after})
    return [f["data"] for f in parse_sse(response.text)[0]]


async def _ended(client, run_id, timeout=5.0):
    async with asyncio.timeout(timeout):
        while True:
            snapshot = (await client.get(f"/api/runs/{run_id}")).json()
            if snapshot["status"] != "running":
                return snapshot
            await asyncio.sleep(0.02)


async def _wait_until(predicate, timeout=5.0):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


# --- Catalogue installable ----------------------------------------------------------------------


async def test_the_catalog_lists_what_is_not_installed_with_the_memory_it_needs(tmp_path):
    async with install_app(tmp_path, ollama(), available_gb=8.0) as (_, client, _r):
        body = (await client.get("/api/models/catalog")).json()
    tags = [m["tag"] for m in body["models"]]
    assert "here:2b" not in tags  # installé : il n'est plus proposé
    assert body["ollama_up"] is True and body["free_gb"] == 8.0
    by_tag = {m["tag"]: m for m in body["models"]}
    mid = by_tag["mid:7b"]  # empreinte mesurée 5,0 Go : requis 5,0 × 1,1 + 0,5
    assert (mid["needed_gb"], mid["required_gb"], mid["fits"], mid["short_gb"]) == (
        5.0,
        6.0,
        True,
        None,
    )
    assert mid["tools_verified"] is True and mid["download_gb"] == 4.7
    small = by_tag["small:1b"]  # taille × 1,25
    assert small["needed_gb"] == 1.0 and small["fits"] is True and small["name"] == "Petit 1B"
    big = by_tag["big:70b"]  # 40 × 1,25 = 50 Go : requis 55,5 ; libres 8,0
    assert (big["needed_gb"], big["required_gb"], big["fits"]) == (50.0, 55.5, False)
    assert big["short_gb"] == 47.5 and big["reasoning"] is True
    assert by_tag["moe:30b"]["params_active_b"] is None  # MoE sans actifs : jamais le total
    assert by_tag["moe:30b"]["params_total_b"] == 30.0


async def test_the_catalog_puts_what_fits_first_then_the_memory_it_needs(tmp_path):
    async with install_app(tmp_path, ollama(), available_gb=8.0) as (_, client, _r):
        tags = [m["tag"] for m in (await client.get("/api/models/catalog")).json()["models"]]
    assert tags == ["small:1b", "mid:7b", "moe:30b", "big:70b"]


async def test_a_loaded_model_counts_as_free_memory_like_the_guard_does(tmp_path):
    server = ollama(loaded=["here:2b"], sizes={"here:2b": int(4 * GB)})
    async with install_app(tmp_path, server, available_gb=3.0) as (_, client, registry):
        body = (await client.get("/api/models/catalog")).json()
    mid = next(m for m in body["models"] if m["tag"] == "mid:7b")
    assert body["free_gb"] == 7.0  # 3,0 libres + 4,0 de modèle chargé que l'on peut décharger
    assert mid["fits"] is True  # requis 6,0 ≤ 7,0
    async with install_app(tmp_path, ollama(), available_gb=3.0) as (_, client, _r):
        alone = (await client.get("/api/models/catalog")).json()
    assert next(m for m in alone["models"] if m["tag"] == "mid:7b")["fits"] is False


async def test_a_model_deleted_from_the_machine_comes_back_to_the_catalog(tmp_path):
    server = ollama(tags=["here:2b", "mid:7b"])
    async with install_app(tmp_path, server) as (_, client, registry):
        first = [m["tag"] for m in (await client.get("/api/models/catalog")).json()["models"]]
        assert "mid:7b" not in first
        server.tags.remove("mid:7b")  # supprimé dans Ollama
        await registry.refresh()
        again = [m["tag"] for m in (await client.get("/api/models/catalog")).json()["models"]]
    assert "mid:7b" in again


async def test_an_installed_latest_variant_hides_its_catalog_entry(tmp_path):
    server = ollama(tags=["small:1b:latest"])
    async with install_app(tmp_path, server) as (_, client, _r):
        tags = [m["tag"] for m in (await client.get("/api/models/catalog")).json()["models"]]
    assert "small:1b" not in tags


async def test_installed_models_say_the_memory_that_is_missing(tmp_path):
    server = ollama(tags=["other:4b"], sizes={"other:4b": 4 * GB})  # 4 Go × 1,25 = 5,0 Go
    async with install_app(tmp_path, server, available_gb=4.8) as (_, client, _r):
        listed = (await client.get("/api/models")).json()["models"]
    other = next(m for m in listed if m["tag"] == "other:4b")
    assert (other["fits"], other["required_gb"], other["short_gb"]) == (False, 6.0, 1.2)


# --- Installation -------------------------------------------------------------------------------


async def test_pull_runs_to_installed_with_its_progress_and_a_fresh_model_list(tmp_path):
    server = ollama(scripts=[PullScript(download(4 * GB, steps=4))])
    async with install_app(tmp_path, server) as (_, client, _r):
        started = await _pull(client, " mid:7b ")
        assert started.status_code == 200 and set(started.json()) == {"run_id"}
        run_id = started.json()["run_id"]
        assert (await _ended(client, run_id))["status"] == "ok"

        events = await _events(client, run_id)
        assert events[0]["type"] == "run_started"
        assert events[0]["data"]["kind"] == "pull" and events[0]["data"]["models"] == ["mid:7b"]
        progress = [e["data"] for e in events if e["type"] == "pull_progress"]
        assert progress[0] == {
            "tag": "mid:7b", "received_bytes": 0, "total_bytes": 0, "percent": None,
            "phase": "preparing",
        }  # fmt: skip
        assert {"downloading", "verifying"} <= {p["phase"] for p in progress}
        assert len(progress) <= 6  # les lignes d'Ollama sont groupées (au plus 4 par seconde)
        last = progress[-1]
        assert last["received_bytes"] == last["total_bytes"] == 4 * GB and last["percent"] == 100
        assert all(p["tag"] == "mid:7b" for p in progress)
        assert events[-1]["type"] == "run_ended" and events[-1]["data"]["status"] == "ok"
        assert server.pull_requests == [{"model": "mid:7b", "stream": True}]

        # La liste est relue avant `run_ended` : le modèle y est déjà, et plus au catalogue.
        listed = {m["tag"] for m in (await client.get("/api/models")).json()["models"]}
        assert "mid:7b" in listed
        catalog = {m["tag"] for m in (await client.get("/api/models/catalog")).json()["models"]}
        assert "mid:7b" not in catalog


async def test_the_progress_can_be_read_again_after_a_cursor(tmp_path):
    server = ollama(scripts=[PullScript(download(2 * GB, steps=2))])
    async with install_app(tmp_path, server) as (_, client, _r):
        run_id = (await _pull(client)).json()["run_id"]
        await _ended(client, run_id)
        everything = await _events(client, run_id)
        cursor = everything[2]["seq"]
        later = await _events(client, run_id, after=cursor)
    assert [e["seq"] for e in later] == [e["seq"] for e in everything if e["seq"] > cursor]
    assert later[-1]["type"] == "run_ended"


async def test_a_second_pull_while_one_runs_is_a_409_run_busy_with_the_run_to_join(tmp_path):
    hold, resume = asyncio.Event(), asyncio.Event()
    script = PullScript(download(4 * GB, steps=4), pause_after=2, resume=resume, hold=hold)
    server = ollama(scripts=[script])
    async with install_app(tmp_path, server) as (_, client, _r):
        run_id = (await _pull(client)).json()["run_id"]
        busy = await _pull(client, "small:1b")
        assert busy.status_code == 409
        envelope = busy.json()
        assert envelope["code"] == "run_busy" and envelope["detail"]["run_id"] == run_id
        assert server.pull_requests == []  # rien n'a encore été demandé à Ollama
        hold.set()
        resume.set()
        await _ended(client, run_id)
        assert len(server.pull_requests) == 1
        again = await _pull(client, "small:1b")  # la place est libre
        assert again.status_code == 200
        await _ended(client, again.json()["run_id"])


async def test_cancelling_stops_the_download_and_leaves_the_list_unchanged(tmp_path):
    server = ollama(scripts=[PullScript(download(4 * GB)[:3], end="hang")])
    async with install_app(tmp_path, server) as (_, client, _r):
        run_id = (await _pull(client)).json()["run_id"]
        await _wait_until(lambda: server.pull_opened == 1)
        before = (await client.get("/api/models")).json()
        cancelled = (await client.post(f"/api/runs/{run_id}/cancel")).json()
        assert cancelled["cancelled"] is True and cancelled["status"] == "cancelled"
        await _wait_until(lambda: server.pull_closed == 1)  # le flux HTTP est refermé
        events = await _events(client, run_id)
        assert events[-1]["type"] == "run_ended" and events[-1]["data"]["status"] == "cancelled"
        after = (await client.get("/api/models")).json()
        assert [m["tag"] for m in after["models"]] == [m["tag"] for m in before["models"]]


@pytest.mark.parametrize(
    ("script", "cause", "needle"),
    [
        (
            PullScript([manifest(), {"error": "pull model manifest: file does not exist"}]),
            "not_found",
            "ce nom n'existe pas",
        ),
        (PullScript(end="refuse"), "ollama_down", "Ollama ne répond plus"),
        (
            PullScript([manifest(), layer("sha256:aaaa1111", 100, 40)], end="error"),
            "ollama_down",
            "Ollama ne répond plus",
        ),
        (
            PullScript([manifest(), {"error": "no space left on device"}]),
            "interrupted",
            "interrompue",
        ),
    ],
)
async def test_a_failed_pull_ends_in_error_with_pull_failed_and_leaves_the_list(
    tmp_path, script, cause, needle
):
    server = ollama(scripts=[script])
    async with install_app(tmp_path, server) as (_, client, _r):
        before = [m["tag"] for m in (await client.get("/api/models")).json()["models"]]
        run_id = (await _pull(client, "granite4.1:8b")).json()["run_id"]
        assert (await _ended(client, run_id))["status"] == "error"
        ended = (await _events(client, run_id))[-1]["data"]
        error = ended["error"]
        assert ended["status"] == "error" and error["code"] == "pull_failed"
        assert error["detail"]["tag"] == "granite4.1:8b" and error["detail"]["cause"] == cause
        assert needle in error["message"] and "granite4.1:8b" in error["message"]
        assert "La liste des modèles est inchangée." in error["action"]
        after = [m["tag"] for m in (await client.get("/api/models")).json()["models"]]
        assert after == before


async def test_a_pull_that_failed_does_not_block_the_next_one(tmp_path):
    server = ollama(scripts=[PullScript(end="refuse"), PullScript(download(GB, steps=1))])
    async with install_app(tmp_path, server) as (_, client, _r):
        first = (await _pull(client)).json()["run_id"]
        assert (await _ended(client, first))["status"] == "error"
        second = (await _pull(client)).json()["run_id"]
        assert (await _ended(client, second))["status"] == "ok"


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"tag": ""}, 422, "invalid_request"),
        ({"tag": "deux mots"}, 422, "invalid_request"),
        ({}, 422, "invalid_request"),
        ({"tag": "gpt-oss:120b-cloud"}, 403, "cloud_not_allowed"),
    ],
)
async def test_an_invalid_tag_is_refused_before_any_run_is_created(tmp_path, body, status, code):
    server = ollama()
    async with install_app(tmp_path, server) as (app, client, _r):
        response = await client.post("/api/models/pull", json=body)
        assert (response.status_code, response.json()["code"]) == (status, code)
        assert app.state.hub.active_root("pull") is None and server.pull_requests == []


async def test_a_pull_from_another_origin_is_refused(tmp_path):
    server = ollama()
    async with install_app(tmp_path, server) as (_, client, _r):
        response = await client.post(
            "/api/models/pull", json={"tag": "mid:7b"}, headers={"Origin": "http://evil.example"}
        )
        assert response.status_code == 403 and response.json()["code"] == "forbidden_origin"
        assert server.pull_requests == []


async def test_a_pull_interrupted_by_a_restart_says_why_when_it_is_replayed(tmp_path):
    store = Store.open(db_path(tmp_path / "data"))
    try:
        first = RunHub(store, batch_interval_s=3600)
        await first.start()
        handle = await first.create_run(
            "pull", models=["granite4.1:8b"], params={"tag": "granite4.1:8b"}
        )
        second = RunHub(store, batch_interval_s=3600)  # le serveur redémarre sans fin propre
        await second.start()
        rows = store.read(
            "SELECT data FROM run_events WHERE run_id = ? ORDER BY seq DESC LIMIT 1",
            (handle.run_id,),
        )
        ended = json.loads(rows[0]["data"])
        await second.stop()
    finally:
        store.close()
    assert ended["status"] == "interrupted"
    assert (
        ended["error"]["code"] == "pull_failed"
        and ended["error"]["detail"]["cause"] == "interrupted"
    )
    assert "redémarrage du serveur" in ended["error"]["message"]
    assert ended["error"]["detail"]["tag"] == "granite4.1:8b"


async def test_the_pull_route_is_the_only_one_that_downloads(tmp_path):
    """AD-17 : lire le catalogue ou la liste ne demande jamais `/api/pull` à Ollama."""
    server = ollama()
    async with install_app(tmp_path, server) as (_, client, _r):
        for path in ("/api/models", "/api/models/catalog", "/api/models/defaults"):
            assert (await client.get(path)).status_code == 200
        assert server.pull_requests == []
        await _ended(client, (await _pull(client)).json()["run_id"])
        assert len(server.pull_requests) == 1


async def test_with_ollama_down_the_catalog_still_answers_and_a_pull_ends_in_ollama_down(tmp_path):
    server = ollama(scripts=[PullScript(end="refuse")])
    async with install_app(tmp_path, server) as (_, client, registry):
        registry._ollama_up = False  # noqa: SLF001 - Ollama a cessé de répondre
        body = (await client.get("/api/models/catalog")).json()
        assert body["ollama_up"] is False and body["models"]
        run_id = (await _pull(client)).json()["run_id"]
        await _ended(client, run_id)
        error = (await _events(client, run_id))[-1]["data"]["error"]
        assert error["detail"]["cause"] == "ollama_down"


async def test_the_last_progress_is_never_lost_when_ollama_goes_quiet(tmp_path):
    """Les lignes d'Ollama sont groupées (4 par seconde) : si le flux se tait juste après une rafale,
    l'état en attente part à l'échéance, sans attendre la ligne suivante."""
    resume = asyncio.Event()
    lines = [
        manifest(),
        layer("sha256:aaaa1111", 4 * GB, 0),
        layer("sha256:aaaa1111", 4 * GB, 2 * GB),
    ]
    server = ollama(scripts=[PullScript([*lines, success()], pause_after=3, resume=resume)])
    async with install_app(tmp_path, server) as (app, client, _r):
        run_id = (await _pull(client)).json()["run_id"]

        async def last_received() -> int:
            events = await app.state.hub.events_after(run_id, 0)
            progress = [e for e in events if e["type"] == "pull_progress"]
            return progress[-1]["data"]["received_bytes"] if progress else 0

        async with asyncio.timeout(3.0):
            while await last_received() < 2 * GB:  # sans la ligne suivante : par l'échéance
                await asyncio.sleep(0.05)
        resume.set()
        assert (await _ended(client, run_id))["status"] == "ok"
