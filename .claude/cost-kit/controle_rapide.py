"""Contrôle rapide de fin de story : lint, format, imports, règle d'architecture.

Adapté du modèle d'agent-cost-kit. Ne contrôle que les fichiers Python modifiés depuis `master`
(diff de branche et fichiers non commités), pour tenir en quelques secondes et ne pas bloquer
sur la dette existante. Versions et exclusions reprises de `.pre-commit-config.yaml`.
Jamais la suite de tests complète.

Comportement :
- n'affiche que les erreurs (les sorties vertes sont tues, pour ne pas gonfler le contexte) ;
- code de retour 2 s'il y a au moins une erreur, 0 sinon ;
- `--max-blocages N` (défaut 2) : au-delà de N échecs consécutifs enregistrés dans
  `.claude/cost-kit/.blocages`, sort en 0 pour ne pas faire boucler l'agent.

Usage : .venv\\Scripts\\python .claude/cost-kit/controle_rapide.py [--max-blocages 2]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BRANCHE_DE_BASE = "master"
# Code tiers ou emprunté, laissé tel que publié (cf. .pre-commit-config.yaml), et scripts de
# recherche jetables des artefacts BMAD.
EXCLUSIONS = re.compile(
    r"^(_bmad/|_bmad-output/|\.claude/|scripts/quality_bench/(grading|envs)/vendored/)"
)
MAX_LIGNES_PAR_COMMANDE = 40


def fichiers_modifies() -> list[str]:
    """Fichiers .py existants modifiés depuis la base de branche, commités ou non."""
    sorties = [
        ["git", "diff", "--name-only", "--diff-filter=d", f"{BRANCHE_DE_BASE}...HEAD"],
        ["git", "diff", "--name-only", "--diff-filter=d", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    fichiers: set[str] = set()
    for commande in sorties:
        resultat = subprocess.run(commande, capture_output=True, text=True)
        fichiers.update(resultat.stdout.split())
    return sorted(
        f for f in fichiers if f.endswith(".py") and not EXCLUSIONS.match(f) and Path(f).exists()
    )


def uvx(outil: str) -> list[str]:
    """`uvx --offline` si l'outil est déjà en cache : sinon uvx interroge PyPI à chaque appel,
    ce qui coûte jusqu'à une minute quand le réseau est lent ou coupé."""
    sonde = subprocess.run(
        ["uvx", "--offline", outil, "--version"], capture_output=True, text=True, timeout=30
    )
    return ["uvx", "--offline", outil] if sonde.returncode == 0 else ["uvx", outil]


def commandes(fichiers: list[str]) -> list[list[str]]:
    return [
        [*uvx("ruff@0.14.9"), "check", "-q", *fichiers],
        [*uvx("black@25.12.0"), "--check", "-q", *fichiers],
        [*uvx("isort@7.0.0"), "--profile", "black", "--check-only", "-q", *fichiers],
    ]


def verifier_architecture(fichiers: list[str]) -> str | None:
    """`src/core/` n'importe jamais streamlit : l'UI reste dans `src/app/`."""
    motif = re.compile(r"^\s*(import|from)\s+streamlit\b", re.MULTILINE)
    fautifs = [
        f
        for f in fichiers
        if f.startswith("src/core/") and motif.search(Path(f).read_text(encoding="utf-8"))
    ]
    if fautifs:
        return "src/core/ importe streamlit : " + ", ".join(fautifs)
    return None


def main() -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--max-blocages", type=int, default=2)
    options = analyseur.parse_args()
    compteur = Path(".claude/cost-kit/.blocages")
    fichiers = fichiers_modifies()
    echecs = []
    if fichiers:
        for commande in commandes(fichiers):
            nom = [mot for mot in commande if mot != "--offline"][:2]
            try:
                resultat = subprocess.run(commande, capture_output=True, text=True, timeout=120)
            except (OSError, subprocess.TimeoutExpired) as erreur:
                echecs.append((nom, str(erreur)))
                continue
            if resultat.returncode != 0:
                sortie = (resultat.stdout + resultat.stderr).strip().splitlines()
                echecs.append((nom, "\n".join(sortie[:MAX_LIGNES_PAR_COMMANDE])))
        erreur_architecture = verifier_architecture(fichiers)
        if erreur_architecture:
            echecs.append((["architecture"], erreur_architecture))
    if not echecs:
        if compteur.exists():
            compteur.unlink()
        return 0
    blocages = int(compteur.read_text() or 0) + 1 if compteur.exists() else 1
    compteur.parent.mkdir(parents=True, exist_ok=True)
    compteur.write_text(str(blocages))
    for commande, sortie in echecs:
        print(f"[contrôle rapide] {' '.join(commande)} a échoué :\n{sortie}\n", file=sys.stderr)
    if blocages > options.max_blocages:
        print(
            f"[contrôle rapide] {blocages} échecs consécutifs : on laisse passer,"
            " à signaler dans le rapport.",
            file=sys.stderr,
        )
        compteur.unlink()
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
