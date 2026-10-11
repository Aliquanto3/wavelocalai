# Provenance : BFCL (Berkeley Function Calling Leaderboard), correcteurs

- **Dépôt :** https://github.com/ShishirPatil/gorilla (dossier `berkeley-function-call-leaderboard/bfcl_eval/`)
- **Commit :** `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`
- **Licence :** Apache-2.0 (`LICENSE` à la racine du dépôt, copié tel quel ; aucun `NOTICE`)
- **Récupéré le :** 2026-10-11 (fichiers bruts du commit, hors dépôt)

Les classes d'environnement multi-tours sont copiées à part, sous `envs/vendored/bfcl/` (voir son `PROVENANCE.md`) : `generation/` les exécute et n'importe jamais `grading/`.

## Fichiers copiés

Chemins amont relatifs à `berkeley-function-call-leaderboard/bfcl_eval/`.

| Fichier amont | Copie | `sha256` amont |
|---|---|---|
| `LICENSE` (racine du dépôt) | `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `constants/enums.py` | `constants/enums.py` | `2182becfa2a1d071ee1db30db593b4758c6bf866aa12d2d4b8daf09175ea518a` |
| `constants/type_mappings.py` | `constants/type_mappings.py` | `1702fb67afbe2c492608e58e2b7d02e46381f50166b47f3c952f76e34c7cd3bd` |
| `eval_checker/ast_eval/ast_checker.py` | `ast_eval/ast_checker.py` | `2aae7a68461a8f76c0be3894c8901b66b56967a1989d3ab066051e3fb97f1538` |
| `eval_checker/ast_eval/type_convertor/__init__.py` | `ast_eval/type_convertor/__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `eval_checker/ast_eval/type_convertor/java_type_converter.py` | `ast_eval/type_convertor/java_type_converter.py` | `2fd4f4b0443b3dd974a1723bb4e45c086d7b352631062da7807ad1ad40706604` |
| `eval_checker/ast_eval/type_convertor/js_type_converter.py` | `ast_eval/type_convertor/js_type_converter.py` | `a114e9ff75c025cb52787ac33d6c2fbaa390905c6125a2b3c6afebab232bb5e4` |
| `eval_checker/multi_turn_eval/multi_turn_checker.py` | `multi_turn_eval/multi_turn_checker.py` | `b3b787515eda3bf0e365e39634a8fc7f831763f010f716d35d86f96fd5aab1b5` |
| `eval_checker/multi_turn_eval/multi_turn_utils.py` (extrait) | `multi_turn_eval/multi_turn_checker.py` (`is_empty_execute_response`) | `9fdbd779ec715959c310445b54b431e91abaa8b45a302abb6fd8db8d61b62ba2` |

Les autres `__init__.py` (vides) sont propres au banc.

## Modifications

- **Imports** `from bfcl_eval… import …` rendus relatifs (`ast_checker.py`, `java_type_converter.py`, `js_type_converter.py`).
- **`ast_checker.py`, lien vers `MODEL_CONFIG_MAPPING` retiré** : l'import de `bfcl_eval.constants.model_config` est supprimé et le paramètre `model_name: str` devient `underscore_to_dot: bool` dans toutes les fonctions qui le relaient (même position). `convert_func_name(function_name, underscore_to_dot)` remplace `MODEL_CONFIG_MAPPING[model_name_escaped].underscore_to_dot` par ce booléen, lu dans `grader.params.underscore_to_dot` de la question. Le reste est tel que publié.
- **`multi_turn_checker.py`, exécuteur injecté au lieu d'`eval`** : l'import de `execute_multi_turn_func_call` (qui exécute les appels par `eval` d'une chaîne) est retiré ; le dernier paramètre `model_name: str` devient `executor`, et les deux appels à `execute_multi_turn_func_call(...)` deviennent `executor(func_call_list=…, ground_truth=False)` (pas du modèle) et `executor(func_call_list=…, ground_truth=True)` (cible du tour). L'exécuteur (`grading/tools.py`) rend `(résultats en chaînes, instances)` depuis deux environnements `envs/` neufs, gardés d'un tour à l'autre. `is_empty_execute_response`, seule autre fonction importée de `multi_turn_utils.py`, est recopiée sans changement en tête du fichier. Le reste (vérification d'état, de réponses, `multi_turn_irrelevance_checker`) est tel que publié.

## Téléchargements retirés

Aucun : ces fichiers ne téléchargent rien.
