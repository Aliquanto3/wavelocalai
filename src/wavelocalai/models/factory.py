"""Adaptateur d'un `ModelRef` résolu : le registre dit quel modèle, la fabrique dit comment le
parler (AD-8, AD-9). Un service reçoit la référence du registre, jamais un tag brut."""

from __future__ import annotations

from collections.abc import Mapping

from ollama import AsyncClient

from wavelocalai.errors import AppError
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.port import ChatModel, ModelRef


class ModelFactory:
    def __init__(self, client: AsyncClient, fakes: Mapping[str, ChatModel] | None = None) -> None:
        self._client = client
        self._fakes = dict(fakes or {})  # non vide seulement si `Settings.testing`

    def chat_model(self, ref: ModelRef) -> ChatModel:
        fake = self._fakes.get(ref.tag)
        if fake is not None:
            return fake
        if ref.provider == "ollama":
            return OllamaChatModel(ref, self._client)
        # Les adaptateurs cloud arrivent avec la story des modèles cloud.
        raise AppError("internal", f"Aucun adaptateur de conversation pour {ref.provider}.")
