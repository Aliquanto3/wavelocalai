---
title: 'Story 9.2 : l''Arène arrête un modèle qui tourne en boucle, automatiquement ou à la demande'
type: 'feature'
created: '2026-10-21'
status: 'review'
baseline_commit: '4472c5c'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
warnings: []
deferred: []
---

# Story 9.2 : l'Arène arrête un modèle qui tourne en boucle, automatiquement ou à la demande

## Objectif

Source R2 (`tev1:0.8b`, question sur la photosynthèse) : une colonne de l'Arène qui se répète ou qui
dérive fait attendre jusqu'au délai de lane (300 s) pour rien. Trois arrêts, un seul mécanisme : un
plafond de jetons (`arena.max_tokens`), un détecteur de répétition (`arena.loop_min_repeats` /
`arena.loop_window_chars`), et un bouton « Arrêter ce modèle » par colonne. Dans les trois cas, la
réponse partielle est gardée **et notée** par le juge comme une lane terminée normalement — jamais
sautée comme une annulation — et la lane continue de montrer CO₂ et débit mesurés (AD-10). Ouvre la
voie à la story 9.3 (même fichiers).

## Réglages ajoutés (`wavelocalai.toml` `[arena]`)

- `max_tokens` (défaut 800) : plafond passé dans `ChatRequest.max_tokens` de chaque lane (déjà porté
  par AD-8 et tous les adaptateurs, story 9.2 n'a eu qu'à le renseigner).
- `loop_min_repeats` (défaut 4) et `loop_window_chars` (défaut 200) : seuil et fenêtre du détecteur
  de répétition (`inference/loop_detector.py`).

## Critères d'acceptation et preuves

1. **Plafond de jetons** : `ArenaService._orchestrate` construit le `ChatRequest` avec
   `max_tokens=settings.arena.max_tokens` ; une lane qui le heurte reçoit `finish_reason: "length"`
   de l'adaptateur (déjà normalisé partout, `models/cloud.py`), mappé en `stopped_reason:
   "max_tokens"` sur son `lane_status: done`. Preuve :
   `tests/v2/web/test_arena_stop_api.py::test_a_lane_that_hits_max_tokens_...` (vérifie
   `requests[0].max_tokens` sur chaque lane) et l'E2E
   `test_arena_stop.py::test_a_lane_that_hits_max_tokens_shows_the_stopped_status_...`.
2. **Détecteur de répétition, faux positifs à zéro** : `inference/loop_detector.py` (`repeated_tail`,
   `LoopDetector`) — fragment exact d'au moins 8 caractères, répété au moins `loop_min_repeats` fois
   sur une fenêtre d'au moins `loop_window_chars` ; vérifié tous les 20 caractères nouveaux
   (`LoopDetector.feed`), pas à chaque jeton. `tests/v2/unit/test_loop_detector.py` (12 tests) :
   - faux positifs testés : liste à puces (6 items distincts), liste numérotée (8 lignes voisines
     mais différentes), tableau Markdown (6 lignes dont l'en-tête et le séparateur), séparateur de
     tableau répété une seule fois, code Python avec assertions voisines mais distinctes (9 lignes),
     indentation vide répétée mais sous la fenêtre (`"    pass\n" * 4`) — **aucun ne déclenche** ;
   - vrais positifs : phrase répétée au-delà de la fenêtre, paragraphe répété, fragment court (7
     caractères) répété 40 fois (span ≥ fenêtre malgré un fragment court) ; et un cas sous le seuil
     (3 répétitions) qui ne déclenche pas.
   - En service réel : `test_arena_stop_api.py::test_a_repeating_lane_is_stopped_with_loop_...` et
     `test_the_false_positive_prose_does_not_stop_the_lane` (prose normale, aucun arrêt) ; E2E
     `test_arena_stop.py::test_a_repeating_lane_is_stopped_with_the_loop_status_...`.
3. **Bouton « Arrêter ce modèle »** : `POST /api/runs/{lane_run_id}/stop` (`routes_runs.py`) appelle
   `ArenaService.request_stop(lane_run_id)` ; la lane s'arrête seule, les autres continuent, CO₂ et
   débit (estimé sur l'horloge, `tps_source: "wallclock"`) restent mesurés. Arrêt réactif même
   pendant une attente (le modèle « réfléchit », pas seulement entre deux jetons) :
   `_RecordingModel._next_or_stop` court-circuite l'attente du prochain jeton par une course
   `asyncio.wait` entre le jeton et l'événement d'arrêt. Preuve :
   `test_arena_stop_api.py::test_stopping_a_lane_keeps_the_other_running_...` (lane arrêtée en plein
   `Sleep(1.0)`, CO₂ `codecarbon` mesuré, l'autre lane finit normalement),
   `test_stopping_an_already_finished_lane_rejects_cleanly`,
   `test_stopping_an_unknown_run_id_is_run_not_found` ; E2E
   `test_arena_stop.py::test_stopping_one_lane_keeps_the_other_running_...` et
   `test_the_stop_button_only_shows_while_a_lane_is_in_progress`.
4. **Contrats documentés** : `contrat-api.md` — nouvelle route (§Runs, §tableau des routes) et
   `lane_status` porte désormais `run_id` (ajout additif, pour que le bouton désigne sa lane) et
   `stopped_reason` (absent si la lane a fini d'elle-même). `EXPERIENCE.md` (§Arène) décrit le bouton
   et les trois textes d'arrêt, en plus du texte « le modèle se répétait » déjà posé par la maquette
   validée de la story 9.6.
5. **Exports CSV et Markdown portent la raison** : `runs/arena_export.py` — colonne `stopped_reason`
   (code brut) en CSV, colonne « Arrêt » (libellé français) dans le tableau Markdown, entrée dans
   `DEFINITIONS`. `tests/v2/unit/test_arena_export.py` (6, inchangés, aucune régression : le champ est
   additif et vaut `None`/« non » par défaut).
6. **Tests de l'Arène réalignés** : `wl-arena-lane.js` (`setStatus(status, error, stoppedReason)`,
   `setRunId`, bouton `wl-lane-stop`), `components.json` (clés `components.lane.stopped.*` et
   `stop_model`), `tests/v2/unit/test_arena_static.py` (16, inchangés — la liste close
   `LANE_STATUSES` n'a pas bougé, `stopped_reason` est un champ additif, pas un nouveau statut) ;
   E2E `test_arena.py` (57), `test_arena_address.py` (5) et `test_arena_results.py` (28) réalignés :
   trois `get_by_role("button", name="Arrêter")` non scopés devenaient ambigus (ils matchaient aussi
   le nouveau bouton de colonne « Arrêter ce modèle ») — scopés à `.arena-banner`.

## Détail technique (hors AC, pour la 9.3)

- `_RecordingModel` (`inference/arena.py`) porte le mécanisme des trois arrêts : il intercepte chaque
  jeton de la lane (déjà fait, pour le juge), applique le détecteur de boucle, et consomme un flux
  externe `request_stop`. Un arrêt (boucle ou demande) clôt le flux de l'adaptateur comme une
  annulation (AD-8 : `aclosing`, le `finally` de chaque adaptateur ferme la connexion) puis synthétise
  un `Done` à partir de ce qui a déjà été reçu (jetons estimés à 4 caractères, comme l'estimation
  cloud de secours existante). La mesure CodeCarbon, elle, tourne pendant tout l'appel et n'est pas
  affectée : elle s'arrête avec le tracker, dans la place du sémaphore (AD-11).
- `POST /api/test/arena` (`routes_test.py`) remplace désormais `request.app.state.arena` par le
  service scripté qu'il construit, pour que `POST /api/runs/{id}/stop` (qui lit cet état) trouve la
  bonne lane en test ; trouvé en diagnostiquant l'échec E2E (voir Rapport de dev).

## Fichiers

- Config : `wavelocalai.toml`, `src/wavelocalai/config.py` (`ArenaSettings`).
- Code : `src/wavelocalai/inference/loop_detector.py` (nouveau), `src/wavelocalai/inference/arena.py`,
  `src/wavelocalai/web/routes_runs.py`, `src/wavelocalai/web/routes_test.py`,
  `src/wavelocalai/runs/arena_export.py`.
- Front : `src/wavelocalai/web/static/components/wl-arena-lane.js`,
  `src/wavelocalai/web/static/screens/arena.js`, `arena-run.js`, `src/wavelocalai/web/static/arena.css`,
  `src/wavelocalai/web/static/core/api/runs.js`, `src/wavelocalai/web/static/i18n/fr/components.json`.
- Doc : `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md`,
  `_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md`.
- Tests : `tests/v2/unit/test_loop_detector.py` (nouveau),
  `tests/v2/web/test_arena_stop_api.py` (nouveau), `tests/v2/e2e/test_arena_stop.py` (nouveau) ;
  réalignés : `tests/v2/e2e/test_arena.py`, `test_arena_address.py`, `test_arena_results.py`.

## Rapport de dev

- Tests ciblés : `tests/v2/unit tests/v2/web -k "arena or loop or stop or export or lane or layers"`
  → 239 passed. E2E Arène, lancés séparément (fichier par fichier, poste limité) :
  `test_arena_stop.py` 4 passed ; `test_arena.py` 57 passed ; `test_arena_address.py` +
  `test_arena_results.py` 33 passed ; `test_arena_reopen.py` + `test_arena_verdict.py` +
  `test_flow2.py` 35 passed. Pas de suite complète ni d'E2E complète (consigne du run, poste limité) :
  la CI joue le reste.
- Deux cycles de correctif :
  1. Un test E2E (arrêt manuel pendant un `Sleep(30 s)`) restait bloqué : diagnostiqué avec un
     serveur réel isolé (hors Playwright) — `POST /api/runs/{lane_run_id}/stop` rendait
     `stopped: false`. Cause : `POST /api/test/arena` construit son propre `ArenaService` à chaque
     appel, jamais enregistré dans `app.state.arena`, que la route `/stop` lit. Corrigé en l'y
     assignant (route de test seulement, voir « Détail technique »).
  2. Après ce correctif, un test E2E préexistant (`test_stop_cancels_every_lane_...`) et deux autres
     (`test_arena_address.py`, `test_arena_results.py`) cliquaient `get_by_role("button",
     name="Arrêter")` sans le scoper : une colonne en cours porte maintenant aussi « Arrêter ce
     modèle » (correspondance Playwright non stricte), violation de mode strict. Scopés à
     `.arena-banner` dans les trois fichiers (consigne : réaligner les E2E qui lisent une structure
     partagée, dans le même commit).
- Faux positifs du détecteur de boucle testés (liste, tableau Markdown, code) : voir AC 2 ci-dessus.
- Contrôle rapide (`controle_rapide.py`) : propre, rien à corriger.
- Reports : aucun — tout le périmètre de l'AC est couvert. La refonte visuelle complète de l'état
  « arrêté » (couleurs, mise en page) reste pour la story 9.7, comme demandé ; cette story réutilise
  les composants existants (ligne de statut `.wl-lane-status`, icône `block` en `--color-risk`, comme
  `cancelled`), sans nouveau statut de lane.

## Revue

Revue Opus (une passe), base `origin/master` 4472c5c à jour (pas de rebase). Second avis Haiku repris point par point.

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| high | second avis 1 | Arrêt demandé sur une lane `waiting` perdu : `stream()` remettait `_requested` à `None`, la colonne tournait en entier. | Corrigé : l'arrêt vaut pour toute la lane ; demandé avant le début, la tentative finit aussitôt sans appeler l'adaptateur (réponse vide, « non évalué », `stopped_reason: "user"`). Tests `test_a_stop_requested_before_the_attempt_starts_skips_the_call`, `test_stopping_a_waiting_lane_finishes_it_at_once_not_evaluated`. |
| medium | revue | En `judging`, `POST …/stop` rendait `stopped: true` sans effet, et le bouton restait visible (EXPERIENCE.md le promettait pendant la notation). | Corrigé : `request_stop` rend `False` une fois la génération finie ; bouton masqué en notation (`IN_PROGRESS` de `wl-arena-lane.js`), EXPERIENCE.md réaligné. |
| high | second avis 2 | `finish_reason` Anthropic brut non normalisé. | Rejeté : `WallClock.result` (`models/cloud.py`) passe par `normalize_finish` pour Anthropic, Mistral et openai_compat (`max_tokens`, `length`, `model_length` -> `length`, vérifié à l'exécution) ; Ollama rend `done_reason: "length"` au plafond `num_predict`. |
| medium | second avis 3 | Période maximale = fenêtre analysée / 4 (200 car.) : un paragraphe répété de plus de 200 caractères n'était jamais vu. | Corrigé : périodes jusqu'à `MAX_PERIOD_CHARS` (1000), fenêtre bornée à `min_repeats × 1000`. Test sur un paragraphe de ~400 car. répété 4 fois. |
| medium | second avis 4 | Faux positifs confirmés (l'ancien code déclenchait) sur une matrice de zéros, une grille ASCII, un CSV et un tableau Markdown de lignes identiques, des objets JSON identiques, des lignes de code identiques. | Corrigé : le fragment répété doit compter au moins 50 % de lettres (`MIN_LETTER_RATIO`). Six cas ajoutés au jeu de faux positifs. |
| medium | second avis 5 | Arrêt au moment du `Done` naturel : `Done` synthétique « user » émis après le réel, dont il écrasait les métriques. | Corrigé : pas de `Done` synthétique après un `Done` réel. Test `test_a_stop_after_the_real_done_keeps_its_metrics_and_is_refused`. |
| medium | revue | Relance d'une lane (`retry_interrupted`) : le détecteur gardait la longueur vérifiée de la tentative précédente et restait aveugle jusqu'à la dépasser. | Corrigé : `LoopDetector.reset()` à chaque tentative. Test `test_loop_detector_reset_forgets_the_previous_attempt`. |
| low | second avis 6 | `await task` sous `suppress(CancelledError)` pouvait avaler l'annulation de la lane. | Corrigé : `asyncio.wait` sur les tâches annulées, qui laisse remonter une annulation externe. |
| low | second avis 7 | `stopped_reason` au milieu de `CSV_COLUMNS`. | Corrigé : dernière colonne. Test d'export CSV et Markdown ajouté (le critère « les exports portent la raison » n'avait pas de test). |
| low | second avis 8 / Complexité | `"".join(self.answer)` à chaque jeton : O(n²) sur la réponse. | Corrigé : `LoopDetector.feed` reçoit le morceau, garde une fin bornée et n'assemble qu'au pas de vérification (O(fenêtre) par vérification ; pire cas mesuré 2 ms sur 4 000 car. de zéros). |
| low | second avis 9 | Boucle à compteur variable (« Étape 1… Étape 2… ») non détectée. | Rejeté (accepté par conception) : documenté dans `loop_detector.py`, le plafond `arena.max_tokens` la borne. |

Tests : `test_loop_detector.py` (17), `test_arena_stop_api.py` (9), `test_arena_export.py` (7), unit Arène / adaptateurs cloud / config / couches, web Arène (4 fichiers), E2E `test_arena_stop.py` (4) et `test_arena.py` (57) sur Edge ; contrôle rapide propre. Pas d'essai réel avec Ollama.
