---
title: 'Chercher autrement (HyDE, Self-RAG) et citer ses sources'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '2f7a323'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-4.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-5.md'
warnings: []
deferred:
  - summary: >-
      Écarts de la §7 (d), points 12 et 18 de `sprint-change-proposal-2026-10-19.md`, non tranchés : variante la plus conservatrice gardée pour chacun. (12c) Marqueur `[n]` non vérifié : le texte de la réponse reste tel que le modèle l'écrit, le marqueur n'est qu'un texte, sans bouton (ni masqué ni retiré) ; seuls les marqueurs que `citations` confirme deviennent des boutons. (12d) Moment de `retrieval_step` : publié à la **fin** de chaque étape (critère de la 4.4), jamais au début ; pour que « Rédaction d'une réponse hypothétique… » soit dite pendant la rédaction, l'écran la pose dès `run_started` d'après la stratégie choisie (`first-stage="hypothesizing"`), et `retrieval_step` fait avancer l'étape suivante. (12a) avertissement cloud et (12b) « Télécharger » : inchangés depuis la 4.5. (18) nom des champs de `citations` : `{citations: [{marker, n}]}`, la forme de la maquette, consignée dans `contrat-api.md`.
    evidence: |-
      `rag/strategies.py::verify_citations`, `screens/documents-citations.js`, `wl-run-status.js::stageAfter`, `test_rag_strategies_api.py::test_without_a_verified_marker_...`, `test_discussion_strategies.py::test_without_a_verified_marker_the_front_makes_no_button`.
    location: _bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md
    severity: low
  - summary: >-
      Écarts additifs à `contrat-api.md` (déjà consignés dans le contrat, à ratifier) : `POST /api/rag/runs` accepte `strategy` `naive`, `hyde`, `self_rag` et `top_k` (1 à 20) ; `retrieval_step` gagne les étapes `hypothesis`, `grade`, `rewrite` et les champs `round`, `fallback`, `checked`, `relevant` ; l'événement `citations` `{citations: [{marker, n}]}` ; `GET /api/rag/documents` rend `search: {top_k, max_top_k}` ; `Settings.rag.self_rag_max_iterations` (2). Aucun nouveau code d'erreur.
    evidence: |-
      `contrat-api.md` (événements, Base documentaire, Discussion), `test_rag_strategies_api.py`, `test_rag_list_api.py::test_an_empty_base_lists_nothing_and_states_the_limits`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Résolu à la fusion avec la 4.3 : le palliatif `search: {top_k, max_top_k}` de `GET /api/rag/documents` est retiré ; l'écran Discussion lit `GET /api/rag/settings` (`top_k`, `strategy`, `limits.top_k.max`) et démarre sur la stratégie par défaut enregistrée. `top_k` de la question prime sur le réglage de l'écran Base, qui prime sur le `.toml`.
    evidence: |-
      `web/routes_rag.py::SearchDefaults`, `screens/documents.js::refreshBase`.
    location: src/wavelocalai/web/routes_rag.py
    severity: medium
  - summary: >-
      Contrats partagés de l'orchestrateur pas sur cette base : `core/ram-guard.js` (4.8) et `components/wl-confirm-dialog.js` (4.3) n'existent pas encore ici. La 4.6 n'en a pas besoin (aucune confirmation) ; `ram_guard` s'affiche toujours par `wl-error` comme en 4.5, le branchement de `core/ram-guard.js` dans `screens/documents.js::submit` se fait à la fusion de la 4.8.
    evidence: |-
      `screens/documents.js::submit` (`error.error = envelopeOf(...)`).
    location: src/wavelocalai/web/static/screens/documents.js
    severity: low
  - summary: >-
      Choix de conception à confirmer. (1) HyDE et Self-RAG appellent **le modèle de réponse choisi** (la v1 prenait `qwen2.5:1.5b` pour l'hypothèse et la notation) : aucun second modèle à charger ni à installer, mais un modèle lourd rédige l'hypothèse et note les extraits ; un modèle « de recherche » distinct serait un réglage de plus. (2) Self-RAG note **tous les extraits en un seul appel** (une ligne `n : oui|non` par extrait) au lieu d'un appel par extrait (v1) : moins de feuilles et de CO₂, mais un petit modèle peut mal suivre le format (un extrait sans verdict est gardé ; une notation illisible garde tous les extraits). (3) Pour HyDE, `relevance_label` et `raw_score` mesurent la similarité entre l'**hypothèse** et l'extrait, pas la question ; le passage surligné reste celui de la question. (4) Seul le marqueur simple `[n]` est vérifié (`[1, 2]` n'est pas lu). (5) HyDE, température 0,3 (0,7 en v1) ; reclassement par reranker : story 4.7.
    evidence: |-
      `rag/strategies.py` (docstring), `rag/query.py::_ask`, `_hyde`, `_self_rag`.
    location: src/wavelocalai/rag/query.py
    severity: low
---

# Story 4.6 : chercher autrement (HyDE, Self-RAG) et citer ses sources

## Objectif

`POST /api/rag/runs` accepte trois stratégies de recherche et un nombre d'extraits ; la réponse qui cite `[n]` voit ses marqueurs vérifiés par le serveur (`citations`), et l'écran Discussion les rend cliquables. Rien n'est ajouté à l'architecture : les appels de modèle de la stratégie sont des feuilles `generation` du run `rag` (AD-5), mesurées comme les autres (AD-10, AD-11), sous le sémaphore local (AD-14).

## Critères d'acceptation et preuves

1. **HyDE** : une réponse hypothétique est générée (appel silencieux, feuille `generation`), puis vectorisée et cherchée ; `retrieval_step` `hypothesis` puis `embedding`, `search` ; le `run-status` dit « Rédaction d'une réponse hypothétique… » dès le départ puis « Recherche des extraits… ». Hypothèse en échec ou vide : repli sur la question (`fallback: "question"`). Preuve : `test_rag_strategies_api.py::test_hyde_writes_a_hypothetical_answer_...`, `::test_hyde_falls_back_...` ; E2E `test_hyde_writes_a_hypothetical_answer_and_searches_with_it` (étape lue pendant la rédaction, première source = celle de l'hypothèse).
2. **Self-RAG** : boucle bornée par `rag.self_rag_max_iterations` (2 reformulations, donc 3 recherches au plus) : recherche, notation des extraits (un appel), reformulation si aucun n'est pertinent ; le `run-status` dit « Vérification de la pertinence… » après chaque recherche ; la borne atteinte (ou une reformulation vide ou inchangée), la réponse part avec les meilleurs extraits trouvés (un par `chunk_id`, la meilleure distance, les `top_k` plus proches). Preuve : `::test_self_rag_keeps_the_relevant_excerpts_...`, `::test_self_rag_reformulates_...`, `::test_self_rag_stops_at_the_bound_with_the_best_excerpts_found`, `::test_self_rag_keeps_every_excerpt_when_the_grade_is_unreadable_or_fails`, `::test_self_rag_stops_when_the_reformulation_is_empty_or_unchanged` ; E2E `test_self_rag_verifies_the_relevance_then_reformulates_...`.
3. **Citations** : la consigne de citation est dans l'invite (`SYSTEM_PROMPT`, sans citer un numéro hors liste) ; à la fin d'une réponse réussie, le serveur vérifie les marqueurs `[n]` contre les sources et publie `citations {citations: [{marker, n}]}` (après `metrics`, avant `run_ended`, seulement s'il y a au moins un marqueur vérifié, persisté et rejoué). Le front ne rend en bouton que les marqueurs confirmés ; survoler ou focaliser `[n]` met la source en évidence, et inversement ; un clic ouvre l'extrait ; sans `citations`, aucun marqueur n'est fabriqué. Preuve : `test_rag_strategies.py` (unit, 22), `::test_the_server_verifies_the_markers_and_publishes_citations_after_the_metrics`, `::test_without_a_verified_marker_no_citations_event_is_published`, `::test_the_markers_are_checked_against_the_sources_of_the_strategy`, `::test_a_cancelled_answer_publishes_no_citations` ; E2E `test_only_the_markers_the_server_verified_become_buttons_that_link_to_the_sources`, `::test_a_marker_of_another_answer_...`, `::test_without_a_verified_marker_the_front_makes_no_button`, `::test_a_reopened_conversation_keeps_its_verified_markers`.
4. **Réglages avancés** : stratégie (« Recherche directe », « Réponse imaginée d'abord », « Recherche vérifiée ») et « Nombre d'extraits » (défaut et plafond du serveur, ramené dans les bornes) ; chaque réglage est envoyé avec la question et agit sur le run suivant ; HyDE, Self-RAG et Top-K ne figurent qu'en aide. Preuve : `::test_the_number_of_excerpts_acts_on_the_next_run`, `::test_a_number_of_excerpts_out_of_range_is_refused_before_any_run`, `::test_the_document_list_gives_the_search_defaults` ; E2E `test_the_advanced_settings_offer_three_strategies_...`, `::test_the_number_of_excerpts_acts_on_the_next_question` ; `test_discussion_static.py::test_the_technical_names_of_the_strategies_only_appear_in_help_texts`.
5. **Annulation et pannes** : annuler pendant un appel de stratégie ferme toutes les feuilles avec un `co2`, sans `sources`, `token` ni `citations` ; un échec d'embedding pendant une reformulation termine le run en `error` (génération « non lancée »). Preuve : `::test_cancelling_during_a_strategy_call_closes_every_leaf_with_a_co2` (HyDE et Self-RAG), `::test_an_embedding_failure_during_a_reformulation_ends_the_run_in_error`.

## Règles écrites

Dans `rag/strategies.py` (règles pures) et `rag/query.py` (orchestration) :

- **Étapes** (`retrieval_step {strategy, step, duration_s}`, publiées à leur fin) : `naive` `embedding`, `search` ; `hyde` `hypothesis`, `embedding`, `search` ; `self_rag` par tour (`round` 0, 1…) `embedding`, `search`, `grade` (`checked`, `relevant`), puis `rewrite`. Champ `fallback` : `question` (hypothèse absente), `all` (notation illisible ou en échec : tous les extraits gardés), `stop` (reformulation vide ou inchangée : plus de tour).
- **Notation** : une ligne `n : oui` ou `n : non` par extrait ; un extrait sans verdict lisible est gardé. Il suffit d'un extrait pertinent pour arrêter la boucle et répondre avec les pertinents (rang 1, 2… dans l'ordre de distance).
- **Meilleurs extraits** (borne atteinte) : tous les extraits vus, un par `chunk_id` avec sa plus petite distance, les `top_k` plus proches.
- **Citation vérifiée** : `[n]` avec `n` entre 1 et le nombre de sources de l'événement `sources` ; un par marqueur, ordre de première apparition ; `marker` = `n`.
- **Durée de recherche** (`metrics.retrieval_s`) : de l'appel de la stratégie à la publication de `sources` (hypothèse, embeddings et notations compris).

## Notes de développement

- `RagService._ask` : appel silencieux (`stream_into_run(capture=)`, comme la notation de l'Arène) dans une feuille `generation` créée à la demande (`_leaf`) et déclarée annulée par défaut ; un parent clos (annulation) lève `CancelledError`. `_embedding_leaf` sert la feuille créée au départ à la première recherche, une nouvelle ensuite.
- `RunHub.answer_text(run_id)` : texte de réponse accumulé d'un run racine actif (jetons en attente versés), lu par le service pour vérifier les marqueurs.
- Front : `screens/documents-chat-settings.js` (réglages avancés ; `documents-settings.js` est celui de l'écran Base, 4.3), `documents-citations.js` (marqueurs en boutons), `documents-replay.js` (rejeu extrait de `documents.js`, qui reste sous 600 lignes) ; `wl-chat-thread` gagne `answer.decorator` (appelé après chaque rendu Markdown) et `answer.refresh()` ; `wl-source-panel` gagne `highlight(n)` et l'événement `wl-source-link` ; `wl-run-status` gagne les étapes `hypothesizing` et `verifying` (`first-stage="hypothesizing"`). Le bouton `[n]` a pour nom « [1] source 1, chats.txt » (le texte visible d'abord, WCAG 2.5.3).
- Test seulement : `FakeChatModel.scripts` et `POST /api/test/chat-model {scripts}` rendent un script par appel (réponse hypothétique, notation, reformulation, réponse) ; le script par appel repart du premier à chaque réglage.
- Réaligné : `test_discussion.py` (le texte d'une réponse se lit sans le complément `.sr-only` du bouton `[1]`, trois options de stratégie), `test_rag_run_api.py` (`hyde` n'est plus une stratégie refusée), `test_rag_list_api.py` (`search`).

## Fichiers

- `src/wavelocalai/rag/strategies.py` (nouveau), `rag/query.py`, `runs/hub.py` (`answer_text`), `config.py` + `wavelocalai.toml` (`self_rag_max_iterations`), `web/routes_rag.py` (`strategy`, `top_k`, `search`), `models/fake.py`, `web/routes_test.py`
- `src/wavelocalai/web/static/screens/documents.js`, `documents-settings.js`, `documents-citations.js`, `documents-replay.js` (nouveaux), `components/wl-chat-thread.js`, `wl-run-status.js`, `wl-source-panel.js`, `components.css`, `documents.css`, `i18n/fr.json`
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md`
- Tests : `tests/v2/unit/test_rag_strategies.py`, `tests/v2/web/test_rag_strategies_api.py`, `tests/v2/e2e/test_discussion_strategies.py` (nouveaux) ; complétés ou réalignés : `test_discussion_static.py`, `test_discussion.py`, `test_rag_run_api.py`, `test_rag_list_api.py`, `test_fake_model.py`, `test_hub_stream.py`, `test_config.py`

## Vérification

Ciblée (la suite complète est lancée par l'orchestrateur). Unitaires et web : `test_rag_strategies.py` (22), `test_rag_strategies_api.py` (22), `test_rag_run_api.py`, `test_rag_api.py`, `test_rag_list_api.py`, `test_discussion_static.py`, `test_fake_model.py`, `test_hub_stream.py`, `test_config.py`, `test_layers.py` : verts. E2E sur Edge (`-m e2e`) : `test_discussion_strategies.py` 14 verts, `test_discussion.py` 18 verts. Contrôle rapide propre. Pas de test d'intégration Ollama ajouté (les stratégies appellent `ChatModel` et `Embedder`, déjà couverts par `integration/test_rag_question_ollama.py` ; le comportement d'un vrai petit modèle sur le format de notation reste à observer).

## Journal

- 2026-10-19 · dev : spec, serveur (stratégies, citations), écran (réglages, marqueurs), tests unitaires, web et E2E ciblés verts.
