# Discussion (`#/documents`)

Fichiers : `js/screens/discussion.js`, `css/screens/discussion.css`, `i18n/screens/discussion.fr.json`, `donnees/discussion.json`, `donnees/flux/discussion-{reponse,erreur}.json`. Parties communes au module Documents : `js/screens/documents-commun.js` (base simulée dans le store sous `ragBase`, panneau de sources, aide en bouton), `css/screens/documents-commun.css`, `i18n/screens/documents-commun.fr.json` (fichiers ajoutés, aucun fichier partagé modifié).

## (a) États couverts (scénarios)

`base-vide`, `aucun-message`, `question-avec-sources` (Flow 2), `ouvrir-une-source` (Flow 2, passage surligné), `recherche-en-cours`, `reponse-en-cours` (sources déjà là, débit provisoire), `premier-chargement-lent`, `citations` ([1] focalisé, source en évidence), `sans-citations`, `strategie-hyde`, `strategie-self-rag`, `reclassement-indisponible`, `reclassement-actif`, `nombre-d-extraits` (5 sources dont 2 « éloignée »), `arret`, `reponse-cloud` (avertissement : les extraits quittent le poste), `conversation-rouverte` (deux réponses, une source « extrait supprimé »), `indexation-en-cours`, `reprise-au-retour`, `rejoint-409`, `erreur-ollama-arrete`, `garde-fou-memoire`, `cloud-non-autorise`, `cloud-autorise` (« Autoriser le cloud » cliqué), `erreur-cloud-injoignable` (sources gardées), `aucun-modele`, `connexion-perdue`, `serveur-redemarre`.

## (b) Écarts avec epics.md, DESIGN.md, EXPERIENCE.md (non tranchés)

- Champ `passage` ajouté aux sources (hors contrat de l'événement `sources`) : seul moyen, dans la maquette, de surligner « le passage qui fonde la réponse » (UX-DR11). Le contrat ne dit pas qui désigne ce passage.
- `retrieval_step` : la maquette le publie au début de chaque étape (`step`: `search`, `hypothetical`, `verify`, `rerank`), la durée de recherche arrivant dans `metrics.search_s`. Le contrat dit `{strategy, étape, durée}` sans préciser le moment.
- Événement `citations` : forme `{citations: [{marker, n}]}` choisie. Un marqueur absent de `citations` reste du texte brut (le contrat dit « seules les citations vérifiées sont affichées » sans dire ce que devient le marqueur écrit par le modèle).
- « Recherche 0,06 s · Génération 5,8 s » (UX-DR23) : deux `wl-metric` ajoutés au pied après `end()`, `wl-chat-thread` n'ayant pas ce pied.
- Avertissement cloud (« les extraits de vos documents lui sont envoyés ») absent d'epics.md et d'EXPERIENCE.md : ajouté au nom de la souveraineté visible (AD-9).
- Pas de « Télécharger » dans le pied (présent dans la maquette 03 §3.5) : aucune route d'export RAG au contrat.
- Bouton « Afficher les sources » par réponse dès la deuxième réponse (un seul panneau, plusieurs réponses) : non prévu par les stories.
- Le panneau est un `details` (ouvert dès 1 024 px, replié en deçà) ; la personne peut le replier en large.
- Le défaut `rag` du sélecteur est Qwen 3.6 7B (données communes), pas « le plus rapide qui tient » d'EXPERIENCE (Flow 2, étape 4).

## (c) Questions pour Anaël

1. Surlignage du passage : (A) le serveur renvoie `passage` (début/fin) avec chaque source ; (B) le front surligne les mots de la question (heuristique, fragile) ; (C) pas de surlignage, extrait entier seul. Recommandation : A.
2. Panneau de sources en large : (A) toujours ouvert, sans repli ; (B) repliable (maquette) ; (C) colonne fixe. Recommandation : A (la vérification de la source est le climax du Flow 2).
3. Plusieurs réponses, un seul panneau : (A) bouton « Afficher les sources » par réponse (maquette) ; (B) un panneau par réponse ; (C) sources de la dernière réponse seulement. Recommandation : A.
