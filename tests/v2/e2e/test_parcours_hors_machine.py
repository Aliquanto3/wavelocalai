"""Aucune requête ne sort de 127.0.0.1, à l'échelle de la suite (story 8.3, NFR13).

Le garde a trois étages, tous dans `conftest.py` : Chromium sans service de fond, une route Playwright
sur chaque contexte qui bloque et relève toute URL hors de 127.0.0.1 (le test qui la provoque échoue),
et un bilan de session (`no_request_left_the_machine`) qui fait échouer la suite entière en fin de
course si une seule sortie a eu lieu. Ici, on prouve que le garde voit et bloque une sortie, et que
le bilan est vide au moment où ce fichier passe.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Error

from . import conftest
from .test_shell import wait_ready

OUTSIDE = "http://example.invalid/sortie"


def test_a_request_to_another_host_is_blocked_and_recorded_by_the_guard(
    page_tolerating_failed_requests, server, traffic
):
    page = page_tolerating_failed_requests
    page.goto(f"{server.base_url}/")
    wait_ready(page)
    with pytest.raises(Error):
        page.goto(OUTSIDE)  # la route du contexte coupe la navigation, rien ne part
    assert traffic.blocked == [OUTSIDE]
    assert OUTSIDE in traffic.urls
    # Le test a prouvé le garde : il retire cette sortie voulue, sinon la fixture `context` (et le bilan
    # de la suite) la compterait comme une fuite.
    traffic.blocked.clear()
    traffic.urls[:] = [url for url in traffic.urls if url != OUTSIDE]


def test_the_suite_summary_is_empty_and_checked_at_the_end_of_the_session(request):
    # Les tests passés avant celui-ci n'ont rien fait sortir ; la fixture de session est active.
    assert conftest.SUITE_OUTSIDE == []
    assert "no_request_left_the_machine" in request.fixturenames
