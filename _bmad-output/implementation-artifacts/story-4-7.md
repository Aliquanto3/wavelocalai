---
title: 'Reclasser les extraits avec un reranker local, s''il est là'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '2cc063f'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-6.md'
warnings: []
deferred:
  - summary: >-
      Écarts de la §7 (d) de `sprint-change-proposal-2026-10-19.md` qui touchent la 4.7, non tranchés : variante la plus conservatrice gardée. (12d) Moment de `retrieval_step` : comme en 4.6, une étape est publiée à sa **fin** ; pour que « Reclassement… » soit dit pendant le calcul, l'étape `search` porte `reranking: true` (le serveur annonce que le reclassement suit, le front ne devine rien) et l'étape `rerank` fait avancer l'étape suivante. (18) nom des champs d'événements : `retrieval_step` gagne `reranking`, `candidates`, `kept`, `fallback: "unavailable"` ; `sources[]` gagne `rerank_score` ; `GET /api/rag/settings` gagne `reranker: {model, available, reason}` ; consignés dans `contrat-api.md`, à ratifier. Aucun autre écart du §7 (d) ne concerne la 4.7 (§7 (a) : « Aucun »).
    evidence: |-
      `rag/query.py::_search`, `_rerank`, `wl-run-status.js::stageAfter`, `contrat-api.md` (événements `sources`, `retrieval_step`, Base documentaire), `test_rag_rerank_api.py`.
    location: _bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md
    severity: low
  - summary: >-
      Choix de conception à confirmer. (1) Modèle par défaut `jinaai/jina-reranker-v2-base-multilingual` (`[rag] reranker_model`), choisi multilingue pour des documents en français ; il pèse environ 1 Go. Il n'a pas pu être vérifié contre fastembed 0.9.0 : l'extra n'est pas installé dans `.venv` et aucun téléchargement n'est permis. L'API utilisée (`TextCrossEncoder(model_name, cache_dir, local_files_only=True)`, `.rerank(query, documents)`) et la liste des modèles pris en charge sont à confirmer en recette, avec le README. (2) Le reclassement vaut pour toute stratégie : chaque recherche prend `3 × top_k` candidats (60 au plus) ; les scores du reranker se comparent à la question de l'utilisateur, jamais à l'hypothèse de HyDE ni à une reformulation. (3) `relevance_label` et `raw_score` restent la similarité des vecteurs ; l'ordre et le rang suivent le reranker, donc un libellé « éloignée » peut précéder « proche » ; `rerank_score` (score brut du modèle) est ajouté, non affiché. (4) Le calcul du reclassement (CPU) n'a pas de feuille de run : AD-10 ne mesure que les `embedding` et `generation`, son énergie n'est pas comptée. (5) `status()` ne charge rien : il lit l'extra et la présence du dossier du modèle dans le cache ; un dossier présent mais illisible n'est découvert qu'au premier chargement (retenu ensuite, aucune seconde tentative avant redémarrage), et l'étape `rerank` le dit (`fallback`). (6) Le lien « Récupérer le modèle de reclassement depuis l'écran Modèles » de la maquette n'est pas posé : la récupération est la story 5.5 (hors run).
    evidence: |-
      `rag/rerank.py`, `rag/strategies.py::rerank_pool`, `rerank_top`, `merge_best`, `rag/query.py::build_sources`, `wavelocalai.toml`.
    location: src/wavelocalai/rag/rerank.py
    severity: medium
  - summary: >-
      Test AST d'AD-21 : `tests/v2/unit/test_telemetry.py::check_telemetry_order` existe déjà (story 1.x) et relève tout module v2 qui importe `fastembed` ou `huggingface_hub` sans `disable_telemetry()` avant, dans la même fonction ; la 4.7 ne le recrée pas, elle y ajoute le premier vrai importeur (`rag/rerank.py::load_fastembed`) et un test qui garantit que le contrôle n'est pas vide (`test_rag_rerank.py::test_fastembed_is_imported_only_inside_a_function_...`).
    evidence: |-
      `tests/v2/unit/test_telemetry.py`, `tests/v2/unit/test_rag_rerank.py`, `tests/v2/unit/test_layers.py`.
    location: tests/v2/unit/test_telemetry.py
    severity: low
---

# Story 4.7 : reclasser les extraits avec un reranker local, s'il est là

## Objectif

Quand un reranker local est déjà présent sur le poste, chaque recherche du RAG reclasse ses candidats avant de répondre ; sinon la recherche garde l'ordre des vecteurs et l'écran dit pourquoi. **Aucun téléchargement, jamais** (AD-17) : la récupération du modèle est un geste de l'utilisateur hors de l'app (README) jusqu'à l'écran Modèles (story 5.5).

## Critères d'acceptation et preuves

1. **Reranker présent** : le modèle fastembed est chargé avec `local_files_only=True` depuis `<données>/models/fastembed`, dans un thread, après `disable_telemetry()` ; les extraits sont reclassés et le `run-status` dit « Reclassement… ». Preuve : `test_rag_rerank.py::test_the_model_is_loaded_offline_from_the_cache_after_the_telemetry_is_cut` (ordre, arguments, sur un faux fastembed), `::test_the_real_fastembed_never_reaches_the_network_with_an_empty_or_partial_cache` (vrai fastembed, saute sans l'extra), `::test_the_model_is_loaded_once_in_a_thread_...`, `::test_a_question_cancelled_during_the_first_load_does_not_start_a_second_one` ; `test_telemetry.py::test_real_package_applies_telemetry_opt_outs_in_order` (AST) et `test_rag_rerank.py::test_fastembed_is_imported_only_inside_a_function_after_the_telemetry_is_cut` ; web `test_rag_rerank_api.py::test_a_present_reranker_reclassifies_...`, `::test_the_pool_is_wider_than_top_k_...`, `::test_hyde_and_self_rag_score_against_the_question_...` ; E2E `test_a_present_reranker_says_reclassement_and_reorders_the_excerpts`, `::test_the_reranking_keeps_only_top_k_excerpts`, `::test_the_stage_after_the_reranking_is_the_one_of_the_strategy`.
2. **Reranker absent** (extra, modèle absent du cache, `ValueError` au chargement) : le RAG tourne sans reranker, `GET /api/rag/settings` rend `reranker: {model, available: false, reason}` et l'écran dit « Reclassement indisponible : <raison>. » (Discussion, Réglages avancés ; Base, réglages) ; aucun téléchargement n'est tenté. Preuve : `test_rag_rerank.py::test_a_value_error_at_load_...`, `::test_a_missing_extra_...`, `::test_the_status_names_...` (2), `::test_a_load_failure_is_kept_and_never_retried` (réseau coupé par une garde) ; web `::test_without_a_reranker_nothing_changes_and_the_settings_say_why`, `::test_a_model_that_cannot_be_loaded_is_remembered_and_never_downloaded` ; E2E `test_without_a_reranker_the_screen_says_why_and_the_search_keeps_its_order`, `test_the_settings_summary_and_form_come_from_the_server` (Base).
3. **README** : « Reranker local de la v2 » dit comment remplir le cache hors de l'app.
4. **Annulation et pannes** : annuler pendant le reclassement termine le run en `cancelled` sans `sources` ni réponse ; un reranker qui échoue en route laisse l'ordre des vecteurs (`fallback: unavailable`). Preuve : `::test_cancelling_during_the_reranking_ends_the_run_without_sources`, `::test_a_reranker_that_fails_while_scoring_keeps_the_vector_order`.

## Règles écrites

- **Candidats** : avec un reranker, la recherche prend `rerank_pool(top_k)` = `max(top_k, min(3 × top_k, 60))` candidats, le reranker les note contre la question, et `rerank_top` garde les `top_k` meilleurs (égalité : le plus proche), chacun avec `rerank_score`. Un seul candidat : pas de reclassement. Self-RAG : `merge_best` ordonne par `rerank_score` si tous en ont un, sinon par distance.
- **Étapes** : `search` porte `reranking: true` quand un reclassement suit, puis `rerank {candidates, kept, round?, fallback?}` ; `wl-run-status` : `search` + `reranking` = « Reclassement… », `rerank` = étape suivante de la stratégie.
- **État** : `RerankerService.status()` ne charge rien (extra installé, dossier du modèle dans le cache, échec retenu) ; le chargement se fait au premier calcul, une fois, sous verrou ; un échec est retenu sans seconde tentative.

## Notes de développement

- `rag/rerank.py` (nouveau) : `RerankerService`, `load_fastembed`, `FakeReranker` (tests : `lexical`, `reverse`, `delay_s`). Copié puis adapté de la v1 (`models_factory.get_reranker_model`, sentence-transformers) : la v2 n'a pas le repli réseau. Créé dans `create_app` (`app.state.reranker`), passé à `RagService` et `RagBaseService`.
- Test seulement : `POST /api/test/reranker {mode: lexical | reverse | absent, delay_s, reason}` et `GET` (calculs faits).
- Réglage `[rag] reranker_model` (`wavelocalai.toml`, `RagSettings`).
- Front : l'état est celui du serveur (`settings.reranker`), le front ne calcule rien (AD-20) ; `documents-chat-settings.js` (ligne `docs-rerank` dans Réglages avancés), `documents-settings.js` (résumé « reclassement actif | indisponible » et ligne, comme la maquette), `wl-run-status.js` (`reranking`).
- Réaligné : `test_documents_manage.py` (résumé des réglages de la Base).
- La revue de la 4.6 (cb98d39 : budget de notation, `guard=` sur les appels de modèle de stratégie) est fusionnée à la fin par l'orchestrateur ; la 4.7 n'ajoute aucun appel au modèle de chat (le reranker n'est pas un `ChatModel`), donc aucun `guard=` à poser.

## Fichiers

- `src/wavelocalai/rag/rerank.py` (nouveau), `rag/strategies.py`, `rag/query.py`, `rag/manage.py`, `config.py` + `wavelocalai.toml`, `web/app.py`, `web/routes_rag_base.py`, `web/routes_test.py`
- `src/wavelocalai/web/static/components/wl-run-status.js`, `screens/documents.js`, `documents-chat-settings.js`, `documents-settings.js`, `documents.css`, `i18n/fr.json`
- `README.md`, `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md`
- Tests : `tests/v2/unit/test_rag_rerank.py`, `tests/v2/web/test_rag_rerank_api.py`, `tests/v2/e2e/test_discussion_rerank.py`, `tests/v2/integration/test_rag_rerank_local.py` (saute sans extra ni cache) ; complétés ou réalignés : `test_config.py`, `test_discussion_static.py`, `test_documents_manage.py`

## Vérification

Ciblée (la suite complète est lancée par l'orchestrateur). Unitaires et web : `test_rag_rerank.py` (20), `test_rag_rerank_api.py` (9), `test_rag_strategies.py`, `test_rag_settings.py`, `test_discussion_static.py`, `test_documents_static.py`, `test_config.py`, `test_layers.py`, `test_telemetry.py`, `test_rag_*_api.py` : verts (deux tests de `test_rag_api.py` ont échoué une fois sous charge, verts relancés seuls). E2E sur Edge (`-m e2e`) : `test_discussion.py` 18, `test_discussion_strategies.py` 14, `test_discussion_rerank.py` 8 et `test_documents_manage.py` 14, soit 54 verts. Contrôle rapide propre. Le test d'intégration saute proprement (extra absent). Jamais lancé avec le vrai modèle : à jouer en recette après `uv sync --extra rerank` et le remplissage du cache.

## Journal

- 2026-10-19 · dev : spec, `rag/rerank.py`, branchement dans la recherche, réglages (Discussion, Base), README, contrat, tests unitaires et web verts.
- 2026-10-19 · revue (Opus) : chargement partagé et protégé de l'annulation, preuve hors ligne sur le vrai fastembed 0.9.0 ; voir « Revue ».

## Revue

Revue Opus du 2026-10-19, une passe, sur `feat/v2-rag-reranker` (8e1ff2f).

- medium · second avis 3 · corrigé : une question annulée pendant le premier chargement laissait `_reranker` vide et la suivante relançait un second chargement pendant que le premier tournait encore dans son thread (2 × ~1 Go). `_load` partage désormais une tâche unique protégée par `asyncio.shield` ; test `test_a_question_cancelled_during_the_first_load_does_not_start_a_second_one` (rouge sur l'ancien code, vert après).
- low · second avis 1 · rejeté : dans fastembed 0.9.0, avec `local_files_only=True`, `download_files_from_huggingface` boucle sur les sources du cache et rend ou lève avant `model_info` et `list_repo_tree` (ces appels ne sont atteints qu'en ligne) ; `download_model` retombe ensuite sur `retrieve_model_gcs(local_files_only=True)`, qui lève `ValueError` sans réseau. Prouvé en exécutant le vrai fastembed 0.9.0 (installé hors ligne depuis le cache uv dans un venv jetable), réseau coupé hors bouclage local : cache vide et dossier de modèle incomplet donnent « n'a pas pu être chargé », aucune tentative de connexion. Forcer `HF_HUB_OFFLINE` est donc inutile.
- low · second avis 2 · corrigé : la preuve « aucun accès réseau » ne portait que sur un faux fastembed. Ajout de `test_the_real_fastembed_never_reaches_the_network_with_an_empty_or_partial_cache` (vrai chemin, saute sans l'extra, donc en CI) ; joué vert dans le venv jetable avec fastembed 0.9.0 ; critère 1 réécrit.
- low · second avis 4 · rejeté : un tour Self-RAG à un seul candidat suppose une base d'au plus un extrait (chaque tour cherche `rerank_pool(top_k)` candidats dans la même base) ; la fusion n'a alors qu'un extrait à ordonner. Le repli sur la distance quand un tour a échoué (`fallback`) est voulu.
- low · revue · reporté : `_model_in_cache` compare le nom du modèle au dossier du cache ; pour un modèle dont la source Hugging Face diffère du nom (`BAAI/bge-reranker-v2-m3` → `onnx-community/bge-reranker-v2-m3-ONNX`) ou une ancienne copie `fast-<nom>`, `status()` dirait « absent » alors que le chargement réussirait. Sans effet sur le modèle par défaut (`jinaai/jina-reranker-v2-base-multilingual`, source au même nom, pris en charge par fastembed 0.9.0 : vérifié dans sa liste). À traiter avec l'écran Modèles (story 5.5), qui saura quel dossier il remplit.
- low · revue · reporté (AD-10) : l'énergie du reclassement (CPU, jusqu'à 60 candidats) n'est pas comptée, faute de feuille de run ; à décider dans la spine (feuille `rerank` ou part de la feuille `embedding`).
- info · revue · vérifié : raison affichée si absent (Discussion et Base, depuis le serveur), borne des candidats (`max(top_k, min(3 × top_k, 60))`), scores contre la question pour HyDE et Self-RAG, couches (`fastembed` importé dans `load_fastembed` après `disable_telemetry()`), i18n en français, fichiers JS sous 600 lignes (`documents-base.js` 570, `documents.js` 569). Complexité : 0 constat (rien ne grossit pendant l'exécution hors `FakeReranker.calls`, réservé aux tests).
- Vérification de la revue : `test_rag_rerank.py` 21 verts + 1 sauté (vrai fastembed, joué vert à part), unit/web `-k "rag or rerank or telemetry or layers or discussion_static or config"` 303 verts, E2E Edge `test_discussion_rerank.py` 8 verts, contrôle rapide propre. Recette avec le vrai modèle toujours à faire (`uv sync --extra rerank`, cache rempli, `tests/v2/integration/test_rag_rerank_local.py`).
