"""Faux serveur SMTP local pour les tests de l'envoi d'email (story 6.3).

Il écoute en processus sur `127.0.0.1`, port éphémère : aucun vrai serveur n'est jamais joint. Il
parle assez de SMTP pour `smtplib` (EHLO, AUTH PLAIN, MAIL, RCPT, DATA, QUIT), garde chaque message
reçu et chaque tentative d'authentification, et refuse un mauvais identifiant. `starttls=True` le
fait annoncer STARTTLS puis couper la connexion à la commande : le client doit alors échouer sans
avoir envoyé le mot de passe.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.message import EmailMessage


@dataclass
class Received:
    sender: str
    recipients: list[str]
    raw: bytes

    def parsed(self) -> EmailMessage:
        message = message_from_bytes(self.raw, policy=policy.default)
        assert isinstance(message, EmailMessage)
        return message

    @property
    def text(self) -> str:
        return self.parsed().get_content().replace("\r\n", "\n").strip()

    @property
    def subject(self) -> str:
        return str(self.parsed()["Subject"])


@dataclass
class FakeSmtp:
    user: str = "moi@example.org"
    password: str = "pw-smtp-0123456789"
    starttls: bool = False
    refuse_recipients: tuple[str, ...] = ()
    messages: list[Received] = field(default_factory=list)
    auth_attempts: list[tuple[str, str]] = field(
        default_factory=list
    )  # (identifiant, mot de passe)
    connections: int = 0
    port: int = 0
    _server: asyncio.AbstractServer | None = None

    async def __aenter__(self) -> FakeSmtp:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    def settings(self, **extra: object) -> dict[str, object]:
        """Section `smtp` de `make_settings` qui vise ce faux serveur."""
        return {
            "server": "127.0.0.1",
            "port": self.port,
            "user": self.user,
            "password": self.password,
            **extra,
        }

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1

        async def say(line: str) -> None:
            writer.write(f"{line}\r\n".encode())
            await writer.drain()

        sender, recipients, authed = "", [], False
        try:
            await say("220 fake ESMTP")
            while line := (await reader.readline()).decode(errors="replace").rstrip("\r\n"):
                verb = line.split(" ", 1)[0].upper()
                if verb in ("EHLO", "HELO"):
                    await say("250-fake")
                    if self.starttls:
                        await say("250-STARTTLS")
                    await say("250 AUTH PLAIN")
                elif verb == "STARTTLS":
                    await say("220 Ready to start TLS")
                    break  # la poignée de main échouera côté client : aucun mot de passe ne part
                elif verb == "AUTH":
                    parts = line.split(" ")
                    raw = base64.b64decode(parts[2]).split(b"\0") if len(parts) > 2 else []
                    login = (raw[1].decode(), raw[2].decode()) if len(raw) == 3 else ("", "")
                    self.auth_attempts.append(login)
                    authed = login == (self.user, self.password)
                    await say("235 2.7.0 Authentication successful" if authed else "535 5.7.8 Bad")
                elif verb == "MAIL":
                    sender, recipients = line.split(":", 1)[1].strip(" <>"), []
                    await say("250 OK" if authed else "530 5.7.0 Authentication required")
                elif verb == "RCPT":
                    rcpt = line.split(":", 1)[1].strip(" <>")
                    if rcpt in self.refuse_recipients:
                        await say("550 5.1.1 Unknown user")
                    else:
                        recipients.append(rcpt)
                        await say("250 OK")
                elif verb == "DATA":
                    await say("354 End data with <CR><LF>.<CR><LF>")
                    lines: list[bytes] = []
                    while (data := await reader.readline()).rstrip(b"\r\n") != b".":
                        lines.append(data[1:] if data.startswith(b"..") else data)
                    self.messages.append(Received(sender, recipients, b"".join(lines)))
                    await say("250 OK queued")
                elif verb == "QUIT":
                    await say("221 Bye")
                    break
                else:
                    await say("502 5.5.2 Command not recognized")
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
