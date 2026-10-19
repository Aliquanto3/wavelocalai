"""Faux Ollama pour l'installation d'un modèle (story 5.3) : `POST /api/pull` en flux NDJSON scripté.

S'ajoute à `FakeOllama` (`/api/tags`, `/api/show`, `/api/ps`) : chaque appel à `/api/pull` consomme
le script suivant. Aucun vrai téléchargement n'est jamais lancé : le transport est simulé, ou le
serveur de test pointe sur un faux Ollama local.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from .fake_ollama import FakeOllama

GB = 1024**3


def manifest() -> dict[str, Any]:
    return {"status": "pulling manifest"}


def layer(digest: str, total: int, completed: int) -> dict[str, Any]:
    return {
        "status": f"pulling {digest[:12]}",
        "digest": digest,
        "total": total,
        "completed": completed,
    }


def verifying() -> dict[str, Any]:
    return {"status": "verifying sha256 digest"}


def success() -> dict[str, Any]:
    return {"status": "success"}


def download(total: int = 4 * GB, steps: int = 4) -> list[dict[str, Any]]:
    """Un téléchargement entier en une couche : préparation, `steps` avancées, vérification, fin."""
    lines = [manifest()]
    lines += [layer("sha256:aaaa1111bbbb", total, total * i // steps) for i in range(1, steps + 1)]
    return [*lines, verifying(), {"status": "writing manifest"}, success()]


@dataclass
class PullScript:
    """Un appel à `/api/pull`. `end` : `done` (le flux se termine après `lines`), `hang` (plus
    rien, jusqu'à l'annulation), `error` (coupure de lecture), `refuse` (connexion refusée),
    `http_error` (statut `status` et corps `body`)."""

    lines: Sequence[dict[str, Any]] = ()
    end: str = "done"
    status: int = 200
    body: str = ""
    hold: asyncio.Event | None = None  # le flux ne part qu'une fois l'événement levé
    pause_after: int | None = None  # nombre de lignes envoyées avant d'attendre `resume`
    resume: asyncio.Event | None = None


@dataclass
class PullOllama(FakeOllama):
    scripts: list[PullScript] = field(default_factory=list)
    pull_requests: list[dict[str, Any]] = field(default_factory=list)
    pull_opened: int = 0
    pull_closed: int = 0
    on_success: Any = None  # appelé avec le tag quand le flux va jusqu'à `success`

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.path != "/api/pull":
            return await super()._handle(request)
        body = json.loads(request.content)
        self.pull_requests.append(body)
        script = self.scripts.pop(0) if self.scripts else PullScript(download())
        if script.end == "refuse":
            raise httpx.ConnectError("connexion refusée", request=request)
        if script.end == "http_error":
            return httpx.Response(script.status, text=script.body)
        self.pull_opened += 1
        return httpx.Response(200, stream=_PullStream(self, script, body.get("model", "")))


class _PullStream(httpx.AsyncByteStream):
    def __init__(self, owner: PullOllama, script: PullScript, tag: str) -> None:
        self._owner = owner
        self._script = script
        self._tag = tag

    async def __aiter__(self) -> AsyncIterator[bytes]:
        script = self._script
        if script.hold is not None:
            await script.hold.wait()
        for index, line in enumerate(script.lines, 1):
            if line.get("status") == "success" and self._owner.on_success is not None:
                self._owner.on_success(self._tag)  # le modèle est installé quand Ollama le dit
            yield (json.dumps(line) + "\n").encode()
            await asyncio.sleep(0)
            if script.pause_after == index and script.resume is not None:
                await script.resume.wait()
        if script.end == "hang":
            await asyncio.Event().wait()
        if script.end == "error":
            raise httpx.ReadError("connexion coupée")

    async def aclose(self) -> None:
        self._owner.pull_closed += 1


# --- Faux Ollama pour le navigateur (le vrai serveur de l'application lui parle en HTTP) -------------


class ThreadedOllama:
    """Un Ollama HTTP local pour les tests E2E de l'installation : `/api/version`, `/api/tags`,
    `/api/show`, `/api/ps` et `/api/pull` en flux scripté. Le vrai Ollama n'est jamais sollicité.

    Un script de `/api/pull` est une liste d'étapes : un dict (une ligne NDJSON ; la ligne
    `success` ajoute le modèle à `/api/tags`), un `threading.Event` (le flux attend qu'il soit
    levé), la chaîne `"hang"` (le flux ne finit plus : il attend que le client coupe) ou `"cut"`
    (la connexion est coupée net, sans fin de flux)."""

    VERSION = "0.9.9"

    def __init__(self, port: int) -> None:
        self.port = port
        self.sizes: dict[str, int] = {}  # tag -> octets ; les modèles installés
        self.params: dict[str, str] = (
            {}
        )  # tag -> `parameter_size` d'Ollama (« 7B »), « 1.5B » sinon
        self.tools: set[str] = set()  # tags dont `/api/show` dit `tools` (agent éligible)
        self.scripts: list[list[Any]] = []
        self.pull_requests: list[str] = []
        self.pull_dropped = 0  # flux coupés par le client (annulation)
        self.loaded: list[str] = []
        self.deleted: list[str] = []  # modèles supprimés par `DELETE /api/delete` (story 5.4)
        self.unloaded: list[str] = []  # modèles déchargés (`keep_alive: 0`)
        self._stop = False
        self._httpd: Any = None

    def install(self, tag: str, size: int = GB) -> None:
        self.sizes[tag] = size

    def reset(self, installed: dict[str, int] | None = None) -> None:
        self.sizes = dict(installed or {})
        self.params = {}
        self.tools = set()
        self.scripts = []
        self.pull_requests = []
        self.pull_dropped = 0
        self.loaded = []
        self.deleted = []
        self.unloaded = []

    def start(self) -> None:
        import http.server
        import threading

        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _json(self, body: Any) -> None:
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):  # noqa: N802
                if self.path == "/api/version":
                    self._json({"version": owner.VERSION})
                elif self.path == "/api/tags":
                    self._json(
                        {
                            "models": [
                                {
                                    "model": tag,
                                    "digest": f"d-{tag}",
                                    "size": size,
                                    "details": {
                                        "family": "qwen2",
                                        "parameter_size": owner.params.get(tag, "1.5B"),
                                        "quantization_level": "Q4_K_M",
                                    },
                                }
                                for tag, size in owner.sizes.items()
                            ]
                        }
                    )
                elif self.path == "/api/ps":
                    self._json(
                        {
                            "models": [
                                {"model": t, "name": t, "size": GB, "size_vram": 0}
                                for t in owner.loaded
                            ]
                        }
                    )
                else:
                    self.send_error(404)

            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                if self.path == "/api/show":
                    caps = ["completion", *(["tools"] if body.get("model") in owner.tools else [])]
                    self._json({"capabilities": caps, "model_info": {}})
                elif self.path == "/api/pull":
                    self._pull(str(body.get("model", "")))
                elif self.path in ("/api/generate", "/api/embed") and body.get("keep_alive") == 0:
                    tag = str(body.get("model", ""))  # « Décharger » (story 5.4)
                    owner.unloaded.append(tag)
                    if tag in owner.loaded:
                        owner.loaded.remove(tag)
                    self._json({"model": tag, "done": True})
                else:
                    self.send_error(404)

            def do_DELETE(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                tag = str(body.get("model", ""))
                if self.path != "/api/delete" or tag not in owner.sizes:
                    self.send_error(404)
                    return
                del owner.sizes[tag]
                owner.deleted.append(tag)
                if tag in owner.loaded:
                    owner.loaded.remove(tag)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def _write(self, data: bytes) -> bool:
                try:
                    self.wfile.write(data)
                    self.wfile.flush()
                except OSError:
                    owner.pull_dropped += 1  # le client a refermé le flux
                    return False
                return True

            def _pull(self, tag: str) -> None:
                owner.pull_requests.append(tag)
                script = owner.scripts.pop(0) if owner.scripts else list(download())
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                for step in script:
                    if isinstance(step, threading.Event):
                        while not step.wait(0.05):
                            if owner._stop or not self._write(b"\n"):
                                return
                    elif step == "hang":
                        while not owner._stop:
                            if not self._write(b"\n"):
                                return
                            threading.Event().wait(0.05)
                        return
                    elif step == "cut":
                        return
                    else:
                        if step.get("status") == "success":
                            owner.sizes[tag] = GB
                        if not self._write((json.dumps(step) + "\n").encode()):
                            return

            def log_message(self, *args):  # noqa: D102
                pass

        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._stop = True
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
