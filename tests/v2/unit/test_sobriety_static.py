"""Écran Sobriété (stories 5.1 et 5.2) : règles de structure du front, sans navigateur. Les parcours
(santé en direct, GPU, session carbone, onglet masqué, panneaux, historique, remise à zéro, axe)
vivent dans `e2e/test_sobriety.py` et `e2e/test_sobriety_history.py`."""

from __future__ import annotations

import re

from .static_files import STATIC, catalog, read

CATALOG = catalog()
LIVE_FILES = ("sobriety", "sobriety-health", "sobriety-carbon", "sobriety-details")  # story 5.1
FILES = (*LIVE_FILES, "sobriety-history", "sobriety-reset")  # + story 5.2
SCREEN = "\n".join(read(f"screens/{name}.js") for name in FILES)
CODE = "\n".join(line for line in SCREEN.splitlines() if not line.lstrip().startswith("//"))
NBSP = "\N{NO-BREAK SPACE}"


def flatten(node: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for name, value in node.items():
        path = f"{prefix}{name}"
        keys |= flatten(value, f"{path}.") if isinstance(value, dict) else {path}
    return keys


TEXTS = flatten(CATALOG["sobriety"], "sobriety.")


def test_every_text_the_screen_asks_for_exists_and_every_text_is_used():
    used = set(re.findall(r"""\bt\(\s*["'](sobriety\.[\w.]+)["']""", CODE))
    for base in re.findall(r"""\bplural\(\s*["'](sobriety\.[\w.]+)["']""", CODE):
        used |= {f"{base}_one", f"{base}_other"}
    used |= {key for key in TEXTS if key.startswith("sobriety.carbon.modules.")}  # par module
    used |= {f"sobriety.method.{k}" for k in ("local", "cloud", "throughput", "unmeasurable")}
    used |= {"sobriety.method.no_threshold"}  # la liste du panneau de méthode, bouclée
    # Segments de période et colonnes du tableau de l'historique : clés construites.
    used |= {
        key
        for key in TEXTS
        if key.startswith(("sobriety.history.window_", "sobriety.history.col_"))
    }
    assert used <= TEXTS, sorted(used - TEXTS)
    assert used >= TEXTS, sorted(TEXTS - used)


def test_plural_texts_come_in_pairs():
    for base in {key.rsplit("_", 1)[0] for key in TEXTS if key.endswith(("_one", "_other"))}:
        assert {f"{base}_one", f"{base}_other"} <= TEXTS, base


def test_texts_keep_a_no_break_space_before_double_punctuation_and_inside_guillemets():
    for key in TEXTS:
        text = CATALOG
        for part in key.split("."):
            text = text[part]
        assert not re.search(r" [:;!?»]|« ", text), (key, text)


def test_the_screen_calls_the_api_only_from_the_folded_panels_the_history_and_the_reset():
    for name in ("sobriety", "sobriety-health", "sobriety-carbon"):
        assert "api." not in read(f"screens/{name}.js").replace("// ", ""), name
    details = read("screens/sobriety-details.js")
    assert details.count("await shellReady()") == 2  # identité et méthode : AD-15
    assert "api.systemIdentity()" in details and "api.carbonMethod()" in details


def test_the_history_reads_after_shell_ready_and_the_reset_is_a_click():
    history = read("screens/sobriety-history.js")
    assert history.count("await shellReady()") == 1 and "api.carbonHistory(" in history
    assert history.index("await shellReady()") < history.index("api.carbonHistory(")
    reset = read("screens/sobriety-reset.js")
    assert "api.resetCarbonSession()" in reset
    assert len(re.findall(r"api\.\w+\(", reset)) == 1  # un seul appel, parti d'un clic
    assert 'addEventListener("click"' in reset


def test_the_reset_has_no_confirmation_dialog_and_never_deletes_anything():
    # La session close reste dans l'historique (AD-13) : rien à confirmer (EXPERIENCE.md).
    assert "wl-confirm-dialog" not in read("screens/sobriety-reset.js")
    assert 'method: "DELETE"' not in read("core/api/system.js")


def test_the_history_holds_no_calculation_of_a_measure():
    history = read("screens/sobriety-history.js")
    code = "\n".join(line for line in history.splitlines() if not line.lstrip().startswith("//"))
    # AD-20 : les totaux viennent du serveur ; l'écran trie, met en forme et trace.
    assert not re.search(r"\.reduce\(|Math\.(max|min|sum)\(|total_mg\s*[-+*/]|\+=", code)
    assert 'unit: "mg"' in code  # une seule unité pour le graphique et le tableau


def test_the_front_holds_no_car_factor_nor_any_calculation_of_a_measure():
    # D-38 : facteur, source, date et distance viennent du serveur (AD-20).
    assert not re.search(r"g_per_km\s*[*/]|[*/]\s*\w*g_per_km|\b(111|142)\b", CODE)
    assert "total_mg /" not in CODE and "total_mg *" not in CODE
    # La mémoire disponible est celle du serveur, pas une soustraction faite à l'écran.
    assert "total_gb - " not in CODE and "used_gb - " not in CODE
    # Aucun appel d'API ne fabrique de mesure : les formats seuls (`core/format.js`).
    assert "Math.round(gpu.temperature_c)" in CODE  # arrondi d'affichage seulement


def test_the_screen_never_writes_html_and_has_no_polite_live_region_for_the_two_second_updates():
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", CODE)
    lines = [line for name in LIVE_FILES for line in read(f"screens/{name}.js").splitlines()]
    live = "\n".join(line for line in lines if not line.lstrip().startswith("//"))
    assert "aria-live" not in live and '"status"' not in live
    # Seule la fin de la remise à zéro est annoncée, en `polite`.
    reset = read("screens/sobriety-reset.js")
    assert reset.count('"status"') == 1 and "aria-live" not in reset


def test_the_screen_is_registered_as_available_and_its_texts_and_stylesheet_are_loaded():
    registry = read("core/routes/sobriety.js")
    assert re.search(
        r'id: "sobriety",\s*path: "/sobriete",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./\.\./screens/sobriety\.js"\)',
        registry,
    )
    assert '"sobriety",' in read("core/i18n.js")
    assert '<link rel="stylesheet" href="/static/sobriety.css">' in read("index.html")
    assert (STATIC / "i18n" / "fr" / "sobriety.json").is_file()


def test_the_stylesheet_has_no_colour_of_its_own_and_none_by_co2_threshold():
    css = re.sub(r"/\*.*?\*/", "", read("sobriety.css"), flags=re.DOTALL)  # hors commentaires
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\b(rgb|hsl)a?\(", css)
    assert not re.search(r"threshold|level|seuil|danger|warning", css)  # aucune couleur par seuil


def test_the_front_gets_the_gpu_from_the_stream_and_the_store_keeps_it():
    assert "gpu: data.gpu ?? null" in read("core/system.js")
    assert "gpu: null" in read("core/store.js")


def test_the_files_stay_under_the_size_budget():
    for name in FILES:
        assert len(read(f"screens/{name}.js").splitlines()) <= 600, name
    assert len(read("sobriety.css").splitlines()) <= 600
