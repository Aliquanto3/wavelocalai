---
title: 'Choix d’après le benchmark du poste : modèle le plus rapide et outils vérifiés'
type: 'bugfix'
created: '2026-09-29'
status: 'done'
baseline_commit: '9e3e88c8d37a23fa176846245288a639ff486237'
baseline_revision: '9e3e88c8d37a23fa176846245288a639ff486237'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/15-juge-modele-defaut-benchmark-poste.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/18-constats-recette-arene-agents.md'
warnings: []
deferred: []
---

<intent-contract>

## Intent

**Problem:** Deux choix de l'app lisent encore des chiffres qui peuvent venir d'une autre machine :
- **Le plus rapide.** Le premier modèle proposé et la présélection de l'Arène se trient sur `benchmark_stats.avg_tokens_per_second` de `data/models.json`. Le benchmark de ce poste est déjà chargé, mais il ne sert qu'au juge et au modèle des agents.
- **Outils vérifiés.** Sur la page Agents, la mention « outils vérifiés » vient de la capacité `tools` du catalogue, même quand le benchmark de ce poste mesure un taux de réussite des outils de 0 (Gemma 3 1B, OLMo 3 7B).

**Approach:**
- **Débit.** Le rang de débit des locaux qui tiennent en mémoire prend le débit prudent du benchmark de ce poste (`BenchScore.speed_tps`) quand ce benchmark mesure tous ces locaux. Sinon, la règle actuelle s'applique : `data/models.json` s'il a un débit pour chacun, sinon la plus petite empreinte.
- **Outils.** Un modèle est « outils vérifiés » d'après le `tool_success` du benchmark de ce poste quand il existe pour ce modèle (≥ `AGENT_MIN_TOOL_SUCCESS`), et d'après le catalogue sinon.
- **Poste non benchmarké :** comportement actuel inchangé.

## Boundaries & Constraints

**Always:**
- La règle reste dans `src/core/model_defaults.py`, sans `streamlit`. Un seul appel à `machine_benchmark()` par construction de menu.
- Même principe que la story 7 : un débit connu ne passe jamais devant un débit inconnu, et deux sources ne se mêlent jamais dans une même comparaison.
- Le reste de la clé de tri garde son ordre (cloud, dédié au raisonnement, ne tient pas).
- Tests sans réseau, avec un benchmark simulé.

**Never:**
- Modifier `scripts/`, `benchmarks/`, `data/`, `config/models_catalog.json` ou `src/core/config.py`.
- Changer le juge par défaut, `agent_default` ou leurs seuils.
- Retirer un modèle d'une liste.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Benchmark complet | Tous les locaux qui tiennent sont mesurés ; data/models.json dit l'inverse | Premier proposé et présélection de l'Arène triés sur le débit du benchmark | N/A |
| Benchmark partiel | Un local qui tient n'est pas mesuré | Règle actuelle (data/models.json si complet, sinon empreinte) | N/A |
| Poste inconnu | Benchmark vide | Ordre actuel | N/A |
| Local qui ne tient pas, non mesuré | Hors benchmark, trop gros | N'empêche pas l'usage du benchmark ; reste après ceux qui tiennent | N/A |
| Outils mesurés à 0 | Catalogue `tools`, `tool_success` = 0 | Pas de mention « outils vérifiés » | N/A |
| Outils mesurés ≥ 0,75 | Catalogue sans `tools` | Mention « outils vérifiés » | N/A |
| Outils non mesurés | Modèle absent du benchmark, ou `tool_success` None | Mention d'après le catalogue | N/A |

</intent-contract>

## Code Map

- `src/core/model_defaults.py`
  - l.374 `_speed_known_for_all_fitting` et l.379 `sort_key` : le rang de débit lit `ModelChoice.speed_tps` (l.147).
  - l.397 `rank_models` : ajouter `benchmark: Mapping[str, BenchScore] | None = None`. Quand le benchmark couvre tous les locaux qui tiennent (tag de base, `base_tag`), chaque local reçoit son débit du benchmark (`dataclasses.replace`, None s'il n'est pas mesuré), et `use_speed` est vrai. Sinon, rien ne change.
  - Nouvelle fonction pure `tools_verified(tag, capabilities, benchmark) -> bool`.
  - Mettre à jour la docstring du module (l.9-18) et celle de `speed_tps`.
- `src/core/benchmark_results.py:43` `BenchScore` (`speed_tps`, `tool_success`) : lecture seule, rien à changer.
- `src/app/ui.py:210` `model_menu` : lire `machine_benchmark()` une fois, puis le passer à `rank_models` (l.223) et à `choose_judge` (l.237). `arena_preselection` suit l'ordre de `ranked` : rien à changer.
- `src/app/views/04_Agent_Lab.py:107-127` : `is_verified = tools_verified(tag, capabilities, bench)` avec `bench = machine_benchmark()`, lu une fois (déjà passé à `agent_default`). `or tag == agent_tag` devient superflu, car `agent_default` exige `tool_success` ≥ 0,75. Mettre à jour le commentaire des l.101-106.
- `src/app/tabs/agent/crew.py:270-272` : prend `sorted_labels[0]`, rien à changer. Le commentaire « outils vérifiés » reste juste.
- Tests :
  - `tests/unit/test_model_defaults.py` : helpers `_rank` (l.72), `_speeds` (l.87) et fixtures `RTX_*` (l.606-640) ;
  - `tests/app/test_defaults.py` : fixture `machine_benchmark` (l.492), `FAKE_LOCAL_MODELS` (Gemma 3 1B sans `tools`, Qwen 2.5 1.5B avec `tools` dans le catalogue de test), `MID_LOCAL`, `BIG_LOCAL` ;
  - `tests/unit/test_ui.py:44` `isolated_rule` neutralise déjà `machine_benchmark`.

## Tasks & Acceptance

**Execution:**
- [x] `src/core/model_defaults.py` -- débit du benchmark dans `rank_models` quand il couvre tous les locaux qui tiennent ; `tools_verified` -- règle
- [x] `src/app/ui.py` -- benchmark lu une fois et passé au tri et au juge -- branchement
- [x] `src/app/views/04_Agent_Lab.py` -- mention et tri d'après `tools_verified` -- page Agents
- [x] `tests/unit/test_model_defaults.py` -- lignes 1 à 4 de la matrice (benchmark contraire à data/models.json, partiel, vide, gros local non mesuré), ordre de l'Arène, `tools_verified` (≥ 0,75 inclusif, 0 malgré le catalogue, None, absent, variante `:latest`) -- non-régression
- [x] `tests/app/test_defaults.py` -- AppTest : Chat libre et Arène triés sur le benchmark quand il couvre tous les locaux ; Agents : Qwen 2.5 1.5B (catalogue `tools`) mesuré à 0 perd la mention ; un modèle hors catalogue mesuré à 1,0 la reçoit -- surface
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les deux entrées traitées (story 15 « le plus rapide », story 18 « outils vérifiés ») -- traçabilité

**Acceptance Criteria:**
- Given un poste dont le benchmark mesure Qwen 2.5 1.5B plus rapide que Gemma 3 1B, when on ouvre l'Arène, then le Chat libre propose Qwen 2.5 1.5B en premier, et la présélection de l'Arène suit le même ordre.
- Given ce même poste, avec Qwen 2.5 1.5B mesuré à 0 en outils, when on ouvre la page Agents, then Qwen 2.5 1.5B apparaît sans « outils vérifiés ».
- Given un poste sans benchmark, when on ouvre l'Arène et les Agents, then les listes sont identiques à celles d'avant la story (tests existants inchangés).

## Spec Change Log

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 22 findings — high 0, medium 0, low 13, false 9, maybe-false 0
- findings:
  - `[low]` `[reject]` (blind) la page Agents relit `machine_benchmark()` après `model_menu` : deux benchmarks possibles si le fichier change entre les deux appels — lecture réussie gardée en cache ; appel antérieur à la story (story 18) ; fenêtre de quelques millisecondes dans un même rerun ; le correctif ajoute un champ à `ModelMenu`.
  - `[low]` `[patch]` (blind) aucun test de la contrainte « un seul appel » ni du même benchmark passé au tri et au juge — test `test_model_menu_reads_machine_benchmark_once_for_sort_and_judge` ajouté dans `tests/unit/test_ui.py`.
  - `[low]` `[reject]` (blind) un modèle dédié au raisonnement installé et non mesuré fait repasser tout le tri sur data/models.json — cas rare (modèle de raisonnement installé après la campagne), repli documenté dans les Design Notes ; le correctif ajoute une couverture par groupe.
  - `[low]` `[reject]` (blind) le repli sur data/models.json ou l'empreinte n'est signalé nulle part — hors intention ; le correctif ajoute un champ de raison ou un journal.
  - `[false]` `[reject]` (blind) la mention « outils vérifiés » mêle mesure et catalogue — c'est l'intention même (« quand il existe », catalogue sinon), reprise de deferred-work.md.
  - `[false]` `[reject]` (blind) `tools_verified` appliquerait le taux local à un modèle cloud — les clés du benchmark sont des tags Ollama locaux ; aucun tag cloud (`gpt-4o`, `mistral-large-2512`, `openai/gpt-oss-120b`, `x:cloud`, `x-cloud`) n'a le même tag de base qu'un modèle local.
  - `[low]` `[patch]` (blind) commentaire de `ModelChoice.speed_tps` inexact en mode benchmark — commentaire corrigé (local non mesuré à None, cloud qui garde data/models.json sans effet sur le tri).
  - `[low]` `[patch]` (blind) assertion `!=` trop faible dans `test_arena_preselection_follows_benchmark_order` — présélection et premier proposé exacts affirmés.
  - `[low]` `[reject]` (blind) égalité de débit, aucun local qui tient, modèle ignoré par `parse_results` non testés — départage et repli antérieurs, déjà couverts sans benchmark ; lecture du benchmark hors story (story 15).
  - `[low]` `[reject]` (blind) nom `test_agents_without_candidate_keep_current_order` devenu trompeur — l'ordre de tête est bien inchangé (valeur = Qwen 2.5 1.5B) ; seule la mention change, docstring mise à jour.
  - `[low]` `[patch]` (blind) `benchmark and` redondant, `_bench_speed` sans docstring — condition simplifiée, helper intégré.
  - `[low]` `[reject]` (blind) `test_chat_and_arena_sorted_on_machine_benchmark` recopie `run_page` — même motif que `test_arena_cloud_enabled_judge_is_most_capable_cloud` (deux exécutions à réglages différents).
  - `[false]` `[reject]` (blind) la story ne garde aucune trace des vérifications — écrite dans l'Auto Run Result à la finalisation.
  - `[low]` `[reject]` (edge) sans candidat d'`agent_default`, un modèle lent aux outils vérifiés par le benchmark peut passer en tête des Agents — règle antérieure des stories 7 et 18 (outils vérifiés d'abord), déjà vraie avec le catalogue ; les vérifiés restent triés par débit ; le correctif ajoute une branche.
  - `[low]` `[reject]` (edge) seconde lecture du benchmark par la page Agents — même constat que la première ligne, même raison.
  - `[false]` `[reject]` (edge) la mémoire disponible change entre reruns et fait basculer la source du débit — `available_memory_gb` est un instantané par session (story 7, KEEP) : la couverture ne bascule pas dans une session.
  - `[false]` `[reject]` (edge) `tools_verified` et tags cloud — même réfutation que la ligne blind.
  - `[false]` `[reject]` (intent) l'effet déborde les surfaces nommées (liste entière, Assistant documentaire) — le « premier modèle proposé » vit dans toutes les pages qui passent par `model_menu` ; une règle unique est le contrat de la story 7.
  - `[false]` `[reject]` (intent) l'ordre et le défaut des Agents changent via le drapeau « vérifié » — la clé de tri des stories 7 et 18 place déjà les outils vérifiés d'abord ; changer la source du drapeau est l'intention.
  - `[false]` `[reject]` (intent) repli modèle par modèle (lecture A2) non retenu — mêler le débit de ce poste à celui de data/models.json reviendrait à lire ce fichier comme benchmark du poste, ce que la story 15 interdit ; Design Notes.
  - `[false]` `[reject]` (intent) lecture C2 (benchmark du poste entier) — « quand il existe » vise le taux de ce modèle ; la source (deferred-work.md) dit « lire `tool_success` du benchmark du poste quand il existe, le catalogue sinon ».
  - `[low]` `[reject]` (intent) second appel à `machine_benchmark()` hors du menu — même constat que la première ligne.

## Design Notes

**Une seule source par comparaison.** Le débit d'un modèle mesuré sur ce poste n'est jamais comparé au débit `data/models.json` d'un autre modèle. Ce fichier peut venir d'une autre machine (story 15, *Never*). Le repli se fait donc par source entière, pas modèle par modèle : c'est ce que « data/models.json en repli » veut dire ici.

**Périmètre de la couverture.** « Tous les locaux qui tiennent », comme `_speed_known_for_all_fitting` aujourd'hui, modèles dédiés au raisonnement compris. Les locaux qui ne tiennent pas n'ont pas besoin d'être mesurés : leur débit n'entre pas dans le tri.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit
- `uvx ruff check` et `uvx black --check` sur les fichiers touchés -- expected: propres
- `git diff --stat 9e3e88c8d37a23fa176846245288a639ff486237 -- scripts benchmarks data config src/core/config.py` -- expected: vide

## Auto Run Result

Status: done

**Résumé.**
- `rank_models` trie « le plus rapide » sur le débit prudent du benchmark de ce poste quand ce benchmark mesure tous les locaux qui tiennent en mémoire. Sinon, la règle d'avant : data/models.json s'il donne un débit pour chacun, sinon l'empreinte. Les deux sources ne se mêlent jamais.
- Le premier modèle proposé et la présélection de l'Arène suivent ce tri. Le juge et `agent_default` ne changent pas.
- `tools_verified` : la mention « outils vérifiés » de la page Agents suit le `tool_success` mesuré sur ce poste quand il existe pour le modèle (≥ 0,75), le catalogue sinon.
- Sur poste-rtx3060 (lecture seule) : trio de tête inchangé (`granite4:350m`, `gemma3:1b`, `qwen3.5:0.8b`), places 4 et 5 inversées ; `gemma3:1b` et `olmo-3:7b`, mesurés à 0 en outils, perdent la mention.

**Fichiers.**
- `src/core/model_defaults.py` : débit du benchmark dans `rank_models`, `tools_verified`, docstrings.
- `src/app/ui.py` : benchmark lu une fois par `model_menu`, passé au tri et au juge.
- `src/app/views/04_Agent_Lab.py` : mention et tri d'après `tools_verified`.
- Tests : `tests/unit/test_model_defaults.py`, `tests/unit/test_ui.py`, `tests/app/test_defaults.py` (cas `debit` du test paramétré : Qwen3.5 prend la mention, mesurée à 1,0).
- `_bmad-output/implementation-artifacts/deferred-work.md` : deux entrées retirées.

**Revue.** 22 constats : 4 corrigés (tous low), 0 différé, 18 rejetés (9 false, 9 low, raisons au journal).

**Revue de suivi recommandée :** false (aucun correctif high ni medium).

**Vérification.**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` : 1 069 réussis.
- ruff et black propres sur les fichiers touchés.
- `git diff --stat` sur `scripts benchmarks data config src/core/config.py` : vide.

**Risques.** Un modèle installé après la campagne de benchmark fait repasser tout le tri sur data/models.json, sans signal à l'écran. Non vérifié au navigateur.
