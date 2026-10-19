---
title: 'Story 8.2 : tous les écrans sont accessibles et lisibles en projection'
type: 'feature'
created: '2026-10-20'
status: 'review'
baseline_commit: 'eed68bf'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
warnings: []
deferred:
  - 'Recette manuelle (clavier seul, NVDA, couleurs, validation W3C, zoom réel, vidéoprojecteur) : listée en tête de `docs/accessibilite/grille-rgaa-v2.md`, à jouer par Anaël.'
  - 'Écarts E2 (8.7, langue des réponses de modèles) et E3 (12.1, second système de navigation) : stories de correctif à créer après la 8.4.'
---

# Story 8.2 : accessibilité et projection

Gouvernée par AD-20, NFR8, UX-DR2, UX-DR19, UX-DR25 ; report B16. Branche `feat/v2-accessibilite`, empilée sur `feat/v2-dette` (8.1).

## Périmètre

1. E2E d'accessibilité de toutes les routes du registre, sans liste en dur : `tests/v2/e2e/test_accessibilite.py`.
2. Corrections des écarts trouvés.
3. Grille RGAA 4.1 : `docs/accessibilite/grille-rgaa-v2.md`, avec la recette manuelle et la recette du mode projection (Flow 1) laissées à Anaël.
4. Décision B16 appliquée et testée.

Aucun téléchargement, aucune dépendance : axe-core vient du paquet `axe-playwright-python` déjà utilisé par les E2E.

## Tests ajoutés (`test_accessibilite.py`)

Routes lues dans `core/registry.js` (`SCREENS`, statut `available`) ; un test vérifie qu'aucune n'est `planned`. Liste des modèles simulée (`page.route`), comme les autres E2E, pour des écrans remplis.

- **axe, six affichages** : Clair, Sombre, Système avec un système clair, Système avec un système sombre, projection en clair, projection en sombre. États : au repos, liste des modèles, fiche d'un modèle, panneaux dépliés (tout `aria-expanded="false"` activé), dialogue de confirmation avec et sans détail, chat avec réflexion et aide ouvertes, Arène terminée rouverte et son dialogue d'effacement, fiche et suppression d'un modèle, Sobriété avec l'historique de ces réponses. Un ensemble d'états attendus est vérifié (rien n'est sauté en silence). axe tourne sans règle désactivée ni exclusion.
- **Panneaux de la barre haute** (Ollama, aide du cloud, CO₂, Affichage), sur chaque route, dans les six affichages.
- **Reflux** : aucun défilement horizontal de la page à 320 px, au zoom 200 % (640 px) et avec un texte à 200 %, en clair et en projection sombre, dans les mêmes états ; un élément plus large que la fenêtre n'est toléré que dans un ancêtre qui défile (tableaux). axe aussi à 320 et 640 px.
- **Espacement du texte** (WCAG 1.4.12) : aucun texte coupé ni défilement à 1 440 et 320 px.
- **Clavier** : en tabulant, chaque arrêt a un indicateur de focus et le parcours avance ; aucun `tabindex` positif.
- **Structure** : `lang="fr"`, un `h1` et un titre de page distinct par écran.
- **Projection** : le plus petit texte de chaque écran (SVG compris, à l'échelle de sa `viewBox`) grandit du rapport 9/7 et reste à 15 px au moins.
- **Contrastes des jetons** de composants (3:1) sur les deux fonds, clair et sombre.
- **B16** : voir ci-dessous.
- **États attendus écran par écran** (revue) : `EXPECTED_BY_ROUTE` ; un écran qui perd sa liste ou son dialogue fait échouer T1, T3 et T4.
- **Contrastes « incomplets » d'axe** (revue) : calculés par le test (`OWN_CONTRAST`), oracle vérifié sur des valeurs écrites à la main.

## Écarts trouvés et corrigés

| Écran ou composant | Écart | Correctif |
|---|---|---|
| Modèles (320 px, projection) | La page débordait de 10 px : la piste de la grille `.models-actions` s'élargissait au plus large de ses contenus. | `models.css` : `grid-template-columns: minmax(0, 1fr)`. |
| Équipe d'agents (projection) | Le schéma (`wl-team-graph`) avait une largeur maximale en px : son texte restait à 13 px en projection, et ne suivait pas la taille de texte du navigateur. | Largeur maximale en `rem` (`wl-team-graph.js`). |
| Réponses (Markdown) | Un lien `target="_blank"` n'annonçait pas la nouvelle fenêtre (RGAA 13.2). | `title` « S'ouvre dans une nouvelle fenêtre » (`core/markdown.js`, `components.json`). |
| Modèles (état vide, fiche sans références) | Deux textes renvoyaient à la position (« ci-dessous », « ci-dessus ») : RGAA 10.10. | Réécrits en nommant la section et la fiche ; test de la fiche réaligné. |

Les autres écrans, les composants et leurs panneaux et dialogues n'ont donné aucune violation axe dans les six affichages. Aucun fichier JS ne dépasse 600 lignes (`arena.js` intact).

## B16 : focus au premier chargement

Tranché en revue : le critère écrit de la story 1.8 (« à chaque route, le focus va sur le `h1` ») s'applique aussi au premier chargement, lien profond compris (`router.js`). Le lien d'évitement reste le premier élément focalisable du document (RGAA 12.7 : présence, position, fonctionnement conservés) et se rejoint par Maj+Tab depuis le `h1`. Aucune contre-indication RGAA ; le coût (au chargement, la navigation se rejoint en remontant) est à juger par Anaël en recette R1 et R2 (NVDA). La première version gardait le focus en tête au chargement.

## Écarts

- E1 : B16, ci-dessus (tranché en revue, à confirmer en recette NVDA).
- Recette du mode projection : non simulée ; la liste des points à vérifier est dans la grille (R8).
- La grille classe 8.7 (langue des réponses) et 12.1 (second système de navigation) « non conforme, reporté » : stories de correctif à créer après la 8.4. Les points chart-4 (2,95:1) sont gardés, contour d'encre (R3).
- Le serveur de test est celui des autres E2E (Ollama arrêté) : les états « remplis » viennent de réponses simulées et de la route de test des runs.

## Reports

- Recette manuelle (R1 à R8) : Anaël.
- Stories de correctif pour E2 et E3 : à créer par l'orchestrateur, après la 8.4.
- Un E2E d'accessibilité de l'Équipe en mission et des états de la Base documentaire avec documents importés reste couvert par les tests de chaque écran (clair et sombre), pas par la matrice à six affichages.

## Tests exécutés

`tests/v2/e2e/test_accessibilite.py` (31 tests, 6 min sur ce poste chargé) ; `test_models_card.py`, `test_agents_crew.py`, `test_models_manage.py`, `test_components.py`, `test_chat.py` (axe et Markdown) ; `tests/v2/unit/test_shell_static.py`, `test_static_split.py`, `test_chat_static.py`, `test_layers.py`, `tests/v2/web/test_static.py`, `test_models_static.py`. Pas de suite complète (poste partagé, consigne de l'orchestrateur).

## Revue

Revue Opus, une passe, sur `feat/v2-accessibilite` à jour de `feat/v2-dette` (fusion 24afe7b) ; second avis Haiku repris point par point.

| Sévérité | Source | Constat | Suite | Motif |
|---|---|---|---|---|
| medium | second avis 1 | `Axe().run` sans options : les résultats `incomplete` de `color-contrast` (texte des SVG de l'équipe et des graphiques, texte d'un caractère, fond recouvert par la liste ou la fiche ouverte, coin arrondi du dialogue) jamais examinés, alors que la grille dit 3.2 conforme. | Corrigé | Sondés sur toutes les routes (quatre causes seulement : `bgOverlap`, `imgNode`, `shortTextContent`, `elmPartiallyObscuring`) ; `axe_problems` calcule leur contraste (`OWN_CONTRAST` : couleur ou `fill`, formes du SVG dessous, fonds des ancêtres ; non calculable = échec), oracle T12 sur valeurs écrites à la main. Tous tiennent. |
| medium | second avis 2 | États vérifiés en union sur toutes les routes : un écran qui perd son dialogue passait en silence. | Corrigé | `EXPECTED_BY_ROUTE` (états mesurés écran par écran), contrôlé dans T1, T3 et T4 ; une ligne sans écran du registre échoue, un écran nouveau est vérifié au repos. |
| medium | second avis 3 | `overflow()` tenait un ancêtre `overflow: hidden/clip` pour un conteneur qui défile : contenu coupé à 320 px ou 200 % non vu. | Corrigé | Seuls `auto`/`scroll` excusent ; `hidden`/`clip` signalés, comme une racine ou un `body` qui masque le défilement. T3 et T5 passent. |
| medium | second avis 4, orchestrateur | B16 gardait le focus en tête au premier chargement, contre le critère écrit de la 1.8. | Corrigé | Focus sur le `h1` au premier chargement (`router.js`) ; lien d'évitement premier focalisable, atteint par Maj+Tab ; T11 réécrit, `test_shell.py` réaligné, grille (B16, 12.7, E1). À confirmer par Anaël (NVDA). |
| low | second avis 5 | Attentes fixes et `prepare_rich` rejoué par paramètre : environ 6 min dans un seul morceau de CI. | Reporté | Sous le délai de 30 min du morceau ; les remplacer par des attentes d'état demande de connaître chaque lecture de chaque écran : à reprendre si le morceau approche du délai. |
| low | second avis 6 | T9 ne prouve que les ratios des jetons. | Corrigé (grille) | Grille T9 et 3.3 réécrites : jetons prouvés, emploi vu à la relecture, 3.3 reste à vérifier par Anaël. |
| low | second avis 7 | Grille 11.12 citait T1 pour « Annuler » en focus initial. | Corrigé (grille) | Preuves réelles citées : `test_agents_solo.py`, `test_arena_reopen.py`. |
| low | second avis 8 | `SMALLEST_TEXT` à l'infini pour un écran sans texte : T10 passait sans mesure. | Corrigé | T10 échoue si un écran n'a aucun texte mesuré. |
| low | revue | axe signale parfois `:root` en contraste incomplet pendant l'ouverture d'un panneau (Système sombre). | Corrigé | Un élément sans texte propre est ignoré par `OWN_CONTRAST`. |
| — | revue | Complexité : 0 constat (aucune structure qui grossit à l'exécution dans le diff ; les boucles du test sont bornées par routes et scènes). | — | — |

Tests de la revue : `test_accessibilite.py` (32), `test_shell.py`, `test_core.py`, `test_home.py`, et les E2E qui tabulent ou tapent au clavier (agents, Arène, banc, chat, composants, documents, évaluation, fiche, sélecteur, sobriété, barre haute).
