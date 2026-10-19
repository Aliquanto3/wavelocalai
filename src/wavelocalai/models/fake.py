"""Adaptateur `fake` scriptable du port `ChatModel` (AD-8), pour les tests.

Il n'est enregistré que si `Settings.testing` est vrai (`fake_models`). Un script est une liste
d'étapes : un `ChatChunk`, un `Sleep`, ou une exception à lever (par ex. `ProviderError`). Sans
`Done` dans le script, l'adaptateur en émet un à la fin. Le flux se ferme dans un `finally`
(`opened` / `closed` le montrent aux tests). `scripts` donne un script par appel, dans l'ordre (le
dernier se répète) : une stratégie de recherche qui appelle le modèle plusieurs fois (story 4.6)
reçoit ainsi des réponses différentes ; sans `scripts`, `script` sert à chaque appel.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from wavelocalai.config import Settings
from wavelocalai.models.port import (
    ChatChunk,
    ChatModel,
    ChatRequest,
    ChatResult,
    Done,
    Embedder,
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
        self.scripts: list[list[Step]] = []
        self.opened = 0
        self.closed = 0
        self.requests: list[ChatRequest] = []

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.opened += 1
        self.requests.append(request)
        script = (
            self.scripts[min(self.opened, len(self.scripts)) - 1] if self.scripts else self.script
        )
        try:
            done = False
            for step in script:
                if isinstance(step, Sleep):
                    await asyncio.sleep(step.seconds)
                elif isinstance(step, BaseException):
                    raise step
                else:
                    done = done or isinstance(step, Done)
                    yield step
            if not done:
                tokens = sum(len(s.text.split()) for s in script if isinstance(s, TextDelta))
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


# --- Embedder (AD-8) -----------------------------------------------------------------------------

FAKE_EMBED_DIM = 16
FAKE_EMBED_REF = ModelRef(
    tag=f"fake-embed:{FAKE_EMBED_DIM}", provider="fake", origin="local", kind="embedding"
)
_WORD = re.compile(r"\w+", re.UNICODE)


def fake_vector(text: str, dim: int = FAKE_EMBED_DIM) -> list[float]:
    """Vecteur déterministe d'un texte : sac de mots hachés (SHA-256, stable d'un processus à
    l'autre) dans `dim` cases, normalisé. Deux textes qui partagent des mots sont proches ; un
    texte sans mot rend un vecteur unitaire fixe (jamais nul)."""
    vector = [0.0] * dim
    for word in _WORD.findall(text.lower()):
        vector[int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % dim] += 1.0
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        vector[0], norm = 1.0, 1.0
    return [x / norm for x in vector]


class FakeEmbedder:
    """`Embedder` scriptable : vecteurs de `fake_vector`, dimension fixe. `script` : une étape par
    appel, dans l'ordre (`Sleep` ou une exception à lever) ; sans étape, l'appel réussit.
    `texts` garde les lots reçus."""

    def __init__(
        self,
        script: Sequence[Sleep | BaseException | None] = (),
        ref: ModelRef = FAKE_EMBED_REF,
        dim: int = FAKE_EMBED_DIM,
    ) -> None:
        self.ref = ref
        self.dim = dim
        self.script = list(script)
        self.texts: list[list[str]] = []
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        step = self.script[self.calls] if self.calls < len(self.script) else None
        self.calls += 1
        self.texts.append(list(texts))
        if isinstance(step, Sleep):
            await asyncio.sleep(step.seconds)
        elif isinstance(step, BaseException):
            raise step
        return [fake_vector(text, self.dim) for text in texts]


def fake_embedders(settings: Settings) -> dict[str, Embedder]:
    """Embedders factices à enregistrer : aucun hors `Settings.testing`."""
    return {FAKE_EMBED_REF.tag: FakeEmbedder()} if settings.testing else {}
