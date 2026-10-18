---
title: 'Le dépôt accueille la v2 (squelette, Python 3.11, CI, ratification)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '7de6a02'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
warnings: []
deferred:
  - summary: >-
      Dépendances des stories suivantes absentes du lock : sqlite-vec, ecologits (`>=0.11.3,<0.12`) ; fastembed (extra `rerank`) est déclaré mais jamais exercé.
    evidence: |-
      La story 1.1 ne les exige pas dans ses critères ; AR1 prévoit l'extra `rerank`, déclaré ici (`fastembed>=0.9.0`, résolu à 0.9.0 dans uv.lock).
    location: pyproject.toml
    severity: low
  - summary: >-
      `CITATION.cff` reste en 1.3.0 : la préversion `2.0.0a1` (pyproject, uv.lock, CITATION.cff, tag, release) viendra en fin d'epic 1.
    evidence: |-
      AD-3 ; consigne de la story.
    location: CITATION.cff
    severity: low
---

# Story 1.1 : le dépôt accueille la v2

## Objectif

Un paquet `src/wavelocalai/` installable à côté de la v1 (même `pyproject.toml`, même `uv.lock`), testé en CI, décrit dans `AGENTS.md`. Aucun comportement serveur : `wavelocalai-v2` affiche seulement un message (le serveur arrive en 1.2).

## Critères d'acceptation et preuves

1. `uv sync` : `requires-python = ">=3.11,<3.13"`, `[tool.hatch.build] dev-mode-dirs = [".", "src"]`, script `wavelocalai-v2` dans `pyproject.toml` ; `uv.lock` régénéré. Preuve : `import wavelocalai` (depuis `src/wavelocalai/`), `import src.core` résolvent ; `.venv\Scripts\wavelocalai.exe` et `wavelocalai-v2.exe` existent, `wavelocalai-v2` s'exécute.
2. Versions de la spine vérifiées par installation réelle : fastapi 0.143.5 et uvicorn 0.54.0 (épinglés `==`, la dernière fastapi est 0.144.0), ollama 0.6.3 (borne basse, résolu ainsi). `import fastapi.sse` fonctionne. **Écart : pydantic reste à 2.12.5** (voir « Écart pydantic »).
3. `version = "2.0.0.dev0"` dans `pyproject.toml` et `uv.lock`, pas de tag.
4. `tests/v2/unit/test_layers.py` (AST) : sens du diagramme d'AD-4 (arêtes directes), aucun `src.*`, `fastapi`/`starlette`/`uvicorn` seulement dans `web/`, imports lourds (`codecarbon`, `fastembed`, `pypdf`, `docx`, `ecologits`, `openai`, `anthropic`, `mistralai`) jamais au niveau d'un module (sous `TYPE_CHECKING` toléré). Preuve : 24 modules pièges et 10 imports légitimes écrits en dossier temporaire par les tests eux-mêmes ; le paquet réel est sans violation et correspond au Structural Seed.
5. CI (`.github/workflows/tests.yml`) : job `test-v2` (`astral-sh/setup-uv`, `uv sync --locked`, `pytest tests/v2`, Python 3.11 et 3.12, trois OS) ; job v1 sans 3.10 ; Codecov sur 3.11 ; lint et sécurité passés en 3.11.
6. Ruff `py311` pour `src/wavelocalai/` et `tests/v2/` par un `ruff.toml` propre à chaque dossier (qui étend `pyproject.toml`) ; réglages globaux et `scripts/benchmark_slm.py` inchangés.
7. `AGENTS.md` : Python 3.11+, v1 en correctifs seulement, section « La v2 » (lanceur, port 8502, `tests/v2/{unit,web,e2e}`, règle d'imports, version). `requirements.txt` et `constraints.txt` régénérés pour 3.11 (`uv pip compile requirements.txt --universal --python-version 3.11`). `README.md` et `docs/TROUBLESHOOT.md` : mention 3.10 corrigée.
8. v1 intacte : `python -m pytest tests/unit tests/app` vert.

## Fichiers

- `pyproject.toml`, `uv.lock`, `requirements.txt`, `constraints.txt`, `AGENTS.md`, `README.md`, `docs/TROUBLESHOOT.md`, `.github/workflows/tests.yml`
- `src/wavelocalai/` : `__init__.py`, `__main__.py` (`main()` minimal), `config.py`, `errors.py`, `telemetry.py`, `ruff.toml`, paquets vides `runs/ models/ inference/ rag/ agents/ evaluation/ greenops/ hardware/ store/ web/`
- `tests/v2/{unit,web,e2e}/`, `tests/v2/unit/test_layers.py`, `tests/v2/ruff.toml`

## Choix notables

- `onnxruntime` perd ses marqueurs de version Python (devenus sans objet avec 3.11+) ; `ollama` relevé à 0.6.3 dans `pyproject.toml` et `requirements.txt`.
- `dev-mode-dirs` passe de `[tool.hatch.build.targets.wheel]` à `[tool.hatch.build]` (comme l'écrit le critère) ; `packages = ["src"]` reste sur la cible wheel.
- Le test ne couvre que les arêtes directes du diagramme (pas leur fermeture transitive) ; `__main__` peut tout importer, l'`__init__` racine rien.

## Écart pydantic (décision à prendre)

La spine §Stack fixe pydantic 2.14.1, mais `crewai` (dépendance v1, dernière version 1.15.28) exige `pydantic<2.13`. Avec `pydantic>=2.14.1`, uv rétrograde crewai à 1.6.1 et 17 tests v1 échouent (`ImportError: Fallback to LiteLLM`, `tests/unit/test_mistral_cloud_models.py`). La story garde donc la borne `pydantic>=2.9.0` (lock : 2.12.5, v1 verte). Les deux voies : relever pydantic à la sortie de crewai de la v1 (bascule, AD-2), ou corriger la spine §Stack (pydantic `<2.13` tant que crewai est là).

## Reports

Voir l'en-tête `deferred` : dépendances des stories suivantes, `CITATION.cff` à la préversion.
