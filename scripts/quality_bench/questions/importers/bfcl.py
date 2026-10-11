"""Importeur de BFCL v4 (Apache-2.0) : quatre sources, une par famille de catégories.

Source : ``ShishirPatil/gorilla``, ``berkeley-function-call-leaderboard/bfcl_eval/data/``
(JSON Lines malgré l'extension ``.json``) ; le dépôt Hugging Face s'arrête à la v3.

- ``bfcl-live`` : ``live_simple`` et ``live_multiple`` (AST) ;
- ``bfcl-parallel`` : ``live_parallel`` et ``live_parallel_multiple`` (AST). Le ``parallel``
  non-live fait partie de « BFCL non-live AST », refusé (``REFUSED_SOURCES``) ;
- ``bfcl-multi`` : ``multi_turn_base`` (état final, environnement simulé de la story 4) ;
- ``bfcl-irrelevance`` : ``live_irrelevance`` (abstention : aucun appel attendu).

Les fonctions passent au format d'outil d'Ollama comme le fait BFCL pour les modèles à appel
de fonction : types Gorilla convertis (``dict`` → ``object``, ``float`` → ``number``…), points
des noms remplacés par ``_``. Les déclarations d'origine restent dans ``grader.params`` pour le
correcteur AST (``ast_checker``).
"""

from __future__ import annotations

import copy
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from ...common.jsonl import read_complete_jsonl
from .base import Importer, build_questions
from .remote import RemoteFile

_REPO = "ShishirPatil/gorilla"
_REVISION = "6ea57973c7a6097fd7c5915698c54c17c5b1b6c8"
_DATA = "berkeley-function-call-leaderboard/bfcl_eval/data/"

_HASHES = {
    "BFCL_v4_live_simple.json": "1af2ac87dca47556db7b7e37e51e28b459a38b594e3c7b3c792b4903598ca0c4",
    "possible_answer/BFCL_v4_live_simple.json": (
        "fec9cfa9744a936f9126981e85a2023da1e63e273eafebc81923a1162fad70ce"
    ),
    "BFCL_v4_live_multiple.json": "fd8ccfad4d911420d0e3341dbe2fff77d1d341da934248b9bb2bda24ab3a10c8",
    "possible_answer/BFCL_v4_live_multiple.json": (
        "97e90d59c5bd76c55a2920ce93e5566e9046307d3f558578f085f9d3a56c3084"
    ),
    "BFCL_v4_live_parallel.json": "6c26e9fdc3350cf596e6d1ea9c179cbff834761bccf562f4141ed29a839ca421",
    "possible_answer/BFCL_v4_live_parallel.json": (
        "8a9f189ff0e832ebbbbdade1fd95a7dbcc67406e9177df3f0aad76f59ab00350"
    ),
    "BFCL_v4_live_parallel_multiple.json": (
        "21d4b9319c1faac431e22757b367ea28917fe467364c3a4b17f16ec06d4f6e79"
    ),
    "possible_answer/BFCL_v4_live_parallel_multiple.json": (
        "f5b5f360556c5feb51db46fb9f56ee4b304f4b45b161599bbb14161c98a2873f"
    ),
    "BFCL_v4_live_irrelevance.json": (
        "6559fda2beaceb609a2cd2e504c65b4a56cb448e1ef88fddfd199e163d163349"
    ),
    "BFCL_v4_multi_turn_base.json": (
        "1a21a995d06fd6f20ba55de7bced30ef953ec35e998f502ec2ecf4d66ef1c43a"
    ),
    "possible_answer/BFCL_v4_multi_turn_base.json": (
        "1fee67823b317571649177dd89d63969feaae4e810cc7448ee55ba797fb7c8fc"
    ),
    "multi_turn_func_doc/gorilla_file_system.json": (
        "c4c1b741c71e2a17c97a5dc9c4a91d89978c4eaece56494d14272d5df6c650e9"
    ),
    "multi_turn_func_doc/math_api.json": (
        "83fa31708c89442bdcf12ac4dfbe3be8663ec9183a1b1524a9fda98164bc7e0b"
    ),
    "multi_turn_func_doc/message_api.json": (
        "4d58ea933a5d2b280d7a52366617fb47fecd333d7b0e08e724db6fa12fb5f847"
    ),
    "multi_turn_func_doc/posting_api.json": (
        "87f9fc404a06e4107d7c366f1399c596440e84c16cb119faf374b2f532d86e8b"
    ),
    "multi_turn_func_doc/ticket_api.json": (
        "31324e0380782664fe82ba05bd23517808ad55692b45a5fe7c3d4d395fe4f0f8"
    ),
    "multi_turn_func_doc/trading_bot.json": (
        "1a7933fd8f0cb8fbec38aeae05cb8c24132747cad4904fe1c13ac3d01fc22c2d"
    ),
    "multi_turn_func_doc/travel_booking.json": (
        "f17b950c13adddf41d0848077df58788252e4c2e7cad5cfa71c8c4bf04f57b26"
    ),
    "multi_turn_func_doc/vehicle_control.json": (
        "0c8a66292844874ef7b168f343bc394d8615d2d9e1f4387999a9ee23011eac78"
    ),
}


def _remote(name: str) -> RemoteFile:
    return RemoteFile("github", _REPO, _REVISION, _DATA + name, _HASHES[name])


# Classe de l'environnement multi-tours → fichier de déclarations (executable_backend_config).
CLASS_DOCS = {
    "GorillaFileSystem": "gorilla_file_system",
    "MathAPI": "math_api",
    "MessageAPI": "message_api",
    "TwitterAPI": "posting_api",
    "TicketAPI": "ticket_api",
    "TradingBot": "trading_bot",
    "TravelAPI": "travel_booking",
    "VehicleControlAPI": "vehicle_control",
}

# Types Gorilla → types JSON Schema (GORILLA_TO_OPENAPI de BFCL, « any » compris).
_TYPE_MAP = {
    "dict": "object",
    "float": "number",
    "tuple": "array",
    "any": "string",
    "Any": "string",
    "bool": "boolean",
    "int": "integer",
    "String": "string",
}


def _convert_types(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                _TYPE_MAP.get(item, item)
                if key == "type" and isinstance(item, str)
                else _convert_types(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_convert_types(item) for item in value]
    return value


def to_ollama_tools(functions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Déclarations BFCL → outils Ollama (nom sans point, types JSON Schema)."""
    return [
        {
            "type": "function",
            "function": {
                "name": function["name"].replace(".", "_"),
                "description": function.get("description", ""),
                "parameters": _convert_types(copy.deepcopy(function["parameters"])),
            },
        }
        for function in functions
    ]


def _answers(local: Mapping[str, Path], name: str) -> dict[str, Any]:
    rows = read_complete_jsonl(local[_DATA + "possible_answer/" + name])
    return {row["id"]: row["ground_truth"] for row in rows}


def _single_turn(
    slug: str, local: Mapping[str, Path], names: tuple[str, ...], with_answers: bool
) -> list[dict[str, Any]]:
    return build_questions(slug, _single_turn_items(slug, local, names, with_answers))


def _single_turn_items(
    slug: str, local: Mapping[str, Path], names: tuple[str, ...], with_answers: bool
) -> Iterator[dict[str, Any]]:
    number = 0
    for name in names:
        category = name.removeprefix("BFCL_v4_").removesuffix(".json")
        answers = _answers(local, name) if with_answers else {}
        for row in read_complete_jsonl(local[_DATA + name]):
            number += 1
            if len(row["question"]) != 1:
                raise ValueError(f"{row['id']} : un seul tour attendu en {category}")
            if with_answers and row["id"] not in answers:
                raise ValueError(f"{row['id']} : réponse attendue absente")
            yield {
                "number": number,
                "group": f"{slug}/{number:04d}",
                "messages": row["question"][0],
                "tools": to_ollama_tools(row["function"]) or None,
                "grader_params": {
                    "bfcl_id": row["id"],
                    "category": category,
                    "functions": row["function"],
                    "underscore_to_dot": True,
                },
                "target": answers.get(row["id"]) if with_answers else None,
            }


LIVE = ("BFCL_v4_live_simple.json", "BFCL_v4_live_multiple.json")
PARALLEL = ("BFCL_v4_live_parallel.json", "BFCL_v4_live_parallel_multiple.json")
IRRELEVANCE = ("BFCL_v4_live_irrelevance.json",)
MULTI = "BFCL_v4_multi_turn_base.json"


def convert_live(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    return _single_turn("bfcl-live", local, LIVE, with_answers=True)


def convert_parallel(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    return _single_turn("bfcl-parallel", local, PARALLEL, with_answers=True)


def convert_irrelevance(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    return _single_turn("bfcl-irrelevance", local, IRRELEVANCE, with_answers=False)


def convert_multi(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    """Conversations multi-tours : premier tour dans ``messages``, suivants dans ``turns`` ;
    outils = déclarations des classes engagées, fonctions exclues retirées ; état initial dans
    ``env`` ; cible = appels attendus par tour."""
    docs = {
        cls: read_complete_jsonl(local[f"{_DATA}multi_turn_func_doc/{doc}.json"])
        for cls, doc in CLASS_DOCS.items()
    }
    answers = _answers(local, MULTI)
    return build_questions("bfcl-multi", _multi_items(local, docs, answers))


def _multi_items(
    local: Mapping[str, Path], docs: Mapping[str, list[dict[str, Any]]], answers: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    for number, row in enumerate(read_complete_jsonl(local[_DATA + MULTI]), start=1):
        excluded = set(row.get("excluded_function") or [])
        functions = [
            function
            for cls in row["involved_classes"]
            for function in docs[cls]
            if function["name"] not in excluded
        ]
        declarations = [
            {key: value for key, value in function.items() if key != "response"}
            for function in functions
        ]
        turns = row["question"]
        yield {
            "number": number,
            "group": f"bfcl-multi/{number:04d}",
            "messages": turns[0],
            "turns": turns[1:] or None,
            "tools": to_ollama_tools(declarations),
            "env": {
                "name": "bfcl_multi_turn",
                "initial_state": {
                    "involved_classes": row["involved_classes"],
                    "initial_config": row["initial_config"],
                },
            },
            "grader_params": {
                "bfcl_id": row["id"],
                "category": "multi_turn_base",
                "excluded_function": sorted(excluded),
                "functions": functions,
                "underscore_to_dot": True,
            },
            "target": answers[row["id"]],
        }


def _files(*names: str) -> tuple[RemoteFile, ...]:
    return tuple(_remote(name) for name in names)


IMPORTERS = {
    "bfcl-live": Importer(
        "bfcl-live", _files(*LIVE, *(f"possible_answer/{n}" for n in LIVE)), convert_live
    ),
    "bfcl-parallel": Importer(
        "bfcl-parallel",
        _files(*PARALLEL, *(f"possible_answer/{n}" for n in PARALLEL)),
        convert_parallel,
    ),
    "bfcl-irrelevance": Importer("bfcl-irrelevance", _files(*IRRELEVANCE), convert_irrelevance),
    "bfcl-multi": Importer(
        "bfcl-multi",
        _files(
            MULTI,
            f"possible_answer/{MULTI}",
            *(f"multi_turn_func_doc/{doc}.json" for doc in CLASS_DOCS.values()),
        ),
        convert_multi,
    ),
}
