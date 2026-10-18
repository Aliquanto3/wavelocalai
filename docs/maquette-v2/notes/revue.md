# Revue de la maquette v2 (une passe)

Diff `origin/master...HEAD`, limité à `docs/maquette-v2/`. Captures Edge 1 280 px, clair et sombre : Arène terminée (matrice et tableau), Évaluation, Sobriété, Modèles, Base documentaire.

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| — | second avis 1 | Diff hors `docs/maquette-v2/` | Rejeté : à trois points, rien hors du dossier. |
| medium | second avis 2 | Chemin Windows personnel dans CONVENTIONS.md (dépôt public) | Corrigé : chemin relatif à la racine du dépôt. Aucun autre chemin personnel. |
| medium | second avis 3 | Routeur : deux montages concurrents du même hôte, démontage du premier perdu (écouteurs `document` jamais retirés) | Corrigé : montage et démontage sérialisés par écran (`exclusive`). Les écrans retirent bien leurs écouteurs au démontage. |
| medium | second avis 4 | `loseConnection()` : tentatives non annulées, bandeau bloqué après un retour rapide (bascule, `ctx.reset()`, `run.cut` court) | Corrigé, test ajouté (`test_sim.py`). |
| low | second avis 5 | `disclosure.js` : écouteurs `document` jamais retirés | Rejeté : liés une seule fois au démarrage de la coquille. |
| low | second avis 6 | `"when": "{{x}}"` sans variable : événement joué | Corrigé, test ajouté. |
| low | second avis 7 | `stop()` avant `run.ready` : jetons tardifs | Corrigé (`schedule` s'arrête si `stopping`), test ajouté. |
| low | second avis 8 | Couleurs en dur (`scenarios.css`, SVG d'Agent seul) | Rejeté : panneau volontairement hors charte, documenté ; le SVG est un fichier téléchargé, sans accès aux jetons, en `#451DC7` (primaire). |
| low | second avis 9 | Nom non échappé dans le SVG téléchargé | Corrigé (échappement), bien que les noms viennent de données fictives. |
| medium | second avis 10 | Société fictive « Hélianthe » cherchée par la « Recherche interne Wavestone » comme « client » : nom porté par des sociétés réelles | Corrigé : renommée « Ombrelune » partout. Le libellé de l'outil reprend celui de la v1 (`search_wavestone_internal`) : gardé. |
| low | second avis 11 | Test des scénarios vide si un écran n'en exporte aucun | Corrigé : assertion d'au moins un scénario. |
| — | second avis 12 | Notes `documents-commun.md`, `etats.md` absentes | Rejeté : ni l'un ni l'autre n'est un écran (module partagé, catalogue propre à la maquette). |
| low | revue (captures) | En-têtes simples et triables décalés en hauteur dans les tableaux communs | Corrigé : `vertical-align: middle` sur `thead th`. |
| low | revue (captures) | Matrice : une étiquette repoussée sous la précédente peut chevaucher une bulle voisine (Arène, LFM 2.5 1.2B sur Gemma 4 1B) | Reporté : placement d'étiquettes à revoir dans `charts.js` (le tableau reste lisible). |
| low | revue (captures) | Classement de l'Arène : la note n'est pas alignée d'une ligne à l'autre quand un badge s'ajoute | Reporté : grille du classement à fixer dans `arene.css`. |
