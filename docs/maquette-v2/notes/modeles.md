# Modèles (`#/modeles`, `#/modeles/<tag>`)

## (a) États couverts

Liste : `nominal`, `premier-chargement` (squelette puis message d'attente), `aucun-modele` (état vide, « Voir le catalogue »), `ollama-arrete` (bandeau, actions désactivées), `garde-fou-memoire` (mémoire libre 2,8 Go, catalogue qui ne tient plus, « Décharger » proposé), `decharger` (annonce, mémoire libre mise à jour), `decharger-rien` (désactivé avec sa raison), `modele-utilise` (Supprimer désactivé, « Utilisé par une réponse en cours »), `supprimer-confirmation` (dialogue chiffré, focus sur Annuler), `supprimer-fait` (« Modèle supprimé », le modèle revient au catalogue), `suppression-conflit-409`.

Installation (`pull_progress`) : `installation-en-cours` (parcours Flow 3, « Téléchargement 1,47 Go sur 4,9 Go · 30 % » + Annuler), `installation-terminee` (« Installé »), `installation-annulee`, `installation-echec-tag` (`pull_failed`, nom inexistant), `installation-echec-ollama`, `installation-connexion-perdue` (reprise sans doublon), `serveur-redemarre` (« interrompue »), `rejoint-409` (une installation tourne ailleurs : on la suit, sans erreur), `reprise-au-retour` (Accueil puis retour).

Défauts : `defaut-changer`, `defaut-choisi` (« Choisi par vous », « Revenir au choix automatique »), `defaut-cloud-inactif`, `defaut-cloud-actif`, `defaut-aucun-agent`. Reranker : `reranker-installation`, `reranker-installe`, `reranker-option-absente`.

Fiche (la liste reste visible ; ces scénarios naviguent vers `#/modeles/<tag>`) : `fiche-modele`, `fiche-pourquoi-debit`, `fiche-autres-postes`, `fiche-autre-version`, `fiche-valeurs-inconnues` (contexte et licence « inconnu »), `fiche-non-installee`, `fiche-references-indisponibles`, `fiche-introuvable`.

## (b) Écarts

- `pull_failed` (story 5.3, trois variantes par `detail.cause` : `not_found`, `ollama_down`, `interrupted`) et `model_in_use` (409 à la suppression) sont au catalogue commun depuis l'intégration ; `errors.py` ne les a pas encore.
- Le catalogue installable montre aussi les modèles supprimés du poste (ils redeviennent installables) ; `config/models_catalog.json` n'est pas explicite sur ce point.
- « Changer » ouvre `wl-model-picker` : le composant ne filtre pas sur l'éligibilité d'un usage (agent : outils vérifiés et 3 B actifs ; documents : 3 B actifs) ni ne propose les modèles de représentation. L'éligibilité est contrôlée à « Enregistrer », avec un message ; EXPERIENCE.md parle d'un sélecteur « filtré sur les modèles éligibles ».
- Installations, suppressions et déchargements passent par le store (`js/sim/modeles.js`) : le sélecteur, les défauts, l'Accueil et le flux système simulé les voient. L'éligibilité d'un modèle installé (`fits`) est figée à l'installation.
- Le tri initial de « Sur ce poste » (chargés d'abord, puis nom) et du catalogue (ceux qui tiennent, puis mémoire croissante) est celui d'EXPERIENCE.md ; aucun en-tête n'est marqué trié tant qu'on ne trie pas.
- Les boutons désactivés sont `aria-disabled` (focalisables) avec leur raison en légende visible, jamais en infobulle seule.
- Parcours Flow 3 : EXPERIENCE.md installe `qwen3.6:7b`, déjà « installé » dans les modèles simulés communs ; la maquette installe `granite4.1:8b` (le texte de `donnees/parcours.json` le dit).
- Pas de bouton « Fiche du modèle » dans `wl-model-picker` (hypothèse d'EXPERIENCE.md) : composant partagé, non modifié.

## (c) Questions pour Anaël

1. Fiche : (A) panneau à droite dès 1 120 px, au-dessus de la liste en deçà (actuel) ; (B) page dédiée sans liste ; (C) tiroir modal. Recommandation : A.
2. Défaut dont le modèle est supprimé : (A) retombe sur la règle avec sa raison (actuel, story 5.4) ; (B) demande confirmation avant de supprimer un modèle choisi comme défaut. Recommandation : B, un message dans le dialogue suffit.
3. Installer un modèle qui ne tient pas : (A) permis sans avertissement supplémentaire (actuel, ligne chiffrée) ; (B) dialogue de confirmation chiffré ; (C) bouton libellé « Installer quand même ». Recommandation : C.
4. Tableau « Sur ce poste » à 9 colonnes : (A) défilement horizontal dans une région focalisable (actuel) ; (B) colonnes secondaires (Usage, Origine) repliées sous 1 024 px ; (C) cartes empilées. Recommandation : B.
