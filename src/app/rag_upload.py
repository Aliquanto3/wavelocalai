"""
Import de documents dans l'assistant documentaire, sans streamlit.

Chaque fichier téléversé (objet exposant `name` et `getvalue()`, comme `UploadedFile`) est
écrit dans un fichier temporaire du dossier temporaire système, seul emplacement accepté avec
`data/` par `IngestionPipeline._validate_path`, puis indexé par `RAGEngine.ingest_file`. Le
fichier temporaire est supprimé même en cas d'erreur. Un échec n'interrompt pas les autres
fichiers ; le résultat agrégé porte le compte réel d'extraits ajoutés.

Les messages sont destinés à un rendu Markdown (st.success, st.error, st.status) : le nom de
fichier y est échappé.
"""

import logging
import os
import re
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.app.formatting import pluralize

logger = logging.getLogger(__name__)

# Raisons affichées à l'utilisateur (la trace technique va dans `detail`).
# Fichier lu sans erreur, mais sans texte : aucun extrait produit.
REASON_NO_TEXT = "aucun texte extrait"
# Un document du même nom est déjà dans la collection : le réindexer doublerait ses extraits.
REASON_DUPLICATE = "déjà présent dans la base documentaire"
# Toute exception : lecture (dépendance manquante, fichier endommagé, encodage), écriture
# temporaire, validation du chemin, calcul des embeddings, Chroma.
REASON_FAILED = "lecture ou indexation impossible"
# Ce que l'utilisateur peut faire, selon la raison.
ADVICE = {
    REASON_NO_TEXT: "Vérifiez que le document contient du texte sélectionnable.",
    REASON_DUPLICATE: "Ses extraits sont déjà interrogeables.",
    REASON_FAILED: "Vérifiez que le fichier s'ouvre, puis importez-le de nouveau.",
}

# Caractères actifs en Markdown en ligne (CommonMark et directives Streamlit « :red[…] »).
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()<>#+!|~$])")


def escape_markdown(text: str) -> str:
    """Échappe les caractères Markdown d'un texte libre (nom de fichier) : « a*b » → « a\\*b »."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


class UploadedDocument(Protocol):
    """Sous-ensemble de `streamlit.runtime.uploaded_file_manager.UploadedFile` utilisé ici."""

    name: str

    def getvalue(self) -> bytes: ...


@dataclass(frozen=True)
class FileResult:
    """Résultat de l'indexation d'un fichier : extraits ajoutés, ou raison de l'échec."""

    name: str
    added: int = 0
    reason: str | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None

    def summary(self) -> str:
        """« 12 extraits ajoutés » ou la raison de l'échec (« aucun texte extrait »)."""
        if self.ok:
            return pluralize(self.added, "extrait ajouté", "extraits ajoutés")
        return self.reason

    def error_message(self) -> str:
        """« « note.txt » n'a pas été indexé : aucun texte extrait. Vérifiez… » (Markdown)."""
        advice = ADVICE.get(self.reason, "")
        message = f"« {escape_markdown(self.name)} » n'a pas été indexé : {self.reason}."
        return f"{message} {advice}" if advice else message


@dataclass
class IngestReport:
    """Agrégat des résultats d'un import de plusieurs fichiers."""

    results: list[FileResult] = field(default_factory=list)

    def add(self, result: FileResult) -> None:
        self.results.append(result)

    @property
    def added(self) -> int:
        return sum(r.added for r in self.results if r.ok)

    @property
    def succeeded(self) -> list[FileResult]:
        return [r for r in self.results if r.ok]

    @property
    def failures(self) -> list[FileResult]:
        return [r for r in self.results if not r.ok]

    def success_message(self) -> str | None:
        """« 12 extraits ajoutés depuis 1 document. », ou None si aucun fichier n'a abouti."""
        if not self.succeeded:
            return None
        added = pluralize(self.added, "extrait ajouté", "extraits ajoutés")
        return f"{added} depuis {pluralize(len(self.succeeded), 'document')}."


def ingest_uploaded_file(engine, uploaded: UploadedDocument) -> FileResult:
    """Indexe un fichier téléversé via un fichier temporaire, supprimé dans tous les cas.

    Un document dont le nom est déjà une source de la collection n'est pas réindexé."""
    name = uploaded.name
    tmp_path = None
    try:
        if name in engine.get_stats().get("sources", []):
            return FileResult(name, reason=REASON_DUPLICATE)
        # Suffixe d'origine : IngestionPipeline choisit le loader d'après l'extension.
        with tempfile.NamedTemporaryFile(
            suffix=Path(name).suffix.lower(), dir=tempfile.gettempdir(), delete=False
        ) as tmp:
            tmp_path = tmp.name
            tmp.write(uploaded.getvalue())
        added = engine.ingest_file(tmp_path, name)
    except Exception as exc:
        logger.exception("Échec de l'indexation de %s", name)
        return FileResult(name, reason=REASON_FAILED, detail=f"{type(exc).__name__} : {exc}")
    finally:
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                logger.warning("Fichier temporaire non supprimé : %s", tmp_path)

    if not added:
        return FileResult(name, reason=REASON_NO_TEXT)
    return FileResult(name, added=added)


def ingest_uploaded_files(
    engine,
    files: Iterable[UploadedDocument],
    on_start: Callable[[str], None] | None = None,
    on_result: Callable[[FileResult, IngestReport], None] | None = None,
) -> IngestReport:
    """Indexe chaque fichier ; un échec n'empêche pas l'indexation des suivants.

    `on_start(nom)` est appelé avant chaque fichier, `on_result(résultat, rapport)` après,
    avec le rapport à jour : l'appelant peut suivre l'avancement et conserver le compte rendu
    partiel si l'exécution est interrompue.
    """
    report = IngestReport()
    for uploaded in files:
        if on_start is not None:
            on_start(uploaded.name)
        result = ingest_uploaded_file(engine, uploaded)
        report.add(result)
        if on_result is not None:
            on_result(result, report)
    return report
