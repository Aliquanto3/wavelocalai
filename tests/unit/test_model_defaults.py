"""
Tests de la règle des choix par défaut (src/core/model_defaults.py) : ordre des sélecteurs,
modèle proposé, juge par défaut, présélection de l'Arène.

Catalogue versionné, data/models.json et mémoire disponible simulés : ni Ollama ni réseau.
Usage: python -m pytest tests/unit/test_model_defaults.py -v
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core import model_defaults as md
from src.core.benchmark_results import BenchScore
from src.core.config import SYSTEM_RAM_BUFFER_GB

ROOT_DIR = Path(__file__).resolve().parents[2]
GB = 1024**3

# Catalogue versionné simulé (format de config/models_catalog.json, clé "models").
CATALOG = {
    "Petit 1B": {
        "ollama_tag": "petit:1b",
        "type": "local",
        "size_gb": "0.8 GB",
        "params_tot": "1B",
        "params_act": "1B",
        "measured_loaded_gb": 1.2,
    },
    "Moyen 3.8B": {
        "ollama_tag": "moyen:3.8b",
        "type": "local",
        "size_gb": "2.5 GB",
        "params_tot": "3.8B",
        "params_act": "3.8B",
        "measured_loaded_gb": 3.1,
    },
    "Gros 8B": {
        "ollama_tag": "gros:8b",
        "type": "local",
        "size_gb": "4.1 GB",
        "params_tot": "8B",
        "params_act": "8B",
        "measured_loaded_gb": 4.9,
    },
    # MoE : mesure absente (None), paramètres actifs distincts du total.
    "MoE 30B-A3B": {
        "ollama_tag": "moe:30b-a3b",
        "type": "local",
        "size_gb": "18 GB",
        "params_tot": "30B",
        "params_act": "3B",
        "measured_loaded_gb": None,
        "moe": True,
    },
}


def _local(tag: str, size_bytes: int = 0, parameter_size: str | None = None) -> dict:
    """Modèle local au format de LLMProvider.list_models."""
    details = {"parameter_size": parameter_size} if parameter_size else {}
    return {"model": tag, "size": size_bytes, "details": details, "type": "local"}


CLOUD = {"model": "mistral-large-2512", "size": 0, "type": "cloud", "provider": "mistral"}
PETIT, MOYEN, GROS = _local("petit:1b"), _local("moyen:3.8b"), _local("gros:8b")


def _rank(models, available_gb, models_db=None, catalog=None, **kwargs):
    return md.rank_models(
        models,
        available_gb,
        catalog=CATALOG if catalog is None else catalog,
        models_db=models_db or {},
        **kwargs,
    )


def _tags(ranked):
    return [c.tag for c in ranked]


def _speeds(**speeds):
    """data/models.json simulé : débit mesuré par tag."""
    return {
        tag: {"ollama_tag": tag, "benchmark_stats": {"avg_tokens_per_second": tps}}
        for tag, tps in speeds.items()
    }


# ---------------------------------------------------------------------------
# Matrice de la story 7
# ---------------------------------------------------------------------------


def test_order_local_first_fastest_fitting_first_cloud_last():
    """Ordre : 1 cloud, 3 locaux (1,2 / 3,1 / 4,9 Go mesurés), 8 Go disponibles."""
    ranked = _rank([CLOUD, GROS, MOYEN, PETIT], available_gb=8.0)

    assert _tags(ranked) == ["petit:1b", "moyen:3.8b", "gros:8b", "mistral-large-2512"]
    assert all(c.fits for c in ranked[:3])
    assert ranked[-1].is_cloud and not ranked[-1].fits
    assert md.default_model(ranked).tag == "petit:1b"


def test_model_that_does_not_fit_is_never_preselected():
    """Ne tient pas : local de 4,9 Go, 3 Go disponibles ; jamais présélectionné, placé après
    les locaux qui tiennent."""
    ranked = _rank([GROS, PETIT, CLOUD], available_gb=3.0)

    gros = next(c for c in ranked if c.tag == "gros:8b")
    assert not gros.fits
    assert _tags(ranked) == ["petit:1b", "gros:8b", "mistral-large-2512"]
    assert "gros:8b" not in md.arena_preselection(ranked, md.default_judge(ranked))
    assert md.default_model(ranked).tag == "petit:1b"


def test_missing_measurement_uses_documented_fallback():
    """Mesure absente : taille du téléchargement × 1,25 (catalogue versionné, puis
    data/models.json, puis taille renvoyée par Ollama)."""
    moe = md.describe_model(_local("moe:30b-a3b"), 32.0, False, CATALOG, {})
    assert moe.footprint_gb == pytest.approx(18 * md.SIZE_TO_LOADED)
    assert moe.params_b == 3.0  # paramètres actifs, pas le total

    db = {"Hors catalogue": {"ollama_tag": "hors:2b", "size_gb": "2.0 GB"}}
    from_db = md.describe_model(_local("hors:2b"), 32.0, False, {}, db)
    assert from_db.footprint_gb == pytest.approx(2.0 * md.SIZE_TO_LOADED)

    from_ollama = md.describe_model(_local("inconnu:1b", size_bytes=2 * GB), 32.0, False, {}, {})
    assert from_ollama.footprint_gb == pytest.approx(2.0 * md.SIZE_TO_LOADED)
    assert from_ollama.fits


def test_missing_measurement_without_estimate_does_not_fit():
    """Mesure absente, aucune estimation : considéré comme ne tenant pas."""
    unknown = _local("inconnu:7b")
    ranked = _rank([unknown, PETIT, MOYEN], available_gb=64.0)

    choice = next(c for c in ranked if c.tag == "inconnu:7b")
    assert choice.footprint_gb is None and not choice.fits
    assert _tags(ranked)[-1] == "inconnu:7b"
    assert "inconnu:7b" not in md.arena_preselection(ranked, md.default_judge(ranked))
    assert md.default_judge(ranked).tag != "inconnu:7b"


def test_nothing_fits_first_is_smallest_local():
    """Aucun local ne tient : le premier proposé est le plus petit local ; aucun plantage."""
    ranked = _rank([CLOUD, GROS, MOYEN, PETIT], available_gb=1.0)

    assert not any(c.fits for c in ranked)
    assert _tags(ranked) == ["petit:1b", "moyen:3.8b", "gros:8b", "mistral-large-2512"]
    assert md.default_model(ranked).tag == "petit:1b"
    assert md.default_judge(ranked).tag == "petit:1b"
    assert md.arena_preselection(ranked, md.default_judge(ranked)) == []


def test_judge_is_largest_fitting_local_with_weak_warning():
    """Juge : locaux de 1B, 3,8B et 8B, le 8B ne tient pas ; juge = 3,8B, note peu fiable."""
    ranked = _rank([PETIT, MOYEN, GROS, CLOUD], available_gb=4.0)

    assert not next(c for c in ranked if c.tag == "gros:8b").fits
    judge = md.default_judge(ranked)
    assert judge.tag == "moyen:3.8b"
    assert judge.weak_judge


def test_judge_of_at_least_4b_has_no_warning():
    """Juge suffisant : un local ≥ 4B tient ; c'est le juge, sans avertissement."""
    ranked = _rank([PETIT, MOYEN, GROS, CLOUD], available_gb=8.0)

    judge = md.default_judge(ranked)
    assert judge.tag == "gros:8b"
    assert not judge.weak_judge


def test_arena_preselects_two_to_three_small_fitting_locals_without_judge():
    """Arène, défaut : ≥ 2 locaux qui tiennent ; 2 à 3 petits locaux présélectionnés (les
    plus rapides, ici les plus petites empreintes), jamais le cloud ni le juge."""
    fourth = _local("quatre:2b", size_bytes=2 * GB, parameter_size="2B")
    ranked = _rank([CLOUD, GROS, MOYEN, PETIT, fourth], available_gb=16.0)
    judge = md.default_judge(ranked)

    assert judge.tag == "gros:8b"
    assert md.arena_preselection(ranked, judge) == ["petit:1b", "quatre:2b", "moyen:3.8b"]


def test_arena_with_exactly_two_fitting_keeps_two_models():
    """Deux locaux qui tiennent seulement : les deux sont présélectionnés (le juge revient
    pour atteindre le minimum de 2), le lancement reste possible sans rien toucher."""
    ranked = _rank([CLOUD, MOYEN, PETIT, GROS], available_gb=4.0)
    judge = md.default_judge(ranked)

    assert judge.tag == "moyen:3.8b"
    assert md.arena_preselection(ranked, judge) == ["petit:1b", "moyen:3.8b"]


def test_arena_with_a_single_fitting_model():
    """Un seul local tient : présélection incomplète (1 modèle), jamais un modèle qui ne
    tient pas ni un cloud."""
    ranked = _rank([CLOUD, MOYEN, PETIT, GROS], available_gb=2.0)
    assert md.arena_preselection(ranked, md.default_judge(ranked)) == ["petit:1b"]


def test_empty_list():
    assert md.rank_models([], 8.0, catalog={}, models_db={}) == []
    assert md.default_model([]) is None
    assert md.default_judge([]) is None
    assert md.arena_preselection([], None) == []


# ---------------------------------------------------------------------------
# « Le plus rapide »
# ---------------------------------------------------------------------------


def test_known_speed_breaks_ties_only_when_all_fitting_have_one():
    """Débits connus pour tous les locaux qui tiennent : le plus rapide en tête."""
    models_db = _speeds(**{"petit:1b": 40, "moyen:3.8b": 60, "gros:8b": 20})
    ranked = _rank([PETIT, MOYEN, GROS], available_gb=16.0, models_db=models_db)

    assert _tags(ranked) == ["moyen:3.8b", "petit:1b", "gros:8b"]
    assert ranked[0].speed_tps == 60.0


def test_known_speed_never_beats_unknown_speed():
    """Un seul débit connu (mesuré sur une autre machine) : ignoré, la plus petite empreinte
    reste l'indicateur de vitesse."""
    models_db = _speeds(**{"moyen:3.8b": 500})
    ranked = _rank([GROS, MOYEN, PETIT], available_gb=16.0, models_db=models_db)

    assert _tags(ranked) == ["petit:1b", "moyen:3.8b", "gros:8b"]


def test_speed_of_a_model_that_does_not_fit_is_ignored():
    """Un débit connu ne fait pas passer devant un modèle qui ne tient pas."""
    models_db = _speeds(**{"petit:1b": 40, "moyen:3.8b": 30, "gros:8b": 500})
    ranked = _rank([GROS, MOYEN, PETIT], available_gb=4.0, models_db=models_db)

    assert _tags(ranked) == ["petit:1b", "moyen:3.8b", "gros:8b"]


# ---------------------------------------------------------------------------
# « Le plus gros » (juge)
# ---------------------------------------------------------------------------


def test_judge_uses_footprint_not_total_parameters():
    """Un 27B quantifié en 1 bit (4,9 Go) ne passe pas devant un 9B en 3 bits (5,4 Go)."""
    catalog = {
        "Bonsai 27B (1-bit)": {
            "ollama_tag": "bonsai:27b-q1_0",
            "params_tot": "27B",
            "params_act": "27B",
            "measured_loaded_gb": 4.902,
        },
        "Qwen 3.5 9B": {
            "ollama_tag": "qwen3.5-ud:9b-q3_k_xl",
            "params_tot": "9.7B",
            "params_act": "9.7B",
            "measured_loaded_gb": 5.411,
        },
    }
    models = [_local("bonsai:27b-q1_0"), _local("qwen3.5-ud:9b-q3_k_xl")]
    ranked = _rank(models, available_gb=16.0, catalog=catalog)

    assert md.default_judge(ranked).tag == "qwen3.5-ud:9b-q3_k_xl"


def test_judge_prefers_reliable_judge_over_larger_moe():
    """Un MoE à grosse empreinte et 1,3B actifs (Ling 3.0 Tiny) ne passe pas devant un juge
    ≥ 4B qui tient : juges fiables d'abord, puis la plus grande empreinte."""
    catalog = {
        "Ling 3.0 Tiny": {
            "ollama_tag": "ling3-tiny:8b-q4_k_m",
            "params_tot": "7.9B",
            "params_act": "1.3B",
            "measured_loaded_gb": 4.646,
        },
        "Qwen 3.5 4B": {
            "ollama_tag": "qwen3.5:4b",
            "params_tot": "4.7B",
            "params_act": "4.7B",
            "measured_loaded_gb": 3.3,
        },
    }
    models = [_local("ling3-tiny:8b-q4_k_m"), _local("qwen3.5:4b")]
    ranked = _rank(models, available_gb=16.0, catalog=catalog)

    judge = md.default_judge(ranked)
    assert judge.tag == "qwen3.5:4b"
    assert not judge.weak_judge

    # Seulement des juges faibles : la plus grande empreinte.
    only_weak = _rank([models[0], PETIT], available_gb=16.0, catalog={**CATALOG, **catalog})
    assert md.default_judge(only_weak).tag == "ling3-tiny:8b-q4_k_m"


def test_no_default_judge_without_local_model():
    """Seulement du cloud : aucun juge par défaut (jamais un juge cloud par défaut)."""
    ranked = _rank([CLOUD], available_gb=16.0)
    assert md.default_judge(ranked) is None
    assert md.arena_preselection(ranked, None) == []


def test_judge_ties_on_footprint_broken_by_active_params():
    catalog = {
        "A": {"ollama_tag": "a:2b", "params_act": "2B", "measured_loaded_gb": 3.0},
        "B": {"ollama_tag": "b:4b", "params_act": "4B", "measured_loaded_gb": 3.0},
    }
    ranked = _rank([_local("a:2b"), _local("b:4b")], available_gb=16.0, catalog=catalog)
    assert md.default_judge(ranked).tag == "b:4b"


def test_moe_judged_on_active_parameters():
    """Paramètres : `params_act` (catalogue, puis data/models.json) avant `params_tot` ;
    `parameter_size` d'Ollama (un total) en dernier recours."""
    # Catalogue : actifs 3B, total 30B.
    assert md.active_params_b(CATALOG["MoE 30B-A3B"]) == 3.0
    # `params_act` de data/models.json passe devant `params_tot` du catalogue versionné.
    assert md.active_params_b({"params_tot": "30B"}, {"params_act": "3B"}) == 3.0
    # Ollama seulement en dernier recours.
    assert md.active_params_b({}, {}, {"parameter_size": "30.5B"}) == 30.5
    assert md.active_params_b({"params_tot": "8B"}, {}, {"parameter_size": "30.5B"}) == 8.0
    assert md.active_params_b({}, {}, {}) is None


def test_judge_of_unknown_size_is_weak():
    """Juge local de taille inconnue : note peu fiable ; juge cloud : jamais marqué."""
    unknown = md.ModelChoice("x:latest", False, 2.0, None, None, True)
    assert unknown.weak_judge
    cloud = md.ModelChoice("mistral-large-2512", True, None, None, None, False)
    assert not cloud.weak_judge


def test_judge_ignores_cloud_even_if_larger():
    """Le juge par défaut est local : un modèle cloud n'est jamais choisi s'il y a un local
    qui tient ; un juge cloud n'est pas marqué peu fiable."""
    cloud = dict(CLOUD, details={"parameter_size": "123B"})
    ranked = _rank([PETIT, cloud], available_gb=8.0)

    assert md.default_judge(ranked).tag == "petit:1b"
    assert not next(c for c in ranked if c.is_cloud).weak_judge


def test_judge_params_fall_back_to_ollama_details():
    """Hors catalogue : paramètres lus dans `details.parameter_size` d'Ollama."""
    small = _local("a:1b", size_bytes=1 * GB, parameter_size="1.2B")
    big = _local("b:7b", size_bytes=4 * GB, parameter_size="7.6B")
    ranked = md.rank_models([small, big], 16.0, catalog={}, models_db={})

    judge = md.default_judge(ranked)
    assert judge.tag == "b:7b" and judge.params_b == 7.6
    assert not judge.weak_judge
    assert md.default_model(ranked).tag == "a:1b"


# ---------------------------------------------------------------------------
# « Tient en mémoire »
# ---------------------------------------------------------------------------


def test_fit_threshold_keeps_margin_and_system_reserve():
    """« Tient » : empreinte × 1,10 ≤ mémoire disponible − réserve système de config.py."""
    limit = 3.0 * md.FIT_MARGIN + SYSTEM_RAM_BUFFER_GB
    assert md.fits_in_memory(3.0, limit)
    assert not md.fits_in_memory(3.0, limit - 0.01)
    # Sans la marge, 3,0 Go tiendraient dans 3,5 Go disponibles : pas avec elle.
    assert not md.fits_in_memory(3.0, 3.0 + SYSTEM_RAM_BUFFER_GB)
    assert not md.fits_in_memory(None, 1000.0)


def test_constants_match_bench_here():
    """Marge et repli identiques à scripts/bench_here.py (lu en texte, sans l'importer)."""
    source = (ROOT_DIR / "scripts" / "bench_here.py").read_text(encoding="utf-8")

    def constant(name: str) -> float:
        match = re.search(rf"^{name}\s*=\s*([0-9.]+)\s*$", source, re.MULTILINE)
        assert match, f"{name} introuvable dans scripts/bench_here.py"
        return float(match.group(1))

    assert constant("FIT_MARGIN") == md.FIT_MARGIN
    assert constant("SIZE_TO_LOADED") == md.SIZE_TO_LOADED


def test_loaded_models_ram_from_ollama_ps():
    """Mémoire des modèles déjà chargés : taille chargée moins la part en mémoire vidéo ;
    0 si `ps()` échoue."""
    from src.core.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider()
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = SimpleNamespace(
            models=[
                SimpleNamespace(model="a:1b", size=3 * GB, size_vram=1 * GB),
                SimpleNamespace(model="b:1b", size=1 * GB, size_vram=None),
            ]
        )
        assert provider.loaded_models_ram_gb() == pytest.approx(3.0)
        mock_ollama.Client.return_value.ps.return_value = {
            "models": [{"name": "c:1b", "size": 2 * GB, "size_vram": 2 * GB}]
        }
        assert provider.loaded_models_ram_gb() == pytest.approx(0.0)
        mock_ollama.Client.return_value.ps.side_effect = ConnectionError("refused")
        assert provider.loaded_models_ram_gb() == 0.0


def test_loaded_models_ram_ignored_for_remote_ollama_host():
    """Hôte Ollama distant : sa mémoire n'est pas celle de cette machine ; `ps()` n'est pas
    appelé et rien n'est ajouté."""
    from src.core.providers.ollama_provider import OllamaProvider

    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        assert OllamaProvider("http://10.0.0.5:11434").loaded_models_ram_gb() == 0.0
        mock_ollama.Client.return_value.ps.assert_not_called()
        for url in ("http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"):
            assert OllamaProvider(url).is_local_host()


def test_llm_provider_loaded_models_ram(monkeypatch):
    """LLMProvider.loaded_models_ram_gb : somme renvoyée par `ps()` ; 0,0 en cas d'erreur,
    y compris quand le fournisseur Ollama lui-même est introuvable."""
    from src.core.llm_provider import LLMProvider
    from src.core.providers.ollama_provider import OllamaProvider

    monkeypatch.setattr(LLMProvider, "_ollama_provider", staticmethod(OllamaProvider))
    with patch("src.core.providers.ollama_provider.ollama") as mock_ollama:
        mock_ollama.Client.return_value.ps.return_value = {
            "models": [
                {"name": "a:1b", "size": 2 * GB, "size_vram": 0},
                {"name": "b:1b", "size": 1 * GB},
            ]
        }
        assert LLMProvider.loaded_models_ram_gb() == pytest.approx(3.0)
        mock_ollama.Client.return_value.ps.side_effect = ConnectionError("refused")
        assert LLMProvider.loaded_models_ram_gb() == 0.0

    def broken():
        raise RuntimeError("factory indisponible")

    monkeypatch.setattr(LLMProvider, "_ollama_provider", staticmethod(broken))
    assert LLMProvider.loaded_models_ram_gb() == 0.0


# ---------------------------------------------------------------------------
# Robustesse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model",
    [
        {"model": "gpt-oss:120b-cloud", "type": "local", "size": 384},
        {"model": "glm-4.6:cloud", "type": "local", "size": 384},
        {"model": "kimi-k2-cloud:latest", "type": "local", "size": 384},
        {"model": "deepseek-v3.1:671b", "type": "local", "remote_host": "https://ollama.com:443"},
    ],
)
def test_remote_tag_served_by_ollama_is_cloud(model):
    """Tag distant servi par Ollama (suffixe `-cloud`, `remote_host`) : traité comme cloud,
    après les locaux, ni présélectionné ni juge."""
    ranked = _rank([model, PETIT, MOYEN], available_gb=16.0)

    assert _tags(ranked)[-1] == model["model"]
    assert ranked[-1].is_cloud and not ranked[-1].fits
    assert model["model"] not in md.arena_preselection(ranked, md.default_judge(ranked))
    assert md.default_judge(ranked).tag != model["model"]


def test_catalog_matches_latest_variant():
    """Correspondance par `ollama_tag`, variante `:latest` comprise."""
    catalog = {"Qwen": {"ollama_tag": "qwen3"}, "Phi": {"ollama_tag": "phi4-mini:latest"}}
    assert md.find_entry("qwen3:latest", catalog) is catalog["Qwen"]
    assert md.find_entry("phi4-mini", catalog) is catalog["Phi"]
    assert md.find_entry("qwen3:8b", catalog) is None


def test_ties_are_broken_by_display_name():
    a = _local("zz:1b", size_bytes=1 * GB)
    b = _local("aa:1b", size_bytes=1 * GB)
    ranked = md.rank_models(
        [a, b], 16.0, catalog={}, models_db={}, names={"zz:1b": "Alpha", "aa:1b": "Beta"}
    )
    assert _tags(ranked) == ["zz:1b", "aa:1b"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.7 GB", 0.7),
        ("1,2 Go", 1.2),
        ("≈ 4.5 GB", 4.5),
        ("350 MB", 0.35),
        (2.5, 2.5),
        ("API", 0.0),
        (None, 0.0),
    ],
)
def test_parse_size_gb(raw, expected):
    assert md.parse_size_gb(raw) == pytest.approx(expected)


def test_unreadable_catalog_is_empty(tmp_path):
    broken = tmp_path / "catalog.json"
    broken.write_text("{ pas du json", encoding="utf-8")
    assert md.load_versioned_catalog(broken) == {}
    assert md.load_versioned_catalog(tmp_path / "absent.json") == {}

    valid = tmp_path / "valid.json"
    valid.write_text(json.dumps({"models": CATALOG}), encoding="utf-8")
    assert md.load_versioned_catalog(valid) == CATALOG


def test_read_failure_is_not_cached_and_result_is_a_copy(tmp_path):
    """Un échec de lecture (fichier en cours de réécriture) n'est pas gardé : la lecture
    suivante réussit. Le résultat est une copie : le modifier ne touche pas le cache."""
    path = tmp_path / "catalog.json"
    path.write_text('{"models": {', encoding="utf-8")  # réécriture en cours
    assert md.load_versioned_catalog(path) == {}

    path.write_text(json.dumps({"models": CATALOG}), encoding="utf-8")
    first = md.load_versioned_catalog(path)
    assert first == CATALOG
    first["Petit 1B"]["measured_loaded_gb"] = 99.0
    first.clear()
    assert md.load_versioned_catalog(path) == CATALOG


@pytest.mark.parametrize(
    "content",
    [
        {"models": [{"ollama_tag": "petit:1b"}]},  # `models` n'est pas un dictionnaire
        {"models": None},
        ["pas", "un", "dictionnaire"],
        {"autre": {}},
    ],
)
def test_catalog_with_unexpected_format_is_ignored(tmp_path, content):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    assert md.load_versioned_catalog(path) == {}


def test_catalog_entries_that_are_not_objects_are_ignored(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"models": {"ok": CATALOG["Petit 1B"], "ko": "?"}}), "utf-8")
    assert md.load_versioned_catalog(path) == {"ok": CATALOG["Petit 1B"]}


# ---------------------------------------------------------------------------
# Catalogue versionné réel (lecture seule)
# ---------------------------------------------------------------------------


def _catalog_as_installed(catalog: dict) -> list[dict]:
    """Chaque entrée du catalogue versionné comme si elle était installée (format de
    LLMProvider.list_models) ; une entrée non locale (API future) compte comme cloud."""
    return [
        {
            "model": entry["ollama_tag"],
            "details": {},
            "type": "local" if entry.get("type", "local") == "local" else "cloud",
        }
        for entry in catalog.values()
        if isinstance(entry.get("ollama_tag"), str) and entry["ollama_tag"]
    ]


@pytest.mark.parametrize("available_gb", [6.5, 20.0])
def test_rule_on_versioned_catalog(available_gb):
    """La règle s'applique au vrai config/models_catalog.json sans erreur. Seuls des
    invariants sont vérifiés (le catalogue est régénéré) : locaux avant cloud, juge local qui
    tient, présélection qui tient, juge hors présélection quand au moins 3 locaux tiennent."""
    catalog = md.load_versioned_catalog()
    models = _catalog_as_installed(catalog)

    ranked = md.rank_models(models, available_gb, catalog=catalog, models_db={})
    assert len(ranked) == len(models)
    assert [c.is_cloud for c in ranked] == sorted(c.is_cloud for c in ranked)

    fitting = [c for c in ranked if c.fits]
    for c in fitting:
        assert c.footprint_gb * md.FIT_MARGIN <= available_gb - SYSTEM_RAM_BUFFER_GB

    judge = md.default_judge(ranked)
    preselection = md.arena_preselection(ranked, judge)
    assert len(preselection) <= md.ARENA_MAX_MODELS
    assert all(next(c for c in ranked if c.tag == t).fits for t in preselection)
    if fitting:
        assert judge in fitting and not judge.is_cloud
        assert ranked[0] in fitting
    if len(fitting) >= 3:
        assert judge.tag not in preselection


# ---------------------------------------------------------------------------
# Story 15 : juge d'après le cloud ou le benchmark de ce poste, modèles de raisonnement
# ---------------------------------------------------------------------------


# Figures de poste-rtx3060 (benchmarks/results/poste-rtx3060-22601cd4.json) : précision
# (moyenne raisonnement / consignes) et débit prudent, paramètres actifs du catalogue.
RTX_MODELS = {
    # nom: (tag, paramètres actifs, empreinte mesurée, précision, débit prudent)
    "Granite 4.0 350M": ("granite4:350m", "0.35B", 1.16, 0.23, 230.07),
    "LFM 2.5 1.2B Thinking": ("lfm2.5-thinking:1.2b", "1.2B", 1.007, 0.66, 272.57),
    "Gemma 3 1B": ("gemma3:1b", "1B", 0.903, 0.59, 185.98),
    "Qwen 3.5 0.8B": ("qwen3.5:0.8b", "0.87B", 1.219, 0.525, 175.71),
    "LFM 2.5 2.6B": ("LiquidAI/lfm2.5-2.6b", "2.7B", 1.972, 0.94, 122.01),
    "Gemma 4 E2B (QAT)": ("gemma4:e2b-it-qat", "2B", 1.548, 0.93, 114.25),
    "Nemotron 3 Nano 4B": ("nemotron-3-nano:4b", "4.0B", 2.938, 0.835, 86.63),
    "Qwen 3.5 4B": ("qwen3.5:4b", "4.7B", 3.3, 0.87, 62.5),
    "Gemma 4 E4B (QAT)": ("gemma4:e4b-it-qat", "4B", None, 0.93, 68.75),
    "Qwen 3.5 9B (Unsloth Q3_K_XL)": ("qwen3.5-ud:9b-q3_k_xl", "9.7B", 5.411, 0.87, 18.73),
    "Gemma 4 12B (Unsloth IQ3_XXS)": ("gemma4-ud:12b-iq3_xxs", "11.9B", 5.379, 0.94, 6.62),
    "Granite 4.2 8B": ("granite4.2:8b", "8.8B", 7.652, 0.795, 5.05),
}
RTX_CATALOG = {
    name: {
        "ollama_tag": tag,
        "type": "local",
        "size_gb": "6.1 GB",
        "params_act": params,
        "params_tot": params,
        "measured_loaded_gb": loaded,
        "capabilities": ["chat", "thinking"] if "qwen" in tag or "gemma4" in tag else ["chat"],
    }
    for name, (tag, params, loaded, _, _) in RTX_MODELS.items()
}
RTX_CATALOG_BY_TAG = {e["ollama_tag"]: e for e in RTX_CATALOG.values()}
RTX_BENCH = {tag: BenchScore(p, s) for tag, _, _, p, s in RTX_MODELS.values()}
RTX_INSTALLED = [_local(tag) for tag, *_ in RTX_MODELS.values()]
# Débits de data/models.json sur ce poste (tous connus : ils départagent les locaux).
RTX_SPEEDS = _speeds(**{tag: s for tag, _, _, _, s in RTX_MODELS.values()})

CLAUDE = {"model": "claude-sonnet-4-20250514", "type": "cloud", "provider": "anthropic"}
GPT4O = {"model": "gpt-4o", "type": "cloud", "provider": "openai"}
GPT4O_MINI = {"model": "gpt-4o-mini", "type": "cloud", "provider": "openai"}


def _rtx(models=None, available_gb=16.7):
    return _rank(
        RTX_INSTALLED if models is None else models,
        available_gb,
        catalog=RTX_CATALOG,
        models_db=RTX_SPEEDS,
    )


def test_cloud_allowed_judge_is_most_capable_cloud():
    """Cloud autorisé, Claude Sonnet 4 et GPT-4o listés : juge = Claude Sonnet 4."""
    ranked = _rtx([GPT4O, *RTX_INSTALLED, CLAUDE])

    judge = md.choose_judge(ranked, RTX_BENCH, allow_cloud=True)
    assert judge.choice.tag == "claude-sonnet-4-20250514"
    assert judge.choice.is_cloud and judge.reason == md.JUDGE_BY_CLOUD
    assert not judge.choice.weak_judge


def test_cloud_judge_order_is_fixed_in_code():
    """Ordre fixé : gpt-4o avant mistral-large ; gpt-4o-mini et les inconnus après, par
    ordre alphabétique."""
    mistral = {"model": "mistral-large-2512", "type": "cloud"}
    unknown = {"model": "aaa-cloud-model", "type": "cloud"}
    ranked = _rank([mistral, GPT4O_MINI, unknown, GPT4O, PETIT], 8.0)
    assert md.default_judge(ranked, allow_cloud=True).tag == "gpt-4o"

    ranked = _rank([GPT4O_MINI, unknown, PETIT], 8.0)
    assert md.default_judge(ranked, allow_cloud=True).tag == "aaa-cloud-model"
    tags = ["gpt-4o-mini", "claude-3-opus-20240229", "claude-3-5-sonnet-20241022", "gpt-4o"]
    assert sorted(tags, key=md.cloud_judge_rank) == [
        "gpt-4o",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "gpt-4o-mini",
    ]


GROQ_MODELS = [
    {"model": tag, "type": "cloud", "provider": "groq"}
    for tag in (
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
    )
]


def test_groq_judge_order():
    """Groq (story 16) : GPT-OSS 120B juste après GPT-4o et avant Mistral Large ; Llama 3.3
    70B après les autres grands modèles cloud ; les autres Groq par ordre alphabétique."""
    tags = [
        "llama-3.3-70b-versatile",
        "mistral-large-2512",
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "gpt-4o",
        "mistral-medium-2508",
        "llama-3.1-8b-instant",
        "claude-sonnet-4-20250514",
    ]
    assert sorted(tags, key=md.cloud_judge_rank) == [
        "claude-sonnet-4-20250514",
        "gpt-4o",
        "openai/gpt-oss-120b",
        "mistral-large-2512",
        "mistral-medium-2508",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-20b",
    ]


def test_groq_only_cloud_judge_is_gpt_oss_120b():
    """Groq seul fournisseur cloud, cloud autorisé : juge = openai/gpt-oss-120b ; cloud
    désactivé : jamais un juge Groq (le benchmark décide)."""
    ranked = _rtx([*GROQ_MODELS, *RTX_INSTALLED])
    assert [c.tag for c in ranked[-4:]] == sorted(m["model"] for m in GROQ_MODELS)
    assert all(c.is_cloud and not c.dedicated_reasoning for c in ranked[-4:])

    judge = md.choose_judge(ranked, RTX_BENCH, allow_cloud=True)
    assert judge.choice.tag == "openai/gpt-oss-120b" and judge.reason == md.JUDGE_BY_CLOUD
    assert md.default_judge(ranked, RTX_BENCH).tag == "gemma4:e4b-it-qat"


def test_no_cloud_judge_when_cloud_is_disabled():
    """Cloud désactivé : jamais un juge cloud, même listé (le benchmark décide)."""
    ranked = _rtx([CLAUDE, *RTX_INSTALLED])

    judge = md.choose_judge(ranked, RTX_BENCH, allow_cloud=False)
    assert judge.choice.tag == "gemma4:e4b-it-qat"
    assert md.default_judge(ranked).tag != "claude-sonnet-4-20250514"


def test_cloud_allowed_without_cloud_model_uses_benchmark():
    judge = md.choose_judge(_rtx(), RTX_BENCH, allow_cloud=True)
    assert judge.reason == md.JUDGE_BY_BENCHMARK


def test_benchmarked_machine_judge_is_gemma_4_e4b():
    """poste-rtx3060, modèles actuels : juge = Gemma 4 E4B (QAT), 0,93 à ~69 tokens/s, sans
    avertissement ; ni Granite 4.2 8B (5 tokens/s), ni les < 4B aussi précis (LFM 2.5 2.6B,
    Gemma 4 E2B), ni Gemma 4 12B (6,6 tokens/s)."""
    ranked = _rtx()

    judge = md.choose_judge(ranked, RTX_BENCH)
    assert judge.choice.tag == "gemma4:e4b-it-qat"
    assert judge.reason == md.JUDGE_BY_BENCHMARK
    assert not judge.choice.weak_judge
    # Sans benchmark de ce poste, la règle de la story 7 choisit la plus grosse empreinte
    # qui tient : Granite 4.2 8B.
    assert md.default_judge(ranked).tag == "granite4.2:8b"


def test_benchmark_judge_without_4b_takes_most_precise_and_stays_weak():
    """Aucun ≥ 4B à plus de 10 tokens/s : le plus précis des rapides, note peu fiable."""
    tags = {"gemma3:1b", "LiquidAI/lfm2.5-2.6b", "granite4.2:8b"}
    ranked = _rtx([m for m in RTX_INSTALLED if m["model"] in tags])

    judge = md.choose_judge(ranked, RTX_BENCH)
    assert judge.choice.tag == "LiquidAI/lfm2.5-2.6b"
    assert judge.reason == md.JUDGE_BY_BENCHMARK
    assert judge.choice.weak_judge


def test_unknown_machine_falls_back_to_footprint_rule():
    """Poste inconnu (benchmark vide) : règle de la story 7."""
    ranked = _rank([PETIT, MOYEN, GROS], 8.0)
    for bench in (None, {}):
        judge = md.choose_judge(ranked, bench)
        assert judge.choice.tag == "gros:8b"
        assert judge.reason == md.JUDGE_BY_FOOTPRINT


def test_nothing_above_10_tps_falls_back_to_footprint_rule():
    """Aucun modèle au-dessus de 10 tokens/s (10,0 exactement ne suffit pas) : story 7."""
    bench = {"petit:1b": BenchScore(0.9, 10.0), "gros:8b": BenchScore(0.8, 5.0)}
    ranked = _rank([PETIT, MOYEN, GROS], 8.0)

    judge = md.choose_judge(ranked, bench)
    assert judge.reason == md.JUDGE_BY_FOOTPRINT and judge.choice.tag == "gros:8b"
    # Même règle quand rien ne tient : la raison le dit.
    assert md.choose_judge(_rank([PETIT], 1.0), bench).reason == md.JUDGE_NONE_FITS


def test_benchmark_judge_only_among_installed_local_models():
    """Un modèle mesuré mais non installé, ou un cloud, n'est jamais le juge du benchmark."""
    bench = {
        "absent:9b": BenchScore(1.0, 90.0),
        "mistral-large-2512": BenchScore(1.0, 90.0),
        "moyen:3.8b": BenchScore(0.5, 50.0),
        "gros:8b": BenchScore(0.6, 20.0),
    }
    ranked = _rank([PETIT, MOYEN, GROS, CLOUD], 8.0)
    assert md.default_judge(ranked, bench).tag == "gros:8b"


def test_benchmark_ties_broken_by_speed_then_tag():
    bench = {"gros:8b": BenchScore(0.9, 20.0), "moe:30b-a3b": BenchScore(0.9, 40.0)}
    catalog = {**CATALOG, "MoE 30B-A3B": {**CATALOG["MoE 30B-A3B"], "params_act": "5B"}}
    ranked = _rank([GROS, _local("moe:30b-a3b")], 64.0, catalog=catalog)
    assert md.default_judge(ranked, bench).tag == "moe:30b-a3b"

    bench = {"b:8b": BenchScore(0.9, 20.0), "a:8b": BenchScore(0.9, 20.0)}
    models = [_local(t, 4 * GB, "8B") for t in ("b:8b", "a:8b")]
    ranked = md.rank_models(models, 64.0, catalog={}, models_db={})
    assert md.default_judge(ranked, bench).tag == "a:8b"


def test_benchmark_matches_latest_variant():
    bench = {"LiquidAI/lfm2.5-2.6b": BenchScore(0.94, 122.0)}
    model = _local("LiquidAI/lfm2.5-2.6b:latest", 2 * GB, "2.7B")
    ranked = md.rank_models([model, PETIT], 16.0, catalog=CATALOG, models_db={})
    assert md.default_judge(ranked, bench).tag == "LiquidAI/lfm2.5-2.6b:latest"


def test_default_model_is_never_a_dedicated_reasoning_model():
    """`lfm2.5-thinking:1.2b`, le plus rapide : premier proposé = Granite 4.0 350M ; Arène :
    Granite 4.0 350M, Gemma 3 1B, Qwen 3.5 0.8B ; LFM Thinking reste sélectionnable."""
    ranked = _rtx()

    assert md.default_model(ranked).tag == "granite4:350m"
    judge = md.default_judge(ranked, RTX_BENCH)
    assert md.arena_preselection(ranked, judge) == ["granite4:350m", "gemma3:1b", "qwen3.5:0.8b"]
    lfm = next(c for c in ranked if c.tag == "lfm2.5-thinking:1.2b")
    assert lfm.dedicated_reasoning and lfm.fits
    # Après tous les autres locaux qui tiennent.
    assert [c.tag for c in ranked if c.fits][-1] == "lfm2.5-thinking:1.2b"


def test_hybrid_thinking_models_stay_candidates():
    """Hybrides (capacité `thinking` du catalogue, Qwen 3.5, Gemma 4) : pas écartés."""
    ranked = _rtx()
    hybrids = [c for c in ranked if "thinking" in RTX_CATALOG_BY_TAG[c.tag]["capabilities"]]
    assert hybrids and not any(c.dedicated_reasoning for c in hybrids)


@pytest.mark.parametrize(
    ("tag", "name", "expected"),
    [
        ("lfm2.5-thinking:1.2b", None, True),
        ("mon-modele:1b", "Phi 4 Mini Reasoning", True),
        ("phi4-mini-reasoning:3.8b", None, True),
        ("qwen3.5:4b", "Qwen 3.5 4B", False),
        ("granite4:350m", "Granite 4.0 350M", False),
    ],
)
def test_dedicated_reasoning_detection(tag, name, expected):
    assert md.is_dedicated_reasoning(tag, name) is expected


def test_dedicated_reasoning_by_catalog_or_display_name():
    """Reconnu au nom du catalogue ou au nom affiché, même si le tag ne le dit pas."""
    catalog = {"Phi 4 Mini Reasoning": {"ollama_tag": "phi4-mr:3.8b", "measured_loaded_gb": 0.5}}
    ranked = _rank([_local("phi4-mr:3.8b"), PETIT], 8.0, catalog={**CATALOG, **catalog})
    assert _tags(ranked)[0] == "petit:1b"

    names = {"x:1b": "X Thinking"}
    models = [_local("x:1b", GB // 4), _local("y:1b", GB)]
    ranked = md.rank_models(models, 8.0, catalog={}, models_db={}, names=names)
    assert _tags(ranked) == ["y:1b", "x:1b"]


def test_reasoning_model_never_first_even_if_only_one_to_fit():
    """Seul modèle qui tient : le local non dédié au raisonnement passe quand même devant,
    même s'il ne tient pas ; le modèle de raisonnement n'est jamais présélectionné."""
    thinking = _local("lfm2.5-thinking:1.2b", GB // 2)
    ranked = md.rank_models([thinking, GROS], 3.0, catalog=CATALOG, models_db={})

    assert not next(c for c in ranked if c.tag == "gros:8b").fits
    assert md.default_model(ranked).tag == "gros:8b"
    assert _tags(ranked) == ["gros:8b", "lfm2.5-thinking:1.2b"]
    assert md.arena_preselection(ranked, md.default_judge(ranked)) == []
    # Seul local : il reste proposé (aucun autre choix).
    only = md.rank_models([thinking, CLOUD], 3.0, catalog=CATALOG, models_db={})
    assert md.default_model(only).tag == "lfm2.5-thinking:1.2b"


def test_benchmark_judge_prefers_a_model_that_fits():
    """Mémoire serrée : le plus précis des rapides ne tient pas, un autre tient ; le juge
    est celui qui tient."""
    bench = {"gros:8b": BenchScore(0.95, 40.0), "moe:30b-a3b": BenchScore(0.80, 60.0)}
    moe = {**CATALOG["MoE 30B-A3B"], "params_act": "5B", "measured_loaded_gb": 2.0}
    catalog = {**CATALOG, "MoE 30B-A3B": moe}
    ranked = _rank([GROS, _local("moe:30b-a3b")], 4.0, catalog=catalog)

    assert not next(c for c in ranked if c.tag == "gros:8b").fits
    judge = md.choose_judge(ranked, bench)
    assert judge.choice.tag == "moe:30b-a3b" and judge.choice.fits
    assert judge.reason == md.JUDGE_BY_BENCHMARK
    # Un juge faible qui tient passe devant un juge fiable qui ne tient pas.
    weak = {"petit:1b": BenchScore(0.5, 90.0), "gros:8b": BenchScore(0.95, 40.0)}
    ranked = _rank([GROS, PETIT], 4.0)
    assert md.default_judge(ranked, weak).tag == "petit:1b"
    # Rien ne tient : le plus précis des fiables.
    ranked = _rank([GROS, PETIT], 1.0)
    assert md.default_judge(ranked, weak).tag == "gros:8b"


# ---------------------------------------------------------------------------
# Story 18 : modèle proposé par défaut sur la page Agents, d'après le benchmark du poste
# ---------------------------------------------------------------------------

# Taux de réussite des outils de poste-rtx3060 (`tool_capability.success_rate`).
RTX_TOOLS = {"granite4:350m": 0.75, "gemma3:1b": 0.0}
RTX_AGENT_BENCH = {
    tag: BenchScore(p, s, tool_success=RTX_TOOLS.get(tag, 1.0))
    for tag, _, _, p, s in RTX_MODELS.values()
}


def test_agent_default_on_benchmarked_machine_is_gemma_4_e4b():
    """poste-rtx3060 : le plus précis des ≥ 3B aux outils vérifiés, à plus de 10 tokens/s
    et qui tient : Gemma 4 E4B (QAT) (0,93), aussi juge de l'Arène ; pas Granite 4.0 350M
    (premier de l'ordre actuel), ni LFM 2.5 2.6B (0,94 mais < 3B), ni Gemma 4 12B (0,94 à
    6,6 tokens/s)."""
    ranked = _rtx()

    assert md.default_model(ranked).tag == "granite4:350m"
    assert md.agent_default(ranked, RTX_AGENT_BENCH).tag == "gemma4:e4b-it-qat"


def test_agent_default_without_benchmark_is_none():
    ranked = _rtx()
    assert md.agent_default(ranked, None) is None
    assert md.agent_default(ranked, {}) is None


@pytest.mark.parametrize(
    ("score", "available_gb", "why"),
    [
        (BenchScore(0.93, 68.75, tool_success=0.5), 16.7, "outils sous 0,75"),
        (BenchScore(0.93, 68.75, tool_success=None), 16.7, "outils inconnus"),
        (BenchScore(0.93, 10.0, tool_success=1.0), 16.7, "10 tokens/s, pas plus"),
        (BenchScore(0.93, 68.75, tool_success=1.0), 2.0, "ne tient pas en mémoire"),
    ],
)
def test_agent_default_criteria(score, available_gb, why):
    """Un seul modèle ≥ 3B, qui manque un critère : aucun candidat (ordre actuel)."""
    ranked = _rtx([_local("gemma4:e4b-it-qat"), _local("gemma3:1b")], available_gb)
    bench = {"gemma4:e4b-it-qat": score, "gemma3:1b": BenchScore(0.59, 185.98, 1.0)}

    assert md.agent_default(ranked, bench) is None, why


def test_agent_default_threshold_is_inclusive():
    """`success_rate` = 0,75 (seuil de `tools_validated`) : candidat."""
    ranked = _rtx([_local("gemma4:e4b-it-qat")])
    bench = {"gemma4:e4b-it-qat": BenchScore(0.93, 68.75, tool_success=0.75)}
    assert md.agent_default(ranked, bench).tag == "gemma4:e4b-it-qat"


def test_agent_default_params_threshold_is_inclusive():
    """Exactement 3B paramètres actifs (`AGENT_MIN_PARAMS_B`) : candidat."""
    catalog = {
        "Trois": {**RTX_CATALOG["Qwen 3.5 4B"], "ollama_tag": "trois:3b", "params_act": "3B"}
    }
    ranked = _rank([_local("trois:3b")], 16.7, catalog=catalog, models_db={})
    assert ranked[0].params_b == 3.0 and ranked[0].fits
    bench = {"trois:3b": BenchScore(0.9, 50.0, tool_success=1.0)}
    assert md.agent_default(ranked, bench).tag == "trois:3b"


def test_agent_default_excludes_small_reasoning_and_cloud_models():
    """Moins de 3B paramètres actifs, dédié au raisonnement, cloud ou paramètres inconnus :
    jamais candidat, même plus précis et plus rapide."""
    catalog = {
        **RTX_CATALOG,
        "Big Thinking": {**RTX_CATALOG["Qwen 3.5 4B"], "ollama_tag": "big-thinking:8b"},
    }
    models = [
        _local("LiquidAI/lfm2.5-2.6b"),
        _local("big-thinking:8b"),
        _local("mystery:7b", size_bytes=4 * GB),
        CLAUDE,
    ]
    ranked = _rank(models, 16.7, catalog=catalog, models_db={})
    best = BenchScore(0.99, 200.0, tool_success=1.0)
    bench = {
        "LiquidAI/lfm2.5-2.6b": best,
        "big-thinking:8b": best,
        "mystery:7b": best,
        "claude-sonnet-4-20250514": best,
    }
    assert md.agent_default(ranked, bench) is None


def test_agent_default_ties_broken_by_speed_then_tag():
    ranked = _rtx([_local("qwen3.5:4b"), _local("nemotron-3-nano:4b")])
    same = {
        "qwen3.5:4b": BenchScore(0.9, 50.0, 1.0),
        "nemotron-3-nano:4b": BenchScore(0.9, 80.0, 1.0),
    }
    assert md.agent_default(ranked, same).tag == "nemotron-3-nano:4b"
    same["nemotron-3-nano:4b"] = BenchScore(0.9, 50.0, 1.0)
    assert md.agent_default(ranked, same).tag == "nemotron-3-nano:4b"  # tag, ordre alphabétique


# ---------------------------------------------------------------------------
# Story 25 : « le plus rapide » d'après le benchmark de ce poste, outils vérifiés
# ---------------------------------------------------------------------------


def test_benchmark_speed_beats_models_json_when_it_measures_all_fitting():
    """Benchmark complet, contraire à data/models.json : le tri suit le débit du benchmark,
    et chaque local porte ce débit."""
    models_db = _speeds(**{"petit:1b": 90, "moyen:3.8b": 40, "gros:8b": 20})
    bench = {
        "petit:1b": BenchScore(0.5, 30.0),
        "moyen:3.8b": BenchScore(0.6, 80.0),
        "gros:8b": BenchScore(0.7, 50.0),
    }
    ranked = _rank([PETIT, MOYEN, GROS], 16.0, models_db=models_db, benchmark=bench)

    assert _tags(ranked) == ["moyen:3.8b", "gros:8b", "petit:1b"]
    assert [c.speed_tps for c in ranked] == [80.0, 50.0, 30.0]
    assert md.default_model(ranked).tag == "moyen:3.8b"
    # Sans benchmark : data/models.json.
    assert _tags(_rank([PETIT, MOYEN, GROS], 16.0, models_db=models_db)) == [
        "petit:1b",
        "moyen:3.8b",
        "gros:8b",
    ]


def test_partial_benchmark_keeps_current_rule():
    """Un local qui tient n'est pas mesuré : jamais de mélange des sources ; data/models.json
    s'il donne un débit pour chacun, sinon la plus petite empreinte."""
    bench = {"moyen:3.8b": BenchScore(0.6, 500.0), "gros:8b": BenchScore(0.7, 400.0)}

    models_db = _speeds(**{"petit:1b": 40, "moyen:3.8b": 60, "gros:8b": 20})
    ranked = _rank([PETIT, MOYEN, GROS], 16.0, models_db=models_db, benchmark=bench)
    assert _tags(ranked) == ["moyen:3.8b", "petit:1b", "gros:8b"]
    assert ranked[0].speed_tps == 60.0  # débit de data/models.json, pas du benchmark

    ranked = _rank([GROS, MOYEN, PETIT], 16.0, benchmark=bench)
    assert _tags(ranked) == ["petit:1b", "moyen:3.8b", "gros:8b"]
    assert all(c.speed_tps is None for c in ranked)


@pytest.mark.parametrize("bench", [None, {}])
def test_empty_benchmark_keeps_current_order(bench):
    """Poste inconnu : ordre identique à celui d'avant (data/models.json, puis empreinte)."""
    models_db = _speeds(**{"petit:1b": 40, "moyen:3.8b": 60, "gros:8b": 20})
    for db in (models_db, {}):
        with_bench = _rank([CLOUD, GROS, MOYEN, PETIT], 16.0, models_db=db, benchmark=bench)
        assert with_bench == _rank([CLOUD, GROS, MOYEN, PETIT], 16.0, models_db=db)


def test_unmeasured_local_that_does_not_fit_does_not_block_benchmark():
    """Un local trop gros, hors benchmark, n'empêche pas le tri sur le benchmark et reste
    après ceux qui tiennent, sans débit."""
    bench = {"petit:1b": BenchScore(0.5, 30.0), "moyen:3.8b": BenchScore(0.6, 80.0)}
    ranked = _rank([PETIT, GROS, MOYEN, CLOUD], 4.0, benchmark=bench)

    assert _tags(ranked) == ["moyen:3.8b", "petit:1b", "gros:8b", "mistral-large-2512"]
    gros = next(c for c in ranked if c.tag == "gros:8b")
    assert not gros.fits and gros.speed_tps is None


def test_benchmark_covers_reasoning_models_too():
    """La couverture compte les modèles dédiés au raisonnement qui tiennent : s'il en manque
    un, règle actuelle ; mesuré, il reste après les autres malgré son débit."""
    thinking = _local("lfm2.5-thinking:1.2b", GB // 2)
    bench = {"petit:1b": BenchScore(0.5, 30.0), "moyen:3.8b": BenchScore(0.6, 80.0)}
    ranked = _rank([PETIT, MOYEN, thinking], 16.0, benchmark=bench)
    assert _tags(ranked) == ["petit:1b", "moyen:3.8b", "lfm2.5-thinking:1.2b"]

    bench["lfm2.5-thinking:1.2b"] = BenchScore(0.7, 300.0)
    ranked = _rank([PETIT, MOYEN, thinking], 16.0, benchmark=bench)
    assert _tags(ranked) == ["moyen:3.8b", "petit:1b", "lfm2.5-thinking:1.2b"]


def test_benchmark_speed_matches_latest_variant():
    """Un tag installé avec la variante `:latest` est reconnu dans le benchmark (tag de
    base)."""
    catalog = {**CATALOG, "Petit 1B": {**CATALOG["Petit 1B"], "ollama_tag": "petit"}}
    bench = {"petit": BenchScore(0.5, 20.0), "moyen:3.8b": BenchScore(0.6, 80.0)}
    ranked = _rank([_local("petit:latest"), MOYEN], 16.0, catalog=catalog, benchmark=bench)

    assert _tags(ranked) == ["moyen:3.8b", "petit:latest"]
    assert ranked[1].speed_tps == 20.0


def test_arena_preselection_follows_benchmark_order():
    """poste-rtx3060, data/models.json à rebours du benchmark : premier proposé et Arène
    suivent le benchmark (Granite 4.0 350M, Gemma 3 1B, Qwen 3.5 0.8B)."""
    inverted = _speeds(**{tag: 1000.0 / s for tag, _, _, _, s in RTX_MODELS.values()})
    without = _rank(RTX_INSTALLED, 16.7, catalog=RTX_CATALOG, models_db=inverted)
    ranked = _rank(
        RTX_INSTALLED, 16.7, catalog=RTX_CATALOG, models_db=inverted, benchmark=RTX_BENCH
    )

    assert md.default_model(ranked).tag == "granite4:350m"
    judge = md.default_judge(ranked, RTX_BENCH)
    assert judge.tag == "gemma4:e4b-it-qat"
    assert md.arena_preselection(ranked, judge) == ["granite4:350m", "gemma3:1b", "qwen3.5:0.8b"]
    # Sans benchmark : data/models.json inversé, les plus lents du benchmark en tête.
    assert md.default_model(without).tag == "granite4.2:8b"
    assert md.arena_preselection(without, md.default_judge(without, RTX_BENCH)) == [
        "granite4.2:8b",
        "gemma4-ud:12b-iq3_xxs",
        "qwen3.5-ud:9b-q3_k_xl",
    ]


@pytest.mark.parametrize(
    ("tag", "capabilities", "bench", "expected"),
    [
        ("a:1b", ["chat"], {"a:1b": BenchScore(0.5, 50.0, tool_success=0.75)}, True),
        ("a:1b", ["chat"], {"a:1b": BenchScore(0.5, 50.0, tool_success=0.74)}, False),
        ("a:1b", ["chat", "tools"], {"a:1b": BenchScore(0.5, 50.0, tool_success=0.0)}, False),
        ("a:1b", ["chat", "tools"], {"a:1b": BenchScore(0.5, 50.0, tool_success=None)}, True),
        ("a:1b", ["chat"], {"a:1b": BenchScore(0.5, 50.0, tool_success=None)}, False),
        ("a:1b", ["chat", "tools"], {"b:1b": BenchScore(0.5, 50.0, tool_success=0.0)}, True),
        ("a:1b", ["chat"], {"b:1b": BenchScore(0.5, 50.0, tool_success=1.0)}, False),
        ("a:1b", ["chat", "tools"], None, True),
        ("a:1b", None, {}, False),
        ("a:latest", ["chat", "tools"], {"a": BenchScore(0.5, 50.0, tool_success=0.0)}, False),
        ("a:latest", [], {"a": BenchScore(0.5, 50.0, tool_success=1.0)}, True),
    ],
    ids=[
        "seuil-inclusif",
        "sous-le-seuil",
        "zero-malgre-catalogue",
        "none-catalogue-tools",
        "none-catalogue-sans-tools",
        "absent-catalogue-tools",
        "absent-catalogue-sans-tools",
        "sans-benchmark",
        "rien",
        "latest-zero",
        "latest-un",
    ],
)
def test_tools_verified(tag, capabilities, bench, expected):
    """Benchmark de ce poste quand il a mesuré les outils du modèle, catalogue sinon."""
    assert md.tools_verified(tag, capabilities, bench) is expected
