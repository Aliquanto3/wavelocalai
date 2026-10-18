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
| 1.7 | feat/v2-flux-systeme (depuis eb81d58) | — | revue faite (0c90516 : arrêt réel avec flux ouverts corrigé + test sous-processus ; feuille en erreur comptée non mesurable ; `contrat-api.md` précise que le client relit `GET /api/carbon/session` à chaque connexion) ; `feat/v2-defauts` fusionné (6eccc25, 374 tests v2, 1286 v1) ; PR #45 fusionnée | reports : `carbon_updated` publié par personne avant 2.3, reset de session avec Sobriété, version Ollama de la fiche `null` avant la 1re sonde, GPU hors flux 2 s |
| 1.9 | feat/v2-barre-haute | — | revue faite (dc568bb : 3 medium corrigés, dont chien de garde du flux SSE et regex de test cassée ; écart AD-15 gardé, à arbitrer) ; `feat/v2-coquille` fusionné ; 424 tests v2, 74 E2E, 1286 v1 ; PR #47 fusionnée | reports : « Réessayer » ne force pas la sonde, pas de pause du flux sur `visibilitychange` (Accueil 1.11) ; sonde du flux système à cache 1 s |
| 1.10 | feat/v2-selecteur (1.6 + 1.8 + 1.9 fusionnées, 9151f62) | #50 | fusionnée ; revue : 3 medium corrigés ; 428 tests v2, 101 E2E, 1286 v1 | reports : Échap des panneaux de la barre haute sans `preventDefault`, `wl-error` affiche des accents graves Markdown, composants pas encore montés dans un écran |
| 1.11 | feat/v2-accueil (depuis 1.9 edb870e) | — | second avis fait (1 medium : conflit certain `core/system.js` avec 1.9 revue ; lows : « en direct » affiché pendant la pause, focus perdu sur Réessayer). PR #51 (avec version 2.0.0a1) ; revue : conflit `core/system.js` résolu, relecture de santé arrêtée pendant la pause ; 429 tests v2, 123 E2E, 1286 v1 | reports : « Ollama sans modèle » attend `GET /api/models` (désormais sur master) ; CO₂ en ligne de détail de la carte Mode ; conflits `core/*.js` probables avec 1.9 revue et 1.10 |
| 2.2 | feat/v2-ecran-chat (2.1 dc1c4e1 + 1.10 fusionnées) | — | second avis (dev 67042f2 : 475 tests v2, 124 E2E, A19 intégré : « Envoyer » sur `--color-primary-fill`, E2E contraste sombre) | reports : « Télécharger » attend les routes de conversation (2.6), débit provisoire à 1 token pour 4 caractères, tableaux Markdown non rendus, pas de reprise après rechargement complet |
| 2.3 | feat/v2-co2-local (depuis 2.1 revue 16f29ca) | — | dev | |
| 2.4 | feat/v2-chat-cloud (2.1 dc1c4e1 + 1.10 fusionnées, 26dfdc8) | — | revue Opus (dev e81b0f1 : 543 tests v2 ; `origin/master` fusionné ; second avis : medium erreur de flux OpenAI → `internal`, medium clé Mistral non masquée dans les journaux) | reports : CO₂ cloud (2.5), outils/`response_schema`/`think` non envoyés, `temperature` omise pour `gpt-5/6/o*`, `gpt-4o` retiré du toml mais cité par `CLOUD_JUDGE_PREFERENCE` ; SDK openai 2.54.0 (3.35.1 trop récente) ; `registry.resolve` rend une référence sans clé pour dire `cloud_key_missing` |
| 2.1 | feat/v2-chat-ollama (depuis master 89e20e1) | — | revue faite (dd12ee8 : prefill en champ optionnel, `co2` des runs annulés via `declare_leaf`) ; `feat/v2-accueil` fusionné ; integration verte sur `qwen2.5:1.5b` (installé avec l'accord d'Anaël) ; 472 tests v2, 1286 v1 ; PR #52 (après #51) | integration non jouée : `qwen2.5:1.5b` absent (notifié) ; code `generation_interrupted` (AD-5) au lieu de `interrupted` d'epics.md ; CO₂ `unmeasurable` jusqu'à 2.3 ; `hub.py` efface le partiel sur `retry` ; `registry.extra_refs` |
| 1.6 | feat/v2-defauts | #44 | fusionnée ; revue : 4 medium corrigés ; reprise : `feat/v2-registre` fusionné, `0003` en dates ISO, `SqlitePreferenceStore` branché ; 334 tests v2 | 216 tests v2, 3 integration verts une fois ; reports : `PreferenceStore` en mémoire à brancher sur le store (migration `0003_preferences.sql` présente), pas de route d'écriture de défaut (UI) |
| 1.5 | feat/v2-registre | #43 | fusionnée ; revue : medium dates ISO corrigé ; `master` fusionné (`port.py` de 1.4) ; 278 tests v2, 1286 v1 ; reports : identifiants cloud à vérifier (2.4/2.5), modèles supprimés qui réapparaissent à froid | reports : `SqliteFactsStore` et médiane `tps` depuis `runs` à brancher sur le store de 1.3 ; migration `0002_model_facts.sql` à renuméroter après celle du hub ; « tient en mémoire » = RAM libre psutil seulement ; conflits attendus `web/app.py` (lifespan) et `errors.py` |
| 1.8 | feat/v2-coquille | — | revue faite (39bfed1 : 1 medium corrigé, hash hors route au chargement) ; `feat/v2-flux-systeme` fusionné ; 413 tests v2, 25 E2E, 1286 v1 ; PR #46 fusionnée | 162 tests v2, 24 E2E sur Edge ; reports : pastilles barre haute (1.9), blanc sur primary-dark 4,26:1, CSP sans `blob:` (exports), pyyaml non déclaré |

## Décisions prises seul

- `_bmad-output/party-mode/` non versionné (mémoire de session, pas un livrable).
- Story 1.1 : pydantic reste en 2.12.x (contrainte `pydantic>=2.9.0`) au lieu de 2.14.1 (spine §Stack). Motif : crewai 1.15.28 de la v1 exige `pydantic<2.13` ; avec 2.14.1, uv rétrograde crewai à 1.6.1 et 17 tests v1 échouent. NFR14 et AD-2 (v1 intacte) priment. À ratifier par Anaël (mise à jour de la spine §Stack via `bmad-spec`, ou relèvement à la bascule).
- Story 1.6 : les usages `agent` et `rag` n'ont pas de règle en v1 ni dans les critères ; règle provisoire posée sur le registre (seuil de 3 milliards de paramètres actifs, repli sur le défaut `chat` avec sa raison), à confirmer avec les mesures du banc.
- `models/port.py` : `ModelRef` de la story 1.5 retenu (AD-9 : `origin` avec `unknown`, `kind` en `Literal`) ; la 1.4 s'y aligne à l'identique et y ajoute les types du port `ChatModel` d'AD-8.
- Story 2.1 : débit de prefill exigé par le critère alors que `ChatResult` est figé par AD-8 → champ optionnel ajouté en fin de `ChatResult` (écart additif à AD-8, à ratifier). Code de coupure `generation_interrupted` (AD-5 interdit un code qui reprend un statut) au lieu de `interrupted` d'epics.md.
- E2E : Chromium de Playwright absent, mais Edge installé fonctionne avec Playwright (vérifié, Edge 155). Le conftest E2E de la v2 accepte `WAVELOCALAI_E2E_CHROMIUM` (comme la v1) ; en local : `$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`. Aucun téléchargement.
- Ollama : utiliser `http://127.0.0.1:11434` (`localhost` échoue en IPv6 sur ce poste).

- `tests/app/test_nothing_lost.py::test_agent_*` (v1) : échec intermittent vu une fois en revue de 1.10, vert en relance sur la branche ; 4 échecs dans le dépôt principal dont le `.venv` n'est plus synchronisé depuis la 1.1 (non modifié par le run). Pour Anaël : `uv sync` dans le dépôt principal remettra le `.venv` au verrou actuel (Python 3.11+, deps v2).

## Décisions d'Anaël (2026-10-18, 18 h 30)

- Ollama rendu au run vers 20 h (quelques minutes de retard possibles) pour l'Epic 2.
- pydantic 2.12.x acté jusqu'à la bascule (spine §Stack à corriger via `bmad-spec`).
- AD-15 amendé : cache 5 s pour les routes de lecture, 1 s pour la sonde du flux système (spine à corriger via `bmad-spec`).
- Défauts `agent`/`rag` : règle provisoire gardée, seuils à caler sur slm-quality-bench à l'Epic 5.
- Définition des Epics 5 à 8 et des reports : confiée à une autre session (branche `docs/`), qui ne touche ni `sprint-status.yaml` ni ce fichier.

## Changement de cours d'Anaël (2026-10-18, soir)

- PR #48 (stories des Epics 5 à 8, inventaire des reports, décisions Q1 à Q7) et PR #49 (mise à jour UX) vont sur master, fusionnées par Anaël.
- Prérequis UX de la 2.2 et de l'Epic 5 levé par la PR #49. La 2.2 ne continue qu'une fois master contenant le commit « Docs: jeton primary-fill (décision Q1) et écrans v2 des Epics 5 à 7 » ; master est alors fusionné dans sa branche (pas de rebase).
- Story 2.2, critère A19 (décision Q1, option C) : tout fond violet portant du texte blanc utilise `var(--color-primary-fill)` (#451DC7 clair, #6A4DE6 sombre, déjà dans `tokens.css`) ; `--color-primary` pour texte violet, bordures, contours, interrupteur coché ; bouton plein désactivé = fond `surface-alt`, bordure `line`, texte `ink-secondary` (jamais la seule opacité) ; E2E axe-core en sombre sur le premier bouton plein, zéro violation `color-contrast`, sans exclusion ; test de dérive `test_shell_static.py` vert, aucune couleur en dur. Lire dans DESIGN.md la « Note `primary-fill` » et « Composants de la v2 ».
- Epics 5 à 7 : EXPERIENCE.md, section « Écrans v2 des Epics 5 à 7 », prime pour le comportement à l'écran ; epics.md prime pour le contrat d'API ; `[ASSUMPTION]` appliqués tels quels ; « Open Questions » 3 à 5 non implémentées sans décision.
- Toute branche en cours fusionne `origin/master` après l'arrivée de #48/#49 (sans rebase).

## Points en attente pour Anaël



- Ollama : Anaël peut l'utiliser ailleurs pendant l'Epic 1 (accord du 2026-10-18). Avant la story 2.1, vérifier `http://127.0.0.1:11434/api/version` ; s'il est arrêté, notifier Anaël et avancer sur ce qui n'en dépend pas. Tests integration d'Epic 1 sautés si Ollama absent : les noter « à rejouer ».


## Préversions (tags et releases en attente d'Anaël)

### 2.0.0a1 (fin de l'Epic 1) — en attente d'Anaël

Version `2.0.0a1` posée dans `pyproject.toml`, `uv.lock` et `CITATION.cff` par la PR de la story 1.11. **Tag `v2.0.0-alpha.1` et release GitHub non créés** : à faire par Anaël après la recette.

Commandes (après recette) :
`git tag -a v2.0.0-alpha.1 -m "wavelocalai 2.0.0a1 : coquille de la v2"` sur le merge commit de la PR 1.11, `git push origin v2.0.0-alpha.1`, puis `gh release create v2.0.0-alpha.1 --prerelease --title "2.0.0a1 : coquille de la v2" --notes-file <notes ci-dessous>`.

Brouillon des notes :

> Première préversion de la v2, à côté de la v1 (toujours lancée par `wavelocalai`, port 8501). La v2 se lance par `wavelocalai-v2` (port 8502) et demande Python 3.11 ou plus.
>
> - Serveur local FastAPI protégé : écoute sur `127.0.0.1` seulement, en-têtes `Host` et `Origin` étrangers refusés, télémétries coupées, verrou du dossier de données, journaux en rotation, arrêt propre même avec des flux ouverts.
> - Hub des exécutions : toute exécution est un run enregistré dans SQLite, suivi en flux (SSE), rejouable sans perte ni doublon, annulable.
> - Registre des modèles : modèles Ollama et cloud configurés, origine (Local, Cloud, Origine inconnue), « tient en mémoire », débit mesuré sur ce poste, modèle par défaut par usage avec sa raison.
> - Flux système en direct et session carbone.
> - Coquille du front aux couleurs de Wavestone (modules JS natifs, aucune dépendance tierce, aucune requête hors de la machine) : barre haute (Ollama, cloud, CO₂ de session), Accueil qui dit en 5 secondes si la démo peut partir ; composants sélecteur de modèle au clavier et suivi d'un run, prêts pour le chat de la préversion suivante.
> - Accessibilité vérifiée par axe-core en clair et sombre sur chaque écran livré.
>
> Pas encore là : chat, Arène, base documentaire (préversions suivantes). Les modules à venir sont visibles et désactivés, avec leur raison.

Recette humaine à jouer (environ 10 min) :
1. `uv sync` dans le dépôt principal, puis `uv run wavelocalai-v2` ; ouvrir `http://127.0.0.1:8502`.
2. Ollama arrêté : l'Accueil s'affiche tout de suite, pastille « Ollama ne répond pas », carte Système « Indisponible » avec la marche à suivre ; relancer Ollama : la pastille repasse « disponible » en moins de 3 s.
3. Barre haute : interrupteur « Autoriser le cloud » (aide lisible, remis à faux au rechargement), panneau CO₂, menu Affichage (thème sombre, mode projection).
4. Modules non livrés visibles, désactivés, avec « Pas encore disponible dans cette préversion ».
5. Navigation au clavier seul (lien d'évitement, focus visible) ; fenêtre réduite à 320 px sans défilement horizontal.
6. Arrêter le serveur (Ctrl+C) avec l'Accueil ouvert : il s'arrête en quelques secondes ; un second lancement sur le même dossier est refusé avec un message clair.
7. `uv run wavelocalai` : la v1 se lance toujours sur 8501.
