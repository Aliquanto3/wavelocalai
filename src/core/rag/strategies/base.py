from abc import ABC, abstractmethod
from typing import Any

from langchain_core.documents import Document


class RetrievalStrategy(ABC):
    """
    Interface abstraite pour les stratégies de Retrieval.
    """

    @abstractmethod
    def retrieve(
        self, query: str, vector_store: Any, k: int, reranker: Any = None, **kwargs
    ) -> list[Document]:
        """
        Exécute la logique de récupération.

        Args:
            query: La question utilisateur
            vector_store: L'instance ChromaDB (LangChain)
            k: Nombre de documents à récupérer
            reranker: (Optionnel) Modèle CrossEncoder pour le re-classement

        Returns:
            Liste de documents pertinents
        """
        pass
