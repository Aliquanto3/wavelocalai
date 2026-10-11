# Sources publiques du banc de qualité difficile

Ce fichier décrit les jeux publics importés par le banc, leurs licences et les commandes qui les téléchargent. Il ne contient aucune question.

Les données téléchargées restent hors du dépôt, sous `$QUALITY_BENCH_DATA` (par défaut `data/quality_bench/`, ignoré par git). Le dépôt ne versionne que :
- les révisions et les empreintes `sha256`, dans chaque importeur de `questions/importers/` ;
- les licences, dans `questions/schema.py` (`SOURCES`) et ci-dessous.

## Commandes d'avant campagne

À lancer depuis la racine du dépôt, dans `.venv-quality`, **avant** toute campagne et jamais pendant (AD-15). Chaque commande prend `$QUALITY_BENCH_DATA/machine.lock` : elle refuse de démarrer si une génération, un jugement ou un autre téléchargement tourne, et rend le code 1.

```powershell
# Facultatif : autre racine de données que data/quality_bench
$env:QUALITY_BENCH_DATA = "D:\quality_bench"

# Jeux publics : fichiers bruts sous sources/<slug>/raw/<hôte>/<dépôt>/<révision>/,
# questions candidates dans sources/<slug>/candidates.jsonl
.venv-quality\Scripts\python -m scripts.quality_bench fetch --all
.venv-quality\Scripts\python -m scripts.quality_bench fetch --source piaf --source ifbench

# Données NLTK (punkt, punkt_tab, stopwords, averaged_perceptron_tagger_eng) sous $QUALITY_BENCH_DATA/nltk_data
.venv-quality\Scripts\python -m scripts.quality_bench fetch-nltk
```

- **Empreintes :** chaque fichier est vérifié contre son empreinte épinglée, avant toute conversion. Un fichier déjà présent et intact n'est pas retéléchargé. En cas d'empreinte inattendue, le fichier est supprimé, aucun candidat de la source n'est écrit et la commande rend le code 1 :
  - après un téléchargement, la source a changé en amont : la revoir avant de mettre à jour l'importeur ;
  - sur un fichier local modifié, relancer `fetch` suffit à le retélécharger.
- **Codes de sortie :** 0 si tout est importé ; 1 si `machine.lock` est occupé, si une empreinte est inattendue ou si le réseau échoue ; 2 pour une source refusée ou inconnue (rien n'est téléchargé).
- **Réexécution :** relancer `fetch` réécrit les candidats, octet pour octet identiques à révision égale.
- **NLTK :** la correction (story 4) lit ces données par la variable `NLTK_DATA`, qui pointe sur `$QUALITY_BENCH_DATA/nltk_data`. Le code emprunté ne télécharge jamais rien.
- **Prompts trop longs :** une question qu'aucun palier `num_ctx` par défaut ne contient (`est × 1,25 + plafond de réponse`) est écartée, et le compte est journalisé. Son numéro n'est pas réattribué.
- **Journal :** `sources/log-fetch.log` et `sources/log-fetch-nltk.log`.

## Sources retenues

Révisions et effectifs relevés le 2026-10-11.

| Slug | Usage | Emplacement et révision | Fichiers | Licence | Candidats |
|---|---|---|---|---|---|
| `bbeh-mini` | `reasoning` | GitHub `google-deepmind/bbeh` @ `80d12ca916b7158f22293fcf3144f4d3d854d4be` | `bbeh/mini/data.json` | CC-BY-4.0 (données) ; code Apache-2.0 | 460 |
| `ifbench` | `instructions` | GitHub `allenai/IFBench` @ `1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d` | `data/IFBench_test.jsonl` | ODC-BY-1.0 (données) ; code Apache-2.0 | 300 |
| `mifeval-fr` | `instructions` | GitHub `lightblue-tech/M-IFEval` @ `10b874dbf8c4ca25ed5d876e1d3226e7f3f9d0dc` | `data/fr_input_data.jsonl` | Apache-2.0 | 235 |
| `bfcl-live` | `tools` | GitHub `ShishirPatil/gorilla` @ `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` | `BFCL_v4_live_simple`, `BFCL_v4_live_multiple` et leurs `possible_answer` | Apache-2.0 | 1 311 |
| `bfcl-parallel` | `tools` | idem | `BFCL_v4_live_parallel`, `BFCL_v4_live_parallel_multiple` et leurs `possible_answer` | Apache-2.0 | 40 |
| `bfcl-multi` | `tools` | idem | `BFCL_v4_multi_turn_base`, son `possible_answer`, `multi_turn_func_doc/*.json` (8 classes) | Apache-2.0 | 200 |
| `bfcl-irrelevance` | `abstention` | idem | `BFCL_v4_live_irrelevance` | Apache-2.0 | 884 |
| `jsonschemabench` | `extraction` | Hugging Face `epfl-dlab/JSONSchemaBench` @ `5bd0f4640badc6f3f02df796421d21cb0ca0b141` | `<sous-ensemble>/test-00000-of-00001.parquet` (10 sous-ensembles) | MIT | 2 787 (68 schémas trop longs écartés) |
| `piaf` | `rag` | GitHub `etalab-ia/piaf-code` @ `86948a73b26498948e70ad92e4b9b0231eac81f7` | `piaf-v1.0.json` | MIT | 3 835 |

Les fichiers BFCL sont sous `berkeley-function-call-leaderboard/bfcl_eval/data/`.

**Attribution** (CC-BY-4.0, ODC-BY-1.0) :
- BBEH : Kazemi et al., *BIG-Bench Extra Hard*, Google DeepMind (2025).
- IFBench : Pyatkin et al., *Generalizing Verifiable Instruction Following*, Allen Institute for AI (2025).

### Notes sur les sources

- **BBEH :** le README sépare le code (Apache-2.0) des autres contenus (CC-BY-4.0). Le fichier mini ne porte pas l'étiquette de tâche : chaque item forme son propre groupe.
- **IFBench :** le jeu Hugging Face n'existe qu'en parquet, d'où la copie JSONL du dépôt GitHub. Le paquet `ifbench` annoncé par le README n'existe pas sur PyPI.
- **BFCL :** le jeu Hugging Face s'arrête à la v3, d'où le dépôt GitHub (v4). La catégorie `parallel` non-live appartient à « BFCL non-live AST », refusée : seules les catégories parallèles *live* sont importées.
- **JSONSchemaBench :** la seule licence déclarée est l'étiquette MIT de la carte Hugging Face. Les dépôts GitHub n'ont pas de fichier LICENSE.
- **PIAF :** c'est la v1.0 sous MIT (Etalab). La v1.2 de data.gouv a une licence non précisée et n'est pas utilisée.

## Sources refusées

Ces sources sont listées dans `REFUSED_SOURCES` de `questions/schema.py`. Une question qui les porte est refusée, et `fetch` ne les télécharge pas.

| Slug | Raison |
|---|---|
| `ifeval` | saturé chez les SLM récents (≥ 80 % dès 2B) |
| `ifeval-fr` | aucune licence déclarée |
| `fquad` | non commercial, redistribution interdite |
| `gsm-symbolic` | CC-BY-NC-ND : pas d'adaptation FR distribuable |
| `math-500` | contamination de Qwen2.5 (reproduction mot pour mot) |
| `musr` | ne discrimine pas (0,33 à 0,41 de 1B à 14B) |
| `bfcl-non-live-ast` | au plafond (~88 % dès 4B) |
| `bfcl-web-search` | exige SerpAPI, donc le réseau |

## Mettre à jour une source

1. Changer la révision dans l'importeur. La révision fait partie du chemin local : les fichiers de l'ancienne révision restent en place.
2. Télécharger les fichiers et relire le changement en amont.
3. Recopier les nouvelles empreintes dans l'importeur.
4. Relancer `fetch --source <slug>`.

Un jeu de questions déjà construit (story 3) n'est jamais modifié : un nouvel import implique un nouveau jeu.
