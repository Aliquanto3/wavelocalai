---
title: 'Jugement découplé de la rédaction en français'
type: 'feature'
created: '2026-10-12'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_revision: '02e871645e59c4e44fefe894889434d127fff1ee'
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/juge-et-calibration.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/campagne-et-reprise.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Contrat /v1/systemone d'Ollama 0.40.2 et chargement de Winnow-E4B sur la RTX 3050 jamais éprouvés.
    evidence: |-
      maybe-false. Juge écrit contre une forme minimale du contrat, testée sur faux serveur ; sonde réelle refusée par les permissions de la session. À régler par la procédure manuelle de juge-et-calibration.md (étape 4 : requête d'essai, étape 5 : ollama ps, nvidia-smi).
    location: >-
      scripts/quality_bench/judge/systemone.py
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** `grade` sait lire les verdicts d'un juge (`judgment-<id>/`), mais rien ne les produit : la rédaction en français reste en `awaiting_judgment`. CAP-5 (jugement séparé, reprenable, critère par critère) n'a pas de commande, et le serveur du juge local n'est pas tranché.

**Approach:** Ajouter le paquet `scripts/quality_bench/judge/` et la sous-commande `judge --campaign <c> --judge <id>`, qui relit `generation.jsonl` et écrit `judgment-<id>/judgment.jsonl` (une ligne `qb.judgment/1` par critère, en ajout seul) pour quatre juges décrits dans `scripts/quality_bench/judges.yaml` : `winnow` (contrat local `POST /v1/systemone`), `haiku` (Message Batches), `mimo` (SDK `openai`), `decider` (contrat `/v1/systemone` hébergé, repli). Serveur local : décision d'Anaël (Winnow-E4B importé dans Ollama 0.40.2 comme modèle `decision`), mesures sur la tour non faites (accès bloqué par les permissions de la session) et procédure manuelle consignée. Règles AD-2, AD-8, AD-12, AD-13, AD-15 et AD-16.

## Boundaries & Constraints

**Always:**
- **Entrées :** manifeste de génération (`phase = generation`, campagne égale), `generation.jsonl` (chaque ligne validée, `manifest` = empreinte du `blocking`), jeu `sets/<blocking.set.id>/` dont l'empreinte égale `blocking.set.hash`. Lignes jugées : `usage = writing` et `status = ok` seulement, une unité par critère de `question.criteria`, clé `"{generation_key}|{criterion}"`. Aucun YAML de campagne n'est lu.
- **Réponse jugée :** contenu verbatim du dernier message `assistant` de `output` (sans extraction ni nettoyage : `grading/answer.py` n'est pas importable depuis `judge/`). Consigne = messages de la question, rendus `rôle : contenu`.
- **Configuration :** `judges.yaml` lu par `common/config.load_judges` seulement (clés fermées par `kind`, valeurs par défaut appliquées, empreinte `config_hash` du juge résolu). Kinds : `systemone` (local ou hébergé), `anthropic_batch`, `openai_chat`. Clés d'API lues dans `os.environ` (nom donné par `api_key_env`), jamais écrites nulle part. Un juge dont `endpoint` est nul refuse le lancement (code 2).
- **Manifeste de jugement** (`qb.manifest/1`, `phase = judgment`) : `set`, `generation`, `models_resolved` et `ollama_version` recopiés du manifeste de génération ; `generation_manifest` = son empreinte ; `judge` = `{id, config_hash, endpoint, model, settings, prompt_template_hash, weights_sha256, server_version}` (Haiku : `effort`, `thinking`, `max_tokens` dans `settings`, aucune température) ; `informative.prices` = prix du YAML avec source et date. Reprise refusée si un champ bloquant diffère (code 1).
- **Exploitation :** `machine.lock` (local et cloud) puis `judgment.lock` ; `keep_awake()` ; `StopFlag(judgment-<id>/STOP)` lu entre deux unités (requête locale, appel MiMo, lot ou attente de lot) ; journal `campaigns/<c>/log-judge.log` : identifiants, statuts, comptes et coûts, jamais de texte de question ni de réponse. Chaque ligne validée par `schemas.validate` avant écriture ; toute clé présente est sautée (aucun re-jugement).
- **Pannes (AD-13 transposé) :** service injoignable ou panne passagère (connexion, délai, 429, 5xx, lot `expired`/`canceled`/`errored` non `invalid_request`) : aucune ligne ; nouvel essai jusqu'à `max_attempts`, puis sortie code 1, l'unité reste à juger. Échec propre à l'unité, service vivant (4xx, verdict illisible, refus, troncature) : ligne `error` (`verdict = null`) après `max_attempts` essais. Pas de nouvelle règle de rejeu des `error` (AD-12 : définitif).
- **Juge local (`systemone`, `local: true`) :** URL `localhost`/`127.0.0.1` seulement ; avant tout appel, `/api/ps` d'Ollama (`ollama_url`) : un modèle chargé autre que le modèle du juge refuse le lancement (code 1) ; Ollama injoignable : avertissement, lancement permis. Une requête par ligne de génération, tous ses critères en questions `noul` ; `verdict = probability ≥ 0,5`. À la fin (et à toute sortie, au mieux), `keep_alive: 0` sur Ollama si `unload_after`. Coût 0.
- **Juges cloud :** `PrivateQuestionError` levée avant tout envoi si une unité porte sur une question `private = true` (code 1, rien n'est envoyé). Coût par ligne (`cost_usd`) depuis l'usage renvoyé et les prix du YAML (remise de lot, palier de contexte long). `--max-cost-usd` obligatoire : avant chaque lot ou appel, dépense de ce lancement + estimation prudente (caractères ÷ `chars_per_token`, sortie = `max_tokens`) ≤ plafond, sinon arrêt sans appel (code 3, reprenable).
- **Haiku :** `client.messages.batches` ; chaque requête : `model`, `max_tokens`, `output_config = {effort, format: json_schema {verdict: boolean}}`, `thinking` selon le YAML ; ni `temperature`, ni `top_p`, ni `top_k`, ni préremplissage. `custom_id` = index dans le lot (clé de jugement dans `batches.jsonl`). `batches.jsonl` (ajout seul, schéma `qb.batch/1`) : ligne `submitted` (identifiant du lot, clés, estimation) écrite **avant** toute attente ; ligne `collected` (comptes, tokens, coût réel) après lecture des résultats. Reprise : un lot `submitted` sans `collected` est relu, jamais resoumis ; `attempts` d'une clé = nombre de lots `submitted` qui la contiennent.
- **MiMo :** `openai.OpenAI(base_url=endpoint)`, `chat.completions.create` sans température ; verdict JSON lu dans le contenu ; `thinking` envoyé seulement s'il est réglé dans le YAML.

**Never:**
- Importer `anthropic` ou `openai` hors de `judge/` ; faire atteindre `judge/` par `generation/` ou `grading/`.
- Envoyer une question privée à un juge cloud ; écrire une clé d'API, un texte de question privée ou une réponse dans un journal ou un fichier versionné.
- Télécharger Winnow, lire le dépôt EldanRing, interroger `/v1/systemone` réel ou importer un modèle dans Ollama (interdit par l'orchestrateur) ; appeler Ollama réel au-delà de `GET /api/ps` en lecture.
- Lancer la cascade (simulée à la story 9) ; trancher les 87 critères qui demandent de compter ; coder un rejeu des lignes `error`.
- Exiger réseau, clé ou Ollama dans un test ; modifier `scripts/benchmark_slm.py`, `src/`, `_bmad/`, `benchmarks/results/`, `.env`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Winnow nominal | 2 réponses de rédaction `ok`, faux `/v1/systemone` | une ligne par critère, `probability` lue, `verdict` à ≥ 0,5, coût 0 ; `keep_alive: 0` envoyé | — |
| Reprise | relance après des lignes déjà écrites | seules les clés absentes sont jugées | — |
| Modèle de génération chargé | `/api/ps` liste `qwen3.5:4b` | rien n'est écrit | code 1 |
| Haiku nominal | faux client de lots | `submitted` écrit avant l'attente, puis lignes et `collected` ; coût = usage × prix × 0,5 | — |
| Lot en attente à la reprise | `submitted` sans `collected` | lot relu (`retrieve`), aucun `create` | — |
| Lot expiré | résultats `expired` | aucune ligne, clés resoumises jusqu'à `max_attempts` | puis code 1 |
| Verdict illisible | sortie non JSON `max_attempts` fois | ligne `error`, `verdict = null` | — |
| Question privée | juge cloud, question `private` | aucun envoi, aucune ligne | `PrivateQuestionError`, code 1 |
| Plafond | estimation au-delà de `--max-cost-usd` | aucun appel de plus | code 3 |
| Endpoint nul | `decider` sans endpoint | rien n'est écrit | code 2 |
| MiMo en panne | 503 à chaque essai | aucune ligne | code 1 |

</intent-contract>

## Code Map

- `scripts/quality_bench/common/config.py` -- `read_yaml`, `ConfigError`, helpers `_require_mapping`, `_reject_unknown`, `_int`, `_string` : y ajouter `load_judges` (seul lecteur de YAML, AD-8).
- `scripts/quality_bench/common/schemas.py` -- `JUDGMENT_V1`, `_JUDGE`, `MANIFEST_V1` déjà prêts ; ajouter `qb.batch/1` à `SCHEMAS`.
- `scripts/quality_bench/common/paths.py` -- `judgment_dir/manifest/path/batches/lock/stop_path`, `log_path`, `generation_*`, `set_*` déjà présents.
- `scripts/quality_bench/common/manifest.py` -- `build_manifest(phase="judgment", judge=..., generation_manifest=...)`, `ensure_manifest`, `blocking_hash`, `collect_informative(prices=...)`.
- `scripts/quality_bench/common/{jsonl,locks,stop,keepawake,logs}.py` -- `open_for_append(path, lock)` (verrou du même dossier), `FileLock`, `StopFlag`, `keep_awake`, `setup_logging`.
- `scripts/quality_bench/ollama/client.py` -- `OllamaClient.ps()`, `.unload(model)`, `check_local_base_url` (réutilisés pour le juge local ; spine : `judge → ollama` permis).
- `scripts/quality_bench/questions/schema.py` -- `set_hash(questions, tracks)`.
- `scripts/quality_bench/grading/commands.py` -- modèle de lecture validée (`_read_manifest`, `_check_generation`) et lecteur des jugements (`_load_judgments`) : contrat de sortie à respecter, ne pas importer.
- `scripts/quality_bench/generation/commands.py` -- modèle de commande (verrous, manifeste, codes de sortie, journal console puis fichier).
- `scripts/quality_bench/__main__.py` -- liste `SUBCOMMANDS` à compléter (import après `disable_telemetry()`).
- `tests/quality_bench/grading_factories.py`, `factories.py`, `test_grade_command.py` -- fabriques de questions de rédaction, de lignes et de manifestes ; `test_vendored._graph` pour le test AST.
- `scripts/quality_bench/questions/writing/writing-fr.yaml` -- 80 questions publiques (critères `c1`…`c5`).

## Tasks & Acceptance

**Execution:**
- `scripts/quality_bench/requirements.txt` -- ajouter `anthropic>=1.13.0` et `openai>=3.28.0` (PyPI le 2026-10-12 : 1.13.0 et 3.29.0, installés dans `.venv-quality`) -- SDK des juges cloud.
- `scripts/quality_bench/judges.yaml` -- quatre entrées (`winnow`, `haiku`, `mimo`, `decider`) avec réglages, prix datés et sources -- AD-8.
- `scripts/quality_bench/common/config.py`, `common/schemas.py` -- `load_judges`, `JudgeConfig`, `qb.batch/1` -- configuration et schéma.
- `scripts/quality_bench/judge/{__init__,base,prompt,pricing,systemone,haiku,mimo,decider,units,commands}.py` -- unités à juger, gabarit et empreinte, coût et estimation, quatre juges, commande -- CAP-5.
- `scripts/quality_bench/__main__.py` -- enregistrer `JUDGE`.
- `tests/quality_bench/test_judge_*.py` -- matrice ci-dessus sur faux serveurs (`httpx2.MockTransport`, faux clients SDK), configuration, coût, test AST (`anthropic`/`openai` dans `judge/` seulement, `judge/` non atteint par `generation/` et `grading/`).
- `.env.example` -- `# MIMO_API_KEY=` et `# PERPLEXITY_API_KEY=` en commentaire.
- `juge-et-calibration.md`, `_bmad-output/implementation-artifacts/deferred-work.md` -- choix du serveur, mesures non faites et procédure manuelle ; prix revérifiés ; entrées du juge mises à jour.

**Acceptance Criteria:**
- Given une campagne synthétique jugée par `winnow`, when `grade` tourne avec `grading.judge: winnow`, then les lignes de rédaction passent de `awaiting_judgment` à `ok` avec le score attendu.
- Given un arrêt par `STOP` pendant l'attente d'un lot, when la commande est relancée, then aucun lot n'est resoumis et aucune clé n'est écrite deux fois.
- Given les vraies clés, when `judge` tourne sur une campagne jetable de 2 ou 3 questions publiques (une bonne et une mauvaise réponse synthétique) avec `--max-cost-usd 0.25` par juge, then les verdicts et le coût réel de Haiku et MiMo sont consignés ici.

## Design Notes

Contrat `/v1/systemone` retenu (hypothèse minimale, à vérifier contre le serveur réel) :

```json
POST /v1/systemone
{"model": "winnow-e4b",
 "messages": [{"role": "system", "content": "…"}, {"role": "user", "content": "<consigne + réponse>"}],
 "questions": [{"id": "c1", "type": "noul", "question": "…"}]}
→ {"model": "…", "answers": [{"id": "c1", "type": "noul", "noul": 0.91}],
   "usage": {"prompt_tokens": 812, "completion_tokens": 5}}
```

Seuls sont confirmés (revue d'actualité du spine) le chemin, la réponse `{"type":"noul","noul":p}`, l'enveloppe `{model, answers, usage}` et 1 à 256 questions par requête. Les réponses sont appariées par `id` s'il est rendu, sinon par position.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` -- expected: tout vert (1 082 avant la story, aucune régression).
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -q -k "every_telemetry_importer or precedes_library_import"` -- expected: 8 verts.

## Spec Change Log

## Review Triage Log

### 2026-10-12 — Review pass
- verdicts: 41 constats des relecteurs (28 lignes une fois les doublons regroupés) + 7 constats de l'audit d'intention, soit 35 lignes — high 2, medium 8, low 22, false 3, maybe-false 0
- findings:
  - `[medium]` `[reject]` (intent) Juge local jamais mesuré sur la tour, contrat `/v1/systemone` supposé — exclu par l'intention : l'orchestrateur interdit téléchargement, import, appel de `/v1/systemone` ; consigné dans `juge-et-calibration.md` (procédure manuelle) et `deferred-work.md`.
  - `[medium]` `[reject]` (intent) Tenue en français de Winnow non mesurée — même exclusion ; reportée à la procédure manuelle puis à la story 9.
  - `[low]` `[reject]` (intent) `decider` non lançable (`endpoint: null`) — l'intention demande « code et faux serveur seulement » ; chemin hébergé désormais testé sur faux serveur (voir B10).
  - `[low]` `[reject]` (intent) Tests Haiku sur faux client, essai réel attesté par la doc seulement — l'essai réel a eu lieu (lot `msgbatch_014sKZk7RcraE5iqju3Nc5wV`), ses données restent hors dépôt par règle (`data/`).
  - `[low]` `[reject]` (intent) Pas de bascule automatique vers decider — aucune lecture de l'intention ne l'exige (« en repli » = entrée de `judges.yaml`).
  - `[low]` `[patch]` (intent) « 7 étapes » contre 8 dans la procédure — corrigé dans `deferred-work.md`.
  - `[low]` `[patch]` (intent) Ligne « tenue en français à vérifier à la story 7 » contradictoire — réécrite dans `juge-et-calibration.md`.
  - `[high]` `[patch]` (VG-5, B1, E3, E20) Haiku : une clé épuisée en pannes passagères bloquait toute relance (code 1 avant toute soumission) — l'épuisement passager se compte désormais par lancement (`submitted_here`), les échecs propres à l'unité sur tout `batches.jsonl` ; test `test_relaunch_after_exhausted_transient_resubmits`.
  - `[high]` `[patch]` (B2, E1, E2) 401/403/404 rendus `UnitError` puis lignes `error` définitives sur toute la campagne (clé fausse, modèle non importé, chemin du contrat faux) — `JudgeLaunchError` (code 1, aucune ligne, sans nouvel essai) dans `systemone.py` et `mimo.py` ; tests paramétrés.
  - `[medium]` `[patch]` (B3, E4) Plafond vérifié une fois par groupe alors que chaque essai est facturé — `Judge.judge(items, budget)` vérifie avant chaque essai et débite chaque essai facturé ; `run` ne débite plus.
  - `[medium]` `[patch]` (B5) `batches.create` relancé sur délai ou 5xx : lot créé deux fois et payé deux fois — soumission jamais relancée (`retry=False`), message qui demande de vérifier la console ; tests 429, 500, connexion.
  - `[medium]` `[patch]` (VG-1) Plafond de MiMo non testé — `test_mimo_cost_cap_stops_before_any_call`, `test_mimo_cost_cap_stops_after_some_calls`.
  - `[medium]` `[patch]` (VG-2) Classement des erreurs d'API de Haiku (`_call`) non testé — tests 429 à la lecture (3 essais puis code 1, lot relu à la reprise), 400 à la soumission.
  - `[medium]` `[patch]` (VG-3) Résultats `errored` et troncature `max_tokens` de Haiku non testés — tests `invalid_request_error` (lignes `error`), autre type (passager, code 1), `max_tokens`.
  - `[low]` `[patch]` (VG-4) Essai échoué puis réussi (attempts, tokens) non testé — tests MiMo (`length` puis succès : attempts 2, tokens et coût cumulés) et winnow (503 puis succès).
  - `[low]` `[patch]` (B4, E5) Coût des essais facturés perdu quand le groupe finit en panne — débité au budget à chaque essai et cité dans le message d'erreur.
  - `[low]` `[patch]` (B6) Juge local lancé sans `weights_sha256` — avertissement au lancement (l'empreinte se relève à l'import manuel ; refuser bloquerait l'essai de la procédure).
  - `[low]` `[patch]` (B7) `.env.example` contredit « jamais dans un fichier » — règle précisée : jamais dans un fichier versionné ni un journal ; `.env` (ignoré par git) chargé par `disable_telemetry()`.
  - `[low]` `[patch]` (B8) Docs incohérentes (7/8 étapes, date du prix de decider, fourchette 0,02-0,04 $) — `checked: 2026-10-07` et source « non revérifiés », texte aligné.
  - `[low]` `[reject]` (B9) Plancher `openai>=3.28.0`, constante `JUDGE_OPERATIONAL_KEYS` non utilisée, seuil 0,5 dupliqué — plancher fixé par le spine (installation réelle en 3.29.0) ; la constante documente la règle, testée par `test_config_hash_ignores_prices_and_operational_keys` ; seuil sans divergence observable.
  - `[medium]` `[patch]` (B10) Chemins à risque sans test (Decider hébergé, erreurs Haiku, 401/404 MiMo, budget sur relance) — tests ajoutés, dont `test_decider_hosted_nominal` (https, en-tête `Authorization`, coût, pas de `/api/ps`), refus du privé et plafond obligatoire pour decider.
  - `[low]` `[patch]` (B11) `_date` accepte `2026-13-45` — `date.fromisoformat` ; test.
  - `[low]` `[patch]` (E6) `prices: null` explicite accepté pour un juge cloud (coût et plafond nuls) — refusé ; test.
  - `[low]` `[patch]` (E7) `api_key_env: null` accepté pour un juge cloud — refusé ; test.
  - `[low]` `[reject]` (E8) `retrieve` en 404 sur un lot repris (résultats purgés après 29 jours) bloquerait la reprise — reprise à plus de 29 jours improbable, correctif non trivial (nouvelle branche d'état) ; résolution manuelle possible.
  - `[low]` `[patch]` (E9, E10) Type de résultat inconnu : schéma fermé de `counts` violé après l'écriture des lignes — traité en panne passagère, hors `counts` ; test.
  - `[low]` `[patch]` (E11) Ligne de `batches.jsonl` hors schéma : trace Python sans code défini — `JudgeError` (code 1).
  - `[false]` `[reject]` (E12) `custom_id` négatif — les `custom_id` sont produits par le banc (`0…n-1`) et rendus tels quels par l'API.
  - `[low]` `[reject]` (E13) Pas d'attente avant de resoumettre un lot après une panne passagère — un lot dure des minutes ; complexité ajoutée sans gain établi.
  - `[low]` `[patch]` (E14) `poll_s: 0` accepté — nombre strictement positif ; test.
  - `[false]` `[reject]` (E15) Plus de 256 critères par réponse — `house.py` borne le nombre de critères (`MAX_CRITERIA`), bien en dessous.
  - `[low]` `[patch]` (E16) `id` de réponse non hachable : `TypeError` — appariement par `id` seulement s'il est une chaîne.
  - `[false]` `[reject]` (E17) Identifiants de critère en double — `house.py` impose `c1…cN` dans l'ordre.
  - `[low]` `[patch]` (E18) Autre `openai.APIError` non attrapée — `UnitError` « réponse invalide ».
  - `[low]` `[patch]` (E19) Entrée `/api/ps` sans nom : refus pour un modèle « fantôme » — noms vides ignorés ; test.
  - (doublons comptés dans les lignes ci-dessus : VG-5 = B1 = E3 = E20 ; B2 = E1 = E2 ; B3 = E4 ; B4 = E5.)

## Auto Run Result

Status: done

**Résumé.** Sous-commande `judge --campaign <c> --judge <id> [--max-cost-usd X]` et paquet `scripts/quality_bench/judge/` : unités = critères des réponses de rédaction `ok`, une ligne `qb.judgment/1` par critère en ajout seul, reprise sans re-jugement, manifeste `phase = judgment`, `machine.lock` puis `judgment.lock`, `STOP`, maintien en éveil. Quatre juges décrits dans `judges.yaml` : `winnow` (contrat `/v1/systemone` local, `/api/ps` avant lancement, `keep_alive: 0` à la sortie), `haiku` (Message Batches, sortie structurée, ni température ni préremplissage, `batches.jsonl` écrit avant l'attente), `mimo` (SDK `openai`), `decider` (même contrat, hébergé, `endpoint: null`). Pannes selon AD-13 transposé. Juges cloud : refus des questions privées avant tout envoi, coût par ligne et par lot, plafond obligatoire vérifié avant chaque essai.

**Serveur du juge local.** Décision d'Anaël retenue : Winnow-E4B (GGUF Q8_0) importé dans Ollama 0.40.2 comme modèle `decision`, étiquette `winnow-e4b`. Mesures de VRAM, de déport en CPU et de tenue en français **non faites** (accès au dépôt et sonde de `/v1/systemone` refusés par les permissions de la session) ; procédure manuelle en 8 étapes dans `juge-et-calibration.md`, non exécutée.

**Contrat `/v1/systemone` retenu (hypothèse).** Voir Design Notes : requête `{model, messages, questions: [{id, type: "noul", question}]}`, réponse `{model, answers: [{id?, type, noul}], usage: {prompt_tokens, completion_tokens}}`, appariement par `id` chaîne sinon par position. Confirmés par la revue d'actualité du spine : chemin, réponse `noul`, enveloppe, 1 à 256 questions.

**Prix relevés le 2026-10-12.** Haiku 5.5 : 0,10 $ / 0,50 $ par M (≤ 100 000 tokens d'entrée), 0,50 $ / 2,50 $ au-delà, −50 % en lot (https://platform.claude.com/docs/en/about-claude/pricing). MiMo-V2.6-Pro : 0,435 $ / 0,87 $, cache 0,0036 $ (blog LiteLLM « Day 0 Support: Xiaomi MiMo V2.6 » et agrégateurs ; page officielle non atteinte). Decider : 0,02 $ / 0 $ (agrégateurs, 2026-10-07, non revérifiés).

**Essai réel (campagne jetable `trial-judge-20261012`, 2 questions publiques, une bonne et une mauvaise réponse chacune, 20 critères par juge, plafond 0,25 $).** Haiku : un lot, 20 verdicts, 0 erreur, 19 205 tokens d'entrée et 200 de sortie, 0,0010 $. MiMo : 20 verdicts, 0 erreur, 0,0060 $. Les deux juges rendent les 20 mêmes verdicts, tous conformes à l'attendu. Total 0,0070 $.

**Fichiers.**
- `scripts/quality_bench/judge/{__init__,base,prompt,pricing,units,systemone,decider,haiku,mimo,commands}.py` -- phase de jugement.
- `scripts/quality_bench/judges.yaml` -- quatre juges, réglages, prix datés.
- `scripts/quality_bench/common/{config,schemas,paths}.py` -- `load_judges`, `qb.batch/1`, `judges_config_path`.
- `scripts/quality_bench/__main__.py` -- sous-commande `judge`.
- `scripts/quality_bench/requirements.txt` -- `anthropic>=1.13.0`, `openai>=3.28.0` (installés : 1.13.0, 3.29.0).
- `tests/quality_bench/{judge_fakes,test_judge_command,test_judge_cloud,test_judge_config,test_judge_imports}.py`, `conftest.py`, `test_package.py` -- tests.
- `.env.example`, `juge-et-calibration.md`, `deferred-work.md` -- documentation.

**Revue.** 35 lignes (41 constats des relecteurs, doublons regroupés, + 7 d'intention) : 24 patchées (2 high, 6 medium, 16 low) ; rejetées : 5 d'intention (exclues par l'orchestrateur ou déjà satisfaites), B9, E8, E13 (low non triviaux ou sans dommage établi), E12, E15, E17 (faux). Rien de différé hors des entrées de `deferred-work.md`.

**Revue de suivi recommandée : oui.** Patchés : 2 high (relance après épuisement Haiku, 401/403/404 qui empoisonnaient la campagne) et 6 medium. Risque non vérifié nommé : la reprise des lots Haiku (comptage des essais par lancement contre historique, soumission non relancée) n'a été éprouvée que sur faux client.

**Vérification.** `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` : 1 181 verts (1 082 avant la story). `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 verts. Essai réel Haiku et MiMo : voir ci-dessus.

**Risques résiduels.** Contrat `/v1/systemone` jamais confronté au serveur réel ; Winnow jamais chargé sur la RTX 3050 (8,01 Go sur 8 Go) ; point d'accès de Decider inconnu ; coût total d'un juge Haiku à lire dans `batches.jsonl` (lignes `collected`), pas en sommant `judgment.jsonl` ; réflexion de Haiku quasi nulle à `effort: low` (à juger à la calibration).
