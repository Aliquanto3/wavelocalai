---
title: 'Récupérer le reranker depuis l''écran Modèles'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '853957f'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-7.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-3.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-4.md'
warnings: []
deferred:
  - summary: >-
      Aucun vrai téléchargement n'a été fait : le téléchargement du reranker passe par un faux (`FakeFetcher`, octets simulés) ou par des tests de son processus avec un faux `fastembed`. À vérifier à la recette d'Anaël, avec l'extra `rerank` installé : le clic sur « Installer le reranker » télécharge `jinaai/jina-reranker-v2-base-multilingual` (environ 1,1 Go) dans `<données>/models/fastembed`, la barre avance (taille du dossier du cache), le run finit `ok`, la ligne passe à « Installé » et la recherche suivante dit « Reclassement… » sans redémarrage ; annuler en cours retire le dossier partiel.
    evidence: |-
      `rag/rerank_pull.py`, `rag/rerank_fetch.py`, `tests/v2/unit/test_rag_rerank_pull.py`, `tests/v2/web/test_models_reranker_api.py`, `tests/v2/e2e/test_models_reranker.py`.
    location: src/wavelocalai/rag/rerank_pull.py
    severity: medium
  - summary: >-
      Écarts non couverts par les décisions du 2026-10-19 : variante conservatrice gardée. (1) Pas de reprise d'un téléchargement annulé ou échoué : le dossier partiel est retiré (sinon `_model_in_cache`, qui ne regarde que la présence du dossier, dirait « installé » pour un modèle tronqué) ; un dossier qui existait avant le run est gardé. Un témoin `.models--<org>--<nom>.installing` (`rerank.install_marker`), écrit avant le téléchargement et retiré après la vérification, couvre l'arrêt brutal du serveur : tant qu'il reste, le modèle n'est pas installé et le `pull` suivant repart d'un dossier vide (revue). (2) La progression n'est pas celle de fastembed (qui n'en rend aucune) mais la taille du dossier du modèle dans le cache rapportée à la taille annoncée par fastembed (`size_in_GB`) ; elle plafonne à 99 % tant que le chargement de vérification tourne. (3) Le téléchargement se fait dans un processus à part, tué à l'annulation : un téléchargement `huggingface_hub` ne s'interrompt pas dans un thread. (4) Route : `POST /api/models/reranker/pull` plutôt qu'un paramètre de `POST /api/models/pull` (qui ne prend que des noms d'Ollama), même type de run `pull`. (5) Sans l'extra, la route répond `422 invalid_request` (aucun code nouveau) et le texte « Installez l'option de reclassement : uv sync --extra rerank » est celui de l'écran. (6) `reranker_failed` est une quatrième cause de `pull_failed` (message propre, sans « La liste des modèles est inchangée »).
    evidence: |-
      `rag/rerank_pull.py`, `rag/rerank.py::RerankerService.refresh`, `errors.py::PULL_CAUSES`, `contrat-api.md` (« Modèles : reranker »).
    location: src/wavelocalai/rag/rerank_pull.py
    severity: low
---

# Story 5.5 : récupérer le reranker depuis l'écran Modèles

## Objectif

Sur `#/modeles`, une consultante installe le reranker local d'un clic, voit la progression chiffrée, et la recherche documentaire reclasse les extraits ensuite, sans redémarrer et sans commande hors de l'app (sauf l'extra `rerank` lui-même).

## Critères d'acceptation et preuves

1. **Non installé** : avec l'extra et sans le modèle dans le `cache_dir`, la section « Reclassement des extraits » dit « Non installé », la raison de `GET /api/rag/settings` (`reranker.reason`) et un bouton « Installer le reranker ». Preuve : `e2e::test_a_missing_model_says_not_installed_*`, `web::test_settings_say_whether_the_extra_*`.
2. **Installation** : le clic crée un run `pull` (`POST /api/models/reranker/pull`) ; `disable_telemetry()` précède l'import de fastembed (test AST de 4.7, qui couvre aussi `rerank_fetch.py` et `rerank_pull.py`) ; le téléchargement va dans le `cache_dir` ; `pull_progress` porte `reranker: true` et les octets ; un `pull` en cours (modèle ou reranker) rend `409 run_busy`, et l'écran désactive les autres « Installer » avec leur raison. Preuve : `web::test_the_pull_reports_bytes_*`, `::test_a_pull_in_progress_refuses_*`, `unit/test_rag_rerank_pull.py`, `e2e::test_installing_shows_the_bytes_*`.
3. **Sans redémarrage** : à la fin `ok`, l'état est relu avant `run_ended` (`RerankerService.refresh`, qui oublie aussi un échec de chargement retenu) ; la recherche suivante charge le modèle, toujours en `local_files_only=True`. Preuve : `web::test_the_pull_reports_bytes_*` (la recherche score), `::test_a_loading_failure_is_forgotten_*`.
4. **Sans l'extra** : bouton `aria-disabled` (focalisable) avec « Installez l'option de reclassement : `uv sync --extra rerank` » ; aucun appel, aucun processus, aucune socket (test sans réseau). Preuve : `web::test_without_the_extra_nothing_is_started_*`, `e2e::test_without_the_extra_the_button_is_disabled_*`.
5. **Annuler et échouer** : « Annuler » tue le processus, le run finit `cancelled`, le dossier partiel est retiré, la ligne reste « Non installé » ; un échec finit `error` avec `pull_failed` (`cause: reranker_failed`) affiché dans la section, et on peut relancer. Preuve : `web::test_cancelling_*`, `::test_a_failed_download_*`, `e2e::test_cancelling_*`, `::test_a_failed_download_*`.
6. **Reprise de l'écran** : une page rechargée pendant l'installation la rejoint dans la section du reranker. Preuve : `e2e::test_leaving_the_screen_and_coming_back_*`.
7. **Accessibilité et structure** : axe-core sans violation (clair, sombre ; sans extra, en cours) ; aucun JS au-delà de 600 lignes. Preuve : `e2e::test_axe_*`, `unit/test_models_static.py`.

## Hors périmètre

Fiche du modèle et « Sur d'autres postes » (5.6). Le choix d'un autre modèle de reranker et la suppression du reranker du cache ne sont pas demandés.

## Notes de développement

- Serveur : `rag/rerank_pull.py` (`RerankerPullService`, `fetch_in_subprocess`, `FakeFetcher`), `rag/rerank_fetch.py` (processus de téléchargement), `rag/rerank.py` (`extra_installed`, `refresh`, `use_loader`, `extra_override`), `rag/manage.py` (`reranker.extra_installed`), `inference/pull.py` (`ProgressThrottle`), `errors.py` (`reranker_failed`), `web/routes_models.py`, `web/app.py`, `web/routes_test.py`.
- Front : `screens/models-rerank.js` (section), `models-pull.js` (le même contrôleur sert le reranker : `start(tag, {reranker})`, `activeReranker`), `models.js` (assemblage ; `api.ragSettings` lu hors de la lecture des listes pour ne pas la ralentir), `core/api/models.js` (`pullReranker`), `i18n/fr/models.json`, `models.css`.
- Contrat : sous-section « Modèles : reranker (story 5.5) » de `contrat-api.md`.
- Tests réalignés : `e2e/test_models_install.py` (quatre `h2`), `unit/test_models_static.py` (nouveau fichier), `unit/test_pull.py` (cause `reranker_failed`).

## Rapport de dev

- Joué (poste partagé : jamais la suite complète) : `tests/v2/unit` en entier ; `tests/v2/web` ciblé (`test_models_reranker_api`, `test_models_install_api`, `test_models_manage_api`, `test_rag_rerank_api`) ; E2E de l'écran Modèles seulement (`test_models_install`, `test_models_manage`, `test_models_reranker`, Edge).
- Aucune dépendance nouvelle, aucun fichier d'état touché.

## Revue

Revue Opus du 2026-10-19 (diff 853957f..f631ee2, branche à jour de master), constats du second avis (Haiku) repris un par un.

- medium · second avis 1 · corrigé · un arrêt brutal du serveur pendant le téléchargement laissait le dossier partiel, vu « Installé » au redémarrage (`start()` refusait « déjà installé », la recherche chargeait un modèle tronqué). Témoin `install_marker` écrit avant le téléchargement, retiré après la vérification ; `_model_in_cache` le respecte ; le `pull` suivant retire le dossier partiel. Un modèle mis dans le cache à la main (procédure de la 4.7) n'a pas de témoin et reste installé. Tests : `web::test_a_download_cut_by_a_hard_stop_*`, `::test_the_marker_marks_an_installation_in_progress_*`.
- low · second avis 2 · rejeté · `expected_bytes` appelle bien `disable_telemetry()` avant d'importer fastembed (test AST de 4.7) ; l'import dans le processus serveur est le même que celui de `load_fastembed` à la première recherche, sans téléchargement (`list_supported_models` est une liste statique).
- low · second avis 3 · corrigé par le témoin · une `_load_once` lancée pendant le téléchargement pouvait retenir un échec après `refresh()`. Pendant l'installation, le témoin rend le modèle « non installé » : `score()` ne lance plus de chargement, la course n'a plus de point de départ.
- low · second avis 4 · rejeté · `hub.stop` annule la tâche sans l'attendre, mais uvicorn sert dans `asyncio.run`, qui annule puis attend les tâches restantes à la fermeture de la boucle : `fetch_in_subprocess` tue alors le processus. Reste l'arrêt brutal (processus parent tué) : le processus `rerank_fetch` peut survivre et finir son téléchargement ; le témoin garde l'état « non installé », et le `pull` suivant repart de zéro. Reporté à la recette : tuer le serveur pendant l'installation, vérifier dans le Gestionnaire des tâches que le processus `rerank_fetch` ne reste pas longtemps, puis relancer l'installation.
- Complexité : 0 constat · `folder_size` parcourt le dossier du modèle (quelques fichiers) une fois par intervalle de progression ; `pull_progress` est limité par `ProgressThrottle` ; côté écran, aucun parcours d'une structure qui grossit.
- Tests joués (poste partagé, pas la suite complète) : `tests/v2/web/test_models_reranker_api.py`, `test_rag_rerank_api.py`, `test_models_install_api.py`, `test_models_manage_api.py`, `tests/v2/unit/test_rag_rerank_pull.py`, `test_rag_rerank.py`, `test_pull.py`, `test_telemetry.py`, `test_layers.py` ; E2E Edge `test_models_reranker`, `test_models_install`, `test_models_manage` (43 réussis) ; ruff sur les fichiers touchés.
