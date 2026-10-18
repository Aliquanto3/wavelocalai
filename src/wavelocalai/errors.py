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
    ErrorSpec(
        "run_busy",
        409,
        "Une exécution de ce genre est déjà en cours.",
        "Rejoignez-la, ou arrêtez-la avant d'en lancer une autre.",
        ("run_id",),
    ),
    ErrorSpec(
        "cloud_not_allowed",
        403,
        "Ce modèle est hébergé hors de ce poste et le mode cloud n'est pas autorisé.",
        "Autorisez le mode cloud pour cette demande, ou choisissez un modèle local.",
        ("tag",),
    ),
    ErrorSpec(
        "model_not_chat",
        422,
        "Ce modèle ne sert pas à générer du texte.",
        "Choisissez un modèle de conversation dans la liste.",
        ("tag", "kind"),
    ),
    ErrorSpec(
        "model_not_embedding",
        422,
        "Ce modèle ne sert pas à calculer des embeddings.",
        "Choisissez un modèle d'embedding local dans la liste.",
        ("tag", "kind"),
    ),
    ErrorSpec(
        "model_not_found",
        404,
        "Ce modèle n'est pas dans la liste des modèles disponibles.",
        "Rechargez la liste des modèles, ou installez ce modèle dans Ollama.",
        ("tag",),
    ),
    ErrorSpec(
        "no_model",
        404,
        "Aucun modèle de conversation n'est disponible pour cet usage.",
        "Installez un modèle de conversation dans Ollama (par exemple `ollama pull qwen3.5:2b`), "
        "puis rechargez la liste.",
        ("purpose",),
    ),
    ErrorSpec(
        "timeout",
        504,
        "Le modèle n'a pas fini de répondre dans le délai prévu.",
        "Réessayez avec un modèle plus petit, ou allongez `lane_timeout_s` dans "
        "`wavelocalai.toml`.",
        ("timeout_s",),
    ),
    ErrorSpec(
        "generation_interrupted",
        502,
        "Ollama a arrêté la génération avant la fin.",
        "Réessayez ; si cela se répète, redémarrez Ollama ou choisissez un modèle plus petit.",
    ),
    ErrorSpec(
        "ollama_error",
        502,
        "Ollama a refusé la requête.",
        "Ouvrez les détails techniques ; vérifiez que le modèle est installé et que la mémoire "
        "suffit.",
    ),
    ErrorSpec(
        "cloud_key_missing",
        400,
        "La clé d'API de {provider_name} n'est pas configurée.",
        "Ajoutez {key_var}=votre clé dans le fichier `.env` à la racine du projet, relancez le "
        "serveur, ou choisissez un modèle local.",
        ("provider", "provider_name", "key_var"),
    ),
    ErrorSpec(
        "cloud_key_refused",
        502,
        "{provider_name} a refusé la clé d'API.",
        "Vérifiez la valeur de {key_var} dans le fichier `.env` (clé valide, droits sur ce "
        "modèle), relancez le serveur, ou repassez en Local.",
        ("provider", "provider_name", "key_var", "http_status"),
    ),
    ErrorSpec(
        "cloud_unreachable",
        502,
        "{provider_name} est injoignable depuis ce poste.",
        "Vérifiez la connexion réseau, puis réessayez ; ou repassez en Local en désactivant le "
        "mode cloud et en choisissant un modèle local.",
        ("provider", "provider_name"),
    ),
    ErrorSpec(
        "cloud_rate_limited",
        429,
        "{provider_name} limite le débit ou le quota de cette clé.",
        "Patientez un peu avant de réessayer, vérifiez le quota de votre compte, ou repassez en "
        "Local.",
        ("provider", "provider_name", "http_status"),
    ),
    ErrorSpec(
        "cloud_error",
        502,
        "{provider_name} a refusé ou interrompu la requête.",
        "Ouvrez les détails techniques ; choisissez un autre modèle de ce fournisseur, réessayez "
        "plus tard, ou repassez en Local.",
        ("provider", "provider_name", "http_status"),
    ),
    ErrorSpec(
        "conversation_busy",
        409,
        "Cette conversation a une réponse en cours : elle ne peut pas être effacée maintenant.",
        "Arrêtez la réponse (touche Échap), puis effacez la conversation.",
        ("run_id",),
    ),  # --- base documentaire (story 4.1) ---
    ErrorSpec(
        "ingest_failed",
        422,
        "Le fichier n'a pas pu être indexé.",
        "Vérifiez que le fichier est un PDF, TXT, MD ou DOCX lisible, sans mot de passe et avec "
        "du texte, puis importez-le de nouveau.",
        ("file", "reason"),
    ),
    ErrorSpec(
        "no_embedding_model",
        404,
        "Aucun modèle d'embedding n'est installé sur ce poste.",
        "Installez un modèle d'embedding dans Ollama (par exemple `ollama pull nomic-embed-text`), "
        "puis réessayez.",
    ),
    ErrorSpec(
        "embedding_locked",
        409,
        "La base documentaire utilise déjà un autre modèle d'embedding.",
        "Importez avec le modèle de la base, ou videz la base avant d'en changer.",
        ("current", "requested"),
    ),
)
ERRORS: dict[str, ErrorSpec] = {spec.code: spec for spec in _SPECS}

_MASK = "***"
# Clés à préfixe connu : OpenAI/Anthropic (`sk-...`), Groq (`gsk_...`), Hugging Face (`hf_...`).
_PREFIXED_KEY = re.compile(r"\b(?:sk-|gsk_|hf_)[A-Za-z0-9_\-]{8,}")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}")
# `api_key=...`, `MISTRAL_API_KEY=...`, `"token": "..."`, `Authorization: ...`.
_NAMED_SECRET = re.compile(
    r"""(?ix)(?<![a-z0-9])(api[_-]?key|secret|token|authorization)(["']?\s*[:=]\s*["']?)"""
    r"""(?!\*\*\*)[^\s"',;}]+"""
)


class _Fill(dict[str, Any]):
    """Valeurs de remplacement d'un texte de code d'erreur (`{provider_name}`) ; un manque donne
    une formule neutre plutôt qu'une erreur."""

    def __missing__(self, key: str) -> str:
        return "le fournisseur" if key == "provider_name" else key


def _fill(text: str, detail: dict[str, Any]) -> str:
    """Remplace les `{clé}` de `message` et `action` par les clés machine du `detail` (nom du
    fournisseur, variable de clé : des constantes de l'application, jamais un texte saisi)."""
    if "{" not in text:
        return text
    return text.format_map(_Fill(detail))


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
        "message": _fill(spec.message, detail),
        "action": _fill(spec.action, detail),
        "detail": _mask_value(body, tuple(secrets)),
    }


class ProviderError(AppError):
    """Refus ou panne d'un fournisseur de modèle (AD-8) : un adaptateur la lève avec un code de
    la liste fermée ; le service la met en enveloppe dans `run_ended.data.error`."""
