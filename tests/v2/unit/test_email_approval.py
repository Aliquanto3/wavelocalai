"""L'envoi d'email derrière la validation : brouillon, transport, et absence de tout autre chemin
(story 6.3, AD-9, D2).

Le seul serveur joint est le faux SMTP local de `tests/v2/fake_smtp.py` (`127.0.0.1`, port éphémère).
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from wavelocalai.agents import outbox
from wavelocalai.agents.outbox import EmailAction, check_draft, deliver
from wavelocalai.agents.tools import ToolError
from wavelocalai.config import SmtpSettings

from ..fake_smtp import FakeSmtp

SRC = Path(__file__).resolve().parents[3] / "src" / "wavelocalai"
GOOD = ("client@example.org", "Objet", "Corps du message")


def _smtp(fake: FakeSmtp, **extra) -> SmtpSettings:
    return SmtpSettings(**fake.settings(**extra))


# --- le brouillon --------------------------------------------------------------------------------


def test_a_valid_draft_is_kept_as_written():
    assert check_draft(" client@example.org ", "Objet", "Ligne 1\nLigne 2") == (
        "client@example.org", "Objet", "Ligne 1\nLigne 2",
    )  # fmt: skip


@pytest.mark.parametrize(
    ("to", "subject", "body", "message"),
    [
        ("", "S", "B", "Adresse email invalide"),
        ("sans-arobase", "S", "B", "Adresse email invalide"),
        ("a@b.c", "", "B", "Sujet manquant"),
        ("a@b.c", "x" * 201, "B", "trop long"),
        ("a@b.c", "S", "x" * 10001, "trop long"),
        ("a@b.c, d@e.f", "S", "B", "un seul destinataire"),
        ("a@b.c;d@e.f", "S", "B", "un seul destinataire"),
        ("a b@c.d", "S", "B", "un seul destinataire"),
        ("Nom <a@b.c>", "S", "B", "un seul destinataire"),
        ("a@b.c\nBcc: x@y.z", "S", "B", "un seul destinataire"),
        ("a@b.c", "S\r\nBcc: x@y.z", "B", "une seule ligne"),
    ],
)
def test_an_invalid_draft_is_a_tool_error(to, subject, body, message):
    with pytest.raises(ToolError, match=message):
        check_draft(to, subject, body)


def test_the_action_is_prepared_as_shown_whatever_happens_to_the_arguments_after():
    smtp = SmtpSettings(server="127.0.0.1", user="moi@example.org", password="pw-smtp-0123456789")
    arguments = {"to": GOOD[0], "subject": GOOD[1], "body": GOOD[2]}
    pending = EmailAction(smtp).prepare(arguments)
    assert pending.kind == "email"
    assert pending.details == {"destinataire": GOOD[0], "objet": GOOD[1], "corps": GOOD[2]}
    arguments["to"] = "autre@example.org"  # ce qui part est ce qui a été montré, pas ceci
    assert pending.details["destinataire"] == GOOD[0]


def test_without_smtp_the_action_cannot_even_be_prepared():
    with pytest.raises(ToolError, match="Configuration SMTP absente"):
        EmailAction(SmtpSettings()).prepare({"to": GOOD[0], "subject": GOOD[1], "body": GOOD[2]})


# --- le transport --------------------------------------------------------------------------------


async def test_the_email_is_delivered_in_utf8_without_altering_the_text():
    body = "Bonjour,\n.Une ligne qui commence par un point\n..deux\nÀ bientôt — été ✓"
    async with FakeSmtp() as fake:
        await asyncio.to_thread(deliver, _smtp(fake), GOOD[0], "Réunion à 14 h", body)
    (message,) = fake.messages
    assert message.recipients == [GOOD[0]] and message.sender == "moi@example.org"
    assert message.subject == "Réunion à 14 h" and message.text == body


async def test_the_action_sends_only_when_it_is_executed():
    async with FakeSmtp() as fake:
        pending = EmailAction(_smtp(fake)).prepare(
            {"to": GOOD[0], "subject": GOOD[1], "body": GOOD[2]}
        )
        await asyncio.sleep(0.1)
        assert fake.connections == 0  # préparer ne se connecte à rien
        assert (await pending.execute()).startswith("Email envoyé à client@example.org")
    assert len(fake.messages) == 1


async def test_a_remote_server_without_starttls_never_receives_the_password(monkeypatch):
    # Ce poste n'a pas de serveur « distant » : on retire seulement 127.0.0.1 de la liste des
    # serveurs locaux pour que le faux soit traité comme distant.
    monkeypatch.setattr(outbox, "LOOPBACK_HOSTS", frozenset())
    async with FakeSmtp() as fake:
        with pytest.raises(ToolError, match="pas de connexion chiffrée"):
            await asyncio.to_thread(deliver, _smtp(fake), *GOOD)
    assert fake.auth_attempts == [] and fake.messages == []


async def test_starttls_is_negotiated_before_the_password_is_sent(monkeypatch):
    # Le faux annonce STARTTLS puis coupe : la négociation échoue, le mot de passe n'est pas parti.
    monkeypatch.setattr(outbox, "LOOPBACK_HOSTS", frozenset())
    async with FakeSmtp(starttls=True) as fake:
        with pytest.raises(ToolError):
            await asyncio.to_thread(deliver, _smtp(fake), *GOOD)
    assert fake.auth_attempts == [] and fake.messages == []


async def test_an_error_message_never_contains_the_password():
    async with FakeSmtp() as fake:
        wrong = _smtp(fake, password="pw-faux-9876543210")
        with pytest.raises(ToolError) as caught:
            await asyncio.to_thread(deliver, wrong, *GOOD)
    assert "authentification" in str(caught.value)
    assert "pw-faux-9876543210" not in str(caught.value) and fake.password not in str(caught.value)


# --- aucun autre chemin d'envoi, aucune approbation automatique --------------------------------


def _modules():
    for path in sorted(SRC.rglob("*.py")):
        yield path.relative_to(SRC).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_outbox_speaks_smtp():
    """Aucun autre module n'importe `smtplib` ; son import dans une fonction seulement est gardé par
    `LAZY_ONLY` de `test_layers.py`."""
    importers = {name for name, tree in _modules() if "smtplib" in _imported_roots(tree)}
    assert importers == {"agents/outbox.py"}


def test_the_tools_cannot_reach_the_outbox():
    for name, tree in _modules():
        if name.startswith("agents/tools/"):
            imported = {
                (node.module or "") if isinstance(node, ast.ImportFrom) else alias.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in getattr(node, "names", [])
            }
            assert not any("outbox" in item or "approval" in item for item in imported), name


def test_a_request_is_answered_from_the_route_only_and_approval_resolved_comes_from_the_hub():
    """Aucun chemin d'approbation automatique : `resolve_approval` n'est appelé que par la route
    d'approbation, et seul le hub publie `approval_resolved` (AD-9)."""
    callers, publishers = set(), set()
    for name, tree in _modules():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "resolve_approval":
                callers.add(name)
            if isinstance(node, ast.Constant) and node.value == "approval_resolved":
                publishers.add(name)
    assert callers == {"web/routes_agents.py"}
    assert publishers == {"runs/hub.py"}
