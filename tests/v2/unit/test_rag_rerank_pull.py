"""Récupération du reranker (story 5.5) : le processus de téléchargement, ses sorties et ses mesures.
Aucun réseau, aucun modèle : `fastembed` est un faux module, le processus un faux."""

from __future__ import annotations

import asyncio
import sys
import types

import pytest

from wavelocalai.rag import rerank_fetch, rerank_pull

MODEL = "jinaai/jina-reranker-v2-base-multilingual"


def fake_fastembed(monkeypatch, encoder):
    """Un `fastembed.rerank.cross_encoder.TextCrossEncoder` factice."""
    module = types.ModuleType("fastembed.rerank.cross_encoder")
    module.TextCrossEncoder = encoder
    for name in ("fastembed", "fastembed.rerank"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "fastembed.rerank.cross_encoder", module)


def test_fetch_downloads_into_the_given_cache_without_local_files_only(monkeypatch, tmp_path):
    calls = []

    class Encoder:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_fastembed(monkeypatch, Encoder)
    order = []
    monkeypatch.setattr(
        rerank_fetch, "disable_telemetry", lambda env=None: order.append("telemetry")
    )
    assert rerank_fetch.main(["x", MODEL, str(tmp_path)]) == 0
    assert calls == [{"model_name": MODEL, "cache_dir": str(tmp_path)}]  # jamais local_files_only
    assert order == ["telemetry"]


def test_fetch_exit_codes_say_fastembed_missing_or_the_first_error_line(
    monkeypatch, tmp_path, capsys
):
    """fastembed est une dépendance de base (story 9.5) : le code reste défensif sur `ImportError`."""
    monkeypatch.setattr(rerank_fetch, "disable_telemetry", lambda env=None: None)
    monkeypatch.setitem(sys.modules, "fastembed", None)  # `import` lève ImportError
    monkeypatch.setitem(
        sys.modules, "fastembed.rerank.cross_encoder", None
    )  # déjà importé ailleurs
    assert rerank_fetch.main(["x", MODEL, str(tmp_path)]) == 2

    class Broken:
        def __init__(self, **kwargs):
            raise OSError("Plus d'espace disque\ndétail")

    fake_fastembed(monkeypatch, Broken)
    assert rerank_fetch.main(["x", MODEL, str(tmp_path)]) == 1
    assert "Plus d'espace disque" in capsys.readouterr().err
    assert rerank_fetch.main(["x"]) == 1  # arguments manquants


def test_the_expected_size_is_the_one_fastembed_announces(monkeypatch):
    monkeypatch.setattr(rerank_pull, "disable_telemetry", lambda env=None: None)

    class Encoder:
        @staticmethod
        def list_supported_models():
            return [{"model": "autre", "size_in_GB": 9}, {"model": MODEL, "size_in_GB": 1.5}]

    fake_fastembed(monkeypatch, Encoder)
    assert rerank_pull.expected_bytes(MODEL) == int(1.5 * rerank_pull.GIB)
    assert rerank_pull.expected_bytes("inconnu") == 0


def test_folder_size_adds_the_files_and_ignores_a_missing_folder(tmp_path):
    folder = rerank_pull.model_folder(tmp_path, MODEL)
    assert folder.name == "models--jinaai--jina-reranker-v2-base-multilingual"
    assert rerank_pull.folder_size(folder) == 0
    (folder / "blobs").mkdir(parents=True)
    (folder / "blobs" / "a").write_bytes(b"x" * 10)
    (folder / "b").write_bytes(b"y" * 5)
    assert rerank_pull.folder_size(folder) == 15


class FakeProcess:
    def __init__(self, code, stderr=b"", hang=False):
        self.returncode = code
        self._stderr = stderr
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.Event().wait()
        return b"", self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


async def test_the_subprocess_runs_the_fetch_module_and_reports_failures(monkeypatch, tmp_path):
    seen = []

    async def spawn(*args, **kwargs):
        seen.append(args)
        return FakeProcess(1, b"ligne 1\nTimeout de connexion")

    monkeypatch.setattr(rerank_pull.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(rerank_pull.RerankerFetchError, match="Timeout de connexion"):
        await rerank_pull.fetch_in_subprocess(MODEL, tmp_path, tmp_path / ".env")
    assert seen[0][1:3] == ("-m", "wavelocalai.rag.rerank_fetch")
    assert seen[0][3:5] == (MODEL, str(tmp_path))

    async def missing(*args, **kwargs):
        return FakeProcess(2)

    monkeypatch.setattr(rerank_pull.asyncio, "create_subprocess_exec", missing)
    with pytest.raises(rerank_pull.RerankerFetchError, match="fastembed"):
        await rerank_pull.fetch_in_subprocess(MODEL, tmp_path)


async def test_cancelling_kills_the_download_process(monkeypatch, tmp_path):
    process = FakeProcess(None, hang=True)

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(rerank_pull.asyncio, "create_subprocess_exec", spawn)
    task = asyncio.ensure_future(rerank_pull.fetch_in_subprocess(MODEL, tmp_path))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.killed is True
