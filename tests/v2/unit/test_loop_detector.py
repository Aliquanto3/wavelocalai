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


def test_identical_rows_of_structured_data_are_not_a_loop():
    zeros = "[" + ", ".join(["0"] * 10) + "],\n"  # matrice de zéros 10 × 10
    assert not is_loop("matrice = [\n" + zeros * 10)
    grid = "+---+---+---+---+\n|   |   |   |   |\n"  # grille ASCII
    assert not is_loop(grid * 8)
    csv_rows = "2026-10-21,0,0,0,0.00\n"  # CSV de lignes identiques
    assert not is_loop("date,a,b,c,total\n" + csv_rows * 15)
    table = "| Oui | Oui | Oui | Non |\n"  # tableau Markdown de lignes identiques
    assert not is_loop("| A | B | C | D |\n| --- | --- | --- | --- |\n" + table * 12)
    objects = '  {"id": 0, "valeur": 0, "ok": true},\n'  # JSON d'objets identiques
    assert not is_loop("[\n" + objects * 10)


def test_repeated_identical_code_lines_are_not_a_loop():
    assert not is_loop("def init():\n" + "    x[0] = 0\n" * 30)


# --- Vrais positifs : phrase ou paragraphe répétés -------------------------------------------


def test_a_repeated_sentence_past_the_window_is_a_loop():
    sentence = "Je ne sais pas comment répondre à cette question précise. "
    assert len(sentence) * MIN_REPEATS >= WINDOW
    assert is_loop(sentence * MIN_REPEATS)


def test_a_repeated_paragraph_is_a_loop():
    paragraph = "La photosynthèse transforme la lumière en énergie chimique dans la feuille.\n\n"
    assert is_loop(paragraph * 6)


def test_a_long_repeated_paragraph_is_a_loop():
    paragraph = (
        "La photosynthèse est le processus par lequel les plantes vertes, les algues et certaines "
        "bactéries convertissent l'énergie lumineuse du soleil en énergie chimique. Elle se déroule "
        "dans les chloroplastes, grâce à la chlorophylle, et produit du glucose et de l'oxygène à "
        "partir d'eau et de dioxyde de carbone. Ce processus est essentiel à la vie sur Terre.\n\n"
    )
    assert 350 <= len(paragraph) <= 450
    assert not is_loop(paragraph * (MIN_REPEATS - 1))
    assert is_loop("Réponse :\n\n" + paragraph * MIN_REPEATS)
    detector = LoopDetector(MIN_REPEATS, WINDOW)
    fed = [detector.feed(word + " ") for word in (paragraph * (MIN_REPEATS + 1)).split(" ")]
    assert any(fed)


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
    seen_loop = False
    for _ in range(MIN_REPEATS + 2):
        for word in sentence.split(" "):  # jeton par jeton, comme le flux d'un adaptateur
            seen_loop = detector.feed(word + " ") or seen_loop
    assert seen_loop


def test_loop_detector_reset_forgets_the_previous_attempt():
    detector = LoopDetector(MIN_REPEATS, WINDOW)
    sentence = "Je ne sais pas comment répondre à cette question précise. "
    detector.feed(sentence * (MIN_REPEATS - 1))
    detector.reset()  # relance : la tentative précédente ne compte plus
    assert detector.feed(sentence) is False
    assert detector.feed(sentence * MIN_REPEATS) is True


def test_loop_detector_keeps_a_bounded_tail_on_a_long_answer():
    detector = LoopDetector(MIN_REPEATS, WINDOW)
    for n in range(5000):
        assert detector.feed(f"Phrase distincte numéro {n} de la réponse. ") is False
    assert len("".join(detector._parts)) <= MIN_REPEATS * 1000 + 100


def test_loop_detector_feed_is_false_on_normal_prose():
    detector = LoopDetector(MIN_REPEATS, WINDOW)
    prose = (
        "La photosynthèse est le processus par lequel les plantes convertissent la lumière du "
        "soleil, l'eau et le dioxyde de carbone en glucose et en oxygène, grâce à la chlorophylle "
        "présente dans leurs feuilles vertes."
    )
    assert detector.feed(prose) is False
