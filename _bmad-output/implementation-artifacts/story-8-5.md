---
title: 'Story 8.5 : La CI passe sans relance'
type: 'bugfix'
created: '2026-10-23'
status: 'review'
baseline_commit: '355fd2cd2e60b244358eeebf8487c9a9dee1a93f'  # pragma: allowlist secret
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-8-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur le run de l'Epic 9, 5 relances de job sur 12 PR, toutes dues à sept tests qui dépendent de la charge du runner, d'une fenêtre de temps ou de l'ordre de la suite, jamais à un défaut réel. Un contrôle rouge ne signale donc plus forcément un défaut, et la suite verte exigée par 8.4 n'est pas garantie du premier coup.

**Approach:** Rendre chaque test déterministe sans l'affaiblir : mesure de latence robuste à un appel lent isolé, attente d'un état stable de l'interface, marges d'horloge indépendantes de la vitesse du runner, état partagé isolé par fixture. Prouver la stabilité par un workflow CI à la demande qui joue ces tests 20 fois sur les trois OS.

## Boundaries & Constraints

**Always:**
- Budget de latence inchangé : 300 ms (NFR1, NFR2, AD-15). Chaque test de latence échoue encore si la route devient vraiment lente : un test le prouve en ralentissant artificiellement la route (doublure ou `monkeypatch`), sans réseau.
- Aucun test supprimé, ignoré (`skip`, `xfail`) ni affaibli ; un test remplacé l'est par un équivalent, avec la raison dans les Implementation Notes.
- Si l'enquête montre qu'un état est réellement trop bref pour l'utilisateur (résumé de l'Arène visible moins d'une seconde), le défaut est corrigé dans l'écran, pas dans le test.
- Aucun test n'exige Ollama, une clé, un téléchargement ou le réseau ; E2E sous le marqueur `e2e`.
- Nouvelle dépendance de test seulement si vérifiée sur PyPI et ajoutée par `uv add --dev` (pas de version écrite de mémoire) ; sinon boucle shell.

**Never:**
- Pas de relance automatique (`pytest-rerunfailures`, `--reruns`, `retry` dans le workflow).
- Ne pas toucher `scripts/benchmark_slm.py`, `benchmarks/`, `src/core/`, `data/`.
- Pas de relèvement de budget ni de `timeout` E2E pour masquer une attente mal posée.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Appel lent isolé | 1 appel sur N à 400 ms (charge du runner), les autres à 50 ms | Test de latence vert | N/A |
| Route vraiment lente | Route ralentie de 400 ms à chaque appel | Test de latence rouge, message avec les temps mesurés | Assertion explicite |
| Runner chargé (Arène) | Lanes et délai de lane sur un runner lent | Statut `done` pour les deux lanes | N/A |
| Test d'accessibilité en suite | Joué après les autres tests du module | Vert, comme joué seul | N/A |

**Décision (Anaël, 2026-10-23) — statistique de latence :** un appel d'échauffement, puis le deuxième meilleur de cinq mesures, pour les trois tests de latence, par un helper commun. La médiane de 5 dépassait déjà le budget une fois sur deux en CI (`test_shell.py:95-99`). Le critère de la story 8.5 dans `epics.md` est ajusté : « deuxième meilleur de cinq appels après un échauffement » remplace « médiane de plusieurs appels ». `test_read_budget.py` (meilleur de trois sur app neuve) n'est pas touché.

</frozen-after-approval>

## Code Map

- `tests/v2/web/test_conversations_api.py:252-272` -- `test_routes_with_a_path_parameter_stay_under_the_read_budget` : un seul appel par chemin, `assert elapsed < 0.3`.
- `tests/v2/web/test_model_card_api.py:338-350` -- `test_the_card_answers_under_300_ms_with_ollama_down` : un appel par tag, `max(timings) < 0.3`.
- `tests/v2/e2e/test_shell.py:82-118` -- `shell_timings` et `test_shell_renders_under_300_ms_without_waiting_for_the_api_ollama_stopped` : déjà 1 échauffement puis deuxième meilleur de 5 ; à aligner sur le helper commun.
- `tests/v2/web/test_read_budget.py:24,65-92` -- `BUDGET_S = 0.3`, meilleur de trois sur app neuve : modèle à réutiliser, ne pas changer son comportement.
- `tests/v2/e2e/test_arena.py:1472-1497` -- test axe à quatre modèles : `fake:a` dort 2,5 s, attente `.arena-summary` visible (15 s dépassées à 1440 px).
- `src/wavelocalai/web/static/screens/arena.js:62,166-177,411` -- `showSummary = running()` ; `run_ended` remet la configuration. `arena-summary.js:1-3` : rôle du résumé. Diagnostiquer pourquoi le résumé n'apparaît que 0,3 à 0,5 s, ou pas du tout, alors que `fake:a` tourne encore.
- `tests/v2/e2e/test_models_manage.py:254-279` -- focus lu par `evaluate(document.activeElement…)` sans attente ; remplacer par `expect(locator).to_be_focused()`.
- `tests/v2/web/test_arena_api.py:203-213` -- `test_lane_timeout_counts_from_the_slot_not_from_the_wait` : 0,25 s par lane pour un délai de 0,4 s (marge de 0,15 s).
- `src/wavelocalai/inference/streaming.py:125` -- délai de lane par `asyncio.timeout(timeout_s)`, horloge de la boucle ; `arena.py:137,154,203` utilise `time.monotonic()`. Ne pas changer le code de production pour ce test.
- `tests/v2/e2e/test_accessibilite.py:723-733` -- un `h1` et un titre distinct par écran ; fixture `app` sur `server` de scope module (`tests/v2/e2e/conftest.py:167`), `browser` de scope session (`:255`). Échoue après d'autres tests (vu sur `/documents/base`, `run-autonome.md:125`).
- `.github/workflows/tests.yml`, `.github/workflows/e2e-nocturne.yml` -- jobs existants ; nocturne déjà en `workflow_dispatch` sans entrées.
- `_bmad-output/implementation-artifacts/run-autonome.md:45` -- liste des tests instables connus à vider.

## Tasks & Acceptance

**Execution:**
- [x] `tests/v2/latency.py` (nouveau, ou `tests/v2/conftest.py`) -- helper de mesure : un échauffement, cinq mesures, deuxième meilleur comparé au budget, message d'échec avec toutes les mesures -- un seul endroit pour la règle.
- [x] `_bmad-output/planning-artifacts/epics.md:1957` -- remplacer « la médiane de plusieurs appels après un appel d'échauffement » par « le deuxième meilleur de cinq appels après un appel d'échauffement » -- décision du 2026-10-23.
- [x] `tests/v2/web/test_conversations_api.py`, `tests/v2/web/test_model_card_api.py`, `tests/v2/e2e/test_shell.py` -- utiliser le helper ; ajouter un test qui ralentit la route (et le chargement de la coquille, par route Playwright retardée) et vérifie l'échec du helper -- preuve que le test mord encore.
- [x] `src/wavelocalai/web/static/screens/arena.js` et/ou `tests/v2/e2e/test_arena.py` -- diagnostiquer, puis corriger l'écran si le résumé disparaît trop tôt ; sinon attendre un état stable (`expect(...).to_be_visible()`, attribut d'état) -- respecte D-16. Diagnostic : pas de défaut d'écran (le backend attend toutes les lanes avant `run_ended`) ; cause trouvée à la revue : « mot » répété 400 fois déclenchait le détecteur de répétition (story 9.2), qui arrêtait les lanes aussitôt ; texte sans répétition, `fake:a` qui ne finit pas seul et run arrêté par « Arrêter » après l'audit, délai par défaut rendu.
- [x] `tests/v2/e2e/test_models_manage.py` -- attentes de focus par `expect(...).to_be_focused()`.
- [x] `tests/v2/web/test_arena_api.py` -- marges proportionnelles : durée de lane et délai tels que « compté depuis l'attente » dépasse nettement et « compté depuis la place » reste nettement en dessous (ex. 1 s par lane, délai 1,5 s), sans changer la production.
- [x] `tests/v2/e2e/conftest.py` et/ou `test_accessibilite.py` -- trouver l'état partagé fautif, l'isoler par fixture ; le test passe seul et en suite.
- [x] `.github/workflows/stabilite.yml` (nouveau) -- `workflow_dispatch`, plus `pull_request` filtré sur ce seul fichier (revue : `workflow_dispatch` n'est lançable qu'une fois le fichier sur `master`), matrice ubuntu/windows/macos, Python 3.12, `uv sync --locked`, Chromium de Playwright, boucle de 20 passes sur les sept tests, arrêt au premier échec.
- [ ] `_bmad-output/implementation-artifacts/run-autonome.md` -- vider la liste des tests instables connus (ligne 45) en citant la story 8.5 ; vérifier qu'`AGENTS.md` ne mentionne aucune relance (rien à y changer). Revue : retiré de la PR de story (fichier d'état du run, PR `chore/etat-run` à part), à faire par l'orchestrateur une fois `stabilite.yml` vert.

**Acceptance Criteria:**
- Given le workflow `stabilite.yml` lancé sur la branche, when il se termine, then les sept tests passent 20 fois de suite sur les trois OS.
- Given la PR de la story, when sa CI tourne trois fois de suite, then les trois passes sont vertes sans relance de job.
- Given la story fusionnée, when trois nuits de `e2e-nocturne.yml` s'enchaînent, then elles sont vertes ; ce constat se note dans la recette et ne bloque pas la fusion.

## Implementation Notes

- `tests/v2/latency.py` (nouveau) : `second_best_of_five` / `assert_under_budget` (synchrone),
  `assert_under_budget_async` (httpx async) et `second_best_of_five_many` (plusieurs mesures par
  passage, comme `fcp`/`ready` de la coquille). Un seul endroit pour la règle du 2026-10-23 ;
  `test_read_budget.py` n'est pas touché (modèle différent, pas de budget à affaiblir).
- `test_conversations_api.py`, `test_model_card_api.py`, `test_shell.py` utilisent le helper ; chacun
  a reçu un test « preuve » qui ralentit sa route (monkeypatch de `conversation_view` / `card_source`,
  route Playwright retardée sur `/static/main.js`) et vérifie que le helper échoue encore.
- `test_arena_api.py::test_lane_timeout_counts_from_the_slot_not_from_the_wait` : marge relevée à 1 s
  par lane pour un délai de 1,5 s (au lieu de 0,25 s/0,4 s) ; code de production inchangé.
- `test_models_manage.py` : les trois lectures de focus par `document.activeElement` remplacées par
  `expect(...).to_be_focused()`. En creusant l'échec reproductible de
  `test_deleting_asks_first_with_the_focus_on_cancel_then_removes_the_model`, le défaut était réel et
  pas seulement une lecture trop tôt : `wl-confirm-dialog#close` gardait une référence DOM directe
  vers le bouton à refocaliser, or le tableau des modèles installés peut être reconstruit
  (`replaceChildren`) pendant que le dialogue est ouvert, ce qui détache ce nœud (`isConnected ===
  false`) avant la fermeture. Corrigé dans l'écran (`wl-confirm-dialog.js`) : une fonction `reacquire`
  retrouve l'équivalent actuel par `id`, ou par tag + classes + `data-tag` (convention des lignes de
  tableau de l'app) quand le nœud d'origine a été remplacé, et le focus est reposé après le retour de
  focus natif du `<dialog>` (`requestAnimationFrame`, lui aussi asynchrone). Validé stable sur
  plusieurs passages locaux (Edge) après correctif.
- `test_arena.py::test_axe_finds_no_violation_with_four_models_the_summary_and_the_folded_answers` :
  le backend n'envoie `run_ended` qu'après `asyncio.gather` de toutes les lanes (`arena.py:451`), donc
  le résumé (`showSummary = running()`, D-16) ne peut pas disparaître avant la fin réelle du run —
  aucun défaut d'écran trouvé après lecture de `arena.js`/`arena-summary.js`/`arena.py`. Reproduit une
  fois en local (sur ce poste, chargé par cette même session) un dépassement du délai par défaut de
  Playwright (15 s) avant que `.arena-summary` devienne visible, cohérent avec les deux occurrences
  CI de `run-autonome.md` (3 morceaux E2E en parallèle sur le même runner) : le délai de cette seule
  attente avait été porté à 30 s. Revue : délai rendu à sa valeur par défaut, l'attente était mal
  posée. Reproduit à chaque passage en local : le run finissait en moins de 4 s, `fake:a` compris,
  car le texte long (`"mot " * 400`) déclenchait le détecteur de répétition de la story 9.2
  (`loop_detector.py`, `stopped_reason: "loop"`), qui arrêtait les lanes sans attendre leur pause ;
  le résumé n'était visible qu'un instant. Le texte long n'a plus de répétition (`mot0 … mot399`),
  `fake:a` dort 3 × 30 s (plafond du `fake`) sans finir seul, et le test audite le résumé, clique
  « Arrêter » et attend « Comparaison arrêtée » avant l'audit de la configuration revenue.
- `test_accessibilite.py::test_every_screen_has_one_h1_a_distinct_title_and_the_french_language` :
  utilisait le `server` partagé (module, toutes les routes de `test_accessibilite.py`) au lieu d'un
  serveur dédié ; un scénario antérieur du même fichier peut laisser des documents ingérés dans la
  base de `/documents/base`, changeant son rendu (plus un seul `h1`) selon l'ordre de la suite. Isolé
  avec la fixture `backend` (serveur et dossier de données neufs, propres à ce test).
- `.github/workflows/stabilite.yml` (nouveau) : `workflow_dispatch` et `pull_request` filtré sur ce fichier, matrice des trois OS,
  vingt passages des sept tests ci-dessus (`-m "e2e or not e2e"` pour mélanger web et E2E dans le même
  passage malgré le `-m "not e2e"` par défaut de `pytest.ini`), arrêt au premier échec par passage.
- `epics.md:1957` mis à jour comme demandé. `run-autonome.md` : retiré de la PR à la revue (fichier
  d'état du run). `AGENTS.md` ne mentionne aucune relance : rien à y changer.

- `test_arena_judge_api.py::test_judge_progress_is_not_published_for_an_empty_answer_or_without_a_judge`
  (ajout de la revue, vu en CI Windows 3.12, run 39926709839, `assert 2 == 1`) : quand le juge de
  `fake:b` prenait la place locale avant que `fake:a` (réponse vide) la demande, `fake:b` était
  noté avec le total juste à cet instant (2) et jamais republié. Pas un défaut : `total` compte les
  colonnes encore en génération, et `_refresh_judge_total` ne republie que les colonnes encore chez
  le juge. `fake:b` génère maintenant pendant 1 s (`Sleep(1.0)`), ce qui laisse `fake:a` attendre la
  place avant le juge (file FIFO de `LocalSlot`) quel que soit l'ordre de départ.
- `wl-confirm-dialog.js` (revue) : le retour de focus synchrone d'avant 8.5 est rétabli ; le
  rattrapage par `requestAnimationFrame` ne joue que si le focus est perdu (`body`, nœud détaché ou
  resté dans le dialogue fermé), pour ne jamais écraser un focus posé par l'appelant après
  `await ask()` (`documents-manage.js` : `focusRow`, `fallbackFocus`).

## Spec Change Log

- 2026-10-23 : critère de `epics.md` (budgets de latence) ajusté de « médiane de plusieurs appels »
  à « deuxième meilleur de cinq appels », décision d'Anaël actée dans le frozen-intent de cette story.

## Review Triage Log

Revue Opus du 2026-10-23, base `origin/master` 355fd2c à jour (pas de rebase nécessaire).

- medium · second avis 1 · corrigé · `test_arena.py` : le délai à 30 s masquait une attente mal posée ; vraie cause, le détecteur de répétition (9.2) arrêtait les lanes sur `"mot " * 400`. Texte sans répétition, run arrêté par « Arrêter », délai par défaut.
- medium · second avis 2 · corrigé · `stabilite.yml` : `workflow_dispatch` n'est lançable qu'une fois le fichier sur `master` ; ajout de `pull_request` filtré sur ce seul fichier, pour avoir la preuve sur la PR avant fusion.
- medium · second avis 3 · corrigé · `run-autonome.md` ramené à l'état de `master` (fichier d'état du run, et preuve affirmée mais pas faite) ; liste à vider par l'orchestrateur, en PR `chore/etat-run`, une fois `stabilite.yml` vert. `sprint-status.yaml` n'est pas dans la branche.
- medium · second avis 4 + revue · corrigé · `wl-confirm-dialog.js` : le `focus()` différé écrasait le focus posé par l'appelant après `await ask()` (`documents-manage.js`). Retour synchrone rétabli, rattrapage seulement si le focus est perdu. E2E rejoués : `test_models_manage` (delete), `test_documents_manage` (21), `test_accessibilite` (focus, h1), approbations `test_agents_solo`/`test_agents_crew`, tous verts.
- low · second avis 5 · rejeté · `reacquire` rend `null` si les classes ont changé : le focus reste alors sur `body`, comme avant la 8.5. Pas de régression, cas non rencontré.
- low · second avis 6 · corrigé · `epic-8-context.md` : « médiane de plusieurs appels » remplacé par « deuxième meilleur de cinq appels ».
- low · second avis 7 · corrigé · `controle_rapide.py` relancé : vert, sans coupe-circuit.
- low · second avis 8 · rejeté · `timeout-minutes: 90` : estimation de 1 à 2 min par passage, soit 20 à 40 min pour 20 passages, plus l'installation. À mesurer au premier passage sur la PR.
- medium · orchestrateur (CI run 39926709839) · corrigé · `test_judge_progress_is_not_published_for_an_empty_answer_or_without_a_judge` dépendait de l'ordre d'accès à la place locale (voir Implementation Notes). Ajouté à `stabilite.yml`.
- medium · orchestrateur (PR #132, `stabilite.yml`) · corrigé (décision d'Anaël du 2026-10-23) · même mesuré depuis `responseStart`, le budget échoue sur les runners macOS (fcp de 315 à 405 ms, ready de 408 à 643 ms) et Windows (ready de 305 à 334 ms) ; Ubuntu passe ses 20 manches. Le temps de réponse du serveur n'était donc pas la cause principale : ces runners rendent le front plus lentement. Correctif : en CI (`CI` posé), le test ne tourne que sur Linux (`skipif` avec raison écrite) ; en local, il tourne partout. Tous les autres tests de `stabilite.yml` passent leurs 20 manches sur les trois OS.
- medium · orchestrateur (CI run 39926709839) · corrigé (décision d'Anaël du 2026-10-23) · `test_shell_renders_under_300_ms…` sur Ubuntu : mesures de 333, 334, 390, 364 et 243 ms, deuxième meilleur à 333 ms. Cause : la mesure partait du début de la navigation et incluait donc le temps de réponse du serveur de test, pas seulement le rendu du front. Correctif : `shell_timings` (`tests/v2/e2e/test_shell.py`) mesure désormais `fcp` et `ready` depuis `responseStart` (Navigation Timing, `performance.getEntriesByType('navigation')[0].responseStart`) au lieu du début de la navigation, en retranchant ce temps de réponse serveur des deux mesures. Budget (300 ms) et règle (échauffement, deuxième meilleur de cinq, `tests/v2/latency.py`) inchangés. Autres tests de la coquille vérifiés (`git grep` sur `getEntriesByType('navigation')` et les budgets de `tests/v2/e2e`) : aucun autre test ne mesure un budget depuis la navigation, rien d'autre à aligner. Note locale (ce poste, Edge) : le test échoue encore ici (fcp/ready entre 400 et 1200 ms, `responseStart` lui-même sous 50 ms) — reproduit à l'identique avec le code non modifié, donc une lenteur propre à ce poste/Edge local, pas un effet du correctif ; preuve attendue sur la CI Ubuntu de la PR.
- low · revue · reporté · `test_models_manage.py::test_the_defaults_section_lists_the_five_purposes_with_their_reason` et `test_choosing_a_default_writes_it_and_reverting_clears_it` dépendent de la RAM libre réelle du poste (rouges ici, poste saturé, comme sur `master`). Verts en CI. À isoler par une mémoire injectée si on les voit en CI.
- Complexité : 0 constat (le helper fait six mesures, `reacquire` une requête DOM par fermeture).

## Revue

Constats medium du second avis et de l'orchestrateur corrigés, sauf le budget de la coquille sous la charge d'Ubuntu, qui attend une décision. Restent à vérifier sur la PR : `stabilite.yml` vert sur les trois OS (AC 1) et trois CI vertes de suite (AC 2). Statut laissé à `review` jusqu'à ces preuves et à cette décision.

## Verification

**Commands:**
- `.venv\Scripts\python -m pytest tests/v2/web/test_conversations_api.py tests/v2/web/test_model_card_api.py tests/v2/web/test_arena_api.py -q --tb=short` -- expected: vert
- `.venv\Scripts\python -m pytest tests/v2/e2e/test_shell.py tests/v2/e2e/test_arena.py tests/v2/e2e/test_models_manage.py tests/v2/e2e/test_accessibilite.py -m e2e -q --tb=short` (avec `WAVELOCALAI_E2E_CHROMIUM` sur Edge) -- expected: vert
- `.venv\Scripts\python .claude/cost-kit/controle_rapide.py` -- expected: aucun défaut
- `stabilite.yml` se lance seul sur la PR (déclencheur `pull_request` filtré sur le fichier) ; `gh run watch <id> --interval 60` -- expected: vert sur les trois OS -- not yet run (rien poussé dans cette session) ; preuve à constater sur la PR avant fusion.

**Observed (ce poste, Edge, exécutions locales) :**
- `tests/v2/web/test_conversations_api.py tests/v2/web/test_model_card_api.py tests/v2/web/test_arena_api.py` : 59 verts.
- `test_models_manage.py` (16, dont la cible `test_deleting_asks_first_with_the_focus_on_cancel_then_removes_the_model`, stable sur plusieurs passages après le correctif de `wl-confirm-dialog.js`) : 15 verts, 1 rouge pré-existant et hors story (`test_the_defaults_section_lists_the_five_purposes_with_their_reason`, dépend de la RAM libre réelle du poste ; rouge aussi sur `master` non modifié, vérifié par `git stash`).
- `test_arena.py::test_axe_finds_no_violation_with_four_models_the_summary_and_the_folded_answers` (les 4 passages) : vert ; reproduit une fois un dépassement du délai par défaut (15 s) avant correctif, cause documentée dans Implementation Notes.
- `test_accessibilite.py::test_every_screen_has_one_h1_a_distinct_title_and_the_french_language` (isolé) : vert.
- `test_shell.py` : 34/35 verts (tout sauf le test de budget de la coquille) ; `test_shell_renders_under_300_ms_without_waiting_for_the_api_ollama_stopped` dépasse le budget sur ce poste en ce moment (900 ms à plus de 3 s de deuxième meilleur), reproduit à l'identique sur `master` non modifié (`git stash`) : ce poste est lui-même trop chargé pour ce test pendant cette session (nombreux processus Edge et un serveur de test orphelin accumulés), pas une régression du correctif. À revérifier sur un poste calme et via `stabilite.yml`.
- `uvx black@25.12.0 --check`, `uvx isort@7.0.0`, `uvx ruff@0.14.9` sur les 8 fichiers Python modifiés : verts en appel direct. `controle_rapide.py` a échoué 3 fois de suite sur l'étape black avec une sortie vide (flakiness réseau connue de `uvx` sans mode `--offline` disponible), puis est passé par son propre coupe-circuit (« 3 échecs consécutifs : on laisse passer ») ; la vérification directe confirme qu'il n'y a pas de défaut de format réel.
