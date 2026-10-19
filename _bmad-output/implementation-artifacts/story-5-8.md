---
title: 'Quel modèle pour quel usage : références du banc par usage'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '37aa9f0'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-6.md'
warnings: []
deferred: []
---

# Story 5.8 : quel modèle pour quel usage

## Objectif

L'onglet « Références » de l'Arène (`#/arene/references`) montre une carte par usage publié par le banc (`qb.results/1`) : le groupe des meilleurs désigné par le serveur (intervalle, aucun rang dans un groupe à égalité, tri par nom), la part de réussite en pourcentage, le débit sur le poste de référence (PC pro de 16 Go sans carte graphique) et la marque « installé » ou « autre version ». « Comparer ces modèles » ouvre l'Arène présélectionnée sur les modèles du groupe installés (D-19). L'Accueil gagne une carte « Références » (« Quel modèle pour quel usage ? ») qui dit le meilleur score.

## Décisions de conception

Variante conservatrice pour tout ce que les décisions du 2026-10-19 ne tranchent pas.

1. **Lecture** : `models/bench_results.py` (5.6) ; `models/references.py` construit la vue (`build_references`) ; `web/routes_references.py` la sert (`GET /api/references`), depuis le cache du registre et le fichier : aucun appel d'Ollama (AD-15, budget 300 ms testé Ollama arrêté). Le front ne calcule ni rang, ni groupe, ni marque (AD-20).
2. **Usages** : les clés publiées par le schéma (`reasoning`, `instructions`, `tools`, `extraction`, `rag`, `abstention`, `writing`), libellés et mesures français côté serveur ; une clé inconnue est ignorée ; un usage sans aucun modèle classé n'a pas de carte (jamais de carte vide).
3. **Score d'un modèle pour un usage** : le résultat de la piste sans raisonnement d'abord, puis complet, puis campagne la plus récente (règle de la 5.6), pris sur le poste de référence, à défaut sur un autre poste du même fichier (la qualité ne dépend pas du poste) ; un score `null` ou `provisional` (usage `writing`) laisse le modèle « non classé » pour cet usage. Débit et énergie : toujours ceux du poste de référence (`null` sans mesure, jamais 0 ; énergie seulement si `status = "measured"`).
4. **Groupe des meilleurs** : le meilleur score, puis tous les modèles dont l'intervalle atteint celui du meilleur (`ci_high` du modèle >= `ci_low` du meilleur) ; un intervalle absent vaut le score seul (égalité stricte). Ni rang ni numéro : les membres sont triés par nom, les autres par score décroissant puis nom (tableau).
5. **Poste de référence** : le PC pro de `bench_results` (aucune carte graphique, 14 à 18 Gio) ; sans lui, `reference_machine` vaut `null`, les débits sont inconnus et l'en-tête le dit.
6. **Marques** : « installé » (mêmes poids, `exact`) ou « autre version » (même tag, autre empreinte), calculées par le serveur sur les modèles locaux de conversation. Ollama arrêté : aucune marque (`installed: null`), `ollama_up: false`, message sur l'écran, « Comparer » désactivé avec sa raison.
7. **Comparer** : le serveur donne par usage `compare.tags` (les modèles du groupe installés, tags tels qu'installés, quatre au plus par nom : l'Arène en accepte quatre) et `compare.reason` quand la liste est vide. Le clic ouvre `#/arene/comparer` et pose les modèles dans le sélecteur de l'Arène (`screens/references-compare.js`) sans modifier `arena.js` (déjà à 600 lignes) ; un run en cours dans l'Arène garde son résumé.
8. **Accueil** : `top` dit le meilleur score de toutes les cartes (modèle, usage, score) ; la carte n'existe que si l'écran est disponible et que `available` est vrai ; un seul appel (`GET /api/references`), après `shell-ready`, relu à chaque affichage de l'Accueil (comme le résumé de la base), jamais en boucle.
9. **Icône** : `leaderboard` (carte Références, jamais `swords`). Le sprite officiel Material Symbols Rounded n'est pas disponible hors ligne : tracé Material Icons (Filled) ajouté sous l'exception `PENDING_ROUNDED` (9 symboles), à remplacer par le sprite officiel (8.1). Écart à signaler à Anaël.
10. **Décision n° 11** : ni « Autres modèles mesurés », ni lien vers le tableau du banc, ni légende des marques. Le bouton « Voir le tableau » de la maquette est donc supprimé ; seul le segment « Cartes · Tableau » bascule.
11. **Version** : inchangée (2.0.0a5 posée par l'orchestrateur).

## Critères d'acceptation et preuves

Remplis en fin de story (voir « Rapport de dev »).

## Hors périmètre

Les défauts `agent` et `rag` calés sur le banc (5.7), toute création sous `benchmarks/`, la version, la release.
