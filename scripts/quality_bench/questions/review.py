"""Échantillons de relecture d'un jeu : ``review-sample --set <s>`` (hors dépôt).

Assemble le jeu en mémoire, exactement comme ``build-set`` mais sans écrire de jeu (ni
``sets/<s>/``, ni ``benchmarks/``), puis écrit deux fichiers Markdown sous
``$QUALITY_BENCH_DATA/review/`` (jamais dans le dépôt), et son journal
``sets/log-review-sample.log`` (identifiants, comptes et empreintes seulement) :

- ``private-sample.md`` : ``--per-source`` questions de chaque source privée ;
- ``writing-sample.md`` : ``--writing`` questions de rédaction.

Pour chaque question : identifiant, groupe, messages, tours, outils, cible et critères. La
commande ne prend aucun verrou : elle ne télécharge rien, ne lance aucun modèle et n'écrit que
ces deux fichiers et son journal. Le tirage est déterministe (graine du jeu,
``[seed, "review", source]``).
"""

from __future__ import annotations

import argparse
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..common import paths
from ..common.canonical import pretty_bytes
from ..common.config import ConfigError
from ..common.logs import setup_logging
from .schema import SOURCES
from .set_builder import EXPECTED_ERRORS, BuiltSet, derived_rng, prepare_set, read_set_config

logger = logging.getLogger(__name__)

PRIVATE_SAMPLE = "private-sample.md"
WRITING_SAMPLE = "writing-sample.md"


def _fence(text: str) -> str:
    """Bloc de code dont la clôture est plus longue que toute suite d'accents graves du texte."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def _json(value: Any) -> str:
    return _fence(pretty_bytes(value).decode("utf-8").rstrip("\n"))


def render_question(question: Mapping[str, Any]) -> str:
    """Bloc Markdown d'une question : id, groupe, messages, tours, outils, cible, critères."""
    lines = [f"### {question['id']}", "", f"- Groupe : `{question['group']}`"]
    lines.append(f"- Unité : `{question['unit']}`, palier `num_ctx` {question['num_ctx']}")
    lines += ["", "**Messages**", ""]
    for message in question["messages"]:
        lines += [f"*{message['role']}*", "", _fence(message["content"]), ""]
    if question["turns"]:
        lines += ["**Tours suivants**", ""]
        for index, turn in enumerate(question["turns"], start=1):
            for message in turn:
                lines += [f"*tour {index}, {message['role']}*", "", _fence(message["content"]), ""]
    if question["tools"]:
        lines += ["**Outils**", "", _json(question["tools"]), ""]
    lines += ["**Correcteur**", "", _json(question["grader"]), ""]
    lines += ["**Cible**", "", _json(question["target"]), ""]
    if question["criteria"]:
        lines += ["**Critères**", ""]
        lines += [f"- {c['id']} : {c['question']}" for c in question["criteria"]]
        lines.append("")
    return "\n".join(lines)


def select(built: BuiltSet, source: str, count: int) -> list[dict[str, Any]]:
    """``count`` questions de ``source`` dans le jeu, tirées par ``[seed, "review", source]``."""
    pool = [question for question in built.questions if question["source"] == source]
    chosen = derived_rng(built.config.seed, "review", source).sample(pool, min(count, len(pool)))
    return sorted(chosen, key=lambda question: question["id"])


def _document(title: str, intro: str, sections: list[tuple[str, list[dict[str, Any]]]]) -> str:
    parts = [f"# {title}", "", intro, ""]
    for source, questions in sections:
        parts += [f"## {source} ({len(questions)} questions)", ""]
        parts += [render_question(question) for question in questions]
    return "\n".join(parts).rstrip("\n") + "\n"


def write_review(built: BuiltSet, per_source: int, writing: int) -> dict[str, Path]:
    """Écrit les deux échantillons sous ``review/`` ; rend leurs chemins."""
    set_id = built.config.set_id
    in_set = {entry.source for entry in built.config.sources}
    private_sources = [s for s in sorted(in_set) if SOURCES[s].private]
    writing_sources = [s for s in sorted(in_set) if SOURCES[s].usage == "writing"]
    outputs = {
        PRIVATE_SAMPLE: _document(
            f"Échantillon de relecture des questions privées — {set_id}",
            "Hors dépôt : ne jamais commiter ni copier ce fichier. Empreinte du jeu assemblé : "
            f"`{built.hash}`.",
            [(source, select(built, source, per_source)) for source in private_sources],
        ),
        WRITING_SAMPLE: _document(
            f"Échantillon de relecture des questions de rédaction — {set_id}",
            f"Empreinte du jeu assemblé : `{built.hash}`.",
            [(source, select(built, source, writing)) for source in writing_sources],
        ),
    }
    directory = paths.review_dir()
    directory.mkdir(parents=True, exist_ok=True)
    written = {}
    for name, text in outputs.items():
        path = directory / name
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        written[name] = path
    return written


def _configure_review(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--set", required=True, metavar="<set>", dest="set_id", help="jeu")
    parser.add_argument(
        "--per-source", type=int, default=5, metavar="N", help="questions par source privée"
    )
    parser.add_argument(
        "--writing", type=int, default=10, metavar="N", help="questions de rédaction"
    )


def _run_review(args: argparse.Namespace) -> int:
    setup_logging("review-sample", paths.sets_log_path("review-sample"))
    if args.per_source < 0 or args.writing < 0:
        logger.error("--per-source et --writing : entiers ≥ 0 attendus")
        return 2
    try:
        config = read_set_config(args.set_id)
    except (ConfigError, ValueError) as error:
        logger.error("YAML de jeu invalide : %s", error)
        return 2
    try:
        built = prepare_set(args.set_id, config)
        for name, path in write_review(built, args.per_source, args.writing).items():
            logger.info("%s écrit : %s", name, path)
    except ConfigError as error:
        logger.error("YAML de jeu invalide : %s", error)
        return 2
    except EXPECTED_ERRORS as error:
        # Refus attendus (source absente, empreinte, effectif) : sans pile, comme build-set.
        logger.error("review-sample %s refusé : %s : %s", args.set_id, type(error).__name__, error)
        return 1
    except Exception:  # erreur inattendue : journalisée avec sa pile, code 1
        logger.exception("review-sample %s interrompu", args.set_id)
        return 1
    return 0


REVIEW_SAMPLE = (
    "review-sample",
    "Écrit des échantillons de relecture du jeu --set <s> (questions privées et rédaction) "
    "sous $QUALITY_BENCH_DATA/review/, hors dépôt ; lecture seule, sans verrou.",
    _configure_review,
    _run_review,
)
