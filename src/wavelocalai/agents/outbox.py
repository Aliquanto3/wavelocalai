"""Envoi réel d'un email, après la validation de l'utilisateur seulement (story 6.3, AD-9, D2).

C'est le seul module de la v2 qui parle SMTP. Il n'est joignable que par `EmailAction.prepare`, dont
l'`execute` est appelé par la boucle après `approval_resolved {decision: "approved"}` : aucun outil
du registre ne l'importe (`tests/v2/unit/test_email_approval.py` le vérifie). Le texte envoyé est
exactement celui que `prepare` a montré. `smtplib` et `email` sont importés dans les fonctions.

Sécurité du transport : STARTTLS exigé (ou TLS implicite sur le port 465) avant d'envoyer le mot de
passe ; seul un serveur local (`127.0.0.1`, `localhost`, `::1` : relais de test) peut s'en passer.
Un destinataire unique, sans retour à la ligne : aucun en-tête ne peut être injecté.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from wavelocalai.agents.approval import PendingAction, SensitiveAction
from wavelocalai.agents.tools import ToolError
from wavelocalai.agents.tools.basic import smtp_missing_help, validate_email
from wavelocalai.config import Settings, SmtpSettings

SMTP_TIMEOUT_S = 30.0
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
IMPLICIT_TLS_PORT = 465
# Une seule adresse : ni espace, ni virgule ou point-virgule (plusieurs destinataires), ni chevrons.
_FORBIDDEN = r"@\s,;<>()\"'\\"
ADDRESS = re.compile(rf"^[^{_FORBIDDEN}]+@[^{_FORBIDDEN}]+$")


def check_draft(to: str, subject: str, body: str) -> tuple[str, str, str]:
    """Destinataire, objet et corps validés, ou `ToolError`. Les règles de la v1 (`validate_email`)
    plus un destinataire unique et aucun saut de ligne dans l'adresse ou l'objet."""
    error = validate_email(to, subject, body)
    if error:
        raise ToolError(error)
    to = str(to).strip()
    subject = str(subject)
    if not ADDRESS.match(to):
        raise ToolError("Erreur : un seul destinataire, sous la forme nom@domaine")
    if re.search(r"[\r\n]", subject):
        raise ToolError("Erreur : l'objet tient sur une seule ligne")
    return to, subject, str(body)


def deliver(smtp: SmtpSettings, to: str, subject: str, body: str) -> None:
    """Envoie l'email (bloquant : à appeler dans un fil). `ToolError` en français, sans mot de passe,
    si le serveur refuse, est injoignable ou n'offre pas de transport chiffré."""
    import smtplib
    import ssl
    from email.message import EmailMessage

    host = smtp.server.strip()
    loopback = host.lower() in LOOPBACK_HOSTS
    message = EmailMessage()
    message["From"] = smtp.user.strip()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body, subtype="plain", charset="utf-8")
    context = ssl.create_default_context()
    try:
        if smtp.port == IMPLICIT_TLS_PORT and not loopback:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                host, smtp.port, timeout=SMTP_TIMEOUT_S, context=context
            )
            encrypted = True
        else:
            # Relais local : nom EHLO fixe, sans `socket.getfqdn()` (résolution inverse de plusieurs
            # secondes sur les runners macOS) ; un vrai serveur garde le nom du poste.
            client = smtplib.SMTP(
                host,
                smtp.port,
                timeout=SMTP_TIMEOUT_S,
                local_hostname="localhost" if loopback else None,
            )
            encrypted = False
        with client:
            client.ehlo()
            if not encrypted:
                if client.has_extn("starttls"):
                    client.starttls(context=context)
                    client.ehlo()
                elif not loopback:
                    raise ToolError(
                        "Le serveur SMTP ne propose pas de connexion chiffrée (STARTTLS) : envoi "
                        "refusé pour ne pas faire circuler le mot de passe en clair."
                    )
            client.login(smtp.user.strip(), smtp.password.get_secret_value())
            client.send_message(message)
    except smtplib.SMTPAuthenticationError:
        raise ToolError(
            "Erreur d'authentification SMTP. Vérifiez SMTP_USER et SMTP_PASSWORD dans le fichier .env."
        ) from None
    except smtplib.SMTPRecipientsRefused:
        raise ToolError("Le serveur SMTP a refusé le destinataire : rien n'est parti.") from None
    except smtplib.SMTPException as exc:
        raise ToolError(f"Erreur SMTP : {exc}") from None
    except OSError as exc:  # injoignable, délai, certificat refusé
        reason = exc.strerror or type(exc).__name__
        raise ToolError(f"Serveur SMTP injoignable ({host}:{smtp.port}) : {reason}.") from None


class EmailAction:
    """« Envoi d'email » : prépare le brouillon, l'envoie quand la boucle l'ordonne."""

    def __init__(self, smtp: SmtpSettings) -> None:
        self._smtp = smtp

    def prepare(self, arguments: dict[str, Any]) -> PendingAction:
        to, subject, body = check_draft(
            arguments.get("to", ""), arguments.get("subject", ""), arguments.get("body", "")
        )
        missing = self._smtp.missing()
        if missing:
            raise ToolError(smtp_missing_help(missing))

        async def send() -> str:
            await asyncio.to_thread(deliver, self._smtp, to, subject, body)
            return f"Email envoyé à {to} (objet : « {subject} »)."

        return PendingAction("email", {"destinataire": to, "objet": subject, "corps": body}, send)


def build_actions(settings: Settings) -> dict[str, SensitiveAction]:
    """Actions sensibles de l'application, par identifiant d'outil."""
    return {"send_email": EmailAction(settings.smtp)}
