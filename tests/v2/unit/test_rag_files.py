"""Lecture des fichiers importés et découpe en extraits (story 4.1) : sans Ollama ni réseau."""

from __future__ import annotations

import pytest

from wavelocalai.rag.extract import IngestError, Page, extract_pages, validate_path
from wavelocalai.rag.split import split_pages, split_text
from wavelocalai.rag.staging import StagedFile, clean_name, stage_upload

from ..rag_files import make_blank_pdf, make_docx, make_encrypted_text_pdf, make_pdf

# --- extraction ---------------------------------------------------------------------------------


def _write(tmp_path, name, data: bytes | str):
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def test_a_pdf_gives_its_text_page_by_page(tmp_path):
    path = _write(tmp_path, "a.pdf", make_pdf(["Premiere page", "Seconde page"]))
    pages = extract_pages(path)
    assert [p.number for p in pages] == [1, 2]
    assert "Premiere page" in pages[0].text and "Seconde page" in pages[1].text


def test_a_docx_gives_paragraphs_and_table_cells(tmp_path):
    data = make_docx(["Titre", "Un paragraphe."], table=[["a", "b"], ["c", "d"]])
    pages = extract_pages(_write(tmp_path, "a.docx", data))
    assert [p.number for p in pages] == [None]
    assert "Un paragraphe." in pages[0].text and "a | b" in pages[0].text


@pytest.mark.parametrize("name", ["a.txt", "a.md"])
def test_text_files_are_read_as_utf8_then_windows_1252(tmp_path, name):
    assert extract_pages(_write(tmp_path, name, "Été à Paris\r\nligne 2"))[0].text == (
        "Été à Paris\nligne 2"
    )
    legacy = _write(tmp_path, "old_" + name, "Été".encode("cp1252"))
    assert extract_pages(legacy)[0].text == "Été"


def test_a_nul_character_never_reaches_the_text(tmp_path):
    assert extract_pages(_write(tmp_path, "a.txt", "a\x00b"))[0].text == "ab"


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("vide.txt", "  \n ", "vide"),
        ("vide.md", "", "vide"),
        ("blank.pdf", make_blank_pdf(), "aucun texte"),
        ("secret.pdf", make_encrypted_text_pdf(), "mot de passe"),
        ("junk.pdf", b"ceci n'est pas un pdf", "illisible"),
        ("junk.docx", b"ceci n'est pas un docx", "Word est illisible"),
        ("data.xlsx", b"PK", "xlsx n'est pas pris en charge"),
        ("noext", b"abc", "sans extension"),
        ("bin.txt", b"\x81\x8d\x8f\x90\x9d", "encodage"),
    ],
)
def test_an_unreadable_file_is_refused_with_a_readable_reason(tmp_path, name, data, expected):
    with pytest.raises(IngestError) as caught:
        extract_pages(_write(tmp_path, name, data))
    assert expected in caught.value.reason
    assert not caught.value.reason.endswith(".")  # l'écran ajoute le point final


def test_a_password_protected_pdf_with_blank_password_is_read(tmp_path):
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(["Visible text"]))))
    writer.encrypt("", owner_password="owner", algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    pages = extract_pages(_write(tmp_path, "open.pdf", buffer.getvalue()))
    assert "Visible text" in pages[0].text


# --- chemin autorisé (copié de la v1) -------------------------------------------------------------


def test_validate_path_accepts_the_temp_dir_and_the_given_data_dir(tmp_path, monkeypatch):
    import tempfile

    inside = tmp_path / "data"
    inside.mkdir()
    file = inside / "a.txt"
    file.write_text("x", encoding="utf-8")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "sys-tmp"))
    assert validate_path(file, [inside]) == file.resolve()
    with pytest.raises(IngestError, match="hors des dossiers autorisés"):
        validate_path(file, [])


def test_validate_path_refuses_a_missing_file_and_a_directory(tmp_path):
    with pytest.raises(IngestError, match="disparu"):
        validate_path(tmp_path / "absent.txt", [tmp_path])
    with pytest.raises(IngestError, match="pas un fichier"):
        validate_path(tmp_path, [tmp_path])


# --- découpe ------------------------------------------------------------------------------------


def test_chunks_stay_under_the_size_and_overlap(tmp_path):
    text = " ".join(f"mot{i:03d}" for i in range(400))
    chunks = split_text(text, size=200, overlap=40)
    assert len(chunks) > 5
    assert all(len(c) <= 200 for c in chunks)
    # le recouvrement : la fin d'un extrait se retrouve au début du suivant
    assert any(chunks[i][-10:] in chunks[i + 1] for i in range(len(chunks) - 1))
    covered = " ".join(chunks)
    assert all(f"mot{i:03d}" in covered for i in range(400))  # rien n'est perdu


def test_a_text_without_separator_is_cut_by_character():
    chunks = split_text("x" * 1000, size=300, overlap=0)
    assert [len(c) for c in chunks] == [300, 300, 300, 100]


def test_short_and_blank_texts():
    assert split_text("Court.", 800, 100) == ["Court."]
    assert split_text(" \n\n ", 800, 100) == []
    with pytest.raises(ValueError):
        split_text("x", size=100, overlap=100)


def test_paragraphs_are_cut_before_sentences():
    text = "Premier paragraphe court.\n\nSecond paragraphe court."
    assert split_text(text, size=30, overlap=0) == [
        "Premier paragraphe court.",
        "Second paragraphe court.",
    ]


def test_pages_are_split_apart_and_chunks_numbered_across_the_document():
    drafts = split_pages([Page(1, "a " * 300), Page(2, "b " * 300)], size=200, overlap=20)
    assert [d.position for d in drafts] == list(range(len(drafts)))
    pages = [d.page for d in drafts]
    assert pages == sorted(pages) and set(pages) == {1, 2}
    assert all(set(d.text.split()) == {"a" if d.page == 1 else "b"} for d in drafts)


# --- réception des fichiers -----------------------------------------------------------------------


class _Upload:
    def __init__(self, filename: str | None, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\moi\\rapport.pdf", "rapport.pdf"),
        ("a\x00b\n.txt", "ab.txt"),
        ("", "document"),
        (None, "document"),
        ("x" * 400 + ".md", ("x" * 400 + ".md")[:255]),
    ],
)
def test_a_file_name_loses_its_folders_and_control_characters(raw, clean):
    assert clean_name(raw) == clean


async def test_a_staged_file_has_a_neutral_disk_name_and_a_fingerprint(tmp_path):
    import hashlib

    staged = await stage_upload(_Upload("../Rapport secret.PDF", b"abc"), tmp_path, 3, 1000)
    assert staged == StagedFile(
        "Rapport secret.PDF", tmp_path / "0003.pdf", hashlib.sha256(b"abc").hexdigest(), 3
    )
    assert staged.path.read_bytes() == b"abc"


async def test_an_oversized_file_is_hashed_but_not_kept(tmp_path):
    import hashlib

    data = b"y" * (3 * 1024 * 1024 + 5)
    staged = await stage_upload(_Upload("gros.txt", data), tmp_path, 1, 1024 * 1024)
    assert staged.rejected == "le fichier dépasse 1 Mo"
    assert staged.size == len(data) and staged.fingerprint == hashlib.sha256(data).hexdigest()
    assert not staged.path.exists()


async def test_a_weird_extension_is_not_kept_on_disk(tmp_path):
    staged = await stage_upload(_Upload("a.p/../d f", b"x"), tmp_path, 1, 100)
    assert staged.path.name == "0001"
