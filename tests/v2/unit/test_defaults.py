"""Défauts par usage : règles de choix, raison, cloud, préférences (AD-9, AD-15)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wavelocalai.errors import AppError
from wavelocalai.models.defaults import ModelDefaults, choose_default
from wavelocalai.models.registry import ModelInfo, ModelList
from wavelocalai.store.preferences import InMemoryPreferenceStore

SRC = Path(__file__).resolve().parents[3] / "src" / "wavelocalai"


def info(
    tag: str,
    *,
    needed: float | None = 2.0,
    fits: bool | None = True,
    params: float | None = 3.0,
    tps: float | None = None,
    accuracy: float | None = None,
    kind: str = "chat",
    origin: str = "local",
    tools: bool = False,
    name: str | None = None,
) -> ModelInfo:
    return ModelInfo(
        tag=tag,
        name=name or (tag if origin == "local" else tag.split("/", 1)[1]),
        provider="ollama" if origin == "local" else tag.split("/")[0],
        origin=origin,
        kind=kind,
        available=True,
        size_gb=needed,
        needed_gb=needed,
        fits=fits,
        params_total_b=params,
        params_active_b=params,
        throughput_tps=tps,
        accuracy=accuracy,
        tools_verified=tools,
        co2_method="codecarbon" if origin == "local" else "unmeasurable",
    )


SMALL = info("small:1b", needed=1.0, params=1.0)
MID = info("mid:4b", needed=3.0, params=4.0, tools=True)
BIG = info("big:9b", needed=7.0, params=9.0, tools=True)
HUGE = info("huge:70b", needed=50.0, params=70.0, fits=False)
EMBED = info("nomic-embed-text:latest", kind="embedding", needed=0.3, params=0.1)
RERANK = info("bge-reranker", kind="reranker", needed=0.3, params=0.1)
THINK = info("lfm2.5-thinking:1.2b", needed=0.5, params=1.2)
CLOUD = [
    info("openai/gpt-4o-mini", origin="cloud", needed=None, fits=None, params=None),
    info("anthropic/claude-opus-5-5", origin="cloud", needed=None, fits=None, params=None),
]
PURPOSES = ("chat", "arena", "judge", "agent", "rag")


def pick(models, purpose, allow_cloud=False):
    return choose_default(models, purpose, allow_cloud)


def test_chat_picks_the_lightest_fitting_local_without_measured_speed():
    result = pick([BIG, SMALL, MID, HUGE], "chat")
    assert result.tags == ["small:1b"]
    assert result.source == "rule"
    assert "tiennent en mémoire" in result.reason and "non mesuré" in result.reason


def test_chat_picks_the_fastest_when_speed_is_measured_for_all_fitting():
    models = [info("a:3b", tps=20.0), info("b:3b", tps=55.0), info("c:3b", tps=30.0)]
    result = pick(models, "chat")
    assert result.tags == ["b:3b"]
    assert result.reason.startswith("Le plus rapide des modèles locaux qui tiennent en mémoire")


def test_speed_and_footprint_are_never_mixed():
    # `heavy` est mesuré, `light` ne l'est pas : l'empreinte départage, pas le débit.
    result = pick([info("heavy:3b", needed=5.0, tps=90.0), info("light:3b", needed=1.0)], "chat")
    assert result.tags == ["light:3b"]


def test_dedicated_reasoning_model_comes_after_the_others():
    assert pick([THINK, MID], "chat").tags == ["mid:4b"]
    only = pick([THINK], "chat")
    assert only.tags == ["lfm2.5-thinking:1.2b"] and "raisonnement" in only.reason


@pytest.mark.parametrize("purpose", PURPOSES)
def test_defaults_are_never_embedding_or_reranker_models(purpose):
    result = pick([EMBED, RERANK, SMALL, MID], purpose)
    assert not {"nomic-embed-text:latest", "bge-reranker"} & set(result.tags)


def test_chat_with_nothing_fitting_proposes_the_smallest_with_a_warning():
    models = [info("big:9b", fits=False, needed=20.0), info("mid:4b", fits=False, needed=9.0)]
    result = pick(models, "chat")
    assert result.tags == ["mid:4b"]
    assert "ne tient en mémoire" in result.reason


def test_unknown_footprint_does_not_fit():
    result = pick([info("mystery:3b", needed=None, fits=None), MID], "chat")
    assert result.tags == ["mid:4b"]


def test_arena_gives_two_or_three_fitting_models_without_the_judge():
    models = [SMALL, MID, BIG, THINK, HUGE]
    assert pick(models, "judge").tags == ["big:9b"]
    # Hors juge (big), hors raisonnement (think), hors HUGE qui ne tient pas.
    assert pick(models, "arena").tags == ["small:1b", "mid:4b"]
    many = pick([SMALL, MID, BIG, info("x:2b"), info("y:2b")], "arena")
    assert len(many.tags) == 3 and "big:9b" not in many.tags


def test_arena_takes_the_judge_back_when_it_is_needed_to_reach_two():
    result = pick([SMALL, BIG], "arena")
    assert sorted(result.tags) == ["big:9b", "small:1b"]
    assert "juge est repris" in result.reason


def test_arena_with_one_fitting_model_says_it_is_incomplete():
    result = pick([SMALL, HUGE], "arena")
    assert result.tags == ["small:1b"] and "au moins 2" in result.reason
    none = pick([HUGE], "arena")
    assert none.tags == [] and "ne peut pas partir" in none.reason


def test_judge_is_the_biggest_local_that_fits():
    result = pick([SMALL, MID, BIG, HUGE], "judge")
    assert result.tags == ["big:9b"]
    assert result.reason.startswith("Le plus gros modèle local qui tient en mémoire")


def test_judge_prefers_a_reliable_note_over_a_bigger_footprint_with_few_active_params():
    moe = info("moe:30b", needed=12.0, params=1.5)  # gros fichier, peu de paramètres actifs
    assert pick([moe, MID], "judge").tags == ["mid:4b"]


def test_weak_judge_is_flagged():
    result = pick([SMALL], "judge")
    assert result.tags == ["small:1b"] and "prudence" in result.reason


def test_judge_uses_measured_accuracy_when_available():
    precise = info("precise:4b", needed=3.0, params=4.0, tps=30.0, accuracy=0.8)
    big = info("big:9b", needed=7.0, params=9.0, tps=30.0, accuracy=0.6)
    assert pick([big, precise], "judge").tags == ["precise:4b"]


@pytest.mark.parametrize("purpose", PURPOSES)
def test_cloud_is_never_a_default_without_allow_cloud(purpose):
    assert all("/" not in t for t in pick([*CLOUD, SMALL], purpose).tags)


def test_a_cloud_only_list_gives_no_model_without_allow_cloud():
    with pytest.raises(AppError) as err:
        pick(CLOUD, "chat")
    assert err.value.code == "no_model"


def test_cloud_judge_only_when_allowed_and_most_capable_first():
    models = [*CLOUD, BIG]
    assert pick(models, "judge", allow_cloud=False).tags == ["big:9b"]
    assert pick(models, "judge", allow_cloud=True).tags == ["anthropic/claude-opus-5-5"]
    # Les autres usages restent locaux, même cloud autorisé.
    assert pick(models, "chat", allow_cloud=True).tags == ["big:9b"]
    assert all("/" not in t for t in pick(models, "arena", allow_cloud=True).tags)


def test_cloud_is_the_chat_fallback_only_when_allowed_and_no_local_chat_model():
    assert pick([*CLOUD, EMBED], "chat", allow_cloud=True).tags[0].count("/") == 1
    with pytest.raises(AppError) as err:
        pick([*CLOUD, EMBED], "chat")
    assert err.value.code == "no_model"


def test_agent_needs_verified_tools_and_enough_active_params():
    result = pick([SMALL, MID, BIG, THINK], "agent")
    assert result.tags and result.tags[0] in {"mid:4b", "big:9b"}
    assert "outils vérifiés" in result.reason
    # Sans outils vérifiés : retombe sur le défaut de chat, et le dit.
    fallback = pick([SMALL, info("plain:4b", params=4.0)], "agent")
    assert fallback.tags == ["small:1b"] and "ne sont pas vérifiés" in fallback.reason


def test_rag_prefers_a_model_with_enough_active_params():
    result = pick([SMALL, MID], "rag")
    assert result.tags == ["mid:4b"] and "extraits" in result.reason
    fallback = pick([SMALL], "rag")
    assert fallback.tags == ["small:1b"] and "milliards" in fallback.reason


@pytest.mark.parametrize("purpose", PURPOSES)
def test_no_chat_model_raises_no_model_with_message_and_action(purpose):
    with pytest.raises(AppError) as err:
        pick([EMBED, RERANK], purpose)
    assert err.value.code == "no_model" and err.value.detail == {"purpose": purpose}


# -- préférences ------------------------------------------------------------------------------


class FakeRegistry:
    def __init__(self, models):
        self.models = models

    async def list_models(self, *, allow_cloud: bool = False) -> ModelList:
        shown = [m for m in self.models if allow_cloud or m.origin == "local"]
        return ModelList(models=shown, ollama_up=True, refreshed_at=1.0)


async def test_a_stored_preference_overrides_the_rule_for_that_purpose_only():
    prefs = InMemoryPreferenceStore()
    prefs.put("default_model.chat", {"tags": ["big:9b"]})
    service = ModelDefaults(FakeRegistry([SMALL, MID, BIG]), prefs)

    chat = await service.get("chat")
    assert chat.tags == ["big:9b"] and chat.source == "preference"
    assert (await service.get("judge")).source == "rule"  # un autre usage garde la règle
    assert (await service.get("arena")).source == "rule"


async def test_a_preference_for_a_removed_or_forbidden_model_is_ignored():
    prefs = InMemoryPreferenceStore()
    prefs.put("default_model.chat", {"tags": ["gone:7b"]})
    prefs.put("default_model.judge", {"tags": ["openai/gpt-4o-mini"]})
    prefs.put("default_model.rag", {"tags": ["nomic-embed-text:latest"]})
    service = ModelDefaults(FakeRegistry([SMALL, EMBED, *CLOUD]), prefs)

    assert (await service.get("chat")).source == "rule"
    assert (await service.get("judge")).tags == ["small:1b"]  # cloud non autorisé
    assert (await service.get("rag")).source == "rule"  # un embedding n'est jamais un défaut
    allowed = await service.get("judge", allow_cloud=True)
    assert allowed.tags == ["openai/gpt-4o-mini"] and allowed.source == "preference"


async def test_the_service_never_writes_preferences():
    prefs = InMemoryPreferenceStore()
    await ModelDefaults(FakeRegistry([SMALL, MID]), prefs).get("chat")
    assert prefs.get("default_model.chat") is None


def test_preferences_migration_creates_a_key_value_table():
    sql = (SRC / "store" / "migrations" / "0003_preferences.sql").read_text(encoding="utf-8")
    db = sqlite3.connect(":memory:")
    db.executescript(sql)
    columns = {row[1]: row for row in db.execute("PRAGMA table_info(preferences)")}
    assert list(columns) == ["key", "value", "updated_at"]
    assert columns["key"][5] == 1  # clé primaire
    db.execute("INSERT INTO preferences VALUES ('default_model.chat', '{}', 1.0)")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO preferences VALUES ('default_model.chat', '{}', 2.0)")


def test_defaults_module_never_imports_the_v1():
    source = (SRC / "models" / "defaults.py").read_text(encoding="utf-8")
    assert "import src" not in source and "from src" not in source
