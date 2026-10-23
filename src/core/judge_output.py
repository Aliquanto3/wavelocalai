"""Nettoyage de la sortie des juges Ragas (sans dépendance à streamlit).

Claude enveloppe volontiers son JSON dans des balises Markdown (```json ... ```), parfois
précédées d'une phrase d'introduction, alors que Ragas attend du JSON brut. Ce module extrait
le premier bloc de code, sans toucher à son contenu ; sans bloc, le texte reste inchangé.
"""

import re
from typing import Any

# Premier bloc de code : balise ouvrante en début de ligne (```json, ```JSON ou ``` seul)
# suivie d'un saut de ligne, contenu, balise fermante en fin de ligne. L'ancrage sur les lignes
# évite de prendre des ``` situés dans une chaîne JSON (un saut de ligne y est toujours échappé).
_FENCE_RE = re.compile(
    r"^[ \t]*```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)(?:\r?\n)?[ \t]*```[ \t]*\r?$",
    re.DOTALL | re.MULTILINE,
)


def strip_markdown_fences(text: str) -> str:
    """Contenu du premier bloc de code Markdown, même entouré de texte ; sinon le texte inchangé."""
    if not isinstance(text, str):
        return text
    match = _FENCE_RE.search(text)
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


class _WithoutTemperature:
    """Vue d'un modèle LangChain qui masque `temperature` (le reste est délégué)."""

    def __init__(self, llm: Any) -> None:
        object.__setattr__(self, "_llm", llm)

    def __getattr__(self, name: str) -> Any:
        if name == "temperature":
            raise AttributeError(name)
        return getattr(self._llm, name)


def make_fence_stripping_wrapper(wrapper_cls: type) -> type:
    """Sous-classe de `LangchainLLMWrapper` qui nettoie les générations sync et async.

    Le `generate_text` sync de Ragas 0.4.3 ignore `bypass_temperature` et réaffecte
    `temperature` sur le modèle (400 chez Claude) : la sous-classe lui masque l'attribut.
    """

    class FenceStrippingLLMWrapper(wrapper_cls):  # type: ignore[misc, valid-type]
        def generate_text(self, *args: Any, **kwargs: Any) -> Any:
            if not getattr(self, "bypass_temperature", False):
                return _clean_result(super().generate_text(*args, **kwargs))
            llm = self.langchain_llm
            self.langchain_llm = _WithoutTemperature(llm)
            try:
                result = super().generate_text(*args, **kwargs)
            finally:
                self.langchain_llm = llm
            return _clean_result(result)

        async def agenerate_text(self, *args: Any, **kwargs: Any) -> Any:
            return _clean_result(await super().agenerate_text(*args, **kwargs))

    return FenceStrippingLLMWrapper
