---
name: WaveLocalAI
status: final
updated: 2026-09-27
sources:
  - docs/audits/frontend-2026-09/SYNTHESE.md
  - docs/audits/frontend-2026-09/poste-rtx3060/UX.md
---

# WaveLocalAI — Experience Spine

## Foundation

- **Forme :** application web de bureau, affichée sur grand écran ou vidéoprojecteur ; thème clair par défaut, sombre disponible.
- **Système d'interface :** Streamlit 1.x, composants natifs, navigation `st.navigation` / `st.Page`. Ce document ne spécifie que le comportement ajouté aux composants natifs.
- **Référence visuelle :** `DESIGN.md`, cité par chemin de token (par exemple `{colors.primary}`).
- **Portée :** front de la v1 (thème, lexique, états, confirmations) ; ni nouvelle fonction d'agent, ni nouveau format d'import, ni refonte de l'architecture des pages.
- **Validation :** implémentation autonome de nuit, validation visuelle au matin en clair et en sombre (D4). Tout `[ASSUMPTION]` s'applique tel quel la nuit et se valide au matin.

## Information Architecture

Chaque module porte **un seul nom**, identique dans le menu, sur l'accueil, en `st.title` et dans l'onglet du navigateur. Ordre du menu et de l'accueil : celui du tableau.

| Surface | Nom unique (remplace) | Icône `[ASSUMPTION]` | Onglets ou modes | Rôle |
|---|---|---|---|---|
| Accueil | « Accueil » ; onglet du navigateur « WaveLocalAI » | `home` | — | Dire si le système est disponible, en Local ou en Cloud, et mener à la démo recommandée |
| Arène des modèles | Inference Arena, Inférence & Arena, Inférence & Model Arena | `leaderboard` | `[ASSUMPTION]` « Chat libre » · « Banc d'essai » · « Arène » · « Gestion des modèles » | Converser, tester un scénario, comparer, installer des modèles |
| Assistant documentaire | RAG Knowledge, Base de Connaissance (RAG), RAG Knowledge Base | `description` | « Discussion » · `[ASSUMPTION]` « Évaluation de la qualité » | Interroger ses documents et voir les sources |
| Agents autonomes | Agent Lab, Agents Autonomes | `smart_toy` | `[ASSUMPTION]` modes « Agent seul » · « Équipe d'agents » | Confier une tâche outillée à un agent ou à une équipe |
| Sobriété et matériel | Socle Hardware, Cockpit GreenOps (& Hardware) | `eco` | Sections « Santé du système » · « Empreinte carbone » · « Carte d'identité technique » | Montrer la machine, sa charge et les émissions mesurées |

**Accueil — liste hiérarchisée.**

1. En-tête : `logo`, titre « WaveLocalAI », accroche « Le démonstrateur d'IA générative souveraine, frugale et sécurisée ».
2. Bandeau d'état en `metric` : Système (« Disponible » / « Indisponible »), Mode (`badge-local` ou `badge-cloud`), Processeur (%), Mémoire (Go utilisés / Go totaux).
3. Modules, sans numérotation : « Arène des modèles » en tête, marquée « Démo recommandée » ; puis les trois autres, chacun avec une phrase sans jargon qui dit ce qu'il prouve.
4. Pied de page : année courante et version réelle de l'application, ou rien.

**Contrôle Local/Cloud unique.** Un seul `cloud-toggle`, `[ASSUMPTION]` libellé « Autoriser le cloud », une seule clé de session, dans la barre latérale commune à toutes les pages. Les copies du pied de l'accueil et des barres latérales de page disparaissent.

## Voice and Tone

Microcopie ; la posture de marque vit dans `DESIGN.md` (Brand & Style).

- `[ASSUMPTION]` Français, casse de phrase, sans *Title Case* ni majuscules d'insistance (« VOS sources »).
- Guillemets « », espace insécable avant « : ; ! ? % » et entre un nombre et son unité.
- Une action garde le même verbe dans le bouton, le titre du dialogue et le message de résultat.
- Boutons : infinitif + objet, sans point d'exclamation ni emoji.
- Pluriels accordés au nombre affiché (« 1 extrait ajouté », « 3 sources utilisées »).
- Noms techniques (LangGraph, CrewAI, HyDE, Top-K, Ragas) en aide contextuelle (`help=`) seulement.

**Lexique** (`[ASSUMPTION]` = appliqué la nuit, validé au matin).

| Au lieu de | Écrire |
|---|---|
| chunks, chunks indexés | `[ASSUMPTION]` extraits, documents indexés |
| Solo (LangGraph) / Crew (Multi-Agent) | `[ASSUMPTION]` Agent seul / Équipe d'agents |
| Labo de tests | `[ASSUMPTION]` Banc d'essai |
| Benchmark & Qualité | `[ASSUMPTION]` Évaluation de la qualité |
| Time · Calculator · Wavestone Search · Email Sender · Data Analyzer · Document Generator · Chart Generator · Markdown Report · System Monitor | `[ASSUMPTION]` Heure · Calculatrice · Recherche interne Wavestone · Envoi d'email · Analyse de données · Génération de document · Génération de graphique · Rapport Markdown · Moniteur système |
| Activer Cloud (Mistral) · Autoriser les API Cloud (Mistral/OpenAI) · Mode Hybride | `[ASSUMPTION]` Autoriser le cloud |
| Opérationnel 🟢 | Disponible / Indisponible |
| Accélérateur AI · Tracking Actif | `[ASSUMPTION]` Accélérateur IA · Suivi carbone actif |
| ⚔️ FIGHT ! · 🚀 Lancer le Test | `[ASSUMPTION]` Lancer la comparaison · Lancer le test |
| Tout supprimer (Reset) | `[ASSUMPTION]` Vider la base documentaire |
| 🗑️ · 🗑️ Reset Chat | `[ASSUMPTION]` Effacer la conversation |
| 📥 | `[ASSUMPTION]` Télécharger |
| Scénario Prédéfini · Entrée Utilisateur | Scénario prédéfini · entrée utilisateur |
| GB | Go |

| À faire | À éviter |
|---|---|
| « 12 extraits ajoutés depuis 1 document. » | « ✅ Indexation terminée avec succès ! » |
| « Délai dépassé pour ce modèle. Les autres continuent. » | `'NoneType' object has no attribute 'output_tokens'` |
| « Ollama ne répond pas. Démarrez-le, puis rechargez la page. » | « Opérationnel 🟢 » écrit en dur |
| `[ASSUMPTION]` « Bonjour ! L'agent est prêt. » (seule exclamation tolérée) | « 🧹 Mémoire libérée ! » |

## Souveraineté visible

D1 et D2 priment sur toute autre règle d'affichage.

- **Local à chaque démarrage**, même si une clé d'API est présente. Passer en Cloud est un geste explicite sur `cloud-toggle`, dont l'aide (`help=`) dit que les données envoyées aux modèles cloud quittent la machine.
- **Cloud désactivé = aucun modèle cloud proposé** dans aucun `model-select`.
- **Badge partout.** `badge-local` ou `badge-cloud`, dérivé du fournisseur réel du modèle, accompagne : chaque option de `model-select` (en texte « · Local » / « · Cloud »), le modèle sélectionné, chaque `chat-message` de réponse, chaque ligne et chaque point des résultats de l'Arène, l'indicateur Mode de l'accueil, la section « Santé du système ». `[ASSUMPTION]` L'état du contrôle global reste lisible à tout moment par ce badge.
- **Tri :** modèles locaux d'abord, par règle explicite, jamais par l'ordre alphabétique du libellé.
- **Jamais dans un delta :** « Hybride », « API Active », « 100 % Local » ne vont pas dans le `delta` d'un `metric`.
- **Email (D2).** « Envoi d'email » décoché par défaut. Coché, l'agent prépare le message ; `confirm-dialog` montre destinataire, objet et corps ; rien ne part sans « Envoyer l'email ». Sans SMTP configuré, la pastille reste visible, non sélectionnable, avec une aide qui dit ce qui manque.

## Chiffres

| Grandeur | Règle |
|---|---|
| Format | `[ASSUMPTION]` `fr-FR` (8,1 %, 0,66 s, 13,8 Go, 26 sept. 2026) : virgule décimale, espace fine insécable des milliers, au plus trois chiffres significatifs. |
| Débit (D3) | « Débit » = `eval_count / eval_duration` d'Ollama, en « tokens/s », comparable à `scripts/benchmark_slm.py`. « Chargement » et « Durée totale » s'affichent à part. |
| CO₂ | « CO₂ » avec l'indice ; mg sous 1 g, g au-delà, kg au-delà de 1 000 g ; une seule unité dans une même comparaison. Conversion depuis les grammes du suivi explicite et testée. Couleur `{colors.ink}` : jamais de code couleur par seuil. |
| Mémoire | Go, jamais GB. |
| Durées | « 0,66 s » ; au-delà de 60 s, « 1 min 12 s ». |
| Dates et heures | « 26 sept. 2026 », « 09:15 ». Sur un axe, si la locale française exige un CDN, format numérique (« 26/09 09:15 »), jamais « Sep 26 ». |
| Scores | Une seule échelle, /100, axes compris. Évaluation impossible = « non évalué », jamais 0/100. |
| Juge de l'Arène | Par défaut, le plus gros modèle local qui tient en mémoire ; sous ~4B, `alert-warning` « note peu fiable ». |
| Deltas | Seulement une variation chiffrée dont la flèche dit vrai ; toute étiquette va en légende ou en badge. |
| Graphiques | Titre qui dit ce qui est tracé (« Émissions par session », pas « Cumul » pour une courbe qui redescend) ; historique en vrai cumul ou en barres par session, en mg, trous de mesure visibles, fenêtre de temps ; légende de taille quand la taille encode une valeur ; noms de modèles complets ; vue tableau à côté de la matrice de l'Arène ; pas d'axe resserré sur un seul point. |

## Component Patterns

Comportement ; le rendu vit dans `DESIGN.md` (Components).

| Composant | Où | Règles |
|---|---|---|
| `button-primary` | Partout | Une action principale par zone. Désactivé tant qu'un prérequis manque, avec une légende qui le nomme. |
| `button-secondary` | Partout | Actions réversibles : Effacer la conversation, Rafraîchir, Libérer la mémoire, Télécharger. Aucune confirmation. |
| `button-destructive` | Assistant documentaire | N'agit jamais au premier clic : ouvre `confirm-dialog`. |
| `confirm-dialog` | Vider la base documentaire, Envoi d'email | Nomme la conséquence chiffrée (« 42 extraits de 3 documents seront supprimés »). « Annuler » ferme sans effet ; la confirmation se solde par un `alert-success` au même verbe. |
| `metric` | Accueil, Sobriété et matériel, résultats | Valeur calculée à chaque affichage, jamais écrite en dur ; unité dans la valeur ; définition en `help=`. |
| `badge-local` · `badge-cloud` | Voir « Souveraineté visible » | Suit le fournisseur réel du modèle, pas le seul réglage global. |
| `cloud-toggle` | Barre latérale commune | Change l'état de toutes les pages sans rechargement manuel. |
| `card` | Accueil, états vides, actions rapides de l'agent | Regroupe un sujet ; jamais une grille de cartes identiques pour des éléments de poids différent. |
| `module-link` | Accueil | Libellé = nom exact du module. |
| `alert-info` · `alert-success` · `alert-warning` · `alert-error` | Partout | `alert-error` = ce qui a échoué + quoi faire ; trace technique dans un `st.expander` replié « Détails techniques ». Pas de succès annoncé avant l'aboutissement réel. |
| `chat-message` | Chat libre, Discussion, Agents autonomes | Métadonnées sous chaque réponse : badge, débit, CO₂, durée. La réponse et son CO₂ survivent aux reruns et aux changements de mode. Raisonnement dans un `st.expander` replié « Raisonnement ». |
| `sources-expander` | Discussion | Replié ; « N sources utilisées » ; chaque source : document, pertinence en `fr-FR`, extrait cité. |
| `model-select` | Pages à modèle | Défaut : modèle local le plus rapide qui tient en mémoire ; choix persistant entre onglets et modes ; Arène : au moins 2 modèles présélectionnés quand ils tiennent. |
| `tool-pills` | Agent seul | Neuf pastilles visibles ; toutes cochées sauf « Envoi d'email ». |
| `progress-status` | Chargement de modèle, Arène, ingestion, installation, équipe d'agents | Dit l'étape et le modèle concernés ; passe à `complete` ou `error` selon le résultat réel. |
| `chart` | Sobriété et matériel, Arène, Évaluation de la qualité | Voir « Chiffres ». Aucune donnée tracée entre deux mesures. |
| `logo` | Barre latérale | Statique, sans lien externe. |

## State Patterns

| État | Surface | Traitement |
|---|---|---|
| Base vide | Assistant documentaire | `card` « Votre base documentaire est vide », une phrase, `button-primary` « Importer des documents » (PDF, TXT, MD, DOCX). |
| Aucun message | Chat libre, Discussion | `st.chat_input` au placeholder explicite (« Posez une question à vos documents »), rien d'autre. |
| Accueil de l'agent | Agents autonomes | `[ASSUMPTION]` « Bonjour ! », une phrase, actions rapides en `card`. |
| Moins de 2 modèles | Arène | `button-primary` désactivé, légende « Choisissez au moins 2 modèles ». |
| Équipe sans agent | Équipe d'agents | Lancement désactivé, légende « Ajoutez au moins un agent ». |
| Aucun modèle installé | Sélecteurs | `alert-info` qui mène à « Gestion des modèles ». |
| Pas d'historique | Sobriété et matériel | « Aucune session mesurée pour l'instant. », pas de graphique vide. |
| Premier chargement lent | Toute inférence | `progress-status` immédiat « Chargement du modèle en mémoire… », qui prévient que le premier appel est plus long (8 à 26 s mesurés). |
| Génération en cours | Chat, Discussion, Agents | `progress-status` jusqu'à la réponse ou l'erreur ; le flux existant est conservé où il existe. |
| Installation d'un modèle | Gestion des modèles | `progress-status` avec nom et avancement ; échec = `alert-error` avec la raison, liste inchangée. |
| Délai dépassé | Chat, Banc d'essai, Arène | `alert-error` « Délai dépassé » avec le délai ; dans l'Arène, la ligne du modèle l'affiche, les autres continuent, le classement se fait sans lui. |
| Évaluation impossible | Arène, Évaluation de la qualité | « non évalué » avec la raison ; ni 0/100 ni podium. |
| Erreur d'ingestion | Assistant documentaire | `alert-error` par fichier en échec, avec la raison ; compteur inchangé pour ce fichier. |
| Ingestion réussie | Assistant documentaire | « N extraits ajoutés depuis M documents », compteur de documents indexés à jour. |
| Bloqué par le garde-fou mémoire | Agents autonomes et toute inférence gardée | Question conservée dans l'historique ; `alert-warning` : mémoire nécessaire estimée, mémoire libre, deux issues (modèle plus petit, libérer la mémoire). |
| Service indisponible | Accueil, puis chaque page | Ollama arrêté : Système « Indisponible » (`LLMProvider.health_check()`), `alert-error` en tête de module avec la marche à suivre. |
| Fournisseur cloud injoignable | Inférence en Cloud | `alert-error` qui nomme le fournisseur et propose de repasser en Local. |
| Accélérateur absent | Sobriété et matériel | « Aucun » ; « Actif » seulement si un accélérateur est réellement détecté. |
| Outil non configuré | Agent seul | Pastille non sélectionnable, aide « Configuration SMTP absente ». |

## Interaction Primitives

- **Confirmation** uniquement pour les actions externes ou irréversibles : vider la base documentaire, envoyer un email. Toujours par `confirm-dialog`. `[ASSUMPTION]` « Effacer la conversation » n'en demande pas : seule la session est vidée.
- **Défauts qui marchent sans rien toucher :** mode Local, modèle local le plus rapide qui tient en mémoire, juge = plus gros modèle local qui tient, Arène à 2 modèles au moins, « Envoi d'email » décoché.
- **Rien ne se perd :** saisies, choix de modèle et réponses survivent aux reruns et aux changements d'onglet ou de mode.
- **Réglages experts** (stratégie de recherche, nombre d'extraits, reranker, prompt système, température) dans un `st.expander` replié ; un réglage proposé agit réellement, sinon il est retiré.

## Accessibility Floor

- WCAG 2.2 AA en clair et en sombre : zéro violation axe-core `color-contrast` et `heading-order` sur les cinq pages (hors `region` et `aria-allowed-attr`, propres à Streamlit).
- Un seul h1 par page (le nom du module), puis h2/h3 sans saut ; aucun titre construit avec `st.markdown("# …")`, aucun emoji dans un titre.
- Tout bouton a un nom textuel ; l'aide au survol n'est pas un libellé.
- Icônes décoratives seulement ; aucune information portée par la seule couleur.
- Tout champ a un libellé, même masqué par `label_visibility="collapsed"`.

## Responsive & Platform

| Largeur | Exigence |
|---|---|
| ≥ 1440 px (poste, vidéoprojecteur) | Cible principale. `[ASSUMPTION]` Aucun libellé tronqué ; les neuf outils de l'agent visibles et lisibles. |
| 390 px | `[ASSUMPTION]` Priorité basse : aucun débordement horizontal ; champ de saisie atteignable sans parcourir toutes les cartes. |

## Inspiration & Anti-patterns

- **Repris des Web Interface Guidelines (Vercel) :** confirmation des actions externes ou irréversibles ; une action garde son nom tout au long du parcours.
- **Repris du skill `frontend-design` :** tokens avant le code, un seul élément signature.
- **Repris du skill `dataviz` :** palettes validées par script, unités et légendes explicites.
- **Rejeté :** l'allure « prototype Streamlit » (Source Sans, rouge `#FF4B4B`, emojis, barre « Deploy ») ; la grille de cartes identiques ; la numérotation « 01. / 02. » de modules qui ne sont pas une séquence ; le CSS injecté avec des couleurs en dur.

## Key Flows

### Flow 1 — Démo d'avant-vente (Claire, consultante senior Wavestone, devant le DSI d'un client)

Salle éclairée, portable de Claire relié au vidéoprojecteur. Le DSI veut savoir si un petit modèle local peut remplacer une API cloud pour son cas d'usage.

1. Claire ouvre WaveLocalAI : Système « Disponible », Mode `badge-local`, sans rien avoir réglé.
2. Elle suit « Arène des modèles », marquée « Démo recommandée ».
3. Onglet « Arène » : trois petits modèles locaux présélectionnés, chacun « · Local » ; juge = plus gros modèle local qui tient.
4. Elle saisit une question du métier du client et clique « Lancer la comparaison ».
5. « Chargement du modèle en mémoire… » : la salle comprend que l'attente est un chargement, pas une panne.
6. Résultats : tableau et matrice qualité/CO₂ avec légende de taille, noms complets, CO₂ en mg pour tous, débit en tokens/s, chargement à part.
7. **Climax :** le vainqueur est le plus petit des trois. Sa ligne montre son score sur /100, son CO₂ en mg et le `badge-local`. Claire se tourne vers le DSI : « Le meilleur des trois tourne ici, sur ce portable, et vos données n'en sont jamais sorties. » Tout ce qui le prouve est lisible du fond de la salle.

Échecs : un modèle dépasse le délai → « Délai dépassé » sur sa ligne, le classement vaut pour les deux autres. Le juge ne peut pas noter → « non évalué », Claire commente débit et CO₂. Ollama arrêté → l'accueil affiche « Indisponible » avant que le DSI voie une page cassée.

### Flow 2 — Atelier de formation interne (Léa, consultante junior, sur son portable sans GPU)

Karim anime ; chaque consultant manipule WaveLocalAI sur son poste (16 Go, sans GPU dédié). Consigne : interroger un document interne et vérifier d'où vient la réponse.

1. Léa ouvre « Assistant documentaire » : `card` « Votre base documentaire est vide », un bouton « Importer des documents ».
2. Elle importe la note de cadrage de l'atelier (`.docx`) ; `progress-status` suit le fichier.
3. « 14 extraits ajoutés depuis 1 document » ; le compteur passe à 1 document indexé.
4. Onglet « Discussion » : le modèle local le plus rapide qui tient sur son poste est choisi, `badge-local` à côté.
5. Elle pose sa question ; premier appel « Chargement du modèle en mémoire… », puis la réponse et ses métadonnées (Local, débit, CO₂, durée).
6. **Climax :** Léa ouvre « 3 sources utilisées » et retrouve mot pour mot le paragraphe de sa propre note qui fonde la réponse. Karim demande qui a retrouvé sa source : toute la salle lève la main.

Échecs : le fichier ne s'indexe pas → `alert-error` avec la raison, compteur inchangé. Le garde-fou mémoire bloque → la question reste, l'alerte chiffre le besoin et la mémoire libre et propose un modèle plus petit. « Vider la base documentaire » cliqué par erreur → `confirm-dialog` annonce les 14 extraits ; « Annuler » ne supprime rien.

## Open Questions

Non bloquantes pour la nuit ; à trancher dans `bmad-spec`.

1. **Mémoire affichée sous les réponses de la Discussion** (« 💾 0.0 GB », non investiguée) : la corriger ou la retirer ?
2. **Garde-fou mémoire avec un modèle déjà chargé dans Ollama** : le chiffre « nécessaire » de l'état bloqué doit être vrai avant d'être affiché.
