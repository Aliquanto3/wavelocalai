# Chat libre (`#/arene/chat`)

## (a) États couverts

Scénarios : `vide`, `reponse-locale` (raisonnement replié, pied définitif : CO₂ mesuré, débit D3, tokens, chargement, durée totale), `reponse-en-cours` (débit provisoire, Arrêter), `premier-chargement-lent`, `arret` (partiel gardé, « Arrêté »), `reponse-cloud-estimee`, `reponse-cloud-non-mesurable`, `conversation-rouverte`, `reprise-au-retour` (Accueil puis retour, reprise après le dernier `seq`), `rejoint-409`, `relance-automatique` (événement `retry`), `erreur-interrompue`, `erreur-delai`, `erreur-ollama-arrete`, `erreur-cloud-injoignable`, `erreur-cle-absente`, `cloud-non-autorise`, `cloud-retire` (le sélecteur retire le modèle cloud et propose le défaut local), `garde-fou-memoire` (question gardée, deux issues), `aucun-modele`, `connexion-perdue` (bandeau, reprise sans doublon), `aller-a-la-fin`, `serveur-redemarre` (« Interrompu »).

## (b) Écarts

- Créativité par défaut à 0,7 (maquette 03 §3.5) ; la branche feat/v2-ecran-chat utilise 0,2.
- Téléchargement : deux boutons (« Télécharger en JSON », « Télécharger en Markdown ») ; UX-DR21 dit « Télécharger (JSON, Markdown) » sans fixer la forme. Effacer et Télécharger sont masqués quand la conversation est vide, désactivés pendant une réponse avec la raison en légende.
- Message « Le premier appel charge le modèle en mémoire : de 8 à 26 secondes » affiché pendant `model_loading` (EXPERIENCE.md, premier chargement lent) ; non cité par la story 2.2.
- Après le garde-fou mémoire, « Prendre un modèle plus petit » choisit `detail.suggested_model` ; aucune story ne fixe ce comportement.
- La maquette garde la conversation dans l'écran (mémoire) ; le vrai front la relit du serveur (story 2.6).

## (c) Questions pour Anaël

1. Créativité par défaut : (A) 0,7 (03) ; (B) 0,2 (branche livrée) ; (C) défaut fourni par le serveur avec le modèle. Recommandation : C, sinon B.
2. Forme de « Télécharger » : (A) deux boutons ; (B) un bouton qui ouvre un menu JSON / Markdown ; (C) Markdown à l'écran, JSON dans l'aide. Recommandation : B sous 768 px, A au-delà.
3. 409 rejoint : le message tapé reste dans le champ. (A) le garder ; (B) proposer de l'envoyer à la fin du run suivi. Recommandation : A.
