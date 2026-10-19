---
title: 'Le garde-fou mémoire chiffre le besoin réel et garde la question'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '4635302'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-4.md'
warnings: []
deferred:
  - summary: >-
      Écarts additifs à `contrat-api.md` (déjà consignés dans le contrat, à ratifier) : `POST /api/models/unload` rend `{unloaded, kept: [{tag, run_id}], failed, free_gb}` et publie aussitôt un `system_state` ; `memory.available_gb` s'ajoute à la mémoire du flux système ; `ram_guard` a le statut 503 ; `detail.needed_gb` n'est PAS le `needed_gb` brut de `GET /api/models` mais la mémoire à avoir de libre (besoin × 1,1 + 0,5 Go de réserve, arrondi au dixième supérieur), pour que « nécessaires » dépasse toujours « libres » quand le garde-fou refuse ; la route de test accepte `{"fail": "<code>", "detail": {...}}`.
    evidence: |-
      `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md`, `inference/memory_guard.py` (docstring), `test_memory_guard_api.py::test_a_chat_that_does_not_fit_...`.
    location: _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
    severity: low
  - summary: >-
      Le garde-fou compare le besoin à la **RAM** libre seulement. Sur un poste avec GPU, un modèle qui tient en mémoire vidéo (ou qu'Ollama charge en partie sur le GPU) peut être refusé à tort quand la RAM libre est basse. La mémoire vidéo libre (NVML, `hardware/nvml.py`) n'est pas lue. Le besoin d'un modèle est aussi l'estimation `taille × 1,25` de `hardware/memory.py` : le cache de contexte (KV) d'un long contexte n'y est pas.
    evidence: |-
      `inference/memory_guard.py::_check` (`reader().available_gb`), `hardware/memory.py` (`SIZE_TO_LOADED`).
    location: src/wavelocalai/inference/memory_guard.py
    severity: medium
  - summary: >-
      Arène locale : les lanes passent l'une après l'autre dans la place, et chacune est jugée contre la RAM libre **du moment**, alors que le modèle de la lane précédente reste chargé (Ollama le décharge de lui-même quand il manque de place). Sur un poste de 16 Go, une lane peut être refusée à tort après une grosse lane. Pistes : compter comme libre la mémoire des modèles chargés inactifs (mais « Décharger » perd alors son rôle), ou décharger le modèle précédent entre deux lanes.
    evidence: |-
      `inference/arena.py::_run_lane` (le garde-fou est appelé dans `_attempt`, à chaque lane).
    location: src/wavelocalai/inference/arena.py
    severity: medium
  - summary: >-
      Écart §7(d) n° 13 (« message de `ram_guard` adapté à l'import »), non tranché : variante la plus conservatrice, **l'import et l'embedding ne sont pas gardés** (seul l'appel de génération l'est ; le modèle d'embedding est petit) et le message est celui du chat. Si Anaël veut un refus à l'import, il faut un texte propre (« Mémoire insuffisante pour indexer… ») et un `ram_guard` sur la feuille `embedding` d'`IngestService`.
    evidence: |-
      `inference/memory_guard.py` (docstring), `rag/embedding_leaf.py` (pas d'appel au garde-fou).
    location: src/wavelocalai/rag/embedding_leaf.py
    severity: low
  - summary: >-
      Arène : « Prendre un modèle plus petit » remplace le modèle de la colonne en échec dans le sélecteur (sans relancer) et le dit par la région `aria-live` seulement : `screens/arena.js` est au plafond de 600 lignes (`test_arena_static`), la notice visible du Chat n'y tient pas. Le changement se voit aux pastilles du sélecteur. Une notice visible est une ligne si le plafond est relevé ou l'écran découpé.
    evidence: |-
      `screens/arena.js` (`onSmallerModel`), `core/ram-guard.js::swapModel`.
    location: src/wavelocalai/web/static/screens/arena.js
    severity: low
  - summary: >-
      Écran Discussion (4.5) : son branchement du garde-fou reste à faire (voir « Contrat laissé à la 4.5 »). L'écran Modèles (5.x) peut appeler `POST /api/models/unload` tel quel : `kept` donne déjà les modèles tenus par un run actif (« Utilisé par une réponse en cours »).
    evidence: |-
      `core/ram-guard.js` (en-tête), `web/routes_models.py::unload_models`.
    location: src/wavelocalai/web/static/core/ram-guard.js
    severity: low
---

# Story 4.8 : le garde-fou mémoire chiffre le besoin réel et garde la question

## Objectif

Avant toute génération locale (chat, lane d'Arène, réponse d'une question RAG), le serveur compare le besoin en mémoire du modèle à la mémoire libre du poste. Si le modèle ne tient pas, le run se termine en `error` avec `ram_guard` : « Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres. », `detail {needed_gb, free_gb, suggested_model}`. Le front en tire deux boutons, « Prendre un modèle plus petit » (choisit `suggested_model` sans relancer) et « Décharger les modèles inactifs » (`POST /api/models/unload`). La question reste dans le champ et dans l'historique ; le front ne calcule rien.

## Critères d'acceptation et preuves

1. **Calcul par `hardware/` ; modèle déjà chargé = aucun blocage à tort.** `hardware/memory.py` chiffre le besoin (`required_gb` : besoin × 1,1 + 0,5 Go de réserve) et le manque (`shortfall_gb`) ; `ModelRegistry.memory_needs()` donne le besoin des modèles locaux connus ; `MemoryGuard` lit `/api/ps` **seulement si le modèle ne tient pas déjà** : un modèle listé par `/api/ps` a un besoin nul (Ollama l'a chargé en entier, sa mesure l'emporte sur l'estimation). Besoin inconnu, modèle non local, Ollama muet, garde-fou en panne : aucun refus. Preuve : `test_memory_guard.py` (règles, besoin, chargé, partiel, inconnu, cloud, panne), `test_memory_guard_api.py::test_a_model_already_loaded_in_ollama_is_not_blocked` (+ `::test_the_same_model_unloaded_is_blocked_with_the_same_memory`), `integration/test_memory_guard_ollama.py` (`/api/ps` réel).
2. **`ram_guard` avant une inférence locale (chat, Arène, RAG).** Le garde-fou s'exécute dans la place « Ollama local », avant le tracker CodeCarbon et avant tout événement de phase (`stream_into_run(guard=)`) ; la feuille se termine en `error` (sans relance ni mesure : `co2` « modèle non chargé : mémoire insuffisante »), le run en `error` avec l'enveloppe. Message exact : « Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres. » (nombres à la française par `_fill`). Le modèle n'est jamais appelé. Une lane d'Arène refusée échoue seule (`lane_status failed` avec l'enveloppe), les autres continuent ; une question RAG garde ses `sources`. Preuve : `test_a_chat_that_does_not_fit_ends_in_ram_guard_and_keeps_the_question`, `test_a_refused_chat_leaves_a_leaf_without_a_measure_and_says_why`, `test_an_arena_lane_that_does_not_fit_fails_alone_with_its_envelope`, `test_a_rag_question_that_does_not_fit_keeps_its_sources_and_ends_in_ram_guard`, `test_a_model_that_does_not_fit_raises_ram_guard_with_the_real_need`.
3. **`detail` : `needed_gb`, `free_gb`, `suggested_model`.** Clés déclarées avec `ram_guard` dans `errors.py` (AD-18, statut 503) ; `needed_gb` arrondi au dixième supérieur, `free_gb` à l'inférieur (un chiffre affiché ne cache jamais le refus). `suggested_model` : le plus gros modèle de conversation local (besoin brut) qui tient, un modèle déjà chargé tenant toujours ; le modèle refusé et les embeddings ne sont jamais proposés ; `null` si rien ne tient. Preuve : `test_the_suggestion_is_the_biggest_local_chat_model_that_fits`, `test_no_suggestion_when_nothing_fits`, `test_the_refused_model_is_never_its_own_suggestion`, `test_loaded_models_count_for_the_suggestion_too`, `test_ram_guard_declares_its_machine_keys_and_keeps_the_text_french`.
4. **Question gardée ; le front ne calcule rien.** Le message utilisateur est écrit à la création du run : il reste dans `GET /api/conversations/{id}`. Le Chat rend la question au champ (sauf si la personne a déjà tapé autre chose) ; l'Arène ne vide jamais sa question. `wl-error` lit l'enveloppe et ne calcule rien (test statique). Preuve : `test_the_question_stays_in_the_field_and_in_the_history`, `test_a_question_typed_in_the_meantime_is_never_overwritten` (E2E), `test_the_component_computes_nothing_it_only_reads_the_envelope`.
5. **Deux actions, dans le Chat et l'Arène.** `wl-error` (composant d'erreur partagé) rend, pour `ram_guard`, « Prendre un modèle plus petit » (si le serveur propose un modèle ; sinon « Aucun modèle installé ne tient dans la mémoire libre. ») et « Décharger les modèles inactifs ». Le premier émet `wl-use-model` (`detail.model` = `suggested_model`) : le Chat choisit le modèle dans `wl-model-picker`, l'Arène remplace celui de la colonne en échec ; aucun des deux ne relance. Preuve : E2E `test_a_refused_chat_says_the_real_need_and_offers_the_two_actions`, `test_take_a_smaller_model_selects_the_proposal_without_relaunching`, `test_without_a_proposal_only_the_unload_action_is_offered_and_the_server_says_why`, `test_an_arena_lane_refused_for_memory_offers_the_actions_and_the_others_go_on`, `test_in_the_arena_the_proposal_replaces_the_refused_model_without_relaunching`.
6. **`POST /api/models/unload`.** Décharge (`/api/generate` avec `keep_alive: 0`, `/api/embed` si le modèle est un embedding) les modèles chargés qu'aucun run actif n'emploie (`RunHub.active_models()` : racines et feuilles), attend que `/api/ps` ne les liste plus (3 s au plus), rend `{unloaded, kept, failed, free_gb}` et publie aussitôt un `system_state` : `memory.available_gb` (nouveau) se met à jour sur le flux sans attendre le tick de 2 s ; la barre haute le montre (« Mémoire libre »). Ollama muet : `503 ollama_down`. Preuve : `test_unload_leaves_the_model_of_a_running_chat_and_frees_the_others`, `test_unload_with_nothing_loaded_is_a_calm_no_op`, `test_unload_reports_a_model_ollama_refuses_to_release`, `test_unload_says_ollama_is_down_with_the_standard_envelope`, `test_unloading_leaves_the_models_a_run_uses`, E2E `test_a_real_unload_empties_ollama_and_the_free_memory_follows_the_stream` (vraie route, Ollama simulé qui perd son modèle, barre haute), `integration/test_memory_guard_ollama.py` (déchargement réel de `qwen2.5:1.5b`, chargé par le test seulement).
7. **Accessibilité.** axe-core sans violation, clair et sombre, sur le refus dans le Chat (puis à 320 px, sans défilement horizontal) et dans l'Arène ; le résultat du déchargement s'écrit dans une zone `role="status"` déjà présente et le bouton garde son focus. Preuve : `test_axe_finds_no_violation_on_the_chat_refusal`, `test_axe_finds_no_violation_on_the_arena_refusal` (clair, sombre), `test_unload_inactive_models_calls_the_server_and_reports_the_result` (zone de statut, focus gardé).

## Règles écrites

**Besoin chiffré** (`hardware/memory.py`). `needed_gb` du modèle (empreinte mesurée du catalogue, sinon taille du catalogue ou d'Ollama × 1,25) ; mémoire requise = `needed_gb × 1,1 + 0,5 Go`. Le modèle passe si requis ≤ mémoire disponible (psutil `available`). Un modèle présent dans `/api/ps` passe toujours. Un besoin inconnu ne bloque jamais.

**Modèle proposé.** Parmi les modèles de conversation locaux au besoin connu, autres que le modèle refusé : ceux qui passent (mêmes règles, déjà chargés compris), le plus gros besoin brut d'abord, puis l'ordre alphabétique du tag ; `null` s'il n'y en a aucun.

## Contrat laissé à la 4.5 (écran Discussion)

Le rendu de `ram_guard` est **déjà réutilisable** : l'écran Discussion n'écrit aucun bouton.

1. **Afficher l'erreur par `wl-error`** (comme `wl-run-status` le fait déjà pour `run_ended.data.error`) : l'enveloppe `ram_guard` donne seule le message chiffré et les deux actions. Le message assistant d'un run `rag` refusé s'affiche en échec, sans texte ; les `sources` du run restent affichées.
2. **Garder la question** : à `run_ended` en `error` dont `isRamGuard(data.error)` (`core/ram-guard.js`), rendre la question au champ (comme `keepQuestion` du Chat, `screens/chat.js` : seulement si le champ est vide) ; elle est déjà dans l'historique (`GET /api/conversations/{id}`).
3. **Écouter « Prendre un modèle plus petit »** : `onSmallerModel(host, (tag) => …)` de `core/ram-guard.js` ; choisir `tag` dans le `wl-model-picker` de l'écran, **sans relancer** ; dire le changement dans une région `role="status"`.
4. **Ne rien calculer** : ni besoin, ni mémoire libre, ni modèle proposé (AD-20). Un second appel d'embedding ou d'ingestion n'est pas gardé (écart §7(d) n° 13).
5. Les clés de texte (`components.error.ram_guard_*`, `unload*`) sont dans `components.error` : aucun texte à ajouter côté Discussion pour les boutons ; seul le texte du changement de modèle (équivalent de `chat.model_changed`) est propre à l'écran.

## Écarts ouverts de `sprint-change-proposal-2026-10-19.md` §7(d)

- **n° 13 (« message de `ram_guard` adapté à l'import »), non tranché.** Variante la plus conservatrice : l'import n'est pas gardé, le message est unique (celui du chat, du texte de l'AC). Voir `deferred`.

## Notes de développement

- **Où** : `inference/memory_guard.py::MemoryGuard` (nouveau), appelé par `stream_into_run(guard=)` dans `_attempt`, dans la place, avant `_tracking`. Les trois services (`ChatService`, `ArenaService`, `RagService`) reçoivent `guard` ; `create_app` construit un seul `MemoryGuard` (`app.state.memory_guard`) sur le registre, `Settings.ollama.host` et la lecture de mémoire (`memory_reader=` et `ollama_transport=` : paramètres de test de `create_app`).
- **Chemin courant sans réseau** : le besoin vient du cache du registre (`memory_needs()` n'attend jamais Ollama) ; `/api/ps` (1 s) n'est lu que si le modèle ne tient pas déjà dans la mémoire libre.
- **`RunHub`** : `_Run.models` et `active_models()` (tag -> run racine) ; le déchargement ne touche jamais le modèle d'un run actif, embedding d'une question RAG compris.
- **Front** : `wl-error` porte les deux boutons (zone `role="status"` du résultat présente d'emblée, focus rendu au bouton), `core/ram-guard.js` (`isRamGuard`, `onSmallerModel`, `swapModel`) pour les écrans, `core/tab-keys.js` (clavier des onglets, extrait d'`arena.js` pour tenir le plafond de 600 lignes), `core/api.js::unloadModels`. Barre haute : ligne « Mémoire libre » (`memory.available_gb`). Textes dans `fr.json` (espaces insécables avant `:`), styles par jetons (`.wl-error-buttons`, `-help`, `-result`).
- **Tests** : `FakeOllama` (`tests/v2/fake_ollama.py`) répond à `/api/generate` et `/api/embed` en `keep_alive: 0` (modèle d'embedding : 400 au premier) et à `/api/ps` avec des tailles ; l'`FakeOllama` E2E (`e2e/conftest.py`) décharge aussi ; la route de test accepte `detail` dans l'étape `fail`.

## Fichiers

- `src/wavelocalai/inference/memory_guard.py` (nouveau), `inference/unload.py` (nouveau), `inference/streaming.py` (`guard`, `NOT_LOADED_CO2`), `inference/chat.py`, `inference/arena.py`, `rag/query.py` (`guard=`)
- `src/wavelocalai/hardware/memory.py` (`required_gb`, `shortfall_gb`, arrondis), `hardware/monitor.py` (`available_gb`), `models/registry.py` (`memory_needs`, `ModelNeed`), `models/ollama_ps.py` (`unload_model`), `runs/hub.py` (`active_models`)
- `src/wavelocalai/web/routes_models.py` (`POST /api/models/unload`), `web/app.py`, `web/routes_test.py`, `errors.py` (`ram_guard`, nombres à la française)
- `src/wavelocalai/web/static/components/wl-error.js`, `core/ram-guard.js` et `core/tab-keys.js` (nouveaux), `core/api.js`, `core/topbar.js`, `screens/chat.js`, `screens/arena.js`, `components.css`, `index.html`, `i18n/fr.json`
- `_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md` (route, `available_gb`, `ram_guard`)
- Tests : `tests/v2/unit/test_memory_guard.py`, `test_memory_guard_static.py`, `tests/v2/web/test_memory_guard_api.py`, `tests/v2/e2e/test_memory_guard.py`, `tests/v2/integration/test_memory_guard_ollama.py` ; `fake_ollama.py`, `e2e/conftest.py`, `test_hardware.py`, `test_system.py` réalignés

## Vérification

`pytest tests/v2` : 916 passés (dont 41 ajoutés : 21 unitaires, 9 statiques, 11 web ; les E2E et l'intégration sont exclus par `pytest.ini`). E2E sur Edge (`-m e2e -k "chat or arena"` : 74 passés, dont 7 de cette story ; le fichier `test_memory_guard.py` seul : 14 passés ; `test_topbar.py` et `test_home.py` : 48 passés après l'extension du faux Ollama), axe-core clair et sombre. Intégration réelle (`-m integration`, Ollama `http://127.0.0.1:11434`, `qwen2.5:1.5b` déjà installé, rien de téléchargé ; Ollama sans modèle chargé avant et après) : `test_memory_guard_ollama.py` vert. Contrôle rapide propre. Sans sqlite-vec (CI macOS) : aucune dépendance au vecteur ajoutée ; le garde-fou n'importe que `psutil` (déjà là) et `httpx`.

## Journal

- 2026-10-19 · dev : spec, code, tests unitaires, web, E2E (Edge) et intégration réelle verts ; déchargement réel limité à `qwen2.5:1.5b` chargé par le test (aucun autre modèle n'était chargé).
- 2026-10-19 · décision de conception : un modèle listé par `/api/ps` a un besoin **nul** (et non « réduit à l'écart » par différence avec l'estimation) : la taille mesurée par Ollama est inférieure à l'estimation `taille × 1,25`, la différence aurait refusé un modèle prêt.
