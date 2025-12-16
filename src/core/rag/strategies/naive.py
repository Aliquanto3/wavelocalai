import logging
from typing import Any

from langchain_core.documents import Document

from src.core.rag.strategies.base import RetrievalStrategy

logger = logging.getLogger(__name__)


class NaiveRetrievalStrategy(RetrievalStrategy):
    """
    Stratégie RAG Classique :
    1. Similarity Search (Vector DB)
    2. (Optionnel) Reranking avec Cross-Encoder
    """

    def retrieve(
        self, query: str, vector_store: Any, k: int, reranker: Any = None, **kwargs
    ) -> list[Document]:

        # 1. Retrieval initial (on en prend un peu plus si on rerank après)
        fetch_k = k * 3 if reranker else k
        logger.info(f"🔍 Naive Search : Fetching {fetch_k} docs for query '{query}'")

        docs = vector_store.similarity_search(query, k=fetch_k)

        # 2. Reranking (Si disponible)
        if reranker and docs:
            logger.info("⚖️ Application du Reranker...")
            try:
                # Prépare les paires [Query, Doc]
                pairs = [[query, doc.page_content] for doc in docs]
                scores = reranker.predict(pairs)

                # Associe score au doc et trie
                scored_docs = list(zip(docs, scores, strict=False))
                scored_docs.sort(key=lambda x: x[1], reverse=True)

                # Garde le top K final
                docs = [doc for doc, score in scored_docs[:k]]

                # Ajoute le score aux métadonnées pour debug
                for _i, (doc, score) in enumerate(scored_docs[:k]):
                    doc.metadata["rerank_score"] = float(score)

            except Exception as e:
                logger.error(f"Erreur Reranking : {e}, fallback sur similarity pure.")
                docs = docs[:k]

        return docs
