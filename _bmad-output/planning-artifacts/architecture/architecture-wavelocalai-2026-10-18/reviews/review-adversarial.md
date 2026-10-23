# Revue adversariale de l'ARCHITECTURE-SPINE (wavelocalai v2)

Lentille : construire des paires d'unités, un niveau sous la spine, qui respectent chaque AD à la lettre et ne s'assemblent pourtant pas. Chaque paire est un trou ; chaque trou propose une règle d'une phrase (à ajouter ou à resserrer).

**Verdict** : le squelette (hub de runs, écrivain unique, flux SSE) est solide, mais la spine ne dit presque rien du cycle de vie des entités partagées (conversation, message, statut de run, session) ni de la frontière hub / services / greenops ; en l'état, deux stories conformes divergent sur au moins 6 points bloquants.

Sévérité : B = bloquant (deux stories conformes ne s'intègrent pas ou violent un invariant de la spine), H = haut (bug latent ou rework probable), M = moyen.

---

## 1. Conversations et messages : trois propriétaires possibles (B)

**Paire** : story Chat, story RAG « Discussion », story Agents (solo), toutes avec `conversation_id?` dans la commande (contrat).

**Ce que la spine permet** : l'ER dit `conversations ||--o{ messages` et `runs ||--o{ messages` (« produit »). Aucun AD ne dit :
- qui crée la ligne `conversations` (la route avant le run, le service au début, le hub ?) ;
- comment le client apprend le `conversation_id` d'une conversation nouvelle : `POST …/runs` ne rend que `{run_id}` ;
- qui écrit le message utilisateur (avant `run_started` ? à `run_ended` ?) et le message assistant (au fil de l'eau, ou en bloc final ?) ; que devient un message partiel si le run est annulé ou `interrupted` ;
- si le canal `thought` est stocké dans `messages` ou seulement dans `run_events` ;
- si une même conversation peut mêler chat, RAG et agent. Avec « un run actif par `kind` » (AD-14), un chat et un run RAG peuvent écrire en même temps dans la même conversation, l'ordre des messages est alors indéfini ;
- d'où vient l'historique envoyé au modèle au tour suivant (table `messages` ou rejeu d'événements) ;
- la citation `[n]` d'un message RAG pointe vers des `sources` qui n'existent que dans `run_events` (voir trou 2).

Chat écrit les messages dans le service, RAG dans la route, Agents dans le hub : chacun est conforme, le résultat est incompatible (doublons, messages orphelins, `GET /api/conversations/{id}` incomplet).

**Règles proposées**
- AD-22 : la ligne `conversations` est créée par le hub dans la même transaction que la ligne `runs`, et le `conversation_id` (créé ou reçu) figure dans `run_started.data` et dans la réponse `{run_id, conversation_id}`.
- AD-23 : seul le hub écrit `messages` : le message utilisateur à la création du run, le message assistant à `run_ended` (texte accumulé `answer`, statut du run, `run_id`) dans la même transaction que le dernier lot d'événements ; une annulation conserve le texte partiel avec `status = cancelled`.
- AD-24 : une conversation a un `kind` fixe à sa création (`chat`, `rag`, `agent`) et un seul run actif à la fois, un second rend `409 run_busy` ; l'historique des tours suivants se lit dans `messages`, jamais dans `run_events`.

---

## 2. Effacement (AD-13) contre `runs`, `run_events`, `sources` et le CO₂ de session (B)

**Paire** : story Chat/Conversations (`DELETE /api/conversations/{id}`), story RAG (`DELETE /api/rag/documents/{id}`), greenops (somme des feuilles de la session).

**Trous**
- `conversations ||--o{ runs` : une cascade supprime les runs, donc leurs `run_events` et leurs enfants. Mais le CO₂ de session (AD-10) est la somme des feuilles de l'`app_session` : effacer une conversation **réduit rétroactivement** le total affiché et `carbon/history`. Deux lectures conformes : cascade (AD-13) ou conservation (AD-10).
- Les événements `sources` (contrat) contiennent le **texte des chunks**, et les `step`/`token` le texte des prompts et réponses. Effacer un document (AD-13 : « DELETE en cascade ») ne touche ni `run_events` ni `messages` des runs RAG passés : le texte du document reste dans le `.db`, ce que le test d'AD-13 (octets du `.db` et du `-wal`) devrait attraper, mais sans règle de cascade il échouera tard.
- Effacer une conversation **pendant qu'un run est actif** : le hub garde les événements en mémoire (AD-7) et les écrit par lot ; le lot suivant réécrit des lignes d'un run supprimé (violation de clé étrangère, ou, sans FK, résurrection du texte effacé). Le `VACUUM` s'exécute-t-il dans la file de l'écrivain unique (il bloque tout ?) ?
- Les exports (`.json`, `.md`, `.csv`), les sorties produites (`/api/outputs/{name}`, artefacts d'agents) et les journaux échappent à la cascade.

**Règles proposées**
- AD-13 (resserré) : les feuilles ne portent pas leur CO₂ seulement dans `runs` mais dans une table `carbon_ledger` (run_id sans FK, `app_session_id`, `mg`, `method`, `estimated`, …) qui ne contient aucun texte et survit à l'effacement ; le total de session lit le registre.
- AD-13 (resserré) : tout texte de document ou de conversation vit dans des tables identifiées (`messages`, `run_events`, `sources`, `outputs`) et la cascade d'effacement d'un document supprime les `sources` des runs qui le citent (le message garde `[n]` sans texte) ; le test d'octets couvre ces cas.
- AD-13 (resserré) : effacer une entité avec un run actif annule d'abord le run, attend `run_ended`, puis supprime ; le `VACUUM` passe par la file de l'écrivain et l'API rend `423` / `run_busy` pendant son exécution.

---

## 3. Approbation, « un run par kind », et annulation (B)

**Paire** : story Agents (`approval_required`, attente humaine) et hub `runs/` (AD-14, annulation).

**Trous**
- Un run agent attend `POST …/approvals/{id}` pendant des minutes ou des heures : il tient son emplacement `agent` (AD-14), donc tout autre run agent rend `409`. Aucune règle n'ordonne de délai, ni de statut « en attente ».
- Aucun événement `approval_resolved` dans le contrat : l'état de l'approbation n'existe nulle part dans le flux rejoué. Deux onglets peuvent approuver deux fois ; un client qui rejoue le flux revoit un dialogue déjà traité.
- Qui possède le futur d'attente : le hub ou le service `agents/` ? Où va le `POST …/approvals` (route → service ? → hub ?). Le hub est « seul à annuler » (AD-5), mais pas à débloquer.
- Une annulation pendant l'attente : la tâche est annulée, mais l'outil (envoi d'e-mail) a-t-il été exécuté ? Après redémarrage (`interrupted`) l'approbation en attente est perdue.
- **Runs enfants et `kind`** : l'arène a des enfants (un par appel de modèle) ; quel `kind` portent-ils ? S'ils portent `chat`, l'arène bloque le chat ; s'ils portent le kind du parent, la limite « un par kind » les compte-t-elle ? Les deux lectures sont conformes. La liste de kinds d'AD-14 n'a pas `crew`, `judge`, `embed`, `rerank`, `agent`-solo/équipe se distinguent seulement par `mode`.
- **Propagation de l'annulation** : annuler un parent annule-t-il les enfants (tâches asyncio, tracker CodeCarbon arrêté dans un `finally` qui attend lui-même le sémaphore) ? Annuler un enfant seul est-il possible ? Statut final d'un parent dont un enfant a échoué (`ok`, `error`) ? Le contrat n'a que `ok|error|cancelled`.
- Une attente de sémaphore (`lane_status = waiting`) annulée : tracker déjà démarré ?

**Règles proposées**
- AD-5 (resserré) : seul un run racine porte un `kind` et compte pour AD-14 ; un enfant porte `kind = "call"` et `parent_run_id`, et l'annulation du parent annule en cascade ses enfants (feuilles non terminées → `cancelled`, mesures partielles conservées avec `estimated = true`).
- AD-5 (resserré) : statut d'un parent = `error` si au moins une feuille obligatoire échoue, `ok` si tous les lanes sont `done` ou `timeout`/`failed` déclarés tolérés (arène/évaluation), `cancelled` si annulé par l'utilisateur ; la table `runs` ajoute `interrupted`, qui est aussi un statut de `run_ended` synthétisé (trou 4).
- AD-25 : l'approbation est une entité du hub (`approvals` : id, run_id, état, délai), `approval_required` et `approval_resolved` sont des événements du flux, un run en attente d'approbation a le statut `awaiting_approval`, libère son emplacement `agent` pour un seul autre run en lecture, expire après un délai de `Settings` (refus par défaut), et un outil sensible n'est exécuté qu'après `approval_resolved(accepted)` persisté.

---

## 4. Statut de run, `run_ended` et lots d'écriture (H)

**Paire** : hub `runs/` (AD-5, AD-7) et écrivain unique du store (AD-12).

**Trous**
- Qui fixe `runs.status` : le service (qui sait si ça a réussi) ou le hub (qui voit l'exception) ? Qui émet `run_ended` ?
- L'écriture finale des événements (AD-7 « en entier à `run_ended` ») et la mise à jour de la ligne `runs` sont-elles une transaction ? Sinon `GET /api/runs/{id}` rend `running` alors que le flux se termine, ou le contraire.
- La mémoire du hub est libérée après l'écriture finale : un client qui rejoue avec `Last-Event-ID` lit la base « sinon » ; entre l'envoi du dernier lot et sa validation, il voit un trou.
- Redémarrage : les runs non terminés passent à `interrupted` (AD-5), mais aucun `run_ended` n'est écrit ; le client qui rejoue le flux d'un run `interrupted` n'obtient jamais l'événement final, `EventSource` se reconnecte sans fin (ce que AD-6 voulait prévenir) ; il perd aussi jusqu'à 1 s d'événements, donc des `seq` en queue, et `seq` n'est plus « contigu jusqu'à `run_ended` ».
- Métriques de feuille : à la fois événement `metrics` (dans `run_events`) et colonnes de la ligne feuille ; deux chemins d'écriture (service via store, hub via événement).
- L'écrivain unique est partagé avec l'ingestion (grosses transactions de chunks et de vecteurs) : un lot d'événements d'un chat attend derrière l'ingestion, la file n'a ni priorité ni taille de transaction maximale. Les migrations de story (colonnes de `runs` ajoutées par hub, greenops, chat…) en parallèle prennent le même numéro `NNNN`.

**Règles proposées**
- AD-7 (resserré) : le hub est seul à fixer `runs.status` et à émettre `run_ended` ; le dernier lot d'événements et la mise à jour de `runs` (statut, `ended_at`, métriques, CO₂) forment une seule transaction de l'écrivain.
- AD-5 (resserré) : au démarrage, le hub écrit pour chaque run non terminé un événement `run_ended` synthétisé (`seq` suivant, `status = interrupted`, erreur `server_restarted`) ; `interrupted` est une valeur officielle du contrat.
- AD-12 (resserré) : l'écrivain traite une file à deux priorités (flux de runs avant ingestion), les transactions d'ingestion sont découpées (≤ 200 ms) ; la table `runs` est créée en entier (colonnes de métriques et de CO₂ comprises) par la migration de la story du hub, et chaque migration réserve son numéro dans un registre des étapes.
- AD-7 (resserré) : la mémoire d'un run est libérée seulement après le commit confirmé, et le rejeu lit mémoire ∪ base sans trou.

---

## 5. Frontière greenops / hub, `app_session`, `carbon_updated` (H)

**Paire** : hub `runs/`, greenops, store.

**Trous**
- Le diagramme interdit `runs → greenops`, pourtant la ligne `runs` porte `app_session_id`, et le hub doit écrire le CO₂ de la feuille. Qui connaît l'`app_session` courante ? Qui la crée au démarrage (`__main__`, greenops, store) ? Que fait `POST /api/carbon/session/reset` : ferme la session et en ouvre une autre ? Un run en cours reste-t-il dans l'ancienne ? Une feuille commencée avant le reset, finie après ?
- `carbon_updated` va sur `/api/system/stream` (AD-6) ; greenops n'importe ni `runs` ni `web`, aucun port ne l'autorise à publier. Les services appellent-ils greenops puis publient-ils eux-mêmes ?
- **Prorata de l'arène** : `allocation = prorata_tokens` n'est défini nulle part. AD-11 mesure par feuille, un tracker à la fois sous le sémaphore, donc une mesure directe par feuille ; le prorata ne se justifie que si la mesure couvre plusieurs lanes. Sur quel ensemble (frères d'un parent ? lane annulée ?), calculé par qui (greenops ne voit pas les frères), à quel moment (avant la fin des frères) ?
- Contamination : le tracker mesure la machine ; l'ingestion (pypdf, ONNX dans le pool de threads, hors sémaphore, AD-14) et les appels cloud tournent en parallèle d'une génération locale, ce qui gonfle son énergie. `estimated` reste faux.
- Les runs d'ingestion, d'installation et d'évaluation sont-ils des feuilles mesurées ? Le CO₂ d'une feuille d'embedding (sans `ChatModel`, voir trou 6) ?
- Les attentes d'approbation et de sémaphore comptent-elles dans `total_s` et l'énergie ?

**Règles proposées**
- AD-26 : une table `app_sessions` est créée par `__main__` avant le hub ; le hub reçoit un `SessionProvider` (port défini dans `runs/`, implémenté par greenops) et fige `app_session_id` sur chaque racine à sa création, les enfants héritent ; un reset ferme la session et n'affecte pas les runs déjà créés.
- AD-26 : les événements hors run (`carbon_updated`, état d'Ollama, système) passent par un port `SystemBus` défini dans `runs/`, que greenops et `hardware/` alimentent et que `web/` diffuse.
- AD-10 (resserré) : `allocation = prorata_tokens` n'existe que pour une mesure de machine partagée entre appels simultanés (jamais pour des feuilles séquentielles sous le sémaphore) ; il se calcule dans greenops à partir d'une liste explicite `(leaf_id, output_tokens)` fournie par le service ; sinon `direct`.
- AD-11 (resserré) : un run feuille local n'est « mesuré » (`estimated = false`) que si aucun travail CPU (pool de threads) ni autre appel local n'a recouvert sa fenêtre ; sinon `estimated = true`. Seules les feuilles `generate` et `embed` sont mesurées ; `ingest` et `pull` sont `unmeasurable` avec raison `not_inference`.

---

## 6. Il manque un port d'embedding, et l'ingestion et le RAG se chevauchent (H)

**Paire** : story Ingestion (`POST /api/rag/documents`) et story RAG (`POST /api/rag/runs`, « Vider », `PUT /api/rag/settings`).

**Trous**
- AD-8 définit `ChatModel` (flux de texte, outils) ; ni l'ingestion ni la requête RAG n'ont de port pour `embed`. L'ingestion appellera l'API Ollama en direct, le RAG un autre client : deux chemins hors `registry.resolve` et `allow_cloud` (AD-9 contourné), sans `ProviderError`.
- Une requête RAG pendant une ingestion lit un document à moitié indexé ; une ingestion annulée laisse-t-elle un document partiel ?
- `PUT /api/rag/settings` (changement du modèle d'embedding) pendant une ingestion ou un run RAG : dimension, table `chunks_vec_<dim>` créée par qui ? AD-16 impose « Vider » puis réimport, sans dire qui l'applique atomiquement ni quoi faire du run en cours.
- Supprimer un document pendant qu'un run RAG a ses `chunk_id` dans `sources` ; `GET /api/rag/chunks/{id}` rend 404.
- Les réglages sont lus au démarrage du run (`preferences`), mais jamais figés dans `run_started` : un export ne dit pas quelle stratégie a produit la réponse.

**Règles proposées**
- AD-8 (étendu) : un port `Embedder` (`embed(texts) -> vectors`, mêmes erreurs, même passage par `registry.resolve`) existe à côté de `ChatModel` ; `rag/` n'appelle jamais un client HTTP directement.
- AD-16 (resserré) : un document a un `status` (`pending`, `ready`, `failed`) et seuls les `ready` sont interrogeables ; une ingestion annulée supprime le document partiel ; changer le modèle d'embedding ou vider refuse (`409 run_busy`) tant qu'un run `ingest` ou `rag` est actif.
- AD-15 (resserré) : à sa création, un run copie dans `run_started.data.params` les valeurs effectives de toutes les préférences qu'il lit, et n'en relit aucune ensuite.

---

## 7. Sens de `lane` hors Arène (H)

**Paire** : story RAG / Agents / Évaluation / Ingestion et front `sse.js` + écrans.

**Trous**
- AD-6 : `lane` toujours présent, « tag du modèle ». Un crew peut employer deux agents avec le même modèle (collision de lane, alors que « un même modèle ne figure qu'une fois par arène ») ; `step` a un champ `agent` mais `token` n'a que `lane`.
- Évaluation : le juge peut être le même modèle qu'un concurrent ; sa lane `judging` entre en collision avec la lane du concurrent.
- Ingestion et installation de modèle n'ont pas de génération : `ingest_progress` a-t-il une `lane` ? (probablement le modèle d'embedding, ou `null` : « toujours présent »).
- `metrics` du contrat n'a pas de `lane` ; en arène, comment relier un `metrics` à une feuille ? Aucun mapping `lane → run_id enfant`.
- Pour le RAG, une seule lane (tag du modèle) mais deux feuilles (embedding de la question, génération).

**Règles proposées**
- AD-6 (resserré) : `lane` est une chaîne opaque `"<role>:<id>"` (`model:qwen3.5:2b`, `agent:analyste`, `judge:gpt-5`, `embed:bge-m3`) unique par parent ; le champ est aussi présent dans `metrics`, `lane_status`, `eval_metric` ; sans génération (`ingest`, `pull`) la lane vaut `"run"`.
- AD-5 (resserré) : chaque lane correspond à exactement un run enfant (`runs.lane`) et l'événement `lane_status(started)` porte son `run_id` enfant.

---

## 8. Création du run, validations et reprise sur `409` (M)

**Paire** : story Chat (validation synchrone, 4xx) et story Arène (erreur dans `run_ended`).

- Où se fait `registry.resolve` : dans la route (réponse 4xx synchrone) ou dans le run (`run_ended.error`) ? Les deux sont conformes à AD-9 et AD-18, les écrans géreront deux cas.
- `409 run_busy` rend le `run_id` actif « que le front rejoint » : si la nouvelle commande avait un autre prompt ou d'autres modèles (arène), le front affiche silencieusement le mauvais run.
- Un envoi multipart de plusieurs fichiers : un run, ou un par fichier ?

**Règles proposées**
- AD-14 (resserré) : toutes les validations (cloud, modèle introuvable, occupé, taille) sont synchrones avant création du run et rendent une erreur HTTP ; après `run_id`, tout échec passe par `run_ended`.
- AD-14 (resserré) : `409 run_busy` rend le résumé du run actif (`kind`, paramètres) et le front le propose comme choix explicite (rejoindre ou annuler), sans rejoindre automatiquement.

---

## 9. Connexions du navigateur et état partagé du front (M)

**Paire** : `core/sse.js`, `core/store.js` et un écran (arène + chat + ingestion en parallèle).

- AD-14 se justifie par « les 6 connexions du navigateur », mais huit kinds actifs en même temps + `system/stream` = 9 flux en HTTP/1.1 ; rien ne limite le nombre de flux ouverts, ni ne dit si `sse.js` ferme le flux à `run_ended`.
- Le store garde les runs actifs hors écran, mais le **schéma d'état d'un run** (texte par lane, métriques, étapes) n'est défini par aucun AD : chaque écran écrit son réducteur, et le retour sur un écran démonté rend un état différent du direct. Qui possède le réducteur, sse.js ou l'écran ?
- Rechargement de page : le store est vide, les runs actifs sont à redécouvrir (`GET /api/runs?status=active` absent du contrat).

**Règles proposées**
- AD-20 (resserré) : `sse.js` ouvre au plus 4 flux de runs (+ le flux système), met les suivants en file et ferme chaque flux à `run_ended` ; une route `GET /api/runs?active=1` permet de reconstruire le store au chargement.
- AD-20 (resserré) : un réducteur unique `core/run-state.js` transforme les événements en un état normalisé par lane ; les écrans ne lisent que cet état et n'ont aucun réducteur propre.

---

## 10. Divers (M)

- `allow_cloud` : il est envoyé par commande mais n'est pas persisté dans le run ; un `retry` ou la reprise d'un enfant ne sait pas s'il peut appeler le cloud. *Règle* : `allow_cloud` est copié sur la racine et hérité par les enfants, jamais relu du client.
- `retry` (événement) : un nouvel essai crée-t-il une nouvelle feuille (CO₂ double compté malgré AD-5) ou réutilise-t-il la feuille ? *Règle* : un essai est une nouvelle feuille de `attempt = n+1` ; la précédente reste comptée au CO₂ avec `estimated = true`.
- Couplage doc : `contrat-api.md` garde `co2.method: local|ecologits|unknown`, AD-10 le remplace ; il faut mettre à jour le contrat, comme l'annonce la spine.
- Arène : le texte de chaque lane vit dans `run_events` compactés ou dans `messages` ? L'export CSV lit quelle source ? *Règle* : les réponses d'arène sont des lignes `messages` (sans `conversation_id`) rattachées à la feuille.
- Migrations : plusieurs stories parallèles prennent le même `NNNN`. *Règle* : numéros réservés par étape dans `store/migrations/README`.

---

## Synthèse des nouvelles règles

| ID | Règle (une phrase) |
| --- | --- |
| AD-22 | Le hub crée la conversation avec le run et rend `{run_id, conversation_id}`. |
| AD-23 | Seul le hub écrit `messages` : utilisateur à la création, assistant à `run_ended`, même transaction que le dernier lot. |
| AD-24 | Une conversation a un `kind` fixe et un seul run actif. |
| AD-25 | L'approbation est une entité du hub avec statut de run, événement de résolution persisté et délai. |
| AD-26 | `app_session` créée par `__main__`, portée par un `SessionProvider` et `SystemBus` définis dans `runs/`. |
| AD-5+ | Seule la racine porte un `kind` ; annulation en cascade ; `interrupted` officiel avec `run_ended` synthétisé. |
| AD-7+ | Le hub fixe seul le statut et émet `run_ended` ; commit unique avec la ligne `runs`. |
| AD-8+ | Port `Embedder` à côté de `ChatModel`. |
| AD-13+ | Registre carbone sans texte ; cascade des `sources` ; annuler avant d'effacer. |
| AD-6+ | `lane` opaque `"<role>:<id>"`, unique par parent, présent dans `metrics`. |
| AD-14+ | Validations synchrones avant `run_id` ; `409` rend un résumé et ne rejoint pas automatiquement. |
| AD-20+ | Au plus 4 flux de runs ; réducteur d'état unique côté front. |
