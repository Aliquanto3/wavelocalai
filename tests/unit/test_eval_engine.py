"""
Tests unitaires pour EvalEngine (Moteur d'évaluation RAG).
Usage: pytest tests/unit/test_eval_engine.py -v
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# On utilise un import conditionnel pour éviter les erreurs si les dépendances ne sont pas encore installées
try:
    from src.core.eval_engine import EvalEngine, EvalResult
except ImportError:
    # Dummy classes pour que les tests puissent être collectés même si l'implémentation manque
    EvalEngine = None
    EvalResult = None


@pytest.fixture
def mock_dependencies():
    """Mocks pour les dépendances externes (Ragas, LangChain, Env)."""
    with (
        patch("src.core.eval_engine.ChatMistralAI") as mock_mistral,
        patch("src.core.eval_engine.HuggingFaceEmbeddings") as mock_embeddings,
        patch("src.core.eval_engine.evaluate") as mock_evaluate,
        patch("src.core.eval_engine.MISTRAL_API_KEY", "fake_key_123"),
    ):
        yield {"mistral": mock_mistral, "embeddings": mock_embeddings, "evaluate": mock_evaluate}


class TestEvalEngineInitialization:
    """Tests de l'initialisation du moteur."""

    def test_init_success(self, mock_dependencies):
        """Vérifie que le moteur s'initialise avec la bonne config JSON pour Mistral."""
        if EvalEngine is None:
            pytest.skip("Module src.core.eval_engine non implémenté")

        # Correction F841 : On n'utilise pas la variable engine, on utilise _
        _ = EvalEngine()

        # 1. Vérification du Juge (Mistral)
        mock_dependencies["mistral"].assert_called_once()
        _, kwargs = mock_dependencies["mistral"].call_args

        # POINT CRITIQUE : Vérifier le mode JSON
        assert kwargs["model"] == "mistral-large-latest"
        assert kwargs["model_kwargs"] == {"response_format": {"type": "json_object"}}
        assert kwargs["temperature"] == 0.0

        # 2. Vérification des Embeddings
        mock_dependencies["embeddings"].assert_called_once()

    def test_init_missing_api_key(self):
        """Vérifie qu'une erreur est levée si la clé API est manquante."""
        if EvalEngine is None:
            pytest.skip("Module src.core.eval_engine non implémenté")

        # Correction SIM117 : Fusion des context managers
        with (
            patch("src.core.eval_engine.MISTRAL_API_KEY", None),
            pytest.raises(ValueError, match="clé API Mistral est requise"),
        ):
            EvalEngine()


class TestEvalEngineEvaluation:
    """Tests de la méthode d'évaluation."""

    def test_evaluate_single_turn_flow(self, mock_dependencies):
        """Vérifie le flux complet d'évaluation d'une interaction."""
        if EvalEngine is None:
            pytest.skip("Module src.core.eval_engine non implémenté")

        engine = EvalEngine()

        # Mock du résultat de ragas.evaluate
        # Ragas retourne un objet Result qui contient un DataFrame pandas
        mock_result = MagicMock()
        mock_result.to_pandas.return_value = pd.DataFrame(
            [
                {
                    "answer_relevancy": 0.95,
                    "faithfulness": 0.85,
                    "context_precision": 0.0,  # On ignore cette métrique dans la V2
                }
            ]
        )
        mock_dependencies["evaluate"].return_value = mock_result

        # Exécution
        result = engine.evaluate_single_turn(
            query="Quelle est la capitale ?",
            response="Paris",
            retrieved_contexts=["La capitale de la France est Paris."],
        )

        # 1. Vérifications de l'appel à Ragas
        mock_dependencies["evaluate"].assert_called_once()
        call_args = mock_dependencies["evaluate"].call_args

        # On vérifie qu'on passe bien le Juge configuré et les Embeddings
        assert call_args.kwargs["llm"] == engine.judge_llm
        assert call_args.kwargs["embeddings"] == engine.embeddings

        # 2. Vérification du Résultat formaté
        assert isinstance(result, EvalResult)
        assert result.answer_relevancy == 0.95
        assert result.faithfulness == 0.85

        # Calcul du score global : (0.95 + 0.85) / 2 = 0.9
        assert result.global_score == 0.9
