"""Manifeste de campagne ``qb.manifest/1`` (AD-8).

Écrit au premier lancement, puis comparé à chaque reprise : toute différence dans ``blocking``
refuse la reprise (``ManifestMismatchError`` qui nomme le premier champ différent, par exemple
``blocking.models_resolved[3].digest``). ``informative`` ne bloque jamais.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import socket
import subprocess
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, pretty_bytes, sha256_bytes, sha256_hex, utc_now
from .paths import PACKAGE_DIR, REPO_ROOT
from .schemas import validate

logger = logging.getLogger(__name__)

MACHINE_ENV = "QUALITY_BENCH_MACHINE"
HARNESS_DIRS = ("common", "ollama", "generation", "envs")
_MISSING = object()
# Variables OLLAMA_* dont la valeur n'est jamais consignée (le manifeste peut être partagé).
_SECRET_WORDS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
_MASKED = "<masqué>"
# Export public : seules ces variables de comportement d'Ollama gardent leur valeur (noms de
# ``envconfig`` d'Ollama, d'après sa documentation). Les autres (``OLLAMA_MODELS``,
# ``OLLAMA_HOST``, ``OLLAMA_ORIGINS``... : chemins, hôtes) sortent avec leur seul nom.
PUBLIC_OLLAMA_ENV = frozenset(
    {
        "OLLAMA_CONTEXT_LENGTH",
        "OLLAMA_FLASH_ATTENTION",
        "OLLAMA_GPU_OVERHEAD",
        "OLLAMA_INTEL_GPU",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_KV_CACHE_TYPE",
        "OLLAMA_LLM_LIBRARY",
        "OLLAMA_LOAD_TIMEOUT",
        "OLLAMA_MAX_LOADED_MODELS",
        "OLLAMA_MAX_QUEUE",
        "OLLAMA_MULTIUSER_CACHE",
        "OLLAMA_NEW_ENGINE",
        "OLLAMA_NEW_ESTIMATES",
        "OLLAMA_NUM_PARALLEL",
        "OLLAMA_SCHED_SPREAD",
        "OLLAMA_VULKAN",
    }
)
_NOT_PUBLISHED = "<non publié>"


def public_ollama_env(env: Mapping[str, Any]) -> dict[str, Any]:
    """Copie exportable de ``informative.ollama_env`` : valeur gardée pour la liste blanche
    ``PUBLIC_OLLAMA_ENV``, remplacée par ``<non publié>`` pour tout autre nom (le nom seul
    indique qu'un réglage existait, sans publier chemin ni hôte)."""
    return {
        name: value if name.upper() in PUBLIC_OLLAMA_ENV and value != _MASKED else _NOT_PUBLISHED
        for name, value in sorted(env.items())
    }


class ManifestMismatchError(RuntimeError):
    """Reprise refusée : le manifeste existant diffère sur un champ bloquant."""

    def __init__(self, path: str, existing: Any, new: Any) -> None:
        self.path = path
        self.existing = existing
        self.new = new
        super().__init__(
            f"Reprise refusée : le champ bloquant {path} diffère du manifeste existant "
            f"(existant : {_short(existing)} ; nouveau : {_short(new)}). "
            "Modifier la génération impose un nouvel identifiant de campagne."
        )


def _short(value: Any) -> str:
    if value is _MISSING:
        return "absent"
    text = canonical_bytes(value).decode("utf-8")
    return text if len(text) <= 120 else text[:117] + "..."


def harness_hash(package_dir: Path = PACKAGE_DIR) -> str:
    """Empreinte du harnais : contenu de tous les fichiers de ``common/``, ``ollama/``,
    ``generation/`` et ``envs/`` existants (hors ``__pycache__`` et ``*.pyc``), triés par chemin
    relatif, fins de ligne normalisées en ``\\n``."""
    files: list[list[str]] = []
    for name in HARNESS_DIRS:
        directory = package_dir / name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            files.append([path.relative_to(package_dir).as_posix(), sha256_bytes(content)])
    files.sort()
    return sha256_hex(files)


def machine_label() -> str:
    """Libellé de la machine : ``$QUALITY_BENCH_MACHINE`` s'il est défini, sinon le nom d'hôte."""
    label = os.environ.get(MACHINE_ENV, "").strip()
    return label or socket.gethostname()


def _run(command: list[str]) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603 (commande fixe, sans shell)
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip()
    return output.splitlines()[0].strip() if result.returncode == 0 and output else None


def collect_informative(
    *,
    checklist: Mapping[str, Any] | None = None,
    prices: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Partie informative : Python, paquets installés, commit, pilote NVIDIA, environnement
    d'Ollama, liste de contrôle et prix. Elle ne bloque jamais une reprise."""
    packages: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            packages[name.lower()] = dist.version
    return {
        "python": platform.python_version(),
        "packages": dict(sorted(packages.items())),
        "code_commit": _run(["git", "rev-parse", "HEAD"]),
        "nvidia_driver": _run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
        ),
        "ollama_env": {
            name: _MASKED if any(word in name.upper() for word in _SECRET_WORDS) else value
            for name, value in sorted(os.environ.items())
            if name.upper().startswith("OLLAMA_")
        },
        "checklist": dict(checklist or {}),
        "prices": dict(prices) if prices is not None else None,
    }


def build_manifest(
    *,
    phase: str,
    campaign: str,
    set_info: Mapping[str, Any],
    generation: Mapping[str, Any],
    models_resolved: list[Mapping[str, Any]],
    ollama_version: str | None,
    judge: Mapping[str, Any] | None = None,
    generation_manifest: str | None = None,
    informative: Mapping[str, Any] | None = None,
    machine: str | None = None,
) -> dict[str, Any]:
    """Construit et valide un manifeste ``qb.manifest/1``.

    ``set_info`` = ``{id, hash, n}`` ; ``generation`` = ``{hash, resolved}`` (voir
    ``config.load_campaign``) ; ``informative`` collectée si elle n'est pas fournie.
    """
    manifest = {
        "schema": "qb.manifest/1",
        "phase": phase,
        "campaign": campaign,
        "created_at": utc_now(),
        "blocking": {
            "set": dict(set_info),
            "generation": dict(generation),
            "models_resolved": [dict(model) for model in models_resolved],
            "ollama_version": ollama_version,
            "machine": machine if machine is not None else machine_label(),
            "harness_hash": harness_hash(),
            "judge": dict(judge) if judge is not None else None,
            "generation_manifest": generation_manifest,
        },
        "informative": dict(informative) if informative is not None else collect_informative(),
    }
    validate(manifest)
    return manifest


def blocking_hash(manifest: Mapping[str, Any]) -> str:
    """Empreinte du ``blocking`` : portée par chaque ligne JSONL qu'il a produite."""
    return sha256_hex(manifest["blocking"])


def _same_scalar(a: Any, b: Any) -> bool:
    # True == 1 et 1 == 1.0 en Python : le type compte aussi.
    return type(a) is type(b) and a == b


def first_difference(existing: Any, new: Any, path: str = "blocking") -> str | None:
    """Chemin JSON du premier champ différent (parcours en profondeur, clés triées, listes
    indexées, longueur différente signalée au premier indice manquant), ou ``None``."""
    if isinstance(existing, dict) and isinstance(new, dict):
        for key in sorted(set(existing) | set(new)):
            if key not in existing or key not in new:
                return f"{path}.{key}"
            found = first_difference(existing[key], new[key], f"{path}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(existing, list) and isinstance(new, list):
        for index in range(max(len(existing), len(new))):
            if index >= len(existing) or index >= len(new):
                return f"{path}[{index}]"
            found = first_difference(existing[index], new[index], f"{path}[{index}]")
            if found is not None:
                return found
        return None
    return None if _same_scalar(existing, new) else path


def _value_at(root: Mapping[str, Any], path: str) -> Any:
    """Valeur au chemin JSON ``path`` relatif à ``root`` (premier segment ignoré), ou
    ``_MISSING`` ; sert au message d'erreur."""
    current: Any = root
    for token in path.replace("[", ".[").split(".")[1:]:
        if token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(current, list) or index >= len(current):
                return _MISSING
            current = current[index]
        else:
            if not isinstance(current, dict) or token not in current:
                return _MISSING
            current = current[token]
    return current


def ensure_manifest(path: str | os.PathLike[str], manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Écrit ``manifest`` au premier lancement ; sinon compare son ``blocking`` à celui du
    fichier et rend le manifeste existant. Le verrou de la phase doit être détenu."""
    path = Path(path)
    validate(manifest)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "wb") as handle:
            handle.write(pretty_bytes(manifest))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return dict(manifest)

    with open(path, encoding="utf-8") as handle:
        existing = json.load(handle)
    validate(existing)
    old_info, new_info = existing["informative"], manifest["informative"]
    changed = sorted(
        name
        for name in set(old_info) | set(new_info)
        if old_info.get(name, _MISSING) != new_info.get(name, _MISSING)
    )
    if changed:
        logger.warning(
            "Reprise : partie informative différente du manifeste existant (non bloquant) : %s",
            ", ".join(f"informative.{name}" for name in changed),
        )
    for field in ("phase", "campaign"):
        if existing[field] != manifest[field]:
            raise ManifestMismatchError(field, existing[field], manifest[field])
    diff = first_difference(existing["blocking"], manifest["blocking"])
    if diff is not None:
        raise ManifestMismatchError(
            diff, _value_at(existing["blocking"], diff), _value_at(manifest["blocking"], diff)
        )
    return existing
