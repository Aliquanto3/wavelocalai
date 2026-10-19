"""Fichiers de la coquille (`web/static/`, story 1.8) : dérive des jetons, emojis, URL externes,
textes, routes et icônes. Aucun navigateur : les parcours vivent dans `tests/v2/e2e/`."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml

from .static_files import catalog as merged_catalog
from .static_files import (
    components_css,
)
from .static_files import registry_text as merged_registry

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
    # Tous les fichiers CSS, ceux des composants (`css/components/`) et ceux à venir compris.
    files = [path for path in sorted(STATIC.rglob("*.css")) if path.name != "tokens.css"]
    assert {"base.css", "button.css", "screens.css", "chat.css", "arena.css"} <= {
        path.name for path in files
    }
    for path in files:
        css = path.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css), f"{path.name} : couleur en dur"
        assert not re.search(r"\b(rgb|hsl)a?\(", css), f"{path.name} : couleur en dur"


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
    return merged_catalog()


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
    "/arene/references",
    "/documents",
    "/documents/base",
    "/documents/evaluation",
    "/agents/seul",
    "/agents/equipe",
    "/sobriete",
    "/modeles",
]
# Routes de la maquette (D-8) : déclarées `planned`, avec leur paramètre de chemin quand elles en ont.
MOCKUP_ROUTES = {
    "/agents/equipe": "run_id",
}
MODULE_IDS = ["home", "arena", "documents", "agents", "sobriety", "models"]


def registry_text() -> str:
    return merged_registry()


def registry_modules() -> list[str]:
    return re.findall(r"""^ {2}id:\s*"([\w-]+)",\s*\n {2}icon""", registry_text(), re.MULTILINE)


def registry_screens() -> list[str]:
    return re.findall(r"""\{\s*id:\s*"([\w-]+)",\s*path:""", registry_text(), re.DOTALL)


def test_registry_declares_the_routes_of_the_contract_and_the_six_modules():
    paths = re.findall(r"""path:\s*"([^"]+)\"""", registry_text())
    assert paths == ROUTES
    assert registry_modules() == MODULE_IDS
    assert len(registry_screens()) == len(set(registry_screens())) == len(ROUTES)


def test_only_the_available_screens_are_declared_so_far():
    text = registry_text()
    assert text.count('status: "available"') == 10
    assert text.count('status: "planned"') == len(ROUTES) - 10
    assert re.search(r'id: "sobriety",\s*path: "/sobriete",\s*status: "available"', text)
    # `#/modeles/<tag>` (fiche d'un modèle, story 5.6) : l'écran Modèles a son `param` de chemin.
    assert re.search(
        r'id: "models",\s*path: "/modeles",\s*param: "tag",\s*status: "available"', text
    )
    assert text.count('param: "tag"') == 1
    assert re.search(r'id: "documents-chat",\s*path: "/documents",\s*status: "available"', text)
    assert re.search(r'id: "arena-chat",\s*path: "/arene/chat",\s*status: "available"', text)
    assert re.search(
        r'id: "arena-compare",\s*path: "/arene/comparer",[^}]*status: "available"', text
    )
    assert re.search(
        r'id: "documents-base",\s*path: "/documents/base",\s*status: "available"', text
    )
    assert re.search(
        r'id: "arena-references",\s*path: "/arene/references",\s*status: "available"', text
    )
    assert re.search(
        r'id: "arena-bench",\s*path: "/arene/banc",\s*param: "run_id",\s*status: "available"', text
    )
    assert re.search(
        r'id: "documents-evaluation",\s*path: "/documents/evaluation",\s*param: "run_id",\s*status: "available"',
        text,
    )


def test_the_mockup_routes_are_planned_with_their_path_parameter():
    """D-8 : `#/agents/equipe/<run_id>` existe, `planned`, sans écran ni `load` (les autres routes de la
    maquette sont livrées : `#/arene/banc/<run_id>` 7.4, `#/documents/evaluation/<run_id>` 7.3,
    `#/modeles/<tag>` 5.6, `#/arene/references` 5.8)."""
    text = registry_text()
    for path, param in MOCKUP_ROUTES.items():
        declaration = re.search(
            r"\{\s*id:\s*\"[\w-]+\",\s*path:\s*\"" + re.escape(path) + r"\",(.*?)\}",
            text,
            re.DOTALL,
        )
        assert declaration, path
        body = declaration.group(1)
        assert 'status: "planned"' in body and "load" not in body, path
        assert (f'param: "{param}"' in body) == (param is not None), path


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


ROUNDED_VIEWBOX = "0 -960 960 960"  # Material Symbols : grille de 960 unités, origine en haut


def used_icons() -> set[str]:
    """Les symboles que le front nomme : HTML (`icons.svg#i-…`), `icon("…")`, `setIcon(…, "…")`,
    `icon: "…"` du registre et de `wl-badge`."""
    used: set[str] = set()
    for path in text_files(suffixes={".js", ".html"}):
        text = path.read_text(encoding="utf-8")
        used |= {f"i-{name}" for name in re.findall(r"""icon\(\s*["']([\w-]+)["']""", text)}
        used |= {
            f"i-{name}" for name in re.findall(r"""setIcon\([^,()]+,\s*["']([\w-]+)["']""", text)
        }
        used |= {f"i-{name}" for name in re.findall(r"""icon:\s*["']([\w-]+)["']""", text)}
        used |= set(re.findall(r"icons\.svg#(i-[\w-]+)", text))
    return used


def symbol_viewboxes(sprite: str) -> dict[str, str]:
    return dict(re.findall(r'<symbol id="(i-[\w-]+)" viewBox="([^"]+)"', sprite))


# Exceptions connues : 8 symboles Material Icons (Filled, viewBox 0 0 24 24) ajoutés au sprite par la
# story 3.2, faute de jeu Rounded hors ligne. À remplacer par le sprite officiel Material Symbols
# Rounded fourni par Anaël ; la liste ne doit que se réduire (test_the_pending_list_does_not_grow).
PENDING_ROUNDED = {
    "i-hourglass-empty": "6767bcdf2d5c3f8c",
    "i-sync": "9e23c1e9bdf79082",
    "i-edit": "0176e05c86e47df0",
    "i-gavel": "d972ac796b422edf",
    "i-timer": "0776b3cda138c889",
    "i-block": "f5021ac956f4e62f",
    "i-open-in-full": "a4294de3eab5dbef",
    "i-close-fullscreen": "703592e1185ac599",
}


def icon_problems(sprite: str, used: set[str]) -> list[str]:
    """Écarts entre le sprite et le front (D-2) : symbole absent, tracé qui n'est pas Rounded."""
    boxes = symbol_viewboxes(sprite)
    problems = [f"{name} utilisé mais absent du sprite" for name in sorted(used - set(boxes))]
    problems += [
        f"{name} : viewBox {box}, pas un Material Symbols Rounded ({ROUNDED_VIEWBOX})"
        for name, box in sorted(boxes.items())
        if box != ROUNDED_VIEWBOX and name not in PENDING_ROUNDED
    ]
    return problems


def test_every_icon_the_front_uses_is_in_the_sprite_and_the_sprite_is_rounded_only():
    """D-2 : chaque symbole utilisé existe, et le sprite n'a que des Material Symbols Rounded
    (aucun tracé Material Icons Filled, `viewBox` de 24 unités, comme ceux de la maquette)."""
    used = used_icons()
    assert {"i-check", "i-home", "i-swords", "i-info", "i-palette"} <= used  # le relevé voit tout
    sprite = (STATIC / "icons.svg").read_text(encoding="utf-8")
    assert icon_problems(sprite, used) == []


def test_the_pending_list_does_not_grow():
    """Aucun symbole de plus n'entre dans les exceptions sans qu'on modifie ce test exprès."""
    assert len(PENDING_ROUNDED) == 8
    assert all(name.startswith("i-") for name in PENDING_ROUNDED)


def test_the_icon_check_sees_a_filled_symbol_and_a_missing_one():
    sprite = (STATIC / "icons.svg").read_text(encoding="utf-8")
    filled = '<symbol id="i-stop" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></symbol>'
    problems = icon_problems(sprite + filled, used_icons() | {"i-stop", "i-hourglass"})
    assert any("i-stop : viewBox 0 0 24 24" in line for line in problems)
    assert "i-hourglass utilisé mais absent du sprite" in problems


# Empreinte (SHA-256, 16 premiers caractères) du contenu de chaque symbole, relevée sur le sprite
# importé avec la coquille (5990111) depuis le jeu Rounded officiel. Le `viewBox` seul ne distingue
# pas Rounded d'Outlined ou de Sharp (même grille) : l'empreinte fige les tracés relus, et tout
# symbole ajouté ou retouché fait échouer le test tant que son empreinte n'est pas ajoutée ici, avec
# sa provenance (jeu Rounded officiel, jamais redessiné à la main) dans le message de commit.
ROUNDED_FINGERPRINTS = {
    "i-home": "8011eaf63beeb77e",
    "i-swords": "896d66cbff1e56a8",
    "i-description": "5d922af9fa65834a",
    "i-smart-toy": "c602ac3f494d956b",
    "i-eco": "75d8e21877b60ddc",
    "i-deployed-code": "62bac9fc448fbaf5",
    "i-menu": "fbeaa0c7baea715d",
    "i-close": "2a69e4a659d670be",
    "i-palette": "ca2b014aecd55a94",
    "i-expand-more": "442351dfefd1f8da",
    "i-computer": "50f05750f97d3a78",
    "i-cloud": "39125432fa536bc9",
    "i-help": "7dc8a6c3bb8032d5",
    "i-dark-mode": "76cfeeaa4e1d0ead",
    "i-light-mode": "3fe46ba9ad3dd7b7",
    "i-check": "1619ea10ae9d3506",
    "i-info": "7d70043c7e03bb0e",
    "i-warning": "0198206a704fb1e8",
    "i-error": "725321bbd8fbf4d8",
}


def symbol_fingerprints(sprite: str) -> dict[str, str]:
    return {
        name: hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
        for name, body in re.findall(r'<symbol id="(i-[\w-]+)"[^>]*>(.*?)</symbol>', sprite, re.S)
    }


def test_every_sprite_symbol_matches_its_reviewed_rounded_fingerprint():
    """D-2 : le `viewBox` ne prouve pas la variante Rounded ; chaque tracé doit être l'un de ceux
    relus à l'import. Un symbole nouveau ou modifié exige d'ajouter son empreinte en connaissance
    de cause (le sprite officiel complet reste à fournir, voir story 1.12)."""
    sprite = (STATIC / "icons.svg").read_text(encoding="utf-8")
    assert symbol_fingerprints(sprite) == {**ROUNDED_FINGERPRINTS, **PENDING_ROUNDED}


def test_the_fingerprint_check_sees_a_retouched_symbol():
    sprite = (STATIC / "icons.svg").read_text(encoding="utf-8")
    retouched = sprite.replace('d="M', 'd="M1 ', 1)
    assert symbol_fingerprints(retouched) != ROUNDED_FINGERPRINTS


def test_icons_license_names_the_provenance():
    license_text = (STATIC / "icons.LICENSE.txt").read_text(encoding="utf-8")
    assert "Material Symbols" in license_text and "Rounded" in license_text
    assert "Google LLC" in license_text and "Apache License" in license_text


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
    """AD-20 : la bascule cloud vit dans le store seulement. `theme.js` (thème et projection) et
    `drafts.js` (brouillons de saisie) sont les seuls modules qui touchent `localStorage`."""
    for path in STATIC.rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\b(?:localStorage|sessionStorage|indexedDB)\s*[.[]", text):
            assert path.name in {"theme.js", "drafts.js"}, f"{path.name} touche le stockage"
    drafts = (STATIC / "core/drafts.js").read_text(encoding="utf-8")
    assert "allowCloud" not in drafts and "allow_cloud" not in drafts
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


# --- Accueil (story 1.11) ---------------------------------------------------------------------


def test_the_home_screen_reads_the_store_and_one_base_summary_and_every_home_text_is_used():
    """Les cartes d'état de l'Accueil lisent le store rempli par le flux (AD-6) et ne calculent rien.
    `home.js` n'appelle que le résumé de la base documentaire (story 4.9) ; la carte « Démo
    recommandée » (story 3.6, `home-demo.js`) ne lit que la liste des modèles et le défaut `arena`,
    et la carte « Références » (story 5.8, `home-references.js`) que `GET /api/references`.
    Les trois attendent le repère `shell-ready` avant d'appeler l'API (AD-15). Le catalogue ne garde
    aucun texte `home.*` qu'il n'affiche pas (un texte au pluriel compte par sa base)."""
    text = (STATIC / "screens/home.js").read_text(encoding="utf-8")
    demo = (STATIC / "screens/home-demo.js").read_text(encoding="utf-8")
    references = (STATIC / "screens/home-references.js").read_text(encoding="utf-8")
    for source in (text, demo, references):
        assert "fetch(" not in source and "EventSource" not in source
        assert 'from "../core/shell-ready.js"' in source and "await shellReady()" in source
    assert re.findall(r"\bapi\.(?!js)(\w+)", text) == ["documents"]
    assert set(re.findall(r"\bapi\.(\w+)\(", demo)) == {"models", "modelDefaults"}
    assert re.findall(r"\bapi\.(\w+)\(", references) == ["references"]
    assert (
        'REFERENCES_ICON = "help"' in references and 'icon("swords")' not in references
    )  # sa propre icône
    text += demo + references
    named = set(re.findall(r"""["'`](home\.[\w.${}]+)["'`]""", text))
    prefixes = {key.split("${")[0] for key in named if "${" in key}
    literal = {key for key in named if "${" not in key}
    literal |= {f"{key}_{form}" for key in literal for form in ("one", "other")}
    orphans = [
        key
        for key in flat_keys(catalog()["home"], "home")
        if key not in literal and not any(key.startswith(prefix) for prefix in prefixes)
    ]
    assert orphans == [], f"textes de l'Accueil jamais utilisés : {orphans}"
    assert "visibilitychange" in text
    assert "visibilitychange" in (STATIC / "core/system.js").read_text(encoding="utf-8")


# --- Interrupteurs en bascule et thème (story 1.12) -------------------------------------------


def test_every_checkbox_of_the_shell_is_a_wl_switch_with_the_check_in_its_thumb():
    """D-6 : « Autoriser le cloud » et « Mode projection » sont des `role="switch"` au même rendu
    `wl-switch` (`label.switch` > `.switch-box` > case + icône `check`), jamais une case nue."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert len(re.findall(r'type="checkbox"', html)) == len(re.findall(r'role="switch"', html)) == 2
    boxes = re.findall(
        r'<label class="switch">\s*<span class="switch-box">\s*<input type="checkbox" role="switch"'
        r"[^>]*>\s*<svg class=\"icon switch-check\"[^>]*><use href=\"/static/icons\.svg#i-check\"/>"
        r"</svg>\s*</span>",
        html,
    )
    assert len(boxes) == 2


def test_the_switch_css_follows_the_wl_switch_tokens_of_design_md():
    css = components_css()

    def rule(selector: str) -> str:
        found = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.DOTALL)
        assert found, selector
        return found.group(1)

    track = rule(".switch input")
    assert "var(--color-ink-secondary)" in track and "var(--color-surface-alt)" in track
    assert "var(--radius-full)" in track
    assert "var(--color-primary-fill)" in rule(".switch input:checked")
    assert "var(--color-surface)" in rule(".switch input::before")


def test_the_theme_module_offers_light_dark_and_system_with_light_as_the_default():
    text = (STATIC / "core/theme.js").read_text(encoding="utf-8")
    assert 'THEMES = ["light", "dark", "system"]' in text
    assert "prefers-color-scheme: dark" in text and '"change"' in text
    assert 'return THEMES.includes(stored) ? stored : "light"' in text
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'name="theme" value="(\w+)"', html) == ["light", "dark", "system"]
    # Aucun troisième jeu de jetons : `tokens.css` n'a que `:root` et `data-theme="dark"`.
    tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
    assert 'data-theme="system"' not in tokens and "prefers-color-scheme" not in tokens


def test_every_stylesheet_has_balanced_braces():
    # Une fusion qui coupe une règle (« garder les deux côtés » au milieu d'un bloc) laisse une
    # accolade ouverte : le navigateur ignore alors silencieusement toutes les règles suivantes.
    for css in sorted(STATIC.rglob("*.css")):
        text = css.read_text(encoding="utf-8")
        assert text.count("{") == text.count("}"), f"{css.name} : accolades déséquilibrées"
