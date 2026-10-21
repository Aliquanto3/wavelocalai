"""Vue des réglages de la base documentaire : `embedding_models` et le dernier recours `fallback_model`
(story 9.4) qui fait apparaître le modèle `fake` des tests quand aucun embedding réel n'est listé.
"""

from __future__ import annotations

import pytest

from wavelocalai.config import Settings
from wavelocalai.rag.manage import offline_settings_view


@pytest.mark.asyncio
async def test_no_registry_and_no_fallback_gives_an_empty_list():
    body = await offline_settings_view(Settings(), None, None)
    assert body["embedding_models"] == []


@pytest.mark.asyncio
async def test_the_fallback_model_fills_the_list_when_nothing_else_is_installed():
    body = await offline_settings_view(Settings(), None, None, fallback_model="fake-embed:16")
    assert body["embedding_models"] == [{"tag": "fake-embed:16", "name": "fake-embed:16"}]
