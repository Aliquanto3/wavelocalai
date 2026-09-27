---
title: 'Ingestion RAG réelle'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: 'c3df9c63c9bacff3078e0de90395a4de0a0c5d74'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      La question du document de test, sa réponse et ses sources dans l'onglet Discussion ne sont pas testées.
    evidence: |-
      Exige un LLM (Ollama) ; seule la recherche est vérifiée sans modèle.
    location: >-
      src/app/tabs/rag/chat.py
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** L'import de documents de l'Assistant documentaire est factice : `time.sleep` à la place de l'ingestion, puis un message de succès ; aucun document n'est jamais indexé (F1). Le nom d'embedding par défaut diffère entre l'initialisation (`all-MiniLM-L6-v2`) et la liste de la barre latérale (`sentence-transformers/all-MiniLM-L6-v2`), ce qui crée deux collections Chroma pour le même modèle (F12).

**Approach:** Écrire chaque `UploadedFile` dans un fichier temporaire, appeler `RAGEngine.ingest_file`, afficher le nombre d'extraits réellement ajoutés et une erreur par fichier en échec ; un seul nom d'embedding par défaut, partagé par le moteur et la page.

## Boundaries & Constraints

**Always:** succès annoncé seulement après l'aboutissement réel, avec le compte réel (« N extraits ajoutés depuis M documents », pluriels accordés via `src/app/formatting.py`) ; échec d'un fichier = `st.error` qui nomme le fichier et la raison, sans bloquer les autres ; fichiers temporaires supprimés même en cas d'erreur ; le résultat reste visible après le `st.rerun` ; tests dans une collection Chroma sous `tmp_path`, embeddings simulés, sans réseau.

**Never:** écrire dans `data/chroma` pendant les tests ; ajouter un format d'import (non-goal) ; ajouter la confirmation du vidage (story 8) ; toucher `src/core/config.py` ou le benchmark ; affaiblir la vérification de chemin de `IngestionPipeline._validate_path`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Import réussi | 1 fichier `.md` non vide | Extraits ajoutés à la collection ; « N extraits ajoutés depuis 1 document » ; compteur de la barre latérale augmenté | — |
| Plusieurs fichiers | 2 fichiers valides | Compte total et « 2 documents » | — |
| Fichier vide | `.txt` sans texte | Aucun extrait ajouté | `st.error` : fichier et « aucun texte extrait » ; pas de succès |
| Fichier illisible | loader qui lève une exception | Les autres fichiers sont indexés | `st.error` par fichier en échec, raison lisible ; compteur inchangé pour ce fichier |
| Tous en échec | tous les fichiers échouent | Aucun message de succès | erreurs seulement |
| Recherche | après import du `.md` de test | `RAGEngine.search` renvoie un extrait dont `metadata["source"]` est le nom du fichier importé | — |
| Nom d'embedding | défaut du moteur et de la page | Même nom, donc même collection | — |

</intent-contract>

## Code Map

- `src/app/views/03_RAG_Knowledge.py:88-136` -- dialogue `open_knowledge_manager` : boucle factice (l.109-124, `time.sleep`, « Indexation terminée. » en dur, `st.rerun`). À remplacer par : pour chaque fichier, `tempfile.NamedTemporaryFile(suffix=<extension d'origine>, delete=False)` dans `tempfile.gettempdir()`, `write(file.getvalue())`, `rag_engine.ingest_file(tmp_path, file.name)`, suppression dans `finally` ; résultat (ajoutés, fichiers réussis, erreurs) stocké dans `st.session_state` puis affiché après le rerun (la fermeture du dialogue perd tout message affiché avant `st.rerun`). `progress-status` (`st.status`) par fichier.
- `src/app/views/03_RAG_Knowledge.py:60-75` -- initialisation : défaut `"all-MiniLM-L6-v2"` ; `:159-171` : liste de repli de la barre latérale `["sentence-transformers/all-MiniLM-L6-v2"]` → nom différent, collection différente (`VectorStoreManager` dérive le nom de collection du nom du modèle, `src/core/rag/vector_store.py:17-22`).
- `src/core/rag_engine.py:23-25,74-79` -- `RAGEngine(embedding_model_name="all-MiniLM-L6-v2")` ; `ingest_file(file_path, original_filename) -> int` renvoie le nombre d'extraits ajoutés. Exposer une constante `DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"` utilisée par le moteur et par la page (valeur actuelle du moteur : ne pas changer la collection par défaut existante).
- `src/core/rag/ingestion.py:21-80` -- `_validate_path` n'accepte que le dossier temporaire système et `DATA_DIR` ; `process_file` gère `.pdf`, `.txt`, `.md`, `.docx` ; renvoie `[]` pour une extension inconnue ; propage les erreurs de validation ; métadonnée `source` = nom d'origine (à vérifier dans le reste de la fonction).
- `src/app/formatting.py` -- `pluralize`, `format_number`.
- `tests/app/conftest.py` -- embeddings `DeterministicFakeEmbedding`, `vector_store.CHROMA_DIR` redirigé vers `tmp_path`, pas de reranker : base pour les tests.
- `src/app/views/03_RAG_Knowledge.py:_base_summary` -- légende « N documents indexés · M extraits » de la barre latérale (story 3).

## Tasks & Acceptance

**Execution:**
- `src/core/rag_engine.py` -- constante `DEFAULT_EMBEDDING_MODEL`, défaut du constructeur.
- `src/app/views/03_RAG_Knowledge.py` -- ingestion réelle par fichier temporaire, résultat persistant, erreurs par fichier ; défaut et liste de repli sur `DEFAULT_EMBEDDING_MODEL`.
- La logique d'ingestion d'une liste de fichiers téléversés (écriture temporaire, appel, agrégation du résultat) dans une fonction testable sans Streamlit (par exemple `src/app/rag_upload.py` ou dans `src/core/rag_engine.py`), la vue ne faisant que l'afficher.
- `tests/unit/test_rag_upload.py` -- chaque ligne de la matrice, avec un vrai `RAGEngine` sur Chroma en `tmp_path` et `DeterministicFakeEmbedding` (monkeypatch de `RAGModelsFactory` et de `vector_store.CHROMA_DIR`) ; vérifier aussi que les fichiers temporaires sont supprimés.
- `tests/app/` -- AppTest de la page : après import simulé du `.md` de test (appel de la fonction d'ingestion via la session, ou `file_uploader` si AppTest le permet en 1.64.0), la légende de la barre latérale augmente et le message de résultat est affiché.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec et aucun fichier créé sous `data/chroma`.
- Given le code de la page, when on cherche `time.sleep`, then il n'apparaît plus dans le chemin d'import.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 33 findings — high 1, medium 7, low 17, false 3, maybe-false 5
- findings:
  - `[maybe-false]` `[defer]` (intent) « interrogeable » : question, réponse et sources de l'onglet Discussion non testées — exige un LLM ; recherche vérifiée au cœur ; parcours e2e (story 11) et matin.
  - `[low]` `[reject]` (intent) sens de l'alignement F12 (page sur moteur) — tranché par la story pour ne pas changer la collection existante.
  - `[false]` `[reject]` (intent) parcours réel non testé — vérifié au navigateur (import `.md` puis `.md` + `.docx`, compteur et message).
  - `[low]` `[reject]` (intent) succès et erreurs affichés ensemble pour un lot mixte — conforme à la matrice (erreur par fichier).
  - `[medium]` `[patch]` (intent, blind, edge, verification-gap) erreurs de lecture avalées en « aucun texte extrait » — `DocumentReadError` remontée avec le détail ; raisons assertées.
  - `[low]` `[patch]` (verification-gap) rotation de clé du sélecteur non observée — clé enregistrée et vérifiée.
  - `[low]` `[patch]` (verification-gap) garde du clic jamais en échec — clic forcé désactivable, test sans clic.
  - `[low]` `[patch]` (verification-gap) `FileResult.summary()` non testé — assertions ajoutées.
  - `[false]` `[reject]` (verification-gap) tests sur le texte du code — le comportement est aussi couvert par AppTest.
  - `[low]` `[patch]` (edge, blind) run interrompu : rapport perdu — rapport enregistré après chaque fichier.
  - `[medium]` `[patch]` (edge, blind) réimport d'un document : extraits doublés — refus avec « déjà présent dans la base documentaire ».
  - `[low]` `[reject]` (edge) nom « .md » sans suffixe — cas improbable.
  - `[low]` `[patch]` (edge) caractères Markdown dans le nom de fichier — échappement.
  - `[low]` `[patch]` (edge) sélection perdue après un échec total — génération incrémentée seulement après un succès.
  - `[low]` `[reject]` (edge) dépassement de la taille maximale de lot Chroma — hors des documents de démonstration visés.
  - `[medium]` `[patch]` (edge, blind) la page n'appelle pas la fonction testée — `ingest_uploaded_files` avec rappels par fichier.
  - `[high]` `[patch]` (blind) tout import `.docx` échoue (`docx2txt` absent) avec un message trompeur — `docx2txt>=0.9` ajouté (PyPI vérifié), contraintes régénérées (seule ligne ajoutée), test d'un vrai `.docx`.
  - `[medium]` `[patch]` (blind) chemin temporaire supprimé stocké dans les métadonnées (nom d'utilisateur sous Windows) — chemin conservé seulement sous `DATA_DIR`.
  - `[low]` `[reject]` (blind) cas limites non testés (majuscules, vrai PDF, `os.remove` en échec) — `.docx` réel et non UTF-8 ajoutés ; le reste est de faible risque.
  - `[low]` `[reject]` (blind) helpers de test dupliqués — sans effet sur le comportement.
  - `[low]` `[reject]` (blind) aucune limite de taille d'import, `get_stats` appelé trois fois — préexistant pour `get_stats` ; limite hors périmètre.
  - `[maybe-false]` `[reject]` (intent) `st.status` par fichier à peine visibles avant le rerun — le compte rendu persistant les remplace.
  - `[maybe-false]` `[reject]` (intent) liste d'embeddings locaux non testée — cas `data/models` absent de la VM.
  - `[maybe-false]` `[reject]` (verification-gap) raison du fichier illisible — doublon, corrigé.
  - `[low]` `[reject]` (edge) shortcode `:smile:` dans un nom de fichier — cosmétique et improbable.
  - `[false]` `[reject]` (blind) test du fichier illisible mal nommé — doublon, raison désormais assertée.
  - `[maybe-false]` `[reject]` (intent) libellé « Indexer » contre « ajoutés » — texte de résultat imposé par la story ; lexique à valider au matin.
  - `[low]` `[patch]` (blind) `.txt` non UTF-8 — test ajouté (erreur de lecture).
  - `[low]` `[reject]` (blind) `dir=tempfile.gettempdir()` redondant — explicite pour `_validate_path`.
  - `[low]` `[patch]` (blind) doublon dans un même lot — refusé.
  - `[low]` `[reject]` (blind) extension en majuscules non testée — gérée par `.suffix.lower()`.
  - `[low]` `[patch]` (edge) extension non gérée : `[]` conservé — test ajouté.
  - `[low]` `[reject]` (verification-gap) callbacks — couverts par `test_callbacks_follow_each_file`.

## Design Notes

Un `st.rerun()` pendant un `st.dialog` ferme le dialogue : le message de résultat doit être posé dans `st.session_state` (par exemple `rag_last_ingest`) et affiché au run suivant, en tête de la page ou dans la barre latérale, puis retiré après affichage.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `grep -n "time.sleep" src/app/views/03_RAG_Knowledge.py` -- expected: aucune ligne
- `find data/chroma -newer /tmp/nuit/start -type f | head` -- expected: aucun fichier créé par la suite (hors fichiers préexistants)

**Manual checks (if no CLI):**
- Navigateur avec le lanceur à providers simulés (`/tmp/nuit/axe/launch_fake.py`, Chroma temporaire) : import d'un `.md`, message « N extraits ajoutés depuis 1 document », compteur de la barre latérale augmenté.

## Auto Run Result

Status: done

**Résumé :** l'import de l'Assistant documentaire indexe réellement : chaque fichier passe par un fichier temporaire vers `RAGEngine.ingest_file`, le compte rendu affiche le nombre réel d'extraits (« N extraits ajoutés depuis M documents ») et une erreur par fichier en échec (lecture impossible, aucun texte, déjà présent) ; le nom d'embedding par défaut est partagé (`DEFAULT_EMBEDDING_MODEL`) ; l'import `.docx` fonctionne (`docx2txt`).

**Fichiers :** `src/app/rag_upload.py` (nouveau) ; `src/app/views/03_RAG_Knowledge.py` ; `src/core/rag_engine.py` ; `src/core/rag/ingestion.py` (erreurs de lecture remontées, chemin temporaire non stocké) ; `requirements.txt`, `constraints.txt` (`docx2txt==0.9`) ; tests `tests/unit/test_rag_upload.py`, `tests/app/test_rag_upload_page.py`.

**Revue :** 17 correctifs (1 high, 5 medium, 11 low), 1 différé, 15 rejetés.

**Suivi recommandé :** true — un correctif high (dépendance `docx2txt`) : vérifié par un test sur un vrai `.docx` et au navigateur, mais l'installation Windows de `docx2txt` et un vrai PDF restent à essayer au matin.

**Vérification :** `pytest tests/unit tests/app` : 336 réussis ; rien sous `data/chroma` ; navigateur (providers simulés, Chroma temporaire) : 0 → « 2 extraits ajoutés depuis 2 documents. » → « 2 documents indexés · 2 extraits » avec un `.md` et un `.docx`.

**Risques :** la question du document de test et ses sources dans l'onglet Discussion exigent Ollama (matin) ; vider la base sans confirmation jusqu'à la story 8.
