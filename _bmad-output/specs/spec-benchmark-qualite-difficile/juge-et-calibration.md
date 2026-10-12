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
- **Prix :** relevés le 2026-10-10 sur des agrégateurs, revérifiés le 2026-10-12 (story 7) et consignés avec leur source et leur date dans `scripts/quality_bench/judges.yaml` :
  - Haiku 5.5 : 0,10 $ / 0,50 $ par M de tokens jusqu'à 100 000 tokens d'entrée par requête, 0,50 $ / 2,50 $ au-delà, −50 % en lot (page officielle https://platform.claude.com/docs/en/about-claude/pricing, lue le 2026-10-12) ;
  - MiMo-V2.6-Pro : 0,435 $ / 0,87 $, lecture en cache 0,0036 $ (blog LiteLLM « Day 0 Support: Xiaomi MiMo V2.6 » et agrégateurs, lus le 2026-10-12 ; page officielle de Xiaomi non atteinte ; le banc compte toute l'entrée au prix plein, donc par excès) ;
  - Perplexity Decider v1.1 (`pplx-decider-v1.1-27b`) : 0,02 $ par M en entrée, sortie gratuite (OpenRouter, llmreference.com, relevés le 2026-10-07 et non revérifiés : point d'accès encore inconnu).
- **Cascade :** ce n'est pas un juge lancé. Elle se simule hors ligne depuis les jugements de Winnow et de Haiku pour régler ses seuils ; si elle est retenue, elle devient une entrée de `judges.yaml`.
- **Winnow-E4B :**
  - dépôt `EldanRing/Winnow-E4B` (Apache-2.0, publié le 2026-09-24) ;
  - seuls les GGUF Q8_0 (8,01 Go) et BF16 sont publiés, pour un pic de 8,56 Gio en texte 8K : au-delà des 8 Go de la RTX 3050, un déport partiel en CPU est à vérifier ;
  - il est interrogé par le contrat `POST /v1/systemone` (question `noul`, probabilité de vrai, verdict à ≥ 0,5), pas par un serveur précis ;
  - il tourne seulement pendant la phase de jugement, jamais pendant la génération (8 Go de VRAM) ;
  - sa tenue en français n'a pas pu être mesurée à la story 7 (voir « Mesures sur la tour ») : procédure manuelle ci-dessous, puis calibration (story 9).
- **Serveur du juge local :** trois options étaient ouvertes :
  - WSL2 avec CUDA et `winnow-inference`, validé seulement sous Linux/CUDA et macOS, qui demande au moins 10 Go de VRAM en texte 8K ;
  - Winnow-E4B importé dans Ollama 0.40.2 comme modèle `decision`, Ollama servant `/v1/systemone` ;
  - Perplexity Decider hébergé.
- **Décision (Anaël, story 7, 2026-10-12) :** Winnow-E4B importé dans Ollama 0.40.2 comme modèle à capacité `decision`, sous l'étiquette `winnow-e4b`, Ollama servant `/v1/systemone` sur `127.0.0.1:11434` (entrée `winnow` de `judges.yaml`). Le préflight de la génération exclut déjà tout modèle `decision` (AD-9) : Winnow ne sert qu'à la phase de jugement. Decider hébergé reste le repli (entrée `decider`, `endpoint: null` tant que son point d'accès n'est pas relevé : le lancement est refusé).
- **Mesures sur la tour : non faites.** Pendant la story 7, les permissions de la session ont refusé tout accès au dépôt `EldanRing/Winnow-E4B` (téléchargement, lecture) et toute sonde de `/v1/systemone` sur Ollama ; l'orchestrateur a donc interdit le téléchargement, l'import dans Ollama et l'appel réel. Le juge est écrit et testé contre le **contrat** (faux serveur) ; restent à mesurer : déport en CPU du Q8_0 (8,01 Go sur 8 Go de VRAM), durée par requête, conformité du contrat réel, tenue en français.
- **Procédure manuelle (à faire à la main avant la calibration, hors campagne, `machine.lock` libre ; non exécutée à la story 7) :**
  1. télécharger à la main le GGUF Q8_0 de `EldanRing/Winnow-E4B` à une révision épinglée, comparer son `sha256` à `SHA256SUMS` du dépôt et le reporter dans `weights_sha256` de l'entrée `winnow` ;
  2. l'importer : `Modelfile` réduit à `FROM <chemin du GGUF>`, puis `ollama create winnow-e4b -f Modelfile` ;
  3. `ollama show winnow-e4b` : la capacité `decision` doit figurer ; sinon l'option tombe et le repli Decider s'applique ;
  4. Ollama sans autre modèle chargé (`ollama ps` vide), envoyer une requête d'essai à `POST http://127.0.0.1:11434/v1/systemone` (deux questions `noul`) et comparer la réponse au contrat de `scripts/quality_bench/judge/systemone.py` (chemin, enveloppe `{model, answers, usage}`, `id` rendu ou non) ; tout écart se corrige dans `systemone.py` et ses tests ;
  5. mesurer : `ollama ps` (`size`, `size_vram` : part déportée en CPU), `nvidia-smi` (pic de VRAM), durée de 10 requêtes sur des réponses de rédaction du pilote ;
  6. lancer `python -m scripts.quality_bench judge --campaign <pilote> --judge winnow`, puis relire `judgment-winnow/` ; la tenue en français se mesure à la calibration (story 9) ;
  7. décharger Winnow (`keep_alive: 0`, fait par `judge` en fin de lancement ; sinon `curl http://127.0.0.1:11434/api/generate -d '{"model": "winnow-e4b", "keep_alive": 0}'`) et vérifier `ollama ps` vide : le GPU doit être libre avant toute génération ;
  8. consigner les mesures ici et la version servie dans `server_version`.
- **Repli si Winnow est inutilisable :** Perplexity Decider v1.1 hébergé (poids Apache-2.0, ~0,02 à 0,04 $/M en entrée). Sa base Qwen3.8-27B impose de mesurer le biais Qwen.
- **Haiku 5.5** (`claude-haiku-5-5`) :
  - SDK `anthropic`, Message Batches, verdict par sortie structurée ;
  - la température n'est pas réglable : l'API refuse toute valeur non par défaut de `temperature`, `top_p` ou `top_k`, et le modèle réfléchit par défaut ;
  - l'effort et le réglage de réflexion sont consignés dans le manifeste du jugement ;
  - la stabilité du verdict est mesurée par rejeu à la calibration.
- **MiMo-V2.6-Pro** (`mimo-v2.6-pro`) : SDK `openai` sur `https://api.xiaomimimo.com/v1`.
- **Clés d'API :** lues dans `os.environ` (`ANTHROPIC_API_KEY`, `MIMO_API_KEY`, `PERPLEXITY_API_KEY`), que `disable_telemetry()`, appelé en tête de la CLI, complète depuis le `.env` de la racine (ignoré par git) sans écraser l'environnement ; jamais dans un fichier versionné ni dans un journal.
- **Commande (story 7) :** `python -m scripts.quality_bench judge --campaign <c> --judge <id> [--max-cost-usd X]`, plafond obligatoire pour un juge cloud. Réglages retenus pour Haiku : `effort: low`, `thinking: {type: adaptive}`, `max_tokens: 2048` ; pour MiMo : `max_tokens: 2048`, réflexion non envoyée (valeur par défaut du service).
- **Essai réel des juges cloud (story 7, 2026-10-12) :** campagne jetable `trial-judge-20261012` sous `data/quality_bench/campaigns/` (non versionnée), 2 questions publiques de `writing-fr.yaml` (`writing/writing-fr/0001`, réclamation ; `0002`, relance fournisseur), une bonne et une mauvaise réponse synthétique chacune, soit 20 critères par juge, `--max-cost-usd 0.25`.
  - **Haiku 5.5** (un lot de 20 requêtes, terminé en 3 min) : 20 verdicts, 0 erreur ; 19 205 tokens d'entrée, 200 de sortie (aucune réflexion visible à `effort: low`) ; **0,0010 $** (estimation préalable 0,0110 $).
  - **MiMo-V2.6-Pro** (20 appels en 2 min) : 20 verdicts, 0 erreur ; environ 500 tokens d'entrée et 11 à 602 de sortie (réflexion) par critère ; **0,0060 $**.
  - **Accord :** les deux juges rendent les mêmes 20 verdicts, tous conformes à l'attendu : bonnes réponses vraies sur les 10 critères ; mauvaises réponses fausses sur 9 critères sur 10, la seule exception (`0002`, c2, corps de moins de 120 mots) étant vraie à juste titre.
  - Paramètres acceptés tels quels par les API : lot Haiku avec `output_config.format` (json_schema) + `thinking: adaptive` + `effort: low` ; MiMo avec `max_completion_tokens`, sans `thinking` envoyé, verdict JSON lu dans le contenu.
  - Dépense totale de l'essai : 0,0070 $.
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
- **Commande (story 9) :** `python -m scripts.quality_bench calibrate-sample --campaign <c> [--size 100] [--seed S]` tire l'échantillon à étiqueter (`calibration/labels-todo-<c>.{jsonl,md}`, moitié Qwen, un critère par réponse tant que possible) ; `python -m scripts.quality_bench calibrate --campaign <c> [--min-agreement X] [--max-qwen-bias Y] [--cascade-margins …] [--projected-judgments N]` écrit `campaigns/<c>/calibration-report.{md,json}`. Les deux sont en lecture seule, sans réseau ni verrou, et n'écrivent que hors dépôt. Étiquettes `qb.label/1` dans `calibration/labels.jsonl`, multi-campagnes : `labels-todo-<c>.jsonl` rempli y est ajouté à la fin, jamais en remplacement (`label` : `true`, `false`, `"undecidable"` ou `null`, avec `author` et `labeled_at` dès qu'elle est posée). Sans les deux seuils, le rapport dit « seuil non fixé » et ne recommande rien ; avec, il propose une configuration sans jamais l'appliquer. Le rejeu de stabilité d'un juge cloud passe par un identifiant distinct `<id>-replay` (entrée `haiku-replay` de `judges.yaml`). Détail des mesures et des codes : `scripts/quality_bench/questions/SOURCES.md`, section « Calibration du juge ».
- **Décision :** le juge retenu est consigné avant la campagne, désigné dans la configuration de campagne et figé dans le manifeste du jugement. Le seuil d'accord minimal et le biais Qwen maximal toléré restent à définir par l'utilisateur, au plus tard à la calibration.
