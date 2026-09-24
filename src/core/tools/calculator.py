# src/core/tools/calculator.py
"""Outil de calcul sécurisé."""

import logging
import re

import numexpr
from func_timeout import FunctionTimedOut, func_timeout
from langchain_core.tools import tool

from src.core.config import CALCULATOR_TIMEOUT

logger = logging.getLogger(__name__)

# Pattern pour valider les expressions mathématiques
SAFE_MATH_PATTERN = re.compile(r"^[\d\s\+\-\*\/\.\(\)\%\^\,e]+$")

# Métadonnées de l'outil
TOOL_METADATA = {
    "name": "🧮 Calculator",
    "description": "Calculs mathématiques",
    "category": "computation",
    "requires_config": False,
}


def _safe_eval(expression: str) -> float:
    """Évalue une expression mathématique de manière sécurisée."""
    expr_clean = expression.replace("^", "**").replace(",", ".")

    if not SAFE_MATH_PATTERN.match(expr_clean.replace("**", "^")):
        raise ValueError(f"Expression non autorisée: {expression}")

    return float(numexpr.evaluate(expr_clean))


@tool
def calculator(expression: str) -> str:
    """
    Effectue un calcul mathématique sécurisé.

    Args:
        expression: Expression mathématique (ex: "2 + 2", "sqrt(16)", "3.14 * 2^2")

    Returns:
        Résultat du calcul ou message d'erreur
    """
    try:
        result = func_timeout(CALCULATOR_TIMEOUT, _safe_eval, args=(expression,))
        return f"Résultat: {result}"
    except FunctionTimedOut:
        return f"Erreur: Calcul trop long (>{CALCULATOR_TIMEOUT}s)"
    except Exception as e:
        return f"Erreur de calcul: {e}"
