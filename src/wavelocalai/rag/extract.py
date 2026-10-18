"""Lecture d'un fichier importé : validation du chemin, puis texte par page (PDF) ou d'un bloc.

`validate_path` est copiée de la v1 (`IngestionPipeline._validate_path`, jamais importée, AD-2) et
adaptée : les dossiers autorisés sont passés en argument, et les refus sont des `IngestError` à
raison lisible. `pypdf` et `docx` ne sont importés que dans la fonction qui s'en sert (AD-4,
AD-21). Ces fonctions sont synchrones : le service les lance dans le pool de threads (AD-14).

Une `IngestError.reason` est une expression en français, sans point final : l'écran écrit « Le
fichier n'a pas pu être indexé : <raison>. »
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("wavelocalai.rag")

SUPPORTED_SUFFIXES = (".pdf", ".txt", ".md", ".docx")


class IngestError(Exception):
    """Un fichier ne peut pas être indexé ; `reason` est affichée, `technical` replié."""

    def __init__(self, reason: str, technical: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.technical = technical


@dataclass(frozen=True)
class Page:
    """Texte d'une page (PDF) ; `number` est nul pour un format sans page."""

    number: int | None
    text: str


def validate_path(file_path: str | Path, allowed_dirs: Iterable[Path] = ()) -> Path:
    """Chemin absolu d'un fichier existant, à l'intérieur du dossier temporaire du système ou de
    `allowed_dirs` (le dossier de données) seulement ; sinon `IngestError`."""
    path = Path(file_path).resolve()
    if not path.exists():
        raise IngestError("le fichier reçu a disparu avant son indexation", f"introuvable : {path}")
    if not path.is_file():
        raise IngestError("ce n'est pas un fichier", f"pas un fichier : {path}")
    roots = [Path(tempfile.gettempdir()).resolve(), *(Path(d).resolve() for d in allowed_dirs)]
    # `is_relative_to` résiste aux liens symboliques et aux différences de montage.
    if not any(path.is_relative_to(root) for root in roots):
        logger.warning("Accès refusé à un fichier hors des dossiers autorisés : %s", path)
        raise IngestError("le fichier est hors des dossiers autorisés", f"refusé : {path}")
    return path


def clean_text(text: str) -> str:
    """Texte sans caractère nul (SQLite le tronquerait) ni fin de ligne Windows."""
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")


def extract_pages(path: Path, suffix: str | None = None) -> list[Page]:
    """Texte du fichier, page par page pour un PDF. `IngestError` si le format est refusé, si le
    fichier est protégé, illisible ou sans texte."""
    suffix = (suffix or path.suffix).lower()
    if suffix == ".pdf":
        pages = _read_pdf(path)
    elif suffix == ".docx":
        pages = [Page(None, _read_docx(path))]
    elif suffix in (".txt", ".md"):
        pages = [Page(None, _read_text(path))]
    else:
        shown = suffix or "sans extension"
        raise IngestError(f"le format {shown} n'est pas pris en charge (PDF, TXT, MD ou DOCX)")
    pages = [Page(p.number, clean_text(p.text)) for p in pages]
    if not any(p.text.strip() for p in pages):
        if suffix == ".pdf":
            raise IngestError("le PDF ne contient aucun texte extractible (vide ou numérisé)")
        raise IngestError("le fichier est vide")
    return pages


def _read_pdf(path: Path) -> list[Page]:
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, PyPdfError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")  # mot de passe vide : 0 si le PDF en exige un
            except DependencyError as exc:
                raise IngestError(
                    "le PDF est chiffré et ce poste ne sait pas le déchiffrer", repr(exc)
                ) from exc
            if not unlocked:
                raise IngestError("le PDF est protégé par un mot de passe")
        return [Page(i, page.extract_text() or "") for i, page in enumerate(reader.pages, 1)]
    except IngestError:
        raise
    except (PyPdfError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        raise IngestError("le PDF est illisible ou endommagé", repr(exc)) from exc


def _read_docx(path: Path) -> str:
    from docx import Document

    try:
        document = Document(str(path))
        blocks = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                blocks.append(" | ".join(cell for cell in cells if cell))
    except Exception as exc:  # noqa: BLE001 - python-docx lève des types variés selon l'atteinte
        raise IngestError(
            "le document Word est illisible (chiffré, protégé ou endommagé)", repr(exc)
        ) from exc
    return "\n".join(block for block in blocks if block.strip())


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError("l'encodage du texte n'est pas reconnu (UTF-8 attendu)")
