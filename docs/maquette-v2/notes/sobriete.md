# Sobriété et matériel (`#/sobriete`)

## (a) États couverts

Scénarios : `nominal` (quatre métriques en direct, session avec Local, Cloud « (estimé) » et une réponse non mesurable, historique 7 jours en graphique), `premier-chargement` (squelettes), `ollama-arrete` (« Ollama ne répond pas » + Réessayer), `aucun-modele-local` (« Aucun modèle chargé »), `sans-accelerateur` (« Aucun », jamais « Actif »), `bridage-thermique` (texte, avec icône d'alerte), `memoire-haute`, `connexion-perdue` (valeurs « inconnu »), `onglet-masque` (mises à jour en pause, dernières valeurs gardées), `session-vide` (pas de « 0 mg », remise à zéro désactivée avec sa raison), `session-non-mesurable` (comptées à part), `session-en-grammes` (une seule unité pour toute la section), `reponse-en-direct` (le total suit `carbon_updated` sans clic), `non-mesurables-lien` (déplie « Comment ces chiffres sont calculés »), `remise-a-zero` (parcours Flow 3 : la session close rejoint l'historique, tableau), `historique-30-jours`, `historique-tout`, `historique-tableau` (tri au clavier), `historique-periode-vide`, `historique-vide`.

Hors scénario mais présents : cartes « Carte d'identité technique » et « Comment ces chiffres sont calculés » (repliées), graphique SVG avec `<title>`, `<desc>` et « Voir le tableau », région à défilement horizontal focalisable pour le graphique et le tableau.

## (b) Écarts

- Unité du graphique et du tableau : toujours le milligramme (story 5.2 : « mg, une seule unité »), alors que la section « session » suit UX-DR15 (unité du plus grand total, mg ou g). Les deux ne se mélangent jamais dans un même bloc.
- Le flux système simulé (`js/sim/systeme.js`) n'a pas de GPU : l'accélérateur, sa température et le bridage viennent de `donnees/sobriete.json` et d'un état propre à l'écran (scénarios). Le réglage global « Onglet masqué » est lu comme `livePaused`.
- « Remettre le compteur à zéro » est désactivé, avec sa raison, quand la session est vide ; EXPERIENCE.md ne prévoit pas cet état.
- La session en cours n'apparaît dans l'historique qu'une fois close ; une phrase le dit sous le graphique. Ni EXPERIENCE.md ni la story 5.2 ne tranchent si la session en cours doit y figurer.
- L'équivalence parlante de la maquette 03 §3.5 (« environ 3,7 m en voiture ») est absente, comme dans les stories (question ouverte 3 d'EXPERIENCE.md).
- « Ollama » : la valeur est le nombre de modèles chargés, les noms et tailles sont dans l'aide (EXPERIENCE.md) ; la version d'Ollama s'affiche en légende, ajout de la maquette.

## (c) Questions pour Anaël

1. Session en cours dans l'historique : (A) absente jusqu'à sa clôture (actuel) ; (B) dernière barre marquée « en cours » ; (C) ligne distincte au-dessus du graphique. Recommandation : A, car le total est déjà au-dessus.
2. Équivalence parlante du CO₂ : (A) aucune (actuel) ; (B) « environ N m en voiture » avec la source du facteur en aide ; (C) équivalence dans le panneau de méthode seulement. Recommandation : C (parlant sans paraître une mesure).
3. Graphique sur écran étroit : (A) défilement horizontal du graphique dans une région focalisable (actuel) ; (B) barres horizontales empilées en une colonne ; (C) tableau par défaut sous 640 px. Recommandation : C.
