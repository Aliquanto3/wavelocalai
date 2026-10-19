"""Version unique du dépôt (AGENTS.md) : `pyproject.toml`, `uv.lock` et `CITATION.cff` la disent
tous trois, et c'est une préversion `2.0.0aN` tant que la v2 n'est pas publiée (story 4.9)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRERELEASE = re.compile(r"2\.0\.0(a\d+|\.dev0)")


def pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def lock_version() -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return next(pkg["version"] for pkg in lock["package"] if pkg["name"] == "wavelocalai")


def citation_version() -> str:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)\s*$", text, re.MULTILINE)
    assert match, "CITATION.cff sans champ version"
    return match.group(1).strip("\"'")


def test_the_three_files_say_the_same_version():
    assert pyproject_version() == lock_version() == citation_version()


def test_the_version_is_a_v2_prerelease():
    assert PRERELEASE.fullmatch(pyproject_version()), pyproject_version()
