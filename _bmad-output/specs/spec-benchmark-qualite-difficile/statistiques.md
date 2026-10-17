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
- **Test z sur la différence appariée** (erreur-type groupée) pour les périmètres non binaires. Quand l'ET groupée est nulle (au bruit flottant près : |ET| ≤ 1e-12 + 1e-9·|diff|) avec une différence non nulle, le z donnerait p = 0 quel que soit l'effectif : repli sur le **test exact des signes** bilatéral sur les **groupes**, cohérent avec l'erreur-type groupée (différence moyenne par groupe, groupes ex aequo écartés, binomiale de paramètre 1/2 ; deux groupes positifs donnent p = 0,5). Il est signalé par `p_method: "sign"` dans le rapport (`"z"` ou `"mcnemar"` sinon), sur les comparaisons au meneur comme dans la matrice BH, et par une note sous le tableau des comparaisons et sous la matrice. Le champ `method` du périmètre (`paired_z`) désigne la famille de tests, pas le test de chaque paire.
- Friedman/Nemenyi est exclu pour une analyse par question : son N compte des jeux de données.

## Unités communes (décision d'Anaël, 2026-10-17)

Un modèle privé d'unités (erreur du banc, `context_exceeded` à limite du banc, ligne en attente du juge sous `--partial`) serait noté sur un sous-ensemble plus facile que ses concurrents. Pour chaque périmètre (piste en global, puis chaque usage) :

- **Score, erreur-type, IC, rang approché, groupes indiscernables, meneur, comparaisons au meneur (Holm), matrice (BH), k̂_Bonferroni et Spearman** portent sur les unités **définies pour tous les modèles comparés du périmètre**. Les tests appariés restent des McNemar ou des z appariés, sur ces unités.
- Le résumé publie à côté, par modèle, la moyenne sur **toutes ses unités définies** (`mean_all`) avec son effectif (`n_all`), les unités écartées (`excluded`), l'effectif commun du périmètre (`common_units`) et le nombre d'unités (`units`).
- `context_exceeded` est compté **séparément selon sa cause** : `context_exceeded_model` (contexte déclaré du modèle inférieur au palier, ou dépassement au palier égal à ce maximum : échec compté, score 0, unité définie) et `context_exceeded_bench` (plafond de la campagne ou erreur d'estimation du banc : unité nulle, hors des unités communes).
- Rapport du pilote : mêmes comptes, par source et par palier.

## Classement

Le classement se présente en **groupes de modèles indiscernables**, calculés sur les unités communes. Un rang approché est possible, à la Chatbot Arena : 1 + le nombre de modèles dont l'IC simultané est entièrement au-dessus. Pour une conclusion transversale (« A gagne sur la plupart des usages »), compter les usages gagnés avec k̂_Bonferroni.

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

## Revue

Revue de `fix/quality-stats-ci` (2026-10-17), constats du second avis (Haiku) et de la revue Opus.

- high | second avis | corrigé | `se == 0.0` laissait passer une ET de bruit flottant (9,8e-18 pour six différences de 0,1 en deux groupes) et rendait p = 0 : tolérance absolue et relative (`_is_zero`), testée sur ce cas.
- medium | second avis | corrigé | le test des signes comptait les ex aequo de bruit flottant (5,6e-17) comme des victoires : même tolérance.
- medium | second avis | corrigé | test des signes sur les unités alors que l'ET est groupée, anticonservateur avec peu de groupes : il porte sur les différences moyennes par groupe (décision de l'orchestrateur).
- low | second avis | corrigé | `p_method` absent de la matrice BH et note absente sous la matrice : champ ajouté (schéma, rapport) et note commune ; `method: "paired_z"` reste le nom de la famille de tests, précisé ci-dessus.
- low | second avis | corrigé | « binomiale, p = 0,5 » ambigu : « binomiale de paramètre 1/2 ».
- low | second avis | corrigé | textes qui citaient encore la variable `NLTK_DATA` (commande `fetch-nltk`, `paths.py`, `nltk_data.py`) ; `common/` change donc `harness_hash`, sans effet puisque le pilote repart de zéro.
- low | second avis | rejeté | `actions/cache@v6` existe (tags v6, v6.0.0, v6.1.0 du 2026-06-23 sur github.com/actions/cache).
- low | second avis | corrigé | politique Python 3.10–3.12 contre job en 3.14 : documenté dans l'écueil CI d'AGENTS.md.
- low | revue | reporté | le job CI `quality-bench` n'a jamais tourné : vérifier au premier push qu'il passe (téléchargement NLTK, cache, 3.14 sur `windows-latest`).
