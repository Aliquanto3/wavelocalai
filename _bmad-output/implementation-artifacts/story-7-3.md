---
title: 'L''écran Évaluation de la qualité montre les étapes et garde le résultat'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '9755e84'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-7-1.md'
warnings: []
deferred: []
---

# Story 7.3 : l'écran Évaluation de la qualité

## Objectif

Sur `#/documents/evaluation`, une consultante lance l'évaluation d'une question ou d'un jeu de questions sur 1 à 4 modèles, voit trois étapes avancer puis les notes arriver au fil de `eval_metric`, déplie chaque note sur ses verdicts, et retrouve le résultat plus tard (`#/documents/evaluation/<run_id>`, partiel compris) ou dans la liste des évaluations passées. Écran seulement : le serveur (7.1) donne tous les scores (AD-20).

## Critères d'acceptation et preuves

1. **Réglages** : segments « Question » · « Jeu de questions » (une question par ligne, 20 au plus), `wl-model-picker` multi présélectionné sur le défaut `arena` (D-27), juge sur le défaut `judge` (raison du défaut par le sélecteur, avertissement « note peu fiable » avant le lancement et, après `judge`, selon `unreliable`), phrase « Les mêmes extraits sont fournis à tous les modèles. ». Lancement désactivé avec la raison visible reliée au bouton : base vide (« Importez des documents pour évaluer » et lien vers la Base documentaire), « Choisissez au moins un modèle », « Choisissez 4 modèles au plus », « Saisissez une question » (D-29), « Choisissez un juge ». Preuve : `test_evaluation.py::test_the_form_...`.
2. **Étapes** : « Recherche des extraits communs » (+ « Voir les extraits » : `wl-source-panel`, une question à la fois pour un jeu), « Réponses » (une ligne par modèle : en attente, chargement, rédaction, fait, échec, arrêté ; un `ram_guard` garde ses deux boutons de `wl-error`), « Notation : fidélité · pertinence · précision du contexte » (compte de notes reçues). États en texte : à venir, en cours, fait, échec, arrêtée, non lancée. Preuve : `::test_the_steps_advance_...`, `::test_step_states_...`.
3. **Tableau** : Modèle, Fidélité, Pertinence, Précision du contexte, Débit, CO₂ (aucune colonne « Global », décision du 2026-10-19). Chaque cellule se remplit au fil de `eval_metric` (« en cours » avant), un score est un bouton « 86/100 » qui déplie le détail ; « non évalué » dit sa raison en texte (« non évalué (juge indisponible) »), jamais 0. Définition en une phrase de chaque métrique en aide ; « Méthode inspirée de Ragas » en aide seulement. Preuve : `::test_scores_fill_in_...`, `::test_not_evaluated_...`.
4. **Détail** : fidélité = « 7 affirmations : 6 appuyées, 1 non appuyée » et la liste des verdicts avec l'extrait d'appui (texte lu dans les `sources` du flux) ; pertinence = la raison et les questions retrouvées ; précision = la raison et les extraits jugés utiles ; la réponse évaluée, repliée. Un jeu de questions : « sur 8 questions (1 non évaluée) » sous le score, détail par question. Preuve : `::test_a_score_unfolds_...`.
5. **Matrice** : segments « Tableau » (par défaut) · « Matrice » (`wl-chart-svg`, fidélité × débit, CO₂ en taille, une seule unité), comme l'Arène. Preuve : `::test_the_matrix_...`.
6. **Rouvrir** : `#/documents/evaluation/<run_id>` rejoue le flux enregistré (aucun modèle relancé), puis lit l'instantané (`summary`, `evaluations`, `missing`, `partial`) ; un résultat partiel est titré « Résultat partiel conservé », ses cellules non notées en « non évalué (évaluation arrêtée) » ; identifiant inconnu : `run_not_found` (avec le texte du serveur) et lien vers une nouvelle évaluation ; évaluation effacée dite de même. Preuve : `::test_reopening_...`, `::test_a_partial_result_...`, `::test_an_unknown_run_...`.
7. **Évaluations passées** : liste de `GET /api/rag/eval/runs` (les plus récentes d'abord), chacune un lien vers son adresse. Preuve : `::test_the_past_evaluations_...`.
8. **Accessibilité** : axe-core sans violation, clair et sombre ; pas de défilement horizontal à 320 px. Preuve : `::test_axe_...`.

## Règles écrites

- Aucun calcul de note à l'écran. Seule arithmétique du front, sur des mesures du serveur et non sur des notes : pour un jeu de questions, le débit affiché est la moyenne des débits mesurés, le CO₂ la somme des CO₂ mesurés (en-têtes « Débit moyen » et « CO₂ total » dits dans l'aide). Un modèle sans mesure : « non mesuré », jamais 0.
- Texte saisi : questions et réponses ne sont lues que dans le flux (`eval_questions`, `eval_answer`, `sources`), posées par `textContent`, jamais gardées hors du brouillon `localStorage` de la question.
- Le flux d'un run n'a qu'un lecteur : l'écran (`connectRun`). Il rend la main à l'instantané à `run_ended` (`readSettled`).

## Écarts et variantes conservatrices

- **Éligibilité de l'usage (décision n° 17)** : l'API des modèles n'expose pas encore d'éligibilité par usage (story 5.4) ; le sélecteur est donc non filtré ici. À brancher par la 5.4 sans changer cet écran.
- **Détail** : `EXPERIENCE.md` parle d'un panneau « Détail » latéral ; le critère dit « se déplie ». Variante conservatrice : une région « Détail » sous le tableau, ouverte par le bouton du score (`aria-expanded`), focus sur son titre, « Fermer » rend le focus au bouton. Pas de nouveau composant `wl-side-panel`.
- **Hors périmètre, non demandé** : « Relancer », « Modifier la question », « Effacer » (la route `DELETE` existe) et l'export ; le juge cité comme modèle évalué est seulement signalé en une phrase.
- **États d'étape** : « arrêtée » et « non lancée » s'ajoutent à « à venir », « en cours », « fait », « échec » pour une évaluation annulée ou interrompue.

## Fichiers

- Écran : `screens/documents-eval.js`, `eval-form.js`, `eval-model.js`, `eval-steps.js`, `eval-results.js`, `eval-detail.js`, `eval-history.js`, `eval-reopen.js` ; `core/api/evaluation.js` ; `i18n/fr/evaluation.json` ; `evaluation.css` ; route `core/routes/documents.js`.
- Tests : `tests/v2/e2e/test_evaluation.py`, `tests/v2/unit/test_evaluation_static.py` ; réalignés : `test_shell_static.py`, `test_shell.py`.

## Rapport de dev

Ciblé (poste partagé : ni `tests/v2` complet ni les autres E2E). `tests/v2/e2e/test_evaluation.py` : 23 verts (Edge, `-m e2e`), dont axe-core clair et sombre à 320 et 1 440 px. Statiques : `test_evaluation_static.py`, `test_static_split.py`, `test_shell_static.py`, `test_documents_static.py`, `test_discussion_static.py`, `test_chat_static.py`, `test_picker_static.py`, `test_arena_static.py` : 111 verts. E2E de la coquille touchés par le passage à `available` (`test_shell.py`, `test_home.py`, sélection « planned / route / mockup / tab ») : 14 verts. Contrôle rapide propre. Aucun fichier JS au-delà de 600 lignes (`documents-eval.js` : 470).

## Journal

- 2026-10-19 · dev : spec, écran en huit modules (`eval-*.js`), textes `evaluation.json`, `evaluation.css`, route `available`, tests E2E et statiques, réalignement des tests de la coquille.

## Points pour la revue

- Les E2E rejouent des flux et des instantanés fixés par le test (`page.route`) : la forme suit `contrat-api.md` § « Évaluation (story 7.1) », pas une évaluation réelle de bout en bout (un vrai juge ne rend pas des notes choisies). Seuls l'identifiant inconnu et la liste vide passent par le vrai serveur.
- Le débit moyen et le CO2 total d'un jeu de questions sont additionnés côté front (mesures, pas notes) : si la revue y voit un calcul de trop, la 7.1 pourrait publier ces totaux.
