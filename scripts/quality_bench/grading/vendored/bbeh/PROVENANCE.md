# Provenance : BIG-Bench Extra Hard (BBEH), évaluation

- **Dépôt :** https://github.com/google-deepmind/bbeh
- **Commit :** `80d12ca916b7158f22293fcf3144f4d3d854d4be`
- **Licence :** Apache-2.0 pour le code (`LICENSE`, copié tel quel ; les données du jeu sont sous CC-BY-4.0, voir `questions/SOURCES.md`)
- **Récupéré le :** 2026-10-11 (archive du commit, hors dépôt)

## Fichiers copiés

| Fichier amont | Copie | `sha256` amont |
|---|---|---|
| `LICENSE` | `LICENSE` | `ed714919b09bcaee887dfed4bca3972041cac53453c3089f57a367e05a50704d` |
| `bbeh/evaluate.py` | `evaluate.py` | `4b4f06e5babb015de2ba639bae995a5526182ffb5b5890af54dfcf038580eb34` |

`__init__.py` (vide) est propre au banc.

## Modifications

- Retrait du bloc final `# Examples` : huit `print(evaluate_correctness(…))` exécutés à l'import. Les fonctions (`strip_latex`, `extract_answer`, `fuzzy_match`, `preprocess_sample`, `preprocess_reference`, `evaluate_correctness`) sont telles que publiées.

## Téléchargements retirés

Aucun.
