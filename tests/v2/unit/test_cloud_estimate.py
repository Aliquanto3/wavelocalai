"""Estimation ecologits du CO2 cloud (story 2.5, AD-10, AD-11) : aucun réseau, tables du paquet.

Le test de contrat fige la signature de `llm_impacts` et confirme chaque entrée de
`wavelocalai.toml` contre la version d'ecologits installée.
"""

from __future__ import annotations

import ast
import inspect
import socket
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

from wavelocalai.config import DEFAULT_TOML
from wavelocalai.greenops import cloud_estimate
from wavelocalai.greenops.cloud_estimate import estimate_cloud_co2

SRC = Path(__file__).resolve().parents[3] / "src" / "wavelocalai"
GROQ_TABLE = {
    "openai/gpt-oss-120b": "openai/gpt-oss-120b",
    "openai/gpt-oss-20b": "openai/gpt-oss-20b",
}
TOKENS, LATENCY = 200, 3.0


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Toute connexion sortante échoue : le calcul d'ecologits ne lit que ses tables."""

    def refuse(*args, **kwargs):
        raise AssertionError("appel réseau interdit pendant l'estimation")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _estimate(provider, model, **kwargs):
    kwargs.setdefault("output_tokens", TOKENS)
    kwargs.setdefault("latency_s", LATENCY)
    kwargs.setdefault("groq_table", GROQ_TABLE)
    return estimate_cloud_co2(provider, model, **kwargs)


# --- contrat d'ecologits ---------------------------------------------------------------------------


def test_llm_impacts_signature_is_frozen():
    from ecologits.tracers.utils import llm_impacts

    params = inspect.signature(llm_impacts).parameters
    assert list(params) == [
        "provider",
        "model_name",
        "output_token_count",
        "request_latency",
        "electricity_mix_zone",
    ]
    assert params["electricity_mix_zone"].default is None
    assert all(params[name].default is inspect.Parameter.empty for name in list(params)[:4])


def test_installed_ecologits_is_in_the_pinned_range():
    version = tuple(int(part) for part in metadata.version("ecologits").split(".")[:3])
    assert (0, 11, 3) <= version < (0, 12, 0)
    pins = [
        line
        for line in (SRC.parents[1] / "pyproject.toml").read_text(encoding="utf-8").splitlines()
        if "ecologits" in line
    ]
    assert any(">=0.11.3,<0.12" in line for line in pins)


def test_impacts_output_shape_the_estimator_relies_on():
    from ecologits.tracers.utils import llm_impacts

    out = llm_impacts(
        provider="openai",
        model_name="gpt-4o",
        output_token_count=TOKENS,
        request_latency=LATENCY,
        electricity_mix_zone=None,
    )
    assert not out.errors and out.gwp is not None and out.gwp.unit == "kgCO2eq"
    assert out.gwp.value.min <= out.gwp.value.max


def test_ecologits_init_is_never_called_and_the_source_does_not_name_it(monkeypatch):
    from ecologits import EcoLogits

    def boom(*args, **kwargs):
        raise AssertionError("EcoLogits.init() est interdit (AD-11)")

    monkeypatch.setattr(EcoLogits, "init", boom)
    assert _estimate("openai", "gpt-4o").method == "ecologits"
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "init":
                assert getattr(node.value, "id", "") != "EcoLogits", path


# --- estimation nominale ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("openai", "gpt-4o"),
        ("anthropic", "claude-sonnet-4-6"),
        ("mistral", "mistral-large-latest"),
        ("groq", "openai/gpt-oss-120b"),
    ],
)
def test_nominal_estimate_for_each_provider(provider, model):
    co2 = _estimate(provider, model)
    assert co2.method == "ecologits" and co2.estimated is True and co2.allocation == "direct"
    assert co2.reason is None and co2.mg is not None and co2.mg > 0
    low, high = co2.range_mg["low"], co2.range_mg["high"]
    assert 0 < low <= co2.mg <= high
    assert co2.as_dict()["range_mg"] == {"low": low, "high": high}


def test_units_are_milligrams_from_kilograms_of_co2_equivalent():
    from ecologits.tracers.utils import llm_impacts

    out = llm_impacts(
        provider="huggingface_hub",
        model_name="openai/gpt-oss-120b",
        output_token_count=TOKENS,
        request_latency=LATENCY,
        electricity_mix_zone=None,
    )
    co2 = _estimate("groq", "openai/gpt-oss-120b")
    assert co2.range_mg["low"] == pytest.approx(out.gwp.value.min * 1_000_000)
    assert co2.range_mg["high"] == pytest.approx(out.gwp.value.max * 1_000_000)
    assert 1 < co2.mg < 1000  # quelques dizaines de mg pour 200 jetons, pas des kg


def test_the_estimate_is_called_by_keyword_with_the_provider_datacenter_zone(monkeypatch):
    from ecologits.tracers import utils

    seen = {}
    real = utils.llm_impacts

    def spy(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return real(*args, **kwargs)

    monkeypatch.setattr(utils, "llm_impacts", spy)
    _estimate("mistral", "mistral-large-latest")
    assert seen["args"] == ()
    assert seen["kwargs"] == {
        "provider": "mistralai",
        "model_name": "mistral-large-latest",
        "output_token_count": TOKENS,
        "request_latency": LATENCY,
        "electricity_mix_zone": None,
    }


# --- non mesurable ---------------------------------------------------------------------------------


def test_groq_without_a_table_entry_is_unmeasurable_with_its_reason():
    co2 = _estimate("groq", "llama-3.3-70b-versatile")
    assert co2.method == "unmeasurable" and co2.mg is None and co2.range_mg is None
    assert "Groq" in co2.reason and "wavelocalai.toml" in co2.reason
    assert _estimate("groq", "openai/gpt-oss-120b", groq_table={}).method == "unmeasurable"


def test_a_model_unknown_to_ecologits_is_unmeasurable_from_the_error_code():
    co2 = _estimate("anthropic", "claude-inconnu-9")
    assert co2.method == "unmeasurable" and co2.mg is None
    assert "Anthropic ne publie pas la taille de ce modèle" in co2.reason


def test_non_empty_errors_make_the_result_unmeasurable(monkeypatch):
    from ecologits.status_messages import ZoneNotRegisteredError
    from ecologits.tracers import utils

    monkeypatch.setattr(
        utils, "llm_impacts", lambda **kw: utils.ImpactsOutput(errors=[ZoneNotRegisteredError()])
    )
    co2 = _estimate("openai", "gpt-4o")
    assert co2.method == "unmeasurable" and co2.mg is None and "mix électrique" in co2.reason

    class Odd:
        code = "nouveau-code"

    monkeypatch.setattr(
        utils, "llm_impacts", lambda **kw: utils.ImpactsOutput.model_construct(errors=[Odd()])
    )
    assert "nouveau-code" in _estimate("openai", "gpt-4o").reason


def test_an_exception_is_unmeasurable_and_never_raised(monkeypatch):
    from ecologits.tracers import utils

    def boom(**kwargs):
        raise RuntimeError("table illisible")

    monkeypatch.setattr(utils, "llm_impacts", boom)
    co2 = _estimate("openai", "gpt-4o")
    assert co2.method == "unmeasurable" and co2.mg is None and "RuntimeError" in co2.reason


@pytest.mark.parametrize(
    "kwargs",
    [
        {"output_tokens": None},
        {"output_tokens": 0},
        {"latency_s": None},
        {"latency_s": 0.0},
    ],
)
def test_missing_tokens_or_latency_is_unmeasurable_never_zero(kwargs):
    co2 = _estimate("openai", "gpt-4o", **kwargs)
    assert co2.method == "unmeasurable" and co2.mg is None and co2.reason


def test_an_unknown_provider_is_unmeasurable():
    assert _estimate("inconnu", "m").method == "unmeasurable"


@pytest.mark.parametrize("value", [0.0, -1e-9, float("nan"), None, "x"])
def test_a_null_or_invalid_gwp_is_never_a_zero_estimate(monkeypatch, value):
    from ecologits.tracers import utils

    class Gwp:
        pass

    gwp = Gwp()
    gwp.value = value
    monkeypatch.setattr(
        utils, "llm_impacts", lambda **kw: utils.ImpactsOutput.model_construct(gwp=gwp)
    )
    co2 = _estimate("openai", "gpt-4o")
    assert co2.method == "unmeasurable" and co2.mg is None


# --- confirmation des tables de wavelocalai.toml (A13) -----------------------------------------------


def _toml() -> dict:
    return tomllib.loads(DEFAULT_TOML.read_text(encoding="utf-8"))


def test_every_groq_table_entry_exists_in_the_installed_ecologits():
    from ecologits.model_repository import models

    table = _toml()["cloud"]["groq_ecologits"]
    assert table, "la table de correspondance Groq ne doit pas être vide"
    for groq_model, hub_model in table.items():
        assert models.find_model(provider="huggingface_hub", model_name=hub_model), groq_model
        assert _estimate("groq", groq_model, groq_table=table).method == "ecologits", groq_model


def test_every_declared_direct_cloud_model_is_known_to_ecologits():
    declared = _toml()["cloud"]["models"]
    table = _toml()["cloud"]["groq_ecologits"]
    for provider, names in declared.items():
        for name in names:
            co2 = _estimate(provider, name, groq_table=table)
            if provider == "groq" and name not in table:
                assert co2.method == "unmeasurable" and co2.reason, name
            else:
                assert co2.method == "ecologits", f"{provider}/{name} : {co2.reason}"


def test_ecologits_is_imported_inside_the_function_only():
    source = Path(cloud_estimate.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    top_level = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not any("ecologits" in ast.dump(node) for node in top_level)
