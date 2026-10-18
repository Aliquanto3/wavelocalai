---
title: 'Le serveur v2 démarre en local, protégé, et dit son état'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'bf7c66f'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-1.md'
warnings: []
deferred:
  - summary: >-
      Arrêt propre : « les runs actifs passent à `cancelled` » (AD-23) n'est pas câblé. uvicorn s'arrête proprement sur Ctrl+C / SIGTERM et le verrou est relâché, mais le hub des runs n'existe pas encore.
    evidence: |-
      Aucun run avant la story du hub (1.3 et suivantes).
    location: src/wavelocalai/web/server.py
    severity: low
  - summary: >-
      Délais de `wavelocalai.toml` (`lane_timeout_s = 300`, `approval_expiry_s = 600`) : valeurs provisoires, lues par aucun code. 600 s vient du contrat (approbation sans réponse en 10 min) ; 300 s est un défaut à confirmer à la story de l'Arène.
    evidence: |-
      Critère « délais » de la story ; aucune story ne les consomme encore.
    location: wavelocalai.toml
    severity: low
  - summary: >-
      Le budget de lecture lit les routes dans le schéma OpenAPI (`app.openapi()`) plus les routes Starlette directes : une route `include_in_schema=False` posée par un `include_router` échappe au test (FastAPI 0.143.5 range ces routes dans `_IncludedRouter`, interne).
    evidence: |-
      `tests/v2/web/test_read_budget.py` ; aucune route de ce type aujourd'hui.
    location: tests/v2/web/test_read_budget.py
    severity: low
  - summary: >-
      Journaux : uvicorn.access écrit chaque requête (méthode et chemin) au niveau INFO. Aucun prompt n'est dans un chemin aujourd'hui ; à surveiller si une route met du texte saisi dans l'URL.
    evidence: |-
      AD-23 (« sans texte de prompt, de réponse ou de document au niveau INFO »).
    location: src/wavelocalai/store/logs.py
    severity: low
---

# Story 1.2 : le serveur v2 démarre en local, protégé, et dit son état

## Objectif

`wavelocalai-v2` lance un serveur FastAPI sur `127.0.0.1:8502` seulement, qui refuse les pages étrangères, répond toujours en erreur au format unique, et dit en moins de 300 ms (Ollama arrêté) si Ollama répond via `GET /api/health`. Un second serveur sur le même dossier de données, ou le même port, refuse de démarrer.

## Critères d'acceptation et preuves

1. `Settings` (pydantic, `config.py`) : défauts du code, puis `wavelocalai.toml` (`tomllib`, versionné : hôte Ollama `127.0.0.1:11434`, port, pays et PUE, délais), puis `.env` et environnement (clés d'API, `WAVELOCALAI_PORT`/`_DATA_DIR`/`_OLLAMA_HOST`), puis options de la ligne de commande. Immuable. Preuve : `tests/v2/unit/test_config.py` (ordre de priorité, toml invalide refusé en français) ; test AST `test_no_getenv_outside_config` (`getenv`, `environ.get`, `environ[...]`, avec modules pièges en dossier temporaire).
2. `telemetry.py` (copie adaptée de la v1, `FASTAPI_OTEL_AUTO_CONFIGURE=false` dans les opt-outs) est appliqué dans `create_app` avant `FastAPI(...)`, créée avec `tracing`, `metrics`, `logs`, `operation_spans`, `auto_configure` à `False` (paramètre `telemetry=` de FastAPI 0.143.5). Preuve : `tests/v2/unit/test_telemetry.py` (valeurs conservées, `app._telemetry`, test AST de l'ordre d'appel pour `create_app` et pour tout import de `fastembed`/`huggingface_hub`).
3. Sécurité locale (`web/security.py`, middleware ASGI pur, compatible SSE) : `Host` hors `127.0.0.1:<port>`/`localhost:<port>` refusé (403 `forbidden_host`) ; écriture avec `Origin` étrangère refusée (403 `forbidden_origin`) ; aucun en-tête CORS (réponses normales, refus, préflight). Écoute sur `127.0.0.1` seulement (`bind_socket`). Preuve : `tests/v2/web/test_security.py` (23 cas), `test_real_launch.py` (serveur réel : Host étranger refusé, pas de CORS).
4. `errors.py` : liste fermée (`ollama_down`, `forbidden_host`, `forbidden_origin`, `internal`, plus `not_found`, `method_not_allowed`, `invalid_request` pour les 404/405/422 de FastAPI), enveloppe `{code, message, action, detail}` en français, `detail` objet (`technical` plus clés machine déclarées avec le code, ici `host` et `origin`), valeurs texte masquées (préfixes `sk-`, `gsk_`, `hf_`, `Bearer`, `api_key=…`, et valeurs des clés configurées dans `Settings`). Les journaux masquent aussi les clés, traces d'exception comprises. Preuve : `test_errors.py`, `web/test_errors_envelope.py` (route qui lève `AppError`, route qui lève `RuntimeError` avec fausse clé `sk-proj-…` et clé configurée sans préfixe).
5. Budget de lecture : `tests/v2/web/test_read_budget.py` découvre depuis l'app les routes `GET` sans paramètre de chemin hors SSE (schéma OpenAPI plus routes directes), et vérifie < 300 ms Ollama injoignable (port fermé). Une route ajoutée entre d'elle-même (test de découverte avec route ajoutée, SSE et paramètre de chemin écartés).
6. `GET /api/health` : `version`, `instance_id` (uuid4 hex nouveau à chaque `create_app`), `ollama {up, version, latency_ms}`, `cloud_providers [{id, configured}]` lus depuis `Settings`, sans appel. Sonde Ollama (`models/ollama_probe.py`) : délai 1 s, cache 5 s, appel unique partagé (tâche de fond), et `status()` n'attend le résultat que 100 ms : Ollama arrêté, la connexion refusée peut durer ~2 s sous Windows, la route répond `up: false` aussitôt. Preuve : `test_ollama_probe.py` (cache, délai, simultanéité, port fermé), `web/test_health.py`. Lancement réel avec l'Ollama du poste : `up: true`, 59 ms, version 0.40.5.
7. Verrou et port : `store/datadir.py` (`DataDirLock`, `msvcrt.locking` / `fcntl.flock`, libéré par le système si le processus meurt) et `web/server.py` (`bind_socket`, socket ouvert puis confié à uvicorn : pas de course). Un second lancement sur le même dossier : « Un autre wavelocalai-v2 utilise déjà le dossier de données… » ; sur le même port : « Le port 8502 est occupé… » ; code de sortie 1. Preuve : `test_datadir.py`, `test_main.py`, `test_real_launch.py` (trois processus réels).
8. Journaux en rotation 5 × 1 Mo dans `data/logs/` (`store/logs.py`, `RotatingFileHandler`, 1 000 000 octets, 4 archives) ; alerte journalisée si le dossier de données est sous OneDrive ; tests en dossier temporaire, jamais `data/`. Preuve : `test_datadir.py` (80 écritures de 100 ko : exactement 5 fichiers), `test_main.py::test_onedrive_data_dir_is_logged_as_a_warning`.
9. Cohérence : `tests/v2/unit/test_layers.py` reste vert (`__main__` importe `web/server.py`, seul à importer `uvicorn`) ; la v1 est intacte (`python -m pytest tests/unit tests/app`) ; `controle_rapide.py` sans erreur.

## Fichiers

- `wavelocalai.toml` (nouveau, versionné)
- `src/wavelocalai/` : `config.py`, `errors.py`, `telemetry.py`, `__main__.py` (lanceur), `models/ollama_probe.py`, `store/datadir.py`, `store/logs.py`, `web/app.py`, `web/routes_health.py`, `web/security.py`, `web/server.py`
- `tests/v2/` : `conftest.py`, `unit/{test_config,test_errors,test_telemetry,test_datadir,test_ollama_probe,test_main}.py`, `web/{test_security,test_errors_envelope,test_health,test_read_budget,test_real_launch}.py`

## Choix notables

- Aucune dépendance nouvelle : `pydantic`, `python-dotenv`, `httpx`, `fastapi`, `uvicorn` étaient déjà au lock (pydantic reste 2.12.5, voir story 1.1).
- FastAPI 0.143.5 : la télémétrie se coupe par `FastAPI(telemetry={...})`, et `include_router` range les routes dans une structure interne (`_IncludedRouter`) : `app.routes` ne les liste plus, d'où la découverte par `app.openapi()`.
- Docs interactives et `/openapi.json` désactivés (`docs_url=None`, `redoc_url=None`, `openapi_url=None`) : surface réduite, rien d'utile pour un serveur local.
- Le verrou est un fichier (`data/.wavelocalai.lock`) verrouillé par le système, sans PID écrit : un verrou périmé ne peut pas rester après un arrêt brutal.
- Les opt-outs de télémétrie de la v2 ne reprennent pas ceux de la v1 qui visent des bibliothèques que la v2 n'utilise pas (Ragas, CrewAI, LangSmith) ; `ANONYMIZED_TELEMETRY` (Chroma) reste par prudence tant que la v1 vit dans le même environnement.
- Une requête sans `Origin` (curl, tests) est acceptée en écriture : seul un navigateur envoie `Origin`, et c'est lui qu'il faut contrer.

## Reports

Voir l'en-tête `deferred` : arrêt propre des runs (hub), délais provisoires du `.toml`, découverte des routes hors schéma, journaux d'accès uvicorn.

## Revue

- medium, second avis n° 1 — corrigé : un Ollama vivant mais lent (> 100 ms, démarrage à froid) était annoncé `up: false` à la première lecture. Le contrat impose `up` booléen, donc pas d'état « inconnu » : `OllamaProbe.start()` lance la première sonde dans le `lifespan` de l'app, avant toute requête, et un cache échu rend l'état précédent pendant la sonde suivante (seul un échec de sonde fait passer à `up: false`). Budget de 300 ms inchangé (`status()` attend toujours 100 ms au plus). Tests : `test_start_probes_before_the_first_read…`, `test_expired_cache_keeps_the_last_state…`, `test_startup_probe_reports_a_slow_ollama_up…` (échoue sans le correctif).
- medium, revue — corrigé : `test_real_launch.py` échouait sous Windows (sortie tubée du sous-processus en cp1252, lue en UTF-8 : `err` vaut `None`). La CI Windows aurait été rouge. Le test passe `PYTHONIOENCODING=utf-8` au sous-processus.
- low, second avis n° 2 — reporté : `Origin` non contrôlée sur une poignée de main WebSocket (le `Host` l'est). Aucune route WS, le contrat n'utilise que SSE ; à traiter avec la première route WS, s'il y en a une.
- low, second avis n° 3 — rejeté : h11 (uvicorn) refuse déjà plusieurs `Host` ; un navigateur n'envoie jamais deux `Origin`, et une page étrangère ne peut pas en forger.
- low, second avis n° 4 — corrigé : `MISTRAL_API_KEY=…` et `ANTHROPIC_API_KEY=…` n'étaient pas masqués (`\b` après `_`) ; l'expression accepte désormais un préfixe (`test_prefixed_env_var_names_are_masked`).
- low, second avis n° 5 — reporté : les `Mount` (fichiers statiques de `web/static/`) échappent à la découverte du budget de lecture ; à revoir avec la story qui monte les fichiers statiques.
- low, second avis n° 6 — reporté : toute `OSError` du verrou devient « un autre wavelocalai-v2 » et `setup_logging` précède le verrou (un second lancement écrit une ligne dans le journal du serveur vivant). Sans gravité ; reprise du lanceur laissée aux stories qui le modifient (1.3) pour ne pas gêner leur fusion.
- low, second avis n° 7 — rejeté : une clé d'API réelle fait toujours plus de 8 caractères ; masquer des valeurs plus courtes remplacerait des sous-chaînes banales.
