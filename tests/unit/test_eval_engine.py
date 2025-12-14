"""
Tests unitaires pour le module EvalEngine.
Usage: pytest tests/unit/test_eval_engine.py -v
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Note : On ne patche plus sys.modules au niveau global ici !


class TestEvalEngine:

    @pytest.fixture
    def mock_env(self):
        """
        Fixture qui simule la présence de 'ragas' et 'datasets'
        UNIQUEMENT pendant la durée de ce test.
        À la fin du test, les vraies librairies sont restaurées.
        """
        mock_ragas = MagicMock()
        mock_datasets = MagicMock()

        # On patche sys.modules temporairement
        with patch.dict(
            sys.modules,
            {"ragas": mock_ragas, "ragas.metrics": MagicMock(), "datasets": mock_datasets},
        ):
            # On doit re-importer ou importer EvalEngine DANS ce contexte
            # pour qu'il voit les mocks.
            # Cependant, comme EvalEngine est déjà chargé par Python,
            # on va surtout mocker ses imports internes.

            # Pour ce test spécifique, on va surtout mocker les composants internes
            # via le patch ci-dessous.
            yield

    @pytest.fixture
    def mock_dependencies(self, mock_env):
        """Mock les dépendances internes de la classe EvalEngine"""
        # On patche là où la classe est définie
        with (
            patch("src.core.eval_engine.HuggingFaceEmbeddings") as mock_embed,
            patch("src.core.eval_engine.evaluate") as mock_evaluate,
            patch("src.core.eval_engine.LLMProvider") as mock_provider,
        ):

            # Setup Embeddings
            mock_embed.return_value = MagicMock()

            # Setup Provider (Juge)
            mock_judge = MagicMock()
            mock_provider.get_langchain_model.return_value = mock_judge

            # IMPORTANT : On force RAGAS_AVAILABLE à True pour tester la logique
            with patch("src.core.eval_engine.RAGAS_AVAILABLE", True):
                # On importe la classe ici pour être sûr
                from src.core.eval_engine import EvalEngine, EvalResult

                yield {
                    "embed": mock_embed,
                    "evaluate": mock_evaluate,
                    "provider": mock_provider,
                    "judge": mock_judge,
                    "engine_cls": EvalEngine,
                    "result_cls": EvalResult,
                }

    def test_init_success(self, mock_dependencies):
        """Test l'initialisation réussie"""
        eval_engine_cls = mock_dependencies["engine_cls"]
        engine = eval_engine_cls()
        assert engine.embeddings is not None
        mock_dependencies["embed"].assert_called_once()

    def test_evaluate_single_turn_flow(self, mock_dependencies):
        """Vérifie le flux complet d'une évaluation"""
        # Setup des données de retour simulées de Ragas
        mock_results = MagicMock()
        mock_df = MagicMock()
        mock_df.iloc.__getitem__.return_value = {"answer_relevancy": 0.85, "faithfulness": 0.90}
        mock_results.to_pandas.return_value = mock_df
        mock_dependencies["evaluate"].return_value = mock_results

        eval_engine_cls = mock_dependencies["engine_cls"]
        eval_result_cls = mock_dependencies["result_cls"]

        engine = eval_engine_cls()

        # Exécution
        result = engine.evaluate_single_turn(
            query="What is WaveLocalAI?",
            response="It is a local AI tool.",
            retrieved_contexts=["Context 1"],
            judge_tag="mistral-large-latest",
        )

        # Vérifications
        mock_dependencies["provider"].get_langchain_model.assert_called_with(
            "mistral-large-latest",
            temperature=0.0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        mock_dependencies["evaluate"].assert_called_once()

        assert isinstance(result, eval_result_cls)
        assert result.faithfulness == 0.90
        assert result.answer_relevancy == 0.85
        assert result.global_score == 0.875

    def test_evaluate_handles_ragas_exception(self, mock_dependencies):
        """Vérifie que le moteur est robuste aux erreurs Ragas"""
        mock_dependencies["evaluate"].side_effect = Exception("Ragas failure")

        eval_engine_cls = mock_dependencies["engine_cls"]
        engine = eval_engine_cls()

        with pytest.raises(Exception) as excinfo:
            engine.evaluate_single_turn(
                query="Q", response="A", retrieved_contexts=["C"], judge_tag="model"
            )
        assert "Ragas failure" in str(excinfo.value)
