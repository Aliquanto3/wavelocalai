"""Configuration de campagne (AD-8) : seul module qui lit les YAML.

``load_campaign(path)`` lit ``scripts/quality_bench/campaigns/<c>.yaml``, applique les valeurs
par défaut d'AD-8, refuse toute clé inconnue (et toute clé en double) et calcule
``generation_hash`` sur la section ``generation`` résolue : un commentaire ou un ordre de clés
différent ne change pas l'empreinte, une valeur par défaut rendue explicite non plus.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .canonical import sha256_hex
from .paths import check_id
from .schemas import TRACKS, USAGES

DEFAULT_GENERATION: dict[str, Any] = {
    "request": {"temperature": 0, "seed_base": 0, "k": 1},
    "caps": {"think_on": {"reasoning": 4096, "default": 2048}, "think_off": {"default": 2048}},
    "num_ctx_tiers": [4096, 8192, 16384, 32768],
    "max_attempts": 3,
    "max_consecutive_errors": 5,
    "ollama_wait_s": 600,
    "max_tool_calls_per_turn": 8,
    "selection": None,
}
_GENERATION_KEYS = {*DEFAULT_GENERATION, "models"}
_MODEL_KEYS = {"tag", "family", "tracks", "think_off", "think_on", "num_ctx_max"}
_MODEL_REQUIRED = ("tag", "family", "tracks", "num_ctx_max")
_CAP_KEYS = {"default", *USAGES}


class ConfigError(ValueError):
    """Configuration de campagne invalide (message qui nomme le champ fautif)."""


@dataclass(frozen=True)
class CampaignConfig:
    """Configuration résolue d'une campagne."""

    path: Path
    campaign: str
    set_id: str
    generation: dict[str, Any]
    generation_hash: str
    grading: dict[str, Any]


class _UniqueKeyLoader(yaml.SafeLoader):
    """Chargeur YAML sûr qui refuse une clé en double au lieu de garder la dernière."""


def _construct_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise ConfigError(
                f"Clé en double dans le YAML : {key!r} (ligne {key_node.start_mark.line + 1})"
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def read_yaml(path: str | os.PathLike[str]) -> Any:
    """Lit un YAML (chargeur sûr, clés en double refusées)."""
    with open(path, encoding="utf-8") as handle:
        return yaml.load(handle, Loader=_UniqueKeyLoader)  # noqa: S506 (SafeLoader dérivé)


def _config_id(value: str, what: str) -> str:
    """``paths.check_id`` dont le refus devient une ``ConfigError``."""
    try:
        return check_id(value, what)
    except ValueError as exc:
        raise ConfigError(str(exc)) from None


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} : un objet (mapping) est attendu")
    return value


def _reject_unknown(value: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise ConfigError(f"{where} : clés inconnues {unknown} (permises : {sorted(allowed)})")


def _int(value: Any, where: str, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ConfigError(f"{where} : entier ≥ {minimum} attendu, reçu {value!r}")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or "|" in value:
        raise ConfigError(f"{where} : chaîne non vide sans « | » attendue, reçu {value!r}")
    return value


def _resolve_request(raw: Any) -> dict[str, Any]:
    value = _require_mapping(raw, "generation.request")
    _reject_unknown(value, set(DEFAULT_GENERATION["request"]), "generation.request")
    request = {**DEFAULT_GENERATION["request"], **value}
    if request["temperature"] != 0 or isinstance(request["temperature"], bool):
        raise ConfigError("generation.request.temperature : seule la valeur 0 est permise (AD-9)")
    request["temperature"] = 0
    _int(request["seed_base"], "generation.request.seed_base", 0)
    _int(request["k"], "generation.request.k", 1)
    return request


def _resolve_caps(raw: Any) -> dict[str, Any]:
    value = _require_mapping(raw, "generation.caps")
    _reject_unknown(value, set(TRACKS), "generation.caps")
    caps = copy.deepcopy(DEFAULT_GENERATION["caps"])
    for track, track_caps in value.items():
        where = f"generation.caps.{track}"
        track_caps = _require_mapping(track_caps, where)
        _reject_unknown(track_caps, _CAP_KEYS, where)
        caps[track] = {**caps[track], **track_caps}
    for track, track_caps in caps.items():
        for usage, cap in track_caps.items():
            _int(cap, f"generation.caps.{track}.{usage}", 1)
    return caps


def _resolve_tiers(raw: Any) -> list[int]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("generation.num_ctx_tiers : liste non vide attendue")
    tiers = [_int(tier, "generation.num_ctx_tiers[]", 1) for tier in raw]
    if any(a >= b for a, b in zip(tiers, tiers[1:], strict=False)):
        raise ConfigError("generation.num_ctx_tiers : valeurs strictement croissantes attendues")
    return tiers


def _resolve_selection(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    value = _require_mapping(raw, "generation.selection")
    if len(value) != 1 or next(iter(value)) not in ("ids", "sample"):
        raise ConfigError("generation.selection : null, {ids: [...]} ou {sample: {...}} attendu")
    if "ids" in value:
        ids = value["ids"]
        if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids):
            raise ConfigError("generation.selection.ids : liste non vide sans doublon attendue")
        return {"ids": [_string(item, "generation.selection.ids[]") for item in ids]}
    sample = _require_mapping(value["sample"], "generation.selection.sample")
    _reject_unknown(sample, {"per_usage", "seed"}, "generation.selection.sample")
    for key in ("per_usage", "seed"):
        if key not in sample:
            raise ConfigError(f"generation.selection.sample.{key} : obligatoire")
    return {
        "sample": {
            "per_usage": _int(sample["per_usage"], "generation.selection.sample.per_usage", 1),
            "seed": _int(sample["seed"], "generation.selection.sample.seed", 0),
        }
    }


def _resolve_model(raw: Any, index: int) -> dict[str, Any]:
    where = f"generation.models[{index}]"
    value = _require_mapping(raw, where)
    _reject_unknown(value, _MODEL_KEYS, where)
    for key in _MODEL_REQUIRED:
        if key not in value:
            raise ConfigError(f"{where}.{key} : obligatoire")
    tracks = value["tracks"]
    if (
        not isinstance(tracks, list)
        or not tracks
        or len(set(tracks)) != len(tracks)
        or any(track not in TRACKS for track in tracks)
    ):
        raise ConfigError(f"{where}.tracks : liste non vide de {list(TRACKS)} attendue")
    model: dict[str, Any] = {
        "tag": _string(value["tag"], f"{where}.tag"),
        "family": _string(value["family"], f"{where}.family"),
        "tracks": [track for track in TRACKS if track in tracks],
        "num_ctx_max": _int(value["num_ctx_max"], f"{where}.num_ctx_max", 1),
    }
    for track in TRACKS:
        # La valeur de think d'une piste lancée est explicite (null : pas de capacité thinking).
        if track in tracks and track not in value:
            raise ConfigError(f"{where}.{track} : obligatoire pour une piste lancée (null permis)")
        think = value.get(track)
        if think is not None and not isinstance(think, (bool, str)):
            raise ConfigError(f"{where}.{track} : booléen, chaîne ou null attendu")
        model[track] = think
    return model


def _bounded(value: dict[str, Any], key: str, minimum: int) -> int:
    """Entier de la section ``generation``, valeur par défaut lue dans ``DEFAULT_GENERATION``."""
    return _int(value.get(key, DEFAULT_GENERATION[key]), f"generation.{key}", minimum)


def resolve_generation(raw: Any) -> dict[str, Any]:
    """Section ``generation`` avec les valeurs par défaut d'AD-8 appliquées et vérifiées."""
    value = _require_mapping(raw, "generation")
    _reject_unknown(value, _GENERATION_KEYS, "generation")
    if "models" not in value:
        raise ConfigError("generation.models : obligatoire")
    models = value["models"]
    if not isinstance(models, list) or not models:
        raise ConfigError("generation.models : liste non vide attendue")
    resolved_models = [_resolve_model(model, index) for index, model in enumerate(models)]
    tags = [model["tag"] for model in resolved_models]
    if len(set(tags)) != len(tags):
        raise ConfigError("generation.models : étiquette de modèle en double")
    return {
        "request": _resolve_request(value.get("request", {})),
        "caps": _resolve_caps(value.get("caps", {})),
        "num_ctx_tiers": _resolve_tiers(
            value.get("num_ctx_tiers", DEFAULT_GENERATION["num_ctx_tiers"])
        ),
        "max_attempts": _bounded(value, "max_attempts", 1),
        "max_consecutive_errors": _bounded(value, "max_consecutive_errors", 1),
        "ollama_wait_s": _bounded(value, "ollama_wait_s", 0),
        "max_tool_calls_per_turn": _bounded(value, "max_tool_calls_per_turn", 1),
        "selection": _resolve_selection(value.get("selection")),
        "models": resolved_models,
    }


def _resolve_grading(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"judge": None}
    value = _require_mapping(raw, "grading")
    _reject_unknown(value, {"judge"}, "grading")
    judge = value.get("judge")
    if judge is not None:
        _config_id(_string(judge, "grading.judge"), "grading.judge")
    return {"judge": judge}


def load_campaign(path: str | os.PathLike[str]) -> CampaignConfig:
    """Lit et résout le YAML de campagne ``path`` (identifiant = nom du fichier sans suffixe)."""
    path = Path(path)
    raw = _require_mapping(read_yaml(path), str(path))
    _reject_unknown(raw, {"set", "generation", "grading"}, str(path))
    if "set" not in raw:
        raise ConfigError(f"{path} : clé « set » obligatoire")
    if "generation" not in raw:
        raise ConfigError(f"{path} : section « generation » obligatoire")
    campaign = _config_id(path.stem, "campagne")  # ni « | » ni séparateur (clés AD-4)
    generation = resolve_generation(raw["generation"])
    return CampaignConfig(
        path=path,
        campaign=campaign,
        set_id=_config_id(_string(raw["set"], "set"), "set"),
        generation=generation,
        generation_hash=sha256_hex(generation),
        grading=_resolve_grading(raw.get("grading")),
    )
