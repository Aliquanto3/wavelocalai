"""Rapport Markdown du pilote (CAP-8), en français, produit depuis le seul dictionnaire de
``pilot.build_pilot_report`` : aucun texte de question ni sortie de modèle, aucune date.
Les choix (N, plafonds, K) restent à Anaël : le rapport en donne les éléments, sans décider."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .markdown import (
    DASH,
    NBSP,
    TRACK_LABELS,
    USAGE_LABELS,
    fr_decimal,
    fr_int,
    fr_percent,
)

SCOPE_LABELS = {"global": "Global (usages binaires)", **USAGE_LABELS}
WRITING_STATUS = {
    "provisional": "provisoire (moyenne sur les seules lignes notées)",
    "not_graded": "non notée (aucune ligne de rédaction notée : jugement absent ou en attente)",
}
STEP_LABELS = {
    "caps": "Abaisser les plafonds de tokens",
    "thinking_only": "Piste activée réservée aux modèles thinking",
    "think_on_n": "Ramener le N de la piste activée",
}


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _hours(value: float | None) -> str:
    return DASH if value is None else f"{fr_decimal(value, 1)}{NBSP}h"


def _num(value: float | None, digits: int = 1) -> str:
    return fr_decimal(value, digits)


def _tok(value: float | None) -> str:
    """Nombre de tokens arrondi à l'entier : ``1 215``."""
    return fr_int(None if value is None else round(value))


def _ranking(order: Sequence[str], values: Mapping[str, float | None]) -> str:
    """Ordre rendu ``a > b = c`` : « = » entre deux modèles de même valeur."""
    if not order:
        return DASH
    text = f"`{order[0]}`"
    for previous, model in zip(order, order[1:], strict=False):
        text += f" {'=' if values.get(previous) == values.get(model) else '>'} `{model}`"
    return text


def _scope(name: str) -> str:
    return SCOPE_LABELS.get(name, name)


def _usage(name: str) -> str:
    return USAGE_LABELS.get(name, name)


def _caps_text(caps: Mapping[str, Mapping[str, int]]) -> str:
    parts = []
    for track in ("think_on", "think_off"):
        values = ", ".join(f"{usage} {fr_int(cap)}" for usage, cap in sorted(caps[track].items()))
        parts.append(f"{track} : {values}")
    return " ; ".join(parts)


# -- Sections -------------------------------------------------------------------------------


def _header(report: Mapping[str, Any]) -> list[str]:
    completeness = report["completeness"]
    lines = [
        f"# Rapport du pilote {report['campaign']}",
        "",
        f"Jeu `{report['set']['id']}` (empreinte `{report['set']['hash'][:12]}`), "
        f"k = {report['k']}, modèles : {', '.join(f'`{m}`' for m in report['models'])}. "
        f"Rejeu : `{report['replay_campaign']}`.",
        "",
        "Les choix de N, des plafonds et de K restent à décider : ce rapport en donne les "
        "éléments, sans rien appliquer. La rédaction y est **provisoire**.",
        "",
        "## Complétude",
        "",
    ]
    rows = []
    for label, entry in (("Pilote", completeness["pilot"]), ("Rejeu", completeness["replay"])):
        if entry is None:
            rows.append([label, DASH, DASH, DASH, DASH, DASH, "rejeu absent"])
            continue
        rows.append(
            [
                f"{label} `{entry['campaign']}`",
                fr_int(entry["expected"]),
                fr_int(entry["retained"]),
                fr_int(entry["generation_missing"] + entry["grading_missing"]),
                fr_int(entry["generation_discordant"] + entry["grading_discordant"]),
                fr_int(entry["awaiting_judgment"]),
                "complète" if entry["complete"] else "partielle",
            ]
        )
    lines += _table(
        ["Campagne", "Attendues", "Retenues", "Manquantes", "Discordantes", "En attente", "État"],
        rows,
    )
    return lines + [""]


def _discordance(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "## Discordance entre modèles (ψ)",
        "",
        "ψ = part des unités définies pour les deux modèles où leurs scores diffèrent (usages "
        "binaires). N indicatif : approximation de Connor (1987) pour McNemar, α = 0,05 "
        "bilatéral, puissance 80 %, un peu sous les repères exacts de statistiques.md ; il se "
        "compte en unités (en groupes en présence de groupes). N est donné au ψ moyen et au ψ "
        "maximal des paires.",
        "",
        f"« {DASH} » dans une colonne N : ψ < δ, hors du domaine de l'approximation de Connor.",
        "",
    ]
    for block in report["discordance"]:
        lines += [f"### {TRACK_LABELS[block['track']]}", ""]
        rows = []
        for scope in block["scopes"]:
            n = {entry["delta"]: entry for entry in scope["n_connor"]}
            rows.append(
                [
                    _scope(scope["scope"]),
                    fr_int(scope["units"]),
                    _num(scope["psi_mean"], 3),
                    f"{_num(scope['psi_min'], 3)} – {_num(scope['psi_max'], 3)}",
                    f"{fr_int(n[0.1]['n'])} / {fr_int(n[0.1]['n_psi_max'])}",
                    f"{fr_int(n[0.2]['n'])} / {fr_int(n[0.2]['n_psi_max'])}",
                ]
            )
        lines += _table(
            [
                "Périmètre",
                "Unités",
                "ψ moyen",
                "ψ min – max",
                "N 10 pts (ψ moyen / max)",
                "N 20 pts (ψ moyen / max)",
            ],
            rows,
        )
        lines += [""]
        pair_rows = []
        for scope in block["scopes"]:
            for pair in scope["pairs"]:
                pair_rows.append(
                    [
                        _scope(scope["scope"]),
                        f"`{pair['a']}` / `{pair['b']}`",
                        fr_int(pair["n"]),
                        fr_int(pair["discordant"]),
                        _num(pair["psi"], 3),
                    ]
                )
        lines += _table(["Périmètre", "Paire", "Unités communes", "Discordantes", "ψ"], pair_rows)
        lines += [""]
    return lines


def _ceiling_floor(report: Mapping[str, Any]) -> list[str]:
    settings = report["settings"]
    lines = [
        "## Usages au plafond ou au plancher",
        "",
        f"Plafond : moyenne de chaque modèle ≥ {fr_decimal(settings['ceiling'], 2)} ; plancher : "
        f"≤ {fr_decimal(settings['floor'], 2)}.",
        "",
    ]
    rows = []
    for entry in report["ceiling_floor"]:
        status = {"ceiling": "au plafond", "floor": "au plancher", None: DASH}[entry["status"]]
        rows.append(
            [
                TRACK_LABELS[entry["track"]],
                _usage(entry["usage"]),
                " ; ".join(f"`{m['model']}` {fr_percent(m['mean'])}" for m in entry["means"]),
                status,
                ", ".join(f"`{m}`" for m in entry["at_ceiling"]) or DASH,
                ", ".join(f"`{m}`" for m in entry["at_floor"]) or DASH,
            ]
        )
    lines += _table(
        ["Piste", "Usage", "Moyennes", "Statut", "Modèles ≥ plafond", "Modèles ≤ plancher"], rows
    )
    return lines + [""]


def _stability(report: Mapping[str, Any]) -> list[str]:
    stability = report["stability"]
    lines = ["## Stabilité au rejeu", ""]
    if stability["status"] == "absent":
        return lines + [
            f"Rejeu absent : aucune configuration ou aucun manifeste pour "
            f"`{report['replay_campaign']}`.",
            "",
        ]
    excluded = stability["excluded"]
    lines += [
        f"Rejeu `{stability['campaign']}` : {fr_int(stability['replay_lines'])} lignes, "
        f"{fr_int(stability['joined'])} paires jointes sur (modèle, digest, piste, question, "
        f"seed) à `prompt_hash` égal. Exclues : {fr_int(excluded['unmatched'])} sans "
        f"correspondance au pilote, {fr_int(excluded['digest'])} de digest différent, "
        f"{fr_int(excluded['prompt_hash'])} de `prompt_hash` différent.",
        "",
        "Sorties et scores changés se comptent sur les paires requêtées des deux côtés ; les "
        "paires non requêtées (contexte dépassé, aucun appel) sont comptées à part, comme les "
        "changements de statut. Score changé : deux scores définis différents (usages "
        "binaires ; rédaction à part). Le ratio rapporte ce taux au ψ moyen global de la "
        "piste ; aucune conclusion sur K n'en est tirée ici.",
        "",
    ]
    rows = [
        [
            TRACK_LABELS[t["track"]],
            fr_int(t["joined"]),
            fr_int(t["requested_pairs"]),
            fr_int(t["not_requested"]),
            fr_int(t["status_changed"]),
            f"{fr_int(t['output_changed'])} ({fr_percent(t['output_changed_rate'])})",
            f"{fr_int(t['score_changed'])} / {fr_int(t['scored_pairs'])} "
            f"({fr_percent(t['score_changed_rate'])})",
            _num(t["psi_mean_global"], 3),
            _num(t["ratio_to_psi"], 2),
            f"{fr_int(t['writing_score_changed'])} / {fr_int(t['writing_scored_pairs'])}",
        ]
        for t in stability["tracks"]
    ]
    lines += _table(
        [
            "Piste",
            "Paires",
            "Requêtées",
            "Non requêtées",
            "Statuts changés",
            "Sorties changées",
            "Scores changés",
            "ψ moyen",
            "Ratio",
            "Rédaction changée",
        ],
        rows,
    )
    return lines + [""]


def _describe(stats: Mapping[str, Any]) -> str:
    return f"{_tok(stats['mean'])} / {_tok(stats['p50'])} / {_tok(stats['p90'])} / {_tok(stats['max'])}"


def _tokens(report: Mapping[str, Any]) -> list[str]:
    section = report["tokens"]
    candidates = report["settings"]["candidate_caps"]
    lines = [
        "## Tokens et troncature",
        "",
        f"{fr_int(section['requested_lines'])} lignes requêtées (au moins un appel, statut "
        "`ok` ou `truncated`). Tokens de réflexion estimés (`thinking_est`, issue Ollama "
        "#17843) et de complétion : moyenne / médiane / 90ᵉ centile / maximum. Troncature "
        "projetée d'un plafond candidat : lignes déjà tronquées ou dont la complétion atteint "
        "plafond × appels.",
        "",
    ]
    for index, caps in enumerate(candidates, start=1):
        lines.append(f"- Plafond candidat {index} : {_caps_text(caps)}.")
    lines.append("")
    headers = ["Piste", "Usage", "Lignes", "Réflexion", "Complétion", "Troncature"]
    headers += [f"Candidat {i}" for i in range(1, len(candidates) + 1)]
    rows = []
    for entry in section["by_usage"]:
        row = [
            TRACK_LABELS[entry["track"]],
            _usage(entry["usage"]),
            fr_int(entry["lines"]),
            _describe(entry["thinking_est"]),
            _describe(entry["completion"]),
            fr_percent(entry["truncation_rate"]),
        ]
        row += [
            f"{fr_int(c['cap'])} : {fr_percent(c['projected_truncation'])}"
            for c in entry["candidates"]
        ]
        rows.append(row)
    lines += _table(headers, rows)
    lines += ["", "### Complétion et troncature par modèle et par usage", ""]
    rows = [
        [
            TRACK_LABELS[entry["track"]],
            f"`{entry['model']}`",
            _usage(entry["usage"]),
            fr_int(entry["lines"]),
            _tok(entry["completion_mean"]),
            fr_int(entry["truncated"]),
            fr_percent(entry["truncation_rate"]),
        ]
        for entry in section["by_model"]
    ]
    lines += _table(
        ["Piste", "Modèle", "Usage", "Lignes", "Complétion moyenne", "Tronquées", "Taux"], rows
    )
    return lines + [""]


def _projection(report: Mapping[str, Any]) -> list[str]:
    p = report["projection"]
    lines = [
        "## Projection de durée de la campagne complète",
        "",
        "Formule, par modèle et par piste (jeu entier ; piste activée pour les seuls modèles "
        "`thinking` du catalogue) : f × Σ questions [C̄ / décodage + P̄ / (préremplissage × "
        "deg(palier))] + Σ paliers (chargement + palier/4 / préremplissage). C̄ et P̄ : "
        "moyennes mesurées au pilote par piste et usage (P̄ par palier), tous modèles "
        "confondus ; débits de l'ancien banc.",
        "",
        f"- Surcoût f = {_num(p['overhead']['value'], 3)}"
        + ("" if p["overhead"]["measured"] else " (sans mesure : 1,0)")
        + " (Σ wall_s / Σ durées d'Ollama).",
        f"- Palier de référence : {fr_int(p['reference_tier']) if p['reference_tier'] else DASH}"
        f" (prompt de chauffe le plus proche de {_tok(p['old_bench_prompt_tokens'])} tokens, "
        "médiane de l'ancien banc des modèles du pilote).",
        "",
    ]
    rows = [
        [
            fr_int(d["num_ctx"]),
            _num(d["factor"], 3),
            fr_int(d["models"]) if d["measured"] else "sans mesure (1,0)",
        ]
        for d in p["degradation"]
    ]
    lines += _table(["Palier", "Dégradation du préremplissage", "Modèles mesurés"], rows)
    lines += [""]
    rows = [
        [
            TRACK_LABELS[m["track"]],
            _usage(m["usage"]),
            fr_int(m["lines"]),
            _tok(m["completion_mean"]),
            _tok(m["prompt_mean"]),
        ]
        for m in p["means"]
    ]
    lines += _table(["Piste", "Usage", "Lignes", "C̄ (complétion)", "P̄ (prompt évalué)"], rows)
    lines += [""]
    if p["unmeasured"]:
        lines.append(
            "Usages sans mesure (C̄ = plafond, P̄ = `est_prompt_tokens`) : "
            + " ; ".join(
                f"{TRACK_LABELS[u['track']]}, {_usage(u['usage'])} "
                f"({fr_int(u['questions'])} questions)"
                for u in p["unmeasured"]
            )
            + "."
        )
        lines.append("")
    rows = []
    for m in p["models"]:
        state = "débit connu" if m["known"] else f"débit inconnu ({m['reason']})"
        thinking = DASH if m["thinking"] is None else ("oui" if m["thinking"] else "non")
        rows.append(
            [
                f"`{m['tag']}`",
                thinking,
                _hours(m["think_off_hours"]),
                _hours(m["think_on_hours"]),
                _hours(m["total_hours"]),
                state,
            ]
        )
    lines += _table(["Modèle", "Thinking", "think_off", "think_on", "Total", "État"], rows)
    lines += [
        "",
        f"**Total projeté : {_hours(p['total_hours'])}** (think_off {_hours(p['think_off_hours'])}"
        f", think_on {_hours(p['think_on_hours'])}) pour un budget de "
        f"{_hours(p['budget_hours'])}"
        + (
            ""
            if p["complete"]
            else " ; **total incomplet** : débit inconnu pour au moins un "
            "modèle, compté pour zéro"
        )
        + ".",
        "",
        "### Contrôle sur les questions du pilote",
        "",
        "Même formule, terme des questions seulement (la chauffe n'entre pas dans `wall_s`), "
        "appliquée aux questions requêtées de chaque modèle du pilote et comparée à la durée "
        "murale mesurée. Dernière colonne : durée murale de toutes ses lignes, erreurs et "
        "contextes dépassés compris.",
        "",
    ]
    rows = [
        [
            f"`{c['model']}`",
            TRACK_LABELS[c["track"]],
            fr_int(c["lines"]),
            _hours(c["predicted_hours"]),
            _hours(c["measured_hours"]),
            _num(c["ratio"], 2),
            f"{_hours(c['measured_all_hours'])} ({fr_int(c['all_lines'])} lignes)",
        ]
        for c in p["control"]
    ]
    lines += _table(
        [
            "Modèle",
            "Piste",
            "Lignes requêtées",
            "Prévu",
            "Mesuré",
            "Mesuré / prévu",
            "Mesuré, toutes lignes",
        ],
        rows,
    )
    lines += [""]
    rows = [
        [
            f"`{d['model']}`",
            _num(d["measured_tok_s"], 1),
            _num(d["old_tok_s"], 1),
            _num(d["ratio"], 2),
        ]
        for d in p["decode"]
    ]
    lines += _table(
        ["Modèle", "Décodage mesuré (tok/s)", "Ancien banc (tok/s)", "Mesuré / ancien"], rows
    )
    lines += [""]
    lines += _reduction(p)
    return lines


def _reduction(p: Mapping[str, Any]) -> list[str]:
    reduction = p["reduction"]
    if reduction is None:
        if p["conclusion"] == "undetermined":
            text = (
                "Indéterminé (débits manquants) : le total des seuls modèles à débit connu est "
                "sous le budget, mais il manque des modèles ; aucune conclusion."
            )
        else:
            text = "Projection sous le budget : aucune réduction nécessaire."
        return ["### Réduction", "", text, ""]
    lines = [
        "### Proposition de réduction",
        "",
        "**Proposition seulement, rien n'est appliqué.** Ordre des Constraints de SPEC.md, "
        "étapes cumulées.",
        "",
    ]
    rows = []
    for position, scenario in enumerate(reduction["scenarios"]):
        step = STEP_LABELS[scenario["step"]]
        if scenario["step"] == "caps":
            detail = f"candidat {scenario['index']} : {_caps_text(scenario['caps'])}"
            detail += (
                f" ; troncature projetée {fr_percent(scenario['projected_truncation'])} des "
                "lignes requêtées"
            )
        elif scenario["step"] == "thinking_only":
            detail = (
                f"constat sans effet : {fr_int(scenario['thinking_models'])} modèles thinking en "
                f"piste activée, {fr_int(scenario['non_thinking_models'])} en piste coupée seule"
            )
        else:
            detail = (
                f"{fr_int(scenario['think_on_full'])} → {fr_int(scenario['think_on_n'])} questions "
                "en piste activée"
            )
        flag = " (premier sous le budget)" if reduction["first_under_budget"] == position else ""
        rows.append(
            [
                f"{position + 1}. {step}",
                detail,
                _hours(scenario["think_off_hours"]),
                _hours(scenario["think_on_hours"]),
                _hours(scenario["total_hours"]) + flag,
            ]
        )
    lines += _table(["Étape", "Détail", "think_off", "think_on", "Total"], rows)
    if reduction["first_under_budget"] is None:
        lines += ["", "Aucune étape ne ramène la projection sous le budget."]
    return lines + [""]


def _order(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "## Cohérence d'ordre",
        "",
        "Contrôle de cohérence seulement, sans Spearman ni test (4 modèles) : décompte des "
        "paires de modèles concordantes, discordantes et à égalité. Ancien banc : raisonnement "
        "↔ `reasoning_avg`, consignes ↔ `instruction_following_avg`, outils ↔ "
        "`tool_capability.success_rate`, extraction ↔ `json_capability.schema_compliance_rate`, "
        "abstention ↔ `abstention_avg`, RAG ↔ part des `needle_in_haystack` réussis, global ↔ "
        "moyenne des trois premiers. Le global du pilote porte ici sur les mêmes usages "
        "(raisonnement, consignes, outils), et non sur tous les usages binaires. « = » : "
        "valeurs égales.",
        "",
    ]
    for block in report["order"]:
        lines += [f"### {TRACK_LABELS[block['track']]} : ancien banc", ""]
        rows = [
            [
                (
                    _scope(s["scope"])
                    if s["scope"] != "global"
                    else "Global (raisonnement, consignes, outils)"
                ),
                _ranking(s["pilot_order"], {e["model"]: e["mean"] for e in s["pilot"]}),
                _ranking(s["old_order"], {e["model"]: e["value"] for e in s["old_bench"]}),
                fr_int(s["concordant"]),
                fr_int(s["discordant"]),
                fr_int(s["tied"]),
            ]
            for s in block["scopes"]
        ]
        lines += _table(
            ["Périmètre", "Ordre du pilote", "Ordre de l'ancien banc", "Conc.", "Disc.", "Égal."],
            rows,
        )
        lines += [""]
    aa = report["aa"]
    lines += ["### Indice Artificial Analysis", ""]
    if aa["status"] == "absent":
        return lines + ["Indice AA absent : aucun fichier `aa-*.json` lu.", ""]
    lines += [
        f"Fichier `{aa['path']}` (`sha256` {aa['sha256'][:12]}…). Décompte sur les seules "
        "entrées `measured`, face au score global hors rédaction de la piste appariée.",
        "",
    ]
    rows = [
        [
            TRACK_LABELS[t["track"]],
            t["variant"],
            " ; ".join(
                f"`{e['model']}` {_num(e['index'], 1)} ({e['status']})" for e in t["entries"]
            ),
            _ranking(t["pilot_order"], {e["model"]: e["mean"] for e in t["pilot"]}),
            _ranking(t["aa_order"], {e["model"]: e["index"] for e in t["entries"]}),
            fr_int(t["models"]),
            fr_int(t["concordant"]),
            fr_int(t["discordant"]),
            fr_int(t["tied"]),
        ]
        for t in aa["tracks"]
    ]
    lines += _table(
        [
            "Piste",
            "Variante",
            "Entrées",
            "Ordre du pilote",
            "Ordre AA",
            "Mesurés",
            "Conc.",
            "Disc.",
            "Égal.",
        ],
        rows,
    )
    return lines + [""]


def _writing(report: Mapping[str, Any]) -> list[str]:
    section = report["writing"]
    lines = [
        "## Rédaction (provisoire)",
        "",
        f"Statut : {WRITING_STATUS[section['status']]}. Notes lues dans `grading.jsonl` ; "
        f"{fr_int(section['awaiting_judgment'])} lignes `awaiting_judgment` comptées à part.",
        "",
    ]
    rows = []
    for block in section["tracks"]:
        for entry in block["models"]:
            rows.append(
                [
                    TRACK_LABELS[block["track"]],
                    f"`{entry['model']}`",
                    fr_int(entry["expected"]),
                    fr_int(entry["available"]),
                    fr_int(entry["scored"]),
                    fr_int(entry["awaiting_judgment"]),
                    fr_percent(entry["mean"])
                    + (" (provisoire)" if entry["mean"] is not None else ""),
                ]
            )
    lines += _table(
        ["Piste", "Modèle", "Attendues", "Réponses disponibles", "Notées", "En attente", "Moyenne"],
        rows,
    )
    return lines + [""]


def _deferred(report: Mapping[str, Any]) -> list[str]:
    section = report["deferred"]
    lines = [
        "## Points à trancher au pilote (deferred-work.md)",
        "",
        "### Contexte dépassé (`context_exceeded`)",
        "",
    ]
    rows = [
        [
            TRACK_LABELS[e["track"]],
            f"`{e['model']}`",
            f"`{e['source']}`",
            fr_int(e["lines"]),
            fr_int(e["context_exceeded"]),
            fr_percent(e["rate"]),
        ]
        for e in section["context_exceeded"]["by_source"]
        if e["context_exceeded"] or e["source"] == "bfcl-multi"
    ]
    lines += _table(["Piste", "Modèle", "Source", "Lignes", "Dépassées", "Part"], rows)
    lines += ["", "Sources sans dépassement omises, sauf `bfcl-multi`, toujours montrée.", ""]
    rows = [
        [
            fr_int(e["num_ctx"]),
            fr_int(e["lines"]),
            fr_int(e["context_exceeded"]),
            fr_percent(e["rate"]),
        ]
        for e in section["context_exceeded"]["by_tier"]
    ]
    lines += _table(["Palier", "Lignes", "Dépassées", "Part"], rows)
    lines += [
        "",
        "### Unités non communes et meneur (AD-10)",
        "",
    ]
    rows = [
        [
            TRACK_LABELS[e["track"]],
            _scope(e["scope"]),
            fr_int(e["units"]),
            fr_int(e["non_common_units"]),
            f"`{e['leader_all_units']}`" if e["leader_all_units"] else DASH,
            f"`{e['leader_common_units']}`" if e["leader_common_units"] else DASH,
            (
                "indéterminé (aucune unité commune)"
                if e["same_leader"] is None
                else "oui" if e["same_leader"] else "**non**"
            ),
        ]
        for e in section["common_units"]
    ]
    lines += _table(
        [
            "Piste",
            "Périmètre",
            "Unités",
            "Non communes",
            "Meneur (toutes ses unités)",
            "Meneur (unités communes)",
            "Même meneur",
        ],
        rows,
    )
    lines += ["", "### Reprises non comptées et erreurs", ""]
    rows = [
        [
            f"`{e['campaign']}`",
            "journal absent" if e["log_lines"] is None else fr_int(e["log_lines"]),
            fr_int(e["attempts_over_one"]),
            fr_int(e["error_lines"]),
        ]
        for e in section["retries"]
    ]
    lines += _table(
        [
            "Campagne",
            "« Ollama ne répond plus » au journal",
            "Lignes à attempts > 1",
            "Lignes error",
        ],
        rows,
    )
    lines += [
        "",
        "### Cache de préfixe",
        "",
        "Part des tokens de prompt servis par le cache : Σ `prompt_cached` / Σ (`prompt` + "
        "`prompt_cached`), sur les lignes requêtées.",
        "",
    ]
    rows = [
        [
            TRACK_LABELS[e["track"]],
            _usage(e["usage"]),
            fr_int(e["lines"]),
            fr_int(e["lines_with_cache"]),
            fr_percent(e["cached_share"]),
        ]
        for e in section["prefix_cache"]
    ]
    lines += _table(["Piste", "Usage", "Lignes", "Lignes avec cache", "Part en cache"], rows)
    return lines + [""]


def _decisions(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "## Éléments pour les choix d'Anaël (N, plafonds, K)",
        "",
        "Rien n'est décidé ici.",
        "",
    ]
    stability = {t["track"]: t for t in report["stability"]["tracks"]}
    for block in report["discordance"]:
        track = block["track"]
        scope = next((s for s in block["scopes"] if s["scope"] == "global"), None)
        if scope is None:
            continue
        n = {entry["delta"]: entry["n"] for entry in scope["n_connor"]}
        ratio = stability.get(track, {}).get("ratio_to_psi")
        lines.append(
            f"- {TRACK_LABELS[track]} : ψ moyen global {_num(scope['psi_mean'], 3)}, N indicatif "
            f"{fr_int(n.get(0.1))} unités pour 10 points et {fr_int(n.get(0.2))} pour 20 points ; "
            f"ratio rejeu / ψ {_num(ratio, 2)}."
        )
    reduction = report["projection"]["reduction"]
    if reduction is not None:
        for scenario in reduction["scenarios"]:
            if scenario["step"] == "caps":
                lines.append(
                    f"- Plafond candidat {scenario['index']} : troncature projetée "
                    f"{fr_percent(scenario['projected_truncation'])}, projection "
                    f"{_hours(scenario['total_hours'])}."
                )
    lines.append(
        "- K : comparer le taux de scores changés au rejeu à ψ (statistiques.md, « Tirages »)."
    )
    return lines + [""]


def _references(report: Mapping[str, Any]) -> list[str]:
    refs = report["references"]
    lines = ["## Références lues", ""]
    for label, key in (("Ancien banc", "old_bench"), ("Catalogue", "catalog")):
        lines.append(f"- {label} : `{refs[key]['path']}` (`sha256` {refs[key]['sha256']}).")
    aa = report["aa"]
    if aa["status"] == "absent":
        lines.append("- Indice AA : absent.")
    else:
        lines.append(f"- Indice AA : `{aa['path']}` (`sha256` {aa['sha256']}).")
    settings = refs["settings"]
    lines.append(f"- Réglage du pilote : `{settings['path']}` (`sha256` {settings['sha256']}).")
    lines.append(f"- Manifeste de génération : `{report['generation_manifest']}`.")
    replay = refs["replay_generation_manifest"]
    lines.append(
        f"- Manifeste de génération du rejeu : `{replay}`."
        if replay
        else "- Manifeste de génération du rejeu : rejeu absent."
    )
    return lines + [""]


def render_pilot(report: Mapping[str, Any]) -> str:
    """Rapport Markdown du pilote ; déterministe (aucune date)."""
    lines: list[str] = []
    for section in (
        _header,
        _decisions,
        _discordance,
        _ceiling_floor,
        _stability,
        _tokens,
        _projection,
        _order,
        _writing,
        _deferred,
        _references,
    ):
        lines += section(report)
    return "\n".join(lines).rstrip("\n") + "\n"
