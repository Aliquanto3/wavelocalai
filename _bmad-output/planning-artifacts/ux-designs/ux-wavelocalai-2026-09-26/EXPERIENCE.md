---
name: WaveLocalAI
status: final
updated: 2026-10-19
sources:
  - docs/audits/frontend-2026-09/SYNTHESE.md
  - docs/audits/frontend-2026-09/poste-rtx3060/UX.md
  - docs/audits/refonte-2026-10/03-ux-front.md
  - _bmad-output/planning-artifacts/epics.md
  - _bmad-output/planning-artifacts/reports-v2-inventaire.md
  - docs/maquette-v2/README.md (maquette validée du front v2, décisions d'Anaël du 2026-10-18)
  - _bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md
---

# WaveLocalAI — Experience Spine

## Foundation

- **Forme :** application web de bureau, affichée sur grand écran ou vidéoprojecteur ; thème clair par défaut, sombre disponible (v2 : aussi « Système », voir « Coquille et écrans v2 du MVP »).
- **Système d'interface :** Streamlit 1.x, composants natifs, navigation `st.navigation` / `st.Page`. Ce document ne spécifie que le comportement ajouté aux composants natifs.
- **Référence visuelle :** `DESIGN.md`, cité par chemin de token (par exemple `{colors.primary}`).
- **Portée :** front de la v1 (thème, lexique, états, confirmations) ; ni nouvelle fonction d'agent, ni nouveau format d'import, ni refonte de l'architecture des pages.
- **Validation :** implémentation autonome de nuit, validation visuelle au matin en clair et en sombre (D4). Tout `[ASSUMPTION]` s'applique tel quel la nuit et se valide au matin.
- **v2 (`src/wavelocalai/`) :** web components servis par `web/`, coquille et barre haute de `03-ux-front.md` §3.3, composants de §3.4 (UX-DR1 à UX-DR25 d'`epics.md`). Lexique, voix, chiffres, souveraineté et états de ce document valent pour la v2 ; la section « Écrans v2 des Epics 5 à 7 » précise Sobriété, Modèles, Agents, Évaluation et Banc d'essai (UX-DR26 à UX-DR29). Les stories portent le contrat d'API ; ce document prime pour le comportement à l'écran.
- **Maquette v2 :** la maquette validée `docs/maquette-v2/` (`maquette-autonome.html`) est la référence visuelle et interactive de la v2. Les 43 décisions d'Anaël du 2026-10-18 (README de la maquette, §6, citées « D-n » ci-dessous) sont reportées dans ce document, dans `DESIGN.md`, dans `epics.md` et dans `contrat-api.md`. En cas d'écart entre la maquette et ces documents, les documents priment ; les écarts encore ouverts sont listés dans `sprint-change-proposal-2026-10-19.md`.

## Information Architecture

Chaque module porte **un seul nom**, identique dans le menu, sur l'accueil, en `st.title` et dans l'onglet du navigateur. Ordre du menu et de l'accueil : celui du tableau.

**v2 (D-10).** Le menu de la barre haute porte le nom court (Accueil, Arène, Documents, Agents, Sobriété, Modèles). Sur l'Accueil, chaque carte de module prend le nom court en titre et le nom long du tableau en sous-titre (« Documents » / « Assistant documentaire »). Le `h1` d'un écran est le nom de sa route (« Chat libre », « Base documentaire »…) ; celui de l'Accueil est « Accueil » (D-9).

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
| Scores | Notes de juge (Arène, Évaluation) : une seule échelle, /100, axes compris. Références du banc (`qb.results/1`) : pourcentage de réussite, libellé « Part de … » en tête de colonne ou de valeur (« Part de réussite 74 % ») (v2, D-5). Évaluation impossible = « non évalué », jamais 0/100 ni 0 %. |
| Juge de l'Arène | Par défaut, le plus gros modèle local qui tient en mémoire ; sous ~4B, `alert-warning` « note peu fiable ». |
| Deltas | Seulement une variation chiffrée dont la flèche dit vrai ; toute étiquette va en légende ou en badge. |
| Graphiques | Titre qui dit ce qui est tracé (« Émissions par session », pas « Cumul » pour une courbe qui redescend) ; historique en vrai cumul ou en barres par session, en mg, trous de mesure visibles, fenêtre de temps ; légende de taille quand la taille encode une valeur ; noms de modèles complets ; vue tableau à côté de la matrice de l'Arène ; pas d'axe resserré sur un seul point. |

## Component Patterns

Comportement ; le rendu vit dans `DESIGN.md` (Components).

| Composant | Où | Règles |
|---|---|---|
| `button-primary` | Partout | Une action principale par zone. Désactivé tant qu'un prérequis manque, avec une légende qui le nomme. |
| `button-secondary` | Partout | Actions réversibles : Effacer la conversation, Rafraîchir, Libérer la mémoire, Télécharger. Aucune confirmation. |
| `button-destructive` | Assistant documentaire, Modèles (v2) | N'agit jamais au premier clic : ouvre `confirm-dialog`. |
| `confirm-dialog` | Vider la base documentaire, Envoi d'email ; v2 : Supprimer un document (D-24), Supprimer un modèle | Nomme la conséquence chiffrée (« 42 extraits de 3 documents seront supprimés »). « Annuler » ferme sans effet ; la confirmation se solde par un `alert-success` au même verbe. |
| `metric` | Accueil, Sobriété et matériel, résultats | Valeur calculée à chaque affichage, jamais écrite en dur ; unité dans la valeur ; définition en `help=`. |
| `badge-local` · `badge-cloud` | Voir « Souveraineté visible » | Suit le fournisseur réel du modèle, pas le seul réglage global. |
| `cloud-toggle` | Barre latérale commune | Change l'état de toutes les pages sans rechargement manuel. |
| `card` | Accueil, états vides, actions rapides de l'agent | Regroupe un sujet ; jamais une grille de cartes identiques pour des éléments de poids différent. |
| `module-link` | Accueil | Libellé = nom exact du module. |
| `alert-info` · `alert-success` · `alert-warning` · `alert-error` | Partout | `alert-error` = ce qui a échoué + quoi faire ; trace technique dans un `st.expander` replié « Détails techniques ». Pas de succès annoncé avant l'aboutissement réel. |
| `chat-message` | Chat libre, Discussion, Agents autonomes | Métadonnées sous chaque réponse : badge, débit, CO₂, durée. La réponse et son CO₂ survivent aux reruns et aux changements de mode. Raisonnement dans un `st.expander` replié « Raisonnement ». |
| `sources-expander` | Discussion | Replié ; « N sources utilisées » ; chaque source : document, pertinence en `fr-FR`, extrait cité. |
| `model-select` | Pages à modèle | Défaut : modèle local le plus rapide qui tient en mémoire (v2 : défaut de l'usage rendu par `GET /api/models/defaults`, règle de `contrat-api.md`) ; choix persistant entre onglets et modes ; Arène : au moins 2 modèles présélectionnés quand ils tiennent. |
| `tool-pills` | Agent seul | Neuf pastilles visibles ; toutes cochées sauf « Envoi d'email ». v2 (D-6) : neuf interrupteurs en bascule (`role="switch"`), même règle. |
| Interrupteur (v2, D-6) | Partout | Toute option binaire est une bascule visuelle comme « Autoriser le cloud » (`<input type="checkbox" role="switch">`) : Mode projection, Format imposé, Réponse concise, outils de l'agent. Jamais une case à cocher nue ni des segments Oui / Non. |
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
| Erreur d'ingestion | Assistant documentaire | `alert-error` par fichier en échec, avec la raison ; compteur inchangé pour ce fichier. v2 (D-26) : le document en échec figure aussi dans le tableau des documents, statut « Échec » avec sa raison, et garde « Supprimer ». |
| Ingestion réussie | Assistant documentaire | « N extraits ajoutés depuis M documents », compteur de documents indexés à jour. |
| Bloqué par le garde-fou mémoire | Agents autonomes et toute inférence gardée | Question conservée dans l'historique ; `alert-warning` : mémoire nécessaire estimée, mémoire libre, deux issues (modèle plus petit, libérer la mémoire). |
| Service indisponible | Accueil, puis chaque page | Ollama arrêté : Système « Indisponible » (`LLMProvider.health_check()`), `alert-error` en tête de module avec la marche à suivre. |
| Fournisseur cloud injoignable | Inférence en Cloud | `alert-error` qui nomme le fournisseur et propose de repasser en Local. |
| Accélérateur absent | Sobriété et matériel | « Aucun » ; « Actif » seulement si un accélérateur est réellement détecté. |
| Outil non configuré | Agent seul | Pastille non sélectionnable, aide « Configuration SMTP absente ». |

## Interaction Primitives

- **Confirmation** uniquement pour les actions externes ou irréversibles : vider la base documentaire, envoyer un email ; en v2, aussi supprimer un document (D-24) et supprimer un modèle. Toujours par `confirm-dialog`. `[ASSUMPTION]` « Effacer la conversation » n'en demande pas : seule la session est vidée.
- **Défauts qui marchent sans rien toucher :** mode Local, modèle local le plus rapide qui tient en mémoire (v2 : défaut de l'usage selon `contrat-api.md`), juge = plus gros modèle local qui tient, Arène à 2 modèles au moins, « Envoi d'email » décoché.
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

## Coquille et écrans v2 du MVP (maquette validée)

Comportements fixés par la maquette `docs/maquette-v2/` et les décisions d'Anaël du 2026-10-18 (D-n), pour la coquille et les écrans des Epics 1 à 4 et l'écran Références. Ils complètent UX-DR1 à UX-DR25 d'`epics.md` et `03-ux-front.md` §3, et priment sur eux en cas d'écart.

### Coquille

| Sujet | Comportement |
|---|---|
| Menu Affichage | Thème « Clair » (défaut), « Sombre », « Système » (suit `prefers-color-scheme`, et ses changements en direct) (D-7) ; « Mode projection » en interrupteur (D-6). Choix gardés dans `localStorage`. |
| Routes | Les routes d'UX-DR4, dont celles ajoutées par la maquette : `#/arene/references` (quatrième onglet de l'Arène, D-8), `#/arene/banc/<run_id>`, `#/documents/evaluation/<run_id>`, `#/agents/equipe/<run_id>` et `#/modeles/<tag>`. Un résultat rouvert par une adresse inconnue (identifiant qui n'existe pas) affiche l'erreur `run_not_found` (« Résultat introuvable : ce résultat n'existe pas ou a été effacé. ») avec un lien vers une nouvelle exécution. |
| Icônes | Material Symbols Rounded officiels, sous-ensemble en sprite avec sa licence (D-2). Les tracés Material Icons (Filled) restent propres à la maquette. |
| Erreurs | Les boutons d'action d'une erreur sont déduits du code et de `detail` par le front (catalogue côté front) ; l'enveloppe du serveur n'en porte pas (D-4, AD-18). |
| Exports | Deux boutons (« Télécharger en JSON » et « Télécharger en Markdown » au Chat, « Exporter en CSV » et « Exporter en Markdown » à l'Arène) ; sous 768 px, un seul bouton « Exporter » qui ouvre un menu des formats (D-3). Le téléchargement suit la route d'export du serveur, jamais un `blob:`. |

### Accueil (`#/`)

- `h1` « Accueil » (D-9), puis l'accroche.
- Cartes de module : nom court en titre, nom long en sous-titre, puis la phrase de résumé (D-10). La carte « Références » (D-8) affiche son meilleur score en pourcentage avec le libellé « Part de … » en tête (D-5).
- « Lancer une comparaison » reste actif même sans modèle local prêt : l'Arène dit alors quoi faire (installer un modèle, ou autoriser le cloud) (D-11).

### Chat libre (`#/arene/chat`)

- Créativité par défaut : la valeur `default_temperature` rendue par le serveur avec le modèle choisi ; sans valeur, 0,2 (D-12). Changer de modèle remet le curseur au défaut du nouveau modèle tant que la personne ne l'a pas déplacé.
- Pendant `model_loading`, `wl-run-status` ajoute « Le premier appel charge le modèle en mémoire : de 8 à 26 secondes. » (état « Premier chargement lent »).
- Un `409 run_busy` rejoint le run actif et laisse le message tapé dans le champ (D-13).
- Exports : voir « Coquille » (D-3). Effacer et Télécharger sont masqués quand la conversation est vide, désactivés pendant une réponse avec la raison en légende.

### Arène (`#/arene/comparer[/<run_id>]`)

- Pendant l'exécution, la configuration est remplacée par un résumé (question, modèles, juge) ; « Modifier la question » la rouvre à la fin (D-16).
- Dès 1 440 px avec 4 modèles : 4 colonnes, la réponse de chaque colonne repliée sur 4 lignes, dépliable par « Afficher toute la réponse » (D-15).
- Après une comparaison : la matrice qualité/CO₂ d'abord, le tableau derrière « Voir le tableau » (segments « Matrice · Tableau », Matrice choisie par défaut) (D-14).
- Bouton « Lancer la comparaison » désactivé avec sa raison visible : « Choisissez au moins 2 modèles », « Choisissez 4 modèles au plus », « Saisissez une question », « Choisissez un juge ».
- Sans modèle local prêt (arrivée depuis l'Accueil, D-11) : `alert-info` qui dit quoi faire (installer un modèle depuis Modèles, ou autoriser le cloud), lancement désactivé avec la raison.

### Références (`#/arene/references`)

- Cartes par usage par défaut, segments « Cartes · Tableau » (D-20).
- Scores en pourcentage de réussite, libellé « Part de … » en tête (D-5) ; un groupe à égalité, désigné par le serveur, n'a pas de rang et se trie par nom.
- « Comparer ces modèles » sur une carte ouvre l'Arène présélectionnée sur les modèles du groupe installés sur ce poste (D-19) ; sans modèle installé du groupe, le bouton est désactivé avec la raison.
- Ollama arrêté : les références restent lisibles ; les marques « installé » sont retirées, avec un message qui le dit.

### Discussion (`#/documents`)

- Chaque source surligne le passage `passage {start, end}` renvoyé par le serveur dans l'événement `sources` ; sans `passage`, l'extrait entier s'affiche sans surlignage (D-21).
- Dès 1 024 px, le panneau des sources est toujours ouvert, sans bouton de repli ; en deçà, il passe sous la réponse, replié (D-22).
- Plusieurs réponses, un seul panneau : dès la deuxième réponse, chaque réponse porte « Afficher les sources », qui charge ses sources dans le panneau (D-23).

### Base documentaire (`#/documents/base`)

- Un seul bouton « Annuler l'import » au-dessus des lignes de progression : il annule le lot (le run `ingest`) ; les documents déjà prêts restent (D-25).
- Un document en échec figure aussi dans le tableau, statut « Échec » avec sa raison, et garde « Supprimer » ; il ne compte pas dans le nombre de documents indexés (D-26).
- « Supprimer » ouvre `wl-confirm-dialog` comme « Vider » : titre « Supprimer « note-cadrage.docx » ? », conséquence « 14 extraits seront retirés de la base. Cette action est irréversible. » (pour un document en échec : « Ce document n'a pas été indexé : aucun extrait n'est retiré. »), focus sur « Annuler », issue « Document supprimé : note-cadrage.docx. 14 extraits retirés de la base. » ; « Annuler » annonce « Suppression annulée » (D-24).

## Écrans v2 des Epics 5 à 7

Précise UX-DR26 à UX-DR29 à partir des maquettes de `03-ux-front.md` §3.5. Rendu des nouveaux composants : `DESIGN.md`, « Composants de la v2 ». Chaque écran passe axe-core sans violation, clair et sombre (UX-DR25).

### Règles communes

| Règle | Comportement |
|---|---|
| Panneau latéral (`wl-side-panel`) | Un seul ouvert à la fois. À l'ouverture, focus sur son `h2` ; « Fermer » et Échap le ferment et rendent le focus au déclencheur. À droite dès 1 024 px, sous le contenu et replié en deçà (UX-DR19). Exceptions fixées par la maquette : panneau des sources toujours ouvert en large (D-22) ; fiche modèle à droite dès 1 120 px, au-dessus de la liste en deçà (D-40) ; « Configurer l'équipe » non modal, qui laisse le schéma visible (D-35) ; panneau « Étapes » de l'agent toujours déplié (D-30). |
| Mises à jour en direct | Valeurs remplacées sur place, sans animation ni `aria-live` (une annonce toutes les 2 s rendrait le lecteur d'écran inutilisable). Seules les fins d'action sont annoncées, en `polite`. |
| Segments (« 7 jours · 30 jours · Tout », « Graphique · Tableau », « Matrice · Tableau », « Cartes · Tableau », « Question · Jeu de questions ») | `radiogroup`, flèches pour changer, segment choisi en `wl-pill-selected`. Le choix tient pour la session de la page. |
| Action longue | `wl-run-status` avec étape nommée, chronomètre et « Arrêter » (Échap si aucun panneau ni dialogue n'est ouvert). Quitter l'écran puis revenir reprend le flux par `?after=`. |
| Résultat conservé | Un run terminé a son URL (`…/<run_id>`) et se reconstruit depuis la base sans relancer de modèle. Adresse inconnue : erreur `run_not_found` avec un lien pour lancer une nouvelle exécution (l'affichage d'un résultat effacé reste à trancher). |
| Bouton désactivé | Toujours avec la raison en légende visible, jamais en infobulle seule. |

### Sobriété et matériel (`#/sobriete`, UX-DR26)

Ordre de l'écran, de haut en bas :

| Zone | Contenu | Comportement |
|---|---|---|
| `h1` « Sobriété et matériel » | — | — |
| `h2` « Santé du système » | Quatre `wl-metric` : « Processeur » (34 %), « Mémoire » (9,8 / 15,7 Go), « Accélérateur » (nom et mémoire GPU « 2,1 / 6 Go », ou « Aucun »), « Ollama » (« 2 modèles chargés », noms en aide) | Mis à jour par le flux système toutes les 2 s, en pause quand l'onglet est masqué ; au retour, les dernières valeurs restent affichées jusqu'au premier échantillon. Avec NVML, une ligne de texte sous l'accélérateur : « 62 °C » et, s'il y a lieu, « Bridage thermique en cours ». Ollama arrêté : « Ollama ne répond pas » et l'action « Réessayer » de la barre haute. |
| `h2` « Empreinte carbone de cette session » | Total en `metric-value` ; ligne « Par module » (Chat libre, Arène, Discussion, Agents, Import de documents ; modules à 0 omis) ; ligne « Local 398 mg · Cloud 14 mg (estimé) · 3 réponses non mesurables » | Suit `carbon_updated` sans clic. « non mesurables » est un lien qui déplie « Comment ces chiffres sont calculés ». Une seule unité pour toute la section (UX-DR15). En-tête de section : `button-secondary` « Remettre le compteur à zéro », sans confirmation (la session close reste dans l'historique) ; annonce « Compteur remis à zéro. La session précédente est dans l'historique. » |
| `h2` « Historique » | Segments « 7 jours » (par défaut), « 30 jours », « Tout » ; segments « Graphique » (par défaut) et « Tableau » | Graphique : barres « Émissions par session », une barre par session, début de session en abscisse, mg en ordonnée ; une session sans mesure garde sa place, marquée « non mesuré » sans barre. Tableau : début, fin, total, Local, Cloud, non mesurables, triable. Vide : « Aucune session mesurée pour l'instant. » sans graphique. La session en cours n'y figure qu'une fois close ; une phrase le dit sous le graphique : « La session en cours n'apparaît qu'une fois close. » (D-37). Sous 640 px, « Tableau » est choisi par défaut (D-39). Graphique et tableau en mg seulement. |
| `details` « Carte d'identité technique » | Fiche machine (processeur, mémoire, accélérateur, système), version d'Ollama, version de WaveLocalAI | Replié. |
| `details` « Comment ces chiffres sont calculés » | CodeCarbon pour le local, ecologits pour le cloud (« estimé »), règle D3 du débit, ce qui rend une réponse non mesurable ; équivalence parlante (D-38) | Replié ; s'ouvre aussi par le lien « non mesurables ». Équivalence, seulement ici : « Pour se représenter l'ordre de grandeur : 412 mg correspondent à environ 3,7 m parcourus en voiture (facteur : N g de CO₂ par km ; source : … ). » Facteur et source viennent du serveur (réglage daté de `wavelocalai.toml`, source publique citée), jamais d'une valeur en dur dans le front. |

Aucune couleur selon un seuil de CO₂ ; la section ne porte pas de jugement (« bon », « élevé ») ; l'équivalence ne sort pas du panneau de méthode (D-38).

### Modèles (`#/modeles`, `#/modeles/<tag>`, UX-DR27)

| Zone | Contenu | Comportement |
|---|---|---|
| `h1` « Modèles », barre d'actions | « Décharger les modèles inactifs » (`button-secondary`) ; champ « Installer un modèle par son nom » + « Installer » | Décharger : la colonne « Chargé » et la mémoire libre suivent le flux système ; annonce « 2 modèles déchargés. » |
| `h2` « Sur ce poste » | `wl-data-table` : Nom (bouton qui ouvre la fiche), Origine (`wl-badge`), Usage (Conversation, Représentation, Reclassement), Paramètres (« 8 B · 1 B actifs »), Taille, Tient en mémoire, Chargé, Débit sur ce poste, Actions (« Supprimer ») | Tri initial : chargés d'abord, puis par nom. « Tient en mémoire » : « Oui », « Non : il manque 1,2 Go » ou « inconnu ». Débit absent : « non mesuré ». Supprimer : voir « Confirmation » ci-dessous. Sous 1 024 px, les colonnes Usage et Origine sont repliées ; un bouton au-dessus du tableau les affiche (D-43). Aucun modèle : « Aucun modèle installé sur ce poste. Installez-en un depuis le catalogue ci-dessous. » |
| `h2` « Modèles proposés par défaut » (décision Q2) | Une ligne par usage : Conversation, Arène, Juge, Agent, Documents ; Modèle (avec badge), Raison, actions | « Changer » remplace la cellule Modèle par `wl-model-picker` filtré sur les modèles éligibles à l'usage, puis « Enregistrer » ou « Annuler ». « Revenir au choix automatique » n'apparaît que si la raison est « Choisi par vous ». Un défaut cloud choisi s'affiche avec « inactif tant que le cloud n'est pas autorisé ». Sans modèle éligible : « Aucun », la raison donne les conditions. |
| `h2` « Catalogue installable » | `wl-data-table` : Nom, Paramètres, Mémoire nécessaire, Tient en mémoire, « Installer » | `[ASSUMPTION]` Tri initial : ceux qui tiennent d'abord, puis par mémoire nécessaire croissante. Un modèle qui ne tient pas reste installable : son bouton devient « Installer quand même » (nom accessible « Installer qwen3.6:14b quand même : il ne tient pas dans la mémoire libre »), et sa ligne dit « Ne tient pas : 6,1 Go nécessaires, 4,8 Go libres » (D-42). Un modèle supprimé du poste revient dans ce catalogue. |
| `h2` « Reclassement des extraits » | Une ligne : état (« Installé », « Non installé » avec la raison), « Installer le reranker » | Sans l'option `rerank` : bouton désactivé, légende « Installez l'option de reclassement : `uv sync --extra rerank` ». |
| Panneau « Fiche du modèle » | Voir ci-dessous | Ouvert par un nom de modèle ou par `#/modeles/<tag>` ; la liste reste visible. À droite dès 1 120 px, au-dessus de la liste en deçà (D-40). |

**Installation.** La cellule d'action de la ligne devient `wl-progress-bytes` + « Annuler » : « Préparation… », « Téléchargement 1,2 Go sur 4,7 Go · 26 % », « Vérification… », puis « Installé » et la ligne rejoint « Sur ce poste ». Pendant ce temps, les autres « Installer » sont désactivés avec « Une installation est en cours (qwen3.5:2b). » Seule la fin est annoncée (« qwen3.5:2b installé. » ou l'erreur). Échec ou annulation : `wl-error` dans la ligne (code `pull_failed`, message, action), liste inchangée.

**Confirmation.** « Supprimer » ouvre `wl-confirm-dialog` : titre « Supprimer qwen3.5:2b ? », conséquence « qwen3.5:2b sera supprimé de ce poste (2,7 Go libérés). », focus sur « Annuler », bouton « Supprimer le modèle » ; issue annoncée « Modèle supprimé ». Si le modèle est un défaut choisi pour un ou plusieurs usages, le dialogue l'ajoute à la conséquence : « C'est le modèle par défaut pour : Agent. Ces usages reviendront à la règle automatique. » (D-41). Un modèle utilisé par un run actif : bouton désactivé, légende « Utilisé par une réponse en cours » ; côté serveur, `409 model_in_use`.

Les boutons « Installer » ont aussi la forme « Installer quand même » dans la fiche d'un modèle qui ne tient pas (D-42).

**Fiche du modèle.** `h2` = nom complet, badge d'origine, puis :

- liste de définitions « Caractéristiques » : architecture (« Dense » ou « MoE »), paramètres totaux et actifs, quantification, contexte, licence, outils vérifiés, raisonnement vérifié ; valeur absente « inconnu », jamais 0 ;
- `details` « Pourquoi ce débit ? » : débit mesuré sur ce poste, puis l'explication par les paramètres actifs, la quantification, la bande passante mémoire et la VRAM, en phrases fournies par l'API ;
- `details` « Sur d'autres postes » : tableau des trois postes de référence (poste, débit, tient en mémoire, énergie si mesurée), source et date de la publication du banc ; mention « autre version » si le digest diffère ; références indisponibles : la raison, sans tableau vide.

`[ASSUMPTION]` Depuis `wl-model-picker`, un bouton « Fiche du modèle » à côté du champ (pas dans la liste d'options, où un contrôle interactif est interdit) ouvre la même fiche en panneau sur l'écran courant, sans changer d'URL.

### Agents autonomes : Agent seul (`#/agents/seul`, UX-DR28)

| Zone | Contenu | Comportement |
|---|---|---|
| `h1` « Agents autonomes », sous-navigation « Agent seul » · « Équipe d'agents » | — | Liens vers les deux routes, comme les sous-écrans de l'Arène. |
| Réglages | `wl-model-picker` sur le défaut `agent` avec sa raison ; groupe « Outils de l'agent » : neuf interrupteurs en bascule (D-6) | Tous activés sauf « Envoi d'email ». Un outil indisponible n'est pas activable (`aria-disabled`, focalisable) et garde sa raison en légende (« Configuration SMTP absente : … »). Chaque outil a sa description en aide. Sans défaut : la raison et « Choisissez un modèle avec outils vérifiés », lancement désactivé. Modèle choisi sans outils vérifiés : avertissement « Ce modèle n'a pas d'outils vérifiés : l'agent risque de mal appeler ses outils. Préférez un modèle marqué « Outils vérifiés ». », lancement permis (D-32). |
| Fil | `wl-chat-thread` ; accueil : `card` « Bonjour ! L'agent est prêt. » + `[ASSUMPTION]` les actions rapides de la v1 | Une action rapide remplit la saisie sans l'envoyer. |
| Panneau « Étapes » | `wl-step-trace` + chronomètre | À droite dès 1 024 px ; en deçà, sous la réponse et **toujours déplié**, sans bouton de repli, pendant un run comme hors run (c'est le cœur de la démo, D-30). |
| Saisie collante | « Décrivez la tâche à confier à l'agent », « Envoyer », « Arrêter » | Entrée envoie, Maj+Entrée va à la ligne (comme le Chat libre). |

**Trace.** Chaque étape s'ajoute à la fin de la liste sans déplacer le focus ; on peut en déplier une pendant que les suivantes arrivent. Dépliée : « Arguments » (JSON mis en forme), « Résultat » (résumé, et « Ouvrir le fichier » quand l'outil a produit un fichier). L'étape en cours a le contour et le libellé « en cours ». `wl-run-status` annonce le changement d'étape (« Appel de l'outil Analyse de données… ») ; la liste elle-même n'est pas `aria-live`. Une erreur d'outil reste une étape « Résultat : erreur » avec son texte, et l'agent poursuit. Borne de tours atteinte : dernière étape « Arrêt : nombre d'étapes maximal atteint (12) ».

**Validation d'email (D2).** L'étape passe à « En attente de votre validation » et `wl-confirm-dialog` s'ouvre : titre « Envoyer cet email ? », Destinataire, Objet, Corps (lecture seule, défilable), mention « Sans réponse dans 10 min, l'envoi est refusé. », focus sur « Annuler », bouton « Envoyer l'email ». Échap vaut « Annuler ». Issues annoncées et inscrites dans la trace : « Email envoyé. », « Envoi annulé : l'agent en est informé. », « Validation expirée : email non envoyé. »

**Pied de réponse (D-31).** Pied réduit : badge, CO₂, « 4 étapes », durée ; ni débit, ni tokens, ni chargement (un débit agrégé sur plusieurs appels dit peu). « Télécharger » (Markdown, route d'export du serveur, sans `blob:`) suit le pied, comme une action. Garde-fou mémoire : l'état `ram_guard` d'`EXPERIENCE.md` (question gardée, besoin chiffré, deux issues).

### Agents autonomes : Équipe d'agents (`#/agents/equipe`, UX-DR28)

| Zone | Contenu | Comportement |
|---|---|---|
| Équipe | Liste « Équipe » (bibliothèque) ; « Configurer » ; si modifiée, badge « Modifiée » et « Revenir à l'équipe d'origine » | Revenir efface la modification sans confirmation, annonce « Équipe d'origine rétablie. » |
| Sujet | Champ « Sujet de la mission » | Requis ; vide, « Lancer la mission » est désactivé avec « Saisissez un sujet ». |
| Schéma | `wl-team-graph` : agents dans l'ordre, puis « Rapport » ; « Lancer la mission » | De gauche à droite dès 768 px jusqu'à 4 agents, de haut en bas en deçà de 768 px ou à 5 agents ; une équipe compte 5 agents au plus (D-36). `<desc>` lit l'ordre (« Chercheur, puis Analyste, puis Rédacteur, puis le rapport »). Non interactif. Sans agent : « Ajoutez au moins un agent ». |
| Suivi | Une ligne dépliable par agent : « En attente », « En cours · Analyse de données… », « Terminé · 3 outils · 41 s », « Arrêté », « Non lancé » (agent que la mission n'a pas atteint après un arrêt ou une erreur, D-34) ; `details` « Journal brut » replié, en lignes horaires lisibles (« 09:15:02 Chercheur · Appel de l'outil Recherche interne Wavestone »), jamais du JSON brut (D-33) ; « Arrêter » | Une ligne dépliée montre la `wl-step-trace` de l'agent. Le nœud du schéma suit la ligne en cours (contour et « en cours »). Les totaux « 3 outils · 41 s » viennent du serveur (`agent_totals`), pas d'un calcul du front. |
| Rapport | Markdown rendu, pied : badge, CO₂, pic de mémoire, durée, « Télécharger » | Mission arrêtée : titre « Rapport partiel (mission arrêtée) ». Rouvrable par son adresse `#/agents/equipe/<run_id>` (D-8). |

**Configurer.** Volet « Configurer l'équipe », **non modal** : il laisse le schéma visible et utilisable en lecture (colonne de droite dès 1 024 px, sous le schéma en deçà) (D-35). Un `fieldset` par agent (Rôle, Objectif, Outils en interrupteurs, Modèle par `wl-model-picker`), « Retirer cet agent », « Ajouter un agent », puis « Enregistrer » et « Annuler ». À 5 agents, « Ajouter un agent » est désactivé, avec la raison visible reliée au bouton : « Une équipe compte 5 agents au plus : retirez un agent pour en ajouter un autre. » (D-36). « Enregistrer » passe par la validation serveur : chaque erreur s'affiche sous son champ (`aria-describedby`) et le focus va à la première. « Annuler » abandonne les changements non enregistrés.

### Évaluation de la qualité (`#/documents/evaluation[/<run_id>]`, UX-DR29)

| Zone | Contenu | Comportement |
|---|---|---|
| Réglages | Segments « Question » · « Jeu de questions » ; champ ou liste du jeu ; « Modèles évalués » (`wl-model-picker` multi) ; « Juge » (défaut `judge` et sa raison, « note peu fiable » sous ~4B actifs) ; phrase « Les mêmes extraits sont fournis à tous les modèles. » ; « Lancer l'évaluation » | « Modèles évalués » présélectionne les modèles du défaut `arena` (les trois petits modèles locaux de l'Arène) (D-27). Base vide : désactivé, « Importez des documents pour évaluer », lien vers Base documentaire. Aucun modèle : « Choisissez au moins un modèle ». Question vide : désactivé, « Saisissez une question » (D-29). |
| `h2` « Étapes » | Liste ordonnée de trois étapes : « Recherche des extraits communs » (+ « Voir les extraits »), « Réponses » (état par modèle), « Notation : fidélité · pertinence · précision du contexte » | État en texte : « à venir », « en cours », « fait », « échec ». « Voir les extraits » ouvre `wl-source-panel`. |
| `h2` « Résultats » | Segments « Tableau » (par défaut) · « Matrice » ; tableau : Modèle, Fidélité, Pertinence, Précision du contexte, Débit, CO₂ | Les cellules se remplissent au fil de `eval_metric`, en « en cours » avant leur score. Chaque score est un bouton « 86/100 » qui ouvre le panneau « Détail ». Matrice : `wl-chart-svg`, fidélité × débit, CO₂ en taille. |
| Panneau « Détail » | Titre « Qwen 3.5 2B · Fidélité » ; « 7 affirmations : 6 appuyées, 1 non appuyée » ; liste des verdicts par affirmation avec l'extrait d'appui | Pertinence et précision : la raison du score en une phrase et les extraits jugés utiles. |

« non évalué » remplace le score dans la cellule, avec la raison en aide (« Juge indisponible », « Sortie du juge invalide », « Réponse vide »), jamais 0. Chaque en-tête de métrique a sa définition en aide : Fidélité « Part des affirmations de la réponse appuyées par les extraits. » ; Pertinence « Proximité entre la question posée et celles que la réponse permet de retrouver. » ; Précision du contexte « Part des extraits fournis qui servent à répondre. » La mention « Méthode inspirée de Ragas » est en aide seulement. `[ASSUMPTION]` Jeu de questions : une ligne par modèle, score moyen des questions évaluées, « sur 8 questions (1 non évaluée) » sous le score, détail par question dans le panneau.

**Évaluation arrêtée (D-28).** Une évaluation arrêtée (ou interrompue par un redémarrage) garde son résultat partiel : les scores déjà notés sont conservés, le reste affiche « non évalué (évaluation arrêtée) », jamais 0. Le résultat est rouvrable par son adresse, titré « Résultat partiel conservé », avec l'annonce « Évaluation arrêtée : résultats partiels. Ce qui n'était pas encore noté reste « non évalué », jamais 0. »

### Banc d'essai (`#/arene/banc[/<run_id>]`, UX-DR29)

| Zone | Contenu | Comportement |
|---|---|---|
| Scénario | Liste « Scénario » (scénarios de la v1, description d'une ligne) ; `details` « Consigne » replié (consigne système du scénario, en lecture seule, D-18) ; `details` « Format attendu » (champs, type, obligatoire, lus du schéma) ; « Entrée » préremplie par le scénario, modifiable | Changer de scénario remplace l'entrée seulement si elle n'a pas été modifiée ; sinon, « Remplacer par l'exemple du scénario » est proposé. Scénario sans format attendu : pas de « Format attendu », « Format imposé » désactivé avec la raison visible, et aucun verdict de format à la fin (D-17). |
| Réglages | `wl-model-picker` ; interrupteurs en bascule (D-6) « Format imposé » et « Réponse concise » ; « Lancer le test » | Aide de « Format imposé » : « Le schéma est transmis au modèle et contraint sa sortie. Désactivé, le format n'est demandé que dans la consigne. » Aide de « Réponse concise » : « Ajoute une consigne de réponse courte : moins de durée et de CO₂, parfois moins de détail. » `[ASSUMPTION]` Un modèle qui ne peut pas imposer de format rend l'interrupteur désactivé, avec la raison. |
| Résultat | Réponse en flux ; à la fin, verdict de format (lu dans l'instantané `GET /api/runs/{id}`, comme le verdict de l'Arène), « Sortie mise en forme » (JSON indenté), rangée `wl-metric` Débit, CO₂, Durée | Verdict en clair : « Format respecté » (`check_circle`) ou « Format non respecté : le champ « date » manque » (`cancel`) ; sortie non JSON : « Format non respecté : la sortie n'est pas du JSON valide. » Délai dépassé : « Délai dépassé (120 s) ». |

## Key Flows

### Flow 1 — Démo d'avant-vente (Claire, consultante senior Wavestone, devant le DSI d'un client)

Salle éclairée, portable de Claire relié au vidéoprojecteur. Le DSI veut savoir si un petit modèle local peut remplacer une API cloud pour son cas d'usage.

1. Claire ouvre WaveLocalAI : Système « Disponible », Mode `badge-local`, sans rien avoir réglé.
2. Elle suit « Arène des modèles », marquée « Démo recommandée ».
3. Onglet « Arène » : trois petits modèles locaux présélectionnés, chacun « · Local » ; juge = plus gros modèle local qui tient.
4. Elle saisit une question du métier du client et clique « Lancer la comparaison ».
5. « Chargement du modèle en mémoire… » : la salle comprend que l'attente est un chargement, pas une panne.
6. Résultats : matrice qualité/CO₂ d'abord (v2, D-14), tableau derrière « Voir le tableau », avec légende de taille, noms complets, CO₂ en mg pour tous, débit en tokens/s, chargement à part.
7. **Climax :** le vainqueur est le plus petit des trois. Sa ligne montre son score sur /100, son CO₂ en mg et le `badge-local`. Claire se tourne vers le DSI : « Le meilleur des trois tourne ici, sur ce portable, et vos données n'en sont jamais sorties. » Tout ce qui le prouve est lisible du fond de la salle.

Échecs : un modèle dépasse le délai → « Délai dépassé » sur sa ligne, le classement vaut pour les deux autres. Le juge ne peut pas noter → « non évalué », Claire commente débit et CO₂. Ollama arrêté → l'accueil affiche « Indisponible » avant que le DSI voie une page cassée.

### Flow 2 — Atelier de formation interne (Léa, consultante junior, sur son portable sans GPU)

Karim anime ; chaque consultant manipule WaveLocalAI sur son poste (16 Go, sans GPU dédié). Consigne : interroger un document interne et vérifier d'où vient la réponse.

1. Léa ouvre « Assistant documentaire » : `card` « Votre base documentaire est vide », un bouton « Importer des documents ».
2. Elle importe la note de cadrage de l'atelier (`.docx`) ; `progress-status` suit le fichier.
3. « 14 extraits ajoutés depuis 1 document » ; le compteur passe à 1 document indexé.
4. Onglet « Discussion » : le modèle local le plus rapide qui tient sur son poste est choisi (v2 : le défaut `rag` du contrat, avec sa raison), `badge-local` à côté.
5. Elle pose sa question ; premier appel « Chargement du modèle en mémoire… », puis la réponse et ses métadonnées (Local, débit, CO₂, durée).
6. **Climax :** Léa ouvre « 3 sources utilisées » (v2 : panneau toujours ouvert en large, passage surligné, D-21 et D-22) et retrouve mot pour mot le paragraphe de sa propre note qui fonde la réponse. Karim demande qui a retrouvé sa source : toute la salle lève la main.

Échecs : le fichier ne s'indexe pas → `alert-error` avec la raison, compteur inchangé. Le garde-fou mémoire bloque → la question reste, l'alerte chiffre le besoin et la mémoire libre et propose un modèle plus petit. « Vider la base documentaire » cliqué par erreur → `confirm-dialog` annonce les 14 extraits ; « Annuler » ne supprime rien.

### Flow 3 — v2 : préparer son poste puis montrer un agent (Claire, la veille et le matin d'un atelier client)

La veille, au bureau, Claire prépare son portable (16 Go, RTX 3050) pour un atelier où elle montrera un agent qui analyse un fichier de ventes et prépare un email au client.

1. Écran Modèles : le catalogue dit que `qwen3.6:7b` tient en mémoire. Elle clique « Installer » ; la ligne suit « Téléchargement 1,2 Go sur 4,7 Go · 26 % » pendant qu'elle lit la fiche d'un autre modèle.
2. « qwen3.6:7b installé. » Dans « Modèles proposés par défaut », elle le choisit pour l'usage Agent : raison « Choisi par vous ».
3. Le matin, écran Sobriété : « Remettre le compteur à zéro » ; l'historique garde la session de la veille.
4. Agent seul : le modèle choisi est déjà là, « Envoi d'email » décoché ; elle le coche devant la salle et demande d'analyser `ventes.csv` puis d'envoyer la synthèse au client.
5. Le panneau « Étapes » se remplit : Réflexion, Analyse de données, Graphique. Elle déplie l'étape d'analyse pendant que la suivante arrive.
6. **Climax :** l'étape « Envoi d'email » passe à « En attente de votre validation » et le dialogue montre destinataire, objet et corps. Claire se tourne vers la salle : « Rien ne part sans moi. » Elle clique « Annuler » ; la trace inscrit « Envoi annulé : l'agent en est informé. » et l'agent conclut sans envoyer.
7. Retour sur Sobriété : l'empreinte de la session montre la part de l'agent, en Local.

Échecs : le modèle ne tient pas → la ligne du catalogue le dit avant l'installation. Le téléchargement échoue → `wl-error` dans la ligne, liste inchangée. Le garde-fou mémoire bloque l'agent → la tâche reste, « Décharger les modèles inactifs » est proposé.

## Open Questions

Non bloquantes pour la nuit ; à trancher dans `bmad-spec`.

1. **Mémoire affichée sous les réponses de la Discussion** (« 💾 0.0 GB », non investiguée) : la corriger ou la retirer ?
2. **Garde-fou mémoire avec un modèle déjà chargé dans Ollama** : le chiffre « nécessaire » de l'état bloqué doit être vrai avant d'être affiché.
3. ~~**v2, Sobriété :** équivalence parlante~~ Tranchée par D-38 : seulement dans le panneau de méthode, avec la source du facteur (story 5.1).
4. **v2, Évaluation :** la colonne « Global » de la maquette §3.5 n'est pas dans la story 7.3 ; une moyenne des trois métriques masquerait un modèle qui invente. Écartée sauf décision contraire (la maquette validée ne l'a pas).
5. **v2, Évaluation et Banc d'essai :** une liste des runs précédents (comme l'historique de l'Arène) n'est pas demandée ; l'URL du run suffit-elle ? (D-28 tranche seulement le résultat partiel d'une évaluation arrêtée : conservé, rouvrable, marqué « partiel ».)
