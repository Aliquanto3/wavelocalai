# Run autonome du MVP v2 (Epics 1 à 4)

Démarré le 2026-10-18. Orchestrateur : session principale (Opus 5.5). Contrat : SPEC.md + compagnons, ARCHITECTURE-SPINE.md (AD-1 à AD-23, prioritaires), epics.md, AGENTS.md.

## Reprise après /clear

1. Lire ce fichier, puis `sprint-status.yaml`.
2. Reprendre la story « en cours » à l'étape indiquée.
3. Boucle par story : dev-story (Sonnet, effort high, worktree, branche `feat/v2-<clé>`) → second-avis (Haiku) → reviewer (Opus, liste du second avis) → contrôles locaux (contrôle rapide, `pytest tests/v2`, `python -m pytest tests/unit tests/app`, `-m e2e` si front, integration si la story en a) → PR → merge commit quand CI verte.
4. Statut du sprint et ce fichier : commités dans la PR de chaque story (copier depuis le dépôt principal dans le worktree avant le dernier push). Après fusion : dans le dépôt principal, `git checkout -- <ces deux fichiers>` puis `git pull`.

## État courant

- Étape 0 : PR #38 fusionnée (merge commit 7de6a02).
- Story en cours : 1.1, étape 4 (PR ouverte, attente CI), worktree `..\wavelocalai-wt\v2-1-1`, branche `feat/v2-squelette`.
- Worktrees : `C:\Users\Utilisateur\Documents\GitHub\wavelocalai-wt\<clé>` (hors du dépôt), chacun avec son `.venv` (`uv sync`). Spec de story : `_bmad-output/implementation-artifacts/story-<n>-<m>.md`.

## Stories

| Story | Branche | PR | Statut | Notes |
|---|---|---|---|---|
| 1.1 | feat/v2-squelette | (en cours) | PR | revue : 1 high corrigé (`models/` ignoré par `.gitignore`) ; reports : angles morts du test AST (`importlib`, `__import__`), starlette 1.7.0 dans `constraints.txt` contre 1.8.0 dans `uv.lock` |

## Décisions prises seul

- `_bmad-output/party-mode/` non versionné (mémoire de session, pas un livrable).
- Story 1.1 : pydantic reste en 2.12.x (contrainte `pydantic>=2.9.0`) au lieu de 2.14.1 (spine §Stack). Motif : crewai 1.15.28 de la v1 exige `pydantic<2.13` ; avec 2.14.1, uv rétrograde crewai à 1.6.1 et 17 tests v1 échouent. NFR14 et AD-2 (v1 intacte) priment. À ratifier par Anaël (mise à jour de la spine §Stack via `bmad-spec`, ou relèvement à la bascule).
- Ollama : utiliser `http://127.0.0.1:11434` (`localhost` échoue en IPv6 sur ce poste).

## Points en attente pour Anaël

- Chromium de Playwright absent (`.venv\Scripts\python -m playwright install chromium`) : nécessaire aux E2E dès la story 1.8. Notifié le 2026-10-18.

- Ratifier l'écart pydantic 2.12.x (voir « Décisions prises seul », story 1.1).

## Préversions (tags et releases en attente d'Anaël)

(aucune pour l'instant)
