---
title: "Un juge note chaque réponse, et « non évalué » n'est jamais 0 (serveur)"
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '8cefd9a'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-4.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-1.md'
warnings: []
deferred:
  - summary: >-
      Passe serveur seulement : le panneau « Critères de notation » (replié), l'affichage de la note, de l'avertissement « note peu fiable » et de l'étiquette « un seul juge », le badge Local ou Cloud du juge et son sélecteur sont à faire dans une seconde passe, après la fusion de l'écran Arène (story 3.2). Le serveur expose tout ce qu'il leur faut (événements `judge`, `judge_score`, `lane_status: judging`, paramètres `judge` et `criteria`).
    evidence: |-
      `contrat-api.md` (lignes `judge` et `judge_score` des « Événements de run », ligne Arène des écrans) ; `web/test_arena_judge_api.py`.
    location: src/wavelocalai/web/static/screens/arena.js
    severity: medium
  - summary: >-
      Ajouts au contrat d'API, à valider avec la story 3.6 : l'événement `judge` (juge retenu, `unreliable`, `single_judge`, `default_criteria`), la clé `judge` de `judge_score`, le code d'erreur `invalid_output` (502, sortie structurée non conforme au schéma) et `LANE_STATUSES` qui compte `judging`. `judging` ne précède que les réponses réellement notées (pas de `judging` pour une réponse vide ni sans juge).
    evidence: |-
      `contrat-api.md` ; `test_each_finished_lane_is_judged_then_done_and_the_judge_is_a_silent_child`, `test_an_empty_answer_is_not_evaluated_and_never_zero`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Une lane en `timeout`, `failed` ou `cancelled` n'a pas de `judge_score` (la notation ne porte que sur une lane terminée) ; l'écran et le classement (3.4) lisent son statut de lane pour dire « non évalué ». Le juge n'est jamais relancé (pas de `retry_interrupted`) et la réponse est tronquée à 12 000 caractères pour lui ; un seul juge, sans panel (« un seul juge » est toujours vrai tant que le panel n'existe pas).
    evidence: |-
      `src/wavelocalai/evaluation/judge.py` (`MAX_ANSWER_CHARS`), `test_invalid_or_unavailable_judge_gives_null_with_a_reason_never_zero`.
    location: src/wavelocalai/evaluation/judge.py
    severity: low
  - summary: >-
      Le validateur de sortie structurée est minimal (type, required, properties, additionalProperties, enum, minimum, maximum, items) parce que `jsonschema` n'est qu'une dépendance de développement. Les schémas plus riches (`oneOf`, `$ref`, `pattern`) ne sont pas vérifiés : à étendre si un service en a besoin (Self-RAG, évaluation).
    evidence: |-
      `tests/v2/unit/test_structured_output.py`.
    location: src/wavelocalai/models/structured.py
    severity: low
  - summary: >-
      Le schéma est envoyé en mode `strict` à OpenAI seulement ; Groq et Mistral le reçoivent sans garantie de conformité stricte (Mistral en `strict: true`, Groq non strict : tous ses modèles ne supportent pas `json_schema`), d'où la vérification côté serveur. Les adaptateurs cloud n'ont pas été éprouvés contre les vrais services dans cette passe (aucun appel payant) : les corps de requête le sont contre les vrais SDK avec un faux transport.
    evidence: |-
      `test_openai_compatible_sends_json_schema_response_format`, `test_mistral_sends_json_schema_and_validates`, `test_anthropic_forces_a_tool_carrying_the_schema_and_returns_its_json`.
    location: src/wavelocalai/models/openai_compat.py
    severity: low
---

# Story 3.3 : un juge note chaque réponse, et « non évalué » n'est jamais 0 (serveur)

## Objectif

Chaque lane terminée de l'Arène est notée sur 100 par un modèle juge, avec sa raison. Quand la note est impossible (réponse vide, juge en panne, sortie invalide), `score` vaut `null` et la raison le dit : jamais 0. Le serveur dit aussi quand la note est peu fiable. Côté serveur seulement (l'écran est la seconde passe, après la 3.2).

## Critères d'acceptation et preuves

1. `response_schema` du port `ChatModel` : Ollama le passe en `format`, Anthropic en `tool_use` forcé (l'entrée de l'outil `respond` est émise comme texte de réponse), OpenAI et Groq en `response_format` `json_schema` (`strict` pour OpenAI), Mistral en `json_schema`. Chaque adaptateur vérifie la sortie à la fin du flux (`StructuredCheck`) et lève `ProviderError("invalid_output")` sans `Done` si elle ne respecte pas le schéma. Preuve : `unit/test_structured_output.py` (un test par adaptateur, faux transports sous les vrais SDK, cas valide et invalide).
2. Le service `evaluation/judge.py` note la réponse de chaque lane `ok` : feuille `judge` enfant de l'Arène (mesurée par CodeCarbon sous la place Ollama pour un juge local ; `carbon_updated` après), appel **silencieux** (`stream_into_run(capture=…)` : ni `token`, ni `metrics`, ni `model_loading`, ni `retry` dans le flux, dont les `lane` sont les modèles comparés). L'Arène publie `lane_status: judging`, puis `judge_score {lane, score, reason, judge}`, puis `done`. Les critères viennent de l'événement `question` (par défaut exactitude, pertinence, clarté). Preuve : `web/test_arena_judge_api.py::test_each_finished_lane_is_judged_then_done_and_the_judge_is_a_silent_child`, `test_default_criteria_are_sent_when_none_are_given`, `test_a_judge_that_is_also_a_lane_keeps_that_lanes_own_metrics`.
3. Réponse vide : `score: null`, « non évalué : réponse vide », le juge n'est pas appelé. Juge en panne, délai ou clé absente, ou aucun juge : « non évalué : juge indisponible ». Sortie non JSON ou hors schéma : « non évalué : sortie du juge invalide ». Jamais 0 ; la lane finit `done` et l'Arène `ok`. Preuve : `test_an_empty_answer_is_not_evaluated_and_never_zero`, `test_invalid_or_unavailable_judge_gives_null_with_a_reason_never_zero`, `test_without_any_judge_scores_are_not_evaluated`.
4. Défaut `judge` (règle de `models/defaults.py`, plus gros local qui tient) quand `judge` est absent ; l'événement `judge` (publié après `question`) dit le juge retenu, `unreliable` (juge local de moins de ~4 milliards de paramètres actifs ou de taille inconnue, via `is_weak_judge`), `single_judge` et `default_criteria`. `runs.params.judge` garde le juge réellement retenu. Preuve : `test_the_default_judge_is_used_and_a_small_one_is_flagged_unreliable`, `test_a_large_judge_is_not_flagged_and_unknown_size_counts_as_small`.
5. `judge` et `criteria` se règlent par `POST /api/arena/runs`. Le cloud n'est jamais le juge sans `allow_cloud` : un juge cloud nommé est refusé (`cloud_not_allowed`) avant tout run ; un défaut cloud est refusé par le registre et donne « aucun juge », jamais un repli silencieux. Avec `allow_cloud`, le juge cloud passe sans la place Ollama. Preuve : `test_a_cloud_judge_is_never_chosen_without_allow_cloud`, `test_a_cloud_judge_with_allow_cloud_runs_in_parallel_without_the_slot`.
6. Annuler l'Arène pendant une notation annule la lane (`cancelled`) et la feuille `judge`, libère la place, sans note à 0. Preuve : `test_cancelling_during_judging_cancels_the_lane_and_the_judge_leaf`.
7. Avec le vrai `qwen2.5:1.5b` : une note entière de 0 à 100 et une raison par lane, `unreliable` vrai (1,5 milliard), feuilles `judge` mesurées par CodeCarbon. Preuve : `integration/test_judge_ollama.py` (marqueur `integration`).

## Fichiers

- `src/wavelocalai/models/structured.py` (nouveau) : `parse_structured`, `StructuredCheck`, validateur minimal ; `models/{ollama,openai_compat,mistral,anthropic}.py` : `response_schema` ; `errors.py` : `invalid_output`
- `src/wavelocalai/evaluation/judge.py` (nouveau) : `Judge`, `build_request`, `JUDGE_SCHEMA`
- `src/wavelocalai/inference/judge_port.py` (nouveau) : `LaneJudge`, `JudgeVerdict`, raisons « non évalué » (`inference/` n'importe pas `evaluation/` : le service est câblé dans `web/app.py`)
- `src/wavelocalai/inference/arena.py` : juge par défaut, événement `judge`, `_judge_lane`, enveloppe d'enregistrement de la réponse ; `inference/streaming.py` : `capture` (appel silencieux) ; `models/defaults.py` : `is_weak_judge`
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md` : événements `judge` et `judge_score`, paramètres de lancement
- Tests : `unit/test_structured_output.py`, `web/test_arena_judge_api.py`, `integration/test_judge_ollama.py` ; `web/test_arena_api.py` (feuilles `judge`) et `integration/test_arena_ollama.py` (juge nommé) réalignés

## Reports

Voir `deferred` : écran (seconde passe, après la 3.2), contrat à valider en 3.6, lanes sans note, validateur minimal, cloud non éprouvé en réel.
