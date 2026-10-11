---
title: "Générateurs à graine, questions privées en français et construction du jeu"
type: 'feature'
created: '2026-10-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_revision: '0d58ef0ef47102754c04fa2e8a2f478971bd53d1'
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/pistes-et-questions.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/juge-et-calibration.md'
  - '{project-root}/scripts/quality_bench/questions/SOURCES.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Le dépôt ne versionne aucune provenance du jeu : empreinte AD-4, graine, empreintes des fichiers d'entrée et commit ne vivent que dans sets/log-build-set.log, hors dépôt.
    evidence: |-
      index.jsonl ne porte que des lignes qb.set_index/1 par question ; AD-6 n'admet aucun autre fichier sous benchmarks/quality/sets/<set>/. Ajouter un manifeste de jeu en liste blanche demande d'amender AD-6 du spine (décision d'architecture) ; à défaut, le manifeste de génération (story 5) porte l'empreinte du jeu.
    location: >-
      scripts/quality_bench/questions/set_builder.py (write_set) ; spine AD-6
    severity: medium
  - summary: >-
      Story 4 : vérifier que les identifiants et les kwargs M-IFEval FR des questions instructions-fr existent dans le registre réduit copié (grading/vendored/mifeval_fr).
    evidence: |-
      house.py ne contrôle que le préfixe fr:, l'unicité et l'alignement des kwargs ; le registre n'existe pas encore. Les 30 questions réelles combinent 2 à 4 vérificateurs (1, 5 et 24 questions). Une coquille ne se verrait qu'à la correction.
    location: >-
      scripts/quality_bench/questions/house.py (_check_grader_params)
    severity: low
  - summary: >-
      87 des 418 critères de writing-fr.yaml demandent au juge de compter (mots, phrases, paragraphes, répliques), tâche où les juges LLM sont peu fiables.
    evidence: |-
      Relevé par la revue de la story 3. À trancher à la relecture d'Anaël ou à la calibration (story 9) : réécrire ces critères, les corriger de façon déterministe, ou mesurer leur accord à part.
    location: >-
      scripts/quality_bench/questions/writing/writing-fr.yaml
    severity: medium
---

<intent-contract>

## Intent

**Problem:** Le banc n'a que des candidats publics (story 2). Il lui manque les questions qui le protègent de la contamination (générateurs à graine OneRuler FR et VAR-MATH, questions privées en français hors dépôt), les 80 questions de rédaction, et la commande `build-set` qui fige un jeu reproductible : `questions.jsonl`, `tracks.json` (~800 en `think_off`, 400 en `think_on`) et l'index versionné. Sans eux, ni la génération (story 5) ni la correction (story 4) n'ont de jeu à lire.

**Approach:** Ajouter les sources maison, générées et privées à la liste fermée de `questions/schema.py`. Écrire deux générateurs purs à graine (OneRuler FR, VAR-MATH FR), un chargeur de questions maison (rédaction versionnée dans `questions/writing/`, questions privées sous `$QUALITY_BENCH_DATA/private/`), puis `questions/set_builder.py` et la sous-commande `build-set --set <s>`. Celle-ci lit `sets/<s>.yaml`, tire les questions par groupes entiers, tire `think_on` par usage et par groupes entiers, et écrit le jeu et l'index en liste blanche `qb.set_index/1`. Règles AD-4, AD-5, AD-6 (et AD-2, AD-12, AD-15) du spine.

## Boundaries & Constraints

**Always:**
- **Reproductibilité :** mêmes entrées (candidats, fichiers bruts, fichiers maison, YAML du jeu) et même graine ⇒ `questions.jsonl`, `tracks.json` et `index.jsonl` identiques octet pour octet, tirage des 400 compris. Tout aléa passe par `random.Random(int(sha256_hex([...]), 16))`, avec une graine dérivée par étape (`[seed, "sample", source]`, `[seed, "think_on", usage]`, `[generator_seed, …]`), jamais par `hash()` ni l'ordre d'un `set`.
- **Tirages par groupes entiers :** l'échantillon `think_off` d'une source et le tirage `think_on` d'un usage prennent ou laissent un `group` entier (sous réserve de `per_group`, qui plafonne le nombre de questions gardées par groupe dans l'échantillon d'une source). Les effectifs du YAML sont atteints exactement, sinon `SetBuildError`. `think_on` ⊂ `think_off`.
- **VAR-MATH :** les variantes d'un problème partagent `unit` et `group` ; dans le jeu final, une `unit` ne franchit jamais un `group` (contrôle, `SetBuildError`).
- **Rédaction :** questions versionnées en entier dans `scripts/quality_bench/questions/writing/` (non privées : le juge cloud doit les lire), avec des `criteria` en questions fermées.
- **Questions privées :** fichiers sous `$QUALITY_BENCH_DATA/private/` seulement (hors dépôt) ; `private = true`, `license = "private"`. Leur `group` et leur `unit` sont opaques (`<source>/<numéro>`, ou le groupe d'origine pour une traduction) : jamais de contenu.
- **Index :** `benchmarks/quality/sets/<set>/index.jsonl`, une ligne `qb.set_index/1` par question (champs `schema, id, usage, group, unit, source, license, private, question_hash`, plus `prompt_hash, target_hash` pour les seules questions publiques), validée contre un schéma fermé de `common/schemas.py` ; tout autre champ est une erreur.
- **`build-set` :** prend `machine.lock` ; écrit une fois et refuse si `sets/<set>/` (données) ou `benchmarks/quality/sets/<set>/` existe déjà ; n'écrit rien en cas d'échec ; aucun accès réseau (les fichiers bruts sont seulement vérifiés). Contrôle de palier d'AD-5 refait sur chaque question.
- **Journaux :** jamais de contenu d'une question privée (identifiants, comptes et empreintes seulement).

**Never:**
- Commiter une question privée, un extrait de question privée, un fichier de `$QUALITY_BENCH_DATA` ou un échantillon de relecture ; mettre une question privée réelle dans un test ou un échantillon de `tests/`.
- Télécharger hors de la commande `fetch` (sous `machine.lock`) ; télécharger le vocabulaire ou les dictionnaires de OneRuler (licence non déclarée) ; utiliser `stanza`.
- Évaluer une expression VAR-MATH par `eval`/`exec` : seul un évaluateur AST restreint (entiers) est permis.
- Coder les correcteurs (story 4) ou le runner (story 5) ; modifier `scripts/benchmark_slm.py`, `src/`, `benchmarks/results/`, `.venv`, `.venv-app`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Construction nominale | `build-set --set <s>`, sources présentes | `sets/<s>/questions.jsonl` (trié par `id`), `tracks.json`, `benchmarks/quality/sets/<s>/index.jsonl` ; empreinte du jeu journalisée ; code 0 | N/A |
| Même graine, deux constructions | deux racines vides, mêmes entrées | trois fichiers identiques octet pour octet, `think_on` compris | N/A |
| Autre graine de jeu | `seed` différent | autre échantillon et autre `think_on`, toujours par groupes entiers | N/A |
| Jeu déjà construit | dossier de données ou d'index présent | rien n'est écrit | `SetBuildError`, code 1 |
| Machine occupée | `machine.lock` détenu | rien n'est écrit | `LockBusyError` journalisé, code 1 |
| Source absente | candidats manquants, fichier privé absent | rien n'est écrit ; le message nomme le fichier attendu et la commande `fetch` à lancer s'il y a lieu | `SetBuildError`, code 1 |
| Fichier brut altéré ou absent | fichier OneRuler d'empreinte inattendue | rien n'est écrit, rien n'est téléchargé | `SourceIntegrityError`, code 1 |
| Effectif inatteignable | pas assez de groupes, ou aucune combinaison de groupes entiers n'atteint l'effectif exact | rien n'est écrit, la source ou l'usage est nommé | `SetBuildError`, code 1 |
| `unit` à cheval sur deux `group` | questions d'une même `unit` dans deux groupes | rien n'est écrit | `SetBuildError` |
| Palier insuffisant | `num_ctx < est × 1,25 + plafond maximal` ou hors des paliers | rien n'est écrit | `SetBuildError` |
| YAML de jeu invalide | clé inconnue, `set` ≠ nom du fichier, `think_on` hors bornes, source refusée ou inconnue | rien n'est écrit | `ConfigError`, code 2 |
| Fichier maison invalide | clé inconnue, `criteria` absent en rédaction, `derived_from` introuvable | refus | `QuestionError` |
| VAR-MATH non instanciable | contraintes jamais satisfaites en N essais, réponse non entière, variantes non distinctes | refus nommant le problème | `GeneratorError` |
| Expression VAR-MATH dangereuse | `__import__('os')`, attribut, appel hors `min`, `max`, `abs` | refus | `GeneratorError` |
| Échantillon de relecture | `review-sample --set <s>` | Markdown sous `$QUALITY_BENCH_DATA/review/`, hors dépôt | N/A |

</intent-contract>

## Code Map

- `scripts/quality_bench/questions/schema.py` -- `SourceSpec`, `SOURCES`, `GRADERS`, `LICENSES`, `validate_question` (vérifie usage, licence, `private` et correcteur de la source), `with_hashes`. Ajouter les sources et correcteurs ci-dessous ; ajouter `set_hash(questions, tracks)` (AD-4 : empreinte de `{questions: [[id, question_hash] triés par id], tracks}`).
- `scripts/quality_bench/questions/importers/base.py` -- `build_question`, `build_questions`, `choose_num_ctx`, `max_cap`, `estimate_prompt_tokens`, `encode_floats`, `question_id`. Il importe `remote.py`, donc `huggingface_hub` : déplacer ces fonctions dans un module sans réseau `questions/build.py` (ajouter les paramètres `criteria`, `generator`, `generator_seed`) et les réexporter depuis `base.py` (API et tests de la story 2 inchangés).
- `scripts/quality_bench/questions/importers/remote.py` -- `RemoteFile`, `file_sha256`, `fetch_files`. Déplacer `RemoteFile` et `file_sha256` dans `questions/pinned.py` (sans réseau), avec une nouvelle `verify_local_files(files, raw_dir) -> dict[RemoteFile, Path]` qui ne télécharge jamais (absent ou empreinte inattendue : `SourceIntegrityError` qui dit de lancer `fetch`) ; réexporter depuis `remote.py`.
- `scripts/quality_bench/questions/importers/commands.py` -- `importable_slugs`, `load_importer`, `fetch_source`, `_run_fetch`. Ajouter les lots bruts des générateurs (`RAW_BUNDLES = {"oneruler-fr": …}`) : `fetch --source oneruler-fr` et `fetch --all` les téléchargent sous `sources/oneruler-fr/raw/`, sans candidats. `importable_slugs()` reste inchangé (test de la story 2).
- `scripts/quality_bench/common/config.py` -- seul lecteur de YAML (`read_yaml`, `_UniqueKeyLoader`), `DEFAULT_GENERATION` (`caps`, `num_ctx_tiers`), `ConfigError`. Ajouter `load_set(path) -> SetConfig`. Le chargeur maison lit ses YAML par `read_yaml`.
- `scripts/quality_bench/common/paths.py` -- ajouter `set_config_path` (`PACKAGE_DIR/sets/<s>.yaml`), `set_dir`, `set_questions_path`, `set_tracks_path`, `sets_log_path`, `exports_root` (`$QUALITY_BENCH_EXPORTS`, défaut `<dépôt>/benchmarks/quality`), `set_index_dir`, `set_index_path`, `private_dir`, `private_source_path(slug)` (`private/<slug>.yaml`), `review_dir`.
- `scripts/quality_bench/common/schemas.py` -- seul module `jsonschema` ; ajouter `qb.set_index/1` au registre de `validate` (fermé ; `prompt_hash` et `target_hash` obligatoires si `private` est faux, interdits sinon).
- `scripts/quality_bench/common/jsonl.py` -- `rewrite_jsonl` (questions, index), `read_complete_jsonl` ; `canonical.pretty_bytes` pour `tracks.json`.
- `scripts/quality_bench/__main__.py` -- `SUBCOMMANDS`, éditée dans ce fichier seulement.
- `tests/quality_bench/conftest.py` -- fixture `autouse` : ajouter `QUALITY_BENCH_EXPORTS` sur `tmp_path`. `tests/quality_bench/test_package.py` : propriétaires uniques (aucune nouvelle bibliothèque réseau hors `importers/`).
- Candidats réels (`$QUALITY_BENCH_DATA/sources/<slug>/candidates.jsonl`, story 2) : groupes d'une question, sauf `piaf` (761 passages de 5 questions ou plus) et 2 groupes de `jsonschemabench`. Paramètres de correcteur à reprendre : `mifeval_fr` → `{instruction_id_list, key, kwargs}` ; `bfcl_ast` → `{bfcl_id, category, functions, underscore_to_dot}`, `target` liste ; `json_schema` → `{schema, subset}`, `target` nul.
- OneRuler : `mungg/OneRuler` @ `a3fe6af862dc4b30794afc0a8f3d4f60758cecfa` -- `LICENSE`, `data/books/fr/les_miserables_fr.txt`, `data/prompt/fr/niah.txt`, `data/prompt/fr/cwe.txt`. Empreintes inconnues à ce jour : les relever par un premier `fetch` (le message de `SourceIntegrityError` donne l'empreinte reçue), les vérifier, puis les épingler. Lire `LICENSE` et les gabarits avant d'écrire le générateur. Pas de `data/vocab/` (licence non déclarée).
- `$QUALITY_BENCH_DATA` n'est pas défini sur la tour : racine par défaut `data/quality_bench/`.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/questions/build.py`, `pinned.py` ; `importers/base.py`, `importers/remote.py` -- déplacements et réexports décrits au Code Map -- générateurs et chargeur maison sans import réseau.
- [x] `scripts/quality_bench/questions/schema.py` -- sources (slug, usage, licence, producteur, correcteur, privé) : `var-math-fr` (reasoning, private, `generators/var_math.py`, `exact_answer`) ; `oneruler-fr-niah` et `oneruler-fr-cwe` (rag, MIT, `generators/oneruler_fr.py`, `oneruler_niah` et `oneruler_cwe`) ; `oneruler-fr-none` (abstention, MIT, même producteur, `oneruler_niah`, cible sans valeur) ; `instructions-fr` (instructions, private, `questions/house.py`, `mifeval_fr`) ; `tools-fr` (tools, private, `house.py`, `bfcl_ast`) ; `extraction-fr` (extraction, private, `house.py`, `json_schema`) ; `abstention-fr` (abstention, private, `house.py`, `abstention_marker`) ; `writing-fr` (writing, MIT, `house.py`, `judge_criteria`). Correcteurs ajoutés à `GRADERS` avec leur commentaire ; `set_hash`.
- [x] `scripts/quality_bench/questions/generators/oneruler_fr.py` -- `RAW_FILES` épinglés ; fonctions pures `generate_niah(texts, seed, count)`, `generate_cwe(...)`, `generate_none(...)` selon la recette OneRuler et les gabarits FR téléchargés : botte de foin = extrait contigu du livre (début tiré), aiguilles insérées à des profondeurs tirées, clés tirées du vocabulaire du livre (mots alphabétiques de 4 lettres ou plus, dédupliqués, triés puis tirés), valeurs à 7 chiffres en chaînes ; variantes `single`, `multikey` (distracteurs), `multivalue` pour `niah`, deux niveaux de fréquence pour `cwe` (10 mots attendus), clé absente pour `none`. Taille remplie au plus près du palier visé (8192, 16384, 32768, répartis à parts égales) sans le dépasser par la règle d'AD-5. Une question par groupe ; `generator = "oneruler_fr@1"`.
- [x] `scripts/quality_bench/questions/generators/var_math.py` -- fichier privé `private/var-math-fr.yaml` (`schema: qb.var_math/1`, `problems: [{number, text, params: {nom: {min, max, step?}}, derived?, constraints, answer}]`) ; évaluateur AST restreint (entiers, `+ - * // % **` à exposant borné, comparaisons, `and/or/not`, `min/max/abs`) ; `generate(problems, seed, variants)` : variantes distinctes par tirage avec rejet borné, `group = unit = reasoning/var-math-fr/p<numéro>`, cible entière, consigne de fin « La réponse est : <entier> » et `grader.params = {"answer_prefix": "La réponse est :"}` ; `generator = "var_math_fr@1"`.
- [x] `scripts/quality_bench/questions/house.py` -- `load_house(path, source)` pour `schema: qb.house/1` (`source`, `questions: [{number, group?, messages, turns?, tools?, format?, grader_params, target, criteria?, derived_from?}]`, clés inconnues refusées) ; `derived_from` (seulement `tools-fr`) copie `tools`, `format`, `env`, `grader.params`, `target` et `group` du candidat d'origine et ne remplace que `messages` ; questions bâties par `build_question`.
- [x] `scripts/quality_bench/questions/writing/writing-fr.yaml` -- 80 questions de rédaction en français (consigne complète, genres variés : courriel, synthèse, reformulation, changement de registre, argumentation, contraintes de longueur ou de structure), 4 à 6 critères fermés chacun (`c1`…, phrase interrogative à réponse oui/non, vérifiable sur la seule réponse), un groupe par question.
- [x] Fichiers privés sous `$QUALITY_BENCH_DATA/private/` (jamais dans le dépôt) -- `var-math-fr.yaml` (au moins 20 problèmes de collège-lycée à plusieurs étapes), `instructions-fr.yaml` (30 consignes FR qui combinent 2 à 4 vérificateurs M-IFEval FR existants), `tools-fr.yaml` (30 traductions FR de candidats `bfcl-live` à 4096, `derived_from`), `extraction-fr.yaml` (30 documents FR inventés, schéma JSON dans le prompt, `target` = valeurs attendues), `abstention-fr.yaml` (30 documents FR inventés et questions sans réponse dans le document, marqueur d'abstention imposé dans la consigne et dans `grader_params.marker`). Contenu inventé, sans données personnelles réelles ni texte protégé recopié, difficile pour des modèles de 1 à 14 milliards de paramètres.
- [x] `scripts/quality_bench/common/config.py` -- `load_set` : clés `set` (= nom du fichier), `seed`, `sources: [{source, count, per_group?, generator_seed?, generator_params?}]` (`generator_seed` obligatoire pour une source générée, interdit sinon ; source dans `SOURCES`), `think_on: {<usage>: effectif}` (chaque effectif ≤ effectif `think_off` de l'usage) ; clés inconnues refusées.
- [x] `scripts/quality_bench/sets/set-v1.yaml` -- 800 / 400 : reasoning `var-math-fr` 60 + `bbeh-mini` 70 ; instructions `instructions-fr` 30 + `mifeval-fr` 50 + `ifbench` 50 ; tools `tools-fr` 30 + `bfcl-multi` 30 + `bfcl-parallel` 20 + `bfcl-live` 50 ; extraction `extraction-fr` 30 + `jsonschemabench` 80 ; rag `oneruler-fr-niah` 36 + `oneruler-fr-cwe` 24 + `piaf` 50 (`per_group: 1`) ; abstention `oneruler-fr-none` 30 + `abstention-fr` 30 + `bfcl-irrelevance` 50 ; writing `writing-fr` 80. `think_on` : 65, 65, 65, 55, 55, 55, 40.
- [x] `scripts/quality_bench/questions/set_builder.py` -- cœur pur `assemble(config, candidates_by_source) -> (questions, tracks)` : sources dans l'ordre du YAML ; un groupe déjà pris par une source précédente est exclu des suivantes (traductions) ; échantillon par groupes entiers ; contrôles (effectifs, `unit`/`group`, palier, `validate_question`, identifiants uniques) ; tirage `think_on`. Coquille `build_set(set_id)` : charge les candidats (story 2), génère, lit les fichiers maison, vérifie les fichiers bruts (`verify_local_files`), écrit dans des dossiers temporaires voisins puis les renomme, journalise l'empreinte de chaque fichier privé lu et l'empreinte du jeu.
- [x] `scripts/quality_bench/questions/review.py` et commandes -- `build-set --set <s>` (sous `machine.lock`, journal `sets/log-build-set.log`, codes 0, 1, 2) et `review-sample --set <s> [--per-source 5] [--writing 10]` (sans verrou, lecture seule ; écrit `review/private-sample.md` et `review/writing-sample.md` : id, groupe, messages, tours, outils, cible, critères), ajoutées à `SUBCOMMANDS`.
- [x] `scripts/quality_bench/questions/SOURCES.md` -- nouvelles sources et licences, lot `oneruler-fr`, formats `qb.house/1` et `qb.var_math/1`, emplacement et sauvegarde des fichiers privés (hors dépôt), commandes `build-set` et `review-sample`.
- [x] `tests/quality_bench/` -- `test_generators.py`, `test_house.py`, `test_set_builder.py`, `test_exports.py`, ajouts à `test_downloads.py`, `test_question_schema.py`, `test_config.py`, `test_paths.py`, `conftest.py`. Couvrir la matrice. Entrées synthétiques seulement (aucune question privée réelle) ; `writing-fr.yaml` réel testé (80 questions valides, 4 à 6 critères).
- [x] Exécution réelle sur la tour : `fetch --source oneruler-fr` (empreintes épinglées), écriture des fichiers privés, `build-set --set set-v1` deux fois (empreintes des trois fichiers identiques entre les deux), puis suppression de `data/quality_bench/sets/set-v1/` et de `benchmarks/quality/sets/set-v1/` (le jeu se fige après la relecture d'Anaël), puis `review-sample --set set-v1`.

**Acceptance Criteria:**
- Given `set-v1.yaml` et des candidats synthétiques de même composition, when `assemble` tourne deux fois avec la même graine, then les questions, `tracks.json` et l'index sont identiques, avec 800 questions en `think_off`, 400 en `think_on` et les effectifs par usage du YAML ; avec une autre graine, `think_on` diffère.
- Given le jeu assemblé, when on regroupe ses questions, then chaque `group` est soit entièrement dans `think_on`, soit entièrement hors de `think_on`, et chaque `unit` VAR-MATH porte ses 3 variantes dans un seul `group`.
- Given un index écrit, when `tests/quality_bench/test_exports.py` parcourt `benchmarks/quality/` (et un index synthétique), then chaque ligne valide `qb.set_index/1`, aucune ligne privée ne porte `prompt_hash` ni `target_hash`, et un fichier ou un champ hors liste blanche fait échouer le test.
- Given la tour, when on lance deux fois `build-set --set set-v1`, then les trois fichiers ont les mêmes empreintes, et `git status` ne montre aucun fichier de `data/` ni de question privée.
- Given `review-sample --set set-v1`, then `$QUALITY_BENCH_DATA/review/private-sample.md` et `writing-sample.md` existent hors dépôt.

## Spec Change Log

## Review Triage Log

### 2026-10-11 — Review pass
- verdicts: 44 findings — high 0, medium 6, low 32, false 6, maybe-false 0
- findings:
  - `[low]` `[reject]` (intent) Pas de test d'écriture à pleine échelle (800/400) par write_set — le cœur assemble est testé à 800/400 et l'écriture sur un petit jeu ; le double build-set réel de set-v1 donne les mêmes empreintes (0cbfb054…, 483d4417…, 75af7102…).
  - `[false]` `[reject]` (intent) set_hash jamais comparé entre deux constructions — fonction pure de questions et tracks, identiques octet pour octet entre deux constructions (testé et mesuré).
  - `[low]` `[reject]` (intent) Refus d'une unit à cheval testé sur bbeh-mini, pas VAR-MATH — contrôle générique ; VAR-MATH tient par construction (group = unit), testé à 20 unités de 3.
  - `[low]` `[reject]` (intent) test_versioned_exports passe à vide (aucun index versionné) — voulu : le jeu se fige après relecture ; la liste blanche est exercée sur des index synthétiques.
  - `[false]` `[reject]` (intent) Aucun contrôle de l'état git — fait à la main : git status ne montre ni data/, ni review/, ni benchmarks/.
  - `[false]` `[reject]` (intent) Pause de relecture invisible dans le diff — gérée par l'orchestrateur ; échantillons produits par review-sample.
  - `[low]` `[patch]` (vérification) Graine et variants du YAML jamais vérifiés jusqu'aux questions — test ajouté (generator_seed égal au YAML ; variants: 2 donne 2 questions par unit).
  - `[low]` `[patch]` (vérification) Cible multikey jamais comparée à la clé demandée — assertion ajoutée (valeur dans l'aiguille de la clé demandée).
  - `[low]` `[patch]` (vérification) Retour arrière de write_set non testé — test ajouté (second os.rename en échec : aucun dossier ni .tmp restant).
  - `[low]` `[patch]` (vérification) Division par zéro VAR-MATH non testée — test ajouté sur 20 graines, cibles recalculées.
  - `[low]` `[patch]` (vérification) Contrôles d'origine de derived_from non testés — trois cas ajoutés (autre usage, origine privée, autre correcteur).
  - `[medium]` `[patch]` (vérification) Contenu privé possible dans les journaux et les erreurs — messages réduits au chemin et au mot-clé (redacted, instance_errors), schéma jamais recopié, review-sample sans pile ; tests ajoutés.
  - `[low]` `[patch]` (vérification) variants mal typé sort en code 1 au lieu de 2 — variants validé (entier ≥ 1) en ConfigError.
  - `[medium]` `[patch]` (blind) Fuite de contenu privé dans les journaux — même entrée que la ligne de vérification.
  - `[low]` `[patch]` (blind) load_set : source non hachable, TypeError — contrôle de type avant la liste des refus ; test.
  - `[low]` `[patch]` (blind) _derived lit messages avant validation — _messages() d'abord ; test.
  - `[low]` `[patch]` (blind) Tirage glouton présenté comme recherche exacte — message reformulé (le tirage glouton à graine n'atteint pas l'effectif).
  - `[low]` `[patch]` (blind) review-sample reconstruit au lieu de lire le jeu figé ; docstring qui nie le journal sous sets/ — reconstruction voulue (relecture avant figement), non changée ; docstring et SOURCES.md corrigés.
  - `[medium]` `[defer]` (blind) Aucune provenance de jeu versionnée — demande d'amender AD-6 ; reporté (frontmatter deferred).
  - `[low]` `[defer]` (blind) Identifiants M-IFEval FR non vérifiés contre le registre — registre à la story 4 ; reporté. Comptes réels de 2 à 4 vérifiés.
  - `[medium]` `[defer]` (blind) Critères de rédaction qui demandent de compter — décision de contenu (relecture, calibration) ; reporté.
  - `[low]` `[patch]` (blind) Paliers OneRuler nominaux — SOURCES.md le précise.
  - `[false]` `[reject]` (blind) Story en revue avec cases non cochées et journal de changement vide — cases cochées à la finalisation ; le journal ne sert qu'aux reprises bad_spec ; écarts consignés au résultat.
  - `[low]` `[reject]` (blind) Règle tools-fr « à 4096 » non imposée, .tmp d'index laissé après un crash — vérifié : les 30 traductions réelles sont à 4096 ; crash entre deux renommages improbable, garde supplémentaire ; test de retour arrière ajouté (ligne de vérification).
  - `[low]` `[patch]` (blind) _private_file dit de restaurer writing-fr depuis une sauvegarde — message distinct pour un fichier versionné.
  - `[low]` `[reject]` (blind) GeneratorError défini dans var_math.py — couplage cosmétique, aucun dommage nommé.
  - `[low]` `[patch]` (blind) Ligne de docstring de 150 caractères dans commands.py — rewrappée.
  - `[low]` `[patch]` (edge) config.py:328 source non hachable — même correctif que la ligne blind.
  - `[low]` `[patch]` (edge) YAMLError non rattrapé : trace et code 1 — read_yaml lève ConfigError (ligne, colonne, sans extrait) ; test.
  - `[low]` `[patch]` (edge) generator_params falsy accepté — `{} if params is None` ; test.
  - `[low]` `[patch]` (edge) think_on non entier pour un usage absent — _int appliqué ; test.
  - `[low]` `[patch]` (edge) variants invalide : code 1 — même correctif que la ligne de vérification ; test.
  - `[low]` `[patch]` (edge) Clé en double d'un fichier privé journalisée comme « YAML de jeu invalide », code 2 — relevée en SetBuildError qui nomme le fichier, code 1 ; test.
  - `[medium]` `[patch]` (edge) Message QuestionError journalisé avec des valeurs privées — même entrée que la fuite de contenu.
  - `[medium]` `[patch]` (edge) house.py:137 cible d'extraction citée dans l'erreur — même entrée.
  - `[low]` `[patch]` (edge) Messages dérivés non validés : TypeError — même correctif que la ligne blind.
  - `[low]` `[reject]` (edge) Deux traductions du même derived_from — vérifié : 30 groupes distincts dans le fichier réel ; garde supplémentaire.
  - `[low]` `[reject]` (edge) Arité de min, max, abs non vérifiée — erreur bruyante, fichier rédigé à la main ; garde supplémentaire.
  - `[low]` `[reject]` (edge) Plage de paramètre immense — improbable dans un fichier rédigé à la main ; garde supplémentaire.
  - `[low]` `[reject]` (edge) Processus tué entre les deux renommages — fenêtre de quelques millisecondes ; garde supplémentaire.
  - `[low]` `[reject]` (edge) rmtree en échec qui masque l'erreur — improbable ; garde supplémentaire.
  - `[low]` `[patch]` (edge) Docstring de review.py qui nie le journal sous sets/ — même correctif que la ligne blind.
  - `[false]` `[reject]` (edge) Codes de sortie annoncés non tenus pour un YAML illisible — couvert par le correctif YAMLError ci-dessus.
  - `[false]` `[reject]` (edge) Journal annoncé sans contenu privé — couvert par le correctif de fuite ci-dessus.

## Design Notes

- **Générateurs en mémoire :** `build-set` appelle les générateurs, purs, plutôt que de lire des `sources/<slug>/candidates.jsonl` qu'ils auraient écrits (AD-2 permet ces fichiers sans les imposer). Seuls les fichiers bruts de OneRuler passent par `fetch`.
- **Licence OneRuler :** gabarits du dépôt MIT, livre du domaine public : `license = "MIT"`. Clés et mots de CWE pris dans le livre, pas dans `data/vocab/` (licence non déclarée).
- **Traductions :** `tools-fr` garde le groupe de son origine (AD-5) et vient avant `bfcl-live` dans le YAML : le groupe pris par la traduction est exclu de l'échantillon anglais, sans doublon.
- **Algorithme de tirage :** groupes triés par identifiant, mélangés par le générateur dérivé, puis ajoutés tant que le total reste ≤ effectif ; un groupe qui dépasse est sauté et le parcours continue. Total ≠ effectif à la fin : `SetBuildError`.
  ```text
  rng = Random(int(sha256_hex([seed, "think_on", usage]), 16))
  groups = sorted(groups_of(usage)); rng.shuffle(groups)
  for g in groups: if total + size(g) <= target: take(g)
  ```
- **Contexte multi-tours (`bfcl-multi`) :** la règle d'AD-5 reste celle du spine (report de la story 2, mesuré au pilote).

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` -- expected : tout passe, sans réseau.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` -- expected : passe (pas de venv d'app sur la tour : le reste de `tests/unit` ne tourne pas ici).
- `uvx ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx black@25.12.0 --check scripts/quality_bench tests/quality_bench`, `uvx isort@7.0.0 --profile black --check scripts/quality_bench tests/quality_bench` -- expected : vert.
- `.venv-quality\Scripts\python -m scripts.quality_bench fetch --source oneruler-fr` puis `build-set --set set-v1` (deux fois, sorties supprimées entre les deux) puis `review-sample --set set-v1` -- expected : code 0, empreintes identiques.
- `git status --porcelain` et `git diff --stat` -- expected : aucun chemin sous `data/`, aucun `review/`, aucun fichier privé.

## Auto Run Result

Status: done

**Résumé :** 9 sources ajoutées à la liste fermée (générées, maison, privées). Deux générateurs purs à graine : OneRuler FR (NIAH, CWE et variante sans aiguille, sur *Les Misérables*, gabarits FR épinglés) et VAR-MATH FR (évaluateur AST restreint, 3 variantes par problème dans une même `unit` et un même `group`). Chargeur `qb.house/1` des questions maison : 80 questions de rédaction versionnées et 5 fichiers privés sous `$QUALITY_BENCH_DATA/private/` (24 problèmes VAR-MATH, 30 questions chacun pour les consignes, les outils, l'extraction et l'abstention). Commande `build-set` : 800 questions en `think_off` et 400 en `think_on`, tirées par groupes entiers et stratifiées par usage, avec un index `qb.set_index/1` en liste blanche. Commande `review-sample` pour la relecture.

**Fichiers modifiés :**
- `scripts/quality_bench/questions/{build,pinned,house,set_builder,review}.py` -- construction sans réseau, vérification des fichiers bruts, questions maison, jeu, relecture.
- `scripts/quality_bench/questions/generators/{oneruler_fr,var_math}.py` -- générateurs à graine.
- `scripts/quality_bench/questions/{schema.py,SOURCES.md}` -- sources, correcteurs, `set_hash`, `redacted`, documentation.
- `scripts/quality_bench/questions/importers/{base,remote,commands}.py` -- réexports, lot `oneruler-fr` de `fetch`.
- `scripts/quality_bench/common/{config,paths,schemas}.py` -- `load_set`, chemins, `qb.set_index/1`, messages sans valeur.
- `scripts/quality_bench/questions/writing/writing-fr.yaml`, `scripts/quality_bench/sets/set-v1.yaml`, `scripts/quality_bench/__main__.py`.
- `tests/quality_bench/` -- nouveaux `test_generators`, `test_house`, `test_set_builder`, `test_exports` et `set_factories`, ajouts aux tests existants.

**Écarts au plan :**
- Les fichiers OneRuler sont en réalité sous `OneRuler/data/…`.
- La signature est `load_set(path, sources, refused)`, car `common/` n'importe pas `questions/`.
- `derived_from` copie aussi `turns`.
- La variante `none` a 4 aiguilles distractrices.

**Revue :** 44 constats. Patchs appliqués : 4 constats medium regroupés en une seule entrée (fuite de contenu privé), plus 17 entrées low. Reportés : 3 constats (frontmatter `deferred` et `deferred-work.md`). Rejetés : 6 false et 10 low, avec leurs raisons dans le journal ci-dessus.

**Revue de suivi recommandée :** non. Une seule entrée medium a été patchée, et aucune high. Patchés par verdict : medium 1, low 17.

**Vérification :**
- `tests/quality_bench` : 501 tests passés, sans réseau.
- `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 tests passés. Le reste de `tests/unit` n'a pas tourné, faute de venv d'app sur la tour.
- ruff 0.14.9, black 25.12.0 et isort 7.0.0 : verts.
- `fetch --source oneruler-fr` : code 0, 4 fichiers vérifiés.
- `build-set --set set-v1` lancé deux fois, avant puis après les correctifs, avec suppression des sorties entre deux lancements : 800/400, empreintes identiques (`questions.jsonl` 0cbfb054…, `tracks.json` 483d4417…, `index.jsonl` 75af7102…).
- Les sorties de `set-v1` sont supprimées : le jeu se fige après la relecture d'Anaël.
- `review-sample --set set-v1` : `data/quality_bench/review/private-sample.md` et `data/quality_bench/review/writing-sample.md`.
- `git status` : aucun chemin sous `data/`, `review/` ni `benchmarks/`.

**Risques résiduels :**
- Tout le contenu (rédaction et questions privées) a été rédigé par des agents : une relecture humaine est requise avant le `build-set` définitif.
- Les fichiers privés n'existent que sur la tour : il faut les sauvegarder hors de la machine.
- Quelques traductions `tools-fr` demandent la même correspondance de valeurs que leur original (« Californie » → CA) : à confirmer avec le correcteur (story 4).
- Contexte multi-tours de `bfcl-multi` : report de la story 2, inchangé.
