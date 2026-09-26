# Audit du frontend Streamlit : poste-rtx3060

- **Date** : 26 septembre 2026
- **Machine** : `poste-rtx3060` (RTX 3060 Laptop 6 Go, Ryzen 7 5800H, 32 Go, Windows 11)
- **Commit testé** : `d954bd67b0b10912ae9a4c8662c418c95e250ba4` (`master`, après la PR #13)
- **Méthode** : parcours pilotés par Playwright (Chromium headless) sur `http://localhost:8501`, relecture du code quand un écran se comportait bizarrement
- **Portée** : les 4 pages et leurs onglets. Seules les actions sans effet de bord durable ont été exercées : aucun téléchargement ni aucune suppression de modèle Ollama.

Ce rapport a un jumeau, rédigé en parallèle sur une autre machine, dans `docs/audits/frontend-2026-09/<machine>/`. Les deux ont vocation à être fusionnés avant l'implémentation (voir le §4).

L'audit UX et visuel (esthétique, accessibilité, cohérence, charte Wavestone) est dans [`UX.md`](UX.md). Il a été fait sur cette machine seulement, puisque le rendu ne dépend pas du matériel. Son §5 ajoute une étape `bmad-ux` et les stories 7 à 9 au plan ci-dessous.

## 1. Synthèse

Le frontend démarre, et la plupart des parcours marchent de bout en bout : chat, labo, arena, chat RAG, agent solo avec outils, équipe CrewAI.

Deux fonctions clés sont pourtant **cassées sans que l'utilisateur le voie** :

- **L'import de documents RAG est factice** : il affiche « Indexation terminée avec succès ! », mais n'indexe rien.
- **Le benchmark RAG renvoie toujours 0/100**, parce que Ragas ne s'importe plus.

S'y ajoutent une gestion des échecs d'inférence qui affiche des erreurs Python brutes, et un débit (t/s) qui n'est pas mesuré comme dans le benchmark.

| Page | Parcours | Résultat |
|---|---|---|
| Accueil | Affichage | ✅ |
| Socle Hardware | Métriques, historique CO₂, bouton Rafraîchir | ✅ (mais « CPU Only », voir F6) |
| Inférence | Chat libre (Gemma 3 1B) | ✅ « Paris », badges CO₂, débit et durée (débit faux au premier message, voir F4) |
| | Labo de tests (scénario par défaut) | ✅ JSON correct, 24,4 t/s, 0,66 s |
| | Arena et juge (Gemma 3 1B, Qwen 3.5 0.8B, Bonsai 8B, juge Llama 3.2 3B) | ✅ Verdict et matrice ; ❌ Bonsai 27B → `AttributeError` (F3) |
| | Gestion des modèles (lecture seule) | ✅ 25 modèles listés, filtres visibles |
| RAG | Import de documents | ❌ Factice (F1) |
| | Chat RAG (document ingéré via le moteur) | ✅ Réponse exacte, 1 source citée, export MD |
| | Benchmark & Qualité | ❌ 0/100 systématique (F2) |
| | Reset de la base | ✅ |
| Agent Lab | Solo (Qwen 3.5 4B) + calculatrice | ✅ 1234 × 5678 = 7 006 652, exact, en 14 s |
| | Solo, action rapide « Audit Système » | ✅ Rapport CPU, RAM et disque cohérent, en 23 s |
| | Crew (1 agent, Qwen 3.5 4B, mission par défaut) | ✅ Rapport structuré en 159 s |

## 2. Constats

Gravité : **bloquant** (on ne peut pas utiliser la fonction), **majeur** (la fonction ment ou plante), **moyen** (chiffre ou comportement trompeur), **mineur**, **cosmétique**.

### F0 — Le `.venv` du dépôt ne peut pas lancer le frontend · bloquant (environnement)

- **Constat** : `python -m streamlit` → `No module named streamlit`. Le `.venv` actuel (Python 3.14.4, 88 paquets) ne contient que les dépendances du benchmark. Le README demande pourtant d'installer `requirements.txt` dans `.venv`.
- **Contournement utilisé** : un second environnement, `.venv-app`, en Python 3.12.13, créé avec `uv venv --python 3.12` puis `uv pip install -r requirements.txt`. Il est ignoré par git (modification du `.gitignore` incluse dans cette PR). Le choix de la 3.12 est prudent : CrewAI et ChromaDB ne sont pas garantis sous 3.14.
- **Aggravant** : `requirements.txt` ne fixe aucune borne haute, et plusieurs paquets y sont listés deux fois (`chromadb`, `openpyxl`, `ragas`, `python-docx`…). Une installation faite aujourd'hui ne reproduit donc pas celle d'il y a six mois (voir F2).

### F1 — L'import de documents RAG est factice · bloquant

- **Où** : `src/app/pages/03_RAG_Knowledge.py:100-117`, fonction `open_knowledge_manager()`
- **Constat** : l'appel réel est commenté (`# rag_engine.ingest(file)`) et remplacé par `time.sleep(0.5)  # Fake work pour la démo UX`, puis `st.success("✅ Indexation terminée avec succès !")`. La base reste à 0 chunk et la page reste sur l'écran « base vide ». Ce code a été introduit par `f056a4f` (« Review Mistral carbon measure + full UI/UX »).
- **Conséquence** : les onglets « Discussion » et « Benchmark & Qualité » sont **inatteignables** depuis l'interface sur une base vide.
- **Le moteur, lui, fonctionne** : `RAGEngine.ingest_file(path, filename)` a indexé le fichier de test (1 chunk), et la recherche le retrouve. Il suffit de le brancher, en écrivant le `UploadedFile` dans un fichier temporaire, puisque le pipeline attend un chemin.
- **Reproduire** : `playwright/t_rag_upload.py` ; captures `captures/rag_upload_success.png` et `captures/rag_after_upload.png`.

### F2 — Le benchmark RAG échoue en silence (0/100) · majeur

- **Cause 1 (environnement)** : `from ragas import evaluate` lève `ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'`. En effet, `ragas 0.4.3` importe un module retiré de `langchain-community 0.4.2`. `src/core/eval_engine.py:6-13` intercepte l'`ImportError` et passe `RAGAS_AVAILABLE = False`.
- **Cause 2 (code)** : l'onglet n'affiche l'avertissement « Ragas n'est pas installé » que si `EvalEngine()` échoue à l'instanciation (`src/app/tabs/rag/eval.py:40`), ce qui n'arrive jamais. `evaluate_single_turn()` renvoie alors `EvalResult(0.0, 0.0, 0.0)` (`eval_engine.py:50-51`), et l'écran affiche « ✅ Benchmark Terminé ! » avec un score global de 0/100, en 4 s.
- **Reproduire** : `playwright/t_rag_eval.py` ; capture `captures/rag_eval_run.png`.
- **À trancher** : fixer des versions compatibles, soit une version de `ragas` qui ne passe plus par Vertex AI, soit `langchain-community` < 0.4. Il faudra vérifier que le reste de la pile LangChain 1.x suit, et distinguer « non évalué » de « évalué à 0 ».

### F3 — Un échec d'inférence s'affiche comme une erreur Python · majeur

- **Constat** : dans l'Arena, Bonsai 27B dépasse le délai de 120 s (log : `Timeout (120s) dépassé pour bonsai:27b-q1_0`). L'écran affiche `❌ KO Bonsai 27B (1-bit): 'NoneType' object has no attribute 'output_tokens'`.
- **Cause** : `InferenceService.run_inference()` ne lève pas d'exception. Il renvoie un `InferenceResult` avec `metrics=None` et `error="Timeout..."` (`src/core/inference_service.py:105-120`). Or `arena.py:212-223`, `lab.py:148-159` et `chat.py:26-31` lisent `m.output_tokens` sans tester `result.error`.
- **Portée** : reproduit dans l'Arena. Le motif est identique dans le Labo et le Chat, mais je ne l'y ai pas reproduit. Les onglets RAG testent déjà `if metrics_obj:`.
- **Aggravant** : l'Arena présélectionne justement Bonsai 27B et Bonsai 8B (F5). Un clic sur « FIGHT ! » avec les valeurs par défaut produit donc ce plantage sur une machine à 6 Go.

### F4 — Le débit affiché inclut le chargement du modèle · moyen

- **Où** : `src/core/providers/ollama_provider.py:136-138`, où `tokens_per_second = eval_count / duration`, avec `duration` = chrono client total
- **Constat** : premier message du Chat sur Gemma 3 1B, **0,6 t/s** pour 16,5 s ; le même modèle, déjà chargé, fait **78,5 t/s** dans l'Arena. Le chrono inclut le chargement du modèle et le prefill.
- **Incohérence** : `scripts/benchmark_slm.py:1601-1620` mesure le débit sur `eval_duration`, renvoyé par Ollama. Les chiffres de l'interface ne sont donc pas comparables à ceux du benchmark publiés dans `benchmarks/results/`.
- **Piste** : Ollama renvoie déjà `eval_duration`, `prompt_eval_duration` et `load_duration` dans le dernier chunk. `load_duration` est lu, mais seulement affiché.

### F5 — Valeurs par défaut inadaptées à la machine · moyen

- Chat, Labo, Agent solo, Crew, et les candidats du benchmark RAG sélectionnent par défaut le **premier modèle par ordre alphabétique**, soit Bonsai 27B (1-bit), 26,9B paramètres. L'Arena prend les deux premiers (Bonsai 27B et 8B).
- Le juge par défaut de l'Arena cherche « mistral » ou « llama », et celui du benchmark RAG « mistral », « gpt » ou « large ». Sans cloud actif, le premier retombe sur Llama 3.2 3B, et le second sur l'index 0, donc Bonsai 27B.
- Sur 6 Go de VRAM, un modèle au-delà de ~4 Go d'empreinte déborde sur le CPU et perd un facteur 3 à 5 (mesures du benchmark). Un choix par défaut guidé par `models.json`, par exemple le plus rapide qui tient en VRAM, éviterait F3 dès le premier clic.

### F6 — Socle Hardware affiche « CPU Only » sur une machine avec GPU · mineur

- **Où** : `src/app/pages/01_Socle_Hardware.py:30-38`, qui détecte via `torch.cuda.is_available()`
- **Constat** : `pip`/`uv` installent la roue torch CPU par défaut sous Windows (`torch 2.14.0+cpu`). La page annonce donc « Actif · CPU Only », alors qu'Ollama tourne bien sur le GPU. La détection devrait passer par NVML, comme `green_monitor.py` avec GPUtil, ou interroger Ollama.

### F7 — Deux collections Chroma pour le même embedding · mineur

- `RAGEngine()` a pour défaut `all-MiniLM-L6-v2`, ce qui donne la collection `wavelocal_all_MiniLM_L6_v2`. La page RAG utilise `sentence-transformers/all-MiniLM-L6-v2`, ce qui donne la collection `wavelocal_sentence_transformers_all_MiniLM_L6_v2`.
- Tout script ou test qui instancie `RAGEngine()` sans argument écrit donc dans une collection que l'interface ne lit pas. Je suis tombé dans le piège pendant l'audit.

### F8 — Défauts visuels · cosmétique

- Le titre « Votre base de connaissances est vide » est un `<h2>` en couleur de thème sombre sur l'encart `#2b2b3b` : il est quasi illisible (`captures/rag_after_upload.png`).
- Le bouton « 📂 📂 Gérer les Documents » affiche deux fois l'icône, car `icon="📂"` s'ajoute à l'emoji du libellé.

### Observations non retenues comme bugs

- **Chroma entre processus** : une écriture faite par un autre processus n'est pas vue par un serveur Streamlit déjà démarré, et une collection créée vide puis remplie ailleurs lève `Error creating hnsw segment reader: Nothing found on disk`. C'est sans effet en usage normal, où l'ingestion se fait dans le même processus, mais c'est un **piège pour les tests e2e** : il faut ingérer via l'interface, ou redémarrer le serveur.
- **Badge « 💾 0.0 GB »** sous les réponses du chat RAG : non investigué.
- **Qwen 3.5 0.8B à 771 mg CO₂** dans l'Arena, contre ~100 mg pour les autres : c'est probablement un raisonnement très long (le CO₂ local est proportionnel aux tokens), non vérifié.
- La liste déroulante des modèles est virtualisée (11 options visibles sur 25). Ce n'est pas un bug, mais les tests doivent taper pour filtrer.

## 3. Environnement de test

| Élément | Version |
|---|---|
| Python (`.venv-app`) | 3.12.13 (uv) |
| streamlit | 1.64.0 |
| langchain / langchain-core / langchain-community | 1.4.2 / 1.6.5 / 0.4.2 |
| langchain-ollama / ollama (client) | 1.1.0 / 0.6.2 |
| ragas / datasets | 0.4.3 / 5.0.1 |
| chromadb / langchain-chroma | 1.1.1 / 1.0.0 |
| crewai | 1.15.22 |
| sentence-transformers / torch | 6.1.0 / 2.14.0+cpu |
| Ollama (serveur) | 0.34.2 |
| playwright | 1.63.0 |

**Rejouer les parcours**, depuis la racine du dépôt, serveur lancé avec `.venv-app/Scripts/python -m streamlit run src/app/Accueil.py --server.headless true` :

```bash
P=docs/audits/frontend-2026-09/poste-rtx3060/playwright
mkdir -p $P/shots
PYTHONIOENCODING=utf-8 .venv-app/Scripts/python $P/smoke.py $P/shots     # toutes les pages
PYTHONIOENCODING=utf-8 .venv-app/Scripts/python $P/t_inference.py $P     # labo, arena, gestion (+ 'chat')
PYTHONIOENCODING=utf-8 .venv-app/Scripts/python $P/t_rag_upload.py $P    # F1
PYTHONIOENCODING=utf-8 .venv-app/Scripts/python $P/t_agent_solo.py $P
PYTHONIOENCODING=utf-8 .venv-app/Scripts/python $P/t_agent_crew.py $P    # ~3 min
```

`t_rag_chat.py` et `t_rag_eval.py` supposent que `doc_test_rag.txt` a été ingéré dans la collection de l'interface, puis que le serveur a été redémarré (voir F7 et l'observation sur Chroma). `t_cleanup.py` vide la base par le bouton Reset. Ces scripts sont des outils d'audit, pas encore une suite de tests : c'est la story S6.

## 4. Plan d'implémentation (BMAD 6.12)

### 4.1 Déroulé

BMAD n'est pas encore installé dans ce dépôt. La version de référence est la 6.12.0, déjà en place dans `agentic-harness-training-demo-cloud`. Le plan suit sa chaîne courte : `bmad-spec` → `bmad-build` par story → `bmad-code-review`, puis `bmad-qa-generate-e2e-tests`. Un PRD et une architecture seraient disproportionnés pour une série de correctifs sur un existant.

| Étape | Qui / quoi | Entrée | Sortie |
|---|---|---|---|
| 0 | Installer BMAD 6.12 (`npx bmad-method install`), puis `bmad-project-context` pour poser le bloc AGENTS.md du dépôt | — | `_bmad/`, `AGENTS.md` |
| 1 | **Fusion des audits**, hors BMAD : dédoublonner les constats des deux machines, garder la gravité la plus haute, conserver les deux reproductions | `docs/audits/frontend-2026-09/*/RAPPORT.md` | `docs/audits/frontend-2026-09/SYNTHESE.md` |
| 1 bis | `bmad-ux` : produire `DESIGN.md` et `EXPERIENCE.md` à partir de `UX.md` | `UX.md`, `SYNTHESE.md` | `DESIGN.md`, `EXPERIENCE.md` (*companions* de la spec) |
| 2 | `bmad-spec` : créer la spec `fiabilisation-frontend`, puis *Story Breakdown* | `SYNTHESE.md` | `SPEC.md` (CAP-1…), `stories.yaml` |
| 3 | `bmad-build`, une story à la fois, une branche et une PR par story | story + `SPEC.md` | code, tests, PR |
| 4 | `bmad-code-review` sur chaque PR avant fusion | diff | constats triés |
| 5 | `bmad-qa-generate-e2e-tests` à partir des scripts `playwright/` | parcours validés | suite `tests/e2e/` |
| 6 | Optionnel : `bmad-retrospective` en fin de série | — | leçons |

### 4.2 Capacités proposées pour `SPEC.md`

- **CAP-1 Installation reproductible du frontend** — *intent* : un environnement créé à neuf lance toutes les pages avec toutes leurs fonctions. *Success* : `uv venv --python 3.12` + installation des dépendances → Streamlit démarre et `import ragas` réussit (F0, F2 cause 1).
- **CAP-2 Ingestion RAG réelle** — *intent* : un document importé depuis l'interface est indexé et interrogeable. *Success* : upload d'un `.txt` → compteur > 0 → la question du document de test obtient la bonne réponse avec sa source (F1, F7).
- **CAP-3 Échecs visibles** — *intent* : aucun échec d'inférence ou d'évaluation n'est présenté comme un succès ni comme une trace Python. *Success* : un timeout affiche « Timeout (120 s) » et l'Arena continue avec les autres modèles ; une évaluation impossible affiche « non évalué », pas 0/100 (F2 cause 2, F3).
- **CAP-4 Débit comparable au benchmark** — *intent* : le t/s affiché mesure la génération seule, comme `benchmark_slm.py`. *Success* : le premier message après chargement affiche un débit proche des messages suivants (±15 %), et le temps de chargement est affiché à part (F4).
- **CAP-5 Défauts adaptés à la machine** — *intent* : un utilisateur qui ne touche à rien obtient une démo rapide. *Success* : sur `poste-rtx3060`, aucun modèle présélectionné ne dépasse ~4 Go d'empreinte, et la page Hardware affiche le GPU (F5, F6, F8).

**Contraintes à porter** : ne pas modifier le `.venv` du benchmark ni `scripts/benchmark_slm.py` ; tests unitaires sans Ollama (mocks) ; aucun téléchargement de modèle dans les tests.
**Non-objectifs** : refonte visuelle, ajout de formats d'import, mode cloud.

### 4.3 Stories proposées pour `stories.yaml`

Ordre d'exécution de haut en bas. Chaque story vise un seul objectif livrable en une PR, conformément au *Scope Standard* de `bmad-build`.

| id | Titre | Constats | `spec_checkpoint` | `done_checkpoint` | Note pour `invoke_dev_with` |
|---|---|---|---|---|---|
| 1 | Environnement frontend reproductible | F0, F2 (cause 1) | **oui** : choisir entre fixer `ragas` ou `langchain-community`, et entre `requirements-app.txt` et un fichier de contraintes | non | Partir des versions du §3, qui marchent sauf Ragas. Documenter `.venv-app` dans le README et `docs/TROUBLESHOOT.md`. |
| 2 | Brancher l'ingestion RAG sur le moteur | F1, F7 | non | **oui** : démo manuelle d'un PDF réel | `UploadedFile` → fichier temporaire → `rag_engine.ingest_file`. Aligner le nom d'embedding par défaut de `RAGEngine` sur celui de la page. Afficher le nombre de chunks réellement ajoutés. |
| 3 | Rendre visibles les échecs d'inférence et d'évaluation | F2 (cause 2), F3 | non | non | Tester `result.error` avant `result.metrics` dans chat, lab et arena. `EvalResult` doit pouvoir porter « non évalué ». Ajouter des tests unitaires avec un `InferenceResult` en erreur. |
| 4 | Mesurer le débit sur `eval_duration` | F4 | **oui** : valider la définition avec `docs/METHODOLOGIE_CARBONE.md` | non | Même formule que `benchmark_slm.py`. Garder la durée totale et le temps de chargement comme métriques séparées. |
| 5 | Valeurs par défaut et affichage matériel | F5, F6, F8 | non | non | Choisir le défaut via `models.json` (empreinte ≤ VRAM disponible, le plus rapide). Détecter le GPU via NVML. `bmad-build` peut proposer de scinder si la spec dépasse 1 600 tokens. |
| 6 | Suite e2e Playwright de non-régression | tous | non | **oui** | Passer par `bmad-qa-generate-e2e-tests` plutôt que `bmad-build`. Ingérer via l'interface (piège Chroma). Petits modèles uniquement (Gemma 3 1B, Qwen 3.5 4B). Marqueur `e2e` exclu de la CI par défaut, car il faut Ollama. |

Les stories 2 et 3 dépendent de la 1 : sans Ragas importable, on ne peut pas distinguer « non évalué » d'« évalué ». Les stories 4 et 5 sont indépendantes et peuvent passer en parallèle.

### 4.4 Pour la fusion avec l'autre machine

- Les identifiants `F0`–`F8` sont **locaux à ce rapport**. La synthèse les renumérote et garde une table de correspondance (`poste-rtx3060:F3` ↔ `<autre>:Fx`).
- Un constat vu sur une seule machine reste dans la synthèse, avec sa machine d'origine. Certains, comme F5 et F6, dépendent du matériel ou de la roue torch installée.
- En cas de désaccord sur une cause, garder les deux hypothèses et marquer le point comme question ouverte dans `bmad-spec`, qui la reportera dans `open_questions`.
