"""Rendus français de la calibration du juge (CAP-6), nombres au format français.

- ``render_calibration`` : ``calibration-report.md`` depuis le seul rapport JSON (aucun texte de
  question ni de réponse, aucune date).
- ``render_labels_todo`` : ``labels-todo-<c>.md``, seul fichier qui contient la consigne, la
  réponse et le critère de chaque item à étiqueter (hors dépôt, sous ``data/``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .markdown import DASH, NBSP, fr_decimal, fr_int, fr_interval, fr_percent, fr_points

STATUS_LABELS = {
    "present": "présent",
    "absent": "absent",
    "discordant": "discordant (autre manifeste de génération) : exclu",
    "computed": "simulée",
    "not_simulable": "non simulable",
}
STABILITY_LABELS = {
    "computed": "mesurée",
    "replay_absent": "rejeu absent",
    "judge_absent": "juge absent",
    "judge_discordant": "juge discordant (exclu)",
    "not_comparable": "rejeu non comparable",
}
NOT_SET = "seuil non fixé"
NO_LABELS = "étiquettes absentes"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _usd(value: float | None, digits: int = 4) -> str:
    return DASH if value is None else f"{fr_decimal(value, digits)}{NBSP}$"


def _label_name(entry_id: str) -> str:
    return f"`{entry_id}`"


def _agreement_cell(block: Mapping[str, Any], labels_used: int) -> str:
    if labels_used == 0:
        return NO_LABELS
    if block["n"] == 0:
        return f"{DASH} (0 étiquette notée)"
    return (
        f"{fr_percent(block['rate'])} {fr_interval(block['ci_low'], block['ci_high'])} "
        f"(n = {fr_int(block['n'])})"
    )


def _bias_cell(block: Mapping[str, Any], labels_used: int) -> str:
    if labels_used == 0:
        return NO_LABELS
    return fr_points(block["bias"])


def _threshold_cell(value: bool | None) -> str:
    if value is None:
        return NOT_SET
    return "oui" if value else "non"


def _header(report: Mapping[str, Any]) -> list[str]:
    units, labels, settings = report["units"], report["labels"], report["settings"]
    lines = [
        f"# Calibration du juge : campagne `{report['campaign']}`",
        "",
        f"Manifeste de génération : `{report['generation_manifest']}`.",
        "",
        f"- Unités jugeables (critères des réponses de rédaction `ok`) : {fr_int(units['total'])}"
        f", dont {fr_int(units['qwen'])} de modèles Qwen et {fr_int(units['non_qwen'])} d'autres "
        f"familles, {fr_int(units['counting'])} critères de comptage ; {fr_int(units['responses'])}"
        f" réponses de {fr_int(units['models'])} modèles.",
        "- Seuil d'accord minimal : "
        + (NOT_SET if settings["min_agreement"] is None else fr_percent(settings["min_agreement"]))
        + " ; biais Qwen maximal : "
        + (
            NOT_SET
            if settings["max_qwen_bias"] is None
            else fr_points(settings["max_qwen_bias"]).lstrip("+")
        )
        + ".",
        f"- Projection du coût sur {fr_int(settings['projected_judgments'])} jugements.",
        "",
        "## Étiquettes",
        "",
    ]
    if not labels["file_present"]:
        lines.append("Étiquettes absentes : `calibration/labels.jsonl` n'existe pas.")
    else:
        lines += [
            f"- Lignes de `calibration/labels.jsonl` : {fr_int(labels['lines'])}.",
            f"- Retenues pour l'accord : {fr_int(labels['used'])} ({fr_int(labels['true'])} "
            f"vraies, {fr_int(labels['false'])} fausses).",
            f"- À étiqueter (`label` nul) : {fr_int(labels['to_label'])} ; indécidables : "
            f"{fr_int(labels['undecidable'])} ; d'autres campagnes : "
            f"{fr_int(labels['other_campaigns'])} (ignorées).",
        ]
        if labels["used"] == 0:
            lines += ["", "Étiquettes absentes : aucune étiquette vraie ou fausse à comparer."]
    return lines


def _judges(report: Mapping[str, Any]) -> list[str]:
    lines = ["", "## Dossiers de jugement", ""]
    if not report["judges"]:
        return lines + ["Aucun dossier `judgment-<id>/`."]
    rows = [
        [
            _label_name(j["id"]),
            STATUS_LABELS[j["status"]],
            fr_int(j["lines"]),
            fr_int(j["collected_batches"]),
            DASH if j["manifest"] is None else f"`{j['manifest'][:12]}`",
        ]
        for j in report["judges"]
    ]
    return lines + _table(["Juge", "Statut", "Lignes", "Lots relevés", "Manifeste"], rows)


def _configurations(report: Mapping[str, Any]) -> list[str]:
    used = report["labels"]["used"]
    lines = [
        "",
        "## Configurations",
        "",
        "Accord sur les unités étiquetées vraies ou fausses que la configuration a notées d'un "
        "verdict booléen, intervalle de Wilson à 95 %. Biais Qwen = accord sur les réponses de "
        "modèles Qwen − accord sur les autres. La cascade se lit par marge (section suivante). "
        "L'accord est calculé sans pondération sur l'échantillon étiqueté (stratifié : moitié "
        "Qwen, parts égales par modèle) : ce n'est pas une estimation pour toute la campagne.",
        "",
    ]
    headers = [
        "Configuration",
        "Statut",
        "Couverture",
        "Erreurs",
        "Coût total",
        "Coût projeté",
        "Accord",
        "Biais Qwen",
        "Accord (comptage)",
        "Accord ≥ seuil",
        "Biais ≤ seuil",
    ]
    rows = []
    for entry in report["configurations"]:
        if entry["kind"] == "cascade":
            margins = report["cascade"]["margins"]
            note = (
                f"{fr_int(len(margins))} marges, voir « Cascade »"
                if entry["status"] == "computed"
                else STATUS_LABELS[entry["status"]]
            )
            rows.append([_label_name(entry["id"]), note] + [DASH] * (len(headers) - 2))
            continue
        if entry["status"] != "present":
            rows.append(
                [_label_name(entry["id"]), STATUS_LABELS[entry["status"]]]
                + [DASH] * (len(headers) - 2)
            )
            continue
        cov, cost, adm = entry["coverage"], entry["cost"], entry["admissibility"]
        rows.append(
            [
                _label_name(entry["id"]),
                STATUS_LABELS["present"],
                f"{fr_int(cov['lines'])}/{fr_int(cov['units'])} ({fr_percent(cov['share'])})",
                fr_int(cov["errors"]),
                _usd(cost["total_usd"]),
                _usd(cost["projected_usd"], 2),
                _agreement_cell(entry["agreement"], used),
                _bias_cell(entry["qwen_bias"], used),
                _agreement_cell(entry["counting"]["counting"], used),
                _threshold_cell(adm["agreement"]),
                _threshold_cell(adm["qwen_bias"]),
            ]
        )
    return lines + _table(headers, rows)


def _detail_rows(entry_id: str, block: Mapping[str, Any]) -> list[list[str]]:
    rows = []
    agreement = block["agreement"]
    groups = (
        ("toutes", agreement),
        ("Qwen", block["qwen_bias"]["qwen"]),
        ("non-Qwen", block["qwen_bias"]["non_qwen"]),
        ("comptage", block["counting"]["counting"]),
        ("hors comptage", block["counting"]["other"]),
    )
    for name, item in groups:
        rows.append(
            [
                _label_name(entry_id),
                name,
                fr_int(item["labeled"]),
                fr_int(item["n"]),
                fr_percent(item["rate"]),
                fr_interval(item["ci_low"], item["ci_high"]),
                f"{fr_int(item['lenient'])} ({fr_percent(item['lenient_rate'])})",
                f"{fr_int(item['severe'])} ({fr_percent(item['severe_rate'])})",
                fr_int(item["labeled_without_line"]),
                fr_int(item["labeled_error"]),
            ]
        )
    return rows


def _details(report: Mapping[str, Any]) -> list[str]:
    lines = ["", "## Détail de l'accord", ""]
    if report["labels"]["used"] == 0:
        return lines + [f"{NO_LABELS[0].upper()}{NO_LABELS[1:]} : accord non mesuré."]
    lines += [
        "Indulgence : juge vrai, humain faux. Sévérité : juge faux, humain vrai. Parts sur "
        "les unités mesurées.",
        "",
    ]
    rows = []
    for entry in report["configurations"]:
        if entry["kind"] == "judge" and entry["status"] == "present":
            rows += _detail_rows(entry["id"], entry)
    for entry in report["cascade"]["margins"]:
        rows += _detail_rows(entry["id"], entry)
    headers = [
        "Configuration",
        "Groupe",
        "Étiquetées",
        "Mesurées",
        "Accord",
        "IC 95 %",
        "Indulgence",
        "Sévérité",
        "Sans ligne",
        "En erreur",
    ]
    return lines + _table(headers, rows)


def _cascade(report: Mapping[str, Any]) -> list[str]:
    section = report["cascade"]
    used = report["labels"]["used"]
    lines = ["", "## Cascade Winnow → Haiku", ""]
    if section["status"] != "computed":
        missing = ", ".join(f"`{j}`" for j in section["missing"])
        return lines + [f"Cascade non simulable : juge absent ou exclu ({missing})."]
    lines += [
        "Simulée hors ligne : probabilité de Winnow ≥ borne haute → vrai, ≤ borne basse → "
        "faux, sinon (ou ligne en erreur, ou probabilité nulle) verdict de Haiku de la même "
        "clé. Coût = coût par jugement de Haiku × escaladées. Aucune entrée n'est ajoutée à "
        "`judges.yaml`.",
        "",
    ]
    headers = [
        "Identifiant",
        "Marge",
        "Escaladées",
        "Sans Haiku",
        "Coût",
        "Coût projeté",
        "Accord",
        "Biais Qwen",
        "Accord (comptage)",
        "Accord ≥ seuil",
        "Biais ≤ seuil",
    ]
    rows = []
    for entry in section["margins"]:
        adm = entry["admissibility"]
        rows.append(
            [
                _label_name(entry["id"]),
                fr_decimal(entry["margin"], 2),
                f"{fr_int(entry['escalated'])}/{fr_int(entry['winnow_lines'])} "
                f"({fr_percent(entry['escalated_share'])})",
                fr_int(entry["escalated_without_haiku"]),
                _usd(entry["cost"]["total_usd"]),
                _usd(entry["cost"]["projected_usd"], 2),
                _agreement_cell(entry["agreement"], used),
                _bias_cell(entry["qwen_bias"], used),
                _agreement_cell(entry["counting"]["counting"], used),
                _threshold_cell(adm["agreement"]),
                _threshold_cell(adm["qwen_bias"]),
            ]
        )
    return lines + _table(headers, rows)


def _stability(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "",
        "## Stabilité au rejeu",
        "",
        "Paire `<id>` / `<id>-replay` comparable si point d'accès, modèle, réglages, gabarit, "
        "poids, version du serveur et manifeste de génération sont égaux ; verdicts booléens "
        "des deux côtés.",
        "",
    ]
    if not report["stability"]:
        return lines + ["Aucun juge présent."]
    rows = []
    for entry in report["stability"]:
        status = STABILITY_LABELS[entry["status"]]
        if entry["field"] is not None:
            status += f" (champ `{entry['field']}`)"
        computed = entry["status"] == "computed"
        rows.append(
            [
                _label_name(entry["judge"]),
                _label_name(entry["replay"]),
                status,
                fr_int(entry["n"]) if computed else DASH,
                fr_percent(entry["rate"]) if computed else DASH,
                fr_interval(entry["ci_low"], entry["ci_high"]) if computed else DASH,
                (
                    f"{fr_int(entry['changed'])} (vrai → faux {fr_int(entry['true_to_false'])}, "
                    f"faux → vrai {fr_int(entry['false_to_true'])})"
                    if computed
                    else DASH
                ),
                fr_int(entry["judge_only"]) if computed else DASH,
                fr_int(entry["replay_only"]) if computed else DASH,
            ]
        )
    headers = [
        "Juge",
        "Rejeu",
        "Statut",
        "Clés",
        "Identiques",
        "IC 95 %",
        "Changements",
        "Juge seul",
        "Rejeu seul",
    ]
    return lines + _table(headers, rows)


def _proposal(report: Mapping[str, Any]) -> list[str]:
    lines = ["", "## Proposition", ""]
    proposal = report["proposal"]
    if proposal is None:
        return lines + [
            f"Aucune recommandation : {NOT_SET} (`--min-agreement` et `--max-qwen-bias` sont "
            "à fournir tous les deux). Le choix du juge revient à Anaël."
        ]
    if proposal["status"] != "proposed":
        reason = (
            NO_LABELS
            if report["labels"]["used"] == 0
            else "aucune configuration n'atteint " "les deux seuils"
        )
        return lines + [f"Aucune configuration admissible ({reason})."]
    admissible = ", ".join(_label_name(c) for c in proposal["admissible"])
    return lines + [
        f"Configurations admissibles : {admissible}.",
        "",
        f"Proposition (accord maximal, puis coût projeté minimal) : "
        f"{_label_name(proposal['id'])}, accord {fr_percent(proposal['agreement'])}, biais Qwen "
        f"{fr_points(proposal['qwen_bias'])}, coût projeté {_usd(proposal['projected_usd'], 2)}.",
        "",
        "C'est une proposition, jamais un choix appliqué : le juge retenu se consigne à la main "
        "dans `grading.judge` du YAML de campagne.",
    ]


def render_calibration(report: Mapping[str, Any]) -> str:
    lines = [
        *_header(report),
        *_judges(report),
        *_configurations(report),
        *_details(report),
        *_cascade(report),
        *_stability(report),
        *_proposal(report),
    ]
    return "\n".join(lines) + "\n"


# -- Échantillon à étiqueter ----------------------------------------------------------------


def _fence(text: str) -> str:
    """Bloc de code dont la clôture est plus longue que toute suite d'accents graves du texte
    (même règle que ``questions/review.py``)."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


TRACK_NAMES = {"think_off": "sans réflexion (think_off)", "think_on": "avec réflexion (think_on)"}


def render_labels_todo(campaign: str, items: Sequence[Mapping[str, Any]]) -> str:
    """Consigne courte, puis chaque item : numéro (= rang de la ligne de
    ``labels-todo-<c>.jsonl``), question, piste, critère, consigne et réponse ; ni modèle ni
    clé."""
    lines = [
        f"# Critères à étiqueter : campagne `{campaign}`",
        "",
        "Pour chaque item, lire la consigne et la réponse, puis décider si la réponse, telle "
        "qu'elle est écrite, satisfait le critère. Reporter la décision dans la ligne de même "
        "rang de `labels-todo-" + campaign + ".jsonl` (item 1 = ligne 1 de ce fichier-là) :",
        "",
        '- `"label"` : `true`, `false` ou `"undecidable"` (laisser `null` pour plus tard) ;',
        '- `"author"` : votre nom ; `"labeled_at"` : la date (`AAAA-MM-JJ`) ;',
        '- `"note"` : remarque facultative (sinon `null`).',
        "",
        "Une fois rempli, **ajouter** ses lignes à la fin de `calibration/labels.jsonl` (le "
        "créer s'il est absent), sans jamais le remplacer : il garde les étiquettes des autres "
        "campagnes et des tirages précédents. Fichier en UTF-8 sans BOM, une ligne par "
        "étiquette, chaque ligne terminée par un retour à la ligne, la dernière comprise. Ce "
        "fichier contient des réponses de modèles : il reste sous `data/`, hors dépôt.",
    ]
    for item in items:
        lines += [
            "",
            f"## Item {item['number']}",
            "",
            f"- Question : `{item['question_id']}`",
            f"- Piste : {TRACK_NAMES.get(item['track'], item['track'])}",
            f"- Critère `{item['criterion']}` : {item['criterion_question']}",
            "",
            "**Consigne**",
            "",
            _fence(item["instruction"]),
            "",
            "**Réponse**",
            "",
            _fence(item["answer"]),
        ]
    return "\n".join(lines) + "\n"
