"""Exports versionnés en liste blanche (AD-6) : tout ``benchmarks/quality/`` est parcouru.

Seuls les fichiers dont le chemin figure dans ``ALLOWED`` s'écrivent sous ``benchmarks/quality/``
(les stories suivantes y ajoutent les leurs) ; chaque ligne d'un index de jeu valide le schéma
fermé ``qb.set_index/1``, et aucune ligne privée ne porte ``prompt_hash`` ni ``target_hash``.
"""

from __future__ import annotations

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
# Chemins permis (relatifs à benchmarks/quality/) → schéma de chaque ligne.
ALLOWED = {re.compile(r"sets/[A-Za-z0-9][A-Za-z0-9._@-]*/index\.jsonl"): "qb.set_index/1"}
PUBLIC_ONLY = ("prompt_hash", "target_hash")


def export_problems(root: Path) -> list[str]:
    """Défauts de l'arborescence d'exports ``root`` (liste vide : conforme)."""
    problems = []
    if not root.exists():
        return problems
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        schema = next((s for pattern, s in ALLOWED.items() if pattern.fullmatch(relative)), None)
        if schema is None:
            problems.append(f"{relative} : fichier hors liste blanche")
            continue
        for line_no, row in enumerate(read_jsonl(path), start=1):
            try:
                if validate(row) != schema:
                    problems.append(f"{relative}:{line_no} : schéma {row.get('schema')}")
            except ValueError as error:
                problems.append(f"{relative}:{line_no} : {error}")
                continue
            if row["private"] and any(field in row for field in PUBLIC_ONLY):
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
