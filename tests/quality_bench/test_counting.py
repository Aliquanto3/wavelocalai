"""Comptage déterministe en français et critères de rédaction vérifiés par le code (AD-10) :
mots, phrases, paragraphes, lignes, éléments de liste, corps de courriel, bornes, tolérance
« environ », forme du ``check`` et note du correcteur ``judge_criteria@2``. Textes synthétiques."""

from __future__ import annotations

import pytest

from scripts.quality_bench.grading import counting
from scripts.quality_bench.grading.counting import (
    count_words,
    email_body,
    evaluate_check,
    evaluate_checks,
    list_items,
    normalize_text,
    paragraphs,
    sentences,
)
from scripts.quality_bench.grading.registry import grade_line
from scripts.quality_bench.questions.checks import CheckError, validate_check, validate_checks
from scripts.quality_bench.questions.schema import QuestionError, validate_question, with_hashes

from .grading_factories import answer_output, generation_for
from .set_factories import synthetic_question

# -- Mots -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", 0),
        ("Bonjour tout le monde", 4),
        ("l'école d'aujourd'hui", 2),  # l'élision ne coupe pas
        ("l’élève et l’été", 3),  # apostrophe typographique
        ("peut-être c'est-à-dire vingt-deux", 3),  # le trait d'union ne coupe pas
        ("Il y a 1 450 tickets", 6),  # un nombre à espaces compte pour plusieurs mots
        ("12h30 et 3,5 kg", 4),
        ("Objet : demande de délai", 4),  # « : » isolé n'est pas un mot
        ("Bonjour — Madame », dit-il", 3),  # tiret, guillemet isolés
        ("« Salut ! »", 1),
        ("a b c", 3),  # espaces insécables
        ("ma​ison de﻿ campagne", 3),  # largeur nulle retirée
        ("- un\n- deux trois\n1. quatre\n2) cinq", 5),  # marqueurs de liste non comptés
        ("# Titre\n\nUn mot", 3),
        ("**Gras** et _italique_", 3),
        ("et/ou", 1),
    ],
)
def test_count_words(text, expected):
    assert count_words(normalize_text(text)) == expected


def test_normalization_is_nfc_and_line_endings():
    decomposed = "été\r\nfin\r"
    assert normalize_text(decomposed) == "été\nfin"
    assert count_words(normalize_text(decomposed)) == 2


# -- Phrases --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", 0),
        ("Une phrase.", 1),
        ("Une phrase. Une autre ! Et une troisième ?", 3),
        ("Une phrase sans point final", 1),
        ("M. Peyrac a écrit. Mme Dupont a répondu.", 2),  # abréviations
        ("Paul D. a appelé. Il rappellera.", 2),  # initiale
        ("Le tarif est de 4.2 euros. Merci.", 2),  # décimale
        ("Il hésite... puis part. Fin.", 2),  # points de suspension suivis d'une minuscule
        ("Il hésite… Puis il part.", 2),  # …, suivi d'une majuscule
        ("Elle dit : « Vraiment ? » dit-il.", 1),  # ? suivi de guillemet puis minuscule
        ("« Non. » Il sort.", 2),
        ("Pommes, poires, etc. et bananes. Merci.", 2),  # « etc. et » ne coupe pas
        ("Voir p. ex. la figure. Fin.", 2),
        ("Première ligne\nDeuxième ligne", 2),  # la ligne coupe
        ("- Un élément\n- Un autre élément.", 2),
        ("# Titre\nUne phrase.", 1),  # titre Markdown : pas une phrase
        ("**Titre**\nUne phrase.", 1),  # ligne en gras seule : pas une phrase
        ("---\nUne phrase.", 1),
        ("Attention ! Danger ! Fuyez !", 3),
        ("Le 3 mars 2025. Ensuite, rien.", 2),
        ("Voyez www.exemple.fr. Merci.", 2),
        (".  —  ...", 0),
    ],
)
def test_sentences(text, expected):
    assert len(sentences(normalize_text(text))) == expected


def test_sentence_text_is_returned_without_marker():
    assert sentences("- Un élément.\n2. Un autre.") == ["Un élément.", "Un autre."]


# -- Paragraphes, lignes, éléments de liste -------------------------------------------------


def test_paragraphs_ignore_extra_blank_lines_and_titles():
    text = (
        "# Titre\n\nPremier paragraphe\nsur deux lignes.\n\n\n   \nSecond.\n\n---\n\n**Intertitre**"
    )
    assert paragraphs(text) == ["Premier paragraphe\nsur deux lignes.", "Second."]


def test_a_title_with_a_text_line_is_a_paragraph():
    assert paragraphs("# Titre\nTexte du paragraphe.") == ["# Titre\nTexte du paragraphe."]


def test_empty_text_has_no_paragraph():
    assert paragraphs("") == [] and paragraphs("\n \n") == []


def test_list_items_by_marker():
    text = "Intro\n- puce a\n* puce b\n• puce c\n1. un\n2) deux\n— réplique\n3. trois"
    assert len(list_items(text, "bullet")) == 4  # - * • et —
    assert list_items(text, "number") == ["un", "deux", "trois"]
    assert list_items(text, "dash") == ["puce a", "réplique"]
    assert len(list_items(text, "any")) == 7  # puces et numéros, pas la ligne d'introduction


def test_list_item_continuation_lines_are_joined():
    text = "- premier\n  suite du premier\n- second\nTexte hors liste\n  indentée sans élément"
    assert list_items(text, "bullet") == ["premier suite du premier", "second"]


def test_nested_bullets_extend_the_top_level_item():
    text = "- a\n  - a1\n  - a2\n- b\n\t* b1\n- c"
    assert list_items(text, "bullet") == ["a - a1 - a2", "b * b1", "c"]
    assert len(list_items("  - a\n  - b", "bullet")) == 2  # liste entière indentée
    assert list_items("1. a\n   - x\n2. b", "number", sequential=True) == ["a - x", "b"]
    assert evaluate_check({"count": "items", "op": "<=", "n": 3}, text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Elle a couru 2 m. Elle s'arrête.", 2),
        ("Il marche 5 km. Puis il rentre.", 2),
        ("Réponse : B. Ensuite on voit.", 2),
        ("La bonne réponse B. Ensuite rien.", 2),
        ("Selon J. Dupont, oui. Non.", 2),  # initiale
        ("Le c.-à-d. Paris est loin.", 1),
        ("Il y a 3 MM. Dupont ici.", 1),  # « MM. » en majuscules : titre
    ],
)
def test_sentence_units_answer_letters_and_abbreviations(text, expected):
    assert len(sentences(text)) == expected


def test_sequential_numbering():
    assert list_items("1. a\n2. b\n3. c", "number", sequential=True) == ["a", "b", "c"]
    assert list_items("1. a\n3. b", "number", sequential=True) is None
    assert list_items("2. a\n3. b", "number", sequential=True) is None
    assert list_items("1. a\n1. b", "number", sequential=True) is None
    assert list_items("", "number", sequential=True) == []


# -- Corps d'un courriel --------------------------------------------------------------------

EMAIL = (
    "Objet : Réclamation commande n° MT-48213\n\n"
    "Madame, Monsieur,\n\n"
    "Premier paragraphe des faits. Il compte deux phrases.\n\n"
    "Deuxième paragraphe, la demande.\n\n"
    "Troisième paragraphe, la conséquence.\n\n"
    "Je vous prie d'agréer, Madame, Monsieur, mes salutations distinguées.\n\n"
    "Claire Fontanel"
)


def test_email_body_drops_subject_greeting_closing_and_signature():
    body = email_body(normalize_text(EMAIL))
    assert body == (
        "Premier paragraphe des faits. Il compte deux phrases.\n\n"
        "Deuxième paragraphe, la demande.\n\n"
        "Troisième paragraphe, la conséquence."
    )


def test_email_body_closing_and_signature_in_one_block():
    text = "Objet : X\n\nBonjour,\n\nCorps.\n\nCordialement,\nHugo Ravenel\nAchats"
    assert email_body(text) == "Corps."


def test_email_body_markdown_subject_and_no_closing():
    text = "**Objet :** Relance\n\nMadame Duval,\n\nUn seul paragraphe de corps.\n\nMerci d'avance."
    assert email_body(text) == "Un seul paragraphe de corps.\n\nMerci d'avance."


def test_email_body_keeps_a_body_that_looks_like_a_name():
    # Sans formule de politesse, rien n'est retiré à la fin : pas de faux retrait de contenu.
    text = "Madame,\n\nPremier.\n\nDeuxième sans point"
    assert email_body(text) == "Premier.\n\nDeuxième sans point"


def test_email_body_does_not_take_a_sentence_for_a_greeting():
    text = "Monsieur Dupont a appelé.\n\nSuite."
    assert email_body(text) == "Monsieur Dupont a appelé.\n\nSuite."


def test_email_body_subject_only_within_the_first_lines():
    text = "Un.\n\nDeux.\n\nTrois.\n\nObjet : tard dans le texte\n\nQuatre."
    assert "Objet" in email_body(text)


def test_email_body_without_any_structure_is_the_text():
    assert email_body("Juste une phrase.") == "Juste une phrase."


def test_email_body_keeps_a_content_paragraph_that_contains_a_closing_word():
    body = "Nous nous verrons à bientôt pour la suite du projet, avec un plan détaillé."
    assert email_body(f"Bonjour,\n\n{body}") == body
    # Signée, une même phrase est la formule de politesse ; courte ou soutenue, aussi.
    assert email_body(f"Bonjour,\n\nCorps.\n\n{body}\n\nJean Dupont") == "Corps."
    assert email_body("Bonjour,\n\nCorps.\n\nÀ bientôt !") == "Corps."
    formal = "Je vous prie d'agréer, Madame, l'expression de mes sentiments distingués."
    assert email_body(f"Madame,\n\nCorps.\n\n{formal}") == "Corps."


def test_before_last_scope_drops_the_last_paragraph():
    text = "Un.\n\nDeux.\n\nPoint de vigilance : trois."
    assert counting.scoped(text, "before_last") == "Un.\n\nDeux."
    assert counting.scoped("Seul.", "before_last") == ""


# -- Vérification d'un contrôle -------------------------------------------------------------


def _words(op, **bounds):
    return {"count": "words", "op": op, **bounds}


@pytest.mark.parametrize(
    "op, bounds, text, expected",
    [
        ("<", {"n": 3}, "a b", True),
        ("<", {"n": 3}, "a b c", False),
        ("<=", {"n": 3}, "a b c", True),
        ("<=", {"n": 3}, "a b c d", False),
        (">", {"n": 3}, "a b c", False),
        (">", {"n": 3}, "a b c d", True),
        (">=", {"n": 3}, "a b c", True),
        (">=", {"n": 3}, "a b", False),
        ("==", {"n": 3}, "a b c", True),
        ("==", {"n": 3}, "a b c d", False),
        ("between", {"min": 2, "max": 4}, "a", False),
        ("between", {"min": 2, "max": 4}, "a b", True),
        ("between", {"min": 2, "max": 4}, "a b c d", True),
        ("between", {"min": 2, "max": 4}, "a b c d e", False),
    ],
)
def test_operators_and_inclusive_bounds(op, bounds, text, expected):
    assert evaluate_check(_words(op, **bounds), text) is expected


@pytest.mark.parametrize(
    "words, expected",
    [(89, False), (90, True), (100, True), (110, True), (111, False)],
)
def test_approx_widens_bounds_by_ten_percent_outwards(words, expected):
    check = _words("between", min=100, max=100, approx=True)
    assert evaluate_check(check, "mot " * words) is expected


def test_approx_applies_to_each_operator():
    assert evaluate_check(_words("==", n=10, approx=True), "m " * 9)
    assert evaluate_check(_words("==", n=10, approx=True), "m " * 11)
    assert not evaluate_check(_words("==", n=10, approx=True), "m " * 12)
    assert evaluate_check(_words("<", n=10, approx=True), "m " * 10)  # moins de ~11
    assert not evaluate_check(_words("<", n=10, approx=True), "m " * 11)
    assert evaluate_check(_words(">=", n=10, approx=True), "m " * 9)
    assert not evaluate_check(_words(">=", n=10, approx=True), "m " * 8)
    assert evaluate_check(_words("<=", n=3, approx=True), "m m m m")  # ceil(3,3) = 4
    assert not evaluate_check(_words("<=", n=3, approx=True), "m " * 5)


def test_exact_boundaries_without_approx():
    assert not evaluate_check(_words("<", n=120), "m " * 120)
    assert evaluate_check(_words("<", n=120), "m " * 119)


def test_count_sentences_paragraphs_lines():
    text = "Un. Deux.\n\nTrois.\nQuatre."
    assert evaluate_check({"count": "sentences", "op": "==", "n": 4}, text)
    assert evaluate_check({"count": "paragraphs", "op": "==", "n": 2}, text)
    assert evaluate_check({"count": "lines", "op": "==", "n": 3}, text)


def test_items_with_marker_and_sequential():
    text = "1. a\n2. b\n3. c"
    assert evaluate_check({"count": "items", "marker": "number", "op": "==", "n": 3}, text)
    assert not evaluate_check({"count": "items", "marker": "bullet", "op": "==", "n": 3}, text)
    assert evaluate_check(
        {"count": "items", "marker": "number", "sequential": True, "op": "==", "n": 3}, text
    )
    assert not evaluate_check(
        {"count": "items", "marker": "number", "sequential": True, "op": "==", "n": 3},
        "1. a\n3. b\n4. c",
    )


def test_per_unit_requires_every_unit_and_at_least_one():
    each = {"count": "words", "per": "sentence", "op": "<", "n": 4}
    assert evaluate_check(each, "Un deux trois. Quatre cinq.")
    assert not evaluate_check(each, "Un deux trois. Quatre cinq six sept.")
    assert not evaluate_check(each, "")  # aucune unité : la borne n'est pas tenue
    per_item = {"count": "words", "per": "item", "marker": "number", "op": "<=", "n": 2}
    assert evaluate_check(per_item, "1. a b\n2. c")
    assert not evaluate_check(per_item, "1. a b\n2. c d e")
    assert not evaluate_check(per_item, "pas de liste")
    per_line = {"count": "words", "per": "line", "op": ">=", "n": 2}
    assert evaluate_check(per_line, "a b\nc d")
    assert not evaluate_check(per_line, "a b\nc")


def test_per_paragraph_in_before_last_scope():
    check = {"count": "sentences", "scope": "before_last", "per": "paragraph", "op": "<=", "n": 3}
    ok = "Un. Deux. Trois.\n\nQuatre. Cinq.\n\nPoint de vigilance : une. Deux. Trois. Quatre."
    assert evaluate_check(check, ok)
    assert not evaluate_check(check, "Un. Deux. Trois. Quatre.\n\nCinq.\n\nFin.")


def test_of_selects_the_nth_unit_and_fails_when_absent():
    first = {"count": "words", "of": {"sentence": 1}, "op": "<", "n": 4}
    assert evaluate_check(first, "Un deux trois. Quatre cinq six sept huit.")
    assert not evaluate_check(first, "Un deux trois quatre. Fin.")
    assert not evaluate_check(first, "")  # absente : jamais vrai, même pour « moins de »
    second = {"count": "sentences", "of": {"paragraph": 2}, "op": "==", "n": 2}
    assert evaluate_check(second, "Un.\n\nDeux. Trois.")
    assert not evaluate_check(second, "Un.")


def test_a_list_of_checks_needs_all_of_them():
    both = [
        {"count": "paragraphs", "op": "==", "n": 1},
        {"count": "words", "op": "between", "min": 3, "max": 5},
    ]
    assert evaluate_checks(both, "un deux trois quatre")
    assert not evaluate_checks(both, "un deux trois quatre\n\ncinq")
    assert not evaluate_checks(both, "un")


def test_body_scope_in_a_check():
    check = {"count": "paragraphs", "scope": "body", "op": "==", "n": 3}
    assert evaluate_check(check, EMAIL)
    assert not evaluate_check(check, EMAIL.replace("Troisième paragraphe, la conséquence.", ""))


def test_evaluation_is_deterministic():
    check = {"count": "sentences", "op": "between", "min": 2, "max": 3}
    text = "M. Dupont écrit. Il hésite... puis part. Fin."
    assert {evaluate_check(check, text) for _ in range(5)} == {True}


# -- Forme du contrôle ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "check",
    [
        {},
        {"count": "words"},
        {"count": "mots", "op": "<", "n": 3},
        {"count": "words", "op": "<>", "n": 3},
        {"count": "words", "op": "<", "n": -1},
        {"count": "words", "op": "<", "n": 1.5},
        {"count": "words", "op": "<", "n": True},
        {"count": "words", "op": "<", "n": 3, "min": 1},
        {"count": "words", "op": "between", "min": 5, "max": 2},
        {"count": "words", "op": "between", "min": 1, "max": 2, "n": 3},
        {"count": "words", "op": "between", "min": 1},
        {"count": "words", "op": "<", "n": 3, "scope": "head"},
        {"count": "words", "op": "<", "n": 3, "extra": 1},
        {"count": "words", "op": "<", "n": 3, "approx": "oui"},
        {"count": "words", "op": "<", "n": 3, "per": "sentence", "of": {"sentence": 1}},
        {"count": "paragraphs", "op": "<", "n": 3, "per": "sentence"},
        {"count": "sentences", "op": "<", "n": 3, "per": "sentence"},
        {"count": "sentences", "op": "<", "n": 3, "of": {"sentence": 1}},
        {"count": "words", "op": "<", "n": 3, "per": "mot"},
        {"count": "words", "op": "<", "n": 3, "of": {"line": 1}},
        {"count": "words", "op": "<", "n": 3, "of": {"sentence": 0}},
        {"count": "words", "op": "<", "n": 3, "of": {"sentence": 1, "paragraph": 1}},
        {"count": "words", "op": "<", "n": 3, "marker": "bullet"},
        {"count": "items", "op": "<", "n": 3, "marker": "tiret"},
        {"count": "items", "op": "<", "n": 3, "sequential": True},
        {"count": "items", "op": "<", "n": 3, "marker": "bullet", "sequential": True},
    ],
)
def test_malformed_checks_are_refused(check):
    with pytest.raises(CheckError):
        validate_check(check)
    with pytest.raises(CheckError):
        evaluate_check(check, "texte")


@pytest.mark.parametrize("value", [None, "texte", 3, [], [1], [{"count": "words"}]])
def test_malformed_check_values_are_refused(value):
    with pytest.raises(CheckError):
        validate_checks(value)


def test_well_formed_checks_pass():
    validate_checks({"count": "words", "op": "<", "n": 3})
    validate_checks(
        [{"count": "items", "marker": "number", "sequential": True, "op": "==", "n": 3}]
    )
    validate_checks({"count": "words", "of": {"paragraph": 2}, "op": ">=", "n": 0})


# -- Dans la question et le correcteur ------------------------------------------------------


def _criteria(*checks):
    return [
        {"id": f"c{i}", "question": f"Critère {i} ?"} | ({"check": check} if check else {})
        for i, check in enumerate(checks, start=1)
    ]


def _question(*checks):
    return synthetic_question("writing-fr", 7, criteria=_criteria(*checks))


COUNT_3 = {"count": "words", "op": "==", "n": 3}


def test_question_schema_accepts_and_validates_check():
    question = _question(COUNT_3, None, None, None)
    assert validate_question(question) == question
    bad = with_hashes({**question, "criteria": _criteria({"count": "words"}, None, None, None)})
    with pytest.raises(QuestionError, match="critère c1"):
        validate_question(bad)
    unknown = with_hashes(
        {**question, "criteria": [{"id": "c1", "question": "?", "juge": True}] * 1}
    )
    with pytest.raises(QuestionError):
        validate_question(unknown)


def test_check_changes_the_target_hash_but_not_the_prompt_hash():
    plain, checked = _question(None, None, None, None), _question(COUNT_3, None, None, None)
    assert plain["prompt_hash"] == checked["prompt_hash"]
    assert plain["target_hash"] != checked["target_hash"]


def _grade(question, content, verdicts=None, status="ok"):
    generation = generation_for(question, answer_output(content), status=status)
    return grade_line(question, generation, verdicts).record


def _verdicts(**values):
    return {key: {"verdict": value, "error": None} for key, value in values.items()}


def test_grader_combines_code_and_judge_verdicts():
    question = _question(COUNT_3, None, None, None)
    record = _grade(question, "un deux trois", _verdicts(c2=True, c3=False, c4=True))
    assert record["grader"] == "judge_criteria@2"
    assert (record["status"], record["score"], record["success"]) == ("ok", 0.75, None)
    record = _grade(question, "un deux", _verdicts(c2=True, c3=False, c4=True))
    assert (record["status"], record["score"]) == ("ok", 0.5)  # le comptage échoue


def test_grader_does_not_need_a_verdict_for_a_checked_criterion():
    question = _question(COUNT_3, None, None, None)
    record = _grade(question, "un deux trois", _verdicts(c2=True, c3=True, c4=True))
    assert record["score"] == 1.0
    # Un verdict de juge pour c1 serait ignoré : le code seul tranche.
    record = _grade(question, "un", _verdicts(c1=True, c2=True, c3=True, c4=True))
    assert record["score"] == 0.75


def test_grader_still_awaits_missing_judged_verdicts():
    question = _question(COUNT_3, None, None, None)
    assert _grade(question, "un deux trois", None)["status"] == "awaiting_judgment"
    partial = _grade(question, "un deux trois", _verdicts(c2=True, c3=True))
    assert partial["status"] == "awaiting_judgment"
    assert _grade(question, "un deux trois", {})["status"] == "awaiting_judgment"


def test_a_question_fully_checked_by_code_needs_no_judge():
    question = _question(COUNT_3, COUNT_3, {"count": "sentences", "op": "==", "n": 1}, COUNT_3)
    record = _grade(question, "un deux trois", None)
    assert (record["status"], record["score"]) == ("ok", 1.0)
    assert _grade(question, "un", None)["score"] == 0.25


def test_judge_error_is_still_a_bench_error():
    question = _question(COUNT_3, None, None, None)
    record = _grade(question, "un deux trois", _verdicts(c2=True, c3=None, c4=True))
    assert record["status"] == "error"


def test_truncated_writing_scores_zero_without_checking():
    question = _question(COUNT_3, None, None, None)
    record = _grade(question, "un deux trois", None, status="truncated")
    assert (record["status"], record["score"], record["success"]) == ("truncated", 0.0, None)


def test_code_verdict_uses_the_final_answer_without_inline_thinking():
    question = _question(COUNT_3, None, None, None)
    content = "<think>beaucoup de mots dans la réflexion en ligne</think>un deux trois"
    record = _grade(question, content, _verdicts(c2=True, c3=True, c4=True))
    assert record["score"] == 1.0


def test_questions_without_check_grade_as_before():
    question = _question(None, None, None, None)
    record = _grade(question, "Texte.", _verdicts(c1=True, c2=True, c3=False, c4=True))
    assert record["score"] == 0.75
