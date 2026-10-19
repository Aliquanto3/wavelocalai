"""Garde-fou mémoire : chiffre le besoin réel d'un modèle local avant qu'il ne charge (AD-14, AD-18).

Appelé par `stream_into_run` **dans la place « Ollama local »**, juste avant l'appel du modèle :
c'est le moment où la mémoire libre compte (aucun autre modèle ne charge en même temps). Un modèle
dont le besoin dépasse la mémoire libre fait lever `ram_guard` ; le run se termine en `error` avec
l'enveloppe d'AD-18, et le message de la personne reste dans l'historique de la conversation.

- Le besoin vient de `hardware/` (empreinte mesurée, sinon taille du catalogue ou d'Ollama × 1,25)
  par `ModelRegistry.memory_needs()` ; la mémoire libre est celle de psutil (`available`).
- Un modèle **déjà chargé** (`/api/ps`) occupe sa place : son besoin est nul. Ollama l'a chargé en
  entier ; l'estimation de `hardware/` ne passe pas devant sa mesure (elle la dépasse d'ordinaire),
  sinon un modèle prêt serait refusé à tort. `/api/ps` n'est lu que si le modèle ne tient pas
  déjà : le chemin courant ne fait aucun appel réseau.
- Les **autres modèles chargés** comptent comme libres : le garde-fou s'exécute dans la place
  « Ollama local » (AD-14, une seule à la fois, embeddings compris), aucun appel local de l'app
  ne les emploie donc à cet instant, et Ollama décharge de lui-même un modèle inactif quand le
  suivant manque de place. Sans cela, la lane d'Arène qui suit une grosse lane, ou un chat qui
  change de modèle, serait refusé à tort. `free_gb` est cette mémoire-là (libre + modèles
  inactifs), celle que compare le garde-fou.
- Besoin inconnu, modèle non local, Ollama muet : le garde-fou ne dit rien (un inconnu n'est jamais
  un refus) ; l'appel suivant dit sa propre erreur.
- `suggested_model` : le plus gros modèle de conversation local qui tient (même règle, modèles
  déjà chargés compris) dont le besoin est **plus petit** que celui du modèle refusé (« Prendre
  un modèle plus petit »), que le front présente tel quel ; `None` si aucun ne tient.
- Seuls les appels de génération sont gardés (chat, Arène, réponse RAG). L'embedding et
  l'ingestion ne le sont pas : leur modèle est petit et l'écart §7(d) n° 13 (message adapté à
  l'import) reste à trancher.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx

from wavelocalai.errors import AppError
from wavelocalai.hardware.memory import (
    MemoryReading,
    ceil_tenth,
    floor_tenth,
    read_memory,
    shortfall_gb,
)
from wavelocalai.models.ollama_ps import LoadedModel, loaded_models
from wavelocalai.models.port import ModelRef
from wavelocalai.models.registry import ModelNeed

logger = logging.getLogger("wavelocalai.inference")

LoadedReader = Callable[[], Awaitable[list[LoadedModel] | None]]


class NeedsSource(Protocol):
    """Fourni par `ModelRegistry` : les besoins en mémoire des modèles locaux."""

    def memory_needs(self) -> list[ModelNeed]: ...


class MemoryGuard:
    def __init__(
        self,
        needs: NeedsSource,
        host: str,
        *,
        reader: Callable[[], MemoryReading] = read_memory,
        ps_timeout_s: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
        loaded: LoadedReader | None = None,
    ) -> None:
        """`reader` : lecture de la mémoire du poste (simulée par les tests). `loaded` : lecture
        de `/api/ps` (par défaut, celle d'Ollama sur `host`, sous `transport` s'il est donné)."""
        self._needs = needs
        self._reader = reader
        self._loaded = loaded or (
            lambda: loaded_models(host, timeout_s=ps_timeout_s, transport=transport)
        )

    async def __call__(self, ref: ModelRef) -> None:
        await self.check(ref)

    async def check(self, ref: ModelRef) -> None:
        """Lève `ram_guard` si le modèle ne tient pas dans la mémoire libre ; sinon, ou en cas
        de doute, ne fait rien."""
        if ref.origin != "local":
            return
        try:
            await self._check(ref)
        except AppError:
            raise
        except Exception:  # noqa: BLE001 - un garde-fou en panne ne bloque jamais une réponse
            logger.warning("Garde-fou mémoire indisponible pour %s", ref.tag, exc_info=True)

    async def _check(self, ref: ModelRef) -> None:
        needs = {need.tag: need for need in self._needs.memory_needs()}
        mine = needs.get(ref.tag)
        if mine is None:
            return  # besoin inconnu : jamais un refus
        available = self._reader().available_gb
        if shortfall_gb(mine.needed_gb, 0.0, available) is None:
            return  # tient sans rien savoir de plus : aucun appel à Ollama
        loaded_list = await self._loaded()
        if loaded_list is None:
            return  # Ollama ne répond pas : l'appel dira sa propre erreur
        loaded = {item.tag: item.size_gb for item in loaded_list}
        if ref.tag in loaded:
            return  # déjà chargé : sa place est prise, rien à demander à la mémoire libre
        # Modèles chargés inactifs (place prise : aucun appel local de l'app ne les emploie) :
        # Ollama les décharge à la demande, leur mémoire compte comme libre.
        free = available + sum(max(0.0, size) for size in loaded.values())
        shortfall = shortfall_gb(mine.needed_gb, 0.0, free)
        if shortfall is None:
            return  # tient une fois les modèles inactifs déchargés par Ollama
        suggestion = _largest_fitting(needs, set(loaded), free, refused=mine)
        raise AppError(
            "ram_guard",
            f"{ref.tag} demande {shortfall:.2f} Go (marge et réserve système comprises) pour "
            f"{free:.2f} Go libres (dont {free - available:.2f} Go de modèles chargés inactifs).",
            needed_gb=ceil_tenth(shortfall),
            free_gb=floor_tenth(free),
            suggested_model=suggestion,
        )


def _largest_fitting(
    needs: dict[str, ModelNeed], loaded: set[str], free: float, *, refused: ModelNeed
) -> str | None:
    """Le modèle de conversation local le plus gros (besoin brut) qui tient et reste plus petit
    que le modèle refusé, ou `None` : un modèle déjà chargé tient toujours."""
    fitting = [
        need
        for need in needs.values()
        if need.kind == "chat"
        and need.tag != refused.tag
        and need.needed_gb < refused.needed_gb
        and (need.tag in loaded or shortfall_gb(need.needed_gb, 0.0, free) is None)
    ]
    if not fitting:
        return None
    return max(fitting, key=lambda need: (need.needed_gb, need.tag)).tag
