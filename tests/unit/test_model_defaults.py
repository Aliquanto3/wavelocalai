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
