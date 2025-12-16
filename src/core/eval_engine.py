import logging
from dataclasses import dataclass
from typing import Any

# Ragas Imports
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False

from src.core.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    """Résultat d'une évaluation Ragas."""

    answer_relevancy: float
    faithfulness: float
    global_score: float


class EvalEngine:
    """
    Moteur d'évaluation RAG Hybride (EvalOps).
    Utilise Ragas avec le LLM Juge et les Embeddings actifs.
    """

    def __init__(self):
        if not RAGAS_AVAILABLE:
            logger.warning("⚠️ Ragas non installé. L'évaluation sera désactivée.")

    def evaluate_single_turn(
        self,
        query: str,
        response: str,
        retrieved_contexts: list[str],
        judge_tag: str,
        embedding_model: Any,  # <--- Injection dynamique
    ) -> EvalResult:
        """
        Évalue une interaction en utilisant le modèle d'embedding ACTIF du RAG.
        """
        if not RAGAS_AVAILABLE:
            return EvalResult(0.0, 0.0, 0.0)

        logger.info(f"⚖️ EvalOps: Juge={judge_tag} | Embedding={type(embedding_model).__name__}")

        # 1. Configuration du Juge (LangChain Object)
        # Force JSON mode pour Mistral afin d'éviter les erreurs de parsing Ragas
        model_kwargs = {}
        if "mistral" in judge_tag.lower():
            model_kwargs = {"response_format": {"type": "json_object"}}

        judge_llm = LLMProvider.get_langchain_model(
            judge_tag, temperature=0.0, model_kwargs=model_kwargs
        )

        # 2. Préparation du Dataset Standard Ragas
        data = {
            "question": [query],
            "answer": [response],
            "contexts": [retrieved_contexts],
            # Ragas demande parfois "ground_truth", on peut laisser vide pour ces métriques
            # "ground_truth": [""]
        }
        dataset = Dataset.from_dict(data)

        # 3. Sélection des métriques
        # On injecte le Juge ET l'Embedding dans chaque métrique
        metrics = [answer_relevancy, faithfulness]

        for m in metrics:
            # Injection du LLM Juge
            if hasattr(m, "llm"):
                m.llm = judge_llm
            # Injection de l'Embedding actif (CRITIQUE pour la cohérence)
            if hasattr(m, "embeddings"):
                m.embeddings = embedding_model

        # 4. Exécution (Safe Mode)
        try:
            results = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=judge_llm,
                embeddings=embedding_model,
                raise_exceptions=False,  # Continue même si une métrique échoue
            )

            scores = results.to_pandas().iloc[0]

            # Parsing sécurisé des scores (parfois NaN si le LLM local échoue)
            answ_rel = scores.get("answer_relevancy", 0.0)
            faith = scores.get("faithfulness", 0.0)

            # Conversion NaN -> 0.0
            answ_rel = 0.0 if answ_rel != answ_rel else answ_rel
            faith = 0.0 if faith != faith else faith

            return EvalResult(
                answer_relevancy=round(answ_rel, 3),
                faithfulness=round(faith, 3),
                global_score=round((answ_rel + faith) / 2, 3),
            )

        except Exception as e:
            logger.error(f"❌ Erreur critique Ragas : {e}")
            return EvalResult(0.0, 0.0, 0.0)
