"""Aucune route ne prend de texte saisi dans son chemin ou sa requête (C4).

`uvicorn.access` journalise la ligne de requête, chemin et chaîne de requête compris : un texte
saisi (question, extrait, nom de document) y serait écrit en clair. Les textes saisis voyagent donc
dans le corps d'un `POST` ou d'un `PUT`, jamais dans l'adresse. Un paramètre d'adresse est admis
s'il est un identifiant (`*_id`), un nombre, un booléen, une valeur d'une liste fermée, ou s'il
figure dans `JUSTIFIED` avec la raison qui l'exclut du « texte saisi ».
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI

from wavelocalai.config import Settings
from wavelocalai.web.app import create_app

from .route_discovery import discover

# Noms qui désignent un texte saisi : refusés partout, sans exception.
TYPED_TEXT_NAMES = re.compile(
    r"^(q|query|search|text|texte|question|prompt|content|message|filename|file_name|path)$"
)

# Paramètres de type texte admis, avec la raison (ils ne sont pas saisis librement).
JUSTIFIED: dict[str, str] = {
    "tag": "nom d'un modèle choisi dans la liste installée ou le catalogue, jamais tapé",
    "name": "nom d'un fichier de sortie d'agent, rendu par l'API de l'agent (liste fermée)",
    "window": "fenêtre de l'historique carbone : valeurs fixes (jour, semaine, mois…)",
    "kind": "type de conversation : liste fermée (chat, discussion…)",
    "purpose": "usage d'un modèle par défaut : liste fermée",
    "after": "curseur d'événement rendu par le serveur (`Last-Event-ID`)",
}


def _is_identifier(name: str) -> bool:
    return name == "id" or name.endswith("_id")


def _schema_is_scalar(schema: dict) -> bool:
    kinds = {schema.get("type")} | {part.get("type") for part in schema.get("anyOf", [])}
    return bool(kinds & {"integer", "number", "boolean"}) and "string" not in kinds


def address_parameters(app: FastAPI) -> list[tuple[str, str, str, dict]]:
    """(chemin, emplacement, nom, schéma) de chaque paramètre d'adresse de l'app, toutes routes
    confondues (schéma OpenAPI, plus les routes hors schéma)."""
    found: dict[tuple[str, str, str], dict] = {}
    for path, operations in app.openapi()["paths"].items():
        for operation in operations.values():
            for parameter in operation.get("parameters", []):
                if parameter["in"] in {"path", "query"}:
                    key = (path, parameter["in"], parameter["name"])
                    found[key] = parameter.get("schema", {})
    routes, _ = discover(app)
    for route in routes:
        for name in route.path_params:
            found.setdefault((route.path, "path", name), {})
        for name in route.query:
            found.setdefault((route.path, "query", name), {})
    return [(path, where, name, schema) for (path, where, name), schema in sorted(found.items())]


def violations(app: FastAPI) -> list[str]:
    problems: list[str] = []
    for path, where, name, schema in address_parameters(app):
        if TYPED_TEXT_NAMES.match(name):
            problems.append(f"{path} : le paramètre {where} `{name}` est un texte saisi")
        elif _is_identifier(name) or _schema_is_scalar(schema) or name in JUSTIFIED:
            continue
        else:
            problems.append(
                f"{path} : le paramètre {where} `{name}` n'est ni un identifiant, ni un nombre, "
                "ni justifié dans JUSTIFIED : un texte saisi va dans le corps de la requête"
            )
    return problems


def test_no_route_takes_typed_text_in_its_path_or_query():
    app = create_app(Settings(env_file=Path("absent.env")))
    assert violations(app) == []


def test_the_check_sees_every_parameter_of_the_real_app():
    """Garde-fou du test : il lit bien les paramètres connus (sinon il passerait à vide)."""
    app = create_app(Settings(env_file=Path("absent.env")))
    names = {(where, name) for _, where, name, _ in address_parameters(app)}
    assert {("path", "run_id"), ("query", "limit"), ("path", "tag")} <= names


def test_the_check_refuses_a_typed_text_parameter():
    app = create_app(Settings(env_file=Path("absent.env")))

    @app.get("/api/recherche")
    async def search(q: str = ""):
        return {}

    @app.get("/api/documents/{titre}", include_in_schema=False)
    async def by_title(titre: str):
        return {}

    @app.get("/api/essai")
    async def trial(question: str = ""):
        return {}

    found = violations(app)
    assert any("`q`" in line for line in found)
    assert any("`titre`" in line for line in found)
    assert any("`question`" in line for line in found)
