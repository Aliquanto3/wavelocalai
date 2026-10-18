# Run autonome — plan et état (MVP v2, Epics 1 à 4)

Fichier lu par `/agent-cost-kit:avancement-run`. Le détail du run (règles, outils, décisions, préversions et recettes, reports par story) reste dans `run-autonome-mvp.md` ; ce fichier-ci porte le périmètre, les vagues et le journal daté.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 1 à 4 | MVP de la v2 ; préversions 2.0.0a1 à 2.0.0a4, une par epic (tag et release par Anaël après recette) |
| Hors run | Epics 5 à 8 | définies par une autre session (PR #48, #49) ; après le MVP |

## Règles fixes

Voir `run-autonome-mvp.md`, sections « Reprise après /clear » et « État courant ». Par story : dev-story (Sonnet, effort high, worktree `..\wavelocalai-wt\<clé>`) → second-avis (Haiku) → reviewer (Opus) → fusion de la branche précédente ou de `origin/master` par l'orchestrateur → contrôles complets (`_outils/checks.sh`) → `_outils/finalize.sh` → PR → merge commit quand la CI est verte.

## Parallélisme

- **Au plus 3 stories en développement à la fois**, chacune dans son worktree.
- Fusion sur master dans l'ordre des dépendances ; master est fusionné dans les branches suivantes (jamais de rebase).

## Sprint 1 — MVP (Epics 1 à 4)

Dépendances des Epics 3 et 4 au-delà de 3.3 et 4.2 : estimées d'après epics.md, à ajuster.

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 1.1 ★ | — |
| V1 | 1.2 | 1.1 |
| V2 | 1.3 · 1.5 · 1.8 | 1.2 |
| V3 | 1.4 · 1.6 | 1.4 ← 1.3 ; 1.6 ← 1.5 |
| V4 | 1.7 | 1.4 |
| V5 | 1.9 · 1.10 · 1.11 ★ | 1.9 ← 1.7, 1.8 ; 1.10 ← 1.6, 1.8 ; 1.11 ← 1.7, 1.8 |
| V6 | 2.1 | 1.10 |
| V7 | 2.2 · 2.3 · 2.4 | 2.2 ← 2.1, 1.10 ; 2.3 ← 2.1 ; 2.4 ← 2.1 |
| V8 | 2.5 · 2.6 ★ · 3.1 | 2.5 ← 2.4, 2.3 ; 2.6 ← 2.2 ; 3.1 ← 2.4, 2.3 |
| V9 | 3.2 · 3.3 · 4.1 | 3.2 ← 3.1 ; 3.3 ← 3.1 ; 4.1 ← 2.3 |
| V10 | 3.4 · 4.2 | 3.4 ← 3.2, 3.3 ; 4.2 ← 4.1 |
| V11 | 3.5 · 4.3 · 4.4 | 3.5 ← 3.4 ; 4.3 ← 4.2 ; 4.4 ← 4.1, 2.1 |
| V12 | 3.6 ★ · 4.5 · 4.6 | 3.6 ← 3.5, 2.6 ; 4.5 ← 4.4, 4.2 ; 4.6 ← 4.4 |
| V13 | 4.7 · 4.8 | 4.7 ← 4.4 ; 4.8 ← 4.4 |
| V14 | 4.9 ★ | 4.9 ← 4.3, 4.5, 4.6, 4.7, 4.8, 3.6 |

## Journal

Convention : `- AAAA-MM-JJ HH:MM · story · étape · résultat · commit`. Étapes : `dev` (lancé / fini), `second-avis`, `review`, `fusion` (PR fusionnée sur master), `CI`, `report`, `décision`, `blocked`, `attente humaine`. Lignes reconstituées le 2026-10-18 à 22:25 depuis `git log` (heures des merge commits des PR) ; les étapes intermédiaires des stories fusionnées ne sont pas reprises.

- 2026-10-18 15:55 · 1.1 · fusion · PR #39 fusionnée · 428c7e6
- 2026-10-18 16:58 · 1.2 · fusion · PR #40 fusionnée · 4e33370
- 2026-10-18 17:20 · 1.3 · fusion · PR #41 fusionnée · e9af784
- 2026-10-18 17:28 · 1.4 · fusion · PR #42 fusionnée · d922c13
- 2026-10-18 17:57 · 1.5 · fusion · PR #43 fusionnée · 59c2aa2
- 2026-10-18 18:08 · 1.6 · fusion · PR #44 fusionnée · 220c15f
- 2026-10-18 18:18 · 1.7 · fusion · PR #45 fusionnée · 2936e3f
- 2026-10-18 18:31 · 1.8 · fusion · PR #46 fusionnée · 89e20e1
- 2026-10-18 18:46 · 1.9 · fusion · PR #47 fusionnée · 422aa59
- 2026-10-18 19:27 · 1.10 · fusion · PR #50 fusionnée · bcc11ef
- 2026-10-18 20:07 · 1.11 · fusion · PR #51 fusionnée, version 2.0.0a1, Epic 1 terminée (tag et release en attente d'Anaël) · ac9c593
- 2026-10-18 20:10 · 2.1 · fusion · PR #52 fusionnée · f77d1f0
- 2026-10-18 20:31 · 3.1 · dev · fini · de64a0d
- 2026-10-18 20:46 · 2.2 · fusion · PR #53 fusionnée · 3f84605
- 2026-10-18 20:59 · 3.1 · review · faite, attend la fusion de 2.6 · 125ba68
- 2026-10-18 21:22 · 2.3 · fusion · PR #54 fusionnée · a7ab77b
- 2026-10-18 21:40 · 2.4 · fusion · PR #55 fusionnée · 33adc49
- 2026-10-18 · 3.2 · dev · lancé (Sonnet high, worktree v2-3-2) · —
- 2026-10-18 · 3.3 · dev · lancé, partie serveur (Sonnet high, worktree v2-3-3) · —
- 2026-10-18 · 4.1 · dev · lancé (Sonnet high, worktree v2-4-1) · —
- 2026-10-18 21:54 · 3.3 · dev · fini, partie serveur, 643 tests v2 · 2c6f54f
- 2026-10-18 22:01 · 4.1 · dev · fini, 646 tests v2 · 64181e4
- 2026-10-18 22:03 · 2.5 · fusion · PR #56 fusionnée · a5585c3
- 2026-10-18 22:05 · 3.3 · second-avis · 4 low · —
- 2026-10-18 22:07 · 3.3 · review · aucun medium, 3 low corrigés ; reste la seconde passe écran après 3.2 · a0b60de
- 2026-10-18 22:10 · 4.1 · second-avis · 2 medium, 3 low · —
- 2026-10-18 22:11 · 3.2 · dev · fini, 618 tests v2, 176 E2E · 1612fe2
- 2026-10-18 22:15 · 2.6 · review · faite plus tôt (bd1ff0e) ; master fusionné, version 2.0.0a2, test E2E stabilisé · 4a2f8e1
- 2026-10-18 22:17 · 4.1 · review · 1 medium corrigé (annulation pendant l'écriture), fusion de master résolue · f3536cb
- 2026-10-18 22:20 · 4.2 · dev · lancé (Sonnet high, worktree v2-4-2, depuis 4.1 revue) · —
- 2026-10-18 22:20 · 3.2 · second-avis · 2 low · —
- 2026-10-18 22:25 · 2.6 · contrôles · contrôles locaux verts (649 v2, 172 E2E, 5 integration, 1286 v1) ; PR à ouvrir · 4a2f8e1
- 2026-10-18 22:24 · 2.6 · contrôles · finalisée, PR #57 ouverte avec la version 2.0.0a2 · 4a2f8e1
