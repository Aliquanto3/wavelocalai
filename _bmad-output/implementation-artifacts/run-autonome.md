# Run autonome — plan et état (v2, Epic 9 : retours de la recette du 2026-10-21)

Fichier lu par `/agent-cost-kit:avancement-run`. Contrat : `planning-artifacts/sprint-change-proposal-2026-10-21.md` (approuvé par Anaël le 2026-10-21), `epics.md` §Epic 9, ARCHITECTURE-SPINE.md, DESIGN.md, EXPERIENCE.md, AGENTS.md. Run précédent (Epics 1 à 8) : `run-autonome-epics-1-8.md` et `run-autonome-mvp.md` (règles reprises ci-dessous, adaptées à ce PC).

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epic 9 | Stories 9.1 à 9.9 ; préversion 2.0.0a8 en fin d'epic (9.9) |
| Hors run | Story 8.4 | « La v2 remplace la v1 » : revient à Anaël, après l'Epic 9 |

**Au plus 1 story en développement à la fois.** Consigne d'Anaël du 2026-10-21 : pas de multi-agents en parallèle sur ce PC (trop gourmand). Les stories d'une même vague passent donc l'une après l'autre ; la vague ne sert qu'à l'ordre des dépendances.

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
- Réglages : `[server] open_browser` (9.1) ; `[arena] max_tokens`, seuil et fenêtre du détecteur de boucle (9.2). Noms définitifs fixés par 9.1 et 9.2, reportés ici.

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

- 9.6 attend la validation d'Anaël (notification) ; le run avance sur 9.1 à 9.3 pendant ce temps.

## Journal

- 2026-10-21 07:32 · Epic 9 · décision · proposition de changement du 2026-10-21 approuvée par Anaël ; Epic 9 reportée dans epics.md et sprint-status.yaml · —
