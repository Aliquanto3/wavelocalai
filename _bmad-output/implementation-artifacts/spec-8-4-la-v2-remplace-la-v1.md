---
title: 'Story 8.4 : la v2 remplace la v1 (2.0.0)'
type: 'refactor'
created: '2026-10-23'
status: 'draft'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
  - '{project-root}/docs/parite-v1-v2.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le dépôt porte encore deux applications : `uv run wavelocalai` lance la v1 Streamlit, la v2 passe par `wavelocalai-v2`, et le paquet ne fonctionne qu'en installation éditable (`packages = ["src"]`, `dev-mode-dirs`). Les dépendances de la v1 (torch, CrewAI, Chroma…) alourdissent l'installation et bloquent pydantic sous 2.13.

**Approach:** Appliquer la décision Q5 : retirer la v1 de `master` (elle reste disponible au tag `v1.3.0`), faire de `wavelocalai` le lanceur de la v2, rendre le paquet installable depuis une roue, alléger les dépendances, ne garder que le job CI v2, et réaligner la documentation. Ensuite, recette humaine, puis publication de `2.0.0`.

## Boundaries & Constraints

**Always:**
- La v1 reste récupérable : le README cite le tag `v1.3.0` (`41846b07a556f6fd0b430eb01bb8a083ad21f135`) et la commande pour la lancer depuis ce tag.
- `scripts/sync_slm_results.py`, `scripts/build_catalog.py` et le workflow `sync-slm-results.yml` restent fonctionnels.
- Toute version de dépendance (pydantic, numpy…) est vérifiée sur PyPI et par une installation réelle (`uv lock` puis `uv sync`), jamais écrite de mémoire.
- `tests/v2` est vert sur les trois OS. Aucun test v2 n'est supprimé, ignoré ni affaibli.
- La recette se fait avant toute publication.
- La décision Q5 l'emporte sur la règle permanente « ne jamais modifier `scripts/benchmark_slm.py` ni `benchmarks/` » : le retrait du banc v1 est l'objet même de la story. `benchmarks/slm-quality/` n'est pas touché.

**Never:**
- Toucher `data/`, `src/data/`, `.venv-bench`, `_bmad/` ou `.claude/skills/bmad-*`.
- Éditer à la main `config/models_catalog.json` ou `benchmarks/slm-quality/*`.
- Réécrire les documents historiques (`docs/audits/`, `_bmad-output/` hors sprint status et cette spec, `docs/parite-v1-v2.md` hors statuts tranchés).
- Changer un comportement d'écran de la v2.
- Pousser un tag, créer une release ou changer un topic GitHub sans accord explicite d'Anaël au moment de le faire.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Dépôt cloné | `uv sync` puis `uv run wavelocalai` | la v2 démarre sur le port 8502 ; catalogue, équipes et résultats de bench lus depuis le dépôt ; `data/` à la racine du dépôt | — |
| Roue hors du dépôt | `uv build`, puis installation de la roue dans un venv propre, puis `wavelocalai` lancé depuis un autre dossier | le serveur démarre et l'écran Modèles affiche le catalogue embarqué | données écrites dans le dossier de données choisi (Q2), jamais dans `site-packages` |
| Ancien lanceur | `uv run wavelocalai-v2` | commande introuvable | — |
| Ancien import | `import src.core` dans le venv | `ModuleNotFoundError` | — |

</frozen-after-approval>

## Open Questions

1. **Parité : les 13 lignes « à confirmer » de `docs/parite-v1-v2.md`** (B3, A8, D4, D5, E5, G5, G9, G10, G11, S4, S8, M5, M6). Options : (a) confirmer les 13 abandons ; chaque ligne passe en « abandonnée » avec le motif « décision du 2026-10-23 » ; (b) confirmer tous les abandons sauf certaines lignes, qui deviennent des stories de suite après 2.0.0, sans bloquer la bascule ; (c) traiter certaines lignes avant la bascule, ce qui retarde 8.4. Recommandation : (b), avec D4 (bouton « Télécharger » sur la route Markdown, qui existe déjà) et A8 (phrase « Pourquoi ? ») en suites.
2. **Dossier de données d'une installation par roue.** Options : (a) `%LOCALAPPDATA%\WaveLocalAI` sous Windows (`~/.local/share/wavelocalai` ailleurs), modifiable par `WAVELOCALAI_HOME` ; c'est ce qu'attend un utilisateur qui installe un outil ; (b) le dossier courant au lancement ; c'est simple, mais `data/` apparaît là où l'on a tapé la commande. Dans les deux cas, un dépôt cloné garde `data/` à sa racine.
3. **Version de la recette.** Options : (a) la PR de bascule passe à `2.0.0rc1`, avec tag et préversion GitHub dont la roue sert à la recette ; après la recette, une PR passe à `2.0.0`, avec tag, release et topic `status-deployed` ; (b) la PR passe directement à `2.0.0`, et le tag n'est posé qu'après la recette, avec des correctifs éventuels sous ce même numéro. Recommandation : (a).
4. **Outils de banc de la v1 qui ne marchent plus sans `benchmark_slm.py`.** `bench_here.py`, `bench_speed_only.py` et `reaggregate_benchmark.py` tombent avec lui. Restent `merge_results.py`, `check_pending.py`, `machine_profile.py`, `benchmarks/results/` (que la v2 ne lit pas), `docs/PROMPT_NOUVELLE_MACHINE.md` et `docs/GUIDE_BENCHMARK_MANUEL.md`. Options : (a) tout retirer, puisque le banc vit dans slm-quality-bench et que le tag `v1.3.0` garde l'historique ; (b) retirer seulement les trois scripts dépendants et garder le reste comme archive. Recommandation : (a).
5. **Les deux fichiers non suivis `output/cahier-tests-v2.html` et `output/guide-testeur-v2.md`** : ils citent probablement `wavelocalai-v2` et le port 8502. Options : (a) les laisser hors de la branche, tels quels ; (b) les mettre à jour pour le nouveau lanceur et les versionner dans `docs/`.

## Code Map

- `pyproject.toml` : `version` l.7, `requires-python` l.11, dépendances l.14-86, scripts l.90-91, groupe dev l.93-111 (`toml` sert seulement à la v1), build l.113-118, `[tool.uv]` index et source torch l.122-128, coverage `src/core` l.130-157, pytest `--cov=src.core` l.174, black, isort et ruff en `py310`.
- Dépendances à retirer (non importées par la v2 ni par un script gardé) : streamlit, watchdog, plotly, langchain*, langgraph, openpyxl, xlrd, tqdm, docx2txt, nest_asyncio, setuptools, GPUtil, py-cpuinfo, chromadb, sentence-transformers, einops, torch, ragas, datasets, crewai, graphviz. À garder : ollama, httpx, pandas, pydantic, python-dotenv, numexpr, func-timeout, matplotlib, python-docx, codecarbon, psutil, nvidia-ml-py, pypdf, mistralai, anthropic, openai, fastapi, uvicorn, ecologits, sqlite-vec, python-multipart, fastembed. `numpy` est importé par `rag/index.py` sans être déclaré : le déclarer.
- `src/wavelocalai/config.py:24-26,70,245-251,330` : `PROJECT_ROOT = parents[2]` suppose le dépôt. Une roue casse `config/models_catalog.json` (`models/registry.py:208`), `config/agent_crews.json` (`web/app.py:338`), `benchmarks/slm-quality/slm-quality-results.json` (`models/bench_results.py:35`, `registry.py:211`), `wavelocalai.toml`, `.env` et `data/`. `config.get_version()` (l.271-276) lit `importlib.metadata`.
- Ressources du paquet, lues par `__file__` : elles suivent la roue (`store/migrate.py:22`, `web/routes_static.py:25`).
- `tests/v2/unit/test_layers.py:250-251,328-329` : règle « n'importe jamais `src.*` », à garder comme garde-fou.
- À retirer :
  - le code et les tests v1 : `src/app/`, `src/core/`, `tests/unit/`, `tests/app/`, `tests/integration/`, `tests/e2e/` (E2E Streamlit), `tests/fixtures/models_catalog_test.json` ;
  - les scripts : `scripts/{benchmark_slm,audit_and_update,setup_models,setup_rag_models,bench_here,bench_speed_only,reaggregate_benchmark}.py`, plus Q4 ;
  - les fichiers racine : `requirements.txt`, `constraints.txt`, `.streamlit/`, le dossier `Crew Multi Agent - Equipe/` ;
  - les images : `docs/assets/{demo.gif,demo.mp4,accueil,agents,chat,hardware,rag}.png` (ces derniers ne sont plus référencés).
- `.github/workflows/tests.yml` :
  - filtre `changes` l.43 ;
  - `lint` l.57-74 sur `src/ tests/` ;
  - job v1 `test` l.77-119, à supprimer ;
  - matrice v2 l.131, avec ajout de 3.13 ;
  - `security` l.198, où bandit doit viser `src/wavelocalai`.
- `.github/workflows/sync-slm-results.yml:63` : `pip install jsonschema -c constraints.txt`, à remplacer par uv et le lockfile.
- `pytest.ini` : `testpaths = tests`, à passer à `tests/v2`. Le marqueur `integration` reste.
- `.claude/cost-kit/controle_rapide.py:68-76` : le contrôle « `src/core` n'importe pas streamlit » devient obsolète.
- Docs vivantes à réaligner :
  - `README.md` : badges l.6-9, l.21, 34, 38, section v1 l.54-130, l.217, 294, 308, 508 ;
  - `AGENTS.md` : l.6, 12, 23, 29, 37, 52, 53, et les règles du banc ;
  - `CONTRIBUTING.md` : l.24 et 39 ;
  - `docs/ARCHITECTURE.md` : l.15-54, toute en v1 ; à remplacer par un renvoi à la spine ;
  - `docs/TROUBLESHOOT.md` : l.20-114 et 136 ;
  - `docs/COMMANDES_UTILES.md` : l.44 ;
  - `docs/AGENT_TOOLS.md` : l.665 ;
  - `scripts/README.md` : l.7 ;
  - `src/wavelocalai/memory.py:16`, qui cite `bench_here.py` ;
  - `CITATION.cff` (version) ;
  - `.gitignore` l.46 et 87 ;
  - la spine : §Stack l.255-258, AD-2 l.72, §Deferred l.354.
- Continuité : 8.5 a fixé la règle des budgets de performance (deuxième meilleur de cinq appels) ; la CI doit passer sans relance.

## Tasks & Acceptance

**Execution:**
- [ ] `docs/parite-v1-v2.md` : appliquer les décisions de Q1. Les lignes « à confirmer » prennent leur statut définitif, et le tableau « À confirmer par Anaël » est remplacé par « Décisions du 2026-10-23 ». Si Q1 crée des suites, ajouter une entrée par suite dans `deferred-work.md`.
- [ ] `src/wavelocalai/config.py` (et ses appelants) : résoudre deux racines. La racine des ressources est le dépôt s'il est détecté (`pyproject.toml` voisin de `parents[2]`), sinon les ressources embarquées dans le paquet. La racine des données suit Q2. Les tests unitaires couvrent les deux cas avec des dossiers temporaires.
- [ ] `pyproject.toml` :
  - scripts : `wavelocalai = "wavelocalai.__main__:main"`, et `wavelocalai-v2` est retiré ;
  - build : `packages = ["src/wavelocalai"]`, `dev-mode-dirs` retiré, `force-include` des trois JSON de ressources dans la roue ;
  - dépendances : celles de la v1 retirées, `numpy` déclaré, pydantic relevé à la dernière version vérifiée, index et source torch retirés, `toml` retiré du groupe dev ;
  - outils : coverage et pytest sur `wavelocalai`, cible ruff, black et isort `py311` ;
  - version selon Q3.
- [ ] `uv.lock` : régénérer avec `uv lock`, puis `uv sync`. Mesurer la taille du `.venv` avant et après.
- [ ] Python 3.13 : l'ajouter à la matrice `test-v2`. Si la CI est verte sur les trois OS, passer la borne à `<3.14` ; sinon garder `<3.13` et noter la raison dans la spine §Deferred.
- [ ] Fichiers listés « à retirer » dans la Code Map, et Q4 : `git rm`.
- [ ] `.github/workflows/tests.yml` et `sync-slm-results.yml` : appliquer la Code Map.
- [ ] `pytest.ini`, `.gitignore`, `.claude/cost-kit/controle_rapide.py` : appliquer la Code Map.
- [ ] Docs vivantes de la Code Map :
  - README : une seule application, le lanceur `wavelocalai`, l'installation par `uv sync`, la v1 au tag `v1.3.0`, des badges sans Streamlit ni couverture de la v1 ;
  - `AGENTS.md` : ne décrit plus que la v2, avec la taille du `.venv` ; il retire les règles du banc v1 et la mention « v1 en correctifs seulement » ;
  - spine : §Stack, AD-2 et §Deferred, mis à jour via `bmad-architecture`.
- [ ] `CITATION.cff` : version et date, selon Q3.
- [ ] `_bmad-output/implementation-artifacts/sprint-status.yaml` : ajouter la clé `8-4-la-v2-remplace-la-v1` ; elle passera à `done` après la publication.

**Acceptance Criteria:**
- Given le dépôt après la bascule, when on cherche `src.core`, `src.app`, `streamlit` ou `wavelocalai-v2` hors des documents historiques, then on ne trouve que la règle de garde-fou de `test_layers.py`.
- Given `uv build` puis l'installation de la roue dans un venv propre hors du dépôt, when on lance `wavelocalai` et qu'on appelle `GET /api/models` (ou la route du catalogue), then le serveur répond et le catalogue n'est pas vide.
- Given la PR, when la CI tourne, then le seul job de tests est `test-v2` (3 OS × 3.11, 3.12, et 3.13 si elle est retenue), vert du premier coup, et le workflow `sync-slm-results` lancé à la main réussit.
- Given la recette humaine de Flow 1 et Flow 2 sur un PC pro de 16 Go sans GPU, installé par `uv sync` seul, when elle est validée, then `2.0.0` est publiée selon Q3 : tag annoté `v2.0.0`, release avec notes, topic `status-deployed`.

## Spec Change Log

## Review Triage Log

## Design Notes

- Ressources de la roue : `[tool.hatch.build.targets.wheel.force-include]` copie `config/models_catalog.json`, `config/agent_crews.json` et `benchmarks/slm-quality/slm-quality-results.json` sous `wavelocalai/_resources/`. Les scripts qui les écrivent ne changent pas. Dans le dépôt, la v2 lit la copie du dépôt, pour qu'une synchro soit vue sans rebuild.
- Une PR de bascule unique. Les retraits massifs font l'objet de commits séparés : code v1, scripts de banc, docs, empaquetage, CI. La revue se lit ainsi commit par commit.
- Implémentation par `agent-cost-kit:dev-story` sur Opus (story transverse et à risque), puis `second-avis`, puis `reviewer`.

## Verification

**Commands:**
- `.venv\Scripts\python -m pytest tests/v2 -q --tb=short` : attendu vert.
- `uv build`, puis dans un venv temporaire du scratchpad : `uv pip install dist\wavelocalai-*.whl`, `wavelocalai` lancé depuis le scratchpad, puis appel de la route du catalogue : attendu 200 et un catalogue non vide.
- `.venv\Scripts\python .claude/cost-kit/controle_rapide.py` : attendu sans erreur.
- `gh pr checks <n> --interval 60` : attendu tout vert, sans relance.

**Manual checks:**
- Recette humaine de Flow 1 et Flow 2 (Anaël), avant toute publication.
