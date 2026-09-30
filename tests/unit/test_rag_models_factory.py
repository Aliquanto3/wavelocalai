"""Chargement des modèles RAG sans réseau d'abord (story 17) : Hugging Face simulé."""

from unittest.mock import MagicMock

import pytest

from src.core.rag import models_factory
from src.core.rag.models_factory import RAGModelsFactory


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    """`data/models` remplacé par un dossier temporaire (vide par défaut)."""
    monkeypatch.setattr(RAGModelsFactory, "EMBEDDINGS_PATH", tmp_path / "embeddings")
    monkeypatch.setattr(RAGModelsFactory, "RERANKERS_PATH", tmp_path / "rerankers")
    return tmp_path


@pytest.fixture
def embeddings_cls(monkeypatch):
    cls = MagicMock(name="HuggingFaceEmbeddings")
    monkeypatch.setattr(models_factory, "HuggingFaceEmbeddings", cls)
    return cls


@pytest.fixture
def cross_encoder_cls(monkeypatch):
    cls = MagicMock(name="CrossEncoder")
    monkeypatch.setattr(models_factory, "CrossEncoder", cls)
    return cls


def test_embedding_in_hf_cache_loaded_offline(models_dir, embeddings_cls):
    model = RAGModelsFactory.get_embedding_model("all-MiniLM-L6-v2")

    assert model is embeddings_cls.return_value
    embeddings_cls.assert_called_once()
    kwargs = embeddings_cls.call_args.kwargs
    assert kwargs["model_name"] == "all-MiniLM-L6-v2"
    assert kwargs["model_kwargs"] == {
        "device": "cpu",
        "trust_remote_code": True,
        "local_files_only": True,
    }
    assert kwargs["encode_kwargs"] == {"normalize_embeddings": True}


def test_embedding_absent_falls_back_to_download(models_dir, embeddings_cls):
    downloaded = MagicMock(name="downloaded")
    embeddings_cls.side_effect = [OSError("not in cache"), downloaded]

    model = RAGModelsFactory.get_embedding_model("all-MiniLM-L6-v2", device="cuda")

    assert model is downloaded
    first, second = embeddings_cls.call_args_list
    assert first.kwargs["model_kwargs"]["local_files_only"] is True
    assert second.kwargs["model_kwargs"] == {"device": "cuda", "trust_remote_code": True}


def test_embedding_other_error_not_retried(models_dir, embeddings_cls):
    embeddings_cls.side_effect = ValueError("configuration invalide")
    with pytest.raises(ValueError):
        RAGModelsFactory.get_embedding_model("all-MiniLM-L6-v2")
    assert embeddings_cls.call_count == 1


def test_embedding_in_data_models_loaded_by_path(models_dir, embeddings_cls):
    local = models_dir / "embeddings" / "all-MiniLM-L6-v2"
    local.mkdir(parents=True)

    RAGModelsFactory.get_embedding_model("all-MiniLM-L6-v2")

    kwargs = embeddings_cls.call_args.kwargs
    assert kwargs["model_name"] == str(local)
    assert kwargs["model_kwargs"]["local_files_only"] is True


def test_reranker_in_hf_cache_loaded_offline(models_dir, cross_encoder_cls):
    model = RAGModelsFactory.get_reranker_model("cross-encoder/ms-marco-MiniLM-L-6-v2")

    assert model is cross_encoder_cls.return_value
    cross_encoder_cls.assert_called_once_with(
        "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device="cpu",
        trust_remote_code=True,
        local_files_only=True,
    )


def test_reranker_absent_falls_back_to_download(models_dir, cross_encoder_cls):
    downloaded = MagicMock(name="downloaded")
    cross_encoder_cls.side_effect = [OSError("not in cache"), downloaded]

    model = RAGModelsFactory.get_reranker_model("cross-encoder/ms-marco-MiniLM-L-6-v2")

    assert model is downloaded
    first, second = cross_encoder_cls.call_args_list
    assert first.kwargs["local_files_only"] is True
    assert "local_files_only" not in second.kwargs
    assert second.kwargs == {"device": "cpu", "trust_remote_code": True}


def test_reranker_in_data_models_loaded_by_path(models_dir, cross_encoder_cls):
    local = models_dir / "rerankers" / "bge-reranker"
    local.mkdir(parents=True)

    RAGModelsFactory.get_reranker_model("bge-reranker")

    assert cross_encoder_cls.call_args.args == (str(local),)


def test_reranker_failure_after_fallback_returns_none(models_dir, cross_encoder_cls):
    cross_encoder_cls.side_effect = OSError("hors ligne")
    assert RAGModelsFactory.get_reranker_model("absent") is None
    assert cross_encoder_cls.call_count == 2


@pytest.mark.parametrize("loader", ["SentenceTransformer", "CrossEncoder"])
def test_real_loaders_raise_oserror_on_cache_miss_offline(loader, monkeypatch, tmp_path):
    """Contrat du repli : les vrais chargeurs acceptent `local_files_only` et lèvent OSError
    pour un modèle absent du cache. Aucune connexion possible (socket bloqué), cache vide."""
    import socket

    import sentence_transformers

    def no_network(*args, **kwargs):
        raise AssertionError("connexion réseau interdite dans ce test")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))

    cls = getattr(sentence_transformers, loader)
    with pytest.raises(OSError):
        cls("wavelocalai-test/absent-model", device="cpu", local_files_only=True)
