"""
Accessibilité des cinq pages, en thème clair puis sombre : axe-core (embarqué par
axe-playwright-python, aucun CDN) sur l'app réelle.

- `heading-order` et `button-name` : zéro violation (U2, U7).
- `color-contrast` : zéro violation imputable au thème (U5, U6, CAP-6). Une couleur de texte
  est imputable au thème quand elle vaut une couleur de `.streamlit/config.toml` mélangée au
  fond avec une opacité quelconque (`is_theme_color`) : Streamlit dérive par exemple ses
  textes estompés (fadedText40/60 : légendes, libellés désactivés) de `textColor` avec une
  transparence.
- Le texte d'un composant inactif (widget désactivé, `aria-disabled` ou `:disabled`) n'a pas
  d'exigence de contraste (WCAG 1.4.3, « inactive user interface component ») : ces nœuds
  sont listés à part, comme les couleurs natives de Streamlit sans rapport avec le thème. Les
  deux listes figurent dans le résumé de la session et dans le rapport JSON (dossier
  `e2e-reports` du dossier temporaire de pytest) : rien n'est masqué.

En sombre, `primaryColor` #7E65E9 est un compromis (DESIGN.md, 27/09) : aucune valeur ne
donne 4,5:1 à la fois au texte blanc des boutons et au violet employé comme texte. Les
pastilles d'outils choisies (4,24:1) font échouer Agent_Lab en sombre : écart accepté.
"""

import json
import re
from pathlib import Path

import pytest
import toml

from src.app.modules import APP_NAME, MODULES
from tests.e2e import helpers as h

pytestmark = pytest.mark.e2e

CONFIG_PATH = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"
RULES = ["color-contrast", "heading-order", "button-name"]
PAGES = [("", APP_NAME)] + [(m.url_path, m.title) for m in MODULES]
PAGE_IDS = ["Accueil"] + [m.url_path for m in MODULES]
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# Écart d'arrondi toléré par canal (0-255) entre une couleur mesurée et un mélange du thème.
BLEND_TOLERANCE = 2

# Nœud inactif : désactivé lui-même, dans un conteneur désactivé, ou libellé d'un widget
# désactivé (même conteneur d'élément Streamlit qu'un contrôle désactivé).
_INACTIVE_JS = """(selector) => {
    const el = document.querySelector(selector);
    if (!el) return false;
    const inactive = '[aria-disabled="true"], :disabled';
    if (el.closest(inactive)) return true;
    const container = el.closest('[data-testid="stElementContainer"]');
    return !!(container && container.querySelector(inactive));
}"""


def theme_colors(scheme: str) -> set[str]:
    """Couleurs du thème pour `scheme` : clés de [theme] et de [theme.<scheme>]."""
    theme = toml.load(CONFIG_PATH).get("theme", {})
    colors = set()
    for section in (theme, theme.get(scheme, {})):
        for value in section.values():
            values = value if isinstance(value, list) else [value]
            colors.update(v.lower() for v in values if isinstance(v, str) and _HEX_RE.match(v))
    return colors


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))


def is_theme_color(fg: str, bg: str | None, palette: set[str]) -> bool:
    """`fg` vaut-il une couleur du thème posée sur `bg` avec une opacité α de 0 à 1
    (fg = α·c + (1 − α)·bg, à BLEND_TOLERANCE près par canal) ? α = 1 : la couleur exacte."""
    fg_rgb = _rgb(fg)
    bg_rgb = _rgb(bg) if bg and _HEX_RE.match(bg) else None
    for color in palette:
        c = _rgb(color)
        if all(abs(a - b) <= BLEND_TOLERANCE for a, b in zip(fg_rgb, c, strict=True)):
            return True
        if bg_rgb is None:
            continue
        for step in range(256):
            alpha = step / 255
            blend = [alpha * ci + (1 - alpha) * bi for ci, bi in zip(c, bg_rgb, strict=True)]
            if all(abs(f - b) <= BLEND_TOLERANCE for f, b in zip(fg_rgb, blend, strict=True)):
                return True
    return False


def _node_colors(node: dict) -> dict:
    for check in node.get("any", []) + node.get("all", []) + node.get("none", []):
        data = check.get("data")
        if isinstance(data, dict) and data.get("fgColor"):
            return data
    return {}


def _is_inactive(page, node: dict) -> bool:
    targets = [t for t in node.get("target", []) if isinstance(t, str)]
    return bool(targets) and page.evaluate(_INACTIVE_JS, targets[-1])


@pytest.mark.parametrize("color_scheme", ["light", "dark"])
@pytest.mark.parametrize(("path", "title"), PAGES, ids=PAGE_IDS)
def test_axe_no_theme_violation(page, app, color_scheme, path, title, report_dir):
    from axe_playwright_python.sync_playwright import Axe

    h.goto(page, app.base_url, path)
    # Graphiques et polices chargés de façon différée.
    page.wait_for_timeout(1_500)
    background = page.locator('[data-testid="stApp"]').evaluate(
        "e => getComputedStyle(e).backgroundColor"
    )
    red, green, blue = _rgb(toml.load(CONFIG_PATH)["theme"][color_scheme]["backgroundColor"])
    assert background == f"rgb({red}, {green}, {blue})", "thème non appliqué"

    results = Axe().run(
        page,
        options={"runOnly": {"type": "rule", "values": RULES}, "resultTypes": ["violations"]},
    )
    palette = theme_colors(color_scheme)
    failures, natives, inactive = [], [], []
    for violation in results.response["violations"]:
        for node in violation["nodes"]:
            colors = _node_colors(node)
            finding = {
                "scheme": color_scheme,
                "page": path or "Accueil",
                "rule": violation["id"],
                "html": re.sub(r"\s+", " ", node.get("html", ""))[:160],
                "target": " ".join(map(str, node.get("target", []))),
                "fg": colors.get("fgColor"),
                "bg": colors.get("bgColor"),
                "ratio": colors.get("contrastRatio"),
                "expected": colors.get("expectedContrastRatio"),
            }
            if violation["id"] != "color-contrast":
                failures.append(finding)
            elif _is_inactive(page, node):
                inactive.append({**finding, "category": "composant inactif (WCAG 1.4.3)"})
            elif finding["fg"] and not is_theme_color(finding["fg"], finding["bg"], palette):
                natives.append({**finding, "category": "couleur native de Streamlit"})
            else:
                failures.append(finding)

    report = report_dir / f"axe-{color_scheme}-{path or 'Accueil'}.json"
    report.write_text(
        json.dumps(
            {"failures": failures, "natives": natives, "inactive": inactive},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    h.AXE_NATIVE_FINDINGS.extend(natives + inactive)

    assert not failures, (
        f"{len(failures)} violation(s) axe imputable(s) au thème ou à l'app sur « {title} » "
        f"({color_scheme}) ; rapport : {report}\n"
        + "\n".join(
            f"- {f['rule']} : {f['html']} (texte {f['fg']} sur {f['bg']}, {f['ratio']}:1)"
            for f in failures
        )
    )
