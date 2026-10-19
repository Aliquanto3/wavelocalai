"""Écran Évaluation de la qualité (story 7.3) : règles de structure, de textes et de style, sans
navigateur. Les parcours (formulaire, étapes, tableau, détail, matrice, réouverture, partiel, axe)
vivent dans `e2e/test_evaluation.py`."""

from __future__ import annotations

import re

from .static_files import STATIC, catalog, read_static

CATALOG = catalog()
SCREEN_FILES = (
    "screens/documents-eval.js",
    "screens/eval-model.js",
    "screens/eval-form.js",
    "screens/eval-steps.js",
    "screens/eval-results.js",
    "screens/eval-detail.js",
    "screens/eval-history.js",
    "screens/eval-reopen.js",
)
NBSP = "\N{NO-BREAK SPACE}"


def source(name: str) -> str:
    return read_static(name)


def code(name: str) -> str:
    return "\n".join(
        line for line in source(name).splitlines() if not line.lstrip().startswith("//")
    )


def lookup(key: str):
    value = CATALOG
    for part in key.split("."):
        value = value[part]
    return value


def leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, f"{path}.{key}" if path else key)
    else:
        yield path, value


def test_the_screen_is_registered_as_available_with_its_path_parameter():
    registry = source("core/routes/documents.js")
    assert re.search(
        r'id: "documents-evaluation",\s*path: "/documents/evaluation",\s*param: "run_id",\s*'
        r'status: "available",\s*load: \(\) => import\("\.\./\.\./screens/documents-eval\.js"\)',
        registry,
    )
    assert "documents-evaluation" in lookup("screens")


def test_the_texts_have_their_own_file_declared_once_with_one_top_level_key():
    assert re.search(r'"evaluation",\n\];', source("core/i18n.js"))
    assert list(CATALOG["evaluation"]) and (STATIC / "i18n/fr/evaluation.json").exists()


def test_every_text_key_the_screen_names_exists_and_plural_bases_have_both_forms():
    used: set[str] = set()
    plurals: set[str] = set()
    for name in SCREEN_FILES:
        text = source(name)
        used |= set(re.findall(r"""\bt\(\s*["'](evaluation\.[\w.]+)["']""", text))
        plurals |= set(re.findall(r"""\bplural\(\s*["'](evaluation\.[\w.]+)["']""", text))
        used |= set(re.findall(r"""\bt\(\s*["'](components\.[\w.]+)["']""", text))
    assert {"evaluation.launch", "evaluation.need_question", "evaluation.too_many"} <= used
    for key in used:
        assert isinstance(lookup(key), str), key
    for base in plurals:
        assert isinstance(lookup(f"{base}_one"), str) and isinstance(lookup(f"{base}_other"), str)


def test_the_dynamic_text_families_match_the_catalog():
    steps = lookup("evaluation.steps")
    assert set(steps["state"]) == {"pending", "current", "done", "failed", "stopped", "not_started"}
    # Tous les statuts de lane publiés par le service (`lane_status`) ont leur texte.
    assert {
        "waiting",
        "loading",
        "generating",
        "judging",
        "done",
        "failed",
        "timeout",
        "cancelled",
    } <= set(steps["lane"])
    assert set(lookup("evaluation.detail.verdict")) == {"appuyée", "non appuyée", "contredite"}
    assert set(lookup("evaluation.history.status")) >= {"ok", "cancelled", "error", "interrupted"}
    for metric in ("faithfulness", "relevance", "context_precision"):
        assert lookup(f"evaluation.results.col_{metric}") and lookup(
            f"evaluation.results.def_{metric}"
        )
    for state in ("running", "ok", "cancelled", "interrupted", "error", "stopping"):
        assert lookup(f"evaluation.banner.{state}")
    for state in ("cancelled", "interrupted", "error"):
        assert "jamais 0" in lookup(f"evaluation.announce.{state}")


def test_the_catalog_follows_the_french_typography_and_the_decisions():
    texts = dict(leaves(CATALOG["evaluation"]))
    for key, text in texts.items():
        assert not re.search(r"[^  ][:;!?]", text) or "http" in text, (key, text)
        assert not re.search(r" [:;!?]", text), (key, text)
        assert not re.search(r"«[^ ]|[^ ]»", text), (key, text)
    assert texts["results.partial_title"] == "Résultat partiel conservé"
    assert texts["same_extracts"] == "Les mêmes extraits sont fournis à tous les modèles."
    assert texts["need_question"] == "Saisissez une question"
    assert texts["too_many"] == "Choisissez 4 modèles au plus"
    assert texts["need_models"] == "Choisissez au moins un modèle"
    assert texts["need_base"] == "Importez des documents pour évaluer"
    assert texts["results.not_evaluated"] == "non évalué ({reason})"
    assert texts["results.stopped_reason"] == "évaluation arrêtée"
    # Pas de colonne « Global » (décision du 2026-10-19) ; Ragas en aide seulement.
    assert not [
        key for key, text in texts.items() if key.startswith("results.col_") and "Global" in text
    ]
    assert "Ragas" in texts["results.method"]
    assert not [key for key, text in texts.items() if "Ragas" in text and key != "results.method"]


def test_the_screen_uses_the_shared_contracts_and_creates_none_of_them_again():
    main = code("screens/documents-eval.js")
    assert (
        'from "../core/screen-tabs.js"' in main
        and 'screenTabs("documents", "documents-evaluation")' in main
    )
    assert (
        'from "../core/ram-guard.js"' in main and "onSmallerModel(" in main and "swapModel(" in main
    )
    assert 'from "../core/sse.js"' in main and "connectRun(" in main
    assert main.count("connectRun(") == 1  # un seul lecteur du flux
    assert 'from "../components/segments.js"' in code("screens/eval-results.js")
    assert 'from "../components/segments.js"' in code("screens/eval-form.js")
    results = code("screens/eval-results.js")
    assert "wl-chart-svg" in results and "wl-data-table" in results and "co2Group(" in results
    assert 'setAttribute("multi", "")' in code("screens/eval-form.js")
    assert 'setAttribute("purpose", "arena")' in code("screens/eval-form.js")
    assert 'setAttribute("purpose", "judge")' in code("screens/eval-form.js")
    assert "MAX_MODELS = 4" in code("screens/eval-form.js")
    for name in SCREEN_FILES:
        assert not re.search(
            r"function (nextTab|moveTab|screenTabs|isRamGuard)\b", code(name)
        ), name


def test_the_front_computes_no_note_and_no_default_score():
    # Les notes viennent du serveur (`eval_metric.score`, `aggregate`, `summary`) : aucune moyenne,
    # aucun arrondi de note ni valeur de repli à 0 dans l'écran. Seules les mesures (débit, CO2) sont
    # additionnées, dites dans l'aide.
    for name in SCREEN_FILES:
        text = code(name)
        assert not re.search(
            r"score\s*\?\?\s*0|score\s*\|\|\s*0|Math\.(round|floor|ceil)\(", text
        ), name
    model = code("screens/eval-model.js")
    assert model.count("reduce(") == 2  # débit moyen et CO2 total seulement
    assert 'typeof data.score === "number" ? data.score : null' in model  # un inconnu reste null


def test_texts_from_documents_questions_and_answers_never_reach_the_dom_as_html():
    forbidden = re.compile(
        r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|"
        r"DOMParser|\beval\(|new Function|setAttribute\(\s*[\"']on|srcdoc"
    )
    for name in SCREEN_FILES:
        assert not forbidden.search(code(name)), name


def test_the_stylesheet_is_linked_after_the_components_and_has_no_hard_coded_color():
    html = source("index.html")
    assert html.count('href="/static/evaluation.css"') == 1
    assert html.index("/static/documents.css") < html.index("/static/evaluation.css")
    css = source("evaluation.css")
    assert "@import" not in css
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css)
    assert "var(--color-primary-fill)" in css and "var(--color-on-primary)" in css
    # Un état ne tient jamais à la couleur seule : l'état d'une étape est un texte.
    assert "eval-step-state" in code("screens/eval-steps.js")


def test_the_api_exposes_the_two_evaluation_calls_under_their_own_domain_file():
    api = source("core/api/evaluation.js")
    assert 'request("/api/rag/eval/runs", { method: "POST", body })' in api
    assert "/api/rag/eval/runs?limit=" in api
    assert 'from "./api/evaluation.js"' in source("core/api.js")
    assert "...evaluationApi(request)," in source("core/api.js")
