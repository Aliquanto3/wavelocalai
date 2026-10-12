"""Candidats synthétiques de la composition de ``set-v1`` (aucune question privée réelle)."""

from __future__ import annotations

from typing import Any

from scripts.quality_bench.common.config import SetConfig, load_set
from scripts.quality_bench.common.paths import PACKAGE_DIR
from scripts.quality_bench.questions.build import build_question
from scripts.quality_bench.questions.generators import var_math
from scripts.quality_bench.questions.schema import REFUSED_SOURCES, SOURCES

SET_V1 = PACKAGE_DIR / "sets" / "set-v1.yaml"


def set_v1() -> SetConfig:
    return load_set(SET_V1, SOURCES, REFUSED_SOURCES)


def synthetic_problems(count: int) -> list[var_math.Problem]:
    """Problèmes VAR-MATH synthétiques (gabarits triviaux, aucun contenu réel)."""
    return var_math.parse_problems(
        {
            "schema": "qb.var_math/1",
            "problems": [
                {
                    "number": number,
                    "text": f"Problème synthétique {number} : {{a}} plus {{b}} ?",
                    "params": {"a": {"min": 1, "max": 50}, "b": {"min": 1, "max": 50}},
                    "constraints": ["a != b"],
                    "answer": "a + b",
                }
                for number in range(1, count + 1)
            ],
        }
    )


def _criteria() -> list[dict[str, str]]:
    return [{"id": f"c{i}", "question": f"Critère synthétique {i} ?"} for i in range(1, 5)]


def synthetic_question(source: str, number: int, group: str | None = None, **extra: Any):
    """Question minimale valide de ``source`` (contenu synthétique)."""
    spec = SOURCES[source]
    fields: dict[str, Any] = {
        "source": source,
        "number": number,
        "group": group or f"{source}/{number:04d}",
        "messages": [{"role": "user", "content": f"Question synthétique {source} {number}"}],
        "grader_params": {},
        "target": None,
    }
    if spec.usage == "writing":
        fields["criteria"] = _criteria()
    if spec.generated:
        fields.update(generator="synthetic@1", generator_seed=0)
    fields.update(extra)
    return build_question(**fields)


def synthetic_candidates(config: SetConfig, spare: int = 2) -> dict[str, list[dict[str, Any]]]:
    """Candidats de chaque source du jeu : ``spare`` fois l'effectif, groupes d'une question,
    sauf ``var-math-fr`` (vrai générateur, groupes de 3), ``piaf`` (groupes de 5) et
    ``tools-fr`` (traductions qui reprennent des groupes de ``bfcl-live``). Les questions de
    ``entry.exclude`` absentes sont ajoutées (numéro tiré du suffixe de l'id), pour que le jeu
    s'assemble."""
    candidates: dict[str, list[dict[str, Any]]] = {}
    for entry in config.sources:
        source, total = entry.source, entry.count * spare
        if source == "var-math-fr":
            problems = synthetic_problems(total // 3 + 1)
            candidates[source] = var_math.generate(problems, entry.generator_seed, 3)
        elif source == "piaf":
            candidates[source] = [
                synthetic_question(source, n, group=f"piaf/{(n - 1) // 5:03d}")
                for n in range(1, total * 5 + 1)
            ]
        elif source == "tools-fr":
            candidates[source] = [
                synthetic_question(source, n, group=f"bfcl-live/{n:04d}")
                for n in range(1, total + 1)
            ]
        else:
            candidates[source] = [synthetic_question(source, n) for n in range(1, total + 1)]
        present = {question["id"] for question in candidates[source]}
        for question_id in entry.exclude:
            if question_id not in present:
                number = int(question_id.rsplit("/", 1)[1])
                candidates[source].append(synthetic_question(source, number))
    return candidates
