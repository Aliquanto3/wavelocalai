"""Nettoyage de la sortie des juges Ragas (sans dépendance à streamlit).

Claude enveloppe volontiers son JSON dans des balises Markdown (```json ... ```), alors que
Ragas attend du JSON brut. Ce module retire ces balises englobantes, rien d'autre.
"""

import re
from typing import Any

# Balise ouvrante (```json, ```JSON ou ``` seul), contenu, balise fermante : tout le texte.
_FENCE_RE = re.compile(r"\A\s*```[A-Za-z0-9_-]*[ \t]*\r?\n?(.*?)\r?\n?[ \t]*```\s*\Z", re.DOTALL)


def strip_markdown_fences(text: str) -> str:
    """Retire les balises de code Markdown qui englobent tout le texte ; sinon l'inchangé."""
    if not isinstance(text, str):
        return text
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def _clean_result(result: Any) -> Any:
    """Nettoie en place les générations d'un `LLMResult` LangChain."""
    for row in getattr(result, "generations", None) or []:
        for gen in row:
            if isinstance(getattr(gen, "text", None), str):
                gen.text = strip_markdown_fences(gen.text)
            message = getattr(gen, "message", None)
            if message is not None and isinstance(getattr(message, "content", None), str):
                message.content = strip_markdown_fences(message.content)
    return result


def make_fence_stripping_wrapper(wrapper_cls: type) -> type:
    """Sous-classe de `LangchainLLMWrapper` qui nettoie les générations sync et async."""

    class FenceStrippingLLMWrapper(wrapper_cls):  # type: ignore[misc, valid-type]
        def generate_text(self, *args: Any, **kwargs: Any) -> Any:
            return _clean_result(super().generate_text(*args, **kwargs))

        async def agenerate_text(self, *args: Any, **kwargs: Any) -> Any:
            return _clean_result(await super().agenerate_text(*args, **kwargs))

    return FenceStrippingLLMWrapper
