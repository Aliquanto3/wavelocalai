"""
Tests unitaires pour les outils d'agents (version corrigée).
Usage: pytest tests/unit/test_agent_tools.py -v
"""

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.core.tools import (
    analyze_csv,
    generate_chart,
    generate_document,
    generate_markdown_report,
    send_email,
    system_monitor,
)


@pytest.fixture
def temp_csv():
    df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [25, 30]})
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", encoding="utf-8") as f:
        df.to_csv(f.name, index=False)
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


class TestSystemMonitor:
    def test_system_monitor_returns_info(self):
        # Utilisation de .invoke() pour les outils LangChain
        result = system_monitor.invoke({})
        assert "CPU" in result
        assert "RAM" in result
        assert "Disque" in result


class TestEmailSender:
    def test_email_validation_invalid_address(self):
        # Passage des arguments sous forme de dictionnaire
        result = send_email.invoke({"to": "invalid_email", "subject": "Subject", "body": "Body"})
        assert "Erreur" in result
        assert "invalide" in result.lower()

    def test_email_simulation_success(self):
        result = send_email.invoke(
            {"to": "test@wavestone.com", "subject": "Hello", "body": "World"}
        )
        assert "✅" in result


class TestCSVAnalyzer:
    @pytest.fixture
    def temp_csv(self):
        df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [25, 30]})
        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w", encoding="utf-8"
        ) as f:
            df.to_csv(f.name, index=False)
            path = f.name
        yield path
        Path(path).unlink(missing_ok=True)

    def test_csv_analyze_describe(self, temp_csv):
        # Aligné sur l'implémentation : query="describe"
        result = analyze_csv.invoke({"file_path": temp_csv, "query": "describe"})
        assert "age" in result
        assert "count" in result

    def test_csv_file_not_found(self):
        result = analyze_csv.invoke({"file_path": "nonexistent.csv", "query": "describe"})
        assert "Erreur" in result


class TestDocumentGenerator:
    def test_document_creation(self):
        result = generate_document.invoke(
            {"title": "Test Doc", "content": "## Section\n\nContenu", "author": "Tester"}
        )
        assert "Document généré" in result
        path = result.split(": ")[1].strip()
        assert Path(path).exists()
        Path(path).unlink(missing_ok=True)


class TestChartGenerator:
    def test_chart_generation(self, temp_csv):
        # Correction : on envoie un chemin de fichier et non du JSON
        result = generate_chart.invoke(
            {
                "file_path": temp_csv,
                "x_column": "name",
                "y_column": "age",
                "chart_type": "bar",
                "title": "Ages",
            }
        )
        assert "Graphique généré" in result
        path = result.split(": ")[1].strip()
        assert Path(path).exists()
        Path(path).unlink(missing_ok=True)


class TestMarkdownReport:
    def test_markdown_creation(self):
        # Format attendu par le code : "Titre: contenu | Titre: contenu"
        sections = "Intro: Bienvenue | Conclusion: Fin"
        result = generate_markdown_report.invoke({"title": "Rapport Test", "sections": sections})
        assert "Rapport généré" in result
        path = result.split(": ")[1].strip()
        assert Path(path).exists()

        content = Path(path).read_text(encoding="utf-8")
        assert "## Intro" in content
        assert "Bienvenue" in content
        Path(path).unlink(missing_ok=True)
