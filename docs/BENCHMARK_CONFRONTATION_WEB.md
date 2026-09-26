# Confrontation des résultats aux mesures publiées

*26 septembre 2026. Données : exports finaux des trois machines, en `b36cb8c`.*

Ce document confronte les mesures des trois machines du benchmark multi-machine aux mesures et études publiées sur le web. Les questions sont les suivantes :
- ces mesures sont-elles cohérentes avec ce qui est publié ?
- où s'en écartent-elles, et pourquoi ?
- qu'apportent-elles de nouveau ?

| Machine | Matériel | Bande passante mémoire |
|---|---|---|
| `poste-rtx3060` | RTX 3060 Laptop 6 Go (95 W, mode Turbo), Ryzen 7 5800H, 31 Go | 336 Go/s (192 bits à 14 Gbps : fréquence relevée par `nvidia-smi`) |
| `tour-rtx3050` | RTX 3050 8 Go (desktop), Ryzen 5 7600, 31 Go | 224 Go/s (128 bits à 14 Gbps) |
| `pro-elitebook-x360` | Core i5-1145G7, CPU seul, 16 Go de LPDDR4x-4266 | environ 68 Go/s théoriques (2 canaux) |

**Méthode.** Quatre recherches parallèles ont été menées :
1. le débit et la bande passante ;
2. la qualité ;
3. les modèles récents ;
4. les effets de mesure.

Les sources qui portent une conclusion ont été relues le 26/09 et sont marquées ✔. Les autres proviennent des agents de recherche et n'ont pas été relues. Plusieurs sont des blogs sans méthodologie publiée : elles sont signalées comme telles et ne servent jamais seules à conclure.

Verdicts : **cohérent** · **écart à expliquer** · **donnée nouvelle** (rien de comparable n'a été trouvé).

---

## Synthèse

1. **Les débits sont cohérents avec les mesures publiées**, là où une comparaison existe :
   - Llama 3.2 3B : 105 tok/s sur la RTX 3060 Laptop, contre 128 sur une RTX 3060 desktop 12 Go ;
   - Bonsai 8B : 99 tok/s, contre 81 annoncés par l'éditeur sur une RTX 3060 Laptop.
2. **Le poste n'exploite pas toute son avance de bande passante sur la tour** : il est 1,13 à 1,31 fois plus rapide, pour 1,50 fois plus de bande passante. C'est un écart à expliquer. La piste privilégiée est un coût fixe par token (processeur, limite de puissance du GPU portable), plus lourd sur les petits modèles.
3. **Les scores de qualité suivent l'ordre attendu** : les plus petits modèles sont en bas, les familles gardent leur hiérarchie, et la quantification IQ2 pénalise plus que l'IQ3. À température 0, le poste et la tour donnent le même raisonnement pour 16 modèles sur 22. Les autres écarts, d'une ou deux questions, correspondent à un non-déterminisme entre GPU que la littérature récente documente.
4. **La plupart des modèles récents n'ont aucune mesure publiée sur ce type de matériel** : Ling 3.0 Tiny, MiniCPM5, LFM 2.5, Gemma 4 E2B et E4B, Granite 4.2, OLMo 3. Ce sont des **données nouvelles**. C'est aussi le cas des courbes de vitesse par palier de contexte sur 6 Go de VRAM.
5. **Un effet de mesure ne semble documenté nulle part** : la chute du débit d'inférence d'un facteur 2 à 4 quand Windows passe en veille moderne, écran éteint. Le débit bimodal de trois modèles sur le portable, d'abord classé parmi les effets nouveaux, s'explique par un mécanisme connu : la limite de puissance du GPU portable change d'une génération à l'autre (§4).

   Les autres effets (générations courtes, dispersion à 2 exécutions, profils constructeur) sont connus, et nos correctifs vont dans le sens des bonnes pratiques.

---

## 1. Débit de génération

### 1.1 Comparaison aux mesures publiées

| Mesure | Notre valeur | Publié | Verdict |
|---|---|---|---|
| Llama 3.2 3B Q4_K_M, RTX 3060 | 105 tok/s (Laptop 6 Go, 336 Go/s) | 128,3 tok/s sur une RTX 3060 desktop 12 Go (360 Go/s), llama.cpp — [tyolab, mai 2026](https://www.tyolab.com/blog/2026/05/11-64gb-ram-12gb-vram-the-honest-local-llm-benchmark/) ✔ | **Cohérent.** Le rapport de 0,82 est un peu sous le rapport de bande passante (0,93), ce qui est attendu pour un GPU portable limité à 95 W. |
| Petit modèle 1B, RTX 3060 Laptop 6 Go | Gemma 3 1B : 187 tok/s ; LFM 2.5 1.2B : 270 tok/s | Llama 3.2 1B Q4_K_M : 151 tok/s, même GPU — [localscore.ai](https://www.localscore.ai/accelerator/767) ✔ | **Cohérent** en ordre de grandeur (modèles différents) |
| 8B entièrement sur GPU, RTX 3060 Laptop 6 Go | Jamais atteint dans notre protocole, qui monte à 16K de contexte | Llama 3.1 8B Q4_K_M : 40,8 tok/s ; Qwen2.5 14B : 1,1 tok/s — [localscore.ai](https://www.localscore.ai/accelerator/767) ✔ | **Cohérent.** Un 8B en Q4 tient dans 6 Go à contexte court seulement. Le 14B publié illustre la même chute brutale que nos mesures (voir 1.4). |
| Bonsai 8B (1-bit), RTX 3060 Laptop | 97 à 99 tok/s | 81 tok/s, chiffre de l'éditeur PrismML repris par [Firethering](https://firethering.com/bonsai-8b-1bit-llm/) ✔ | **Cohérent**, et même 20 % au-dessus de l'annonce. La version de llama.cpp ou le contexte peuvent différer. |
| RTX 3050 | Tour (8 Go, 224 Go/s) : Llama 3.2 3B à 85 tok/s | La seule page trouvée concerne une RTX 3050 **6 Go**, une autre variante au bus plus étroit : Llama 3.2 1B à 104 tok/s, Llama 3.1 8B à 37 tok/s — [localscore.ai](https://www.localscore.ai/accelerator/977) ✔ | Pas de comparaison directe possible |
| Nemotron 3 Nano 4B, Qwen 3.5 4B, Gemma 4 12B | Au-dessus des chiffres de blogs (Qwen 3.5 4B : 72 tok/s contre « 25-40 » annoncés sur RTX 3060) | Blogs agrégateurs sans configuration publiée (markaicode, buildfastwithai) | Écart **non concluant** : ces sources sont trop peu fiables pour trancher |

### 1.2 Bande passante : ce que prédit la théorie

Pendant la génération, chaque token relit tous les poids du modèle : le débit est donc d'abord limité par la bande passante mémoire. Sur les 16 modèles qui tiennent entièrement dans le GPU des deux machines (campagne « au mieux », jusqu'à 8K de contexte) :

| | Modèles ≤ 1B | Modèles de 1,5 à 3,5 Go | Théorie (336 / 224) |
|---|---|---|---|
| Rapport poste / tour | 1,14 à 1,24 | 1,18 à 1,31 | 1,50 |
| Part de la bande passante utilisée, poste | 45 à 59 % | 62 à 86 % | — |
| Part de la bande passante utilisée, tour | 57 à 76 % | 76 à 105 % | — |

- La fréquence mémoire du poste a été vérifiée : 7001 MHz selon `nvidia-smi`, soit 14 Gbps effectifs. L'hypothèse d'une mémoire bridée à 12 Gbps (288 Go/s), avancée par une des recherches, est donc écartée.
- **Écart à expliquer** : le poste reste en deçà de son avantage théorique, surtout sur les plus petits modèles. Cela désigne un coût fixe par token, indépendant de la taille du modèle, qui pèse d'autant plus que la génération est rapide. Deux candidats, tous deux plausibles et non vérifiés :
  - le processeur : le Ryzen 5 7600 (Zen 4) de la tour lance les calculs et échantillonne plus vite que le Ryzen 7 5800H (Zen 3) ;
  - la limite de puissance à 95 W du GPU portable, relevée pendant la campagne (motif `SW power cap`).
- Les modèles Gemma 4 E2B et E4B dépassent 100 % : une partie de leurs fichiers (les plongements par couche) n'est pas relue à chaque token. Le calcul simplifié ne s'applique donc pas à eux.
- **Bonsai 1-bit** n'utilise que 34 à 46 % de la bande passante : ses noyaux de calcul le limitent plus que la mémoire. Sur CPU, l'écart devient énorme : 3,0 tok/s sur l'EliteBook, contre 7 à 11 tok/s pour des modèles pourtant plus volumineux (1,5 à 4,3 Go). C'est une **donnée nouvelle** : les noyaux 1-bit semblent encore peu optimisés sur CPU x86.

### 1.3 EliteBook (CPU seul)

La tour est 8 à 12 fois plus rapide que l'EliteBook, alors que sa bande passante n'est que 3,3 fois supérieure. Le CPU est donc aussi limité par le calcul et la latence mémoire. C'est **cohérent** avec le fonctionnement de llama.cpp sur CPU, mais aucune mesure publiée n'a été trouvée pour l'i5-1145G7 : c'est une **donnée nouvelle**.

### 1.4 Débordement sur le CPU (6 Go de VRAM)

Au-delà d'environ 4 à 5 Go chargés, le modèle ne tient plus entièrement dans le GPU du poste, et le débit chute. Les débits viennent de la campagne « au mieux » (jusqu'à 8K de contexte), sauf pour Gemma 4 12B (vitesse seule au poste, campagne standard à la tour). La part sur GPU est celle du palier le plus haut.

| Modèle | Poste (part sur GPU) | Tour (part sur GPU) | Chute |
|---|---|---|---|
| Ministral 3 8B | 10,9 tok/s (52 %) | 33,9 (84 %) | ×3,1 |
| Gemma 4 12B IQ3_XXS | 13,1 en vitesse seule (69 %) | 30,9 (100 %) | ×2,4 |
| Qwen 3.5 9B Q3_K_XL | 26,0 (76 %) | 34,9 (100 %) | ×1,3 |

- Le principe est documenté : chaque couche restée sur le CPU ralentit tout le pipeline. Les sources sont des guides d'utilisateurs, pas la documentation de llama.cpp : [dev.to](https://dev.to/pat9000/llamacpp-ngl-when-ngl-99-still-runs-on-your-cpu-46im), [bmdpat.com](https://bmdpat.com/blog/llama-cpp-n-gpu-layers-explained-2026).
- **Nuance à apporter à notre propre règle** : la chute varie de ×1,3 à ×3 selon la part déportée et l'architecture du modèle. Le « facteur 3 à 5 » retenu jusqu'ici n'est donc pas une loi générale.
- Aucune source n'a été trouvée pour ce seuil précis sur une carte de 6 Go, avec des modèles dont les fiches promettent de « tenir dans 6 à 8 Go ». Nos courbes de vitesse par palier de contexte (vitesse seule) sont une **donnée nouvelle**.

---

## 2. Qualité

Nos suites sont courtes : 14 questions de raisonnement et 8 consignes de suivi d'instructions. Seuls l'ordre des modèles et les grands écarts sont comparés aux benchmarks publiés, jamais les valeurs absolues.

| Modèle | Raisonnement standard (poste / tour / EliteBook) | Publié | Verdict |
|---|---|---|---|
| Granite 4.0 350M, Qwen 3.5 0.8B | 0,21 et 0,43, en bas du classement | Plus petites variantes de leur famille, en bas des classements (Artificial Analysis, blog Qwen) | **Cohérent** |
| LFM 2.5 2.6B | 1,00 / 1,00 / 0,93 | Environ 80 % sur GSM8K et IFEval pour LFM2 2.6B — [Liquid AI](https://www.liquid.ai/blog/introducing-lfm2-2-6b-redefining-efficiency-in-language-models) | **Cohérent** : avec 80 % de réussite, un sans-faute sur 14 questions n'a rien d'improbable |
| Bonsai 8B et 27B (1-bit) | 0,71 en standard, 0,73 et 1,00 en « au mieux » | GSM8K 88,2 pour le 8B, entraîné nativement en 1-bit — [PrismML](https://prismml.com/news/bonsai-8b) | **Cohérent** |
| Ling 3.0 Tiny | 0,86 / 0,93 en standard ; 1,00 / 0,95 en « au mieux » | GSM8K 94 % (éditeur), mais indice composite d'Artificial Analysis modeste — [Hugging Face](https://huggingface.co/inclusionAI/Ling-3.0-tiny) | **Cohérent** sur ce que nos questions mesurent (arithmétique et logique) |
| Gemma 4 12B IQ3_XXS, Ministral 3 14B IQ2_M | 1,00 contre 0,71 | Ministral 3 14B est meilleur que Gemma 12B en pleine précision, mais la qualité chute nettement sous 3 bits — [kaitchup](https://kaitchup.substack.com/p/choosing-a-gguf-model-k-quants-i), [tinyweights](https://tinyweights.dev/posts/gguf-quantization-levels-q4-q5-q8/) | **Cohérent** : l'ordre s'inverse à cause de l'IQ2_M, plus destructrice que l'IQ3_XXS |
| OLMo 3 7B | 0,57 / 0,71 | La variante Instruct est en bas de classement ; la variante Think est bien plus haut — [Artificial Analysis](https://artificialanalysis.ai/models/olmo-3-7b-instruct) | **Écart à expliquer** : vérifier quelle variante sert le tag Ollama `olmo-3:7b` |
| Qwen 3.5 de 0.8B à 9B | Scores croissants avec la taille | Même ordre que les publications de Qwen | **Cohérent** |

### Écarts entre machines à température 0

- En standard, le poste et la tour obtiennent **le même score de raisonnement pour 16 modèles sur 22**.
  - Cinq modèles diffèrent d'une question sur 14 (±0,07) : LFM 2.5 1.2B, Llama 3.2 3B, Ling 3.0 Tiny, Ministral 3 3B et Qwen 3.5 2B.
  - OLMo 3 7B diffère de deux questions.
- Pour Ling, l'écart persiste avec un gabarit identique sur les deux machines, ce qui écarte cette cause.
- Ce non-déterminisme entre GPU est documenté. Même avec des poids, un prompt, des versions logicielles et un décodage glouton identiques, les sorties divergent d'une architecture de GPU à l'autre. En cause : le choix des noyaux de multiplication de matrices et l'ordre des additions en virgule flottante. Voir [Cooper et al., arXiv 2609.25624, septembre 2026](https://arxiv.org/html/2609.25624) ✔ (divergence sur 31 à 100 % des problèmes entre A100, L40S et H100) et, sur le mécanisme, [Thinking Machines, 2025](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) ✔.
- Nos deux cartes sont de la même génération (Ampere), mais avec des puces et des nombres de cœurs différents. S'y ajoute un écart de version d'Ollama (0.34.2 contre 0.34.3).
- **Conséquence pratique** : sur nos suites courtes, un écart de ±0,07 entre machines est du bruit, pas une différence de qualité.

---

## 3. Modèles récents : ce que nos mesures apportent

| Modèle | Mesures publiées sur GPU grand public ou CPU de portable | Verdict |
|---|---|---|
| Ling 3.0 Tiny | Aucune. La prise en charge par llama.cpp date de l'été 2026. | **Donnée nouvelle.** Elle confirme la promesse de l'éditeur : 124 à 127 tok/s, et une empreinte presque inchangée entre 2K et 16K de contexte (+0,2 Go). |
| MiniCPM5 1B et 2B | Seulement du débit cumulé multi-requêtes sur DGX Spark | **Donnée nouvelle** pour une requête seule |
| LFM 2.5 1.2B et 2.6B | H100 et NPU mobile seulement | **Donnée nouvelle** |
| Gemma 4 E2B et E4B (QAT) | Rien sur GPU de 6 à 8 Go | **Donnée nouvelle** |
| Granite 4.2 3B et 8B | Rien sur GPU dédié | **Donnée nouvelle** |
| OLMo 3 7B | Rien | **Donnée nouvelle** |
| Bonsai 8B et 27B | 8B : chiffre de l'éditeur (voir 1.1) ; 27B : un seul site d'estimation, pour une RTX 3060 Ti | **Cohérent** pour le 8B ; **donnée nouvelle** pour le 27B sur 6 et 8 Go, et pour le 1-bit sur CPU |
| Ministral 3 | Seulement du matériel haut de gamme (RTX 5090, Jetson Thor) et l'API | **Donnée nouvelle** sur 6 et 8 Go |

---

## 4. Effets de mesure

| Effet observé | Ce qu'on en sait | Verdict |
|---|---|---|
| **Veille moderne** : écran éteint, le débit est divisé par 2 à 4, sans alerte | Microsoft documente que l'écran s'éteint si aucun thread ne demande `ES_DISPLAY_REQUIRED` ; `ES_SYSTEM_REQUIRED` n'empêche que la mise en veille — [Microsoft Learn](https://learn.microsoft.com/en-us/windows/win32/power/system-sleep-criteria) ✔. Aucune source ne chiffre l'effet sur un calcul en cours. | **Mécanisme connu, effet apparemment nouveau** |
| **Profils Armoury Crate** : bridage à 88 °C en Performance ; en Turbo, fréquence plafonnée mais meilleur débit | Principe connu (arbitrage entre puissance, température et fréquence), rien de chiffré pour ce modèle ou pour l'inférence | **Partiellement connu** |
| **Générations courtes** : 274 tok/s calculés sur 3 tokens pour un modèle qui en fait environ 230 | `llama-bench` génère 128 tokens, répète 5 fois et préchauffe par défaut — [README llama-bench](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md) ✔ | **Connu.** Notre seuil de 32 tokens va dans le même sens, en moins strict. |
| **Dispersion à 2 exécutions** : IC95 de ±20 à 40 % pour 5 % d'écart réel | Propriété statistique connue (coefficient de Student de 12,7 à n=2). La référence de fait, `llama-bench`, répète 5 fois. | **Connu** |
| **Débit bimodal en standard** (Qwen 3.5 4B, Ministral 3 3B, MiniCPM5 2B, sur le portable seulement) | NVIDIA documente Dynamic Boost, qui déplace de la puissance entre CPU et GPU selon la charge, sur secteur seulement — [README du pilote NVIDIA](https://download.nvidia.com/XFree86/Linux-x86_64/535.98/README/dynamicboost.html) ✔. Aucune source ne chiffre l'effet sur l'inférence. | **Mécanisme connu**, effet chiffré ici |

**Cause du débit bimodal** (tests du 26/09, poste au repos, sur secteur, en Turbo) :
- **Ce n'est pas l'échantillonnage.** La mesure de vitesse du protocole standard tourne à température 0,7, pas 0. En dehors de la campagne, température 0, température 0,7 et paramètres de l'éditeur, avec ou sans raisonnement, donnent tous 72 à 74,6 tok/s sur Qwen 3.5 4B (78 générations, 38 chargements).
- **C'est la limite de puissance du GPU.** Rejouée à l'identique, la campagne standard reproduit les deux régimes. Relevé `nvidia-smi` à 100 ms, les 18 générations mesurées se rangent sans exception :

  | Régime | Plafond de puissance | Fréquence SM au plafond | Qwen 3.5 4B | MiniCPM5 2B |
  |---|---|---|---|---|
  | Lent | 80 W | 1 200 à 1 280 MHz | 61 à 62 tok/s | 113 à 120 tok/s |
  | Rapide | 90 à 95 W | 1 480 à 1 600 MHz | 71 à 73 tok/s | 128 à 132 tok/s |

  Le motif de bridage est le même dans les deux cas (`0x4`, limite de puissance logicielle) : c'est le plafond qui change. 80 W correspondent vraisemblablement à la puissance de base du GPU, et les 15 W au-dessus à Dynamic Boost.
- **Le logiciel est hors de cause.** Entre un palier lent et un palier rapide, le serveur d'Ollama est lancé avec les mêmes arguments, les mêmes paramètres d'échantillonnage et le même placement mémoire, et réutilise autant de graphes CUDA. Son propre chronométrage donne 61,05 contre 70,83 tok/s. Le test (c) avec `llama-bench` n'apporterait rien de plus : il tournerait sous le même plafond.
- **Le relevé du benchmark ne pouvait pas le voir.** `gpu_clock_mhz` est lu après la génération, sur un GPU déjà revenu au repos à 2,1 GHz. D'où la mention erronée de « fréquences hautes et stables » dans les résultats de la campagne.

Reste ouvert : ce qui fait tomber le plafond à 80 W. Une charge sur 8 cœurs CPU ne l'abaisse qu'à 90 W (−3 % de débit). Les mesures isolées restent à 95 W. Seul l'enchaînement de la campagne standard (tests fonctionnels, recherche d'aiguille, rechargements du modèle toutes les dix secondes environ) le fait descendre à 80 W.

Depuis, `benchmark_slm.py` relève la puissance et la fréquence pendant chaque génération (`gpu_power_plateau_w`, `gpu_sm_clock_gen_mhz`). Il avertit quand le plafond varie de plus de 5 W entre les générations d'un même modèle.

---

## 5. Suites recommandées

- **Répétitions** : passer à 3 exécutions en standard, ou publier la médiane, pour que les intervalles de vitesse deviennent exploitables. `llama-bench` en fait 5.
- **Versions** : aligner la version d'Ollama sur les trois machines, pour réduire les écarts de qualité à température 0.
- **Débit bimodal** : cause identifiée (§4). Deux options, à trancher : désactiver Dynamic Boost pendant les campagnes, pour un débit stable mais plus bas, ou remesurer les modèles signalés par le nouvel avertissement. Le réglage existe dans le panneau de configuration NVIDIA d'après la [page d'aide NVIDIA](https://nvidia.custhelp.com/app/answers/detail/a_id/5087/~/how-to-enable-or-disable-dynamic-boost-in-the-nvidia-control-panel) (non relue : accès refusé) ; sa présence sur ce portable reste à vérifier.
- **OLMo 3 7B** : vérifier la variante servie par `olmo-3:7b`.
- **Diffusion** : publier les mesures signalées comme données nouvelles, qui n'ont pas d'équivalent public connu. Il s'agit de Ling 3.0 Tiny, MiniCPM5, LFM 2.5, Gemma 4 E2B et E4B, Granite 4.2, du 1-bit sur CPU, et des courbes de débordement sur 6 Go.

---

## Sources

Relues le 26/09 (✔) :
- localscore.ai, [RTX 3060 Laptop 6 Go](https://www.localscore.ai/accelerator/767) et [RTX 3050 6 Go](https://www.localscore.ai/accelerator/977)
- [tyolab, « 64 GB RAM, 12 GB VRAM: the honest local LLM benchmark », mai 2026](https://www.tyolab.com/blog/2026/05/11-64gb-ram-12gb-vram-the-honest-local-llm-benchmark/)
- [Firethering, Bonsai 8B (chiffres PrismML)](https://firethering.com/bonsai-8b-1bit-llm/)
- [README de llama-bench](https://github.com/ggml-org/llama.cpp/blob/master/tools/llama-bench/README.md)
- [Microsoft Learn, System Sleep Criteria](https://learn.microsoft.com/en-us/windows/win32/power/system-sleep-criteria)
- [NVIDIA, README du pilote Linux 535.98, « Dynamic Boost on Linux »](https://download.nvidia.com/XFree86/Linux-x86_64/535.98/README/dynamicboost.html)
- [Cooper et al., « Accelerating the Mitigation of LLM Inference Nondeterminism Across GPU Architectures », arXiv 2609.25624, septembre 2026](https://arxiv.org/html/2609.25624)
- [Thinking Machines, « Defeating Nondeterminism in LLM Inference », septembre 2025](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)
- Mesure locale : `nvidia-smi -q -d CLOCK` sur le poste (fréquence mémoire maximale de 7001 MHz)

Rapportées par les agents de recherche, non relues :
- [Liquid AI, LFM2 2.6B](https://www.liquid.ai/blog/introducing-lfm2-2-6b-redefining-efficiency-in-language-models)
- [PrismML, Bonsai 8B](https://prismml.com/news/bonsai-8b)
- [inclusionAI, Ling 3.0 Tiny](https://huggingface.co/inclusionAI/Ling-3.0-tiny)
- [Artificial Analysis, OLMo 3 7B Instruct](https://artificialanalysis.ai/models/olmo-3-7b-instruct)
- [kaitchup, K-quants et I-quants](https://kaitchup.substack.com/p/choosing-a-gguf-model-k-quants-i)
- [tinyweights, niveaux de quantification GGUF](https://tinyweights.dev/posts/gguf-quantization-levels-q4-q5-q8/)
- [dev.to, -ngl et CPU](https://dev.to/pat9000/llamacpp-ngl-when-ngl-99-still-runs-on-your-cpu-46im)
- [bmdpat.com, --n-gpu-layers](https://bmdpat.com/blog/llama-cpp-n-gpu-layers-explained-2026)
- [NVIDIA, Mistral 3](https://developer.nvidia.com/blog/nvidia-accelerated-mistral-3-open-models-deliver-efficiency-accuracy-at-any-scale/)
- [Intel ARK, i5-1145G7](https://www.intel.com/content/www/us/en/products/sku/208660/intel-core-i51145g7-processor-8m-cache-up-to-4-40-ghz-with-ipu/specifications.html)
- [gpuspecs, RTX 3050 8 Go](https://gpuspecs.com/card/nvidia-geforce-rtx-3050-8gb)

Écartées faute de fiabilité (blogs agrégateurs sans configuration publiée) : markaicode.com, buildfastwithai.com, willitrunai.com.
