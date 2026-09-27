"""
Chiffres justes (story 6), avec AppTest : CO₂ de session et historique d'émissions de
« Sobriété et matériel », débit, chargement et durée totale de l'Arène des modèles.

Aucun Ollama ni réseau : tracker et inférence simulés, fichiers d'émissions sous tmp_path
(tests/app/conftest.py redirige LOGS_DIR et EMISSIONS_DIR).
Usage: python -m pytest tests/app/test_figures.py -v
"""

import base64
import json
import re
from datetime import datetime, timedelta

import numpy as np
import pytest
from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df

from src.app.charts import THEME_CATEGORY_TOKENS, THEME_TEXT_TOKEN
from src.app.formatting import NBSP, NNBSP
from src.app.states import THROUGHPUT_HELP
from src.app.ui import badge_markdown
from tests.app.conftest import FAKE_LOCAL_MODELS
from tests.app.test_states import (  # noqa: F401 (fixtures partagées : run_page, indexed_base)
    ARENA_PAGE,
    HARDWARE_PAGE,
    RAG_PAGE,
    _app,
    _button,
    _friendly,
    _metric,
    _results_table,
    _run_arena,
    _run_evaluation,
    indexed_base,
    run_page,
)

# Badge Local en directive Markdown (story 8), en tête des métadonnées d'une réponse.
LOCAL_BADGE = badge_markdown(False)

CSV_HEADER = "timestamp,project_name,run_id,duration,emissions\n"


class FakeTracker:
    """GreenTracker simulé : stop() renvoie des grammes, comme le vrai."""

    def __init__(self, emissions_g: float, running: bool = True):
        self.emissions_g = emissions_g
        self._is_running = running

    def start(self):
        self._is_running = True

    def stop(self) -> float:
        self._is_running = False
        return self.emissions_g


_UNSET = object()


def _hardware_page(tracker=None, last_emissions=_UNSET):
    at = _app(HARDWARE_PAGE)
    if tracker is not None:
        at.session_state["tracker"] = tracker
    if last_emissions is not _UNSET:
        at.session_state["last_emissions"] = last_emissions
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _captions(at):
    return [c.value for c in at.caption]


# ---------------------------------------------------------------------------
# Sobriété et matériel : CO₂ de session
# ---------------------------------------------------------------------------


def test_session_co2_unit_and_value():
    """stop() = 0,42 g : « 420 mgCO₂ » (jamais des grammes sous l'unité kgCO₂), km calculés
    depuis 0,00042 kg."""
    at = _hardware_page(FakeTracker(0.42, running=False), last_emissions=0.42)

    assert _metric(at, "Total de la session") == f"420{NBSP}mgCO₂"
    # 0,00042 kg / 0,110 kg/km = 0,00382 km (et non 3,82 km depuis des grammes).
    assert f"soit environ 0,00382{NBSP}km en voiture" in _captions(at)


def test_session_co2_after_stop_button():
    """« Arrêter et enregistrer » : la valeur affichée est celle renvoyée par stop()."""
    at = _hardware_page(FakeTracker(1234.0))
    _button(at, "Arrêter et enregistrer").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert _metric(at, "Total de la session") == f"1,23{NBSP}kgCO₂"
    assert f"soit environ 11,2{NBSP}km en voiture" in _captions(at)


# ---------------------------------------------------------------------------
# Sobriété et matériel : historique des émissions
# ---------------------------------------------------------------------------


def _decode(values):
    """Tableau d'une trace Plotly : liste JSON ou tableau binaire (« bdata »)."""
    if isinstance(values, dict) and "bdata" in values:
        return np.frombuffer(base64.b64decode(values["bdata"]), dtype=values["dtype"]).tolist()
    return list(values)


def _history_figure(at):
    (chart,) = at.get("plotly_chart")
    return json.loads(chart.proto.spec)


def _chart_values(at):
    figure = _history_figure(at)
    return [v for trace in figure["data"] for v in _decode(trace["y"])]


def _axis_title(axis: dict) -> str:
    """Titre d'un axe ou d'une figure (layout), texte seul."""
    title = axis.get("title")
    return title.get("text") if isinstance(title, dict) else title


def _stamp(delta: timedelta) -> str:
    """Horodatage local relatif à maintenant (les fenêtres de temps partent de l'heure
    courante : des dates fixes sortiraient de la fenêtre par défaut avec le temps)."""
    return (datetime.now() - delta).isoformat(timespec="seconds")


def _write_sessions(env, sessions):
    """Écrit le fichier du suivi : (écart avec maintenant, grammes) par session."""
    rows = "".join(
        f"{_stamp(delta)},wavelocal_session,run{i},10,{grams / 1000}\n"
        for i, (delta, grams) in enumerate(sessions)
    )
    (env / "logs" / "emissions.csv").write_text(CSV_HEADER + rows, encoding="utf-8")


def test_history_without_file():
    """Aucun fichier d'émissions : message d'état vide, pas de graphique ni d'avertissement."""
    at = _hardware_page(FakeTracker(0.0))

    assert "Aucune session mesurée pour l'instant." in [i.value for i in at.info]
    assert not at.get("plotly_chart")
    assert not [w.value for w in at.warning if "historique" in w.value]


def test_history_reads_tracker_file_and_ignores_benchmark(offline_app_env):
    """L'historique lit le fichier du suivi (logs/emissions.csv), suivi de session seulement ;
    le fichier du benchmark (logs/emissions/emissions.csv) est ignoré. Valeurs en mg."""
    logs_dir = offline_app_env / "logs"
    (logs_dir / "emissions.csv").write_text(
        CSV_HEADER
        + f"{_stamp(timedelta(hours=5))},wavelocal_session,a,10,0.00042\n"
        + f"{_stamp(timedelta(hours=4))},wavelocal_audit,b,10,0.00081\n"
        + f"{_stamp(timedelta(hours=3))},crew_mission,c,10,0.0005\n"
        + f"{_stamp(timedelta(hours=2))},codecarbon,d,10,0.9\n"
        + f"{_stamp(timedelta(hours=1))},wavelocal_session,e,10,0.00063\n",
        encoding="utf-8",
    )
    bench_dir = logs_dir / "emissions"
    bench_dir.mkdir()
    (bench_dir / "emissions.csv").write_text(
        CSV_HEADER + f"{_stamp(timedelta(minutes=30))},benchmark_slm,f,10,0.777\n",
        encoding="utf-8",
    )

    at = _hardware_page(FakeTracker(0.0))

    assert _chart_values(at) == pytest.approx([420, 630])


def test_history_matches_real_tracker(offline_app_env):
    """CAP-4 : le CO₂ affiché (stop()) et la ligne lue par l'historique viennent du même
    tracker, dans le même fichier : écart < 5 %."""
    from src.app.formatting import CO2_UNITS
    from src.core.green_monitor import SESSION_PROJECT, GreenTracker

    tracker = GreenTracker(SESSION_PROJECT)
    tracker.start()
    emissions_g = tracker.stop()

    at = _hardware_page(FakeTracker(0.0, running=False), last_emissions=emissions_g)

    (logged,) = _chart_values(at)
    unit = _axis_title(_history_figure(at)["layout"]["yaxis"]).removeprefix("CO₂ (")[:-1]
    assert logged * CO2_UNITS[unit] == pytest.approx(emissions_g, rel=0.05, abs=1e-12)


def test_history_bars_per_session_in_rule_unit(offline_app_env):
    """Sessions de 0,42 g, 0,63 g et 1,2 g : barres par session, en mg (unité de la règle),
    titre qui dit ce qui est tracé, unité dans le titre d'axe, un seul axe y."""
    _write_sessions(
        offline_app_env,
        [(timedelta(hours=3), 0.42), (timedelta(hours=2), 0.63), (timedelta(hours=1), 1.2)],
    )
    at = _hardware_page(FakeTracker(0.0))

    figure = _history_figure(at)
    (trace,) = figure["data"]
    assert trace["type"] == "bar"
    assert "fill" not in trace and "line" not in trace
    # Une seule série : première couleur de la palette du thème (jeton, jamais un hex).
    assert trace["marker"]["color"] == THEME_CATEGORY_TOKENS[0]
    assert _decode(trace["y"]) == pytest.approx([420, 630, 1200])
    layout = figure["layout"]
    assert _axis_title(layout) == "Émissions de CO₂ par session"
    assert _axis_title(layout["yaxis"]) == "CO₂ (mg)"
    assert "yaxis2" not in layout
    assert layout["separators"] == f",{NNBSP}"
    # Info-bulle : date et CO₂ au format fr-FR ; dates numériques sur l'axe.
    assert re.fullmatch(rf"\d\d/\d\d/\d{{4}} \d\d:\d\d<br>420{NBSP}mgCO₂", trace["hovertext"][0])
    assert trace["hovertext"][2].endswith(f"<br>1{NNBSP}200{NBSP}mgCO₂")
    formats = {stop["value"] for stop in layout["xaxis"]["tickformatstops"]}
    assert formats == {"%d/%m %H:%M", "%d/%m"}


def test_history_gap_between_sessions_stays_empty(offline_app_env):
    """Sessions à deux heures d'écart, rien entre : deux barres séparées, sans liaison (ni
    ligne ni aire) ; aucune barre ne s'étend jusqu'à sa voisine."""
    _write_sessions(offline_app_env, [(timedelta(hours=3), 0.42), (timedelta(hours=1), 0.63)])
    at = _hardware_page(FakeTracker(0.0))

    (trace,) = _history_figure(at)["data"]
    assert trace["type"] == "bar" and trace.get("mode") is None
    first, second = (datetime.fromisoformat(x) for x in trace["x"])
    gap_ms = (second - first).total_seconds() * 1000
    widths = _decode(trace["width"])
    # Deux demi-barres ne couvrent pas l'écart : un vide reste visible entre elles.
    assert widths[0] / 2 + widths[1] / 2 < gap_ms


def _period(at):
    (control,) = [b for b in at.button_group if b.label == "Période"]
    return control


def test_history_time_window(offline_app_env):
    """Sessions sur 40 jours : 7 derniers jours par défaut, puis 30 jours, puis tout ; la
    fenêtre est choisie par l'utilisateur."""
    _write_sessions(
        offline_app_env,
        [(timedelta(days=40), 1.2), (timedelta(days=10), 0.63), (timedelta(days=1), 0.42)],
    )
    at = _hardware_page(FakeTracker(0.0))

    assert _period(at).options == ["7 derniers jours", "30 derniers jours", "Tout"]
    assert _period(at).value == "7 derniers jours"
    assert _chart_values(at) == pytest.approx([420])

    _period(at).set_value("30 derniers jours").run()
    assert _chart_values(at) == pytest.approx([630, 420])

    _period(at).set_value("Tout").run()
    assert _chart_values(at) == pytest.approx([1200, 630, 420])
    # « Tout » : l'année sur l'axe des dates.
    formats = {s["value"] for s in _history_figure(at)["layout"]["xaxis"]["tickformatstops"]}
    assert formats == {"%d/%m/%Y %H:%M", "%d/%m/%Y"}


def test_history_empty_window(offline_app_env):
    """Aucune session sur la période choisie : message dédié, pas de graphique vide ; la
    fenêtre reste modifiable."""
    _write_sessions(offline_app_env, [(timedelta(days=40), 0.42)])
    at = _hardware_page(FakeTracker(0.0))

    # Des sessions plus anciennes existent : le message les compte et invite à « Tout ».
    assert (
        f"Aucune session sur cette période. 1{NBSP}session plus ancienne : choisissez « Tout » "
        "pour les afficher." in [i.value for i in at.info]
    )
    assert "Aucune session mesurée pour l'instant." not in [i.value for i in at.info]
    assert not at.get("plotly_chart")

    _period(at).set_value("Tout").run()
    assert _chart_values(at) == pytest.approx([420])


def test_history_table_view(offline_app_env):
    """Vue tableau repliée sous le graphique : date et CO₂ dans l'unité du graphique."""
    _write_sessions(offline_app_env, [(timedelta(hours=2), 0.42), (timedelta(hours=1), 1.2)])
    at = _hardware_page(FakeTracker(0.0))

    (expander,) = [e for e in at.expander if e.label == "Voir les données"]
    (table,) = expander.dataframe
    assert list(table.value["CO₂"]) == pytest.approx([420, 1200])
    assert json.loads(table.proto.columns)["CO₂"]["label"] == "CO₂ (mg)"


def test_malformed_history_shows_readable_warning(offline_app_env):
    (offline_app_env / "logs" / "emissions.csv").write_text(
        CSV_HEADER
        + "2026-09-26T09:15:00,wavelocal_session,a,10,0.00042\n"
        + "2026-09-26T09:20:00,wavelocal_session,b,10,0.00042,x,y\n",
        encoding="utf-8",
    )
    at = _hardware_page(FakeTracker(0.0))

    (warning,) = [w.value for w in at.warning if "historique" in w.value]
    assert "mal formé" in warning
    assert "Error" not in warning


def test_session_value_missing_hides_km():
    """Valeur de session absente : « — », pas de ligne « soit environ 0 km »."""
    at = _hardware_page(FakeTracker(0.0, running=False), last_emissions=None)

    assert _metric(at, "Total de la session") == "—"
    assert not [c for c in _captions(at) if c.startswith("soit environ")]


def test_tracking_unavailable_is_not_empty_history(monkeypatch):
    """Module de suivi non importable : « Suivi carbone indisponible », jamais « Aucune
    session mesurée »."""
    import sys

    monkeypatch.setitem(sys.modules, "src.core.green_monitor", None)
    at = _hardware_page()

    warnings = [w.value for w in at.warning]
    assert any(w.startswith("Suivi carbone indisponible") for w in warnings)
    assert "Aucune session mesurée pour l'instant." not in [i.value for i in at.info]
    assert "Suivi carbone en pause" not in warnings


# ---------------------------------------------------------------------------
# Arène des modèles : débit, chargement et durée totale ; une unité de CO₂
# ---------------------------------------------------------------------------


def test_lab_shows_load_and_total_apart(fake_inference, run_page):
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]

    assert _metric(at, "Débit") == f"25,0{NBSP}tokens/s"
    (throughput,) = [m for m in at.metric if m.label == "Débit"]
    assert throughput.help == THROUGHPUT_HELP
    assert _metric(at, "Chargement") == f"0,1{NBSP}s"
    assert _metric(at, "Durée totale") == f"1,6{NBSP}s"
    assert _metric(at, "CO₂") == f"7,6{NBSP}mgCO₂"


@pytest.fixture
def cloud_like_inference(monkeypatch, fake_inference):
    """Résultat d'un fournisseur cloud : ni chargement ni durée de génération mesurés."""
    from src.core.inference_service import InferenceService

    fake_run = InferenceService.run_inference

    async def cloud_like(*args, **kwargs):
        result = await fake_run(*args, **kwargs)
        if result.metrics is not None:
            result.metrics.load_measured = False
            result.metrics.eval_duration_s = None
        return result

    monkeypatch.setattr(InferenceService, "run_inference", staticmethod(cloud_like))
    return fake_inference


def test_lab_without_load_measure_hides_load(cloud_like_inference, run_page):
    """Fournisseur cloud : pas de « Chargement », débit signalé « estimé »."""
    at = run_page(ARENA_PAGE)
    _button(at, "Lancer le test").click().run()
    assert not at.exception, [e.value for e in at.exception]

    labels = [m.label for m in at.metric]
    assert "Débit" in labels and "Durée totale" in labels
    assert "Chargement" not in labels
    assert _metric(at, "Débit") == f"25,0{NBSP}tokens/s (estimé)"


def test_chat_footer_shows_load_apart(fake_inference, run_page):
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    # Badge Local du modèle qui a répondu (story 8), puis les mesures.
    footer = (
        f"{LOCAL_BADGE} · 7,6{NBSP}mgCO₂ · 25,0{NBSP}tokens/s · Chargement 0,1{NBSP}s · "
        f"Durée totale 1,6{NBSP}s"
    )
    (caption,) = [c for c in at.caption if c.value == footer]
    assert caption.help == THROUGHPUT_HELP


def test_chat_footer_estimated_throughput(cloud_like_inference, run_page):
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    footer = (
        f"{LOCAL_BADGE} · 7,6{NBSP}mgCO₂ · 25,0{NBSP}tokens/s (estimé) · Durée totale 1,6{NBSP}s"
    )
    assert footer in _captions(at)


def test_chat_session_total(fake_inference, run_page):
    """« Session : … » : somme des réponses (2 × 7,6 mg), convertie par la règle CO₂."""
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    at.chat_input[0].set_value("Encore").run()
    assert not at.exception, [e.value for e in at.exception]

    assert f"Session : **15,2{NBSP}mgCO₂**" in _captions(at)


def _bubble_texts(at):
    """Étiquettes directes des points de la matrice de l'Arène (annotations reliées)."""
    (chart,) = at.get("plotly_chart")
    figure = json.loads(chart.proto.spec)
    return [a["text"] for a in figure["layout"].get("annotations", [])]


def test_arena_same_co2_unit_for_all_rows(fake_inference, run_page):
    """Une ligne à 7,6 mg, l'autre à 1,14 g : toutes deux en mg (unité de la plus petite,
    lisible dans le tableau) ; chargement à part."""
    small, big = (m["model"] for m in FAKE_LOCAL_MODELS)
    fake_inference.output_tokens[big] = 6000  # 6000 × 0,19 mg = 1,14 g
    fake_inference.judge_reply = "Note : 72/100"
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    table = _results_table(at)
    assert list(table["CO₂"]) == pytest.approx([7.6, 1140])
    assert list(table["Chargement"]) == pytest.approx([0.1, 0.1])
    assert list(table["Durée totale"]) == pytest.approx([1.6, 1.6])
    assert list(table["Débit"]) == pytest.approx([25.0, 25.0])

    captions = _captions(at)
    assert any(c.startswith("CO₂ : ") and c.endswith(f"{NBSP}mgCO₂") for c in captions)
    assert f"Chargement 0,1{NBSP}s · Durée totale 1,6{NBSP}s" in captions

    names = {_friendly(m): m["model"] for m in FAKE_LOCAL_MODELS}
    expected = {small: f"7,6{NBSP}mgCO₂", big: f"1{NNBSP}140{NBSP}mgCO₂"}
    texts = _bubble_texts(at)
    assert sorted(texts) == sorted(
        f"<b>{name}</b><br>{expected[tag]}" for name, tag in names.items()
    )


# ---------------------------------------------------------------------------
# Arène des modèles : matrice note / débit lisible et juste (story 10)
# ---------------------------------------------------------------------------

GRANITE = {
    "model": "granite4:3b",
    "size": 2_100_000_000,
    "digest": "3" * 64,
    "details": {"family": "granite", "parameter_size": "3B", "quantization_level": "Q4_K_M"},
    "type": "local",
    "provider": "ollama",
}
GRANITE_NAME = "Granite 4.0 3B Instruct"


@pytest.fixture
def granite_installed(monkeypatch):
    """Trois modèles locaux installés, dont un au nom long du catalogue."""
    from src.core.llm_provider import LLMProvider
    from src.core.models_db import MODELS_DB

    MODELS_DB[GRANITE_NAME] = {
        **MODELS_DB["Qwen 2.5 1.5B"],
        "ollama_tag": GRANITE["model"],
        "editor": "IBM",
        "params_tot": "3B",
        "params_act": "3B",
    }
    models = [*FAKE_LOCAL_MODELS, GRANITE]
    monkeypatch.setattr(
        LLMProvider,
        "list_models",
        staticmethod(lambda cloud_enabled=True: [dict(m) for m in models]),
    )
    return models


def _arena_figure(at):
    (chart,) = at.get("plotly_chart")
    return json.loads(chart.proto.spec)


def _traces_by_name(figure):
    return {trace["name"]: trace for trace in figure["data"]}


def test_arena_matrix_axes_legends_and_labels(granite_installed, fake_inference, run_page):
    """3 modèles à 5,8, 5,9 et 6,0 tokens/s : axe du débit depuis 0, légende des modèles,
    légende de taille (CO₂), étiquettes vers l'intérieur du cadre, nom long complet."""
    speeds = {"qwen2.5:1.5b": 5.8, "gemma3:1b": 5.9, GRANITE["model"]: 6.0}
    fake_inference.throughput.update(speeds)
    fake_inference.output_tokens.update(
        {"qwen2.5:1.5b": 40, "gemma3:1b": 80, GRANITE["model"]: 160}
    )
    at = run_page(ARENA_PAGE)
    _run_arena(at, granite_installed)

    figure = _arena_figure(at)
    layout = figure["layout"]
    # Un seul axe y, sur /100 ; axe du débit de 0 au maximum plus une marge.
    assert "yaxis2" not in layout
    assert layout["xaxis"]["range"][0] == 0
    assert layout["xaxis"]["range"][1] == pytest.approx(6.0 * 1.15)
    assert layout["yaxis"]["tickvals"] == [0, 20, 40, 60, 80, 100]
    assert "CO₂" in layout["title"]["text"]

    # Légende des modèles, noms complets (graphique, légende et tableau).
    assert layout["showlegend"] is True
    traces = _traces_by_name(figure)
    names = [_friendly(m) for m in granite_installed]
    assert GRANITE_NAME in names
    assert sorted(traces) == sorted(names)
    assert all(trace["mode"] == "markers" for trace in traces.values())
    assert GRANITE_NAME in set(_results_table(at)["Modèle"])

    # Étiquettes directes : nom complet et CO₂, reliées à leur point, du côté intérieur (les
    # points sont dans la moitié droite de l'axe), sans chevauchement (notes toutes à 85).
    annotations = layout["annotations"]
    assert sorted(a["text"].split("<br>")[0] for a in annotations) == sorted(
        f"<b>{name}</b>" for name in names
    )
    for annotation in annotations:
        assert annotation["showarrow"] is True
        assert annotation["font"]["color"] == THEME_TEXT_TOKEN
        assert annotation["xanchor"] == "right" and annotation["ax"] < 0
        assert annotation["ayref"] == "y" and 0 <= annotation["ay"] <= 100
    label_ys = sorted(a["ay"] for a in annotations)
    assert all(b - a >= 13 - 1e-9 for a, b in zip(label_ys[:-1], label_ys[1:], strict=True))

    # Légende de taille : surface proportionnelle au CO₂ (40, 80, 160 tokens).
    sizes = {name: trace["marker"]["size"] for name, trace in traces.items()}
    qwen, gemma = (_friendly(m) for m in FAKE_LOCAL_MODELS)
    assert sizes[GRANITE_NAME] == pytest.approx(44)
    assert sizes[gemma] == pytest.approx(44 / 2**0.5)
    assert sizes[qwen] == pytest.approx(22)
    assert f"Taille du point : CO₂ de la réponse, de 7,6{NBSP}mgCO₂ à 30,4{NBSP}mgCO₂." in " ".join(
        _captions(at)
    )


def test_arena_winner_star_and_minimum_size(fake_inference, run_page):
    """Le vainqueur (le plus rapide, le moins de CO₂) : étoile sur sa trace seulement, au moins
    25 px même si son CO₂ donnerait un point minuscule ; la légende de taille le dit.
    Légende des modèles horizontale sous le graphique."""
    small, big = (m["model"] for m in FAKE_LOCAL_MODELS)
    fake_inference.throughput.update({small: 30.0, big: 20.0})
    fake_inference.output_tokens.update({small: 10, big: 1000})
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    figure = _arena_figure(at)
    traces = _traces_by_name(figure)
    winner, other = (_friendly(m) for m in FAKE_LOCAL_MODELS)
    assert traces[winner]["marker"]["symbol"] == "star"
    assert traces[other]["marker"]["symbol"] != "star"
    assert traces[winner]["marker"]["size"] == pytest.approx(25)
    assert traces[other]["marker"]["size"] == pytest.approx(44)
    assert any(f"au moins 25{NBSP}px quel que soit son CO₂" in c for c in _captions(at))

    legend = figure["layout"]["legend"]
    assert legend["orientation"] == "h"
    assert legend["yref"] == "container" and legend["yanchor"] == "bottom"


def test_arena_colors_follow_the_model(three_models, fake_inference, run_page):
    """Modèles A, B, C puis B, C seulement : B et C gardent leur couleur. Couleurs de la
    palette du thème (jetons remplacés par Streamlit), jamais en dur, distinctes."""
    from tests.app.conftest import THIRD_LOCAL_MODEL

    models = [*FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL]
    at = run_page(ARENA_PAGE)
    _run_arena(at, models)
    first = {n: t["marker"]["color"] for n, t in _traces_by_name(_arena_figure(at)).items()}
    assert len(set(first.values())) == 3
    assert set(first.values()) <= set(THEME_CATEGORY_TOKENS[:4])

    _run_arena(at, models[1:])
    second = {n: t["marker"]["color"] for n, t in _traces_by_name(_arena_figure(at)).items()}
    assert set(second) == {_friendly(m) for m in models[1:]}
    assert second == {name: first[name] for name in second}


def test_arena_color_ignores_rank_and_failures(three_models, fake_inference, run_page):
    """Un modèle en échec n'est pas tracé : les autres gardent la couleur de leur place dans
    la sélection, pas celle de leur rang."""
    from tests.app.conftest import THIRD_LOCAL_MODEL

    models = [*FAKE_LOCAL_MODELS, THIRD_LOCAL_MODEL]
    fake_inference.timeouts.add(models[0]["model"])
    at = run_page(ARENA_PAGE)
    _run_arena(at, models)

    colors = {n: t["marker"]["color"] for n, t in _traces_by_name(_arena_figure(at)).items()}
    assert colors == {
        _friendly(models[1]): THEME_CATEGORY_TOKENS[1],
        _friendly(models[2]): THEME_CATEGORY_TOKENS[2],
    }


def test_arena_single_scored_model_has_no_legend_box(fake_inference, run_page):
    """Un seul modèle noté (l'autre en échec) : une série, pas de boîte de légende ; le
    titre et l'étiquette le nomment."""
    fake_inference.timeouts.add(FAKE_LOCAL_MODELS[1]["model"])
    at = run_page(ARENA_PAGE)
    _run_arena(at, FAKE_LOCAL_MODELS)

    figure = _arena_figure(at)
    assert figure["layout"]["showlegend"] is False
    (annotation,) = figure["layout"]["annotations"]
    assert annotation["text"].startswith(f"<b>{_friendly(FAKE_LOCAL_MODELS[0])}</b>")


# ---------------------------------------------------------------------------
# Assistant documentaire : badge CO₂ de la Discussion, unité de l'évaluation
# ---------------------------------------------------------------------------


def _rag_stream(tokens_by_tag=None):
    from src.core.metrics import InferenceMetrics

    async def stream(model_name, messages, temperature=0.7, system_prompt=None):
        yield "Réponse simulée."
        output = (tokens_by_tag or {}).get(model_name, 20)
        yield InferenceMetrics(model_name, 10, output, 1.0, 0.1, 20.0)

    return stream


def test_documents_chat_co2_badge(monkeypatch, indexed_base, run_page):
    """20 tokens × 0,19 mg = 3,8 mg : badge « 3,8 mgCO₂ » (mg convertis en grammes)."""
    from src.core.llm_provider import LLMProvider

    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_rag_stream()))
    at = run_page(RAG_PAGE)
    at.chat_input[0].set_value("Quels sont les risques ?").run()
    assert not at.exception, [e.value for e in at.exception]

    assert any(c.endswith(f" · 3,8{NBSP}mgCO₂") for c in _captions(at))


def _vega_spec(at):
    (chart,) = at.get("vega_lite_chart")
    return json.loads(chart.proto.spec)


@pytest.mark.parametrize(
    ("tokens", "unit", "podium"),
    [
        # 3,8 mg et 1,14 g : unité de la plus petite, mg.
        ((20, 6000), "mg", [f"3,8{NBSP}mgCO₂", f"1{NNBSP}140{NBSP}mgCO₂"]),
        # 1,14 g et 11,4 g : g.
        ((6000, 60000), "g", [f"1,14{NBSP}gCO₂", f"11,4{NBSP}gCO₂"]),
    ],
)
def test_documents_evaluation_common_co2_unit(
    monkeypatch, indexed_base, run_page, tokens, unit, podium
):
    """Deux modèles d'ordres de grandeur différents : podium, en-tête du tableau, axe et
    infobulle du graphique dans la même unité."""
    from src.core.eval_engine import EvalEngine, EvalResult
    from src.core.llm_provider import LLMProvider

    tags = [m["model"] for m in FAKE_LOCAL_MODELS]
    scores = iter([EvalResult(0.9, 0.9, 0.9), EvalResult(0.8, 0.8, 0.8)])
    monkeypatch.setattr(EvalEngine, "evaluate_single_turn", lambda self, **kw: next(scores))
    monkeypatch.setattr(
        LLMProvider, "chat_stream", staticmethod(_rag_stream(dict(zip(tags, tokens, strict=True))))
    )
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    assert [c for c in _captions(at) if c.startswith("CO₂ : ")] == [
        f"CO₂ : {text}" for text in podium
    ]

    (table,) = [t for t in at.dataframe if "Statut" in t.value.columns]
    assert json.loads(table.proto.columns)["CO₂"]["label"] == f"CO₂ ({unit})"

    spec = json.dumps(_vega_spec(at), ensure_ascii=False)
    assert f"CO₂ ({unit}), plus bas est mieux" in spec
    assert f'"title": "CO₂ ({unit})"' in spec


@pytest.fixture
def evaluation(monkeypatch, indexed_base):
    """Évaluation simulée : notes Ragas fixes (0,9 puis 0,8…), 20 tokens par réponse."""
    from src.core.eval_engine import EvalEngine, EvalResult
    from src.core.llm_provider import LLMProvider

    scores = iter([EvalResult(0.9, 0.9, 0.9), EvalResult(0.8, 0.8, 0.8)] * 3)
    monkeypatch.setattr(EvalEngine, "evaluate_single_turn", lambda self, **kw: next(scores))
    monkeypatch.setattr(LLMProvider, "chat_stream", staticmethod(_rag_stream()))


def _layers(spec):
    """Couches (point, étiquettes) de la matrice de l'évaluation."""
    points = next(layer for layer in spec["layer"] if layer["mark"]["type"] == "point")
    labels = [layer for layer in spec["layer"] if layer["mark"]["type"] == "text"]
    return points, labels


def test_documents_evaluation_single_model_matrix(evaluation, run_page):
    """Un seul modèle noté : axe CO₂ depuis 0 avec quelques graduations, point étiqueté du
    nom du modèle, échelle /100 comme le podium, pas de boîte de légende pour une série."""
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS[:1])

    spec = _vega_spec(at)
    points, labels = _layers(spec)
    x = points["encoding"]["x"]
    assert x["scale"]["domain"][0] == 0
    # 3,8 mg : domaine [0 ; 4,75] arrondi, cinq graduations au plus (pas de pas au dixième).
    assert x["scale"]["domain"][1] == pytest.approx(3.8 * 1.25)
    assert x["axis"]["tickCount"] == 5
    y = points["encoding"]["y"]
    assert y["scale"]["domain"] == [0, 100]
    assert y["axis"]["values"] == [0, 20, 40, 60, 80, 100]
    assert points["encoding"]["color"]["legend"] is None

    # Étiquette directe du point, en couleur de texte du thème (jamais la couleur de série).
    assert {label["encoding"]["text"]["field"] for label in labels} == {"Modèle"}
    assert all("expr" in label["mark"]["color"] for label in labels)
    (chart,) = at.get("vega_lite_chart")
    (dataset,) = chart.proto.datasets
    data = convert_arrow_bytes_to_pandas_df(dataset.data.data)
    assert list(data["Modèle"]) == [_friendly(FAKE_LOCAL_MODELS[0])]
    assert list(data["Côté"]) == ["left"]

    # Côté de l'étiquette : à gauche du point (alignée à droite, dx < 0) dans la moitié
    # droite de l'axe, et l'inverse.
    by_side = {label["transform"][0]["filter"]: label["mark"] for label in labels}
    left = next(mark for f, mark in by_side.items() if "'left'" in str(f) or '"left"' in str(f))
    right = next(mark for f, mark in by_side.items() if "'right'" in str(f) or '"right"' in str(f))
    assert left["align"] == "right" and left["dx"] < 0
    assert right["align"] == "left" and right["dx"] > 0


def test_documents_evaluation_colors_follow_the_model(evaluation, run_page):
    """Deux modèles : légende des séries, puis le second seul garde sa couleur (sa place dans
    le domaine de couleur) ; noms complets dans la légende."""
    names = [_friendly(m) for m in FAKE_LOCAL_MODELS]
    at = run_page(RAG_PAGE)
    _run_evaluation(at, FAKE_LOCAL_MODELS)

    points, _ = _layers(_vega_spec(at))
    color = points["encoding"]["color"]
    assert color["scale"]["domain"][:2] == names
    assert color["legend"]["values"] == names
    assert color["legend"]["labelLimit"] == 0

    _run_evaluation(at, FAKE_LOCAL_MODELS[1:])
    points, _ = _layers(_vega_spec(at))
    domain = points["encoding"]["color"]["scale"]["domain"]
    # Même place (index 1) : même couleur de la palette du thème ; la place 0 reste vide.
    assert domain.index(names[1]) == 1
    assert names[0] not in domain


def _eval_matrix(names, scores, co2_mg):
    """Matrice de l'évaluation construite directement (données simulées, sans page)."""
    import pandas as pd

    from src.app.tabs.rag.eval import _quality_matrix

    df = pd.DataFrame(
        {"Modèle": names, "Score": scores, "CO2_mg": co2_mg, "Latence_s": [1.0] * len(names)}
    )
    spec = _quality_matrix(df, {name: i for i, name in enumerate(names)}, "mg").to_dict()
    return spec, df


def test_documents_evaluation_more_models_than_colors():
    """6 modèles pour 4 couleurs : la forme distingue ceux qui partagent une couleur, dans la
    légende comme sur le graphique."""
    names = [f"Modèle {i}" for i in range(6)]
    spec, _ = _eval_matrix(names, [0.9, 0.8, 0.7, 0.6, 0.5, 0.4], [1, 2, 3, 4, 5, 6])
    points, _ = _layers(spec)
    shape = points["encoding"]["shape"]
    assert shape["scale"]["domain"] == names
    assert shape["scale"]["range"] == ["circle"] * 4 + ["square"] * 2
    assert shape["legend"] == points["encoding"]["color"]["legend"]
    # Chaque paire (couleur, forme) est unique.
    color_domain = points["encoding"]["color"]["scale"]["domain"]
    pairs = {
        (color_domain.index(n) % 4, s) for n, s in zip(names, shape["scale"]["range"], strict=True)
    }
    assert len(pairs) == 6


def test_documents_evaluation_labels_do_not_overlap():
    """Deux modèles au même CO₂ et aux notes proches (90 et 88) : étiquettes empilées à 8
    points d'écart au moins, reliées à leur point par un trait."""
    spec, _ = _eval_matrix(["Granite 4.0 3B Instruct", "Gemma 3 1B"], [0.9, 0.88], [3.8, 3.8])
    (rows,) = spec["datasets"].values()
    label_ys = sorted(row["label_y"] for row in rows)
    assert label_ys[1] - label_ys[0] >= 8 - 1e-9
    assert all(0 <= y <= 100 for y in label_ys)
    _, labels = _layers(spec)
    assert {label["encoding"]["y"]["field"] for label in labels} == {"label_y"}
    rules = [layer for layer in spec["layer"] if layer["mark"]["type"] == "rule"]
    assert rules and rules[0]["encoding"]["y2"]["field"] == "label_y"
