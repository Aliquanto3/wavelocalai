"""Adaptateur d'un `ModelRef` résolu : le registre dit quel modèle, la fabrique dit comment le
parler (AD-8, AD-9). Un service reçoit la référence du registre, jamais un tag brut."""

from __future__ import annotations

from collections.abc import Mapping

from ollama import AsyncClient

from wavelocalai.errors import AppError
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.ollama_embed import OllamaEmbedder
from wavelocalai.models.port import ChatModel, Embedder, ModelRef


class ModelFactory:
    def __init__(
        self,
        client: AsyncClient,
        fakes: Mapping[str, ChatModel] | None = None,
        fake_embedders: Mapping[str, Embedder] | None = None,
    ) -> None:
        self._client = client
        self._fakes = dict(fakes or {})  # non vide seulement si `Settings.testing`
        self._fake_embedders = dict(fake_embedders or {})  # idem

    def chat_model(self, ref: ModelRef) -> ChatModel:
        fake = self._fakes.get(ref.tag)
        if fake is not None:
            return fake
        if ref.provider == "ollama":
            return OllamaChatModel(ref, self._client)
        # Les adaptateurs cloud arrivent avec la story des modèles cloud.
        raise AppError("internal", f"Aucun adaptateur de conversation pour {ref.provider}.")

    def embedder(self, ref: ModelRef) -> Embedder:
        """Embedder d'une référence résolue par `registry.resolve_embedder` (local seulement)."""
        fake = self._fake_embedders.get(ref.tag)
        if fake is not None:
            return fake
        if ref.provider == "ollama":
            return OllamaEmbedder(ref, self._client)
        raise AppError("internal", f"Aucun adaptateur d'embedding pour {ref.provider}.")
