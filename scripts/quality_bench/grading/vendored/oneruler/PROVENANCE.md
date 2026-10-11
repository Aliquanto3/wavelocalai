# Provenance : OneRuler, évaluation

- **Dépôt :** https://github.com/mungg/OneRuler
- **Commit :** `a3fe6af862dc4b30794afc0a8f3d4f60758cecfa`
- **Licence :** MIT (`LICENSE`, Yekyung Kim, 2025, copié tel quel)
- **Récupéré le :** 2026-10-11 (archive du commit, hors dépôt)

## Fichiers copiés

| Fichier amont | Copie | `sha256` amont |
|---|---|---|
| `LICENSE` | `LICENSE` | `1446bc54001a59261b6da027dbfb252932076bbc351c8e7f0d345b6c604edc48` |
| `OneRuler/eval/evaluate.py` (extrait) | `evaluate.py` | `ad9d0301128807c935ebc79d589e9df447c2240c7d4bb2e88ff3e42c01c5f0d3` |

`__init__.py` (vide) est propre au banc.

## Modifications

Extrait d'`evaluate.py`, fonctions copiées sans changement :
- `clean_text`, `is_correct_order`, `compare_numbers`, `compare_none` ;
- `none_dict` réduit à sa seule entrée `"fr": ["aucun"]`.

Retirés : les autres langues de `none_dict`, `extract_model_name`, `escape_quotes`, `evaluate_jsonl` (lecture de fichiers), `main` et leurs imports (`argparse`, `os`, `json`).

## Téléchargements retirés

Aucun.
