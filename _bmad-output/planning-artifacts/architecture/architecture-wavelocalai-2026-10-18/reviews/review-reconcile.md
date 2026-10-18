# Revue de réconciliation : spine d'architecture contre spec, compagnons et 03-ux-front §3.2 à §3.10

Périmètre : `ARCHITECTURE-SPINE.md` lu contre `SPEC.md`, `pile-technique.md`, `contrat-api.md`, `etapes-et-criteres.md` et `docs/audits/refonte-2026-10/03-ux-front.md` §3.2 à §3.10. Ne sont retenus que les écarts sur lesquels un développeur qui suit la spine peut se tromper. Ce que la spec couvre seule et que la spine n'a pas à répéter est écarté.

Verdict : la spine est solide sur les structures (runs, SSE, port, store), mais elle laisse tomber plusieurs exigences silencieuses de confidentialité, de performance et de sémantique d'Arène. Deux de ses règles contredisent les entrées sans le dire. Une dizaine d'ajouts d'une ligne chacun suffisent à les corriger.

## A. Contradictions non assumées (la spine dit autre chose que les entrées)

### A1. Haute. « Effacer efface » ne couvre pas les copies de texte dans `run_events`, `sources` et les résultats d'Arène
- Entrées : SPEC (Constraints) : « Effacer » efface réellement ; CAP-8 : suppression d'un document seul.
- Spine : AD-13 ne cascade que conversation et document. Or l'événement `sources` (contrat) porte `text`, l'extrait entier. Il est rejoué depuis `run_events`. Les runs d'Arène n'ont pas de `conversation_id` et contiennent prompt et réponses. Les `messages.reasoning` et les appels d'outils sont aussi des copies.
- Risque : supprimer un document laisse son texte dans `run_events` et dans le `-wal`. Le test d'AD-13 ne le verrait que s'il cherche le bon texte.
- Correctif : étendre AD-13. Supprimer un document purge les `run_events` `sources` et les `messages` qui le citent, ou on ne stocke pas `text` dans `sources` (référence `chunk_id` seulement, texte relu à l'affichage). Ajouter « effacer un résultat d'Arène ou d'évaluation » et une rétention des `run_events`. Le test d'AD-13 couvre ces tables.

### A2. Haute. Un run `interrupted` au redémarrage n'a pas de `run_ended` : rejeu sans fin
- Entrées : contrat : `run_ended.status` ∈ {ok, error, cancelled} ; 03 §3.6 : « Serveur redémarré : message + Recharger ».
- Spine : AD-5 passe les runs non terminés à `interrupted` ; AD-6 exige `run_ended` en dernier et une seule fois, et un `Last-Event-ID` inférieur au dernier `seq` rejoue. Rien ne dit qu'un `run_ended` est écrit pour un run interrompu, ni quel statut il porte.
- Risque : un client qui rouvre un run interrompu reçoit des événements sans fin, ne reçoit pas le `204`, et l'`EventSource` se reconnecte en boucle (le piège même qu'AD-6 veut éviter). De plus `interrupted` est à la fois un statut de run (spine) et un code d'erreur (03 §3.8 : Ollama a coupé, relance automatique une fois). Les deux sens se confondent.
- Correctif : AD-5 et AD-6 écrivent un `run_ended` synthétique (`status = interrupted`, `error.code = server_restarted`) avec le `seq` suivant, au démarrage. Étendre l'énumération du contrat. Renommer le code d'erreur d'Ollama (`generation_interrupted`).

### A3. Moyenne. « Aucun téléchargement à l'exécution » (spec, étape 1, tableau Exploitation de la spine) contredit AD-17 et le run `pull`
- Entrées : SPEC : « ni Node ni téléchargement à l'exécution » ; étape 1 : même critère.
- Spine : le tableau Exploitation répète « aucun téléchargement à l'exécution », mais AD-17 télécharge le modèle fastembed sur action explicite, et le run `pull` installe des modèles Ollama.
- Risque : un développeur prudent bloque le pull, ou un autre ajoute un téléchargement implicite (Hugging Face) en pensant qu'AD-17 l'autorise.
- Correctif : une phrase. La règle vise l'installation de l'app et l'absence de requêtes silencieuses ; les téléchargements de modèles sont explicites, déclenchés par l'utilisateur, et la requête vers Hugging Face est annoncée. Vérifier que l'E2E « aucune requête hors `127.0.0.1` » vise le navigateur, pas le serveur.

### A4. Moyenne. La mesure CO₂ par run feuille contredit l'hypothèse de la spec sur l'Arène mixte
- Entrées : SPEC (Assumptions) : « avec cloud en parallèle, CO₂ mesuré sur l'ensemble et réparti au prorata des jetons, en le disant ».
- Spine : AD-11 mesure chaque run feuille local sous le sémaphore, un tracker à la fois. AD-10 garde `allocation: prorata_tokens`, mais aucune règle ne dit quand il s'applique (jamais pour un local mesuré seul ?).
- Risque : deux lectures, avec ou sans répartition ; l'export dit « prorata » ou non au hasard.
- Correctif : trancher dans AD-10 ou AD-11. Soit `prorata_tokens` n'existe plus (la spine remplace l'hypothèse de la spec, à écrire), soit on dit quel cas l'emploie.

### A5. Moyenne. AD-2 conserve toutes les dépendances de la v1 jusqu'à la bascule, mais la spec promet une v2 sans elles
- Entrées : SPEC : « sans LangChain, … Chroma, sentence-transformers ni torch », succès : `uv sync` seul sur un PC de 16 Go ; pile : gain de 1,8 Go.
- Spine : un seul `pyproject` et un seul `uv.lock`, les dépendances de la v1 sortent à la bascule. Pendant les étapes 1 à 7, `uv sync` installe torch et les 4 librairies instables.
- Risque : le « Success signal » et les budgets (premier rendu, installation) se mesurent sur un environnement alourdi ; un import accidentel de torch passe. AD-4 teste les imports lourds mais pas l'absence des bibliothèques interdites dans `wavelocalai`.
- Correctif : dire que ces garanties valent après la bascule pour l'environnement, mais dès l'étape 1 pour le code. Étendre le test AST d'AD-4 aux imports interdits (langchain, crewai, chromadb, torch, ragas, sentence_transformers).

### A6. Moyenne. La spine déclare `03-ux-front.md §3` contrat du front alors que la spec le déclare « traçabilité seulement »
- Entrées : SPEC (en-tête) : la spec et ses `companions` forment le contrat, les sources ne servent qu'à la traçabilité. `03` n'est qu'une source.
- Spine (Deferred) : « `03-ux-front.md` §3 sert de contrat front ».
- Risque : les exigences silencieuses du §3.6 à §3.10 (voir C ci-dessous) n'ont aucun statut. Un lot peut les ignorer en citant la spec.
- Correctif : rendre le statut explicite, ou mieux, créer un compagnon `exigences-front.md` qui recopie §3.6 à §3.10 sous forme de critères testables et l'ajouter à `companions`.

### A7. Moyenne. AD-1 (target `py311`, `requires-python >=3.11`) touche des fichiers que la politique du dépôt protège
- Entrées : AGENTS.md : on ne modifie `scripts/benchmark_slm.py` et `src/core/` que dans une PR dédiée au banc (le SHA de `benchmark_slm.py` est tracé) ; la cible black/ruff est `py310` ; `.venv-bench` ne se resynchronise jamais ; la CI v1 tourne de 3.10 à 3.12. SPEC : la v1 reste en maintenance stricte et ne reçoit pas de nouvelle fonctionnalité.
- Spine : AD-1 change la cible ruff/black de tout le projet dès le premier lot. Un reformatage ou une correction automatique `py311` modifie `scripts/benchmark_slm.py` ou `src/core/` et fausse les comparaisons sans alerte. Les machines de banc en 3.10 ne peuvent plus `git pull` vers un `requires-python` plus haut sans casse.
- Correctif : AD-1 précise que la cible `py311` ne s'applique qu'à `src/wavelocalai/` et `tests/v2/` (réglage par dossier), que le code v1 et le banc gardent `py310`, et que le changement de `requires-python` passe par la PR bench ou est annoncé aux machines de banc. AD-3 est à relire de la même façon : « un correctif v1 part avec la préversion suivante » contredit la spec (`1.3.x` pour les correctifs bloquants) sauf si la branche `maintenance/1.3` est créée, ce que la spine laisse conditionnel.

## B. Exigences silencieuses absentes de la spine

### B1. Haute. Sémantique de file de l'Arène : délai isolé, point de départ du délai, enfants et limite « un run par kind »
- Entrées : CAP-7 : locaux en séquence, cloud en parallèle, « un délai dépassé n'arrête pas les autres », « non évalué » n'est jamais 0 ; 03 : délai de 2 min, statuts en attente/chargement/génération/notation/terminé/délai dépassé/échec/arrêté ; `lane_status` (contrat).
- Spine : AD-14 pose un sémaphore pris par appel, ce qui donne bien la séquence des locaux. Mais :
  1. Rien ne dit où démarre le délai. S'il part à la création du run, les colonnes « en attente » expirent avant même de générer. Il doit démarrer après l'acquisition du sémaphore.
  2. Rien ne dit qu'un délai ou une erreur d'une colonne n'annule pas le parent ni les autres (`lane_status = timeout`, `failed`), alors que l'annulation par `asyncio` d'AD-8 se propage facilement à tout le groupe (`TaskGroup` interdit ici sans `return_exceptions`).
  3. AD-14 limite à un run actif par `kind`. Les runs enfants (un par appel de modèle) ont-ils un `kind` ? S'ils portent `chat`, une Arène en cours rend `409` au Chat. S'ils portent `arena`, ils se bloquent entre eux. La règle doit dire qu'elle ne compte que les runs racines.
  4. Le juge est un appel local de plus sous le même sémaphore ; son attente est `judging`.
  5. Le garde-fou mémoire (voir B3) doit passer avant chaque chargement séquentiel, et le sémaphore ne décharge pas le modèle précédent d'Ollama.
- Correctif : ajouter à AD-14 ou AD-5 : délai par feuille, démarré à l'acquisition du sémaphore (valeur de `wavelocalai.toml`, 2 min par défaut), erreur de feuille isolée en `lane_status` sans arrêt des autres, limite par `kind` sur les runs racines uniquement, énumération des statuts de `lane`, note jamais convertie en 0 (`score` nul).

### B2. Haute. CodeCarbon : « aucun réseau » et mesure hors du fil de requête perdus
- Entrées : pile : « CodeCarbon par run hors du fil de requête », « imports paresseux, aucun réseau, un échec n'arrête jamais l'appel » ; SPEC : tout local, pays et PUE dans `wavelocalai.toml`.
- Spine : AD-11 garde le tracker unique et l'absence d'exception, mais ne dit ni mode hors ligne, ni pays et PUE, ni le thread. Par défaut, CodeCarbon interroge un service de géolocalisation par IP et peut envoyer des données (API cloud).
- Risque : une requête sortante silencieuse vers un tiers dès le premier chat, en violation du « tout local » et d'une démo devant un client.
- Correctif : AD-11 impose le mode hors ligne (`OfflineEmissionsTracker` avec `country_iso_code`, PUE et réglages de `wavelocalai.toml`), aucune sortie réseau (sauvegarde API désactivée), `start`/`stop` dans le pool de threads, et un test qui interdit les sockets pendant une mesure. Ajouter les clés pays et PUE à AD-15.

### B3. Moyenne. Le garde-fou mémoire (`ram_guard`) n'a pas de place dans la spine
- Entrées : CAP-9, CAP-11, étapes 4 et 6 : « garde-fou mémoire garde la question et chiffre le besoin réel, modèle déjà chargé compris, propose un modèle plus petit ou décharger » ; 03 §3.8 : code `ram_guard`, « toute inférence ».
- Spine : `hardware/` et `fits` sont cités, aucune règle sur qui évalue le garde-fou ni quand. Le risque est de le placer dans le front (interdit par AD-20) ou seulement dans l'écran RAG.
- Correctif : un AD court. L'évaluation se fait côté service avant le sémaphore et avant le chargement de toute inférence locale ; l'échec renvoie `ram_guard` avec besoin, mémoire libre et issues, sans perdre la question (le message reste dans `messages`).

### B4. Moyenne. D2 (e-mail validé) est absent
- Entrées : SPEC D2 ; CAP-11 ; contrat : `approval_required` et `POST /api/runs/{id}/approvals/{approval_id}` ; étape 6 : outil décoché par défaut.
- Spine : aucune mention de D2, ni de l'attente d'approbation. Questions non traitées : le run attend sans timeout ? Il garde son `kind` actif et bloque les suivants (AD-14). Un redémarrage l'interrompt. Annuler pendant l'attente. Surtout, l'exécution de l'outil d'envoi doit être refusée côté serveur sans approbation enregistrée.
- Correctif : un AD « outils sensibles » : l'outil `send_email` ne s'exécute que si le hub a reçu l'approbation pour cet `approval_id` ; l'attente est annulable ; délai paramétrable ; l'outil est décoché par défaut et l'API refuse de l'activer sans le champ explicite. Le test d'API correspondant (D7).

### B5. Moyenne. Budgets de performance et « Ollama arrêté » sans règle de cache ni de délai
- Entrées : SPEC (Constraints) : changement d'écran < 150 ms, premier rendu < 1 s, aucune route de lecture > 300 ms Ollama arrêté ; pile : « délais courts et cache de l'état Ollama indisponible quelques secondes » ; CAP-1 : « Ollama ne répond pas » en < 3 s.
- Spine : le schéma d'exploitation dit que le registre se reconstruit avec « Ollama en direct ». Sans cache, `GET /api/models` et `/api/health` attendent le délai de connexion à chaque appel. Aucun budget n'est cité hors AD-21 (imports paresseux).
- Correctif : AD (ou ligne de la table de conventions) : client Ollama avec délai de connexion court (≤ 1 s) pour les lectures, état « indisponible » mis en cache quelques secondes, `/api/models` répond depuis `model_facts` et le catalogue quand Ollama est arrêté, aucune route de lecture n'appelle un SDK cloud. Ajouter un test de budget (route de lecture < 300 ms avec un Ollama simulé injoignable).

### B6. Moyenne. Redémarrage du serveur : détection côté client non définie
- Entrées : 03 §3.6 : `server_instance` change → « Le serveur a redémarré. Les exécutions en cours sont perdues. » + « Recharger » ; perte de connexion : message de la barre haute après 3 essais, reprise sans doublon.
- Spine : `instance_id` est généré à chaque démarrage, mais `GET /api/system/stream` n'indique pas qu'il le porte, et AD-6 n'attribue pas la détection. Le nom diffère aussi (`server_instance` / `instance_id`).
- Correctif : AD-6 précise que le premier événement du flux système et `/api/health` portent `instance_id` ; `core/sse.js` compare à la reconnexion et lève l'état « serveur redémarré » dans le store. Les 3 essais et le message appartiennent aussi à `sse.js`.

### B7. Moyenne. Preuve d'export de l'Arène : où et quand figer la fiche machine
- Entrées : CAP-7 : export CSV/Markdown avec fiche machine, version d'Ollama, digests, méthode CO₂, juge ; résultat rouvrable par URL.
- Spine : routes d'export par extension, `model_facts` (tag, digest) lié aux runs, `GET /api/system/identity` en lecture directe. Rien n'impose de figer la preuve dans le run au lancement.
- Risque : l'export est recalculé avec la machine et Ollama du moment, donc faux après une mise à jour ou sur un autre poste.
- Correctif : le parent de l'Arène stocke un instantané (fiche machine, version d'Ollama, digests des modèles, juge et critères, version du barème de prix) dans les données de `run_started`, et l'export ne lit que cela.

### B8. Moyenne. Verdict local/cloud, classement, matrice et barème de prix : qui calcule ?
- Entrées : CAP-7 : écart de note, coût pour 1 000 requêtes (table de prix datée dans `wavelocalai.toml`), CO₂, données restées sur le poste ; 03 : « Note peu fiable sous 4 milliards de paramètres actifs », badges « un seul juge ».
- Spine : AD-20 interdit au front de calculer une mesure, et le contrat n'a aucun événement de synthèse (ni classement, ni verdict). La table de prix ne figure dans aucun AD.
- Risque : chacun calcule dans le navigateur, ou personne.
- Correctif : un événement `arena_summary` (ou champ de `run_ended.data`) produit par `evaluation/`, avec la règle de fiabilité du juge, le barème de prix daté et le non-évalué exclu des moyennes et du classement.

### B9. Moyenne. Tests : marqueurs par défaut et contrôles de charte absents
- Entrées : D7 (pytest, E2E marqués `e2e`) ; AGENTS.md : un `pytest` nu lance l'intégration qui exige Ollama, et `pytest.ini` prime sur `pyproject` ; étape 1 : test de dérive de `tokens.css`, axe-core clair et sombre sans exclusion, aucun emoji dans `static/`, aucune requête hors `127.0.0.1`.
- Spine : la table Tests liste les dossiers et deux marqueurs ; le job CI lance `pytest tests/v2` sans exclure `e2e` ni `integration`. Aucun contrôle de charte.
- Correctif : déclarer les marqueurs dans `pytest.ini`, avec `addopts = -m "not e2e and not integration"` par défaut et un job CI e2e séparé (Playwright installé en CI seulement). Lister les quatre contrôles de charte comme tests obligatoires de l'étape 1.

### B10. Basse à moyenne. Charte Wavestone, typographie et texte français
- Entrées : SPEC : charte (`#451DC7`, icônes Material, aucun emoji), Aptos puis Inter local, i18n ; 03 §3.7 : formats `fr-FR` par `Intl`, mg sous 1 g, une seule unité par comparaison, « estimé » toujours présent, aucune couleur par seuil de CO₂.
- Spine : la structure prévoit `tokens.css`, `fonts/`, `icons.svg`, `i18n/fr.json`, mais aucune règle de convention. `fr.json` diffère de `content/ui.fr.yaml` (03) sans le dire. Les textes d'erreur sont français côté serveur (AD-18) et le reste côté front : deux sources pour les libellés de badges (« indicatif », « un seul juge », « estimé », « non mesurable »).
- Correctif : ajouter une ligne « Présentation » dans les conventions : charte et jetons, formats `Intl`, règle des unités et de « estimé », pas de couleur par seuil, qui possède quelles chaînes (serveur : erreurs ; front : le reste).

### B11. Basse à moyenne. Vie privée et hors ligne côté navigateur
- Entrées : SPEC : aucune requête du navigateur hors `127.0.0.1`, aucun CDN ; pile : polices servies localement.
- Spine : AD-20 interdit les dépendances JS tierces et AD-19 les requêtes d'origine étrangère, mais ni CSP ni test de non-sortie ne sont posés.
- Correctif : en-tête `Content-Security-Policy: default-src 'self'` dans `web/` et E2E qui échoue sur toute requête réseau externe.

### B12. Basse. Divers
- Alerte OneDrive : la spine la place au démarrage mais ne dit pas où elle s'affiche (journal seul ? barre haute ?) ni comment on détecte (chemin contenant `OneDrive`). Avec WAL, le risque de corruption mérite un bandeau.
- Flux système : arrêt à l'onglet masqué (CAP-10, 03 Accueil). La spine ne dit pas que le serveur ne collecte que s'il y a un abonné, ni que `sse.js` ferme le flux sur `visibilitychange`.
- Relance automatique : 03 §3.8 prévoit une relance après une coupure d'Ollama (événement `retry`). La spine ne reprend ni `retry` ni sa règle (une seule fois, puis bouton). Le contrat garde l'événement mais le port `ChatModel` n'a pas de `RetryNotice`.
- Annulation : « Arrêter » garde le partiel en base avec statut `cancelled` (CAP-5). AD-5 et AD-8 ne le disent pas ; vérifier dans la story que le message partiel est écrit dans le `finally` de la tâche annulée.
- Reset de session : `POST /api/carbon/session/reset` et « Arrêter et enregistrer » (03) n'apparaissent pas ; `app_sessions` suppose un cycle de vie à décrire.
- Rendu : 03 §3.6 (Markdown au plus toutes les 150 ms, défilement qui ne force pas vers le bas, annonce `aria-live` en fin de flux seulement, focus sur le `h1`, `document.title`) n'a pas d'AD ; à couvrir par le compagnon proposé en A6.
- Un même modèle une seule fois par Arène (AD-6) est une nouvelle contrainte qui n'existe pas dans la spec ; et 2 à 4 colonnes (03) n'est pas bornée côté API.
- Ingestion : un seul run `ingest` actif à la fois (AD-14) alors que 03 permet plusieurs dépôts et « Annuler » par fichier ; décrire le dépôt suivant (file d'attente ou 409) et la granularité d'annulation.
- Tarif et dates : la pile écrit `CO₂ g` en table `runs` et la spine `mg`. AD-10 remplace déjà le vocabulaire des méthodes, mais l'unité n'est dite que dans les conventions.

## C. Ce qui est bien traité (aucune action)
- D1 (AD-9), D3 (AD-8), D5 (AD-19). Reprise par `Last-Event-ID` et `204`. « Jamais 0 pour inconnu » côté données (AD-10). Remplacement explicite des vocabulaires CO₂ et de la table `jobs`. Python 3.11, sqlite-vec, fastembed en extra, migrations avant seulement, fichiers de 600 lignes.

## D. Synthèse des priorités
1. A1, A2, B1, B2, B5 (haute) avant l'étape 1.
2. B4 avant l'étape 6 ; B3 et B7 à B9 avant les étapes 2 à 4 qui les portent.
3. A3 à A7 et B10 à B12 : corrections rédactionnelles de la spine.
