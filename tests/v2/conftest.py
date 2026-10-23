"""Outils communs aux tests de la v2 : réglages isolés, base et données en dossier temporaire."""

from __future__ import annotations

import functools
import os
import socket
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from wavelocalai.config import Settings, load_settings
from wavelocalai.telemetry import TELEMETRY_OPT_OUTS

TEST_PORT = 8502


@functools.cache
def vec_loadable() -> bool:
    """`sqlite-vec` se charge-t-il ici ? Faux avec un CPython sans `enable_load_extension`
    (Python de `setup-python` sur macOS) : l'application bascule alors sur `NumpyIndex`."""
    from wavelocalai.store.vec import load_vec

    conn = sqlite3.connect(":memory:")
    try:
        return load_vec(conn)
    finally:
        conn.close()


needs_vec = pytest.mark.skipif(
    not vec_loadable(), reason="l'extension sqlite-vec ne se charge pas sur cette plateforme"
)


def closed_port() -> int:
    """Un port local libre, puis refermé : rien n'y écoute (Ollama « injoignable »)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_settings(
    tmp_path: Path, environ: dict[str, str] | None = None, **overrides: Any
) -> Settings:
    """`Settings` isolés : ni `.toml` ni `.env` du dépôt, environnement vide, données en tmp.

    Ollama pointe par défaut sur un port fermé (aucun vrai réseau).
    """
    merged: dict[str, Any] = {
        "data": {"dir": tmp_path / "data"},
        "ollama": {"host": f"http://127.0.0.1:{closed_port()}"},
    }
    for section, values in overrides.items():
        merged.setdefault(section, {}).update(values)
    return load_settings(
        toml_path=tmp_path / "absent.toml",
        env_file=tmp_path / "absent.env",
        environ=environ or {},
        overrides=merged,
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture(autouse=True)
def _restore_telemetry_env():
    """`create_app` applique les opt-outs de télémétrie à `os.environ` : on les retire après."""
    before = {name: os.environ.get(name) for name in TELEMETRY_OPT_OUTS}
    yield
    for name, value in before.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


@pytest.fixture(autouse=True)
def _stub_codecarbon(monkeypatch):
    """Les tests ne lancent jamais le vrai CodeCarbon (plusieurs secondes de détection du matériel) :
    le compteur par défaut de l'app prend un double. Les tests de la vraie mesure construisent leur
    `LocalMeter` avec `real_loader` (importé avant ce remplacement)."""
    from wavelocalai.greenops import local_meter

    from .carbon_stub import Probe

    probe = Probe()
    monkeypatch.setattr(local_meter, "load_tracker_class", probe.tracker_class)
    return probe
