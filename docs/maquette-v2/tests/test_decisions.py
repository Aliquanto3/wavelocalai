"""Décisions d'Anaël (README §6) : un contrôle de comportement par décision appliquée, en plus des
passes axe des scénarios (qui ne vérifient pas le comportement)."""

from __future__ import annotations

from conftest import open_route, wait_for

VISIBLE = (
    "(el) => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden'"
)


def scenario(page, scenario_id: str) -> None:
    page.evaluate("(id) => window.__maquette.runScenario(id)", scenario_id)
    page.wait_for_timeout(150)


def visible(page, selector: str) -> bool:
    return page.evaluate(
        f"(s) => ({VISIBLE})(document.querySelector('section.screen:not([hidden]) ' + s))", selector
    )


def test_3_exports_deux_boutons_puis_menu_sous_768(page, base_url):
    open_route(page, base_url, "/arene/chat")
    scenario(page, "reponse-locale")
    assert page.locator("section.screen:not([hidden]) .wl-export-wide button:visible").count() == 2
    page.set_viewport_size({"width": 600, "height": 900})
    assert not visible(page, ".wl-export-wide")
    toggle = page.locator("section.screen:not([hidden]) .wl-export-narrow > button")
    toggle.click()
    assert toggle.get_attribute("aria-expanded") == "true"
    assert page.locator("section.screen:not([hidden]) .wl-export-choice:visible").count() == 2
    page.keyboard.press("Escape")
    assert toggle.get_attribute("aria-expanded") == "false"


def test_5_10_accueil_noms_courts_et_pourcentage(page, base_url):
    open_route(page, base_url, "/")
    wait_for(page, "() => document.documentElement.dataset.ready === 'true'")
    names = page.locator(".home-module-name").all_inner_texts()
    assert "Documents" in names and "Agents" in names
    assert "Assistant documentaire" in page.locator(".home-module-long").all_inner_texts()
    wait_for(
        page,
        "() => /Part de .*%/.test(document.querySelectorAll('.home-module-summary')[4]?.textContent ?? '')",
    )


def test_6_interrupteurs_en_bascule(page, base_url):
    open_route(page, base_url, "/arene/banc")
    switches = page.locator("section.screen:not([hidden]) input.wl-switch-input[role=switch]")
    assert switches.count() == 2
    assert page.locator("input[name=projection].wl-switch-input[role=switch]").count() == 1


def test_12_creativite_fournie_avec_le_modele(page, base_url):
    open_route(page, base_url, "/arene/chat")
    wait_for(
        page,
        "() => document.querySelector('.chat-creativity-default')?.textContent.includes('Qwen 3.5 2B')",
    )
    assert page.locator(".chat-slider").input_value() == "0.6"


def test_15_quatre_colonnes_repliees_sur_4_lignes(page, base_url):
    open_route(page, base_url, "/arene/comparer/run-arene-demo")
    wait_for(page, "() => document.querySelector('.ar-lanes')?.dataset.count === '4'")
    assert (
        page.evaluate(
            "() => getComputedStyle(document.querySelector('.ar-lanes')).gridTemplateColumns.split(' ').length"
        )
        == 4
    )


def test_18_consigne_repliee(page, base_url):
    open_route(page, base_url, "/arene/banc")
    details = page.locator("section.screen:not([hidden]) details.bc-instruction")
    assert details.count() == 1 and details.get_attribute("open") is None
    assert details.locator(".bc-instruction-body").text_content()


def test_19_comparer_ces_modeles_preselectionne_l_arene(page, base_url):
    open_route(page, base_url, "/arene/references")
    scenario(page, "comparer-ces-modeles")
    wait_for(page, "() => location.hash === '#/arene/comparer'")
    wait_for(
        page,
        "() => (document.querySelector('section.screen[data-screen=arene]:not([hidden]) wl-model-picker')?.values ?? []).length >= 2",
    )


def test_21_22_passage_surligne_et_panneau_fixe(page, base_url):
    open_route(page, base_url, "/documents")
    scenario(page, "ouvrir-une-source")
    wait_for(
        page, "() => !!document.querySelector('section.screen:not([hidden]) mark.wl-source-mark')"
    )
    page.locator("section.screen:not([hidden]) .wl-sources-summary").click()
    assert page.evaluate(
        "() => document.querySelector('section.screen:not([hidden]) details.wl-sources').open"
    )


def test_24_25_26_base_documentaire(page, base_url):
    open_route(page, base_url, "/documents/base")
    scenario(page, "suppression-confirmation")
    assert page.evaluate("() => !!document.querySelector('wl-confirm-dialog dialog[open]')")
    page.evaluate(
        "() => document.querySelector('wl-confirm-dialog .wl-dialog-actions .btn').click()"
    )
    scenario(page, "import-en-cours")
    assert page.locator("section.screen:not([hidden]) .docs-import-cancel").count() == 1
    assert (
        page.locator("section.screen:not([hidden]) .docs-import .docs-import-cancel").count() == 0
    )
    scenario(page, "import-avec-echec")
    wait_for(
        page,
        "() => [...document.querySelectorAll('section.screen:not([hidden]) .docs-row')].some((row) => row.textContent.includes('Échec'))",
    )


def test_31_pied_reduit_de_l_agent(page, base_url):
    open_route(page, base_url, "/agents/seul")
    scenario(page, "tache-terminee")
    labels = page.locator("section.screen:not([hidden]) .wl-msg-foot wl-metric").evaluate_all(
        "(nodes) => nodes.map((node) => node.getAttribute('label'))"
    )
    assert len(labels) == 3, labels


def test_35_36_configurer_non_modal_cinq_agents(page, base_url):
    open_route(page, base_url, "/agents/equipe")
    scenario(page, "configurer-cinq-agents")
    assert not page.evaluate("() => document.querySelector('.crew-drawer').matches(':modal')")
    assert visible(page, ".crew-graph svg")
    assert page.locator(".crew-add-agent").is_disabled()


def test_38_equivalence_dans_la_methode(page, base_url):
    open_route(page, base_url, "/sobriete")
    scenario(page, "methode-equivalence")
    assert "source" in page.locator(".sob-equivalence").inner_text()


def test_39_historique_en_tableau_sous_640(page, base_url):
    page.set_viewport_size({"width": 600, "height": 900})
    open_route(page, base_url, "/sobriete")
    wait_for(
        page,
        "() => !!document.querySelector('section.screen:not([hidden]) .sob-history-body table')",
    )


def test_41_42_43_modeles(page, base_url):
    open_route(page, base_url, "/modeles")
    scenario(page, "supprimer-confirmation")
    assert "par défaut" in page.locator("wl-confirm-dialog dialog[open]").inner_text()
    page.evaluate(
        "() => document.querySelector('wl-confirm-dialog .wl-dialog-actions .btn').click()"
    )
    assert page.locator("text=Installer quand même").count() >= 1
    page.set_viewport_size({"width": 800, "height": 900})
    assert not visible(page, ".mod-installed .mod-col-secondary")
    page.locator('[data-fid="secondary-toggle"]').click()
    assert visible(page, ".mod-installed .mod-col-secondary")
