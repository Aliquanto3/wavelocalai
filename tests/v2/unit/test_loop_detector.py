"""Détecteur de boucle de l'Arène (story 9.2) : faux positifs à zéro sur des listes, des tableaux
Markdown et du code ; vrais positifs sur une phrase ou un paragraphe répétés."""

from __future__ import annotations

from wavelocalai.inference.loop_detector import LoopDetector, repeated_tail

MIN_REPEATS = 4
WINDOW = 200


def is_loop(text: str, *, min_repeats: int = MIN_REPEATS, window_chars: int = WINDOW) -> bool:
    return repeated_tail(text, min_repeats=min_repeats, window_chars=window_chars)


# --- Faux positifs : listes, tableaux, code --------------------------------------------------


def test_a_bulleted_list_of_distinct_items_is_not_a_loop():
    items = [
        "- Les plantes captent la lumière du soleil.",
        "- Elles absorbent du dioxyde de carbone.",
        "- Elles rejettent de l'oxygène dans l'air.",
        "- Cette réaction s'appelle la photosynthèse.",
        "- Elle se produit surtout dans les feuilles.",
        "- La chlorophylle donne sa couleur verte à la plante.",
    ]
    assert not is_loop("\n".join(items))


def test_a_numbered_list_with_similar_short_lines_is_not_a_loop():
    items = [f"{n}. Étape {n} : vérifier la configuration." for n in range(1, 9)]
    assert not is_loop("\n".join(items))


def test_a_markdown_table_with_varying_rows_is_not_a_loop():
    rows = [
        "| Modèle | Score | Débit |",
        "| --- | --- | --- |",
        "| fake:a | 82 | 12.4 |",
        "| fake:b | 75 | 9.1 |",
        "| fake:c | 91 | 15.3 |",
        "| fake:d | 68 | 7.8 |",
    ]
    assert not is_loop("\n".join(rows))


def test_a_markdown_table_with_a_repeated_short_separator_is_not_a_loop():
    # Le séparateur d'en-tête ("| --- | --- |", ~16 car.) est plus court que le plancher de
    # fragment du détecteur (8 car.) * un seul exemplaire : jamais répété dans un tableau normal.
    text = "| --- | --- |\n" * 1 + "| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |\n| 7 | 8 |\n"
    assert not is_loop(text)


def test_python_code_with_similar_but_distinct_lines_is_not_a_loop():
    code = "\n".join(f"    assert compute(x={n}) == {n * n}  # cas n° {n}" for n in range(1, 10))
    assert not is_loop(code)


def test_repeated_short_indentation_in_code_stays_under_the_window():
    # Des lignes vides indentées identiques, mais trop peu de caractères pour atteindre la fenêtre.
    assert not is_loop("    pass\n" * 4)


# --- Vrais positifs : phrase ou paragraphe répétés -------------------------------------------


def test_a_repeated_sentence_past_the_window_is_a_loop():
    sentence = "Je ne sais pas comment répondre à cette question précise. "
    assert len(sentence) * MIN_REPEATS >= WINDOW
    assert is_loop(sentence * MIN_REPEATS)


def test_a_repeated_paragraph_is_a_loop():
    paragraph = "La photosynthèse transforme la lumière en énergie chimique dans la feuille.\n\n"
    assert is_loop(paragraph * 6)


def test_many_repeats_of_a_shorter_fragment_also_trigger():
    fragment = "boucle "  # 7 caractères : en dessous du plancher seul, mais répété massivement
    assert not is_loop(fragment * 3)  # trop peu de répétitions, fenêtre non couverte
    assert is_loop(fragment * 40)


def test_a_sentence_repeated_just_under_the_threshold_is_not_a_loop():
    sentence = "Un paragraphe correct qui ne se répète que trois fois dans la réponse. "
    assert not is_loop(sentence * (MIN_REPEATS - 1))


# --- `LoopDetector` : vérifie sans refaire le travail à chaque caractère ----------------------


def test_loop_detector_feed_matches_repeated_tail_once_the_window_is_reached():
    detector = LoopDetector(MIN_REPEATS, WINDOW)
    sentence = "Je ne sais pas comment répondre à cette question précise. "
    text = ""
    seen_loop = False
    for _ in range(MIN_REPEATS + 2):
        text += sentence
        seen_loop = detector.feed(text) or seen_loop
    assert seen_loop


def test_loop_detector_feed_is_false_on_normal_prose():
    detector = LoopDetector(MIN_REPEATS, WINDOW)
    prose = (
        "La photosynthèse est le processus par lequel les plantes convertissent la lumière du "
        "soleil, l'eau et le dioxyde de carbone en glucose et en oxygène, grâce à la chlorophylle "
        "présente dans leurs feuilles vertes."
    )
    assert detector.feed(prose) is False
