"""Parcours « Évaluation et Banc d'essai » de bout en bout (story 8.3), sans recharger la page.

Un seul chargement de page. L'Évaluation de la qualité d'abord : les trois étapes avancent et les
notes arrivent au fil de l'eau, un « non évalué » garde sa raison. Puis le Banc d'essai, par la
navigation de l'application : un format violé est signalé, « Relancer le test » rend un format
respecté. Enfin le retour à l'Évaluation, dont le résultat se rouvre depuis sa liste sans relancer de
modèle.

Doublures : celles de `test_evaluation.py` (flux et instantanés fixés par le test, `page.route`) et de
`test_bench.py` (le vrai serveur, le modèle `fake` scripté, liste des modèles simulée). Ollama n'est
jamais sollicité, aucune requête ne sort de 127.0.0.1 (fixture `context` et bilan de la suite).
"""

from __future__ import annotations

import re

from .parcours import assert_never_reloaded, mark_no_reload, open_module, open_tab, wait_screen
from .test_bench import BAD, GOOD
from .test_bench import NBSP as BENCH_NBSP
from .test_bench import install_models as install_bench_models
from .test_bench import launch as bench_launch
from .test_bench import run_test as run_bench_test
from .test_bench import script as bench_script
from .test_bench import verdict_text
from .test_evaluation import (
    Scenario,
    cell_text,
    fill_question,
    launch_button,
)
from .test_evaluation import open_screen as open_evaluation
from .test_evaluation import (
    step_state,
    wait_post,
)
from .test_shell import wait_for


def test_parcours_evaluation_puis_banc_d_essai_sans_recharger_la_page(page, server):
    scenario = Scenario()
    wire = open_evaluation(page, server, scenario)
    wire.released = 0  # le test lâche les événements phase par phase
    mark_no_reload(page)

    # 1. L'Évaluation : le formulaire part avec la question, les modèles et le juge.
    fill_question(page)
    launch_button(page).click()
    command = wait_post(wire)
    assert command["models"] == ["fake:a", "fake:b"] and command["allow_cloud"] is False
    wait_for(page, "() => document.querySelector('form.eval-form').hidden")

    # 2. Les étapes avancent, les notes arrivent au fil de l'eau, jamais « 0/100 » en attendant.
    wire.release(0)
    wait_for(page, "() => document.querySelectorAll('.eval-lane').length === 2")
    assert step_state(page, "retrieval").endswith("en cours")
    wire.release(2)
    wait_for(
        page,
        "() => document.querySelector('.eval-step[data-step=answers]')?.textContent.includes('fait')",
    )
    wire.release(3)
    wait_for(page, "() => document.querySelectorAll('.eval-score').length === 3")
    assert cell_text(page, "Alpha 1B", 1) == "33/100"
    assert cell_text(page, "Bravo 2B", 1) == "en cours"
    assert not re.search(r"(?<!\d)0/100", page.inner_text(".eval-results"))
    wire.release(4)
    wait_for(
        page, "() => document.querySelector('.eval-banner-text')?.textContent.includes('terminée')"
    )

    # 3. Une note impossible reste « non évalué » avec sa raison, jamais un zéro.
    assert cell_text(page, "Bravo 2B", 2) == "non évalué (sortie du juge invalide)"
    assert page.locator(".eval-history-item").count() == 1

    # 4. Le Banc d'essai, par la navigation : un format violé est dit, sa première violation aussi.
    install_bench_models(page)
    bench_script(page, server, BAD)
    open_module(page, "Arène")
    open_tab(page, "Arène", "Banc d'essai", "arena-bench")
    wait_for(
        page,
        "() => document.querySelector('[data-screen=\"arena-bench\"] wl-model-picker')?.value === 'fake:1b'",
    )
    wait_for(page, "() => !!document.querySelector('[data-screen=\"arena-bench\"] .bc-form')")
    run_bench_test(page)
    assert verdict_text(page) == (
        f"« sentiment »{BENCH_NBSP}: valeur hors de la liste permise (Positif, Neutre, Négatif)"
    )
    assert page.locator(".bc-verdict-line").get_attribute("data-ok") == "false"

    # 5. « Relancer le test » avec une sortie conforme : « Format respecté ».
    bench_script(page, server, GOOD)
    with page.expect_response(re.compile(r"/api/bench/runs$")) as again:
        page.get_by_role("button", name="Relancer le test").click()
    assert again.value.ok
    wait_for(
        page,
        "() => document.querySelector('.bc-verdict-line')?.dataset.ok === 'true'",
    )
    assert verdict_text(page) == "Format respecté"
    assert page.locator(".bc-json").inner_text() == (
        '{\n  "sentiment": "Neutre",\n  "categorie": "formation"\n}'
    )

    # 6. Retour à l'Évaluation : son résultat se rouvre depuis la liste, sans relancer de modèle.
    open_module(page, "Documents")
    open_tab(page, "Documents", "Évaluation de la qualité", "documents-evaluation")
    wait_for(page, "() => document.querySelectorAll('.eval-history-item').length === 1")
    posts_before = len(wire.posts)
    page.locator(".eval-history-item a, .eval-history-item button").first.click()
    wait_for(page, f"() => location.hash === '#/documents/evaluation/{scenario.run_id}'")
    wait_screen(page, "documents-evaluation")
    wait_for(page, "() => document.querySelectorAll('.eval-score').length === 5")
    rows = page.locator(".eval-results tbody tr")
    assert "33/100" in rows.nth(0).inner_text()
    assert "non évalué (sortie du juge invalide)" in rows.nth(1).inner_text()
    assert len(wire.posts) == posts_before  # rouvrir ne lance rien

    # 7. Le tout sans recharger la page.
    assert_never_reloaded(page)
