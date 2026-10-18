---
title: 'Choisir un modèle au clavier, et suivre l''étape d''un run'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '9151f62'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-8.md'
warnings: []
deferred:
  - summary: >-
      `wl-run-status` ne nomme que quatre étapes (démarrage, chargement du modèle, génération, fin). « Recherche des extraits… » et les étapes des agents (UX-DR8) arrivent avec les événements des stories RAG et agents : la table `STAGE_TEXT` et `fr.json` (`components.run_status`) les attendent.
    evidence: |-
      Critère de la story : `model_loading`, `token`, `run_ended` du `fake` seulement.
    location: src/wavelocalai/web/static/components/wl-run-status.js
    severity: low
  - summary: >-
      Aucun écran ne monte encore les deux composants : ils sont vérifiés sur la page d'essai `tests/v2/e2e/fixtures/picker.html`. Le chat, l'Arène et les documents les branchent (`purpose="chat"`, `purpose="arena" multi`) et écoutent `wl-model-change`.
    evidence: |-
      Critère « vérifiés en E2E sur la page d'essai des tests ».
    location: tests/v2/e2e/fixtures/picker.html
    severity: low
  - summary: >-
      Échap ferme le menu Affichage (`core/shell.js`, `core/disclosure.js`) sans `preventDefault` : avec un run suivi et un panneau ouvert, la même touche arrête aussi le run. Le sélecteur, lui, retient Échap (`stopPropagation`). Une fois la barre haute et l'écran du chat réunis, faire appeler `preventDefault` aux deux panneaux.
    evidence: |-
      `test_escape_closes_an_open_list_without_stopping_the_run` (liste du sélecteur seulement).
    location: src/wavelocalai/web/static/core/disclosure.js
    severity: low
  - summary: >-
      `wl-error` affiche l'action du code `no_model` telle que l'API la donne, avec ses accents graves Markdown (« `ollama pull qwen3.5:2b` »). Le catalogue de la barre haute les retire pour `ollama_down` ; un nettoyage commun dans `wl-error` serait plus sûr.
    evidence: |-
      `errors.py` (action de `no_model`) et `tests/v2/unit/test_shell_static.py::test_the_ollama_down_text_mirrors_errors_py`.
    location: src/wavelocalai/web/static/components/wl-error.js
    severity: low
---

# Story 1.10 : choisir un modèle au clavier, et suivre l'étape d'un run

## Objectif

Deux Custom Elements partagés, sans Shadow DOM, que les écrans de chat, d'Arène et de documents réutiliseront : `wl-model-picker`, un sélecteur de modèle filtrable au clavier qui groupe « Sur cette machine » et « Cloud » et dit pourquoi un modèle est proposé, et `wl-run-status`, qui nomme l'étape d'un run, chronomètre et offre Arrêter (et Échap). Aucune route serveur ajoutée : tout vient de `/api/models`, `/api/models/defaults`, du flux `/api/runs/{id}/events` et de `POST /api/runs/{id}/cancel`.

## Critères d'acceptation et preuves

1. **Combobox ARIA APG.** Champ `role="combobox"` (`aria-autocomplete="list"`, `aria-expanded`, `aria-controls`, `aria-activedescendant`), liste `role="listbox"` en groupes `role="group"` nommés, options `role="option"` avec `aria-selected`. Taper « qwen » filtre (tous les mots de la saisie dans le nom, le tag, le fournisseur ou l'éditeur) ; ↓ ↑ déplacent l'option active, Entrée choisit, Échap ferme et rend le nom choisi, Alt+↓ ouvre, Tab ferme ; le nombre de résultats est annoncé. Preuve : `test_the_combobox_follows_the_aria_pattern`, `test_typing_qwen_filters_the_list_and_enter_picks_the_first`, `test_a_filter_without_match_says_so_and_escape_restores_the_choice`, `test_keyboard_alone_opens_moves_picks_and_closes`.
2. **Groupes, tri, types.** « Sur cette machine » (origine locale ou inconnue) puis « Cloud », ce dernier seulement si la bascule du store l'autorise. Règle de tri explicite, par groupe : le défaut d'abord, puis `fits` vrai, puis `fits` inconnu, puis `fits` faux, puis le nom. Seuls les modèles `kind == "chat"` : ni embedding ni reranker. Preuve : `test_groups_are_local_first_without_embedding_or_reranker`, `test_the_cloud_group_exists_only_when_the_cloud_is_allowed`.
3. **Ligne de modèle.** Nom, `wl-badge` d'origine (Local, Cloud, Origine inconnue : toujours un texte), taille en Go, « Tient en mémoire » ou, sinon, « Ne tient pas en mémoire (21,4 Go requis) » avec une icône d'avertissement (le modèle reste choisissable), « Besoin en mémoire inconnu » sans `fits`, débit mesuré s'il existe, pastilles « Outils vérifiés », « Raisonnement », « MoE 3B actifs » (actifs < total), « Par défaut ». Le front ne calcule rien : `fits`, `needed_gb` et `throughput_tps` viennent de l'API. Un modèle `available: false` est listé avec sa raison (Ollama ne répond pas, clé absente) et ne se choisit pas. Preuve : `test_each_row_shows_badge_size_memory_throughput_and_pills`, `test_an_unreachable_model_is_listed_with_its_reason_and_cannot_be_chosen`.
4. **Défaut et raison en aide.** Au premier chargement, le défaut de l'usage (`purpose`) est choisi et « Proposé par défaut : <nom>. <raison> » est le texte d'aide relié par `aria-describedby`. Sans modèle de conversation, `wl-error` montre le message puis l'action de `no_model`. Preuve : `test_the_default_is_chosen_and_its_reason_is_the_help`, `test_no_model_shows_the_error_message_then_its_action`.
5. **Mode multi.** Attribut `multi` : cases dans la liste (`aria-multiselectable`), la liste reste ouverte, choix en pastilles retirables (bouton « Retirer <nom> », ou Retour arrière sur un champ vide), un modèle une seule fois, `el.values` expose la liste, événement `wl-model-change`. Preuve : `test_multi_ticks_three_models_then_removes_one`, `test_multi_chips_are_removable_by_button_and_by_backspace`, `test_a_model_appears_once_and_the_component_exposes_the_list`.
6. **Cloud coupé.** Le composant suit `store.allowCloud` (et l'état d'Ollama) ; si un modèle cloud choisi disparaît, il est retiré, un avis `role="status"` le dit (« « claude-haiku-5-5 » est retiré de la sélection : le cloud n'est plus autorisé. ») et un bouton « Utiliser <défaut local> » le propose, sans choisir à la place de la personne. Les requêtes portent `allow_cloud=false` tant que la bascule est coupée. Preuve : `test_turning_the_cloud_off_removes_a_cloud_choice_says_so_and_proposes_the_local_default`, `test_multi_cloud_choice_is_removed_and_the_others_stay`, `test_requests_stay_on_the_server_and_ask_for_the_cloud_only_when_allowed`.
7. **`wl-run-status`.** `el.runId = "<id>"` suit le run par le client SSE unique (`connectRun`) : « Chargement du modèle en mémoire… » (`model_loading`), « Génération… » (`model_loaded`, `token`), puis « Terminé », « Arrêté », « Échec » (avec `wl-error` pour l'enveloppe de `run_ended.data.error`) ou « Interrompu ». Chronomètre local (`role="timer"`) parti de l'horodatage de `run_started`, figé à `run_ended`. Un run terminé est rejoué jusqu'à sa fin. Preuve : `test_the_run_goes_through_loading_generation_and_the_end`, `test_the_timer_runs_locally_and_stops_at_the_end`, `test_a_failed_run_shows_the_error_envelope`, `test_a_finished_run_is_replayed_to_its_end`.
8. **Arrêter et Échap.** Le bouton et la touche Échap appellent `POST /api/runs/{id}/cancel` ; l'état final vient du flux (`cancelled`, vérifié par `GET /api/runs/{id}`). Échap qui ferme la liste du sélecteur n'arrête pas le run. Preuve : `test_the_stop_button_cancels_the_run`, `test_escape_cancels_the_run_from_the_keyboard`, `test_escape_closes_an_open_list_without_stopping_the_run`.
9. **Accessibilité et trafic.** axe-core sans violation ni exclusion, clair et sombre : liste du choix unique ouverte (avec le groupe Cloud), liste multiple ouverte, run en cours et terminé, après un choix. Aucune requête hors de `127.0.0.1` (garde du contexte E2E, run piloté par l'adaptateur `fake`, listes simulées par `page.route`). Preuve : `test_axe_finds_no_violation_with_both_lists_open_and_a_run_going[light|dark]`.
10. **Cohérence.** `tests/v2/unit/test_picker_static.py` (4 cas : textes tous utilisés, pas de Shadow DOM ni d'`EventSource`, pas de calcul de mémoire), `test_layers.py`, le budget de lecture et les tests de textes de la coquille restent verts ; aucun code de `src/core/`, `src/app/`, `scripts/` touché ; `errors.py` inchangé ; `controle_rapide.py` sans erreur.

## Fichiers

- `src/wavelocalai/web/static/components/wl-model-picker.js`, `wl-run-status.js` (nouveaux), `components/index.js` (deux exports)
- `src/wavelocalai/web/static/core/api.js` (`api.models`, `api.modelDefaults`, `api.cancelRun`), `components.css` (blocs `wl-picker-*` et `wl-run-*`), `i18n/fr.json` (`components.picker`, `components.run_status`)
- `tests/v2/e2e/test_picker.py` (25 cas), `tests/v2/e2e/fixtures/picker.{html,js}`, `tests/v2/unit/test_picker_static.py` (4 cas)

## Choix notables

- Aucun module de la 1.9 recréé : `core/sse.js` (`connectRun`), `core/store.js`, `core/api.js`, `core/format.js`, `wl-badge` et `wl-error` sont réutilisés ; l'API n'a reçu que trois appels en plus. Aucune route serveur n'est ajoutée.
- La liste défile elle-même (`.wl-picker-listbox`), et non son conteneur : axe reconnaît ainsi la fenêtre d'un combobox ; un conteneur défilant sans contenu focalisable est une violation de `scrollable-region-focusable`.
- Un choix unique est sélectionné dans le champ au clic : la saisie remplace le nom au lieu de s'y ajouter.
- Les listes de `/api/models*` sont simulées côté navigateur : les composants se testent sans Ollama, et les routes serveur ont leurs propres tests (stories 1.5 et 1.6).
- `autouse` côté tests : les runs lancés par un test sont annulés à sa fin (un seul run de chat à la fois).

## Reports

Voir l'en-tête `deferred` : étapes RAG et agents, premier écran qui monte les composants, Échap des panneaux de la barre haute, Markdown dans l'action de `no_model`.
