"""Préférences choisies par l'UI (table `preferences`, migration `0003_preferences.sql`, AD-15).

`PreferenceStore` est l'interface que les services consomment ; l'implémentation en mémoire sert
aux tests et d'ici au branchement sur le store SQLite (écrivain unique, story 1.3). Les valeurs
sont des documents JSON (dict, liste, nombre, texte).
"""

from __future__ import annotations

import copy
from typing import Any, Protocol


class PreferenceStore(Protocol):
    def get(self, key: str) -> Any | None:
        """Valeur enregistrée pour cette clé, `None` si elle n'existe pas."""
        ...

    def put(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...


class InMemoryPreferenceStore:
    def __init__(self) -> None:
        self._rows: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        value = self._rows.get(key)
        return None if value is None else copy.deepcopy(value)

    def put(self, key: str, value: Any) -> None:
        self._rows[key] = copy.deepcopy(value)

    def delete(self, key: str) -> None:
        self._rows.pop(key, None)
