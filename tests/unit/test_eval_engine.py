"""
Tests unitaires pour le module EvalEngine.
Usage: pytest tests/unit/test_eval_engine.py -v
"""

import importlib
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
        # patch.object sur le module de sys.modules : sous Python 3.10, patch("src.core.eval_engine.x")
        # passe par l'attribut du paquet, périmé après le patch.dict(sys.modules) du test précédent.
        engine_module = importlib.import_module("src.core.eval_engine")
        with (
            patch.object(engine_module, "evaluate") as mock_evaluate,
            patch.object(engine_module, "LLMProvider") as mock_provider,
        ):
            # Setup Provider (Juge)
            mock_judge = MagicMock()
            mock_provider.get_langchain_model.return_value = mock_judge

            # On force RAGAS_AVAILABLE à True
            with patch.object(engine_module, "RAGAS_AVAILABLE", True):
                yield {
                    "evaluate": mock_evaluate,
                    "provider": mock_provider,
                    "judge": mock_judge,
                    "engine_cls": engine_module.EvalEngine,
                    "result_cls": engine_module.EvalResult,
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

        # Le moteur attrape l'exception : « non évalué » avec la raison, jamais 0.
        result = engine.evaluate_single_turn(
            query="Q",
            response="A",
            retrieved_contexts=["C"],
            judge_tag="model",
            embedding_model=MagicMock(),
        )

        assert result.global_score is None
        assert result.answer_relevancy is None
        assert result.faithfulness is None
        assert not result.evaluated
        # Raison courte pour le tableau, texte de l'exception à part (Détails techniques).
        assert result.reason == "l'évaluation par le juge a échoué."
        assert "Ragas failure" in result.detail

    def _run_with_scores(self, mock_dependencies, scores):
        mock_results = MagicMock()
        mock_df = MagicMock()
        mock_df.iloc.__getitem__.return_value = scores
        mock_results.to_pandas.return_value = mock_df
        mock_dependencies["evaluate"].return_value = mock_results
        engine = mock_dependencies["engine_cls"]()
        return engine.evaluate_single_turn(
            query="Q",
            response="A",
            retrieved_contexts=["C"],
            judge_tag="model",
            embedding_model=MagicMock(),
        )

    def test_evaluate_nan_scores_are_not_evaluated(self, mock_dependencies):
        """NaN (juge local qui échoue) : « non évalué », jamais converti en 0."""
        nan = float("nan")
        result = self._run_with_scores(
            mock_dependencies, {"answer_relevancy": nan, "faithfulness": nan}
        )
        assert result.global_score is None
        assert result.answer_relevancy is None and result.faithfulness is None
        assert result.reason

    def test_evaluate_missing_metric_is_not_evaluated(self, mock_dependencies):
        """Colonne absente : la métrique calculée est gardée, la note globale non évaluée."""
        result = self._run_with_scores(mock_dependencies, {"answer_relevancy": 0.8})
        assert result.answer_relevancy == 0.8
        assert result.faithfulness is None
        assert result.global_score is None
        assert "fidélité" in result.reason

    def test_evaluate_scores_zero_is_a_real_score(self, mock_dependencies):
        """Un vrai 0 calculé par Ragas reste une note (différente de « non évalué »)."""
        result = self._run_with_scores(
            mock_dependencies, {"answer_relevancy": 0.0, "faithfulness": 0.0}
        )
        assert result.global_score == 0.0
        assert result.evaluated
        assert result.reason is None

    def test_evaluate_judge_creation_failure(self, mock_dependencies):
        """Juge impossible à créer : « non évalué » avec la raison, sans exception."""
        mock_dependencies["provider"].get_langchain_model.side_effect = ValueError(
            "Provider non disponible"
        )
        engine = mock_dependencies["engine_cls"]()
        result = engine.evaluate_single_turn(
            query="Q",
            response="A",
            retrieved_contexts=["C"],
            judge_tag="model",
            embedding_model=MagicMock(),
        )
        assert result.global_score is None
        assert "Provider non disponible" in result.detail
        assert "Provider" not in result.reason
        mock_dependencies["evaluate"].assert_not_called()

    def test_evaluate_without_ragas(self):
        """Ragas absent : « non évalué » avec la raison."""
        engine_module = importlib.import_module("src.core.eval_engine")
        with patch.object(engine_module, "RAGAS_AVAILABLE", False):
            result = engine_module.EvalEngine().evaluate_single_turn(
                query="Q",
                response="A",
                retrieved_contexts=["C"],
                judge_tag="model",
                embedding_model=MagicMock(),
            )
        assert result.global_score is None
        assert not result.evaluated
        assert "Ragas" in result.reason
