# Parité de la v1 (Streamlit) avec la v2

Liste page par page et onglet par onglet de ce que fait la v1 et de ce qu'il en advient dans la v2
(`src/wavelocalai/`, port 8502). Elle sert à décider de l'archivage de la v1 (story 8.4) sans perdre
une fonction sans le dire. Source : l'inventaire de `docs/audits/refonte-2026-10/03-ux-front.md` §1.1,
relu contre le code de la v1 (`src/app/Accueil.py`, `home.py`, `views/`, `tabs/`, `rag_upload.py`,
`rag_clear.py`) et contre le code, les textes et les tests de la v2.

Statuts :

- **reprise** : la fonction existe dans la v2, au même endroit logique (écran indiqué).
- **remplacée par** : la v2 rend le même service autrement (écran et geste indiqués).
- **abandonnée** : la fonction n'existe plus dans la v2, avec son motif.

Aucune fonction n'est sans statut. Les lignes marquées **(à confirmer)** sont des fonctions de la v1
sans équivalent dans la v2 et sans décision d'abandon trouvée dans `epics.md`,
`decisions-2026-10-19.md`, `sprint-change-proposal-2026-10-19.md` ni les specs de stories : elles sont
classées « abandonnée » par prudence documentaire, avec le motif « à confirmer par Anaël ». Pour
quelques-unes, une spec de story note déjà l'écart (« variante conservatrice »), cité en motif.

## À confirmer par Anaël

Chaque cas porte le numéro de sa ligne dans les tableaux ci-dessous. Tant qu'il n'est pas tranché, la
v2 se comporte comme décrit ; une décision « à reprendre » ouvre une story de suite avant ou après 8.4.

| N° | Fonction de la v1 | État dans la v2 | Pistes |
|---|---|---|---|
| B3 | Banc d'essai : consigne système éditable et curseur « Température » (« Réglages avancés ») | « Consigne » en lecture seule, température fixe à 0,2 (écart noté en 7.4) | reprendre un champ de consigne et un curseur, ou garder les scénarios figés |
| A8 | Arène : phrase « Pourquoi ? » sous le vainqueur (« Meilleure note (+N points) », « Plus rapide », « Moins de CO₂ »…) | le classement ordonne par note, sans phrase de motif | ajouter une ligne de motif au rang 1 (calcul serveur, AD-20) |
| D4 | Discussion : « Télécharger » la réponse en Markdown | absent (écart n° 12 du §7(d), toujours ouvert : aucune route d'export du RAG) | un bouton sur la route commune `GET /api/conversations/{id}.md` (déjà servie pour toute conversation, sans filtre de genre ; les sources du RAG n'y figurent pas encore) |
| D5 | Base vide : trois encarts « Pourquoi un assistant documentaire local ? » (Confidentialité, Précision, Sobriété) | une carte « Votre base documentaire est vide » avec l'action « Importer des documents », sans encarts | reprendre les trois phrases en pied de la carte, ou les laisser à la page d'accueil du module |
| E5 | Évaluation : colonnes « Durée (s) » et « Mémoire (Go) » du tableau détaillé | le tableau montre fidélité, pertinence, précision du contexte, débit et CO₂ ; durée et mémoire absentes | ajouter les colonnes (une mesure serveur serait à prévoir, AD-20) |
| G5 | Agent seul : bibliothèque « Scénarios » (cinq scénarios en quatre catégories, outils préremplis) | deux actions rapides à l'accueil (« Lancer l'audit », « Analyser les données ») | reprendre la bibliothèque dans un panneau, ou la juger superflue |
| G9 | Équipe : estimation de la mémoire avant lancement et bouton « Lancer malgré le risque » | pas d'estimation ; le garde-fou serveur `ram_guard` coupe un appel de modèle qui ne tient pas ; `onSmallerModel` (deux actions de l'Arène, de la Discussion, de l'Agent seul) n'est pas branché sur l'écran Équipe | brancher `onSmallerModel` sur l'écran Équipe, ou confirmer |
| G10 | Équipe : délégation entre agents (`allow_delegation`) | ordre fixe, le texte de l'agent précédent est transmis (écart noté en 6.5) | confirmer l'ordre fixe |
| G11 | Équipe : champ « Contexte » (`backstory`) éditable par agent | valeur gardée à l'enregistrement, non éditable (écart noté en 6.6) | confirmer, ou ajouter le champ |
| S4 | Sobriété : « Arrêter et enregistrer » puis « Reprendre le suivi » de la session CodeCarbon | la mesure est continue ; seule « Remettre le compteur à zéro » clôt une session (elle va à l'historique) | confirmer qu'une pause de mesure n'a pas d'usage |
| S8 | Sobriété, carte d'identité : « Nom de la machine », « Architecture », version de Python | la fiche montre processeur, mémoire, accélérateur, système, version d'Ollama et de WaveLocalAI | confirmer (le nom de machine n'a pas d'intérêt en démonstration, et peut être sensible) |
| M5 | Gestion des modèles : filtres rapides par capacité (Raisonnement, Outils, Rapide, Cloud) | pas de filtre sur l'écran Modèles ; le sélecteur de modèles se filtre par saisie et marque outils, raisonnement et MoE | ajouter des filtres, ou s'en remettre au filtre par saisie du sélecteur |
| M6 | Gestion des modèles : colonnes « RAM » estimée et « CO₂ pour 1 000 tokens » de chaque modèle installé | « Tient en mémoire » et « Débit sur ce poste » sur l'écran ; la fiche d'un modèle donne mémoire au pic et énergie par 1 000 tokens, mesurées sur les postes de référence | confirmer (le CO₂ est mesuré par réponse, pas estimé par modèle) |

## Commun à toutes les pages

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| C1 | Barre latérale avec wordmark et liste des cinq modules (`st.navigation`) | remplacée par | coquille : barre haute et navigation par modules (`#module-list`), onglets d'écran par module |
| C2 | Bascule « Autoriser le cloud », locale à la session, désactivée à chaque ouverture (D1) | reprise | barre haute : interrupteur « Autoriser le cloud », désactivé à chaque ouverture de la page, avec son aide |
| C3 | Alerte « Ollama ne répond pas » en tête de module | remplacée par | barre haute : pastille d'état d'Ollama (panneau avec « Réessayer ») ; chaque écran dit lui-même l'indisponibilité de ce qu'il affiche |
| C4 | Suivi CodeCarbon de session lancé par le routeur | remplacée par | mesure par réponse côté serveur (AD-10), total dans la barre haute (« CO₂ session ») et l'écran Sobriété |
| C5 | Thème de l'interface (fourni par Streamlit) | remplacée par | barre haute, menu « Affichage » : thème Clair, Sombre ou Système, plus le mode projection |
| C6 | États « aucun modèle installé » (`render_no_models`) | remplacée par | chaque écran dit quoi faire (lien vers Modèles) ; le sélecteur dit « Aucun modèle de conversation n'est disponible » |
| C7 | Détail technique replié sous chaque erreur | reprise | composant d'erreur commun (`wl-error`) : message, action, « Détails techniques » repliés |
| C8 | Composants non importés (`components/chat_message.py`, `metrics_display.py`, `model_selector.py`, `source_expander.py`, T9 de l'audit) | abandonnée | code mort, jamais affiché par la v1 |

## Accueil

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| H1 | Métrique « Système » (Disponible / Indisponible) | reprise | Accueil, carte « Système » en direct, avec « Réessayer » |
| H2 | Métrique « Mode » (Local ou Cloud) | reprise | Accueil, carte « Mode », avec le CO₂ de la session |
| H3 | Métriques « Processeur » et « Mémoire » (figées à l'ouverture) | reprise | Accueil, cartes en direct (flux système toutes les 2 s) |
| H4 | Carte « Démo recommandée » et lien vers l'Arène | reprise | Accueil, carte « Démo recommandée » : modèles prêts et « Lancer une comparaison » |
| H5 | Trois cartes de modules (`st.page_link`) | remplacée par | Accueil, cinq cartes de modules avec nom court, nom long, résumé (documents indexés) ; carte « Références » |
| H6 | Pied de page © année · Wavestone | remplacée par | pied de page de la coquille (« Les données restent sur ce poste tant que le cloud n'est pas autorisé ») |

## Arène des modèles : Chat libre

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| L1 | Choix du modèle actif et badge Local/Cloud | reprise | Chat libre `#/arene/chat` : sélecteur de modèles groupé Local/Cloud, filtrable, avec le défaut et sa raison |
| L2 | Curseur « Créativité » (température) | reprise | Chat libre : curseur « Créativité », valeur conseillée du modèle (repli 0,2) |
| L3 | CO₂ de la session dans le bandeau | remplacée par | barre haute « CO₂ session » ; pied de chaque réponse |
| L4 | « Effacer la conversation » | reprise | Chat libre : « Effacer la conversation » |
| L5 | Message envoyé, réponse en flux, indicateur de premier chargement | reprise | Chat libre : champ de saisie (Entrée envoie, Échap arrête), réponse au fil de l'eau, message de premier chargement ; **annulation** ajoutée |
| L6 | Raisonnement du modèle replié | reprise | fil de conversation commun (`wl-chat-thread`) : « Raisonnement » |
| L7 | Pied de réponse : badge, CO₂, débit, chargement, durée | reprise | pied de réponse : CO₂ (mesuré ou estimé, ou « non mesurable » dit), débit, tokens, chargement, durée |
| L8 | Erreur d'un tour gardée dans l'historique | reprise | message en échec dans le fil, avec action |
| L9 | Relance automatique après coupure de génération | reprise | « Génération relancée : raison » dans le fil |
| L10 | Conversation tenue en mémoire de session | remplacée par | conversations enregistrées côté serveur (rechargement de page sans perte), export JSON et Markdown |

## Arène des modèles : Banc d'essai

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| B1 | Choix du modèle (avec badge) | reprise | Banc d'essai `#/arene/banc` : sélecteur de modèles |
| B2 | Six scénarios prédéfinis (Classification, Traduction technique, Extraction, Assistant de code, Raisonnement pas à pas, Résumé) | reprise | Banc d'essai : liste « Scénario prédéfini », les six, consigne et format attendu distincts |
| B3 | « Réglages avancés » : consigne système éditable et température | abandonnée | **(à confirmer)** « Consigne » repliée en lecture seule (D-18), température fixe à 0,2 : écart noté en 7.4 |
| B4 | Entrée utilisateur éditable, préremplie par le scénario | reprise | Banc d'essai : champ « Entrée » (gardé quand on change de scénario, avec « Remplacer par l'exemple du scénario ») |
| B5 | « Lancer le test », réponse et métriques (débit, chargement, durée, CO₂) | reprise | Banc d'essai : réponse en flux, mesures D3, CO₂, durée |
| B6 | Résultat conservé au rerun suivant | remplacée par | essai enregistré, rouvrable par `#/arene/banc/<run_id>`, liste « Tests passés » |
| B7 | Sortie JSON non vérifiée | remplacée par | verdict de format calculé par le serveur (« Format respecté » ou la première violation), sortie mise en forme, interrupteurs « Format imposé » et « Réponse concise » ; « Relancer le test » et « Modifier le test » |
| B8 | Raisonnement du modèle replié | reprise | fil de réponse commun : « Raisonnement » |

## Arène des modèles : Arène (comparaison)

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| A1 | Choix des modèles à comparer (multisélection, au moins 2) | reprise | Arène `#/arene/comparer` : sélecteur multiple, 2 à 4 modèles, défaut `arena` ; légendes « Choisissez 4 modèles au plus » |
| A2 | Question libre | reprise | Arène : champ « Question », avec quatre scénarios prédéfinis (Vulgarisation, Extraction JSON, Résumé, Traduction) en plus |
| A3 | Réglages du juge : modèle juge, avertissements de juge faible, juge évalué aussi | reprise | Arène : panneau « Critères de notation », « Juge », aides et alertes (« Note peu fiable », « Aucun juge ») |
| A4 | Invite brute du juge (texte libre) | remplacée par | critères de notation en liste (un à huit critères, ajout, retrait, « Rétablir les critères par défaut ») |
| A5 | « Lancer la comparaison », désactivé sous deux modèles avec sa raison | reprise | Arène : « Lancer la comparaison », raison visible (« Choisissez au moins 2 modèles ») |
| A6 | Barre de progression et statut « Comparaison en cours… » | remplacée par | bandeau d'avancement avec chronomètre « 0:42 », une colonne par modèle avec son statut (chargement, rédaction, notation) ; **réponses en flux** et bouton d'arrêt ajoutés |
| A7 | Délai dépassé ou échec d'un modèle, les autres continuent | reprise | colonne en échec avec son message (« Délai dépassé (120 s) ») ; les autres continuent |
| A8 | Carte « Vainqueur » avec la phrase « Pourquoi ? » | abandonnée | **(à confirmer)** le classement porte le rang et les faits (note, débit, CO₂) ; la phrase de motif n'existe plus. Le podium lui-même : remplacée par « Classement » |
| A9 | Matrice qualité, débit et CO₂ (Plotly) | reprise | Arène : « Matrice » (SVG local), CO₂ en taille de point, légende, valeurs dans « Tableau » |
| A10 | Tableau des résultats (note, exécution, débit, CO₂, chargement, durée) | reprise | Arène : « Tableau » et définitions des colonnes |
| A11 | « Non évalué » avec sa raison, jamais 0/100 | reprise | Arène : « non évalué : raison », sans rang |
| A12 | Réponses des modèles (côte à côte pour deux, repliées sinon) | reprise | Arène : colonnes par modèle (onglets sous 768 px, mode focus) |
| A13 | Raisonnement d'une réponse, « Réponse vide » | reprise | « Raisonnement » dans la colonne ; « non évalué : réponse vide » |
| A14 | « Détails techniques » des échecs | reprise | composant d'erreur commun |
| A15 | Légende « le plus petit des trois » / étoile du vainqueur | abandonnée | décision n° 6 du 2026-10-19 (étiquette abandonnée) |
| A16 | Résultats perdus au clic suivant | remplacée par | comparaison enregistrée : `#/arene/comparer/<run_id>`, « Comparaisons précédentes », « Relancer », « Modifier la question », « Effacer la comparaison » |
| A17 | Export des résultats | remplacée par | exports CSV et Markdown (menu « Exporter » sous 768 px) |
| A18 | Badge Local/Cloud d'un modèle | reprise | badge sur chaque colonne et chaque ligne du classement |
| A19 | (nouveau en v2) verdict local et cloud : écart de note, coût, CO₂, données restées sur le poste | — | hors v1, ajouté par l'Epic 3 |

## Arène des modèles : Gestion des modèles (écran Modèles)

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| M1 | Tableau des modèles disponibles (nom, format, vitesse, RAM, CO₂, paramètres, capacités) | remplacée par | Modèles `#/modeles` : « Sur ce poste » (nom, origine, usage, paramètres, taille, tient en mémoire, chargé, débit mesuré) ; modèles cloud dans le groupe « Cloud » du sélecteur ; fiche d'un modèle par `#/modeles/<tag>` |
| M2 | « Rafraîchir » la liste | remplacée par | liste servie en direct par le registre ; pas de bouton |
| M3 | « Ajouter un modèle » : catalogue Ollama et Wavestone, caractéristiques, tag libre, progression | reprise | Modèles : « Catalogue installable » (avec mémoire nécessaire, « Tient en mémoire »), « Installer un modèle par son nom », progression chiffrée et « Annuler », « Installer quand même » |
| M4 | Aucune suppression de modèle | remplacée par | **ajout** : « Supprimer » avec confirmation et conséquence chiffrée |
| M5 | Filtres rapides par capacité (Raisonnement, Outils, Rapide, Cloud) | abandonnée | **(à confirmer)** pas de filtre sur l'écran Modèles |
| M6 | Colonnes « RAM » et « CO₂ pour 1 000 tokens » | abandonnée | **(à confirmer)** remplacées en partie : « Tient en mémoire », « Débit sur ce poste », fiche du modèle (mémoire au pic, énergie par 1 000 tokens) |
| M7 | Info-bulles des colonnes | reprise | aides des colonnes et des définitions de la fiche |
| M8 | « Libérer la mémoire » (page Agents) | remplacée par | Modèles : « Décharger les modèles inactifs » (la v1 vidait un cache CUDA, sans effet sur Ollama : audit 03 §1.2) ; « sans bouton Libérer la mémoire » est écrit dans les critères de la story 6.4 |
| M9 | (nouveau en v2) modèles par défaut par usage, installation du reclassement, fiche, comparaison avec les postes de référence | — | hors v1 |

## Assistant documentaire : base et réglages

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| D1 | Dialogue « Gérer la base documentaire » : import PDF, TXT, MD, DOCX, multi-fichiers | remplacée par | Base documentaire `#/documents/base` : zone de dépôt, « Choisir des fichiers », limites dites, suivi par fichier (lecture, découpage, vectorisation), « Annuler l'import » |
| D2 | Résumé de la base (documents, extraits) | reprise | Base documentaire : « N documents prêts · N extraits » ; carte de l'Accueil ; décompte dans la Discussion |
| D3 | « Vider » la base avec confirmation | reprise | Base documentaire : « Vider la base documentaire » avec dialogue chiffré, « Annuler » sans suppression ; **suppression d'un document** ajoutée |
| D4 | Discussion : « Télécharger » la réponse en Markdown | abandonnée | **(à confirmer)** écart n° 12 du §7(d), ouvert |
| D5 | État vide : trois encarts « Pourquoi un assistant documentaire local ? » | abandonnée | **(à confirmer)** la carte vide garde le titre, une phrase et l'action |
| D6 | État vide : carte « Votre base documentaire est vide » et bouton « Importer des documents » | reprise | Discussion et Base documentaire : même carte et même action |
| D7 | Compte rendu d'import par fichier, erreurs avec détail | reprise | Base documentaire : ligne par fichier, « Déjà indexé », « Échec : raison », comptes de fin d'import |
| D8 | Réglage « Modèle de représentation » (embedding) | reprise | Base documentaire : « Modèle de représentation », avec l'avertissement de réindexation |
| D9 | Réglage « Stratégie de recherche » (naïve, HyDE, Self-RAG) | reprise | Discussion, « Réglages avancés » : « Recherche directe », « Réponse imaginée d'abord », « Recherche vérifiée » ; défaut dans la Base |
| D10 | Réglage « Nombre d'extraits » (Top-K) | reprise | Discussion, « Réglages avancés », et défaut dans la Base documentaire |
| D11 | Réglage « Modèle de reclassement » (choix, « Aucun ») | remplacée par | Modèles : « Installer le reranker » (un clic, téléchargement unique) ; le reclassement est actif quand il est installé, et dit « Reclassement actif » ou sa raison d'absence, sans choix par session |
| D12 | (nouveau en v2) taille des extraits, index en mémoire sans sqlite-vec | — | hors v1 |

## Assistant documentaire : onglet Discussion

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| Q1 | Choix du modèle de réponse et badge | reprise | Discussion `#/documents` : sélecteur de modèles (défaut `rag`) |
| Q2 | Question et réponse en flux | reprise | Discussion : champ de saisie, réponse au fil de l'eau, arrêt par Échap |
| Q3 | Sources sous la réponse (400 caractères, score de reclassement brut) | remplacée par | panneau de sources **avant** la réponse, renvois [n] dans le texte, extrait complet au clic avec le passage surligné, document, page, rang et score brut expliqué |
| Q4 | Raisonnement du modèle replié | reprise | fil de conversation commun |
| Q5 | Pied de réponse : badge, modèle, durée, mémoire, CO₂ | reprise | pied de réponse : CO₂, débit, durée, avec la durée de la recherche des extraits et celle de la génération |
| Q6 | Avertissement pour un modèle cloud | remplacée par | « {modèle} est un modèle cloud : les extraits retrouvés dans vos documents lui sont envoyés » |
| Q7 | Conversation tenue en mémoire de session | remplacée par | conversation enregistrée côté serveur ; « Effacer la conversation » |
| Q8 | Garde-fou mémoire (question bloquée, message) | reprise | `ram_guard` : question gardée dans le champ, besoin chiffré, « Prendre un modèle plus petit » |

## Assistant documentaire : onglet Évaluation de la qualité

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| E1 | Choix des modèles évalués, avec défaut hors juge | reprise | Évaluation `#/documents/evaluation` : modèles évalués (1 à 4), défaut `arena` |
| E2 | Choix du juge, avertissements, juge aussi candidat | reprise | Évaluation : « Juge », aides, « Note peu fiable », « Aucun juge », « Le juge est aussi un modèle évalué » |
| E3 | Question de référence (une seule) | reprise | Évaluation : mode « Question », et **« Jeu de questions »** (20 au plus) ajouté |
| E4 | Recherche des extraits communs à tous les modèles | reprise | étape « Recherche des extraits communs », « Voir les extraits » par question |
| E5 | « Durée (s) » et « Mémoire (Go) » du tableau détaillé | abandonnée | **(à confirmer)** le tableau montre débit et CO₂ |
| E6 | « Note globale », podium de la qualité | abandonnée | décision du 2026-10-19 : pas de colonne « Global » ; le tableau et la matrice montrent chaque note |
| E7 | Fidélité et pertinence (Ragas) | reprise | tableau : fidélité, pertinence et **précision du contexte** ; définitions et détail d'un score (verdicts par affirmation, extrait d'appui) |
| E8 | Matrice « Qualité selon le CO₂ » | reprise | « Matrice » : fidélité selon le débit, CO₂ en taille de point |
| E9 | Réponses des modèles et extraits fournis | reprise | détail d'un score (« Réponse évaluée »), « Extraits communs » |
| E10 | Raison d'un « non évalué » | reprise | « non évalué (raison) » dans le tableau |
| E11 | Résultat perdu au clic suivant | remplacée par | évaluation enregistrée, rouvrable (`#/documents/evaluation/<run_id>`), « Évaluations passées », résultat partiel conservé à l'arrêt |
| E12 | Bandeau « Sobriété : trouver le modèle le plus léger… » | abandonnée | texte d'accroche sans fonction ; le CO₂ et le débit sont dans le tableau |
| E13 | Message « moteur d'évaluation non installé » | remplacée par | la v2 n'importe pas `ragas` : l'évaluation (« méthode inspirée de Ragas ») est faite par son propre service, appliquée par un juge |

## Agents autonomes : commun

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| G1 | Choix du mode (radio : Agent seul, Équipe d'agents) | remplacée par | onglets du module Agents : `#/agents/seul` et `#/agents/equipe` |
| G2 | « Santé du système » : mémoire disponible, utilisation, alerte sous 1 Go | remplacée par | barre haute (mémoire libre, modèles chargés) et écran Sobriété ; garde-fou `ram_guard` à l'appel |
| G3 | « Libérer la mémoire » | remplacée par | Modèles : « Décharger les modèles inactifs » (voir M8) |
| G4 | « Effacer la conversation » | reprise | Agent seul : « Effacer la conversation » |

## Agents autonomes : Agent seul

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| G5 | Bibliothèque « Scénarios » (dialogue, cinq scénarios en catégories) | abandonnée | **(à confirmer)** deux actions rapides subsistent |
| G6 | Choix du modèle, tri par outils vérifiés, avertissement | reprise | Agent seul : sélecteur (défaut `agent`), « Outils vérifiés », avertissement sans outils vérifiés |
| G7 | Pastilles d'outils (neuf outils, email décoché) | reprise | Agent seul : neuf interrupteurs (Heure, Calculatrice, Recherche interne Wavestone, Analyse de données, Génération de document, de graphique, Rapport Markdown, Moniteur système, Envoi d'email), « Envoi d'email » décoché ; un outil non configuré dit pourquoi |
| G8 | Actions rapides « Lancer l'audit » et « Analyser les données » | reprise | Agent seul : écran d'accueil « Bonjour ! », mêmes deux actions (le CSV est celui de l'espace de travail des agents) |
| G12 | Flux d'événements `tool_call`, `tool_result`, réponse finale | reprise | Agent seul : trace d'étapes dépliables (`wl-step-trace`) ; la réponse arrive d'un bloc (dit) |
| G13 | Validation d'un email (dialogue « Envoyer l'email ? ») | reprise | Agent seul : dialogue de validation (destinataire, objet, corps), délai de réponse dit, aucun envoi sans accord |
| G14 | Garde-fou mémoire (question non envoyée) | reprise | `ram_guard` : tâche gardée dans le champ |
| G15 | Téléchargement des fichiers produits | reprise | liens vers les fichiers de l'agent (`/api/outputs/…`) et « Télécharger » la réponse |
| G16 | Badge Local/Cloud et CO₂ de la réponse | reprise | pied de réponse : CO₂, nombre d'étapes, durée |
| G17 | Budget carbone « gamifié » | abandonnée | jamais affiché dans la v1 (audit 03 §1.2) |

## Agents autonomes : Équipe d'agents

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| G18 | « Charger une équipe » (bibliothèque de trois équipes) | reprise | Équipe : liste « Équipe » (Étude concurrentielle, Audit des mesures, Comparaison carbone) ; « Modifiée » et « Revenir à l'équipe d'origine » |
| G19 | Sujet de la mission | reprise | Équipe : « Sujet de la mission » |
| G20 | Modèle principal de l'équipe | reprise | Équipe : « Modèle des agents » |
| G21 | « Configurer l'équipe » : rôle, objectif, modèle, outils, ajout et retrait d'agent | reprise | Équipe : volet « Configurer » (rôle, objectif, outils, modèle, « Ajouter un agent », « Retirer cet agent », « Enregistrer ») |
| G11 | Champ « Contexte » (`backstory`) éditable | abandonnée | **(à confirmer)** non éditable, valeur gardée (écart noté en 6.6) |
| G22 | Schéma de l'enchaînement (Graphviz) | remplacée par | Équipe : schéma SVG local (`wl-team-graph`), état de chaque agent ; plus de dépendance à Graphviz |
| G9 | Estimation de mémoire avant lancement et « Lancer malgré le risque » | abandonnée | **(à confirmer)** remplacée en partie par le garde-fou `ram_guard` du serveur ; pas d'estimation avant lancement |
| G23 | « Lancer l'équipe » | reprise | Équipe : « Lancer la mission », raison visible d'un bouton désactivé |
| G24 | Journal d'exécution (stdout brut de CrewAI) | remplacée par | Équipe : suivi agent par agent avec étapes, et « Journal brut » des événements |
| G25 | Rapport final | reprise | Équipe : « Rapport » conservé, « Télécharger en Markdown », rapport partiel à l'arrêt ; mission rouvrable par `#/agents/equipe/<run_id>` |
| G10 | Délégation entre agents (`allow_delegation`) | abandonnée | **(à confirmer)** ordre fixe, écart noté en 6.5 |
| G27 | Mission sans arrêt possible | remplacée par | arrêt de la mission (Échap, bouton), rapport partiel |
| G28 | Outil d'email de l'équipe : brouillon seulement, aucun envoi | remplacée par | Équipe : un agent peut demander l'envoi, validé dans le même dialogue que l'Agent seul (aucun envoi sans accord) |

## Sobriété et matériel

| N° | Fonction de la v1 | Statut | Écran v2 ou motif |
|---|---|---|---|
| S1 | Métriques « Processeur » et « Mémoire » (rafraîchies par « Rafraîchir ») | remplacée par | Sobriété `#/sobriete` : cartes en direct, sans clic ; pause quand l'onglet est masqué |
| S2 | Métrique « Accélérateur IA » (mémoire, légende sans carte) | reprise | Sobriété : « Accélérateur », mémoire vidéo, température, bridage thermique |
| S3 | Métrique « Mode » (Local/Cloud) | remplacée par | carte Ollama (modèles chargés, version) ; le mode est à l'Accueil et dans la barre haute |
| S4 | « Arrêter et enregistrer » et « Reprendre le suivi » | abandonnée | **(à confirmer)** remplacées par « Remettre le compteur à zéro » (la session précédente va à l'historique) |
| S5 | Total de la session et équivalence en kilomètres de voiture | remplacée par | Sobriété : « Total de la session », local et cloud estimé, par module, non mesurables à part ; équivalence dans « Comment ces chiffres sont calculés » seulement (calcul serveur) |
| S6 | Historique des émissions : une barre par lancement, période (segmenté), données en tableau replié | reprise | Sobriété : historique par session, période 7 jours / 30 jours / Tout, « Graphique » ou « Tableau », une seule unité |
| S7 | Message « suivi indisponible » ou sans historique | reprise | états vides et d'échec de la section (« Réessayer ») |
| S8 | Carte d'identité : système, architecture, nom de la machine, Python, cœurs logiques | abandonnée | **(à confirmer)** remplacée par processeur (cœurs physiques et fils), mémoire, accélérateur, système, versions d'Ollama et de WaveLocalAI |
| S9 | « Rafraîchir » | abandonnée | inutile : les valeurs suivent le flux sans clic |
| S10 | Avertissement « l'impact par réponse est une estimation théorique » | remplacée par | panneau « Comment ces chiffres sont calculés » : local mesuré, cloud estimé, non mesurable dit |

## Fonctions nouvelles de la v2 (sans équivalent dans la v1)

Pour mémoire, hors parité : écran Références (quel modèle pour quel usage, `#/arene/references`), mode
projection, flux système en direct, Arène à 4 colonnes en flux, notes de l'Évaluation au fil de l'eau,
historique des comparaisons, évaluations, essais et missions, fiche d'un modèle et comparaison avec les
postes de référence, modèles par défaut par usage, suppression de modèle ou de document.
