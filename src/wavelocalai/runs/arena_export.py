"""Export d'une Arène en CSV ou en Markdown, avec la preuve de la mesure (story 3.6, AD-13, AD-20).

Fonctions pures : elles reçoivent l'instantané du run (`run_snapshot`), ce que son flux dit de la
configuration et des notes (`arena_record`) et la preuve que `routes_arena` rassemble (fiche machine,
version d'Ollama, digests des modèles). Rien d'autre n'entre dans le document : aucun réglage, aucune
clé d'API ; les valeurs texte passent en plus par `mask_secrets` avec les secrets connus de `Settings`,
au cas où une clé aurait été collée dans une question.

Par modèle : note et raison, débit D3 et `tps_source`, CO2 avec sa méthode, chargement, durée. La
preuve : fiche machine, version d'Ollama, digest de chaque modèle, méthode du CO2, juge et critères.
Un inconnu n'est jamais un 0 : une cellule vide en CSV, « inconnu » ou « non mesurable » en Markdown.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

from wavelocalai.runs.conversation_export import TPS_SOURCES, mask_value

FORMAT = "wavelocalai.arena/1"
CSV_COLUMNS = (
    "run_id",
    "question",
    "model",
    "origin",
    "status",
    "stopped_reason",
    "score",
    "reason",
    "tps",
    "tps_source",
    "co2_mg",
    "co2_method",
    "co2_estimated",
    "co2_reason",
    "load_s",
    "total_s",
    "input_tokens",
    "output_tokens",
    "model_digest",
    "judge",
    "judge_origin",
    "criteria",
    "ollama_version",
    "machine_os",
    "machine_cpu",
    "machine_ram_gb",
    "machine_accelerator",
    "app_version",
    "exported_at",
)
DEFINITIONS = {
    "score": "Note sur 100 donnée par le juge ; `null` pour « non évalué », jamais 0 ; `reason` dit "
    "pourquoi.",
    "tps": "Débit D3 : tokens générés par seconde de génération, chargement du modèle exclu ; "
    "`tps_source` dit s'il est mesuré par Ollama (ollama_eval) ou estimé sur l'horloge (wallclock).",
    "co2": "mg de CO2 équivalent ; `method` dit comment (codecarbon : mesuré sur ce poste, ecologits : "
    "estimé pour un modèle distant, unmeasurable : non mesurable, avec sa `reason`). Jamais 0 pour "
    "un inconnu.",
    "stopped_reason": "Présent si la lane a été arrêtée avant sa fin naturelle : `max_tokens` "
    "(plafond de jetons atteint), `loop` (répétition détectée) ou `user` (bouton « Arrêter ce "
    "modèle »). La réponse partielle reste notée.",
}
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _lane_rows(snapshot: Mapping[str, Any], record: Mapping[str, Any], digests: Mapping[str, Any]):
    models = [c for c in snapshot["children"] if c["kind"] == "generation"]
    for child in models:
        metrics = child["metrics"] or {}
        score = record["scores"].get(child["model"]) or {}
        lane = record["lanes"].get(child["model"]) or {}
        yield {
            "model": child["model"],
            "origin": metrics.get("origin"),
            "status": lane.get("status") or child["status"],
            "stopped_reason": lane.get("stopped_reason"),
            "score": score.get("score"),
            "reason": score.get("reason"),
            "tps": metrics.get("tps"),
            "tps_source": metrics.get("tps_source"),
            "co2": metrics.get("co2"),
            "load_s": metrics.get("load_s"),
            "total_s": metrics.get("total_s"),
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
            "digest": digests.get(child["model"]),
        }


def export_document(
    snapshot: Mapping[str, Any],
    record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    exported_at: str,
    version: str,
    secrets: Iterable[str] = (),
) -> dict[str, Any]:
    """Document d'export d'une Arène terminée, secrets masqués. `evidence` : `machine` (fiche et
    `ollama_version`) et `digests` (tag -> digest ou `None`)."""
    judge = record["judge"] or {}
    question = record["question"] or {}
    criteria = question.get("criteria") or judge.get("default_criteria") or []
    digests = evidence.get("digests") or {}
    rows = list(_lane_rows(snapshot, record, digests))
    tags = [row["model"] for row in rows] + ([judge["model"]] if judge.get("model") else [])
    document = {
        "format": FORMAT,
        "exported_at": exported_at,
        "app_version": version,
        "arena": {
            "run_id": snapshot["run_id"],
            "status": snapshot["status"],
            "started_at": snapshot["started_at"],
            "ended_at": snapshot["ended_at"],
            "question": question.get("text"),
        },
        "models": rows,
        "proof": {
            "machine": evidence.get("machine"),
            "ollama_version": (evidence.get("machine") or {}).get("ollama_version"),
            "model_digests": {tag: digests.get(tag) for tag in tags},  # juge compris
            "co2_methods": sorted(
                {row["co2"]["method"] for row in rows if row["co2"] and row["co2"].get("method")}
            ),
            "judge": {
                "model": judge.get("model"),
                "origin": judge.get("origin"),
                "params_active_b": judge.get("params_active_b"),
                "unreliable": judge.get("unreliable"),
                "single_judge": judge.get("single_judge"),
                "criteria": list(criteria),
            },
        },
        "definitions": DEFINITIONS,
    }
    return mask_value(document, tuple(secrets))  # type: ignore[no-any-return]


def _cell(value: Any) -> Any:
    """Une cellule CSV : vide pour un inconnu ; un texte qui commencerait un calcul dans un tableur
    (`=`, `+`, `-`, `@`) est précédé d'une apostrophe, la question ou la raison du juge pouvant le
    faire."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        return "'" + value
    return value


def to_csv(document: Mapping[str, Any]) -> str:
    """Une ligne par modèle ; la preuve de la mesure est répétée sur chaque ligne, pour qu'un
    tableau seul reste vérifiable. Séparateur `,`, guillemets RFC 4180, BOM UTF-8 pour Excel."""
    arena, proof = document["arena"], document["proof"]
    machine = proof.get("machine") or {}
    accelerator = (machine.get("accelerator") or {}).get("name")
    judge = proof["judge"]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in document["models"]:
        co2 = row["co2"] or {}
        writer.writerow(
            [
                _cell(value)
                for value in (
                    arena["run_id"],
                    arena["question"],
                    row["model"],
                    row["origin"],
                    row["status"],
                    row["stopped_reason"],
                    row["score"],
                    row["reason"],
                    row["tps"],
                    row["tps_source"],
                    co2.get("mg"),
                    co2.get("method"),
                    co2.get("estimated") if co2 else None,
                    co2.get("reason"),
                    row["load_s"],
                    row["total_s"],
                    row["input_tokens"],
                    row["output_tokens"],
                    row["digest"],
                    judge["model"],
                    judge["origin"],
                    " | ".join(judge["criteria"]),
                    proof["ollama_version"],
                    machine.get("os"),
                    machine.get("cpu"),
                    machine.get("ram_gb"),
                    accelerator,
                    document["app_version"],
                    document["exported_at"],
                )
            ]
        )
    return "\ufeff" + out.getvalue()


def _num(value: float | None, unit: str, digits: int = 1) -> str | None:
    if value is None:
        return None
    return f"{value:.{digits}f}".replace(".", ",") + " " + unit


def _co2_text(co2: Mapping[str, Any] | None) -> str:
    if co2 is None:
        return "non renseigné"
    if co2.get("mg") is None:
        return f"non mesurable ({co2.get('reason')})"
    value = f"{co2['mg']:.3g}".replace(".", ",")
    return f"{value} mg ({co2['method']}, {'estimé' if co2.get('estimated') else 'mesuré'})"


def _escape(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _score_text(row: Mapping[str, Any]) -> str:
    if row["score"] is None:
        reason = row["reason"] or row["status"]
        return f"non évalué ({reason})"
    return f"{row['score']}/100"


# Libellé de `stopped_reason` (story 9.2) dans l'export Markdown ; le CSV garde le code (`max_tokens`,
# `loop`, `user`), relisible par un tableur.
_STOPPED_LABELS = {
    "max_tokens": "longueur maximale atteinte",
    "loop": "arrêtée : le modèle se répétait",
    "user": "arrêtée à la demande",
}


def _stopped_text(row: Mapping[str, Any]) -> str:
    return _STOPPED_LABELS.get(row.get("stopped_reason") or "", "non")


def to_markdown(document: Mapping[str, Any]) -> str:
    arena, proof = document["arena"], document["proof"]
    lines = [
        "# Comparaison wavelocalai",
        "",
        f"- Lancée le {arena['started_at']} (statut : {arena['status']})",
        f"- Exportée le {document['exported_at']} (wavelocalai {document['app_version']})",
        "",
        "## Question",
        "",
        *[
            f"> {line}"
            for line in (arena["question"] or "(question absente du journal du run)").splitlines()
            or [""]
        ],
        "",
        "## Résultats",
        "",
        "| Modèle | Origine | Note | Débit | CO2 | Chargement | Durée | Arrêt |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in document["models"]:
        source = TPS_SOURCES.get(row["tps_source"] or "", "source inconnue")
        rate = _num(row["tps"], "tokens/s")
        cells = [
            row["model"],
            row["origin"] or "inconnue",
            _score_text(row),
            f"{rate} ({source})" if rate else "non mesuré",
            _co2_text(row["co2"]),
            _num(row["load_s"], "s") or "non mesuré",
            _num(row["total_s"], "s") or "non mesuré",
            _stopped_text(row),
        ]
        lines.append("| " + " | ".join(_escape(cell) for cell in cells) + " |")
    lines += ["", "## Preuve de la mesure", ""]
    machine = proof.get("machine") or {}
    accelerator = (machine.get("accelerator") or {}).get("name") or "aucun accélérateur détecté"
    ram = _num(machine.get("ram_gb"), "Go", 0) or "inconnue"
    lines += [
        f"- Machine : {machine.get('os') or 'inconnue'}, {machine.get('cpu') or 'processeur inconnu'}, "
        f"mémoire {ram}, {accelerator}",
        f"- Ollama : version {proof['ollama_version'] or 'inconnue'}",
        "- Digests des modèles : "
        + (
            ", ".join(
                f"{tag} {digest or 'inconnu'}" for tag, digest in proof["model_digests"].items()
            )
            or "aucun"
        ),
        f"- Méthode du CO2 : {', '.join(proof['co2_methods']) or 'aucune mesure'}",
    ]
    judge = proof["judge"]
    lines.append(
        f"- Juge : {judge['model'] or 'aucun juge'}"
        + (f" ({judge['origin']})" if judge["origin"] else "")
        + (", note peu fiable" if judge["unreliable"] else "")
        + (", un seul juge" if judge["single_judge"] else "")
    )
    lines.append(f"- Critères de notation : {', '.join(judge['criteria']) or 'ceux du serveur'}")
    reasons = [row for row in document["models"] if row["reason"]]
    if reasons:
        lines += ["", "## Raisons du juge", ""]
        lines += [f"- {row['model']} : {_escape(row['reason'])}" for row in reasons]
    lines += ["", "## Définitions", ""]
    lines += [f"- **{name}** : {text}" for name, text in DEFINITIONS.items()]
    return "\n".join(lines).rstrip() + "\n"
