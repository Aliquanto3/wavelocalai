# Run autonome — plan et état (v2, Epic 9 : retours de la recette du 2026-10-21)

Fichier lu par `/agent-cost-kit:avancement-run`. Contrat : `planning-artifacts/sprint-change-proposal-2026-10-21.md` (approuvé par Anaël le 2026-10-21), `epics.md` §Epic 9, ARCHITECTURE-SPINE.md, DESIGN.md, EXPERIENCE.md, AGENTS.md. Run précédent (Epics 1 à 8) : `run-autonome-epics-1-8.md` et `run-autonome-mvp.md` (règles reprises ci-dessous, adaptées à ce PC).

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epic 9 | Stories 9.1 à 9.9 ; préversion 2.0.0a8 en fin d'epic (9.9) |
| Hors run | Story 8.4 | « La v2 remplace la v1 » : revient à Anaël, après l'Epic 9 |

**Au plus 1 story en développement à la fois.** Essai de 2 en parallèle (9.4 et 9.2) le 2026-10-21 vers 12:15 : les deux agents se sont figés faute de mémoire, retour à 1 vers 13:30. Consigne d'Anaël du 2026-10-21 : pas de multi-agents en parallèle sur ce PC (trop gourmand). Les stories d'une même vague passent donc l'une après l'autre ; la vague ne sert qu'à l'ordre des dépendances.

## Règles fixes

- Par story : dev-story (Sonnet, effort high, worktree `..\wavelocalai-wt\<clé>`, branche `feat/v2-<clé>` ou `fix/v2-<clé>`) → second-avis (Haiku) → reviewer (Opus, liste du second avis, branche à jour de `origin/master`) → contrôles → PR → merge commit quand la CI est verte (jamais de squash, jamais de push sur `master`). Appels bloquants, un seul agent actif à la fois.
- Contrôles locaux : contrôle rapide (`.venv\Scripts\python .claude/cost-kit/controle_rapide.py`), tests ciblés de la story, E2E ciblés des écrans touchés (Edge : `$env:WAVELOCALAI_E2E_CHROMIUM`), `$env:PYTHONUTF8 = "1"`. La CI de branche (3 OS) sert de suite complète. Suite E2E complète sur master après 9.5 et en fin d'epic.
- Modèles locaux : **Granite 4.0 350M (`granite4:350m`) seulement**, pour tout essai réel (consigne d'Anaël : la qualité des réponses n'est pas évaluée). `qwen2.5:1.5b` n'est pas installé sur ce PC : `tests/integration` (v1) n'est pas lancé en local, la CI ne le lance pas non plus. Exception : 9.4 vérifie le tag du modèle d'embedding par une installation réelle (seul téléchargement autorisé du run) ; 9.5 télécharge le modèle du reranker par le bouton pour le vérifier.
- Outils `_outils/` du run précédent absents de ce PC : `git`, `gh` et `uv run python` directement. `git worktree prune` avant chaque lancement ; worktrees supprimés en fin de run seulement.
- Fichiers d'état (`sprint-status.yaml`, ce fichier) hors des PR de story : PR `chore/etat-run-*` à part, à chaque fin de vague et en fin d'epic. Après `gh pr merge`, vérifier `MERGED` avant de journaliser ; après fusion, `git log -1` sur master avant de tester.
- `gh run watch <id> --interval 60`.
- Heure du journal prise par `date` au moment d'écrire.

## Contrats partagés (à citer dans chaque prompt de dev et de revue)

- `stopped_reason` : `"max_tokens" | "loop" | "user"` dans `lane_status` (9.2) ; route `POST /api/runs/{run_id}/stop` (arrêt qui garde et fait noter la réponse partielle, distinct de `cancel`).
- Événement `judge_progress` `{judge, phase: "queued"|"loading"|"scoring", lane, position, total}` (9.3).
- Réglages : `[server] open_browser` (booléen, défaut true) et option `--no-browser` (9.1, fusionnée) ; `[arena] max_tokens` (800), `loop_min_repeats` (4), `loop_window_chars` (200) (9.2) ; `lane_status` porte aussi `run_id`.

## Sprint 9 — Retours de recette

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 9.1 · 9.5 · 9.4 · 9.2 · 9.6 (humaine) | — |
| V1 | 9.3 | 9.3 ← 9.2 |
| V2 | 9.7 ★ | 9.7 ← 9.3 ; 9.7 ← 9.6 |
| V3 | 9.8 · 9.9 | 9.8 ← 9.7 ; 9.9 ← 9.7 |

Ordre d'exécution (une à la fois) : 9.6 (maquette, préparée en premier pour qu'Anaël la valide pendant le reste) → 9.1 → 9.5 → 9.4 → 9.2 → 9.3 → [validation de 9.6 par Anaël] → 9.7 → 9.8 → 9.9.
9.5 avant 9.4 : les deux lisent `screens/models-pull.js` ; si 9.4 doit le modifier, elle part de 9.5 fusionnée.

## Décisions et points d'attente

- 9.6 validée par Anaël le 2026-10-21 (recommandations de DECISIONS.md §4 retenues) ; amendements de DESIGN.md et EXPERIENCE.md sur la PR #119, fusionnée avant 9.7.
- Tests instables au temps vus en CI (sans lien avec les stories) : `test_lane_timeout_counts_from_the_slot_not_from_the_wait` (macOS) et `test_the_card_answers_under_300_ms_with_ollama_down` (Windows) ; relance du job seulement, à signaler en fin de run. Local seulement : `test_rag_run_api.py::test_a_cloud_model_needs_allow_cloud` échoue seul sur master sur ce poste (délai de 5 s de `_ended`), vert en CI. Aussi `test_models_manage.py::test_deleting_asks_first_with_the_focus_on_cancel_then_removes_the_model` (E2E Linux, focus).

## Journal

- 2026-10-21 07:32 · Epic 9 · décision · proposition de changement du 2026-10-21 approuvée par Anaël ; Epic 9 reportée dans epics.md et sprint-status.yaml · —
- 2026-10-21 07:42 · Epic 9 · fusion · PR #118 (plan de l'Epic 9) fusionnée sur master · ba606cb
- 2026-10-21 07:52 · 9.6 · dev · lancé (Sonnet high, worktree `v2-9-6`, branche `docs/v2-9-6-maquette`) · —
- 2026-10-21 08:04 · 9.6 · dev · fini (maquette + DECISIONS.md, 6 questions à Anaël) · 2b2e247
- 2026-10-21 08:07 · 9.6 · second-avis · 1 high (contraste « Arrêté »), 3 medium (débord 390 px, primaire sur aplat sombre, légende inactive), 6 low · —
- 2026-10-21 08:08 · 9.6 · review · lancé (Opus) · —
- 2026-10-21 08:15 · 9.6 · review · fini (1 high, 6 medium, 7 low corrigés ; 2 écartés) · 774ea69
- 2026-10-21 08:15 · 9.6 · attente humaine · maquette publiée (artifact privé https://claude.ai/artifact/64zGMV9ufSX9KDtWaFhJvH), PR #119 en brouillon, notification envoyée · 774ea69
- 2026-10-21 08:15 · 9.1 · dev · lancé (Sonnet high, worktree `v2-9-1`, branche `feat/v2-9-1-navigateur`) · —
- 2026-10-21 08:31 · 9.1 · dev · fini (`[server] open_browser`, `--no-browser` ; unit 1310 verts) · ab1fcfe
- 2026-10-21 08:34 · 9.1 · second-avis · 2 medium (délai de 30 s muet, caplog dépendant de l'ordre), 3 low · —
- 2026-10-21 08:34 · 9.1 · review · lancé (Opus) · —
- 2026-10-21 08:40 · 9.6 · décision · maquette validée par Anaël (« mieux que l'existant, partons dessus ») ; recommandations de DECISIONS.md §4 retenues (Q1 à Q6) ; amendements DESIGN.md / EXPERIENCE.md à poser sur la PR #119 avant 9.7 · 774ea69
- 2026-10-21 08:41 · 9.1 · review · fini (1 medium corrigé : URL écrite si le port ne répond pas ; 1 medium non reproduit) · 8b88442
- 2026-10-21 08:48 · 9.6 · dev · amendements DESIGN.md / EXPERIENCE.md appliqués, jetons à poser listés pour 9.7 à 9.9 (DECISIONS.md §6) · 414ae98
- 2026-10-21 08:49 · 9.5 · dev · lancé (Sonnet high, worktree `v2-9-5`, branche `feat/v2-9-5-fastembed`) · —
- 2026-10-21 09:00 · 9.1 · CI · rouge (macOS 3.12 seul : test_lane_timeout_counts_from_the_slot_not_from_the_wait, Arène, sans lien avec 9.1, instable au temps) ; job relancé · 8b88442
- 2026-10-21 09:06 · 9.1 · CI · verte après relance du job macOS · 8b88442
- 2026-10-21 09:06 · 9.1 · fusion · PR #120 fusionnée · 257574a
- 2026-10-21 09:06 · 9.6 · CI · rouge (Windows 3.12 seul : test_the_card_answers_under_300_ms_with_ollama_down, 0,42 s, instable au temps ; PR de docs seulement) ; job relancé · 414ae98
- 2026-10-21 09:16 · 9.6 · CI · verte après relance du job Windows · 414ae98
- 2026-10-21 09:16 · 9.6 · fusion · PR #119 fusionnée (maquette, DESIGN.md et EXPERIENCE.md amendés) · 3ac97cb
- 2026-10-21 09:22 · 9.5 · dev · fini (fastembed 0.9.0 en dépendance de base, extra retiré, .venv +1,2 Mo, bouton essayé : pull ok en 26 s) · e6265a4
- 2026-10-21 09:25 · 9.5 · second-avis · 3 medium (EXPERIENCE.md, contrat-api.md, maquette gelée citent encore l'extra), 5 low · —
- 2026-10-21 09:25 · 9.5 · review · lancé (Opus) · —
- 2026-10-21 09:33 · 9.5 · review · fini (rebase sur 3ac97cb ; 2 medium + 4 low corrigés, maquette gelée et find_spec écartés) · c365496
- 2026-10-21 09:50 · 9.5 · CI · rouge (E2E Linux : test_documents_manage.py::test_the_dialog_and_the_screen_fit_a_phone_width, débord de 111 px en 390 ; probablement l'option du reranker désormais disponible) ; correctif lancé (Sonnet) · c365496
- 2026-10-21 10:45 · 9.5 · dev · correctif CI (chemin du cache sans coupure dans `.docs-rerank` : `overflow-wrap: anywhere`) · 58e9cd6
- 2026-10-21 11:01 · 9.5 · CI · verte (18 contrôles) · 58e9cd6
- 2026-10-21 11:01 · 9.5 · fusion · PR #121 fusionnée · 4472c5c
- 2026-10-21 11:01 · 9.4 · dev · lancé (Sonnet high, worktree `v2-9-4`, branche `feat/v2-9-4-embedding`) · —
- 2026-10-21 12:14 · 9.2 · décision · Anaël demande de paralléliser ce qui est sûr : 9.2 lancée à côté de 9.4 (fichiers disjoints ; 9.3, 9.7 à 9.9 restent séquentielles) · —
- 2026-10-21 12:14 · 9.2 · dev · lancé (Sonnet high, worktree `v2-9-2`, branche `feat/v2-9-2-boucle`) · —
- 2026-10-21 14:02 · 9.2 · dev · agent coupé par le chien de garde pendant les E2E (travail non commité intact) ; relancé avec son contexte · —
- 2026-10-21 14:03 · 9.4, 9.2 · décision · les deux agents coupés par le chien de garde (2 Go libres sur 16) : retour à une story à la fois ; 9.4 reprise d'abord (travail indexé), 9.2 en pause (travail non commité intact dans son worktree) · —
- 2026-10-21 14:07 · 9.4 · dev · fini (nomic-embed-text:latest vérifié par installation réelle, 274 Mo, puis désinstallé ; unit 1313 verts) · 4bdf233
- 2026-10-21 14:12 · 9.4 · second-avis · 2 medium (défaut de représentation non persisté, non testé), 5 low · —
- 2026-10-21 14:12 · 9.4 · review · lancé (Opus) · —
- 2026-10-21 14:18 · 9.4 · review · fini (2 medium corrigés : défaut de représentation enregistré après le pull, testé en E2E ; 2 low corrigés, 2 écartés) · 868b7f1
- 2026-10-21 14:18 · 9.2 · dev · repris (seul agent actif) · —
- 2026-10-21 14:34 · 9.4 · CI · rouge (E2E : ReferenceError `data` avant initialisation dans documents-base.js:232, écran non chargé ; libellé « Modèle de représentation » repris par l'encart, sélecteurs E2E ambigus) ; correctif après le dev de 9.2 (un seul agent) · 868b7f1
- 2026-10-21 14:56 · 9.2 · dev · fini (`[arena] max_tokens` 800, `loop_min_repeats` 4, `loop_window_chars` 200 ; route `/stop` ; 12 tests du détecteur ; E2E Arène verts) · 64a2edd
- 2026-10-21 14:56 · 9.4 · dev · correctif CI lancé (Sonnet) · —
- 2026-10-21 15:00 · 9.2 · second-avis · 2 high (arrêt perdu en attente, max_tokens d'Anthropic non normalisé), 3 medium (fenêtre du détecteur, faux positifs sur lignes identiques, Done doublé), 4 low · —
- 2026-10-21 15:39 · 9.4 · dev · correctif CI (état déclaré avant l'encart ; libellés de l'encart sans « Modèle de représentation ») · 7afb670
- 2026-10-21 15:39 · 9.2 · review · lancé (Opus) · —
- 2026-10-21 15:55 · 9.4 · CI · rouge (documents-base.js à 608 lignes, plafond 600) ; corrigé par l'orchestrateur (commentaires resserrés, `loadSettings`), tests statiques verts · b6c442e
- 2026-10-21 15:55 · 9.2 · review · fini (1 high + 5 medium + 3 low corrigés ; high Anthropic écarté : déjà normalisé par WallClock) · d3d2ebf
- 2026-10-21 15:56 · 9.2 · PR · #123 ouverte · d3d2ebf
- 2026-10-21 16:15 · 9.4 · CI · verte · b6c442e
- 2026-10-21 16:15 · 9.4 · fusion · PR #122 fusionnée · dfa17ef
- 2026-10-21 16:15 · 9.2 · CI · rouge (espace insécable manquante avant « : » dans i18n ; test_shell_renders_under_300_ms instable, 301 à 430 ms) · d3d2ebf
- 2026-10-21 16:18 · 9.2 · dev · rebase sur dfa17ef + espace insécable (orchestrateur), E2E test_arena_stop vert · e416767
- 2026-10-21 16:18 · 9.3 · dev · lancé (Sonnet high, worktree `v2-9-3`, branche `feat/v2-9-3-juge` empilée sur 9.2 e416767) · —
- 2026-10-21 16:37 · 9.2 · CI · verte · e416767
- 2026-10-21 16:37 · 9.2 · fusion · PR #123 fusionnée (fin de la vague V0) · 3339538
- 2026-10-21 17:21 · 9.3 · dev · fini (judge_progress, bandeau du juge, sous-statuts de colonne ; E2E Arène 59 verts) ; rebasée sur master 7001b34 · 1e0f576
- 2026-10-21 17:25 · 9.3 · second-avis · 5 high (bandeau bloqué sur « chargement », colonne qui repasse en file, panne après une note ignorée, minuteur jamais arrêté, horloge dans la région live), 2 medium, 3 low · —
- 2026-10-21 17:25 · 9.3 · review · lancé (Opus) · —
- 2026-10-21 18:23 · 9.3 · review · fini (5 high, 3 medium, 3 low corrigés ; modèle d'état unique du bandeau ; à vérifier en recette : juge froid réel) · f016867
- 2026-10-21 18:23 · 9.3 · PR · #125 ouverte · f016867
- 2026-10-21 18:24 · 9.7 · dev · lancé (Sonnet high, worktree `v2-9-7`, branche `feat/v2-9-7-mise-en-page` empilée sur 9.3 f016867) · —
- 2026-10-21 18:57 · 9.3 · CI · rouge (E2E Linux : test_models_manage.py focus après suppression, écran Modèles non touché par 9.3) ; job relancé · f016867
- 2026-10-21 19:07 · 9.3 · CI · verte après relance · f016867
- 2026-10-21 19:07 · 9.3 · fusion · PR #125 fusionnée · 3f9e9a2
- 2026-10-21 19:15 · 9.7 · dev · fini (jetons par module, classes génériques dans base.css, Chat, Arène, Banc d'essai et Références habillés ; heure du commit) · 782f512
- 2026-10-22 07:27 · run · reprise · journal commité (PR chore/etat-run), puis 9.7 : rebase sur 3f9e9a2, second-avis, revue · —
- 2026-10-22 07:31 · 9.7 · second-avis · 2 medium (classe `stack` sans règle CSS : espacement perdu dans les colonnes de l'Arène et du Banc ; captures E2E non réalignées), 5 low · —
- 2026-10-22 07:31 · 9.7 · review · lancé (Opus) · —
- 2026-10-22 11:09 · 9.7 · review · agent coupé par le chien de garde (600 s sans sortie ; travail non commité intact) ; relancé avec son contexte · —
- 2026-10-22 12:08 · 9.7 · review · fini (2 medium + 3 low corrigés, dont `stack` et icône de module sur Chat et Références ; 2 low écartés ; 2 tests E2E réalignés sur les intertitres en majuscules ; captures du README reportées en recette) · 9c79ec8
- 2026-10-22 12:08 · 9.7 · PR · #127 ouverte · 9c79ec8
- 2026-10-22 13:19 · 9.7 · CI · verte (12 contrôles) · 9c79ec8
- 2026-10-22 13:19 · 9.7 · fusion · PR #127 fusionnée · 633bf1b
- 2026-10-22 13:20 · 9.8 · dev · lancé (Sonnet high, worktree `v2-9-8`, branche `feat/v2-9-8-documents-agents`) · —
- 2026-10-22 14:45 · 9.8 · dev · fini (Discussion, Base documentaire, Évaluation, Agent seul, Équipe ; icône Agents = arena ; E2E des écrans verts) · bbaca4f
- 2026-10-22 14:50 · 9.8 · second-avis · 1 medium (échecs E2E d'accessibilité sur /documents/base classés instables sans relance isolée prouvée), 5 low · —
- 2026-10-22 14:50 · 9.8 · review · lancé (Opus) · —
- 2026-10-22 15:21 · 9.8 · review · fini (1 medium corrigé : fond de `.zone-disabled` écrasé par `.docs-drop`, E2E ajouté ; échecs d'accessibilité relancés seuls, verts ; low à la recette : largeur de l'Évaluation, espacements des piles) · 58eb41e
- 2026-10-22 15:21 · 9.8 · PR · #128 ouverte · 58eb41e
- 2026-10-22 15:39 · 9.8 · CI · verte (12 contrôles) · 58eb41e
- 2026-10-22 15:39 · 9.8 · fusion · PR #128 fusionnée · 3380be0
- 2026-10-22 15:40 · 9.9 · dev · lancé (Sonnet high, worktree `v2-9-9`, branche `feat/v2-9-9-modeles-sobriete-accueil` ; inclut le débord à 320 px sur /modeles ; préversion faite ensuite par l'orchestrateur) · —
- 2026-10-22 16:31 · 9.9 · dev · fini (Modèles réordonné : reranker à 537 px au lieu de 1870 à 1920 px ; débord à 320 px sur /modeles corrigé : chemin de cache sans coupure dans `.models-reason`) · 7abcf10
- 2026-10-22 16:36 · 9.9 · second-avis · 1 high (écran Modèles toujours à 4 135 px contre ≈1 295 dans la maquette ; catalogue à 1 666 px), 4 medium (formulaire d'installation par nom au-dessus du reranker, tableaux plus denses que la maquette, fiche contradictoire), 3 low · —
- 2026-10-22 16:36 · 9.9 · review · lancé (Opus, avec compactage de l'écran Modèles) · —
- 2026-10-22 17:29 · 9.9 · review · fini (high corrigé : actions déplacées, densité de la maquette ; reranker à 255 px, catalogue dans le premier écran à 1920×1080 ; lignes étiquetées sous 600 px ; icônes Sobriété/Accueil écartées) · 0afc828
- 2026-10-22 17:29 · 9.9 · PR · #129 ouverte · 0afc828
- 2026-10-22 21:12 · 9.9 · CI · rouge (E2E Linux morceau 1/3 : test_axe_finds_no_violation_with_four_models…[dark-1440], instabilité connue de l'Arène, sans lien avec 9.9) ; job relancé · 0afc828
- 2026-10-22 21:30 · 9.9 · CI · verte après relance · 0afc828
- 2026-10-22 21:30 · 9.9 · fusion · PR #129 fusionnée (fin de l'Epic 9) · f6f36ae
- 2026-10-22 21:30 · Epic 9 · décision · suite E2E complète sur master lancée par le workflow nocturne (run 39840701099) ; préversion 2.0.0a8 (pyproject, uv.lock, CITATION.cff) en PR, tag après la fusion · f6f36ae
- 2026-10-22 22:04 · Epic 9 · CI · suite E2E complète sur master : 732 verts, 1 rouge (test_axe_finds_no_violation_with_four_models…[light-1440], instabilité connue) · f6f36ae
- 2026-10-22 22:04 · 2.0.0a8 · CI · rouge (Windows 3.12 seul : test_routes_with_a_path_parameter_stay_under_the_read_budget, 348 ms pour 300, instable au temps) ; job relancé · 538170b
- 2026-10-23 05:43 · 2.0.0a8 · CI · verte après relance du job Windows · 538170b
- 2026-10-23 05:43 · 2.0.0a8 · fusion · PR #130 fusionnée · 1de07be
- 2026-10-23 05:43 · 2.0.0a8 · release · tag annoté `v2.0.0a8` et release GitHub en préversion (v1.3.0 reste « Latest ») · 1de07be
- 2026-10-23 05:43 · 8.5 · décision · Anaël demande de planifier la fiabilisation des tests instables : story 8.5 « La CI passe sans relance » ajoutée à l'Epic 8, avant 8.4 · —
- 2026-10-23 05:43 · Epic 9 · fin du run · 9 stories fusionnées, préversion 2.0.0a8 publiée ; à la recette : captures du README, doublon « SCÉNARIO » du Banc d'essai, largeur de l'Évaluation, écran Modèles avec les vrais modèles · —
- 2026-10-23 · 8.5 · review · fini (second avis Haiku + revue Opus : attente de l'Arène sans relèvement de délai, focus du dialogue de confirmation, course du juge, `stabilite.yml` déclenché par PR) · cddc360
- 2026-10-23 · 8.5 · décision · Anaël : budget de la coquille mesuré depuis `responseStart`, puis vérifié en CI sur Ubuntu seulement (macOS et Windows trop lents même depuis `responseStart`) · 737912f
- 2026-10-23 13:59 · 8.5 · fusion · PR #132 fusionnée, CI verte sur les trois OS, `stabilite.yml` vert (20 passages, trois OS) · 14aee5b
- 2026-10-23 · README · fusion · PR #22 fusionnée (lien vers slm-quality-bench, paragraphe aligné sur la migration du 2026-10-18) · b0d5d6e
