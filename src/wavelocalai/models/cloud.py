"""Socle commun des adaptateurs cloud du port `ChatModel` (AD-8, AD-18).

Un adaptateur cloud ne calcule pas de CO2, n'écrit pas en base et ne lit pas `allow_cloud` : c'est
`registry.resolve` qui a déjà dit oui (AD-9). Ce module porte ce que les trois adaptateurs
(`openai_compat`, `anthropic`, `mistral`) partagent :

- les noms de fournisseurs et la variable de `.env` qui porte leur clé ;
- la traduction d'une panne du SDK en `ProviderError` à code fermé, sans jamais laisser la clé
  dans le texte (`cloud_key_missing`, `cloud_key_refused`, `cloud_rate_limited`,
  `cloud_unreachable`, `cloud_error`, `generation_interrupted` pour un flux coupé en route) ;
- le chronomètre mural d'un appel : un fournisseur cloud ne dit pas combien de temps le modèle a
  mis à générer, le débit est donc `tokens / durée murale` avec `tps_source = "wallclock"` ;
- le raccord de test : une fabrique de client HTTP par fournisseur (`HttpClientFactory`), pour
  brancher un faux transport sous le vrai SDK sans toucher au réseau.

Les SDK (`openai`, `anthropic`, `mistralai`) ne sont importés que dans les fonctions (AD-4).
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable
from typing import Any

from wavelocalai.config import CLOUD_KEY_VARS
from wavelocalai.errors import ERRORS, ProviderError, mask_secrets
from wavelocalai.models.port import ChatMessage, ChatResult

logger = logging.getLogger("wavelocalai.models")

PROVIDER_NAMES: dict[str, str] = {
    "openai": "OpenAI",
    "groq": "Groq",
    "anthropic": "Anthropic",
    "mistral": "Mistral",
}
CONNECT_TIMEOUT_S = 10.0
TECHNICAL_MAX_CHARS = 600

# Renvoie un client HTTP asynchrone neuf pour le SDK du fournisseur (`httpx.AsyncClient` pour
# openai, `httpx2.AsyncClient` pour anthropic et mistralai). Absent en production : le SDK crée
# le sien. Appelé à chaque appel de modèle (le SDK ferme le client qu'on lui donne).
HttpClientFactory = Callable[[], Any]

# Erreurs de réseau, reconnues par le nom de classe : openai/anthropic enveloppent les leurs dans
# `APIConnectionError`, le SDK Mistral laisse passer celles de son client HTTP, et les trois
# n'utilisent pas la même bibliothèque (`httpx` ou `httpx2`).
_TRANSPORT_NAMES = {
    "APIConnectionError",
    "APITimeoutError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "TimeoutException",
    "NetworkError",
    "ReadError",
    "WriteError",
    "CloseError",
    "TransportError",
    "RemoteProtocolError",
    "ProtocolError",
    "NoResponseError",
    "ConnectionError",
}
_CUT_NAMES = {"ReadError", "RemoteProtocolError", "ProtocolError", "ReadTimeout", "NoResponseError"}
# Erreurs d'API des SDK (`openai.APIError`, `anthropic.APIError`, `mistralai` : `SDKError`).
_SDK_ERROR_NAMES = {"APIError", "SDKError"}


def provider_of(tag: str) -> str:
    """Fournisseur d'un tag cloud `fournisseur/modèle`."""
    return tag.partition("/")[0]


def model_of(tag: str) -> str:
    """Identifiant du modèle chez le fournisseur : `groq/openai/gpt-oss-120b` donne
    `openai/gpt-oss-120b`."""
    return tag.partition("/")[2]


def provider_detail(provider: str) -> dict[str, str]:
    """Clés machine communes des erreurs cloud (déclarées avec chaque code dans `errors.py`)."""
    return {
        "provider": provider,
        "provider_name": PROVIDER_NAMES.get(provider, provider),
        "key_var": CLOUD_KEY_VARS.get(provider, ""),
    }


def _error(code: str, technical: str | None, provider: str, **extra: Any) -> ProviderError:
    """`ProviderError` dont `detail` ne porte que les clés déclarées pour ce code."""
    keys = ERRORS[code].detail_keys
    detail = {**provider_detail(provider), **extra}
    return ProviderError(code, technical, **{k: v for k, v in detail.items() if k in keys})


def key_missing(provider: str) -> ProviderError:
    detail = provider_detail(provider)
    return _error(
        "cloud_key_missing",
        f"Aucune clé d'API pour {detail['provider_name']} ({detail['key_var']}).",
        provider,
    )


def _status_of(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _clip(text: str) -> str:
    return text if len(text) <= TECHNICAL_MAX_CHARS else text[:TECHNICAL_MAX_CHARS] + "…"


def _names(exc: BaseException) -> set[str]:
    return {cls.__name__ for cls in type(exc).__mro__}


def translate_error(
    provider: str, exc: Exception, api_key: str | None, *, fragments: int = 0
) -> Exception:
    """`ProviderError` correspondant à une panne du SDK ; les autres exceptions passent telles
    quelles (le service les range sous `internal`). Le texte technique est masqué : la clé du
    fournisseur n'en sort jamais, ni par `detail` ni par le journal."""
    if isinstance(exc, ProviderError):
        return exc
    secrets = [api_key] if api_key else []
    technical = _clip(mask_secrets(f"{type(exc).__name__}: {exc}", secrets))
    detail = provider_detail(provider)
    status = _status_of(exc)
    if status is not None and status >= 400:
        if status in (401, 403):
            code = "cloud_key_refused"
        elif status == 429:
            code = "cloud_rate_limited"
        else:
            code = "cloud_error"
        logger.warning("%s a répondu %s (%s).", detail["provider_name"], status, code)
        return _error(code, technical, provider, http_status=status)
    names = _names(exc)
    if names & _TRANSPORT_NAMES:
        if fragments > 0 and (names & _CUT_NAMES or "APIConnectionError" in names):
            logger.warning(
                "Flux de %s coupé après %s fragments.", detail["provider_name"], fragments
            )
            return ProviderError(
                "generation_interrupted",
                f"{detail['provider_name']} : flux coupé après {fragments} fragments ({technical})",
            )
        logger.warning("%s est injoignable (%s).", detail["provider_name"], type(exc).__name__)
        return _error("cloud_unreachable", technical, provider)
    if status is not None:  # réponse d'erreur dans un flux : code HTTP d'un statut 2xx
        return _error("cloud_error", technical, provider, http_status=status)
    if names & _SDK_ERROR_NAMES:
        # Erreur annoncée dans le flux SSE (OpenAI, Groq : `openai.APIError` sans statut HTTP).
        logger.warning("%s a signalé une erreur dans le flux.", detail["provider_name"])
        return _error("cloud_error", technical, provider)
    return exc


def chat_text_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
    """Messages `system` / `user` / `assistant` au format commun (Chat Completions). Les messages
    d'outils attendent la story des agents : ils ne sont pas envoyés."""
    return [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in ("system", "user", "assistant") and m.content
    ]


class WallClock:
    """Chronomètre d'un appel cloud : départ, premier fragment, fin."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self.started = clock()
        self.first_at: float | None = None
        self.text_chars = 0

    def note(self, text: str) -> None:
        """Un fragment de texte (réponse ou raisonnement) vient d'arriver."""
        if text:
            if self.first_at is None:
                self.first_at = self._clock()
            self.text_chars += len(text)

    def result(
        self,
        *,
        finish_reason: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> ChatResult:
        """`ChatResult` d'un appel terminé. Le fournisseur ne dit pas combien de temps le modèle a
        généré : le débit est `jetons / (fin - premier fragment)` (hors attente du premier
        fragment, comme D3 écarte le prefill), repli sur la durée totale ; `tps_source` vaut
        toujours `wallclock`. Sans `usage`, les jetons sont estimés à 4 caractères."""
        total = max(self._clock() - self.started, 0.0)
        ttft = None if self.first_at is None else max(self.first_at - self.started, 0.0)
        tokens = output_tokens if output_tokens is not None else self.text_chars // 4
        generation = total - ttft if ttft is not None else 0.0
        if tokens > 1 and generation > 0:
            tps = (tokens - 1) / generation  # le premier jeton marque la fin de l'attente
        else:
            tps = tokens / total if total > 0 else 0.0
        return ChatResult(
            finish_reason=normalize_finish(finish_reason),
            input_tokens=input_tokens,
            output_tokens=tokens,
            ttft_s=None if ttft is None else round(ttft, 3),
            load_s=None,  # un fournisseur cloud n'a pas de chargement de modèle
            eval_s=round(generation, 3) if generation > 0 else None,
            total_s=round(total, 3),
            tps=round(tps, 2),
            tps_source="wallclock",
        )


_FINISH = {
    "stop": "stop",
    "end_turn": "stop",
    "stop_sequence": "stop",
    "tool_use": "tool_calls",
    "tool_calls": "tool_calls",
    "length": "length",
    "max_tokens": "length",
    "model_length": "length",
}


def normalize_finish(reason: str | None) -> str:
    """Motif de fin dans le vocabulaire commun (`stop`, `length`, `tool_calls`, sinon tel quel)."""
    return _FINISH.get(reason or "stop", reason or "stop")


async def close_quietly(obj: Any) -> None:
    """Ferme un flux ou un client de SDK (`aclose` ou `close`, async), sans jamais lever."""
    if obj is None:
        return
    for name in ("aclose", "close"):
        closer = getattr(obj, name, None)
        if closer is None:
            continue
        with contextlib.suppress(Exception):
            result = closer()
            if hasattr(result, "__await__"):
                await result
        return
