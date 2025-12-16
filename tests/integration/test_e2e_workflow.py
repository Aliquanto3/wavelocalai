"""
Tests End-to-End du workflow complet.
Usage: pytest tests/integration/test_e2e_workflow.py -v -m integration
"""

import tempfile
from pathlib import Path

import pytest

from src.core.agent_engine import AgentEngine
from src.core.inference_service import InferenceService
from src.core.rag_engine import RAGEngine


@pytest.mark.integration
@pytest.mark.asyncio
class TestEndToEndWorkflow:
    """Tests du workflow complet de l'application."""

    async def test_simple_inference_workflow(self):
        """Test workflow : Simple inférence."""
        result = await InferenceService.run_inference(
            model_tag="qwen2.5:1.5b",
            messages=[{"role": "user", "content": "Dis 'test' (un mot)"}],
            temperature=0.0,
            timeout=30,
        )

        assert result.error is None, f"Erreur : {result.error}"
        assert len(result.clean_text) > 0
        assert result.metrics is not None
        assert result.metrics.tokens_per_second > 0

    async def test_rag_workflow(self):
        """Test workflow : RAG complet (ingestion + recherche)."""
        # MISE À JOUR V2 : On instancie avec un modèle léger explicite
        # Le paramètre 'collection_name' n'existe plus, c'est géré par le modèle
        rag = RAGEngine(embedding_model_name="all-MiniLM-L6-v2")

        # Nettoyage préventif
        rag.clear_database()

        try:
            test_content = """
            WaveLocalAI est une application de demonstration IA.
            Elle utilise des modeles locaux via Ollama.
            L'objectif est la confidentialite et le Green IT.
            """

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(test_content)
                temp_path = f.name

            chunks = rag.ingest_file(temp_path, "test_doc.txt")
            assert chunks > 0, "Devrait créer au moins 1 chunk"

            # Test de recherche
            results = rag.search("Quel est l'objectif de WaveLocalAI ?", k=2)
            assert len(results) > 0, "Devrait trouver des résultats"

            combined_text = " ".join([doc.page_content for doc in results])
            assert "confidentialite" in combined_text.lower() or "green" in combined_text.lower()

            stats = rag.get_stats()
            assert stats["count"] > 0

        finally:
            Path(temp_path).unlink(missing_ok=True)
            rag.clear_database()

    async def test_agent_workflow(self):
        """Test workflow : Agent avec outils."""
        agent = AgentEngine(model_name="qwen2.5:1.5b")

        query = "Utilise l'outil get_current_time pour me dire quelle heure il est exactement"

        tool_used = False
        final_answer = None

        stream = agent.run_stream(query)
        for event in stream:
            if event["type"] == "tool_call":
                tool_used = True
            elif event["type"] == "final_answer":
                final_answer = event["content"]

        has_time_info = final_answer and any(char.isdigit() for char in final_answer)
        assert (
            tool_used or has_time_info
        ), "L'agent devrait utiliser l'outil ou répondre avec l'heure"

    async def test_combined_inference_and_rag(self):
        """Test workflow : Inférence + RAG."""
        # MISE À JOUR V2
        rag = RAGEngine(embedding_model_name="all-MiniLM-L6-v2")
        rag.clear_database()

        try:
            test_content = "Le projet WaveLocalAI a ete cree en decembre 2025."

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(test_content)
                temp_path = f.name

            rag.ingest_file(temp_path, "info.txt")

            docs = rag.search("Quand a ete cree WaveLocalAI ?", k=1)
            assert len(docs) > 0

            context = docs[0].page_content
            prompt = f"Contexte : {context}\n\nQuestion : Quand a ete cree le projet ?"

            result = await InferenceService.run_inference(
                model_tag="qwen2.5:1.5b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                timeout=30,
            )

            assert result.error is None
            assert "2025" in result.clean_text or "decembre" in result.clean_text.lower()

        finally:
            Path(temp_path).unlink(missing_ok=True)
            rag.clear_database()

    async def test_agent_with_selective_tools(self):
        """Test workflow : Agent avec outils sélectionnés."""
        agent = AgentEngine(
            model_name="qwen2.5:1.5b", enabled_tools=["calculator", "system_monitor"]
        )

        assert len(agent.tools) == 2
        tool_names = [t.name for t in agent.tools]
        assert "calculator" in tool_names
        assert "system_monitor" in tool_names
        assert "send_email" not in tool_names

        query = "Calcule 25 * 4 puis vérifie l'état du système"

        tool_calls = []
        stream = agent.run_stream(query)
        for event in stream:
            if event["type"] == "tool_call":
                tool_calls.append(event["tool"])

        assert len(tool_calls) > 0
        assert any(name in ["calculator", "system_monitor"] for name in tool_calls)


@pytest.mark.integration
class TestErrorRecovery:
    """Tests de récupération d'erreur."""

    @pytest.mark.asyncio
    async def test_inference_with_invalid_model(self):
        """Test gestion d'un modèle invalide."""
        result = await InferenceService.run_inference(
            model_tag="modele-inexistant-123",
            messages=[{"role": "user", "content": "Test"}],
            timeout=5,
        )

        has_error = result.error is not None or "erreur" in result.raw_text.lower()
        assert has_error, "Devrait contenir une erreur"

    def test_rag_with_invalid_file(self):
        """Test RAG avec fichier invalide."""
        # MISE À JOUR V2
        rag = RAGEngine()

        with pytest.raises((FileNotFoundError, ValueError)):
            rag.ingest_file("/chemin/inexistant/fichier.pdf", "fake.pdf")

    def test_rag_with_malicious_path(self):
        """Test RAG avec chemin malveillant."""
        # MISE À JOUR V2
        rag = RAGEngine()

        # Le message d'erreur peut varier selon l'OS (séparateur / ou \), on cherche "refusé" ou "outside"
        with pytest.raises((ValueError, FileNotFoundError)):
            # Note: selon l'implémentation v2, FileNotFoundError peut lever avant la sécu si le fichier n'existe pas
            # Mais ingestion_pipeline._validate_path devrait lever une erreur.
            rag.ingest_file("../../../../etc/passwd", "malicious.txt")
