"""Le juge de l'Arène : note la réponse d'une lane sur 100, avec sa raison (story 3.3, AD-5, AD-8).

La notation est un run enfant `judge` du run `arena`, mesuré comme toute feuille (AD-10) : un juge
local passe par le sémaphore « Ollama local » à chaque appel (AD-14), un juge cloud part aussitôt.
L'appel est **silencieux** (`stream_into_run(capture=…)`) : ni jetons ni `metrics` dans le flux de
l'Arène, dont les `lane` sont les modèles comparés (le juge peut en être un). Le juge est interrogé
avec `response_schema` (sortie structurée) ; la valeur est relue ici, car un modèle peut ignorer le
schéma.

Une réponse vide, un juge en panne ou une sortie invalide rendent un verdict sans note et sa
raison : jamais 0 pour un inconnu.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from wavelocalai.config import Settings
from wavelocalai.errors import ProviderError
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.chat import cloud_estimator
from wavelocalai.inference.judge_port import (
    DEFAULT_CRITERIA,
    NOT_EVALUATED_EMPTY,
    NOT_EVALUATED_INVALID,
    NOT_EVALUATED_UNAVAILABLE,
    JudgePhaseCallback,
    JudgeVerdict,
)
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import NOT_MEASURED, Guard, stream_into_run
from wavelocalai.models.port import ChatMessage, ChatModel, ChatRequest
from wavelocalai.models.structured import parse_structured
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.system_bus import SystemBus

logger = logging.getLogger("wavelocalai.evaluation")


@dataclass(frozen=True)
class JudgeReply:
    """Réponse brute d'un appel du juge : son texte, ou `None` avec la raison « non évalué »."""

    text: str | None
    reason: str


MAX_ANSWER_CHARS = 12_000  # au-delà, la réponse est tronquée pour le juge (petit contexte)
MAX_REASON_CHARS = 600

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
    "additionalProperties": False,
}

SYSTEM = (
    "Tu es un évaluateur strict et impartial. On te donne une question, des critères de notation "
    "et la réponse d'un assistant. Tu notes la réponse sur 100 selon ces critères seulement : "
    "0 pour une réponse inutilisable, 100 pour une réponse irréprochable. Tu réponds uniquement "
    'par un objet JSON {"score": <entier de 0 à 100>, "reason": "<une ou deux phrases en '
    'français qui justifient la note>"}.'
)


def build_request(question: str, criteria: Sequence[str], answer: str) -> ChatRequest:
    wanted = list(criteria) or list(DEFAULT_CRITERIA)
    shown = answer
    if len(answer) > MAX_ANSWER_CHARS:
        shown = answer[:MAX_ANSWER_CHARS] + "\n[…réponse tronquée]"
    user = (
        f"Question :\n{question}\n\n"
        "Critères de notation :\n" + "\n".join(f"- {c}" for c in wanted) + "\n\n"
        f"Réponse à noter :\n{shown}"
    )
    return ChatRequest(
        [ChatMessage("system", SYSTEM), ChatMessage("user", user)],
        temperature=0.0,
        response_schema=JUDGE_SCHEMA,
    )


def _scoring_phase(on_phase: JudgePhaseCallback | None) -> JudgePhaseCallback | None:
    """Traduit les phases de `stream_into_run` (`loading`, `generating`) en celles de
    `judge_progress` (story 9.3) : `generating` -> `scoring` (le juge travaille, chargé ou non,
    dès la prise de la place ou le départ de l'appel cloud)."""
    if on_phase is None:
        return None
    return lambda phase: on_phase("loading" if phase == "loading" else "scoring")


def verdict_from_text(text: str) -> JudgeVerdict:
    try:
        value = parse_structured(text, JUDGE_SCHEMA)
    except ProviderError:
        return JudgeVerdict(None, NOT_EVALUATED_INVALID)
    reason = str(value["reason"]).strip()[:MAX_REASON_CHARS] or "Aucune justification donnée."
    return JudgeVerdict(int(value["score"]), reason)


class Judge:
    """Service de notation ; une instance par application, câblée à l'Arène (`LaneJudge`)."""

    def __init__(
        self,
        hub: RunHub,
        slot: LocalSlot,
        settings: Settings,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        guard: Guard | None = None,
    ) -> None:
        self._hub = hub
        self._slot = slot
        self._settings = settings
        self._meter = meter  # sans compteur, le CO2 d'un juge local n'est pas mesuré
        self._bus = bus  # sans bus, `carbon_updated` n'est pas publié
        # Garde-fou mémoire d'un juge local (story 4.8) : le juge est choisi à part et se charge
        # après les lanes, moment où la mémoire est la plus entamée. Un refus `ram_guard` rend
        # « non évalué » (juge indisponible), sans charger le modèle ni bloquer l'Arène.
        self._guard = guard

    async def _announce_carbon(self) -> None:
        """`carbon_updated` après chaque feuille (AD-10) : la notation en est une."""
        session_id = self._hub.app_session_id
        if self._bus is not None and session_id is not None:
            await announce_carbon_updated(self._bus, self._hub.store, session_id)

    async def score(
        self,
        parent_run_id: str,
        judge: ChatModel,
        question: str,
        criteria: Sequence[str],
        answer: str,
        on_phase: JudgePhaseCallback | None = None,
    ) -> JudgeVerdict:
        if not answer.strip():
            return JudgeVerdict(None, NOT_EVALUATED_EMPTY)  # inutile de déranger le juge
        reply = await self.ask(
            parent_run_id, judge, build_request(question, criteria, answer), on_phase=on_phase
        )
        if reply.text is None:
            return JudgeVerdict(None, reply.reason)
        return verdict_from_text(reply.text)

    async def ask(
        self,
        parent_run_id: str,
        judge: ChatModel,
        request: ChatRequest,
        on_phase: JudgePhaseCallback | None = None,
    ) -> JudgeReply:
        """Un appel silencieux du juge, en feuille `judge` du run `parent_run_id` : rend le texte de
        sa réponse, ou `text=None` avec la raison « non évalué » (juge indisponible, sortie
        invalide). Ne lève que pour une annulation. Sert la notation de l'Arène (`score`) et celle
        de l'évaluation de la qualité (story 7.1), qui lui passent leurs propres invites.
        `on_phase` (story 9.3) : `loading` puis `scoring`, traduits depuis `stream_into_run`."""
        try:
            leaf = await self._hub.create_run(
                "judge", models=[judge.ref.tag], parent_run_id=parent_run_id
            )
        except ValueError:  # le parent se clôt : le run est annulé, rien à publier
            return JudgeReply(None, NOT_EVALUATED_UNAVAILABLE)
        captured: list[str] = []
        result = await stream_into_run(
            self._hub,
            leaf.run_id,
            judge,
            request,
            secrets=self._settings.secret_values(),
            co2=NOT_MEASURED,
            estimate_co2=cloud_estimator(judge, self._settings),  # juge cloud : ecologits (AD-11)
            slot=self._slot,
            timeout_s=self._settings.delays.lane_timeout_s,
            publish_to=parent_run_id,
            on_phase=_scoring_phase(on_phase),
            meter=self._meter,
            on_leaf_closed=self._announce_carbon,
            capture=captured,
            guard=self._guard,
        )
        if result.status != "ok":
            code = (result.error or {}).get("code")
            logger.warning("Juge %s indisponible (%s)", judge.ref.tag, code)
            if code == "invalid_output":
                return JudgeReply(None, NOT_EVALUATED_INVALID)
            return JudgeReply(None, NOT_EVALUATED_UNAVAILABLE)
        return JudgeReply("".join(captured), "")
