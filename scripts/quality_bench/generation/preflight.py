"""Préflight des modèles (AD-8, AD-9) : fonctions pures sur les réponses de ``/api/show`` et
``/api/tags``, appelées pour chaque modèle avant tout manifeste.

Tout refus lève ``LaunchError`` (code 2) avec un message qui nomme le modèle et la raison :
aucun modèle, aucune piste ni aucune question n'est omis en silence (AD-8).

- ``resolve_model`` : entrée de ``models_resolved`` (``tag``, ``digest``, ``family``,
  ``capabilities`` triées, ``tracks``, ``think_off``, ``think_on``, ``num_ctx_max`` effectif) ;
  refuse un modèle absent de ``/api/tags`` ou sans ``digest``, distant (``remote_host``), qui
  déclare ``decision``, sans ``completion``, une piste ``think_on`` sans ``thinking`` ou à valeur
  fausse ou nulle, une piste ``think_off`` à valeur vraie, une valeur ``think`` incohérente avec la capacité ``thinking`` ou de type
  chaîne (``/api/show`` ne publie aucune liste de valeurs permises).
- ``check_launch`` : refuse une question à outils sélectionnée pour un modèle sans ``tools``.
- ``effective_ctx_max`` : ``min(num_ctx_max de la configuration, <arch>.context_length)``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

THINKING = "thinking"
TOOLS = "tools"
COMPLETION = "completion"
DECISION = "decision"


class LaunchError(RuntimeError):
    """Lancement refusé (code 2) : configuration incompatible avec un modèle ou le jeu."""


def _tag_candidates(tag: str) -> set[str]:
    """Noms sous lesquels ``/api/tags`` liste ``tag`` (« :latest » implicite sans étiquette)."""
    candidates = {tag}
    if ":" not in tag.rsplit("/", 1)[-1]:
        candidates.add(f"{tag}:latest")
    return candidates


def find_tag(tags: Sequence[Mapping[str, Any]], tag: str) -> Mapping[str, Any] | None:
    """Entrée de ``/api/tags`` (champ ``name`` ou ``model``) qui correspond à ``tag``."""
    candidates = _tag_candidates(tag)
    for entry in tags:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("name") in candidates or entry.get("model") in candidates:
            return entry
    return None


def declared_context_length(show: Mapping[str, Any]) -> int | None:
    """``<arch>.context_length`` de ``model_info`` (``arch`` = ``general.architecture``)."""
    info = show.get("model_info")
    if not isinstance(info, Mapping):
        return None
    arch = info.get("general.architecture")
    if not isinstance(arch, str) or not arch:
        return None
    value = info.get(f"{arch}.context_length")
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def effective_ctx_max(num_ctx_max: int, show: Mapping[str, Any]) -> int:
    """Contexte maximal effectif : le plus petit du plafond configuré et du contexte déclaré."""
    declared = declared_context_length(show)
    return num_ctx_max if declared is None else min(num_ctx_max, declared)


def _capabilities(tag: str, show: Mapping[str, Any]) -> list[str]:
    capabilities = show.get("capabilities")
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) for item in capabilities
    ):
        raise LaunchError(f"{tag} : capacités illisibles dans /api/show")
    return sorted(set(capabilities))


def _check_think(tag: str, track: str, value: Any, thinking: bool) -> None:
    if isinstance(value, str):
        raise LaunchError(
            f"{tag} : valeur think {value!r} de la piste {track} refusée (/api/show ne publie "
            "aucune liste de valeurs permises ; booléen attendu)"
        )
    if thinking and value is None:
        raise LaunchError(
            f"{tag} : le modèle déclare « thinking », la piste {track} doit fixer think "
            "(true ou false), pas null"
        )
    if not thinking and value is not None:
        raise LaunchError(
            f"{tag} : le modèle ne déclare pas « thinking », la piste {track} doit avoir "
            f"think null (reçu {value!r})"
        )


def resolve_model(
    model_cfg: Mapping[str, Any],
    show: Mapping[str, Any],
    tags: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Entrée ``models_resolved`` du modèle ``model_cfg`` (configuration résolue), ou
    ``LaunchError`` qui nomme le modèle et la raison du refus."""
    tag = model_cfg["tag"]
    entry = find_tag(tags, tag)
    if entry is None:
        raise LaunchError(f"{tag} : modèle absent de /api/tags (non installé)")
    digest = entry.get("digest")
    if not isinstance(digest, str) or not digest:
        raise LaunchError(f"{tag} : aucun digest dans /api/tags")
    if entry.get("remote_host") or show.get("remote_host"):
        raise LaunchError(f"{tag} : modèle distant (remote_host déclaré), refusé (AD-9)")
    capabilities = _capabilities(tag, show)
    if DECISION in capabilities:
        raise LaunchError(f"{tag} : capacité « decision » déclarée, modèle exclu du chat (AD-9)")
    if COMPLETION not in capabilities:
        raise LaunchError(f"{tag} : capacité « completion » absente de /api/show")
    thinking = THINKING in capabilities
    tracks = list(model_cfg["tracks"])
    if "think_on" in tracks:
        if not thinking:
            raise LaunchError(
                f"{tag} : piste think_on demandée sans capacité « thinking » dans /api/show"
            )
        if model_cfg.get("think_on") in (False, None):
            raise LaunchError(
                f"{tag} : piste think_on demandée avec think_on = {model_cfg.get('think_on')!r}"
            )
    if "think_off" in tracks and model_cfg.get("think_off") is True:
        raise LaunchError(f"{tag} : piste think_off demandée avec think_off = True")
    for track in tracks:
        _check_think(tag, track, model_cfg.get(track), thinking)
    return {
        "tag": tag,
        "digest": digest,
        "family": model_cfg["family"],
        "capabilities": capabilities,
        "tracks": tracks,
        "think_off": model_cfg.get("think_off"),
        "think_on": model_cfg.get("think_on"),
        "num_ctx_max": effective_ctx_max(model_cfg["num_ctx_max"], show),
    }


def check_launch(
    resolved: Sequence[Mapping[str, Any]],
    questions_by_track: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    """Refuse le lancement si une question à outils est sélectionnée sur une piste d'un modèle
    qui ne déclare pas ``tools`` (aucune omission silencieuse)."""
    for model in resolved:
        if TOOLS in model["capabilities"]:
            continue
        for track in model["tracks"]:
            with_tools = [q["id"] for q in questions_by_track.get(track, ()) if q.get("tools")]
            if with_tools:
                raise LaunchError(
                    f"{model['tag']} : {len(with_tools)} question(s) à outils sélectionnée(s) "
                    f"sur la piste {track} (première : {with_tools[0]}) sans capacité « tools »"
                )
