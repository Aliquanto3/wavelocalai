"""Télémétries coupées au démarrage de l'app (src/core/telemetry.py)."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.core.telemetry import TELEMETRY_OPT_OUTS, disable_telemetry

ROOT = Path(__file__).resolve().parents[2]


def test_disable_telemetry_sets_missing_and_keeps_existing(monkeypatch, tmp_path):
    for name in TELEMETRY_OPT_OUTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANONYMIZED_TELEMETRY", "True")  # choix explicite conservé
    # Réactivation volontaire par le .env : lu avant, jamais écrasé.
    dotenv = tmp_path / ".env"
    dotenv.write_text("LANGSMITH_TRACING=true\n", encoding="utf-8")

    disable_telemetry(dotenv)

    assert os.environ["RAGAS_DO_NOT_TRACK"] == "true"
    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true"
    assert os.environ["CREWAI_DISABLE_VERSION_CHECK"] == "true"  # pas d'appel à pypi.org
    assert os.environ["ANONYMIZED_TELEMETRY"] == "True"
    assert os.environ["LANGSMITH_TRACING"] == "true"


def test_crewai_version_check_keeps_existing_value(monkeypatch, tmp_path):
    for name in TELEMETRY_OPT_OUTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CREWAI_DISABLE_VERSION_CHECK", "false")  # choix explicite conservé
    disable_telemetry(tmp_path / "absent.env")
    assert os.environ["CREWAI_DISABLE_VERSION_CHECK"] == "false"


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in TELEMETRY_OPT_OUTS}


def test_ragas_does_not_track_after_eval_engine_import():
    """Constat du 27/09 : sans RAGAS_DO_NOT_TRACK, l'évaluation résolvait
    t.explodinggradients.com. L'import d'eval_engine suffit à couper Ragas."""
    pytest.importorskip("ragas")
    code = (
        "import src.core.eval_engine\n"
        "from ragas._analytics import do_not_track\n"
        "assert do_not_track(), 'Ragas suit toujours'\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, env=_clean_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_chroma_settings_without_telemetry():
    code = (
        "from src.core.telemetry import disable_telemetry\n"
        "disable_telemetry()\n"
        "from chromadb.config import Settings\n"
        "assert Settings().anonymized_telemetry is False\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], cwd=ROOT, env=_clean_env(), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr[-2000:]


def test_app_disables_telemetry_before_importing_src():
    """Accueil.py appelle disable_telemetry() avant tout autre import de src."""
    tree = ast.parse((ROOT / "src" / "app" / "Accueil.py").read_text(encoding="utf-8"))
    call_line = next(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and getattr(node.value.func, "id", None) == "disable_telemetry"
    )
    src_imports = [
        node.lineno
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("src.")
            and node.module != "src.core.telemetry"
        )
        or (isinstance(node, ast.Import) and any(a.name.startswith("src.") for a in node.names))
    ]
    assert src_imports and call_line < min(src_imports)


def test_e2e_env_does_not_mask_app_opt_outs():
    """La garde réseau e2e vérifie l'app elle-même : l'environnement de test ne coupe pas à
    sa place les télémétries que l'app doit couper."""
    from tests.e2e.conftest import APP_ENV

    assert not set(APP_ENV) & set(TELEMETRY_OPT_OUTS)


# --- Story 26 : imports directs, hors de l'app -------------------------------------------

# Racines des bibliothèques à télémétrie (ou qui en chargent une : langchain_community charge
# huggingface_hub). Tout fichier de src/ ou scripts/ qui en importe une figure ci-dessous.
TELEMETRY_ROOTS = frozenset(
    {
        "crewai",
        "chromadb",
        "langchain_chroma",
        "ragas",
        "huggingface_hub",
        "sentence_transformers",
        "langchain_huggingface",
        "transformers",
        "langchain_community",
    }
)

# Module → bibliothèques à télémétrie qu'il importe ; disable_telemetry() doit précéder la
# première de ces importations. Un module importé seulement après un module déjà protégé
# pourrait en être dispensé : il serait alors signalé ici par un commentaire (aucun à ce jour).
TELEMETRY_IMPORTERS: dict[str, tuple[str, ...]] = {
    "src/core/eval_engine.py": ("ragas", "datasets"),
    "src/core/crew_engine.py": ("crewai",),
    "src/core/rag/vector_store.py": ("langchain_chroma", "chromadb"),
    "src/core/rag/models_factory.py": (
        "langchain_huggingface",
        "sentence_transformers",
        "huggingface_hub",
        "transformers",
    ),
    "src/core/rag/ingestion.py": ("langchain_community",),
    "scripts/setup_rag_models.py": ("huggingface_hub",),
}


def _run(code: str, cwd: Path, env: dict[str, str] | None = None):
    """`python -c` hors du dépôt : find_dotenv part alors du répertoire courant, et le .env
    réel du développeur n'est pas lu. src reste importable par PYTHONPATH."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=cwd,
        env={**(env if env is not None else _clean_env()), "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


def test_crewai_opt_outs_set_before_crewai_import(tmp_path):
    """Un script qui importe crew_engine directement : les variables sont posées avant que
    crewai ne soit importé (relevé au moment de son import par un chercheur de modules)."""
    pytest.importorskip("crewai")
    code = (
        "import os, sys\n"
        "seen = {}\n"
        "class Spy:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'crewai' and not seen:\n"
        "            seen.update({k: os.environ.get(k) for k in (\n"
        "                'CREWAI_DISABLE_TELEMETRY', 'OTEL_SDK_DISABLED',\n"
        "                'CREWAI_DISABLE_VERSION_CHECK')})\n"
        "        return None\n"
        "sys.meta_path.insert(0, Spy())\n"
        "import src.core.crew_engine\n"
        "assert seen == {'CREWAI_DISABLE_TELEMETRY': 'true', 'OTEL_SDK_DISABLED': 'true',\n"
        "                'CREWAI_DISABLE_VERSION_CHECK': 'true'}, seen\n"
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stderr[-2000:]


def test_chroma_telemetry_off_after_vector_store_import(tmp_path):
    pytest.importorskip("chromadb")
    code = (
        "import src.core.rag.vector_store\n"
        "from chromadb.config import Settings\n"
        "assert Settings().anonymized_telemetry is False\n"
    )
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stderr[-2000:]


# Hugging Face : DO_NOT_TRACK=1 suffirait à la constante ; la variable propre est vérifiée aussi.
HF_OFF_ASSERTS = (
    "import os\n"
    "from huggingface_hub import constants\n"
    "value = os.environ.get('HF_HUB_DISABLE_TELEMETRY')\n"
    "assert value == '1', value\n"
    "assert constants.HF_HUB_DISABLE_TELEMETRY is True\n"
)


@pytest.mark.parametrize("module", ["src.core.rag.models_factory", "src.core.rag_engine"])
def test_hf_telemetry_off_after_direct_import(module, tmp_path):
    """models_factory, et rag_engine, dont ingestion.py charge huggingface_hub (par
    langchain_community) avant models_factory."""
    pytest.importorskip("huggingface_hub")
    result = _run(f"import {module}\n" + HF_OFF_ASSERTS, tmp_path)
    assert result.returncode == 0, result.stderr[-2000:]


def test_setup_rag_models_disables_hf_telemetry(tmp_path):
    """Script chargé depuis un autre dossier : il coupe Hugging Face avant d'importer
    huggingface_hub, sans rien télécharger à l'import."""
    pytest.importorskip("huggingface_hub")
    script = ROOT / "scripts" / "setup_rag_models.py"
    code = (
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('setup_rag_models', {str(script)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
    ) + HF_OFF_ASSERTS
    result = _run(code, tmp_path)
    assert result.returncode == 0, result.stderr[-2000:]


def test_setup_rag_models_help_runs_without_opt_outs(tmp_path):
    """Critère d'acceptation : `python scripts/setup_rag_models.py --help` sans opt-out, lancé
    hors du dépôt (le script trouve src seul, sans PYTHONPATH)."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "setup_rag_models.py"), "--help"],
        cwd=tmp_path,
        env=_clean_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "--embeddings" in result.stdout


def test_explicit_reactivation_kept_on_direct_import(tmp_path):
    """Réactivation volontaire de Hugging Face (sa variable et DO_NOT_TRACK, qu'il lit aussi) :
    l'import ne l'écrase pas, et la télémétrie est réellement active."""
    pytest.importorskip("huggingface_hub")
    code = (
        "import os\n"
        "import src.core.rag.models_factory\n"
        "from huggingface_hub import constants\n"
        "assert os.environ['HF_HUB_DISABLE_TELEMETRY'] == '0'\n"
        "assert constants.HF_HUB_DISABLE_TELEMETRY is False\n"
    )
    env = {**_clean_env(), "HF_HUB_DISABLE_TELEMETRY": "0", "DO_NOT_TRACK": "0"}
    result = _run(code, tmp_path, env)
    assert result.returncode == 0, result.stderr[-2000:]


def _module_level_call_line(tree: ast.Module) -> int | None:
    return next(
        (
            node.lineno
            for node in tree.body
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "disable_telemetry"
        ),
        None,
    )


def _imported_roots(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def test_every_telemetry_importer_is_listed():
    """Découverte : un module nouveau ou oublié qui importe une bibliothèque à télémétrie fait
    échouer la suite tant qu'il n'est pas protégé et listé dans TELEMETRY_IMPORTERS."""
    files = sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")])
    importers = {
        path.relative_to(ROOT).as_posix()
        for path in files
        if any(
            TELEMETRY_ROOTS & set(_imported_roots(node))
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    }
    missing = sorted(importers - set(TELEMETRY_IMPORTERS))
    assert not missing, f"Modules à protéger par disable_telemetry() puis à lister : {missing}"


@pytest.mark.parametrize("relpath", sorted(TELEMETRY_IMPORTERS))
def test_disable_telemetry_precedes_library_import(relpath):
    """Dans chaque module, l'appel précède la première importation de la bibliothèque (y
    compris dans un try ou une fonction)."""
    tree = ast.parse((ROOT / relpath).read_text(encoding="utf-8"))
    libraries = set(TELEMETRY_IMPORTERS[relpath])
    library_lines = [
        node.lineno for node in ast.walk(tree) if libraries & set(_imported_roots(node))
    ]
    call_line = _module_level_call_line(tree)
    assert library_lines, f"{relpath} n'importe plus {libraries} : mettre à jour la liste"
    assert call_line is not None, f"{relpath} n'appelle pas disable_telemetry()"
    assert call_line < min(library_lines)


def test_readme_documents_every_opt_out():
    """La documentation reprend TELEMETRY_OPT_OUTS, sans en oublier (nom exact entre accents
    graves : DO_NOT_TRACK ne compte pas dans RAGAS_DO_NOT_TRACK)."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [name for name in TELEMETRY_OPT_OUTS if f"`{name}`" not in readme]
    assert not missing, f"Variables absentes de README.md : {missing}"
    assert "`gatherUsageStats" in readme
