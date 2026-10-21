# Maquette de la nouvelle mise en page — décisions proposées (story 9.6)

Statut : **en attente de validation par Anaël**. Rien ici n'est appliqué à `DESIGN.md`, `EXPERIENCE.md` ni au code : ce sont des propositions, à trancher avant la story 9.7. Maquette : `docs/maquette-v2-mise-en-page/index.html` (fichier unique, à ouvrir directement dans un navigateur).

## 1. Choix proposés, chiffrés

| Sujet | Valeur proposée | Pourquoi |
|---|---|---|
| Point de bascule de la grille à deux colonnes | **1400 px** (`min-width` du cadre) | Milieu de la fourchette « environ 1 400 px » de la story ; en dessous (1280 px et 390 px), tout reste en une colonne verticale, comme demandé. |
| Largeur de la colonne gauche (saisie, modèle) | `minmax(480px, 1fr)` | Flexible, absorbe la largeur excédentaire en 1920 px sans texte trop long par ligne. |
| Largeur de la colonne droite (réglages, aperçu/résultats) | `minmax(320px, 400px)` | Assez large pour les cartes de critères et les métriques, sans dominer l'écran ; comparable à `wl-side-panel` (360 px mini) déjà utilisé ailleurs. |
| Échelle typographique | Intertitre `0.8125rem` (13 px, majuscules, espacé) ; libellé de champ principal `1.0625rem` (17 px, gras) ; titre d'écran inchangé `1.75rem` | Ratio ~1,3 entre intertitre et champ : l'intertitre reste identifiable mais ne rivalise plus avec « Entrée » ou « Modèle ». |
| Couleur d'icône par module | Arène `chart-1` (violet) · Banc d'essai `chart-3` (bleu) · Base documentaire `chart-2` (vert) · Modèles **nouveau jeton** `--color-amber-strong` (`#A66E00` en clair, `chart-4` en sombre) ; l'icône est posée sur une pastille de sa propre couleur à 8 % | Réutilise les jetons `chart-*` déjà validés par `DESIGN.md`, sauf en clair pour Modèles : `chart-4` clair (`#C98A00`) ne tient que 2,74:1 sur sa pastille, sous 3:1 ; `#A66E00` tient 3,92:1 sans changer la teinte perçue. Le même ambre foncé sert à l'icône et au liseré de l'encart d'alerte (Base documentaire). |
| Aplat des zones d'action | `primary` à **8 % en clair**, `primary-dark` à **10 % en sombre** (même dosage que la pastille choisie de la v1, note `primary-dark` de `DESIGN.md`) | Le texte posé dessus reste l'encre (`ink`, ≥ 16:1) ; le violet n'y sert qu'aux icônes, entourages et soulignés (≥ 4,2:1). Les pastilles choisies suivent `wl-pill-selected` (aplat `primary-fill`, texte blanc), pas cet aplat. |
| Jetons à ajouter à `tokens.css` | `--color-icon-arena`, `--color-icon-bench`, `--color-icon-documents`, `--color-icon-models`, `--color-amber-strong`, `--color-action-tint`, `--text-section-label`, `--text-field-label` | Voir le brouillon d'amendement §3. |

## 2. Table des contrastes (méthode de la story 8.2 : luminance relative WCAG, `tests/v2/e2e/test_accessibilite.py::contrast`)

Valeurs recalculées sur les couleurs effectivement rendues par le CSS de la maquette (aplats mélangés au fond avant calcul). Seuils : 4,5:1 pour le texte, 3:1 pour une icône ou un composant.

| Couple (élément de la maquette) | Clair | Sombre | Seuil | Résultat |
|---|---|---|---|---|
| `ink` / `surface` | 19,69:1 | 18,15:1 | 4,5:1 | OK |
| `ink-secondary` / `surface` | 8,63:1 | 9,64:1 | 4,5:1 | OK |
| `primary` / `surface` (marque, liens) | 9,32:1 | 4,62:1 | 4,5:1 | OK |
| blanc / `primary-fill` (bouton principal, pastille choisie) | 9,32:1 | 5,50:1 | 4,5:1 | OK |
| `primary-fill` / `surface` (bord du bouton plein) | 9,32:1 | 3,58:1 | 3:1 | OK, inchangé (note `primary-fill` de `DESIGN.md`) |
| `ink` / aplat d'action (nav courante, bandeau du juge, carte choisie) | 17,08:1 | 16,70:1 | 4,5:1 | OK |
| `primary` / aplat d'action (icône du juge, coche, souligné de nav) | 8,08:1 | 4,25:1 | 3:1 | OK (jamais en texte sur l'aplat) |
| **icône Arène** `chart-1` / sa pastille 8 % | 4,93:1 | 4,10:1 | 3:1 | OK |
| **icône Banc d'essai** `chart-3` / sa pastille 8 % | 3,71:1 | 4,91:1 | 3:1 | OK |
| **icône Documents** `chart-2` / sa pastille 8 % | 3,12:1 | 5,76:1 | 3:1 | OK, marge étroite en clair (2,92:1 avec une pastille à 14 %, d'où les 8 %) |
| **icône Modèles** `chart-4` / sa pastille 8 % (non retenu) | **2,74:1** | 4,86:1 | 3:1 | **Sous le seuil en clair** |
| **icône Modèles** `amber-strong` / sa pastille 8 % (retenu) | 3,92:1 | 4,86:1 | 3:1 | OK |
| icône d'alerte `amber-strong` / fond de l'encart (`chart-4` à 12 %) | 3,85:1 | 4,66:1 | 3:1 | OK (`chart-4` clair y donnait 2,62:1) |
| `ink` / fond de l'encart d'alerte | 17,52:1 | 16,32:1 | 4,5:1 | OK |
| icône « Arrêté » `risk` / `surface` | 3,70:1 | 5,33:1 | 3:1 | OK ; le texte « Arrêté : … » est en `ink` (`risk` jamais en texte sur blanc, `DESIGN.md`) |
| `ink-secondary` / `surface-alt` (zone de dépôt désactivée) | 7,96:1 | 8,70:1 | 4,5:1 | OK ; désactivation par bordure en pointillés et fond `surface-alt`, jamais par l'opacité (`DESIGN.md`, `wl-button-primary`) |

Détail du calcul : `tests/v2/e2e/test_accessibilite.py` (fonctions `_luminance`/`contrast`, lignes 827-858) ; valeurs recalculées pour cette story avec les mêmes formules (sRGB linéarisé, ratio `(L1+0.05)/(L2+0.05)`).

**Limite connue à trancher (question 3 ci-dessous) :** l'icône du module Modèles ne peut pas rester sur `chart-4` clair sans descendre sous 3:1. Deux options : un jeton dédié (`--color-amber-strong`, `#A66E00`, retenu dans la maquette) ou assumer la limite comme `DESIGN.md` le fait déjà pour les points de `chart-4` dans les graphiques (toujours accompagnés d'un libellé).

## 3. Brouillon des amendements (non appliqués)

### `DESIGN.md` — §Brand, point 4
> Remplacer : « Icônes Material, pas d'emojis. Icônes `:material/…:` monochromes, qui héritent de la couleur du texte, sans exception. »
> Par : « Icônes Material Symbols Rounded, **colorées par module** selon la palette (violet pour l'Arène, bleu pour le Banc d'essai, vert pour la Base documentaire, ambre pour Modèles — jetons `--color-icon-*`) ; jamais d'emoji. Les icônes d'état (succès, erreur, arrêt) restent les couleurs sémantiques existantes (`risk`, `accent-green`). »

### `DESIGN.md` — §Layout & Spacing
> Ajouter, après la règle « Module » : « Dès **1 400 px** environ, l'écran de configuration (saisie, choix du modèle) passe en grille à deux colonnes : colonne principale flexible (480 px au moins) à gauche, colonne secondaire (320 à 400 px) à droite pour les réglages repliés, l'aperçu et les résultats. En deçà de 1 400 px, une seule colonne, dans le même ordre (saisie puis réglages). Pendant l'exécution, la configuration se replie en résumé (inchangé, EXPERIENCE.md) ; les résultats (lanes de l'Arène, tableau) occupent alors la largeur pleine, hors de cette grille à deux colonnes (question 5). »

### `DESIGN.md` — §Typography
> Ajouter une ligne au tableau : « `{typography.field-label}` | — | Libellé d'un champ mis en avant (prompt, choix du modèle) : au moins aussi grand que `{typography.body}`, toujours plus grand que l'intertitre de sa section (`{typography.section-label}`, 13 px, majuscules). »

### `EXPERIENCE.md` — Arène (`#/arene/comparer[/<run_id>]`)
> Ajouter : « Une colonne arrêtée automatiquement affiche "Arrêté : le modèle se répétait" (icône `block` en `risk`, texte en `ink`), sa réponse partielle reste affichée et notée. Le bandeau du juge, au-dessus des colonnes, affiche "Juge : <modèle> · Notation N sur M" pendant la notation. »

### `EXPERIENCE.md` — Base documentaire (`#/documents/base`)
> Ajouter : « Sans modèle de représentation installé, un encart d'alerte (icône `warning` et liseré `amber-strong`) précède tout le reste de l'écran : il annonce l'absence du modèle, propose "Installer nomic-embed-text" avec sa taille, et la zone de dépôt reste visible mais désactivée avec la raison en légende. »

## 4. Décisions d'Anaël (2026-10-21) : recommandations retenues

Anaël a validé la maquette le 2026-10-21 (« elle est mieux que l'existant, partons dessus ») et retient les six recommandations ci-dessous telles quelles, aux valeurs issues de la revue (§1-§2, déjà à jour sur les corrections de la revue). Le brouillon d'amendements du §3 est appliqué à `DESIGN.md` et `EXPERIENCE.md` dans ce même commit, avant la story 9.7.

1. **Point de bascule de la grille.** 1 400 px pile, ou une valeur ronde côté implémentation comme 1 408 px (88 × 16, aligné sur une grille de 8) ? *Recommandation : 1 400 px, lisible dans la story et déjà la valeur citée partout.*
2. **Largeur de la colonne droite.** Fixe entre 320 et 400 px (retenu), ou proportionnelle (1/3 de la largeur disponible, comme `wl-side-panel`) ? *Recommandation : fixe, plus stable visuellement entre 1 440 et 1 920 px, où un tiers deviendrait trop large.*
3. **Icône du module Modèles.** Nouveau jeton `--color-amber-strong` (`#A66E00`) pour tenir 3:1 en clair (retenu dans la maquette, il sert aussi à l'icône d'alerte), ou garder `chart-4` tel quel et assumer la même limite documentée que pour les graphiques (2,74:1 sur la pastille, en s'appuyant sur le libellé texte systématiquement présent) ? *Recommandation : le nouveau jeton, un seul hex à ajouter, coût nul.*
4. **Grille sur l'écran de résultats de l'Arène.** Cette maquette ne met pas le bandeau du juge ni les colonnes de réponse dans la grille à deux colonnes (elles occupent la pleine largeur) : seule la phase de configuration (avant de lancer) suit le schéma gauche/droite. Confirmer cette lecture de l'AC, qui ne tranche pas explicitement le cas des résultats ? *Recommandation : oui, les résultats ont leur propre grille de lanes (D-15 existant, 4 colonnes dès 1 440 px avec 4 modèles) : imposer aussi 2 colonnes gauche/droite par-dessus réduirait la largeur utile.*
5. **Aplat des zones d'action.** 8 % de violet en clair et 10 % en sombre (retenu), ou 6 % (plus discret) / 12 % (plus visible) ? *Recommandation : 8 % / 10 %, lisible sans dominer sur les captures de la maquette ; l'aplat ne porte que du texte d'encre.*
6. **Échelle typographique.** Intertitre 13 px / libellé de champ 17 px (retenu, ratio ~1,3), ou un écart plus marqué (12 px / 18 px) pour une hiérarchie plus nette sur grand écran ? *Recommandation : 13/17, déjà net sur les captures et cohérent avec `--text-caption` existant (14 px).*

## 5. Captures de vérification

Prises par Playwright (Edge headless), stockées hors dépôt (scratchpad de la session) : fenêtres de 1920 et 1440 px, les 4 largeurs simulées (1920, 1440, 1280, 390), clair et sombre, les cinq écrans. Aucune erreur console, aucune requête hors du fichier, aucun débord horizontal dans le cadre ni dans la page (le cadre mis à l'échelle prend sa taille réduite, sans défilement interne) ; en 390 px, les tableaux passent en lignes étiquetées. Bouton principal à 1920 px dans une fenêtre 1920×1080 : bas à 550 px (Banc d'essai) et 377 px (Arène formulaire). Hauteur de l'écran Modèles à 1920 px : environ 1 295 px (3 900 px dans la version actuelle).

## 6. Pour les stories 9.7 à 9.9

`DESIGN.md` et `EXPERIENCE.md` décrivent désormais la mise en page validée, mais aucun jeton ni aucune classe n'a été posé dans le code (`tests/v2` reste vert : le test de dérive `test_tokens_css_mirrors_design_md` n'accepte dans le front matter de `DESIGN.md` que les jetons déjà dans `tokens.css`). Ce qui reste à poser, par fichier :

| Fichier | À créer / changer |
|---|---|
| `tokens.css` | `--color-icon-arena` (= `--color-chart-1`), `--color-icon-bench` (= `--color-chart-3`), `--color-icon-documents` (= `--color-chart-2`), `--color-amber-strong` (`#A66E00` clair, `--color-chart-4` sombre), `--color-icon-models` (= `--color-amber-strong`), `--color-action-tint` (`rgba(69, 29, 199, 0.08)` clair, `rgba(126, 101, 233, 0.10)` sombre), `--text-section-label` (`0.8125rem`), `--text-field-label` (`1.0625rem`) — puis ajouter les 8 clés correspondantes au front matter `colors:`/`typography:` de `DESIGN.md` dans la même PR (le test de dérive exige les deux à la fois). |
| `base.css` | Classes génériques réutilisables entre écrans : `.icon-mod` (+ variantes `.arena`/`.bench`/`.docs`/`.models`, pastille `color-mix(... 8%, surface)`), `.section-label` / `.field-label`, grille à deux colonnes de configuration (`min-width: 1400px`, colonne gauche `minmax(480px, 1fr)`, colonne droite `minmax(320px, 400px)`), `.judge-banner`, `.alert-warning` (liseré `amber-strong`), zone désactivée (bordure pointillés + `surface-alt`, jamais `opacity`). |
| `screens.css` | Par écran : grille deux-colonnes posée sur le conteneur de configuration ; bandeau du juge et statut « Arrêté » (Arène résultats) ; encart d'alerte modèle de représentation manquant + zone de dépôt désactivée (Base documentaire). |

Écran → story qui le livre (Epic 9, stories restantes) :

| Story | Écrans |
|---|---|
| 9.7 | Chat libre, Arène (formulaire et résultats), Banc d'essai, Références |
| 9.8 | Discussion, Base documentaire, Évaluation, Agent seul, Équipe |
| 9.9 | Modèles, Sobriété, Accueil |

Chaque story ne pose que les jetons et classes que ses écrans utilisent ; `--color-icon-arena`/`--color-icon-bench` et la grille deux-colonnes sont donc posés par 9.7, `--color-amber-strong`/`--color-icon-documents` par 9.8, et aucun jeton nouveau n'est attendu de 9.9 (Modèles réutilise `amber-strong` déjà posé par 9.8).
