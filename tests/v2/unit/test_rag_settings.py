"""Réglages de la base documentaire : les préférences priment sur le `.toml` (AD-15, story 4.3)."""

from __future__ import annotations

import pytest

from wavelocalai.config import RagSettings
from wavelocalai.rag.settings import PREF_KEY, RagTunables, effective, stored_overrides
from wavelocalai.store.preferences import InMemoryPreferenceStore

TOML = RagSettings(chunk_size=800, chunk_overlap=100, top_k=4, embedding_model="nomic:latest")


def test_without_preferences_the_toml_applies():
    assert effective(TOML, None) == RagTunables("nomic:latest", 800, 100, 4, "naive")
    assert effective(TOML, InMemoryPreferenceStore()) == effective(TOML, None)


def test_a_preference_wins_key_by_key():
    prefs = InMemoryPreferenceStore()
    prefs.put(PREF_KEY, {"chunk_size": 300, "top_k": 2, "embedding_model": "autre:1"})
    assert effective(TOML, prefs) == RagTunables("autre:1", 300, 100, 2, "naive")


@pytest.mark.parametrize(
    "stored",
    [
        {"chunk_size": "300"},
        {"chunk_size": 50},
        {"chunk_size": True},
        {"top_k": 0},
        {"top_k": 99},
        {"strategy": "hyde"},
        {"embedding_model": "   "},
        {"embedding_model": 3},
        "pas un dictionnaire",
        ["x"],
    ],
)
def test_an_invalid_stored_value_falls_back_to_the_toml(stored):
    prefs = InMemoryPreferenceStore()
    prefs.put(PREF_KEY, stored)
    assert effective(TOML, prefs) == effective(TOML, None)


def test_the_overlap_stays_under_the_size_even_when_the_toml_changed_since():
    prefs = InMemoryPreferenceStore()
    prefs.put(PREF_KEY, {"chunk_size": 150})  # le recouvrement du .toml (100) reste permis
    assert effective(TOML, prefs).chunk_overlap == 100
    prefs.put(PREF_KEY, {"chunk_size": 100})  # 100 >= 100 : ramené à la moitié
    assert effective(TOML, prefs).chunk_overlap == 50


def test_stored_overrides_are_a_copy_of_what_the_user_chose_only():
    prefs = InMemoryPreferenceStore()
    assert stored_overrides(prefs) == {} and stored_overrides(None) == {}
    prefs.put(PREF_KEY, {"top_k": 2})
    copy = stored_overrides(prefs)
    copy["top_k"] = 9
    assert prefs.get(PREF_KEY) == {"top_k": 2}
