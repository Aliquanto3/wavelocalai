"""Ce que la barre haute (story 1.9) demande au serveur : la route de test publie `carbon_updated`
comme le feront les services, et la sonde du flux système est plus fraîche que son intervalle."""

from __future__ import annotations

import pytest

from wavelocalai.models.ollama_probe import OllamaProbe
from wavelocalai.runs.system_bus import SAMPLE_INTERVAL_S
from wavelocalai.web.app import create_app

from ..conftest import make_settings
from .test_system import Stream

LOCAL = {"mg": 1.8, "method": "codecarbon"}
CLOUD = {"mg": 0.9, "method": "ecologits", "estimated": True}


async def next_carbon(stream: Stream) -> dict:
    while True:
        envelope = (await stream.frame())["data"]
        if envelope["type"] == "carbon_updated":
            return envelope["data"]


async def test_a_scripted_run_publishes_carbon_updated_with_the_session_sum(served):
    app, client = served
    stream = Stream(app, "/api/system/stream")
    await stream.frame()

    response = await client.post("/api/test/runs", json={"origin": "cloud", "co2": CLOUD})
    assert response.status_code == 200
    summary = await next_carbon(stream)
    assert summary["total_mg"] == pytest.approx(0.9)
    assert summary["by_origin"]["cloud"] == {"mg": pytest.approx(0.9), "runs": 1}
    assert summary["by_origin"]["local"] == {"mg": 0.0, "runs": 0}
    assert summary["unmeasurable_runs"] == 0
    await stream.disconnect()


async def test_a_scripted_run_without_measure_counts_as_unmeasurable_never_zero(served):
    app, client = served
    stream = Stream(app, "/api/system/stream")
    await stream.frame()

    assert (await client.post("/api/test/runs", json={"origin": "cloud"})).status_code == 200
    summary = await next_carbon(stream)
    assert summary["unmeasurable_runs"] == 1 and summary["measured_runs"] == 0
    assert summary["by_origin"]["cloud"]["runs"] == 1
    await stream.disconnect()


async def test_the_summary_endpoint_agrees_with_the_event(served):
    app, client = served
    stream = Stream(app, "/api/system/stream")
    await stream.frame()
    await client.post("/api/test/runs", json={"origin": "local", "co2": LOCAL})
    event = await next_carbon(stream)
    assert (await client.get("/api/carbon/session")).json() == event
    await stream.disconnect()


async def test_an_invalid_co2_or_origin_is_refused(served):
    _, client = served
    bad_co2 = await client.post(
        "/api/test/runs", json={"co2": {"mg": None, "method": "codecarbon"}}
    )
    assert bad_co2.status_code in (400, 422) and bad_co2.json()["code"] == "invalid_request"
    unknown = await client.post("/api/test/runs", json={"co2": {"method": "magie", "mg": 1.0}})
    assert unknown.json()["code"] == "invalid_request"
    bad_origin = await client.post("/api/test/runs", json={"origin": "lune"})
    assert bad_origin.status_code in (400, 422)


def test_the_stream_probe_keeps_the_state_for_less_than_the_stream_interval(tmp_path):
    app = create_app(make_settings(tmp_path))
    stream_probe = app.state.system_sampler._probe
    assert stream_probe._cache_s <= SAMPLE_INTERVAL_S / 2  # un Ollama relancé se voit en < 3 s
    assert app.state.probe._cache_s == 5.0  # les routes de lecture gardent le cache d'AD-15
    assert stream_probe is not app.state.probe


def test_an_injected_probe_serves_both_the_routes_and_the_stream(tmp_path):
    settings = make_settings(tmp_path)
    probe = OllamaProbe(settings.ollama.host)
    app = create_app(settings, probe)
    assert app.state.probe is probe and app.state.system_sampler._probe is probe
