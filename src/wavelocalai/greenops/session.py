"""Session carbone : somme des feuilles de l'`app_session` courante (AD-10).

Une `app_session` commence à chaque démarrage du serveur et à chaque remise à zéro (le hub l'ouvre).
Le CO2 de session est la somme des `co2.mg` des **runs feuilles** de cette session : un run parent
n'est jamais compté (ses feuilles le sont), et un run sans mesure (`mg` nul, méthode
`unmeasurable`) est compté à part, jamais comme 0. Le module est le genre du run racine : celui du
parent pour une feuille enfant, le sien pour une feuille racine. Ne dépend ni de CodeCarbon ni
d'ecologits : elle lit seulement la table `runs`.
"""

from __future__ import annotations

from typing import Any

from wavelocalai.runs.system_bus import SystemBus
from wavelocalai.store.db import Store

CARBON_UPDATED = "carbon_updated"
ORIGINS = ("local", "cloud")

# Feuille = run terminé sans enfant. Une feuille close sans `co2` (erreur, annulation, arrêt) n'a
# pas de mesure : elle compte parmi les non-mesurables (AD-10), jamais comme 0 ni comme absente.
# Un run encore actif n'est pas compté. Un import (`ingest`) est un parent pur : sans lot
# d'embedding (fichiers déjà présents, tous en échec) il n'est pas une feuille à compter. L'origine
# manquante se déduit de la méthode : ecologits estime un modèle distant, codecarbon mesure ce poste.
LEAF_WHERE = """r.ended_at IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM runs child WHERE child.parent_run_id = r.id)
  AND r.kind <> 'ingest'"""
ORIGIN_SQL = "COALESCE(r.origin, CASE r.co2_method WHEN 'ecologits' THEN 'cloud' ELSE 'local' END)"

# `LEAF_WHERE` et `ORIGIN_SQL` sont partagés avec l'historique (`history.py`) : une session close et
# la session courante comptent exactement les mêmes runs, avec la même origine.
_LEAVES_SQL = f"""
SELECT COALESCE(parent.kind, r.kind) AS module,
       {ORIGIN_SQL} AS bucket,
       COUNT(*) AS runs,
       SUM(r.co2_mg IS NULL) AS unmeasurable,
       COALESCE(SUM(r.co2_mg), 0.0) AS mg
FROM runs r
LEFT JOIN runs parent ON parent.id = r.parent_run_id
WHERE r.app_session = ?
  AND {LEAF_WHERE}
GROUP BY module, bucket
"""


def empty_summary(session: dict[str, Any] | None = None) -> dict[str, Any]:
    """Session sans aucun run : total 0 mg et 0 non-mesurable."""
    return {
        "app_session": session,
        "total_mg": 0.0,
        "measured_runs": 0,
        "unmeasurable_runs": 0,
        "by_origin": {origin: {"mg": 0.0, "runs": 0, "unmeasurable_runs": 0} for origin in ORIGINS},
        "by_module": {},
    }


async def session_summary(store: Store, session_id: str) -> dict[str, Any]:
    """CO2 de la session `session_id`, par module, Local et Cloud, non-mesurables à part."""
    rows = await store.aread(
        "SELECT id, started_at, reason FROM app_sessions WHERE id = ?", (session_id,)
    )
    session = None if not rows else {k: rows[0][k] for k in ("id", "started_at", "reason")}
    summary = empty_summary(session)
    leaves = await store.aread(_LEAVES_SQL, (session_id,))
    for row in leaves:
        measured = row["runs"] - row["unmeasurable"]
        mg = float(row["mg"])
        summary["total_mg"] += mg
        summary["measured_runs"] += measured
        summary["unmeasurable_runs"] += row["unmeasurable"]
        origin = summary["by_origin"][row["bucket"]]
        origin["mg"] += mg
        origin["runs"] += row["runs"]
        origin["unmeasurable_runs"] += row["unmeasurable"]
        module = summary["by_module"].setdefault(
            row["module"], {"mg": 0.0, "runs": 0, "unmeasurable_runs": 0}
        )
        module["mg"] += mg
        module["runs"] += row["runs"]
        module["unmeasurable_runs"] += row["unmeasurable"]
    return summary


async def announce_carbon_updated(bus: SystemBus, store: Store, session_id: str) -> dict[str, Any]:
    """Publie `carbon_updated` (la somme de la session) sur le port `SystemBus` ; à appeler après
    chaque `hub.finish_leaf`. Rend la somme publiée."""
    summary = await session_summary(store, session_id)
    bus.publish(CARBON_UPDATED, summary)
    return summary
