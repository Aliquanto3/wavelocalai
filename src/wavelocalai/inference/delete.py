"""Suppression d'un modèle installé : « Supprimer » de l'écran Modèles (story 5.4, AD-9, AD-17).

`DELETE /api/models/{tag}` appelle `delete_installed_model` : le tag doit être un modèle local connu
du registre, qu'aucun run actif n'emploie (`409 model_in_use`, `detail.tag` et `detail.run_id`, y
compris un run en cours de création). Un verrou par modèle (`RunHub.deleting_model`) est tenu de
ce contrôle à la fin de la suppression : un run qui voudrait démarrer sur ce modèle entre-temps est
refusé (`model_not_found`), sans fenêtre entre le contrôle et l'appel d'Ollama. Le modèle est déchargé de la mémoire s'il l'était, Ollama le supprime
(`DELETE /api/delete` ; un modèle qu'Ollama ne connaît déjà plus est une suppression réussie), ses
lignes `model_facts` sont purgées et il quitte la liste (il ne réapparaît pas au démarrage à froid),
et les usages dont il était le défaut choisi reviennent à la règle automatique (D-41).

C'est le seul chemin qui retire un modèle du poste : aucune route de lecture, aucun démarrage.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

import httpx

from wavelocalai.errors import AppError
from wavelocalai.models.classify import base_tag
from wavelocalai.models.defaults import ModelDefaults
from wavelocalai.models.ollama_api import OllamaUnavailableError
from wavelocalai.models.ollama_delete import DeleteError, delete_model
from wavelocalai.models.ollama_ps import loaded_models, unload_model
from wavelocalai.models.registry import ModelRegistry


@dataclass(frozen=True)
class DeleteReport:
    tag: str
    freed_gb: float | None  # taille du modèle supprimé (Go), `None` si inconnue
    reverted: list[str] = field(default_factory=list)  # usages revenus à la règle automatique


def _busy(active_models: Callable[[], dict[str, str]], tag: str) -> tuple[str, str] | None:
    """`(tag, run_id)` du run actif qui emploie ce modèle, sinon `None`."""
    wanted = base_tag(tag)
    for used, run_id in active_models().items():
        if base_tag(used) == wanted:
            return used, run_id
    return None


def _refuse_if_busy(active_models: Callable[[], dict[str, str]], tag: str) -> None:
    busy = _busy(active_models, tag)
    if busy is not None:
        raise AppError(
            "model_in_use",
            f"Le run {busy[1]} emploie {tag}.",
            tag=tag,
            run_id=busy[1],
        )


async def delete_installed_model(
    host: str,
    tag: str,
    *,
    registry: ModelRegistry,
    defaults: ModelDefaults,
    active_models: Callable[[], dict[str, str]],
    deleting: Callable[[str], AbstractContextManager[None]] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> DeleteReport:
    """Supprime le modèle du poste. `model_not_found` s'il n'est pas un modèle local de la liste,
    `model_in_use` si un run actif l'emploie, `ollama_down` si Ollama ne répond pas,
    `model_delete_failed` si Ollama refuse.

    `deleting` (`RunHub.deleting_model`) est le verrou par modèle : posé avant le contrôle d'usage
    et tenu jusqu'à la fin de la suppression, il refuse tout run qui démarrerait sur ce modèle entre
    « est-il employé ? » et l'appel d'Ollama (pas de course, story 8.1)."""
    listed = await registry.list_models(allow_cloud=True)
    model = next((m for m in listed.models if m.tag == tag and m.origin == "local"), None)
    if model is None:
        raise AppError("model_not_found", f"Modèle local inconnu : {tag}", tag=tag)
    with deleting(tag) if deleting is not None else contextlib.nullcontext():
        return await _delete_locked(
            host, tag, model.size_gb, registry, defaults, active_models, transport
        )


async def _delete_locked(
    host: str,
    tag: str,
    size_gb: float | None,
    registry: ModelRegistry,
    defaults: ModelDefaults,
    active_models: Callable[[], dict[str, str]],
    transport: httpx.AsyncBaseTransport | None,
) -> DeleteReport:
    _refuse_if_busy(active_models, tag)
    # Déchargé seulement s'il est chargé : `keep_alive: 0` sur un modèle froid (`/api/embed` d'un
    # modèle d'embedding, ou un Ollama ancien) le chargerait avant de le décharger.
    loaded = await loaded_models(host, timeout_s=2.0, transport=transport) or []
    if any(base_tag(m.tag) == base_tag(tag) for m in loaded):
        await unload_model(host, tag, transport=transport)  # libère la mémoire, sans rien générer
    _refuse_if_busy(active_models, tag)  # un run a pu démarrer pendant le déchargement
    try:
        await delete_model(host, tag, transport=transport)
    except OllamaUnavailableError as exc:
        raise AppError("ollama_down", f"Suppression de {tag} : {exc}") from exc
    except DeleteError as exc:
        raise AppError("model_delete_failed", exc.technical, tag=tag) from exc
    await registry.forget(tag)
    return DeleteReport(tag=tag, freed_gb=size_gb, reverted=defaults.forget_model(tag))
