---
title: 'Poser une question à ses documents et recevoir les sources d''abord (serveur)'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: 'bb272a5'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-1.md'
warnings: []
deferred:
  - summary: >-
      Écarts additifs à `contrat-api.md` (déjà consignés dans le contrat, à ratifier) : `sources` porte `{strategy, sources: [...]}` (une liste par événement) ; `retrieval_step` vaut `{strategy, step, duration_s}`, publié à la fin de chaque étape (`embedding`, `search`) ; `metrics` d'un run `rag` gagne `retrieval_s` ; codes `rag_base_empty` (409) et `chunk_not_found` (404, `detail.chunk_id`).
    evidence: |-
      `rag/query.py` (docstring), `web/test_rag_run_api.py::test_the_sources_come_before_the_first_token_...`, `::test_an_empty_base_leads_to_the_document_base_...`, `::test_a_chunk_is_read_whole_...`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Écran Discussion (4.5) : le message assistant d'un run `rag` rend, dans `GET /api/conversations/{id}`, la ligne du run **racine**, qui n'a ni métriques ni `co2` (AD-5 : elles sont sur les feuilles). Le pied de réponse (débit, CO₂, « Recherche 0,06 s · Génération 5,8 s ») se lit dans l'événement `metrics` rejoué, ou dans `GET /api/runs/{id}` (`children`). Si 4.5 préfère une seule lecture, `conversation_view` peut ajouter `children` à `run` (additif).
    evidence: |-
      `runs/conversations.py::_run_view` (inchangé), `test_the_question_and_the_generation_are_two_leaves_each_with_its_co2`.
    location: src/wavelocalai/runs/conversations.py
    severity: medium
  - summary: >-
      Positions de `passage` en points de code Python (`str`), pas en unités UTF-16 comme `String.slice` de JavaScript : identiques tant que l'extrait n'a pas de caractère hors du plan multilingue de base (emoji). Le front (4.5) doit convertir (`Array.from(text)`) ou le contrat passer en UTF-16.
    evidence: |-
      `rag/passage.py` (docstring), `test_passage.py::test_positions_count_code_points_not_utf16_units`.
    location: src/wavelocalai/rag/passage.py
    severity: low
  - summary: >-
      `nomic-embed-text` sépare mal le pertinent du hors-sujet quand la question et l'extrait sont embeddés sans préfixe de tâche (`search_query: ` / `search_document: ` que recommande le modèle) : mesuré le 2026-10-19, des extraits pertinents à 0,63 à 0,80 de similarité, des hors-sujet jusqu'à 0,65. Les libellés (0,70 et 0,60) sont donc des bandes de similarité, pas un jugement de pertinence. Un préfixe par rôle exigerait d'élargir le port `Embedder` (document ou question) et de réindexer.
    evidence: |-
      Calibrage sur 5 extraits et 7 questions contre le vrai `nomic-embed-text` (journal ci-dessous) ; `integration/test_rag_question_ollama.py`.
    location: src/wavelocalai/models/port.py
    severity: low
  - summary: >-
      Avec le repli `NumpyIndex` (sans sqlite-vec), les vecteurs sont perdus au redémarrage : une question sur une base « prête » ne trouve alors aucun extrait et le run s'arrête en `rag_base_empty` (message « aucun document prêt », trompeur). Le refus explicite d'une base sans vecteurs reste à décider avec 4.2 ou 4.3 (report de la 4.1).
    evidence: |-
      `rag/query.py::_retrieve` (`found` vide), `rag/index.py::select_index`.
    location: src/wavelocalai/rag/query.py
    severity: low
  - summary: >-
      `retrieval_s` mesure l'attente de la place Ollama comprise : si un chat local ou un lot d'ingestion tient la place, la recherche affichée est plus longue que le calcul seul. `top_k` (4) et les seuils de pertinence ne se règlent que dans `wavelocalai.toml` ; `PUT /api/rag/settings` (4.3) les portera en préférences. Le prompt `naive` ne reprend pas l'historique de la conversation (une question est indépendante).
    evidence: |-
      `rag/query.py::_retrieve`, `config.py::RagSettings`.
    location: src/wavelocalai/rag/query.py
    severity: low
---

# Story 4.4 : poser une question à ses documents et recevoir les sources d'abord (serveur)

## Objectif

`POST /api/rag/runs` pose une question aux documents `ready` : le serveur embedde la question, cherche les extraits les plus proches, publie `retrieval_step` puis `sources` **avant** le premier `token`, puis génère la réponse en flux. Le run `rag` est composite : une feuille `embedding` (la question) et une feuille `generation`, chacune avec son `co2`. Aucun écran : l'écran Discussion est la story 4.5.

## Critères d'acceptation et preuves

1. **`POST /api/rag/runs {conversation_id?, question, model, strategy: "naive", allow_cloud}`** rend `{run_id, conversation_id}` ; le hub crée la conversation `rag` (la question est le message utilisateur, jamais dans `runs.params`, AD-7) ; seuls les documents `ready` sont interrogés (les extraits d'un document `indexing` sont dans l'index ; la recherche les écarte avant de prendre les plus proches). Preuve : `test_rag_run_api.py` (`test_the_sources_come_before_...`, `test_only_ready_documents_are_queried_even_when_...`, `test_a_document_not_ready_...`, `test_a_conversation_goes_on_...`, `test_the_whole_path_works_with_the_numpy_fallback_index`).
2. **Ordre du flux** : `retrieval_step {strategy, step: "embedding", duration_s}`, `retrieval_step {…, step: "search"}`, `sources`, puis `token`, `metrics`, `run_ended` ; chaque étape est publiée à sa fin (durée connue). Preuve : `test_the_sources_come_before_the_first_token_...` (ordre, `seq` contigus, `lane` = modèle de réponse).
3. **Feuilles** : `embedding` (question, locale, mesurée par CodeCarbon **dans la place** du `LocalSlot`, comme un lot d'ingestion) et `generation` (comme le chat ; cloud estimé par `cloud_estimator`/ecologits) ; chacune close avec son `co2` ; une feuille annulée ou jamais jouée garde un `co2` non mesuré avec sa raison ; `carbon_updated` suit chaque feuille ; module de session `rag`. Preuve : `test_the_question_and_the_generation_are_two_leaves_...`, `test_a_local_question_takes_the_local_slot_...` (une place par appel), `test_a_cloud_model_needs_allow_cloud` (cloud estimé, embedding local), `test_an_embedding_failure_...`, `test_cancelling_during_the_answer_...`.
4. **`sources`** : `{strategy, sources: [{n, doc_id, document, page, chunk_id, text, rank, relevance_label, raw_score, passage}]}` ; extrait entier ; `relevance_label` et `passage` selon les deux règles ci-dessous. Persisté **sans `text`** (les positions de `passage` le sont) ; au rejeu le hub le réhydrate depuis `chunks` (`events_after`), `text: null` si le document a été supprimé. Preuve : `test_a_replayed_run_gets_its_source_text_back_and_null_...` (octets de `run_events` sans le texte, positions gardées, `null` après suppression), `test_passage.py` (22).
5. **`GET /api/rag/chunks/{id}`** rend `{chunk_id, doc_id, document, page, position, text}` ; extrait disparu, ou document pas `ready` : `404 chunk_not_found` (`detail.chunk_id`, marche à suivre). Preuve : `test_a_chunk_is_read_whole_...`, `test_a_chunk_of_a_document_not_ready_...`.
6. **`metrics`** (feuille de génération) : débit D3 (`tps`, `tps_source`), `co2`, et `retrieval_s` (recherche, embedding compris, à part de `total_s`). Preuve : même test, `integration/test_rag_question_ollama.py` (`ollama_eval`, `codecarbon`).
7. **Base vide** : aucun document `ready` donne `409 rag_base_empty` **avant tout run** (rien créé), dont l'action renvoie à `#/documents/base` ; une recherche sans résultat en cours de run termine le run en `error` avec le même code. Preuve : `test_an_empty_base_leads_to_...`, `test_a_document_not_ready_does_not_make_the_base_queryable`.
8. **Cloud (AD-9)** : un modèle `origin != "local"` sans `allow_cloud` rend `403 cloud_not_allowed` avant tout run ; l'embedding reste local. **Concurrence (AD-14)** : un second run `rag` rend `409 run_busy` avec le `run_id` actif. Preuve : `test_a_cloud_model_needs_allow_cloud`, `test_a_second_question_while_one_runs_is_a_409_...`, `test_a_bad_question_gets_the_error_envelope_...` (question vide, stratégie inconnue, modèle inconnu ou d'embedding).
9. **Pannes** : embedding en panne = run `error` sans `sources` ni `token`, modèle jamais appelé ; génération en panne = `sources` gardées, run `error` avec le code du fournisseur ; annulation = statut `cancelled`, `sources` et réponse partielle gardées. Preuve : `test_an_embedding_failure_...`, `test_a_generation_failure_keeps_...`, `test_cancelling_during_the_answer_...`.

## Règles écrites

**`relevance_label`** (`rag/passage.py`, seuils dans `[rag]` de `wavelocalai.toml`). La distance cosinus de l'index devient `s = 1 − distance`, ramenée dans [0, 1] (négatif = 0). `s ≥ 0,70` → « très proche » ; `s ≥ 0,60` → « proche » ; sinon « éloignée » (seuils inclus dans la classe haute). La règle ne regarde que le score de l'extrait, pas les autres résultats ; elle est monotone (un rang plus bas n'a jamais un meilleur libellé). Seuils calés le 2026-10-19 sur `nomic-embed-text` (voir le journal) ; un autre modèle se règle dans le `.toml` (`relevance_very_close` > `relevance_close`, validé au chargement). `raw_score` est la similarité brute `1 − distance`, arrondie à 4 décimales.

**`passage`** (`rag/passage.py`, D-21). La phrase de l'extrait qui partage le plus de termes avec la question, sinon `null` :

1. phrases : coupe après `. ! ? …` suivi d'un espace, et à chaque saut de ligne ; espaces de bord exclus des positions ;
2. termes : minuscules, accents retirés, mots d'au moins 3 lettres ou chiffres, hors mots vides (français, anglais), tronqués à 6 caractères (« voiture » = « voitures ») ;
3. score d'une phrase : nombre de termes distincts de la question qu'elle contient ; la plus haute gagne, à égalité la plus proche du début ;
4. `null` si aucune phrase n'a de point, ou si la phrase gagnante est tout l'extrait (rien à mettre en valeur).

Positions : indices de `str` Python dans `text`, `end` exclu (`text[start:end]` est la phrase). `null` = pas de surlignage, l'extrait s'affiche entier.

## Notes de développement

- **Composite** : racine `rag` + feuilles `embedding` et `generation` créées au `start` (comme l'Arène), toutes deux déclarées `CANCELLED_CO2`. La racine publie seule ; la tâche unique est attachée à la racine, `hub.cancel` l'interrompt. Génération `ok` → `finish_run("ok")` ; génération en erreur → `finish_run("error", error=leaf.error)`.
- **Feuille d'embedding partagée** : `rag/embedding_leaf.py::embed_into_leaf` (place par appel, tracker dedans, délai de lane, `finish_leaf`, annulation) est extraite d'`IngestService._embed_batch`, qui l'appelle désormais ; comportement inchangé (tests 4.1 verts).
- **Recherche** : `Store.aread_with` (nouvelle lecture multi-requêtes sur une connexion courte, `vec=` si l'extension est chargée) ; `rag/repo.py::search_chunks` passe au KNN le filtre `among` (identifiants des extraits de documents `ready`), appliqué avant la sélection des `top_k` (`rowid IN (...)` de vec0, ensemble admis pour `NumpyIndex`), puis relit les extraits. L'index est partagé avec l'ingestion (`select_index` appelé une fois dans `app.py` : indispensable pour le repli en mémoire).
- **Prompt `naive`** : consigne système en français (réponds d'après les extraits seuls, cite `[n]`, dis si les extraits ne suffisent pas), puis `[n] (document, page p)` + texte de chaque extrait, puis `Question : …`. Température 0,1. Sans historique.
- **Métriques** : `stream_into_run(metrics_extra=)` ajoute `retrieval_s` à l'événement `metrics` sans jamais remplacer un champ du flux.
- **Rejeu** : `RunHub.events_after` réhydrate `text` des `sources` (une requête par tranche de 500 `chunk_id`) quand l'événement vient de la base ; un run actif sert la mémoire (texte déjà présent).
- **Écarts ouverts de `sprint-change-proposal-2026-10-19.md` §7(d), point 12 (Discussion), non tranchés** : (a) avertissement cloud « les extraits de vos documents lui sont envoyés » : le serveur applique seulement `allow_cloud` (AD-9), l'avertissement est du front ; (b) « Télécharger » : aucune route d'export RAG ajoutée ; (c) marqueur `[n]` non vérifié : variante la plus conservatrice, le texte de la réponse est publié tel que le modèle l'écrit, aucun événement `citations` (4.6) ; la consigne demande les `[n]` (une ligne de `SYSTEM_PROMPT` à retirer si Anaël préfère aucune mention) ; (d) moment de `retrieval_step` : variante conservatrice, une fois **à la fin** de chaque étape (durée connue), jamais au début.

## Fichiers

- `src/wavelocalai/rag/query.py` (nouveau : `RagService`, `RagCommand`, `chunk_view`), `rag/passage.py` (nouveau : règles de libellé et de passage), `rag/embedding_leaf.py` (nouveau, extrait de l'ingestion), `rag/repo.py` (`search_chunks`, SQL de la base prête et d'un extrait), `rag/ingest.py` (appelle `embed_into_leaf`)
- `src/wavelocalai/runs/hub.py` (`events_after` réhydrate `sources`), `inference/streaming.py` (`metrics_extra`), `store/db.py` (`read_with`, `aread_with`)
- `src/wavelocalai/web/routes_rag.py` (`POST /api/rag/runs`, `GET /api/rag/chunks/{id}`), `web/app.py` (`app.state.rag`, index partagé), `errors.py` (`rag_base_empty`, `chunk_not_found`), `config.py` + `wavelocalai.toml` (`top_k`, seuils)
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md` (événements, codes, routes de la Discussion)
- Tests : `tests/v2/unit/test_passage.py`, `tests/v2/web/test_rag_run_api.py`, `tests/v2/integration/test_rag_question_ollama.py`

## Vérification

`pytest tests/v2` : 859 passés (dont 46 ajoutés : 22 de règles, 24 web ; les 172 tests E2E et d'intégration sont exclus par `pytest.ini`). Intégration réelle (`-m integration`, Ollama `http://127.0.0.1:11434`, `qwen2.5:1.5b` et `nomic-embed-text:latest` déjà installés, rien de téléchargé) : `test_rag_question_ollama.py` et `test_rag_ollama.py` (4.1, après l'extraction de la feuille d'embedding) verts. Contrôle rapide propre. Sans sqlite-vec (CI macOS) : `test_the_whole_path_works_with_the_numpy_fallback_index` force `NumpyIndex`.

## Journal

- 2026-10-19 · calibrage des libellés sur le vrai `nomic-embed-text` (Ollama local, 5 extraits, 7 questions) : similarité cosinus des extraits pertinents 0,63 à 0,80 (0,72 « où dort le chat » contre l'extrait sur le sommeil, 0,79 pour la recharge d'une voiture, 0,73 pour le délai d'intervention), des hors-sujet de 0,42 à 0,65. Seuils fixés à 0,70 et 0,60 (les premiers essais à 0,75 et 0,55 classaient « proche » des extraits sans rapport à 0,55 à 0,56).
- 2026-10-19 · dev : spec, code, tests unitaires et web ciblés verts ; test d'intégration réel (Ollama `127.0.0.1:11434`, `qwen2.5:1.5b`, `nomic-embed-text:latest` déjà installés, aucun téléchargement) vert.

## Revue

- medium · second avis · corrigé · plus de 4096 extraits `indexing` plus proches que les extraits prêts : KNN plafonné, `found` vide, `rag_base_empty` à tort (reproduit, sqlite-vec et numpy). `VectorIndex.search(..., among=)` filtre avant la sélection (`rowid IN (sous-requête)` de vec0 0.1.9, vérifié) ; `test_rag_search.py` (4200 extraits en cours).
- low · second avis · corrigé · feuille `generation` jamais jouée (échec de l'embedding ou recherche vide) close avec « réponse annulée avant la fin » : raison « réponse non lancée : la recherche a échoué » (statut `cancelled` gardé, l'état du hub n'a pas d'autre statut de feuille non jouée).
- low · second avis · corrigé · mots vides accentués jamais reconnus (« était ») : liste repliée comme les termes, « dont » ajouté ; test.
- low · second avis · rejeté · validation `relevance_close < relevance_very_close` : déjà présente (`RagSettings._thresholds_ordered`, testée).
- low · second avis · reporté · repli `NumpyIndex` après redémarrage → `rag_base_empty` : déjà dans `deferred` (4.2/4.3).
- Complexité : 0 constat. Le comptage plein des extraits non prêts à chaque question disparaît avec le filtre ; `_rehydrate_sources` est linéaire par rejeu, par tranches de 500.
