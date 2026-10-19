---
title: 'Aucun email ne part sans validation explicite (serveur)'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '19a01bd'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/reports-v2-inventaire.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-1.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-2.md'
warnings: []
deferred:
  - summary: >-
      Écart nouveau, variante conservatrice : l'épique ne dit pas ce que le client reçoit quand il répond trop tard, ni comment l'écran retrouve l'appel d'outil de la demande. Ajouts au contrat : le code **`409 approval_not_pending`** (demande déjà traitée, expirée, inconnue, ou run terminé ; `404 run_not_found` si le run n'existe pas) et deux champs additifs de `approval_required`, `call_id` (l'appel d'outil de l'étape `tool_call`) et `expiry_s` (le délai que l'écran affiche). Les clés `destinataire`, `objet` et `corps` sont celles de l'épique. `expired` n'est jamais accepté d'un client (`422`). Le délai `approval_expiry_s` (600 s) est confirmé tel quel : un seul réglage global, sans prolongation.
    evidence: |-
      `tests/v2/web/test_email_approval_api.py::test_no_answer_in_time_expires_and_nothing_is_sent`, `::test_the_approval_route_refuses_unknown_runs_requests_and_decisions`, `errors.py` (`approval_not_pending`), `contrat-api.md` § « Agents (story 6.3) ».
    location: src/wavelocalai/web/routes_agents.py
    severity: low
  - summary: >-
      Écarts nouveaux, variante conservatrice, sur le brouillon et le transport (la v1 acceptait tout `to` contenant `@` et faisait toujours STARTTLS). (1) Un seul destinataire, sans espace, virgule, point-virgule ni chevrons, et aucun saut de ligne dans l'adresse ou l'objet (injection d'en-tête) : sinon `tool_result` en échec **sans** demande. Pas de Cc, Cci ni pièce jointe. (2) Un message qui contient un secret de la configuration (mot de passe SMTP, clé d'API) est refusé avant la demande : le texte montré serait masqué, donc différent du texte envoyé. (3) STARTTLS exigé (TLS implicite sur le port 465) avant d'envoyer le mot de passe ; seul un serveur local (`127.0.0.1`, `localhost`, `::1`) peut s'en passer, ce qui sert aux tests et à un relais local. (4) Texte brut UTF-8, `From` = `SMTP_USER`, délai SMTP de 30 s (constante de `outbox.py`, pas un réglage).
    evidence: |-
      `tests/v2/unit/test_email_approval.py` (`check_draft`, transport), `tests/v2/web/test_email_approval_api.py::test_an_invalid_draft_is_refused_without_asking_the_user`, `::test_the_smtp_password_is_never_shown_nor_sent_by_the_agent`.
    location: src/wavelocalai/agents/outbox.py
    severity: low
  - summary: >-
      Limites connues, variante conservatrice. (1) Annuler le run **après** `approved`, pendant l'envoi SMTP : le fil de l'envoi ne peut pas être interrompu, l'email peut donc partir alors que l'étape `tool_result` n'est jamais publiée (l'utilisateur avait approuvé). Annuler pendant l'**attente** est un refus et rien ne part. (2) Le vrai chiffrement n'est pas rejoué : aucun serveur STARTTLS de test ; les tests prouvent que la négociation précède l'envoi du mot de passe (un faux qui coupe après `STARTTLS`) et qu'un serveur distant sans STARTTLS est refusé, jamais un échange TLS réussi. (3) Aucun vrai serveur SMTP joint, aucun email réel : le test d'intégration (Ollama `qwen2.5:1.5b`) vise le faux SMTP local. (4) `runs_active` du flux système ne porte `awaiting_approval` qu'au prochain instantané : le hub ne pousse pas d'événement système au changement de statut (l'écran de la 6.4 lit `approval_required` sur le flux du run).
    evidence: |-
      `agents/outbox.py::deliver`, `tests/v2/unit/test_email_approval.py::test_starttls_is_negotiated_before_the_password_is_sent`, `::test_a_remote_server_without_starttls_never_receives_the_password`, `tests/v2/integration/test_email_approval_ollama.py`.
    location: src/wavelocalai/agents/outbox.py
    severity: low
  - summary: >-
      Pour la 6.5 et la 6.6 (équipe) : « un outil sensible dans une équipe suit l'approbation de 6.3 ». Le hub accepte plusieurs demandes en attente par run (le run reste `awaiting_approval` tant qu'il en reste une) et la boucle prend ses actions sensibles par paramètre (`AgentLoop(actions=…)`, `build_actions(settings)`), mais `approval_required` n'a pas de champ `agent` : la 6.5 l'ajoute (additif) si l'écran d'équipe doit dire quel agent demande. Rien n'est câblé côté équipe ici.
    evidence: |-
      `runs/hub.py::request_approval`, `tests/v2/unit/test_approval_hub.py::test_the_run_stays_awaiting_until_every_pending_request_is_answered`.
    location: src/wavelocalai/agents/loop.py
    severity: low
---

# Story 6.3 : aucun email ne part sans validation explicite (serveur)

## Objectif

L'outil « Envoi d'email » prépare un email, le hub demande à l'utilisateur de le valider avec le destinataire, l'objet et le corps sous les yeux, et rien ne part sans un `approved` explicite (D2). Serveur seulement : l'écran de validation est la 6.4. Reports B1 (`approval_expiry_s` lu par un code) et B2 (transitions vers `awaiting_approval` du hub) de `reports-v2-inventaire.md`.

## Critères d'acceptation et preuves

1. **Demande** : un appel valide de `send_email` n'est pas exécuté ; le hub publie `approval_required {approval_id, kind: "email", destinataire, objet, corps, call_id, expiry_s}` et passe le run en `awaiting_approval` (nouvelle transition du hub, en mémoire et en base, retour à `running` après la réponse) ; il garde son `kind: agent`. Rien n'est envoyé, aucune connexion SMTP n'est ouverte, tant que `approval_resolved {decision: "approved"}` n'est pas publié ; l'attente n'est pas coupée par `tool_timeout_s`. Preuve : `test_approval_hub.py::test_a_request_publishes_the_details_and_moves_the_run_to_awaiting_and_back`, `test_email_approval_api.py::test_the_email_is_sent_only_after_an_explicit_approval`, `::test_the_approval_wait_is_not_cut_by_the_tool_timeout`.
2. **Réponse par route** : `POST /api/runs/{id}/approvals/{approval_id} {decision: approved|rejected}` (`Origin` contrôlée par le middleware d'AD-19). `approval_resolved` est publié avant que l'agent reprenne ; une seule décision par demande (`409 approval_not_pending` ensuite) ; `expired` refusé d'un client, run inconnu `404`, `Origin` étrangère `403`. Preuve : `::test_a_second_answer_is_refused_and_one_approval_sends_one_email`, `::test_the_approval_route_refuses_unknown_runs_requests_and_decisions`, `::test_a_foreign_origin_cannot_approve`.
3. **Refus, expiration, annulation** : `rejected` et `expired` (sans réponse en `delays.approval_expiry_s`, 600 s, confirmé) n'envoient rien et rendent à l'agent un `tool_result` en échec qu'il lit et annonce ; annuler le run pendant l'attente publie `approval_resolved {rejected}` juste avant `run_ended` et coupe la tâche. Preuve : `::test_a_refusal_sends_nothing_and_the_agent_can_announce_it`, `::test_no_answer_in_time_expires_and_nothing_is_sent`, `::test_cancelling_the_run_is_a_refusal_and_nothing_is_sent`, `test_approval_hub.py::test_no_answer_in_time_is_expired_and_the_run_goes_on`, `::test_cancelling_the_run_rejects_the_pending_request_before_run_ended`.
4. **Redémarrage** : un serveur relancé pendant l'attente passe le run à `interrupted` (`run_ended` synthétique, aucun `approval_resolved`) : l'email n'est jamais envoyé. Preuve : `test_approval_hub.py::test_a_restart_during_the_wait_interrupts_the_run_and_nothing_is_approved`.
5. **Aucune approbation automatique** : `RunHub.resolve_approval` n'est appelé que par la route d'approbation et seul le hub publie `approval_resolved` (test AST) ; `smtplib` n'est importé que par `agents/outbox.py`, dans une fonction (`LAZY_ONLY` de `test_layers.py`), et aucun module de `agents/tools/` n'importe `outbox` ni `approval`. Preuve : `test_email_approval.py::test_a_request_is_answered_from_the_route_only_and_approval_resolved_comes_from_the_hub`, `::test_only_the_outbox_speaks_smtp`, `::test_the_tools_cannot_reach_the_outbox`, `test_builtin_tools.py::test_the_email_tool_only_prepares_a_draft_and_the_module_cannot_send`.
6. **Ce qui est montré est ce qui part** : `EmailAction.prepare` valide le brouillon et capture destinataire, objet et corps ; `execute` envoie exactement cela, même si les arguments changent ensuite. Brouillon invalide (adresse, plusieurs destinataires, saut de ligne, longueurs, secret dans le texte) = échec sans demande. Preuve : `test_email_approval.py::test_the_action_is_prepared_as_shown_whatever_happens_to_the_arguments_after`, `::test_an_invalid_draft_is_a_tool_error`, `test_email_approval_api.py::test_an_invalid_draft_is_refused_without_asking_the_user`.
7. **Mot de passe SMTP masqué partout** : ni dans les événements, l'instantané, les étapes, la liste des outils, la réponse de la route, ni dans ce que lit le modèle, y compris quand l'agent le glisse dans son message ou quand l'authentification échoue. Preuve : `::test_the_smtp_password_is_never_shown_nor_sent_by_the_agent`, `::test_a_wrong_smtp_password_is_a_failed_result_without_revealing_it`, `test_email_approval.py::test_an_error_message_never_contains_the_password`.
8. **Transport** : texte UTF-8 intact, STARTTLS avant le mot de passe, serveur distant sans STARTTLS refusé ; échecs (destinataire refusé, injoignable, authentification) en `tool_result`. Preuve : `test_email_approval.py::test_the_email_is_delivered_in_utf8_without_altering_the_text`, `::test_starttls_is_negotiated_before_the_password_is_sent`, `test_email_approval_api.py::test_a_refused_recipient_and_an_unreachable_server_are_failed_results`.

## Règles écrites

- **L'envoi vit hors des outils** : `agents/outbox.py` (seul module SMTP) est derrière `agents/approval.py` (`PendingAction`, `SensitiveAction`) ; l'outil `send_email` de `agents/tools/` ne fait que contrôler le brouillon. Le test AST « aucun code d'envoi dans `agents/tools/` » de la 6.2 reste vrai tel quel.
- **Une action sensible sans action enregistrée est refusée** (comportement de la 6.1) : seul `send_email` en a une.
- **Un test ne joint jamais un vrai serveur** : faux SMTP local en processus (`tests/v2/fake_smtp.py`, port éphémère sur `127.0.0.1`) ; les `Settings` viennent de `make_settings` ou de `load_settings` avec `env_file` absent et un environnement vide, jamais du `.env`.
- **Couches** : `runs/hub.py` n'importe rien de nouveau ; `agents/outbox.py` n'importe que `agents`, `config`, `errors` ; seul `web/` importe FastAPI.

## Notes de développement

- Nouveaux : `agents/approval.py`, `agents/outbox.py`, `tests/v2/fake_smtp.py`, `test_approval_hub.py`, `test_email_approval.py`, `test_email_approval_api.py`, `integration/test_email_approval_ollama.py`. Modifiés : `runs/hub.py` (`request_approval`, `resolve_approval`, `_resolve`, `_transition`, rejet à la clôture), `runs/repo.py` (`transition_status`), `agents/loop.py` (`_approved`, paramètre `actions`), `agents/service.py` (`build_actions`), `web/routes_agents.py` (route d'approbation), `errors.py` (`approval_not_pending`, en fin de liste), `contrat-api.md` (§ « Agents (story 6.3) » et les deux lignes d'événements), textes de `send_email`, `config.py`, `registry.py`, `basic.py`, `test_layers.py` (`smtplib`, `email`), `test_agent_tools_api.py` (le test « jamais exécuté sans approbation » de la 6.2 est remplacé par ceux de la 6.3).
- Aucune dépendance nouvelle (`smtplib` et `email` sont de la bibliothèque standard ; pas d'`aiosmtpd`). Aucun fichier du front, aucun fichier d'état.

## Rapport de dev

- Tests : nouveaux, 7 (`test_approval_hub`), 22 (`test_email_approval`), 17 (`test_email_approval_api`) et 1 d'intégration, passé sur le vrai Ollama (`qwen2.5:1.5b`, SMTP factice). Régression ciblée (hub, runs, arène, chat, conversations, agents, outils, sécurité, config, erreurs, couches) : 239 passés, 5 sautés (liens symboliques non permis sur ce poste). Aucun E2E, aucune suite complète (poste partagé).
- Contrôle rapide propre. Aucun email réel, aucune connexion hors `127.0.0.1`, `.env` jamais lu.
