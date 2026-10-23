"""Flow 1 d'EXPERIENCE.md (story 3.6) de bout en bout dans un vrai navigateur, sur le vrai serveur :
l'Accueil dit « Disponible », la comparaison se lance depuis la carte « Démo recommandée », les colonnes
se remplissent, le classement ne vaut que pour les modèles notés, l'export contient la preuve de la
mesure, et la page n'est jamais rechargée.

Trois modèles `fake` : Alpha répond et est noté, Bravo dépasse son délai, Charlie rend une réponse vide
(« non évalué »). Ollama est un `FakeOllama` ; la liste des modèles est simulée comme pour l'Arène.
La recette humaine rejoue ce parcours sur une démo réelle (Ollama, vrais modèles).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from .test_arena import (  # noqa: F401  (`cancel_leftover_runs` est une fixture automatique)
    DONE,
    JUDGE_DEFAULT,
    NBSP,
    cancel_leftover_runs,
    install_models,
    lane,
    launch,
    scripted,
    verdict,
    wait_banner,
)
from .test_home import wait_card
from .test_shell import assert_no_axe_violations, assert_no_horizontal_scroll, wait_for, wait_ready

SCRIPTS = {
    "fake:a": [{"text": "Alpha répond"}, {"done": DONE}],
    "fake:b": [{"text": "Début"}, {"fail": "timeout"}],  # délai dépassé
    "fake:c": [{"done": DONE}],  # réponse vide : « non évalué »
}
JUDGE = {"script": verdict(72), "origin": "local"}


@pytest.fixture
def flow(backend, fake_ollama, page):
    """L'Accueil sur un serveur dont Ollama (le FakeOllama) répond, trois modèles prêts."""
    backend.ollama_port = fake_ollama.port
    fake_ollama.start()
    server = backend.start()
    install_models(page, defaults=("fake:a", "fake:b", "fake:c"))
    commands: list[dict] = []
    scripted(page, server, SCRIPTS, commands, judge=JUDGE)
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    page.evaluate("window.__noReload = true")  # un rechargement l'effacerait
    wait_card(page, "system", "Disponible")
    wait_for(page, "() => document.querySelector('[data-demo]')?.dataset.state === 'ready'")
    return page, server, commands


def test_flow_1_from_the_home_card_to_the_export_without_a_reload(flow):
    page, server, commands = flow
    # 1. L'Accueil dit « Disponible » et la carte propose les trois modèles prêts.
    assert page.locator('[data-card="system"]').inner_text().count("Disponible") == 1
    card = page.locator("[data-demo]")
    assert card.locator(".home-demo-item .home-demo-model").all_inner_texts() == [
        "Alpha 1B",
        "Bravo 2B",
        "Charlie 3B",
    ]

    # 2. Elle ouvre l'Arène avec ces modèles présélectionnés ; la question tient dans le champ.
    card.get_by_role("link", name="Lancer une comparaison").click()
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 3")
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1"
    )
    launch(page)

    # 3. Les colonnes se remplissent, chacune avec son statut en texte.
    lane(page, "fake:a").locator(".wl-md").filter(has_text="Alpha répond").wait_for()
    wait_banner(page, "Comparaison terminée")
    assert page.locator("wl-arena-lane").count() == 3
    assert lane(page, "fake:b").locator(".wl-lane-status-text").inner_text() == "Délai dépassé"
    assert commands[0]["models"] == ["fake:a", "fake:b", "fake:c"]

    # 4. Le classement ne vaut que pour les modèles notés ; les autres disent pourquoi, sans rang.
    wait_for(page, "() => document.querySelectorAll('.arena-rank-item').length === 1")
    assert page.locator(".arena-rank-item .arena-rank-name").all_inner_texts() == ["Alpha 1B"]
    reasons = page.locator(".arena-unranked-reason").all_inner_texts()
    assert [r.replace(NBSP, " ") for r in reasons] == [
        "Non évalué : délai dépassé",
        "Non évalué : réponse vide",
    ]
    assert "0/100" not in page.locator(".arena-ranking").inner_text()

    # 5. L'export contient, par modèle, la note et la raison, et la preuve de la mesure.
    wait_for(page, "() => !document.querySelector('.arena-run-actions button').disabled")
    group = page.get_by_role("group", name="Actions sur cette comparaison")
    with page.expect_download() as download:
        group.get_by_role("button", name="Exporter en CSV").click()
    text = Path(download.value.path()).read_text(encoding="utf-8-sig")
    rows = {row["model"]: row for row in csv.DictReader(io.StringIO(text))}
    assert set(rows) == {"fake:a", "fake:b", "fake:c"}
    assert rows["fake:a"]["score"] == "72" and rows["fake:a"]["tps_source"] == "ollama_eval"
    assert rows["fake:b"]["status"] == "timeout" and rows["fake:b"]["score"] == ""
    assert rows["fake:c"]["score"] == "" and "réponse vide" in rows["fake:c"]["reason"]
    proof = rows["fake:a"]
    assert proof["machine_os"] and proof["machine_cpu"] and proof["app_version"]
    assert proof["ollama_version"] == "0.9.9"  # celle du FakeOllama, vue par la sonde
    assert proof["judge"] == JUDGE_DEFAULT and proof["criteria"]
    assert "model_digest" in proof and proof["co2_method"]
    assert "key" not in text.lower().replace("keyboard", "")  # aucune clé d'API
    with page.expect_download() as markdown:
        group.get_by_role("button", name="Exporter en Markdown").click()
    assert "## Preuve de la mesure" in Path(markdown.value.path()).read_text(encoding="utf-8")

    # 6. La page n'a jamais été rechargée.
    assert page.evaluate("window.__noReload") is True
    assert page.evaluate("performance.getEntriesByType('navigation').length") == 1


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_flow_1_screens_have_no_axe_violation_in_either_theme(flow, theme):
    page, server, _ = flow
    page.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    assert_no_axe_violations(page, f"Accueil avec la démo, thème {theme}")
    page.locator("[data-demo]").get_by_role("link", name="Lancer une comparaison").click()
    wait_for(page, "() => document.querySelector('wl-model-picker')?.values.length === 3")
    wait_for(
        page, "() => document.querySelector('wl-model-picker[purpose=judge]')?.values.length === 1"
    )
    launch(page)
    wait_banner(page, "Comparaison terminée")
    wait_for(page, "() => !document.querySelector('.arena-run-actions button').disabled")
    wait_for(page, "() => document.querySelectorAll('.arena-history-item').length >= 1")
    assert_no_axe_violations(page, f"Arène terminée, thème {theme}")
    assert_no_horizontal_scroll(page)
    page.set_viewport_size({"width": 320, "height": 900})
    assert_no_axe_violations(page, f"Arène terminée, 320 px, thème {theme}")
    assert_no_horizontal_scroll(page)
