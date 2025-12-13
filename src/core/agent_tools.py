import numexpr
from langchain_core.tools import tool
import datetime
import unicodedata
import operator

# --- Helper de Normalisation ---
def remove_accents(input_str):
    """
    Normalise une chaîne de caractères :
    - Décompose les caractères (ex: 'ë' devient 'e' + '¨')
    - Garde uniquement les caractères de base (supprime les marques)
    - Met tout en minuscules
    """
    if not isinstance(input_str, str):
        return str(input_str)
        
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)]).lower()

# Définition des outils via le décorateur @tool qui permet à LangChain 
# de comprendre automatiquement la description et les arguments.

@tool
def get_current_time():
    """Retourne la date et l'heure actuelle précise."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def calculator(expression: str) -> str:
    """
    Effectue un calcul mathématique sécurisé. 
    L'entrée doit être une expression mathématique simple (ex: '2 + 2' ou '3 * (12/4)').
    """
    try:
        # 1. Nettoyage préventif (Whitelisting strict)
        # On ne garde que les chiffres, les opérateurs basiques et les parenthèses
        # Cela bloque les tentatives d'injection type "__import__('os')..."
        allowed_chars = "0123456789+-*/().% "
        if not all(c in allowed_chars for c in expression):
            return "Erreur de sécurité : Caractères non autorisés dans le calcul."

        # 2. Évaluation via Moteur Sécurisé (numexpr)
        # numexpr est isolé et ne peut pas exécuter de code Python arbitraire
        result = numexpr.evaluate(expression).item()
        
        return str(result)
        
    except Exception as e:
        return f"Erreur de calcul : {e}"

@tool
def search_wavestone_internal(query: str) -> str:
    """
    Simule un moteur de recherche interne à l'entreprise Wavestone.
    Utilise cet outil pour chercher des informations sur les employés, les projets ou les politiques RH.
    """
    # Base de connaissances simulée
    knowledge = {
        "meteo": "Il fait toujours beau dans le Cloud, mais gris à Paris aujourd'hui (12°C).",
        "anael": "Anaël est un consultant IA Senior spécialisé dans le GenAI.",
        "pue": "Le PUE moyen des datacenters Wavestone est de 1.4.",
        "politique": "La politique Green IT impose d'éteindre les GPU le week-end."
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

# Liste exportée pour l'import dans le moteur
AVAILABLE_TOOLS = [get_current_time, calculator, search_wavestone_internal]