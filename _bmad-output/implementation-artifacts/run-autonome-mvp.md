# Run autonome du MVP v2 (Epics 1 à 4)

Démarré le 2026-10-18. Orchestrateur : session principale (Opus 5.5). Contrat : SPEC.md + compagnons, ARCHITECTURE-SPINE.md (AD-1 à AD-23, prioritaires), epics.md, AGENTS.md.

## Reprise après /clear

1. Lire ce fichier, puis `sprint-status.yaml`.
2. Reprendre la story « en cours » à l'étape indiquée.
3. Boucle par story : dev-story (Sonnet, effort high, worktree, branche `feat/v2-<clé>`) → second-avis (Haiku) → reviewer (Opus, liste du second avis) → contrôles locaux (contrôle rapide, `pytest tests/v2`, `python -m pytest tests/unit tests/app`, `-m e2e` si front, integration si la story en a) → PR → merge commit quand CI verte.
4. Statut du sprint et ce fichier : commités dans la PR de chaque story (copier depuis le dépôt principal dans le worktree avant le dernier push). Après fusion : dans le dépôt principal, `git checkout -- <ces deux fichiers>` puis `git pull`.

## État courant

- Étape 0 : PR #38 fusionnée (merge commit 7de6a02).
- 1.2 : étape 2 (second avis), worktree `v2-1-2`, branche `feat/v2-serveur`, dev 68de3ef.
- 1.3 (`v2-1-3`, `feat/v2-hub`), 1.5 (`v2-1-5`, `feat/v2-registre`), 1.8 (`v2-1-8`, `feat/v2-coquille`) : étape 1 (dev-story), toutes parties de 68de3ef. Après fusion de 1.2, fusionner `master` dans chacune avant sa PR.
- Worktrees : `C:\Users\Utilisateur\Documents\GitHub\wavelocalai-wt\<clé>` (hors du dépôt), chacun avec son `.venv` (`uv sync`). Spec de story : `_bmad-output/implementation-artifacts/story-<n>-<m>.md`.

## Parallélisation (autorisée par Anaël le 2026-10-18)

Vagues prévues selon les dépendances, fusion dans l'ordre du sprint (fusionner `master` dans les branches suivantes, re-verrouiller `uv.lock` en cas de conflit) :
- après 1.2 : 1.3 (store, hub), 1.5 (registre), 1.8 (coquille front ; E2E sur Edge) ;
- puis 1.4 (SSE, après 1.3) et 1.6 (défauts, après 1.5) ; 1.7 après 1.4 ; 1.9, 1.10, 1.11 après 1.7 et 1.8.

## Stories

| Story | Branche | PR | Statut | Notes |
|---|---|---|---|---|
| 1.1 | feat/v2-squelette | #39 | fusionnée (428c7e6) | revue : 1 high corrigé (`models/` ignoré par `.gitignore`) ; reports : angles morts du test AST (`importlib`, `__import__`), starlette 1.7.0 dans `constraints.txt` contre 1.8.0 dans `uv.lock` |
| 1.2 | feat/v2-serveur | #40 | PR, attente CI (c1f6aca) | revue : 2 medium corrigés (sonde Ollama lente annoncée arrêtée ; encodage cp1252 du test de lancement réel) ; reports : arrêt propre → `cancelled` (attend le hub), délais `lane_timeout_s`/`approval_expiry_s` provisoires, Origin des WebSocket, `Mount` hors test de budget |
| 1.3 | feat/v2-hub | — | dev | |
| 1.5 | feat/v2-registre | — | attend la fusion de 1.3 (dev cf78d71, second avis fait : 2 medium = MoE sans `/api/show` sert le total comme actif ; AC3/AC4 non tenus tant que facts et débit sont en mémoire). Suite : relancer l'agent dev 1.5 pour fusionner `master`, brancher `SqliteFactsStore` + médiane `tps` sur `runs`, renuméroter la migration, corriger le MoE ; puis reviewer Opus avec ces constats | reports : `SqliteFactsStore` et médiane `tps` depuis `runs` à brancher sur le store de 1.3 ; migration `0002_model_facts.sql` à renuméroter après celle du hub ; « tient en mémoire » = RAM libre psutil seulement ; conflits attendus `web/app.py` (lifespan) et `errors.py` |
| 1.8 | feat/v2-coquille | — | dev | |

## Décisions prises seul

- `_bmad-output/party-mode/` non versionné (mémoire de session, pas un livrable).
- Story 1.1 : pydantic reste en 2.12.x (contrainte `pydantic>=2.9.0`) au lieu de 2.14.1 (spine §Stack). Motif : crewai 1.15.28 de la v1 exige `pydantic<2.13` ; avec 2.14.1, uv rétrograde crewai à 1.6.1 et 17 tests v1 échouent. NFR14 et AD-2 (v1 intacte) priment. À ratifier par Anaël (mise à jour de la spine §Stack via `bmad-spec`, ou relèvement à la bascule).
- E2E : Chromium de Playwright absent, mais Edge installé fonctionne avec Playwright (vérifié, Edge 155). Le conftest E2E de la v2 accepte `WAVELOCALAI_E2E_CHROMIUM` (comme la v1) ; en local : `$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`. Aucun téléchargement.
- Ollama : utiliser `http://127.0.0.1:11434` (`localhost` échoue en IPv6 sur ce poste).

## Points en attente pour Anaël


- Ratifier l'écart pydantic 2.12.x (voir « Décisions prises seul », story 1.1).

## Préversions (tags et releases en attente d'Anaël)

(aucune pour l'instant)
