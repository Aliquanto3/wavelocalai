"""Rapport Markdown en français (AD-6) : produit depuis le résumé ``qb.report/1`` seul, sans
texte de question, sortie de modèle ni identifiant de question. Nombres au format français."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

NBSP = " "
NNBSP = " "
DASH = "—"
TRACK_LABELS = {
    "think_off": "Piste sans réflexion (think_off)",
    "think_on": "Piste avec réflexion (think_on)",
}
USAGE_LABELS = {
    "reasoning": "Raisonnement",
    "instructions": "Suivi de consignes",
    "tools": "Appels d'outils",
    "extraction": "Extraction structurée",
    "rag": "Questions sur documents (RAG)",
    "abstention": "Abstention",
    "writing": "Rédaction",
}
METHOD_LABELS = {
    "mcnemar": "McNemar exact apparié, intervalle de Wilson",
    "paired_z": (
        "test z sur la différence appariée (erreur-type groupée), intervalle moyenne ± z·ET, "
        "IC bootstrap apparié de la différence"
    ),
}
METRIC_LABELS = {"instructions_followed": "part de consignes suivies", "f1": "F1"}
CONCLUSION_LABELS = {
    "inconclusive": "sans conclusion (moins de 8 modèles mesurés)",
    "investigate": "ρ négatif : enquête nécessaire",
    "concordant": "concordant (ρ significativement positif)",
    "not_significant": "non significatif (ne disqualifie pas le banc)",
}
VARIANT_LABELS = {"reasoning": "en raisonnement", "non_reasoning": "sans raisonnement"}


# -- Nombres au format français -------------------------------------------------------------


def fr_decimal(value: float | None, digits: int = 3) -> str:
    """``0,624`` ; ``—`` si indéfini."""
    if value is None:
        return DASH
    text = f"{value:.{digits}f}"
    if text.startswith("-") and float(text) == 0:
        text = text[1:]
    return text.replace("-", "−").replace(".", ",")


def fr_percent(value: float | None, digits: int = 1) -> str:
    """``62,4 %`` (espace insécable) ; ``—`` si indéfini."""
    if value is None:
        return DASH
    return f"{fr_decimal(value * 100, digits)}{NBSP}%"


def fr_points(value: float | None, digits: int = 1) -> str:
    """Différence en points de pourcentage, signée : ``+12,5 pts``."""
    if value is None:
        return DASH
    text = fr_decimal(value * 100, digits)
    if not text.startswith("−") and text.strip("0,") != "":
        text = "+" + text
    return f"{text}{NBSP}pts"


def fr_int(value: int | None) -> str:
    """Entier à espace fine insécable : ``12 345``."""
    if value is None:
        return DASH
    return f"{value:,}".replace(",", NNBSP)


def fr_pvalue(value: float | None) -> str:
    if value is None:
        return DASH
    if value < 0.001:
        return f"<{NBSP}0,001"
    return fr_decimal(value, 3)


def fr_interval(low: float | None, high: float | None, *, points: bool = False) -> str:
    if low is None or high is None:
        return DASH
    if points:
        return f"[{fr_points(low)} ; {fr_points(high)}]"
    return f"[{fr_percent(low)} ; {fr_percent(high)}]"


def scope_title(track: str, usage: str | None) -> str:
    where = "score global" if usage is None else USAGE_LABELS[usage].lower()
    return f"{TRACK_LABELS[track]} : {where}"


def chart_name(track: str, usage: str | None) -> str:
    return f"{track}-{usage or 'global'}.svg"


# -- Tableaux -------------------------------------------------------------------------------


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _models_table(scope: Mapping[str, Any]) -> list[str]:
    entries = sorted(
        scope["models"],
        key=lambda e: (e["group"] is None, e["group"] or 0, -(e["mean"] or 0.0)),
    )
    rows = [
        [
            DASH if e["group"] is None else str(e["group"]),
            DASH if e["rank"] is None else str(e["rank"]),
            f"`{e['model']}`",
            fr_percent(e["mean"]),
            fr_interval(e["ci_low"], e["ci_high"]),
            fr_interval(e["sim_ci_low"], e["sim_ci_high"]),
            fr_decimal(e["se"], 3),
            fr_int(e["n"]),
            fr_int(e["excluded"]),
            f"{fr_percent(e['truncation_rate'])} ({fr_int(e['truncated'])}/{fr_int(e['graded'])})",
        ]
        for e in entries
    ]
    headers = [
        "Groupe",
        "Rang",
        "Modèle",
        "Score",
        "IC 95 %",
        "IC simultané",
        "ET groupée",
        "Unités",
        "Exclues",
        "Troncature",
    ]
    return _table(headers, rows)


def _comparisons_table(scope: Mapping[str, Any]) -> list[str]:
    binary = scope["method"] == "mcnemar"
    headers = ["Modèle", "Unités", "Différence", "ET appariée", "IC 95 %"]
    headers += ["b", "c"] if binary else ["IC bootstrap"]
    headers += ["Corrélation", "p", "p (Holm)", "Distingué"]
    rows = []
    for c in scope["comparisons"]:
        row = [
            f"`{c['model']}`",
            fr_int(c["n"]),
            fr_points(c["diff"]),
            fr_decimal(c["se"], 3),
            fr_interval(c["ci_low"], c["ci_high"], points=True),
        ]
        if binary:
            row += [fr_int(c["b"]), fr_int(c["c"])]
        else:
            row += [fr_interval(c["bootstrap_ci_low"], c["bootstrap_ci_high"], points=True)]
        row += [
            fr_decimal(c["correlation"], 2),
            fr_pvalue(c["p"]),
            fr_pvalue(c["p_holm"]),
            "oui" if c["reject"] else "non",
        ]
        rows.append(row)
    return _table(headers, rows)


def _matrix_lines(scope: Mapping[str, Any]) -> list[str]:
    wins = []
    for pair in scope["matrix"]:
        if not pair["reject"] or pair["diff"] is None or pair["diff"] == 0:
            continue
        winner, loser = (pair["a"], pair["b"]) if pair["diff"] > 0 else (pair["b"], pair["a"])
        wins.append(
            f"- `{winner}` devant `{loser}` ({fr_points(abs(pair['diff']))}, "
            f"p BH {fr_pvalue(pair['p_bh'])})"
        )
    if not wins:
        return ["Aucune paire distinguée après correction de Benjamini-Hochberg."]
    return wins


def _continuous_lines(block: Mapping[str, Any]) -> list[str]:
    label = METRIC_LABELS[block["metric"]]
    lines = [
        f"Métrique continue : {label} (`{block['metric']}`), meneur "
        f"{DASH if block['leader'] is None else '`' + block['leader'] + '`'}.",
        "",
    ]
    rows = [
        [f"`{e['model']}`", fr_percent(e["mean"]), fr_int(e["n"]), fr_int(e["excluded"])]
        for e in block["models"]
    ]
    lines += _table(["Modèle", "Moyenne", "Unités", "Exclues"], rows)
    if block["comparisons"]:
        lines += ["", "Différence au meneur, IC bootstrap apparié à 95 % :", ""]
        rows = [
            [
                f"`{c['model']}`",
                fr_int(c["n"]),
                fr_points(c["diff"]),
                fr_interval(c["bootstrap_ci_low"], c["bootstrap_ci_high"], points=True),
            ]
            for c in block["comparisons"]
        ]
        lines += _table(["Modèle", "Unités", "Différence", "IC bootstrap"], rows)
    return lines


def _scope_lines(track: str, scope: Mapping[str, Any], level: str) -> list[str]:
    usage = scope["usage"]
    title = "Score global" if usage is None else f"{USAGE_LABELS[usage]} (`{usage}`)"
    leader = scope["leader"]
    lines = [
        f"{level} {title}",
        "",
        f"Méthode : {METHOD_LABELS[scope['method']]}. Unités : {fr_int(scope['units'])}. "
        f"Meneur : {DASH if leader is None else '`' + leader + '`'}.",
        "",
        f"![{scope_title(track, usage)}](charts/{chart_name(track, usage)})",
        "",
    ]
    lines += _models_table(scope)
    if scope["comparisons"]:
        lines += [
            "",
            "Comparaisons au meneur (Holm sur les m − 1 comparaisons au meneur, m modèles du "
            "périmètre) :",
            "",
        ]
        lines += _comparisons_table(scope)
    lines += ["", "Matrice exploratoire « qui bat qui » (BH) :", ""]
    lines += _matrix_lines(scope)
    if scope["continuous"] is not None:
        lines += [""] + _continuous_lines(scope["continuous"])
    return lines + [""]


def _k_lines(block: Mapping[str, Any]) -> list[str]:
    lines = ["### Conclusion transversale (k̂_Bonferroni)", ""]
    if block["leader"] is None or not block["models"]:
        return lines + ["Sans objet : moins de deux modèles comparables.", ""]
    lines += [
        f"Nombre d'usages, sur {fr_int(block['usages'])}, où le meneur global "
        f"`{block['leader']}` bat chaque modèle au seuil α/m = "
        f"{fr_decimal(block['alpha_per_test'], 4)} :",
        "",
    ]
    rows = [
        [f"`{m['model']}`", f"{fr_int(m['wins'])} / {fr_int(m['tests'])}"] for m in block["models"]
    ]
    return lines + _table(["Modèle", "Usages gagnés"], rows) + [""]


def _spearman_lines(block: Mapping[str, Any]) -> list[str]:
    lines = ["### Validation externe (Spearman contre l'indice AA)", ""]
    variant = VARIANT_LABELS[block["variant"]]
    if block["status"] == "absent":
        return lines + [f"Indice AA absent : aucune référence pour l'indice {variant}.", ""]
    lines += [
        f"Indice AA {variant}, modèles mesurés appariés par tag : {fr_int(block['n'])}.",
        "",
        f"- ρ = {fr_decimal(block['rho'], 3)}, p unilatérale = {fr_pvalue(block['p'])}, "
        f"IC bootstrap à 95 % [{fr_decimal(block['ci_low'], 3)} ; "
        f"{fr_decimal(block['ci_high'], 3)}]",
        f"- Conclusion : {CONCLUSION_LABELS[block['conclusion']]}.",
        "",
    ]
    return lines


def render(summary: Mapping[str, Any]) -> str:
    """Rapport Markdown complet de la campagne."""
    completeness = summary["completeness"]
    method = summary["method"]
    lines = [f"# Rapport de la campagne {summary['campaign']}", ""]
    if summary["partial"]:
        lines += [
            "> **Rapport partiel** : lignes manquantes, discordantes ou en attente du juge "
            "écartées et comptées (voir « Complétude »).",
            "",
        ]
    lines += [
        f"Jeu `{summary['set']['id']}` (empreinte `{summary['set']['hash'][:12]}`), manifeste "
        f"de génération `{summary['generation_manifest'][:12]}`, "
        f"{fr_int(summary['k'])} tirage(s) par question. Seuil α = "
        f"{fr_decimal(method['alpha'], 2)} ; bootstrap : {fr_int(method['bootstrap_resamples'])} "
        f"tirages, graine {method['bootstrap_seed']}.",
        "",
        "Unité statistique : (modèle, piste, unité) ; les questions d'une unité sont agrégées "
        "par minimum, puis les seeds par moyenne. Une unité sans score (erreur du banc) est "
        "retirée des seules comparaisons de son modèle, et comptée dans « Exclues ».",
        "",
        "## Complétude",
        "",
    ]
    rows = [
        ["Clés attendues", fr_int(completeness["expected"])],
        ["Lignes retenues", fr_int(completeness["retained"])],
        ["Génération manquante", fr_int(completeness["generation_missing"])],
        ["Génération discordante", fr_int(completeness["generation_discordant"])],
        ["Correction manquante", fr_int(completeness["grading_missing"])],
        ["Correction discordante", fr_int(completeness["grading_discordant"])],
        ["En attente du juge", fr_int(completeness["awaiting_judgment"])],
        ["Configuration", "discordante" if completeness["config_discordant"] else "concordante"],
    ]
    lines += _table(["Contrôle", "Valeur"], rows) + ["", "## Modèles", ""]
    rows = [
        [
            f"`{m['tag']}`",
            m["family"],
            ", ".join(m["tracks"]),
            f"`{m['digest'].split(':')[-1][:12]}`",
        ]
        for m in summary["models"]
    ]
    lines += _table(["Modèle", "Famille", "Pistes", "Empreinte"], rows) + [""]
    for block in summary["tracks"]:
        lines += [f"## {TRACK_LABELS[block['track']]}", ""]
        for scope in block["scopes"]:
            lines += _scope_lines(
                block["track"], scope, "###" if scope["usage"] is None else "####"
            )
        lines += _k_lines(block["k_bonferroni"])
        lines += _spearman_lines(block["spearman"])
    aa = summary["aa_reference"]
    lines += ["## Références", ""]
    if aa is None:
        lines += ["Indice AA absent : aucun fichier `references/aa-AAAA-MM-JJ.json`."]
    else:
        lines += [f"Indice AA du {aa['date']} : `{aa['path']}` (sha256 `{aa['sha256']}`)."]
    return "\n".join(lines).rstrip("\n") + "\n"
