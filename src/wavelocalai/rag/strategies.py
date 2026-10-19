"""Stratégies de recherche HyDE et Self-RAG, et vérification des citations (story 4.6).

Ce module ne contient que des règles pures (prompts, lecture des réponses du modèle, fusion des
extraits, vérification des marqueurs) : aucun appel de modèle, aucune base. Le service
`rag/query.py` les orchestre (appels de modèle en feuilles, étapes `retrieval_step`). Copié puis
adapté de `src/core/rag/strategies/` de la v1 (la v2 n'importe jamais `src.*`).

**HyDE** (`hyde_request`). Le modèle rédige un court passage « tel qu'on le trouverait dans un
document » qui répond à la question ; c'est ce passage, pas la question, qui est vectorisé pour
chercher les extraits. Sans passage (appel en échec, réponse vide), la recherche retombe sur la
question (comme la v1) et l'étape le dit (`fallback`).

**Self-RAG** (`grade_request`, `parse_grade`, `rewrite_request`, `clean_query`, `merge_best`).
Boucle bornée par `rag.self_rag_max_iterations` reformulations : 1. recherche des extraits ; 2. une
seule notation de tous les extraits (une ligne `n : oui` ou `n : non` par extrait) ; 3. s'il en
reste au moins un de pertinent, la boucle s'arrête avec ceux-là ; sinon le modèle reformule la
question et on recommence. Un extrait sans verdict lisible est gardé (le doute profite à
l'extrait) ; une notation illisible ou en échec garde donc tous les extraits (`fallback`). La borne
atteinte, ou une reformulation vide ou inchangée, la réponse part avec **les meilleurs extraits
trouvés** : tous les extraits vus, un par `chunk_id` (la meilleure distance), les `top_k` plus
proches de la question. La v1 rendait une liste vide à la borne ; la story 4.6 demande les meilleurs
extraits.

**Citations** (`verify_citations`). Un marqueur `[n]` de la réponse est vérifié s'il désigne une
source de l'événement `sources` (`n` entre 1 et le nombre de sources). Les autres (`[0]`, `[9]` pour
trois sources) sont inventés par le modèle : ils ne figurent pas dans `citations`. Seul le marqueur
simple `[n]` compte (`[1, 2]` ou `[1][2]` : seul `[1][2]` est lu, deux marqueurs).
"""

from __future__ import annotations

import re
from typing import Any

from wavelocalai.models.port import ChatMessage, ChatRequest

STRATEGIES = ("naive", "hyde", "self_rag")
MAX_TOP_K = 20  # le plafond de `RagSettings.top_k`, aussi celui d'une commande

HYDE_TEMPERATURE = 0.3
HYDE_MAX_TOKENS = 220
GRADE_MAX_TOKENS = 64  # plancher du budget de notation
GRADE_TOKENS_PER_EXCERPT = 8  # « 12 : non » et son retour à la ligne, avec de la marge
GRADE_EXCERPT_CHARS = 600  # un extrait est noté sur ses premiers caractères
REWRITE_MAX_TOKENS = 80
REWRITE_MAX_CHARS = 500

_GRADE_LINE = re.compile(r"(?<!\d)(\d{1,3})\]?\s*[:=.)\-–]?\s*(oui|non|yes|no)\b", re.IGNORECASE)
_MARKER = re.compile(r"\[(\d{1,3})\]")
# Préambule d'un petit modèle avant la reformulation (« Voici la question reformulée : … »).
_PREAMBLE = re.compile(
    r"^(voici|reformulation|question reformul[ée]e|nouvelle (question|formulation)|here is)[^:]{0,60}:\s*",
    re.IGNORECASE,
)


def hyde_request(question: str) -> ChatRequest:
    """Demande d'un passage hypothétique : le texte qui contiendrait la réponse, sans préambule."""
    system = (
        "Tu aides à retrouver des passages dans une base de documents. Rédige en français, en trois "
        "à cinq phrases, le passage qu'on trouverait dans un document pour répondre à la question. "
        "N'écris aucun préambule et ne commente pas : seulement le passage."
    )
    return ChatRequest(
        messages=[ChatMessage("system", system), ChatMessage("user", f"Question : {question}")],
        temperature=HYDE_TEMPERATURE,
        max_tokens=HYDE_MAX_TOKENS,
    )


def grade_request(question: str, found: list[dict[str, Any]]) -> ChatRequest:
    """Demande de notation de tous les extraits d'un coup : une ligne `n : oui` ou `n : non`."""
    system = (
        "Tu évalues si des extraits de documents aident à répondre à une question. Réponds par une "
        "ligne par extrait, au format « numéro : oui » si l'extrait contient de quoi répondre ou s'y "
        "rapporte directement, « numéro : non » sinon. Aucune autre phrase."
    )
    blocks = [
        f"[{rank}]\n{item['text'][:GRADE_EXCERPT_CHARS]}" for rank, item in enumerate(found, 1)
    ]
    # Le gabarit des lignes attendues : sans lui, qwen2.5:1.5b ne note que le premier extrait
    # (« 1 : oui »), et les autres, sans verdict, seraient tous gardés (mesure de la revue 4.6).
    count = len(found)
    template = "\n".join(f"{rank} : oui ou non" for rank in range(1, count + 1))
    user = (
        "Extraits :\n\n"
        + "\n\n".join(blocks)
        + f"\n\nQuestion : {question}"
        + f"\n\nRéponds par exactement {count} lignes, de 1 à {count}, une par extrait :\n"
        + template
    )
    return ChatRequest(
        messages=[ChatMessage("system", system), ChatMessage("user", user)],
        temperature=0.0,
        # Une ligne par extrait : un budget fixe couperait la notation de 20 extraits, et les rangs
        # sans verdict seraient gardés par défaut.
        max_tokens=max(GRADE_MAX_TOKENS, GRADE_TOKENS_PER_EXCERPT * len(found) + 16),
    )


def parse_grade(text: str) -> dict[int, bool]:
    """Les verdicts lisibles d'une notation : `{n: True | False}` (« oui » ou « non »). Un numéro
    sans verdict lisible n'y figure pas ; le premier verdict d'un numéro l'emporte."""
    verdicts: dict[int, bool] = {}
    for number, word in _GRADE_LINE.findall(text):
        verdicts.setdefault(int(number), word.lower() in ("oui", "yes"))
    return verdicts


def rewrite_request(question: str, previous: str) -> ChatRequest:
    """Demande d'une reformulation de la question, différente de la dernière formulation essayée."""
    system = (
        "Tu reformules une question pour mieux retrouver des passages dans une base de documents : "
        "autres mots, termes plus précis, sans changer le sens. Réponds par la seule question "
        "reformulée, sur une ligne."
    )
    user = f"Question d'origine : {question}"
    if previous != question:
        user += f"\nDernière formulation essayée : {previous}"
    user += "\nCette recherche n'a ramené aucun extrait utile. Propose une autre formulation."
    return ChatRequest(
        messages=[ChatMessage("system", system), ChatMessage("user", user)],
        temperature=0.5,
        max_tokens=REWRITE_MAX_TOKENS,
    )


def clean_query(text: str) -> str:
    """Une reformulation propre : première ligne non vide, guillemets de bord et espaces en trop
    retirés, au plus `REWRITE_MAX_CHARS` caractères ; vide si le modèle n'a rien rendu d'utile.
    Un préambule (« Voici la question reformulée : ») est retiré, et une ligne qui n'est que lui
    est sautée."""
    for line in text.splitlines():
        line = " ".join(line.split()).strip("«»\"'“” *")
        line = _PREAMBLE.sub("", line).strip("«»\"'“” *")
        if line:
            return line[:REWRITE_MAX_CHARS]
    return ""


def merge_best(rounds: list[list[dict[str, Any]]], top_k: int) -> list[dict[str, Any]]:
    """Les meilleurs extraits de toutes les recherches : un par `chunk_id` (la plus petite
    distance), du plus proche, au plus `top_k`."""
    best: dict[int, dict[str, Any]] = {}
    for found in rounds:
        for item in found:
            kept = best.get(item["chunk_id"])
            if kept is None or item["distance"] < kept["distance"]:
                best[item["chunk_id"]] = item
    return sorted(best.values(), key=lambda item: item["distance"])[:top_k]


def verify_citations(answer: str, numbers: set[int]) -> list[dict[str, int]]:
    """Les marqueurs `[n]` de la réponse qui désignent une source (`numbers` : les `n` de
    l'événement `sources`), dans l'ordre de première apparition, un par marqueur :
    `{marker, n}`. Un marqueur qui ne désigne aucune source n'y figure pas."""
    seen: list[int] = []
    for found in _MARKER.finditer(answer):
        number = int(found.group(1))
        if number in numbers and number not in seen:
            seen.append(number)
    return [{"marker": number, "n": number} for number in seen]
