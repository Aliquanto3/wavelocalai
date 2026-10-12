"""Interface des juges (AD-16) : ``Judge.judge(items) -> list[Verdict]``, une implémentation
par entrée de ``judges.yaml``, et règle des pannes (AD-13 transposé).

- **Panne du service** (connexion, délai, 429, 5xx ; pour un lot, résultat ``expired``,
  ``canceled`` ou ``errored`` hors ``invalid_request``) : ``TransientError`` ; aucune ligne,
  nouvel essai jusqu'à ``max_attempts``, puis ``JudgeUnavailableError`` (code 1), l'unité
  reste à juger.
- **Échec propre à l'unité**, service vivant (4xx, verdict illisible, refus, troncature) :
  ``UnitError`` ; après ``max_attempts`` essais, ligne ``error`` (``verdict = null``),
  définitive (AD-12).

Les messages d'erreur ne citent jamais de texte de question ni de réponse : statut HTTP, type
d'erreur ou raison rédigée par le banc seulement.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..common.canonical import utc_now
from ..common.schemas import validate

if TYPE_CHECKING:
    from ..common.config import JudgeConfig
    from ..common.jsonl import JsonlAppender
    from ..common.stop import StopFlag
    from .pricing import Budget
    from .units import Unit

logger = logging.getLogger(__name__)


class JudgeError(RuntimeError):
    """Erreur de la phase de jugement (code 1 sauf mention contraire)."""


class JudgeInputError(JudgeError):
    """Entrées incohérentes (manifeste, jeu, ``generation.jsonl``) : rien n'est écrit."""


class JudgeLaunchError(JudgeError):
    """Lancement refusé à l'exploitation (modèle de génération chargé, requête de lot refusée)."""


class JudgeUnavailableError(JudgeError):
    """Service toujours en panne après ``max_attempts`` essais : aucune ligne, unités à juger."""


class PrivateQuestionError(JudgeError):
    """Unité portant sur une question privée pour un juge cloud : rien n'est envoyé (AD-15)."""


class CostCapError(JudgeError):
    """Plafond ``--max-cost-usd`` atteint avant un envoi : aucun appel de plus (code 3)."""


class TransientError(Exception):
    """Un essai a échoué par panne du service (aucune ligne)."""


class UnitError(Exception):
    """Un essai a échoué pour cette unité, service vivant (ligne ``error`` au dernier essai).

    ``tokens`` et ``cost_usd`` : consommation facturée de l'essai malgré l'échec."""

    def __init__(self, reason: str, tokens: tuple[int, int] = (0, 0), cost_usd: float = 0.0):
        self.reason = reason
        self.tokens = tokens
        self.cost_usd = cost_usd
        super().__init__(reason)


@dataclass(frozen=True)
class Verdict:
    """Verdict d'une unité : booléen, ou ``None`` avec une erreur."""

    key: str
    verdict: bool | None
    probability: float | None
    tokens: tuple[int, int]
    cost_usd: float
    attempts: int
    error: str | None = None


@dataclass
class Session:
    """Ce que partage la boucle d'un lancement : écrivain de ``judgment.jsonl``, empreinte du
    manifeste, arrêt, plafond, attente (injectée par les tests)."""

    judge_id: str
    manifest_hash: str
    writer: JsonlAppender
    stop: StopFlag
    budget: Budget
    sleep: Callable[[float], None]
    batches: JsonlAppender | None = None
    written: int = 0
    errors: int = 0

    def write(self, unit: Unit, verdict: Verdict) -> None:
        """Écrit la ligne ``qb.judgment/1`` d'une unité, validée avant écriture."""
        record = {
            "schema": "qb.judgment/1",
            "key": unit.key,
            "generation_key": unit.generation_key,
            "manifest": self.manifest_hash,
            "criterion": unit.criterion,
            "judge": self.judge_id,
            "verdict": verdict.verdict,
            "probability": verdict.probability,
            "tokens": {"input": verdict.tokens[0], "output": verdict.tokens[1]},
            "cost_usd": verdict.cost_usd,
            "attempts": verdict.attempts,
            "error": verdict.error,
            "created_at": utc_now(),
        }
        validate(record)
        self.writer.append(record)
        self.written += 1
        if verdict.error is not None:
            self.errors += 1
            logger.warning(
                "%s : erreur du juge après %d essai(s) (%s)",
                unit.key,
                verdict.attempts,
                verdict.error,
            )


def split_int(total: int, parts: int) -> list[int]:
    """Répartit un entier sur ``parts`` lignes (le reste sur les premières) : somme conservée."""
    base, rest = divmod(total, parts)
    return [base + (1 if index < rest else 0) for index in range(parts)]


class Judge:
    """Juge synchrone : ``judge(items)`` juge un groupe d'unités (une requête), avec essais.

    ``run`` parcourt les groupes, lit l'arrêt entre deux groupes, vérifie le plafond avant
    chaque envoi d'un juge cloud et écrit les verdicts. Haiku (lots) redéfinit ``run``."""

    def __init__(self, config: JudgeConfig, sleep: Callable[[float], None]) -> None:
        self.config = config
        self.sleep = sleep
        self.max_attempts: int = config.options["max_attempts"]
        self.retry_wait_s: float = config.options["retry_wait_s"]

    # -- À fournir par chaque juge -----------------------------------------------------------

    def groups(self, units: Sequence[Unit]) -> list[list[Unit]]:
        """Unités envoyées ensemble (une requête) ; une par unité par défaut."""
        return [[unit] for unit in units]

    def estimate(self, items: Sequence[Unit]) -> float:
        """Estimation prudente du coût d'une requête (0 pour un juge local)."""
        return 0.0

    def attempt(self, items: Sequence[Unit]) -> list[Verdict]:
        """Un essai : verdicts (``attempts`` ignoré), ou ``TransientError``/``UnitError``."""
        raise NotImplementedError

    def close(self) -> None:
        """Libère le client (fin de lancement)."""

    # -- Mécanique commune -------------------------------------------------------------------

    def judge(self, items: Sequence[Unit], budget: Budget | None = None) -> list[Verdict]:
        """Juge un groupe avec au plus ``max_attempts`` essais (voir la docstring du module).

        ``budget`` (juge cloud) : vérifié avant **chaque** essai (estimation de l'essai) et
        débité de chaque essai facturé, réussi ou non ; ``CostCapError`` sans envoi."""
        tokens_in = tokens_out = 0
        cost = 0.0
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            if budget is not None and self.config.cloud:
                budget.check(self.estimate(items))
            try:
                verdicts = self.attempt(items)
            except TransientError as exc:
                last = exc
            except UnitError as exc:
                last = exc
                tokens_in += exc.tokens[0]
                tokens_out += exc.tokens[1]
                cost += exc.cost_usd
                if budget is not None:
                    budget.spend(exc.cost_usd)
            else:
                if budget is not None:
                    budget.spend(sum(v.cost_usd for v in verdicts))
                # Consommation des essais échoués : répartie sur les lignes du groupe.
                extra_in = split_int(tokens_in, len(verdicts))
                extra_out = split_int(tokens_out, len(verdicts))
                return [
                    Verdict(
                        key=v.key,
                        verdict=v.verdict,
                        probability=v.probability,
                        tokens=(v.tokens[0] + extra_in[i], v.tokens[1] + extra_out[i]),
                        cost_usd=v.cost_usd + cost / len(verdicts),
                        attempts=attempt,
                        error=None,
                    )
                    for i, v in enumerate(verdicts)
                ]
            if attempt < self.max_attempts:
                wait = self.retry_wait_s * 2 ** (attempt - 1)
                logger.info(
                    "%s : essai %d/%d échoué (%s), nouvel essai dans %g s",
                    items[0].generation_key,
                    attempt,
                    self.max_attempts,
                    last,
                    wait,
                )
                self.sleep(wait)
        if isinstance(last, TransientError):
            billed = (
                f" ; {cost:.6f} $ facturés par les essais échoués de ce groupe, sans ligne"
                if cost
                else ""
            )
            raise JudgeUnavailableError(
                f"juge {self.config.id} en panne après {self.max_attempts} essai(s) ({last}) : "
                "aucune ligne écrite pour l'unité en cours, reprise par la même commande"
                f"{billed}"
            )
        reason = last.reason if isinstance(last, UnitError) else str(last)
        ins = split_int(tokens_in, len(items))
        outs = split_int(tokens_out, len(items))
        return [
            Verdict(
                key=unit.key,
                verdict=None,
                probability=None,
                tokens=(ins[i], outs[i]),
                cost_usd=cost / len(items),
                attempts=self.max_attempts,
                error=reason,
            )
            for i, unit in enumerate(items)
        ]

    def run(self, units: Sequence[Unit], session: Session) -> bool:
        """Juge les unités ; ``False`` après un arrêt propre (``STOP`` ou Ctrl+C)."""
        for group in self.groups(units):
            if session.stop.should_stop():
                return False
            verdicts = self.judge(group, session.budget)  # plafond vérifié avant chaque essai
            by_key = {verdict.key: verdict for verdict in verdicts}
            for unit in group:
                session.write(unit, by_key[unit.key])
        return True


def parse_verdict(text: str) -> bool:
    """Verdict d'un juge LLM : objet JSON ``{"verdict": booléen}`` (clôture Markdown tolérée) ;
    ``UnitError`` sinon, sans citer le texte."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        payload: Any = json.loads(cleaned)
    except ValueError:
        raise UnitError("verdict illisible (JSON invalide)") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("verdict"), bool):
        raise UnitError("verdict illisible (booléen « verdict » absent)")
    return payload["verdict"]
