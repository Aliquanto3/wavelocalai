"""
Tests de sécurité pour l'Ingestion RAG (Path Traversal).
Usage: pytest tests/unit/test_rag_security.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import DATA_DIR

# ✅ CORRECTION : On importe IngestionPipeline, car c'est lui qui porte la logique de sécurité maintenant
from src.core.rag.ingestion import IngestionPipeline


class TestRAGSecurity:
    """Tests de sécurité du pipeline d'ingestion."""

    @pytest.fixture
    def pipeline(self):
        """Fixture : Instance du pipeline."""
        return IngestionPipeline()

    @pytest.fixture
    def valid_temp_file(self):
        """Crée un fichier texte valide dans le dossier temp."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content.")
            temp_path = f.name
        yield temp_path
        Path(temp_path).unlink(missing_ok=True)

    # ========================================
    # TESTS VALIDES
    # ========================================

    def test_validation_temp_file(self, pipeline, valid_temp_file):
        """Test qu'un fichier dans TEMP est accepté."""
        # _validate_path est une méthode statique
        validated_path = pipeline._validate_path(valid_temp_file)
        assert validated_path.exists()

    def test_validation_data_dir_file(self, pipeline):
        """Test qu'un fichier dans DATA_DIR est accepté."""
        test_file = DATA_DIR / "security_test.txt"
        test_file.write_text("ok")
        try:
            validated_path = pipeline._validate_path(str(test_file))
            assert validated_path.exists()
        finally:
            test_file.unlink(missing_ok=True)

    # ========================================
    # TESTS DE SÉCURITÉ (Path Traversal)
    # ========================================

    def test_reject_path_traversal_simple(self, pipeline):
        """Test rejet d'un path traversal simple."""
        malicious_path = "../../../../etc/passwd"
        # Le code lève FileNotFoundError car le resolve() pointe vers un fichier qui n'existe pas (sur Windows)
        # ou un ValueError si on sort des dossiers autorisés.
        with pytest.raises((ValueError, FileNotFoundError)):
            pipeline._validate_path(malicious_path)

    def test_reject_absolute_path_outside(self, pipeline):
        """Test rejet d'un chemin absolu interdit."""
        # On essaie d'accéder à un fichier système Windows ou Linux
        target = "C:/Windows/System32/drivers/etc/hosts" if Path("C:/").exists() else "/etc/hosts"

        # S'il existe, ça doit être ValueError (Accès interdit).
        # S'il n'existe pas (CI/CD), FileNotFoundError.
        if Path(target).exists():
            with pytest.raises(ValueError):  # N'est pas dans DATA_DIR ou TEMP
                pipeline._validate_path(target)
        else:
            with pytest.raises(FileNotFoundError):
                pipeline._validate_path(target)

    def test_reject_nonexistent_file(self, pipeline):
        """Test rejet d'un fichier qui n'existe pas."""
        fake_path = str(Path(tempfile.gettempdir()) / "ghost_file.txt")
        with pytest.raises(FileNotFoundError):
            pipeline._validate_path(fake_path)

    # ========================================
    # TESTS EXTENSIONS
    # ========================================

    def test_extension_validation(self, pipeline, valid_temp_file):
        """Test l'ingestion avec un fichier supporté."""
        # On mock les loaders pour ne pas faire de vrai parsing
        with patch("src.core.rag.ingestion.TextLoader") as mock_loader:
            mock_doc = MagicMock()
            mock_doc.page_content = "content"
            mock_doc.metadata = {}
            mock_loader.return_value.load.return_value = [mock_doc]

            docs = pipeline.process_file(valid_temp_file, "test.txt")
            assert len(docs) > 0

    def test_reject_bad_extension(self, pipeline):
        """Test rejet extension non supportée via process_file."""
        # Création d'un .exe
        with tempfile.NamedTemporaryFile(mode="w", suffix=".exe", delete=False) as f:
            f.write("fake binary")
            exe_path = f.name

        try:
            # process_file retourne une liste vide et log un warning pour les extensions non supportées
            docs = pipeline.process_file(exe_path, "malware.exe")
            assert len(docs) == 0
        finally:
            Path(exe_path).unlink(missing_ok=True)
