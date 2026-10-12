"""Juge du contrat ``POST /v1/systemone`` (questions ``noul``), local ou hébergé (AD-16).

Contrat retenu (hypothèse minimale, à vérifier contre le serveur réel) :

    POST /v1/systemone
    {"model": "winnow-e4b",
     "messages": [{"role": "system", "content": "…"}, {"role": "user", "content": "…"}],
     "questions": [{"id": "c1", "type": "noul", "question": "…"}]}
    → {"model": "…", "answers": [{"id": "c1", "type": "noul", "noul": 0.91}],
       "usage": {"prompt_tokens": 812, "completion_tokens": 5}}

Confirmés : le chemin, la réponse ``{"type": "noul", "noul": p}``, l'enveloppe
``{model, answers, usage}`` et 1 à 256 questions par requête. Les réponses sont appariées par
``id`` s'il est rendu, sinon par position. ``verdict = probabilité ≥ 0,5``.

Une requête par ligne de génération (tous ses critères). Tokens et coût de la requête répartis
sur ses lignes (somme conservée). Juge local : URL ``localhost``/``127.0.0.1`` seulement, sans
proxy, coût nul.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import httpx2

from ..common.config import JudgeConfig
from ..ollama.client import check_local_base_url
from .base import Judge, JudgeLaunchError, TransientError, UnitError, Verdict, split_int
from .pricing import estimate_cost, request_cost
from .prompt import SYSTEMONE_SYSTEM, systemone_user
from .units import Unit

ENDPOINT_PATH = "/v1/systemone"
MAX_QUESTIONS = 256
THRESHOLD = 0.5
# Statuts qui ne tiennent pas à l'unité (clé, chemin ou modèle) : arrêt sans ligne (code 1).
LAUNCH_STATUSES = (401, 403, 404)


def _usage_count(usage: Any, name: str) -> int:
    value = usage.get(name) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


class SystemOneJudge(Judge):
    """Juge ``/v1/systemone`` ; ``transport`` injecté par les tests (``httpx2.MockTransport``)."""

    def __init__(
        self,
        config: JudgeConfig,
        sleep: Callable[[float], None],
        *,
        api_key: str | None = None,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        super().__init__(config, sleep)
        if config.endpoint is None:
            raise ValueError(f"juge {config.id} : endpoint nul")
        if config.local:
            base_url = check_local_base_url(config.endpoint)
        else:
            if not config.endpoint.startswith("https://"):
                raise ValueError(f"juge {config.id} : endpoint hébergé en https attendu")
            base_url = config.endpoint.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx2.Client(
            base_url=base_url,
            transport=transport,
            headers=headers,
            trust_env=not config.local,  # juge local : aucun proxy, la requête reste locale
            timeout=httpx2.Timeout(config.options["timeout_s"], connect=10.0),
        )

    def close(self) -> None:
        self._http.close()

    def groups(self, units: Sequence[Unit]) -> list[list[Unit]]:
        by_generation: dict[str, list[Unit]] = {}
        for unit in units:
            by_generation.setdefault(unit.generation_key, []).append(unit)
        return list(by_generation.values())

    def body(self, items: Sequence[Unit]) -> dict[str, Any]:
        if not items or len(items) > MAX_QUESTIONS:
            raise ValueError(f"1 à {MAX_QUESTIONS} questions par requête, reçu {len(items)}")
        first = items[0]
        return {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEMONE_SYSTEM},
                {"role": "user", "content": systemone_user(first.instruction, first.answer)},
            ],
            "questions": [
                {"id": unit.criterion, "type": "noul", "question": unit.criterion_question}
                for unit in items
            ],
        }

    def estimate(self, items: Sequence[Unit]) -> float:
        body = self.body(items)
        chars = sum(len(m["content"]) for m in body["messages"]) + sum(
            len(q["question"]) for q in body["questions"]
        )
        # Sortie : une probabilité par question, quelques tokens chacune.
        return estimate_cost(
            self.config.prices, chars, 16 * len(items), self.config.options["chars_per_token"]
        )

    def attempt(self, items: Sequence[Unit]) -> list[Verdict]:
        try:
            response = self._http.post(ENDPOINT_PATH, json=self.body(items))
        except httpx2.TransportError as exc:
            raise TransientError(f"service injoignable ({type(exc).__name__})") from None
        if response.status_code == 429 or response.status_code >= 500:
            raise TransientError(f"statut {response.status_code}")
        if response.status_code in LAUNCH_STATUSES:
            # Clé refusée, chemin ou modèle introuvable : panne de configuration, aucune ligne.
            raise JudgeLaunchError(
                f"juge {self.config.id} : requête refusée (statut {response.status_code}) ; "
                "vérifier la clé, le modèle et le point d'accès"
            )
        if response.status_code >= 400:
            raise UnitError(f"requête refusée (statut {response.status_code})")
        try:
            payload = response.json()
        except ValueError:
            raise UnitError("réponse illisible (JSON invalide)") from None
        usage = payload.get("usage") if isinstance(payload, dict) else None
        tokens = (_usage_count(usage, "prompt_tokens"), _usage_count(usage, "completion_tokens"))
        cost = request_cost(self.config.prices, *tokens)
        probabilities = self._probabilities(payload, items, tokens, cost)
        ins = split_int(tokens[0], len(items))
        outs = split_int(tokens[1], len(items))
        return [
            Verdict(
                key=unit.key,
                verdict=probabilities[index] >= THRESHOLD,
                probability=probabilities[index],
                tokens=(ins[index], outs[index]),
                cost_usd=cost / len(items),
                attempts=0,
            )
            for index, unit in enumerate(items)
        ]

    @staticmethod
    def _probabilities(
        payload: Any, items: Sequence[Unit], tokens: tuple[int, int], cost: float
    ) -> list[float]:
        def fail(reason: str) -> UnitError:
            return UnitError(f"réponse illisible ({reason})", tokens, cost)

        answers = payload.get("answers") if isinstance(payload, dict) else None
        if not isinstance(answers, list) or len(answers) != len(items):
            raise fail("« answers » absent ou de longueur inattendue")
        if all(isinstance(a, dict) and isinstance(a.get("id"), str) for a in answers):
            by_id = {answer["id"]: answer for answer in answers}
            if len(by_id) != len(answers) or set(by_id) != {u.criterion for u in items}:
                raise fail("identifiants de réponse inattendus")
            ordered = [by_id[unit.criterion] for unit in items]
        else:
            ordered = answers  # appariement par position
        probabilities = []
        for answer in ordered:
            value = answer.get("noul") if isinstance(answer, dict) else None
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise fail("probabilité « noul » absente ou hors de [0, 1]")
            probabilities.append(float(value))
        return probabilities
