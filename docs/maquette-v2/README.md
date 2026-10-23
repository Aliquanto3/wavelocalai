# Maquette du front de WaveLocalAI v2

## 1. Objet

Maquette HTML interactive du front définitif de la v2, à valider avant le codage complet. Les contenus sont fictifs (modèles, documents, mesures, sociétés). Rien n'est appelé hors du dossier : aucune requête hors de `127.0.0.1`, aucun serveur applicatif, aucun fichier de l'utilisateur lu.

Ce document liste ce que la maquette couvre, les écarts avec le contrat (sans les trancher, sauf ceux que les décisions d'Anaël règlent) et ces décisions.

## 2. Ouvrir

- Double-clic sur `maquette-autonome.html` : un seul fichier, ouvrable en `file://`, qui embarque CSS, JavaScript, données, textes, polices et icônes. Il peut circuler hors du dépôt.
- En second, depuis les sources : double-clic sur `ouvrir.cmd` (Windows), ou `python serveur.py` depuis `docs/maquette-v2/`, puis l'adresse affichée.

Les sources modulaires restent la référence. `maquette-autonome.html` est généré par `python construire_autonome.py` (bibliothèque standard seulement) et commité ; un test échoue s'il n'est plus à jour. Technique : chaque module ES est embarqué en URL `data:` dans une carte d'import (`importmap`) statique, ses spécificateurs relatifs (y compris le préfixe des `import()` du routeur) deviennent des noms `@wl/js/…` ; `import.meta.url` devient l'adresse fictive `wl:/js/…`, un `fetch` intercepté sert les JSON de `donnees/` et `i18n/`, et les feuilles d'écran passent par des URL `blob:`. Le fichier pèse environ 2,3 Mo.

Un double-clic sur `index.html` ne lance pas la maquette : Chromium et Edge bloquent les modules ES et `fetch` en `file://`. La page renvoie vers `maquette-autonome.html`.

`serveur.py` remplace `python -m http.server` : il écoute sur `127.0.0.1`, prend un port libre et fixe les types MIME. Sous Windows, `http.server` sert parfois les `.js` en `text/plain`, que les modules refusent.

Dans la maquette :

- Le bouton « Scénarios (maquette) », en bas à droite, force un état d'écran, un état global (Ollama arrêté, cloud, connexion perdue, serveur redémarré, garde-fou mémoire, premier chargement lent, aucun modèle local, onglet masqué, thème, projection, vitesse) ou joue un parcours de bout en bout.
- Le catalogue des états communs est à `#/maquette/etats`.

Version en ligne (artifact privé, accès sur invitation) : https://claude.ai/artifact/WTgFyyF3bMJGFE6jx4DEYH

## 3. Structure

- `maquette-autonome.html` (généré par `construire_autonome.py`) : la maquette en un seul fichier.
- `index.html`, `serveur.py`, `ouvrir.cmd` : point d'entrée des sources et serveur local.
- `js/` : coquille (`shell/`), écrans (`screens/`), composants communs (`components/`), simulateur de flux (`sim/`), scénarios globaux et parcours (`scenarios/`).
- `css/`, `tokens.css`, `fonts/`, `icons.svg` : styles, jetons, police Inter, sprite d'icônes.
- `donnees/` : routes, parcours, données fictives par écran, flux d'événements (`flux/`), catalogue d'erreurs. Le nom évite `data/`, ignoré par `.gitignore`.
- `i18n/` : textes en français.
- `notes/` : une note par écran (états, écarts, décisions) et `revue.md`.
- `tests/` : suite pytest et Playwright.

Les règles pour ajouter ou modifier un écran sont dans `docs/maquette-v2/CONVENTIONS.md`.

## 4. Écrans et états couverts

Le nombre de scénarios est celui des `scenarios` exportés par chaque module d'écran.

| Chemin | Écran | Scénarios |
|---|---|---|
| `/` | Accueil | 10 |
| `/arene/chat` | Chat libre | 23 |
| `/arene/comparer`, `/arene/comparer/:run_id` | Arène | 33 |
| `/arene/banc`, `/arene/banc/:run_id` | Banc d'essai | 28 |
| `/arene/references` | Références | 10 |
| `/documents` | Discussion | 28 |
| `/documents/base` | Base documentaire | 30 |
| `/documents/evaluation`, `/documents/evaluation/:run_id` | Évaluation de la qualité | 26 |
| `/agents/seul` | Agent seul | 31 |
| `/agents/equipe`, `/agents/equipe/:run_id` | Équipe d'agents | 30 |
| `/sobriete` | Sobriété et matériel | 21 |
| `/modeles`, `/modeles/:tag` | Modèles | 36 |
| `/maquette/etats` | Catalogue des états (propre à la maquette) | 3 |

Onze scénarios globaux s'y ajoutent dans le panneau (voir section 2).

### Coquille et barre haute

- Pastille Ollama (vérification, disponible, ne répond pas, inconnu) et son panneau (version, mémoire, modèles chargés, « Réessayer »).
- Interrupteur « Autoriser le cloud » (store seulement, perdu au rechargement, pied de page qui suit).
- CO₂ de session et son panneau (total, Local, Cloud, non mesurables).
- Menu Affichage : clair (défaut), sombre, système, projection (interrupteur). Menu replié sous 1 024 px.
- Bandeaux « Connexion au serveur perdue » (après trois échecs) et « Le serveur a redémarré ».
- États communs du catalogue : vide, chargement lent, 409 rejoint, étapes d'un run, score et « non évalué », CO₂ mesuré, estimé ou « non mesurable », garde-fou mémoire, confirmation de « Vider », chaque code de `donnees/erreurs.json`.

### Familles d'états par écran

- **Accueil** : nominal, squelettes, Ollama arrêté (avec ou sans cloud), aucun modèle local, cloud autorisé, connexion perdue, mémoire haute, onglet masqué, étape du Flow 1.
- **Chat libre** : vide, réponse locale, en cours, arrêt, cloud estimé ou non mesurable, conversation rouverte, reprise au retour, 409, relance automatique, erreurs (interrompue, délai, Ollama, cloud, clé absente, cloud non autorisé ou retiré), garde-fou mémoire, aucun modèle, connexion perdue, serveur redémarré.
- **Arène** : configuration (moins de deux modèles, trop de modèles, juge peu fiable), exécution (chargement lent, arrêt, reprise, 409), résultats (classement, matrice, tableau, réponse entière, focus, verdict local/cloud, non mesurable, délai, non évalué, juge indisponible, colonne en échec), erreurs et gardes, résultat conservé, effacé ou introuvable.
- **Banc d'essai** : configuration (consigne repliée, format attendu, entrée modifiée, format imposé indisponible), résultats (format respecté ou non, sortie non JSON, sans format, concise, cloud), exécution, erreurs et gardes, résultat conservé ou introuvable.
- **Références** : cartes, « Comparer ces modèles » vers l'Arène présélectionnée, tableau trié, chargement, fichier absent ou de format inconnu, aucun usage publié, aucun modèle installé, Ollama arrêté.
- **Discussion** : base vide, sources et citations, ouverture d'une source, stratégies (HyDE, Self-RAG), reclassement, nombre d'extraits, cloud avec avertissement, conversation rouverte, indexation en cours, erreurs et gardes.
- **Base documentaire** : base vide ou remplie, import (un fichier, plusieurs, progression, échec, format refusé, doublon, annulation), filtrage et tri, suppression confirmée, document en échec dans le tableau, « Vider » (confirmation, annulation), réglages, changement d'embedding.
- **Évaluation** : formulaire, jeu de questions, base vide, évaluation en cours, détails de fidélité et de précision du contexte, matrice, jeu terminé, non évalué, délai, arrêt, résultat partiel rouvert, résultat rouvert ou introuvable.
- **Agent seul** : vide, outil indisponible, modèle sans outils, étapes en cours, tâche terminée, étape dépliée, erreur d'outil, bornes atteintes, validation d'email (envoyé, annulé, expirée, non coché), arrêt, cloud, redémarrage en attente de validation.
- **Équipe d'agents** : équipe prête, sans agent, sujet vide, équipe modifiée, volet Configurer non modal (avec erreurs, cinq agents au plus), mission en cours, rapport final, arrêtée (tôt ou tard), rouverte, validation d'email, 409 venant d'un agent seul.
- **Sobriété** : nominal, squelettes, Ollama arrêté, sans accélérateur, bridage thermique, mémoire haute, session vide, non mesurable, en grammes, réponse en direct, remise à zéro, équivalence dans la méthode, historique (7 jours, 30 jours, tout, tableau, période vide, vide).
- **Modèles** : liste, déchargement, suppression (confirmation, 409), installation (en cours, terminée, annulée, échecs, reprise), défauts par usage, reranker, fiche (débit, autres postes, autre version, valeurs inconnues, non installée, introuvable).

Tous les écrans couvrent aussi : premier chargement lent, reprise au retour, 409 rejoint, connexion perdue, serveur redémarré, Ollama arrêté, garde-fou mémoire.

### Parcours de bout en bout

Définis dans `donnees/parcours.json`, joués par le panneau Scénarios :

- Flow 1 : démo d'avant-vente (Accueil, Arène, vainqueur le plus petit).
- Flow 2 : atelier de formation (base vide, import, question avec sources, ouverture d'une source).
- Flow 3 : installation d'un modèle, remise à zéro du compteur, agent et validation d'email.
- Mission d'équipe : équipe prête, mission en cours, rapport final, mission rouverte par son adresse.
- Évaluation : jeu de questions, évaluation en cours, résultat rouvert.

## 5. Écarts avec le contrat

Chaque écart est signalé sans être tranché. Références : epics.md (stories, UX-DR), DESIGN.md, EXPERIENCE.md, `docs/audits/refonte-2026-10/03-ux-front.md` (03).

### Transverse

- Dossier `donnees/` au lieu de `data/` : `data/` est ignoré par `.gitignore`.
- Ouverture par serveur local et non par double-clic (voir section 2). **Réglé par la décision 1.**
- Thème « Système » ajouté au menu Affichage : UX-DR2 et la story 1.8 ne prévoient que clair et sombre. **Réglé par la décision 7.**
- Route `#/arene/references` (FR47) et route `#/agents/equipe/:run_id` ajoutées aux onze routes d'UX-DR4. Les sous-routes de Banc, Évaluation et Modèles viennent d'EXPERIENCE.md. **Réglé par la décision 8.**
- Code d'erreur `generation_interrupted` (`errors.py`) au lieu de `interrupted` (UX-DR16).
- Message du code `timeout` : la maquette cite le délai (« 2 min »), comme 03 §3.8, ce qu'`errors.py` ne fait pas. Texte de `cloud_not_allowed` : celui de 03 §3.8, plus court que celui d'`errors.py`.
- Boutons d'action des erreurs : le catalogue du front (`donnees/erreurs.json`, champ `buttons`) les déduit du code et de `detail` (AD-18), l'enveloppe du serveur n'en porte pas. **Réglé par la décision 4.**
- `pull_failed` (story 5.3) et `model_in_use` sont au catalogue de la maquette ; `errors.py` ne les a pas encore.
- Icônes : sprite de 37 symboles, dont 18 tracés Material Icons (Filled) gardés dans la maquette ; le front utilisera les Material Symbols Rounded officiels (voir `icons.LICENSE.txt`). DESIGN.md cite `leaderboard` pour l'Arène, le sprite a `swords` (non tranché). **Réglé par la décision 2.**
- Composants lus dans des branches `feat/v2-*` non fusionnées, pas dans `master` ; la maquette peut diverger de leur version finale.
- Contrat d'écran : `mount(host, ctx)` qui rend `unmount` (AD-20), avec `render(root, ctx)` en alias.
- Verdict de l'Arène (story 3.5) et verdict de format du Banc lus dans l'instantané du run ; `contrat-api.md` ne dit pas où ils vivent.
- Noms de champs d'événements (`step`, `approval_required`, `lane_status.error`, `ingest_progress.error`, `eval_metric`, `citations`) : lecture de `contrat-api.md`, qui ne donne que des libellés.
- Défauts restants de `notes/revue.md` : étiquette de la matrice de l'Arène pouvant chevaucher une bulle voisine (`charts.js`) ; note du classement de l'Arène non alignée quand un badge s'ajoute (`arene.css`).
- Le panneau Scénarios, ouvert, peut recouvrir du contenu (outil de maquette, replié par défaut, hors charte).

### Coquille

- Dans le front définitif, tous les modules sont disponibles : la maquette n'a aucun lien « Pas encore disponible ». Pas d'autre écart propre à la coquille au-delà du transverse.

### Accueil

- `h1` « Accueil » (03 §3.9) ; EXPERIENCE.md place le titre « WaveLocalAI » en tête. **Réglé par la décision 9.**
- Cartes des modules : nom court du menu en titre, nom long en sous-titre (« Documents », « Assistant documentaire »). **Réglé par la décision 10.**
- Carte « Références » ajoutée, avec l'icône de l'Arène (DESIGN.md : icône jamais partagée ; l'icône reste non tranchée). **Réglé par la décision 8.**
- Carte Mode : « N appels cloud dans cette session », compteur qu'aucune story ne définit.
- Score de la carte Références en pourcentage, libellé « Part de … » en tête, comme l'écran Références. **Réglé par la décision 5.**

### Chat libre

- Créativité par défaut fournie par le serveur avec le modèle (`default_temperature`, simulé dans `js/sim/modeles.js`), repli à 0,2. **Réglé par la décision 12.**
- Deux boutons « Télécharger en JSON » et « en Markdown », un menu « Exporter » sous 768 px. **Réglé par la décision 3.**
- Message « de 8 à 26 secondes » pendant `model_loading` (EXPERIENCE.md), non cité par la story 2.2.
- « Prendre un modèle plus petit » choisit `detail.suggested_model` : aucune story ne le fixe.
- Conversation gardée en mémoire dans l'écran ; le vrai front la relit du serveur (story 2.6).

### Arène

- Chronomètre en « 27 s » (EXPERIENCE.md) et non « 0:42 » (UX-DR20, 03 §3.5).
- Exports : deux boutons CSV et Markdown, un menu « Exporter » sous 768 px. **Réglé par la décision 3.**
- Légendes « Choisissez 4 modèles au plus », « Saisissez une question », « Choisissez un juge » ajoutées (story 3.2 : « au moins 2 »).
- Étiquette « le plus petit des trois » (03) absente des stories ; dérivée des paramètres actifs.
- `lane_status` avec champ `error` : absent du tableau d'événements de `contrat-api.md`.
- Colonne en délai : phrase de la story 3.2, pas le message du code `timeout`.
- Adresse réécrite à la fin du run par `history.replaceState` ; instantané gardé en mémoire.
- Comparaison effacée : seules les mesures de CO₂ restent (AD-13) ; classement et notes non reconstruits (`judge_score` vit dans `run_events`).
- « un seul juge » affiché avec les notes dans tous les cas (story 3.3 ambiguë).
- Bandeau « Comparaison en cours · 2 sur 3 » propre à l'écran : `wl-run-status` ne porte pas ces libellés.
- Réponses simulées par modèle, pas par scénario prédéfini.

### Banc d'essai

- Verdict de format lu dans l'instantané, pas un événement.
- « Délai dépassé (120 s) » (EXPERIENCE.md) : la maquette affiche le message du code `timeout` (« 2 min »).
- Trois scénarios sans format attendu (`GET /api/scenarios` en rend un par scénario) : « Format imposé » désactivé, pas de verdict. **Réglé par la décision 17.**
- Détection d'un modèle sans sortie structurée (`no_structured_output`) fixée par aucun contrat : donnée simulée.
- Boutons « Relancer le test » et « Modifier le test » ajoutés (non demandés par UX-DR29).
- Consigne système du scénario dans un bloc « Consigne » replié. **Réglé par la décision 18.**

### Références

- Scores en pourcentage pour les références (libellé « Part de … » en tête), /100 pour les notes de juge. **Réglé par la décision 5.**
- Groupe à égalité sans rang, tri alphabétique ; le serveur devrait dire quels modèles forment le groupe (champ `group`, hypothèse).
- « Autres modèles mesurés », lien vers le tableau et légende des marques : non demandés par la story 5.8.
- Schéma `qb.results/1` absent du dépôt : structure de `donnees/references.json` hypothétique.
- Ollama arrêté : écran lisible, marques « installé » retirées avec un message.

### Discussion

- Champ `passage` (`{start, end}`) renvoyé par le serveur dans `sources`, simulé, pour surligner le passage (UX-DR11) ; à ajouter au contrat. **Réglé par la décision 21.**
- `retrieval_step` publié au début de chaque étape, durée dans `metrics.search_s` ; le contrat ne précise pas le moment.
- Forme `{citations: [{marker, n}]}` choisie ; sort d'un marqueur non vérifié non précisé.
- « Recherche 0,06 s · Génération 5,8 s » (UX-DR23) : deux `wl-metric` ajoutés après `end()`.
- Avertissement cloud sur les extraits envoyés : absent d'epics.md et d'EXPERIENCE.md (AD-9).
- Pas de « Télécharger » dans le pied (présent en 03 §3.5) : aucune route d'export RAG au contrat.
- « Afficher les sources » par réponse dès la deuxième, un seul panneau, toujours ouvert en large. **Réglé par la décision 22 et 23.**
- Modèle `rag` par défaut : Qwen 3.6 7B, pas « le plus rapide qui tient » (EXPERIENCE.md, Flow 2).

### Base documentaire

- Échec ou doublon par fichier : champs `error` et `skipped` ajoutés à `ingest_progress` ; le contrat ne dit pas comment ils voyagent.
- Un seul « Annuler l'import » au-dessus des lignes (le lot est un seul run). **Réglé par la décision 25.**
- Document `failed` (4.1) dans le tableau, statut « Échec », avec Supprimer ; compteur inchangé. **Réglé par la décision 26.**
- Suppression d'un document confirmée par `wl-confirm-dialog`, comme « Vider ». **Réglé par la décision 24.**
- Supprimer et Vider désactivés pendant un import, au lieu du 409 prévu.
- Pas de code d'erreur au catalogue pour : changement d'embedding avec base non vide, `expected_count` périmé, 409 d'un document à run actif.
- Message d'action de `ram_guard` réécrit pour l'import.

### Évaluation de la qualité

- Limite de 4 modèles absente du contrat.
- Modèles évalués par défaut pris sur `arena` ; le contrat n'en définit pas. **Réglé par la décision 27.**
- `eval_metric` étendu (`by_question`, `n_questions`, `n_unscored`) ; verdicts détaillés pour la question 1 seulement.
- Précision du contexte variable selon le modèle (définition d'EXPERIENCE.md).
- Pas de colonne « Global » (EXPERIENCE.md, question ouverte 4).
- Aucune liste des évaluations passées (EXPERIENCE.md, question ouverte 5, non tranchée) ; le résultat partiel d'un run arrêté est conservé, rouvrable et marqué « partiel ». **Réglé par la décision 28.**

### Agent seul

- `h1` « Agent seul » ; EXPERIENCE.md : « Agents autonomes ».
- Panneau « Étapes » toujours déplié, sans repli hors run. **Réglé par la décision 30.**
- « Arrêter » dans la saisie, pas dans la ligne d'état.
- Pied de réponse réduit : badge, CO₂, étapes, durée, puis « Télécharger » (action gardée). Téléchargement par `Blob` (le vrai front : route d'export, story 6.6). **Réglé par la décision 31.**
- Mention « 10 min » affichée dans le panneau « Étapes » et non dans le dialogue.
- « Validation expirée : email non envoyé. » (EXPERIENCE.md) diffère de `states.email.expired` du catalogue de la maquette.
- Avertissement ajouté pour un modèle sans outils vérifiés. **Réglé par la décision 32.**
- Noms de champs de `step` et `approval_required`, `step` à deux temps, `is_error`, `limit_reached`, `outcome` : propositions à confirmer pour la story 6.1.
- Choix d'outils simulé par intention de la tâche, pas par les cases cochées.

### Équipe d'agents

- `h1` « Équipe d'agents » ; EXPERIENCE.md : « Agents autonomes ».
- « Charger une équipe » en liste et bouton (forme non fixée).
- État « Non lancé » ajouté (EXPERIENCE.md : En attente, En cours, Terminé, Arrêté). La ligne « Terminé · 3 outils · 41 s » exige `agent_totals` côté serveur, non défini. **Réglé par la décision 34.**
- Pic de mémoire dans `metrics` ; la story 6.5 le met dans l'instantané `GET /api/runs/{id}`.
- Mission rouvrable par `/agents/equipe/:run_id`, route ajoutée à UX-DR4 ; l'adresse n'est pas réécrite à la fin d'une mission (l'Arène le fait).
- « Configurer » en volet non modal (colonne de droite en large, sous le schéma en deçà de 1 024 px) ; 5 agents au plus, « Ajouter un agent » grisé avec la raison ; schéma horizontal jusqu'à 4 agents. **Réglé par la décision 35 et 36.**
- Messages de validation par champ hors de `erreurs.json`.
- Agent ajouté joue un scénario générique ; ligne d'agent qui s'ouvre et se referme seule (confort de démo).

### Sobriété et matériel

- Graphique et tableau d'historique en mg seulement (story 5.2) ; la section session suit UX-DR15 (mg ou g).
- Accélérateur, température et bridage venant de `donnees/sobriete.json` : le flux système simulé n'a pas de GPU.
- « Remettre le compteur à zéro » désactivé avec raison quand la session est vide (état non prévu).
- Session en cours absente de l'historique jusqu'à sa clôture ; ni EXPERIENCE.md ni la story 5.2 ne tranchent. **Réglé par la décision 37.**
- Équivalence parlante (distance en voiture) seulement dans le panneau de méthode, avec la source du facteur (fictif : 111 g/km, aligné sur 03 §3.5). **Réglé par la décision 38.**
- Version d'Ollama en légende : ajout de la maquette.

### Modèles

- Catalogue installable incluant les modèles supprimés du poste ; `config/models_catalog.json` n'est pas explicite.
- `wl-model-picker` ne filtre pas sur l'éligibilité d'un usage ni ne propose les modèles de représentation ; contrôle à « Enregistrer » (EXPERIENCE.md : sélecteur filtré).
- Éligibilité (`fits`) figée à l'installation.
- Flow 3 installe `granite4.1:8b` (EXPERIENCE.md : `qwen3.6:7b`, déjà installé dans les modèles simulés).
- Pas de bouton « Fiche du modèle » dans `wl-model-picker` (hypothèse d'EXPERIENCE.md).

## 6. Décisions d'Anaël (2026-10-18)

Anaël a tranché les 43 questions de la version précédente de ce document (même numérotation ; le détail des options reste dans `notes/`). « Appliquée » : la maquette a changé ; « déjà conforme » : elle faisait déjà ce qui est décidé. Chaque décision est visible dans un scénario et vérifiée par `tests/test_decisions.py` ou `tests/test_autonome.py` quand elle change un comportement.

| N° | Décision | État dans la maquette |
|---|---|---|
| 1 | Page autonome `maquette-autonome.html` générée par `construire_autonome.py`, ouvrable en `file://` ; le serveur local passe en second. | Appliquée |
| 2 | Tracés Filled gardés dans la maquette ; le front utilisera les Material Symbols Rounded officiels (`icons.LICENSE.txt`). | Appliquée (documentation) |
| 3 | Exports : deux boutons ; sous 768 px, un seul « Exporter » qui ouvre un menu (Chat et Arène). | Appliquée |
| 4 | Boutons d'action des erreurs déduits du code par le front (AD-18). | Déjà conforme |
| 5 | Scores : pourcentage pour les références, libellé « Part de … » en tête ; /100 pour les notes de juge. | Appliquée (carte de l'Accueil, colonne « Part de réussite ») |
| 6 | Interrupteurs : bascule visuelle partout, comme « Autoriser le cloud ». | Appliquée (Banc, Mode projection, outils des agents) |
| 7 | Thème : Clair (défaut), Sombre, Système. | Déjà conforme |
| 8 | Références : quatrième onglet de l'Arène et carte sur l'Accueil. | Déjà conforme |
| 9 | Titre h1 de l'Accueil : « Accueil ». | Déjà conforme |
| 10 | Cartes de l'Accueil : nom court en titre, nom long en sous-titre. | Appliquée |
| 11 | « Lancer une comparaison » reste actif sans modèle local prêt ; l'Arène dit quoi faire. | Déjà conforme |
| 12 | Créativité par défaut du Chat fournie par le serveur avec le modèle, repli 0,2. | Appliquée (simulée dans `js/sim/modeles.js`) |
| 13 | 409 rejoint : le message tapé reste dans le champ. | Déjà conforme |
| 14 | Après une comparaison : matrice d'abord, tableau derrière « Voir le tableau ». | Déjà conforme |
| 15 | 4 modèles à 1 440 px : 4 colonnes, réponse repliée sur 4 lignes, dépliable. | Appliquée (repli à 4 lignes) |
| 16 | Configuration de l'Arène remplacée par un résumé pendant l'exécution. | Déjà conforme |
| 17 | Scénario sans format (Banc) : interrupteur désactivé avec la raison, pas de verdict. | Déjà conforme |
| 18 | Consigne du scénario (Banc) dans un bloc « Consigne » replié. | Appliquée |
| 19 | Références : « Comparer ces modèles » ouvre l'Arène présélectionnée sur les modèles installés du groupe. | Appliquée |
| 20 | Références : cartes par défaut. | Déjà conforme |
| 21 | Surlignage : le serveur renvoie `passage` (début, fin) dans `sources`. | Appliquée (`{start, end}` simulé) |
| 22 | Panneau de sources toujours ouvert en large. | Appliquée |
| 23 | Plusieurs réponses : « Afficher les sources » par réponse, un seul panneau. | Déjà conforme |
| 24 | Supprimer un document : confirmation `wl-confirm-dialog`, comme « Vider ». | Appliquée |
| 25 | Annuler un import : un seul « Annuler l'import » au-dessus des lignes. | Appliquée |
| 26 | Documents en échec aussi dans le tableau, statut « Échec », avec Supprimer. | Appliquée |
| 27 | Évaluation : les trois petits modèles locaux de l'Arène présélectionnés. | Déjà conforme |
| 28 | Évaluation arrêtée : résultat partiel conservé, rouvrable, marqué « partiel ». | Appliquée |
| 29 | Évaluation, question vide : bouton désactivé avec la raison. | Déjà conforme |
| 30 | Panneau « Étapes » sous 1 024 px : toujours déplié. | Déjà conforme |
| 31 | Pied de réponse d'agent réduit : badge, CO₂, étapes, durée. | Appliquée (« Télécharger » gardé après le pied, c'est une action) |
| 32 | Modèle sans outils vérifiés : avertir et laisser lancer. | Déjà conforme |
| 33 | Journal brut d'une mission : lignes horaires lisibles. | Déjà conforme |
| 34 | Agent qui n'a pas pu s'exécuter : « Non lancé ». | Déjà conforme |
| 35 | « Configurer » (Équipe) : volet non modal qui laisse le schéma visible. | Appliquée |
| 36 | Équipe : 5 agents au plus, message clair au-delà. | Appliquée (message précisé, relié au bouton grisé) |
| 37 | Sobriété : session en cours absente de l'historique jusqu'à sa clôture. | Déjà conforme |
| 38 | Équivalence parlante du CO₂ seulement dans le panneau de méthode, avec la source du facteur. | Appliquée (facteur fictif : 111 g/km) |
| 39 | Historique sur écran étroit : tableau par défaut sous 640 px. | Appliquée |
| 40 | Fiche modèle : panneau à droite dès 1 120 px, au-dessus de la liste en deçà. | Déjà conforme |
| 41 | Supprimer un modèle choisi comme défaut : message dans le dialogue de confirmation. | Appliquée |
| 42 | Installer un modèle qui ne tient pas : bouton « Installer quand même ». | Appliquée (catalogue et fiche) |
| 43 | Tableau « Sur ce poste » : Usage et Origine repliées sous 1 024 px. | Appliquée (bouton pour les afficher) |

Scénarios ajoutés pour rendre les décisions visibles : `consigne-depliee` (Banc), `comparer-ces-modeles` (Références), `suppression-confirmation` (Base documentaire), `partiel-rouvert` (Évaluation), `configurer-cinq-agents` (Équipe), `methode-equivalence` (Sobriété).

## 7. Vérifier

Depuis la racine du dépôt :

```
.venv\Scripts\python.exe -m pytest docs/maquette-v2/tests -q --tb=short
```

Les tests pilotent Edge ou Chromium (variable `WAVELOCALAI_E2E_CHROMIUM`, sinon Edge à son emplacement habituel). Ils contrôlent :

- les routes de `donnees/routes.json` et la coquille ;
- chaque scénario exporté par chaque écran, avec axe-core sans exclusion (clair, sombre, projection) ;
- 320 à 1 440 px sans défilement horizontal de la page ;
- le clavier, dont l'ouverture et la fermeture du panneau Scénarios ;
- les états globaux et les parcours de bout en bout ;
- le simulateur (reprise, coupure de connexion, arrêt) ;
- les décisions d'Anaël (`test_decisions.py`) ;
- la page autonome (`test_autonome.py`) : à jour par rapport aux sources, puis ouverte en `file://` (toutes les routes, Flow 2, axe) ;
- aucune erreur ni avertissement de console, aucune requête hors de `127.0.0.1` (hors de la page autonome en `file://`).

Dernier résultat (2026-10-19) : 167 tests passés, dont la page autonome et les décisions.

## 8. Détail

Le détail par écran (états, écarts, questions d'origine et décisions) est dans `notes/` : une note par écran, `coquille.md` et `revue.md` (revue de la maquette).
