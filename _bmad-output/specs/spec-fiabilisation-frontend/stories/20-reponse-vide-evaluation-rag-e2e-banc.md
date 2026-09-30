---
title: "Suites de la story 19 : réponse vide de l'évaluation RAG, Banc d'essai e2e face au flux tronqué"
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: '43b277491a2d91dfa9300609d15ef1f1c7c447b9'
route: 'oneshot'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/19-constats-recette-discussion-flux-e2e.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:**
- **Évaluation de la qualité de l'Assistant documentaire** (`src/app/tabs/rag/eval.py`). Un candidat qui ne répond que par du raisonnement (Qwen 3.5 0.8B) est encore envoyé au juge et à Ragas. Son raisonnement transmis à part (`ReasoningChunk`) est ignoré, et le corps de sa réponse s'affiche vide (`st.markdown`). Écart différé par la story 19.
- **`_lab_run` des tests e2e** (`tests/e2e/test_arena.py`). Le Banc d'essai n'est relancé qu'une fois après « Réponse interrompue ». Or Ollama 0.34.2 ferme parfois le flux sans fragment `done` : `common_chat_peg_parse` échoue sur un caractère UTF-8 coupé, environ 1 flux sur 8. Deux interruptions de suite font donc échouer le test sans que l'app soit en cause.

**Approach:**
1. **Évaluation RAG, comme la Discussion et l'Arène (story 18).** Le raisonnement transmis à part est récupéré. La pensée affichée réunit d'abord ce raisonnement, puis les balises `<think>`. La réponse est `clean_answer or ""`. Une réponse vide est marquée « Réponse vide, non notée » dans le suivi. Elle n'est envoyée ni au juge ni à Ragas : résultat « non évalué », raison « réponse vide. ». Son CO₂ et sa latence restent mesurés. Les réponses s'affichent avec `render_answer`.
2. **`_lab_run`.** Jusqu'à 3 passages quand la réponse est interrompue ; avant chaque relance à froid, le modèle est redéchargé (`ensure_cold`). Si les 3 passages sont interrompus, le test est ignoré (`pytest.skip`) et le motif cite le bug d'Ollama 0.34.2 : flux fermé sans `done`, `common_chat_peg_parse` sur un caractère UTF-8 coupé.
3. **Test app.** Un candidat ne répond que par du raisonnement, l'autre répond normalement. Le juge n'est appelé que pour le second. Le statut du premier est « Non évalué : réponse vide. ». Sa réponse s'affiche « Réponse vide », avec son raisonnement.

</frozen-after-approval>

## Implementation Notes

- `src/app/tabs/rag/eval.py` : `_stream_and_capture` renvoie aussi le raisonnement (`ReasoningChunk`) ; pensée = raisonnement puis `<think>`, comme `rag/chat.py` ; `clean_answer or ""`. Réponse vide : ligne « **modèle** : réponse vide, non notée. » dans le suivi, `EvalResult.not_evaluated(EMPTY_ANSWER_REASON)` sans appel d'`evaluate_single_turn` ; CO₂ et latence gardés. Affichage par `render_answer` ; le raisonnement garde son `st.info` actuel.
- `tests/e2e/test_arena.py` : `LAB_ATTEMPTS = 3` et `OLLAMA_TRUNCATED_STREAM_BUG` (motif du `pytest.skip`) ; `ensure_cold` avant chaque relance d'un passage à froid.
- `tests/app/test_states.py` : `test_documents_evaluation_empty_answer_not_judged`, en échec sur le code d'avant (le juge recevait `None`).
- `deferred-work.md` : l'entrée de la story 19 sur l'évaluation RAG d'une réponse vide est traitée ici (le fichier est en ajout seul, entrée laissée telle quelle).
- Vérifié : `.venv-app\Scripts\python -m pytest tests/unit tests/app` 916/916 ; `pytest -m e2e tests/e2e/test_arena.py -k lab_throughput` réussi sur poste-rtx3060 (Ollama 0.34.2) ; ruff et black propres.

## Review Triage Log

Revue du 29/09 : Blind Hunter (10 constats).

- Balises `</content>` et `</invoke>` à la fin de la spec — low, patch : supprimées.
- Notes d'implémentation vides, statut `in-progress` — false : notes écrites pendant la revue, statut passé à `done` à la finalisation.
- Flux interrompu compté comme échec générique dans l'évaluation, avec un conseil erroné — medium, defer : antérieur à la story 20 (rejeté en story 19), entrée ajoutée à `deferred-work.md`.
- Aide de la colonne « Statut » qui ne cite pas la réponse vide — low, patch : aide complétée.
- CO₂ et durée d'une réponse vide non vérifiés par le test — low, patch : assertion ajoutée.
- Chemins `<think>` seul, raisonnement plus `<think>`, réponse blanche non testés dans l'évaluation — low, rejeté : même code que la Discussion, déjà couvert par `test_documents_chat_think_tags_only` et `test_documents_chat_reasoning_and_think_tags` ; `render_answer` traite déjà le blanc.
- Raisonnement dans un `st.info` et non un dépliant comme la Discussion — low, rejeté : hors intention (seul `render_answer` demandé), affichage antérieur.
- Skip e2e qui cite Ollama 0.34.2 sans lire la version — low, rejeté : motif demandé par l'utilisateur ; « Réponse interrompue » n'apparaît que sur un flux fermé sans `done` par Ollama.
- Import `EvalResult` dans un groupe à part — low, rejeté : ruff (isort) accepte, cosmétique.
- « Non évalué » en dur dans le test — low, patch : `NOT_EVALUATED.capitalize()`.
