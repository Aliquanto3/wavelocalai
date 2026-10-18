"""Erreurs de la v2 : liste fermée de codes et enveloppe unique (AD-18).

Chaque réponse en erreur, et plus tard `run_ended.data.error`, a la forme
`{code, message, action, detail}` : `message` et `action` en français, `detail` un objet avec
`technical` (texte replié sous « Détails techniques ») et les clés machine déclarées avec le code
(`detail_keys`). Les valeurs texte de `detail` passent par `mask_secrets`. Chaque story ajoute ses
codes à `ERRORS`. Module de base : il n'importe rien du paquet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    status: int
    message: str
    action: str
    detail_keys: tuple[str, ...] = ()  # clés machine de `detail`, hors `technical`


_SPECS = (
    ErrorSpec(
        "ollama_down",
        503,
        "Ollama ne répond pas sur ce poste.",
        "Lancez Ollama (application ou `ollama serve`), puis réessayez.",
    ),
    ErrorSpec(
        "forbidden_host",
        403,
        "Cette requête vise une adresse que le serveur local n'accepte pas.",
        "Ouvrez l'application depuis http://127.0.0.1 ou http://localhost, sur le port affiché "
        "au lancement.",
        ("host",),
    ),
    ErrorSpec(
        "forbidden_origin",
        403,
        "Cette écriture vient d'une page qui n'est pas celle de l'application.",
        "Utilisez l'application ouverte sur votre poste et fermez les onglets étrangers.",
        ("origin",),
    ),
    ErrorSpec(
        "not_found",
        404,
        "Cette ressource n'existe pas.",
        "Vérifiez l'adresse, ou rechargez l'application.",
    ),
    ErrorSpec(
        "method_not_allowed",
        405,
        "Cette opération n'est pas permise sur cette ressource.",
        "Rechargez l'application ; si le problème persiste, signalez-le.",
    ),
    ErrorSpec(
        "invalid_request",
        422,
        "La requête est incomplète ou invalide.",
        "Corrigez les champs signalés dans les détails techniques, puis réessayez.",
    ),
    ErrorSpec(
        "internal",
        500,
        "Une erreur interne est survenue.",
        "Réessayez ; si elle persiste, consultez les journaux de `data/logs/` et relancez le "
        "serveur.",
    ),
)
ERRORS: dict[str, ErrorSpec] = {spec.code: spec for spec in _SPECS}

_MASK = "***"
# Clés à préfixe connu : OpenAI/Anthropic (`sk-...`), Groq (`gsk_...`), Hugging Face (`hf_...`).
_PREFIXED_KEY = re.compile(r"\b(?:sk-|gsk_|hf_)[A-Za-z0-9_\-]{8,}")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}")
# `api_key=...`, `"token": "..."`, `Authorization: ...`.
_NAMED_SECRET = re.compile(
    r"""(?ix)\b(api[_-]?key|secret|token|authorization)(["']?\s*[:=]\s*["']?)"""
    r"""(?!\*\*\*)[^\s"',;}]+"""
)


def mask_secrets(text: str, extra_secrets: Iterable[str] = ()) -> str:
    """Masque les clés d'API reconnaissables et les valeurs secrètes connues de `Settings`."""
    for secret in extra_secrets:
        if len(secret) >= 8:
            text = text.replace(secret, _MASK)
    text = _PREFIXED_KEY.sub(_MASK, text)
    text = _BEARER.sub(f"Bearer {_MASK}", text)
    return _NAMED_SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASK}", text)


def _mask_value(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return mask_secrets(value, secrets)
    if isinstance(value, dict):
        return {key: _mask_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask_value(item, secrets) for item in value]
    return value


class AppError(Exception):
    """Erreur applicative à code fermé ; les routes la lèvent, `web/` la met en enveloppe."""

    def __init__(self, code: str, technical: str | None = None, **detail: Any) -> None:
        if code not in ERRORS:
            raise ValueError(f"Code d'erreur inconnu : {code}")
        super().__init__(technical or ERRORS[code].message)
        self.code = code
        self.technical = technical
        self.detail = detail


def build_envelope(
    code: str,
    technical: str | None = None,
    secrets: Iterable[str] = (),
    **detail: Any,
) -> dict[str, Any]:
    """Enveloppe `{code, message, action, detail}` ; `detail` limité aux clés du code."""
    spec = ERRORS.get(code)
    if spec is None:
        raise ValueError(f"Code d'erreur inconnu : {code}")
    unknown = set(detail) - set(spec.detail_keys)
    if unknown:
        raise ValueError(f"Clés de detail non déclarées pour {code} : {sorted(unknown)}")
    body = {"technical": technical, **detail}
    return {
        "code": spec.code,
        "message": spec.message,
        "action": spec.action,
        "detail": _mask_value(body, tuple(secrets)),
    }
