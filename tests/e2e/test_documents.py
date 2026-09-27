"""
Assistant documentaire, dans l'app réelle : import du document de test par l'interface (une
écriture Chroma d'un autre processus resterait invisible pour le serveur), question et source,
vidage confirmé. La collection est celle du dossier temporaire de l'app, jamais `data/chroma`.

Constats couverts : F1 et CAP-2 (ingestion réelle : compteur, réponse juste avec sa source),
F2 (évaluation de la qualité : note ou « non évalué », parcours t_rag_eval.py), U6 (état
vide lisible), U15 (vidage soumis à confirmation, « Annuler » ne supprime rien),
D1 (badge Local sur la réponse), F3 (aucune trace).
"""

import re

import pytest

from src.app.modules import DOCUMENTS
from tests.e2e import helpers as h

pytestmark = pytest.mark.e2e

QUESTION_PLACEHOLDER = "Posez une question à vos documents"
EMPTY_TITLE = "Votre base documentaire est vide"
_SUMMARY_RE = re.compile(r"(\d+)\s+documents? indexés? · (\d+)\s+extraits?")


def base_summary(page) -> tuple[int, int]:
    """(documents indexés, extraits) lus dans la barre latérale."""
    text = h.flat(h.sidebar(page).inner_text())
    match = _SUMMARY_RE.search(text)
    assert match, f"compteur de la base absent : {text[-300:]}"
    return int(match.group(1)), int(match.group(2))


def open_documents(page, app) -> None:
    h.goto(page, app.base_url, DOCUMENTS.url_path)


def import_document(page, path) -> int:
    """Importe `path` par le dialogue de la base ; renvoie le nombre d'extraits ajoutés."""
    main = h.main(page)
    empty = main.get_by_role("button", name="Importer des documents")
    if empty.count():
        empty.click()
    else:
        h.sidebar(page).get_by_role("button", name="Gérer la base documentaire").click()
    dialog = page.get_by_role("dialog")
    h.settle_after_action(page, until=dialog)
    dialog.locator('input[type="file"]').set_input_files(str(path))
    ready = dialog.get_by_text(re.compile(r"1\s+fichier prêt à être indexé"))
    h.settle_after_action(page, until=ready)
    dialog.get_by_role("button", name="Indexer les documents").click()
    success = h.wait_text(main, re.compile(r"extraits? ajoutés? depuis 1\s+document"))
    h.settle(page)
    match = re.search(r"(\d+)\s+extraits? ajoutés?", h.flat(success.inner_text()))
    assert match, success.inner_text()
    return int(match.group(1))


def test_import_then_ask_with_source(
    page, app, require_models, require_embedding, test_document, generation_timeout_ms
):
    """Le document importé est indexé (compteur à jour, fichiers Chroma dans le dossier
    temporaire), puis la question obtient la bonne réponse avec sa source."""
    (tag,) = require_models("chat")
    open_documents(page, app)
    main = h.main(page)
    assert main.get_by_role("heading", name=EMPTY_TITLE).count() == 1
    assert base_summary(page) == (0, 0)

    added = import_document(page, test_document)
    assert added >= 1
    assert base_summary(page) == (1, added)
    assert any((app.data_dir / "chroma").rglob("*")), "rien d'écrit dans la collection temporaire"
    assert h.ui_errors(page) == []

    panel = h.visible_panel(page)
    h.pick_model(page, panel.locator('[data-testid="stSelectbox"]').first, tag)
    h.chat_send(page, QUESTION_PLACEHOLDER, "Quel est le budget total du projet Hirondelle ?")
    sources = main.locator('[data-testid="stExpander"]').filter(
        has_text=re.compile(r"sources? utilisées?")
    )
    h.wait_count(page, sources, 1, generation_timeout_ms, "Réponse de l'assistant documentaire")

    answer = h.flat(main.locator('[data-testid="stChatMessage"]').last.inner_text())
    assert "412" in answer, f"budget du document (412 000 euros) absent de : {answer}"
    assert "Local" in answer
    sources.first.locator("summary").click()
    h.settle_after_action(page, until=sources.first.get_by_text(test_document.name).first)
    assert h.exceptions(page) == []


def test_quality_evaluation_scores_or_not_evaluated(
    page, app, require_models, require_embedding, test_document, generation_timeout_ms
):
    """Évaluation de la qualité sur le document de test (parcours t_rag_eval.py) : un modèle,
    un juge local ; le résultat est une note sur 100 ou « non évalué », jamais un succès vide
    ni une trace (F2)."""
    from src.app.states import NOT_EVALUATED

    chat, judge = require_models("chat", "judge")
    open_documents(page, app)
    if base_summary(page)[1] == 0:
        import_document(page, test_document)
    h.click_tab(page, "Évaluation de la qualité")
    panel = h.visible_panel(page)

    candidates = panel.locator('[data-testid="stMultiSelect"]').first
    h.multiselect_clear(page, candidates)
    h.add_model(page, candidates, chat)
    h.pick_model(page, panel.locator('[data-testid="stSelectbox"]').first, judge)
    panel.get_by_label("Question qui demande le contenu de vos documents").fill(
        "Quel est le budget total du projet Hirondelle ?"
    )
    panel.get_by_role("button", name="Lancer l'évaluation").click()

    status = h.wait_text(panel, re.compile(r"Évaluation (terminée|échouée)"), generation_timeout_ms)
    h.settle(page, generation_timeout_ms)
    label = h.flat(status.inner_text())
    assert "Évaluation terminée" in label, label
    text = h.flat(panel.inner_text())
    scores = [
        h.flat(t)
        for t in panel.locator('[data-testid="stMetric"]')
        .filter(has_text="Note globale")
        .locator('[data-testid="stMetricValue"]')
        .all_inner_texts()
    ]
    assert all(re.fullmatch(r"\d+/100", v) for v in scores), scores
    assert scores or NOT_EVALUATED in text, text[-1500:]
    assert panel.get_by_role("heading", name="Réponses des modèles").count() == 1
    assert h.exceptions(page) == []


def test_clear_needs_confirmation(page, app, require_embedding, test_document):
    """Vider la base : le premier clic ne supprime rien et chiffre la conséquence ;
    « Annuler » ne supprime rien ; « Vider définitivement » vide la collection temporaire."""
    open_documents(page, app)
    if base_summary(page)[1] == 0:
        import_document(page, test_document)
    documents, chunks = base_summary(page)
    assert chunks >= 1

    def open_clear_confirmation():
        h.sidebar(page).get_by_role("button", name="Gérer la base documentaire").click()
        dialog = page.get_by_role("dialog")
        h.settle_after_action(page, until=dialog)
        dialog.get_by_role("button", name="Vider la base documentaire").click()
        alert = dialog.locator('[data-testid="stAlertContentWarning"]')
        h.settle_after_action(page, until=alert)
        warning = h.flat(alert.inner_text())
        assert re.search(rf"{chunks}\s+extraits? de {documents}\s+documents?", warning), warning
        assert re.search(r"sera supprimé|seront supprimés", warning), warning
        return dialog

    dialog = open_clear_confirmation()
    assert base_summary(page) == (documents, chunks), "supprimé avant confirmation"
    dialog.get_by_role("button", name="Annuler").click()
    h.settle_after_action(page, until=lambda: page.get_by_role("dialog").count() == 0)
    assert base_summary(page) == (documents, chunks), "« Annuler » a supprimé des extraits"

    dialog = open_clear_confirmation()
    # Garde-fou : la base vidée doit être celle du dossier temporaire de l'app, jamais
    # data/chroma (redirect_data de launch_app.py, testé par tests/unit/test_e2e_suite.py).
    chroma_dir = app.data_dir / "chroma"
    if not (chroma_dir.is_dir() and any(chroma_dir.rglob("*"))):
        pytest.fail(
            f"{chroma_dir} ne contient aucune donnée alors que la base affiche {chunks} "
            "extrait(s) : Chroma n'est pas redirigé, le vidage toucherait data/chroma.",
            pytrace=False,
        )
    dialog.get_by_role("button", name="Vider définitivement").click()
    success_alert = h.main(page).locator('[data-testid="stAlertContentSuccess"]')
    h.settle_after_action(page, until=success_alert)
    success = h.flat(success_alert.inner_text())
    assert "Base documentaire vidée" in success, success
    assert base_summary(page) == (0, 0)
    assert h.main(page).get_by_role("heading", name=EMPTY_TITLE).count() == 1
    assert h.exceptions(page) == []
