---
title: 'Publier l''état du système en direct et ouvrir la session carbone'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'eb81d58'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-4.md'
warnings: []
deferred:
  - summary: >-
      Personne ne publie encore `carbon_updated` : la mesure par feuille (CodeCarbon, ecologits) arrive avec la story 2.3, qui appellera `announce_carbon_updated(bus, store, session_id)` après chaque `hub.finish_leaf`. Le port, l'aide et le flux sont livrés et éprouvés ici avec un producteur de test.
    evidence: |-
      `greenops/session.py::announce_carbon_updated`, `tests/v2/unit/test_carbon_session.py`.
    location: src/wavelocalai/greenops/session.py
    severity: low
  - summary: >-
      `POST /api/carbon/session/reset` (ouvre une nouvelle `app_session`, `hub.new_app_session("reset")` existe déjà) et l'historique carbone appartiennent à la story Sobriété ; ici seule la lecture de la session courante.
    evidence: |-
      `contrat-api.md` : « Sobriété » liste la remise à zéro.
    location: src/wavelocalai/web/routes_system.py
    severity: low
  - summary: >-
      La fiche machine rend la version d'Ollama que la sonde a vue en dernier (aucun appel réseau, exigé par le critère) : `null` tant qu'aucun échantillon du flux ni `GET /api/health` n'a vu Ollama ; la fiche exportée par Sobriété devra donc être demandée après l'ouverture de l'écran. Un accès à l'état en cache de la sonde (sans la relancer) la lèverait, mais touche `models/ollama_probe.py` (hors périmètre ici).
    evidence: |-
      `SystemSampler.ollama_version`, `test_identity_has_no_ollama_version_before_the_probe_saw_it`.
    location: src/wavelocalai/web/system_state.py
    severity: low
  - summary: >-
      Le GPU (mémoire utilisée, température, bridage) n'est pas dans le flux de 2 s : NVML est lent à initialiser et le critère ne le demande pas. `hardware/nvml.py` et `machine_state.py` sont copiés et testés pour l'export de preuve et la jauge GPU des stories suivantes.
    evidence: |-
      `hardware/machine_state.py` : aucun appelant dans `web/` à ce jour.
    location: src/wavelocalai/hardware/
    severity: low
  - summary: >-
      Un client lent du flux perd les plus anciens événements de sa file (64) plutôt que de faire grossir la mémoire ; `carbon_updated` portant la somme complète, le suivant corrige. Une file saturée de `system_state` n'arrive qu'en cas de client bloqué.
    evidence: |-
      `SystemFeed.publish`, `test_a_slow_client_loses_the_oldest_events_not_the_memory`.
    location: src/wavelocalai/runs/system_bus.py
    severity: low
---

# Story 1.7 : le système publie son état en direct et la session carbone existe

## Objectif

L'écran d'accueil sait à tout instant si le poste est prêt : Ollama, processeur, mémoire, modèles chargés, runs actifs et CO2 de la session, sans que le consultant clique. Les services publient leurs événements système par un port, sans connaître le flux.

## Critères d'acceptation et preuves

1. `GET /api/system/stream` : enveloppe d'AD-6 (`run_id: null`), trame `data:` seule (ni `id:` ni `event:`), sans rejeu (`Last-Event-ID` ignoré), toutes les 2 s : `ollama {up, version, latency_ms}`, `cpu_percent`, `memory {used_gb, total_gb, percent}`, `models_loaded` (`/api/ps` : `tag`, `size_gb`, `vram_gb` ; `null` si Ollama ne répond pas), `runs_active = [{run_id, kind, status}]`. Preuve : `tests/v2/web/test_system.py` (trame, rafraîchissement, runs actifs, Ollama arrêté).
2. Port `SystemBus` défini dans `runs/system_bus.py` (`publish(event_type, data)`), implémenté par `SystemFeed` ; un événement publié (ex. `carbon_updated`) part sur le flux. Preuve : `test_system_bus.py`, `test_services_publish_to_the_stream_through_the_port`.
3. Pause et reprise côté serveur, sans fuite : la mesure ne tourne que s'il y a un client (démarrée à la première connexion, arrêtée à la dernière déconnexion, reprise à la suivante) ; l'abonnement se referme dans le `finally` du flux (déconnexion ASGI, annulation de tâche) ; l'arrêt du serveur termine les flux ouverts. Preuve : `test_disconnect_releases_the_subscriber_and_pauses_the_measure`, `test_server_shutdown_ends_the_open_streams`, `test_subscription_is_released_when_the_client_task_is_cancelled`.
4. `hardware/` : copies adaptées de `accelerator.py`, `HardwareMonitor` (v1), `hardware.py` (`fiche.py`), `nvml.py` et `machine_state.py` (archive), sans importer `src.*` ; `pynvml` et `psutil` importés dans les fonctions, GPU absent = « aucun », jamais d'erreur. Preuve : `test_hardware.py`, `test_layers.py`.
5. `GET /api/system/identity` : OS, processeur (cœurs), mémoire, accélérateur (nom, pilote, CUDA, mémoire), version d'Ollama, sans aucun appel réseau (le test coupe `socket.connect` et la sonde). Fiche capturée une fois par processus, préchauffée au démarrage. Preuve : `test_identity_returns_the_machine_card_without_any_network_call`.
6. `GET /api/carbon/session` : somme des `co2.mg` des runs feuilles de l'`app_session` courante, par module (genre du run racine), Local et Cloud, avec les non-mesurables comptés à part (jamais 0) ; sans run : total 0 mg, 0 non-mesurable ; les runs parents ne sont jamais comptés (test avec un run composite, y compris une ligne parent corrompue qui porterait un `co2`) ; une remise à zéro (`hub.new_app_session`) repart de 0. Preuve : `test_carbon_session.py`, `test_carbon_session_empty_then_sums_leaves_and_never_the_composite_parent`.
7. Budget de lecture : `identity` et `carbon/session` entrent d'office dans le test de budget (< 300 ms, Ollama injoignable), le flux en est exclu. `test_layers.py` reste vert. Preuve : `test_read_budget.py`, `test_new_get_routes_enter_the_read_budget_and_the_stream_stays_out`.

## Fichiers

- `src/wavelocalai/hardware/` : `accelerator.py`, `monitor.py`, `fiche.py`, `nvml.py`, `machine_state.py`
- `src/wavelocalai/runs/system_bus.py` : `SystemBus` (port), `SystemFeed`
- `src/wavelocalai/greenops/session.py` : `session_summary`, `announce_carbon_updated`
- `src/wavelocalai/models/ollama_ps.py` : lecture de `/api/ps`
- `src/wavelocalai/web/` : `routes_system.py`, `system_state.py`, `app.py` (câblage, préchauffage, fermeture du flux)
- `tests/v2/` : `unit/{test_system_bus,test_hardware,test_carbon_session}.py`, `web/test_system.py`
- Aucune dépendance ajoutée (`psutil` et `nvidia-ml-py` sont déjà déclarées) ; `errors.py` inchangé (aucun code nouveau).

## Choix notables

- `SystemFeed` porte à la fois le bus et la mesure à la demande : un seul objet à fermer, un seul endroit où se décide « pause ». `seq` du flux système croît pour la vie du serveur (jamais remis à 1 par client) : informatif, sans rejeu.
- L'événement périodique s'appelle `system_state` ; `runs_active` en est un champ (critère de la story), pas un événement distinct.
- Module d'un CO2 = genre du run racine (parent d'une feuille enfant, sinon le run lui-même). Origine absente d'une feuille : déduite de la méthode (`ecologits` = Cloud, sinon Local).
- Hors cycle de vie (app sans hub, comme dans le test de budget), `GET /api/carbon/session` rend la session vide plutôt qu'une `500`.
- Les tests lisent le flux par un client ASGI brut : httpx met toute la réponse en mémoire, ce qui interdit de lire un flux ouvert ou de simuler une déconnexion.

## Reports

Voir l'en-tête `deferred` : publication de `carbon_updated` (2.3), remise à zéro et historique (Sobriété), version d'Ollama de la fiche, jauge GPU, file saturée d'un client lent.

## Revue

- HIGH, second avis 1, corrigé : uvicorn attend la fin des connexions avant `lifespan.shutdown`, donc un `/api/system/stream` ouvert, ou le flux `/api/runs/{id}/events` d'un run actif (1.4), bloquait l'arrêt sans fin (reproduit en serveur réel : « Waiting for connections to close » au-delà de 15 s). `web/server.py` : `_Server.shutdown` ferme l'écoute puis appelle `stop_streams` (flux système fermés, `hub.stop()` qui passe les runs actifs à `cancelled`) **avant** l'attente d'uvicorn ; filet `timeout_graceful_shutdown = 5 s`. Preuve : `tests/v2/web/test_real_shutdown.py` (vrai serveur, deux flux ouverts, Ctrl+Break ou SIGINT : sortie en moins de 4 s, « Application shutdown complete », run `cancelled`), qui échoue sans le correctif.
- MEDIUM, second avis 2, corrigé : une feuille close sans `co2` (erreur, annulation, arrêt) sortait du total et du compte des non-mesurables. `greenops/session.py` compte toute feuille terminée (`ended_at` renseigné), une feuille sans `co2` étant non-mesurable ; `inference/streaming.py` passe aussi le `co2` sur le chemin d'erreur (AD-10 : `co2` partout). Le test qui entérinait l'oubli est réécrit, `test_fake_model.py` vérifie le `co2` de la feuille en erreur.
- MEDIUM, second avis 3, corrigé par le contrat : le flux système n'a pas de rejeu (contrat), donc pas de rejeu du dernier `carbon_updated`. `contrat-api.md` précise que le client lit `GET /api/carbon/session` à chaque (re)connexion du flux, après l'ouverture, puis applique les `carbon_updated` (à suivre par la 1.9). API des routes et des événements inchangée.
- low, second avis 4, reporté : le budget de `/api/system/identity` est mesuré sur cache chaud ; la capture NVML à froid est préchauffée au démarrage. À chronométrer sur la tour RTX 3050 (premier appel juste après le lancement).
- low, second avis 5, rejeté : le générateur du flux est fermé par `EventSourceResponse` à la déconnexion, et l'abonnement se referme dans le `finally` du `with` (testé par `test_subscription_is_released_when_the_client_task_is_cancelled`).
- low, second avis 6, rejeté : `test_real_launch.py` sous cp1252, déjà corrigé sur master.
- low, revue, reporté (hors story) : sous Windows, Ctrl+Break fait relever SIGBREAK par uvicorn après l'arrêt, ce qui termine le processus sans passer par les `finally` du lanceur (`store.close`, `lock.release`). L'arrêt du hub est fait avant ; vérifier à la story du lanceur si la base WAL et le verrou doivent être libérés explicitement.
