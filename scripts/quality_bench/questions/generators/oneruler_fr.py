"""Générateur OneRuler FR (``oneruler-fr-niah``, ``oneruler-fr-cwe``, ``oneruler-fr-none``).

Recette de OneRuler (``mungg/OneRuler``, code MIT, dérivé de RULER) appliquée au français, avec
les gabarits FR du dépôt et *Les Misérables* (domaine public) comme botte de foin :

- **NIAH** : extrait contigu du livre (phrase de début tirée), aiguilles « Le nombre magique
  spécial pour "<clé>" est : <valeur>. » insérées à des profondeurs tirées parmi 40 points
  de 0 à 100 %. Variantes ``single`` (une clé, une valeur), ``multikey`` (quatre clés, dont
  trois distracteurs, une seule demandée) et ``multivalue`` (une clé, quatre valeurs).
- **NONE** : quatre aiguilles distractrices, et la clé demandée n'en fait pas partie (réponse
  attendue « aucun », sans cible).
- **CWE** : liste numérotée de mots où 10 mots reviennent plus souvent que les autres ; deux
  niveaux de fréquence : facile (30 contre 3) et difficile (20 contre 10).

Clés et mots viennent du vocabulaire du livre (mots alphabétiques de 4 lettres ou plus, en
minuscules, dédupliqués, triés puis tirés), jamais de ``data/vocab/`` (licence non déclarée) ;
pas de ``stanza`` : les phrases sont découpées par l'expression régulière de repli de OneRuler.
Valeurs : nombres à 7 chiffres, en chaînes. La taille de chaque question remplit au plus près
son palier visé (8192, 16384, 32768, à parts égales) sans le dépasser selon la règle d'AD-5.
Une question par groupe. Noyau pur : les fichiers bruts sont lus par ``set_builder``.
"""

from __future__ import annotations

import json
import random
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ...common.canonical import nfc, sha256_hex
from ..build import build_question, estimate_prompt_tokens, required_num_ctx
from ..pinned import RemoteFile
from .var_math import GeneratorError

GENERATOR = "oneruler_fr@1"
BUNDLE = "oneruler-fr"
_REPO = "mungg/OneRuler"
_REVISION = "a3fe6af862dc4b30794afc0a8f3d4f60758cecfa"
LICENSE_PATH = "LICENSE"
BOOK_PATH = "OneRuler/data/books/fr/les_miserables_fr.txt"
NIAH_TEMPLATE_PATH = "OneRuler/data/prompt/fr/niah.txt"
CWE_TEMPLATE_PATH = "OneRuler/data/prompt/fr/cwe.txt"
_HASHES = {
    LICENSE_PATH: "1446bc54001a59261b6da027dbfb252932076bbc351c8e7f0d345b6c604edc48",
    BOOK_PATH: "61ea68ac4f11ec9f5d76fbaf7c8ec866274cbc7441b4bc63a513623fc8d7c2d9",
    NIAH_TEMPLATE_PATH: "ad1a21dc5ce1c10d41cc9a825744e61e7fb639cc55acfd401d152c9a9a8972d7",
    CWE_TEMPLATE_PATH: "dc74806ffde8d0203245fb88954117ffeaec4175da12954b13e308226eb7dda8",
}
RAW_FILES = tuple(
    RemoteFile("github", _REPO, _REVISION, path, digest) for path, digest in _HASHES.items()
)

TIERS = (8192, 16384, 32768)
# Profondeurs d'insertion de OneRuler : 40 points régulièrement espacés de 0 à 100 %.
DEPTHS = tuple(round(index * 100 / 39) for index in range(40))
NIAH_VARIANTS = ("single", "multikey", "multivalue")
NUM_KEYS = {"single": 1, "multikey": 4, "multivalue": 1, "none": 4}
NUM_VALUES = {"single": 1, "multikey": 1, "multivalue": 4, "none": 1}
# Niveaux de CWE : (nom, répétitions des 10 mots fréquents, répétitions des autres).
CWE_LEVELS = (("easy", 30, 3), ("hard", 20, 10))
CWE_COMMON = 10
CWE_POOL = 5000

_SENTENCE_SPLIT = re.compile(r"(?<=[?.!])\s+")
_WORD = re.compile(r"[^\W\d_]+")
_NIAH_KEYS = (
    "task",
    "needle_numbers",
    "question_single_numbers",
    "please_list",
    "if_no_numbers",
    "answer_prefix",
    "answer_numbers",
    "none",
)


@dataclass(frozen=True)
class OneRulerTexts:
    """Textes préparés : phrases et vocabulaire du livre, gabarits FR."""

    sentences: tuple[str, ...]
    vocabulary: tuple[str, ...]
    niah: Mapping[str, str]
    cwe: str


def parse_texts(book: str, niah_template: str, cwe_template: str) -> OneRulerTexts:
    """Prépare les textes bruts (contenu des fichiers épinglés, en UTF-8)."""
    flat = re.sub(r"\s+", " ", nfc(book)).strip()
    sentences = tuple(part.strip() for part in _SENTENCE_SPLIT.split(flat) if part.strip())
    vocabulary = tuple(
        sorted({word.lower() for word in _WORD.findall(flat) if len(word) >= 4 and word.isalpha()})
    )
    niah = json.loads(nfc(niah_template))
    missing = [key for key in _NIAH_KEYS if not isinstance(niah.get(key), str)]
    if missing:
        raise GeneratorError(f"gabarit NIAH FR : champs absents {missing}")
    cwe = nfc(cwe_template)
    if "{context}" not in cwe or "{context}" not in niah["task"]:
        raise GeneratorError("gabarits OneRuler : champ {context} absent")
    if len(sentences) < 100 or len(vocabulary) < CWE_POOL:
        raise GeneratorError("livre OneRuler trop court pour le générateur")
    return OneRulerTexts(sentences, vocabulary, {k: niah[k] for k in _NIAH_KEYS}, cwe)


def _rng(seed: int, task: str, index: int) -> random.Random:
    return random.Random(int(sha256_hex([seed, GENERATOR, task, index]), 16))


def _prompt_tokens(content: str) -> int:
    return estimate_prompt_tokens(
        {
            "messages": [{"role": "user", "content": content}],
            "turns": None,
            "tools": None,
            "format": None,
        }
    )


def _fill(build: Callable[[int], str], upper: int, tier: int, usage: str) -> int:
    """Plus grand ``n`` ≤ ``upper`` dont le prompt ``build(n)`` (croissant en ``n``) tient dans
    ``tier`` selon la règle d'AD-5."""
    low, high = 0, upper
    while low < high:  # plus grand n tel que le prompt tienne dans le palier
        middle = (low + high + 1) // 2
        if required_num_ctx(_prompt_tokens(build(middle)), usage) <= tier:
            low = middle
        else:
            high = middle - 1
    return low


def _niah_question(texts: OneRulerTexts, rng: random.Random, variant: str, tier: int, usage: str):
    niah = texts.niah
    keys = rng.sample(texts.vocabulary, NUM_KEYS[variant] + (1 if variant == "none" else 0))
    query_key = keys.pop() if variant == "none" else None
    values_by_key: dict[str, list[str]] = {}
    used: set[str] = set()
    for key in keys:
        values_by_key[key] = []
        while len(values_by_key[key]) < NUM_VALUES[variant]:
            value = str(rng.randint(10**6, 10**7 - 1))
            if value not in used:
                used.add(value)
                values_by_key[key].append(value)
    needles = [
        niah["needle_numbers"].replace("{key}", key).replace("{value}", value) + "."
        for key in keys
        for value in values_by_key[key]
    ]
    rng.shuffle(needles)
    depths = sorted(rng.sample(DEPTHS, len(needles)))
    if query_key is None:
        query_key = keys[rng.randrange(len(keys))]
        answers: list[str] | None = values_by_key[query_key]
    else:
        answers = None
    start = rng.randrange(len(texts.sentences))
    question = (
        niah["question_single_numbers"] + " " + niah["please_list"] + " " + niah["if_no_numbers"]
    ).replace("{query1}", query_key)
    answer = niah["answer_prefix"] + " " + niah["answer_numbers"]

    def build(count: int) -> str:
        sentences = [
            texts.sentences[(start + offset) % len(texts.sentences)] for offset in range(count)
        ]
        positions = [0, *(int(count * depth / 100) for depth in depths), count]
        parts = []
        for index in range(1, len(positions)):
            chunk = " ".join(sentences[positions[index - 1] : positions[index]])
            if chunk:
                parts.append(chunk)
            if index - 1 < len(needles):
                parts.append(needles[index - 1])
        context = " ".join(parts)
        return niah["task"].replace("{context}", context) + question + answer

    content = build(_fill(build, 4 * len(texts.sentences), tier, usage))
    return content, answers, query_key


def _generate_niah_like(texts, seed, count, source, task, variant_of) -> list[dict[str, Any]]:
    usage = "abstention" if task == "none" else "rag"
    questions = []
    for index in range(count):
        tier = TIERS[index % len(TIERS)]
        variant = variant_of(index)
        rng = _rng(seed, task, index)
        content, answers, _ = _niah_question(texts, rng, variant, tier, usage)
        questions.append(
            _build(
                source,
                index,
                tier,
                content,
                {"variant": variant, "none_answer": texts.niah["none"]},
                answers,
                seed,
            )
        )
    return questions


def _build(source, index, tier, content, params, target, seed) -> dict[str, Any]:
    number = index + 1
    question = build_question(
        source=source,
        number=number,
        group=f"{source}/{number:04d}",
        messages=[{"role": "user", "content": content}],
        grader_params=params,
        target=target,
        generator=GENERATOR,
        generator_seed=seed,
    )
    if question["num_ctx"] != tier:
        raise GeneratorError(
            f"{source} n° {number} : palier {question['num_ctx']} au lieu de {tier}"
        )
    return question


def _check_count(count: int) -> None:
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise GeneratorError(f"count : entier ≥ 1 attendu, reçu {count!r}")


def generate_niah(texts: OneRulerTexts, seed: int, count: int) -> list[dict[str, Any]]:
    """``count`` questions NIAH : paliers puis variantes (single, multikey, multivalue) en
    alternance, à parts égales quand ``count`` est multiple de 9."""
    _check_count(count)
    return _generate_niah_like(
        texts,
        seed,
        count,
        "oneruler-fr-niah",
        "niah",
        lambda index: NIAH_VARIANTS[(index // len(TIERS)) % len(NIAH_VARIANTS)],
    )


def generate_none(texts: OneRulerTexts, seed: int, count: int) -> list[dict[str, Any]]:
    """``count`` questions sans aiguille pertinente (clé demandée absente), cible nulle."""
    _check_count(count)
    return _generate_niah_like(texts, seed, count, "oneruler-fr-none", "none", lambda _: "none")


def generate_cwe(texts: OneRulerTexts, seed: int, count: int) -> list[dict[str, Any]]:
    """``count`` questions CWE : paliers puis niveaux (facile, difficile) en alternance ; cible
    = les 10 mots fréquents, triés."""
    _check_count(count)
    source = "oneruler-fr-cwe"
    questions = []
    for index in range(count):
        tier = TIERS[index % len(TIERS)]
        level, common_repeats, uncommon_repeats = CWE_LEVELS[
            (index // len(TIERS)) % len(CWE_LEVELS)
        ]
        rng = _rng(seed, "cwe", index)
        words = rng.sample(texts.vocabulary, CWE_POOL)
        common, pool = words[:CWE_COMMON], words[CWE_COMMON:]

        def word_list(
            uncommon: int, common=common, pool=pool, c=common_repeats, u=uncommon_repeats
        ):
            return common * c + pool[:uncommon] * u

        def build(uncommon: int, word_list=word_list) -> str:
            listed = " ".join(f"{i + 1}. {word}" for i, word in enumerate(word_list(uncommon)))
            return texts.cwe.replace("{context}", listed)

        words_listed = word_list(_fill(build, len(pool), tier, "rag"))
        rng.shuffle(words_listed)
        listed = " ".join(f"{i + 1}. {word}" for i, word in enumerate(words_listed))
        content = texts.cwe.replace("{context}", listed)
        params = {
            "level": level,
            "common_repeats": common_repeats,
            "uncommon_repeats": uncommon_repeats,
        }
        questions.append(_build(source, index, tier, content, params, sorted(common), seed))
    return questions


GENERATORS: dict[str, Callable[[OneRulerTexts, int, int], list[dict[str, Any]]]] = {
    "oneruler-fr-niah": generate_niah,
    "oneruler-fr-cwe": generate_cwe,
    "oneruler-fr-none": generate_none,
}
