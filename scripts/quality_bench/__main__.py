"""Point d'entrée : ``python -m scripts.quality_bench <commande>`` depuis la racine du dépôt.

Les télémétries sont coupées avant tout import du paquet (AD-1, AD-15). Les sous-commandes
(``build-set``, ``generate``, ``judge``, ``grade``, ``report``, ``pilot``, ``calibrate``)
s'ajoutent en éditant ce fichier : importer leur module ici, après ``disable_telemetry()``, et
ajouter leur entrée à la liste ``SUBCOMMANDS`` ci-dessous. Ne pas les enregistrer depuis un
autre module en important celui-ci : sous ``python -m``, ce fichier s'exécute comme
``__main__``, un autre objet module que ``scripts.quality_bench.__main__``, dont la liste
modifiée ne serait jamais lue.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from src.core.telemetry import disable_telemetry

disable_telemetry()

# Imports des modules de sous-commandes : ici, après disable_telemetry() (noqa: E402).
from scripts.quality_bench.grading.commands import GRADE  # noqa: E402
from scripts.quality_bench.questions.importers.commands import FETCH, FETCH_NLTK  # noqa: E402
from scripts.quality_bench.questions.review import REVIEW_SAMPLE  # noqa: E402
from scripts.quality_bench.questions.set_builder import BUILD_SET  # noqa: E402

# (nom, aide, configuration du sous-analyseur, exécution qui rend le code de sortie) ; liste
# éditée dans ce fichier seulement (voir la docstring).
Subcommand = tuple[
    str,
    str,
    Callable[[argparse.ArgumentParser], None],
    Callable[[argparse.Namespace], int],
]
SUBCOMMANDS: list[Subcommand] = [FETCH, FETCH_NLTK, BUILD_SET, REVIEW_SAMPLE, GRADE]


def _reconfigure_console() -> None:
    """Console en UTF-8 (accents des journaux sous Windows)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.quality_bench",
        description=(
            "Banc de qualité difficile des petits modèles locaux : jeu de questions, "
            "génération Ollama, correction, jugement, statistiques et rapports. "
            "À lancer depuis la racine du dépôt, dans .venv-quality."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<commande>")
    for name, help_text, configure, run in SUBCOMMANDS:
        subparser = subparsers.add_parser(name, help=help_text, description=help_text)
        configure(subparser)
        subparser.set_defaults(run=run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _reconfigure_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    run = getattr(args, "run", None)
    if run is None:
        parser.print_help()
        return 2
    return int(run(args))


if __name__ == "__main__":
    sys.exit(main())
