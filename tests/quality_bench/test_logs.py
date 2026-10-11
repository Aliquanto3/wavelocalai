"""Journal : fichier ``log-<commande>.log`` et console, en UTF-8."""

import logging

import pytest

from scripts.quality_bench.common import paths
from scripts.quality_bench.common.logs import PACKAGE_LOGGER, setup_logging


@pytest.fixture(autouse=True)
def _restore_package_logger():
    """Rend le logger du paquet dans son état initial (fichiers fermés avant le nettoyage)."""
    yield
    logger = logging.getLogger(PACKAGE_LOGGER)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def test_setup_logging_writes_utf8_file_and_console(capsys):
    log_file = paths.log_path("c1", "generate")
    logger = setup_logging("generate", log_file)
    assert logger.name == PACKAGE_LOGGER == "scripts.quality_bench"
    logging.getLogger("scripts.quality_bench.common.jsonl").warning("Arrêt demandé : été")
    for handler in logger.handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "Arrêt demandé : été" in content
    assert "[generate]" in content
    assert "Arrêt demandé" in capsys.readouterr().err


def test_setup_logging_replaces_previous_handlers():
    setup_logging("grade", paths.log_path("c1", "grade"))
    logger = setup_logging("grade", None)
    assert len(logger.handlers) == 1
    assert not logger.propagate
