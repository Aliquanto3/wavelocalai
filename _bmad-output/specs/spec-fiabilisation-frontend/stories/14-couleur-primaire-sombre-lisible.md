---
title: 'Couleur primaire du thème sombre lisible'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** En sombre, Streamlit emploie `primaryColor` `#6A4DE6` comme couleur de texte : valeur du curseur de l'Arène à 3,57:1, pastilles d'outils choisies de l'agent à 3,34:1 ; `test_axe_no_theme_violation[Inference_Arena-dark]` et `[Agent_Lab-dark]` échouent.

**Approach:** Remplacer la primaire sombre dans `.streamlit/config.toml`, DESIGN.md et `tests/app/test_theme.py`, puis vérifier par axe en sombre. Décision de l'utilisateur (27/09) : `#8468EC`, sous réserve de la vérification axe.

Décisions après vérification (27/09) : `#8468EC` puis `#886DED` écartés ; aucune valeur unique ne donne 4,5:1 à la fois au texte blanc des boutons principaux et au violet employé comme texte. Retenu : `#7E65E9`, compromis qui rend le plus faible contraste aussi haut que possible ; le test axe `Agent_Lab` en sombre reste en échec sur les pastilles (4,24:1), écart accepté et documenté.

</frozen-after-approval>

## Code Map

- `.streamlit/config.toml:57` -- `[theme.dark] primaryColor` (valeur de test `#8468EC` appliquée, non commitée).
- `_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md:27,156` -- token `primary-dark` et tableau Colors (mis à jour pour `#8468EC`).
- `tests/app/test_theme.py:32` -- valeur attendue du thème sombre.
- `tests/e2e/README.md:71`, `tests/e2e/test_accessibility.py:17` -- textes sur la décision en attente, à réécrire une fois tranchée.
- `src/app/static/wordmark.svg` -- reste `#6A4DE6` : image unique pour les deux thèmes, grand texte (seuil 3:1).

## Implementation Notes

- Le fond d'une pastille choisie dérive de la primaire (10 % sur le fond) : `#16132A` avec `#8468EC`, d'où 4,45:1 mesuré au lieu des 4,53:1 annoncés sur un fond fixe. `#886DED` passait axe mais mettait le texte blanc des boutons principaux (14 px, graisse normale) à 3,85:1, relevé à la main : axe ne voit pas ces boutons (onglets masqués) et classe le blanc hors thème.
- Contraintes incompatibles : blanc dessus ≥ 4,5:1 exige une luminance ≤ 0,183, texte sur `#0A0A14` ≥ 0,190. `#7E65E9` maximise le plus faible : boutons 4,26:1, curseur 4,62:1, curseur de la barre latérale 4,17:1, pastilles 4,25:1 (4,24:1 par axe).
- Fichiers : `.streamlit/config.toml`, DESIGN.md (token, tableau Colors, note `primary-dark`), `tests/app/test_theme.py` (valeur attendue et planchers de contraste calculés depuis la config), `tests/e2e/README.md`, docstring de `tests/e2e/test_accessibility.py`, commentaire de `src/app/static/wordmark.svg` (couleur fixe `#6A4DE6` conservée), `RAPPORT-NUIT.md` (décision tranchée).
- Vérifié : `tests/e2e/test_accessibility.py` 9 réussis sur 10, seul `Agent_Lab-dark` échoue sur les 8 pastilles à 4,24:1 ; `tests/app/test_theme.py` 19 réussis.

## Review Triage Log

Revue Blind Hunter (9 constats) :

- Commentaire du wordmark devenu faux — low, corrigé (couleur fixe documentée).
- Seuil de luminance 0,191 au lieu de 0,190 — low, corrigé.
- Curseur de la barre latérale (RAG) à 4,17:1 non mentionné — medium, corrigé (note DESIGN.md, README).
- Composants touchés hors de la vue d'axe (pastilles de filtre, outils de l'équipe) — medium, corrigé (écarts décrits par type de composant).
- Aucun test sur le contraste des boutons — medium, corrigé (planchers calculés depuis `config.toml`).
- Test axe toujours en échec — medium, différé : l'utilisateur a retenu l'option où il reste en échec, documenté ; une liste d'écarts acceptés dans le test est notée dans deferred-work.md.
- Critère du choix non écrit — medium, corrigé (note `primary-dark` : critère et valeurs écartées).
- Question ouverte du rapport de nuit non close — low, corrigé.
- 4,24 mesuré contre 4,25 calculé — low, corrigé (méthode indiquée).

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/e2e/test_accessibility.py -m e2e` -- expected: 10 réussis
- `.venv-app\Scripts\python -m pytest tests/app/test_theme.py -q` -- expected: tout réussit
