---
title: 'Maquette de la nouvelle mise en page'
type: 'docs'
created: '2026-10-21'
status: 'review'
baseline_commit: 'ba606cb'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-21.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings:
  - 'En attente de la validation d''Anaël : DESIGN.md et EXPERIENCE.md ne sont amendés qu''après son accord (story 9.6, deuxième critère), avant la story 9.7.'
deferred: []
---

# Story 9.6 : Maquette de la nouvelle mise en page

## Objectif

Avant toute refonte visuelle (stories 9.7 à 9.9), Anaël valide une maquette statique de la nouvelle mise en page — grille à deux colonnes, hiérarchie des champs, couleur par module — sur les écrans les plus représentatifs, en clair et en sombre, du mobile au grand écran.

## Critères d'acceptation et preuves

1. **Maquette** : `docs/maquette-v2-mise-en-page/index.html`, fichier HTML unique (CSS et JS inline, aucune ressource externe, icônes Material Symbols Rounded en SVG inline copiées de `icons.svg`), avec un sélecteur d'écran (Banc d'essai, Arène formulaire, Arène résultats, Base documentaire, Modèles), de largeur simulée (1920, 1440, 1280, 390 px, cadre à largeur fixe mis à l'échelle) et de thème (clair/sombre). Contenu fictif uniquement. Preuve : le fichier, vérifié par Playwright (Edge headless) sur les 5 écrans × 2 largeurs (1920, 390) × 2 thèmes : zéro erreur console, zéro défilement horizontal.
2. **Exigences de layout visibles** :
   - grille à deux colonnes dès 1400 px environ sur les écrans de configuration (Banc d'essai, Arène formulaire) : saisie et choix du modèle à gauche, réglages repliés et aperçu/résultats à droite ; une seule colonne en dessous (1280 et 390 px) ;
   - prompt en police normale dans un grand champ (`textarea.big-input`), modèles en cartes de choix (`.model-card`), bouton principal (« Lancer le test », « Lancer la comparaison ») visible sans défilement vertical à 1920×1100 ;
   - réglages secondaires dans un `<details>` replié, intertitres (`--text-section-label`, 13 px, majuscules) plus petits que les libellés de champ principal (`--text-field-label`, 17 px) ;
   - Arène résultats : bandeau du juge « Juge : Gemma3 12B · Notation 2 sur 3 », trois colonnes de modèles dont une « Arrêté : le modèle se répétait » (réponse partielle gardée, notée) ;
   - Base documentaire : encart d'alerte « Installer nomic-embed-text » avant la zone d'import, désactivée avec sa raison ;
   - Modèles : encart du reranker, tableaux « Sur ce poste », « Catalogue installable » et « Modèles proposés par défaut » compacts (hauteur totale mesurée ≈ 1315 px à 1920 px de large, loin sous les 3900 px actuels) ;
   - icônes Material colorées par module (violet Arène, bleu Banc d'essai, vert Base documentaire, ambre Modèles), aplat léger de la primaire (8 %) sur les zones d'action, aucun emoji.
3. **Contrastes** : `DECISIONS.md` donne la table des contrastes calculés avec la même méthode que la story 8.2 (luminance relative WCAG, formule de `tests/v2/e2e/test_accessibilite.py`), clair et sombre, pour chaque couple nouveau (icônes par module, aplat d'action). Une limite connue est documentée (icône Modèles sur `chart-4` clair, 2,95:1, sous le seuil), avec un jeton dédié proposé pour la lever.
4. **Décisions à trancher** : `DECISIONS.md` liste les choix chiffrés (bascule de grille, largeurs de colonnes, échelle typographique, couleurs, jetons à ajouter), la table des contrastes, 6 questions fermées avec recommandation, et un brouillon (non appliqué) des amendements de `DESIGN.md` (§Brand 4, §Layout, §Typography) et `EXPERIENCE.md`.
5. **Validation en attente** : cette story reste `status: review` ; `DESIGN.md`, `EXPERIENCE.md`, `sprint-status.yaml` et `run-autonome.md` ne sont pas modifiés. Une fois Anaël d'accord, les amendements du §3 de `DECISIONS.md` sont reportés dans les deux documents avant la story 9.7 (hors périmètre de cette story).

## Règles écrites

- Aucun fichier de `src/wavelocalai/` n'est modifié : la maquette est un document autonome dans `docs/`.
- Aucune donnée réelle : tous les modèles, documents et résultats affichés sont fictifs (« Qwen3.6 2B », « note-cadrage.docx »…).
- Aucun téléchargement de modèle, aucun appel à Ollama : la vérification Playwright ouvre le fichier en local (`file://`).

## Écarts et variantes conservatrices

- La maquette précédente (`docs/maquette-v2/`) est un simulateur complet (modules ES, scénarios, flux SSE rejoués) ; cette story en demande une version plus légère, un seul fichier HTML statique, suffisante pour juger la mise en page (le simulateur complet n'est pas dans le périmètre de 9.6).
- L'écran Arène résultats n'est pas mis dans la grille à deux colonnes gauche/droite : le bandeau du juge et les colonnes de réponse occupent la pleine largeur (question 4 de `DECISIONS.md`, à confirmer par Anaël). La grille à deux colonnes s'applique à la phase de configuration (avant de lancer).
- Icône du module Modèles : `chart-4` clair ne tient pas 3:1 ; la maquette introduit un jeton dédié (`#A66E00`) plutôt que de garder la limite, proposé comme choix à trancher (question 3).

## Fichiers

- `docs/maquette-v2-mise-en-page/index.html`
- `docs/maquette-v2-mise-en-page/DECISIONS.md`
- `_bmad-output/implementation-artifacts/story-9-6.md` (ce fichier)

## Rapport de dev

- Vérification : script Playwright (Edge headless, `WAVELOCALAI_E2E_CHROMIUM`) ouvrant `index.html` en `file://`, parcourant les 5 écrans × {1920, 390} × {clair, sombre} : aucune erreur console/page, aucun défilement horizontal (`scrollWidth` ≤ `clientWidth`), captures prises hors dépôt (scratchpad de session).
- Pas de suite de tests du projet à lancer : aucun fichier Python ni JS applicatif modifié.
- Contrôle rapide du projet (ruff/black/isort sur les fichiers modifiés) : sans objet côté code, aucun fichier suivi par le contrôle rapide n'est touché ; exécuté quand même pour vérifier qu'il reste propre.
- Reports : amendements de `DESIGN.md`/`EXPERIENCE.md` et simulateur interactif complet (`docs/maquette-v2/`-like) laissés à la story 9.7, après validation d'Anaël sur les 6 questions de `DECISIONS.md`.

## Revue

En attente (second avis puis reviewer, par l'orchestrateur).
