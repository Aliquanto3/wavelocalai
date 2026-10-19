"""Ce que l'instantané d'un banc d'essai (`GET /api/runs/{id}`, kind `bench`) ajoute au run, et la
liste des tests passés (story 7.4).

Lecture seule sur la base : la configuration vit dans `runs.params` (scénario, `force_format`,
`concise`), l'entrée saisie dans l'événement `bench_input` (jamais dans `params`, AD-7), la sortie
dans les `token` du flux et le verdict de format dans l'événement `metrics` (`format_verdict`, calculé
par le serveur au moment de la réponse, AD-20). Un scénario sans format n'a pas de `format_verdict` :
la clé est absente.
"""

from __future__ import annotations

import json
from typing import Any

from wavelocalai.store.db import Store

EXCERPT_CHARS = 200


async def bench_snapshot_fields(store: Store, snapshot: dict[str, Any]) -> dict[str, Any]:
    """`bench` : `{scenario, force_format, concise, input, output}` ; `format_verdict` à part, quand
    le scénario attend un format et que la réponse est allée à son terme."""
    rows = await store.aread(
        "SELECT type, data FROM run_events WHERE run_id = ?"
        " AND type IN ('bench_input', 'token', 'retry', 'metrics') ORDER BY seq",
        (snapshot["run_id"],),
    )
    text: str | None = None
    parts: list[str] = []
    verdict: dict[str, Any] | None = None
    for row in rows:
        data = json.loads(row["data"])
        if row["type"] == "bench_input":
            text = data.get("text")
        elif row["type"] == "token":
            if data.get("channel", "answer") == "answer":
                parts.append(data.get("text") or "")
        elif row["type"] == "retry":  # génération relancée : le texte partiel n'est plus la réponse
            parts.clear()
        elif isinstance(data.get("format_verdict"), dict):
            verdict = data["format_verdict"]
    params = snapshot["params"]
    fields: dict[str, Any] = {
        "bench": {
            "scenario": params.get("scenario"),
            "force_format": bool(params.get("force_format")),
            "concise": bool(params.get("concise")),
            "input": text,
            "output": "".join(parts),
        }
    }
    if verdict is not None:
        fields["format_verdict"] = verdict
    return fields


async def list_bench_runs(store: Store, limit: int = 20) -> list[dict[str, Any]]:
    """Les bancs d'essai les plus récents d'abord, pour les rouvrir : identifiant, statut, dates,
    scénario, modèle, options, début de l'entrée et, si le scénario attend un format, si la sortie
    le respecte (`format_ok`, `null` sans verdict)."""
    rows = await store.aread(
        "SELECT r.id, r.status, r.started_at, r.ended_at, r.model, r.params,"
        " (SELECT data FROM run_events e WHERE e.run_id = r.id AND e.type = 'bench_input'"
        "  LIMIT 1) AS input,"
        " (SELECT data FROM run_events e WHERE e.run_id = r.id AND e.type = 'metrics'"
        "  LIMIT 1) AS metrics"
        " FROM runs r WHERE r.kind = 'bench' AND r.parent_run_id IS NULL"
        " ORDER BY r.started_at DESC, r.rowid DESC LIMIT ?",
        (limit,),
    )
    runs = []
    for row in rows:
        params = json.loads(row["params"])
        text = (json.loads(row["input"]).get("text") or "") if row["input"] else ""
        verdict = json.loads(row["metrics"]).get("format_verdict") if row["metrics"] else None
        runs.append(
            {
                "run_id": row["id"],
                "status": row["status"],
                "started_at": row["started_at"],
                "ended_at": row["ended_at"],
                "scenario": params.get("scenario"),
                "model": row["model"],
                "force_format": bool(params.get("force_format")),
                "concise": bool(params.get("concise")),
                "format_ok": verdict.get("ok") if isinstance(verdict, dict) else None,
                "input": text[:EXCERPT_CHARS],
            }
        )
    return runs
