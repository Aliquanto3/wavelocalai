---
title: 'Chaque usage a un modèle par défaut, avec sa raison'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'cf78d71'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-5.md'
warnings: []
deferred:
  - summary: >-
      La table `preferences` (migration `0003_preferences.sql`) existe mais rien ne l'écrit encore : `PreferenceStore` est une interface injectable avec une implémentation en mémoire (`InMemoryPreferenceStore`, `create_app(preferences=...)`), parce que le store SQLite du hub (story 1.3) n'est pas fusionné. À brancher : `SqlitePreferenceStore` (écrivain unique du store) sur `0003_preferences.sql`, clé `default_model.<usage>`, valeur `{"tags": [...]}`. Sans cela, une préférence ne survit pas à un redémarrage.
    evidence: |-
      `create_app` construit `ModelDefaults(registry, preferences or InMemoryPreferenceStore())`.
    location: src/wavelocalai/web/app.py
    severity: medium
  - summary: >-
      Aucune route d'écriture d'un défaut choisi (`PUT /api/models/defaults/{purpose}` ou équivalent) : les critères ne portent que sur la lecture et la priorité de la préférence. Elle viendra avec l'UI de sélection de modèle (epic 2/3), derrière le contrôle d'origine des écritures.
    evidence: |-
      `ModelDefaults` ne lit que `preferences` et ne l'écrit jamais (test).
    location: src/wavelocalai/web/routes_models.py
    severity: low
  - summary: >-
      Les règles qui s'appuient sur la précision mesurée (juge d'après `accuracy`) sont écrites mais sans effet tant que `qb.results/1` n'alimente pas `ModelInfo.accuracy` (étape 5) ; de même le débit ne vient de `RunStats` que lorsque le store est branché (report de 1.5). Sans débit mesuré, `chat` et `arena` départagent par la plus petite empreinte (la v1 faisait de même).
    evidence: |-
      `ModelInfo.accuracy` vaut toujours `null` ; `throughput_tps` vide sans run.
    location: src/wavelocalai/models/defaults.py
    severity: low
  - summary: >-
      Les usages `agent` et `rag` n'ont pas de règle dans la v1 (`agent_default` exigeait le benchmark du poste, `rag` n'existait pas) : règles posées ici sur les données du registre (outils vérifiés et ≥ 3 milliards de paramètres actifs pour `agent`, ≥ 3 milliards pour `rag`, repli sur le défaut de `chat` avec la raison dite). Seuils à confirmer avec les mesures du banc.
    evidence: |-
      `AGENT_MIN_PARAMS_B`, `RAG_MIN_PARAMS_B` dans `models/defaults.py`.
    location: src/wavelocalai/models/defaults.py
    severity: low
  - summary: >-
      Le test `integration/test_defaults_ollama.py` (et `test_models_ollama.py`) demande un Ollama joignable et se saute proprement sinon ; il a passé une fois contre le vrai Ollama du poste pendant cette story, mais Ollama peut être arrêté ou saturé ensuite : à rejouer avec Ollama (`pytest tests/v2 -m integration`). Les tests unitaires et web, sans réseau, suffisent à la preuve.
    evidence: |-
      `pytest tests/v2 -m integration` : 3 passed, avec Ollama.
    location: tests/v2/integration/test_defaults_ollama.py
    severity: low
---

# Story 1.6 : chaque usage a un modèle par défaut, avec sa raison

## Objectif

`GET /api/models/defaults?purpose=chat|arena|judge|agent|rag[&allow_cloud=true]` rend `{purpose, tags, reason, source}` : les tags du défaut (un seul, sauf `arena` : 2 ou 3), une raison en français affichable en aide, et `source` (`rule` ou `preference`). Les règles de `src/core/model_defaults.py` sont copiées puis adaptées dans `models/defaults.py` ; elles portent sur les `ModelInfo` du registre (catalogue déjà fusionné), sans `config`, sans `models_db`, sans import de `src.*`.

## Critères d'acceptation et preuves

1. Règles copiées et adaptées, jamais importées : `models/defaults.py` ne lit aucun fichier et n'importe que le paquet v2. Preuve : `tests/v2/unit/test_defaults.py::test_defaults_module_never_imports_the_v1`, `test_layers.py` (vert).
2. Chaque usage rend des tags et une raison en français ; `arena` rend au moins 2 modèles quand ils tiennent ; `judge` est le plus gros modèle local qui tient. Preuve : `web/test_defaults.py::test_every_purpose_returns_tags_and_a_reason_in_french`, `unit/test_defaults.py::test_chat_picks_the_*`, `test_arena_*`, `test_judge_*`, `test_agent_*`, `test_rag_*`.
3. Jamais un modèle d'embedding ou de reranker (`test_defaults_are_never_embedding_or_reranker_models`, 5 usages) ; jamais un modèle cloud sans `allow_cloud` (`test_cloud_is_never_a_default_without_allow_cloud`, `web/test_defaults.py::test_cloud_defaults_need_allow_cloud`) ; avec `allow_cloud`, seul `judge` prend un cloud (le plus capable, `CLOUD_JUDGE_PREFERENCE`), et `chat` n'en prend un que sans aucun local.
4. Aucun modèle de conversation : code `no_model` (404) avec message, action et `detail.purpose`. Preuve : `web/test_defaults.py::test_no_chat_model_installed_answers_no_model`, `unit/test_defaults.py::test_no_chat_model_raises_no_model_with_message_and_action`.
5. Préférence : `preferences` (`0003_preferences.sql`, clé `default_model.<usage>`, valeur `{"tags": [...]}`) prime sur la règle pour ce seul usage, pourvu que ses modèles soient encore des modèles de conversation disponibles (cloud interdit sans accord) ; sinon la règle reprend. Le service n'écrit jamais, ni `wavelocalai.toml`. Preuve : `test_a_stored_preference_overrides_the_rule_for_that_purpose_only`, `test_a_preference_for_a_removed_or_forbidden_model_is_ignored`, `test_the_service_never_writes_preferences`, `test_preferences_migration_creates_a_key_value_table`.
6. Budget : la route (`purpose` vaut `chat` par défaut, elle entre donc d'elle-même dans le test de budget de 1.2) répond en moins de 300 ms Ollama arrêté, depuis le cache du registre. Preuve : `web/test_defaults.py::test_ollama_down_answers_from_cache_under_300_ms`, `test_read_budget.py`. Test `integration` contre le vrai Ollama : `integration/test_defaults_ollama.py`.

## Fichiers

- `src/wavelocalai/models/defaults.py` (règles pures, `ModelDefaults`), `src/wavelocalai/store/preferences.py` (`PreferenceStore`, version en mémoire), `src/wavelocalai/store/migrations/0003_preferences.sql`
- `src/wavelocalai/web/routes_models.py` (route), `web/app.py` (`create_app(preferences=...)`, `app.state.defaults`)
- `src/wavelocalai/errors.py` : `no_model` en fin de liste
- `tests/v2/` : `unit/test_defaults.py`, `web/test_defaults.py`, `integration/test_defaults_ollama.py`

## Choix notables

- Le registre n'est lu que par `list_models` : empreinte (`needed_gb`), `fits`, débit mesuré, outils vérifiés, paramètres actifs et précision viennent de `ModelInfo`. Le raisonnement « dédié » se relit sur le tag et le nom (`is_dedicated_reasoning`), pas sur `ModelInfo.reasoning` qui inclut les hybrides.
- Débit et empreinte ne se mêlent jamais dans un même tri : le débit mesuré sert s'il existe pour tous les locaux qui tiennent, sinon l'empreinte (règle de la v1).
- `arena` ne rend que des locaux ; si moins de 2 tiennent, elle rend ce qui tient (voire aucun tag) et la raison le dit : le lancement reste désactivé côté UI.
