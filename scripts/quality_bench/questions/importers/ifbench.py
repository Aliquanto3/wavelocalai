"""Importeur d'IFBench (``ifbench``, consignes vérifiables) : 300 prompts EN, données ODC-BY-1.0.

Source : ``allenai/IFBench``, ``data/IFBench_test.jsonl`` (``key``, ``prompt``,
``instruction_id_list``, ``kwargs``). Pas de réponse attendue : les vérificateurs IFBench
(story 4) lisent ``instruction_id_list`` et ``kwargs`` dans les paramètres du correcteur.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...common.jsonl import read_complete_jsonl
from .base import Importer, build_questions
from .remote import RemoteFile

SLUG = "ifbench"
DATA = RemoteFile(
    "github",
    "allenai/IFBench",
    "1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d",
    "data/IFBench_test.jsonl",
    "d2ada7da94a38cfe406351614c4e686846ed2da6d1b339db95fa5ead19554a4a",
)


def convert_instruction_rows(slug: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lignes ``{key, prompt, instruction_id_list, kwargs}`` (IFBench, M-IFEval) en questions."""
    return build_questions(
        slug,
        (
            {
                "number": number,
                "group": f"{slug}/{number:04d}",
                "messages": [{"role": "user", "content": row["prompt"]}],
                "grader_params": {
                    "key": str(row["key"]),
                    "instruction_id_list": row["instruction_id_list"],
                    "kwargs": row["kwargs"],
                },
                "target": None,
            }
            for number, row in enumerate(rows, start=1)
        ),
    )


def convert(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    return convert_instruction_rows(SLUG, read_complete_jsonl(local[DATA.path]))


IMPORTERS = {SLUG: Importer(SLUG, (DATA,), convert)}
