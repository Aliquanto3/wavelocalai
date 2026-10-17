"""Vérification du GPU avant mesure (AD-13) : ``nvidia-smi`` en sous-processus, sans dépendance.

``/api/ps`` ne voit que les modèles d'Ollama : un autre processus de calcul (``llama-server``
d'un autre projet, par exemple) fausserait les débits mesurés sans alerte. ``check_gpu`` refuse
(``GpuCheckError``, message français qui nomme les processus et la mémoire occupée) quand :

- un processus de calcul autre qu'Ollama (nom de programme commençant par ``ollama``) occupe le
  GPU ;
- ou la mémoire GPU utilisée dépasse ``max_idle_used_mib`` alors qu'aucun modèle n'est chargé
  d'après ``/api/ps`` (``loaded_models`` vide).

Sous Windows (WDDM), ``--query-compute-apps`` rend ``[N/A]`` pour la mémoire par processus : la
règle de mémoire repose donc sur ``--query-gpu=memory.used``, jamais sur la mémoire par
processus. Cette valeur compte aussi la mémoire graphique (affichage, navigateurs, overlays) :
sur une machine dont l'affichage passe par le GPU NVIDIA, relever ``max_idle_used_mib``.
``memory.used`` lui-même inconnu (``[N/A]``) : la règle de mémoire est sautée, avec un
avertissement journalisé et ``memory_rule: "skipped_unknown"`` dans le résultat (la règle des
processus reste appliquée ; refuser bloquerait sans recours les cartes qui ne rendent pas
cette valeur). ``nvidia-smi`` absent, lent ou illisible refuse quand le contrôle est actif
(``gpu_check: {enabled: false}`` dans la configuration de campagne pour le désactiver).

En cours de campagne (``wait_gpu_released``, avant chaque modèle), le modèle précédent vient
d'être déchargé : la règle de mémoire attend sa libération (``/api/ps`` vide, puis
``memory.used`` sous le seuil) jusqu'à ``release_wait_s`` secondes avant de refuser.

Le résultat (``gpu_check_result``) va dans ``informative.checklist`` du manifeste : jamais
bloquant à la reprise.
"""

from __future__ import annotations

import logging
import ntpath
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MAX_IDLE_USED_MIB = 1024
DEFAULT_RELEASE_WAIT_S = 30
RELEASE_POLL_S = 2
TIMEOUT_S = 10
_APPS_QUERY = ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory"]
_MEMORY_QUERY = ["nvidia-smi", "--query-gpu=index,memory.used"]
_FORMAT = "--format=csv,noheader,nounits"

# Point d'injection des tests (sous-processus simulé) : lu à l'appel.
RUN: Callable[..., Any] = subprocess.run


class GpuCheckError(RuntimeError):
    """GPU occupé, ou contrôle impossible alors qu'il est actif : lancement refusé."""


class GpuMemoryBusyError(GpuCheckError):
    """Règle de mémoire : GPU trop occupé alors qu'aucun modèle n'est chargé."""


@dataclass(frozen=True)
class GpuCheckSettings:
    """Section ``gpu_check`` de la configuration de campagne."""

    enabled: bool = True
    max_idle_used_mib: int = DEFAULT_MAX_IDLE_USED_MIB
    release_wait_s: int = DEFAULT_RELEASE_WAIT_S


@dataclass(frozen=True)
class GpuProcess:
    pid: int
    name: str  # nom du programme, sans dossier
    used_mib: int | None  # None : « [N/A] » (WDDM)


def _nvidia_smi(query: list[str]) -> list[str]:
    command = [*query, _FORMAT]
    disable_hint = "désactiver le contrôle avec gpu_check: {enabled: false} dans la campagne"
    try:
        result = RUN(  # noqa: S603 (commande fixe, sans shell)
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
        )
    except FileNotFoundError:
        raise GpuCheckError(
            f"nvidia-smi introuvable : état du GPU invérifiable ; {disable_hint} si la machine "
            "n'a pas de GPU NVIDIA"
        ) from None
    except subprocess.TimeoutExpired:
        raise GpuCheckError(
            f"nvidia-smi sans réponse après {TIMEOUT_S} s : état du GPU invérifiable ; "
            f"{disable_hint}"
        ) from None
    except OSError as exc:
        raise GpuCheckError(
            f"nvidia-smi inexécutable ({type(exc).__name__}) ; {disable_hint}"
        ) from None
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise GpuCheckError(
            f"nvidia-smi a échoué (code {result.returncode}"
            f"{' : ' + detail[0] if detail else ''}) ; {disable_hint}"
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _mib(text: str) -> int | None:
    text = text.strip()
    if text.upper() in ("[N/A]", "N/A", "[NOT SUPPORTED]"):
        return None
    return int(float(text))


def parse_compute_apps(lines: Sequence[str]) -> list[GpuProcess]:
    """Lignes ``pid, process_name, used_memory`` : le chemin du programme peut contenir des
    virgules, la mémoire est donc lue depuis la droite et le pid depuis la gauche."""
    processes = []
    for line in lines:
        try:
            pid_text, rest = line.split(",", 1)
            path, memory = rest.rsplit(",", 1)
            processes.append(
                GpuProcess(
                    int(pid_text),
                    ntpath.basename(path.strip().replace("/", "\\")) or path.strip(),
                    _mib(memory),
                )
            )
        except ValueError:
            raise GpuCheckError(f"sortie de nvidia-smi illisible : {line!r}") from None
    return processes


def parse_memory_used(lines: Sequence[str]) -> list[int | None]:
    """Lignes ``index, memory.used`` : mémoire utilisée (MiB) de chaque GPU, ``None`` si
    ``nvidia-smi`` la dit inconnue (``[N/A]``)."""
    used: list[int | None] = []
    for line in lines:
        try:
            used.append(_mib(line.split(",", 1)[1]))
        except (IndexError, ValueError):
            raise GpuCheckError(f"sortie de nvidia-smi illisible : {line!r}") from None
    return used


def is_ollama(process: GpuProcess) -> bool:
    return process.name.lower().startswith("ollama")


def check_gpu(
    settings: GpuCheckSettings, loaded_models: Sequence[str] | None
) -> dict[str, Any]:
    """Refuse (``GpuCheckError``) si le GPU est occupé par autre chose qu'Ollama ; rend le
    résultat consignable (``enabled``, ``used_mib``, ``processes``...). Contrôle inactif :
    ``{"enabled": False}`` sans appel à ``nvidia-smi``. ``loaded_models`` : modèles de
    ``/api/ps`` (la règle de mémoire ne s'applique qu'à vide ; ``None`` = ``/api/ps``
    illisible, seule la règle des processus s'applique). ``memory.used`` inconnu : règle de
    mémoire sautée, avertissement journalisé, ``memory_rule: "skipped_unknown"``."""
    if not settings.enabled:
        return {"enabled": False}
    processes = parse_compute_apps(_nvidia_smi(_APPS_QUERY))
    used = parse_memory_used(_nvidia_smi(_MEMORY_QUERY))
    known = [value for value in used if value is not None]
    total_used: int | None = sum(known) if used and len(known) == len(used) else None
    total_text = "mémoire inconnue" if total_used is None else f"{total_used} MiB utilisés"

    def describe(item: GpuProcess) -> str:
        memory = "mémoire inconnue (WDDM)" if item.used_mib is None else f"{item.used_mib} MiB"
        return f"{item.name} (pid {item.pid}, {memory})"

    others = [item for item in processes if not is_ollama(item)]
    if others:
        raise GpuCheckError(
            "GPU occupé par un processus de calcul autre qu'Ollama : "
            f"{', '.join(describe(item) for item in others)} ; {total_text} au "
            "total sur le GPU. Arrêter ce processus avant la mesure : il fausserait les débits."
        )
    result: dict[str, Any] = {
        "enabled": True,
        "used_mib": total_used,
        "max_idle_used_mib": settings.max_idle_used_mib,
        "loaded_models": len(loaded_models or ()),
        "processes": [item.name for item in processes],
    }
    idle = loaded_models is not None and not loaded_models
    if total_used is None:
        logger.warning(
            "nvidia-smi ne rend pas memory.used ([N/A]) : règle de mémoire GPU sautée, "
            "seule la règle des processus s'applique"
        )
        result["memory_rule"] = "skipped_unknown"
    elif idle and total_used > settings.max_idle_used_mib:
        names = ", ".join(describe(item) for item in processes) or "aucun processus de calcul listé"
        raise GpuMemoryBusyError(
            f"{total_used} MiB de mémoire GPU utilisés (memory.used, mémoire graphique comprise : "
            "affichage, navigateurs) alors qu'aucun modèle n'est chargé dans Ollama, au-dessus "
            f"du seuil de {settings.max_idle_used_mib} MiB (processus de calcul : {names}). "
            "Libérer le GPU, ou relever gpu_check.max_idle_used_mib dans la campagne."
        )
    return result


def wait_gpu_released(
    settings: GpuCheckSettings,
    list_loaded: Callable[[], Sequence[str] | None],
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Contrôle d'avant modèle, en cours de campagne : attend jusqu'à ``release_wait_s`` que
    ``list_loaded()`` (modèles de ``/api/ps``, ``None`` si illisible) soit vide puis que la
    règle de mémoire passe ; au-delà, ``GpuMemoryBusyError``. Un modèle encore listé à
    l'échéance : seule la règle des processus s'applique (comme au lancement). Processus
    étranger ou ``nvidia-smi`` en échec : refus immédiat."""
    if not settings.enabled:
        return {"enabled": False}
    deadline = clock() + settings.release_wait_s
    while True:
        loaded = list_loaded()
        expired = clock() >= deadline
        if loaded and not expired:
            sleep(RELEASE_POLL_S)
            continue
        try:
            return check_gpu(settings, loaded)
        except GpuMemoryBusyError:
            if expired:
                raise
        sleep(RELEASE_POLL_S)


def driver_version() -> str | None:
    """Version du pilote NVIDIA pour la partie informative du manifeste (``None`` sans
    ``nvidia-smi``), par le même point d'injection ``RUN`` que le contrôle."""
    try:
        lines = _nvidia_smi(["nvidia-smi", "--query-gpu=driver_version"])
    except GpuCheckError:
        return None
    return lines[0] if lines else None
