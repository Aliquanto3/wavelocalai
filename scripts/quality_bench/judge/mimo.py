"""MiMo-V2.6-Pro par le SDK ``openai`` (``chat.completions``), une requête par critère (AD-16).

Sans température ni autre paramètre d'échantillonnage ; ``thinking`` envoyé (``extra_body``)
seulement s'il est réglé dans ``judges.yaml``. Verdict JSON lu dans le contenu du message.
Les essais sont comptés par le banc : le client du SDK ne relance rien (``max_retries=0``).

- connexion, délai, 429, 5xx : panne passagère ;
- autre 4xx, ``finish_reason`` ``length`` (troncature) ou ``content_filter`` (refus), verdict
  illisible : échec propre à l'unité.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import openai

from ..common.config import JudgeConfig
from .base import Judge, JudgeLaunchError, TransientError, UnitError, Verdict, parse_verdict
from .pricing import estimate_cost, request_cost
from .prompt import LLM_SYSTEM, llm_user
from .units import Unit


def make_client(config: JudgeConfig, api_key: str, http_client: Any = None) -> openai.OpenAI:
    """Client ``openai`` sur le point d'accès de MiMo, sans relance automatique."""
    return openai.OpenAI(
        api_key=api_key,
        base_url=config.endpoint,
        max_retries=0,
        timeout=config.options["timeout_s"],
        http_client=http_client,
    )


class MimoJudge(Judge):
    def __init__(
        self, config: JudgeConfig, sleep: Callable[[float], None], client: openai.OpenAI
    ) -> None:
        super().__init__(config, sleep)
        self.client = client

    def close(self) -> None:
        self.client.close()

    def messages(self, unit: Unit) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": LLM_SYSTEM},
            {
                "role": "user",
                "content": llm_user(unit.instruction, unit.answer, unit.criterion_question),
            },
        ]

    def estimate(self, items: Sequence[Unit]) -> float:
        chars = sum(len(m["content"]) for unit in items for m in self.messages(unit))
        return estimate_cost(
            self.config.prices,
            chars,
            self.config.options["max_tokens"] * len(items),
            self.config.options["chars_per_token"],
        )

    def attempt(self, items: Sequence[Unit]) -> list[Verdict]:
        (unit,) = items
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": self.messages(unit),
            "max_completion_tokens": self.config.options["max_tokens"],
        }
        thinking = self.config.options.get("thinking")
        if thinking is not None:
            kwargs["extra_body"] = {"thinking": dict(thinking)}
        try:
            completion = self.client.chat.completions.create(**kwargs)
        except openai.APIConnectionError as exc:  # délai compris (APITimeoutError)
            raise TransientError(f"service injoignable ({type(exc).__name__})") from None
        except openai.APIStatusError as exc:
            if exc.status_code == 429 or exc.status_code >= 500:
                raise TransientError(f"statut {exc.status_code}") from None
            if exc.status_code in (401, 403, 404):
                # Clé refusée, modèle ou chemin introuvable : panne de configuration, sans ligne.
                raise JudgeLaunchError(
                    f"juge {self.config.id} : requête refusée (statut {exc.status_code}) ; "
                    "vérifier la clé, le modèle et le point d'accès"
                ) from None
            raise UnitError(f"requête refusée (statut {exc.status_code})") from None
        except openai.APIError as exc:  # réponse invalide pour le SDK (validation, etc.)
            raise UnitError(f"réponse invalide ({type(exc).__name__})") from None
        usage = getattr(completion, "usage", None)
        tokens = (
            int(getattr(usage, "prompt_tokens", 0) or 0),
            int(getattr(usage, "completion_tokens", 0) or 0),
        )
        cost = request_cost(self.config.prices, *tokens)
        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise UnitError("réponse sans choix", tokens, cost)
        choice = choices[0]
        if choice.finish_reason == "length":
            raise UnitError("sortie tronquée (max_tokens)", tokens, cost)
        if choice.finish_reason == "content_filter":
            raise UnitError("refus du modèle (content_filter)", tokens, cost)
        try:
            verdict = parse_verdict(choice.message.content or "")
        except UnitError as exc:
            raise UnitError(exc.reason, tokens, cost) from None
        return [Verdict(unit.key, verdict, None, tokens, cost, 0)]
