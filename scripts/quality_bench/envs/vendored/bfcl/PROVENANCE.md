# Provenance : BFCL (Berkeley Function Calling Leaderboard), classes d'environnement multi-tours

- **Dépôt :** https://github.com/ShishirPatil/gorilla (dossier `berkeley-function-call-leaderboard/bfcl_eval/eval_checker/multi_turn_eval/func_source_code/`)
- **Commit :** `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`
- **Licence :** Apache-2.0 (`LICENSE` à la racine du dépôt, copié tel quel ; aucun `NOTICE`)
- **Récupéré le :** 2026-10-11 (fichiers bruts du commit, hors dépôt)

Ces classes vivent sous `envs/` et non sous `grading/vendored/` (écart au spine assumé par la story 4) : le runner (`generation/`) les exécute et n'importe jamais `grading/`. Elles entrent donc dans `harness_hash`.

## Fichiers copiés

| Fichier amont | Copie | `sha256` amont |
|---|---|---|
| `LICENSE` (racine du dépôt) | `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `__init__.py` | `__init__.py` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `gorilla_file_system.py` | `gorilla_file_system.py` | `84173750930b09aaa31b90547c9bd79ce75714682608b35e78a9c1ea259faf2b` |
| `math_api.py` | `math_api.py` | `abde32cc25e71b2ff3acf4d028a3c005b98409c174aba4abddbfe1c018afb9a8` |
| `message_api.py` | `message_api.py` | `cf72af1635654147af17df1891a7fb354549e78a61930139f741a31f4be21121` |
| `posting_api.py` | `posting_api.py` | `32b887aaa37c7167ad9c84ddfa7bbb855c75d3c1edab19ba868aba29acc4cfa1` |
| `ticket_api.py` | `ticket_api.py` | `6a9375aa6425410c07a151aef27f3e44e9ed1023bb5cc5c25f14f4a9b3c99116` |
| `trading_bot.py` | `trading_bot.py` | `cc2e3949035b561e9d07418b081561aa07b211672200e2e511aec074bf79fcb2` |
| `travel_booking.py` | `travel_booking.py` | `e698e22adccf0d6d41b297f2d5e44faebd828cef4752df6a4ffb1570c0c35296` |
| `vehicle_control.py` | `vehicle_control.py` | `f5f7a2f28968728927a98ae12ec68a32d70781cfb74c2d7b14801772362b12d1` |
| `long_context.py` | `long_context.py` | `5c9a5710115609c779e5b2ccb43f6ad58271ed96f2ea7a797edb0d65c385aa38` |

`envs/vendored/__init__.py` (vide) est propre au banc. Non copiés : `web_search.py` (réseau) et les classes de mémoire (`memory_*.py`), hors de la suite multi-tours du banc.

## Modifications

Sources de non-déterminisme figées (horloge et fuseau de la machine, ordre d'un ensemble) ; le reste est tel que publié.

- **Imports** `from bfcl_eval…long_context import (…)` rendus relatifs (`from .long_context import (…)`) dans `gorilla_file_system.py`, `trading_bot.py`, `travel_booking.py` et `vehicle_control.py`.
- **`gorilla_file_system.py`** : les trois `datetime.datetime.now()` de `File` (attribut privé `_last_modified`, jamais lu ni comparé) deviennent la constante `_FROZEN_NOW = datetime.datetime(2024, 9, 1, 10, 30)`, la date de `CURRENT_TIME` de `trading_bot.py`. `import subprocess`, inutilisé, est retiré.
- **`travel_booking.py`** : `datetime.today()` (calcul de l'âge dans `verify_traveler_information`) devient `datetime(2024, 9, 1, 10, 30)`.
- **`trading_bot.py`** : `_generate_transaction_timestamp` convertit `CURRENT_TIME` en horodatage et retour en UTC (`replace(tzinfo=timezone.utc)`, `datetime.fromtimestamp(…, tz=timezone.utc)`) au lieu de l'heure locale de la machine ; hors changement d'heure dans la journée, la chaîne produite est celle de BFCL, sur toute machine.
- **`ticket_api.py`** : `edit_ticket` joint les champs refusés dans l'ordre trié (`', '.join(sorted(invalid_fields))`) et non dans celui d'un `set`, qui dépend de `PYTHONHASHSEED` et change d'un processus à l'autre : sans cela, `grade` rejoue le message dans un autre ordre que la génération et sort la ligne en `error` (rejeu divergent).

Le hasard reste celui de BFCL : chaque classe tire dans son propre `random.Random(random_seed)` de l'état initial, jamais dans le `random` global.

## Téléchargements retirés

Aucun : ces fichiers ne téléchargent rien. `math_api.py` importe `mpmath` (installé par `requirements.txt`).
