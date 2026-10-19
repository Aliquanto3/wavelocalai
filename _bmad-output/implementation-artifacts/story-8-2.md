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

## Écarts trouvés et corrigés

| Écran ou composant | Écart | Correctif |
|---|---|---|
| Modèles (320 px, projection) | La page débordait de 10 px : la piste de la grille `.models-actions` s'élargissait au plus large de ses contenus. | `models.css` : `grid-template-columns: minmax(0, 1fr)`. |
| Équipe d'agents (projection) | Le schéma (`wl-team-graph`) avait une largeur maximale en px : son texte restait à 13 px en projection, et ne suivait pas la taille de texte du navigateur. | Largeur maximale en `rem` (`wl-team-graph.js`). |
| Réponses (Markdown) | Un lien `target="_blank"` n'annonçait pas la nouvelle fenêtre (RGAA 13.2). | `title` « S'ouvre dans une nouvelle fenêtre » (`core/markdown.js`, `components.json`). |
| Modèles (état vide, fiche sans références) | Deux textes renvoyaient à la position (« ci-dessous », « ci-dessus ») : RGAA 10.10. | Réécrits en nommant la section et la fiche ; test de la fiche réaligné. |

Les autres écrans, les composants et leurs panneaux et dialogues n'ont donné aucune violation axe dans les six affichages. Aucun fichier JS ne dépasse 600 lignes (`arena.js` intact).

## B16 : focus au premier chargement

La spec ne dit rien de plus que « à chaque route » (lu en 1.8 comme « à chaque changement d'écran »). Variante conservatrice : au premier chargement le focus reste en tête (le premier Tab atteint « Aller au contenu », RGAA 12.7), le titre de la page et l'annonce polie sont posés dès le premier rendu ; à chaque changement d'écran, le focus va sur le `h1`. C'était le comportement livré ; la story l'écrit (`router.js`), le teste et le consigne dans la grille. Si la recette NVDA le met en défaut, l'inverse tient en quelques lignes du routeur.

## Écarts

- E1 : B16, ci-dessus.
- Recette du mode projection : non simulée ; la liste des points à vérifier est dans la grille (R8).
- La grille classe 8.7 (langue des réponses) et 12.1 (second système de navigation) « non conforme, reporté » : stories de correctif à créer après la 8.4. Les points chart-4 (2,95:1) sont gardés, contour d'encre (R3).
- Le serveur de test est celui des autres E2E (Ollama arrêté) : les états « remplis » viennent de réponses simulées et de la route de test des runs.

## Reports

- Recette manuelle (R1 à R8) : Anaël.
- Stories de correctif pour E2 et E3 : à créer par l'orchestrateur, après la 8.4.
- Un E2E d'accessibilité de l'Équipe en mission et des états de la Base documentaire avec documents importés reste couvert par les tests de chaque écran (clair et sombre), pas par la matrice à six affichages.

## Tests exécutés

`tests/v2/e2e/test_accessibilite.py` (31 tests, 6 min sur ce poste chargé) ; `test_models_card.py`, `test_agents_crew.py`, `test_models_manage.py`, `test_components.py`, `test_chat.py` (axe et Markdown) ; `tests/v2/unit/test_shell_static.py`, `test_static_split.py`, `test_chat_static.py`, `test_layers.py`, `tests/v2/web/test_static.py`, `test_models_static.py`. Pas de suite complète (poste partagé, consigne de l'orchestrateur).
