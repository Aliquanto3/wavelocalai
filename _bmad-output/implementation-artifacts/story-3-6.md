---
title: "Rouvrir, exporter, relancer et effacer l'Arène, et la lancer depuis l'Accueil (Flow 1, préversion 2.0.0a3)"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: 'cf2e079'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-5.md'
warnings: []
deferred:
  - summary: >-
      Écart §7(d) n° 7, non tranché : l'adresse n'est pas réécrite à la fin d'un run (`history.replaceState` vers `…/<run_id>`), l'Arène de la maquette le fait, l'Équipe non. Variante la plus conservatrice (critère actuel, qui ne la demande pas) : l'adresse de la comparaison en cours reste `#/arene/comparer`, changer le `hash` démonterait l'écran et casserait le flux (story 3.2). La porte d'entrée pour rouvrir est la liste « Comparaisons précédentes » de l'écran (`GET /api/arena/runs`) et l'adresse `#/arene/comparer/<run_id>` elle-même, qui marche déjà. À reprendre quand l'écart sera tranché.
    evidence: |-
      `sprint-change-proposal-2026-10-19.md` §7(d) n° 7 ; `screens/arena-history.js`.
    location: src/wavelocalai/web/static/screens/arena.js
    severity: low
  - summary: >-
      Écart §7(d) n° 8, non tranché : l'affichage d'un résultat effacé rouvert par son adresse. Variante la plus conservatrice : seul l'identifiant inconnu rend `404 run_not_found` (critère actuel et contrat) ; une Arène effacée rend `200` avec `erased: true` et `config: null`, et l'écran affiche le même titre « Résultat introuvable » avec une phrase distincte (« a été effacée : seules ses mesures de CO₂ restent au registre carbone »), sans écran « effacé » séparé. Son export rend `404 run_not_found` (plus rien à exporter). À trancher par Anaël : écran « effacé » distinct qui montre le CO₂ gardé (maquette, AD-13), ou `run_not_found` pour tout résultat sans texte.
    evidence: |-
      `runs/snapshot.py` (`erased`), `screens/arena-reopen.js`, `contrat-api.md` (Runs), `sprint-change-proposal-2026-10-19.md` §7(d) n° 8.
    location: src/wavelocalai/web/static/screens/arena-reopen.js
    severity: medium
  - summary: >-
      Écart §7(d) n° 3, non tranché : l'icône de l'Arène (`leaderboard` de DESIGN.md, ou `swords` du code livré et de la maquette). La carte « Démo recommandée » reprend l'icône du registre des écrans (`swords`), comme le menu et le lien de module de l'Accueil : un seul endroit à changer quand l'écart sera tranché.
    evidence: |-
      `core/registry.js` (`arena.icon`), `screens/home-demo.js`.
    location: src/wavelocalai/web/static/core/registry.js
    severity: low
  - summary: >-
      Relancer une comparaison dont un modèle n'est plus installé (ou un modèle cloud sans « Autoriser le cloud ») : le front reprend la configuration telle qu'elle était et laisse le serveur refuser (`model_not_found`, `cloud_not_allowed`), dont l'enveloppe est affichée. Aucun contrôle préalable côté écran : le sélecteur ne sait pas qu'un tag a disparu avant la commande.
    evidence: |-
      `screens/arena-actions.js` (`reuseConfig`), `inference/arena.py` (`_resolve`).
    location: src/wavelocalai/web/static/screens/arena-actions.js
    severity: low
  - summary: >-
      La liste « Comparaisons précédentes » montre les 20 plus récentes, sans pagination ni recherche, et les modèles par leur nom lu dans le sélecteur (le tag tant que la liste des modèles n'est pas arrivée). Une liste plus longue demande un critère d'interface (Epic 5 : historique).
    evidence: |-
      `runs/snapshot.py` (`list_arena_runs`), `screens/arena-history.js`.
    location: src/wavelocalai/runs/snapshot.py
    severity: low
  - summary: >-
      L'export ne contient pas le texte des réponses des modèles (ni leur raisonnement) : le critère demande les mesures, la note, la raison du juge et la preuve. Les réponses se relisent en rouvrant la comparaison. Les ajouter demande de rejouer les `token` du run dans l'export (volume, et le texte quitte l'écran).
    evidence: |-
      `runs/arena_export.py`.
    location: src/wavelocalai/runs/arena_export.py
    severity: low
  - summary: >-
      Tag annoté `v2.0.0-alpha.3` et release GitHub non créés : à faire par Anaël après la recette (notes et recette en brouillon dans le rapport de la story). La version `2.0.0a3` est posée dans `pyproject.toml`, `uv.lock` et `CITATION.cff` ; `date-released` de `CITATION.cff` n'est pas touchée (comme pour a2) : à la date de la release.
    evidence: |-
      `pyproject.toml`, `CITATION.cff`, `uv.lock`.
    location: CITATION.cff
    severity: low
---

# Story 3.6 : rouvrir, exporter, relancer et effacer l'Arène, et la lancer depuis l'Accueil

## Objectif

Clore l'Epic 3. Une comparaison terminée se rouvre par son adresse ou par la liste des comparaisons précédentes, sans relancer de modèle ; elle s'exporte en CSV ou en Markdown avec la preuve de la mesure ; elle se relance ou se reprend dans le formulaire ; elle s'efface (AD-13). La carte « Démo recommandée » de l'Accueil la lance. Le Flow 1 d'`EXPERIENCE.md` se joue de bout en bout, sans rechargement de la page. La version passe à `2.0.0a3`.

## Critères d'acceptation et preuves

Preuves : `tests/v2/web/test_arena_reopen_api.py` (routes, effacement, octets du `.db` et du `-wal`), `tests/v2/unit/test_arena_export.py` (export), `tests/v2/unit/test_errors.py`, `tests/v2/e2e/test_arena_reopen.py` (écran rouvert, actions, histoire, axe), `tests/v2/e2e/test_home_demo.py` (carte), `tests/v2/e2e/test_flow1.py` (Flow 1).

1. **Rouvrir par l'adresse.** `#/arene/comparer/<run_id>` rejoue le flux depuis la base (colonnes, notes, classement, matrice) puis lit l'instantané du run (verdict, actions, CO₂ complété d'une lane arrêtée) ; aucun modèle n'est relancé. Un identifiant inconnu rend `404 run_not_found` (`detail.run_id`, code ajouté à `errors.py`, aussi pour `GET /api/runs/{id}/events`, `POST /api/runs/{id}/cancel` et les routes de l'Arène) et l'écran dit « Résultat introuvable » avec un lien « Lancer une nouvelle comparaison ». Preuve : `test_an_unknown_id_is_a_404_run_not_found_with_the_id`, `test_a_finished_arena_is_rebuilt_from_the_database_without_running_a_model`, `test_an_unknown_id_says_result_not_found_with_a_link_to_a_new_comparison`.
2. **Liste des comparaisons.** `GET /api/arena/runs?limit=` rend les plus récentes d'abord (`run_id`, `status`, dates, `models`, début de la question) sans les Arènes effacées ; l'écran la montre sous « Comparaisons précédentes », chaque entrée est un lien vers l'adresse ci-dessus, relue à la fin de chaque run. Preuve : `test_the_list_gives_the_latest_arenas_first_with_models_and_a_question_excerpt`, `test_the_history_lists_previous_comparisons_and_each_one_reopens`, `test_a_new_comparison_appears_in_the_history_when_it_ends`.
3. **« Relancer » et « Modifier la question ».** L'instantané d'une Arène porte `config` (`models`, `prompt`, `criteria`, `judge`) ; « Modifier la question » reprend tout dans le formulaire et rend le focus à la question, « Relancer » le lance aussitôt (si le formulaire le permet : sinon la raison du bouton désactivé reste lisible). Preuve : `test_the_snapshot_of_an_arena_carries_its_configuration`, `test_modify_the_question_takes_the_whole_configuration_back_into_the_form`, `test_rerun_launches_the_same_configuration_again`.
4. **Export.** `GET /api/arena/runs/{id}.csv` et `.md` : par modèle, note et raison, débit D3 et `tps_source`, CO₂ avec sa méthode, chargement, durée ; la preuve : fiche machine, version d'Ollama, digests des modèles et du juge, méthode du CO₂, juge et critères ; aucune clé d'API (secrets masqués) ; une cellule qui commencerait une formule de tableur est précédée d'une apostrophe. Deux boutons dès 768 px, un menu « Exporter » en dessous (composant de la 2.7, D-3), des liens de téléchargement du serveur (jamais de `blob:`). Preuve : `test_the_csv_export_has_each_model_and_the_proof_of_the_measure`, `test_exports_never_contain_a_configured_key_and_neutralise_spreadsheet_formulas`, `test_the_csv_export_carries_each_model_and_the_proof_of_the_measure`, `test_under_768_px_a_single_export_button_opens_the_formats`, `tests/v2/unit/test_arena_export.py`.
5. **Effacer (AD-13).** `DELETE /api/arena/runs/{id}` supprime les `run_events` et `messages` de la racine et de ses feuilles, purge le `.db` et le `-wal`, garde les lignes `runs` sans texte comme registre carbone (le CO₂ de session ne baisse pas) ; une Arène active rend `409 arena_busy`. L'écran demande confirmation (`wl-confirm-dialog`, focus sur « Annuler », conséquence dite), puis se vide et le dit. Preuve : `test_erasing_an_arena_removes_the_text_from_the_database_and_the_journal` (la question, une réponse et une raison sont cherchées dans les octets avant et après : report de la story 3.1), `test_erasing_an_active_arena_is_a_409_and_changes_nothing`, `test_erasing_asks_first_then_empties_the_screen_and_keeps_only_the_carbon`.
6. **Carte « Démo recommandée ».** « Arène » en titre, « Arène des modèles » en sous-titre (D-10), sa phrase, les modèles locaux prêts du défaut `arena` avec leur badge, « Lancer une comparaison » (lien vers `#/arene/comparer`, où le sélecteur présélectionne ce même défaut), toujours actif (D-11). Sans modèle local : « Aucun modèle local disponible » et, si le cloud est autorisé, des modèles cloud proposés, sinon la marche à suivre. La carte n'existe que si l'Arène est disponible au registre. Preuve : `tests/v2/e2e/test_home_demo.py`.
7. **Flow 1 de bout en bout.** Trois modèles `fake` (un en délai dépassé, un « non évalué ») : l'Accueil dit « Disponible », la comparaison se lance depuis la carte, les colonnes se remplissent, le classement ne vaut que pour le modèle noté, l'export contient la preuve, la page n'est jamais rechargée. axe-core sans violation sur l'Arène (rouverte, terminée, « Résultat introuvable », dialogue d'effacement) et sur l'Accueil, clair et sombre, à 320 et 1 440 px. Preuve : `test_flow_1_from_the_home_card_to_the_export_without_a_reload`, `test_flow_1_screens_have_no_axe_violation_in_either_theme`, `test_axe_finds_no_violation_on_a_reopened_arena`, `test_axe_finds_no_violation_on_the_demo_card`.
8. **Préversion `2.0.0a3`.** `pyproject.toml`, `uv.lock` (`uv lock`) et `CITATION.cff` ; tag annoté et release : voir `deferred`.

## Reports des stories précédentes traités

- **Effacement d'une Arène (AD-13, report de la 3.1)** : critère 5, avec la recherche dans les octets du `.db` et du `-wal`.
- **CO₂ d'une lane arrêtée « non mesuré » (report de la 3.4)** : à `run_ended`, l'écran lit l'instantané (`arena-snapshot.js`, `applyLateMeasures`) et pose sur les colonnes sans CO₂ chiffré les mesures que le serveur a complétées ; classement, tableau et pied de la colonne suivent. Preuve : `test_the_co2_the_server_completed_for_a_stopped_lane_replaces_not_measured`.
- **Contrat (reports des 3.1 et 3.3)** : `contrat-api.md` ratifie l'événement `judge`, la clé `judge` de `judge_score` (déjà dite) et le code `invalid_output` ; l'événement `question` et la clé `error` de `lane_status` y figuraient déjà. Il documente aussi `config`, `erased`, `run_not_found` étendu, `arena_busy`, la liste et les exports.

## Fichiers

- Serveur : `errors.py` (`run_not_found`, `arena_busy`) ; `runs/repo.py` (`erase_arena`), `runs/hub.py` (`erase_arena`), `runs/snapshot.py` (`arena_record`, `config`, `erased`, `list_arena_runs`), `runs/arena_export.py` (nouveau, fonctions pures), `runs/conversation_export.py` (`mask_value` rendue publique) ; `web/routes_arena.py` (liste, exports, effacement), `web/routes_runs.py` (`run_not_found`).
- Front : `screens/arena-snapshot.js`, `arena-actions.js`, `arena-history.js`, `arena-reopen.js`, `home-demo.js` (nouveaux) ; `arena-results.js` (instantané lu une fois, actions montées), `arena-verdict.js` (affiche, ne lit plus), `arena-form.js` (`launchReasonOf`, `envelopeOf` sortis d'`arena.js`), `arena-judge.js` (`restore`), `arena.js` (589 lignes, des lignes libérées avant d'en ajouter), `home.js` ; `core/api.js`, `core/format.js` (`formatDateTime`) ; `components/wl-chat-thread.js` (`metrics` après la fin remet à jour le pied) ; `arena-results.css`, `screens.css`, `i18n/fr.json`.
- Spec et version : `contrat-api.md`, `pyproject.toml`, `uv.lock`, `CITATION.cff`.
- Tests : voir les preuves ; réalignés : `test_runs_api.py`, `test_run_stream.py` (`run_not_found`), `test_arena_static.py`, `test_arena_verdict_static.py`, `test_shell_static.py`, `test_arena.py`, `test_home.py`.

## Tâches

- [x] Serveur : `run_not_found`, `arena_busy`, instantané (`config`, `erased`), liste, exports CSV et Markdown, effacement AD-13.
- [x] Front : instantané lu une fois à `run_ended`, actions (relancer, modifier, exporter, effacer), liste, résultat introuvable, CO₂ complété.
- [x] Accueil : carte « Démo recommandée ».
- [x] Tests (web, unité, E2E Edge, axe) et contrat ; version `2.0.0a3`.
- [ ] Recette humaine, tag `v2.0.0-alpha.3` et release (Anaël).

## Notes

- **`arena.js` à 589 lignes.** Rien n'a été ajouté sans en retirer : les prérequis du lancement (`launchReasonOf`) et `envelopeOf` sont passés dans `arena-form.js` (environ 35 lignes libérées dans `arena.js`), les actions, la liste et la réouverture vivent dans des modules voisins ; `arena.js` écoute deux événements (`wl-arena-reuse`, `wl-arena-erased`) émis par `arena-actions.js`. `wl-model-picker.js` fait 666 lignes depuis avant cette story (non touché).
- **Écarts §7(d)** : n° 3, 7 et 8 touchent la 3.6 (voir `deferred`) ; n° 1, 2, 4, 5, 6 ne la touchent pas ; ceux des stories voisines restent comme les 3.2 à 3.5 les ont laissés. Le §7(c) change la 3.6 (exports en deux boutons ou menu, `run_not_found`, carte à nom court et long, « Lancer une comparaison » toujours actif) : appliqué.
- **AD-6 et l'Accueil.** Les quatre cartes d'état lisent toujours le store seul. La carte « Démo recommandée » lit `GET /api/models` et `GET /api/models/defaults?purpose=arena` (cache du registre), une fois par état du cloud et d'Ollama ; sans modèle local de conversation elle ne demande pas le défaut (le serveur répondrait `404 no_model`, que le navigateur affiche en console).
- **Aucun type d'événement nouveau** : `config`, `erased` et la liste sont lus en base, comme le verdict.
- **Export CSV** : une seule table, la preuve répétée sur chaque ligne (un tableau seul reste vérifiable) ; BOM UTF-8 pour Excel ; virgule comme séparateur (RFC 4180).
- **Lecture de l'instantané** : `run_ended` est publié avant l'écriture du statut final (story 3.5) ; `readSettled` relit tant que le run est actif (20 fois, 150 ms), et sert au verdict, aux actions et au CO₂ complété.

Tests : `tests/v2/unit` et `tests/v2/web` 1 119 réussis (2 échecs de `test_rag_api.py` sous charge du poste partagé, verts seuls : 11 sur 11) ; E2E sur Edge : `test_arena.py` 57, `test_arena_verdict.py` et `test_arena_results.py` 40, `test_arena_reopen.py` 17, `test_home_demo.py` 13, `test_flow1.py` 3, `test_home.py` 29, `test_components.py` et `test_chat.py` 43 ; contrôle rapide propre.
