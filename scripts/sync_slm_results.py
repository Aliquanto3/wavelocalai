#!/usr/bin/env python3
"""Synchronise les résultats de benchmark publiés par slm-quality-bench.

wavelocalai ne produit plus de résultats de benchmark : ils viennent de la
dernière release de `Aliquanto3/slm-quality-bench`, qui publie l'asset
`slm-quality-results.json`. Ce script :

1. lit la dernière release (API GitHub `releases/latest`) ;
2. télécharge le JSON Schema **au tag de la release** et valide le fichier ;
3. écrit un instantané versionné dans `benchmarks/slm-quality/` :
   `slm-quality-results.json` (octets inchangés) et `SOURCE.json` (provenance).

    python scripts/sync_slm_results.py            # synchronise
    python scripts/sync_slm_results.py --check    # dit ce qui changerait, n'écrit rien

Codes de sortie : 0 (synchronisé, déjà à jour, ou dépôt joignable sans release
ni asset publié), 1 (dépôt source introuvable, échec réseau, tag ou schéma
inutilisable, validation en échec : rien n'est écrit), 2 (dépendance
`jsonschema` absente).

Quand la variable `GITHUB_OUTPUT` existe, le script y écrit `changed=true|false`
et `version=<tag>` pour le workflow `sync-slm-results.yml`.

Le transport HTTP est injectable (`Transport`) : les tests n'ouvrent aucune
connexion. Le jeton `GITHUB_TOKEN` (optionnel) n'est envoyé qu'à l'API GitHub,
jamais au téléchargement de l'asset (le dépôt source est public).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent

DEFAULT_REPO = "Aliquanto3/slm-quality-bench"
ASSET_NAME = "slm-quality-results.json"
SOURCE_NAME = "SOURCE.json"
DEFAULT_OUT_DIR = ROOT / "benchmarks" / "slm-quality"
# Schéma retenu quand le fichier n'annonce pas sa version de schéma.
DEFAULT_SCHEMA_ID = "qb.results-1"
# Champs (à la racine, puis dans `header`) qui portent la version de schéma.
SCHEMA_FIELDS = ("schema", "schema_version")
SCHEMA_PATH = "docs/schemas/{schema_id}.schema.json"
MAX_REPORTED_ERRORS = 10
# Plafond de taille d'une réponse HTTP (asset, schéma, API).
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024

# Un tag ou un identifiant de schéma finit dans une URL, un nom de branche et
# GITHUB_OUTPUT : on n'accepte que des caractères sans danger.
_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SCHEMA_ID_RE = re.compile(r"^qb\.results[/-]\d+$")

# Transport injectable : (url, en-têtes) -> (code HTTP, corps).
Transport = Callable[[str, Mapping[str, str]], tuple[int, bytes]]


class SyncError(Exception):
    """Échec de la synchronisation : message en français, code de sortie 1."""


def http_transport(url: str, headers: Mapping[str, str]) -> tuple[int, bytes]:
    """Transport réel : renvoie aussi les codes d'erreur HTTP (404 compris)."""
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read(MAX_DOWNLOAD_BYTES + 1)
            if len(body) > MAX_DOWNLOAD_BYTES:
                raise SyncError(
                    f"Réponse trop volumineuse sur {url} (plus de {MAX_DOWNLOAD_BYTES} octets)."
                )
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(MAX_DOWNLOAD_BYTES)
    except (OSError, http.client.HTTPException) as exc:
        # URLError, TimeoutError, ConnectionResetError, IncompleteRead...
        raise SyncError(f"Échec réseau sur {url} : {exc!r}") from exc


def _loads(data: bytes, what: str) -> Any:
    """json.loads avec un message clair (JSON invalide ou trop imbriqué)."""
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as exc:
        raise SyncError(f"{what} n'est pas un JSON lisible : {exc!r}") from exc


def _write_atomic(path: Path, data: bytes) -> None:
    """Écrit `path` via un fichier temporaire voisin puis os.replace."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_outputs(env: Mapping[str, str], changed: bool, version: str) -> None:
    """Écrit `changed` et `version` dans $GITHUB_OUTPUT s'il existe."""
    target = env.get("GITHUB_OUTPUT")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(f"changed={'true' if changed else 'false'}\n")
        handle.write(f"version={version}\n")


def _api_headers(env: Mapping[str, str]) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "wavelocalai-sync-slm-results",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = env.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release(
    repo: str, transport: Transport, env: Mapping[str, str]
) -> dict[str, Any] | None:
    """Dernière release du dépôt source, ou None si le dépôt n'en a aucune.

    Un 404 sur `releases/latest` est ambigu : le dépôt n'a pas de release, ou
    il est introuvable (renommé, privé, supprimé). Dans le second cas, on échoue
    pour que le workflow planifié passe au rouge au lieu de rester vert à vide.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    status, body = transport(url, _api_headers(env))
    if status == 404:
        repo_url = f"https://api.github.com/repos/{repo}"
        repo_status, _ = transport(repo_url, _api_headers(env))
        if repo_status == 200:
            return None
        raise SyncError(
            f"Dépôt source {repo} introuvable (HTTP {repo_status} sur {repo_url}) : "
            "renommé, privé ou supprimé ?"
        )
    if status != 200:
        raise SyncError(f"L'API GitHub a répondu HTTP {status} pour {url}.")
    release = _loads(body, "La réponse de l'API GitHub")
    if not isinstance(release, dict):
        raise SyncError("Réponse de l'API GitHub inattendue (objet JSON attendu).")
    return release


def find_asset_url(release: Mapping[str, Any]) -> str | None:
    """URL de téléchargement de l'asset de résultats, ou None s'il manque."""
    for asset in release.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == ASSET_NAME:
            url = asset.get("browser_download_url")
            if isinstance(url, str) and url:
                return url
    return None


def schema_id_of(payload: Any) -> str:
    """Identifiant de schéma annoncé par le fichier, sinon le schéma par défaut.

    « qb.results/1 » devient « qb.results-1 » (nom du fichier de schéma).
    """
    if isinstance(payload, dict):
        scopes = [payload]
        if isinstance(payload.get("header"), dict):
            scopes.append(payload["header"])
        for scope in scopes:
            for field in SCHEMA_FIELDS:
                value = scope.get(field)
                if isinstance(value, str) and value:
                    if not _SCHEMA_ID_RE.fullmatch(value):
                        raise SyncError(
                            f"Version de schéma non reconnue dans le fichier : {value!r}."
                        )
                    return value.replace("/", "-")
    return DEFAULT_SCHEMA_ID


def validate_payload(payload: Any, schema: Mapping[str, Any]) -> list[str]:
    """Valide `payload` contre `schema` ; renvoie les erreurs (liste vide si ok)."""
    try:
        import referencing.exceptions
        from jsonschema import exceptions, validators
    except ImportError as exc:  # pragma: no cover - dépend de l'environnement
        raise ModuleNotFoundError("jsonschema") from exc

    cls = validators.validator_for(schema)
    try:
        cls.check_schema(schema)
    except exceptions.SchemaError as exc:
        raise SyncError(f"Le JSON Schema téléchargé est invalide : {exc.message}") from exc
    validator = cls(schema, format_checker=cls.FORMAT_CHECKER)
    try:
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    except (referencing.exceptions.Unresolvable, RecursionError) as exc:
        raise SyncError(f"Validation impossible avec le JSON Schema téléchargé : {exc!r}") from exc
    messages = []
    for error in errors:
        where = "/".join(str(part) for part in error.absolute_path) or "(racine)"
        messages.append(f"{where} : {error.message}")
    return messages


def _read_existing(out_dir: Path) -> tuple[str | None, dict[str, Any]]:
    """Sha256 du fichier actuellement synchronisé et contenu de SOURCE.json."""
    results = out_dir / ASSET_NAME
    source = out_dir / SOURCE_NAME
    current = _sha256(results.read_bytes()) if results.is_file() else None
    meta: dict[str, Any] = {}
    if source.is_file():
        try:
            loaded = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                meta = loaded
        except ValueError:
            meta = {}
    return current, meta


def sync(
    repo: str = DEFAULT_REPO,
    *,
    check: bool = False,
    transport: Transport | None = None,
    out_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    """Synchronise l'instantané ; renvoie le code de sortie."""
    env = os.environ if env is None else env
    transport = transport or http_transport
    out_dir = DEFAULT_OUT_DIR if out_dir is None else out_dir
    now = now or (lambda: datetime.now(timezone.utc))

    release = fetch_latest_release(repo, transport, env)
    if release is None:
        print(f"Aucune release publiée sur {repo} : rien à synchroniser.")
        _write_outputs(env, False, "")
        return 0

    tag = release.get("tag_name")
    if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
        raise SyncError(f"Tag de release inutilisable : {tag!r}.")
    release_url = release.get("html_url") or f"https://github.com/{repo}/releases/tag/{tag}"

    asset_url = find_asset_url(release)
    if asset_url is None:
        print(
            f"La release {tag} de {repo} ne contient pas encore l'asset {ASSET_NAME} : "
            "rien à synchroniser."
        )
        _write_outputs(env, False, tag)
        return 0

    status, asset_bytes = transport(asset_url, {"User-Agent": "wavelocalai-sync-slm-results"})
    if status != 200:
        raise SyncError(f"Téléchargement de {asset_url} impossible (HTTP {status}).")
    asset_sha = _sha256(asset_bytes)

    payload = _loads(asset_bytes, ASSET_NAME)

    schema_id = schema_id_of(payload)
    schema_url = (
        f"https://raw.githubusercontent.com/{repo}/{urllib.parse.quote(tag)}/"
        + SCHEMA_PATH.format(schema_id=schema_id)
    )
    status, schema_bytes = transport(schema_url, {"User-Agent": "wavelocalai-sync-slm-results"})
    if status != 200:
        raise SyncError(f"Téléchargement du JSON Schema impossible (HTTP {status}) : {schema_url}")
    schema = _loads(schema_bytes, "Le JSON Schema téléchargé")
    if not isinstance(schema, dict):
        raise SyncError("Le JSON Schema téléchargé n'est pas un objet JSON.")

    errors = validate_payload(payload, schema)
    if errors:
        lines = [f"Validation échouée pour {ASSET_NAME} ({tag}, schéma {schema_id}) :"]
        lines += [f"  - {message}" for message in errors[:MAX_REPORTED_ERRORS]]
        if len(errors) > MAX_REPORTED_ERRORS:
            lines.append(f"  ... et {len(errors) - MAX_REPORTED_ERRORS} autre(s) erreur(s).")
        lines.append("Rien n'a été écrit.")
        raise SyncError("\n".join(lines))

    schema_sha = _sha256(schema_bytes)
    current_sha, meta = _read_existing(out_dir)
    if (
        current_sha == asset_sha
        and meta.get("asset_sha256") == asset_sha
        and meta.get("tag") == tag
        and meta.get("schema_sha256") == schema_sha
    ):
        print(f"Résultats déjà à jour ({tag}, sha256 {asset_sha[:12]}).")
        _write_outputs(env, False, tag)
        return 0

    if check:
        print(
            f"Mise à jour disponible : {tag} (sha256 {asset_sha[:12]}), "
            "--check : rien n'a été écrit."
        )
        _write_outputs(env, True, tag)
        return 0

    source = {
        "repo": repo,
        "tag": tag,
        "release_url": release_url,
        "asset": ASSET_NAME,
        "asset_url": asset_url,
        "asset_sha256": asset_sha,
        "schema": schema_id,
        "schema_url": schema_url,
        "schema_sha256": schema_sha,
        "fetched_at": now().astimezone(timezone.utc).isoformat(timespec="seconds"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    # Chaque fichier est remplacé atomiquement ; SOURCE.json en dernier, si bien
    # qu'une interruption entre les deux est détectée au passage suivant.
    _write_atomic(out_dir / ASSET_NAME, asset_bytes)
    _write_atomic(
        out_dir / SOURCE_NAME,
        (json.dumps(source, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )
    print(f"Résultats synchronisés : {tag} (sha256 {asset_sha[:12]}) dans {out_dir}.")
    _write_outputs(env, True, tag)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help=f"dépôt source (défaut : {DEFAULT_REPO})"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="dit si une mise à jour existe, sans rien écrire",
    )
    args = parser.parse_args(argv)
    try:
        return sync(args.repo, check=args.check)
    except SyncError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    except ModuleNotFoundError:
        print(
            "Erreur : le paquet `jsonschema` est requis (uv sync, ou pip install jsonschema).",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
