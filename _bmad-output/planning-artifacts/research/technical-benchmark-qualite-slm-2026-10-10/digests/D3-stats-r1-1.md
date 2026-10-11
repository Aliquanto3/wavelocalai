# D3 — Statistiques de comparaison appariée et taille d'échantillon (tour 1, digest 1)

Date : 2026-10-10. Périmètre : test de McNemar, bootstrap apparié, barres d'erreur des évaluations de LLM, comparaisons multiples, non-déterminisme.

## Tableau de tailles d'échantillon

Hypothèses : bilatéral, α = 0,05, puissance 80 % (z₀,₉₇₅ = 1,960 ; z₀,₈₀ = 0,842). On note ψ = p10 + p01 la proportion de questions discordantes (un modèle juste, l'autre faux) et d = p10 − p01 l'écart de précision. On en déduit p10 = (ψ + d)/2 et p01 = (ψ − d)/2. N est le nombre de questions. Dans le cas non apparié, N est le nombre de questions par modèle, pour la même analyse sans exploiter l'appariement.

| Écart (pA → pB) | ψ discordance | N McNemar, Connor | N apparié, Miller | N McNemar exact conditionnel | N non apparié (Miller, Cov = 0) | N non apparié (Fleiss, contrôle) |
|---|---|---|---|---|---|---|
| 10 pts (60 → 70 %) | 0,20 | 155 | 150 | 168 | 354 | 356 |
| 10 pts (60 → 70 %) | 0,30 | 234 | 228 | 249 | 354 | 356 |
| 10 pts (60 → 70 %) | 0,40 | 312 | 307 | 329 | 354 | 356 |
| 20 pts (50 → 70 %) | 0,20 (*) | 37 | 32 | 39 | 91 | 93 |
| 20 pts (50 → 70 %) | 0,30 | 57 | 52 | 61 | 91 | 93 |
| 20 pts (50 → 70 %) | 0,40 | 77 | 71 | 84 | 91 | 93 |

(*) Pour 50 → 70 %, ψ = 0,20 est le minimum possible : p01 = 0, le modèle B réussit toutes les questions que A réussit. C'est un cas limite.

Méthodes de calcul (script Python à la bibliothèque standard, `statistics.NormalDist`, sans scipy ni statsmodels dans l'environnement ; vérification croisée ci-dessous) :
- **Connor** : formule de Connor (1987) telle que la documente SAS PROC POWER, avec z₁₋α/₂ dans le terme α. Contrôle : l'exemple publié par MetricGate (p_d = 0,20, OR = 2,5) donne 211,3, arrondi à 212 paires, exactement la valeur de la page.
- **Miller (apparié)** : n = (z_{α/2} + z_β)² ω² / δ², avec ω² = Var(s_A − s_B). Pour des scores binaires avec K = 1, Var(s_A − s_B) = ψ − d². C'est ma dérivation : la différence par question vaut −1, 0 ou +1, son espérance est d et E[diff²] = ψ.
- **Exact conditionnel** : puissance « inconditionnelle » = Σ_{n_D} P(n_D) · P(rejet | n_D), avec n_D ~ Bin(N, ψ), et un test binomial exact bilatéral à p = 0,5 sur n01 | n_D (méthode décrite par SAS, DIST=EXACT_COND). Le tableau donne le premier N tel que la puissance ≥ 0,80. La puissance du test exact est en dents de scie en fonction de N : quelques N voisins peuvent repasser sous 0,80.
- **Non apparié** : formule de Miller avec Cov(x_A, x_B) = 0, soit ω² = pA·qA + pB·qB. Le contrôle par Fleiss (variance poolée sous H0, sans correction de continuité) donne une formule classique que je n'ai pas re-sourcée pendant ce run : c'est une croyance non vérifiée, elle sert seulement de contrôle de cohérence.

### Ce que permet le banc actuel (N ≈ 30)

| ψ | Puissance à N = 30 pour 10 pts (exact / Connor) | Puissance à N = 30 pour 20 pts (exact / Connor) | Écart minimal détectable à 80 % (Miller), N = 30 / 100 / 200 / 500 / 1000 |
|---|---|---|---|
| 0,20 | 0,10 / 0,23 | 0,57 / 0,71 | 20,4 / 12,1 / 8,7 / 5,6 / 3,9 pts |
| 0,30 | 0,09 / 0,17 | 0,40 / 0,52 | 24,9 / 14,8 / 10,6 / 6,8 / 4,8 pts |
| 0,40 | 0,08 / 0,14 | 0,31 / 0,41 | 28,8 / 17,1 / 12,3 / 7,9 / 5,6 pts |

Lecture : avec environ 30 questions, un écart de 10 points est indétectable (puissance de 8 à 23 %). Un écart de 20 points n'est détecté qu'une fois sur trois à une fois sur deux. L'écart minimal détectable se situe entre 20 et 29 points selon la discordance.

## Formules utilisées et sources

1. **Connor (1987), forme unilatérale** (SAS PROC POWER, METHOD=CONNOR) :
   N = { z₁₋α·√(p10+p01) + z_puissance·√[p10+p01 − (p01−p10)²] }² / (p01−p10)²
   Dans le cas bilatéral, SAS somme les deux puissances unilatérales, chacune à α/2. Le N bilatéral n'a pas de forme close et s'obtient par inversion numérique. L'approximation usuelle, retenue ici, remplace z₁₋α par z₁₋α/₂. MetricGate écrit la même formule directement avec z₁₋α/₂.
   Sources : SAS/STAT PROC POWER, McNemar (https://support.sas.com/documentation/cdl/en/statug/67523/HTML/default/statug_power_details55.htm) ; MetricGate (https://metricgate.com/docs/sample-size-mcnemar-paired). Référence primaire citée par les deux, non lue : Connor R.J. (1987), *Biometrics* 43(1):207-211.
   Selon SAS, Connor est « slightly conservative » (il surestime N), alors que Miettinen est un peu plus précis mais anticonservateur (Lachin 1992).
2. **Miettinen** (SAS) : N = { z₁₋α·ψ + z_p·[ψ² − ¼·d²·(3+ψ)]^½ }² / (ψ·d²). Je ne l'ai pas utilisée dans le tableau.
3. **Miller (2024), puissance pour une différence appariée** : n = (z_{α/2} + z_β)² (ω² + σ_A²/K_A + σ_B²/K_B) / δ², avec ω² = Var(x_A) + Var(x_B) − 2Cov(x_A, x_B). Les σ² sont les variances conditionnelles moyennes par question, et K le nombre de tirages par question. Écart minimal détectable : δ = (z_{α/2}+z_β)·√((ω² + σ_A²/K_A + σ_B²/K_B)/n).
   Source : https://arxiv.org/html/2411.00640v1
4. **Erreur-type appariée (Miller)** : SE_paired = √(Var(s_A − s_B)/n) = √(SE_A² + SE_B² − 2·SE_A·SE_B·Corr(s_A, s_B)).
5. **Erreur-type groupée (Miller)** : SE_clustered = (SE_CLT² + (1/n²) Σ_c Σ_i Σ_{j≠i} (s_{i,c} − s̄)(s_{j,c} − s̄))^½.
6. **Bootstrap apparié (Berg-Kirkpatrick et al. 2012, fig. 1)** : on tire b échantillons de taille n avec remise, on compte s tel que δ(x⁽ⁱ⁾) > 2·δ(x), et on estime p ≈ s/b. Les auteurs prennent b = 10⁶.

Concordance des deux sources : la formule de Miller avec ω² = ψ − d² et la formule de Connor ne diffèrent que par la variance du terme α (ψ sous H0 chez Connor, ψ − d² chez Miller). D'où un écart de 3 à 6 questions, Connor étant le plus conservateur. Le test exact conditionnel demande 5 à 10 % de questions en plus que Connor.

## Affirmations

- claim: Le test de McNemar a un faible taux d'erreur de type I. Pour des algorithmes qu'on ne peut exécuter qu'une fois, c'est le seul des tests étudiés dont l'erreur de type I est acceptable. Le test de différence de deux proportions (non apparié) et le t-test apparié sur splits aléatoires ont une erreur de type I élevée et « should never be used ». | source: https://mlanthology.org/neco/1998/dietterich1998neco-approximate/ (résumé ; PDF de l'auteur : https://web.engr.oregonstate.edu/~tgd/publications/dietterich-approximate-statistical-tests-nc1998.pdf, non lu en entier) | publisher: Neural Computation (MIT Press) | pub_date: 1998-10 | accessed: 2026-10-10 | confidence: medium | class: recommandation
- claim: La formule de Connor (1987) pour la taille d'échantillon de McNemar dépend de p10 + p01 (discordance) et de (p01 − p10)². Elle est légèrement conservatrice (surestime N) ; Miettinen est un peu plus précise mais anticonservatrice (Lachin 1992). | source: https://support.sas.com/documentation/cdl/en/statug/67523/HTML/default/statug_power_details55.htm | publisher: SAS Institute | pub_date: 2014-01 (approx., SAS/STAT 13.2) | accessed: 2026-10-10 | confidence: high | class: formule
- claim: La même formule de Connor s'écrit en bilatéral avec z₁₋α/₂. Exemple : p_d = 0,20, OR = 2,5 donne n = 212 paires, dont 43 discordantes attendues. Le calculateur recommande l'approche binomiale exacte conditionnelle quand on attend moins de 20 paires discordantes. | source: https://metricgate.com/docs/sample-size-mcnemar-paired | publisher: MetricGate (documentation de calculateur, qualité moyenne) | pub_date: 2026-05 (approx.) | accessed: 2026-10-10 | confidence: medium | class: formule
- claim: SAS calcule la puissance du McNemar exact comme une moyenne pondérée sur n_D ~ Bin(N, π01 + π10) des puissances conditionnelles ; tous les tests McNemar y sont conditionnels à n_D. | source: https://support.sas.com/documentation/cdl/en/statug/67523/HTML/default/statug_power_details55.htm | publisher: SAS Institute | pub_date: 2014-01 (approx.) | accessed: 2026-10-10 | confidence: high | class: methode
- claim: Avec α = 0,05 bilatéral et 80 % de puissance, détecter 10 points (60 → 70 %) demande environ 155 à 312 questions avec McNemar (Connor) pour ψ de 0,2 à 0,4, et environ 168 à 329 avec le test exact. Sans appariement, il en faut environ 354. Pour 20 points (50 → 70 %), il faut 37 à 77 questions (Connor), 39 à 84 (exact), et environ 91 sans appariement. | source: calcul propre à partir des formules de SAS/Connor, MetricGate et Miller (2411.00640) | publisher: dérivation | pub_date: 2026-10 | accessed: 2026-10-10 | confidence: high (formules à deux sources concordantes ; contrôle numérique sur l'exemple MetricGate) | class: taille-echantillon
- claim: À N = 30, la puissance pour détecter 10 points est d'environ 8 à 10 % (exact) ou 14 à 23 % (Connor) ; pour 20 points, elle est de 31 à 57 % (exact). L'écart minimal détectable à 80 % se situe entre 20 et 29 points selon ψ. | source: calcul propre (même base) | publisher: dérivation | pub_date: 2026-10 | accessed: 2026-10-10 | confidence: high | class: taille-echantillon
- claim: Miller recommande de comparer deux modèles par les différences appariées par question plutôt que par les scores agrégés, et de publier la différence, l'erreur-type appariée et la corrélation. La variance appariée vaut la variance non appariée moins 2Cov/n ; dans son exemple, une corrélation de 0,5 réduit la variance d'un tiers. | source: https://arxiv.org/html/2411.00640v1 | publisher: arXiv (Evan Miller, Anthropic) | pub_date: 2024-11 | accessed: 2026-10-10 | confidence: high | class: recommandation
- claim: Erreurs-types groupées quand les questions partagent un contexte (passage, traductions d'une même question) : dans les exemples de Miller, elles atteignent environ 3 fois les erreurs-types naïves. | source: https://arxiv.org/html/2411.00640v1 | publisher: arXiv (Evan Miller, Anthropic) | pub_date: 2024-11 | accessed: 2026-10-10 | confidence: high | class: methode
- claim: Réduction de variance : rééchantillonner K réponses par question et calculer l'erreur-type sur les moyennes par question. Dans l'exemple de Miller (difficulté uniforme, scores binaires), Var(K) = Var(1)·(1 + 2/K)/3, avec un gain plafonné à 2/3 ; le gain ultérieur est faible une fois E[σ²]/K ≪ Var(x). Si le score se lit dans les probabilités du token suivant, on prend le score espéré, ce qui supprime la variance conditionnelle. | source: https://arxiv.org/html/2411.00640v1 | publisher: arXiv (Evan Miller, Anthropic) | pub_date: 2024-11 | accessed: 2026-10-10 | confidence: high | class: methode
- claim: Miller recommande de ne pas baisser la température pour réduire la variance, sauf si l'on étudie justement le comportement à cette température : baisser la température peut déplacer la variance vers les moyennes par question ou introduire un biais (exemple où la variance passe de 1/12 à 1/4). | source: https://arxiv.org/html/2411.00640v1 | publisher: arXiv (Evan Miller, Anthropic) | pub_date: 2024-11 | accessed: 2026-10-10 | confidence: high | class: recommandation
- claim: Dans l'exemple de puissance de Miller (ω² = 1/9, sans variance conditionnelle), détecter δ = 3 points avec α = 0,05 et 80 % de puissance demande n ≈ 969, d'où sa suggestion d'au moins ~1 000 questions pour une nouvelle évaluation. Avec n = 198, passer de K = 1 à K = 10 réduit l'écart minimal détectable de 13,2 % à 7,5 %. | source: https://arxiv.org/html/2411.00640v1 | publisher: arXiv (Evan Miller, Anthropic) | pub_date: 2024-11 | accessed: 2026-10-10 | confidence: high | class: taille-echantillon
- claim: L'arbre de décision de Dror et al. : statistique de loi connue → test paramétrique ; sinon, si l'échantillon est petit → bootstrap ou randomisation ; sinon → test non paramétrique sans échantillonnage. McNemar est « designed for paired nominal observations (binary labels) » sur une table 2×2. L'article juge inapproprié le t-test sur des tâches de classification (observations catégorielles) et le bootstrap sur un petit jeu de test, celui-ci supposant que la distribution du jeu de test ne s'écarte pas trop de celle de la population. | source: https://aclanthology.org/P18-1128.pdf | publisher: ACL 2018 (Dror, Baumer, Shlomov, Reichart) | pub_date: 2018-07 | accessed: 2026-10-10 | confidence: high | class: recommandation
- claim: Bootstrap apparié : on rééchantillonne le jeu de test avec remise et on compte les cas où δ(x⁽ⁱ⁾) > 2δ(x), l'hypothèse nulle étant recentrée. Les auteurs prennent b = 10⁶, « more than sufficient » pour stabiliser la p-valeur, et la méthode s'applique à toute métrique, y compris F1 et BLEU. Avec un jeu de test tiré i.i.d., la significativité est bien calibrée, mais cette calibration se dégrade quand le domaine des nouvelles données s'écarte de celui du jeu de test. | source: https://nlp.cs.berkeley.edu/pubs/BergKirkpatrick-Burkett-Klein_2012_Significance_paper.pdf | publisher: EMNLP-CoNLL 2012 (ACL Anthology D12-1091) | pub_date: 2012-07 | accessed: 2026-10-10 | confidence: high | class: methode
- claim: Comparaisons multiples : dans les articles ACL 2017 évalués sur plusieurs jeux de données, seuls 3 sur 110 corrigeaient la multiplicité (tous par Bonferroni). Dror et al. proposent l'analyse de réplicabilité (Dror et al. 2017, estimateur K-Bonferroni) pour des jeux de test dépendants, par exemple les plis d'une validation croisée. | source: https://aclanthology.org/P18-1128.pdf | publisher: ACL 2018 | pub_date: 2018-07 | accessed: 2026-10-10 | confidence: high | class: recommandation
- claim: La variance des benchmarks LLM est rarement quantifiée (variance entre graines, monotonie). Reformuler un QCM comme MMLU en tâche de complétion réduit la variance pour les modèles d'environ 7B, mais l'analyse d'items et l'IRT ne la réduisent pas sensiblement. | source: https://arxiv.org/abs/2406.10229 | publisher: arXiv (Madaan et al., Meta) | pub_date: 2024-06 | accessed: 2026-10-10 | confidence: medium (résumé seulement) | class: methode
- claim: tinyBenchmarks (ICML 2024) affirme qu'environ 100 exemples choisis suffisent à estimer la performance sur MMLU (~14 000 items). Il s'agit d'estimer le score d'un modèle, pas de détecter l'écart entre deux modèles. | source: https://arxiv.org/abs/2402.14992 | publisher: ICML 2024 / arXiv (Maia Polo et al.) | pub_date: 2024-05 (v2) | accessed: 2026-10-10 | confidence: medium (résumé seulement ; la méthode IRT n'est pas nommée dans le résumé) | class: methode
- claim: La température 0 ne garantit pas le déterminisme. Atil et al. observent jusqu'à 15 % de variation de précision sur 10 exécutions « déterministes » (5 modèles, 8 tâches). | source: https://arxiv.org/html/2408.04667v5 | publisher: arXiv (Atil et al.) | pub_date: 2024-08 (v1 ; v5 révisée plus tard) | accessed: 2026-10-10 | confidence: medium (vu à travers le résumé du moteur de recherche, page non lue) | class: recommandation
- claim: Le non-déterminisme à température 0 vient surtout du manque d'invariance au lot des noyaux (RMSNorm, matmul, attention) : le batch varie avec la charge du serveur. Sur 1 000 complétions de Qwen3-235B, on obtient 80 sorties distinctes, contre 1 seule avec des noyaux invariants au lot (vLLM), qui rendent l'inférence environ 1,6 à 2 fois plus lente. L'article ne traite pas de llama.cpp ni d'Ollama. | source: https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/ | publisher: Thinking Machines Lab (Horace He) | pub_date: 2025-09 | accessed: 2026-10-10 | confidence: high | class: methode

## Synthèse orientée décision

- **Test** : McNemar sur la table 2×2 des réussites par question. Avec moins d'environ 20 à 25 paires discordantes, ce qui est le cas à N ≈ 30, il faut le test binomial exact (conditionnel). Sources : MetricGate pour le seuil ; Dietterich et Dror pour le choix de McNemar sur des sorties binaires. Ajouter une erreur-type appariée et un IC à 95 % sur la différence (Miller), ou un IC par bootstrap apparié quand N est assez grand. Dror déconseille le bootstrap sur un petit jeu de test.
- **Taille** : 30 items ne suffisent ni pour 10 points ni, de façon fiable, pour 20 points. Il faut environ 85 questions pour 20 points et environ 330 pour 10 points dans le cas le plus défavorable étudié (ψ = 0,4, test exact). La discordance ψ observée entre petits modèles fixe le N réel. On peut l'estimer sur le banc actuel, mais 30 items l'estiment mal.
- **Température** : rester à 0 ne supprime pas la variance d'exécution (non-déterminisme). Miller déconseille de régler la température dans le seul but de réduire la variance. Si l'on fait K tirages à T > 0, on moyenne par question et on applique la formule avec σ²/K. Le score par question devient alors une proportion et McNemar ne s'applique plus tel quel : on passe à une erreur-type appariée sur les moyennes par question ou à un bootstrap apparié.

## Pistes à creuser

- Lire le texte intégral de Connor (1987) et de Lachin (1992) pour confirmer la convention bilatérale et la formule de Miettinen.
- Lire Dietterich (1998) en entier : version de McNemar recommandée (avec correction de continuité ou non), seuil de validité de l'approximation du χ².
- Documentation statsmodels de `mcnemar(exact=True, correction=True)` : comportement par défaut. Je ne l'ai pas consultée pendant ce run.
- Déterminisme d'Ollama et llama.cpp en mono-utilisateur sur une même machine, et entre machines ou backends (CUDA, Metal, CPU) : le banc multi-machines peut produire des réponses différentes à température 0. À mesurer (même prompt répété) ou à documenter (issues llama.cpp, options de seed).
- Annexe C de Miller : puissance avec erreurs-types groupées, utile si des questions partagent un contexte (RAG sur un même document).
- Comparaisons multiples : sources primaires sur Holm (1979) et Benjamini-Hochberg (1995), et pratique récente en évaluation de LLM (classements par paires, intervalles simultanés). Dror et al. (2017, TACL) sur la réplicabilité.
- IRT et sélection d'items (tinyBenchmarks, Anchor Points, metabench), à confronter à Madaan et al., pour qui l'IRT ne réduit pas la variance.
- Atil et al. (2408.04667) : lire la version complète pour les chiffres par modèle et les recommandations (TARr@N, nombre de répétitions).

## Cherché sans trouver

- Le texte intégral de Dietterich (1998) : DOI MIT Press en 403, seul le résumé est lu.
- Une fonction de puissance McNemar dans statsmodels : rien trouvé ce run, et ni scipy ni statsmodels ne sont installés dans l'environnement local. Les calculs sont faits à la main avec la bibliothèque standard.
- La documentation PASS (NCSS) « Tests for Two Correlated Proportions » : non récupérée.
- Une recommandation explicite sur la correction de Holm ou le contrôle du FDR propre aux benchmarks LLM entre 2024 et 2026 : non trouvée dans le budget. Miller ne traite pas des comparaisons multiples.
- La recommandation de Koehn (2004) sur le nombre de rééchantillonnages : non lue (seulement citée par Dror et par Berg-Kirkpatrick).
