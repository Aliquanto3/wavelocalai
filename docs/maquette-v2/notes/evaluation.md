# Évaluation de la qualité (`#/documents/evaluation[/<run_id>]`)

Fichiers : `js/screens/evaluation.js` (routes `evaluation` et `evaluation-resultat`), `css/screens/evaluation.css`, `i18n/screens/evaluation.fr.json`, `donnees/evaluation.json`, script construit à l'exécution (`sim.play({kind: "eval", events})`, nombre de modèles libre). Parties communes : voir notes/discussion.md. Un résultat terminé est gardé dans le store (`ragEvals`) et rouvrable par son adresse ; `run-eval-demo` est un résultat fictif fourni.

## (a) États couverts (scénarios)

Ajouté avec les décisions du 2026-10-18 : `partiel-rouvert` (décision 28).

Route `evaluation` : `formulaire` (« Saisissez une question »), `jeu-de-questions`, `base-vide`, `aucun-modele`, `juge-peu-fiable`, `cloud-autorise` (CO₂ « estimé » et « non mesurable », avertissement d'envoi des extraits), `evaluation-en-cours`, `voir-les-extraits`, `evaluation-terminee`, `detail-fidelite`, `detail-precision-contexte`, `matrice`, `jeu-termine` (« sur 8 questions (1 non évaluée) »), `detail-jeu`, `non-evalue` (réponse vide, sortie du juge invalide), `modele-delai-depasse`, `arret` (résultats partiels), `reprise-au-retour`, `rejoint-409`, `erreur-ollama-arrete`, `garde-fou-memoire`, `connexion-perdue`, `serveur-redemarre`. Sur les deux routes : `resultat-rouvert` (parcours), `resultat-introuvable`.

## (b) Écarts (non tranchés)

- Limite de 4 modèles évalués (« Choisissez 4 modèles au plus ») : absente du contrat, nécessaire pour la matrice et la lisibilité.
- Modèles évalués : défaut du sélecteur pris sur `arena` (trois petits modèles) ; le contrat ne définit pas de défaut pour cet usage.
- `eval_metric` : la maquette ajoute `by_question`, `n_questions`, `n_unscored` pour le jeu de questions (« sur 8 questions (1 non évaluée) » est dans EXPERIENCE, pas dans le contrat) ; les verdicts ne sont détaillés que pour la question 1.
- Verdicts en français (« appuyée », « non appuyée », « contredite ») comme la story 7.1 ; `metric` : `faithfulness`, `relevance`, `context_precision`.
- Précision du contexte = part des 4 extraits jugés utiles pour cette réponse (définition d'EXPERIENCE) : elle varie donc selon le modèle alors que les extraits sont communs.
- Pas de colonne « Global » (écartée par EXPERIENCE, question ouverte 4).
- Matrice : composant commun `bubbleMatrix` (débit en échelle logarithmique, un modèle cloud à 365 tokens/s écraserait les locaux ; CO₂ en taille, cercle pointillé pour « non mesurable », légende HTML). Le tableau des scores reste fait main (en-têtes avec aide, cellules à bouton, pas de tri).
- Étapes : nommées par `wl-run-status.setStage`. « Voir les extraits » ouvre le panneau de sources commun (`js/components/source-panel.js`).
- Aucune liste des évaluations passées (question ouverte 5 d'EXPERIENCE) : l'adresse seule, affichée après la fin du run ; adresse inconnue : enveloppe `run_not_found` du catalogue.
- Arrêt ou redémarrage : les cellules sans note affichent « non évalué (évaluation arrêtée) », jamais 0 ; le contrat ne dit pas ce que devient le résultat partiel (la maquette ne le garde pas).

## (c) Décisions d'Anaël (2026-10-18)

Questions tranchées ; numéros du README §6.

1. Défaut des modèles évalués : (A) trois petits modèles locaux de l'Arène (maquette) ; (B) le défaut `rag` seul ; (C) vide, à choisir. Recommandation : A.
   **Décision n° 27** : Évaluation : les trois petits modèles locaux de l'Arène présélectionnés. État : déjà conforme.
2. Résultat partiel d'un run arrêté : (A) non conservé (maquette) ; (B) conservé et rouvrable, marqué « partiel ». Recommandation : B.
   **Décision n° 28** : Évaluation arrêtée : résultat partiel conservé, rouvrable, marqué « partiel ». État : appliquée.
3. Question vide : (A) bouton désactivé avec la raison (maquette) ; (B) champ prérempli par une question d'exemple. Recommandation : A pour le produit, B pour la démo d'atelier.
   **Décision n° 29** : Évaluation, question vide : bouton désactivé avec la raison. État : déjà conforme.
