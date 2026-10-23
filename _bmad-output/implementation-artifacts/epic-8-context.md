# Epic 8 Context: Remplacer la v1

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Faire de la v2 l'unique application du dépôt : solder la dette technique et les garde-fous relevés pendant le MVP, vérifier l'accessibilité complète (RGAA/WCAG, lisibilité en projection), lister la parité fonctionnelle avec la v1 et compléter la suite E2E, puis archiver la v1 et publier `2.0.0`. C'est l'epic de bascule : après lui, il n'existe plus qu'une application à installer et à maintenir.

## Stories

- Story 8.1 : Solder la dette technique relevée pendant le MVP
- Story 8.2 : Tous les écrans sont accessibles et lisibles en projection
- Story 8.3 : La parité avec la v1 est listée et la suite E2E est complète
- Story 8.4 : La v2 remplace la v1 (2.0.0)
- Story 8.5 : La CI passe sans relance

## Requirements & Constraints

- Budgets de performance : coquille < 300 ms en local, changement d'écran < 150 ms, premier rendu < 1 s ; aucune route de lecture > 300 ms Ollama arrêté (sonde ≤ 1 s, cache 5 s en lecture / 1 s pour le flux système). Les tests de budget doivent mesurer le deuxième meilleur de cinq appels après un appel d'échauffement, pas un appel isolé (8.5, décision du 2026-10-23).
- Accessibilité : RGAA 4.1 / WCAG 2.2 AA, axe-core sans violation ni exclusion sur chaque écran, en clair, en sombre et en mode projection (panneaux et dialogues ouverts compris) ; aucun défilement horizontal à 320 px CSS et 200 % de zoom, hors tableaux larges qui défilent dans leur conteneur.
- Tests : `tests/v2/unit` (sans serveur), `tests/v2/web` (TestClient), `tests/v2/e2e` (Playwright, marqueur `e2e`, exclu par défaut de la CI de PR) ; Ollama réel = marqueur `integration` ; base de test toujours en dossier temporaire. « Terminé » = code et tests verts vérifiables par l'agent, puis recette humaine en fin de lot ; la v1 doit rester lançable et intacte jusqu'à la bascule.
- Aucun test ne doit être supprimé, ignoré (`skip`, `xfail`) ni affaibli pour stabiliser la CI (8.5) ; un test retiré est remplacé par un équivalent, raison documentée.
- Décision Q5 (archivage v1) : à la bascule, `src/app`, `src/core`, les tests v1 (`tests/unit`, `tests/app`, `tests/integration`) et les scripts qui importent `src.core` (`benchmark_slm.py`, `audit_and_update.py`, `setup_models.py`, `setup_rag_models.py`) sortent de `master` ; la v1 reste accessible par son dernier tag `v1.3.x`. `scripts/sync_slm_results.py` et `scripts/build_catalog.py` restent fonctionnels.
- Décision Q6 (E2E en CI) : suite E2E complète en job CI Linux nocturne (Chromium de Playwright installé par la CI) plus en local (Edge via `WAVELOCALAI_E2E_CHROMIUM`, sinon Chromium Playwright) ; les PR n'attendent pas ce job nocturne.

## Technical Decisions

- AD-1/AD-2/AD-3 (bascule) : à 8.4, `requires-python` peut relever sa borne haute si 3.13 est vérifiée par la CI (sinon gardée, raison dans la spine §Deferred) ; le paquet passe en installation non éditable (`dev-mode-dirs` retiré, `packages` → `src/wavelocalai`) ; le script `wavelocalai` pointe sur la v2 (`wavelocalai-v2` disparaît) ; `version = "2.0.0"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0`, release GitHub, topic GitHub → `status-deployed`.
- AD-4 (frontière des imports) : le test AST `tests/v2/unit/test_layers.py` doit détecter aussi un import par attribut (`import wavelocalai` puis accès), par `importlib.import_module` ou par `__import__`, pas seulement `import wavelocalai.xxx` direct (8.1, report C1).
- AD-12 (migrations/sauvegardes) : une seule copie `.db.bak-N` gardée ; purgée (texte compris) après la migration suivante réussie ou lors d'un effacement (8.1).
- AD-15 (budgets de lecture) : le test de budget doit découvrir et mesurer aussi les routes `GET` posées avec `include_in_schema=False` ou servies par `Mount`, sans dépendre d'une classe interne de FastAPI ; aucune route ne doit prendre de texte saisi dans son chemin ou sa requête (pour que `uvicorn.access` ne le journalise jamais) (8.1).
- AD-18 (erreurs) : les textes de `ollama_down` n'ont qu'une source (API ou catalogue généré depuis `errors.py`) ; le panneau Ollando doit pouvoir forcer une sonde immédiate (bouton « Réessayer », budget 300 ms) sans attendre l'échéance du cache (8.1).
- AD-23 (exploitation) : message d'erreur du verrou doit distinguer un second serveur d'un échec de droits/disque ; `setup_logging` s'exécute après le verrou pour qu'un second lancement n'écrive rien dans le journal du serveur vivant ; sous Windows, Ctrl+Break doit fermer le store et relâcher le verrou.
- Pydantic : contraint sous 2.13 par crewai (v1) ; une fois crewai retiré à la bascule, relever à la dernière version vérifiée sur PyPI et par installation réelle, mettre à jour la spine §Stack, garder `tests/v2` vert.
- CI/dépendances à la bascule : job v1 supprimé, seul le job v2 reste ; `requirements.txt` et `constraints.txt` (chemin pip v1) retirés, installation uniquement par `uv sync` ; dépendances lourdes de la v1 (Streamlit, LangChain, LangGraph, CrewAI, Ragas, Chroma, torch…) sorties de `pyproject.toml`, `uv.lock` régénéré, taille du `.venv` mesurée et consignée dans `AGENTS.md`.
- Recette finale (8.4) : suite complète verte + recette humaine de Flow 1 et Flow 2 sur un PC pro 16 Go sans GPU, installé par `uv sync` seul.
- Stabilité CI (8.5) : horloge injectée ou marges indépendantes de la charge du runner pour les tests temporisés ; état partagé isolé par fixture pour les tests sensibles à l'ordre de la suite ; chaque test instable doit passer 20 fois de suite sur les trois OS avant clôture, et la liste des « tests instables connus » de `run-autonome.md` doit être vidée.

## UX & Interaction Patterns

- Contrat du front (AD-20) commun à tous les écrans : Custom Elements sans Shadow DOM, préfixe `wl-`, un seul store observable et un seul client SSE ; aucune mesure calculée côté navigateur.
- Base typographique et thèmes (UX-DR2) : pile Inter servie en local avec licence, `:focus-visible` à 3:1, `prefers-reduced-motion`, mode projection (rampe typographique agrandie, pied masqué) ; thèmes Clair (défaut), Sombre et Système.
- Responsive (UX-DR19) : ≥ 1440 px Arène 3-4 colonnes et panneaux à droite ; 1024-1439 px 2 colonnes et défilement ; 768-1023 px panneaux repliés sous menu ; < 768 px une colonne, Arène en onglets par modèle, saisie collante ; lisible à 200 % et 320 px sans défilement horizontal (hors tableaux larges).
- Vérification systématique (UX-DR25) : axe-core en E2E sur chaque écran livré, clair et sombre, zéro violation sans exclusion ; E2E vérifiant qu'aucune requête ne sort de `127.0.0.1`.
- Focus au premier chargement : point resté ouvert (report B16) à trancher et appliquer dans la grille RGAA de 8.2.

## Cross-Story Dependencies

- 8.1 (dette technique) doit être traitée avant que 8.2 et 8.3 ne s'appuient sur des garde-fous stables ; 8.4 dépend explicitement de 8.1 à 8.3 pour la recette finale et de 8.5 pour une CI fiable (8.5 est née du run de l'Epic 9, elle précède ou accompagne la clôture de 8.4).
- 8.4 est marquée « Avant : 8.4 » par 8.5 elle-même (origine : relances de CI pendant l'Epic 9) : la suite complète exigée par 8.4 doit être verte du premier coup, donc 8.5 doit être traitée avant ou avec la préparation finale de 8.4.
- 8.3 porte la décision Q6 (E2E en CI nocturne) et le report B21 (E2E sur Edge hors CI, mode d'emploi `AGENTS.md`) ; 8.4 porte la décision Q5 (archivage v1) et les reports B17 (contrainte `constraints.txt`/starlette obsolète à la bascule) et B18 (borne haute de Python).
- 8.1 inclut aussi des écarts du `sprint-change-proposal-2026-10-19.md` (§7(d)) sur du code déjà livré (Arène, Discussion, Base documentaire, sprite d'icônes) : ces correctifs touchent des écrans d'epics antérieurs (1 à 4) et doivent rester cohérents avec leur comportement documenté dans `EXPERIENCE.md`.
