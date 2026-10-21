---
title: 'Le lanceur ouvre l''application dans le navigateur'
type: 'feature'
created: '2026-10-21'
status: 'review'
baseline_commit: 'ba606cb'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
warnings: []
deferred: []
---

# Story 9.1 : le lanceur ouvre l'application dans le navigateur

## Objectif

`uv run wavelocalai-v2` (et `wavelocalai` après la 8.4) ouvre le navigateur par défaut sur l'application, une fois le serveur réellement prêt, sans jamais perturber les tests, la CI ni les E2E (gouverné par AD-23).

## Critères d'acceptation et preuves

1. **Ouverture unique, après que le port répond** : `_open_browser_when_ready` (`src/wavelocalai/__main__.py`) sonde le port par une vraie connexion TCP (`_port_is_open`), jamais par un délai fixe, dans un fil dédié démarré juste avant `serve(...)`. Preuve : `tests/v2/unit/test_browser_open.py::test_opens_once_after_the_port_is_ready_never_before` — `webbrowser.open` n'est pas appelé tant que rien n'écoute sur le port, puis appelé une seule fois dès qu'un socket se met à écouter.
2. **`--no-browser` et `[server] open_browser = false`** : nouvelle option CLI `--no-browser` et nouveau réglage `ServerSettings.open_browser` (défaut `true`, `src/wavelocalai/config.py`). `main()` ne lance le fil de guet que si `not args.no_browser and settings.server.open_browser`. Preuve : `test_no_browser_flag_skips_the_guard` et `test_open_browser_false_setting_skips_the_guard` (le fil n'est jamais créé, via un espion qui remplace `threading.Thread` seulement dans `__main__`).
3. **Les tests, la CI et les E2E ne lancent jamais de navigateur** : revue de toutes les façons dont `tests/v2` démarre un vrai serveur en sous-processus (`python -m wavelocalai`) — `tests/v2/web/test_real_launch.py`, `tests/v2/web/test_real_shutdown.py`, `tests/v2/e2e/conftest.py` (`Backend.start`) — chacune reçoit désormais `--no-browser`. Les tests `tests/v2/web` et `tests/v2/unit` qui passent par `create_app`/`TestClient` ou qui s'arrêtent avant `serve()` (port occupé, verrou pris, réglages invalides) n'atteignent jamais le fil de guet : aucun changement nécessaire là.
4. **Échec d'ouverture** : si `webbrowser.open` renvoie `False` ou lève, l'URL est écrite sur la console (`stderr`) et dans le journal (`logger.warning`/`logger.exception`), et la fonction revient sans exception : le serveur, déjà lancé dans le fil principal, continue. Preuve : `test_failed_open_writes_the_url_to_console_and_log`, `test_open_exception_is_caught_and_logged_without_crashing`.

## Contrat partagé

- Réglage `[server] open_browser` (booléen, défaut `true`), documenté dans `wavelocalai.toml` (commentaire à côté de `port`) et dans le README (section de lancement de la v2, à côté de `--port`/`--data-dir`/`--config`).

## Fichiers

- Code : `src/wavelocalai/__main__.py` (option `--no-browser`, `_port_is_open`, `_open_browser_when_ready`, câblage dans `main`), `src/wavelocalai/config.py` (`ServerSettings.open_browser`).
- Doc : `wavelocalai.toml`, `README.md`.
- Tests : `tests/v2/unit/test_browser_open.py` (nouveau) ; `tests/v2/web/test_real_launch.py`, `tests/v2/web/test_real_shutdown.py`, `tests/v2/e2e/conftest.py` (`--no-browser` ajouté aux lancements en sous-processus).

## Écarts et variantes conservatrices

- Le guet tourne dans un fil dédié démarré juste avant l'appel bloquant à `serve()`, plutôt que dans `serve()` lui-même : `web/server.py` reste le seul module à importer uvicorn/FastAPI (AD-4, AD-19), et `__main__.py` n'importe que `socket`, `threading`, `time`, `webbrowser` (stdlib). `tests/v2/unit/test_layers.py` reste vert.
- Fenêtre de sonde bornée à 30 s (`BROWSER_PROBE_TIMEOUT_S`) : si le port ne répond jamais (serveur qui ne démarre pas), le fil s'arrête sans ouvrir de navigateur, en écrivant l'URL sur la console et dans le journal comme pour un échec d'ouverture (`test_probe_timeout_writes_the_url_without_opening`), plutôt que d'attendre indéfiniment ; aucun critère ne demande explicitement cette borne, ajoutée par prudence (le fil est de toute façon `daemon=True` et arrêté par `stop_browser.set()` dès la sortie de `serve()`).

## Rapport de dev

- Tests ciblés : `tests/v2/unit` (1310 passés, 6 ignorés), `tests/v2/web/test_real_launch.py`, `tests/v2/web/test_real_shutdown.py`, `tests/v2/web/test_lifecycle.py` (6 passés) — tous verts, aucun navigateur ouvert.
- Contrôle rapide (`uv run python .claude/cost-kit/controle_rapide.py`) : propre.
- Pas de suite complète ni de lancement des E2E Playwright (hors périmètre des contrôles demandés pour cette story).

## Revue

Revue Opus du 2026-10-21, base à jour (`origin/master` = `ba606cb`, pas de rebase nécessaire).

- medium · second avis 1 · corrigé : sonde expirée (30 s) sans rien écrire. `_open_browser_when_ready` écrit désormais l'URL sur la console et dans le journal dans ce cas aussi (`_write_url_instead`), test `test_probe_timeout_writes_the_url_without_opening`. L'URL d'écoute était déjà toujours écrite au démarrage (`logger.info`, console et fichier), vérifié par un lancement réel `--no-browser`.
- medium · second avis 2 · rejeté : `propagate = False` laissé par `setup_logging` n'empêche pas `caplog` de capter les messages ; vérifié en plaçant avant `test_browser_open.py` un test qui met `propagate = False`, puis `test_main.py`, `test_cloud_adapters.py` et `test_datadir.py` : tout passe.
- low · second avis 3 · rejeté : la sonde ne réussit que si uvicorn écoute (`bind_socket` lie sans `listen`) ; un échec de `serve()` arrête le fil via `stop_browser`, et le fil est `daemon`.
- low · second avis 4 · rejeté : `webbrowser.open` qui renvoie `True` sans navigateur reste possible, mais l'URL est écrite au démarrage dans la console et le journal, quel que soit le résultat.
- low · second avis 5 · corrigé : spec réalignée avec le constat 1 (section « Écarts »).
- Complexité : 0 constat (aucune structure qui grossit).
