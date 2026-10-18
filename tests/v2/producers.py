"""Producteurs de test du hub : ils jouent le rôle d'un service sans aucun adaptateur de modèle.

Ils ne font que ce qu'un service fait avec le hub : créer un run, publier des événements, terminer
une feuille. Aucun port `ChatModel` ni client Ollama n'est nécessaire.
"""

from __future__ import annotations

from collections.abc import Sequence

from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, LeafResult, RunHandle

LOCAL_CO2 = Co2(mg=1.5, method="codecarbon", estimated=False)


async def produce_chat(
    hub: RunHub,
    question: str = "Bonjour ?",
    tokens: Sequence[str] = ("Salut", " !"),
    *,
    conversation_id: str | None = None,
    finish: bool = True,
) -> RunHandle:
    """Un chat à un seul run (feuille racine) : tokens, métriques, `finish_leaf`."""
    handle = await hub.create_run(
        "chat",
        models=["fake:1b"],
        params={"temperature": 0.2, "allow_cloud": False},
        user_message=question,
        conversation_id=conversation_id,
    )
    for text in tokens:
        hub.publish(handle.run_id, "token", {"lane": "fake:1b", "text": text, "channel": "answer"})
    if finish:
        result = LeafResult(
            origin="local", input_tokens=4, output_tokens=len(tokens), tps=42.0,
            tps_source="ollama_eval", ttft_s=0.1, total_s=0.5, energy_wh=0.001,
        )  # fmt: skip
        hub.publish(handle.run_id, "metrics", {"lane": "fake:1b", "co2": LOCAL_CO2.as_dict()})
        await hub.finish_leaf(handle.run_id, result, LOCAL_CO2)
    return handle


async def produce_arena(
    hub: RunHub, models: Sequence[str] = ("a:1b", "b:1b"), *, prompt: str = "Compare."
) -> tuple[RunHandle, list[RunHandle]]:
    """Une arène : un parent qui publie le flux et un run enfant `generation` par modèle."""
    parent = await hub.create_run("arena", models=models, params={"judge": "j:1b"})
    leaves = [
        await hub.create_run("generation", models=[model], parent_run_id=parent.run_id)
        for model in models
    ]
    for model in models:
        hub.publish(parent.run_id, "lane_status", {"lane": model, "status": "generating"})
    return parent, leaves
