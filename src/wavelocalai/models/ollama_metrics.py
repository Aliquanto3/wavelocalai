"""Résultat d'un appel Ollama depuis son fragment final (`done`) : copie adaptée de
`ollama_metrics` de la v1 (`src/core/metrics.py`), sans l'importer.

Débit (D3) = `eval_count / eval_duration` : vitesse de génération pure, hors chargement du modèle
et hors lecture du prompt (prefill, `prompt_eval_duration`), comme `scripts/benchmark_slm.py`. Le
repli sur la durée murale (chargement et prefill compris) n'a lieu que si `eval_duration` manque
ou vaut 0 ; il est alors marqué `tps_source = "wallclock"`. Jamais de division par zéro. Le prefill
a ses propres champs (`prefill_s`, `prefill_tps = prompt_eval_count / prompt_eval_duration`), nuls
si Ollama ne donne pas sa durée (prompt déjà en cache).
"""

from __future__ import annotations

from typing import Any

from wavelocalai.models.port import ChatResult

NS_PER_S = 1e9


def chunk_field(chunk: Any, name: str) -> Any:
    """Champ d'un fragment Ollama, dict ou objet pydantic (`ollama.ChatResponse`) ; `None` s'il
    manque."""
    if chunk is None:
        return None
    if isinstance(chunk, dict):
        return chunk.get(name)
    return getattr(chunk, name, None)


def _positive_ns(value: Any) -> float | None:
    """Durée Ollama (ns) strictement positive, sinon `None` (absente, nulle, illisible)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _seconds(ns: float) -> float:
    return round(ns / NS_PER_S, 3)


def ollama_result(
    final_chunk: Any,
    wall_s: float,
    *,
    ttft_s: float | None = None,
    fallback_output_tokens: int = 0,
) -> ChatResult:
    """`ChatResult` d'un appel `/api/chat` terminé.

    `wall_s` : durée murale de l'appel. `ttft_s` : délai jusqu'au premier fragment de texte (mesuré
    par l'adaptateur). `fallback_output_tokens` : estimation utilisée seulement si `eval_count`
    manque (un `eval_count` réel, 0 compris, prime).
    """
    eval_count = chunk_field(final_chunk, "eval_count")
    output_tokens = eval_count if eval_count is not None else (fallback_output_tokens or 0)
    eval_ns = _positive_ns(chunk_field(final_chunk, "eval_duration"))
    raw_load = chunk_field(final_chunk, "load_duration")
    load_ns = _positive_ns(raw_load)
    total_ns = _positive_ns(chunk_field(final_chunk, "total_duration"))
    prompt_eval_ns = _positive_ns(chunk_field(final_chunk, "prompt_eval_duration"))
    prompt_count = chunk_field(final_chunk, "prompt_eval_count")
    wall = wall_s if wall_s and wall_s > 0 else 0.0

    if eval_ns:
        tps = round(output_tokens / (eval_ns / NS_PER_S), 2)
        source = "ollama_eval"
    else:
        tps = round(output_tokens / wall, 2) if wall > 0 else 0.0
        source = "wallclock"

    return ChatResult(
        finish_reason=str(chunk_field(final_chunk, "done_reason") or "stop"),
        input_tokens=chunk_field(final_chunk, "prompt_eval_count"),
        output_tokens=output_tokens,
        ttft_s=None if ttft_s is None else round(ttft_s, 3),
        load_s=(_seconds(load_ns) if load_ns else 0.0) if raw_load is not None else None,
        eval_s=_seconds(eval_ns) if eval_ns else None,
        total_s=_seconds(total_ns) if total_ns else round(wall, 3),
        tps=tps,
        tps_source=source,  # type: ignore[arg-type]
        prefill_s=_seconds(prompt_eval_ns) if prompt_eval_ns else None,
        prefill_tps=(
            round(prompt_count / (prompt_eval_ns / NS_PER_S), 2)
            if prompt_eval_ns and prompt_count is not None
            else None
        ),
    )
