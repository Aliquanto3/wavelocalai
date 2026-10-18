---
title: 'Indexer un document dans la base locale (serveur)'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'a7ab77b'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-3.md'
warnings: []
deferred:
  - summary: >-
      Écarts additifs à `contrat-api.md`, à ratifier : l'événement `ingest_progress` porte `file` (et non `fichier`, convention « JSON en anglais snake_case »), `file_index`, `file_count`, `phase`, `done`, `total` ; `extract` et `split` valent 0/1 puis 1/1 (pas de progression par page), `embed` compte les extraits vectorisés. Nouvel événement `ingest_file_done {file, file_index, file_count, document_id, status: ready|failed|duplicate, chunks, error}` (l'enveloppe `ingest_failed` d'AD-18 en cas d'échec) : sans lui l'écran 4.2 ne saurait pas la fin ni la raison d'un fichier sans relire la liste.
    evidence: |-
      `rag/ingest.py` (docstring), `test_ingest_service.py::test_progress_events_follow_each_file_through_its_phases`, `test_rag_api.py::test_several_files_are_imported_...`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Résidu de texte dans le journal WAL après un échec ou une annulation : les extraits d'un document `failed` ou annulé sont supprimés (`secure_delete` efface les pages de la base) mais le `-wal` garde les anciens cadres jusqu'au prochain point de contrôle. L'ordre `DELETE` / `wal_checkpoint(TRUNCATE)` / `VACUUM` d'AD-13 et son test d'octets sont ceux de la story « Effacer » (4.4) ; le résidu vectoriel dans le blob vec0 après suppression par `rowid` (Deferred de la spine) y est vérifié aussi.
    evidence: |-
      `rag/repo.py::delete_chunks` (suppression transactionnelle, vecteurs puis extraits) ; aucun test d'octets ici.
    location: src/wavelocalai/rag/repo.py
    severity: medium
  - summary: >-
      Une annulation qui arrive pendant le démarrage du tracker CodeCarbon (avant le premier appel d'embedding) perd la mesure de ce lot : il garde le `co2` de remplacement `unmeasurable` (« réponse annulée avant la fin »), comme le chat. Au-delà, la mesure faite jusqu'à l'arrêt est écrite (`amend_cancelled_leaf`).
    evidence: |-
      `test_cancelling_a_batch_keeps_the_energy_measured_until_the_stop`.
    location: src/wavelocalai/rag/ingest.py
    severity: low
  - summary: >-
      Le plafond d'un fichier (`rag.max_file_mb`, 50) est appliqué à la réception : Starlette a déjà reçu tout le corps multipart (fichiers temporaires) avant la route, il n'y a pas de limite de requête (`413`). Suffisant pour un poste mono-utilisateur sur 127.0.0.1 ; à reprendre si l'API s'ouvre.
    evidence: |-
      `rag/staging.py`, `test_rag_api.py::test_an_oversized_file_fails_with_its_reason`.
    location: src/wavelocalai/rag/staging.py
    severity: low
  - summary: >-
      Le port `Embedder` d'AD-8 rend les vecteurs seulement : une feuille `embedding` n'a ni `input_tokens` ni `tps` (durée totale mesurée par le service, `total_s`). Un compte de jetons exigerait d'élargir le port (`/api/embed` rend `prompt_eval_count`).
    evidence: |-
      `models/port.py::Embedder`, `models/ollama_embed.py`.
    location: src/wavelocalai/models/port.py
    severity: low
  - summary: >-
      `master` a avancé pendant la story (PR #55, chat cloud 2.4) : `web/app.py`, `errors.py`, `models/factory.py`, `models/fake.py` et `models/port.py` sont touchés des deux côtés ; les ajouts de cette story y sont isolés (voir « Fichiers »).
    evidence: |-
      Branche partie de `a7ab77b` ; `master` à `33adc49`.
    location: src/wavelocalai/web/app.py
    severity: low
---

# Story 4.1 : indexer un document dans la base locale (serveur)

## Objectif

`POST /api/rag/documents` (multipart, plusieurs fichiers) importe des PDF, DOCX, TXT et MD : un run racine `ingest` lit les fichiers un par un (extraction et découpe dans le pool de threads, puis embedding par lots), chaque lot est une feuille `embedding` mesurée par CodeCarbon sous le sémaphore, et un fichier qui échoue passe à `failed` avec sa raison sans arrêter les autres. Aucun écran : l'écran « Base documentaire » est la story 4.2.

## Critères d'acceptation et preuves

1. **Migration `0004_documents.sql`** : `documents` (`source`, `fingerprint` SHA-256, `embedding_model`, `embedding_dim`, `status` `indexing`/`ready`/`failed`, `chunk_count`, `page_count`, `error` JSON d'AD-18, `run_id`, dates) et `chunks` (`id` AUTOINCREMENT = `rowid` vec0, `document_id` en cascade, `position`, `page`, `text`). Index unique partiel sur l'empreinte des documents non `failed` : un contenu présent n'est pas indexé deux fois, un échec ne bloque pas un nouvel essai ; un `failed` exige son erreur, un `ready` sa dimension. Instantané `schema_v4.sql`. Preuve : `test_schema.py` (v4), `test_documents_schema.py` (6).
2. **`store.ensure_vec_table(dim)`** (`store/vec.py`, `Store.ensure_vec_table`) crée `chunks_vec_<dim>` (vec0, cosinus, `rowid = chunks.id`) de façon idempotente ; aucune migration ne crée de table virtuelle. L'écrivain charge sqlite-vec ; `Store.read(..., vec=True)` le charge pour une lecture. Preuve : `test_vector_index.py` (création, idempotence, tables d'ombre écartées, dimension refusée, survie à la réouverture).
3. **Port `VectorIndex`** (`rag/index.py`) : `add` (crée la table de la dimension au premier lot), `remove` (par `rowid`, toutes dimensions), `search` (distance cosinus), `count`, sur la connexion de l'écrivain pour que vecteurs et extraits partent dans la même transaction (AD-13). Deux implémentations, `SqliteVecIndex` (sqlite-vec) et `NumpyIndex` (repli des tests, `numpy` importé dans les méthodes), qui rendent les mêmes réponses. Preuve : `test_vector_index.py` (20, deux implémentations, accord croisé).
4. **`Embedder`** (`models/port.py`, AD-8) : `OllamaEmbedder` (`/api/embed`, pannes en `ProviderError` : `ollama_down`, `model_not_found`, `ollama_error`, vecteurs absents ou de longueurs différentes) et `FakeEmbedder` scriptable (sac de mots hachés en SHA-256, 16 dimensions, normalisé), enregistré **seulement si `Settings.testing`** (`fake_embedders`). `ModelFactory.embedder(ref)`. `registry.resolve_embedder(tag)` reste le seul accès (cloud refusé, `model_not_embedding`). Preuve : `test_embedder.py` (12), `test_ingest_service.py::test_the_registry_refuses_...`.
5. **Route** : `POST /api/rag/documents` (`files`, `embedding_model` optionnel) copie les fichiers dans un dossier temporaire (nom neutre `0001.pdf`, empreinte SHA-256, plafond `rag.max_file_mb` = 50 Mo), crée le run et rend `{run_id}` ; un refus (`run_busy` 409, `embedding_locked`, modèle inconnu, aucun fichier 422) supprime le dossier. Modèle d'embedding : le champ du formulaire, sinon celui de la base (une base = un modèle, AD-16 : un autre modèle sur une base non vide donne `409 embedding_locked`), sinon `rag.embedding_model` des réglages, sinon le premier modèle d'embedding installé (`no_embedding_model` 404 s'il n'y en a pas). Preuve : `test_rag_api.py` (11), `test_ingest_service.py::test_the_model_defaults_...`.
6. **Pipeline** (`rag/ingest.py`) : chaque fichier passe par `validate_path` (copiée de la v1, dossiers autorisés passés en argument : dossier temporaire du système et dossier de données), l'extraction (`pypdf` : texte par page, mot de passe vide essayé ; `python-docx` : paragraphes puis tableaux ; TXT/MD en UTF-8 puis Windows-1252) et la découpe récursive (800 caractères, recouvrement 100, une page de PDF découpée seule, sans langchain) dans `asyncio.to_thread`. `pypdf` et `docx` sont importés dans leurs fonctions (`test_layers.py`). Le flux publie `ingest_progress {file, phase: extract|split|embed, done, total}` par fichier. Preuve : `test_rag_files.py` (31), `test_ingest_service.py::test_progress_events_...`, `::test_pdf_and_docx_...`.
7. **CO₂** : chaque lot (`rag.embed_batch_size` = 16 extraits) est une feuille `embedding` du run, mesurée par `LocalMeter` **dans la place du `LocalSlot`** (prise par lot, pas par run), un tracker à la fois, `carbon_updated` après chaque feuille, comptée dans le CO₂ de session (module `ingest`). Un import sans lot (doublons, échecs avant embedding) n'est pas compté comme feuille non mesurable (`greenops/session.py`). Preuve : `test_ingest_service.py` (nominal, session, panne CodeCarbon, import sans lot), `integration/test_rag_ollama.py` (vrai CodeCarbon, vrai Ollama).
8. **Échecs** : fichier protégé par mot de passe, vide, sans texte (PDF numérisé), de format refusé, trop gros, ou embedding en panne : le document passe à `failed` avec l'enveloppe `ingest_failed` (`detail.reason` lisible, `detail.technical` replié), ses extraits partiels et leurs vecteurs sont supprimés, les autres fichiers continuent, le run finit `ok`. Preuve : `test_unreadable_files_fail_one_by_one_...`, `test_an_embedding_failure_removes_the_partial_...`, `test_partial_chunks_are_never_queryable_...`.
9. **Annulation et concurrence** : annuler laisse les documents `ready` intacts et retire le document en cours (lignes, extraits, vecteurs) ; les fichiers suivants ne sont pas commencés ; tracker arrêté, place rendue, dossier temporaire supprimé. Un chat local s'intercale entre deux lots (le sémaphore est pris par lot). Un second import actif rend `409 run_busy` avec le `run_id`. Un contenu déjà présent (même empreinte, autre nom) donne `ingest_file_done {status: "duplicate"}` sans embedding ; un échec précédent du même contenu est remplacé. Au démarrage, un document resté `indexing` passe à `failed` sans extraits (`IngestService.recover`). Preuve : `test_cancelling_...` (2), `test_the_slot_is_taken_per_batch_...`, `test_a_second_import_...`, `test_a_document_already_present_...`, `test_a_failed_document_can_be_imported_again_...`, `test_a_document_left_indexing_...`.

## Dépendances (versions revérifiées le 2026-10-18 sur PyPI et par installation `uv`)

- `sqlite-vec==0.1.9` (ajoutée, épinglée comme la spine) ; `python-multipart>=0.0.32` (ajoutée : la route multipart l'exige, elle n'arrivait que par `streamlit` et `mcp`) ; `pypdf` 6.21.1 et `python-docx` 1.2.0 déjà au `pyproject` (`>=4.0.0`, `>=1.0.0`), versions installées = dernières publiées, inchangés ; `numpy` 2.5.4 déjà présent (repli de tests).
- Ni Chroma ni Hugging Face ne sont importés : `disable_telemetry()` n'est pas requis.

## Fichiers

- `src/wavelocalai/store/migrations/0004_documents.sql`, `store/vec.py` (nouveaux), `store/db.py` (extension chargée par l'écrivain, `ensure_vec_table`, `read(vec=)`)
- `src/wavelocalai/rag/` : `extract.py`, `split.py`, `staging.py`, `index.py`, `repo.py`, `ingest.py` (nouveaux)
- `src/wavelocalai/models/ollama_embed.py` (nouveau), `models/port.py` (`Embedder`), `models/fake.py` (`FakeEmbedder`, `fake_embedders`), `models/factory.py` (`embedder`)
- `src/wavelocalai/web/routes_rag.py` (nouveau), `web/app.py` (service dans le cycle de vie, `recover`, fabrique partagée), `errors.py` (`ingest_failed`, `no_embedding_model`, `embedding_locked`), `config.py` + `wavelocalai.toml` (`[rag]`), `greenops/session.py` (une ligne de SQL)
- `pyproject.toml`, `uv.lock`
- Tests : `tests/v2/rag_files.py`, `unit/{test_rag_files,test_vector_index,test_ingest_service,test_embedder,test_documents_schema}.py`, `unit/snapshots/schema_v4.sql`, `web/test_rag_api.py`, `integration/test_rag_ollama.py`

## Vérification

`pytest tests/v2` : 646 passés (dont 136 ajoutés ; les 155 E2E Playwright sont exclus par `pytest.ini`, la story n'a pas d'écran). Le test d'intégration d'embedding réel a tourné contre `nomic-embed-text:latest` (déjà installé, rien n'est téléchargé) ; sans modèle d'embedding installé il saute avec sa raison.
