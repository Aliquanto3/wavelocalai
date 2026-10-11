"""Brique commune des importeurs : contrat ``Importer``.

La construction d'une question (``build_question``, ``build_questions``, choix du palier,
estimation du prompt, encodage des flottants, identifiant) vit dans ``questions/build.py``, un
module sans réseau partagé avec les générateurs et les questions maison ; elle est réexportée
ici, avec l'API de la story 2.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..build import (
    CHARS_PER_TOKEN,
    CONTEXT_MARGIN,
    FLOAT_MARKER,
    PromptTooLongError,
    build_question,
    build_questions,
    choose_num_ctx,
    encode_floats,
    estimate_prompt_tokens,
    max_cap,
    question_id,
)
from ..pinned import RemoteFile

__all__ = [
    "CHARS_PER_TOKEN",
    "CONTEXT_MARGIN",
    "FLOAT_MARKER",
    "Importer",
    "PromptTooLongError",
    "build_question",
    "build_questions",
    "choose_num_ctx",
    "encode_floats",
    "estimate_prompt_tokens",
    "max_cap",
    "question_id",
]


@dataclass(frozen=True)
class Importer:
    """Importeur d'une source : fichiers bruts épinglés et conversion pure en candidats.

    ``convert`` reçoit ``{chemin dans le dépôt: chemin local}`` et rend les questions
    candidates, chacune déjà validée, dans un ordre stable.
    """

    slug: str
    files: tuple[RemoteFile, ...]
    convert: Callable[[Mapping[str, Path]], list[dict[str, Any]]]
