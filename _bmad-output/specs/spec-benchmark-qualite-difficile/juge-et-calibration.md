# Juge et calibration

Interface, lignes de jugement et lots : AD-16 du spine d'architecture.

## Critères

Chaque critère de rédaction est formulé en **question fermée** (oui ou non), pour être jugé critère par critère, avec une ligne de `judgment.jsonl` par critère.

Les questions de rédaction ne sont **pas privées** : le juge doit voir la consigne, et une tâche ouverte notée sur critères craint peu la contamination. Aucune question privée ne quitte la machine.

## Configurations comparées

| Configuration | Principe | Coût estimé de la campagne |
|---|---|---|
| Winnow-E4B seul | modèle de décision ouvert (Gemma 4 E4B, Apache-2.0), qui renvoie une probabilité par question fermée, en local | nul |
| Winnow-E4B en cascade | Winnow accepte quand il est confiant, sinon il escalade vers Haiku 5.5 | < 2 $ |
| MiMo-V2.6-Pro | juge LLM cloud (0,435 $ / 0,87 $ par M de tokens) | ~10 $ |
| Claude Haiku 5.5 | juge LLM cloud en batch (0,10 $ / 0,50 $ par M de tokens, −50 % en batch, tokenizer +30 %) | ~2 $ |

- **Volume :** environ 11 000 jugements, soit (80 × 20 + 40 × 15) réponses × ~5 critères. Le prix ne départage pas les configurations : c'est l'accord avec les étiquettes qui décide.
- **Prix :** relevés le 2026-10-10 sur des agrégateurs. Les revérifier avant l'implémentation.
- **Cascade :** ce n'est pas un juge lancé. Elle se simule hors ligne depuis les jugements de Winnow et de Haiku pour régler ses seuils ; si elle est retenue, elle devient une entrée de `judges.yaml`.
- **Winnow-E4B :**
  - dépôt `EldanRing/Winnow-E4B` (Apache-2.0, publié le 2026-09-24) ;
  - seuls les GGUF Q8_0 (8,01 Go) et BF16 sont publiés, pour un pic de 8,56 Gio en texte 8K : au-delà des 8 Go de la RTX 3050, un déport partiel en CPU est à vérifier ;
  - il est interrogé par le contrat `POST /v1/systemone` (question `noul`, probabilité de vrai, verdict à ≥ 0,5), pas par un serveur précis ;
  - il tourne seulement pendant la phase de jugement, jamais pendant la génération (8 Go de VRAM) ;
  - sa tenue en français est à vérifier à la story 7.
- **Serveur du juge local :** à trancher au début de la story 7, par mesure sur la tour, entre trois options :
  - WSL2 avec CUDA et `winnow-inference`, validé seulement sous Linux/CUDA et macOS, qui demande au moins 10 Go de VRAM en texte 8K ;
  - Winnow-E4B importé dans Ollama 0.40.2 comme modèle `decision`, Ollama servant `/v1/systemone` ;
  - Perplexity Decider hébergé.
- **Repli si Winnow est inutilisable :** Perplexity Decider v1.1 hébergé (poids Apache-2.0, ~0,02 à 0,04 $/M en entrée). Sa base Qwen3.8-27B impose de mesurer le biais Qwen.
- **Haiku 5.5** (`claude-haiku-5-5`) :
  - SDK `anthropic`, Message Batches, verdict par sortie structurée ;
  - la température n'est pas réglable : l'API refuse toute valeur non par défaut de `temperature`, `top_p` ou `top_k`, et le modèle réfléchit par défaut ;
  - l'effort et le réglage de réflexion sont consignés dans le manifeste du jugement ;
  - la stabilité du verdict est mesurée par rejeu à la calibration.
- **MiMo-V2.6-Pro** (`mimo-v2.6-pro`) : SDK `openai` sur `https://api.xiaomimimo.com/v1`.
- **Clés d'API :** par l'environnement (`ANTHROPIC_API_KEY`, `MIMO_API_KEY`), jamais dans un fichier.
- **Écartés :**
  - Jev (TypeSafe) : propriétaire, prix non publié ;
  - JevK5 4B : anglais seul ;
  - Perplexity Decider en local : ~49 Gio, sans GGUF.

## Calibration

- **Référence :** environ 100 étiquettes humaines, produites par Anaël sur des réponses de rédaction du pilote, critère par critère. Une étiquette porte la même clé qu'un jugement.
- **Mesures par configuration :**
  - accord avec les étiquettes ;
  - coût ;
  - pour la cascade, part des jugements escaladés ;
  - écart d'accord entre réponses de candidats Qwen et de non-Qwen (biais Qwen, selon la famille déclarée par modèle) ;
  - pour un juge cloud, stabilité du verdict par rejeu.
- **Décision :** le juge retenu est consigné avant la campagne, désigné dans la configuration de campagne et figé dans le manifeste du jugement. Le seuil d'accord minimal et le biais Qwen maximal toléré restent à définir par l'utilisateur, au plus tard à la calibration.
