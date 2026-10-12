"""Exports versionnés d'une campagne (AD-2, AD-6) : ``benchmarks/quality/<c>/`` réécrit en
entier, en liste blanche, sans date, octets identiques d'une passe à l'autre.

- ``scores/<modèle>.jsonl`` : une ligne ``qb.score/1`` par ligne retenue, triée par (piste,
  ``question_hash``, seed) ; ni texte ni identifiant de question ;
- ``summary.json`` : résumé ``qb.report/1`` ;
- ``manifest.json`` : copie du manifeste de génération, une sélection ``ids`` réduite à son
  effectif et à son empreinte ;
- ``report.md`` et ``charts/*.svg`` : produits depuis le résumé seul.

Chaque enregistrement est validé par ``common/schemas.py`` avant écriture. Tous les octets sont
produits en mémoire avant la moindre écriture ; le dossier est assemblé à côté puis mis en place
par renommage : un échec laisse l'ancien dossier intact.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..common import paths
from ..common.canonical import canonical_bytes, pretty_bytes, sha256_hex
from ..common.schemas import validate
from .inputs import CampaignInputs, ReportError

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def model_file_name(tag: str) -> str:
    """Nom de fichier d'un modèle : caractère hors ``[A-Za-z0-9._-]`` remplacé par ``_``."""
    return _UNSAFE_RE.sub("_", tag) + ".jsonl"


def _checked(record: Mapping[str, Any], expected: str) -> Mapping[str, Any]:
    name = validate(record)
    if name != expected:
        raise ReportError(f"export : schéma {name} au lieu de {expected}")
    return record


def exported_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Copie du manifeste de génération publiée : une sélection ``{ids: [...]}`` (des
    ``question_id``) y devient ``{ids_count, ids_sha256}`` (empreinte des ids triés) ; le
    manifeste lu n'est pas modifié."""
    exported = copy.deepcopy(dict(manifest))
    resolved = exported["blocking"]["generation"]["resolved"]
    selection = resolved.get("selection") if isinstance(resolved, dict) else None
    if isinstance(selection, dict) and "ids" in selection:
        ids = sorted(selection["ids"])
        resolved["selection"] = {"ids_count": len(ids), "ids_sha256": sha256_hex(ids)}
    return exported


def score_files(inputs: CampaignInputs) -> dict[str, bytes]:
    """``scores/<modèle>.jsonl`` de chaque modèle du manifeste (``ReportError`` si deux modèles
    donnent le même nom de fichier)."""
    names: dict[str, str] = {}
    for model in inputs.models:
        name = model_file_name(model["tag"])
        # Insensible à la casse : sous NTFS, « M.jsonl » et « m.jsonl » sont un même fichier.
        if name.casefold() in {other.casefold() for other in names.values()}:
            raise ReportError(f"modèles {model['tag']} et d'autres : même fichier de scores {name}")
        names[model["tag"]] = name
    by_model: dict[str, list[dict[str, Any]]] = {tag: [] for tag in names}
    for row in inputs.rows.values():
        record = {
            "schema": "qb.score/1",
            "question_hash": inputs.questions[row.question_id]["question_hash"],
            "model": row.model,
            "digest": row.digest,
            "track": row.track,
            "seed": row.seed,
            "status": row.status,
            "score": row.score,
            "success": row.success,
            "metrics": dict(row.metrics),
        }
        by_model[row.model].append(dict(_checked(record, "qb.score/1")))
    files = {}
    for tag, records in by_model.items():
        records.sort(key=lambda r: (r["track"], r["question_hash"], r["seed"]))
        files[f"scores/{names[tag]}"] = b"".join(canonical_bytes(r) + b"\n" for r in records)
    return files


def export_files(
    inputs: CampaignInputs,
    summary: Mapping[str, Any],
    report_md: str,
    charts: Mapping[str, str],
) -> dict[str, bytes]:
    """Tous les fichiers du dossier d'export, chemin relatif → octets (validés)."""
    files = score_files(inputs)
    files["summary.json"] = pretty_bytes(dict(_checked(summary, "qb.report/1")))
    exported = _checked(exported_manifest(inputs.manifest), "qb.manifest/1")
    files["manifest.json"] = pretty_bytes(dict(exported))
    files["report.md"] = report_md.encode("utf-8")
    for name, svg in charts.items():
        files[f"charts/{name}"] = svg.encode("utf-8")
    return files


def write_export_dir(campaign: str, files: Mapping[str, bytes]) -> Path:
    """Remplace ``benchmarks/quality/<c>/`` par ``files`` : dossier assemblé à côté
    (``.<c>.tmp``), puis mis en place par renommage ; l'ancien dossier est supprimé ensuite."""
    target = paths.campaign_exports_dir(campaign)
    staging = target.with_name(f".{target.name}.tmp")
    retired = target.with_name(f".{target.name}.old")
    for leftover in (staging, retired):
        if leftover.exists():
            shutil.rmtree(leftover)
    try:
        for relative in sorted(files):
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(files[relative])
                handle.flush()
                os.fsync(handle.fileno())
        if target.exists():
            os.replace(target, retired)
        try:
            os.replace(staging, target)
        except OSError:
            if retired.exists() and not target.exists():
                os.replace(retired, target)  # l'ancien dossier reste en place
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    if retired.exists():
        shutil.rmtree(retired)
    return target
