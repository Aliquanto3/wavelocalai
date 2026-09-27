"""
Sobriété et matériel, dans l'app réelle : CO₂ de session et historique lus dans le fichier
que CodeCarbon écrit (dossier temporaire de l'app), accélérateur détecté.

Constats couverts : F5 et CAP-4 (CO₂ de session dans la bonne unité, à moins de 5 % du CSV),
F6 et U16 (la session apparaît dans l'historique, en barres par session, unité CO₂ réelle),
F11 (accélérateur détecté, jamais « Actif » en dur), U13 (aucun delta détourné).
"""

import csv
import platform
import shutil
import subprocess

import pytest

from src.app.modules import SOBRIETY
from tests.e2e import helpers as h

pytestmark = pytest.mark.e2e

SESSION_PROJECT = "wavelocal_session"  # src/core/green_monitor.py
# Laisse CodeCarbon relever quelques mesures (une par seconde) avant l'arrêt.
MEASURE_WAIT_MS = 5_000


def _last_session_row_g(app) -> float:
    """Émissions (g) de la dernière ligne du suivi de session dans le CSV de CodeCarbon."""
    path = app.data_dir / "logs" / "emissions.csv"
    assert path.is_file(), f"CodeCarbon n'a pas écrit {path}"
    with open(path, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("project_name") == SESSION_PROJECT]
    assert rows, f"aucune ligne « {SESSION_PROJECT} » dans {path}"
    return float(rows[-1]["emissions"]) * 1000.0


def test_session_co2_matches_codecarbon_and_history(page, app):
    """« Arrêter et enregistrer » : CO₂ affiché à moins de 5 % de la ligne du CSV (unité
    annoncée juste), puis la session apparaît dans l'historique, en barres par session."""
    h.goto(page, app.base_url, SOBRIETY.url_path)
    main = h.main(page)
    assert main.get_by_text("Suivi carbone actif").count() == 1
    page.wait_for_timeout(MEASURE_WAIT_MS)

    main.get_by_role("button", name="Arrêter et enregistrer").click()
    h.settle_after_action(page, until=main.get_by_text("Suivi carbone en pause"))
    shown = h.metric_value(main, "Total de la session")
    shown_g = h.parse_co2_grams(shown)
    csv_g = _last_session_row_g(app)
    assert csv_g > 0, "CodeCarbon a mesuré 0 g : mesure impossible sur cette machine ?"
    assert abs(shown_g - csv_g) <= 0.05 * csv_g, f"UI « {shown} » contre CSV {csv_g} g"
    assert main.get_by_text("Suivi carbone en pause").count() == 1

    # Historique : le fichier écrit par le suivi est celui que lit le graphique.
    assert main.get_by_text("Aucune session mesurée pour l'instant.").count() == 0
    chart = main.locator('[data-testid="stPlotlyChart"]').first
    chart.wait_for(timeout=h.PAGE_TIMEOUT_MS)
    page.wait_for_function(
        "e => e.innerText.includes('Émissions de CO₂ par session')",
        arg=chart.element_handle(),
        timeout=h.PAGE_TIMEOUT_MS,
    )
    chart_text = h.flat(chart.inner_text())
    assert "Cumul" not in chart_text
    assert "µ" not in chart_text
    assert "CO₂ (" in chart_text
    assert main.get_by_text("Voir les données").count() == 1
    assert main.locator('[data-testid="stMetricDelta"]').count() == 0
    assert h.ui_errors(page) == []

    # Reprise : le suivi repart.
    main.get_by_role("button", name="Reprendre le suivi").click()
    h.settle_after_action(page, until=main.get_by_text("Suivi carbone actif"))


def _nvidia_gpu_names() -> list[str]:
    """Noms des GPU NVIDIA selon `nvidia-smi` (liste vide sans pilote NVIDIA)."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        out = subprocess.run(  # noqa: S603
            [exe, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def test_accelerator_is_detected_not_assumed(page, app):
    """« Accélérateur IA » : le nom du GPU que voit la machine (nvidia-smi), la puce Apple, ou
    « Aucun » sans GPU ; jamais « Actif » ni « CPU Only » écrits en dur (F11)."""
    h.goto(page, app.base_url, SOBRIETY.url_path)
    main = h.main(page)
    value = h.metric_value(main, "Accélérateur IA")
    names = _nvidia_gpu_names()
    if names:
        # Un GPU : son nom ; plusieurs : « 2 × nom » ou « nom + nom » (src/core/accelerator.py).
        assert all(name in value for name in set(names)), f"« {value} » contre nvidia-smi {names}"
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        assert value == "Apple Silicon", value
    else:
        # Ni NVIDIA ni Apple : l'app ne cherche pas d'autre GPU, elle affiche « Aucun ».
        assert value == "Aucun", value
        assert main.get_by_text("Aucun GPU NVIDIA ni Apple détecté").count() == 1
