# src/core/tools/email_tools.py
"""Outils d'envoi d'email (simulation)."""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

TOOL_METADATA = {
    "name": "📧 Email Sender",
    "description": "Envoi d'emails",
    "category": "communication",
    "requires_config": True,
    "config_vars": ["SMTP_SERVER", "SMTP_USER", "SMTP_PASSWORD"],
}


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Simule l'envoi d'un email (mode demo).

    Args:
        to: Adresse email du destinataire
        subject: Sujet de l'email
        body: Corps du message

    Returns:
        Confirmation de l'envoi simulé
    """
    # Validation basique
    if "@" not in to:
        return f"Erreur: Adresse email invalide: {to}"

    if not subject.strip():
        return "Erreur: Le sujet ne peut pas être vide"

    logger.info(f"[DEMO] Email simulé vers {to}: {subject}")

    return f"""✅ Email simulé (mode démo):
- Destinataire: {to}
- Sujet: {subject}
- Longueur du corps: {len(body)} caractères

Note: En production, configurez SMTP dans .env"""
