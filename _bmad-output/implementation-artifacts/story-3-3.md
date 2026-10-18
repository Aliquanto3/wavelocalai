---
title: "Un juge note chaque réponse, et « non évalué » n'est jamais 0 (serveur et écran)"
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
      Écran (seconde passe) : l'avertissement « note peu fiable » vient de l'événement `judge`, donc il n'apparaît qu'au lancement ; avant, le panneau ne donne qu'une aide statique (« moins de 4 milliards de paramètres actifs »), parce que le front ne calcule rien (la règle `is_weak_judge` reste au serveur). Les critères modifiés ne sont pas gardés d'une visite à l'autre (aucun brouillon, contrairement à la question) ; le classement qui lit ces notes est la story 3.4.
    evidence: |-
      `test_a_column_shows_notation_then_its_score_its_reason_and_the_one_judge_label`, `test_the_criteria_panel_is_folded_and_proposes_the_default_judge_and_criteria` (`tests/v2/e2e/test_arena.py`).
    location: src/wavelocalai/web/static/screens/arena-judge.js
    severity: low
  - summary: >-
      Écran : une colonne en `timeout`, `failed`, `cancelled` ou `interrupted` n'a pas de `judge_score` (contrat) ; l'écran lit son statut et affiche « Non évalué » avec « délai dépassé », « échec du modèle », « comparaison arrêtée » ou « comparaison interrompue ». Le même texte devra être repris par le classement (3.4).
    evidence: |-
      `test_not_evaluated_is_said_with_its_reason_and_is_never_zero`.
    location: src/wavelocalai/web/static/components/wl-arena-lane.js
    severity: low
  - summary: >-
      Ajout à la route de test `POST /api/test/arena` (`judge` : tag, origine, script) : elle câble le vrai service de notation avec un juge `fake`, pour les parcours E2E. Elle n'existe qu'avec `WAVELOCALAI_TESTING`.
    evidence: |-
      `src/wavelocalai/web/routes_test.py` ; `tests/v2/e2e/test_arena.py` (`scripted(..., judge=...)`).
    location: src/wavelocalai/web/routes_test.py
    severity: low
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

## Seconde passe : l'écran

Critères de la 3.3 que l'écran Arène (3.2) porte, prouvés par `tests/v2/e2e/test_arena.py` (Edge, clair et sombre, axe-core, 320 px) et `tests/v2/unit/test_arena_static.py`.

- **Panneau « Critères de notation »** (`screens/arena-judge.js`, `details` replié) : critères par défaut exactitude, pertinence, clarté ; au plus 8 de 64 caractères (borne alignée sur `MAX_CRITERIA` et `MAX_CRITERION_CHARS` du serveur) ; ajout, retrait, « Rétablir les critères par défaut », Entrée ajoute sans envoyer ; vides et doublons non envoyés ; envoyés dans `criteria`. Preuve : `test_the_criteria_panel_is_folded_…`, `test_criteria_are_edited_added_up_to_eight_…`, `test_the_panel_opens_and_works_from_the_keyboard`.
- **Juge** : `wl-model-picker` `purpose="judge"` (défaut `judge` du serveur, cloud absent de la liste sans « Autoriser le cloud »), badge Local ou Cloud sous le sélecteur, envoyé dans `judge` ; le résumé du juge retenu (événement `judge`) porte son badge, « un seul juge » et les critères appliqués. Preuve : `test_a_cloud_judge_wears_the_cloud_badge_…`, `test_a_column_shows_notation_then_its_score_…`.
- **Note par colonne** : « 72/100 » et sa raison à l'arrivée de `judge_score` (`wl-arena-lane.setScore`), annoncée poliment (région `aria-live` qui accumule une ligne par note) ; « Non évalué » et sa raison, jamais 0 (réponse vide, juge indisponible, sortie invalide, et pour une colonne en délai, échec ou arrêt, le motif du statut). Preuve : `test_not_evaluated_is_said_…`, `test_an_unavailable_or_invalid_judge_…`, `test_without_any_judge_the_screen_says_so_…`, `test_scores_survive_a_visit_elsewhere_…`.
- **Fiabilité** : « note peu fiable » (badge `unreliable` avec l'icône `warning`, et message du résumé) pour un juge faible ; « un seul juge » à côté de chaque note ; absents d'un « non évalué ». Un juge cloud n'est pas « peu fiable ».
- **CO2 d'un juge cloud** : `evaluation/judge.py` passe `estimate_co2=cloud_estimator(...)` (couches respectées : `evaluation` importe `inference`) ; la feuille `judge` d'un juge cloud est estimée par ecologits, plus « non mesurable ». Preuve : `test_a_cloud_judge_leaf_is_estimated_by_ecologits_not_left_unmeasurable` (échoue sans le correctif).
- Accessibilité et mise en page : focus visible (`summary`, boutons, champs), `aria-label` de chaque critère, aucune couleur en dur (jetons de `tokens.css`, aucun aplat violet sous texte blanc), 320 px sans défilement horizontal, axe-core sans violation (panneau ouvert, notes et « non évalué », onglets ; clair et sombre).

## Reports

Voir `deferred` : écran (seconde passe, après la 3.2), contrat à valider en 3.6, lanes sans note, validateur minimal, cloud non éprouvé en réel.

## Revue

Revue Opus du 2026-10-18 (une passe, diff `8cefd9a..2c6f54f`). Aucun constat medium ou high. Complexité : 0 constat (texte capturé, réponse enregistrée et `StructuredCheck` accumulent puis joignent une fois ; aucun parcours complet par événement).

- low, second avis 1 — `models/anthropic.py` : bloc `tool_use` → `end_turn` dupliqué. Corrigé (sans effet sur le comportement).
- low, second avis 2 — `inference/arena.py` : modèle juge construit après `create_run("arena")`, hors du `try`. Requalifié low : `ModelFactory.chat_model` ne lève pas pour un tag résolu par le registre (constructeurs sans appel). Corrigé quand même : le juge est construit avant la racine.
- low, second avis 3 — `inference/arena.py` : sans service de notation, l'événement `judge`, `runs.params.judge` et `judge_score.judge` nommaient un juge qui ne notait pas. Corrigé : pas de juge annoncé sans service. Test `test_without_a_scoring_service_a_named_judge_is_not_announced` (échoue sans le correctif). En production, le service est toujours câblé (`web/app.py`).
- low, second avis 4 — `models/mistral.py` : `strict: true` envoyé sans essai réel. Reporté (déjà dans `deferred`) : vérifier par un appel réel que Mistral accepte `response_format.json_schema.strict` en flux.
- low, revue — Groq : la sortie structurée `json_schema` avec `stream: true` n'est peut-être pas acceptée par tous les modèles Groq (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile` figurent dans `CLOUD_JUDGE_PREFERENCE`). Reporté : un refus donne « non évalué : juge indisponible », jamais 0 ; à vérifier par un appel réel, sinon demander la notation sans flux ou en `json_object` pour Groq.
- low, revue — `evaluation/judge.py` : 12 000 caractères de réponse peuvent dépasser le `num_ctx` d'un petit juge Ollama, qui tronque alors l'entrée sans erreur. Reporté : les réponses d'Arène restent en général bien plus courtes ; à reprendre si l'on règle `num_ctx` par appel.
- low, revue — un juge local différent des modèles comparés alterne avec eux sous la place Ollama (rechargements). Rejeté pour cette story : conforme à AD-14 (place prise appel par appel) ; optimisation possible en 3.4 (noter après toutes les lanes).

Tests : `tests/v2` 644 réussis, `-m integration` 7 réussis (dont `test_judge_ollama.py`, vrai `qwen2.5:1.5b`).

### Revue de la seconde passe (écran)

Revue Opus du 2026-10-18 (une passe, diff `0dce811..2a8f225`). Complexité : 0 constat (région `aria-live` des notes bornée à 5 lignes, `setJudge` parcourt au plus 5 colonnes à l'événement `judge`, aucun parcours complet par jeton).

- medium, second avis 1 — `wl-arena-lane.js` `interrupt()` : constat requalifié. `judging` ferme déjà la réponse (`#ended`), donc `interrupt()` ne faisait rien : un flux perdu pendant la notation laissait la colonne « Notation » sans note ni « Non évalué » (et non « comparaison interrompue » comme décrit). Corrigé : une colonne `judging` sans `judge_score` passe à « Interrompu » et dit « Non évalué : comparaison interrompue » ; notée, elle passe à « Terminé ». Test `test_a_column_in_notation_when_the_stream_is_lost_says_not_evaluated_interrupted` (échoue sans le correctif). Rattachement au run qui tourne encore côté serveur : reporté, c'est le comportement de l'écran 3.2 pour toute colonne (flux abandonné après plusieurs essais), repris par la reconnexion de la story 4.2.
- low, second avis 2 — `judge_score` rejoués (rechargement, `run_busy` rejoint) annoncés d'un coup. Rejeté : au plus 5 lignes polies, et elles informent qui rejoint un run des notes déjà rendues.
- low, second avis 3 — « Autoriser le cloud » coupé avant la fin du rechargement du sélecteur : juge cloud envoyé avec `allow_cloud=false`. Rejeté : fenêtre de quelques millisecondes, le serveur refuse et l'écran affiche l'erreur (AD-9 tenu côté serveur).
- low, second avis 4 — `routes_test.py` : un `judge.tag` égal au tag d'une lane remplace son script. Rejeté : route de test seulement, aucun test ne le fait ; un juge qui se note lui-même reste possible en production.
- low, second avis 5 — icône `warning` en `--color-chart-4` (≈ 2,9:1 sur fond clair). Rejeté : l'icône double un texte qui porte le sens (« note peu fiable »), WCAG 1.4.11 ne s'applique pas ; même jeton que les badges et alertes déjà validés par axe-core.
- low, second avis 6 — fixture `cancel_leftover_runs` : `sleep(0,2 s)` sans attendre la fin du run. Corrigé : elle attend que `GET /api/runs/{id}` ne soit plus `running` (10 s au plus).
