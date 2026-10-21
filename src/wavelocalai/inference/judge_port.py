"""Port du juge de l'Arène : ce que `inference/` attend de `evaluation/` (AD-4, AD-5).

`inference/` n'importe pas `evaluation/` (diagramme des couches) : l'Arène reçoit un `LaneJudge`
que l'application câble au démarrage. Un verdict sans note (`score` nul) dit toujours pourquoi ;
« non évalué » n'est jamais 0.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from wavelocalai.models.port import ChatModel

DEFAULT_CRITERIA = ("exactitude", "pertinence", "clarté")  # quand l'appelant n'en donne aucun
NOT_EVALUATED_EMPTY = "non évalué : réponse vide"
NOT_EVALUATED_UNAVAILABLE = "non évalué : juge indisponible"
NOT_EVALUATED_INVALID = "non évalué : sortie du juge invalide"

# Phases de `judge_progress` (story 9.3) dites pendant un appel du juge, dans l'ordre : `loading`
# (chargement du modèle en mémoire, juge local froid seulement), puis `scoring` (le juge lit l'invite
# et génère la note). `queued` (en attente de la place locale) est publié par l'appelant, avant.
JudgePhaseCallback = Callable[[str], None]


@dataclass(frozen=True)
class JudgeVerdict:
    score: int | None  # sur 100 ; `None` : non évalué (jamais 0)
    reason: str  # la justification du juge, ou pourquoi la réponse n'est pas évaluée

    def __post_init__(self) -> None:
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score : entre 0 et 100")


class LaneJudge(Protocol):
    async def score(
        self,
        parent_run_id: str,
        judge: ChatModel,
        question: str,
        criteria: Sequence[str],
        answer: str,
        on_phase: JudgePhaseCallback | None = None,
    ) -> JudgeVerdict:
        """Note `answer` ; ne lève que pour une annulation. Une panne du juge, une sortie invalide
        ou une réponse vide donnent un verdict sans note et sa raison. `on_phase` (story 9.3) reçoit
        `loading` (juge froid) puis `scoring` ; jamais appelé pour une réponse vide (le juge n'est
        pas dérangé) ni pour un juge injoignable avant sa première réponse.
        """
        ...
