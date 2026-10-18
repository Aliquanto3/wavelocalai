---
workflow: bmad-correct-course
date: '2026-10-19'
mode: 'batch, non interactif (Anaël a délégué ; décisions conservatrices consignées)'
trigger: 'Maquette validée du front v2 et 43 décisions d''Anaël du 2026-10-18 (branche docs/maquette-front-v2, PR #58)'
scope: 'Modéré : ajustement direct du backlog, deux stories de suite, aucune story retirée'
---

# Proposition de changement de sprint : report de la maquette v2 dans le contrat

## 1. Résumé du problème

La maquette interactive du front v2 (`docs/maquette-v2/`, PR #58) a été validée par Anaël le 2026-10-18, qui a tranché les 43 questions qu'elle posait (README de la maquette, §6). Ces décisions précisent ou modifient le contrat du front : routes, thème, interrupteurs, exports, échelle des scores, comportement de la Discussion, de la Base documentaire, des Agents, de l'Évaluation, de Sobriété et de Modèles, et quatre points du contrat d'API (`default_temperature`, `passage` dans `sources`, route `#/agents/equipe/<run_id>`, codes `pull_failed`, `model_in_use`, `run_not_found`).

Tant qu'elles ne sont que dans la maquette, le run autonome implémente des stories dont les critères les contredisent ou les ignorent (par exemple un « Annuler » par fichier dans la 4.2, une créativité fixée à 0,2 dans le Chat livré, un thème sans « Système »). Le run s'est d'ailleurs donné un garde-fou : aucune story de l'Epic 5 ou suivante avant la fusion de ce correct course.

Preuves : README de la maquette §5 (écarts) et §6 (décisions), `notes/*.md` de la branche `origin/docs/maquette-front-v2`, tests `tests/test_decisions.py` de la maquette ; état du code sur `master` (5ab78e4) : `core/theme.js` (clair et sombre seulement), case à cocher « Mode projection », `routes_chat.py` (température 0,2 fixe), liens de l'Accueil sans nom long.

## 2. Analyse d'impact

### Checklist (mode non interactif)

| Section | Statut | Constat |
|---|---|---|
| 1. Déclencheur | [x] | Maquette validée + 43 décisions ; nouvelles exigences précisées, pas d'échec technique. |
| 2. Impact sur les epics | [x] | Epics 1 et 2 livrées : deux stories de suite (1.12, 2.7). Epics 3 et 4 en cours : critères ajoutés à 3.2, 3.3, 4.1, 4.2 et au backlog. Epics 5 à 8 : critères ajustés, aucune story ajoutée ni retirée, ordre inchangé. |
| 3. Conflits d'artefacts | [x] | `EXPERIENCE.md`, `DESIGN.md`, `epics.md`, `contrat-api.md`, spine (AD-7, une phrase), `03-ux-front.md` §3 (note et table d'IA). SPEC.md (tient lieu de PRD) : aucun changement, le périmètre ne bouge pas. |
| 4. Voie retenue | [x] | Ajustement direct (option 1). Pas de retour arrière, pas de révision du MVP. |
| 5. Proposition | [x] | Ce document. |
| 6. Revue et passage de main | [x] | Validation d'Anaël remplacée par la règle du run : option la plus conservatrice, écarts non réglés laissés ouverts (§7 (d)). |

### Impact par epic

- **Epic 1 (livrée)** : thème « Système » (D-7), « Mode projection » en interrupteur (D-6), icônes Material Symbols Rounded (D-2), Accueil avec nom court et nom long (D-10), routes de la maquette dans le registre (D-8). → story 1.12.
- **Epic 2 (livrée)** : créativité par défaut fournie par le serveur avec le modèle (D-12), menu « Exporter » sous 768 px (D-3), message de premier chargement (UX-DR17), 409 qui garde le message (D-13, déjà conforme). → story 2.7.
- **Epic 3 (en cours)** : 4 colonnes repliées à 1 440 px (D-15), résumé pendant l'exécution (D-16), légendes de bouton désactivé, Arène qui dit quoi faire sans modèle local (D-11), matrice d'abord (D-14), exports (D-3), `run_not_found` à la réouverture.
- **Epic 4 (en cours)** : un seul « Annuler l'import » (D-25), documents en échec dans le tableau (D-26), suppression confirmée (D-24), `passage` dans `sources` (D-21), panneau des sources toujours ouvert en large (D-22), « Afficher les sources » par réponse (D-23).
- **Epic 5** : équivalence CO₂ dans la méthode seulement (D-38), session en cours hors historique (D-37), tableau sous 640 px (D-39), « Installer quand même » (D-42), colonnes repliées (D-43), fiche à 1 120 px (D-40), défaut signalé à la suppression (D-41), `model_in_use`, références en pourcentage (D-5), cartes par défaut (D-20), « Comparer ces modèles » (D-19).
- **Epic 6** : outils en interrupteurs (D-6), avertissement sans outils vérifiés (D-32), panneau « Étapes » toujours déplié (D-30), pied réduit (D-31), journal lisible (D-33), « Non lancé » et `agent_totals` (D-34), « Configurer » non modal (D-35), 5 agents au plus (D-36), route `#/agents/equipe/<run_id>` (D-8).
- **Epic 7** : modèles évalués sur le défaut `arena` (D-27), résultat partiel conservé (D-28), question vide (D-29), consigne repliée (D-18), scénario sans format (D-17), interrupteurs (D-6).
- **Epic 8** : 8.2 couvre toutes les routes du registre et le thème « Système ». 8.1, 8.3, 8.4 : aucun changement.

### Impact technique

Petites additions de contrat, toutes additives : champ `default_temperature` de `GET /api/models` ; champ `passage` de `sources` ; `agent_totals` sur l'étape `answer` d'un agent d'équipe ; `format_verdict` et `partial` dans l'instantané ; `instruction` et format nullable dans `GET /api/scenarios` ; codes `run_not_found`, `pull_failed` (`detail.cause`), `model_in_use`. Aucune migration fusionnée ne change (AD-12). Aucun nouveau type d'événement.

## 3. Voie retenue

**Ajustement direct.** Les décisions précisent le comportement sans changer le périmètre ni l'ordre des epics. Retour arrière : inutile (le code livré se complète par deux petites stories). Révision du MVP : inutile.

- Effort : faible à moyen. 1.12 et 2.7 : une demi-journée à une journée chacune. Ajouts aux stories en cours : quelques heures chacune.
- Risque : faible. Conflits de fusion possibles sur `screens/home.js` (1.12, 3.6, 4.9) et `models/registry` (2.7) ; d'où l'ordre proposé au §7 (b).
- Calendrier : le garde-fou du run sur l'Epic 5 se lève à la fusion de cette PR.

## 4. Propositions de modification détaillées (appliquées dans cette PR)

### UX : `EXPERIENCE.md`

- Foundation : la maquette devient la référence visuelle de la v2 ; les documents priment sur elle.
- Architecture d'information : nom court au menu, nom long en sous-titre sur l'Accueil, `h1` « Accueil » (D-9, D-10).
- Chiffres : notes de juge sur /100, références du banc en pourcentage « Part de … » (D-5).
- Composants : interrupteur en bascule pour toute option binaire (D-6) ; confirmation étendue à la suppression d'un document (D-24) et d'un modèle.
- Nouvelle section « Coquille et écrans v2 du MVP » : Coquille (thème, routes, icônes, erreurs, exports), Accueil, Chat libre, Arène, Références, Discussion, Base documentaire.
- Écrans des Epics 5 à 7 : décisions D-17, D-18, D-27 à D-43 reportées dans leurs tableaux ; exceptions au panneau latéral listées ; questions ouvertes 3 (tranchée par D-38) et 5 (précisée par D-28) mises à jour.
- Flows 1 et 2 : matrice d'abord, défaut `rag` du contrat, passage surligné.

Exemple (Base documentaire, `EXPERIENCE.md`) :

```
AVANT : « Confirmation uniquement pour les actions externes ou irréversibles : vider la base documentaire, envoyer un email. »
APRÈS : « … vider la base documentaire, envoyer un email ; en v2, aussi supprimer un document (D-24) et supprimer un modèle. »
```

### UX : `DESIGN.md`

Composant `wl-switch` (jetons et rendu), icônes Material Symbols Rounded (D-2), thème « Système » sans troisième jeu de jetons (D-7), variantes de `wl-side-panel` (D-22, D-35, D-40), `wl-team-graph` (« Non lancé », orientation selon le nombre d'agents), menu « Exporter » (D-3), réponse repliée de l'Arène (D-15). Aucun jeton de couleur modifié : le test de dérive de `tokens.css` reste vert.

### Stories : `epics.md`

- FR8, FR27, FR32, FR34, FR37, FR43, FR44, FR46, FR47 précisés.
- UX-DR2, 3, 4, 11, 12, 15, 16, 20, 21, 22, 24, 26 à 29 mis à jour (D-n cités). UX-DR16 : `interrupted` → `generation_interrupted` (code livré par 2.1), ajout de `run_not_found`, `pull_failed`, `model_in_use`.
- Stories de suite 1.12 et 2.7 ajoutées (§7 (b)).
- Critères ajoutés ou modifiés : 3.2, 3.3, 3.4, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.8, 4.9, 5.1, 5.2, 5.3, 5.4, 5.6, 5.8, 6.4, 6.5, 6.6, 7.1, 7.3, 7.4, 8.2.

Exemple (4.2) :

```
AVANT : « … puis « Découpage · Vectorisation 18/40 extraits » depuis `ingest_progress`, et Annuler »
APRÈS : « … depuis `ingest_progress` ; un seul bouton « Annuler l'import », au-dessus des lignes, annule le lot entier (…) (D-25 : remplace l'« Annuler » par ligne) »
Raison : D-25 ; le contrat n'a qu'un run `ingest` par lot.
```

### Contrat : `contrat-api.md`

- Modèles : `default_temperature` (D-12).
- Événements : `sources.passage {start, end} | null` (D-21) ; `step.agent_totals` en mode équipe (D-34).
- Instantané : `format_verdict` (banc), `partial` (évaluation, D-28), `404 run_not_found`.
- Erreurs : clés de `detail` de `run_not_found`, `pull_failed`, `model_in_use` ; boutons déduits par le front (D-4).
- Par écran : Accueil, Chat, Références, Base documentaire, Modèles, Sobriété (équivalence calculée par le serveur, sessions closes), Équipe (route, 5 agents), Évaluation (défaut `arena`, partiel), Banc (`instruction`, format nullable, routes).
- `409` : `model_in_use`.

### Architecture

Spine AD-7 : une phrase. Les positions `passage` ne sont pas du texte ; elles sont persistées et ignorées quand `text` est `null`. Aucune autre AD ne change : D-4 confirme AD-18, D-12 et D-21 respectent AD-15 et AD-7, l'équivalence CO₂ côté serveur respecte AD-20.

### `03-ux-front.md` §3

Note en tête de §3 qui renvoie aux documents mis à jour ; table d'IA (§3.3) avec les nouvelles routes ; menu Affichage avec « Système ».

## 5. Passage de main

- **Classement : modéré.** Ajustement du backlog par l'orchestrateur du run (rôle PO/DEV) ; aucun replan PM/architecte.
- **Destinataire :** l'orchestrateur du run autonome (session principale) applique le §7 ; Anaël tranche les écarts du §7 (d) au réveil.
- **Critères de succès :** cette PR fusionnée ; 1.12 et 2.7 ajoutées au statut du sprint par l'orchestrateur ; les stories en cours portent les critères du §7 (a) avant leur PR ; aucune story de l'Epic 5 ne démarre avant la fusion ; aucun écart du §7 (d) n'est tranché sans Anaël.

## 6. Décisions prises seul (non interactif)

- Mode batch ; chaque proposition appliquée telle quelle, à la lecture la plus conservatrice de la décision.
- Le statut du sprint, `run-autonome-mvp.md` et `run-autonome.md` ne sont pas modifiés : l'orchestrateur ajoute lui-même 1.12 et 2.7 au statut.
- Précisions adoptées sans choix produit (pas des décisions) : code `run_not_found` pour un identifiant de run inconnu (`detail.run_id`) ; `model_in_use` nommé pour le 409 de suppression déjà prévu ; verdict de format du banc dans l'instantané, comme celui de l'Arène ; groupe des références désigné par le serveur (AD-20) ; catalogue installable = catalogue moins les installés ; légendes de bouton désactivé (« Choisissez 4 modèles au plus », « Saisissez une question », « Choisissez un juge ») ; « Prendre un modèle plus petit » sélectionne `detail.suggested_model` sans relancer ; codes d'erreur des trois refus de 4.3 laissés au choix de la story ; défaut `rag` du contrat cité dans le Flow 2 (le contrat prime sur `EXPERIENCE.md`).
- `default_temperature` : lue des paramètres publiés par Ollama ou du catalogue, sinon `null`. La source exacte se règle dans 2.7.
- `passage` : la règle de désignation (par exemple la phrase la plus proche de la question) est laissée à 4.4, écrite et testée.
- Équivalence CO₂ : calculée par le serveur (AD-20), facteur daté et sourcé dans `wavelocalai.toml`. Le facteur de la maquette (111 g/km) est fictif ; 5.1 vérifie une source publique.
- Affichage d'un résultat **effacé** rouvert par son adresse : non tranché (la maquette distingue « effacé » et « introuvable »). Seul l'identifiant inconnu rend `run_not_found`.

## 7. Consignes pour l'orchestrateur du run

**Prérequis.** Fusionner cette PR, puis fusionner `origin/master` dans chaque branche en cours (sans rebase) avant sa PR. Le garde-fou de l'Epic 5 se lève à la fusion. Note : le statut du sprint du dépôt principal marque déjà la **3.1 terminée** (PR #59, 5ab78e4).

### (a) Ajustements aux stories en cours

| Story | Ajustements (critères ajoutés dans `epics.md`) |
|---|---|
| **3.1** (fusionnée) | Aucun. Le rejet au-delà de 4 modèles existe déjà ; `run_not_found` arrive avec 3.6. |
| **3.2** | 1. Dès 1 440 px avec 4 modèles : 4 colonnes, réponse repliée sur 4 lignes, « Afficher toute la réponse » (D-15). 2. Configuration remplacée par un résumé (question, modèles, juge) jusqu'à `run_ended` (D-16). 3. Légendes de bouton désactivé : « Choisissez 4 modèles au plus », « Saisissez une question », en plus de « au moins 2 ». 4. Sans modèle local prêt : `alert-info` qui dit quoi faire (installer depuis Modèles ou autoriser le cloud), lancement désactivé avec raison (D-11). Le chronomètre « 0:42 » reste tel quel (écart ouvert, (d)). |
| **3.3** | Sans juge choisi : bouton désactivé avec « Choisissez un juge ». Notes sur /100 (D-5, déjà prévu). « un seul juge » : garder le critère actuel (écart ouvert, (d)). |
| **4.1** | 1. `GET /api/rag/documents` rend aussi les documents `failed` avec leur raison, hors du compte des documents prêts (D-26), avec un test. 2. Consigner dans `contrat-api.md` (Événements, `ingest_progress`) le champ déjà choisi pour l'échec et le doublon d'un fichier (écart du run : `ingest_progress.file`…). C'est une documentation de l'existant, pas un nouveau choix. |
| **4.2** | 1. Remplacer l'« Annuler » de chaque ligne par un seul « Annuler l'import » au-dessus des lignes, qui annule le lot (run `ingest` ou envoi en cours), les documents prêts restant (D-25). 2. Tableau : un document `failed` y figure, statut « Échec » avec sa raison, hors du compte « N documents indexés », toujours là après rechargement (D-26). Son « Supprimer » arrive avec 4.3. |

### (b) Stories de suite pour les Epics 1 et 2

À ajouter au statut du sprint en `backlog` (clés proposées), puis à traiter dans le run. Le texte complet est dans `epics.md`.

| Clé proposée | Epic | Titre | Critères (résumé) | Dépendances |
|---|---|---|---|---|
| `1-12-la-coquille-et-l-accueil-suivent-la-maquette-validée` | 1 | La coquille et l'Accueil suivent la maquette validée | Thème « Système » qui suit `prefers-color-scheme` en direct, défaut Clair, axe en Système (D-7) ; « Mode projection » en interrupteur `role="switch"`, rendu `wl-switch` partagé avec « Autoriser le cloud » (D-6) ; sprite Material Symbols Rounded officiel, test des icônes utilisées (D-2) ; liens de l'Accueil avec nom court, nom long et résumé, `h1` « Accueil » (D-9, D-10) ; routes de la maquette déclarées `planned` dans le registre (D-8) ; axe clair, sombre et projection, 320 px. | `master` actuel ; **à fusionner avant 3.6 et 4.9** (même fichier `screens/home.js`). Front seul, sans Ollama. |
| `2-7-le-chat-prend-la-créativité-du-modèle-et-s-exporte-sur-écran-étroit` | 2 | Le Chat prend la créativité du modèle et s'exporte sur écran étroit | `GET /api/models` rend `default_temperature` (Ollama ou catalogue, sinon `null`), servi depuis le cache, budget 300 ms (D-12) ; curseur « Créativité » sur ce défaut, repli 0,2, remis au défaut du nouveau modèle si non déplacé ; sous 768 px, menu « Exporter » (JSON, Markdown) au clavier, route serveur sans `blob:`, composant réutilisable (D-3) ; message « de 8 à 26 secondes » pendant `model_loading` (UX-DR17) ; test E2E qui garde le message tapé après un 409 (D-13). | `master` actuel ; **à fusionner avant 3.6** (qui réutilise le menu « Exporter »). Touche `models/` (registre) et `screens/chat.js`. |

Aucune des deux ne change de version : elles partent dans la préversion suivante (`2.0.0a3`).

### (c) Changements dans les stories du backlog (3.4 à 8.3)

| Story | Changement |
|---|---|
| 3.4 | Matrice affichée d'abord, segments « Matrice · Tableau », tableau derrière « Voir le tableau » (D-14). |
| 3.5 | Aucun. |
| 3.6 | Exports : deux boutons, menu « Exporter » de 2.7 sous 768 px (D-3) ; identifiant inconnu = `404 run_not_found`, code ajouté à `errors.py` ; carte « Démo recommandée » : nom court et nom long (D-10), « Lancer une comparaison » toujours actif (D-11). |
| 4.3 | « Supprimer » ouvre `wl-confirm-dialog` (textes dans `epics.md`), pour un document prêt ou en échec (D-24, D-26) ; codes `errors.py` pour les trois refus (embedding sur base non vide, `expected_count` périmé, document à run actif). |
| 4.4 | `sources.passage {start, end}` ou `null`, règle de désignation écrite et testée, positions persistées (D-21, AD-7). |
| 4.5 | Passage surligné (D-21) ; panneau toujours ouvert dès 1 024 px (D-22) ; « Afficher les sources » par réponse dès la deuxième, un seul panneau (D-23). |
| 4.6, 4.7 | Aucun. |
| 4.8 | « Prendre un modèle plus petit » sélectionne `detail.suggested_model` sans relancer. |
| 4.9 | Carte « Documents » / « Assistant documentaire » (D-10) ; le Flow 2 vérifie le passage surligné (D-21). |
| 5.1 | Équivalence CO₂ seulement dans le panneau de méthode, facteur et source du serveur (`wavelocalai.toml`, source publique vérifiée) (D-38). |
| 5.2 | Historique des sessions closes seulement, avec une phrase sous le graphique (D-37) ; Tableau par défaut sous 640 px (D-39). |
| 5.3 | « Installer quand même » dans le catalogue et la fiche (D-42) ; colonnes Usage et Origine repliées sous 1 024 px (D-43) ; un modèle supprimé revient au catalogue ; `pull_failed` avec `detail.cause`. |
| 5.4 | Dialogue de suppression qui signale un défaut choisi (D-41) ; `409 model_in_use` ajouté à `errors.py`. |
| 5.5, 5.7 | Aucun. |
| 5.6 | Fiche à droite dès 1 120 px, au-dessus de la liste en deçà, `#/modeles/<tag>` (D-40, D-8) ; « Installer quand même » dans la fiche (D-42). |
| 5.8 | Pourcentage « Part de … » (D-5) ; cartes par défaut et segment « Cartes · Tableau » (D-20) ; « Comparer ces modèles » (D-19) ; groupe désigné par le serveur ; Ollama arrêté lisible ; carte d'Accueil « Références » en pourcentage. |
| 6.1, 6.2, 6.3 | Aucun. |
| 6.4 | Outils en interrupteurs (D-6) ; avertissement pour un modèle sans outils vérifiés, lancement permis (D-32) ; « Étapes » toujours déplié sous 1 024 px (D-30) ; pied réduit, puis « Télécharger » par route serveur (D-31). |
| 6.5 | `validate` refuse plus de 5 agents (D-36) ; `agent_totals {tools, duration_s}` sur l'étape `answer` d'un agent (D-34). |
| 6.6 | Orientation du schéma ; « Configurer » non modal (D-35) ; 5 agents au plus avec la raison (D-36) ; « Non lancé » (D-34) ; journal en lignes horaires (D-33) ; réouverture par `#/agents/equipe/<run_id>` et `run_not_found` (D-8). |
| 7.1 | Agrégats par question dans `eval_metric` ; résultat partiel conservé, `partial: true` dans l'instantané (D-28). |
| 7.2 | Aucun. |
| 7.3 | Défaut `arena` présélectionné (D-27) ; question vide = bouton désactivé (D-29) ; résultat partiel rouvert, titré (D-28) ; `run_not_found`. |
| 7.4 | `GET /api/scenarios` rend `instruction` et un format nullable (D-17, D-18) ; « Consigne » repliée ; scénario sans format : interrupteur désactivé avec raison, sans verdict ; `format_verdict` dans l'instantané ; interrupteurs en bascule (D-6) ; route `#/arene/banc/<run_id>`. |
| 8.1, 8.3 | Aucun. |
| 8.2 | Toutes les routes du registre (plus « onze ») et le thème « Système » dans les E2E d'accessibilité. |

Pour les écrans des Epics 5 à 7, la référence visuelle est `docs/maquette-v2/` une fois la PR #58 fusionnée ; les documents de contrat priment.

### (d) Écarts encore ouverts, à trancher par Anaël

Non tranchés par les 43 décisions ; les stories gardent leur critère actuel en attendant.

1. **Message du code `timeout`** : citer le délai (« 2 min », 03 §3.8) ou non (`errors.py`) ; dans l'Arène, phrase de la story 3.2 contre message du code ; au Banc, « Délai dépassé (120 s) » (EXPERIENCE.md) contre message du code.
2. **Texte de `cloud_not_allowed`** : celui de 03 §3.8, plus court, ou celui d'`errors.py`.
3. **Icône de l'Arène** : `leaderboard` (DESIGN.md) ou `swords` (code livré et maquette). Et l'icône de la carte Références (DESIGN.md : jamais partagée).
4. **Chronomètre de l'Arène** : « 27 s » (EXPERIENCE.md, Chiffres) ou « 0:42 » (UX-DR20, 03 §3.5).
5. **« un seul juge »** : toujours avec les notes (maquette) ou seulement sous ~4B actifs (story 3.3 ambiguë).
6. **Étiquette « le plus petit des trois »** (03, Flow 1) : absente des stories ; la maquette la dérive des paramètres actifs.
7. **Adresse réécrite à la fin d'un run** (`history.replaceState` vers `…/<run_id>`) : l'Arène de la maquette le fait, l'Équipe non. À harmoniser.
8. **Résultat effacé rouvert par son adresse** : écran « effacé » distinct (la maquette ne garde que le CO₂, AD-13) ou `run_not_found`.
9. **Carte Mode de l'Accueil** : compteur « N appels cloud dans cette session », défini par aucune story.
10. **Banc** : comment le front sait qu'un modèle ne peut pas imposer de format (`no_structured_output`, champ du registre ?) ; boutons « Relancer le test » et « Modifier le test » (ajoutés par la maquette).
11. **Références** : bloc « Autres modèles mesurés », lien vers le tableau et légende des marques (non demandés par 5.8).
12. **Discussion** : avertissement cloud « les extraits de vos documents lui sont envoyés » (AD-9, absent des documents) ; « Télécharger » absent (aucune route d'export RAG) ; sort d'un marqueur [n] non vérifié (texte brut ?) ; moment de `retrieval_step` (début de chaque étape ?).
13. **Base documentaire** : Supprimer et Vider désactivés pendant un import (maquette) ou 409 affiché (contrat) ; message de `ram_guard` adapté à l'import.
14. **Évaluation** : limite de 4 modèles évalués ; colonne « Global » (question ouverte 4, écartée sauf décision contraire) ; liste des évaluations et bancs passés (question ouverte 5).
15. **Agents** : `h1` « Agent seul » / « Équipe d'agents » (maquette) ou « Agents autonomes » (EXPERIENCE.md) ; forme de « Charger une équipe » (liste et bouton ?) ; ligne d'agent qui s'ouvre et se referme seule (confort de démo).
16. **Sobriété** : « Remettre le compteur à zéro » désactivé quand la session est vide (état non prévu) ; version d'Ollama en légende de la santé du système.
17. **Modèles** : `wl-model-picker` filtré sur l'éligibilité de l'usage (EXPERIENCE.md) ou contrôle à « Enregistrer » (maquette) ; bouton « Fiche du modèle » à côté du sélecteur (`[ASSUMPTION]` d'EXPERIENCE.md, absent de la maquette).
18. **Noms de champs d'événements** (`step`, `approval_required`, `citations`, `eval_metric`, échec et doublon d'`ingest_progress`) : à fixer par les stories serveur (6.1, 4.6, 7.1, 4.1) et à consigner dans `contrat-api.md`. Ce n'est pas un choix produit : signalé pour mémoire.

Sans objet (propres à la maquette, contrat inchangé) : dossier `donnees/`, page autonome (D-1), contrat `render` en alias, réponses simulées, panneau Scénarios, défauts de `revue.md`, pic de mémoire dans `metrics` (la story 6.5 garde l'instantané), `fits` figé à l'installation.
