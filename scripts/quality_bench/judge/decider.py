"""Perplexity Decider v1.1 hébergé (repli si Winnow est inutilisable, AD-16).

Même contrat ``/v1/systemone`` que le juge local, sur un point d'accès hébergé (https), avec
une clé d'API lue dans l'environnement et un coût par requête. Juge cloud : les questions
privées sont refusées avant tout envoi, et le plafond ``--max-cost-usd`` s'applique. Le point
d'accès n'est pas encore relevé : ``endpoint: null`` dans ``judges.yaml`` refuse le lancement.
"""

from __future__ import annotations

from .systemone import SystemOneJudge


class DeciderJudge(SystemOneJudge):
    """Juge ``/v1/systemone`` hébergé (``local: false``)."""
