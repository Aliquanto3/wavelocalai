"""Dossier de travail des agents : aucun chemin libre (story 6.2, AD-9).

Chaque évasion plausible (`..`, chemin absolu, lecteur, flux Windows, périphérique réservé, lien
symbolique, jonction) est refusée par `Workspace` avant tout accès au disque hors de la racine.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from wavelocalai.agents.tools import Workspace, WorkspaceError
from wavelocalai.agents.tools.workspace import check_output_name


@pytest.fixture
def space(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    (root / "ventes.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "sous").mkdir()
    (root / "sous" / "autre.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("hors de la racine", encoding="utf-8")
    return Workspace(root)


def test_a_file_of_the_root_and_of_a_subfolder_are_readable(space):
    assert space.read_path("ventes.csv").name == "ventes.csv"
    assert space.read_path("sous/autre.csv").name == "autre.csv"
    assert space.read_path("./sous\\autre.csv").name == "autre.csv"


@pytest.mark.parametrize(
    "name",
    [
        "../secret.txt",
        "..\\secret.txt",
        "sous/../../secret.txt",
        "sous/..\\..\\secret.txt",
        "..",
        "/etc/passwd",
        "\\Windows\\win.ini",
        "C:\\Windows\\win.ini",
        "C:/Windows/win.ini",
        "C:secret.txt",
        "\\\\serveur\\partage\\secret.txt",
        "//serveur/partage/secret.txt",
        "~/secret.txt",
        "ventes.csv:flux",
        "ventes.csv\x00.png",
        "NUL",
        "sous/CON.txt",
        "",
        "   ",
        "sous/",
    ],
)
def test_traversals_absolute_paths_and_system_names_are_refused_on_read(space, name):
    with pytest.raises(WorkspaceError):
        space.read_path(name)


def test_an_absolute_path_inside_the_root_is_still_refused(space):
    with pytest.raises(WorkspaceError, match="absolu"):
        space.read_path(str(space.root / "ventes.csv"))


def test_a_missing_file_a_folder_and_a_big_file_are_refused(space):
    with pytest.raises(WorkspaceError, match="non trouvé"):
        space.read_path("absent.csv")
    with pytest.raises(WorkspaceError, match="pas un fichier"):
        space.read_path("sous")
    with pytest.raises(WorkspaceError, match="volumineux"):
        space.read_path("ventes.csv", max_bytes=3)


def _symlink(link, target, *, directory=False):
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("les liens symboliques ne sont pas permis sur ce poste")


def test_a_symlink_to_a_file_outside_the_root_is_refused(space, tmp_path):
    _symlink(space.root / "lien.csv", tmp_path / "secret.txt")
    with pytest.raises(WorkspaceError, match="liens"):
        space.read_path("lien.csv")


def test_a_symlink_to_a_file_inside_the_root_is_refused_too(space):
    _symlink(space.root / "alias.csv", space.root / "ventes.csv")
    with pytest.raises(WorkspaceError, match="liens"):
        space.read_path("alias.csv")


def test_a_symlinked_folder_is_not_followed(space, tmp_path):
    _symlink(space.root / "dehors", tmp_path, directory=True)
    with pytest.raises(WorkspaceError, match="liens"):
        space.read_path("dehors/secret.txt")


@pytest.mark.skipif(sys.platform != "win32", reason="les jonctions n'existent que sous Windows")
def test_a_junction_to_the_outside_is_refused(space, tmp_path):
    junction = space.root / "jonction"
    made = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(tmp_path)],
        capture_output=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip("mklink /J n'est pas permis sur ce poste")
    with pytest.raises(WorkspaceError):
        space.read_path("jonction/secret.txt")


def test_an_output_is_written_flat_in_the_root_with_its_extension(space):
    path = space.output_path("rapport", stem="document", extension=".docx", stamp="20260101_000000")
    assert path == space.root.resolve() / "rapport.docx"
    named = space.output_path("x.DOCX", stem="document", extension=".docx", stamp="s")
    assert named.name == "x.DOCX"
    auto = space.output_path(None, stem="chart", extension=".png", stamp="20260101_000000")
    assert auto.name == "chart_20260101_000000.png"
    assert space.output_path("  ", stem="chart", extension=".png", stamp="t").name == "chart_t.png"


@pytest.mark.parametrize(
    "name",
    [
        "../evasion",
        "..\\evasion",
        "dossier/fichier",
        "/tmp/evasion",
        "C:\\evasion",
        "evasion:flux",
        "..",
        ".caché",
        "nul",
        "AUX.md",
        "fin.",
        "a" * 101,
        "a\nb",
    ],
)
def test_an_output_name_is_one_plain_name(space, name):
    with pytest.raises(WorkspaceError):
        space.output_path(name, stem="x", extension=".md", stamp="s")
    with pytest.raises(WorkspaceError):
        check_output_name(name)
    assert not (space.root.parent / "evasion").exists()


def test_an_output_cannot_replace_a_symlink_or_a_folder(space, tmp_path):
    _symlink(space.root / "lien.md", tmp_path / "secret.txt")
    with pytest.raises(WorkspaceError, match="lien"):
        space.output_path("lien", stem="x", extension=".md", stamp="s")
    (space.root / "dossier.md").mkdir()
    with pytest.raises(WorkspaceError, match="dossier"):
        space.output_path("dossier", stem="x", extension=".md", stamp="s")
    assert (tmp_path / "secret.txt").read_text(encoding="utf-8") == "hors de la racine"


def test_the_root_is_created_on_the_first_output_only(tmp_path):
    space = Workspace(tmp_path / "data" / "agent_work")
    assert not space.root.exists() and space.served_path("x.md") is None
    path = space.output_path("x", stem="r", extension=".md", stamp="s")
    assert space.root.is_dir() and path.parent == space.root.resolve()


def test_served_path_finds_a_flat_file_and_nothing_else(space, tmp_path):
    (space.root / "rapport.md").write_text("# R", encoding="utf-8")
    assert space.served_path("rapport.md").name == "rapport.md"
    assert space.served_path("absent.md") is None
    assert space.served_path("sous") is None  # un dossier
    with pytest.raises(WorkspaceError):
        space.served_path("../secret.txt")
    with pytest.raises(WorkspaceError):
        space.served_path("sous/autre.csv")
    _symlink(space.root / "lien.md", tmp_path / "secret.txt")
    assert space.served_path("lien.md") is None


def test_the_artifact_url_quotes_the_name(space):
    path = space.output_path("bilan été", stem="x", extension=".md", stamp="s")
    assert space.artifact_url(path) == "/api/outputs/bilan%20%C3%A9t%C3%A9.md"
