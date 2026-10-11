"""JSON canonique et empreintes (AD-4) : seule implémentation du banc.

JSON canonique = ``json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
allow_nan=False)`` encodé en UTF-8. Empreinte = ``sha256`` hexadécimal minuscule.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any


def canonical_bytes(obj: Any) -> bytes:
    """Sérialise ``obj`` en JSON canonique UTF-8.

    Un flottant non fini (NaN, ±inf) lève ``ValueError`` : il n'a pas de forme JSON.
    """
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def pretty_bytes(obj: Any) -> bytes:
    """Sérialisation lisible (manifestes) : clés triées, indentation, flottants finis seulement.

    Ce n'est pas la forme canonique : ne jamais en calculer d'empreinte.
    """
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False)
    return (text + "\n").encode("utf-8")


def plain_json(obj: Any) -> str:
    """``json.dumps(obj)`` aux réglages par défaut de Python (``", "``, ``": "``, ASCII
    échappé) : forme que BFCL donne au résultat d'un appel d'outil (``envs/``). Ce n'est pas
    la forme canonique : ne jamais en calculer d'empreinte. Un objet non sérialisable lève
    ``TypeError`` ou ``ValueError``, comme ``json.dumps``."""
    return json.dumps(obj)


def sha256_bytes(data: bytes) -> str:
    """Empreinte ``sha256`` hexadécimale minuscule d'octets bruts."""
    return hashlib.sha256(data).hexdigest()


def sha256_hex(obj: Any) -> str:
    """Empreinte ``sha256`` hexadécimale minuscule du JSON canonique de ``obj``."""
    return sha256_bytes(canonical_bytes(obj))


def nfc(text: str) -> str:
    """Normalise une chaîne en NFC (toute chaîne entrant dans le jeu de questions)."""
    return unicodedata.normalize("NFC", text)


def utc_now() -> str:
    """Date et heure UTC au format ISO 8601 avec ``Z``, à la seconde."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
