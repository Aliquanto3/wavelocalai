"""
Tests unitaires pour les nouveaux outils d'agents.
Usage: pytest tests/unit/test_new_agent_tools.py -v

CORRECTION : Fermeture explicite des fichiers temporaires sous Windows
"""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.core.agent_tools import (
    AVAILABLE_TOOLS,
    TOOLS_METADATA,
    _analyze_csv_impl,
    _generate_chart_impl,
    _generate_document_impl,
    _generate_markdown_report_impl,
    _send_email_impl,
    _system_monitor_impl,
)


class TestSystemMonitor:
    """Tests pour system_monitor."""

    def test_system_monitor_returns_info(self):
        """Test que system_monitor retourne des infos système."""
        result = _system_monitor_impl()

        assert "CPU" in result
        assert "RAM" in result
        assert "Disque" in result
        assert "%" in result

    def test_system_monitor_has_metrics(self):
        """Test que les métriques sont présentes."""
        result = _system_monitor_impl()

        assert any(char.isdigit() for char in result)
        assert "GB" in result


class TestEmailSender:
    """Tests pour send_email."""

    def test_email_validation_invalid_address(self):
        """Test rejet des adresses invalides."""
        result = _send_email_impl("invalid_email", "Subject", "Body")
        assert "❌" in result
        assert "invalide" in result.lower()

    def test_email_validation_empty_subject(self):
        """Test rejet des sujets vides."""
        result = _send_email_impl("test@example.com", "", "Body")
        assert "❌" in result

    def test_email_validation_empty_body(self):
        """Test rejet des corps vides."""
        result = _send_email_impl("test@example.com", "Subject", "")
        assert "❌" in result

    def test_email_requires_smtp_config(self):
        """Test que SMTP doit être configuré."""
        result = _send_email_impl("test@example.com", "Subject", "Body")
        assert "❌" in result or "⚠️" in result


class TestCSVAnalyzer:
    """Tests pour analyze_csv."""

    @pytest.fixture
    def temp_csv(self):
        """Crée un CSV temporaire."""
        df = pd.DataFrame(
            {"name": ["Alice", "Bob", "Charlie"], "age": [25, 30, 35], "score": [85.5, 92.0, 78.5]}
        )

        # CORRECTION : Utilisation de delete=True et gestion explicite
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        ) as f:
            temp_path = f.name
            df.to_csv(f.name, index=False)

        yield temp_path

        # Cleanup : Suppression si le fichier existe encore
        Path(temp_path).unlink(missing_ok=True)

    def test_csv_file_not_found(self):
        """Test erreur si fichier inexistant."""
        result = _analyze_csv_impl("nonexistent.csv", "aperçu")
        assert "❌" in result

    def test_csv_invalid_format(self):
        """Test erreur si format non supporté."""
        # CORRECTION : Créer directement un fichier .txt au lieu de renommer
        df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [25, 30]})

        # Créer un fichier avec mauvaise extension
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            bad_file = f.name
            df.to_csv(f.name, index=False)

        try:
            result = _analyze_csv_impl(bad_file, "aperçu")
            assert "❌" in result
            assert "non supporté" in result.lower()
        finally:
            # Cleanup garanti
            Path(bad_file).unlink(missing_ok=True)

    def test_csv_preview(self, temp_csv):
        """Test aperçu des données."""
        result = _analyze_csv_impl(temp_csv, "aperçu")

        assert "📊" in result
        assert "Lignes" in result
        assert "Colonnes" in result
        assert "name" in result  # Nom de colonne
        assert "Alice" in result or "Bob" in result  # Données

    def test_csv_statistics(self, temp_csv):
        """Test statistiques descriptives."""
        result = _analyze_csv_impl(temp_csv, "stats")

        assert "Statistiques" in result
        # Devrait contenir des stats pour les colonnes numériques

    def test_csv_mean_calculation(self, temp_csv):
        """Test calcul de moyenne."""
        result = _analyze_csv_impl(temp_csv, "moyenne de age")

        assert "Moyenne" in result
        assert "age" in result
        # Moyenne de [25, 30, 35] = 30
        assert "30" in result


class TestDocumentGenerator:
    """Tests pour generate_document."""

    def test_document_creation(self):
        """Test création d'un document."""
        result = _generate_document_impl(
            title="Test Document", content="## Section 1\n\nContenu de test."
        )

        assert "✅" in result
        assert ".docx" in result

        # Vérifier que le fichier existe
        filepath = result.split(":")[-1].strip()
        assert Path(filepath).exists()

        # Cleanup
        Path(filepath).unlink(missing_ok=True)

    def test_document_with_custom_filename(self):
        """Test avec nom de fichier personnalisé."""
        result = _generate_document_impl(
            title="Test", content="Content", filename="custom_doc.docx"
        )

        assert "custom_doc.docx" in result

        # Cleanup
        filepath = result.split(":")[-1].strip()
        Path(filepath).unlink(missing_ok=True)


class TestChartGenerator:
    """Tests pour generate_chart."""

    def test_chart_bar(self):
        """Test graphique en barres."""
        data = json.dumps({"labels": ["A", "B", "C"], "values": [10, 20, 15]})

        result = _generate_chart_impl(data, "bar", "Test Chart")

        assert "✅" in result
        assert ".png" in result

        # Vérifier que le fichier existe
        filepath = result.split(":")[-1].strip()
        assert Path(filepath).exists()

        # Cleanup
        Path(filepath).unlink(missing_ok=True)

    def test_chart_line(self):
        """Test graphique en courbe."""
        data = json.dumps({"labels": ["Jan", "Feb", "Mar"], "values": [5, 10, 8]})

        result = _generate_chart_impl(data, "line", "Test Line")

        assert "✅" in result
        assert ".png" in result

        filepath = result.split(":")[-1].strip()
        Path(filepath).unlink(missing_ok=True)

    def test_chart_pie(self):
        """Test graphique camembert."""
        data = json.dumps({"labels": ["Part A", "Part B"], "values": [60, 40]})

        result = _generate_chart_impl(data, "pie", "Test Pie")

        assert "✅" in result
        filepath = result.split(":")[-1].strip()
        Path(filepath).unlink(missing_ok=True)

    def test_chart_invalid_json(self):
        """Test erreur avec JSON invalide."""
        result = _generate_chart_impl("not json", "bar", "Test")

        assert "❌" in result
        assert "JSON invalide" in result

    def test_chart_invalid_type(self):
        """Test erreur avec type invalide."""
        data = json.dumps({"labels": ["A"], "values": [10]})
        result = _generate_chart_impl(data, "invalid_type", "Test")

        assert "❌" in result
        assert "non supporté" in result


class TestMarkdownReport:
    """Tests pour generate_markdown_report."""

    def test_markdown_creation(self):
        """Test création d'un rapport Markdown."""
        sections = json.dumps(
            {"Introduction": "Ceci est l'intro", "Conclusion": "Ceci est la conclusion"}
        )

        result = _generate_markdown_report_impl("Test Report", sections)

        assert "✅" in result
        assert ".md" in result

        # Vérifier contenu
        filepath = result.split(":")[-1].strip()
        assert Path(filepath).exists()

        content = Path(filepath).read_text(encoding="utf-8")
        assert "# Test Report" in content
        assert "## Introduction" in content
        assert "## Conclusion" in content

        # Cleanup
        Path(filepath).unlink(missing_ok=True)

    def test_markdown_with_text_content(self):
        """Test avec contenu texte simple (pas JSON)."""
        result = _generate_markdown_report_impl("Simple Report", "Juste du texte simple")

        assert "✅" in result

        filepath = result.split(":")[-1].strip()
        content = Path(filepath).read_text(encoding="utf-8")
        assert "Simple Report" in content
        assert "texte simple" in content

        Path(filepath).unlink(missing_ok=True)


class TestToolsIntegration:
    """Tests d'intégration des outils."""

    def test_all_new_tools_importable(self):
        """Test que tous les nouveaux outils sont importables."""
        from src.core.agent_tools import (
            analyze_csv,
            generate_chart,
            generate_document,
            generate_markdown_report,
            send_email,
            system_monitor,
        )

        tools = [
            analyze_csv,
            generate_chart,
            generate_document,
            generate_markdown_report,
            send_email,
            system_monitor,
        ]

        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert callable(tool.run)

    def test_tools_metadata_complete(self):
        """Test que TOOLS_METADATA est complet."""
        from src.core.agent_tools import TOOLS_METADATA

        required_new_tools = [
            "send_email",
            "analyze_csv",
            "generate_document",
            "generate_chart",
            "generate_markdown_report",
            "system_monitor",
        ]

        for tool_name in required_new_tools:
            assert tool_name in TOOLS_METADATA
            metadata = TOOLS_METADATA[tool_name]

            assert "name" in metadata
            assert "description" in metadata
            assert "category" in metadata
            assert "requires_config" in metadata

    def test_all_tools_count(self):
        """Test nombre total d'outils."""
        assert (
            len(AVAILABLE_TOOLS) == 9
        ), f"Devrait avoir 9 outils, mais {len(AVAILABLE_TOOLS)} trouvé(s)"
        assert (
            len(TOOLS_METADATA) == 9
        ), f"Devrait avoir 9 métadonnées, mais {len(TOOLS_METADATA)} trouvées"

    def test_all_tools_have_metadata(self):
        """Test que chaque outil a ses métadonnées."""
        for tool in AVAILABLE_TOOLS:
            assert tool.name in TOOLS_METADATA, f"L'outil {tool.name} n'a pas de métadonnées"

    def test_metadata_categories_valid(self):
        """Test que les catégories sont valides."""
        valid_categories = ["system", "computation", "data", "communication", "output", "custom"]

        for tool_name, metadata in TOOLS_METADATA.items():
            category = metadata.get("category")
            assert category in valid_categories, f"Catégorie '{category}' invalide pour {tool_name}"
