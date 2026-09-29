---
title: 'Réponse interrompue : relance automatique, CO₂ compté, message juste partout'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: 'ac7e0bc3800e433821b3141638cdd3216d17d216'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/19-constats-recette-discussion-flux-e2e.md'
warnings: []
deferred:
  - summary: >-
      Deux coupures de suite : le CO₂ des tentatives coupées n'est compté que dans le Chat libre (total de session), ni dans le Banc d'essai, ni dans l'Arène, ni dans la Discussion ou l'évaluation de l'Assistant documentaire.
    evidence: |-
      Ces onglets n'ont pas de total de session ; lab.py sort de _render_metrics sur erreur, l'Arène met CO2 (mg) à None pour une ligne en échec, rag/chat.py et rag/eval.py jettent e.output_tokens. La matrice de la story ne vise que le Chat libre.
    location: >-
      src/app/tabs/inference/arena.py, lab.py, src/app/tabs/rag/chat.py, eval.py
    severity: low
  - summary: >-
      Effacement du texte partiel et annonce de la relance non observables par AppTest (seul l'arbre final est visible).
    evidence: |-
      Chat libre et Banc d'essai remplacent l'annonce par la nouvelle réponse ; retirer la remise à zéro du texte laisserait passer les tests. À vérifier au navigateur (recette) ou avec un double qui enregistre les écritures de st.empty.
    location: >-
      src/app/tabs/inference/chat.py, lab.py, src/app/tabs/rag/chat.py
    severity: low
---

<intent-contract>

## Intent

**Cause établie le 29/09.** Ollama 0.34.2 ferme parfois le flux HTTP (réponse 200) sans fragment `done`. `common_chat_peg_parse` échoue alors sur un caractère UTF-8 coupé, environ une réponse française sur cinq. Depuis la story 19, l'app lève `InterruptedResponseError` et affiche « Réponse interrompue… ».

**Problem:**
- **Relance manuelle.** L'utilisateur doit relancer lui-même la génération interrompue.
- **Énergie oubliée.** Une tentative coupée ne produit aucune métrique : les tokens générés avant la coupure n'entrent dans aucun CO₂.
- **Mauvais conseil dans l'évaluation.** L'évaluation de la qualité de l'Assistant documentaire range une interruption parmi les échecs génériques. Elle affiche alors le conseil « Vérifiez qu'Ollama est démarré et que le modèle est installé », qui ne correspond pas à la cause.

**Approach:**
- **Relance.** Une génération interrompue est relancée une fois, automatiquement, par une seule logique du cœur. Avant la relance, le texte partiel est effacé et la relance est annoncée. Une seconde interruption s'affiche comme aujourd'hui (« Réponse interrompue… »).
- **CO₂.** Les tokens des tentatives coupées sont ajoutés au CO₂ de la réponse, par la règle unique de la story 23 (`answer_carbon_mg`), donc au total de session. Si les deux tentatives échouent, leur CO₂ est compté quand même.
- **Évaluation.** Une interruption y affiche « Réponse interrompue » au lieu du conseil sur Ollama.

## Boundaries & Constraints

**Always:**
- **Une seule relance, par une seule logique.** Elle vit dans `src/core`, sans `streamlit`, et sert à toutes les générations de l'app qui lisent le flux d'Ollama :
  - Chat libre, Banc d'essai, Arène (modèles et juge), via `InferenceService` ;
  - Discussion et évaluation de l'Assistant documentaire.
- **Texte partiel.** Il n'est jamais montré après l'annonce de la relance, ni stocké, ni envoyé au juge ou à Ragas.
- **Tokens d'une tentative coupée.** On compte les fragments reçus (texte et raisonnement) avant la coupure. `InterruptedResponseError` les transporte.
- **Annonce de la relance.** Son texte (une constante, par exemple `RETRY_MESSAGE` dans `src/app/states.py`) ne contient pas « réponse interrompue », quelle que soit la casse : les tests e2e de la story 21 lisent ce texte comme un échec.
- **Tests.** Aucun réseau : les flux Ollama sont simulés.

**Never:**
- Relancer plus d'une fois, relancer après un délai dépassé ou une autre erreur, ou relancer une génération des agents (`ChatOllama`, hors intention).
- Modifier `src/core/config.py`, `scripts/`, `benchmarks/`, `data/`, `tests/e2e/`, ou le débit et les durées d'une réponse complète (D3).
- Changer `INTERRUPTED_MESSAGE` ou `INTERRUPTED_RESPONSE_DEFAULT`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Relance réussie | 1er flux : 12 fragments sans `done` ; 2e flux complet (40 tokens) | Réponse du 2e flux seule ; annonce affichée pendant la relance ; CO₂ = `answer_carbon_mg(tag, 40 + 12, is_cloud)` | N/A |
| Deux interruptions | 2 flux sans `done` (12 puis 8 fragments) | « Réponse interrompue… » comme aujourd'hui ; rien d'ajouté comme réponse ; CO₂ de 20 tokens compté dans le total de session du Chat libre | N/A |
| Flux complet | `done` au 1er flux | Inchangé : aucune annonce, CO₂ identique à avant | N/A |
| Autre erreur ou délai dépassé | exception autre, `TimeoutError` | Aucune relance, message actuel | N/A |
| Arène | modèle ou juge interrompu une fois | Ligne du suivi qui annonce la relance ; résultat de la 2e tentative | 2 interruptions : comme aujourd'hui (« Réponse interrompue », non évalué) |
| Évaluation de la qualité | candidat interrompu 2 fois | Échec affiché avec `INTERRUPTED_MESSAGE`, sans le conseil « Vérifiez qu'Ollama est démarré » ; autre échec du même lot : conseil actuel pour celui-là | N/A |

</intent-contract>

## Code Map

- `src/core/metrics.py:18-27` : `InterruptedResponseError`. Ajouter des attributs, par exemple `output_tokens: int = 0` (fragments reçus) ; le message par défaut ne change pas.
- `src/core/providers/ollama_provider.py:~126-155` `chat_stream` : compter les fragments `thinking` et `content` reçus, puis les passer à l'erreur levée quand `final_chunk is None`.
- `src/core/inference_service.py` :
  - `run_inference` (l.~80-150) et `_execute_inference` (l.~153-200) : relance unique. Suggestion : un générateur du cœur, par exemple `stream_with_retry(open_stream, on_retry)`, qui rouvre le flux une fois après `InterruptedResponseError` et appelle `on_retry(err)`. `_execute_inference` et les deux onglets RAG le réutilisent.
  - `InferenceCallbacks` : ajouter `on_retry`.
  - `InferenceResult` : ajouter les tokens des tentatives coupées, par exemple `interrupted_output_tokens: int`, renseignés aussi quand le résultat final est une erreur interrompue.
  - Timeout : chaque tentative reste bornée comme aujourd'hui.
- `src/app/states.py:~190-205` : `RETRY_MESSAGE`. `INTERRUPTED_MESSAGE` est inchangé.
- Onglets :
  - `src/app/tabs/inference/chat.py:~176-250` :
    - `on_retry` vide `state["current_text"]` et `msg_container`, puis affiche l'annonce dans la bulle ;
    - CO₂ : `_calculate_metrics` reçoit les tokens des tentatives coupées ;
    - tour en erreur interrompu : garder le CO₂ gaspillé (par exemple `metrics_data={"co2_mg": …}`) pour que `session_co2_mg` le compte, sans afficher de pied de réponse.
  - `src/app/tabs/inference/lab.py:~165-205` : même principe (texte, annonce, CO₂ de `_render_metrics`).
  - `src/app/tabs/inference/arena.py:~598-690` : ligne `status_box.write` à la relance (callback), CO₂ de la ligne. Juge : `_judge` (l.~470-490) relancé par la même logique, sans nouvelle ligne de résultat.
  - `src/app/tabs/rag/chat.py:215-300` : `run_gen` passe par le générateur du cœur ; à la relance, remise à zéro de `full_txt`, de `reasoning_txt` et de `resp_container`, puis annonce dans `status_box`. CO₂ avec les tokens coupés.
  - `src/app/tabs/rag/eval.py:296-310,382-406` : `_stream_and_capture` passe par le même générateur. La boucle distingue une interruption finale : son message est `INTERRUPTED_MESSAGE`, et le conseil sur Ollama n'est gardé que pour les autres échecs.
- CO₂ : `src/core/answer_carbon.py::answer_carbon_mg`, appelé avec `metrics.output_tokens + tokens coupés`.
- Tests :
  - motifs `_ollama_stream_chunks` et `TestOllamaReasoningChunks` dans `tests/unit/test_llm_provider.py:~600-665` ;
  - `tests/unit/test_inference_service.py` ;
  - `tests/app/test_states.py` (motifs `failing_stream`, `_fake_stream`) ;
  - `tests/app/test_answer_carbon.py` (story 23).

## Tasks & Acceptance

**Execution:**
- [x] `src/core/metrics.py`, `src/core/providers/ollama_provider.py` -- tokens reçus portés par `InterruptedResponseError` -- CO₂ d'une tentative coupée
- [x] `src/core/inference_service.py` -- relance unique réutilisable, `on_retry`, tokens coupés dans le résultat -- une seule logique
- [x] `src/app/states.py` -- `RETRY_MESSAGE` sans « réponse interrompue » -- annonce
- [x] `src/app/tabs/inference/chat.py`, `lab.py`, `arena.py`, `src/app/tabs/rag/chat.py`, `src/app/tabs/rag/eval.py` -- texte partiel effacé, relance annoncée, CO₂ compté ; message d'interruption dans l'évaluation -- toutes les générations
- [x] Tests de la matrice (unitaires et AppTest, flux simulés) -- non-régression sans réseau
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les trois entrées traitées (relance automatique et énergie d'une génération interrompue, story 19 ; message de l'évaluation, story 20) -- traçabilité

**Acceptance Criteria:**
- Given un flux simulé interrompu puis complet, when le Chat libre, le Banc d'essai, l'Arène ou la Discussion génère, then la page n'affiche que la seconde réponse, sans « Réponse interrompue », et son CO₂ compte les tokens des deux tentatives.
- Given la page en cours de relance (flux simulé interrompu une fois), when on lit tout son texte, masqué compris, then « réponse interrompue » n'y figure en aucune casse (détection des tests e2e de la story 21).

## Spec Change Log

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 29 findings — high 0, medium 4, low 23, false 2, maybe-false 0
- findings:
  - `[low]` `[reject]` (intent) énergie mesurée (durée murale) plutôt que tokens — la spec retient la règle unique par token de la story 23, dont cette story dépend.
  - `[low]` `[reject]` (intent) CO₂ de chaque réponse gonflé au-delà du total de session — choix de la spec : l'énergie de la tentative coupée appartient à la réponse relancée.
  - `[low]` `[defer]` (intent) annonce éphémère, jamais vue par les tests du Chat libre et du Banc d'essai — limite d'AppTest ; différé avec la ligne verification-gap.
  - `[medium]` `[patch]` (intent) durées différentes selon l'onglet après une relance — groupé avec la ligne blind des durées.
  - `[low]` `[reject]` (intent) délai maximal doublé — la spec borne chaque tentative, et le message « Timeout (Xs) » reste vrai pour une tentative.
  - `[false]` `[reject]` (intent) juge de l'Arène et évaluation inclus — c'est la portée voulue (« toutes les générations »).
  - `[low]` `[reject]` (intent) aucun e2e ni flux Ollama réel — la suite e2e tourne deux fois en fin de série.
  - `[false]` `[reject]` (intent) ligne de suivi « réponse interrompue deux fois » — ajout conforme, affiché seulement sur un vrai échec.
  - `[medium]` `[patch]` (verification-gap) évaluation : issues « coupés seulement » et « un succès, un coupé deux fois » non testées — deux tests ajoutés (un seul message d'erreur, pas « Aucun résultat » ; « 1 modèle en échec »).
  - `[low]` `[defer]` (verification-gap) effacement du texte partiel non observé — limite d'AppTest, différé ; docstring du test de la Discussion corrigée.
  - `[low]` `[patch]` (verification-gap) aide du CO₂ du Banc d'essai non vérifiée — assertion après relance, absente pour un flux complet.
  - `[low]` `[defer]` (verification-gap) CO₂ de deux coupures perdu hors du Chat libre — différé (frontmatter).
  - `[low]` `[defer]` (blind) même constat du CO₂ de deux coupures — même entrée différée.
  - `[low]` `[reject]` (blind) tokens perdus quand la relance échoue autrement, dans les onglets RAG — aucun total ne les afficherait ; même cause que l'entrée différée.
  - `[medium]` `[patch]` (blind) latence de l'évaluation qui compte la tentative coupée — chronomètre relancé dans `on_retry` ; test. La durée totale de la Discussion reste l'attente réelle de l'utilisateur.
  - `[low]` `[reject]` (blind) CO₂ gonflé sans explication hors du Banc d'essai — cosmétique ; aide ajoutée là où les tokens sont affichés à côté.
  - `[low]` `[patch]` (blind) « tokens » pour des fragments — aide et docstring : « environ N tokens (fragments reçus) ».
  - `[low]` `[reject]` (blind) message final muet sur la relance déjà faite — « Réessayez » reste un conseil valable ; `INTERRUPTED_MESSAGE` ne change pas (spec).
  - `[low]` `[patch]` (blind) « Réponse impossible pour : X. Réponse interrompue… » — reformulé : `INTERRUPTED_MESSAGE` puis « Modèles concernés : X. ».
  - `[low]` `[patch]` (blind) deferred-work non à jour (entrée e2e de la story 21, exclusions) — entrée reformulée, relance des agents consignée.
  - `[low]` `[patch]` (blind) critère 2 couvert par un test qui ne voit pas la relance en cours — docstring corrigée ; observation différée.
  - `[low]` `[patch]` (blind) tests fragiles (marge du délai, voie « autre erreur » du helper) — marge portée à 0,5 s, cas `ConnectionError` ajouté ; repérage du juge par son texte rejeté (même motif qu'en story 19).
  - `[low]` `[reject]` (blind) Code Map qui cite `stream_with_retry` — suggestion (« par exemple ») ; la corriger serait éditer la spec. Écart noté au résultat.
  - `[low]` `[reject]` (blind) délai doublé non annoncé — même raison que la ligne d'intention.
  - `[low]` `[patch]` (edge) tour en erreur d'un tag distant hors catalogue qui fait passer la session à « — » — `metrics_data` stocké seulement si le CO₂ est connu.
  - `[low]` `[reject]` (edge) délai par tentative — même raison que la ligne d'intention.
  - `[medium]` `[patch]` (edge) `Latence_s` qui compte la tentative coupée — même correctif que la ligne blind.
  - `[low]` `[patch]` (edge) statut de chargement resté ouvert si la 1re tentative est coupée sans texte — `on_retry` le clôt (Chat libre, Banc d'essai).
  - `[low]` `[defer]` (edge) CO₂ de deux coupures hors du Chat libre — même entrée différée.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus d'AGENTS.md s'ils se produisent
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres

## Auto Run Result

Status: done

**Résumé.**
- `retry_interrupted` (`src/core/inference_service.py`) est la seule règle de relance : une génération coupée par Ollama est relancée une fois.
  - Elle sert `InferenceService.run_inference` : Chat libre, Banc d'essai, Arène (modèles et juge).
  - La Discussion et l'évaluation de l'Assistant documentaire l'appellent directement.
  - Écart assumé au Code Map : une coroutine qui relance une tentative entière, au lieu d'un générateur de flux. Chaque tentative garde ainsi son propre délai.
- À chaque relance, le texte partiel est effacé et la relance est annoncée par `RETRY_MESSAGE`, qui ne contient pas « réponse interrompue ».
- Les fragments reçus avant la coupure (≈ tokens) s'ajoutent au CO₂ de la réponse. Après deux coupures, le Chat libre les compte dans le total de session.
- L'évaluation affiche `INTERRUPTED_MESSAGE` pour un candidat coupé deux fois, sans le conseil « Vérifiez qu'Ollama est démarré ». Sa latence ne compte que la tentative réussie.

**Fichiers.**
- `src/core/metrics.py`, `src/core/providers/ollama_provider.py` : fragments reçus portés par `InterruptedResponseError`.
- `src/core/inference_service.py` : `retry_interrupted`, `on_retry`, `interrupted_output_tokens`.
- `src/app/states.py` : `RETRY_MESSAGE`.
- `src/app/tabs/inference/chat.py`, `lab.py`, `arena.py` et `src/app/tabs/rag/chat.py`, `eval.py` : effacement, annonce, CO₂ et message.
- Tests : `tests/unit/test_llm_provider.py`, `tests/unit/test_inference_service.py`, `tests/app/test_interrupted_retry.py` (nouveau), `tests/app/test_nothing_lost.py`.
- `_bmad-output/implementation-artifacts/deferred-work.md` : trois entrées retirées, une reformulée et deux ajoutées.

**Revue.** 29 constats :
- 12 corrigés, dont 4 medium répartis en 2 correctifs : durées de l'évaluation, issues de l'évaluation testées ;
- 5 différés, regroupés en 2 entrées ;
- 12 rejetés, dont 2 false.

Revue de suivi recommandée, pour 2 correctifs medium. Risque non vérifié : l'effacement et l'annonce ne se voient pas dans AppTest, et le comportement face à un vrai flux tronqué d'Ollama 0.34.2 reste à confirmer par les deux passages e2e de fin de série.

**Vérification.**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` : 1 046 réussis.
- ruff et black propres.
