# Run autonome du MVP v2 (Epics 1 à 4)

Démarré le 2026-10-18. Orchestrateur : session principale (Opus 5.5). Contrat : SPEC.md + compagnons, ARCHITECTURE-SPINE.md (AD-1 à AD-23, prioritaires), epics.md, AGENTS.md.

## Reprise après /clear

1. Lire ce fichier, puis `sprint-status.yaml`.
2. Reprendre la story « en cours » à l'étape indiquée.
3. Boucle par story : dev-story (Sonnet, effort high, worktree, branche `feat/v2-<clé>`) → second-avis (Haiku) → reviewer (Opus, liste du second avis) → contrôles locaux (contrôle rapide, `pytest tests/v2`, `python -m pytest tests/unit tests/app`, `-m e2e` si front, integration si la story en a) → PR → merge commit quand CI verte.
4. Journal daté : après chaque étape, ajouter une ligne `- AAAA-MM-JJ HH:MM · story · étape · résultat · commit` à la section « Journal » de `run-autonome.md` (lu par `/agent-cost-kit:avancement-run`). Statut du sprint, ce fichier et `run-autonome.md` : commités dans la PR de chaque story (copier depuis le dépôt principal dans le worktree avant le dernier push). Après fusion : dans le dépôt principal, sauvegarder ces trois fichiers, `git checkout -- <ces fichiers>`, `git pull`, puis les restaurer (`run-autonome.md`, nouveau, n'est pas encore sur master : rien à restaurer pour lui tant qu'il est non suivi) (ils portent l'état le plus récent).
5. Avant la PR d'une story, fusionner dans sa branche la branche de la story précédente **après** son commit de statut (ou `origin/master` si elle est fusionnée) : les fichiers d'état restent linéaires, sans conflit.
6. Les fusions de branches (`git merge`) sont faites par l'orchestrateur : le classifieur de permissions les refuse aux sous-agents. Conflit sémantique : laisser la fusion en cours et confier la résolution au reviewer (« étape 1 obligatoire »).
7. Outils de l'orchestrateur, dans `C:\Users\Utilisateur\Documents\GitHub\wavelocalai-wt\_outils\` (lancer avec `.venv\Scripts\python` du dépôt principal ; `finalize.ps1 <worktree> <branche> <préfixe de clé> <libellé>`) : `set_status.py` (statut du sprint), `set_row.py` (ligne du tableau ci-dessous), `finalize.ps1` (statut `done`, copie des fichiers d'état dans le worktree, commit `Chore: statut du sprint…`, push), `keep_both.py` / `ours_then_theirs.py` (conflits « garder les deux »), `bump_version.py`.
8. E2E : `$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`. Tests : `$env:PYTHONUTF8 = "1"`. Ollama : `http://127.0.0.1:11434`, `qwen2.5:1.5b` installé.

## État courant (2026-10-18 vers 23 h, avant /clear)

- **Epics 1 et 2 terminées** (PR #39 à #57). Versions 2.0.0a1 et 2.0.0a2 posées ; tags et releases en attente d'Anaël (section « Préversions »).
- Suivi : `run-autonome.md` (périmètre, vagues, journal daté, lu par `/agent-cost-kit:avancement-run`) ; ajouter une ligne de journal après chaque étape.
- Outils : `_outils/finalize.sh <worktree> <branche> <préfixe> <libellé>` (statut `done`, copie des 3 fichiers d'état, commit, push ; préférer à `finalize.ps1`), `_outils/checks.sh <worktree>` (contrôles complets, résumé court ; lancer en arrière-plan, sortie dans le scratchpad). `keep_both.py <fichier> [séparateur]` : un seul fichier par appel.
- Pièges vus : « uvx black a échoué » sans détail dans le contrôle rapide = un fichier à reformater (la sortie emoji de black est perdue) : lancer `uvx --offline black@25.12.0 <fichier>` ; faire `uv sync` dans un worktree après toute fusion qui change `uv.lock` (sinon des dizaines d'échecs v2) ; un test E2E qui lance un run doit attendre sa fin (sinon `409 run_busy` au test suivant) ; espaces insécables avant « : ; ! ? » dans `fr.json` (test).

**Ordre des fusions à venir** (chacune : fusionner dans sa branche `origin/master`, `uv sync`, `checks.sh`, `finalize.sh`, PR, CI verte, merge commit, puis dans le dépôt principal sauvegarder les 3 fichiers d'état, `git checkout --` dessus, `git pull`, les restaurer) :
1. **3.1** (`v2-3-1`, `feat/v2-arene-serveur`, revue 125ba68) : fusionner `origin/master` (conflits probables avec 2.4, 2.5, 2.6 dans `web/app.py`, `errors.py`, `inference/`).
2. **4.1** (`v2-4-1`, `feat/v2-rag-index`, revue f3536cb ; master a5585c3 déjà fusionné) : fusionner `origin/master`.
3. **3.2** (`v2-3-2`, `feat/v2-arene-ecran`, revue d104fc4) : fusionner `origin/master`.
4. **3.3** (`v2-3-3`, `feat/v2-juge`, serveur revu a0b60de) : fusionner `origin/master` (qui contient alors la 3.2), puis **seconde passe écran** par dev-story (panneau « Critères de notation », note /100 et raison, avertissement « note peu fiable », « un seul juge », badge et sélecteur de juge ; événements `judge` et `judge_score` décrits dans `story-3-3.md`), second avis, revue, contrôles, PR.
5. **4.2** (`v2-4-2`, `feat/v2-rag-ecran`, depuis la 4.1 revue) : voir sa ligne du tableau.

**Ensuite** : 3.4 (après 3.2 et 3.3), 3.5, 3.6 (+ préversion 2.0.0a3, notes et recette) ; 4.3, 4.4, puis 4.5 à 4.8, et 4.9 (+ 2.0.0a4, fin du MVP). Au plus 3 stories en développement à la fois.

- Worktrees : `C:\Users\Utilisateur\Documents\GitHub\wavelocalai-wt\<clé>`, chacun avec son `.venv` ; supprimer ceux des stories fusionnées (`git worktree remove`). Spec de story : `_bmad-output/implementation-artifacts/story-<n>-<m>.md` (dans le worktree tant que la story n'est pas fusionnée).

## Périmètre étendu (confirmé par Anaël le 2026-10-18 vers 23 h 20)

- Après le MVP (Epics 3 et 4 jusqu'à la 4.9, dans l'ordre prévu) : Epics 5 à 8, stories 5.1 à 5.8, 6.1 à 6.6, 7.1 à 7.4, 8.1 à 8.3 (en backlog dans le statut du sprint). **8.4 (« La v2 remplace la v1 ») exclue** : revient à Anaël.
- **Garde-fou** : aucune story de l'Epic 5 ou suivante avant la fusion sur master de la PR `bmad-correct-course` (43 décisions d'UX de la maquette, PR #58). Vérifier : `gh pr list --state merged --search "correct-course"` ou un commit qui modifie `epics.md` avec les décisions de la maquette. Une fois fusionnée : fusionner `origin/master`, appliquer ses ajustements aux stories en cours (3.1, 3.2, 3.3, 4.1, 4.2 citées) avant leur PR, ajouter les stories de suite qu'elle liste (Epics 1 et 2).
- Préversions 2.0.0a5 (5.8), a6 (6.6), a7 (7.4) : version dans le manifeste, tags et releases en attente d'Anaël.
- 6.3 (email) : SMTP factice seulement, aucun envoi réel. 5.3 et 5.5 (installation de modèle, reranker) : téléchargements simulés ; un vrai téléchargement est une ressource à activer par Anaël (le prévenir, avancer sur le reste).
- Écrans des Epics 5 à 7 : référence visuelle `docs/maquette-v2/` (une fois la PR #58 fusionnée) ; les documents de contrat priment sur la maquette.
- **Second message de `wavelocalai-d7` (2026-10-19 vers 0 h 30, annoncé par Anaël), appliqué** : PR #58 (maquette, f4e48b8) et #61 (correct course, 72137a4) fusionnées ; **garde-fou de l'Epic 5 levé**. Consignes détaillées : `_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md` §7 ((a) ajustements des stories en cours, (b) stories 1.12 et 2.7, (c) changements du backlog, (d) 18 écarts ouverts).
- **Ordre confirmé** : finir le MVP (Epics 3 et 4 jusqu'à la 4.9, avec 1.12 et 2.7 fusionnées avant 3.6 ; 1.12 aussi avant 4.9), puis 5.1 à 5.8, 6.1 à 6.6, 7.1 à 7.4, 8.1 à 8.3 dans l'ordre ; au plus 3 stories en développement à la fois. 1.12 et 2.7 ne changent pas la version.
- **Ajustements avant PR** (§7(a)) : 3.2 (D-15 4 colonnes repliées à 1 440 px, D-16 résumé pendant l'exécution, légendes « Choisissez 4 modèles au plus » et « Saisissez une question », D-11 sans modèle local) ; 3.3 (« Choisissez un juge ») ; 4.1 (consigner le champ échec/doublon d'`ingest_progress` dans `contrat-api.md`) ; 4.2 (un seul « Annuler l'import », D-25 ; documents `failed` dans le tableau et dans `GET /api/rag/documents` avec leur raison, hors compte, D-26).
- **Specs des stories du backlog** : rédigées depuis `epics.md` de master à jour (stories ajustées listées au §7(c)).
- **18 écarts du §7(d)** : ne pas les trancher ; prendre la variante la plus conservatrice (critère actuel de la story), la signaler dans la PR de la story et au journal.
- **Incident** : le commit b7703cd (sur master, par un sous-agent de l'autre session) contient les 3 fichiers d'état d'alors ; `run-autonome.md` est suivi sur master. À chaque synchronisation, la version locale l'emporte (vérifié le 2026-10-19 : aucune ligne du statut perdue). Annulation éventuelle : décision d'Anaël.
- Anaël (2026-10-18, 23 h 25) : un second message de la session `wavelocalai-d7` sur le périmètre arrivera dans la nuit, quand ses évolutions fonctionnelles pour la suite des epics seront finies ; le prendre en compte (stories ajoutées ou ajustées), en gardant les arrêts ci-dessus (8.4, envois et téléchargements réels, tags et releases).

## Parallélisation (autorisée par Anaël le 2026-10-18)

Vagues prévues selon les dépendances, fusion dans l'ordre du sprint (fusionner `master` dans les branches suivantes, re-verrouiller `uv.lock` en cas de conflit) :
- après 1.2 : 1.3 (store, hub), 1.5 (registre), 1.8 (coquille front ; E2E sur Edge) ;
- puis 1.4 (SSE, après 1.3) et 1.6 (défauts, après 1.5) ; 1.7 après 1.4 ; 1.9, 1.10, 1.11 après 1.7 et 1.8.

## Stories

| Story | Branche | PR | Statut | Notes |
|---|---|---|---|---|
| 2.7 | feat/v2-chat-creativite (depuis master 72137a4, puis bb272a5) | #63 | fusionnée ; dev 6904013 ; master fusionné (8f5efd7 : migration renumérotée `0005_model_parameters.sql`) ; revue f424965 (pas du curseur 0,05) ; rapide OK, 838 v2, 192 E2E, 8 integration, 1286 v1 | écarts : libellés « Télécharger (JSON) » gardés, ligne d'aide du curseur reprise de la maquette, boutons désactivés sans conversation ; reports pour Anaël : `default_temperature` absent du catalogue (`build_catalog.py`), icône `download` absente du sprite |
| 4.4 | feat/v2-rag-question (depuis master bb272a5) | #64 | fusionnée ; dev 4191eef ; revue eea4abc (recherche filtrée sur les documents prêts, raison « non lancée », mots vides repliés) ; rapide OK, 862 v2, 172 E2E, 8 integration (`qwen2.5:1.5b`, `nomic-embed-text`), 1286 v1 | écarts à ratifier : `sources {strategy, sources}`, `retrieval_step {strategy, step, duration_s}`, `metrics.retrieval_s`, codes `rag_base_empty` (409) et `chunk_not_found` (404), réglages `rag.top_k` et `rag.relevance_*` ; §7(d) n° 12 en variante conservatrice (pas d'avertissement cloud serveur, pas d'export, consigne `[n]` dans `SYSTEM_PROMPT`, `retrieval_step` en fin d'étape) ; reports : message RAG sans métriques dans `GET /api/conversations/{id}` (4.5), positions de `passage` en points de code (emoji), `nomic-embed-text` sans préfixes de tâche, repli numpy perdu au redémarrage, `retrieval_s` inclut l'attente de la place, historique non repris |
| 1.12 | feat/v2-coquille-maquette (depuis master bb272a5) | #66 | fusionnée ; dev 5382c7d ; revue 1cdca6a (empreintes des 19 symboles du sprite, CSS mort retiré) ; rapide OK, 821 v2, 196 E2E, 7 integration, 1286 v1 | §7(d) n° 3 (icône `swords`) et n° 9 (carte Mode sans compteur) en variante actuelle ; ressource à fournir par Anaël : sprite Material Symbols Rounded officiel (18 symboles de la maquette + build, psychology, output, pending_actions, leaderboard) ; reports : flash de thème hors Chromium (`blocking="render"`), noms longs « Arène des modèles » et « Installation et choix par usage » à confirmer |
| 4.3 | feat/v2-rag-gestion (depuis master fff8faa, puis 2567e44 et b90056e) | — | dev 974925c ; revue 0829e07 (`null` des réglages, embedding contrôlé, refus `vector_tables_unreachable` sans module vec0, délai client 300 s) ; rapide OK, 1017 v2, 298 E2E, 11 integration, 1286 v1 | écarts : quatre codes (`embedding_change_needs_clear`, `base_count_stale`, `base_in_use`, `vector_index_lost`) + `vector_tables_unreachable`, `GET /api/rag/settings` enrichi ; §7(d) n° 13 en variante contrat (409 affiché) ; pour Anaël : interprétation de « document visé » (refus si `indexing` ou run `rag` actif), import non refusé sans sqlite-vec ; résidu vectoriel : aucun avec sqlite-vec 0.1.9 ; reports : bornes d'API plus larges que la maquette, purge bloquée par un lecteur sans signal à l'écran |
| 1.1 | feat/v2-squelette | #39 | fusionnée (428c7e6) | revue : 1 high corrigé (`models/` ignoré par `.gitignore`) ; reports : angles morts du test AST (`importlib`, `__import__`), starlette 1.7.0 dans `constraints.txt` contre 1.8.0 dans `uv.lock` |
| 1.2 | feat/v2-serveur | #40 | fusionnée (4e33370) ; 1 correction CI (sonde Ollama : client httpx construit hors boucle) | revue : 2 medium corrigés (sonde Ollama lente annoncée arrêtée ; encodage cp1252 du test de lancement réel) ; reports : arrêt propre → `cancelled` (attend le hub), délais `lane_timeout_s`/`approval_expiry_s` provisoires, Origin des WebSocket, `Mount` hors test de budget |
| 1.3 | feat/v2-hub | #41 | fusionnée (e9af784) ; revue : high course stop/flush et medium feuille pendant annulation corrigés | reports : réhydratation `sources` (attend `chunks`), `409 run_busy` (story des POST runs), SSE et routes de runs (1.4), effacement AD-13 |
| 1.4 | feat/v2-flux-sse (depuis d86d06a) | #42 | fusionnée ; revue : `ModelRef` aligné sur 1.5, medium `_error_envelope` corrigé ; 227 tests v2 | 219 tests v2 ; a créé `models/port.py` + `fake.py` en doublon de `port.py` de 1.5 → réconcilier à la fusion ; hub : `publish_token`, `watch`, `active_root`, `run_busy` ajoutés ; reports : `token` non groupé ?, CO₂ des runs de test `unmeasurable` |
| 1.7 | feat/v2-flux-systeme (depuis eb81d58) | — | revue faite (0c90516 : arrêt réel avec flux ouverts corrigé + test sous-processus ; feuille en erreur comptée non mesurable ; `contrat-api.md` précise que le client relit `GET /api/carbon/session` à chaque connexion) ; `feat/v2-defauts` fusionné (6eccc25, 374 tests v2, 1286 v1) ; PR #45 fusionnée | reports : `carbon_updated` publié par personne avant 2.3, reset de session avec Sobriété, version Ollama de la fiche `null` avant la 1re sonde, GPU hors flux 2 s |
| 1.9 | feat/v2-barre-haute | — | revue faite (dc568bb : 3 medium corrigés, dont chien de garde du flux SSE et regex de test cassée ; écart AD-15 gardé, à arbitrer) ; `feat/v2-coquille` fusionné ; 424 tests v2, 74 E2E, 1286 v1 ; PR #47 fusionnée | reports : « Réessayer » ne force pas la sonde, pas de pause du flux sur `visibilitychange` (Accueil 1.11) ; sonde du flux système à cache 1 s |
| 1.10 | feat/v2-selecteur (1.6 + 1.8 + 1.9 fusionnées, 9151f62) | #50 | fusionnée ; revue : 3 medium corrigés ; 428 tests v2, 101 E2E, 1286 v1 | reports : Échap des panneaux de la barre haute sans `preventDefault`, `wl-error` affiche des accents graves Markdown, composants pas encore montés dans un écran |
| 1.11 | feat/v2-accueil (depuis 1.9 edb870e) | — | second avis fait (1 medium : conflit certain `core/system.js` avec 1.9 revue ; lows : « en direct » affiché pendant la pause, focus perdu sur Réessayer). PR #51 fusionnée (avec version 2.0.0a1, Epic 1 terminée) ; revue : conflit `core/system.js` résolu, relecture de santé arrêtée pendant la pause ; 429 tests v2, 123 E2E, 1286 v1 | reports : « Ollama sans modèle » attend `GET /api/models` (désormais sur master) ; CO₂ en ligne de détail de la carte Mode ; conflits `core/*.js` probables avec 1.9 revue et 1.10 |
| 2.2 | feat/v2-ecran-chat (2.1 dc1c4e1 + 1.10 fusionnées) | — | revue faite (beb3be6 : 2 medium corrigés, annonce de fin unique et position de défilement au retour) ; `origin/master` fusionné (conflits `index.html`/`test_shell_static.py` : garder `screens.css` et `chat.css`) ; 480 tests v2, 150 E2E (1 test de l'Accueil réaligné : l'Arène est disponible), 1286 v1 ; PR #53 fusionnée ; A19 intégré | reports : « Télécharger » attend les routes de conversation (2.6), débit provisoire à 1 token pour 4 caractères, tableaux Markdown non rendus, pas de reprise après rechargement complet |
| 2.3 | feat/v2-co2-local | #54 | fusionnée (a7ab77b) ; revue : préchauffage CodeCarbon (1re réponse 4,9 s → 0,52 s), vrai tracker testé ; pied « CO₂ 1,8 mg » | reports pour Anaël : réponse pendant le préchauffage attend (3,8 à 14,5 s), `energy_wh` dans `metrics` à ratifier |
| 3.3 | feat/v2-juge (3.1 + master, puis 3.2, 3.2 ajustée et 4.4) | #67 | fusionnée ; serveur revu a0b60de ; écran 2a8f225 revu ef39f97 ; fusion de la 3.2 ajustée d5f6ff0 (`arena-form.js`, `arena-summary.js`), ajustement « Choisissez un juge » 18e4824 revu a9215b3 ; master (4.4) c79c074 ; rapide OK, 915 v2, 229 E2E, 9 integration, 1286 v1 | ajouts au contrat à ratifier en 3.6 : événement `judge`, clé `judge` de `judge_score`, `invalid_output` ; §7(d) n° 5 (« un seul juge » avec chaque note) en variante actuelle ; reports : Mistral `strict`, Groq `json_schema` en flux à vérifier en réel, réponse de 12 000 caractères au-delà du `num_ctx` d'un petit juge, rattachement au run après abandon du flux, course au retrait du cloud pour les modèles de l'Arène, critères non gardés entre deux visites |
| 4.1 | feat/v2-rag-index (depuis master a7ab77b, puis master fusionné jusqu'à 5ab78e4) | #60 | fusionnée (correctif CI 2d4b0b6 : course du test d'annulation, index numpy si sqlite-vec absent ; ajustement correct course 6d17a04) ; revue faite (f3536cb) ; master fusionné (6384545, f65e592 : conflits `errors.py`, `store/db.py`, `web/app.py`), black de `errors.py` (def67ea) ; rapide OK, 810 tests v2, 172 E2E, 7 integration, 1286 v1 | écarts : `ingest_progress.file`, événement `ingest_file_done` (à ratifier dans `contrat-api.md`), annulation supprime le document en cours ; reports : code d'erreur « sqlite-vec absent », résidu WAL (4.4), limite 413, pas d'`input_tokens` pour l'embedding |
| 3.2 | feat/v2-arene-ecran (3.1 + master 2eed892, puis 3.1 à jour et master 5ab78e4) | #62 | fusionnée ; revue faite (d104fc4) ; ajustements du correct course (142b9c7 : D-15, D-16, légendes, D-11) revus (f983f4b : focus, D-11 avec Ollama arrêté) ; 3.1 fusionnée (16774d8 : conflits `routes_test.py`, `wl-chat-thread.js`, `api.js`), master (74286f2) ; rapide OK, 680 tests v2, 206 E2E, 6 integration, 1286 v1 | reports : battement de cœur serveur des flux de run (flux figé non détecté, aussi dans le Chat : `core/sse.js` + `routes_runs.py`), rattachement à un run qui tourne encore après abandon du flux (comme la reconnexion de la 4.2), 8 icônes Material Icons au lieu de Symbols Rounded (aucun jeu hors ligne), question préremplie et légendes acceptées |
| 4.2 | feat/v2-rag-ecran (depuis 4.1 revue f3536cb, puis 4.1 à jour et master bb272a5) | #65 | fusionnée ; dev 8b73a5b ; revue 5a77b2a ; ajustements du correct course (214c206 : un seul « Annuler l'import » D-25, échecs dans le tableau D-26) revus (7e5a119 : focus clavier, run rejoint après réponse d'envoi perdue) ; rapide OK, 832 v2, 202 E2E, 7 integration, 1286 v1 | écarts : route de test `POST /api/test/embedder` ; §7(d) n° 13 en variante actuelle (boutons désactivés pendant un import) ; reports : plafonds vérifiés après lecture du multipart (limite `Content-Length`), progression d'envoi par répartition des octets, refus « sqlite-vec absent » à trancher en 4.3, E2E lent (~3 min) |
| 2.6 | feat/v2-conversations (2.2 + master, puis 2.5 et master a5585c3) | #57 | fusionnée (8963e14) ; revue : bd1ff0e ; fusion 2.5 (conflits `errors.py` garder les deux, 11dcfc7), version 2.0.0a2, test E2E de reprise stabilisé (4a2f8e1) ; 649 tests v2, 172 E2E, 5 integration, 1286 v1 | report pour Anaël : copies `.db.bak-N` gardent le texte effacé |
| 3.1 | feat/v2-arene-serveur (2.4 revue + 2.3 revue fusionnées, puis master 8963e14) | #59 | fusionnée (5ab78e4) ; revue faite (125ba68) ; `origin/master` fusionné (784ff71 : conflits `streaming.py` et `web/app.py`, lanes cloud estimées par ecologits via `cloud_estimator` partagé) ; rapide OK, 668 tests v2, 172 E2E (topbar relancé seul : 26/26), 6 integration, 1286 v1 | écarts au contrat : événement `question {text, criteria}`, `POST /api/arena/runs` sans conversation, `lane_status.error` ; effacement d'une Arène (AD-13) reporté à 3.6 |
| 2.5 | feat/v2-co2-cloud (depuis 2.4 revue a43ff7d) | #56 | fusionnée (a5585c3) ; revue : 6bc81e0 (avertissements ecologits traduits dans `co2.reason`) ; 2.4 puis `origin/master` fusionnés (conflits 2.3 résolus par l'orchestrateur, b8604bc) ; pied « (estimé) » + réserve EcoLogits ; rapide OK, 626 tests v2, 157 E2E, 5 integration, 1286 v1 | reports : `llama-3.3-70b-versatile` non mesurable (absent d'ecologits), raison `NOT_MEASURED` partagée avec 2.3 ; décision : `electricity_mix_zone=None` (centre de données du fournisseur) |
| 2.4 | feat/v2-chat-cloud (2.1 + 1.10, puis 2.3 fusionnée) | #55 | fusionnée (33adc49) ; revue : a43ff7d (erreur de flux OpenAI/Groq en `cloud_error`, juge cloud sur les identifiants vérifiés, `constraints.txt` mistralai 3.2.0) ; `origin/master` fusionné ; rapide OK, 591 tests v2, 5 integration, 1286 v1, E2E verts (topbar relancé seul : 25/25) | reports : outils/`response_schema`/`think` non envoyés, `temperature` omise pour `gpt-5/6/o*`, comportement réel des 4 API à vérifier avec une vraie clé |
| 2.1 | feat/v2-chat-ollama (depuis master 89e20e1) | — | revue faite (dd12ee8 : prefill en champ optionnel, `co2` des runs annulés via `declare_leaf`) ; `feat/v2-accueil` fusionné ; integration verte sur `qwen2.5:1.5b` (installé avec l'accord d'Anaël) ; 472 tests v2, 1286 v1 ; PR #52 fusionnée | integration non jouée : `qwen2.5:1.5b` absent (notifié) ; code `generation_interrupted` (AD-5) au lieu de `interrupted` d'epics.md ; CO₂ `unmeasurable` jusqu'à 2.3 ; `hub.py` efface le partiel sur `retry` ; `registry.extra_refs` |
| 1.6 | feat/v2-defauts | #44 | fusionnée ; revue : 4 medium corrigés ; reprise : `feat/v2-registre` fusionné, `0003` en dates ISO, `SqlitePreferenceStore` branché ; 334 tests v2 | 216 tests v2, 3 integration verts une fois ; reports : `PreferenceStore` en mémoire à brancher sur le store (migration `0003_preferences.sql` présente), pas de route d'écriture de défaut (UI) |
| 1.5 | feat/v2-registre | #43 | fusionnée ; revue : medium dates ISO corrigé ; `master` fusionné (`port.py` de 1.4) ; 278 tests v2, 1286 v1 ; reports : identifiants cloud à vérifier (2.4/2.5), modèles supprimés qui réapparaissent à froid | reports : `SqliteFactsStore` et médiane `tps` depuis `runs` à brancher sur le store de 1.3 ; migration `0002_model_facts.sql` à renuméroter après celle du hub ; « tient en mémoire » = RAM libre psutil seulement ; conflits attendus `web/app.py` (lifespan) et `errors.py` |
| 1.8 | feat/v2-coquille | — | revue faite (39bfed1 : 1 medium corrigé, hash hors route au chargement) ; `feat/v2-flux-systeme` fusionné ; 413 tests v2, 25 E2E, 1286 v1 ; PR #46 fusionnée | 162 tests v2, 24 E2E sur Edge ; reports : pastilles barre haute (1.9), blanc sur primary-dark 4,26:1, CSP sans `blob:` (exports), pyyaml non déclaré |

## Décisions prises seul

- `_bmad-output/party-mode/` non versionné (mémoire de session, pas un livrable).
- Story 1.1 : pydantic reste en 2.12.x (contrainte `pydantic>=2.9.0`) au lieu de 2.14.1 (spine §Stack). Motif : crewai 1.15.28 de la v1 exige `pydantic<2.13` ; avec 2.14.1, uv rétrograde crewai à 1.6.1 et 17 tests v1 échouent. NFR14 et AD-2 (v1 intacte) priment. À ratifier par Anaël (mise à jour de la spine §Stack via `bmad-spec`, ou relèvement à la bascule).
- Story 1.6 : les usages `agent` et `rag` n'ont pas de règle en v1 ni dans les critères ; règle provisoire posée sur le registre (seuil de 3 milliards de paramètres actifs, repli sur le défaut `chat` avec sa raison), à confirmer avec les mesures du banc.
- `models/port.py` : `ModelRef` de la story 1.5 retenu (AD-9 : `origin` avec `unknown`, `kind` en `Literal`) ; la 1.4 s'y aligne à l'identique et y ajoute les types du port `ChatModel` d'AD-8.
- Story 2.1 : débit de prefill exigé par le critère alors que `ChatResult` est figé par AD-8 → champ optionnel ajouté en fin de `ChatResult` (écart additif à AD-8, à ratifier). Code de coupure `generation_interrupted` (AD-5 interdit un code qui reprend un statut) au lieu de `interrupted` d'epics.md.
- Story 2.5 : zone de mix électrique du CO₂ cloud = celle du centre de données du fournisseur (`electricity_mix_zone=None`, défaut d'ecologits), et non le pays du poste (`Settings.carbon.country_iso`), qui décrit la machine locale. À confirmer par Anaël si une zone réglable est voulue.
- E2E : Chromium de Playwright absent, mais Edge installé fonctionne avec Playwright (vérifié, Edge 155). Le conftest E2E de la v2 accepte `WAVELOCALAI_E2E_CHROMIUM` (comme la v1) ; en local : `$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`. Aucun téléchargement.
- Ollama : utiliser `http://127.0.0.1:11434` (`localhost` échoue en IPv6 sur ce poste).

- `tests/app/test_nothing_lost.py::test_agent_*` (v1) : échec intermittent vu une fois en revue de 1.10, vert en relance sur la branche ; 4 échecs dans le dépôt principal dont le `.venv` n'est plus synchronisé depuis la 1.1 (non modifié par le run). Pour Anaël : `uv sync` dans le dépôt principal remettra le `.venv` au verrou actuel (Python 3.11+, deps v2).

## Décisions d'Anaël (2026-10-18, 23 h 15)

- Ollama laissé au run pour toute la nuit (tests integration gardés dans `checks.sh`).

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

### 2.0.0a2 (fin de l'Epic 2) — en attente d'Anaël

Version `2.0.0a2` posée dans `pyproject.toml`, `uv.lock` et `CITATION.cff` par la PR de la story 2.6. **Tag `v2.0.0-alpha.2` et release GitHub non créés** : à faire par Anaël après la recette.

Commandes (après recette) :
`git tag -a v2.0.0-alpha.2 -m "wavelocalai 2.0.0a2 : chat local et cloud"` sur le merge commit de la PR 2.6, `git push origin v2.0.0-alpha.2`, puis `gh release create v2.0.0-alpha.2 --prerelease --title "2.0.0a2 : chat local et cloud" --notes-file <notes ci-dessous>`.

Brouillon des notes :

> Deuxième préversion de la v2 (`wavelocalai-v2`, port 8502 ; la v1 reste sur 8501). Elle apporte le chat libre, local et cloud, avec son empreinte carbone.
>
> - Chat en flux avec un modèle Ollama : réponse et raisonnement en direct, débit, premier token, chargement et durée dans le pied de réponse ; Arrêter (Échap) garde le texte partiel ; une génération coupée est relancée une fois ; quitter l'écran puis revenir reprend le flux sans perte ni doublon.
> - Chat avec un modèle cloud (OpenAI, Groq, Anthropic, Mistral), seulement si « Autoriser le cloud » est activé et la clé présente dans `.env` ; erreurs de clé, de réseau ou de quota expliquées avec la marche à suivre.
> - CO₂ de chaque réponse : mesuré par CodeCarbon pour un modèle local (préchauffé au démarrage), estimé par EcoLogits pour un modèle cloud (« (estimé) », réserve en aide), « non mesurable » avec sa raison sinon, jamais 0 ; le CO₂ de session de la barre haute suit chaque réponse.
> - Conversations : rouvertes telles qu'affichées, exportées en JSON ou Markdown (sans clé d'API), effacées pour de bon (texte absent de la base et de son journal ; le CO₂ de session ne baisse pas).
>
> Pas encore là : Arène, base documentaire (préversions suivantes).

Recette humaine à jouer (environ 15 min) :
1. `uv sync` puis `uv run wavelocalai-v2` ; ouvrir `http://127.0.0.1:8502`, aller dans Chat.
2. Chat local (`qwen2.5:1.5b` ou un autre modèle Ollama) : 3 échanges ; la réponse arrive en flux, le pied affiche débit, durée et « CO₂ … mg » ; le CO₂ de session de la barre haute augmente. Arrêter une réponse longue avec Échap : le partiel reste.
3. Quitter l'écran pendant une réponse, revenir : le flux reprend sans doublon.
4. Chat cloud : activer « Autoriser le cloud », choisir un modèle d'un fournisseur dont la clé est dans `.env` ; la réponse arrive, le pied affiche « CO₂ … (estimé) » et l'aide cite EcoLogits. Sans clé : message « La clé d'API de … n'est pas configurée » avec la marche à suivre.
5. Recharger la page : la conversation revient telle qu'affichée ; Télécharger en JSON et en Markdown (pas de clé d'API dedans).
6. Effacer la conversation : elle disparaît ; le CO₂ de session ne baisse pas. Pendant une réponse en cours, l'effacement est refusé avec son explication.
7. Points à trancher en même temps : réponse pendant le préchauffage de CodeCarbon (3,8 à 14,5 s d'attente), `energy_wh` dans `metrics`, copies `.db.bak-N` qui gardent le texte effacé, zone de mix électrique du CO₂ cloud.
