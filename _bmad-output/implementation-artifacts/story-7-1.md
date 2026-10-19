---
title: 'Noter la fidélité et la pertinence d''une réponse documentaire (serveur)'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '13bcd36'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-3.md'
warnings: []
deferred:
  - summary: >-
      Choix de conception à confirmer, variante la plus conservatrice gardée. (1) Les extraits communs sont cherchés par la stratégie `naive`, sans reclassement (4.7) : la comparaison porte sur les modèles, pas sur la recherche ; `top_k` est celui en vigueur. (2) La fidélité vérifie une affirmation par appel du juge (« une à une »), au plus 10 affirmations par réponse : un modèle bavard n'est noté que sur ses dix premières. Un juge local fait donc jusqu'à 13 appels par réponse (1 + 10 + 1 + 1). (3) Un verdict « appuyée » dont l'extrait désigné n'existe pas garde son verdict, `support` devient `null` (le serveur ne corrige pas le juge). (4) `question_index` compte à partir de 0 (comme `round` de `retrieval_step`). (5) La notation commence quand toutes les réponses sont données (trois étapes qui avancent dans l'ordre, pas de chargement alterné entre le modèle évalué et le juge) ; les locaux répondent un modèle après l'autre. (6) Plafonds : 1 à 4 modèles, 1 à 20 questions de 20 000 caractères au plus. (7) `partial` vaut vrai aussi pour un run `error` (une évaluation arrêtée par un incident d'orchestration), pas seulement `cancelled` et `interrupted` : sinon ses cellules resteraient « en cours » à la réouverture.
    evidence: |-
      `src/wavelocalai/evaluation/service.py`, `prompts.py`, `runs/eval_snapshot.py::PARTIAL_STATUSES` ; `tests/v2/web/test_eval_api.py`.
    location: src/wavelocalai/evaluation/service.py
    severity: medium
  - summary: >-
      Ajout à la lettre des critères : l'événement `eval_answer {lane, question_index, text, error}` (la réponse de chaque modèle, texte saisi donc dans le flux, effacé avec lui, AD-7 et AD-13) et `eval_questions {questions}`. Sans eux le front ne saurait ni quelle question porte quel rang ni ce que le modèle a répondu (l'appel est silencieux : aucun `token`, et `metrics` est publié par un nouveau paramètre `publish_metrics` de `stream_into_run`). Consignés dans `contrat-api.md`.
    evidence: |-
      `contrat-api.md` § « Évaluation (story 7.1) » ; `inference/streaming.py::stream_into_run(publish_metrics=)`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Pas de route de liste des évaluations passées (`GET /api/rag/eval/runs`) : le critère 7.1 ne la demande pas, mais la story 7.3 doit « lister les évaluations passées, les plus récentes d'abord » (décision n° 14 du 2026-10-19). À ajouter par la 7.3 (comme `list_arena_runs` pour l'Arène : `runs/snapshot.py`, `eval_questions` lu dans le flux), ou par une passe serveur avant elle.
    evidence: |-
      `decisions-2026-10-19.md` n° 14 ; `runs/snapshot.py::list_arena_runs` (modèle à suivre).
    location: _bmad-output/planning-artifacts/epics.md
    severity: medium
  - summary: >-
      Fusion avec les stories parallèles (5.1, 5.3, 6.1) : la migration s'appelle `0006_evaluations.sql` (et `schema_v6.sql`) ; si l'une d'elles fusionne avant avec une `0006`, renuméroter les deux fichiers, l'instantané et `test_default_temperature.py::test_migration_0005_...` (qui borne désormais `migrate(path, target=5)`, au lieu de la dernière version). `web/app.py` reçoit, en plus de l'enregistrement du routeur, trois lignes de cycle de vie (`app.state.evaluation` : défaut, construction par `routes_eval.build_service`, remise à `None`), le service ayant besoin de la fabrique de modèles et de l'index, locaux au cycle de vie.
    evidence: |-
      `git diff master -- src/wavelocalai/web/app.py` (5 lignes) ; `tests/v2/unit/snapshots/schema_v6.sql`.
    location: src/wavelocalai/web/app.py
    severity: low
  - summary: >-
      Le texte de `run_not_found` (`errors.py`) parle de « comparaison » : il s'affiche tel quel pour une évaluation (ou un banc) introuvable. À reformuler en 7.3 et 7.4 (code inchangé, texte neutre).
    evidence: |-
      `src/wavelocalai/errors.py` (`run_not_found`).
    location: src/wavelocalai/errors.py
    severity: low
  - summary: >-
      La justesse des notes n'est pas prouvée ici : un vrai juge de 1,5 milliard de paramètres (`qwen2.5:1.5b`) rend des notes plausibles mais peu fiables (fidélité 0 avec une affirmation « contredite », pertinence 68, précision 100 sur la note de cadrage de l'atelier). Le jeu fixe et son seuil d'accord viennent avec la 7.2 (relecture d'Anaël en prérequis).
    evidence: |-
      `tests/v2/integration/test_eval_ollama.py` (vérifie la forme des notes, pas leur justesse).
    location: tests/v2/integration/test_eval_ollama.py
    severity: low
---

# Story 7.1 : noter la fidélité et la pertinence d'une réponse (serveur)

## Objectif

Une consultante lance l'évaluation d'un à quatre modèles sur une question ou un jeu de questions : les mêmes extraits leur sont fournis, chaque réponse est découpée en affirmations vérifiées une à une contre ces extraits, sa pertinence et la précision du contexte sont mesurées, et chaque note arrive au fil de l'eau, avec ses verdicts. Serveur seulement : l'écran est la 7.3.

## Critères d'acceptation et preuves

1. **Migration `0006_evaluations.sql`** : table `evaluations` (run, modèle, question, métrique, `score` nul = non évalué, `reason`, `detail` JSON : verdicts, questions ou extraits utiles), instantané de schéma `schema_v6.sql` à jour. Preuve : `test_schema.py` (instantané, `test_evaluations_keep_one_note_per_model_question_and_metric`).
2. **`POST /api/rag/eval/runs {questions, models, judge, allow_cloud}`** : racine `eval`, extraits communs cherchés une fois par question (feuille `embedding`), une feuille `generation` par modèle et question, notation en feuilles `judge` ; locaux en séquence, cloud en parallèle (AD-14). 1 à 4 modèles, au-delà `422 invalid_request` (décision n° 14) ; `cloud_not_allowed`, `model_not_found`, `rag_base_empty` avant toute écriture ; `run_busy` à la deuxième évaluation. Preuve : `test_eval_api.py::test_two_models_answer_on_the_same_extracts_...`, `::test_one_to_four_models_at_most_otherwise_422`, `::test_four_models_are_accepted`, `::test_bad_requests_are_refused_before_any_run`, `::test_a_cloud_model_or_judge_needs_allow_cloud`, `::test_an_empty_base_is_refused_with_rag_base_empty`, `::test_a_second_evaluation_while_one_runs_is_run_busy`, `::test_locals_answer_one_after_the_other_and_the_cloud_in_parallel`.
3. **Fidélité** : affirmations extraites puis vérifiées une à une par `response_schema`, verdict « appuyée », « non appuyée » ou « contredite » et extrait d'appui (`support`), score = part d'affirmations appuyées. **Pertinence** : le juge retrouve 3 questions depuis la réponse, cosinus moyen avec la question par l'`Embedder` de la base. **Précision du contexte** : part des extraits que le juge désigne utiles. Preuve : `test_eval_scoring.py` (invites, lecture des sorties, notes), `test_eval_api.py::test_two_models_...` (67 / cosinus attendu / 50), `test_eval_ollama.py` (vrai Ollama).
4. **`eval_metric`** publié au fil de l'eau, `score: null` et raison pour un juge indisponible, une sortie invalide, une réponse vide, un modèle en échec : jamais 0. Un jeu de questions porte `question_index`, `question_count` et `aggregate {score, evaluated, not_evaluated, total}` (« sur 8 questions (1 non évaluée) »). Noms de champs consignés dans `contrat-api.md` § « Évaluation (story 7.1) ». Preuve : `test_eval_api.py::test_a_set_of_questions_...`, `::test_a_partly_unscored_set_...`, `::test_a_failing_judge_never_gives_zero_on_the_faithfulness[*]`, `::test_the_other_metrics_have_their_own_not_evaluated_reasons`, `::test_an_empty_answer_is_not_evaluated_...`, `::test_a_model_that_fails_...`, `::test_no_judge_gives_not_evaluated_everywhere_...`.
5. **Effacer** : `DELETE /api/rag/eval/runs/{id}` supprime `evaluations` et `run_events`, garde les `runs` (AD-13), ni le texte de la question ni celui des réponses ne reste dans le `.db` ni le `-wal`. Preuve : `::test_erasing_an_evaluation_removes_its_text_and_scores_and_keeps_the_runs`, `::test_erasing_refuses_an_active_or_foreign_run`.
6. **Évaluation annulée ou interrompue** : les notes déjà données restent dans `evaluations`, l'instantané `GET /api/runs/{id}` porte `partial: true` et `missing` (les notes non produites, « non évalué : évaluation arrêtée », jamais 0). Preuve : `::test_a_cancelled_evaluation_keeps_its_scores_...`, `::test_an_evaluation_interrupted_by_a_restart_is_partial_too`.
7. **Intégration** : le vrai Ollama (`qwen2.5:1.5b` modèle évalué et juge, embedding installé) note une réponse sur les trois métriques (`integration`, saute sans Ollama ni modèles). Preuve : `tests/v2/integration/test_eval_ollama.py`.

## Hors périmètre

L'écran (7.3), le jeu fixe de non-régression et le seuil d'accord du juge (7.2), le Banc d'essai (7.4), la liste des évaluations passées (voir `deferred`), le reclassement des extraits, un export.

## Règles écrites

- **Une note n'est jamais 0 par défaut** : `score: null` avec une raison parmi « réponse vide », « juge indisponible », « sortie du juge invalide », « aucune affirmation à vérifier », « aucune question retrouvée depuis la réponse », « modèle d'embedding indisponible », « délai dépassé », « réponse en échec », « évaluation arrêtée ». Un 0 est une vraie note (aucune affirmation appuyée, aucun extrait utile).
- **Couches** : `evaluation/` n'importe pas `rag/` ; la base lui est donnée par le port `EvalBase` (`evaluation/service.py`), implémenté par `rag/eval_base.py` et câblé par `web/routes_eval.py::build_service`. Le juge est celui de l'Arène (`Judge.ask`, extrait de `Judge.score`, qui n'a pas changé de comportement).
- **Base occupée** : un run `eval` est un run de base (AD-16) : supprimer un document, « Vider » ou changer d'embedding rend `409 base_in_use` pendant l'évaluation.
- **Texte saisi** : les questions et les réponses vivent dans le flux (`eval_questions`, `eval_answer`), jamais dans `runs.params` (AD-7).

## Notes de développement

- `evaluation/service.py` (service, port `EvalBase`), `prompts.py` (invites, schémas, lecture des sorties), `scoring.py` (fonctions pures), `repo.py` (écriture de `evaluations`), `runs/eval_snapshot.py` (résumé, `partial`, `missing`, partagé avec l'instantané), `rag/eval_base.py`, `web/routes_eval.py`.
- Modifiés : `evaluation/judge.py` (`ask`, `JudgeReply`), `inference/streaming.py` (`publish_metrics`), `rag/query.py` (`check_vectors` en fonction de module), `rag/manage.py` (`eval` dans les runs de base), `runs/hub.py` et `runs/repo.py` (`erase_eval`), `runs/snapshot.py` (instantané `eval`), `web/app.py` (câblage).
- `contrat-api.md` : sous-section « Évaluation (story 7.1) » avant « Par écran » ; la ligne `eval_metric` du tableau y renvoie.

## Fichiers

- `src/wavelocalai/store/migrations/0006_evaluations.sql`, `src/wavelocalai/evaluation/{service,prompts,scoring,repo}.py`, `src/wavelocalai/runs/eval_snapshot.py`, `src/wavelocalai/rag/eval_base.py`, `src/wavelocalai/web/routes_eval.py`
- Tests : `tests/v2/web/test_eval_api.py`, `tests/v2/unit/test_eval_scoring.py`, `tests/v2/integration/test_eval_ollama.py`, `tests/v2/unit/snapshots/schema_v6.sql` (nouveaux) ; `tests/v2/unit/test_schema.py`, `tests/v2/unit/test_default_temperature.py` (complété, réaligné)

## Rapport de dev

Ciblé (poste partagé : ni `tests/v2` complet ni E2E ; la CI lance la suite). `tests/v2/unit` : 899 verts, 1 sauté. `test_eval_api.py` : 30 verts ; régression des fichiers touchés (`test_arena_*`, `test_rag_run_api`, `test_rag_manage_api`, `test_rag_strategies_api`, `test_read_budget`, `test_lifecycle`, `test_runs_api`, `test_memory_guard_api`) : 171 verts. Intégration sur le vrai Ollama de ce poste : `test_eval_ollama.py` vert (14 s). Contrôle rapide propre.

## Journal

- 2026-10-19 · dev : spec, migration 0006, service d'évaluation (fidélité, pertinence, précision du contexte), routes, instantané partiel, effacement, contrat, tests.
