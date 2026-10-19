"""Lecture des fichiers statiques du front que la story 5.0 a découpés en plusieurs fichiers.

Les tests de structure cherchent des textes dans « le catalogue », « components.css », « le
registre » ou « l'API » : ces fonctions rendent l'ensemble de leurs fichiers, dans l'ordre de
chargement, pour que le découpage ne change rien à ce qu'ils vérifient.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
TEXTS = STATIC / "i18n" / "fr"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def text_file_names() -> list[str]:
    """Les fichiers de textes déclarés par `core/i18n.js` (`TEXT_FILES`), dans l'ordre."""
    declared = re.search(r"TEXT_FILES = \[(.*?)\];", read("core/i18n.js"), re.DOTALL)
    assert declared, "TEXT_FILES absent de core/i18n.js"
    return re.findall(r'"([\w-]+)"', declared.group(1))


def catalog() -> dict:
    """Le catalogue de textes entier : les fichiers de `i18n/fr/` fusionnés, sans écrasement."""
    merged: dict = {}
    for path in sorted(TEXTS.glob("*.json")):
        for key, value in json.loads(path.read_text(encoding="utf-8")).items():
            assert key not in merged, f"clé « {key} » déclarée deux fois ({path.name})"
            merged[key] = value
    return merged


def component_stylesheets() -> list[str]:
    """Les feuilles `css/components/` liées par `index.html`, dans l'ordre de la cascade."""
    links = re.findall(r'<link rel="stylesheet" href="/static/([\w/.-]+)">', read("index.html"))
    return [name for name in links if name.startswith("css/components/")]


def components_css() -> str:
    """Les CSS des composants, concaténés dans l'ordre de la cascade (l'ancien `components.css`)."""
    return "\n".join(read(name) for name in component_stylesheets())


def registry_text() -> str:
    """`core/registry.js` suivi des fichiers de `core/routes/`, dans l'ordre de `MODULES`."""
    registry = read("core/registry.js")
    files = dict(re.findall(r'import \{ (\w+) \} from "\./routes/([\w-]+)\.js";', registry))
    order = re.search(r"MODULES = \[(.*?)\];", registry, re.DOTALL)
    assert order, "MODULES absent de core/registry.js"
    names = re.findall(r"\w+", order.group(1))
    return "\n".join([registry, *(read(f"core/routes/{files[name]}.js") for name in names)])


def api_text() -> str:
    """`core/api.js` suivi des fichiers de `core/api/`."""
    parts = [read("core/api.js")]
    parts += [
        path.read_text(encoding="utf-8") for path in sorted((STATIC / "core/api").glob("*.js"))
    ]
    return "\n".join(parts)


def picker_text() -> str:
    """`wl-model-picker.js` suivi de `model-picker-option.js`, dont il a sorti les lignes."""
    return read("components/wl-model-picker.js") + "\n" + read("components/model-picker-option.js")


COMBINED = {
    "components.css": components_css,
    "core/registry.js": registry_text,
    "core/api.js": api_text,
    "components/wl-model-picker.js": picker_text,
}


def read_static(name: str) -> str:
    """Le fichier `name` de `static/`, ou l'ensemble de ses morceaux s'il a été découpé."""
    return COMBINED[name]() if name in COMBINED else read(name)
