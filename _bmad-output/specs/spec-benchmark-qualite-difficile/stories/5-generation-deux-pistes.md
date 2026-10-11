---
title: 'Génération sur les deux pistes'
type: 'feature'
created: '2026-10-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_revision: 'e7e8d63a595d4f18fde588525d55c8b31a3f9794'
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/campagne-et-reprise.md'
  - '{project-root}/scripts/quality_bench/questions/SOURCES.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Reprises non comptées sans borne : une question (ou une chauffe) qui fait tomber le service Ollama lui-même, relancé aussitôt, est refaite indéfiniment.
    evidence: |-
      maybe-false. Après un OllamaUnavailableError dont la sonde /api/version échoue, le runner attend puis refait la question sans compter l'essai (spec, AD-13), et la boucle de chauffe fait de même. Un plantage du runner llama renvoie un 5xx service vivant (essai compté) ; la boucle n'existe que si le serveur entier tombe à chaque essai et redémarre seul. À vérifier au pilote (story 8) sur la tour : provoquer ou observer un tel plantage ; s'il existe, borner les reprises non comptées par clé (règle d'AD-13 à amender).
    location: >-
      scripts/quality_bench/generation/runner.py (Runner._process, Runner._ensure_warm)
    severity: medium (unverified)
  - summary: >-
      Comportements d'Ollama 0.40.2 figés dans le faux service des tests et jamais confrontés au vrai : remote_host dans /api/tags et /api/show, chaînes de capacités et clés model_info, size et size_vram de /api/ps, prompt_eval_cached_count, done_reason "length", déchargement par /api/generate keep_alive 0.
    evidence: |-
      maybe-false. Tous les tests passent par tests/quality_bench/ollama_fake.py (MockTransport), comme l'exige la story ; aucune génération réelle n'a tourné. À vérifier en interactif sur la tour au pilote (story 8) : préflight des 4 modèles, une chauffe et quelques questions, puis lecture de manifest.json, warmups.jsonl et generation.jsonl.
    location: >-
      scripts/quality_bench/generation/preflight.py, runner.py ; tests/quality_bench/ollama_fake.py
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Le banc sait construire un jeu (stories 2 et 3) et corriger un `generation.jsonl` (story 4), mais rien ne le produit : pas de préflight des modèles, pas de boucle de génération ordonnée, pas de chauffe consignée, pas d'exécution des outils pendant la génération. CAP-2 (deux pistes, plafonds de tokens, sortie brute) et la reprise de CAP-3 restent sans commande.

**Approach:** Ajouter le paquet `scripts/quality_bench/generation/` (préflight, conversation, runner, commande) et la sous-commande `generate --campaign <c>`. Elle lit la configuration et le jeu, fait le préflight de chaque modèle par `/api/show` et `/api/tags`, écrit ou compare le manifeste, puis parcourt modèle > piste > palier `num_ctx` > question en ajoutant une ligne `qb.generation/1` brute par (modèle, piste, question, seed), avec chauffe consignée dans `warmups.jsonl` et déchargement en fin de modèle. Règles AD-7, AD-9, AD-11 et AD-14 du spine (et AD-2, AD-3, AD-8, AD-12, AD-13, AD-15).

## Boundaries & Constraints

**Always:**
- **AD-3 :** `generation.jsonl` ne porte ni score, ni succès, ni réponse analysée : `output` est la suite brute des messages postérieurs à `messages`, chacun annoté `turn`. `truncated` est un statut de génération ; c'est `grade` qui le compte comme échec.
- **Statuts (AD-7) :** `context_exceeded` si un appel donne `prompt_eval_count + prompt_eval_cached_count ≥ num_ctx − num_predict`, ou si le palier dépasse le maximum effectif du modèle (ligne écrite sans requête) ; sinon `truncated` dès qu'un appel rend `done_reason == "length"` ; la question s'arrête alors. `error` seulement après `max_attempts` essais en échec, service vivant.
- **Préflight par modèle, avant tout manifeste :** `/api/tags` (digest), `/api/show` (capacités, contexte déclaré). Refus de lancement (code 2, message qui nomme le modèle et la raison) pour : modèle absent de `/api/tags` ou sans `digest` ; `remote_host` déclaré dans `/api/tags` ou `/api/show` ; capacité `decision` ; capacité `completion` absente ; piste `think_on` sans capacité `thinking` ou avec `think_on` faux ou nul ; valeur `think` incohérente avec la capacité (`thinking` déclarée et valeur nulle, ou non déclarée et valeur non nulle) ; valeur `think` chaîne (aucune liste de valeurs publiée par `/api/show`) ; question à outils sélectionnée sans capacité `tools`. Maximum effectif = min(`num_ctx_max` de la configuration, `<arch>.context_length` de `model_info` s'il existe).
- **`models_resolved`** (manifeste, figé au premier lancement) : `tag`, `digest`, `family`, `capabilities` triées, `tracks`, `think_off`, `think_on`, `num_ctx_max` effectif. Toute différence à la reprise (digest, capacités, version d'Ollama, jeu, configuration, machine, harnais) refuse la reprise par `ensure_manifest` (code 1).
- **Ordre (AD-14) :** modèle (ordre de la configuration) > piste (`think_off` puis `think_on`) > palier croissant de `num_ctx_tiers` > question (ordre d'`id`) > seed (`seed_base + epoch`, `epoch < k`), restreint à `selection`. Clé `"{campaign}|{model}|{track}|{question_id}|{seed}"` ; toute clé présente est sautée.
- **Requêtes :** par `OllamaClient.chat` seulement ; `num_predict` = `caps[piste][usage]`, sinon `caps[piste].default` (défauts : 4 096 en raisonnement `think_on`, 2 048 ailleurs) ; `format` de la question ; `tools` seulement si la question en a ; `think` = valeur de la piste si `thinking` est déclarée, sinon absent.
- **Outils (AD-11, contrat de `SOURCES.md`) :** question à `env` non nul : `make_env(env)` neuf par essai, `env.call(name, arguments)` pour chaque appel dans l'ordre, contenu rendu tel quel dans un message `tool`, puis nouvel appel du modèle ; le tour s'achève sur une réponse sans appel. Question à `env` nul : le tour s'achève sur la **première** réponse, appels compris, sans message `tool` (BFCL ne lit que la première réponse). Appel mal formé (sans nom, arguments non objet) : la question s'arrête, sortie gardée. Borne : un pas dont les appels porteraient le total du tour au-delà de `max_tool_calls_per_turn` n'est pas exécuté, `call_cap_reached = true`, la question s'arrête. Tours suivants : messages de `turns[t-1]` injectés dans `output` (rôle `user`, `turn = t`).
- **Chauffe :** une requête jetée chaque fois que le couple (modèle, `num_ctx`) chargé change, avant la première question à requêter du palier, et de nouveau après toute panne du service ; une ligne `qb.warmup/1` dans `warmups.jsonl` (`model`, `num_ctx`, `prompt_tokens`, `size`, `size_vram` lus dans `/api/ps`, `prefill_tok_s`, `load_ns`) ; avertissement sous `min_prefill_tok_s` de la configuration (défaut 50). Échec de la chauffe, service vivant : journalisé, sans ligne, la génération continue.
- **Pannes (AD-13) :** `OllamaUnavailableError` : si `/api/version` répond aussitôt (service vivant), l'essai compte dans `max_attempts` ; sinon `wait_for_ollama` (sans redémarrage), puis la question est refaite en entier sans compter l'essai. Service toujours absent ou revenu dans une autre version : sortie code 1 sans écrire la ligne en cours. `OllamaRequestError` : essai compté. `max_consecutive_errors` lignes `error` de suite : sortie code 1.
- **Exploitation :** `machine.lock` puis `generation.lock` ; `keep_awake()` ; `StopFlag` lu entre deux questions (arrêt propre : code 0) ; `keep_alive: 0` (`client.unload`) en fin de modèle et à toute sortie (au mieux) ; journal `campaigns/<c>/log-generate.log` sans contenu de question ni de réponse ; chaque ligne validée par `common/schemas.validate` avant écriture.

**Never:**
- Importer depuis `generation/` : `grading/`, `judge/`, `stats/`, `report/`, `questions/importers/`, une bibliothèque réseau (`anthropic`, `openai`, `huggingface_hub`, `datasets`, `urllib.request`, `httpx`, `requests`), `nltk` ou spaCy ; `httpx2` n'est atteint que par `ollama/client.py`.
- Lancer une génération réelle, télécharger un modèle ou exiger Ollama dans un test (Ollama simulé par `httpx2.MockTransport`).
- Omettre en silence un modèle, une piste ou une question : tout refus arrête le lancement.
- Modifier `scripts/benchmark_slm.py`, `src/`, `benchmarks/results/`, `.venv`, `.venv-app`, `SPEC.md` ou `stories.yaml` ; commiter une question privée ou une réponse.
- Coder le juge, les statistiques, le rapport ou le pilote (stories 6 à 8).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Campagne nominale | 2 modèles (dont un sans `thinking`), jeu synthétique | lignes dans l'ordre d'AD-14, `think_on` seulement pour le modèle capable ; une chauffe par couple ; `unload` par modèle ; manifeste écrit ; code 0 | N/A |
| Reprise | même commande après arrêt | clés présentes sautées, aucun doublon, série complétée | N/A |
| Arrêt propre | `STOP` créé pendant une question | question terminée et écrite, modèle déchargé, code 0 | N/A |
| Troncature | `done_reason = length` | `status = truncated`, sortie gardée, pas d'appel suivant | N/A |
| Contexte dépassé | prompt + cache ≥ `num_ctx − num_predict` ; ou palier > maximum effectif | `context_exceeded` ; sans requête dans le second cas | N/A |
| Préflight refusé | distant, sans digest, `decision`, piste ou valeur `think` non permise, outils sans capacité | rien n'est écrit, message qui nomme le modèle | `LaunchError`, code 2 |
| Manifeste différent | digest ou version d'Ollama changés à la reprise | rien n'est écrit | `ManifestMismatchError`, code 1 |
| Panne confirmée | connexion refusée puis service revenu | question refaite en entier, essai non compté, nouvelle chauffe | absent après `ollama_wait_s` : code 1, sans ligne |
| Échec service vivant | 5xx ou 4xx, `/api/version` répond | essai compté ; après `max_attempts` : `status = error` | 5 `error` de suite : code 1 |
| Outils multi-tours | `bfcl_multi_turn`, appels puis texte | messages `tool` = `env.call`, tours injectés ; `grade_line` rejoue sans écart | borne dépassée : `call_cap_reached` |
| Outils à un tour | `env` nul, réponse avec appels | une seule réponse au tour 0, aucun message `tool` | N/A |
| Configuration ou jeu | YAML invalide ; jeu absent ; sélection ou palier hors jeu | rien n'est écrit | code 2 (configuration, sélection, palier) ; code 1 (jeu absent) |

</intent-contract>

## Code Map

- `scripts/quality_bench/ollama/client.py` -- `OllamaClient(base_url, transport)` : `version()`, `show(model)`, `tags()`, `ps()`, `unload(model)`, `chat(model, messages, *, seed, num_ctx, num_predict, capabilities, format, think, tools)` → `ChatResult` (`content`, `thinking`, `tool_calls`, `chunks` par champ, `done_reason`, `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`, `durations_ns`, `wall_s`) ; `wait_for_ollama(client, wait_s, expected_version, sleep=, clock=)` ; erreurs `OllamaUnavailableError`, `OllamaRequestError`, `OllamaGoneError`, `OllamaVersionChangedError`. `build_chat_body` lève `ValueError` si `think`/`tools` incompatibles (le préflight doit l'éviter). Messages renvoyés tels quels : un message `tool` peut porter `tool_name`.
- `scripts/quality_bench/common/config.py` -- `DEFAULT_GENERATION` (ajouter `min_prefill_tok_s: 50`, nombre > 0, dans `resolve_generation`) ; `load_campaign(path)` → `CampaignConfig(campaign, set_id, generation, generation_hash, grading)` ; modèles résolus `{tag, family, tracks, num_ctx_max, think_off, think_on}`, `selection` `null | {ids} | {sample: {per_usage, seed}}`.
- `scripts/quality_bench/common/manifest.py` -- `build_manifest(phase="generation", campaign, set_info={id, hash, n}, generation={hash, resolved}, models_resolved, ollama_version, informative=collect_informative(checklist=…))`, `ensure_manifest(path, manifest)` (lève `ManifestMismatchError`), `blocking_hash`.
- `scripts/quality_bench/common/jsonl.py` -- `open_for_append(path, lock)` (verrou du même dossier : `generation.lock` couvre `generation.jsonl` et `warmups.jsonl`), `JsonlAppender.append/keys/__contains__`, `read_jsonl`.
- `scripts/quality_bench/common/{paths,locks,stop,keepawake,logs,canonical}.py` -- `campaign_config_path` (appelé par l'attribut du module : les tests le redirigent), `generation_manifest_path`, `generation_path`, `warmups_path`, `generation_lock_path`, `generation_stop_path`, `machine_lock_path`, `log_path`, `set_questions_path`, `set_tracks_path` ; `FileLock`, `LockBusyError` ; `StopFlag.should_stop()` ; `keep_awake()` ; `setup_logging(command, path)` ; `utc_now`, `sha256_hex`.
- `scripts/quality_bench/common/schemas.py` -- `GENERATION_V1` (messages `output` fermés par rôle, `thinking` chaîne ou null), `validate`, `TRACKS` ; ajouter `qb.warmup/1` au registre `SCHEMAS`.
- `scripts/quality_bench/questions/schema.py:281` -- `set_hash(questions, tracks)` (seul import de `questions/` permis à `generation/`, avec rien d'autre).
- `scripts/quality_bench/envs/registry.py` -- `make_env(spec)` ; `envs/base.py` -- `ToolEnv.call(name, arguments) -> str` ne lève jamais pour un appel du modèle.
- `scripts/quality_bench/grading/{answer,tools,registry}.py` -- consommateurs du format : `tool_steps` (messages `tool` consécutifs à un message `assistant` avec appels), `tool_calls_by_turn`, `answered_turns` ; `bfcl_ast` lit tous les appels du tour 0 ; `grade_line` met `call_cap_reached` en `non_compliant`. Lecture seule ; les tests peuvent l'appeler, pas `generation/`.
- `scripts/quality_bench/grading/commands.py` -- modèle de sous-commande (codes, journal, `_run`) ; `__main__.py` -- `SUBCOMMANDS`, éditée dans ce fichier seulement.
- `scripts/quality_bench/questions/SOURCES.md:216` -- « Contrat d'outils (runner, story 5) » : y ajouter le cas `env` nul et la borne d'appels.
- `tests/quality_bench/test_vendored.py:129-225` -- `_module_path`, `_imports`, `_graph` : graphe d'import AST réutilisable. `test_package.py` -- `httpx2` seulement dans `ollama/client.py`, `json.dumps` seulement dans `canonical.py`, `open()` texte en UTF-8. `test_client.py` -- motif `Recorder` + `httpx2.MockTransport`. `grading_factories.py` -- `questions()`, `FILE_SYSTEM_STATE`, `GOOD_STEPS`, `run_conversation` ; `factories.py`, `set_factories.synthetic_question`.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- deux reports levés ici : contrat des outils à un seul tour (story 4) ; `OllamaUnavailableError` non confirmé compté dans `max_attempts` (story 1).

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/common/config.py`, `common/schemas.py` -- `min_prefill_tok_s` (défaut 50) ; schéma fermé `qb.warmup/1` : `schema, key, manifest, campaign, model, num_ctx, prompt_tokens, size, size_vram, prefill_tok_s, load_ns, created_at` (`size`, `size_vram`, `prefill_tok_s` nuls si inconnus).
- [x] `scripts/quality_bench/generation/__init__.py`, `preflight.py` -- `LaunchError` ; fonctions pures `resolve_model(model_cfg, show, tags)` et `check_launch(resolved, questions_by_track)` appliquant les refus des Boundaries ; `effective_ctx_max`.
- [x] `scripts/quality_bench/generation/conversation.py` -- `run_conversation(question, chat, *, num_ctx, num_predict, max_tool_calls_per_turn)` → `Outcome(status, output, call_cap_reached, calls, tokens, durations_ns, wall_s)` : tours, outils, borne, troncature, contexte ; `chat(messages, tools)` injecté.
- [x] `scripts/quality_bench/generation/runner.py` -- plan (sélection : ids, ou tirage par usage à graine dérivée `sha256_hex([seed, "selection", usage])` dans `think_off`), boucle d'AD-14, essais et pannes, chauffe et `warmups.jsonl`, lignes `qb.generation/1`, compteur d'erreurs, arrêt, déchargement.
- [x] `scripts/quality_bench/generation/commands.py`, `__main__.py` -- sous-commande `generate --campaign <c> [--ollama-url]` : configuration, jeu et empreinte, verrous, préflight, manifeste (`informative.checklist` : rappels d'AD-13 et `OLLAMA_NUM_PARALLEL`, affichés au lancement), runner ; codes 0, 1, 2.
- [x] `scripts/quality_bench/questions/SOURCES.md` -- contrat d'outils complété ; commande `generate`.
- [x] `tests/quality_bench/` -- `ollama_fake.py` (Ollama simulé sur `MockTransport` : version, tags, show, ps, generate, chat scénarisé), `test_preflight.py`, `test_conversation.py`, `test_generate_command.py` (matrice, ordre, reprise, arrêt, pannes, chauffe, sortie corrigeable par `grade_line` pour `bfcl_multi` et `bfcl_ast`), `test_generation_imports.py` (graphe AST de `generation/`), ajouts à `test_schemas.py`, `test_config.py`.

**Acceptance Criteria:**
- Given une campagne synthétique et Ollama simulé, when on lance `python -m scripts.quality_bench generate --campaign <c>` (Ollama injecté), then chaque ligne de `generation.jsonl` valide `qb.generation/1`, ne contient aucun champ `score` ou `success`, et l'ordre des clés suit AD-14.
- Given un modèle sans capacité `thinking` dont la configuration demande `think_on`, when on lance `generate`, then le code est 2 et aucun fichier de campagne n'est écrit.
- Given le graphe d'import AST de `generation/`, then il n'atteint ni `judge/`, ni `questions/importers/`, ni `grading/`, ni une bibliothèque réseau, ni `nltk`, ni un attribut `nltk.download`, et `httpx2` n'y est importé que par `ollama/client.py`.
- Given la suite `.venv-quality\Scripts\python -m pytest tests/quality_bench` et `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"`, then tout passe sans Ollama ni réseau.

## Spec Change Log

## Review Triage Log

### 2026-10-11 — Review pass
- verdicts: 41 findings — high 0, medium 5, low 23, false 9, maybe-false 4
- findings:
  - `[medium]` `[patch]` (VG) Remise à zéro du compteur d'erreurs consécutives jamais testée — tests `test_consecutive_error_counter_resets_on_ok_lines` et `test_lines_without_request_do_not_reset_error_counter` ajoutés.
  - `[medium]` `[patch]` (VG) Contrôle de version de `Runner._alive` jamais exercé — `test_live_failure_with_other_version_exits_1` (503, version différente, code 1, aucune ligne, aucune attente).
  - `[medium]` `[patch]` (VG) Chemins de panne et d'échec de la chauffe non testés — `test_warmup_outage_waits_then_retries_warmup` et `test_warmup_503_with_live_service_writes_no_line`.
  - `[low]` `[patch]` (VG) Tirage de `selection.sample` non épinglé — `test_selection_sample_draw_is_pinned` (ids fixés pour une graine, autre graine différente, usage ajouté sans effet sur les autres).
  - `[low]` `[patch]` (VG) Avertissement `OLLAMA_NUM_PARALLEL` et valeur du manifeste non vérifiés — `test_num_parallel_warning_and_checklist`.
  - `[false]` `[reject]` (IA) Plafond du raisonnement en `think_off` (2 048) contre « 4 096 en raisonnement » — AD-8 fixe `caps: {think_on: {reasoning: 4096, default: 2048}, think_off: {default: 2048}}` (défauts de la story 1) ; `pistes-et-questions.md` place ce plafond sous la piste activée.
  - `[false]` `[reject]` (IA) `decision` refusée au lancement plutôt qu'omise — choix consigné (Design Notes) : un modèle omis resterait attendu par la complétude du rapport (AD-17) ; aucune issue n'omet en silence (AD-8).
  - `[false]` `[reject]` (IA) Toute valeur `think` chaîne refusée — `/api/show` ne publie aucune liste de valeurs ; la règle « parmi les valeurs déclarées » ne peut donc admettre aucune chaîne.
  - `[false]` `[reject]` (IA) Lignes `context_exceeded` écrites à l'arrivée du palier, pas au préflight — après une campagne complète le fichier est le même ; après un arrêt, la reprise écrit les paliers non atteints.
  - `[low]` `[patch]` (IA) Ligne `truncated` produite par `generate` jamais passée par `grade` — `test_truncation_keeps_output_and_stops` vérifie `grade_line` : `truncated`, score 0, succès faux.
  - `[false]` `[reject]` (IA) Passage de `think_off` à `think_on` sans nouvelle chauffe — chaque piste repart du plus petit palier, le couple chargé change donc ; `think` ne change pas le chargement du modèle.
  - `[low]` `[reject]` (IA) Test AST limité à une liste de bibliothèques (ni `socket`, ni `http.client`) — `common/manifest.py` importe légitimement `socket` et `subprocess` ; liste conforme à la spec, élargir demanderait une liste d'exceptions.
  - `[maybe-false]` `[defer]` (IA) Comportements réels d'Ollama figés dans le faux service — à confronter au pilote sur la tour (frontmatter `deferred`).
  - `[maybe-false]` `[defer]` (BH) Boucle sans fin si une question fait tomber le service, relancé aussitôt — dépend d'un plantage du serveur entier ; à vérifier au pilote (frontmatter `deferred`).
  - `[low]` `[patch]` (BH) Après un échec compté, le modèle se recharge à froid sans chauffe — `self.loaded = None` puis `_ensure_warm` avant le nouvel essai (`runner.py`).
  - `[low]` `[patch]` (BH) Compteur d'erreurs remis à zéro par une ligne écrite sans requête ; non persisté à la reprise — remise à zéro limitée aux lignes avec `attempts > 0` ; la persistance est rejetée (état supplémentaire, `max_consecutive_errors` protège une exécution).
  - `[false]` `[reject]` (BH) Lignes `error` jamais rejouées — AD-12 rend `error` définitif ; le rejeu est un report du spine (Deferred).
  - `[medium]` `[patch]` (BH) `think_off: true` accepté pour un modèle à réflexion — `resolve_model` refuse (code 2) une piste `think_off` lancée avec `true` ; cas ajoutés aux tests de refus.
  - `[false]` `[reject]` (BH) `min_prefill_tok_s` dans l'empreinte bloquante — AD-8 rend la section `generation` bloquante en entier, et AD-14 place ce seuil dans la configuration.
  - `[low]` `[patch]` (BH) `50` et `50.0` donnent deux empreintes — `min_prefill_tok_s` normalisé en flottant ; test d'empreinte identique.
  - `[low]` `[patch]` (BH) `OLLAMA_NUM_PARALLEL` lu dans le processus client, pas dans le service — message reformulé : valeur vue par ce processus, celle du service peut différer.
  - `[low]` `[reject]` (BH) Débordement en RAM partagée non détecté par `size_vram < size` — amélioration ; le seuil de préremplissage d'AD-14 couvre le signal demandé.
  - `[low]` `[reject]` (BH) Chauffe ratée sans trace dans `warmups.jsonl` — comportement voulu par la spec ; l'échec est journalisé ; un statut demanderait un nouveau schéma.
  - `[low]` `[reject]` (BH) Défaut du banc (`ValueError`) terminé en trace brute — erreur de programmation, jamais transformée (convention « Erreurs ») ; rare, le préflight évite les paramètres refusés.
  - `[low]` `[patch]` (BH) Message « ligne en cours » pour une erreur d'Ollama au lancement — message reformulé (« aucune ligne n'est écrite pour la question en cours, s'il y en a une »).
  - `[low]` `[patch]` (BH) Tests de refus sans contrôle du message — les tests de refus lisent la ligne « Lancement refusé » (stderr) et y cherchent le modèle et la raison.
  - `[medium]` `[patch]` (BH) Chemins sans test (avertissement de file, panne pendant la chauffe, version pendant la chauffe…) — même cause et mêmes tests que les trois entrées VG medium ci-dessus.
  - `[low]` `[reject]` (BH) Question sans `env` à tours suivants avec appels — inatteignable : seul `bfcl-multi` a des tours, avec `env` non nul.
  - `[low]` `[reject]` (BH) Coût des essais ratés perdu — la spec garde le dernier essai ; un cumul demanderait des champs hors `qb.generation/1`.
  - `[false]` `[reject]` (BH) Spec absente du diff — elle est le fichier de revendications, transmis à part ; elle est commitée à la finalisation.
  - `[low]` `[patch]` (EC) `num_predict ≥ num_ctx` (plafonds de campagne au-dessus de ceux du jeu) : requête gâchée — `build_plan` refuse (code 2) ; tests unitaire et de commande.
  - `[maybe-false]` `[defer]` (EC) Reprises non comptées sans borne dans `_process` — même cause que l'entrée BH ci-dessus.
  - `[maybe-false]` `[defer]` (EC) Boucle de chauffe sans borne — même cause que l'entrée BH ci-dessus.
  - `[low]` `[reject]` (EC) Entrée de `tool_calls` qui n'est pas un objet — hors du format d'Ollama ; garde supplémentaire.
  - `[low]` `[reject]` (EC) Environnement inconnu du registre découvert en cours de campagne — le jeu est construit et validé par `build-set` ; garde supplémentaire.
  - `[low]` `[reject]` (EC) Exceptions non rattrapées en trace brute — même raison que l'entrée BH « défaut du banc ».
  - `[low]` `[patch]` (EC) Pas de chauffe après un 5xx service vivant — même correctif que l'entrée BH du rechargement à froid.
  - `[false]` `[reject]` (EC) Identifiant de sélection présent dans le jeu mais dans aucune piste — `set_builder` écrit `think_off` = toutes les questions du jeu (`set_builder.py:221`).
  - `[low]` `[reject]` (EC) Identifiants en double dans `questions.jsonl` — `set_builder` les refuse ; garde supplémentaire.
  - `[low]` `[reject]` (EC) Entier géant pour `min_prefill_tok_s` : `OverflowError` — valeur absurde ; garde supplémentaire.
  - `[low]` `[patch]` (EC) Échec de `/api/show` au préflight : code 1 et message « ligne en cours » — message corrigé (entrée BH) ; le code 1 reste (panne ou refus du service, pas un refus de configuration).

## Design Notes

- **Décision du report « outils à un seul tour » :** arrêt après la première réponse quand `env` est nul. `bfcl_ast@1` reste inchangé : avec une seule réponse, « tous les pas du tour 0 » = la première réponse, comme BFCL.
- **Décision du report « panne non confirmée » :** sonde `/api/version` immédiate après chaque `OllamaUnavailableError` ; elle répond → essai compté ; elle échoue → attente sans compter. La version relue doit rester celle du manifeste.
- **`decision` refusée plutôt qu'omise :** un modèle omis resterait attendu par la complétude du rapport (AD-17, clés attendues depuis `models_resolved`) ; le refus de lancement est la seule issue cohérente avec AD-8.
- **Chauffe :** invite fixe en français, longue d'environ un quart du palier (estimation 3 caractères par token), `num_predict = 1`, `think` de la piste : le débit de préremplissage mesure la dégradation par palier (story 8).
- **Ligne `error` :** sortie et compteurs du dernier essai, message d'Ollama dans `error` (jamais de contenu de question).

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` -- expected : tout passe, sans réseau ni Ollama.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` -- expected : passe (pas de venv d'app sur la tour : le reste de `tests/unit` ne tourne pas ici).
- `uvx ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx black@25.12.0 --check scripts/quality_bench tests/quality_bench`, `uvx isort@7.0.0 --profile black --check scripts/quality_bench tests/quality_bench` -- expected : vert.
- `.venv-quality\Scripts\python -m scripts.quality_bench generate --help` -- expected : code 0 (aucune génération réelle).
- `git status --porcelain` -- expected : aucun chemin sous `data/` ni `benchmarks/`.

## Auto Run Result

Status: done

**Résumé :** paquet `generation/` et sous-commande `generate --campaign <c>`. Préflight de chaque modèle par `/api/tags` et `/api/show` : refus de lancement (code 2) d'un modèle distant, sans digest, `decision`, sans `completion`, d'une piste ou d'une valeur `think` non permises, d'une question à outils sans capacité `tools`. Boucle modèle > piste > palier > question > seed avec reprise par clé, lignes `qb.generation/1` brutes (`truncated`, `context_exceeded` avec ou sans requête, `error` après `max_attempts`), outils exécutés par `envs/` (arrêt après la première réponse quand `env` est nul), chauffe consignée dans `warmups.jsonl` (`qb.warmup/1`), déchargement `keep_alive: 0`, pannes d'Ollama selon AD-13 (sonde `/api/version` : essai compté si le service vit, attente sinon).

**Fichiers modifiés :**
- `scripts/quality_bench/generation/{__init__,preflight,conversation,runner,commands}.py` -- préflight, conversation et outils, boucle et pannes, commande.
- `scripts/quality_bench/common/config.py` -- `min_prefill_tok_s` (défaut 50, flottant).
- `scripts/quality_bench/common/schemas.py` -- schéma fermé `qb.warmup/1`.
- `scripts/quality_bench/__main__.py` -- sous-commande `generate`.
- `scripts/quality_bench/questions/SOURCES.md` -- contrat d'outils complété, section « Générer une campagne ».
- `tests/quality_bench/` -- `ollama_fake.py`, `test_preflight.py`, `test_conversation.py`, `test_generate_command.py`, `test_generation_imports.py` ; ajouts à `test_config.py` et `test_schemas.py`.

**Revue :** 41 constats (medium 5, low 23, false 9, maybe-false 4). Patchs : 2 entrées medium (tests de vérification manquants, `think_off: true` accepté) et 10 entrées low. Reportés : 2 entrées maybe-false (reprises non comptées sans borne ; comportements réels d'Ollama à confronter au pilote), frontmatter `deferred` et `deferred-work.md`. Rejetés : 9 false et 13 low, raisons dans le journal ci-dessus.

**Revue de suivi recommandée :** oui. Deux entrées medium ont été patchées dans cette passe (patchés par verdict : medium 2, low 10). Risque non vérifié : la nouvelle chauffe avant chaque essai compté, le refus de `think_off: true` et le refus `num_predict ≥ num_ctx` n'ont été relus par aucune passe.

**Vérification :**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` : 885 passés, sans réseau ni Ollama.
- `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 passés. Le reste de `tests/unit` n'a pas tourné, faute de venv d'app sur la tour.
- ruff 0.14.9, black 25.12.0, isort 7.0.0 : verts.
- `generate --help` : code 0. Aucune génération réelle lancée.
- `git status` : aucun chemin sous `data/` ni `benchmarks/`.

**Risques résiduels :**
- Aucune requête réelle à Ollama : le préflight, la chauffe et les compteurs restent à confirmer sur la tour (story 8).
- Une panne du serveur entier relancée à chaque essai ferait boucler la question (reporté).
- Le tirage `selection.sample` prend des questions isolées : des variantes VAR-MATH d'une même `unit` peuvent être séparées.
- Reports levés par cette story : contrat des outils à un seul tour (story 4) et panne non confirmée comptée dans `max_attempts` (story 1).
