---
name: WaveLocalAI
description: Démonstrateur Wavestone d'IA générative locale et sobre, en Streamlit 1.x natif ; charte Wavestone appliquée par .streamlit/config.toml, sans framework CSS.
status: final
updated: 2026-09-27
sources:
  - docs/audits/frontend-2026-09/SYNTHESE.md
  - docs/audits/frontend-2026-09/poste-rtx3060/UX.md
colors:
  # Thème clair (par défaut) -> [theme.light]
  primary: '#451DC7'            # primaryColor ; blanc dessus 9,32:1
  on-primary: '#FFFFFF'
  surface: '#FFFFFF'            # backgroundColor
  surface-alt: '#F6F5FA'        # secondaryBackgroundColor (--ws-cream)
  ink: '#0A0A14'                # textColor (--ws-ink) ; 19,69:1 sur surface
  ink-secondary: '#4A4A5E'      # légendes (--ws-ink-soft) ; 8,63:1 sur surface, 7,96:1 sur surface-alt
  gray-graphic: '#8A8A9E'       # non textuel uniquement ; 3,38:1 sur surface
  line: '#E6E6EC'               # borderColor (--ws-line)
  link: '#451DC7'               # linkColor ; 9,32:1
  accent-green: '#04F06A'       # accent rare ; 1,54:1 sur blanc -> jamais en texte ; ink dessus 12,83:1
  risk: '#FF2A49'               # risque uniquement ; 3,70:1 sur blanc -> jamais en texte courant sur blanc
  chart-1: '#6A4DE6'            # chartCategoricalColors, thème clair
  chart-2: '#0E9F5E'
  chart-3: '#2F7FD8'
  chart-4: '#C98A00'
  # Thème sombre -> [theme.dark]
  primary-dark: '#7E65E9'       # compromis : blanc dessus 4,26:1, texte 4,62:1 sur surface-dark, 4,24:1 sur une pastille choisie
  on-primary-dark: '#FFFFFF'
  surface-dark: '#0A0A14'
  surface-alt-dark: '#16162A'   # secondaryBackgroundColor
  ink-dark: '#F6F5FA'           # 18,15:1 sur surface-dark, 16,37:1 sur surface-alt-dark
  ink-secondary-dark: '#B4B4C6' # légendes ; 9,64:1 sur surface-dark, 8,70:1 sur surface-alt-dark
  line-dark: '#2E2E44'          # borderColor
  link-dark: '#9B85F0'          # 6,57:1 sur surface-dark
  accent-green-dark: '#04F06A'  # 12,83:1 sur surface-dark
  risk-dark: '#FF2A49'          # 5,33:1 sur surface-dark
  chart-1-dark: '#7A5FEA'
  chart-2-dark: '#12A564'
  chart-3-dark: '#3B86DB'
  chart-4-dark: '#B07800'
typography:
  # Une seule famille : theme.font et theme.headingFont.
  body:
    fontFamily: 'Aptos, Inter, sans-serif'
    note: 'Streamlit natif — corps de texte, taille de base Streamlit'
  heading:
    fontFamily: 'Aptos, Inter, sans-serif'
    note: 'Streamlit natif — st.title (h1) · st.header (h2) · st.subheader (h3)'
  metric-value:
    fontFamily: 'Aptos, Inter, sans-serif'
    note: 'Streamlit natif — valeur de st.metric'
  caption:
    fontFamily: 'Aptos, Inter, sans-serif'
    note: 'Streamlit natif — st.caption ; couleur {colors.ink-secondary} / {colors.ink-secondary-dark} si clé native'
  code:
    note: 'Streamlit natif — codeFont par défaut'
rounded:
  DEFAULT: 12px                 # theme.baseRadius (--radius-sm de la charte)
  full: 9999px                  # pastilles natives (st.badge, st.pills)
spacing:
  page:
    note: 'Streamlit natif — st.set_page_config(layout="wide") sur toutes les pages'
  columns:
    note: 'Streamlit natif — espacements de st.columns / st.container, aucune marge CSS'
components:
  button-primary:
    streamlit: 'st.button(type="primary")'
    background: '{colors.primary}'
    foreground: '{colors.on-primary}'
    radius: '{rounded.DEFAULT}'
  button-secondary:
    streamlit: 'st.button(type="secondary")'
    background: '{colors.surface}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
    radius: '{rounded.DEFAULT}'
  button-destructive:
    streamlit: 'st.button(type="secondary", icon=":material/delete:")'
    background: '{colors.surface}'
    foreground: '{colors.ink}'
    border: '{colors.line}'
  confirm-dialog:
    streamlit: 'st.dialog + st.warning'
    radius: '{rounded.DEFAULT}'
  metric:
    streamlit: 'st.metric'
    value: '{typography.metric-value}'
  badge-local:
    streamlit: 'st.badge("Local", icon=":material/computer:", color="green")'
    radius: '{rounded.full}'
  badge-cloud:
    streamlit: 'st.badge("Cloud", icon=":material/cloud:", color="orange")'
    radius: '{rounded.full}'
  cloud-toggle:
    streamlit: 'st.toggle'
    active: '{colors.primary}'
  card:
    streamlit: 'st.container(border=True)'
    border: '{colors.line}'
    radius: '{rounded.DEFAULT}'
  module-link:
    streamlit: 'st.page_link(icon=":material/…:")'
    foreground: '{colors.link}'
  alert-info:
    streamlit: 'st.info'
  alert-success:
    streamlit: 'st.success'
  alert-warning:
    streamlit: 'st.warning'
  alert-error:
    streamlit: 'st.error'
  chat-message:
    streamlit: 'st.chat_message + st.chat_input'
    meta: '{typography.caption}'
  sources-expander:
    streamlit: 'st.expander'
  model-select:
    streamlit: 'st.selectbox / st.multiselect'
  tool-pills:
    streamlit: 'st.pills(selection_mode="multi")'
    selected: '{colors.primary}'
  progress-status:
    streamlit: 'st.status / st.spinner / st.progress'
  chart:
    streamlit: 'st.plotly_chart(width=…) et graphiques natifs'
    palette-light: ['{colors.chart-1}', '{colors.chart-2}', '{colors.chart-3}', '{colors.chart-4}']
    palette-dark: ['{colors.chart-1-dark}', '{colors.chart-2-dark}', '{colors.chart-3-dark}', '{colors.chart-4-dark}']
  logo:
    streamlit: 'st.logo avec wordmark texte « WaveLocalAI »'
    foreground: '{colors.ink}'
---

## Brand & Style

WaveLocalAI est un démonstrateur Wavestone : il prouve, mesures à l'appui, qu'un petit modèle local suffit pour le cas d'usage montré, sur grand écran, devant des consultants et des décideurs clients. La marche à franchir est l'identité et la cohérence : l'interface doit ressembler à Wavestone et à ce qu'elle défend, pas à un prototype Streamlit.

1. **Les chiffres sont les héros.** Débit, CO₂ et latence portent la plus grande taille de la page (`{typography.metric-value}`).
2. **Une seule couleur d'action.** Violet `{colors.primary}` pour agir, vert pour « local, sobre, réussi », rouge `{colors.risk}` pour le risque seulement.
3. **La souveraineté se voit.** Le badge Local/Cloud est l'**élément signature** : sobre, répété, porteur du propos. Le reste de l'interface s'efface.
4. `[ASSUMPTION]` **Icônes Material, pas d'emojis.** Icônes `:material/…:` monochromes, qui héritent de la couleur du texte ; seule exception, l'accueil « Bonjour ! » de l'agent.

**Implémentation.** Streamlit 1.x, composants natifs uniquement : aucun framework CSS, aucun `<style>` injecté, aucun hex dans le code des pages. Les tokens passent par `.streamlit/config.toml` :

- `[client] toolbarMode = "viewer"` : ni « Deploy » ni menu de développement ;
- `[theme]` : `baseRadius` = `{rounded.DEFAULT}` ; `font` et `headingFont` = `{typography.body.fontFamily}` ; `[[theme.fontFaces]]` pour Inter, servie par `server.enableStaticServing` ;
- `[theme.light]` et `[theme.dark]` : `primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor`, `borderColor`, `linkColor`, `chartCategoricalColors` selon le tableau Colors.

Chaque clé se vérifie dans la documentation de la version de Streamlit figée par la story 1, jamais de mémoire. La charte Wavestone prime pour la couleur et la typographie ; la liberté ne porte que sur la mise en page et l'élément signature.

## Colors

Clair par défaut (salle éclairée, vidéoprojecteur) ; sombre disponible et soigné, avec des neutres dérivés de l'encre. Seuils WCAG 2.2 : 4,5:1 pour le texte courant, 3:1 pour le grand texte et le graphique.

| Token (clair / sombre) | Clair | Sombre | Clé `config.toml` | Usage | Interdit |
|---|---|---|---|---|---|
| `primary` / `primary-dark` | `#451DC7` | `#7E65E9` | `primaryColor` | Action principale, bascule active, pastille sélectionnée. Blanc dessus : 9,32:1 / 4,26:1 (compromis sombre, voir la note sous le tableau) | Décoration, fonds, titres colorés |
| `surface` / `surface-dark` | `#FFFFFF` | `#0A0A14` | `backgroundColor` | Fond de page | — |
| `surface-alt` / `surface-alt-dark` | `#F6F5FA` | `#16162A` | `secondaryBackgroundColor` | Barre latérale, champs, blocs de code | Violet en fond |
| `ink` / `ink-dark` | `#0A0A14` | `#F6F5FA` | `textColor` | Tout le texte | — |
| `ink-secondary` / `ink-secondary-dark` | `#4A4A5E` | `#B4B4C6` | clé native seulement | Légendes : 8,63:1 / 9,64:1 | CSS injecté pour l'obtenir |
| `gray-graphic` | `#8A8A9E` | — | — | Non textuel (3,38:1) | Tout texte |
| `line` / `line-dark` | `#E6E6EC` | `#2E2E44` | `borderColor` | Bordures décoratives de `card`, séparateurs | Seule frontière d'un contrôle |
| `link` / `link-dark` | `#451DC7` | `#9B85F0` | `linkColor` | Liens, `module-link` : 9,32:1 / 6,57:1 | — |
| `accent-green` / `accent-green-dark` | `#04F06A` | `#04F06A` | — | Accent rare « local, sobre, réussi » : en clair, aplat sous `{colors.ink}` (12,83:1) ; en sombre, texte possible (12,83:1) | Texte ou icône sur blanc (1,54:1) |
| `risk` / `risk-dark` | `#FF2A49` | `#FF2A49` | — | Risque et erreur, toujours nommés par un texte. Graphique ou grand texte en clair (3,70:1), texte en sombre (5,33:1) | Action principale, seuil de CO₂, texte courant sur blanc |
| `chart-1…4` / `chart-1…4-dark` | `#6A4DE6` `#0E9F5E` `#2F7FD8` `#C98A00` | `#7A5FEA` `#12A564` `#3B86DB` `#B07800` | `chartCategoricalColors` | Séries catégorielles, validées par le script du skill `dataviz` | Couleur Plotly par défaut |

**Note `primary-dark` (décision du 27/09, story 14 de `spec-fiabilisation-frontend`).** En sombre, Streamlit emploie `primaryColor` comme fond du texte blanc des boutons principaux et comme couleur de texte (valeur des curseurs, pastilles et segments choisis, dont le fond mêle 10 % de la primaire au fond). Aucune valeur unique ne donne 4,5:1 partout : blanc dessus exige une luminance ≤ 0,183, texte sur `surface-dark` ≥ 0,190. Critère retenu : rendre le plus faible de ces contrastes aussi haut que possible. `#7E65E9` donne (calculé) blanc dessus 4,26:1, curseur sur `surface-dark` 4,62:1, curseur sur `surface-alt-dark` (barre latérale) 4,17:1, pastille choisie 4,25:1 (4,24:1 mesuré par axe). Écartés : `#6A4DE6` (texte 3,34:1), `#7A5FEA` (pastille 4,04:1), `#8468EC` (blanc dessus 4,06:1), `#886DED` (blanc dessus 3,85:1). Écarts connus, par type de composant : texte blanc des boutons principaux, pastilles et segments choisis, curseurs de la barre latérale. Le wordmark garde `#6A4DE6` (image unique, grand texte).

- **Légendes.** `{colors.ink-secondary}` et `{colors.ink-secondary-dark}` ne s'appliquent que si la version figée expose une clé de thème native. Sinon, la couleur native reste, son contraste est mesuré et signalé au rapport de nuit ; aucun CSS.
- **Badges.** `badge-local` vert et `badge-cloud` orange utilisent les couleurs natives de `st.badge` (`[ASSUMPTION]`), dont le contraste est vérifié à l'axe-core au matin. Orange = attention, les données sortent de la machine ; jamais de rouge.
- **Graphiques.** `chart-4` clair fait 2,95:1 sur blanc : il n'encode jamais seul une valeur, ses points sont étiquetés.
- Aucune couleur ne porte seule une information : badge, succès, erreur et série ont toujours un libellé.

## Typography

Une seule famille pour le texte et les titres : **Aptos**, appelée par son nom et utilisée si elle est installée (Office) ; sinon **Inter**, servie localement depuis le dépôt ; sinon `sans-serif`. Aucun fichier Aptos versionné (licence, dépôt public), aucun CDN. Si `theme.font` n'accepte pas de pile de repli dans la version figée, Inter seule s'applique.

| Rôle | Streamlit | Règle visuelle |
|---|---|---|
| `{typography.heading}` | `st.title` · `st.header` · `st.subheader` | Casse de phrase ; aucun emoji, aucune couleur. |
| `{typography.metric-value}` | valeur de `st.metric` | Plus gros chiffre de la page ; débit, CO₂ et durées passent par là, pas par du gras. |
| `{typography.caption}` | `st.caption` | Métadonnées et légendes. |
| `{typography.body}` | texte | Ni majuscules d'insistance ni gras décoratif. |

## Layout & Spacing

- Toutes les pages en `layout="wide"`, barre latérale ouverte au démarrage ; espacements natifs, aucune marge CSS.
- Largeurs par `width=` (pas `use_container_width`, déprécié) et par les ratios de `st.columns`.
- **Accueil :** une colonne hiérarchisée — en-tête, bandeau d'état (une rangée de `metric`), liste des modules. Pas de grille de cartes.
- **Module :** titre, onglets (`st.tabs`), réglages en barre latérale, rangée de `metric` au-dessus du détail des résultats.

## Elevation & Depth

Ni ombre ni dégradé. La hiérarchie vient de l'ordre des titres, de la taille des chiffres et des bordures de `card` ; `{colors.surface-alt}` ne distingue que la barre latérale et les champs.

## Shapes

Un seul rayon, `{rounded.DEFAULT}` (12 px, `--radius-sm` de la charte), porté par `theme.baseRadius` : boutons, champs, conteneurs, dialogues. Les pastilles natives gardent `{rounded.full}`.

## Components

| Composant | Streamlit | Spécification visuelle |
|---|---|---|
| `button-primary` | `st.button(type="primary")` | Fond `{colors.primary}`, texte `{colors.on-primary}`, icône Material facultative à gauche. |
| `button-secondary` | `st.button(type="secondary")` | Fond `{colors.surface}`, bordure `{colors.line}`, texte `{colors.ink}` ; toujours un libellé texte. |
| `button-destructive` | `st.button(type="secondary", icon=":material/delete:")` | Rendu de `button-secondary` : Streamlit n'a pas de bouton rouge natif, le risque se lit dans le libellé et dans `confirm-dialog`. |
| `confirm-dialog` | `st.dialog` | Titre en question, `alert-warning`, puis bouton de confirmation et `button-secondary` « Annuler » côte à côte. |
| `metric` | `st.metric` | Libellé court, valeur avec unité ; `delta` natif (flèche verte ou rouge) seulement pour une variation chiffrée. |
| `badge-local` | `st.badge(color="green")` | « Local » + `:material/computer:` `[ASSUMPTION]`. Élément signature. |
| `badge-cloud` | `st.badge(color="orange")` | « Cloud » + `:material/cloud:` `[ASSUMPTION]`. |
| `cloud-toggle` | `st.toggle` | Actif en `{colors.primary}`. |
| `card` | `st.container(border=True)` | Bordure `{colors.line}`, fond du thème ; remplace tout encart en CSS injecté. |
| `module-link` | `st.page_link` | Icône Material propre au module, jamais partagée. |
| `alert-info` · `alert-success` · `alert-warning` · `alert-error` | `st.info` · `st.success` · `st.warning` · `st.error` | Rendu natif, une icône Material au plus, aucun emoji. |
| `chat-message` | `st.chat_message` | Réponse, puis ligne de métadonnées en `{typography.caption}`. |
| `sources-expander` | `st.expander` | Natif. |
| `model-select` | `st.selectbox` / `st.multiselect` | Options en texte seul, sans emoji. |
| `tool-pills` | `st.pills` | Sélection en `{colors.primary}`. |
| `progress-status` | `st.status` · `st.spinner` · `st.progress` | Texte sans emoji. |
| `chart` | `st.plotly_chart` et natifs | Palette du thème actif ; unité dans le titre d'axe. |
| `logo` | `st.logo` | Wordmark texte « WaveLocalAI » en `{colors.ink}` pour la nuit ; l'ajout du SVG Wavestone se décide au matin. |

## Do's and Don'ts

| À faire | À éviter |
|---|---|
| Couleurs, police et rayon dans `.streamlit/config.toml` | Hex en dur, `<style>`, `unsafe_allow_html` pour colorer |
| `{colors.primary}` pour l'action principale | Rouge sur une action principale (« FIGHT ! ») |
| `{colors.risk}` pour le risque, nommé par un texte | CO₂ coloré vert/orange/rouge selon un seuil |
| `{colors.accent-green}` en aplat sous de l'encre, ou en sombre | Vert de la charte en texte sur blanc |
| Icônes `:material/…:`, distinctes par module | Emojis en icône, doublés (« 📂 📂 ») ou en titre |
| `toolbarMode = "viewer"` | Barre « Deploy » visible en démo |
| Polices servies localement | Google Fonts ou tout CDN |
