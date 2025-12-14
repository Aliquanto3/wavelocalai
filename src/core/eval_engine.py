import logging
from dataclasses import dataclass

from langchain_huggingface import HuggingFaceEmbeddings

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
    Moteur d'évaluation RAG Hybride.
    Capable d'utiliser n'importe quel modèle (Local ou Cloud) comme Juge.
    """

    def __init__(self):
        if not RAGAS_AVAILABLE:
            raise ImportError("Le module 'ragas' n'est pas installé.")

        # Embeddings (Local - Rapide) pour Ragas
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    def evaluate_single_turn(
        self, query: str, response: str, retrieved_contexts: list[str], judge_tag: str
    ) -> EvalResult:
        """
        Évalue une seule interaction avec un Juge spécifique.
        """
        logger.info(f"⚖️ Démarrage évaluation Ragas avec le juge : {judge_tag}")

        # 1. Configuration Avancée du Juge
        # Si c'est un modèle Mistral API, on force le mode JSON Object pour éviter le Markdown qui casse Ragas
        model_kwargs = {}
        if "mistral" in judge_tag.lower() or "ministral" in judge_tag.lower():
            model_kwargs = {"response_format": {"type": "json_object"}}

        # 2. Instanciation Dynamique
        judge_llm = LLMProvider.get_langchain_model(
            judge_tag, temperature=0.0, model_kwargs=model_kwargs
        )

        # 3. Préparation du Dataset
        data = {
            "question": [query],
            "answer": [response],
            "contexts": [retrieved_contexts],
        }
        dataset = Dataset.from_dict(data)

        # 4. Configuration des métriques
        metrics = [answer_relevancy, faithfulness]

        # Injection du Juge dans chaque métrique
        for m in metrics:
            if hasattr(m, "llm"):
                m.llm = judge_llm
            if hasattr(m, "embeddings"):
                m.embeddings = self.embeddings

        # 5. Exécution de l'évaluation
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=judge_llm,
            embeddings=self.embeddings,
            raise_exceptions=False,
        )

        # 6. Extraction des scores
        scores = results.to_pandas().iloc[0]

        return EvalResult(
            answer_relevancy=round(scores.get("answer_relevancy", 0.0), 3),
            faithfulness=round(scores.get("faithfulness", 0.0), 3),
            global_score=round(
                (scores.get("answer_relevancy", 0) + scores.get("faithfulness", 0)) / 2, 3
            ),
        )
