"""Journaux en rotation dans `data/logs/` (AD-23).

5 fichiers de 1 Mo au plus (le courant et 4 archives). Aucun texte de prompt, de réponse ou de
document au niveau INFO : c'est aux appelants de s'y tenir. Toute clé d'API reconnaissable est
masquée à l'écriture (AD-18), exceptions comprises.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from wavelocalai.errors import mask_secrets

LOG_NAME = "wavelocalai.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 4  # + le fichier courant = 5 fichiers
LOGGERS = ("wavelocalai", "uvicorn", "uvicorn.error", "uvicorn.access")
_TAG = "_wavelocalai_handler"


class MaskingFormatter(logging.Formatter):
    """Masque les clés d'API dans la ligne finale, trace d'exception incluse."""

    def __init__(self, *args: object, secrets: tuple[str, ...] = (), **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._secrets = secrets

    def format(self, record: logging.LogRecord) -> str:
        return mask_secrets(super().format(record), self._secrets)


def setup_logging(
    data_dir: Path,
    *,
    console: bool = True,
    level: int = logging.INFO,
    secrets: tuple[str, ...] = (),
) -> Path:
    """Branche fichier tournant (et console) sur les journaux du serveur ; idempotent."""
    close_logging()
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_NAME
    formatter = MaskingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s", secrets=secrets)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
    ]
    if console:
        handlers.append(logging.StreamHandler(sys.stderr))
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.setLevel(level)
        setattr(handler, _TAG, True)
    for name in LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False
        for handler in handlers:
            logger.addHandler(handler)
    return log_file


def close_logging() -> None:
    """Retire et ferme les gestionnaires posés par `setup_logging`."""
    for name in LOGGERS:
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if getattr(handler, _TAG, False):
                logger.removeHandler(handler)
                handler.close()
