"""Importeur de BBEH mini (``bbeh-mini``, raisonnement) : 460 items, données CC-BY-4.0.

Source : ``google-deepmind/bbeh``, ``bbeh/mini/data.json`` (``{"examples": [{input, target}]}``).
Chaque item est son propre groupe : le fichier ne porte pas l'étiquette de tâche. Le prompt
reprend l'énoncé, suivi d'une consigne de réponse au préfixe « The answer is: », celui que
cherche ``bbeh/evaluate.py``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .base import Importer, build_questions
from .remote import RemoteFile

SLUG = "bbeh-mini"
DATA = RemoteFile(
    "github",
    "google-deepmind/bbeh",
    "80d12ca916b7158f22293fcf3144f4d3d854d4be",
    "bbeh/mini/data.json",
    "14e77b3d6be68faa008d268abf53b1f8d2420ffdd762504a304dafc3f8d43026",
)

ANSWER_SUFFIX = (
    "\n\nThink step by step, and when you provide the final answer, please use the prefix "
    '"The answer is:" without any modification, and provide the answer directly, with no '
    'formatting, no bolding, and no markup. For instance: "The answer is: 42" or "The answer '
    'is: yes". If the question is multiple choice with a single correct answer, the final '
    'answer must only be the letter corresponding to the correct answer. For example, "The '
    'answer is: (a)"'
)


def convert(local: Mapping[str, Path]) -> list[dict[str, Any]]:
    with open(local[DATA.path], encoding="utf-8") as handle:
        examples = json.load(handle)["examples"]
    return build_questions(
        SLUG,
        (
            {
                "number": number,
                "group": f"{SLUG}/{number:04d}",
                "messages": [{"role": "user", "content": example["input"] + ANSWER_SUFFIX}],
                "grader_params": {},
                "target": example["target"],
            }
            for number, example in enumerate(examples, start=1)
        ),
    )


IMPORTERS = {SLUG: Importer(SLUG, (DATA,), convert)}
