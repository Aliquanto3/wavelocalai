"""Lanceur `wavelocalai-v2` : réglages, télémétrie, dossier de données, journaux, verrou, port.

Le serveur ne démarre qu'une fois le verrou du dossier de données pris et le port ouvert ; sinon
le lanceur s'arrête avec un message clair (AD-23).
"""

from __future__ import annotations

import argparse
import logging
import socket
import sqlite3
import sys
import threading
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from wavelocalai.config import DEFAULT_PORT, LOOPBACK, ConfigError, load_settings
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

# Fenêtre de sonde du port avant d'abandonner l'ouverture du navigateur (serveur très lent à
# démarrer, ou qui ne démarre pas) : large, pour ne jamais ouvrir avant que le port réponde.
BROWSER_PROBE_TIMEOUT_S = 30.0
BROWSER_PROBE_INTERVAL_S = 0.1


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wavelocalai-v2", description="Serveur local wavelocalai v2 (127.0.0.1)."
    )
    parser.add_argument("--port", type=int, help=f"port d'écoute (défaut {DEFAULT_PORT})")
    parser.add_argument("--data-dir", type=Path, help="dossier des données (défaut : data/)")
    parser.add_argument("--config", type=Path, help="fichier de réglages (wavelocalai.toml)")
    parser.add_argument(
        "--no-browser", action="store_true", help="n'ouvre pas le navigateur au démarrage"
    )
    return parser.parse_args(argv)


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection((LOOPBACK, port), timeout=0.2):
            return True
    except OSError:
        return False


def _open_browser_when_ready(url: str, port: int, stop: threading.Event) -> None:
    """Sonde le port (jamais un délai fixe) puis ouvre le navigateur une seule fois. Un échec
    d'ouverture (pas de navigateur, session sans affichage) écrit l'URL sur la console et dans le
    journal ; le serveur, déjà en service, continue sans lui."""
    deadline = time.monotonic() + BROWSER_PROBE_TIMEOUT_S
    while not stop.is_set() and time.monotonic() < deadline:
        if _port_is_open(port):
            break
        time.sleep(BROWSER_PROBE_INTERVAL_S)
    else:
        return
    if stop.is_set():
        return
    opened = False
    try:
        opened = webbrowser.open(url)
    except Exception:  # noqa: BLE001 — l'ouverture ne doit jamais faire tomber le serveur
        logger.exception("Ouverture du navigateur en échec")
    if not opened:
        print(f"wavelocalai-v2 : ouvrez {url} dans votre navigateur.", file=sys.stderr)
        logger.warning("Ouverture automatique du navigateur impossible : %s", url)


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
            open_browser = not args.no_browser and settings.server.open_browser
            stop_browser = threading.Event()
            if open_browser:
                url = f"http://{LOOPBACK}:{settings.server.port}/"
                threading.Thread(
                    target=_open_browser_when_ready,
                    args=(url, settings.server.port, stop_browser),
                    daemon=True,
                ).start()
            try:
                serve(settings, sock, store)
            finally:
                stop_browser.set()
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
