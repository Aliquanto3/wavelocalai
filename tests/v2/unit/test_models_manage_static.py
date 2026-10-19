"""Écran Modèles, décharger, supprimer et choisir ses défauts (story 5.4) : règles de structure du
front, sans navigateur. Les parcours vivent dans `e2e/test_models_manage.py`."""

from __future__ import annotations

import re

from .static_files import STATIC, read_static

UNLOAD = read_static("screens/models-unload.js")
DELETE = read_static("screens/models-delete.js")
DEFAULTS = read_static("screens/models-defaults.js")
SCREEN = read_static("screens/models.js")
INSTALLED = read_static("screens/models-installed.js")


def code(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def test_each_write_has_a_single_caller_in_the_screen_folder():
    """Décharger, supprimer et écrire un défaut n'ont chacun qu'un appelant : aucun autre module de
    l'écran ne les déclenche (un geste, un fichier)."""
    callers = {
        "unloadModels": "models-unload.js",
        "deleteModel": "models-delete.js",
        "setModelDefault": "models-defaults.js",
        "clearModelDefault": "models-defaults.js",
    }
    for call, owner in callers.items():
        found = sorted(
            path.name
            for path in (STATIC / "screens").glob("models*.js")
            if re.search(rf"api\.{call}\(", code(path.read_text(encoding="utf-8")))
        )
        assert found == [owner], (call, found)


def test_a_deletion_always_goes_through_the_confirmation_dialog():
    body = code(DELETE)
    assert "wl-confirm-dialog" in body
    assert body.index("dialog.ask(") < body.index("api.deleteModel(")
    assert "if (!confirmed) return" in body
    # Le bouton n'appelle jamais l'API : il ouvre le dialogue (`onDelete`).
    assert "api." not in code(INSTALLED)


def test_the_delete_button_stays_focusable_when_disabled_and_says_why():
    body = code(INSTALLED)
    assert 'setAttribute("aria-disabled"' in body and "aria-describedby" in body
    assert ".disabled" not in body  # jamais `disabled` : le bouton perdrait le focus
    unload = code(UNLOAD)
    assert 'setAttribute("aria-disabled"' in unload and ".disabled" not in unload
    assert "models-unload-reason" in unload or "why.id" in unload


def test_the_defaults_picker_is_filtered_on_eligibility_and_the_front_decides_nothing():
    body = code(DEFAULTS)
    assert 'setAttribute("eligible-only", "")' in body
    # Le serveur dit qui est éligible ; le front ne compare ni outils ni paramètres.
    assert not re.search(r"tools_verified|params_active_b|params_total_b", body)
    picker = read_static("components/wl-model-picker.js")
    assert '"eligible-only"' in picker and "this.#defaults?.eligible" in picker


def test_the_defaults_are_read_only_after_the_shell_is_ready():
    read = SCREEN[SCREEN.index("async function read()") :]
    assert read.index("await shellReady()") < read.index("defaults.load(")
    assert SCREEN.count("defaults.load(") == 1
    # Un module écrit ne lit rien à sa création : aucun appel hors d'un geste ou de `load`.
    for name, text in (("unload", UNLOAD), ("delete", DELETE)):
        assert "api.modelDefaults(" not in code(text), name


def test_the_stream_state_carries_the_models_a_run_uses():
    system = read_static("core/system.js")
    assert "modelsInUse: data.models_in_use" in system
    assert "modelsInUse" in read_static("core/store.js")


def test_the_new_files_and_the_shared_components_stay_under_600_lines():
    names = (
        "screens/models.js",
        "screens/models-unload.js",
        "screens/models-delete.js",
        "screens/models-defaults.js",
        "screens/models-installed.js",
        "components/wl-model-picker.js",
        "components/model-picker-option.js",
        "components/wl-confirm-dialog.js",
        "components/wl-data-table.js",
        "models.css",
    )
    for name in names:
        assert len((STATIC / name).read_text(encoding="utf-8").splitlines()) <= 600, name
