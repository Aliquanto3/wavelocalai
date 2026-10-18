"""Lecture de la liste et des détails des modèles d'Ollama (`/api/tags`, `/api/show`).

Appels HTTP bornés (AD-15), faits en tâche de fond par le registre, jamais par une route de
lecture. L'hôte vient de `Settings` (`http://127.0.0.1:11434` : `localhost` échoue en IPv6 sur
certains postes).
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx


class OllamaUnavailableError(Exception):
    """Ollama ne répond pas (arrêté, trop lent ou réponse illisible)."""


class OllamaSource(Protocol):
    async def list_tags(self) -> list[dict[str, Any]]: ...

    async def show(self, tag: str) -> dict[str, Any]: ...


class OllamaHttpSource:
    def __init__(
        self,
        host: str,
        *,
        timeout_s: float = 1.0,
        show_timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self._timeout_s = timeout_s
        self._show_timeout_s = show_timeout_s
        self._transport = transport

    def _client(self, timeout_s: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._host,
            timeout=timeout_s,
            transport=self._transport,
            trust_env=False,  # pas de proxy système pour une adresse locale
        )

    async def list_tags(self) -> list[dict[str, Any]]:
        try:
            async with self._client(self._timeout_s) as client:
                response = await client.get("/api/tags")
            response.raise_for_status()
            models = response.json().get("models")
        except Exception as exc:  # noqa: BLE001 - toute panne = Ollama indisponible
            raise OllamaUnavailableError(str(exc)) from exc
        if not isinstance(models, list):
            raise OllamaUnavailableError("Réponse /api/tags inattendue.")
        return [m for m in models if isinstance(m, dict)]

    async def show(self, tag: str) -> dict[str, Any]:
        try:
            async with self._client(self._show_timeout_s) as client:
                response = await client.post("/api/show", json={"model": tag})
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            raise OllamaUnavailableError(str(exc)) from exc
        if not isinstance(data, dict):
            raise OllamaUnavailableError("Réponse /api/show inattendue.")
        return data
