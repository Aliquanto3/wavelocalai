---
title: 'Socle : installation figée, serveur local, CI active, tests au vert'
type: 'chore'
created: '2026-09-27'
status: 'done'
baseline_revision: 'e3f684f679c27356d0c8c9bd44e1e1a56abd42b8'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
warnings: []
deferred:
  - summary: >-
      scripts/benchmark_slm.py importe `from mistralai import Mistral`, qui échoue avec mistralai 2.10.1 figé.
    evidence: |-
      ImportError constaté dans .venv-app ; MISTRAL_AVAILABLE passe à False sans alerte.
    location: >-
      scripts/benchmark_slm.py:59
    severity: medium
  - summary: >-
      AGENTS.md est périmé (CI sur main/develop, 4 tests en échec, commandes d'installation).
    evidence: |-
      La story active la CI sur master, répare les 4 tests et introduit constraints.txt.
    location: >-
      AGENTS.md
    severity: medium
  - summary: >-
      La suite de tests écrit encore dans data/ (dossiers créés par config.py, logs créés par l'import de benchmark_slm.py).
    evidence: |-
      Un fichier data/logs/benchmarks/benchmark_<horodatage>.log apparaît à chaque run ; data/chroma reste vide.
    location: >-
      src/core/config.py:21 ; scripts/benchmark_slm.py:67
    severity: low
---

<intent-contract>

## Intent

**Problem:** L'installation n'est pas reproductible (aucune version figée, doublons, `import ragas` cassé avec `langchain-community` 0.4.2), le serveur Streamlit s'annonce sur le réseau, la CI ne se déclenche jamais (branches `main`/`develop`), et `tests/unit` a 9 échecs dans un environnement sans Ollama ni `data/` (4 connus E3 + 5 de `test_models_db.py` qui lisent le `data/models.json` local). Aucun banc `AppTest` n'existe pour les pages.

**Approach:** Figer les versions dans un fichier de contraintes universel généré par `uv pip compile` et vérifié par une installation réelle ; `.streamlit/config.toml` avec `server.address = "localhost"` ; banc `tests/app/` avec `AppTest` et providers simulés ; réparer les tests en corrigeant cible, données ou marqueur ; CI active sur `master`.

## Boundaries & Constraints

**Always:** versions vérifiées par installation réelle dans `.venv-app` (aucune de mémoire) ; `import ragas` réussit ; les tests tournent sans Ollama, clé d'API, réseau ni téléchargement ; les tests redirigent Chroma et CodeCarbon vers `tmp_path` ; marqueur `e2e` déclaré et exclu par défaut ; textes et docs en français.

**Never:** modifier `scripts/benchmark_slm.py`, `benchmarks/`, `src/core/config.py` ou le `.venv` du benchmark ; affaiblir, sauter ou supprimer une assertion ; écrire dans `data/chroma` ; rendre le lint bloquant ; toucher au thème (story 2) ou aux libellés (story 3).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Installation neuve | `uv pip install -r requirements.txt -c constraints.txt` sur Python 3.12 | Réussit ; `import ragas` et `import streamlit` réussissent | — |
| Démarrage | `streamlit run src/app/Accueil.py` | Seule une URL `localhost` est annoncée, pas d'« External URL » | — |
| Pages sans Ollama | `AppTest` sur les 5 pages, providers simulés | Aucune exception, un titre rendu par page | — |
| Tests sans `data/models.json` | `pytest tests/unit tests/app` | 0 échec ; `test_models_db` lit un catalogue de test | — |
| Ouverture réseau voulue | `--server.address 0.0.0.0` | Documenté comme un choix explicite dans le README | — |

</intent-contract>

## Code Map

- `requirements.txt` -- doublons (sentence-transformers, chromadb, pypdf, python-docx, openpyxl ×3, ragas, datasets, huggingface-hub, langchain-chroma/-huggingface, py-cpuinfo) ; exclure `langchain-community==0.4.2` (ragas 0.4.3 importe `langchain_community.chat_models.vertexai`, retiré en 0.4.2 ; 0.4.1 vérifié OK) ; ajouter `pytest-mock`.
- `constraints.txt` (nouveau) -- sortie de `uv pip compile requirements.txt --universal --python-version 3.10` : Python 3.10–3.12, toutes plateformes (marqueurs). Streamlit 1.64.0 : sa source (`streamlit/config.py`) expose `theme.light`/`theme.dark`, `chartCategoricalColors`, `baseRadius`, `fontFaces`, `headingFont`, `client.toolbarMode`, et `st.badge` existe — ce que DESIGN.md exige.
- `src/core/providers/mistral_provider.py:18-24` -- `from mistralai import Mistral` échoue avec mistralai 2.x (classe déplacée dans `mistralai.client`) : repli d'import. Non importé par le benchmark.
- `.streamlit/config.toml` (nouveau) -- `[server] address = "localhost"`, `[browser] gatherUsageStats = false`. Le thème viendra en story 2.
- `pytest.ini` -- prime sur `pyproject.toml` ; ajouter le marqueur `e2e` et `-m "not e2e"` dans `addopts`.
- `tests/unit/test_inference_service.py:286-305` -- `test_inference_reelle_ollama` (déjà `integration`) → déplacé dans `tests/integration/`.
- `tests/unit/test_llm_provider.py:150-193` -- patchent `src.core.model_detector.is_api_model`, alors que `llm_provider` et `provider_factory` l'importent par nom ; patcher `LLMProvider._is_mistral_api_model`, `provider_factory.is_api_model`, `ChatMistralAI` dans `langchain_mistralai`, et remettre à `None` `LLMProviderFactory._instance` (singleton de classe) en plus de `_factory`.
- `tests/unit/test_models_db.py` -- `MODELS_DB` est chargé à l'import depuis `data/models.json` (vide dans la VM) : fixture autouse qui remplit le dict en place depuis `tests/fixtures/models_catalog_test.json`, puis le restaure.
- `tests/unit/test_green_monitor.py` -- écrit `data/logs/emissions.csv` : rediriger `src.core.green_monitor.LOGS_DIR` vers `tmp_path`.
- `src/app/Accueil.py`, `src/app/pages/0[1-4]_*.py` -- `LLMProvider.list_models` (Arène, Agents), `RAGEngine` → `RAGModelsFactory.get_embedding_model` (télécharge depuis HF : 403 dans la VM), `vector_store.CHROMA_DIR`, `GreenTracker` → `green_monitor.LOGS_DIR`. Agent Lab lève `KeyError: None` sans modèle (`solo.py:96`) : le banc fournit des modèles simulés ; l'état vide relève de la story 5.
- `.github/workflows/tests.yml` -- déclencheurs `main`/`develop` ; `upload-artifact@v3` refusé par GitHub ; dernières majeures vérifiées par `git ls-remote` : checkout v7, setup-python v7 (`cache: pip`), upload-artifact v7, codecov v7 (`files:`).
- `README.md:40-65`, `docs/TROUBLESHOOT.md:30-60` -- commandes d'installation et de lancement.

## Tasks & Acceptance

**Execution:**
- `requirements.txt` -- dédoublonner, exclure `langchain-community==0.4.2` avec la raison en commentaire, ajouter `pytest-mock` -- E1.
- `constraints.txt` -- générer avec `uv pip compile`, commande en en-tête ; réinstaller `.venv-app` avec et vérifier `import ragas` -- D6.
- `src/core/providers/mistral_provider.py` -- repli `from mistralai.client import Mistral` -- le cloud Mistral est inutilisable avec la version figée.
- `.streamlit/config.toml` -- serveur sur localhost, télémétrie coupée -- F8, D5.
- `pytest.ini` -- marqueur `e2e`, exclu par défaut.
- `tests/integration/test_inference_ollama.py` -- y déplacer `test_inference_reelle_ollama` à l'identique.
- `tests/unit/test_llm_provider.py`, `tests/unit/test_models_db.py`, `tests/fixtures/models_catalog_test.json`, `tests/unit/test_green_monitor.py` -- corriger cibles de patch et données, assertions inchangées -- E3.
- `tests/app/conftest.py`, `tests/app/test_pages.py` -- providers simulés (modèles locaux factices, embeddings `DeterministicFakeEmbedding`, pas de reranker), Chroma et CodeCarbon dans `tmp_path`, `HF_HUB_OFFLINE=1` ; un test par page : aucune exception, un `st.title` rendu.
- `.github/workflows/tests.yml` -- `push`/`pull_request` sur `master` ; installation avec `-c constraints.txt` ; `pytest tests/unit tests/app` ; lint non bloquant ; actions à jour.
- `README.md`, `docs/TROUBLESHOOT.md` -- installation avec contraintes, `.venv-app`, localhost par défaut et ouverture réseau explicite.

**Acceptance Criteria:**
- Given `.venv-app` réinstallé depuis `constraints.txt`, when `pytest tests/unit tests/app -q`, then 0 échec, sans Ollama ni `data/models.json`.
- Given la suite lancée, when elle se termine, then aucun fichier n'a été créé dans `data/chroma`.
- Given `pytest --collect-only -m e2e`, when aucun test `e2e` n'existe encore, then la commande s'exécute sans erreur de marqueur.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 33 findings — high 0, medium 4, low 16, false 7, maybe-false 6
- findings:
  - `[false]` `[reject]` (blind) constraints.txt absent du diff — exclu volontairement du diff de revue (fichier généré de 1342 lignes) ; il est commité avec la story.
  - `[medium]` `[defer]` (blind) benchmark_slm.py importe encore `from mistralai import Mistral`, qui échoue avec mistralai 2.10.1 — fichier interdit hors PR de benchmark ; noté au rapport.
  - `[medium]` `[defer]` (blind) AGENTS.md périmé (CI, 4 tests en échec, commandes) — fichier d'instructions agent : différé.
  - `[medium]` `[patch]` (blind) rien n'empêche constraints.txt de dériver de requirements.txt — ajout de `test_constraints_cover_requirements`.
  - `[low]` `[patch]` (blind) test d'import ne vérifie pas les contraintes — couvert par le test précédent.
  - `[low]` `[reject]` (blind) `toml` n'est qu'une dépendance transitive de streamlit — figé dans constraints.txt ; changer de parseur ajoute un repli sans gain.
  - `[low]` `[patch]` (blind) tracker arrêté seulement si les assertions passent — try/finally.
  - `[low]` `[reject]` (blind) liste PAGES codée en dur — 5 pages stables ; la story 3 passe à st.navigation et reprendra la liste.
  - `[low]` `[reject]` (blind) fixture de catalogue dupliquée — deux usages, aucune panne constatée.
  - `[low]` `[patch]` (blind) variables HF posées à l'import pour toute la session — forcées à 1 (voulu : aucun accès Hub pendant les tests).
  - `[low]` `[reject]` (blind) `-m "not e2e"` remplacé par un `-m` en ligne de commande — comportement standard de pytest, documenté.
  - `[low]` `[patch]` (blind) commandes Mac/Linux et avertissement réseau manquants dans le README — ajoutés.
  - `[low]` `[reject]` (blind) outils de lint non figés, pas de timeout CI, CI jamais exécutée — lint non bloquant par décision ; la CI s'exécutera sur la PR.
  - `[low]` `[patch]` (verification-gap) gatherUsageStats non testé — assertion ajoutée.
  - `[medium]` `[patch]` (verification-gap) couverture requirements → constraints non vérifiée — même correctif que ci-dessus.
  - `[false]` `[reject]` (verification-gap) constraints.txt non suivi — voir la première ligne.
  - `[low]` `[reject]` (verification-gap) import `toml` transitif — voir ci-dessus.
  - `[low]` `[defer]` (verification-gap) la suite écrit encore dans data/logs/benchmarks via l'import de benchmark_slm.py — préexistant, fichier interdit.
  - `[maybe-false]` `[reject]` (intent) lecture B : démarrage réel non testé automatiquement — vérifié à la main (seule « URL: http://localhost:8501 ») ; un test qui lance le serveur serait lent et fragile.
  - `[medium]` `[patch]` (intent) confinement dépendant du répertoire de lancement — README et TROUBLESHOOT imposent de lancer depuis la racine ; un réglage global demanderait de modifier ~/.streamlit, hors dépôt.
  - `[maybe-false]` `[reject]` (intent) CI non exécutée sur Windows, macOS, 3.10, 3.11 — se vérifie sur la PR ; résolution pip en 3.11 faite.
  - `[false]` `[reject]` (intent) import ragas ne prouve pas l'installation neuve — `.venv-app` a été recréé de zéro depuis constraints.txt (0 écart).
  - `[maybe-false]` `[reject]` (intent) pages non exercées au-delà du premier rendu — conforme au critère « les 5 pages passent AppTest » ; interactions couvertes par les stories suivantes.
  - `[false]` `[reject]` (intent) `pytest` nu collecte tests/integration — comportement documenté (AGENTS.md) ; la suite visée est tests/unit + tests/app.
  - `[maybe-false]` `[defer]` (intent) écritures résiduelles dans data/ (config.py, benchmark) — fichiers importés par le benchmark, non modifiables ici.
  - `[false]` `[reject]` (intent) AGENTS.md non mis à jour — doublon, déjà différé.
  - `[low]` `[patch]` (edge) JSON lu après `MODELS_DB.clear()` dans conftest — lecture avant clear.
  - `[low]` `[patch]` (edge) même défaut dans test_models_db.py — idem.
  - `[low]` `[reject]` (edge) tracker non arrêté — doublon du correctif try/finally.
  - `[low]` `[patch]` (edge) télémétrie Chroma active dans les tests — `ANONYMIZED_TELEMETRY=False`.
  - `[false]` `[reject]` (edge) config.toml non lu hors racine — doublon, corrigé par la doc.
  - `[maybe-false]` `[reject]` (edge) langchain-community ≥0.4.3 pourrait aussi casser ragas — hypothétique ; les contraintes figent 0.4.1.
  - `[false]` `[reject]` (edge) docs COMMANDES_UTILES.md et assertion « Hub garanti hors ligne » — HF forcé à 1 par le correctif ; COMMANDES_UTILES noté au rapport.
  - `[maybe-false]` `[reject]` (edge) test_socle ne lit pas l'option effective de Streamlit — la lecture du fichier est la source ; démarrage vérifié à la main.

## Design Notes

Le fichier de contraintes est universel (`--universal`) pour que la CI de 3.10 à 3.12, Windows et macOS l'utilisent ; il n'est vérifié par installation réelle que sur Linux 3.12 cette nuit, la CI couvre le reste. `config.py` crée `data/logs` et `data/chroma` vides à l'import : inchangé (importé par le benchmark), noté au rapport.

## Verification

**Commands:**
- `.venv-app/bin/python -c "import ragas, streamlit"` -- expected: aucune erreur
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `timeout 20 .venv-app/bin/python -m streamlit run src/app/Accueil.py --server.headless true` -- expected: « Local URL: http://localhost:8501 » et aucune « Network URL » ni « External URL »

## Auto Run Result

Status: done

**Résumé :** versions figées dans `constraints.txt` (uv pip compile --universal, Python 3.10–3.12), `import ragas` réparé (langchain-community ≠ 0.4.2), import mistralai 2.x réparé, serveur sur localhost et télémétrie Streamlit coupée, banc AppTest des 5 pages avec providers simulés, tests/unit au vert sans Ollama ni data/models.json, CI sur master, docs à jour.

**Fichiers :**
- `requirements.txt` — dédoublonné, exclusion de langchain-community 0.4.2, pytest-mock.
- `constraints.txt` — versions figées (333 paquets, marqueurs par version de Python).
- `src/core/providers/mistral_provider.py` — repli d'import `mistralai.client`.
- `.streamlit/config.toml` — `server.address = "localhost"`, `gatherUsageStats = false`.
- `pytest.ini` — marqueur `e2e`, exclu par défaut.
- `tests/app/` — banc AppTest (5 pages) et tests du socle.
- `tests/fixtures/models_catalog_test.json`, `.gitignore` — catalogue de test versionné.
- `tests/unit/test_llm_provider.py`, `test_models_db.py`, `test_green_monitor.py`, `test_inference_service.py`, `tests/integration/test_inference_ollama.py` — cibles, données, marqueur.
- `.github/workflows/tests.yml` — déclencheurs master, contraintes, tests/app, actions v7.
- `README.md`, `docs/TROUBLESHOOT.md` — installation, lancement depuis la racine, ouverture réseau.

**Revue :** 11 correctifs appliqués (2 medium, 9 low), 4 différés (benchmark mistralai, AGENTS.md, écritures data/), 18 rejetés (motifs au journal).

**Suivi recommandé :** false — aucun correctif high ; les deux medium corrigés sont couverts par un test (couverture des contraintes) ou vérifiés à la main (lancement depuis la racine).

**Vérification :** `pytest tests/unit tests/app` : 171 réussis ; `import ragas, streamlit` OK ; démarrage : seule « URL: http://localhost:8501 » ; ruff : 18 remarques, comme avant.

**Risques :** contraintes installées réellement sur Linux 3.12 seulement (la CI couvre le reste) ; torch CUDA rend la CI Linux lente ; le benchmark perd l'API Mistral avec mistralai 2.x.
