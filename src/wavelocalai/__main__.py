"""Lanceur `wavelocalai-v2` : réglages, télémétrie, dossier de données, journaux, verrou, port.

Le serveur ne démarre qu'une fois le verrou du dossier de données pris et le port ouvert ; sinon
le lanceur s'arrête avec un message clair (AD-23).
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from wavelocalai.config import DEFAULT_PORT, ConfigError, load_settings
from wavelocalai.store.datadir import (
    DataDirLock,
    DataDirLockError,
    ensure_data_dir,
    is_under_onedrive,
)
from wavelocalai.store.db import Store, db_path
from wavelocalai.store.logs import close_logging, setup_logging
from wavelocalai.store.migrate import MigrationError
from wavelocalai.telemetry import disable_telemetry

logger = logging.getLogger("wavelocalai")


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wavelocalai-v2", description="Serveur local wavelocalai v2 (127.0.0.1)."
    )
    parser.add_argument("--port", type=int, help=f"port d'écoute (défaut {DEFAULT_PORT})")
    parser.add_argument("--data-dir", type=Path, help="dossier des données (défaut : data/)")
    parser.add_argument("--config", type=Path, help="fichier de réglages (wavelocalai.toml)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée du script `wavelocalai-v2` ; rend le code de sortie."""
    args = _parse(argv)
    overrides: dict[str, dict[str, object]] = {}
    if args.port is not None:
        overrides["server"] = {"port": args.port}
    if args.data_dir is not None:
        overrides["data"] = {"dir": args.data_dir.resolve()}
    try:
        settings = load_settings(args.config, overrides=overrides)
    except ConfigError as exc:
        print(f"wavelocalai-v2 : {exc}", file=sys.stderr)
        return 2

    disable_telemetry(settings.env_file)  # avant tout import de la pile web
    try:
        data_dir = ensure_data_dir(settings.data_dir)
    except OSError as exc:
        print(
            f"wavelocalai-v2 : dossier de données {settings.data_dir} inutilisable : "
            f"{exc.strerror or exc}",
            file=sys.stderr,
        )
        return 1
    # Le verrou d'abord, les journaux ensuite : un second lancement refusé n'écrit rien dans le
    # journal du serveur vivant (C5). Ses refus vont sur la console seulement.
    lock = DataDirLock(data_dir)
    try:
        lock.acquire()
    except DataDirLockError as exc:
        print(f"wavelocalai-v2 : {exc}", file=sys.stderr)
        return 1
    try:
        setup_logging(data_dir, secrets=tuple(settings.secret_values()))
        try:
            if is_under_onedrive(data_dir):
                logger.warning(
                    "Le dossier de données %s est sous OneDrive : la synchronisation peut "
                    "corrompre la base. Choisissez un dossier hors OneDrive (--data-dir).",
                    data_dir,
                )
            from wavelocalai.web.server import PortBusyError, bind_socket, serve

            try:
                sock = bind_socket(settings.server.port)
            except PortBusyError as exc:
                print(f"wavelocalai-v2 : {exc}", file=sys.stderr)
                logger.error("%s", exc)
                return 1
            try:
                store = Store.open(db_path(data_dir))  # migre la base, ou refuse de démarrer
            except (MigrationError, sqlite3.Error, OSError) as exc:
                sock.close()
                print(f"wavelocalai-v2 : {exc}", file=sys.stderr)
                logger.error("%s", exc)
                return 1
            logger.info(
                "wavelocalai-v2 sur http://127.0.0.1:%d (données : %s)",
                settings.server.port,
                data_dir,
            )
            try:
                serve(settings, sock, store)
            finally:
                store.close()
                lock.release()
            logger.info("wavelocalai-v2 arrêté : base fermée, verrou relâché")
        finally:
            close_logging()
    finally:
        lock.release()  # idempotent : couvre toutes les sorties, exceptions comprises
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
