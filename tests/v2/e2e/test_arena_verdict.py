"""Verdict local/cloud de l'Arène (story 3.5) dans un vrai navigateur, sur le vrai serveur.

Le serveur de ce fichier est lancé avec une table de prix de test (`--config`) : les prix et la
date n'ont aucune valeur réelle, ils servent à vérifier le calcul et l'affichage ; la vraie table de
`wavelocalai.toml` est vide tant qu'aucun prix sourcé n'est relevé. Les lanes sont des `fake`
scriptés (l'une d'origine cloud), le juge note 70 partout (égalité), par le vrai service de l'Arène.
Chaque test qui lance une comparaison attend sa fin.

L'écran ne calcule rien : un test réécrit l'instantané du run (`page.route`) et vérifie que la page
affiche exactement ce que le serveur lui dit.
"""

from __future__ import annotations

import json
import re

import pytest

from .conftest import Backend
from .test_arena import (  # noqa: F401  (`cancel_leftover_runs` est une fixture automatique)
    BASE_MODEL,
    DONE,
    JUDGE_DEFAULT,
    STARTED,
    cancel_leftover_runs,
    install_models,
    launch,
    pick,
    verdict,
    wait_banner,
)
from .test_arena_results import wait_names
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

PRICE_TABLE = """\
[cloud.prices]
currency = "EUR"
retrieved_at = 2026-03-04
source = "https://exemple.invalid/prix"

[cloud.prices.models]
"fake:nuage" = { input_per_mtok = 2.0, output_per_mtok = 10.0 }
"""
NUAGE = {**BASE_MODEL, "tag": "fake:nuage", "name": "Nuage 70B", "origin": "cloud"}
AUTRE = {**BASE_MODEL, "tag": "fake:autre", "name": "Autre 30B", "origin": "cloud"}
CLOUD_TAGS = {"fake:nuage", "fake:autre"}


@pytest.fixture(scope="module")
def priced(tmp_path_factory):
    """Le serveur avec une table de prix de test."""
    folder = tmp_path_factory.mktemp("e2e-verdict")
    config = folder / "wavelocalai.toml"
    config.write_text(PRICE_TABLE, encoding="utf-8")
    data = folder / "data"
    data.mkdir()
    backend = Backend(data, config=config)
    try:
        yield backend.start()
    finally:
        backend.stop()


def scripted_with_clouds(page, server):
    """Les commandes de la page lancent des lanes `fake` (celles de `CLOUD_TAGS` d'origine cloud) et
    un juge local qui note 70."""

    def on_arena(route):
        body = json.loads(route.request.post_data)
        lanes = [
            {
                "tag": tag,
                "origin": "cloud" if tag in CLOUD_TAGS else "local",
                "script": [{"text": "Une réponse"}, {"done": DONE}],
            }
            for tag in body["models"]
        ]
        payload = {
            "prompt": body["prompt"],
            "criteria": body.get("criteria", []),
            "allow_cloud": body["allow_cloud"],
            "lanes": lanes,
            "judge": {"tag": body["judge"], "script": verdict(70), "origin": "local"},
        }
        response = page.request.post(f"{server.base_url}/api/test/arena", data=payload)
        if response.ok:
            STARTED.append((server.base_url, response.json()["run_id"]))
        route.fulfill(status=response.status, content_type="application/json", body=response.text())

    page.route(re.compile(r"/api/arena/runs$"), on_arena)


def open_arena(page, server, cloud=()):
    install_models(page, cloud=list(cloud), judge_tags=(JUDGE_DEFAULT,))
    scripted_with_clouds(page, server)
    page.goto(f"{server.base_url}/#/arene/comparer")
    wait_ready(page)
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 2")
    wait_for(
        page,
        "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1",
    )
    if cloud:
        page.evaluate(
            """async () => {
                const { store } = await import('/static/core/store.js');
                store.set({ allowCloud: true });
            }"""
        )


def compare(page, cloud_name=None):
    """Lance la comparaison (un cloud remplace Bravo si `cloud_name`) et attend sa fin."""
    if cloud_name:
        page.get_by_role("button", name="Retirer Bravo 2B").click()
        pick(page, cloud_name)
    launch(page)
    wait_banner(page, "Comparaison terminée")


def rows(page) -> dict[str, str]:
    """Libellé -> texte de chaque ligne du verdict (espaces insécables ramenés à des espaces)."""
    items = page.locator(".arena-verdict-row")
    out = {}
    for index in range(items.count()):
        label = items.nth(index).locator("dt").inner_text()
        value = items.nth(index).locator("dd").inner_text()
        out[re.sub(r"[  ]", " ", label)] = re.sub(r"\s+", " ", re.sub(r"[  ]", " ", value))
    return out


def verdict_section(page):
    return page.locator(".arena-verdict")


# --- Lecture de l'instantané ----------------------------------------------------------------------


def test_the_verdict_is_read_from_the_snapshot_at_the_end_and_on_reopening(page, priced):
    open_arena(page, priced, cloud=[NUAGE])
    snapshots: list[str] = []
    page.on(
        "response",
        lambda response: (
            snapshots.append(response.url) if re.search(r"/api/runs/[^/]+$", response.url) else None
        ),
    )
    compare(page, "Nuage 70B")
    verdict_section(page).wait_for(state="visible")
    run_id = re.search(r"/api/runs/([^/]+)$", snapshots[-1]).group(1)
    assert len(snapshots) == 1  # une lecture, à `run_ended`, jamais pendant le flux
    live = rows(page)
    assert list(live) == [
        "Écart de note",
        "Coût pour 1 000 requêtes de même taille",
        "CO₂ par réponse",
        "Données restées sur le poste",
    ]
    assert live["Écart de note"] == "Alpha 1B et Nuage 70B sont à égalité (70/100)."
    assert live["Données restées sur le poste"] == (
        "Les questions et les réponses d'un modèle local n'ont pas quitté ce poste."
    )
    assert page.get_by_role("heading", name="Verdict local et cloud").is_visible()
    # Rouvrir par l'adresse : la même lecture de l'instantané, sans relancer de modèle.
    page.goto(f"{priced.base_url}/#/arene/comparer/{run_id}")
    page.reload()
    wait_ready(page)
    wait_banner(page, "Comparaison terminée")
    verdict_section(page).wait_for(state="visible")
    # Les colonnes, puis le verdict, prennent leur nom d'affichage à l'arrivée de la liste des modèles.
    wait_names(page)
    # Après un rechargement, l'interrupteur cloud est coupé (AD-20) : la liste n'a plus le modèle
    # cloud, que les colonnes (donc le verdict) nomment alors par son identifiant, comme depuis 3.2.
    reopened = {
        label: text.replace("fake:nuage", "Nuage 70B") for label, text in rows(page).items()
    }
    assert reopened == live


def test_the_verdict_shows_the_price_table_date_with_the_cost(page, priced):
    open_arena(page, priced, cloud=[NUAGE])
    compare(page, "Nuage 70B")
    verdict_section(page).wait_for(state="visible")
    cost = rows(page)["Coût pour 1 000 requêtes de même taille"]
    # 1 000 x (4 tokens x 2 + 12 tokens x 10) / 1 000 000 = 0,128 : le prix daté de la table.
    assert cost.startswith("0,00 € en local ; 0,128 € avec Nuage 70B.")
    assert "Prix relevés le 4 mars 2026." in cost
    assert "Source : https://exemple.invalid/prix." in cost
    assert "inconnu" not in cost


def test_an_unknown_cost_says_why_and_is_never_zero(page, priced):
    open_arena(page, priced, cloud=[AUTRE])
    compare(page, "Autre 30B")
    verdict_section(page).wait_for(state="visible")
    cost = rows(page)["Coût pour 1 000 requêtes de même taille"]
    assert "inconnu avec Autre 30B" in cost
    assert "Ce modèle ne figure pas dans la table de prix cloud." in cost
    assert "0,00 € avec" not in cost and "0 € avec" not in cost
    assert "Prix relevés le 4 mars 2026." in cost  # la date de la table reste dite


def test_a_comparison_without_cloud_has_no_verdict_section(page, priced):
    open_arena(page, priced)
    compare(page)
    page.locator(".arena-results").wait_for(state="visible")
    assert verdict_section(page).is_hidden()
    assert page.get_by_role("heading", name="Verdict local et cloud").count() == 0
    assert page.locator(".arena-rank-item").count() == 2  # le classement suffit


def test_the_screen_shows_what_the_server_says_and_computes_nothing(page, priced):
    open_arena(page, priced, cloud=[NUAGE])
    doctored = {
        "leader": "cloud",
        "score_gap": 7,
        "local": {
            "model": "fake:a",
            "score": 63,
            "co2": None,
            "cost": {"amount": 0.0, "currency": "USD", "reason": None},
        },
        "cloud": {
            "model": "fake:nuage",
            "score": 70,
            "co2": {
                "mg": 5.0,
                "method": "ecologits",
                "estimated": True,
                "range_mg": None,
                "allocation": "direct",
                "reason": None,
            },
            "cost": {"amount": 12.5, "currency": "USD", "reason": None},
        },
        "requests": 1000,
        "price_table": {"retrieved_at": "2025-12-31", "source": None, "currency": "USD"},
        "data_on_device": {"models": ["fake:a"], "count": 1, "judge_off_device": True},
    }

    def on_snapshot(route):
        response = route.fetch()
        data = response.json()
        data["verdict"] = doctored
        route.fulfill(response=response, body=json.dumps(data))

    page.route(re.compile(r"/api/runs/[^/]+$"), on_snapshot)
    compare(page, "Nuage 70B")
    verdict_section(page).wait_for(state="visible")
    shown = rows(page)
    assert shown["Écart de note"] == "Nuage 70B (70/100) devance Alpha 1B (63/100) de 7 points."
    cost = shown["Coût pour 1 000 requêtes de même taille"]
    assert "12,50" in cost and "$" in cost and "Prix relevés le 31 déc. 2025." in cost
    assert "Source" not in cost  # sans source dans la table, aucune source n'est inventée
    assert (
        "5 mg (estimé)" in shown["CO₂ par réponse"]
        and "non mesurable" not in shown["CO₂ par réponse"]
    )
    assert "Alpha 1B" in shown["CO₂ par réponse"] or "en local" in shown["CO₂ par réponse"]
    assert shown["Données restées sur le poste"].startswith("Le juge est un modèle cloud")


def test_a_snapshot_read_before_the_final_status_is_written_is_read_again(page, priced):
    # Le hub publie `run_ended` avant d'écrire le statut final : la première lecture peut encore
    # dire `running`, sans verdict. L'écran relit au lieu de cacher la section.
    open_arena(page, priced, cloud=[NUAGE])
    reads = []

    def on_snapshot(route):
        response = route.fetch()
        data = response.json()
        reads.append(data["status"])
        if len(reads) == 1:
            data["status"], data["verdict"] = "running", None
        route.fulfill(response=response, body=json.dumps(data))

    page.route(re.compile(r"/api/runs/[^/]+$"), on_snapshot)
    compare(page, "Nuage 70B")
    verdict_section(page).wait_for(state="visible")
    assert len(reads) >= 2
    assert page.locator(".arena-verdict-row").count() == 4


def test_a_failed_snapshot_read_says_so_without_a_verdict(page_tolerating_failed_requests, priced):
    page = page_tolerating_failed_requests
    open_arena(page, priced, cloud=[NUAGE])
    page.route(re.compile(r"/api/runs/[^/]+$"), lambda route: route.fulfill(status=500, body="{}"))
    compare(page, "Nuage 70B")
    verdict_section(page).wait_for(state="visible")
    assert "n'a pas pu être lu" in verdict_section(page).inner_text()
    assert page.locator(".arena-verdict-row").count() == 0


# --- Accessibilité --------------------------------------------------------------------------------


@pytest.mark.parametrize("width", [320, 1440])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_axe_finds_no_violation_on_the_verdict(page, priced, theme, width):
    open_arena(page, priced, cloud=[NUAGE])
    page.set_viewport_size({"width": width, "height": 900})
    compare(page, "Nuage 70B")
    verdict_section(page).wait_for(state="visible")
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"verdict, {width} px, thème {theme}")
    assert_no_horizontal_scroll(page)


def test_the_unknown_cost_has_no_violation_either(page, priced):
    open_arena(page, priced, cloud=[AUTRE])
    page.set_viewport_size({"width": 320, "height": 900})
    compare(page, "Autre 30B")
    verdict_section(page).wait_for(state="visible")
    page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    assert_no_axe_violations(page, "verdict à coût inconnu, 320 px, thème dark")
    assert_no_horizontal_scroll(page)
