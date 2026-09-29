"""
Arène des modèles, dans l'app réelle avec de petits modèles Ollama : Chat libre, Banc
d'essai, Arène (2 modèles et un juge), Gestion des modèles en lecture seule.

Constats couverts : F4 et CAP-4 (débit selon D3 : même consigne à froid puis à chaud, le premier
pas plus de 15 % sous le second, sur assez de tokens, chargement à part), U20 (« Chargement du modèle en mémoire… »), D1/U12 (badge Local, modèles
locaux seuls), F10 et CAP-5 (défauts locaux, juge local), F13 (Arène désactivée sous
2 modèles), U17 (matrice avec légende de taille, tableau), U19 (avertissement de juge faible),
F3 pour le chemin nominal (aucune trace).
"""

import re

import pytest

from src.app.modules import ARENA
from src.app.states import INTERRUPTED_MESSAGE
from src.app.tabs.inference.arena import MIN_MODELS_CAPTION
from src.app.tabs.inference.lab import USE_CASES
from tests.e2e import helpers as h
from tests.e2e.ollama_api import ensure_cold, normalize_tag, ollama_get

pytestmark = pytest.mark.e2e

CHAT_PLACEHOLDER = "Écrivez votre message"
# Baisse tolérée du débit du premier passage (modèle chargé à froid) par rapport au suivant.
# Seule une baisse trahit un chargement compté dans le débit : un passage à froid plus
# rapide vient du GPU (plafond de puissance variable d'un portable, 80 à 95 W), pas de l'app.
THROUGHPUT_TOLERANCE = 0.15
# Tokens générés au minimum pour que le débit mesuré soit comparable.
MIN_OUTPUT_TOKENS = 30
# Même consigne pour les deux passages du banc d'essai : une réponse de plusieurs phrases.
LAB_SCENARIO = "Raisonnement pas à pas"
LAB_PROMPT = (
    "Explique en cinq phrases complètes ce qu'est l'inférence locale d'un modèle de langage "
    "et pourquoi elle protège les données."
)


def _footers(page):
    """Légendes de métadonnées sous les réponses du chat (badge, CO₂, débit, durées)."""
    return (
        h.main(page)
        .locator('[data-testid="stChatMessage"] [data-testid="stCaptionContainer"]')
        .filter(has_text="tokens/s")
    )


def _open_arena(page, app, tab: str | None = None):
    h.goto(page, app.base_url, ARENA.url_path)
    if tab:
        h.click_tab(page, tab)
    return h.visible_panel(page)


def expected_weak_judge(tag: str, ollama_models: dict) -> bool:
    """Le juge `tag` est-il « peu fiable » (< ~4B actifs ou taille inconnue) selon la règle
    de l'app (src/core/model_defaults.py), avec les mêmes catalogues ?"""
    from src.core.model_defaults import describe_model, load_versioned_catalog
    from src.core.models_db import MODELS_DB

    entry = next(m for t, m in ollama_models.items() if normalize_tag(t) == normalize_tag(tag))
    return describe_model(entry, 1e6, False, load_versioned_catalog(), MODELS_DB).weak_judge


def available_memory_gb() -> float:
    """Mémoire disponible selon la règle de l'app (`src.app.ui.available_memory_gb`) : mémoire
    libre plus celle des modèles déjà chargés dans Ollama."""
    from src.core.llm_provider import LLMProvider
    from src.core.resource_manager import ResourceManager

    return ResourceManager.get_available_ram_gb() + LLMProvider.loaded_models_ram_gb()


def expected_default_judge(ollama_models: dict, available_gb: float) -> str | None:
    """Juge local par défaut selon la règle de l'app (`choose_judge`, cloud non autorisé),
    avec les mêmes catalogues, les modèles installés et la mémoire `available_gb` : d'après
    le benchmark de ce poste (story 15), sinon d'après la mémoire. None sans modèle local."""
    from src.core.benchmark_results import load_machine_benchmark
    from src.core.model_defaults import choose_judge, is_remote_tag, rank_models

    local = [m for m in ollama_models.values() if not is_remote_tag(m)]
    # La mémoire disponible intervient : l'app écarte les modèles qui n'y tiennent pas.
    choice = choose_judge(
        rank_models(local, available_gb), load_machine_benchmark(), allow_cloud=False
    ).choice
    return choice.tag if choice else None


def test_chat_cold_start_load_and_badge(page, app, require_models, generation_timeout_ms):
    """Premier message à froid (vérifié par /api/ps) : chargement annoncé puis affiché à part
    du débit, badge Local, CO₂, réponse juste, formats fr-FR."""
    (tag,) = require_models("chat")
    ensure_cold(tag)
    panel = _open_arena(page, app)
    selectbox = panel.locator('[data-testid="stSelectbox"]').first

    options = h.first_options(page, selectbox)
    assert options and all(o.endswith("· Local") for o in options), options
    label = h.pick_model(page, selectbox, tag)
    assert label.endswith("· Local")

    h.chat_send(
        page, CHAT_PLACEHOLDER, "Quelle est la capitale de la France ? Réponds en une phrase."
    )
    h.wait_text(h.main(page), "Chargement du modèle en mémoire", timeout_ms=60_000)
    h.wait_count(page, _footers(page), 1, generation_timeout_ms, "Premier message")
    footer = h.flat(_footers(page).nth(0).inner_text())
    answer = h.flat(h.main(page).locator('[data-testid="stChatMessage"]').nth(1).inner_text())
    assert "Paris" in answer, answer
    for part in ("Local", "tokens/s", "Chargement", "Durée totale", "CO₂"):
        assert part in footer, f"« {part} » absent de « {footer} »"
    # Formats fr-FR : virgule décimale (U10).
    assert re.search(r"\d,\d\s*tokens/s", footer), footer
    session = h.flat(panel.get_by_text(re.compile(r"^Session :")).first.inner_text())
    assert h.parse_co2_grams(session) > 0
    assert h.exceptions(page) == []


def _interrupted(page) -> bool:
    """La page affiche « Réponse interrompue… » (flux Ollama fermé sans fragment final)."""
    return any(INTERRUPTED_MESSAGE in e for e in h.ui_errors(page))


def _lab_run(page, panel, timeout_ms: int, retry_cold: str | None = None) -> dict[str, str]:
    """Lance le banc d'essai et attend des métriques nouvelles ; renvoie {libellé: valeur}.

    Ollama ferme parfois le flux sans fragment final (« Réponse interrompue ») : le passage
    est relancé une fois. `retry_cold` (tag) : passage à froid, le modèle est d'abord
    redéchargé (`ensure_cold`) pour que la relance mesure encore un vrai chargement."""
    metrics = panel.locator('[data-testid="stMetric"]')
    for attempt in range(2):
        before = metrics.all_inner_texts()
        panel.get_by_role("button", name="Lancer le test").click()
        if attempt:
            # L'alerte du passage interrompu reste affichée jusqu'au rerun : l'attendre, sinon
            # elle passerait pour une nouvelle interruption.
            assert h.wait_rerun_started(page), "relance du Banc d'essai non démarrée"
        h.settle_after_action(
            page,
            timeout_ms,
            until=lambda before=before: _interrupted(page)
            or (metrics.count() >= 4 and metrics.all_inner_texts() != before),
        )
        if attempt == 0 and _interrupted(page):
            if retry_cold:
                ensure_cold(retry_cold)
            continue
        break
    assert h.ui_errors(page) == [], h.ui_errors(page)
    labels = [h.flat(t) for t in panel.locator('[data-testid="stMetricLabel"]').all_inner_texts()]
    return {label: h.metric_value(panel, label) for label in labels}


def test_lab_throughput_excludes_loading(page, app, require_models, generation_timeout_ms):
    """Banc d'essai, même consigne deux fois, la première à froid (vérifié par /api/ps) :
    chargement affiché à part, débit du premier passage au moins à 85 % du second, chacun sur au
    moins MIN_OUTPUT_TOKENS tokens (F4, D3, CAP-4)."""
    (tag,) = require_models("chat")
    panel = _open_arena(page, app, "Banc d'essai")
    selectboxes = panel.locator('[data-testid="stSelectbox"]')
    h.pick_model(page, selectboxes.first, tag)
    # Le scénario par défaut (« Classification (JSON) ») impose une réponse JSON d'une
    # vingtaine de tokens : scénario en prose pour mesurer le débit sur une vraie réponse.
    # Sa question par défaut n'apparaît qu'au rendu du serveur : l'attendre avant de saisir,
    # sinon ce rendu écraserait la saisie.
    user_box = panel.get_by_label("Entrée utilisateur")
    h.select_option(page, selectboxes.nth(1), LAB_SCENARIO)
    h.settle_after_action(
        page, until=lambda: user_box.input_value() == USE_CASES[LAB_SCENARIO]["user"]
    )
    user_box.fill(LAB_PROMPT)
    ensure_cold(tag)

    cold = _lab_run(page, panel, generation_timeout_ms, retry_cold=tag)
    assert {"Débit", "CO₂", "Chargement", "Durée totale", "Tokens générés"} <= set(cold), cold
    assert panel.get_by_role("heading", name="Réponse", exact=True).count() == 1
    assert "Local" in h.flat(panel.inner_text())
    warm = _lab_run(page, panel, generation_timeout_ms)

    for run in (cold, warm):
        tokens = h.parse_number(run["Tokens générés"])
        assert tokens >= MIN_OUTPUT_TOKENS, f"{tokens} tokens : mesure trop courte ({run})"
    cold_tps, warm_tps = h.parse_throughput(cold["Débit"]), h.parse_throughput(warm["Débit"])
    assert warm_tps > 0
    assert cold_tps >= (1 - THROUGHPUT_TOLERANCE) * warm_tps, (
        f"débit à froid {cold_tps} tokens/s contre {warm_tps} ensuite : le chargement est-il "
        f"compté dans le débit ? (chargement à froid : {cold['Chargement']})"
    )


def test_arena_two_local_models_with_judge(
    page, app, require_models, ollama_models, generation_timeout_ms
):
    """Arène : défauts locaux, lancement impossible sous 2 modèles, deux petits modèles
    notés par un juge local, verdict lisible (matrice avec légende de taille, tableau)."""
    chat, small, judge = require_models("chat", "small", "judge")
    # L'app mesure la mémoire disponible une fois, au premier affichage (entre ces deux
    # mesures) : le juge attendu est celui de l'une ou l'autre.
    memory_before = available_memory_gb()
    panel = _open_arena(page, app, "Arène")
    memory_after = available_memory_gb()
    multiselect = panel.locator('[data-testid="stMultiSelect"]').first
    launch = panel.get_by_role("button", name="Lancer la comparaison")

    preselected = h.multiselect_values(multiselect)
    assert all(v.endswith("· Local") for v in preselected), preselected
    assert launch.is_enabled() == (len(preselected) >= 2)

    # Vider la liste est immédiat dans le navigateur ; la légende et le bouton désactivé
    # viennent du rerun du serveur.
    h.multiselect_clear(page, multiselect)
    h.settle_after_action(page, until=panel.get_by_text(MIN_MODELS_CAPTION))
    assert launch.is_disabled()
    assert panel.get_by_text(MIN_MODELS_CAPTION).is_visible()
    for tag in (chat, small):
        h.add_model(page, multiselect, tag)
    assert len(h.multiselect_values(multiselect)) == 2
    h.settle_after_action(page, until=launch.is_enabled)

    panel.get_by_text("Réglages du juge").click()
    judge_box = panel.locator('[data-testid="stSelectbox"]').first
    judge_box.wait_for()
    # Clés cloud vides (APP_ENV) : le juge par défaut reste local : celui de la règle de
    # l'app (benchmark de ce poste, sinon mémoire), sans nom de modèle figé ici.
    default_judge = h.selected_value(judge_box)
    assert default_judge.endswith("· Local"), "juge par défaut non local"
    expected_judges = {
        expected_default_judge(ollama_models, memory) for memory in (memory_before, memory_after)
    } - {None}
    if expected_judges:
        from src.core.models_db import get_friendly_name_from_tag

        expected = set()
        for tag in expected_judges:
            name = get_friendly_name_from_tag(tag)
            expected |= {f"{name} · Local", f"{name} ({tag}) · Local"}
        assert default_judge in expected, (default_judge, expected, memory_before, memory_after)
    h.pick_model(page, judge_box, judge)
    # L'avertissement suit le rerun déclenché par le choix du juge (la valeur affichée, elle,
    # change avant) : attendre ce rerun, puis l'état attendu (qui peut être déjà vrai avant).
    weak = expected_weak_judge(judge, ollama_models)
    weak_warning = panel.locator('[data-testid="stAlertContentWarning"]').filter(
        has_text="Note peu fiable"
    )
    h.settle_after_action(page)
    h.wait_until(
        page,
        lambda: (weak_warning.count() > 0) == weak,
        what=f"avertissement « Note peu fiable » {'affiché' if weak else 'absent'}",
    )
    h.settle(page)
    warnings = [
        h.flat(t) for t in panel.locator('[data-testid="stAlertContentWarning"]').all_inner_texts()
    ]
    assert any("Note peu fiable" in w for w in warnings) == weak, warnings

    launch.click()
    h.wait_text(panel, re.compile(r"Comparaison (terminée|échouée)"), generation_timeout_ms)
    h.settle(page)
    text = h.flat(panel.inner_text())
    assert "Comparaison échouée" not in text, text[-1500:]
    assert panel.get_by_role("heading", name="Verdict", exact=True).count() == 1
    assert panel.locator('[data-testid="stDataFrame"]').count() >= 1
    assert panel.get_by_role("heading", name="Réponses des modèles").count() == 1
    if "Le juge n'a pu noter aucune réponse" not in text:
        assert re.search(r"\d+/100", h.metric_value(panel, "Note du juge"))
        chart = panel.locator('[data-testid="stPlotlyChart"]').first
        chart.wait_for(timeout=h.PAGE_TIMEOUT_MS)
        page.wait_for_function(
            "e => e.innerText.includes('taille du point')",
            arg=chart.element_handle(),
            timeout=h.PAGE_TIMEOUT_MS,
        )
        assert "Taille du point" in text
    # Une seule unité de CO₂ dans toute la comparaison.
    assert len(h.co2_units(h.flat(panel.inner_text()))) <= 1
    assert h.exceptions(page) == []


def _local_model_count(models: dict) -> int:
    from src.core.model_defaults import is_remote_tag

    return sum(1 for m in models.values() if not is_remote_tag(m))


def test_model_manager_is_read_only(page, app, ollama_models):
    """Gestion des modèles : liste des modèles installés, fenêtre d'ajout ouverte puis
    fermée sans rien installer ; la liste d'Ollama n'a pas changé."""
    before = set(ollama_models)
    panel = _open_arena(page, app, "Gestion des modèles")

    caption = h.flat(panel.get_by_text(re.compile(r"prêts? à l'emploi")).first.inner_text())
    assert int(h.parse_number(caption.split()[0])) == _local_model_count(ollama_models), caption
    if ollama_models:
        assert panel.locator('[data-testid="stDataFrame"]').count() == 1

    panel.get_by_role("button", name="Ajouter un modèle").click()
    dialog = page.get_by_role("dialog")
    h.settle_after_action(page, until=dialog)
    assert dialog.get_by_role("button", name="Ajouter le modèle").is_disabled()
    page.keyboard.press("Escape")
    h.settle_after_action(page, until=lambda: page.get_by_role("dialog").count() == 0)

    after = {m["model"] for m in ollama_get("/api/tags").get("models", [])}
    assert after == before
    assert h.ui_errors(page) == []
