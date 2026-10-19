---
title: "L'écran Équipe d'agents montre le schéma, la trace et le rapport"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: 'c5ca237'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-4.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-5.md'
warnings: []
deferred:
  - summary: >-
      Écart (variante conservatrice) : « Modèle » de chaque agent dans le volet Configurer est une liste native (`select`, « Modèle de la mission » = aucun modèle propre) et non un `wl-model-picker` par agent : le sélecteur préchoisit un défaut (ce qui supprimerait le sens de `model: null`) et cinq combobox chargeraient cinq fois la liste. La liste vient d'un seul `GET /api/models`.
    evidence: |-
      `tests/v2/e2e/test_agents_crew.py::test_configure_opens_a_non_modal_panel_beside_the_schema_and_saves_the_change`.
    location: src/wavelocalai/web/static/screens/agents-crew-config.js
    severity: low
  - summary: >-
      Écarts nouveaux, variante conservatrice. (1) Le `backstory` (contexte) d'un agent n'est pas éditable : il est conservé tel quel à l'enregistrement. (2) Un agent dont la mission s'arrête ou échoue est « Arrêté » (échec compris) ; les suivants « Non lancé ». (3) La mission rouverte (`#/agents/equipe/<run_id>`) montre le schéma de l'équipe **telle qu'elle a été jouée** (`params.agents`), pas l'équipe en vigueur ; le sujet vient de la conversation (jamais des `params`). (4) Le rapport d'une mission rouverte vient des `token` rejoués, sinon du dernier message `assistant` de la conversation. (5) Pas de bouton « Effacer la conversation » ni de réouverture de la dernière mission. (6) Un rôle de plus de 19 caractères est coupé sur deux lignes dans le nœud du schéma (abrégé au-delà), son nom entier est dans le `<title>` du nœud. (7) Le garde-fou mémoire (`ram_guard`) n'a pas de traitement propre à cet écran : l'erreur de `run_ended` est affichée par `wl-run-status`, et le sujet reste dans le champ.
    evidence: |-
      `tests/v2/e2e/test_agents_crew.py`, `tests/v2/unit/test_agents_crew_static.py`.
    location: src/wavelocalai/web/static/screens/agents-crew.js
    severity: low
  - summary: >-
      Hors périmètre, constaté : `test_agents_solo.py::test_steps_arrive_in_order_…` échoue seul sur un serveur neuf (le premier appel de modèle met une dizaine de secondes à mesurer, avant que les trois étapes n'arrivent) et passe dès qu'un test a chauffé le serveur du module. Le fichier d'équipe a une fixture `warm_up` de module ; le fichier de l'Agent seul n'en a pas.
    evidence: |-
      Lancé seul, le test échoue ; dans la même exécution que `test_agents_crew.py`, il passe.
    location: tests/v2/e2e/test_agents_solo.py
    severity: low
---

# Story 6.6 : l'écran Équipe d'agents montre le schéma, la trace et le rapport

## Objectif

`#/agents/equipe[/<run_id>]` (écran passé à `available`) : choisir une équipe, voir son schéma, la configurer, lancer une mission, la suivre agent par agent, valider un email si un agent le demande, lire le rapport et le télécharger. Front, plus le point d'intégration laissé par la 6.5 : l'approbation d'email de la 6.3 s'applique à un agent d'équipe (la boucle de mission reçoit les actions sensibles, `agents/service.py`). La préversion `2.0.0a6` est posée par l'orchestrateur : ce point du critère n'est pas traité ici.

## Critères d'acceptation et preuves

1. **Écran et schéma** : `h1` « Équipe d'agents » (décision n° 15), onglets `screenTabs`, liste « Équipe » (bibliothèque), sujet proposé par l'équipe, `wl-team-graph` (SVG fait main : `<title>`, `<desc>` qui lit « Chercheur, puis Analyste, puis Rédacteur, puis le rapport », un nœud par agent puis « Rapport »), horizontal dès 768 px jusqu'à 4 agents, vertical en deçà ou à 5 agents ; l'agent actif est marqué par un contour de 3 px et le libellé « en cours » (aussi « terminé » avec coche, « arrêté », « non lancé »), jamais par la couleur seule. Sans agent : « Lancer la mission » désactivé, « Ajoutez au moins un agent » ; sans sujet : « Saisissez un sujet », relié au bouton. Preuve : `test_agents_crew.py::test_the_screen_is_equipe_d_agents_*`, `::test_the_schema_is_vertical_*`, `::test_changing_the_crew_*`, `::test_a_crew_without_agent_*`.
2. **Configurer** : volet **non modal** (colonne de droite dès 1 024 px, sous le schéma en deçà, D-35 ; focus sur son `h2`), un `fieldset` par agent (rôle, objectif, outils en interrupteurs réutilisés de l'Agent seul, modèle), « Retirer cet agent », « Ajouter un agent » désactivé à 5 agents avec « Une équipe compte 5 agents au plus : retirez un agent pour en ajouter un autre. » relié au bouton (D-36). « Enregistrer » passe par `POST /api/agents/crews/validate` (erreurs sous leur champ, `aria-describedby`, focus sur la première) puis `PUT /api/agents/crews/{id}` ; « Annuler » abandonne ; « Modifiée » et « Revenir à l'équipe d'origine » (`DELETE`, annonce « Équipe d'origine rétablie. »). La modification survit à un rechargement. Preuve : `::test_configure_opens_a_non_modal_*`, `::test_the_fifth_agent_*`, `::test_the_server_errors_*`.
3. **Suivi** : une ligne par agent (`agents-crew-track.js`) : « En attente », « En cours · Réflexion… » / « Appel de l'outil X… » / « En attente de votre validation », « Terminé · 3 outils · 41 s » (lus dans `agent_totals`, rien n'est calculé), « Arrêté », « Non lancé » (D-34) ; dépliée, elle montre la `wl-step-trace` de l'agent (réutilisée : `add`, `note`, `setCurrent`, `labelOf`, `maxTurns`, champ `agent` aiguille chaque étape) ; « Journal brut » replié, lignes horaires (« 09:15:02 Chercheur · Appel de l'outil … »), jamais du JSON (D-33) ; Arrêter et Échap annulent. Preuve : `::test_a_mission_goes_agent_by_agent_*`, `::test_stopping_with_escape_*`, `::test_stopping_before_the_first_agent_*`.
4. **Rapport** : Markdown rendu dans `wl-chat-thread` (pied réduit : CO₂, étapes, durée et **pic de mémoire** lus de `GET /api/runs/{id}` — `totals` et `mission` —, jamais additionnés ici, AD-20), « Télécharger en Markdown » par la route d'export (sans `blob:`) ; mission arrêtée : « Rapport partiel (mission arrêtée) », ou « Aucun rapport » si aucun agent n'a fini. Preuve : mêmes tests, `test_agents_crew_static.py`.
5. **Adresse** (décision n° 7, D-8) : à la fin d'un run lancé ici, `history.replaceState` écrit `#/agents/equipe/<run_id>` (sans entrée d'historique) ; la route se rouvre (flux rejoué, sujet et rapport de la conversation) ; un identifiant inconnu dit « Mission introuvable » avec un lien vers une nouvelle mission. Preuve : `::test_a_finished_mission_reopens_*`, `::test_an_unknown_mission_address_*`.
6. **Validation d'email par un agent d'équipe** : le dialogue de la 6.4 (`agents-approval.js`, `details` de `wl-confirm-dialog`) s'ouvre, l'issue s'inscrit dans la trace de l'agent qui l'a demandée ; approuvé = un message au faux SMTP local, refusé = aucune connexion. Côté serveur : `AgentLoop` de la mission reçoit `actions=build_actions(...)`. Preuve : `::test_an_email_asked_by_a_team_agent_*`, `::test_a_refused_email_*`, `tests/v2/web/test_email_approval_api.py::test_a_crew_agent_asks_for_the_same_approval_as_a_single_agent`.
7. **Accessibilité** : axe-core sans violation au repos, volet ouvert, mission en cours et finie, journal ouvert, à 320 px, clair et sombre. Preuve : `::test_axe_*`.

## Liste de parité avec la v1 (Agent seul et Équipe)

| Parcours v1 | v2 | Écart |
|---|---|---|
| Outils (9) | interrupteurs de l'Agent seul ; par agent dans « Configurer » | aucun |
| Validation d'email | dialogue unique (D2, AD-9), Agent seul et agent d'équipe | plus strict que la v1 (jamais d'envoi sans accord) |
| Garde-fou mémoire | Agent seul : `ram_guard` (6.4) ; Équipe : erreur du run affichée, sujet gardé | pas de traitement dédié à l'Équipe (nommé) |
| Équipe chargée | bibliothèque de 3 équipes de la v1, schéma | aucun |
| Équipe configurée | volet « Configurer », enregistré dans `preferences`, « Revenir à l'origine » | `backstory` non éditable ; modèle par liste native |
| Équipe lancée | mission séquentielle, suivi par agent, `agent_totals` | aucun |
| Équipe arrêtée | Arrêter / Échap, rapport partiel gardé, « Arrêté » / « Non lancé » | aucun |
| Rapport conservé | conversation `agent`, téléchargement Markdown, mission rouvrable par son adresse | aucun |

## Règles écrites

- **Un seul lecteur du flux** : l'écran (`connectRun`), qui passe chaque enveloppe à `wl-run-status` (piloté), au suivi et à la validation.
- **Contrats réutilisés** : `screenTabs`, `wl-confirm-dialog` (`details`), `wl-step-trace`, `format.js` (`formatTime` ajouté pour le journal), export par route du serveur, `switchFor` d'`agents-tools.js` (exporté). Textes : `i18n/fr/crew.json` (écran, clé `crew`) et `components.team_graph.*` ; CSS : `css/components/team-graph.css` (composant) et `agents-crew.css` (écran). Aucun fichier JS au-delà de 600 lignes (`agents-crew.js`, `-track.js`, `-config.js`).
- **`wl-chat-thread`** : `summarize` accepte `peak_memory_gb` (« Pic de mémoire », `formatGb`, inconnu jamais 0).
- **Tests de l'écran Agent seul** : l'onglet « Équipe d'agents » est un lien actif ; `test_shell_static.py` compte 8 écrans `available`.

## Revue

Revue Opus du 2026-10-19 (diff eff6d0c, 7a83bf6, f265e92 au-dessus de c5ca237, puis fusions 82298a7 et origin/master).

| Sévérité | Source | Constat | Issue | Motif |
|---|---|---|---|---|
| medium | second avis 1 | `submit` rejoignait tout run `agent` actif sur `409 run_busy` : un Agent seul en cours était suivi comme une mission. | corrigé | `joinBusy` relit le run : mission rejointe si `params.mode === "crew"`, sinon « Un agent seul travaille en ce moment… » avec le lien « Voir l'Agent seul » (`#/agents/seul`), sans suivi ; la lecture du run en échec s'affiche au lieu de rejeter la promesse. Preuve : `test_agents_crew.py::test_a_running_single_agent_is_said_with_a_link_and_not_joined_as_a_mission` (échoue sur l'ancien code). |
| low | second avis 2 | `wl-team-graph` lisait `this.#states[label]` par la chaîne prototype (rôle `constructor`, `toString`). | corrigé | `Object.hasOwn`. |
| low | second avis 3 | `MIN_TYPED_MATCH = 20` (`runs/hub.py`). | rejeté | Défense en profondeur : le sujet n'entre jamais dans les `params` (construits par le serveur), et `MAX_PARAM_TEXT` borne les valeurs longues ; déjà accepté en revue 6.5. |
| low | second avis 4 | `reopen` disait « Mission introuvable » pour toute erreur (réseau, serveur). | corrigé | « introuvable » seulement sur `run_not_found` ou un run qui n'est pas une mission ; sinon l'erreur du serveur (ou « La mission n'a pas pu être relue. »). Preuve : `::test_a_server_failure_on_reopen_is_shown_and_not_called_unknown` (échoue sur l'ancien code). |
| low | dev, confirmé | `test_agents_solo.py::test_steps_arrive_in_order_…` échouait lancé seul sur un serveur neuf (0 étape en 5 s). | corrigé | Fixture `warmed` de module (`warm_up`, puis conversations oubliées) ; le test passe seul. |
| low | revue | L'Agent seul (`agents-solo.js`, 6.4) rejoint de même sans vérifier le mode une mission d'équipe active sur `409 run_busy`. | reporté | Hors du diff de la story (écran 6.4) ; à traiter comme ici (`params.mode === "solo"`, sinon lien vers `#/agents/equipe/<run_id>`). |
| — | revue | Approbation d'email en équipe (`actions=build_actions`), `PUT`/`DELETE` de l'équipe, 5 agents (serveur et bouton), adresse réécrite par `replaceState`, mission rouverte, parité v1 : vérifiés. | aucun défaut | Tests web et E2E de la story passés. |
| — | revue | Complexité : journal brut en ajout seul, suivi et schéma bornés à 5 agents (signature de rendu), jetons passés à `wl-chat-thread` existant. | aucun constat | Aucun parcours complet par événement sur une structure non bornée. |
