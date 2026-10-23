"""Écran Modèles, installation (story 5.3) : règles de structure du front, sans navigateur. Les
parcours (installation, progression, annulation, échec, reprise, axe) vivent dans
`e2e/test_models_install.py`."""

from __future__ import annotations

import re

from .static_files import catalog, read_static

CATALOG = catalog()
FILES = (
    "screens/models.js",
    "screens/models-installed.js",
    "screens/models-catalog.js",
    "screens/models-pull.js",
    "screens/models-progress.js",
    "screens/models-format.js",
    "screens/models-unload.js",
    "screens/models-delete.js",
    "screens/models-defaults.js",
    "screens/models-rerank.js",
    "screens/models-card.js",
    "components/model-card-view.js",
    "components/model-card-loader.js",
    "components/model-card-drawer.js",
    "components/model-card-launcher.js",
)
SCREEN = "\n".join(read_static(name) for name in FILES)
CODE = "\n".join(line for line in SCREEN.splitlines() if not line.lstrip().startswith("//"))


def flatten(node: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in node.items():
        path = f"{prefix}{key}"
        keys |= flatten(value, f"{path}.") if isinstance(value, dict) else {path}
    return keys


def test_every_screen_text_exists_and_every_catalog_text_is_used():
    declared = flatten(CATALOG["models"], "models.")
    used = set(re.findall(r"""\bt\(\s*["'](models\.[\w.]+)["']""", SCREEN))
    # Famille de textes choisie par l'usage d'un modèle : `t(`models.installed.usage_${m.kind}`)`.
    for prefix in re.findall(r"""t\(`(models\.[\w.]+_)\$\{""", SCREEN):
        used |= {key for key in declared if key.startswith(prefix)}
    # Textes à choisir entre deux clés : `t(cond ? "models.a" : "models.b")`.
    used |= set(re.findall(r"""["'](models\.[\w.]+)["']""", SCREEN))
    # Textes au pluriel : `plural("models.a.b", n)` lit `models.a.b_one` et `models.a.b_other`.
    for base in re.findall(r"""plural\(\s*["'](models\.[\w.]+)["']""", SCREEN):
        used = (used - {base}) | {f"{base}_one", f"{base}_other"}
    assert used == declared


def test_the_texts_put_a_no_break_space_before_double_punctuation():
    text = "\n".join(
        value
        for key, value in {k: _lookup(k) for k in flatten(CATALOG["models"], "models.")}.items()
        if "qwen3.6:7b" not in value  # un nom de modèle n'est pas une ponctuation
    )
    assert not re.search(r" [:;!?]", text), re.findall(r".{12} [:;!?].{4}", text)


def _lookup(key: str) -> str:
    node: object = CATALOG
    for part in key.split("."):
        node = node[part]  # type: ignore[index]
    return str(node)


def test_the_text_file_is_declared_and_the_screen_is_registered_as_available():
    assert '"models",' in read_static("core/i18n.js")
    registry = read_static("core/routes/models.js")
    assert re.search(
        r'id: "models",\s*path: "/modeles",\s*param: "tag",\s*status: "available",\s*'
        r'load: \(\) => import\("\.\./\.\./screens/models\.js"\)',
        registry,
    )
    assert '<link rel="stylesheet" href="/static/models.css">' in read_static("index.html")


def test_the_screen_never_writes_html_and_reads_the_stream_through_the_single_sse_client():
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", CODE)
    assert "connectRun" in CODE and "EventSource" not in CODE
    assert "?after=" not in CODE  # la reprise est celle du client SSE (`keepSeq`)
    assert "keepSeq: true" in CODE


def test_no_call_to_the_api_leaves_before_the_shell_is_ready():
    main = read_static("screens/models.js")
    assert 'import { shellReady } from "../core/shell-ready.js"' in main
    read = main[main.index("async function read()") :]
    assert read.index("await shellReady()") < read.index("api.models(allowCloud)")
    # Seul l'écran appelle les listes ; le contrôleur d'installation n'appelle que sur un clic.
    assert "api.models(" not in read_static("screens/models-pull.js")
    assert "api.pullModel(" in read_static("screens/models-pull.js")


def test_the_screen_builds_its_page_before_any_server_call():
    main = read_static("screens/models.js")
    assert main.index("host.replaceChildren(") < main.index("\n  load();")


def test_the_screen_computes_no_measure():
    """AD-20 : `fits`, la mémoire nécessaire et celle qui manque viennent du serveur. Aucun calcul
    sur ces champs : le front les lit, les trie et les met en forme."""
    for field in ("required_gb", "needed_gb", "short_gb", "free_gb", "percent", "total_bytes"):
        assert not re.search(rf"{field}\s*[-+*/]|[-+*/]\s*\w*\.?{field}", CODE), field
    assert "Math.max" not in CODE and "reduce(" not in CODE
    # Seul « Mo / Go » est un calcul d'unité, rangé dans `formatSize`.
    assert len(re.findall(r"/\s*(?:GIB|MIB)\b", CODE)) == 2


def test_the_install_buttons_stay_focusable_when_disabled_and_say_why():
    catalog_js = read_static("screens/models-catalog.js")
    assert 'setAttribute("aria-disabled"' in catalog_js and "aria-describedby" in catalog_js
    assert ".disabled" not in catalog_js  # jamais `disabled` : le bouton perdrait le focus
    assert '"models.catalog.install_anyway_aria"' in catalog_js


def test_the_stylesheet_has_no_color_of_its_own_and_the_files_stay_under_the_size_budget():
    css = read_static("models.css")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\b(rgb|hsl)a?\(", css)
    block = re.search(r"\.models-install-named \{(.*?)\}", css, re.DOTALL)
    assert block and "var(--color-primary-fill)" in block.group(1)
    assert "var(--color-on-primary)" in block.group(1)
    for name in (*FILES, "models.css"):
        assert len(read_static(name).splitlines()) <= 600, name
