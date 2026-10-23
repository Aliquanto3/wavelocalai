# Revue de la spine d'architecture wavelocalai v2 (grille « bonne spine »)

Date : 2026-10-18. Relecture en lecture seule de `ARCHITECTURE-SPINE.md` contre `SPEC.md`, `contrat-api.md`, `pile-technique.md`, `etapes-et-criteres.md`, et contre le code existant (`pyproject.toml`, `pytest.ini`, `.github/workflows/tests.yml`, `src/app/launcher.py`, `AGENTS.md`).

## Verdict

Spine solide et bien ciblée (21 AD, paradigme clair, versions réelles), prête à 80 %. Quatre points hauts à corriger avant le découpage en epics : ordre d'effacement WAL/VACUUM, plafond de flux SSE, vec0 hors migrations, enveloppe opérationnelle (mise à jour du schéma, sauvegarde, journaux). S'y ajoutent des écarts de ratification de la CI et d'AGENTS.md.

## Vérifications techniques faites

| Affirmation | Résultat |
| --- | --- |
| `dev-mode-dirs = [".", "src"]` rend `import wavelocalai` possible en installation éditable, `import src.core` restant valide | Vrai. Testé (hatchling, `uv pip install -e`) : `import wavelocalai, src.core` passe. Effet de bord : `src/` entre dans `sys.path`, donc `core` et `app` deviennent aussi importables en top-level (risque de double import `core.x` / `src.core.x`). |
| Script `wavelocalai.__main__:main` résout avec ce montage | Vrai en éditable (testé, le script s'exécute). **Faux en non éditable** : avec `packages = ["src"]`, la roue contient `src/wavelocalai/...`, le module s'appelle `src.wavelocalai` et le script échoue (roue construite et inspectée). À écrire : installation éditable seulement (le lanceur v1 refuse déjà le cas), et `packages` à changer à la bascule. |
| `fastapi.sse.EventSourceResponse` natif | Existe en FastAPI 0.143.5 (`ServerSentEvent` avec `id`, `retry`, `comment`, `KEEPALIVE_COMMENT`). Un `204` impose de renvoyer une `Response` simple avant le flux : à couvrir par un test. |
| SSE `204` arrête la reconnexion d'`EventSource` | Vrai (WHATWG : une réponse 204 fait échouer la connexion, sans reconnexion). Mais le client doit aussi fermer l'`EventSource` sur `run_ended` ; sinon le flux d'un run fini se rejoue, se ferme, puis se reconnecte une fois pour rien avant le 204. Toute réponse non 200 (404 run inconnu) échoue aussi définitivement : à écrire. |
| SQLite WAL + un seul fil écrivain avec asyncio | Principe sain, mais le pont asyncio n'est pas décidé (voir F-8). |
| Versions de la pile (FastAPI 0.143.5, uvicorn 0.54.0, pydantic 2.14.1, ollama 0.6.3, sqlite-vec 0.1.9, ecologits 0.11.3, fastembed 0.9.0, SQLite 3.53.1) | Vérifiées : toutes résolvent par `uv pip install --dry-run`, SQLite 3.53.1 confirmé, `enable_load_extension` disponible. `fastapi==0.143.5 crewai chromadb` se résout sans conflit. `llm_impacts` existe avec la signature `(provider, model_name, output_token_count, request_latency, electricity_mix_zone)` : l'AD-11 écrit d'autres noms de paramètres (cosmétique, à aligner). « Python 3.11.17 » non revérifié. |

## Constats

### F-1 (haut) AD-13 : ordre `wal_checkpoint(TRUNCATE)` puis `VACUUM` incorrect
`VACUUM` réécrit toute la base en passant par le WAL : après lui, les pages réécrites restent dans `-wal` jusqu'au prochain checkpoint. Le test d'absence de texte dans le `-wal` échouerait. Un lecteur ouvert empêche aussi la troncature.
Correctif : `DELETE`, puis `VACUUM`, puis `wal_checkpoint(TRUNCATE)`, sur le fil écrivain et sans lecteur ouvert (pause brève du store), avec test sur les octets du `.db` et du `-wal` après l'opération. Dire ce que fait la règle si un run est actif (refuser ou attendre).

### F-2 (haut) AD-14 : le plafond de connexions SSE n'est pas tenu
Le texte dit prévenir la saturation des 6 connexions HTTP/1.1 par origine, mais la règle autorise un run actif par `kind` (8 types) plus `/api/system/stream` : jusqu'à 9 `EventSource` simultanés, et les `fetch` restent bloqués derrière. AD-20 impose « un seul client SSE » sans dire qu'il multiplexe.
Correctif : borner les flux ouverts par `core/sse.js` (par ex. 4 : système, runs de l'écran visible, une réserve) et faire passer la progression des runs d'arrière-plan (`ingest`, `pull`) par le flux système, ou prévoir un flux multiplexé. Ajouter un test E2E qui lance plusieurs runs.

### F-3 (haut) Enveloppe opérationnelle incomplète
Décidé : environnement unique, installation, port, données, redémarrage, CI. Manquent :
- **Évolution du schéma entre versions** : migrations avant seulement, mais rien sur une base plus récente que le code (retour de `2.0.0a3` à `a2` : refuser de démarrer sans toucher à la base), ni sauvegarde avant migration (copie `VACUUM INTO`), ni politique des alphas (base jetable autorisée ? migrations regroupées avant la 2.0.0 ?). C'est la question qui fera le plus diverger les stories.
- **Sauvegarde et restauration** : aucune (ni export complet, ni consigne de copier `data/` base fermée). À décider ou à reporter explicitement.
- **Journaux** : seule la convention de contenu existe. Manquent niveau configurable, rotation, corrélation par `run_id`, et test que « Effacer » (AD-13) n'a rien à retrouver dans les journaux.
- **Reprise de la v1** : `pile-technique.md` prévoit « historique migré vers `runs` » (`read_app_emissions`) ; la spine n'en dit rien (décidé, reporté ou abandonné ?).
- **Arrêt propre** : à l'arrêt, le hub doit vider ses lots d'événements (AD-7) et les flux SSE ouverts bloquent l'arrêt gracieux d'uvicorn (`timeout_graceful_shutdown`). Un seul processus, un seul worker, pas de `--reload` : jamais écrit alors que le hub est en mémoire.
- **Second lancement** : port 8502 occupé, ou deuxième instance sur la même base (verrou de fichier ?).
- **Racine et chemins** : comment `__main__` retrouve `wavelocalai.toml` et `data/` (le lanceur v1 fait `chdir(ROOT)` pour cette raison).

### F-4 (haut) AD-16 contre AD-12 et AD-13 : tables `chunks_vec_<dim>`
- La table vec0 est créée à la volée par dimension, donc hors migration : contraire à « schéma modifié hors migration » et le test d'instantané de schéma devient instable. Décider : migrations qui créent les dimensions connues, ou exception écrite avec registre en table.
- Le `DELETE` en cascade (AD-13) ne traverse pas les tables virtuelles : supprimer un document laisse des vecteurs orphelins qui peuvent revenir dans les résultats. Le point est classé « Deferred » (« résidu vectoriel ») alors qu'il tranche le contrat de suppression de CAP-8. Une règle suffit : le dépôt `rag` supprime dans `chunks_vec_<dim>` par `rowid` dans la même transaction que les `chunks`, avec test.

### F-5 (moyen-haut) Ratification de la CI, de `pyproject` et d'AGENTS.md
- AGENTS.md dit « Viser Python 3.10+ » et la matrice CI v1 a 3.10 : AD-1 les contredit sans prévoir leur mise à jour (le premier lot touche déjà AGENTS.md : y ajouter la ligne).
- Le job v1 installe par `pip install -r requirements.txt -c constraints.txt` (généré par `uv pip compile --universal`) : changer `requires-python` oblige à les régénérer, marqueurs `onnxruntime` de `pyproject` compris. Absent de la spine, ainsi que de savoir si les dépendances v2 y entrent.
- La condition Codecov `python-version == '3.10'` cesse de s'appliquer en retirant 3.10 : le téléversement s'arrête sans alerte. À déplacer sur 3.11 ou 3.12.
- Le job v2 `uv sync --locked` installe aussi toute la v1 (torch, chromadb, crewai : plusieurs Go sur trois OS). Décider un groupe de dépendances ou accepter le coût.
- E2E Playwright dans `tests/v2/e2e` : installation du navigateur en CI non décidée ; `pytest.ini` exclut `e2e` par défaut (`-m "not e2e"`) : dire quel job les lance.
- Configuration de test v2 : `pythonpath`, couverture (`--cov=src.core` en CI et `pyproject` ; la v2 aura `--cov=wavelocalai`), cibles `py311` de ruff et black : AD-1 ne cite que ruff et black, pas `[tool.coverage]`.
- Politique AGENTS.md sur le banc : un changement de `requires-python` ou de la version d'`ollama` dans `pyproject` touche l'environnement du banc ; prévoir une PR dédiée, comme pour `src/core/`.
- AD-3 : « un correctif v1 part avec la préversion suivante » contredit la spec (« maintenance stricte 1.3.x ») et rend la release `latest` GitHub ambiguë ; CITATION.cff à tenir à jour.

### F-6 (moyen) Diagramme de couches contre ses propres routes
`web` n'a de flèche que vers `services` et `runs`, mais `/api/models`, `/api/system/*`, les conversations et `/api/carbon/*` demandent `models/`, `hardware/`, `greenops/`, `store/`. Le test AST d'AD-4 « vérifie le diagramme » : il échouera dès la première route, ou on l'assouplira au cas par cas. Tracer les flèches `web` vers ces paquets (ou un service de lecture). De même `models --> store` (cache `model_facts`) contredit « un adaptateur n'écrit pas en base » : réserver l'accès `store` au registre.

### F-7 (moyen) Règles sans mécanisme de contrôle ou ambiguës
- AD-9 (« seul moyen d'obtenir un `ChatModel` ») et AD-8 (pas de base, pas de `allow_cloud`, pas de CO₂ dans les adaptateurs) : ajouter au test AST que seul `registry.py` importe les adaptateurs et que ceux-ci n'importent ni `store` ni `greenops`.
- AD-18 (masquage de clé) et AD-20 (« aucune mesure recalculée dans le navigateur ») : aucun contrôle ; prévoir un test qui injecte une fausse clé dans une erreur, et une recherche de motifs dans `static/`.
- AD-19 : ajouter une en-tête `Content-Security-Policy: default-src 'self'` qui fait respecter « aucune requête hors de `127.0.0.1` » par le navigateur ; accepter ou refuser `[::1]` par écrit.
- AD-14 : « un run actif par `kind` » ne dit pas si les runs enfants comptent ; un enfant de l'Arène de kind `chat` se heurterait au 409 du chat. Écrire « s'applique aux runs racines ».
- AD-6 : `lane` = tag du modèle entre en collision dans une équipe d'agents qui utilise le même modèle pour plusieurs agents ; définir `lane` pour `agent` et `eval`. « Token groupé par tranches de 50 ms » doit exempter le premier token (CAP-5 : premier token dès réception).
- AD-10 : `allocation: prorata_tokens` n'a pas de règle de déclenchement ; l'hypothèse de la spec (cloud en parallèle d'un local mesuré) recoupe mal AD-11 (tracker par run feuille local sous sémaphore). Écrire quand le prorata s'applique.
- AD-5/AD-14 : un `approval_required` (D2) laisse un run `agent` actif indéfiniment et bloque tout autre run `agent` (409). Prévoir délai d'expiration ou statut `waiting_approval` non actif.

### F-8 (moyen) AD-12 : détails qui feront diverger les stories
- Pont asyncio vers le fil écrivain : `ThreadPoolExecutor(max_workers=1)` ou fil dédié avec file ? Imposer une interface (`await store.write(fn)` qui exécute une fonction entière dans une transaction), car une transaction ne peut pas franchir un `await`.
- En `sqlite3` Python, `executescript` valide implicitement ; « migration dans une transaction » demande `isolation_level=None` et `BEGIN` explicite.
- Chaque connexion de lecture doit charger sqlite-vec (`enable_load_extension`, absent de certains Python système) : dire que seul le Python fourni par uv est supporté.
- `busy_timeout` et `synchronous=NORMAL` à fixer.
- AD-7 : rejeu pendant le passage mémoire vers base (libération après écriture finale) : définir la bascule sans trou ni doublon. Au redémarrage, un run `interrupted` n'a pas de `run_ended` en base : le rejeu doit en fabriquer un, et la perte possible de 1 s d'événements est à documenter.

### F-9 (moyen) Budgets de la spec sans AD
Aucun AD ne décide : cache et délai de l'état d'Ollama (« aucune route de lecture > 300 ms Ollama arrêté », « Ollama ne répond pas en < 3 s »), repli du catalogue quand Ollama est arrêté, absence de GZip sur les flux SSE, en-têtes de cache des fichiers statiques, taille du pool de threads. `pile-technique.md` les mentionnait, la spine ne les reprend pas.

### F-10 (bas) Cohérence des documents
- `contrat-api.md` garde `model_loading/model_loaded`, `tps_estimated`, `local|ecologits|unknown` ; la spine déclare sa priorité sans lister les correspondances (LoadState vers `model_loading`, `tps_source` vers `tps_estimated`). Ajouter le tableau, ou mettre à jour le contrat avant les stories.
- `pile-technique.md` garde une table `jobs` et une table `models` que la spine supprime (AD-5) sans que le fichier soit corrigé.
- Le kind `bench` voisine avec `benchmarks/` et le principe « l'app ne produit pas de banc » ; renommer `format_check`.
- La borne `<3.13` vient de la v1 (torch, chromadb), pas de la v2 : l'écrire pour que la bascule la relève.
- Clés obligatoires de `wavelocalai.toml` / `.env` et validation au démarrage (échec lisible) non décrites.

## Couverture CAP-1 à CAP-14
Tous les CAP ont une ligne dans la carte. Points faibles : CAP-10 (« Sur d'autres postes » dépend d'un schéma différé, acceptable avant l'étape 5) ; CAP-11 (approbations, restriction des chemins des outils, format d'appel d'outil différés à l'étape 6, acceptable car une seule story, mais la forme du run en attente d'approbation est à décider maintenant, voir F-7) ; CAP-13 (« hérité de la spec » : rien sur le chemin de `benchmarks/slm-quality/`, son absence ou sa version) ; CAP-14 (sort de `packages = ["src"]`, de `requirements.txt` et des tags v1 à la bascule non décidé).

## Éléments différés pouvant faire diverger deux unités
- Résidu vectoriel de vec0 (F-4) : à promouvoir en règle.
- Liste des codes d'erreur : chaque story ajoute les siens ; risque de doublons ou de noms divergents. Imposer un préfixe par module et un test d'unicité.
- Détail des colonnes : acceptable si une règle fixe les noms des colonnes communes (`id`, `created_at`, `run_id`, `co2_*`).

## Points forts
Paradigme et diagramme lisibles ; unicité du run et du point de contrôle cloud ; `ts`, identifiants et unités fixés ; refus de `EcoLogits.init()` ; versions réelles ; E2E avec faux modèle ; Deferred honnête sur `qb.results/1`.
