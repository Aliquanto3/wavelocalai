# Audit 02 : architecture back et librairies

Date : 2026-10-18. Base : `master` à `5b5e2d1`. Périmètre : `src/core/`, dépendances, stabilité, cible v2.
Les deux autres audits couvrent la performance mesurée et l'UX/front.

Méthode :
- lecture de `src/core/` (38 modules, environ 8 000 lignes) et des appels depuis `src/app/` ;
- tailles mesurées avec `du -sm` dans `.venv\Lib\site-packages` (Python 3.12.14) ;
- versions installées lues avec `importlib.metadata` ; versions récentes lues sur PyPI le 2026-10-18 ;
- suite `tests/unit` lancée avec couverture de `src/core` ;
- essais ciblés : imports, `crewai.LLM` pour Ollama et Mistral, API Ollama locale (0.40.5).

## Synthèse

| Sujet | Constat | Gravité |
|---|---|---|
| Poids | `.venv` de 2 161 Mo, 290 paquets installés, 331 entrées dans `uv.lock`. torch seul pèse 509 Mo, pour un seul modèle d'embedding de 90 Mo | majeur |
| Dépendances inutiles | `docling`, `einops`, `timeout_decorator`, `GPUtil` (doublon de `nvidia-ml-py`) : aucun import. `docling` tire OpenCV, RapidOCR et docling-parse (environ 180 Mo) | majeur |
| Panne constatée | Mode Crew avec un modèle Mistral cloud : `crewai` 1.15 refuse `mistral/…` sans LiteLLM (`crew_engine.py:124-126`) | majeur |
| Librairies fragiles | Ragas sans version depuis janvier 2026, imports dépréciés ; `create_react_agent` déprécié depuis LangGraph 1.0 ; CrewAI change d'API majeure entre machines (0.193 contre 1.15) | majeur |
| CO₂ par réponse | Le CO₂ local est une constante de 0,19 mg par token, quel que soit le modèle (`green_monitor.py:47`, `answer_carbon.py:57`). La formule cloud recopie EcoLogits à la main (`green_monitor.py:33-42`) | majeur (vérité affichée) |
| Code mort | `rate_limiter.py`, `session/`, `exporters/`, `repositories/` : 1 233 lignes, appelées par les seuls tests | moyen |
| Identité des modèles | Savoir si un tag est local, cloud ou Groq est réparti dans 5 fonctions de 5 modules | moyen |
| Async | Du code async appelé par `asyncio.run` depuis Streamlit, plus `nest_asyncio` ; un client Ollama créé à chaque appel | moyen |
| Tests | 817 tests passent en 187 s, couverture de `src/core` 81,65 %. Ils simulent surtout LangChain : une grande part sera à réécrire | info |

Recommandation d'ensemble : la v2 garde la logique métier utile de `src/core/` (règles de choix des modèles, métriques, outils, sécurité des chemins). Elle remplace LangChain, LangGraph, CrewAI, Chroma, sentence-transformers et Ragas par des appels directs aux SDK et quelques modules maison. Gain attendu : environ 1,8 Go en moins et 4 librairies instables en moins, sans perdre de fonctionnalité visible.

## 1. Cartographie de `src/core/`

### 1.1 Modules et responsabilités

Colonnes « app » et « tests » : nombre de fichiers qui importent le module.

| Module | Lignes | Rôle | app | tests | Statut |
|---|---|---|---|---|---|
| `config.py` | 36 | Chemins, `.env`, clé Mistral, pays CodeCarbon | 1 | 9 | Effets de bord à l'import (`load_dotenv`, `mkdir`, l. 7, 21-22). Importé par le banc |
| `telemetry.py` | 55 | Coupe les télémétries de Chroma, CrewAI, Ragas, HF | 1 | 3 | Utile tant que ces libs restent |
| `models_db.py` | 151 | Lit `data/models.json` une fois, à l'import (l. 26) | 7 | 9 | Pas de rechargement ; `basicConfig` à l'import (l. 9) |
| `model_detector.py` | 104 | Tag → fiche, local ou API | 1 | 1 | Doublon partiel de `models_db` et `provider_factory` |
| `model_defaults.py` | 646 | Catalogue `config/models_catalog.json`, choix par défaut des modèles selon la RAM | 8 | 6 | Bon, couvert à 99 %. À réutiliser |
| `model_profiles.py` | 99 | RAM d'une mission Crew | 1 | 0 | Doublon de l'estimation de `resource_manager` |
| `benchmark_results.py` | 199 | Lit `benchmarks/results/*.json` (scores du banc) | 1 | 5 | Contrat de données avec le banc. À réutiliser |
| `utils.py` | 49 | `extract_params_billions` | 2 | 0 | À réutiliser |
| `interfaces/__init__.py` | 112 | `ILLMProvider` (ABC) | 0 | 0 | Impose `get_langchain_model` à chaque fournisseur (l. 71) |
| `providers/*.py` | 1 253 | Ollama, Mistral, OpenAI, Anthropic, Groq : streaming et version LangChain | 2 | 5 | Cœur utile, couplé à LangChain |
| `providers/provider_factory.py` | 249 | Routage tag → fournisseur, singleton | 2 | 5 | Singleton sans verrou (l. 76-83) |
| `llm_provider.py` | 232 | Façade statique sur la fabrique | 11 | 14 | Dit « conservé pour rétrocompatibilité » (l. 28-31) mais c'est le point d'entrée réel de l'app |
| `metrics.py` | 154 | `InferenceMetrics`, calcul des débits depuis les durées Ollama | 3 | 10 | Bon. À réutiliser |
| `inference_service.py` | 367 | Boucle de streaming, interruption, reprise | 5 | 8 | Logique à reprendre ; bloc de démo `__main__` (l. 367) |
| `metrics_service.py` | 257 | Mise en forme et CO₂ pour un composant | 1 | 1 | Doublon de `answer_carbon.py` (l. 71-135) |
| `answer_carbon.py` | 61 | CO₂ d'une réponse, règle unique annoncée | 6 | 3 | Règle à corriger (voir §4.4) |
| `green_monitor.py` | 333 | Formules CO₂, matériel temps réel, `GreenTracker` CodeCarbon, historique | 3 | 10 | À scinder |
| `accelerator.py` | 97 | Détection GPU (NVML) | 1 | 3 | À réutiliser |
| `resource_manager.py` | 175 | RAM disponible, garde-fou, déchargement Ollama | 2 | 4 | Couvert à 49 % |
| `agent_tools.py` | 955 | 10 outils (calcul, CSV, docx, graphique, email, moniteur…) | 2 | 8 | Les `_impl` sont indépendants de LangChain : à réutiliser |
| `agent_engine.py` | 340 | Agent ReAct LangGraph | 1 | 4 | `create_react_agent` déprécié (l. 17, 123) ; fonctions de debug mortes (l. 284-314) |
| `crew_engine.py` | 239 | Multi-agents CrewAI | 1 | 2 | Route Mistral cassée ; hôte Ollama codé en dur (l. 130) |
| `rag_engine.py` | 133 | Façade RAG | 1 | 11 | Instancié par session Streamlit |
| `rag/ingestion.py` | 116 | Chargeurs LangChain, découpe 800/100 | 0 | 3 | `_validate_path` (l. 37-60) à réutiliser |
| `rag/models_factory.py` | 105 | Embeddings HF et reranker CrossEncoder | 0 | 6 | Tire torch |
| `rag/vector_store.py` | 65 | Chroma, une collection par embedding | 0 | 6 | `clear` avale les erreurs (l. 60-65) |
| `rag/strategies/*.py` | 379 | Naïve, HyDE, Self-RAG (graphe LangGraph) | 1 | 2 | `asyncio.run` dans du code sync (hyde l. 58, self_rag l. 197) |
| `eval_engine.py` | 179 | Ragas : fidélité et pertinence | 2 | 7 | Deux métriques seulement |
| `rate_limiter.py` | 205 | Limiteur de débit | 0 | 0 | Mort (0 % de couverture) |
| `session/session_manager.py` | 303 | Sessions avec verrou | 0 | 1 | Mort |
| `exporters/metrics_exporter.py` | 267 | Export de métriques | 0 | 3 | Mort |
| `repositories/benchmark_repository.py` | 458 | SQLite de benchmarks | 0 | 3 | Mort |

### 1.2 Dépendances internes

```
config ← models_db ← model_detector ← provider_factory ← llm_provider ← (app, agent, crew, eval, rag/strategies)
                   ← model_defaults ← provider_factory
                   ← answer_carbon, metrics_service, resource_manager
providers/* → interfaces → metrics          (et chacun → langchain_<fournisseur>)
agent_engine → agent_tools, llm_provider, langgraph, langchain_ollama, langchain_mistralai
crew_engine  → agent_tools, crewai, providers (clés API lues dans les modules fournisseurs)
rag_engine   → rag/{ingestion, models_factory, vector_store, strategies}
eval_engine  → llm_provider, ragas, datasets
green_monitor → codecarbon, config ; answer_carbon → green_monitor, models_db
```

Pas de cycle d'import. Mais `provider_factory` dépend de `model_defaults` (646 lignes) pour une seule fonction, `is_remote_tag`.

### 1.3 Doublons

| Sujet | Emplacements | Effet |
|---|---|---|
| Tag local ou cloud | `models_db.get_model_info` (l. 78, par nom), `model_detector.get_model_info` (l. 15, par tag), `model_defaults.is_remote_tag` (l. 314), `provider_factory.prefixed_cloud_provider` et `is_cloud_tag` (l. 24, 41), `groq_provider.is_groq_model` | Règles qui divergent : `model_detector.is_api_model` classe tout tag inconnu en local (l. 55-57), `is_cloud_tag` renvoie `None` |
| CO₂ d'une réponse | `answer_carbon.answer_carbon_mg` et `metrics_service.calculate_carbon` | Deux chemins pour une règle « unique » |
| Estimation RAM | `resource_manager.estimate_model_ram`, `model_profiles.estimate_mission_ram_gb`, `model_defaults` (`SYSTEM_RAM_BUFFER_GB`) | Trois estimations |
| Construction d'un LLM | `providers/*.get_langchain_model`, `agent_engine._initialize_mistral_api` (l. 140-177), `crew_engine._get_native_llm` (l. 80-131) | Trois routages tag → fournisseur ; le Crew n'a pas suivi |
| `llm_provider.py` contre `provider_factory.py` | La façade n'apporte que des `try/except` et des aides Ollama | À fondre en un service unique en v2, pas à supprimer seule en v1 |

### 1.4 Couplages app ↔ core

- L'état vit dans `st.session_state` : `RAGEngine` créé par session (`views/03_RAG_Knowledge.py:97-110`), donc un jeu de modèles d'embedding par onglet de navigateur.
- L'app lance l'async : `asyncio.run` dans `tabs/inference/arena.py:488, 615`, `chat.py:209`, `lab.py:199`, `tabs/rag/chat.py:243`, `tabs/rag/eval.py:336`, plus `nest_asyncio.apply()` (`views/03_RAG_Knowledge.py:57`, `views/04_Agent_Lab.py:16`).
- De la logique métier est restée dans l'app : suivi RAM du Crew par un thread (`tabs/agent/crew.py:494-517`), boucle d'évaluation (`tabs/rag/eval.py`, 600 lignes), lecture `psutil` directe (`home.py:28`, `views/01_Socle_Hardware.py:83`).
- `core` n'importe jamais `streamlit` : la règle d'AGENTS.md est tenue.

### 1.5 Couplage avec le banc de benchmark

| Sens | Lien | Fichier |
|---|---|---|
| banc → core | `scripts/benchmark_slm.py` importe `BENCHMARKS_DIR, DATA_DIR, DEFAULT_COUNTRY_ISO_CODE, EMISSIONS_DIR, MISTRAL_API_KEY, MODELS_JSON_PATH` | `benchmark_slm.py:44-51` → `src/core/config.py` |
| scripts → core | `audit_and_update.py:14, 24`, `setup_models.py:15` (config), `setup_rag_models.py:19` (telemetry) | |
| core → sorties du banc | `benchmark_results.py:39` lit `benchmarks/results/*.json` ; `model_defaults.py:91` lit `config/models_catalog.json` (écrit par `scripts/build_catalog.py`) | |
| données partagées | `data/models.json` lu par l'app et par le banc | `models_db.py:26` |

Le seul import du banc est `config.py`. Mais ce fichier a des effets de bord à l'import et lit `.env` : toute retouche change le banc sans trace dans le SHA exporté.
Le banc de qualité a migré vers `slm-quality-bench` ; l'ancien banc de vitesse reste ici car l'app lit ses résultats.

Règle pour la v2 :
1. La v2 n'importe rien de `scripts/` et le banc n'importe rien de la v2. `src/core/config.py` et `scripts/benchmark_slm.py` restent figés dans la v1.
2. Les résultats du banc deviennent un contrat de données en lecture seule : un schéma JSON versionné (champ `schema_version`) pour `results/*.json` et `models_catalog.json`, validé par pydantic au chargement.
3. La v2 récupère ces fichiers comme des données (copie versionnée, ou téléchargement d'une release de `slm-quality-bench`), jamais comme du code.
4. Le catalogue `data/models.json` (local, non versionné) devient une table `models` de la v2, alimentée par la découverte Ollama et un fichier de surcharge.

## 2. Inventaire des dépendances

Total mesuré : 2 161 Mo dans `site-packages`. `requirements.txt` recopie `pyproject.toml` et y mêle les outils de dev (pytest, playwright, pre-commit). `constraints.txt` (1 369 lignes) fige la résolution pour Python 3.10.

### 2.1 Dépendances directes

« Usages » : fichiers de `src/` et `scripts/` qui importent le paquet. Taille : dossier du paquet seul.

| Paquet (installé) | Rôle | Usages | Taille | Risque |
|---|---|---|---|---|
| streamlit 1.66.0 (+ pydeck, altair, watchdog) | UI v1 | toute l'app | 35 + 23 + 10 Mo | Remplacé par le front web en v2 |
| plotly | Graphiques Arène et Sobriété | 2 | 40 Mo | Côté front en v2 |
| langchain 1.4.6 | Méta-paquet | 0 import direct | 2 Mo (+ `langchain_classic` 6) | Inutile seul |
| langchain-core 1.6.12 | Messages, `Document`, `@tool` | 8 | 5 Mo | Lié à tout le reste |
| langchain-community 0.4.1 | 3 chargeurs de fichiers | 1 (`rag/ingestion.py`) | 12 Mo | 0.4.2 casse `import ragas` (exclu dans `pyproject.toml`) |
| langchain-ollama, -mistralai, -openai, -anthropic | `get_langchain_model` | 2 à 4 | 1-2 Mo chacun | Suivent chacun leur SDK |
| langchain-huggingface, langchain-chroma, langchain-text-splitters | Embeddings, Chroma, découpe | 1 chacun | 1 Mo chacun | |
| langgraph 1.2.16 | Agent ReAct, Self-RAG | 2 | 4 Mo (+ sdk, checkpoint) | `create_react_agent` déprécié depuis la 1.0 |
| crewai 1.15.28 | Multi-agents | 1 | 26 Mo, plus `lancedb` 143 Mo et `pyarrow` 86 Mo qu'il tire | Route Mistral cassée ; écart 0.193 / 1.15 entre machines ; erreurs d'encodage de son bus d'événements sous Windows |
| ragas 0.4.3 | 2 métriques | 1 | 4 Mo (+ `scikit-network` 15, `instructor`, `datasets` 6) | Dernière version : 2026-01-13. Imports dépréciés vus en test. Casse selon la version de langchain-community |
| datasets 5.1.0 | Format d'entrée de Ragas | 1 | 6 Mo (+ pyarrow) | Disparaît avec Ragas |
| chromadb 1.5.9 | Base vectorielle | 0 direct (via langchain-chroma) | 5 Mo + binaire Rust 61 Mo + `kubernetes` 42 Mo + `grpc` 13 Mo + OpenTelemetry | Versions différentes entre machines (1.1.1 / 1.3.7 / 1.5.9) ; télémétrie |
| onnxruntime 1.31.0 | Tiré par chromadb | 0 | 43 Mo | Plus de roue cp310 dès 1.24 (marqueurs dans `pyproject.toml`) |
| sentence-transformers 6.1.0 | Embedding all-MiniLM-L6-v2, reranker CrossEncoder | 1 | 6 Mo + torch 509 + transformers 67 + scipy 99 + scikit-learn 31 + sympy 42 | Import mesuré à 7,2 s. Roue CPU sous Linux, d'où la détection « CPU Only » (F11) |
| torch 2.14.1 | Déclaré pour l'index CPU Linux ; un import dans l'app | 1 (`views/04_Agent_Lab.py:77`) | 509 Mo (+ torchvision 8) | Plus gros paquet |
| huggingface-hub, einops | Téléchargement des modèles RAG ; rien | 1 (script) ; 0 | 9 Mo (hf_xet) | `einops` inutile |
| docling 2.140.0 | Parsing riche de PDF | **0** | 5 Mo + docling-parse 37 + opencv (`cv2`) 113 + rapidocr 32 + docling-ibm-models (tire torch, transformers, accelerate) | Inutile : à retirer |
| pypdf, docx2txt | Lus par les chargeurs LangChain | 0 direct | petits | À garder en direct |
| codecarbon 3.3.1 | Suivi de session et du Crew | 3 | 2 Mo (+ `pycountry` 22) | 112 W constants relevés sur un processeur de 28 W (F15) |
| psutil, py-cpuinfo, nvidia-ml-py | Matériel | 10, 1, 2 | petits | À garder |
| GPUtil, setuptools | GPU (doublon de NVML) ; requis par GPUtil en 3.12 | 1 ; 0 | petits | GPUtil appelle `distutils` déprécié |
| ollama 0.6.3 | Client Ollama | 3 | 1 Mo | Fin, sur httpx. À garder |
| httpx 0.28.1 | Déclaré | 0 direct | 1 Mo | Utile en v2 |
| mistralai 3.2.0, openai 2.54.0, anthropic 1.15.0 | SDK cloud | 2, 2, 1 | 11, 19, 26 Mo | À garder (le juge Claude passe par anthropic) |
| pandas, openpyxl, xlrd | Outil CSV/Excel, historique CO₂ | 7 | 45 Mo | À garder si l'outil CSV reste |
| matplotlib, numexpr, python-docx | Outils graphique, calcul, document | 1 chacun | 28 Mo ; petits | Voir §3 |
| graphviz | Schéma de l'équipe Crew | 1 | petit | Exige le binaire Graphviz ; côté front en v2 |
| nest_asyncio | Async dans Streamlit | 2 | petit | Contournement, plus maintenu activement |
| timeout_decorator | rien | 0 | petit | Inutile |
| func-timeout | Délai du calculateur | 1 | petit | Remplaçable par l'évaluateur `numexpr` seul |
| pydantic 2.12.5, python-dotenv, tqdm | Modèles, `.env`, barre de progression (script) | | | À garder (sauf tqdm hors scripts) |

### 2.2 Ce qui pèse vraiment

| Bloc | Poids approximatif | Tiré par | Valeur visible |
|---|---|---|---|
| torch + transformers + scipy + scikit-learn + sympy | environ 750 Mo | sentence-transformers, docling | Un embedding de 90 Mo et un reranker |
| lancedb + pyarrow | environ 230 Mo | crewai (et datasets, streamlit pour pyarrow) | Aucune (mémoire CrewAI non utilisée) |
| opencv + rapidocr + docling-parse | environ 180 Mo | docling | Aucune (non importé) |
| chromadb (binaire, kubernetes, grpc, OTel) | environ 125 Mo | langchain-chroma | Index vectoriel de quelques centaines de passages |
| playwright | 108 Mo | dev | Tests e2e |

## 3. Recommandations par brique lourde

Versions lues sur PyPI le 2026-10-18 ; ne pas les figer sans installation réelle.

### 3.1 Orchestration LLM : LangChain, LangGraph, CrewAI

| Option | Pour | Contre | Coût |
|---|---|---|---|
| A. Garder | Rien à réécrire | 3 frameworks pour un ReAct et un Crew séquentiel ; API qui changent (0.x → 1.x en un an) ; panne Mistral du Crew ; dépréciations | Nul à court terme, élevé ensuite |
| B. Boucle d'outils maison sur les SDK (recommandé) | Le démonstrateur montre la boucle (pensée, appel d'outil, résultat) : on la maîtrise et on la trace. Ollama, OpenAI, Anthropic, Mistral et Groq gèrent l'appel d'outils natif. Le Crew séquentiel devient une suite d'agents de rôle | Il faut écrire l'adaptation des formats d'outils (3 dialectes : OpenAI-compatible, Anthropic, Mistral) | Environ 600 lignes et leurs tests ; 3 à 5 jours |
| C. pydantic-ai (2.57.0, « Production/Stable », MIT) | Agents typés, outils, streaming, sortie structurée, multi-fournisseurs ; même famille que pydantic | Encore une abstraction ; le Crew reste à écrire ; vérifier les extras par fournisseur et le support Ollama | 2 à 3 jours |
| D. LiteLLM (1.106.0) comme passerelle | Un seul format pour tous | Très gros, rythme de versions effréné, dépendances larges | Déconseillé |

Recommandation : **B**. Le dépôt de référence fait déjà ainsi (`src/wavestack/tools/`, `models/openai_chat.py`, `models/anthropic_messages.py`). Les implémentations `_*_impl` de `agent_tools.py` sont déjà indépendantes de LangChain : seuls les décorateurs `@tool` (l. 670 et suivantes) disparaissent. Self-RAG (4 nœuds) devient une boucle bornée ; HyDE une fonction async.
Fonctionnalité visible conservée : agent seul, équipe multi-agents, outils, email validé par l'humain. Le schéma Graphviz de l'équipe passe côté front.

### 3.2 Base vectorielle : Chroma

| Option | Pour | Contre |
|---|---|---|
| Garder Chroma | Connu | Environ 125 Mo, télémétrie à couper, écritures invisibles d'un processus à l'autre (AGENTS.md), versions qui divergent |
| sqlite-vec 0.1.9 (recommandé) | Une extension SQLite : les vecteurs vivent dans la même base que les documents, les runs et les évaluations. Déjà utilisé, épinglé, dans le dépôt de référence | Version 0.1.x, dernière sortie le 2026-03-31 : rythme lent. Recherche exacte (force brute), suffisante pour un démonstrateur (quelques milliers de passages) |
| LanceDB 0.40.0 | Rapide, colonnes | Classé « Alpha » sur PyPI, 143 Mo plus pyarrow |
| numpy en force brute | Zéro dépendance | Pas de persistance native ; garder comme repli de test |

Recommandation : **sqlite-vec**, derrière un port `VectorIndex` avec un repli numpy. Coût : 1 à 2 jours. Les index Chroma existants ne migrent pas : il faut réindexer (les documents sont locaux).

### 3.3 Embeddings et reranker : sentence-transformers et torch

| Option | Pour | Contre |
|---|---|---|
| Embeddings par Ollama (`/api/embed`) (recommandé) | Zéro paquet ML. Même serveur que la génération, donc même mesure d'énergie. `nomic-embed-text` est déjà installé sur ce poste ; `bge-m3` et `all-minilm` sont dans la bibliothèque Ollama | Ollama doit tourner (c'est déjà le cas pour tout le reste) |
| fastembed 0.9.0 (ONNX, Apache-2.0) | Hors ligne, sans torch. Couvre `sentence-transformers/all-MiniLM-L6-v2`, `multilingual-e5-large`, `nomic-embed-text-v1.5` et les rerankers `BAAI/bge-reranker-base`, `bge-reranker-v2-m3`, `jina-reranker-v2-base-multilingual` (vérifié dans le code source le 2026-10-18) | Tire onnxruntime (43 Mo) et tokenizers ; `bge-m3` dense absent de sa liste |
| Garder sentence-transformers | Rien à changer | 750 Mo, 7,2 s d'import |

Recommandation : embeddings par **Ollama** par défaut ; reranker par **fastembed** en option (extra `rerank`). Ollama n'offre pas, à ma connaissance, d'API de reranking stable : à revérifier avant la story.
Gain : environ 750 Mo et le plus long import. Coût : 1 jour. À dire à l'utilisateur : le choix d'embedding passe d'une liste de dossiers locaux à une liste de modèles Ollama.

### 3.4 Évaluation RAG : Ragas

Usage réel : deux métriques, fidélité et pertinence de la réponse (`eval_engine.py:13-15`), sur une seule question à la fois.

| Option | Pour | Contre |
|---|---|---|
| Garder Ragas | Métriques reconnues | Aucune version depuis 9 mois ; imports dépréciés ; casse selon langchain-community ; tire datasets, scikit-network, instructor ; score 0/100 affiché comme un succès quand il manque (F2) |
| Juge maison à sortie structurée (recommandé) | Fidélité : le juge extrait les affirmations puis vérifie chacune contre le contexte. Pertinence : le juge génère des questions depuis la réponse, comparées par cosinus à la question. Sortie JSON imposée (`format` d'Ollama, `tool_use` d'Anthropic, schéma OpenAI). On affiche le verdict par affirmation : gain pédagogique net | Il faut expliquer que ce n'est plus « Ragas » ; écrire les prompts et les tester sur quelques cas fixes | 
| deepeval, autres cadres | Plus de métriques | Mêmes défauts de poids et de dépendance à un framework |

Recommandation : **juge maison**, environ 250 lignes, 2 jours avec un jeu de cas de non-régression. Garder les noms de métriques (« fidélité », « pertinence ») et citer la méthode Ragas dans l'aide.

### 3.5 Mesure carbone : CodeCarbon et formules recopiées

| Cas | Aujourd'hui | Cible |
|---|---|---|
| Réponse d'un modèle local | 0,19 mg/token fixe, même pour un 0,8B et un 35B (`green_monitor.py:47`) | Énergie mesurée par génération : tracker CodeCarbon hors ligne autour de l'appel, ou échantillonneur maison (NVML pour le GPU, TDP × charge pour le CPU). Afficher « estimation » quand Windows n'expose pas RAPL |
| Réponse cloud | Formule EcoLogits recopiée à la main, calée sur l'ACV de Mistral Large 2 (`green_monitor.py:33-42`) | **ecologits** 0.11.3 (MPL-2.0) : `llm_impacts` par fournisseur et modèle, avec une fourchette. Vérifier la couverture de Groq |
| Session | `GreenTracker` CodeCarbon, `measure_power_secs=1`, `atexit` (`green_monitor.py:272-283`) | Garder, dans un service unique, avec un seul fichier d'historique (corrige F6) |

Recommandation : garder **CodeCarbon** (2 Mo, pycountry 22 Mo) pour le local, ajouter **ecologits** pour le cloud, sur le modèle de `wavestack/greenops.py` (imports paresseux, pas de réseau, une estimation qui échoue n'arrête jamais l'appel). Pas de perte visible ; le chiffre local devient enfin différent d'un modèle à l'autre.

### 3.6 Autres briques

| Brique | Recommandation | Raison |
|---|---|---|
| docling, einops, timeout_decorator, GPUtil, setuptools | Supprimer (possible dès la v1) | Aucun usage ; GPUtil doublonne NVML |
| Chargeurs LangChain | pypdf, python-docx (ou docx2txt) et lecture texte en direct ; découpe récursive maison (environ 50 lignes) | Retire langchain-community |
| ollama | Garder, un `AsyncClient` partagé par processus | Fin. httpx direct possible, mais le client officiel suit l'API (`think`, `tools`, `format`) |
| openai, anthropic, mistralai | Garder. Groq passe par le client OpenAI (déjà le cas) | SDK officiels |
| pandas + openpyxl | Garder si l'outil CSV reste ; sinon `csv` standard | 45 Mo pour un outil |
| matplotlib | Remplacer par une spécification de graphique JSON rendue par le front | 28 Mo ; images figées |
| graphviz, plotly, streamlit | Côté front en v2 | |
| nest_asyncio, func-timeout | Supprimer | Inutiles avec un serveur async |

Empreinte attendue du back v2 : ordre de grandeur 250 à 400 Mo (à mesurer), contre 2 161 Mo.

## 4. Stabilité et qualité

### 4.1 Gestion d'erreurs

- Bonne base : `EvalResult.not_evaluated` ne remplace jamais un score manquant par 0 (`eval_engine.py:35-56`) ; `answer_carbon` renvoie `None` plutôt qu'une valeur fausse ; les aides Ollama de `llm_provider.py` ne lèvent jamais.
- `try/except Exception` large qui masque les pannes : `vector_store.get_stats` renvoie 0 document sur erreur (l. 48-58), `clear` journalise sans remonter (l. 60-65), `list_all_models` (`provider_factory.py:200-210`).
- `health_check_all` appelle réellement les fournisseurs cloud (`provider_factory.py:225-232`).
- Pas de type d'erreur métier commun : l'app teste des messages ou des `None`. La v2 a besoin d'erreurs typées traduites en codes HTTP.

### 4.2 Async, sync et concurrence

- Le core est async (streaming), l'app est sync : `asyncio.run` à chaque génération et `nest_asyncio` pour les boucles imbriquées (§1.4). Les stratégies RAG sync appellent `asyncio.run` en interne (`hyde.py:58`, `self_rag.py:197`) : impossible depuis une boucle déjà active sans `nest_asyncio`.
- Un nouveau client Ollama async par appel (`ollama_provider.py:47-55`), pour contourner les boucles fermées : pas de réutilisation de connexion.
- Singletons globaux sans verrou : `provider_factory.py:76-83, 240-249`, `metrics_service.py:252-257`.
- Aucune file d'attente devant Ollama : deux onglets peuvent charger deux gros modèles en même temps et saturer la RAM. Le garde-fou RAM est consultatif.
- Thread maison pour la RAM du Crew (`tabs/agent/crew.py:499-506`), sans `join` garanti.

### 4.3 État global et effets de bord à l'import

| Effet | Fichier |
|---|---|
| `logging.basicConfig` | `llm_provider.py:18`, `agent_engine.py:27`, `models_db.py:9` |
| `load_dotenv` et `mkdir` | `config.py:7, 21-22` |
| `MODELS_DB` chargé une fois | `models_db.py:26` |
| Identifiants SMTP lus à l'import | `agent_tools.py:51-54` |
| `outputs/` créé relativement au dossier courant | `agent_tools.py:47-48` (d'où `output/` et `outputs/` à la racine du dépôt) |
| Hôte Ollama codé en dur | `ollama_provider.py:39`, `crew_engine.py:130` |

### 4.4 Sécurité et vérité

- L'outil `analyze_csv` lit n'importe quel chemin donné par le modèle (`agent_tools.py:319-325`), alors que l'ingestion RAG limite aux dossiers autorisés (`rag/ingestion.py:37-60`). À aligner.
- L'envoi d'email passe par une validation humaine (`send_validated_email`, l. 266) : bon modèle à garder.
- CO₂ local constant par token (§3.5) : chiffre présenté comme une mesure alors que c'est une moyenne fixe.

### 4.5 Tests

- `tests/unit` : 34 fichiers, **817 tests passés** en 187 s sur ce poste. Les 4 échecs signalés dans AGENTS.md ne se reproduisent plus : la note est à mettre à jour.
- Couverture `src/core` : 81,65 %. Points faibles : `model_profiles` 44 %, `resource_manager` 49 %, `mistral_provider` 51 %, `models_db` 53 %, `crew_engine.create_custom_crew` (l. 165-214) non couvert, initialisation de l'agent (l. 107-123) non couverte.
- Les modules morts sont testés (session, exporters, repositories) : du coût sans valeur.
- Beaucoup de tests simulent LangChain, Chroma ou Ragas : ils partent avec ces libs.
- Tests réutilisables tels quels ou presque : `test_model_defaults`, `test_benchmark_results`, `test_metrics`, `test_answer_carbon` (règles), `test_agent_tools` (partie `_impl`), `test_rag_security`, `test_inference_service` (sémantique de reprise).
- La CI ne tourne pas (branche `master` absente des déclencheurs). La v2 doit l'activer dès le premier commit.

### 4.6 Dette repérée

1. Trois routages tag → fournisseur (§1.3).
2. `ILLMProvider` impose `get_langchain_model` à chaque fournisseur.
3. 1 233 lignes mortes et leurs tests.
4. `requirements.txt` mélange dev et prod ; trois sources de vérité des dépendances.
5. Fonctions de debug et blocs `__main__` dans le core (`agent_engine.py:284-314`, `inference_service.py:367`).
6. Débit affiché qui inclut chargement et prefill (F4) alors que `metrics.ollama_metrics` sait le calculer à part.

## 5. Architecture cible du back v2

### 5.1 Choix du cadre HTTP

**FastAPI + uvicorn**. Raisons : même pile que le dépôt de référence (savoir-faire et code à réutiliser) ; pydantic déjà utilisé ; OpenAPI généré, utile au front ; async natif, aligné sur `ollama.AsyncClient`, httpx et les SDK cloud ; SSE simple avec `StreamingResponse` (ou `sse-starlette` 3.5.0).
Alternatives écartées : Litestar (bon, mais une pile de plus à apprendre), Flask (sync), Starlette nu (on réécrirait la validation).

Générations en **SSE** plutôt qu'en WebSocket : flux unidirectionnel, reprise facile, compatible `fetch` + `ReadableStream`. L'arrêt passe par l'abandon de la requête (détection de déconnexion) ou par `POST /api/runs/{id}/cancel`. L'Arène multiplexe plusieurs modèles dans un seul flux, chaque événement portant `model`.

Événements SSE communs : `start`, `token`, `reasoning`, `tool_call`, `tool_result`, `sources`, `metrics`, `carbon`, `error`, `done`.

### 5.2 Découpage

```
src/wavelocalai/
  config.py          # pydantic : wavelocalai.toml + .env, chargé une fois, sans effet de bord à l'import
  errors.py          # erreurs typées → codes HTTP
  models/            # LLM
    port.py          # ChatModel : stream(messages, tools, format) -> événements
    ollama.py  openai_compat.py (OpenAI, Groq)  anthropic.py  mistral.py
    registry.py      # identité unique d'un modèle : local / cloud / distant-Ollama
    catalog.py       # catalogue, scores du banc (contrat JSON validé), choix par défaut
  inference/         # chat, labo, arène ; métriques ; file d'attente Ollama
  rag/               # ingestion (pypdf, docx), découpe, embeddings, index sqlite-vec, reranker, stratégies
  agents/            # boucle d'outils, équipe séquentielle, outils (repris de agent_tools._impl)
  evaluation/        # juge LLM à sortie structurée (fidélité, pertinence)
  greenops/          # CodeCarbon local, ecologits cloud, historique
  hardware/          # psutil, NVML, accélérateur, RAM disponible
  store/             # SQLite unique : schéma, migrations
  web/
    app.py           # routes FastAPI
    static/          # front web servi par le back (comme wavestack/web)
```

Règles : `web/` est le seul module qui connaît FastAPI ; les autres sont testables sans serveur. Imports lourds paresseux (`fastembed`, `codecarbon`).

### 5.3 Endpoints principaux

| Fonction | Méthode et chemin | Sortie |
|---|---|---|
| Santé | `GET /api/health` | Ollama joignable, version, fournisseurs cloud configurés (sans les appeler) |
| Matériel | `GET /api/hardware`, `GET /api/hardware/live` (SSE, 1 Hz) | CPU, RAM, GPU, accélérateur |
| Modèles | `GET /api/models`, `GET /api/models/defaults`, `POST /api/models/pull` (SSE de progression), `DELETE /api/models/{tag}`, `POST /api/models/{tag}/unload` | Liste unifiée local/cloud, scores du banc |
| Chat | `POST /api/chat` (SSE) | Jetons, raisonnement, métriques, CO₂ |
| Arène | `POST /api/arena` (SSE multiplexé), `POST /api/arena/{id}/judge` | Réponses parallèles ou en file, verdict |
| Documents | `POST /api/documents` (envoi de fichier, job), `GET /api/documents`, `DELETE /api/documents/{id}`, `DELETE /api/documents` | Ingestion en tâche de fond |
| Assistant documentaire | `POST /api/rag/query` (SSE : `sources` puis jetons) | Réponse sourcée |
| Évaluation | `POST /api/rag/evaluations` (job), `GET /api/rag/evaluations/{id}` | Scores et verdict par affirmation |
| Agent seul | `POST /api/agents/run` (SSE : pensées, outils, réponse), `POST /api/agents/runs/{id}/approve-email` | Trace complète |
| Équipe | `POST /api/crews/run` (SSE par agent), `GET /api/crews/templates` | Trace par rôle, RAM de crête |
| Sobriété | `GET /api/carbon/session`, `GET /api/carbon/history`, `POST /api/carbon/session/reset` | Énergie et CO₂ |
| Jobs | `GET /api/jobs/{id}` (SSE de progression), `POST /api/jobs/{id}/cancel` | Pour ingestion, évaluation, équipe |
| Fichiers produits | `GET /api/outputs/{name}` | Documents et graphiques des outils |

### 5.4 Modèle de données (SQLite unique, `data/wavelocalai.db`)

| Table | Contenu |
|---|---|
| `models` | tag, nom, origine (local, cloud, distant), fournisseur, paramètres totaux et actifs, RAM estimée, capacités (outils, raisonnement) |
| `runs` | id, type (chat, arène, rag, agent, équipe, éval), modèle, début, fin, statut, jetons d'entrée et de sortie, TTFT, débit de génération, énergie Wh, CO₂ g, méthode de mesure (`codecarbon`, `ecologits`, `estimation`) |
| `messages` | run, rôle, contenu, raisonnement, appels d'outils |
| `documents`, `chunks`, `chunks_vec` (table virtuelle sqlite-vec, une par dimension d'embedding) | source, empreinte, modèle d'embedding, texte, position |
| `evaluations` | run, métrique, score, verdicts détaillés (JSON) |
| `jobs` | id, type, progression, erreur |

La table `runs` remplace le CSV d'émissions et l'historique dispersé (corrige F5 et F6 à la source). Le catalogue du banc reste un fichier JSON en lecture seule.

### 5.5 Configuration

- `wavelocalai.toml` versionné pour les valeurs par défaut (hôte Ollama, pays et PUE, tailles de découpe, modèle d'embedding, délais).
- `.env` pour les secrets (clés API, SMTP) seulement.
- Un objet `Settings` pydantic chargé au démarrage, injecté dans les services ; aucun `os.getenv` hors de `config.py`.
- Hôte Ollama configurable partout (`OLLAMA_HOST`), écoute du serveur sur `127.0.0.1` par défaut (corrige F8).

### 5.6 Concurrence

- Un `AsyncClient` Ollama partagé ; un sémaphore « Ollama local » (1 par défaut) pour sérialiser les générations locales ; les appels cloud en parallèle.
- Travail CPU (parsing PDF, reranker ONNX) dans un pool de threads (`anyio.to_thread`).
- Tâches longues en jobs annulables, avec progression en SSE.
- Mesure carbone par run : un tracker à la fois par processus (CodeCarbon n'est pas conçu pour des trackers concurrents) ; en Arène parallèle, mesurer l'ensemble et répartir au prorata des jetons, en le disant.

### 5.7 Ce qui se réutilise de `src/core/`

| Réutilisable presque tel quel | Adaptation |
|---|---|
| `model_defaults.py` (règles de choix, 99 %) | Couper le lien à `config` et `models_db` ; injecter le catalogue |
| `benchmark_results.py` | Ajouter le schéma pydantic du contrat |
| `metrics.py` (`ollama_metrics`, débits) | Exposer débit de génération et prefill séparés |
| `agent_tools.py`, fonctions `_*_impl` | Retirer `@tool`, ajouter un schéma JSON par outil, restreindre les chemins |
| `rag/ingestion._validate_path` | Tel quel |
| `accelerator.py`, `HardwareMonitor`, `read_app_emissions` | Tel quel, puis migration de l'historique vers `runs` |
| Streaming Anthropic, OpenAI, Mistral des `providers/` | Retirer `get_langchain_model` ; ajouter les outils |
| `inference_service.retry_interrupted` | Logique de reprise à garder |
| `answer_carbon` | Garder la règle « jamais 0 pour inconnu », remplacer la formule |

À ne pas reprendre : `rate_limiter`, `session/`, `exporters/`, `repositories/`, `model_detector`, `metrics_service`, `llm_provider` (fondu dans `models/registry`), `telemetry` (inutile sans Chroma, CrewAI, Ragas, HF ; garder `ANONYMIZED_TELEMETRY` si une lib en réclame encore).

### 5.8 Plan de migration

| Étape | Contenu | Livrable vérifiable |
|---|---|---|
| 0 (v1, PR courte) | Retirer docling, einops, timeout_decorator, GPUtil et setuptools ; séparer dev et prod dans `requirements.txt` ; corriger la route Mistral du Crew ; mettre à jour la note de tests d'AGENTS.md | `uv sync` plus léger ; tests verts |
| 1 | Squelette v2 : FastAPI, `Settings`, SQLite, `/api/health`, `/api/hardware`, `/api/models` ; CI active | Front de démo qui liste les modèles |
| 2 | Port `ChatModel` (Ollama, OpenAI/Groq, Anthropic, Mistral) ; chat en SSE ; métriques ; greenops (CodeCarbon + ecologits) ; table `runs` | Une réponse avec débit et CO₂ mesurés |
| 3 | Arène (SSE multiplexé, file Ollama, juge) | Comparaison de 3 modèles sans saturer la RAM |
| 4 | RAG : ingestion, embeddings Ollama, sqlite-vec, reranker fastembed, stratégies naïve, HyDE, Self-RAG | Réponse sourcée ; réindexation |
| 5 | Évaluation maison | Scores et verdict par affirmation sur un jeu fixe |
| 6 | Agents : boucle d'outils, outils repris, email validé ; équipe séquentielle | Parité avec l'agent Solo et le Crew v1 |
| 7 | Bascule : la v1 passe en archive ; le banc lit et écrit ses JSON sans changement | Parité fonctionnelle listée page par page |

Fonctionnalités visibles : toutes conservées. Changements à annoncer : modèles d'embedding issus d'Ollama, évaluation « méthode Ragas » au lieu de la librairie, schéma d'équipe dessiné par le front.

## Décisions à prendre par l'utilisateur

| # | Décision | Options | Recommandation |
|---|---|---|---|
| 1 | Orchestration des agents | A. garder LangChain/LangGraph/CrewAI ; B. boucle maison sur les SDK ; C. pydantic-ai | **B** : moins de dépendances, boucle visible, déjà fait dans le dépôt de référence |
| 2 | Base vectorielle | Chroma ; sqlite-vec ; LanceDB | **sqlite-vec**, avec un repli numpy, en acceptant sa version 0.1.x |
| 3 | Embeddings | Ollama ; fastembed ; sentence-transformers | **Ollama** pour l'embedding, **fastembed** en option pour le reranker ; retirer torch |
| 4 | Évaluation RAG | Ragas ; juge maison ; autre cadre | **Juge maison** à sortie structurée, verdict par affirmation affiché |
| 5 | CO₂ local | Constante par token ; mesure CodeCarbon par run ; échantillonneur maison | **CodeCarbon par run**, étiqueté « estimation » sans RAPL ; **ecologits** pour le cloud |
| 6 | Cadre HTTP et flux | FastAPI + SSE ; FastAPI + WebSocket ; Litestar | **FastAPI + SSE** |
| 7 | Outils graphique et CSV | Garder matplotlib et pandas ; spec JSON rendue par le front et `csv` standard | **Spec JSON** pour les graphiques ; garder pandas seulement si l'analyse Excel est montrée en démo |
| 8 | Lien avec le banc | Import de code ; contrat de données JSON versionné | **Contrat JSON** en lecture seule, récupéré depuis `slm-quality-bench` ou copié ; ne jamais toucher `benchmark_slm.py` ni `src/core/config.py` |
| 9 | Nettoyage de la v1 | Rien ; étape 0 seule ; refonte | **Étape 0 seule** (dépendances inutiles, route Mistral du Crew), en PR dédiée, sans toucher au périmètre du banc |
| 10 | Fournisseurs cloud | Garder les 4 ; réduire | Garder les 4 : le coût est faible avec les SDK officiels et Groq passe par le client OpenAI |
