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

1. **Maquette** : `docs/maquette-v2-mise-en-page/index.html`, fichier HTML unique (CSS et JS inline, aucune ressource externe, icônes Material Symbols Rounded en SVG inline copiées de `icons.svg`), avec un sélecteur d'écran (Banc d'essai, Arène formulaire, Arène résultats, Base documentaire, Modèles), de largeur simulée (1920, 1440, 1280, 390 px, cadre à largeur fixe mis à l'échelle) et de thème (clair/sombre). Contenu fictif uniquement. Preuve : le fichier, vérifié par Playwright (Edge headless) sur les 5 écrans × 4 largeurs simulées × 2 thèmes, dans des fenêtres de 1920 et 1440 px : zéro erreur console, zéro requête hors du fichier, aucun débord horizontal dans le cadre ni dans la page (tableaux en lignes étiquetées à 390 px).
2. **Exigences de layout visibles** :
   - grille à deux colonnes dès 1400 px environ sur les écrans de configuration (Banc d'essai, Arène formulaire) : saisie et choix du modèle à gauche, réglages repliés et aperçu/résultats à droite ; une seule colonne en dessous (1280 et 390 px) ;
   - prompt en police normale dans un grand champ (`textarea.big-input`), modèles en cartes de choix (`.model-card`), bouton principal (« Lancer le test », « Lancer la comparaison ») visible sans défilement vertical à 1920×1100 ;
   - réglages secondaires dans un `<details>` replié, intertitres (`--text-section-label`, 13 px, majuscules) plus petits que les libellés de champ principal (`--text-field-label`, 17 px) ;
   - Arène résultats : bandeau du juge « Juge : Gemma 4 12B · Notation 2 sur 3 », trois colonnes de modèles dont une « Arrêté : le modèle se répétait » (réponse partielle gardée, notée) ;
   - Base documentaire : encart d'alerte « Installer nomic-embed-text » avant la zone d'import, désactivée avec sa raison ;
   - Modèles : encart du reranker, tableaux « Sur ce poste », « Catalogue installable » et « Modèles proposés par défaut » compacts (hauteur totale mesurée ≈ 1295 px à 1920 px de large, loin sous les 3900 px actuels) ;
   - icônes Material colorées par module (violet Arène, bleu Banc d'essai, vert Base documentaire, ambre Modèles), aplat léger de la primaire (8 % en clair, 10 % en sombre) sur les zones d'action, aucun emoji.
3. **Contrastes** : `DECISIONS.md` donne la table des contrastes calculés avec la même méthode que la story 8.2 (luminance relative WCAG, formule de `tests/v2/e2e/test_accessibilite.py`), clair et sombre, pour chaque couple nouveau (icônes par module, aplat d'action). Une limite connue est documentée (icône Modèles sur `chart-4` clair, 2,74:1 sur sa pastille, sous le seuil), avec un jeton dédié proposé pour la lever.
4. **Décisions à trancher** : `DECISIONS.md` liste les choix chiffrés (bascule de grille, largeurs de colonnes, échelle typographique, couleurs, jetons à ajouter), la table des contrastes, 6 questions fermées avec recommandation, et un brouillon (non appliqué) des amendements de `DESIGN.md` (§Brand 4, §Layout, §Typography) et `EXPERIENCE.md`.
5. **Validation en attente** : cette story reste `status: review` ; `DESIGN.md`, `EXPERIENCE.md`, `sprint-status.yaml` et `run-autonome.md` ne sont pas modifiés. Une fois Anaël d'accord, les amendements du §3 de `DECISIONS.md` sont reportés dans les deux documents avant la story 9.7 (hors périmètre de cette story).

## Règles écrites

- Aucun fichier de `src/wavelocalai/` n'est modifié : la maquette est un document autonome dans `docs/`.
- Aucune donnée réelle : tous les modèles, documents et résultats affichés sont fictifs ; les noms de modèles sont pris dans `config/models_catalog.json` (« Qwen 3.5 2B », « Gemma 4 12B »…) ou dans les identifiants cloud de `models/defaults.py` (« gpt-oss-120b »), les documents sont inventés (« note-cadrage.docx »).
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

Revue (Opus, une passe, base `ba606cb` à jour, aucun rebase nécessaire). Constats du second avis (Haiku) repris un par un, puis constats propres.

| # | Sévérité | Source | Constat | Décision |
|---|---|---|---|---|
| 1 | high | second avis | « Arrêté : le modèle se répétait » en texte `risk` sur blanc (3,70:1), contraire à `DESIGN.md` | Corrigé : texte en `ink` (gras), icône `block` seule en `risk` (3:1 graphique) |
| 2 | medium | second avis | Tableaux coupés à 390 px (colonne Actions masquée par le `overflow: hidden` du cadre) | Corrigé : tableaux enveloppés comme `wl-table-wrap`, et en lignes étiquetées (`data-label`) à 390 px ; grille en `minmax(0, 1fr)` |
| 3 | medium | second avis | Texte `primary` sur l'aplat sombre : 4,25:1 (pastilles choisies, bandeau du juge, nav courante) | Corrigé : pastilles choisies selon `wl-pill-selected` (aplat `primary-fill`, texte blanc, coche) ; bandeau et nav en texte `ink`, violet réservé aux icônes et au souligné |
| 4 | medium | second avis | Zone de dépôt désactivée par `opacity: 0.6` (3,08:1), interdit par `DESIGN.md` | Corrigé : pointillés, fond `surface-alt`, texte `ink-secondary` (7,96:1) |
| 5 | low | second avis | Icône d'alerte `chart-4` clair sur fond de l'encart : 2,62:1 | Corrigé : jeton `--color-amber-strong` (3,85:1) partagé avec l'icône Modèles |
| 6 | low | second avis | Table des contrastes mal libellée, aplat sombre calculé à 8 % au lieu de 10 % | Corrigé : table recalculée sur les couleurs rendues (aplats mélangés au fond) |
| 7 | low | second avis | « Arrêté : le modèle se répétait » absent d'i18n | Écarté : libellé apporté par la story 9.2, la maquette le propose |
| 8 | low | second avis | Libellés différents d'i18n | En partie écarté : « passent l'un après l'autre » est le libellé de `i18n/fr/arena.json` (« répondent » vient d'`evaluation.json`) ; « Notation en cours » aligné sur « Notation » (`components.json`), icône `gavel` au lieu d'une coche trompeuse |
| 9 | low | second avis | Cadre 1920 dans une fenêtre 1440 : défilement interne, mise à l'échelle décalée | Corrigé : `transform` posé sur le cadre, conteneur dimensionné à la taille réduite (ResizeObserver) ; mesuré sans débord à 1440 et 1920 |
| 10 | low | second avis | Noms de modèles absents du catalogue | Corrigé : Qwen 3.5 2B, Llama 3.2 3B, Granite 4.2 3B, Gemma 4 12B, qwen3.5:9b, phi4-mini:3.8b, qwen3.6:35b-a3b (tailles du catalogue), gpt-oss-120b (Groq) |
| 11 | low | second avis | « Zéro défilement horizontal » affirmé sans vérification aux 4 largeurs | Corrigé : vérification refaite sur 5 écrans × 4 largeurs × 2 thèmes × 2 fenêtres |
| 12 | medium | reviewer | Icônes de module mesurées sur `surface`, mais posées sur une pastille à 14 % : Documents à 2,92:1 en clair | Corrigé : pastille à 8 % (Documents 3,12:1, marge étroite signalée dans `DECISIONS.md`) |
| 13 | medium | reviewer | Critère d'acceptation « 1920, 1440, 1280 et 390 px » vérifié seulement à 1920 et 390 | Corrigé : les 4 largeurs vérifiées (voir n° 11) |
| 14 | low | reviewer | `<pre>` de la sortie JSON débordant sa carte | Corrigé : `white-space: pre-wrap` |

Vérification finale (Edge headless, captures hors dépôt) : 0 erreur console, 0 requête externe, aucun débord ; bouton principal à 1920 px visible dans une fenêtre 1920×1080 (bas à 550 px pour le Banc d'essai, 377 px pour l'Arène formulaire). Complexité : 0 constat (page statique, aucune structure qui grossit). Questions à Anaël : 3 et 5 précisées (jeton `amber-strong`, aplat 8 % / 10 %), aucune ajoutée.
