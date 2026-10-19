"""« Quel modèle pour quel usage » (story 5.8) : `GET /api/references`. L'app est la vraie, Ollama un
faux ; les résultats du banc viennent de la fixture `tests/v2/fixtures/` réécrite en dossier temporaire
(aucun fichier de `benchmarks/` n'est lu ni écrit)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from wavelocalai.models.usage_references import NONE_INSTALLED, OLLAMA_DOWN
from wavelocalai.web.app import create_app

from ..conftest import closed_port, make_settings
from .test_model_card_api import BASE, FIXTURE, card_app


def scope(score, low=None, high=None, status=None):
    body = {"score": score, "ci_low": low, "ci_high": high, "n_units": 40, "coverage": 1.0}
    if status:
        body["status"] = status
    return body


# (modèle, poste, piste) -> usages publiés ; les autres résultats de la fixture n'en ont aucun.
USAGES = {
    ("mid:7b", "pc-pro", "think_off"): {
        "tools": scope(0.72, 0.67, 0.77),
        "reasoning": scope(0.5, 0.45, 0.55),
        "writing": scope(0.4, 0.3, 0.5, status="provisional"),
    },
    ("mid:7b", "pc-pro", "think_on"): {"tools": scope(0.9, 0.85, 0.95)},  # jamais choisi
    ("grand:14b", "pc-pro", "think_off"): {"tools": scope(0.78, 0.73, 0.83)},
    ("other:4b", "portable", "think_off"): {"tools": scope(0.55, 0.5, 0.6)},
    ("small:1b", "pc-pro", "think_off"): {"tools": scope(None)},
}


def bench_data(usages=USAGES):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for result in data["results"]:
        key = (result["model"], result["machine"], result["track"])
        result["quality"]["usages"] = usages.get(key, {})
    return data


def write(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


async def _references(client):
    response = await client.get("/api/references")
    assert response.status_code == 200, response.text
    return response.json()


def _usage(body, usage_id):
    return next(u for u in body["usages"] if u["id"] == usage_id)


async def test_a_card_per_published_usage_with_the_best_group_designated_by_the_server(tmp_path):
    async with card_app(tmp_path, bench_data=bench_data()) as (_, client, _b):
        body = await _references(client)
    assert body["available"] is True and body["source"] == "slm-quality-bench"
    # Aucune carte pour un usage sans modèle classé (`writing` n'a que du provisoire).
    assert [u["id"] for u in body["usages"]] == ["reasoning", "tools"]
    tools = _usage(body, "tools")
    assert tools["label"] == "Appel d'outils" and tools["measure"].startswith("Part d")
    # Le meilleur (0,78) et celui dont l'intervalle l'atteint (0,77 >= 0,73) forment le groupe, par nom.
    assert [(e["name"], e["group"]) for e in tools["entries"]] == [
        ("Grand 14B", "best"),
        ("Moyen 7B", "best"),
        ("Autre 4B", "other"),
        ("Petit 1B", None),  # mesuré, mais sans score : « non classé »
    ]
    assert tools["best_count"] == 2
    moyen = tools["entries"][1]
    # La piste sans raisonnement l'emporte sur celle qui raisonne (0,9) : règle de la 5.6.
    assert (moyen["score"], moyen["ci_low"], moyen["ci_high"]) == (0.72, 0.67, 0.77)
    assert "rank" not in moyen and "rang" not in moyen
    assert _usage(body, "reasoning")["best_count"] == 1


async def test_the_reference_machine_gives_the_throughput_and_unknown_stays_null(tmp_path):
    async with card_app(tmp_path, bench_data=bench_data()) as (_, client, _b):
        body = await _references(client)
    assert body["reference_machine"]["id"] == "pc-pro" and body["reference_machine"]["gpu"] is None
    assert body["reference_machine"]["ram_gb"] == 15.0
    by_name = {e["name"]: e for e in _usage(body, "tools")["entries"]}
    assert by_name["Moyen 7B"]["decode_tok_s"] == 5.2
    assert by_name["Grand 14B"]["decode_tok_s"] == 2.1
    # « Autre 4B » n'est mesuré que sur le portable : son score vient de là, son débit est inconnu.
    assert by_name["Autre 4B"]["score"] == 0.55 and by_name["Autre 4B"]["decode_tok_s"] is None
    assert by_name["Petit 1B"]["score"] is None
    assert all(e["energy_wh_per_1k_tokens"] is None for e in by_name.values())  # `unavailable`


async def test_energy_is_given_only_when_measured(tmp_path):
    data = bench_data()
    for result in data["results"]:
        if result["model"] == "mid:7b" and result["machine"] == "pc-pro":
            status = "measured" if result["track"] == "think_off" else "unvalidated"
            result["energy"] = {"status": status, "gpu_power_avg_w": 30, "gpu_wh_per_1k_tokens": 0.4}
        if result["model"] == "grand:14b" and result["machine"] == "pc-pro":
            result["energy"] = {
                "status": "unvalidated",
                "gpu_power_avg_w": 30,
                "gpu_wh_per_1k_tokens": 0.9,
            }
    async with card_app(tmp_path, bench_data=data) as (_, client, _b):
        body = await _references(client)
    by_name = {e["name"]: e for e in _usage(body, "tools")["entries"]}
    assert by_name["Moyen 7B"]["energy_wh_per_1k_tokens"] == 0.4
    assert by_name["Grand 14B"]["energy_wh_per_1k_tokens"] is None


async def test_marks_say_installed_other_version_or_nothing_and_compare_targets_the_group(tmp_path):
    async with card_app(tmp_path, bench_data=bench_data()) as (_, client, _b):
        body = await _references(client)
    tools = _usage(body, "tools")
    marks = {e["name"]: e["installed"] for e in tools["entries"]}
    assert marks == {
        "Grand 14B": None,  # au catalogue seulement
        "Moyen 7B": "installed",
        "Autre 4B": "other_version",  # même tag, autres poids
        "Petit 1B": "installed",
    }
    # Le groupe est Grand (pas installé) et Moyen : seul Moyen part dans l'Arène.
    assert tools["compare"] == {"tags": ["mid:7b"], "reason": None}
    assert body["ollama_up"] is True


async def test_compare_is_empty_with_its_reason_when_no_group_model_is_installed(tmp_path):
    data = bench_data()
    data["results"] = [r for r in data["results"] if r["model"] == "grand:14b"]
    async with card_app(tmp_path, bench_data=data) as (_, client, _b):
        body = await _references(client)
    assert _usage(body, "tools")["compare"] == {"tags": [], "reason": NONE_INSTALLED}


async def test_compare_takes_at_most_four_models_by_name(tmp_path):
    tags = [f"m{n}:1b" for n in range(6)]
    data = bench_data({})
    data["models"] = [
        {**data["models"][0], "tag": tag, "digest": f"d-{tag}", "name": f"Modèle {n}"}
        for n, tag in enumerate(tags)
    ]
    data["results"] = [
        {
            **data["results"][0],
            "model": tag,
            "digest": f"d-{tag}",
            "machine": "pc-pro",
            "track": "think_off",
            "quality": {"global": scope(0.7), "usages": {"tools": scope(0.7)}},
        }
        for tag in tags
    ]
    async with card_app(tmp_path, tags=tags, bench_data=data) as (_, client, _b):
        body = await _references(client)
    tools = _usage(body, "tools")
    assert tools["best_count"] == 6  # six scores égaux, aucun rang
    assert tools["compare"]["tags"] == tags[:4]


async def test_an_interval_missing_means_the_score_alone(tmp_path):
    data = bench_data(
        {
            ("mid:7b", "pc-pro", "think_off"): {"tools": scope(0.72)},
            ("grand:14b", "pc-pro", "think_off"): {"tools": scope(0.78)},
        }
    )
    async with card_app(tmp_path, bench_data=data) as (_, client, _b):
        body = await _references(client)
    tools = _usage(body, "tools")
    assert [(e["name"], e["group"]) for e in tools["entries"] if e["group"]] == [
        ("Grand 14B", "best"),
        ("Moyen 7B", "other"),
    ]
    assert tools["entries"][0]["ci_low"] is None


async def test_the_best_score_of_all_cards_is_given_for_the_home_card(tmp_path):
    async with card_app(tmp_path, bench_data=bench_data()) as (_, client, _b):
        body = await _references(client)
    assert body["top"] == {
        "usage": "tools",
        "usage_label": "Appel d'outils",
        "measure": "Part d'appels d'outils corrects",
        "tag": "grand:14b",
        "name": "Grand 14B",
        "score": 0.78,
    }
    assert body["published"] == "2026-10-01" and body["bench_version"] == "1.4.0"


async def test_without_the_results_file_the_reason_is_given_and_no_card(tmp_path):
    async with card_app(tmp_path, with_bench=False) as (_, client, _b):
        body = await _references(client)
    assert body["available"] is False and body["reason_code"] == "missing"
    assert "pas synchronisé" in body["reason"] and body["usages"] == [] and body["top"] is None


async def test_a_file_of_another_schema_is_unavailable_not_an_error(tmp_path):
    async with card_app(tmp_path, bench_data={**bench_data(), "schema": "qb.results/2"}) as (_, client, _b):
        body = await _references(client)
    assert body["available"] is False and body["reason_code"] == "schema"


async def test_a_file_without_any_ranked_model_has_no_empty_card(tmp_path):
    async with card_app(tmp_path, bench_data=bench_data({})) as (_, client, _b):
        body = await _references(client)
    assert body["available"] is False and body["reason_code"] == "no_usage"
    assert body["usages"] == [] and body["bench_version"] == "1.4.0"


async def test_without_a_pc_pro_the_throughput_is_unknown(tmp_path):
    data = bench_data({})
    data["machines"] = [m for m in data["machines"] if m["id"] != "pc-pro"]
    for result in data["results"]:
        if result["machine"] == "portable" and result["model"] == "mid:7b":
            result["quality"]["usages"] = {"tools": scope(0.71, 0.66, 0.76)}
        if result["machine"] == "station" and result["model"] == "grand:14b":
            result["quality"]["usages"] = {"tools": scope(0.5, 0.45, 0.55)}
    async with card_app(tmp_path, bench_data=data) as (_, client, _b):
        body = await _references(client)
    assert body["reference_machine"] is None and body["available"] is True
    tools = _usage(body, "tools")
    assert all(e["decode_tok_s"] is None for e in tools["entries"])
    assert [(e["name"], e["group"]) for e in tools["entries"] if e["group"]] == [
        ("Moyen 7B", "best"),
        ("Grand 14B", "other"),
    ]


def test_references_stay_readable_with_ollama_down_and_without_marks_in_under_300_ms(tmp_path):
    data_path = tmp_path / "bench.json"
    write(data_path, bench_data())
    settings = make_settings(tmp_path, ollama={"host": f"http://127.0.0.1:{closed_port()}"})
    app = create_app(settings)
    app.state.registry.bench._path = data_path
    client = TestClient(app, base_url=BASE)
    started = time.perf_counter()
    response = client.get("/api/references")
    elapsed = time.perf_counter() - started
    body = response.json()
    assert response.status_code == 200 and elapsed < 0.3, elapsed
    assert body["ollama_up"] is False and body["available"] is True
    tools = _usage(body, "tools")
    assert all(e["installed"] is None for e in tools["entries"])
    assert tools["compare"] == {"tags": [], "reason": OLLAMA_DOWN}
    assert [e["name"] for e in tools["entries"] if e["group"] == "best"] == ["Grand 14B", "Moyen 7B"]
