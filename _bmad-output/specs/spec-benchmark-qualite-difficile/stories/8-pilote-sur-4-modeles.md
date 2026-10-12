---
title: 'Pilote sur 4 modèles'
type: 'feature'
created: '2026-10-12'
status: 'in-progress'
baseline_revision: '49b2888c04037f06bde0dc1eb525e42357156473'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/campagne-et-reprise.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/statistiques.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/modeles.md'
warnings:
  - oversized
deferred: []
---

<intent-contract>

## Intent

**Problem:** Avant la campagne complète (20 modèles, 5 à 6 jours), rien ne vérifie que le banc discrimine et tient le budget : il manque les campagnes du pilote (CAP-8) et la commande `pilot` qui en tire discordance, plafonds et planchers, stabilité au rejeu, tokens de réflexion, troncature, projection de durée et cohérence d'ordre. `generation.selection` ne sait pas non plus tirer un échantillon par groupes entiers, ni un rejeu qui soit un sous-ensemble garanti du pilote.

**Approach:** Étendre `generation.selection` d'un mode `groups` (tirage stratifié par usage, par source et par groupes entiers, à préfixe stable : un rejeu à la même graine et aux effectifs plus petits est un sous-ensemble du pilote). Écrire les YAML `pilot-20261012` et `pilot-20261012-replay`, un réglage versionné `pilot.yaml`, et la sous-commande `pilot --campaign <c> [--replay <c>-replay] [--aa-date AAAA-MM-JJ]`, en lecture seule, qui écrit un rapport sous `campaigns/<c>/` (hors dépôt). **Code seulement** : aucune génération, la story reste `in-progress` (l'orchestrateur lance les campagnes, puis la passe à `done`).

## Boundaries & Constraints

**Always:**
- **Lecture seule (spine, Consistency Conventions) :** `pilot` lit `campaigns/<c>.yaml`, les manifestes, `generation.jsonl`, `grading.jsonl` (tel quel), `warmups.jsonl` et `log-generate.log` du pilote et du rejeu, le jeu, `pilot.yaml`, l'ancien banc `benchmarks/results/tour-rtx3050-a2b6baf5.json` et `config/models_catalog.json` (lecture seule, jamais modifiés), et un éventuel `benchmarks/quality/references/aa-<date>.json`. Elle n'écrit que `campaigns/<c>/pilot-report.md`, `campaigns/<c>/pilot-report.json` (temporaire puis `os.replace`) et `campaigns/<c>/log-pilot.log`. Ni verrou machine, ni réseau, ni Ollama.
- **Entrées des deux campagnes :** par `report.inputs.load_inputs(c, partial=True)` (mêmes contrôles d'incohérence, mêmes clés attendues que `report`) ; la complétude de chacune est publiée, jamais bloquante. Rejeu absent (YAML ou manifeste) : section « rejeu absent », code 0.
- **Mesures (CAP-8), par piste :** discordance ψ par paire et par usage binaire (et globale hors rédaction) sur les unités définies pour les deux modèles ; usages au plafond ou au plancher ; taux de réponses changeantes au rejeu comparé à ψ ; distribution des tokens de réflexion (`tokens.thinking_est`) et de complétion par usage, taux de troncature par modèle et par usage ; projection de durée des 20 modèles ; cohérence d'ordre avec l'ancien banc et l'indice AA, **sans Spearman ni test** (décompte de paires concordantes) ; rédaction notée par `grading.jsonl`, marquée **provisoire**, `awaiting_judgment` compté à part. Plus les mesures des points « à trancher au pilote » de `deferred-work.md` : part de `context_exceeded` par source (`bfcl-multi` toujours montré), unités non communes et meneur sur unités communes (AD-10), reprises non comptées visibles au journal, part de tokens servis par le cache de préfixe.
- **Rejeu (AD-4, AD-17) :** jointure sur (`model`, `digest`, `track`, `question_id`, `seed`) avec `prompt_hash` égal ; une paire sans correspondance ou de `prompt_hash` ou `digest` différent est exclue et comptée.
- **Projection (campagne-et-reprise.md, Pilote) :** tokens mesurés au pilote divisés par les débits de l'ancien banc de chacun des 20 modèles ; préremplissage dégradé par palier selon `warmups.jsonl`. Au-delà de `budget_hours` (144 h = 6 jours) : l'ordre de réduction de `SPEC.md` (plafonds, piste activée réservée aux modèles thinking, N de la piste activée vers 330) est chiffré et publié comme **proposition**, jamais appliqué.
- **Choix laissés à Anaël :** N, plafonds et K ne sont pas décidés ; le rapport donne les éléments (ψ, N de Connor, troncature projetée par plafond candidat, ratio rejeu/ψ).
- Messages, journal et rapport en français, sans texte de question ni sortie de modèle ; identifiants en anglais. Le rapport est déterministe (deux passes : octets identiques, aucune date).

**Never:**
- Lancer une génération, appeler Ollama, le réseau ou un juge ; télécharger quoi que ce soit.
- Écrire sous `benchmarks/` (aucun export versionné dans cette story), modifier `generation.jsonl`, `grading.jsonl`, `warmups.jsonl`, le jeu, l'ancien banc ou le catalogue.
- Décider N, les plafonds ou K, trancher un point de `deferred-work.md`, ou changer le comportement des sélections `null`, `ids` et `sample` (test épinglé `test_selection_sample_draw_is_pinned`).
- Importer depuis `report/` : `generation/`, `grading/`, `judge/`, `ollama/`, `envs/`, `questions/importers/`, une bibliothèque réseau ; depuis `stats/` : autre chose que la bibliothèque standard, `numpy`, `scipy`, `statsmodels`.
- Toucher `scripts/benchmark_slm.py`, `src/`, `.venv`, `_bmad/`, `.claude/skills/bmad-*`, `benchmarks/results/*.json`, `config/models_catalog.json`, `SPEC.md`, `stories.yaml`, le spine.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Pilote et rejeu complets | 4 modèles, 2 pistes, rejeu = sous-ensemble | `pilot-report.{md,json}` écrits, toutes les sections ; deux passes identiques octet pour octet | code 0 |
| Rejeu absent | pas de `<c>-replay.yaml` ou de manifeste | section stabilité « rejeu absent » | code 0 |
| Rejeu discordant | une paire de `prompt_hash` différent, une clé absente du pilote | exclues et comptées ; taux sur les paires jointes | code 0 |
| Sortie ou score changé | une sortie différente, un score différent | comptés séparément ; ratio au ψ moyen de la piste | code 0 |
| Projection > budget | débits lents ou tokens élevés | section « Proposition de réduction » dans l'ordre de SPEC.md, marquée proposition | code 0 |
| Projection ≤ budget | — | « aucune réduction nécessaire », aucune proposition | code 0 |
| Indice AA absent | aucun `aa-*.json` | « indice AA absent » | code 0 |
| Rédaction en attente | lignes `awaiting_judgment` | comptées à part, moyenne provisoire sur les seules lignes notées | code 0 |
| Jugement absent | aucun dossier de juge | rédaction « non notée », réponses disponibles comptées | code 0 |
| Débit inconnu | un des 20 modèles absent de l'ancien banc ou du catalogue | ligne « débit inconnu », total marqué incomplet | code 0 |
| Entrées incohérentes | ligne hors schéma, jeu différent entre pilote et rejeu, ancien banc illisible | rien n'est écrit, premier écart nommé | `ReportError`, code 1 |
| Configuration | `campaigns/<c>.yaml` ou `pilot.yaml` absent ou invalide | rien n'est écrit | code 2 |
| Sélection `groups` | effectifs par usage et par piste | groupes entiers, stratifiés par source ; même graine et effectifs plus petits → sous-ensemble | `ConfigError` (code 2) si clé inconnue, usage inconnu, `think_on > think_off` ou négatif |

</intent-contract>

## Code Map

- `scripts/quality_bench/common/selection.py` -- `selected_ids(selection, questions, think_off_ids)` (`:52`) et `sample_ids` : ajouter le mode `groups` et un paramètre `think_on_ids: Sequence[str] = ()` ; appelants : `generation/runner.py:104` (`build_plan`), `report/inputs.py:254` (`expected_keys`), `tests/quality_bench/report_factories.py:180` — leur passer `tracks["think_on"]`. `common/` est dans `harness_hash` : permis, aucune campagne réelle n'existe.
- `scripts/quality_bench/common/config.py:166` -- `_resolve_selection` (modes `ids`, `sample`) : ajouter `groups` ; `_resolve_caps` (`:142`) réutilisé pour les plafonds candidats de `pilot.yaml` ; ajouter `load_pilot_settings(path) -> PilotSettings` (seul lecteur de YAML, AD-8 ; `read_yaml`, `_reject_unknown`, `_int`, `_string`).
- `scripts/quality_bench/common/paths.py` -- `campaign_dir`, `warmups_path`, `log_path`, `campaign_config_path`, `REPO_ROOT` ; ajouter `pilot_settings_path()` (`PACKAGE_DIR / "pilot.yaml"`), `pilot_report_path(c, suffix)` (`campaign_dir(c) / f"pilot-report{suffix}"`).
- `scripts/quality_bench/common/schemas.py:604` -- `qb.warmup/1` (`model, num_ctx, prompt_tokens, size, size_vram, prefill_tok_s, load_ns`) ; `qb.generation/1` (`tokens.{prompt, prompt_cached, completion, thinking_est, answer_est}`, `durations_ns.{total, load, prompt_eval, eval}`, `wall_s`, `calls`, `attempts`, `status`, `output`).
- `scripts/quality_bench/generation/runner.py:62,140,287-302,428-433` -- chauffe : invite d'environ `num_ctx/4` tokens, d'où `prompt_tokens` et `prefill_tok_s` par palier ; messages de reprise non comptée : « Ollama ne répond plus » (question et chauffe) dans `log-generate.log`.
- `scripts/quality_bench/report/inputs.py` -- `load_inputs(campaign, partial, aa_date) -> CampaignInputs` (`rows`, `expected`, `models`, `questions`, `completeness`, `generation_hash`, `judgment_hash`, `k`, `aa_reference`), `Row` (sans tokens : relire `generation.jsonl` par `read_jsonl` pour les lignes au manifeste concordant), `ReportError`, `IncompleteError`, `AAReference`, `load_aa_reference`.
- `scripts/quality_bench/report/campaign.py` -- `number()` (flottant fini ou `None`), `WRITING`, `AA_VARIANT_BY_TRACK` ; `stats.units.unit_scores`, `stats.groups.leader_order`.
- `scripts/quality_bench/report/markdown.py:45-93` -- `fr_decimal`, `fr_percent`, `fr_int`, `fr_points` (formats français à réutiliser).
- `scripts/quality_bench/report/commands.py` -- modèle de sous-commande (codes 0/1/2, `setup_logging`, journal par `paths.log_path`).
- `scripts/quality_bench/common/canonical.py` -- `pretty_bytes`, `canonical_bytes`, `sha256_bytes`, `sha256_hex` (seul module qui sérialise du JSON, test `test_json_dumps_only_in_canonical`).
- `scripts/quality_bench/__main__.py` -- liste `SUBCOMMANDS` : ajouter `PILOT` (import après `disable_telemetry()`).
- `benchmarks/results/tour-rtx3050-a2b6baf5.json` -- `models[<nom>]` : `avg_tokens_per_second`, `prefill_tokens_per_second`, `prefill_prompt_tokens` (~4 500), `load_time_ms`, `quality_scores.{reasoning_avg, instruction_following_avg, abstention_avg}`, `tool_capability.success_rate`, `json_capability.schema_compliance_rate`, `needle_in_haystack.ctx_*` (booléens). Clé = nom d'affichage, pas le tag.
- `config/models_catalog.json` -- `models[<nom>].ollama_tag` (pont nom → tag) et `capabilities` (`"thinking"` pour 15 des 20 modèles de `modeles.md`).
- `tests/quality_bench/report_factories.py` -- `make_campaign(tmp_path, monkeypatch, …)` (nom fixe `CAMPAIGN`) : ajouter un paramètre `campaign: str = CAMPAIGN` utilisé partout à la place de la constante ; `SECRET_QUESTION`, `SECRET_OUTPUT`. `tests/quality_bench/factories.py` -- `generation_record`, `model_resolved` (tags `model-<i>:4b`, famille `qwen`).
- `tests/quality_bench/test_generate_command.py:581` -- `test_selection_sample_draw_is_pinned` (ne pas casser) ; `test_report_imports.py`, `test_package.py:62` (`STATS_MODULES` : y ajouter tout nouveau module de `stats/` qui importe `numpy`).
- Jeu réel `data/quality_bench/sets/set-v1/` (hors dépôt, lu seulement pour la vérification manuelle) : groupes tous singletons sauf `var-math-fr` (20 groupes de 3) ; 400 questions en `think_on`, tirées par groupes entiers.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/common/selection.py`, `common/config.py` -- mode `groups` (Design Notes), validation (`ConfigError` : clé inconnue, usage hors `USAGES`, entier négatif, `think_on > think_off`, `per_usage` vide) ; paramètre `think_on_ids` passé par `generation/runner.py`, `report/inputs.py` et `tests/quality_bench/report_factories.py`.
- [x] `scripts/quality_bench/common/config.py`, `common/paths.py`, `scripts/quality_bench/pilot.yaml` -- `load_pilot_settings` (clés fermées, valeurs vérifiées, plafonds candidats résolus par `_resolve_caps`) et chemins ; contenu de `pilot.yaml` dans Design Notes.
- [x] `scripts/quality_bench/campaigns/pilot-20261012.yaml`, `campaigns/pilot-20261012-replay.yaml` -- contenu exact dans Design Notes.
- [x] `scripts/quality_bench/stats/power.py`, `stats/describe.py` -- `mcnemar_sample_size(psi, delta, alpha=0.05, power=0.8)` (Connor 1987, `statistics.NormalDist`, `nan` si `delta ≤ 0` ou `psi < delta` ou `psi ≥ 1` hors domaine) ; `describe(values) -> {n, mean, p50, p90, max}` (`numpy.percentile` linéaire, `nan` si vide). Ajouter `describe` (et `power` s'il importe numpy) à `STATS_MODULES`.
- [x] `scripts/quality_bench/report/pilot.py` -- mesures pures depuis les entrées chargées (discordance, plafonds et planchers, stabilité, tokens et troncature, cohérence d'ordre, rédaction provisoire, points différés) ; `report/projection.py` -- projection pure et proposition de réduction ; `report/pilot_markdown.py` -- rendu français ; `report/pilot_commands.py` -- lecture (pilote, rejeu, warmups, journaux, ancien banc, catalogue, AA), écriture atomique, sous-commande `PILOT` et codes ; `__main__.py`.
- [x] `scripts/quality_bench/questions/SOURCES.md` -- section « Pilote » : commandes `generate` des deux campagnes, `grade`, `judge`, `pilot` ; sorties ; formule de projection ; mode `groups` de la sélection.
- [x] `tests/quality_bench/` -- `test_pilot_command.py` (matrice I/O sur campagnes synthétiques : pilote et rejeu par `make_campaign(campaign=…)` puis lignes retouchées ; warmups, journal, ancien banc, catalogue, AA et `pilot.yaml` synthétiques sous `tmp_path`, `paths.pilot_settings_path` redirigé ; aucun `SECRET_*` dans les sorties ni le journal) ; `test_pilot_measures.py` (ψ, plafonds, stabilité, projection et dégradation calculés à la main, ordre de réduction, Connor sous le tableau de statistiques.md et à 20 % près) ; ajouts à `test_config.py` (mode `groups`, `pilot.yaml`), `test_generate_command.py` (plan d'une sélection `groups`), `test_report_command.py` (clés attendues d'une sélection `groups` : campagne complète) ; `test_campaign_files.py` (les deux YAML réels se chargent, mêmes `generation` hors `selection`, même graine, effectifs du rejeu ≤ pilote et `think_off − think_on` aussi, 4 modèles de `modeles.md`, `k = 1`, plafonds par défaut ; `pilot.yaml` réel : 20 modèles, dont les 4 du pilote, chemins existants).

**Acceptance Criteria:**
- Given un jeu synthétique, when on résout une sélection `groups` puis la même graine avec des effectifs plus petits, then la seconde est incluse dans la première, chaque groupe est pris en entier, et chaque source d'un usage est représentée en proportion (à une unité près).
- Given une campagne synthétique dont la sélection est `groups`, when on lance `report`, then la campagne est complète (`expected == retained`) : le runner et le rapport résolvent la même sélection.
- Given pilote et rejeu synthétiques, when on lance deux fois `python -m scripts.quality_bench pilot --campaign <c>`, then le code est 0, `pilot-report.md` et `pilot-report.json` sont identiques octet pour octet, et ni eux ni `log-pilot.log` ne contiennent un texte de question ou de sortie.
- Given `report/` et `stats/`, when `test_report_imports.py` analyse leurs imports, then les nouveaux modules respectent les graphes permis.
- Given `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` et `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"`, then tout passe (au moins 1 181 et 8 verts avant la story, aucun ne régresse), sans Ollama ni réseau.

## Spec Change Log

## Review Triage Log

### 2026-10-12 — Review pass
- verdicts: 49 findings — high 0, medium 13, low 27, false 9, maybe-false 0
- findings:
  - `[false]` `[reject]` (IA-a) Le chemin de génération (`selection`, `config`, `runner`) et `pilot.yaml` dépassent « commande + YAML » — l'orchestrateur autorise l'extension de `generation.selection` avant la phase 6 ; aucune campagne réelle n'existe, l'empreinte du harnais peut encore changer.
  - `[low]` `[reject]` (IA-b) « Rejeu ⊂ pilote » vérifié sur le jeu réel à la main seulement — les tests ne doivent pas dépendre de `data/` ; la propriété de préfixe est testée sur jeux synthétiques et les inégalités sur les YAML réels.
  - `[low]` `[reject]` (IA-c) Dans les tests de commande, le pilote n'utilise pas `groups` — l'inclusion par préfixe est testée à part (`test_generate_command`) ; la commande ne dépend pas du mode de sélection.
  - `[low]` `[patch]` (IA-d) Rien n'affirme que les 20 modèles réels se résolvent dans l'ancien banc et le catalogue — test en lecture seule des deux fichiers réels (débits, chargement, 15 thinking).
  - `[false]` `[reject]` (IA-e) Capacité thinking lue dans le catalogue et non dans `/api/show` — seule source hors ligne ; `/api/show` fait foi au lancement (préflight).
  - `[false]` `[reject]` (IA-f) « Appliquer » la réduction contre « proposition » — l'orchestrateur exige « en proposition seulement : la décision revient à Anaël ».
  - `[low]` `[reject]` (IA-g) `grading.judge: haiku` figé — section non bloquante, modifiable sans nouvel identifiant (commentaire du YAML) ; `grade` doit désigner un juge.
  - `[false]` `[reject]` (IA-h) Tour et Ollama 0.40.2 absents du code — consignés par le manifeste de `generate`, hors de cette story.
  - `[low]` `[reject]` (IA-i) Déterminisme testé sur campagnes synthétiques seulement — aucune campagne réelle n'existe ; deux processus à `PYTHONHASHSEED` différents sont testés.
  - `[medium]` `[patch]` (VG) `tokens()` sans test de valeurs (réflexion, troncature, plafonds candidats) — tests calculés à la main ajoutés.
  - `[medium]` `[patch]` (VG) `order_consistency` sans test de valeurs — test des ordres et des décomptes sur entrées connues.
  - `[medium]` `[patch]` (VG) `common_units` et `context_exceeded` par palier non testés — tests ajoutés (même cause que BH « mesures sans test »).
  - `[medium]` `[patch]` (VG) Contrôle sur le pilote et débit de décodage mesuré non testés — `project()` testé avec `pilot_questions` non vide.
  - `[low]` `[reject]` (VG) Exclusion par `prompt_hash` ou `digest` non testée de bout en bout — un `prompt_hash` différent du jeu est déjà refusé par `load_inputs` (code 1) avant la jointure ; la jointure est testée en unitaire sur les trois causes.
  - `[false]` `[reject]` (VG) Index du pilote sans `digest` — l'unicité des clés de campagne rend la jointure équivalente au quintuplet ; l'écart de digest est compté à part.
  - `[low]` `[reject]` (VG) L'étape `think_on_n` réduit aussi les chauffes de la piste — effet de quelques secondes sur un total en jours ; « part think_on » couvre la piste entière.
  - `[medium]` `[patch]` (BH) « Global » du pilote (tous usages binaires) et de l'ancien banc (trois usages) non comparables — le pilote est ramené aux trois mêmes usages pour cette comparaison.
  - `[medium]` `[patch]` (BH) Paires non requêtées comptées dans la stabilité, changements de statut non comptés — taux sur les paires requêtées des deux côtés, `status_changed` publié.
  - `[medium]` `[patch]` (BH) « Aucune réduction nécessaire » sur un total incomplet — conclusion « indéterminé » quand des débits manquent.
  - `[low]` `[patch]` (BH) N tiré du seul ψ moyen, « — » inexpliqué — ψ minimal et maximal, N de Connor au ψ maximal, note sur le hors-domaine.
  - `[low]` `[patch]` (BH) Contrôle sans le temps des lignes en erreur ou hors contexte — Σ `wall_s` de toutes les lignes publié à côté du contrôle.
  - `[low]` `[patch]` (BH) Verbosité par modèle cachée derrière `C̄` — complétion moyenne par modèle, piste et usage publiée.
  - `[medium]` `[patch]` (BH) Plafonds candidats fusionnés aux valeurs d'AD-8 et non aux plafonds de la campagne — fusion avec `generation.caps` résolus au moment de la projection, test d'un plafond `think_off` non défaut.
  - `[medium]` `[patch]` (BH) Génération du rejeu jamais comparée à celle du pilote ; rejeu identique au pilote accepté — `ReportError` au premier écart (hors `selection`), code 2 si `--replay` = `--campaign`.
  - `[low]` `[patch]` (BH) `think_on_ids=()` par défaut : zéro groupe `think_on` en silence — paramètre rendu obligatoire.
  - `[low]` `[patch]` (BH) Chemin « ensemble trop court » non testé — test avec `caplog`.
  - `[medium]` `[patch]` (BH) Mesures sans test calculé à la main (`common_units`, paliers, `_cache`, `writing()`, paires AA) — tests ajoutés (même cause que VG).
  - `[low]` `[patch]` (BH) « Même meneur : non » sans unité commune ; égalités rendues « > » — « indéterminé » et « = ».
  - `[false]` `[reject]` (BH) « Réponses disponibles » sans les lignes `truncated` — le juge ne note que les lignes `ok` (AD-16) ; une réponse tronquée n'est ni jugée ni étiquetable.
  - `[low]` `[patch]` (BH) Chaîne « Ollama ne répond plus » recopiée du runner — test qui l'épingle dans les deux messages du runner.
  - `[low]` `[patch]` (BH) Identité du rejeu et de `pilot.yaml` non consignée — empreinte du manifeste du rejeu, chemin et `sha256` de `pilot.yaml` dans les références.
  - `[low]` `[reject]` (BH) Journal créé avant validation de la configuration — même comportement que `report` (story 6) ; `campaigns/<c>/` est hors dépôt.
  - `[false]` `[reject]` (BH) Estimation de la story non reproductible par l'outil ; cases non cochées — l'estimation précède le pilote par construction (le pilote la remplace par des mesures) ; les cases relèvent de la spec, cochées à la finalisation.
  - `[low]` `[reject]` (BH) Reformatage de `test_envs.py` hors story — nécessaire pour que `black --check` passe (écart préexistant, vérifié sur la base).
  - `[low]` `[patch]` (BH) Nom de test trompeur (`test_settings_file_is_written_canonically`) — renommé.
  - `[low]` `[patch]` (BH) « Usages sans mesure » affiche l'identifiant brut de piste — `TRACK_LABELS`.
  - `[low]` `[patch]` (BH) Import du privé `_aa_date` — rendu public (`aa_date_argument`).
  - `[low]` `[patch]` (EC) « À une unité près » faux pour des sources très inégales — docstring reformulée (proportion approchée, vérifiée à moins d'une unité sur set-v1).
  - `[false]` `[reject]` (EC) Groupe à cheval sur deux usages — aucun dans set-v1 (0 sur 760 groupes, contrôle en lecture) ; une question dérivée garde l'usage de son groupe d'origine (AD-5).
  - `[medium]` `[patch]` (EC) Plafonds candidats sur les valeurs par défaut — même cause et même correctif que BH.
  - `[medium]` `[patch]` (EC) `--replay` égal au pilote — même cause et même correctif que BH.
  - `[medium]` `[patch]` (EC) Génération du rejeu différente — même cause et même correctif que BH.
  - `[low]` `[reject]` (EC) Ajout concurrent entre deux lectures — `pilot` se lance après les campagnes ; aucune commande de lecture ne prend de verrou (AD-12).
  - `[low]` `[reject]` (EC) `grading_status` non filtré sur `judgment_manifest` — `grade` réécrit tout le fichier avec un seul juge ; un écart exige un fichier altéré.
  - `[low]` `[reject]` (EC) Les deux `os.replace` ne forment pas une paire atomique — fenêtre de quelques millisecondes, rapport régénérable.
  - `[low]` `[reject]` (EC) Deux `pilot` simultanés partagent le temporaire — un seul opérateur, commande manuelle.
  - `[low]` `[reject]` (EC) `OSError` non rattrapée — même choix que `report` (story 6), rien de publié à moitié.
  - `[low]` `[patch]` (EC) `load_time_ms` absent compté 0 s — traité comme un débit manquant (raison, total incomplet).
  - `[false]` `[reject]` (EC) Lignes de rédaction `truncated` exclues des réponses disponibles — même réfutation que BH (AD-16).

## Design Notes

**Mode `groups` de `generation.selection`.**

```yaml
selection:
  groups:
    seed: 8
    per_usage:
      reasoning: {think_off: 70, think_on: 36}   # effectifs en GROUPES, think_on ≤ think_off
```

Pour chaque usage cité (un usage absent ne donne rien) : groupes de l'usage dans `think_off` (source d'un groupe = celle de sa première question par `id`), partagés en `G_on` (au moins une question dans `think_on`) et `G_off` (les autres). Ordre d'un ensemble G : dans chaque source s, groupes triés par `h(g) = sha256_hex([seed, "groups", usage, g])` puis `g`, rang `r` (0…n_s−1), position `(r + 0.5) / n_s` ; G trié par (position, `h(g)`, `g`). Retenus : les `think_on` premiers de l'ordre de `G_on` et les `think_off − think_on` premiers de `G_off` (avertissement journalisé si un ensemble est trop court, tout est pris). Sélection = toutes les questions `think_off` des groupes retenus ; `think_on` en garde l'intersection (inchangé). Le préfixe est stable : même graine, effectifs plus petits → sous-ensemble ; l'ordre de génération reste celui du runner (AD-14).

**`campaigns/pilot-20261012.yaml`** (commentaire d'en-tête : pilote CAP-8, estimation dans la story 8 ; `grading` non bloquant, juge changeable) :

```yaml
set: set-v1
generation:
  request: {temperature: 0, seed_base: 0, k: 1}
  caps: {think_on: {reasoning: 4096, default: 2048}, think_off: {default: 2048}}
  num_ctx_tiers: [4096, 8192, 16384, 32768]
  selection:
    groups:
      seed: 8
      per_usage:
        reasoning: {think_off: 70, think_on: 36}
        instructions: {think_off: 90, think_on: 44}
        tools: {think_off: 90, think_on: 44}
        extraction: {think_off: 80, think_on: 40}
        rag: {think_off: 80, think_on: 40}
        abstention: {think_off: 80, think_on: 40}
        writing: {think_off: 40, think_on: 20}
  models:
    - {tag: "ling3-tiny:8b-q4_k_m", family: ling, tracks: [think_off, think_on], think_off: false, think_on: true, num_ctx_max: 32768}
    - {tag: "LiquidAI/lfm2.5-2.6b", family: lfm, tracks: [think_off, think_on], think_off: false, think_on: true, num_ctx_max: 32768}
    - {tag: "gemma4:e2b-it-qat", family: gemma, tracks: [think_off, think_on], think_off: false, think_on: true, num_ctx_max: 32768}
    - {tag: "qwen3.5:4b", family: qwen, tracks: [think_off, think_on], think_off: false, think_on: true, num_ctx_max: 32768}
grading:
  judge: haiku
```

**`campaigns/pilot-20261012-replay.yaml`** : identique, sauf `per_usage` : reasoning 18/9, instructions 22/11, tools 22/11, extraction 20/10, rag 20/10, abstention 20/10, writing 10/5 (`think_off`/`think_on`).

**`pilot.yaml`** : `old_bench: benchmarks/results/tour-rtx3050-a2b6baf5.json`, `catalog: config/models_catalog.json` (chemins relatifs à la racine du dépôt, un chemin absolu reste absolu), `budget_hours: 144`, `ceiling: 0.9`, `floor: 0.1`, `reduction: {caps: [{think_on: {reasoning: 3072, default: 1536}}, {think_on: {reasoning: 2048, default: 1024}}], think_on_n: 330}`, `full_models:` les 20 tags de `modeles.md` dans son ordre.

**Taille du pilote (avec le jeu réel `set-v1`, algorithme ci-dessus).**

| Usage | Pilote think_off | Pilote think_on | Rejeu think_off | Rejeu think_on |
|---|---|---|---|---|
| reasoning | 102 (70 groupes) | 54 | 26 | 13 |
| instructions | 90 | 44 | 22 | 11 |
| tools | 90 | 44 | 22 | 11 |
| extraction | 80 | 40 | 20 | 10 |
| rag | 80 | 40 | 20 | 10 |
| abstention | 80 | 40 | 20 | 10 |
| writing | 40 (210 critères) | 20 (109 critères) | 10 | 5 |
| **Total** | **562** | **282** | **140** | **70** |

Rejeu = 25 % du pilote. Rédaction : 4 × 60 réponses, dont 60 de Qwen, soit ~1 270 critères jugeables pour l'échantillon de ~100 étiquettes.

**Estimation de durée** (même formule que la projection, débits de l'ancien banc : décodage 129,6 / 103,3 / 102,6 / 58,9 tok/s, préremplissage 3 008 / 3 808 / 3 700 / 1 845 tok/s ; préremplissage × 0,85 à 16K et × 0,6 à 32K ; 0,5 s de surcoût par requête ; 30 s par chauffe). Par question et par modèle : `complétion / décodage + est_prompt_tokens / préremplissage` (× 2,5 en `bfcl-multi`). Complétions supposées (moyenne des modèles, think_off / think_on) — scénario central : reasoning 450 / 2 600, instructions 400 / 1 300, tools 150 / 900 (bfcl-multi 600 / 1 800), extraction 300 / 1 100, rag 60 / 800, abstention 80 / 800, writing 550 / 1 400 ; scénario haut : 700 / 3 500, 600 / 1 750, 250 / 1 400 (900 / 2 500), 450 / 1 750, 100 / 1 400, 120 / 1 400, 800 / 1 750. Résultat : pilote 8,5 h (central ; 3,0 h en think_off, 5,2 h en think_on) à 11,7 h (haut) ; rejeu 2,35 h à 3,1 h ; **total 10,9 h (central) à 14,8 h (haut)**. La piste activée pèse 60 % ; Qwen 3.5 4B à lui seul ~35 %.

**Discordance ψ :** pour une paire (a, b), un périmètre et une piste : `ψ = #{unités définies pour a et b avec score_a ≠ score_b} / #{unités définies pour a et b}` (scores d'unité par `stats.units`) ; usages binaires seulement, « global » = tous les usages binaires. N indicatif : `mcnemar_sample_size(ψ moyen, δ)` pour δ = 0,10 et 0,20, `n = (z₁₋α/₂·√ψ + z₁₋β·√(ψ − δ²))² / δ²`, présenté comme approximation de Connor, un peu sous les repères exacts de statistiques.md.

**Plafond et plancher :** usage au plafond si la moyenne de chaque modèle est ≥ `ceiling`, au plancher si ≤ `floor` ; les modèles qui y sont seuls sont listés.

**Stabilité :** sur les paires jointes, sortie changée = `sha256_hex(output)` différent ; score changé = deux scores non nuls différents (usages binaires ; rédaction à part) ; ratio = taux de score changé / ψ moyen global de la piste. Aucune conclusion sur K.

**Tokens et troncature :** lignes requêtées (`calls ≥ 1`, statut `ok` ou `truncated`) ; `describe` de `thinking_est` et de `completion` par piste et usage ; troncature = `truncated` / lignes requêtées, par modèle et usage ; pour chaque plafond candidat : part des lignes déjà tronquées ou dont `completion ≥ plafond × calls` (approximation par appel).

**Projection :** pour chaque (piste, usage), complétion moyenne `C̄` et prompt évalué moyen `P̄ = moyenne(tokens.prompt)` par palier (repli : moyenne de la piste et de l'usage), sur les lignes requêtées du pilote, tous modèles confondus. Palier de référence = celui dont le `prompt_tokens` de chauffe est le plus proche de la médiane des `prefill_prompt_tokens` de l'ancien banc des 4 modèles ; `deg(palier)` = médiane sur les modèles du pilote de `prefill(palier) / prefill(référence)` (médiane des chauffes d'un même couple ; 1,0 et signalé sans mesure). Surcoût `f = Σ wall_s / Σ (prompt_eval + eval) / 1e9`. Pour chaque modèle m des 20 et chaque piste (think_on seulement si `"thinking"` dans ses capacités du catalogue) : `f × Σ_questions de la piste (jeu entier) [C̄/décodage_m + P̄/(préremplissage_m × deg(palier))] + paliers × (load_time_m + palier/4 / préremplissage_m)`. Usage sans mesure : `C̄` = plafond, `P̄` = `est_prompt_tokens`, compté et signalé. Contrôle : la même formule appliquée aux questions du pilote, comparée au `wall_s` mesuré de chaque modèle du pilote ; débit de décodage mesuré (`Σ completion / Σ eval`) face à l'ancien banc. Réductions (si total > budget), cumulées dans l'ordre : chaque plafond candidat (`C̄` recalculé avec `min(completion, plafond × calls)`, troncature projetée publiée) ; nombre de modèles thinking en piste activée (constat, sans effet) ; piste activée ramenée à `think_on_n` (part think_on × `think_on_n / |think_on|`). Le premier scénario sous le budget est signalé.

**Cohérence d'ordre :** ancien banc (nom → tag par le catalogue) : reasoning ↔ `reasoning_avg`, instructions ↔ `instruction_following_avg`, tools ↔ `tool_capability.success_rate`, extraction ↔ `json_capability.schema_compliance_rate`, abstention ↔ `abstention_avg`, rag ↔ part des `needle_in_haystack` vrais ; « global » ↔ moyenne des trois premiers. Pilote : moyenne des unités définies par piste et usage (global hors rédaction). Publié : les deux ordres et le décompte de paires concordantes, discordantes, à égalité. AA : variante appariée à la piste, entrées des 4 tags avec leur statut, décompte sur les seules `measured`. Chemin et `sha256` de l'ancien banc, du catalogue et du fichier AA consignés.

**Points différés :** `context_exceeded` / lignes par (modèle, piste, source) et par palier ; par périmètre binaire, unités non communes aux 4 modèles et meneur sur toutes ses unités face au meneur sur les unités communes ; lignes du journal contenant « Ollama ne répond plus », lignes à `attempts > 1`, lignes `error` ; cache : `Σ prompt_cached / Σ (prompt + prompt_cached)` et lignes à `prompt_cached > 0`, par piste et usage.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` -- expected : tout passe (≥ 1 181 avant la story), sans réseau ni Ollama.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -q -k "every_telemetry_importer or precedes_library_import"` -- expected : 8 passés.
- `uvx --offline ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx --offline black@25.12.0 --check scripts/quality_bench tests/quality_bench`, `uvx --offline isort@7.0.0 --profile black --check scripts/quality_bench tests/quality_bench` -- expected : vert.
- `.venv-quality\Scripts\python -m scripts.quality_bench pilot --help` -- expected : code 0.
- `git status --porcelain` -- expected : aucun chemin sous `data/` ni `benchmarks/`.

**Manual checks:**
- Résoudre les sélections des deux YAML réels sur `data/quality_bench/sets/set-v1/` (lecture seule, n'afficher que des comptes) : effectifs du tableau « Taille du pilote », rejeu inclus dans le pilote.

## Auto Run Result

Status: in-progress (code testé et commité ; les campagnes réelles, puis le passage à `done`, reviennent à l'orchestrateur)

**Résumé.** Mode `groups` de `generation.selection` : tirage par groupes entiers, stratifié par usage et par source, à préfixe stable (même graine, effectifs plus petits → sous-ensemble). Campagnes `pilot-20261012` (562 questions en think_off, 282 en think_on, 4 modèles) et `pilot-20261012-replay` (140 / 70, inclus dans le pilote). Réglage versionné `pilot.yaml`. Sous-commande `pilot --campaign <c> [--replay <c>-replay] [--aa-date AAAA-MM-JJ]`, en lecture seule, qui écrit `campaigns/<c>/pilot-report.{md,json}` (hors dépôt) avec :
- la discordance ψ (minimum, maximum, N de Connor) ;
- les usages au plafond ou au plancher ;
- la stabilité au rejeu (sorties, scores et statuts changés, ratio à ψ) ;
- les tokens de réflexion, la troncature et la troncature projetée par plafond candidat ;
- la projection des 20 modèles (contrôle sur le pilote, décodage mesuré) et la proposition de réduction dans l'ordre de SPEC.md ;
- la cohérence d'ordre avec l'ancien banc et l'indice AA ;
- la rédaction provisoire ;
- les points différés : `context_exceeded`, unités non communes, reprises non comptées, cache de préfixe.

Aucune génération, aucun appel à Ollama ni au réseau.

**Fichiers.**
- `scripts/quality_bench/common/{selection,config,paths}.py` -- mode `groups` (`think_on_ids` obligatoire), `load_pilot_settings` (plafonds candidats partiels), chemins du pilote.
- `scripts/quality_bench/generation/runner.py`, `report/inputs.py` -- passage de `think_on_ids`.
- `scripts/quality_bench/campaigns/pilot-20261012.yaml`, `pilot-20261012-replay.yaml`, `pilot.yaml` -- campagnes et réglage.
- `scripts/quality_bench/stats/{power,describe}.py` -- N de Connor, résumé de distribution.
- `scripts/quality_bench/report/{pilot,projection,pilot_markdown,pilot_commands}.py`, `report/commands.py` (`aa_date_argument`), `__main__.py` -- sous-commande `pilot`.
- `scripts/quality_bench/questions/SOURCES.md` -- section « Pilote ».
- `tests/quality_bench/` -- `test_pilot_command.py`, `test_pilot_measures.py`, `test_campaign_files.py` ; ajouts à `test_config.py`, `test_generate_command.py`, `test_report_command.py`, `test_package.py`, `report_factories.py` ; `test_envs.py` reformaté par black (écart préexistant).

**Revue.** 49 constats : medium 13, low 27, false 9. Patchés : 13 medium et 16 low (voir le journal). Rejetés : 9 false et 11 low, raisons au journal. Rien de différé.

**Revue de suivi recommandée : oui.** Plusieurs entrées medium ont été patchées dans cette passe (13 medium, 16 low). Risque non vérifié : les nouvelles règles de stabilité (paires requêtées des deux côtés, `status_changed`) et la fusion des plafonds candidats avec ceux de la campagne n'ont été relues par aucune passe de revue.

**Vérification.**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` : 1 311 passés (1 181 avant la story).
- `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 passés.
- ruff, black, isort (`uvx --offline`) : verts. `pilot --help` : code 0. Aucun chemin sous `data/` ni `benchmarks/`.
- Contrôle manuel sur `set-v1` (comptes seulement) : tableau « Taille du pilote » retrouvé, rejeu inclus dans le pilote, écart de proportion par source ≤ 0,8 groupe.

**Risques résiduels.**
- Rien n'a tourné sur des données réelles.
- La proportion par source n'est garantie à une unité près que pour des sources de tailles proches (vérifiée sur `set-v1`).
- Un `prompt_hash` discordant au rejeu est refusé par `load_inputs` (code 1) avant la jointure.
- `num_ctx_max: 32768` pour les 4 modèles alors que l'ancien banc n'a validé que 16K : la phase 5 doit vérifier le préremplissage à 32K (avertissement `min_prefill_tok_s` dans `warmups.jsonl`).
- Juge `haiku` dans `grading` : à changer si un autre juge note la rédaction du pilote (section non bloquante).
