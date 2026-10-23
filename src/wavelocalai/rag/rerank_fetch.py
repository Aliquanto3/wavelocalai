"""Récupération du reranker dans le cache (story 5.5, AD-17), dans un processus à part.

`python -m wavelocalai.rag.rerank_fetch <modèle> <cache_dir> [<fichier .env>]` télécharge le modèle
fastembed dans le `cache_dir` du dossier de données (le seul téléchargement du reranker), puis le charge
pour vérifier qu'il est lisible. Un processus à part, tué à l'annulation : un téléchargement de
`huggingface_hub` ne s'interrompt pas dans un thread, et le chargement du modèle (~1 Go) ne reste pas
dans la mémoire de l'application. Code de sortie : 0 réussi ; 1 échec (dernière ligne de l'erreur sur
`stderr`) ; 2 fastembed introuvable (environnement cassé : dépendance de base depuis la story 9.5).
"""

from __future__ import annotations

import sys

from wavelocalai.telemetry import disable_telemetry


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage : rerank_fetch <modèle> <cache_dir> [<fichier .env>]", file=sys.stderr)
        return 1
    model, cache = argv[1], argv[2]
    env_file = argv[3] if len(argv) > 3 else None
    disable_telemetry(env_file)  # juste avant l'import de fastembed et de huggingface_hub (AD-21)
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
    except ImportError:
        print(
            "fastembed n'est pas disponible (réinstallez les dépendances : uv sync)",
            file=sys.stderr,
        )
        return 2
    try:
        TextCrossEncoder(model_name=model, cache_dir=cache)  # télécharge, puis charge
    except Exception as exc:  # noqa: BLE001 - toute cause est rapportée à l'écran
        print((str(exc).strip().splitlines() or [type(exc).__name__])[0][:300], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
