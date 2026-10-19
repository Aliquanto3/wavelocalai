---
title: "Le classement, la matrice qualité/CO₂ et le tableau se construisent au fil des résultats (écran)"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '2567e44'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-2.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-3.md'
warnings: []
deferred:
  - summary: >-
      Écart §7(d) n° 6, non tranché : l'étiquette « le plus petit des trois » (Flow 1) n'est pas livrée. Aucune story ne la demande, la maquette la dérive des paramètres actifs du modèle (absents de l'événement `metrics` et de `lane_status`), et le front ne calcule rien (AD-20). Variante la plus conservatrice : aucune étiquette ; le classement dit le rang, la note, le débit et le CO₂, et la salle lit elle-même que le premier est le plus petit. À reprendre quand l'écart sera tranché (donnée du serveur, ou fiche du modèle lue par le sélecteur).
    evidence: |-
      `docs/maquette-v2/js/screens/arene.js` (`smallestLabel`), `sprint-change-proposal-2026-10-19.md` §7(d) n° 6.
    location: src/wavelocalai/web/static/screens/arena-results.js
    severity: low
  - summary: >-
      Le CO₂ d'une lane annulée ou interrompue après un calcul partiel reste « non mesuré » à l'écran : le serveur peut l'avoir complété en base (`amend_cancelled_leaf`), mais aucun événement ne le publie, et le front ne lit pas l'instantané `GET /api/runs/{id}` (les mesures des feuilles y figurent). À reprendre avec la réouverture de la story 3.6, qui lit l'instantané.
    evidence: |-
      `src/wavelocalai/inference/streaming.py` (`amend_cancelled_leaf`), `contrat-api.md` (instantané).
    location: src/wavelocalai/web/static/screens/arena-results-data.js
    severity: low
  - summary: >-
      `co2.range_mg` (fourchette d'une estimation cloud) n'est pas affichée : le classement, le tableau et la légende donnent la valeur centrale suivie de « (estimé) », comme le pied de réponse d'un fil. Une fourchette dans la matrice demande une barre d'erreur (UX à décider).
    evidence: |-
      `test_an_estimated_and_an_unmeasurable_co2_are_said_in_text`.
    location: src/wavelocalai/web/static/screens/arena-results-data.js
    severity: low
  - summary: >-
      « note peu fiable » et « un seul juge » (3.3) restent sur les colonnes et dans le bloc du juge ; le classement ne les répète pas. Une salle qui ne lit que le classement ne voit pas l'avertissement d'un juge faible.
    evidence: |-
      `screens/arena-judge.js` (`judgeInfo`), `components/wl-arena-lane.js` (`setJudge`).
    location: src/wavelocalai/web/static/screens/arena-results.js
    severity: low
  - summary: >-
      Les tests de notes, de débits et de CO₂ différents d'une lane à l'autre réécrivent le flux d'une comparaison terminée (`replayed`) : la route de test `POST /api/test/arena` rejoue le même script de juge pour toutes les lanes, ne mesure pas le CO₂ d'une lane locale, et un juge dont le tag est celui d'une lane remplace son script. Si d'autres stories en ont besoin, ajouter un script de juge par lane et un `co2` par lane à cette route.
    evidence: |-
      `tests/v2/e2e/test_arena_results.py` (`replayed`, `tuned`).
    location: src/wavelocalai/web/routes_test.py
    severity: low
  - summary: >-
      Échelle du débit : linéaire de 0 au plus grand débit. Un modèle cloud (centaines de tokens/s) écrase les modèles locaux (dizaines) dans le coin gauche de la matrice ; leurs étiquettes se décalent mais les points se chevauchent. Une échelle logarithmique (la maquette la prévoit en option) demande un choix de lecture pour la salle.
    evidence: |-
      `core/chart-scale.js` (`linearAxis`), `docs/maquette-v2/js/components/charts.js`.
    location: src/wavelocalai/web/static/core/chart-scale.js
    severity: low
---

# Story 3.4 : le classement, la matrice qualité/CO₂ et le tableau se construisent au fil des résultats (écran)

## Objectif

Pendant la comparaison, un classement se met à jour à chaque `judge_score` et `metrics` ; à `run_ended` il se fige. Une matrice qualité (/100) × débit, avec le CO₂ en taille, puis le tableau équivalent, disent d'un coup d'œil que le plus petit modèle peut gagner. Écran seulement : aucune route, aucun événement, aucun calcul de mesure de plus (AD-20). Rouvrir une comparaison terminée par son adresse reconstruit les trois depuis le rejeu du flux.

## Critères d'acceptation et preuves

Preuves : `tests/v2/e2e/test_arena_results.py` (Edge, 25 parcours, axe-core clair et sombre à 320 px et 1 440 px, projection) et `tests/v2/unit/test_arena_results_static.py`.

1. **Classement au fil de l'eau, figé à `run_ended`.** `screens/arena-results.js` relit les colonnes (statut, note, mesures) à chaque `wl-lane-change` (statut, note ou mesures d'une colonne, jamais un token ; regroupé par image), et se fige à `run_ended` (`results.end`). Chaque ligne : rang, nom, badge Local ou Cloud, note /100, débit, CO₂ ; notes égales : même rang et « ex æquo » en texte. Une lane « non évalué » est listée sous les lanes notées, dans « Non évalués, sans rang », avec sa raison (juge : « réponse vide », « juge indisponible », « sortie du juge invalide » ; statut de lane : « délai dépassé », « échec du modèle », « comparaison arrêtée », « comparaison interrompue », repris de la 3.3), sans rang, sans chiffre. Une comparaison arrêtée dit que le classement ne vaut que pour les modèles déjà notés. Preuve : `test_the_ranking_builds_as_results_arrive_and_freezes_at_the_end`, `test_the_ranking_updates_with_each_score_before_the_comparison_ends`, `test_a_lane_not_evaluated_is_listed_with_its_reason_below_the_ranked_ones_without_a_rank`, `test_a_partial_comparison_says_the_ranking_only_holds_for_the_scored_models`, `test_a_run_without_any_score_gives_no_ranking_and_every_lane_not_evaluated`.
2. **Matrice, d'abord (D-14).** Segments « Matrice · Tableau » (`components/segments.js`, `radiogroup`, flèches, icône `check` sur le choix), Matrice par défaut, le choix tient pour la session de la page. `components/wl-chart-svg.js` : nuage de points SVG fait main, note /100 en ordonnée (0 à 100), débit en abscisse, CO₂ en taille (surface selon le CO₂), nom complet de chaque modèle en étiquette (à plusieurs lignes si besoin, sans chevauchement), couleurs `--color-chart-1` à `-4` par jeton, `<title>` et `<desc>` (la description liste chaque point), légende de taille en texte HTML (plus petit et plus grand CO₂, « Contour en pointillés : CO₂ non mesurable »), bouton « Voir le tableau » qui mène au tableau. Preuve : `test_the_matrix_is_shown_first_with_a_title_a_description_a_size_legend_and_full_names`, `test_see_the_table_leads_to_the_table_and_the_segments_switch_with_the_arrow_keys`, `test_the_segment_choice_holds_for_the_page_session`.
3. **Aucun axe resserré, aucune couleur seule.** Un axe part toujours de 0 et sa longueur n'est jamais nulle (un point, des points alignés, aucun point : toujours des graduations régulières). Chaque point garde son contour d'encre et son nom écrit ; un CO₂ non mesurable est en pointillés, dit en légende ; une lane qui n'a pas à la fois note et débit est nommée sous le graphique (« Non placés sur la matrice : … »). Le texte du SVG suit le mode projection (rem, marges et interlignes recalculés) et la largeur (redessiné au redimensionnement, la police ne rétrécit pas). Preuve : `test_a_linear_axis_always_starts_at_zero_and_never_collapses_on_one_point`, `test_the_axes_start_at_zero_and_one_point_does_not_squeeze_them`, `test_the_point_size_grows_with_the_co2_and_an_unknown_co2_has_its_own_size`, `test_the_labels_stay_inside_the_plot_and_do_not_overlap`, `test_the_matrix_labels_stay_inside_the_picture_at_320_px_and_in_projection`, `test_the_chart_redraws_when_the_width_changes_and_keeps_its_text_size`.
4. **Tableau.** `wl-data-table` : `<caption>`, `<th scope="col">`, première colonne `<th scope="row">`, colonnes Modèle, Origine (badge), Note, Débit, CO₂, Chargement, Durée totale ; en-têtes triables au clavier (Entrée, Espace, `aria-sort`, annonce polie), l'inconnu en dernier dans les deux ordres, le CO₂ trié en mg. Lignes dans l'ordre du classement, puis les lanes non évaluées. Preuve : `test_the_table_lists_every_model_in_a_semantic_table_with_one_co2_unit`, `test_the_table_sorts_with_the_keyboard_and_puts_the_unknown_last`.
5. **Une unité de CO₂, jamais 0 ni « — ».** `co2GroupOf` choisit l'unité du plus grand CO₂ mesuré de la comparaison ; classement, tableau et légende de taille la partagent (« Tous les CO₂ de cette comparaison sont exprimés en mg. »). « non mesurable » : le serveur n'a pas pu mesurer (`co2.mg` nul) ; « 2,4 mg (estimé) » : estimation cloud ; « non mesuré » : aucune mesure publiée (délai, échec, arrêt) ; « en cours » : pas encore fini ; « non évalué : raison » pour la note ; « sans objet » pour le chargement d'un modèle cloud. Preuve : `test_the_co2_of_one_comparison_is_in_one_unit_and_a_tie_shares_its_rank`, `test_an_estimated_and_an_unmeasurable_co2_are_said_in_text`, `test_the_table_lists_every_model_in_a_semantic_table_with_one_co2_unit`.
6. **Réouverture par l'adresse.** Le classement, la matrice et le tableau se construisent depuis le rejeu du flux (`#/arene/comparer/<run_id>`), sans état à part : la vue relit les colonnes que le rejeu remplit. Preuve : les parcours `open_replayed` (flux réécrit pour des notes, débits et CO₂ distincts, rouvert par l'adresse) de `test_arena_results.py`.
7. **Accessibilité.** axe-core sans violation (classement et matrice, tableau, tableau trié ; clair et sombre ; 320 px et 1 440 px ; projection), aucun défilement horizontal de la page (le tableau défile dans sa zone), aucune couleur en dur (jetons seulement). Preuve : `test_axe_finds_no_violation_on_the_ranking_the_matrix_and_the_table`, `test_axe_finds_no_violation_on_the_results_in_projection_mode`, `test_the_chart_is_styled_from_tokens_only_and_the_css_is_linked`.

## Fichiers

- `src/wavelocalai/web/static/screens/arena-results.js` (nouveau) : classement, segments, matrice et tableau ; `screens/arena-results-data.js` (nouveau) : rangs, raisons, unité commune, textes de mesure (sans DOM) ; `screens/arena-tabs.js` (nouveau) : touches des onglets, sorties de `arena.js` pour rester sous 600 lignes
- `src/wavelocalai/web/static/components/wl-chart-svg.js` (nouveau) ; `components/segments.js` (nouveau) ; `core/chart-scale.js` (nouveau, fonctions pures : axe, rayon, légende, étiquettes)
- `src/wavelocalai/web/static/components/wl-arena-lane.js` : `name`, `origin`, `result` et l'événement `wl-lane-change` ; `screens/arena.js` : une vue de résultats, `reset` et `end` ; `components/index.js`
- `src/wavelocalai/web/static/arena-results.css` (nouveau, lié dans `index.html`), `components.css` (segments, `wl-chart-svg`), `i18n/fr.json` (`arena.results`, `arena.chart`)
- Tests : `tests/v2/e2e/test_arena_results.py`, `tests/v2/unit/test_arena_results_static.py` ; `unit/test_arena_static.py` (les trois scripts de l'écran ajoutés à `NEW_SCRIPTS`)

## Écarts

- **Matrice avant la fin** : le critère dit « quand la comparaison est finie » ; le titre de la story dit « au fil des résultats ». La matrice et le tableau apparaissent dès la première lane mesurée et se complètent ; la lecture définitive est à `run_ended` (Matrice par défaut dans les deux cas).
- **« Voir le tableau » est un bouton**, non un lien (`<a>`) : le routeur lit le hash, un lien d'ancre le détournerait (même choix que la maquette).
- **Écarts §7(d)** (non tranchés, variante la plus conservatrice gardée) : n° 6 « le plus petit des trois » non livré (voir `deferred`) ; n° 5 « un seul juge » inchangé (3.3) ; n° 4 chronomètre « 0:42 » inchangé ; n° 7 l'adresse n'est pas réécrite à la fin d'un run (aucun `history.replaceState`) ; n° 8 aucun écran « effacé » (la 3.6 le tranche).

## Reports

Voir `deferred` : étiquette « le plus petit », CO₂ d'une lane annulée (instantané), fourchette d'estimation, fiabilité du juge dans le classement, route de test, échelle logarithmique du débit.

Tests : `tests/v2` 971 réussis (hors E2E, désélectionnés par défaut) ; E2E sur Edge : `-m e2e -k arena` 83 réussis (dont les 25 de `test_arena_results.py`), `test_components.py`, `test_shell.py` et `test_home.py` 57 réussis ; contrôle rapide propre.
