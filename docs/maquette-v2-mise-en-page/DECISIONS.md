# Maquette de la nouvelle mise en page — décisions proposées (story 9.6)

Statut : **en attente de validation par Anaël**. Rien ici n'est appliqué à `DESIGN.md`, `EXPERIENCE.md` ni au code : ce sont des propositions, à trancher avant la story 9.7. Maquette : `docs/maquette-v2-mise-en-page/index.html` (fichier unique, à ouvrir directement dans un navigateur).

## 1. Choix proposés, chiffrés

| Sujet | Valeur proposée | Pourquoi |
|---|---|---|
| Point de bascule de la grille à deux colonnes | **1400 px** (`min-width` du cadre) | Milieu de la fourchette « environ 1 400 px » de la story ; en dessous (1280 px et 390 px), tout reste en une colonne verticale, comme demandé. |
| Largeur de la colonne gauche (saisie, modèle) | `minmax(480px, 1fr)` | Flexible, absorbe la largeur excédentaire en 1920 px sans texte trop long par ligne. |
| Largeur de la colonne droite (réglages, aperçu/résultats) | `minmax(320px, 400px)` | Assez large pour les cartes de critères et les métriques, sans dominer l'écran ; comparable à `wl-side-panel` (360 px mini) déjà utilisé ailleurs. |
| Échelle typographique | Intertitre `0.8125rem` (13 px, majuscules, espacé) ; libellé de champ principal `1.0625rem` (17 px, gras) ; titre d'écran inchangé `1.75rem` | Ratio ~1,3 entre intertitre et champ : l'intertitre reste identifiable mais ne rivalise plus avec « Entrée » ou « Modèle ». |
| Couleur d'icône par module | Arène `chart-1` (violet) · Banc d'essai `chart-3` (bleu) · Base documentaire `chart-2` (vert) · Modèles **nouveau jeton dédié** `#A66E00` en clair / `chart-4` en sombre | Réutilise les jetons `chart-*` déjà validés par `DESIGN.md`, sauf en clair pour Modèles : `chart-4` clair (`#C98A00`) ne tient que 2,95:1, sous le seuil nécessaire ; `#A66E00` tient 4,33:1 sans changer la teinte perçue. |
| Aplat des zones d'action | `rgba(primaire, 8%)` sur `surface` | Reste ≥ 15:1 de contraste avec le texte d'encre posé dessus (l'aplat ne porte jamais de texte blanc, seulement un entourage) ; visible sans dominer. |
| Jetons à ajouter à `tokens.css` | `--color-icon-arena`, `--color-icon-bench`, `--color-icon-documents`, `--color-icon-models` (+ une valeur claire dédiée), `--color-action-tint`, `--text-section-label`, `--text-field-label` | Voir le brouillon d'amendement §3. |

## 2. Table des contrastes (méthode de la story 8.2 : luminance relative WCAG, `tests/v2/e2e/test_accessibilite.py::contrast`)

| Couple | Clair | Sombre | Seuil | Résultat |
|---|---|---|---|---|
| `ink` / `surface` | 19,69:1 | 18,15:1 | 4,5:1 (texte) | OK |
| `ink-secondary` / `surface` | 8,63:1 | 9,64:1 | 4,5:1 | OK |
| `primary` / `surface` | 9,32:1 | 4,62:1 | 4,5:1 (texte) | OK |
| `primary-fill` / `surface` (texte blanc dessus) | 9,32:1 | 3,58:1* | — | *déjà documenté comme écart connu dans DESIGN.md (note `primary-fill`), inchangé par cette story |
| **icône Arène** `chart-1` / `surface` | 5,50:1 | 4,36:1 | 3:1 (graphique) | OK |
| **icône Banc d'essai** `chart-3` / `surface` | 4,08:1 | 5,27:1 | 3:1 | OK |
| **icône Documents** `chart-2` / `surface` | 3,42:1 | 6,18:1 | 3:1 | OK |
| **icône Modèles** `chart-4` / `surface` (non modifié) | **2,95:1** | 5,19:1 | 3:1 | **Sous le seuil en clair** (déjà noté comme limite connue dans DESIGN.md pour l'usage graphique de `chart-4`) |
| **icône Modèles** `#A66E00` / `surface` (nouveau, clair) | 4,33:1 | — | 3:1 | OK (remplace `chart-4` en clair pour cet usage) |
| Aplat `primary` 8 % / `ink` dessus | 17,08:1 | 17,06:1 | 4,5:1 | OK (texte posé sur l'aplat reste l'encre normale) |
| `risk` / `surface` (statut « Arrêté ») | 3,70:1 | 5,33:1 | 3:1 (icône) / texte toujours avec un mot | OK, comme déjà documenté |

Détail du calcul : `tests/v2/e2e/test_accessibilite.py` (fonctions `_luminance`/`contrast`, lignes 827-858) ; valeurs recalculées pour cette story avec les mêmes formules (sRGB linéarisé, ratio `(L1+0.05)/(L2+0.05)`).

**Limite connue à trancher (question 3 ci-dessous) :** l'icône du module Modèles ne peut pas rester sur `chart-4` clair sans descendre sous 3:1. Deux options : un jeton d'icône dédié (`#A66E00`, retenu dans la maquette) ou assumer la limite comme `DESIGN.md` le fait déjà pour les points de `chart-4` dans les graphiques (toujours accompagnés d'un libellé).

## 3. Brouillon des amendements (non appliqués)

### `DESIGN.md` — §Brand, point 4
> Remplacer : « Icônes Material, pas d'emojis. Icônes `:material/…:` monochromes, qui héritent de la couleur du texte, sans exception. »
> Par : « Icônes Material Symbols Rounded, **colorées par module** selon la palette (violet pour l'Arène, bleu pour le Banc d'essai, vert pour la Base documentaire, ambre pour Modèles — jetons `--color-icon-*`) ; jamais d'emoji. Les icônes d'état (succès, erreur, arrêt) restent les couleurs sémantiques existantes (`risk`, `accent-green`). »

### `DESIGN.md` — §Layout & Spacing
> Ajouter, après la règle « Module » : « Dès **1 400 px** environ, l'écran de configuration (saisie, choix du modèle) passe en grille à deux colonnes : colonne principale flexible (480 px au moins) à gauche, colonne secondaire (320 à 400 px) à droite pour les réglages repliés, l'aperçu et les résultats. En deçà de 1 400 px, une seule colonne, dans le même ordre (saisie puis réglages). Pendant l'exécution, la configuration se replie en résumé (inchangé, EXPERIENCE.md) ; les résultats (lanes de l'Arène, tableau) occupent alors la largeur pleine, hors de cette grille à deux colonnes (question 5). »

### `DESIGN.md` — §Typography
> Ajouter une ligne au tableau : « `{typography.field-label}` | — | Libellé d'un champ mis en avant (prompt, choix du modèle) : au moins aussi grand que `{typography.body}`, toujours plus grand que l'intertitre de sa section (`{typography.section-label}`, 13 px, majuscules). »

### `EXPERIENCE.md` — Arène (`#/arene/comparer[/<run_id>]`)
> Ajouter : « Une colonne arrêtée automatiquement affiche "Arrêté : le modèle se répétait" (icône `block`, couleur `risk`), sa réponse partielle reste affichée et notée. Le bandeau du juge, au-dessus des colonnes, affiche "Juge : <modèle> · Notation N sur M" pendant la notation. »

### `EXPERIENCE.md` — Base documentaire (`#/documents/base`)
> Ajouter : « Sans modèle de représentation installé, un encart d'alerte (icône `warning`, couleur `chart-4`) précède tout le reste de l'écran : il annonce l'absence du modèle, propose "Installer nomic-embed-text" avec sa taille, et la zone de dépôt reste visible mais désactivée avec la raison en légende. »

## 4. Questions à trancher par Anaël

1. **Point de bascule de la grille.** 1 400 px pile, ou une valeur ronde côté implémentation comme 1 408 px (88 × 16, aligné sur une grille de 8) ? *Recommandation : 1 400 px, lisible dans la story et déjà la valeur citée partout.*
2. **Largeur de la colonne droite.** Fixe entre 320 et 400 px (retenu), ou proportionnelle (1/3 de la largeur disponible, comme `wl-side-panel`) ? *Recommandation : fixe, plus stable visuellement entre 1 440 et 1 920 px, où un tiers deviendrait trop large.*
3. **Icône du module Modèles.** Nouveau jeton dédié `#A66E00` pour tenir 3:1 en clair (retenu dans la maquette), ou garder `chart-4` tel quel et assumer la même limite documentée que pour les graphiques (2,95:1, en s'appuyant sur le libellé texte systématiquement présent) ? *Recommandation : le nouveau jeton, un seul hex à ajouter, coût nul.*
4. **Grille sur l'écran de résultats de l'Arène.** Cette maquette ne met pas le bandeau du juge ni les colonnes de réponse dans la grille à deux colonnes (elles occupent la pleine largeur) : seule la phase de configuration (avant de lancer) suit le schéma gauche/droite. Confirmer cette lecture de l'AC, qui ne tranche pas explicitement le cas des résultats ? *Recommandation : oui, les résultats ont leur propre grille de lanes (D-15 existant, 4 colonnes dès 1 440 px avec 4 modèles) : imposer aussi 2 colonnes gauche/droite par-dessus réduirait la largeur utile.*
5. **Aplat des zones d'action.** 8 % de violet sur le fond (retenu), ou 6 % (plus discret) / 12 % (plus visible) ? *Recommandation : 8 %, lisible sans dominer sur les captures de la maquette, clair et sombre.*
6. **Échelle typographique.** Intertitre 13 px / libellé de champ 17 px (retenu, ratio ~1,3), ou un écart plus marqué (12 px / 18 px) pour une hiérarchie plus nette sur grand écran ? *Recommandation : 13/17, déjà net sur les captures et cohérent avec `--text-caption` existant (14 px).*

## 5. Captures de vérification

Prises par Playwright (Edge headless), stockées hors dépôt (scratchpad de la session) : 1920 et 390 px, clair et sombre, pour les cinq écrans. Aucune erreur console, aucun défilement horizontal, hauteur totale de l'écran Modèles en 1920 px : environ 1 315 px (loin sous la limite de 3 900 px de l'ancienne version).
