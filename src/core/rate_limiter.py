# src/core/rate_limiter.py
"""
Rate limiter pour les appels API.
Protège contre la surcharge des services externes.
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration du rate limiting pour un provider."""

    requests_per_minute: int = 60
    requests_per_day: int = 10000
    tokens_per_minute: int = 100000
    concurrent_requests: int = 10


@dataclass
class RateLimitState:
    """État du rate limiter."""

    minute_requests: list[float] = field(default_factory=list)
    day_requests: list[float] = field(default_factory=list)
    minute_tokens: int = 0
    last_token_reset: float = field(default_factory=time.time)
    semaphore: asyncio.Semaphore | None = None


class RateLimiter:
    """
    Rate limiter configurable par provider.

    Supporte :
    - Limite de requêtes par minute
    - Limite de requêtes par jour
    - Limite de tokens par minute
    - Limite de requêtes concurrentes
    """

    # Configurations par défaut pour chaque provider
    DEFAULT_CONFIGS: dict[str, RateLimitConfig] = {
        "ollama": RateLimitConfig(
            requests_per_minute=1000,  # Local, pas de limite stricte
            requests_per_day=100000,
            tokens_per_minute=1000000,
            concurrent_requests=5,
        ),
        "mistral": RateLimitConfig(
            requests_per_minute=60,
            requests_per_day=10000,
            tokens_per_minute=100000,
            concurrent_requests=10,
        ),
        "openai": RateLimitConfig(
            requests_per_minute=60,
            requests_per_day=10000,
            tokens_per_minute=90000,
            concurrent_requests=10,
        ),
        "anthropic": RateLimitConfig(
            requests_per_minute=60,
            requests_per_day=10000,
            tokens_per_minute=100000,
            concurrent_requests=5,
        ),
    }

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._states: dict[str, RateLimitState] = defaultdict(RateLimitState)
            cls._instance._configs: dict[str, RateLimitConfig] = cls.DEFAULT_CONFIGS.copy()
        return cls._instance

    def configure(self, provider: str, config: RateLimitConfig):
        """Configure le rate limiting pour un provider."""
        self._configs[provider] = config
        logger.info(f"Rate limiter configuré pour {provider}: {config}")

    def _get_state(self, provider: str) -> RateLimitState:
        """Récupère ou initialise l'état pour un provider."""
        if provider not in self._states:
            config = self._configs.get(provider, RateLimitConfig())
            self._states[provider] = RateLimitState(
                semaphore=asyncio.Semaphore(config.concurrent_requests)
            )
        return self._states[provider]

    def _get_config(self, provider: str) -> RateLimitConfig:
        """Récupère la configuration pour un provider."""
        return self._configs.get(provider, RateLimitConfig())

    def _cleanup_old_requests(self, state: RateLimitState):
        """Nettoie les requêtes expirées."""
        now = time.time()
        minute_ago = now - 60
        day_ago = now - 86400

        state.minute_requests = [t for t in state.minute_requests if t > minute_ago]
        state.day_requests = [t for t in state.day_requests if t > day_ago]

        # Reset tokens si une minute s'est écoulée
        if now - state.last_token_reset > 60:
            state.minute_tokens = 0
            state.last_token_reset = now

    def can_make_request(self, provider: str) -> tuple[bool, str]:
        """
        Vérifie si une requête peut être effectuée.

        Returns:
            (can_proceed, reason)
        """
        config = self._get_config(provider)
        state = self._get_state(provider)
        self._cleanup_old_requests(state)

        if len(state.minute_requests) >= config.requests_per_minute:
            return False, f"Limite minute atteinte ({config.requests_per_minute}/min)"

        if len(state.day_requests) >= config.requests_per_day:
            return False, f"Limite journalière atteinte ({config.requests_per_day}/jour)"

        return True, "OK"

    def record_request(self, provider: str, tokens: int = 0):
        """Enregistre une requête effectuée."""
        state = self._get_state(provider)
        now = time.time()

        state.minute_requests.append(now)
        state.day_requests.append(now)
        state.minute_tokens += tokens

    async def acquire(self, provider: str) -> bool:
        """
        Acquiert un slot pour effectuer une requête.

        Bloque si la limite de concurrence est atteinte.
        Retourne False si les limites de rate sont dépassées.
        """
        can_proceed, reason = self.can_make_request(provider)
        if not can_proceed:
            logger.warning(f"Rate limit {provider}: {reason}")
            return False

        state = self._get_state(provider)
        config = self._get_config(provider)

        # Initialiser le semaphore si nécessaire
        if state.semaphore is None:
            state.semaphore = asyncio.Semaphore(config.concurrent_requests)

        await state.semaphore.acquire()
        return True

    def release(self, provider: str, tokens: int = 0):
        """Libère un slot après une requête."""
        state = self._get_state(provider)
        self.record_request(provider, tokens)

        if state.semaphore:
            state.semaphore.release()

    def get_stats(self, provider: str) -> dict[str, Any]:
        """Retourne les statistiques actuelles pour un provider."""
        config = self._get_config(provider)
        state = self._get_state(provider)
        self._cleanup_old_requests(state)

        return {
            "provider": provider,
            "requests_last_minute": len(state.minute_requests),
            "requests_last_day": len(state.day_requests),
            "tokens_last_minute": state.minute_tokens,
            "limits": {
                "requests_per_minute": config.requests_per_minute,
                "requests_per_day": config.requests_per_day,
                "tokens_per_minute": config.tokens_per_minute,
                "concurrent_requests": config.concurrent_requests,
            },
        }


# Instance singleton globale
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Retourne l'instance singleton du rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
