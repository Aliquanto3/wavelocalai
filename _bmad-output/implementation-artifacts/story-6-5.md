---
title: "Une équipe d'agents mène une mission l'un après l'autre (serveur)"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '8339d2c'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/reports-v2-inventaire.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
warnings: []
deferred:
  - summary: >-
      Variante conservatrice : aucune dépendance CrewAI. Un enchaînement séquentiel de la boucle d'outils de la 6.1 suffit au critère (la sortie d'un agent est l'entrée du suivant). La v1 (`crew_engine.py`) donnait aussi `allow_delegation=True` (un agent peut déléguer à un autre) ; la délégation n'est pas reprise, l'ordre est fixe. La v2 transmet explicitement le texte de l'agent précédent (tronqué à `agents.result_chars`).
    evidence: '`agents/mission.py::MissionRunner.run`, `agents/crews.py::task_for`.'
    location: src/wavelocalai/agents/mission.py
    severity: low
  - summary: >-
      Écarts additifs à confirmer. (1) `PUT /api/agents/crews/{id}` et `DELETE /api/agents/crews/{id}` ne sont pas dans le critère : sans eux « Configurer » et « Revenir à l'équipe d'origine » (Q3) n'ont aucune route. (2) `validate` rend toujours `200 {valid, errors}` (et non un `422`) pour que l'écran affiche un message par champ en direct ; `PUT` et le lancement refusent par `422`. (3) Le `model` d'un agent est facultatif (`null` = le modèle de la mission, champ `model` de la commande). (4) Pas de création d'équipe : on modifie une équipe de la bibliothèque (6.6 : « Configurer »). (5) Rôles uniques dans une équipe (`step.agent` identifie l'agent) ; longueurs bornées (rôle 60, objectif 300, contexte 500). (6) `temperature` 0,2 par défaut pour tous les agents (la v1 : 0,7), comme l'agent seul, car les petits modèles appellent mal les outils à chaud.
    evidence: '`agents/crews.py`, `web/routes_agents.py`, `tests/v2/web/test_agent_crew_api.py`.'
    location: src/wavelocalai/web/routes_agents.py
    severity: low
  - summary: >-
      Pic de mémoire : mesure du **poste** (mémoire vive occupée, total moins disponible, relevée chaque seconde), non celle des seuls modèles de la mission, car aucun relevé par processus Ollama n'existe dans la v2. Il inclut donc le reste du poste. Publié en événement `mission_totals` (durée, pic, agents terminés) plutôt qu'en colonne de `runs` (pas de migration) ; l'instantané le relit (`mission`).
    evidence: '`agents/mission.py::MissionRunner`, `runs/snapshot.py::mission_totals`.'
    location: src/wavelocalai/agents/mission.py
    severity: low
  - summary: >-
      Point d'intégration avec la 6.3 (approbation d'un outil sensible, pas encore dans cette branche) : le refus de la 6.1 est gardé pour un agent d'équipe (`tool_result` en échec, aucun envoi). Quand la 6.3 remplacera ce refus dans `AgentLoop._execute`, la boucle étant partagée, l'approbation vaudra pour l'équipe ; `step.agent` dit quel agent la demande. À vérifier à la fusion : un test d'équipe qui approuve un `send_email`.
    evidence: '`tests/v2/web/test_agent_crew_api.py::test_a_sensitive_tool_is_refused_in_a_crew_until_approval_exists`.'
    location: src/wavelocalai/agents/loop.py
    severity: low
  - summary: >-
      Rapport partiel : à l'annulation, c'est la réponse du dernier agent **terminé** (texte complet). Le texte déjà généré par l'agent interrompu n'est pas gardé (la réponse d'un tour n'est publiée qu'une fois le tour fini, 6.1). Une erreur d'un agent ne garde pas de rapport partiel (le critère ne parle que de l'arrêt). Les réponses intermédiaires sont tronquées à `agents.summary_chars` dans leur étape `answer` ; leur texte complet va à l'agent suivant.
    evidence: '`tests/v2/web/test_agent_crew_api.py::test_cancelling_keeps_the_partial_report_and_the_mission_totals`.'
    location: src/wavelocalai/agents/mission.py
    severity: low
---

# Story 6.5 : une équipe d'agents mène une mission l'un après l'autre (serveur)

## Objectif

Lancer une équipe (chercheur, analyste, rédacteur…) sur un sujet, chaque agent avec ses outils et son modèle, l'arrêter quand on veut, et garder un rapport. Serveur seulement : l'écran est la 6.6, l'approbation de l'email la 6.3.

## Critères d'acceptation et preuves

1. **Bibliothèque** : `GET /api/agents/crews` rend les équipes (agents : rôle, objectif, outils, modèle ; tâches ordonnées) ; `POST /api/agents/crews/validate` rejette une équipe sans agent, de plus de 5 agents (D-36), un outil inconnu, répété ou indisponible, un modèle inconnu ou cloud sans `allow_cloud`, avec un message par champ. Équipes de la v1 dans `config/agent_crews.json` (versionné, lecture seule) ; modification dans `preferences` (`agents.crews`) par `PUT`, `DELETE` l'efface (« Revenir à l'équipe d'origine », Q3). Preuve : `tests/v2/unit/test_agent_crews.py`, `tests/v2/web/test_agent_crew_api.py::test_the_library_*`, `::test_validate_*`, `::test_a_modification_*`, `::test_an_invalid_modification_*`.
2. **Mission** : `POST /api/agents/runs {mode: "crew", crew, topic, model?, allow_cloud}` ; un run racine `agent`, les agents en séquence (sortie de l'un dans la tâche du suivant), chacun par la boucle de la 6.1, `step.agent` renseigné, chaque appel de modèle une feuille avec son `co2` ; `agent_totals {tools, duration_s}` sur l'étape `answer` de chaque agent ; un agent non atteint ne publie rien ; seul le rapport du dernier agent part en `token`. Un outil sensible reste refusé (6.1) : point d'intégration de la 6.3. Preuve : `::test_a_mission_chains_the_agents_and_publishes_their_steps`, `::test_an_agent_that_fails_stops_the_mission_*`, `::test_a_sensitive_tool_is_refused_in_a_crew_*`, `::test_start_errors_run_nothing`, `::test_a_second_mission_*`, et, contre le vrai Ollama (`qwen2.5:1.5b`), `tests/v2/integration/test_agent_ollama.py::test_real_ollama_runs_a_two_agent_crew_*`.
3. **Annulation** : l'agent courant est coupé, le run finit `cancelled`, le rapport partiel est gardé dans la conversation ; une mission terminée garde son rapport final, rouvrable ; `GET /api/runs/{id}` porte `mission {duration_s, peak_memory_gb, agents_done}`. Preuve : `::test_cancelling_keeps_the_partial_report_*`, `::test_cancelling_the_first_agent_*`, `::test_a_mission_chains_*` (conversation et `mission`).
4. **Contrat** : `contrat-api.md`, « Équipe (story 6.5) », événement `mission_totals`, ligne Équipe de « Par écran ».

## Règles écrites

- **Couches** : `agents/` n'importe pas `store` ; `CrewLibrary` reçoit un `PreferenceStore` structurel (protocole local). Aucun SDK ni `psutil` au niveau du module (`hardware/memory.py` importe `psutil` à l'appel).
- **Consigne d'un agent** : rôle, objectif, contexte, rang dans l'équipe ; la tâche reprend la formulation de la v1 (« Analyse le sujet… ») et, après le premier agent, le texte de l'agent précédent.
- **Boucle** : `AgentLoop.run` recevait déjà `agent` et `stream_answer` (prévus en 6.1) ; la 6.5 y ajoute `agent_totals`. Un seul `AgentLoop` par mission : `step_id` contigu sur tout le run.

## Notes de développement

- Nouveaux : `agents/crews.py`, `agents/mission.py`, `config/agent_crews.json`. Modifiés : `agents/service.py` (`_start_crew`), `agents/loop.py` (`agent_totals`), `web/routes_agents.py`, `web/app.py`, `runs/snapshot.py` (`mission`), `config.py` et `wavelocalai.toml` (`memory_sample_s`), `contrat-api.md`.
- Aucune dépendance nouvelle, aucun fichier du front, aucun code d'erreur nouveau.

## Rapport de dev

- Tests : `test_agent_crews.py` (10), `test_agent_crew_api.py` (13), `test_layers.py`, `test_agent_api.py`, `test_agent_tools_api.py`, `test_agent_tools.py`, `test_config.py`, `test_runs_api.py` ; intégration Ollama (`test_agent_ollama.py`, 2, `qwen2.5:1.5b` installé, aucun téléchargement). Aucun E2E, aucune suite complète (poste partagé).

## Revue

- medium · second avis · corrigé · `check_params` (AD-7) refusait tout sujet court contenu dans un identifiant des `params` (sujet « duo » ou « carbone », équipe `comparaison_carbone`, rôle, outil) : `ValueError` du hub, 500 sans run ; défaut déjà latent pour l'agent seul (tâche « calculator »). Le texte saisi n'est plus cherché dans les valeurs qu'à partir de `MIN_TYPED_MATCH` (20) caractères ; clés réservées et valeurs de plus de 256 caractères toujours refusées pour tous les runs. Tests : `test_hub.py::test_run_params_never_hold_typed_text`, `test_agent_crew_api.py::test_a_short_topic_found_in_the_crew_identifiers_still_starts`.
- low · second avis · corrigé · `_on_cancel` publiait le rapport partiel sur la lane de l'agent interrompu : `_Mission.lane` est désormais celle de l'agent qui a écrit `last_output`.
- low · second avis · rejeté · le `pytest.skip` cité est celui du test de l'agent seul (6.1) ; le test d'équipe n'a pas d'outil et ne se saute que si Ollama ou le modèle manque (passé contre `qwen2.5:1.5b`).
- low · revue · rejeté · `PUT`/`DELETE /api/agents/crews/{id}` hors critère : variante acceptable, Q3 exige d'enregistrer une modification et de revenir à l'origine, aucune autre route ne le permet ; consigné en écart additif.
- info · revue · vérifié · D-36 (5 agents au plus) contrôlé par `validate` et au lancement (`check`) ; les trois équipes livrées passent `validate` contre le vrai registre d'outils ; outil sensible toujours refusé en équipe (point d'intégration 6.3 consigné) ; annulation : hook idempotent (`totals_sent`, `reported`), aucun `await` entre la publication du rapport et l'état.
- Complexité : 0 constat (bibliothèque de 3 équipes, une lecture de `preferences` par équipe ; aucun parcours complet par événement ajouté).
