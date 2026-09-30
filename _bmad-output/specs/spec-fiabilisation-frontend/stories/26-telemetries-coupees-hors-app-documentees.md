---
title: 'Télémétries coupées hors de l’app et documentées'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: 'e4d023205bdb15377169ee46f7e0ab1363ad17fd'
baseline_revision: 'e4d023205bdb15377169ee46f7e0ab1363ad17fd'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/17-constats-recette-groq-reseau.md'
warnings: []
deferred:
  - summary: >-
      scripts/setup_rag_models.py annonce « Tous les modèles demandés sont prêts » même après un échec de téléchargement, et ce chemin d'échec n'a aucun test.
    evidence: |-
      download_model attrape toute exception, journalise l'échec et supprime le dossier ; main() termine sur le message de succès sans compter les échecs. Antérieur à la story 26, relevé par la revue.
    location: >-
      scripts/setup_rag_models.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** `disable_telemetry()` (`src/core/telemetry.py`) n'est appelée que par l'app (`Accueil.py`), par `eval_engine.py` et par le lanceur e2e. Les autres points d'entrée gardent les télémétries actives :
- `scripts/setup_rag_models.py` importe `huggingface_hub` sans couper la télémétrie de Hugging Face ;
- un script ou un test qui importe directement `crew_engine` (CrewAI) ou `vector_store` (Chroma) ne passe pas par l'app.

Par ailleurs, rien n'indique à l'utilisateur quelles télémétries sont coupées par défaut, ni comment en réactiver une.

**Approach:**
- **Couper au bon endroit.** Chaque module du cœur qui importe une bibliothèque à télémétrie appelle `disable_telemetry()` avant cet import, comme `eval_engine.py` avant Ragas :
  - `src/core/crew_engine.py` (CrewAI) ;
  - `src/core/rag/vector_store.py` (Chroma, par `langchain_chroma`) ;
  - `src/core/rag/models_factory.py` (Hugging Face, par `langchain_huggingface` et `sentence_transformers`).

  `scripts/setup_rag_models.py` l'appelle avant d'importer `huggingface_hub`.
- **Documenter.** `README.md` et `AGENTS.md` disent quelles télémétries sont coupées par défaut, et comment en réactiver une : définir sa variable dans l'environnement ou dans le `.env`, car une valeur déjà définie l'emporte.

## Boundaries & Constraints

**Always:**
- Une seule liste de variables : `TELEMETRY_OPT_OUTS`. La documentation la reprend sans en inventer.
- Même règle que la story 12 : une valeur déjà définie (environnement, puis `.env`) n'est jamais écrasée.
- Tests sans réseau ni téléchargement : `snapshot_download` simulé, écritures dans `tmp_path`, jamais dans `data/`.

**Never:**
- Modifier `src/core/config.py`, `scripts/benchmark_slm.py`, `benchmarks/` ou `data/`.
- Définir `HF_HUB_OFFLINE` ou `TRANSFORMERS_OFFLINE`, ce qui bloquerait le premier téléchargement légitime (story 17).
- Ajouter les variables à `APP_ENV` de `tests/e2e/conftest.py` (story 12).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Import direct de CrewAI | Environnement sans opt-out, `import src.core.crew_engine` | `CREWAI_DISABLE_TELEMETRY`, `OTEL_SDK_DISABLED` et `CREWAI_DISABLE_VERSION_CHECK` posés avant l'import de `crewai` | N/A |
| Import direct de Chroma | Idem, `import src.core.rag.vector_store` | `Settings().anonymized_telemetry` de Chroma vaut `False` | N/A |
| Import direct de Hugging Face | Idem, `import src.core.rag.models_factory` | `huggingface_hub.constants.HF_HUB_DISABLE_TELEMETRY` vaut `True` | N/A |
| Script de préparation RAG | Idem, chargement de `scripts/setup_rag_models.py` | Télémétrie de Hugging Face coupée avant l'import de `huggingface_hub` ; le script reste lançable par `python scripts/setup_rag_models.py` | N/A |
| Réactivation volontaire | `HF_HUB_DISABLE_TELEMETRY=0` dans l'environnement | Valeur conservée | N/A |
| Documentation | `README.md` | Cite chaque variable de `TELEMETRY_OPT_OUTS` et explique la réactivation (environnement ou `.env`) | N/A |

</intent-contract>

## Code Map

- `src/core/telemetry.py`
  - `TELEMETRY_OPT_OUTS` (l.22) et `disable_telemetry()` (l.41) : rien à changer.
  - Mettre à jour la docstring (l.1-12) : elle énumère les appelants.
- `src/core/eval_engine.py:6-9` : le modèle à suivre. Import de `disable_telemetry`, appel, puis imports de la bibliothèque (`# noqa: E402` si ruff le demande).
- `src/core/crew_engine.py:12-13` : `from crewai import …` en tête de module.
- `src/core/rag/vector_store.py:3` : `from langchain_chroma import Chroma`.
- `src/core/rag/models_factory.py:5-6` : `langchain_huggingface`, `sentence_transformers`.
- `scripts/setup_rag_models.py:16` : `from huggingface_hub import snapshot_download`.
  - `src` n'est pas importable depuis `scripts/` sans chemin. Ajouter la racine à `sys.path` avant l'import, comme `scripts/bench_here.py:24`.
  - Aucun effet de bord à l'import : `ensure_dirs` reste dans `main()`.
- Importeurs actuels à ne pas casser : `src/app/tabs/agent/crew.py:27`, `src/core/rag_engine.py:12` et les tests `tests/unit/test_agent_tools.py`, `tests/unit/test_rag_upload.py`, `tests/app/test_nothing_lost.py`, `tests/e2e/launch_app.py:93-100`. `src/core/config.py:7` fait déjà `load_dotenv()` : l'appel ne charge donc aucune variable de plus.
- Tests :
  - `tests/unit/test_telemetry.py` : motifs `_clean_env` et `subprocess.run` (l.40-70), test d'ordre par AST (l.73).
  - `tests/unit/test_rag_models_factory.py` (story 17) pour les simulations Hugging Face.
- Documentation :
  - `README.md` : section « Configuration Avancée », l.210 et suivantes (bloc `.env`) ; la l.66 cite déjà `gatherUsageStats`.
  - `AGENTS.md` : une ligne dans « Where things are » ou « Known pitfalls ».

## Tasks & Acceptance

**Execution:**
- [x] `src/core/crew_engine.py`, `src/core/rag/vector_store.py`, `src/core/rag/models_factory.py` -- `disable_telemetry()` avant l'import de la bibliothèque -- imports directs
- [x] `scripts/setup_rag_models.py` -- racine dans `sys.path`, `disable_telemetry()` avant `huggingface_hub` -- script hors app
- [x] `src/core/telemetry.py` -- docstring : appelants à jour -- traçabilité
- [x] `tests/unit/test_telemetry.py` -- lignes 1 à 5 de la matrice :
  - en sous-processus, environnement sans opt-out ;
  - test par AST : dans chaque module listé, l'appel précède le premier import de la bibliothèque ;
  - garde de documentation : chaque variable de `TELEMETRY_OPT_OUTS` figure dans `README.md` (ligne 6) ;

  -- non-régression
- [x] `tests/unit/test_setup_rag_models.py` (nouveau) -- `download_model` avec `snapshot_download` simulé dans `tmp_path` : appel avec le bon dépôt, puis modèle déjà présent qui ne rappelle rien -- aucun téléchargement
- [x] `README.md` -- sous-section « Télémétries » : liste de `TELEMETRY_OPT_OUTS` (et Streamlit par `gatherUsageStats`), réactivation par l'environnement ou le `.env` avec un exemple (`LANGSMITH_TRACING=true`) -- utilisateur
- [x] `AGENTS.md` -- une ligne : télémétries coupées par `src/core/telemetry.py` ; tout nouveau point d'entrée qui importe Chroma, CrewAI, Ragas ou Hugging Face appelle `disable_telemetry()` avant ; réactivation par l'environnement ou le `.env` -- agents
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les deux entrées de la story 12 traitées ici -- traçabilité

**Acceptance Criteria:**
- Given un environnement sans aucune variable d'opt-out, when on lance `python scripts/setup_rag_models.py --help`, then le script s'exécute sans erreur d'import.
- Given un lecteur du README, when il cherche comment réactiver LangSmith, then il trouve la variable et les deux façons de la définir (environnement ou `.env`).

## Spec Change Log

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 29 findings — high 0, medium 3, low 21, false 5, maybe-false 0
- findings:
  - `[false]` `[reject]` (intent) garde placée dans les modules plutôt que chez l'appelant, avec un effet de bord sur `os.environ` à l'import — choix des Design Notes (seul endroit sûr avant l'import d'une bibliothèque), déjà celui d'`eval_engine.py` depuis la story 12.
  - `[low]` `[reject]` (intent) `tests/e2e/conftest.py` importe `huggingface_hub` sans garde — harnais de test ; `try_to_load_from_cache` ne lit que le cache local, aucun envoi.
  - `[false]` `[reject]` (intent) LangSmith sans garde propre — LangSmith ne trace que si une variable l'active ; sans elle, rien n'est envoyé.
  - `[low]` `[reject]` (intent) tests sur l'état des variables, pas sur le réseau — un test réseau exigerait une connexion ; l'état lu par chaque bibliothèque est le contrat.
  - `[low]` `[reject]` (intent) réactivation par le `.env` par défaut non exercée à l'import direct — couverte par le test de la story 12 (`disable_telemetry(dotenv)`), même fonction.
  - `[medium]` `[patch]` (intent) liste fermée `TELEMETRY_IMPORTERS` alors qu'AGENTS.md promet un contrôle des nouveaux modules — test de découverte `test_every_telemetry_importer_is_listed` (AST sur `src/` et `scripts/`, 9 racines dont `langchain_community`) ; AGENTS.md reformulé.
  - `[low]` `[patch]` (intent) garde README par sous-chaîne (`DO_NOT_TRACK` trouvé dans `RAGAS_DO_NOT_TRACK`) — noms cherchés entre accents graves.
  - `[false]` `[reject]` (intent) AGENTS.md n'énumère pas les variables — il nomme la liste unique (`TELEMETRY_OPT_OUTS`, reprise dans le README), conforme à « une seule liste ».
  - `[medium]` `[patch]` (blind) `setup_rag_models.py` passe `local_dir_use_symlinks`, absent de `snapshot_download` en 1.33.0 : `TypeError` attrapé, aucun téléchargement possible ; le faux du test accepte `**kwargs` et le masque — défaut antérieur, exposé par le test de la story : paramètre retiré, faux construit par `create_autospec` (contre-épreuve : les deux tests échouent avec l'ancien appel).
  - `[low]` `[defer]` (blind) chemin d'échec du script non testé ; `main()` annonce « Tous les modèles demandés sont prêts » après un échec — antérieur à la story (frontmatter `deferred`).
  - `[low]` `[patch]` (blind) tests Hugging Face masqués par `DO_NOT_TRACK=1` — la variable `HF_HUB_DISABLE_TELEMETRY` est aussi vérifiée dans le sous-processus.
  - `[low]` `[patch]` (blind) test de réactivation sans effet réel (`DO_NOT_TRACK=1` garde la coupure) — les deux variables à 0, constante `False` affirmée.
  - `[low]` `[patch]` (blind) README : couple CrewAI (`OTEL_SDK_DISABLED` ou `CREWAI_DISABLE_TELEMETRY`), portée d'`OTEL_SDK_DISABLED`, `DO_NOT_TRACK=0` — trois précisions ajoutées (couple vérifié dans `crewai_core/telemetry.py`).
  - `[medium]` `[patch]` (blind) AGENTS.md promet un contrôle que le test ne fait pas — même entrée que la liste fermée.
  - `[medium]` `[patch]` (blind) le test AST ne connaît que les bibliothèques listées et ignore les imports indirects — même cause (liste fermée) ; la découverte couvre `langchain_community`, cause de l'import indirect.
  - `[low]` `[patch]` (blind) tests dépendants du `.env` réel du développeur — sous-processus lancés dans `tmp_path` avec `PYTHONPATH`, le `.env` du dépôt n'est plus lu.
  - `[low]` `[reject]` (blind) `test_setup_rag_models.py` modifie `os.environ` et `sys.path` pour la session — même effet que tout import de `crew_engine` ou `vector_store` par la suite ; suite complète au vert ; le correctif ajouterait une sauvegarde et une restauration.
  - `[low]` `[patch]` (blind) README trop large (« rien ne quitte la machine ») — « aucune télémétrie de bibliothèque n'est envoyée », téléchargements et cloud cités.
  - `[low]` `[patch]` (blind) ligne de docstring de 147 caractères — repliée.
  - `[medium]` `[patch]` (edge) import direct de `src.core.rag_engine` : `ingestion.py` charge `huggingface_hub` par `langchain_community` avant toute coupure (constante `False`, reproduit) — `disable_telemetry()` avant l'import dans `ingestion.py`, test en sous-processus paramétré sur `rag_engine`.
  - `[medium]` `[patch]` (edge) test AST sans importeurs nouveaux ou transitifs — même entrée que la liste fermée.
  - `[low]` `[patch]` (edge) sous-processus qui lisent le `.env` du dépôt — même correctif que la ligne blind.
  - `[low]` `[patch]` (edge) test de réactivation inopérant — même correctif que la ligne blind.
  - `[low]` `[reject]` (edge) `find_dotenv` part du répertoire courant en mode `-c`, REPL ou Jupyter — comportement antérieur, identique à `src/core/config.py:7` ; l'app et les scripts ont un `__file__`, le `.env` du dépôt est trouvé.
  - `[low]` `[reject]` (edge) mutation de l'environnement par la fixture du script — même raison que la ligne blind.
  - `[medium]` `[patch]` (edge) README qui promet la coupure pour les modules importés directement, démentie par `rag_engine` — même entrée qu'`ingestion.py`.
  - `[medium]` `[patch]` (edge) AGENTS.md qui promet un contrôle des nouveaux modules — même entrée que la liste fermée.
  - `[medium]` `[patch]` (verification-gap) aucun test de découverte des importeurs — même entrée que la liste fermée.
  - `[low]` `[reject]` (verification-gap) le processus pytest des e2e hérite désormais des opt-outs transmis à l'app — `tests/e2e/launch_app.py:93-95` appelait déjà `disable_telemetry()` : la garde réseau ne pouvait pas le détecter avant non plus ; le test AST d'`Accueil.py` couvre l'app.

## Design Notes

**`models_factory.py` inclus.** L'intention cite `crew_engine` et `vector_store` en exemples d'imports directs. `models_factory.py` est le troisième module du cœur qui importe une bibliothèque à télémétrie (Hugging Face), et `rag_engine.py` ainsi que des tests l'importent directement. L'exclure laisserait ouvert le même trou que celui du script.

**Pourquoi dans le module et pas chez l'appelant.** Chaque bibliothèque lit sa variable à l'import. Le seul endroit sûr est donc la ligne qui précède cet import : un appelant peut toujours importer le module d'abord.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit
- `.venv-app\Scripts\python scripts/setup_rag_models.py --help` -- expected: aide affichée, aucun téléchargement
- `uvx ruff check` et `uvx black --check` sur les fichiers Python touchés -- expected: propres
- `git diff --stat e4d023205bdb15377169ee46f7e0ab1363ad17fd -- src/core/config.py scripts/benchmark_slm.py benchmarks data` -- expected: vide

## Auto Run Result

Status: done

**Résumé.**
- Chaque module qui importe une bibliothèque à télémétrie appelle `disable_telemetry()` juste avant cet import, comme `eval_engine.py` :
  - `crew_engine.py` (CrewAI) ;
  - `rag/vector_store.py` (Chroma) ;
  - `rag/models_factory.py` (Hugging Face) ;
  - `rag/ingestion.py` (`langchain_community`, qui charge Hugging Face ; relevé à la revue) ;
  - `scripts/setup_rag_models.py`, qui trouve désormais `src` seul.
- Un test de découverte par AST relève tout module de `src/` ou `scripts/` qui importe l'une de ces bibliothèques et vérifie que l'appel précède l'import.
- `README.md` : section « Télémétries » (les 9 variables, Streamlit, réactivation par l'environnement ou le `.env`, couples LangSmith, CrewAI et Hugging Face). `AGENTS.md` : la règle pour tout nouveau module.
- Écart à la spec : l'exemple de réactivation `LANGSMITH_TRACING=true` seul ne suffit pas (LangSmith lit d'abord `LANGCHAIN_TRACING_V2`, que la liste pose à `false`). Le README demande les deux variables.
- Défaut antérieur corrigé en passant : `setup_rag_models.py` ne pouvait plus rien télécharger (`local_dir_use_symlinks`, retiré de `huggingface_hub` 1.33).

**Fichiers.**
- `src/core/crew_engine.py`, `src/core/rag/vector_store.py`, `src/core/rag/models_factory.py`, `src/core/rag/ingestion.py` : coupure avant l'import.
- `scripts/setup_rag_models.py` : chemin de `src`, coupure, paramètre obsolète retiré.
- `src/core/telemetry.py` : docstring (appelants, réactivation).
- `tests/unit/test_telemetry.py` : sous-processus sans opt-out ni `.env`, test d'ordre et de découverte par AST, garde du README.
- `tests/unit/test_setup_rag_models.py` (nouveau) : `snapshot_download` simulé avec sa vraie signature, écritures dans `tmp_path`.
- `README.md`, `AGENTS.md`, `_bmad-output/implementation-artifacts/deferred-work.md` (deux entrées retirées).

**Revue.** 29 constats :
- 3 causes medium corrigées (liste fermée des importeurs, `ingestion.py`, paramètre obsolète masqué par le test) et 9 low corrigés ;
- 1 différé (message de succès après un échec du script, antérieur) ;
- 8 rejetés, dont 5 false (raisons au journal).

**Revue de suivi recommandée :** true, pour 3 correctifs medium. Risque à vérifier : un import indirect qui chargerait une bibliothèque à télémétrie par une racine absente de `TELEMETRY_ROOTS`.

**Vérification.**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` : 1 086 réussis.
- `.venv-app\Scripts\python scripts/setup_rag_models.py --help` : aide affichée, rien téléchargé.
- ruff et black propres ; `git diff --stat` sur `src/core/config.py scripts/benchmark_slm.py benchmarks data` : vide.

**Risques.** Aucune vérification réseau réelle : les tests lisent l'état des variables et des réglages de chaque bibliothèque.
