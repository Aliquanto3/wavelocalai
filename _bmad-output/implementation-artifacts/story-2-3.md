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
      Préchauffage de CodeCarbon (revue) : une réponse locale demandée pendant les premières secondes du serveur attend la fin du préchauffage (verrou du compteur, un seul tracker à la fois) ; mesuré 3,8 à 14,5 s selon la charge de la machine au démarrage. À trancher si l'on préfère, dans cette fenêtre, répondre sans mesure (`unmeasurable`) plutôt qu'attendre.
    evidence: |-
      Mesure de revue : réponse lancée dès le démarrage 14,5 s ; lancée 12 s après, 0,52 s.
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

## Revue

Revue Opus du 2026-10-18 (une passe), avec la liste du second avis (Haiku).

Mesures (poste Windows, `qwen2.5:1.5b`, app réelle par `ASGITransport`, vrai `LocalMeter`) :
- avant : premier `start` 3,8 à 10 s (détection du matériel par CodeCarbon, une fois par processus), premier `stop` 0,35 à 0,68 s, tous deux dans la place Ollama de la première réponse (run complet 4,9 s pour 0,34 s de génération) ; ensuite `start` et `stop` 0,00 s (moins de 10 ms), run complet 0,15 s. Les 1,4 s et 2 à 2,7 s par appel relevés par le second avis ne se reproduisent pas (trois séries, avec ou sans charge GPU) : seul le premier tracker du processus est lent.
- après (`warm_up` au démarrage du serveur) : première réponse 0,52 s, `start`/`stop` 0,00 s dans la place ; le préchauffage (5,9 s ici) se fait hors requête.

- medium, second avis 1 (`start`/`stop` dans la place) : corrigé en partie, confirmé pour le premier tracker seulement. `LocalMeter.warm_up` (un tracker jeté, sous le verrou du compteur, AD-11) est lancé en tâche de fond par le cycle de vie de l'app (`web/app.py`) ; il paie la détection du matériel hors du chemin de requête. La piste `start_task`/`stop_task` sur un tracker unique est écartée : après le premier tracker, `start`/`stop` coûtent moins de 10 ms, et le mode tâche garderait chaque tâche dans `tracker._tasks` pendant toute la vie du serveur. Reste une attente si la première réponse arrive pendant le préchauffage (report ci-dessus). Preuve : `test_the_app_warms_codecarbon_up_at_startup_before_any_reply`, `test_warm_up_runs_one_throwaway_tracker_under_the_lock`.
- medium, second avis 2 (vrai tracker jamais passé par `track()` en CI) : corrigé. `test_the_real_tracker_measures_a_local_leaf_through_track` : vrai CodeCarbon, réseau bloqué, dossier vide, `warm_up` puis `stream_into_run` → `meter.track()` dans la place, ligne `runs` en `codecarbon` avec `co2_mg` et `energy_wh` positifs, aucun CSV.
- low, second avis 3 (seconde annulation pendant le `stop`) : corrigé. `_until_done` attend le fil jusqu'au bout malgré des annulations répétées, puis relaie l'annulation ; même chose pour l'arrêt du tracker d'un démarrage annulé. Preuve : `test_a_second_cancellation_during_stop_keeps_the_lock_until_the_tracker_stops` (échoue sur 8778fba).
- low, second avis 4 (`start` qui lève après avoir lancé son fil) : corrigé, le tracker construit est arrêté (`stop` sous `suppress`). Preuve : `test_a_tracker_whose_start_fails_midway_is_stopped` (échoue sur 8778fba).
- low, second avis 5 (branche `_another_instance_already_running` morte) : rejeté. Exact avec `allow_multiple_runs=True` (CodeCarbon 3.3.1 ne lève le drapeau qu'avec son fichier de verrou), mais la garde est sans coût et protège d'un changement de réglage.
- low, second avis 6 (`amend_cancelled_leaf` attend 5 s si la clôture échoue) : corrigé, `_close` lève `run.closed` avant de relayer l'échec d'écriture ; `amend_cancelled_co2` ne touche alors rien (la ligne n'est pas `cancelled`).
- info, revue : le pied de réponse « CO₂ 1,8 mg » reste reporté à la story 2.2 (report ci-dessus) ; vérifié que le serveur publie `metrics.co2`, `metrics.energy_wh` et `carbon_updated`.
