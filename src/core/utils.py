# src/core/utils.py
"""
Utilitaires partagés pour le projet WaveLocalAI.
Centralise les fonctions dupliquées à travers les modules.
"""

# Réexport de extract_thought depuis models_db (source de vérité historique)
from src.core.models_db import extract_thought


def extract_params_billions(val: str | int | float) -> float:
    """
    Extrait le nombre de paramètres en milliards (float) depuis une chaîne.
    Formats supportés :
    - "7B" → 7.0
    - "1.5B" → 1.5
    - "8x7B" → 56.0 (MoE)
    - "500M" → 0.5
    - 7 → 7.0
    Args:
        val: Valeur à parser (str, int ou float)
    Returns:
        float: Nombre de paramètres en milliards, 0.0 si non parsable
    """
    if isinstance(val, (int, float)):
        return float(val)
    if not val or not isinstance(val, str):
        return 0.0
    s = val.upper().strip().replace(" ", "")
    try:
        # Format MoE : "8x7B" → 56.0
        if "X" in s and "B" in s:
            parts = s.replace("B", "").split("X")
            return float(parts[0]) * float(parts[1])
        # Format standard : "7B" → 7.0
        if s.endswith("B"):
            return float(s[:-1])
        # Format millions : "500M" → 0.5
        if s.endswith("M"):
            return float(s[:-1]) / 1000.0
        # Format numérique pur
        if s.replace(".", "").isdigit():
            return float(s)
    except (ValueError, IndexError):
        pass
    return 0.0


__all__ = ["extract_params_billions", "extract_thought"]
