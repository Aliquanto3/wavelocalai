"""Suppression d'un modèle par Ollama (`DELETE /api/delete`) : seul appel de la v2 qui retire un
modèle du poste (story 5.4). Jamais lancé par une route de lecture : seul le service de
suppression l'appelle, après la confirmation de l'écran Modèles.

Ollama répond `200` quand le modèle est supprimé, `404` quand il n'existe pas (ou plus : le
résultat voulu est atteint, le service le traite comme une suppression réussie). Toute autre
réponse lève `DeleteError` avec le texte d'Ollama ; un Ollama muet lève `OllamaUnavailableError`.
"""

from __future__ import annotations

import httpx

from wavelocalai.models.ollama_api import OllamaUnavailableError

DELETE_TIMEOUT_S = 20.0  # supprimer des fichiers de plusieurs Go peut prendre un moment


class DeleteError(Exception):
    """Ollama a refusé la suppression : `technical` est ce qu'il a répondu."""

    def __init__(self, technical: str) -> None:
        super().__init__(technical)
        self.technical = technical


async def delete_model(
    host: str,
    tag: str,
    *,
    timeout_s: float = DELETE_TIMEOUT_S,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Supprime le modèle d'Ollama. Vrai s'il l'a supprimé, faux s'il n'existait déjà plus."""
    try:
        async with httpx.AsyncClient(
            base_url=host.rstrip("/"), timeout=timeout_s, transport=transport, trust_env=False
        ) as client:
            response = await client.request("DELETE", "/api/delete", json={"model": tag})
    except httpx.TransportError as exc:
        raise OllamaUnavailableError(str(exc)) from exc
    if response.status_code == 404:
        return False
    if not response.is_success:
        raise DeleteError(f"Ollama a répondu {response.status_code} : {response.text[:300]}")
    return True
