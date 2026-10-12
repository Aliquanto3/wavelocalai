# Sources du banc de qualité difficile

Ce fichier décrit les sources du banc (jeux publics importés, générateurs à graine, questions maison), leurs licences, et les commandes qui les téléchargent et construisent le jeu. Il ne contient aucune question.

Les données téléchargées restent hors du dépôt, sous `$QUALITY_BENCH_DATA` (par défaut `data/quality_bench/`, ignoré par git). Le dépôt ne versionne que :
- les révisions et les empreintes `sha256`, dans chaque importeur de `questions/importers/` ;
- les licences, dans `questions/schema.py` (`SOURCES`) et ci-dessous.

## Commandes d'avant campagne

À lancer depuis la racine du dépôt, dans `.venv-quality`, **avant** toute campagne et jamais pendant (AD-15). Chaque commande prend `$QUALITY_BENCH_DATA/machine.lock` : elle refuse de démarrer si une génération, un jugement ou un autre téléchargement tourne, et rend le code 1.

```powershell
# Facultatif : autre racine de données que data/quality_bench
$env:QUALITY_BENCH_DATA = "D:\quality_bench"

# Jeux publics : fichiers bruts sous sources/<slug>/raw/<hôte>/<dépôt>/<révision>/,
# questions candidates dans sources/<slug>/candidates.jsonl ; --all inclut le lot oneruler-fr
.venv-quality\Scripts\python -m scripts.quality_bench fetch --all
.venv-quality\Scripts\python -m scripts.quality_bench fetch --source piaf --source ifbench

# Lot brut du générateur OneRuler FR, sous sources/oneruler-fr/raw/ (sans candidats)
.venv-quality\Scripts\python -m scripts.quality_bench fetch --source oneruler-fr

# Données NLTK (punkt, punkt_tab, stopwords, averaged_perceptron_tagger_eng) sous $QUALITY_BENCH_DATA/nltk_data
.venv-quality\Scripts\python -m scripts.quality_bench fetch-nltk
```

- **Empreintes :** chaque fichier est vérifié contre son empreinte épinglée, avant toute conversion. Un fichier déjà présent et intact n'est pas retéléchargé. En cas d'empreinte inattendue, le fichier est supprimé, aucun candidat de la source n'est écrit et la commande rend le code 1 :
  - après un téléchargement, la source a changé en amont : la revoir avant de mettre à jour l'importeur ;
  - sur un fichier local modifié, relancer `fetch` suffit à le retélécharger.
- **Codes de sortie :** 0 si tout est importé ; 1 si `machine.lock` est occupé, si une empreinte est inattendue ou si le réseau échoue ; 2 pour une source refusée ou inconnue, ou pour une source générée ou maison, qui n'a rien à télécharger (rien n'est téléchargé).
- **Réexécution :** relancer `fetch` réécrit les candidats, octet pour octet identiques à révision égale.
- **NLTK :** la correction lit ces données sous `$QUALITY_BENCH_DATA/nltk_data` et nulle part ailleurs : `grading/nlp.py` réduit `nltk.data.path` à ce seul dossier avant chaque vérification (la variable `NLTK_DATA` n'est pas lue). Le code emprunté ne télécharge jamais rien.
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

## Sources générées

Les générateurs sont des fonctions pures à graine (`questions/generators/`). `build-set` les appelle en mémoire, sans écrire de candidats. La même graine (`generator_seed` du YAML de jeu) donne les mêmes empreintes.

| Slug | Usage | Générateur | Correcteur | Licence | Entrée |
|---|---|---|---|---|---|
| `oneruler-fr-niah` | `rag` | `oneruler_fr@1` (`generate_niah`) | `oneruler_niah` | MIT | lot `oneruler-fr` |
| `oneruler-fr-cwe` | `rag` | `oneruler_fr@1` (`generate_cwe`) | `oneruler_cwe` | MIT | lot `oneruler-fr` |
| `oneruler-fr-none` | `abstention` | `oneruler_fr@1` (`generate_none`) | `oneruler_niah` (cible nulle) | MIT | lot `oneruler-fr` |
| `var-math-fr` | `reasoning` | `var_math_fr@1` | `exact_answer` (`answer_prefix` « La réponse est : ») | privée | `private/var-math-fr.yaml` |

**Lot `oneruler-fr`** : GitHub `mungg/OneRuler` @ `a3fe6af862dc4b30794afc0a8f3d4f60758cecfa`. Quatre fichiers sont épinglés dans `generators/oneruler_fr.py` (`RAW_FILES`) :
- `LICENSE` (MIT, Yekyung Kim, 2025) ;
- `OneRuler/data/books/fr/les_miserables_fr.txt` (Victor Hugo, domaine public) ;
- `OneRuler/data/prompt/fr/niah.txt` et `OneRuler/data/prompt/fr/cwe.txt` (gabarits FR, MIT).

Les empreintes ont été relevées le 2026-10-11 par un premier `fetch`, puis recoupées avec les SHA-1 de blob Git de l'arbre du dépôt à cette révision. Le dossier `OneRuler/data/vocab/` (licence non déclarée) n'est jamais téléchargé : clés et mots viennent du vocabulaire du livre. `stanza` n'est pas utilisé : les phrases sont découpées par l'expression régulière de repli de OneRuler. Le gabarit CWE amont demande « votre traduction » au lieu de « votre réponse » : il est repris tel quel.

**Recette OneRuler :**
- botte de foin : extrait contigu du livre, à partir d'une phrase tirée ;
- aiguilles « Le nombre magique spécial pour "<clé>" est : <valeur>. », insérées à des profondeurs tirées parmi 40 points de 0 à 100 % ; valeurs à 7 chiffres ;
- variantes NIAH : `single`, `multikey` (quatre clés dont trois distracteurs) et `multivalue` (quatre valeurs) ;
- `none` : quatre aiguilles distractrices, clé demandée absente (réponse « aucun ») ;
- CWE : 10 mots fréquents, niveau facile (30 contre 3) et difficile (20 contre 10).

Chaque question remplit au plus près son palier (8192, 16384 ou 32768, à parts égales) sans le dépasser selon la règle d'AD-5. Ces paliers sont nominaux : le remplissage suit l'estimation d'AD-5 (3 caractères par token, marge de 1,25 et plafond de réponse), si bien que la longueur réelle du prompt en tokens reste nettement inférieure au palier. Une question par groupe.

**Format `qb.var_math/1`** (fichier privé) :

```yaml
schema: qb.var_math/1
problems:
  - number: 1                          # entier ≥ 1, unique
    text: "… {a} … {b} … ?"            # chaque paramètre y figure ; {nom} = paramètre ou dérivé
    params: {a: {min: 2, max: 30, step: 2}, b: {min: 1, max: 9}}
    derived: {c: "a * b"}               # facultatif, évalué dans l'ordre
    constraints: ["c % 4 == 0"]         # toutes vraies, sinon le tirage est rejeté
    answer: "c // 4"                    # entier
```

Les expressions passent par un évaluateur AST restreint, jamais par `eval`. Il n'admet que les entiers, `+ - * // % **` (exposant de 0 à 10), les comparaisons, `and`, `or`, `not`, `min`, `max` et `abs`. Chaque problème donne 3 variantes distinctes (`generator_params.variants`), tirées avec rejet borné, qui partagent `group` et `unit` (`reasoning/var-math-fr/p<numéro>`).

## Questions maison

Elles sont lues par `questions/house.py`, au format `qb.house/1`.

| Slug | Usage | Correcteur | Licence | Fichier |
|---|---|---|---|---|
| `writing-fr` | `writing` | `judge_criteria` | MIT | `questions/writing/writing-fr.yaml` (versionné : le juge cloud doit le lire) |
| `instructions-fr` | `instructions` | `mifeval_fr` | privée | `$QUALITY_BENCH_DATA/private/instructions-fr.yaml` |
| `tools-fr` | `tools` | `bfcl_ast` | privée | `$QUALITY_BENCH_DATA/private/tools-fr.yaml` |
| `extraction-fr` | `extraction` | `json_schema` | privée | `$QUALITY_BENCH_DATA/private/extraction-fr.yaml` |
| `abstention-fr` | `abstention` | `abstention_marker` | privée | `$QUALITY_BENCH_DATA/private/abstention-fr.yaml` |

```yaml
schema: qb.house/1
source: extraction-fr
questions:
  - number: 1
    group: extraction-fr/0001           # facultatif ; « <source>/<numéro> » pour une source privée
    messages: [{role: user, content: "…"}]
    turns: null                          # facultatifs : turns, tools, format
    grader_params: {schema: {…}, subset: extraction-fr}
    target: {…}
    criteria: [{id: c1, question: "… ?"}]   # rédaction seulement : 4 à 6 questions fermées
  - number: 2
    derived_from: tools/bfcl-live/0042   # tools-fr seulement : clés number, derived_from, messages
    messages: [{role: user, content: "…"}]
```

- **Clés inconnues refusées.** Aucune cible flottante. Paramètres de correcteur exigés :
  - `mifeval_fr` : `{instruction_id_list, key, kwargs}`, identifiants `fr:…`, `kwargs` alignés ;
  - `json_schema` : `{schema, subset}`, schéma recopié dans le prompt sous la forme `json.dumps(…, sort_keys=True, ensure_ascii=False, indent=2)`, cible conforme au schéma ;
  - `abstention_marker` : `{marker}`, marqueur cité tel quel dans la consigne ;
  - `judge_criteria` : `{}`.
- **Traductions (`derived_from`) :** la question copie `tools`, `format`, `env`, `turns`, `grader.params`, `target` et `group` du candidat d'origine (`sources/bfcl-live/candidates.jsonl`) et ne remplace que `messages`, avec les mêmes rôles. `tools-fr` vient avant `bfcl-live` dans le YAML de jeu : le groupe pris par la traduction est exclu de l'échantillon anglais.
- **Questions privées :** `private = true`, `license = "private"`, groupe et `unit` opaques. Elles ne vivent que sous `$QUALITY_BENCH_DATA/private/`, jamais dans le dépôt, un test, un échantillon de `tests/`, une PR ou un journal. Le journal de `build-set` ne porte que l'empreinte `sha256` de chaque fichier lu.
- **Sauvegarde des fichiers privés :** copier `private/` hors de la machine (support chiffré ou coffre personnel) après chaque modification. Sans ces fichiers, un jeu qui les cite ne peut plus être reconstruit.

## Construire et relire le jeu

```powershell
# Jeu figé : sets/<s>/questions.jsonl et tracks.json (hors dépôt), index versionné
# benchmarks/quality/sets/<s>/index.jsonl ; prend machine.lock, aucun accès réseau
.venv-quality\Scripts\python -m scripts.quality_bench build-set --set set-v1

# Échantillons de relecture, hors dépôt : review/private-sample.md et review/writing-sample.md
.venv-quality\Scripts\python -m scripts.quality_bench review-sample --set set-v1 --per-source 5 --writing 10
```

- **`build-set`** lit `scripts/quality_bench/sets/<s>.yaml` : `set`, `seed`, `sources: [{source, count, per_group?, generator_seed?, generator_params?, exclude?}]` et `think_on: {<usage>: effectif}`.
  - `exclude` : liste d'identifiants de questions de la source (`tools/bfcl-live/0107`), chaînes non vides et sans doublon (sinon code 2). Ils sont retirés des candidats avant tout tirage. Un identifiant absent des candidats (faute de frappe, renumérotation après un changement de révision) refuse le jeu (code 1). Le commentaire du YAML garde la raison et l'identifiant amont de chaque exclusion. `set-v1` exclut ainsi 5 cibles `bfcl-live` défectueuses dans BFCL lui-même : aucune réponse ne les passe, même avec le correcteur amont. On exclut par cette liste, jamais en éditant les candidats.
  - Il tire chaque source par groupes entiers, dans l'ordre du YAML, puis `think_on` par usage et par groupes entiers.
  - Mêmes entrées et même graine : les trois fichiers sont identiques octet pour octet.
  - Le jeu s'écrit une fois : la commande refuse si `sets/<s>/` ou `benchmarks/quality/sets/<s>/` existe, et n'écrit rien en cas d'échec.
  - Codes de sortie : 0 ; 1 si la machine est occupée, si le jeu existe, si une source ou un fichier privé manque, si un fichier brut a une empreinte inattendue, si un identifiant exclu est absent des candidats, si un effectif est inatteignable ou si un palier est insuffisant ; 2 si le YAML de jeu est invalide.
  - Journal : `sets/log-build-set.log`, avec le nombre de questions exclues par source, l'empreinte du jeu (AD-4) et celle de chaque fichier écrit.
- **Index versionné** (`qb.set_index/1`, liste blanche d'AD-6) : `id, usage, group, unit, source, license, private, question_hash`, plus `prompt_hash, target_hash` pour les seules questions publiques.
- **`review-sample`** assemble le jeu en mémoire, sans verrou et sans écrire de jeu (ni `sets/<s>/`, ni `benchmarks/`). Il n'écrit que les deux échantillons sous `$QUALITY_BENCH_DATA/review/` (id, groupe, messages, tours, outils, cible, critères) et son journal `sets/log-review-sample.log`. Ne jamais commiter ni copier les échantillons dans une PR.

## Correction

La correction est une phase séparée, sans réseau, sans GPU et sans verrou machine (AD-3, AD-10). Elle seule écrit un score.

```powershell
# Réécrit campaigns/<c>/grading.jsonl en entier ; journal campaigns/<c>/log-grade.log
.venv-quality\Scripts\python -m scripts.quality_bench grade --campaign pilot-20261015
```

- **Entrées lues :** `campaigns/<c>.yaml` (jeu, `grading.judge`), `campaigns/<c>/manifest.json` et `generation.jsonl`, le jeu `sets/<set>/` et, pour la rédaction, le seul dossier `judgment-<grading.judge>/`. Rien d'autre n'est lu ni modifié.
- **Sortie :** une ligne `qb.grading/1` par ligne de génération, canonique, triée par `key`, sans date : `generation_manifest` (empreinte du manifeste de génération), `judgment_manifest` (rédaction jugée seulement), `grader` (`nom@version`), `status`, `score`, `success`, `metrics`. Recorriger les mêmes entrées donne des octets identiques.
- **Statuts :** statut de génération d'abord (`truncated` : 0 et échec, rédaction 0 et `success` nul ; `context_exceeded` et `error` : ni score ni succès), puis borne d'appels (`non_compliant`), puis le correcteur. `non_compliant` (JSON illisible ou hors schéma, appel d'outil mal formé, borne d'appels) est un échec du modèle ; `error` (vérificateur en défaut, identifiant de consigne inconnu, cible illisible, rejeu divergent, verdict du juge en erreur) est une erreur du banc. Rédaction sans verdict complet, sans juge désigné ou sans dossier de jugement : `awaiting_judgment`. `metrics.inline_thinking` vaut 1.0 si la réponse contenait `<think>`.
- **Codes de sortie :** 0 ; 1 si les entrées sont incohérentes (manifeste absent, jeu ou empreinte du jeu différents, question absente du jeu, `prompt_hash` différent, ligne de génération ou de jugement d'un autre manifeste ou hors schéma) ; 2 si `campaigns/<c>.yaml` est absent ou invalide. Dans les deux cas d'échec, rien n'est écrit.
- **Journal :** identifiants, statuts, comptes et raisons rédigées par le banc ; jamais de contenu de question ni de réponse.

### Correcteurs

Registre `grading/registry.py`, un correcteur par nom de `GRADERS`, tous en version 1. Seul `grading/answer.py` lit `output` : réponse finale = dernier message `assistant`, texte après la dernière `</think>` (balise ouvrante seule : texte avant elle).

| Correcteur | Sources | Règle |
|---|---|---|
| `exact_answer@1` | `bbeh-mini` ; `var-math-fr` | cible chaîne : `evaluate_correctness` de BBEH ; cible entière : dernier « La réponse est : » (casse et espace avant « : » libres), première ligne qui suit, `*`, `$`, `\boxed{}`, espaces de milliers et point final retirés, entier exact ; sans préfixe : échec |
| `ifbench@1`, `mifeval_fr@1` | `ifbench` ; `mifeval-fr`, `instructions-fr` | boucle « strict » amont, `kwargs` nuls retirés, réponse vide non suivie ; succès = toutes suivies ; `metrics.instructions_followed` |
| `bfcl_ast@1` | `bfcl-live`, `bfcl-parallel`, `tools-fr` | appels du tour 0, `ast_checker` de BFCL (Python, catégorie de la question) |
| `bfcl_state@1` | `bfcl-multi` | rejeu des appels dans `envs/`, puis `multi_turn_checker` de BFCL (état et réponses) ; tour absent ou rejeu divergent : erreur |
| `bfcl_irrelevance@1` | `bfcl-irrelevance` | succès si aucun appel d'outil |
| `json_schema@1` | `jsonschemabench`, `extraction-fr` | JSON décodé (clôtures Markdown admises) et vérifié contre le schéma (`$schema` déclaré, aucune résolution distante) ; avec cible : feuilles comparées par chemin (clés et indices, listes par position), toutes les feuilles attendues retrouvées, `metrics.f1` |
| `squad_f1@1` | `piaf` | correspondance exacte après normalisation française, `metrics.f1` de jetons |
| `oneruler_niah@1`, `oneruler_cwe@1` | `oneruler-fr-niah`, `oneruler-fr-none` ; `oneruler-fr-cwe` | `compare_numbers`, `compare_none` (« aucun ») et `is_correct_order` de OneRuler |
| `abstention_marker@1` | `abstention-fr` | réponse sans espaces, guillemets, `*`, `` ` `` ni point final en bordure, égale au marqueur sans tenir compte de la casse |
| `judge_criteria@1` | `writing-fr` | score = part des critères jugés vrais sur tous les critères, `success` nul |

Le hasard global (`random`) est fixé puis restauré autour des vérificateurs de consignes, et `langdetect` reçoit la graine 0 avant tout chargement.

### Code emprunté

Copié tel que publié, avec `LICENSE` et `PROVENANCE.md` (dépôt, commit, empreintes `sha256` amont, modifications, téléchargements retirés) dans chaque dossier ; exclu de black, isort et ruff.

| Dossier | Projet @ commit | Licence | Modifications principales |
|---|---|---|---|
| `grading/vendored/ifbench/` | `allenai/IFBench` @ `1c40f0c1` | Apache-2.0 | imports relatifs ; `download_nltk_resources()` et le dossier `.nltk_data` retirés |
| `grading/vendored/mifeval_fr/` | `lightblue-tech/M-IFEval` @ `10b874db` | Apache-2.0 | fichiers FR seulement, registre réduit aux identifiants `fr:`, `nltk.download` retiré, sans spaCy |
| `grading/vendored/bfcl/` | `ShishirPatil/gorilla` @ `6ea57973` | Apache-2.0 | `MODEL_CONFIG_MAPPING` remplacé par `underscore_to_dot` ; `multi_turn_checker` avec exécuteur injecté au lieu d'`eval` |
| `envs/vendored/bfcl/` | `ShishirPatil/gorilla` @ `6ea57973` | Apache-2.0 | classes multi-tours : horloge figée (2024-09-01 10:30), horodatages en UTC, `import subprocess` retiré |
| `grading/vendored/bbeh/` | `google-deepmind/bbeh` @ `80d12ca9` | Apache-2.0 | `print` d'exemple exécutés à l'import retirés |
| `grading/vendored/oneruler/` | `mungg/OneRuler` @ `a3fe6af8` | MIT | extrait : `clean_text`, `compare_numbers`, `compare_none`, `is_correct_order`, `none_dict` réduit à `fr` |

Aucun `eval` ni `exec` sur une sortie de modèle ou une cible : une cible BFCL (`"cd(folder='document')"`) est analysée par `ast` (appel d'un nom, arguments littéraux), toute autre forme est une erreur du banc.

### Contrat d'outils (runner, story 5)

Les environnements d'outils vivent sous `envs/` (`bfcl_multi_turn@1`), purs et déterministes, et sont importables par `generation/` sans `grading/`.

1. Pour une question à `env` non nul, le runner crée un environnement neuf par conversation : `make_env(question["env"])`, gardé d'un tour à l'autre.
2. Pour chaque appel d'outil d'un message `assistant`, dans l'ordre, il appelle `env.call(name, arguments)` (`arguments` : objet JSON de l'appel) et écrit la chaîne rendue, telle quelle, comme `content` du message `tool` qui suit. `env.call` ne lève jamais pour un appel du modèle : une erreur est rendue en chaîne « Error during execution: … », comme dans BFCL.
3. Il ne persiste aucun état d'environnement : le correcteur rejoue les appels de `output` sur un environnement neuf et vérifie chaque contenu `tool` ; un écart est une erreur du banc.
4. Après les messages `tool` d'un pas, il rappelle le modèle. Le tour s'achève sur une réponse sans appel. Les messages de `turns[t-1]` sont alors injectés dans `output` (rôle `user`, `turn = t`) avant le tour suivant.
5. **Borne d'appels :** un pas dont les appels porteraient le total du tour au-delà de `max_tool_calls_per_turn` n'est pas exécuté. `call_cap_reached` vaut `true` et la question s'arrête, sortie gardée ; `grade` la compte `non_compliant`.
6. **`env` nul** (`bfcl-live`, `bfcl-parallel`, `bfcl-irrelevance`, `tools-fr`) : le tour s'achève sur la **première** réponse du modèle, appels compris, sans message `tool` ni nouvel appel. BFCL ne lit que la première réponse : « tous les appels du tour 0 » de `bfcl_ast@1` sont donc ceux de cette seule réponse. La borne d'appels ne s'applique qu'aux pas exécutés.
7. **Appel mal formé** (sans nom, ou arguments qui ne sont pas un objet) : la question s'arrête, sortie gardée, sans exécuter le pas ; `grade` le compte `non_compliant`.

## Générer une campagne

```powershell
# Campagne décrite par scripts/quality_bench/campaigns/<c>.yaml ; écrit campaigns/<c>/ (hors dépôt)
.venv-quality\Scripts\python -m scripts.quality_bench generate --campaign pilot-20261015
# Autre port local (seuls localhost et 127.0.0.1 sont permis)
.venv-quality\Scripts\python -m scripts.quality_bench generate --campaign pilot-20261015 --ollama-url http://127.0.0.1:11435
```

- **Avant tout manifeste**, la commande lit la configuration et le jeu, prend `machine.lock`, puis fait le préflight de chaque modèle par `/api/tags` et `/api/show`. Elle refuse le lancement (code 2, message qui nomme le modèle et la raison), sans rien écrire sous `campaigns/<c>/`, pour :
  - un modèle absent de `/api/tags`, sans `digest` ou distant (`remote_host`) ;
  - une capacité `decision`, ou `completion` absente ;
  - une piste `think_on` sans capacité `thinking`, ou avec `think_on` faux ou nul ;
  - une valeur `think` incohérente avec la capacité `thinking`, ou de type chaîne ;
  - une question à outils sélectionnée pour un modèle sans capacité `tools`.
- **Contexte effectif :** un palier au-delà de `min(num_ctx_max, <arch>.context_length)` donne une ligne `context_exceeded` sans requête.
- **Ordre :** modèle, piste (`think_off` puis `think_on`), palier croissant, question, seed. Une chauffe jetée, consignée dans `warmups.jsonl`, précède chaque changement du couple (modèle, `num_ctx`) et suit toute panne du service. Un avertissement est journalisé sous `min_prefill_tok_s` (50 par défaut). Le modèle est déchargé (`keep_alive: 0`) en fin de modèle et à toute sortie.
- **Arrêt et reprise :** Ctrl+C ou un fichier `campaigns/<c>/STOP` termine la question en cours, puis sort avec le code 0. La même commande reprend en sautant les clés présentes. Un manifeste différent (digest, capacités, version d'Ollama, jeu, configuration, machine, harnais) refuse la reprise.
- **Pannes :** une erreur d'Ollama compte un essai si `/api/version` répond aussitôt. Sinon, la commande attend le service jusqu'à `ollama_wait_s` sans le redémarrer, puis refait la question en entier sans compter l'essai. Après `max_attempts` essais : ligne `error`. Après `max_consecutive_errors` lignes `error` de suite : code 1.
- **Codes de sortie :** 0 (campagne complète ou arrêt propre) ; 1 (jeu absent ou incohérent, verrou occupé, Ollama injoignable, manifeste différent, service absent ou revenu dans une autre version, trop d'erreurs de suite) ; 2 (configuration invalide, sélection ou palier hors jeu, préflight refusé, URL non locale).
- **Journal :** `campaigns/<c>/log-generate.log`, ouvert une fois le préflight accepté. La liste de contrôle d'avant campagne (AD-13, `OLLAMA_NUM_PARALLEL`) y est affichée, et consignée dans `informative.checklist` du manifeste. Le journal ne contient jamais de contenu de question ni de réponse.

## Rapport

Le rapport est une phase séparée, sans réseau, sans GPU et sans verrou machine (AD-6, AD-17). Il lit `grading.jsonl` pour les scores, jamais `judgment.jsonl` ni `labels.jsonl`.

```powershell
# Réécrit benchmarks/quality/<c>/ en entier ; journal campaigns/<c>/log-report.log
.venv-quality\Scripts\python -m scripts.quality_bench report --campaign pilot-20261015
# Campagne incomplète : lignes écartées et comptées, rapport marqué partiel
.venv-quality\Scripts\python -m scripts.quality_bench report --campaign pilot-20261015 --partial
# Indice AA d'une date précise (par défaut : le fichier le plus récent)
.venv-quality\Scripts\python -m scripts.quality_bench report --campaign pilot-20261015 --aa-date 2026-10-01
```

- **Entrées lues :** `campaigns/<c>.yaml`, `campaigns/<c>/manifest.json`, `generation.jsonl`, `grading.jsonl`, le seul `judgment-<grading.judge>/manifest.json`, le jeu `sets/<set>/` et un fichier `benchmarks/quality/references/aa-<AAAA-MM-JJ>.json`. Rien d'autre n'est lu ni modifié.
- **Complétude :** les clés attendues sont `models_resolved` × pistes du modèle × questions de la piste restreintes à `selection` × seeds (`seed_base + epoch`, `epoch < k`), calculées depuis le `blocking` du manifeste et le jeu (même résolution de `selection` que le runner, `common/selection.py`).
- **Refus (code 1, rien n'est écrit) :**
  - une clé attendue manque dans `generation.jsonl` ou dans `grading.jsonl` ;
  - il reste une ligne `awaiting_judgment` ;
  - une empreinte ne concorde pas : ligne de génération d'un autre manifeste, `generation_manifest` ou `judgment_manifest` d'une ligne de correction différent, section `generation` de la configuration modifiée depuis le manifeste.

  Le journal nomme le premier écart et donne les comptes.
- **`--partial` :** les lignes manquantes, discordantes ou en attente du juge sont écartées et comptées (`completeness` du résumé). Une question écartée rend son unité nulle pour ce modèle, et le rapport est marqué partiel.
- **Entrées incohérentes (code 1, même avec `--partial`) :**
  - manifeste absent ou d'un autre jeu, empreinte du jeu différente ;
  - ligne hors schéma ou clé en double ;
  - question absente du jeu ou `prompt_hash` différent ;
  - clé de correction inconnue de `generation.jsonl` ;
  - référence AA hors schéma, ou date demandée absente ;
  - campagne nommée `sets`, `references` ou `calibration`.
- **Configuration :** `campaigns/<c>.yaml` absent ou invalide : code 2.
- **Statistiques :** unité = (`model`, `track`, `unit`). Les questions d'une unité sont agrégées par minimum, puis les seeds par moyenne. Une erreur du banc (`error`, `context_exceeded`) rend l'unité nulle pour ce modèle : elle est retirée de ses seules comparaisons, et comptée (`excluded`). Avec `k = 1`, un usage binaire est testé par McNemar exact avec un intervalle de Wilson. Avec `k > 1`, en rédaction, ou pour le score global d'une piste qui contient la rédaction : test z apparié à erreur-type groupée et IC bootstrap apparié (graine fixée). Le rapport publie aussi :
  - Holm sur les m − 1 comparaisons au meneur (m modèles du périmètre) ;
  - la matrice « qui bat qui » corrigée par BH ;
  - les groupes indiscernables, les IC simultanés et le rang approché ;
  - le taux de troncature ;
  - k̂_Bonferroni ;
  - Spearman contre l'indice AA.
- **Exports** (`benchmarks/quality/<c>/`, liste blanche d'AD-6, sans date, octets identiques d'une passe à l'autre) :
  - `scores/<modèle>.jsonl` (`qb.score/1` ; caractère hors `[A-Za-z0-9._-]` remplacé par `_`) ;
  - `summary.json` (`qb.report/1`) ;
  - `manifest.json` (copie du manifeste de génération ; une sélection `{ids: [...]}` y devient `{ids_count, ids_sha256}`, effectif et empreinte des `question_id` triés, pour qu'aucun identifiant de question ne sorte) ;
  - `report.md` en français et `charts/<piste>-<global|usage>.svg`.

  Aucun texte de question, sortie de modèle ni `question_id` n'y figure. Le dossier est assemblé à côté (`.<c>.tmp`), puis mis en place par renommage.
- **Fichier AA à fournir** (par Anaël, jamais récupéré en ligne) : `benchmarks/quality/references/aa-<AAAA-MM-JJ>.json`, la date du nom égale au champ `date`.

  ```json
  {
    "schema": "qb.aa_reference/1",
    "date": "2026-10-01",
    "source": "Artificial Analysis, relevé manuel du 2026-10-01",
    "entries": [
      {"tag": "qwen3.5:4b", "index": 21.5, "status": "measured", "variant": "reasoning"},
      {"tag": "qwen3.5:4b", "index": 14.0, "status": "estimated", "variant": "non_reasoning"}
    ]
  }
  ```

  `tag` = tag Ollama de la campagne ; `variant` : `reasoning` (comparé à la piste `think_on`) ou `non_reasoning` (piste `think_off`). Seuls les indices `measured` comptent, et un couple (`tag`, `variant`) n'apparaît qu'une fois. Lecture de ρ :
  - moins de 8 modèles mesurés : sans conclusion ;
  - ρ < 0 : enquête ;
  - p unilatérale < 0,05 : concordant ;
  - sinon : non significatif.

  Sans fichier, la section Spearman est marquée « indice AA absent », sans échec. Chemin et `sha256` du fichier lu sont consignés dans `summary.json`.

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

Un jeu de questions déjà construit n'est jamais modifié : un nouvel import implique un nouveau jeu.
