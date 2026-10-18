"""Fichiers de la coquille (`web/static/`, story 1.8) : dérive des jetons, emojis, URL externes,
textes, routes et icônes. Aucun navigateur : les parcours vivent dans `tests/v2/e2e/`."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
DESIGN = ROOT / "_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md"
TEXT_SUFFIXES = {".html", ".css", ".js", ".json", ".svg"}

# Pictogrammes emoji (même périmètre que tests/e2e/helpers.py) : plans pictographiques, symboles
# divers, dingbats, sélecteur de variante emoji.
EMOJI = re.compile("[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff️‼⁉ℹ]")


def text_files(*, suffixes: set[str] = TEXT_SUFFIXES) -> list[Path]:
    return sorted(
        path
        for path in STATIC.rglob("*")
        if path.is_file() and path.suffix in suffixes and "vendor" not in path.parts
    )


# --- Dérive des jetons (UX-DR1) ---------------------------------------------------------------


def design_tokens(design_text: str) -> dict:
    front_matter = design_text.split("---")[1]
    return yaml.safe_load(front_matter)


def css_variables(css: str, selector: str) -> dict[str, str]:
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.DOTALL)
    assert block, f"bloc {selector} absent"
    return {
        name: " ".join(value.split())
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block.group(1))
    }


def token_drift(css: str, design: dict) -> list[str]:
    """Écarts entre `tokens.css` et le front matter de DESIGN.md (vide = identiques)."""
    light = css_variables(css, ":root")
    dark = css_variables(css, ':root[data-theme="dark"]')
    problems: list[str] = []

    def compare(where: dict[str, str], name: str, expected: str, label: str) -> None:
        actual = where.get(name)
        if actual is None:
            problems.append(f"{label} : {name} absent de tokens.css")
        elif actual.upper() != expected.upper():
            problems.append(f"{label} : {name} vaut {actual}, DESIGN.md dit {expected}")

    for key, value in design["colors"].items():
        if key.endswith("-dark"):
            compare(dark, f"--color-{key.removesuffix('-dark')}", value, f"couleur {key}")
        else:
            compare(light, f"--color-{key}", value, f"couleur {key}")
    compare(light, "--radius", design["rounded"]["DEFAULT"], "rayon DEFAULT")
    compare(light, "--radius-full", design["rounded"]["full"], "rayon full")
    for role in ("body", "heading", "metric-value", "caption"):
        compare(light, f"--font-{role}", design["typography"][role]["fontFamily"], f"police {role}")
    return problems


def test_tokens_css_mirrors_design_md():
    css = (STATIC / "tokens.css").read_text(encoding="utf-8")
    design = design_tokens(DESIGN.read_text(encoding="utf-8"))
    assert token_drift(css, design) == []
    # Le miroir est complet : 4 séries de graphique, clair et sombre.
    assert {f"chart-{n}" for n in range(1, 5)} <= set(design["colors"])


@pytest.mark.parametrize(
    ("old", "new", "fragment"),
    [
        ("--color-primary: #451DC7", "--color-primary: #451DC8", "--color-primary"),
        ("--color-surface-alt: #16162A", "--color-surface-alt: #16162B", "--color-surface-alt"),
        ("--radius: 12px", "--radius: 10px", "rayon DEFAULT"),
        ("--font-body: Aptos, Inter, sans-serif", "--font-body: Inter, sans-serif", "police body"),
    ],
)
def test_the_drift_test_fails_when_a_value_differs(old, new, fragment):
    css = (STATIC / "tokens.css").read_text(encoding="utf-8")
    assert old in css
    design = design_tokens(DESIGN.read_text(encoding="utf-8"))
    drift = token_drift(css.replace(old, new, 1), design)
    assert drift and any(fragment in line for line in drift), drift


def test_the_drift_test_fails_when_a_token_is_missing():
    css = (STATIC / "tokens.css").read_text(encoding="utf-8")
    design = design_tokens(DESIGN.read_text(encoding="utf-8"))
    drift = token_drift(css.replace("--color-risk: #FF2A49;", "", 1), design)
    assert any("--color-risk" in line and "absent" in line for line in drift)


def test_css_outside_tokens_has_no_hard_coded_color():
    for name in ("base.css", "components.css"):
        css = (STATIC / name).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), f"{name} : couleur en dur"
        assert not re.search(r"\b(rgb|hsl)a?\(", css), f"{name} : couleur en dur"


# --- Aucun emoji, aucune ressource externe ----------------------------------------------------


def test_no_emoji_in_static():
    found = {
        path.relative_to(STATIC).as_posix(): EMOJI.findall(path.read_text(encoding="utf-8"))
        for path in text_files()
    }
    assert {name: chars for name, chars in found.items() if chars} == {}


def test_the_emoji_detector_sees_emojis():
    assert EMOJI.search("Local \U0001f7e2") and EMOJI.search("Cloud ☁️")
    assert not EMOJI.search("Écran Accueil · Sobriété — 3 mg de CO₂ …")


def test_no_external_url_cdn_or_third_party_script_outside_vendor():
    allowed = {"http://www.w3.org/2000/svg"}  # espace de noms SVG, jamais une requête
    for path in text_files():
        text = path.read_text(encoding="utf-8")
        urls = set(re.findall(r"https?://[^\s\"'<>)]+", text)) - allowed
        assert urls == set(), f"{path.name} : URL externe {urls}"
        assert not re.search(r"@import|googleapis|gstatic|cdn\.", text), path.name
        assert not re.search(r"""(?:src|href)=["']//""", text), path.name


def test_vendor_directory_exists_and_third_party_code_carries_its_license():
    vendor = STATIC / "vendor"
    assert vendor.is_dir()
    files = [p for p in vendor.rglob("*") if p.is_file() and p.name != "README.md"]
    if files:
        assert any("licen" in p.name.lower() for p in files), "licence absente de vendor/"


def test_fonts_and_icons_ship_their_licenses():
    assert "SIL Open Font License" in (STATIC / "fonts/LICENSE.txt").read_text(encoding="utf-8")
    assert "Apache License" in (STATIC / "icons.LICENSE.txt").read_text(encoding="utf-8")
    assert (STATIC / "fonts/InterVariable.woff2").stat().st_size > 10_000


# --- index.html : références, textes -----------------------------------------------------------


class _Index(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.texts: dict[str, str] = {}  # clé i18n -> texte du HTML
        self.attributes: dict[str, str] = {}  # clé i18n -> valeur d'attribut
        self.lang: str | None = None
        self.landmarks: set[str] = set()
        self._key: str | None = None
        self._buffer = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "html":
            self.lang = attributes.get("lang")
        if tag in {"header", "nav", "main", "footer"}:
            self.landmarks.add(tag)
        for name in ("href", "src"):
            value = attributes.get(name)
            if value and value.startswith("/static/"):
                self.references.append(value.split("#")[0])
        if "data-i18n" in attributes:
            self._key, self._buffer = attributes["data-i18n"], ""
        if "data-i18n-aria-label" in attributes:
            self.attributes[attributes["data-i18n-aria-label"]] = attributes.get("aria-label", "")

    def handle_data(self, data):
        if self._key:
            self._buffer += data

    def handle_endtag(self, tag):
        if self._key:
            self.texts[self._key] = " ".join(self._buffer.split())
            self._key = None


def parse_index() -> _Index:
    parser = _Index()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    return parser


def catalog() -> dict:
    return json.loads((STATIC / "i18n/fr.json").read_text(encoding="utf-8"))


def lookup(key: str):
    value = catalog()
    for part in key.split("."):
        value = value[part]
    return value


def test_index_is_french_with_the_three_landmarks():
    index = parse_index()
    assert index.lang == "fr"
    assert {"header", "nav", "main"} <= index.landmarks


def test_index_references_existing_files_only():
    references = parse_index().references
    assert references
    for reference in references:
        assert (STATIC / reference.removeprefix("/static/")).is_file(), reference


def test_index_texts_equal_the_catalog():
    index = parse_index()
    assert index.texts
    for key, text in {**index.texts, **index.attributes}.items():
        assert " ".join(lookup(key).split()) == text, key


def test_every_text_key_used_by_the_scripts_exists_in_the_catalog():
    keys: set[str] = set()
    for path in STATIC.rglob("*.js"):
        keys |= set(re.findall(r"""\bt\(\s*["']([\w.-]+)["']""", path.read_text(encoding="utf-8")))
    keys |= {f"modules.{module_id}" for module_id in registry_modules()}
    keys |= {f"screens.{screen_id}" for screen_id in registry_screens()}
    assert keys
    for key in keys:
        assert isinstance(lookup(key), str), key


# --- Registre des écrans et routes (UX-DR4) ---------------------------------------------------

ROUTES = [
    "/",
    "/arene/chat",
    "/arene/comparer",
    "/arene/banc",
    "/documents",
    "/documents/base",
    "/documents/evaluation",
    "/agents/seul",
    "/agents/equipe",
    "/sobriete",
    "/modeles",
]
MODULE_IDS = ["home", "arena", "documents", "agents", "sobriety", "models"]


def registry_text() -> str:
    return (STATIC / "core/registry.js").read_text(encoding="utf-8")


def registry_modules() -> list[str]:
    return re.findall(r"""^ {4}id:\s*"([\w-]+)",\s*\n {4}icon""", registry_text(), re.MULTILINE)


def registry_screens() -> list[str]:
    return re.findall(r"""\{\s*id:\s*"([\w-]+)",\s*path:""", registry_text(), re.DOTALL)


def test_registry_declares_the_routes_of_the_contract_and_the_six_modules():
    paths = re.findall(r"""path:\s*"([^"]+)\"""", registry_text())
    assert paths == ROUTES
    assert registry_modules() == MODULE_IDS
    assert len(registry_screens()) == len(set(registry_screens())) == len(ROUTES)


def test_only_the_home_screen_is_available_in_this_story():
    text = registry_text()
    assert text.count('status: "available"') == 1
    assert text.count('status: "planned"') == len(ROUTES) - 1


# --- Icônes (UX-DR3) --------------------------------------------------------------------------


def sprite_ids() -> set[str]:
    return set(re.findall(r'<symbol id="(i-[\w-]+)"', (STATIC / "icons.svg").read_text("utf-8")))


def test_each_module_has_its_own_icon_in_the_sprite():
    icons = re.findall(r"""icon:\s*"([\w-]+)\"""", registry_text())
    assert len(icons) == len(set(icons)) == len(MODULE_IDS)
    assert {f"i-{name}" for name in icons} <= sprite_ids()


def test_every_icon_the_html_names_exists_in_the_sprite():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r"icons\.svg#(i-[\w-]+)", html))
    assert used and used <= sprite_ids()


def test_sprite_is_monochrome_and_inherits_the_text_color():
    sprite = (STATIC / "icons.svg").read_text(encoding="utf-8")
    assert "currentColor" in sprite and not re.search(r"#[0-9a-fA-F]{3,6}\b", sprite)


# --- Microcopie (UX-DR18) ---------------------------------------------------------------------

# Espace ordinaire avant « ; : ! ? » ou » , ou après « : il faut une espace insécable (EXPERIENCE.md).
BREAKING_SPACE = re.compile(r" [;:!?»]|« ")


def catalog_strings(value) -> list[str]:
    if isinstance(value, dict):
        return [text for child in value.values() for text in catalog_strings(child)]
    return [value] if isinstance(value, str) else []


def test_catalog_and_index_use_non_breaking_spaces_before_high_punctuation():
    texts = catalog_strings(catalog())
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    texts += re.findall(r">([^<>]+)<", index)
    assert texts
    offending = [text for text in texts if BREAKING_SPACE.search(text)]
    assert offending == []


def test_the_space_detector_sees_a_breaking_space():
    assert BREAKING_SPACE.search("Texte ; suite")
    assert not BREAKING_SPACE.search("Texte ; suite")


# --- Barre haute, composants et formats (story 1.9) -------------------------------------------

I18N_KEY = re.compile(r"""["']((?:topbar|components|errors|format|shell)\.[\w.]+)["']""")


def test_every_text_key_named_in_a_script_exists_in_the_catalog():
    """Les clés écrites dans une table (`text: "components.badge.local"`) ou passées à `t()` d'une
    variable ne sont pas vues par le test plus haut : on les cherche par leur forme."""
    keys: set[str] = set()
    for path in STATIC.rglob("*.js"):
        keys |= set(I18N_KEY.findall(path.read_text(encoding="utf-8")))
    assert {"components.badge.local", "topbar.ollama.up", "topbar.co2.unmeasurable_many"} <= keys
    for key in sorted(keys):
        assert isinstance(lookup(key), str), key


def test_the_catalog_keeps_no_unused_text_of_the_top_bar():
    index = parse_index()
    scripts = " ".join(path.read_text(encoding="utf-8") for path in STATIC.rglob("*.js"))
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    used = set(index.texts) | set(index.attributes) | set(I18N_KEY.findall(scripts + html))
    orphans = [key for key in flat_keys(catalog()["topbar"], "topbar") if key not in used]
    assert orphans == [], f"textes de la barre haute jamais utilisés : {orphans}"


def flat_keys(value, prefix: str) -> list[str]:
    if isinstance(value, dict):
        return [
            key for name, child in value.items() for key in flat_keys(child, f"{prefix}.{name}")
        ]
    return [prefix]


def test_the_ollama_down_text_mirrors_errors_py():
    from wavelocalai.errors import ERRORS

    spec = ERRORS["ollama_down"]
    mirror = catalog()["errors"]["ollama_down"]
    assert mirror["message"] == spec.message
    assert mirror["action"] == spec.action.replace("`", "")  # le front n'affiche pas le Markdown


def test_no_script_reads_or_writes_the_cloud_switch_in_storage():
    """AD-20 : la bascule cloud vit dans le store seulement. `theme.js` est le seul module qui
    touche `localStorage` (thème et projection)."""
    for path in STATIC.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"(?:localStorage|sessionStorage|indexedDB)s*[.[]", text):
            assert path.name == "theme.js", f"{path.name} touche le stockage du navigateur"
    assert "allowCloud" in (STATIC / "core/store.js").read_text(encoding="utf-8")


def test_the_front_computes_no_measure_and_names_no_host():
    """Aucune mesure recalculée côté front (AD-20) : pas de conversion de CO2 hors de format.js,
    et aucune adresse en dur (les appels vont à la même origine)."""
    for path in STATIC.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(
            r"https?://", text.replace("http://www.w3.org/2000/svg", "")
        ), path.name
        if path.name != "format.js":
            assert "1_000_000" not in text and "per_mg" not in text, path.name
