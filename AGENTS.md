<!-- bmad:context -->
<!-- Verified 2026-09-26 against 27d2f7e. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## wavelocalai (v1)

Démonstrateur Streamlit de petits modèles de langage locaux (Ollama), avec mesure carbone (CodeCarbon), et banc de benchmark multi-machines dans `scripts/`. Python. La v1 est en maintenance : elle sert de référence à la v2 (dépôt voisin `wavelocalai-v2`). Plans en cours : `docs/audits/frontend-2026-09/` et `_bmad-output/`.

## Policy

- Jamais de push sur `master` : une branche préfixée (`fix/`, `feat/`, `docs/`, `chore/`, `bench/`, `audit/`, ou `claude/` en session cloud), une PR, fusion par merge commit, jamais de squash.
- Nouvelles fonctionnalités dans la v1 seulement si elles améliorent l'UI ou l'UX ; les autres vont dans la v2.
- Ne modifier la mesure du benchmark (`scripts/benchmark_slm.py`, et ce qu'il importe de `src/core/`, dont `config.py`) que dans une PR dédiée au benchmark. Les exports ne tracent que le SHA de `benchmark_slm.py` : un changement dans `src/core/` fausse les comparaisons sans alerte.
- Ne jamais éditer à la main `benchmarks/results/*.json` (écrit par `scripts/bench_here.py export`) ni `config/models_catalog.json` (écrit par `scripts/build_catalog.py`).
- Ne jamais commiter, vider ou réinitialiser `data/` (Chroma, logs, `models.json` local). Le dépôt est public : aucun document client, extrait de réponse RAG ou capture montrant du contenu indexé dans un commit ou une PR.
- Ne jamais éditer `_bmad/` ni `.claude/skills/bmad-*`, régénérés par l'installeur : personnaliser via `_bmad/custom/*.toml`.
- Ne jamais figer une version de dépendance de mémoire : la vérifier sur PyPI ou npm, ou par une installation réelle.
- Toute évolution visuelle suit la charte Wavestone (primaire `#451DC7`, icônes Material, aucun emoji décoratif).
- Docs, messages de commit, PR et textes d'interface en français ; identifiants de code en anglais.

## Where things are

- App : `src/app/Accueil.py`, pages dans `src/app/pages/`, onglets dans `src/app/tabs/`. Logique dans `src/core/`, qui n'importe jamais `streamlit` : l'UI reste dans `src/app/`.
- Catalogue de modèles de l'app : `data/models.json` (local, non versionné) ; `config/models_catalog.json` en est l'extrait versionné.
- Lancer un benchmark ? Lire d'abord `docs/PROMPT_NOUVELLE_MACHINE.md` : aucun téléchargement pendant une campagne, et une PR de bench ne contient que le fichier de résultats.

## Running and verifying

- Appeler l'interpréteur directement (`.venv\Scripts\python -m …`) plutôt qu'activer le venv : l'exécution de scripts PowerShell peut être bloquée.
- Sur certaines machines, `.venv` ne contient que les dépendances du benchmark (pas Streamlit) : l'app tourne alors dans `.venv-app` (ignoré par git). Ne jamais installer `requirements.txt` dans un `.venv` réservé au benchmark.
- Tests : `python -m pytest tests/unit`. Un `pytest` nu ou `pytest tests/` lance aussi `tests/integration`, qui exige Ollama et `qwen2.5:1.5b`.
- `pytest.ini` prime sur la section pytest de `pyproject.toml`, dont les options de couverture sont donc ignorées ; la CI ajoute `--cov` elle-même.
- Viser Python 3.10+ (cible black/ruff `py310`, CI de 3.10 à 3.12).

## Conventions that differ from defaults

- Messages de commit : `Préfixe: description en français` (`Fix:`, `Feat:`, `Docs:`, `Chore:`, `Bench:`, `Audit:`, `Catalogue:`), pas de conventional commits en minuscules.

## Known pitfalls

- La CI (`.github/workflows/tests.yml`) ne se déclenche que sur `main` et `develop` : elle ne tourne jamais ici. Lancer les tests en local avant toute PR.
- Sur `master` (3dfdfda), 4 tests de `tests/unit` échouent déjà : `test_inference_reelle_ollama`, `test_get_langchain_model_mistral`, `test_pull_model_cloud_raises_error`, `test_get_all_languages`. Ne pas les imputer à sa propre modification.
- `.secrets.baseline` : sous Windows PowerShell 5.1, `Out-File -Encoding utf8` ajoute un BOM qui casse detect-secrets ; écrire avec `[System.Text.UTF8Encoding]::new($false)`.
- Télémétries coupées par défaut par `src/core/telemetry.py` (`TELEMETRY_OPT_OUTS`, liste reprise dans le README) : tout module de `src/` ou `scripts/` qui importe Chroma, CrewAI, Ragas, Hugging Face ou `langchain_community` (qui charge Hugging Face) appelle `disable_telemetry()` juste avant cet import ; un test AST de `tests/unit/test_telemetry.py` relève ces modules et vérifie l'ordre. Réactivation par l'environnement ou le `.env`, dont la valeur l'emporte.
- Tests navigateur : les listes de modèles de Streamlit sont virtualisées (taper pour filtrer), et une écriture Chroma faite par un autre processus reste invisible pour un serveur déjà lancé (ingérer via l'interface).

<!-- /bmad:context -->
