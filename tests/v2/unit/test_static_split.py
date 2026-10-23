"""Découpage des fichiers partagés du front (story 5.0) : textes par domaine, CSS par composant,
appels de l'API par domaine, routes par module. Aucun navigateur : l'équivalence du rendu est jouée
par la suite E2E, qui lit les mêmes textes, styles et routes qu'avant."""

from __future__ import annotations

import json
import re

import pytest

from .static_files import ROOT, STATIC, TEXTS, catalog, component_stylesheets, read, text_file_names

MAX_JS_LINES = 600


# --- Textes ---------------------------------------------------------------------------------


def test_every_text_file_is_declared_once_and_every_declared_file_exists():
    declared = text_file_names()
    assert len(declared) == len(set(declared))
    assert sorted(declared) == sorted(path.stem for path in TEXTS.glob("*.json"))
    assert not (STATIC / "i18n" / "fr.json").exists()  # plus de catalogue unique


def test_two_text_files_never_declare_the_same_top_level_key():
    keys: dict[str, str] = {}
    for path in sorted(TEXTS.glob("*.json")):
        for key in json.loads(path.read_text(encoding="utf-8")):
            assert key not in keys, f"« {key} » : {keys[key]} et {path.name}"
            keys[key] = path.name
    # Le catalogue ajoute `errors`, généré depuis errors.py (jamais dans un fichier, C9).
    assert keys.keys() | {"errors"} == catalog().keys()


def test_the_duplicate_detector_fails_on_a_shared_key(monkeypatch, tmp_path):
    from . import static_files

    (tmp_path / "a.json").write_text('{"home": {"x": "1"}}', encoding="utf-8")
    (tmp_path / "b.json").write_text('{"home": {"y": "2"}}', encoding="utf-8")
    monkeypatch.setattr(static_files, "TEXTS", tmp_path)
    with pytest.raises(AssertionError, match="home"):
        static_files.catalog()


def test_the_loader_refuses_a_key_declared_twice():
    code = read("core/i18n.js")
    assert "if (key in merged) throw" in code and "Promise.all" in code


# --- CSS ------------------------------------------------------------------------------------


def linked_stylesheets(html: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="/static/([\w/.-]+)">', html)


def test_every_component_stylesheet_is_linked_once_in_cascade_order_before_the_screens():
    links = linked_stylesheets(read("index.html"))
    components = component_stylesheets()
    assert len(components) == len(set(components)) >= 15
    on_disk = sorted(f"css/components/{p.name}" for p in (STATIC / "css/components").glob("*.css"))
    assert sorted(components) == on_disk  # aucun fichier oublié, aucun fichier absent
    assert links[: 2 + len(components)] == ["tokens.css", "base.css", *components]
    assert not (STATIC / "components.css").exists()  # remplacé par un fichier par composant
    assert "screens.css" in links and links.index("screens.css") == 2 + len(components)


def test_the_fixtures_load_the_same_component_stylesheets_as_the_shell():
    expected = ["tokens.css", "base.css", *component_stylesheets()]
    for name in ("components", "picker"):
        html = (ROOT / "tests/v2/e2e/fixtures" / f"{name}.html").read_text(encoding="utf-8")
        assert linked_stylesheets(html) == expected, name


def test_no_stylesheet_imports_another_one():
    # axe-core réinjecte une feuille importée dans la page en `<style>` : la politique de contenu
    # (`style-src 'self'`) le refuse et la suite d'accessibilité échoue.
    for path in STATIC.rglob("*.css"):
        assert "@import" not in path.read_text(encoding="utf-8"), path.name


# --- JS -------------------------------------------------------------------------------------


def test_no_front_script_exceeds_600_lines():
    too_long = {
        path.relative_to(STATIC).as_posix(): len(path.read_text(encoding="utf-8").splitlines())
        for path in STATIC.rglob("*.js")
        if "vendor" not in path.parts
    }
    assert {name: n for name, n in too_long.items() if n > MAX_JS_LINES} == {}


def test_every_api_domain_file_is_assembled_by_api_js():
    api = read("core/api.js")
    domains = sorted(path.stem for path in (STATIC / "core/api").glob("*.js"))
    assert domains
    for domain in domains:
        assert f'from "./api/{domain}.js"' in api, domain
        assert f"...{domain}Api(request)," in api, domain
    assert "export async function request" in api and "export class ApiError" in api
    assert "export function uploadDocuments" in api


def test_every_route_file_is_assembled_by_registry_js_in_the_navigation_order():
    registry = read("core/registry.js")
    files = sorted(path.stem for path in (STATIC / "core/routes").glob("*.js"))
    imported = re.findall(r'from "\./routes/([\w-]+)\.js"', registry)
    assert sorted(imported) == files
    modules = re.search(r"MODULES = \[(.*?)\];", registry, re.DOTALL)
    assert modules and len(re.findall(r"\w+Module", modules.group(1))) == len(files)
    assert "export function findScreen" in registry and "export function entryScreen" in registry
