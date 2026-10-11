# Statistiques

Toutes les analyses partent de `grading.jsonl` (scores) et de `generation.jsonl` (tokens, durées), question par question. Unités, complétude et références hors ligne : AD-17 du spine.

## Par modèle

- Exactitude par piste et par usage, avec un **intervalle de Wilson** à 95 %.
- **Erreurs-types groupées** par identifiant de groupe, car des questions qui partagent un contexte peuvent tripler l'erreur-type naïve.

## Entre modèles

- **McNemar exact (binomial)** par paire, sur la table 2×2 des réussites par question : `statsmodels…mcnemar(table, exact=True)` ou `scipy.stats.binomtest(b, b+c)`. Le test non apparié de deux proportions est proscrit.
- Publier la **différence** avec son erreur-type appariée et son IC à 95 %, ainsi que la corrélation entre modèles, pas seulement la valeur p.
- **Holm** sur les k−1 comparaisons au meneur (19 tests pour 20 modèles). Passer `method='holm'` à `multipletests`, dont la valeur par défaut est Holm-Šidák.
- **BH (FDR)** réservé à la matrice exploratoire « qui bat qui ».
- **Bootstrap apparié** pour les métriques non binaires (F1 d'extraction, note du juge).
- Friedman/Nemenyi est exclu pour une analyse par question : son N compte des jeux de données.

## Classement

Le classement se présente en **groupes de modèles indiscernables**. Un rang approché est possible, à la Chatbot Arena : 1 + le nombre de modèles dont l'IC simultané est entièrement au-dessus. Pour une conclusion transversale (« A gagne sur la plupart des usages »), compter les usages gagnés avec k̂_Bonferroni.

## Tirages

- K = 1 tirage par question, température 0, graine fixée.
- Si le taux de réponses changeantes mesuré au pilote n'est pas négligeable devant la part de questions discordantes entre modèles, passer à K > 1 et à l'erreur-type appariée sur les moyennes par question : McNemar ne s'applique plus tel quel.

## Troncature

En piste activée, une réponse tronquée au plafond compte comme un échec. Le taux de troncature est publié par modèle et par usage, séparément des mauvaises réponses.

## Validation externe

**Corrélation de Spearman avec l'indice Artificial Analysis (AA), sur la campagne complète :**
- Pas au pilote : avec 4 modèles, même ρ = 1 ne donne que p = 0,042 en unilatéral.
- Modèles pris en compte : ceux qui ont un indice AA **mesuré**, pas « estimé ».
- Appariement : la piste activée se compare à l'indice en raisonnement ; la piste coupée à l'indice sans raisonnement, quand il existe.
- **Critère de concordance :** ρ significativement positif (unilatéral, α = 0,05), soit environ ρ ≥ 0,64 pour n = 8 et ρ ≥ 0,56 pour n = 10. Publier aussi l'IC bootstrap de ρ.
- **Lecture :**
  - un ρ non significatif ne disqualifie pas le banc : l'indice AA des modèles de moins de 10B est bruité (5 à 14, souvent estimé), anglophone, et couvre peu de modèles ;
  - un ρ négatif déclenche une enquête ;
  - avec moins de 8 modèles mesurés, le test est rapporté sans conclusion.

**Au pilote :** un contrôle de cohérence seulement. L'ordre des 4 modèles est comparé à celui de l'ancien banc et aux indices AA disponibles.

## Repères de taille d'échantillon

α = 0,05 bilatéral, puissance 80 %, McNemar exact. ψ = part de questions discordantes.

| Écart | ψ = 0,2 | ψ = 0,3 | ψ = 0,4 |
|---|---|---|---|
| 10 points | 168 | 249 | 329 |
| 20 points | 39 | 61 | 84 |

Ces effectifs supposent des questions indépendantes : en présence de groupes, ils se comptent en groupes.
