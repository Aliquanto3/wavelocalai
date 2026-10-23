---
title: 'Un agent appelle des outils et publie chaque étape (serveur)'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '13bcd36'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/reports-v2-inventaire.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
warnings: []
deferred:
  - summary: >-
      Écart nouveau, variante conservatrice : la réponse finale n'est **pas** publiée jeton par jeton. Le service ne sait qu'à la fin du flux d'un tour s'il appelle des outils (son texte est alors une réflexion, `think`) ou s'il conclut ; le texte d'un tour est donc gardé (`Turn`) et la réponse part en un seul `token`, après l'étape `answer`. Le critère de la 6.4 (« la réponse finale arrive en flux dans `wl-chat-thread` ») est tenu par l'événement `token` ; l'effet visuel de frappe progressive est perdu. Alternative plus lourde : publier le texte au fil de l'eau sur un canal provisoire et le requalifier en `think` quand un `ToolCall` arrive (nouvel événement de requalification, front à adapter).
    evidence: |-
      `agents/loop.py::AgentLoop.run`, `inference/streaming.py::Turn`, `tests/v2/web/test_agent_api.py::test_a_task_runs_a_tool_then_answers_and_every_step_is_published` (`token` unique).
    location: src/wavelocalai/agents/loop.py
    severity: medium
  - summary: >-
      Écarts nouveaux, variante conservatrice. (1) Un outil `sensitive` n'est jamais exécuté en 6.1 (refus en `tool_result`) : aucun mécanisme d'approbation n'existe avant la 6.3 (AD-9 interdit tout chemin automatique). (2) Le registre d'outils est vide en production : les outils de la v1, `GET /api/agents/tools` et la disponibilité sont la 6.2 ; un run réel n'a donc des outils que par les tests jusque-là. (3) Borne de tours atteinte : fin `ok` avec la raison pour réponse (`stopped: "max_turns"`), pas `error` (« fin propre avec la raison »). (4) Aucun plafond d'appels d'outils par tour ni dédoublonnage d'appels identiques : la borne est celle des tours (`agents.max_turns`). (5) Le blocage des réflexions de modèles « thinking » étendu d'Anthropic n'est pas rejoué avec les appels d'outils : l'adaptateur n'active pas `thinking` (inchangé). (6) Une conversation d'agent prolongée ne rejoue au modèle que les tâches et réponses finales, pas les outils des tâches passées.
    evidence: |-
      `agents/loop.py` (`SENSITIVE_REFUSAL`, `MAX_TURNS_MESSAGE`), `agents/tools/registry.py`, `tests/v2/web/test_agent_api.py::test_unknown_unreadable_and_sensitive_calls_are_refused_without_running_a_tool`, `::test_the_turn_limit_ends_cleanly_with_the_reason`.
    location: src/wavelocalai/agents/
    severity: low
  - summary: >-
      Écarts additifs à confirmer. `ToolCall` porte un champ `error` (arguments illisibles, jamais devinés) ; Ollama, qui ne donne pas d'identifiant d'appel, reçoit un `id` fabriqué (9 caractères alphanumériques, format exigé par Mistral, revue) pour que les tours d'une boucle ne s'y confondent pas ; `metrics` d'un run `agent` porte `turn` ; `step` porte `turn`, `call_id` et `failed`. Noms consignés dans `contrat-api.md` §Agents (écart n° 18 : fixés par la story serveur). Rien n'a été joué sur un vrai fournisseur cloud (aucune clé, consigne) : les trois formats cloud sont prouvés sous les vrais SDK à transport simulé ; seul Ollama a tourné pour de vrai.
    evidence: |-
      `models/port.py::ToolCall`, `models/tool_format.py`, `tests/v2/unit/test_tool_calls.py`, `tests/v2/integration/test_agent_ollama.py`.
    location: src/wavelocalai/models/port.py
    severity: low
---

# Story 6.1 : un agent appelle des outils et publie chaque étape (serveur)

## Objectif

Un modèle local ou cloud appelle des outils en boucle, et chaque réflexion, appel et résultat est publié (`step`), quel que soit le fournisseur. Serveur seulement : l'écran est la 6.4, les outils de la v1 la 6.2, l'approbation de l'email la 6.3, l'équipe la 6.5.

## Critères d'acceptation et preuves

1. **Quatre adaptateurs, trois formats** : le port reçoit des outils au schéma neutre (`{name, description, parameters}`) ; Ollama, OpenAI-compatible (OpenAI, Groq) et Mistral les passent en `{type: "function", function}`, Anthropic en `tool_use` / `tool_result` ; chacun rend des `ToolCall(id, name, arguments)` assemblés depuis son flux, puis accepte le résultat au tour suivant (message `assistant` avec ses appels, message `tool`). Formats lus dans le code des SDK verrouillés (`ollama` 0.6.3, `openai` 2.54.0, `anthropic` 1.15.0, `mistralai` 3.2.0), consignés en tête de `models/tool_format.py`. Des arguments illisibles donnent `ToolCall.error`, jamais une devinette. Preuve : `tests/v2/unit/test_tool_calls.py` (faux clients sous les vrais SDK, 15 tests : requête, appels assemblés, résultat au tour suivant, `response_schema` d'Anthropic gardé à part), `tests/v2/integration/test_agent_ollama.py` (vrai Ollama, `qwen2.5:1.5b`).
2. **`stream_into_run` ne jette plus les `ToolCall`** : avec un `Turn`, le texte (réponse et réflexion) et les appels d'outils d'un tour sont gardés au lieu d'être publiés ; chargement du modèle et `metrics` restent publiés, une relance après un flux coupé ne publie pas de `retry`. Preuve : `test_agent_api.py::test_an_interrupted_model_call_is_retried_once_without_leaking_partial_text`.
3. **`POST /api/agents/runs {mode: "solo", model, tools, prompt, conversation_id?, allow_cloud}`** rend `{run_id, conversation_id}` (conversation `agent` créée par le hub) ; le modèle passe par `registry.resolve` (`cloud_not_allowed` sans `allow_cloud`, fournisseur jamais appelé), les outils par le registre (inconnu, répété ou indisponible : `422 invalid_request` avant tout run), un run `agent` à la fois (`409 run_busy`), `ram_guard` à chaque appel local. Chaque appel de modèle est une feuille `generation` avec son `co2`. Preuve : `test_agent_api.py` (nominal, sans outil et conversation prolongée, outil inconnu, corps invalides, `run_busy`, `ram_guard` sur le vrai adaptateur Ollama, cloud OpenAI sous faux transport avec `allow_cloud`).
4. **Étapes publiées** : `step {lane, step_id, agent, kind: think|tool_call|tool_result|answer, turn, duration_s, summary, tool?, call_id?, arguments?, failed?, artifact_url?, stopped?}`, la réponse finale en `token`, un `metrics` par appel de modèle. Nombre de tours borné par `Settings.agents.max_turns` : borne atteinte = fin `ok` avec la raison (`stopped: "max_turns"`). Preuve : `test_a_task_runs_a_tool_then_answers_and_every_step_is_published` (ordre des événements, champs, messages rendus au modèle, feuilles et `co2`), `::test_the_reasoning_channel_becomes_a_think_step_before_the_answer`, `::test_parallel_calls_run_in_order_and_artifacts_are_referenced`, `::test_the_turn_limit_ends_cleanly_with_the_reason`.
5. **Erreur ou délai d'un outil** : l'étape `tool_result` porte l'erreur en texte (`failed: true`), l'agent la reçoit et poursuit ; nom d'outil non proposé, arguments illisibles et outil sensible sont refusés de même, sans exécution. **Annuler** le run coupe l'appel de modèle (flux fermé) et l'outil en cours. Preuve : `::test_a_failing_tool_is_reported_to_the_agent_which_goes_on`, `::test_a_slow_tool_hits_its_timeout_and_the_agent_receives_it`, `::test_unknown_unreadable_and_sensitive_calls_are_refused_without_running_a_tool`, `::test_cancelling_during_a_tool_cuts_the_tool_and_leaves_no_new_model_call`, `::test_cancelling_during_a_model_call_closes_its_stream`, `::test_agent_secrets_never_reach_the_steps`.
6. **Protocole consigné** : spine §Deferred « Formats d'appel d'outils » (story 6.1, levé) et `contrat-api.md` §Agents (story 6.1) : commande, événements, noms de champs de `step` (écart n° 18), réglages.

## Règles écrites

- **Boucle** (`agents/loop.py`) : un tour = un appel de modèle (feuille `generation`) ; texte et appels gardés ; avec appels : `think?` puis, pour chaque appel dans l'ordre, `tool_call` (avant l'exécution) et `tool_result` ; sans appel : `think?`, `answer`, puis `token`. Le résultat rendu au modèle est tronqué à `agents.result_chars`, le `summary` publié à `agents.summary_chars`, les clés d'API masquées.
- **Registre** (`agents/tools/`) : `AgentTool(id, description, run, parameters, sensitive, available, reason)` ; identifiant `^[a-z][a-z0-9_]{0,63}$` (accepté des quatre fournisseurs). Le registre n'a aucun outil de la v1 (6.2).
- **Couches** : `agents/` importe `inference`, `runs`, `models`, `greenops` ; seul `web/` importe FastAPI ; aucun SDK au niveau du module (`tests/v2/unit/test_layers.py`).

## Notes de développement

- Nouveaux : `models/tool_format.py`, `agents/{loop,service}.py`, `agents/tools/`, `web/routes_agents.py`, `[agents]` dans `wavelocalai.toml` (`AgentSettings`). Modifiés : les quatre adaptateurs et `ollama.py` (outils, appels), `cloud.py` (`chat_text_messages` remplacé par `tool_format.chat_messages`), `inference/streaming.py` (`Turn`), `port.py` (`ToolCall.error`), `web/app.py`.
- Aucune dépendance nouvelle. Aucun fichier du front. Aucun code d'erreur nouveau (`errors.py` inchangé).

## Rapport de dev

- Tests : `tests/v2/unit` en entier (897 passés, 1 sauté), les fichiers `web` voisins touchés par `streaming.py` et `app.py` (chat, chat cloud, RAG, stratégies RAG, Arène, budget de lecture, cycle de vie, sécurité, enveloppe d'erreurs, runs, garde-fou : 172 passés) ; nouveaux : `test_tool_calls.py` (15), `test_agent_tools.py` (5), `test_agent_api.py` (21), `test_agent_ollama.py` (1, vrai Ollama, passé). Aucun E2E, aucune suite complète (poste partagé).
- Le test d'intégration saute si `qwen2.5:1.5b` n'appelle pas l'outil (modèle de 1,5 milliard) ; il l'a appelé à chaque essai.
- Ollama : `qwen2.5:1.5b` déjà installé, aucun téléchargement. Aucun appel cloud réel.

## Revue

Revue Opus du 2026-10-19 (une passe, base `13bcd36`). Second avis (Haiku) repris point par point.

- low · second avis 1 · **corrigé** : `ToolCallDeltas.add` fusionnait deux appels entiers rendus sur le même `index` avec `id = "null"` (Mistral) : le second nom écrasait le premier, les arguments se concaténaient en JSON invalide (ou le second objet remplaçait le premier). Un nom qui revient sans le même `id` ouvre désormais un nouvel appel. Tests `test_whole_calls_on_one_index_without_id_are_not_merged`, `test_a_repeated_name_with_the_same_id_stays_one_call`.
- low · second avis 2 · **corrigé** : `new_call_id` rend 9 caractères alphanumériques (format que Mistral exige pour `tool_call_id`, accepté par OpenAI, Anthropic `^[a-zA-Z0-9_-]+$` et Ollama qui l'ignore) au lieu de `call_` + 12 hexadécimaux, qu'un fragment Mistral sans `id` aurait renvoyé et fait refuser au tour suivant. Contrat mis à jour.
- low · second avis 3 · **corrigé** : les `arguments` de l'étape `tool_call` étaient publiés (et persistés dans `run_events`) sans masquage ; ils passent par `masked` (textes masqués à toute profondeur). `test_agent_secrets_never_reach_the_steps` le vérifie avec une clé imbriquée.
- low · second avis 4 · **rejeté** : la journalisation est masquée à l'écriture par `MaskingFormatter` (`store/logs.py`, secrets de `Settings` passés par `__main__`), exceptions comprises ; le texte rendu au modèle et publié passe déjà par `mask_secrets`.
- low · second avis 5 · **reporté** (écart déclaré) : pas de plafond d'appels d'outils par tour ni de délai global. Bornes existantes : `max_turns`, délai de lane par appel de modèle, `tool_timeout_s` par outil, jetons de sortie du modèle, annulation. À reprendre en 6.2 si un outil réel rend un emballement plausible (plafond par tour et refus en `tool_result`).
- Complexité : 1 constat, low, **rejeté** : `tool_name_of` remonte la conversation pour chaque message `tool` (O(n²) par requête), avec n borné par `max_turns` et les appels d'un tour ; l'historique rejoué d'une conversation prolongée n'a pas de message `tool`. Aucune autre structure qui grossit n'est parcourue à chaque événement.
- medium · conception (flux de la réponse) · **gardé, précisé pour la 6.4** : la réponse finale reste un seul `token` après l'étape `answer`. Motifs : (1) OpenAI, Mistral et Anthropic ne livrent leurs `ToolCall` qu'à la fin du flux, et Claude écrit presque toujours un préambule avant `tool_use` : relayer le texte du tour puis le requalifier ferait apparaître puis disparaître du texte à chaque tour d'outil, pire en démo qu'un bloc ; (2) le hub accumule les `token` `answer` dans le message persisté (`hub._append`), donc une requalification demande un nouvel événement, une purge côté hub (fichier partagé) et un front à deux états, pour un gain visuel seul. **Ce que la 6.4 doit faire** : `wl-run-status` dit « Réflexion… » dès le lancement et après chaque `tool_result` (un appel de modèle est en cours, sa nature n'est connue qu'à la fin), « Appel de l'outil <libellé>… » entre `tool_call` et `tool_result`, « Génération… » à l'étape `answer` ; le `token` qui suit est rendu dans `wl-chat-thread` par le même chemin que le chat (Markdown, pied réduit), sans attendre `run_ended`. Le critère « la réponse finale arrive en flux » se lit comme « par le flux d'événements » ; l'effet de frappe progressive est perdu : à faire confirmer par Anaël à la recette de la 6.4, et, s'il le faut, ouvrir alors la variante avec requalification (événement consigné dans `contrat-api.md`, purge de `run.answer` par le hub comme pour `retry`).
- Vérifié sans constat : branchement (`web/app.py` crée `AgentService`, route incluse), `registry.resolve` avant tout run, `ram_guard` et `LocalSlot` par appel, feuilles `generation` + `co2` (`declare_leaf`), annulation (flux fermé, outil coupé), type de conversation vérifié par le hub, imports lourds absents des modules (`test_layers`).
