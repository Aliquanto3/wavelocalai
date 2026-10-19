"""Garde-fou mémoire (story 4.8) : besoin chiffré, modèle déjà chargé, modèle proposé, déchargement.

Mémoire du poste, besoins des modèles et `/api/ps` sont simulés ; aucun réseau, aucun Ollama.
"""

from __future__ import annotations

import json

import httpx
import pytest

from wavelocalai.errors import AppError, build_envelope
from wavelocalai.hardware.memory import (
    FIT_MARGIN,
    SYSTEM_RAM_BUFFER_GB,
    MemoryReading,
    ceil_tenth,
    floor_tenth,
    remaining_need_gb,
    required_gb,
    shortfall_gb,
)
from wavelocalai.inference.memory_guard import MemoryGuard
from wavelocalai.inference.unload import unload_idle_models
from wavelocalai.models.ollama_ps import LoadedModel, unload_model
from wavelocalai.models.port import ModelRef
from wavelocalai.models.registry import ModelNeed

HOST = "http://127.0.0.1:11434"


def local(tag: str, kind: str = "chat") -> ModelRef:
    return ModelRef(tag, "ollama", "local", kind)  # type: ignore[arg-type]


class Needs:
    def __init__(self, *needs: ModelNeed) -> None:
        self.needs = list(needs)

    def memory_needs(self) -> list[ModelNeed]:
        return list(self.needs)


def reader(available_gb: float):
    return lambda: MemoryReading(total_gb=16.0, available_gb=available_gb)


class Ps:
    """`/api/ps` simulé : compte ses lectures (le chemin courant n'en fait aucune)."""

    def __init__(self, *loaded: LoadedModel, down: bool = False) -> None:
        self.loaded = list(loaded)
        self.down = down
        self.reads = 0

    async def __call__(self):
        self.reads += 1
        return None if self.down else list(self.loaded)


def guard(needs: Needs, available_gb: float, ps: Ps | None = None) -> MemoryGuard:
    ps = ps or Ps()
    return MemoryGuard(needs, HOST, reader=reader(available_gb), loaded=ps)


BIG = ModelNeed("qwen3:8b", "chat", 4.2)  # besoin chiffré : 4,2 × 1,1 + 0,5 = 5,12 Go
MID = ModelNeed("qwen3.5:2b", "chat", 1.8)  # 2,48 Go
SMALL = ModelNeed("qwen2.5:0.5b", "chat", 0.6)  # 1,16 Go
EMBED = ModelNeed("nomic-embed-text", "embedding", 0.3)


# --- Règles de `hardware/memory.py` -------------------------------------------------------------


def test_required_memory_adds_the_margin_and_the_system_reserve():
    assert required_gb(4.2) == pytest.approx(4.2 * FIT_MARGIN + SYSTEM_RAM_BUFFER_GB)


def test_a_loaded_model_leaves_no_need_or_only_the_gap():
    assert remaining_need_gb(4.2, 4.2) == 0.0
    assert remaining_need_gb(4.2, 5.0) == 0.0
    assert remaining_need_gb(4.2, 3.0) == pytest.approx(1.2)
    assert remaining_need_gb(4.2, 0.0) == 4.2


def test_a_shortfall_is_the_required_memory_or_nothing():
    assert shortfall_gb(4.2, 0.0, 8.0) is None
    assert shortfall_gb(4.2, 0.0, 2.8) == pytest.approx(required_gb(4.2))
    assert shortfall_gb(4.2, 4.2, 0.1) is None  # déjà chargé : rien à demander
    assert shortfall_gb(4.2, 3.0, 2.0) is None  # l'écart (1,2 Go) demande 1,82 Go : il tient


def test_displayed_figures_never_hide_the_refusal():
    assert ceil_tenth(2.81) == 2.9 and ceil_tenth(2.8) == 2.8
    assert floor_tenth(2.89) == 2.8 and floor_tenth(2.8) == 2.8


# --- Le garde-fou -------------------------------------------------------------------------------


async def test_a_model_that_fits_passes_without_asking_ollama():
    ps = Ps()
    await guard(Needs(BIG), 9.0, ps).check(local(BIG.tag))
    assert ps.reads == 0


async def test_a_model_that_does_not_fit_raises_ram_guard_with_the_real_need():
    ps = Ps()
    needs = Needs(BIG, MID, SMALL, EMBED)
    with pytest.raises(AppError) as raised:
        await guard(needs, 2.8, ps).check(local(BIG.tag))
    error = raised.value
    assert error.code == "ram_guard"
    assert error.detail == {"needed_gb": 5.2, "free_gb": 2.8, "suggested_model": MID.tag}
    envelope = build_envelope(error.code, error.technical, **error.detail)
    assert envelope["message"] == "Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres."
    assert envelope["detail"]["suggested_model"] == MID.tag
    assert ps.reads == 1


async def test_the_suggestion_is_the_biggest_local_chat_model_that_fits():
    # 3,5 Go libres : MID (2,48) tient, BIG (5,12) non ; l'embedding n'est jamais proposé.
    with pytest.raises(AppError) as raised:
        await guard(Needs(BIG, SMALL, MID, EMBED), 3.5).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] == MID.tag
    # 1,3 Go libres : seul SMALL (1,16) tient.
    with pytest.raises(AppError) as raised:
        await guard(Needs(BIG, SMALL, MID, EMBED), 1.3).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] == SMALL.tag


async def test_no_suggestion_when_nothing_fits():
    with pytest.raises(AppError) as raised:
        await guard(Needs(BIG, MID, SMALL, EMBED), 0.9).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] is None
    assert raised.value.detail["free_gb"] == 0.9


async def test_the_refused_model_is_never_its_own_suggestion():
    with pytest.raises(AppError) as raised:
        await guard(Needs(BIG), 2.8).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] is None


async def test_a_model_already_loaded_is_not_blocked():
    """Chargé en entier, son besoin est nul : la mémoire libre ne le compte plus (AC 1)."""
    ps = Ps(LoadedModel(BIG.tag, size_gb=4.5, vram_gb=0.0))
    await guard(Needs(BIG, SMALL), 0.4, ps).check(local(BIG.tag))
    assert ps.reads == 1  # elle n'est lue que parce que le modèle ne tient pas à vide


async def test_ollamas_own_size_never_makes_a_loaded_model_blocked():
    """Chargé plus petit que l'estimation (3,0 Go pour 4,2 Go estimés) : il reste chargé en entier,
    la mesure d'Ollama l'emporte sur l'estimation et rien n'est refusé."""
    ps = Ps(LoadedModel(BIG.tag, size_gb=3.0, vram_gb=0.0))
    await guard(Needs(BIG), 0.3, ps).check(local(BIG.tag))


async def test_loaded_models_count_for_the_suggestion_too():
    # BIG est refusé ; MID est chargé (besoin nul) : il tient même sans mémoire libre.
    ps = Ps(LoadedModel(MID.tag, size_gb=2.0, vram_gb=0.0))
    with pytest.raises(AppError) as raised:
        await guard(Needs(BIG, MID, SMALL), 0.2, ps).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] == MID.tag


async def test_a_cloud_model_is_never_guarded():
    ps = Ps()
    cloud = ModelRef("openai/gpt-x", "openai", "cloud", "chat")
    await guard(Needs(ModelNeed(cloud.tag, "chat", 400.0)), 0.1, ps).check(cloud)
    assert ps.reads == 0


async def test_an_unknown_need_is_never_a_refusal():
    ps = Ps()
    await guard(Needs(SMALL), 0.1, ps).check(local("inconnu:1b"))
    assert ps.reads == 0


async def test_a_silent_ollama_is_not_a_refusal():
    await guard(Needs(BIG), 0.5, Ps(down=True)).check(local(BIG.tag))


async def test_a_guard_that_breaks_does_not_block_the_answer():
    class Broken:
        def memory_needs(self):
            raise RuntimeError("boum")

    await MemoryGuard(Broken(), HOST, reader=reader(0.1), loaded=Ps()).check(local(BIG.tag))


# --- Enveloppe et déchargement -----------------------------------------------------------------


def test_ram_guard_declares_its_machine_keys_and_keeps_the_text_french():
    from wavelocalai.errors import ERRORS

    spec = ERRORS["ram_guard"]
    assert spec.detail_keys == ("needed_gb", "free_gb", "suggested_model")
    envelope = build_envelope(
        "ram_guard", None, needed_gb=7.0, free_gb=2.0, suggested_model="qwen2.5:0.5b"
    )
    assert envelope["message"] == "Mémoire insuffisante : 7,0 Go nécessaires, 2,0 Go libres."
    assert "modèle plus petit" in envelope["action"]
    with pytest.raises(ValueError):
        build_envelope("ram_guard", None, needed_gb=1.0, free_gb=1.0, tag="x")


def _ollama(
    loaded: list[str], *, refuse: set[str] = frozenset(), embedding: set[str] = frozenset()
):
    calls: list[tuple[str, dict]] = []
    state = {"loaded": list(loaded)}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"model": tag, "size": 2 * 1024**3, "size_vram": 0}
                        for tag in state["loaded"]
                    ]
                },
            )
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        assert body["keep_alive"] == 0
        if body["model"] in refuse:
            return httpx.Response(500, text="boum")
        if request.url.path == "/api/generate" and body["model"] in embedding:
            return httpx.Response(400, json={"error": "does not support generate"})
        state["loaded"].remove(body["model"])
        return httpx.Response(200, json={"done": True})

    return httpx.MockTransport(handle), calls


async def test_unloading_leaves_the_models_a_run_uses():
    transport, calls = _ollama(["a:1b", "b:2b", "emb"], embedding={"emb"})
    report = await unload_idle_models(
        HOST,
        lambda: {"a:1b": "run-1"},
        reader=reader(6.34),
        transport=transport,
        settle_s=0.5,
    )
    assert report.unloaded == ["b:2b", "emb"]
    assert report.kept == [{"tag": "a:1b", "run_id": "run-1"}]
    assert report.failed == []
    assert report.free_gb == 6.3
    # Le modèle d'embedding refuse `generate` (400) : `embed` prend le relais.
    assert [path for path, _ in calls] == ["/api/generate", "/api/generate", "/api/embed"]
    assert all(body["model"] != "a:1b" for _, body in calls)


async def test_a_model_ollama_refuses_to_unload_is_reported_not_hidden():
    transport, _ = _ollama(["a:1b", "b:2b"], refuse={"b:2b"})
    report = await unload_idle_models(
        HOST, dict, reader=reader(5.0), transport=transport, settle_s=0.1
    )
    assert report.unloaded == ["a:1b"] and report.failed == ["b:2b"]


async def test_unloading_with_nothing_loaded_is_a_calm_no_op():
    transport, calls = _ollama([])
    report = await unload_idle_models(HOST, dict, reader=reader(5.0), transport=transport)
    assert (report.unloaded, report.kept, report.failed) == ([], [], [])
    assert calls == []


async def test_unloading_says_ollama_is_down():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refusé", request=request)

    with pytest.raises(AppError) as raised:
        await unload_idle_models(HOST, dict, transport=httpx.MockTransport(refuse))
    assert raised.value.code == "ollama_down"
    assert await unload_model(HOST, "a:1b", transport=httpx.MockTransport(refuse)) is False


# --- Revue : modèles inactifs, suggestion plus petite, déchargement relu -----------------------


async def test_an_idle_loaded_model_counts_as_free_memory():
    """`a:7b` reste chargé (keep_alive) après la lane ou le chat précédent : Ollama l'évincera pour
    `b:4b`. 3,0 Go libres + 5,0 Go inactifs couvrent les 4,9 Go requis : aucun refus à tort."""
    ps = Ps(LoadedModel("a:7b", size_gb=5.0, vram_gb=0.0))
    needs = Needs(ModelNeed("a:7b", "chat", 6.0), ModelNeed("b:4b", "chat", 4.0))
    await guard(needs, 3.0, ps).check(local("b:4b"))
    assert ps.reads == 1


async def test_a_refusal_counts_the_idle_models_in_the_free_memory():
    # 1,0 Go libre + 2,0 Go inactifs (MID) = 3,0 Go : BIG (5,12 Go) ne tient toujours pas.
    ps = Ps(LoadedModel(MID.tag, size_gb=2.0, vram_gb=0.0))
    with pytest.raises(AppError) as raised:
        await guard(Needs(BIG, MID, SMALL), 1.0, ps).check(local(BIG.tag))
    assert raised.value.detail == {"needed_gb": 5.2, "free_gb": 3.0, "suggested_model": MID.tag}


async def test_the_suggestion_is_never_bigger_than_the_refused_model():
    """Un modèle chargé tient toujours, mais « Prendre un modèle plus petit » ne propose jamais un
    modèle au besoin supérieur ou égal à celui du modèle refusé."""
    huge = ModelNeed("huge:32b", "chat", 20.0)
    ps = Ps(LoadedModel(huge.tag, size_gb=0.5, vram_gb=0.0))  # chargé (mesure basse)
    with pytest.raises(AppError) as raised:
        await guard(Needs(huge, BIG, SMALL), 0.8, ps).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] == SMALL.tag  # 0,8 + 0,5 Go : SMALL tient
    # Rien de plus petit ne tient : aucune proposition plutôt qu'un modèle plus gros.
    with pytest.raises(AppError) as raised:
        await guard(Needs(huge, BIG), 0.5, ps).check(local(BIG.tag))
    assert raised.value.detail["suggested_model"] is None


async def test_unloading_rereads_the_active_runs_before_each_model():
    """Un run lancé pendant la boucle (après le premier déchargement) garde son modèle."""
    transport, calls = _ollama(["a:1b", "b:2b"])
    busy: dict[str, str] = {}

    def active() -> dict[str, str]:
        snapshot = dict(busy)
        busy["b:2b"] = "run-late"  # le run démarre juste après la première lecture
        return snapshot

    report = await unload_idle_models(
        HOST, active, reader=reader(5.0), transport=transport, settle_s=0.1
    )
    assert report.unloaded == ["a:1b"]
    assert report.kept == [{"tag": "b:2b", "run_id": "run-late"}]
    assert all(body["model"] != "b:2b" for _, body in calls)
