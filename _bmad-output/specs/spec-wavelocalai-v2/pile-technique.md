# Pile technique de la v2

Décisions §6 validées par Anaël le 2026-10-18, précisées par `ARCHITECTURE-SPINE.md` (règles `AD-n`, qui priment sur ce fichier). Versions : celles de la spine §Stack, vérifiées par installation réelle le 2026-10-18 ; les autres se vérifient sur PyPI ou par installation au moment de la story, jamais de mémoire.

## Couches

| Couche | Choix | Remplace |
|---|---|---|
| Python et projet | `requires-python = ">=3.11,<3.13"` pour tout le dépôt dès le premier lot, cible de lint `py311` pour `src/wavelocalai/` et `tests/v2/` seulement (AD-1). Un seul `pyproject.toml` et `uv.lock`, installation éditable, `dev-mode-dirs = [".", "src"]` ; la v2 n'importe jamais `src.*`, la v1 jamais `wavelocalai` ; lanceur `wavelocalai-v2`, port 8502 (AD-2). Version unique : `2.0.0.dev0` dès le premier lot, puis `2.0.0aN` à la fin de chaque étape (`a1` à `a7` pour les étapes 1 à 7), `2.0.0` à la bascule (AD-3). pydantic reste en 2.12.x jusqu'à la bascule (crewai de la v1 exige `pydantic<2.13`), puis passe à la version vérifiée à ce moment | Python 3.10 |
| Serveur | FastAPI + uvicorn, SSE natif `fastapi.sse.EventSourceResponse` (sans sse-starlette), écoute sur `127.0.0.1`, protection `Host`/`Origin`, télémétrie FastAPI coupée (AD-19) | Streamlit |
| Front | Coquille HTML unique, modules JS natifs sans compilation ni Node, routeur par `hash`, écrans chargés par `import()` (`mount`/`unmount`), Custom Elements `wl-` sans Shadow DOM, un client SSE et un store (AD-20) ; détail dans `03-ux-front.md` §3 ; graphiques en SVG fait main (deux types) | Pages et onglets Streamlit |
| Modèles | Ports `ChatModel` et `Embedder` (AD-8), 4 adaptateurs sur les SDK officiels : Ollama natif (`/api/chat`, seul à donner `eval_count`/`eval_duration`, `tps_source = "ollama_eval"`), OpenAI-compatible (OpenAI, Groq), Anthropic, Mistral ; adaptateurs `fake` (`ChatModel` et `Embedder` à vecteurs déterministes) en test seulement. Registre unique portant `origin` (`local`, `cloud`, `unknown`) et `kind` (`chat`, `embedding`, `reranker` ; règle de `is_embedding_model`, PR #30) ; `registry.resolve(tag, allow_cloud)` seul accès (AD-9) | LangChain, `llm_provider`, `model_detector` |
| Agents | Boucle d'outils maison (3 formats d'appel d'outils : OpenAI-compatible, Anthropic, Mistral), équipe séquentielle maison ; Self-RAG en boucle bornée, HyDE en fonction async ; schéma d'équipe dessiné par le front ; approbation d'outil sensible par le hub (AD-9) | LangGraph, CrewAI (pydantic-ai écarté : `/v1` d'Ollama sans métriques D3, ~200 versions par an) |
| RAG | sqlite-vec derrière un port `VectorIndex` (repli numpy pour les tests) ; une base = un modèle d'embedding, table `chunks_vec_<dim>` (AD-16) ; embeddings locaux par Ollama `/api/embed` ; Ollama n'ayant pas d'API de reranking, reranker fastembed en dépendance de base (extra `rerank` retiré par la story 9.5, D-R6), `local_files_only=True`, absent = RAG sans reranker avec raison ; cache rempli par le bouton « Installer le reranker » de l'écran Modèles (run `pull`, AD-17) | Chroma, sentence-transformers, torch |
| Évaluation | Juge maison à sortie structurée (`response_schema` du port : `format` d'Ollama, `tool_use` d'Anthropic, schéma OpenAI). Fidélité : affirmations extraites puis vérifiées une à une contre le contexte, verdict par affirmation affiché. Pertinence : questions générées depuis la réponse, cosinus avec la question. Noms gardés, méthode Ragas citée dans l'aide. Échec = « non mesurable ». Calibré sur un jeu fixe de cas de non-régression | Ragas |
| Carbone | Service `greenops/` sur le modèle de `wavestack/greenops.py` : CodeCarbon `OfflineEmissionsTracker` par run feuille local, sous le sémaphore Ollama, un seul à la fois, `start`/`stop` dans le pool de threads ; cloud par `ecologits.tracers.utils.llm_impacts(...)` en arguments nommés, jamais `EcoLogits.init()`, Groq par table explicite de `wavelocalai.toml` (AD-11) ; champ `co2` d'AD-10 ; imports paresseux, aucun réseau, un échec n'arrête jamais l'appel | Tracker par session, constante 0,19 mg/token, formule recopiée |
| Persistance | SQLite unique (défaut `data/wavelocalai.db`, dossier configurable), WAL, un seul écrivain, migrations `store/migrations/NNNN_*.sql` avant seulement, sauvegarde `.bak` avant migration, base plus récente que le code = refus de démarrer (AD-12) ; « Effacer » selon AD-13 ; export JSON/Markdown par conversation ; alerte au démarrage si le dossier est sous OneDrive | CSV d'émissions, état de session |
| Configuration | `wavelocalai.toml` versionné (hôte Ollama, pays et PUE, découpe, embedding, délais, table de prix cloud datée, correspondance Groq → ecologits) lu par `tomllib`, + `.env` pour les secrets ; objet `Settings` pydantic chargé une fois ; réglages modifiés par l'UI dans la table `preferences` ; l'app n'écrit jamais le `.toml` (AD-15) | `config.py` à effets de bord |
| Données tabulaires | `csv` standard ; pandas seulement si l'analyse Excel est montrée en démo | matplotlib, pandas |

Gain attendu : environ 1,8 Go de dépendances et 4 librairies instables en moins. À annoncer aux utilisateurs : embeddings issus d'Ollama (liste de modèles Ollama), évaluation « méthode Ragas » sans la librairie, schéma d'équipe dessiné par le front.

## Découpage

Arborescence fixée par le Structural Seed de la spine (`__main__.py`, `config.py`, `errors.py`, `telemetry.py`, `runs/`, `models/`, `inference/`, `rag/`, `agents/`, `evaluation/`, `greenops/`, `hardware/`, `store/`, `web/`) ; sens des imports vérifié par `tests/v2/unit/test_layers.py` (AD-4) ; imports lourds paresseux (AD-4, AD-21). Tests dans `tests/v2/{unit,web,e2e}/`.

## Modèle de données

Colonnes fixées par la migration de la story qui crée la table (spine §Deferred).

| Table | Contenu |
|---|---|
| `app_sessions` | une par démarrage du serveur et par remise à zéro du CO₂ (AD-10) |
| `conversations` | id, `kind` (`chat`, `rag`, `agent`), créée par le hub avec le premier run |
| `runs` | id, `kind` (racine, ou feuille en liste close `generation`, `judge`, `embedding`, AD-5), `parent_run_id`, `app_session`, conversation (`NULL` après effacement), modèle, début, fin, statut (AD-5), jetons entrée/sortie, TTFT, débit et `tps_source`, énergie Wh, `co2` d'AD-10 (feuilles seulement), `params` sans texte saisi (AD-7) |
| `run_events` | run, `seq`, type, données, écrits par lots (AD-7) |
| `messages` | conversation, run, rôle, contenu, raisonnement, appels d'outils ; écrits par le hub seul |
| `documents`, `chunks`, `chunks_vec_<dim>` | source, empreinte, modèle d'embedding, `status` (`indexing`, `ready`, `failed`), texte, position ; table vec0 par dimension, `rowid = chunks.id`, créée par `store.ensure_vec_table(dim)` |
| `evaluations` | run, métrique, score, verdicts par affirmation (JSON) |
| `model_facts` | cache de `/api/show` par (tag, digest) |
| `preferences` | clé, valeur JSON (réglages modifiés par l'UI) |

Pas de table `jobs` ni de table `models` : le registre se reconstruit en mémoire (cache d'Ollama, cloud depuis `Settings`, catalogue versionné `config/models_catalog.json` en lecture seule, `qb.results/1`, débit mesuré tiré de `runs`, AD-15).

## Résultats du banc (AD-22)

L'app lit seulement `benchmarks/slm-quality/slm-quality-results.json`, synchronisé par l'Action existante (`scripts/sync_slm_results.py`), jamais par le réseau. Modèle pydantic `extra="ignore"` ; `schema` différent de `qb.results/1` = références indisponibles avec raison. Jointure `results[]` ↔ `models[]` sur `(model, digest)` ; un modèle installé correspond par `(tag, digest)`, à défaut par tag avec la mention « autre version ». `null` = « inconnu » ou « non classé », jamais 0 ; fractions affichées en pourcentage ; `energy` affichée seulement si `status = "measured"`.

## Concurrence (AD-14)

- Un client Ollama async partagé ; sémaphore « Ollama local » à 1, pris **par appel** (génération, lot d'embedding) : une ingestion et un chat s'intercalent ; appels cloud en parallèle.
- Au plus un run racine actif par `kind`.
- Travail CPU (pypdf, docx, reranker ONNX) dans un pool de threads.
- Tâches longues (ingestion, évaluation, équipe, installation de modèle) = runs annulables avec progression SSE.
- Sonde Ollama ≤ 1 s ; état en cache 5 s pour les routes de lecture, 1 s pour la sonde du flux système (AD-15 amendé) ; un test de budget parcourt toutes les routes `GET` sans paramètre de chemin, hors SSE, et vérifie < 300 ms Ollama injoignable (AD-15).

## Réutilisation

| Source | Reprise | Adaptation |
|---|---|---|
| `src/core/model_defaults.py` | Règles de choix (99 %) | Copier (AD-2), injecter le catalogue, couper `config` et `models_db` |
| `src/core/benchmark_results.py` | Lecture des résultats | Schéma pydantic de `qb.results/1` (AD-22) |
| `src/core/metrics.py` | `ollama_metrics`, débits | Débit de génération et prefill séparés |
| `src/core/agent_tools.py`, fonctions `_*_impl` | Outils | Retirer `@tool`, schéma JSON par outil, chemins restreints |
| `rag/ingestion._validate_path` | Tel quel | — |
| `accelerator.py`, `HardwareMonitor`, `read_app_emissions` | Tel quel | Historique dans `runs` ; CSV de la v1 non importé (AD-23) |
| `src/core/telemetry.py` | `disable_telemetry()` et opt-outs | Copie adaptée en `wavelocalai/telemetry.py`, appelée avant fastembed et huggingface_hub, `FASTAPI_OTEL_AUTO_CONFIGURE=false` ajouté (AD-19, AD-21) |
| Streaming des `providers/` cloud | Flux Anthropic, OpenAI, Mistral | Retirer `get_langchain_model`, ajouter les outils |
| `inference_service.retry_interrupted` | Logique de reprise | — |
| `answer_carbon` | Règle « jamais 0 pour inconnu » | Nouvelle formule |
| Harnais `agentic-harness-training-demo` | `models/openai_chat.py`, `models/anthropic_messages.py`, `tools/`, `greenops.py`, front `wavestack/web` | Copier ce qui sert, sans dépendre du dépôt |
| Archive `docs/archive/ancienne-v2/` | `hardware.py`, `nvml.py`, `machine_state.py` (étape 1, bridage thermique) | — |

Tout ce qui est repris est copié puis adapté, jamais importé (AD-2). À ne pas reprendre : `rate_limiter`, `session/`, `exporters/`, `repositories/`, `model_detector`, `metrics_service`, `llm_provider`.
