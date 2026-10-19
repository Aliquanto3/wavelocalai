"""Fiche d'un modèle (story 5.6) : `GET /api/models/card/{tag}`. L'app est la vraie ; Ollama est un faux
(`FakeOllama`) et les résultats du banc viennent de la fixture `tests/v2/fixtures/` copiée en dossier
temporaire (aucun fichier de `benchmarks/` n'est lu ni écrit)."""

from __future__ import annotations

import contextlib
import json
import shutil
import time
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.models.ollama_api import OllamaHttpSource
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, closed_port, make_settings
from ..fake_ollama import FakeOllama

BASE = f"http://127.0.0.1:{TEST_PORT}"
GB = 1024**3
FIXTURE = Path(__file__).parent.parent / "fixtures" / "slm-quality-results.sample.json"
CATALOG = {
    "models": {
        "Moyen 7B": {"ollama_tag": "mid:7b", "size_gb": "4.7 GB", "params_tot": "7B",
                     "params_act": "7B", "capabilities": ["chat", "tools"], "moe": False,
                     "measured_loaded_gb": 5.0, "license": "Apache 2.0"},
        "Petit 1B": {"ollama_tag": "small:1b", "size_gb": "0.8 GB", "params_tot": "1B",
                     "params_act": "1B", "capabilities": ["chat"]},
        "Autre 4B": {"ollama_tag": "other:4b", "size_gb": "2.5 GB", "params_tot": "4B",
                     "params_act": "4B", "capabilities": ["chat"]},
        "Grand 14B": {"ollama_tag": "grand:14b", "size_gb": "9 GB", "params_tot": "14B",
                      "params_act": "14B", "capabilities": ["chat", "tools", "thinking"],
                      "moe": False, "ctx": 131072},
        "Mélange 30B": {"ollama_tag": "moe:30b", "size_gb": "18 GB", "params_tot": "30B",
                        "params_act": "3B", "capabilities": ["chat"], "moe": True},
    }
}  # fmt: skip
TAGS = ["mid:7b", "small:1b", "other:4b"]


@contextlib.asynccontextmanager
async def card_app(tmp_path: Path, *, with_bench: bool = True, available_gb: float = 12.0, **fake):
    bench = tmp_path / "slm-quality-results.json"
    if with_bench:
        shutil.copy(FIXTURE, bench)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(CATALOG), encoding="utf-8")
    server = FakeOllama(
        **{"tags": list(TAGS), "sizes": {"mid:7b": int(4.7 * GB), "small:1b": GB}, **fake}
    )
    config = make_settings(
        tmp_path,
        environ={"WAVELOCALAI_TESTING": "1", "GROQ_API_KEY": "gsk_test_0123456789"},
        cloud={"models": {"groq": ["openai/gpt-oss-120b"]}},
    )
    memory = lambda: MemoryReading(total_gb=32.0, available_gb=available_gb)  # noqa: E731
    registry = ModelRegistry(
        config,
        source=OllamaHttpSource(config.ollama.host, transport=server.transport),
        advisor=MemoryAdvisor(memory),
        catalog_path=catalog,
        bench_path=bench,
    )
    app = create_app(
        config,
        registry=registry,
        ollama_client=server.client(),
        ollama_transport=server.transport,
        memory_reader=memory,
    )
    async with app.router.lifespan_context(app):
        await registry.refresh()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=BASE, headers={"Origin": BASE}
        ) as client:
            yield app, client, bench


async def _card(client, tag):
    response = await client.get(f"/api/models/card/{tag}")
    assert response.status_code == 200, response.text
    return response.json()


def _row(card, machine_id):
    return next(row for row in card["references"]["rows"] if row["machine_id"] == machine_id)


async def test_an_installed_model_has_its_traits_and_values_stay_unknown_when_absent(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "mid:7b")
        bare = await _card(client, "other:4b")
    assert card["installed"] is True and card["origin"] == "local" and card["in_catalog"] is True
    assert (card["name"], card["architecture"]) == ("Moyen 7B", "dense")
    assert card["params_total_b"] is not None and card["params_active_b"] == 7.0
    assert card["license"] == "Apache 2.0" and card["tools_verified"] is True
    assert card["size_gb"] == 4.7 and card["fits"] is True
    assert card["quantization"] == "Q4_K_M"  # `/api/tags` (faux Ollama)
    # Rien n'est publié ni par `/api/show` ni par le catalogue : « inconnu », jamais 0.
    assert card["context_length"] is None
    assert bare["license"] is None
    assert bare["throughput_tps"] is None


async def test_a_catalog_model_not_installed_carries_whether_it_fits(tmp_path):
    async with card_app(tmp_path, available_gb=4.0) as (_, client, _b):
        card = await _card(client, "grand:14b")
        moe = await _card(client, "moe:30b")
    assert card["installed"] is False and card["in_catalog"] is True
    assert card["context_length"] == 131072 and card["reasoning"] is True
    assert card["fits"] is False and card["short_gb"] > 0 and card["required_gb"] > 0
    assert card["why"] is None  # pas installé : rien à expliquer sur ce poste
    assert (moe["architecture"], moe["params_total_b"], moe["params_active_b"]) == (
        "moe",
        30.0,
        3.0,
    )


async def test_a_cloud_model_has_no_local_figures(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "groq/openai/gpt-oss-120b")
    assert card["origin"] == "cloud" and card["why"] is None
    assert card["params_total_b"] is None and card["architecture"] is None
    assert card["tools_verified"] is None  # inconnu, jamais « non »


async def test_an_unknown_tag_is_a_404_with_the_standard_envelope(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        response = await client.get("/api/models/card/inconnu:1b")
    assert response.status_code == 404
    assert response.json()["code"] == "model_not_found"


async def test_a_tag_with_slashes_is_found(tmp_path):
    async with card_app(tmp_path, tags=[*TAGS, "hf.co/acme/depot:Q4_K_M"]) as (_, client, _b):
        card = await _card(client, "hf.co/acme/depot:Q4_K_M")
    assert card["tag"] == "hf.co/acme/depot:Q4_K_M" and card["installed"] is True


async def test_other_posts_list_the_pc_pro_first_with_published_figures(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "mid:7b")
    refs = card["references"]
    assert refs["available"] is True and refs["version"] == "exact"
    assert refs["bench_version"] == "1.4.0" and refs["pc_pro_published"] is True
    assert [row["machine_id"] for row in refs["rows"]] == ["pc-pro", "portable", "station"]
    pc = _row(card, "pc-pro")
    assert pc["pc_pro"] is True and pc["track"] == "think_off"  # la piste sans raisonnement
    assert pc["decode_tok_s"] == 5.2 and pc["load_time_s"] == 2.3
    assert pc["memory"]["gpu_fraction"] is None  # sans carte graphique
    assert (
        pc["memory"]["ram_peak_gb"] == 6.0 and pc["memory"]["ram_fraction"] == 0.4
    )  # 6144 / 15360
    portable = _row(card, "portable")
    assert portable["memory"]["gpu_fraction"] == 1.0 and portable["memory"]["ram_fraction"] == 0.125


async def test_energy_is_given_only_when_it_is_measured(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "mid:7b")
        small = await _card(client, "small:1b")
    assert _row(card, "pc-pro")["energy"] == {
        "status": "unavailable", "wh_per_1k_tokens": None, "power_avg_w": None,
    }  # fmt: skip
    assert _row(card, "portable")["energy"] == {
        "status": "measured", "wh_per_1k_tokens": 0.42, "power_avg_w": 55.0,
    }  # fmt: skip
    assert _row(small, "pc-pro")["energy"]["status"] == "unvalidated"
    assert _row(small, "pc-pro")["energy"]["wh_per_1k_tokens"] is None


async def test_a_null_stays_unknown_and_is_never_a_zero(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        small = await _card(client, "small:1b")
    row = _row(small, "pc-pro")
    assert row["measured"] is True and row["complete"] is False
    assert (
        row["decode_tok_s"] is None and row["prefill_tok_s"] is None and row["load_time_s"] is None
    )
    assert row["memory"]["ram_peak_gb"] is None and row["memory"]["ram_fraction"] is None
    missing = _row(small, "station")  # aucun résultat sur ce poste
    assert missing["measured"] is False and missing["decode_tok_s"] is None


async def test_another_digest_is_flagged_as_another_version(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "other:4b")
    assert card["references"]["version"] == "other_version"
    assert _row(card, "portable")["decode_tok_s"] == 25.0


async def test_a_catalog_model_shows_the_published_figures_without_comparing_digests(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "grand:14b")
    assert card["references"]["version"] == "unknown"
    assert _row(card, "station")["decode_tok_s"] == 38.0


async def test_a_model_the_bench_does_not_measure_says_so(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        card = await _card(client, "moe:30b")
    refs = card["references"]
    assert refs["available"] is True and refs["version"] == "not_published" and refs["rows"] == []


async def test_without_results_the_references_are_unavailable_with_a_reason(tmp_path):
    async with card_app(tmp_path, with_bench=False) as (_, client, _b):
        card = await _card(client, "mid:7b")
        listing = (await client.get("/api/models")).json()["models"]
    refs = card["references"]
    assert refs["available"] is False and "pas synchronisé" in refs["reason"]
    assert refs["rows"] == []
    assert card["why"] is not None  # le reste de la fiche reste valable
    assert all(model["accuracy"] is None for model in listing)


async def test_a_file_of_another_schema_is_unavailable_with_its_reason(tmp_path):
    async with card_app(tmp_path) as (_, client, bench):
        data = json.loads(bench.read_text(encoding="utf-8"))
        data["schema"] = "qb.results/2"
        bench.write_text(json.dumps(data), encoding="utf-8")
        card = await _card(client, "mid:7b")
    assert (
        card["references"]["available"] is False and "qb.results/1" in card["references"]["reason"]
    )


async def test_the_card_follows_a_change_of_the_results_file(tmp_path):
    async with card_app(tmp_path) as (_, client, bench):
        assert (await _card(client, "mid:7b"))["references"]["bench_version"] == "1.4.0"
        data = json.loads(bench.read_text(encoding="utf-8"))
        data["bench_version"] = "1.5.0"
        bench.write_text(json.dumps(data, indent=2), encoding="utf-8")
        assert (await _card(client, "mid:7b"))["references"]["bench_version"] == "1.5.0"


async def test_the_models_list_gets_the_published_accuracy_for_the_same_weights_only(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        models = {m["tag"]: m for m in (await client.get("/api/models")).json()["models"]}
    assert models["mid:7b"]["accuracy"] == 0.72
    assert models["other:4b"]["accuracy"] is None  # autres poids : pas de score
    assert models["small:1b"]["accuracy"] is None  # score `null` dans le fichier


# --- « Pourquoi ce débit ? » ---------------------------------------------------------------------


async def test_the_throughput_is_explained_by_active_parameters_quantization_and_vram(tmp_path):
    async with card_app(tmp_path) as (app, client, _b):
        app.state.system_sampler._gpu = {"memory_total_gb": 8.0}  # type: ignore[assignment]
        card = await _card(client, "mid:7b")
    why = card["why"]
    assert why["vram_gb"] == 8.0 and why["bandwidth_gb_s"] is None
    text = "\n".join(why["lines"])
    assert "active 7 milliards de paramètres" in text
    assert "garde tout le modèle en mémoire vidéo" in text  # 5 Go d'empreinte dans 8 Go de VRAM
    assert "bande passante mémoire de ce poste n'est pas mesurée" in text
    assert "Aucun débit n'est encore mesuré" in text  # aucun run sur ce poste


async def test_a_model_larger_than_the_vram_is_said_to_spill_into_memory(tmp_path):
    async with card_app(tmp_path) as (app, client, _b):
        app.state.system_sampler._gpu = {"memory_total_gb": 3.0}  # type: ignore[assignment]
        text = "\n".join((await _card(client, "mid:7b"))["why"]["lines"])
    assert "dépasse la mémoire vidéo de 3" in text and "mémoire vive, plus lente" in text


async def test_without_a_gpu_the_weights_are_read_from_ram(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        why = (await _card(client, "mid:7b"))["why"]
    assert why["vram_gb"] is None
    assert "lus dans la mémoire vive" in "\n".join(why["lines"])


async def test_punctuation_in_the_explanation_keeps_a_non_breaking_space(tmp_path):
    async with card_app(tmp_path) as (_, client, _b):
        lines = (await _card(client, "mid:7b"))["why"]["lines"]
    assert not any(" :" in line or " ;" in line or " ?" in line for line in lines)
    assert any(" :" in line for line in lines)


# --- Budget de lecture (AD-15) -------------------------------------------------------------------


def test_the_card_answers_under_300_ms_with_ollama_down(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "bench.json")
    settings = make_settings(tmp_path, ollama={"host": f"http://127.0.0.1:{closed_port()}"})
    app = create_app(settings)
    app.state.registry.bench._path = tmp_path / "bench.json"  # le fichier de la fixture, en tmp
    client = TestClient(app, base_url=BASE)
    timings = []
    for tag in ("mid:7b", "inconnu:1b"):
        started = time.perf_counter()
        response = client.get(f"/api/models/card/{tag}")
        timings.append(time.perf_counter() - started)
        assert response.status_code in (200, 404), response.text
    assert max(timings) < 0.3, timings
