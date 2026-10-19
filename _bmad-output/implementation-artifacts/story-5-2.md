---
title: "Retrouver l'historique carbone et ouvrir une nouvelle session"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '2dcadab'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-1.md'
  - '{project-root}/docs/maquette-v2/notes/sobriete.md'
warnings: []
deferred:
  - summary: >-
      Écarts nouveaux de l'historique, non couverts par `epics.md` ni les décisions du 2026-10-19 : variante la plus conservatrice gardée pour chacun. (1) « Fin » d'une session = fin de sa dernière réponse comptée : `app_sessions` ne stocke que le début, et ajouter une colonne `closed_at` demanderait une migration (aucune n'est ajoutée : pas de `0007`). Une session close par un redémarrage n'a ainsi pas la durée d'arrêt du serveur dans sa « fin ». (2) La période (`7d`, `30d`) filtre sur cette dernière réponse, non sur le début : une session commencée il y a 8 jours dont la dernière réponse date de la veille figure dans « 7 jours ». (3) Une session sans aucune feuille comptée (un démarrage sans réponse) n'est pas listée : chaque lancement ajouterait sinon une ligne vide. (4) Local et Cloud : une origine sans aucune réponse vaut 0 (« aucun appel » au tableau, comme la maquette), une origine dont toutes les réponses sont sans mesure est nulle (« non mesuré ») ; `total_mg` est nul quand aucune réponse de la session n'est mesurée (barre absente, jamais 0).
    evidence: |-
      `greenops/history.py`, `tests/v2/unit/test_carbon_history.py` (`test_a_session_with_nothing_measured_*`, `test_an_origin_*`, `test_windows_*`, `test_a_session_without_any_counted_run_*`).
    location: src/wavelocalai/greenops/history.py
    severity: low
  - summary: >-
      Choix de conception à confirmer. (1) « un run actif pendant la remise à zéro reste compté dans la session où il a commencé » a exigé une correction du hub (story 2.x, code livré) : une feuille enfant créée après la remise à zéro prend la session de son run racine (`_Run.app_session`), non la session courante, sinon la deuxième voie d'une Arène lancée avant le clic partait dans la nouvelle session. Une feuille racine garde la session où elle a été créée, comme avant. (2) `POST /api/carbon/session/reset` sur une session vide est accepté côté serveur (une session vide de plus, non listée) : seul l'écran le désactive, comme le demande la décision n° 16 ; variante la plus simple, sans nouveau code d'erreur ni `409`. (3) « Remettre le compteur à zéro » n'ouvre pas `wl-confirm-dialog` : EXPERIENCE.md dit « sans confirmation » (la session close reste dans l'historique). Après le clic le bouton se désactive : le focus passe au titre de la section, la fin est annoncée en `polite`. (4) L'historique est relu à chaque `carbon_updated` (une lecture SQL par réponse, jamais en boucle) : un run actif au moment de la remise à zéro finit dans la session close, dont le total change après coup ; avec une période sans session, une lecture de `all` de plus dit si des sessions plus anciennes existent (« Aucune session sur cette période… » ou « Aucune session mesurée pour l'instant. »).
    evidence: |-
      `runs/hub.py::create_run`, `tests/v2/unit/test_carbon_history.py::test_an_active_run_keeps_counting_*`, `tests/v2/web/test_carbon_history_api.py`, `screens/sobriety-reset.js`, `screens/sobriety-history.js::read`.
    location: src/wavelocalai/runs/hub.py
    severity: medium
  - summary: >-
      Composants et contrat partagés. `wl-chart-svg` ne traçait que des nuages de points : un graphique qui porte `bars` (au lieu de `points`) est maintenant tracé en barres par `components/chart-bars.js` (même titre, description et bouton « Voir le tableau » ; mode d'emploi en tête du fichier). `core/chart-scale.js` gagne `barBands`, `barHeight`, `labelStride` et `core/format.js` `formatShortDateTime` (étiquette d'abscisse). Une barre trop basse garde 2 px (jamais invisible), les étiquettes d'abscisse sont espacées quand elles se chevaucheraient, la valeur est écrite au-dessus de la barre quand sa bande est assez large. Route de test `POST /api/test/carbon-sessions` (sessions closes du passé, `WAVELOCALAI_TESTING`). `contrat-api.md` : sous-section « Historique carbone et remise à zéro (story 5.2) ». Aucune migration, aucun ajout à `errors.py`, aucune dépendance.
    evidence: |-
      `components/chart-bars.js`, `tests/v2/e2e/test_sobriety_history.py::test_the_bar_scale_helpers`, `test_many_sessions_keep_the_chart_readable_*`.
    location: src/wavelocalai/web/static/components/chart-bars.js
    severity: low
---

# Story 5.2 : retrouver l'historique carbone et ouvrir une nouvelle session

## Objectif

Un consultant qui présente la sobriété voit sur `#/sobriete`, sous la session en direct, les émissions de chaque session close sur 7 jours, 30 jours ou tout, en graphique puis en tableau, et remet le compteur à zéro d'un clic pour repartir d'un compteur propre : la session close reste dans l'historique.

## Critères d'acceptation et preuves

1. **`GET /api/carbon/history?window=7d|30d|all`** : une ligne par `app_session` close de la fenêtre (`id`, `started_at`, `ended_at`, `total_mg`, `local_mg`, `cloud_mg`, `measured_runs`, `unmeasurable_runs`), du plus ancien au plus récent, calculée depuis les feuilles de `runs` (même prédicat que le CO₂ de session) conversations effacées comprises (AD-13) ; la session en cours n'y figure pas (D-37). Une fenêtre inconnue : `invalid_request`. La route entre dans le test de budget de lecture : 1 000 runs de test, Ollama arrêté, moins de 300 ms. Preuve : `unit/test_carbon_history.py`, `web/test_carbon_history_api.py::test_history_*`, `test_the_session_in_progress_is_not_listed`, `test_history_answers_under_300_ms_with_1000_runs_*`, `test_the_history_route_enters_the_read_budget_*`.
2. **Remise à zéro** : `POST /api/carbon/session/reset` (écriture, `Origin` contrôlée) ouvre une nouvelle `app_session` (`hub.new_app_session("reset")`), publie `carbon_updated` (somme nulle) et rend la nouvelle session ; la session close apparaît dans l'historique, rien n'est effacé. Un run actif pendant la remise à zéro reste compté dans la session où il a commencé, y compris ses feuilles créées après le clic. Preuve : `web/test_carbon_history_api.py::test_reset_*`, `test_an_active_run_stays_counted_*`, `test_reset_refuses_a_foreign_origin_*` ; `unit/test_carbon_history.py::test_an_active_run_keeps_counting_in_the_session_where_it_started`.
3. **Graphique et tableau** : segments « 7 jours · 30 jours · Tout » (7 jours par défaut) et « Graphique · Tableau » ; `wl-chart-svg` trace une barre par session, titrée « Émissions par session » (`<title>`, `<desc>`, « Voir le tableau »), en mg, une seule unité ; une session sans mesure garde sa place, marquée « non mesuré », sans barre ; `wl-data-table` donne le même contenu (début, fin, total, Local, Cloud (estimé), non mesurables), triable au clavier, la plus récente d'abord. Sans historique : « Aucune session mesurée pour l'instant. », sans graphique vide ; période sans session : « Aucune session sur cette période… ». « La session en cours n'apparaît qu'une fois close. » sous le graphique. Sous 640 px, « Tableau » par défaut (D-39) ; le choix tient pour la session de la page. Preuve : `e2e/test_sobriety_history.py` (`test_the_default_is_seven_days_*`, `test_the_period_segments_*`, `test_the_table_gives_the_same_content_*`, `test_a_session_with_nothing_measured_*`, `test_below_640_px_*`, `test_without_any_session_*`, `test_a_period_without_session_*`).
4. **« Remettre le compteur à zéro »** (en-tête de la section carbone, sans confirmation) : désactivé quand la session est vide avec sa raison écrite dessous (décision n° 16) ; au clic, le total de la section et de la barre haute repart de 0, « Compteur remis à zéro. La session précédente est dans l'historique. » est annoncé en `polite` et le focus passe au titre de la section ; un échec garde le compteur et dit le message du serveur. Preuve : `e2e::test_the_reset_is_disabled_*`, `test_the_reset_starts_a_new_session_*`, `test_a_run_active_during_the_reset_*`, `test_a_failed_reset_*`.
5. **Appels** : aucun avant `shell-ready` (AD-15), une lecture par période et par réponse, jamais en boucle, rien onglet masqué ; aucune requête hors de `127.0.0.1` ; aucun calcul de métrique à l'écran (AD-20) ; aucun JS au-delà de 600 lignes. Preuve : `e2e::test_no_history_call_before_shell_ready_*`, `test_a_hidden_tab_does_not_read_the_history_*`, `test_the_history_never_leaves_127_0_0_1`, `unit/test_sobriety_static.py`.
6. **Accessibilité** : axe-core sans violation, clair et sombre (historique en graphique, complet, en tableau, période vide, remise à zéro active et faite) ; pas de défilement horizontal à 320, 768 et 1440 px, graphique et tableau ; 25 sessions : étiquettes d'abscisse espacées, jamais l'une sur l'autre. Preuve : `e2e::test_axe_finds_no_violation_*`, `test_the_history_has_no_horizontal_scroll`, `test_many_sessions_keep_the_chart_readable_*`.

## Hors périmètre

Écran Modèles (5.3 et suivantes). Équivalence en voiture, santé du système et fiche d'identité : 5.1.

## Notes de développement

- Serveur : `greenops/history.py` (`carbon_history`), `greenops/session.py` (`LEAF_WHERE` et `ORIGIN_SQL` partagés), `runs/hub.py` (la feuille prend la session de son run racine), `web/routes_system.py` (`GET /api/carbon/history`, `POST /api/carbon/session/reset`), route de test `POST /api/test/carbon-sessions`.
- Front : `screens/sobriety-history.js` (section, segments, graphique, tableau), `sobriety-reset.js` (bouton, raison, annonce), `sobriety-carbon.js` (en-tête de section, `sessionIsEmpty`), `sobriety.js` (montage) ; `components/chart-bars.js` + `wl-chart-svg.js` ; `core/chart-scale.js`, `core/format.js`, `core/api/system.js` ; textes `i18n/fr/sobriety.json` (`reset`, `history`), CSS `sobriety.css` et `css/components/chart.css`.
- Contrat : `contrat-api.md`, sous-section « Historique carbone et remise à zéro (story 5.2) ». Aucune migration, aucun ajout à `errors.py`.
- Réalignés : `test_sobriety.py` (troisième `h2` « Historique »), `test_sobriety_static.py` (fichiers de la 5.2, appels d'API permis à l'historique et à la remise à zéro, seule zone `status` de l'écran).

## Rapport de dev

- Joué en local : `tests/v2/unit` en entier (918 passés, 1 sauté), `tests/v2/web` ciblé (`test_carbon_history_api` 11, `test_sobriety_api`, `test_system`, `test_read_budget`, `test_security`, `test_errors_envelope`, `test_runs_api` : 82 passés au total), E2E `test_sobriety.py` (27) et `test_sobriety_history.py` (28), `test_topbar.py` et `test_arena_results.py` (54, composants partagés). La suite complète est celle de la CI.
- Pas de dépendance nouvelle. Pas de migration : si une story parallèle prend `0007`, rien à renommer ici.

## Revue

Revue Opus, une passe, sur `a96b9a9` (branche à jour de `origin/master`, 5.1 fusionnée).

- low · second avis 1 · rejeté · `sobriety.json` : « Tout » et « : {sessions} » portent déjà des insécables U+00A0 (vérifié octet par octet).
- low · second avis 2 · rejeté · double lecture `7d`/`30d` puis `all` : seulement quand la période est vide, donc deux lectures de quelques lignes. `_HISTORY_SQL` : mesuré sur une base réelle (migrations, une racine et une feuille par paire) : 10 000 runs, 9 à 21 ms ; 100 000 runs, 210 à 240 ms. Linéaire (`NOT EXISTS` sur l'index `runs_parent`), sous le budget de 300 ms même à 100 000 runs ; borner la fenêtre en SQL demanderait un index sur `ended_at`, donc une migration : non justifié.
- low · second avis 3 · rejeté · session lue avant `awrite` dans `create_run` : un run créé pendant la remise à zéro part dans l'ancienne session, celle où il a été demandé, qui existe toujours (aucune contrainte rompue) ; c'est le comportement attendu par le critère 2.
- low · second avis 4 · corrigé · un écran monté onglet masqué lisait l'historique (`history.start()` sans test de `document.hidden`), contre le critère 5 (« rien onglet masqué ») : le premier chargement attend le retour de l'onglet, et une réponse arrivée avant ne relit rien (`sobriety.js`). Test `e2e::test_a_screen_opened_in_a_hidden_tab_reads_the_history_only_once_shown`, rouge sur l'ancien code.
- low · second avis 5 · rejeté (écart accepté) · « Fin » = dernière réponse, période filtrée sur elle, sessions sans réponse absentes : le critère demande début, fin et total d'une session close sans dire comment dater la fin ; une session close par redémarrage n'a pas d'heure d'arrêt connue sans migration. Variante conservatrice, documentée dans `deferred`.
- info · dev (correctif du hub) · confirmé · `create_run` : une feuille prend la session de sa racine. Sans remise à zéro, la session de la racine est toujours la session courante (seule `start()` en ouvrait une, sans run actif) : aucun changement pour le chat, l'Arène, le RAG, l'évaluation (le juge est une feuille de l'Arène, il suit sa racine) ni les agents (absents de cette base). Les `carbon_updated` des modules publient la session courante, ce qui garde la barre haute à 0 après la remise à zéro.
- low · revue · reporté · course rare : un `carbon_updated` de l'ancienne session, calculé juste avant la remise à zéro et publié après la réponse de `POST /reset`, peut réafficher l'ancien total dans la barre haute jusqu'à la réponse suivante. À vérifier : comparer l'id de session de la somme reçue avec celle de la remise à zéro, si `session_summary` le porte un jour.
- Complexité : 1 constat (low, rejeté) · historique relu à chaque `carbon_updated` : O(runs) côté SQL, mesuré ci-dessus ; côté écran, reconstruction du graphique ou du tableau en O(sessions) par réponse, sans parcours quadratique.
