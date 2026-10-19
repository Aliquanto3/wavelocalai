"""Outils de la v1 sans fichier : heure, calculatrice, recherche interne, moniteur système, email.

Copiés de `src/core/agent_tools.py` (les fonctions `_*_impl`, sans `@tool` LangChain) puis adaptés :
la v2 n'importe jamais `src.*`. Ce sont des fonctions synchrones ; `builtin.py` les passe à un fil
(`asyncio.to_thread`) pour ne pas bloquer la boucle d'événements. Les imports lourds (`numexpr`,
`func_timeout`, `psutil`) restent dans les fonctions.
"""

from __future__ import annotations

import datetime
import re

CALC_MAX_CHARS = 100
CALC_TIMEOUT_S = 2


def current_time() -> str:
    """Date et heure du poste, `AAAA-MM-JJ HH:MM:SS`."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calculate_safe(expression: str) -> str:
    """Calcul sécurisé : liste blanche stricte de caractères, longueur bornée, délai de 2 s."""
    import numexpr
    from func_timeout import FunctionTimedOut, func_timeout

    expression = str(expression)
    if len(expression) > CALC_MAX_CHARS:
        return f"Erreur : Expression trop longue (max {CALC_MAX_CHARS} caractères)"
    expression = " ".join(expression.split())
    if not expression.strip():
        return "Erreur : Expression vide"
    if not re.match(r"^[\d\s+\-*/().]+$", expression):
        return "Erreur : Caractères non autorisés. Utilisez uniquement : + - * / ( ) et nombres"
    if re.search(r"[+\-*/]{2,}", expression):
        return "Erreur : Opérateurs consécutifs détectés"
    if expression.count("(") != expression.count(")"):
        return "Erreur : Parenthèses non équilibrées"
    try:

        def _safe_eval():
            return numexpr.evaluate(expression).item()

        result = func_timeout(CALC_TIMEOUT_S, _safe_eval)
        if not isinstance(result, (int, float)):
            return "Erreur : Résultat invalide"
        if result == float("inf") or result == float("-inf"):
            return "Erreur : Résultat infini (division par zéro ou overflow)"
        if result != result:  # NaN
            return "Erreur : Résultat indéfini (NaN)"
        if isinstance(result, float):
            if abs(result - round(result)) < 1e-10:
                return str(int(round(result)))
            return f"{result:.10g}"
        return str(result)
    except FunctionTimedOut:
        return "Erreur : Calcul trop long (timeout 2s). Simplifiez l'expression"
    except ZeroDivisionError:
        return "Erreur : Division par zéro"
    except (ValueError, SyntaxError) as exc:
        return f"Erreur de syntaxe : {exc}"
    except Exception as exc:  # noqa: BLE001 - l'erreur de calcul est le résultat
        return f"Erreur de calcul : {exc}"


_INTERNAL_KNOWLEDGE = {
    "meteo": "Il fait toujours beau dans le Cloud, mais gris à Paris aujourd'hui (12°C).",
    "anael": "Anaël est un consultant IA Senior spécialisé dans le GenAI.",
    "pue": "Le PUE moyen des datacenters Wavestone est de 1.4.",
    "politique": "La politique Green IT impose d'éteindre les GPU le week-end.",
}


def search_wavestone(query: str) -> str:
    """Recherche dans la base interne simulée (quatre entrées, comme la v1)."""
    query = str(query).lower()
    results = [value for key, value in _INTERNAL_KNOWLEDGE.items() if key in query]
    if results:
        return "\n".join(results)
    return "Aucune information trouvée dans la base interne pour cette requête."


def system_report() -> str:
    """Métriques du poste (CPU, RAM, disque) avec alertes, au format de la v1."""
    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=False)
        cpu_count_logical = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        gb = 1024**3
        report = "**Monitoring Système**\n\n"
        report += "### CPU\n"
        report += f"- Utilisation : {cpu_percent}%\n"
        report += f"- Cœurs physiques : {cpu_count}\n"
        report += f"- Cœurs logiques : {cpu_count_logical}\n\n"
        report += "### RAM\n"
        report += f"- Total : {mem.total / gb:.2f} GB\n"
        report += f"- Utilisée : {mem.used / gb:.2f} GB ({mem.percent}%)\n"
        report += f"- Disponible : {mem.available / gb:.2f} GB\n\n"
        report += "### Disque (/)\n"
        report += f"- Total : {disk.total / gb:.2f} GB\n"
        report += f"- Utilisé : {disk.used / gb:.2f} GB ({disk.percent}%)\n"
        report += f"- Libre : {disk.free / gb:.2f} GB\n\n"
        if mem.percent > 90:
            report += "**ALERTE** : RAM critique (>90%)\n"
        elif mem.percent > 80:
            report += "Attention : RAM élevée (>80%)\n"
        if disk.percent > 90:
            report += "**ALERTE** : Disque critique (>90%)\n"
        elif disk.percent > 80:
            report += "Attention : Disque élevé (>80%)\n"
        return report
    except Exception as exc:  # noqa: BLE001 - l'erreur de lecture est le résultat
        return f"Erreur lors du monitoring : {exc}"


# --- email (le brouillon ; l'envoi est dans `agents/outbox.py`, story 6.3) -------------------------------------------------------


def validate_email(to: str, subject: str, body: str) -> str | None:
    """Message d'erreur si le destinataire, l'objet ou le corps est invalide ; `None` sinon."""
    if not to or "@" not in str(to):
        return "Erreur : Adresse email invalide"
    if not subject or len(str(subject)) > 200:
        return "Erreur : Sujet manquant ou trop long (max 200 caractères)"
    if not body or len(str(body)) > 10000:
        return "Erreur : Corps du message manquant ou trop long (max 10000 caractères)"
    return None


def draft_email(to: str, subject: str, body: str) -> str:
    """Contrôle d'un brouillon d'email : **rien n'est envoyé**, ni ici ni jamais par cette fonction
    (D2, AD-9). La boucle demande ensuite la validation de l'utilisateur, puis l'envoi est
    `agents/outbox.py` (story 6.3)."""
    error = validate_email(to, subject, body)
    if error:
        return error
    return (
        f"Brouillon d'email préparé pour {to} (objet : « {subject} »). Il n'est pas envoyé : "
        "l'utilisateur doit le relire et valider l'envoi dans l'interface. Indique-lui que "
        "l'email attend sa validation."
    )


def smtp_missing_help(missing: list[str]) -> str:
    """Raison d'indisponibilité de l'outil d'email : variables à renseigner dans `.env`."""
    names = ", ".join(missing) or "SMTP_USER, SMTP_PASSWORD"
    return (
        f"Configuration SMTP absente : renseignez {names} dans le fichier .env, puis redémarrez "
        "l'application. SMTP_SERVER vaut smtp.gmail.com par défaut et SMTP_PORT 587."
    )
