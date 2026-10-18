"""Adaptateur `fake` scriptable du port `ChatModel` (AD-8), pour les tests.

Il n'est enregistré que si `Settings.testing` est vrai (`fake_models`). Un script est une liste
d'étapes : un `ChatChunk`, un `Sleep`, ou une exception à lever (par ex. `ProviderError`). Sans
`Done` dans le script, l'adaptateur en émet un à la fin. Le flux se ferme dans un `finally`
(`opened` / `closed` le montrent aux tests).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from wavelocalai.config import Settings
from wavelocalai.models.port import (
    ChatChunk,
    ChatModel,
    ChatRequest,
    ChatResult,
    Done,
    ModelRef,
    TextDelta,
)

FAKE_REF = ModelRef(tag="fake:1b", provider="fake", origin="local", kind="chat")


@dataclass(frozen=True)
class Sleep:
    seconds: float


Step = ChatChunk | Sleep | BaseException


class FakeChatModel:
    def __init__(self, script: Sequence[Step] = (), ref: ModelRef = FAKE_REF) -> None:
        self.ref = ref
        self.script = list(script)
        self.opened = 0
        self.closed = 0
        self.requests: list[ChatRequest] = []

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.opened += 1
        self.requests.append(request)
        try:
            done = False
            for step in self.script:
                if isinstance(step, Sleep):
                    await asyncio.sleep(step.seconds)
                elif isinstance(step, BaseException):
                    raise step
                else:
                    done = done or isinstance(step, Done)
                    yield step
            if not done:
                tokens = sum(len(s.text.split()) for s in self.script if isinstance(s, TextDelta))
                yield Done(
                    ChatResult(
                        input_tokens=4,
                        output_tokens=tokens,
                        ttft_s=0.01,
                        total_s=0.05,
                        tps=100.0,
                        tps_source="wallclock",
                    )
                )
        finally:
            self.closed += 1


def fake_models(settings: Settings) -> dict[str, ChatModel]:
    """Modèles factices à enregistrer : aucun hors `Settings.testing`."""
    return {FAKE_REF.tag: FakeChatModel()} if settings.testing else {}
