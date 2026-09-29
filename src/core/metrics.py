import time
from dataclasses import dataclass
from typing import Any

# Les durées d'Ollama sont en nanosecondes.
NS_PER_S = 1e9


@dataclass(frozen=True)
class ReasoningChunk:
    """Fragment du raisonnement d'un modèle (`message.thinking` d'Ollama), transmis à part du
    texte de la réponse. Ce n'est pas un `str` : les consommateurs qui ne gardent que les `str`
    ne le comptent jamais comme réponse."""

    text: str


INTERRUPTED_RESPONSE_DEFAULT = "Réponse interrompue : Ollama a arrêté la génération avant la fin."


class InterruptedResponseError(RuntimeError):
    """Flux Ollama terminé sans fragment final (`done`) : la réponse est tronquée. Elle ne doit
    jamais être présentée comme complète, stockée ni envoyée au juge."""

    def __init__(self, message: str = INTERRUPTED_RESPONSE_DEFAULT):
        super().__init__(message)


@dataclass
class InferenceMetrics:
    """Structure standard pour les métriques d'inférence"""

    model_name: str
    input_tokens: int
    output_tokens: int
    total_duration_s: float
    load_duration_s: float
    tokens_per_second: float
    model_size_gb: float = 0.0  # Rempli via la config

    # Placeholder pour le Green IT (Module futur)
    energy_wh: float = None
    carbon_g: float = None

    # Chargement du modèle mesuré par le fournisseur (`load_duration` d'Ollama présent) :
    # « Chargement » s'affiche à part. False pour les fournisseurs cloud et quand Ollama ne
    # l'a pas renvoyé.
    load_measured: bool = False
    # Durées de génération et de lecture du prompt (prefill) d'Ollama, en secondes.
    # `eval_duration_s` None : débit calculé sur la durée murale (cloud, ou repli), estimé.
    eval_duration_s: float | None = None
    prompt_eval_duration_s: float | None = None

    @property
    def throughput_estimated(self) -> bool:
        """Débit calculé sur la durée murale (chargement et prefill compris), pas sur la seule
        génération : l'interface le signale « estimé »."""
        return self.eval_duration_s is None


def _chunk_field(chunk: Any, name: str):
    """Champ d'un chunk Ollama, dict ou objet pydantic ; None s'il manque."""
    if chunk is None:
        return None
    if isinstance(chunk, dict):
        return chunk.get(name)
    return getattr(chunk, name, None)


def _positive_ns(value) -> float | None:
    """Durée Ollama (ns) strictement positive, sinon None (absente, nulle, illisible)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def ollama_metrics(
    model_name: str,
    final_chunk: Any,
    wall_duration_s: float,
    fallback_output_tokens: int = 0,
) -> InferenceMetrics:
    """
    Métriques d'un appel Ollama depuis son chunk final (`done`), dict ou objet pydantic.

    Débit (D3) = `eval_count / eval_duration`, comme `scripts/benchmark_slm.py` : vitesse de
    génération pure, hors chargement et hors lecture du prompt. Repli sur la durée murale
    seulement si `eval_duration` manque ou vaut 0 ; jamais de division par zéro.
    Durée totale = `total_duration` d'Ollama, sinon la durée murale. Chargement =
    `load_duration`, affiché à part s'il est présent (`load_measured`). Repli sur la durée
    murale : `eval_duration_s` vaut None (`throughput_estimated`).

    Args:
        model_name: Tag du modèle.
        final_chunk: Chunk final du flux (None si le flux n'en a pas fourni).
        wall_duration_s: Durée murale de l'appel, en secondes.
        fallback_output_tokens: Tokens générés si `eval_count` manque (estimation).
    """
    eval_count = _chunk_field(final_chunk, "eval_count")
    # Un eval_count réel (0 compris) prime ; l'estimation seulement s'il manque.
    output_tokens = eval_count if eval_count is not None else (fallback_output_tokens or 0)
    input_tokens = _chunk_field(final_chunk, "prompt_eval_count") or 0
    eval_ns = _positive_ns(_chunk_field(final_chunk, "eval_duration"))
    prompt_eval_ns = _positive_ns(_chunk_field(final_chunk, "prompt_eval_duration"))
    raw_load = _chunk_field(final_chunk, "load_duration")
    load_ns = _positive_ns(raw_load)
    total_ns = _positive_ns(_chunk_field(final_chunk, "total_duration"))

    wall = wall_duration_s if wall_duration_s and wall_duration_s > 0 else 0.0
    if eval_ns:
        tokens_per_second = output_tokens / (eval_ns / NS_PER_S)
    else:
        tokens_per_second = output_tokens / wall if wall > 0 else 0.0

    return InferenceMetrics(
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_duration_s=round(total_ns / NS_PER_S if total_ns else wall, 2),
        load_duration_s=round(load_ns / NS_PER_S, 2) if load_ns else 0.0,
        tokens_per_second=round(tokens_per_second, 2),
        carbon_g=0.0,
        load_measured=raw_load is not None,
        eval_duration_s=round(eval_ns / NS_PER_S, 3) if eval_ns else None,
        prompt_eval_duration_s=round(prompt_eval_ns / NS_PER_S, 3) if prompt_eval_ns else None,
    )


class MetricsCalculator:
    """Helper pour mesurer le temps d'exécution"""

    def __init__(self):
        self.start_time = 0.0
        self.end_time = 0.0

    def start(self):
        self.start_time = time.perf_counter()

    def stop(self):
        self.end_time = time.perf_counter()

    @property
    def duration(self):
        return self.end_time - self.start_time
