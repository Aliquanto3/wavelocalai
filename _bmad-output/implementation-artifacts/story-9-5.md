---
title: 'Story 9.5 : fastembed est installé d''office, le bouton du reranker fonctionne'
type: 'feature'
created: '2026-10-21'
status: 'review'
baseline_commit: 'ba606cb'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-21.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
warnings: []
deferred: []
---

# Story 9.5 : fastembed est installé d'office, le bouton du reranker fonctionne

## Objectif

fastembed (le reranker local) passait par l'extra optionnel `rerank` : sans `uv sync --extra rerank`,
le bouton « Installer le reranker » de l'écran Modèles restait désactivé avec un renvoi à une
commande (R6 de la recette du 2026-10-21). Décision D-R6 : fastembed devient une dépendance de base.
Après `uv sync` seul, le bouton télécharge directement le modèle par le run `pull` existant.

## Critères d'acceptation et preuves

1. **Bouton actif après `uv sync` seul** : `pyproject.toml` porte `fastembed>=0.9.0` dans
   `dependencies` (plus d'`[project.optional-dependencies]`). Preuve : `uv sync --locked` (sans
   extra) installe fastembed ; `RerankerService.status()` ne porte plus de notion d'extra, seul
   « modèle absent du cache » bloque. Essai réel ci-dessous : le bouton a effectivement téléchargé et
   installé le modèle par le run `pull`.
2. **Version vérifiée, `uv.lock` régénéré, taille du `.venv` consignée** :
   - PyPI (`https://pypi.org/pypi/fastembed/json`, 2026-10-21) : dernière version **0.9.0**
     (2026-10-07), déjà la contrainte en place (`>=0.9.0`) — gardée, pas de changement de borne.
   - Installation réelle : `uv sync --locked` (après `uv lock`) installe `fastembed==0.9.0` sans
     erreur ; ajoute aussi `loguru`, `py-rust-stemmers`, `win32-setctime` (dépendances transitives de
     fastembed ; `onnxruntime`, `huggingface-hub`, `tokenizers` étaient déjà tirés par
     `sentence-transformers`/`langchain-huggingface`, donc pas de nouvel ajout lourd).
   - `uv.lock` régénéré (`uv lock`, « Resolved 267 packages »).
   - Taille du `.venv` du worktree (`du -sb .venv`) : **1 797 031 399 octets (≈ 1,674 GiB) avant**
     fastembed, **1 798 295 519 octets (≈ 1,675 GiB) après** — delta ≈ **1,2 Mo** (pour mémoire : le
     `.venv` du dépôt principal avec ses extras est à 1,9 Go, cf. consigne).
3. **Extra `rerank` et toute mention de `uv sync --extra rerank` retirés** : `pyproject.toml`
   (section `[project.optional-dependencies]` supprimée) ; `README.md` (§« Reranker local de la v2 ») ;
   `AGENTS.md` ne le citait pas (vérifié, rien à faire) ; `errors.py` ne le citait pas (vérifié) ;
   `routes_test.py`, `routes_models.py`, `rerank.py`, `rerank_pull.py`, `rerank_fetch.py`, `manage.py`,
   `web/static/screens/models-rerank.js`, `web/static/core/api/models.js`,
   `web/static/i18n/fr/models.json` (clés `extra_missing`, `extra_command` retirées) ; tests listés
   plus bas ; `.github/workflows/*.yml` ne passait pas `--extra rerank` (vérifié, rien à faire). Preuve :
   `grep -rn "extra.*rerank\|--extra rerank\|rerank\]"` sur `src/`, `tests/`, `README.md`, `AGENTS.md`,
   `.github/` ne rend plus rien (hors historique : `_bmad-output/planning-artifacts/epics.md` et
   `sprint-change-proposal-2026-10-21.md`, qui *décrivent* la story, et les artefacts d'implémentation
   antérieurs de 4.7/5.5, laissés tels quels comme journal).
4. **Imports paresseux, télémétrie, `test_layers.py` vert** : aucun changement sur l'emplacement des
   `import fastembed`/`disable_telemetry()` (toujours dans `load_fastembed`, `expected_bytes`,
   `rerank_fetch.main`, juste avant l'import). `tests/v2/unit/test_layers.py` : 58 passed.
5. **Spine amendée (AD-17, règle de coexistence)** : `ARCHITECTURE-SPINE.md` — AD-17 (« extra `rerank` »
   → dépendance de base, causes d'indisponibilité réduites à « modèle absent ou `ValueError` ») ; §Stack
   (ligne fastembed, revérifiée) ; §Structural Seed/Exploitation (ligne « Installation » : `uv sync`
   seul). La règle de coexistence vivante est **AD-2** (« Coexistence v1 / v2 »), pas AD-1 (Python
   3.11) : l'AC de `epics.md` cite « AD-1 », vérifié contre le document — c'est une imprécision du
   texte de la story reprise de la proposition de sprint ; AD-2 est la bonne, amendée en conséquence,
   et la divergence est consignée dans `.memlog.md`. Fait directement dans le style du document
   (mention datée), sans relancer `bmad-architecture` (consigne explicite de la story).
6. **Essai réel du bouton (seul téléchargement autorisé)** : serveur `wavelocalai-v2` lancé depuis le
   worktree (`--port 8799`, `--data-dir` temporaire, pas de navigateur — le lanceur n'en ouvre aucun) ;
   `POST /api/models/reranker/pull` → `{"run_id": "70f66…"}`, `GET /api/runs/{id}` passe de `running`
   à **`ok`** en ~26 s ; `GET /api/rag/settings` rend ensuite
   `{"model": "jinaai/jina-reranker-v2-base-multilingual", "available": true, "reason": null}` (plus
   d'`extra_installed`). Dossier `models/fastembed` du cache : ≈ 1,1 Go, conforme à l'annonce
   « environ 1 Go ». Aucun autre modèle (Ollama ou autre) téléchargé pendant la story. Serveur arrêté
   et données temporaires hors du dépôt (scratchpad de session).

## Règles écrites

- Périmètre strict story 9.5 : aucun écran hors « Reclassement des extraits », aucune autre dépendance
  touchée.
- `docs/maquette-v2/` (prototype HTML autonome, antérieur à l'écran réel) et
  `docs/audits/refonte-2026-10/0{2,3}-*.md` (notes d'audit historiques, base de la spine) citent encore
  l'extra `rerank` : laissés tels quels, comme les autres artefacts de planification gelés
  (`_bmad-output/planning-artifacts/epics.md`, `sprint-change-proposal-2026-10-21.md`) — ce sont des
  snapshots d'une décision passée, pas l'interface ni la doc courante de l'app.
  `_bmad-output/specs/spec-wavelocalai-v2/contrat/5-5.md` (contrat d'API vivant, cité par
  `contrat-api.md`) a lui été amendé : c'est une doc qui décrit le comportement actuel de l'API.

## Fichiers

- Dépendances : `pyproject.toml`, `uv.lock`.
- Code : `src/wavelocalai/rag/rerank.py`, `rerank_pull.py`, `rerank_fetch.py`, `rag/manage.py`,
  `rag/query.py` (docstring), `web/routes_models.py`, `web/routes_test.py`.
- Front : `web/static/screens/models-rerank.js`, `web/static/core/api/models.js`,
  `web/static/i18n/fr/models.json`.
- Doc : `README.md`, `_bmad-output/specs/spec-wavelocalai-v2/contrat/5-5.md`,
  `_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md`
  et `.memlog.md`.
- Tests : `tests/v2/unit/test_rag_rerank.py`, `test_rag_rerank_pull.py` ;
  `tests/v2/web/test_models_reranker_api.py`, `test_rag_rerank_api.py` ;
  `tests/v2/e2e/test_models_reranker.py` ; `tests/v2/integration/test_rag_rerank_local.py`.

## Rapport de dev

- Tests ciblés : `tests/v2/unit tests/v2/web -k "rerank or model or layers or telemetry"` → 414 passed
  (une 1ʳᵉ passe a montré 4 échecs : 2 réels, corrigés — voir ci-dessous — et 2 flakes du budget
  300 ms dus à la charge du poste pendant la passe, confirmés indépendants en relançant isolément,
  verts). `tests/v2/unit` complet : 1304 passed, 5 skipped.
- Corrections trouvées par les tests (hors périmètre prévu, nécessaires pour fermer la story) :
  - `test_rag_rerank_pull.py::test_fetch_exit_codes_...` : en ne neutralisant que
    `sys.modules["fastembed"]`, un test précédent avait déjà importé pour de vrai
    `fastembed.rerank.cross_encoder` (fastembed est maintenant une dépendance de base) ; `from X
    import Y` retrouvait alors ce sous-module réel en cache et **lançait un vrai téléchargement**
    réseau. Corrigé en neutralisant aussi `sys.modules["fastembed.rerank.cross_encoder"]`, comme le
    fait déjà `test_rag_rerank.py`.
  - `test_rag_rerank_pull.py::test_the_subprocess_runs_...` et
    `test_rag_rerank_api.py::test_a_model_that_cannot_be_loaded_...` : assertions et monkeypatchs sur
    l'ancien texte/attribut d'extra, réalignés.
- Contrôle rapide du projet (black, isort, règle d'architecture) : propre après reformatage
  (`uvx black@25.12.0`) de 3 fichiers touchés par les corrections ci-dessus.
- Pas de suite complète ni d'E2E (consigne de la story) ; pas d'Ollama utilisé.
- Reports : aucun — tout le périmètre de l'AC est couvert dans cette story.
