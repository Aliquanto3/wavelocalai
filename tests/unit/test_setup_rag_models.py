"""scripts/setup_rag_models.py : téléchargement simulé, écritures dans tmp_path (story 26)."""

import importlib.util
from pathlib import Path
from unittest.mock import create_autospec

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def setup_rag_models():
    spec = importlib.util.spec_from_file_location(
        "setup_rag_models", ROOT / "scripts" / "setup_rag_models.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def snapshot(monkeypatch, setup_rag_models):
    """snapshot_download simulé avec sa vraie signature (un paramètre inconnu lève TypeError,
    comme la bibliothèque) : écrit un fichier dans le dossier cible, sans réseau."""
    from huggingface_hub import snapshot_download

    def fake_download(repo_id, *, local_dir=None, **kwargs):
        path = Path(local_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "config.json").write_text("{}", encoding="utf-8")
        return str(path)

    mock = create_autospec(snapshot_download, side_effect=fake_download)
    monkeypatch.setattr(setup_rag_models, "snapshot_download", mock)
    return mock


def test_download_model_calls_snapshot_with_repo(setup_rag_models, snapshot, tmp_path):
    target = tmp_path / "embeddings" / "all-MiniLM-L6-v2"

    setup_rag_models.download_model("sentence-transformers/all-MiniLM-L6-v2", target)

    snapshot.assert_called_once()
    kwargs = snapshot.call_args.kwargs
    assert kwargs["repo_id"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert kwargs["local_dir"] == str(target)
    assert (target / "config.json").exists()


def test_download_model_skips_present_model(setup_rag_models, snapshot, tmp_path):
    target = tmp_path / "rerankers" / "bge-reranker-base"

    setup_rag_models.download_model("BAAI/bge-reranker-base", target)
    setup_rag_models.download_model("BAAI/bge-reranker-base", target)

    snapshot.assert_called_once()
