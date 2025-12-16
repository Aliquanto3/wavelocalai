"""
Tests unitaires pour le module EvalEngine.
Usage: pytest tests/unit/test_eval_engine.py -v
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestEvalEngine:

    @pytest.fixture
    def mock_env(self):
        """Simule l'environnement avec ragas installé."""
        mock_ragas = MagicMock()
        mock_datasets = MagicMock()

        # On patche sys.modules pour simuler la présence des libs
        with patch.dict(
            sys.modules,
            {"ragas": mock_ragas, "ragas.metrics": MagicMock(), "datasets": mock_datasets},
        ):
            yield

    @pytest.fixture
    def mock_dependencies(self, mock_env):
        """Mock les dépendances internes."""
        # ✅ CORRECTION : On ne patche plus HuggingFaceEmbeddings car il n'est plus importé dans eval_engine.py
        with (
            patch("src.core.eval_engine.evaluate") as mock_evaluate,
            patch("src.core.eval_engine.LLMProvider") as mock_provider,
        ):
            # Setup Provider (Juge)
            mock_judge = MagicMock()
            mock_provider.get_langchain_model.return_value = mock_judge

            # On force RAGAS_AVAILABLE à True
            with patch("src.core.eval_engine.RAGAS_AVAILABLE", True):
                from src.core.eval_engine import EvalEngine, EvalResult

                yield {
                    "evaluate": mock_evaluate,
                    "provider": mock_provider,
                    "judge": mock_judge,
                    "engine_cls": EvalEngine,
                    "result_cls": EvalResult,
                }

    def test_init_success(self, mock_dependencies):
        """Test l'initialisation réussie."""
        eval_engine_cls = mock_dependencies["engine_cls"]
        engine = eval_engine_cls()
        assert engine is not None

    def test_evaluate_single_turn_flow(self, mock_dependencies):
        """Vérifie le flux complet d'une évaluation."""
        mock_results = MagicMock()
        mock_df = MagicMock()
        mock_df.iloc.__getitem__.return_value = {"answer_relevancy": 0.85, "faithfulness": 0.90}
        mock_results.to_pandas.return_value = mock_df
        mock_dependencies["evaluate"].return_value = mock_results

        eval_engine_cls = mock_dependencies["engine_cls"]
        engine = eval_engine_cls()

        # ✅ CORRECTION : On passe un mock pour embedding_model
        mock_embedding_model = MagicMock()

        result = engine.evaluate_single_turn(
            query="What is WaveLocalAI?",
            response="It is a local AI tool.",
            retrieved_contexts=["Context 1"],
            judge_tag="mistral-large-latest",
            embedding_model=mock_embedding_model,
        )

        mock_dependencies["provider"].get_langchain_model.assert_called_with(
            "mistral-large-latest",
            temperature=0.0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        mock_dependencies["evaluate"].assert_called_once()
        assert result.faithfulness == 0.90
        assert result.answer_relevancy == 0.85

    def test_evaluate_handles_ragas_exception(self, mock_dependencies):
        """Vérifie que le moteur est robuste aux erreurs Ragas."""
        mock_dependencies["evaluate"].side_effect = Exception("Ragas failure")
        eval_engine_cls = mock_dependencies["engine_cls"]
        engine = eval_engine_cls()

        # Le moteur attrape l'exception et renvoie des scores à 0.0
        result = engine.evaluate_single_turn(
            query="Q",
            response="A",
            retrieved_contexts=["C"],
            judge_tag="model",
            embedding_model=MagicMock(),
        )

        assert result.global_score == 0.0
