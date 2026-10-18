---
title: 'Le registre dit quels modèles sont disponibles, d''où ils viennent et s''ils tiennent en mémoire'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '68de3ef'
merged: 'feat/v2-hub (story 1.3)'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-2.md'
warnings: []
deferred:
  - summary: >-
      Ports `ChatModel` / `Embedder` et adaptateurs absents : `registry.resolve` rend une `ModelRef` (tag, fournisseur, origine, type). La story 2.1 y ajoute l'adaptateur Ollama et branche le client sur la référence ; `models/port.py` ne contient que `ModelRef`.
    evidence: |-
      Les critères de 1.5 ne portent que sur le refus du cloud et du type.
    location: src/wavelocalai/models/port.py
    severity: low
  - summary: >-
      Les listes de modèles cloud et la correspondance Groq vers ecologits (`[cloud.models]`, `[cloud.groq_ecologits]` de `wavelocalai.toml`) sont des listes fixes de départ, sans appel fournisseur ; le test de contrat ecologits (story 2.5) doit confirmer ou corriger la table Groq (deux entrées gpt-oss seulement).
    evidence: |-
      AD-11 : correspondance Groq explicite dans le `.toml`, test de contrat de signature.
    location: wavelocalai.toml
    severity: low
  - summary: >-
      « Tient en mémoire » ne compte que la RAM disponible lue par psutil : pas de VRAM (NVML), ni la mémoire déjà occupée par les modèles chargés dans Ollama (la v1 la rajoutait via `/api/ps`), ni le contexte (KV cache). Pessimiste quand un modèle est déjà chargé. La fiche machine et NVML viennent en 1.7, le garde-fou chiffré en 4.8.
    evidence: |-
      `MemoryAdvisor` lit `psutil.virtual_memory().available`.
    location: src/wavelocalai/hardware/memory.py
    severity: low
  - summary: >-
      `test_real_launch.py` (story 1.2) échoue sous Windows sans `PYTHONUTF8=1` : la sortie du sous-processus est en cp1252 et le test la lit en UTF-8 (`UnicodeDecodeError` dans le fil de lecture). Antérieur à cette story (échoue aussi sur `feat/v2-serveur`).
    evidence: |-
      `pytest tests/v2` vert avec `PYTHONUTF8=1`, un échec sans.
    location: tests/v2/web/test_real_launch.py
    severity: low
---

# Story 1.5 : le registre dit quels modèles sont disponibles, d'où ils viennent et s'ils tiennent en mémoire

## Objectif

`GET /api/models` rend une liste unique de modèles, locaux (Ollama) et cloud (clé présente et `allow_cloud=true`), avec origine, type, paramètres totaux et actifs, taille, mémoire nécessaire et `fits`, débit mesuré, précision (`null`), méthode CO₂. Elle vient du cache, y compris Ollama arrêté (< 300 ms). `registry.resolve(tag, allow_cloud)` est le seul accès à un modèle et refuse le cloud sans accord.

## Critères d'acceptation et preuves

1. Liste : chaque entrée porte `tag`, `name`, `provider`, `origin` (`local`, `cloud`, `unknown`), `kind` (`chat`, `embedding`, `reranker` ; `is_embedding_model` de la PR #30 recopiée dans `models/classify.py`, « rerank » dans le tag pour le reranker), `params_total_b` / `params_active_b` (MoE, repéré par les experts de `/api/show`, `moe` du catalogue ou une famille en `...moe` : valeur du catalogue, sinon `null`, jamais le total, y compris `/api/show` indisponible ; `test_moe_without_show_never_gets_the_total_as_active_params`), `size_gb`, `needed_gb` et `fits` (`hardware/memory.py` : psutil, empreinte mesurée du catalogue, sinon taille × 1,25, tient si besoin × 1,10 ≤ disponible − 0,5 Go, règle de la v1 ; `null` si la taille est inconnue), `tools_verified`, `reasoning`. Preuve : `tests/v2/unit/test_registry.py::test_lists_local_models_...`, `test_model_helpers.py` (règle de mémoire aux bornes, `is_embedding_model`, paramètres), `tests/v2/integration/test_models_ollama.py` (vrai Ollama : 33 modèles, tailles, `fits`).
2. Même entrée : `throughput_tps` (médiane du `tps` des feuilles `ok` en `ollama_eval`, `null` sans run, via `SqliteRunStats` : feuilles `generation`/`judge`/`embedding` de `runs`, `status = 'ok'`, `tps_source = 'ollama_eval'`, par `model`), `accuracy` toujours `null`, `co2_method` (`codecarbon` en local ; `ecologits` pour openai, anthropic, mistral et un modèle Groq de `[cloud.groq_ecologits]` ; `unmeasurable` sinon), sans importer ecologits. Preuve : `test_registry_store.py::test_throughput_is_the_median_of_ok_ollama_eval_leaves_in_runs` (runs insérés), `test_cloud_models_need_a_key_and_allow_cloud`, `test_run_stats_median_keeps_only_ok_ollama_eval_leaves`.
3. Cache : `/api/show` est mis en cache par `(tag, digest)` (`SqliteFactsStore` sur le store de 1.3 : écrivain unique, lectures courtes ; migration `0002_model_facts.sql` appliquée par `store/migrate.py` après `0001_hub.sql`, instantané `tests/v2/unit/snapshots/schema_v2.sql`) ; le catalogue `config/models_catalog.json` est lu en lecture seule (test d'octets identiques). Preuve : `test_show_is_cached_by_tag_and_digest`, `test_real_catalog_is_read_without_being_written`, `test_model_facts_migration_matches_the_dataclass`, `test_schema.py` (instantané v2), `test_registry_store.py::test_facts_roundtrip_and_digest_keying`.
4. Ollama arrêté : la réponse vient de la dernière liste connue (puis de `model_facts` en base au démarrage à froid), `ollama_up: false`, `available: false`, en moins de 300 ms ; le rafraîchissement se fait en tâche de fond (lancé au démarrage par le `lifespan`, relancé quand le cache de 5 s est périmé, seul le tout premier appel attend 0,1 s). Preuve : `web/test_models.py::test_ollama_down_answers_from_cache_under_300_ms`, `test_models_are_served_from_cache_...`, `test_list_never_waits_for_a_slow_ollama`, `test_registry_store.py::test_model_facts_survive_a_restart_with_ollama_down` (remplir, fermer, rouvrir la même base, Ollama injoignable) et `test_create_app_serves_the_persisted_list_with_ollama_down`, et le test de budget de 1.2 (`/api/models` y entre d'elle-même).
5. Cloud : sans `allow_cloud`, aucun modèle d'origine non locale n'est listé ; avec `allow_cloud=true`, les modèles des fournisseurs dont la clé est dans `Settings` apparaissent en `origin: "cloud"`, id `fournisseur/modèle`. Aucun SDK ni appel réseau cloud. Preuve : `web/test_models.py::test_models_route_lists_local_models_then_cloud_on_request`.
6. `resolve(tag, allow_cloud)` : `origin != "local"` sans `allow_cloud` (absent ou faux) lève `cloud_not_allowed` (403) ; `kind != "chat"` lève `model_not_chat` (422) ; tag inconnu `model_not_found` (404). `resolve_embedder(tag)` : local et `embedding` seulement (`model_not_embedding`). Preuve : `web/test_models.py::test_resolve_through_a_command_refuses_cloud_without_allow_cloud` (commande factice, enveloppe d'erreur complète), `test_registry.py::test_resolve_*`.

## Fichiers

- `src/wavelocalai/models/` : `registry.py`, `port.py`, `classify.py`, `catalog.py`, `facts.py`, `facts_store.py`, `run_stats.py`, `ollama_api.py`
- `src/wavelocalai/hardware/memory.py`
- `src/wavelocalai/web/routes_models.py`, `web/app.py` (registre dans le `lifespan` du hub, route)
- `src/wavelocalai/store/migrations/0002_model_facts.sql`
- `src/wavelocalai/config.py` (`CloudSettings`), `errors.py` (quatre codes en fin de liste : `cloud_not_allowed`, `model_not_chat`, `model_not_embedding`, `model_not_found`), `wavelocalai.toml` (`[cloud.models]`, `[cloud.groq_ecologits]`)
- `tests/v2/` : `unit/{test_model_helpers,test_registry,test_registry_store}.py`, `unit/snapshots/schema_v2.sql`, `web/test_models.py`, `integration/test_models_ollama.py`

## Choix notables

- `models/` n'importe pas `hardware/` (AD-4) : `web/app.py` injecte le `MemoryAdvisor` dans le registre.
- `origin: "unknown"` : modèle d'Ollama sans digest (provenance invérifiable). Il est traité comme non local (refusé sans `allow_cloud`). Un tag distant d'Ollama (`:cloud`, `-cloud`) est `cloud`.
- `tools_verified` : capacité `tools` du catalogue si le modèle y est (comme la v1), sinon celle que déclare Ollama ; le banc (`qb.results/1`) l'affinera à l'étape 5.
- Réponse : `{models, ollama_up, refreshed_at}`.
- Aucune dépendance ajoutée (`psutil` et `httpx` étaient déjà au lock).

## Reports

Voir l'en-tête `deferred` : ports et adaptateurs (2.1), listes cloud et table Groq (2.5), mémoire (VRAM, modèles chargés, contexte), échec Windows de `test_real_launch`.

## Revue

Revue Opus, une passe (2026-10-18).

- medium, revue : `model_facts.fetched_at` en `REAL` (époque Unix) et `refreshed_at` de `GET /api/models` en flottant, contre la convention « ISO 8601 UTC avec `Z` en base et en API » de l'architecture ; la migration ne pourrait plus changer une fois fusionnée. Corrigé : `fetched_at TEXT` (`utc_now_iso()`), `refreshed_at` en chaîne ISO, instantané `schema_v2.sql` régénéré.
- low, revue : `SqliteRunStats.medians()` (lecture de `runs` à chaque appel) tournait sur la boucle. Corrigé : `asyncio.to_thread` dans `list_models`.
- low, revue : test de médiane sans nombre pair de valeurs. Corrigé : deux feuilles pour `moe:30b` (médiane 7,5).
- medium, second avis 1 (MoE sans `/api/show`) : confirmé corrigé ; actifs `null` sans valeur au catalogue, catalogue prioritaire (`params_act`). Reste un cas sans indice MoE (famille `gptoss` hors catalogue, `/api/show` en échec) : actifs = total, faute de signal ; low, non corrigé.
- medium, second avis 2 (cache et débit en mémoire) : confirmé corrigé. Écritures par `store.write` (écrivain unique), lectures courtes ; liste servie Ollama arrêté après redémarrage (test) ; médiane limitée aux feuilles `ok` en `ollama_eval`, `wallclock`, statuts autres et racines exclus (test, désormais pair et impair).
- low, second avis 3 (numérotation, `len(discover())`) : rejeté comme défaut ; le garde-fou reste entier, `test_schema.py` applique les migrations jusqu'à chaque N et compare à `schema_vN.sql` (une `0001` modifiée casse `schema_v1`).
- low, second avis 4 (identifiants cloud non vérifiés) : reporté à la story 2.4/2.5. L'affichage dit `available: true` pour « clé présente », sans prétendre à un appel ; à vérifier contre les listes des fournisseurs lors du premier appel réel.
- low, revue : au démarrage à froid Ollama arrêté, `model_facts` rend aussi les modèles supprimés depuis (la table garde chaque tag). Reporté à la story qui livre `DELETE /api/models/{tag}` : y purger `model_facts` du tag.
- low, revue : `resolve` (cloud ou `unknown` sans `allow_cloud` → 403, type → 422, inconnu → 404), lifespan unique (sonde, hub, registre ; arrêt inverse), tâche de fond annulée à l'arrêt, imports conformes à AD-4 (`models` → `store` seulement) : vérifiés, sans défaut.
