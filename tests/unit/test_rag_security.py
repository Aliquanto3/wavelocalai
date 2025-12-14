""" "
Tests de sécurité pour le RAG Engine (Path Traversal).
Usage: pytest tests/unit/test_rag_security.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import DATA_DIR
from src.core.rag_engine import RAGEngine


class TestRAGSecurity:
    """Tests de sécurité du moteur RAG."""

    @pytest.fixture
    def mock_dependencies(self):
        """
        Mock les composants lourds (Embeddings, Chroma) pour éviter
        de charger les modèles ML lors des tests unitaires de sécurité.
        """
        with (
            patch("src.core.rag_engine.HuggingFaceEmbeddings") as mock_embed,
            patch("src.core.rag_engine.Chroma") as mock_chroma,
        ):

            # On configure les mocks pour qu'ils ne fassent rien
            mock_embed.return_value = MagicMock()
            mock_chroma.return_value = MagicMock()

            yield {"embed": mock_embed, "chroma": mock_chroma}

    @pytest.fixture
    def rag_engine(self, mock_dependencies):
        """Fixture : Instance RAG légère (mockée) pour les tests."""
        # Les mocks sont actifs grâce à la fixture mock_dependencies
        return RAGEngine(collection_name="test_security")

    @pytest.fixture
    def valid_temp_file(self):
        """Crée un fichier texte valide dans le dossier temp."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test content for security validation.")
            temp_path = f.name

        yield temp_path

        # Cleanup
        Path(temp_path).unlink(missing_ok=True)

    # ========================================
    # TESTS VALIDES (Chemins autorisés)
    # ========================================

    def test_validation_temp_file(self, rag_engine, valid_temp_file):
        """Test qu'un fichier dans TEMP est accepté."""
        validated_path = rag_engine._validate_file_path(valid_temp_file)
        assert validated_path.exists()
        assert validated_path.is_file()

    def test_validation_data_dir_file(self, rag_engine, tmp_path):
        """Test qu'un fichier dans DATA_DIR est accepté."""
        # Crée un fichier temporaire dans DATA_DIR
        test_file = DATA_DIR / "test_rag_security.txt"
        test_file.write_text("Test content in DATA_DIR")

        try:
            validated_path = rag_engine._validate_file_path(str(test_file))
            assert validated_path.exists()
        finally:
            test_file.unlink(missing_ok=True)

    def test_ingest_valid_file(self, rag_engine, valid_temp_file):
        """Test ingestion d'un fichier valide."""
        # On doit mocker le loader car on ne teste pas le parsing PDF/TXT ici
        with patch("src.core.rag_engine.TextLoader") as mock_loader:
            mock_doc = MagicMock()
            mock_doc.page_content = "content"
            mock_doc.metadata = {}
            mock_loader.return_value.load.return_value = [mock_doc]

            chunks = rag_engine.ingest_file(valid_temp_file, "test.txt")

            # On vérifie juste que ça n'a pas crashé et appelé le vector store
            assert chunks >= 0
            rag_engine.vector_store.add_documents.assert_called()

    # ========================================
    # TESTS DE SÉCURITÉ (Path Traversal)
    # ========================================

    def test_reject_path_traversal_simple(self, rag_engine):
        """Test rejet d'un path traversal simple."""
        malicious_path = "../../../../etc/passwd"

        with pytest.raises(ValueError, match="Accès refusé"):
            rag_engine._validate_file_path(malicious_path)

    def test_reject_path_traversal_windows(self, rag_engine):
        """Test rejet d'un path traversal Windows."""
        malicious_path = r"..\..\..\..\Windows\System32\config\SAM"

        with pytest.raises(ValueError, match="Accès refusé"):
            rag_engine._validate_file_path(malicious_path)

    def test_reject_absolute_path_outside(self, rag_engine):
        """Test rejet d'un chemin absolu en dehors des zones autorisées."""
        if Path("/etc/passwd").exists():  # Linux/Mac
            with pytest.raises(ValueError, match="Accès refusé"):
                rag_engine._validate_file_path("/etc/passwd")
        elif Path("C:/Windows/System.ini").exists():  # Windows
            with pytest.raises(ValueError, match="Accès refusé"):
                rag_engine._validate_file_path("C:/Windows/System.ini")

    def test_reject_nonexistent_file(self, rag_engine):
        """Test rejet d'un fichier qui n'existe pas."""
        fake_path = str(Path(tempfile.gettempdir()) / "ce_fichier_nexiste_pas.txt")

        with pytest.raises(FileNotFoundError):
            rag_engine._validate_file_path(fake_path)

    def test_reject_directory_instead_of_file(self, rag_engine):
        """Test rejet d'un dossier au lieu d'un fichier."""
        with pytest.raises(ValueError, match="ne pointe pas vers un fichier"):
            rag_engine._validate_file_path(tempfile.gettempdir())

    def test_reject_symlink_outside_allowed(self, rag_engine, tmp_path):
        """Test rejet d'un symlink pointant vers une zone interdite."""
        # Crée un symlink dans TEMP qui pointe vers /etc
        if not Path("/etc").exists():
            pytest.skip("Test Unix uniquement")

        symlink_path = tmp_path / "malicious_link"
        try:
            symlink_path.symlink_to("/etc/passwd")

            with pytest.raises(ValueError, match="Accès refusé"):
                rag_engine._validate_file_path(str(symlink_path))
        except OSError:
            pytest.skip("Symlink non supporté sur ce système")
        finally:
            symlink_path.unlink(missing_ok=True)

    # ========================================
    # TESTS DE ROBUSTESSE
    # ========================================

    def test_normalize_path_with_dots(self, rag_engine, valid_temp_file):
        """Test que les chemins avec './' sont normalisés."""
        # Ajoute des ./././ au chemin
        weird_path = "./" + valid_temp_file
        validated_path = rag_engine._validate_file_path(weird_path)
        assert validated_path.is_absolute()

    def test_reject_empty_path(self, rag_engine):
        """Test rejet d'un chemin vide."""
        with pytest.raises((ValueError, FileNotFoundError)):
            rag_engine._validate_file_path("")

    def test_extension_validation_on_ingest(self, rag_engine, tmp_path):
        """Test que seuls PDF/TXT/MD sont acceptés."""
        # Crée un fichier .exe malveillant dans TEMP
        fake_exe = Path(tempfile.gettempdir()) / "malicious.exe"
        fake_exe.write_text("fake executable")

        try:
            with pytest.raises(ValueError, match="Format non supporté"):
                rag_engine.ingest_file(str(fake_exe), "malicious.exe")
        finally:
            fake_exe.unlink(missing_ok=True)
