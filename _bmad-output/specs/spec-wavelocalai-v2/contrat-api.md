# Contrat d'API de la v2

Arbitrage de la synthèse §3 : **modèle « run » du front** (03 §4), porté par la table `runs`. Les noms de routes sont indicatifs ; les données, le modèle run, la trame SSE et les noms d'événements sont contractuels. Les règles citées `AD-n` sont celles d'`ARCHITECTURE-SPINE.md`, qui prime sur ce fichier.

## Runs (AD-5)

- Toute génération, ingestion, installation, évaluation, équipe ou banc est un run créé par le hub `runs/`, seul à attribuer `seq`, publier, persister, annuler et fixer le statut. Pas de jobs à part.
- Commande = `POST /api/<module>/runs`, qui rend `{run_id}`, plus `conversation_id` si le run ouvre ou prolonge une conversation (créée par le hub avec le premier run ; `kind` de conversation fixe : `chat`, `rag`, `agent`).
- Run racine : `kind` parmi `chat`, `arena`, `rag`, `agent`, `ingest`, `pull`, `eval`, `bench`. Un run composite a des enfants (`parent_run_id`), un par appel de modèle, juge compris ; métriques et CO₂ ne vivent que sur les feuilles ; le parent publie seul le flux ; annuler le parent annule ses enfants ; le parent finit `ok` si l'orchestration aboutit, l'échec d'une lane reste dans son `lane_status`.
- Feuille : `kind` en liste close `generation` (tout appel de modèle hors notation, HyDE et Self-RAG compris), `judge`, `embedding` (lot d'ingestion, question, évaluation) ; une feuille `embedding` locale est mesurée comme les autres. Le reclassement fastembed n'est pas une feuille.
- Instantané `GET /api/runs/{id}` : statut, métriques des feuilles, erreur ; ce qui se calcule sur un run terminé y figure et non dans le flux (run `arena` : `verdict` ; run `bench` : `format_verdict` ; run `eval` arrêté ou interrompu : `partial: true`). Un identifiant inconnu rend `404 run_not_found` (`detail.run_id`) ; l'affichage d'un run effacé (AD-13 : `runs` gardé sans événements) reste à trancher.
- Statuts : `running`, `awaiting_approval`, `ok`, `error`, `cancelled`, `interrupted`. Au démarrage du serveur, chaque run non terminé reçoit un `run_ended {status: "interrupted"}` synthétique.
- Au plus un run racine actif par `kind` : un second rend `409 run_busy` avec le `run_id` actif dans `detail.run_id`, que le front rejoint (AD-14).

## Trame SSE (AD-6)

- Trame : `id: <seq>` puis `data: <enveloppe JSON>`, **sans champ `event:`** ; enveloppe `{seq, run_id, type, ts, data}`, `ts` en ISO 8601 UTC avec `Z`. Type inconnu ignoré.
- `seq` commence à 1, contigu par run ; `run_started` en premier, `run_ended` en dernier, une seule fois. Le client écarte tout `seq` déjà vu et ferme à `run_ended`.
- Reprise par `Last-Event-ID` ou `?after=<seq>` (mémoire du hub si le run est actif, base sinon) ; curseur au dernier `seq` d'un run terminé = `204`. Commentaire de maintien toutes les 15 s.
- `token` groupé par tranches de 50 ms au plus et par `lane`. `lane` = tag du modèle, toujours présent sur `token`, `metrics`, `lane_status`, `judge_score`, `step`, `eval_metric` ; un modèle figure une fois par arène.
- Le front n'ouvre de flux que pour les runs de l'écran monté et reprend avec `?after=` en revenant.

## Champ `co2` (AD-10)

Partout (événement `metrics`, table `runs`, exports) : `{mg: float | null, method: "codecarbon" | "ecologits" | "unmeasurable", estimated: bool, range_mg: {low, high} | null, allocation: "direct" | "prorata_tokens", reason: str | null}`, `reason` requis si `mg` est nul. Une feuille locale a son propre tracker (`direct`) ; `prorata_tokens` est réservé à une mesure partagée par plusieurs feuilles locales (aucune au MVP).

## Transverse

| Besoin | Route | Données |
|---|---|---|
| Santé | `GET /api/health` | version, `instance_id` (nouveau à chaque démarrage), Ollama `{up, version, latency_ms}` (sonde ≤ 1 s, cache 5 s, AD-15), fournisseurs cloud `{id, configured}` sans les appeler |
| Flux système | `GET /api/system/stream` (SSE, 2 s) | enveloppe d'AD-6 avec `run_id: null`, sans `id:` ni rejeu : état d'Ollama (sonde à cache 1 s, AD-15), CPU %, mémoire utilisée et totale, modèles chargés et leur mémoire, `carbon_updated`, `runs_active` = `[{run_id, kind, status}]` |
| Identité machine | `GET /api/system/identity` | fiche machine (export de preuve, Sobriété) |
| Modèles | `GET /api/models?allow_cloud=` | servi depuis le cache (AD-15) : `tag`, nom, fournisseur, `origin`, `kind`, paramètres totaux et actifs, taille, mémoire nécessaire, `fits` (calculés par `hardware/`), débit mesuré sur ce poste (médiane du `tps` des feuilles `ok` en `ollama_eval` de `runs`, absent sans run), précision (`qb.results/1` dès l'étape 5, `null` avant), outils vérifiés, raisonnement, `default_temperature` (créativité par défaut du modèle, `float\|null`, lue des paramètres publiés par Ollama pour le modèle ou du catalogue ; `null` si inconnue, le front replie alors à 0,2 ; décision D-12), méthode CO₂ disponible (`codecarbon` en local, `ecologits` pour un fournisseur direct ou un modèle Groq de la table de correspondance, `unmeasurable` sinon) ; catalogue `config/models_catalog.json` en lecture seule |
| Défauts | `GET /api/models/defaults?purpose=chat\|arena\|judge\|agent\|rag` | tags et **raison** affichée en aide. Règle provisoire, seuils calés sur `qb.results/1` à l'étape 5 : `agent` = modèle local aux outils vérifiés d'au moins 3 milliards de paramètres actifs, sinon `tags: []` et une raison qui donne les conditions ; `rag` = modèle local d'au moins 3 milliards de paramètres actifs, sinon défaut `chat` avec la raison dite |
| Mode cloud | champ `allow_cloud` sur chaque commande | modèle `origin != "local"` sans lui = `cloud_not_allowed` ; absent = faux (D1, AD-9) |
| Exécutions | `GET /api/runs/{id}/events`, `POST /api/runs/{id}/cancel`, `GET /api/runs/{id}` (instantané, `verdict` pour un run `arena`) | trame d'AD-6 |
| Erreurs | toutes les routes et `run_ended.data.error` | `{code, message, action, detail}` en français, codes fermés dans `errors.py` ; `detail` est un objet : `technical` (texte replié) et les clés machine déclarées avec le code (`run_busy` : `run_id` ; `ram_guard` : `needed_gb`, `free_gb`, `suggested_model` ; `run_not_found` : `run_id` ; `pull_failed` : `tag`, `cause` parmi `not_found`, `ollama_down`, `interrupted` ; `model_in_use` : `tag`), valeurs texte masquées (AD-18). L'enveloppe ne porte pas de boutons : le front les déduit du code et de `detail` (décision D-4) |
| Budget de lecture | toutes les routes `GET` sans paramètre de chemin, hors SSE | < 300 ms Ollama injoignable, test paramétré qui inclut d'office toute nouvelle route (AD-15) |
| CO₂ de session | `GET /api/carbon/session`, `carbon_updated` sur le flux système | somme des feuilles de l'`app_session` courante (nouvelle à chaque démarrage et remise à zéro), par module, Local et Cloud, nombre de non-mesurables ; le flux système n'ayant pas de rejeu, le client lit `GET /api/carbon/session` à chaque (re)connexion du flux, après l'ouverture, puis applique les `carbon_updated` |
| Sécurité locale | toutes les routes | écoute `127.0.0.1:8502` ; `Host` hors `127.0.0.1:<port>`/`localhost:<port>` refusé ; écriture d'`Origin` étrangère refusée ; aucun CORS (AD-19) |

## Événements de run

| Type | Données | Écrans |
|---|---|---|
| `run_started` | `kind`, modèles, paramètres | tous |
| `question` | `text` : la question d'une Arène, et `criteria` : ses critères de notation (liste, vide par défaut), publiés juste après `run_started` (une Arène n'a pas de conversation ni de `messages` ; `runs.params` ne porte pas de texte saisi, AD-7) | Arène |
| `model_loading` / `model_loaded` | `tag`, durée | chat, Arène, RAG, agents |
| `token` | `lane`, `text`, `channel` (`answer` ou `thought`) | chat, Arène, RAG, agent |
| `retry` | raison | chat, Arène, RAG |
| `metrics` | `lane`, `ttft_s`, `load_s`, `eval_tokens`, `eval_s`, `tps` (D3), `tps_source` (`ollama_eval` ou `wallclock`), `total_s`, `co2` (AD-10), origine | tous |
| `lane_status` | `lane`, `status` (`waiting`, `loading`, `generating`, `judging`, `done`, `timeout`, `failed`, `cancelled`), `error` (enveloppe d'AD-18) avec `timeout` et `failed` | Arène, Évaluation |
| `judge_score` | `lane`, `score\|null`, `reason` | Arène |
| `sources` | `{n, doc_id, document, page, chunk_id, text, rank, relevance_label, raw_score, passage}` ; `passage` = `{start, end}` (positions en caractères dans `text`) du passage que le serveur désigne pour le surlignage, ou `null` (décision D-21) ; persisté sans `text` (les positions, elles, sont persistées), réhydraté depuis `chunks` au rejeu, `text: null` si le document a été supprimé (« extrait supprimé », AD-7), `passage` alors ignoré | RAG, Évaluation |
| `citations` | correspondances [n] vers les sources | RAG |
| `retrieval_step` | `strategy`, étape, durée | RAG |
| `eval_metric` | `lane`, métrique, `score\|null`, raison, verdicts par affirmation | Évaluation |
| `step` | `lane`, `step_id`, `agent`, `kind` (`think`, `tool_call`, `tool_result`, `answer`), outil, arguments, résumé, `artifact_url`, durée ; en mode équipe, l'étape `answer` qui clôt un agent porte `agent_totals {tools, duration_s}` (ligne « Terminé · 3 outils · 41 s », décision D-34) | agents |
| `approval_required` | `approval_id`, `kind: email`, destinataire, objet, corps ; run en `awaiting_approval` ; réponse par `POST /api/runs/{id}/approvals/{approval_id}` | agent seul |
| `approval_resolved` | `approval_id`, `decision` (`approved`, `rejected`, `expired`) ; sans réponse en 10 min = `expired` = refus ; annuler le run = refus ; un outil sensible ne s'exécute qu'après `approved` (AD-9) | agent seul |
| `ingest_progress` | `{file, file_index, file_count, phase, done, total}` ; `phase` : `extract`, `split` (0/1 puis 1/1), `embed` (extraits vectorisés sur le total du fichier) | Base documentaire |
| `ingest_file_done` | `{file, file_index, file_count, document_id, status, chunks, error}` à la fin de chaque fichier ; `status` : `ready`, `failed` (`error` = enveloppe `ingest_failed` d'AD-18, avec `detail.file` et `detail.reason`) ou `duplicate` (document déjà présent, `document_id` et `chunks` du document existant) ; une annulation n'émet pas d'`ingest_file_done` pour le fichier en cours, qui est retiré | Base documentaire |
| `pull_progress` | tag ou reranker, octets reçus et totaux, phase | Modèles |
| `run_ended` | `status` (`ok`, `error`, `cancelled`, `interrupted`), erreur au format unique | tous |

## Par écran

| Écran | Lectures | Commandes |
|---|---|---|
| Accueil | santé, flux système, défauts `arena`, résumé de la base, outils, CO₂ de session, carte Références (meilleur score en pourcentage, D-5) | — |
| Chat libre | modèles (dont `default_temperature`, qui fixe la créativité par défaut, D-12), défaut `chat`, `GET /api/conversations/{id}`, `GET /api/conversations?kind=chat&limit=1` (les plus récentes d'abord, l'écran rouvre la dernière) | `POST /api/chat/runs {conversation_id?, model, message, temperature, allow_cloud}` ; `DELETE /api/conversations/{id}` ; export `GET /api/conversations/{id}.json` et `.md` |
| Arène | modèles, défauts `arena` et `judge`, scénarios, `GET /api/arena/runs`, verdict par `GET /api/runs/{id}` à `run_ended` et à la réouverture | `POST /api/arena/runs {models, prompt, judge, criteria, allow_cloud}` ; export `GET /api/arena/runs/{id}.csv` et `.md` |
| Références (`#/arene/references`) | références par usage lues depuis `qb.results/1` (AD-22), avec, par usage, le groupe des meilleurs désigné par le serveur (le front n'invente aucun rang) | — (« Comparer ces modèles » ouvre l'Arène présélectionnée, D-19) |
| Base documentaire | `GET /api/rag/documents` rend `{documents: [{id, source, status (`indexing`, `ready`, `failed` ; un document `failed` y figure avec sa raison dans `error`, D-26), chunks, pages, size_bytes, embedding_model, created_at, ready_at, run_id, error}], totals: {documents, chunks} (documents `ready` seulement), limits: {max_file_mb, max_files, max_import_mb}}`, plus récent d'abord ; `GET /api/rag/settings` | `POST /api/rag/documents` (multipart, rend le `run_id` du run `ingest` ; `422 invalid_request` au-delà de `max_files` fichiers ou `max_import_mb` Mo) ; `DELETE /api/rag/documents/{id}` ; `DELETE /api/rag/base?expected_count=` ; `PUT /api/rag/settings` (changer d'embedding impose « Vider ») |
| Discussion | résumé de la base, réglages, défaut `rag` | `POST /api/rag/runs {conversation_id?, question, model, strategy, allow_cloud}` ; `GET /api/rag/chunks/{id}` |
| Modèles | installés, catalogue installable avec mémoire nécessaire et `fits` (un modèle supprimé y revient), état du reranker | `POST /api/models/pull {tag}` et récupération du reranker (runs `pull`, seuls téléchargements, AD-17 ; échec = `pull_failed`) ; `DELETE /api/models/{tag}` (run actif sur le modèle = `409 model_in_use`) ; `POST /api/models/unload` |
| Sobriété | flux système, identité, `GET /api/carbon/history?window=` (sessions closes seulement, D-37), méthode (dont l'équivalence parlante : facteur en g de CO₂ par km, sa source et sa date, valeur pour la session, calculées par le serveur, D-38) | `POST /api/carbon/session/reset` (ouvre une nouvelle `app_session`) |
| Agent seul | `GET /api/agents/tools` (`id`, libellé, description, disponible, raison, sensible), scénarios, défaut `agent` | `POST /api/agents/runs {mode: solo, model, tools, prompt, conversation_id?}` ; approbations |
| Équipe | `GET /api/agents/crews` ; mission rouverte par `GET /api/runs/{id}` (route `#/agents/equipe/<run_id>`, D-8) | `POST /api/agents/runs {mode: crew, crew, topic}` ; `POST /api/agents/crews/validate` (5 agents au plus, D-36) |
| Évaluation | jeux de questions, historique, défaut `arena` (modèles évalués présélectionnés, D-27) ; résultat rouvert par `GET /api/runs/{id}` (route `#/documents/evaluation/<run_id>`), partiel compris (D-28) | `POST /api/rag/eval/runs {questions, models, judge, allow_cloud}` |
| Banc d'essai | `GET /api/scenarios` : par scénario, consigne système (`instruction`, D-18) et format attendu en schéma JSON ou `null` si le scénario n'en a pas (D-17) ; résultat rouvert par `GET /api/runs/{id}` (route `#/arene/banc/<run_id>`) | `POST /api/bench/runs` ; le serveur dit si la sortie respecte le format (`format_verdict` de l'instantané, absent sans format attendu) |
| Fichiers produits | `GET /api/outputs/{name}` | — |

## `409` hors `run_busy`

- Effacer une conversation, un run ou un document qui a un run actif (AD-13).
- Supprimer un modèle utilisé par un run actif : `model_in_use`.
- Changer d'embedding ou « Vider » pendant un run `ingest` ou `rag` (AD-16).
