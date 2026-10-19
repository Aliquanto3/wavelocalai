"""Rouvrir, exporter et effacer une Arène (story 3.6), de bout en bout sur la vraie app.

Les modèles et le juge sont des `FakeChatModel` (aucun Ollama, aucun réseau). Un identifiant inconnu
rend `404 run_not_found` ; une Arène effacée (AD-13) perd sa question, ses réponses et ses raisons,
dans le `.db` comme dans le `-wal`, et garde ses lignes `runs` (registre carbone).
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path

import httpx

from wavelocalai.models.fake import FakeChatModel, Sleep
from wavelocalai.models.port import ModelRef
from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings
from .test_arena_api import _ended, _post, arena_app, children, cloud, local, say

SECRET_QUESTION = "Question-unique-3-6 : que pèse un nuage ?"
ANSWER_WORD = "Réponse-unique-3-6"
FAKE_KEY = "sk-FAKEKEY-3-6-abcdefghijklmnop"
JUDGE_REASON = "Raison-unique-3-6"


class ReasonJudge(FakeChatModel):
    """Un juge qui note 70 partout avec une raison reconnaissable (ou celle qu'on lui donne)."""

    def __init__(self, tag: str, reason: str = JUDGE_REASON) -> None:
        super().__init__([], ModelRef(tag, "fake", "local", "chat"))
        self.reason = reason

    async def stream(self, request):
        self.script = say(json.dumps({"score": 70, "reason": self.reason}))
        async for chunk in super().stream(request):
            yield chunk


async def finished_arena(client, *models, judge="fake:j", **body):
    response = await _post(client, *models, judge=judge, **body)
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    return run_id, await _ended(client, run_id)


async def test_an_unknown_id_is_a_404_run_not_found_with_the_id(tmp_path):
    async with arena_app(tmp_path, local("fake:a"), local("fake:b")) as (_, client):
        for method, path in (
            ("GET", "/api/runs/inconnu"),
            ("GET", "/api/runs/inconnu/events"),
            ("POST", "/api/runs/inconnu/cancel"),
            ("GET", "/api/arena/runs/inconnu.csv"),
            ("GET", "/api/arena/runs/inconnu.md"),
            ("DELETE", "/api/arena/runs/inconnu"),
        ):
            response = await client.request(method, path)
            body = response.json()
            assert response.status_code == 404, path
            assert body["code"] == "run_not_found" and body["detail"]["run_id"] == "inconnu", path
            assert body["message"] and body["action"]


async def test_the_snapshot_of_an_arena_carries_its_configuration(tmp_path):
    a, b = local("fake:a", say("Alpha")), local("fake:b", say("Bravo"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        run_id, snapshot = await finished_arena(
            client, "fake:a", "fake:b", prompt=SECRET_QUESTION, criteria=["clarté", "ton"]
        )
    assert snapshot["erased"] is False
    assert snapshot["config"] == {
        "models": ["fake:a", "fake:b"],
        "prompt": SECRET_QUESTION,
        "criteria": ["clarté", "ton"],
        "judge": "fake:j",
    }
    assert snapshot["run_id"] == run_id


async def test_the_list_gives_the_latest_arenas_first_with_models_and_a_question_excerpt(tmp_path):
    a, b = local("fake:a", say("Alpha")), local("fake:b", say("Bravo"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, a, b, judge) as (_, client):
        first, _ = await finished_arena(client, "fake:a", "fake:b", prompt="Première question")
        second, _ = await finished_arena(client, "fake:b", "fake:a", prompt="x" * 500)
        listed = (await client.get("/api/arena/runs")).json()["runs"]
        limited = (await client.get("/api/arena/runs?limit=1")).json()["runs"]
        assert (await client.get("/api/arena/runs?limit=0")).status_code == 422
    assert [run["run_id"] for run in listed] == [second, first]
    assert [run["run_id"] for run in limited] == [second]
    assert listed[0]["models"] == ["fake:b", "fake:a"] and listed[1]["models"] == [
        "fake:a",
        "fake:b",
    ]
    assert listed[1]["question"] == "Première question"
    assert len(listed[0]["question"]) == 200  # début de la question seulement
    assert listed[0]["status"] == "ok" and listed[0]["started_at"] and listed[0]["ended_at"]


async def test_the_csv_export_has_each_model_and_the_proof_of_the_measure(tmp_path):
    a, c = local("fake:a", say(ANSWER_WORD)), cloud("fake/c", say("Lumière"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, a, c, judge) as (_, client):
        run_id, _ = await finished_arena(
            client, "fake:a", "fake/c", prompt=SECRET_QUESTION, criteria=["clarté"]
        )
        response = await client.get(f"/api/arena/runs/{run_id}.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert f'filename="arene-{run_id[:8]}.csv"' in response.headers["content-disposition"]
    text = response.text
    assert text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    assert [row["model"] for row in rows] == ["fake:a", "fake/c"]
    first = rows[0]
    assert first["origin"] == "local" and first["score"] == "70" and first["reason"] == JUDGE_REASON
    assert first["tps"] and first["tps_source"] in {"ollama_eval", "wallclock"}
    assert first["co2_method"] and first["total_s"] != ""  # `load_s` : vide si inconnu
    assert first["question"] == SECRET_QUESTION and first["criteria"] == "clarté"
    # La preuve : fiche machine, version d'Ollama, digest, juge ; répétée sur chaque ligne.
    assert first["machine_os"] and first["app_version"] and first["exported_at"]
    assert first["judge"] == "fake:j" and first["judge_origin"] == "local"
    assert {"ollama_version", "model_digest", "machine_cpu", "machine_ram_gb"} <= set(first)
    assert rows[1]["origin"] == "cloud" and rows[1]["co2_method"] == "unmeasurable"
    assert rows[1]["co2_mg"] == "" and rows[1]["co2_reason"]  # non mesurable : vide, jamais 0
    assert rows[1]["machine_os"] == first["machine_os"]


async def test_the_markdown_export_names_the_proof_and_never_a_zero_for_an_unknown(tmp_path):
    a, c = local("fake:a", say(ANSWER_WORD)), cloud("fake/c", say("Lumière"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, a, c, judge) as (_, client):
        run_id, _ = await finished_arena(client, "fake:a", "fake/c", prompt=SECRET_QUESTION)
        response = await client.get(f"/api/arena/runs/{run_id}.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    text = response.text
    for part in (
        "# Comparaison wavelocalai",
        SECRET_QUESTION,
        "| fake:a |",
        "70/100",
        "## Preuve de la mesure",
        "- Machine :",
        "- Ollama : version",
        "- Digests des modèles :",
        "- Méthode du CO2 :",
        "- Juge : fake:j (local)",
        "- Critères de notation :",
        JUDGE_REASON,
        "non mesurable",
    ):
        assert part in text, part
    assert "0 mg" not in text


async def test_exports_never_contain_a_configured_key_and_neutralise_spreadsheet_formulas(
    tmp_path,
):
    settings = make_settings(
        tmp_path, environ={"WAVELOCALAI_TESTING": "1", "GROQ_API_KEY": FAKE_KEY}
    )
    a, b = local("fake:a", say("Alpha")), local("fake:b", say("Bravo"))
    judge = ReasonJudge("fake:j", reason='=HYPERLINK("http://x")')
    from wavelocalai.models.registry import ModelRegistry

    registry = ModelRegistry(settings, extra_refs={m.ref.tag: m.ref for m in (a, b, judge)})
    app = create_app(settings, registry=registry)
    app.state.models.update({m.ref.tag: m for m in (a, b, judge)})
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url=f"http://127.0.0.1:{TEST_PORT}"
        ) as client:
            run_id, _ = await finished_arena(
                client, "fake:a", "fake:b", prompt=f"Ma clé est {FAKE_KEY}"
            )
            csv_text = (await client.get(f"/api/arena/runs/{run_id}.csv")).text
            md_text = (await client.get(f"/api/arena/runs/{run_id}.md")).text
    for text in (csv_text, md_text):
        assert FAKE_KEY not in text and "FAKEKEY" not in text and "***" in text
        assert "api_key" not in text.lower()
    rows = list(csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))))
    assert rows[0]["reason"].startswith("'=HYPERLINK")  # jamais interprété comme une formule


async def test_exporting_a_running_arena_is_a_409_and_an_erased_one_a_404(tmp_path):
    slow = local("fake:a", [Sleep(5.0), *say("Lent")])
    b = local("fake:b", say("Bravo"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, slow, b, judge) as (app, client):
        run_id = (await _post(client, "fake:a", "fake:b", judge="fake:j")).json()["run_id"]
        busy = await client.get(f"/api/arena/runs/{run_id}.csv")
        assert busy.status_code == 409 and busy.json()["code"] == "arena_busy"
        await client.post(f"/api/runs/{run_id}/cancel")
        await _ended(client, run_id)
        assert (
            await client.get(f"/api/arena/runs/{run_id}.md")
        ).status_code == 200  # arrêtée : oui
        assert (await client.delete(f"/api/arena/runs/{run_id}")).status_code == 204
        gone = await client.get(f"/api/arena/runs/{run_id}.csv")
        assert gone.status_code == 404 and gone.json()["code"] == "run_not_found"
        assert app.state.hub is not None


async def test_erasing_an_arena_removes_the_text_from_the_database_and_the_journal(tmp_path):
    a, c = local("fake:a", say(ANSWER_WORD)), cloud("fake/c", say("Lumière"))
    d, e = local("fake:d", say("Autre")), local("fake:e", say("Mot"))
    judge, other_judge = ReasonJudge("fake:j"), ReasonJudge("fake:k", reason="Autre raison")
    async with arena_app(tmp_path, a, c, d, e, judge, other_judge) as (app, client):
        keep, _ = await finished_arena(
            client, "fake:d", "fake:e", judge="fake:k", prompt="Question gardée"
        )
        run_id, snapshot = await finished_arena(
            client, "fake:a", "fake/c", prompt=SECRET_QUESTION, criteria=["clarté"]
        )
        store = app.state.store
        db = Path(store.path)
        wal = db.with_name(db.name + "-wal")
        needles = (SECRET_QUESTION, ANSWER_WORD, JUDGE_REASON)

        def stored() -> bytes:
            return db.read_bytes() + (wal.read_bytes() if wal.exists() else b"")

        for needle in needles:
            assert needle.encode() in stored()  # le test sait voir le texte avant l'effacement
        co2_before = {child["run_id"]: child["metrics"]["co2"] for child in snapshot["children"]}
        session_before = (await client.get("/api/carbon/session")).json()

        response = await client.delete(f"/api/arena/runs/{run_id}")
        assert response.status_code == 204

        for needle in needles:
            assert needle.encode() not in db.read_bytes()
            assert needle.encode() not in wal.read_bytes()
        assert wal.stat().st_size == 0
        ids = [run_id, *co2_before]
        marks = ",".join("?" * len(ids))
        assert (
            store.read(
                f"SELECT count(*) AS n FROM run_events WHERE run_id IN ({marks})",
                tuple(ids),  # noqa: S608
            )[0]["n"]
            == 0
        )
        # Les lignes `runs` restent, sans texte, avec leur CO2 (registre carbone).
        after = (await client.get(f"/api/runs/{run_id}")).json()
        assert after["erased"] is True and after["config"] is None and after["verdict"] is None
        assert after["status"] == "ok"
        assert {c["run_id"]: c["metrics"]["co2"] for c in after["children"]} == co2_before
        assert (await client.get("/api/carbon/session")).json() == session_before
        # L'autre Arène est intacte, et seule l'effacée sort de la liste.
        listed = [run["run_id"] for run in (await client.get("/api/arena/runs")).json()["runs"]]
        assert listed == [keep]
        kept = (await client.get(f"/api/runs/{keep}")).json()
        assert kept["erased"] is False and kept["config"]["prompt"] == "Question gardée"
        # Effacer deux fois : sans erreur ; rouvrir son flux n'a plus rien à rejouer.
        assert (await client.delete(f"/api/arena/runs/{run_id}")).status_code == 204
        assert children(after)  # les feuilles restent listées


async def test_erasing_an_active_arena_is_a_409_and_changes_nothing(tmp_path):
    slow = local("fake:a", [Sleep(5.0), *say("Lent")])
    b = local("fake:b", say("Bravo"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, slow, b, judge) as (app, client):
        run_id = (
            await _post(client, "fake:a", "fake:b", judge="fake:j", prompt=SECRET_QUESTION)
        ).json()["run_id"]
        await asyncio.sleep(0.2)
        response = await client.delete(f"/api/arena/runs/{run_id}")
        body = response.json()
        assert response.status_code == 409 and body["code"] == "arena_busy"
        assert body["detail"]["run_id"] == run_id and body["message"] and body["action"]
        snapshot = (await client.get(f"/api/runs/{run_id}")).json()
        assert snapshot["status"] == "running" and snapshot["erased"] is False
        await client.post(f"/api/runs/{run_id}/cancel")
        await _ended(client, run_id)
        assert (await client.delete(f"/api/arena/runs/{run_id}")).status_code == 204
        assert app.state.hub is not None


async def test_only_an_arena_can_be_erased_through_the_arena_route(tmp_path):
    a, b = local("fake:a", say("Alpha")), local("fake:b", say("Bravo"))
    judge = ReasonJudge("fake:j")
    async with arena_app(tmp_path, a, b, judge) as (app, client):
        run_id, snapshot = await finished_arena(client, "fake:a", "fake:b")
        leaf = snapshot["children"][0]["run_id"]
        for path in (f"/api/arena/runs/{leaf}", f"/api/arena/runs/{leaf}.csv"):
            method = "DELETE" if not path.endswith(".csv") else "GET"
            response = await client.request(method, path)
            assert response.status_code == 404 and response.json()["code"] == "run_not_found"
        assert (await client.get(f"/api/runs/{run_id}")).json()["erased"] is False
        assert app.state.hub is not None
