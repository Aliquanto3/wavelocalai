"""JSONL en ajout seul, reprise après arrêt brutal (AD-2, AD-12)."""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.quality_bench.common import jsonl, paths
from scripts.quality_bench.common.canonical import canonical_bytes
from scripts.quality_bench.common.jsonl import (
    DuplicateKeyError,
    JsonlReadError,
    open_for_append,
    read_jsonl,
)
from scripts.quality_bench.common.locks import FileLock
from tests.quality_bench.processes import APPEND_LOOP, kill_hard, start_append_loop


@pytest.fixture
def jsonl_path():
    return paths.generation_path("c1")


@pytest.fixture
def lock():
    with FileLock(paths.generation_lock_path("c1")) as held:
        yield held


def _write_raw(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as handle:
        handle.write(data)


def test_append_writes_one_canonical_line_per_record(jsonl_path, lock):
    with open_for_append(jsonl_path, lock) as writer:
        writer.append({"key": "a", "text": "été", "n": 1})
        writer.append({"n": 2, "key": "b"})
        assert "a" in writer and len(writer) == 2
    raw = jsonl_path.read_bytes()
    assert (
        raw
        == canonical_bytes({"key": "a", "text": "été", "n": 1})
        + b"\n"
        + canonical_bytes({"key": "b", "n": 2})
        + b"\n"
    )
    assert [r["key"] for r in read_jsonl(jsonl_path)] == ["a", "b"]


def test_duplicate_key_raises_and_writes_nothing(jsonl_path, lock):
    with open_for_append(jsonl_path, lock) as writer:
        writer.append({"key": "a", "v": 1})
    before = jsonl_path.read_bytes()
    with open_for_append(jsonl_path, lock) as writer:
        assert writer.keys == frozenset({"a"})
        with pytest.raises(DuplicateKeyError, match="'a'"):
            writer.append({"key": "a", "v": 2})
    assert jsonl_path.read_bytes() == before


def test_record_without_key_refused(jsonl_path, lock):
    with open_for_append(jsonl_path, lock) as writer, pytest.raises(ValueError):
        writer.append({"v": 1})


def test_open_for_append_requires_held_lock(jsonl_path):
    lock = FileLock(paths.generation_lock_path("c1"))
    with pytest.raises(RuntimeError, match="verrou"):
        open_for_append(jsonl_path, lock)
    assert not jsonl_path.exists()


def test_open_for_append_refuses_lock_of_another_directory(jsonl_path):
    for lock_path in (paths.machine_lock_path(), paths.generation_lock_path("c2")):
        with FileLock(lock_path) as foreign, pytest.raises(RuntimeError, match="verrou"):
            open_for_append(jsonl_path, foreign)
    assert not jsonl_path.exists()


def test_append_refused_once_lock_released(jsonl_path):
    lock = FileLock(paths.generation_lock_path("c1")).acquire()
    writer = open_for_append(jsonl_path, lock)
    try:
        writer.append({"key": "a"})
        lock.release()
        with pytest.raises(RuntimeError, match="libéré"):
            writer.append({"key": "b"})
    finally:
        writer.close()
    assert [r["key"] for r in read_jsonl(jsonl_path)] == ["a"]


def test_failed_write_breaks_appender(jsonl_path, lock, monkeypatch):
    real_fsync = jsonl.os.fsync
    calls = {"n": 0}

    def fsync_failing_once(fd):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disque plein")
        real_fsync(fd)

    monkeypatch.setattr(jsonl.os, "fsync", fsync_failing_once)
    writer = open_for_append(jsonl_path, lock)
    writer.append({"key": "a"})
    with pytest.raises(OSError, match="disque plein"):
        writer.append({"key": "b"})
    with pytest.raises(RuntimeError, match="échoué"):
        writer.append({"key": "c"})
    writer.close()
    monkeypatch.setattr(jsonl.os, "fsync", real_fsync)
    with open_for_append(jsonl_path, lock) as reopened:
        assert "c" not in reopened


@pytest.mark.parametrize(
    "lines, fragment",
    [
        # Plusieurs blocs, fragment plus long qu'un bloc.
        ([{"key": f"k{i}", "pad": "x" * 9} for i in range(6)], b'{"key":"z","pad":"' + b"y" * 40),
        # Dernier \n exactement à la frontière d'un bloc (voir la taille de bloc ci-dessous).
        ([{"key": "a", "pad": "x" * 6}], b'{"key":"b",' + b"y" * 21),
    ],
)
def test_fragment_truncation_across_small_blocks(jsonl_path, lock, monkeypatch, lines, fragment):
    monkeypatch.setattr(jsonl, "_CHUNK", 8)
    body = b"".join(canonical_bytes(line) + b"\n" for line in lines)
    _write_raw(jsonl_path, body + fragment)
    size = len(body) + len(fragment)
    if len(lines) == 1:
        assert (size - len(body)) % 8 == 0  # le \n final tombe sur une frontière de bloc
    assert len(fragment) > 8
    with open_for_append(jsonl_path, lock) as writer:
        assert writer.keys == frozenset(line["key"] for line in lines)
    assert jsonl_path.read_bytes() == body


def test_read_jsonl_ignores_final_fragment_and_leaves_file_intact(jsonl_path):
    data = b'{"key":"a"}\n{"key":"b"}\n{"key":"c","tro'
    _write_raw(jsonl_path, data)
    assert [r["key"] for r in read_jsonl(jsonl_path)] == ["a", "b"]
    assert jsonl_path.read_bytes() == data


def test_read_jsonl_missing_file_is_empty(jsonl_path):
    assert read_jsonl(jsonl_path) == []


@pytest.mark.parametrize(
    "data, line_no",
    [
        (b'{"key":"a"}\n{"key":\n{"key":"c"}\n', 2),
        (b'{"key":"a"}\n\n', 2),
        (b"[1,2]\n", 1),
        (b'{"key":"a"}\n{"key":"\xff"}\n', 2),
    ],
)
def test_read_jsonl_stops_on_illegible_line_with_its_number(jsonl_path, data, line_no):
    _write_raw(jsonl_path, data)
    with pytest.raises(JsonlReadError, match=f"ligne {line_no}") as excinfo:
        read_jsonl(jsonl_path)
    assert excinfo.value.line_no == line_no
    assert jsonl_path.read_bytes() == data


def test_open_for_append_truncates_final_fragment_and_logs(jsonl_path, lock, caplog):
    _write_raw(jsonl_path, b'{"key":"a"}\n' + '{"key":"b","partial":"ét'.encode())
    with caplog.at_level(logging.WARNING), open_for_append(jsonl_path, lock) as writer:
        assert writer.keys == frozenset({"a"})
        writer.append({"key": "b"})
    assert jsonl_path.read_bytes() == b'{"key":"a"}\n{"key":"b"}\n'
    assert "fragment final" in caplog.text


def test_open_for_append_truncates_fragment_only_file(jsonl_path, lock):
    _write_raw(jsonl_path, b'{"key":"a"')
    with open_for_append(jsonl_path, lock) as writer:
        assert len(writer) == 0
    assert jsonl_path.read_bytes() == b""


def test_open_for_append_refuses_corrupted_middle_line(jsonl_path, lock):
    _write_raw(jsonl_path, b'{"key":"a"}\nnot json\n{"key":"c"}\n')
    with pytest.raises(JsonlReadError, match="ligne 2"):
        open_for_append(jsonl_path, lock)


def test_open_for_append_refuses_duplicate_keys_in_file(jsonl_path, lock):
    _write_raw(jsonl_path, b'{"key":"a"}\n{"key":"a"}\n')
    with pytest.raises(JsonlReadError, match="double"):
        open_for_append(jsonl_path, lock)


def _wait_for_lines(path: Path, count: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_bytes().count(b"\n") >= count:
            return
        time.sleep(0.02)
    raise AssertionError(f"{path} : moins de {count} lignes après {timeout} s")


def test_killed_writer_resumes_without_duplicate_or_gap(jsonl_path):
    """Sous-processus tué en cours de route, fragment final simulé, puis relancé : exactement
    N+1 lignes valides, clés toutes distinctes."""
    last = 59
    lock_path = paths.generation_lock_path("c1")
    command = [sys.executable, str(APPEND_LOOP), str(jsonl_path), str(lock_path), str(last)]

    # Pause par ligne assez longue pour que l'arrêt tombe en cours de route, même lent.
    writer, writer_pid = start_append_loop(jsonl_path, lock_path, last, 0.05)
    try:
        _wait_for_lines(jsonl_path, 10)
    finally:
        kill_hard(writer, writer_pid, lock_path)
    written = jsonl_path.read_bytes().count(b"\n")
    assert 10 <= written < last + 1, "le processus devait être tué en cours de route"
    # Écriture interrompue en pleine ligne : fragment sans fin de ligne.
    _write_raw(jsonl_path, b'{"index":' + str(written).encode() + b',"key":"k' + b"\xc3")

    result = subprocess.run([*command, "0"], capture_output=True, timeout=120)  # noqa: S603
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")[-2000:]

    raw = jsonl_path.read_bytes()
    assert raw.endswith(b"\n")
    records = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    keys = [record["key"] for record in records]
    assert len(records) == last + 1
    assert len(set(keys)) == last + 1
    assert sorted(record["index"] for record in records) == list(range(last + 1))


def test_rewrite_jsonl_replaces_whole_file(tmp_path):
    from scripts.quality_bench.common.jsonl import rewrite_jsonl

    path = tmp_path / "candidates.jsonl"
    assert rewrite_jsonl(path, [{"key": "a"}, {"key": "b"}]) == 2
    assert rewrite_jsonl(path, [{"key": "c", "v": "é"}]) == 1
    assert path.read_bytes() == '{"key":"c","v":"é"}\n'.encode()
    assert not path.with_name("candidates.jsonl.tmp").exists()


def test_read_complete_jsonl_accepts_last_line_without_newline(tmp_path):
    from scripts.quality_bench.common.jsonl import JsonlReadError, read_complete_jsonl

    path = tmp_path / "source.jsonl"
    path.write_bytes(b'{"a":1}\r\n\n{"a":2}')
    assert read_complete_jsonl(path) == [{"a": 1}, {"a": 2}]
    path.write_bytes(b'{"a":1}\n{illisible}\n')
    with pytest.raises(JsonlReadError, match="ligne 2"):
        read_complete_jsonl(path)
