"""Mesure de latence stable face à la charge du runner (story 8.5) : un appel d'échauffement, puis
cinq mesures, dont on retient le deuxième meilleur -- robuste à un appel lent isolé sans affaiblir le
budget. Décision d'Anaël du 2026-10-23 (remplace le critère « médiane de plusieurs appels » de
`epics.md`) : la médiane de cinq dépassait déjà le budget une fois sur deux en CI
(`test_shell.py:95-99`), alors que le deuxième meilleur reste stable sous la charge des autres jobs.

Un seul endroit pour la règle : `test_conversations_api.py`, `test_model_card_api.py` et
`test_shell.py` l'utilisent tous les trois. `test_read_budget.py` a son propre modèle (meilleur de
trois sur une app neuve, à chaque essai) : il n'est pas touché, il mesure un cas différent (cache
froid d'une app qui vient de démarrer, pas un appel répété sur une app déjà chaude)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

MEASUREMENTS = 5
SECOND_BEST_INDEX = 1  # deuxième meilleur de cinq, après l'échauffement


def _format(runs: list[float]) -> str:
    return ", ".join(f"{seconds * 1000:.0f}" for seconds in runs)


def second_best_of_five(measure: Callable[[], float]) -> tuple[float, list[float]]:
    """`measure` rend une durée en secondes à chaque appel. Un premier appel chauffe (jeté, jamais
    mesuré) ; rend `(deuxième meilleur, les cinq mesures triées)`."""
    measure()
    runs = sorted(measure() for _ in range(MEASUREMENTS))
    return runs[SECOND_BEST_INDEX], runs


def assert_under_budget(measure: Callable[[], float], budget_s: float, label: str = "") -> None:
    """Échoue si le deuxième meilleur de cinq mesures (après échauffement) dépasse `budget_s`, avec
    toutes les mesures dans le message d'échec."""
    best, runs = second_best_of_five(measure)
    prefix = f"{label} : " if label else ""
    assert best < budget_s, f"{prefix}{_format(runs)} ms (budget {budget_s * 1000:.0f} ms)"


async def assert_under_budget_async(
    measure: Callable[[], Awaitable[float]], budget_s: float, label: str = ""
) -> None:
    """Comme `assert_under_budget`, pour une mesure asynchrone (un appel HTTP via `httpx.AsyncClient`,
    par exemple) : mêmes règles, un seul endroit pour la statistique."""
    await measure()
    runs = sorted([await measure() for _ in range(MEASUREMENTS)])
    best = runs[SECOND_BEST_INDEX]
    prefix = f"{label} : " if label else ""
    assert best < budget_s, f"{prefix}{_format(runs)} ms (budget {budget_s * 1000:.0f} ms)"


def second_best_of_five_many(
    measure: Callable[[], Mapping[str, float]],
) -> tuple[dict[str, float], list[Mapping[str, float]]]:
    """Comme `second_best_of_five`, pour une mesure qui rend plusieurs durées nommées à la fois (un
    seul chargement produit plusieurs repères) : le deuxième meilleur est pris séparément pour
    chaque nom, sur les cinq mêmes passages."""
    measure()
    runs = [measure() for _ in range(MEASUREMENTS)]
    best = {key: sorted(run[key] for run in runs)[SECOND_BEST_INDEX] for key in runs[0]}
    return best, runs
