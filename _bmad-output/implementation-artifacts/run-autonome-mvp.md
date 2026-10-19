# Run autonome du MVP v2 (Epics 1 à 4)

Démarré le 2026-10-18. Orchestrateur : session principale (Opus 5.5). Contrat : SPEC.md + compagnons, ARCHITECTURE-SPINE.md (AD-1 à AD-23, prioritaires), epics.md, AGENTS.md.

## Reprise après /clear

1. Lire ce fichier, puis `sprint-status.yaml`.
2. Reprendre la story « en cours » à l'étape indiquée.
3. Boucle par story : dev-story (Sonnet, effort high, worktree, branche `feat/v2-<clé>`) → second-avis (Haiku) → reviewer (Opus, liste du second avis) → contrôles locaux (contrôle rapide, `pytest tests/v2`, `python -m pytest tests/unit tests/app`, `-m e2e` si front, integration si la story en a) → PR → merge commit quand CI verte.
4. Journal daté : après chaque étape, ajouter une ligne `- AAAA-MM-JJ HH:MM · story · étape · résultat · commit` à la section « Journal » de `run-autonome.md` (lu par `/agent-cost-kit:avancement-run`). **Depuis le 2026-10-19 (décision d'Anaël), les trois fichiers d'état (`sprint-status.yaml`, ce fichier, `run-autonome.md`) ne partent plus avec les PR de story** : ils restent modifiés dans le dépôt principal et partent dans une PR `chore/etat-run-*` ouverte par `_outils/etat_pr.sh "<libellé>"` (à chaque fin d'epic et toutes les 3 à 4 fusions), fusionnée par merge commit quand la CI est verte. `finalize.sh` ramène les fichiers d'état d'une branche à ceux de `origin/master` avant le push. Après toute fusion : dans le dépôt principal, sauvegarder ces trois fichiers, `git checkout -- <ces fichiers>`, `git pull`, puis les restaurer (la version locale l'emporte).
5. Avant la PR d'une story : la CI d'une PR teste déjà la fusion avec master ; ne fusionner `origin/master` dans la branche que s'il y a conflit (GitHub ne lance pas la CI d'une PR en conflit) ou si une story fusionnée touche les mêmes fichiers. `rerere` est activé dans le dépôt (résolutions rejouées). Vagues planifiées par fichiers touchés : deux stories qui modifient le même écran passent l'une après l'autre.
6. Les fusions de branches (`git merge`) sont faites par l'orchestrateur : le classifieur de permissions les refuse aux sous-agents. Conflit sémantique : laisser la fusion en cours et confier la résolution au reviewer (« étape 1 obligatoire »).
7. Outils de l'orchestrateur, dans `C:\Users\Utilisateur\Documents\GitHub\wavelocalai-wt\_outils\` (lancer avec `.venv\Scripts\python` du dépôt principal ; `finalize.ps1 <worktree> <branche> <préfixe de clé> <libellé>`) : `set_status.py` (statut du sprint), `set_row.py` (ligne du tableau ci-dessous), `finalize.sh` (statut `done` dans le dépôt principal, fichiers d'état de la branche ramenés à ceux de master, push), `etat_pr.sh` (PR des fichiers d'état), `keep_both.py` / `ours_then_theirs.py` (conflits « garder les deux »), `bump_version.py`.
8. E2E : `$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`. Tests : `$env:PYTHONUTF8 = "1"`. Ollama : `http://127.0.0.1:11434`, `qwen2.5:1.5b` installé.
9. **Depuis le 2026-10-19 vers 8 h (accord d'Anaël, amélioration continue d'agent-cost-kit n° 1, 3, 4, 10, 16)** : la CI de branche (3 OS) joue `tests/v2` et la v1. En local, `checks.sh <wt>` lance le contrôle rapide, les **E2E ciblés** (`e2e_cibles.sh` : écrans touchés, composants et coquille si `core/`, `components/` ou CSS changent, fumée Accueil + coquille) et l'integration, et relance une fois seuls les tests en échec ; `checks.sh <wt> complet` pour tout. **Suite E2E complète sur master** après chaque lot de 3 à 4 fusions : `e2e_master.sh` (worktree `v2-master`) ; un échec y ouvre un correctif avant la fusion suivante. Un seul contrôle local à la fois ; au plus 5 agents actifs (dev + revue). Chaque prompt de dev et de revue cite la section « Contrats partagés en cours ». Second avis : comparer à `git merge-base HEAD origin/master` et signaler « base en retard de N fusions » ; le reviewer part d'une branche à jour de master (l'orchestrateur fusionne d'abord). Une décision qui revient à Anaël ne bloque que les stories qui en dépendent. Après la 5.0 : pile de branches revues fusionnée par lots (n° 3).

## État courant (2026-10-19 vers 22 h 15, avant /clear pour l'Epic 8)

- **Fusionnées depuis 17 h 15** : #92, #93 (6.2), #90 (7.1), #97, #94 (5.2), #89 (5.3), #98 (7.2), #101, #100 (CI allégée), #99 (7.3), #102 (5.4), #95 (6.3), #96 (6.5), #103 (5.5), #104 (7.4), #106, #108 (6.4 + 6.6, du premier coup). Fermées : #105, #107 (remplacées par les PR par pile).
- **PR ouvertes, dans cet ordre** (une à la fois, `_outils/queue2.sh <pr>`) : **#109** (correctif du budget de la coquille, premier point de la 8.1, revu, e87fe34) puis **#110** (5.6 + 5.8) : après la fusion de #109, fusionner `origin/master` dans `feat/v2-usages` (worktree `v2-5-8`), pousser, relancer la file. Une PR en conflit : `_outils/contrat_both.sh <worktree>` pour le contrat ; tests de la coquille : 12 écrans `available`, plus aucune route `planned` (versions de `feat/v2-dette` à reprendre).
- **Préversions** (manifeste seulement, sans tag ni release, `_outils/bump_version.py`) : 2.0.0a5, a6, a7 dans une seule PR `chore/` **après la fusion de #110** (5.8 = a5, 6.6 = a6 déjà fusionnée, 7.4 = a7 déjà fusionnée), journal : une ligne `version` par préversion.
- **Essai du levier 3** (PR par pile, décision d'Anaël) : #108 fusionnée du premier coup (1 run au lieu de 2 à 4) ; #110 à suivre ; bilan dans les apprentissages de fin de projet.
- **Epic 8** : branche `feat/v2-dette` (worktree `v2-8-1`, `.venv` prêt) = master + toutes les stories revues + commit du budget 1d70820. Avant de reprendre la 8.1 : fusionner `origin/master` (après #109 et #110). Le test E2E `test_chat.py::test_the_arena_module_is_available_and_its_other_tabs_are_disabled_with_their_reason` est à réaligner (fait dans #110 : reprendre). Spec : `story-8-1.md` (budget fait ; le reste en `deferred`). Puis 8.2, 8.3.
- **Ajouts à la 8.1** (revues du soir) : `onSmallerModel` non retiré dans Arène, Discussion, Base (7.3) ; `agents-solo.js` rejoint une mission d'équipe active sans vérifier `params.mode` (6.6) ; message `timeout` côté serveur avec le délai (7.4, n° 1) ; verrou par modèle entre contrôle d'usage et suppression (5.4) ; tests instables (`test_topbar` serveur relancé, `test_shell` 300 ms) ; icône Références provisoire `help` en attendant le sprite officiel (5.8). **Moins de conflits entre stories parallèles (décision d'Anaël, 21 h 30)** : (a) contrat découpé, une sous-section par story dans son propre fichier (`_bmad-output/specs/spec-wavelocalai-v2/contrat/<story>.md`, indexé par `contrat-api.md`) au lieu d'ajouts en fin de `contrat-api.md` ; (b) tests de la coquille (`test_shell_static.py`, `test_shell.py`, `test_home.py`, statiques des écrans) qui lisent le nombre d'écrans `available` et les routes `planned` dans le registre (`core/routes/*.js`) au lieu de comptes écrits en dur.
- **Journal** (lu par `/agent-cost-kit:avancement-run` 0.7.1) : après une CI rouge relancée ou corrigée, écrire une ligne `CI · verte` quand elle passe ; `PR · #n ouverte` à l'ouverture ; une story ne passe à `in-progress` qu'au lancement de son agent de dev (la 8.1 est remise à `backlog` jusque-là).
- **Ollama** : gardé jusqu'à la fin (décision d'Anaël, 19 h 40). **Prévenir Anaël dès que le run n'en a plus besoin** (après les contrôles de la 8.3) : il lancera slm-quality-bench, puis la 5.7.
- **5.7** : reportée après le run (décision d'Anaël, 19 h 30 ; version sans les chiffres du banc acceptée).
- **Pour Anaël** (en plus de l'état précédent) : réponse de l'agent en un bloc (6.4, à confirmer) ; textes des issues de validation d'email (6.4) ; licence des modèles (5.6 : migration ou catalogue) ; jointure d'empreinte et définition du PC pro à la première synchro réelle (5.6) ; recette réelle du reranker ~1,1 Go (5.5) et du `DELETE /api/delete` (5.4) ; icône `help` provisoire des Références (5.8) ; décisions prises seul : budget de la coquille au deuxième meilleur de 5 (#97), EHLO fixe en boucle locale (6.3, CI macOS).

## État précédent (2026-10-19 vers 17 h 15, pause pour /clear demandée par Anaël)

- **Fusionnées** : report au contrat (#85), 5.0 (#86, E2E en CI), 5.1 (#88), correctif verdict/budget (#91), 6.1 (#87).
- **PR ouvertes, à fusionner par `_outils/merge_queue.sh` quand la CI est verte** (vérifier d'abord `gh pr view <n> --json state,mergeable`) : #92 (état), #90 (7.1, conflits avec la 6.1 résolus 9755e84), #89 (5.3, conflits avec la 5.1 résolus 3bf7ff2), #93 (6.2, 8339d2c). Après chaque fusion, une PR suivante peut passer en conflit : fusionner `origin/master` dans sa branche (conflits sémantiques → agent Sonnet), pousser, relancer la file.
- **Prêtes, PR à ouvrir** : 7.2 (`v2-7-2`, 5da70b5, revue faite, contrôles verts) après la fusion de #90 : fusionner `origin/master`, `finalize.sh v2-7-2 feat/v2-jeu-fixe 7-2 7.2`, PR. 5.2 (`v2-5-2`, a3e424d, revue faite) : **relancer `checks.sh v2-5-2`** (coupés par la pause), puis fusionner `origin/master`, `finalize.sh v2-5-2 feat/v2-historique-carbone 5-2 5.2`, PR.
- **Revue Opus à lancer** (second avis fait, sa liste dans le journal de `run-autonome.md`) : 5.4 (`v2-5-4`, 744529e) après fusion de #89 dans la branche — 2 medium : course refresh/suppression dans `models/registry.py forget`, `keep_alive: 0` qui charge un modèle froid (lire `/api/ps` avant) ; 3 low. 6.3 (`v2-6-3`, 4b7702f) après fusion de master (6.1, 6.2) — 2 low : course délai/approbation dans `runs/hub.py request_approval`, `tool_timeout_s` < 30 s pendant l'envoi SMTP.
- **Stories suivantes** (au plus 3 en dev, 5 agents) : 6.5 ← 6.1 (serveur équipe), 7.3 ← 7.1 (écran Évaluation, route `GET /api/rag/eval/runs` livrée), 5.5 ← 5.4, 5.7 (mixte) ← 5.4, 6.4 ← 6.3 (écran Agent seul ; consignes des revues 6.1 et 6.3 dans leurs specs), puis 5.6, 5.8 (a5), 6.6 (a6), 7.4 (a7), 8.1 à 8.3.
- Méthode : spec de story rédigée par l'agent de dev depuis epics.md + décisions ; branche empilée sur la story précédente revue ; master fusionné dans la branche avant la revue et avant la PR ; prompts de dev : « poste partagé, tests ciblés seulement », worktree, jamais `git stash`.
- **Pour Anaël** : facteur voiture 142 g/km (5.1) ; `fits` sans VRAM ni cache KV (5.3) ; recette du vrai `pull` et du vrai `/api/delete` (5.3, 5.4) ; réponse de l'agent en un bloc (6.1, à confirmer en 6.4) ; relecture du jeu fixe `tests/v2/fixtures/eval/cases.json` (7.2, ~30 min) et choix d'un juge plus gros (le 1,5 B est non informatif) ; écart Q4 (pas de verdicts cloud) ; limite de 4 modèles aussi côté serveur (PR #85) ; éligibilité par usage (5.4) à employer ou non dans les sélecteurs des Epics 6 et 7.

## État précédent (2026-10-19, fin du run vers 12 h 30)

- **MVP terminé** (Epics 1 à 4) : 4.9 fusionnée (#79, de1288c). Fusionnées depuis 7 h 30 : 4.3 (#68), 4.8 (#70), tests instables (#72), 4.5 (#73), 3.5 (#74), 3.6 (#76), 4.6 (#77), 4.7 (#78), 4.9 (#79). Epics 5 à 8 reportés (décision d'Anaël) ; plan V15 à V25 dans `run-autonome.md`. Ollama rendu à Anaël vers 11 h 50.

## État précédent (2026-10-19 vers 7 h)

- **Fusionnées cette nuit** : 3.1 (#59), 4.1 (#60), 3.2 (#62), 2.7 (#63), 4.4 (#64), 4.2 (#65), 1.12 (#66), 3.3 (#67), 3.4 (#69). Epics 1 et 2 de nouveau terminées (1.12, 2.7).
- **En cours (pause demandée par Anaël vers 7 h 30 pour un /clear)** : PR #71 (état du run) fusionnée 644eb47. PR #68 (4.3) : CI rouge sur `test_read_budget` (minutage), job relancé ; fusionner si verte (`_outils/merge_queue.sh 68`). PR #70 (4.8) : CI rouge, car fusionnée avec la 3.4 `screens/arena.js` fait 606 lignes (> 600) : fusionner `origin/master` dans `feat/v2-garde-memoire` (worktree `v2-4-8`), sortir quelques lignes d'`arena.js` dans un module voisin, `checks.sh`, push. 4.5 : revue faite (e6ab8a7), reste master à fusionner (sans conflit attendu sur les fichiers d'état), `checks.sh`, `finalize.sh`, PR. 3.5 : dev fini (763a122, worktree `v2-3-5`, table de prix cloud vide à remplir par Anaël) ; reste second avis (Haiku), revue (Opus), `checks.sh`, `finalize.sh`, PR.
- **Ensuite** : 4.6 et 4.7 (après fusion de 4.5 : leur écran vit dans la Discussion) ; 3.6 (+ 2.0.0a3) après 3.5 ; 4.9 (+ 2.0.0a4) ; puis 5.0 (découpage du front), Epics 5 à 8 (vagues par fichiers à écrire dans `run-autonome.md`). Au plus 3 stories en développement.
- Outils : `_outils/finalize.sh <worktree> <branche> <préfixe> <libellé>`, `_outils/etat_pr.sh "<libellé>"`, `_outils/checks.sh <worktree>` (en arrière-plan, sortie dans le scratchpad), `keep_both.py <fichier> [séparateur]`.
- Pièges vus : **`git stash` est partagé entre worktrees** : aucun agent ne l'utilise (WIP commité ou copie) ; **`keep_both.py` sur un CSS peut couper une règle** (conflit au milieu d'un bloc) : vérifier les accolades (`test_every_stylesheet_has_balanced_braces`, ajouté par la 4.5) ou reconstruire « master + ajouts de la branche » ; « uvx black a échoué » sans détail = un fichier à reformater (`uvx --offline black@25.12.0 <fichier>`) ; `uv sync` dans un worktree après toute fusion qui change `uv.lock` ; un test E2E qui lance un run attend sa fin ; espaces insécables avant « : ; ! ? » dans `fr.json` ; sqlite-vec absent sur la CI macOS (tests `needs_vec`, valeurs qui suivent `store.vec_available`) ; tests instables sous charge (`test_read_budget` 300 ms, `test_topbar` serveur relancé, `test_arena` panneau au clavier « Response has been disposed », axe du pied de message en sombre) : relancer seul, à stabiliser en 8.1.
- Worktrees : `C:/Users/Utilisateur/Documents/GitHub/wavelocalai-wt/<clé>`, chacun avec son `.venv` ; supprimer ceux des stories fusionnées. Spec de story : `_bmad-output/implementation-artifacts/story-<n>-<m>.md`.

## Fin du run du 2026-10-19 (décision d'Anaël vers 8 h 40)

Le run s'arrête à la fin de l'Epic 4 (4.9 fusionnée, préversion 2.0.0a4) : Epics 5 à 8 reportés (budget de tokens). Ollama reste au run jusqu'à la fin des contrôles de la 4.9, puis est rendu à Anaël (benchmarks) : le prévenir. Aucune story des Epics 5 à 8 ni la 7.1 avant une nouvelle consigne.

## Décisions d'Anaël (2026-10-19, vers 12 h 30, pour la reprise des Epics 5 à 8)

- Ollama disponible au run la plupart du temps ; une ou deux pauses possibles sur demande (tests integration alors notés « à rejouer »).
- Prix cloud : Groq à 0 (plan gratuit de l'API) ; `mistral-large-latest` = `mistral-large-2512` (Large 3) vérifié par l'API, 0,50 / 1,50 USD (PR #81).
- Sprite Material Symbols Rounded officiel : accord (à intégrer, aucun téléchargement par le run : fourni par Anaël ou story dédiée).
- `.venv` du dépôt principal resynchronisé (`uv sync`, 2.0.0a4).
- Recommandations de l'orchestrateur acceptées (AD-6 amendé, 18 écarts du §7(d) tranchés, ajouts d'API et points ouverts ratifiés, dette 8.1, `mesures-couts/` ignoré) : **`_bmad-output/planning-artifacts/decisions-2026-10-19.md`** (PR #82), qui prime sur les documents qu'elle amende jusqu'à la passe « Report au contrat » (avant la 5.1). Les écarts du §7(d) ne sont plus « jamais tranchés » : appliquer ce fichier.

## Contrats partagés en cours

Noms, modules et constantes décidés pour plusieurs stories ; à citer dans chaque prompt, à réutiliser plutôt qu'à recréer.
- Onglets au clavier : `screens/arena-tabs.js` (`nextTab`, `moveTab`) ; pas de second module (doublon `core/tab-keys.js` retiré à la fusion de la 4.8).
- Onglets d'écran : `core/screen-tabs.js` (`screenTabs`).
- Garde-fou mémoire côté écran : `core/ram-guard.js` (`isRamGuard`, `onSmallerModel`, `swapModel`), erreur `ram_guard` (503) avec `detail.needed_gb`, `detail.suggested_model` (4.8).
- Dialogue de confirmation : `components/wl-confirm-dialog.js` (4.3).
- Graphiques : `components/wl-chart-svg.js`, `core/chart-scale.js` (3.4).
- Formats : `core/format.js` (`formatMoney`, `formatDate`, `co2Group`, `formatScore`…), jamais de calcul de métrique à l'écran (AD-20).
- Prix cloud : `[cloud.prices]` de `wavelocalai.toml` (`PriceTable`, devise ISO 4217), vide tant qu'Anaël ne l'a pas remplie (3.5).
- `onSmallerModel` (`core/ram-guard.js`) rend une fonction de retrait de l'écouteur, à appeler au démontage (7.3) ; Arène, Discussion et Base ne l'appellent pas encore (8.1).
- Trace d'étapes d'agent : `components/wl-step-trace.js` (6.4), réutilisée par l'Équipe (6.6).
- Résultats du banc côté serveur : `models/bench_results.py` (5.6), réutilisé par 5.7 et 5.8.
- Préversions a5, a6, a7 : posées par l'orchestrateur (`bump_version.py`), dans l'ordre, jamais par l'agent de story.
- Taille : aucun fichier JS du front au-delà de 600 lignes (`arena.js` à 598 : ne plus rien y ajouter, sortir un module voisin).

## Périmètre étendu (confirmé par Anaël le 2026-10-18 vers 23 h 20)

- Après le MVP (Epics 3 et 4 jusqu'à la 4.9, dans l'ordre prévu) : Epics 5 à 8, stories 5.1 à 5.8, 6.1 à 6.6, 7.1 à 7.4, 8.1 à 8.3 (en backlog dans le statut du sprint). **8.4 (« La v2 remplace la v1 ») exclue** : revient à Anaël.
- **Garde-fou** : aucune story de l'Epic 5 ou suivante avant la fusion sur master de la PR `bmad-correct-course` (43 décisions d'UX de la maquette, PR #58). Vérifier : `gh pr list --state merged --search "correct-course"` ou un commit qui modifie `epics.md` avec les décisions de la maquette. Une fois fusionnée : fusionner `origin/master`, appliquer ses ajustements aux stories en cours (3.1, 3.2, 3.3, 4.1, 4.2 citées) avant leur PR, ajouter les stories de suite qu'elle liste (Epics 1 et 2).
- Préversions 2.0.0a5 (5.8), a6 (6.6), a7 (7.4) : version dans le manifeste, tags et releases en attente d'Anaël.
- 6.3 (email) : SMTP factice seulement, aucun envoi réel. 5.3 et 5.5 (installation de modèle, reranker) : téléchargements simulés ; un vrai téléchargement est une ressource à activer par Anaël (le prévenir, avancer sur le reste).
- Écrans des Epics 5 à 7 : référence visuelle `docs/maquette-v2/` (une fois la PR #58 fusionnée) ; les documents de contrat priment sur la maquette.
- **Second message de `wavelocalai-d7` (2026-10-19 vers 0 h 30, annoncé par Anaël), appliqué** : PR #58 (maquette, f4e48b8) et #61 (correct course, 72137a4) fusionnées ; **garde-fou de l'Epic 5 levé**. Consignes détaillées : `_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md` §7 ((a) ajustements des stories en cours, (b) stories 1.12 et 2.7, (c) changements du backlog, (d) 18 écarts ouverts).
- **Décision d'Anaël (2026-10-19 vers 7 h)** : (1) fichiers d'état hors des PR de story (PR `chore/etat-run-*`) ; (2) story technique **5.0 « Découper les fichiers partagés du front »** avant l'Epic 5 (textes par écran, CSS par composant, `api.js` par domaine, routes déclarées par écran, job E2E dans la CI) ; (3) vagues des Epics 5 à 8 planifiées par fichiers touchés ; `rerere` activé, journal `run-autonome.md` fusionné par `union` (`.gitattributes`).
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
| 4.5 | feat/v2-rag-discussion | #73 | fusionnée (3e11106) ; dev 90cfc80 ; revue e6ab8a7 ; CSS reconstruit + test d'accolades (ad38c42) ; garde-fou branché (23357db) | §7(d) n° 12 en variante conservatrice ; report : `conversation_id` dans le détail de `run_busy` |
| 3.5 | feat/v2-verdict | #74 | fusionnée (03243e5) ; dev 763a122 ; revue ba68f14 ; prix relevés a9f0dab (8 modèles, USD) | table de prix : Groq llama et mistral-large-latest « inconnu » ; verdict non figé en base |
| 4.9 | feat/v2-flow2 | #79 | fusionnée (de1288c) ; dev c935eff ; fusions 4.7 et 3.6 + revue c82d742/50ef444 (Accueil après `shell-ready`, une lecture par affichage) ; complet : 459 E2E, 12 integration, 1238 v2, 1286 v1 | écart AD-6 (l'Accueil appelle `GET /api/rag/documents`) ; §7(d) n° 12, 13 conservateurs ; report : `wl-model-picker.js` 666 lignes |
| 4.7 | feat/v2-rag-reranker | #78 | fusionnée (4fb98c8) ; dev 6d8ab31 ; revue 15d461e (chargement unique, test sur le vrai fastembed hors ligne) | écarts `reranker` dans `GET /api/rag/settings`, champs de `retrieval_step` ; reports : nom de cache vs dépôt source (5.5), énergie du reclassement (AD-10) |
| 4.6 | feat/v2-rag-strategies | #77 | fusionnée (8d6210d) ; dev 94ec8bb ; fusion 4.3 2cc063f ; revue cb98d39 (notation Self-RAG, garde-fou sur les appels de stratégie) | écarts `strategy`/`top_k`, étapes de `retrieval_step`, `citations` (§7(d) n° 18) ; report : integration HyDE |
| 3.6 | feat/v2-arene-reouvrir | #76 | fusionnée (360c6a4) ; dev 1978ab7 ; revue 0c907bc ; carte démo après `shell-ready` e96be54 | §7(d) n° 3, 7, 8 conservateurs ; préversion 2.0.0a3 |
| 4.3 | feat/v2-rag-gestion (depuis master fff8faa, puis 2567e44 et b90056e) | #68 | fusionnée (f25f398) ; dev 974925c ; revue 0829e07 (`null` des réglages, embedding contrôlé, refus `vector_tables_unreachable` sans module vec0, délai client 300 s) ; rapide OK, 1017 v2, 298 E2E, 11 integration, 1286 v1 | écarts : quatre codes (`embedding_change_needs_clear`, `base_count_stale`, `base_in_use`, `vector_index_lost`) + `vector_tables_unreachable`, `GET /api/rag/settings` enrichi ; §7(d) n° 13 en variante contrat (409 affiché) ; pour Anaël : interprétation de « document visé » (refus si `indexing` ou run `rag` actif), import non refusé sans sqlite-vec ; résidu vectoriel : aucun avec sqlite-vec 0.1.9 ; reports : bornes d'API plus larges que la maquette, purge bloquée par un lecteur sans signal à l'écran |
| 3.4 | feat/v2-classement (depuis master 2567e44, puis b90056e) | #69 | fusionnée ; dev ecf58f6 ; revue 02fdaef (étiquettes longues coupées, défilement du tableau gardé, gel à `run_ended`, largeur mesurée) ; rapide OK, 971 v2, 307 E2E, 10 integration, 1286 v1 | écarts : matrice et tableau dès la première lane mesurée, « Voir le tableau » en bouton ; §7(d) n° 4 à 8 en variante actuelle (« le plus petit des trois » non livré) ; reports : CO₂ d'une lane annulée « non mesuré » (3.6), `range_mg` non affichée, échelle linéaire du débit (log à décider), route de test sans script de juge ni `co2` par lane |
| 4.8 | feat/v2-garde-memoire (depuis master 4635302, puis 2567e44 et b90056e) | #70 | fusionnée (3a36f55) ; dev b7f6fc6 ; revue 67fb239 (mémoire des modèles chargés inactifs comptée comme libre, modèle proposé plus petit, `required_gb` partagé, déchargement relit les runs actifs) ; fusion de master résolue 8e2f758 (garde-fou aussi pour le juge local) ; rapide OK, 1019 v2, 317 E2E, 10 integration, 1286 v1 | écarts à ratifier : `detail.needed_gb` = mémoire à avoir de libre (marge comprise), `ram_guard` en 503, `memory.available_gb` dans le flux système, `required_gb` dans `GET /api/models` ; §7(d) n° 13 : import non gardé ; pour Anaël : bouton « Décharger les modèles inactifs » lors d'un refus, vérification Linux 16 Go (mmap) ; reports : VRAM non comparée, cache de contexte ignoré |
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

### 2.0.0a3 (fin de l'Epic 3) — en attente d'Anaël

Version `2.0.0a3` posée par la PR de la story 3.6 (#76, merge commit 360c6a4). **Tag `v2.0.0-alpha.3` et release GitHub non créés** : à faire par Anaël après la recette.

Commandes (après recette) : `git tag -a v2.0.0-alpha.3 360c6a4 -m "wavelocalai 2.0.0a3 : l'Arène des modèles"`, `git push origin v2.0.0-alpha.3`, puis `gh release create v2.0.0-alpha.3 --prerelease --title "2.0.0a3 : l'Arène des modèles" --notes-file <notes ci-dessous>`.

Brouillon des notes :

> Troisième préversion de la v2 (`wavelocalai-v2`, port 8502 ; la v1 reste sur 8501). Elle apporte l'Arène des modèles : la même question posée à 2 à 4 modèles, côte à côte, notée, classée et chiffrée.
>
> - Colonnes qui se remplissent au fil du flux, avec le statut de chaque modèle en texte. Un modèle en échec ou en délai ne bloque pas les autres.
> - Notation par un juge (local par défaut, cloud seulement si « Autoriser le cloud » est actif) sur des critères modifiables ; « non évalué » avec sa raison, jamais 0 ; avertissements « note peu fiable » et « un seul juge ».
> - Classement, matrice note / débit / CO₂ (avec son tableau), verdict local contre cloud qui chiffre l'écart de note, le coût pour 1 000 requêtes (prix publics relevés le 2026-10-19, en USD ; « inconnu » pour les modèles sans prix public) et les données restées sur le poste.
> - Garde-fou mémoire : le besoin d'un modèle est chiffré avant la génération, avec « Prendre un modèle plus petit ».
> - Rouvrir une comparaison par son adresse ou la liste des comparaisons précédentes, sans relancer de modèle ; « Relancer » et « Modifier la question ».
> - Export CSV ou Markdown avec la preuve de la mesure (fiche machine, version d'Ollama, digests, méthode du CO₂, juge et critères ; aucune clé d'API). Effacement d'une comparaison : le texte disparaît de la base et de son journal, le CO₂ reste au registre carbone.
> - Accueil : carte « Démo recommandée » qui présélectionne les modèles prêts et lance l'Arène.

Recette humaine (environ 15 min, Flow 1) :
1. `uv sync` puis `uv run wavelocalai-v2`, ouvrir `http://127.0.0.1:8502` ; avec Ollama et au moins 3 petits modèles, l'Accueil dit « Disponible ».
2. Carte « Démo recommandée » : modèles prêts avec badge Local ; Ollama arrêté : « Aucun modèle local disponible », « Lancer une comparaison » reste actif.
3. Ollama relancé, « Lancer une comparaison » : modèles présélectionnés ; Lancer ; colonnes en flux, classement qui se fige, matrice et CO₂, sans rechargement.
4. Avec « Autoriser le cloud » et une clé dans `.env` : un modèle local contre un cloud ; le verdict chiffre écart de note, coût (USD) et CO₂ (estimé pour le cloud).
5. Pendant un run, Échap : « Comparaison arrêtée » ; CO₂ d'une colonne arrêtée affiché ou « non mesuré ».
6. Recharger sur `#/arene/comparer/<run_id>` ou ouvrir une « Comparaison précédente » : tout se reconstruit sans relancer ; une adresse bidon dit « Résultat introuvable ».
7. « Modifier la question » reprend question, modèles, juge et critères ; « Relancer » les relance.
8. Exporter en CSV et en Markdown (sous 768 px : un seul menu « Exporter ») ; aucune clé dans les fichiers.
9. « Effacer la comparaison » : confirmation sur « Annuler » par défaut ; le CO₂ de session ne baisse pas ; l'adresse dit ensuite que la comparaison est effacée.
10. À trancher : §7(d) n° 7 (adresse non réécrite en fin de run) et n° 8 (résultat effacé : même titre « Résultat introuvable »), `date-released` de `CITATION.cff`, prix de `mistral-large-latest`.

### 2.0.0a4 (fin de l'Epic 4, fin du MVP) — en attente d'Anaël

Version `2.0.0a4` posée par la PR de la story 4.9 (#79, merge commit de1288c). **Tag `v2.0.0-alpha.4` et release GitHub non créés** : à faire par Anaël après la recette.

Commandes (après recette) : `git tag -a v2.0.0-alpha.4 de1288c -m "wavelocalai 2.0.0a4 : MVP, atelier documentaire"`, `git push origin v2.0.0-alpha.4`, puis `gh release create v2.0.0-alpha.4 --prerelease --title "2.0.0a4 : MVP, atelier documentaire" --notes-file <notes ci-dessous>`.

Brouillon des notes :

> Quatrième préversion de la v2 (`wavelocalai-v2`, port 8502 ; la v1 reste sur 8501). Elle clôt le MVP : Arène des modèles et assistant documentaire, de bout en bout, sur le poste.
>
> - Arène : comparer 2 à 4 petits modèles sur une question, avec juge, matrice qualité/CO₂, verdict local/cloud chiffré, historique et exports (préversion a3).
> - Base documentaire : importer PDF, TXT, MD ou DOCX avec suivi par fichier ; supprimer un document ou vider la base avec confirmation chiffrée ; réglages (embedding, découpe, extraits, stratégie).
> - Discussion avec ses documents : sources avant la réponse, avec page, pertinence et extrait entier dont le passage qui répond est surligné ; stratégies directe, HyDE et vérifiée (Self-RAG) ; marqueurs [n] vérifiés et reliés aux sources ; reclassement par un reranker local s'il est déjà installé (sinon l'écran dit pourquoi ; aucun téléchargement).
> - Garde-fou mémoire : la question reste, l'alerte chiffre le besoin et propose un modèle plus petit ou de décharger les modèles inactifs.
> - Accueil : la carte « Documents » dit « N documents indexés · M extraits ».
> - Aucune requête hors de la machine ; axe-core sans violation sur chaque écran, en clair et en sombre.
>
> Pas encore là : Sobriété, Modèles, Agents, Évaluation, Banc d'essai (préversions suivantes).

Recette humaine (10 à 15 min, PC de 16 Go sans GPU) :
1. `uv sync` puis `uv run wavelocalai-v2` ; l'Accueil dit « Disponible » ; carte « Documents » : « 0 document indexé · 0 extrait ».
2. Flow 1 rapide (3 min) : Arène, 3 petits modèles locaux, une question, un juge ; matrice et chiffres lisibles du fond de la salle.
3. Flow 2 : carte « Documents » → « Votre base documentaire est vide » ; importer un `.docx` ; la ligne suit le fichier, puis « N extraits ajoutés depuis 1 document » ; l'Accueil dit « 1 document indexé · N extraits ».
4. Discussion : modèle local par défaut avec sa raison ; une question : « Chargement du modèle en mémoire… », puis réponse avec débit, CO₂, durée ; sources avant la réponse.
5. « Ouvrir l'extrait » : paragraphe retrouvé mot pour mot, phrase qui répond surlignée ; essayer HyDE et « Recherche vérifiée » ; sans reranker : « Reclassement indisponible : <raison> ». Avec reranker (optionnel) : `uv sync --extra rerank`, modèle dans le cache, puis `tests/v2/integration/test_rag_rerank_local.py`.
6. Base documentaire, « Vider la base documentaire » : le dialogue annonce le nombre d'extraits ; « Annuler » ne supprime rien.
7. Garde-fou : modèle trop gros pour la mémoire libre : la question reste, « Mémoire insuffisante : X Go nécessaires, Y Go libres » ; « Prendre un modèle plus petit » sans relancer.
8. Clavier seul et 320 px sans défilement horizontal ; panneau réseau : aucune requête hors de 127.0.0.1.
9. À trancher : l'appel de l'Accueil (AD-6), écarts au contrat des 4.6/4.7 (`strategy`, `top_k`, `citations`, `reranker`, champs de `retrieval_step`), §7(d) n° 7, 8, 12, 13, 18, `date-released` de `CITATION.cff`.
