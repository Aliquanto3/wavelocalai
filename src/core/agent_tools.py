import datetime
import re
import unicodedata

import numexpr
from func_timeout import FunctionTimedOut, func_timeout
from langchain_core.tools import tool


# --- Helper de Normalisation ---
def remove_accents(input_str):
    """Normalise une chaîne de caractères."""
    if not isinstance(input_str, str):
        return str(input_str)
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()


# ========================================
# LOGIQUE PURE (Sans décorateurs)
# ========================================


def _calculate_safe(expression: str) -> str:
    """
    Logique pure de calcul sécurisé (testable directement).

    Cette fonction contient toute la logique métier sans dépendance
    au framework LangChain, ce qui facilite les tests unitaires.
    """
    # 1. Validation de la longueur
    if len(expression) > 100:
        return "❌ Erreur : Expression trop longue (max 100 caractères)"

    # 2. Nettoyage préventif des espaces multiples
    expression = " ".join(expression.split())

    # 3. Protection contre les expressions vides (DÉPLACÉ AVANT LA REGEX)
    if not expression.strip():
        return "❌ Erreur : Expression vide"

    # 4. Whitelist STRICTE (APRÈS LA VÉRIFICATION VIDE)
    if not re.match(r"^[\d\s+\-*/().]+$", expression):
        return "❌ Erreur : Caractères non autorisés. Utilisez uniquement : + - * / ( ) et nombres"

    # 5. Détection d'opérateurs consécutifs
    if re.search(r"[+\-*/]{2,}", expression):
        return "❌ Erreur : Opérateurs consécutifs détectés"

    # 6. Vérification des parenthèses équilibrées
    if expression.count("(") != expression.count(")"):
        return "❌ Erreur : Parenthèses non équilibrées"

    try:
        # 7. Évaluation avec TIMEOUT de 2 secondes
        def _safe_eval():
            return numexpr.evaluate(expression).item()

        result = func_timeout(2, _safe_eval)

        # 8. Validation du résultat
        if not isinstance(result, (int, float)):
            return "❌ Erreur : Résultat invalide"

        # 9. Détection des valeurs spéciales (inf, nan)
        if result == float("inf") or result == float("-inf"):
            return "❌ Erreur : Résultat infini (division par zéro ou overflow)"

        if result != result:  # Test pour NaN
            return "❌ Erreur : Résultat indéfini (NaN)"

        # 10. Formatage du résultat
        if isinstance(result, float):
            if abs(result - round(result)) < 1e-10:
                return str(int(round(result)))
            else:
                return f"{result:.10g}"

        return str(result)

    except FunctionTimedOut:
        return "❌ Erreur : Calcul trop long (timeout 2s). Simplifiez l'expression"

    except ZeroDivisionError:
        return "❌ Erreur : Division par zéro"

    except (ValueError, SyntaxError) as e:
        return f"❌ Erreur de syntaxe : {str(e)}"

    except Exception as e:
        return f"❌ Erreur de calcul : {str(e)}"


def _get_current_time_impl() -> str:
    """Logique pure pour récupérer l'heure."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _search_wavestone_impl(query: str) -> str:
    """Logique pure pour la recherche interne."""
    knowledge = {
        "meteo": "Il fait toujours beau dans le Cloud, mais gris à Paris aujourd'hui (12°C).",
        "anael": "Anaël est un consultant IA Senior spécialisé dans le GenAI.",
        "pue": "Le PUE moyen des datacenters Wavestone est de 1.4.",
        "politique": "La politique Green IT impose d'éteindre les GPU le week-end.",
    }

    query = query.lower()
    results = []
    for key, value in knowledge.items():
        if key in query:
            results.append(value)

    if results:
        return "\n".join(results)
    else:
        return "Aucune information trouvée dans la base interne pour cette requête."


# ========================================
# WRAPPERS LANGCHAIN (Outils pour agents)
# ========================================


@tool
def get_current_time():
    """Retourne la date et l'heure actuelle précise."""
    return _get_current_time_impl()


@tool
def calculator(expression: str) -> str:
    """
    Effectue un calcul mathématique sécurisé avec timeout et validation stricte.

    Limitations de sécurité :
    - Longueur max : 100 caractères
    - Timeout : 2 secondes
    - Opérateurs autorisés : + - * / ( ) . (espaces et chiffres)

    Exemples valides :
    - "2 + 2"
    - "3.14 * (12/4)"
    - "100 / 3"
    """
    return _calculate_safe(expression)


@tool
def search_wavestone_internal(query: str) -> str:
    """
    Simule un moteur de recherche interne à l'entreprise Wavestone.
    Utilise cet outil pour chercher des informations sur les employés, les projets ou les politiques RH.
    """
    return _search_wavestone_impl(query)


# Liste exportée pour l'import dans le moteur
AVAILABLE_TOOLS = [get_current_time, calculator, search_wavestone_internal]
