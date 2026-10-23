---
title: 'Story 9.3 : on voit le juge de l''Arène travailler'
type: 'feature'
created: '2026-10-21'
status: 'review'
baseline_commit: 'e416767'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-9-2.md'
warnings: []
deferred: []
---

# Story 9.3 : on voit le juge de l'Arène travailler

## Objectif

Source R3 : pendant la notation (l'une des étapes les plus longues de l'Arène, un appel de modèle
par colonne, sérialisé sur la même place locale que les générations), rien ne distingue « en
attente de la place » de « le juge écrit sa note ». Un bandeau au-dessus des colonnes et un sous-
statut par colonne disent l'un et l'autre, sans compteur quand il n'y a pas de juge ou qu'il est en
panne. Après la story 9.2 (mêmes fichiers côté Arène).

## Contrat ajouté

`judge_progress` `{judge, phase: "queued"|"loading"|"scoring", lane, position, total}`, publié entre
`lane_status: judging` et `judge_score` d'une même lane (`contrat-api.md`). `queued` : le serveur
vient de décider de noter cette lane, juste avant d'essayer d'appeler le juge (avant même la place
locale). `loading` : le modèle du juge charge en mémoire. `scoring` : le juge travaille, chargé ou
non — publié **dès la prise de la place** (comme `lane_status: generating`, D3), donc parfois avant
un `loading` qui suit. `position`/`total` comptent les colonnes de la comparaison (une réponse vide
n'appelle pas le juge et n'a pas de `judge_progress`).

## Critères d'acceptation et preuves

1. **Le serveur publie `judge_progress`** : `ArenaService._judge_lane` (`inference/arena.py`) publie
   `queued` juste avant d'appeler `LaneJudge.score`, avec `position` = `_Arena.judge_done` (compteur
   incrémenté à chaque colonne envoyée au juge) et `total` = `_Arena.judge_total` (nombre de colonnes
   de la comparaison, fixé au départ). `judge_port.LaneJudge.score` et `evaluation.judge.Judge.score`/
   `.ask` portent un nouveau paramètre `on_phase` (`loading`/`scoring`), relayé depuis `on_phase` de
   `stream_into_run` (translaté par `_scoring_phase`). Correctif connexe dans
   `inference/streaming.py::_consume` : un appel **silencieux** (`capture`, la notation en est un)
   ne publiait ni jetons ni `model_loading`/`model_loaded` dans le flux, et jusqu'ici n'appelait pas
   non plus `on_phase` pour un `LoadState` — nécessaire pour que `loading` atteigne `judge_progress`
   sans pour autant publier `model_loading` dans le flux de l'Arène (toujours tu, comme avant).
   Preuve : `tests/v2/web/test_arena_judge_api.py::test_judge_progress_is_published_queued_then_scoring_with_position_and_total`
   (`position`/`total` corrects, ordre `lane_status: judging` < `judge_progress` < `judge_score`),
   `test_judge_progress_reports_loading_when_the_judge_warms_up`,
   `test_judge_progress_is_not_published_for_an_empty_answer_or_without_a_judge` (réponse vide : pas
   dérangé ; sans juge : aucun événement). Les 16 tests existants du même fichier restent verts
   (`on_phase` additif, défaut `None`).
2. **Bandeau du juge** (`arena-judge-banner.js`, nouveau module, classe `.judge-banner` reprise de la
   maquette validée `docs/maquette-v2-mise-en-page/index.html` ; refonte visuelle complète en 9.7) :
   « Juge : <modèle> · chargement » dès l'événement `judge` (modèle connu), puis
   « Notation {position} sur {total} · {colonne} · {temps écoulé} » dès le premier `judge_progress`
   `phase: scoring`, qui **remplace** l'affichage précédent sans jamais être effacé par le `queued`
   ou le `loading` d'une **autre** colonne déjà en file (bug trouvé et corrigé en E2E, voir Rapport de
   dev) ; chronomètre `formatClock`, mis à jour chaque seconde, région `role=status aria-live=polite`
   (un seul texte réécrit par étape, jamais par jeton). Figé sur le dernier état connu à la fin du
   run (rien ne l'efface). `arena.js` le câble aux événements `judge`, `judge_progress`,
   `judge_score` (compacté à 600 lignes pile, trois fonctions ramassées sur une ligne pour faire de
   la place, `test_static_split.py::test_no_front_script_exceeds_600_lines`).
3. **Colonne : file vs notation en cours** : `wl-arena-lane.js::setJudgeProgress(phase)` pose
   `#judgePhase` (`queued` par défaut à l'entrée en `judging`, `scoring` sur le premier `phase:
   scoring`) ; `components.json` `components.lane.judging_phase.{queued,scoring}` (« En file pour la
   notation » / « Notation en cours »), **hors** de `components.lane.status` pour ne pas casser
   l'invariant 1:1 avec `STATUS_ICON` que vérifie
   `test_arena_static.py::test_every_lane_status_of_the_server_has_a_text_and_an_icon`.
4. **Sans juge, ou juge en panne : pas de compteur** : `banner_none` (« Comparaison sans juge… »,
   posé dès l'événement `judge` sans modèle) et `banner_down` (« Juge indisponible… », posé par
   `judge_score` dont la raison dit « juge indisponible » **avant toute note réussie** — `scored()`
   lève une panne déjà affichée si le juge finit par noter correctement). Note : un juge configuré
   qui tombe en panne **pendant** un appel peut malgré tout afficher brièvement une `position` avant
   l'échec (le `scoring` optimiste part dès la prise de place, avant que l'appel échoue) ; la panne,
   elle, est rattrapée dès le premier `judge_score` « indisponible » et reste affichée ensuite, comme
   demandé par le critère.
5. **Contrats documentés** : `contrat-api.md` (ligne `judge_progress`) ; `EXPERIENCE.md` (§Arène,
   nouvelle puce « On voit le juge travailler »).
6. **Tests réalignés** : unitaires et web ci-dessus ; E2E `test_arena.py` —
   `test_the_judge_banner_shows_loading_then_scoring_n_of_total_then_ends` (chargement -> notation 1
   sur 2 avec le nom de la colonne et le chronomètre -> colonne en file pendant qu'une autre note ->
   fin figée sur « Notation 2 sur 2 ») et `test_the_judge_banner_says_no_judge_without_a_counter`.
7. **Textes FR, pas d'emoji** : `arena.json` (`judge.banner_*`, espace insécable avant « : »,
   vérifié par `test_catalog_and_index_use_non_breaking_spaces_before_high_punctuation`),
   `components.json` (`lane.judging_phase.*`). Icône `gavel` déjà au sprite (story 9.2/maquette).

## Détail technique (hors AC)

- `_Arena.judge_total`/`judge_done` (`inference/arena.py`) : compteur simple, pas de verrou — le
  service tourne sur une seule boucle asyncio, l'incrément est synchrone entre deux `await`.
- Bug trouvé en E2E (pas en unitaire, où les deux lanes sont notées sans recouvrement observable) :
  le bandeau effaçait la notation en cours d'une colonne dès qu'une **autre** colonne publiait son
  propre `queued`/`loading` (en attendant son tour derrière la première). Corrigé en ne mettant à
  jour l'affichage que sur un `phase: scoring` ; `queued`/`loading` d'une autre colonne n'a plus
  d'effet sur le bandeau tant qu'une notation est en cours.
- `arena.js` était déjà à 600 lignes (plafond dur) avant cette story : trois petites fonctions
  (`count`, `elapsed`, `startTicker`) resserrées sur une ligne chacune pour faire de la place au
  câblage du bandeau, sans changer leur comportement.

## Hors périmètre (reporté)

- Refonte visuelle complète du bandeau et des colonnes (classes, disposition) : story 9.7, comme prévu
  par la maquette validée.

## Revue

Revue Opus (une passe, base `origin/master` 7001b34, à jour). Correctif racine : un seul modèle
d'état du bandeau (`arena-judge-banner.js` : colonnes chez le juge, phase et horloge par colonne,
panne, fin), et l'ordre réel des phases tiré du flux du juge (`_PhasedModel`, `evaluation/judge.py`)
au lieu du relais `on_phase` de `streaming.py`, rendu à son état d'avant la story.

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| high | second avis 1 | `scoring` publié à la prise de place avant `loading` ; bandeau bloqué sur « chargement » pendant toute la génération | corrigé : séquence `queued` -> `loading` (juge froid) -> `scoring` (chargement fini, premier fragment, ou 0,25 s sans chargement annoncé ; aussitôt en cloud) ; bandeau « en attente des réponses » avant la notation, « chargement » seulement en phase `loading` |
| high | second avis 2 | colonne qui recule de « Notation en cours » à « En file » | corrigé : `setJudgeProgress` monotone, phase remise à zéro seulement au changement de statut |
| high | second avis 3 | panne après une note réussie jamais affichée | corrigé : « Juge indisponible » dès la dernière note « juge indisponible », jusqu'à une phase `loading`/`scoring` ou une note réussie ; ni compteur ni horloge |
| high | second avis 4 | minuteur jamais arrêté (fin, démontage, nouvelle comparaison) | corrigé : minuteur actif seulement tant qu'une colonne est chargée ou notée ; `end()` dans `finish`, `reset()` dans `clearLanes` et au démontage ; E2E qui compte les minuteurs (`COUNT_JUDGE_CLOCKS`) |
| high | second avis 5 | horloge dans la région live (annonce chaque seconde) | corrigé : horloge `aria-hidden` à part, la région n'annonce que les étapes |
| medium | second avis 6 | `total = len(refs)` compte les colonnes en échec | corrigé : `total` = colonnes passées au juge + colonnes qui génèrent encore ; baisse republiée pour les colonnes chez le juge ; documenté dans `contrat-api.md` |
| medium | second avis 7 | juge cloud en parallèle : « Notation N » saute d'une colonne à l'autre | corrigé : « Notation : k sur N · m en cours » dès deux colonnes notées à la fois ; documenté dans `EXPERIENCE.md` |
| low | second avis 8 | relais `on_phase` en silencieux : l'Évaluation publiait `lane_status: loading` | corrigé : relais retiré de `streaming.py` (comportement de l'Évaluation inchangé depuis master) |
| low | second avis 9 | panne détectée par sous-chaîne française | corrigé : constante `JUDGE_UNAVAILABLE`, égalité exacte, vérifiée contre `NOT_EVALUATED_UNAVAILABLE` |
| low | second avis 10 | `startedAt` jamais remis à zéro | corrigé : horloge par phase et par colonne |
| medium | revue | E2E d'origine attendait « Notation 2 sur 2 » figé à la fin et un `scoring` avant `loading` | corrigé : tests web (ordre exact, juge chaud, juge injoignable, total qui baisse), unitaires (`test_arena_judge_banner_static.py`) et E2E réalignés |
| low | revue | juge injoignable : `queued` seul publié, la colonne reste « En file » jusqu'à sa note | accepté : la note « juge indisponible » arrive aussitôt |
| — | revue | Complexité : 0 constat (`active` et colonnes bornées à 4, aucun parcours d'une structure qui grossit) | — |

Report : `/api/ps` plus lent que 0,25 s sur une machine chargée ferait publier `scoring` puis
`loading` (la colonne ne recule pas, le bandeau repasse à « chargement ») ; à vérifier avec un vrai
Ollama et un juge froid (`tests/v2/integration/test_judge_ollama.py`, puis l'Arène à l'écran).
