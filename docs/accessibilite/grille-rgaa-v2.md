# Grille RGAA 4.1 de la v2

Story 8.2 (NFR8, UX-DR2, UX-DR19, UX-DR25, AD-20). Périmètre : tous les écrans du registre (`static/core/routes/*.js`), servis par `wavelocalai-v2`. Les 106 critères du RGAA 4.1 sont listés, treize thématiques, chacun avec un statut.

Statuts :

- **Conforme** : vérifié par un test automatique (preuve citée) ou par relecture du code (dit).
- **Non conforme, corrigé** : écart trouvé et corrigé dans la story 8.2.
- **Non conforme, reporté** : écart connu, non corrigé ici ; sa raison et sa suite sont dans « Écarts et reports ».
- **Non applicable** : le critère ne porte sur rien de ce que la v2 sert.
- **À vérifier par Anaël (recette manuelle)** : seul un audit humain (clavier seul, NVDA, vidéoprojecteur réel) peut trancher ; listé en tête.

## À vérifier par Anaël (recette manuelle)

Aucun agent ne simule ces points. Cocher au fur et à mesure ; un écart relevé devient une ligne de « Écarts et reports ».

| N° | Recette | Critères | Comment |
|---|---|---|---|
| R1 | **Clavier seul**, sans souris, sur chaque écran du menu | 7.3, 7.4, 12.8, 12.9, 12.11 | Tab et Maj+Tab de bout en bout : l'ordre suit la lecture, aucun arrêt sans indicateur, aucun piège (dialogues : Échap ; panneaux de la barre haute : Échap rend le focus au bouton ; liste des modèles : flèches, Entrée, Échap ; menu Exporter : flèches, Échap ; onglets de l'Arène). Le test automatique prouve les indicateurs de focus et l'absence de `tabindex` positif, pas la cohérence de l'ordre. |
| R2 | **NVDA** (Firefox puis Edge), sur l'Accueil, le Chat, l'Arène terminée, la Base documentaire, l'Agent seul, Sobriété, Modèles | 1.3, 1.7, 5.5, 6.1, 7.1, 7.5, 9.1, 11.2, 11.9, 11.10 | Naviguer par titres (H), repères (D), liens (K), tableaux (T) ; écouter l'annonce de changement d'écran, de fin de réponse, d'erreur, de progression d'une installation ; vérifier que les graphiques sont compris à la lecture de leur description et de « Voir le tableau » ; que les intitulés de liens et de boutons se comprennent hors contexte ; que les étiquettes de champs sont justes. |
| R3 | **Couleurs seules** | 3.1, 3.3 | Afficher la matrice qualité/CO₂ et le classement de l'Arène en niveaux de gris (filtres de couleur de Windows) : chaque point, badge et état se lit sans la couleur. Regarder les points orange (`chart-4`, 2,95:1 sur blanc) : leur contour d'encre doit les rendre nets. |
| R4 | **Validation du code** | 8.2 | Passer `index.html` et le DOM d'un écran rendu au validateur W3C (Nu), hors réseau pour les agents. |
| R5 | **Limite de temps** | 13.1 | Agent seul : lancer une demande qui exige la validation d'un email et mesurer si le délai affiché dans le dialogue (« Sans réponse dans … ») laisse le temps de lire et de décider avec un lecteur d'écran. Le refus à l'expiration est une mesure de sécurité (exception « limite essentielle »). |
| R6 | **Zoom réel du navigateur** | 10.4, 10.11 | Edge à 200 % puis 400 % de zoom (Ctrl +) sur une fenêtre de 1 280 px : aucune perte de contenu ni défilement horizontal de la page. Les E2E émulent la largeur correspondante (320 px, 640 px) et un texte à 200 %, ce qui rend la même mise en page. |
| R7 | **Langue des réponses** | 8.7 | Décider si une réponse de modèle en langue étrangère doit être balisée (voir « Écarts et reports »). |
| R8 | **Vidéoprojecteur réel** | 3.2, 10.4 | Voir la liste ci-dessous. |

### Recette du mode projection (Flow 1 du fond de la salle)

Matériel : le vidéoprojecteur de la salle de démonstration, la démo réelle (Ollama, vrais modèles), réglage Affichage > Mode projection. Se placer au dernier rang et jouer Flow 1 : Accueil, carte « Démo recommandée », comparaison de 3 modèles, classement, matrice, verdict, export.

- [ ] Les titres et les boutons se lisent du fond de la salle, sans plisser les yeux ; le plus petit texte (aides, étiquettes d'axes) reste lisible ou est tolérable (le plus petit fait 18 px à 1 440 px de large, 15 px pour les graduations).
- [ ] Les chiffres de métrique (note, durée, CO₂) sont lisibles à distance et leur unité aussi.
- [ ] Les trois ou quatre colonnes de l'Arène tiennent sans défilement sur l'écran du projecteur (1 920 x 1 080, ou 1 280 x 720 si c'est la définition de la salle) ; sinon noter la définition et le défilement.
- [ ] Le contraste du thème choisi (Clair ou Sombre) tient dans une pièce éclairée : si la lumière de la salle délave le clair, essayer le sombre.
- [ ] Le classement et la matrice se lisent sans la couleur : les noms écrits suffisent.
- [ ] Le pied de page est bien masqué ; rien d'autre ne manque.
- [ ] Le curseur de la souris, le focus clavier et le bouton « Arrêter » se voient depuis le fond.
- [ ] Noter la définition, la distance, le thème et les écarts relevés : chaque écart est corrigé ou consigné dans « Écarts et reports ».

## Preuves automatiques

Fichier : `tests/v2/e2e/test_accessibilite.py` (axe-core réinjecté tel quel : aucune règle désactivée, aucune exclusion, routes lues dans le registre). Les tests propres à chaque écran (`test_arena.py`, `test_chat.py`, etc.) gardent leurs contrôles axe d'états précis.

| Sigle | Test | Ce qu'il prouve |
|---|---|---|
| T1 | `test_axe_finds_no_violation_on_any_route_in_any_display_mode` | Zéro violation axe, chaque route, dans six affichages (Clair, Sombre, Système avec un système clair et avec un système sombre, projection en clair et en sombre) : au repos, liste des modèles ouverte, fiche d'un modèle, panneaux dépliés, dialogue de confirmation (avec et sans détail à valider), chat avec réflexion et aide ouvertes, Arène rouverte et son dialogue d'effacement, fiche et suppression d'un modèle, Sobriété avec son historique. Il vérifie aussi que ces états ont bien été atteints. |
| T2 | `test_axe_finds_no_violation_on_the_topbar_panels_in_any_display_mode` | Les quatre panneaux de la barre haute (Ollama, aide du cloud, CO₂, Affichage), sur chaque route, dans les six affichages. |
| T3 | `test_no_horizontal_scroll_on_any_route` | Aucun défilement horizontal de la page, ni débordement hors d'un conteneur qui défile : 320 px, zoom à 200 % (640 px), texte à 200 %, en clair et en projection sombre, mêmes états que T1 et panneaux de la barre haute. |
| T4 | `test_axe_finds_no_violation_on_any_route_when_reflowed` | axe à 320 px et à 640 px, mêmes états. |
| T5 | `test_text_spacing_overrides_clip_no_text_and_cause_no_horizontal_scroll` | Espacement du texte de WCAG 1.4.12 (interligne 1,5, lettres 0,12 em, mots 0,16 em, paragraphes 2 em) : aucun texte coupé, aucun défilement horizontal, à 1 440 et 320 px. |
| T6 | `test_keyboard_reaches_every_stop_with_a_visible_focus_and_never_gets_trapped` | En tabulant (40 arrêts au plus par écran), chaque arrêt porte un contour ou une ombre de focus, et le parcours avance. |
| T7 | `test_every_screen_has_one_h1_a_distinct_title_and_the_french_language` | `lang="fr"`, un `h1` et un titre de page distinct par écran. |
| T8 | `test_no_positive_tabindex_and_no_new_window_without_a_warning` | Aucun `tabindex` positif ; tout lien `target="_blank"` annonce la nouvelle fenêtre. |
| T9 | `test_interface_component_tokens_keep_three_to_one_on_both_surfaces` | Bordures des champs, contour de focus et liseré des interrupteurs à 3:1 au moins sur les deux fonds, clair et sombre. |
| T10 | `test_projection_scales_the_smallest_text_of_every_route_by_the_ramp` | Le plus petit texte de chaque écran grandit du rapport 9/7 en projection (texte des SVG compris), et reste à 15 px au moins. |
| T11 | `test_first_load_leaves_the_focus_at_the_top_so_the_skip_link_is_the_first_stop` et `test_a_route_change_moves_the_focus_to_the_h1_of_the_screen` | Décision B16 (focus au premier chargement) et focus sur le `h1` à chaque changement d'écran. |

## Focus au premier chargement (B16)

**Décision : au premier chargement de la page, le focus n'est pas déplacé sur le `h1`.** Il reste en tête du document : le premier Tab atteint le lien d'évitement « Aller au contenu » (RGAA 12.7, WCAG 2.4.1), puis la navigation. Le lien d'évitement place le focus sur `main` sans changer la route. Le titre de la page (`<Écran> · WaveLocalAI`) et l'annonce polie (« Écran … ») sont posés dès le premier rendu. À chaque changement d'écran ensuite, le focus va sur le `h1` (déjà livré en 1.8, inchangé).

Pourquoi : la spec ne tranche pas (le critère de l'epic 1.8 dit « à chaque route » et la story 1.8 l'a lu « à chaque changement d'écran »). La variante conservatrice garde le comportement livré, qui est celui des pages ordinaires : un lecteur d'écran lit le titre à l'ouverture, et déplacer le focus au chargement ferait sauter la barre haute à un utilisateur du clavier. Si la recette R2 montre qu'un utilisateur de NVDA ne repère pas l'écran au premier chargement, la variante inverse tient en trois lignes du routeur.

Appliqué : `core/router.js` (commentaire daté), test T11 (jamais le `h1` au premier chargement, `Tab` puis `Entrée` sur le lien d'évitement, focus sur `main`, adresse inchangée).

## Grille des 106 critères

### 1. Images

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 1.1 | Image porteuse d'information : alternative textuelle | Conforme | Les graphiques et le schéma d'équipe sont des `svg role="img"` nommés par `<title>` et `<desc>` ; T1 (`svg-img-alt`, `image-alt`). |
| 1.2 | Image de décoration ignorée | Conforme | Icônes `aria-hidden="true" focusable="false"`, logo `alt=""` ; T1. |
| 1.3 | Alternative pertinente | À vérifier par Anaël (recette manuelle) | R2 : pertinence des descriptions de graphiques à l'écoute. |
| 1.4 | Image-test (captcha) : nature identifiable | Non applicable | Aucun captcha. |
| 1.5 | Captcha : alternative | Non applicable | Aucun captcha. |
| 1.6 | Description détaillée si nécessaire | Conforme | Chaque graphique a `<desc>` et un bouton « Voir le tableau » qui mène au tableau équivalent (`wl-chart-svg`) ; le schéma d'équipe a `<desc>` (ordre des agents). |
| 1.7 | Description détaillée pertinente | À vérifier par Anaël (recette manuelle) | R2. |
| 1.8 | Image-texte remplacée par du texte | Conforme | Aucune image-texte : texte en HTML ou en `<text>` SVG. |
| 1.9 | Légende d'image reliée | Non applicable | Aucune `figure` à légende ; la légende de taille des points est du HTML voisin du graphique. |

### 2. Cadres

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 2.1 | Titre de cadre | Non applicable | Aucun `iframe`. |
| 2.2 | Titre de cadre pertinent | Non applicable | Aucun `iframe`. |

### 3. Couleurs

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 3.1 | Information jamais donnée par la couleur seule | À vérifier par Anaël (recette manuelle) | Conçu ainsi (badges en texte et icône, points nommés avec contour d'encre, états écrits) ; R3 le confirme en niveaux de gris. |
| 3.2 | Contraste du texte | Conforme | T1, T2, T4 : règle `color-contrast` d'axe dans les six affichages, dont la projection. |
| 3.3 | Contraste des composants d'interface et des éléments graphiques | À vérifier par Anaël (recette manuelle) | T9 prouve 3:1 pour les bordures de champs, le focus et les interrupteurs ; reste le point `chart-4` (2,95:1 sur blanc, contour d'encre) : R3. |

### 4. Multimédia

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 4.1 à 4.13 | Média temporel ou non temporel : transcription, sous-titres, audiodescription, contrôle, compatibilité (treize critères) | Non applicable | Aucun `video`, `audio`, `object`, `embed` ni son : la v2 ne sert aucun média. |

### 5. Tableaux

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 5.1 | Tableau de données complexe : résumé | Non applicable | Aucun tableau à en-têtes multiples ou imbriqués (`wl-data-table` : une ligne d'en-têtes, première colonne en en-tête de ligne). |
| 5.2 | Résumé pertinent | Non applicable | Idem. |
| 5.3 | Tableau de mise en forme linéarisable | Non applicable | Aucun tableau de mise en forme : les mises en page sont en flex et en grille. |
| 5.4 | Titre associé au tableau de données | Conforme | `<caption class="sr-only">` et `aria-label` de la zone qui défile (`wl-data-table`) ; T1. |
| 5.5 | Titre pertinent | À vérifier par Anaël (recette manuelle) | R2. |
| 5.6 | En-têtes de colonnes et de lignes déclarés | Conforme | `<th scope="col">`, `<th scope="row">` ; T1 (`th-has-data-cells`, `scope-attr-valid`). |
| 5.7 | Technique appropriée d'association cellule et en-tête | Conforme | `scope` ; aucune cellule fusionnée ; T1 (`td-headers-attr`). |
| 5.8 | Tableau de mise en forme sans élément de tableau de données | Non applicable | Aucun tableau de mise en forme. |

### 6. Liens

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 6.1 | Lien explicite | À vérifier par Anaël (recette manuelle) | R2 : liste des liens de NVDA. Les liens de module, d'onglet d'écran et de fiche sont nommés par leur texte ; T1 (`link-name`). |
| 6.2 | Lien avec un intitulé | Conforme | T1 (`link-name`, `button-name`) : aucun lien ni bouton sans nom accessible. |

### 7. Scripts

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 7.1 | Script compatible avec les technologies d'assistance | À vérifier par Anaël (recette manuelle) | Composants au patron ARIA APG (combobox du sélecteur, menu Exporter, onglets, `<dialog>`, panneaux `aria-expanded`) ; T1 contrôle leurs rôles et propriétés ; R2 le comportement réel sous NVDA. |
| 7.2 | Alternative au script pertinente | Non applicable | Aucun script n'a d'alternative (la page exige JavaScript, `noscript` le dit) : aucune alternative à juger. |
| 7.3 | Script contrôlable au clavier et au pointeur | À vérifier par Anaël (recette manuelle) | T6 prouve l'atteignabilité et le focus visible ; R1 l'opérabilité complète. |
| 7.4 | Changement de contexte annoncé ou contrôlé | À vérifier par Anaël (recette manuelle) | Aucun changement de contexte sans action : un changement d'écran vient d'un lien, annoncé et suivi du focus sur le `h1` ; aucune soumission automatique. R1. |
| 7.5 | Messages de statut restitués | À vérifier par Anaël (recette manuelle) | Zones `role="status"` (`#announcer`, `#status-announcer`) et `role="alert"` (erreurs, bandeau de redémarrage), progression des runs annoncée ; R2 l'écoute. |

### 8. Éléments obligatoires

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 8.1 | Type de document déclaré | Conforme | `<!doctype html>` ; T7 charge la page. |
| 8.2 | Code source valide | À vérifier par Anaël (recette manuelle) | R4. axe contrôle les identifiants dupliqués, rôles et attributs ARIA valides (T1). |
| 8.3 | Langue par défaut indiquée | Conforme | `lang="fr"` ; T7. |
| 8.4 | Code de langue pertinent | Conforme | `fr` ; T7. |
| 8.5 | Titre de page | Conforme | `<Écran> · WaveLocalAI` à chaque route ; T7. |
| 8.6 | Titre de page pertinent | Conforme | Un titre distinct par écran ; T7. |
| 8.7 | Changement de langue indiqué | Non conforme, reporté | Les réponses des modèles sont en langue libre et ne sont pas balisées : « Écarts et reports ». Les textes de l'interface sont tous en français ; les noms de modèles et de produits (Ollama, Qwen, Self-RAG…) sont des noms propres ou des termes sans traduction. |
| 8.8 | Code de langue de changement pertinent | Non applicable | Aucun passage balisé. |
| 8.9 | Balises non détournées à des fins de présentation | Conforme | Relecture : `ul`, `dl`, `table`, `fieldset`, `dialog`, `details` pour leur sens ; T1 (`list`, `definition-list`, `empty-heading`). |
| 8.10 | Changements de sens de lecture | Non applicable | Texte français, sens unique, aucun passage de droite à gauche. |

### 9. Structuration

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 9.1 | Information structurée par des titres | À vérifier par Anaël (recette manuelle) | T7 (un `h1`) et T1 (`heading-order`, `empty-heading`) ; la pertinence de la hiérarchie : R2. |
| 9.2 | Structure du document cohérente | Conforme | `header`, `nav`, `main`, `footer` ; T1 (`region`, `landmark-*`). |
| 9.3 | Listes structurées | Conforme | `ul`/`ol` ; T1 (`list`, `listitem`). |
| 9.4 | Citations indiquées | Conforme | Le rendu Markdown (`core/markdown.js`) produit un `blockquote` pour une citation. |

### 10. Présentation de l'information

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 10.1 | Feuilles de styles pour la présentation | Conforme | Aucun attribut de présentation dans le HTML (hors les dimensions du logo) ; couleurs par les jetons de `tokens.css`. |
| 10.2 | Contenu visible sans CSS | Conforme | Seul `::before` à porter du texte : le numéro d'étape de l'évaluation, dans une liste `ol` (relecture des feuilles) ; le sens tient sans lui. |
| 10.3 | Information compréhensible sans CSS | Conforme | L'ordre du DOM suit la lecture (T8, T6). |
| 10.4 | Taille des caractères et zoom à 200 % | Conforme | Tout en `rem` ; T3 (zoom 200 %, texte à 200 %). R6 le confirme au zoom réel. Un schéma d'équipe à largeur en px ne suivait pas le texte : corrigé (T10). |
| 10.5 | Couleurs de fond et de texte déclarées ensemble | Conforme | Jetons `--color-surface` et `--color-ink` déclarés ensemble, thèmes clair et sombre. |
| 10.6 | Lien visible au survol et au focus, distinct du texte | Conforme | T1 (`link-in-text-block`), T6 (focus). |
| 10.7 | Focus visible | Conforme | `:focus-visible` à 3:1 (`base.css`) ; T6 ; T9. |
| 10.8 | Contenu masqué ignoré par les technologies d'assistance | Conforme | `hidden`, `aria-hidden` ; T1 (`aria-hidden-focus`). |
| 10.9 | Information jamais donnée par la forme seule | Conforme | Badges en texte, états écrits ; relecture. |
| 10.10 | Information jamais donnée par la position seule | Non conforme, corrigé | Deux textes renvoyaient à la position (« ci-dessous », « ci-dessus ») : réécrits en nommant la section et la fiche (`models.json`). |
| 10.11 | Contenu sans défilement à 320 px (reflux) | Non conforme, corrigé | À 320 px en projection, l'écran Modèles débordait de 10 px (la piste de grille s'élargissait au plus large contenu) : `models.css`. T3 et T4 : aucun écran ne défile horizontalement à 320 px ni à 640 px ; seuls les tableaux larges défilent dans leur conteneur. |
| 10.12 | Espacement du texte redéfinissable | Conforme | T5. |
| 10.13 | Contenus additionnels au survol ou au focus : fermables, survolables, persistants | Conforme | Aucune infobulle de survol : les aides sont des boutons à `aria-expanded`, fermés par Échap ; seule la bulle native du `title` des liens Markdown est affichée. |
| 10.14 | Contenus additionnels par CSS seul : visibles au clavier | Conforme | Aucun contenu révélé par `:hover` ou `:focus` seul (relecture des feuilles). |

### 11. Formulaires

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 11.1 | Étiquette de champ | Conforme | T1 (`label`, `select-name`, `aria-input-field-name`). |
| 11.2 | Étiquette pertinente | À vérifier par Anaël (recette manuelle) | R2. |
| 11.3 | Étiquettes cohérentes pour des champs de même fonction | Conforme | Mêmes composants (`wl-model-picker`, interrupteurs) partout. |
| 11.4 | Étiquette et champ accolés | Conforme | Étiquette visible au-dessus ou à côté ; relecture des feuilles. |
| 11.5 | Champs de même nature regroupés | Conforme | `fieldset` (thème, scénarios, outils, agents). |
| 11.6 | Légende du regroupement | Conforme | `legend` ; T1 (`aria-required-children`, `radiogroup`). |
| 11.7 | Légende pertinente | Conforme | Relecture des textes (`shell.json`, `arena.json`, `agents.json`, `crew.json`). |
| 11.8 | Items d'une liste de choix regroupés | Conforme | Le sélecteur de modèles groupe « Sur cette machine » et « Cloud » (`role="group"`). |
| 11.9 | Intitulé de bouton pertinent | À vérifier par Anaël (recette manuelle) | R2 ; T1 (`button-name`). |
| 11.10 | Contrôle de saisie pertinent | À vérifier par Anaël (recette manuelle) | Raison des boutons désactivés écrite en clair (« Choisissez au moins 2 modèles ») ; R2 la lecture des erreurs. |
| 11.11 | Suggestions d'aide à la saisie | Non applicable | Aucune saisie à format strict à corriger par suggestion ; les erreurs disent l'action à faire (`wl-error`). |
| 11.12 | Saisies à enjeu : modifiables, vérifiables, confirmées | Conforme | Suppression d'un document, d'un modèle, vidage de la base, effacement d'une comparaison, envoi d'un email : `wl-confirm-dialog` avec « Annuler » comme focus initial ; T1. |
| 11.13 | Finalité d'un champ de données personnelles | Non applicable | Aucun champ de données personnelles de la personne (nom, adresse, etc.). |

### 12. Navigation

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 12.1 | Deux systèmes de navigation au moins | Non conforme, reporté | Le menu des modules et l'Accueil (cartes vers chaque module) : ni plan du site ni moteur de recherche. Voir « Écarts et reports ». |
| 12.2 | Menu et barres de navigation toujours à la même place | Conforme | Barre haute commune à tous les écrans ; onglets d'écran en tête de chaque module. |
| 12.3 | Page « plan du site » pertinente | Non applicable | Aucune page « plan du site ». |
| 12.4 | Page « plan du site » atteignable de manière identique | Non applicable | Idem. |
| 12.5 | Moteur de recherche atteignable de manière identique | Non applicable | Aucun moteur de recherche. |
| 12.6 | Zones de regroupement atteignables ou évitables | Conforme | `header`, `nav`, `main`, `footer`, lien d'évitement ; T1 (`region`, `bypass`). |
| 12.7 | Lien d'évitement ou d'accès rapide au contenu | Conforme | « Aller au contenu », premier arrêt de Tab, focus sur `main` ; T11. |
| 12.8 | Ordre de tabulation cohérent | À vérifier par Anaël (recette manuelle) | T8 : aucun `tabindex` positif ; l'ordre suit le DOM, qui suit la lecture. R1. |
| 12.9 | Aucun piège au clavier | À vérifier par Anaël (recette manuelle) | T6 : le parcours avance sur chaque écran ; dialogues modaux fermés par Échap et « Annuler ». R1. |
| 12.10 | Raccourcis à une seule touche contrôlables | Non applicable | Aucun raccourci à touche seule : flèches, Entrée et Échap n'agissent que dans un composant qui a le focus. |
| 12.11 | Contenus additionnels atteignables au clavier | À vérifier par Anaël (recette manuelle) | Aides, panneaux, fiches et listes s'ouvrent par un bouton ou un champ ; T1 les contrôle ouverts ; R1. |

### 13. Consultation

| Critère | Intitulé | Statut | Preuve ou action |
|---|---|---|---|
| 13.1 | Limite de temps contrôlable | À vérifier par Anaël (recette manuelle) | Seule limite : le délai de validation d'un email par l'Agent seul, affiché dans le dialogue ; son refus à l'expiration protège l'envoi (limite essentielle). R5. |
| 13.2 | Nouvelle fenêtre ouverte seulement sur action, et annoncée | Non conforme, corrigé | Les liens d'une réponse Markdown s'ouvraient dans une nouvelle fenêtre sans le dire : `title` « S'ouvre dans une nouvelle fenêtre » (`core/markdown.js`) ; T8. |
| 13.3 | Document bureautique en téléchargement accessible | Non applicable | Les exports sont du CSV, du Markdown et du JSON, pas des documents bureautiques. |
| 13.4 | Document bureautique : alternative accessible | Non applicable | Idem. |
| 13.5 | Contenu cryptique : alternative | Non applicable | Aucun art ASCII ni écriture cryptique. |
| 13.6 | Alternative au contenu cryptique pertinente | Non applicable | Idem. |
| 13.7 | Changement brusque de luminosité | Conforme | Aucun clignotement : seul un squelette de chargement pulse à 0,7 Hz entre 50 et 100 % d'opacité. |
| 13.8 | Contenu en mouvement ou clignotant contrôlable | Conforme | Seul le squelette de chargement bouge, tant que la donnée n'est pas arrivée ; `prefers-reduced-motion` coupe toute animation (`base.css`). |
| 13.9 | Contenu consultable quelle que soit l'orientation | Conforme | Aucun verrouillage d'orientation ; T3 à 320 et 640 px de large. |
| 13.10 | Gestes complexes remplaçables | Conforme | Aucun geste de glisser, de pincer ou à plusieurs doigts. |
| 13.11 | Action au pointeur annulable | Conforme | Boutons et liens natifs : l'action part au relâchement. |
| 13.12 | Mouvement de l'appareil | Non applicable | Aucune fonction par mouvement de l'appareil. |

## Écarts et reports

| Réf. | Écart | Décision | Suite |
|---|---|---|---|
| E1 | Focus au premier chargement (B16) | Variante conservatrice : le focus reste en tête ; titre et annonce posés au premier rendu (voir plus haut). | Rouvrir si R2 montre un défaut. |
| E2 | 8.7 : réponses de modèles en langue libre, non balisées | Non corrigé : le client ne connaît pas la langue d'un texte généré, et un balisage faux est pire que l'absence. | Décision d'Anaël (R7) ; piste : un réglage « langue des réponses » dans le chat. Story de correctif à créer après la 8.4. |
| E3 | 12.1 : pas de second système de navigation (ni plan ni recherche) | Non corrigé : douze écrans, un menu des modules, des onglets d'écran et un Accueil qui lie chaque module. | À trancher avec la 8.4 ; piste : une page « Plan de l'application » ou un champ « Aller à… » sous l'Accueil. Story de correctif à créer. |
| E4 | Points `chart-4` à 2,95:1 sur blanc | Gardés : le contour d'encre porte la lisibilité (3.3). | R3 ; si la recette conclut non, assombrir `chart-4` dans `DESIGN.md` et `tokens.css` (test de dérive à réaligner). |
| E5 | Lien Markdown : `title` seul pour annoncer la nouvelle fenêtre | Variante conservatrice : sans ajouter d'icône (le sprite officiel attend le fichier d'Anaël, décision du 2026-10-19). | À réexaminer avec le sprite : une icône « ouvre dans un nouvel onglet » visible. |
