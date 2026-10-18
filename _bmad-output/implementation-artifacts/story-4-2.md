---
title: "L'écran Base documentaire suit chaque fichier"
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'f3536cb'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-1.md'
warnings: []
deferred:
  - summary: >-
      La progression d'envoi par fichier est une répartition : `XMLHttpRequest` ne rend que les octets du formulaire entier, répartis sur les fichiers dans l'ordre d'envoi (les en-têtes multipart gonflent un peu le total, la valeur est bornée à 100 %). Pas de reprise d'un envoi interrompu ni d'envoi par blocs.
    evidence: |-
      `core/api.js::uploadDocuments`, `spreadProgress`.
    location: src/wavelocalai/web/static/core/api.js
    severity: low
  - summary: >-
      Un document `failed` reste dans la liste jusqu'à un nouvel import du même contenu (qui le remplace) ou jusqu'au vidage de la base : sa suppression individuelle (bouton « Supprimer » de sa ligne) est la story 4.3. La liste n'est pas paginée (base locale d'un poste).
    evidence: |-
      `test_a_failed_document_keeps_its_reason_in_the_table_after_a_reload`.
    location: src/wavelocalai/rag/repo.py
    severity: low
  - summary: >-
      Reporté de la 4.1 (second avis 3) : sans `sqlite-vec` chargeable, chaque fichier échoue en « erreur interne » ; un refus explicite au démarrage demande un code d'erreur nouveau dans `contrat-api.md`. Non traité ici (aucun écran ne l'exige) ; à trancher avec la 4.3 (réglages et vidage).
    evidence: |-
      `rag/ingest.py::_failure`.
    location: src/wavelocalai/rag/ingest.py
    severity: low
  - summary: >-
      Suite E2E de l'écran lente (environ 3 min pour 22 tests) : chaque lot d'embedding démarre un vrai tracker CodeCarbon (1 à 4 s), et chaque test lance son serveur. Un `fake` de mesure en mode test la raccourcirait, mais la mesure réelle fait partie de ce que l'E2E prouve (CO₂ de session).
    evidence: |-
      `tests/v2/e2e/test_documents.py` (22 passés en 198 s).
    location: tests/v2/e2e/test_documents.py
    severity: low
---

# Story 4.2 : l'écran Base documentaire suit chaque fichier

## Objectif

L'écran `#/documents/base` (module Documents passé à `available`) montre une zone de dépôt tout de suite, suit chaque fichier d'un import ligne par ligne (envoi, lecture, découpage, vectorisation, résultat) et liste les documents de la base dans un `wl-data-table`. Suppression, vidage et réglages sont la story 4.3 ; la Discussion, les stories 4.4 et 4.5.

## Critères d'acceptation et preuves

1. **Zone de dépôt sans serveur** : « Déposez des fichiers ici ou Choisir des fichiers · PDF, TXT, MD, DOCX » est construite avant tout appel ; le glisser-déposer et le bouton (clavier) ouvrent le même import. Les plafonds (`50 Mo au plus par fichier ; 50 fichiers et 500 Mo au plus par import`) s'ajoutent sous la zone dès que la liste est lue. Base vide : la carte « Votre base documentaire est vide » et « Importer des documents ». Les onglets « Discussion » et « Évaluation de la qualité » restent désactivés avec leur raison. Preuve : `test_the_drop_zone_is_visible_before_the_server_answers_...` (la liste est retenue), `test_the_module_tabs_...`, `test_both_import_buttons_open_the_file_chooser`, `test_documents_static.py` (zone montée avant `refresh`).
2. **Une ligne par fichier** : « Envoi n % », puis « Envoi 100 % · Découpage · Vectorisation 18/40 extraits » depuis `ingest_progress` (ligne repérée par `file_index`), `<progress>` (indéterminé hors envoi et vectorisation), Annuler. Un échec affiche `wl-error` « Le fichier n'a pas pu être indexé : <raison>. » avec « Détails techniques » replié (seulement quand la trace dit autre chose que la raison) ; un succès « N extraits ajoutés depuis M documents. » annoncé une seule fois en fin d'import (zone polie), avec le nombre de fichiers en échec. Pluriels accordés (0 et 1 au singulier). Preuve : `test_each_file_has_its_line_...`, `test_a_failed_file_says_why_...`, `test_a_content_already_in_the_base_is_not_indexed_twice`, `test_an_unreachable_embedding_model_...`, `test_a_docx_file_is_indexed_from_the_screen`.
3. **`GET /api/rag/documents`** (nouvelle route de lecture, `contrat-api.md`) : `{documents: [{id, source, status, chunks, pages, size_bytes, embedding_model, created_at, ready_at, run_id, error}], totals: {documents, chunks}, limits: {...}}`, plus récent d'abord, tous statuts ; les totaux ne comptent que les `ready`. Le tableau montre nom, extraits, date d'ajout (`fr-FR`), modèle de représentation et statut ; un document `indexing` affiche « Indexation en cours » et « en cours » à la place du nombre d'extraits, jamais « Prêt » ; un `failed` garde sa raison. `wl-data-table` : `<table>` sémantique (`caption`, `th scope`), en-têtes triables au clavier (`aria-sort`, focus conservé, ordre annoncé). Preuve : `test_rag_list_api.py` (8), `test_an_indexing_document_is_never_shown_as_ready`, `test_the_table_lists_name_chunks_date_model_and_status_and_sorts_from_the_keyboard`, `test_read_budget.py`.
4. **Reprise** : quitter l'écran pendant un import ferme le flux en gardant le `seq`, et le retour le rouvre par `?after=` ; une page rechargée retrouve l'import par le `run_id` d'un document `indexing` et le rejoue ; un second import pendant un import actif rejoint le run (`409 run_busy`, sans erreur affichée). Preuve : `test_leaving_the_screen_...`, `test_reloading_the_page_...`, `test_a_second_import_joins_...`.
5. **Plafonds d'import** (reporté de la 4.1, second avis 5) : `rag.max_files` (50) et `rag.max_import_mb` (500) dans `wavelocalai.toml` ; l'écran refuse avant l'envoi (« Trop de fichiers : 50 au plus par import. »), la route refuse aussi (`422 invalid_request`, rien n'est gardé). Preuve : `test_too_many_files_are_refused_before_anything_is_sent`, `test_an_import_over_the_file_count_or_total_size_cap_is_refused`.
6. **Annulation** : pendant l'envoi, l'envoi est abandonné (aucun run) ; ensuite, `POST /api/runs/{id}/cancel` : le document en cours est retiré, les lignes passent à « Annulé », la base vide revient. Preuve : `test_cancelling_stops_...`, `test_cancelling_during_the_upload_...`.
7. **Charte et accessibilité** : bouton plein sur `var(--color-primary-fill)` avec texte blanc (A19), aucune couleur en dur (`documents.css` ajouté au test de dérive), aucune icône nouvelle ni emoji ; axe-core sans violation, clair et sombre, sur l'écran vide, l'import en cours (avec une ligne en échec) et le tableau ; largeur 375 px sans défilement horizontal. Preuve : `test_the_filled_button_uses_primary_fill_...`, `test_axe_finds_nothing_...`, `test_the_screen_fits_a_phone_width_...`, `test_shell_static.py`.

## Écarts au contrat

- `contrat-api.md` : `ingest_progress` (champs `file`, `file_index`, `file_count`) et `ingest_file_done` ratifiés (écart de la 4.1) ; forme de `GET /api/rag/documents` ; `422` des plafonds.
- Route de test `POST /api/test/embedder` (mode test seulement) : règle les pauses et pannes du `FakeEmbedder` pour l'E2E.
- Le front compose la phrase d'échec depuis le message de l'enveloppe et `detail.reason` (le critère l'exige) ; la liste vient du serveur, le front ne calcule que le tri et les pluriels.
- Le module Documents (lien de l'Accueil et de la barre haute) mène désormais à la Base documentaire ; `test_home.py`, `test_shell.py` et `test_shell_static.py` réalignés.

## Fichiers

- `src/wavelocalai/web/static/screens/documents-base.js`, `components/wl-data-table.js` (nouveaux), `documents.css`, `components.css`, `core/api.js` (`documents`, `uploadDocuments`), `core/registry.js`, `i18n/fr.json`, `index.html`
- `src/wavelocalai/web/routes_rag.py` (`GET`, plafonds), `rag/repo.py` (`LIST_SQL`, `TOTALS_SQL`), `config.py` + `wavelocalai.toml` (`max_files`, `max_import_mb`), `web/routes_test.py`
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md`
- Tests : `tests/v2/e2e/test_documents.py` (22), `unit/test_documents_static.py` (10), `web/test_rag_list_api.py` (8) ; réalignés : `e2e/test_home.py`, `e2e/test_shell.py`, `unit/test_shell_static.py`

## Vérification

`pytest tests/v2` : 787 passés ; `-m e2e` : 179 passés (dont 22 de l'écran).

## Revue

- medium · second avis · corrigé : Annuler une fois le corps envoyé (« Envoi 100 % ») abandonnait la requête alors que le serveur créait le run, qui indexait quand même. `uploadDocuments` signale l'envoi du corps (`onSent`) ; Annuler attend alors le `run_id` et arrête le run. Preuve : `test_cancelling_once_the_files_are_sent_stops_the_run_the_server_started` (échoue sur l'ancien code).
- medium · second avis · corrigé : chaque lecture de la liste pendant un import reconstruisait le tableau et faisait perdre le focus à l'en-tête de tri (ou à la zone qui défile). `wl-data-table` rend le focus au nœud équivalent. Preuve : `test_a_sort_header_keeps_the_focus_while_an_import_updates_the_table` (échoue sur l'ancien code).
- low · second avis · corrigé : après 6 échecs du flux, l'import était dit interrompu alors que le run tournait encore ; si `GET /api/runs/{id}` dit `running`, le flux est rouvert, et un `ingest_file_done` rejoué n'est plus compté deux fois.
- low · second avis · corrigé : après un échec de lecture de la liste, le tableau périmé restait affiché ; il est masqué tant que l'erreur est là.
- low · second avis · corrigé : « Annuler l'import de <fichier> » (nom accessible propre à chaque ligne).
- low · second avis · corrigé : un import fait seulement de doublons finissait sans annonce ; la phrase de fin dit « N fichier(s) déjà dans la base ».
- low · second avis · reporté : les plafonds de taille sont vérifiés pendant la copie de staging, après que Starlette a déjà lu tout le multipart en fichiers temporaires. Un refus avant lecture demande une limite sur `Content-Length` (middleware ou serveur) ; l'écran refuse déjà avant l'envoi. À traiter avec le durcissement du serveur.
- low · revue · rejeté (complexité) : chaque événement de fin de fichier relit la liste et reconstruit le tableau, soit O(fichiers × documents) par import ; les lectures sont coalescées (`refreshAgain`), 50 fichiers au plus par import, base locale : impact négligeable. Complexité : 1 constat, sans correctif.

## Ajustements du correct course (2026-10-19)

Maquette validée par Anaël ; critères ajoutés à la 4.1 et à la 4.2 (`sprint-change-proposal-2026-10-19.md` §7(a)).

1. **Un seul « Annuler l'import »** (D-25) : le bouton « Annuler » de chaque ligne et son nom accessible par fichier sont retirés ; un bouton unique `.docs-imports-cancel` se place au-dessus des lignes, visible tant qu'un envoi ou un run tourne. La logique revue est inchangée (envoi abandonné ; corps parti : attendre le `run_id` puis arrêter le run ; sinon arrêter le run `ingest`), les documents prêts restent. Quand le lot finit, le bouton disparaît et le focus passe à « Choisir des fichiers ». Preuve : `test_the_single_cancel_button_sits_above_the_rows_and_only_shows_during_an_import`, `test_cancelling_keeps_the_documents_that_are_already_ready`, les trois tests d'annulation réalignés.
2. **`GET /api/rag/documents` rend les `failed`** (D-26, 4.1) : déjà le cas (`LIST_SQL` sans filtre de statut, `TOTALS_SQL` sur `ready` seulement, `error` portant la raison) ; test serveur ajouté pour une base qui ne contient qu'un document en échec : totaux à 0, document listé avec sa raison, relu à l'identique. Preuve : `test_a_base_with_only_a_failed_document_lists_it_with_its_reason_and_counts_none`.
3. **Tableau** (D-26) : un document `failed` figure déjà dans `wl-data-table` (statut « Échec », raison lisible dans la cellule, absent du compte « N documents prêts », retrouvé après rechargement) ; aucun bouton « Supprimer » ni inactif (4.3). Preuve : `test_a_failed_document_is_in_the_table_but_not_in_the_ready_count` (deux lectures, avant et après rechargement).
4. **Charte** : axe-core clair et sombre inchangé ; largeur ramenée de 375 à 320 px, avec import en cours (bouton d'annulation compris) puis tableau avec un document en échec : aucun défilement horizontal, aucune violation.

Découpage : `documents-base.js` dépassait 600 lignes ; `ImportRow`, `plural` et la composition du message d'échec passent dans `screens/documents-import-row.js` (le test de textes lit les deux fichiers, et le plafond de 600 lignes couvre les deux).

Écarts §7(d) : n° 13 (Supprimer et Vider désactivés pendant un import, ou 409 affiché) non tranché, concerne la 4.3 ; ici, « Choisir des fichiers » et « Importer des documents » sont déjà désactivés pendant un import, avec la phrase d'attente, et le critère actuel est gardé tel quel.

Vérification : voir le rapport de l'orchestrateur (`pytest tests/v2`, E2E de l'écran sur Edge).
