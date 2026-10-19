---
title: 'L''écran Discussion montre la réponse à côté de ses sources'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: 'fff8faa'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-4.md'
warnings: []
deferred:
  - summary: >-
      Écarts de la §7 (d), point 12 de `sprint-change-proposal-2026-10-19.md`, non tranchés : variante la plus conservatrice gardée pour chacun. (a) Avertissement cloud : affiché tant qu'un modèle cloud est choisi (« les extraits retrouvés dans vos documents lui sont envoyés, hors de ce poste »), sans confirmation à l'envoi. (b) « Télécharger » : absent (aucune route d'export RAG, rien d'ajouté au serveur). (c) Marqueur `[n]` : le texte de la réponse reste tel que le modèle l'écrit, aucun bouton, aucun événement `citations` (story 4.6). (d) `retrieval_step` : publié par le serveur à la fin de chaque étape (story 4.4) ; l'écran n'en dépend pas pour « Recherche des extraits… », affiché dès `run_started` jusqu'à `sources`.
    evidence: |-
      `screens/documents.js` (en-tête), `test_discussion.py::test_a_cloud_model_warns_...`, `test_discussion_static.py::test_no_download_and_no_citation_marker_is_invented`.
    location: _bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md
    severity: low
  - summary: >-
      Le pied de réponse montre le CO₂ de la feuille de génération (événement `metrics`), pas la somme avec la feuille d'embedding de la question : l'addition mêlerait mesuré et estimé (cloud) et serait un calcul du front (AD-20). Le CO₂ de l'embedding reste compté dans la session (`carbon_updated`). Si la somme est voulue, c'est le serveur qui la porte (`metrics.co2` d'un run `rag`, ou une ligne de plus).
    evidence: |-
      `components/wl-chat-thread.js` (`#finalFoot`), `rag/query.py` (`metrics_extra`).
    location: src/wavelocalai/rag/query.py
    severity: medium
  - summary: >-
      Réglages avancés minimaux : une seule stratégie (`naive`, « Recherche directe »), pas de nombre d'extraits ni de stratégie par défaut. `GET /api/rag/settings` (story 4.3, en parallèle) et les stratégies HyDE et Self-RAG (4.6) viendront les alimenter ; l'écran ne lit donc aucun réglage du serveur et envoie `strategy: "naive"`.
    evidence: |-
      `screens/documents.js::STRATEGIES`, `strategy` du corps de `POST /api/rag/runs`.
    location: src/wavelocalai/web/static/screens/documents.js
    severity: low
  - summary: >-
      Garde-fou mémoire (story 4.8, fusionnée) : l'écran branche `core/ram-guard.js` comme le Chat. Sur un `run_ended` en erreur `ram_guard`, la question revient dans le champ (sauf si la personne a déjà tapé autre chose) ; « Prendre un modèle plus petit » choisit `detail.suggested_model` dans le sélecteur, met à jour l'avertissement cloud et annonce le choix (`discussion.model_changed`), sans relancer. Le serveur applique le garde-fou à la réponse RAG.
    evidence: |-
      `screens/documents.js::submit` (`error.error = envelopeOf(...)`).
    location: src/wavelocalai/web/static/screens/documents.js
    severity: low
  - summary: >-
      Une conversation rouverte rejoue le flux de chaque réponse finie (`connectRun`, run fini, un flux par réponse) pour retrouver ses sources et ses mesures, que `GET /api/conversations/{id}` ne porte pas (report de la 4.4). Correct et borné (délai de 10 s par flux), mais un flux par réponse pour une longue conversation. Si cela pèse, `conversation_view` peut porter `sources` et `metrics` du run (additif).
    evidence: |-
      `screens/documents.js::replay`, `::showConversation`, `test_discussion.py::test_a_reopened_conversation_...`.
    location: src/wavelocalai/runs/conversations.py
    severity: low
  - summary: >-
      Joindre une question déjà en cours (`409 run_busy`) rejoue la réponse sans la question de l'autre onglet : le fil montre la réponse seule, comme le Chat libre. La question n'est pas dans le flux (AD-7).
    evidence: |-
      `test_discussion.py::test_a_question_already_running_is_joined_without_an_error`.
    location: src/wavelocalai/web/static/screens/documents.js
    severity: low
  - summary: >-
      Écart à la maquette : le passage surligné est un aplat violet sous texte blanc (`primary-fill`, A19, en plus du gras), non un fond `surface-alt` souligné, que le fond de page rendait presque invisible. Le panneau est un `details` dont le titre est un `h2` dans le `summary` (toujours ouvert dès 1 024 px, sans repli ; le `summary` quitte alors l'ordre de tabulation).
    evidence: |-
      `components.css` (`.wl-source-mark`), `test_discussion_static.py::test_the_passage_highlight_is_...`.
    location: src/wavelocalai/web/static/components.css
    severity: low
---

# Story 4.5 : l'écran Discussion montre la réponse à côté de ses sources

## Objectif

`#/documents` devient l'écran Discussion : une question aux documents prêts, la réponse au fil de son flux, et à côté d'elle `wl-source-panel` avec les sources trouvées **avant** le premier jeton. Le serveur est celui de la story 4.4 (`POST /api/rag/runs`, `GET /api/rag/chunks/{id}`, événements `retrieval_step`, `sources`, `metrics.retrieval_s`) ; aucune route n'est ajoutée hors de la route de test `POST /api/test/chat-model`.

## Critères d'acceptation et preuves

1. **Ouverture** : l'en-tête dit « 3 documents · 3 extraits » (totaux des documents prêts, lien « Gérer la base documentaire », note d'indexation si des documents sont en cours) ; `wl-model-picker` sur l'usage `rag` (défaut et raison du serveur) ; « Réglages avancés » replié (une stratégie, « Recherche directe », le nom `naive` en aide) ; le champ dit « Posez une question à vos documents ». Base sans document prêt : une carte « Votre base documentaire est vide » mène à `#/documents/base` (« L'indexation est en cours » si des documents s'indexent). Preuve : `test_discussion.py::test_the_header_the_model_and_the_collapsed_settings`, `::test_an_empty_base_leads_to_the_document_base`, `::test_a_base_emptied_meanwhile_leads_to_the_document_base_instead_of_an_answer`.
2. **Question** : `wl-run-status` dit « Recherche des extraits… » dès le démarrage puis « Génération… » à `sources` ; le panneau se remplit avant la réponse (liste numérotée, document, page quand le document en a une, libellé de pertinence, score brut en aide, extrait replié à trois lignes) ; « Ouvrir l'extrait » relit l'extrait entier (`GET /api/rag/chunks/{id}`) et surligne le `passage` du serveur ; la réponse et son pied (badge, CO₂, débit, tokens, chargement, « Recherche 0,06 s », « Génération 5,8 s ») suivent. Preuve : `::test_the_sources_fill_the_panel_before_the_answer_with_the_stages_the_passage_and_the_foot` (étapes, panneau plein pendant une réponse encore vide, `mark` = la phrase désignée, emoji avant le passage, pied), `::test_the_passage_positions_count_code_points_and_an_invalid_passage_is_not_highlighted`.
3. **Panneau toujours ouvert dès 1 024 px (D-22)** : à droite de la réponse, sans bouton de repli (cliquer le titre ne le ferme pas, il sort de la tabulation) ; en deçà, sous la réponse, replié, qui se déplie par son titre ; 320 px sans défilement horizontal. Preuve : `::test_the_panel_is_always_open_beside_the_answer_from_1024px_and_collapsed_below_it`.
4. **« Afficher les sources » (D-23)** : absent avec une réponse ; dès la deuxième, chaque réponse porte le bouton (`aria-pressed`) qui charge ses sources dans l'unique panneau, qui montre par défaut celles de la dernière. Preuve : `::test_each_answer_shows_its_sources_in_the_single_panel_from_the_second_answer_on`.
5. **« extrait supprimé »** : une source sans texte (document supprimé, flux rejoué) ou dont l'extrait a disparu à l'ouverture (`404 chunk_not_found`) dit « extrait supprimé » et n'offre plus d'ouvrir. Preuve : `::test_a_reopened_conversation_says_deleted_extract_for_a_document_deleted_since` (rechargement de l'écran, pied rejoué), `::test_each_answer_shows_...` (404 à l'ouverture).
6. **Reprise** : quitter l'écran puis revenir reprend le flux par `?after=` (la génération a fini en l'absence de l'écran : rien de perdu ni de répété) ; `409 run_busy` rejoint le run sans erreur. Preuve : `::test_leaving_and_coming_back_resumes_the_stream_by_after`, `::test_a_question_already_running_is_joined_without_an_error`.
7. **axe-core** sans violation, clair et sombre, à 1 440, 1 024 et 320 px : écran prêt, sources avec extrait ouvert et aide du score brut, « extrait supprimé ». Preuve : `::test_axe_finds_no_violation_with_sources_an_open_extract_and_the_source_deleted` (6 cas).
8. **Cloud (AD-9)** : un modèle cloud choisi affiche l'avertissement « les extraits retrouvés dans vos documents lui sont envoyés, hors de ce poste » ; `allow_cloud` du store accompagne chaque commande. Preuve : `::test_a_cloud_model_warns_that_the_extracts_leave_the_machine`, `test_discussion_static.py::test_the_screen_reads_the_stream_through_the_single_sse_client_and_resumes_by_after`.

## Règles écrites

- **Un lecteur du flux** : l'écran (`connectRun`) ; il passe chaque enveloppe à `wl-run-status` (mode piloté, attribut `first-stage="retrieving"`) et au fil. `sources` fait passer l'étape à « Génération… » ; `model_loading` la ramène à « Chargement du modèle… » si le modèle n'est pas en mémoire.
- **Passage** : le front ne désigne aucun passage. Les positions `{start, end}` de `sources` sont des points de code Python : `splitPassage` découpe avec `Array.from`, sinon un emoji avant le passage décalerait le surlignage ; hors bornes ou texte relu différent de celui de la recherche, l'extrait s'affiche entier sans surlignage.
- **Conversation rouverte** : la dernière conversation `rag` est relue ; le texte vient du message, les sources et les mesures du flux rejoué de chaque réponse finie. Un run encore actif est suivi par son flux.
- **Pied** : `metrics.retrieval_s` donne « Recherche », `total_s` (génération seule) donne « Génération » ; sans `retrieval_s`, le pied garde « Durée totale » (Chat libre, Arène inchangés).

## Notes de développement

- `components/wl-source-panel.js` (nouveau) : `panel.sources = […]`, `clear()`, `open(n)` ; `details` + `summary > h2`, `matchMedia("(min-width: 1024px)")` ouvre le panneau et rend le titre inerte en large ; aide du score brut par le motif de `wl-metric` (bouton « i », Échap).
- `components/wl-chat-thread.js` : zone `answer.actions` sous le pied (le pied est reconstruit à la fin, pas la zone), `restoreAnswer` rend la réponse, pied « Recherche » et « Génération » ; `wl-run-status.js` : étape `retrieving`, attribut `first-stage`, gestion de `retrieval_step` et `sources`.
- `core/format.js::plural` (extrait de `documents-import-row.js`, qui le ré-exporte) ; `core/api.js` : `startRag`, `chunk` ; `core/registry.js` : `documents-chat` disponible (le lien du module Documents de l'Accueil mène donc à la Discussion, sans changement de `home.js`).
- `web/routes_test.py` : `POST /api/test/chat-model` fixe le script du `fake` que lisent les commandes réelles (réponse scriptée sans contourner `POST /api/rag/runs`) ; les tests suppriment un document par SQL direct (aucune route de suppression avant la story 4.3).

## Fichiers

- `src/wavelocalai/web/static/screens/documents.js` (nouveau), `components/wl-source-panel.js` (nouveau), `components/wl-chat-thread.js`, `components/wl-run-status.js`, `components/index.js`, `core/api.js`, `core/format.js`, `core/registry.js`, `screens/documents-import-row.js`, `components.css`, `documents.css`, `i18n/fr.json`
- `src/wavelocalai/web/routes_test.py`
- Tests : `tests/v2/e2e/test_discussion.py` (nouveau), `tests/v2/unit/test_discussion_static.py` (nouveau), `tests/v2/web/test_rag_run_api.py` (route de test) ; réalignés : `tests/v2/unit/test_shell_static.py`, `tests/v2/e2e/test_home.py`, `test_shell.py`, `test_documents.py` (la Discussion est disponible, l'Accueil y mène)

## Vérification

`pytest tests/v2` : 932 passés (273 E2E et d'intégration exclus par `pytest.ini`). E2E sur Edge (`-m e2e`, lancés par lots pour tenir dans le délai de l'outil) : 17 de la Discussion, 30 de la Base documentaire, 126 du Chat, de l'Arène, des composants et du noyau, 100 de la coquille, du sélecteur, de la barre haute et de l'Accueil, tous verts. `test_conversations.py::test_the_conversation_is_continued_by_the_next_message` a échoué une fois dans un lot chargé (attente d'un run `fake` de 10 s, CodeCarbon) puis passé seul et en lot, sans rapport avec la Discussion. Contrôle rapide propre.

## Journal

- 2026-10-19 · dev : spec, écran, composant, tests statiques et E2E ciblés verts.

## Revue

Revue Opus, une passe, sur la liste du second avis (Haiku).

- medium · second avis · corrigé : conversation rouverte avec un modèle cloud, `picker.value` n'émet pas `wl-model-change`, l'avertissement AD-9 manquait ; `restore()` appelle `updateCloudNote()`. Test E2E `test_a_reopened_conversation_with_a_cloud_model_warns_too`, rouge avant le correctif.
- low · second avis · reporté : `409 run_busy` rejoint sans `conversationId`, la question suivante ouvre une autre conversation. Même motif que l'écran Chat (`chat.js`) ; `run_busy` ne porte que `run_id`. À traiter dans les deux écrans en ajoutant `conversation_id` au détail de `run_busy` (contrat d'API).
- low · second avis · corrigé : `wl-source-panel` écrasait la classe `docs-chat-sources` (`className =`), la règle de grille dès 1 024 px ne s'appliquait pas ; `classList.add`. Assertion `gridRowEnd == span 2` dans le test du panneau.
- low · second avis · corrigé : `panel.clear()` sans `refreshButtons()` laissait `aria-pressed="true"` sur l'ancienne réponse jusqu'à l'événement `sources`.
- low · second avis · corrigé : rejeu des runs d'une conversation rouverte en parallèle sans limite ; au plus 3 flux à la fois (`replayAll`), le délai de 10 s compte depuis la connexion de chaque rejeu.
- low · second avis · corrigé : `#items.delete(n)` après un `chunk_not_found` périmé pouvait retirer l'entrée de la nouvelle liste ; suppression seulement si l'entrée est encore celle du bouton.
- low (test) · second avis · corrigé : la reprise par `?after=` est prouvée en cours de flux (run encore `running` au retour, « deux » manqué pendant le masquage puis reçu).
- low (test) · reviewer · corrigé : `test_a_question_already_running_is_joined_without_an_error` instable (1 échec sur 3) : `restore()` pouvait reprendre le run lancé par le test et la question n'était pas envoyée. L'écran pose `data-restored` une fois la conversation relue ; `open_screen` et `reload_screen` l'attendent.
- Complexité : 0 constat (`refreshButtons` parcourt les réponses une fois par événement `sources` ou clic, pas par token).

