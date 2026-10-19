---
title: "L'écran Agent seul montre chaque étape et demande la validation"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '7db423c'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-1.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-3.md'
warnings: []
deferred:
  - summary: >-
      Écart nouveau, variante conservatrice (AD-20) : le pied de la réponse dit « CO₂, nombre d'étapes, durée » d'**une tâche**, mais le CO₂ n'existe que par appel de modèle (une feuille `generation` par tour) et la racine `agent` n'a aucune mesure. Le front ne les additionne pas : l'instantané `GET /api/runs/{id}` d'un run `agent` porte désormais `totals {turns, steps, duration_s, co2}`, calculé par le serveur (`runs/agent_totals.py`). Règle du CO₂ : somme des feuilles mesurées ; `unmeasurable` (`mg: null`, `reason`) dès qu'une feuille ne l'est pas, jamais une somme partielle ; `estimated` si une feuille l'est. Contrat mis à jour (« Agents (story 6.4) »).
    evidence: |-
      `tests/v2/unit/test_agent_totals.py`, `tests/v2/web/test_agent_api.py::test_the_snapshot_of_an_agent_run_carries_server_computed_totals`, `contrat-api.md`.
    location: src/wavelocalai/runs/agent_totals.py
    severity: low
  - summary: >-
      Variante conservatrice de la 6.1 gardée et rendue visible : la réponse finale arrive **en un bloc** à la fin du dernier tour (pas de frappe progressive). L'écran le dit à la personne par une ligne d'aide sous le fil (« La réponse de l'agent s'affiche d'un bloc, à la fin de sa dernière étape »), et `wl-run-status` dit « Réflexion… » pendant l'attente. À faire confirmer par Anaël à la recette ; sinon variante avec requalification du texte du tour (événement au contrat, purge de `run.answer` par le hub).
    evidence: |-
      `tests/v2/e2e/test_agents_solo.py::test_the_answer_arrives_as_one_block_and_the_screen_says_so`.
    location: src/wavelocalai/web/static/screens/agents-solo.js
    severity: medium
  - summary: >-
      Écarts nouveaux, variante conservatrice, sans décision d'Anaël. (1) D-17 (`wl-model-picker` filtré sur l'éligibilité de l'usage) est assigné aux stories 5.4 et 5.6 et l'API n'expose aucun champ d'éligibilité : le sélecteur de l'Agent n'est pas filtré (un modèle sans outils vérifiés reste choisissable avec l'avertissement de D-32, ce que l'épique exige). (2) Icônes des étapes prises dans le sprite actuel (`smart-toy`, `sync`, `check`, `error`, `description`, `hourglass-empty`, `block`) : aucun symbole n'est dessiné à la main avant le sprite officiel d'Anaël. (3) Pas de curseur de créativité (température du serveur, 0,2), pas de bibliothèque de scénarios de la v1, pas de réouverture de la dernière conversation d'agent ni de reprise après rechargement de la page (le flux se reprend seulement en revenant sur l'écran, ou en rejoignant le run actif sur `409 run_busy`). (4) Le bouton « Arrêter » du pied de saisie de l'EXPERIENCE est celui de `wl-run-status` (et Échap), pas un second bouton. (5) Actions rapides : « Audit du système » et « Analyse de données » de la v1 (le CSV s'appelle `ventes.csv`, dans le dossier de travail de l'agent), et la carte « Sobriété » reste une phrase, comme en v1.
    evidence: |-
      `tests/v2/e2e/test_agents_solo.py`, `tests/v2/unit/test_agents_static.py`.
    location: src/wavelocalai/web/static/screens/agents-solo.js
    severity: low
---

# Story 6.4 : l'écran Agent seul montre chaque étape et demande la validation

## Objectif

`#/agents/seul` (module Agents passé à `available`, onglet « Équipe d'agents » désactivé avec sa raison) : la personne confie une tâche à l'agent, voit chaque étape arriver dans le panneau « Étapes », déplie celle qu'elle veut sans perdre le focus, valide ou refuse l'email dans un dialogue, et lit la réponse finale avec un pied réduit. Front seul, plus le strict nécessaire au pied (totaux calculés par le serveur) et à la preuve (route de test).

## Critères d'acceptation et preuves

1. **Réglages** : `h1` « Agent seul » (décision n° 15) ; `wl-model-picker purpose="agent"` avec sa raison (sans défaut : la raison du serveur, « Choisissez un modèle avec outils vérifiés », lancement désactivé) ; avertissement D-32 pour un modèle sans outils vérifiés, lancement permis ; neuf outils en interrupteurs (`role="switch"`, D-6), tous activés sauf l'outil `sensitive` (« Envoi d'email »), un outil indisponible `aria-disabled` focalisable, non activable, avec sa raison ; accueil « Bonjour ! L'agent est prêt. » et actions rapides qui remplissent la saisie sans l'envoyer. Preuve : `test_agents_solo.py::test_settings_*`.
2. **Panneau « Étapes »** : à droite dès 1 024 px, sous la réponse en deçà, toujours déplié, sans bouton de repli (D-30). `wl-step-trace` : liste ordonnée, une étape par `step` (icône, libellé, durée, agent), motif de divulgation APG ; une étape se déplie (« Arguments » en JSON mis en forme, « Résultat », « Ouvrir le fichier » si `artifact_url`) pendant que les suivantes arrivent, le focus et l'état déplié sont conservés ; l'étape en cours est marquée « en cours » ; la liste n'est pas `aria-live`. Composant générique : le champ `agent` du `step` (`null` en agent seul) est affiché quand il existe, pour la 6.6. Preuve : `::test_steps_arrive_in_order_and_one_can_be_opened_while_the_next_ones_arrive`.
3. **`wl-run-status`** (mode `first-stage="thinking"`) : « Réflexion… » au lancement et après chaque `tool_result`, « Appel de l'outil <libellé>… » entre `tool_call` et `tool_result`, « En attente de votre validation » entre `approval_required` et `approval_resolved`, « Génération… » à l'étape `answer`. Preuve : `::test_the_status_follows_the_steps`.
4. **Réponse** : un seul `token` à la fin du dernier tour, rendu dans `wl-chat-thread` (Markdown sans astérisques visibles : gras, séparateur, italique), pied réduit (CO₂, étapes, durée ; ni débit, ni tokens, ni chargement, D-31), puis « Télécharger » (lien vers `GET /api/conversations/{id}.md`, sans `blob:`). Preuve : `::test_the_answer_arrives_as_one_block_and_the_screen_says_so`, `::test_the_reduced_footer_and_the_download`.
5. **Validation de l'email** : `approval_required` ouvre `wl-confirm-dialog` (« Envoyer cet email ? », Destinataire, Objet, Corps en lecture seule et défilable, mention de l'expiration, focus sur « Annuler ») ; « Envoyer l'email » approuve, « Annuler » (ou Échap) refuse, par `POST /api/runs/{id}/approvals/{approval_id}` ; le résultat est inscrit dans la trace et annoncé au même verbe (« Email envoyé. », « Envoi annulé : l'agent en est informé. », « Validation expirée : email non envoyé. »). `approval_resolved` venu du serveur (expiration, run annulé) ferme le dialogue ; une réponse tardive refusée en `409 approval_not_pending` est dite sans erreur technique. Avec un faux SMTP local : approuvé = un message reçu, annulé = aucune connexion. Preuve : `::test_an_email_is_sent_only_after_approval`, `::test_cancel_sends_nothing`, `::test_the_server_closing_the_request_closes_the_dialog`.
6. **Garde-fou mémoire** : `ram_guard` s'applique comme au Chat (question gardée dans le champ, besoin chiffré, deux actions), sans « Libérer la mémoire » de la v1. Retour sur l'écran : la trace reprend par `?after=`. axe-core sans violation, clair et sombre. Preuve : `::test_the_memory_guard_*`, `::test_leaving_and_coming_back_resumes_the_trace`, `::test_axe_*`.
7. **Aucun calcul de métrique** : CO₂, étapes et durée du pied viennent de `totals` (serveur) ; le front ne fait que les mettre en forme (AD-20). Preuve : `test_agents_static.py`.

## Règles écrites

- **Un seul lecteur du flux d'un run** : l'écran (`connectRun`), qui passe chaque enveloppe à `wl-run-status` (mode piloté) et à la trace.
- **Contrats partagés réutilisés** : `screenTabs`, `ram-guard.js`, `wl-confirm-dialog` (étendu : `details` et `note`), `format.js`, `export` par route du serveur. Aucun fichier JS du front au-delà de 600 lignes.
- **Textes** : `i18n/fr/agents.json` (écran) et `components.*` (trace, statut, dialogue) ; CSS : `css/components/step-trace.css` (composant), `agents.css` (écran).
- **Test E2E** : la route de test `POST /api/test/chat-model` accepte des appels d'outil (`{"tool_call": {id, name, arguments}}`) ; SMTP : faux serveur local en processus, aucun email réel.

## Notes de développement

- Nouveaux : `screens/agents-solo.js`, `agents-approval.js`, `agents-tools.js`, `components/wl-step-trace.js`, `css/components/step-trace.css`, `agents.css`, `i18n/fr/agents.json`, `core/api/agents.js`, `runs/agent_totals.py`, `test_agents_solo.py` (E2E), `test_agents_static.py`, `test_agent_totals.py`.
- Modifiés : `wl-run-status.js` (`first-stage="thinking"`, étapes « Réflexion… », « Appel de l'outil… », « En attente de votre validation » ; Échap laissé à un dialogue modal ouvert), `wl-chat-thread.js` (`reduced` et `summarize`), `wl-confirm-dialog.js` (`details`), `wl-model-picker.js` (raison affichée sans défaut), `runs/snapshot.py` (`totals`), `web/routes_test.py` (`tool_call` dans un script), `core/routes/agents.js`, `core/api.js`, `core/i18n.js`, `index.html`, `switch.css` (état indisponible de `wl-switch`), `confirm-dialog.css`, `contrat-api.md`.
- Tests réalignés (structure partagée) : `test_shell_static.py` (7 écrans disponibles), `test_shell.py` (module Agents disponible), `test_home.py` (quatre liens de modules), fixtures `components.html` et `picker.html` (feuille de la trace), `Backend(env=…)` du banc E2E (SMTP toujours vide sauf faux SMTP).
- Un serveur neuf met environ 10 s à mesurer son premier appel de modèle (compteur CodeCarbon) : les E2E qui lancent leur propre serveur l'échauffent une fois (`warm_up`).
- Aucune dépendance nouvelle, aucun fichier d'état du run.

## Rapport de dev

- Tests ciblés : unit 171 passés (agents, totaux, coquille, découpage, chat, sélecteur, couches, API agents et approbation, statique) ; E2E `test_agents_solo.py` 24 passés (Edge, clair et sombre pour axe-core) ; E2E touchés `test_shell`, `test_home`, `test_components`, `test_picker` : 110 passés ; `test_chat` et `test_memory_guard` (arrêt, garde-fou) : 6 passés. Aucune suite complète (poste partagé).
- Contrôle rapide propre. Faux SMTP local seulement : aucun email réel, aucune connexion hors `127.0.0.1`, `.env` jamais lu.
