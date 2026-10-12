"""Exports versionnés en liste blanche (AD-6) : tout ``benchmarks/quality/`` est parcouru.

Seuls les fichiers dont le chemin figure dans ``ALLOWED`` s'écrivent sous ``benchmarks/quality/``
(les stories suivantes y ajoutent les leurs) ; chaque ligne d'un JSONL et chaque document JSON
valide son schéma fermé (``qb.set_index/1``, ``qb.score/1``, ``qb.report/1``, ``qb.manifest/1``,
``qb.aa_reference/1``), aucune ligne privée d'un index ne porte ``prompt_hash`` ni
``target_hash``, et le rapport Markdown et les graphiques SVG (sans schéma) sont en UTF-8.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.quality_bench.common.canonical import canonical_bytes
from scripts.quality_bench.common.jsonl import read_jsonl
from scripts.quality_bench.common.schemas import validate
from scripts.quality_bench.questions.set_builder import assemble, index_rows

from .set_factories import set_v1, synthetic_candidates

ROOT = Path(__file__).resolve().parents[2]
EXPORTS = ROOT / "benchmarks" / "quality"
_ID = r"[A-Za-z0-9][A-Za-z0-9._@-]*"
# Dossier d'une campagne : jamais un dossier réservé (sets, references, calibration).
_CAMPAIGN = rf"(?!(?:sets|references|calibration)/){_ID}"
# Chemins permis (relatifs à benchmarks/quality/) → schéma de chaque ligne (.jsonl) ou du
# document (.json) ; ``None`` : texte sans schéma (.md, .svg).
ALLOWED = {
    re.compile(rf"sets/{_ID}/index\.jsonl"): "qb.set_index/1",
    re.compile(rf"{_CAMPAIGN}/scores/[A-Za-z0-9._-]+\.jsonl"): "qb.score/1",
    re.compile(rf"{_CAMPAIGN}/summary\.json"): "qb.report/1",
    re.compile(rf"{_CAMPAIGN}/manifest\.json"): "qb.manifest/1",
    re.compile(rf"{_CAMPAIGN}/report\.md"): None,
    re.compile(rf"{_CAMPAIGN}/charts/[A-Za-z0-9._-]+\.svg"): None,
    re.compile(r"references/aa-\d{4}-\d{2}-\d{2}\.json"): "qb.aa_reference/1",
}
PUBLIC_ONLY = ("prompt_hash", "target_hash")


def _records(path: Path) -> list:
    """Lignes d'un JSONL, ou le document JSON seul."""
    if path.suffix == ".jsonl":
        return read_jsonl(path)
    return [json.loads(path.read_text(encoding="utf-8"))]


def export_problems(root: Path) -> list[str]:
    """Défauts de l'arborescence d'exports ``root`` (liste vide : conforme)."""
    problems = []
    if not root.exists():
        return problems
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        matched = [s for pattern, s in ALLOWED.items() if pattern.fullmatch(relative)]
        if not matched:
            problems.append(f"{relative} : fichier hors liste blanche")
            continue
        schema = matched[0]
        if schema is None:
            try:
                path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                problems.append(f"{relative} : texte hors UTF-8")
            continue
        try:
            records = _records(path)
        except ValueError as error:
            problems.append(f"{relative} : illisible ({error})")
            continue
        for line_no, row in enumerate(records, start=1):
            try:
                if validate(row) != schema:
                    problems.append(f"{relative}:{line_no} : schéma {row.get('schema')}")
                    continue
            except ValueError as error:
                problems.append(f"{relative}:{line_no} : {error}")
                continue
            private = schema == "qb.set_index/1" and row["private"]
            if private and any(field in row for field in PUBLIC_ONLY):
                problems.append(f"{relative}:{line_no} : empreinte publique sur une ligne privée")
    return problems


def _write_index(root: Path, rows, name="set-test") -> Path:
    path = root / "sets" / name / "index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in rows))
    return path


@pytest.fixture(scope="module")
def synthetic_rows():
    config = set_v1()
    questions, _ = assemble(config, synthetic_candidates(config))
    return index_rows(questions)


def test_versioned_exports_follow_the_whitelist():
    assert export_problems(EXPORTS) == []


def test_synthetic_index_follows_the_whitelist(tmp_path, synthetic_rows):
    _write_index(tmp_path, synthetic_rows)
    assert export_problems(tmp_path) == []
    private = [row for row in synthetic_rows if row["private"]]
    assert private and all(not set(PUBLIC_ONLY) & set(row) for row in private)


def test_extra_field_fails(tmp_path, synthetic_rows):
    _write_index(tmp_path, [{**synthetic_rows[0], "messages": []}])
    assert export_problems(tmp_path)


def test_private_line_with_prompt_hash_fails(tmp_path, synthetic_rows):
    row = next(row for row in synthetic_rows if row["private"])
    _write_index(tmp_path, [{**row, "prompt_hash": "a" * 64, "target_hash": "b" * 64}])
    assert export_problems(tmp_path)


def test_public_line_without_target_hash_fails(tmp_path, synthetic_rows):
    row = next(row for row in synthetic_rows if not row["private"])
    _write_index(tmp_path, [{k: v for k, v in row.items() if k != "target_hash"}])
    assert export_problems(tmp_path)


def test_file_outside_the_whitelist_fails(tmp_path, synthetic_rows):
    _write_index(tmp_path, synthetic_rows[:1])
    (tmp_path / "sets" / "set-test" / "questions.jsonl").write_text("{}\n", encoding="utf-8")
    assert export_problems(tmp_path) == [
        "sets/set-test/questions.jsonl : fichier hors liste blanche"
    ]


# -- Exports d'une campagne (story 6) -------------------------------------------------------


@pytest.fixture
def report_root(tmp_path, monkeypatch):
    """Exports d'une campagne synthétique produits par ``report`` ; rend leur racine."""
    from scripts.quality_bench.__main__ import main
    from scripts.quality_bench.common import paths
    from scripts.quality_bench.common.logs import setup_logging

    from .report_factories import CAMPAIGN, aa_reference, make_campaign, write_aa_reference

    campaign = make_campaign(tmp_path, monkeypatch)
    entries = [
        {"tag": tag, "index": 10.0 + i, "status": "measured", "variant": "non_reasoning"}
        for i, tag in enumerate(campaign.models)
    ]
    write_aa_reference(aa_reference("2026-10-01", entries))
    try:
        assert main(["report", "--campaign", CAMPAIGN]) == 0
    finally:
        setup_logging("test", None)
    return paths.exports_root()


def test_report_exports_follow_the_whitelist(report_root):
    assert export_problems(report_root) == []
    names = {p.relative_to(report_root).as_posix() for p in report_root.rglob("*") if p.is_file()}
    assert "references/aa-2026-10-01.json" in names
    assert "report-test/summary.json" in names and "report-test/report.md" in names


def test_score_line_with_extra_field_fails(report_root):
    path = next((report_root / "report-test" / "scores").glob("*.jsonl"))
    rows = read_jsonl(path)
    rows[0]["question_id"] = "reasoning/var-math/0000"
    path.write_bytes(b"".join(canonical_bytes(row) + b"\n" for row in rows))
    assert export_problems(report_root)


def test_summary_with_extra_field_fails(report_root):
    path = report_root / "report-test" / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["questions"] = []
    path.write_bytes(canonical_bytes(summary))
    assert export_problems(report_root)


@pytest.mark.parametrize(
    "relative",
    [
        "report-test/notes.txt",
        "report-test/charts/graphique.png",
        "report-test/scores/m.json",
        "references/aa-2026-10.json",
        "sets/report-test/summary.json",
    ],
)
def test_campaign_file_outside_the_whitelist_fails(report_root, relative):
    path = report_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    assert export_problems(report_root) == [f"{relative} : fichier hors liste blanche"]
