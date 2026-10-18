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
| 1.2 | feat/v2-serveur | #40 | fusionnée (4e33370) ; 1 correction CI (sonde Ollama : client httpx construit hors boucle) | revue : 2 medium corrigés (sonde Ollama lente annoncée arrêtée ; encodage cp1252 du test de lancement réel) ; reports : arrêt propre → `cancelled` (attend le hub), délais `lane_timeout_s`/`approval_expiry_s` provisoires, Origin des WebSocket, `Mount` hors test de budget |
| 1.3 | feat/v2-hub | #41 | fusionnée (e9af784) ; revue : high course stop/flush et medium feuille pendant annulation corrigés | reports : réhydratation `sources` (attend `chunks`), `409 run_busy` (story des POST runs), SSE et routes de runs (1.4), effacement AD-13 |
| 1.4 | feat/v2-flux-sse (depuis d86d06a) | #42 | fusionnée ; revue : `ModelRef` aligné sur 1.5, medium `_error_envelope` corrigé ; 227 tests v2 | 219 tests v2 ; a créé `models/port.py` + `fake.py` en doublon de `port.py` de 1.5 → réconcilier à la fusion ; hub : `publish_token`, `watch`, `active_root`, `run_busy` ajoutés ; reports : `token` non groupé ?, CO₂ des runs de test `unmeasurable` |
| 1.7 | feat/v2-flux-systeme (depuis eb81d58) | — | revue faite (0c90516 : arrêt réel avec flux ouverts corrigé + test sous-processus ; feuille en erreur comptée non mesurable ; `contrat-api.md` précise que le client relit `GET /api/carbon/session` à chaque connexion) ; `feat/v2-defauts` fusionné (6eccc25, 374 tests v2, 1286 v1) ; PR #45 (après #44) | reports : `carbon_updated` publié par personne avant 2.3, reset de session avec Sobriété, version Ollama de la fiche `null` avant la 1re sonde, GPU hors flux 2 s |
| 1.9 | feat/v2-barre-haute (1.7 3964610 + 1.8 39bfed1 fusionnées, 54e43c5) | — | revue Opus (dev edb870e : 311 tests v2, 72 E2E ; second avis : 2 medium coquille/redémarrage, cache sonde 1 s contre 5 s d'AD-15) | reports : « Réessayer » ne force pas la sonde, pas de pause du flux sur `visibilitychange` (Accueil 1.11) ; sonde du flux système à cache 1 s |
| 1.10 | feat/v2-selecteur (1.6 + 1.8 + 1.9 fusionnées, 9151f62) | — | dev (reprise après fusion de 1.9 faite par l'orchestrateur : refusée à l'agent par le classifieur de permissions) | réutilise `core/` de 1.9 |
| 1.11 | feat/v2-accueil (depuis 1.9 edb870e) | — | dev | |
| 1.6 | feat/v2-defauts | #44 | fusionnée ; revue : 4 medium corrigés ; reprise : `feat/v2-registre` fusionné, `0003` en dates ISO, `SqlitePreferenceStore` branché ; 334 tests v2 | 216 tests v2, 3 integration verts une fois ; reports : `PreferenceStore` en mémoire à brancher sur le store (migration `0003_preferences.sql` présente), pas de route d'écriture de défaut (UI) |
| 1.5 | feat/v2-registre | #43 | fusionnée ; revue : medium dates ISO corrigé ; `master` fusionné (`port.py` de 1.4) ; 278 tests v2, 1286 v1 ; reports : identifiants cloud à vérifier (2.4/2.5), modèles supprimés qui réapparaissent à froid | reports : `SqliteFactsStore` et médiane `tps` depuis `runs` à brancher sur le store de 1.3 ; migration `0002_model_facts.sql` à renuméroter après celle du hub ; « tient en mémoire » = RAM libre psutil seulement ; conflits attendus `web/app.py` (lifespan) et `errors.py` |
| 1.8 | feat/v2-coquille | — | revue faite (39bfed1 : 1 medium corrigé, hash hors route au chargement) ; `feat/v2-flux-systeme` fusionné ; 413 tests v2, 25 E2E, 1286 v1 ; PR #46 (après #45) | 162 tests v2, 24 E2E sur Edge ; reports : pastilles barre haute (1.9), blanc sur primary-dark 4,26:1, CSP sans `blob:` (exports), pyyaml non déclaré |

## Décisions prises seul

- `_bmad-output/party-mode/` non versionné (mémoire de session, pas un livrable).
- Story 1.1 : pydantic reste en 2.12.x (contrainte `pydantic>=2.9.0`) au lieu de 2.14.1 (spine §Stack). Motif : crewai 1.15.28 de la v1 exige `pydantic<2.13` ; avec 2.14.1, uv rétrograde crewai à 1.6.1 et 17 tests v1 échouent. NFR14 et AD-2 (v1 intacte) priment. À ratifier par Anaël (mise à jour de la spine §Stack via `bmad-spec`, ou relèvement à la bascule).
- Story 1.6 : les usages `agent` et `rag` n'ont pas de règle en v1 ni dans les critères ; règle provisoire posée sur le registre (seuil de 3 milliards de paramètres actifs, repli sur le défaut `chat` avec sa raison), à confirmer avec les mesures du banc.
- `models/port.py` : `ModelRef` de la story 1.5 retenu (AD-9 : `origin` avec `unknown`, `kind` en `Literal`) ; la 1.4 s'y aligne à l'identique et y ajoute les types du port `ChatModel` d'AD-8.
- E2E : Chromium de Playwright absent, mais Edge installé fonctionne avec Playwright (vérifié, Edge 155). Le conftest E2E de la v2 accepte `WAVELOCALAI_E2E_CHROMIUM` (comme la v1) ; en local : `$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`. Aucun téléchargement.
- Ollama : utiliser `http://127.0.0.1:11434` (`localhost` échoue en IPv6 sur ce poste).

## Points en attente pour Anaël


- Ratifier l'écart pydantic 2.12.x (voir « Décisions prises seul », story 1.1).

- Ollama : Anaël peut l'utiliser ailleurs pendant l'Epic 1 (accord du 2026-10-18). Avant la story 2.1, vérifier `http://127.0.0.1:11434/api/version` ; s'il est arrêté, notifier Anaël et avancer sur ce qui n'en dépend pas. Tests integration d'Epic 1 sautés si Ollama absent : les noter « à rejouer ».

## Préversions (tags et releases en attente d'Anaël)

(aucune pour l'instant)
