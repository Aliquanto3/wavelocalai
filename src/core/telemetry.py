"""
Télémétries des bibliothèques coupées : aucune télémétrie de bibliothèque n'est envoyée sans
action de l'utilisateur.

Chaque bibliothèque lit sa propre variable d'environnement, souvent au moment de son import :
`disable_telemetry()` doit donc s'exécuter avant. Appelants : l'app au démarrage (Accueil.py),
le lanceur e2e (tests/e2e/launch_app.py), et chaque module qui importe une bibliothèque à
télémétrie, juste avant cet import : eval_engine.py (Ragas), crew_engine.py (CrewAI),
rag/vector_store.py (Chroma), rag/models_factory.py (Hugging Face), rag/ingestion.py
(langchain_community, qui charge huggingface_hub), ainsi que scripts/setup_rag_models.py
(huggingface_hub). Tout nouveau module qui importe l'une de ces bibliothèques fait de même
(tests/unit/test_telemetry.py le vérifie).

Une valeur déjà définie, dans l'environnement ou dans le .env (lu ici d'abord, sans rien
écraser), l'emporte : c'est ainsi qu'on réactive volontairement une télémétrie
(LANGSMITH_TRACING=true avec LANGCHAIN_TRACING_V2=true, que LangSmith lit en premier…).
Streamlit est coupé à part, par `gatherUsageStats` dans .streamlit/config.toml. La liste est
documentée dans README.md (section « Télémétries »).

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
