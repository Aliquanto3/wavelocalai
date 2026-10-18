---
title: 'Retrouver, exporter et effacer une conversation'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'b5602cd'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-2.md'
warnings: []
deferred:
  - summary: >-
      Les copies `wavelocalai.db.bak-<version>` faites avant une migration (AD-12) ne passent pas par l'effacement : une conversation écrite avant une mise à jour de schéma peut rester lisible dans une de ces copies. Aucune migration n'a lieu avant la prochaine étape du schéma ; à traiter avec la première migration qui suit (supprimer ou purger la copie une fois la migration validée).
    evidence: |-
      `store/migrate.py` : `backup_path` ; la copie n'est faite que sur une base existante qui migre.
    location: src/wavelocalai/store/migrate.py
    severity: low
  - summary: >-
      La liste `GET /api/conversations` est un ajout au contrat d'API (noms de routes indicatifs) : l'écran rouvre « la dernière conversation de chat ». Sans notion de conversation courante côté serveur, une personne qui efface la conversation courante retrouve, au rechargement, la précédente si elle existe encore. Avant la 2.6 aucune conversation ne s'effaçait : il n'y en a donc qu'une par poste en pratique ; une liste de conversations (UX) est hors périmètre. À ratifier dans `contrat-api.md`.
    evidence: |-
      `test_the_list_gives_the_latest_conversation_first_and_filters_by_kind`.
    location: src/wavelocalai/web/routes_conversations.py
    severity: low
  - summary: >-
      Une réponse rouverte montre le tag du modèle (`qwen3.5:2b`) et non son nom d'affichage, et, si le run a été arrêté ou a échoué, aucun pied : ni durée ni débit n'ont été mesurés, et l'estimation du navigateur ne se reconstruit pas. Le CO₂ de chaque réponse est dans l'API et dans les exports ; il s'affiche dans le pied avec la story 2.3 (local) et 2.5 (cloud).
    evidence: |-
      `test_a_stopped_answer_comes_back_marked_stopped_with_its_partial`.
    location: src/wavelocalai/web/static/screens/chat.js
    severity: low
---

# Story 2.6 : retrouver, exporter et effacer une conversation

## Objectif

Rouvrir `#/arene/chat` sur la conversation en cours de la veille, l'exporter (JSON, Markdown) et l'effacer pour de bon, sans toucher au CO₂ déjà compté. Ferme les reports de la story 2.2 (« Télécharger » et « Effacer » attendaient ces routes). La version `2.0.0a2` et la publication sont gérées par l'orchestrateur.

## Critères d'acceptation et preuves

1. **Retrouver.** `GET /api/conversations/{id}` rend messages, raisonnement, et, pour chaque message, le `run` qui l'a écrit (statut, modèle, mesures, `co2`) ; `model` et `temperature` sont ceux du dernier run (le modèle est « gardé par conversation » sans champ ni préférence de plus, rien dans `localStorage`) ; `active_run_id` nomme un run en cours. L'écran, à l'ouverture, relit la dernière conversation de chat (`GET /api/conversations?kind=chat&limit=1`), la remonte telle qu'affichée (réponses en Markdown, raisonnement replié, pied de mesures du serveur, rien d'annoncé), remet le modèle et la créativité, et suit par son flux un run encore actif. Preuve : `test_a_conversation_comes_back_as_displayed`, `test_reasoning_and_the_partial_of_a_stopped_run_are_kept`, `test_an_active_run_is_named_...` ; E2E `test_reopening_the_screen_shows_messages_reasoning_and_metrics_as_displayed`, `test_the_chosen_model_and_creativity_are_kept_with_the_conversation`, `test_a_run_still_active_is_followed_after_a_reload`, `test_a_stopped_answer_comes_back_marked_stopped_with_its_partial`, `test_the_conversation_is_continued_by_the_next_message`.
2. **Exporter.** `GET /api/conversations/{id}.json` et `.md` (pièce jointe `conversation-<8 car.>.json|md`) : messages, raisonnement, modèle et origine, débit D3 avec sa source (`ollama_eval` mesuré, `wallclock` estimé), tokens, durées, `co2` avec sa méthode ou « non mesurable (raison) », jamais 0 pour un inconnu. Les exports ne reprennent que des champs nommés ; les valeurs texte passent en plus par `mask_secrets` (clé collée dans un message comprise). Boutons « Télécharger (JSON) » et « Télécharger (Markdown) ». Preuve : `test_json_export_has_messages_model_origin_rate_and_co2_with_method`, `test_markdown_export_reads_as_a_transcript`, `test_an_unmeasurable_co2_is_said_and_never_zero`, `test_exports_never_contain_a_configured_api_key` (fausse clé Groq configurée) ; E2E `test_download_json_...`, `test_download_markdown_...`.
3. **Effacer.** `DELETE /api/conversations/{id}` (`204`) : le hub supprime `messages` et `run_events`, garde les `runs` sans texte avec `conversation_id` à `NULL`, puis la même tâche de l'écrivain enchaîne `wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)` (`Store.write(..., purge=True)`). Le bouton « Effacer la conversation » l'appelle, sans confirmation (UX-DR21), et annonce « Conversation effacée de ce poste. Le CO₂ déjà compté reste dans le total de la session. » Preuve : `test_delete_removes_the_text_from_the_database_and_the_journal` (texte unique présent avant, absent des octets du `.db` et du `-wal`, `-wal` à 0 octet, `runs` gardés, CO₂ de session identique, `/api/carbon/session` aussi), `test_delete_keeps_the_other_conversations`, `test_a_message_sent_to_a_deleted_conversation_is_refused`, `test_purge_is_checkpoint_vacuum_...` ; E2E `test_clear_deletes_the_conversation_without_confirmation_and_keeps_the_co2` (aucun dialogue, rechargement vide).
4. **Run actif.** Le contrôle se fait dans la transaction de l'écrivain (donc après tout run déjà en file) : `409 conversation_busy` (nouveau code, en fin de liste) avec message, action et `detail.run_id` ; rien n'est effacé. Preuve : `test_delete_with_an_active_run_is_a_409_with_message_and_action`, `test_conversation_busy_is_a_409_...` ; E2E `test_clear_while_a_run_is_active_shows_the_409_message_and_action`.
5. **Budget de lecture.** `GET /api/conversations` (sans paramètre de chemin) entre d'office dans `test_read_budget.py` ; les routes `{id}`, `.json`, `.md` sont mesurées à part (< 300 ms, Ollama arrêté). Preuve : `test_routes_with_a_path_parameter_stay_under_the_read_budget`.
6. **Accessibilité, réseau.** axe-core, clair et sombre, zéro violation sans exclusion (conversation rouverte, aide ouverte, effacement refusé, conversation effacée) ; aucune requête hors 127.0.0.1. Preuve : `test_axe_finds_no_violation_on_a_reopened_conversation`, `..._after_clearing_and_with_the_conflict_message`, `test_every_request_stays_on_127_0_0_1`. Boutons secondaires : désactivés (sans conversation, pendant une requête) par couleurs, comme « Envoyer ».

## Choix de conception

- La lecture (`runs/conversations.py`) et l'export (`runs/conversation_export.py`) sont en lecture seule ; l'effacement passe par le hub (`erase_conversation`), qui reste seul à écrire (AD-5, AD-12). Les mesures d'une réponse viennent de sa ligne `runs` (le flux, effacé avec la conversation, n'est pas relu).
- `Store.write(func, purge=True)` : le vidage suit le `COMMIT` dans la même tâche, sans écriture intercalée.
- Route de test `POST /api/test/runs` : champ `conversation_id` pour prolonger une conversation (échanges scriptés).
- Le test E2E de la story 2.2 vide les conversations avant chaque test (l'écran rouvre désormais la dernière) et attend l'effacement serveur.

## Fichiers

- `src/wavelocalai/runs/conversations.py`, `runs/conversation_export.py`, `runs/repo.py` (`erase_conversation`), `runs/hub.py` (`erase_conversation`), `runs/snapshot.py` (`run_snapshot_row`), `store/db.py` (`purge`), `errors.py` (`conversation_busy`), `web/routes_conversations.py`, `web/app.py`, `web/routes_test.py`
- Front : `screens/chat.js`, `components/wl-chat-thread.js` (`restoreAnswer`), `core/api.js`, `i18n/fr.json`
- Tests : `tests/v2/web/test_conversations_api.py`, `tests/v2/e2e/test_conversations.py`, `tests/v2/e2e/test_chat.py`, `tests/v2/unit/test_store.py`, `tests/v2/unit/test_errors.py`

## Revue

Une passe (Opus), avec la liste du second avis (Haiku).

- medium · second avis 1 · corrigé : `repo.erase_conversation` retire `detail.technical` de `runs.error` (texte d'exception ou de fournisseur pouvant citer le message) ; code, message et action restent. Test `test_delete_drops_the_technical_text_of_a_failed_run` (octets du `.db` et du `-wal`).
- medium · second avis 2 · corrigé : constat prouvé (lecteur en transaction : `wal_checkpoint(TRUNCATE)` rend `busy=1`, `-wal` de 24 Kio avec le texte). `purge_free_space` rend désormais l'état du dernier checkpoint ; incomplète, la purge est journalisée et `Store.purge_pending` la rejoue après l'écriture suivante et à la fermeture. Test `test_a_purge_blocked_by_a_reader_is_reported_then_replayed` (effet disque réel).
- medium · second avis 3 · corrigé : une purge qui lève après le `COMMIT` ne fait plus échouer l'effacement (204) ; elle est journalisée et rejouée comme ci-dessus. Test `test_a_failing_purge_does_not_undo_or_fail_the_committed_erase`.
- medium · second avis 4 · rejeté : mesuré, effacement plus purge = 21 ms sur 5 000 `run_events` (1,4 Mo) et 123 ms sur 50 000 (14 Mo) ; acceptable pour une démo.
- medium · second avis 5 · corrigé : `GET /api/conversations?kind=chat&limit=1` ratifiée dans `contrat-api.md` (ligne Chat libre).
- low · second avis 6 · corrigé en partie : le test d'ordre par `Recorder` reste, l'effet disque est désormais couvert par le test de purge bloquée.
- low · second avis 7 · rejeté : l'export `.md` est un fichier téléchargé, jamais rendu par l'application.
- low · second avis 8 · reporté (déjà en `deferred`) : copies `.db.bak-N` ; pour Anaël, à traiter avec la première migration qui suit.
- low · second avis 9 · rejeté : masquage limité aux secrets configurés, choix de la spec (les exports ne reprennent en plus que des champs nommés).
- low · second avis 10 · rejeté : `forget_conversations` est un nettoyage d'isolation ; un run actif est annulé par la fixture `cancel_leftover_runs`, le test suivant le verrait.
- info · revue · E2E `test_topbar.py::test_a_restarted_server_is_announced_with_a_reload_button` échoue une fois dans la suite complète et passe seul : intermittent, hors périmètre de la story.
