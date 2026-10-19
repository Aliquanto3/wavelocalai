"""API de l'écran Sobriété (story 5.1) : GPU du flux système, fiche machine, équivalence en voiture."""

from __future__ import annotations

import time
from datetime import date

import httpx
import pytest

from wavelocalai.config import CarEquivalence
from wavelocalai.web.app import create_app
from wavelocalai.web.system_state import cached_fiche

from ..conftest import make_settings
from ..producers import produce_chat
from .test_system import BASE, Stream, system  # noqa: F401 - `system` : fixture partagée

GPU = {
    "name": "NVIDIA GeForce RTX 3050",
    "memory_used_gb": 2.1,
    "memory_total_gb": 6.0,
    "temperature_c": 62.0,
    "thermal_throttle": True,
    "throttle_reasons": ["sw_thermal_slowdown"],
}


# --- Flux système : GPU -------------------------------------------------------------------------


async def test_the_stream_publishes_the_gpu_and_drops_it_without_nvml(system):  # noqa: F811
    app, client = system
    app.state.system_sampler.gpu_reader = lambda: dict(GPU)
    stream = Stream(app, "/api/system/stream")
    data = (await stream.frame())["data"]["data"]
    assert data["gpu"] == GPU
    await stream.disconnect()

    app.state.system_sampler.gpu_reader = lambda: None
    stream = Stream(app, "/api/system/stream")
    data = (await stream.frame())["data"]["data"]
    assert "gpu" not in data  # sans NVML, ces champs sont absents (jamais un « Actif » inventé)
    await stream.disconnect()


async def test_the_test_route_sets_the_gpu_the_stream_publishes(tmp_path):
    settings = make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"})
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client,
    ):
        assert (await client.post("/api/test/gpu", json={"gpu": GPU})).json() == {"gpu": True}
        assert (await app.state.system_sampler.sample())["gpu"] == GPU
        assert (await client.post("/api/test/gpu", json={"gpu": None})).json() == {"gpu": False}
        assert "gpu" not in await app.state.system_sampler.sample()
        incomplete = await client.post("/api/test/gpu", json={"gpu": {"name": "x"}})
        assert incomplete.status_code == 422


# --- Fiche machine ------------------------------------------------------------------------------


async def test_identity_reads_the_ollama_version_from_the_cached_probe_state(system):  # noqa: F811
    app, client = system
    await app.state.system_sampler._probe.status()  # la sonde du flux a vu Ollama (0.40.6 simulé)
    app.state.system_sampler.ollama_version = None  # sans passer par un échantillon
    body = (await client.get("/api/system/identity")).json()
    assert body["ollama_version"] == "0.40.6"


async def test_identity_answers_in_under_300_ms_just_after_launch(tmp_path):
    """Lancement à froid : la fiche est préchauffée par le démarrage (NVML est lent), la première
    lecture n'a plus qu'à la servir. Mesure consignée dans la spec de la story."""
    import wavelocalai.web.system_state as state

    state._fiche = None  # NVML froid : la fiche n'a pas encore été capturée dans ce processus
    app = create_app(make_settings(tmp_path))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client,
    ):
        started = time.perf_counter()
        response = await client.get("/api/system/identity")
        elapsed_ms = (time.perf_counter() - started) * 1000
    assert response.status_code == 200 and response.json()["accelerator"]["kind"] in {
        None,
        "nvidia",
        "apple",
    }
    assert elapsed_ms < 300, elapsed_ms
    assert cached_fiche() is not None


# --- Panneau de méthode : équivalence en voiture ------------------------------------------------


def with_factor(tmp_path, g_per_km: float | None):
    settings = make_settings(tmp_path)
    if g_per_km is not None:
        carbon = settings.carbon.model_copy(
            update={
                "car_equivalence": CarEquivalence(
                    g_per_km=g_per_km, source="ADEME (essai)", retrieved_at=date(2026, 10, 19)
                )
            }
        )
        settings = settings.model_copy(update={"carbon": carbon})
    return settings


async def test_carbon_method_is_the_server_computed_equivalence_with_factor_source_and_date(
    tmp_path,
):
    app = create_app(with_factor(tmp_path, 142))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client,
    ):
        empty = (await client.get("/api/carbon/method")).json()["equivalence"]
        assert empty["distance_m"] is None and empty["total_mg"] is None  # jamais 0 m
        assert empty["g_per_km"] == 142 and empty["source"] == "ADEME (essai)"
        assert empty["retrieved_at"] == "2026-10-19"

        await produce_chat(app.state.hub)  # une feuille locale mesurée : 1,5 mg
        summary = (await client.get("/api/carbon/session")).json()
        method = (await client.get("/api/carbon/method")).json()["equivalence"]
        assert method["total_mg"] == pytest.approx(summary["total_mg"])
        assert method["distance_m"] == pytest.approx(summary["total_mg"] / 142)  # mg / (g/km) = m

        await app.state.hub.new_app_session("reset")  # la remise à zéro redonne « aucune mesure »
        assert (await client.get("/api/carbon/method")).json()["equivalence"]["distance_m"] is None


async def test_carbon_method_has_no_equivalence_without_a_dated_setting(tmp_path):
    app = create_app(with_factor(tmp_path, None))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client,
    ):
        assert (await client.get("/api/carbon/method")).json() == {"equivalence": None}


def test_the_new_routes_enter_the_read_budget(tmp_path):
    from .test_read_budget import discover_read_routes

    found = discover_read_routes(create_app(make_settings(tmp_path)))
    assert "/api/carbon/method" in found
