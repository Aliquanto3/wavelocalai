"""
Télémétries des bibliothèques coupées : rien ne quitte la machine sans action de l'utilisateur.

Chaque bibliothèque lit sa propre variable d'environnement, souvent au moment de son import :
`disable_telemetry()` doit donc s'exécuter avant (au démarrage de l'app, et avant l'import de
Ragas dans eval_engine.py). Une valeur déjà définie, dans l'environnement ou dans le .env (lu
ici d'abord, sans rien écraser), l'emporte : c'est ainsi qu'on réactive volontairement une
télémétrie (LANGSMITH_TRACING=true…). Streamlit est coupé à part, par `gatherUsageStats` dans
.streamlit/config.toml.

Ne pas appeler depuis src/core/config.py : le benchmark l'importe (AGENTS.md).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Variable → valeur qui coupe la télémétrie (lues par les versions de constraints.txt).
TELEMETRY_OPT_OUTS: dict[str, str] = {
    # Ragas 0.4 : seule variable lue (DO_NOT_TRACK est ignoré) ; sinon t.explodinggradients.com.
    "RAGAS_DO_NOT_TRACK": "true",
    # Chroma : Settings.anonymized_telemetry (PostHog).
    "ANONYMIZED_TELEMETRY": "False",
    # CrewAI, et le SDK OpenTelemetry qu'il embarque.
    "CREWAI_DISABLE_TELEMETRY": "true",
    "OTEL_SDK_DISABLED": "true",
    # CrewAI : pas de vérification de version auprès de pypi.org au démarrage.
    "CREWAI_DISABLE_VERSION_CHECK": "true",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    # LangSmith : pas de traces envoyées sans activation explicite.
    "LANGCHAIN_TRACING_V2": "false",
    "LANGSMITH_TRACING": "false",
    # Convention commune, lue par plusieurs bibliothèques.
    "DO_NOT_TRACK": "1",
}


def disable_telemetry(dotenv_path: str | Path | None = None) -> None:
    """Coupe les télémétries connues, sans écraser une valeur déjà définie (environnement,
    puis .env : le même que celui de src/core/config.py par défaut)."""
    load_dotenv(dotenv_path)
    for name, value in TELEMETRY_OPT_OUTS.items():
        os.environ.setdefault(name, value)
