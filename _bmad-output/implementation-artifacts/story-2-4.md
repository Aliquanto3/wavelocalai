---
title: 'Converser avec un modèle cloud (OpenAI, Groq, Anthropic, Mistral)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '26dfdc8'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-5.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-1.md'
warnings: []
deferred:
  - summary: >-
      Le CO2 d'une réponse cloud reste « non mesurable » (raison « mesure non branchée ») : l'estimation ecologits et la table Groq sont la story 2.5.
    evidence: |-
      `test_cloud_chat_streams_without_the_local_slot_and_marks_the_run_as_cloud` (champ `co2` présent, `mg` nul, raison).
    location: src/wavelocalai/inference/streaming.py
    severity: low
  - summary: >-
      Les adaptateurs cloud n'envoient ni outils (`ToolCall`), ni `response_schema`, ni `think` : les messages `tool` sont écartés. Les agents et le juge (étapes suivantes) les brancheront ; aucun chemin actuel ne les produit.
    evidence: |-
      `models/cloud.py::chat_text_messages`, `models/anthropic.py::_split_messages`.
    location: src/wavelocalai/models/
    severity: low
  - summary: >-
      Identifiants de modèles de `wavelocalai.toml` revérifiés dans la documentation officielle (2026-10-18). Retirés : `gpt-4o` et `gpt-4o-mini` (dépréciés, arrêt le 2027-01-14, alias nus non listés) et `mistral-medium-latest` (alias non confirmé). Ajoutés : `gpt-6-sol`, `gpt-6-luna` (OpenAI), `mistral-small-latest` (exemple de la référence de l'API). Confirmés tels quels : les 4 modèles Groq et les 3 Claude. Les préférences de juge de `models/defaults.py` (`CLOUD_JUDGE_PREFERENCE`) nomment encore `gpt-4o` et n'ont pas été touchées (hors périmètre) ; la table `groq_ecologits` reste à confirmer en 2.5.
    evidence: |-
      `wavelocalai.toml` (commentaire daté) ; pages de modèles OpenAI et Anthropic, Groq, référence de l'API Mistral.
    location: wavelocalai.toml
    severity: medium
  - summary: >-
      Les modèles OpenAI `gpt-5*`/`gpt-6*`/`o*` sont appelés sans `temperature` (règle de l'adaptateur) : la documentation lue ne dit pas s'ils la refusent. À confirmer par un appel réel (hors tests, une clé est nécessaire). Idem pour `Mistral` : `temperature` est envoyée.
    evidence: |-
      `test_openai_request_body_headers_and_usage`, `test_openai_non_reasoning_model_gets_the_temperature`.
    location: src/wavelocalai/models/openai_compat.py
    severity: low
  - summary: >-
      Versions des SDK : installées et verrouillées `openai 2.54.0`, `anthropic 1.15.0`, `mistralai 3.2.0` ; PyPI le 2026-10-18 donne `openai 3.35.1` (publiée le jour même), `anthropic 1.15.0`, `mistralai 3.2.0`. `openai` n'est pas monté (version de moins de 2 semaines, `uv.lock` partagé avec la v1) ; les planchers de `pyproject.toml` (`openai>=1.50.0`, `mistralai>=1.0.0`, `anthropic>=1.15.0`) ne sont pas touchés, l'adaptateur Mistral repère `Mistral` dans `mistralai.client` puis `mistralai`. Anthropic et Mistral dépendent de `httpx2`, `openai` de `httpx` : les tests simulent chaque transport avec la bonne bibliothèque.
    evidence: |-
      PyPI (JSON) et `uv pip list` du worktree ; `tests/v2/fake_cloud.py`.
    location: pyproject.toml
    severity: low
  - summary: >-
      Un modèle cloud déclaré dans `[cloud.models]` mais sans clé se résout maintenant (`registry.resolve`, après `cloud_not_allowed`) pour que l'appel dise `cloud_key_missing` et où mettre la clé ; la liste `GET /api/models` ne le propose toujours pas. Avant, il rendait `model_not_found`.
    evidence: |-
      `test_a_declared_cloud_model_without_key_resolves_but_is_never_listed`, `test_missing_key_ends_the_run_in_cloud_key_missing_without_any_call`.
    location: src/wavelocalai/models/registry.py
    severity: low
---

# Story 2.4 : converser avec un modèle cloud (OpenAI, Groq, Anthropic, Mistral)

## Objectif

Le chat de la story 2.1 accepte un modèle cloud quand `allow_cloud` est vrai : le même `POST /api/chat/runs` et le même flux d'événements, avec des erreurs qui nomment le fournisseur. Côté serveur seulement (l'écran est la story 2.2, le CO2 cloud la 2.5).

## Critères d'acceptation et preuves

1. Adaptateurs sur les SDK officiels, importés dans la fonction (AD-4) : `models/openai_compat.py` (OpenAI, et Groq par `base_url` `https://api.groq.com/openai/v1`), `models/anthropic.py` (événements bruts de `messages`), `models/mistral.py` (`chat.stream_async`). Streaming repris de `src/core/providers/` et du harnais `wavestack`, sans `get_langchain_model`. Ils émettent `TextDelta` (raisonnement sur le canal `thought`) puis un seul `Done` avec `tps_source = "wallclock"` (débit `(jetons - 1) / (fin - premier fragment)`), ne calculent pas de CO2, n'écrivent pas en base et ne lisent pas `allow_cloud` ; flux et client fermés dans un `finally`, annulation comprise. Preuve : `unit/test_cloud_adapters.py` (4 fournisseurs sous leur vrai SDK, faux transport HTTP : flux nominal, corps et en-têtes, usage, annulation) ; `unit/test_layers.py` (import paresseux).
2. `allow_cloud: true` : l'appel part sans prendre le sémaphore local, `metrics.origin = "cloud"` (le badge Cloud lit ce champ), `co2` « non mesurable » avec sa raison. Preuve : `web/test_chat_cloud_api.py::test_cloud_chat_streams_without_the_local_slot_...` et `test_cloud_call_is_not_blocked_by_a_busy_local_slot` (4 fournisseurs).
3. Pannes dans `run_ended.data.error` : `cloud_key_missing` (variable de `.env` à renseigner, aucun appel), `cloud_key_refused` (401/403), `cloud_rate_limited` (429), `cloud_error` (autres refus), `cloud_unreachable` (nomme le fournisseur, propose de repasser en Local), `generation_interrupted` (flux coupé en route, relancé une fois par le service). Codes en fin de liste de `errors.py`, `message` et `action` avec `{provider_name}` / `{key_var}` remplis par `build_envelope` depuis `detail`. Aucune clé dans `detail`, les événements, l'instantané ni les journaux (fausses clés `sk-…`, `sk-ant-…`, `gsk_…`, le fournisseur renvoie la clé dans son message). Preuve : `test_missing_key_...`, `test_refused_key_...`, `test_unreachable_provider_...`, `test_a_rate_limited_provider_...`, `test_no_key_in_logs_...`, `unit/test_errors.py::test_cloud_codes_...`.
4. `allow_cloud` absent ou faux : `cloud_not_allowed` (403) sans client ni appel, pour chacun des 4 fournisseurs. Preuve : `test_cloud_model_without_allow_cloud_is_refused_and_the_provider_is_never_called`. Côté écran, le sélecteur de la story 1.10 retire déjà le modèle cloud choisi quand le cloud est coupé, le dit en texte et propose le défaut local (aucun changement de front) : E2E `test_picker.py::test_turning_the_cloud_off_removes_a_cloud_choice_says_so_and_proposes_the_local_default` et `test_multi_cloud_choice_is_removed_and_the_others_stay`.
5. Un second tour renvoie toute la conversation au fournisseur. Preuve : `test_a_second_turn_resends_the_history_to_the_provider`.

## Fichiers

- `src/wavelocalai/models/` : `cloud.py` (socle : erreurs, chronomètre, raccord de test), `openai_compat.py`, `anthropic.py`, `mistral.py`, `factory.py` (clés de `Settings`, `cloud_http`), `registry.py` (résolution d'un modèle déclaré sans clé)
- `src/wavelocalai/errors.py` : `cloud_key_missing`, `cloud_key_refused`, `cloud_unreachable`, `cloud_rate_limited`, `cloud_error` en fin de liste ; textes à `{clé}`
- `src/wavelocalai/web/app.py` : `create_app(cloud_http=...)`
- `wavelocalai.toml` : identifiants de modèles cloud revérifiés
- Tests : `tests/v2/fake_cloud.py`, `unit/test_cloud_adapters.py`, `web/test_chat_cloud_api.py`, `unit/test_errors.py`, `unit/test_registry.py`

## Revue

Revue Opus du 2026-10-18 (une passe), avec la liste du second avis (Haiku).

- medium, second avis 1 — corrigé : une erreur annoncée dans le flux SSE d'OpenAI ou de Groq (`openai.APIError` sans statut HTTP) n'était pas traduite et finissait en `internal`. `translate_error` la range en `cloud_error` (`_SDK_ERROR_NAMES`). Prouvé avant/après par `test_an_error_event_inside_the_stream_is_cloud_error` (4 fournisseurs ; Anthropic et Mistral donnaient déjà `cloud_error`).
- medium, second avis 2 — rejeté (pas de fuite), test ajouté : le journal passe par `MaskingFormatter`, que `__main__` règle avec `Settings.secret_values()` (trace d'exception comprise), et `_error_envelope` masque `technical` avec les mêmes valeurs (`chat.py`). Une clé Mistral sans préfixe est donc masquée. Preuve : `test_unexpected_error_log_and_envelope_mask_a_raw_mistral_key`.
- low, second avis 3 — corrigé : `constraints.txt` donnait `mistralai==2.10.1` contre `3.2.0` dans `uv.lock` (écart antérieur à la story, venu de 73311f6). Recompilé avec `uv pip compile … --upgrade-package mistralai==3.2.0` : seule cette version change. `openai==2.54.0` concordait déjà.
- low, second avis 4 — corrigé : `CLOUD_JUDGE_PREFERENCE` (v2) nomme `gpt-6-sol` à la place de `gpt-4o` et `gpt-6-luna` (palier économique) à la place de `gpt-4-turbo`. `src/core/` n'est pas touché.
- low, second avis 5 — reporté : l'omission de `temperature` pour `gpt-5*`/`gpt-6*`/`o*` est documentée dans le module et dans les reports. À vérifier par un appel réel avec une clé OpenAI (le modèle accepte-t-il `temperature`).
- low, second avis 6 — rejeté : la relance unique après coupure est exigée par le critère 3 (`generation_interrupted`, reprise de la v1) ; le coût d'un second appel est accepté par la spec.
- low, revue — reporté : les erreurs dans le flux et le comportement réel des 4 API (corps, en-têtes, `stream_options`, `max_completion_tokens` chez Groq) ne sont prouvés que sous faux transport. À vérifier par un appel réel par fournisseur, avec une clé.
