"""Dossier de données : verrou d'instance unique, alerte OneDrive, journaux en rotation (AD-23)."""

from __future__ import annotations

import errno
import logging

import pytest

from wavelocalai.store.datadir import (
    LOCK_NAME,
    DataDirLock,
    DataDirLockedError,
    DataDirLockError,
    ensure_data_dir,
    is_under_onedrive,
)
from wavelocalai.store.logs import BACKUP_COUNT, MAX_BYTES, close_logging, setup_logging


def test_second_lock_on_same_data_dir_is_refused_until_release(tmp_path):
    first = DataDirLock(tmp_path)
    second = DataDirLock(tmp_path)
    first.acquire()
    try:
        with pytest.raises(DataDirLockedError, match="autre wavelocalai-v2"):
            second.acquire()
    finally:
        first.release()
    with second:  # libéré : le suivant passe
        pass


def test_lock_failure_other_than_a_live_server_says_the_real_cause(tmp_path, monkeypatch):
    """C5 : droits ou disque ne sont pas « un autre serveur » (mauvais diagnostic sinon)."""
    from wavelocalai.store import datadir

    def refuse(handle):
        raise OSError(errno.EIO, "Erreur d'entrée/sortie")

    monkeypatch.setattr(datadir, "_lock", refuse)
    with pytest.raises(DataDirLockError, match="Impossible de prendre le verrou") as raised:
        DataDirLock(tmp_path).acquire()
    assert not isinstance(raised.value, DataDirLockedError)
    assert "autre wavelocalai-v2" not in str(raised.value)


def test_lock_file_that_cannot_be_created_says_the_real_cause(tmp_path):
    (tmp_path / LOCK_NAME).mkdir()  # un dossier à la place du fichier de verrou
    with pytest.raises(DataDirLockError, match="Impossible de créer le verrou") as raised:
        DataDirLock(tmp_path).acquire()
    assert not isinstance(raised.value, DataDirLockedError)


def test_other_data_dirs_do_not_conflict(tmp_path):
    with DataDirLock(tmp_path / "a"), DataDirLock(tmp_path / "b"):
        pass


def test_release_is_idempotent(tmp_path):
    lock = DataDirLock(tmp_path)
    lock.acquire()
    lock.release()
    lock.release()


def test_ensure_data_dir_creates_logs_folder(tmp_path):
    root = ensure_data_dir(tmp_path / "x" / "data")
    assert (root / "logs").is_dir()


def test_onedrive_is_detected_from_the_path(tmp_path):
    assert is_under_onedrive(tmp_path / "OneDrive - Entreprise" / "data")
    assert is_under_onedrive(tmp_path / "onedrive" / "data")
    assert not is_under_onedrive(tmp_path / "data")


@pytest.fixture
def logs(tmp_path):
    yield tmp_path
    close_logging()


def test_logs_rotate_five_files_of_one_megabyte(logs):
    log_file = setup_logging(logs, console=False)
    handler = next(h for h in logging.getLogger("wavelocalai").handlers if hasattr(h, "maxBytes"))
    assert (handler.maxBytes, handler.backupCount) == (1_000_000, 4)
    assert (MAX_BYTES, BACKUP_COUNT) == (1_000_000, 4)
    assert log_file.parent == logs / "logs"

    logger = logging.getLogger("wavelocalai.test")
    for _ in range(80):  # ~8 Mo : bien plus que 5 fichiers de 1 Mo
        logger.info("x" * 100_000)
    files = sorted(p.name for p in (logs / "logs").iterdir())
    assert files == [
        "wavelocalai.log",
        "wavelocalai.log.1",
        "wavelocalai.log.2",
        "wavelocalai.log.3",
        "wavelocalai.log.4",
    ]
    assert all(p.stat().st_size <= 1_100_000 for p in (logs / "logs").iterdir())


def test_logs_mask_api_keys_even_in_exceptions(logs):
    log_file = setup_logging(logs, console=False, secrets=("valeur-secrete-connue",))
    logger = logging.getLogger("wavelocalai.test")
    try:
        raise RuntimeError("échec avec sk-proj-AbCdEf0123456789")
    except RuntimeError:
        logger.exception("appel refusé (valeur-secrete-connue)")
    for handler in logging.getLogger("wavelocalai").handlers:
        handler.flush()
    text = log_file.read_text(encoding="utf-8")
    assert "sk-proj-AbCdEf" not in text and "valeur-secrete-connue" not in text
    assert "***" in text


def test_setup_logging_is_idempotent(logs):
    setup_logging(logs, console=False)
    setup_logging(logs, console=False)
    ours = [h for h in logging.getLogger("wavelocalai").handlers if hasattr(h, "baseFilename")]
    assert len(ours) == 1
