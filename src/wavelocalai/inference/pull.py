"""Installation d'un modèle : un run racine `pull` (AD-5, AD-14, AD-17), seule action qui télécharge.

`POST /api/models/pull {tag}` appelle `PullService.start` : le tag est contrôlé (nom d'Ollama, jamais
un tag distant : ses données quitteraient le poste), le hub crée le run racine `pull` (`run_busy` si
une installation tourne déjà : l'écran la rejoint), et une tâche suit le flux `/api/pull` d'Ollama
(`models/ollama_pull.py`). Le téléchargement ne prend pas la place « Ollama local » : il ne charge
aucun modèle et ne doit pas bloquer une réponse.

Événement publié (en plus de ceux du hub), ajout à `contrat-api.md` :
- `pull_progress {tag, received_bytes, total_bytes, percent, phase}` ; `phase` : `preparing`,
  `downloading`, `verifying` ; `percent` entier de 0 à 100, `null` tant que le total est inconnu.
  Au plus quatre par seconde (les lignes d'Ollama arrivent bien plus vite) : un changement de
  phase part toujours, et la dernière mise à jour n'est jamais perdue (elle part à l'échéance si
  Ollama se tait). Un téléchargement de plusieurs minutes ne remplit ni la mémoire ni la base.

Fin du run : `ok` quand Ollama dit `success` (le registre est relu avant `run_ended`, la liste
des modèles est donc à jour quand l'écran la relit), `cancelled` à l'annulation (Ollama garde les
couches reçues : une nouvelle installation reprend), `error` avec `pull_failed` (`detail.tag` et
`detail.cause`) sinon ; la liste des modèles reste inchangée.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Callable

import httpx

from wavelocalai.config import Settings
from wavelocalai.errors import AppError, build_envelope, pull_failed_envelope
from wavelocalai.models.classify import is_remote_tag
from wavelocalai.models.ollama_pull import PullError, PullUpdate, pull_updates
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import RunHandle

logger = logging.getLogger("wavelocalai.inference")

PROGRESS_INTERVAL_S = 0.25  # au plus quatre `pull_progress` par seconde
REFRESH_WAIT_S = 8.0  # attente du registre avant la fin du run (liste, puis détails du modèle)
# Nom d'Ollama : `qwen3.6:7b`, `hf.co/utilisateur/depot:Q4_K_M`, `registre/nom:variante`.
TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/:@]{0,199}$")


def clean_tag(raw: str) -> str:
    """Le tag à installer, sans espaces autour ; `invalid_request` s'il n'a pas la forme d'un nom
    d'Ollama, `cloud_not_allowed` s'il vise un modèle distant."""
    tag = raw.strip()
    if not TAG_PATTERN.match(tag) or ".." in tag:
        raise AppError("invalid_request", f"Nom de modèle invalide : {raw[:80]!r}.")
    if is_remote_tag({"model": tag}):
        raise AppError("cloud_not_allowed", f"{tag} est hébergé hors de ce poste.", tag=tag)
    return tag


def progress_data(tag: str, update: PullUpdate) -> dict[str, object]:
    total = update.total_bytes
    received = min(update.received_bytes, total) if total > 0 else update.received_bytes
    percent = None if total <= 0 else min(100, int(received * 100 / total))
    return {
        "tag": tag,
        "received_bytes": received,
        "total_bytes": total,
        "percent": percent,
        "phase": update.phase,
    }


class _Throttle:
    """Publie la progression au plus une fois par `interval_s`, un changement de phase toujours, et
    la dernière mise à jour jamais perdue : si Ollama se tait un moment (vérification, pause), l'état
    en attente part à l'échéance plutôt que de laisser l'écran sur un chiffre périmé."""

    def __init__(
        self, publish: Callable[[PullUpdate], object], interval_s: float, clock: Callable[[], float]
    ) -> None:
        self._publish = publish
        self._interval_s = interval_s
        self._clock = clock
        self._at = float("-inf")
        self._phase = ""
        self._pending: PullUpdate | None = None
        self._timer: asyncio.TimerHandle | None = None

    def push(self, update: PullUpdate, *, force: bool = False) -> None:
        now = self._clock()
        if force or update.phase != self._phase or now - self._at >= self._interval_s:
            self._emit(update, now)
            return
        self._pending = update
        if self._timer is None:
            delay = max(0.0, self._at + self._interval_s - now)
            self._timer = asyncio.get_running_loop().call_later(delay, self._flush)

    def _emit(self, update: PullUpdate, now: float) -> None:
        self._cancel_timer()
        self._pending = None
        self._publish(update)
        self._at, self._phase = now, update.phase

    def _flush(self) -> None:
        self._timer = None
        if self._pending is not None:
            self._emit(self._pending, self._clock())

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def close(self) -> None:
        """Plus rien ne part : la mise à jour en attente est abandonnée (fin du run)."""
        self._cancel_timer()
        self._pending = None


class PullService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        interval_s: float = PROGRESS_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._settings = settings
        self._transport = transport  # tests : faux Ollama ; jamais un vrai téléchargement
        self._interval_s = interval_s
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()  # références fortes jusqu'à la fin

    async def start(self, raw_tag: str) -> RunHandle:
        """Crée le run `pull` et rend `{run_id}` aussitôt ; le téléchargement suit en tâche.
        Lève `invalid_request`, `cloud_not_allowed` ou `run_busy` (une installation est active)."""
        tag = clean_tag(raw_tag)
        handle = await self._hub.create_run("pull", models=[tag], params={"tag": tag})
        task = asyncio.create_task(self._run(handle, tag), name=f"wavelocalai-pull-{handle.run_id}")
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _run(self, handle: RunHandle, tag: str) -> None:
        run_id = handle.run_id
        secrets = self._settings.secret_values()
        progress = _Throttle(
            lambda update: self._hub.publish(run_id, "pull_progress", progress_data(tag, update)),
            self._interval_s,
            self._clock,
        )
        try:
            progress.push(PullUpdate("preparing"), force=True)
            async for update in pull_updates(
                self._settings.ollama.host, tag, transport=self._transport
            ):
                progress.push(update, force=update.done)
            progress.close()
            await self._refresh_registry()
            await self._hub.finish_run(run_id, "ok")
        except asyncio.CancelledError:
            raise  # `hub.cancel` a déjà fixé `cancelled` ; la connexion à Ollama se ferme
        except PullError as exc:
            progress.close()
            logger.warning("Installation de %s en échec (%s) : %s", tag, exc.cause, exc.technical)
            error = pull_failed_envelope(tag, exc.cause, exc.technical, secrets)
            await self._hub.finish_run(run_id, "error", error=error)
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            progress.close()
            logger.error("Installation de %s interrompue par une erreur", tag, exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            await self._hub.finish_run(run_id, "error", error=error)
        finally:
            progress.close()  # annulation comprise : aucun événement tardif sur un run clos

    async def _refresh_registry(self) -> None:
        """La liste des modèles est relue avant la fin du run : à `run_ended`, `GET /api/models`
        rend déjà le modèle. Ollama muet ou lent : la liste se rafraîchira au prochain appel."""
        self._registry.invalidate()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self._registry.refresh(), REFRESH_WAIT_S)
