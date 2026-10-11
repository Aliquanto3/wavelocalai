"""Client de l'API native d'Ollama (AD-9, AD-13) : seul constructeur de requêtes du banc.

- Transport ``httpx2`` synchrone, ``POST /api/chat`` en streaming ; jamais ``/v1`` ni la
  bibliothèque ``ollama``. URL de base limitée à ``localhost`` ou ``127.0.0.1``, sans proxy.
- Chaque requête de chat fixe ``options.seed``, ``options.temperature = 0``,
  ``options.num_ctx``, ``options.num_predict`` et ``format`` (schéma, ``"json"`` ou ``null``
  explicite). ``think`` et ``tools`` ne partent que si la capacité est déclarée.
- Panne du service (connexion refusée, coupure avant ``done``, statut 5xx) :
  ``OllamaUnavailableError``. Erreur propre à la requête (4xx, erreur dans le flux) :
  ``OllamaRequestError``. Aucune des deux n'est un statut ``error`` en soi : c'est au runner
  d'en décider (AD-13).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any
from urllib.parse import urlsplit

import httpx2

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
VERSION_TIMEOUT_S = 10.0


class OllamaError(Exception):
    """Erreur du client Ollama."""


class OllamaUnavailableError(OllamaError):
    """Le service ne répond pas (connexion refusée, coupure avant ``done``, 5xx)."""


class OllamaRequestError(OllamaError):
    """Requête refusée ou échouée, service vivant (4xx, erreur ou flux illisible)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class OllamaGoneError(OllamaError):
    """Le service est resté absent pendant toute l'attente (``ollama_wait_s``)."""


class OllamaVersionChangedError(OllamaError):
    """Le service est revenu dans une autre version : la campagne s'arrête (AD-8)."""


@dataclass
class ChatResult:
    """Réponse agrégée d'un appel ``/api/chat`` en streaming."""

    content: str = ""
    thinking: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Fragments du flux comptés par champ : estimations des tokens (issue Ollama #17843).
    chunks: dict[str, int] = field(
        default_factory=lambda: {"content": 0, "thinking": 0, "tool_calls": 0}
    )
    done_reason: str | None = None
    prompt_eval_count: int = 0
    prompt_eval_cached_count: int = 0
    eval_count: int = 0
    durations_ns: dict[str, int] = field(
        default_factory=lambda: {"total": 0, "load": 0, "prompt_eval": 0, "eval": 0}
    )
    wall_s: float = 0.0


def check_local_base_url(base_url: str) -> str:
    """Rend l'URL normalisée, ou lève ``ValueError`` si elle quitte la machine."""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"URL d'Ollama invalide (schéma http attendu) : {base_url!r}")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(f"URL d'Ollama invalide (ni identifiants ni paramètres) : {base_url!r}")
    if parts.path not in ("", "/"):
        raise ValueError(f"URL d'Ollama invalide (racine du service attendue) : {base_url!r}")
    try:
        parts.port  # noqa: B018 (valide le port)
    except ValueError as exc:
        raise ValueError(f"URL d'Ollama invalide (port) : {base_url!r}") from exc
    if parts.hostname not in LOCAL_HOSTS:
        raise ValueError(
            f"URL d'Ollama refusée : {base_url!r} (seuls localhost et 127.0.0.1 sont permis)"
        )
    return f"{parts.scheme}://{parts.netloc}"


def _int_field(obj: Mapping[str, Any], name: str) -> int:
    value = obj.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _error_message(response: httpx2.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        return payload["error"]
    return str(payload)[:500]


class OllamaClient:
    """Client synchrone de l'API native d'Ollama, sur une URL locale."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx2.BaseTransport | None = None,
        *,
        connect_timeout_s: float = 10.0,
        read_timeout_s: float = 900.0,
    ) -> None:
        self.base_url = check_local_base_url(base_url)
        self._http = httpx2.Client(
            base_url=self.base_url,
            transport=transport,
            trust_env=False,  # aucun proxy de l'environnement : la requête reste locale
            timeout=httpx2.Timeout(
                connect=connect_timeout_s, read=read_timeout_s, write=60.0, pool=60.0
            ),
        )

    # -- Cycle de vie ------------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- Requêtes simples --------------------------------------------------------------------

    def _check_status(self, response: httpx2.Response, endpoint: str) -> None:
        if response.status_code >= 500:
            raise OllamaUnavailableError(
                f"{endpoint} : statut {response.status_code} ({_error_message(response)})"
            )
        if response.status_code >= 400:
            raise OllamaRequestError(
                f"{endpoint} : statut {response.status_code} ({_error_message(response)})",
                response.status_code,
            )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        body: Mapping[str, Any] | None = None,
        timeout: Any = httpx2.USE_CLIENT_DEFAULT,
    ) -> dict[str, Any]:
        try:
            response = self._http.request(method, endpoint, json=body, timeout=timeout)
        except httpx2.TransportError as exc:
            raise OllamaUnavailableError(f"{endpoint} : service injoignable ({exc})") from exc
        self._check_status(response, endpoint)
        try:
            payload = response.json()
        except ValueError as exc:
            raise OllamaRequestError(f"{endpoint} : réponse illisible ({exc})") from exc
        if not isinstance(payload, dict):
            raise OllamaRequestError(f"{endpoint} : objet JSON attendu")
        return payload

    def version(self) -> str:
        """Version du service (``GET /api/version``), avec un délai court : une sonde bloquée
        ne doit pas dépasser ``ollama_wait_s`` dans ``wait_for_ollama``."""
        payload = self._request_json("GET", "/api/version", timeout=VERSION_TIMEOUT_S)
        version = payload.get("version")
        if not isinstance(version, str) or not version:
            raise OllamaRequestError("/api/version : champ « version » absent")
        return version

    def show(self, model: str) -> dict[str, Any]:
        """Fiche du modèle (``POST /api/show``) : capacités, informations, détails."""
        return self._request_json("POST", "/api/show", {"model": model})

    def tags(self) -> list[dict[str, Any]]:
        """Modèles installés (``GET /api/tags``), avec leur ``digest``."""
        return list(self._request_json("GET", "/api/tags").get("models") or [])

    def ps(self) -> list[dict[str, Any]]:
        """Modèles chargés (``GET /api/ps``), avec ``size`` et ``size_vram``."""
        return list(self._request_json("GET", "/api/ps").get("models") or [])

    def unload(self, model: str) -> None:
        """Décharge le modèle (``keep_alive: 0`` sans prompt, sur ``/api/generate``)."""
        self._request_json(
            "POST", "/api/generate", {"model": model, "keep_alive": 0, "stream": False}
        )

    # -- Chat --------------------------------------------------------------------------------

    @staticmethod
    def build_chat_body(
        model: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        seed: int,
        num_ctx: int,
        num_predict: int,
        capabilities: Collection[str],
        format: Mapping[str, Any] | str | None = None,  # noqa: A002 (nom de l'API Ollama)
        think: bool | str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        allowed_think_values: Collection[str] = (),
        keep_alive: int | str | None = None,
    ) -> dict[str, Any]:
        """Corps de ``POST /api/chat`` : tout paramètre implicite est refusé (``ValueError``)."""
        for name, value, minimum in (
            ("seed", seed, 0),
            ("num_ctx", num_ctx, 1),
            ("num_predict", num_predict, 1),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
                raise ValueError(f"{name} : entier ≥ {minimum} attendu, reçu {value!r}")
        capabilities = set(capabilities)
        if "decision" in capabilities:
            raise ValueError(f"{model} déclare la capacité « decision » : exclu du chat (AD-9)")
        if format is not None and format != "json" and not isinstance(format, Mapping):
            raise ValueError("format : schéma JSON, « json » ou None attendu")

        body: dict[str, Any] = {
            "model": model,
            "messages": [dict(message) for message in messages],
            "stream": True,
            "format": dict(format) if isinstance(format, Mapping) else format,
            "options": {
                "seed": seed,
                "temperature": 0,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }

        if "thinking" in capabilities:
            if think is None:
                raise ValueError(
                    f"{model} déclare « thinking » : think doit être fixé explicitement"
                )
            if isinstance(think, str) and think not in set(allowed_think_values):
                raise ValueError(f"think={think!r} absent des valeurs déclarées pour {model}")
            if not isinstance(think, (bool, str)):
                raise ValueError(f"think : booléen ou chaîne attendu, reçu {think!r}")
            body["think"] = think
        elif think is not None:
            raise ValueError(f"think fourni alors que {model} ne déclare pas « thinking »")

        if tools is not None:
            if "tools" not in capabilities:
                raise ValueError(f"tools fourni alors que {model} ne déclare pas « tools »")
            if not tools:
                raise ValueError("tools : liste non vide ou None attendue")
            body["tools"] = [dict(tool) for tool in tools]

        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        return body

    def chat(
        self,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        seed: int,
        num_ctx: int,
        num_predict: int,
        capabilities: Collection[str],
        format: Mapping[str, Any] | str | None = None,  # noqa: A002 (nom de l'API Ollama)
        think: bool | str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        allowed_think_values: Collection[str] = (),
        keep_alive: int | str | None = None,
    ) -> ChatResult:
        """Appel ``POST /api/chat`` en streaming, agrégé (voir ``ChatResult``).

        ``capabilities`` = liste ``capabilities`` de ``/api/show`` pour ce modèle. Aucune
        requête ne part si un paramètre est incompatible avec elle (``ValueError``).
        """
        body = self.build_chat_body(
            model,
            messages,
            seed=seed,
            num_ctx=num_ctx,
            num_predict=num_predict,
            capabilities=capabilities,
            format=format,
            think=think,
            tools=tools,
            allowed_think_values=allowed_think_values,
            keep_alive=keep_alive,
        )
        result = ChatResult()
        start = time.perf_counter()
        content: list[str] = []
        thinking: list[str] = []
        done = False
        try:
            with self._http.stream("POST", "/api/chat", json=body) as response:
                if response.status_code >= 400:
                    response.read()
                    self._check_status(response, "/api/chat")
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    chunk = self._parse_chunk(line)
                    message = chunk.get("message") or {}
                    if message.get("content"):
                        content.append(message["content"])
                        result.chunks["content"] += 1
                    if message.get("thinking"):
                        thinking.append(message["thinking"])
                        result.chunks["thinking"] += 1
                    if message.get("tool_calls"):
                        result.tool_calls.extend(message["tool_calls"])
                        result.chunks["tool_calls"] += 1  # fragments du flux, pas appels
                    if chunk.get("done"):
                        done = True
                        self._read_final_chunk(chunk, result)
                        break
        except httpx2.TransportError as exc:
            raise OllamaUnavailableError(
                f"/api/chat : service injoignable ou coupé ({exc})"
            ) from exc
        if not done:
            raise OllamaUnavailableError("/api/chat : flux interrompu avant « done »")
        result.content = "".join(content)
        result.thinking = "".join(thinking)
        result.wall_s = time.perf_counter() - start
        return result

    @staticmethod
    def _parse_chunk(line: str) -> dict[str, Any]:
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OllamaRequestError(f"/api/chat : fragment de flux illisible ({exc})") from exc
        if not isinstance(chunk, dict):
            raise OllamaRequestError("/api/chat : fragment de flux qui n'est pas un objet")
        if "error" in chunk:
            raise OllamaRequestError(f"/api/chat : erreur dans le flux ({chunk['error']})")
        return chunk

    @staticmethod
    def _read_final_chunk(chunk: Mapping[str, Any], result: ChatResult) -> None:
        reason = chunk.get("done_reason")
        result.done_reason = reason if isinstance(reason, str) else None
        result.prompt_eval_count = _int_field(chunk, "prompt_eval_count")
        # Absent quand rien n'est en cache (omitempty côté Ollama) : 0.
        result.prompt_eval_cached_count = _int_field(chunk, "prompt_eval_cached_count")
        result.eval_count = _int_field(chunk, "eval_count")
        result.durations_ns = {
            "total": _int_field(chunk, "total_duration"),
            "load": _int_field(chunk, "load_duration"),
            "prompt_eval": _int_field(chunk, "prompt_eval_duration"),
            "eval": _int_field(chunk, "eval_duration"),
        }


def wait_for_ollama(
    client: OllamaClient,
    wait_s: float,
    expected_version: str | None,
    *,
    poll_s: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Attend que ``/api/version`` réponde, au plus ``wait_s`` secondes, sans jamais
    redémarrer Ollama. Rend la version ; ``OllamaGoneError`` si le service reste absent,
    ``OllamaVersionChangedError`` s'il revient dans une autre version que ``expected_version``.
    """
    deadline = clock() + wait_s
    announced = False
    while True:
        try:
            version = client.version()
        except OllamaUnavailableError as exc:
            remaining = deadline - clock()
            if remaining <= 0:
                raise OllamaGoneError(
                    f"Ollama toujours absent après {wait_s:g} s d'attente ({exc}) : arrêt sans "
                    "écrire de ligne."
                ) from exc
            if not announced:
                logger.warning(
                    "Ollama ne répond pas (%s) : attente jusqu'à %g s, sans redémarrage.",
                    exc,
                    wait_s,
                )
                announced = True
            sleep(min(poll_s, remaining))
            continue
        if expected_version is not None and version != expected_version:
            raise OllamaVersionChangedError(
                f"Ollama est revenu en version {version}, la campagne exige {expected_version}."
            )
        if announced:
            logger.info("Ollama répond de nouveau (version %s).", version)
        return version
