"""
CO₂ d'une réponse, règle unique des onglets de l'application (Chat libre, agent seul, Arène,
Banc d'essai, Discussion et évaluation de la qualité de l'Assistant documentaire).

La formule suit l'origine réelle du modèle, celle de son badge (`is_cloud`) : un tag distant
servi par Ollama (`glm-4.6:cloud`) n'a jamais de CO₂ local. Les formules restent celles de
`CarbonCalculator`, qui n'est pas modifié ici.
"""

import math

from src.core.green_monitor import CarbonCalculator
from src.core.models_db import get_friendly_name_from_tag, get_model_info
from src.core.utils import extract_params_billions

MG_PER_G = 1000.0


def answer_carbon_mg(
    model_tag: str | None, output_tokens, is_cloud: bool | None = None
) -> float | None:
    """CO₂ d'une réponse en mg, d'après le nombre de tokens générés.

    - `is_cloud` vrai : formule cloud, avec la taille du catalogue (paramètres actifs, sinon
      totaux) ; `is_cloud` faux : formule locale ; `is_cloud` inconnu (None) : type du
      catalogue.
    - La fiche est cherchée par le nom du catalogue déduit du tag, jamais par un libellé de
      sélecteur.

    Returns:
        Le CO₂ en mg (0.0 pour 0 token), ou None s'il est inconnu : tag absent, nombre de
        tokens absent, booléen, non fini ou négatif, catalogue illisible, ou modèle cloud de
        taille inconnue (tag distant hors catalogue). Jamais 0 pour une valeur inconnue ; ne
        lève jamais d'exception.
    """
    if not model_tag or isinstance(output_tokens, bool):
        return None
    if not isinstance(output_tokens, (int, float)) or not math.isfinite(output_tokens):
        return None
    if output_tokens < 0:
        return None
    tokens = int(output_tokens)
    if tokens == 0:
        return 0.0  # Aucun token généré : 0 quelle que soit la formule (taille inutile).
    try:
        info = get_model_info(get_friendly_name_from_tag(model_tag)) or {}
    except Exception:
        return None  # Catalogue illisible : CO₂ inconnu, jamais d'exception.
    cloud = is_cloud if is_cloud is not None else info.get("type") == "api"
    if cloud:
        raw_params = info.get("params_act") or info.get("params_tot") or "0"
        active_params = extract_params_billions(raw_params)
        if not active_params or active_params <= 0:
            return None
        carbon_g = CarbonCalculator.compute_mistral_impact_g(active_params, tokens)
    else:
        carbon_g = CarbonCalculator.compute_local_theoretical_g(tokens)
    return carbon_g * MG_PER_G


__all__ = ["answer_carbon_mg"]
