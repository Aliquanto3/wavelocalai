"""Consignes vérifiables : ``ifbench`` (IFBench) et ``mifeval_fr`` (M-IFEval FR).

Boucle « strict » des deux projets amont (``test_instruction_following_strict``) : pour chaque
consigne, ``build_description`` avec ses ``kwargs`` (valeurs ``None`` retirées, comme IFBench),
prompt réinjecté si le vérificateur le demande (``content`` du dernier message ``user`` de
``messages``), puis ``check_following`` sur la réponse finale ; une réponse vide n'en suit
aucune. ``success`` = toutes suivies ; ``metrics.instructions_followed`` = part suivie.

Le hasard global (``random``, tiré par certains ``build_description`` pour les paramètres
absents) est fixé à 0 puis restauré autour des vérificateurs ; les données NLTK sont celles du
banc (``nlp.bench_data``, ``nltk.data.path`` restauré ensuite). Un identifiant de consigne
inconnu ou une exception d'un vérificateur emprunté sont des erreurs du banc, jamais un échec du
modèle.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Mapping
from typing import Any

from .answer import final_answer
from .base import Grade, bench_error, from_success
from .nlp import bench_data
from .vendored.ifbench.instructions_registry import INSTRUCTION_DICT as IFBENCH_INSTRUCTIONS
from .vendored.mifeval_fr.instructions_registry import INSTRUCTION_DICT as MIFEVAL_FR_INSTRUCTIONS

RANDOM_SEED = 0


def _last_user_content(question: Mapping[str, Any]) -> str | None:
    for message in reversed(question["messages"]):
        if message["role"] == "user":
            return message["content"]
    return None


def _follow(registry: Mapping[str, Any], question: Mapping[str, Any], response: str) -> Grade:
    params = question["grader"]["params"]
    ids = params.get("instruction_id_list")
    kwargs_list = params.get("kwargs")
    if (
        not isinstance(ids, list)
        or not isinstance(kwargs_list, list)
        or len(ids) != len(kwargs_list)
        or not ids
    ):
        return bench_error("instruction_id_list et kwargs absents ou désalignés")
    prompt = _last_user_content(question)
    state = random.getstate()
    followed: list[bool] = []
    try:
        with bench_data():
            random.seed(RANDOM_SEED)
            for instruction_id, kwargs in zip(ids, kwargs_list, strict=True):
                instruction_class = registry.get(instruction_id)
                if instruction_class is None:
                    return bench_error(f"identifiant de consigne inconnu : {instruction_id}")
                if kwargs is not None and not isinstance(kwargs, Mapping):
                    return bench_error(f"kwargs illisibles pour {instruction_id}")
                arguments = {
                    key: copy.deepcopy(value)
                    for key, value in (kwargs or {}).items()
                    if value is not None
                }
                try:
                    instruction = instruction_class(instruction_id)
                    instruction.build_description(**arguments)
                    description_args = instruction.get_instruction_args()
                    if description_args and "prompt" in description_args:
                        instruction.build_description(prompt=prompt)
                    is_following = bool(response.strip()) and bool(
                        instruction.check_following(response)
                    )
                except (
                    Exception
                ) as exc:  # noqa: BLE001 (vérificateur emprunté en défaut : erreur du banc)
                    return bench_error(
                        f"vérificateur {instruction_id} en défaut ({type(exc).__name__})"
                    )
                followed.append(is_following)
    finally:
        random.setstate(state)
    share = sum(followed) / len(followed)
    return from_success(all(followed), {"instructions_followed": share})


def ifbench(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    return _follow(IFBENCH_INSTRUCTIONS, question, final_answer(generation).text)


def mifeval_fr(
    question: Mapping[str, Any], generation: Mapping[str, Any], verdicts: Any = None
) -> Grade:
    return _follow(MIFEVAL_FR_INSTRUCTIONS, question, final_answer(generation).text)
