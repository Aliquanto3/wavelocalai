---
title: 'Supprimer un document, vider la base, changer de réglages'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: 'fff8faa'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-1.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-2.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-4.md'
warnings: []
deferred:
  - summary: >-
      Écart ouvert n° 13 de `sprint-change-proposal-2026-10-19.md` §7(d), non tranché (Supprimer et Vider désactivés pendant un import, comme la maquette, ou `409` affiché, comme le contrat). Variante la plus conservatrice gardée : le contrat. Aucun bouton n'est désactivé par le front ; pendant un import ou une question, le serveur répond `409 base_in_use` et `wl-error` l'affiche. Passer à la maquette = désactiver `.docs-delete`, `.docs-clear` et le formulaire de réglages quand `busy()` (une ligne chacun, avec la phrase « Disponible à la fin de l'import. »). Seul « Supprimer » d'un document `indexing` n'existe pas (« Annuler l'import » l'arrête).
    evidence: |-
      `documents-manage.js` (en-tête), `test_clearing_during_an_import_shows_the_409_and_deletes_nothing`, `test_a_document_being_indexed_has_no_delete_button`.
    location: src/wavelocalai/web/static/screens/documents-manage.js
    severity: medium
  - summary: >-
      Interprétation de « document visé par un run actif » (AD-13) : un document est refusé (`409 base_in_use`) s'il est `indexing` (son import tourne) ou si un run `rag` est actif (la question lit toute la base) ; un document `ready` ou `failed` se supprime pendant l'import d'autres fichiers. « Vider » et le changement d'embedding refusent tout run `ingest` ou `rag` actif (AD-16). À durcir (refuser tout effacement pendant un import) si Anaël préfère la lecture la plus stricte.
    evidence: |-
      `rag/manage.py` (`delete_document`, `clear`, `update_settings`).
    location: src/wavelocalai/rag/manage.py
    severity: low
  - summary: >-
      Report 4.1/4.2/4.4 « refus explicite sans sqlite-vec » : variante conservatrice. Le repli `NumpyIndex` reste utilisable (aucune régression : tests, CI macOS), mais (1) une question sur une base « prête » dont les vecteurs ont disparu (redémarrage) est refusée avant tout run par `409 vector_index_lost` (au lieu de « aucun document prêt ») ; (2) `GET /api/rag/settings` expose `index.persistent` et l'écran affiche, dans les réglages, que l'index est en mémoire et que les documents seront à réimporter après un redémarrage. Un import n'est pas refusé sans sqlite-vec : `sqlite-vec` étant une dépendance épinglée, le cas exige un CPython sans `enable_load_extension` ; refuser l'import hors `testing` (nouveau code, pas de repli silencieux) reste à décider.
    evidence: |-
      `rag/query.py::_check_vectors`, `test_a_base_whose_vectors_were_lost_is_refused_with_its_own_message`, `index.persistent`.
    location: src/wavelocalai/rag/query.py
    severity: low
  - summary: >-
      Quatre codes dans `errors.py`, pas trois : `embedding_change_needs_clear`, `base_count_stale`, `base_in_use` (les trois refus de la story : modèle sur base non vide, `expected_count` périmé, document ou base utilisés par un run actif ; `base_in_use` sert aussi à « Vider » et au changement d'embedding pendant un run, plutôt que `run_busy` dont l'action « Rejoignez-la » ne convient pas), et `vector_index_lost` (report ci-dessus). `embedding_locked` (4.1, import d'un autre modèle) reste tel quel.
    evidence: |-
      `errors.py`, `contrat-api.md` (codes).
    location: src/wavelocalai/errors.py
    severity: low
  - summary: >-
      Maquette non reprise : la ligne « reclassement » des réglages (reranker, AD-17) et les stratégies `hyde` et `self_rag` (liste des stratégies fournie par le serveur, `naive` seule jusqu'aux stories 4.6 et 4.7). Les bornes de l'API sont celles de `RagSettings` (extraits 100 à 8 000 caractères, `top_k` 1 à 20), plus larges que celles de la maquette (200 à 2 000, 1 à 5) ; le formulaire les lit du serveur.
    evidence: |-
      `GET /api/rag/settings` (`strategies`, `limits`), `documents-settings.js`.
    location: src/wavelocalai/web/static/screens/documents-settings.js
    severity: low
  - summary: >-
      Purge incomplète (AD-13) : si un lecteur tient le journal au moment de `wal_checkpoint(TRUNCATE)`, la suppression est validée et rend 200 mais le texte reste dans le `-wal` jusqu'à la prochaine écriture (`Store.purge_pending`, mécanisme de la story 2.6). Aucun signal n'est rendu à l'écran. Le test d'octets ne le provoque pas (aucun lecteur concurrent).
    evidence: |-
      `store/db.py::purge_free_space`, `test_a_purge_blocked_by_a_reader_is_reported_then_replayed`.
    location: src/wavelocalai/store/db.py
    severity: low
  - summary: >-
      La liste des modèles d'embedding du formulaire vient d'Ollama (modèles installés, `kind == "embedding"`) : Ollama arrêté, elle est vide et le formulaire ne propose que « Par défaut » et le modèle de la base. Changer de modèle d'embedding de bout en bout n'est donc pas couvert par l'E2E (un seul modèle `fake`) : le refus du serveur est prouvé côté web (second modèle `fake-other:8`), l'affichage du refus et du bouton « Vider » côté navigateur (réponse `409` simulée).
    evidence: |-
      `test_changing_the_embedding_of_a_non_empty_base_must_clear_first`, `test_a_refused_embedding_change_says_to_clear_first_and_offers_the_button`.
    location: tests/v2/e2e/test_documents_manage.py
    severity: low
---

# Story 4.3 : supprimer un document, vider la base, changer de réglages

## Objectif

Maîtriser ce que contient la base documentaire : supprimer un document (prêt ou en échec) après une confirmation chiffrée, vider toute la base après une confirmation qui dit combien d'extraits et de documents partent, et régler le modèle de représentation, la découpe, le nombre d'extraits et la stratégie par défaut. Une erreur de clic ne détruit rien : « Annuler » reçoit le focus et ne supprime rien. Un effacement efface vraiment (AD-13) : le texte supprimé n'est ni dans le `.db` ni dans le `-wal`.

## Critères d'acceptation et preuves

1. **Supprimer, dialogue (D-24)** : « Supprimer » par ligne `ready` ou `failed` (pas de bouton pour `indexing`) ouvre `wl-confirm-dialog` (`<dialog>` natif, `showModal`, focus sur « Annuler ») : « Supprimer « note-cadrage.docx » ? » ; « 14 extraits seront retirés de la base. Cette action est irréversible. » (« 1 extrait sera retiré… ») ; document en échec : « Ce document n'a pas été indexé : aucun extrait n'est retiré. » « Annuler » (bouton ou Échap) ne supprime rien et annonce « Suppression annulée : <nom> reste dans la base. » (le focus revient au bouton de la ligne) ; confirmer appelle `DELETE /api/rag/documents/{id}` et annonce « Document supprimé : <nom>. 14 extraits retirés de la base. » (document en échec : « Aucun extrait retiré de la base. »), le focus reste dans la liste, ou passe à « Choisir des fichiers » quand la base est vide. Preuve : `test_documents_manage.py` (`test_the_dialog_asks_with_the_numbered_consequence_and_focuses_cancel`, `test_cancel_deletes_nothing_announces_it_and_returns_the_focus`, `test_escape_closes_the_dialog_like_cancel`, `test_confirming_deletes_the_document_and_says_how_many_chunks_went`, `test_deleting_the_last_document_brings_back_the_empty_base`, `test_a_failed_document_can_be_deleted_and_nothing_is_retired`, `test_a_document_being_indexed_has_no_delete_button`).
2. **`DELETE /api/rag/documents/{id}`** : ses `chunks` et, dans la même transaction, leurs lignes vec0 par `rowid` (`delete_chunks`), puis le document ; puis `wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)` passent dans la file de l'écrivain (`Store.write(purge=True)`, story 2.6). Rend `{document_id, source, status, chunks_removed}` ; `404 not_found` si inconnu. Preuve : `test_rag_manage_api.py` (`test_deleting_a_document_removes_its_chunks_and_vectors_and_keeps_the_others`, `test_a_failed_document_is_deleted_with_no_chunk_to_remove`, `test_an_unknown_document_is_a_404`).
3. **Test d'octets et résidu vectoriel** : le texte du document supprimé est absent des octets du `.db` et du `-wal` (le test le voit avant), le `-wal` fait 0 octet, le document voisin est intact. **Résidu vectoriel dans le blob vec0 (point différé de la spine)** : constaté avec sqlite-vec 0.1.9, **aucun** : ni le vecteur entier (16 `float32` du `fake`, 768 pour `nomic-embed-text` réel) ni un fragment de 16 octets ne se retrouvent dans le fichier après la suppression, alors que le vecteur du voisin y est (vec0 met à zéro le vecteur supprimé, le `VACUUM` réécrit le fichier). Preuve : `test_the_deleted_text_is_in_neither_the_database_nor_the_journal`, `test_the_vector_residue_state_in_the_vec0_blob_after_a_delete_by_rowid`, et `integration/test_rag_manage_ollama.py` (vrais vecteurs).
4. **Vider (dialogue)** : « Vider la base documentaire » (au-dessus du tableau, dès qu'un document existe, un document en échec compris) ouvre le même dialogue : « Vider la base documentaire ? », « 340 extraits de 12 documents seront supprimés. » (« 1 extrait de 1 document sera supprimé. »), focus sur « Annuler », « Annuler » ne supprime rien (« Opération annulée : la base documentaire est inchangée. », test sur le serveur), confirmer appelle `DELETE /api/rag/base?expected_count=340` et annonce « Base documentaire vidée : 340 extraits de 12 documents supprimés. » (même verbe) ; le focus passe à « Choisir des fichiers » et l'état vide revient. Preuve : `test_clear_asks_with_the_numbered_consequence_then_cancel_deletes_nothing`, `test_confirming_clears_the_base_and_says_so_with_the_same_verb`.
5. **`DELETE /api/rag/base?expected_count=`** : dans une seule transaction, compare `expected_count` au nombre réel d'extraits (`count(*)` de `chunks`), supprime les extraits et **tous** les documents (statuts compris), puis `VectorIndex.clear` **supprime et recrée** la table vec0 (`DROP TABLE` puis `CREATE`, ou `clear()` du repli), suivi de la même purge. Rend `{documents_removed, chunks_removed}`. Un `expected_count` périmé rend `409 base_count_stale` (`detail.expected`, `detail.actual`) **sans rien supprimer** ; `expected_count` absent ou négatif : `422 invalid_request` ; base vide : 200 à zéro. L'écran relit la base après un `base_count_stale`. Preuve : `test_clearing_deletes_everything_and_recreates_the_vector_table`, `test_clearing_leaves_no_vector_in_the_file`, `test_a_stale_expected_count_deletes_nothing`, `test_the_expected_count_is_required_and_a_number`, `test_an_empty_base_clears_to_zero`, `test_a_stale_count_is_refused_and_the_base_is_read_again` (E2E), `unit/test_vector_index.py::test_clear_empties_the_index_and_keeps_it_usable`.
6. **`GET` et `PUT /api/rag/settings`** : réglages dans `preferences` (clé `rag.settings`, `rag/settings.py`), qui **priment** sur le `.toml` pour ces seules clés (AD-15) : `embedding_model`, `chunk_size`, `chunk_overlap`, `top_k`, `strategy`. L'ingestion les lit à chaque import (découpe, modèle par défaut) et la question à chaque run (`top_k`) ; `runs.params` porte les valeurs en vigueur. `GET` rend aussi l'état de la base, les modèles d'embedding installés, les stratégies disponibles, les bornes et `index.persistent` ; **`top_k` et `strategy` sont lus par la Discussion (4.5) dans cette réponse**. `PUT` ne change que les champs envoyés (`null` rend le choix au `.toml`), valide les bornes et `chunk_overlap < chunk_size` (`422 invalid_request`, rien n'est écrit), vérifie que le modèle est un embedding local. **L'app n'écrit jamais `wavelocalai.toml`** (test sur les octets du fichier du dépôt et sur l'absence de tout `.toml` créé). Preuve : `test_the_settings_start_from_the_toml_defaults`, `test_a_put_keeps_the_other_fields_and_applies_to_the_next_import_and_question`, `test_a_null_gives_the_choice_back_to_the_toml`, `test_a_bad_setting_is_a_422_and_nothing_is_stored` (8), `test_an_unknown_or_chat_model_cannot_be_the_embedding`, `test_the_app_never_writes_the_toml_file`, `unit/test_rag_settings.py` (14).
7. **Changer d'embedding sur une base non vide** : `409 embedding_change_needs_clear` (`detail.current`, `detail.requested`), rien n'est écrit ; le même modèle passe ; une fois la base vidée, le changement passe et sert à l'import suivant. Écran : « Enregistrer » envoie seulement les champs changés ; sur ce refus, `wl-error` dit pourquoi et un bouton « Vider la base documentaire » (déduit du code, D-4) ouvre le dialogue ; la base vidée, les réglages refusés sont rejoués et annoncés à la suite (« … supprimés. Réglages enregistrés. »). Preuve : `test_changing_the_embedding_of_a_non_empty_base_must_clear_first`, `test_a_refused_embedding_change_says_to_clear_first_and_offers_the_button` (E2E).
8. **`409` pendant un run actif** : `base_in_use` (`detail.run_id`, `detail.kind`) pour un document `indexing`, un run `rag` actif (suppression d'un document), un run `ingest` ou `rag` actif (« Vider », changement d'embedding) ; rien n'est supprimé, `wl-error` l'affiche avec son action. Preuve : `test_a_document_still_indexing_is_a_409_with_the_active_import`, `test_a_document_cannot_be_deleted_while_a_question_runs`, `test_clearing_is_a_409_while_an_import_runs_and_nothing_is_deleted`, `test_clearing_is_a_409_while_a_question_runs`, `test_changing_the_embedding_is_a_409_while_an_import_runs`, `test_clearing_during_an_import_shows_the_409_and_deletes_nothing` (E2E).
9. **Sans sqlite-vec** (report 4.1/4.4, voir `deferred`) : `409 vector_index_lost` avant tout run quand la base est « prête » mais que l'index en mémoire n'a plus ses vecteurs ; vider puis réimporter répare ; `index.persistent` faux affiche l'avertissement dans les réglages. Preuve : `test_a_base_whose_vectors_were_lost_is_refused_with_its_own_message`.
10. **Textes et charte** : `docs.*` du catalogue (espaces insécables avant `: ; ? !` et autour des guillemets), `components.confirm.cancel` ; boutons `.btn` sans couleur en dur (`documents.css` et `components.css` au test de dérive), aucune icône ni emoji ; axe-core sans violation, clair et sombre, tableau et réglages ouverts, dialogue « Supprimer » ouvert, dialogue « Vider » ouvert ; 320 px sans défilement horizontal, dialogue contenu dans l'écran. Preuve : `test_axe_finds_nothing_with_the_delete_buttons_the_dialog_and_the_settings` (2), `test_the_dialog_and_the_screen_fit_a_phone_width`, `test_documents_static.py` (plafond de 600 lignes, textes utilisés), `test_shell_static.py`.

## Écarts au contrat

- `contrat-api.md` : formes de `DELETE /api/rag/documents/{id}`, `DELETE /api/rag/base`, `GET`/`PUT /api/rag/settings` et quatre codes (`embedding_change_needs_clear`, `base_count_stale`, `base_in_use`, `vector_index_lost`) consignés (contrat à ratifier).
- Le contrat nommait trois refus ; un quatrième code (`vector_index_lost`) répond au report « refus explicite sans sqlite-vec ».
- `base_in_use` plutôt que `run_busy` pour « Vider », le changement d'embedding et la suppression pendant un run : `run_busy` dit « rejoignez-la », qui n'a pas de sens ici.
- `GET /api/rag/settings` rend plus que les quatre réglages (état de la base, modèles installés, bornes, `index.persistent`) : l'écran et la Discussion n'ont ainsi qu'un appel.

## Notes de développement

- **Course contrôle/écriture** : `RagBaseService` contrôle les runs actifs (`hub.active_root`) puis met l'écriture en file **sans `await` entre les deux** : un import ne peut pas démarrer entre le contrôle et la transaction (l'écrivain exécute ensuite dans l'ordre). Les refus (`document indexing`, `base_count_stale`) sont relevés **dans** la transaction, qui s'annule en entier.
- **Vider** : `index.clear` est le dernier geste de la transaction (l'index en mémoire du repli n'est pas transactionnel). Avec sqlite-vec, `DROP TABLE chunks_vec_<dim>` libère les pages de la table et de ses tables d'ombre ; la même table est recréée vide ; le `VACUUM` du `purge` réécrit le fichier.
- **Réglages en vigueur** : `rag/settings.effective(RagSettings, PreferenceStore)` ; une préférence invalide ou absente retombe sur le `.toml` ; un recouvrement devenu supérieur à la taille est ramené à la moitié. `IngestService` fige les réglages au `start` (tout l'import avec les mêmes), `RagService` lit `top_k` au `start` et le garde dans le run.
- **Front** : `wl-confirm-dialog` (nouveau composant partagé, `<dialog>` natif, sans Shadow DOM, `ask()` rend une promesse booléenne) ; `documents-manage.js` (supprimer, vider, zone d'annonce polie `.docs-manage-status`) et `documents-settings.js` (réglages) sortent de `documents-base.js`, qui reste sous le plafond de 600 lignes. `refresh()` rend désormais la promesse de la lecture en cours (même coalescée), pour que le focus soit posé après le rendu.
- **Colonne « Actions »** du `wl-data-table` : `sortable: false` ; le tableau rend `rows = []` quand la base est vide (plus de bouton caché).
- **Écart §7(d) n° 13 et variante gardée** : voir le premier point de `deferred` ; aucun bouton désactivé, `409` affiché.

## Fichiers

- `src/wavelocalai/rag/manage.py` (nouveau : `RagBaseService`), `rag/settings.py` (nouveau : réglages en vigueur), `rag/index.py` (`persistent`, `clear`), `rag/ingest.py` et `rag/query.py` (lisent les préférences ; `vector_index_lost`), `web/routes_rag_base.py` (nouveau : quatre routes), `web/app.py` (service, `app.state.preferences`), `errors.py` (quatre codes)
- `src/wavelocalai/web/static/components/wl-confirm-dialog.js` (nouveau), `components/index.js`, `components.css`, `screens/documents-manage.js`, `screens/documents-settings.js` (nouveaux), `screens/documents-base.js`, `documents.css`, `core/api.js`, `i18n/fr.json`
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md`
- Tests : `tests/v2/web/test_rag_manage_api.py` (32), `unit/test_rag_settings.py` (14), `unit/test_vector_index.py` (+3), `e2e/test_documents_manage.py` (19), `integration/test_rag_manage_ollama.py` (1) ; réalignés : `e2e/test_documents.py` (colonne « Actions », « Supprimer » présent), `unit/test_documents_static.py` (nouveaux fichiers)

## Vérification

`pytest tests/v2` : 971 passés (les E2E et les tests d'intégration sont exclus par `pytest.ini`). `-m e2e -k documents` sur Edge : 41 passés (22 de la 4.2, 19 de la 4.3), dont axe-core clair et sombre et 320 px. Intégration réelle (`-m integration -k rag`, Ollama `http://127.0.0.1:11434`, `nomic-embed-text` et `qwen2.5:1.5b` déjà installés, rien de téléchargé) : verte (4.1, 4.4 et le nouveau test de suppression avec de vrais vecteurs). Sans sqlite-vec (CI macOS) : les tests qui lisent les tables vec0 portent `needs_vec` ; le repli est exercé par `test_a_base_whose_vectors_were_lost_is_refused_with_its_own_message` et `test_vector_index.py`.

## Journal

- 2026-10-19 · constat du résidu vectoriel : aucun octet du vecteur supprimé ne reste dans le `.db` ni le `-wal` après `DELETE ... WHERE rowid` + purge (sqlite-vec 0.1.9) ; voisin intact.
- 2026-10-19 · dev : spec, code, tests unitaires, web, E2E (Edge) et intégration réelle verts. Deux tests de budget de lecture (`/api/models/defaults`, 362 ms et 313 ms contre 300) ont échoué une fois pendant la suite complète sous charge ; ils passent seuls et sans les changements de la story (aucun lien : `ModelDefaults` reçoit le même magasin de préférences).

## Revue

- medium · second avis n° 1 · corrigé : `PUT /api/rag/settings {"chunk_size": null}` (ou `chunk_overlap`) levait `TypeError` (500) ; `null` retombe désormais sur le `.toml` pour la comparaison. Test : `test_a_null_chunk_size_or_overlap_gives_the_choice_back_to_the_toml`.
- low (rétrogradé de medium) · second avis n° 2 · corrigé : `embedding_model: null` sur une base non vide passait sans contrôle alors que le `.toml` nomme un autre modèle. L'écran affiche le modèle de la base et l'import le garde (AD-16 tenu en pratique), mais le réglage enregistré annonçait un changement silencieux : `null` est maintenant comparé au modèle du `.toml` (`409 embedding_change_needs_clear`, `requested` = modèle du `.toml`) ; sans modèle au `.toml`, `null` reste accepté. Tests : `test_going_back_to_another_toml_embedding_on_a_non_empty_base_must_clear_first`, `test_without_a_toml_embedding_a_null_is_accepted_on_a_non_empty_base`.
- medium · second avis n° 3 · corrigé : avec le repli `NumpyIndex`, un fichier qui garde des tables vec0 (écrites un jour avec sqlite-vec) gardait leurs vecteurs après « Supprimer » ou « Vider ». `_erase_stray_vectors` (`rag/manage.py`) les efface par `rowid` ou recrée les tables si la connexion connaît vec0 ; sinon (« no such module: vec0 », vérifié : ni `DELETE` ni `DROP` possibles sans le module), refus `409 vector_tables_unreachable` avant toute écriture, rien n'est supprimé (variante sûre ; nouveau code consigné dans `errors.py` et `contrat-api.md`). Tests : `test_the_fallback_index_still_erases_vectors_left_in_vec0_tables`, `test_vectors_that_cannot_be_erased_without_sqlite_vec_refuse_the_deletion`.
- low · second avis n° 4 · corrigé : délai du client porté de 30 s à 300 s pour `DELETE` document et base (`VACUUM` d'une grosse base).
- low · second avis n° 5 · rejeté : « N documents » compte tous les statuts, ce qui est juste, « Vider » supprime aussi les documents `failed` (`documents_removed` du serveur compte de même).
- low · second avis n° 6 · rejeté : inatteignable, `working` de `documents-manage.js` empêche un second `ask()` pendant un dialogue ouvert.
- info · demande de l'orchestrateur · validé : l'interprétation de « document visé » (refus si `indexing` ou run `rag` actif ; `ready`/`failed` supprimable pendant l'import d'autres fichiers) suit AD-13 et le critère ; reste consignée dans `deferred` pour arbitrage d'Anaël.
- Complexité : 0 constat (aucune structure qui grossit parcourue à chaque événement ; `COLUMNS` est local à `mount`).
