"""Configurations de campagne et de jeu (AD-8) : seul module qui lit les YAML.

``load_set(path, sources, refused)`` lit ``scripts/quality_bench/sets/<set>.yaml`` (sources,
effectifs, graines). Le catalogue des sources (``questions/schema.py``) lui est passé par
l'appelant : ``common/`` n'importe jamais ``questions/`` (sens des dépendances du spine).

``load_campaign(path)`` lit ``scripts/quality_bench/campaigns/<c>.yaml``, applique les valeurs
par défaut d'AD-8, refuse toute clé inconnue (et toute clé en double) et calcule
``generation_hash`` sur la section ``generation`` résolue : un commentaire ou un ordre de clés
différent ne change pas l'empreinte, une valeur par défaut rendue explicite non plus.
"""

from __future__ import annotations

import copy
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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
    "min_prefill_tok_s": 50,
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
    """Lit un YAML (chargeur sûr, clés en double refusées) ; un YAML illisible lève
    ``ConfigError`` avec sa position seulement, jamais l'extrait du texte (fichiers privés)."""
    with open(path, encoding="utf-8") as handle:
        try:
            return yaml.load(handle, Loader=_UniqueKeyLoader)  # noqa: S506 (SafeLoader dérivé)
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            where = f" (ligne {mark.line + 1}, colonne {mark.column + 1})" if mark else ""
            raise ConfigError(f"YAML illisible : {path}{where}") from None


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


def _positive_number(value: Any, where: str) -> float:
    """Nombre fini strictement positif (entier ou flottant, jamais booléen), rendu en flottant :
    ``50`` et ``50.0`` donnent la même empreinte."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ConfigError(f"{where} : nombre > 0 attendu, reçu {value!r}")
    return float(value)


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
        "min_prefill_tok_s": _positive_number(
            value.get("min_prefill_tok_s", DEFAULT_GENERATION["min_prefill_tok_s"]),
            "generation.min_prefill_tok_s",
        ),
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


# --- Jeu de questions : scripts/quality_bench/sets/<set>.yaml ------------------------------

_SET_KEYS = {"set", "seed", "sources", "think_on"}
_SET_SOURCE_KEYS = {
    "source",
    "count",
    "per_group",
    "generator_seed",
    "generator_params",
    "exclude",
}


class SourceInfo(Protocol):
    """Ce que ``load_set`` lit d'une source du catalogue (``questions/schema.SourceSpec``)."""

    @property
    def usage(self) -> str: ...

    @property
    def generated(self) -> bool: ...


@dataclass(frozen=True)
class SetSource:
    """Une source du jeu : effectif exact, plafond par groupe, graine, réglages et
    identifiants de questions exclues du tirage (``exclude``)."""

    source: str
    usage: str
    count: int
    per_group: int | None
    generator_seed: int | None
    generator_params: dict[str, Any]
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetConfig:
    """Configuration résolue d'un jeu : sources dans l'ordre du YAML, effectifs par usage."""

    path: Path
    set_id: str
    seed: int
    sources: tuple[SetSource, ...]
    think_off: dict[str, int]
    think_on: dict[str, int]


def _set_source(
    raw: Any,
    index: int,
    sources: Mapping[str, SourceInfo],
    refused: Mapping[str, str],
) -> SetSource:
    where = f"sources[{index}]"
    value = _require_mapping(raw, where)
    _reject_unknown(value, _SET_SOURCE_KEYS, where)
    for key in ("source", "count"):
        if key not in value:
            raise ConfigError(f"{where}.{key} : obligatoire")
    slug = value["source"]
    if not isinstance(slug, str):
        raise ConfigError(f"{where}.source : chaîne attendue, reçu {slug!r}")
    if slug in refused:
        raise ConfigError(f"{where}.source : source refusée « {slug} » ({refused[slug]})")
    if slug not in sources:
        raise ConfigError(f"{where}.source : source inconnue {slug!r}")
    info = sources[slug]
    per_group = value.get("per_group")
    if per_group is not None:
        per_group = _int(per_group, f"{where}.per_group", 1)
    if info.generated:
        if "generator_seed" not in value:
            raise ConfigError(f"{where}.generator_seed : obligatoire pour la source générée {slug}")
        generator_seed = _int(value["generator_seed"], f"{where}.generator_seed", 0)
        params = value.get("generator_params")
        params = {} if params is None else params
        generator_params = dict(_require_mapping(params, f"{where}.generator_params"))
    else:
        for key in ("generator_seed", "generator_params"):
            if key in value:
                raise ConfigError(f"{where}.{key} : interdit pour la source non générée {slug}")
        generator_seed, generator_params = None, {}
    return SetSource(
        source=slug,
        usage=info.usage,
        count=_int(value["count"], f"{where}.count", 1),
        per_group=per_group,
        generator_seed=generator_seed,
        generator_params=generator_params,
        exclude=_exclude(value.get("exclude", []), f"{where}.exclude"),
    )


def _exclude(value: Any, where: str) -> tuple[str, ...]:
    """Identifiants de questions exclues : liste de chaînes non vides, sans doublon."""
    if not isinstance(value, list):
        raise ConfigError(f"{where} : liste d'identifiants de questions attendue, reçu {value!r}")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"{where} : identifiant non vide attendu, reçu {item!r}")
    duplicates = sorted({item for item in value if value.count(item) > 1})
    if duplicates:
        raise ConfigError(f"{where} : identifiants en double {duplicates}")
    return tuple(value)


def load_set(
    path: str | os.PathLike[str],
    sources: Mapping[str, SourceInfo],
    refused: Mapping[str, str],
) -> SetConfig:
    """Lit et vérifie le YAML de jeu ``path`` ; ``ConfigError`` qui nomme le champ fautif.

    ``sources`` : catalogue fermé des sources (``questions/schema.SOURCES``) ; ``refused`` :
    sources refusées (``REFUSED_SOURCES``).
    """
    path = Path(path)
    raw = _require_mapping(read_yaml(path), str(path))
    _reject_unknown(raw, _SET_KEYS, str(path))
    for key in sorted(_SET_KEYS):
        if key not in raw:
            raise ConfigError(f"{path} : clé « {key} » obligatoire")
    set_id = _config_id(_string(raw["set"], "set"), "set")
    if set_id != path.stem:
        raise ConfigError(f"set : {set_id!r} différent du nom du fichier {path.stem!r}")
    seed = _int(raw["seed"], "seed", 0)
    if not isinstance(raw["sources"], list) or not raw["sources"]:
        raise ConfigError("sources : liste non vide attendue")
    resolved = tuple(
        _set_source(item, index, sources, refused) for index, item in enumerate(raw["sources"])
    )
    slugs = [item.source for item in resolved]
    if len(set(slugs)) != len(slugs):
        raise ConfigError("sources : source en double")
    think_off = {
        usage: sum(item.count for item in resolved if item.usage == usage)
        for usage in USAGES
        if any(item.usage == usage for item in resolved)
    }
    raw_think_on = _require_mapping(raw["think_on"], "think_on")
    _reject_unknown(raw_think_on, set(USAGES), "think_on")
    think_on = {}
    for usage in think_off:
        count = _int(raw_think_on.get(usage, 0), f"think_on.{usage}", 0)
        if count > think_off[usage]:
            raise ConfigError(
                f"think_on.{usage} : {count} au-delà de l'effectif think_off {think_off[usage]}"
            )
        think_on[usage] = count
    for usage in raw_think_on:
        if usage not in think_off and _int(raw_think_on[usage], f"think_on.{usage}", 0) != 0:
            raise ConfigError(f"think_on.{usage} : aucun effectif think_off pour cet usage")
    return SetConfig(path, set_id, seed, resolved, think_off, think_on)
