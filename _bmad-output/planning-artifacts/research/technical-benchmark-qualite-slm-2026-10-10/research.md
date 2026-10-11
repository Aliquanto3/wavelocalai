---
title: 'technical research: Benchmark qualité plus difficile pour SLM locaux (Ollama)'
type: 'technical'
topic: 'Benchmark qualité plus difficile pour SLM locaux (Ollama)'
decision: "Choisir jeux d'évaluation, harnais et taille d'échantillon pour un banc qualité discriminant (agents/outils, RAG FR, extraction JSON)"
source: 'run'
status: complete
preset: 'standard'
validation: 'normal'
created: '2026-10-10'
updated: '2026-10-10'
claims_verified: 14
claims_unverified: 6
claims_disputed: 1
claims_overturned: 1
---

# Recherche technique : benchmark qualité plus difficile pour SLM locaux (Ollama)

**Décision servie :** choisir les jeux d'évaluation, le harnais et la taille d'échantillon d'un banc qualité discriminant pour les petits modèles de langage (SLM) locaux de wavelocalai. Usages visés : agents avec appel d'outils, RAG en français, extraction JSON, plus le raisonnement, le suivi d'instructions et l'abstention.

## Résumé exécutif

**Ce que les preuves disent de faire :** construire le harnais maison sur l'API native d'Ollama. Il doit tirer ses items de jeux sous licence ouverte et, surtout, de **générateurs** (items paramétrés), avec au moins **≈ 330 items par piste** pour départager deux modèles à 10 points d'écart. Les comparaisons se font par **McNemar exact apparié avec correction de Holm**. Détail en section 5 (R1 à R8), composition des pistes en R2.

**Les trois constats qui portent la décision :**

1. **Le banc actuel ne peut pas départager les modèles.** Avec environ 30 items, un écart de 10 points n'est détecté que dans 8 à 10 % des cas. Il faut 168 à 329 items par piste (McNemar exact, selon la part de questions où les modèles divergent), et 39 à 84 pour un écart de 20 points. Ces effectifs sont calculés par le rapport à partir de la formule de Connor [1], recoupée par celle de Miller [2], et recalculés indépendamment (section 3.2).
2. **Les jeux publics les plus connus sont saturés, peu discriminants ou biaisés pour des SLM.**
   - IFEval plafonne à 89–90 % dès 4B chez Gemma 3 [3][4].
   - MuSR reste entre 0,33 et 0,41 (score sur 1) de 1B à 14B [5].
   - MATH-500 est contaminé chez Qwen2.5 [6], et le surapprentissage se confirme sur des variantes générées [7][8].
   - Les remplaçants utiles existent : IFBench (EN), M-IFEval (FR), BFCL v4 live et multi-turn, BBEH mini, OneRuler (contexte long, français inclus), JSONSchemaBench et PIAF. Tous sont sous licence redistribuable (section 1).
3. **Aucun framework n'apporte ce dont le banc a besoin.**
   - lm-eval, Inspect et BFCL passent tous par l'API compatible OpenAI d'Ollama (`/v1`), qui ne permet de régler ni `num_ctx`, ni `think`, ni `format` (schéma JSON natif) [9][10].
   - Aucun ne fait de comparaison appariée entre modèles.
   - Sur Ollama, lm-eval perd en outre toutes les tâches à choix multiples, dont BBH et MuSR [11][12].
   - Le harnais maison, déjà décidé, est donc justifié. Il reprendra les **vérificateurs** d'IFBench et de M-IFEval ainsi que le vérificateur AST de BFCL, à copier dans le dépôt (tous sous Apache-2.0) [13][14][15].

**Principale réserve :** Ollama n'applique pas toujours la contrainte `format` quand `think` est actif (issue ouverte en octobre 2026) [16], et un réglage censé être déterministe ne l'est pas toujours [17][18]. Le harnais doit donc valider chaque sortie côté client et mesurer la stabilité, faute de quoi des écarts dus à Ollama passeront pour des écarts entre modèles.

**Deuxième réserve :** les scores publiés qui fondent le constat n° 2 datent de la génération 2024–2025 (Llama 3.2, Qwen2.5, Gemma 3) et sont périmés selon les fenêtres de revérification (section 7). Un pilote sur les modèles réels du catalogue doit mesurer la saturation et la discordance avant de figer les pistes.

## 0. Cadre de décision

Le cadre tient compte des décisions déjà prises par l'utilisateur le 10/10/2026, relevées dans la mémoire du projet. Elles cadrent les questions, mais ne valent pas preuve :
- couvrir tous les usages ;
- campagne de 5 à 6 jours sur une seule machine (tour-rtx3050), avec 19 modèles ;
- environ 800 items par modèle et par piste ;
- reprise après arrêt sans perte au-delà de l'item en cours ;
- juge cloud accepté pour la rédaction en français ;
- harnais maison.

**Critères éliminatoires :**
- appel de l'API Ollama locale ;
- correction déterministe, sauf pour la rédaction FR jugée ;
- résultats par question ;
- exécution hors ligne pendant une campagne ;
- licence compatible avec un dépôt public ;
- Python 3.10+.

**Préférences pondérées :**
- adaptabilité au français : ×3 ;
- pertinence pour les usages : ×3 ;
- faible contamination : ×2 ;
- facilité d'intégration : ×2 ;
- pouvoir discriminant pour les SLM : ×2.

## 1. Jeux d'évaluation réutilisables

**Question :** quels jeux publics reprendre, sous quelle licence, avec quel risque de contamination, quelle adaptabilité au français et quel pouvoir de discrimination entre SLM ?

### 1.1 Fiche par candidat, regroupée par piste

| Jeu | Licence (données / code) | Taille | Correction | Contamination / saturation | Français | Discrimine les SLM ? |
|---|---|---|---|---|---|---|
| ***Suivi d'instructions*** | | | | | | |
| **IFEval** | Apache-2.0 [19] | ≈ 500 prompts, 25 types de contraintes [19] | vérificateurs Python | **saturé chez les SLM récents** : 80 % et plus dès 2B [4] ; Gemma 3 plat à 89–90 de 4B à 27B [3]. Nuance : les SLM de 2024 restent entre 0,51 et 0,79 [5] | voir M-IFEval | non au-delà de 4B pour les modèles récents |
| **IFBench** | ODC-BY-1.0 / Apache-2.0 [20][21] | 300 prompts, 58 contraintes inédites [4] | vérificateurs Python | conçu contre la contamination (prompts WildChat non publiés) [4]. Un entraînement ciblé y fait gagner environ 17 points [4] | **aucune version FR** | oui : Qwen3-32B < 50 %, Tülu-3-8B 28,9 [4] (une source) |
| **M-IFEval (FR)** | Apache-2.0 (code) [15] | 235 prompts FR, dont 5 contraintes propres au français [22] | vérificateurs réécrits pour chaque langue [22] | prompts générés par LLM puis édités à la main [22] | **natif FR** | Qwen2.5-32B 81,7 en FR [22] ; aucun score de SLM < 14B trouvé |
| IFEval-fr (le-leadboard) | **aucune licence déclarée** [23] | 515 | idem IFEval | idem IFEval | traduction | à écarter pour un dépôt public |
| ***Appel d'outils*** | | | | | | |
| **BFCL v4** | Apache-2.0 [24] | ≈ 2 400 items hors catégorie live (somme des effectifs détaillés sous le tableau) | AST et transition d'état, déterministes [25] | aucune preuve trouvée | **aucune version FR** ; le jeu GregoryD est une traduction automatique d'un jeu d'entraînement, pleine de fautes [26] | **étalé au global** : 7 % (Gemma-3-1B) à 55 % (xLAM-2-32B) [27] |
| ***Extraction JSON*** | | | | | | |
| *Joker* **JSONSchemaBench** | MIT [28] | ≈ 10 000 schémas réels, du trivial à l'ultra [28] | validation par JSON Schema | — | indépendant de la langue | non mesuré |
| ***RAG et contexte long*** | | | | | | |
| **RULER** | Apache-2.0 [29] | générateur, 13 tâches [29] | déterministe | faible (généré) | non (voir OneRuler) | contexte long seulement |
| **OneRuler** | code MIT [30] | 26 langues **dont le français**, de 8K à 128K, 7 tâches, 50 exemples par configuration [31] | déterministe | faible (généré, botte de foin = livres du domaine public) [31] | **instructions traduites par des locuteurs natifs** [31] | Qwen2.5-7B et Llama-3.1-8B évalués (scores FR non extraits). Échec fréquent : le modèle répond à tort « aucune réponse » [31] |
| *Joker* **PIAF** | MIT [32] | 3 835 questions sur Wikipédia FR [32] | extractif (EM / F1) | **soupçon** : Wikipédia figure dans les corpus de pré-entraînement | natif FR, annoté par des humains | non mesuré |
| *Joker* FQuAD | non commercial, redistribution interdite [33] | — | — | — | natif FR | **inutilisable** ; le miroir `manu/fquad2_test` en Apache-2.0 contredit ces conditions [34] |
| ***Raisonnement*** | | | | | | |
| **MuSR** | conflit : CC-BY-4.0 sur HF [35], MIT sur GitHub [36] | 756 [35] | QCM | données générées par GPT-4, régénérables [37] | musr-fr : noms incohérents dans l'exemple de la fiche [38] | **non** : 0,33 à 0,41 de 1B à 14B ; murder_mysteries au niveau du hasard, object_placements plat [5] |
| **BBH** | MIT [39] | 23 tâches × ≈ 250 | correspondance exacte | saturé chez les modèles de pointe (> 90 %) [40] ; Gemma 3 : 85,7 à 12B [3] | bbh-fr (Apache-2.0, méthode de traduction non documentée) [41] | oui pour les SLM de 2024 (0,35 → 0,64) [5] ; plafond atteint dès 12B pour les modèles récents [3] |
| **BBEH** | Apache-2.0 / CC-BY-4.0 [42] | 4 520, **mini : 460** [42] | `evaluate.py` (correspondance exacte non confirmée) | conçu plus dur que BBH [40] | non | **près du plancher** : Gemma 3 de 7,2 (1B) à 19,3 (27B), mais croissant avec la taille [3] |
| **MATH / MATH-500 / Lvl 5** | MIT [43] ; la fiche HF de MATH-500 n'en déclare pas [44] | 5 000 / 500 | réponse finale, sensible au format [37] | **contamination de Qwen2.5** : reproduction mot pour mot de MATH-500 [6]. Surapprentissage confirmé indépendamment sur des variantes (VAR-MATH : 36,9 → 2,0 [7] ; GSM-Symbolic [8]) | MATH_LVL5_fr : exemple qui n'est pas de niveau 5 [45] | étalé (0,07 → 0,55) mais **biaisé en faveur de Qwen** [5][6] |

Scores en %, sauf ceux de l'Open LLM Leaderboard [5], exprimés de 0 à 1.

*Joker* : candidat ajouté en dehors de la liste demandée, pour couvrir un usage qu'elle laissait sans jeu.

**Détail de BFCL v4 par catégorie :**
- **Tailles** : non-live 1 240 items en AST, dont 240 d'irrelevance ; multi-turn 4 × 200 ; web search 100 × 2 ; memory 150 et plus [24][25][46]. Effectifs de la catégorie live non trouvés.
- **Non-live AST** : **au plafond**, environ 88 % dès 4B [27].
- **Live AST** : bien étalé, de 12 % à 82 % [27].
- **Multi-turn** : **au plancher** sous 8B [27].
- **Web search** : exige SerpAPI, donc le réseau [47].

### 1.2 Matrice de décision (re-pondérable)

Les notes vont de 1 à 3 et reflètent mon jugement sur les faits ci-dessus. Les poids sont ceux des préférences pondérées (section 0). La matrice note aussi une option construite, les maths générées selon la recette VAR-MATH, détaillée en 1.3.

| Jeu | FR (×3) | Pertinence pour les usages (×3) | Contamination faible (×2) | Facilité d'intégration (×2) | Discrimine (×2) | **Total /36** |
|---|---|---|---|---|---|---|
| OneRuler (FR, contexte long) | 3 | 3 | 3 | 2 | 2 | **32** |
| PIAF (RAG FR) | 3 | 3 | 1 | 3 | 2 | **30** |
| JSONSchemaBench | 2 | 3 | 2 | 3 | 2 | **29** |
| IFBench | 1 | 2 | 3 | 3 | 3 | **27** |
| M-IFEval FR | 3 | 2 | 2 | 2 | 2 | **27** |
| BFCL v4 (live AST + multi-turn) | 1 | 3 | 2 | 2 | 3 | **26** |
| Maths générées (recette VAR-MATH) | 3 | 1 | 3 | 1 | 2 | **24** |
| RULER (EN) | 1 | 2 | 3 | 2 | 2 | 23 |
| IFEval (EN) | 2 | 2 | 1 | 3 | 1 | 22 |
| BBH | 2 | 1 | 1 | 3 | 2 | 21 |
| BBEH mini | 1 | 1 | 2 | 3 | 2 | 20 |
| MuSR | 1 | 1 | 2 | 3 | 1 | 18 |
| MATH-500 / Lvl 5 | 1 | 1 | 1 | 2 | 2 | 16 |

### 1.3 Ce qu'on en retient

- **Écarter :**
  - MuSR, qui ne discrimine pas entre SLM [5] ;
  - MATH-500 tel quel, biaisé en faveur de Qwen [6] ;
  - IFEval-fr de le-leadboard, faute de licence [23] ;
  - FQuAD, non redistribuable [33] ;
  - les sous-catégories BFCL saturées (non-live AST) ou qui exigent le réseau (web search) [47][27].
- **Le français est désormais couvert** pour le contexte long (OneRuler) et le suivi d'instructions (M-IFEval).
- **Aucun banc public d'appel d'outils en français n'est utilisable** [26]. La licence Apache-2.0 de BFCL autorise une traduction maison, en gardant les noms de fonctions et de paramètres [24].
- **Générer les maths plutôt que les reprendre.** GSM-Symbolic est sous CC-BY-NC-ND : la clause ND interdit d'en distribuer une adaptation française [48]. VAR-MATH ne publie pas de code, mais sa recette (constantes remplacées par des variables, réponse symbolique, plusieurs variantes par problème, score strict : problème réussi seulement si toutes ses variantes le sont) se réimplémente avec une correction déterministe [7].
- **Les traductions de le-leadboard** (bbh-fr, musr-fr, MATH_LVL5_fr) **ne sont pas documentées** et montrent des anomalies sur les exemples de leurs fiches [38][45]. Il faut en relire un échantillon avant tout usage (confiance moyenne : observé sur un seul exemple chacune).

## 2. Frameworks d'évaluation et harnais maison

**Question :** faut-il adopter lm-evaluation-harness, Inspect ou le harnais BFCL, ou étendre `scripts/benchmark_slm.py` ? Le projet a déjà retenu un harnais maison (voir le cadre, section 0). Cette section établit donc ce qu'on peut **emprunter** aux frameworks et ce qu'il faut **éviter**.

### 2.1 Aucun framework ne parle l'API native d'Ollama

Les trois candidats passent tous par l'API d'Ollama compatible OpenAI (`/v1`), jamais par l'API native `/api/chat` :
- **Inspect** appelle `http://localhost:11434/v1` par défaut, via le paquet `openai` [10] ;
- **lm-eval** passe par `local-chat-completions` [12] ;
- **BFCL** passe par `--skip-server-setup`, avec un serveur compatible OpenAI et un *handler* à écrire [49].

Sur `/v1`, Ollama n'offre aucun champ pour `num_ctx`, qu'il faut alors fixer dans un Modelfile. Ni `tool_choice` ni `echo` n'y sont pris en charge, pas plus que les logprobs sur `/v1/completions` [9]. Conséquence : un score obtenu par un framework sur `/v1` ne serait pas comparable à une mesure du script actuel sur `/api/chat` sans aligner `num_ctx`, `think` et `format`. Gemma 4 sur `/v1` illustre le problème : tout le texte part dans `reasoning`, et il est impossible d'y passer `think=false` [50] (confiance faible, statut actuel de l'issue non revérifié).

### 2.2 Comparatif

| Critère | lm-evaluation-harness | Inspect (`inspect_ai`) | BFCL (`bfcl-eval`) |
|---|---|---|---|
| Version, licence | 0.4.13 (31/08/2026), MIT [51] | 0.3.278 (09/10/2026), MIT, environ 10 versions en 3 semaines [52] | 2026.3.23, Apache-2.0 [53] |
| Branchement Ollama | `local-chat-completions` : génération seule, sans log-vraisemblance [12] | provider `ollama/` sur `/v1` [10] | aucun support documenté ; handler à écrire [49] |
| Tâches utiles qui tournent sur Ollama | `ifeval`, `math_hard`. `bbh`, `musr`, `gpqa` et `mmlu_pro` sont à choix multiples (*multichoice*), donc **inutilisables** sur une API chat [11] | IFEval, BBH, BBEH, MuSR, BFCL (AST et état, sans juge) ; ni IFBench, ni MATH, ni RULER, ni tâche FR [54][55] | AST simple, multiple, parallèle et live ; multi-turn |
| Correction déterministe | vérificateurs IFEval ; extraction Minerva et équivalence `sympy` pour MATH [11] | scorers `includes`, `match`, `pattern`, `exact`, `choice`, `math` [56] | AST, état final [49] |
| Résultats par question | `--log_samples` : `doc_id`, `resps`, `filtered_resps`, métriques, empreintes `*_hash` [57] | journaux `.eval`, `samples_df()` (`id`, `epoch`, `score_*`) [58] | fichiers de score par catégorie ; `ast_checker` renvoie `{valid, error, error_type}` par item [13] |
| Statistiques intégrées | stderr bootstrap, `bootstrap_iters` = 100 000 [57] | `stderr(cluster=…)`, `bootstrap_stderr` (1 000 tirages) [59] | aucune trouvée |
| Comparaison appariée entre modèles | non documentée | non documentée (jointure à faire soi-même) [58] | non |
| Poids des dépendances | base sans torch depuis déc. 2025 [51] | léger (non vérifié en détail) | lourd : `sentence-transformers` (donc torch), `faiss-cpu`, `numpy==1.26.4` épinglé, plusieurs SDK de fournisseurs [53] |

**Lecture :** Inspect est le mieux outillé. Le harnais maison se justifie par l'API native et par la mesure énergie/vitesse déjà en place, pas par la contamination : celle-ci dépend des items, pas du harnais (voir section 1).

### 2.3 Ce qu'il faut emprunter

| Composant | Licence | Dépendances | Comment l'intégrer |
|---|---|---|---|
| Vérificateurs IFBench (AllenAI) | code Apache-2.0, données ODC-BY-1.0 | `absl-py`, `langdetect`, `nltk`, `immutabledict`, `emoji`, `syllapy`, `pydantic` ; ni spacy ni torch [14] | paquet `ifbench` importable ; entrée en JSONL prompt/réponse [14] |
| Vérificateurs IFEval (google-research) | non confirmée par cette recherche | `absl`, `langdetect`, `nltk`, `immutabledict` [60] | à copier, ou à reprendre de lm-eval (MIT [61]) |
| Vérificateur AST de BFCL | Apache-2.0 [53] | **ne s'importe pas seul** : `ast_checker.py` charge `MODEL_CONFIG_MAPPING`, qui importe tous les handlers [13] | copier `ast_checker.py` et `type_convertor/`, puis retirer ce lien |
| Vérificateurs FR de M-IFEval | code Apache-2.0, dépôt `lightblue-tech/M-IFEval` [15] | modèles spaCy `es_core_news_sm` et `xx_sent_ud_sm` [15] | à copier |
| Format par item | — | — | reprendre l'union des champs de lm-eval et d'Inspect : id, empreintes du prompt et de la cible, réponse brute, réponse parsée, score par métrique, `epoch` (répétition), colonne de grappe (*cluster*), tokens [57][58] |

### 2.4 Pièges d'Ollama (v0.40.2 du 08/10/2026 [62])

1. **`format` n'est pas fiable avec `think`.** L'issue #18774, ouverte le 03/10/2026 (Ollama 0.35.1, gemma4:e4b), montre qu'avec `think: true` le modèle peut répondre directement et ignorer le schéma : HTTP 200, réponse « 391 » [16]. Vérifié à la source. Sur le backend MLX, `format` est ignoré en silence [50] (confiance faible). **Conséquence :** valider chaque sortie contre le schéma côté client, et consigner `think`, le backend et la version d'Ollama pour chaque item.
2. **Les logprobs sont documentés de façon contradictoire.** L'API native `/api/chat` documente `logprobs` et `top_logprobs` [63], la page `/v1` les dit non supportés [9], alors que la release 0.12.11 les annonçait sur les deux [64]. À tester sur une installation réelle avant d'en dépendre. Le protocole recommandé (génération et correction) n'en a de toute façon pas besoin.
3. **Le déterminisme reste à mesurer, pas à supposer.** `seed` est documenté comme garant de sorties reproductibles [63]. Pourtant, une ancienne issue (2024) observe une première exécution différente des suivantes [65], et `OLLAMA_NUM_PARALLEL` peut retomber en silence à une seule file [66] (confiance faible pour les deux). **Conséquence :** fixer `OLLAMA_NUM_PARALLEL=1`, lancer une requête de chauffe jetée, fixer `seed`, `temperature` et `num_ctx` à chaque requête, et mesurer la stabilité sur N répétitions.
4. **Lire les capacités avant d'envoyer `tools` ou `think`.** Depuis la 0.35.1, les modèles qui déclarent la capacité `decision` ne sont plus proposés pour le chat, les outils ou la réflexion [62]. Quand `think` reçoit une chaîne, sa valeur doit correspondre exactement à l'une de celles que liste `/api/show` [63].
5. **Épingler la version.** La numérotation des releases n'est pas chronologique : la v0.35.1 (29/09) est sortie après la v0.40.0 (25/09) [62].

## 3. Statistiques de comparaison appariée et taille d'échantillon

**Question :** comment comparer deux modèles évalués sur les mêmes questions, et combien de questions faut-il pour détecter un écart de 10 ou de 20 points ?

### 3.1 Méthode

- **Test : McNemar sur la table 2×2 des réussites par question.** C'est le test conçu pour des observations binaires appariées [67]. Pour des algorithmes qu'on n'exécute qu'une fois, Dietterich le retient comme le seul à l'erreur de type I acceptable [68] (confiance moyenne : résumé lu, pas le texte intégral). Le test non apparié de deux proportions est à proscrire [68].
- **Prendre la version exacte (binomiale).** Elle s'impose dès que les paires discordantes sont peu nombreuses, moins de 20 environ [69]. Elle se calcule avec `statsmodels…mcnemar(table, exact=True)` [70] ou `scipy.stats.binomtest(b, b+c)` [71].
- **Publier la différence, pas seulement la valeur p.** Il faut donner la différence par question, son erreur-type appariée et la corrélation entre modèles [2]. Dans l'exemple de Miller, une corrélation de 0,5 retranche un tiers de la variance [2].
- **Utiliser des erreurs-types groupées quand des items partagent un contexte** : plusieurs questions sur un même passage RAG, variantes d'un même gabarit. Dans les exemples de Miller, elles atteignent environ 3 fois les erreurs-types naïves [2]. Pour le banc, chaque item doit donc porter un identifiant de groupe.
- **Le bootstrap apparié est une option pour les métriques non binaires**, comme une F1 d'extraction ou une note du juge. Méthode : b = 10⁶ rééchantillonnages, puis compter les rééchantillonnages x⁽ⁱ⁾ où δ(x⁽ⁱ⁾) > 2δ(x), δ étant l'écart de score entre les deux modèles et x le jeu de test [72]. Dror le déconseille sur un petit jeu de test [67].

### 3.2 Taille d'échantillon (α = 0,05 bilatéral, puissance 80 %)

ψ désigne la part de questions discordantes, c'est-à-dire où un seul des deux modèles réussit. C'est elle qui fixe le N : plus deux modèles se ressemblent, moins il faut de questions.

| Écart | ψ = 0,2 | ψ = 0,3 | ψ = 0,4 | Sans appariement |
|---|---|---|---|---|
| **10 points** (60 → 70 %), formule de Connor | 155 | 234 | 312 | ≈ 354 à 356 |
| 10 points, McNemar exact | 168 | 249 | 329 | |
| **20 points** (50 → 70 %), formule de Connor | 37 | 57 | 77 | ≈ 91 à 93 |
| 20 points, McNemar exact | 39 | 61 | 84 | |

Les formules ont deux sources concordantes. La formule de Connor (1987) est documentée par SAS [1], et PASS (NCSS) en donne une forme algébriquement identique [73]. La formule de Miller ne s'en écarte que de 3 à 6 questions [2]. J'ai refait les calculs indépendamment (script `digests/D3-verif-mcnemar_n.py`, voir le journal de bord) et ils concordent. Statut : **vérifié**.

**Ce que permet le banc actuel (environ 30 items) :**
- un écart de 10 points n'est détecté que dans 8 à 10 % des cas ;
- un écart de 20 points, dans 31 à 57 % des cas ;
- l'écart minimal détectable est de 20 à 29 points.

**À plus grande échelle :**
- l'écart minimal détectable tombe à 6 à 8 points pour N = 500 et à 4 à 6 points pour N = 1 000 (calcul du rapport à partir de la formule de Miller [2]) ;
- pour un nouveau jeu, Miller recommande au moins 1 000 questions [2].

**Lecture pour le budget :** avec environ 800 items par piste, l'objectif de détecter un écart de 10 points est largement atteint (≥ 330 items). Une sous-piste de 85 items suffit pour un écart de 20 points. Ces chiffres supposent des items indépendants : quand les items sont groupés, il faut compter avec l'effet de grappe [2].

### 3.3 Température et répétitions

- **La température 0 ne garantit pas le déterminisme.** Atil et al. mesurent jusqu'à 15 % de variation de précision sur 10 exécutions dans un réglage censé être déterministe [17] (confiance moyenne : résumé lu). La cause principale est la non-invariance des noyaux GPU à la taille du lot [18]. Aucune de ces sources ne traite d'Ollama ni de llama.cpp.
- **Miller déconseille de baisser la température dans le seul but de réduire la variance.** Il recommande K tirages par question, avec un gain plafonné à 2/3 de la variance dans son exemple [2].
- **Conséquence pratique.** Avec K > 1 tirages, le score par question devient une proportion et McNemar ne s'applique plus tel quel. On passe à une erreur-type appariée sur les moyennes par question, ou à un bootstrap apparié [2][72]. Avec le budget de 5 à 6 jours, la voie la plus simple est un seul tirage (K = 1) à température 0, seed fixée, avec McNemar exact, complété par un contrôle de stabilité. Ce contrôle consiste à rejouer un sous-ensemble et à mesurer la part de réponses qui changent (voir 2.4).

### 3.4 Comparaisons multiples et classement

- **Holm plutôt que Bonferroni.** Holm reste valide quelle que soit la dépendance entre les tests [74], et il est plus puissant que Bonferroni-Dunn [75]. Attention : dans statsmodels, `multipletests` utilise Holm-Šidák par défaut, il faut passer `method='holm'` [76].
- **Réduire la famille de tests.** Comparer chaque modèle au meneur demande k−1 tests au lieu de k(k−1)/2 [75]. Pour 19 modèles, cela donne 18 tests au lieu de 171.
- **Réserver BH (FDR) à une matrice exploratoire « qui bat qui »** [74].
- **Pour une conclusion transversale** du type « A est meilleur sur la plupart des pistes », compter les pistes gagnées avec l'estimateur k̂_Bonferroni [74].
- **Friedman et Nemenyi ne convient pas par item** : son N compte des jeux de données, pas des questions [75].
- **Présenter un rang approché.** On peut suivre la méthode de Chatbot Arena : R = 1 + le nombre de modèles dont l'intervalle de confiance simultané est entièrement au-dessus du sien [77]. On peut aussi présenter des groupes de modèles indistinguables, à la manière d'un diagramme de différence critique (CD) [75].

### 3.5 Élimination adaptative (hors périmètre v1)

Hors périmètre v1, voir R8. Si le sujet revient, deux méthodes paient le coût des regards intermédiaires, qui invalident un intervalle de confiance à taille fixe [78] : la dépense d'alpha de type O'Brien-Fleming [79] et les Hoeffding races [80]. Toutes deux exigent un ordre d'items figé. La réduction d'items par IRT (tinyBenchmarks) n'est qu'un pré-tri : elle exige un historique de calibration [81].

## 4. Enseignements transversaux

Ces cinq constats n'apparaissent qu'en croisant les trois dimensions.

1. **La contamination se règle dans les items, pas dans le harnais.**
   - Aucun framework n'offre de protection contre la contamination (section 2).
   - Les jeux statiques connus sont saturés ou contaminés [4][6].
   - Les jeux qui résistent sont des **générateurs** : OneRuler (MIT, français inclus) [30], RULER [29], et la recette VAR-MATH, à réimplémenter [7].
   - Il faut donc investir dans les générateurs et les items privés, pas dans le harnais.
2. **Les jeux en français seul manquent d'items pour détecter un écart de 10 points.**
   - M-IFEval FR ne compte que 235 prompts [22], sous les 249 à 329 items requis pour 10 points dès que les modèles divergent sur 30 % des questions ou plus (section 3.2).
   - Utilisé seul, son écart minimal détectable est d'environ 12 à 15 points.
   - Pour détecter 10 points, il faut soit le combiner à IFBench (EN, 300) dans une même piste d'instructions, soit l'étendre avec des prompts maison qui réutilisent ses vérificateurs.
3. **Les items groupés réduisent le N effectif.**
   - Les tâches multi-turn de BFCL, les questions OneRuler sur une même botte de foin, les questions PIAF sur un même passage et les variantes d'un même gabarit mathématique partagent leur contexte.
   - L'erreur-type groupée peut alors atteindre environ 3 fois l'erreur naïve [2].
   - Le format de résultat doit porter un identifiant de groupe par item [58][2], et le N par piste se compte en **groupes** plutôt qu'en items.
4. **Fiabilité de la mesure et validité statistique sont liées.**
   - McNemar à un seul tirage (K = 1) suppose qu'un modèle répond toujours de la même façon à un item.
   - Or `format` peut être ignoré avec `think` [16], et un réglage censé être déterministe varie d'une exécution à l'autre [17].
   - Il faut donc mesurer le taux de réponses qui changent sur un sous-ensemble rejoué. S'il n'est pas négligeable devant la part de questions discordantes entre modèles, il faut passer à K > 1 tirages et à l'erreur-type appariée sur les moyennes [2].
5. **Items privés et dépôt public.** Des items **privés** anti-contamination publiés dans un dépôt public perdent leur intérêt. Ils doivent vivre hors du dépôt, avec seulement leur empreinte versionnée. Pour les exclusions de licence, voir 1.3.

## 5. Recommandations

Chaque recommandation est rattachée à son consommateur (`bmad-spec`, puis architecture du banc) et à sa base de confiance.

| # | Recommandation | Pour | Base de confiance |
|---|---|---|---|
| R1 | **Harnais maison sur `/api/chat`**, sans dépendance à lm-eval, Inspect ou bfcl-eval. Copier dans le dépôt : vérificateurs IFBench (Apache-2.0), vérificateurs M-IFEval FR (Apache-2.0, plus 2 modèles spaCy), `ast_checker` et `type_convertor` de BFCL (Apache-2.0) | spec, contraintes ; architecture | haute [10][53][13][14][15] |
| R2 | **Composition des pistes** (proposition, à arbitrer dans `bmad-spec`) : voir le tableau ci-dessous | spec, périmètre | moyenne : notes de la matrice 1.2 issues du jugement de l'auteur |
| R3 | **Au moins ≈ 330 items, ou groupes indépendants, par piste** pour détecter un écart de 10 points ; une sous-piste de 85 suffit pour un écart de 20 points. Mesurer la part de questions où les modèles divergent sur un pilote, puis réajuster le N | spec, exigences non fonctionnelles | haute [1][2][73] |
| R4 | **Statistiques** : McNemar exact par paire ; différence avec erreur-type appariée et IC à 95 % ; erreurs-types groupées par identifiant de groupe ; Holm sur les k−1 comparaisons au meneur (`method='holm'`) ; rang approché à la Chatbot Arena dans le rapport | spec, sorties ; architecture, module d'analyse | haute [2][74][75][77][76] |
| R5 | **Format de résultat par item**, en JSONL, une ligne par item, écrite sitôt l'item terminé : id, groupe, piste, empreinte du prompt, réponse brute, réponse parsée, score, `epoch`, `think`, backend, version d'Ollama, `seed`, `num_ctx`, tokens et énergie. Ce format sert aussi la reprise après arrêt | spec, données ; architecture | haute pour le contenu [57][58] |
| R6 | **Hygiène Ollama** : épingler la version ; `OLLAMA_NUM_PARALLEL=1` ; requête de chauffe jetée ; `seed`, `temperature` et `num_ctx` fixés à chaque requête ; lire les capacités via `/api/show` avant d'envoyer `tools` ou `think` ; valider chaque sortie JSON côté client ; contrôle de stabilité sur un sous-ensemble rejoué | spec, contraintes ; procédure de campagne | moyenne : issues en partie anciennes ou à source unique [62][63][16][66] |
| R7 | **Items privés et générés hors du dépôt public**, seule leur empreinte étant versionnée. Générateurs (OneRuler, maths à la VAR-MATH) avec graine fixée et versionnée | spec, contraintes ; architecture | moyenne [7][30] |
| R8 | **Élimination adaptative : ne pas l'implémenter en v1.** Le budget de 5 à 6 jours suffit. Si on en a besoin plus tard, prendre O'Brien-Fleming ou Hoeffding races avec un ordre d'items figé, après une simulation de l'erreur de type I | spec, hors périmètre | faible : synthèse non publiée [80][79] |

**R2, composition proposée des pistes** (effectifs indicatifs, à confronter au budget de 5 à 6 jours) :

| Piste | Sources | Correction |
|---|---|---|
| Suivi d'instructions | IFBench 300 (EN) [4] + M-IFEval FR 235 [22] ; IFEval seulement pour les modèles < 2B, ou abandonné | vérificateurs |
| Appel d'outils | BFCL v4 : live AST, multi-turn, irrelevance (pour l'abstention) ; ni non-live AST, saturé, ni web search, qui exige le réseau [47][27]. Plus une traduction FR maison d'environ 200 items, noms de fonctions et de paramètres inchangés | AST, état |
| Extraction JSON | échantillon stratifié de JSONSchemaBench (test) [28] + documents FR maison à extraire | validation de schéma + valeurs attendues |
| RAG / contexte long FR | OneRuler FR (NIAH, recherche d'une aiguille dans une botte de foin, dont la variante « aucune aiguille » ; CWE, extraction des mots les plus fréquents) à 8K–32K selon la mémoire disponible [31] + échantillon de PIAF [32] | correspondance exacte, F1 |
| Raisonnement | BBEH mini 460 [42] + maths FR générées (recette VAR-MATH, score strict) [7] | correspondance exacte, réponse numérique |
| Abstention | variante « aucune aiguille » de OneRuler [31] + irrelevance de BFCL [24] + items maison | déterministe |
| Rédaction FR | juge cloud (décision déjà prise ; hors du périmètre de cette recherche) | juge |

## 6. Questions ouvertes

| Question | Pourquoi c'est important | Pour y répondre |
|---|---|---|
| Quelle part de questions discordantes (ψ) entre deux SLM du catalogue ? | elle fixe le N réel entre 155 et 330 | pilote de 2 modèles sur 100 à 200 items par piste |
| Ollama 0.40.x est-il stable d'une exécution à l'autre sur tour-rtx3050 ? | conditionne le choix K = 1 | rejouer 10 fois un sous-ensemble, mesurer la part de réponses qui changent |
| Effectifs BFCL v4 live ; la catégorie memory s'exécute-t-elle hors ligne ? | dimensionner la piste outils | lire `BFCL_v4_live_*.json` ; tester l'embedder hors ligne |
| Scores OneRuler en français des modèles de 7–8B ; 32K tient-il en mémoire ? | éviter un plancher et un dépassement mémoire | figure 17 de l'article ; essai local |
| Les traductions de le-leadboard (bbh-fr, musr-fr, MATH_LVL5_fr) sont-elles fiables ? | possibles items FR gratuits | relire un échantillon de 30 items par jeu |
| Licence propre des gabarits GitHub de GSM-Symbolic | possible source de gabarits | lire le LICENSE de `apple/ml-gsm-symbolic` |
| Erreur de type I de l'élimination adaptative | seulement si R8 est rouvert | simulation Monte-Carlo |
| Statistiques d'accord entre juge cloud et étiquettes humaines | hors périmètre ici, nécessaire pour la piste rédaction | recherche dédiée ou pilote de calibration (déjà prévu) |
| Les vérificateurs d'IFBench fonctionnent-ils en français ? | seulement si IFBench est traduit | lire `instructions_util.py` |

## 7. Carte de péremption

Calculée avec `recon_kit.py staleness`. Fenêtres de revérification retenues : version et compatibilité 1 mois, fonctionnalité 3 mois, performance et contamination 3 mois (paysage IA), licence 6 mois.

Pour les licences, les versions et les fonctionnalités, la date retenue est celle de la lecture en direct (2026-10). Pour les scores et la contamination, c'est la date de la source.

Les formules et méthodes statistiques (Connor, Holm, O'Brien-Fleming, Miller) ne périment pas et sont exclues.

| Affirmation | Classe | Date retenue | À revérifier le | Périmée ? |
|---|---|---|---|---|
| [5] Scores Open LLM Leaderboard v2 de SLM 1B–14B (IFEval, BBH, MATH Lvl5, MuSR) | perf | 2025-02 | 2025-05-01 | **oui** |
| [4] IFBench : 300 prompts, 58 contraintes, saturation d'IFEval, scores | contamination | 2025-07 | 2025-10-01 | **oui** |
| [6] Contamination de Qwen2.5 sur MATH-500 | contamination | 2025-07 | 2025-10-01 | **oui** |
| [27] Scores BFCL des SLM par catégorie | perf | 2026-04 | 2026-07-01 | **oui** |
| [76] multipletests : Holm-Šidák par défaut | version | 2026-10 | 2026-11-01 | non |
| [10] Provider ollama d'Inspect sur /v1 (vérifié à la source) | compatibilite | 2026-10 | 2026-11-01 | non |
| [63] API native /api/chat : logprobs, think, format, seed | compatibilite | 2026-10 | 2026-11-01 | non |
| [62] Ollama v0.40.2 (08/10/2026), ordre des releases, capacité decision | version | 2026-10 | 2026-11-01 | non |
| [16] #18774 : format non appliqué avec think (vérifié à la source) | fonctionnalite | 2026-10 | 2027-01-01 | non |
| [11] Types des tâches leaderboard de lm-eval (multichoice vs génératif) | fonctionnalite | 2026-10 | 2027-01-01 | non |
| [13] ast_checker non importable seul, sortie par item | fonctionnalite | 2026-10 | 2027-01-01 | non |
| [30] Code OneRuler MIT avec scripts de génération (vérifié à la source) | licence | 2026-10 | 2027-04-01 | non |
| [15] Code M-IFEval Apache-2.0, FR/JA/ES, modèles spaCy (vérifié à la source) | licence | 2026-10 | 2027-04-01 | non |
| [48] Données GSM-Symbolic sous CC-BY-NC-ND-4.0 | licence | 2026-10 | 2027-04-01 | non |
| [42] BBEH : licences, 4 520 items, mini 460 | licence | 2026-10 | 2027-04-01 | non |
| [23] IFEval-fr de le-leadboard sans licence déclarée | licence | 2026-10 | 2027-04-01 | non |
| [33] FQuAD : non commercial, redistribution interdite | licence | 2026-10 | 2027-04-01 | non |

**Constat :** 4 affirmations de performance ou de contamination sont déjà périmées selon ces fenêtres. Les scores publiés de SLM datent de la génération 2024–2025 (Llama 3.2, Qwen2.5, Gemma 3) et ne couvrent pas les modèles actuels du catalogue. Le pilote (questions ouvertes, section 6) doit donc mesurer directement la saturation et la discordance sur les modèles réels, au lieu de se fier aux chiffres publiés.

**Prochaine revérification : 2026-11-01**, pour la version d'Ollama, son API et sa compatibilité (logprobs, `format` et `think`, issue #18774) ; à refaire avant de figer le harnais.

## 8. Annexe des sources

Date d'accès de toutes les sources : 2026-10-10.

| # | Affirmation ou constat étayé | Éditeur | Date de publication | Confiance |
|---|---|---|---|---|
| [1] | Formule de Connor (1987), puissance McNemar | [SAS Institute (PROC POWER)](https://support.sas.com/documentation/cdl/en/statug/67523/HTML/default/statug_power_details55.htm) | 2014-01 | haute |
| [2] | Erreurs-types appariées et groupées, puissance, K tirages, ≥ 1 000 questions | [Evan Miller, Anthropic (arXiv 2411.00640)](https://arxiv.org/abs/2411.00640) | 2024-11 | haute |
| [3] | Scores Gemma 3 IT (IFEval, BBH, BBEH) | [Google (fiche modèle)](https://ai.google.dev/gemma/docs/core/model_card_3) | 2025-03 | haute |
| [4] | IFBench : 300 prompts, 58 contraintes, saturation d'IFEval, scores | [AllenAI (arXiv 2507.02833)](https://arxiv.org/abs/2507.02833) | 2025-07 | haute |
| [5] | Scores Open LLM Leaderboard v2 de SLM 1B–14B (IFEval, BBH, MATH Lvl5, MuSR) | [Hugging Face (résultats bruts)](https://huggingface.co/datasets/open-llm-leaderboard/results) | 2025-02 | haute |
| [6] | Contamination de Qwen2.5 sur MATH-500 | [Fudan et al. (arXiv 2507.10532)](https://arxiv.org/abs/2507.10532) | 2025-07 | moyenne |
| [7] | VAR-MATH : chutes sur variantes, recette réimplémentable | [HK PolyU (arXiv 2507.12885)](https://arxiv.org/html/2507.12885) | 2025-07 | moyenne |
| [8] | GSM-Symbolic : baisses sur variantes numériques | [Apple (arXiv 2410.05229)](https://arxiv.org/abs/2410.05229) | 2024-10 | haute |
| [9] | Compatibilité OpenAI d'Ollama : pas de num_ctx, tool_choice, echo, logprobs | [Ollama (docs)](https://docs.ollama.com/api/openai-compatibility) | 2026-10 | haute |
| [10] | Provider ollama d'Inspect sur /v1 (vérifié à la source) | [UK AISI (docs)](https://inspect.aisi.org.uk/providers.html) | 2026-10 | haute |
| [11] | Types des tâches leaderboard de lm-eval (multichoice vs génératif) | [EleutherAI (GitHub)](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/tasks/leaderboard/README.md) | 2026 | haute |
| [12] | lm-eval : chat-completions en génération seule | [EleutherAI (GitHub, API guide)](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/API_guide.md) | 2026 | haute |
| [13] | ast_checker non importable seul, sortie par item | [UC Berkeley Gorilla (code)](https://raw.githubusercontent.com/ShishirPatil/gorilla/main/berkeley-function-call-leaderboard/bfcl_eval/eval_checker/ast_eval/ast_checker.py) | 2026-10 | haute |
| [14] | IFBench : licence et dépendances légères | [AllenAI (pyproject)](https://raw.githubusercontent.com/allenai/IFBench/main/pyproject.toml) | 2026-10 | haute |
| [15] | Code M-IFEval Apache-2.0, FR/JA/ES, modèles spaCy (vérifié à la source) | [Lightblue (GitHub)](https://github.com/lightblue-tech/M-IFEval) | 2025-02 | haute |
| [16] | #18774 : format non appliqué avec think (vérifié à la source) | [GitHub ollama/ollama](https://github.com/ollama/ollama/issues/18774) | 2026-10 | haute |
| [17] | Jusqu'à 15 % de variation à température 0 | [Atil et al. (arXiv 2408.04667)](https://arxiv.org/abs/2408.04667) | 2024-08 | moyenne |
| [18] | Non-déterminisme dû à la non-invariance au lot | [Thinking Machines Lab](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) | 2025-09 | haute |
| [19] | Licence et taille d'IFEval | [Google (fiche HF)](https://huggingface.co/datasets/google/IFEval) | 2023-11 | haute |
| [20] | Licence ODC-BY-1.0 des données IFBench | [AllenAI (fiche HF)](https://huggingface.co/datasets/allenai/IFBench_test) | 2025-07 | haute |
| [21] | Licence Apache-2.0 du code IFBench | [AllenAI (GitHub)](https://github.com/allenai/IFBench/blob/main/LICENSE) | 2025-07 | haute |
| [22] | M-IFEval : 235 prompts FR, contraintes propres au français, scores | [Lightblue (arXiv 2502.04688)](https://arxiv.org/abs/2502.04688) | 2025-02 | haute |
| [23] | IFEval-fr de le-leadboard sans licence déclarée | [le-leadboard (fiche HF)](https://huggingface.co/datasets/le-leadboard/IFEval-fr) | 2025-02 | haute |
| [24] | Licence Apache-2.0 et tailles BFCL | [UC Berkeley Gorilla (fiche HF)](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard) | 2024-09 | haute |
| [25] | BFCL v4 web search, notation AST/état déterministe, multi-turn 4 × 200 | [UC Berkeley Gorilla (blog)](https://gorilla.cs.berkeley.edu/blogs/15_bfcl_v4_web_search.html) | 2025-07 | haute |
| [26] | Jeu GregoryD : traduction automatique d'un jeu d'entraînement | [GregoryD (fiche HF)](https://huggingface.co/datasets/GregoryD/explicit-function-calling-french) | 2024-02 | haute |
| [27] | Scores BFCL des SLM par catégorie | [UC Berkeley Gorilla (CSV du leaderboard)](https://gorilla.cs.berkeley.edu/data_overall.csv) | 2026-04 | haute (une source) |
| [28] | JSONSchemaBench : MIT, ≈ 10 000 schémas | [EPFL dlab (fiche HF)](https://huggingface.co/datasets/epfl-dlab/JSONSchemaBench) | 2025-01 | haute |
| [29] | RULER : générateur synthétique, 13 tâches, Apache-2.0 | [NVIDIA (arXiv 2404.06654)](https://arxiv.org/abs/2404.06654) | 2024-04 | haute |
| [30] | Code OneRuler MIT avec scripts de génération (vérifié à la source) | [UMass Amherst (GitHub)](https://github.com/mungg/OneRuler) | 2025-03 | haute |
| [31] | OneRuler : 26 langues dont FR, 8K–128K, 50 exemples/config, échecs « aucune réponse » | [UMass Amherst (arXiv 2503.01996)](https://arxiv.org/abs/2503.01996) | 2025-09 | haute |
| [32] | PIAF : MIT, 3 835 questions sur Wikipédia FR | [Etalab / AgentPublic (fiche HF)](https://huggingface.co/datasets/AgentPublic/piaf) | 2020-02 | haute |
| [33] | FQuAD : non commercial, redistribution interdite | [Illuin Technology (fiche HF, via résultat de recherche)](https://huggingface.co/datasets/fquad) | 2020-02 | moyenne |
| [34] | Miroir fquad2_test en Apache-2.0 | [Manuel Faysse (fiche HF)](https://huggingface.co/datasets/manu/fquad2_test) | 2024-04 | moyenne |
| [35] | Licence CC-BY-4.0 et taille de MuSR sur HF | [UT Austin TAUR Lab (fiche HF)](https://huggingface.co/datasets/TAUR-Lab/MuSR) | 2024 | haute |
| [36] | Licence MIT de MuSR sur GitHub | [Zayne Sprague (GitHub)](https://github.com/Zayne-sprague/MuSR/blob/main/LICENSE) | 2024 | haute |
| [37] | MuSR proche du hasard, format MATH Lvl5 (Open LLM Leaderboard) | [Hugging Face (doc)](https://huggingface.co/docs/leaderboards/open_llm_leaderboard/about) | 2024-06 | haute |
| [38] | Anomalie de noms dans musr-fr | [le-leadboard (fiche HF)](https://huggingface.co/datasets/le-leadboard/musr-fr) | 2024-10 | moyenne |
| [39] | Licence MIT de BBH | [Suzgun et al. (GitHub)](https://github.com/suzgunmirac/BIG-Bench-Hard/blob/main/LICENSE) | 2022-10 | haute |
| [40] | BBH saturé, BBEH plus dur | [Google DeepMind (arXiv 2502.19187)](https://arxiv.org/abs/2502.19187) | 2025-02 | haute |
| [41] | bbh-fr Apache-2.0, méthode non documentée | [le-leadboard (fiche HF)](https://huggingface.co/datasets/le-leadboard/bbh-fr) | 2024-10 | moyenne |
| [42] | BBEH : licences, 4 520 items, mini 460 | [Google DeepMind (GitHub)](https://github.com/google-deepmind/bbeh) | 2025-02 | haute |
| [43] | Licence MIT de MATH | [Dan Hendrycks (GitHub)](https://github.com/hendrycks/math/blob/main/LICENSE) | 2021-03 | haute |
| [44] | MATH-500 issu de PRM800K, fiche HF sans licence | [Hugging Face H4 (fiche HF)](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) | 2023-05 | haute |
| [45] | Anomalie de niveau dans MATH_LVL5_fr | [le-leadboard (fiche HF)](https://huggingface.co/datasets/le-leadboard/MATH_LVL5_fr) | 2024-10 | moyenne |
| [46] | BFCL v4 memory : 150+ questions, backends en mémoire | [UC Berkeley Gorilla (blog)](https://gorilla.cs.berkeley.edu/blogs/16_bfcl_v4_memory.html) | 2025 | moyenne |
| [47] | Catégories BFCL v4, web search exige SerpAPI | [UC Berkeley Gorilla (GitHub)](https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/TEST_CATEGORIES.md) | 2025 | haute |
| [48] | Données GSM-Symbolic sous CC-BY-NC-ND-4.0 | [Apple (fiche HF)](https://huggingface.co/datasets/apple/GSM-Symbolic) | 2024-10 | haute |
| [49] | Harnais BFCL : serveur compatible OpenAI, handler à écrire | [UC Berkeley Gorilla (README)](https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/README.md) | 2026 | haute |
| [50] | Autres échecs de format (#15260, #17933, #18441, #15288) | [GitHub ollama/ollama](https://github.com/ollama/ollama/issues/17933) | 2026 | faible |
| [51] | lm-eval 0.4.13, MIT, base sans torch | [PyPI](https://pypi.org/project/lm-eval/) | 2026-08 | haute |
| [52] | inspect-ai 0.3.278, MIT, cadence de releases | [PyPI](https://pypi.org/project/inspect-ai/) | 2026-10 | haute |
| [53] | bfcl-eval : Apache-2.0, dépendances lourdes | [UC Berkeley Gorilla (pyproject)](https://raw.githubusercontent.com/ShishirPatil/gorilla/main/berkeley-function-call-leaderboard/pyproject.toml) | 2026-10 | haute |
| [54] | Catalogue inspect_evals | [UK AISI (GitHub Pages)](https://ukgovernmentbeis.github.io/inspect_evals/) | 2026 | moyenne |
| [55] | BFCL dans inspect_evals : AST et état, sans juge | [UK AISI (GitHub)](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main/src/inspect_evals/bfcl) | 2026 | haute |
| [56] | Scorers intégrés d'Inspect | [UK AISI (docs)](https://inspect.aisi.org.uk/scorers.html) | 2026 | haute |
| [57] | Champs de --log_samples, bootstrap_iters = 100 000 | [EleutherAI (code evaluator.py)](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/lm_eval/evaluator.py) | 2026-10 | haute |
| [58] | Journaux .eval et samples_df d'Inspect | [UK AISI (docs)](https://inspect.aisi.org.uk/dataframe.html) | 2026-10 | haute |
| [59] | stderr(cluster) et bootstrap_stderr d'Inspect | [UK AISI (docs)](https://inspect.aisi.org.uk/metrics.html) | 2026-10 | haute |
| [60] | Dépendances du code IFEval de google-research | [Google Research (GitHub)](https://raw.githubusercontent.com/google-research/google-research/master/instruction_following_eval/requirements.txt) | 2026-10 | haute |
| [61] | lm-eval sous MIT, extra ifeval | [EleutherAI (pyproject)](https://raw.githubusercontent.com/EleutherAI/lm-evaluation-harness/main/pyproject.toml) | 2026-10 | haute |
| [62] | Ollama v0.40.2 (08/10/2026), ordre des releases, capacité decision | [Ollama (GitHub releases)](https://github.com/ollama/ollama/releases) | 2026-10 | haute |
| [63] | API native /api/chat : logprobs, think, format, seed | [Ollama (docs)](https://docs.ollama.com/api/chat) | 2026-10 | moyenne |
| [64] | Logprobs annoncés en 0.12.11 | [Ollama (release)](https://github.com/ollama/ollama/releases/tag/v0.12.11) | 2025-11 | moyenne |
| [65] | Première exécution différente (#5321) | [GitHub ollama/ollama](https://github.com/ollama/ollama/issues/5321) | 2024-06 | faible |
| [66] | OLLAMA_NUM_PARALLEL retombe en silence (#17556) | [GitHub ollama/ollama](https://github.com/ollama/ollama/issues/17556) | 2026 | faible |
| [67] | Choix du test : McNemar pour binaire apparié, bootstrap déconseillé sur petit jeu | [ACL 2018 (Dror et al.)](https://aclanthology.org/P18-1128.pdf) | 2018-07 | haute |
| [68] | McNemar seul test à erreur de type I acceptable (exécution unique) | [Neural Computation (Dietterich 1998)](https://mlanthology.org/neco/1998/dietterich1998neco-approximate/) | 1998-10 | moyenne |
| [69] | Seuil de ~20 paires discordantes pour le test exact | [MetricGate (doc de calculateur)](https://metricgate.com/docs/sample-size-mcnemar-paired) | 2026-05 | moyenne |
| [70] | statsmodels mcnemar(exact=True) | [statsmodels (doc)](https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html) | 2026-08 | haute |
| [71] | scipy.stats.binomtest | [SciPy (doc)](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html) | 2026-10 | moyenne |
| [72] | Bootstrap apparié, b = 10⁶ | [EMNLP-CoNLL 2012 (Berg-Kirkpatrick et al.)](https://nlp.cs.berkeley.edu/pubs/BergKirkpatrick-Burkett-Klein_2012_Significance_paper.pdf) | 2012-07 | haute |
| [73] | Formule de Machin et al., identique à Connor | [NCSS (doc PASS)](https://www.ncss.com/wp-content/themes/ncss/pdf/Procedures/PASS/Tests_for_Two_Correlated_Proportions-McNemar_Test.pdf) | inconnue | moyenne |
| [74] | Holm, BH, k̂_Bonferroni pour plusieurs jeux | [TACL 2017 (Dror et al.)](https://aclanthology.org/Q17-1033.pdf) | 2017-12 | haute |
| [75] | Comparaison à un témoin, Holm, Friedman/Nemenyi, diagrammes CD | [JMLR (Demšar 2006)](https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf) | 2006-01 | haute |
| [76] | multipletests : Holm-Šidák par défaut | [statsmodels (doc)](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html) | 2026-08 | haute |
| [77] | Rang approché par IC simultanés (Chatbot Arena) | [Chiang et al. (arXiv 2403.04132, ICML 2024)](https://arxiv.org/abs/2403.04132) | 2024-03 | haute |
| [78] | Arrêt selon les données et couverture des IC ; confidence sequences | [Hsu et Shekhar (arXiv 2607.17409)](https://arxiv.org/abs/2607.17409) | 2026-07 | moyenne |
| [79] | Fonction de dépense O'Brien-Fleming (Lan-DeMets) | [CRAN gsDesign (doc)](https://rdocumentation.org/packages/gsDesign/versions/3.0-1/topics/sfLDOF) | 2016-01 | moyenne |
| [80] | Hoeffding races, bornes simultanées | [NIPS 1993 (Maron et Moore)](https://papers.neurips.cc/paper_files/paper/1993/file/02a32ad2669e6fe298e607fe7cc0e1a0-Paper.pdf) | 1993-12 | haute |
| [81] | tinyBenchmarks : ≈ 2 % d'erreur avec 100 items, limites | [Maia Polo et al. (arXiv 2402.14992, ICML 2024)](https://arxiv.org/abs/2402.14992) | 2024-05 | haute |
