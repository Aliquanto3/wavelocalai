---
title: 'Juge et modèle par défaut choisis d’après le benchmark du poste'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_commit: 'e828b7e15a58dc46d2f251b2f4d9d538acb92c54'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/specs/spec-fiabilisation-frontend/stories/7-choix-par-defaut-adaptes-machine.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Sur poste-rtx3060 (6 Go de VRAM, 16,7 Go de RAM libre), la règle de la story 7 choisit pour juge `granite4.2:8b`, la plus grosse empreinte qui tient en RAM : 7,65 Go, 51 % sur le GPU, 5 à 10 tokens/s, alors que le benchmark de ce poste mesure des juges plus précis et bien plus rapides. Le modèle proposé par défaut est `lfm2.5-thinking:1.2b`, dont le raisonnement allonge la réponse réelle malgré son débit.

**Approach:** Le juge par défaut suit, dans l'ordre : (1) si des modèles cloud sont proposés (cloud autorisé et fournisseur configuré), le cloud le plus capable, selon un ordre fixé dans le code ; (2) sinon, parmi les modèles locaux installés que le benchmark de ce poste a mesurés à plus de 10 tokens/s, le plus précis d'au moins 4B de paramètres actifs, et le plus précis de tous seulement si aucun n'atteint 4B (avertissement « Note peu fiable » conservé) ; (3) sans benchmark de ce poste, ou si aucun modèle ne dépasse 10 tokens/s, la règle actuelle de la story 7. Le modèle proposé par défaut n'est jamais un modèle de raisonnement ; ces modèles restent sélectionnables.

Décisions de l'utilisateur (27/09) :
- précision = moyenne de `reasoning_avg` et `instruction_following_avg` (`quality_scores`) ;
- plancher de 4B paramètres actifs conservé pour le juge ;
- juge cloud le plus capable, jamais un juge cloud quand le cloud est désactivé.
- modèle de raisonnement écarté du choix par défaut = modèle dédié, reconnu à « thinking » ou « reasoning » dans son tag ou son nom (LFM 2.5 1.2B Thinking) ; les hybrides (capacité `thinking` du catalogue) restent candidats ;
- la présélection de l'Arène écarte aussi ces modèles dédiés.

## Boundaries & Constraints

**Always:** Le benchmark du poste est lu dans `benchmarks/results/<machine_id>.json` (versionné, lecture seule), le poste étant reconnu par la même empreinte que `scripts/machine_profile.machine_id`. Débit retenu : le plus bas entre `avg_tokens_per_second` et `runs.tokens_per_second.mean` (prudent : Granite 4.2 8B mesure 10,41 puis 5,05). Seuls les modèles installés et locaux sont candidats au juge local. La logique reste dans `src/core` sans `streamlit` ; l'aide du sélecteur de juge dit comment le juge a été choisi.

**Never:** Modifier `scripts/`, `benchmarks/`, `data/` ou `src/core/config.py`. Proposer un juge cloud quand le cloud est désactivé. Lire `data/models.json` comme benchmark du poste (il peut venir d'une autre machine). Mesurer quoi que ce soit au démarrage de l'app.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Cloud autorisé | Claude Sonnet 4 et GPT-4o listés | Juge = Claude Sonnet 4, badge Cloud | N/A |
| Poste benchmarké | poste-rtx3060, modèles actuels | Juge = Gemma 4 E4B (QAT) : 0,93, ~69 tok/s | N/A |
| Aucun ≥ 4B à plus de 10 tok/s | seuls des < 4B rapides | Le plus précis d'entre eux, avertissement « Note peu fiable » | N/A |
| Poste inconnu | aucun fichier à son empreinte | Règle de la story 7 | N/A |
| Fichier illisible | JSON invalide ou champs absents | Règle de la story 7, avertissement dans le journal | Aucune exception |
| Modèle par défaut | `lfm2.5-thinking:1.2b` le plus rapide | Premier proposé : Granite 4.0 350M ; Arène : Granite 4.0 350M, Gemma 3 1B, Qwen 3.5 0.8B | N/A |

</frozen-after-approval>

## Code Map

- `src/core/model_defaults.py` -- règle actuelle : `rank_models`, `default_model` (premier trié), `default_judge` (plus grosse empreinte, plancher `JUDGE_MIN_PARAMS_B`), `arena_preselection` (exclut le juge). Point d'extension principal.
- `src/core/benchmark_results.py` (nouveau) -- empreinte du poste (même calcul que `scripts/machine_profile.py:93`, sans importer `scripts/`), lecture de `benchmarks/results/*.json`, correspondance nom → tag par `config/models_catalog.json` (`find_entry`), précision et débit prudent par tag.
- `src/app/ui.py:177` `model_menu` -- appelle `rank_models`, `default_judge`, `arena_preselection` ; y passer le benchmark du poste. `judge_help` (l.218) choisit l'aide selon le juge.
- `src/app/states.py:57-80` -- textes du juge (`JUDGE_HELP_*`, `WEAK_JUDGE_*`) : ajouter l'aide « choisi d'après le benchmark de ce poste » et « juge cloud ».
- `src/app/tabs/inference/arena.py:475-510`, `src/app/tabs/rag/eval.py:185-240` -- consommateurs de `menu.judge_default` : inchangés, sauf si le juge cloud y demande un badge (déjà rendu par `render_badge`).
- `src/core/providers/{anthropic,openai,mistral}_provider.py` -- modèles cloud listés seulement si la clé est configurée ; tags à ordonner (`claude-sonnet-4-20250514`, `gpt-4o`, `mistral-large-*`…).
- Catalogue : `capabilities` contient `thinking` ; LFM 2.5 1.2B Thinking est le seul modèle dédié au raisonnement installé ici.
- Tests : `tests/unit/test_model_defaults.py`, `tests/app/test_defaults.py` (catalogue de test de `tests/app/conftest.py`).

## Tasks & Acceptance

**Execution:**
- [x] `src/core/benchmark_results.py` -- empreinte du poste, chargement tolérant du fichier de résultats, `{tag: (précision, débit prudent)}` -- source unique du benchmark côté app
- [x] `src/core/model_defaults.py` -- ordre de préférence cloud, juge par benchmark (seuil 10 tok/s, plancher 4B, repli story 7), exclusion des modèles de raisonnement dédiés du premier proposé et de la présélection de l'Arène -- règle
- [x] `src/app/ui.py`, `src/app/states.py` -- brancher le benchmark dans `model_menu`, textes d'aide du juge -- interface
- [x] `tests/unit/test_benchmark_results.py`, `tests/unit/test_model_defaults.py`, `tests/app/test_defaults.py` -- matrice ci-dessus, empreinte identique à `scripts/machine_profile.machine_id`, résultats factices en `tmp_path` -- non-régression
- [x] `tests/e2e/test_arena.py` -- le juge par défaut reste local sans cloud ; ne pas figer un nom de modèle propre à un poste -- e2e

**Acceptance Criteria:**
- Given poste-rtx3060 avec ses modèles actuels et le cloud désactivé, when on ouvre l'Arène, then le juge par défaut est Gemma 4 E4B (QAT) et aucun avertissement « Note peu fiable » ne s'affiche.
- Given le cloud activé avec une clé Anthropic, when on ouvre l'Arène, then le juge par défaut est Claude Sonnet 4 avec un badge Cloud.
- Given poste-rtx3060, when on ouvre la Discussion, then le premier modèle proposé n'est pas LFM 2.5 1.2B Thinking.

## Implementation Notes

- Implémentation par sous-agent, puis 12 correctifs de revue. `src/core/benchmark_results.py` (nouveau) : empreinte du poste identique à `scripts/machine_profile.machine_id`, lecture tolérante, précision et débit prudent par tag ; `model_defaults.choose_judge` renvoie le juge et sa raison (cloud, benchmark, empreinte).
- Hors Code Map, validés : tri de l'Agent Lab (modèle de raisonnement après les autres, sinon LFM Thinking redevenait défaut par ses outils vérifiés) ; nom du fournisseur pour un modèle cloud hors catalogue (« Claude Sonnet 4 · Cloud ») ; `test_sovereignty` attend 2 badges Cloud quand le juge est cloud.
- Un modèle dédié au raisonnement passe après tous les autres locaux, même ceux qui ne tiennent pas en mémoire ; il n'est premier que s'il est le seul local (intention : « jamais »).
- Vérifié sur poste-rtx3060 : premier proposé `granite4:350m`, juge `gemma4:e4b-it-qat` (benchmark), Arène `granite4:350m`, `gemma3:1b`, `qwen3.5:0.8b` ; `pytest tests/unit tests/app` 816 réussis ; `tests/e2e/test_arena.py` 4 réussis ; `scripts/`, `benchmarks/`, `data/`, `config/` et `src/core/config.py` intacts.

## Review Triage Log

Revue du 27/09 : Blind Hunter (13), Edge Case Hunter (11), Verification Gap (2 écarts + 1 autre). Doublons regroupés par cause.

- Juge du benchmark sans vérification de la mémoire (blind, edge) — medium, patch : candidats qui tiennent d'abord ; RAM libre faible réaliste (Gemma 4 E4B = 7,6 Go).
- Modèle de raisonnement encore proposé en premier quand il est seul à tenir (edge, claim) — medium, patch : écart à l'intention gelée (« jamais ») ; `dedicated_reasoning` avant `not fits` dans les deux tris.
- Tri de l'Agent Lab non testé avec un modèle de raisonnement (verification-gap) — medium, patch : test ajouté.
- Résultat vide jamais mis en cache non testé (verification-gap) — low, patch : test ajouté.
- `tests/unit/test_ui.py` lit le benchmark du poste (verification-gap, autre) — medium, patch : `machine_benchmark` neutralisé dans `isolated_rule` ; échec reproduit sur poste-rtx3060.
- Aide du juge cloud muette sur les extraits envoyés en évaluation RAG (blind) — low, patch : texte élargi.
- NaN ou infini acceptés dans les résultats (edge) — low, patch : valeurs non finies ignorées.
- Docstring « lu une fois par processus » inexacte (blind, edge) — low, patch (docstring) ; le glob à chaque rerun, les avertissements répétés et le cache sans date de modification : low, rejetés (dossier minuscule, cas d'échec seulement, export rare suivi d'un redémarrage).
- Assertion e2e par préfixe (blind, edge) — low, patch : libellé exact.
- `CLOUD_JUDGE_EXCLUDED` mal nommé (blind) — low, patch : renommé `CLOUD_JUDGE_DEMOTED`.
- `ModelChoice` construit par position (blind) — low, patch : arguments nommés.
- Trois lignes vides, `black --check` en CI (blind) — low, patch.
- Juge dédié au raisonnement possible (blind, edge) — low, rejeté : seulement si aucun modèle ≥ 4B ne dépasse 10 tok/s et que le modèle de raisonnement est le plus précis ; l'intention ne vise que le modèle proposé et l'Arène.
- Cloud hors liste classé par ordre alphabétique (blind, edge ×2) — false comme écart : c'est la règle des Design Notes ; la story 16 ajoute Groq à la liste.
- Modèle par défaut trié sur le débit de data/models.json (blind) — medium, defer : antérieur (story 7).
- Détection du raisonnement par sous-chaîne seulement (blind) — false comme défaut : décision de l'utilisateur (dédiés reconnus à « thinking » ou « reasoning »).
- Lignes 3 et 5 de la matrice sans test AppTest (blind) — false : couvertes par `test_benchmark_judge_without_4b_takes_most_precise_and_stays_weak` et `test_unreadable_file_gives_empty_benchmark_and_a_warning`.
- Comparaison lexicale d'`exported_at`, fichier récent invalide, tags en double (edge) — low, rejetés : un seul exporteur au format constant, cas non rencontrés.

## Design Notes

Ordre cloud (du plus capable au moins capable, préfixes de tag) : `claude-sonnet-4`, `gpt-4o` (hors `-mini`), `mistral-large`, `claude-3-5-sonnet`, `claude-3-opus`, `gpt-4-turbo`, `mistral-medium`, puis les autres cloud par ordre alphabétique. Un fournisseur ajouté plus tard (Groq…) s'insère dans cette liste.

Précision égale : départage par le débit prudent, puis par le tag.

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit
- `.venv-app\Scripts\python -m pytest tests/e2e/test_arena.py -m e2e` -- expected: réussit sur poste-rtx3060

**Manual checks (if no CLI):**
- Arène, cloud désactivé : juge Gemma 4 E4B (QAT) ; cloud activé : juge cloud avec badge.
