# Audit performance et stabilité de la v1 (octobre 2026)

Poste : Windows 11, Python 3.12.14, `.venv` de l'application. Mesures du 2026-10-18.
Scripts de mesure : `C:\Users\UTILIS~1\AppData\Local\Temp\claude\C--Users-Utilisateur-Documents-GitHub-wavelocalai\d88119c1-6cbe-4761-ad14-af4fdea26275\scratchpad\perf\` (`imp.py`, `pages.py`, `prof.py`), hors dépôt.

## Résumé : où part le temps

1. **Ollama via `localhost` coûte 2,05 s par nouveau client** (repli IPv6 sous Windows). Avec `127.0.0.1` : 0,11 s. Chaque rerun d'Arène, d'Agents ou d'Assistant documentaire (base non vide) paie cet appel : 2,18 s sur 2,19 s.
2. **Premier chargement d'une session : 6 à 14 s**, dont 6 à 11 s pour démarrer le tracker CodeCarbon du routeur (`py-cpuinfo` : 9 s à lui seul) et 2 à 6 s d'imports.
3. **Aucun cache sur le travail réel** : un seul `st.cache_data` dans toute l'application (état d'Ollama, TTL 10 s). Liste des modèles, classement, benchmark relus à chaque rerun.
4. **Imports lourds au premier accès d'une page** : Assistant documentaire 6,1 s (`sentence_transformers` 5,4 s), Agents 4,1 s (CrewAI 2,1 s). Le routeur seul n'en charge que 2,3 s.
5. **État par session** : moteur RAG, tracker CodeCarbon (2 threads, jamais arrêtés) et évaluateur vivent dans `st.session_state`. Chaque session de navigateur les recrée.

Les pages Accueil et Sobriété sont rapides (0,11 s à chaud). Le contenu des onglets est quasi gratuit (3 à 5 ms chacun). Le coût vient du haut de page, pas des onglets.

## Conditions des mesures

- Ollama a tourné pendant toute la série de pages (cas d'usage réel, 32 modèles installés). Le message du coordinateur indique qu'un téléchargement de 30 B était en pause depuis son arrivée. Les imports (`imp.py`) ont été mesurés deux fois, avant et après ce message : écarts de 0 à 25 %, chiffres retenus = seconde série (stable). Les temps de page et le profil Ollama ont été pris après le message.
- Les appels Ollama ont été vérifiés avec `curl` : `/api/tags` 0,31 s, `/api/version` 0,21 s (hors Python, `localhost` aussi). Python `ollama.Client(host=...)` : `localhost` 2,17 s, `127.0.0.1` 0,11 s, trois appels sur un même client 0,32 s.
- Pas de mesure sans Ollama (un autre agent s'en charge). Par lecture de code, `list_models` attrape l'exception et renvoie une liste vide ; la durée dépend alors du refus de connexion.
- Mesure faite sous `AppTest`, pas dans un navigateur : elle exclut le rendu et le transfert WebSocket.

## Mesures d'import

Commande : sous-processus par module, `python -c "import time,psutil,os;t=time.perf_counter();import M;..."` (`imp.py`). Temps = import seul dans un processus neuf ; Mo = RSS du processus après import.

| Module | Temps (s) | RSS (Mo) |
|---|---|---|
| sentence_transformers | 5,39 | 457 |
| src.core.rag_engine | 6,12 | 496 |
| src.app.tabs.agent.crew | 4,59 | 368 |
| src.core.crew_engine | 4,14 | 312 |
| src.app.tabs.rag.eval | 3,59 | 312 |
| src.core.eval_engine | 2,90 | 233 |
| src.core.agent_engine | 2,86 | 237 |
| src.app.ui (= states = llm_provider) | 2,45 | 177 |
| src.core.llm_provider | 2,21 | 146 |
| crewai | 2,11 | 166 |
| ragas | 1,75 | 179 |
| transformers | 1,52 | 65 |
| torch | 1,04 | 198 |
| chromadb | 0,68 | 68 |
| streamlit | 0,38 | 66 |
| codecarbon | 0,12 | 57 |

Les valeurs ne s'additionnent pas (modules partagés). Top des imports cumulés (`python -X importtime -c "import src.core.rag_engine"`, en s) :

| Rang | Module | Cumulé (s) |
|---|---|---|
| 1 | src.core.rag_engine | 6,53 |
| 2 | src.core.rag.models_factory | 5,66 |
| 3 | sentence_transformers | 5,62 |
| 4 | sentence_transformers.backend | 3,90 |
| 5 | sentence_transformers.backend.load | 2,98 |
| 6 | transformers.configuration_utils | 2,98 |
| 7 | sentence_transformers.base.sampler / base | 1,66 |
| 8 | sentence_transformers.base.model | 1,65 |
| 9 | transformers | 1,51 |
| 10 | transformers.dependency_versions_check | 1,11 |
| 11 | transformers.generation.configuration_utils | 1,09 |
| 12 | transformers.generation.logits_process | 1,09 |
| 13 | torch | 1,09 |

Chemin du routeur (`-X importtime -c "import src.app.ui, src.app.states"`, 2,58 s) :

| Module | Cumulé (s) |
|---|---|
| src.core.providers (via provider_factory) | 2,13 |
| anthropic (importé par anthropic_provider, même sans clé) | 1,06 |
| openai (importé par openai_provider et groq_provider) | 0,50 |

## Temps par page sous `AppTest`

Commande : `.venv\Scripts\python pages.py` (`AppTest.from_file`, un fichier par page, `run()` trois fois). « Froid » = premier `run()` du fichier dans un processus où les pages précédentes ont déjà chargé leurs modules : il sous-estime le froid absolu de la page. Chaud = 2e et 3e run.

| Page | Froid (s) | Chaud (s) | Cause du chaud |
|---|---|---|---|
| Accueil (routeur + home) | 13,72 | 0,11 | `psutil.cpu_percent(0,1)` + cache Ollama |
| Arène des modèles | 4,84 | 2,18 | `list_models` : 2,15 s (profil `cProfile`) |
| Assistant documentaire, base vide | 7,25 | 0,01 | rien ne s'exécute au-delà du moteur |
| Assistant documentaire, base non vide | (non mesuré sur ce poste) | ≈ 2,2 estimé | même `list_models` (`03_RAG_Knowledge.py:339`) |
| Agents autonomes | 5,95 | 2,17 | `list_models` (`04_Agent_Lab.py:100`) |
| Sobriété et matériel | 1,81 | 0,12 | `psutil` + lecture CSV |

Profil du rerun de l'Arène : 2,182 s au total, dont `LLMProvider.list_models` 2,163 s, entièrement dans `httpx` (`_send_single_request` 2,152 s). `model_menu` 4 ms. Les quatre onglets (`render_chat_tab`, `render_lab_tab`, `render_manager_tab`, `render_arena_tab`) font 3 à 5 ms chacun au total.

Froid absolu d'une première session (premier accès, Accueil) : 13,7 s sous `AppTest`. Décomposition mesurée à part :

| Poste | Temps (s) |
|---|---|
| Imports du routeur (`src.app.ui`, providers, streamlit) | ≈ 2,5 à 3 |
| `GreenTracker.start()`, premier du processus (2 mesures) | 11,5 puis 6,5 |
| dont `cpuinfo.get_cpu_info()` (appelé par CodeCarbon) | 9,0 |
| `GreenTracker` suivants (même processus) | 1,25 à 1,33 chacun |

Test de fuite de threads (`/tmp/t.py`) : chaque `GreenTracker.start()` ajoute 2 threads (3 → 5 → 7), jamais libérés tant que `stop()` n'est pas appelé.

Mémoire du processus de test après avoir chargé toutes les pages : 783 Mo de RSS (Accueil 269 Mo, +511 Mo après l'Assistant documentaire avec `all-MiniLM-L6-v2` ; Agents n'ajoute presque rien après).

## Streamlit lui-même ou le back ?

| Symptôme | Streamlit (modèle de rerun) | Back v1 |
|---|---|---|
| Changer d'onglet `st.tabs` | Non : changement côté navigateur, sans rerun. Les 4 onglets s'exécutent tous à chaque rerun, mais coûtent 3 à 5 ms | Aucun |
| Changer de page | Oui : le routeur `Accueil.py` et la page s'exécutent en entier (0,1 s si la page est vide de travail) | Appel Ollama `localhost` de 2,2 s, tracker au 1er accès |
| Cliquer sur un widget | Oui : rerun complet de la page | Même appel Ollama à chaque rerun |
| Premier accès | Non | Imports (6 s RAG), CodeCarbon (6 à 11 s) |

Conclusion : le modèle de rerun de Streamlit explique la **fréquence** des appels (à chaque interaction). Il n'explique pas leur **coût**. Les 2,2 s sont un défaut du back (nom d'hôte, aucun cache). Un front web à état local supprime la fréquence, pas le coût du back.

## Constats classés par gain estimé

| # | Constat | Fichier:ligne | Cause | Correctif proposé | Gain estimé | Effort |
|---|---|---|---|---|---|---|
| 1 | `localhost` = 2,05 s par client Ollama | `src/core/providers/ollama_provider.py:39` (`base_url="http://localhost:11434"`), `:193-200` | Résolution IPv6 d'abord, repli IPv4 après délai (Windows). Un nouveau client par appel | `127.0.0.1` par défaut (et dans l'hôte d'`OLLAMA_HOST` si `localhost`) ; un client réutilisé | -2,0 s par rerun d'Arène, Agents, Assistant doc. ; -2,0 s sur chaque `health_check`, `ps`, `is_model_loaded` | S |
| 2 | Aucun cache de la liste des modèles | `src/app/views/02_Inference_Arena.py:20`, `03_RAG_Knowledge.py:339`, `04_Agent_Lab.py:100`, `components/model_selector.py:37` | `list_models` rappelle `/api/tags` à chaque rerun, 3 vues, 4 sites. `model_menu` (classement, benchmark, `os` + JSON) recalculé aussi | `st.cache_data(ttl=10-30 s)` clé = `cloud_enabled`, invalidé après pull/suppression | -0,12 à -0,3 s par rerun (après #1), -2,2 s sans #1 | S |
| 3 | Tracker CodeCarbon bloquant au 1er accès | `src/app/Accueil.py:64-67`, `src/core/green_monitor.py:290-303` | `OfflineEmissionsTracker` appelle `cpuinfo.get_cpu_info()` (9 s, sous-processus) puis démarre 2 threads. Exécuté dans le fil de la session, avant tout rendu | Le démarrer dans un fil de fond, ou une fois par processus (`st.cache_resource`) ; fournir le CPU en cache disque | -6 à -11 s au 1er accès ; -1,3 s par nouvelle session | M |
| 4 | Imports lourds chargés au premier accès | `src/app/views/03_RAG_Knowledge.py:32` (rag_engine, 6,1 s), `04_Agent_Lab.py` (crew 4,1 s), `src/core/providers/provider_factory.py` (anthropic 1,06 s, openai 0,5 s) | `import` en tête de module ; providers cloud importés même sans clé | Imports différés (dans la fonction qui les utilise) ; précharger en fil de fond après le 1er rendu ; providers cloud importés seulement si une clé existe | -1,5 s au 1er accès au routeur ; -3 à -6 s à l'ouverture des pages RAG et Agents (déplacés, pas supprimés) | M |
| 5 | Moteur RAG, embeddings et évaluateur par session | `src/app/views/03_RAG_Knowledge.py:100-123` | `st.session_state.rag_engine = RAGEngine(...)` : un moteur, un client Chroma et un modèle d'embedding par session de navigateur | `st.cache_resource` (un moteur par processus) avec verrou d'écriture | -1 s et -0,3 à -0,5 Go par session supplémentaire | M |
| 6 | État d'Ollama : TTL 10 s, délai 2 s | `src/app/states.py:30,107`, `ollama_provider.py:28,202` | Après #1, le coût passe à 0,1 s. Avant #1, le contrôle dure 2,12 s pour un `timeout=2,0` : un hôte plus lent serait déclaré « Indisponible » à tort | #1 ; séparer délai de connexion et de lecture | Fiabilité, -2 s toutes les 10 s sur l'Accueil | S |
| 7 | `loaded_models_ram_gb` | `src/app/ui.py:144`, `ollama_provider.py:274` | `/api/ps` : 2,02 s, appelé une fois par session (`MEMORY_SNAPSHOT_KEY`) | #1 | -2 s au 1er accès à une page à sélecteur | S |
| 8 | `psutil.cpu_percent(interval=0.1)` bloquant | `src/app/home.py:30`, `views/01_Socle_Hardware.py:83` | Attend 100 ms à chaque rerun | `interval=None` après un 1er appel d'amorçage | -0,1 s par rerun (Accueil, Sobriété) | S |
| 9 | Plusieurs `asyncio.run` par rerun d'envoi | `tabs/inference/chat.py:209`, `lab.py:199`, `arena.py:488,615`, `rag/chat.py:243`, `rag/eval.py:336`, `core/rag/strategies/hyde.py:58`, `self_rag.py:197` | Une boucle d'événements neuve à chaque appel | Une boucle dédiée en fil de fond (ou génération `async` côté serveur) | Faible en temps, vrai gain de stabilité | M |

Ordre de gain cumulé estimé sur un parcours « ouvrir l'Arène puis changer de page » : de ≈ 2,2 s par changement à ≈ 0,2 s avec #1 et #2.

## Stabilité

| # | Constat | Fichier:ligne | Risque | Correctif |
|---|---|---|---|---|
| S1 | « Multiple instances of codecarbon » : un tracker par session de navigateur, plus un par mission d'équipe | `Accueil.py:64-67`, `tabs/agent/crew.py:494` | Chaque session ajoute 2 threads et un fichier CSV ouvert. Rien ne l'arrête à la fermeture de l'onglet : seul `atexit` (`green_monitor.py:292-301`) le fait. Écritures CSV concurrentes sur `data/logs/emissions.csv` | Un tracker par processus, partagé ; l'arrêter via `atexit` seulement ; un fichier ou un verrou par run |
| S2 | La clause `if "tracker" not in st.session_state` de `01_Socle_Hardware.py:165` est du code mort | `01_Socle_Hardware.py:165-167` | Le routeur crée toujours le tracker avant la page. Sans le routeur, le projet `AUDIT_PROJECT` n'est plus alimenté | Supprimer ou documenter |
| S3 | Exceptions avalées | 77 `except Exception` dans `src/` ; dont `Accueil.py` (import du tracker), `green_monitor.py:157-167` (GPU `pass`), `03_RAG_Knowledge.py:125-131` (`eval_engine = None` sans trace), `ollama_provider.py:65-90` (liste vide sur erreur) | Une panne d'Ollama se lit comme « aucun modèle » ; une panne d'EvalEngine désactive l'évaluation sans message | Journaliser avec trace, retourner un résultat typé (`ok`, `erreur`) |
| S4 | Fil de surveillance mémoire non rattaché | `tabs/agent/crew.py:497-506` | `threading.Thread(...).start()` sans `join` ni `daemon` ; boucle `time.sleep(0.5)` : si la mission lève une exception avant `stop_evt.set()`, le fil tourne jusqu'à la fin du processus | `daemon=True` + `try/finally` |
| S5 | État global partagé entre sessions | `provider_factory.py:51-56,252-258` (`LLMProviderFactory._instance`, `_providers` de classe), `benchmark_results._CACHE`, `GreenTracker._active_trackers` | Singletons de processus : sûrs en lecture, mais `register_provider` et `_active_trackers` sont modifiés sans verrou | Verrou, ou instances par requête |
| S6 | Écritures Chroma concurrentes | `src/core/rag/vector_store.py` (client persistant par moteur), 3 vues d'ingestion | Deux sessions = deux moteurs sur le même dossier `data/` : SQLite verrouillé, état d'une session invisible pour l'autre (déjà signalé dans AGENTS.md) | Un moteur par processus + file d'écriture |
| S7 | Fuite mémoire probable | `session_state` : `rag_engine`, `eval_engine`, `messages`, `lab_result`, `tracker` | Rien n'est libéré à la fermeture d'une session (Streamlit ne notifie pas la fin pour ces objets). Les trackers (2 threads chacun) et modèles d'embeddings s'accumulent | Ressources de processus (`cache_resource`), pas de session |
| S8 | `time.sleep` + `st.rerun` dans le fil de la page | `tabs/inference/chat.py:276-277`, `manager.py:100` | Bloque la session pendant le sommeil, rerun supplémentaire (donc nouvel appel Ollama à 2,2 s) | État + `st.fragment` |

## Gains rapides dans la v1 Streamlit (pour information)

À ne pas appliquer dans cette PR d'audit. Ordre conseillé :

1. `OllamaProvider` : `127.0.0.1` à la place de `localhost`, client conservé (S, -2,0 s par rerun). Vérifier avec `OLLAMA_HOST` et le test `test_inference_reelle_ollama`.
2. `@st.cache_data(ttl=15)` sur `list_models` et sur `model_menu` (S).
3. Imports de `anthropic` et `openai` différés, providers cloud chargés seulement avec une clé (S, -1,5 s).
4. Démarrage du tracker CodeCarbon dans un fil de fond et un seul par processus (M, -6 à -11 s).
5. `cpu_percent(interval=None)` (S, -0,1 s).
6. Page RAG : importer `rag_engine` seulement quand la base n'est pas vide, ou précharger en tâche de fond (M).

Attention : la PR de benchmark ne doit pas être touchée (`scripts/benchmark_slm.py`, `src/core/config.py`). Le changement #1 modifie `src/core/providers/` : à relire à l'aune de la règle AGENTS.md sur ce qu'importe le benchmark.

## Ce que la v2 doit éviter

| Contrainte | Pourquoi (mesure) |
|---|---|
| Aucun appel réseau dans le chemin de rendu d'une page ni dans un import | 2,2 s sur 2,2 s d'un rerun étaient un appel Ollama |
| Un client HTTP par processus, adresse `127.0.0.1` explicite ; tester Windows IPv6 dès le premier jour | Écart 2,17 s contre 0,11 s |
| Un seul service d'état d'Ollama (sondage en tâche de fond), exposé en lecture au front | La v1 relance le même appel depuis 4 sites |
| Modèles lourds (embeddings, torch, CrewAI, ragas) chargés dans un worker séparé, à la demande, avec file d'attente et message de progression | 6 s d'import et 0,5 Go de RSS bloquent la 1re requête de la v1 |
| Pas de suivi carbone dans le fil de requête ; mesure par run, démarrée par le worker | 6 à 11 s au premier accès, 2 threads par session |
| Ressources (Chroma, embeddings, trackers) rattachées au processus, jamais à la session | S5, S6, S7 |
| `py-cpuinfo` mis en cache sur disque ou remplacé (`psutil`, WMI) | 9 s pour lire le processeur |
| Providers cloud (`anthropic`, `openai`) importés seulement si une clé est configurée | 1,5 s d'imports sans usage |
| Écriture Chroma sérialisée par un seul processus ; lectures concurrentes autorisées | S6 |
| Journalisation structurée à la place des `except Exception: pass` ; résultats typés | S3 |
| Budget à tenir : changement de page < 150 ms hors appel de génération ; 1er rendu < 1 s ; démarrage de modèle signalé | Mesures de la v1 : 2,2 s et 6 à 14 s |
| Mesurer dès le début : `AppTest` ne suffit plus pour un front web ; prévoir une mesure navigateur (temps jusqu'au premier contenu) | `AppTest` exclut le rendu |

## Limites de l'audit

- Pas de mesure navigateur (transfert WebSocket, rendu).
- Assistant documentaire avec base non vide non mesuré (la base locale est vide) : son chaud est estimé à partir du même `list_models`.
- Pas de mesure sans Ollama (autre agent). Par lecture de code, tout ce qui dépend d'Ollama : `list_models`, `health_check`, `is_model_loaded`, `loaded_model_size_gb`, `loaded_models_ram_gb`, `pull_model`, `chat_stream`.
- La première mesure du tracker (11,5 s puis 6,5 s) varie avec le cache disque de `cpuinfo` : fourchette, pas valeur fixe.
