---
title: 'Le hub enregistre chaque exécution (store SQLite, migration du hub, cycle de vie)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '68de3ef'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-2.md'
warnings: []
deferred:
  - summary: >-
      Réhydratation de `sources` au rejeu (AD-7) : le hub écrit `sources` sans `text` et rend les événements tels quels depuis la base. Réhydrater le texte depuis `chunks` (`null` si le document est supprimé) attend la table `chunks`, créée par la story de la base documentaire.
    evidence: |-
      `RunHub.events_after` ; test `test_sources_are_persisted_without_text_but_live_with_it`.
    location: src/wavelocalai/runs/hub.py
    severity: medium
  - summary: >-
      Un run racine actif par `kind` (`409 run_busy`, AR12/AD-14) : aucun code `run_busy` dans `errors.py` ni contrôle dans le hub. Il appartient aux stories qui exposent les commandes `POST …/runs` (elles portent le code et sa clé `run_id`).
    evidence: |-
      `hub.active_runs()` fournit la liste ; `create_run` n'interdit pas deux racines du même genre.
    location: src/wavelocalai/runs/hub.py
    severity: medium
  - summary: >-
      Flux SSE, reprise `Last-Event-ID`/`?after=`, `204`, groupage des `token` par 50 ms, routes `GET /api/runs/{id}` et `POST …/cancel` : story 1.4. Le hub offre `events_after`, `cancel` et `attach_task`, mais pas encore d'attente d'un nouvel événement (abonnement) pour un flux ouvert.
    evidence: |-
      Découpage des stories 1.3 / 1.4.
    location: src/wavelocalai/runs/hub.py
    severity: low
  - summary: >-
      Effacement (AD-13 : `DELETE` conversation/run, `VACUUM`, `wal_checkpoint`, `409` si run actif), `ensure_vec_table(dim)` et sqlite-vec : non requis ici. Les clés étrangères sont prêtes (`messages` et `run_events` en cascade, `runs.conversation_id` à `NULL`), vérifiées par `test_erasing_a_conversation_keeps_the_runs_without_text`.
    evidence: |-
      `tests/v2/unit/test_schema.py`.
    location: src/wavelocalai/store/migrations/0001_hub.sql
    severity: low
  - summary: >-
      Transitions vers `awaiting_approval` (approbations, étape 6) : le statut existe en base et `interrupt_orphans` le traite, mais le hub n'a pas de méthode pour y entrer.
    evidence: |-
      Statuts d'AD-5.
    location: src/wavelocalai/runs/hub.py
    severity: low
  - summary: >-
      Si la transaction de clôture échoue (disque plein), l'exception remonte et le run reste en mémoire, fermé aux événements ; il sera `interrupted` au prochain démarrage. Pas de nouvel essai automatique.
    evidence: |-
      `test_last_batch_status_and_assistant_message_are_one_transaction` (rien n'est écrit à moitié).
    location: src/wavelocalai/runs/hub.py
    severity: low
  - summary: >-
      `tests/v2/web/test_real_launch.py` (story 1.2) échoue sous Windows sans `PYTHONUTF8=1` : le sous-processus écrit sa sortie en cp1252 et le test la lit en UTF-8. Constaté aussi sur la base de la story 1.2 seule, sans cette story.
    evidence: |-
      `pytest tests/v2` : 1 échec sans `PYTHONUTF8=1`, 179 réussis avec.
    location: tests/v2/web/test_real_launch.py
    severity: low
---

# Story 1.3 : le hub enregistre chaque exécution

## Objectif

Chaque génération est un run enregistré, numéroté par le hub seul, terminé proprement ; après un redémarrage, ce qui était en cours est déclaré `interrupted` avec un `run_ended` synthétique, et l'arrêt propre passe les runs actifs à `cancelled`. La base `data/wavelocalai.db` est migrée au démarrage ; une base plus récente que le code refuse le démarrage.

## Critères d'acceptation et preuves

1. Base absente : `store/db.py` ouvre `wavelocalai.db` (dossier de données configurable) en `journal_mode=WAL`, `foreign_keys=ON`, `secure_delete=ON` ; un seul écrivain (connexion dédiée, fil unique, file d'attente, une transaction par écriture) ; lectures sur connexions courtes en `query_only`. Preuve : `tests/v2/unit/test_store.py` (pragmas de l'écrivain et d'un lecteur ; 200 écritures depuis 8 fils exécutées par un seul fil distinct de l'appelant ; `ROLLBACK` sur exception ; lecture refusée en écriture).
2. `store/migrations/0001_hub.sql` crée en entier `app_sessions`, `conversations`, `runs`, `run_events`, `messages` ; `PRAGMA user_version` = 1. `runs.status` : les six statuts ; `runs.kind` : les huit racines et `generation`, `judge`, `embedding` ; colonnes : `parent_run_id`, `app_session`, `conversation_id` (nullable), modèle, début, fin, jetons, `ttft_s`, `tps`, `tps_source`, `energy_wh`, champ `co2` d'AD-10 à plat (`co2_mg`, `_method`, `_estimated`, `_range_low_mg`, `_range_high_mg`, `_allocation`, `_reason`), `params`, `error` ; `conversations.kind` : `chat`, `rag`, `agent` ; `messages` : rôle, contenu, raisonnement, appels d'outils, `run_id`. Preuve : `test_schema.py` (chaque valeur du vocabulaire du code est admise, une valeur inconnue refusée ; `co2_reason` exigé quand `mg` est nul ; JSON valide ; clés étrangères).
3. Instantané : `test_schema.py` applique les migrations sur une base vide et compare à `tests/v2/unit/snapshots/schema_v1.sql` (un instantané par migration, `python -m tests.v2.unit.test_schema N` l'écrit).
4. Migration N+1 : copie `wavelocalai.db.bak-N` (API `backup`, cohérente avec le WAL) avant la migration, appliquée dans une transaction (échec = `ROLLBACK`, version inchangée, message qui cite la copie) ; `user_version` au-dessus du code : `DatabaseTooNewError`, base intacte, `wavelocalai-v2` sort avec le code 1 et le message. Preuve : `test_store.py`, `web/test_lifecycle.py::test_launcher_refuses_a_database_newer_than_the_code`.
5. Hub (`runs/hub.py`) : seul à attribuer `seq` (contigu dès 1, `run_started` publié par la création, `run_ended` unique et dernier, refus des deux types côté service), garde les événements en mémoire, les écrit en lots (tâche de fond, au plus 1 s), et écrit dernier lot + `run_ended` + statut + métriques/`co2` + message assistant dans une transaction (test avec échec injecté : rien de la clôture ne subsiste). Avec un message utilisateur, le hub crée la conversation (ou reprend celle donnée, de même genre) et écrit le message utilisateur dans la transaction de création du run. `runs.params` : `check_params` refuse les clés de texte saisi, tout texte long et tout texte contenant la question ; test sur la base. Preuve : `tests/v2/unit/test_hub.py`.
6. Composite : un parent et deux feuilles `generation` ; `cancel(parent)` annule les tâches attachées, passe les enfants et le parent à `cancelled` (feuille déjà `ok` conservée) ; métriques et `co2` à `NULL` hors feuilles ; `finish_leaf` refuse un parent. Preuve : `test_hub.py` (`test_cancelling_the_parent_…`, `test_metrics_live_on_leaves_only`).
7. Démarrage et arrêt : `start()` passe les runs `running` à `interrupted` (racine : `run_ended {status: "interrupted", error: null}` à la suite du dernier `seq` écrit ; message assistant partiel reconstruit des `token` déjà écrits), puis ouvre une nouvelle `app_session` ; `stop()` (lifespan de l'app) passe les runs actifs à `cancelled` ; `new_app_session("reset")` pour la remise à zéro. Preuve : `test_hub.py`, `web/test_lifecycle.py`.
8. Les tests du hub utilisent `tests/v2/producers.py` (chat à un run, arène à deux feuilles), sans adaptateur de modèle. `tests/v2/unit/test_layers.py` reste vert (`runs` → `store`, `web` → `runs` + `store`).

## Fichiers

- `src/wavelocalai/store/` : `db.py`, `migrate.py`, `migrations/0001_hub.sql`
- `src/wavelocalai/runs/` : `hub.py`, `models.py` (`Co2`, `LeafResult`, `AssistantMessage`, listes closes), `repo.py` (SQL du hub)
- `src/wavelocalai/web/app.py` (lifespan : base, hub), `web/server.py`, `__main__.py` (ouverture de la base, refus)
- `tests/v2/` : `producers.py`, `unit/{test_store,test_schema,test_hub}.py`, `unit/snapshots/schema_v1.sql`, `web/test_lifecycle.py`

## Choix notables

- Un run « simple » (chat) est une racine sans enfant : `finish_leaf` la clôt avec son flux. Un run composite se clôt par `finish_run` ; ses feuilles (`generation`, `judge`, `embedding`) ne publient rien, le parent publie seul (AD-5).
- Aucun code d'erreur ajouté à `errors.py` : conversation inconnue = `not_found`, genre incompatible = `invalid_request`.
- Les écritures du hub sont `await`ées sur la boucle ; `publish` est synchrone et ne touche que la mémoire. Un `publish` ou un `finish_leaf` tardif après annulation est écarté sans lever (course normale).
- `app.state.store` / `app.state.hub` : le lanceur ouvre la base (refus de démarrer avant d'écouter) ; sans lanceur (tests), l'app ouvre et ferme la sienne dans son lifespan.

## Reports

Voir l'en-tête `deferred` : réhydratation des sources, `409 run_busy`, flux SSE (1.4), effacement et sqlite-vec, `awaiting_approval`, échec de clôture, encodage de `test_real_launch`.
