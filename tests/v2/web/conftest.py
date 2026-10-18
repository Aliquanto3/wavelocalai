"""Client HTTP asynchrone sur l'app ASGI, cycle de vie compris (hub démarré), pour les flux SSE."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from wavelocalai.web.app import create_app

from ..conftest import TEST_PORT, make_settings

BASE = f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture
async def served(tmp_path) -> AsyncIterator[tuple[Any, httpx.AsyncClient]]:
    """(app, client) avec `WAVELOCALAI_TESTING=1` : route de test et modèle `fake` actifs."""
    app = create_app(make_settings(tmp_path, environ={"WAVELOCALAI_TESTING": "1"}))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
            yield app, client


def parse_sse(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Trames d'un flux : ([{id, data (enveloppe décodée), fields}], commentaires)."""
    frames: list[dict[str, Any]] = []
    comments: list[str] = []
    for block in text.split("\n\n"):
        fields: dict[str, list[str]] = {}
        for line in block.split("\n"):
            if not line:
                continue
            if line.startswith(":"):
                comments.append(line[1:].strip())
                continue
            name, _, value = line.partition(":")
            fields.setdefault(name, []).append(value.removeprefix(" "))
        if fields:
            frames.append(
                {
                    "id": fields.get("id", [None])[0],
                    "data": json.loads("\n".join(fields["data"])) if "data" in fields else None,
                    "fields": sorted(fields),
                }
            )
    return frames, comments
