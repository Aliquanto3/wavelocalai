---
title: 'Suivre, reprendre et annuler un run en flux (SSE)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'd86d06a'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-3.md'
warnings: []
deferred:
  - summary: >-
      Adaptateur `fake` de l'`Embedder` (vecteurs déterministes, AD-8) et port `Embedder` : seuls `ChatModel` et son faux modèle sont livrés ici. Ils viennent avec le registre de modèles (1.5) et l'ingestion.
    evidence: |-
      `models/port.py` ne définit que `ChatModel` ; `fake_models` ne renvoie qu'un `FakeChatModel`.
    location: src/wavelocalai/models/
    severity: low
  - summary: >-
      `verdict` d'un run `arena` dans `GET /api/runs/{id}` et appels d'outils (`ToolCall`) dans `stream_into_run` : propres aux stories de l'Arène et des agents. L'instantané rend déjà statut, métriques des feuilles (`children`) et erreur.
    evidence: |-
      `runs/snapshot.py`, `inference/streaming.py` (le `ToolCall` est ignoré).
    location: src/wavelocalai/runs/snapshot.py
    severity: low
  - summary: >-
      `co2` des métriques d'un run de test : `unmeasurable` avec la raison « mesure non branchée » tant que `greenops/` (CodeCarbon) n'existe pas ; le service passe un `Co2` à `stream_into_run`.
    evidence: |-
      `inference/streaming.py::NOT_MEASURED`.
    location: src/wavelocalai/inference/streaming.py
    severity: low
  - summary: >-
      Un service qui appelle `hub.publish("token", …)` directement ne bénéficie pas du groupage par 50 ms : il doit passer par `hub.publish_token`. Aucun garde-fou ne l'impose (les tests de 1.3 publient encore des `token` bruts).
    evidence: |-
      `RunHub.publish` et `RunHub.publish_token`.
    location: src/wavelocalai/runs/hub.py
    severity: low
  - summary: >-
      Reprise de bout en bout dans le navigateur (`core/sse.js`, `EventSource`) : fermée par la story 2.2 ; ici le flux est éprouvé par un client httpx ASGI. Limites aussi : le sémaphore Ollama (AD-14) et le délai d'une lane n'existent pas encore.
    evidence: |-
      Découpage des stories 1.4 / 2.2.
    location: tests/v2/web/test_run_stream.py
    severity: low
  - summary: >-
      `tests/v2/web/test_real_launch.py` (story 1.2) échoue sous Windows sans `PYTHONUTF8=1` (cp1252) ; corrigé dans la branche de 1.2, non repris ici.
    evidence: |-
      Les tests de cette story passent avec `PYTHONUTF8=1`.
    location: tests/v2/web/test_real_launch.py
    severity: low
---

# Story 1.4 : suivre, reprendre et annuler un run en flux

## Objectif

Un écran qui change de page ne perd ni ne duplique aucun morceau de réponse : le flux d'un run se reprend au `seq` voulu, depuis la mémoire du hub si le run est actif, depuis la base sinon. « Arrêter » annule la tâche, ferme le flux de l'adaptateur et termine le run en moins d'une seconde, partiel conservé. Sans modèle réel : le `fake` scriptable et une commande de test servent de producteur.

## Critères d'acceptation et preuves

1. Port et faux modèle : `models/port.py` (`ChatModel`, `ChatRequest`, `ChatChunk` = `LoadState | TextDelta | ToolCall | Done(ChatResult)`) ; `models/fake.py` scriptable, enregistré par `fake_models(settings)` seulement si `Settings.testing`. Preuve : `tests/v2/unit/test_fake_model.py`.
2. Trame : `GET /api/runs/{id}/events` rend `id: <seq>` et `data: {seq, run_id, type, ts, data}` sans champ `event:`, `ts` en ISO 8601 UTC avec `Z`, par `fastapi.sse.EventSourceResponse` natif ; `seq` contigu de 1, `run_started` puis `run_ended` unique. Preuve : `tests/v2/web/test_run_stream.py::test_frame_is_id_then_data_…`.
3. `token` groupés par tranches d'au plus 50 ms et par `lane` (et par canal) : `RunHub.publish_token` ; les jetons en attente partent avant tout autre événement et à la clôture (flux et message partiel). Preuve : `test_hub_stream.py` (groupage, ordre, clôture), `test_run_stream.py::test_tokens_are_grouped_…`.
4. Commande de test : `POST /api/test/runs {kind, model, message?, script}` lance un run scripté du `fake` ; absente hors `WAVELOCALAI_TESTING`. Preuve : `test_runs_api.py` (validation, 404 sans mode test).
5. Reprise : `Last-Event-ID` ou `?after=` (le paramètre l'emporte), mémoire si actif et base sinon, sans trou ni doublon, y compris à cheval sur un lot persisté ; curseur au dernier `seq` d'un run terminé : `204` ; inconnu ou feuille : `404` ; curseur invalide : `422` ; commentaire de maintien de 15 s (natif, réglage vérifié, test avec un intervalle réduit). Preuve : `test_run_stream.py` (reprise active, lot persisté, 204, maintien, erreurs).
6. Annulation : `POST /api/runs/{id}/cancel` annule la tâche, l'adaptateur ferme son flux (`finally`), `run_ended {cancelled}` en moins d'une seconde, partiel conservé ; un parent annule ses enfants ; idempotent. `GET /api/runs/{id}` rend statut, métriques (feuilles dans `children`), `co2` et erreur. Preuve : `test_runs_api.py`, `test_fake_model.py::test_cancelling_the_run_…`.
7. `409 run_busy` : un seul run racine actif par `kind` (réservation pendant l'écriture, donc sans course), `detail.run_id` du run actif ; libéré à la fin ou à l'annulation. Preuve : `test_hub_stream.py`, `test_runs_api.py::test_a_second_run_…`, `test_two_simultaneous_…`.
8. Échec fournisseur : `ProviderError(code)` (sous-classe d'`AppError`) devient `run_ended.data.error` au format `{code, message, action, detail}`, clé masquée, statut `error` ; aucun code d'erreur ne reprend un nom de statut. Preuve : `test_fake_model.py`, `test_runs_api.py::test_a_provider_error_…`, `test_hub_stream.py::test_run_busy_envelope_…`.
9. Le budget de lecture (les `GET` sans paramètre de chemin, hors SSE) et `test_layers.py` restent verts.

## Fichiers

- `src/wavelocalai/models/` : `port.py`, `fake.py`
- `src/wavelocalai/inference/streaming.py` : `stream_into_run` (le patron des services)
- `src/wavelocalai/runs/` : `hub.py` (ajouts : `publish_token`, `watch`, `active_root`, `run_busy`), `snapshot.py`
- `src/wavelocalai/web/` : `routes_runs.py`, `routes_test.py`, `app.py` (routes, `NoContentError` → `204`, registre de modèles)
- `src/wavelocalai/errors.py` : `run_busy` (fin de liste), `ProviderError`
- `tests/v2/` : `unit/{test_hub_stream,test_fake_model}.py`, `web/{conftest,test_run_stream,test_runs_api}.py`

## Choix notables

- Le groupage des `token` se fait dans le hub, pas dans le flux : `seq` reste contigu et la base garde les mêmes événements que le direct.
- Un flux ouvert attend un `asyncio.Event` du run, renouvelé à chaque événement (`RunHub.watch`, pris avant la lecture) ; à la clôture, il relit la base, qui a tout.
- Le `204` est levé par une dépendance (`NoContentError` + gestionnaire) puisqu'un générateur SSE ne peut rendre que `200`.
- `FastAPI` écrit `data:` avant `id:` dans la trame ; l'ordre des champs SSE est sans effet pour un client.
- Test de 1.3 modifié : `test_start_interrupts_running_runs_…` crée d'abord son chat terminé, puis le chat inachevé (il en créait deux actifs à la fois, refusé par `run_busy`).

## Reports

Voir l'en-tête `deferred` : `Embedder` factice, `verdict` d'arène et appels d'outils, CO2 des runs de test, `publish("token")` brut, E2E navigateur (2.2), encodage de `test_real_launch`.
