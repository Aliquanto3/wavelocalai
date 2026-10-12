"""Gabarits de prompt du juge et leur empreinte (``prompt_template_hash``, AD-8, AD-16).

- Consigne = messages de la question, rendus ``rôle : contenu`` et séparés par une ligne vide.
- Réponse jugée = contenu verbatim du dernier message ``assistant`` de ``output``, sans
  extraction ni nettoyage (``grading/answer.py`` n'est pas importable depuis ``judge/``).
- Juges LLM (Haiku, MiMo) : une requête par critère, verdict JSON ``{"verdict": booléen}``.
- Contrat ``/v1/systemone`` (Winnow, Decider) : une requête par réponse, un critère par
  question ``noul``.

Les gabarits sont des ``string.Template`` : seul le gabarit est analysé, jamais le texte
substitué (un ``$`` ou une accolade dans une réponse ne change rien).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from string import Template
from typing import Any

from ..common.canonical import sha256_hex

VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"verdict": {"type": "boolean"}},
    "required": ["verdict"],
    "additionalProperties": False,
}

LLM_SYSTEM = (
    "Tu es un évaluateur rigoureux de textes rédigés en français. On te donne une consigne de "
    "rédaction, la réponse d'un modèle à cette consigne et un critère formulé en question "
    "fermée. Décide si la réponse, telle qu'elle est écrite, satisfait ce seul critère. "
    'Réponds uniquement par un objet JSON : {"verdict": true} si le critère est satisfait, '
    '{"verdict": false} sinon, sans autre texte.'
)
LLM_USER = Template(
    "## Consigne\n\n$instruction\n\n"
    "## Réponse à évaluer\n\n$answer\n\n"
    "## Critère\n\n$criterion\n\n"
    'La réponse satisfait-elle ce critère ? Réponds par {"verdict": true} ou '
    '{"verdict": false}.'
)
SYSTEMONE_SYSTEM = (
    "Tu évalues la réponse d'un modèle à une consigne de rédaction en français. Chaque "
    "question porte sur la réponse telle qu'elle est écrite."
)
SYSTEMONE_USER = Template("## Consigne\n\n$instruction\n\n## Réponse à évaluer\n\n$answer")


def render_instruction(messages: Sequence[Mapping[str, Any]]) -> str:
    """Consigne : messages de la question rendus ``rôle : contenu``."""
    return "\n\n".join(f"{message['role']} : {message['content']}" for message in messages)


def final_answer(output: Sequence[Mapping[str, Any]]) -> str:
    """Contenu verbatim du dernier message ``assistant`` (chaîne vide s'il n'y en a aucun)."""
    for message in reversed(output):
        if message.get("role") == "assistant":
            return str(message.get("content") or "")
    return ""


def llm_user(instruction: str, answer: str, criterion: str) -> str:
    return LLM_USER.substitute(instruction=instruction, answer=answer, criterion=criterion)


def systemone_user(instruction: str, answer: str) -> str:
    return SYSTEMONE_USER.substitute(instruction=instruction, answer=answer)


def prompt_template_hash(kind: str) -> str:
    """Empreinte des gabarits qu'emploie un juge de ce ``kind`` (consignée dans le manifeste)."""
    if kind == "systemone":
        templates: dict[str, Any] = {
            "system": SYSTEMONE_SYSTEM,
            "user": SYSTEMONE_USER.template,
            "question_type": "noul",
            "instruction": "role : content, joined by blank lines",
        }
    else:
        templates = {
            "system": LLM_SYSTEM,
            "user": LLM_USER.template,
            "verdict_schema": VERDICT_SCHEMA,
            "instruction": "role : content, joined by blank lines",
        }
    return sha256_hex({"kind": kind, "templates": templates})
