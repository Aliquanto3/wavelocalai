---
title: "Correcteurs déterministes, environnements d'outils et phase grade"
type: 'feature'
created: '2026-10-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_revision: 'e033e3ffc52789f3e28a7c363503f3b9209e4ca8'
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/campagne-et-reprise.md'
  - '{project-root}/scripts/quality_bench/questions/SOURCES.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Contrat des outils à un seul tour (bfcl-live, bfcl-parallel, bfcl-irrelevance, tools-fr, env nul) : rien ne dit ce que fait le runner après un appel d'outil, alors que bfcl_ast réunit tous les pas du tour 0.
    evidence: |-
      maybe-false. BFCL ne décode que la première réponse du modèle ; SOURCES.md ne décrit le contrat que pour env non nul. Si le runner (story 5) renvoie un contenu d'outil factice et que le modèle rappelle un outil, bfcl_ast compterait deux appels (« wrong count »). À trancher dans la spec de la story 5 : arrêt après la première réponse, ou correcteur limité au premier pas.
    location: >-
      scripts/quality_bench/grading/tools.py (bfcl_ast) ; scripts/quality_bench/questions/SOURCES.md (Contrat d'outils)
    severity: medium (unverified)
  - summary: >-
      conformity_error ne vérifie pas les mots-clés format (date-time, email, uri…) des schémas JSONSchemaBench : ce sont de simples annotations.
    evidence: |-
      maybe-false. Aucun FormatChecker n'est passé au validateur. Pour trancher, lire le validateur du dépôt JSONSchemaBench (epfl-dlab) et voir s'il active la vérification des formats ; si oui, l'activer ici et consigner le choix dans SOURCES.md.
    location: >-
      scripts/quality_bench/common/schemas.py (conformity_error)
    severity: medium (unverified)
  - summary: >-
      5 cibles bfcl-live défectueuses dans BFCL lui-même (aucune réponse ne peut passer) : les exclure avant de figer set-v1.
    evidence: |-
      Exécution réelle sur la tour : 1 306 cibles sur 1 311 passent comme réponse du modèle ; les 5 autres échouent aussi avec le correcteur amont (paramètre requis sans valeur possible, ou paramètre non déclaré) : live_simple_106-63-0, live_simple_112-68-0, live_multiple_507-149-4, live_multiple_862-181-3, live_multiple_964-207-0. Aucun jeu n'est encore figé.
    location: >-
      scripts/quality_bench/questions/importers/bfcl.py ou set_builder (exclusion) ; sets/set-v1.yaml
    severity: medium
  - summary: >-
      tools-fr : 3 valeurs attendues (dans 3 questions) figurent dans le prompt anglais d'origine mais plus dans la traduction (type « Californie » → CA).
    evidence: |-
      Mesure locale (comptes seulement) : 63 paramètres chaîne attendus dans les 30 traductions ; pour 3 d'entre eux, une valeur admise apparaît dans le prompt EN mais dans aucune forme du prompt FR (normalisation de BFCL). Le correcteur ne peut pas en décider : garder la valeur littérale dans la traduction, ou accepter la difficulté. À trancher à la relecture des questions privées par Anaël.
    location: >-
      $QUALITY_BENCH_DATA/private/tools-fr.yaml (hors dépôt)
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le banc sait construire un jeu (stories 2 et 3), mais rien ne note une réponse : pas de correcteur, pas d'environnement d'outils pour le multi-tours BFCL, pas de vérificateurs IFBench, M-IFEval FR ou BFCL dans le dépôt, et pas de commande qui écrive `grading.jsonl`. La génération (story 5) a besoin des `envs/` pour exécuter les appels d'outils, et les statistiques (story 6) ont besoin de `grading.jsonl`, seul porteur des scores (AD-3).

**Approach:** Ajouter le noyau pur `envs/` (environnement BFCL multi-tours, rejouable) et `grading/` : un correcteur pur `grade(question, generation, verdicts=None) -> Grade` par nom de `GRADERS`, enregistré sous `name@version`, une seule extraction de réponse (`grading/answer.py`), le code emprunté sous `vendored/<projet>/` avec `LICENSE` et `PROVENANCE.md`, puis la sous-commande `grade --campaign <c>` qui réécrit `grading.jsonl` en entier, identique octet pour octet à chaque passe. Règles AD-3, AD-10, AD-11 (et AD-2, AD-4, AD-12, AD-15, AD-16) du spine.

## Boundaries & Constraints

**Always:**
- **Correcteurs :** fonctions pures (aucune I/O, aucun réseau, aucun état global durable), une par nom de `questions/schema.GRADERS` (12), enregistrées dans `grading/registry.py` sous `name@1`. Seul `grading/answer.py` extrait la réponse finale de `output` (dernier message `assistant`, réflexion en ligne retirée) et décode le JSON (clôtures Markdown) et les appels d'outils.
- **Statuts (AD-10) :** `truncated` et `non_compliant` (JSON illisible ou hors schéma, appel d'outil mal formé, `call_cap_reached`) donnent `score = 0`, `success = false` (rédaction : `success = null`) ; `error` et `context_exceeded` donnent `score = success = null` ; rédaction sans verdict complet : `awaiting_judgment`, verdict en erreur : `error`. Aucun `except` ne change une erreur du banc en échec du modèle, ni l'inverse : une exception d'un vérificateur emprunté, un identifiant de consigne inconnu, une cible BFCL illisible ou un rejeu divergent sont des `error`.
- **Déterminisme :** recorriger le même `generation.jsonl` (et les mêmes verdicts) donne un `grading.jsonl` identique octet pour octet : lignes `qb.grading/1` canoniques triées par `key`, sans date. `langdetect.DetectorFactory.seed = 0` avant tout chargement emprunté ; le hasard global (`random`) est fixé puis restauré autour des vérificateurs de consignes ; données NLTK lues sous `$QUALITY_BENCH_DATA/nltk_data` seulement.
- **Environnements (AD-11) :** `envs/` purs et déterministes (aucune horloge, aucun fichier, aucun réseau), versionnés `name@1`. Le runner (story 5) appelle `make_env(question["env"])` puis `env.call(name, arguments)` par appel d'outil et écrit la chaîne rendue telle quelle comme `content` du message `tool` suivant, dans l'ordre des appels. Le correcteur rejoue ces appels depuis `output` sur un environnement neuf et vérifie chaque contenu `tool`.
- **Code emprunté :** sous `grading/vendored/<projet>/` (et `envs/vendored/bfcl/` pour les classes d'environnement BFCL, que `generation/` doit pouvoir importer sans `grading/`), chaque dossier avec `LICENSE` et `PROVENANCE.md` (dépôt, commit, fichiers et leur `sha256` amont, modifications, téléchargements retirés). M-IFEval : fichiers FR seulement, registre réduit, sans spaCy ; aucun `nltk.download` dans le code copié ; `MODEL_CONFIG_MAPPING` retiré d'`ast_checker` ; aucun `eval`/`exec` sur une sortie de modèle ou une cible.
- **`grade` :** sans verrou machine ni réseau ; lit `campaigns/<c>.yaml`, le manifeste et `generation.jsonl` de la campagne, le jeu `sets/<set>/` et, pour la rédaction, le seul dossier `judgment-<grading.judge>/` ; journal `campaigns/<c>/log-grade.log` sans contenu de question ni de réponse (identifiants, statuts, comptes, raisons rédigées par le banc).
- Dépendances ajoutées à `requirements.txt` par bornes inférieures vérifiées sur PyPI (2026-10-11), installées dans `.venv-quality` seulement.

**Never:**
- Écrire un score ailleurs que dans `grading.jsonl` ; modifier `generation.jsonl`, `judgment.jsonl` ou le jeu ; appeler un juge ; télécharger quoi que ce soit (ni `nltk.download`, ni jeu, ni modèle).
- Importer depuis `grading/` ou `envs/` : `judge/`, `questions/importers/`, `ollama/`, `generation/`, une bibliothèque réseau (`anthropic`, `openai`, `huggingface_hub`, `datasets`, `urllib.request`, `httpx2`) ou spaCy.
- Commiter une question privée, une réponse à une question privée, un fichier de `data/` ; mettre une question privée réelle dans un test.
- Coder le runner, le préflight ou le juge (stories 5 et 7) ; modifier `scripts/benchmark_slm.py`, `src/`, `benchmarks/results/`, `.venv`, `.venv-app`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Correction nominale | `grade --campaign c` : manifeste, `generation.jsonl`, jeu présents | une ligne `qb.grading/1` par ligne de génération, triée par `key`, comptes par statut journalisés ; code 0 | N/A |
| Deux passes | même entrée, `grade` deux fois | `grading.jsonl` identique octet pour octet | N/A |
| Statut de génération non `ok` | `truncated`, `context_exceeded`, `error` | `truncated` (0, false ; rédaction 0, null) ; les deux autres : null, null | N/A |
| Borne d'appels | `call_cap_reached = true` | `non_compliant`, 0, false | N/A |
| JSON hors schéma | extraction, sortie illisible ou non conforme | `non_compliant`, 0, false, `f1 = 0.0` si cible | N/A |
| Appel d'outil mal formé | `tool_calls` sans nom ou arguments non objet | `non_compliant` | N/A |
| Réflexion en ligne | `<think>…</think>` dans `content` | réponse = texte après la balise fermante ; `metrics.inline_thinking = 1.0` | balise ouvrante seule : texte avant elle |
| Rédaction | verdicts complets / critère manquant / verdict en erreur | `ok`, score = part de vrais / `awaiting_judgment` / `error` (score et success nuls) | pas de juge désigné ou pas de dossier : `awaiting_judgment` |
| Vérificateur en défaut | id de consigne inconnu, exception empruntée, cible BFCL illisible | `error`, raison journalisée sans contenu | jamais `non_compliant` |
| Rejeu divergent | contenu `tool` ≠ `env.call` rejoué | `error` | N/A |
| Incohérence d'entrées | question absente du jeu, `prompt_hash` différent, empreinte du jeu ≠ manifeste, ligne de génération ou de jugement d'un autre manifeste ou hors schéma | rien n'est écrit | `GradeError` journalisée, code 1 |
| Configuration | `campaigns/<c>.yaml` absent ou invalide | rien n'est écrit | `ConfigError`, code 2 |

</intent-contract>

## Code Map

- `scripts/quality_bench/questions/schema.py` -- `GRADERS` (12 noms, sans version), `SOURCES` (correcteur par source), `HASH_FIELDS`. Lecture seule ; `grading/` en importe les noms.
- `scripts/quality_bench/questions/build.py:44` -- `encode_floats` : flottants de cible encodés `{"$float": repr}` ; le correcteur décode par `float()` (cibles BFCL `live`/`parallel`). Les `grader.params` (fonctions BFCL, kwargs IFBench) gardent leurs flottants.
- Paramètres de correcteur par source (candidats réels de la story 2, fichiers privés de la story 3) :
  - `exact_answer` : `bbeh-mini` `{}` + cible chaîne (préfixe « The answer is: ») ; `var-math-fr` `{answer_prefix: "La réponse est :"}` + cible entière ;
  - `ifbench`, `mifeval_fr` : `{key, instruction_id_list, kwargs}`, cible nulle ; IFBench a 14 234 kwargs `None` (retirés comme le fait IFBench) et des flottants ; le prompt du vérificateur est le `content` du dernier message `user` de `messages` ;
  - `bfcl_ast` (`bfcl-live`, `bfcl-parallel`, `tools-fr`) : `{bfcl_id, category, functions, underscore_to_dot}`, cible = réponses possibles BFCL ; `category` ∈ `live_simple`, `live_multiple`, `live_parallel`, `live_parallel_multiple` (langage Python) ;
  - `bfcl_state` (`bfcl-multi`) : `{bfcl_id, category: multi_turn_base, excluded_function, functions, underscore_to_dot}`, `env = {name: bfcl_multi_turn, initial_state: {involved_classes, initial_config}}`, cible = appels attendus par tour, chaînes Python (1 142 appels, 40 avec arguments positionnels, aucun appel imbriqué, 3 tours vides) ;
  - `bfcl_irrelevance` : aucun appel attendu ; `json_schema` : `{schema, subset}`, cible nulle (`jsonschemabench`) ou valeurs attendues (`extraction-fr`) ; `squad_f1` (`piaf`) : cible = liste des réponses admises ;
  - `oneruler_niah` : `{variant, none_answer: "aucun"}`, cible = valeurs à 7 chiffres en chaînes, ou nulle (`oneruler-fr-none`) ; `oneruler_cwe` : `{level, common_repeats, uncommon_repeats}`, cible = 10 mots triés ;
  - `abstention_marker` : `{marker}` imposé par la consigne ; `judge_criteria` : `{}`, `criteria` `c1…`.
- `scripts/quality_bench/common/schemas.py` -- seul module `jsonschema` (`test_single_owner_of_each_library`) : ajouter `qb.grading/1` (AD-10) et `qb.judgment/1` (AD-16) au registre `SCHEMAS`, et `conformity_error(schema, instance)` (validateur de la version déclarée par `$schema`, 2020-12 par défaut, entiers JSON standard, aucune résolution distante) pour la correction d'extraction.
- `scripts/quality_bench/common/manifest.py:165` -- `blocking_hash(manifest)` : empreinte portée par `generation.manifest` et à recopier dans `generation_manifest` / `judgment_manifest`.
- `scripts/quality_bench/common/{paths,config,jsonl}.py` -- `campaign_config_path` (à appeler par l'attribut du module : les tests le redirigent), `generation_manifest_path`, `generation_path`, `grading_path`, `log_path`, `judgment_manifest_path`, `judgment_path`, `set_questions_path`, `set_tracks_path`, `nltk_data_dir` ; `load_campaign` (`grading.judge`, `set_id`) ; `read_jsonl`, `rewrite_jsonl`.
- `scripts/quality_bench/questions/schema.py:205` -- `set_hash(questions, tracks)` : à comparer à `blocking.set.hash` du manifeste.
- `scripts/quality_bench/__main__.py` -- `SUBCOMMANDS`, éditée dans ce fichier seulement (ajouter `GRADE`).
- `tests/quality_bench/test_package.py` -- `_package_modules` exclut `grading/vendored/` : y ajouter `envs/vendored/` ; propriétaires uniques à ajouter : `nltk` (aussi `grading/nlp.py`), `langdetect` (`grading/registry.py`), `mpmath` (code emprunté seulement). `conftest.py` : `REQUIRED_MODULES` += `absl`, `langdetect`, `immutabledict`, `emoji`, `syllapy`, `mpmath`, `nltk`.
- `tests/quality_bench/factories.py` -- `generation_record`, `manifest`, `question` ; `set_factories.synthetic_question`.
- `.pre-commit-config.yaml`, `pyproject.toml` -- exclusions de black, isort et ruff : étendre à `scripts/quality_bench/envs/vendored/` (et déclarer les deux dossiers dans `pyproject.toml` pour un appel direct de ruff, black et isort).
- Code amont (à récupérer sous `$TMP`, hors dépôt, puis copier) :
  - IFBench `allenai/IFBench` @ `1c40f0c10d9b5c5c2f10a175a28007ebb64f7f4d` (Apache-2.0) : `ifbench/{instructions,classic_instructions,instructions_registry,instructions_util}.py` ; à retirer : `download_nltk_resources()` et son appel, le dossier `.nltk_data` créé à l'import, `NLTK_DATA` forcé ; pas de spaCy ni de pydantic dans ces fichiers ;
  - M-IFEval `lightblue-tech/M-IFEval` @ `10b874dbf8c4ca25ed5d876e1d3226e7f3f9d0dc` (Apache-2.0, `LICENSE.txt`) : `instructions/fr_instructions.py`, `instruction_utils/fr_instructions_util.py`, `instructions_registry.py` réduit à `FR_INSTRUCTION_DICT` (préfixe `fr:`) ; à retirer : `nltk.download('punkt_tab')` à l'import ;
  - BFCL `ShishirPatil/gorilla` @ `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8` (Apache-2.0, `LICENSE` racine) : `bfcl_eval/eval_checker/ast_eval/ast_checker.py`, `type_convertor/`, `constants/{enums,type_mappings}.py`, `multi_turn_eval/multi_turn_checker.py` (exécuteur injecté au lieu d'`eval`) ; classes `multi_turn_eval/func_source_code/{gorilla_file_system,math_api,message_api,posting_api,ticket_api,trading_bot,travel_booking,vehicle_control,long_context}.py` ; sources de non-déterminisme à figer : `datetime.now()` (fichiers), `datetime.today()` (âge, `travel_booking`), `datetime.fromtimestamp` local (`trading_bot`) ; `import subprocess` inutilisé ; `math_api` importe `mpmath` ;
  - BBEH `google-deepmind/bbeh` @ `80d12ca916b7158f22293fcf3144f4d3d854d4be` (Apache-2.0) : `bbeh/evaluate.py` sans les `print` d'exemple exécutés à l'import ;
  - OneRuler `mungg/OneRuler` @ `a3fe6af862dc4b30794afc0a8f3d4f60758cecfa` (MIT) : de `OneRuler/eval/evaluate.py`, `clean_text`, `compare_numbers`, `compare_none`, `is_correct_order` et l'entrée `fr` de `none_dict`.
- NLTK sur la tour : `data/quality_bench/nltk_data` contient `punkt` (dont `french.pickle`, `english.pickle`), `punkt_tab`, `stopwords`, `averaged_perceptron_tagger_eng` ; NLTK 3.10.3 charge `nltk:tokenizers/punkt/french.pickle` (vérifié).

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/requirements.txt` -- `absl-py>=2.5.1`, `langdetect>=1.0.9`, `immutabledict>=4.3.1`, `emoji>=2.16.0`, `syllapy>=0.8.0`, `mpmath>=1.4.1` (PyPI, 2026-10-11) ; installation dans `.venv-quality`.
- [x] `scripts/quality_bench/common/schemas.py` -- `qb.grading/1` (règles croisées statut/score/success, `grader` `name@entier`, `metrics` nombres), `qb.judgment/1`, `conformity_error`.
- [x] `scripts/quality_bench/envs/` -- `__init__.py`, `base.py` (`ToolEnv` : `call(name, arguments) -> str`, `call_expression(text) -> str` pour les cibles BFCL analysées par `ast`, `instances`), `bfcl_multi_turn.py` (classes engagées et état initial, table méthode → instance comme BFCL, résultat converti comme BFCL, erreur rendue en chaîne « Error during execution: … », jamais levée), `registry.py` (`ENVS`, `make_env(spec)`), `vendored/bfcl/` (classes BFCL figées, `LICENSE`, `PROVENANCE.md`).
- [x] `scripts/quality_bench/grading/vendored/{ifbench,mifeval_fr,bfcl,bbeh,oneruler}/` -- copies avec `LICENSE` et `PROVENANCE.md`, imports rendus relatifs, modifications ci-dessus et rien d'autre.
- [x] `scripts/quality_bench/grading/answer.py` -- `final_answer(generation) -> Answer(text, inline_thinking)`, `decode_json(text)`, `tool_calls_by_turn(generation)` et `tool_steps(generation)` (`ToolCallError` si mal formé), `after_prefix(text, prefix)`, `decode_floats(value)`.
- [x] `scripts/quality_bench/grading/base.py` -- `Grade` (statut, score, success, metrics, raison non écrite) et constructeurs `passed/failed/non_compliant/bench_error/awaiting`.
- [x] `scripts/quality_bench/grading/{reasoning,instructions,tools,extraction,rag,abstention,writing}.py` et `grading/nlp.py` -- correcteurs (règles en Design Notes) ; `nlp.py` seul à configurer `nltk.data.path`.
- [x] `scripts/quality_bench/grading/registry.py` -- `DetectorFactory.seed = 0` puis `GRADERS = {nom: Registered("nom@1", fonction)}` pour les 12 noms ; `grade_line(question, generation, verdicts)` : statuts de génération, borne d'appels, `inline_thinking`, ligne `qb.grading/1` sans les champs de manifeste.
- [x] `scripts/quality_bench/grading/commands.py` et `__main__.py` -- sous-commande `grade --campaign <c>` (codes 0, 1, 2), contrôles d'intégrité de la matrice, `rewrite_jsonl`.
- [x] `tests/quality_bench/` -- `test_answer.py`, `test_graders.py` (cas à verdict connu par correcteur, sur sorties synthétiques), `test_envs.py` (rejeu et déterminisme, entrée et état synthétiques), `test_grade_command.py` (campagne synthétique : manifeste, `generation.jsonl`, `judgment.jsonl`, deux passes identiques, matrice), `test_vendored.py` (`LICENSE` et `PROVENANCE.md` présents, registre M-IFEval réduit au FR, aucun `nltk.download`, `eval`, `exec`, `spacy`, `MODEL_CONFIG_MAPPING` dans le code copié, graphe d'import de `grading/` et `envs/` hors des modules et bibliothèques interdits), ajouts à `test_schemas.py`, `test_package.py`, `conftest.py`. Une fixture fait lire les données NLTK réelles de la tour (échec explicite si `fetch-nltk` n'a pas tourné).
- [x] `scripts/quality_bench/questions/SOURCES.md` -- section « Correction » : correcteurs, code emprunté, commande `grade`, contrat d'outils de la story 5.
- [x] Exécution réelle sur la tour, hors dépôt : chaque cible des candidats `bfcl-live`, `bfcl-parallel` et `bfcl-multi` passée comme réponse du modèle donne `success = true` ; chaque question `ifbench`, `mifeval-fr` et `instructions-fr` construit ses vérificateurs sans erreur ; chaque schéma `jsonschemabench` se vérifie sans erreur ; seuls les comptes sont rapportés.

**Acceptance Criteria:**
- Given une campagne synthétique dont `generation.jsonl` couvre chaque correcteur et chaque statut, et des verdicts synthétiques, when on lance deux fois `python -m scripts.quality_bench grade --campaign <c>`, then le code est 0, chaque ligne a le statut, le score et le succès attendus, et les deux `grading.jsonl` sont identiques octet pour octet.
- Given les 12 noms de `GRADERS`, when on lit `grading/registry.py`, then chacun est enregistré sous `nom@1` et chaque ligne écrite valide `qb.grading/1`.
- Given une conversation `bfcl-multi` synthétique produite par `make_env(...).call`, when le correcteur la rejoue, then il retrouve chaque contenu `tool` et note l'état final comme BFCL ; un contenu modifié donne `error`.
- Given les dossiers `vendored/`, when `test_vendored.py` les parcourt, then chacun a `LICENSE` et `PROVENANCE.md`, M-IFEval n'expose que des identifiants `fr:`, et aucun n'appelle `nltk.download`, `eval`, `exec` ni n'importe spaCy ou `MODEL_CONFIG_MAPPING`.
- Given le scan AST de télémétrie, when on lance `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` dans `.venv-quality`, then il passe.

## Spec Change Log

## Review Triage Log

### 2026-10-11 — Review pass
- verdicts: 36 findings — high 0, medium 8, low 22, false 4, maybe-false 2
- findings:
  - `[medium]` `[patch]` (blind) Les hooks trailing-whitespace et end-of-file-fixer réécriraient 8 fichiers empruntés au commit (empreintes amont et harness_hash cassées) — exclusion `(grading|envs)/vendored/` ajoutée à ces deux hooks (detect-secrets garde le scan).
  - `[false]` `[reject]` (blind) bfcl_state n'appelle pas multi_turn_irrelevance_checker contrairement à BFCL — eval_runner.py amont importe la fonction sans jamais l'appeler ; _evaluate_single_multi_turn_entry n'appelle que multi_turn_checker.
  - `[maybe-false]` `[defer]` (blind) Outils à un seul tour : bfcl_ast réunit tous les pas du tour 0, contrat du runner non écrit — dépend du runner (story 5) ; reporté (frontmatter deferred, medium non vérifié).
  - `[maybe-false]` `[defer]` (blind) conformity_error n'impose pas `format` — dépend de la pratique de JSONSchemaBench ; reporté (frontmatter deferred, medium non vérifié).
  - `[medium]` `[patch]` (blind) Sans données NLTK, toutes les consignes passent en error et grade sort en 0 — grade refuse (code 1, rien d'écrit) si une question ifbench ou mifeval_fr est à corriger et qu'une ressource manque ; test_missing_nltk_data_is_refused.
  - `[low]` `[reject]` (blind) Entrées partielles acceptées sans le dire (génération en cours, judgment.jsonl absent) — la complétude est vérifiée par le rapport (AD-17, story 6) et les comptes par statut sont journalisés ; garde supplémentaire.
  - `[low]` `[reject]` (blind) qb.grading/1 sans règles croisées pour awaiting_judgment et judgment_manifest — grade, seul écrivain, ne produit pas ces états ; garde supplémentaire.
  - `[low]` `[patch]` (blind) use_bench_data() remplace nltk.data.path pour toujours (état global durable) — context manager nlp.bench_data() qui restaure le chemin ; test ajouté.
  - `[low]` `[reject]` (blind) Aucun test ne compare les copies empruntées aux empreintes de PROVENANCE.md — le risque concret (hooks pre-commit) est corrigé ; test supplémentaire.
  - `[medium]` `[patch]` (blind) Chemins de refus (code 1) non testés — 10 tests de refus ajoutés (clé en double, campagne, usage, phase, jeu, jugement sans manifeste, autre juge, ligne en double, question hors rédaction, critère inconnu).
  - `[low]` `[reject]` (blind) Une ligne hors schéma en sortie ferait planter grade — n'arrive que sur un bug de correcteur ; échec bruyant voulu.
  - `[false]` `[reject]` (blind) La story n'a ni cases cochées ni comptes de l'exécution réelle — cases cochées et comptes consignés à la finalisation (Auto Run Result).
  - `[low]` `[reject]` (blind) _load_set écrase un identifiant de question en double — build-set refuse les identifiants en double ; inatteignable.
  - `[low]` `[patch]` (blind) flatten donne le même chemin à {"a.b":1} et {"a":{"b":1}} — chemins en tuples ; comparaison des listes par position documentée ; assertions ajoutées.
  - `[medium]` `[patch]` (edge) bfcl_multi_turn.py : un résultat non rendable (entier de plus de 4 300 chiffres) fait lever env.call — rendu dans le try, « Error during execution: … » ; test ajouté.
  - `[low]` `[reject]` (edge) Arguments énormes (power, square_root) qui bloquent la génération — appel improbable d'un modèle ; le correctif (budget de temps, bornes) est une garde supplémentaire.
  - `[low]` `[reject]` (edge) initial_config mal typé : TypeError au lieu d'EnvError — données épinglées vérifiées (200/200) ; erreur bruyante, correcteur en error.
  - `[low]` `[patch]` (edge) decode_json laisse fuir la ValueError d'un entier de plus de 4 300 chiffres (error au lieu de non_compliant) — ValueError rattrapée ; cas de test ajouté.
  - `[low]` `[patch]` (edge) parse_integer lève sur plus de 4 300 chiffres — rend None (échec) ; cas de test ajouté.
  - `[low]` `[patch]` (edge) Marqueur d'abstention finissant par un point jamais retrouvé — strip_marker appliqué aussi au marqueur ; test ajouté.
  - `[low]` `[patch]` (edge) Réponse PIAF admise vide après normalisation (4 candidats réels) : une réponse vide compte juste — réponses vides écartées, aucune restante = error ; test ajouté.
  - `[low]` `[patch]` (edge) flatten : chemins ambigus — même correctif que la ligne blind.
  - `[low]` `[patch]` (edge) judgment_manifest posé sur des lignes de rédaction jamais jugées — seulement pour un statut de génération ok ; attente de test ajustée.
  - `[medium]` `[patch]` (edge) env.call « jamais levée » contredit par le rendu hors du try — même correctif que la ligne edge du rendu.
  - `[medium]` `[patch]` (vérification) Le test d'absence de résolution distante passe sans le registre local — urlopen surveillé (zéro appel) et NoSuchResource exigé dans la chaîne.
  - `[medium]` `[patch]` (vérification) Clé de génération en double non testée — même entrée que les refus (code 1) ci-dessus.
  - `[medium]` `[patch]` (vérification) Contrôles d'intégrité des jugements non testés — même entrée que les refus (code 1) ci-dessus.
  - `[low]` `[patch]` (vérification) decode_floats de la cible d'extraction jamais exercé — test_extraction_float_target_is_decoded.
  - `[low]` `[patch]` (intention) Pureté : nltk.data.path et mpmath laissés modifiés — nltk restauré (même entrée que use_bench_data) ; mpmath.mp.dps est fixé par chaque appel de logarithm, sans effet sur le déterminisme.
  - `[low]` `[patch]` (intention) tools.py lit output directement (tours répondus) — helper answered_turns dans answer.py.
  - `[low]` `[reject]` (intention) Déterminisme multi-machines peu exercé (TradingBot, TravelAPI, langdetect) — horloges figées et contrôlées par AST, graine vérifiée ; tests supplémentaires.
  - `[low]` `[reject]` (intention) Contrat de rejeu vérifié contre un producteur de test seulement — le runner est la story 5 ; contrat écrit dans SOURCES.md.
  - `[low]` `[reject]` (intention) Format de jugement jamais confronté à un vrai juge — le juge est la story 7 ; schéma pris tel quel d'AD-16.
  - `[low]` `[reject]` (intention) Fidélité des copies non vérifiée par test — même verdict que la ligne blind sur PROVENANCE.md.
  - `[false]` `[reject]` (intention) Arguments d'outil hors schéma de paramètres non comptés non_compliant — la spec ne range en non_compliant que l'appel mal formé ; un mauvais argument est une mauvaise réponse, comme dans BFCL.
  - `[false]` `[reject]` (intention) Aucune preuve de l'exécution réelle — comptes consignés dans l'Auto Run Result.

## Design Notes

- **Ordre des statuts :** statut de génération ≠ `ok` d'abord ; puis `call_cap_reached` → `non_compliant` ; puis le correcteur. `inline_thinking` (1.0 / 0.0) figure dans `metrics` de toute ligne corrigée depuis une sortie `ok`.
- **Règles par correcteur :**
  - `exact_answer` : cible entière → dernier « La réponse est : » (casse et espace avant « : » libres), première ligne qui suit, `*`, `$`, `\boxed{}`, espaces de milliers et point final retirés, entier signé exact ; sans préfixe : échec. Cible chaîne → `bbeh.evaluate_correctness(texte, cible)` amont.
  - `ifbench`, `mifeval_fr` : boucle « strict » amont (kwargs `None` retirés, `build_description`, prompt réinjecté si demandé, réponse vide = non suivie) ; `success` = toutes suivies ; `metrics.instructions_followed` = part suivie.
  - `bfcl_ast` : appels du tour 0 au format BFCL `[{nom: arguments}]`, cible décodée (`$float`), `ast_checker(..., Language.PYTHON, category, underscore_to_dot)`. `bfcl_irrelevance` : succès si aucun appel. `bfcl_state` : rejeu des pas (messages `assistant` avec appels) tour par tour, `multi_turn_checker` amont avec exécuteur injecté (état des instances publiques + réponses), tours manquants : `error`.
  - `json_schema` : `decode_json` puis `conformity_error` ; illisible ou non conforme → `non_compliant`. Avec cible : feuilles aplaties par chemin (chaînes NFC, espaces réduits, casse ignorée ; nombres par valeur ; booléens distincts), `success` = toutes les feuilles attendues retrouvées, `metrics.f1` sur les feuilles.
  - `squad_f1` : normalisation française (minuscules, apostrophes en espaces, ponctuation retirée, articles `le la les l un une des du d` retirés, espaces réduits) ; `success` = correspondance exacte avec une réponse admise ; `metrics.f1` = meilleur F1 de jetons.
  - `oneruler_niah` / `oneruler_cwe` : `compare_numbers` / `compare_none` / `is_correct_order` amont (langue `fr`) sur la réponse finale.
  - `abstention_marker` : réponse débarrassée des espaces, guillemets, `*`, `` ` `` et du point final, égale au marqueur sans tenir compte de la casse.
  - `judge_criteria` : `score` = part des critères jugés vrais sur tous les `criteria`, `success = null`.
- **Exécuteur BFCL sans `eval` :** un appel du modèle est `(nom, arguments)` ; une cible est analysée par `ast.parse(..., mode="eval")` (un `Call` sur un nom, arguments par `ast.literal_eval`), toute autre forme est une `error`. Les instances du modèle et de la cible sont deux environnements neufs du même `initial_state`, gardés d'un tour à l'autre comme dans BFCL.
- **Écart au spine :** les classes BFCL vont sous `envs/vendored/bfcl/` et non `grading/vendored/` : `generation/` les exécute et n'importe jamais `grading/`. Elles entrent ainsi dans `harness_hash`.
- **NLTK :** `grading/nlp.py` place `paths.nltk_data_dir()` en tête de `nltk.data.path` avant la première vérification ; une ressource absente lève, ce qui donne `error`.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pip install -r scripts/quality_bench/requirements.txt` -- expected : installation sans erreur.
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` -- expected : tout passe, sans réseau ni Ollama.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` -- expected : passe (pas de venv d'app sur la tour : le reste de `tests/unit` ne tourne pas ici).
- `uvx ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx black@25.12.0 --check scripts/quality_bench tests/quality_bench`, `uvx isort@7.0.0 --profile black --check scripts/quality_bench tests/quality_bench` -- expected : vert, code emprunté exclu.
- `git status --porcelain` -- expected : aucun chemin sous `data/`, aucune question privée.

## Auto Run Result

Status: done

**Résumé :** noyau `envs/` (environnement BFCL multi-tours `bfcl_multi_turn@1`, rejouable, sans horloge ni `eval`) et `grading/` : 12 correcteurs purs enregistrés `nom@1`, extraction unique de la réponse (`answer.py`), code emprunté (IFBench, M-IFEval FR, BFCL, BBEH, OneRuler) avec `LICENSE` et `PROVENANCE.md`, schémas `qb.grading/1` et `qb.judgment/1`, et sous-commande `grade --campaign <c>` qui réécrit `grading.jsonl`, identique octet pour octet d'une passe à l'autre.

**Fichiers modifiés :**
- `scripts/quality_bench/envs/` (`base`, `bfcl_multi_turn`, `registry`, `vendored/bfcl/`) -- contrat d'outils, classes BFCL figées.
- `scripts/quality_bench/grading/` (`answer`, `base`, `registry`, `commands`, `nlp`, `reasoning`, `instructions`, `tools`, `extraction`, `rag`, `abstention`, `writing`, `vendored/`) -- correcteurs, commande `grade`, code emprunté.
- `scripts/quality_bench/common/schemas.py`, `common/canonical.py` -- `qb.grading/1`, `qb.judgment/1`, `conformity_error` ; `plain_json` (forme BFCL des résultats d'outil).
- `scripts/quality_bench/__main__.py`, `requirements.txt`, `questions/SOURCES.md` -- sous-commande, dépendances, section « Correction » et contrat d'outils de la story 5.
- `.pre-commit-config.yaml`, `pyproject.toml`, `.secrets.baseline` -- code emprunté exclu des formateurs, linters et hooks de nettoyage ; faux mot de passe de BFCL admis.
- `tests/quality_bench/` -- `test_answer`, `test_graders`, `test_envs`, `test_grade_command`, `test_vendored`, `grading_factories` ; ajouts à `test_schemas`, `test_package`, `conftest`.

**Écarts au plan :** classes BFCL sous `envs/vendored/bfcl/` (importables par `generation/`) ; `plain_json` ajouté à `common/canonical.py` (change `harness_hash`) ; `env.call` copie les arguments en profondeur (sinon `post_tweet` partageait les listes du modèle) ; commande `grade` chargée paresseusement (CLI sans nltk) ; `nltk.data.path` restreint au seul dossier du banc puis restauré.

**Revue :** 36 constats. Patchs : 5 entrées medium (hooks pre-commit, refus sans NLTK, refus non testés, rendu d'erreur de l'environnement, absence de résolution distante) et 9 entrées low. Reportés : 2 maybe-false (frontmatter `deferred`). Rejetés : 4 false et 11 low, raisons dans le journal.

**Revue de suivi recommandée :** oui. Cinq entrées medium ont été patchées dans cette passe (patchés par verdict : medium 5, low 9). Risque non vérifié : les correctifs du refus sans données NLTK et du rendu d'erreur de `env.call` (contrat que consommera la story 5) n'ont été relus par aucune passe.

**Vérification :**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` : 758 passés, sans réseau ni Ollama.
- `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 passés. Le reste de `tests/unit` n'a pas tourné, faute de venv d'app sur la tour.
- ruff 0.14.9, black 25.12.0, isort 7.0.0 : verts, code emprunté exclu.
- Exécution réelle sur la tour, hors dépôt (comptes seulement) : `bfcl-live` 1 306/1 311 cibles passent comme réponse du modèle (5 cibles défectueuses dans BFCL, reportées) ; `bfcl-parallel` 40/40 ; `bfcl-multi` 200/200 rejouées par `envs/` ; vérificateurs construits sans erreur pour `ifbench` 300, `mifeval-fr` 235 et `instructions-fr` 30 (identifiants M-IFEval FR tous présents dans le registre réduit) ; 2 787 schémas `jsonschemabench` vérifiables.
- `git status` : aucun chemin sous `data/` ni `benchmarks/`.

**Risques résiduels :**
- Contrat d'outils à un seul tour et vérification de `format` : reportés (frontmatter `deferred`).
- 5 cibles `bfcl-live` défectueuses à exclure avant de figer `set-v1` ; 3 valeurs `tools-fr` perdues à la traduction.
- Le format `qb.judgment/1` n'a pas encore de producteur réel (story 7).
