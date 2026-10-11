"""Journal des commandes : fichier ``log-<commande>.log`` et console, en UTF-8 (convention
« Journal » du spine). Jamais de contenu de question privée dans un message."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Logger du paquet (« scripts.quality_bench ») : les modules journalisent par
# ``logging.getLogger(__name__)`` et héritent de ses gestionnaires.
PACKAGE_LOGGER = __name__.rsplit(".common", 1)[0]
_FORMAT = "%(asctime)s %(levelname)s [%(command)s] %(name)s : %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"


class _CommandFilter(logging.Filter):
    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command

    def filter(self, record: logging.LogRecord) -> bool:
        record.command = self.command
        return True


def setup_logging(command: str, log_path: Path | None, level: int = logging.INFO) -> logging.Logger:
    """Configure le logger du paquet : console (stderr) et, si ``log_path`` est donné, fichier
    en ajout (``paths.log_path(campagne, commande)``). Un nouvel appel remplace les
    gestionnaires du précédent."""
    logger = logging.getLogger(PACKAGE_LOGGER)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    command_filter = _CommandFilter(command)

    console = logging.StreamHandler(sys.stderr)
    handlers: list[logging.Handler] = [console]
    if log_path is not None:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, mode="a", encoding="utf-8"))
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(command_filter)
        logger.addHandler(handler)
    return logger
