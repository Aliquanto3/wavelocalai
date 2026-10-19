"""Le hub des runs : seul à créer, numéroter, persister, annuler et terminer un run (AD-5, AD-7).

Tout se passe dans la boucle d'événements : `publish` est synchrone et ne touche que la mémoire ;
les écritures SQLite passent par l'écrivain unique du store (`Store.awrite`). Un run racine garde
tous ses événements en mémoire tant qu'il est actif ; une tâche de fond les écrit par lots d'au plus
une seconde, et `run_ended`, le statut final et le message assistant partent dans une même
transaction. Les runs enfants (un par appel de modèle) ne portent pas de flux : le parent publie
seul, et métriques et CO2 ne vivent que sur les feuilles (`finish_leaf`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sqlite3
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from wavelocalai.errors import AppError
from wavelocalai.runs import repo
from wavelocalai.runs.models import (
    CONVERSATION_KINDS,
    FINAL_STATUSES,
    LEAF_KINDS,
    RESERVED_EVENTS,
    ROOT_KINDS,
    AssistantMessage,
    Co2,
    LeafResult,
    RunHandle,
    StoredMessage,
)
from wavelocalai.store.db import Store, utc_now_iso

logger = logging.getLogger("wavelocalai.runs")

BATCH_INTERVAL_S = 1.0  # AD-7 : un lot au plus chaque seconde
TOKEN_WINDOW_S = 0.05  # AD-6 : les `token` sont groupés par tranches de 50 ms au plus
CLOSE_WAIT_S = 5.0  # attente de la clôture d'une feuille annulée avant d'y écrire sa mesure

# `runs.params` ne contient aucun texte saisi (AD-7) : clés qui en portent d'ordinaire, et taille
# au-delà de laquelle une valeur texte est tenue pour du texte saisi.
FORBIDDEN_PARAM_KEYS = frozenset(
    {"prompt", "message", "question", "text", "content", "topic", "query", "input"}
)
MAX_PARAM_TEXT = 256


def check_params(params: Mapping[str, Any], typed_text: str | None = None) -> None:
    """Refuse des `params` qui porteraient du texte saisi (`ValueError`)."""

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if str(key).lower() in FORBIDDEN_PARAM_KEYS:
                    raise ValueError(f"params.{path}{key} : le texte saisi n'a pas sa place ici")
                visit(item, f"{path}{key}.")
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item, path)
        elif isinstance(value, str) and (
            len(value) > MAX_PARAM_TEXT or (typed_text and typed_text in value)
        ):
            raise ValueError(f"params.{path[:-1]} : texte saisi probable (AD-7)")

    visit(params, "")


def strip_source_text(value: Any) -> Any:
    """Retire `text` des sources avant écriture (AD-7) ; accepte un objet, une liste ou un objet
    qui porte la liste (`sources`, `items`)."""
    if isinstance(value, list):
        return [strip_source_text(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_source_text(item) for key, item in value.items() if key != "text"}
    return value


class _Event:
    __slots__ = ("data", "data_json", "seq", "ts", "type")

    def __init__(self, seq: int, etype: str, ts: str, data: dict[str, Any]) -> None:
        self.seq = seq
        self.type = etype
        self.ts = ts
        self.data = data  # complet, pour le flux en direct
        stored = strip_source_text(data) if etype == "sources" else data
        self.data_json = repo.dumps(stored)  # sérialisé tout de suite : une erreur remonte ici

    def envelope(self, run_id: str) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "run_id": run_id,
            "type": self.type,
            "ts": self.ts,
            "data": self.data,
        }

    def row(self) -> tuple[int, str, str, str]:
        return (self.seq, self.type, self.ts, self.data_json)


class _Run:
    def __init__(
        self,
        run_id: str,
        kind: str,
        parent_id: str | None,
        conversation_id: str | None,
        models: Sequence[str] = (),
        app_session: str | None = None,
    ):
        self.id = run_id
        self.app_session = app_session  # la session où le run a commencé (AD-10)
        self.models = tuple(models)
        self.kind = kind
        self.parent_id = parent_id
        self.conversation_id = conversation_id
        self.events: list[_Event] = []
        self.flushed = 0  # nombre d'événements déjà écrits
        self.children: list[str] = []
        self.status = "running"
        self.closing = False
        self.task: asyncio.Task[Any] | None = None
        self.on_cancel: Callable[[], None] | None = None
        self.answer: list[str] = []
        self.thought: list[str] = []
        self.leaf_co2: Co2 | None = None  # `co2` d'une feuille close sans le sien (annulation)
        # Demandes de validation en attente (AD-9) : `approval_id` -> résultat à attendre.
        self.approvals: dict[str, asyncio.Future[str]] = {}
        self.lock = asyncio.Lock()
        self.closed = asyncio.Event()  # levé quand la clôture est écrite (`amend_cancelled_leaf`)
        # Abonnement (AD-6) : un flux ouvert attend `signal` ; chaque événement le déclenche et le
        # remplace. Jetons en attente de groupage : (lane, channel) -> textes.
        self.signal = asyncio.Event()
        self.pending_tokens: dict[tuple[str, str], list[str]] = {}
        self.token_timer: asyncio.TimerHandle | None = None


class RunHub:
    """Hub d'exécutions ; une instance par serveur."""

    def __init__(
        self,
        store: Store,
        *,
        batch_interval_s: float = BATCH_INTERVAL_S,
        token_window_s: float = TOKEN_WINDOW_S,
        clock: Callable[[], str] = utc_now_iso,
    ) -> None:
        self.store = store
        self.batch_interval_s = batch_interval_s
        self.token_window_s = token_window_s
        self._clock = clock
        self._runs: dict[str, _Run] = {}
        self._closed: set[str] = set()
        self._reserved: dict[str, str] = {}  # kind -> run racine en cours de création
        self._flusher: asyncio.Task[None] | None = None
        self.app_session_id: str | None = None

    # --- cycle de vie du serveur ---------------------------------------------------------------

    async def start(self) -> list[str]:
        """Au démarrage : les runs non terminés deviennent `interrupted` (avec un `run_ended`
        synthétique), puis une nouvelle `app_session` s'ouvre. Rend les runs interrompus."""
        now = self._clock()
        interrupted = await self.store.awrite(lambda conn: repo.interrupt_orphans(conn, now))
        if interrupted:
            logger.warning("%d run(s) interrompu(s) par l'arrêt précédent", len(interrupted))
        await self.new_app_session("startup")
        self._flusher = asyncio.create_task(self._flush_loop(), name="wavelocalai-run-flusher")
        return interrupted

    async def stop(self) -> None:
        """À l'arrêt propre : les runs actifs passent à `cancelled` (AD-23)."""
        if self._flusher is not None:
            self._flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flusher
            self._flusher = None
        for run in [r for r in self._runs.values() if r.parent_id is None]:
            if run.closing:  # sa clôture est en cours : annuler sa tâche la perdrait
                continue
            self._cancel_tasks(run)
            try:
                await self._close(run, "cancelled")
            except Exception:
                logger.exception("Arrêt : le run %s n'a pas pu être clos", run.id)

    async def new_app_session(self, reason: str = "reset") -> str:
        """Ouvre une `app_session` (démarrage ou remise à zéro du CO2, AD-10)."""
        session_id = uuid.uuid4().hex
        now = self._clock()
        await self.store.awrite(lambda conn: repo.insert_session(conn, session_id, now, reason))
        self.app_session_id = session_id
        return session_id

    # --- création ------------------------------------------------------------------------------

    async def create_run(
        self,
        kind: str,
        *,
        models: Sequence[str] = (),
        params: Mapping[str, Any] | None = None,
        parent_run_id: str | None = None,
        user_message: str | None = None,
        conversation_id: str | None = None,
    ) -> RunHandle:
        """Crée un run. Un run racine publie `run_started` (seq 1). Avec `user_message`, le hub
        crée la conversation (ou reprend `conversation_id`) et écrit le message utilisateur, dans
        la même transaction. Un run enfant (`parent_run_id`) est une feuille du parent actif."""
        if self.app_session_id is None:
            raise RuntimeError("Le hub n'est pas démarré.")
        params = dict(params or {})
        check_params(params, user_message)
        parent = self._runs.get(parent_run_id) if parent_run_id else None
        if parent_run_id is not None:
            if parent is None or parent.closing or parent.parent_id is not None:
                raise ValueError("Le parent d'une feuille doit être un run racine actif.")
            if kind not in LEAF_KINDS or user_message is not None or conversation_id:
                raise ValueError("Un run enfant est une feuille (generation, judge, embedding).")
        elif kind not in ROOT_KINDS:
            raise ValueError(f"Un run racine a un genre parmi {ROOT_KINDS}, pas {kind!r}.")
        else:
            busy = self.active_root(kind)  # AD-14 : un run racine actif par genre
            if busy is not None:
                raise AppError("run_busy", f"Un run {kind} est déjà actif.", run_id=busy)
        if (user_message is not None or conversation_id) and kind not in CONVERSATION_KINDS:
            raise ValueError(f"Un run {kind} n'ouvre pas de conversation.")
        if conversation_id and user_message is None:
            raise ValueError("Reprendre une conversation exige un message utilisateur.")

        run_id = uuid.uuid4().hex
        new_conversation = user_message is not None and not conversation_id
        conv_id = (uuid.uuid4().hex if new_conversation else conversation_id) or (
            parent.conversation_id if parent else None
        )
        now = self._clock()
        started = (
            None
            if parent
            else _Event(
                1,
                "run_started",
                now,
                {"kind": kind, "models": list(models), "params": params},
            )
        )
        # Une feuille reste dans la session de son parent : une remise à zéro pendant un run actif
        # n'envoie pas ses réponses suivantes dans la nouvelle session (le run reste compté là où il
        # a commencé).
        session = (parent.app_session if parent is not None else None) or self.app_session_id

        def tx(conn: sqlite3.Connection) -> None:
            if new_conversation:
                repo.insert_conversation(conn, str(conv_id), kind, now)
            elif conversation_id:
                found = repo.conversation_kind(conn, conversation_id)
                if found is None:
                    raise AppError("not_found", "Conversation introuvable.")
                if found != kind:
                    raise AppError(
                        "invalid_request", f"La conversation est de genre {found}, pas {kind}."
                    )
            repo.insert_run(
                conn,
                run_id=run_id,
                kind=kind,
                parent_run_id=parent_run_id,
                app_session=session,
                conversation_id=conv_id,
                model=models[0] if len(models) == 1 else None,
                started_at=now,
                params=params,
            )
            if started is not None:
                repo.insert_events(conn, run_id, [started.row()])
            if user_message is not None:  # après le run, que le message référence
                repo.insert_message(conn, str(conv_id), run_id, "user", now, user_message)

        run = _Run(run_id, kind, parent_run_id, conv_id, models, session)
        if parent is None:
            # Racine réservée pendant l'écriture : pas de course entre deux POST du même genre.
            self._reserved[kind] = run_id
        else:
            # Une feuille est rattachée à son parent avant son écriture : un parent clos pendant
            # celle-ci l'annule (`cancel_rows` passe après l'insertion dans la file de l'écrivain).
            self._runs[run_id] = run
            parent.children.append(run_id)
        try:
            await self.store.awrite(tx)
        except Exception:
            if parent is not None:
                self._runs.pop(run_id, None)
                with contextlib.suppress(ValueError):
                    parent.children.remove(run_id)
            raise
        else:
            if started is not None:
                run.events.append(started)
                run.flushed = 1
                self._runs[run_id] = run
        finally:
            if parent is None and self._reserved.get(kind) == run_id:
                del self._reserved[kind]
        return RunHandle(run_id, conv_id)

    # --- publication ---------------------------------------------------------------------------

    def attach_task(self, run_id: str, task: asyncio.Task[Any]) -> None:
        """Associe la tâche asyncio d'un run, que `cancel` interrompra (AD-8). Si le run a déjà
        été clos (parent annulé pendant la création de la feuille), la tâche est annulée."""
        run = self._runs.get(run_id)
        if run is None and run_id in self._closed:
            task.cancel()
            return
        if run is None:
            raise KeyError(f"Run inconnu : {run_id}")
        run.task = task

    def set_cancel_hook(self, run_id: str, hook: Callable[[], None]) -> None:
        """Fonction synchrone que le hub appelle une fois, juste avant de clore le run racine en
        `cancelled` (annulation ou arrêt du serveur) : elle peut encore publier. Une Arène y publie
        le `lane_status: cancelled` des lanes inachevées, que `run_ended` clôt ensuite."""
        run = self._runs.get(run_id)
        if run is None:
            if run_id in self._closed:
                return
            raise KeyError(f"Run inconnu : {run_id}")
        run.on_cancel = hook

    def declare_leaf(self, run_id: str, co2: Co2) -> None:
        """Le run porte une génération (feuille, ou racine sans enfant comme un chat) : s'il est
        clos sans `co2` (annulation, arrêt du serveur), il reçoit celui-ci, `unmeasurable` avec sa
        raison, plutôt que rien (AD-10). Sans effet sur un run inconnu ou déjà en clôture."""
        run = self._runs.get(run_id)
        if run is not None and not run.closing:
            run.leaf_co2 = co2

    def publish(
        self, run_id: str, event_type: str, data: Mapping[str, Any] | None = None
    ) -> int | None:
        """Publie un événement sur un run racine actif ; rend son `seq`. Rend `None` si le run est
        déjà en cours de clôture (course avec une annulation : l'événement est écarté)."""
        if event_type in RESERVED_EVENTS:
            raise ValueError(f"{event_type} est publié par le hub seul")
        run = self._runs.get(run_id)
        if run is None:
            if run_id in self._closed:
                return None
            raise KeyError(f"Run inconnu : {run_id}")
        if run.parent_id is not None:
            raise ValueError("Seul un run racine publie un flux : le parent publie (AD-5).")
        if run.closing:
            return None
        self._drain_tokens(run)  # l'ordre des événements est celui des appels
        return self._append(run, event_type, dict(data or {}))

    def publish_token(self, run_id: str, lane: str, text: str, channel: str = "answer") -> None:
        """Publie du texte généré : les morceaux d'une même `lane` et d'un même canal reçus dans
        une tranche de `token_window_s` (50 ms) partent en un seul événement `token` (AD-6).
        Ne rend pas de `seq` : l'événement naît à la fin de la tranche, ou avant le prochain
        événement du run, ou à sa clôture."""
        if not lane:
            raise ValueError("Un token porte toujours sa lane (AD-6).")
        run = self._runs.get(run_id)
        if run is None:
            if run_id in self._closed:
                return
            raise KeyError(f"Run inconnu : {run_id}")
        if run.parent_id is not None:
            raise ValueError("Seul un run racine publie un flux : le parent publie (AD-5).")
        if run.closing or not text:
            return
        run.pending_tokens.setdefault((lane, channel), []).append(text)
        if run.token_timer is None:
            run.token_timer = asyncio.get_running_loop().call_later(
                self.token_window_s, self._drain_tokens, run
            )

    def _drain_tokens(self, run: _Run) -> None:
        """Transforme les jetons en attente en événements `token` (un par lane et canal)."""
        if run.token_timer is not None:
            run.token_timer.cancel()
            run.token_timer = None
        pending, run.pending_tokens = run.pending_tokens, {}
        if run.closing:
            return
        for (lane, channel), texts in pending.items():
            self._append(run, "token", {"lane": lane, "text": "".join(texts), "channel": channel})

    def _append(self, run: _Run, event_type: str, data: dict[str, Any]) -> int:
        event = _Event(len(run.events) + 1, event_type, self._clock(), data)
        run.events.append(event)
        self._wake(run)
        if event_type == "token" and run.conversation_id is not None:
            text = str(data.get("text") or "")
            (run.thought if data.get("channel") == "thought" else run.answer).append(text)
        elif event_type == "retry":
            # Génération relancée : le texte partiel de la tentative coupée n'est plus la réponse.
            run.answer.clear()
            run.thought.clear()
        return event.seq

    @staticmethod
    def _wake(run: _Run) -> None:
        woken, run.signal = run.signal, asyncio.Event()
        woken.set()

    # --- validation d'une action sensible (AD-9, story 6.3) ------------------------------------

    async def request_approval(
        self,
        run_id: str,
        kind: str,
        details: Mapping[str, Any],
        *,
        expiry_s: float,
        call_id: str | None = None,
    ) -> str:
        """Demande la validation de l'utilisateur et l'attend : publie `approval_required
        {approval_id, kind, **details, call_id, expiry_s}` (les textes de `details` sont déjà
        masqués par l'appelant), passe le run en `awaiting_approval` (il garde son `kind`), puis
        rend `approved`, `rejected` ou `expired` (sans réponse en `expiry_s`). Seul `approved`
        autorise l'action ; `approval_resolved` est publié avant le retour. Annuler ou clore le run
        pendant l'attente vaut `rejected` (publié par `_close`) et la tâche reçoit `CancelledError`.
        Un run déjà en clôture rend `rejected` sans rien publier."""
        run = self._runs.get(run_id)
        if run is None:
            if run_id in self._closed:
                return "rejected"
            raise KeyError(f"Run inconnu : {run_id}")
        if run.parent_id is not None:
            raise ValueError("Seul un run racine demande une validation : le parent publie (AD-5).")
        if run.closing:
            return "rejected"
        approval_id = uuid.uuid4().hex
        waiter: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        run.approvals[approval_id] = waiter
        data = {"approval_id": approval_id, "kind": kind, **details, "call_id": call_id}
        self.publish(run_id, "approval_required", {**data, "expiry_s": expiry_s})
        try:
            await self._transition(run, "awaiting_approval", "running")
            try:
                async with asyncio.timeout(expiry_s):
                    return await waiter
            except TimeoutError:
                if waiter.done() and not waiter.cancelled():  # réponse arrivée avec le délai
                    return waiter.result()
                self._resolve(run, approval_id, "expired")
                await self._leave_approval(run)
                return "expired"
        finally:
            run.approvals.pop(approval_id, None)

    async def resolve_approval(self, run_id: str, approval_id: str, decision: str) -> bool:
        """Réponse de l'utilisateur (`approved` ou `rejected`) à une demande en attente : publie
        `approval_resolved` et réveille l'action. Rend `False` si la demande n'est plus en attente
        (déjà traitée, expirée, run clos) : jamais deux décisions pour une demande."""
        if decision not in ("approved", "rejected"):
            raise ValueError(f"décision inconnue : {decision!r}")
        run = self._runs.get(run_id)
        waiter = None if run is None else run.approvals.get(approval_id)
        if run is None or run.closing or waiter is None or waiter.done():
            # `done()` : l'attente vient d'être interrompue (délai atteint, tâche annulée) sans
            # avoir encore repris ; publier `approved` mentirait, car rien ne sera exécuté.
            return False
        self._resolve(run, approval_id, decision)
        await self._leave_approval(run)
        return True

    def _resolve(self, run: _Run, approval_id: str, decision: str) -> None:
        """Retire la demande, publie `approval_resolved` (même sur un run en clôture : `_close` le
        fait avant `run_ended`) et réveille l'attente."""
        waiter = run.approvals.pop(approval_id, None)
        if waiter is None:
            return
        self._drain_tokens(run)
        self._append(run, "approval_resolved", {"approval_id": approval_id, "decision": decision})
        if not waiter.done():  # annulé avec sa tâche (annulation du run) : la décision est publiée
            waiter.set_result(decision)

    async def _leave_approval(self, run: _Run) -> None:
        """Plus aucune demande en attente : le run repasse à `running`."""
        if not run.approvals:
            await self._transition(run, "running", "awaiting_approval")

    async def _transition(self, run: _Run, new: str, expected: str) -> None:
        """Transition de statut d'un run actif (`running` <-> `awaiting_approval`), en mémoire et en
        base ; sans effet si le run est déjà en clôture."""
        if run.closing:
            return
        run.status = new
        await self.store.awrite(lambda conn: repo.transition_status(conn, run.id, new, expected))

    # --- fin d'un run --------------------------------------------------------------------------

    async def finish_leaf(self, run_id: str, result: LeafResult, co2: Co2 | None = None) -> bool:
        """Termine une feuille : statut, métriques et `co2`. Une feuille qui est aussi un run
        racine (sans enfants) est close avec son flux : dernier lot, `run_ended`, statut et message
        assistant dans une transaction. Rend `False` si le run était déjà clos (annulation)."""
        run = self._runs.get(run_id)
        if run is None:
            if run_id in self._closed:
                return False
            raise KeyError(f"Run inconnu : {run_id}")
        if run.closing:
            return False
        if run.children:
            raise ValueError("Un run composite ne porte ni métriques ni CO2 : finish_run (AD-5).")
        if run.parent_id is None:
            return await self._close(
                run,
                result.status,
                error=result.error,
                leaf=result,
                co2=co2,
                assistant=result.assistant,
            )
        run.closing = True
        now = self._clock()
        await self.store.awrite(
            lambda conn: repo.finish_run_row(
                conn, run_id, result.status, now, result.error, result, co2
            )
        )
        self._forget(run, result.status)
        return True

    async def finish_run(
        self,
        run_id: str,
        status: str = "ok",
        *,
        error: dict[str, Any] | None = None,
        assistant: AssistantMessage | None = None,
    ) -> bool:
        """Termine un run racine, composite ou non, sans métriques (elles sont sur les feuilles).
        Les enfants encore actifs passent à `cancelled`."""
        if status not in FINAL_STATUSES:
            raise ValueError(f"statut de fin inconnu : {status!r}")
        run = self._runs.get(run_id)
        if run is None:
            if run_id in self._closed:
                return False
            raise KeyError(f"Run inconnu : {run_id}")
        if run.parent_id is not None:
            raise ValueError("finish_run termine un run racine ; une feuille : finish_leaf.")
        return await self._close(run, status, error=error, assistant=assistant)

    async def cancel(self, run_id: str) -> bool:
        """Annule un run actif et ses enfants ; rend `False` s'il n'est pas actif."""
        run = self._runs.get(run_id)
        if run is None or run.closing:
            return False
        self._cancel_tasks(run)
        if run.parent_id is None:
            return await self._close(run, "cancelled")
        run.closing = True
        now = self._clock()
        leaf_co2 = run.leaf_co2

        def tx(conn: sqlite3.Connection) -> None:
            repo.cancel_rows(conn, [run_id], now)
            if leaf_co2 is not None:
                repo.fill_cancelled_co2(conn, [(run_id, leaf_co2)])

        await self.store.awrite(tx)
        self._forget(run, "cancelled")
        return True

    async def amend_cancelled_leaf(
        self, run_id: str, co2: Co2, energy_wh: float | None = None
    ) -> bool:
        """Écrit la mesure d'une feuille annulée. Le hub clôt une annulation avant que la tâche du
        service reprenne la main (elle ne peut donc pas appeler `finish_leaf`) : le `co2` de
        remplacement de `declare_leaf` est alors remplacé par ce qui a été mesuré jusqu'à
        l'arrêt (AD-10, l'énergie dépensée compte). Rend `False` si la feuille n'est pas annulée
        ou a déjà une valeur. Si la clôture est en cours d'écriture, l'attend (au plus quelques
        secondes) : la tâche annulée peut reprendre la main avant elle."""
        run = self._runs.get(run_id)
        if run is not None:
            if not run.closing:
                return False  # encore active : `finish_leaf` écrira le `co2`
            try:
                await asyncio.wait_for(run.closed.wait(), CLOSE_WAIT_S)
            except TimeoutError:
                return False
        elif run_id not in self._closed:
            return False
        return await self.store.awrite(
            lambda conn: repo.amend_cancelled_co2(conn, run_id, co2, energy_wh)
        )

    def _cancel_tasks(self, run: _Run) -> None:
        current = asyncio.current_task()
        for item in [run, *(self._runs[c] for c in run.children if c in self._runs)]:
            if item.task is not None and item.task is not current and not item.task.done():
                item.task.cancel()

    async def _close(
        self,
        run: _Run,
        status: str,
        *,
        error: dict[str, Any] | None = None,
        leaf: LeafResult | None = None,
        co2: Co2 | None = None,
        assistant: AssistantMessage | None = None,
    ) -> bool:
        if run.closing:
            return False
        if status == "cancelled" and run.on_cancel is not None:
            hook, run.on_cancel = run.on_cancel, None
            try:
                hook()
            except Exception:  # noqa: BLE001 - une annulation ne s'arrête jamais sur un crochet
                logger.exception("Le crochet d'annulation du run %s a échoué", run.id)
        for approval_id in list(run.approvals):  # clore ou annuler le run vaut refus (AD-9)
            self._resolve(run, approval_id, "rejected")
        if co2 is None and not run.children:
            co2 = run.leaf_co2  # feuille close sans mesure (annulation) : `co2` présent (AD-10)
        self._drain_tokens(run)  # le texte reçu jusque-là entre dans le flux et le partiel
        run.closing = True  # plus aucun événement n'entre
        children = [self._runs[c] for c in run.children if c in self._runs]
        for child in children:
            child.closing = True
            self._cancel_tasks(child)
        now = self._clock()
        run.events.append(
            _Event(len(run.events) + 1, "run_ended", now, {"status": status, "error": error})
        )
        self._wake(run)
        message = self._final_message(run, assistant)
        child_ids = [child.id for child in children]
        child_co2 = [(c.id, c.leaf_co2) for c in children if c.leaf_co2 is not None]
        async with run.lock:  # attend un lot en cours : pas d'écriture en double
            batch = [event.row() for event in run.events[run.flushed :]]

            def tx(conn: sqlite3.Connection) -> None:
                repo.insert_events(conn, run.id, batch)
                repo.finish_run_row(conn, run.id, status, now, error, leaf, co2)
                repo.cancel_rows(conn, child_ids, now)
                repo.fill_cancelled_co2(conn, child_co2)
                if message is not None and run.conversation_id is not None:
                    repo.insert_message(
                        conn, run.conversation_id, run.id, "assistant", now, message
                    )

            try:
                await self.store.awrite(tx)
            except Exception:
                logger.exception("Le run %s n'a pas pu être clos en base", run.id)
                run.closed.set()  # `amend_cancelled_leaf` n'attend pas une clôture qui n'aura pas lieu
                raise
        for child in children:
            self._forget(child, "cancelled")
        self._forget(run, status)
        return True

    @staticmethod
    def _final_message(run: _Run, explicit: AssistantMessage | None) -> AssistantMessage | None:
        """Message assistant écrit avec le statut final : celui du service, sinon le texte reçu
        jusque-là (partiel compris) ; rien si le run n'ouvre pas de conversation."""
        if run.conversation_id is None:
            return None
        message = explicit or AssistantMessage(
            content="".join(run.answer), reasoning="".join(run.thought) or None
        )
        return None if message.is_empty() else message

    def _forget(self, run: _Run, status: str) -> None:
        run.status = status
        if run.token_timer is not None:
            run.token_timer.cancel()
            run.token_timer = None
        self._wake(run)  # un flux ouvert relit alors la base, qui a tout
        run.events = []
        run.flushed = 0
        self._runs.pop(run.id, None)
        self._closed.add(run.id)
        run.closed.set()

    # --- lots d'événements ---------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.batch_interval_s)
            await self.flush()

    async def flush(self) -> None:
        """Écrit en base les événements publiés depuis le dernier lot (un lot par run actif)."""
        for run in [r for r in self._runs.values() if r.parent_id is None]:
            if run.closing or len(run.events) <= run.flushed:
                continue
            async with run.lock:
                batch = run.events[run.flushed :]
                if run.closing or not batch:
                    continue
                rows = [event.row() for event in batch]
                future = asyncio.wrap_future(
                    self.store.write(
                        lambda conn, rows=rows, rid=run.id: repo.insert_events(conn, rid, rows)
                    )
                )
                try:
                    await asyncio.shield(future)
                except asyncio.CancelledError:
                    # `stop()` annule le flusher : le lot peut déjà être parti dans le fil de
                    # l'écrivain. Son sort est attendu sous le verrou, sinon `_close` réécrirait
                    # les mêmes `seq` (UNIQUE) et la clôture échouerait.
                    while not future.done():
                        with contextlib.suppress(asyncio.CancelledError):
                            await asyncio.wait([future])
                    if not future.cancelled() and future.exception() is None:
                        run.flushed += len(batch)
                    raise
                except Exception:
                    logger.exception(
                        "Lot d'événements du run %s non écrit, nouvel essai plus tard", run.id
                    )
                    continue
                run.flushed += len(batch)

    # --- lecture -------------------------------------------------------------------------------

    def active_runs(self) -> list[dict[str, str]]:
        """Runs racines actifs, pour `runs_active` du flux système."""
        return [
            {"run_id": r.id, "kind": r.kind, "status": r.status}
            for r in self._runs.values()
            if r.parent_id is None and not r.closing
        ]

    def active_models(self) -> dict[str, str]:
        """Modèles qu'un run actif (racine ou feuille) emploie : tag -> `run_id` du run racine.
        Sert à ne décharger que les modèles inactifs (story 4.8)."""
        used: dict[str, str] = {}
        for run in self._runs.values():
            if run.closing:
                continue
            root = run.id if run.parent_id is None else run.parent_id
            for tag in run.models:
                used.setdefault(tag, root)
        return used

    def active_root(self, kind: str) -> str | None:
        """`run_id` du run racine actif (ou en création) de ce genre, sinon `None` (AD-14)."""
        for run in self._runs.values():
            if run.parent_id is None and run.kind == kind and not run.closing:
                return run.id
        return self._reserved.get(kind)

    async def conversation_messages(self, conversation_id: str) -> list[StoredMessage]:
        """Messages d'une conversation dans l'ordre d'écriture (le dernier message utilisateur
        d'un run en cours compris), pour construire la requête du modèle."""
        rows = await self.store.aread(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY rowid",
            (conversation_id,),
        )
        return [StoredMessage(r["role"], r["content"]) for r in rows]

    async def erase_conversation(self, conversation_id: str) -> None:
        """Efface une conversation et le texte de ses runs (AD-13) ; `conversation_busy` si l'un
        d'eux est actif. L'effacement et le vidage du fichier et du journal (`wal_checkpoint`,
        `VACUUM`) passent dans la file de l'écrivain, l'un derrière l'autre."""
        await self.store.awrite(
            lambda conn: repo.erase_conversation(conn, conversation_id), purge=True
        )

    async def erase_arena(self, run_id: str) -> None:
        """Efface une Arène terminée et le texte de ses runs (AD-13) : `run_not_found` si ce n'est
        pas une Arène, `arena_busy` si elle est active. Même passage par la file de l'écrivain, avec
        la purge du fichier et du journal, que l'effacement d'une conversation."""
        await self.store.awrite(lambda conn: repo.erase_arena(conn, run_id), purge=True)

    async def erase_eval(self, run_id: str) -> None:
        """Efface une évaluation terminée, ses notes et le texte de ses runs (AD-13) :
        `run_not_found` si ce n'est pas une évaluation, `run_busy` si elle est active. Même passage
        par la file de l'écrivain, avec la purge du fichier et du journal, que l'Arène."""
        await self.store.awrite(lambda conn: repo.erase_eval(conn, run_id), purge=True)

    def watch(self, run_id: str) -> asyncio.Event | None:
        """Événement qui se déclenche au prochain événement (ou à la clôture) d'un run racine
        actif ; `None` si le run n'est plus actif. À prendre *avant* `events_after`."""
        run = self._runs.get(run_id)
        return None if run is None or run.parent_id is not None else run.signal

    def answer_text(self, run_id: str) -> str | None:
        """Texte de réponse reçu jusque-là par un run racine actif d'une conversation (les jetons en
        attente y sont versés d'abord) ; `None` si le run n'est plus actif. Un service s'en sert pour
        vérifier la réponse une fois le flux fini (`citations`, story 4.6)."""
        run = self._runs.get(run_id)
        if run is None or run.parent_id is not None:
            return None
        self._drain_tokens(run)
        return "".join(run.answer)

    async def events_after(self, run_id: str, after: int = 0) -> list[dict[str, Any]]:
        """Enveloppes d'AD-6 de `seq > after` : mémoire du hub si le run est actif, base sinon.
        Depuis la base, le texte des `sources` est réhydraté depuis `chunks` (AD-7) : `null` si
        l'extrait n'existe plus (document supprimé)."""
        run = self._runs.get(run_id)
        if run is not None:
            return [e.envelope(run_id) for e in run.events if e.seq > after]
        rows = await self.store.aread(
            "SELECT seq, type, ts, data FROM run_events WHERE run_id = ? AND seq > ? ORDER BY seq",
            (run_id, after),
        )
        envelopes = [
            {
                "seq": r["seq"],
                "run_id": run_id,
                "type": r["type"],
                "ts": r["ts"],
                "data": json.loads(r["data"]),
            }
            for r in rows
        ]
        await self._rehydrate_sources(envelopes)
        return envelopes

    async def _rehydrate_sources(self, envelopes: list[dict[str, Any]]) -> None:
        """Remet le `text` des sources persistées sans lui (AD-7), d'après `chunk_id` ; `None` si
        l'extrait a été supprimé. Les positions de `passage` restent telles qu'écrites : le front
        les ignore quand `text` est nul."""
        sources = [
            source
            for envelope in envelopes
            if envelope["type"] == "sources"
            for source in envelope["data"].get("sources", [])
        ]
        ids = sorted({int(s["chunk_id"]) for s in sources if s.get("chunk_id") is not None})
        texts: dict[int, str] = {}
        for start in range(0, len(ids), 500):  # limite de variables de SQLite
            part = ids[start : start + 500]
            rows = await self.store.aread(
                f"SELECT id, text FROM chunks WHERE id IN ({','.join('?' * len(part))})", part
            )
            texts.update({int(r["id"]): r["text"] for r in rows})
        for source in sources:
            chunk_id = source.get("chunk_id")
            source["text"] = None if chunk_id is None else texts.get(int(chunk_id))
