---
title: 'La parité avec la v1 est listée et la suite E2E est complète'
type: 'chore'
created: '2026-10-19'
status: 'review'
baseline_commit: 'ce1aac9'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/reports-v2-inventaire.md'
  - '{project-root}/docs/audits/refonte-2026-10/03-ux-front.md'
warnings: []
deferred: []
---

# Story 8.3 : parité v1 / v2 et suite E2E complète

## Objectif

Avant l'archivage de la v1 (8.4), la mainteneuse sait ce que chaque page et chaque onglet de la v1 devient dans la v2 (liste écrite, aucune fonction sans statut), la suite E2E joue les parcours de bout en bout sans recharger la page et prouve qu'aucune requête ne sort de `127.0.0.1`, un job CI nocturne la lance sur Linux, et le README montre la v2. Décision Q6 (variante B) : E2E en local sur Edge et en job nocturne.

## Critères d'acceptation et preuves

1. **Parité** : `docs/parite-v1-v2.md` marque chaque fonction des pages et onglets de la v1 (03 §1.1) « reprise » (écran), « remplacée par » (écran) ou « abandonnée » (motif) ; les fonctions sans équivalent ni décision d'abandon sont « abandonnée », motif « à confirmer par Anaël », et listées en tête (13 cas). Preuve : le document, relu contre le code de la v1 (`Accueil.py`, `home.py`, `views/`, `tabs/`, `rag_upload.py`, `rag_clear.py`) et contre la v2 (`i18n/fr/*.json`, `core/routes/*.js`, `agents/`, `inference/scenarios.py`, specs 5 à 7).
2. **Parcours E2E** : `tests/v2/e2e/test_parcours_*.py` jouent, chacun sans recharger la page (`window.__noReload` et une seule entrée de navigation, aides de `parcours.py`) :
   - `test_parcours_sobriete_modeles.py` : Modèles, Sobriété (session carbone qui suit une réponse sans clic), retour aux Modèles (installation chiffrée d'un modèle du catalogue), Sobriété qui garde son total ;
   - `test_parcours_agents.py` : Agent seul (outil, étapes, réponse d'un bloc, email validé avant tout envoi, faux SMTP local), onglet Équipe (mission de trois agents, rapport, téléchargement), retour à l'Agent seul ;
   - `test_parcours_evaluation_banc.py` : Évaluation (étapes, notes au fil de l'eau, « non évalué » avec sa raison), Banc d'essai (format violé dit, « Relancer le test », format respecté), retour à l'Évaluation et réouverture de son résultat sans relancer de modèle ;
   - Flow 1 (`test_flow1.py`) et Flow 2 (`test_flow2.py`) couvrent déjà leurs parcours ; Flow 2 reçoit la même preuve de non-rechargement (3 lignes). Mêmes doublures que les tests existants : Ollama n'est jamais sollicité.
3. **Rien ne sort de `127.0.0.1`** : le garde par test (fixture `context`, déjà là) est complété à l'échelle de la suite. Chaque contexte verse ses sorties dans un bilan (`SUITE_OUTSIDE`), et la fixture de session `no_request_left_the_machine` fait échouer la suite en fin de course si une seule requête est sortie, quel que soit le test. Preuve : `test_parcours_hors_machine.py` (une navigation vers un autre hôte est bloquée et relevée, puis retirée du bilan ; le bilan est vide en cours de suite) et un essai à vide : une fuite ajoutée à `SUITE_OUTSIDE` fait échouer la session.
4. **CI nocturne** : `.github/workflows/e2e-nocturne.yml` (`schedule` à 02 h 30 UTC + `workflow_dispatch`), Ubuntu, `uv sync --locked`, Chromium de Playwright installé par la CI, `pytest tests/v2 -m e2e`, 90 min au plus ; versions d'actions reprises de `tests.yml` (`checkout@v7`, `setup-uv@v10.3.0`). Mode d'emploi dans `AGENTS.md` (« La v2 »). `tests.yml` n'est pas touché.
5. **README** : la v2 d'abord (installation par `uv sync`, lanceur `uv run wavelocalai-v2`, port 8502, options, tests), cinq captures `docs/assets/v2-*.png` et un GIF `docs/assets/v2-demo.gif` (ces captures à la suite, 2,5 s chacune, Pillow), produits par `scripts/readme_captures_v2.py` (Playwright, doublures, aucun document réel). La doc et la démo de la v1 restent, sous « La v1 (Streamlit) » (la bascule est la 8.4).

## Règles écrites

- Aucun écran, composant, CSS ni module de `src/wavelocalai/` n'est modifié ; aucun hook de test n'a été nécessaire.
- Les tests `test_shell*.py`, `test_home.py`, `test_topbar.py`, `test_arena*.py`, `test_layers.py` et `contrat-api.md` ne sont pas modifiés (les parcours en importent des aides).
- Aucun bug d'écran révélé par les parcours : aucun `xfail`.

## Écarts et variantes conservatrices

- **`tests.yml` lance déjà les E2E dans chaque PR** (job `test-v2-e2e`, trois morceaux, bloquant, ajouté par la 5.0), alors que la décision Q6 (B) dit que les PR n'attendent pas les E2E. Consigne de la story : ne pas toucher `tests.yml`. Le job nocturne est ajouté à côté, sans retirer celui des PR ; **à trancher par Anaël** en 8.4 (retirer `test-v2-e2e` des PR, ou garder les deux).
- **Parité** : 13 fonctions de la v1 sans équivalent ni décision d'abandon, classées « abandonnée, à confirmer par Anaël » et listées en tête du document (B3, A8, D4, D5, E5, G5, G9, G10, G11, S4, S8, M5, M6). D4 est l'écart n° 12 du §7(d), G10 et G11 viennent des specs 6.5 et 6.6, B3 de la 7.4.
- **Évaluation** : le parcours rejoue les flux et instantanés fixés par le test (`page.route`, comme `test_evaluation.py`), pas le service d'évaluation du serveur : les routes de test n'ont pas de juge scripté pour l'Évaluation. Le service est prouvé côté serveur (`tests/v2/web`, 7.1).
- **GIF** : une suite de cinq captures (pas un enregistrement de parcours) ; l'enregistrement vidéo reste à faire à la recette humaine. La capture de l'Arène garde l'avertissement « Note peu fiable » de la doublure de juge (la route de test ne rend pas la taille du juge).
- **Captures** : les modèles s'appellent « Alpha 1B », « Factice 1B » : jamais un vrai nom de modèle avec une réponse simulée. Le matériel affiché (processeur, mémoire, accélérateur) est fictif : psutil du serveur doublé par un `sitecustomize` temporaire, GPU par `POST /api/test/gpu` (revue).
- **Flow 2** : modifié (repère de non-rechargement) bien que non listé comme interdit ; changement minimal, sans effet sur ses assertions.

## Fichiers

- Doc : `docs/parite-v1-v2.md`, `README.md`, `AGENTS.md`, `docs/assets/v2-*.png`, `docs/assets/v2-demo.gif`.
- CI : `.github/workflows/e2e-nocturne.yml`.
- Script : `scripts/readme_captures_v2.py`.
- Tests : `tests/v2/e2e/parcours.py` (aides), `test_parcours_sobriete_modeles.py`, `test_parcours_agents.py`, `test_parcours_evaluation_banc.py`, `test_parcours_hors_machine.py` ; `conftest.py` (bilan de suite) ; `test_flow2.py` (non-rechargement).

## Rapport de dev

- Tests ciblés (Edge, `-m e2e`) : les quatre fichiers `test_parcours_*.py` et `test_flow1.py`, `test_flow2.py` verts ; `tests/unit/test_telemetry.py`, `tests/app/test_socle.py` et `tests/v2/unit/test_shell_static.py` (qui lisent le README ou `AGENTS.md`) verts. Pas de suite complète (poste partagé).
- Contrôle rapide du projet (ruff, black, isort) propre.
- Reports : enregistrer un vrai GIF de parcours à la recette humaine ; trancher le job `test-v2-e2e` de `tests.yml` (écart ci-dessus) ; les 13 cas « à confirmer ».

## Revue

Revue Opus, une passe, branche à jour de master (0f140e3). Constats du second avis (Haiku) repris un à un, puis vérifications propres.

- low · second avis 1 · corrigé · `wait_for` évalue la condition par `page.evaluate` : un `.textContent` sur un élément absent lève au lieu d'attendre ; `?.` ajouté aux deux conditions.
- low · second avis 2 · rejeté · une fuite d'un test précédent fait déjà échouer ce test (fixture `context`) ; l'assertion vérifie l'état courant et la présence de la fixture de session autouse, sans dépendre de l'ordre pour être juste.
- low · second avis 3 · corrigé · `permissions: contents: read` dans `e2e-nocturne.yml`.
- low · second avis 4 · corrigé · docstring brute (`r"""`) : l'exemple PowerShell montre des antislashs simples.
- medium · second avis 5 · corrigé · Accueil et Sobriété montraient le processeur et la mémoire réels du poste (31,1 Go) et un GPU au nom du matériel de l'autrice : psutil du serveur doublé (`HARDWARE`, 18 %, 12,4 / 32 Go), GPU « GPU de démonstration » 8 Go ; captures et GIF régénérés et relus, README et écart mis à jour.
- low · second avis 6 · corrigé (commentaire) · portée du bilan dite dans `conftest.py` (requêtes et navigations, ni WebSocket ni worker ; un bilan par morceau de CI).
- low · second avis 7 · rejeté · décision d'Anaël déjà consignée (écart `tests.yml`), rien à faire en 8.3.
- low · revue · corrigé · capture Documents : la réponse scriptée des tests (« Le chat dort sur le canapé [1]. ») ne répondait pas à la question montrée ; réponse cohérente tirée de la note fictive.
- low · revue · corrigé · parité : la délégation entre agents était numérotée G10 en tête et G26 dans le tableau ; renumérotée G10.
- low · revue · corrigé · parité D4 : la route commune `GET /api/conversations/{id}.md` sert déjà toute conversation (sans les sources du RAG) ; piste mise à jour.
- info · revue · vérifié · trois statuts « à confirmer » relus contre le code : D4 (aucun bouton dans `documents.js`, commentaire explicite), M5 (aucun filtre dans `models.js`), G9 (`onSmallerModel` absent de `agents-crew.js`) ; S4 aussi (la pause de `sobriety.js` ne concerne que le flux d'un onglet masqué).
- Complexité : 0 constat (`SUITE_OUTSIDE` et `traffic` ne grossissent qu'en cas de fuite, aucun parcours complet par événement).
- Tests : `test_parcours_evaluation_banc.py` et `test_parcours_hors_machine.py` (Edge, `-m e2e`) verts ; script de captures relancé ; contrôle rapide propre. Pas de suite complète (poste partagé).
