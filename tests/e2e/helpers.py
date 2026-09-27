"""
Pilotage de l'app Streamlit dans Playwright, pour les tests e2e.

Repris des scripts d'audit (`docs/audits/frontend-2026-09/poste-rtx3060/playwright/common.py`
et `pro-elitebook-x360/e2e/helpers.js`) : attendre la fin du rerun Streamlit, taper pour
filtrer les listes virtualisées, relever exceptions et alertes. Aucun import de Playwright
au chargement : la collecte de la suite par défaut n'en dépend pas.
"""

import contextlib
import re
import time

# Délais (ms). Une génération réelle sur un petit modèle, premier chargement compris, tient
# largement dans GENERATION_TIMEOUT_MS ; WAVELOCALAI_E2E_TIMEOUT_S le change (conftest.py).
PAGE_TIMEOUT_MS = 120_000
GENERATION_TIMEOUT_MS = 300_000

# Onglet « running » : Streamlit expose l'état du script sur la racine de l'app.
_APP = '[data-testid="stApp"]'
_IDLE_JS = """() => {
    const app = document.querySelector('[data-testid="stApp"]');
    return !!app
        && app.getAttribute('data-test-connection-state') === 'CONNECTED'
        && app.getAttribute('data-test-script-state') === 'notRunning'
        && !document.querySelector('[data-stale="true"]');
}"""
_RUNNING_JS = """() => {
    const app = document.querySelector('[data-testid="stApp"]');
    return !!app && app.getAttribute('data-test-script-state') !== 'notRunning';
}"""

# Pictogrammes emoji (même périmètre que tests/app/test_theme.py) : plans pictographiques,
# symboles divers, dingbats, sélecteur de variante emoji.
EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff\ufe0f\u203c\u2049\u2139]"
)
# Seul emoji toléré dans un titre (accueil de l'agent, EXPERIENCE.md).
ALLOWED_EMOJI_HEADINGS = {"👋 Bonjour !"}

# Contrastes non imputables au thème (couleurs natives de Streamlit, texte de composants
# inactifs), relevés par test_accessibility.py et listés en fin de session (conftest.py) :
# jamais masqués.
AXE_NATIVE_FINDINGS: list[dict] = []


# ---------------------------------------------------------------------------
# Attente
# ---------------------------------------------------------------------------


def settle(page, timeout_ms: int = PAGE_TIMEOUT_MS) -> None:
    """Attend que le script Streamlit ait fini de tourner et qu'aucun élément ne soit périmé."""
    page.wait_for_selector(_APP, timeout=timeout_ms)
    page.wait_for_function(_IDLE_JS, timeout=timeout_ms, polling=250)
    # Le rendu des derniers éléments suit le message de fin de script.
    page.wait_for_timeout(300)


def wait_until(page, condition, timeout_ms: int = PAGE_TIMEOUT_MS, what: str = "") -> None:
    """Attend `condition` : un locator (visible) ou une fonction sans argument qui renvoie
    vrai."""
    if hasattr(condition, "wait_for"):
        condition.wait_for(state="visible", timeout=timeout_ms)
        return
    deadline = time.monotonic() + timeout_ms / 1000
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError(f"État attendu non atteint après {timeout_ms / 1000:.0f} s {what}")
        page.wait_for_timeout(200)


def settle_after_action(page, timeout_ms: int = PAGE_TIMEOUT_MS, until=None) -> None:
    """Après un clic ou une saisie : attend le rerun qu'elle déclenche, puis sa fin.

    `until` (locator à voir, ou fonction qui renvoie vrai) désigne l'état que l'action doit
    produire : à donner dès que le test lit le DOM juste après, car un rerun qui démarre tard
    échapperait sinon à l'attente. Sans `until`, le rerun est attendu 1,5 s au plus."""
    if until is not None:
        wait_until(page, until, timeout_ms)
    else:
        # Pas de rerun dans ce délai : l'action n'en déclenche pas.
        with contextlib.suppress(Exception):
            page.wait_for_function(_RUNNING_JS, timeout=1_500, polling=100)
    settle(page, timeout_ms)


def goto(page, base_url: str, path: str = "", timeout_ms: int = PAGE_TIMEOUT_MS) -> None:
    """Ouvre une page (nouvelle session Streamlit) et attend son premier rendu complet."""
    page.goto(f"{base_url}/{path}", timeout=timeout_ms)
    # Premier rendu : le titre du module (h1) dans la zone principale, puis fin du script.
    main(page).locator("h1").first.wait_for(timeout=timeout_ms)
    settle(page, timeout_ms)


def nav(page, title: str, timeout_ms: int = PAGE_TIMEOUT_MS) -> None:
    """Change de page par le menu : la session (st.session_state) est conservée."""
    sidebar(page).locator('[data-testid="stSidebarNav"] a', has_text=title).first.click()
    settle_after_action(page, timeout_ms)
    main(page).locator("h1", has_text=title).first.wait_for(timeout=timeout_ms)


def wait_text(scope, text, timeout_ms: int = GENERATION_TIMEOUT_MS):
    """Attend qu'un texte (chaîne ou regex) soit visible dans `scope` ; renvoie le locator."""
    locator = scope.get_by_text(text).first
    locator.wait_for(state="visible", timeout=timeout_ms)
    return locator


# ---------------------------------------------------------------------------
# Zones et relevés
# ---------------------------------------------------------------------------


def main(page):
    """Zone principale de la page (hors barre latérale et champ de discussion en pied)."""
    return page.locator('[data-testid="stMainBlockContainer"]')


def sidebar(page):
    return page.locator('[data-testid="stSidebar"]')


def visible_panel(page):
    """Panneau de l'onglet affiché."""
    return page.locator('[role="tabpanel"]:visible').first


def flat(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def ui_errors(page) -> list[str]:
    """Exceptions Python et `st.error` visibles, texte aplati."""
    texts = page.locator('[data-testid="stException"], [data-testid="stAlertContentError"]')
    return [t for t in (flat(x) for x in texts.all_inner_texts()) if t]


def exceptions(page) -> list[str]:
    """Traces Python affichées (jamais acceptables)."""
    return [flat(x) for x in page.locator('[data-testid="stException"]').all_inner_texts()]


def click_tab(page, name: str) -> None:
    tab = page.get_by_role("tab", name=name)
    tab.click()
    settle_after_action(page, until=lambda: tab.get_attribute("aria-selected") == "true")


def metric_value(scope, label: str, timeout_ms: int = PAGE_TIMEOUT_MS) -> str:
    """Valeur d'un `st.metric` repéré par son libellé exact."""
    metrics = scope.locator('[data-testid="stMetric"]')
    metrics.first.wait_for(timeout=timeout_ms)
    labels = []
    for i in range(metrics.count()):
        metric = metrics.nth(i)
        name = flat(metric.locator('[data-testid="stMetricLabel"]').inner_text())
        if name == label:
            return flat(metric.locator('[data-testid="stMetricValue"]').inner_text())
        labels.append(name)
    raise AssertionError(f"Métrique « {label} » absente ; métriques affichées : {labels}")


def headings(page, levels: str = "h1, h2, h3") -> list[str]:
    return [flat(t) for t in main(page).locator(levels).all_inner_texts()]


# ---------------------------------------------------------------------------
# Sélecteurs (listes virtualisées : taper pour filtrer)
# ---------------------------------------------------------------------------


def _options(page) -> list[str]:
    options = page.locator('[role="option"]')
    return [flat(t) for t in options.all_inner_texts()]


def _option_name(label: str) -> str:
    """Nom d'une option de modèle : « Nom · Local · outils vérifiés » → « Nom »."""
    return label.split(" · ", 1)[0].strip()


def match_options(names: list[str], text: str, tag: str | None = None) -> list[int]:
    """Options qui désignent `text` sans ambiguïté.

    Avec `tag` (sélecteur de modèles) : d'abord l'option dont le libellé porte le tag (deux
    modèles au même nom), sinon celles dont le nom est exactement `text`. Jamais une simple
    sous-chaîne : « Granite 4 » ne choisit pas « Granite 4 H Tiny ». Sans `tag` : le nom
    exact, sinon l'option unique qui contient `text`."""
    lowered = text.lower()
    if tag:
        by_tag = [i for i, n in enumerate(names) if f"({tag.lower()})" in n.lower()]
        if by_tag:
            return by_tag
    exact = [i for i, n in enumerate(names) if _option_name(n).lower() == lowered]
    if exact or tag:
        return exact
    return [i for i, n in enumerate(names) if lowered in n.lower()]


def _pick(page, text: str, tag: str | None) -> str:
    """Clique l'option désignée par `text` (et `tag`) ; échoue si elle est introuvable ou
    ambiguë."""
    deadline = time.monotonic() + 10
    names: list[str] = []
    while time.monotonic() < deadline:
        names = _options(page)
        hits = match_options(names, text, tag)
        if len(hits) > 1:
            page.keyboard.press("Escape")
            raise AssertionError(f"« {text} » ambigu parmi : {[names[i] for i in hits]}")
        if hits:
            page.locator('[role="option"]').nth(hits[0]).click()
            return names[hits[0]]
        page.wait_for_timeout(250)
    page.keyboard.press("Escape")
    raise AssertionError(f"Option « {text} » introuvable parmi : {names}")


def select_option(page, selectbox, text: str, tag: str | None = None) -> str:
    """Choisit dans un `st.selectbox` l'option désignée par `text` (voir `match_options`) ;
    renvoie son libellé."""
    selectbox.click()
    page.keyboard.type(text)
    label = _pick(page, text, tag)
    settle_after_action(page, until=lambda: selected_value(selectbox) == label)
    return label


def first_options(page, selectbox) -> list[str]:
    """Premières options affichées d'un `st.selectbox` (la liste est virtualisée)."""
    selectbox.click()
    page.locator('[role="option"]').first.wait_for(timeout=10_000)
    names = _options(page)
    page.keyboard.press("Escape")
    return names


def selected_value(selectbox) -> str:
    """Valeur affichée d'un `st.selectbox` (champ de la liste déroulante)."""
    return flat(selectbox.locator('input[role="combobox"]').first.input_value())


def multiselect_values(multiselect) -> list[str]:
    """Valeurs choisies d'un `st.multiselect` (une étiquette par valeur)."""
    tags = multiselect.locator("[data-tag]")
    return [flat(tags.nth(i).get_attribute("aria-label")) for i in range(tags.count())]


def multiselect_clear(page, multiselect) -> None:
    """Retire toutes les valeurs d'un `st.multiselect`."""
    clear = multiselect.get_by_role("button", name=re.compile("clear all", re.I))
    if clear.count():
        clear.first.click()
    else:
        for _ in range(50):
            if not multiselect.locator("[data-tag]").count():
                break
            multiselect.locator("[data-tag] button").first.click()
            page.wait_for_timeout(200)
        else:
            raise AssertionError("multiselect non vidé")
    page.keyboard.press("Escape")
    settle_after_action(page, until=lambda: not multiselect.locator("[data-tag]").count())


def multiselect_add(page, multiselect, text: str, tag: str | None = None) -> str:
    """Ajoute à un `st.multiselect` l'option désignée par `text` (voir `match_options`)."""
    multiselect.locator("input").click()
    page.keyboard.type(text)
    label = _pick(page, text, tag)
    page.keyboard.press("Escape")
    settle_after_action(page, until=lambda: label in multiselect_values(multiselect))
    return label


def chat_send(page, placeholder: str, text: str) -> None:
    box = page.get_by_placeholder(placeholder)
    box.fill(text)
    box.press("Enter")


# ---------------------------------------------------------------------------
# Nombres fr-FR (src/app/formatting.py)
# ---------------------------------------------------------------------------

_NUMBER = r"-?\d[\d\u202f\u00a0 ]*(?:,\d+)?"
_CO2_RE = re.compile(rf"({_NUMBER})\s*(mg|g|kg)CO₂")
_THROUGHPUT_RE = re.compile(rf"({_NUMBER})\s*tokens/s")
_CO2_UNIT_G = {"mg": 1e-3, "g": 1.0, "kg": 1e3}


def parse_number(text: str) -> float:
    """« 12 345,6 » (espaces fines ou insécables) → 12345.6."""
    cleaned = re.sub(r"[\s\u202f\u00a0]", "", text).replace(",", ".")
    return float(cleaned)


def parse_co2_grams(text: str) -> float:
    """Première masse de CO₂ d'un texte (« 12,3 mgCO₂ ») en grammes."""
    match = _CO2_RE.search(text)
    if not match:
        raise AssertionError(f"Aucune masse de CO₂ dans « {text} »")
    return parse_number(match.group(1)) * _CO2_UNIT_G[match.group(2)]


def co2_units(text: str) -> set[str]:
    return {m.group(2) for m in _CO2_RE.finditer(text)}


def parse_throughput(text: str) -> float:
    """Premier débit d'un texte (« 78,5 tokens/s ») en tokens/s."""
    match = _THROUGHPUT_RE.search(text)
    if not match:
        raise AssertionError(f"Aucun débit dans « {text} »")
    return parse_number(match.group(1))


def model_query(tag: str) -> tuple[str, str]:
    """(nom affiché, tag) d'un modèle : le sélecteur affiche « Nom · Local », complété par le
    tag si deux modèles portent le même nom. Taper le nom filtre la liste, le tag départage."""
    from src.core.models_db import get_friendly_name_from_tag

    return get_friendly_name_from_tag(tag), tag


def pick_model(page, selectbox, tag: str) -> str:
    """Choisit le modèle `tag` dans un sélecteur de modèles ; renvoie son libellé."""
    friendly, tag = model_query(tag)
    return select_option(page, selectbox, friendly, tag=tag)


def add_model(page, multiselect, tag: str) -> str:
    """Ajoute le modèle `tag` à un `st.multiselect` de modèles ; renvoie son libellé."""
    friendly, tag = model_query(tag)
    return multiselect_add(page, multiselect, friendly, tag=tag)


def wait_count(page, locator, count: int, timeout_ms: int, what: str) -> None:
    """Attend au moins `count` éléments ; échoue tout de suite si une trace ou une erreur
    s'affiche, avec son texte."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if locator.count() >= count:
            settle(page)
            return
        errors = ui_errors(page)
        if errors:
            raise AssertionError(f"{what} : erreur affichée au lieu du résultat : {errors}")
        page.wait_for_timeout(500)
    raise AssertionError(f"{what} : rien après {timeout_ms / 1000:.0f} s")
