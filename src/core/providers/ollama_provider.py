# src/core/providers/ollama_provider.py
"""
Provider Ollama pour les modèles locaux.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlsplit

import ollama
from langchain_ollama import ChatOllama

from src.core.interfaces import ILLMProvider
from src.core.metrics import InferenceMetrics, MetricsCalculator, ollama_metrics

logger = logging.getLogger(__name__)

# Délai des appels d'état (santé, modèles en mémoire), en secondes : court, pour ne jamais
# bloquer l'affichage quand Ollama est arrêté.
STATUS_TIMEOUT_S = 2.0

# Hôtes Ollama situés sur cette machine.
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class OllamaProvider(ILLMProvider):
    """
    Provider pour les modèles locaux via Ollama.
    """

    def __init__(self, base_url: str = "http://localhost:11434"):
        """
        Initialise le provider Ollama.

        Args:
            base_url: URL du serveur Ollama
        """
        self._base_url = base_url

    def _create_async_client(self):
        """
        Crée un nouveau client async à chaque appel.
        Évite les problèmes d'event loop fermée entre les requêtes.
        """
        from ollama import AsyncClient as OllamaAsyncClient

        return OllamaAsyncClient(host=self._base_url)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def is_local(self) -> bool:
        return True

    def list_models(self) -> list[dict[str, Any]]:
        """Liste les modèles installés localement via Ollama."""
        models = []
        try:
            ollama_resp = self._create_client().list()
            raw_models = (
                ollama_resp.models
                if hasattr(ollama_resp, "models")
                else ollama_resp.get("models", [])
            )

            for m in raw_models:
                model_dict = (
                    m.model_dump()
                    if hasattr(m, "model_dump")
                    else (m.__dict__ if hasattr(m, "__dict__") else dict(m))
                )
                model_dict["type"] = "local"
                if "model" not in model_dict and "name" in model_dict:
                    model_dict["model"] = model_dict["name"]
                models.append(model_dict)

        except Exception as e:
            logger.error(f"Erreur Ollama list: {e}")

        return models

    async def chat_stream(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str | InferenceMetrics, None]:
        """Génère une réponse en streaming via Ollama."""

        final_messages = messages.copy()
        if system_prompt:
            final_messages.insert(0, {"role": "system", "content": system_prompt})

        timer = MetricsCalculator()
        full_text = ""
        final_chunk = None

        # Créer un nouveau client pour chaque requête (évite "Event loop is closed")
        client = self._create_async_client()

        try:
            timer.start()
            stream = await client.chat(
                model=model_name,
                messages=final_messages,
                stream=True,
                options={"temperature": temperature},
            )

            async for chunk in stream:
                if isinstance(chunk, dict):
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        full_text += content
                        yield content

                    # Chunk final : porte les compteurs et les durées d'Ollama.
                    if chunk.get("done"):
                        final_chunk = chunk
                else:
                    # Format objet Pydantic
                    content = getattr(chunk, "message", None)
                    if content and hasattr(content, "content"):
                        text = content.content
                        if text:
                            full_text += text
                            yield text

                    if getattr(chunk, "done", False):
                        final_chunk = chunk

            timer.stop()

            # Débit = eval_count / eval_duration (D3, comme scripts/benchmark_slm.py) ;
            # chargement et durée totale à part.
            yield ollama_metrics(
                model_name,
                final_chunk,
                wall_duration_s=timer.duration,
                fallback_output_tokens=len(full_text) // 4,
            )

        except Exception as e:
            logger.error(f"Ollama Error: {e}")
            raise e

    def get_langchain_model(
        self, model_name: str, temperature: float = 0.7, **kwargs
    ) -> ChatOllama:
        """Retourne un modèle LangChain Ollama."""
        return ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=self._base_url,
            keep_alive="5m",
            **kwargs,
        )

    def pull_model(self, model_name: str) -> Any:
        """Télécharge un modèle via Ollama."""
        try:
            return self._create_client().pull(model_name, stream=True)
        except Exception as e:
            logger.error(f"Erreur pull {model_name}: {e}")
            raise e

    def _create_client(self, timeout: float | None = None):
        """Client synchrone sur l'hôte utilisé pour la génération (`base_url`), pour tous les
        appels (liste, téléchargement, santé, modèles en mémoire) : jamais le client par
        défaut (OLLAMA_HOST), qui pourrait viser un autre serveur. `timeout` : délai court
        des appels d'état ; None garde le délai par défaut (téléchargement long)."""
        if timeout is None:
            return ollama.Client(host=self._base_url)
        return ollama.Client(host=self._base_url, timeout=timeout)

    def health_check(self, timeout: float = STATUS_TIMEOUT_S) -> bool:
        """Vérifie qu'Ollama répond, sur l'hôte utilisé pour la génération (`base_url`).

        Un seul appel local, borné par `timeout` : ne bloque pas l'interface si le service
        est arrêté. Ne lève jamais d'exception.
        """
        try:
            self._create_client(timeout).list()
            return True
        except Exception as e:
            logger.debug(f"Ollama injoignable ({self._base_url}) : {e}")
            return False

    def is_model_loaded(self, model_name: str, timeout: float = STATUS_TIMEOUT_S) -> bool | None:
        """Indique si le modèle est déjà en mémoire (`ollama ps`).

        Returns:
            True s'il est chargé, False s'il ne l'est pas (le premier appel sera plus long),
            None si l'état est inconnu (Ollama injoignable, réponse illisible). Ne lève jamais.
        """
        try:
            response = self._create_client(timeout).ps()
            raw_models = (
                response.models if hasattr(response, "models") else response.get("models", [])
            )
            loaded = set()
            for m in raw_models or []:
                for key in ("model", "name"):
                    value = getattr(m, key, None) if not isinstance(m, dict) else m.get(key)
                    if value:
                        loaded.add(_normalize_tag(value))
            return _normalize_tag(model_name) in loaded
        except Exception as e:
            logger.debug(f"ollama ps impossible ({self._base_url}) : {e}")
            return None

    def is_local_host(self) -> bool:
        """Hôte Ollama sur cette machine (localhost, 127.0.0.1, ::1, ou hôte par défaut)."""
        url = self._base_url or "http://localhost:11434"
        host = urlsplit(url if "//" in url else f"//{url}").hostname
        return host in LOCAL_HOSTS

    def loaded_models_ram_gb(self, timeout: float = STATUS_TIMEOUT_S) -> float:
        """Mémoire vive (Go) de cette machine occupée par les modèles déjà chargés dans Ollama
        (`ollama ps`) : taille chargée moins la part en mémoire vidéo. 0.0 si l'hôte Ollama
        est distant (sa mémoire n'est pas celle de cette machine) ou si l'état est inconnu.

        Limite : en mémoire unifiée (Apple Silicon), Ollama annonce `size_vram == size`,
        alors que le modèle occupe bien la mémoire vive ; il compte ici pour 0 et un modèle
        résident peut y être déclassé (erreur prudente). Ne lève jamais."""
        try:
            if not self.is_local_host():
                return 0.0
            response = self._create_client(timeout).ps()
            raw_models = (
                response.models if hasattr(response, "models") else response.get("models", [])
            )
            total = 0.0
            for m in raw_models or []:
                get = m.get if isinstance(m, dict) else lambda k, _m=m: getattr(_m, k, None)
                size = get("size") or 0
                vram = get("size_vram") or 0
                total += max(float(size) - float(vram), 0.0)
            return total / (1024**3)
        except Exception as e:
            logger.debug(f"ollama ps impossible ({self._base_url}) : {e}")
            return 0.0


def _normalize_tag(tag: str) -> str:
    """Tag complet : « qwen2.5 » et « qwen2.5:latest » désignent le même modèle."""
    return tag if ":" in tag else f"{tag}:latest"
