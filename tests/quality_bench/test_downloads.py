"""Téléchargements d'avant campagne, sans réseau : empreintes, verrou machine, sources refusées."""

import hashlib
import io
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.jsonl import read_jsonl
from scripts.quality_bench.common.locks import FileLock
from scripts.quality_bench.questions.importers import commands, nltk_data
from scripts.quality_bench.questions.importers.remote import (
    RemoteFile,
    SourceIntegrityError,
    fetch_files,
)

ROOT = Path(__file__).resolve().parents[2]
REV = "0" * 40
CONTENT = b'{"a": 1}\n'


def _remote(content=CONTENT, path="data/file.json", host="github"):
    return RemoteFile(host, "owner/repo", REV, path, hashlib.sha256(content).hexdigest())


def _writer(content=CONTENT, calls=None):
    def download(remote, target):
        if calls is not None:
            calls.append(remote.path)
        target.write_bytes(content)

    return download


def test_fetch_files_downloads_then_reuses(tmp_path):
    calls = []
    remote = _remote()
    first = fetch_files([remote], tmp_path, _writer(calls=calls))
    assert first[remote].read_bytes() == CONTENT
    assert first[remote] == tmp_path / "github" / "owner" / "repo" / REV / "data" / "file.json"
    fetch_files([remote], tmp_path, _writer(calls=calls))
    assert calls == ["data/file.json"]  # second appel : empreinte vérifiée, pas de téléchargement


def test_fetch_files_refuses_unexpected_hash(tmp_path):
    remote = _remote()
    with pytest.raises(SourceIntegrityError, match="Empreinte inattendue"):
        fetch_files([remote], tmp_path, _writer(content=b"autre"))
    assert not list(tmp_path.rglob("*.json")) and not list(tmp_path.rglob("*.part"))


def test_fetch_files_refuses_then_deletes_a_modified_local_file(tmp_path):
    calls = []
    remote = _remote()
    path = remote.local_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"corrompu")
    with pytest.raises(SourceIntegrityError, match="fichier local"):
        fetch_files([remote], tmp_path, _writer(calls=calls))
    assert not path.exists() and calls == []
    fetch_files([remote], tmp_path, _writer(calls=calls))  # relance : retéléchargé
    assert path.read_bytes() == CONTENT and calls == ["data/file.json"]


@pytest.mark.parametrize(
    "revision, path",
    [("main", "a.json"), ("x" * 40, "a.json"), (REV, "../a.json"), (REV, "/abs.json")],
)
def test_remote_file_requires_pinned_revision_and_relative_path(revision, path):
    with pytest.raises(ValueError):
        RemoteFile("hf", "owner/repo", revision, path, "0" * 64)


def test_remote_urls():
    assert _remote().url == f"https://raw.githubusercontent.com/owner/repo/{REV}/data/file.json"
    assert _remote(host="hf").url == (
        f"https://huggingface.co/datasets/owner/repo/resolve/{REV}/data/file.json"
    )


@pytest.mark.parametrize("slug", sorted(commands.REFUSED_SOURCES))
def test_refused_sources_cannot_be_fetched(slug):
    with pytest.raises(commands.UnknownSourceError, match="refusée"):
        commands.load_importer(slug)


def test_unknown_source_cannot_be_fetched():
    with pytest.raises(commands.UnknownSourceError, match="inconnue"):
        commands.load_importer("squad")


def test_every_importable_source_has_an_importer():
    for slug in commands.importable_slugs():
        importer = commands.load_importer(slug)
        assert importer.slug == slug
        assert importer.files, slug
        for remote in importer.files:
            assert len(remote.sha256) == 64


def test_cli_fetch_refuses_when_machine_is_busy(_isolated_data_root):
    with FileLock(paths.machine_lock_path()):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-m", "scripts.quality_bench", "fetch", "--source", "piaf"],
            cwd=ROOT,
            capture_output=True,
            timeout=120,
        )
    assert result.returncode == 1
    assert "Verrou occupé" in result.stderr.decode("utf-8", "replace")
    assert not paths.sources_dir().joinpath("piaf").exists()


def test_cli_fetch_refuses_a_refused_source():
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.quality_bench", "fetch", "--source", "musr"],
        cwd=ROOT,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 2
    assert "refusée" in result.stderr.decode("utf-8", "replace")


def _zip_bytes(package, text="données"):
    """Archive NLTK synthétique : ``<paquet>/data.txt``."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{package}/data.txt", text)
    return buffer.getvalue()


def _fake_nltk(content_by_package):
    calls = []

    def download(package, root):
        calls.append(package)
        path = nltk_data.archive_path(root, package)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content_by_package[package])

    return download, calls


def test_fetch_nltk_data_downloads_verifies_and_skips(tmp_path, monkeypatch):
    contents = {pkg: _zip_bytes(pkg) for pkg in ("punkt", "stopwords")}
    packages = {
        pkg: ("tokenizers", hashlib.sha256(data).hexdigest(), "Unknown")
        for pkg, data in contents.items()
    }
    monkeypatch.setattr(nltk_data, "PACKAGES", packages)
    download, calls = _fake_nltk(contents)
    result = nltk_data.fetch_nltk_data(tmp_path, download)
    assert set(result) == set(contents) and sorted(calls) == sorted(contents)
    nltk_data.fetch_nltk_data(tmp_path, download)
    assert len(calls) == 2  # déjà présents : rien de retéléchargé


def test_fetch_nltk_data_refuses_unexpected_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(nltk_data, "PACKAGES", {"punkt": ("tokenizers", "0" * 64, "Unknown")})
    download, _ = _fake_nltk({"punkt": b"autre"})
    with pytest.raises(nltk_data.NltkDataError, match="Empreinte inattendue"):
        nltk_data.fetch_nltk_data(tmp_path, download)


def test_nltk_packages_are_the_four_required():
    assert set(nltk_data.PACKAGES) == {
        "punkt",
        "punkt_tab",
        "stopwords",
        "averaged_perceptron_tagger_eng",
    }


def test_nltk_data_dir_is_under_data_root(_isolated_data_root):
    assert paths.nltk_data_dir() == _isolated_data_root / "nltk_data"


def test_rewritten_candidates_are_canonical(_isolated_data_root, monkeypatch):
    """``fetch_source`` réécrit les candidats en JSONL canonique, sans réseau."""
    from scripts.quality_bench.questions.importers.base import Importer, build_question

    remote = _remote()

    def convert(local):
        assert local[remote.path].read_bytes() == CONTENT
        return [
            build_question(
                source="bbeh-mini",
                number=1,
                group="bbeh-mini/0001",
                messages=[{"role": "user", "content": "Question ?"}],
                grader_params={},
                target="4",
            )
        ]

    monkeypatch.setattr(commands, "load_importer", lambda slug: Importer(slug, (remote,), convert))
    assert commands.fetch_source("bbeh-mini", downloader=_writer()) == 1
    lines = read_jsonl(paths.candidates_path("bbeh-mini"))
    assert [line["id"] for line in lines] == ["reasoning/bbeh-mini/0001"]


def test_fetch_nltk_data_removes_unexpected_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(nltk_data, "PACKAGES", {"punkt": ("tokenizers", "0" * 64, "Unknown")})
    download, _ = _fake_nltk({"punkt": b"autre"})
    extracted = tmp_path / "tokenizers" / "punkt"
    extracted.mkdir(parents=True)
    with pytest.raises(nltk_data.NltkDataError):
        nltk_data.fetch_nltk_data(tmp_path, download)
    assert not nltk_data.archive_path(tmp_path, "punkt").exists() and not extracted.exists()


def _bbeh_importer(content):
    """Importeur ``bbeh-mini`` sur un fichier synthétique d'empreinte ``content``."""
    from scripts.quality_bench.questions.importers import bbeh
    from scripts.quality_bench.questions.importers.base import Importer

    remote = RemoteFile(
        "github", "owner/repo", REV, bbeh.DATA.path, hashlib.sha256(content).hexdigest()
    )
    return Importer("bbeh-mini", (remote,), bbeh.convert)


BBEH_CONTENT = '{"examples": [{"input": "Québec ?", "target": "oui"}]}'.encode()


def test_second_fetch_reuses_files_and_rewrites_identical_candidates(monkeypatch):
    calls = []
    monkeypatch.setattr(commands, "load_importer", lambda slug: _bbeh_importer(BBEH_CONTENT))
    downloader = _writer(content=BBEH_CONTENT, calls=calls)
    assert commands.fetch_source("bbeh-mini", downloader=downloader) == 1
    first = paths.candidates_path("bbeh-mini").read_bytes()
    assert commands.fetch_source("bbeh-mini", downloader=downloader) == 1
    assert paths.candidates_path("bbeh-mini").read_bytes() == first
    assert calls == [_bbeh_importer(BBEH_CONTENT).files[0].path]  # un seul téléchargement


def test_unexpected_hash_writes_no_candidate(monkeypatch):
    monkeypatch.setattr(commands, "load_importer", lambda slug: _bbeh_importer(BBEH_CONTENT))
    stale = paths.candidates_path("bbeh-mini")
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b'{"ancien":1}\n')  # candidats d'un import précédent
    with pytest.raises(SourceIntegrityError):
        commands.fetch_source("bbeh-mini", downloader=_writer(content=b"{}"))
    assert not paths.candidates_path("bbeh-mini").exists()
    assert not list(paths.source_raw_dir("bbeh-mini").rglob("*.json"))


@pytest.fixture
def _reset_logging():
    """Ferme le journal de fichier ouvert par la CLI (sinon ``tmp_path`` reste verrouillé)."""
    yield
    from scripts.quality_bench.common.logs import setup_logging

    setup_logging("test", None)


@pytest.mark.parametrize(
    "argv, target, error",
    [
        (["fetch", "--source", "bbeh-mini"], "fetch_source", SourceIntegrityError("empreinte")),
        (["fetch-nltk"], None, nltk_data.NltkDataError("empreinte NLTK")),
    ],
)
def test_cli_integrity_errors_are_logged_with_code_1(
    argv, target, error, monkeypatch, _reset_logging
):
    from scripts.quality_bench.__main__ import main

    def fail(*args, **kwargs):
        raise error

    if target:
        monkeypatch.setattr(commands, target, fail)
    else:
        monkeypatch.setattr(nltk_data, "fetch_nltk_data", fail)
    assert main(argv) == 1
    log = paths.sources_log_path(argv[0]).read_text(encoding="utf-8")
    assert str(error) in log and "ERROR" in log
    assert not paths.machine_lock_path().read_bytes()  # verrou relâché


def test_cli_fetch_nltk_writes_into_data_root(monkeypatch, _reset_logging):
    from scripts.quality_bench.__main__ import main

    seen = []
    monkeypatch.setattr(nltk_data, "fetch_nltk_data", lambda root: seen.append(root) or {})
    assert main(["fetch-nltk"]) == 0
    assert seen == [paths.nltk_data_dir()]


def test_cli_loads_without_network_libraries():
    """Charger la CLI n'importe ni ``huggingface_hub``, ni ``pyarrow``, ni ``nltk`` : seuls
    ``fetch`` et ``fetch-nltk`` les chargent, à l'exécution."""
    code = (
        "import sys; import scripts.quality_bench.__main__ as m; m.build_parser(); "
        "print(sorted(n for n in ('huggingface_hub', 'pyarrow', 'nltk') if n in sys.modules))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, capture_output=True, timeout=120
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-2000:]
    assert result.stdout.decode().strip() == "[]"


def test_fetch_nltk_data_reextracts_a_tampered_folder(tmp_path, monkeypatch):
    content = _zip_bytes("punkt", "vérifié")
    digest = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(nltk_data, "PACKAGES", {"punkt": ("tokenizers", digest, "Unknown")})
    download, calls = _fake_nltk({"punkt": content})
    nltk_data.fetch_nltk_data(tmp_path, download)
    extracted = tmp_path / "tokenizers" / "punkt"
    (extracted / "data.txt").write_text("modifié", encoding="utf-8")
    (extracted / "ajout.txt").write_text("x", encoding="utf-8")
    nltk_data.fetch_nltk_data(tmp_path, download)
    assert calls == ["punkt"]  # archive intacte : pas retéléchargée
    assert (extracted / "data.txt").read_text(encoding="utf-8") == "vérifié"
    assert not (extracted / "ajout.txt").exists()


def test_fetch_nltk_data_refuses_a_download_without_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(nltk_data, "PACKAGES", {"punkt": ("tokenizers", "0" * 64, "Unknown")})
    with pytest.raises(nltk_data.NltkDataError, match="absente"):
        nltk_data.fetch_nltk_data(tmp_path, lambda package, root: None)


def test_importable_slugs_are_the_nine_sources():
    from scripts.quality_bench.questions.schema import SOURCES

    assert commands.importable_slugs() == sorted(SOURCES)
    assert len(SOURCES) == 9


def test_importers_match_declared_producers():
    import importlib

    from scripts.quality_bench.questions.schema import SOURCES

    for producer in {spec.producer for spec in SOURCES.values()}:
        module = importlib.import_module(
            "scripts.quality_bench." + producer.removesuffix(".py").replace("/", ".")
        )
        expected = {slug for slug, spec in SOURCES.items() if spec.producer == producer}
        assert set(module.IMPORTERS) == expected, producer


def test_cli_fetch_all_attempts_every_source(monkeypatch, _reset_logging):
    from scripts.quality_bench.__main__ import main

    seen = []
    monkeypatch.setattr(commands, "fetch_source", lambda slug: seen.append(slug) or 1)
    assert main(["fetch", "--all"]) == 0
    assert seen == commands.importable_slugs()


def test_cli_fetch_continues_after_a_failing_source(monkeypatch, _reset_logging):
    from scripts.quality_bench.__main__ import main

    seen = []

    def fake(slug):
        seen.append(slug)
        if slug == "bfcl-live":
            raise SourceIntegrityError("empreinte bfcl-live")
        return 1

    monkeypatch.setattr(commands, "fetch_source", fake)
    argv = ["fetch", "--source", "bbeh-mini", "--source", "bfcl-live", "--source", "piaf"]
    assert main(argv) == 1
    assert seen == ["bbeh-mini", "bfcl-live", "piaf"]
    log = paths.sources_log_path("fetch").read_text(encoding="utf-8")
    assert "bfcl-live : import échoué" in log and "Sources en échec (1/3) : bfcl-live" in log


def test_cli_fetch_nltk_refuses_when_machine_is_busy(monkeypatch, _reset_logging):
    from scripts.quality_bench.__main__ import main

    calls = []
    monkeypatch.setattr(nltk_data, "fetch_nltk_data", lambda root: calls.append(root) or {})
    with FileLock(paths.machine_lock_path()):
        assert main(["fetch-nltk"]) == 1
    assert calls == [] and not paths.nltk_data_dir().exists()


def test_cli_refused_source_is_logged_to_file(_reset_logging):
    from scripts.quality_bench.__main__ import main

    assert main(["fetch", "--source", "musr"]) == 2
    assert "refusée" in paths.sources_log_path("fetch").read_text(encoding="utf-8")
