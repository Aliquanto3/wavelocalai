"""Campagnes synthétiques pour la commande ``report`` (AD-17) : jeu, manifeste, génération,
correction et manifeste du juge, sans Ollama ni correcteur réel."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.quality_bench.common import config, paths
from scripts.quality_bench.common.canonical import pretty_bytes, sha256_hex
from scripts.quality_bench.common.jsonl import rewrite_jsonl
from scripts.quality_bench.common.manifest import blocking_hash
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.common.selection import selected_ids
from scripts.quality_bench.questions.schema import set_hash

from .factories import JUDGE, generation_record, manifest, model_resolved, question

CAMPAIGN = "report-test"
SET_ID = "small-report"
JUDGE_ID = "haiku"
# Textes témoins : ils ne doivent jamais sortir dans un export ni dans le journal.
SECRET_QUESTION = "Énoncé confidentiel témoin 7f3a"
SECRET_OUTPUT = "Réponse confidentielle témoin 9b2c"
PROFILES = (0.85, 0.6, 0.3, 0.75, 0.5, 0.45, 0.65, 0.2, 0.55, 0.4)


@dataclass
class Synthetic:
    config_dir: Path
    manifest: dict[str, Any]
    generation_hash: str
    judgment_hash: str
    questions: dict[str, dict[str, Any]]
    tracks: dict[str, list[str]]
    generation: list[dict[str, Any]]
    grading: list[dict[str, Any]]
    models: list[str]
    k: int
    scores: dict[str, float | None] = field(default_factory=dict)  # clé → score
    campaign: str = CAMPAIGN

    def write_generation(self, lines=None) -> None:
        path = paths.generation_path(self.campaign)
        rewrite_jsonl(path, self.generation if lines is None else lines)

    def write_grading(self, lines=None) -> None:
        rewrite_jsonl(paths.grading_path(self.campaign), self.grading if lines is None else lines)


def _question(qid: str, usage: str, group: str, unit: str, grader: str) -> dict[str, Any]:
    criteria = None
    if usage == "writing":
        criteria = [
            {"id": f"c{i}", "question": "Le texte reste-t-il en français ?"} for i in (1, 2)
        ]
    return question(
        id=qid,
        usage=usage,
        group=group,
        unit=unit,
        grader={"name": grader, "params": {}},
        messages=[{"role": "user", "content": f"{SECRET_QUESTION} ({qid})"}],
        criteria=criteria,
        target=None if usage == "writing" else "4",
    )


def build_set(small: bool = False) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Jeu synthétique : raisonnement (dont une unité VAR-MATH de trois variantes, groupes de
    deux unités), consignes, RAG (dont deux NIAH sans ``f1``), rédaction ; ``small`` : du
    raisonnement seulement."""
    items: list[dict[str, Any]] = []
    for u in range(12 if small else 24):
        unit = f"reasoning/var-math/{u:04d}"
        variants = 3 if u == 0 else 1
        for v in range(variants):
            qid = unit if v == 0 else f"{unit}-v{v}"
            items.append(_question(qid, "reasoning", f"var-math/g{u // 2}", unit, "exact_answer"))
    if not small:
        for i in range(16):
            qid = f"instructions/ifbench/{i:04d}"
            items.append(_question(qid, "instructions", f"ifbench/{i}", qid, "ifbench"))
        for i in range(18):
            source = "piaf" if i < 16 else "oneruler-fr-niah"
            qid = f"rag/{source}/{i:04d}"
            grader = "squad_f1" if i < 16 else "oneruler_niah"
            items.append(_question(qid, "rag", f"{source}/{i // 3}", qid, grader))
        for i in range(8):
            qid = f"writing/writing-fr/{i:04d}"
            items.append(_question(qid, "writing", f"writing-fr/{i}", qid, "judge_criteria"))
    questions = {q["id"]: q for q in items}
    ids = sorted(questions)
    think_on = [
        qid
        for qid in ids
        if (qid.startswith("reasoning/") and int(qid.split("/")[2][:4]) < 10)
        or (qid.startswith("writing/") and int(qid.split("/")[2]) < 4)
    ]
    return questions, {"think_off": ids, "think_on": think_on}


def _draw(model: str, track: str, qid: str, seed: int) -> float:
    return random.Random(sha256_hex([model, track, qid, seed])).random()


def grade_for(
    q: Mapping[str, Any], model: str, profile: float, track: str, seed: int, status: str
) -> tuple[float | None, bool | None, dict[str, float]]:
    """(score, success, metrics) synthétiques d'une question."""
    usage = q["usage"]
    writing = usage == "writing"
    if status in ("error", "context_exceeded", "awaiting_judgment"):
        return None, None, {}
    if status in ("truncated", "non_compliant"):
        metrics = {"f1": 0.0} if status == "non_compliant" and usage == "rag" else {}
        return 0.0, None if writing else False, metrics
    r = _draw(model, track, q["id"], seed)
    if writing:
        score = min(1.0, max(0.0, round((profile + (r - 0.5) * 0.6) * 4) / 4))
        return score, None, {"inline_thinking": 0.0}
    success = r < profile
    metrics: dict[str, float] = {"inline_thinking": 0.0}
    if usage == "instructions":
        metrics["instructions_followed"] = 1.0 if success else round(r * 0.8, 3)
    if usage == "rag" and "niah" not in q["id"]:
        metrics["f1"] = 1.0 if success else round(r * 0.5, 3)
    return (1.0 if success else 0.0), success, metrics


def make_campaign(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    n_models: int = 3,
    k: int = 1,
    small: bool = False,
    statuses: Mapping[tuple[int, str, str, int], str] | None = None,
    think_off_only: tuple[int, ...] = (2,),
    selection: Mapping[str, Any] | None = None,
    campaign: str = CAMPAIGN,
    set_id: str = SET_ID,
) -> Synthetic:
    """Campagne complète écrite sous ``$QUALITY_BENCH_DATA`` ; ``statuses`` : (indice du
    modèle, piste, question, seed) → statut de correction particulier ; ``selection`` :
    section ``generation.selection`` (lignes écrites pour les seules questions du plan) ;
    ``campaign`` : identifiant (pilote et rejeu dans le même ``$QUALITY_BENCH_DATA``) ;
    ``set_id`` : jeu écrit et cité (un autre jeu pour un rejeu discordant)."""
    statuses = dict(statuses or {})
    questions, tracks = build_set(small)
    question_list = [questions[qid] for qid in sorted(questions)]
    rewrite_jsonl(paths.set_questions_path(set_id), question_list)
    path = paths.set_tracks_path(set_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_bytes(tracks))

    resolved_models = []
    yaml_models = []
    for index in range(n_models):
        model = model_resolved(index)
        if index in think_off_only:
            model["tracks"] = ["think_off"]
        resolved_models.append(model)
        tracks_yaml = ", ".join(model["tracks"])
        yaml_models.append(
            f'    - {{tag: "{model["tag"]}", family: qwen, tracks: [{tracks_yaml}], '
            "think_off: false, think_on: true, num_ctx_max: 32768}"
        )
    config_dir = tmp_path / "campaigns_yaml"
    config_dir.mkdir(exist_ok=True)
    yaml_text = (
        f"set: {set_id}\ngeneration:\n  request: {{temperature: 0, seed_base: 0, k: {k}}}\n"
        + ("" if selection is None else f"  selection: {json.dumps(selection)}\n")
        + "  models:\n"
        + "\n".join(yaml_models)
        + f"\ngrading:\n  judge: {JUDGE_ID}\n"
    )
    (config_dir / f"{campaign}.yaml").write_text(yaml_text, encoding="utf-8")
    monkeypatch.setattr(paths, "campaign_config_path", lambda c: config_dir / f"{c}.yaml")
    campaign_config = config.load_campaign(config_dir / f"{campaign}.yaml")
    # Plan du runner : même résolution de la sélection que generate et report.
    selected = selected_ids(
        campaign_config.generation["selection"], questions, tracks["think_off"], tracks["think_on"]
    )

    generation_manifest = manifest(campaign=campaign)
    generation_manifest["blocking"]["set"] = {
        "id": set_id,
        "hash": set_hash(question_list, tracks),
        "n": {track: len(tracks[track]) for track in tracks},
    }
    generation_manifest["blocking"]["generation"] = {
        "hash": campaign_config.generation_hash,
        "resolved": campaign_config.generation,
    }
    generation_manifest["blocking"]["models_resolved"] = resolved_models
    validate(generation_manifest)
    _write_json(paths.generation_manifest_path(campaign), generation_manifest)
    generation_hash = blocking_hash(generation_manifest)

    judgment_manifest = manifest(campaign=campaign, phase="judgment")
    judgment_manifest["blocking"]["judge"] = dict(JUDGE)
    judgment_manifest["blocking"]["generation_manifest"] = generation_hash
    validate(judgment_manifest)
    _write_json(paths.judgment_manifest_path(campaign, JUDGE_ID), judgment_manifest)
    judgment_hash = blocking_hash(judgment_manifest)

    generation, grading, scores = [], [], {}
    for index, model in enumerate(resolved_models):
        tag = model["tag"]
        for track in ("think_off", "think_on"):
            if track not in model["tracks"]:
                continue
            for qid in tracks[track]:
                if selected is not None and qid not in selected:
                    continue
                q = questions[qid]
                for epoch in range(k):
                    seed = epoch
                    status = statuses.get((index, track, qid, seed), "ok")
                    key = f"{campaign}|{tag}|{track}|{qid}|{seed}"
                    gen_status = (
                        status if status in ("truncated", "context_exceeded", "error") else "ok"
                    )
                    generation.append(
                        generation_record(
                            key=key,
                            manifest=generation_hash,
                            campaign=campaign,
                            model=tag,
                            digest=model["digest"],
                            track=track,
                            question_id=qid,
                            usage=q["usage"],
                            group=q["group"],
                            unit=q["unit"],
                            prompt_hash=q["prompt_hash"],
                            seed=seed,
                            epoch=epoch,
                            status=gen_status,
                            output=[
                                {
                                    "turn": 0,
                                    "role": "assistant",
                                    "content": SECRET_OUTPUT,
                                    "thinking": None,
                                    "tool_calls": [],
                                }
                            ],
                        )
                    )
                    score, success, metrics = grade_for(
                        q, tag, PROFILES[index], track, seed, status
                    )
                    writing = q["usage"] == "writing"
                    grading.append(
                        {
                            "schema": "qb.grading/1",
                            "key": key,
                            "generation_manifest": generation_hash,
                            "judgment_manifest": (
                                judgment_hash if writing and status == "ok" else None
                            ),
                            "grader": f"{q['grader']['name']}@1",
                            "status": status,
                            "score": score,
                            "success": success,
                            "metrics": metrics,
                        }
                    )
                    scores[key] = score
    synthetic = Synthetic(
        config_dir=config_dir,
        manifest=generation_manifest,
        generation_hash=generation_hash,
        judgment_hash=judgment_hash,
        questions=questions,
        tracks=tracks,
        generation=generation,
        grading=sorted(grading, key=lambda r: r["key"]),
        models=[m["tag"] for m in resolved_models],
        k=k,
        scores=scores,
        campaign=campaign,
    )
    for record in synthetic.grading:
        validate(record)
    synthetic.write_generation()
    synthetic.write_grading()
    return synthetic


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pretty_bytes(obj))


def aa_reference(date: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "qb.aa_reference/1",
        "date": date,
        "source": "Artificial Analysis (test)",
        "entries": entries,
    }


def write_aa_reference(document: Mapping[str, Any], name: str | None = None) -> Path:
    path = paths.references_dir() / (name or f"aa-{document['date']}.json")
    _write_json(path, dict(document))
    return path
