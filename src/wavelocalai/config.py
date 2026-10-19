"""Configuration de la v2 : `Settings`, chargé une fois au démarrage (AD-15).

Ordre de chargement : défauts du code, puis `wavelocalai.toml` (`tomllib`), puis `.env` et
l'environnement du processus (secrets et quelques réglages de poste), puis les surcharges
explicites (options de la ligne de commande). L'application n'écrit jamais le `.toml`.

C'est le seul module de la v2 qui lit l'environnement : aucun `os.getenv` ailleurs (un test AST
le vérifie). Module de base : il n'importe rien du paquet.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOML = PROJECT_ROOT / "wavelocalai.toml"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_PORT = 8502
LOOPBACK = "127.0.0.1"

# Fournisseurs cloud et variable (de `.env` ou de l'environnement) qui porte leur clé.
CLOUD_KEY_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}

# Réglages de poste lisibles dans `.env` ou l'environnement : variable -> chemin dans les réglages.
ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "WAVELOCALAI_PORT": ("server", "port"),
    "WAVELOCALAI_DATA_DIR": ("data", "dir"),
    "WAVELOCALAI_OLLAMA_HOST": ("ollama", "host"),
}
TESTING_VAR = "WAVELOCALAI_TESTING"


class ConfigError(Exception):
    """Configuration illisible ou invalide (message en français, affiché au lancement)."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ServerSettings(_Section):
    port: int = Field(DEFAULT_PORT, ge=1, le=65535)


class DataSettings(_Section):
    dir: Path = Path("data")


class OllamaSettings(_Section):
    host: str = "http://127.0.0.1:11434"
    probe_timeout_s: float = Field(1.0, gt=0, le=1.0)  # AD-15 : 1 s au plus
    probe_cache_s: float = Field(5.0, ge=0)


class CarbonSettings(_Section):
    country_iso: str = Field("FRA", min_length=3, max_length=3)
    pue: float = Field(1.1, ge=1.0)


class ModelPrice(_Section):
    """Prix public d'un modèle cloud, par million de tokens (dans la devise de la table)."""

    input_per_mtok: float = Field(ge=0)
    output_per_mtok: float = Field(ge=0)


class PriceTable(_Section):
    """Table de prix cloud datée (story 3.5), clé = identifiant exposé `fournisseur/modèle`.

    Aucune entrée sans date de relevé ni source : un prix sans date ne se vérifie pas. Vide, elle
    est valide ; le verdict dit alors le coût « inconnu » avec sa raison (jamais 0).
    """

    currency: str = Field("EUR", pattern=r"^[A-Z]{3}$")  # code ISO 4217 : lu par `Intl`
    retrieved_at: date | None = None
    source: str | None = None
    models: dict[str, ModelPrice] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _dated_and_sourced(self) -> PriceTable:
        if self.models and (self.retrieved_at is None or not (self.source or "").strip()):
            raise ValueError("une table de prix a besoin de retrieved_at et de source")
        return self


class CloudSettings(_Section):
    """Modèles cloud proposés (listes fixes : aucun fournisseur n'est appelé pour les lister),
    correspondance Groq vers l'entrée `huggingface_hub` d'ecologits (AD-11) et table de prix."""

    models: dict[str, list[str]] = Field(default_factory=dict)
    groq_ecologits: dict[str, str] = Field(default_factory=dict)
    prices: PriceTable = PriceTable()


class DelaySettings(_Section):
    lane_timeout_s: float = Field(300.0, gt=0)
    approval_expiry_s: float = Field(600.0, gt=0)


class RagSettings(_Section):
    """Base documentaire : découpe, lots d'embedding et plafonds d'un import (stories 4.1 et 4.2)."""

    chunk_size: int = Field(800, ge=100, le=8000)  # caractères par extrait
    chunk_overlap: int = Field(100, ge=0)
    embed_batch_size: int = Field(16, ge=1, le=256)  # extraits par lot, une feuille `embedding`
    max_file_mb: int = Field(50, ge=1)
    max_files: int = Field(50, ge=1)  # fichiers par import
    max_import_mb: int = Field(500, ge=1)  # taille totale d'un import
    embedding_model: str | None = None  # défaut de la base ; sinon le premier installé
    # Question (story 4.4) : nombre d'extraits cités et seuils du libellé de pertinence (similarité
    # cosinus, 0 à 1) calés sur le modèle d'embedding par défaut de la base.
    top_k: int = Field(4, ge=1, le=20)
    # Self-RAG (story 4.6) : reformulations de la question au plus, donc `1 + n` recherches ; la
    # borne atteinte, la réponse part avec les meilleurs extraits trouvés.
    self_rag_max_iterations: int = Field(2, ge=1, le=5)
    relevance_very_close: float = Field(0.70, gt=0.0, le=1.0)
    relevance_close: float = Field(0.60, ge=0.0, lt=1.0)

    @model_validator(mode="after")
    def _overlap_below_size(self) -> RagSettings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap doit rester inférieur à chunk_size")
        return self

    @model_validator(mode="after")
    def _thresholds_ordered(self) -> RagSettings:
        if self.relevance_close >= self.relevance_very_close:
            raise ValueError("relevance_close doit rester inférieur à relevance_very_close")
        return self


class Settings(BaseModel):
    """Réglages du serveur ; immuables une fois chargés."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    server: ServerSettings = ServerSettings()
    data: DataSettings = DataSettings()
    ollama: OllamaSettings = OllamaSettings()
    carbon: CarbonSettings = CarbonSettings()
    cloud: CloudSettings = CloudSettings()
    delays: DelaySettings = DelaySettings()
    rag: RagSettings = RagSettings()
    api_keys: dict[str, SecretStr] = Field(default_factory=dict)
    testing: bool = False  # autorise l'adaptateur `fake` (AD-8) ; jamais vrai hors des tests
    base_dir: Path = PROJECT_ROOT  # base des chemins relatifs (dossier du `.toml`)
    env_file: Path | None = None  # `.env` lu (et passé à `disable_telemetry`)

    @property
    def data_dir(self) -> Path:
        path = self.data.dir.expanduser()
        return path if path.is_absolute() else (self.base_dir / path).resolve()

    def cloud_providers(self) -> list[dict[str, Any]]:
        """`[{id, configured}]` lu d'ici : aucun fournisseur n'est appelé."""
        return [
            {"id": provider, "configured": bool(self.api_keys.get(provider))}
            for provider in CLOUD_KEY_VARS
        ]

    def secret_values(self) -> list[str]:
        """Valeurs des clés configurées, pour le masquage (AD-18)."""
        return [key.get_secret_value() for key in self.api_keys.values() if key.get_secret_value()]


def get_version() -> str:
    """Version du paquet installé (celle de `pyproject.toml`)."""
    try:
        return metadata.version("wavelocalai")
    except metadata.PackageNotFoundError:  # pragma: no cover - paquet non installé
        return "0+unknown"


def _merge(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Le fichier de réglages {path} est illisible : {exc}") from exc


def load_settings(
    toml_path: Path | None = None,
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> Settings:
    """Charge `Settings` une fois : `.toml`, puis `.env` et environnement, puis surcharges.

    `environ` vaut l'environnement du processus par défaut ; il l'emporte sur `.env`.
    """
    toml_file = Path(toml_path) if toml_path is not None else DEFAULT_TOML
    dotenv_file = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
    data = _read_toml(toml_file)
    values: dict[str, str | None] = (
        dict(dotenv_values(dotenv_file)) if dotenv_file.is_file() else {}
    )
    values.update(os.environ if environ is None else environ)

    for var, (section, key) in ENV_OVERRIDES.items():
        if values.get(var):
            data.setdefault(section, {})[key] = values[var]
    data["api_keys"] = {
        provider: value
        for provider, var in CLOUD_KEY_VARS.items()
        if (value := (values.get(var) or "").strip())
    }
    data["testing"] = (values.get(TESTING_VAR) or "").strip().lower() in {"1", "true"}
    data["base_dir"] = toml_file.resolve().parent
    data["env_file"] = dotenv_file
    if overrides:
        _merge(data, overrides)
    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])} : {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(f"Réglages invalides ({details}).") from exc
