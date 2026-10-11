# Modèles

Le périmètre est tiré des mesures de l'ancien banc sur tour-rtx3050 (`benchmarks/results/tour-rtx3050-a2b6baf5.json`) et des capacités déclarées dans `config/models_catalog.json`. La capacité thinking réelle se relit dans `/api/show` au lancement.

## Les 20 modèles de la campagne

Ils sont classés par débit de génération.

| Modèle | Tag Ollama | tok/s | Thinking | Raisonnement | Consignes | Outils | Rôle |
|---|---|---|---|---|---|---|---|
| LFM 2.5 1.2B Thinking | `lfm2.5-thinking:1.2b` | 230 | oui | 9/14 | 6/8 | 4/4 | |
| Ling 3.0 Tiny | `ling3-tiny:8b-q4_k_m` | 130 | oui | 13/14 | 7/8 | 4/4 | pilote |
| MiniCPM5 2B | `minicpm5:2b-q4_k_m` | 111 | oui | 9/14 | 7/8 | 4/4 | |
| LFM 2.5 2.6B | `LiquidAI/lfm2.5-2.6b` | 103 | oui | 14/14 | 7/8 | 4/4 | pilote |
| Gemma 4 E2B (QAT) | `gemma4:e2b-it-qat` | 103 | oui | 12/14 | 8/8 | 4/4 | pilote |
| Bonsai 8B (1-bit) | `bonsai:8b-q1_0` | 85 | non | 10/14 | 7/8 | 4/4 | |
| Qwen 3.5 2B | `qwen3.5:2b` | 83 | oui | 9/14 | 7/8 | 4/4 | |
| Ministral 3 3B | `ministral-3:3b` | 76 | non | 10/14 | 7/8 | 4/4 | |
| Granite 4.2 3B | `granite4.2:3b` | 75 | oui | 9/14 | 7/8 | 4/4 | |
| Phi 4 Mini 3.8B | `phi4-mini:3.8b` | 68 | non | 9/14 | 7/8 | 2/4 | |
| Nemotron 3 Nano 4B | `nemotron-3-nano:4b` | 65 | oui | 11/14 | 7/8 | 4/4 | |
| Qwen 3.5 4B | `qwen3.5:4b` | 59 | oui | 12/14 | 7/8 | 4/4 | pilote |
| Gemma 4 E4B (QAT) | `gemma4:e4b-it-qat` | 57 | oui | 12/14 | 7/8 | 4/4 | |
| Qwen 3.5 9B | `qwen3.5:9b` | 35 | oui | 13/14 | 7/8 | 4/4 | |
| Qwen 3.6 35B-A3B (MoE) | `qwen3.6:35b-a3b` | 32 | oui | 13/14 | 7/8 | 2/4 | |
| Granite 4.2 8B | `granite4.2:8b` | 31 | oui | 10/14 | 7/8 | 4/4 | |
| Gemma 4 12B (Unsloth IQ3_XXS) | `gemma4-ud:12b-iq3_xxs` | 31 | oui | 14/14 | 7/8 | 4/4 | |
| Ministral 3 8B | `ministral-3:8b` | 29 | non | 13/14 | 7/8 | 4/4 | |
| Bonsai 27B (1-bit) | `bonsai:27b-q1_0` | 27 | oui | 10/14 | 7/8 | 4/4 | |
| Ministral 3 14B (Unsloth IQ2_M) | `ministral3-ud:14b-iq2_m` | 27 | non | 10/14 | 7/8 | 3/4 | |

15 modèles passent les deux pistes, et 5 seulement la piste coupée.

Le compte est de 20, et non de 19 : `qwen3.6:35b-a3b`, d'abord écarté pour la RAM, tourne finalement sur la tour (pic à 27,5 Go).

## Exclus

| Modèle | Raison |
|---|---|
| `granite4:350m` | faible : raisonnement 3/14, consignes 3/8 |
| `minicpm5:1b-q4_k_m` | faible : raisonnement 5/14 |
| `gemma3:1b` | faible : raisonnement 6/14, outils 0/4 |
| `qwen3.5:0.8b` | faible : raisonnement 6/14 |
| `llama3.2:3b` | faible : raisonnement 8/14 (p = 0,016) |
| `olmo-3:7b` | faible : outils 0/4, aiguille 0/3 |
| `ling3-tiny:8b-iq4_xs` | doublon plus lent que `q4_k_m` (118 contre 130 tok/s) |
| `qwen3.5-ud:9b-q3_k_xl` | doublon plus lent que `qwen3.5:9b` (34,8 contre 35,2 tok/s) |
| `gemma4:12b` (Q4_K_M), `saluki:27b-iq2_mix` | supprimés de la tour, à ne pas réinstaller (trop lents) |

**Critère « faible » :** sur l'ancien banc, le modèle est nettement sous le meilleur sur au moins un usage (Fisher exact, p < 0,02), ou obtient 0 sur un usage. Les cinq modèles à 9/14 en raisonnement (p = 0,041) sont gardés : cet écart reste dans le bruit des tests multiples.

## Pilote

Quatre modèles, tous capables de raisonnement :
- **Ling 3.0 Tiny**, **LFM 2.5 2.6B** et **Gemma 4 E2B** forment le front de Pareto précision/vitesse de l'ancien banc.
- **Qwen 3.5 4B** est le meilleur rapport parmi les Qwen. Il en faut un pour mesurer le biais Qwen du juge sur les réponses du pilote.

La projection de durée extrapole aux modèles lents : tokens mesurés au pilote, divisés par le débit de chaque modèle.
