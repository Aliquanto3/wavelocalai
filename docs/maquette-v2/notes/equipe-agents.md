# Équipe d'agents (`#/agents/equipe`)

## (a) États couverts

Scénarios : `equipe-prete` (parcours), `sans-agent` (« Ajoutez au moins un agent »), `sujet-vide` (« Saisissez un sujet »), `equipe-modifiee` (badge « Modifiée », « Revenir à l'équipe d'origine »), `configurer` (panneau latéral), `configurer-erreurs` (une erreur sous chaque champ, focus sur le premier), `mission-en-cours` (parcours : agent actif marqué sur le schéma, trace par agent), `rapport-final` (parcours : rapport, badge, CO₂, pic de mémoire, durée, Télécharger), `mission-arretee` (« Rapport partiel (mission arrêtée) »), `mission-arretee-tot` (agents suivants « Non lancé », pas de rapport), `mission-rouverte` (sans flux), `mission-validation-email`, `mission-email-envoye`, `mission-email-annule`, `validation-expiree`, `serveur-redemarre-en-attente`, `premier-chargement-lent`, `rejoint-409`, `agent-seul-en-cours` (le 409 vient d'une tâche d'agent seul : message et lien), `reprise-au-retour`, `connexion-perdue`, `serveur-redemarre`, `erreur-interrompue`, `erreur-delai`, `erreur-ollama-arrete`, `garde-fou-memoire`, `aucun-modele-local`, `cloud-non-autorise`.

Événements joués : `run_started`, `model_loading/loaded`, `step` avec `agent` et `lane`, `token` (rapport), `approval_required/resolved`, `metrics`, `run_ended`. Équipes de la bibliothèque : « Veille concurrentielle » (3 agents), « Compte rendu au client » (2 agents, outil d'email, validation), « Nouvelle équipe (vide) ». Axe : zéro violation en clair, sombre, projection, de 320 à 1 440 px, pour chaque scénario.

## (b) Écarts (non tranchés)

- `h1` = « Équipe d'agents » (titre de la route) ; EXPERIENCE.md : « Agents autonomes ».
- « Charger une équipe » : liste déroulante et bouton « Charger cette équipe » (EXPERIENCE.md ne fixe pas la forme).
- Une ligne par agent affiche « Non lancé » pour les agents que la mission n'a pas atteints après un arrêt ou une erreur ; EXPERIENCE.md ne prévoit que En attente, En cours, Terminé, Arrêté. La ligne « Terminé · 3 outils · 41 s » exige que le serveur publie les totaux de l'agent (`agent_totals` sur la fin de son étape `answer`) : le contrat ne les définit pas.
- Le pic de mémoire est dans l'événement `metrics` de la maquette ; la story 6.5 le met dans l'instantané `GET /api/runs/{id}`.
- Rouvrable « par l'URL du run » (EXPERIENCE.md) : `routes.json` n'a pas `/agents/equipe/:run_id` ; la réouverture est un scénario sur la même route.
- Panneau « Configurer » : dialogue modal collé à droite (pas un panneau non modal). 5 agents au plus (invention de la maquette, pour la lisibilité du schéma). Schéma horizontal dès 768 px jusqu'à 4 agents, vertical sinon.
- Messages de validation par champ (« Indiquez le rôle de l'agent. »…) : absents de `erreurs.json` (ce ne sont pas des enveloppes UX-DR16), écrits dans `donnees/equipe-agents.json`.
- Un agent ajouté par « Configurer » joue un scénario générique (une réflexion) ; la maquette ne dérive pas ses étapes de ses outils.
- La ligne d'un agent s'ouvre seule quand il démarre et se referme quand il a fini (confort de démo, non prévu).

## Composants communs (intégration)

Trace d'étapes, ligne d'état, fermeture du dialogue et pause de décision : composants communs (voir notes/agent-seul.md). Les événements d'une mission sont construits à l'exécution (la composition de l'équipe change) et joués par le simulateur comme script `{kind, events}`. La feuille `agent-seul.css` n'est plus ajoutée. Le schéma SVG de l'équipe reste propre à l'écran (seul utilisateur). Une mission se rouvre par son adresse `#/agents/equipe/<run_id>` (`mission-rouverte`, `mission-introuvable` avec `run_not_found`) ; la maquette ne réécrit pas l'adresse à la fin d'une mission (l'Arène le fait).

## (c) Questions pour Anaël

1. Journal brut : (A) lignes horaires lisibles, comme la maquette ; (B) événements JSON bruts ; (C) sortie texte du serveur. Recommandation : A.
2. Agent qui n'a pas pu s'exécuter : (A) « Non lancé » ; (B) rester « En attente ». Recommandation : A.
3. Forme de « Configurer » : (A) volet modal à droite (maquette) ; (B) volet non modal qui laisse le schéma visible ; (C) page dédiée. Recommandation : B si le schéma doit rester lisible pendant l'édition, sinon A.
4. Nombre maximal d'agents : (A) 5 ; (B) 8 avec schéma vertical au-delà de 5 ; (C) illimité. Recommandation : A.
