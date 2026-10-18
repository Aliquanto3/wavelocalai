"""Adaptateur Ollama du port `Embedder` : `/api/embed` natif, client async partagé (AD-8).

Embeddings locaux seulement. Les pannes deviennent des `ProviderError` à code fermé, comme pour
`OllamaChatModel` : Ollama injoignable (`ollama_down`), modèle absent (`model_not_found`), autre
refus (`ollama_error`). Il ne calcule pas de CO2 et n'écrit pas en base.
"""

from __future__ import annotations

import httpx
from ollama import AsyncClient, RequestError, ResponseError

from wavelocalai.errors import ProviderError
from wavelocalai.models.port import ModelRef

_DOWN = (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError)


class OllamaEmbedder:
    """`Embedder` pour un tag local servi par Ollama."""

    def __init__(self, ref: ModelRef, client: AsyncClient) -> None:
        self.ref = ref
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._client.embed(model=self.ref.tag, input=texts)
        except _DOWN as exc:
            raise ProviderError("ollama_down", f"{type(exc).__name__}: {exc}") from exc
        except ResponseError as exc:
            if exc.status_code == 404:
                raise ProviderError("model_not_found", str(exc), tag=self.ref.tag) from exc
            raise ProviderError("ollama_error", str(exc)) from exc
        except (RequestError, httpx.HTTPError) as exc:
            raise ProviderError("ollama_error", f"{type(exc).__name__}: {exc}") from exc
        vectors = [[float(x) for x in vector] for vector in response.embeddings]
        if len(vectors) != len(texts) or not all(vectors) or len({len(v) for v in vectors}) != 1:
            raise ProviderError(
                "ollama_error",
                f"{self.ref.tag} a rendu {len(vectors)} vecteurs pour {len(texts)} textes "
                "(ou des vecteurs vides, ou de longueurs différentes).",
            )
        return vectors
