# Provenance : IFBench

- **Dépôt :** https://github.com/allenai/IFBench
- **Commit :** `1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d`
- **Licence :** Apache-2.0 (`LICENSE`, copié tel quel)
- **Récupéré le :** 2026-10-11 (archive du commit, hors dépôt)

## Fichiers copiés

| Fichier amont | Copie | `sha256` amont |
|---|---|---|
| `LICENSE` | `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `ifbench/instructions.py` | `instructions.py` | `a76a3b300b531b95200e53427c6b1fbb72b671cf6d358796797c0fa4b6c7c44f` |
| `ifbench/classic_instructions.py` | `classic_instructions.py` | `d26e642f2e71e4f57218e5e05f098a22e36311485779baac401161d3228c9973` |
| `ifbench/instructions_registry.py` | `instructions_registry.py` | `5119f2919261c77566f698f2f367883aff56cf89443bac5a56b6e30ddbd5aef9` |
| `ifbench/instructions_util.py` | `instructions_util.py` | `6996a6efaf6e3c92a2e926881eadc8c0262fb8d06c8cb56394ef7322f69e1930` |

`__init__.py` est propre au banc (vide) : le `__init__.py` amont, qui importe le paquet `ifbench` en absolu et expose `data_path`, n'est pas copié.

## Modifications

- Imports `from ifbench import …` rendus relatifs (`from . import …`, `from .instructions import Instruction`) dans `instructions.py`, `classic_instructions.py` et `instructions_registry.py`.
- `instructions.py` : retrait du dossier `.nltk_data` créé à l'import à côté du fichier, du `NLTK_DATA` forcé par `os.environ.setdefault` et de l'insertion de ce dossier dans `nltk.data.path`. Les données NLTK sont celles du banc (`grading/nlp.py`).
- Aucune autre modification : les vérificateurs, le registre et les utilitaires sont tels que publiés (indentation et style compris).

## Téléchargements retirés

- `instructions_util.py` : fonction `download_nltk_resources()` (quatre `nltk.download` : `punkt`, `punkt_tab`, `stopwords`, `averaged_perceptron_tagger_eng`) et son appel à l'import. Ces données sont téléchargées avant campagne par `fetch-nltk` (AD-15).
