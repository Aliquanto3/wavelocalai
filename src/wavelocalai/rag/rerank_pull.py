"""Installation du reranker depuis l'écran Modèles : un run racine `pull` (story 5.5, AD-5, AD-14, AD-17).

`POST /api/models/reranker/pull` appelle `RerankerPullService.start` : même genre de run que
l'installation d'un modèle d'Ollama (`inference/pull.py`), donc un seul `pull` à la fois (`run_busy`).
Le téléchargement tourne dans un processus à part (`rag/rerank_fetch.py`) que l'annulation tue ; il va
dans le `cache_dir` du dossier de données. C'est le seul téléchargement du reranker : la recherche
elle-même charge toujours en `local_files_only=True`.

`pull_progress` (même forme que pour un modèle d'Ollama) porte en plus `reranker: true` ; `tag` est le
nom du modèle fastembed. Les octets reçus sont la taille du dossier du modèle dans le cache (fastembed ne
rend aucune progression) ; le total est la taille annoncée par fastembed pour ce modèle, `0` (donc
pourcentage `null`) si elle est inconnue. Le reçu reste sous le total tant que le chargement de
vérification n'a pas fini. À la fin, l'état du reranker est relu : la recherche suivante reclasse, sans
redémarrage. Un échec ou une annulation retire le dossier du modèle s'il n'existait pas avant
(« non installé » reste vrai) ; sinon il est gardé.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from wavelocalai.config import Settings
from wavelocalai.errors import AppError, build_envelope, pull_failed_envelope
from wavelocalai.inference.pull import PROGRESS_INTERVAL_S, ProgressThrottle, progress_data
from wavelocalai.models.ollama_pull import PullUpdate
from wavelocalai.rag.rerank import RerankerService, fastembed_missing_reason, install_marker
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import RunHandle
from wavelocalai.telemetry import disable_telemetry

logger = logging.getLogger("wavelocalai.rag")

GIB = 1024**3


class RerankerFetchError(Exception):
    """Le téléchargement a échoué ; `str(exc)` est le détail technique."""


Fetcher = Callable[[str, Path, "str | Path | None"], Awaitable[None]]
Measure = Callable[[Path], int]
Expected = Callable[[str, "str | Path | None"], int]


async def fetch_in_subprocess(model: str, cache: Path, env_file: str | Path | None = None) -> None:
    """Télécharge le modèle dans un processus à part (`rerank_fetch`), tué si la tâche est annulée."""
    args = [sys.executable, "-m", "wavelocalai.rag.rerank_fetch", model, str(cache)]
    if env_file is not None:
        args.append(str(env_file))
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await process.communicate()
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        raise
    if process.returncode == 2:
        raise RerankerFetchError(fastembed_missing_reason())
    if process.returncode != 0:
        lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise RerankerFetchError(lines[-1] if lines else f"code de sortie {process.returncode}")


def expected_bytes(model: str, env_file: str | Path | None = None) -> int:
    """La taille du modèle annoncée par fastembed (`size_in_GB`), 0 si elle est inconnue."""
    disable_telemetry(env_file)  # avant l'import de fastembed (AD-21)
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        for entry in TextCrossEncoder.list_supported_models():
            if str(entry.get("model", "")).lower() == model.lower():
                return int(float(entry.get("size_in_GB") or 0) * GIB)
    except Exception:  # noqa: BLE001 - un total inconnu n'empêche pas l'installation
        return 0
    return 0


def folder_size(path: Path) -> int:
    """Octets des fichiers sous `path` (liens non suivis) ; 0 si le dossier n'existe pas encore."""
    total = 0
    stack = [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


def model_folder(cache: Path, model: str) -> Path:
    """Le dossier du modèle dans le cache de Hugging Face : `models--<organisation>--<nom>`."""
    return cache / f"models--{model.replace('/', '--')}"


class RerankerPullService:
    def __init__(
        self,
        hub: RunHub,
        reranker: RerankerService,
        settings: Settings,
        *,
        fetch: Fetcher = fetch_in_subprocess,
        expected: Expected = expected_bytes,
        measure: Measure = folder_size,
        interval_s: float = PROGRESS_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._hub = hub
        self._reranker = reranker
        self._settings = settings
        self._fetch = fetch  # tests : jamais un vrai téléchargement
        self._expected = expected
        self._measure = measure
        self._interval_s = interval_s
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> RunHandle:
        """Crée le run `pull` du reranker et rend `{run_id}` aussitôt. `invalid_request` si le modèle
        est déjà installé ; `run_busy` si une installation tourne."""
        status = self._reranker.status()
        model = self._reranker.model
        if status.available:
            raise AppError("invalid_request", f"Le reranker {model} est déjà installé.")
        handle = await self._hub.create_run(
            "pull", models=[model], params={"tag": model, "reranker": True}
        )
        task = asyncio.create_task(self._run(handle), name=f"wavelocalai-rerank-{handle.run_id}")
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _run(self, handle: RunHandle) -> None:
        run_id, model, cache = handle.run_id, self._reranker.model, self._reranker.cache
        folder = model_folder(cache, model)
        marker = install_marker(cache, model)
        if marker.exists():  # installation coupée par un arrêt brutal : le dossier est partiel
            shutil.rmtree(folder, ignore_errors=True)
        existed = folder.exists()
        secrets = self._settings.secret_values()
        done = False

        def publish(update: PullUpdate) -> None:
            data = {**progress_data(model, update), "reranker": True}
            self._hub.publish(run_id, "pull_progress", data)

        throttle = ProgressThrottle(publish, self._interval_s, self._clock)
        try:
            if not existed:  # retiré une fois le modèle vérifié ; sinon « non installé » reste vrai
                cache.mkdir(parents=True, exist_ok=True)
                marker.write_text(run_id, encoding="utf-8")
            throttle.push(PullUpdate("preparing"), force=True)
            total = await asyncio.to_thread(self._expected, model, self._settings.env_file)
            fetching = asyncio.ensure_future(self._fetch(model, cache, self._settings.env_file))
            try:
                while not fetching.done():
                    await asyncio.wait({fetching}, timeout=self._interval_s)
                    received = await asyncio.to_thread(self._measure, folder)
                    if total > 0:
                        cap = int(total * 0.99)  # sous le total tant que la vérification tourne
                        received = min(received, cap)
                        phase = "verifying" if received >= cap else "downloading"
                    else:
                        phase = "downloading"
                    throttle.push(PullUpdate(phase, received, total))
                await fetching
            finally:
                if not fetching.done():
                    fetching.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await fetching
            final = max(total, await asyncio.to_thread(self._measure, folder))
            throttle.push(PullUpdate("verifying", final, final, done=True), force=True)
            throttle.close()
            marker.unlink(missing_ok=True)
            self._reranker.refresh()
            done = True
            await self._hub.finish_run(run_id, "ok")
        except asyncio.CancelledError:
            raise  # `hub.cancel` a déjà fixé `cancelled` ; le processus de téléchargement est tué
        except RerankerFetchError as exc:
            throttle.close()
            logger.warning("Installation du reranker %s en échec : %s", model, exc)
            error = pull_failed_envelope(model, "reranker_failed", str(exc), secrets)
            await self._hub.finish_run(run_id, "error", error=error)
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            throttle.close()
            logger.error("Installation du reranker %s interrompue", model, exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            await self._hub.finish_run(run_id, "error", error=error)
        finally:
            throttle.close()
            if not done and not existed:
                shutil.rmtree(folder, ignore_errors=True)  # « non installé » reste vrai
                marker.unlink(missing_ok=True)


class FakeFetcher:
    """Installation factice des tests (`Settings.testing`, `POST /api/test/reranker-install`) : aucun
    réseau, aucun modèle. Les octets sont simulés (`expected`, `measure`) ; `fetch` écrit un faux
    dossier de modèle à la fin. `mode` : `ok`, `fail` (échec à mi-course, `reason` en détail
    technique) ou `hang` (plus rien après le premier pas, jusqu'à l'annulation)."""

    def __init__(
        self,
        mode: str = "ok",
        *,
        total_bytes: int = GIB,
        steps: int = 4,
        step_delay_s: float = 0.0,
        reason: str = "connexion refusée",
    ) -> None:
        self.mode = mode
        self.total_bytes = total_bytes
        self.steps = max(1, steps)
        self.step_delay_s = step_delay_s
        self.reason = reason
        self.written = 0
        self.calls = 0  # nombre de téléchargements lancés

    def expected(self, model: str, env_file: str | Path | None = None) -> int:
        return self.total_bytes

    def measure(self, folder: Path) -> int:
        return self.written

    async def fetch(self, model: str, cache: Path, env_file: str | Path | None = None) -> None:
        self.calls += 1
        self.written = 0
        folder = model_folder(cache, model)
        folder.mkdir(parents=True, exist_ok=True)
        for step in range(1, self.steps + 1):
            await asyncio.sleep(self.step_delay_s)
            self.written = self.total_bytes * step // self.steps
            if self.mode == "hang" and step == 1:
                await asyncio.Event().wait()  # jusqu'à l'annulation
            if self.mode == "fail" and step == max(1, self.steps // 2):
                raise RerankerFetchError(self.reason)
        snapshot = folder / "snapshots" / "test"
        snapshot.mkdir(parents=True, exist_ok=True)
        (snapshot / "model.onnx").write_bytes(b"fake")
