"""Adaptateur d'un `ModelRef` résolu : le registre dit quel modèle, la fabrique dit comment le
parler (AD-8, AD-9). Un service reçoit la référence du registre, jamais un tag brut.

Les adaptateurs cloud (OpenAI, Groq, Anthropic, Mistral) reçoivent la clé du fournisseur lue dans
`Settings` ; une clé absente n'empêche pas de les construire : l'appel dit `cloud_key_missing`.
`cloud_http` (tests) donne, par fournisseur, une fabrique de client HTTP pour le SDK.
"""

from __future__ import annotations

from collections.abc import Mapping

from ollama import AsyncClient

from wavelocalai.config import Settings
from wavelocalai.errors import AppError
from wavelocalai.models.anthropic import AnthropicChatModel
from wavelocalai.models.cloud import HttpClientFactory
from wavelocalai.models.mistral import MistralChatModel
from wavelocalai.models.ollama import OllamaChatModel
from wavelocalai.models.openai_compat import OpenAICompatChatModel
from wavelocalai.models.port import ChatModel, ModelRef


class ModelFactory:
    def __init__(
        self,
        client: AsyncClient,
        fakes: Mapping[str, ChatModel] | None = None,
        settings: Settings | None = None,
        cloud_http: Mapping[str, HttpClientFactory] | None = None,
    ) -> None:
        self._client = client
        self._fakes = dict(fakes or {})  # non vide seulement si `Settings.testing`
        self._settings = settings
        self._cloud_http = dict(cloud_http or {})

    def _api_key(self, provider: str) -> str | None:
        if self._settings is None:
            return None
        key = self._settings.api_keys.get(provider)
        return key.get_secret_value() if key is not None else None

    def chat_model(self, ref: ModelRef) -> ChatModel:
        fake = self._fakes.get(ref.tag)
        if fake is not None:
            return fake
        if ref.provider == "ollama":
            return OllamaChatModel(ref, self._client)
        http = self._cloud_http.get(ref.provider)
        key = self._api_key(ref.provider)
        if ref.provider in ("openai", "groq"):
            return OpenAICompatChatModel(ref, key, http_client=http)
        if ref.provider == "anthropic":
            return AnthropicChatModel(ref, key, http_client=http)
        if ref.provider == "mistral":
            return MistralChatModel(ref, key, http_client=http)
        raise AppError("internal", f"Aucun adaptateur de conversation pour {ref.provider}.")
