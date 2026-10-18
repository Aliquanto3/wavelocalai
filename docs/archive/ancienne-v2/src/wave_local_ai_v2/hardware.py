"""Hardware fiche capture: the machine-bound fields every runtime row must carry.

`capture_fiche()` stays machine-only: run-specific fields (engine id, build
and configuration hash, the declared machine id and compute mode, roster entry
id + its sha256, quant, flags) are supplied by the caller (the three writers) via `build_fiche`, which merges them with no re-reading of the
machine and no side effects -- this keeps `build_fiche` composable with a
plain dict in tests, without needing a live roster entry.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Mapping
from typing import Any, TypedDict

from wave_local_ai_v2.nvml import decode_nvml_str, nvml_device


class HardwareFiche(TypedDict):
    cpu: str
    ram_gb: float | None
    gpu_name: str | None
    gpu_driver_version: str | None
    os: str
    cuda_ceiling: str | None


class Fiche(HardwareFiche):
    """The machine fiche plus the run-specific fields that describe one launch."""

    engine_id: str
    engine_build: str | None
    engine_config_hash: str
    machine_id: str
    compute_mode: str
    # The run profile the launch resolved (`profiles.py`). Evidence like
    # `flags`, outside every projection: the flags the profile produced are
    # already here, and a renamed profile must not move a hash.
    profile_id: str
    roster_entry_id: str
    model_sha256: str
    quant: str
    flags: list[str]


class FicheProjectionError(ValueError):
    """Raised when a fiche lacks a key of the projection it is hashed under."""


# The projections `fiche_hash` is computed over, by version. `flags`,
# `profile_id`, host and port are in none of them: `flags` stays on the stored fiche as raw evidence
# only (Methodology 14; it carries an absolute model path), and host/port never
# existed on the fiche at all -- stated here so a future field addition doesn't
# reintroduce them silently. The engine's launch configuration enters "2"
# through `engine_config_hash`, taken over a path- and location-free
# normalisation of those flags (`engines.config_hash`).
#
# "1": every fiche cited by a row below schema "22" -- one engine, named only
# by its build. Kept so every committed fiche still verifies under the
# projection it was written with; never chosen by a field being absent.
# "2": `llama_cpp_build` generalised to `engine_build`, with `engine_id` and
# `engine_config_hash` beside it, so two engines on one machine can never
# hash to one identity.
# "3": the declared `machine_id` and the `compute_mode` beside "2"'s keys, for
# every fiche cited by a row at schema "23" or later. Without the mode a `gpu`
# and a `cpu_only` run of one model on one machine were one identity (their
# only difference, `-ngl`, lives in `flags`, outside every projection), so the
# second run's fiche was never stored and the first stood in for it. Without
# the machine id two machines of one CPU generation and RAM size could collide
# silently; the id names a declared configuration, so one configuration still
# hashes identically wherever it runs.
FICHE_PROJECTIONS: dict[str, tuple[str, ...]] = {
    "1": (
        "cpu",
        "ram_gb",
        "gpu_name",
        "gpu_driver_version",
        "os",
        "cuda_ceiling",
        "llama_cpp_build",
        "quant",
        "roster_entry_id",
        "model_sha256",
    ),
    "2": (
        "cpu",
        "ram_gb",
        "gpu_name",
        "gpu_driver_version",
        "os",
        "cuda_ceiling",
        "engine_id",
        "engine_build",
        "engine_config_hash",
        "quant",
        "roster_entry_id",
        "model_sha256",
    ),
    "3": (
        "cpu",
        "ram_gb",
        "gpu_name",
        "gpu_driver_version",
        "os",
        "cuda_ceiling",
        "engine_id",
        "engine_build",
        "engine_config_hash",
        "machine_id",
        "compute_mode",
        "quant",
        "roster_entry_id",
        "model_sha256",
    ),
}

# The projection every fiche written today is hashed under.
CURRENT_FICHE_PROJECTION = "3"


def capture_fiche() -> HardwareFiche:
    """Capture the machine's hardware fiche. GPU fields degrade to None on failure."""
    gpu_name, gpu_driver_version, cuda_ceiling = _capture_gpu_fields()

    return HardwareFiche(
        cpu=platform.processor() or platform.machine(),
        ram_gb=_capture_ram_gb(),
        gpu_name=gpu_name,
        gpu_driver_version=gpu_driver_version,
        cuda_ceiling=cuda_ceiling,
        os=f"{platform.system()} {platform.release()}",
    )


def build_fiche(
    machine: HardwareFiche,
    *,
    engine_id: str,
    engine_build: str | None,
    engine_config_hash: str,
    machine_id: str,
    compute_mode: str,
    profile_id: str,
    roster_entry_id: str,
    model_sha256: str,
    quant: str,
    flags: list[str],
) -> Fiche:
    """Merge a machine capture with the fields that describe one run.

    No re-reading of the machine, no side effects: a plain dict for
    `machine` is enough to exercise this in a test.
    """
    return Fiche(
        **machine,
        engine_id=engine_id,
        engine_build=engine_build,
        engine_config_hash=engine_config_hash,
        machine_id=machine_id,
        compute_mode=compute_mode,
        profile_id=profile_id,
        roster_entry_id=roster_entry_id,
        model_sha256=model_sha256,
        quant=quant,
        flags=list(flags),
    )


def normalise_fiche(
    fiche: Mapping[str, Any], projection: str = CURRENT_FICHE_PROJECTION
) -> dict[str, Any]:
    """Project `fiche` to exactly the fields its identity hash is computed over.

    `projection` names a `FICHE_PROJECTIONS` version; the caller chooses it
    from the citing row's schema version, never from which keys `fiche`
    happens to hold. A fiche lacking a key of that projection raises
    `FicheProjectionError` naming it: a new fiche that forgot an engine field
    cannot pass as an old one.
    """
    keys = FICHE_PROJECTIONS[projection]
    missing = [key for key in keys if key not in fiche]
    if missing:
        raise FicheProjectionError(
            f"fiche lacks projection {projection!r} field(s): {', '.join(missing)}"
        )
    return {key: fiche[key] for key in keys}


def fiche_hash(
    fiche: Mapping[str, Any], projection: str = CURRENT_FICHE_PROJECTION
) -> str:
    """SHA-256 over the sorted-key JSON of `fiche`'s normalised projection.

    Sorted keys make the hash independent of dict insertion order without a
    bespoke serializer.
    """
    payload = json.dumps(normalise_fiche(fiche, projection), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _capture_ram_gb() -> float | None:
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 1)
    except Exception:  # noqa: BLE001 - best-effort capture, must never crash the run
        return None


def _capture_gpu_fields() -> tuple[str | None, str | None, str | None]:
    try:
        import pynvml

        with nvml_device(0) as handle:
            name = decode_nvml_str(pynvml.nvmlDeviceGetName(handle))
            driver_version = decode_nvml_str(pynvml.nvmlSystemGetDriverVersion())
            cuda_version = pynvml.nvmlSystemGetCudaDriverVersion()
            cuda_ceiling = f"{cuda_version // 1000}.{(cuda_version % 1000) // 10}"
            return name, driver_version, cuda_ceiling
    except Exception:  # noqa: BLE001 - best-effort capture, must never crash the run
        return None, None, None
