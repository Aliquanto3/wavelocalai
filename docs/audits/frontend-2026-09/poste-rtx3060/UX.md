# Audit UX et visuel du frontend : poste-rtx3060

- **Date** : 26 septembre 2026
- **Commit** : `d954bd67b0b10912ae9a4c8662c418c95e250ba4`
- **Complète** `RAPPORT.md`, qui porte sur le fonctionnement. Ici, on se demande si le front est beau, cohérent et agréable à prendre en main.
- **Fait sur une seule machine** : le rendu ne dépend pas du matériel, donc l'audit jumeau n'a pas à être refait ailleurs.

## Méthode et référentiels

- **Captures** : 5 pages × 2 thèmes (Streamlit lancé avec `--theme.base light`, puis `dark`) × 2 largeurs (1440 px et 390 px), plus les écrans avec résultats du premier audit.
- **Mesures automatiques** :
  - [axe-core](https://github.com/dequelabs/axe-core) 4.10.2 sur chaque page, en thème clair et en thème sombre ;
  - nombre d'emojis ;
  - polices et couleurs calculées ;
  - débordement horizontal ;
  - noms accessibles des boutons.
- **Référentiels** :
  - [Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines) de Vercel, via le skill `web-design-guidelines`. Les règles pensées pour l'anglais sont transposées au français : casse de phrase et non *Title Case*, guillemets « », espaces insécables.
  - Le skill `frontend-design` d'Anthropic pour la direction artistique ; la charte Wavestone (skill `wavestone-web`) ; le skill `dataviz` pour les graphiques. Les palettes proposées au §4 ont été validées par son script, pas à l'œil.
  - WCAG 2.2 niveau AA pour les contrastes : 4,5:1 pour le texte courant, 3:1 pour le grand texte et les éléments graphiques.
- **Piège de mesure** : Streamlit fait défiler la page dans un conteneur interne. Une capture Playwright en `full_page` s'arrête donc au bas de la fenêtre. Les captures « hautes » ont été prises avec une fenêtre de 2600 px.

## 1. Verdict

**Le front est propre, mais générique, et il ne ressemble ni à Wavestone ni à ce qu'il défend.**

C'est le thème Streamlit par défaut : police Source Sans, rouge `#FF4B4B`, emojis en guise d'icônes. On le reconnaît au premier coup d'œil comme un prototype Streamlit.

Trois choses empêchent d'aller plus loin :
- **La couleur dit le contraire de ce qu'elle devrait.** Le rouge de l'action principale est aussi celui de l'erreur, alors que la seule action destructrice est grise.
- **Le vocabulaire est éclaté.** Chaque module porte trois ou quatre noms, en français ou en anglais selon l'endroit.
- **L'interface affirme des choses fausses.** « Opérationnel » est écrit en dur, « Cumul » désigne une courbe qui redescend, et le mode cloud est actif par défaut sur une démo « souveraine ».

Côté positif :
- aucun débordement horizontal, même à 390 px ;
- le thème sombre ne pose presque pas de problème de contraste ;
- les parcours sont lisibles ;
- l'état vide du RAG et l'accueil de l'Agent Lab (« Bonjour ! » et actions rapides) sont de bonnes intentions de design.

Mon avis : pour une démo destinée à des clients Wavestone, la marche est surtout **d'identité et de cohérence**, pas d'ergonomie. Les parcours tiennent. C'est l'emballage qui dessert le propos.

## 2. Mesures

| Page | Emojis (texte visible) | Contraste en échec (clair / sombre) | Autres violations axe | Défilement horizontal à 390 px |
|---|---|---|---|---|
| Accueil | 13 | 4 / 0 | `heading-order` ×5 | non |
| Socle Hardware | 8 | 7 / 0 | `heading-order` | non |
| Inférence | 8 | 5 / 0 | `heading-order` | non |
| RAG | 7 | 3 / 2 | `heading-order` | non |
| Agent Lab | 19 | 10 / 0 | `heading-order` | non |

Les violations `region` (contenu hors d'une zone repère de la page) et `aria-allowed-attr` (sur `.stSidebar`) viennent de Streamlit lui-même. Elles ne sont pas corrigeables côté application et ne sont pas comptées ici.

**Contrastes mesurés** (texte de 14 px, seuil de 4,5:1) :

| Élément | Couleurs | Ratio |
|---|---|---|
| Texte blanc sur bouton principal | `#FFFFFF` / `#FF4B4B` | **3,30** |
| Légendes (`st.caption`) | `#83858C` / `#FFFFFF` | **3,68** |
| Pastille d'erreur (Agent Lab) | `#FF4B4B` / `#FFEDED` | **2,92** |
| Delta vert des métriques | `#158237` / `#E9F9EE` | 4,49 |
| Titre de l'encart « base vide », thème clair | `#31333F` / `#262730` | **1,18** |

## 3. Constats

Gravité : **majeur** (trompe l'utilisateur ou bloque l'accessibilité AA), **moyen** (nuit à la compréhension ou à l'image), **mineur**.

### Identité et thème

**U1 — Aucune identité Wavestone · moyen**
- Il n'existe pas de `.streamlit/config.toml`. Tout est au défaut Streamlit : Source Sans, primaire rouge, aucun logo.
- La charte (`wavestone-web`) impose pourtant le violet `#451DC7`, le vert `#04F06A` en accent rare, Aptos avec Inter en repli, et le logo dans l'en-tête.
- Streamlit 1.64 permet tout cela sans CSS : `[theme.light]` et `[theme.dark]`, `font`, `headingFont`, `baseRadius`, `chartCategoricalColors`, `st.logo`. Voir le §4.

**U2 — Emojis en guise d'icônes, parfois en double ou comme titres · moyen**
- De 7 à 19 emojis par page. Le bouton « 📂 📂 Gérer les Documents » les cumule (`03_RAG_Knowledge.py:150` : `icon="📂"` plus l'emoji du libellé).
- 🧠 sert d'icône à la fois à Inférence et au RAG (`02_Inference_Arena.py:13`, `03_RAG_Knowledge.py:29`).
- Sur l'Accueil, les emojis 🔋 🧠 📚 🤖 sont balisés en `<h1>`, ce qui casse la hiérarchie des titres (axe `heading-order` ×5).
- La charte proscrit les emojis décoratifs. Streamlit propose nativement les icônes Material (`icon=":material/database:"`) : elles sont monochromes, héritent de la couleur du texte et sont traitées comme décoratives par les lecteurs d'écran.

**U3 — Barre d'outils de développement visible · mineur**
- « Deploy » et le menu Streamlit apparaissent sur toutes les pages. En démo client, `client.toolbarMode = "viewer"` les retire.

### Couleur et accessibilité

**U4 — Sémantique des couleurs inversée · majeur**
- Le rouge sert à l'action principale : « Lancer le Test », « FIGHT ! », « Lancer le Benchmark », « Gérer les Documents ». C'est aussi la couleur des erreurs (`st.error`) et des pastilles d'outils.
- À l'inverse, « Tout supprimer (Reset) », la seule action vraiment destructrice, est un bouton secondaire gris (`03_RAG_Knowledge.py:126`).
- Avec la charte, le primaire passe au violet `#451DC7` (9,32:1 avec texte blanc), et le rouge `#FF2A49` est réservé au risque, avec une confirmation.

**U5 — Contrastes insuffisants en thème clair · majeur**
- Voir le tableau du §2. Les boutons principaux (3,30:1) et toutes les légendes (3,68:1) échouent au niveau AA, sur toutes les pages. En thème sombre, seul le bouton rouge échoue.
- Pour les légendes, prendre l'encre secondaire de la charte `#4A4A5E` (8,63:1). Le gris de la charte `#8A8A9E` ne fait que 3,38:1 : il est à réserver aux éléments non textuels.

**U6 — L'encart « base vide » suppose le thème sombre · majeur (thème clair)**
- Le CSS injecté fixe `background-color: #262730`, le fond du thème sombre de Streamlit (`03_RAG_Knowledge.py:37-45`). Le `<h2>` suit le thème. En clair : 1,18:1, titre illisible.
- Correctif : utiliser `st.container(border=True)` et les couleurs du thème, sans aucun hex en dur. C'est la cause de F8 dans `RAPPORT.md`.

**U7 — Bouton à icône seule sans nom accessible · mineur**
- Le bouton 🗑️ « Effacer l'historique » du Chat (`tabs/inference/chat.py:110`) a pour nom accessible « 🗑️ ». L'aide au survol n'est pas un libellé. Il faut le libellé « Effacer » et une icône Material.

### Vocabulaire et rédaction

**U8 — Un module, quatre noms · moyen**

| Menu latéral | Carte d'accueil | Titre de page | Onglet du navigateur |
|---|---|---|---|
| Socle Hardware | 01. Cockpit GreenOps | Cockpit GreenOps & Hardware | Socle Hardware |
| Inference Arena | 02. Inférence & Arena | Inférence & Model Arena | Inférence & Arena |
| RAG Knowledge | 03. Base de Connaissance (RAG) | Assistant Documentaire | RAG Knowledge Base |
| Agent Lab | 04. Agents Autonomes | Agent Lab | Agent Lab |

- Le même interrupteur a aussi trois libellés : « Activer Cloud (Mistral) » dans la barre latérale, « Autoriser les API Cloud (Mistral/OpenAI) » en bas de l'Accueil (tronqué en « …(Mis… »), et « Mode Hybride (Local / Cloud) ».
- Règle du skill `frontend-design` : une action garde le même nom tout au long du parcours. Il faut fixer un nom par module et par commande, en français, et l'appliquer partout.

**U9 — Français et anglais mêlés, jargon technique exposé · moyen**
- Les outils de l'agent s'appellent « Time », « Calculator », « Email Sender », « Data Analyzer »… (`src/core/agent_tools.py:807-856`).
- On lit aussi « Accélérateur AI », « Tracking Actif », « Solo (LangGraph) », « Crew (Multi-Agent) », « chunks indexés ».
- Une démo destinée à des décideurs devrait parler de « documents indexés » et d'« extraits », et garder les noms techniques pour l'aide contextuelle.

**U10 — Typographie et formats anglais · mineur**
- Nombres : « 8.1% », « 0.66 s », « 13.83/31.4 GB ». Le français veut « 8,1 % », « 0,66 s », « 13,8 / 31,4 Go ».
- Dates des graphiques : « Sep 26, 2026 ».
- *Title Case* dans des titres français : « IA Générative Souveraine, Frugale et Sécurisée », « Entrée Utilisateur », « Scénario Prédéfini ».
- Pluriels non accordés : « 1 chunks indexés » (`03_RAG_Knowledge.py:155`), « 1 Sources utilisées » (`tabs/rag/chat.py:60`).
- Majuscules d'insistance (« VOS sources »), « © 2025 » en 2026 (`Accueil.py:167`).

### Vérité de l'interface

**U11 — « Opérationnel 🟢 » est écrit en dur · majeur**
- `Accueil.py:88` affiche `st.metric("Système", "Opérationnel 🟢", help="Tous les services sont actifs")` sans rien vérifier. Si Ollama est arrêté, l'accueil l'annonce quand même comme opérationnel. La valeur est en plus tronquée en « Opérationnel… » à 1440 px.
- Il faut un vrai test, `LLMProvider.health_check()` existe déjà, ou retirer l'indicateur.

**U12 — Le mode cloud est actif par défaut sur une démo « souveraine » · majeur (décision produit)**
- `Accueil.py:31` : `cloud_enabled = True`. La clé Mistral est présente dans `.env`, donc le mode est réellement actif. L'accueil affiche « Mode Hybride · API Active » juste sous le slogan « IA Générative Souveraine », et Socle Hardware affiche « Sécurité Données : Hybride ».
- Le README promet pourtant « 0 appel API par défaut ». Il faut trancher : désactivé par défaut, et un badge « Local » ou « Cloud » visible sur chaque modèle et chaque réponse.

**U13 — Deltas de `st.metric` détournés en étiquettes · moyen**
- Socle Hardware (`01_Socle_Hardware.py:106-130`) passe des libellés dans `delta=` : « ↑ Charge Actuelle », « ↑ CPU Only », « ↑ API Active ». Même chose dans la barre latérale d'Agent Lab (« ↑ 12.9 GB vs Requis »).
- Une flèche verte montante signifie « en hausse, et c'est bien ». Ici elle est décorative, et ment sur « API Active ». Ces libellés devraient passer en légende ou en badge (`st.badge`).

**U14 — L'agent peut envoyer des emails sans confirmation · majeur (dès que le SMTP est configuré)**
- Tous les outils sont cochés par défaut (`tabs/agent/solo.py:104`), y compris « Email Sender », qui envoie réellement par SMTP (`agent_tools.py:180`). Sur ce poste, `SMTP_USER` n'est pas renseigné, donc il n'y a aucun effet aujourd'hui.
- Règle des Web Interface Guidelines : toute action externe ou irréversible demande une confirmation. Il faut une validation humaine avant l'envoi, et l'outil désactivé par défaut.

**U15 — Suppression immédiate de la base documentaire · moyen**
- « Tout supprimer (Reset) » vide la collection en un clic, sans confirmation ni annulation (vérifié pendant l'audit fonctionnel).

### Graphiques (skill `dataviz`)

**U16 — Historique d'émissions : titre faux, unité illisible, trous masqués · moyen**
- `01_Socle_Hardware.py:180-186` :
  - le graphique s'intitule « Cumul CO2 (kg) » alors qu'il trace les émissions de chaque mesure CodeCarbon. La courbe monte et redescend, ce qu'un cumul ne fait jamais ;
  - l'axe est en « µ » de kg (`20µ`), à exprimer en mg ;
  - une aire relie par une droite des périodes sans aucune mesure (de 09:00 à 09:15), ce qui invente des données ;
  - `tail(50)` prend les 50 dernières lignes, et non une fenêtre de temps.
- Il faut soit un vrai cumul (`cumsum`), soit des barres par session, avec les trous visibles.

**U17 — Matrices de l'Arena et du benchmark RAG · mineur**
- Arena : la taille des points encode le CO₂, sans légende de taille. Un seul point a une couleur différente (le vainqueur, étoile orange), sinon tout est bleu Plotly par défaut. Il n'y a pas de vue tableau à côté.
- Benchmark RAG : l'axe « Qualité Globale (0-1) » contredit le podium, affiché « /100 » (`tabs/rag/eval.py:226`). L'axe CO₂ porte 21 graduations de 0,0 à 4,0 pour un seul point.
- Avec `chartCategoricalColors` réglé dans le thème (§4), toutes les figures Plotly héritent d'une palette validée.

### Mobile

**U18 — Passable à 390 px, sans être pensé pour ; outils masqués dès 1440 px · moyen**
- Pas de débordement horizontal.
- Mais la rangée d'outils de l'Agent Lab est coupée dès 1440 px (« Dat… ») : **5 outils actifs sur 9 sont invisibles**, alors qu'ils sont tous cochés par défaut (voir U14). À 390 px, les cartes empilées repoussent en plus le champ de saisie tout en bas.
- Une démo se fait sur grand écran, donc c'est une priorité basse.

## 4. Direction de design proposée

Elle suit la méthode du skill `frontend-design` : un plan de *tokens* d'abord, confronté au brief, puis le code. Pour la couleur et la typographie, le brief est ici **la charte Wavestone, qui prime**. La liberté ne porte que sur la mise en page et l'élément signature.

**Brief.**
- *Sujet* : un démonstrateur Wavestone d'IA générative locale et sobre.
- *Public* : consultants et décideurs clients, en démonstration sur grand écran.
- *Mission principale* : prouver, mesures à l'appui, qu'un petit modèle local suffit pour le cas d'usage montré.

**Principes.**
1. **Les chiffres sont les héros.** Débit, CO₂ et latence sont la preuve. Ils méritent la plus grande taille, des formats français et une unité toujours visible.
2. **Une seule couleur d'action.** Le violet pour agir, le vert pour « local, sobre, réussi », le rouge uniquement pour le risque.
3. **La souveraineté se voit.** Chaque modèle et chaque réponse porte un badge « Local » ou « Cloud ». C'est l'**élément signature** : sobre, répété, et il porte le propos. Le reste de l'interface reste discret.
4. **Des icônes Material, pas d'emojis.** Seule exception tolérée : l'accueil de l'Agent Lab.

**Tokens.** Couleurs de la charte. Palettes de graphiques validées avec `validate_palette.js` : tous les tests passent, avec un seul avertissement sur l'ambre en thème clair, sans conséquence puisque les points sont étiquetés.

```toml
# .streamlit/config.toml : ébauche à finaliser dans bmad-ux
[client]
toolbarMode = "viewer"

[theme]
baseRadius = "12px"          # --radius-sm de la charte
# Police : Inter servie localement ([[theme.fontFaces]] + server.enableStaticServing),
# plutôt que Google Fonts : une démo souveraine ne dépend pas d'un CDN. Aptos si licence.

[theme.light]
primaryColor = "#451DC7"               # blanc dessus : 9,32:1
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F6F5FA"   # --ws-cream
textColor = "#0A0A14"                  # --ws-ink
borderColor = "#E6E6EC"                # --ws-line
linkColor = "#451DC7"
chartCategoricalColors = ["#6A4DE6", "#0E9F5E", "#2F7FD8", "#C98A00"]

[theme.dark]
primaryColor = "#6A4DE6"               # blanc dessus : 5,50:1
backgroundColor = "#0A0A14"
textColor = "#F6F5FA"
linkColor = "#9B85F0"                  # 6,31:1 sur fond sombre
chartCategoricalColors = ["#7A5FEA", "#12A564", "#3B86DB", "#B07800"]
```

**Ce que ce plan évite volontairement** (contrôle du skill `frontend-design` contre les rendus « par défaut ») :
- la grille de cartes toutes identiques de l'accueil, à remplacer par une liste de modules hiérarchisée, avec la démo recommandée en tête ;
- la numérotation « 01. / 02. » des modules, qui ne sont pas une séquence ;
- le vert `#04F06A` en aplat de texte (1,54:1 avec du blanc) : il ne s'emploie qu'avec l'encre `#0A0A14` (12,83:1).

## 5. Remédiation

Le plan de remédiation est unique pour les deux audits. Il se trouve dans [`RAPPORT.md` §4](RAPPORT.md#4-plan-de-remédiation-bmad-612), et le §4.4 y affecte chaque constat U à une story. En résumé :

- **Nouvelle étape `bmad-ux`**, entre la fusion et `bmad-spec`. Elle part de ce document pour produire `DESIGN.md` (thème, *tokens*, icônes) et `EXPERIENCE.md` (lexique, états vides, erreurs, confirmations), que la spec adopte comme *companions*.
- **Deux capacités issues de cet audit** : CAP-6 « Interface à la charte, accessible et cohérente » et CAP-7 « Souveraineté visible, actions sensibles maîtrisées ».
- **Stories concernées** :
  - 2 : thème, icônes, accessibilité (U1–U7, U18) ;
  - 3 : vocabulaire (U8–U10) ;
  - 5 : états vrais (U11) ;
  - 7 : souveraineté et actions sensibles (U12–U15) ;
  - 9 : graphiques (U16, U17) ;
  - 10 : axe-core dans la suite e2e.
- **Les stories 2 et 3 passent en tête**, juste après l'environnement : elles touchent toutes les pages, et les correctifs fonctionnels s'écrivent ensuite directement dans le nouveau thème et le nouveau lexique.

## Captures

Dans `captures/` : `ux_accueil_clair.png`, `ux_hardware_clair.png`, `ux_agent_mobile.png`, `ux_rag_sombre.png`, ainsi que `rag_after_upload.png` (U6) et `inf_arena.png` (U17), issues du premier audit.
