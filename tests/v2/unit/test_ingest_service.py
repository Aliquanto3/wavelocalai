"""Service d'ingestion (story 4.1) : run `ingest`, feuilles `embedding` mesurées, échecs fichier par
fichier, annulation, doublons. Le hub, le store et l'index sont les vrais ; l'embedder est le `fake`
scriptable, CodeCarbon un double ; aucun réseau (Ollama pointe sur un port fermé)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from wavelocalai.errors import AppError, ProviderError
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import session_summary
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.fake import (
    FAKE_EMBED_REF,
    FAKE_REF,
    FakeChatModel,
    FakeEmbedder,
    Sleep,
)
from wavelocalai.models.port import ModelRef
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag import repo
from wavelocalai.rag.index import NumpyIndex, SqliteVecIndex, VectorIndex
from wavelocalai.rag.ingest import IngestService
from wavelocalai.rag.split import ChunkDraft
from wavelocalai.rag.staging import StagedFile
from wavelocalai.runs.hub import RunHub
from wavelocalai.store.db import Store, db_path

from ..carbon_stub import Probe
from ..conftest import make_settings
from ..rag_files import make_blank_pdf, make_docx, make_encrypted_text_pdf, make_pdf

OTHER_REF = ModelRef("fake-other:16", "fake", "local", "embedding")
LONG_TEXT = " ".join(f"mot{i:03d}" for i in range(200))  # ~1400 caractères


class Bus:
    """Port `SystemBus` enregistreur."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def publish(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append((event_type, data))


class Rig:
    def __init__(self, tmp_path, store, hub, service, embedder, slot, probe, bus, index, settings):
        self.tmp_path = tmp_path
        self.store, self.hub, self.service = store, hub, service
        self.embedder, self.slot, self.probe = embedder, slot, probe
        self.bus, self.index, self.settings = bus, index, settings
        self.count = 0

    def stage(self, files: Mapping[str, bytes | str]) -> tuple[list[StagedFile], Path]:
        self.count += 1
        directory = self.tmp_path / f"staging-{self.count}"
        directory.mkdir()
        staged = []
        for i, (name, data) in enumerate(files.items(), 1):
            raw = data if isinstance(data, bytes) else data.encode("utf-8")
            path = directory / f"{i:04d}{Path(name).suffix.lower()}"
            path.write_bytes(raw)
            staged.append(StagedFile(name, path, hashlib.sha256(raw).hexdigest(), len(raw)))
        return staged, directory

    async def ingest(self, files, model: str | None = None, **kwargs):
        staged, directory = self.stage(files)
        handle = await self.service.start(staged, directory, model, **kwargs)
        return handle, directory

    async def finished(self, run_id: str, timeout: float = 5.0) -> list[dict[str, Any]]:
        async with asyncio.timeout(timeout):
            while self.hub.watch(run_id) is not None:
                await asyncio.sleep(0.01)
        return await self.hub.events_after(run_id)

    async def run(self, files, model: str | None = None):
        handle, directory = await self.ingest(files, model)
        return handle.run_id, await self.finished(handle.run_id), directory

    def docs(self) -> dict[str, Any]:
        rows = self.store.read("SELECT * FROM documents ORDER BY created_at, source")
        return {r["source"]: r for r in rows}

    def chunks(self, source: str | None = None) -> int:
        if source is None:
            return self.store.read("SELECT count(*) AS n FROM chunks")[0]["n"]
        sql = "SELECT count(*) AS n FROM chunks c JOIN documents d ON d.id = c.document_id"
        return self.store.read(sql + " WHERE d.source = ?", (source,))[0]["n"]

    def vectors(self) -> int:
        return self.store.write(lambda conn: self.index.count(conn)).result()

    def leaves(self, run_id: str):
        return self.store.read(
            "SELECT * FROM runs WHERE parent_run_id = ? ORDER BY started_at, rowid", (run_id,)
        )


@pytest.fixture(params=["sqlite-vec", "numpy"])
def index(request) -> VectorIndex:
    return SqliteVecIndex() if request.param == "sqlite-vec" else NumpyIndex()


@pytest.fixture
async def rig(tmp_path, index, _stub_codecarbon):
    settings = make_settings(
        tmp_path,
        environ={"WAVELOCALAI_TESTING": "1"},
        rag={"embed_batch_size": 4, "chunk_size": 200, "chunk_overlap": 20},
    )
    store = Store.open(db_path(settings.data_dir))
    hub = RunHub(store, batch_interval_s=3600)
    await hub.start()
    embedder = FakeEmbedder()
    other = FakeEmbedder(ref=OTHER_REF)
    chat = FakeChatModel()
    registry = ModelRegistry(
        settings,
        extra_refs={
            FAKE_EMBED_REF.tag: FAKE_EMBED_REF,
            OTHER_REF.tag: OTHER_REF,
            FAKE_REF.tag: FAKE_REF,
        },
    )
    factory = ModelFactory(
        None,  # type: ignore[arg-type] - aucun appel Ollama
        {FAKE_REF.tag: chat},
        {FAKE_EMBED_REF.tag: embedder, OTHER_REF.tag: other},
    )
    slot, bus = LocalSlot(), Bus()
    meter = LocalMeter("FRA", 1.1, loader=_stub_codecarbon.loader())
    service = IngestService(
        hub, registry, factory, slot, settings, index, meter=meter, bus=bus,
        fallback_model=FAKE_EMBED_REF.tag,
    )  # fmt: skip
    yield Rig(tmp_path, store, hub, service, embedder, slot, _stub_codecarbon, bus, index, settings)
    await hub.stop()
    store.close()


def of_type(events, name):
    return [e["data"] for e in events if e["type"] == name]


# --- parcours nominal ----------------------------------------------------------------------------


async def test_a_text_file_is_indexed_in_batches_of_measured_embedding_leaves(rig):
    run_id, events, directory = await rig.run({"notes.txt": LONG_TEXT, "court.md": "Un seul mot."})

    # le run `ingest` finit `ok`, ses documents sont `ready`
    assert events[0]["type"] == "run_started" and events[-1]["data"] == {
        "status": "ok",
        "error": None,
    }
    docs = rig.docs()
    assert {name: d["status"] for name, d in docs.items()} == {
        "notes.txt": "ready",
        "court.md": "ready",
    }
    assert docs["court.md"]["chunk_count"] == 1 and docs["notes.txt"]["chunk_count"] > 4
    assert rig.chunks() == sum(d["chunk_count"] for d in docs.values()) == rig.vectors()
    assert docs["notes.txt"]["embedding_model"] == FAKE_EMBED_REF.tag
    assert docs["notes.txt"]["embedding_dim"] == 16 and docs["notes.txt"]["ready_at"]

    # un lot = une feuille `embedding`, rattachée au run, mesurée par CodeCarbon
    leaves = rig.leaves(run_id)
    batches = [len(texts) for texts in rig.embedder.texts]
    assert len(leaves) == len(batches) > 1 and max(batches) == 4
    assert {leaf["kind"] for leaf in leaves} == {"embedding"}
    assert {leaf["status"] for leaf in leaves} == {"ok"}
    assert {leaf["model"] for leaf in leaves} == {FAKE_EMBED_REF.tag}
    assert {(leaf["co2_method"], leaf["origin"]) for leaf in leaves} == {("codecarbon", "local")}
    assert all(leaf["co2_mg"] == pytest.approx(1.8) for leaf in leaves)
    assert all(leaf["energy_wh"] == pytest.approx(0.001) for leaf in leaves)
    assert rig.probe.started == rig.probe.stopped == len(leaves)
    assert rig.probe.peak == 1  # un seul tracker à la fois (AD-11)

    # la racine ne porte ni métriques ni CO2 ; le staging est supprimé
    root = rig.store.read("SELECT * FROM runs WHERE id = ?", (run_id,))[0]
    assert (root["kind"], root["status"], root["co2_method"]) == ("ingest", "ok", None)
    assert not directory.exists()


async def test_progress_events_follow_each_file_through_its_phases(rig):
    _, events, _ = await rig.run({"a.txt": LONG_TEXT, "b.txt": "Bref."})
    progress = of_type(events, "ingest_progress")
    first = [p for p in progress if p["file"] == "a.txt"]
    assert [(p["phase"], p["done"], p["total"]) for p in first[:4]] == [
        ("extract", 0, 1),
        ("extract", 1, 1),
        ("split", 0, 1),
        ("split", 1, 1),
    ]
    embed = [p for p in first if p["phase"] == "embed"]
    total = embed[0]["total"]
    assert [p["done"] for p in embed] == sorted({p["done"] for p in embed}) and embed[-1][
        "done"
    ] == total
    assert embed[0]["done"] == 0 and total == rig.docs()["a.txt"]["chunk_count"]
    assert {(p["file_index"], p["file_count"]) for p in first} == {(1, 2)}
    done = of_type(events, "ingest_file_done")
    assert [(d["file"], d["status"], d["error"]) for d in done] == [
        ("a.txt", "ready", None),
        ("b.txt", "ready", None),
    ]
    assert done[0]["chunks"] == total and done[0]["document_id"] == rig.docs()["a.txt"]["id"]
    # l'ordre : tous les événements de a.txt avant ceux de b.txt
    files = [e["data"]["file"] for e in events if e["type"].startswith("ingest_")]
    assert files == sorted(files)


async def test_pdf_and_docx_are_indexed_with_their_pages(rig):
    _, events, _ = await rig.run(
        {
            "r.pdf": make_pdf(["Page un du rapport", "Page deux du rapport"]),
            "w.docx": make_docx(["Titre du document", "Un paragraphe."]),
        }
    )
    docs = rig.docs()
    assert docs["r.pdf"]["status"] == docs["w.docx"]["status"] == "ready"
    assert docs["r.pdf"]["page_count"] == 2 and docs["w.docx"]["page_count"] is None
    pages = rig.store.read(
        "SELECT c.page FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE d.source = 'r.pdf' ORDER BY c.position"
    )
    assert [p["page"] for p in pages] == [1, 2]


async def test_the_run_params_and_events_carry_no_file_text_or_name(rig):
    run_id, _, _ = await rig.run({"secret-client.txt": "contenu confidentiel du client"})
    params = json.loads(rig.store.read("SELECT params FROM runs WHERE id = ?", (run_id,))[0][0])
    assert params == {
        "embedding_model": FAKE_EMBED_REF.tag,
        "file_count": 1,
        "batch_size": 4,
        "chunk_size": 200,
        "chunk_overlap": 20,
    }
    started = rig.store.read(
        "SELECT data FROM run_events WHERE run_id = ? AND type = 'run_started'", (run_id,)
    )[0][0]
    assert "confidentiel" not in started and "secret-client" not in started


# --- CO2 ----------------------------------------------------------------------------------------


async def test_every_batch_counts_in_the_session_co2_and_announces_carbon_updated(rig):
    run_id, _, _ = await rig.run({"a.txt": LONG_TEXT})
    n = len(rig.leaves(run_id))
    summary = await session_summary(rig.store, rig.hub.app_session_id)
    assert summary["by_module"]["ingest"] == {
        "mg": pytest.approx(1.8 * n),
        "runs": n,
        "unmeasurable_runs": 0,
    }
    assert summary["by_origin"]["local"]["runs"] == n and summary["unmeasurable_runs"] == 0
    updates = [data for kind, data in rig.bus.events if kind == "carbon_updated"]
    assert len(updates) >= n and updates[-1]["total_mg"] == pytest.approx(1.8 * n)


async def test_a_codecarbon_failure_leaves_the_batch_ok_and_unmeasurable(rig):
    rig.probe.start_error = RuntimeError("pas de capteur")
    run_id, events, _ = await rig.run({"a.txt": "Un petit texte."})
    assert events[-1]["data"]["status"] == "ok" and rig.docs()["a.txt"]["status"] == "ready"
    leaf = rig.leaves(run_id)[0]
    assert (leaf["co2_method"], leaf["co2_mg"], leaf["status"]) == ("unmeasurable", None, "ok")
    assert leaf["co2_reason"]


async def test_an_import_without_any_embedding_batch_is_not_an_unmeasurable_leaf(rig):
    await rig.run({"a.txt": "Même contenu."})
    await rig.run({"a-copie.txt": "Même contenu."})  # doublon : aucun lot
    await rig.run({"vide.txt": ""})  # échec avant tout lot
    summary = await session_summary(rig.store, rig.hub.app_session_id)
    assert summary["by_module"]["ingest"]["runs"] == 1  # le seul lot du premier import
    assert summary["unmeasurable_runs"] == 0


# --- échecs fichier par fichier ------------------------------------------------------------------


async def test_unreadable_files_fail_one_by_one_and_the_others_continue(rig):
    run_id, events, _ = await rig.run(
        {
            "bon.txt": "Du texte à indexer.",
            "vide.txt": "   ",
            "protege.pdf": make_encrypted_text_pdf(),
            "scan.pdf": make_blank_pdf(),
            "tableur.xlsx": b"PK\x03\x04",
            "autre.md": "Un second bon fichier.",
        }
    )
    assert events[-1]["data"]["status"] == "ok"  # l'orchestration aboutit (AD-5)
    docs = rig.docs()
    assert {n: d["status"] for n, d in docs.items()} == {
        "bon.txt": "ready",
        "vide.txt": "failed",
        "protege.pdf": "failed",
        "scan.pdf": "failed",
        "tableur.xlsx": "failed",
        "autre.md": "ready",
    }
    reasons = {}
    for name, doc in docs.items():
        if doc["status"] == "failed":
            error = json.loads(doc["error"])
            assert error["code"] == "ingest_failed" and error["message"]
            assert error["detail"]["file"] == name
            reasons[name] = error["detail"]["reason"]
            assert doc["chunk_count"] == 0 and rig.chunks(name) == 0
    assert "mot de passe" in reasons["protege.pdf"] and "vide" in reasons["vide.txt"]
    assert "numérisé" in reasons["scan.pdf"] and "xlsx" in reasons["tableur.xlsx"]
    done = {d["file"]: d for d in of_type(events, "ingest_file_done")}
    assert (
        done["vide.txt"]["status"] == "failed"
        and done["vide.txt"]["error"]["code"] == "ingest_failed"
    )
    assert done["bon.txt"]["status"] == "ready"
    # seuls les `ready` comptent, et seuls leurs vecteurs existent
    ready = sum(1 for d in docs.values() if d["status"] == "ready")
    assert ready == 2 and rig.chunks() == rig.vectors() == 2


async def test_an_oversized_file_fails_with_its_reason_without_embedding(rig):
    staged, directory = rig.stage({"gros.txt": "x"})
    big = StagedFile(
        "gros.txt", staged[0].path, staged[0].fingerprint, 99, "le fichier dépasse 1 Mo"
    )
    handle = await rig.service.start([big], directory)
    await rig.finished(handle.run_id)
    error = json.loads(rig.docs()["gros.txt"]["error"])
    assert error["detail"]["reason"] == "le fichier dépasse 1 Mo" and rig.embedder.calls == 0


async def test_a_file_outside_the_allowed_folders_is_refused(rig, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(rig.tmp_path / "ailleurs"))
    staged, directory = rig.stage({"a.txt": "Texte."})
    handle = await rig.service.start(staged, directory)
    await rig.finished(handle.run_id)
    # le dossier de données (tmp_path/data) n'est pas celui du fichier : refusé
    error = json.loads(rig.docs()["a.txt"]["error"])
    assert "hors des dossiers autorisés" in error["detail"]["reason"] and rig.embedder.calls == 0


async def test_an_embedding_failure_removes_the_partial_chunks_and_vectors(rig):
    rig.embedder.script = [None, ProviderError("ollama_down", "refus de connexion")]
    run_id, events, _ = await rig.run({"long.txt": LONG_TEXT, "court.txt": "Bref."})
    docs = rig.docs()
    assert docs["long.txt"]["status"] == "failed" and docs["court.txt"]["status"] == "ready"
    error = json.loads(docs["long.txt"]["error"])
    assert error["detail"]["reason"] == "Ollama ne répond pas sur ce poste"
    assert error["detail"]["technical"] == "refus de connexion"
    assert rig.chunks("long.txt") == 0  # les extraits partiels ne sont plus là
    assert rig.chunks() == rig.vectors() == 1  # ni leurs vecteurs : il ne reste que court.txt
    statuses = [leaf["status"] for leaf in rig.leaves(run_id)]
    assert statuses == ["ok", "error", "ok"]
    failed = rig.leaves(run_id)[1]
    assert json.loads(failed["error"])["code"] == "ollama_down"
    assert failed["co2_method"] == "unmeasurable"  # un appel raté n'est pas une mesure (AD-10)
    assert events[-1]["data"]["status"] == "ok"


async def test_partial_chunks_are_never_queryable_while_a_document_is_indexing(rig):
    rig.embedder.script = [None, Sleep(0.3)]
    handle, _ = await rig.ingest({"long.txt": LONG_TEXT})
    async with asyncio.timeout(3):
        while rig.embedder.calls < 2:
            await asyncio.sleep(0.01)
    doc = rig.docs()["long.txt"]
    assert doc["status"] == "indexing" and doc["embedding_dim"] is None
    # seuls les `ready` sont interrogés (AD-16) : aucun extrait de ce document n'est de ce nombre
    ready = rig.store.read(
        "SELECT count(*) AS n FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE d.status = 'ready'"
    )[0]["n"]
    assert ready == 0
    await rig.finished(handle.run_id)
    assert rig.docs()["long.txt"]["status"] == "ready"


async def test_a_model_that_changes_dimension_is_refused_for_that_file(rig):
    await rig.run({"a.txt": "Premier document."})
    rig.embedder.dim = 4  # le même tag, republié avec une autre taille de vecteur
    _, events, _ = await rig.run({"b.txt": "Second document."})
    error = json.loads(rig.docs()["b.txt"]["error"])
    assert (
        "dimension 4" in error["detail"]["reason"] and "videz la base" in error["detail"]["reason"]
    )
    assert rig.docs()["a.txt"]["status"] == "ready" and rig.chunks() == rig.vectors() == 1


# --- doublons ------------------------------------------------------------------------------------


async def test_a_document_already_present_is_not_indexed_twice(rig):
    _, events, _ = await rig.run({"a.txt": LONG_TEXT, "a-copie.txt": LONG_TEXT})
    done = of_type(events, "ingest_file_done")
    assert [d["status"] for d in done] == ["ready", "duplicate"]
    assert (
        done[1]["document_id"] == done[0]["document_id"] and done[1]["chunks"] == done[0]["chunks"]
    )
    calls = rig.embedder.calls
    _, again, _ = await rig.run({"renomme.txt": LONG_TEXT})  # même contenu, autre nom
    assert [d["status"] for d in of_type(again, "ingest_file_done")] == ["duplicate"]
    assert rig.embedder.calls == calls and len(rig.docs()) == 1
    assert rig.chunks() == rig.vectors() == done[0]["chunks"]


async def test_a_failed_document_can_be_imported_again_and_replaces_its_failed_row(rig):
    rig.embedder.script = [ProviderError("ollama_down", "refus")]
    await rig.run({"a.txt": "Un texte."})
    assert rig.docs()["a.txt"]["status"] == "failed"
    await rig.run({"a.txt": "Un texte."})  # Ollama est revenu
    docs = rig.store.read("SELECT status FROM documents")
    assert [d["status"] for d in docs] == ["ready"]  # une seule ligne : l'échec est remplacé


# --- annulation et concurrence --------------------------------------------------------------------


async def test_cancelling_keeps_ready_documents_and_removes_the_one_in_progress(rig):
    await rig.run({"a.txt": "Bref."})  # prêt avant l'annulation
    rig.embedder.script = [None, Sleep(10)]  # b.txt : premier lot fait, second bloqué
    rig.embedder.calls = 0
    handle, directory = await rig.ingest({"b.txt": LONG_TEXT, "c.txt": "Jamais atteint."})
    async with asyncio.timeout(3):
        while rig.embedder.calls < 2:
            await asyncio.sleep(0.01)
    assert rig.docs()["b.txt"]["status"] == "indexing" and rig.chunks("b.txt") > 0
    ready_before = (rig.docs()["a.txt"]["chunk_count"], rig.chunks("a.txt"))

    assert await rig.hub.cancel(handle.run_id)
    await rig.finished(handle.run_id)

    docs = rig.docs()
    assert set(docs) == {"a.txt"}  # b.txt retiré, c.txt jamais commencé
    assert docs["a.txt"]["status"] == "ready"
    assert (docs["a.txt"]["chunk_count"], rig.chunks("a.txt")) == ready_before
    assert rig.chunks() == rig.vectors() == 1  # aucun extrait ni vecteur de b.txt
    root = rig.store.read("SELECT status FROM runs WHERE id = ?", (handle.run_id,))[0]
    assert root["status"] == "cancelled"
    assert {leaf["status"] for leaf in rig.leaves(handle.run_id)} <= {"ok", "cancelled"}
    assert not directory.exists()
    assert rig.probe.running == 0 and not rig.slot.busy  # tracker arrêté, place rendue


async def test_cancelling_a_batch_keeps_the_energy_measured_until_the_stop(rig):
    rig.embedder.script = [Sleep(10)]
    handle, _ = await rig.ingest({"a.txt": "Un texte."})
    async with asyncio.timeout(3):
        while rig.embedder.calls < 1:  # l'appel est en cours : le tracker tourne déjà
            await asyncio.sleep(0.01)
    await rig.hub.cancel(handle.run_id)
    await rig.finished(handle.run_id)
    async with asyncio.timeout(3):  # la mesure d'une feuille annulée arrive juste après la clôture
        while True:
            leaf = rig.leaves(handle.run_id)[0]
            if leaf["co2_method"] == "codecarbon":
                break
            await asyncio.sleep(0.02)
    assert leaf["status"] == "cancelled" and leaf["co2_mg"] == pytest.approx(1.8)
    assert rig.docs() == {} and rig.probe.running == 0


async def test_the_slot_is_taken_per_batch_so_a_local_chat_interleaves(rig):
    rig.embedder.script = [Sleep(0.05)] * 8
    handle, _ = await rig.ingest({"a.txt": LONG_TEXT * 3})
    async with asyncio.timeout(3):
        while rig.embedder.calls < 1:
            await asyncio.sleep(0.01)
    async with asyncio.timeout(2):
        async with rig.slot:  # un « chat » local réclame la place pendant l'ingestion
            seen = rig.embedder.calls
    await rig.finished(handle.run_id)
    final_calls = rig.embedder.calls
    assert final_calls >= 5 and seen < final_calls  # il est passé avant la fin de l'import
    assert rig.slot.acquired == final_calls + 1  # une prise par lot, plus celle du « chat »


async def test_a_second_import_while_one_runs_is_busy(rig):
    rig.embedder.script = [Sleep(0.3)]
    handle, _ = await rig.ingest({"a.txt": "Premier."})
    staged, directory = rig.stage({"b.txt": "Second."})
    with pytest.raises(AppError) as busy:
        await rig.service.start(staged, directory)
    assert busy.value.code == "run_busy" and busy.value.detail == {"run_id": handle.run_id}
    await rig.finished(handle.run_id)


# --- modèle d'embedding ------------------------------------------------------------------------


async def test_the_model_defaults_to_the_one_of_the_base_and_cannot_change_while_it_is_not_empty(
    rig,
):
    await rig.run({"a.txt": "Un document."})  # modèle de repli : le fake
    handle, _ = await rig.ingest({"b.txt": "Un autre."})  # sans modèle : celui de la base
    await rig.finished(handle.run_id)
    assert {d["embedding_model"] for d in rig.docs().values()} == {FAKE_EMBED_REF.tag}

    staged, directory = rig.stage({"c.txt": "Troisième."})
    with pytest.raises(AppError) as locked:
        await rig.service.start(staged, directory, OTHER_REF.tag)
    assert locked.value.code == "embedding_locked"
    assert locked.value.detail == {"current": FAKE_EMBED_REF.tag, "requested": OTHER_REF.tag}
    assert (
        rig.store.read("SELECT count(*) FROM runs WHERE kind = 'ingest'")[0][0] == 2
    )  # pas de run


async def test_an_empty_base_accepts_any_installed_embedding_model(rig):
    handle, _ = await rig.ingest({"a.txt": "Un document."}, OTHER_REF.tag)
    await rig.finished(handle.run_id)
    assert rig.docs()["a.txt"]["embedding_model"] == OTHER_REF.tag


@pytest.mark.parametrize(
    ("tag", "code"),
    [
        ("inconnu:1b", "model_not_found"),
        (FAKE_REF.tag, "model_not_embedding"),  # un modèle de chat n'embarque pas
        ("openai/text-embedding", "model_not_found"),
    ],
)
async def test_the_registry_refuses_what_is_not_a_local_embedder(rig, tag, code):
    staged, directory = rig.stage({"a.txt": "Texte."})
    with pytest.raises(AppError) as error:
        await rig.service.start(staged, directory, tag)
    assert error.value.code == code and rig.docs() == {}


async def test_without_any_embedding_model_the_import_says_so(rig):
    bare = IngestService(
        rig.hub, rig.service._registry, rig.service._factory, rig.slot, rig.settings, rig.index
    )
    staged, directory = rig.stage({"a.txt": "Texte."})
    with pytest.raises(AppError) as error:
        await bare.start(staged, directory)
    assert error.value.code == "no_embedding_model"


async def test_an_empty_import_is_refused(rig):
    with pytest.raises(AppError) as error:
        await rig.service.start([], rig.tmp_path)
    assert error.value.code == "invalid_request"


# --- reprise après arrêt ---------------------------------------------------------------------------


async def test_a_document_left_indexing_by_a_crash_is_failed_without_its_chunks_at_startup(rig):
    run_id, _, _ = await rig.run({"a.txt": "Document terminé."})
    now = "2026-10-18T12:00:00.000Z"

    def crash(conn):
        repo.insert_document(
            conn, doc_id="d2", source="crash.txt", fingerprint="f2", size_bytes=3,
            embedding_model=FAKE_EMBED_REF.tag, run_id=run_id, now=now,
        )  # fmt: skip
        ids = repo.insert_chunks(conn, "d2", [ChunkDraft(0, None, "texte")])
        rig.index.add(conn, ids, [[1.0] * 16])

    await rig.store.awrite(crash)
    assert rig.chunks("crash.txt") == 1
    assert await rig.service.recover() == 1
    doc = rig.docs()["crash.txt"]
    error = json.loads(doc["error"])
    assert doc["status"] == "failed" and "arrêt du serveur" in error["detail"]["reason"]
    assert rig.chunks("crash.txt") == 0 and rig.docs()["a.txt"]["status"] == "ready"
    assert rig.chunks() == rig.vectors() == 1
    assert await rig.service.recover() == 0


# --- revue : annulation pendant une écriture hors du `try`, reprise au démarrage ------------------


async def test_cancelling_while_the_document_row_is_written_leaves_no_indexing_row(
    rig, monkeypatch
):
    import threading

    gate, entered = threading.Event(), threading.Event()
    insert = repo.insert_document

    def slow_insert(conn, **kwargs):
        entered.set()
        gate.wait(5)  # le job tourne sur le fil de l'écrivain pendant l'annulation
        insert(conn, **kwargs)

    monkeypatch.setattr(repo, "insert_document", slow_insert)
    handle, _ = await rig.ingest({"a.txt": "Bref."})
    assert await asyncio.to_thread(entered.wait, 3)
    cancelling = asyncio.create_task(rig.hub.cancel(handle.run_id))
    await asyncio.sleep(0.05)
    gate.set()
    assert await cancelling
    await rig.finished(handle.run_id)
    await rig.store.awrite(lambda conn: None)  # file de l'écrivain vidée

    assert rig.docs() == {} and rig.chunks() == rig.vectors() == 0
    _, events, _ = await rig.run({"a.txt": "Bref."})  # pas vu comme un doublon
    assert of_type(events, "ingest_file_done")[0]["status"] == "ready"


async def test_cancelling_while_a_failure_is_queued_still_marks_the_document_failed(
    rig, monkeypatch
):
    import threading

    from wavelocalai.rag import ingest as ingest_module

    gate, entered = threading.Event(), threading.Event()
    failure = ingest_module._failure

    def failure_behind_a_busy_writer(exc):
        rig.store.write(lambda conn: (entered.set(), gate.wait(5)))  # écrivain occupé
        return failure(exc)

    monkeypatch.setattr(ingest_module, "_failure", failure_behind_a_busy_writer)
    rig.embedder.script = [None, RuntimeError("panne")]  # premier lot fait, second en erreur
    handle, _ = await rig.ingest({"b.txt": LONG_TEXT})
    assert await asyncio.to_thread(entered.wait, 3)
    cancelling = asyncio.create_task(rig.hub.cancel(handle.run_id))
    await asyncio.sleep(0.05)
    gate.set()
    await cancelling
    await rig.finished(handle.run_id)
    await rig.store.awrite(lambda conn: None)

    assert {d["status"] for d in rig.docs().values()} <= {"failed"}  # jamais `indexing`
    assert rig.chunks() == rig.vectors() == 0


async def test_recovery_does_not_stop_the_startup_when_the_index_is_unusable(rig):
    run_id, _, _ = await rig.run({"a.txt": "Document terminé."})

    def crash(conn):
        repo.insert_document(
            conn, doc_id="d2", source="crash.txt", fingerprint="f2", size_bytes=3,
            embedding_model=FAKE_EMBED_REF.tag, run_id=run_id, now="2026-10-18T12:00:00.000Z",
        )  # fmt: skip
        repo.insert_chunks(conn, "d2", [ChunkDraft(0, None, "texte")])

    await rig.store.awrite(crash)

    class Broken(NumpyIndex):
        def remove(self, conn, ids):
            raise sqlite3.OperationalError("no such module: vec0")

    rig.service._index = Broken()
    assert await rig.service.recover() == 0  # journalisé, sans lever
    assert rig.docs()["crash.txt"]["status"] == "indexing"
