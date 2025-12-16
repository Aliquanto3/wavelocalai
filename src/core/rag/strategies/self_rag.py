import asyncio
import logging
from typing import Any, TypedDict

from langchain_core.documents import Document

# LangGraph & LangChain
from langgraph.graph import END, StateGraph

from src.core.llm_provider import LLMProvider

# Core App
from src.core.rag.strategies.base import RetrievalStrategy

logger = logging.getLogger(__name__)


# --- 1. DÉFINITION DE L'ÉTAT DU GRAPHE ---
class GraphState(TypedDict):
    """
    L'état qui circule dans le graphe.
    """

    question: str  # La question (originale ou réécrite)
    original_question: str  # Pour référence
    documents: list[Document]  # Les docs récupérés
    generation: str  # La réponse finale
    loop_step: int  # Compteur pour éviter les boucles infinies


class SelfRAGStrategy(RetrievalStrategy):
    """
    Stratégie Self-RAG (Corrective RAG) locale avec LangGraph.
    Vérifie la pertinence des documents avant de répondre.
    """

    def __init__(self, grader_llm: str = "qwen2.5:1.5b"):
        # On utilise un "petit" modèle rapide pour la notation (Grading)
        self.grader_llm_tag = grader_llm
        self.MAX_LOOPS = 2  # Sécurité : max 2 réécritures

    # --- 2. LES NOEUDS (NODES) ---

    async def retrieve_node(self, state: GraphState, vector_store, k, reranker):
        """Node: Récupère les documents."""
        logger.info(f"🔄 [Self-RAG] Retrieval pour : {state['question']}")

        # On utilise la logique standard (Similarity + Rerank)
        # Note: On duplique un peu la logique 'Naive' ici pour l'intégrer au graphe
        docs = vector_store.similarity_search(state["question"], k=k * 2)  # Fetch large

        if reranker and docs:
            try:
                pairs = [[state["question"], doc.page_content] for doc in docs]
                scores = reranker.predict(pairs)
                scored_docs = sorted(
                    zip(docs, scores, strict=False), key=lambda x: x[1], reverse=True
                )
                docs = [d for d, s in scored_docs[:k]]
            except Exception:
                docs = docs[:k]
        else:
            docs = docs[:k]

        return {"documents": docs, "question": state["question"]}

    async def grade_documents_node(self, state: GraphState):
        """Node: Filtre les documents non pertinents."""
        logger.info("⚖️ [Self-RAG] Grading documents...")
        question = state["question"]
        documents = state["documents"]

        filtered_docs = []

        # Prompt de notation binaire (JSON mode implicite)
        system_prompt = (
            "You are a grader assessing relevance of a retrieved document to a user question. "
            "If the document contains keyword(s) or semantic meaning related to the question, grade it as relevant. "
            "Reply only with 'yes' or 'no'."
        )

        for doc in documents:
            # Appel LLM léger pour chaque doc (parallélisable idéalement)
            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Document: {doc.page_content[:400]}...\n\nQuestion: {question}",
                },
            ]

            # On utilise chat_stream en mode "one shot"
            response_text = ""
            async for chunk in LLMProvider.chat_stream(
                self.grader_llm_tag, messages, temperature=0
            ):
                if isinstance(chunk, str):
                    response_text += chunk

            grade = response_text.strip().lower()

            if "yes" in grade:
                filtered_docs.append(doc)
            else:
                logger.debug("   ❌ Doc rejeté")

        return {"documents": filtered_docs}

    async def rewrite_node(self, state: GraphState):
        """Node: Réécrit la question pour améliorer le retrieval."""
        logger.info("✍️ [Self-RAG] Réécriture de la question...")
        question = state["question"]

        msg = [
            {
                "role": "system",
                "content": "You are a question re-writer that converts an input question to a better version that is optimized for vectorstore retrieval. Look at the initial and formulate an improved question. Just output the question.",
            },
            {"role": "user", "content": f"Initial question: {question}"},
        ]

        better_question = ""
        async for chunk in LLMProvider.chat_stream(self.grader_llm_tag, msg, temperature=0.5):
            if isinstance(chunk, str):
                better_question += chunk

        return {"question": better_question, "loop_step": state["loop_step"] + 1}

    # --- 3. LES BORDS (EDGES) ---

    def decide_to_generate(self, state: GraphState):
        """Edge Conditionnel : Générer ou Réécrire ?"""
        filtered_documents = state["documents"]
        loop_step = state.get("loop_step", 0)

        if not filtered_documents:
            # Aucun doc pertinent trouvé
            if loop_step >= self.MAX_LOOPS:
                logger.warning("🛑 [Self-RAG] Max loops reached. Stop.")
                return "stop_empty"  # Cas d'abandon
            else:
                logger.info("🔄 [Self-RAG] Documents insuffisants -> Rewrite.")
                return "rewrite"
        else:
            # On a des docs pertinents
            return "generate"

    # --- 4. MAIN EXECUTION ---

    def retrieve(
        self, query: str, vector_store: Any, k: int, reranker: Any = None, **kwargs
    ) -> list[Document]:

        # Construction du graphe (à chaque appel pour simplifier le passage des objets k/store)
        workflow = StateGraph(GraphState)

        # Définition des noeuds (wrappers asynchrones nécessaires pour LangGraph)
        # Note: Dans une app pure LangGraph, on compilerait le graphe une seule fois.
        # Ici, on l'utilise de manière ad-hoc pour s'intégrer dans ta structure de classe.

        async def _retrieve_wrapper(state):
            return await self.retrieve_node(state, vector_store, k, reranker)

        workflow.add_node("retrieve", _retrieve_wrapper)
        workflow.add_node("grade_documents", self.grade_documents_node)
        workflow.add_node("rewrite", self.rewrite_node)

        # Construction des arcs
        workflow.set_entry_point("retrieve")
        workflow.add_edge("retrieve", "grade_documents")

        workflow.add_conditional_edges(
            "grade_documents",
            self.decide_to_generate,
            {
                "rewrite": "rewrite",
                "generate": END,  # Succès : on retourne les docs filtrés
                "stop_empty": END,  # Échec : on retourne liste vide (ou docs originaux selon choix)
            },
        )
        workflow.add_edge("rewrite", "retrieve")

        app = workflow.compile()

        # Exécution du graphe
        logger.info(f"🚀 Démarrage Self-RAG Graph pour : {query}")

        # On doit utiliser asyncio.run car retrieve est sync dans la classe de base
        # mais LangGraph est async.
        try:
            inputs = {"question": query, "original_question": query, "loop_step": 0}

            # Invocation
            final_state = asyncio.run(app.ainvoke(inputs))

            final_docs = final_state.get("documents", [])
            logger.info(f"🏁 Fin Self-RAG. Docs retenus : {len(final_docs)}")

            # Marquage des métadonnées pour l'UI
            for doc in final_docs:
                doc.metadata["strategy"] = "Self-RAG"
                doc.metadata["final_query"] = final_state["question"]  # Pour voir si réécriture

            return final_docs

        except Exception as e:
            logger.error(f"❌ Erreur Critical Self-RAG: {e}")
            # Fallback Naive en cas de crash du graphe
            return vector_store.similarity_search(query, k=k)
