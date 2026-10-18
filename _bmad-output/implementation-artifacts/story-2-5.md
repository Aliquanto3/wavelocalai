---
title: 'Une réponse cloud affiche une estimation ou « non mesurable », jamais 0'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'a43ff7d'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-5.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-7.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-4.md'
warnings: []
deferred:
  - summary: >-
      Le pied de réponse de l'écran Chat (story 2.2, autre branche) n'existe pas ici : il doit afficher « 0,9 mg (estimé) » ou « non mesurable » avec son aide, jamais « — » seul ni 0. Les données sont publiées (`metrics.co2` : `mg`, `estimated`, `range_mg`, `reason` en français), la `reason` est le texte d'aide à afficher ; sur une estimation, elle porte la réserve d'ecologits (« … ne publie pas l'architecture de ce modèle : … moins précise. ») et s'affiche aussi en aide, `null` sans avertissement. Le panneau CO2 de session (barre du haut) est fait.
    evidence: |-
      `web/test_chat_cloud_co2.py` (champ `co2` de `metrics`) ; `e2e/test_topbar.py::test_a_cloud_without_any_measure_reads_non_mesurable_never_zero`.
    location: src/wavelocalai/web/static/screens/
    severity: medium
  - summary: >-
      `electricity_mix_zone` reste `None` : ecologits prend alors le centre de données du fournisseur (USA pour OpenAI, Anthropic et Groq/huggingface_hub, SWE pour Mistral). Le pays de `Settings.carbon.country_iso` (FRA) décrit ce poste, pas le serveur du fournisseur ; l'utiliser fausserait l'estimation. À trancher par Anaël si l'on veut une zone réglable.
    evidence: |-
      `test_the_estimate_is_called_by_keyword_with_the_provider_datacenter_zone`.
    location: src/wavelocalai/greenops/cloud_estimate.py
    severity: low
  - summary: >-
      Table Groq : `llama-3.1-8b-instant` ajoutée (vers `meta-llama/Meta-Llama-3.1-8B-Instruct`, même modèle). `llama-3.3-70b-versatile` reste sans entrée (Llama 3.3 absent d'ecologits 0.11.3, Llama 3.1 70B est un autre modèle) : sa réponse est « non mesurable ». Les deux entrées `gpt-oss` sont confirmées.
    evidence: |-
      `test_every_groq_table_entry_exists_in_the_installed_ecologits`, `test_every_declared_direct_cloud_model_is_known_to_ecologits`.
    location: wavelocalai.toml
    severity: low
  - summary: >-
      Une réponse cloud en erreur ou annulée garde « mesure non branchée » comme raison (`NOT_MEASURED`, partagé avec le chemin local de la story 2.3). Une annulation n'annonce pas `carbon_updated` (le hub ferme le run hors de la tâche) : le compteur de non-mesurables se met à jour à la réponse suivante.
    evidence: |-
      `inference/streaming.py` (`NOT_MEASURED`), `inference/chat.py::_announce_carbon`.
    location: src/wavelocalai/inference/
    severity: low
  - summary: >-
      `requirements.txt` et `constraints.txt` (méthode sans uv) ne reçoivent pas `ecologits` : ils ne portent déjà ni `fastapi` ni `uvicorn` de la v2, qui s'installe par `uv sync`.
    evidence: |-
      `pyproject.toml`, `uv.lock` (ecologits 0.11.3, wrapt 2.5.1).
    location: requirements.txt
    severity: low
---

# Story 2.5 : une réponse cloud affiche une estimation ou « non mesurable », jamais 0

## Objectif

Le CO2 d'une réponse cloud est estimé par ecologits après l'appel, ou déclaré « non mesurable » avec sa raison : jamais un zéro, jamais un chiffre inventé. La réponse n'est jamais interrompue par la mesure.

## Critères d'acceptation et preuves

1. `ecologits` épinglé `>=0.11.3,<0.12` (`uv add` ; résolu : 0.11.3), importé dans la fonction. `greenops/cloud_estimate.py::estimate_cloud_co2` appelle `ecologits.tracers.utils.llm_impacts(provider=…, model_name=…, output_token_count=…, request_latency=…, electricity_mix_zone=…)` par arguments nommés, jamais `EcoLogits.init()`, et rend `co2 = {mg, method: "ecologits", estimated: true, range_mg: {low, high}, allocation: "direct"}` (`mg` : milieu de la plage ; kgCO2eq converti en mg). Le calcul ne lit que les tables livrées avec ecologits : aucun réseau (lu dans le code installé, et test avec `socket.connect` refusé). ecologits n'a pas de télémétrie à couper. Preuve : `unit/test_cloud_estimate.py` (`test_llm_impacts_signature_is_frozen`, `test_installed_ecologits_is_in_the_pinned_range`, `test_ecologits_init_is_never_called_...`, `test_nominal_estimate_for_each_provider` pour OpenAI, Anthropic, Mistral et Groq, `test_units_are_milligrams_...`, `test_the_estimate_is_called_by_keyword_...`, `test_ecologits_is_imported_inside_the_function_only`) ; `unit/test_layers.py` reste vert.
2. Groq : la table `[cloud.groq_ecologits]` de `wavelocalai.toml` donne l'entrée `huggingface_hub` ; sans entrée, `co2 = {mg: null, method: "unmeasurable", reason}`. Chaque entrée de la table et chaque modèle déclaré est confirmé contre la version installée. Preuve : `test_groq_without_a_table_entry_is_unmeasurable_...`, `test_every_groq_table_entry_exists_in_the_installed_ecologits`, `test_every_declared_direct_cloud_model_is_known_to_ecologits` ; `web/test_chat_cloud_co2.py::test_groq_model_with_a_table_entry_is_estimated_on_the_open_model` (appel sur `huggingface_hub` / `openai/gpt-oss-20b`) et `..._without_a_table_entry_...`.
3. `errors` non vide, exception, jetons ou durée absents : `unmeasurable` avec une raison en français tirée du code d'erreur (« Anthropic ne publie pas la taille de ce modèle : … » pour `model-not-registered`), le run se termine `ok`. Un `gwp` nul, négatif ou NaN n'est jamais un zéro estimé. Preuve : `test_a_model_unknown_to_ecologits_...`, `test_non_empty_errors_...`, `test_an_exception_is_unmeasurable_...`, `test_missing_tokens_or_latency_...`, `test_a_null_or_invalid_gwp_...` ; `web/test_chat_cloud_co2.py::test_an_ecologits_exception_leaves_the_run_ok_and_unmeasurable`.
4. Branchement : `stream_into_run(..., estimate_co2=…)` calcule le `co2` de la réponse réussie hors de la boucle (`asyncio.to_thread`), à partir de ses jetons et de sa durée murale ; `ChatService` ne le fournit que pour un modèle cloud. Le `co2` est dans l'événement `metrics`, la table `runs` (plage comprise) et l'instantané. Après chaque réponse, `ChatService` publie `carbon_updated` (somme de la session) sur le port `SystemBus`. Preuve : `web/test_chat_cloud_co2.py::test_estimated_cloud_response_is_stored_and_announced` ; `web/test_chat_cloud_api.py` (4 fournisseurs, estimation et plage dans `metrics`).
5. Affichage : le panneau CO2 de session montre « 0,9 mg (estimé) » pour le Cloud, « non mesurable » quand aucune réponse cloud n'a de mesure (jamais 0), et compte les non-mesurables à part (« 1 réponse »). `by_origin.<origine>.unmeasurable_runs` est ajouté à la somme de session (champ additif). Preuve : `e2e/test_topbar.py` (`test_co2_panel_follows_carbon_updated_...`, `test_a_cloud_without_any_measure_reads_non_mesurable_never_zero`) ; `web/test_chat_cloud_co2.py::test_estimated_and_unmeasurable_responses_add_up_separately`. Le pied de réponse est reporté (voir reports).

## Fichiers

- `src/wavelocalai/greenops/cloud_estimate.py` (estimateur), `greenops/session.py` (`unmeasurable_runs` par origine)
- `src/wavelocalai/inference/streaming.py` (`estimate_co2`), `inference/chat.py` (estimateur cloud, `carbon_updated`), `web/app.py` (bus passé au service)
- `src/wavelocalai/web/static/core/topbar.js`, `i18n/fr.json` (Cloud « (estimé) » ou « non mesurable »)
- `wavelocalai.toml` (table Groq), `pyproject.toml` et `uv.lock` (ecologits)
- Tests : `unit/test_cloud_estimate.py`, `web/test_chat_cloud_co2.py`, `web/test_chat_cloud_api.py`, `fake_cloud.py`, `unit/test_carbon_session.py`, `web/test_topbar_support.py`, `e2e/test_topbar.py`

## Revue

Revue Opus du 2026-10-18 sur 30c6fbe, avec la liste du second avis (Haiku). Aucun constat medium ni high.

- LOW, second avis 1, corrigé : les `warnings` d'ecologits (`model-arch-not-released` pour gpt-6-*, claude-*-5-5 ; `model-arch-multimodal`) étaient ignorés. Le contrat n'exige `reason` que si `mg` est nul et ne l'interdit pas sinon : l'estimation reste `estimated: true` et `reason` porte la réserve en français (code inconnu cité). Tests : `test_an_unreleased_architecture_keeps_the_estimate_with_its_caveat`, `test_a_model_without_warning_has_no_caveat`, `test_an_unknown_warning_code_is_cited`.
- LOW, second avis 2, rejeté : le total « 0 mg » est la somme des mesures, défini ainsi par la story 1.7 (« sans run : total 0 mg »), et le panneau dit que les non-mesurables « ne sont pas comptées dans le total » en les comptant à part. La ligne Cloud, seule visée par le critère « jamais 0 », affiche « non mesurable ».
- LOW, second avis 3, rejeté : `contrat-api.md` définit la méthode disponible comme « `ecologits` pour un fournisseur direct » ; `test_every_declared_direct_cloud_model_is_known_to_ecologits` vérifie chaque modèle déclaré contre le référentiel installé, et un modèle inconnu donne `unmeasurable` avec sa raison à l'exécution.
- LOW, second avis 4, rejeté : deux listes de trois fournisseurs (`registry.py`, `cloud_estimate.py`), sans écart ; les fusionner ferait importer `greenops` par `models`, contre le sens des couches. Coût de maintenance seulement.
- LOW, second avis 5, rejeté : les quatre adaptateurs demandent l'usage (`stream_options.include_usage` pour OpenAI et Groq, `message_delta` Anthropic, dernier événement Mistral) ; le repli à 4 caractères ne joue que si le fournisseur l'omet, et l'estimation reste marquée « estimé » avec sa plage.
- LOW, second avis 6, rejeté : la publication passe par `greenops.session.announce_carbon_updated` sur le port `SystemBus` ; `inference` ne fait que l'appeler après la feuille, seul point qui sait qu'elle est close.
- LOW, second avis 7, rejeté : ecologits est une dépendance principale (`uv.lock`, `uv sync --locked` en CI) ; s'il manquait, l'`ImportError` donne « L'estimation d'ecologits a échoué (ModuleNotFoundError) » et un avertissement dans le journal, pas un silence.
- LOW, second avis 8, rejeté : le test AST est doublé d'un test d'exécution qui fait lever `EcoLogits.init` pendant l'estimation (`test_ecologits_init_is_never_called_...`), ce qu'un alias ne contourne pas.
- Vérifié par la revue : réponses réelles d'ecologits 0.11.3 pour chaque modèle déclaré (plage pour OpenAI, Anthropic et `huggingface_hub`, nombre seul pour Mistral, `model-not-registered` pour un inconnu) ; l'import d'ecologits ne charge ni client HTTP ni Hugging Face (aucune télémétrie à couper) ; la CI v2 installe ecologits par `uv sync --locked`.
