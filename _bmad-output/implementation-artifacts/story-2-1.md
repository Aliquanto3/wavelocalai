---
title: 'Converser en flux avec un modèle Ollama (serveur)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '89e20e1'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-3.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-5.md'
warnings: []
deferred:
  - summary: >-
      Le code d'erreur de la génération coupée deux fois s'appelle `generation_interrupted`, pas `interrupted` comme le dit le texte de la story 2.1 : AD-5 interdit qu'un code d'erreur reprenne un nom de statut (`interrupted` en est un). La spine prime ; `epics.md` (story 2.1) et le front de la story 2.2 doivent lire `generation_interrupted`.
    evidence: |-
      `tests/v2/unit/test_errors.py::test_chat_codes_are_declared_and_none_reuses_a_status_name`.
    location: src/wavelocalai/errors.py
    severity: medium
  - summary: >-
      Aucun adaptateur cloud : `ModelFactory.chat_model` lève `internal` pour un fournisseur autre qu'Ollama (modèle cloud listé avec `allow_cloud=true` puis choisi). Les adaptateurs cloud, leur flux et le CO2 ecologits viennent avec leurs stories.
    evidence: |-
      `src/wavelocalai/models/factory.py`.
    location: src/wavelocalai/models/factory.py
    severity: low
  - summary: >-
      Le CO2 d'une feuille est `unmeasurable` (raison « mesure non branchée ») : CodeCarbon est la story 2.3, qui s'ouvre et se ferme dans la place du `LocalSlot`.
    evidence: |-
      `test_nominal_chat_streams_tokens_then_metrics_and_stores_both_messages` (champ `co2` présent partout, AD-10).
    location: src/wavelocalai/inference/streaming.py
    severity: low
  - summary: >-
      `LoadState("loaded").duration_s` est le délai jusqu'au premier fragment (chargement et lecture du prompt compris) : l'API d'Ollama ne donne `load_duration` qu'au fragment final, où il reste exact dans `metrics.load_s`. Le débit de lecture du prompt (prefill) n'a pas de champ dans `ChatResult` (figé par AD-8) : seul `input_tokens` est exposé.
    evidence: |-
      Docstring de `models/ollama.py` ; `test_loading_is_announced_...`.
    location: src/wavelocalai/models/ollama.py
    severity: low
  - summary: >-
      Ollama arrêté, `ollama_down` arrive après 2 à 3 s sous Windows (un refus de connexion locale met ~2 s à échouer) ; la sonde `/api/ps` du chargement échoue déjà sur le refus et évite un second essai. Le message assistant d'un run en erreur ou annulé garde son texte partiel, et le tour suivant le renvoie au modèle dans l'historique.
    evidence: |-
      `test_ollama_stopped_ends_in_ollama_down` (délai de 10 s) ; `test_cancelling_closes_the_http_stream_and_keeps_the_partial_answer`.
    location: src/wavelocalai/models/ollama.py
    severity: low
  - summary: >-
      `registry.resolve` ne lit que la dernière liste connue : au tout premier lancement, avant le premier rafraîchissement (< 1 s), un tag installé donne `model_not_found`. L'écran de la story 2.2 liste les modèles avant d'envoyer, ce qui laisse le temps au cache.
    evidence: |-
      Comportement hérité de la story 1.5, non modifié ici.
    location: src/wavelocalai/models/registry.py
    severity: low
  - summary: >-
      Le test `integration` sur `qwen2.5:1.5b` n'a pas tourné sur le poste de développement : le modèle n'y est pas installé (Ollama y servait un autre modèle de 26 Go, rien n'a été chargé). Il est écrit, marqué `integration`, et saute proprement.
    evidence: |-
      `pytest tests/v2 -m integration -rs` : 1 sauté (« qwen2.5:1.5b n'est pas installé »).
    location: tests/v2/integration/test_chat_ollama.py
    severity: low
---

# Story 2.1 : converser en flux avec un modèle Ollama (serveur)

## Objectif

`POST /api/chat/runs {conversation_id?, model, message, temperature, allow_cloud}` rend `{run_id, conversation_id}` aussitôt et lance la réponse d'un modèle Ollama en flux, avec le débit fidèle à Ollama (D3). Côté serveur seulement : le front du chat est la story 2.2.

## Critères d'acceptation et preuves

1. Adaptateur `models/ollama.py` (`OllamaChatModel`, `/api/chat` natif, `AsyncClient` partagé sur `http://127.0.0.1:11434`, `trust_env=False`) : `LoadState("loading"|"loaded", duration_s)` (annoncé si `/api/ps` ne montre pas le modèle en mémoire, `loaded` avant le premier jeton), `TextDelta` (`answer` / `thought`), `ToolCall`, un seul `Done(ChatResult)` avec `tps = eval_count / eval_duration`, `tps_source = "ollama_eval"`, `load_s`, `ttft_s`, `eval_s`, `total_s`, jetons entrée/sortie. `models/ollama_metrics.py` copie et adapte `ollama_metrics` de la v1 (génération et prefill séparés, repli `wallclock` marqué). Preuve : `test_ollama_adapter.py` (flux nominal, corps de requête, chargement, repli, bornes de `ollama_result`).
2. Annulation : la tâche annulée ferme le flux HTTP dans un `finally`. Refus d'Ollama : `ProviderError(code)` (`ollama_down`, `model_not_found`, `ollama_error`, `generation_interrupted`). Preuve : `test_cancelling_the_task_closes_the_http_stream`, `test_closing_the_generator_early_...`, `test_ollama_refusals_become_provider_errors_...`, `test_a_stream_cut_before_done_is_generation_interrupted`.
3. Route : le hub crée la conversation `chat` et le message utilisateur ; `inference/chat.py` obtient le modèle par `registry.resolve(tag, allow_cloud)` seulement ; flux `run_started`, `model_loading` / `model_loaded`, `token` (`lane` = tag), `metrics` (avec `co2` non mesurable et sa raison), `run_ended` ; le hub écrit le message assistant (raisonnement à part) ; `runs.params` ne porte que `temperature` et `allow_cloud`. Un second tour reprend toute la conversation (`RunHub.conversation_messages`). Preuve : `web/test_chat_api.py` (nominal, reprise, modèle inconnu / cloud sans accord / message vide, `run_busy` avec le `run_id` actif, origine étrangère, `fake` en mode test).
4. Sémaphore « Ollama local » à 1 (`inference/local_slot.py`), pris par appel et non par run, rendu à l'annulation ; un appel cloud n'y passe pas. Preuve : `test_chat_service.py::test_two_local_calls_run_one_after_the_other_...` (`fake` puis faux client Ollama), `test_an_interrupted_generation_is_retried_...` (deux prises pour un run), `test_a_cloud_call_...`, `test_cancelling_a_run_...`.
5. Coupure avant la fin : un `retry` (lane, raison, tentative) puis relance unique, le texte partiel étant retiré du message assistant (le hub l'efface au `retry`) ; seconde coupure : `error` avec `generation_interrupted`. Ollama arrêté : `ollama_down` sans relance. Délai dépassé : `timeout` avec `timeout_s` de `Settings.delays.lane_timeout_s`, compté depuis la prise de la place (local). Preuve : `test_a_cut_generation_is_retried_once_then_succeeds`, `test_a_generation_cut_twice_...`, `test_ollama_stopped_ends_in_ollama_down`, `test_a_delay_exceeded_ends_in_timeout_...`, `test_the_local_delay_starts_at_slot_acquisition_...`. Test réel : `integration/test_chat_ollama.py` (saute si Ollama ou `qwen2.5:1.5b` manque).

## Fichiers

- `src/wavelocalai/models/` : `ollama.py`, `ollama_metrics.py`, `factory.py`, `registry.py` (`extra_refs` pour le `fake` en mode test)
- `src/wavelocalai/inference/` : `chat.py`, `local_slot.py`, `streaming.py` (place, délai, relance unique)
- `src/wavelocalai/runs/` : `hub.py` (`conversation_messages`, effacement du partiel au `retry`), `models.py`
- `src/wavelocalai/web/` : `routes_chat.py`, `app.py` (client Ollama partagé, service, `LocalSlot`)
- `src/wavelocalai/errors.py` : `timeout`, `generation_interrupted`, `ollama_error` en fin de liste
- Tests : `tests/v2/fake_ollama.py`, `unit/test_ollama_adapter.py`, `unit/test_chat_service.py`, `unit/test_errors.py`, `web/test_chat_api.py`, `integration/test_chat_ollama.py`
