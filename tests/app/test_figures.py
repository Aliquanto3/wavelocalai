"""
Chiffres justes (story 6), avec AppTest : CO₂ de session et historique d'émissions de
« Sobriété et matériel », débit, chargement et durée totale de l'Arène des modèles.

Aucun Ollama ni réseau : tracker et inférence simulés, fichiers d'émissions sous tmp_path
(tests/app/conftest.py redirige LOGS_DIR et EMISSIONS_DIR).
Usage: python -m pytest tests/app/test_figures.py -v
"""

import base64
import json

import numpy as np
import pytest

from src.app.formatting import NBSP, NNBSP
from src.app.states import THROUGHPUT_HELP
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


def _chart_values(at):
    (chart,) = at.get("plotly_chart")
    figure = json.loads(chart.proto.spec)
    return [v for trace in figure["data"] for v in _decode(trace["y"])]


def test_history_without_file():
    """Aucun fichier d'émissions : message d'état vide, pas de graphique ni d'avertissement."""
    at = _hardware_page(FakeTracker(0.0))

    assert "Aucune session mesurée pour l'instant." in [i.value for i in at.info]
    assert not at.get("plotly_chart")
    assert not [w.value for w in at.warning if "historique" in w.value]


def test_history_reads_tracker_file_and_ignores_benchmark(offline_app_env):
    """L'historique lit le fichier du suivi (logs/emissions.csv), suivi de session seulement ;
    le fichier du benchmark (logs/emissions/emissions.csv) est ignoré."""
    logs_dir = offline_app_env / "logs"
    (logs_dir / "emissions.csv").write_text(
        CSV_HEADER
        + "2026-09-26T09:15:00,wavelocal_session,a,10,0.00042\n"
        + "2026-09-26T09:30:00,wavelocal_audit,b,10,0.00081\n"
        + "2026-09-26T09:35:00,crew_mission,c,10,0.0005\n"
        + "2026-09-26T09:40:00,codecarbon,d,10,0.9\n"
        + "2026-09-26T09:45:00,wavelocal_session,e,10,0.00063\n",
        encoding="utf-8",
    )
    bench_dir = logs_dir / "emissions"
    bench_dir.mkdir()
    (bench_dir / "emissions.csv").write_text(
        CSV_HEADER + "2026-09-26T10:00:00,benchmark_slm,f,10,0.777\n", encoding="utf-8"
    )

    at = _hardware_page(FakeTracker(0.0))

    assert _chart_values(at) == pytest.approx([0.00042, 0.00063])


def test_history_matches_real_tracker(offline_app_env):
    """CAP-4 : le CO₂ affiché (stop()) et la ligne lue par l'historique viennent du même
    tracker, dans le même fichier : écart < 5 %."""
    from src.core.green_monitor import SESSION_PROJECT, GreenTracker

    tracker = GreenTracker(SESSION_PROJECT)
    tracker.start()
    emissions_g = tracker.stop()

    at = _hardware_page(FakeTracker(0.0, running=False), last_emissions=emissions_g)

    (logged_kg,) = _chart_values(at)
    assert logged_kg * 1000 == pytest.approx(emissions_g, rel=0.05, abs=1e-12)


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

    footer = (
        f"7,6{NBSP}mgCO₂ · 25,0{NBSP}tokens/s · Chargement 0,1{NBSP}s · Durée totale 1,6{NBSP}s"
    )
    (caption,) = [c for c in at.caption if c.value == footer]
    assert caption.help == THROUGHPUT_HELP


def test_chat_footer_estimated_throughput(cloud_like_inference, run_page):
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    assert not at.exception, [e.value for e in at.exception]

    footer = f"7,6{NBSP}mgCO₂ · 25,0{NBSP}tokens/s (estimé) · Durée totale 1,6{NBSP}s"
    assert footer in _captions(at)


def test_chat_session_total(fake_inference, run_page):
    """« Session : … » : somme des réponses (2 × 7,6 mg), convertie par la règle CO₂."""
    at = run_page(ARENA_PAGE)
    at.chat_input[0].set_value("Bonjour").run()
    at.chat_input[0].set_value("Encore").run()
    assert not at.exception, [e.value for e in at.exception]

    assert f"Session : **15,2{NBSP}mgCO₂**" in _captions(at)


def _bubble_texts(at):
    (chart,) = at.get("plotly_chart")
    figure = json.loads(chart.proto.spec)
    return [t for trace in figure["data"] for t in trace["text"]]


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
