"""Registre des modèles : liste, cache `model_facts`, Ollama arrêté, cloud, `resolve` (AD-9)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from wavelocalai.errors import AppError
from wavelocalai.hardware.memory import MemoryAdvisor, MemoryReading
from wavelocalai.models.facts import InMemoryFactsStore
from wavelocalai.models.ollama_api import OllamaUnavailableError
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.models.run_stats import InMemoryRunStats

from ..conftest import make_settings

GB = 1024**3


def _listed(tag: str, digest: str, size_gb: float, family: str = "llama", params: str = "3B"):
    return {
        "model": tag,
        "digest": digest,
        "size": int(size_gb * GB),
        "details": {"family": family, "parameter_size": params, "quantization_level": "Q4_K_M"},
    }


class FakeOllama:
    def __init__(
        self, listed: list[dict[str, Any]], shows: dict[str, dict[str, Any]] | None = None
    ):
        self.listed = listed
        self.shows = shows or {}
        self.down = False
        self.show_calls: list[str] = []
        self.tag_calls = 0

    async def list_tags(self):
        self.tag_calls += 1
        if self.down:
            raise OllamaUnavailableError("arrêté")
        return self.listed

    async def show(self, tag: str):
        self.show_calls.append(tag)
        if self.down:
            raise OllamaUnavailableError("arrêté")
        return self.shows.get(tag, {"capabilities": ["completion"], "model_info": {}})


def _fixture_source() -> FakeOllama:
    return FakeOllama(
        [
            _listed("qwen3.5:2b", "d-qwen", 2.5, "qwen35", "2.3B"),
            _listed("nomic-embed-text:latest", "d-nomic", 0.25, "nomic-bert", "137M"),
            _listed("bge-reranker-base", "d-rerank", 0.5, "bert", "278M"),
            _listed("moe:30b", "d-moe", 18.0, "qwenmoe", "30B"),
            _listed("glm-4.6:cloud", "d-remote", 0.0001, "glm", "355B"),
            _listed("oddball:1b", "", 0.7),
        ],
        {
            "qwen3.5:2b": {
                "capabilities": ["completion", "tools", "thinking"],
                "model_info": {"general.architecture": "qwen35", "general.parameter_count": 2.27e9},
            },
            "nomic-embed-text:latest": {"capabilities": ["embedding"], "model_info": {}},
            "moe:30b": {
                "capabilities": ["completion"],
                "model_info": {
                    "general.architecture": "qwenmoe",
                    "general.parameter_count": 30e9,
                    "qwenmoe.expert_count": 128,
                    "qwenmoe.expert_used_count": 8,
                },
            },
        },
    )


def _registry(tmp_path, source, **kwargs) -> ModelRegistry:
    settings = kwargs.pop("settings", None) or make_settings(tmp_path)
    return ModelRegistry(settings, source=source, **kwargs)


async def test_lists_local_models_with_their_kind_origin_and_facts(tmp_path):
    advisor = MemoryAdvisor(lambda: MemoryReading(32.0, 8.0))
    registry = _registry(tmp_path, _fixture_source(), advisor=advisor)
    await registry.refresh()
    result = await registry.list_models()
    by_tag = {m.tag: m for m in result.models}

    assert result.ollama_up is True and result.refreshed_at is not None
    chat = by_tag["qwen3.5:2b"]
    assert (chat.origin, chat.kind, chat.provider) == ("local", "chat", "ollama")
    assert chat.params_total_b == pytest.approx(2.27, abs=0.01)
    assert chat.params_active_b == chat.params_total_b  # dense : actifs = totaux
    assert chat.size_gb == pytest.approx(2.5, abs=0.01)
    assert chat.needed_gb == pytest.approx(2.5 * 1.25, abs=0.01) and chat.fits is True
    assert chat.required_gb == 4.0  # 3,125 × 1,1 + 0,5 = 3,94 : le « requis » d'un refus ram_guard
    assert chat.reasoning is True and chat.tools_verified is True
    assert chat.co2_method == "codecarbon" and chat.accuracy is None
    assert chat.throughput_tps is None  # aucun run
    assert by_tag["nomic-embed-text:latest"].kind == "embedding"
    assert by_tag["bge-reranker-base"].kind == "reranker"
    moe = by_tag["moe:30b"]
    assert moe.params_total_b == pytest.approx(30.0) and moe.params_active_b is None
    assert moe.fits is False  # 18 Go × 1,25 × 1,1 > 7,5 Go utilisables


async def test_unknown_digest_is_unknown_origin_and_remote_tag_is_cloud(tmp_path):
    registry = _registry(tmp_path, _fixture_source())
    await registry.refresh()
    hidden = {m.tag for m in (await registry.list_models()).models}
    assert "oddball:1b" not in hidden and "glm-4.6:cloud" not in hidden  # ni local, ni autorisé
    shown = {m.tag: m for m in (await registry.list_models(allow_cloud=True)).models}
    assert shown["oddball:1b"].origin == "unknown" and shown["oddball:1b"].fits is None
    assert shown["glm-4.6:cloud"].origin == "cloud"
    assert shown["glm-4.6:cloud"].co2_method == "unmeasurable"


async def test_show_is_cached_by_tag_and_digest(tmp_path):
    source = _fixture_source()
    facts = InMemoryFactsStore()
    registry = _registry(tmp_path, source, facts=facts)
    await registry.refresh()
    first = len(source.show_calls)
    assert first == 6
    await registry.refresh()
    assert len(source.show_calls) == first + 1  # seul le modèle sans digest est relu
    source.listed[0] = _listed("qwen3.5:2b", "d-qwen-v2", 2.5, "qwen35", "2.3B")
    await registry.refresh()
    assert source.show_calls.count("qwen3.5:2b") == 2  # nouveau digest = nouvelle lecture
    assert facts.get("qwen3.5:2b", "d-qwen") is not None


async def test_ollama_down_serves_last_known_list_from_cache(tmp_path):
    source = _fixture_source()
    registry = _registry(tmp_path, source)
    await registry.refresh()
    source.down = True
    await registry.refresh()
    result = await registry.list_models()
    assert result.ollama_up is False
    assert "qwen3.5:2b" in {m.tag for m in result.models}
    assert all(m.available is False for m in result.models)


async def test_cold_start_with_ollama_down_uses_model_facts(tmp_path):
    source = _fixture_source()
    facts = InMemoryFactsStore()
    await _registry(tmp_path, source, facts=facts).refresh()  # un précédent démarrage
    down = FakeOllama([])
    down.down = True
    restarted = _registry(tmp_path, down, facts=facts)
    result = await restarted.list_models()
    assert result.ollama_up is False and result.refreshed_at is None
    assert {"qwen3.5:2b", "nomic-embed-text:latest"} <= {m.tag for m in result.models}


async def test_list_never_waits_for_a_slow_ollama(tmp_path):
    class Slow(FakeOllama):
        async def list_tags(self):
            await asyncio.sleep(5)
            return []

    registry = _registry(tmp_path, Slow([]), wait_s=0.05)
    started = time.perf_counter()
    result = await registry.list_models()
    assert time.perf_counter() - started < 0.5
    assert result.models == []
    await registry.stop()


async def test_refresh_runs_in_background_when_cache_is_stale(tmp_path):
    source = _fixture_source()
    now = [0.0]
    registry = _registry(tmp_path, source, cache_s=5.0, clock=lambda: now[0], wait_s=1.0)
    await registry.list_models()
    assert source.tag_calls == 1
    await registry.list_models()
    assert source.tag_calls == 1  # dans les 5 s : cache
    now[0] = 6.0
    await registry.list_models()  # sert l'ancienne liste, relance en fond
    await registry._task
    assert source.tag_calls == 2


async def test_throughput_is_the_median_of_measured_leaves(tmp_path):
    stats = InMemoryRunStats()
    for tps in (10.0, 20.0, 30.0):
        stats.record_leaf("qwen3.5:2b", tps)
    registry = _registry(tmp_path, _fixture_source(), run_stats=stats)
    await registry.refresh()
    by_tag = {m.tag: m for m in (await registry.list_models()).models}
    assert by_tag["qwen3.5:2b"].throughput_tps == 20.0
    assert by_tag["moe:30b"].throughput_tps is None


async def test_catalog_supplies_names_active_params_and_measured_memory(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "models_catalog.json").write_text(
        '{"models": {"Qwen Deux": {"ollama_tag": "qwen3.5:2b", "editor": "Alibaba", '
        '"params_tot": "2.3B", "params_act": "1B", "capabilities": ["chat"], '
        '"measured_loaded_gb": 2.4, "size_gb": "2.7 GB"}}}',
        encoding="utf-8",
    )
    registry = _registry(
        tmp_path, _fixture_source(), advisor=MemoryAdvisor(lambda: MemoryReading(32, 16))
    )
    await registry.refresh()
    info = {m.tag: m for m in (await registry.list_models()).models}["qwen3.5:2b"]
    assert (info.name, info.editor, info.in_catalog) == ("Qwen Deux", "Alibaba", True)
    assert info.params_active_b == 1.0 and info.needed_gb == 2.4
    assert info.tools_verified is False  # le catalogue prime : pas de capacité `tools`


def _cloud_registry(tmp_path):
    settings = make_settings(
        tmp_path,
        environ={"OPENAI_API_KEY": "sk-test-0123456789", "GROQ_API_KEY": "gsk_test_0123456789"},
        cloud={
            "models": {
                "openai": ["gpt-4o"],
                "groq": ["openai/gpt-oss-120b", "llama-3.1-8b-instant"],
                "anthropic": ["claude-haiku-5-5"],  # clé absente : jamais listé
            },
            "groq_ecologits": {"openai/gpt-oss-120b": "openai/gpt-oss-120b"},
        },
    )
    return _registry(tmp_path, _fixture_source(), settings=settings)


async def test_cloud_models_need_a_key_and_allow_cloud(tmp_path):
    registry = _cloud_registry(tmp_path)
    await registry.refresh()
    without = await registry.list_models()
    assert {m.origin for m in without.models} == {"local"}

    with_cloud = await registry.list_models(allow_cloud=True)
    cloud = {m.tag: m for m in with_cloud.models if m.provider != "ollama"}
    assert set(cloud) == {"openai/gpt-4o", "groq/openai/gpt-oss-120b", "groq/llama-3.1-8b-instant"}
    assert all(m.origin == "cloud" and m.kind == "chat" and m.fits is None for m in cloud.values())
    assert cloud["openai/gpt-4o"].co2_method == "ecologits"
    assert cloud["groq/openai/gpt-oss-120b"].co2_method == "ecologits"  # dans la table
    assert cloud["groq/llama-3.1-8b-instant"].co2_method == "unmeasurable"  # hors table


async def test_resolve_refuses_cloud_without_allow_cloud(tmp_path):
    registry = _cloud_registry(tmp_path)
    await registry.refresh()
    with pytest.raises(AppError) as absent:
        registry.resolve("openai/gpt-4o")
    assert absent.value.code == "cloud_not_allowed"
    with pytest.raises(AppError) as false:
        registry.resolve("openai/gpt-4o", False)
    assert false.value.code == "cloud_not_allowed"
    ref = registry.resolve("openai/gpt-4o", allow_cloud=True)
    assert (ref.origin, ref.provider, ref.kind) == ("cloud", "openai", "chat")
    with pytest.raises(AppError) as unknown:
        registry.resolve("oddball:1b")  # origine inconnue = non locale
    assert unknown.value.code == "cloud_not_allowed"
    with pytest.raises(AppError) as remote:
        registry.resolve("glm-4.6:cloud")
    assert remote.value.code == "cloud_not_allowed"


async def test_resolve_local_chat_and_rejects_other_kinds(tmp_path):
    registry = _registry(tmp_path, _fixture_source())
    await registry.refresh()
    assert registry.resolve("qwen3.5:2b").origin == "local"
    for tag, kind in (("nomic-embed-text", "embedding"), ("bge-reranker-base", "reranker")):
        with pytest.raises(AppError) as exc:
            registry.resolve(tag)
        assert exc.value.code == "model_not_chat" and exc.value.detail["kind"] == kind
    with pytest.raises(AppError) as missing:
        registry.resolve("nope:1b")
    assert missing.value.code == "model_not_found"
    with pytest.raises(AppError) as undeclared:
        registry.resolve("anthropic/claude-haiku-5-5", allow_cloud=True)
    assert undeclared.value.code == "model_not_found"  # hors de `[cloud.models]`


async def test_a_declared_cloud_model_without_key_resolves_but_is_never_listed(tmp_path):
    registry = _cloud_registry(tmp_path)  # anthropic déclaré, clé absente
    await registry.refresh()
    with pytest.raises(AppError) as refused:
        registry.resolve("anthropic/claude-haiku-5-5")
    assert refused.value.code == "cloud_not_allowed"  # D1 d'abord, même sans clé
    ref = registry.resolve("anthropic/claude-haiku-5-5", allow_cloud=True)
    assert (ref.provider, ref.origin) == ("anthropic", "cloud")  # l'appel dira `cloud_key_missing`
    shown = {m.tag for m in (await registry.list_models(allow_cloud=True)).models}
    assert "anthropic/claude-haiku-5-5" not in shown
    with pytest.raises(AppError) as unknown:
        registry.resolve("anthropic/claude-inconnu", allow_cloud=True)
    assert unknown.value.code == "model_not_found"


async def test_resolve_embedder_is_local_embedding_only(tmp_path):
    registry = _cloud_registry(tmp_path)
    await registry.refresh()
    assert registry.resolve_embedder("nomic-embed-text:latest").kind == "embedding"
    assert registry.resolve_embedder("nomic-embed-text").tag == "nomic-embed-text:latest"
    with pytest.raises(AppError) as chat:
        registry.resolve_embedder("qwen3.5:2b")
    assert chat.value.code == "model_not_embedding"
    with pytest.raises(AppError) as cloud:
        registry.resolve_embedder("openai/gpt-4o")
    assert cloud.value.code == "cloud_not_allowed"


async def test_moe_without_show_never_gets_the_total_as_active_params(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "models_catalog.json").write_text(
        '{"models": {"Gros MoE": {"ollama_tag": "moe:30b", "params_tot": "30B", "moe": true}}}',
        encoding="utf-8",
    )
    source = _fixture_source()

    async def no_show(tag: str):
        raise OllamaUnavailableError("show indisponible")

    source.show = no_show
    registry = _registry(tmp_path, source)
    await registry.refresh()
    by_tag = {m.tag: m for m in (await registry.list_models()).models}
    assert by_tag["moe:30b"].params_total_b == 30.0
    assert by_tag["moe:30b"].params_active_b is None  # catalogue MoE sans params_act
    # Sans catalogue ni show, la famille (`...moe`) suffit à ne pas inventer la valeur.
    source.listed.append(_listed("lfm:24b", "d-lfm", 14.0, "lfm2moe", "24B"))
    await registry.refresh()
    by_tag = {m.tag: m for m in (await registry.list_models()).models}
    assert by_tag["lfm:24b"].params_active_b is None
    assert by_tag["qwen3.5:2b"].params_active_b == by_tag["qwen3.5:2b"].params_total_b
