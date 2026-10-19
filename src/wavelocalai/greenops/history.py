"""Historique carbone : une ligne par `app_session` close (story 5.2, AD-10, AD-13).

Calculé depuis les feuilles de `runs`, avec le même prédicat que le CO2 de session (`session.py`) :
les conversations effacées y comptent encore, car `runs` survit à l'effacement (AD-13 : le registre
carbone ne baisse jamais). La session en cours n'y figure pas : elle n'y entre qu'une fois close, par
une remise à zéro ou le démarrage suivant du serveur (D-37). Une session sans aucune feuille comptée
(un démarrage sans réponse) n'a rien à montrer et n'y figure pas non plus.

Un total inconnu n'est jamais 0 (AD-10) : `total_mg` est nul quand aucune réponse de la session n'a
été mesurée, `local_mg` et `cloud_mg` le sont quand la session a des réponses de cette origine mais
aucune mesurée. Une origine sans aucune réponse vaut exactement 0 (aucun appel cloud, par exemple).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from wavelocalai.greenops.session import LEAF_WHERE, ORIGIN_SQL
from wavelocalai.store.db import Store

Window = Literal["7d", "30d", "all"]
WINDOWS: dict[str, timedelta | None] = {
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "all": None,
}

_HISTORY_SQL = f"""
SELECT s.id, s.started_at,
       MAX(r.ended_at) AS ended_at,
       COUNT(*) AS runs,
       SUM(r.co2_mg IS NULL) AS unmeasurable,
       SUM(r.co2_mg) AS mg,
       SUM(CASE WHEN {ORIGIN_SQL} = 'local' THEN r.co2_mg END) AS local_mg,
       SUM(CASE WHEN {ORIGIN_SQL} = 'cloud' THEN r.co2_mg END) AS cloud_mg,
       SUM({ORIGIN_SQL} = 'local') AS local_runs,
       SUM({ORIGIN_SQL} = 'cloud') AS cloud_runs
FROM app_sessions s
JOIN runs r ON r.app_session = s.id
WHERE s.id <> ?
  AND {LEAF_WHERE}
GROUP BY s.id
HAVING MAX(r.ended_at) >= ?
ORDER BY s.started_at, s.rowid
"""


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


async def carbon_history(
    store: Store,
    current_session_id: str | None,
    window: str = "7d",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Sessions closes dont la dernière réponse tombe dans la fenêtre, de la plus ancienne à la plus
    récente. `window` : `7d`, `30d` ou `all`."""
    if window not in WINDOWS:
        raise ValueError(f"Fenêtre inconnue : {window!r}")
    span = WINDOWS[window]
    since = "" if span is None else _iso((now or datetime.now(UTC)) - span)
    rows = await store.aread(_HISTORY_SQL, (current_session_id or "", since))
    sessions = [
        {
            "id": row["id"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "total_mg": row["mg"],
            "local_mg": row["local_mg"] if row["local_runs"] else 0.0,
            "cloud_mg": row["cloud_mg"] if row["cloud_runs"] else 0.0,
            "measured_runs": row["runs"] - row["unmeasurable"],
            "unmeasurable_runs": row["unmeasurable"],
        }
        for row in rows
    ]
    return {"window": window, "sessions": sessions}
