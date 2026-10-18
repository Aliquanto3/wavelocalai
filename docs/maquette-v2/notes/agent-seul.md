# Agent seul (`#/agents/seul`)

## (a) États couverts

Scénarios : `vide` (« Bonjour ! L'agent est prêt. », actions rapides, neuf outils dont « Envoi d'email » décoché), `outil-indisponible` (SMTP absent : pastille non cochable, `aria-disabled`, raison en légende), `aucun-modele` (« Choisissez un modèle avec outils vérifiés », lancement désactivé), `modele-sans-outils`, `etapes-en-cours` (parcours Flow 3), `tache-terminee` (quatre étapes, CO₂ mesuré, « 4 étapes », Télécharger), `etape-depliee` (Arguments, Résultat, « Ouvrir le fichier »), `erreur-outil` (« Résultat : erreur », l'agent poursuit), `bornes-atteintes` (« Arrêt : nombre d'étapes maximal atteint (12) »), `validation-email` (parcours Flow 3), `email-envoye`, `email-annule`, `validation-expiree`, `email-non-coche`, `arret`, `premier-chargement-lent`, `reponse-cloud-estimee`, `reponse-cloud-non-mesurable`, `rejoint-409` (étapes rejouées), `reprise-au-retour`, `connexion-perdue`, `serveur-redemarre`, `serveur-redemarre-en-attente` (« Interrompu », l'email n'est jamais envoyé), `erreur-interrompue`, `erreur-delai`, `erreur-ollama-arrete`, `erreur-cloud-injoignable`, `erreur-cle-absente`, `cloud-non-autorise`, `cloud-retire`, `garde-fou-memoire` (deux issues).

Événements joués : `run_started`, `model_loading/loaded`, `step` (début sans durée, puis fin avec `duration_s`, même `step_id` ; `kind` `think|tool_call|tool_result|answer`), `token`, `approval_required`, `approval_resolved`, `metrics`, `run_ended`. Axe : zéro violation en clair, sombre, projection, de 320 à 1 440 px, pour chaque scénario.

## (b) Écarts (non tranchés)

- `h1` = « Agent seul » (titre de la route, comme le Chat libre) ; EXPERIENCE.md veut « Agents autonomes ».
- Le panneau « Étapes » est toujours déplié, sans bouton de repli : EXPERIENCE.md le dit « déplié pendant un run » sous 1 024 px, sans prévoir de repli hors run.
- « Arrêter » est dans la saisie (EXPERIENCE.md) ; la ligne d'état du panneau « Étapes » n'a pas de second bouton.
- Le pied de réponse est celui de `wl-chat-thread` (CO₂, débit, tokens, chargement, durée totale) complété de « N étapes » et « Télécharger » ; EXPERIENCE.md liste badge, CO₂, étapes, durée, Télécharger. Débit, tokens et chargement s'ajoutent. Le téléchargement passe par un `Blob` (le vrai front : route d'export, 6.6).
- Mention « Sans réponse dans 10 min, l'envoi est refusé. » : EXPERIENCE.md la place dans le dialogue ; `ctx.states.confirmEmail` ne la porte pas, elle est affichée dans le panneau « Étapes » pendant l'attente.
- « Validation expirée : email non envoyé. » (EXPERIENCE.md) diffère de `states.email.expired` de `maquette.fr.json` (« …après 10 minutes : l'email n'est pas parti. ») ; l'écran suit EXPERIENCE.md.
- Avertissement ajouté quand le modèle choisi n'a pas d'outils vérifiés (pas dans les stories).
- Noms de champs de `step` et `approval_required` (`tool`, `arguments`, `summary`, `duration_s`, `artifact_url`, `to`, `subject`, `body`) : ma lecture de `contrat-api.md`, qui ne donne que des libellés français. Un `step` à deux temps (début, fin) et `is_error`, `limit_reached`, `outcome` : propositions à confirmer pour 6.1.
- Une action rapide « Préparer un email » nécessite l'outil coché : l'écran le dit, sans le cocher.
- La maquette ne simule pas le choix d'outils par le modèle : le script suit l'intention de la tâche (analyse, poste, devis, email), pas les cases cochées (sauf l'email).

## Composants communs (intégration)

- Résolus à l'intégration : trace d'étapes (`js/components/step-trace.js`), ligne d'état (`wl-run-status` piloté : « Réflexion… », « Appel de l'outil … », « En attente de votre validation »), fermeture du dialogue (`wl-confirm-dialog.close()`), mention des 10 min dans `confirmEmail`, pause de décision du simulateur (`{pause: true}` puis `run.resume`), icônes d'étapes dans le sprite.
- Reste : pas de `wl-team-graph` (schéma propre à l'écran Équipe d'agents).

## (c) Questions pour Anaël

1. Panneau « Étapes » sous 1 024 px : (A) toujours déplié ; (B) repliable, déplié par défaut pendant un run ; (C) tiroir. Recommandation : A.
2. Le pied de réponse d'une tâche d'agent : (A) pied du Chat + étapes ; (B) pied réduit (badge, CO₂, étapes, durée) comme EXPERIENCE.md ; (C) pied du Chat sans étapes. Recommandation : B (le débit agrégé de plusieurs appels dit peu).
3. Modèle sans outils vérifiés : (A) avertir et laisser lancer ; (B) bloquer le lancement ; (C) ne pas le proposer. Recommandation : A, comme la maquette.
