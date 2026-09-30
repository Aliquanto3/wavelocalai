---
title: "Une seule règle de CO₂ par réponse, selon l'origine réelle du modèle"
type: 'refactor'
created: '2026-09-29'
status: 'done'
baseline_commit: 'e3cd4f5127a5194aa7ba2b046dbdcc7cc1e927a6'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/AGENTS.md'
warnings: []
deferred:
  - summary: >-
      MetricsService.calculate_carbon (src/core/metrics_service.py) garde sa propre règle de CO₂ (params d'abord, taille devinée d'après le tag, booléen is_local), sans appelant dans les pages.
    evidence: |-
      Exporté par src/app/components/metrics_display.py, qu'aucune page n'appelle ; la garde test_only_the_core_calls_carbon_formulas ne couvre que src/app. À brancher sur answer_carbon_mg ou à supprimer, puis étendre la garde à src/. Antérieur à la story 23.
    location: >-
      src/core/metrics_service.py:111-119
    severity: low
---

<intent-contract>

## Intent

**Problem:**
- **Six copies de la règle de CO₂.** Le CO₂ d'une réponse est recalculé dans six onglets : `chat.py`, `solo.py`, `arena.py`, `lab.py`, `rag/chat.py` et `rag/eval.py`. Ces copies divergent déjà sur quatre points : repli de la taille, gardes sur les tokens, taille inconnue (0 ou « — ») et unité.
- **Formule choisie d'après le catalogue.** Seuls le Chat libre et l'agent seul suivent l'origine du badge. Les quatre autres onglets choisissent la formule d'après le type du catalogue : un tag distant servi par Ollama (`glm-4.6:cloud`) affiche donc un badge Cloud avec un CO₂ local.
- **Badge mémoire toujours à « 0,0 Go ».** Sous les réponses de la Discussion documentaire, le badge mémoire affiche toujours « 0,0 Go », car `InferenceMetrics.model_size_gb` n'est jamais rempli. La colonne « Mémoire » de l'évaluation de la qualité, qui lit ce même champ, a le même défaut.

**Approach:**
- Une fonction de `src/core` calcule le CO₂ d'une réponse, en mg, à partir du tag, du nombre de tokens générés et de l'origine réelle du modèle (celle du badge, `is_cloud`). Les six onglets l'appellent.
- Le badge mémoire affiche la taille chargée du modèle, lue dans `/api/ps` d'Ollama juste après la génération. Sans cette valeur (modèle cloud, Ollama muet, taille nulle), le badge n'est pas affiché : jamais « 0,0 Go ».

## Boundaries & Constraints

**Always:**
- Mêmes chiffres qu'avant dans les cas déjà justes. Les tests actuels des onglets qui fixent un CO₂ restent verts sans changer leurs valeurs : 7,6 mg pour 40 tokens en local, 3,8 mg pour 20 tokens, 1 140 mg pour 6 000 tokens, formule Mistral pour `mistral-large-2512`.
- La formule suit l'origine réelle :
  - `is_cloud` vrai : formule cloud, avec la taille du catalogue (`params_act`, sinon `params_tot`) ;
  - `is_cloud` faux : formule locale ;
  - `is_cloud` inconnu (None) : type du catalogue.
- Un CO₂ inconnu vaut None et s'affiche « — », jamais 0. Il est ignoré dans les totaux et les comparaisons. Une ligne classée dont le CO₂ est inconnu ne fait échouer ni le tableau, ni la taille des bulles, ni le vainqueur, ni la matrice. La matrice de l'évaluation, dont l'axe est le CO₂, la laisse de côté.
- `src/core` n'importe jamais `streamlit`. Tests sans Ollama ni réseau : `/api/ps` est simulé.

**Never:**
- Modifier `src/core/config.py`, `scripts/`, `benchmarks/`, `data/`, `config/models_catalog.json` ou les constantes de `CarbonCalculator`.
- Afficher « 0,0 Go » ou une mémoire estimée.
- Affaiblir ou supprimer une assertion de CO₂ existante. Un test peut seulement être reciblé, quand la fonction qu'il visait change de module.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Local | `qwen2.5:1.5b`, 40 tokens, `is_cloud=False` | 7,6 mg, dans les 6 onglets | N/A |
| Cloud du catalogue | `mistral-large-2512`, 100 tokens, `is_cloud=True` | `compute_mistral_impact_g(123, 100) × 1000` | N/A |
| Tag distant d'Ollama | `glm-4.6:cloud` (hors catalogue), `is_cloud=True` | None : « — », badge Cloud | N/A |
| Tag distant, taille connue | tag cloud du catalogue avec `params_act` | Formule cloud, dans les 6 onglets (plus jamais locale) | N/A |
| Origine inconnue | `is_cloud=None` | Type du catalogue | N/A |
| Tokens invalides | None, bool, NaN, inf, négatif ; tag vide | None | N/A |
| Banc d'essai, deux modèles au même nom | libellé « Nom (tag) » | Fiche trouvée par le tag, pas par le libellé | N/A |
| Mémoire connue | `/api/ps` liste le tag, `size` = 2,5 Gio | Badge « 2,5 Go » ; colonne « Mémoire » de l'évaluation à 2,5 | N/A |
| Mémoire inconnue | modèle cloud, `ps()` en échec, tag absent, `size` ≤ 0, ancien historique à 0.0 | Pas de badge ; « — » dans la colonne | Aucune erreur affichée |

</intent-contract>

## Code Map

- `src/core/green_monitor.py:55-111` `CarbonCalculator` (formules en grammes). À réutiliser, jamais à modifier. Le benchmark n'importe que `src/core/config.py`.
- `src/core/utils.py:11-46` `extract_params_billions`. `src/core/models_db.py` : `get_model_info(friendly_name)` et `get_friendly_name_from_tag(tag)`, la clé de fiche commune à 5 onglets sur 6.
- Nouvelle fonction, par exemple `answer_carbon_mg(model_tag, output_tokens, is_cloud=None) -> float | None` dans un module `src/core` (par exemple `src/core/answer_carbon.py`). Elle reprend la version la plus défensive, `solo.py:137-161` (gardes, None si la taille cloud est inconnue).
- Appelants :
  - `src/app/tabs/inference/chat.py:30-62` `_calculate_metrics(metrics, model_tag, is_cloud)` : garder son nom et ses paramètres, qui sont vérifiés par AST dans `test_chat_passes_tag_and_origin_to_carbon`, et déléguer. Session : `or 0.0` déjà tolérant.
  - `src/app/tabs/agent/solo.py:137-161,630-636` : `answer_carbon_mg` local à remplacer par la fonction du cœur. `test_agent_carbon_failure_keeps_answer` patche `solo.get_model_info` : le recibler sur le module du cœur.
  - `src/app/tabs/inference/arena.py:631-648` : `is_cloud` de la ligne (l.595) ; la valeur reste arrondie à 2 décimales (l.684). Autres usages à rendre sûrs quand la valeur est None :
    - taille des bulles (~l.269) ;
    - légende de taille (l.432) ;
    - vainqueur (l.408-410, déjà gardé par `_num`).
  - `src/app/tabs/inference/lab.py:70-100` `_render_metrics(res, model_name)` : la fiche est cherchée par libellé et le résultat est en grammes. Passer le tag et l'origine : `lab_last_tag` et `lab_last_is_cloud`, déjà en `session_state` (l.201-204).
  - `src/app/tabs/rag/chat.py:241-265` : `selected_is_cloud` (l.66). Pas de métriques : None.
  - `src/app/tabs/rag/eval.py:339-359` : `c_is_cloud` (l.318). `CO2_mg` sert à la matrice (l.111, `co2_in_unit` → None) et au podium ; les lignes sans CO₂ sont exclues de la matrice.
- Mémoire :
  - `src/core/providers/ollama_provider.py:210-263` : `is_model_loaded` et `loaded_models_ram_gb` lisent déjà `ps()` (normalisation `_normalize_tag`, l.266). Ajouter une lecture par modèle, par exemple `loaded_model_size_gb(model_name) -> float | None` : `size` / 1024³ du modèle, None si absent, en échec, ou si `size` ≤ 0.
  - `src/core/llm_provider.py:167-203` : ajouter l'enveloppe sur le modèle de `is_model_loaded`, qui renvoie None pour un fournisseur autre qu'Ollama.
  - `rag/chat.py:249` et `:118-119` : `ram_gb` rempli par cette lecture ; badge seulement si la valeur est > 0. Ancien historique à 0.0 : badge masqué.
  - `rag/eval.py:~344,386,502` : `RAM_GB` rempli de même ; « — » dans la colonne s'il est inconnu.
- Tests à garder verts sans toucher leurs chiffres :
  - `tests/app/test_nothing_lost.py` (l.96-205) ;
  - `tests/app/test_figures.py` : lab 7,6 mg ; footer du chat ; session 15,2 mg ; Arène [7.6, 1140] et matrice ; Discussion 3,8 mg ; évaluation mg/g ; matrice à une ligne ;
  - `tests/app/test_states.py` (~l.950-987) ;
  - `tests/app/test_sovereignty.py`.

## Tasks & Acceptance

**Execution:**
- [x] module `src/core` de la règle de CO₂ et ses tests unitaires (`tests/unit/`) -- une seule règle, toute la matrice sans onglet
- [x] `src/app/tabs/inference/chat.py`, `src/app/tabs/agent/solo.py`, `src/app/tabs/inference/arena.py`, `src/app/tabs/inference/lab.py`, `src/app/tabs/rag/chat.py`, `src/app/tabs/rag/eval.py` -- appel de la fonction du cœur avec l'origine du badge ; CO₂ inconnu toléré partout -- copies supprimées
- [x] `src/core/providers/ollama_provider.py`, `src/core/llm_provider.py` -- taille chargée d'un modèle lue dans `/api/ps` -- mémoire réelle
- [x] `src/app/tabs/rag/chat.py`, `src/app/tabs/rag/eval.py` -- badge et colonne « Mémoire » d'après cette lecture, masqués ou « — » sinon -- plus de « 0,0 Go »
- [x] `tests/app/` -- par onglet : un tag distant d'Ollama avec badge Cloud n'a plus de CO₂ local ; Banc d'essai trouvé par le tag ; badge mémoire présent (ps simulé) et absent (cloud, ps en échec) -- non-régression
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les deux entrées de la story 12 sur la règle de CO₂ -- traçabilité

**Acceptance Criteria:**
- Given un modèle local de 40 tokens, when il répond dans chacun des 6 onglets, then chaque onglet affiche 7,6 mgCO₂, comme avant.
- Given un tag distant d'Ollama hors catalogue, badge Cloud, when il répond dans l'Arène, le Banc d'essai, la Discussion ou l'évaluation de la qualité, then son CO₂ s'affiche « — » et aucun total ni classement n'échoue.
- Given `/api/ps` simulé qui donne 2,5 Gio pour le modèle de la Discussion, when une réponse s'affiche, then sa légende contient « 2,5 Go » ; sans cette donnée, elle ne contient aucun « Go ».

## Spec Change Log

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 30 findings — high 0, medium 3, low 26, false 1, maybe-false 0
- findings:
  - `[medium]` `[patch]` (verification-gap) garde mémoire des modèles cloud jamais exercée (`ps` ne listait pas le tag distant) — `ps` simulé liste le tag distant, tags interrogés relevés ; retirer une garde fait échouer les tests.
  - `[low]` `[patch]` (verification-gap) matrice de l'évaluation disparue sans message quand aucun CO₂ n'est connu — légende affichée même sans matrice ; test.
  - `[low]` `[defer]` (intent) `MetricsService.calculate_carbon`, seconde règle du cœur — sans appelant dans les pages, hors des six copies nommées ; différé.
  - `[low]` `[reject]` (intent) tag distant avec taille du catalogue testé seulement au cœur — aucun tag distant dans le catalogue versionné ; les onglets transmettent seulement `is_cloud`, testé par onglet.
  - `[false]` `[reject]` (intent) tests du Chat libre et de l'agent sans défaut à corriger — ce sont des tests de non-régression voulus, pas un défaut.
  - `[low]` `[patch]` (intent) total de session qui ignore sans le dire un CO₂ inconnu — groupé avec la ligne blind du total de session.
  - `[low]` `[patch]` (intent) commentaire périmé de `model_size_gb` — corrigé.
  - `[low]` `[reject]` (intent) colonne « Mémoire », exclusion de la matrice, Banc d'essai par tag au-delà de l'intention littérale — choix de la spec pour la même cause, pas un défaut.
  - `[low]` `[patch]` (edge) matrice vide sans légende — même correctif que la ligne verification-gap.
  - `[low]` `[patch]` (edge) exception du catalogue qui fait perdre la réponse de la Discussion — la fonction du cœur rattrape l'échec et renvoie None ; test.
  - `[low]` `[patch]` (edge) `_is_mistral_api_model` hors du try de `loaded_model_size_gb` — corps entier sous try ; test.
  - `[low]` `[patch]` (edge) `is_cloud` None pour un tag distant : `ps` lu dans la Discussion — le cœur renvoie None si `is_cloud_tag` est vrai.
  - `[low]` `[patch]` (edge) même cas dans l'évaluation — même correctif.
  - `[low]` `[patch]` (edge) cloud à 0 token et taille inconnue : « — » au lieu de 0 — 0 token donne 0,0 avant la recherche de taille ; test.
  - `[low]` `[reject]` (edge) nom non textuel dans `ps` — Ollama renvoie toujours des chaînes ; garde pour un cas non rencontré.
  - `[low]` `[patch]` (edge) `lab_last_model` écrit mais plus lu — écriture et variable inutilisée retirées (aucun autre lecteur).
  - `[low]` `[reject]` (edge) « — » promis dans les colonnes, cellule vide rendue — convention existante des colonnes numériques (CO₂, échecs) : cellule vide, jamais 0 ; un texte casserait le tri.
  - `[low]` `[defer]` (blind) septième copie dans `metrics_service` — même entrée différée que la ligne d'intention.
  - `[medium]` `[patch]` (blind) total de session à « 0 mgCO₂ » quand aucun CO₂ n'est connu — `session_co2_mg` renvoie None, « Session : — » ; test.
  - `[medium]` `[patch]` (blind) bulle minimale de l'Arène lue comme « le plus sobre » pour un CO₂ inconnu — modèles nommés dans la légende (« CO₂ inconnu, taille minimale : … ») ; test.
  - `[low]` `[patch]` (blind) matrice de l'évaluation disparue — même correctif que la ligne verification-gap.
  - `[low]` `[patch]` (blind) tolérance aux erreurs inégale entre onglets — même correctif que la ligne edge (échec du catalogue rattrapé dans le cœur).
  - `[low]` `[patch]` (blind) `loaded_model_size_gb` ne filtre pas les tags distants malgré sa docstring — même correctif que la ligne edge.
  - `[low]` `[reject]` (blind) lecture de `ps` en trois copies — refonte sans défaut observé.
  - `[low]` `[patch]` (blind) `lab_last_model` inutile — même correctif que la ligne edge.
  - `[low]` `[reject]` (blind) entiers numpy rejetés, décimales tronquées — les fournisseurs renvoient des `int` Python ; aucun appelant ne passe numpy.
  - `[low]` `[patch]` (blind) badge mémoire de l'historique qui accepte `True` et `inf` — `_known_memory` : nombre fini, non booléen, > 0.
  - `[low]` `[reject]` (blind) `MG_PER_G` défini deux fois — le cœur ne peut pas importer l'app ; unifier toucherait `formatting` sans défaut.
  - `[low]` `[reject]` (blind) « Mémoire » sans « — » — même raison que la ligne edge des colonnes.
  - `[low]` `[reject]` (blind) critères non testés par onglet (tag distant à taille connue, 40 tokens dans la Discussion et l'évaluation) — même fonction du cœur, testée pour tous les cas ; 3,8 mg à 20 tokens vérifiés dans ces onglets.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus d'AGENTS.md s'ils se produisent
- `git grep -n "compute_local_theoretical_g\|compute_mistral_impact_g" src/app` -- expected: aucune ligne (seul le module du cœur appelle `CarbonCalculator`)
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres

## Auto Run Result

Status: done

**Résumé.** `src/core/answer_carbon.py::answer_carbon_mg(model_tag, output_tokens, is_cloud)` est désormais la seule règle de CO₂ par réponse. Les six onglets l'appellent avec l'origine de leur badge.
- Un tag distant d'Ollama hors catalogue affiche « — », jamais un CO₂ local. Il est ignoré par les totaux et les classements.
- Le Banc d'essai trouve la fiche du modèle par son tag.
- Le badge mémoire de la Discussion et la colonne « Mémoire » de l'évaluation lisent la taille chargée dans `ollama ps`. Ils sont masqués quand elle est inconnue : jamais « 0,0 Go ».

**Fichiers.**
- `src/core/answer_carbon.py` (nouveau) : la règle.
- `src/core/providers/ollama_provider.py`, `src/core/llm_provider.py` : `loaded_model_size_gb`.
- `src/core/metrics.py` : commentaire de `model_size_gb`.
- Onglets `chat.py`, `solo.py`, `arena.py`, `lab.py`, `rag/chat.py`, `rag/eval.py` : copies supprimées ; « — » dans le total de session ; légende de l'Arène ; légende de la matrice de l'évaluation.
- Tests : `tests/unit/test_answer_carbon.py`, `tests/app/test_answer_carbon.py`, `tests/unit/test_failure_states.py`, `tests/app/conftest.py`, `tests/app/test_nothing_lost.py` (recibles vers le module du cœur, chiffres inchangés).
- `_bmad-output/implementation-artifacts/deferred-work.md` : deux entrées de la story 12 retirées, une ajoutée.

**Revue.** 30 constats :
- 18 lignes corrigées, dont 3 medium : garde mémoire des modèles cloud testée, total de session à « — », légende de l'Arène ;
- 2 différées (même entrée : `MetricsService`) ;
- 10 rejetées, dont 1 false.

Revue de suivi recommandée : 3 medium corrigés. Le risque non vérifié concerne le « Session : — » du Chat libre et la légende « CO₂ inconnu, taille minimale » de l'Arène, vérifiés seulement par AppTest, jamais dans un navigateur avec un vrai tag distant.

**Vérification.**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` : 1 020 réussis.
- `git grep` des formules dans `src/app` : aucune ligne.
- ruff et black propres.

**Risques résiduels.**
- `size` de `ps` compte la mémoire vive et la mémoire vidéo : le badge montre l'empreinte chargée.
- Un appel `ps` de 2 s au plus suit chaque réponse d'un modèle local dans la Discussion et l'évaluation.
