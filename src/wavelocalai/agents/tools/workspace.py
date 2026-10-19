"""Dossier de travail des agents : la seule racine que leurs outils lisent et écrivent (story 6.2).

« Sans chemin libre » : un outil ne reçoit jamais un chemin du disque, seulement un nom relatif à
cette racine fixe (`<données>/agent_work`). `Workspace` résout puis vérifie chaque nom : pas de chemin
absolu, de lecteur, de flux de données Windows (`:`), de `..`, de composant lié (lien symbolique ou
jonction) ni de sortie de la racine une fois le chemin résolu. Les fichiers produits sont à plat dans
la racine (un seul niveau) et servis par `GET /api/outputs/{name}`, dont le nom passe par la même
validation. Une violation lève `WorkspaceError` : la boucle la publie comme un `tool_result` en échec.
"""

from __future__ import annotations

import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote

from wavelocalai.agents.tools.registry import ToolError

OUTPUTS_ROUTE = "/api/outputs/"
MAX_NAME_CHARS = 100
# Caractères refusés dans un nom : séparateurs, flux et caractères réservés de Windows, contrôles.
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
# Noms réservés de Windows (avec ou sans extension, espaces avant l'extension compris) : ouvrir
# `CON.txt` ouvre le périphérique. Les chiffres en exposant (`COM¹`) et `CONIN$`, `CONOUT$`, `CLOCK$`
# en font partie.
_RESERVED = re.compile(
    r"^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³]|conin\$|conout\$|clock\$)\s*(\..*)?$",
    re.IGNORECASE,
)
# Catégories Unicode refusées : contrôles, formats (bidi U+202E, largeur nulle), séparateurs de ligne.
# Sans ce refus, un nom à inversion bidi s'afficherait à l'envers au téléchargement.
_INVISIBLE = {"Cc", "Cf", "Zl", "Zp"}


class WorkspaceError(ToolError, ValueError):
    """Nom ou chemin refusé : le message (français) est ce que l'agent lit."""


def _bare(name: str) -> str:
    """Nom de fichier simple, ou `WorkspaceError`."""
    if not isinstance(name, str) or not name.strip():
        raise WorkspaceError("Nom de fichier vide.")
    name = unicodedata.normalize("NFC", name.strip())
    if len(name) > MAX_NAME_CHARS:
        raise WorkspaceError(f"Nom de fichier trop long (max {MAX_NAME_CHARS} caractères).")
    if _FORBIDDEN.search(name) or any(unicodedata.category(c) in _INVISIBLE for c in name):
        raise WorkspaceError(
            "Nom de fichier refusé : un nom simple suffit, sans dossier ni caractère spécial "
            '(pas de / \\ : * ? " < > |).'
        )
    if name in {".", ".."} or name.startswith(".") or name.endswith((".", " ")):
        raise WorkspaceError("Nom de fichier refusé : ni « .. », ni nom caché, ni point final.")
    if _RESERVED.match(name):
        raise WorkspaceError(f"Nom de fichier réservé par le système : {name}.")
    return name


def check_output_name(name: str) -> str:
    """Nom valide d'un fichier produit (route `/api/outputs/{name}` comprise)."""
    return _bare(name)


class Workspace:
    """Racine fixe des fichiers d'agent ; `root` est résolue une fois, jamais modifiée."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # --- lecture -------------------------------------------------------------------------------

    def read_path(self, relative: str, *, max_bytes: int | None = None) -> Path:
        """Chemin d'un fichier **existant** de la racine désigné par un nom relatif (un sous-dossier
        est permis en lecture). Refus : chemin absolu ou à lecteur, `..`, composant lié, hors de la
        racine, dossier, fichier trop gros."""
        parts = self._relative_parts(relative)
        base = self._base()
        current = base
        for part in parts:
            current = current / part
            if current.is_symlink() or _is_junction(current):
                raise WorkspaceError(
                    "Chemin refusé : les liens symboliques et jonctions ne sont pas suivis."
                )
        try:
            resolved = current.resolve(strict=True)
        except (FileNotFoundError, OSError):
            raise WorkspaceError(
                f"Fichier non trouvé dans le dossier de travail : {relative}"
            ) from None
        if not _inside(resolved, base):
            raise WorkspaceError("Chemin refusé : il sort du dossier de travail.")
        if not resolved.is_file():
            raise WorkspaceError(f"Ce n'est pas un fichier : {relative}")
        if max_bytes is not None and resolved.stat().st_size > max_bytes:
            raise WorkspaceError(
                f"Fichier trop volumineux (max {max_bytes // (1024 * 1024)} Mo) : {relative}"
            )
        return resolved

    # --- écriture ------------------------------------------------------------------------------

    def output_path(self, name: str | None, *, stem: str, extension: str, stamp: str) -> Path:
        """Chemin d'un fichier à produire, **à plat** dans la racine. `name` absent : `<stem>_<stamp>`.
        L'extension `extension` (avec son point) est ajoutée si elle manque. Le dossier est créé ici,
        et un fichier du même nom qui serait un lien est refusé."""
        if name is None or not str(name).strip():
            clean = f"{stem}_{stamp}{extension}"
        else:
            clean = _bare(name)
            if not clean.lower().endswith(extension):
                clean += extension
            clean = _bare(clean)
        base = self._base(create=True)
        target = base / clean
        if target.is_symlink() or _is_junction(target):
            raise WorkspaceError("Chemin refusé : le fichier existant est un lien.")
        if target.exists() and not target.is_file():
            raise WorkspaceError(f"Ce nom désigne un dossier : {clean}")
        return target

    def served_path(self, name: str) -> Path | None:
        """Fichier produit rendu par `GET /api/outputs/{name}`, ou `None` s'il n'existe pas. Un nom
        invalide lève `WorkspaceError` ; un lien, un dossier ou une sortie de la racine rendent `None`.
        """
        clean = _bare(name)
        if not self.root.is_dir():
            return None
        base = self._base()
        target = base / clean
        if target.is_symlink() or _is_junction(target) or not target.is_file():
            return None
        resolved = target.resolve()
        return resolved if resolved.parent == base else None

    def artifact_url(self, path: Path) -> str:
        return OUTPUTS_ROUTE + quote(path.name, safe="")

    # --- internes ------------------------------------------------------------------------------

    def _base(self, *, create: bool = False) -> Path:
        if create:
            self.root.mkdir(parents=True, exist_ok=True)
        return self.root.resolve()

    @staticmethod
    def _relative_parts(relative: str) -> list[str]:
        if not isinstance(relative, str) or not relative.strip():
            raise WorkspaceError("Chemin vide : donnez le nom d'un fichier du dossier de travail.")
        text = relative.strip()
        if "\x00" in text:
            raise WorkspaceError("Chemin refusé : caractère nul.")
        windows, posix = PureWindowsPath(text), PurePosixPath(text)
        if windows.is_absolute() or posix.is_absolute() or windows.drive or text[:1] in "/\\~":
            raise WorkspaceError(
                "Chemin refusé : seul un nom relatif au dossier de travail est accepté "
                "(pas de chemin absolu)."
            )
        parts = [part for part in re.split(r"[\\/]+", text) if part not in ("", ".")]
        if not parts:
            raise WorkspaceError("Chemin vide : donnez le nom d'un fichier du dossier de travail.")
        if any(part == ".." for part in parts):
            raise WorkspaceError("Chemin refusé : « .. » n'est pas permis.")
        for part in parts:
            if (
                ":" in part
                or _RESERVED.match(part)
                or part.endswith((".", " "))
                or any(unicodedata.category(c) in _INVISIBLE for c in part)
            ):
                raise WorkspaceError(f"Chemin refusé : composant non valide « {part} ».")
        return parts


def _inside(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _is_junction(path: Path) -> bool:
    """Jonction Windows. `Path.is_junction` n'existe qu'à partir de Python 3.12 ; avant, la balise
    de point de montage de `lstat` (Windows seulement) dit la même chose."""
    checker = getattr(path, "is_junction", None)
    if checker is not None:
        return bool(checker())
    try:
        tag = getattr(path.lstat(), "st_reparse_tag", 0)
    except OSError:
        return False
    return tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", -1)
