---
title: 'Dette de l''Epic 8, lot a : serveur et garde-fous'
type: 'fix'
created: '2026-10-19'
status: 'review'
baseline_commit: 'ce1aac9'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
warnings: []
deferred:
  - summary: >-
      Le lanceur sort désormais normalement sur Ctrl+Break (C7), donc il attend aussi le
      préchauffage de CodeCarbon encore en cours (jusqu'à ~10 s sous Windows, mesuré) : avant, le
      processus était tué net par le gestionnaire par défaut de SIGBREAK, ce qui cachait ce délai
      et laissait la base et le verrou à l'OS. Le préchauffage tourne dans le pool de threads par
      défaut, que `asyncio.run` attend à la fermeture de la boucle.
    evidence: |-
      Journal de `wavelocalai.log` : 7,5 s entre « Finished server process » et « base fermée,
      verrou relâché » quand le signal arrive moins de 8 s après le démarrage ; trace
      `faulthandler` : `local_meter._start_sync` → `codecarbon ... _setup_windows_emi`.
    location: src/wavelocalai/greenops/local_meter.py
    severity: low
  - summary: >-
      Le flux d'un run dont la clôture a échoué en base se termine sans `run_ended` (la transaction
      est annulée, rien n'est persisté) : le front verra un flux fermé sans fin de run, puis, après
      redémarrage, le run `interrupted`. Pas de second essai d'écriture (disque plein).
    evidence: |-
      `runs/hub.py::_abandon`, `tests/v2/unit/test_hub.py::test_failed_close_purges_the_run_...`.
    location: src/wavelocalai/runs/hub.py
    severity: low
  - summary: >-
      Un run qui démarre sur un modèle en cours de suppression reçoit `404 model_not_found`
      (variante conservatrice : aucun code d'erreur nouveau) ; un message dédié (« en cours de
      suppression ») demanderait un code et son texte, à décider.
    evidence: |-
      `runs/hub.py::RunHub.deleting_model`, `inference/delete.py`.
    location: src/wavelocalai/runs/hub.py
    severity: low
---

# Story 8.1a : serveur et garde-fous

## Objectif

Solder la dette serveur et tests relevée pendant le MVP (C1 à C9, copies de migration, verrou par
modèle), et découper le contrat d'API par story, pour que les lots b et c de la 8.1 (écrans) et les
stories suivantes s'y ajoutent sans conflit.

## Critères d'acceptation et preuves

1. **C1** : `tests/v2/unit/test_layers.py` relève `import wavelocalai` suivi d'un accès d'attribut
   (`wavelocalai.runs`, alias compris), `getattr(wavelocalai, "runs")`, `importlib.import_module`
   et `__import__` (noms absolus, relatifs avec `package=`), et refuse un import dynamique dont le
   nom n'est pas un littéral (non vérifiable). Modules pièges ajoutés et cas légitimes acceptés.
2. **C2, C3** : `tests/v2/web/route_discovery.py` découvre toutes les routes (dans un routeur inclus
   avec ou sans préfixe, `include_in_schema=False` compris) et les `Mount` de fichiers, sans importer
   de classe interne de FastAPI (attributs `original_router` et `include_context.prefix`, `Mount`
   de Starlette). Un test recoupe la découverte avec `app.openapi()` : une montée de FastAPI qui
   change la structure fait rougir le test au lieu d'oublier une route. Le budget de 300 ms mesure
   aussi un échantillon de fichiers de chaque `Mount` (les trois plus gros, un par extension).
3. **C4** : `tests/v2/web/test_route_params.py` : aucun paramètre de chemin ou de requête n'est un
   texte saisi ; admis : `*_id`, nombres et booléens, valeurs d'une liste fermée, ou liste
   `JUSTIFIED` (`tag`, `name`, `window`, `kind`, `purpose`, `after`, chacun avec sa raison). Le test
   refuse `q`, `question`, `text`… et un paramètre texte nouveau non justifié.
4. **C5** : `DataDirLock.acquire` distingue un serveur vivant (`DataDirLockedError`) de toute autre
   cause (`DataDirLockError` : droits, disque, dossier absent), dite telle quelle. Le lanceur prend le
   verrou **avant** `setup_logging` : un second lancement refusé n'ouvre ni n'écrit le journal du
   serveur vivant (test : fichier et date de modification intacts).
5. **C7** : sous Windows, Ctrl+Break : sortie 0, base fermée (plus de `-wal`), verrou relâché, ligne
   « base fermée, verrou relâché » au journal (test en sous-processus, ignoré hors Windows). Cause :
   uvicorn relève le signal à sa sortie et le gestionnaire par défaut de `SIGBREAK` tuait le
   processus sans passer par les `finally` ; `serve` pose un gestionnaire sans effet pendant `run`
   (`SIGINT`, `SIGTERM`, `SIGBREAK`).
6. **C6** : échec de la transaction de clôture (disque plein simulé) : racine et enfants purgés de la
   mémoire du hub (`_abandon`), erreur journalisée, place du `kind` libre (un nouveau run démarre),
   appels tardifs sans effet, ligne `running` devenue `interrupted` au démarrage suivant.
7. **C8** : `POST /api/system/ollama/recheck` force une sonde neuve (celle des routes de lecture et
   celle du flux) sans attendre le cache, répond en moins de 300 ms (`wait_s` de 250 ms) avec
   `{up, version, latency_ms, settled}` ; sonde lente : `settled` faux, puis `system_state` publié sur
   le flux dès qu'elle finit. Le front applique la réponse tout de suite (`core/system.js`,
   `core/api/system.js`). Une sonde lancée avant le clic ne réécrit pas l'état (génération).
8. **C9** : le catalogue de textes (`text_catalog`) ajoute `errors`, généré depuis `errors.py`
   (`error_texts()`, sans Markdown, espaces insécables) ; `errors` retiré de `i18n/fr/shell.json` ;
   test miroir supprimé, remplacé par des tests de la génération et du refus d'une clé `errors`
   déclarée dans un fichier. `tests/v2/unit/static_files.py::catalog()` rend le même catalogue.
9. **Copies `.db.bak-N`** : une seule copie gardée (celle de la dernière migration), les autres
   supprimées après une migration réussie ; tout effacement (`purge=True`) supprime aussi la copie,
   et si elle est tenue, la purge reste due et se rejoue (tests, dont un effacement réel avec texte
   unique retrouvé dans la copie avant, absent après).
10. **Verrou par modèle** : `RunHub.deleting_model(tag)` posé avant le contrôle d'usage et tenu
    jusqu'à la fin de la suppression ; un run en cours de création compte comme employant ses
    modèles (`_pending`, même segment synchrone que le contrôle). Test web : un run lancé pendant
    l'appel d'Ollama est refusé (`model_not_found`), la suppression réussit, aucun run ne reste.
11. **Contrat découpé** : chaque sous-section « (story X.Y) » de `contrat-api.md` est déplacée telle
    quelle dans `contrat/<X-Y>.md` (13 fichiers) ; `contrat-api.md` garde le transverse et un index
    (« une story ajoute ses champs dans son propre fichier `contrat/<story>.md` et une ligne
    d'index »). Vérifié : aucune ligne perdue. Le lot a ajoute `contrat/8-1a.md` et sa ligne
    d'index ; les lots b et c créent le leur.
12. **`test_topbar` (serveur relancé)** : le test attend que la page connaisse l'identité du serveur
    (`instanceId`) avant d'arrêter le serveur : la pastille vient du flux avant `/api/health`, et sans
    identité un redémarrage n'est pas détecté (cause probable de l'instabilité sous charge, non
    reproduite à la demande). Le test « Réessayer » vérifie la requête `POST` et sa réponse.

## Hors périmètre

Écrans Arène, Banc, Discussion, Base, Agent, `wl-model-picker.js`, tests de la coquille
(`test_shell*.py` hors suppression du test miroir, `test_home.py`), message de `timeout`, sprite
d'icônes (attend Anaël).

## Écarts

- Test miroir de `test_shell_static.py` supprimé comme demandé (C9) ; `static_files.catalog()` ajoute
  `errors` : un seul test de `test_static_split.py` ajusté (`errors` est la seule clé non portée par
  un fichier).
- `test_real_shutdown.py` : la borne de 4 s du test des flux ouverts passe à 30 s (le lanceur sort
  maintenant normalement et attend le préchauffage de CodeCarbon, voir report) ; la preuve « flux
  fermés et non coupés » reste le journal sans « timeout graceful shutdown exceeded ».
- Le texte de `model_not_found` sert au refus d'un run sur un modèle en cours de suppression (aucun
  code nouveau, variante conservatrice).

## Notes de développement

- Serveur : `store/datadir.py`, `__main__.py`, `web/server.py` (`_absorb_reraised_signals`),
  `runs/hub.py` (`_abandon`, `deleting_model`, `_pending`), `store/migrate.py` (`backup_files`,
  `remove_backups`), `store/db.py`, `models/ollama_probe.py` (`recheck`, `settled`, `wait_settled`),
  `web/routes_system.py`, `web/system_state.py`, `inference/delete.py`, `errors.py`
  (`error_texts`), `web/routes_static.py`.
- Front : `core/system.js`, `core/api/system.js`, commentaires de `core/topbar.js` et `core/i18n.js`,
  `i18n/fr/shell.json`.
- Tests : `unit/test_layers.py`, `web/route_discovery.py`, `web/test_read_budget.py`,
  `web/test_route_params.py`, `unit/test_datadir.py`, `unit/test_main.py`,
  `web/test_real_shutdown.py`, `unit/test_hub.py`, `unit/test_ollama_probe.py`,
  `web/test_system.py`, `unit/test_errors.py`, `unit/test_static_split.py`, `web/test_static.py`,
  `unit/test_store.py`, `web/test_models_manage_api.py`, `e2e/test_topbar.py`.

## Rapport de dev

Voir le rapport de l'agent (tests ciblés lancés, résultats).

## Revue

Revue Opus, une passe, sur `ce1aac9..171efbc` (branche à jour de master par `ba43279`).

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| medium | second avis 1 | C1 : `import_module as im`, `getattr(importlib, "import_module")(...)`, `w = wavelocalai; w.runs`, `getattr(wavelocalai, nom)` et `package=` calculé échappaient au contrôle (le dernier était résolu contre le paquet du fichier). | Corrigé : alias du chargeur et réaffectations suivis, chargeur obtenu par `getattr`, nom ou `package=` non littéraux refusés (« non vérifiable ») ; 5 modules pièges. |
| medium | second avis 2 | Copie `.bak-N` tenue (Windows) : `VACUUM` et deux checkpoints rejoués à chaque écriture tant qu'elle reste. | Corrigé : deux reports séparés (espace libre, copies) ; une copie tenue ne rejoue que la suppression ; test qui prouve qu'aucun `VACUUM` n'est relancé. |
| low | second avis 3 | « Réessayer » : chaque clic lançait deux sondes et une publication ; 20 clics = 40 requêtes vers Ollama. | Corrigé : une sonde forcée en cours sert aux clics suivants, une seule publication `system_state` en attente par application ; test (20 clics, une requête). |
| low | second avis 4 | `route_discovery.py` : WebSocket et routes sans méthode ignorées en silence. | Corrigé : la découverte échoue (« route non couverte ») ; test. Rejeté pour les attributs `original_router`, `include_context`, `dependant` : c'est la solution retenue par C2 (aucune classe interne importée), gardée par le recoupement avec `app.openapi()`. |
| low | second avis 5 | Textes « Ollama ne répond pas » dans `models.json` et `components.json`. | Rejeté : ce sont des états d'écran propres à leur contexte (liste, installation, déchargement, sélecteur), pas le message ni l'action du code `ollama_down` d'`errors.py` ; C9 vise ces derniers, dont le miroir est supprimé. Écrans hors du lot a. |

Complexité : 0 constat (structures qui grossissent : `_pending`, `_deleting`, annonces de « Réessayer », bornées par les runs ou clics en cours ; la suppression des copies rejouée à chaque écriture ne coûte plus qu'un `glob`).

Tests ciblés : `unit/test_layers.py`, `test_store.py`, `test_ollama_probe.py`, `test_hub.py`, `test_errors.py`, `test_main.py`, `test_datadir.py`, `web/test_system.py`, `test_models_manage_api.py`, `test_read_budget.py`, `test_route_params.py` (245 passés) ; E2E `test_topbar.py` « Réessayer » (3 passés). Suite complète non lancée (poste partagé) : la CI de branche en tient lieu.
