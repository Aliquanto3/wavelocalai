---
title: 'Quel modèle pour quel usage : références du banc par usage'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '37aa9f0'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-6.md'
warnings: []
deferred: []
---

# Story 5.8 : quel modèle pour quel usage

## Objectif

L'onglet « Références » de l'Arène (`#/arene/references`) montre une carte par usage publié par le banc (`qb.results/1`) : le groupe des meilleurs désigné par le serveur (intervalle, aucun rang dans un groupe à égalité, tri par nom), la part de réussite en pourcentage, le débit sur le poste de référence (PC pro de 16 Go sans carte graphique) et la marque « installé » ou « autre version ». « Comparer ces modèles » ouvre l'Arène présélectionnée sur les modèles du groupe installés (D-19). L'Accueil gagne une carte « Références » (« Quel modèle pour quel usage ? ») qui dit le meilleur score.

## Décisions de conception

Variante conservatrice pour tout ce que les décisions du 2026-10-19 ne tranchent pas.

1. **Lecture** : `models/bench_results.py` (5.6) ; `models/references.py` construit la vue (`build_references`) ; `web/routes_references.py` la sert (`GET /api/references`), depuis le cache du registre et le fichier : aucun appel d'Ollama (AD-15, budget 300 ms testé Ollama arrêté). Le front ne calcule ni rang, ni groupe, ni marque (AD-20).
2. **Usages** : les clés publiées par le schéma (`reasoning`, `instructions`, `tools`, `extraction`, `rag`, `abstention`, `writing`), libellés et mesures français côté serveur ; une clé inconnue est ignorée ; un usage sans aucun modèle classé n'a pas de carte (jamais de carte vide).
3. **Score d'un modèle pour un usage** : le résultat de la piste sans raisonnement d'abord, puis complet, puis campagne la plus récente (règle de la 5.6), pris sur le poste de référence, à défaut sur un autre poste du même fichier (la qualité ne dépend pas du poste) ; un score `null` ou `provisional` (usage `writing`) laisse le modèle « non classé » pour cet usage. Débit et énergie : toujours ceux du poste de référence (`null` sans mesure, jamais 0 ; énergie seulement si `status = "measured"`).
4. **Groupe des meilleurs** : le meilleur score, puis tous les modèles dont l'intervalle atteint celui du meilleur (`ci_high` du modèle >= `ci_low` du meilleur) ; un intervalle absent vaut le score seul (égalité stricte). Ni rang ni numéro : les membres sont triés par nom, les autres par score décroissant puis nom (tableau).
5. **Poste de référence** : le PC pro de `bench_results` (aucune carte graphique, 14 à 18 Gio) ; sans lui, `reference_machine` vaut `null`, les débits sont inconnus et l'en-tête le dit.
6. **Marques** : « installé » (mêmes poids, `exact`) ou « autre version » (même tag, autre empreinte), calculées par le serveur sur les modèles locaux de conversation. Ollama arrêté : aucune marque (`installed: null`), `ollama_up: false`, message sur l'écran, « Comparer » désactivé avec sa raison.
7. **Comparer** : le serveur donne par usage `compare.tags` (les modèles du groupe installés, tags tels qu'installés, quatre au plus par nom : l'Arène en accepte quatre) et `compare.reason` quand la liste est vide. Le clic ouvre `#/arene/comparer` et pose les modèles dans le sélecteur de l'Arène (`screens/references-compare.js`) sans modifier `arena.js` (déjà à 600 lignes) ; un run en cours dans l'Arène garde son résumé.
8. **Accueil** : `top` dit le meilleur score de toutes les cartes (modèle, usage, score) ; la carte n'existe que si l'écran est disponible et que `available` est vrai ; un seul appel (`GET /api/references`), après `shell-ready`, relu à chaque affichage de l'Accueil (comme le résumé de la base), jamais en boucle.
9. **Icône** (revue) : `help`, symbole déjà présent au sprite Rounded officiel et qui n'est l'icône d'aucun module (jamais `swords`). Aucun tracé redessiné : `leaderboard`, prévu par la maquette, viendra avec le sprite officiel Material Symbols Rounded d'Anaël (8.1). Écart à signaler à Anaël.
10. **Décision n° 11** : ni « Autres modèles mesurés », ni lien vers le tableau du banc, ni légende des marques. Le bouton « Voir le tableau » de la maquette est donc supprimé ; seul le segment « Cartes · Tableau » bascule.
11. **Version** : inchangée (2.0.0a5 posée par l'orchestrateur).

## Critères d'acceptation et preuves

1. **Cartes par usage** : une carte par usage publié, groupe des meilleurs désigné par le serveur (intervalle, aucun rang, tri par nom), « Part de réussite » en pourcentage, débit du poste de référence, marques « installé » et « autre version » ; segment « Cartes · Tableau ». Preuve : `web/test_references_api.py::test_a_card_per_published_usage_*`, `::test_the_reference_machine_*`, `::test_marks_say_*`, `::test_an_interval_missing_*`, `e2e/test_references.py::test_one_card_per_usage_*`, `::test_the_table_is_the_same_content_*`.
2. **Indisponible, Ollama arrêté** : la raison s'affiche sans carte vide ; Ollama arrêté, références lisibles, marques retirées et message. Preuve : `web/test_references_api.py::test_without_the_results_file_*`, `::test_a_file_of_another_schema_*`, `::test_a_file_without_any_ranked_model_*`, `::test_references_stay_readable_with_ollama_down_*` (moins de 300 ms), `e2e::test_without_the_results_file_*`, `::test_a_file_with_no_ranked_model_*`, `::test_with_ollama_down_*`.
3. **Décision n° 11** : ni « Autres modèles mesurés », ni lien vers le tableau du banc, ni légende. Preuve : `e2e::test_marks_say_installed_or_nothing_without_legend_*`.
4. **Comparer ces modèles** : l'Arène s'ouvre présélectionnée sur les modèles du groupe installés ; sans modèle installé, bouton désactivé (`aria-disabled`, focalisable) avec sa raison. Preuve : `web::test_compare_*`, `e2e::test_compare_opens_the_arena_*`, `::test_compare_is_disabled_*`.
5. **Accueil** : carte « Références » (nom long « Quel modèle pour quel usage ? »), meilleur score « Part de réussite 78 % », absente sans références, un seul appel après `shell-ready`, icône propre (`help`, en attendant `leaderboard`). Preuve : `web::test_the_best_score_of_all_cards_*`, `e2e::test_the_home_card_*`, `unit/test_shell_static.py::test_the_home_screen_*`.
6. **Parcours** : Sobriété (métriques sans clic), Modèles (installation simulée jusqu'à « Installé »), fiche, Références, aucune requête hors de 127.0.0.1 (garde-fou de `e2e/conftest.py`), axe-core sans violation (clair et sombre : cartes, tableau, indisponible, Ollama arrêté). Preuve : `e2e::test_journey_*`, `::test_axe_*`, `::test_the_screen_never_scrolls_horizontally`.
7. **Structure** : aucun JS au-delà de 600 lignes (`arena.js` intact), couches respectées, `GET /api/references` sous le budget de lecture. Preuve : `unit/test_static_split.py`, `unit/test_layers.py`, `web/test_read_budget.py`.
8. **Version** : inchangée (2.0.0a5 posée par l'orchestrateur) ; tag et release : orchestrateur.

## Hors périmètre

Les défauts `agent` et `rag` calés sur le banc (5.7), toute création sous `benchmarks/`, la version, la release.

## Notes de développement

- Serveur : `models/usage_references.py` (`build_usage_references`), `models/bench_results.py` (`usage_score`, `best_result(…, usage)`), `web/routes_references.py`, `web/app.py`. Contrat : sous-section « Références (story 5.8) » de `contrat-api.md`.
- Front : `screens/references.js` (écran, relu à chaque retour), `references-view.js` (cartes, tableau), `references-compare.js` (présélection de l'Arène sans toucher `arena.js`), `home-references.js` (carte de l'Accueil), `core/api/references.js`, `i18n/fr/references.json`, `references.css`, icône `help` (déjà au sprite).
- Tests réalignés : `unit/test_shell_static.py` (8 écrans disponibles, la route Références n'est plus « planned », la carte lit un seul appel), `e2e/test_shell.py` (Références n'est plus une route de la maquette). `web/test_model_card_api.py::card_app` accepte `bench_data` (fichier de résultats propre au test).

## Écarts et reports

- **Icône** : la carte Références porte `help` (déjà au sprite Rounded, aucune icône de module). Le tracé `i-leaderboard` écrit de mémoire a été retiré en revue (règle du sprite : jamais redessiné à la main) ; `PENDING_ROUNDED` reste à 8. `leaderboard` est à poser avec le sprite officiel d'Anaël (8.1).
- **Schéma réel non synchronisé** : aucun `qb.results/1` réel sur `master` ; l'écran se teste avec la fixture réécrite. Les libellés des sept usages (`reasoning`, `instructions`, `tools`, `extraction`, `rag`, `abstention`, `writing`) sont ceux du schéma publié ; la décision Q7 disait que le banc ne publie pas « Réponse sur documents », mais le schéma a la clé `rag` : elle s'affiche si le banc la publie.
- **« Non classés pour cet usage »** de la maquette : abandonné sur les cartes (proche du bloc « Autres modèles mesurés » retiré par la décision n° 11) ; ces modèles figurent seulement dans le tableau (« non classé »).
- **« Comparer »** : quatre modèles au plus (limite de l'Arène) ; avec un seul modèle installé, l'Arène le présélectionne et dit elle-même qu'il en faut deux. Un run en cours dans l'Arène garde son résumé (le choix est posé dans le formulaire caché).
- **Relecture** : l'écran relit `GET /api/references` à chaque retour dessus ; le registre rafraîchit en tâche de fond (AD-15), donc une marque « installé » peut avoir un retour de retard.
- **Conflit attendu** : `test_shell_static.py` (compte des écrans `available`) avec la 7.4.

## Rapport de dev

- Joué (poste partagé) : `tests/v2/unit` en entier, `tests/v2/web` (`test_references_api`, `test_model_card_api`, `test_read_budget`), E2E Edge `test_references` (19), `test_home`, `test_shell`, `test_home_demo`. Contrôle rapide du projet propre.
- Aucune dépendance nouvelle, aucun fichier d'état ni de `benchmarks/` touché.

## Revue

Revue Opus du 2026-10-19 (commits d3b7ff8 et 1f94396, après fusion de `origin/master` : conflits `web/app.py` et `web/routes_test.py` résolus en gardant les deux côtés).

- Medium · second avis n° 1 · corrigé : à égalité au meilleur score, le plancher du groupe dépendait du nom retenu (`_leader`) ; il vaut désormais la plus basse des bornes basses des ex æquo. `top` de l'Accueil ne dépend que du score (le nom ne fait que départager l'affichage) : inchangé. Test `web::test_a_tie_at_the_best_score_takes_the_lowest_floor_whatever_the_names` (échoue sur l'ancien code).
- Low · second avis n° 2 · corrigé : `best_result(…, usage)` écartait les résultats à score `null` ou provisoire et prenait celui d'une autre piste ou d'un autre poste, contre la décision 3. Le filtre ne garde plus que les résultats dont le jeu couvre l'usage ; `null` ou provisoire y laisse le modèle « non classé ». Test `web::test_a_null_score_on_the_reference_machine_is_unranked_not_replaced`. Contrat aligné.
- Low · second avis n° 3 · corrigé : `compare.tags` prenait aussi les « autre version » ; seuls les mêmes poids (`installed`) partent dans l'Arène. Test `web::test_compare_leaves_out_another_version_of_a_best_model`. Contrat aligné.
- Low · second avis n° 4 · rejeté : le critère 5 fixe « Part de réussite 78 % » sur la carte de l'Accueil, qui nomme aussi l'usage ; `top.measure` reste servi pour un usage futur.
- Low · second avis n° 5 · corrigé : l'écran Références lisait deux fois `GET /api/references` à la première visite (montage, puis affichage par le routeur, qui monte l'hôte masqué) ; lecture au montage seulement s'il est déjà affiché, comme l'Accueil.
- Medium · second avis n° 6 (icône) · corrigé, variante conservatrice : tracé `i-leaderboard` écrit de mémoire retiré, `icons.svg`, `icons.LICENSE.txt` et `PENDING_ROUNDED` (8, test « does_not_grow ») remis tels qu'avant la story ; la carte porte `help`, déjà au sprite Rounded et icône d'aucun module. `leaderboard` attend le sprite officiel d'Anaël (8.1).
- Low · second avis n° 7 · corrigé : sans `bench_version`, la ligne de source n'a plus d'espace avant le point (la version porte son espace).
- Info · revue · reporté : `e2e/test_shell.py::test_shell_renders_under_300_ms_*` échoue sur ce poste chargé (repère `ready` entre 300 et 370 ms), aussi sans les correctifs de la revue : charge du poste partagé, la CI tranche.
- Low · revue (complexité) · corrigé : `_usage` recalculait l'ensemble des modèles mesurés pour chaque modèle (quadratique en nombre de modèles, par usage) ; calculé une fois par usage. Le reste est borné par le fichier publié, sans structure qui grossit pendant l'exécution.
