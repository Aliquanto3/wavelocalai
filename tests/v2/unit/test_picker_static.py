"""Sélecteur de modèle et état de run (story 1.10) : textes et règles de structure, sans navigateur.
Les parcours (clavier, filtre, mode multi, cloud coupé, run du `fake`, axe) vivent dans
`tests/v2/e2e/test_picker.py`."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "src" / "wavelocalai" / "web" / "static"
SOURCES = {
    "picker": (STATIC / "components/wl-model-picker.js").read_text(encoding="utf-8"),
    "run_status": (STATIC / "components/wl-run-status.js").read_text(encoding="utf-8"),
}
CATALOG = json.loads((STATIC / "i18n/fr.json").read_text(encoding="utf-8"))["components"]


def test_every_picker_and_run_status_text_is_used_by_its_component():
    for group, source in SOURCES.items():
        used = set(re.findall(rf"""["']components\.{group}\.(\w+)["']""", source))
        assert used == set(CATALOG[group]), group


def test_components_are_exported_by_the_shared_index():
    index = (STATIC / "components/index.js").read_text(encoding="utf-8")
    assert "wl-model-picker.js" in index and "wl-run-status.js" in index


def test_components_use_no_shadow_dom_and_the_single_sse_client():
    for source in SOURCES.values():
        assert "attachShadow" not in source and "EventSource" not in source
    assert "../core/sse.js" in SOURCES["run_status"]
    assert "../core/store.js" in SOURCES["picker"]


def test_the_picker_never_proposes_embedding_models_and_computes_no_memory_fit():
    source = SOURCES["picker"]
    assert 'model.kind === "chat"' in source
    # `fits` et `needed_gb` viennent de l'API : le front ne les recalcule pas (AD-20).
    assert "available_gb" not in source and "total_gb" not in source
