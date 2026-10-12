"""Noyau statistique pur (AD-17) : fonctions sur des tableaux ou des séquences, sans I/O ni état
global. N'importe que la bibliothèque standard, ``numpy``, ``scipy``, ``statsmodels`` et ses
propres modules, jamais un autre module du paquet.

Une valeur indéfinie (effectif nul, variance nulle) est rendue en ``nan`` : c'est l'appelant
(``report/``) qui la publie en ``null``.

- ``units`` : score d'unité (minimum des questions, puis moyenne des seeds) ;
- ``wilson`` : intervalle de Wilson ;
- ``clustered`` : moyenne et erreur-type groupée ;
- ``mcnemar`` : McNemar exact, différence appariée, test z ;
- ``multiple`` : Holm, BH, k̂_Bonferroni ;
- ``bootstrap`` : bootstrap apparié par groupes, à graine fixée ;
- ``groups`` : IC simultanés, rang approché, groupes indiscernables ;
- ``spearman`` : validation externe contre l'indice AA ;
- ``power`` : taille d'échantillon indicative de McNemar (Connor), pour le pilote ;
- ``describe`` : effectif, moyenne et centiles d'une distribution (pilote).
"""

ALPHA = 0.05
