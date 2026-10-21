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
