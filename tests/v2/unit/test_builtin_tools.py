"""Outils de la v1 copiés dans la v2 (story 6.2) : mêmes résultats, registre, email jamais envoyé.

Les textes attendus de l'analyse de CSV sont ceux que rendait `_analyze_csv_impl` de la v1 sur ce
jeu de test (relevés une fois, vérifiés égaux octet pour octet) : aucun import de `src.*` ici.
"""

from __future__ import annotations

import ast
import zipfile
from pathlib import Path

import pytest

from wavelocalai.agents.tools import ToolError, ToolOutput, Workspace
from wavelocalai.agents.tools import basic as basic_module
from wavelocalai.agents.tools import build_registry
from wavelocalai.agents.tools import builtin as builtin_module
from wavelocalai.agents.tools import files as files_module

from ..conftest import make_settings

CSV = (
    "region,produit,quantite,prix\nNord,Stylo,10,1.5\nSud,Cahier,5,3.2\nNord,Cahier,7,3.2\n"
    "Est,Stylo,12,1.4\nSud,Stylo,3,1.5\nOuest,Règle,8,2.25\n"
)
HEAD = (
    "**Analyse de ventes.csv**\n\n- Lignes : 6\n- Colonnes : 4\n"
    "- Colonnes disponibles : region, produit, quantite, prix\n\n"
)
V1_RESULTS = {
    "aperçu": HEAD + "**Aperçu (5 premières lignes) :**\n  region produit  quantite  prix\n"
    "0   Nord   Stylo        10   1.5\n1    Sud  Cahier         5   3.2\n"
    "2   Nord  Cahier         7   3.2\n3    Est   Stylo        12   1.4\n"
    "4    Sud   Stylo         3   1.5",
    "stats": HEAD
    + "**Statistiques descriptives :**\n        quantite      prix\ncount   6.000000  6.000000\n"
    "mean    7.500000  2.175000\nstd     3.271085  0.850735\nmin     3.000000  1.400000\n"
    "25%     5.500000  1.500000\n50%     7.500000  1.875000\n75%     9.500000  2.962500\n"
    "max    12.000000  3.200000",
    "moyenne de prix": HEAD + "**Moyenne de 'prix' :** 2.18",
    "somme": HEAD + "Attention : Aucune colonne spécifique détectée. Voici les sommes :\n"
    "quantite    45.00\nprix        13.05",
    "bonjour": HEAD
    + "Attention : Requête non comprise. Reformulez avec : 'aperçu', 'moyenne de X', "
    "'somme de X', 'stats', etc.",
}


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def space(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    (root / "ventes.csv").write_text(CSV, encoding="utf-8")
    return Workspace(root)


@pytest.fixture
def registry(settings, space):
    return build_registry(settings, space)


def _imported_roots(module) -> set[str]:
    """Paquets que le module importe (au niveau du module ou dans une fonction)."""
    roots: set[str] = set()
    for node in ast.walk(ast.parse(Path(module.__file__).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


async def run(registry, tool_id, **arguments):
    tool = next(t for t in registry.all() if t.id == tool_id)
    return await tool.run(arguments)


# --- registre ------------------------------------------------------------------------------------


def test_the_registry_carries_the_nine_tools_of_the_v1_with_the_lexicon_labels(registry):
    assert {t.id: t.label for t in registry.all()} == {
        "get_current_time": "Heure",
        "calculator": "Calculatrice",
        "search_wavestone_internal": "Recherche interne Wavestone",
        "send_email": "Envoi d'email",
        "analyze_csv": "Analyse de données",
        "generate_document": "Génération de document",
        "generate_chart": "Génération de graphique",
        "generate_markdown_report": "Rapport Markdown",
        "system_monitor": "Moniteur système",
    }
    for tool in registry.all():
        spec = tool.spec()
        assert spec["parameters"]["type"] == "object" and spec["description"]
        assert set(spec["parameters"]["required"]) <= set(spec["parameters"]["properties"])


def test_only_the_email_is_sensitive_and_only_without_smtp_unavailable(registry):
    assert [t.id for t in registry.all() if t.sensitive] == ["send_email"]
    unavailable = {t.id: t.reason for t in registry.all() if not t.available}
    assert list(unavailable) == ["send_email"]
    reason = unavailable["send_email"]
    assert reason.startswith("Configuration SMTP absente : renseignez SMTP_USER, SMTP_PASSWORD")
    assert "dans le fichier .env" in reason


def test_the_email_is_available_once_smtp_is_configured(tmp_path, space):
    env = {"SMTP_USER": "moi@example.org", "SMTP_PASSWORD": "mot-de-passe-smtp"}
    registry = build_registry(make_settings(tmp_path, environ=env), space)
    email = registry.get(["send_email"])[0]  # plus d'erreur : l'outil est disponible
    assert email.available and email.reason is None and email.sensitive
    assert email.listing()["reason"] is None


def test_a_tool_whose_module_is_missing_is_unavailable_with_its_reason(
    monkeypatch, settings, space
):
    real = builtin_module.importlib.util.find_spec
    monkeypatch.setattr(
        builtin_module.importlib.util,
        "find_spec",
        lambda name, *a: None if name == "docx" else real(name, *a),
    )
    docx = next(t for t in build_registry(settings, space).all() if t.id == "generate_document")
    assert not docx.available and docx.reason == "Module Python absent : docx."


def test_the_listing_gives_what_the_screen_shows(registry):
    row = next(t.listing() for t in registry.all() if t.id == "calculator")
    assert row == {
        "id": "calculator",
        "label": "Calculatrice",
        "description": "Calculs mathématiques",
        "available": True,
        "reason": None,
        "sensitive": False,
    }


def test_smtp_settings_come_from_the_environment_and_the_password_is_a_masked_secret(tmp_path):
    settings = make_settings(
        tmp_path,
        environ={
            "SMTP_SERVER": "smtp.example.org",
            "SMTP_PORT": "2525",
            "SMTP_USER": "moi",
            "SMTP_PASSWORD": "pw-smtp-secret",
        },
    )
    assert (settings.smtp.server, settings.smtp.port, settings.smtp.user) == (
        "smtp.example.org",
        2525,
        "moi",
    )
    assert settings.smtp.missing() == []
    assert "pw-smtp-secret" in settings.secret_values()
    assert "pw-smtp-secret" not in repr(settings)


def test_smtp_defaults_need_a_user_and_a_password(settings):
    assert settings.smtp.server == "smtp.gmail.com" and settings.smtp.port == 587
    assert settings.smtp.missing() == ["SMTP_USER", "SMTP_PASSWORD"]
    assert "pw" not in settings.secret_values()


# --- outils sans fichier -------------------------------------------------------------------------


async def test_the_calculator_gives_the_results_of_the_v1(registry):
    assert await run(registry, "calculator", expression="2 + 2") == "4"
    assert await run(registry, "calculator", expression="3.14 * (12/4)") == "9.42"
    assert await run(registry, "calculator", expression="100 / 3") == "33.33333333"
    assert await run(registry, "calculator", expression="0.1+0.2") == "0.3"
    for bad, message in [
        ("2**3", "Opérateurs consécutifs"),
        ("__import__('os')", "Caractères non autorisés"),
        ("(1+2", "Parenthèses non équilibrées"),
        ("1/0", "Division par zéro"),
        ("1" * 101, "trop longue"),
        ("   ", "Argument manquant"),
    ]:
        with pytest.raises(ToolError, match=message):
            await run(registry, "calculator", expression=bad)


async def test_a_missing_argument_is_an_error_the_agent_can_read(registry):
    with pytest.raises(ToolError, match="Argument manquant : « expression »"):
        await run(registry, "calculator")


async def test_time_search_and_system_monitor(registry):
    assert len((await run(registry, "get_current_time")).split()) == 2
    assert "Wavestone" in await run(registry, "search_wavestone_internal", query="PUE")
    assert "1.4" in await run(registry, "search_wavestone_internal", query="pue")
    assert "Aucune information" in await run(registry, "search_wavestone_internal", query="zzz")
    report = await run(registry, "system_monitor")
    assert report.startswith("**Monitoring Système**") and "### RAM" in report


async def test_the_email_tool_only_prepares_a_draft_and_the_module_cannot_send(registry):
    text = await run(
        registry, "send_email", to="client@example.org", subject="Synthèse", body="Bonjour"
    )
    assert "Brouillon d'email préparé pour client@example.org" in text and "pas envoyé" in text
    with pytest.raises(ToolError, match="Adresse email invalide"):
        await run(registry, "send_email", to="pas-une-adresse", subject="S", body="B")
    with pytest.raises(ToolError, match="Sujet manquant"):
        await run(registry, "send_email", to="a@b.c", subject="x" * 201, body="B")
    # Aucun code d'envoi dans les outils : ni `smtplib`, ni socket, ni sous-processus (6.3 seulement).
    for module in (basic_module, builtin_module, files_module):
        assert not _imported_roots(module) & {"smtplib", "socket", "subprocess", "httpx", "os"}


# --- analyse de CSV : les résultats de la v1 -----------------------------------------------------


@pytest.mark.parametrize("query", list(V1_RESULTS))
async def test_the_csv_analysis_gives_the_exact_text_of_the_v1(registry, query):
    assert (
        await run(registry, "analyze_csv", filepath="ventes.csv", query=query) == V1_RESULTS[query]
    )


async def test_the_csv_analysis_refuses_free_paths_and_other_formats(registry, space, tmp_path):
    (tmp_path / "secret.csv").write_text("a\n1\n", encoding="utf-8")
    (space.root / "classeur.xlsx").write_bytes(b"PK")
    for path in ("../secret.csv", str(tmp_path / "secret.csv"), "C:\\secret.csv", "absent.csv"):
        with pytest.raises(ToolError):
            await run(registry, "analyze_csv", filepath=path, query="aperçu")
    with pytest.raises(ToolError, match="Format non supporté"):
        await run(registry, "analyze_csv", filepath="classeur.xlsx", query="aperçu")


async def test_an_empty_csv_is_an_error(registry, space):
    (space.root / "vide.csv").write_text("", encoding="utf-8")
    with pytest.raises(ToolError, match="Fichier vide"):
        await run(registry, "analyze_csv", filepath="vide.csv", query="stats")


# --- fichiers produits ---------------------------------------------------------------------------


async def test_a_document_is_written_in_the_work_folder_and_referenced(registry, space):
    out = await run(
        registry,
        "generate_document",
        title="Rapport Q4",
        content="## Intro\n\n- un\n- deux\n1. premier\nTexte simple",
        filename="bilan",
    )
    assert isinstance(out, ToolOutput) and out.artifact_url == "/api/outputs/bilan.docx"
    assert out.text == "Document créé : bilan.docx" and str(space.root) not in out.text
    path = space.root / "bilan.docx"
    assert zipfile.is_zipfile(path)
    from docx import Document

    paragraphs = [p.text for p in Document(str(path)).paragraphs]
    assert "Rapport Q4" in paragraphs and "Intro" in paragraphs and "Texte simple" in paragraphs


async def test_a_chart_is_a_png_in_the_work_folder(registry, space):
    for kind in ("bar", "line", "pie"):
        out = await run(
            registry,
            "generate_chart",
            data_json='{"labels": ["Jan", "Fév", "Mar"], "values": [10, 25, 15]}',
            chart_type=kind,
            title="Ventes",
            filename=f"ventes-{kind}",
        )
        assert out.artifact_url == f"/api/outputs/ventes-{kind}.png"
        assert (space.root / f"ventes-{kind}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    out = await run(registry, "generate_chart", data_json={"labels": ["a"], "values": [1]})
    assert out.artifact_url.startswith("/api/outputs/chart_") and out.artifact_url.endswith(".png")


async def test_chart_errors_are_the_ones_of_the_v1(registry, space):
    for arguments, message in [
        ({"data_json": "pas du json"}, "Format JSON invalide"),
        ({"data_json": '{"labels": []}'}, "Format JSON invalide"),
        ({"data_json": '{"labels": ["a"], "values": [1, 2]}'}, "identique"),
        ({"data_json": '{"labels": ["a"], "values": [1]}', "chart_type": "radar"}, "non supporté"),
    ]:
        with pytest.raises(ToolError, match=message):
            await run(registry, "generate_chart", **arguments)
    assert not list(space.root.glob("*.png"))


async def test_a_markdown_report_is_written_from_json_sections_or_plain_text(registry, space):
    out = await run(
        registry,
        "generate_markdown_report",
        title="Analyse IA",
        sections='{"Introduction": "Bonjour", "Résultats": "42"}',
        filename="analyse",
    )
    assert out.artifact_url == "/api/outputs/analyse.md"
    text = (space.root / "analyse.md").read_text(encoding="utf-8")
    assert text.startswith("# Analyse IA\n\n*Généré le ") and "## Résultats\n\n42" in text
    plain = await run(registry, "generate_markdown_report", title="T", sections="juste du texte")
    name = plain.artifact_url.rsplit("/", 1)[1]
    assert "## Contenu\n\njuste du texte" in (space.root / name).read_text(encoding="utf-8")
    with pytest.raises(ToolError, match="JSON invalide"):
        await run(registry, "generate_markdown_report", title="T", sections="{pas du json")


@pytest.mark.parametrize(
    "tool_id", ["generate_document", "generate_chart", "generate_markdown_report"]
)
@pytest.mark.parametrize("filename", ["../evasion", "/tmp/evasion", "C:\\evasion", "a/b"])
async def test_a_producing_tool_never_writes_outside_the_work_folder(
    registry, space, tmp_path, tool_id, filename
):
    arguments = {
        "generate_document": {"title": "T", "content": "x"},
        "generate_chart": {"data_json": '{"labels": ["a"], "values": [1]}'},
        "generate_markdown_report": {"title": "T", "sections": "x"},
    }[tool_id]
    with pytest.raises(ToolError, match="refusé"):
        await run(registry, tool_id, filename=filename, **arguments)
    assert not list(tmp_path.glob("evasion*")) and not list(space.root.glob("*evasion*"))
    assert not [p for p in space.root.iterdir() if p.name != "ventes.csv"]
