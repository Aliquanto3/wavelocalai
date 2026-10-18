# Banc d'essai (`#/arene/banc`, `#/arene/banc/<run_id>`)

## (a) États couverts

Scénarios (axe clair, sombre et projection ; 320 à 1 440 px sans défilement horizontal) :

- Configuration : `vide`, `format-attendu` (détail déplié), `entree-modifiee` (« Remplacer par l'exemple du scénario »), `format-impose-indisponible` (modèle sans sortie structurée), `aucun-modele`.
- Résultats : `format-respecte`, `format-non-respecte` (champ « date » manque), `sortie-non-json`, `scenario-sans-format` (pas de verdict), `reponse-concise`, `reponse-cloud-non-mesurable`.
- Exécution : `essai-en-cours` (débit provisoire), `premier-chargement-lent`, `arret`, `delai-depasse`, `reprise-au-retour`, `rejoint-409`, `connexion-perdue`, `serveur-redemarre`.
- Erreurs et gardes : `erreur-ollama-arrete`, `erreur-cloud-injoignable`, `erreur-cle-absente`, `cloud-non-autorise`, `garde-fou-memoire`.
- Résultat conservé : `resultat-rouvert` (`run-banc-demo`), `resultat-delai` (`run-banc-delai`), `resultat-introuvable`.

Flux : `donnees/flux/banc-essai-reponse.json` (`run_started`, `model_loading`, `model_loaded`, `token`, `metrics`, `run_ended`).

## (b) Écarts (non tranchés)

- Le verdict de format n'est pas un événement : il est lu dans l'instantané du run à `run_ended`, comme le `verdict` de l'Arène. `contrat-api.md` ne dit pas où il vit.
- « Délai dépassé (120 s) » (EXPERIENCE.md) : la maquette affiche le message du code `timeout` du catalogue (« … en 2 min »).
- Scénarios sans format (code, raisonnement, résumé) : l'API `GET /api/scenarios` rend un format attendu par scénario ; ici trois scénarios n'en ont pas, donc « Format imposé » est désactivé et le verdict absent.
- Comment le front sait qu'un modèle ne peut pas imposer un format (`no_structured_output`) n'est fixé par aucun contrat : donnée simulée, hypothèse d'EXPERIENCE.md.
- Boutons « Relancer le test » et « Modifier le test » ajoutés (non demandés par UX-DR29), par cohérence avec l'Arène.
- Les consignes système des scénarios ne sont pas montrées ; seule l'« Entrée » l'est.
- Essai introuvable : enveloppe `run_not_found` du catalogue (ajoutée à l'intégration).

## (c) Questions pour Anaël

1. Scénario sans format. (A) interrupteur désactivé avec raison, pas de verdict (actuel). (B) masquer l'interrupteur. (C) proposer un format libre. Recommandation : A.
2. Afficher la consigne du scénario. (A) non (actuel). (B) dans « Format attendu ». (C) bloc « Consigne » replié. Recommandation : C, pour expliquer pourquoi le modèle répond ainsi.
3. Interrupteurs. (A) bascule visuelle (actuel). (B) cases à cocher. (C) segments Oui / Non. Recommandation : A.
