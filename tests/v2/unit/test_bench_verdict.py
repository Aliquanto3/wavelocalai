"""Verdict de format du Banc d'essai (story 7.4) : la première violation, en clair."""

from __future__ import annotations

import pytest

from wavelocalai.inference.bench import RESPECTED, format_verdict
from wavelocalai.inference.scenarios import SCENARIOS, find_scenario

SCHEMA = find_scenario("traduction").schema
NBSP = " "


def test_respected_with_fence_and_pretty_output():
    verdict = format_verdict('```json\n{"en": "a", "es": "b", "de": "c"}\n```', SCHEMA)
    assert verdict["ok"] is True and verdict["message"] == RESPECTED
    assert verdict["formatted"] == '{\n  "en": "a",\n  "es": "b",\n  "de": "c"\n}'


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"en": "a", "es": "b"}', f"« de »{NBSP}: champ requis absent"),
        ('{"en": "a", "es": "b", "de": 3}', f"« de »{NBSP}: type attendu texte"),
        ('{"en": "a", "es": "b", "de": "c", "fr": "d"}', f"« fr »{NBSP}: champ non prévu"),
        ('["en"]', f"La réponse{NBSP}: type attendu objet"),
        ("", "La sortie est vide"),
    ],
)
def test_first_violation_in_plain_french(text, message):
    verdict = format_verdict(text, SCHEMA)
    assert verdict["ok"] is False and verdict["message"] == message


def test_only_json_scenarios_have_a_schema():
    assert [s.id for s in SCENARIOS if s.schema is None] == ["code", "raisonnement", "resume"]
