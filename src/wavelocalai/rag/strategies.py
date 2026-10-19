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

**Reclassement** (`rerank_pool`, `rerank_top`, story 4.7). Quand un reranker local est là, chaque
recherche (toute stratégie) prend `RERANK_POOL_FACTOR` fois plus de candidats que `top_k`, puis le
reranker les note **contre la question de l'utilisateur** (jamais contre l'hypothèse de HyDE ni une
reformulation) et seuls les `top_k` meilleurs restent. Sans reranker, rien ne change.

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
GRADE_MAX_TOKENS = 64
GRADE_EXCERPT_CHARS = 600  # un extrait est noté sur ses premiers caractères
REWRITE_MAX_TOKENS = 80
REWRITE_MAX_CHARS = 500
RERANK_POOL_FACTOR = 3  # candidats cherchés par extrait gardé quand un reranker reclassera
RERANK_POOL_MAX = 60  # plafond du nombre de candidats reclassés (CPU)

_GRADE_LINE = re.compile(r"(?<!\d)(\d{1,3})\]?\s*[:=.)\-–]?\s*(oui|non|yes|no)\b", re.IGNORECASE)
_MARKER = re.compile(r"\[(\d{1,3})\]")


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
    user = "Extraits :\n\n" + "\n\n".join(blocks) + f"\n\nQuestion : {question}"
    return ChatRequest(
        messages=[ChatMessage("system", system), ChatMessage("user", user)],
        temperature=0.0,
        max_tokens=GRADE_MAX_TOKENS,
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
    retirés, au plus `REWRITE_MAX_CHARS` caractères ; vide si le modèle n'a rien rendu d'utile."""
    for line in text.splitlines():
        line = " ".join(line.split()).strip("«»\"'“” ")
        if line:
            return line[:REWRITE_MAX_CHARS]
    return ""


def rerank_pool(top_k: int) -> int:
    """Combien de candidats chercher quand un reranker reclassera : `RERANK_POOL_FACTOR` fois les
    extraits gardés, au plus `RERANK_POOL_MAX` (jamais moins que `top_k`)."""
    return max(top_k, min(top_k * RERANK_POOL_FACTOR, RERANK_POOL_MAX))


def rerank_top(
    found: list[dict[str, Any]], scores: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Les `top_k` meilleurs candidats selon `scores` (le plus grand d'abord ; à égalité, le plus
    proche par la distance), chacun avec son `rerank_score` (4 décimales). `found` et `scores` ont
    la même longueur ; `distance` reste celle des vecteurs (libellé de pertinence, score brut)."""
    scored = [
        {**item, "rerank_score": round(float(score), 4)}
        for item, score in zip(found, scores, strict=True)
    ]
    scored.sort(key=lambda item: (-item["rerank_score"], item["distance"]))
    return scored[:top_k]


def merge_best(rounds: list[list[dict[str, Any]]], top_k: int) -> list[dict[str, Any]]:
    """Les meilleurs extraits de toutes les recherches : un par `chunk_id`, au plus `top_k`. Si
    tous ont un `rerank_score` (même question à chaque tour, scores comparables), le meilleur score
    de chacun et le plus grand d'abord ; sinon la plus petite distance et le plus proche."""
    items = [item for found in rounds for item in found]
    reranked = bool(items) and all("rerank_score" in item for item in items)

    def rank(item: dict[str, Any]) -> tuple[float, float]:
        return (-item["rerank_score"] if reranked else 0.0, item["distance"])

    best: dict[int, dict[str, Any]] = {}
    for item in items:
        kept = best.get(item["chunk_id"])
        if kept is None or rank(item) < rank(kept):
            best[item["chunk_id"]] = item
    return sorted(best.values(), key=rank)[:top_k]


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
