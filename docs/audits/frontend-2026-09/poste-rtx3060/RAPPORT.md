# Audit du frontend Streamlit : poste-rtx3060

- **Date** : 26 septembre 2026
- **Machine** : `poste-rtx3060` (RTX 3060 Laptop 6 Go, Ryzen 7 5800H, 32 Go, Windows 11)
- **Commit testé** : `d954bd67b0b10912ae9a4c8662c418c95e250ba4` (`master`, après la PR #13)
- **Méthode** : parcours pilotés par Playwright (Chromium headless) sur `http://localhost:8501`, relecture du code quand un écran se comportait bizarrement
- **Portée** : les 4 pages et leurs onglets. Seules les actions sans effet de bord durable ont été exercées : aucun téléchargement ni aucune suppression de modèle Ollama.

Ce rapport a un jumeau, rédigé en parallèle sur une autre machine, dans `docs/audits/frontend-2026-09/<machine>/`. Les deux ont vocation à être fusionnés avant l'implémentation (voir le §4.5).

L'audit UX et visuel (esthétique, accessibilité, cohérence, charte Wavestone) est dans [`UX.md`](UX.md). Il a été fait sur cette machine seulement, puisque le rendu ne dépend pas du matériel. Le plan de remédiation du §4 couvre les deux audits.

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

## 4. Plan de remédiation (BMAD 6.12)

Ce plan couvre **l'ensemble des constats** : ceux de ce rapport (F0–F8, fonctionnels) et ceux de [`UX.md`](UX.md) (U1–U18, design, accessibilité, rédaction). La table du §4.4 vérifie qu'aucun n'est oublié.

### 4.1 Déroulé

BMAD n'est pas encore installé dans ce dépôt. La version de référence est la 6.12.0, déjà en place dans `agentic-harness-training-demo-cloud`. Le plan suit sa chaîne courte, complétée par l'étape UX : `bmad-ux` → `bmad-spec` → `bmad-build` par story → `bmad-code-review`. Un PRD et une architecture seraient disproportionnés pour des correctifs sur un existant.

| Étape | Qui / quoi | Entrée | Sortie |
|---|---|---|---|
| 0 | Installer BMAD 6.12 (`npx bmad-method install`), puis `bmad-project-context` pour poser le bloc AGENTS.md du dépôt | — | `_bmad/`, `AGENTS.md` |
| 1 | **Fusion des audits**, hors BMAD : dédoublonner les constats des deux machines, garder la gravité la plus haute, conserver les deux reproductions | `docs/audits/frontend-2026-09/*/RAPPORT.md` et `UX.md` | `docs/audits/frontend-2026-09/SYNTHESE.md` |
| 2 | `bmad-ux` : fixer le thème, les *tokens*, les icônes, le lexique et les états (vide, erreur, confirmation) | `UX.md` (§4 direction de design), `SYNTHESE.md` | `DESIGN.md`, `EXPERIENCE.md` |
| 3 | `bmad-spec` : créer la spec `fiabilisation-frontend` avec `DESIGN.md` et `EXPERIENCE.md` en *companions* adoptés, puis *Story Breakdown* | `SYNTHESE.md`, `DESIGN.md`, `EXPERIENCE.md` | `SPEC.md` (CAP-1 à CAP-7), `stories.yaml` |
| 4 | `bmad-build`, une story à la fois, une branche et une PR par story | story + `SPEC.md` | code, tests, PR |
| 5 | `bmad-code-review` sur chaque PR avant fusion | diff | constats triés |
| 6 | `bmad-qa-generate-e2e-tests` pour la story 10 | scripts `playwright/` | suite `tests/e2e/` |
| 7 | Optionnel : `bmad-retrospective` en fin de série | — | leçons |

### 4.2 Capacités proposées pour `SPEC.md`

- **CAP-1 Installation reproductible du frontend** — *intent* : un environnement créé à neuf lance toutes les pages avec toutes leurs fonctions. *Success* : `uv venv --python 3.12` + installation des dépendances → Streamlit démarre et `import ragas` réussit.
- **CAP-2 Ingestion RAG réelle** — *intent* : un document importé depuis l'interface est indexé et interrogeable. *Success* : upload d'un `.txt` → compteur > 0 → la question du document de test obtient la bonne réponse avec sa source.
- **CAP-3 Échecs visibles, états vrais** — *intent* : aucun échec n'est présenté comme un succès ni comme une trace Python, et aucun indicateur n'est écrit en dur. *Success* :
  - un timeout affiche « Timeout (120 s) » et l'Arena continue ;
  - une évaluation impossible affiche « non évalué », pas 0/100 ;
  - Ollama arrêté fait passer l'accueil à « Indisponible ».
- **CAP-4 Débit comparable au benchmark** — *intent* : le t/s affiché mesure la génération seule, comme `benchmark_slm.py`. *Success* : le premier message après chargement affiche un débit à ±15 % des suivants, et le temps de chargement est affiché à part.
- **CAP-5 Défauts adaptés à la machine** — *intent* : un utilisateur qui ne touche à rien obtient une démo rapide. *Success* : sur `poste-rtx3060`, aucun modèle présélectionné ne dépasse ~4 Go d'empreinte, et la page Hardware affiche le GPU.
- **CAP-6 Interface à la charte, accessible et cohérente** — *intent* : l'interface ressemble à Wavestone et se lit sans effort. *Success* :
  - zéro violation axe `color-contrast` ou `heading-order`, en clair comme en sombre ;
  - un seul nom par module et par commande ;
  - des formats `fr-FR` ;
  - aucun emoji décoratif.
- **CAP-7 Souveraineté visible, actions sensibles maîtrisées** — *intent* : l'utilisateur sait ce qui sort de la machine et valide ce qui est irréversible. *Success* :
  - mode local par défaut ;
  - un badge Local ou Cloud sur chaque modèle et chaque réponse ;
  - envoi d'email et suppression de la base soumis à confirmation.

**Contraintes à porter** :
- ne pas modifier le `.venv` du benchmark ni `scripts/benchmark_slm.py` ;
- tests unitaires sans Ollama (mocks) ;
- aucun téléchargement de modèle dans les tests ;
- pas de framework CSS : on passe par `config.toml` et les composants natifs ;
- polices servies localement, pas de CDN.

**Non-objectifs** : ajout de formats d'import, nouvelles fonctionnalités d'agent, refonte de l'architecture des pages.

### 4.3 Stories proposées pour `stories.yaml`

Ordre d'exécution de haut en bas.
- **Les stories 1 à 3 sont transverses** : environnement, thème, libellés. Elles touchent toutes les pages. Les passer en premier évite que chaque correctif fonctionnel soit retouché deux fois, et que les PR se marchent dessus.
- **Les stories 4 à 9** touchent souvent les mêmes fichiers (`arena.py`, `chat.py`, les pages). Mieux vaut donc les enchaîner que les paralléliser.

| id | Titre | Constats | Taille | `spec_checkpoint` | `done_checkpoint` | Note pour `invoke_dev_with` |
|---|---|---|---|---|---|---|
| 1 | Environnement frontend reproductible | F0, F2 (cause 1) | S | **oui** : fixer `ragas` ou `langchain-community` ; `requirements-app.txt` ou fichier de contraintes | non | Partir des versions du §3, qui marchent sauf Ragas. Documenter `.venv-app` dans le README et `docs/TROUBLESHOOT.md`. |
| 2 | Thème Wavestone, icônes et accessibilité | U1–U7, U18, F8 | L | **oui** : valider la maquette issue de `bmad-ux` | **oui** : revue visuelle en clair et en sombre | Créer `.streamlit/config.toml` (ébauche en `UX.md` §4). Ajouter `st.logo`, et `toolbarMode = "viewer"`. Remplacer les emojis par des icônes Material. Supprimer les hex en dur (encart « base vide »). Rendre visible la rangée d'outils de l'agent. Nommer le bouton de la corbeille. |
| 3 | Vocabulaire et rédaction unifiés | U8, U9, U10 | M | **oui** : valider le lexique d'`EXPERIENCE.md` | non | Un nom par module, identique dans le menu, la carte, le titre et l'onglet. Outils de l'agent en français. Utilitaire de formats `fr-FR` (nombres, unités, dates). Accorder les pluriels. |
| 4 | Brancher l'ingestion RAG sur le moteur | F1, F7 | M | non | **oui** : démo manuelle d'un PDF réel | `UploadedFile` → fichier temporaire → `rag_engine.ingest_file`. Aligner le nom d'embedding par défaut de `RAGEngine` sur celui de la page. Afficher le nombre d'extraits réellement ajoutés. |
| 5 | Échecs visibles et état de santé réel | F2 (cause 2), F3, U11 | M | non | non | Tester `result.error` avant `result.metrics` dans chat, labo et arena. `EvalResult` doit pouvoir porter « non évalué ». Brancher l'indicateur « Système » sur `LLMProvider.health_check()`. Tests unitaires avec un `InferenceResult` en erreur. |
| 6 | Valeurs par défaut adaptées à la machine | F5, F6 | M | non | non | Choisir le défaut via `models.json` (empreinte ≤ VRAM disponible, le plus rapide), pour le chat, le labo, l'arena, les juges et les candidats RAG. Détecter le GPU via NVML, pas via torch. |
| 7 | Souveraineté visible et actions sensibles | U12, U13, U14, U15 | M | **oui** : décisions produit (cloud par défaut, outil email) | non | Cloud désactivé par défaut et badge Local/Cloud. Deltas de `st.metric` remplacés par des légendes ou `st.badge`. Outil email décoché par défaut, avec confirmation humaine avant l'envoi. Confirmation avant le Reset de la base. |
| 8 | Mesurer le débit sur `eval_duration` | F4 | S | **oui** : valider la définition avec `docs/METHODOLOGIE_CARBONE.md` | non | Même formule que `benchmark_slm.py`. Durée totale et temps de chargement affichés à part. |
| 9 | Graphiques lisibles et justes | U16, U17 | M | non | non | Suivre le skill `dataviz`. Historique : vrai cumul ou barres par session, en mg, trous visibles, fenêtre de temps. Arena : légende de taille et vue tableau. Benchmark RAG : même échelle que le podium (/100). Palette via `chartCategoricalColors`. |
| 10 | Suite e2e Playwright et accessibilité | tous | L | non | **oui** | Passer par `bmad-qa-generate-e2e-tests`. Ingérer via l'interface (piège Chroma). Petits modèles uniquement (Gemma 3 1B, Qwen 3.5 4B). axe-core en clair et en sombre, en ignorant `region` et `aria-allowed-attr` sur `.stSidebar`. Marqueur `e2e` exclu de la CI par défaut, car il faut Ollama. |

**Tailles** : S (≤ ½ journée), M (~1 journée), L (1 à 2 journées), avec revue comprise.

**Dépendances** :
- 2 et 3 dépendent de 1 ;
- 4 à 9 dépendent de 2 et 3 (thème et lexique en place) ;
- 5 dépend de 1 (Ragas importable) ;
- 10 vient en dernier.

**Si le temps manque**, l'ordre de valeur est : 1, 4, 5 (le front ne ment plus et le RAG marche) → 7, 2 (confiance, image) → 3, 6, 9 → 8, 10.

### 4.4 Couverture des constats

| Constat | Story | Constat | Story | Constat | Story |
|---|---|---|---|---|---|
| F0 | 1 | U1 | 2 | U10 | 3 |
| F1 | 4 | U2 | 2 | U11 | 5 |
| F2 | 1, 5 | U3 | 2 | U12 | 7 |
| F3 | 5 | U4 | 2 | U13 | 7 |
| F4 | 8 | U5 | 2 | U14 | 7 |
| F5 | 6 | U6 (= F8) | 2 | U15 | 7 |
| F6 | 6 | U7 | 2 | U16 | 9 |
| F7 | 4 | U8 | 3 | U17 | 9 |
| F8 | 2 | U9 | 3 | U18 | 2 |

**Restent hors plan, comme questions ouvertes pour `bmad-spec`** : le badge « 💾 0.0 GB » du chat RAG, et les 771 mg CO₂ de Qwen 3.5 0.8B dans l'Arena (§2, observations).

### 4.5 Pour la fusion avec l'autre machine

- Les identifiants `F0`–`F8` et `U1`–`U18` sont **locaux à ce rapport**. La synthèse les renumérote et garde une table de correspondance (`poste-rtx3060:F3` ↔ `<autre>:Fx`).
- Un constat vu sur une seule machine reste dans la synthèse, avec sa machine d'origine. Certains, comme F5 et F6, dépendent du matériel ou de la roue torch installée.
- `UX.md` n'a pas de jumeau : le rendu ne dépend pas de la machine. Ses constats entrent tels quels dans la synthèse.
- En cas de désaccord sur une cause, garder les deux hypothèses et marquer le point comme question ouverte dans `bmad-spec`, qui la reportera dans `open_questions`.
