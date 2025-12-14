import logging
from dataclasses import dataclass

from langchain_huggingface import HuggingFaceEmbeddings

# LangChain Imports
from langchain_mistralai import ChatMistralAI

# Ragas Imports
try:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False

from src.core.config import MISTRAL_API_KEY

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
    Utilise un LLM Cloud (Mistral) pour juger un LLM Local (Ollama).
    """

    def __init__(self):
        if not RAGAS_AVAILABLE:
            raise ImportError("Le module 'ragas' n'est pas installé.")

        if not MISTRAL_API_KEY:
            raise ValueError("La clé API Mistral est requise pour le Juge (EvalOps).")

        # 1. Configuration du Juge (Cloud - Puissant)
        # On force le 'json_object' pour éviter les ```json qui font crasher Ragas
        self.judge_llm = ChatMistralAI(
            model="mistral-large-latest",
            api_key=MISTRAL_API_KEY,
            temperature=0.0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

        # 2. Configuration des Embeddings (Local - Rapide)
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    def evaluate_single_turn(
        self, query: str, response: str, retrieved_contexts: list[str]
    ) -> EvalResult:
        """
        Évalue une seule interaction (Question/Réponse/Contexte).
        """
        logger.info(f"⚖️ Démarrage évaluation Ragas pour : '{query}'")

        # 1. Préparation du Dataset
        data = {
            "question": [query],
            "answer": [response],
            "contexts": [retrieved_contexts],
        }
        dataset = Dataset.from_dict(data)

        # 2. Configuration des métriques (Reference-Free uniquement)
        # Context Precision nécessite une vérité terrain (Ground Truth), on l'omet ici.
        metrics = [answer_relevancy, faithfulness]

        # Injection des dépendances
        for m in metrics:
            if hasattr(m, "llm"):
                m.llm = self.judge_llm
            if hasattr(m, "embeddings"):
                m.embeddings = self.embeddings

        # 3. Exécution de l'évaluation
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=self.judge_llm,
            embeddings=self.embeddings,
            raise_exceptions=False,
        )

        # 4. Extraction des scores
        scores = results.to_pandas().iloc[0]

        return EvalResult(
            answer_relevancy=round(scores.get("answer_relevancy", 0.0), 3),
            faithfulness=round(scores.get("faithfulness", 0.0), 3),
            global_score=round(
                (scores.get("answer_relevancy", 0) + scores.get("faithfulness", 0)) / 2, 3
            ),
        )
