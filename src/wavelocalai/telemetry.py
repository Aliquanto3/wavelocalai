"""Télémétries des bibliothèques coupées : aucune n'est envoyée sans action de l'utilisateur.

Copie adaptée de la v1 (`src/core/telemetry.py`, jamais importée : AD-2). Chaque bibliothèque lit
sa variable au moment de son import : `disable_telemetry()` s'exécute avant la création de l'app
(`web/app.py`, qui passe le `.env` des réglages) et juste avant tout import de `fastembed` ou de
`huggingface_hub` (AD-21) ; un test AST de la v2 le vérifie.

Une valeur déjà définie, dans l'environnement ou dans le `.env` (lu ici d'abord, sans rien
écraser), l'emporte : c'est ainsi qu'on réactive volontairement une télémétrie. Module de base :
il n'importe rien du paquet.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Variable -> valeur qui coupe la télémétrie.
TELEMETRY_OPT_OUTS: dict[str, str] = {
    # FastAPI : pas de configuration automatique d'OpenTelemetry (AD-19). `web/app.py` coupe en
    # plus tracing, metrics, logs et operation_spans à la création de l'app.
    "FASTAPI_OTEL_AUTO_CONFIGURE": "false",
    "OTEL_SDK_DISABLED": "true",
    # Hugging Face (huggingface_hub, tiré par fastembed).
    "HF_HUB_DISABLE_TELEMETRY": "1",
    # Chroma reste installé tant que la v1 vit dans le même environnement.
    "ANONYMIZED_TELEMETRY": "False",
    # Convention commune, lue par plusieurs bibliothèques.
    "DO_NOT_TRACK": "1",
}


def disable_telemetry(dotenv_path: str | Path | None = None) -> None:
    """Coupe les télémétries connues, sans écraser une valeur déjà définie (environnement,
    puis `.env`)."""
    load_dotenv(dotenv_path)
    for name, value in TELEMETRY_OPT_OUTS.items():
        os.environ.setdefault(name, value)
