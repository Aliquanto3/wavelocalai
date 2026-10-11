"""Importeur de PIAF (``piaf``, RAG FR) : 3 835 questions au format SQuAD v1, MIT.

Source : ``etalab-ia/piaf-code``, ``piaf-v1.0.json``. Les questions d'un même paragraphe
partagent un groupe ; la cible est la liste des réponses admises (correspondance exacte
normalisée et F1, story 4).
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from .base import Importer, build_questions
from .remote import RemoteFile

SLUG = "piaf"
DATA = RemoteFile(
    "github",
    "etalab-ia/piaf-code",
    "86948a73b26498948e70ad92e4b9b0231eac81f7",
    "piaf-v1.0.json",
    "008229ccefa0195d7e809d777d33149cab03433059c9477bdbadb4838a277cd2",
)

PROMPT = (
    "Lis le contexte, puis réponds à la question par un extrait exact du contexte, le plus "
    "court possible, sans phrase d'introduction.\n\nContexte :\n{context}\n\nQuestion : {question}"
)


def convert(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    with open(local[DATA.path], encoding="utf-8") as handle:
        articles = json.load(handle)["data"]
    return build_questions(SLUG, _items(articles))


def _items(articles: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    number = 0
    for article_index, article in enumerate(articles, start=1):
        for paragraph_index, paragraph in enumerate(article["paragraphs"], start=1):
            group = f"{SLUG}/{article_index:03d}-{paragraph_index:03d}"
            for qa in paragraph["qas"]:
                number += 1
                answers = list(dict.fromkeys(answer["text"] for answer in qa["answers"]))
                prompt = PROMPT.format(context=paragraph["context"], question=qa["question"])
                yield {
                    "number": number,
                    "group": group,
                    "messages": [{"role": "user", "content": prompt}],
                    "grader_params": {},
                    "target": answers,
                }


IMPORTERS = {SLUG: Importer(SLUG, (DATA,), convert)}
