"""L'Arène arrête un modèle qui tourne en boucle, qui atteint `arena.max_tokens`, ou à la demande
(story 9.2), dans un vrai navigateur : texte et icône de la colonne, bouton « Arrêter ce modèle »,
réponse partielle gardée, les autres colonnes continuent."""

from __future__ import annotations

import pytest

from .test_arena import DONE, banner, lane, launch, open_arena, scripted, status_of, wait_banner


@pytest.fixture
def arena(page, server):
    open_arena(page, server)
    return page


def test_a_lane_that_hits_max_tokens_shows_the_stopped_status_and_keeps_the_others_running(
    arena, server
):
    scripted(
        arena,
        server,
        {
            "fake:a": [
                {"text": "Un "},
                {"text": "mot"},
                {"done": {**DONE, "finish_reason": "length"}},
            ],
            "fake:b": [{"text": "ok"}, {"done": DONE}],
        },
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert status_of(arena, "fake:a") == "Arrêté : longueur maximale atteinte"
    assert lane(arena, "fake:a").locator(".wl-md").inner_text().strip() == "Un mot"
    assert status_of(arena, "fake:b") == "Terminé"  # fin naturelle : jamais une raison d'arrêt


def test_a_repeating_lane_is_stopped_with_the_loop_status_while_the_other_lane_finishes(
    arena, server
):
    sentence = "Je ne sais pas comment répondre à cette question précise. "  # ~60 caractères
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": sentence} for _ in range(8)],  # jamais tous livrés si vue
            "fake:b": [{"text": "ok"}, {"done": DONE}],
        },
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert status_of(arena, "fake:a") == "Arrêté : le modèle se répétait"
    text_a = lane(arena, "fake:a").locator(".wl-md").inner_text().strip()
    assert len(text_a) < len(sentence) * 8  # arrêtée avant la fin du script
    assert status_of(arena, "fake:b") == "Terminé"


def test_stopping_one_lane_keeps_the_other_running_and_notes_the_partial(arena, server):
    scripted(
        arena,
        server,
        {
            "fake:a": [{"text": "Partiel"}, {"sleep_s": 30}, {"text": "Jamais"}],
            "fake:b": [{"sleep_s": 0.2}, {"text": "ok"}, {"done": DONE}],
        },
    )
    launch(arena)
    lane(arena, "fake:a").locator(".wl-md").filter(has_text="Partiel").wait_for()
    lane(arena, "fake:a").get_by_role("button", name="Arrêter ce modèle").click()
    wait_banner(arena, "Comparaison terminée")  # l'arrêt d'une lane n'est pas un arrêt du run
    assert status_of(arena, "fake:a") == "Arrêté à la demande"
    assert lane(arena, "fake:a").locator(".wl-md").inner_text().strip() == "Partiel"
    assert status_of(arena, "fake:b") == "Terminé"  # l'autre lane a continué et fini normalement
    # Le bouton disparaît avec la colonne terminée ; la note du juge existe (notée, pas sautée).
    assert lane(arena, "fake:a").get_by_role("button", name="Arrêter ce modèle").is_hidden()
    assert lane(arena, "fake:a").locator(".wl-lane-score").is_visible()


def test_the_stop_button_only_shows_while_a_lane_is_in_progress(arena, server):
    scripted(
        arena,
        server,
        {"fake:a": [{"text": "ok"}, {"done": DONE}], "fake:b": [{"text": "ok"}, {"done": DONE}]},
    )
    launch(arena)
    wait_banner(arena, "Comparaison terminée")
    assert lane(arena, "fake:a").get_by_role("button", name="Arrêter ce modèle").is_hidden()
    assert banner(arena).inner_text().startswith("Comparaison terminée · 2 sur 2")
