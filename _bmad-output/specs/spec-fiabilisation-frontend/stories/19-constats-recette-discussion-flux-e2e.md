---
title: 'Constats de la recette de la story 18 : réponse vide de la Discussion, flux interrompu, tests e2e'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: 'd7d965d06a8478d00d0e8a7d1d5972876d44b097'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/18-constats-recette-arene-agents.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Le cahier de recette de la story 18 (V2, et 2 échecs e2e sur 35) a relevé trois écarts :
- **Discussion de l'Assistant documentaire, Qwen 3.5 0.8B** : la réponse affiche « None ». Au rerun suivant, la page plante (`StreamlitAPIException`, `st.download_button`, `rag/chat.py:125`) et le champ de question disparaît. `extract_thought("")` renvoie `(None, None)`, et le raisonnement (`ReasoningChunk`) est ignoré.
- **Flux Ollama tronqué.** Ollama 0.34.2 ferme parfois le flux HTTP en 200, sans fragment `done`. Reproduit le 29/09 : 1 flux sur 8, à chaud comme à froid, sur `gemma3:1b` et une consigne française. Son journal montre `common_chat_peg_parse: unparsed Content-only output` sur un caractère UTF-8 coupé, avant « : », puis `cancel task`. L'app affiche alors le début de la réponse comme une réponse complète, avec un débit « estimé » et sans chargement. C'est l'échec e2e `test_lab_throughput_excludes_loading`.
- **Juge attendu dans `test_arena_two_local_models_with_judge`.** Le test calcule le juge attendu avec une mémoire infinie (`1e6`). L'app, elle, écarte les modèles qui ne tiennent pas dans la mémoire mesurée. Résultat observé : app « Qwen 3.5 4B », test « Gemma 4 E4B (QAT) ».

**Approach:**
1. **Discussion.** Une réponse vide est stockée en `""` (jamais `None`). Elle s'affiche « Réponse vide » avec son raisonnement dépliable, comme dans le Chat libre. Le raisonnement transmis à part est conservé. Le bouton Télécharger ne plante plus, même sur un historique qui contient déjà `None`.
2. **Fournisseur Ollama.** Un flux qui se termine sans fragment `done` lève une erreur dédiée au message lisible : réponse interrompue. Les pages l'affichent comme un échec, jamais comme une réponse.
3. **Tests e2e.** Le test de l'Arène calcule le juge attendu avec la mémoire réellement disponible, selon la règle de l'app. Pour `ensure_cold`, voir la décision ci-dessous.

Décision de l'utilisateur (29/09, option A). `ensure_cold` reste tel quel : les mesures montrent qu'il attend déjà le déchargement. Sur 10 appels à froid, `/api/ps` ne listait plus le modèle dès le premier sondage, et chaque appel suivant a mesuré un vrai chargement (`load_duration` ≈ 2,2 s). Le test du Banc d'essai relance une fois un passage qui affiche « Réponse interrompue » ; pour le passage à froid, il recommence par `ensure_cold`. Il échoue toujours si l'app compte le chargement dans le débit.

## Boundaries & Constraints

**Always:**
- La logique reste dans `src/core`, sans `streamlit`.
- Tous les tests de `tests/unit` et `tests/app` sont sans réseau : flux Ollama simulés.
- Une réponse interrompue n'est jamais stockée dans l'historique ni envoyée au juge.

**Never:**
- Modifier `scripts/`, `benchmarks/`, `data/`, `config/models_catalog.json` ou `src/core/config.py`.
- Relancer automatiquement une génération interrompue (hors intention ; différé).
- Changer la règle du juge ou de la mémoire disponible de l'app.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Discussion, réponse vide | `ReasoningChunk` puis aucun `str` | « Réponse vide » ; dépliant « Raisonnement » ; historique `content == ""` ; rerun sans exception | N/A |
| Discussion, `<think>` seul | `"<think>x</think>"` | Même rendu, raisonnement « x » | N/A |
| Ancien historique | message assistant `content: None` | « Réponse vide », Télécharger inactif, sans exception | N/A |
| Flux complet | fragments puis `done: true` | Inchangé | N/A |
| Flux tronqué | fragments sans `done` | Pas de `InferenceMetrics` ; `InterruptedResponseError` levée | Chat libre, Banc d'essai, Arène, Discussion : « Réponse interrompue… » ; question gardée, rien d'ajouté |
| Juge tronqué (Arène) | réponse du juge sans `done` | Réponse non évaluée, avec la raison | N/A |

</frozen-after-approval>

## Code Map

- `src/core/metrics.py` : `ReasoningChunk` (l.~50). Y ajouter `InterruptedResponseError(RuntimeError)`, dont le message par défaut est en français : « Réponse interrompue : Ollama a arrêté la génération avant la fin. »
- `src/core/providers/ollama_provider.py:130-160` `chat_stream` : après la boucle, si `final_chunk is None`, lever `InterruptedResponseError` au lieu de produire `ollama_metrics(…, None…)`. Le `except` actuel la relaie telle quelle. `ollama_metrics` garde son repli sur la durée murale (autres appelants et tests).
- `src/core/inference_service.py:26` `InferenceResult` : ajouter `interrupted: bool = False`. Dans `run_inference`, avant `except Exception` : `except InterruptedResponseError` renvoie `error=str(e)`, `interrupted=True` (appel de `on_error` comme ailleurs).
- `src/app/states.py:189` `inference_error_message` : ajouter le cas `interrupted`, avec la constante `INTERRUPTED_MESSAGE` : « Réponse interrompue : Ollama a arrêté la génération avant la fin. Réessayez ; si cela se répète, choisissez un autre modèle. » Le Chat libre (`chat.py:217`), le Banc d'essai (`lab.py:59`) et l'Arène (`arena.py:610`, via `result.error`) en profitent sans autre modification. Le juge de l'Arène (`arena.py:482`, `eval_res.error`) donne déjà « non évalué ».
- `src/app/tabs/rag/chat.py` :
  - l.75-80, historique : `render_answer(msg.get("content"))` à la place de `st.markdown`. Le dépliant « Raisonnement » y est déjà (replié).
  - l.125 : `msg.get("content") or ""`, avec `disabled` si c'est vide.
  - l.196-206 `run_gen` : accumuler les `ReasoningChunk` à part.
  - l.217 : pensée = raisonnement, puis `<think>`, comme `inference_service.py:176-178`. Stocker `clean or ""`.
  - l.222-225 : `render_answer(clean)`.
  - l.273 `except` : si `InterruptedResponseError`, afficher `INTERRUPTED_MESSAGE` au lieu du message générique.
- `src/app/tabs/rag/eval.py:317` : une réponse vide y part aussi au juge. Hors intention : ajouter une entrée à `deferred-work.md`. Relance automatique : même chose.
- `tests/e2e/test_arena.py:65-75` `expected_benchmark_judge` : prendre la mémoire comme `ui.available_memory_gb`, soit `ResourceManager.get_available_ram_gb() + OllamaProvider().loaded_models_ram_gb()`. La mesurer juste avant `_open_arena` et juste après ; accepter les juges des deux mesures, car l'app mesure au premier affichage, entre les deux. Corriger le commentaire « La mémoire disponible n'intervient pas ».
- `tests/e2e/ollama_api.py:49` `ensure_cold` : inchangé.
- `tests/e2e/test_arena.py:108-157` : `_lab_run` accepte `retry_cold: str | None` (le tag). Si `h.ui_errors(page)` contient « Réponse interrompue », il relance une fois : `ensure_cold(tag)` d'abord pour le passage à froid, puis un nouveau clic. Sinon, l'assertion reste la même. Réutiliser `INTERRUPTED_MESSAGE` de `src/app/states.py` pour le texte.
- Tests :
  - `tests/unit/test_llm_provider.py:600-665` (`_ollama_stream_chunks`, `TestOllamaReasoningChunks`) : flux sans `done`, pour le dict et l'objet `ChatResponse` ;
  - `tests/unit/test_metrics.py:270-360` : les deux tests existants gardent un `done` ;
  - `tests/unit/test_inference_service.py` : `interrupted` ;
  - `tests/app/test_states.py:588` (motif `failing_stream`, `_fake_stream` l.~830) : Discussion vide, `<think>`, ancien `None`, interruption ; Chat libre interrompu.

## Tasks & Acceptance

**Execution:**
- [x] `src/core/metrics.py`, `src/core/providers/ollama_provider.py`, `src/core/inference_service.py` -- `InterruptedResponseError`, levée sans `done`, `interrupted` -- flux tronqué jamais présenté comme complet
- [x] `src/app/states.py` -- `INTERRUPTED_MESSAGE`, cas `interrupted` -- erreur lisible partout
- [x] `src/app/tabs/rag/chat.py` -- réponse vide, raisonnement, Télécharger, interruption -- V2
- [x] `tests/e2e/test_arena.py`, `tests/e2e/ollama_api.py` -- juge attendu selon la mémoire réelle ; Banc d'essai relancé une fois après « Réponse interrompue » -- e2e fiables
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- évaluation RAG d'une réponse vide, relance automatique -- traçabilité
- [x] Tests de la matrice (voir Code Map) -- non-régression sans réseau

**Acceptance Criteria:**
- Given poste-rtx3060 et la Discussion avec Qwen 3.5 0.8B, when une question donne une réponse vide et qu'on en pose une seconde, then la première reste « Réponse vide » avec son raisonnement, et aucune exception n'apparaît.
- Given un flux Ollama simulé sans `done`, when il sert le Chat libre, le Banc d'essai, l'Arène ou la Discussion, then la page affiche « Réponse interrompue… » et aucune réponse n'est ajoutée.
- Given poste-rtx3060, when on lance `pytest -m e2e tests/e2e/test_arena.py`, then `test_arena_two_local_models_with_judge` passe, quelle que soit la mémoire libre.

## Implementation Notes

- `InterruptedResponseError` (`metrics.py`) levée par `OllamaProvider.chat_stream` quand le flux se termine sans `done` ; `InferenceResult.interrupted` ; `INTERRUPTED_MESSAGE` dans `states.py`. Hors Code Map : `inference_failure_label` renvoie « Réponse interrompue » pour un résultat interrompu, pour que la ligne de l'Arène et la raison « non évalué » du juge le disent (« le juge n'a pas répondu (réponse interrompue). »).
- Discussion : `render_answer` à l'affichage et au réaffichage, `ReasoningChunk` accumulés à part, pensée = raisonnement puis `<think>`, `content` toujours `""` au pire ; Télécharger inactif sur une réponse vide ; flux interrompu : `INTERRUPTED_MESSAGE`, rien d'ajouté à l'historique.
- e2e : `available_memory_gb()` du test mesurée avant et après `_open_arena`, juges des deux mesures acceptés. `_lab_run(…, retry_cold=tag)` relance une fois après « Réponse interrompue » (`ensure_cold` d'abord pour le passage à froid). Hors Code Map : helper `wait_rerun_started` dans `tests/e2e/helpers.py` ; sans lui, l'alerte du passage interrompu, encore affichée avant le rerun, était prise pour une seconde interruption (échec observé au premier essai).
- Vérifié sur poste-rtx3060 (Ollama 0.34.2) : `pytest -m e2e tests/e2e/test_arena.py` 4/4, puis `test_lab_throughput_excludes_loading` 3 fois de suite.

## Spec Change Log

## Review Triage Log

Revue du 29/09 : Blind Hunter (13), Edge Case Hunter (8), Verification Gap (1 écart). Doublons regroupés par cause.

- Contrôle du juge par défaut sauté dès qu'une mesure ne donne pas de juge d'après le benchmark (blind, edge) — medium, patch : juge attendu calculé par `choose_judge` (benchmark puis mémoire) pour chaque mesure, toujours vérifié.
- Mémoire du test lue sur `OllamaProvider()` (hôte par défaut) et non `LLMProvider` comme l'app (edge) — low, patch : `LLMProvider.loaded_models_ram_gb()`.
- Retour de `wait_rerun_started` ignoré : échec attribué à tort à une seconde interruption (blind, edge) — low, patch : retour vérifié avec un message clair.
- Assertions « texte partiel absent » par égalité d'élément, qui ne peuvent pas échouer (blind) — low, patch : recherche de sous-chaîne.
- Ordre raisonnement puis `<think>` de la Discussion non testé avec les deux sources (verification-gap) — medium, patch : `test_documents_chat_reasoning_and_think_tags`.
- `INTERRUPTED_MESSAGE` recopie `INTERRUPTED_RESPONSE_DEFAULT` (blind) — low, patch : construit à partir de la constante du cœur.
- Autres e2e générateurs (premier message du Chat libre, Arène avec juge) exposés au flux tronqué d'Ollama (blind) — medium, defer : la décision A ne vise que le Banc d'essai.
- Énergie d'une génération interrompue absente du CO₂ (plus de métriques) (blind) — low, defer : génération courte (~150 ms observés), mais biais de mesure dans un démonstrateur carbone.
- HyDE, Self-RAG et évaluation RAG : une interruption devient un repli sur la recherche simple ou un échec générique (blind, edge ×2) — low, rejeté : HyDE et Self-RAG se replient déjà proprement (`hyde.py:57-62`, `self_rag.py:193-212`), l'évaluation compte un échec au lieu de noter un texte tronqué.
- `timed_out` et `interrupted` testés dans un ordre différent par `inference_error_message` et `inference_failure_label` (blind) — false : les deux branches d'`except` de `run_inference` sont exclusives, jamais vraies ensemble.
- Faux juge des tests reconnu par « juge impartial » (blind) — low, rejeté : fragilité de test, message d'échec explicite.
- `test_arena_interrupted_stream` peu exigeant (blind) — low, rejeté : la colonne « Statut » est vérifiée par `test_arena_interrupted_judge_is_not_evaluated`.
- Raisonnement invisible pendant la génération dans la Discussion (blind) — low, rejeté : comme en story 18, affichage à la fin demandé.
- Question sans réponse puis seconde question : deux tours `user` rejoués (blind) — false : la Discussion n'envoie au modèle que la question courante (`payload`), l'historique n'est qu'affiché.
- Tâches de la spec : `ollama_api.py` cité mais inchangé (blind) — rejeté : correctif de la spec de cette story.
- Agents (`ChatOllama`) et fournisseurs cloud sans détection de flux tronqué (blind) — rejeté : l'intention vise le fournisseur Ollama.
- `render_answer` appliqué aux tours `user` vides (edge) — false : `st.chat_input` n'envoie jamais une saisie vide.
- Erreur d'interruption journalisée aussi « Ollama Error » (edge) — low, rejeté : journal seulement, double ligne sans effet pour l'utilisateur.
- Chat libre : tour d'erreur ajouté à l'historique malgré « rien d'ajouté » (edge) — false : le tour stocke `INTERRUPTED_MESSAGE` marqué `error`, jamais la réponse tronquée ; comportement de toutes les erreurs, conforme à « jamais stockée dans l'historique ».

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus d'AGENTS.md s'ils se produisent
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres
- `.venv-app\Scripts\python -m pytest -m e2e tests/e2e/test_arena.py` (Ollama réel, lecture seule) -- expected: réussit

**Manual checks (if no CLI):**
- Recette V2 (Qwen 3.5 0.8B puis Gemma dans la Discussion).
