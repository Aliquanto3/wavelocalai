"""Reclassement des extraits par un reranker local, s'il est là (story 4.7, AD-17, AD-21).

Ollama n'a pas d'API de reranking : le reranker est un modèle ONNX que fastembed charge, dépendance
de base depuis la story 9.5 (décision D-R6, 2026-10-21). **Aucun téléchargement** : le modèle n'est
chargé qu'avec `local_files_only=True`, depuis le `cache_dir` du dossier de données
(`<données>/models/fastembed`). Modèle absent du cache ou `ValueError` au chargement : la recherche se
fait sans reclassement, et `RerankerService.status()` dit pourquoi (« Reclassement indisponible :
<raison> »). `fastembed` introuvable (environnement cassé) reste un cas défensif du code, plus un
chemin attendu en usage normal. Remplir le cache est une action explicite : le bouton « Installer le
reranker » de l'écran Modèles (run `pull`, `rag/rerank_pull.py`, story 5.5), seul téléchargement du
reranker.

Copié puis adapté de `src/core/rag/models_factory.py` de la v1 (un `CrossEncoder` de
sentence-transformers, chargé hors ligne d'abord puis, en repli, depuis le Hub : la v2 n'a pas ce
repli) ; la v2 n'importe jamais `src.*`.

Imports lourds : `fastembed` n'est importé que dans `load_fastembed`, après `disable_telemetry()`
(AD-21), et le chargement comme le calcul des scores tournent dans un pool de threads.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from wavelocalai.telemetry import disable_telemetry

logger = logging.getLogger("wavelocalai.rag")

CACHE_SUBDIR = ("models", "fastembed")


def cache_dir(data_dir: Path) -> Path:
    """Le `cache_dir` du reranker dans le dossier de données."""
    return data_dir.joinpath(*CACHE_SUBDIR)


class Reranker(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        """Un score de pertinence par texte, dans l'ordre : plus grand = plus pertinent."""
        ...


Loader = Callable[[str, Path, str | Path | None], Reranker]


class RerankerUnavailableError(Exception):
    """Le reranker ne peut pas servir ; `str(exc)` est la raison, en français, sans point final."""


@dataclass(frozen=True)
class RerankerStatus:
    model: str
    available: bool
    reason: str | None  # présent quand `available` est faux


class _Fastembed:
    def __init__(self, encoder: object) -> None:
        self._encoder = encoder

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        return [float(score) for score in self._encoder.rerank(query, list(texts))]  # type: ignore[attr-defined]


def load_fastembed(model: str, cache: Path, env_file: str | Path | None = None) -> Reranker:
    """Charge le reranker depuis le cache, sans jamais le télécharger (`local_files_only=True`).

    Lève `RerankerUnavailableError` : fastembed introuvable (`ImportError`, cas défensif seulement
    depuis que c'est une dépendance de base), modèle absent du cache ou illisible (`ValueError`, que
    fastembed lève quand il ne trouve pas le modèle hors ligne)."""
    disable_telemetry(env_file)  # juste avant l'import de fastembed (AD-21)
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
    except ImportError:
        raise RerankerUnavailableError(missing_extra_reason()) from None
    try:
        encoder = TextCrossEncoder(model_name=model, cache_dir=str(cache), local_files_only=True)
    except ValueError as exc:
        raise RerankerUnavailableError(
            f"le modèle {model} n'a pas pu être chargé depuis {cache} ({_first_line(exc)})"
        ) from exc
    return _Fastembed(encoder)


def missing_extra_reason() -> str:
    """fastembed est une dépendance de base (D-R6) : n'arrive que si l'installation est cassée."""
    return "fastembed n'est pas disponible (réinstallez les dépendances : uv sync)"


def _first_line(exc: BaseException) -> str:
    return (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]


def install_marker(cache: Path, model: str) -> Path:
    """Le témoin d'une installation en cours depuis l'écran Modèles (story 5.5), à côté du dossier du
    modèle : écrit avant le téléchargement, retiré une fois le modèle vérifié. S'il reste (arrêt brutal
    du serveur pendant l'installation), le dossier est partiel : le modèle n'est pas installé."""
    return cache / f".models--{model.replace('/', '--')}.installing"


def _model_in_cache(model: str, cache: Path) -> bool:
    """Le cache a un dossier pour ce modèle (`models--<organisation>--<nom>` de Hugging Face), sans
    installation inachevée (`install_marker`). Une présence ne prouve pas que le chargement réussira :
    le chargement tranche."""
    wanted = model.replace("/", "--").lower()
    if install_marker(cache, model).exists():
        return False
    try:
        return any(
            entry.is_dir() and entry.name.lower().endswith(wanted) for entry in cache.iterdir()
        )
    except OSError:  # cache absent
        return False


class RerankerService:
    """Le reranker de l'app : état lisible sans le charger, chargement unique à la demande.

    `status()` ne charge rien (extra installé ? dossier du modèle dans le cache ? chargement déjà
    échoué ?), donc `GET /api/rag/settings` reste instantané. `score()` charge le modèle au premier
    appel, dans un thread ; un échec de chargement est retenu : les recherches suivantes passent
    sans reranker, sans réessayer, et `status()` en donne la raison."""

    def __init__(
        self,
        model: str,
        cache: Path,
        *,
        loader: Loader = load_fastembed,
        env_file: str | Path | None = None,
    ) -> None:
        self.model = model
        self.cache = cache
        self._loader = loader
        self._env_file = env_file
        self._reranker: Reranker | None = None
        self._failure: str | None = None
        self._loading: asyncio.Task[None] | None = None  # le chargement unique, partagé

    def preset(self, reranker: Reranker | None = None, reason: str | None = None) -> None:
        """Tests seulement : un reranker déjà chargé, ou une indisponibilité fixée par `reason`."""
        self._reranker = reranker
        self._failure = None if reranker is not None else (reason or "indisponible")

    @property
    def loaded(self) -> Reranker | None:
        """Le reranker chargé, s'il y en a un."""
        return self._reranker

    def status(self) -> RerankerStatus:
        if self._reranker is not None:
            return RerankerStatus(self.model, True, None)
        if self._failure is not None:
            return RerankerStatus(self.model, False, self._failure)
        if not _model_in_cache(self.model, self.cache):
            reason = f"le modèle {self.model} n'est pas dans le dossier de cache {self.cache}"
            return RerankerStatus(self.model, False, reason)
        return RerankerStatus(self.model, True, None)

    def use_loader(self, loader: Loader) -> None:
        """Tests seulement : un autre chargeur (un faux reranker au lieu de fastembed)."""
        self._loader = loader

    def refresh(self) -> None:
        """Oublie un chargement échoué ou en cours : après l'installation du modèle, l'état se relit du
        cache et la recherche suivante le charge, sans redémarrage (story 5.5)."""
        self._reranker = None
        self._failure = None
        self._loading = None

    async def _load(self) -> Reranker | None:
        """Le reranker, chargé au premier appel. Le chargement est une tâche unique, partagée et
        protégée (`asyncio.shield`) : une question annulée pendant qu'il tourne ne l'interrompt pas
        et la suivante l'attend au lieu d'en lancer un second (deux fois ~1 Go en mémoire)."""
        if self._reranker is None and self._failure is None:
            if self._loading is None:
                self._loading = asyncio.ensure_future(self._load_once())
            await asyncio.shield(self._loading)
        return self._reranker

    async def _load_once(self) -> None:
        try:
            self._reranker = await asyncio.to_thread(
                self._loader, self.model, self.cache, self._env_file
            )
        except RerankerUnavailableError as exc:
            self._failure = str(exc)
        except Exception as exc:  # noqa: BLE001 - un reranker cassé ne casse pas le RAG
            self._failure = f"chargement impossible ({_first_line(exc)})"
        if self._failure is not None:
            logger.warning("Reranker indisponible : %s", self._failure)

    async def score(self, query: str, texts: Sequence[str]) -> list[float] | None:
        """Les scores de `texts` pour `query`, ou `None` si le reranker ne peut pas servir
        (indisponible, ou calcul en échec : la recherche garde l'ordre des vecteurs)."""
        if not self.status().available:
            return None
        reranker = await self._load()
        if reranker is None:
            return None
        try:
            scores = await asyncio.to_thread(reranker.score, query, list(texts))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reclassement en échec : %r", exc)
            return None
        return scores if len(scores) == len(texts) else None


class FakeReranker:
    """Reranker factice des tests (`Settings.testing`, `POST /api/test/reranker`) : aucun modèle.

    `mode` `lexical` : le score est le nombre de mots de la question que le texte contient ;
    `reverse` : l'ordre des vecteurs est renversé (le dernier candidat passe premier). `delay_s`
    fait durer le calcul, pour qu'un test lise l'étape « Reclassement… »."""

    def __init__(self, mode: str = "lexical", delay_s: float = 0.0) -> None:
        self.mode = mode
        self.delay_s = delay_s
        self.calls: list[tuple[str, int]] = []  # (question, nombre de textes) de chaque calcul

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        self.calls.append((query, len(texts)))
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.mode == "reverse":
            return [float(index) for index in range(len(texts))]
        words = {word for word in query.lower().split() if len(word) > 2}
        return [float(sum(word in text.lower() for word in words)) for text in texts]
