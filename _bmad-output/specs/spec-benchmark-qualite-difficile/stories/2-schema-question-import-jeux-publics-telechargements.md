---
title: "Schéma de question, import des jeux publics et téléchargements d'avant campagne"
type: 'feature'
created: '2026-10-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_revision: '8c42d53199abb2a1da7aa84940562447d234b67b'
followup_review_recommended: false
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/pistes-et-questions.md'
warnings: []
deferred:
  - summary: >-
      Contexte des questions multi-tours (bfcl-multi) : la règle d'AD-5 n'ajoute qu'un plafond de réponse au prompt estimé, sans l'historique des tours (réponses du modèle, retours d'outils).
    evidence: |-
      base.choose_num_ctx applique num_ctx ≥ est × 1,25 + plafond ; 89 conversations de bfcl-multi tombent à 8192 et 111 à 16384 alors qu'elles comptent jusqu'à 7 tours. Le runner (AD-7) écrira context_exceeded plutôt que de tronquer, mais une part notable de bfcl-multi risque de sortir des comparaisons. Règle propre au multi-tours à trancher dans le spine (AD-5), puis appliquée par set_builder (story 3) ou mesurée au pilote.
    location: >-
      scripts/quality_bench/questions/importers/base.py (choose_num_ctx)
    severity: medium
  - summary: >-
      Lancer python -m pytest tests/unit en entier (4 échecs préexistants attendus) sur une machine dotée d'un venv d'app.
    evidence: |-
      La tour n'a pas de venv d'app : seuls tests/quality_bench et tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import" ont tourné dans .venv-quality (8 passés). La modification de tests/unit/test_telemetry.py (datasets dans TELEMETRY_ROOTS, remote.py dans TELEMETRY_IMPORTERS) reste à confirmer sur la suite complète.
    location: >-
      tests/unit/test_telemetry.py
    severity: low
  - summary: >-
      Story 3 : télécharger avant campagne les fichiers bruts de OneRuler FR (livre, vocabulaire, gabarits) par le même mécanisme épinglé (RemoteFile, empreintes), sous machine.lock.
    evidence: |-
      mungg/OneRuler @ a3fe6af862dc4b30794afc0a8f3d4f60758cecfa : data/books/fr/les_miserables_fr.txt, data/prompt/fr/{niah,cwe}.txt, data/vocab/100_noun_list_translated.tsv, data/vocab/dictionaries/French/French.csv. Code MIT ; aucune licence ni provenance déclarée pour le texte et les dictionnaires ; niah.py appelle stanza.download (réseau). Non importé à la story 2, qui ne couvre que les jeux publics prêts à convertir.
    location: >-
      scripts/quality_bench/questions/ (générateur OneRuler, story 3)
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le banc n'a ni schéma de question, ni jeux publics importés, ni données NLTK. La story 3 (construction du jeu) et la story 4 (correcteurs IFBench et M-IFEval) ne peuvent pas démarrer, et rien ne garantit qu'un jeu refusé (licence, saturation, contamination) ou qu'une source modifiée en amont n'entre pas dans le jeu.

**Approach:** Définir `qb.question/1` (AD-5) dans `questions/schema.py`, avec la liste fermée des sources et la liste des sources refusées. Écrire un importeur par jeu public retenu dans `pistes-et-questions.md`. Chaque importeur télécharge ses fichiers bruts à une révision épinglée, vérifie leur empreinte `sha256`, puis les convertit en questions candidates validées. Ajouter deux sous-commandes d'avant campagne, `fetch` et `fetch-nltk`, sous `machine.lock` (AD-12, AD-15).

## Boundaries & Constraints

**Always:**
- **Données :** sous `$QUALITY_BENCH_DATA`, hors dépôt :
  - `sources/<slug>/raw/` et `sources/<slug>/candidates.jsonl` (réécrit par son seul importeur, AD-2) ;
  - `nltk_data/` pour `punkt`, `punkt_tab`, `stopwords` et `averaged_perceptron_tagger_eng`.
- **Versionné :** seulement les révisions et les empreintes (dans les importeurs) et les licences (`SOURCES`, `SOURCES.md`).
- **Téléchargements :** révision complète (SHA de 40 caractères) ; empreinte vérifiée avant toute conversion ; `machine.lock` pris par `fetch` et `fetch-nltk`.
- **Questions candidates :**
  - chacune est validée par `validate_question` : schéma fermé, source de la liste fermée, usage, licence, caractère privé et correcteur déclarés pour la source ;
  - identifiant `<usage>/<source>/<numéro ≥ 4 chiffres>` ;
  - chaînes en NFC, aucun flottant dans `target` ;
  - les trois empreintes d'AD-4 se recalculent à l'identique.
- **Télémétrie :** tout fichier de `questions/importers/` qui importe `huggingface_hub` ou `datasets` appelle `disable_telemetry()` (nom nu, niveau module) avant cet import et figure dans `TELEMETRY_IMPORTERS` ; `datasets` entre dans `TELEMETRY_ROOTS`.
- **Isolement :** `huggingface_hub`, `urllib.request`, `nltk` et `pyarrow` ne sont importés que dans `questions/importers/`.

**Never:**
- Importer IFEval, IFEval-fr, FQuAD, GSM-Symbolic, MATH-500, MuSR, BFCL non-live AST (dont `parallel` non-live) ou BFCL web search. Ces sources sont listées dans `REFUSED_SOURCES`, que `fetch` refuse.
- Commiter une donnée téléchargée, une question ou un extrait de question.
- Installer quoi que ce soit hors de `.venv-quality`.
- Exiger le réseau dans un test.
- Coder les générateurs, les questions privées ou maison, `set_builder` (story 3) ou les correcteurs (story 4).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Import nominal | `fetch --source <slug>`, fichiers à l'empreinte épinglée | `raw/` rempli, `candidates.jsonl` réécrit, toutes ses lignes valides | N/A |
| Fichier déjà présent et intact | second `fetch` | rien de retéléchargé ; candidats identiques octet pour octet | N/A |
| Empreinte inattendue | fichier téléchargé ou local modifié | fichier supprimé, aucun candidat écrit | `SourceIntegrityError` ; CLI : journal, code 1 |
| Machine occupée | `machine.lock` détenu par un autre processus | rien de téléchargé | `LockBusyError` journalisé, code 1 |
| Source refusée ou inconnue | `fetch --source musr` | rien de téléchargé | `UnknownSourceError`, code 2 |
| Question non conforme | source, licence, usage, correcteur, identifiant, NFC, flottant ou empreinte incohérents | refus | `QuestionError` |
| Prompt trop long | aucun palier par défaut ne contient `est × 1,25 + plafond` | question écartée, compte journalisé | `PromptTooLongError` interne |
| NLTK | `fetch-nltk` | 4 archives sous `nltk_data/` à l'empreinte épinglée ; déjà présentes : rien de retéléchargé | empreinte inattendue : `NltkDataError`, code 1 |

</intent-contract>

## Code Map

- `scripts/quality_bench/common/schemas.py` -- seul module qui importe `jsonschema` (test `test_single_owner_of_each_library`). Exposer `validate_with(name, schema, record)` : même vérificateur d'entiers stricts que `validate`.
- `scripts/quality_bench/common/jsonl.py` -- seul module des JSONL. Ajouter :
  - `rewrite_jsonl` (temporaire + `os.replace`, fichiers « réécrits » d'AD-2) ;
  - `read_complete_jsonl` (fichier tiers complet : dernière ligne sans `\n` admise).
- `scripts/quality_bench/common/paths.py` -- ajouter `sources_dir`, `source_dir`, `source_raw_dir`, `candidates_path`, `sources_log_path` et `nltk_data_dir`.
- `scripts/quality_bench/common/config.py` -- `DEFAULT_GENERATION` (`caps`, `num_ctx_tiers`) sert au choix du palier des candidats.
- `scripts/quality_bench/__main__.py` -- liste `SUBCOMMANDS`, éditée dans ce fichier seulement. Le module de commandes ne doit pas importer `huggingface_hub` au chargement.
- `tests/unit/test_telemetry.py:108-137` -- `TELEMETRY_ROOTS` et `TELEMETRY_IMPORTERS`. `src/core/eval_engine.py` liste déjà `datasets`.
- `tests/quality_bench/test_package.py` -- `test_single_owner_of_each_library` n'autorisait `src` que dans `__main__.py`. AD-15 impose `disable_telemetry()` dans l'importeur réseau : ajouter ce fichier aux propriétaires, plus des propriétaires uniques pour `huggingface_hub`, `datasets`, `urllib.request`, `nltk` et `pyarrow`.
- `tests/quality_bench/conftest.py` -- `REQUIRED_MODULES` doit inclure `huggingface_hub`.
- Sources vérifiées le 2026-10-11 :
  - BBEH mini (GitHub) : données CC-BY-4.0 ;
  - IFBench (GitHub, JSONL ; le HF n'a que du parquet) ;
  - M-IFEval FR (GitHub) ;
  - BFCL v4 (GitHub `gorilla` ; le HF s'arrête à la v3) ;
  - JSONSchemaBench (HF parquet ; seule source déclarant MIT) ;
  - PIAF v1.0 (GitHub `piaf-code`, MIT ; le HF n'a plus que du parquet).
  - Révisions et fichiers : `scripts/quality_bench/questions/SOURCES.md`.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/questions/schema.py` -- `QUESTION_V1` fermé (AD-5) ; `LICENSES`, `GRADERS`, `SOURCES` (`SourceSpec` : slug, usage, licence, producteur, correcteur, privé) ; `REFUSED_SOURCES` (8 exclusions) ; `prompt_hash`, `target_hash`, `question_hash`, `with_hashes`, `validate_question`.
- [x] `scripts/quality_bench/questions/importers/remote.py` -- `disable_telemetry()` puis `huggingface_hub` ; `RemoteFile` (hôte `hf` ou `github`, révision complète, chemin relatif, `sha256`) ; `fetch_files(files, raw_dir, downloader)` : vérification, temporaire `.part`, `SourceIntegrityError`.
- [x] `scripts/quality_bench/questions/importers/base.py` -- `Importer(slug, files, convert)` ; `build_question` (NFC, `est_prompt_tokens` = caractères / 3, plus petit palier par défaut respectant AD-5, flottants de `target` encodés `{"$float": repr}`, empreintes, validation) ; `PromptTooLongError`.
- [x] Importeurs `bbeh.py`, `ifbench.py`, `mifeval.py`, `bfcl.py` (`bfcl-live`, `bfcl-parallel`, `bfcl-multi`, `bfcl-irrelevance`), `jsonschemabench.py`, `piaf.py` -- chacun expose `IMPORTERS = {slug: Importer}`, avec révisions et empreintes épinglées.
- [x] `scripts/quality_bench/questions/importers/nltk_data.py` -- `PACKAGES` (sous-dossier, `sha256`, licence de l'index) ; `fetch_nltk_data(root, download)` ; seul appel à `nltk.download`.
- [x] `scripts/quality_bench/questions/importers/commands.py` et `__main__.py` -- sous-commandes `fetch --source <slug>… | --all` et `fetch-nltk`, sous `machine.lock`, journal `sources/log-<commande>.log`.
- [x] `scripts/quality_bench/requirements.txt` -- `huggingface-hub>=2.2.0`, `nltk>=3.10.3`, `pyarrow>=26.0.0` (PyPI, 2026-10-11).
- [x] `scripts/quality_bench/questions/SOURCES.md` -- commandes documentées, sources, révisions, licences, attributions, sources refusées.
- [x] `tests/unit/test_telemetry.py` -- `datasets` dans `TELEMETRY_ROOTS` ; `remote.py` dans `TELEMETRY_IMPORTERS`.
- [x] `tests/quality_bench/` -- `test_question_schema.py`, `test_importers.py` (échantillons synthétiques au format des sources), `test_downloads.py` (téléchargeurs simulés, verrou, CLI) ; ajouts à `test_jsonl.py`, `test_package.py`, `factories.py` et `conftest.py`. Couvrir la matrice.
- [x] Exécution réelle sur la tour : `fetch --all` puis `fetch-nltk`.

**Acceptance Criteria:**
- Given `.venv-quality` à jour, when on lance `python -m scripts.quality_bench fetch --all` deux fois, then les deux exécutions écrivent les candidats des 9 sources, et ceux-ci sont identiques octet pour octet.
- Given `REFUSED_SOURCES`, when on la compare aux exclusions de `pistes-et-questions.md`, then les 8 y figurent, et aucune n'est dans `SOURCES`.
- Given le scan AST de télémétrie, when on lance `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` dans `.venv-quality`, then il passe.
- Given `python -m scripts.quality_bench fetch-nltk`, then les 4 paquets sont présents sous `$QUALITY_BENCH_DATA/nltk_data` avec leur empreinte épinglée.

## Spec Change Log

## Review Triage Log

### 2026-10-11 — Review pass
- verdicts: 43 findings — high 0, medium 3, low 36, false 4, maybe-false 0
- findings:
  - `[false]` `[reject]` (intent) Seul remote.py appelle disable_telemetry() ; les autres importeurs n'y figurent pas — la consigne vise les fichiers qui importent huggingface_hub ou datasets ; seul remote.py le fait (AST), et l'appel y précède l'import.
  - `[low]` `[defer]` (intent) La suite tests/unit complète n'a pas tourné — pas de venv d'app sur la tour ; seuls les tests de télémétrie ont tourné dans .venv-quality ; reporté pour une machine dotée d'un venv d'app.
  - `[low]` `[patch]` (intent) fetch-nltk sous machine.lock occupé non testé — ajout de test_cli_fetch_nltk_refuses_when_machine_is_busy.
  - `[false]` `[reject]` (intent) Aucune preuve de l'exécution réelle de fetch-nltk — exécuté sur la tour avant et après les correctifs : code 0, 4 empreintes vérifiées.
  - `[false]` `[reject]` (intent) Le dépôt versionne plus que des empreintes et des licences (effectifs, suffixe BBEH) — aucune donnée téléchargée ni question n'est versionnée ; le suffixe est un texte du banc, les effectifs sont des comptes.
  - `[low]` `[reject]` (intent) Aucun test n'interdit un fichier BFCL non-live — les tuples LIVE, PARALLEL, IRRELEVANCE et MULTI sont des constantes revues ; défaut improbable, garde supplémentaire.
  - `[false]` `[reject]` (intent) MATH-500 modifié pourrait entrer sous un autre slug — tout slug nouveau passe par la liste fermée de schema.py, donc par une revue de code.
  - `[medium]` `[patch]` (vérification) La sélection de fetch --all n'est vérifiée par aucun test — ajout de test_importable_slugs_are_the_nine_sources, test_cli_fetch_all_attempts_every_source et test_importers_match_declared_producers.
  - `[low]` `[patch]` (vérification) Le test de propriétaire unique ne voit pas `from urllib import request` — _absolute_imports rend aussi `module.alias` pour un ImportFrom.
  - `[low]` `[patch]` (vérification) Branche « archive NLTK absente après téléchargement » non testée — ajout de test_fetch_nltk_data_refuses_a_download_without_archive.
  - `[medium]` `[defer]` (blind) bfcl-multi : num_ctx ne compte pas l'historique des tours — règle d'AD-5 (spine), antérieure à la story ; le runner écrit context_exceeded, sans troncature silencieuse ; reporté (frontmatter deferred).
  - `[low]` `[patch]` (blind) Candidats périmés laissés après un fetch en échec — fetch_source supprime candidates.jsonl avant de télécharger ; test mis à jour.
  - `[low]` `[patch]` (blind) fetch --all s'arrête à la première source en échec — boucle qui continue, journal par slug, récapitulatif, code 1 ; test_cli_fetch_continues_after_a_failing_source.
  - `[low]` `[patch]` (blind) NLTK : seule l'archive est vérifiée, pas le dossier extrait — dossier supprimé puis réextrait de l'archive vérifiée ; test_fetch_nltk_data_reextracts_a_tampered_folder.
  - `[low]` `[reject]` (blind) base.py importe remote, donc huggingface_hub — aucun appel réseau à l'import, télémétrie coupée en amont ; déplacer des classes pour un gain cosmétique.
  - `[low]` `[reject]` (blind) huggingface_hub superflu — choix fonctionnel et épinglé ; le dossier temporaire est sous raw/ et sans effet sur les empreintes.
  - `[low]` `[patch]` (blind) _CHAT_MESSAGE non fermé, QUESTION_V1 jamais validé comme schéma — additionalProperties false (les candidats réels n'ont que role et content) ; check_schema exposé et testé.
  - `[low]` `[reject]` (blind) PIAF accepte une question sans réponse — 0 cas à la révision épinglée (vérifié sur les 3 835 candidats) ; garde supplémentaire.
  - `[low]` `[reject]` (blind) BFCL : table de types incomplète, collisions de noms possibles — types de la révision épinglée tous couverts ; un changement de révision change les empreintes et impose une relecture.
  - `[low]` `[reject]` (blind) JSONSchemaBench : rendu indenté qui gonfle l'estimation ; `|` dans unique_id — lisibilité voulue, 2,4 % écartés ; aucun `|` dans les identifiants épinglés.
  - `[low]` `[patch]` (blind) pyarrow absent de REQUIRED_MODULES ; ImportError hors du verrou non journalisée — pyarrow ajouté ; la partie ImportError est rejetée (dépendances installées par requirements.txt).
  - `[low]` `[patch]` (blind) Trous de tests (fetch-nltk occupé, --all, 9 sources, IMPORTERS et producteurs, effectifs de SOURCES.md) — tests ajoutés ; les effectifs de SOURCES.md, documentaires, sont rejetés.
  - `[low]` `[reject]` (blind) read_complete_jsonl ne gère pas le BOM — fichiers épinglés sans BOM (lus sans erreur) ; garde supplémentaire.
  - `[low]` `[patch]` (blind) Test de propriétaire unique contournable pour urllib.request — même correctif que la ligne de vérification.
  - `[low]` `[patch]` (edge) commands.py:50-63 candidats périmés — même correctif que la ligne blind.
  - `[low]` `[patch]` (edge) commands.py:99-102 --all bloqué par une source — même correctif que la ligne blind.
  - `[low]` `[reject]` (edge) convert vide : candidats vides, code 0 — impossible aux révisions épinglées ; garde supplémentaire.
  - `[low]` `[reject]` (edge) setup_logging hors du try — racine de données non inscriptible improbable ; l'erreur reste visible.
  - `[low]` `[reject]` (edge) Deux RemoteFile au même chemin — aucun importeur ne le fait ; garde supplémentaire.
  - `[low]` `[patch]` (edge) Révision de 40 caractères non hexadécimale acceptée — fullmatch `[0-9a-f]{40}` ; test paramétré étendu.
  - `[low]` `[reject]` (edge) Chemin avec antislash, vide, ou dépôt avec `..` — dépôts et chemins sont des constantes du code ; garde supplémentaire.
  - `[low]` `[reject]` (edge) Chemin local qui est un dossier — improbable ; échec bruyant.
  - `[low]` `[patch]` (edge) nltk_data.py:95-96 dossier extrait non vérifié — même correctif que la ligne blind.
  - `[low]` `[reject]` (edge) build_question avec une source inconnue : KeyError — erreur de développeur, bruyante.
  - `[low]` `[reject]` (edge) unit non NFC — aucun importeur ne passe unit.
  - `[low]` `[reject]` (edge) Cible contenant déjà une clé `$float` — absent des sources épinglées.
  - `[low]` `[reject]` (edge) NaN ou Infinity dans un json_schema — l'import épinglé passe ; garde supplémentaire.
  - `[low]` `[reject]` (edge) PIAF sans réponse — même verdict que la ligne blind.
  - `[low]` `[reject]` (edge) Classe absente de CLASS_DOCS : KeyError — les 8 classes des données épinglées sont couvertes ; échec bruyant.
  - `[low]` `[reject]` (edge) Identifiants en double dans possible_answer — absent des données épinglées.
  - `[medium]` `[defer]` (edge) Contexte multi-tours sous-dimensionné — même entrée que la ligne blind, reportée.
  - `[low]` `[patch]` (edge) Contournement du test urllib.request — même correctif que la ligne de vérification.
  - `[low]` `[patch]` (edge) Refus de source (code 2) absent de log-fetch.log — setup_logging vers sources_log_path ; test_cli_refused_source_is_logged_to_file.

## Design Notes

- **Schéma hors de `common/` :** AD-5 place `qb.question/1` dans `questions/schema.py`, alors qu'AD-8 réserve les schémas à `common/schemas.py`. Le schéma est défini dans `questions/` et validé par `common.schemas.validate_with`, pour que `jsonschema` garde un seul propriétaire.
- **Sources des stories suivantes :** la liste fermée ne contient que les sources importées ici. Les générateurs (OneRuler FR, VAR-MATH FR) et les questions maison ou privées y ajoutent leur slug avec leur producteur (story 3).
- **JSONSchemaBench :** `format` reste `null`, et le schéma figure dans le prompt. Le banc mesure le modèle, pas le décodage contraint d'Ollama ; la conformité se vérifie côté client.
- **BFCL :** outils au format Ollama, comme le fait BFCL pour les modèles à appel de fonction :
  - types Gorilla convertis (`dict` → `object`, `float` → `number`, `tuple` → `array`, `any` → `string`) ;
  - points des noms remplacés par `_` ;
  - déclarations d'origine dans `grader.params.functions`, avec `underscore_to_dot: true`.

  Pour le multi-tours, le premier tour va dans `messages` et les suivants dans `turns`. L'état initial va dans `env` : `bfcl_multi_turn` avec `involved_classes` et `initial_config`. Les fonctions exclues sont retirées des outils.
- **`datasets` non installé :** aucun jeu retenu ne l'exige (JSON, JSONL, parquet par `pyarrow`). Il est malgré tout ajouté à `TELEMETRY_ROOTS`, comme le demande AD-15.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pip install -r scripts/quality_bench/requirements.txt` -- expected : installation sans erreur.
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` -- expected : tout passe, sans réseau.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` -- expected : passe. La tour n'a pas de venv d'app : le reste de `tests/unit` ne tourne pas ici.
- `.venv-quality\Scripts\python -m scripts.quality_bench fetch --all` puis `fetch-nltk` -- expected : code 0. Les 9 sources ont leurs candidats, et les données NLTK sont vérifiées.
- `uvx ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx black@25.12.0 --check …`, `uvx isort@7.0.0 --profile black --check …` -- expected : vert.

## Auto Run Result

Status: done

**Résumé :** schéma `qb.question/1` avec liste fermée de 9 sources et 8 sources refusées ; importeurs épinglés (révision et `sha256`) de BBEH mini, IFBench, M-IFEval FR, BFCL v4 (live, parallèle live, multi-tours, non-pertinence), JSONSchemaBench et PIAF ; sous-commandes `fetch` et `fetch-nltk` sous `machine.lock`, données sous `$QUALITY_BENCH_DATA` ; télémétrie et propriétaires uniques des bibliothèques réseau vérifiés par AST.

**Fichiers modifiés :**
- `scripts/quality_bench/questions/schema.py` -- schéma, sources, refus, empreintes, validation.
- `scripts/quality_bench/questions/importers/` (`remote`, `base`, `bbeh`, `ifbench`, `mifeval`, `bfcl`, `jsonschemabench`, `piaf`, `nltk_data`, `commands`) -- téléchargement vérifié, conversion, commandes.
- `scripts/quality_bench/questions/SOURCES.md` -- commandes, sources, licences, attributions, refus.
- `scripts/quality_bench/common/` (`schemas`, `jsonl`, `paths`) -- `validate_with`, `check_schema`, `rewrite_jsonl`, `read_complete_jsonl`, chemins des sources et de `nltk_data`.
- `scripts/quality_bench/__main__.py`, `requirements.txt` -- sous-commandes ; huggingface-hub, nltk, pyarrow.
- `tests/unit/test_telemetry.py` -- `datasets` dans `TELEMETRY_ROOTS`, `remote.py` dans `TELEMETRY_IMPORTERS`.
- `tests/quality_bench/` -- `test_question_schema.py`, `test_importers.py`, `test_downloads.py`, ajouts à `test_jsonl.py`, `test_package.py`, `conftest.py`, `factories.py`.

**Revue :** 43 constats. Patchs appliqués : une entrée medium et onze entrées low (constats regroupés par cause). Reportés : 3 entrées (frontmatter `deferred` et `deferred-work.md`). Rejetés : 4 false et 24 low, raisons dans le journal ci-dessus.

**Revue de suivi recommandée :** non. Une seule entrée medium corrigée (tests de la sélection de `fetch --all`), aucune high ; patchés par verdict : medium 1, low 11.

**Vérification :**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` : 312 passés.
- `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 passés. Le reste de `tests/unit` n'a pas tourné, faute de venv d'app sur la tour.
- `fetch --all` : code 0, 9 sources, candidats identiques octet pour octet entre deux exécutions (460, 300, 235, 1 311, 40, 200, 884, 2 787, 3 835).
- `fetch-nltk` : code 0, 4 archives vérifiées et réextraites.
- ruff 0.14.9, black 25.12.0, isort 7.0.0 : verts.

**Risques résiduels :**
- Licences : 3 paquets NLTK sont « Unknown » dans l'index, et le MIT de JSONSchemaBench ne repose que sur la carte Hugging Face.
- Contexte de bfcl-multi (reporté).
- Flottants des cibles BFCL encodés `{"$float": repr}` : la story 4 doit les décoder.
