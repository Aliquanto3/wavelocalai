"""Installation d'un modèle (story 5.3) : lecture du flux `/api/pull`, tag, progression, enveloppe,
et mémoire qui manque. Faux Ollama seulement : aucun téléchargement."""

from __future__ import annotations

import httpx
import pytest

from wavelocalai.errors import PULL_CAUSES, AppError, pull_failed_envelope
from wavelocalai.hardware.memory import FIT_MARGIN, MemoryAdvisor, MemoryReading, required_gb
from wavelocalai.inference.pull import clean_tag, progress_data
from wavelocalai.models.ollama_pull import Layers, PullError, PullUpdate, parse_line, pull_updates

from ..pull_fake import GB, PullOllama, PullScript, download, layer, manifest, success


async def collect(ollama: PullOllama, tag: str = "qwen3.6:7b") -> list[PullUpdate]:
    return [
        update
        async for update in pull_updates("http://127.0.0.1:11434", tag, transport=ollama.transport)
    ]


# --- Lecture du flux --------------------------------------------------------------------------


def test_layers_are_added_and_the_total_never_goes_down():
    layers = Layers()
    layers.update("a", 1000, 400)
    layers.update("b", 500, 0)
    assert (layers.received, layers.total) == (400, 1500)
    layers.update("a", 0, 1000)  # une ligne sans total garde celui de la couche
    assert (layers.received, layers.total) == (1000, 1500)
    layers.update("a", 1000, 5000)  # jamais plus que le total
    assert layers.received == 1000


def test_each_line_of_the_stream_gives_its_phase():
    layers = Layers()
    assert parse_line(manifest(), layers) == PullUpdate("preparing")
    assert parse_line(layer("sha256:abc", 100, 25), layers) == PullUpdate("downloading", 25, 100)
    assert parse_line({"status": "verifying sha256 digest"}, layers).phase == "verifying"
    assert parse_line({"status": "writing manifest"}, layers).phase == "verifying"
    assert parse_line({}, layers) is None
    done = parse_line(success(), layers)
    assert done is not None and done.done and done.total_bytes == 100


@pytest.mark.parametrize(
    ("message", "cause"),
    [
        ("pull model manifest: file does not exist", "not_found"),
        ("pull model manifest: Not Found", "not_found"),
        ("write /root/.ollama: no space left on device", "interrupted"),
    ],
)
def test_an_error_line_gives_a_cause_of_the_closed_list(message, cause):
    with pytest.raises(PullError) as raised:
        parse_line({"error": message}, Layers())
    assert raised.value.cause == cause and message in raised.value.technical


async def test_a_whole_download_goes_from_preparing_to_success_with_bytes_of_the_layers():
    ollama = PullOllama(scripts=[PullScript(download(4 * GB, steps=4))])
    updates = await collect(ollama)
    assert updates[0] == PullUpdate("preparing")
    downloading = [u for u in updates if u.phase == "downloading"]
    assert [u.received_bytes for u in downloading] == [i * GB for i in (1, 2, 3, 4)]
    assert {u.total_bytes for u in downloading} == {4 * GB}
    assert updates[-1].done and ollama.pull_requests == [{"model": "qwen3.6:7b", "stream": True}]
    assert ollama.pull_closed == 1  # le flux HTTP est refermé


async def test_an_unknown_name_is_not_found_whether_ollama_says_it_by_status_or_by_line():
    by_status = PullOllama(
        scripts=[PullScript(end="http_error", status=404, body='{"error":"pull model manifest"}')]
    )
    with pytest.raises(PullError) as first:
        await collect(by_status)
    by_line = PullOllama(
        scripts=[PullScript([manifest(), {"error": "pull model manifest: file does not exist"}])]
    )
    with pytest.raises(PullError) as second:
        await collect(by_line)
    assert first.value.cause == second.value.cause == "not_found"


@pytest.mark.parametrize("end", ["refuse", "error"])
async def test_ollama_stopping_gives_ollama_down(end):
    lines = [manifest(), layer("sha256:aaaa", 100, 10)] if end == "error" else []
    ollama = PullOllama(scripts=[PullScript(lines, end=end)])
    with pytest.raises(PullError) as raised:
        await collect(ollama)
    assert raised.value.cause == "ollama_down"


async def test_a_stream_closed_without_success_is_not_an_installation():
    ollama = PullOllama(scripts=[PullScript([manifest(), layer("sha256:aaaa", 100, 100)])])
    with pytest.raises(PullError) as raised:
        await collect(ollama)
    assert raised.value.cause == "ollama_down" and "success" in raised.value.technical


# --- Tag, progression, enveloppe --------------------------------------------------------------


@pytest.mark.parametrize(
    "tag", ["qwen3.6:7b", " granite4.1:8b ", "hf.co/unsloth/Qwen3-GGUF:Q4_K_M", "nomic-embed-text"]
)
def test_a_tag_of_ollama_is_kept_without_its_spaces(tag):
    assert clean_tag(tag) == tag.strip()


@pytest.mark.parametrize(
    "tag", ["", "  ", "deux mots", "../etc", "a;b", "x" * 201, "-nom", "a:b\nc"]
)
def test_a_tag_that_is_not_a_name_of_ollama_is_refused(tag):
    with pytest.raises(AppError) as raised:
        clean_tag(tag)
    assert raised.value.code == "invalid_request"


@pytest.mark.parametrize("tag", ["gpt-oss:120b-cloud", "glm-4.6:cloud", "deepseek-v3.1:671b-cloud"])
def test_a_remote_tag_is_refused_because_its_data_would_leave_the_machine(tag):
    with pytest.raises(AppError) as raised:
        clean_tag(tag)
    assert raised.value.code == "cloud_not_allowed" and raised.value.detail == {"tag": tag}


def test_the_percent_is_the_servers_and_unknown_until_a_total_is_announced():
    assert progress_data("m", PullUpdate("preparing"))["percent"] is None
    data = progress_data("m", PullUpdate("downloading", 1_200_000_000, 4_700_000_000))
    assert data == {
        "tag": "m",
        "received_bytes": 1_200_000_000,
        "total_bytes": 4_700_000_000,
        "percent": 25,
        "phase": "downloading",
    }
    assert progress_data("m", PullUpdate("verifying", 10, 10))["percent"] == 100
    assert progress_data("m", PullUpdate("downloading", 12, 10))["received_bytes"] == 10


@pytest.mark.parametrize("cause", sorted(PULL_CAUSES))
def test_each_cause_has_its_own_message_and_action_and_the_tag_in_the_detail(cause):
    envelope = pull_failed_envelope("granite4.1:8b", cause, "POST /api/pull : échec")
    assert envelope["code"] == "pull_failed"
    assert envelope["detail"] == {
        "technical": "POST /api/pull : échec",
        "tag": "granite4.1:8b",
        "cause": cause,
    }
    assert "granite4.1:8b" in envelope["message"] and "{" not in envelope["message"]
    assert "La liste des modèles est inchangée." in envelope["action"]
    assert envelope["message"] != pull_failed_envelope("granite4.1:8b", "autre")["message"]


# --- Mémoire qui manque -----------------------------------------------------------------------


def advisor(available_gb: float) -> MemoryAdvisor:
    return MemoryAdvisor(lambda: MemoryReading(16.0, available_gb))


def test_the_missing_memory_is_what_the_model_requires_beyond_the_free_memory():
    result = advisor(4.8).assess(measured_loaded_gb=5.0)
    assert result.fits is False
    assert result.required_gb == 6.0  # 5,0 × 1,1 + 0,5
    assert result.short_gb == pytest.approx(1.2)  # 6,0 − 4,8, dixième supérieur
    assert advisor(8.0).assess(measured_loaded_gb=5.0).short_gb is None  # il tient
    assert advisor(8.0).assess().short_gb is None  # besoin inconnu : jamais deviné


def test_memory_of_loaded_models_counts_as_free_like_the_guard_does():
    needed = 5.0
    assert advisor(2.0).assess(measured_loaded_gb=needed).fits is False
    with_loaded = advisor(2.0).assess(measured_loaded_gb=needed, reclaimable_gb=4.5)
    assert with_loaded.fits is True and with_loaded.available_gb == 6.5
    assert needed * FIT_MARGIN <= 6.5 - 0.5
    assert required_gb(needed) == 6.0
    # Une valeur négative n'enlève rien.
    assert advisor(2.0).assess(measured_loaded_gb=needed, reclaimable_gb=-3.0).available_gb == 2.0
