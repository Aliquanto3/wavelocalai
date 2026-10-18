---
title: "L'Arène exécute plusieurs modèles sur une même question (serveur)"
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'a43ff7d'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-3.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-1.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-4.md'
warnings: []
deferred:
  - summary: >-
      Le `co2` de chaque lane est « non mesurable » (raison « mesure non branchée ») : la lane passe par `stream_into_run`, le chemin de feuille commun du chat, qui portera la mesure locale (story 2.3) et l'estimation cloud (story 2.5) après leur fusion. Aucun chemin de mesure parallèle n'a été écrit ici.
    evidence: |-
      `test_two_local_lanes_and_a_cloud_lane_compose_one_run` (`co2.method == "unmeasurable"` sur chaque feuille et chaque `metrics`).
    location: src/wavelocalai/inference/streaming.py
    severity: low
  - summary: >-
      `judge` et `criteria` sont acceptés, bornés et rangés dans `runs.params` de la racine (identifiants courts, jamais de texte saisi) ; le juge est seulement résolu (`cloud_not_allowed` avant tout run). La notation, `lane_status: judging` et `judge_score` sont la story 3.3 ; le verdict de l'instantané `GET /api/runs/{id}` la 3.5. Si les critères deviennent du texte libre, ils iront dans un événement, pas dans `params`.
    evidence: |-
      `test_the_prompt_lives_in_run_events_never_in_run_params`.
    location: src/wavelocalai/inference/arena.py
    severity: low
  - summary: >-
      Ajouts au contrat d'API, à valider avec la story 3.6 (rouvrir) : l'événement `question {text}` (la question d'une Arène vit dans `run_events`, faute de conversation) et la clé `error` de `lane_status` pour `timeout` et `failed`. Une Arène n'ouvre pas de conversation (`conversations.kind` n'admet pas `arena`) : `POST /api/arena/runs` rend `{run_id}` seul.
    evidence: |-
      `contrat-api.md` (tables « Événements de run ») ; `test_two_local_lanes_...`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      `metrics` et `lane_status: done` d'une lane locale sont publiés juste après la libération du sémaphore (le chemin commun publie les métriques hors de la place) : le `generating` de la lane suivante peut précéder de quelques millisecondes le `done` de la précédente dans le flux. Ses jetons, eux, suivent toujours la dernière sortie de la première. Le déplacer dans la place est un changement du chemin commun que la story 2.3 (mesure dans la place) touche aussi.
    evidence: |-
      `test_locals_run_in_sequence_under_the_slot_and_the_cloud_runs_at_once` (ordre des jetons, pas des `done`).
    location: src/wavelocalai/inference/streaming.py
    severity: low
---

# Story 3.1 : l'Arène exécute plusieurs modèles sur une même question (serveur)

## Objectif

`POST /api/arena/runs {models, prompt, judge, criteria, allow_cloud}` lance un run composite : une racine `arena` qui publie seule le flux et une feuille `generation` par modèle. Les locaux passent l'un après l'autre par le sémaphore, les cloud partent en parallèle, une lane lente ou en échec n'arrête pas les autres. Côté serveur seulement (l'écran est la story 3.2, le juge la 3.3).

## Critères d'acceptation et preuves

1. 2 à 4 modèles distincts : le hub crée la racine `arena` et un enfant par modèle (`parent_run_id`) ; moins de 2, plus de 4, un doublon, un prompt vide ou des critères hors bornes rendent `invalid_request` (422) ; un modèle inconnu `model_not_found` ; un modèle cloud (ou un juge cloud) sans `allow_cloud` rend `cloud_not_allowed` avant tout appel et toute écriture. Seule la racine publie ; `token`, `metrics` et `lane_status` portent `lane` = tag ; métriques et `co2` vivent sur les feuilles. Pas de conversation. Preuve : `web/test_arena_api.py::test_two_local_lanes_and_a_cloud_lane_compose_one_run`, `test_invalid_requests_are_refused_without_creating_a_run`, `test_a_cloud_model_without_allow_cloud_is_refused_before_any_call_or_write`.
2. Deux locaux et un cloud : les locaux passent en séquence par le sémaphore (FIFO, dans l'ordre de `models`), le cloud part aussitôt ; chaque lane publie `lane_status` (`waiting` au départ, `generating` à la prise de la place ou au départ de l'appel, `loading` pendant le chargement d'Ollama, `done`). Preuve : `test_locals_run_in_sequence_under_the_slot_and_the_cloud_runs_at_once`, `test_the_loading_phase_is_published_for_a_local_lane`.
3. Délai de lane depuis la prise de la place (local) ou le départ (cloud) ; une lane hors délai (`timeout`) ou en échec (`failed`) porte son erreur d'AD-18 dans `lane_status`, les autres continuent, la racine finit `ok`. Preuve : `test_a_slow_lane_times_out_and_a_failing_lane_fails_while_the_others_finish`, `test_lane_timeout_counts_from_the_slot_not_from_the_wait`.
4. Annuler la racine annule les feuilles : toutes les lanes inachevées passent à `cancelled` (publié par un crochet du hub juste avant `run_ended`, `hub.set_cancel_hook`), les partiels restent dans `run_events`, les flux des adaptateurs sont fermés ; l'arrêt du serveur fait de même. Une seconde Arène rend `409 run_busy` avec le `run_id` actif dans `detail`. Preuve : `test_cancelling_the_parent_cancels_every_lane_and_keeps_the_partials`, `test_the_arena_is_cancelled_with_the_server`, `test_a_second_arena_gets_409_run_busy_with_the_active_run_id`.
5. AD-7 : la question vit dans l'événement `question` du flux, jamais dans `runs.params` (température, `allow_cloud`, tag du juge, critères). Preuve : `test_the_prompt_lives_in_run_events_never_in_run_params`.
6. Avec deux vrais petits modèles locaux (`qwen2.5:1.5b`, `granite4:350m`, déjà installés) : un seul à la fois, métriques `ollama_eval`. Preuve : `integration/test_arena_ollama.py` (marqueur `integration`).

## Fichiers

- `src/wavelocalai/inference/arena.py` : `ArenaService`, `ArenaCommand` (orchestration, `lane_status`)
- `src/wavelocalai/inference/streaming.py` : `stream_into_run(publish_to=, on_phase=)` rend le `LeafResult` ; une feuille publie sur son parent
- `src/wavelocalai/runs/hub.py` : `set_cancel_hook`
- `src/wavelocalai/web/routes_arena.py`, `web/app.py` : `POST /api/arena/runs`, `app.state.arena`
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md` : événement `question`, `error` de `lane_status`
- Tests : `tests/v2/web/test_arena_api.py`, `tests/v2/integration/test_arena_ollama.py`

## Reports

Voir `deferred` : CO2 des lanes (2.3 et 2.5), juge et verdict (3.3, 3.5), contrat à valider en 3.6, ordre `done` / `generating` entre deux locales.
