"""Invites et lecture des sorties du juge pour l'évaluation de la qualité (story 7.1, AD-8).

Méthode inspirée de Ragas, sans sa bibliothèque (juge maison, sans LangChain) :

- **fidélité** : le juge découpe la réponse en affirmations (`claims`), puis vérifie chacune contre
  les extraits (`verdict`) ; le score est la part d'affirmations appuyées ;
- **pertinence** : le juge retrouve des questions à partir de la réponse seule ; le score est la
  proximité (cosinus moyen, `scoring.py`) entre la question posée et ces questions ;
- **précision du contexte** : le juge dit quels extraits servent à répondre.

Chaque appel passe par `response_schema` (sortie structurée) ; la valeur est relue ici, car un
modèle peut ignorer le schéma : une sortie inutilisable lève `ProviderError("invalid_output")`, que
le service traduit en « non évalué : sortie du juge invalide », jamais en 0.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from wavelocalai.models.port import ChatMessage, ChatRequest
from wavelocalai.models.structured import parse_structured

SUPPORTED = "appuyée"
UNSUPPORTED = "non appuyée"
CONTRADICTED = "contredite"
VERDICTS = (SUPPORTED, UNSUPPORTED, CONTRADICTED)

MAX_CLAIMS = 10  # au-delà, les premières affirmations seules sont vérifiées (un appel chacune)
MAX_CLAIM_CHARS = 400
RELEVANCE_QUESTIONS = 3  # questions retrouvées depuis la réponse
MAX_QUESTION_CHARS = 300
MAX_REASON_CHARS = 600
MAX_ANSWER_CHARS = (
    12_000  # comme le juge de l'Arène : la réponse est tronquée pour un petit contexte
)

CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {"type": "string"}}},
    "required": ["claims"],
    "additionalProperties": False,
}
VERDICT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(VERDICTS)},
        "support": {"type": ["integer", "null"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "support", "reason"],
    "additionalProperties": False,
}
QUESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "string"}}},
    "required": ["questions"],
    "additionalProperties": False,
}
USEFUL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "useful": {"type": "array", "items": {"type": "integer"}},
        "reason": {"type": "string"},
    },
    "required": ["useful", "reason"],
    "additionalProperties": False,
}

CLAIMS_SYSTEM = (
    "Tu décomposes la réponse d'un assistant en affirmations simples. Chaque affirmation dit une "
    "seule chose, tient en une phrase autonome (pas de « il », « elle » ou « cela » sans sujet "
    "nommé) et peut être vérifiée seule. Tu ignores les marqueurs de citation comme [1]. Tu ne "
    "corriges rien et tu n'ajoutes rien : tu restes fidèle à la réponse. Tu réponds uniquement par "
    'un objet JSON {"claims": ["<affirmation>", ...]}.'
)
VERDICT_SYSTEM = (
    "Tu vérifies une affirmation contre des extraits de documents numérotés, et contre eux seuls : "
    "jamais d'après tes connaissances. Verdict « appuyée » : un extrait dit ou implique "
    "directement l'affirmation. Verdict « contredite » : un extrait dit le contraire. Verdict "
    "« non appuyée » : aucun extrait ne permet de conclure. `support` est le numéro de l'extrait "
    "qui l'appuie ou la contredit, `null` pour « non appuyée ». Tu réponds uniquement par un objet "
    'JSON {"verdict": "appuyée" | "non appuyée" | "contredite", "support": <numéro ou null>, '
    '"reason": "<une phrase en français>"}.'
)
QUESTIONS_SYSTEM = (
    f"À partir de la seule réponse d'un assistant, tu retrouves {RELEVANCE_QUESTIONS} questions "
    "différentes auxquelles cette réponse répond. Tu les rédiges en français, sans les recopier de "
    'la réponse. Tu réponds uniquement par un objet JSON {"questions": ["<question>", ...]}.'
)
USEFUL_SYSTEM = (
    "On te donne une question, la réponse d'un assistant et des extraits de documents numérotés. "
    "Tu indiques les numéros des extraits qui servent à répondre à la question (dont la réponse "
    "reprend ou prolonge le contenu), et tu écartes les autres. Tu réponds uniquement par un objet "
    'JSON {"useful": [<numéros>], "reason": "<une phrase en français>"}.'
)


def _shown(answer: str) -> str:
    if len(answer) > MAX_ANSWER_CHARS:
        return answer[:MAX_ANSWER_CHARS] + "\n[…réponse tronquée]"
    return answer


def format_sources(sources: Sequence[dict[str, Any]]) -> str:
    """Les extraits numérotés comme dans l'invite de la réponse (`rag/query.py::build_request`)."""
    blocks = []
    for source in sources:
        where = source["document"] + (f", page {source['page']}" if source.get("page") else "")
        blocks.append(f"[{source['n']}] ({where})\n{source['text']}")
    return "\n\n".join(blocks)


def _request(system: str, user: str, schema: dict[str, Any]) -> ChatRequest:
    return ChatRequest(
        [ChatMessage("system", system), ChatMessage("user", user)],
        temperature=0.0,
        response_schema=schema,
    )


def claims_request(question: str, answer: str) -> ChatRequest:
    user = f"Question :\n{question}\n\nRéponse à décomposer :\n{_shown(answer)}"
    return _request(CLAIMS_SYSTEM, user, CLAIMS_SCHEMA)


def verdict_request(claim: str, sources: Sequence[dict[str, Any]]) -> ChatRequest:
    user = f"Extraits :\n\n{format_sources(sources)}\n\nAffirmation à vérifier :\n{claim}"
    return _request(VERDICT_SYSTEM, user, VERDICT_SCHEMA)


def questions_request(answer: str) -> ChatRequest:
    return _request(QUESTIONS_SYSTEM, f"Réponse :\n{_shown(answer)}", QUESTIONS_SCHEMA)


def useful_request(question: str, answer: str, sources: Sequence[dict[str, Any]]) -> ChatRequest:
    user = (
        f"Question :\n{question}\n\nRéponse de l'assistant :\n{_shown(answer)}\n\n"
        f"Extraits :\n\n{format_sources(sources)}"
    )
    return _request(USEFUL_SYSTEM, user, USEFUL_SCHEMA)


def _clean(texts: Sequence[str], limit: int, size: int) -> list[str]:
    """Textes nettoyés : sans vide ni doublon (ordre gardé), tronqués à `size`, au plus `limit`."""
    seen: dict[str, None] = {}
    for text in texts:
        cleaned = " ".join(str(text).split())[:size]
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)[:limit]


def parse_claims(text: str) -> list[str]:
    """Les affirmations de la réponse (liste vide : le juge n'en a trouvé aucune)."""
    value = parse_structured(text, CLAIMS_SCHEMA)
    return _clean(value["claims"], MAX_CLAIMS, MAX_CLAIM_CHARS)


def parse_verdict(text: str, source_count: int) -> dict[str, Any]:
    """`{verdict, support, reason}` d'une affirmation. `support` hors de la liste des extraits (ou
    donné avec « non appuyée ») devient `None` : le verdict du juge reste tel qu'il l'a rendu."""
    value = parse_structured(text, VERDICT_SCHEMA)
    support = value["support"]
    valid = isinstance(support, int) and 1 <= support <= source_count
    return {
        "verdict": value["verdict"],
        "support": support if valid and value["verdict"] != UNSUPPORTED else None,
        "reason": str(value["reason"]).strip()[:MAX_REASON_CHARS],
    }


def parse_questions(text: str) -> list[str]:
    """Les questions retrouvées depuis la réponse (liste vide : aucune exploitable)."""
    value = parse_structured(text, QUESTIONS_SCHEMA)
    return _clean(value["questions"], RELEVANCE_QUESTIONS, MAX_QUESTION_CHARS)


def parse_useful(text: str, source_count: int) -> tuple[list[int], str]:
    """Numéros des extraits utiles (sans doublon, de 1 à `source_count`, dans l'ordre) et la raison.
    Une liste vide est une vraie note : aucun extrait ne sert (0 sur 100)."""
    value = parse_structured(text, USEFUL_SCHEMA)
    numbers = sorted({n for n in value["useful"] if 1 <= n <= source_count})
    return numbers, str(value["reason"]).strip()[:MAX_REASON_CHARS]
