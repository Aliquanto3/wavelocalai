"""Fiche d'un modèle (story 5.6) : règles de structure du front, sans navigateur. Les parcours
(ouverture, disposition, références, bouton du sélecteur, axe) vivent dans `e2e/test_models_card.py`.
"""

from __future__ import annotations

import re

from .static_files import STATIC, catalog, read_static

CARD_FILES = (
    "components/model-card-view.js",
    "components/model-card-loader.js",
    "components/model-card-drawer.js",
    "components/model-card-launcher.js",
    "screens/models-card.js",
)
CODE = "\n".join(
    "\n".join(line for line in read_static(name).splitlines() if not line.lstrip().startswith("//"))
    for name in CARD_FILES
)


def test_the_front_calculates_nothing_it_only_formats_the_published_values():
    # AD-20 : ni débit, ni mémoire, ni énergie recalculés. Seule conversion : une fraction de 0 à 1
    # publiée par le serveur devient un pourcentage entier, au seul endroit `fraction`.
    assert "Math.max" not in CODE and "Math.min" not in CODE and "reduce(" not in CODE
    for field in (
        "decode_tok_s", "ram_peak_gb", "gpu_fraction", "ram_fraction", "wh_per_1k_tokens",
        "measured_tps", "params_active_b", "params_total_b", "short_gb", "needed_gb",
    ):  # fmt: skip
        assert not re.search(rf"{field}\s*[-+*/]|[-+*/]\s*\w*\.?{field}", CODE), field
    assert CODE.count("* 100") == 1
    view = read_static("components/model-card-view.js")
    assert "const fraction" in view and "Math.round(value * 100)" in view


def test_the_energy_is_shown_only_when_it_is_measured():
    view = read_static("components/model-card-view.js")
    assert 'energy.status === "measured"' in view
    assert "energy_unvalidated" in view and "energy_not_measured" in view


def test_an_absent_value_is_unknown_never_zero():
    view = read_static("components/model-card-view.js")
    # Chaque valeur facultative passe par `formatUnknown()` ou un test de `null`.
    assert view.count("formatUnknown()") >= 8
    assert not re.search(r"\?\?\s*0\b|\|\|\s*0\b", view)


def test_the_launcher_adds_a_button_beside_the_picker_not_in_its_option_list():
    launcher = read_static("components/model-card-launcher.js")
    assert "picker.after(box)" in launcher  # frère du sélecteur, jamais dans sa liste
    picker = read_static("components/wl-model-picker.js")
    assert "model-card" not in picker  # le sélecteur, déjà long, n'a pas grossi pour la fiche
    assert "watchModelPickers" in read_static("components/index.js")


def test_the_card_route_takes_a_tag_parameter_and_the_router_can_follow_it_without_remounting():
    assert 'param: "tag"' in read_static("core/routes/models.js")
    router = read_static("core/router.js")
    assert 'typeof entry.module.update === "function"' in router
    models = read_static("screens/models.js")
    assert "export function update(host" in models and "mounted.get(host)?.openCard" in models


def test_the_card_is_read_only_after_the_shell_is_ready_and_never_writes():
    loader = read_static("components/model-card-loader.js")
    assert loader.index("await shellReady()") < loader.index("api.modelCard(")
    api = read_static("core/api/models.js")
    assert re.search(r"modelCard: \(tag\) => request\(`/api/models/card/", api)
    assert "method" not in api[api.index("modelCard:") : api.index("setModelDefault")]


def test_the_new_files_stay_under_600_lines():
    for name in (*CARD_FILES, "screens/models.js", "screens/models-format.js", "models.css"):
        assert len((STATIC / name).read_text(encoding="utf-8").splitlines()) <= 600, name


def test_the_card_texts_put_a_no_break_space_before_double_punctuation():
    texts = catalog()["models"]["card"]
    assert not any(re.search(r" [:;!?]", value) for value in texts.values())
