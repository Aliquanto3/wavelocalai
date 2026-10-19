"""Modèles chargés en mémoire par Ollama (`GET /api/ps`), pour le flux système.

Lecture seule, délai court (1 s), jamais d'exception : Ollama arrêté ou muet donne `None`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

GIB = 1024**3


@dataclass(frozen=True)
class LoadedModel:
    tag: str
    size_gb: float  # mémoire occupée par le modèle chargé
    vram_gb: float  # dont la part en mémoire GPU

    def as_dict(self) -> dict[str, object]:
        return {"tag": self.tag, "size_gb": self.size_gb, "vram_gb": self.vram_gb}


def parse_ps(payload: object) -> list[LoadedModel]:
    """Modèles chargés d'une réponse `/api/ps` ; les entrées mal formées sont ignorées."""
    models = payload.get("models") if isinstance(payload, dict) else None
    loaded: list[LoadedModel] = []
    for item in models if isinstance(models, list) else []:
        if not isinstance(item, dict):
            continue
        tag = item.get("name") or item.get("model")
        if not isinstance(tag, str) or not tag:
            continue
        size = item.get("size")
        vram = item.get("size_vram")
        loaded.append(
            LoadedModel(
                tag=tag,
                size_gb=round(size / GIB, 2) if isinstance(size, (int, float)) else 0.0,
                vram_gb=round(vram / GIB, 2) if isinstance(vram, (int, float)) else 0.0,
            )
        )
    return loaded


async def loaded_models(
    host: str, *, timeout_s: float = 1.0, transport: httpx.AsyncBaseTransport | None = None
) -> list[LoadedModel] | None:
    """Modèles chargés, ou `None` si Ollama ne répond pas à temps."""
    try:
        async with httpx.AsyncClient(
            base_url=host.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            trust_env=False,  # pas de proxy système pour une adresse locale
        ) as client:
            response = await asyncio.wait_for(client.get("/api/ps"), timeout_s)
        response.raise_for_status()
        return parse_ps(response.json())
    except Exception:  # noqa: BLE001 - toute panne = pas d'information
        return None


async def unload_model(
    host: str,
    tag: str,
    *,
    timeout_s: float = 10.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Décharge un modèle de la mémoire d'Ollama (`keep_alive: 0`), sans rien lui faire générer.

    `/api/generate` pour un modèle de conversation, `/api/embed` pour un modèle d'embedding (le
    premier le refuse). Vrai si Ollama a accepté ; jamais d'exception.
    """
    try:
        async with httpx.AsyncClient(
            base_url=host.rstrip("/"), timeout=timeout_s, transport=transport, trust_env=False
        ) as client:
            response = await client.post("/api/generate", json={"model": tag, "keep_alive": 0})
            if response.status_code == 400:  # modèle d'embedding : « does not support generate »
                response = await client.post(
                    "/api/embed", json={"model": tag, "input": "", "keep_alive": 0}
                )
        return response.is_success
    except Exception:  # noqa: BLE001 - toute panne = non déchargé
        return False
