"""Sert la maquette sur 127.0.0.1, sur un port libre, et ouvre le navigateur.

Usage : python serveur.py [--port N] [--sans-navigateur]
Rien ne sort du poste : le serveur n'écoute que 127.0.0.1 et la page ne charge que ce dossier.
Les types MIME sont fixés ici : sous Windows, le registre associe parfois `.js` à `text/plain`, ce
qui fait refuser les modules ES par le navigateur avec `python -m http.server`.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socket
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **TYPES}

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        pass


class Server(http.server.ThreadingHTTPServer):
    # La page charge une trentaine de modules d'un coup : la file d'attente par défaut (5) fait
    # refuser des connexions sous Windows.
    request_queue_size = 128
    daemon_threads = True


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_server(port: int = 0, root: Path = ROOT) -> Server:
    handler = functools.partial(Handler, directory=str(root))
    return Server(("127.0.0.1", port or free_port()), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sert la maquette de WaveLocalAI v2.")
    parser.add_argument("--port", type=int, default=0, help="port (libre par défaut)")
    parser.add_argument(
        "--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur"
    )
    args = parser.parse_args()
    server = make_server(args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Maquette servie sur {url}  (Ctrl+C ou fermer cette fenêtre pour arrêter)")
    if not args.sans_navigateur:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
