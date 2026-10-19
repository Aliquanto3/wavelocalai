"""Action sensible d'un agent : préparée, montrée à l'utilisateur, exécutée après son accord seul
(story 6.3, AD-9, D2).

Un outil `sensitive` du registre (`agents/tools/`) ne fait que préparer : la boucle demande ensuite
au hub la validation de l'utilisateur (`RunHub.request_approval`) et n'appelle `execute` que si la
décision est `approved`. Le travail réel (l'envoi d'un email, `agents/outbox.py`) vit donc hors des
outils, derrière cette porte. `details` est ce que l'utilisateur lit : l'action exécutée est celle
de ce texte, par construction (`execute` capture ce que `prepare` a validé).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class PendingAction:
    kind: str  # `approval_required.kind` (`email`)
    details: dict[str, str]  # champs publiés tels quels (`destinataire`, `objet`, `corps`)
    execute: Callable[[], Awaitable[str]]  # texte rendu à l'agent ; `ToolError` si l'action échoue


class SensitiveAction(Protocol):
    def prepare(self, arguments: dict[str, Any]) -> PendingAction:
        """Valide les arguments et prépare l'action ; `ToolError` si elle est invalide (rien n'est
        alors demandé à l'utilisateur)."""
        ...
