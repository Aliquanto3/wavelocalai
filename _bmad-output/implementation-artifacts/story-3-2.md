---
title: "L'écran Arène affiche les colonnes en flux"
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '2eed892'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-2.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-1.md'
warnings: []
deferred:
  - summary: >-
      La notation est la story 3.3 : l'écran affiche seulement le statut `judging` (« Notation ») s'il arrive, sans note `/100`, sans critères repliés, sans avertissement « note peu fiable ». Le formulaire n'envoie ni `judge` ni `criteria`. Une lane `done` accepte un `judging` ensuite (seuls timeout, failed, cancelled et interrupted sont définitifs) : l'ordre `done` puis `judging` ou `judging` puis `done` que choisira la 3.3 marche des deux façons.
    evidence: |-
      `test_a_notation_status_is_shown_as_a_status_only` (`tests/v2/e2e/test_arena.py`).
    location: src/wavelocalai/web/static/components/wl-arena-lane.js
    severity: low
  - summary: >-
      Rouvrir par URL (story 3.6) : `#/arene/comparer/<run_id>` suit le run en rejouant son flux depuis le début (le serveur garde `run_events`), ce qui reconstruit colonnes, statuts et mesures d'un run terminé sans relancer de modèle. L'URL n'est pas posée au lancement : changer le `hash` démonte l'écran et casserait le flux en cours. Reconstruction depuis l'instantané (verdict, classement) et pose de l'URL à `run_ended` sont à décider avec la 3.4 et la 3.6. Un run inconnu dit « Cette comparaison est introuvable ».
    evidence: |-
      `test_a_running_arena_is_joined_on_run_busy_and_by_its_url`, `test_an_unknown_run_in_the_url_is_said`.
    location: src/wavelocalai/web/static/screens/arena.js
    severity: low
  - summary: >-
      Hors périmètre, pour les stories suivantes : classement et matrice (3.4), actions Relancer, Modifier la question et Exporter (UX-DR20, 3.4 et 3.5). Le mode focus est une bascule d'affichage de l'écran, sans effet serveur.
    evidence: |-
      Critères de la story 3.2 de `epics.md`.
    location: _bmad-output/planning-artifacts/epics.md
    severity: low
  - summary: >-
      Huit symboles d'état ajoutés au sprite `icons.svg` (`hourglass-empty`, `sync`, `edit`, `gavel`, `timer`, `block`, `open-in-full`, `close-fullscreen`) sont des Material Icons 24 px (même licence Apache 2.0), pas des Material Symbols Rounded comme le reste du sprite : aucun jeu Symbols n'était disponible hors ligne. À remplacer par les Symbols Rounded au prochain passage sur le sprite pour homogénéiser le tracé.
    evidence: |-
      `test_every_lane_status_of_the_server_has_a_text_and_an_icon`.
    location: src/wavelocalai/web/static/icons.svg
    severity: low
---

# Story 3.2 : l'écran Arène affiche les colonnes en flux

## Objectif

`#/arene/comparer` (onglet « Arène », passé à `available`) : la personne choisit une question (champ, scénarios prédéfinis) et 2 à 4 modèles (`wl-model-picker` en mode multi, présélectionné sur le défaut `arena`), lance la comparaison, et voit une colonne par modèle se remplir au fil du flux, avec son statut en texte et en icône, ses mesures et un bandeau « Comparaison en cours · 2 sur 3 · 0:42 » qui porte Arrêter (et Échap). Côté serveur, tout existe depuis la 3.1.

## Critères d'acceptation et preuves

1. Écran, formulaire et défauts : champ Question (prérempli du scénario « Vulgarisation » : l'Arène marche sans rien toucher), scénarios Vulgarisation, Extraction JSON, Résumé, Traduction qui remplissent la question, sélecteur multi sur le défaut `arena`, phrase d'exécution. Avec moins de 2 modèles, « Lancer la comparaison » est désactivé et sa légende visible (reliée par `aria-describedby`) dit « Choisissez au moins 2 modèles » ; de même « Choisissez au plus 4 modèles » et « Saisissez une question ». Preuve : `test_the_screen_opens_with_the_form_the_scenarios_and_the_default_models`, `test_under_two_models_the_launch_is_disabled_with_a_visible_reason`.
2. Colonnes en flux : une colonne par modèle (2 à 4) avec nom, badge d'origine, statut en texte et icône (En attente, Chargement du modèle en mémoire, Génération, Notation, Terminé, Délai dépassé, Échec, Arrêté), débit provisoire puis final, premier token, tokens, chargement, durée, et la réponse en Markdown sûr avec « Afficher toute la réponse ». Une colonne qui attend son tour n'a pas de réponse ni de durée qui court. Le bandeau compte les lanes finies et porte Arrêter. Preuve : `test_a_comparison_fills_one_column_per_model_with_status_and_final_measures`, `test_local_lanes_wait_for_their_turn_and_the_banner_counts_finished_lanes`, `test_show_the_whole_answer_lifts_the_height_limit`.
3. Délai dépassé et échec : la colonne dit « Délai dépassé pour ce modèle. Les autres continuent. » (ou l'erreur `wl-error` de la lane en échec), le partiel reste, les autres colonnes finissent. Preuve : `test_a_lane_in_timeout_and_a_lane_in_failure_do_not_stop_the_others`.
4. Mise en page : 1 440 px et plus, toutes les colonnes ; de 768 à 1 439 px, deux colonnes visibles avec défilement horizontal et en-têtes collants ; sous 768 px, onglets par modèle (`tablist`, flèches, Début et Fin) ; mode focus par colonne. Preuve : `test_between_1024_and_1439_px_two_columns_are_visible_with_a_horizontal_scroll`, `test_from_1440_px_every_column_is_visible_without_horizontal_scroll`, `test_under_768_px_the_arena_becomes_tabs_by_model`, `test_the_focus_mode_enlarges_one_column_and_hides_the_others`.
5. Arrêt, reprise et run déjà actif : Arrêter et Échap annulent le parent, toutes les lanes passent à « Arrêté », les partiels restent ; quitter l'écran puis revenir reprend le flux par `?after=` sans perte ni doublon ; `409 run_busy` rejoint l'Arène active sans erreur, de même `#/arene/comparer/<run_id>`. Preuve : `test_stop_cancels_every_lane_and_keeps_the_partial_answers`, `test_escape_stops_the_comparison`, `test_the_stream_resumes_by_after_without_loss_or_duplicate_after_a_visit_to_home`, `test_a_running_arena_is_joined_on_run_busy_and_by_its_url`.
6. Accessibilité : axe-core sans violation, clair et sombre, formulaire, comparaison en cours et terminée (lane en échec et en délai), onglets, mode focus, mode projection ; bouton plein en `primary-fill` (A19, test de dérive `test_shell_static.py` vert, aucune couleur en dur) ; une seule annonce polie de fin faite par l'écran (les fils des colonnes sont muets) ; aucune requête hors de 127.0.0.1. Preuve : `test_axe_finds_no_violation_on_the_arena_screen`, `test_axe_finds_no_violation_in_projection_mode`, `test_every_request_stays_on_127_0_0_1`, `tests/v2/unit/test_arena_static.py`.

## Fichiers

- `src/wavelocalai/web/static/screens/arena.js` : l'écran (formulaire, bandeau, un lecteur du flux, onglets, mode focus)
- `src/wavelocalai/web/static/components/wl-arena-lane.js` : la colonne (en-tête collant, statut, fil muet)
- `src/wavelocalai/web/static/arena.css`, `index.html`, `i18n/fr.json`, `icons.svg` : styles, textes, icônes d'état
- `core/registry.js` (`arena-compare` disponible), `core/api.js` (`startArena`), `core/format.js` (`formatClock`)
- `components/wl-chat-thread.js` (options `firstToken` et attribut `silent`), `components/wl-model-picker.js` (`modelFor`, `selectedModels`)
- `src/wavelocalai/web/routes_test.py` : `POST /api/test/arena` (lanes `fake` scriptées par le vrai service, `WAVELOCALAI_TESTING` seulement)
- Tests : `tests/v2/e2e/test_arena.py`, `tests/v2/unit/test_arena_static.py`, `tests/v2/web/test_arena_api.py` ; réalignés : `test_shell_static.py`, `test_chat_static.py`, `e2e/test_shell.py`, `e2e/test_chat.py` (l'écran Arène n'est plus « à venir »)

## Reports

Voir `deferred` : notation (3.3), rouvrir par URL et verdict (3.4, 3.6), classement et actions (3.4, 3.5), tracé des icônes d'état.

## Revue

Revue Opus du 2026-10-18 sur `2eed892..1612fe2`, une passe. E2E de l'Arène joués (mise en page 1 200 px, 1 440 px, 600 px, mode focus, axe clair, sombre et projection) : verts.

- medium, second avis 1 : corrigé. Un `run_ended` en `error` (échec de l'orchestration, `arena.py`) était dit « Comparaison interrompue », sans la cause publiée par le hub. Le bandeau dit « Comparaison en échec », l'annonce aussi, et le `wl-error` de l'écran montre l'enveloppe du serveur (à défaut, `arena.run_failed`). Preuve : `test_an_orchestration_failure_is_said_with_its_cause` (flux simulé, rouge sans le correctif).
- medium, revue : corrigé. Mode focus actif puis passage sous 768 px : l'onglet choisi pouvait désigner une colonne masquée par le focus, et aucune colonne n'était visible. Le passage en onglets quitte le mode focus. Preuve : `test_the_focus_mode_is_left_when_the_arena_becomes_tabs` (rouge sans le correctif).
- low, second avis 2 : reporté. Un flux de run figé sans fermeture n'est pas détecté (`connectRun` sans `idleMs`), comme pour le chat. Un chien de garde côté client exige d'abord un battement de cœur serveur sur les flux de run : une lane locale qui attend le sémaphore ou charge son modèle peut rester muette plusieurs minutes, et un délai d'inactivité seul la déclarerait perdue à tort. Le flux système, lui, signale déjà un serveur mort (bandeau de connexion). À traiter dans `core/sse.js` et `routes_runs.py` pour tous les écrans.
- low, développeur : reporté (déjà en `deferred`). Les 8 icônes d'état sont des Material Icons 24 px, pas des Symbols Rounded : aucun jeu Symbols n'est disponible hors ligne sur ce poste, et AGENTS.md interdit d'en figer un de mémoire. `close-fullscreen` est d'ailleurs inutilisé (le bouton de focus garde `open-in-full` et `aria-pressed`).
- low, développeur : accepté. Question préremplie du scénario « Vulgarisation » : conforme à EXPERIENCE.md, « Défauts qui marchent sans rien toucher ».
- low, développeur : accepté. Légendes « Choisissez au plus 4 modèles » et « Saisissez une question » : même mécanisme que la légende exigée, reliée par `aria-describedby`.
- low, revue : rejeté. `wl-model-picker.selectedModels` n'a pas d'appelant ; sans effet, gardé pour la 3.4.
- Complexité : 0 constat. Comptages et mises à jour d'onglets en O(colonnes) (4 au plus) ; le rendu Markdown du fil est déjà limité dans le temps (`RENDER_MS`).
