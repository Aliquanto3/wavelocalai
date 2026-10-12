"""Claude Haiku 5.5 par Message Batches du SDK ``anthropic`` (AD-16).

Chaque requête du lot : ``model``, ``max_tokens``, ``output_config = {effort, format:
json_schema {verdict: boolean}}``, ``thinking`` selon ``judges.yaml`` ; ni ``temperature``, ni
``top_p``, ni ``top_k``, ni préremplissage (refusés par l'API). Une requête par critère ;
``custom_id`` = index dans le lot.

``batches.jsonl`` (ajout seul, ``qb.batch/1``) :
- ligne ``submitted`` (identifiant du lot, clés de jugement dans l'ordre des ``custom_id``,
  estimation) écrite **avant** toute attente ;
- ligne ``collected`` (comptes, tokens, coût réel, issue de chaque clé) écrite après les lignes
  de jugement du lot.

Reprise : un lot ``submitted`` sans ``collected`` est relu (``retrieve`` puis ``results``),
jamais resoumis ni annulé. ``attempts`` d'une clé = nombre de lots ``submitted`` qui la
contiennent. Issue d'une clé :
- ``ok`` : verdict lu, ligne écrite ;
- ``transient`` (``expired``, ``canceled``, ``errored`` hors ``invalid_request_error``, résultat
  absent) : aucune ligne, clé resoumise jusqu'à ``max_attempts``, puis sortie code 1 ;
- ``unit`` (``errored`` ``invalid_request_error``, refus, troncature, verdict illisible) : ligne
  ``error`` au ``max_attempts``-ième lot.

Coût : usage renvoyé × prix du YAML × (1 − remise de lot), palier de contexte long par requête.
Le plafond porte sur les lots soumis par ce lancement (un lot repris a été payé avant).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import anthropic

from ..common.canonical import utc_now
from ..common.config import JudgeConfig
from ..common.jsonl import read_jsonl
from ..common.schemas import SchemaValidationError, UnknownSchemaError, validate
from .base import (
    Judge,
    JudgeError,
    JudgeLaunchError,
    JudgeUnavailableError,
    Session,
    TransientError,
    UnitError,
    Verdict,
    parse_verdict,
)
from .pricing import estimate_cost, request_cost
from .prompt import LLM_SYSTEM, VERDICT_SCHEMA, llm_user
from .units import Unit

logger = logging.getLogger(__name__)

TRANSIENT_RESULTS = ("expired", "canceled")
UNIT_ERROR_TYPES = ("invalid_request_error",)


def make_client(config: JudgeConfig, api_key: str) -> anthropic.Anthropic:
    """Client ``anthropic`` sans relance automatique (le banc compte les essais)."""
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=config.endpoint,
        max_retries=0,
        timeout=config.options["timeout_s"],
    )


class HaikuJudge(Judge):
    def __init__(
        self, config: JudgeConfig, sleep: Callable[[float], None], client: anthropic.Anthropic
    ) -> None:
        super().__init__(config, sleep)
        self.client = client
        self.poll_s: float = config.options["poll_s"]
        self.batch_size: int = config.options["batch_size"]

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if close is not None:
            close()

    # -- Requêtes ----------------------------------------------------------------------------

    def params(self, unit: Unit) -> dict[str, Any]:
        options = self.config.options
        params: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": options["max_tokens"],
            "system": LLM_SYSTEM,
            "messages": [
                {
                    "role": "user",
                    "content": llm_user(unit.instruction, unit.answer, unit.criterion_question),
                }
            ],
            "output_config": {
                "effort": options["effort"],
                "format": {"type": "json_schema", "schema": VERDICT_SCHEMA},
            },
        }
        if options["thinking"] is not None:
            params["thinking"] = dict(options["thinking"])
        return params

    def estimate(self, items: Sequence[Unit]) -> float:
        total = 0.0
        for unit in items:
            params = self.params(unit)
            chars = len(params["system"]) + len(params["messages"][0]["content"])
            total += estimate_cost(
                self.config.prices,
                chars,
                params["max_tokens"],
                self.config.options["chars_per_token"],
                batch=True,
            )
        return total

    # -- Appels de l'API, avec essais sur panne passagère -------------------------------------

    def _call(self, what: str, function: Callable[[], Any], *, retry: bool = True) -> Any:
        """Appel de l'API ; ``retry=False`` pour une soumission (non idempotente : un lot créé
        dont la réponse s'est perdue serait payé deux fois)."""
        last: TransientError | None = None
        attempts = self.max_attempts if retry else 1
        for attempt in range(1, attempts + 1):
            try:
                return function()
            except anthropic.APIConnectionError as exc:
                last = TransientError(f"{what} : service injoignable ({type(exc).__name__})")
            except anthropic.APIStatusError as exc:
                if exc.status_code == 429 or exc.status_code >= 500:
                    last = TransientError(f"{what} : statut {exc.status_code}")
                else:
                    raise JudgeLaunchError(
                        f"{what} refusé par l'API (statut {exc.status_code})"
                    ) from None
            if attempt < attempts:
                self.sleep(self.retry_wait_s * 2 ** (attempt - 1))
        if not retry:
            raise JudgeUnavailableError(
                f"juge {self.config.id} : {last} ; soumission non relancée (un lot a pu être "
                "créé sans réponse : le vérifier dans la console Anthropic avant de relancer)"
            )
        raise JudgeUnavailableError(
            f"juge {self.config.id} en panne après {attempts} essai(s) ({last})"
        )

    # -- Historique des lots -----------------------------------------------------------------

    @staticmethod
    def _history(session: Session) -> list[dict[str, Any]]:
        assert session.batches is not None
        lines = read_jsonl(session.batches.path)
        for line_no, line in enumerate(lines, start=1):
            try:
                validate(line)
            except (SchemaValidationError, UnknownSchemaError) as exc:
                raise JudgeError(f"batches.jsonl ligne {line_no} : hors schéma ({exc})") from None
            if line["judge"] != session.judge_id or line["manifest"] != session.manifest_hash:
                raise JudgeError("batches.jsonl : lot d'un autre juge ou d'un autre manifeste")
        return lines

    @classmethod
    def _attempts(cls, history: Sequence[Mapping[str, Any]]) -> Counter[str]:
        return Counter(
            key for line in history if line["status"] == "submitted" for key in line["keys"]
        )

    @staticmethod
    def _last_outcomes(history: Sequence[Mapping[str, Any]]) -> dict[str, str]:
        outcomes: dict[str, str] = {}
        for line in history:
            if line["status"] == "collected":
                outcomes.update(line["outcomes"])
        return outcomes

    # -- Boucle ------------------------------------------------------------------------------

    def run(self, units: Sequence[Unit], session: Session) -> bool:
        by_key = {unit.key: unit for unit in units}
        history = self._history(session)
        collected = {line["batch_id"] for line in history if line["status"] == "collected"}
        for line in history:
            if line["status"] == "submitted" and line["batch_id"] not in collected:
                logger.info(
                    "Lot %s en attente à la reprise : relu, jamais resoumis", line["batch_id"]
                )
                if not self._collect(line, by_key, session, paid_here=False):
                    return False
        # Pannes passagères : max_attempts lots par clé et par lancement (une relance repart à
        # zéro et ne bloque pas) ; échecs propres à l'unité : comptés sur tout batches.jsonl.
        submitted_here: Counter[str] = Counter()
        while True:
            history = self._history(session)
            attempts = self._attempts(history)
            outcomes = self._last_outcomes(history)
            exhausted = []
            for key, unit in by_key.items():
                if key in session.writer:
                    continue
                if outcomes.get(key) == "unit" and attempts[key] >= self.max_attempts:
                    session.write(
                        unit, _error_verdict(key, attempts[key], "échec propre à l'unité")
                    )
                elif submitted_here[key] >= self.max_attempts:
                    exhausted.append(key)
            if exhausted:
                raise JudgeUnavailableError(
                    f"juge {self.config.id} : {len(exhausted)} clé(s) sans résultat après "
                    f"{self.max_attempts} lot(s) (lots expirés, annulés ou en erreur) ; aucune "
                    "ligne pour elles"
                )
            pending = [key for key in by_key if key not in session.writer]
            if not pending:
                return True
            if session.stop.should_stop():
                return False
            chunk = [by_key[key] for key in pending[: self.batch_size]]
            estimate = self.estimate(chunk)
            session.budget.check(estimate)
            requests = [
                {"custom_id": str(index), "params": self.params(unit)}
                for index, unit in enumerate(chunk)
            ]
            batch = self._call(
                "soumission du lot",
                lambda requests=requests: self.client.messages.batches.create(requests=requests),
                retry=False,
            )
            submitted_here.update(unit.key for unit in chunk)
            submitted = {
                "schema": "qb.batch/1",
                "key": f"{batch.id}|submitted",
                "batch_id": batch.id,
                "judge": session.judge_id,
                "manifest": session.manifest_hash,
                "status": "submitted",
                "keys": [unit.key for unit in chunk],
                "estimate_usd": estimate,
                "created_at": utc_now(),
            }
            validate(submitted)
            assert session.batches is not None
            session.batches.append(submitted)
            logger.info(
                "Lot %s soumis : %d requête(s), estimation %.4f $", batch.id, len(chunk), estimate
            )
            if not self._collect(submitted, by_key, session, paid_here=True):
                return False

    def _collect(
        self,
        submitted: Mapping[str, Any],
        by_key: Mapping[str, Unit],
        session: Session,
        *,
        paid_here: bool,
    ) -> bool:
        """Attend la fin du lot, lit ses résultats, écrit les lignes puis ``collected`` ;
        ``False`` si l'arrêt est demandé pendant l'attente (le lot reste à relire)."""
        batch_id = submitted["batch_id"]
        keys: list[str] = submitted["keys"]
        while True:
            batch = self._call(
                "lecture du lot", lambda: self.client.messages.batches.retrieve(batch_id)
            )
            if batch.processing_status == "ended":
                break
            if session.stop.should_stop():
                logger.info("Lot %s non terminé : relu à la reprise, jamais annulé", batch_id)
                return False
            self.sleep(self.poll_s)
        results = self._call(
            "résultats du lot", lambda: list(self.client.messages.batches.results(batch_id))
        )

        outcomes: dict[str, str] = {}
        verdicts: dict[str, Verdict] = {}
        reasons: dict[str, str] = {}
        usage_by_key: dict[str, tuple[int, int, float]] = {}
        counts = Counter({"succeeded": 0, "errored": 0, "canceled": 0, "expired": 0})
        for entry in results:
            try:
                key = keys[int(entry.custom_id)]
            except (ValueError, IndexError):
                logger.warning("Lot %s : custom_id inattendu ignoré", batch_id)
                continue
            result = entry.result
            if result.type not in counts:
                logger.warning(
                    "Lot %s : type de résultat inconnu, traité en panne passagère", batch_id
                )
                outcomes[key] = "transient"
                continue
            counts[result.type] += 1
            if result.type == "succeeded":
                try:
                    verdict, usage = self._read_message(result.message)
                except UnitError as exc:
                    outcomes[key] = "unit"
                    reasons[key] = exc.reason
                    usage_by_key[key] = (*exc.tokens, exc.cost_usd)
                else:
                    outcomes[key] = "ok"
                    usage_by_key[key] = usage
                    verdicts[key] = Verdict(key, verdict, None, usage[:2], usage[2], 0)
            elif result.type == "errored":
                error_type = getattr(getattr(result.error, "error", None), "type", None)
                if error_type in UNIT_ERROR_TYPES:
                    outcomes[key] = "unit"
                    reasons[key] = f"requête refusée ({error_type})"
                else:
                    outcomes[key] = "transient"
            else:
                outcomes[key] = "transient"
        for key in keys:
            outcomes.setdefault(key, "transient")  # résultat absent : à resoumettre

        attempts = self._attempts(self._history(session))
        for key in keys:
            unit = by_key.get(key)
            if unit is None or key in session.writer:
                continue  # clé déjà écrite (reprise après un arrêt brutal) ou hors du jeu
            tokens_in, tokens_out, cost = usage_by_key.get(key, (0, 0, 0.0))
            if outcomes[key] == "ok":
                verdict = verdicts[key]
                session.write(
                    unit,
                    Verdict(
                        key, verdict.verdict, None, verdict.tokens, verdict.cost_usd, attempts[key]
                    ),
                )
            elif outcomes[key] == "unit" and attempts[key] >= self.max_attempts:
                session.write(
                    unit,
                    Verdict(
                        key, None, None, (tokens_in, tokens_out), cost, attempts[key], reasons[key]
                    ),
                )
        total_in = sum(value[0] for value in usage_by_key.values())
        total_out = sum(value[1] for value in usage_by_key.values())
        total_cost = sum(value[2] for value in usage_by_key.values())
        line = {
            "schema": "qb.batch/1",
            "key": f"{batch_id}|collected",
            "batch_id": batch_id,
            "judge": session.judge_id,
            "manifest": session.manifest_hash,
            "status": "collected",
            "counts": dict(counts),
            "tokens": {"input": total_in, "output": total_out},
            "cost_usd": total_cost,
            "outcomes": outcomes,
            "created_at": utc_now(),
        }
        validate(line)
        assert session.batches is not None
        session.batches.append(line)
        if paid_here:
            session.budget.spend(total_cost)
        logger.info(
            "Lot %s relevé : %s ; %d tokens d'entrée, %d de sortie, %.4f $",
            batch_id,
            ", ".join(f"{name} {counts[name]}" for name in sorted(counts)),
            total_in,
            total_out,
            total_cost,
        )
        return True

    def _read_message(self, message: Any) -> tuple[bool, tuple[int, int, float]]:
        usage = message.usage
        tokens_in = (
            int(usage.input_tokens or 0)
            + int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
            + int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        )
        tokens_out = int(usage.output_tokens or 0)
        cost = request_cost(self.config.prices, tokens_in, tokens_out, batch=True)
        spent = (tokens_in, tokens_out)
        if message.stop_reason == "refusal":
            raise UnitError("refus du modèle (refusal)", spent, cost)
        if message.stop_reason in ("max_tokens", "model_context_window_exceeded"):
            raise UnitError(f"sortie tronquée ({message.stop_reason})", spent, cost)
        text = "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
        try:
            verdict = parse_verdict(text)
        except UnitError as exc:
            raise UnitError(exc.reason, spent, cost) from None
        return verdict, (tokens_in, tokens_out, cost)


def _error_verdict(key: str, attempts: int, reason: str) -> Verdict:
    return Verdict(key, None, None, (0, 0), 0.0, attempts, reason)
