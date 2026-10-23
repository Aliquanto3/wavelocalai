"""
Les SDK cloud (anthropic, openai) ne sont importés qu'au premier client.

Usage: python -m pytest tests/unit/test_cloud_lazy_imports.py -q
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_providers_import_does_not_load_cloud_sdks():
    """`import src.core.providers` ne charge ni anthropic ni openai, même installés."""
    result = _run(
        "import sys\n"
        "import src.core.providers\n"
        "loaded = [m for m in ('anthropic', 'openai') if m in sys.modules]\n"
        "assert not loaded, loaded\n"
    )
    assert result.returncode == 0, result.stderr[-800:]


def test_provider_without_key_never_imports_sdk():
    """Sans clé, le provider se déclare indisponible sans importer le SDK."""
    result = _run(
        "import sys\n"
        "from src.core.providers import AnthropicProvider, OpenAIProvider\n"
        "from src.core.providers import anthropic_provider, openai_provider\n"
        "anthropic_provider.ANTHROPIC_API_KEY = ''\n"  # clé éventuelle du .env du poste
        "openai_provider.OPENAI_API_KEY = ''\n"
        "assert not AnthropicProvider(api_key='').is_available\n"
        "assert not OpenAIProvider(api_key='').is_available\n"
        "loaded = [m for m in ('anthropic', 'openai') if m in sys.modules]\n"
        "assert not loaded, loaded\n"
    )
    assert result.returncode == 0, result.stderr[-800:]


@pytest.mark.parametrize(
    ("module_name", "sdk"),
    [("anthropic_provider", "anthropic"), ("openai_provider", "openai")],
)
def test_client_class_loaded_on_first_use(module_name, sdk):
    """Le premier client importe le SDK, les suivants réutilisent la classe."""
    pytest.importorskip(sdk)
    result = _run(
        "import sys\n"
        f"from src.core.providers import {module_name} as mod\n"
        f"assert '{sdk}' not in sys.modules\n"
        "first = mod._async_client_class()\n"
        f"assert '{sdk}' in sys.modules\n"
        "assert mod._async_client_class() is first\n"
    )
    assert result.returncode == 0, result.stderr[-800:]
