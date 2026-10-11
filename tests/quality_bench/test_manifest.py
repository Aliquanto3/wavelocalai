"""Manifeste ``qb.manifest/1`` : écriture au premier lancement, reprise refusée sur
``blocking`` différent (AD-8)."""

import json
import logging
import sys

import pytest

from scripts.quality_bench.common import manifest as manifest_module
from scripts.quality_bench.common import paths
from scripts.quality_bench.common.manifest import (
    ManifestMismatchError,
    blocking_hash,
    build_manifest,
    collect_informative,
    ensure_manifest,
    first_difference,
    harness_hash,
    machine_label,
)
from scripts.quality_bench.common.schemas import SchemaValidationError, UnknownSchemaError
from tests.quality_bench.factories import HASH_A, HASH_B, manifest


@pytest.fixture
def manifest_path():
    return paths.generation_manifest_path("pilot-20261015")


def test_first_launch_writes_then_identical_resume_accepted(manifest_path):
    first = manifest()
    assert ensure_manifest(manifest_path, first) == first
    on_disk = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert on_disk == first
    again = manifest(created_at="2026-10-16T09:00:00Z")
    assert ensure_manifest(manifest_path, again)["created_at"] == first["created_at"]


def test_blocking_difference_refused_with_first_field_path(manifest_path):
    ensure_manifest(manifest_path, manifest())
    changed = manifest()
    changed["blocking"]["models_resolved"][3]["digest"] = "sha256:" + "f" * 64
    changed["blocking"]["ollama_version"] = "0.40.3"  # plus loin dans l'ordre des clés
    with pytest.raises(ManifestMismatchError) as excinfo:
        ensure_manifest(manifest_path, changed)
    assert excinfo.value.path == "blocking.models_resolved[3].digest"
    assert "blocking.models_resolved[3].digest" in str(excinfo.value)
    assert "f" * 64 in str(excinfo.value)


def test_ollama_version_difference_named(manifest_path):
    ensure_manifest(manifest_path, manifest())
    changed = manifest()
    changed["blocking"]["ollama_version"] = "0.40.3"
    with pytest.raises(ManifestMismatchError, match=r"blocking\.ollama_version"):
        ensure_manifest(manifest_path, changed)


def test_informative_difference_accepted(manifest_path):
    ensure_manifest(manifest_path, manifest())
    changed = manifest()
    changed["informative"]["python"] = "3.14.0"
    changed["informative"]["packages"] = {"httpx2": "2.13.1"}
    assert ensure_manifest(manifest_path, changed)["informative"]["python"] == "3.12.8"


def test_phase_difference_refused(manifest_path):
    ensure_manifest(manifest_path, manifest())
    judgment = manifest(phase="judgment")
    judgment["blocking"]["judge"] = {
        "id": "haiku",
        "config_hash": HASH_A,
        "endpoint": "https://api.anthropic.com",
        "model": "claude-haiku-5-5",
        "settings": {},
        "prompt_template_hash": HASH_B,
        "weights_sha256": None,
        "server_version": None,
    }
    judgment["blocking"]["generation_manifest"] = HASH_A
    with pytest.raises(ManifestMismatchError, match="phase"):
        ensure_manifest(manifest_path, judgment)


def test_unknown_schema_on_disk_refused(manifest_path):
    stored = manifest(schema="qb.manifest/2")
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(stored), encoding="utf-8")
    with pytest.raises(UnknownSchemaError):
        ensure_manifest(manifest_path, manifest())


def test_invalid_manifest_not_written(manifest_path):
    with pytest.raises(SchemaValidationError):
        ensure_manifest(manifest_path, manifest(phase="grading"))
    assert not manifest_path.exists()


@pytest.mark.parametrize(
    "a, b, expected",
    [
        ({"x": 1}, {"x": 1}, None),
        ({"x": 1}, {"x": 2}, "blocking.x"),
        ({"x": True}, {"x": 1}, "blocking.x"),
        ({"x": 1}, {"x": 1.0}, "blocking.x"),
        ({"a": 1, "b": 1}, {"b": 2, "a": 2}, "blocking.a"),
        ({"x": 1}, {"x": 1, "y": 2}, "blocking.y"),
        ({"l": [1, 2]}, {"l": [1, 2, 3]}, "blocking.l[2]"),
        ({"l": [1, 2, 3]}, {"l": [1]}, "blocking.l[1]"),
        ({"l": [{"d": "a"}]}, {"l": [{"d": "b"}]}, "blocking.l[0].d"),
        ({"x": None}, {"x": {}}, "blocking.x"),
    ],
)
def test_first_difference(a, b, expected):
    assert first_difference(a, b) == expected


def test_harness_hash_normalizes_line_endings_and_covers_listed_dirs(tmp_path):
    package = tmp_path / "pkg"
    for name, content in [
        ("common/a.py", b"x = 1\r\ny = 2\r\n"),
        ("ollama/client.py", b"z = 3\n"),
        ("grading/ignored.py", b"w = 4\n"),
    ]:
        target = package / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    first = harness_hash(package)
    (package / "common" / "a.py").write_bytes(b"x = 1\ny = 2\n")
    assert harness_hash(package) == first  # fins de ligne normalisées
    (package / "grading" / "ignored.py").write_bytes(b"w = 5\n")
    assert harness_hash(package) == first  # grading/ hors du harnais
    (package / "ollama" / "client.py").write_bytes(b"z = 4\n")
    assert harness_hash(package) != first
    (package / "generation").mkdir()
    changed = harness_hash(package)
    (package / "generation" / "runner.py").write_bytes(b"")
    assert harness_hash(package) != changed  # generation/ existant : couvert


def test_harness_hash_covers_every_file_but_bytecode(tmp_path):
    package = tmp_path / "pkg"
    (package / "envs" / "data").mkdir(parents=True)
    (package / "envs" / "data" / "fs.json").write_bytes(b'{"a": 1}\n')
    first = harness_hash(package)
    (package / "envs" / "data" / "fs.json").write_bytes(b'{"a": 2}\n')
    second = harness_hash(package)
    assert second != first  # fichier non Python couvert
    (package / "envs" / "__pycache__").mkdir()
    (package / "envs" / "__pycache__" / "x.cpython-314.pyc").write_bytes(b"\x00")
    (package / "envs" / "stale.pyc").write_bytes(b"\x01")
    assert harness_hash(package) == second


def test_harness_hash_of_real_package_is_stable():
    assert harness_hash() == harness_hash()


def test_machine_label(monkeypatch):
    monkeypatch.setenv("QUALITY_BENCH_MACHINE", "tour-rtx3050")
    assert machine_label() == "tour-rtx3050"
    monkeypatch.setenv("QUALITY_BENCH_MACHINE", "  ")
    assert machine_label() == manifest_module.socket.gethostname()
    monkeypatch.delenv("QUALITY_BENCH_MACHINE")
    assert machine_label() == manifest_module.socket.gethostname()


def test_build_manifest_and_blocking_hash(monkeypatch):
    monkeypatch.setenv("QUALITY_BENCH_MACHINE", "tour-rtx3050")
    informative = manifest()["informative"]
    built = build_manifest(
        phase="generation",
        campaign="pilot-20261015",
        set_info={"id": "set-v1", "hash": HASH_A, "n": {"think_off": 800, "think_on": 400}},
        generation={"hash": HASH_B, "resolved": {"max_attempts": 3}},
        models_resolved=manifest()["blocking"]["models_resolved"],
        ollama_version="0.40.2",
        informative=informative,
    )
    assert built["blocking"]["machine"] == "tour-rtx3050"
    assert built["blocking"]["harness_hash"] == harness_hash()
    assert built["blocking"]["judge"] is None
    assert built["informative"] == informative
    assert len(blocking_hash(built)) == 64
    other = json.loads(json.dumps(built))
    other["created_at"] = "2030-01-01T00:00:00Z"
    other["informative"]["python"] = "3.10.0"
    assert blocking_hash(other) == blocking_hash(built)


def test_collect_informative_shape(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_PARALLEL", "1")
    monkeypatch.setattr(manifest_module, "_run", lambda command: None)
    info = collect_informative(checklist={"windows_update_paused": True})
    assert info["packages"]["jsonschema"]
    assert info["ollama_env"]["OLLAMA_NUM_PARALLEL"] == "1"
    assert info["checklist"] == {"windows_update_paused": True}
    assert info["code_commit"] is None and info["prices"] is None


def test_collect_informative_masks_secret_ollama_values(monkeypatch):
    monkeypatch.setattr(manifest_module, "_run", lambda command: None)
    secrets = {
        "OLLAMA_API_KEY": "sk-1",
        "OLLAMA_AUTH_TOKEN": "t-2",
        "OLLAMA_CLIENT_SECRET": "s-3",
        "OLLAMA_PROXY_PASSWORD": "p-4",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "5m")
    env = collect_informative()["ollama_env"]
    for name, value in secrets.items():
        assert env[name] == "<masqué>"
        assert value not in json.dumps(env)
    assert env["OLLAMA_KEEP_ALIVE"] == "5m"


def test_informative_difference_logged_on_resume(manifest_path, caplog):
    ensure_manifest(manifest_path, manifest())
    changed = manifest()
    changed["informative"]["python"] = "3.14.0"
    changed["informative"]["code_commit"] = "deadbeef"
    with caplog.at_level(logging.WARNING):
        ensure_manifest(manifest_path, changed)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "informative.code_commit, informative.python" in warnings[0].getMessage()
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        ensure_manifest(manifest_path, manifest())  # identique : rien
    assert not caplog.records


def test_run_tolerates_undecodable_output(monkeypatch):
    command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok\\n')"]
    assert manifest_module._run(command).endswith("ok")
