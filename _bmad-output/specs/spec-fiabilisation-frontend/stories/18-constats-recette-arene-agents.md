---
title: 'Constats de la recette du 29/09 : réponse vide dans l’Arène, modèle des agents, petits défauts'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: '9f485893e54153499934b916262449d6ba776f11'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/15-juge-modele-defaut-benchmark-poste.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** La recette dans Chrome du 29/09 (cahier de recette, D4, G2, G1, C5, R1) a relevé trois écarts :
- Dans l’Arène, Qwen 3.5 0.8B rend une réponse vide : tout son texte part dans le raisonnement, que l’app ignore. Le juge local l’a pourtant notée 98/100.
- Sur la page Agents, le modèle proposé par défaut (Granite 4.0 350M) répond sans appeler d’outil.
- Trois petits défauts :
  - le gras de la réponse de l’agent s’affiche avec ses astérisques (GPT-OSS 120B) ;
  - « Annuler » l’email n’affiche aucun message ;
  - à note égale, l’étoile du vainqueur ne désigne pas le même modèle que la section des réponses.

**Approach:** Une story en trois volets, à la demande de l’utilisateur (29/09) :
1. **Arène.** Le fournisseur Ollama transmet le raisonnement (`message.thinking`) à part du texte de la réponse. Une réponse dont le texte est vide :
   - affiche son raisonnement ;
   - est marquée « réponse vide » ;
   - n’est jamais envoyée au juge : elle est « non évaluée », avec cette raison.
2. **Agents.** Le modèle proposé par défaut (Agent seul et Équipe) est choisi d’après le benchmark de ce poste. Candidats : les modèles locaux installés, non dédiés au raisonnement, qui tiennent en mémoire, avec au moins 3B paramètres actifs, aux outils vérifiés par le benchmark (`tool_capability.success_rate` ≥ 0,75, seuil de `tools_validated` du benchmark) et à plus de 10 tokens/s. Sans benchmark de ce poste ou sans candidat : l’ordre actuel.
3. **Petits défauts.**
   - Message « Email non envoyé » après « Annuler » ou la fermeture du dialogue.
   - À note égale, un seul classement pour l’étoile, la carte du vainqueur, le tableau et la section des réponses. « Pourquoi ? » dit « À note égale, le plus rapide ».

Décisions de l’utilisateur (29/09) :
- Agents : parmi les candidats, le plus précis (même précision que le juge : moyenne de `reasoning_avg` et `instruction_following_avg`), puis le plus rapide, puis le tag. Sur ce poste : Gemma 4 E4B (QAT), qui est aussi le juge de l’Arène.
- Étoile : le défaut est bien l’ordre différent de la section des réponses (tri par note seule). Correctif : un seul ordre partout.
- Gras : un appel réel à Groq autorisé pour capturer la réponse. Réponse capturée : `**Résultat :** 7 006 652` (espaces fines insécables), puis `---` et une ligne en italique. Rendue correctement par Streamlit 1.64.0 dans Chrome (`st.markdown` et `st.chat_message`) (`<strong>`, `<hr>`, `<em>`). Le défaut n’est pas reproduit : il sort de cette story et passe en travail différé.

## Boundaries & Constraints

**Always:**
- La logique reste dans `src/core`, sans `streamlit`.
- Le raisonnement n’est jamais compté comme texte de réponse ni envoyé au juge.
- Les autres consommateurs de `LLMProvider.chat_stream` (Discussion documentaire, évaluation, HyDE, Self-RAG) reçoivent le même texte qu’aujourd’hui : ils ne gardent que les `str`.
- Tous les tests sont sans réseau : fournisseur et benchmark simulés.

**Never:**
- Modifier `scripts/`, `benchmarks/`, `data/`, `config/models_catalog.json` ou `src/core/config.py`.
- Changer le juge par défaut ou la présélection de l’Arène.
- Exclure un modèle de la liste de la page Agents : seul le premier proposé change.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Réponse vide | Qwen 3.5 0.8B : `thinking` rempli, `content` vide | Carte « réponse vide », raisonnement dépliable, « non évalué : réponse vide », juge non appelé | N/A |
| Raisonnement et réponse | `thinking` et `content` remplis | Réponse notée ; raisonnement dépliable (Arène, Chat libre) | N/A |
| Balises `<think>` | contenu `<think>x</think>` seul | Même traitement que la réponse vide (plus de repli sur le texte brut) | N/A |
| Agents, poste benchmarké | poste-rtx3060, cloud désactivé | Premier proposé : Gemma 4 E4B (QAT) | N/A |
| Agents, aucun candidat | benchmark sans modèle ≥ 3B aux outils ≥ 0,75 à plus de 10 tokens/s qui tienne | Ordre actuel | N/A |
| Agents, poste inconnu | pas de benchmark | Ordre actuel (outils vérifiés du catalogue) | N/A |
| Email annulé | « Annuler » ou croix | `st.info` « Email non envoyé : envoi annulé. », une fois | N/A |
| Ex æquo | deux notes 72, débits 90 et 60 | Étoile, vainqueur et première réponse : le modèle à 90 ; « À note égale, le plus rapide » | N/A |

</frozen-after-approval>

## Code Map

- `src/core/providers/ollama_provider.py:85-140` `chat_stream`. Aujourd’hui, il lit seulement `message.content` (dict ou objet `ollama.Message`, qui a un champ `thinking` en 0.6.2). Ajout : produire un `ReasoningChunk` (nouveau type, pas un `str`) pour `message.thinking`. Ne pas passer `think=` : le comportement par défaut d’Ollama reste le même.
- `src/core/metrics.py` : y définir `ReasoningChunk` (dataclass `text: str`), à côté d’`InferenceMetrics`. Les types de `LLMProvider.chat_stream` et de `interfaces.chat_stream` sont mis à jour (annotation seulement).
- `src/core/inference_service.py:136-182` `_execute_inference` :
  - accumuler les `ReasoningChunk` dans `thought`, en premier, puis les balises `<think>` d’`extract_thought` ;
  - supprimer le repli `clean_text or full_text` quand un raisonnement existe ;
  - appeler `on_thought` comme aujourd’hui.
- `src/app/tabs/inference/arena.py` :
  - l.563-656 : si `result.clean_text.strip()` est vide et qu’il n’y a pas d’erreur, ne pas appeler `_judge` ; statut `STATUS_NOT_EVALUATED`, raison « réponse vide ». Nouvelle constante de texte dans `src/app/states.py` avec les autres.
  - l.711-733 : trier la section des réponses avec l’ordre de `rank_results` (l.132), au lieu de `_order`.
  - Afficher « Réponse vide » (`st.caption` ou `st.warning` léger) et un expander « Raisonnement » (motif de `chat.py:170-172`, pas `render_thinking_block`, qui contient un emoji et une couleur figée).
  - l.390-410 « Pourquoi ? » : cas de note égale.
  - Étoile de `_quality_matrix` (l.267, 282) : inchangée, elle suit déjà `df.iloc[0]`.
- `src/app/tabs/inference/chat.py:170-172` : affiche déjà `thought` ; rien à changer, sinon un test.
- `src/core/benchmark_results.py:42` `BenchScore` : ajouter `tool_success: float | None` (lu dans `tool_capability.success_rate`, tolérant). `load_machine_benchmark` le remplit.
- `src/core/model_defaults.py` : nouvelle fonction `agent_default(ranked, benchmark) -> ModelChoice | None`, avec les constantes `AGENT_MIN_PARAMS_B = 3.0` et `AGENT_MIN_TOOL_SUCCESS = 0.75`. Réutiliser `BENCH_MIN_SPEED_TPS`, `base_tag` et le motif de `benchmark_judge` (l.449).
- `src/app/views/04_Agent_Lab.py:104-119` : après le tri actuel, placer en tête le label du modèle de `agent_default(menu.ranked…, machine_benchmark())`. `model_menu` expose déjà les choix ; vérifier s’il expose la liste triée, sinon l’y ajouter. `solo.py:125` et `crew.py:272` prennent déjà `sorted_labels[0]` : rien à changer.
- `src/app/tabs/agent/solo.py` :
  - l.281 `_dismiss_email` et l.323 branche Annuler : poser `EMAIL_RESULT_KEY = {"ok": None, "cancelled": True, "to": …}` ;
  - l.328 `_render_email_result` : `st.info("Email non envoyé : envoi annulé.", icon=":material/cancel:")`.
- Tests :
  - `tests/app/conftest.py:178-250` `fake_inference` : ajouter `thought` par tag ;
  - `tests/app/test_states.py:310-380` (Arène) et `tests/app/test_figures.py:552` (étoile) ;
  - `tests/app/test_defaults.py:321-390` : les tests agents attendent aujourd’hui « Qwen 2.5 1.5B · Local · outils vérifiés » sans benchmark. Ils restent valides ; ajouter des cas avec la fixture `machine_benchmark` (l.492) ;
  - `tests/app/test_sovereignty.py:675` `test_email_cancel_sends_nothing` ;
  - `tests/unit/test_llm_provider.py` (flux Ollama simulé), `tests/unit/test_inference_service.py`, `tests/unit/test_benchmark_results.py`, `tests/unit/test_model_defaults.py`.

## Tasks & Acceptance

**Execution:**
- [x] `src/core/metrics.py`, `src/core/providers/ollama_provider.py`, `src/core/inference_service.py` -- `ReasoningChunk`, raisonnement lu à part, pas de repli sur le texte brut -- D4
- [x] `src/app/tabs/inference/arena.py`, `src/app/states.py` -- réponse vide non jugée et marquée, raisonnement dépliable, un seul ordre, « Pourquoi ? » à note égale -- D4, R1
- [x] `src/core/benchmark_results.py`, `src/core/model_defaults.py` -- `tool_success`, `agent_default` -- G2
- [x] `src/app/views/04_Agent_Lab.py` -- modèle de `agent_default` en tête -- G2
- [x] `src/app/tabs/agent/solo.py` -- message d’annulation -- G1
- [x] Tests de la matrice (voir Code Map) -- non-régression sans réseau

**Acceptance Criteria:**
- Given poste-rtx3060 et l’Arène avec Qwen 3.5 0.8B, when la comparaison se termine, then sa carte dit « réponse vide », montre son raisonnement, et le juge n’a reçu qu’une requête par réponse non vide.
- Given poste-rtx3060, cloud désactivé, when on ouvre Agents (Agent seul, puis Équipe), then le premier modèle proposé est le candidat de la règle, avec « outils vérifiés ».

## Implementation Notes

- `ReasoningChunk` (dans `metrics.py`) produit par `OllamaProvider.chat_stream` pour `message.thinking` (dict et `ollama.ChatResponse`), sans `think=`. `_execute_inference` : raisonnement transmis d'abord, puis `<think>` ; `clean_text` n'a plus de repli sur le texte brut. Les autres consommateurs filtrent déjà les `str` : texte inchangé (test).
- Arène : réponse vide non jugée, `EMPTY_ANSWER_REASON` (« réponse vide. ») ; carte `st.warning` « Réponse vide » et expander « Raisonnement » (y compris dans l'expander d'une réponse à 3 modèles : Streamlit 1.64 accepte l'imbrication, vérifié par AppTest). Section des réponses triée par `response_order` (= `rank_results`). « Pourquoi ? » : « À note égale, le plus rapide (+N tokens/s) » quand la note est égale et le vainqueur plus rapide.
- Agents : `agent_default` ; hors Code Map, le libellé du modèle choisi prend « outils vérifiés » même si le catalogue local ne le dit pas (le benchmark les a vérifiés), pour l'AC. Vérifié sur poste-rtx3060 (Ollama réel, lecture seule) : `agent_default` = `gemma4:e4b-it-qat`, premier modèle actuel `granite4:350m`.
- Email : `_cancel_email` partagé par « Annuler » et la fermeture ; rien n'est posé sans brouillon.
- Formatage : `black` et `ruff --fix` appliqués à des lignes préexistantes de `inference_service.py`, `test_inference_service.py`, `test_benchmark_results.py`, `test_defaults.py` (UP045, ligne vide après docstring, F841) pour que la vérification soit propre.

## Spec Change Log

## Review Triage Log

Revue du 29/09 : Blind Hunter (13), Edge Case Hunter (6), Verification Gap (1 écart + 3 autres). Doublons regroupés par cause.

- Réponse vide affichée sans marqueur dans le Chat libre et le Banc d'essai (repli sur le texte brut supprimé) ; tour vide gardé dans l'historique du Chat (blind, edge ×2, verification-gap) — medium, patch : « Réponse vide » dans les deux pages et au réaffichage de l'historique, tests AppTest. Un tour vide dans l'historique existait déjà pour Qwen 3.5 avant la story (texte vide, raisonnement ignoré).
- Plancher de 3B jamais testé comme inclusif (verification-gap) — medium, patch : `test_agent_default_params_threshold_is_inclusive`.
- « outils vérifiés » lu dans le catalogue, même quand le benchmark de ce poste mesure 0 (Gemma 3 1B) (blind) — low, defer : antérieur à la story ; seul le modèle d'`agent_default` reçoit la mention d'après le benchmark.
- Nombre de tokens de repli (`len(full_text) // 4`) sans le raisonnement quand `eval_count` manque (blind, edge) — low, rejeté : antérieur (le raisonnement n'était pas compté avant), Ollama renvoie toujours `eval_count` sur le dernier fragment.
- Client ollama 0.4.x sans champ `thinking` (edge) — false : `getattr(message, "thinking", None)` et `.get` ignorent un champ absent ; 0.6.2 installé.
- Raisonnement non affiché pendant la génération (blind) — low, rejeté : hors intention (affichage à la fin demandé), fonctionnalité nouvelle.
- Seuil 0,75 recopié de `scripts/benchmark_slm.py` sans test de synchronisation (blind) — low, rejeté : un test importerait `scripts/`, que l'app n'importe pas ; commentaire en place.
- Note et débit égaux : vainqueur = ordre de lancement, « Meilleur équilibre » (blind) — low, rejeté : cas rare (deux cloud sans débit), comportement antérieur.
- Réponse vide classée parmi les « non évalué » par débit, devant une réponse dont le juge a échoué (blind) — low, rejeté : ordre secondaire du tableau, correctif = champ et branche de tri.
- Double mention « Non évalué : réponse vide. » et « Réponse vide » avec 3 modèles (blind) — low, rejeté : cosmétique, les deux textes disent la même chose.
- Raisonnement séparé pour Ollama seulement ; champ `reasoning` des API compatibles OpenAI ignoré (blind) — low, rejeté : antérieur, le texte de réponse cloud reste présent.
- Reformatages hors story (`Optional` → `X | None`, jointures de lignes) (blind) — low, rejeté : exigés par ruff et black sur les fichiers touchés.
- Fichiers de la story absents du diff (blind) — false : spec, `stories.yaml` et `deferred-work.md` iront dans le commit.
- Tests manquants : fermeture du dialogue par `on_dismiss` en page, `ChatResponse` sans `thinking`, agents ajoutés à l'Équipe (blind) — low, rejeté : `_dismiss_email` testé, `getattr` couvre l'absence, ajout d'agent déjà couvert par `test_crew_add_agent_uses_the_rule`.
- Réponses de l'Arène indexées par nom affiché (deux tags au même nom) (edge) — low, rejeté : antérieur, noms du catalogue distincts.
- Statut « tout dans le raisonnement » pour un vide sans raisonnement (edge) — false : le statut dit « réponse vide, non notée », sans parler du raisonnement.
- Réponse du juge faite seulement de `<think>` : note illisible au lieu d'une note lue dans le bloc (verification-gap) — low, rejeté : Ollama sépare désormais le raisonnement ; un juge qui ne note qu'en pensée n'a pas répondu.
- `test_chat_shows_reasoning_apart_from_answer` ne passe pas par `ReasoningChunk` (verification-gap) — low, rejeté : chemin couvert par les tests unitaires du fournisseur et du service ; le test couvre la ligne « Chat libre » de la matrice.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus d’AGENTS.md s’ils se produisent
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres

**Manual checks (if no CLI):**
- Recette : D4 (Qwen 3.5 0.8B), G2 (modèle par défaut, équipe), G1 (Annuler), étoile à note égale (D4).
