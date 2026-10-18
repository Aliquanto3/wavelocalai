---
title: 'Chaque réponse locale affiche son CO2 mesuré (serveur)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '16f29ca'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-7.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-1.md'
warnings: []
deferred:
  - summary: >-
      Le pied de réponse du chat (« CO2 1,8 mg », `fr-FR`, sans couleur par seuil) est le dernier critère de la story 2.3 mais appartient à l'écran Chat (story 2.2, `screens/chat.js`). Le serveur publie tout ce qu'il lui faut : `metrics.co2` (`mg`, `method`, `reason`) et `metrics.energy_wh` dans le flux du run, `co2` et `energy_wh` dans `GET /api/runs/{id}` (`metrics`), et `carbon_updated` sur le flux système (le panneau CO2 de la barre haute le suit déjà, story 1.7). À brancher dans le pied de l'écran Chat : `mg` en `fr-FR`, « non mesurable » avec `reason` sinon.
    evidence: |-
      `web/test_chat_api.py::test_nominal_chat_...` (co2 et energy_wh dans `metrics`) et `test_carbon_updated_follows_each_local_reply_with_the_session_sum`.
    location: src/wavelocalai/web/static/screens/chat.js
    severity: medium
  - summary: >-
      Premier tracker du processus lent : CodeCarbon détecte le matériel au premier `start` (mesuré 8,6 s sur ce poste Windows, 1,5 s ensuite). Il s'exécute sous le sémaphore, hors du délai de lane, mais la toute première réponse attend. Un préchauffage (un tracker jeté, en tâche de fond, quand Ollama répond) est à ajouter ; il n'est pas branché ici parce qu'il importerait CodeCarbon dans chaque test qui démarre l'app et que l'ordre du préchauffage et des runs mérite une décision.
    evidence: |-
      Mesure manuelle (`start` 8,6 s puis 1,5 s) ; `local_meter.load_tracker_class` met `count_physical_cpus` en cache.
    location: src/wavelocalai/greenops/local_meter.py
    severity: low
  - summary: >-
      Ajout additif à `contrat-api.md`, à ratifier : l'événement `metrics` porte `energy_wh` (Wh mesurés par CodeCarbon, nul si non mesuré), comme `GET /api/runs/{id}` le faisait déjà dans `metrics.energy_wh`.
    evidence: |-
      `inference/streaming.py::_metrics`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Une feuille locale en erreur garde un `co2` `unmeasurable` (« réponse en erreur : aucune mesure retenue ») même si le tracker a mesuré : l'énergie d'un appel raté n'est pas celle d'une réponse. Une feuille annulée, elle, garde la mesure faite jusqu'à l'arrêt. À trancher si l'on veut compter l'énergie des erreurs.
    evidence: |-
      `test_an_errored_leaf_stops_its_tracker_and_keeps_an_unmeasurable_co2`, `test_a_cancelled_leaf_stops_its_tracker_and_keeps_what_was_measured`.
    location: src/wavelocalai/inference/streaming.py
    severity: low
  - summary: >-
      `kwh <= 0` ou non fini est tenu pour une mesure ratée (`unmeasurable`), jamais pour un 0 : CodeCarbon ne rend 0 que lorsqu'il n'a rien lu. Sous Windows sans RAPL il estime la puissance du processeur (TDP et charge) : la valeur est mesurée par CodeCarbon, mais estimée par lui, comme dans la v1.
    evidence: |-
      `test_a_codecarbon_failure_leaves_the_run_ok_with_an_unmeasurable_co2[zero,nan,negative]`.
    location: src/wavelocalai/greenops/local_meter.py
    severity: low
---

# Story 2.3 : chaque réponse locale affiche son CO2 mesuré (serveur)

## Objectif

Une réponse locale du chat est mesurée par CodeCarbon (`OfflineEmissionsTracker`, pays et PUE de `Settings`) et sa feuille porte `co2 = {mg, method: "codecarbon", estimated: false, range_mg: null, allocation: "direct", reason: null}` et `energy_wh`. Le service publie `carbon_updated` après chaque feuille. Côté serveur seulement : le pied de réponse « CO2 1,8 mg » est dans l'écran Chat (story 2.2), voir reports.

## Critères d'acceptation et preuves

1. `greenops/local_meter.py` (modèle de `wavestack/greenops.py`, copie adaptée, `codecarbon` importé dans `load_tracker_class` seulement, version revérifiée : 3.3.1 installée, dernière sur PyPI, `pyproject` inchangé `>=2.8.0`). `LocalMeter.track()` démarre le tracker puis l'arrête **dans la place du `LocalSlot`** (`inference/streaming.py::_attempt`, hors du délai de lane), un seul à la fois (verrou du compteur en plus du sémaphore), `start`/`stop` par `asyncio.to_thread`. Pays et PUE : `Settings.carbon`. `tracking_mode="machine"` (Ollama est un autre processus), `save_to_file=False`, `save_to_api=False`, `allow_multiple_runs=True` (pas de fichier de verrou : l'unicité est la nôtre). La feuille finit par `hub.finish_leaf(result, co2)` avec `energy_wh` ; une relance additionne les deux mesures. Preuve : `test_local_meter.py` (nominal, arguments du tracker, tracker vivant pendant la place prise, démarrage lent hors du délai, relance, cloud non mesuré), `test_chat_api.py::test_nominal_chat_...`.
2. Aucun réseau, aucun fichier : le vrai `OfflineEmissionsTracker` tourne avec `socket.socket`, `create_connection`, `getaddrinfo` et `gethostbyname` remplacés (tentatives consignées, aucune) dans un dossier courant vide (aucun CSV). Preuve : `test_the_real_offline_tracker_measures_without_any_network_or_file`.
3. Erreur de CodeCarbon (absent, démarrage, arrêt, données absentes, énergie nulle, négative ou NaN) : le run finit `ok`, `co2 = {mg: null, method: "unmeasurable", reason}`. Preuve : `test_a_codecarbon_failure_leaves_the_run_ok_with_an_unmeasurable_co2` (6 cas), `test_codecarbon_missing_...`. Une feuille en erreur arrête son tracker et garde un `co2` sans valeur (`test_an_errored_leaf_...`). Une feuille annulée arrête son tracker, libère la place et **garde la mesure faite jusqu'à l'arrêt** : le hub clôt l'annulation avant que la tâche reprenne la main, donc `RunHub.amend_cancelled_leaf` (attend la clôture, ne remplace que le `co2` de remplacement d'une feuille `cancelled`) l'écrit, report de la story 2.1. Preuve : `test_a_cancelled_leaf_...` (deux tests), `test_hub.py::test_a_cancelled_leaf_gets_its_late_measure_...`.
4. Un seul tracker à la fois, même avec plusieurs feuilles locales : trois runs (`chat`, `rag`, `agent`) en parallèle sous un `LocalSlot`, pic de trackers simultanés 1 ; le compteur seul, sans sémaphore, sérialise aussi. Preuve : `test_several_local_leaves_never_run_two_trackers_at_once`, `test_the_meter_alone_serializes_trackers_even_without_the_slot`.
5. `carbon_updated` : `ChatService` passe `on_leaf_closed` à `stream_into_run`, qui l'attend à la fermeture de la feuille, annulation comprise, après l'écriture du `co2` ; l'événement porte la somme de la session (`announce_carbon_updated`). Un échec de publication est journalisé sans interrompre. Preuve : `test_carbon_updated_is_published_after_each_leaf_including_a_cancelled_one`, `test_a_failing_announcement_...`, `test_chat_api.py::test_carbon_updated_follows_each_local_reply_with_the_session_sum`.
6. Test `integration` : les deux plus petits modèles de chat installés, de tailles différentes (le plus petit, puis le plus petit pesant au moins 1,5 fois plus ; lus dans `GET /api/tags`, aucun téléchargement), donnent des `co2.mg` différents, tous deux `codecarbon`, ni égaux à `0,19 mg x jetons` ni à 0,19 mg/jeton. Preuve : `integration/test_co2_ollama.py` (lancé sur ce poste, voir le rapport) ; `test_chat_ollama.py` attend désormais `codecarbon` (saute sans `qwen2.5:1.5b`).

## Fichiers

- `src/wavelocalai/greenops/local_meter.py` (nouveau), `greenops/__init__.py`
- `src/wavelocalai/inference/streaming.py` (compteur sous la place, `on_leaf_closed`, `energy_wh`), `inference/chat.py` (`meter`, `bus`), `web/app.py` (`create_app(meter=)`, `app.state.meter`)
- `src/wavelocalai/runs/hub.py`, `runs/repo.py` (`amend_cancelled_leaf`)
- Tests : `tests/v2/carbon_stub.py` (double de tracker), `tests/v2/conftest.py` (le double remplace `load_tracker_class` pour tous les tests), `unit/test_local_meter.py`, `unit/test_hub.py`, `web/test_chat_api.py`, `integration/conftest.py` (`real_meter`), `integration/test_co2_ollama.py`, `integration/test_chat_ollama.py`

## Télémétrie

CodeCarbon n'est pas dans `TELEMETRY_OPT_OUTS` (`src/core/telemetry.py` et `wavelocalai/telemetry.py` ne le citent pas) : le tracker `Offline` n'envoie rien (`save_to_api=False`, test sans socket), `disable_telemetry()` n'est pas requis avant son import.
