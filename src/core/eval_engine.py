import logging
import math
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
    """Résultat d'une évaluation Ragas, scores entre 0 et 1.

    Un score None signifie « non évalué » (Ragas absent, erreur, NaN, métrique manquante), avec
    la raison dans `reason` ; il n'est jamais remplacé par 0. `global_score` n'existe que si
    les deux métriques ont été calculées.
    """

    answer_relevancy: float | None
    faithfulness: float | None
    global_score: float | None
    reason: str | None = None
    # Trace technique (texte de l'exception), à replier dans « Détails techniques ».
    detail: str | None = None

    @property
    def evaluated(self) -> bool:
        """Vrai si la note globale a pu être calculée."""
        return self.global_score is not None

    @classmethod
    def not_evaluated(cls, reason: str, detail: str | None = None) -> "EvalResult":
        return cls(None, None, None, reason, detail)


def _score(scores: Any, name: str) -> float | None:
    """Score fini d'une métrique, ou None (colonne absente, NaN, valeur illisible)."""
    try:
        value = scores.get(name)
    except Exception:
        return None
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


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
            return EvalResult.not_evaluated("Ragas n'est pas installé.")

        logger.info(f"⚖️ EvalOps: Juge={judge_tag} | Embedding={type(embedding_model).__name__}")

        try:
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
            results = evaluate(
                dataset=dataset,
                metrics=metrics,
                llm=judge_llm,
                embeddings=embedding_model,
                raise_exceptions=False,  # Continue même si une métrique échoue
            )

            scores = results.to_pandas().iloc[0]

        except Exception as e:
            logger.error(f"❌ Erreur critique Ragas : {e}")
            return EvalResult.not_evaluated(
                "l'évaluation par le juge a échoué.", f"{type(e).__name__}: {e}"
            )

        # Scores absents ou NaN (juge local qui échoue) : « non évalué », jamais 0.
        answ_rel = _score(scores, "answer_relevancy")
        faith = _score(scores, "faithfulness")

        missing = [
            label
            for label, value in (("pertinence", answ_rel), ("fidélité", faith))
            if value is None
        ]
        if missing:
            reason = (
                f"Le juge n'a pas pu calculer : {', '.join(missing)}."
                if len(missing) == 1
                else "Le juge n'a pu calculer ni la pertinence ni la fidélité."
            )
            return EvalResult(
                answer_relevancy=None if answ_rel is None else round(answ_rel, 3),
                faithfulness=None if faith is None else round(faith, 3),
                global_score=None,
                reason=reason,
            )

        return EvalResult(
            answer_relevancy=round(answ_rel, 3),
            faithfulness=round(faith, 3),
            global_score=round((answ_rel + faith) / 2, 3),
        )
