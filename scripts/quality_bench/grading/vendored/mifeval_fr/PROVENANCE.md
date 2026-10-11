# Provenance : M-IFEval (français seulement)

- **Dépôt :** https://github.com/lightblue-tech/M-IFEval
- **Commit :** `10b874dbf8c4ca25ed5d876e1d3226e7f3f9d0dc`
- **Licence :** Apache-2.0 (`LICENSE.txt` amont, copié tel quel sous le nom `LICENSE`)
- **Récupéré le :** 2026-10-11 (archive du commit, hors dépôt)

## Fichiers copiés

| Fichier amont | Copie | `sha256` amont |
|---|---|---|
| `LICENSE.txt` | `LICENSE` | `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd` |
| `instructions/fr_instructions.py` | `instructions/fr_instructions.py` | `34b5dec67faf87745d97ca75c55a8e33b68ac153aa64efa0ca52f5abf1824633` |
| `instruction_utils/fr_instructions_util.py` | `instruction_utils/fr_instructions_util.py` | `05ad253c59094dddc1fb35919682d5a7d653ba847d3590f2ea00bad85e7f9100` |
| `instructions_registry.py` | `instructions_registry.py` (réduit) | `fa35119e963d1be9c2223f2eb2a23ff161e6f93c80ae2a9b58526b8d5f56dced` |

Les fichiers anglais, espagnols et japonais ne sont pas copiés. Les `__init__.py` (vides) sont propres au banc.

## Modifications

- `instructions/fr_instructions.py` : `from instruction_utils import fr_instructions_util` devient `from ..instruction_utils import fr_instructions_util`. Rien d'autre.
- `instructions_registry.py` réduit au français : import du seul `fr_instructions` (relatif), préfixes `_KEYWORD`… et `FR_INSTRUCTION_DICT` tels que publiés, puis `INSTRUCTION_DICT` construit avec le seul préfixe `fr:`. `EN_INSTRUCTION_DICT`, `JA_INSTRUCTION_DICT`, `ES_INSTRUCTION_DICT` et leurs imports sont retirés : le registre n'expose que des identifiants `fr:…`.
- Pas de spaCy : aucun des fichiers français n'en dépend (seul le japonais, non copié, s'en sert).

## Téléchargements retirés

- `instruction_utils/fr_instructions_util.py` : `nltk.download('punkt_tab')` exécuté à l'import. `punkt_tab` (et `punkt`, dont `french.pickle`) est téléchargé avant campagne par `fetch-nltk` (AD-15).
