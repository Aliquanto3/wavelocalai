"""`errors.py` : liste fermée, enveloppe `{code, message, action, detail}`, masquage des clés."""

from __future__ import annotations

import re

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


def test_timeout_message_names_the_real_delay():
    # Écart n° 1 : « Délai dépassé (120 s) », partout ; un délai entier sans décimale, sinon à la
    # française.
    assert build_envelope("timeout", None, timeout_s=120.0)["message"].startswith(
        "Délai dépassé (120 s)"
    )
    assert build_envelope("timeout", None, timeout_s=300)["message"].startswith(
        "Délai dépassé (300 s)"
    )
    assert build_envelope("timeout", None, timeout_s=0.3)["message"].startswith(
        "Délai dépassé (0,3 s)"
    )
    # Revue 8.1b : sans délai connu, jamais « (timeout_s s) ».
    assert build_envelope("timeout", None)["message"] == (
        "Délai dépassé : le modèle n'a pas fini de répondre."
    )
    assert build_envelope("timeout", None, timeout_s=1234)["message"].startswith(
        "Délai dépassé (1234 s)"
    )


def test_cloud_codes_name_the_provider_and_the_key_variable():
    detail = {"provider": "groq", "provider_name": "Groq", "key_var": "GROQ_API_KEY"}
    missing = build_envelope("cloud_key_missing", "x", **detail)
    assert "Groq" in missing["message"] and "GROQ_API_KEY" in missing["action"]
    assert ".env" in missing["action"] and "{" not in missing["message"] + missing["action"]
    unreachable = build_envelope("cloud_unreachable", None, provider="groq", provider_name="Groq")
    assert "Groq" in unreachable["message"] and "Local" in unreachable["action"]
    refused = build_envelope("cloud_key_refused", None, http_status=401, **detail)
    assert refused["detail"]["http_status"] == 401
    bare = build_envelope("cloud_error")  # sans detail : formule neutre, jamais d'accolade
    assert "{" not in bare["message"] and "le fournisseur" in bare["message"]
    from wavelocalai.runs.models import STATUSES

    assert not {c for c in ERRORS if c.startswith("cloud_")} & set(STATUSES)


def test_conversation_busy_is_a_409_that_names_the_active_run():
    spec = ERRORS["conversation_busy"]
    assert spec.status == 409 and spec.detail_keys == ("run_id",)
    envelope = build_envelope("conversation_busy", "run actif", run_id="abc")
    assert envelope["detail"] == {"technical": "run actif", "run_id": "abc"}
    assert envelope["message"] and envelope["action"]


def test_run_not_found_is_a_404_and_arena_busy_a_409_that_name_the_run():
    """Story 3.6 : un identifiant de run inconnu, et l'effacement d'une Arène encore active."""
    assert ERRORS["run_not_found"].status == 404 and ERRORS["run_not_found"].detail_keys == (
        "run_id",
    )
    assert ERRORS["arena_busy"].status == 409 and ERRORS["arena_busy"].detail_keys == ("run_id",)
    for code in ("run_not_found", "arena_busy"):
        envelope = build_envelope(code, "détail", run_id="abc")
        assert envelope["detail"]["run_id"] == "abc"
        assert envelope["message"] and envelope["action"] and "{" not in envelope["message"]


# --- Source unique des textes d'erreur du front (C9) -----------------------------------------


def test_error_texts_are_generated_from_the_closed_list_without_markdown():
    from wavelocalai.errors import ERRORS, error_texts

    texts = error_texts()
    assert set(texts) == set(ERRORS)
    for code, spec in ERRORS.items():
        plain = {k: v.replace(" ", " ") for k, v in texts[code].items()}
        assert plain["message"] == spec.message
        assert plain["action"] == spec.action.replace("`", "")
        assert "`" not in texts[code]["action"]
        assert not re.search(r" [;:!?»]|« ", texts[code]["message"] + texts[code]["action"])
    assert texts["ollama_down"]["action"].startswith("Lancez Ollama (application ou ollama serve)")


def test_no_text_file_declares_the_generated_errors_key():
    """Le front lit `errors.*` du catalogue généré : aucun `i18n/fr/*.json` ne le recopie."""
    import json

    from wavelocalai.web.routes_static import STATIC_DIR

    for path in (STATIC_DIR / "i18n" / "fr").glob("*.json"):
        assert "errors" not in json.loads(path.read_text(encoding="utf-8")), path.name


def test_a_text_file_that_redeclares_errors_stops_the_assembly(tmp_path):
    import pytest

    from wavelocalai.web.routes_static import text_catalog

    folder = tmp_path / "i18n" / "fr"
    folder.mkdir(parents=True)
    (folder / "a.json").write_text(
        '{"errors": {"ollama_down": {"message": "x"}}}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="errors"):
        text_catalog(tmp_path)
