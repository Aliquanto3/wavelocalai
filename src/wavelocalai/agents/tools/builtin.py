"""Les outils de la v1 inscrits au registre des agents, avec leur disponibilité (story 6.2, AD-9).

Neuf outils, mêmes identifiants et libellés (lexique d'EXPERIENCE.md) que `TOOLS_METADATA` de la v1.
Chacun est une coroutine `run(arguments)` qui passe le travail (pandas, matplotlib, psutil, calcul à
délai) à un fil : la boucle d'événements et les autres runs ne sont jamais bloqués. Un résultat qui
commence par « Erreur » est une erreur d'outil (`failed: true`, `ToolError`), comme les refus du
dossier de travail. Disponibilité : le module Python requis est-il installé (`find_spec`, sans
l'importer), et, pour l'email, le SMTP est-il configuré dans `Settings`. « Envoi d'email » est
`sensitive` : la boucle ne l'exécute jamais sans approbation (6.3) et la fonction qu'il porte ne
fait que préparer un brouillon : aucun envoi réel n'existe dans ce module.
"""

from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import Callable, Sequence
from typing import Any

from wavelocalai.agents.tools import basic, files
from wavelocalai.agents.tools.registry import (
    AgentTool,
    ToolError,
    ToolFunction,
    ToolOutput,
    ToolRegistry,
)
from wavelocalai.agents.tools.workspace import Workspace
from wavelocalai.config import Settings

_STRING = {"type": "string"}


def _schema(properties: dict[str, Any], required: Sequence[str] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": list(required)}


def _argument(arguments: dict[str, Any], name: str, *, required: bool = True) -> Any:
    value = arguments.get(name)
    if value is None or (required and isinstance(value, str) and not value.strip()):
        if required:
            raise ToolError(f"Argument manquant : « {name} ».")
        return None
    return value


def _checked(text: str) -> str:
    """Un résultat « Erreur : … » est un échec d'outil."""
    if text.startswith("Erreur"):
        raise ToolError(text)
    return text


def _needs(*modules: str) -> dict[str, Any]:
    """`available` et `reason` d'un outil qui exige ces modules Python (cherchés sans les importer)."""
    absent = [name for name in modules if importlib.util.find_spec(name) is None]
    if not absent:
        return {"available": True, "reason": None}
    return {"available": False, "reason": f"Module Python absent : {', '.join(absent)}."}


def _plain(function: Callable[..., str], *names: str) -> ToolFunction:
    """Outil sans fichier : `function(**arguments de ces noms)` dans un fil."""

    async def run(arguments: dict[str, Any]) -> str:
        values = [_argument(arguments, name) for name in names]
        return _checked(await asyncio.to_thread(function, *values))

    return run


def build_registry(settings: Settings, workspace: Workspace | None = None) -> ToolRegistry:
    """Registre des outils de la v1 pour cette configuration. `workspace` : dossier de travail (par
    défaut `Settings.agent_work_dir`)."""
    space = workspace or Workspace(settings.agent_work_dir)
    max_bytes = settings.agents.max_input_mb * 1024 * 1024

    async def analyze_csv(arguments: dict[str, Any]) -> str:
        path = _argument(arguments, "filepath")
        query = _argument(arguments, "query")
        return await asyncio.to_thread(
            files.analyze_csv, space, str(path), str(query), max_bytes=max_bytes
        )

    def produced(
        function: Callable[..., tuple[str, Any]],
        required: Sequence[str],
        optional: Sequence[str],
    ) -> ToolFunction:
        """Outil qui écrit un fichier : son nom n'est jamais un chemin (`Workspace`) et le fichier
        est référencé par `artifact_url`. `required` : arguments passés dans l'ordre ; `optional` :
        passés par nom s'ils sont donnés."""

        async def run(arguments: dict[str, Any]) -> ToolOutput:
            values = [_argument(arguments, name) for name in required]
            extra = {n: arguments[n] for n in optional if arguments.get(n) is not None}
            text, path = await asyncio.to_thread(function, space, *values, **extra)
            return ToolOutput(text, space.artifact_url(path))

        return run

    smtp_missing = settings.smtp.missing()
    email_absent = basic.smtp_missing_help(smtp_missing) if smtp_missing else None

    async def draft_email(arguments: dict[str, Any]) -> str:
        values = [_argument(arguments, name) for name in ("to", "subject", "body")]
        return _checked(await asyncio.to_thread(basic.draft_email, *values))

    async def system_monitor(arguments: dict[str, Any]) -> str:
        return _checked(await asyncio.to_thread(basic.system_report))

    async def current_time(arguments: dict[str, Any]) -> str:
        return basic.current_time()

    return ToolRegistry(
        [
            AgentTool(
                "get_current_time",
                "Retourne la date et l'heure actuelles précises, au format AAAA-MM-JJ HH:MM:SS.",
                current_time,
                _schema({}),
                label="Heure",
                summary="Heure système",
            ),
            AgentTool(
                "calculator",
                "Effectue un calcul mathématique sécurisé (longueur max 100 caractères, délai de "
                "2 secondes). Opérateurs autorisés : + - * / ( ) . avec des nombres. "
                'Exemples : "2 + 2", "3.14 * (12/4)", "100 / 3".',
                _plain(basic.calculate_safe, "expression"),
                _schema(
                    {
                        "expression": {
                            **_STRING,
                            "description": "Expression mathématique à calculer",
                        }
                    },
                    ["expression"],
                ),
                label="Calculatrice",
                summary="Calculs mathématiques",
                **_needs("numexpr", "func_timeout"),
            ),
            AgentTool(
                "search_wavestone_internal",
                "Simule un moteur de recherche interne à l'entreprise Wavestone. Utilise cet outil "
                "pour chercher des informations sur les employés, les projets ou les politiques RH.",
                _plain(basic.search_wavestone, "query"),
                _schema({"query": {**_STRING, "description": "Terme de recherche"}}, ["query"]),
                label="Recherche interne Wavestone",
                summary="Base interne simulée",
            ),
            AgentTool(
                "send_email",
                "Prépare un email (brouillon) pour l'utilisateur. L'email n'est PAS envoyé par cet "
                "outil : l'utilisateur relit le destinataire, l'objet et le corps, puis valide "
                "lui-même l'envoi dans l'interface.",
                draft_email,
                _schema(
                    {
                        "to": {**_STRING, "description": "Adresse email du destinataire"},
                        "subject": {**_STRING, "description": "Objet (200 caractères au plus)"},
                        "body": {**_STRING, "description": "Corps du message (10000 au plus)"},
                    },
                    ["to", "subject", "body"],
                ),
                label="Envoi d'email",
                summary="Brouillon d'email, envoyé seulement après validation",
                sensitive=True,
                available=email_absent is None,
                reason=email_absent,
            ),
            AgentTool(
                "analyze_csv",
                "Analyse un fichier CSV du dossier de travail et répond à une question. Donne le "
                "nom du fichier (par exemple « ventes.csv »), jamais un chemin. Requêtes : "
                '"aperçu" (5 premières lignes), "stats" (statistiques descriptives), '
                '"moyenne de [colonne]", "somme de [colonne]", "compte [colonne]".',
                analyze_csv,
                _schema(
                    {
                        "filepath": {
                            **_STRING,
                            "description": "Nom du fichier CSV dans le dossier de travail",
                        },
                        "query": {**_STRING, "description": "Question d'analyse"},
                    },
                    ["filepath", "query"],
                ),
                label="Analyse de données",
                summary="Analyse d'un CSV du dossier de travail",
                **_needs("pandas"),
            ),
            AgentTool(
                "generate_document",
                "Génère un document Word (.docx). Le contenu peut utiliser le Markdown : # Titre, "
                "## Sous-titre, ### Sous-sous-titre, - puces, 1. liste numérotée. Rend le nom du "
                "fichier créé, que l'utilisateur télécharge.",
                produced(files.generate_document, ("title", "content"), ("filename",)),
                _schema(
                    {
                        "title": {**_STRING, "description": "Titre principal du document"},
                        "content": {**_STRING, "description": "Contenu en Markdown"},
                        "filename": {
                            **_STRING,
                            "description": "Nom du fichier, sans dossier (facultatif)",
                        },
                    },
                    ["title", "content"],
                ),
                label="Génération de document",
                summary="Création de DOCX",
                **_needs("docx"),
            ),
            AgentTool(
                "generate_chart",
                "Génère un graphique (PNG) à partir de données : barres (bar), courbe (line) ou "
                "camembert (pie). Rend le nom du fichier créé, que l'utilisateur télécharge.",
                produced(files.generate_chart, ("data_json",), ("chart_type", "title", "filename")),
                _schema(
                    {
                        "data_json": {
                            **_STRING,
                            "description": 'Données JSON {"labels": [...], "values": [...]}',
                        },
                        "chart_type": {"type": "string", "enum": list(files.CHART_TYPES)},
                        "title": {**_STRING, "description": "Titre du graphique"},
                        "filename": {
                            **_STRING,
                            "description": "Nom du fichier, sans dossier (facultatif)",
                        },
                    },
                    ["data_json"],
                ),
                label="Génération de graphique",
                summary="Graphiques PNG",
                **_needs("matplotlib"),
            ),
            AgentTool(
                "generate_markdown_report",
                "Génère un rapport structuré au format Markdown. Rend le nom du fichier créé, que "
                "l'utilisateur télécharge.",
                produced(files.generate_markdown_report, ("title", "sections"), ("filename",)),
                _schema(
                    {
                        "title": {**_STRING, "description": "Titre du rapport"},
                        "sections": {
                            **_STRING,
                            "description": 'Sections JSON {"Section 1": "contenu", ...}',
                        },
                        "filename": {
                            **_STRING,
                            "description": "Nom du fichier, sans dossier (facultatif)",
                        },
                    },
                    ["title", "sections"],
                ),
                label="Rapport Markdown",
                summary="Rapports MD",
            ),
            AgentTool(
                "system_monitor",
                "Récupère les métriques système actuelles (CPU, RAM, disque), avec alertes. À "
                "utiliser pour vérifier les ressources avant une tâche intensive ou diagnostiquer "
                "un problème de performance.",
                system_monitor,
                _schema({}),
                label="Moniteur système",
                summary="Métriques système",
                **_needs("psutil"),
            ),
        ]
    )
