# Arène (`#/arene/comparer`, `#/arene/comparer/<run_id>`)

## (a) États couverts

Scénarios (tous passent axe, clair, sombre et projection ; 320 à 1 440 px sans défilement horizontal de la page) :

- Configuration : `trois-locaux-preselectionnes` (Flow 1), `moins-de-deux-modeles`, `trop-de-modeles`, `juge-peu-fiable`, `aucun-modele`.
- Exécution : `comparaison-en-cours` (Flow 1), `premier-chargement-lent`, `arret`, `reprise-au-retour`, `rejoint-409`, `connexion-perdue`, `serveur-redemarre`.
- Résultats : `resultats-vainqueur-le-plus-petit` (Flow 1), `resultats-tableau`, `reponse-entiere`, `mode-focus`, `verdict-local-cloud`, `cloud-non-mesurable`, `un-modele-en-delai`, `un-modele-non-evalue`, `juge-indisponible`, `colonne-en-echec`.
- Erreurs et gardes : `erreur-ollama-arrete`, `cloud-non-autorise`, `cloud-retire`, `erreur-cle-absente`, `garde-fou-memoire`.
- Résultat conservé : `resultat-rouvert` (`run-arene-demo`, quatre modèles dont un cloud), `resultat-rouvert-arrete`, `resultat-efface` (AD-13), `resultat-introuvable`, `modifier-la-question`, `relancer`.

Flux : `donnees/flux/arene-comparaison.json` (événements `run_started`, `lane_status`, `model_loading`, `model_loaded`, `token` par `lane`, `metrics`, `judge_score`, `run_ended`). Les modèles cloud partent d'abord, les locaux suivent un par un, chaque lane est notée dès qu'elle a fini. Sous 768 px : onglets par modèle ; de 768 à 1 439 px : 2 colonnes visibles avec défilement et en-têtes collants ; dès 1 440 px : 3 à 4 colonnes.

## (b) Écarts (non tranchés)

- Chronomètre en « 27 s » (EXPERIENCE.md, Chiffres) et non « 0:42 » (UX-DR20, 03 §3.5).
- « Exporter (CSV, Markdown) » : deux boutons dans un groupe « Exporter ».
- Légende « Choisissez 4 modèles au plus » ajoutée (la story 3.2 ne nomme que « au moins 2 ») ; « Saisissez une question » et « Choisissez un juge » aussi.
- « le plus petit des trois » (maquette 03) n'est dans aucune story : étiquette dérivée des paramètres actifs, masquée si un paramètre est inconnu (modèles cloud sans taille).
- `lane_status` porte un champ `error` pour `failed` et `timeout` : absent du tableau d'événements de `contrat-api.md`.
- Délai dépassé : la colonne affiche la phrase de la story 3.2 (« Délai dépassé pour ce modèle. Les autres continuent. »), pas le message du code `timeout` (« … en 2 min »).
- L'adresse devient `#/arene/comparer/<run_id>` à la fin du run par `history.replaceState` (sans remonter l'écran) ; un instantané en mémoire rend la réouverture possible pendant la visite.
- Le verdict local/cloud est lu dans l'instantané du run (story 3.5) ; la maquette le calcule dans `serverVerdict`, marqué « côté serveur ».
- Comparaison effacée : seules les mesures de CO₂ restent (AD-13) ; classement et notes ne sont pas reconstruits, puisque `judge_score` vit dans `run_events`.
- « un seul juge » accompagne les notes dans tous les cas, pas seulement sous 4B (la story 3.3 est ambiguë).
- Les réponses simulées sont par modèle, pas par scénario prédéfini : choisir « Traduction » change la question, pas les réponses.

- Comparaison introuvable : enveloppe `run_not_found` du catalogue (ajoutée à l'intégration).
- Le bandeau « Comparaison en cours · 2 sur 3 » reste propre à l'écran (compteur de modèles, ligne de résultat rouvert, durée lue dans l'instantané) : `wl-run-status` ne porte pas ces libellés.

## (c) Questions pour Anaël

1. Matrice ou tableau par défaut après une comparaison. (A) Matrice, tableau derrière « Voir le tableau » (actuel). (B) Tableau d'abord, matrice en second. (C) Les deux côte à côte dès 1 440 px. Recommandation : A pour la démo, C en projection.
2. Colonnes étroites à 4 modèles sur 1 440 px. (A) 4 colonnes serrées (actuel). (B) 2 colonnes visibles comme à 1 024 px, défilement ensuite. (C) 4 colonnes, réponse repliée sur 4 lignes. Recommandation : C.
3. Exporter. (A) deux boutons (actuel). (B) un bouton qui ouvre un menu CSV / Markdown. (C) Markdown à l'écran, CSV en second. Recommandation : A.
4. Pendant l'exécution, la configuration disparaît au profit d'un résumé. (A) résumé (actuel). (B) configuration grisée visible. (C) résumé avec configuration repliable. Recommandation : A.
