---
title: 'Story 9.7 : fondation de la mise en page et écrans de l''Arène'
type: 'feature'
created: '2026-10-22'
status: 'review'
baseline_commit: 'c7804ec'
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/docs/maquette-v2-mise-en-page/DECISIONS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
warnings: []
deferred:
  - 'Captures du README (docs/assets/v2-*.png, v2-demo.gif) à régénérer'
---

# Story 9.7 : fondation de la mise en page et écrans de l'Arène

Critères : `epics.md`, story 9.7. Maquette : `docs/maquette-v2-mise-en-page/` (DECISIONS.md §4 à §6).
Fiche écrite à la revue (le développement n'en avait pas laissé) : elle sert de contrat aux stories
9.8 et 9.9.

## Contrat pour les stories 9.8 et 9.9

Jetons (`tokens.css`, miroir dans le front matter de `DESIGN.md`) : `--color-icon-arena`,
`--color-icon-bench`, `--color-icon-documents`, `--color-icon-models`, `--color-amber-strong`,
`--color-action-tint`, `--text-section-label` (0.8125rem), `--text-field-label` (1.0625rem). Tous
posés dès 9.7 (y compris ceux que DECISIONS.md §6 attribuait à 9.8), en clair et en sombre.

Classes génériques de `base.css` (nom et comportement stables) :

| Classe | Comportement | Usage attendu |
|---|---|---|
| `.two-col` | grille une colonne ; dès 1400px, `minmax(480px, 1fr)` à gauche et `minmax(320px, 400px)` à droite | conteneur de configuration (formulaire) d'un écran |
| `.stack` | colonne flex, `gap: 1rem` | colonne gauche de `.two-col` |
| `.col-right` | colonne flex, `gap: 1rem` | colonne droite de `.two-col` (réglages, lancement, aperçu) |
| `.section-label` | intertitre 13 px, majuscules, `ink-secondary` | « Réglages », « Scénario »… (h2, p, label ou summary) |
| `.field-label` | libellé de champ 17 px, gras, `ink` | prompt, choix du modèle |
| `.icon-mod` + `.arena` / `.bench` / `.docs` / `.models` | icône colorée sur pastille à 8 % | via `moduleTitle(icon, mod, texte)` de `core/dom.js` |
| `.judge-banner` | bandeau sur aplat `action-tint`, icône en `primary` | bandeau du juge (Arène) |
| `.alert-warning` | encart à liseré `amber-strong` | modèle de représentation manquant (9.8) |
| `.zone-disabled` | bordure pointillée, fond `surface-alt`, texte secondaire (jamais l'opacité) | zone de dépôt désactivée (9.8) ; nommée `.dropzone-disabled` dans la maquette |

Écrans de la story : Chat libre, Arène (formulaire en `.two-col`, bandeau du juge ; lanes et statut
« Arrêté » déjà livrés par 9.2 et 9.3), Banc d'essai (formulaire en `.two-col`), Références. Les
quatre onglets de l'Arène portent l'icône de module devant leur `h1` (épées violettes ; chronomètre
bleu pour le Banc d'essai).

## Revue

Revue Opus (une passe, branche rebasée sur `origin/master` c7804ec, sans conflit).

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| medium | second avis 1 | classe `stack` sans règle CSS : colonne gauche de l'Arène et du Banc sans espacement | corrigé : `.stack` (flex colonne, gap 1rem, comme la maquette) dans `base.css` |
| medium | second avis 2 | captures du README (`scripts/readme_captures_v2.py`, `docs/assets/`) non régénérées | reporté : le script tourne sur doublures (faux Ollama, note fictive), sans contenu client, mais il lance un serveur et Edge sur tous les écrans et le poste, saturé, a déjà coupé deux commandes longues ; à lancer en recette : `.venv\Scripts\python scripts/readme_captures_v2.py`, vérifier `v2-arene.png` (grille à deux colonnes, icône de module) puis commiter `docs/assets/` |
| low | second avis 3 | `judgePanel` importé sans usage dans `arena.js` | corrigé : import retiré (le panneau est construit dans `buildForm`) |
| low | second avis 4 | Chat libre et Références sans icône de module | corrigé : `moduleTitle("swords", "arena", …)`, comme l'onglet Comparer (même module Arène) ; pas de grille, ces écrans n'ont pas de formulaire de configuration |
| low | second avis 5 | résultats de l'Arène non retouchés | écarté : lanes et statut « Arrêté » livrés par 9.2 au format de la maquette ; le bandeau du juge prend `.judge-banner` (aplat `action-tint`) ; DECISIONS.md §4 point 4 garde les résultats hors de la grille à deux colonnes |
| low | second avis 6 | classes de `base.css` sans usage (`.alert-warning`, `.zone-disabled`, `.icon-mod.docs/.models`) | écarté : voulu pour 9.8 et 9.9, contrat documenté ci-dessus |
| low | second avis 7 | test de contraste des pastilles qui recalcule le mélange (oracle de même formule) | corrigé : le test pose un vrai `.icon-mod.<module>` dans la page et mesure la couleur et le fond rendus (canevas 1x1, `color-mix` résolu par le navigateur) ; il échoue si la classe manque |
| medium | revue | deux E2E cassés par les intertitres en majuscules CSS (`inner_text()` rend « CRITÈRES DE NOTATION », « GROUPE DES MEILLEURS ») : `test_arena.py::test_the_criteria_panel_is_folded…`, `test_references.py::test_one_card_per_usage…` | corrigé : assertions sur le texte du DOM (`text_content()`) ; le nom accessible et les `get_by_label`/`get_by_role` ne changent pas |
| info | revue | `test_arena.py::test_axe_finds_no_violation_with_four_models…[*-1440]` instable (le résumé ne reste visible que 0,3 à 0,5 s) | hors story : échoue aussi sur `master` c7804ec (1 ou 2 échecs sur 4 à chaque passe, trois passes) ; à stabiliser à part |
| info | revue | `test_no_horizontal_scroll_on_any_route[*-320 px]` échoue sur `/modeles` | hors story : échoue aussi sur `master` c7804ec |
| info | revue | `test_every_screen_has_one_h1_a_distinct_title…` instable quand il suit d'autres tests (titre lu avant la fin du changement d'écran) | hors story : vert seul (trois fois sur trois) ; `master` montre la même instabilité sur le test du clavier |

Complexité : aucun constat (aucune structure qui grossit pendant l'exécution n'est touchée).
