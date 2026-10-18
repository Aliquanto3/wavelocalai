# Maquette du front de WaveLocalAI v2

## 1. Objet

Maquette HTML interactive du front définitif de la v2, à valider avant le codage complet. Les contenus sont fictifs (modèles, documents, mesures, sociétés). Rien n'est appelé hors du dossier : aucune requête hors de `127.0.0.1`, aucun serveur applicatif, aucun fichier de l'utilisateur lu.

Ce document liste ce que la maquette couvre, les écarts avec le contrat (sans les trancher) et les questions qui reviennent à Anaël.

## 2. Ouvrir

- Windows : double-clic sur `ouvrir.cmd`.
- Autre cas : `python serveur.py` depuis `docs/maquette-v2/`, puis l'adresse affichée.

Un double-clic sur `index.html` ne fonctionne pas. Chromium et Edge bloquent les modules ES et `fetch` en `file://`. La page l'explique et donne la marche à suivre.

`serveur.py` remplace `python -m http.server` : il écoute sur `127.0.0.1`, prend un port libre et fixe les types MIME. Sous Windows, `http.server` sert parfois les `.js` en `text/plain`, que les modules refusent.

Dans la maquette :

- Le bouton « Scénarios (maquette) », en bas à droite, force un état d'écran, un état global (Ollama arrêté, cloud, connexion perdue, serveur redémarré, garde-fou mémoire, premier chargement lent, aucun modèle local, onglet masqué, thème, projection, vitesse) ou joue un parcours de bout en bout.
- Le catalogue des états communs est à `#/maquette/etats`.

Version en ligne (artifact privé) : LIEN_ARTIFACT

## 3. Structure

- `index.html`, `serveur.py`, `ouvrir.cmd` : point d'entrée et serveur local.
- `js/` : coquille (`shell/`), écrans (`screens/`), composants communs (`components/`), simulateur de flux (`sim/`), scénarios globaux et parcours (`scenarios/`).
- `css/`, `tokens.css`, `fonts/`, `icons.svg` : styles, jetons, police Inter, sprite d'icônes.
- `donnees/` : routes, parcours, données fictives par écran, flux d'événements (`flux/`), catalogue d'erreurs. Le nom évite `data/`, ignoré par `.gitignore`.
- `i18n/` : textes en français.
- `notes/` : une note par écran (états, écarts, questions) et `revue.md`.
- `tests/` : suite pytest et Playwright.

Les règles pour ajouter ou modifier un écran sont dans `docs/maquette-v2/CONVENTIONS.md`.

## 4. Écrans et états couverts

Le nombre de scénarios est celui des `scenarios` exportés par chaque module d'écran.

| Chemin | Écran | Scénarios |
|---|---|---|
| `/` | Accueil | 10 |
| `/arene/chat` | Chat libre | 23 |
| `/arene/comparer`, `/arene/comparer/:run_id` | Arène | 33 |
| `/arene/banc`, `/arene/banc/:run_id` | Banc d'essai | 27 |
| `/arene/references` | Références | 9 |
| `/documents` | Discussion | 28 |
| `/documents/base` | Base documentaire | 29 |
| `/documents/evaluation`, `/documents/evaluation/:run_id` | Évaluation de la qualité | 25 |
| `/agents/seul` | Agent seul | 31 |
| `/agents/equipe`, `/agents/equipe/:run_id` | Équipe d'agents | 29 |
| `/sobriete` | Sobriété et matériel | 20 |
| `/modeles`, `/modeles/:tag` | Modèles | 36 |
| `/maquette/etats` | Catalogue des états (propre à la maquette) | 3 |

Onze scénarios globaux s'y ajoutent dans le panneau (voir section 2).

### Coquille et barre haute

- Pastille Ollama (vérification, disponible, ne répond pas, inconnu) et son panneau (version, mémoire, modèles chargés, « Réessayer »).
- Interrupteur « Autoriser le cloud » (store seulement, perdu au rechargement, pied de page qui suit).
- CO₂ de session et son panneau (total, Local, Cloud, non mesurables).
- Menu Affichage : clair, sombre, système, projection. Menu replié sous 1 024 px.
- Bandeaux « Connexion au serveur perdue » (après trois échecs) et « Le serveur a redémarré ».
- États communs du catalogue : vide, chargement lent, 409 rejoint, étapes d'un run, score et « non évalué », CO₂ mesuré, estimé ou « non mesurable », garde-fou mémoire, confirmation de « Vider », chaque code de `donnees/erreurs.json`.

### Familles d'états par écran

- **Accueil** : nominal, squelettes, Ollama arrêté (avec ou sans cloud), aucun modèle local, cloud autorisé, connexion perdue, mémoire haute, onglet masqué, étape du Flow 1.
- **Chat libre** : vide, réponse locale, en cours, arrêt, cloud estimé ou non mesurable, conversation rouverte, reprise au retour, 409, relance automatique, erreurs (interrompue, délai, Ollama, cloud, clé absente, cloud non autorisé ou retiré), garde-fou mémoire, aucun modèle, connexion perdue, serveur redémarré.
- **Arène** : configuration (moins de deux modèles, trop de modèles, juge peu fiable), exécution (chargement lent, arrêt, reprise, 409), résultats (classement, matrice, tableau, réponse entière, focus, verdict local/cloud, non mesurable, délai, non évalué, juge indisponible, colonne en échec), erreurs et gardes, résultat conservé, effacé ou introuvable.
- **Banc d'essai** : configuration (format attendu, entrée modifiée, format imposé indisponible), résultats (format respecté ou non, sortie non JSON, sans format, concise, cloud), exécution, erreurs et gardes, résultat conservé ou introuvable.
- **Références** : cartes, tableau trié, chargement, fichier absent ou de format inconnu, aucun usage publié, aucun modèle installé, Ollama arrêté.
- **Discussion** : base vide, sources et citations, ouverture d'une source, stratégies (HyDE, Self-RAG), reclassement, nombre d'extraits, cloud avec avertissement, conversation rouverte, indexation en cours, erreurs et gardes.
- **Base documentaire** : base vide ou remplie, import (un fichier, plusieurs, progression, échec, format refusé, doublon, annulation), filtrage et tri, suppression, « Vider » (confirmation, annulation), réglages, changement d'embedding.
- **Évaluation** : formulaire, jeu de questions, base vide, évaluation en cours, détails de fidélité et de précision du contexte, matrice, jeu terminé, non évalué, délai, arrêt, résultat rouvert ou introuvable.
- **Agent seul** : vide, outil indisponible, modèle sans outils, étapes en cours, tâche terminée, étape dépliée, erreur d'outil, bornes atteintes, validation d'email (envoyé, annulé, expirée, non coché), arrêt, cloud, redémarrage en attente de validation.
- **Équipe d'agents** : équipe prête, sans agent, sujet vide, équipe modifiée, panneau Configurer (avec erreurs), mission en cours, rapport final, arrêtée (tôt ou tard), rouverte, validation d'email, 409 venant d'un agent seul.
- **Sobriété** : nominal, squelettes, Ollama arrêté, sans accélérateur, bridage thermique, mémoire haute, session vide, non mesurable, en grammes, réponse en direct, remise à zéro, historique (7 jours, 30 jours, tout, tableau, période vide, vide).
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
- Ouverture par serveur local et non par double-clic (voir section 2 et question 1).
- Thème « Système » ajouté au menu Affichage : UX-DR2 et la story 1.8 ne prévoient que clair et sombre.
- Route `#/arene/references` (FR47) et route `#/agents/equipe/:run_id` ajoutées aux onze routes d'UX-DR4. Les sous-routes de Banc, Évaluation et Modèles viennent d'EXPERIENCE.md.
- Code d'erreur `generation_interrupted` (`errors.py`) au lieu de `interrupted` (UX-DR16).
- Message du code `timeout` : la maquette cite le délai (« 2 min »), comme 03 §3.8, ce qu'`errors.py` ne fait pas. Texte de `cloud_not_allowed` : celui de 03 §3.8, plus court que celui d'`errors.py`.
- Boutons d'action des erreurs dans `donnees/erreurs.json` (champ `buttons`) ; AD-18 les fait déduire du code par l'écran.
- `pull_failed` (story 5.3) et `model_in_use` sont au catalogue de la maquette ; `errors.py` ne les a pas encore.
- Icônes : sprite de 37 symboles, dont 18 tracés Material Icons (Filled) ajoutés à l'intégration, et non les Material Symbols Rounded officiels (voir `icons.LICENSE.txt`). DESIGN.md cite `leaderboard` pour l'Arène, le sprite a `swords`.
- Composants lus dans des branches `feat/v2-*` non fusionnées, pas dans `master` ; la maquette peut diverger de leur version finale.
- Contrat d'écran : `mount(host, ctx)` qui rend `unmount` (AD-20), avec `render(root, ctx)` en alias.
- Verdict de l'Arène (story 3.5) et verdict de format du Banc lus dans l'instantané du run ; `contrat-api.md` ne dit pas où ils vivent.
- Noms de champs d'événements (`step`, `approval_required`, `lane_status.error`, `ingest_progress.error`, `eval_metric`, `citations`) : lecture de `contrat-api.md`, qui ne donne que des libellés.
- Défauts restants de `notes/revue.md` : étiquette de la matrice de l'Arène pouvant chevaucher une bulle voisine (`charts.js`) ; note du classement de l'Arène non alignée quand un badge s'ajoute (`arene.css`).
- Le panneau Scénarios, ouvert, peut recouvrir du contenu (outil de maquette, replié par défaut, hors charte).

### Coquille

- Dans le front définitif, tous les modules sont disponibles : la maquette n'a aucun lien « Pas encore disponible ». Pas d'autre écart propre à la coquille au-delà du transverse.

### Accueil

- `h1` « Accueil » (03 §3.9) ; EXPERIENCE.md place le titre « WaveLocalAI » en tête.
- Libellés longs des liens (« Assistant documentaire », « Agents autonomes », « Sobriété et matériel », maquette 03 §3.5) alors que le menu dit « Documents », « Agents », « Sobriété » ; EXPERIENCE.md veut un nom unique partout.
- Carte « Références » ajoutée, avec l'icône de l'Arène (DESIGN.md : icône jamais partagée).
- Carte Mode : « N appels cloud dans cette session », compteur qu'aucune story ne définit.
- Score de la carte Références en « /100 » ; l'écran Références l'affiche en pourcentage.

### Chat libre

- Créativité par défaut à 0,7 (03 §3.5) ; la branche `feat/v2-ecran-chat` utilise 0,2.
- Deux boutons « Télécharger en JSON » et « en Markdown » ; UX-DR21 ne fixe pas la forme.
- Message « de 8 à 26 secondes » pendant `model_loading` (EXPERIENCE.md), non cité par la story 2.2.
- « Prendre un modèle plus petit » choisit `detail.suggested_model` : aucune story ne le fixe.
- Conversation gardée en mémoire dans l'écran ; le vrai front la relit du serveur (story 2.6).

### Arène

- Chronomètre en « 27 s » (EXPERIENCE.md) et non « 0:42 » (UX-DR20, 03 §3.5).
- Exports : deux boutons CSV et Markdown (« Exporter (CSV, Markdown) »).
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
- Trois scénarios sans format attendu (`GET /api/scenarios` en rend un par scénario) : « Format imposé » désactivé, pas de verdict.
- Détection d'un modèle sans sortie structurée (`no_structured_output`) fixée par aucun contrat : donnée simulée.
- Boutons « Relancer le test » et « Modifier le test » ajoutés (non demandés par UX-DR29).
- Consignes système des scénarios non montrées.

### Références

- Scores en pourcentage (AD-22) contre « /100 » sur l'Accueil et dans EXPERIENCE.md (une seule échelle).
- Groupe à égalité sans rang, tri alphabétique ; le serveur devrait dire quels modèles forment le groupe (champ `group`, hypothèse).
- « Autres modèles mesurés », lien vers le tableau et légende des marques : non demandés par la story 5.8.
- Schéma `qb.results/1` absent du dépôt : structure de `donnees/references.json` hypothétique.
- Ollama arrêté : écran lisible, marques « installé » retirées avec un message.

### Discussion

- Champ `passage` ajouté aux sources (hors contrat) pour surligner le passage (UX-DR11).
- `retrieval_step` publié au début de chaque étape, durée dans `metrics.search_s` ; le contrat ne précise pas le moment.
- Forme `{citations: [{marker, n}]}` choisie ; sort d'un marqueur non vérifié non précisé.
- « Recherche 0,06 s · Génération 5,8 s » (UX-DR23) : deux `wl-metric` ajoutés après `end()`.
- Avertissement cloud sur les extraits envoyés : absent d'epics.md et d'EXPERIENCE.md (AD-9).
- Pas de « Télécharger » dans le pied (présent en 03 §3.5) : aucune route d'export RAG au contrat.
- « Afficher les sources » par réponse dès la deuxième ; panneau repliable en large.
- Modèle `rag` par défaut : Qwen 3.6 7B, pas « le plus rapide qui tient » (EXPERIENCE.md, Flow 2).

### Base documentaire

- Échec ou doublon par fichier : champs `error` et `skipped` ajoutés à `ingest_progress` ; le contrat ne dit pas comment ils voyagent.
- « Annuler » par fichier (UX-DR22) arrête en fait le lot restant.
- Document `failed` (4.1) absent du tableau, visible dans la ligne d'import seulement.
- Suppression d'un document sans confirmation (EXPERIENCE.md : seulement « Vider » et l'email).
- Supprimer et Vider désactivés pendant un import, au lieu du 409 prévu.
- Pas de code d'erreur au catalogue pour : changement d'embedding avec base non vide, `expected_count` périmé, 409 d'un document à run actif.
- Message d'action de `ram_guard` réécrit pour l'import.

### Évaluation de la qualité

- Limite de 4 modèles absente du contrat.
- Modèles évalués par défaut pris sur `arena` ; le contrat n'en définit pas.
- `eval_metric` étendu (`by_question`, `n_questions`, `n_unscored`) ; verdicts détaillés pour la question 1 seulement.
- Précision du contexte variable selon le modèle (définition d'EXPERIENCE.md).
- Pas de colonne « Global » (EXPERIENCE.md, question ouverte 4).
- Aucune liste des évaluations passées (EXPERIENCE.md, question ouverte 5) ; le résultat partiel d'un run arrêté n'est pas conservé, le contrat ne le dit pas.

### Agent seul

- `h1` « Agent seul » ; EXPERIENCE.md : « Agents autonomes ».
- Panneau « Étapes » toujours déplié, sans repli hors run.
- « Arrêter » dans la saisie, pas dans la ligne d'état.
- Pied de réponse du Chat plus « N étapes » et « Télécharger » ; EXPERIENCE.md liste badge, CO₂, étapes, durée, Télécharger. Téléchargement par `Blob` (le vrai front : route d'export, story 6.6).
- Mention « 10 min » affichée dans le panneau « Étapes » et non dans le dialogue.
- « Validation expirée : email non envoyé. » (EXPERIENCE.md) diffère de `states.email.expired` du catalogue de la maquette.
- Avertissement ajouté pour un modèle sans outils vérifiés.
- Noms de champs de `step` et `approval_required`, `step` à deux temps, `is_error`, `limit_reached`, `outcome` : propositions à confirmer pour la story 6.1.
- Choix d'outils simulé par intention de la tâche, pas par les cases cochées.

### Équipe d'agents

- `h1` « Équipe d'agents » ; EXPERIENCE.md : « Agents autonomes ».
- « Charger une équipe » en liste et bouton (forme non fixée).
- État « Non lancé » ajouté (EXPERIENCE.md : En attente, En cours, Terminé, Arrêté). La ligne « Terminé · 3 outils · 41 s » exige `agent_totals` côté serveur, non défini.
- Pic de mémoire dans `metrics` ; la story 6.5 le met dans l'instantané `GET /api/runs/{id}`.
- Mission rouvrable par `/agents/equipe/:run_id`, route ajoutée à UX-DR4 ; l'adresse n'est pas réécrite à la fin d'une mission (l'Arène le fait).
- « Configurer » en dialogue modal à droite ; 5 agents au plus (invention) ; schéma horizontal jusqu'à 4 agents.
- Messages de validation par champ hors de `erreurs.json`.
- Agent ajouté joue un scénario générique ; ligne d'agent qui s'ouvre et se referme seule (confort de démo).

### Sobriété et matériel

- Graphique et tableau d'historique en mg seulement (story 5.2) ; la section session suit UX-DR15 (mg ou g).
- Accélérateur, température et bridage venant de `donnees/sobriete.json` : le flux système simulé n'a pas de GPU.
- « Remettre le compteur à zéro » désactivé avec raison quand la session est vide (état non prévu).
- Session en cours absente de l'historique jusqu'à sa clôture ; ni EXPERIENCE.md ni la story 5.2 ne tranchent.
- Pas d'équivalence parlante (03 §3.5 : « environ 3,7 m en voiture ») ; question ouverte 3 d'EXPERIENCE.md.
- Version d'Ollama en légende : ajout de la maquette.

### Modèles

- Catalogue installable incluant les modèles supprimés du poste ; `config/models_catalog.json` n'est pas explicite.
- `wl-model-picker` ne filtre pas sur l'éligibilité d'un usage ni ne propose les modèles de représentation ; contrôle à « Enregistrer » (EXPERIENCE.md : sélecteur filtré).
- Éligibilité (`fits`) figée à l'installation.
- Flow 3 installe `granite4.1:8b` (EXPERIENCE.md : `qwen3.6:7b`, déjà installé dans les modèles simulés).
- Pas de bouton « Fiche du modèle » dans `wl-model-picker` (hypothèse d'EXPERIENCE.md).

## 6. Questions pour Anaël

Chaque question porte sur un choix que le contrat ne fixe pas. Les recommandations sont celles des notes d'écran.

### Transverse

1. Ouverture par double-clic sur `index.html`, impossible en `file://`. (A) Garder le serveur local (`ouvrir.cmd`, `serveur.py`) ; (B) générer une page autonome par un script Python qui inline tout (CSS, JS, JSON, polices, sprite) ; (C) réécrire en scripts classiques sans modules ES. Recommandation : A pour la maquette, B si elle doit circuler hors du dépôt (un seul fichier, aucun écart de code).
2. Icônes ajoutées en tracés Material Icons (Filled). (A) Les remplacer par les Material Symbols Rounded officiels avant le codage ; (B) garder les tracés pour la maquette, remplacer dans le front ; (C) garder partout. Recommandation : B, la maquette n'en dépend pas.
3. Forme des exports (Chat : JSON et Markdown ; Arène : CSV et Markdown). (A) deux boutons ; (B) un bouton qui ouvre un menu ; (C) un format à l'écran, l'autre en second. Recommandation : A, B sous 768 px.
4. Boutons d'action des erreurs. (A) déduits du code par le front (AD-18) ; (B) champ `actions` dans l'enveloppe du serveur. Recommandation : A tant que la liste reste courte.
5. Échelle des scores (Références en pourcentage, Accueil en /100). (A) pourcentage partout ; (B) /100 partout ; (C) pourcentage pour les références, /100 pour les notes de juge. Recommandation : C, avec le libellé « Part de … » en tête.
6. Interrupteurs (Banc d'essai). (A) bascule visuelle ; (B) cases à cocher ; (C) segments Oui / Non. Recommandation : A.

### Coquille et Accueil

7. Thème « Système ». (A) le garder, défaut « Clair » ; (B) le garder et en faire le défaut ; (C) le retirer (UX-DR2 strict). Recommandation : A.
8. Place de « Références ». (A) quatrième onglet de l'Arène (FR47) ; (B) section de Modèles ; (C) carte d'Accueil seulement. Recommandation : A, avec la carte d'Accueil en plus.
9. Titre de l'Accueil. (A) « Accueil » ; (B) « WaveLocalAI » ; (C) « WaveLocalAI » en `h1`, « Accueil » dans l'onglet. Recommandation : A (cohérence avec les autres écrans).
10. Noms des modules sur l'Accueil. (A) noms longs (03) ; (B) noms courts du menu ; (C) court en titre, long en sous-titre. Recommandation : C.
11. « Lancer une comparaison » sans modèle local prêt. (A) actif, l'Arène dit quoi faire ; (B) désactivé avec la raison. Recommandation : A (03 : les liens restent actifs).

### Arène (Chat libre, Arène, Banc d'essai, Références)

12. Créativité par défaut du Chat. (A) 0,7 (03) ; (B) 0,2 (branche livrée) ; (C) défaut fourni par le serveur avec le modèle. Recommandation : C, sinon B.
13. 409 rejoint : le message tapé reste dans le champ. (A) le garder ; (B) proposer de l'envoyer à la fin du run suivi. Recommandation : A.
14. Après une comparaison. (A) matrice, tableau derrière « Voir le tableau » ; (B) tableau d'abord ; (C) les deux côte à côte dès 1 440 px. Recommandation : A pour la démo, C en projection.
15. Colonnes à 4 modèles sur 1 440 px. (A) 4 colonnes serrées ; (B) 2 colonnes visibles puis défilement ; (C) 4 colonnes, réponse repliée sur 4 lignes. Recommandation : C.
16. Configuration de l'Arène pendant l'exécution. (A) remplacée par un résumé ; (B) grisée et visible ; (C) résumé avec configuration repliable. Recommandation : A.
17. Scénario sans format (Banc). (A) interrupteur désactivé avec raison, pas de verdict ; (B) interrupteur masqué ; (C) proposer un format libre. Recommandation : A.
18. Consigne du scénario (Banc). (A) non montrée ; (B) dans « Format attendu » ; (C) bloc « Consigne » replié. Recommandation : C, pour expliquer la réponse du modèle.
19. Références : passer à l'action. (A) rien ; (B) « Comparer ces modèles » ouvre l'Arène présélectionnée sur les modèles installés du groupe ; (C) lien « Installer » vers Modèles pour ceux qui manquent. Recommandation : B.
20. Références : cartes ou tableau par défaut. (A) cartes ; (B) tableau ; (C) cartes en projection, tableau sinon. Recommandation : A.

### Documents

21. Surlignage du passage d'une source. (A) le serveur renvoie `passage` (début, fin) ; (B) le front surligne les mots de la question ; (C) aucun surlignage. Recommandation : A.
22. Panneau de sources en large. (A) toujours ouvert ; (B) repliable ; (C) colonne fixe. Recommandation : A (la vérification de la source est le climax du Flow 2).
23. Plusieurs réponses, un seul panneau. (A) bouton « Afficher les sources » par réponse ; (B) un panneau par réponse ; (C) sources de la dernière réponse seulement. Recommandation : A.
24. Supprimer un document. (A) sans confirmation ; (B) avec `wl-confirm-dialog` comme « Vider » ; (C) sans confirmation mais avec « Annuler » dans le message. Recommandation : B (irréversible).
25. Annuler un import. (A) un bouton par ligne qui arrête tout le lot ; (B) un seul « Annuler l'import » au-dessus des lignes ; (C) un run par fichier côté serveur. Recommandation : B.
26. Documents en échec. (A) seulement dans la ligne d'import ; (B) aussi dans le tableau, statut « Échec » et Supprimer. Recommandation : B.
27. Modèles évalués par défaut (Évaluation). (A) trois petits modèles locaux de l'Arène ; (B) le défaut `rag` seul ; (C) vide. Recommandation : A.
28. Résultat partiel d'un run arrêté (Évaluation). (A) non conservé ; (B) conservé, rouvrable, marqué « partiel ». Recommandation : B.
29. Question vide (Évaluation). (A) bouton désactivé avec la raison ; (B) champ prérempli par une question d'exemple. Recommandation : A pour le produit, B pour la démo d'atelier.

### Agents

30. Panneau « Étapes » sous 1 024 px. (A) toujours déplié ; (B) repliable, déplié pendant un run ; (C) tiroir. Recommandation : A.
31. Pied de réponse d'une tâche d'agent. (A) pied du Chat plus étapes ; (B) pied réduit (badge, CO₂, étapes, durée) ; (C) pied du Chat sans étapes. Recommandation : B (le débit agrégé de plusieurs appels dit peu).
32. Modèle sans outils vérifiés. (A) avertir et laisser lancer ; (B) bloquer le lancement ; (C) ne pas le proposer. Recommandation : A.
33. Journal brut d'une mission. (A) lignes horaires lisibles ; (B) événements JSON bruts ; (C) sortie texte du serveur. Recommandation : A.
34. Agent qui n'a pas pu s'exécuter. (A) « Non lancé » ; (B) rester « En attente ». Recommandation : A.
35. Forme de « Configurer ». (A) volet modal à droite ; (B) volet non modal qui laisse le schéma visible ; (C) page dédiée. Recommandation : B si le schéma doit rester lisible pendant l'édition, sinon A.
36. Nombre maximal d'agents d'une équipe. (A) 5 ; (B) 8 avec schéma vertical au-delà de 5 ; (C) illimité. Recommandation : A.

### Sobriété

37. Session en cours dans l'historique. (A) absente jusqu'à sa clôture ; (B) dernière barre marquée « en cours » ; (C) ligne distincte au-dessus du graphique. Recommandation : A (le total est déjà au-dessus).
38. Équivalence parlante du CO₂. (A) aucune ; (B) « environ N m en voiture » avec la source du facteur en aide ; (C) dans le panneau de méthode seulement. Recommandation : C.
39. Graphique d'historique sur écran étroit. (A) défilement horizontal dans une région focalisable ; (B) barres horizontales empilées ; (C) tableau par défaut sous 640 px. Recommandation : C.

### Modèles

40. Fiche d'un modèle. (A) panneau à droite dès 1 120 px, au-dessus de la liste en deçà ; (B) page dédiée sans liste ; (C) tiroir modal. Recommandation : A.
41. Défaut dont le modèle est supprimé. (A) retombe sur la règle avec sa raison (story 5.4) ; (B) confirmation avant de supprimer un modèle choisi comme défaut. Recommandation : B, un message dans le dialogue suffit.
42. Installer un modèle qui ne tient pas. (A) permis sans avertissement supplémentaire ; (B) dialogue de confirmation chiffré ; (C) bouton « Installer quand même ». Recommandation : C.
43. Tableau « Sur ce poste » à 9 colonnes. (A) défilement horizontal dans une région focalisable ; (B) colonnes secondaires (Usage, Origine) repliées sous 1 024 px ; (C) cartes empilées. Recommandation : B.

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
- aucune erreur ni avertissement de console, aucune requête hors de `127.0.0.1`.

Dernier résultat : 146 tests passés.

## 8. Détail

Le détail par écran (états, écarts, questions d'origine) est dans `notes/` : une note par écran, `coquille.md` et `revue.md` (revue de la maquette).
