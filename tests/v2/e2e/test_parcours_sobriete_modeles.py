"""Parcours « Sobriété et Modèles » de bout en bout (story 8.3), sans recharger la page.

Un seul chargement de page : l'écran Modèles (un modèle installé, un catalogue), un détour par la
Sobriété où la session carbone suit une réponse sans clic, le retour aux Modèles pour installer un
modèle du catalogue (téléchargement chiffré, ligne qui change de liste), puis la Sobriété qui garde
son total. La navigation se fait par la coquille, jamais par `page.goto`.

Doublures de l'écran Modèles : un `ThreadedOllama` (aucun vrai téléchargement) et les listes
`GET /api/models*` simulées dans le navigateur, comme `test_models_install.py` ; la réponse mesurée
de la Sobriété vient de la route de test (`POST /api/test/runs`). Aucune requête ne sort de 127.0.0.1
(fixture `context` et bilan de la suite).
"""

from __future__ import annotations

from ..pull_fake import GB, layer, manifest, success, verifying
from .parcours import assert_never_reloaded, mark_no_reload, open_module, wait_screen
from .test_models_install import (  # noqa: F401  (fixtures de module et aides de l'écran Modèles)
    catalog_row,
    install_button,
    models_server,
    ollama,
    open_models,
    wait_notice,
)
from .test_shell import wait_for
from .test_sobriety import wait_screen as wait_sobriety_text
from .test_topbar import LOCAL_CO2, NBSP, run_scripted


def installed_names(page) -> list[str]:
    """Le nom (première cellule) de chaque ligne de « Sur ce poste »."""
    rows = page.locator(".models-installed tbody tr")
    return [rows.nth(i).locator("th, td").first.inner_text().strip() for i in range(rows.count())]


def test_parcours_sobriete_puis_modeles_sans_recharger_la_page(page, models_server, ollama):
    open_models(page, models_server, ollama)  # remet le faux Ollama à zéro : un modèle installé
    ollama.loaded = ["here:2b"]  # et chargé en mémoire, ce que la Sobriété doit dire
    mark_no_reload(page)

    # 1. Modèles : un modèle installé, trois dans le catalogue, une seule installation à la fois.
    assert installed_names(page) == ["here:2b"]
    assert page.locator(".models-catalog tbody tr").count() == 3

    # 2. Sobriété : les quatre cartes de santé se remplissent sans clic ; Ollama est joignable et dit
    # son modèle chargé ; la session carbone est vide, sans zéro affiché.
    open_module(page, "Sobriété")
    wait_screen(page, "sobriety")
    wait_for(
        page,
        '() => document.querySelector(\'[data-screen="sobriety"] [data-card="cpu"]\')'
        "?.getAttribute('aria-busy') === 'false'",
    )
    assert page.title() == "Sobriété et matériel · WaveLocalAI"
    wait_sobriety_text(page, "Aucune réponse mesurée dans cette session")
    wait_sobriety_text(page, "1 modèle chargé")

    # 3. Une réponse mesurée arrive pendant qu'on regarde l'écran : le total suit, sans clic.
    run_scripted(page, models_server, kind="chat", origin="local", co2=LOCAL_CO2)
    wait_sobriety_text(page, f"1,8{NBSP}mg")
    wait_sobriety_text(page, f"Par module{NBSP}: Chat libre 1,8{NBSP}mg")

    # 4. Retour aux Modèles par la navigation : l'installation d'un modèle du catalogue.
    open_module(page, "Modèles")
    wait_screen(page, "models")
    wait_for(page, "() => document.querySelectorAll('.models-catalog tbody tr').length === 3")
    ollama.scripts.append(
        [
            manifest(),
            layer("sha256:aaaa1111bbbb", GB, GB // 2),
            layer("sha256:aaaa1111bbbb", GB, GB),
            verifying(),
            success(),
        ]
    )
    install_button(page, "small:1b").click()
    wait_notice(page, "Petit 1B installé.")
    wait_for(page, "() => document.querySelectorAll('.models-installed tbody tr').length === 2")
    names = " ".join(installed_names(page))
    assert "here:2b" in names and "Petit 1B" in names
    assert catalog_row(page, "small:1b").count() == 0  # la ligne a changé de liste
    assert ollama.pull_requests == ["small:1b"]

    # 5. La Sobriété a gardé la session : le total est toujours là, rien n'est reparti de zéro.
    open_module(page, "Sobriété")
    wait_screen(page, "sobriety")
    wait_sobriety_text(page, f"1,8{NBSP}mg")

    # 6. Le tout sans recharger la page.
    assert_never_reloaded(page)
