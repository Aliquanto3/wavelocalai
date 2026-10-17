"""Graphiques SVG écrits à la main (aucune bibliothèque de tracé), à la charte Wavestone
(primaire ``#451DC7``, aucun emoji) : score et IC à 95 % de chaque modèle d'un périmètre,
produits depuis le résumé seul. Titre et ``aria-label`` en français, nombres au format
français."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from .markdown import chart_name, fr_percent, scope_title

PRIMARY = "#451DC7"
PRIMARY_LIGHT = "#B5A5EC"
TEXT = "#1F1A33"
MUTED = "#6B6880"
GRID = "#E4E1F0"
BACKGROUND = "#FFFFFF"
FONT = "Arial, Helvetica, sans-serif"

WIDTH = 760
LABEL_WIDTH = 220
VALUE_WIDTH = 90
TOP = 64
ROW = 30
BOTTOM = 40


def _x(value: float) -> float:
    plot = WIDTH - LABEL_WIDTH - VALUE_WIDTH - 20
    return LABEL_WIDTH + max(0.0, min(1.0, value)) * plot


def _num(value: float) -> str:
    return f"{value:.1f}"


def _no_score(entry: Mapping[str, Any]) -> str:
    return "sans score" if entry.get("eligible", True) else "hors classement"


def scope_chart(track: str, scope: Mapping[str, Any]) -> str:
    """SVG d'un périmètre : un point (score) et un segment (IC à 95 %) par modèle, dans l'ordre
    des groupes puis des scores."""
    title = scope_title(track, scope["usage"])
    entries = sorted(
        scope["models"],
        key=lambda e: (e["group"] is None, e["group"] or 0, -(e["mean"] or 0.0)),
    )
    height = TOP + ROW * max(1, len(entries)) + BOTTOM
    described = []
    for e in entries:
        if e["mean"] is None:
            described.append(f"{e['model']} : {_no_score(e)}")
        else:
            described.append(
                f"{e['model']} : {fr_percent(e['mean'])} (IC à 95 % de "
                f"{fr_percent(e['ci_low'])} à {fr_percent(e['ci_high'])})"
            )
    label = f"{title}. " + " ; ".join(described) + "."
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" role="img" aria-label={quoteattr(label)}>',
        f"<title>{escape(title)}</title>",
        f"<desc>{escape(label)}</desc>",
        f'<rect width="{WIDTH}" height="{height}" fill="{BACKGROUND}"/>',
        f'<text x="16" y="28" font-family="{FONT}" font-size="16" font-weight="bold" '
        f'fill="{PRIMARY}">{escape(title)}</text>',
        f'<text x="16" y="48" font-family="{FONT}" font-size="12" fill="{MUTED}">'
        "Score moyen par unité et IC à 95 % ; point plein : groupe de tête (indiscernable du meneur)</text>",
    ]
    axis_y = TOP + ROW * max(1, len(entries))
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = _num(_x(tick))
        parts.append(
            f'<line x1="{x}" y1="{TOP - 6}" x2="{x}" y2="{axis_y}" stroke="{GRID}" '
            'stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x}" y="{axis_y + 18}" font-family="{FONT}" font-size="11" '
            f'fill="{MUTED}" text-anchor="middle">{escape(fr_percent(tick, 0))}</text>'
        )
    for index, e in enumerate(entries):
        y = TOP + ROW * index + ROW / 2
        parts.append(
            f'<text x="{LABEL_WIDTH - 12}" y="{_num(y + 4)}" font-family="{FONT}" '
            f'font-size="12" fill="{TEXT}" text-anchor="end">{escape(e["model"])}</text>'
        )
        if e["mean"] is None:
            parts.append(
                f'<text x="{WIDTH - VALUE_WIDTH}" y="{_num(y + 4)}" font-family="{FONT}" '
                f'font-size="12" fill="{MUTED}">{escape(_no_score(e))}</text>'
            )
            continue
        if e["ci_low"] is not None and e["ci_high"] is not None:
            parts.append(
                f'<line x1="{_num(_x(e["ci_low"]))}" y1="{_num(y)}" '
                f'x2="{_num(_x(e["ci_high"]))}" y2="{_num(y)}" stroke="{PRIMARY_LIGHT}" '
                'stroke-width="4" stroke-linecap="round"/>'
            )
        leader = e["model"] == scope["leader"]
        parts.append(
            f'<circle cx="{_num(_x(e["mean"]))}" cy="{_num(y)}" r="6" '
            f'fill="{PRIMARY if leader or e["group"] == 1 else BACKGROUND}" '
            f'stroke="{PRIMARY}" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{WIDTH - VALUE_WIDTH}" y="{_num(y + 4)}" font-family="{FONT}" '
            f'font-size="12" fill="{TEXT}">{escape(fr_percent(e["mean"]))}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def charts(summary: Mapping[str, Any]) -> dict[str, str]:
    """Nom de fichier (sous ``charts/``) → SVG, un par périmètre de chaque piste."""
    result = {}
    for block in summary["tracks"]:
        for scope in block["scopes"]:
            result[chart_name(block["track"], scope["usage"])] = scope_chart(block["track"], scope)
    return result
