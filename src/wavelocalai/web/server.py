"""Démarrage d'uvicorn sur 127.0.0.1 : seul `web/` importe uvicorn (AD-4, AD-19)."""

from __future__ import annotations

import logging
import socket
import sys

import uvicorn
from fastapi import FastAPI

from wavelocalai.config import LOOPBACK, Settings
from wavelocalai.store.db import Store
from wavelocalai.web.app import create_app, stop_streams

logger = logging.getLogger("wavelocalai.web")

# Filet : une connexion qui ne finit toujours pas est coupée après ce délai, puis le cycle de vie
# s'arrête (hub, base). Sans lui, uvicorn attend sans fin (`timeout_graceful_shutdown=None`).
GRACEFUL_SHUTDOWN_S = 5.0


class PortBusyError(Exception):
    """Le port d'écoute est déjà pris."""


def bind_socket(port: int) -> socket.socket:
    """Ouvre le port d'écoute (127.0.0.1 seulement) ; `PortBusyError` s'il est occupé.

    Le socket est ouvert ici puis confié à uvicorn : pas de course entre le contrôle et l'écoute.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != "win32":  # sous Windows, SO_REUSEADDR laisserait voler un port occupé
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((LOOPBACK, port))
    except OSError as exc:
        sock.close()
        raise PortBusyError(
            f"Le port {port} est occupé : un autre programme (ou un autre wavelocalai-v2) "
            f"l'utilise. Fermez-le, ou lancez avec --port <autre port>."
        ) from exc
    return sock


class _Server(uvicorn.Server):
    """uvicorn attend la fin des connexions **avant** l'arrêt du cycle de vie : les flux ouverts
    (système, runs actifs) sont donc terminés d'abord, sinon l'arrêt ne vient jamais."""

    def __init__(self, config: uvicorn.Config, app: FastAPI) -> None:
        super().__init__(config)
        self._app = app

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        for server in self.servers:
            server.close()  # plus de nouvelle connexion pendant qu'on ferme les flux
        try:
            await stop_streams(self._app)
        except Exception:
            logger.exception("Arrêt : les flux ouverts n'ont pas pu être fermés")
        await super().shutdown(sockets)


def serve(settings: Settings, sock: socket.socket, store: Store | None = None) -> None:
    """Sert l'application jusqu'à l'arrêt (Ctrl+C ou SIGTERM : arrêt propre d'uvicorn, qui
    annule les runs actifs). `store` : la base ouverte par le lanceur, qui la ferme ensuite."""
    app = create_app(settings, store=store)
    config = uvicorn.Config(
        app,
        host=LOOPBACK,
        port=settings.server.port,
        log_config=None,  # les journaux sont réglés par `store/logs.py`
        server_header=False,
        proxy_headers=False,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S,
    )
    _Server(config, app).run(sockets=[sock])
