import asyncio
import logging
from typing import Any

from langchain_core.documents import Document

from src.core.llm_provider import LLMProvider
from src.core.rag.strategies.base import RetrievalStrategy

logger = logging.getLogger(__name__)


class HyDERetrievalStrategy(RetrievalStrategy):
    """
    Stratégie HyDE (Hypothetical Document Embeddings).
    1. Génère un document fictif (hypothèse) via un LLM.
    2. Utilise ce document pour la recherche vectorielle.
    3. (Optionnel) Reranking.
    """

    def __init__(self, generator_model_tag: str = "qwen2.5:1.5b"):
        # On utilise un petit modèle rapide par défaut pour générer l'hypothèse
        self.generator_model = generator_model_tag

    async def _generate_hypothesis(self, query: str) -> str:
        """Génère le document hypothétique."""
        prompt = (
            f"Write a comprehensive scientific or technical passage that answers the question: '{query}'. "
            "Do not answer the question directly, but write the paragraph that would contain the answer. "
            "Be concise."
        )

        # On utilise le LLMProvider existant pour générer
        full_text = ""
        stream = LLMProvider.chat_stream(
            model_name=self.generator_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        async for chunk in stream:
            if isinstance(chunk, str):
                full_text += chunk

        return full_text

    def retrieve(
        self, query: str, vector_store: Any, k: int, reranker: Any = None, **kwargs
    ) -> list[Document]:

        # Récupération du modèle à utiliser (passé depuis l'UI ou défaut)
        llm_tag = kwargs.get("llm_model", self.generator_model)

        logger.info(f"🔮 HyDE : Génération d'hypothèse avec {llm_tag}...")

        # Hack pour exécuter l'async dans le sync (Streamlit gère ça, mais ici on est dans une classe)
        try:
            hypothesis = asyncio.run(self._generate_hypothesis(query))
            logger.info(f"🔮 Hypothèse générée : {hypothesis[:100]}...")
        except Exception as e:
            logger.error(f"HyDE Failed: {e}, fallback sur query originale.")
            hypothesis = query

        # Recherche avec l'hypothèse au lieu de la query
        # On fetch plus large (k*2) car l'hypothèse peut être bruitée
        fetch_k = k * 2
        docs = vector_store.similarity_search(hypothesis, k=fetch_k)

        # Reranking Standard (identique à Naive)
        if reranker and docs:
            try:
                # On rerank par rapport à la QUERY originale, pas l'hypothèse !
                # C'est la subtilité : on cherche avec l'hypothèse, on vérifie avec la query.
                pairs = [[query, doc.page_content] for doc in docs]
                scores = reranker.predict(pairs)
                scored_docs = list(zip(docs, scores, strict=False))
                scored_docs.sort(key=lambda x: x[1], reverse=True)
                docs = [doc for doc, score in scored_docs[:k]]

                # Debug info
                for doc in docs:
                    doc.metadata["strategy"] = "HyDE"
            except Exception:
                docs = docs[:k]

        return docs
