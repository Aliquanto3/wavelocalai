"""Export d'une Arène (story 3.6) : le document, le CSV et le Markdown, sur des données écrites à la
main. Fonctions pures : aucun serveur. Les parcours (routes, effacement, navigateur) vivent dans
`tests/v2/web/test_arena_reopen_api.py` et `tests/v2/e2e/test_arena_reopen.py`."""

from __future__ import annotations

import csv
import io

from wavelocalai.runs.arena_export import CSV_COLUMNS, export_document, to_csv, to_markdown

KEY = "sk-secret-0123456789abcdef"
CO2_LOCAL = {
    "mg": 1.8,
    "method": "codecarbon",
    "estimated": False,
    "range_mg": None,
    "allocation": "direct",
    "reason": None,
}
CO2_CLOUD = {
    "mg": None,
    "method": "unmeasurable",
    "estimated": False,
    "range_mg": None,
    "allocation": None,
    "reason": "fournisseur inconnu d'EcoLogits",
}


def leaf(model, origin, co2, **metrics):
    return {
        "run_id": f"leaf-{model}",
        "kind": "generation",
        "model": model,
        "status": "ok",
        "metrics": {
            "origin": origin,
            "tps": 38.4,
            "tps_source": "ollama_eval",
            "load_s": 0.42,
            "total_s": 1.2,
            "input_tokens": 4,
            "output_tokens": 12,
            "co2": co2,
            **metrics,
        },
    }


SNAPSHOT = {
    "run_id": "run-1234567890",
    "kind": "arena",
    "status": "ok",
    "started_at": "2026-10-19T10:00:00Z",
    "ended_at": "2026-10-19T10:00:09Z",
    "params": {"judge": "qwen3:8b"},
    "children": [
        leaf("qwen2.5:1.5b", "local", CO2_LOCAL),
        leaf("openai/gpt", "cloud", CO2_CLOUD, load_s=None, tps_source="wallclock"),
        {
            "run_id": "leaf-judge",
            "kind": "judge",
            "model": "qwen3:8b",
            "status": "ok",
            "metrics": {},
        },
    ],
}
RECORD = {
    "question": {"text": "Que pèse un nuage ?\nExplique.", "criteria": ["clarté", "ton"]},
    "judge": {
        "model": "qwen3:8b",
        "origin": "local",
        "params_active_b": 8.0,
        "unreliable": False,
        "single_judge": True,
        "default_criteria": ["exactitude"],
    },
    "scores": {
        "qwen2.5:1.5b": {
            "lane": "qwen2.5:1.5b",
            "score": 64,
            "reason": "=SOMME(1;1)",
            "judge": "qwen3:8b",
        },
        "openai/gpt": {"lane": "openai/gpt", "score": None, "reason": "non évalué : réponse vide"},
    },
    "lanes": {"qwen2.5:1.5b": {"status": "done"}, "openai/gpt": {"status": "done"}},
}
EVIDENCE = {
    "machine": {
        "os": "Windows 11",
        "cpu": "Intel64 Family 6",
        "ram_gb": 32.0,
        "accelerator": {"kind": "nvidia", "name": "RTX 3050"},
        "ollama_version": "0.40.6",
    },
    "digests": {"qwen2.5:1.5b": "sha256:abc123", "qwen3:8b": "sha256:def456", "openai/gpt": None},
}


def document(**overrides):
    args = {"snapshot": SNAPSHOT, "record": RECORD, "evidence": EVIDENCE, **overrides}
    return export_document(
        args["snapshot"], args["record"], args["evidence"], "2026-10-19T11:00:00Z", "2.0.0a3"
    )


def test_the_document_has_per_model_results_and_the_proof_of_the_measure():
    doc = document()
    assert doc["format"] == "wavelocalai.arena/1" and doc["app_version"] == "2.0.0a3"
    first, second = doc["models"]
    assert first["model"] == "qwen2.5:1.5b" and first["score"] == 64 and first["tps"] == 38.4
    assert first["tps_source"] == "ollama_eval" and first["digest"] == "sha256:abc123"
    assert second["score"] is None and second["reason"] == "non évalué : réponse vide"
    proof = doc["proof"]
    assert proof["ollama_version"] == "0.40.6" and proof["machine"]["os"] == "Windows 11"
    # Les digests des modèles comparés et celui du juge ; un digest inconnu reste `None`.
    assert proof["model_digests"] == {
        "qwen2.5:1.5b": "sha256:abc123",
        "openai/gpt": None,
        "qwen3:8b": "sha256:def456",
    }
    assert proof["co2_methods"] == ["codecarbon", "unmeasurable"]
    assert proof["judge"]["model"] == "qwen3:8b" and proof["judge"]["criteria"] == ["clarté", "ton"]


def test_without_criteria_in_the_question_the_judge_default_criteria_are_the_proof():
    record = {**RECORD, "question": {"text": "Q", "criteria": []}}
    assert document(record=record)["proof"]["judge"]["criteria"] == ["exactitude"]


def test_the_csv_repeats_the_proof_on_each_row_and_never_writes_a_zero_for_an_unknown():
    text = to_csv(document())
    assert text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    assert list(rows[0]) == list(CSV_COLUMNS)
    local, cloud = rows
    assert (
        local["score"] == "64" and local["co2_mg"] == "1.8" and local["co2_method"] == "codecarbon"
    )
    assert local["model_digest"] == "sha256:abc123" and local["ollama_version"] == "0.40.6"
    assert local["machine_accelerator"] == "RTX 3050" and local["judge"] == "qwen3:8b"
    assert local["criteria"] == "clarté | ton" and local["question"].startswith("Que pèse un nuage")
    assert cloud["score"] == "" and cloud["co2_mg"] == "" and cloud["load_s"] == ""
    assert cloud["co2_method"] == "unmeasurable" and cloud["model_digest"] == ""
    assert cloud["co2_estimated"] == "non"
    assert cloud["machine_os"] == "Windows 11"  # la preuve suit chaque ligne


def test_a_text_that_would_start_a_formula_is_written_as_text_in_the_csv():
    rows = list(csv.DictReader(io.StringIO(to_csv(document()).lstrip("﻿"))))
    assert rows[0]["reason"] == "'=SOMME(1;1)"
    record = {**RECORD, "question": {"text": "@cmd|' /C calc'!A0", "criteria": []}}
    rows = list(csv.DictReader(io.StringIO(to_csv(document(record=record)).lstrip("﻿"))))
    assert rows[0]["question"].startswith("'@cmd")


def test_the_markdown_has_the_table_the_proof_and_the_definitions():
    text = to_markdown(document())
    for part in (
        "# Comparaison wavelocalai",
        "> Que pèse un nuage ?",
        "> Explique.",
        "| qwen2.5:1.5b | local | 64/100 |",
        "38,4 tokens/s (mesuré par Ollama (D3))",
        "1,8 mg (codecarbon, mesuré)",
        "non mesurable (fournisseur inconnu d'EcoLogits)",
        "non évalué (non évalué : réponse vide)",
        "## Preuve de la mesure",
        "- Machine : Windows 11, Intel64 Family 6, mémoire 32 Go, RTX 3050",
        "- Ollama : version 0.40.6",
        "qwen2.5:1.5b sha256:abc123",
        "openai/gpt inconnu",
        "- Méthode du CO2 : codecarbon, unmeasurable",
        "- Juge : qwen3:8b (local), un seul juge",
        "- Critères de notation : clarté, ton",
        "## Raisons du juge",
        "## Définitions",
    ):
        assert part in text, part
    assert "| 0 mg" not in text


def test_a_configured_key_is_masked_everywhere_in_the_document():
    record = {**RECORD, "question": {"text": f"Ma clé est {KEY}", "criteria": []}}
    doc = export_document(
        SNAPSHOT, record, EVIDENCE, "2026-10-19T11:00:00Z", "2.0.0a3", secrets=[KEY]
    )
    for text in (to_csv(doc), to_markdown(doc), str(doc)):
        assert KEY not in text
    assert "***" in to_markdown(doc)


def test_the_exports_carry_the_stopped_reason_of_a_lane_stopped_early():
    # Story 9.2 : la raison d'arrêt (`lane_status.stopped_reason`) va dans le document, en dernière
    # colonne du CSV (les colonnes existantes ne bougent pas) et dans la colonne « Arrêt » du
    # Markdown ; une lane finie d'elle-même n'en a pas.
    lanes = {
        "qwen2.5:1.5b": {"status": "done", "stopped_reason": "loop"},
        "openai/gpt": {"status": "done"},
    }
    doc = document(record={**RECORD, "lanes": lanes})
    assert [m["stopped_reason"] for m in doc["models"]] == ["loop", None]
    rows = list(csv.reader(io.StringIO(to_csv(doc).lstrip("﻿"))))
    assert rows[0][-1] == "stopped_reason" and rows[0][:5] == [
        "run_id",
        "question",
        "model",
        "origin",
        "status",
    ]
    assert rows[1][-1] == "loop" and rows[2][-1] == ""
    markdown = to_markdown(doc)
    assert "| Arrêt |" in markdown and "arrêtée : le modèle se répétait" in markdown
