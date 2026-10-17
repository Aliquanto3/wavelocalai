---
title: 'Calibration du juge'
type: 'feature'
created: '2026-10-12'
status: 'in-progress'
baseline_revision: 'a0fcfe79bb4abbe5221c1985a23a0a920486be72'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/juge-et-calibration.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** CAP-6 n'a pas de commande : rien ne mesure l'accord des juges avec les étiquettes humaines, leur coût, la part escaladée d'une cascade Winnow → Haiku, le biais Qwen ni la stabilité au rejeu, et le format de `calibration/labels.jsonl` n'existe pas. Il manque aussi l'échantillon d'environ 100 critères qu'Anaël doit étiqueter.

**Approach:** Schéma fermé `qb.label/1`, sous-commande `calibrate-sample` (échantillon à étiqueter) et sous-commande `calibrate` (rapport), toutes deux en lecture seule, sans réseau ni verrou, qui écrivent hors dépôt. **Code seulement :** la story reste `in-progress` en attendant les étiquettes et les seuils d'Anaël.

## Boundaries & Constraints

**Always:**
- **Étiquette `qb.label/1`** (fermée, dans `common/schemas.py`) : `{schema, key, label, author, labeled_at, note}`. `key` = clé de jugement `<generation_key>|<critère>` ; `label` ∈ `true`, `false`, `"undecidable"`, `null` (à étiqueter) ; si `label` n'est pas nul, `author` est une chaîne non vide et `labeled_at` une date `AAAA-MM-JJ` ou un horodatage ISO 8601 UTC `Z` ; `note` : chaîne ou `null`. Fichier `$QUALITY_BENCH_DATA/calibration/labels.jsonl`, écrit par Anaël seul (AD-2), qui peut couvrir plusieurs campagnes.
- **Lecture des étiquettes :** BOM UTF-8 en tête ou dernière ligne sans fin de ligne refusés (message explicite : `read_jsonl` ignorerait la dernière étiquette) ; ligne hors schéma, clé en double, clé de la campagne qui n'est pas une unité jugeable : `ReportError` avec le numéro de ligne. Lignes d'autres campagnes (préfixe `<c>|`), `null` et `undecidable` : ignorées dans l'accord et comptées.
- **Unités jugeables :** lignes de `generation.jsonl` au manifeste concordant, `usage = writing`, `status = ok`, une par critère de la question (même règle que `judge/units.py`). Entrées par `report.inputs.load_inputs(c, partial=True)` (manifeste, jeu, familles par `models_resolved[].family`), puis relecture de `generation.jsonl` comme `pilot_commands.campaign_data`. Qwen = `family == "qwen"`.
- **Jugements :** chaque dossier `campaigns/<c>/judgment-<id>/` : `manifest.json` (phase `judgment`, `judge.id = <id>`), `judgment.jsonl` et `batches.jsonl`, contrôlés comme dans `grading/commands._load_judgments` (schéma, manifeste de ligne, juge, clé = `generation_key|criterion`, unité connue, pas de doublon : sinon `ReportError`). Un dossier sans manifeste est « absent » ; un manifeste d'un autre manifeste de génération rend le juge « discordant », exclu et signalé, sans échec. Seul `report/calibration.py` lit `judgment.jsonl`, `batches.jsonl` et `labels.jsonl` (AD-3).
- **Configurations** dans cet ordre : `winnow`, cascade `winnow` → `haiku`, `mimo`, `haiku`, puis tout autre juge présent (ordre alphabétique), hors dossiers `*-replay`. Un juge absent est rapporté « absent » ; sans `winnow` ou sans `haiku`, la cascade est « non simulable ».
- **Mesures** (Design Notes) par configuration : couverture, erreurs, coût, accord (intervalle de Wilson), écart Qwen / non-Qwen, accord à part des critères de comptage. Cascade : par marge, part escaladée, accord, coût, identifiant `winnow-cascade-haiku@<bas>-<haut>`. Stabilité : par paire `<id>` / `<id>-replay`.
- **Seuils :** `--min-agreement` et `--max-qwen-bias`, sans valeur par défaut. Absents : chaque colonne dit « seuil non fixé » et aucune recommandation n'est écrite ; tous deux fournis : proposition, jamais un choix appliqué.
- **Rejeu d'un juge** (AD-12, AD-16) : un identifiant distinct `<id>-replay` dans `judges.yaml`, donc un dossier à lui, jugé par la commande `judge` habituelle sur les mêmes clés ; aucun dossier existant n'est rejugé. Entrée `haiku-replay` ajoutée, réglages identiques à `haiku` (alias YAML).
- **Sorties** (hors dépôt, déterministes, sans date) : `campaigns/<c>/calibration-report.{md,json}` (temporaires puis `os.replace`), `calibration/labels-todo-<c>.{jsonl,md}` ; journaux `campaigns/<c>/log-calibrate.log` et `log-calibrate-sample.log` (identifiants, comptes, chemins). Le rapport et les journaux ne contiennent aucun texte de question ni de réponse ; seul `labels-todo-<c>.md` en contient (consigne, réponse, critère), sous `data/`.
- Français dans les messages, rapports et docs ; identifiants en anglais ; nombres au format français (`report/markdown.fr_*`).

**Never:**
- Écrire `labels.jsonl`, `judgment.jsonl`, `grading.jsonl`, sous `benchmarks/`, ou dans le dépôt ; appeler un juge, Ollama ou le réseau ; prendre `machine.lock`.
- Choisir un seuil d'accord ou un biais maximal à la place d'Anaël ; trancher les critères de comptage ou le rejeu des verdicts `error` (seulement les mesurer).
- Ajouter le juge `winnow-cascade-haiku@…` à `judges.yaml` ou le matérialiser dans un dossier de jugement.
- Modifier `generation/`, `ollama/`, `envs/`, `tests/quality_bench/ollama_fake.py`, `report/projection.py`, `report/inputs.py`, `scripts/benchmark_slm.py`, `src/`, `_bmad/`, `.env`, `SPEC.md`, `stories.yaml`, le spine ; toucher à `common/` au-delà de `qb.label/1` et des chemins de calibration.
- Importer depuis `report/` : `generation/`, `grading/`, `judge/`, `ollama/`, `envs/`, `questions/importers/`, une bibliothèque réseau.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Calibration complète | winnow, haiku, mimo, haiku-replay, étiquettes | rapport avec les 4 configurations, cascade par marge, biais, stabilité ; deux passes identiques octet pour octet | code 0 |
| Sans étiquettes | `labels.jsonl` absent ou seulement `null` | coût, part escaladée, stabilité ; accord « étiquettes absentes » | code 0 |
| Juge absent | pas de `judgment-winnow/` | `winnow` « absent », cascade « non simulable » | code 0 |
| Seuils non fournis | sans `--min-agreement` ni `--max-qwen-bias` | « seuil non fixé », aucune recommandation | code 0 |
| Seuils fournis | les deux | configurations admissibles et proposition | code 0 |
| Rejeu non comparable | `haiku-replay` à réglages ou gabarit différents | stabilité « rejeu non comparable » qui nomme le champ | code 0 |
| Juge discordant | manifeste d'une autre génération | juge exclu et signalé | code 0 |
| Étiquette invalide | hors schéma, doublon, clé inconnue, BOM, fin de ligne manquante | rien n'est écrit, ligne nommée | `ReportError`, code 1 |
| Ligne de jugement incohérente | autre manifeste, autre juge, clé inconnue | rien n'est écrit | `ReportError`, code 1 |
| Configuration | `campaigns/<c>.yaml` absent, seuil hors [0, 1], marge hors [0, 0,5], `--size` < 1 | rien n'est écrit | code 2 |
| Échantillon | 4 modèles dont 1 Qwen, `--size 100 --seed 9` | 50 critères Qwen et 50 répartis sur les autres, au plus un critère par réponse tant que possible, même graine → mêmes octets | code 0 |
| Échantillon impossible | aucune unité jugeable | rien n'est écrit | code 1 |

</intent-contract>

## Code Map

- `scripts/quality_bench/report/pilot_commands.py` -- modèle à suivre : `_validated`, `_lines`, `campaign_data` (relecture de `generation.jsonl` au manifeste concordant), `_write_atomic`, `_run` (codes 0/1/2, `setup_logging`, journal par `paths.log_path`).
- `scripts/quality_bench/report/inputs.py` -- `load_inputs(c, partial=True) -> CampaignInputs` (`manifest`, `generation_hash`, `questions`, `models`, `expected`), `ReportError` ; lecture seule, **ne pas modifier** (l'orchestrateur travaille sur `report/`).
- `scripts/quality_bench/grading/commands.py:144` -- `_load_judgments` : contrôles de référence d'un dossier de jugement (à reproduire, pas à importer).
- `scripts/quality_bench/judge/units.py`, `judge/prompt.py` -- unités (`writing` + `ok`, un critère par unité), `render_instruction` et `final_answer` (consigne et réponse vues par le juge) : non importables depuis `report/`, à reproduire avec un test d'égalité.
- `scripts/quality_bench/common/schemas.py` -- `_closed`, `_TIMESTAMP`, `_NON_EMPTY`, `JUDGMENT_V1`, `BATCH_V1` (lignes `collected` : `cost_usd` réel d'un lot), `SCHEMAS`, `validate`. Ajouter `LABEL_V1`.
- `scripts/quality_bench/common/paths.py` -- `data_root`, `campaign_dir`, `judgment_dir`, `judgment_*_path`, `batches_path`, `log_path`, `check_id`. Ajouter `calibration_dir`, `labels_path`, `labels_todo_path(c, suffix)`, `calibration_report_path(c, suffix)`. `common/` entre dans `harness_hash` : à signaler.
- `scripts/quality_bench/common/jsonl.py` -- `read_jsonl` (ignore la dernière ligne sans `\n`), `rewrite_jsonl` (écriture atomique de `labels-todo-<c>.jsonl`).
- `scripts/quality_bench/common/config.py:884` -- `load_judges` (alias YAML admis par `_UniqueKeyLoader`), `config_hash` inclut l'`id`.
- `scripts/quality_bench/judges.yaml` -- entrées `winnow`, `haiku`, `mimo`, `decider` ; ajouter `haiku-replay`.
- `scripts/quality_bench/stats/wilson.py` -- `wilson_interval(successes, n)` (import tardif, comme `pilot`).
- `scripts/quality_bench/report/markdown.py` -- `fr_decimal`, `fr_percent`, `fr_points`, `fr_int`, `DASH`.
- `scripts/quality_bench/questions/review.py` -- `_fence` (bloc de code sûr) : modèle pour `labels-todo-<c>.md`.
- `scripts/quality_bench/__main__.py` -- `SUBCOMMANDS` : ajouter `CALIBRATE_SAMPLE` et `CALIBRATE`.
- `scripts/quality_bench/questions/writing/writing-fr.yaml` -- 418 critères ; base du test de l'heuristique de comptage.
- `tests/quality_bench/report_factories.py` -- `make_campaign` (familles toutes `qwen` : ajouter un paramètre `families`), `SECRET_QUESTION`, `SECRET_OUTPUT`, `JUDGE_ID`, `JUDGE` de `factories.py` ; `test_pilot_command.py` comme modèle de tests de commande.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/common/schemas.py`, `common/paths.py` -- `LABEL_V1` dans `SCHEMAS` ; chemins de calibration.
- [x] `scripts/quality_bench/judges.yaml` -- `haiku-replay` (alias de `haiku`) et commentaire sur la convention `<id>-replay`.
- [x] `scripts/quality_bench/report/calibration_measures.py` -- fonctions pures : heuristique de comptage, accord, biais, cascade, stabilité, coût, admissibilité et proposition, tirage de l'échantillon.
- [x] `scripts/quality_bench/report/calibration_markdown.py` -- rendus français du rapport et de `labels-todo-<c>.md`.
- [x] `scripts/quality_bench/report/calibration.py` -- lecture (unités, dossiers de jugement, lots, étiquettes), écritures, sous-commandes `CALIBRATE` et `CALIBRATE_SAMPLE` ; `__main__.py`.
- [x] `tests/quality_bench/test_calibration_measures.py`, `test_calibration_command.py` ; ajouts à `test_schemas.py`, `test_judge_config.py` (`haiku-replay` = `haiku` hors `id`), `report_factories.py` (`families`) -- matrice I/O, valeurs calculées à la main, aucun `SECRET_*` hors de `labels-todo-<c>.md`, déterminisme.
- [x] `scripts/quality_bench/questions/SOURCES.md` (section « Calibration du juge » : format d'étiquette, commandes, sorties, mesures, codes), `juge-et-calibration.md` (commande), `_bmad-output/implementation-artifacts/deferred-work.md` (entrées des critères de comptage, des `error` et du coût de Haiku mises à jour ; nouvelles entrées : cascade dans `judges.yaml`, export versionné de la calibration).

**Acceptance Criteria:**
- Given une campagne synthétique jugée par winnow, haiku, mimo et haiku-replay, et des étiquettes connues, when on lance `calibrate`, then accord, écart Qwen, part escaladée et coût égalent les valeurs calculées à la main.
- Given `calibrate-sample` puis `copy labels-todo-<c>.jsonl labels.jsonl` sans rien remplir, when on lance `calibrate`, then le code est 0 et toutes les étiquettes sont comptées « à étiqueter ».
- Given `report/`, when `test_report_imports.py` analyse les imports, then les nouveaux modules respectent les graphes permis.
- Given `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` et le filtre de `tests/unit/test_telemetry.py`, then tout passe (1 311 et 8 avant la story), sans réseau ni Ollama.

## Spec Change Log

### 2026-10-12 — amendement de revue (patch)
- Déclencheur : constat (EC) du juge partiel. Amendé : Design Notes, « Échantillon » (seuls les juges complets réduisent le réservoir, aux clés à verdict booléen ; clés déjà dans `labels.jsonl` écartées). État évité : un échantillon concentré sur quelques modèles quand MiMo s'arrête à son plafond. KEEP : tirage moitié Qwen, un critère par réponse et par tour, ordre par empreinte.

## Review Triage Log

### 2026-10-12 — Review pass
- verdicts: 50 findings — high 0, medium 11, low 29, false 10, maybe-false 0
- note : le premier diff transmis aux relecteurs omettait les fichiers suivis ; un diff complet leur a été renvoyé. Le Blind Hunter a rendu deux rapports : le second (relu sur le diff complet) fait foi, plus deux constats propres au premier.
- findings:
  - `[false]` `[reject]` (IA) Le diff ne contient que les fichiers nouveaux — artefact de mise en forme du diff de revue, corrigé (diff complet renvoyé) ; le code est complet.
  - `[low]` `[reject]` (IA) `common/paths.py` gagne des chemins au-delà du « schéma d'étiquette » — permis par le spec (chemins de calibration) ; quatre fonctions sans logique.
  - `[false]` `[reject]` (IA) Statut `in-review` contre `in-progress` — statut transitoire du workflow ; le statut final est `in-progress`.
  - `[low]` `[patch]` (IA) 84 critères de comptage détectés contre 87 cités — résumé de `deferred-work.md` précisé (87 de la revue de la story 3, 84 de l'heuristique, écart non réconcilié).
  - `[low]` `[reject]` (IA) `labels-todo-<c>.jsonl` au lieu de `labels-todo.jsonl` — choix du spec (un fichier par campagne, `labels.jsonl` multi-campagnes).
  - `[medium]` `[patch]` (IA) La copie de `labels-todo` sur `labels.jsonl` écraserait les étiquettes d'autres campagnes — consigne réécrite (remplir le todo puis ajouter ses lignes à la fin, jamais remplacer) dans `labels-todo-<c>.md`, `SOURCES.md` et `juge-et-calibration.md`.
  - `[false]` `[reject]` (IA) Règle de classement de la proposition inventée par le diff — fixée par les Design Notes du spec, et la proposition n'est jamais appliquée.
  - `[medium]` `[patch]` (BH) Le flux documenté efface les étiquettes antérieures — même cause et même correctif que la copie (IA).
  - `[medium]` `[patch]` (BH) `calibrate-sample` relancé écrase un todo en cours de remplissage — refus (code 1, rien n'est écrit) si une ligne du todo porte une étiquette ; test `test_filled_labels_todo_blocks_a_new_draw`.
  - `[medium]` `[patch]` (BH) Un second tirage reprend des clés déjà dans `labels.jsonl` (doublons puis code 1) — clés de la campagne déjà présentes retirées du réservoir, comptées au journal ; test `test_labels_todo_appended_to_existing_labels_has_no_duplicate`.
  - `[low]` `[patch]` (BH) `.jsonl` et `.md` de l'échantillon écrits séparément — un seul `_write_atomic`.
  - `[low]` `[reject]` (BH) Correspondance item ↔ ligne par le seul rang — l'étiqueteur remplit dans l'ordre ; un identifiant commun ajouterait un champ au schéma fermé pour un mésusage improbable.
  - `[low]` `[reject]` (BH) Étiquette non liée à la réponse jugée (nouveau manifeste) — AD-8 impose un nouvel identifiant de campagne quand `generation` change, donc une autre clé ; étiquette orpheline fatale par choix du spec.
  - `[low]` `[reject]` (BH) Admissibilité sans effectif ni couverture minimaux — le réservoir est réduit aux clés jugées par tous les juges complets, donc les effectifs sont égaux entre juges ; intervalles et `n` publiés ; la proposition n'est qu'indicative.
  - `[false]` `[reject]` (BH) Le biais Qwen mesure un écart d'accord, pas une complaisance — définition de `juge-et-calibration.md` et de CAP-6 (« écart d'accord ») ; l'indulgence par groupe est publiée.
  - `[low]` `[patch]` (BH) Accord global non pondéré sur un échantillon stratifié — phrase ajoutée au rapport (accord sans pondération, pas une estimation pour la campagne).
  - `[low]` `[reject]` (BH) Quota non atteint non redistribué — avertissement prévu par le spec ; au pilote, Qwen a environ 300 critères pour un quota de 50.
  - `[low]` `[reject]` (BH) Identifiants de juges codés en dur — identifiants fixés par `judges.yaml` et AD-16 ; un renommage rend la cascade « non simulable », visible au rapport.
  - `[low]` `[reject]` (BH) Seul Haiku a un rejeu — le spec et `stories.yaml` demandent la stabilité de Haiku ; `<id>-replay` est documenté pour tout autre juge.
  - `[false]` `[reject]` (BH) Modèle sans famille compté non-Qwen — `read_units` ne garde que les clés attendues, construites depuis `models_resolved` : chaque modèle a sa famille.
  - `[low]` `[reject]` (BH) `0` contre `0.0` jugés différents au rejeu — les deux manifestes viennent du même `load_judges` sur une entrée aliasée ; aucune voie ne produit l'écart.
  - `[low]` `[patch]` (BH) Stabilité : `judge_only`/`replay_only` non affichés — colonnes « Juge seul » et « Rejeu seul » ajoutées.
  - `[low]` `[reject]` (BH) Lots `submitted` jamais relevés non signalés dans le coût — déjà consigné dans `deferred-work.md` (entrée du coût de Haiku).
  - `[false]` `[reject]` (BH) Coût de la cascade facturé aux escalades sans ligne Haiku — une cascade réelle appellerait Haiku sur toute escalade : le coût simulé doit les compter.
  - `[low]` `[patch]` (BH) 84 contre 87 — même correctif que (IA).
  - `[low]` `[patch]` (BH) `--cascade-margins` piège la virgule décimale — messages d'erreur complétés (point décimal, virgules entre marges).
  - `[low]` `[patch]` (BH) Dates impossibles acceptées dans `labeled_at` — contrôle `date.fromisoformat`/`time.fromisoformat`, code 1 avec la ligne ; test.
  - `[low]` `[reject]` (BH) Nom d'Anaël dans le texte généré — convention du projet (docs, spec et stories nomment Anaël) ; rapport hors dépôt.
  - `[low]` `[patch]` (BH) Manques de tests — tests ajoutés pour les chemins corrigés (todo rempli, clés déjà étiquetées, dates) ; `_fence` (copie de `review.py`), marges en double (dédoublonnées par ensemble), `none_admissible` : rejetés, sans dommage établi.
  - `[false]` `[reject]` (BH, premier rapport) Diff incomplet — même artefact que (IA).
  - `[false]` `[reject]` (BH, premier rapport) `judge_cost` ignore les coûts de lignes dès qu'un lot est relevé — toutes les lignes de Haiku viennent de lots (`judge/haiku.py`) ; aucun juge ne mêle lots et appels directs.
  - `[medium]` `[patch]` (VG) Exclusion des questions privées de l'échantillon non testée — `test_private_question_is_never_sampled_but_counted`.
  - `[medium]` `[patch]` (VG) Marquage des critères de comptage non vérifié de bout en bout — `test_counting_criteria_agreement_end_to_end` (`question_overrides` dans `make_campaign`).
  - `[medium]` `[patch]` (VG) Contrôles de `batches.jsonl` jamais exercés — `test_incoherent_batch_line_is_refused` (autre manifeste, autre juge, clé en double).
  - `[low]` `[patch]` (VG) Statut `judge_discordant` de la stabilité non testé — test ajouté.
  - `[low]` `[patch]` (EC) `judgment.jsonl` sans `manifest.json` rapporté « absent » alors que `grade` refuse — `ReportError` ; test.
  - `[medium]` `[patch]` (EC) Un juge partiel (MiMo arrêté par son plafond, en ordre de clés donc modèle par modèle) effondre le réservoir sur quelques modèles — seuls les juges complets réduisent le réservoir ; Design Notes du spec mises à jour ; test `test_partial_judge_is_ignored_and_error_keys_are_excluded`.
  - `[low]` `[patch]` (EC) Clés en `error` d'un juge gardées dans le réservoir — réduction aux clés à verdict booléen ; même test.
  - `[medium]` `[patch]` (EC) Second tirage après étiquetage → doublons — même correctif que (BH).
  - `[medium]` `[patch]` (EC) Todo rempli écrasé — même correctif que (BH).
  - `[low]` `[patch]` (EC) Écriture non appariée des deux fichiers — même correctif que (BH).
  - `[low]` `[reject]` (EC) `OSError` (fichier ouvert sous Windows) non rattrapée — même choix que `report` et `pilot` (stories 6 et 8) ; rien de publié à moitié.
  - `[low]` `[reject]` (EC) `load_inputs` échoue sur un `grading.jsonl` ou un fichier AA invalide — entrée imposée par le spec (mêmes contrôles que `report` et `pilot`).
  - `[false]` `[reject]` (EC) Famille « Qwen » ou « qwen3 » non reconnue — convention du spine : `family == "qwen"`.
  - `[low]` `[reject]` (EC) Unité jugée par Haiku sans ligne Winnow absente de la cascade — la cascade part de Winnow ; ces unités sont comptées « étiquetées sans ligne ».
  - `[low]` `[reject]` (EC) Dossier `judgment-winnow-cascade-haiku` — identifiant jamais produit (les cascades portent `@<bas>-<haut>`) et interdit par le spec.
  - `[low]` `[reject]` (EC) Dossier `<id>-replay` sans `<id>` omis de la stabilité — cas sans usage : un rejeu se lance après son juge.
  - `[false]` `[reject]` (EC) Coûts de lignes hors lot ignorés — même réfutation que (BH, premier rapport).
  - `[low]` `[patch]` (EC) Dates impossibles — même correctif que (BH).
  - `[medium]` `[patch]` (EC) Rang des items après ajout à `labels.jsonl` — même correctif que la consigne d'ajout (IA) : le rang vaut pour le todo seulement.

### 2026-10-17 — Revue de suivi (règles du réservoir de `calibrate-sample`)

- source : second avis (SA, Haiku) puis revue (R, Opus), une passe, sans Ollama ni réseau. Règles relues : juges complets seulement (couverture comptée sur les unités publiques, clés `error` écartées ensuite), clés déjà dans `labels.jsonl` écartées (y compris les lignes à `label` nul), refus d'un todo rempli. Aucun constat high ; aucun nouveau constat medium de la revue.
  - `[medium]` `[patch]` (SA) Étiquette posée sur la dernière ligne du todo sans fin de ligne finale : `read_jsonl` l'ignorait et un nouveau tirage l'écrasait (reproduit) — le todo passe par le même contrôle que `labels.jsonl` (`_check_hand_edited` : BOM et fin de ligne manquante refusés, code 1) ; test `test_todo_labeled_on_last_line_without_newline_blocks_a_new_draw`.
  - `[low]` `[patch]` (SA) Refus du re-tirage limité à `label` : `author`, `labeled_at` ou `note` saisis seuls étaient écrasés — toute saisie de ces quatre champs bloque ; test `test_todo_with_author_but_no_label_blocks_a_new_draw`.
  - `[low]` `[reject]` (SA) Journal et dossier `campaigns/<c>/` créés pour une campagne inconnue — même schéma que `grade` (`grading/commands.py`) ; « rien n'est écrit » vise les sorties, le journal est la trace attendue du refus.
  - `[low]` `[patch]` (SA) `datetime.time.fromisoformat` accepte `24:00:00` depuis Python 3.11 (vérifié sous 3.14), pas sous 3.10 — contrôle par `datetime.strptime` sur la forme du schéma, identique de 3.10 à 3.14 ; test `test_unreal_labeled_at_is_refused_on_every_python`.
  - `[low]` `[patch]` (SA) Sans juge complet, réservoir de toutes les unités publiques, même non notées — règle du spec gardée ; avertissement journalisé « Aucun juge complet ».
  - `[low]` `[patch]` (SA) « aucune unité jugeable » trompeur quand tout est déjà étiqueté — message complété « (toutes déjà présentes dans labels.jsonl) » ; test `test_all_units_already_labeled_says_so`.
  - `[low]` `[reject]` (SA) `qb.label/1` accepte `author` « " " » et un `label` nul avec `author`/`labeled_at` — le second est l'état normal d'un todo en cours (compté « à étiqueter ») ; le premier est sans effet sur les mesures, et `common/schemas.py` entre dans `harness_hash` : pas de changement de schéma pour un cas cosmétique.

## Design Notes

**Accord.** Sur les unités étiquetées `true`/`false` qu'un juge a notées d'un verdict booléen : `accord = #égaux / n`, Wilson à 95 % ; publiés aussi : indulgence (juge vrai, humain faux), sévérité (juge faux, humain vrai), étiquetées sans ligne, lignes `error`. **Biais Qwen** = accord(Qwen) − accord(non-Qwen), en points, avec les deux effectifs et intervalles, et l'indulgence de chaque groupe ; comparé en valeur absolue à `--max-qwen-bias`. **Critères de comptage** : heuristique `nombre (chiffres, deux…cent, « un seul ») + au plus un mot + unité (mots, phrases, paragraphes, répliques, lignes, puces, éléments, étapes, conseils, questions)` sur le texte du critère ; accord publié à part, nombre détecté sur `writing-fr.yaml` épinglé par un test.

**Coût.** Total facturé = Σ `cost_usd` des lignes `collected` de `batches.jsonl` s'il y en a (Haiku), sinon Σ `cost_usd` de `judgment.jsonl` ; coût par jugement = total / lignes ; projection = coût par jugement × `--projected-judgments` (11 000 par défaut, volume de `juge-et-calibration.md`).

**Cascade**, par marge `m` (`--cascade-margins`, défaut `0, 0.05, …, 0.5`) : `bas = 0,5 − m`, `haut = 0,5 + m`. Probabilité Winnow `p ≥ haut` → vrai, `p ≤ bas` → faux, sinon (ou ligne `error`, ou `p` nulle) escalade vers le verdict Haiku de la même clé. Part escaladée sur les unités notées par Winnow ; coût = coût par jugement de Haiku × escaladées. Identifiant `winnow-cascade-haiku@0.35-0.65` (deux décimales).

**Stabilité.** Paire `<id>` / `<id>-replay` comparable si `endpoint`, `model`, `settings`, `prompt_template_hash`, `weights_sha256`, `server_version` et `generation_manifest` sont égaux ; sur les clés à verdict booléen des deux côtés : part identique (Wilson), changements. Juge cloud sans rejeu : « rejeu absent ».

**Proposition** (les deux seuils fournis) : candidats = chaque configuration, chaque marge de cascade comptant comme candidat ; admissible si accord ≥ `--min-agreement` et |biais| ≤ `--max-qwen-bias` (biais indéfini : non admissible) ; proposé = accord maximal, puis coût projeté minimal, puis ordre des configurations.

**Échantillon.** Réservoir = unités jugeables publiques, réduit, pour chaque juge concordant hors `*-replay` qui a une ligne pour chaque unité publique, aux clés où il rend un verdict booléen (un juge partiel est ignoré et sa couverture journalisée), puis privé des clés de la campagne déjà présentes dans `labels.jsonl`. Quota : moitié Qwen, moitié non-Qwen (tout à un groupe si l'autre est vide), partagé à parts égales entre les modèles du groupe (reste aux premiers tags). Par modèle, réponses triées par `sha256_hex([seed, "calibration", generation_key])`, critère d'une réponse par `sha256_hex([seed, "calibration", key])` ; tour 1 = premier critère de chaque réponse, puis tour 2… jusqu'au quota (quota non atteint : tout le modèle, avertissement). Ordre des items : `sha256_hex([seed, "calibration-order", key])` (modèles mêlés). `labels-todo-<c>.jsonl` : une ligne `qb.label/1` à `label`, `author`, `labeled_at` et `note` nuls par item ; `labels-todo-<c>.md` : consigne courte, puis par item son numéro (= rang de la ligne), l'identifiant de question, la piste, le critère, la consigne et la réponse, sans modèle ni clé.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` -- expected : tout vert (≥ 1 311 avant la story).
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -q -k "every_telemetry_importer or precedes_library_import"` -- expected : 8 verts.
- `uvx --offline ruff@0.14.9 check`, `uvx --offline black@25.12.0 --check`, `uvx --offline isort@7.0.0 --profile black --check` sur les fichiers touchés -- expected : vert.
- `.venv-quality\Scripts\python -m scripts.quality_bench calibrate --help` et `calibrate-sample --help` -- expected : code 0.
- `git status --porcelain` -- expected : aucun chemin sous `data/` ni `benchmarks/` dans les fichiers ajoutés.

## Auto Run Result

Status: in-progress (code testé et commité ; restent les étiquettes d'Anaël, ses seuils d'accord et de biais Qwen, puis le choix du juge)

**Résumé.** Schéma fermé `qb.label/1` (`common/schemas.py`), chemins de calibration (`common/paths.py`), entrée `haiku-replay` (alias de `haiku`) dans `judges.yaml`, et deux sous-commandes en lecture seule, sans réseau ni verrou :
- `calibrate-sample --campaign <c> [--size 100] [--seed 0]` : échantillon moitié Qwen, moitié non-Qwen, un critère par réponse et par tour, ordre par empreinte. Il écrit `calibration/labels-todo-<c>.{jsonl,md}` en une écriture atomique. Il refuse d'écraser un todo déjà rempli et écarte les clés déjà présentes dans `labels.jsonl`. Seuls les juges complets réduisent le réservoir, aux clés où ils rendent un verdict booléen.
- `calibrate --campaign <c> [--min-agreement X] [--max-qwen-bias Y] [--cascade-margins …] [--projected-judgments N]` : il écrit `campaigns/<c>/calibration-report.{md,json}` et donne, par configuration :
  - l'accord avec Wilson, l'indulgence et la sévérité ;
  - le biais Qwen ;
  - l'accord à part des critères de comptage (heuristique, 84 critères de `writing-fr.yaml`) ;
  - la couverture et le coût (lots `collected`, sinon lignes), projeté sur 11 000 jugements ;
  - pour la cascade Winnow → Haiku : la part escaladée par marge et l'identifiant `winnow-cascade-haiku@<bas>-<haut>` ;
  - la stabilité `<id>` / `<id>-replay` ;
  - une proposition seulement si les deux seuils sont fournis (« seuil non fixé » sinon).

**Fichiers.**
- `scripts/quality_bench/common/schemas.py`, `common/paths.py` -- `qb.label/1`, chemins de calibration (`harness_hash` modifié).
- `scripts/quality_bench/judges.yaml` -- `haiku: &haiku`, `haiku-replay: *haiku`, convention `<id>-replay`.
- `scripts/quality_bench/report/calibration.py` -- lecture (unités, juges, lots, étiquettes), écritures, sous-commandes.
- `scripts/quality_bench/report/calibration_measures.py` -- mesures pures et tirage.
- `scripts/quality_bench/report/calibration_markdown.py` -- rapport et `labels-todo-<c>.md` en français.
- `scripts/quality_bench/__main__.py` -- `CALIBRATE_SAMPLE`, `CALIBRATE`.
- `tests/quality_bench/test_calibration_command.py`, `test_calibration_measures.py` (nouveaux) ; `test_schemas.py`, `test_paths.py`, `test_judge_config.py`, `test_report_imports.py`, `report_factories.py` (`families`, `question_overrides`).
- `scripts/quality_bench/questions/SOURCES.md`, `juge-et-calibration.md`, `_bmad-output/implementation-artifacts/deferred-work.md` -- documentation, entrées mises à jour et ajoutées.

**Revue.** 50 constats : medium 11, low 29, false 10, aucun high.
- **Patchés :** 11 medium et 15 low. Ils couvrent la consigne d'ajout à `labels.jsonl`, le todo rempli protégé, les clés déjà étiquetées, l'écriture appariée, les juges partiels et les verdicts `error` dans le réservoir, `judgment.jsonl` sans manifeste, les dates réelles, la mention de non-pondération, les colonnes de stabilité, les messages des marges, 84 contre 87 et les tests manquants.
- **Rejetés :** 10 false et 14 low, raisons au journal.
- **Différé :** rien de nouveau hors des deux entrées ajoutées à `deferred-work.md`.

**Revue de suivi recommandée : oui.** Plusieurs medium ont été patchés dans cette passe. Aucune passe de revue n'a relu les nouvelles règles du réservoir de `calibrate-sample` (juges complets seulement, clés déjà étiquetées, refus d'un todo rempli).

**Vérification.**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` : 1 430 passés (1 311 avant la story).
- Filtre de `tests/unit/test_telemetry.py` : 8 passés.
- ruff, black et isort (`uvx --offline`) : verts sur les fichiers touchés.
- `calibrate --help` et `calibrate-sample --help` : code 0.
- Aucun fichier sous `data/` ni `benchmarks/`.

**Risques résiduels.**
- Rien n'a tourné sur la vraie campagne `pilot-20261012`.
- `harness_hash` change (`common/`) : une campagne déjà commencée ne se reprend plus.
- L'heuristique de comptage (84) diffère du relevé manuel (87).
- Le classement de la proposition (accord, puis coût) est indicatif.
- La cascade n'est pas matérialisée en juge, et l'export versionné de la calibration n'existe pas (deux entrées de `deferred-work.md`).
