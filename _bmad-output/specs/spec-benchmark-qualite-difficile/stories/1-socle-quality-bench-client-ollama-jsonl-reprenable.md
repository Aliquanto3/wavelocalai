---
title: 'Socle : paquet quality_bench, client Ollama natif, JSONL reprenable, arrêt propre'
type: 'feature'
created: '2026-10-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'cba5aa630dbd362385da45942a48dce58f5c6ae5'
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/campagne-et-reprise.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le banc de qualité difficile (stories 2 à 10) n'a pas de socle : ni paquet, ni écriture JSONL qui survive à un arrêt brutal, ni manifeste qui bloque une reprise incohérente, ni client Ollama dont les requêtes soient entièrement fixées. Sans lui, chaque phase réinventerait clés, empreintes, verrous et reprise, de façons divergentes.

**Approach:** Créer le paquet `scripts/quality_bench/` avec sa coquille `common/` (JSON canonique, JSONL ajout seul + reprise, manifeste `qb.manifest/1`, verrous, arrêt, veille, chemins, configuration de campagne, schémas) et le client `ollama/` sur l'API native. Le tout est testé sans Ollama ni réseau, dans un venv dédié `.venv-quality`. Règles du spine appliquées : AD-1, AD-2, AD-4, AD-8, AD-9, AD-12, AD-13.

## Boundaries & Constraints

**Always:**
- Identifiants en anglais ; docstrings, journaux et messages d'erreur en français. Tout `open()` texte en `encoding="utf-8"`.
- Seul import de `src/` : `from src.core.telemetry import disable_telemetry`, appelé en tête de `__main__.py`.
- Seul `common/canonical.py` sérialise en JSON canonique et calcule les empreintes ; seul `common/jsonl.py` lit et écrit les JSONL ; seul `common/config.py` lit les YAML ; seul `common/schemas.py` définit les schémas de ligne et de manifeste ; seul `ollama/client.py` construit les requêtes à Ollama.
- Chaque requête `/api/chat` fixe `options.seed`, `options.temperature = 0`, `options.num_ctx`, `options.num_predict` et `format` (schéma ou `null` explicite), en streaming. URL de base limitée à `localhost` ou `127.0.0.1`.
- Dépendances déclarées par bornes inférieures vérifiées sur PyPI le 2026-10-11 ; installées seulement dans `.venv-quality`.

**Never:**
- Modifier `scripts/benchmark_slm.py`, `src/core/` (dont `config.py`), `benchmarks/`, `.venv` ou `.venv-app` ; importer la bibliothèque `ollama`, `httpx` ou `/v1`.
- Redémarrer Ollama, écrire une ligne quand le service reste absent, ou transformer une panne de service en statut `error`.
- Écrire dans `data/` réel pendant les tests (fixture `autouse` sur `tmp_path`) ; exiger Ollama, une clé d'API ou le réseau dans un test.
- Coder le runner de génération, le préflight, les questions, la correction ou le juge (stories 2 à 7).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Reprise après arrêt brutal | processus tué en pleine écriture | à la réouverture, fragment final sans `\n` tronqué physiquement et journalisé ; clés présentes sautées ; série complétée sans doublon ni trou | N/A |
| Lecture seule | `read_jsonl` sur fichier à fragment final | fragment ignoré, fichier intact | autre ligne illisible : exception avec le numéro de ligne |
| Clé déjà présente | `append` d'une clé existante | rien n'est écrit | `DuplicateKeyError` |
| Manifeste différent | reprise avec `blocking.models_resolved[3].digest` modifié | reprise refusée | `ManifestMismatchError` nommant `blocking.models_resolved[3].digest` |
| Manifeste informatif différent | autre version de Python | reprise acceptée | N/A |
| Schéma inconnu | ligne `qb.generation/2` | refus | `UnknownSchemaError` |
| Verrou occupé | second processus sur le même verrou | refus immédiat, PID et heure du détenteur affichés à titre indicatif | `LockBusyError` |
| Arrêt propre | SIGINT ou fichier `STOP` pendant une unité | drapeau levé, lu entre deux unités ; `STOP` supprimé à la sortie | `STOP` présent au lancement : supprimé et journalisé |
| Panne d'Ollama | connexion refusée ou 5xx | `OllamaUnavailableError` ; `wait_for_ollama` sonde `/api/version` jusqu'à `ollama_wait_s` | service toujours absent : `OllamaGoneError` ; autre version au retour : `OllamaVersionChangedError` |
| Capacité absente | `think` ou `tools` sans la capacité déclarée | aucune requête envoyée | `ValueError` |
| URL distante | base URL hors `localhost`/`127.0.0.1` | client non construit | `ValueError` |

</frozen-after-approval>

## Code Map

- `src/core/telemetry.py` -- `disable_telemetry()` (charge le `.env` par `python-dotenv`) : seul import permis de `src/`. Ni `src/` ni `src/core/` n'ont d'`__init__.py` : paquets namespace, importables depuis la racine.
- `scripts/` -- pas d'`__init__.py` : `python -m scripts.quality_bench` passe par un paquet namespace ; ne pas en ajouter un à `scripts/`.
- `tests/unit/test_telemetry.py:271` -- `test_every_telemetry_importer_is_listed` scanne `scripts/**/*.py` : la story 1 n'importe aucune bibliothèque de `TELEMETRY_ROOTS`, donc rien à y ajouter.
- `pytest.ini` -- `testpaths = tests`, `--strict-markers`, marqueurs `integration`, `e2e` ; `asyncio_mode` sera un avertissement sans pytest-asyncio dans `.venv-quality`, sans conséquence. Un `pytest tests/` lancé depuis `.venv` ou `.venv-app` collecte `tests/quality_bench/` : le `conftest.py` doit l'ignorer si `httpx2`, `yaml` ou `jsonschema` manquent.
- `tests/__init__.py` existe : pytest insère la racine du dépôt dans `sys.path` (mode prepend), `scripts.quality_bench` et `src.core` sont donc importables.
- `.gitignore` -- `data/` (couvre `data/quality_bench/`), `*.log`, `lib/`, `.venv/`, `.venv-app/` déjà présents ; ajouter `.venv-quality/`.
- `.pre-commit-config.yaml` -- hooks black, isort, ruff, detect-secrets sans `exclude` propre : y ajouter les exclusions demandées.
- `pyproject.toml` -- black/ruff ligne 100, cible `py310`, règles ruff `E,W,F,I,N,UP,B,C4,SIM`.
- Machine : la tour (Ollama 0.40.2 installé, `py` ne propose que Python 3.14).

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/requirements.txt` -- `httpx2>=2.13.1`, `pyyaml>=6.0.3`, `jsonschema>=4.26.0`, `python-dotenv>=1.2.4`, `pytest>=9.1.1`, avec la date de vérification -- dépendances du socle seul ; chaque story ajoute les siennes.
- [x] `.gitignore`, `.pre-commit-config.yaml` -- `.venv-quality/` ignoré ; `exclude: ^benchmarks/quality/` sur detect-secrets ; `exclude: ^scripts/quality_bench/grading/vendored/` sur black, isort et ruff -- convention « Dépôt » du spine.
- [x] `scripts/quality_bench/__init__.py`, `__main__.py` -- `disable_telemetry()` puis CLI `argparse` qui reconfigure la console en UTF-8 ; sous-commandes enregistrées par les stories suivantes, `--help` fonctionnel -- AD-1.
- [x] `scripts/quality_bench/common/canonical.py` -- `canonical_bytes(obj)`, `sha256_hex(obj)`, `nfc(text)`, `utc_now()` (ISO 8601 `Z` à la seconde) ; refus des flottants non finis -- AD-4.
- [x] `scripts/quality_bench/common/paths.py` -- racine `$QUALITY_BENCH_DATA` (défaut `<racine du dépôt>/data/quality_bench`), chemins de campagne, de jugement, de `machine.lock`, de `STOP` -- AD-2.
- [x] `scripts/quality_bench/common/logs.py` -- `setup_logging(command, log_path)` : fichier `log-<commande>.log` + console, UTF-8 -- convention « Journal ».
- [x] `scripts/quality_bench/common/locks.py` -- `FileLock` (contexte) : `msvcrt.locking` sous Windows, `fcntl.flock` ailleurs, non bloquant ; PID et heure écrits à titre d'information ; `LockBusyError` -- AD-12.
- [x] `scripts/quality_bench/common/jsonl.py` -- `read_jsonl(path)` en lecture seule ; `open_for_append(path, lock)` qui exige le verrou détenu, tronque le fragment final, charge les clés, et renvoie un écrivain dont `append(record)` écrit une ligne canonique + `\n`, `flush` puis `os.fsync`, et lève `DuplicateKeyError` -- AD-2, AD-12.
- [x] `scripts/quality_bench/common/schemas.py` -- schémas JSON (`jsonschema`, `additionalProperties: false`) de `qb.manifest/1` et `qb.generation/1` exactement comme AD-8 et AD-7 ; `validate(record)` lit `schema`, refuse un `<n>` inconnu -- AD-7, AD-8.
- [x] `scripts/quality_bench/common/config.py` -- `load_campaign(path)` : YAML de campagne, valeurs par défaut d'AD-8 appliquées (`request`, `caps`, `num_ctx_tiers`, `max_attempts=3`, `max_consecutive_errors=5`, `ollama_wait_s=600`, `max_tool_calls_per_turn=8`, `selection=null`), clés inconnues refusées, `generation_hash` sur la section résolue -- AD-8.
- [x] `scripts/quality_bench/common/manifest.py` -- `harness_hash()` (contenu des `.py` de `common/`, `ollama/`, `generation/`, `envs/` existants, triés par chemin relatif, fins de ligne normalisées) ; `machine_label()` ; `build_manifest(...)` ; `ensure_manifest(path, manifest)` : écrit au premier lancement, sinon compare `blocking` et lève `ManifestMismatchError` avec le chemin JSON du premier champ différent -- AD-8.
- [x] `scripts/quality_bench/common/stop.py` -- `StopFlag` : gestionnaire SIGINT qui lève un drapeau, `should_stop()` lit aussi le fichier `STOP`, suppression au lancement (journalisée) et à la sortie -- AD-13.
- [x] `scripts/quality_bench/common/keepawake.py` -- contexte `keep_awake()` : `SetThreadExecutionState(0x80000000|0x1|0x2)` à l'entrée, `0x80000000` dans le `finally` ; sans effet hors Windows -- AD-13.
- [x] `scripts/quality_bench/ollama/client.py` -- `OllamaClient(base_url, transport=None)` sur `httpx2.Client` : `version()`, `show(model)`, `tags()`, `ps()`, `chat(...)` en streaming (agrège `content`, `thinking`, `tool_calls`, compte les fragments par champ, rend `done_reason`, `prompt_eval_count`, `prompt_eval_cached_count`, `eval_count`, durées), `unload(model)` (`keep_alive: 0`) ; exceptions `OllamaUnavailableError` ; `wait_for_ollama(client, wait_s, expected_version)` -- AD-9, AD-13.
- [x] `tests/quality_bench/` -- `__init__.py`, `conftest.py` (`collect_ignore_glob` avec message si dépendances absentes, fixture `autouse` `QUALITY_BENCH_DATA`, marqueur `integration` sauté sauf `QUALITY_BENCH_INTEGRATION=1`), `samples/append_loop.py` (écrivain de test), un fichier de test par module -- couvre la matrice I/O.

**Acceptance Criteria:**
- Given `.venv-quality` créé avec `scripts/quality_bench/requirements.txt`, when on lance `.venv-quality\Scripts\python -m pytest tests/quality_bench`, then tous les tests passent sans Ollama ni réseau.
- Given un sous-processus qui écrit des clés `0..N` par `open_for_append`, when il est tué (`kill`) en cours de route puis relancé, then le fichier contient exactement `N+1` lignes valides, clés toutes distinctes.
- Given une requête construite par `chat(...)` interceptée par `httpx2.MockTransport`, when on lit son corps, then `stream`, `options.seed`, `options.temperature == 0`, `options.num_ctx`, `options.num_predict` et la clé `format` sont présents, et `think` / `tools` n'y figurent que si la capacité est passée.
- Given les modules du paquet, when on analyse leurs imports (AST), then aucun n'importe `scripts.benchmark_slm`, `src.*` hors `src.core.telemetry`, `ollama`, ni `httpx`.
- Given `python -m scripts.quality_bench --help` depuis la racine dans `.venv-quality`, then la commande sort avec le code 0.
- Given le scan AST de télémétrie (`tests/unit/test_telemetry.py::test_every_telemetry_importer_is_listed`), when on le lance dans `.venv-quality` (la tour n'a pas de venv d'app), then il passe.

## Implementation Notes

- **Versions installées** dans `.venv-quality` (Python 3.14.6, le 2026-10-11) : httpx2 2.13.1 (httpcore2 2.13.1), PyYAML 6.0.3, jsonschema 4.26.0, python-dotenv 1.2.4, pytest 9.1.1. Bornes vérifiées par `pip index versions` : ce sont les dernières publiées.
- **Verrous Windows :** `msvcrt.locking` porte sur un octet à l'offset `0x7FFFFFFE`, loin après le texte `pid=… started_at=…` : les verrous Windows étant impératifs, un second processus peut ainsi lire le PID du détenteur. Le fichier de verrou n'est jamais supprimé (vidé à la libération).
- **Lanceur du venv :** sous Windows, `.venv-quality\Scripts\python.exe` crée l'interpréteur réel comme processus enfant. Les tests d'arrêt brutal tuent donc le PID affiché par `samples/append_loop.py` (`ready <pid>`), puis attendent que le système libère le verrou (`tests/quality_bench/processes.py`).
- **Choix non dictés par la spec :** `unload()` passe par `POST /api/generate` (`keep_alive: 0`, sans prompt) pour qu'aucune requête `/api/chat` n'échappe à la règle des options fixées ; un modèle qui déclare `thinking` exige un `think` explicite ; la capacité `decision` refuse le chat ; un fragment de flux illisible ou `{"error": …}` dans le flux est une `OllamaRequestError` (bornée par `max_attempts`), pas une panne ; `httpx2.Client(trust_env=False)` pour qu'aucun proxy de l'environnement ne fasse sortir la requête.
- **Configuration :** pour chaque piste listée d'un modèle, la clé `think_off` / `think_on` est obligatoire (`null` permis) ; `tag`, `family`, `tracks`, `num_ctx_max` sont obligatoires ; `temperature` autre que 0 est refusée ; clés YAML en double refusées.
- **Schémas :** le type `integer` refuse `1.0` et les booléens (AD-4). Les messages de `output` sont fermés par rôle (`assistant` : `content`, `thinking`, `tool_calls` ; `tool` et `user` : `content`), exactement comme l'exemple d'AD-7 : un champ `tool_name` côté outil exigera `qb.generation/2` ou un amendement avant la première campagne.
- **CLI :** les sous-commandes s'enregistrent dans `SUBCOMMANDS` de `__main__.py` (nom, aide, configuration du sous-analyseur, fonction d'exécution) ; sans sous-commande, l'aide s'affiche et le code est 2.

## Spec Change Log

## Review Triage Log

Passe 1 (2026-10-11) : Blind Hunter (B), Edge Case Hunter (E), Verification Gap (V).

| # | Constat | Verdict | Preuve | Route |
|---|---------|---------|--------|-------|
| V1 | Troncature du fragment final jamais testée au-delà d'un bloc de 64 Kio | medium | Pré-vérifié : les fichiers des trois tests tiennent dans un bloc ; une régression de la boucle arrière effacerait toutes les lignes sans échec. | patch |
| V2 | `tests/quality_bench` hors CI ; branche `fcntl` jamais exécutée | medium | Pré-vérifié : `tests.yml` tourne sur les PR vers `master` mais ne lance que `tests/unit tests/app`. Le spine exclut la CI et la SPEC toute autre machine que la tour. | defer |
| V3 | `check_id` lève `ValueError`, pas `ConfigError`, dans `load_campaign` | low | `config.py` appelle `check_id` sur le nom de fichier, `set` et `grading.judge` : l'erreur échappe à un `except ConfigError`. | patch |
| V4 | Écueil d'AGENTS.md « CI seulement sur main et develop » périmé | medium | `tests.yml:3-7` se déclenche sur `master` depuis 8dfc946. Fichier de contexte d'agent. | defer |
| B1 | `ollama_env` recopie tout `OLLAMA_*`, secrets compris, dans le manifeste ; detect-secrets exclu de `benchmarks/quality/` | low | Le manifeste vit dans `data/` (ignoré), mais une clé ou un hôte à identifiants serait exporté tel quel si la story 6 publie `informative`. Masquage par nom : correction directe. | patch |
| B2 / E1 | `append` reste utilisable après un échec d'écriture ou de `fsync` | medium | `jsonl.py` : l'exception laisse un fragment, puis la ligne suivante s'y colle ; `open_for_append` refuse ensuite le fichier (ligne illisible au milieu). | patch |
| B3 / E2 / E3 / E-claim | `open_for_append` accepte n'importe quel verrou détenu, sans revérifier ensuite | medium | `jsonl.py` ne teste que `lock.held` : `machine.lock` ou le verrou d'une autre campagne passent, et l'écrivain continue après libération. | patch |
| B4 / E-500 | `ReadTimeout` et 5xx d'un service vivant classés en panne : `wait_for_ollama` rend aussitôt la main, nouvel essai sans borne | maybe-false (medium si vrai) | Le dommage dépend de la politique du runner (story 5) : dire si une panne non confirmée par `/api/version` compte dans `max_attempts`. | defer |
| B5a | Journalisation depuis le gestionnaire SIGINT (réentrance du flux) | low | `stop.py` : `request_stop` appelle `logger.warning` dans le gestionnaire ; risque `RuntimeError: reentrant call` sur stderr. | patch |
| B5b / E-sig2 | Un second Ctrl+C ne force pas la sortie | medium | Avec un délai de lecture de 900 s, l'opérateur n'a que `taskkill`. La reprise tolère la perte de la question en cours. | patch |
| B5c | SIGTERM, SIGBREAK, fermeture de console non gérés | low | Hors AD-13 (SIGINT et STOP) ; garde supplémentaire, rarement atteint. | reject |
| B6 | Registre `SUBCOMMANDS` inopérant si une story l'alimente par import | low | `python -m` exécute le fichier sous `__main__` : un import de `scripts.quality_bench.__main__` crée un autre objet module. Préciser la règle dans le module. | patch |
| B7 | `ensure_manifest` réécrit un manifeste absent même si le JSONL a des lignes ; verrou non vérifié | low | Il faut qu'on supprime `manifest.json` à la main, et chaque ligne porte l'empreinte de son `blocking` (AD-8, contrôlée au rapport, AD-17). Le correctif ajoute des paramètres. | reject |
| B8 | Différences d'`informative` perdues à la reprise | low | `ensure_manifest` rend l'existant sans trace du nouveau ; un journal WARNING suffit. | patch |
| B9 | `harness_hash` ne couvre que les `.py` | medium | AD-8 dit « contenu » des quatre dossiers : des données de `envs/` (story 4) changées ne bloqueraient pas la reprise. | patch |
| B10 | Constats d'API relevés sur le source 0.40.3, tour en 0.40.2 | low | Notes de conception et Deferred du spine citent 0.40.3 sans le dire. Préciser dans le spine. | patch |
| B11 | Aucun test d'intégration contre un vrai Ollama | low | Non demandé par la story ; le marqueur est prêt. Hypothèses (déchargement, `prompt_eval_cached_count`) à vérifier au runner (story 5) ou au pilote. | reject |
| B12 | `check_id` accepte `CON`, `NUL`, un point final, des casses différentes | low | Identifiants par convention `pilot-AAAAMMJJ` ; garde supplémentaire. | reject |
| E-id | `check_id` accepte un saut de ligne final (`$` de `re.match`) | low | Vérifié : `_ID_RE.match("abc\n")` est vrai. `fullmatch` : correction directe. | patch |
| B13 | Valeurs par défaut dupliquées en littéraux dans `resolve_generation` | low | `3`, `5`, `600`, `8` répètent `DEFAULT_GENERATION` : une dérive changerait `generation_hash` sans bruit. | patch |
| B14 | `num_ctx_max` non comparé aux paliers, plafonds non comparés aux contextes | false | AD-9 et AD-7 écrivent `context_exceeded` pour un palier écarté ; `set_builder` (story 3) contrôle `num_ctx ≥ prompt × 1,25 + num_predict`. | reject |
| B15 | Pas de règles croisées dans `qb.generation/1` (`status`/`error`, `attempts` ≥ 1) | low | Seul le runner (story 5) écrira ces lignes ; règles `if/then` à ajouter, garde supplémentaire. | reject |
| B16 | Exceptions non journalisées dans le fichier, pas de codes de sortie dédiés | low | Aucune sous-commande n'existe encore ; à traiter avec la première (story 3 ou 5). | reject |
| B17 | Garde AST d'encodage aveugle à `Path.read_text()`, `write_text()`, `.open()` | low | Les stories suivantes liront du texte français par `read_text` : sans `encoding`, cp1252 sous Windows. Extension directe du test. | patch |
| B18 | Test d'arrêt brutal fragile (pause de 10 ms) | low | Sur un hôte lent, les 60 lignes peuvent finir avant le kill ; allonger la pause. | patch |
| B19 | `chunks["tool_calls"]` compte des appels, pas des fragments | low | `client.py` : `+= len(...)`, contraire au commentaire du champ. | patch |
| B20 | `conftest.py` ne vérifie pas `dotenv` | low | `__main__` importe `src.core.telemetry`, qui importe `dotenv` : tests de CLI en échec au lieu d'être ignorés. | patch |
| E-lock1 | Échec de l'écriture d'information après la prise du verrou : descripteur gardé | low | Improbable (fichier local fraîchement ouvert) ; garde supplémentaire. | reject |
| E-lock2 | Toute `OSError` du verrou présentée comme « verrou occupé » | low | Improbable sur disque local ; tri par `errno` à ajouter. | reject |
| E-awake | `keep_awake` imbriqué rétablit la veille trop tôt | low | Un seul appel par commande (AD-13). | reject |
| E-stop-prev | Gestionnaire SIGINT précédent `None` : `TypeError` à la sortie | low | Cas rare (gestionnaire posé hors Python), correction directe (`SIG_DFL`). | patch |
| E-stop-race | `STOP` supprimé entre `exists()` et `unlink()` au lancement | low | Correction directe (`missing_ok`). | patch |
| E-wait | `/api/version` qui pend : une sonde bloque jusqu'à 900 s | medium | `version()` hérite du délai de lecture de 900 s : `ollama_wait_s` peut être dépassé de 15 min. Délai court par requête. | patch |
| E-msg | Fragment de flux dont `message` n'est pas un objet | low | Hors protocole d'Ollama ; garde supplémentaire. | reject |
| E-empty | `messages` vide | low | Bug d'appelant (runner) ; garde supplémentaire. | reject |
| E-cfg-hash | Éléments non hachables dans `tracks` ou `ids` : `TypeError` brut | low | YAML improbable ; garde supplémentaire. | reject |
| E-cfg-key | Clé YAML complexe non hachable | low | Idem. | reject |
| E-think-empty | `think_on: ""` accepté par la configuration | low | Échoue bruyamment au chat (valeur non déclarée) ; garde supplémentaire. | reject |
| E-run-utf8 | Sortie non UTF-8 de `nvidia-smi` ou `git` : `UnicodeDecodeError` non rattrapé | low | `_run` décode en strict et ne rattrape que `OSError` / `SubprocessError` : un message d'erreur localisé en cp1252 bloquerait le lancement. `errors="replace"` : correction directe. | patch |
| E-dist | Distribution installée sans version | low | Improbable ; garde supplémentaire. | reject |
| E-path | Clé contenant `.` ou `[` : valeurs « absent » dans le message | low | Message seulement, chemin exact ; refonte de `first_difference`. | reject |
| E-proc | Enfant de test mort avant `ready` : erreur opaque | low | Diagnostic de test seulement. | reject |

## Design Notes

- **Cache de préfixe d'Ollama (Deferred du spine) :** aucun réglage par requête trouvé (ni `cache_prompt` dans `docs/api.md` ni dans `api/types.go`, Ollama 0.40.3 le 2026-10-11). `prompt_eval_cached_count` existe (`api.Metrics`, `omitempty`) : le client le lit et rend 0 s'il manque. Changer `num_ctx` recharge le modèle (`needsReload` compare les options par `reflect.DeepEqual`, `server/sched.go`), ce que la chauffe par couple (modèle, `num_ctx`) d'AD-14 absorbe. À consigner dans le Deferred du spine après la story.
- **`think` chaîne :** `/api/show` ne publie pas de liste de niveaux documentée. Le client accepte un booléen si `thinking` est déclaré, et une chaîne seulement si elle figure dans `allowed_think_values` fourni par l'appelant (vide par défaut, donc refusée).
- **Machine :** `machine_label()` = `QUALITY_BENCH_MACHINE` si défini, sinon le nom d'hôte. Le libellé `tour-rtx3050` s'obtient par la variable ; le manifeste bloque si l'un ou l'autre change.
- **Erreurs Ollama :** `httpx2.ConnectError`, `ReadTimeout` coupé avant `done`, ou statut 5xx → `OllamaUnavailableError` ; un 4xx est une erreur de requête (`OllamaRequestError`), propre à la question.
- **Python :** seul 3.14 est disponible sur la tour ; le code reste compatible 3.10 (pas de syntaxe postérieure).
- Exemple de premier champ différent : `blocking.models_resolved[3].digest`, `blocking.ollama_version` ; parcours en profondeur, clés triées, listes indexées, longueur différente signalée au premier indice manquant.

## Verification

**Commands:**
- `py -3.14 -m venv .venv-quality` puis `.venv-quality\Scripts\python -m pip install -r scripts/quality_bench/requirements.txt` -- expected : installation sans erreur ; versions relevées dans les notes.
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` -- expected : tout passe.
- `.venv-quality\Scripts\python -m scripts.quality_bench --help` -- expected : code 0.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -k every_telemetry_importer` -- expected : passe (pas de venv d'app sur la tour : `.venv` n'a que le banc de vitesse, sans Streamlit).
- `uvx ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx black@25.12.0 --check …`, `uvx isort@7.0.0 --profile black --check …` (versions des `rev` de `.pre-commit-config.yaml` ; pre-commit n'est pas installé) -- expected : vert.
