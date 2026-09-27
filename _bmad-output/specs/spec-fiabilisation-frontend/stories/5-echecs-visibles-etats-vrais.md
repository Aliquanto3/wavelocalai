---
title: 'Échecs visibles et états vrais'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '8b079424f3179cf608a77917d3efe6f2ede53625'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      « Libérer la mémoire » ne décharge pas les modèles d'Ollama, alors que le garde-fou le propose.
    evidence: |-
      ResourceManager.free_ollama_memory lit ps() et appelle gc.collect() sans décharger.
    location: >-
      src/core/resource_manager.py:83
    severity: medium
  - summary: >-
      Pas d'indicateur de premier chargement dans l'évaluation de la qualité ni dans l'équipe d'agents.
    evidence: |-
      Sites non listés par la story ; EXPERIENCE.md dit « toute inférence ».
    severity: low
  - summary: >-
      État « Fournisseur cloud injoignable » d'EXPERIENCE.md incomplet (pas de bascule vers Local proposée en action).
    evidence: |-
      Le conseil nomme le fournisseur et suggère Local en texte seulement.
    severity: low (unverified)
  - summary: >-
      Premier import de crewai lent : la page Agents autonomes a dépassé 30 s à froid.
    evidence: |-
      Mesuré au navigateur (Playwright) ; 8 s une fois le module chargé.
    location: >-
      src/app/views/04_Agent_Lab.py
    severity: medium (unverified)
---

<intent-contract>

## Intent

**Problem:** Les échecs se présentent comme des succès ou des traces : aucun appelant ne teste `result.error` (le Banc d'essai plante en boucle, l'Arène affiche `'NoneType' … 'output_tokens'`, le chat ajoute une réponse vide), une évaluation impossible devient 0/100 (Ragas absent, juge en échec), l'accueil affiche « Disponible » en dur et l'accélérateur « Actif » même sans GPU, une question bloquée par le garde-fou mémoire disparaît, le premier chargement d'un modèle (8 à 26 s) n'a aucun retour, et les sélecteurs plantent quand aucun modèle n'est installé (F2, F3, F11, F17, U11, U20).

**Approach:** Tester l'erreur avant les métriques partout et afficher les états d'EXPERIENCE.md (délai dépassé, non évalué, service indisponible, blocage mémoire, chargement, aucun modèle) ; porter « non évalué » dans `EvalResult` ; brancher « Système » sur l'état réel d'Ollama et l'accélérateur sur une détection réelle.

## Boundaries & Constraints

**Always:** textes et états d'EXPERIENCE.md (State Patterns, Chiffres « Scores », Voice and Tone) ; `alert-error` = ce qui a échoué + quoi faire, trace technique dans un `st.expander` replié « Détails techniques » ; « non évalué » jamais converti en 0 ; l'état « Système » ne sollicite qu'Ollama, en local, avec un délai court (aucun appel à un fournisseur cloud) ; les tests simulent Ollama (aucun réseau).

**Never:** changer le calcul du débit ou du CO₂ (story 6) ; conserver la réponse finale de l'agent ou le modèle choisi (story 9) ; changer le nombre minimal de modèles de l'Arène ou les défauts (story 7) ; toucher `src/core/config.py` ou le benchmark ; affaiblir un test : un test qui fige « 0/100 pour un échec » est corrigé sur la cible (« non évalué »), pas supprimé.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Délai dépassé, chat | `InferenceResult(error="Timeout…", metrics=None)` | `alert-error` « Délai dépassé (N s) » ; aucune réponse vide ajoutée | détail dans « Détails techniques » |
| Délai dépassé, Banc d'essai | idem | `alert-error`, pas d'exception, pas de plantage au rerun suivant | — |
| Arène, un modèle en échec | 3 modèles, le 2ᵉ en délai dépassé | Sa ligne affiche « Délai dépassé » ; les 2 autres sont classés | statut final `error` seulement si tous échouent |
| Arène, tous en échec | 2 modèles en échec | Aucun podium ; message d'erreur | — |
| Juge en échec | réponse du juge vide ou erreur | Note « non évalué », jamais 0/100 ; classée après les notes | raison en aide |
| Ragas absent ou en échec | `RAGAS_AVAILABLE=False`, exception, NaN | `EvalResult` « non évalué » avec raison ; podium et tableau sans 0/100 | — |
| Ollama arrêté | health check en échec | Accueil : Système « Indisponible » ; `alert-error` en tête de module « Ollama ne répond pas. Démarrez-le, puis rechargez la page. » | délai court, pas de blocage |
| Ollama joignable | health check OK | « Disponible » | — |
| Accélérateur | NVML sans GPU, pas d'Apple Silicon | « Aucun » (jamais « Actif ») | détection en échec = « Aucun » |
| Accélérateur présent | NVML détecte un GPU | Nom du GPU | — |
| Garde-fou mémoire | question posée, mémoire insuffisante | Question visible dans l'historique ; `alert-warning` : mémoire nécessaire, mémoire libre, deux issues (modèle plus petit, libérer la mémoire) | — |
| Premier chargement | modèle absent de `ollama.ps()` | « Chargement du modèle en mémoire… » affiché avant la génération | `ps()` en échec = pas d'indicateur, pas d'erreur |
| Aucun modèle | `list_models` vide | `alert-info` qui mène à « Gestion des modèles » ; aucune exception (agent seul, équipe, chat, RAG) | — |

</intent-contract>

## Code Map

- `src/core/inference_service.py:25-34,97-119` -- `InferenceResult(error, metrics=None)` ; délai : `error = f"Timeout ({timeout}s) dépassé pour {model_tag}"`. Exposer un moyen fiable de savoir qu'il s'agit d'un délai (champ ou constante) plutôt que d'analyser le texte.
- `src/app/tabs/inference/chat.py:141-176` -- ni test d'erreur ni `on_error` ; ajoute une réponse vide et `st.rerun()`.
- `src/app/tabs/inference/lab.py:108-165` -- `lab_last_result` en session puis `res.metrics.output_tokens` → `AttributeError` à chaque rerun.
- `src/app/tabs/inference/arena.py:195-262` -- `m = result.metrics` puis `m.output_tokens` ; `except` générique affiche l'`AttributeError` ; modèle en échec retiré ; statut toujours « complete » ; rien si tout échoue ; juge : `score = 0` par défaut (l.222), `eval_res.error` ignoré, `re.search(r"\d+")` prend le premier entier ; tri `sort_values(["Note","Débit…"])` (l.27), podium `f"{winner['Note']}/100"` (l.43).
- `src/core/llm_provider.py:106-109` -- `chat_stream` renvoie « Erreur : {e} » comme du texte normal (affiché comme réponse par `src/app/tabs/rag/chat.py` et capturé par `eval.py`) : lever l'erreur et laisser les appelants l'afficher (`rag/chat.py:215` a déjà un `except` → `st.error`).
- `src/core/eval_engine.py:20-26,50-51,94-115` -- `EvalResult(answer_relevancy, faithfulness, global_score)` sans état ; 0.0 pour Ragas absent, exception, NaN ou colonne manquante. Non importé par le benchmark.
- `src/app/tabs/rag/eval.py:58-63,189,215-301` -- podium, graphique et tableau ; `_format_ratio` rend « — » pour None/NaN.
- `tests/unit/test_eval_engine.py:89` -- `test_evaluate_handles_ragas_exception` asserte `global_score == 0.0` : à corriger sur la cible « non évalué ».
- `src/app/home.py:57-59` -- `st.metric("Système", "Disponible")` en dur.
- `src/core/providers/ollama_provider.py:174-180` -- `health_check` = `ollama.list()` via le client par défaut sans délai et avec l'hôte `OLLAMA_HOST`, alors que le chat utilise `self._base_url`. `src/core/providers/provider_factory.py:154-161` -- `health_check_all` appelle aussi les fournisseurs cloud (Anthropic envoie un vrai message) : ne pas l'utiliser pour l'accueil.
- `src/app/views/01_Socle_Hardware.py:38-55,117-123` -- détection par `torch.cuda` / `mps`, valeur « Actif » en dur. `nvidia-ml-py` (module `pynvml`) est installé en dépendance de codecarbon et figé dans `constraints.txt` : le déclarer dans `requirements.txt` s'il est importé directement. `ollama.ps()` renvoie `size_vram` par modèle chargé.
- `src/core/green_monitor.py:154-182` -- `HardwareMonitor` (GPUtil) : réutilisable.
- `src/core/resource_manager.py:118-175` -- `check_resources` → `ResourceCheckResult(allowed, message, ram_required_gb, ram_available_gb)`.
- `src/app/tabs/agent/solo.py:212-231` -- `use_prompt` supprimé, contrôle mémoire avant l'ajout à l'historique → question perdue ; `:97-98` `display_to_tag[None]` → `KeyError` sans modèle.
- `src/app/tabs/agent/crew.py:313-319` -- `display_to_tag[new_lbl]` → `KeyError` sans modèle.
- Sites d'inférence sans indicateur de chargement : `chat.py:141`, `lab.py:108`, `arena.py:197`, `rag/chat.py:111,143`, `solo.py:237`.
- `src/app/Accueil.py` (routeur) -- endroit unique pour l'alerte « service indisponible » en tête de module.
- `tests/app/conftest.py` -- `health_check` simulé ; ajouter des fixtures « aucun modèle », « Ollama arrêté », « inférence en échec ».

## Tasks & Acceptance

**Execution:**
- `src/core/inference_service.py`, `src/core/llm_provider.py` -- délai identifiable ; `chat_stream` lève au lieu de renvoyer un texte d'erreur.
- `src/core/eval_engine.py` -- `EvalResult` porte « non évalué » (scores `None` + raison) pour Ragas absent, exception, NaN, colonne manquante.
- `src/core/providers/ollama_provider.py` (ou module dédié) -- état d'Ollama avec délai court (≈2 s) sur l'hôte réellement utilisé ; présence d'un modèle en mémoire (`ps()`), sans exception.
- Détection d'accélérateur (NVML, puis Apple Silicon, sinon « Aucun ») dans `src/core/` ; `requirements.txt` si nécessaire.
- `src/app/home.py`, `src/app/Accueil.py`, `src/app/views/01_Socle_Hardware.py` -- Système réel, alerte en tête de module, accélérateur réel.
- `src/app/tabs/inference/{chat,lab,arena}.py`, `src/app/tabs/rag/{chat,eval}.py`, `src/app/tabs/agent/{solo,crew}.py` -- erreur avant métriques, délai dépassé, non évalué, chargement, aucun modèle, question conservée au blocage mémoire.
- `tests/unit/` et `tests/app/` -- une ou plusieurs vérifications par ligne de la matrice, avec Ollama, inférence et Ragas simulés.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given l'app lancée avec des providers simulés dont Ollama arrêté, when on ouvre l'accueil puis un module au navigateur, then « Indisponible » et l'alerte s'affichent, sans exception ni requête hors localhost.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 50 findings — high 0, medium 9, low 27, false 5, maybe-false 9
- findings:
  - `[low]` `[patch]` (blind, edge) fournisseurs cloud qui renvoient « Erreur : » comme token — `ValueError` levée.
  - `[medium]` `[patch]` (blind) Ollama arrêté : alerte « aucun modèle » fausse en plus de l'alerte d'indisponibilité — masquée quand Ollama est indisponible.
  - `[medium]` `[patch]` (blind) santé et liste des modèles sur des hôtes différents — `base_url` pour tous les appels.
  - `[low]` `[patch]` (blind, edge) état « indisponible » gardé 10 s en cache — seul « disponible » est mis en cache.
  - `[low]` `[patch]` (blind, edge) indicateur de chargement trop tardif dans la Discussion (HyDE, Self-RAG), libellé en double — contrôle avant la recherche.
  - `[low]` `[defer]` (blind, intent) pas d'indicateur de chargement dans l'évaluation de la qualité ni l'équipe d'agents — sites non listés par la story.
  - `[low]` `[patch]` (blind) détail d'erreur du juge perdu — replié dans « Détails techniques ».
  - `[low]` `[patch]` (blind) exception brute de Ragas dans la colonne « Statut » — raison courte, détail replié.
  - `[low]` `[patch]` (blind, intent) conseil d'erreur qui cite Ollama pour un modèle cloud — conseil selon le fournisseur.
  - `[medium]` `[defer]` (blind) « Libérer la mémoire » ne décharge pas les modèles d'Ollama — préexistant (`free_ollama_memory` ne fait que `gc`) ; le message du garde-fou propose aussi un modèle plus petit.
  - `[medium]` `[patch]` (blind, edge) question bloquée renvoyée au moteur comme tour orphelin — marquée `blocked`, exclue de l'historique envoyé.
  - `[medium]` `[patch]` (blind, edge) `parse_judge_score` retient un nombre isolé (« enfant de 10 ans ») et « -5 » — note explicite ou réponse réduite au nombre ; négatifs rejetés.
  - `[low]` `[patch]` (blind, edge) accélérateur : aide « les modèles tournent sur le processeur » fausse sur AMD ou Intel ; un seul GPU affiché — formulation neutre, tous les GPU NVIDIA.
  - `[low]` `[patch]` (blind, intent) `suppress(Exception)` autour du lien, lien libellé « Gestion des modèles » qui ouvre « Chat libre » — exception ciblée, lien libellé d'après sa page.
  - `[medium]` `[patch]` (blind, verification-gap) indicateur de chargement testé seulement au Banc d'essai — tests Chat libre, Agent seul, Discussion et échec.
  - `[low]` `[patch]` (blind) `LOADING_HINT` promet « de 8 à 26 s » — formulation sans chiffre ; le conseil de délai mentionne le chargement.
  - `[medium]` `[patch]` (verification-gap) « Libérer la mémoire » ne vide plus la conversation, non testé — test ajouté.
  - `[medium]` `[patch]` (verification-gap) évaluation RAG mixte (notée / non évaluée) jamais exécutée — test ajouté.
  - `[medium]` `[patch]` (verification-gap) évaluation RAG avec échec de génération non testée — test ajouté.
  - `[low]` `[patch]` (verification-gap) échec non lié au délai jamais exercé dans l'interface — test ajouté.
  - `[maybe-false]` `[reject]` (intent) « Système » par une sonde Ollama et non `health_check()` — choix de la story : `health_check_all` appelle les fournisseurs cloud (Anthropic envoie un message payant).
  - `[maybe-false]` `[reject]` (intent) aucun test avec Ollama réellement arrêté — vérifié au navigateur avec la vraie sonde : accueil « Indisponible », alerte sur les 4 modules, aucune exception, aucune requête externe.
  - `[low]` `[reject]` (intent) alerte absente de l'accueil — l'accueil porte la métrique « Indisponible » (note de conception).
  - `[maybe-false]` `[reject]` (intent) délai testé par une simulation — `timed_out` produit par `InferenceService` vérifié en unitaire.
  - `[low]` `[patch]` (intent, edge) exceptions de l'agent seul et de l'équipe en texte brut — `render_error` avec détails.
  - `[maybe-false]` `[defer]` (intent) état « Fournisseur cloud injoignable » d'EXPERIENCE.md — conseil par fournisseur ajouté ; bascule proposée vers Local seulement en texte ; story 8 pour le mode.
  - `[maybe-false]` `[reject]` (intent) stratégies RAG non testées face au nouveau `chat_stream` qui lève — exceptions attrapées par la Discussion (testé).
  - `[low]` `[reject]` (intent) politique stricte de `parse_judge_score` au-delà de l'intention — note de conception de la story ; « non évalué » plutôt qu'une note inventée.
  - `[low]` `[reject]` (intent) voie `size_vram` d'Ollama non utilisée — NVML suffit pour NVIDIA ; noté pour le matin.
  - `[false]` `[reject]` (intent) libellé « Actif » autorisé par EXPERIENCE.md — le nom du GPU est plus informatif.
  - `[maybe-false]` `[reject]` (intent) vrai message du garde-fou non vérifié par l'AppTest — vérifié par `test_resource_manager.py`.
  - `[false]` `[reject]` (intent) règle du benchmark — aucun module importé par le benchmark n'est touché.
  - `[low]` `[patch]` (edge) NaN de Débit/CO₂ sur une ligne notée sans métriques — traité comme absent.
  - `[low]` `[reject]` (edge) « 7 sur 100 000 » — improbable pour un juge.
  - `[low]` `[reject]` (edge) tag sans version venant d'un registre avec port — improbable.
  - `[low]` `[reject]` (edge) Python x86_64 sous Rosetta — cas marginal.
  - `[low]` `[patch]` (edge) erreur de recherche présentée comme un problème d'Ollama — message propre.
  - `[low]` `[patch]` (edge) statut de l'agent bloqué sur « Chargement… » sans événement final — clos après la boucle.
  - `[low]` `[patch]` (edge) statut « Chargement… » ouvert pendant la génération du Banc d'essai — fermé au premier token.
  - `[low]` `[patch]` (edge) erreur du chat perdue au rerun — tour en échec conservé et rendu en erreur.
  - `[false]` `[reject]` (edge) fournisseurs cloud non enregistrés — doublon du premier correctif.
  - `[maybe-false]` `[reject]` (intent) « vide » lu comme « aucun modèle » — base vide et historique vide existaient déjà.
  - `[low]` `[reject]` (verification-gap) non-timeout : doublon.
  - `[maybe-false]` `[reject]` (intent) un appel `ps()` en direct par inférence locale (≤ 2 s) — coût accepté pour l'indicateur.
  - `[false]` `[reject]` (blind) tests d'orchestrateur — doublon.
  - `[low]` `[reject]` (blind) plusieurs GPU : doublon.
  - `[false]` `[reject]` (edge) conseil de délai : doublon.
  - `[low]` `[reject]` (intent) `nvidia-ml-py` déclaré, commentaire « via » modifié à la main dans constraints.txt — commentaire seul, versions inchangées ; `test_constraints_cover_requirements` vert.
  - `[maybe-false]` `[defer]` (orchestrateur) premier import de crewai lent : la page Agents autonomes a dépassé 30 s à froid au navigateur (8 s une fois chargée) — préexistant.

## Design Notes

Juge de l'Arène : ne retenir une note que si la réponse contient un entier de 0 à 100 clairement identifiable ; sinon « non évalué ». Dans le classement, les notes numériques d'abord (décroissant, puis débit), les « non évalué » ensuite, les échecs sans ligne de podium.

Alerte « service indisponible » : la placer dans le routeur avant `pg.run()` pour les pages de module, pas sur l'accueil (qui a déjà la métrique). La mettre en cache quelques secondes (`st.cache_data(ttl=…)`) pour ne pas interroger Ollama à chaque interaction.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `grep -n '"Disponible"\|"Actif"' src/app/home.py src/app/views/01_Socle_Hardware.py` -- expected: aucune valeur écrite en dur hors branche calculée

**Manual checks (if no CLI):**
- Navigateur avec le lanceur `/tmp/nuit/axe/launch_fake.py` modifié pour simuler Ollama arrêté : accueil « Indisponible », alerte en tête de module.

## Auto Run Result

Status: done

**Résumé :** les échecs sont visibles et les états vrais : erreur testée avant les métriques (chat, Banc d'essai, Arène, Discussion, agents), « Délai dépassé » identifiable (`InferenceResult.timed_out`), Arène qui continue sans le modèle en échec et classe notés / non évalués / échecs, « non évalué » porté par `EvalResult` (plus jamais 0/100), « Système » branché sur une sonde Ollama locale (2 s, sans fournisseur cloud), alerte en tête de module, accélérateur détecté par NVML ou Apple Silicon, question conservée et besoin expliqué au blocage mémoire, indicateur « Chargement du modèle en mémoire… », état « aucun modèle » sans exception.

**Fichiers :** `src/core/{inference_service,llm_provider,eval_engine,accelerator}.py`, `src/core/providers/*.py` ; `src/app/states.py` (nouveau), `src/app/{Accueil,home}.py`, `src/app/views/{01_Socle_Hardware,04_Agent_Lab}.py`, `src/app/tabs/**` ; `requirements.txt` (`nvidia-ml-py`) ; tests `tests/app/test_states.py`, `tests/unit/test_failure_states.py`, `tests/unit/test_eval_engine.py` (0/100 → « non évalué »), `tests/unit/test_llm_provider.py`, `tests/unit/test_inference_service.py`.

**Revue :** 31 correctifs (8 medium, 23 low), 4 différés, 15 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les medium sont couverts par des tests ajoutés.

**Vérification :** `pytest tests/unit tests/app` : 439 réussis ; navigateur avec la vraie sonde et Ollama arrêté : accueil « Indisponible », alerte « Ollama ne répond pas… » sur les modules, accélérateur « Aucun GPU NVIDIA ni Apple détecté », aucune exception, aucune requête hors localhost.

**Risques :** « Libérer la mémoire » ne décharge pas Ollama ; premier import de crewai lent ; délais réels à vérifier avec Ollama au matin.
