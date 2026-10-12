"""Boucle de génération (AD-7, AD-13, AD-14) : plan, essais, pannes, chauffe et déchargement.

- **Plan** (``build_plan``) : questions de chaque piste (``tracks.json``) restreintes à
  ``selection`` (résolue par ``common/selection.py``, partagé avec le rapport : ``ids``, ou
  tirage de ``per_usage`` questions par usage dans ``think_off`` ; ``think_on`` en garde
  l'intersection), triées par palier ``num_ctx`` croissant puis par ``id``.
- **Ordre** : modèle (ordre de la configuration) > piste (``think_off`` puis ``think_on``) >
  palier > question > seed (``seed_base + epoch``, ``epoch < k``). Clé
  ``"{campaign}|{model}|{track}|{question_id}|{seed}"`` ; toute clé présente est sautée.
- **Palier au-delà du maximum effectif** du modèle : ligne ``context_exceeded`` sans requête.
- **Essais (AD-13)** : ``OllamaRequestError`` compte un essai ; ``OllamaUnavailableError`` aussi
  si ``/api/version`` répond aussitôt (service vivant), sinon ``wait_for_ollama`` puis la
  question est refaite en entier sans compter l'essai, après une nouvelle chauffe. Après
  ``max_attempts`` essais comptés : ligne ``error`` (sortie et compteurs du dernier essai,
  message d'Ollama). ``max_consecutive_errors`` lignes ``error`` de suite : ``GenerationAbortedError``.
- **Chauffe** : une requête jetée chaque fois que le couple (modèle, ``num_ctx``) chargé change,
  avant la première question à requêter du palier, après toute panne du service et après un
  essai compté en ``OllamaUnavailableError`` (5xx ou coupure, service vivant) ; une ligne
  ``qb.warmup/1`` dans ``warmups.jsonl``. Échec de la chauffe, service vivant : journalisé, sans
  ligne, la génération continue.
- **Arrêt** : ``stop.should_stop()`` lu avant chaque clé (question, seed) ; le modèle en cours
  est déchargé (``keep_alive: 0``) en fin de modèle et à toute sortie, au mieux.

Le journal ne porte que des identifiants, statuts et comptes : jamais de contenu de question ni
de réponse.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from ..common.canonical import utc_now
from ..common.jsonl import JsonlAppender
from ..common.schemas import TRACKS, validate
from ..common.selection import SelectionError, selected_ids
from ..ollama.client import (
    OllamaClient,
    OllamaError,
    OllamaRequestError,
    OllamaUnavailableError,
    OllamaVersionChangedError,
    wait_for_ollama,
)
from .conversation import (
    STATUS_CONTEXT_EXCEEDED,
    ChatFailedError,
    Outcome,
    run_conversation,
)
from .preflight import LaunchError, find_tag

logger = logging.getLogger(__name__)

GENERATION_SCHEMA_ID = "qb.generation/1"
WARMUP_SCHEMA_ID = "qb.warmup/1"
STATUS_ERROR = "error"
# Invite de chauffe fixe (aucun contenu de question), longue d'environ un quart du palier.
WARMUP_SENTENCE = (
    "Le banc de qualité chauffe le modèle avant de mesurer ses réponses ; cette phrase est "
    "répétée pour remplir environ un quart du contexte. "
)
WARMUP_INSTRUCTION = "\nRéponds seulement « prêt »."
CHARS_PER_TOKEN = 3


class SetError(RuntimeError):
    """Jeu de questions incohérent (``tracks.json`` qui cite une question absente) : code 1."""


class GenerationAbortedError(RuntimeError):
    """Campagne arrêtée par trop d'erreurs de suite (AD-13) : code 1."""


class StopSignal(Protocol):
    def should_stop(self) -> bool: ...


# -- Plan -----------------------------------------------------------------------------------


def build_plan(
    generation: Mapping[str, Any],
    questions: Mapping[str, Mapping[str, Any]],
    tracks: Mapping[str, Sequence[str]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Questions de chaque piste, restreintes à ``selection`` et triées (palier, ``id``).

    ``SetError`` si ``tracks.json`` cite une question absente ; ``LaunchError`` (code 2) si la
    sélection cite une question hors du jeu, si une question a un palier hors de
    ``num_ctx_tiers``, un plafond ``num_predict`` qui atteint son ``num_ctx`` ou un tour suivant
    qui n'est pas un message ``user``."""
    for track in TRACKS:
        listed = tracks.get(track)
        if not isinstance(listed, list):
            raise SetError(f"tracks.json : piste {track} absente ou illisible")
        missing = [qid for qid in listed if qid not in questions]
        if missing:
            raise SetError(f"tracks.json : {len(missing)} question(s) absente(s) ({missing[0]})")
    try:
        selected = selected_ids(generation["selection"], questions, tracks["think_off"])
    except SelectionError as exc:
        raise LaunchError(str(exc)) from None
    tiers = set(generation["num_ctx_tiers"])
    plan: dict[str, list[Mapping[str, Any]]] = {}
    for track in TRACKS:
        ids = [qid for qid in tracks[track] if selected is None or qid in selected]
        chosen = [questions[qid] for qid in dict.fromkeys(ids)]
        for question in chosen:
            if question["num_ctx"] not in tiers:
                raise LaunchError(
                    f"question {question['id']} : palier {question['num_ctx']} absent de "
                    f"num_ctx_tiers {sorted(tiers)}"
                )
            num_predict = num_predict_for(generation, track, question["usage"])
            if num_predict >= question["num_ctx"]:
                raise LaunchError(
                    f"question {question['id']}, piste {track} : num_predict {num_predict} ≥ "
                    f"num_ctx {question['num_ctx']} (plafonds de la campagne au-delà du jeu)"
                )
            for turn in question.get("turns") or []:
                if any(message["role"] != "user" for message in turn):
                    raise LaunchError(
                        f"question {question['id']} : tour suivant avec un message autre que "
                        "« user », non injectable"
                    )
        plan[track] = sorted(chosen, key=lambda q: (q["num_ctx"], q["id"]))
    return plan


def num_predict_for(generation: Mapping[str, Any], track: str, usage: str) -> int:
    """Plafond par appel : ``caps[piste][usage]``, sinon ``caps[piste].default``."""
    caps = generation["caps"][track]
    return int(caps.get(usage, caps["default"]))


def warmup_prompt(num_ctx: int) -> str:
    """Invite fixe en français d'environ ``num_ctx / 4`` tokens (3 caractères par token)."""
    length = max(1, num_ctx // 4) * CHARS_PER_TOKEN
    repeats = length // len(WARMUP_SENTENCE) + 1
    return (WARMUP_SENTENCE * repeats)[:length] + WARMUP_INSTRUCTION


# -- Boucle ---------------------------------------------------------------------------------


class Runner:
    """Parcourt le plan et écrit une ligne ``qb.generation/1`` par clé absente."""

    def __init__(
        self,
        *,
        client: OllamaClient,
        campaign: str,
        generation: Mapping[str, Any],
        models: Sequence[Mapping[str, Any]],
        plan: Mapping[str, Sequence[Mapping[str, Any]]],
        manifest_hash: str,
        ollama_version: str,
        generations: JsonlAppender,
        warmups: JsonlAppender,
        stop: StopSignal,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.campaign = campaign
        self.generation = generation
        self.models = models
        self.plan = plan
        self.manifest_hash = manifest_hash
        self.ollama_version = ollama_version
        self.generations = generations
        self.warmups = warmups
        self.stop = stop
        self.sleep = sleep
        self.clock = clock
        self.loaded: tuple[str, int] | None = None
        self.consecutive_errors = 0
        self.statuses: Counter[str] = Counter()
        self.skipped = 0
        self.requested: set[str] = set()  # modèles qui ont reçu au moins une requête

    # -- Entrée ------------------------------------------------------------------------------

    def run(self) -> bool:
        """Parcourt tout le plan ; rend ``False`` si un arrêt propre a été demandé."""
        request = self.generation["request"]
        try:
            for model in self.models:
                tag = model["tag"]
                try:
                    for track in TRACKS:
                        if track not in model["tracks"]:
                            continue
                        for question in self.plan.get(track, ()):
                            for epoch in range(request["k"]):
                                seed = request["seed_base"] + epoch
                                key = "|".join(
                                    [self.campaign, tag, track, question["id"], str(seed)]
                                )
                                if key in self.generations:
                                    self.skipped += 1
                                    continue
                                if self.stop.should_stop():
                                    return False
                                self._process(model, track, question, epoch, seed, key)
                finally:
                    if tag in self.requested:
                        self._unload(tag)
            return True
        finally:
            logger.info(
                "Génération : %d lignes écrites (%s), %d clés déjà présentes sautées",
                sum(self.statuses.values()),
                ", ".join(f"{s} {n}" for s, n in sorted(self.statuses.items())) or "aucune",
                self.skipped,
            )

    # -- Une question ------------------------------------------------------------------------

    def _process(
        self,
        model: Mapping[str, Any],
        track: str,
        question: Mapping[str, Any],
        epoch: int,
        seed: int,
        key: str,
    ) -> None:
        """Écrit la ligne de ``key`` (une requête par essai, sauf palier hors maximum)."""
        num_ctx = question["num_ctx"]
        num_predict = num_predict_for(self.generation, track, question["usage"])
        think = model[track] if "thinking" in model["capabilities"] else None
        line = {
            "schema": GENERATION_SCHEMA_ID,
            "key": key,
            "manifest": self.manifest_hash,
            "campaign": self.campaign,
            "model": model["tag"],
            "digest": model["digest"],
            "track": track,
            "question_id": question["id"],
            "usage": question["usage"],
            "group": question["group"],
            "unit": question["unit"],
            "prompt_hash": question["prompt_hash"],
            "seed": seed,
            "epoch": epoch,
            "think": think,
            "backend": "ollama",
            "ollama_version": self.ollama_version,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
        }
        if num_ctx > model["num_ctx_max"]:
            # Palier écarté par le préflight (AD-7, AD-9) : ligne écrite sans requête.
            self._write(line, Outcome(status=STATUS_CONTEXT_EXCEEDED), attempts=0, error=None)
            return
        self.requested.add(model["tag"])
        self._ensure_warm(model, num_ctx, think)

        def chat(messages: list[dict[str, Any]], tools: Any) -> Any:
            return self.client.chat(
                model["tag"],
                messages,
                seed=seed,
                num_ctx=num_ctx,
                num_predict=num_predict,
                capabilities=model["capabilities"],
                format=question["format"],
                think=think,
                tools=tools,
            )

        attempts = 0
        while True:
            try:
                outcome = run_conversation(
                    question,
                    chat,
                    num_ctx=num_ctx,
                    num_predict=num_predict,
                    max_tool_calls_per_turn=self.generation["max_tool_calls_per_turn"],
                )
            except ChatFailedError as failure:
                cause = failure.cause
                if isinstance(cause, OllamaUnavailableError):
                    if not self._alive():
                        logger.warning("%s : Ollama ne répond plus, attente du service", key)
                        self._wait()
                        self._ensure_warm(model, num_ctx, think)
                        continue  # question refaite en entier, essai non compté
                elif not isinstance(cause, OllamaRequestError):
                    # Défaut du banc (paramètre refusé par le client) : jamais un essai.
                    raise cause from failure
                attempts += 1
                logger.warning(
                    "%s : essai %d/%d en échec, service vivant (%s)",
                    key,
                    attempts,
                    self.generation["max_attempts"],
                    type(cause).__name__,
                )
                if isinstance(cause, OllamaUnavailableError):
                    # 5xx ou coupure, service vivant : le runner du modèle a pu tomber et le
                    # décharger. Nouvelle chauffe avant la requête suivante (cet essai ou la
                    # question suivante), pour ne pas compter un rechargement à froid dans ses
                    # durées. Un refus 4xx laisse le modèle chargé : rechauffer relirait
                    # l'invite de chauffe depuis le cache de préfixe et fausserait son débit.
                    self.loaded = None
                if attempts >= self.generation["max_attempts"]:
                    self._write(line, failure.partial, attempts=attempts, error=str(cause))
                    return
                self._ensure_warm(model, num_ctx, think)
                continue
            self._write(line, outcome, attempts=attempts + 1, error=None)
            return

    def _write(
        self,
        line: dict[str, Any],
        outcome: Outcome,
        *,
        attempts: int,
        error: str | None,
    ) -> None:
        """Valide et écrit la ligne ; ``error`` non nul : statut ``error`` (sortie et compteurs
        du dernier essai, message d'Ollama)."""
        record = {
            **line,
            "status": STATUS_ERROR if error is not None else outcome.status,
            "output": outcome.output,
            "call_cap_reached": outcome.call_cap_reached,
            "tokens": dict(outcome.tokens),
            "durations_ns": dict(outcome.durations_ns),
            "wall_s": round(outcome.wall_s, 6),
            "calls": outcome.calls,
            "attempts": attempts,
            "error": error,
            "created_at": utc_now(),
        }
        validate(record)
        self.generations.append(record)
        status = record["status"]
        self.statuses[status] += 1
        logger.info(
            "%s : %s (%d appel(s), %d essai(s)%s)",
            record["key"],
            status,
            record["calls"],
            attempts,
            ", borne d'appels atteinte" if record["call_cap_reached"] else "",
        )
        if status == STATUS_ERROR:
            self.consecutive_errors += 1
            limit = self.generation["max_consecutive_errors"]
            if self.consecutive_errors >= limit:
                raise GenerationAbortedError(
                    f"{self.consecutive_errors} lignes « error » de suite (limite {limit}) : "
                    "campagne arrêtée"
                )
        elif attempts > 0:
            # Une ligne écrite sans requête (palier hors maximum) ne rompt pas la série.
            self.consecutive_errors = 0

    # -- Service -----------------------------------------------------------------------------

    def _alive(self) -> bool:
        """Sonde immédiate de ``/api/version`` : le service répond-il encore ?"""
        try:
            version = self.client.version()
        except OllamaUnavailableError:
            return False
        except OllamaRequestError:
            return True
        if version != self.ollama_version:
            raise OllamaVersionChangedError(
                f"Ollama répond en version {version}, la campagne exige {self.ollama_version}."
            )
        return True

    def _wait(self) -> None:
        """Attend le retour du service (sans redémarrage) ; le modèle sera rechauffé."""
        wait_for_ollama(
            self.client,
            self.generation["ollama_wait_s"],
            self.ollama_version,
            sleep=self.sleep,
            clock=self.clock,
        )
        self.loaded = None

    def _unload(self, tag: str) -> None:
        """Décharge ``tag`` (``keep_alive: 0``), au mieux."""
        try:
            self.client.unload(tag)
        except OllamaError as exc:
            logger.warning("%s : déchargement impossible (%s)", tag, type(exc).__name__)
        else:
            logger.info("%s : modèle déchargé", tag)
        if self.loaded is not None and self.loaded[0] == tag:
            self.loaded = None

    # -- Chauffe -----------------------------------------------------------------------------

    def _ensure_warm(self, model: Mapping[str, Any], num_ctx: int, think: Any) -> None:
        pair = (model["tag"], num_ctx)
        if self.loaded == pair:
            return
        tag = model["tag"]
        while True:
            try:
                result = self.client.chat(
                    tag,
                    [{"role": "user", "content": warmup_prompt(num_ctx)}],
                    seed=self.generation["request"]["seed_base"],
                    num_ctx=num_ctx,
                    num_predict=1,
                    capabilities=model["capabilities"],
                    format=None,
                    think=think,
                )
                break
            except OllamaUnavailableError as exc:
                if self._alive():
                    self._warmup_failed(tag, num_ctx, exc)
                    return
                logger.warning("%s : Ollama ne répond plus pendant la chauffe", tag)
                self._wait()
            except OllamaRequestError as exc:
                self._warmup_failed(tag, num_ctx, exc)
                return
        self.loaded = pair
        size = size_vram = None
        try:
            entry = find_tag(self.client.ps(), tag)
        except OllamaError as exc:
            logger.warning("%s : /api/ps illisible après la chauffe (%s)", tag, type(exc).__name__)
            entry = None
        if entry is not None:
            size = _count_or_none(entry.get("size"))
            size_vram = _count_or_none(entry.get("size_vram"))
        duration = result.durations_ns.get("prompt_eval", 0)
        prefill = (
            result.prompt_eval_count / (duration / 1e9)
            if result.prompt_eval_count > 0 and duration > 0
            else None
        )
        record = {
            "schema": WARMUP_SCHEMA_ID,
            "key": f"{self.campaign}|{tag}|{num_ctx}|{len(self.warmups)}",
            "manifest": self.manifest_hash,
            "campaign": self.campaign,
            "model": tag,
            "num_ctx": num_ctx,
            "prompt_tokens": result.prompt_eval_count,
            "size": size,
            "size_vram": size_vram,
            "prefill_tok_s": round(prefill, 3) if prefill is not None else None,
            "load_ns": int(result.durations_ns.get("load", 0)),
            "created_at": utc_now(),
        }
        validate(record)
        self.warmups.append(record)
        threshold = self.generation["min_prefill_tok_s"]
        if prefill is None:
            logger.warning("%s, num_ctx %d : débit de préremplissage inconnu", tag, num_ctx)
        elif prefill < threshold:
            logger.warning(
                "%s, num_ctx %d : préremplissage à %.1f tok/s, sous le seuil de %g tok/s "
                "(débordement en RAM partagée ?)",
                tag,
                num_ctx,
                prefill,
                threshold,
            )
        else:
            logger.info("%s, num_ctx %d : chauffe à %.1f tok/s", tag, num_ctx, prefill)

    def _warmup_failed(self, tag: str, num_ctx: int, exc: Exception) -> None:
        logger.warning(
            "%s, num_ctx %d : chauffe en échec, service vivant (%s) ; sans ligne, la génération "
            "continue",
            tag,
            num_ctx,
            type(exc).__name__,
        )
        self.loaded = (tag, num_ctx)


def _count_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
