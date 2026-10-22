---
title: 'Story 9.9 : Modèles, Sobriété et Accueil suivent la nouvelle mise en page'
type: 'feature'
created: '2026-10-22'
status: 'review'
baseline_commit: '3380be0'
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/docs/maquette-v2-mise-en-page/DECISIONS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-9-7.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-9-8.md'
warnings: []
deferred: []
---

# Story 9.9 : Modèles, Sobriété et Accueil suivent la nouvelle mise en page

Critères : `epics.md`, story 9.9. Maquette : `docs/maquette-v2-mise-en-page/` (DECISIONS.md §4 à §6).
Contrat de jetons et de classes posé par la story 9.7 (`story-9-7.md`) et déjà complet (`tokens.css`,
`base.css`) : aucun nouveau jeton n'était attendu de cette story (DECISIONS.md §6), et aucun n'a été
ajouté.

La préversion `2.0.0a8` (version, tag, release) n'est pas faite par cette story : l'orchestrateur du
run s'en charge après la revue.

## Périmètre

| Écran | Fichier(s) | Traitement |
|---|---|---|
| Modèles | `screens/models.js`, `models-rerank.js`, `models-installed.js`, `models-catalog.js`, `models-defaults.js`, `models.css` | Icône de module (`.icon-mod.models`) devant le `h1` ; les 4 intertitres de section (« Reclassement des extraits », « Sur ce poste », « Catalogue installable », « Modèles proposés par défaut ») passent en `.section-label` ; réordonnés dans l'ordre de la maquette (le reranker d'abord, puis « Sur ce poste », le catalogue, les défauts en dernier) ; `.models-section` resserré (2rem → 1,5rem) |
| Sobriété | `screens/sobriety-health.js`, `sobriety-carbon.js`, `sobriety-history.js` | Les 3 intertitres de section (« Santé du système », « Empreinte carbone de cette session », « Historique ») passent en `.section-label` ; pas d'icône de module (voir ci-dessous) |
| Accueil | `screens/home.js`, `home-demo.js` | Les intertitres « Les modules » (`modules_title`), « État du poste » (`status_title`) et « Démo recommandée » passent en `.section-label` ; pas d'icône de module |

Aucune grille `.two-col` : ni Modèles (listes et cartes, pas un formulaire de configuration), ni
Sobriété, ni Accueil (cartes de métriques déjà en grille responsive, `home-cards`) n'ont l'équivalent
d'un écran de saisie gauche/droite que `.two-col` vise.

## Icône de module (Sobriété, Accueil)

La maquette validée (DECISIONS.md §6) ne couvre que Banc d'essai, Arène, Base documentaire et
Modèles ; `--color-icon-arena/bench/documents/models` sont les 4 seules couleurs posées, sans aucun
jeton prévu pour un 5ᵉ ou 6ᵉ module (contrairement à Agents en 9.8, pour qui l'Arène violette était un
choix de cohérence défendable : une tâche confiée à des modèles, comme une comparaison). Ni Sobriété
(mesure du matériel, pas un module de génération) ni Accueil (l'écran qui liste tous les modules, pas
un module en soi) ne se rapprochent sémantiquement d'une des 4 couleurs existantes sans forcer un
rapprochement arbitraire, et les contrastes des pastilles de DECISIONS.md §2 n'ont été calculés que
pour les 4 couples existants : en poser un 5ᵉ sans le même calcul (`contrast`, story 8.2) risquerait un
jeton non vérifié. Choix retenu : laisser leurs `h1` sans icône de module, comme avant cette story.
Documenté ici pour que la prochaine story qui toucherait ces écrans n'ait pas à redécouvrir ce choix.

## Modèles : atteindre le reranker et le catalogue sans défiler toute la hauteur

Mesuré dans Edge (Playwright), jeu de données de la maquette (3 modèles installés, 3 entrées de
catalogue, 5 usages, reranker non installé avec sa raison), haut de chaque intertitre en px depuis le
haut de la page :

| Repère (1920×1080) | Commit du dev (7abcf10) | Après la revue |
|---|---|---|
| Reclassement des extraits (reranker) | 537 | **255** |
| Catalogue installable (titre / fin du tableau) | 1 096 / 1 379 | **823 / 1 062** |
| Hauteur totale de l'écran | 1 894 | **1 729** (maquette : ≈ 1 295) |

À 1920×1080, le reranker, « Sur ce poste » et le catalogue entier tiennent dans le premier écran : le
critère est tenu. La différence restante avec la maquette vient de ce que la maquette n'a ni
« Installer un modèle par son nom », ni « Décharger », ni la raison du reranker : ces fonctions sont
gardées. Les 4 135 px que citait la première version de cette fiche (et le second avis) avaient été
mesurés sur un autre jeu de données (recette E2E, lignes plus nombreuses) : ils ne se comparaient pas
aux ≈ 1 295 px de la maquette, d'où la contradiction entre « critère tenu » et une hauteur totale
inchangée. Ce que la revue a changé :

- le bloc d'actions qui précédait le reranker (≈ 280 px) est rangé : « Décharger les modèles
  inactifs » dans « Sur ce poste », au-dessus du tableau (il agit sur la colonne « Chargé ») ;
  « Installer un modèle par son nom » et la mémoire libre après le catalogue (le cas d'un modèle
  absent du catalogue). Sélecteurs E2E inchangés ;
- la zone d'annonce `.models-notice` ne réserve plus de hauteur quand elle est vide (elle reste dans
  le document pour les annonces) ;
- densité de la maquette (0,45 × 0,6 rem) pour les tableaux de cet écran seulement, alignement en haut
  gardé (un alignement centré faisait bouger les boutons d'une ligne quand la liste du sélecteur se
  refermait : clics manqués dans `test_models_manage.py`) ; nom et tag sur une même ligne ;
- sous 600 px, les tableaux de l'écran passent en lignes étiquetées comme la maquette à 390 px
  (`wl-data-table` pose `data-label` sur chaque cellule de données ; la CSS n'est appliquée qu'à
  `.models-section`).

À 390 px, la page est plus haute (3 744 px contre 3 415) : les lignes étiquetées remplacent un tableau
qui défilait dans sa zone, ce qui est le choix de la maquette.

## Défaut corrigé : débordement horizontal à 320 px sur /modeles

`test_no_horizontal_scroll_on_any_route[*-320 px]` et `test_text_spacing_overrides_clip_no_text…[320]`
échouaient déjà sur `master` (signalé « hors story » par les revues 9.7 et 9.8). Cause trouvée par
bissection (`display:none` successif des enfants jusqu'à ce que `document.documentElement.scrollWidth`
retombe à `clientWidth`) : la raison du reranker (`models-rerank.js`, `.models-reason`), lue depuis le
serveur (`GET /api/rag/settings`), peut contenir un chemin de cache fastembed sans espace
(`C:\...\models\fastembed` en recette, un chemin de cache réel en production) — un seul mot, donc
incoupable par le retour à la ligne normal (`overflow-wrap: normal`), qui déborde de son conteneur à
320 px. Corrigé : `.models-reason { overflow-wrap: anywhere; }` (`models.css`), qui s'applique aussi au
catalogue et à la barre d'installation (même classe), pour toute raison variable venant du serveur.
Les deux tests passent désormais de façon stable (relancés plusieurs fois pendant le diagnostic).

## Réalignement d'E2E (texte visuel vs DOM)

`.section-label` met le texte en majuscules par CSS (`text-transform`) : comme en 9.7, les tests qui
lisaient ces intertitres avec `inner_text()` (le texte rendu) ont été réalignés sur `text_content()`
ou `all_text_contents()` (le texte du DOM, inchangé) :

- `test_models_install.py::test_the_screen_lists_what_is_installed_and_what_can_be_installed` : ordre
  des 4 `h2` mis à jour (reranker, installés, catalogue, défauts) et `text_content()`.
- `test_sobriety.py::test_the_screen_has_one_title_and_the_sections_in_order` et
  `test_sobriety_history.py::test_without_any_session_the_history_says_so_and_draws_no_empty_chart` :
  `all_text_contents()`.
- `test_home_demo.py::test_the_card_names_the_arena_and_lists_the_ready_models_with_their_badge` :
  `text_content()` sur le titre « Démo recommandée ».

Aucun autre test ne lisait ces intertitres (vérifié par recherche des chaînes « État du poste »,
« Modules », « Démo recommandée », etc. sur `tests/v2/e2e`).

## Tests

Unitaires et web ciblés (`tests/v2/unit tests/v2/web -k "static or i18n or layers or tokens or models
or sobriety or home"`) : 437 passés. `test_tokens_css_mirrors_design_md` vert (aucun jeton ajouté).

E2E (Edge, un fichier à la fois) :

| Fichier | Résultat |
|---|---|
| `test_models_install.py` | 19 (1 échec transitoire à la première passe — `cells[5]` « Chargé » à `inconnu` au lieu de `Non`, une course avec le flux système — vert en isolation et vert sur `master` non modifié : flaky préexistant, pas une régression) |
| `test_models_manage.py` | 42 au total avec `test_models_reranker.py`/`test_models_card.py` (2 échecs reproduits à l'identique sur `master` non modifié : `agentmodel:7b`/`docmodel:4b` absents des lignes de défauts — flaky préexistant d'éligibilité, pas une régression) |
| `test_models_reranker.py` | 7 passés |
| `test_models_card.py` | 19 passés |
| `test_home.py`, `test_home_demo.py` | 45 passés |
| `test_sobriety.py`, `test_sobriety_history.py`, `test_parcours_sobriete_modeles.py` | 57 passés |
| `test_accessibilite.py` (ciblé : contrastes, pastilles, focus du `h1`, icônes) | 7 passés |
| `test_accessibilite.py::test_no_horizontal_scroll_on_any_route`, `test_text_spacing_overrides_clip_no_text_and_cause_no_horizontal_scroll`, `test_projection_scales_the_smallest_text_of_every_route_by_the_ramp` | 9 passés (320 px, zoom 200 %, texte 200 %, clair et sombre/projection) — le défaut connu de `/modeles` à 320 px (ci-dessus) est corrigé et stable |

Aucune régression des critères de la story 8.2 (contrastes calculés, `h1` focalisé, contenu coupé,
projection).

## Report

Rien : le périmètre de la story est couvert en entier (Modèles, Sobriété, Accueil). La préversion
`2.0.0a8` (version, tag, release GitHub) reste à l'orchestrateur, comme demandé.

## Revue

Base à jour (origin/master = 3380be0, aucun rebase nécessaire).

| Sévérité | Source | Constat | Suite | Motif |
|---|---|---|---|---|
| high | second avis 1 | Écran Modèles trop haut, reranker et catalogue loin du haut | Corrigé | Bloc d'actions rangé, densité, zone d'annonce vide sans hauteur : reranker à 255 px, catalogue entier avant 1 080 px (tableau ci-dessus) |
| medium | second avis 3 | Formulaire « installer par nom » au-dessus du reranker | Corrigé | Après le catalogue ; « Décharger » dans « Sur ce poste » ; sélecteurs E2E inchangés |
| medium | second avis 4 | Tableaux plus denses que la maquette ; pas de lignes étiquetées à 390 px | Corrigé en partie | Lignes étiquetées sous 600 px, nom et tag sur une ligne, densité ; colonnes gardées : Paramètres, Débit, Origine et Usage portent les décisions D-42/D-43 et les tests des stories 5.3/5.4 (repli sous 1 024 px), et tiennent sur une ligne à 1 440 px |
| medium | second avis 5 | Critère du catalogue non tenu | Corrigé | Même correctif que le 1 |
| medium | revue | Contradiction de la fiche : « critère tenu » avec une hauteur totale quasi inchangée, mesures sur un autre jeu de données que la maquette | Corrigé | Section de mesure réécrite, chiffres comparables à la maquette |
| low | second avis 6 | Cellules plus hautes que la maquette | Corrigé | Classe de densité limitée à `.models-section` |
| low | second avis 7 | Pas d'icône de module sur Sobriété et Accueil | Rejeté | Absents de la maquette, aucun jeton de contraste testé pour eux ; choix du dev documenté ci-dessus |
| low | second avis 8 | `.models-legend` sans `overflow-wrap` | Rejeté | Légendes à texte fixe (i18n, mots courts), aucun chemin de texte serveur ; 320 px vert |
| — | revue | Échecs E2E préexistants sur master, reproduits à l'identique : `test_models_install::test_the_screen_lists…` (« Chargé » à « inconnu »), `test_models_manage` (défauts agent/documents, focus de « Supprimer ») ; latences < 300 ms de `tests/v2/web` (poste chargé) | Hors story | Reproduits sur master 3380be0 ; `test_the_new_actions_stay_in_reach_at_320_px`, rouge sur master, passe sur la branche |
| — | revue | Complexité : 0 constat | — | Aucune structure qui grossit pendant l'exécution n'est touchée |

À vérifier en recette : écran Modèles à 1920×1080 avec les vrais modèles du poste (catalogue visible
sans défiler) ; lignes étiquetées à 390 px (lecteur d'écran : étiquettes lues, en-têtes de colonne
masqués sur ce gabarit) ; « Décharger » et « Installer par nom » à leur nouvelle place.
