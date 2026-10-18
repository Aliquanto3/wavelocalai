# Références (`#/arene/references`)

## (a) États couverts

Scénarios (axe clair, sombre et projection ; 320 à 1 440 px sans défilement horizontal) : `cartes` (une carte par usage, groupe des meilleurs, intervalle, débit de la machine de référence, marques « installé » et « autre version », énergie mesurée), `tableau`, `tableau-trie` (tri au clavier), `chargement` (squelettes), `indisponible-fichier-absent`, `indisponible-format` (schéma différent de `qb.results/1`), `aucun-usage-publie` (aucune carte vide), `aucun-modele-installe`, `ollama-arrete` (références lisibles, marques non vérifiées).

Données : `donnees/references.json` (forme jointe telle que l'API la servirait, AD-22). Le schéma réel de `qb.results/1` n'est pas dans le dépôt : la structure est une hypothèse.

## (b) Écarts (non tranchés)

- Scores en pourcentage de réussite (« 74 % », AD-22 : fractions en pourcentage), alors que l'Accueil affiche la carte Références en « 74/100 » (`formatScore`) et qu'EXPERIENCE.md veut une seule échelle /100. À harmoniser.
- Groupe à égalité : aucun rang, tri alphabétique dans le groupe ; « Meilleur modèle » quand le groupe n'a qu'un membre. Le serveur doit dire quels modèles forment le groupe (champ `group`, hypothèse).
- « Autres modèles mesurés » et lien vers le tableau : non demandés par la story 5.8.
- Légende des marques sous les cartes : hypothèse, pour éviter les infobulles.
- Pas de carte « Réponse sur documents » : la décision Q7 dit que le banc ne publie pas cet usage.
- Ollama arrêté : l'écran reste lisible (fichier local, budget 300 ms) ; les marques « installé » sont retirées avec un message.

## (c) Questions pour Anaël

1. Échelle des scores. (A) pourcentage de réussite partout, Accueil compris. (B) /100 partout. (C) pourcentage ici, /100 pour les notes de juge. Recommandation : C, avec le libellé « Part de … » en tête.
2. Passer de la référence à l'action. (A) rien (actuel). (B) « Comparer ces modèles » ouvre l'Arène présélectionnée sur les modèles installés du groupe. (C) lien « Installer » vers Modèles pour ceux qui manquent. Recommandation : B.
3. Cartes ou tableau par défaut. (A) cartes (actuel). (B) tableau. (C) cartes en projection, tableau sinon. Recommandation : A.
