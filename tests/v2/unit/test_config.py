"""`Settings` : chargement unique (toml puis .env), et aucun `os.getenv` hors de `config.py`."""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from wavelocalai.config import DEFAULT_TOML, ConfigError, load_settings

from ..conftest import make_settings

SRC = Path(__file__).resolve().parents[3] / "src" / "wavelocalai"


def test_versioned_toml_gives_the_documented_defaults():
    settings = load_settings(DEFAULT_TOML, env_file=Path("absent.env"), environ={})
    assert settings.server.port == 8502
    assert settings.ollama.host == "http://127.0.0.1:11434"  # pas localhost (IPv6)
    assert settings.ollama.probe_timeout_s == 1.0
    assert settings.ollama.probe_cache_s == 5.0
    assert (settings.carbon.country_iso, settings.carbon.pue) == ("FRA", 1.1)
    assert settings.delays.approval_expiry_s == 600.0
    assert settings.data_dir == DEFAULT_TOML.parent / "data"


def test_toml_then_env_then_overrides(tmp_path):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text("[server]\nport = 9100\n[carbon]\npue = 1.4\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-test-1234567890\nWAVELOCALAI_PORT=9200\n", encoding="utf-8")

    from_env = load_settings(toml, env, environ={})
    assert from_env.server.port == 9200  # .env prime sur le .toml
    assert from_env.carbon.pue == 1.4
    assert from_env.api_keys["openai"].get_secret_value() == "sk-test-1234567890"

    process = load_settings(toml, env, environ={"WAVELOCALAI_PORT": "9300"})
    assert process.server.port == 9300  # l'environnement prime sur .env

    forced = load_settings(toml, env, environ={}, overrides={"server": {"port": 9400}})
    assert forced.server.port == 9400  # surcharge explicite (ligne de commande)


def test_relative_data_dir_follows_the_toml(tmp_path):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text('[data]\ndir = "donnees"\n', encoding="utf-8")
    settings = load_settings(toml, tmp_path / "absent.env", environ={})
    assert settings.data_dir == (tmp_path / "donnees").resolve()


def test_cloud_providers_read_from_settings_without_leaking_keys(tmp_path):
    settings = make_settings(
        tmp_path, environ={"GROQ_API_KEY": "gsk_secret_value_123", "MISTRAL_API_KEY": " "}
    )
    providers = {p["id"]: p["configured"] for p in settings.cloud_providers()}
    assert providers == {"openai": False, "groq": True, "anthropic": False, "mistral": False}
    assert "gsk_secret_value_123" not in repr(settings)  # SecretStr


@pytest.mark.parametrize(
    "content",
    [
        "[server\nport = 1",
        "[server]\nport = 70000",
        "[serveur]\nport = 1",
        "[ollama]\nprobe_timeout_s = 5",
    ],
)
def test_invalid_settings_are_refused_in_french(tmp_path, content):
    toml = tmp_path / "wavelocalai.toml"
    toml.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(toml, tmp_path / "absent.env", environ={})


def test_settings_are_immutable(settings):
    with pytest.raises(Exception, match="frozen"):
        settings.server = None  # type: ignore[misc]


# --- Aucun os.getenv hors de config.py (AST) ---------------------------------------------------


def find_env_reads(root: Path) -> list[str]:
    """Lectures de l'environnement hors de `config.py` : `getenv`, `environ.get`, `environ[...]`."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.relative_to(root).as_posix() == "config.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            where = f"{path.relative_to(root).as_posix()}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.Attribute) and node.attr in {"getenv", "getenvb"}:
                found.append(f"{where} {node.attr}")
            elif isinstance(node, ast.ImportFrom) and node.module == "os":
                found.extend(
                    f"{where} from os import {a.name}"
                    for a in node.names
                    if a.name in {"getenv", "environ"}
                )
            elif (
                isinstance(node, ast.Attribute)
                and node.attr in {"get", "pop", "copy", "items", "keys", "values"}
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "environ"
            ):
                found.append(f"{where} environ.{node.attr}")
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "environ"
                and isinstance(node.ctx, ast.Load)
            ):
                found.append(f"{where} environ[...]")
    return found


def test_no_getenv_outside_config():
    assert find_env_reads(SRC) == []


@pytest.mark.parametrize(
    "code",
    [
        "import os\nx = os.getenv('A')\n",
        "import os\nx = os.environ.get('A')\n",
        "import os\nx = os.environ['A']\n",
        "from os import getenv\n",
    ],
)
def test_env_read_is_detected_outside_config(tmp_path, code):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "trap.py").write_text(textwrap.dedent(code), encoding="utf-8")
    (tmp_path / "config.py").write_text("import os\nx = os.getenv('OK')\n", encoding="utf-8")
    assert find_env_reads(tmp_path)


def test_the_self_rag_bound_is_in_the_toml_and_stays_between_one_and_five(tmp_path):
    assert (
        load_settings(
            DEFAULT_TOML, env_file=Path("absent.env"), environ={}
        ).rag.self_rag_max_iterations
        == 2
    )
    for bad in (0, 6):
        with pytest.raises(ConfigError):
            make_settings(tmp_path, rag={"self_rag_max_iterations": bad})


def test_the_reranker_model_is_in_the_toml_and_cannot_be_empty(tmp_path):
    rag = load_settings(DEFAULT_TOML, env_file=Path("absent.env"), environ={}).rag
    assert rag.reranker_model == "jinaai/jina-reranker-v2-base-multilingual"
    with pytest.raises(ConfigError):
        make_settings(tmp_path, rag={"reranker_model": ""})
