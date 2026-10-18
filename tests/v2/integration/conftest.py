"""Tests contre le vrai Ollama : ici CodeCarbon aussi est le vrai (le double des autres tests en est
écarté)."""

from __future__ import annotations

import pytest

from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.local_meter import load_tracker_class as real_loader  # avant le double


@pytest.fixture
def real_meter() -> LocalMeter:
    """Compteur CodeCarbon réel, pays et PUE des réglages par défaut."""
    return LocalMeter("FRA", 1.1, loader=real_loader)
