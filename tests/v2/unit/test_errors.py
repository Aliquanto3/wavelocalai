"""`errors.py` : liste fermée, enveloppe `{code, message, action, detail}`, masquage des clés."""

from __future__ import annotations

import pytest

from wavelocalai.errors import ERRORS, AppError, build_envelope, mask_secrets

REQUIRED = {"ollama_down", "forbidden_host", "forbidden_origin", "internal"}


def test_initial_closed_list():
    assert set(ERRORS) >= REQUIRED
    for spec in ERRORS.values():
        assert spec.message and spec.action  # en français, jamais vides
        assert spec.message.endswith(".") and spec.status >= 400


def test_envelope_shape_and_declared_keys():
    envelope = build_envelope("forbidden_host", "Host refusé", host="evil.example")
    assert list(envelope) == ["code", "message", "action", "detail"]
    assert envelope["code"] == "forbidden_host"
    assert envelope["detail"] == {"technical": "Host refusé", "host": "evil.example"}


def test_undeclared_detail_key_and_unknown_code_are_refused():
    with pytest.raises(ValueError, match="non déclarées"):
        build_envelope("internal", run_id="abc")
    with pytest.raises(ValueError, match="inconnu"):
        build_envelope("code_inconnu")
    with pytest.raises(ValueError, match="inconnu"):
        AppError("code_inconnu")


@pytest.mark.parametrize(
    "leaky",
    [
        "appel refusé avec sk-proj-AbCdEf0123456789",
        "clé sk-ant-api03-abcdefghijklmnop",
        "Authorization: Bearer abcdef1234567890",
        'api_key="abcd1234efgh5678"',
        "gsk_abcdefghijkl1234",
    ],
)
def test_text_values_of_detail_are_masked(leaky):
    envelope = build_envelope("internal", leaky)
    technical = envelope["detail"]["technical"]
    for fragment in (
        "sk-proj",
        "sk-ant",
        "abcdef1234567890",
        "abcd1234efgh5678",
        "gsk_abcdefghijkl",
    ):
        assert fragment not in technical
    assert "***" in technical


def test_masking_also_covers_known_secret_values_and_nested_detail():
    envelope = build_envelope("internal", "échec avec ZZtopSecret99", secrets=["ZZtopSecret99"])
    assert "ZZtopSecret99" not in envelope["detail"]["technical"]
    assert mask_secrets("rien à cacher ici") == "rien à cacher ici"
    assert mask_secrets("token=abc") == "token=***" or "abc" not in mask_secrets("token=abc")


def test_prefixed_env_var_names_are_masked():
    from wavelocalai.errors import mask_secrets

    text = mask_secrets("MISTRAL_API_KEY=abcd1234efgh ANTHROPIC_API_KEY: zzzz9999yyyy")
    assert "abcd1234efgh" not in text and "zzzz9999yyyy" not in text
    assert text.startswith("MISTRAL_API_KEY=***")


def test_chat_codes_are_declared_and_none_reuses_a_status_name():
    # AD-5 : aucun code d'erreur ne reprend un nom de statut (d'où `generation_interrupted`).
    from wavelocalai.runs.models import STATUSES

    assert not set(ERRORS) & set(STATUSES)
    envelope = build_envelope("timeout", "300 s", timeout_s=300.0)
    assert envelope["detail"] == {"technical": "300 s", "timeout_s": 300.0}
    assert ERRORS["generation_interrupted"].detail_keys == ()
    assert ERRORS["ollama_error"].status == 502
