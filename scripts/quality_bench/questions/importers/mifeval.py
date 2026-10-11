"""Importeur de M-IFEval FR (``mifeval-fr``, consignes vérifiables) : 235 prompts, Apache-2.0.

Source : ``lightblue-tech/M-IFEval``, ``data/fr_input_data.jsonl`` (identifiants
d'instruction préfixés ``fr:``), même forme qu'IFBench.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...common.jsonl import read_complete_jsonl
from .base import Importer
from .ifbench import convert_instruction_rows
from .remote import RemoteFile

SLUG = "mifeval-fr"
DATA = RemoteFile(
    "github",
    "lightblue-tech/M-IFEval",
    "10b874dbf8c4ca25ed5d876e1d3226e7f3f9d0dc",
    "data/fr_input_data.jsonl",
    "a7cd5276fe3cad92cfaad444a9bb5f10cd769b0f3858582a8147b495e7e957ce",
)


def convert(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    return convert_instruction_rows(SLUG, read_complete_jsonl(local[DATA.path]))


IMPORTERS = {SLUG: Importer(SLUG, (DATA,), convert)}
