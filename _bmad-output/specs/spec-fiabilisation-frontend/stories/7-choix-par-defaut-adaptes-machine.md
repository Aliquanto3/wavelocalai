---
title: 'Choix par défaut adaptés à la machine'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_revision: '1b91fa2cc25b51db42b25ab144297044e1697036'
review_loop_iteration: 1
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      La règle « tient en mémoire » ignore la VRAM : sur la machine de référence (6 Go de VRAM), le juge par défaut peut déborder sur le CPU.
    evidence: |-
      Contrat : mémoire vive disponible. rtx F5 suggérait « le plus rapide qui tient en VRAM ».
    location: >-
      src/core/model_defaults.py
    severity: medium (unverified)
  - summary: >-
      Unifier l'empreinte de model_defaults et ResourceManager.estimate_model_ram (garde-fou).
    evidence: |-
      Deux règles : taille × 1,25 et marge 1,10 contre ram_usage × 1,1 ou taille + 1 Go.
    location: >-
      src/core/resource_manager.py:47
    severity: medium
  - summary: >-
      Juge avec seulement des modèles cloud : le sélecteur affiche le premier modèle cloud.
    evidence: |-
      Pas de juge par défaut, mais index 0 ; aide « aucun modèle local installé ».
    location: >-
      src/app/tabs/inference/arena.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** Les modèles proposés par défaut ne tiennent pas compte de la machine : tri qui place le cloud en tête puis l'ordre alphabétique, premier de la liste choisi partout (y compris un 27B sur un portable de 16 Go), juges choisis par sous-chaîne de nom (« mistral », « llama », « gpt »), Arène qui démarre avec un seul modèle et bouton actif avec un seul modèle, juge de 1B qui note 90/100 une réponse qui boucle (F10, F13, U19).

**Approach:** Une règle explicite et testée, calculée depuis l'empreinte mesurée (`measured_loaded_gb` de `config/models_catalog.json`) et la mémoire disponible : modèles locaux d'abord, le premier proposé étant le plus rapide qui tient en mémoire ; juge par défaut = le plus gros modèle local qui tient, avec un avertissement sous ~4B ; Arène à 2 modèles minimum, présélectionnés quand ils tiennent.

## Boundaries & Constraints

**Always:** règle en fonctions pures (sans `streamlit`), testées ; empreinte lue dans `measured_loaded_gb`, avec un repli documenté quand la mesure manque ; « tient en mémoire » comparé à la mémoire vive disponible (moins la réserve système de `src/core/config.py`) ; modèles locaux avant le cloud dans toutes les listes (`model-select`), les tags sous-jacents inchangés ; tests sans Ollama ni réseau, avec un catalogue et une mémoire simulés.

**Never:** éditer `config/models_catalog.json` (écrit par `scripts/build_catalog.py`) ni `src/core/config.py` ; changer l'état par défaut du mode cloud (D1 : story 8) ; persister le choix entre onglets (story 9) ; télécharger un modèle.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Ordre | 1 cloud, 3 locaux (1,2 Go, 3,1 Go, 4,9 Go mesurés), 8 Go disponibles | Locaux d'abord ; le premier est le plus rapide qui tient ; cloud en dernier | — |
| Ne tient pas | local de 4,9 Go, 3 Go disponibles | Jamais présélectionné, placé après les locaux qui tiennent | — |
| Mesure absente | local sans `measured_loaded_gb` | Empreinte estimée par le repli ; si aucune estimation, considéré comme ne tenant pas pour la présélection | — |
| Aucun local ne tient | tous trop gros | Premier de la liste = le plus petit local ; aucun plantage | — |
| Juge | locaux de 1B, 3,8B et 8B ; le 8B ne tient pas | Juge = 3,8B, avertissement « note peu fiable » (< ~4B) | — |
| Juge suffisant | un local ≥ 4B tient | Pas d'avertissement | — |
| Arène, défaut | ≥ 2 locaux qui tiennent | 2 à 3 petits locaux présélectionnés | — |
| Arène, 1 modèle | 1 modèle sélectionné | Bouton « Lancer la comparaison » désactivé, légende « Choisissez au moins 2 modèles » | — |
| Agents | modèles avec et sans outils vérifiés | Outils vérifiés d'abord, puis local avant cloud, puis la règle mémoire | — |

</intent-contract>

## Code Map

- `src/app/ui.py:34-55` -- `model_options(models, cloud_types)` : clé de tri `(not is_cloud, friendly)` = cloud d'abord ; docstring qui renvoie le tri à cette story. Point d'entrée commun de l'Arène (`views/02_Inference_Arena.py:25`) et de l'Assistant documentaire (`views/03_RAG_Knowledge.py:259-265`).
- `config/models_catalog.json` (LECTURE SEULE, versionné) -- `{"_reference_machine": …, "models": {nom: {ollama_tag, type, size_gb "0.7 GB", params_tot "0.35B", params_act, capabilities, role, measured_loaded_gb (float ou absent/None, None pour les MoE), moe}}}` ; 28 modèles locaux ; n'est lu nulle part dans `src/`. Correspondance par `ollama_tag` (et variante `:latest`). Pas de mesure de vitesse.
- `scripts/bench_here.py:77-80` (LECTURE SEULE) -- repli existant : `measured_loaded_gb or parse_size(size_gb) * 1.25`, marge `FIT_MARGIN = 1.10`.
- `src/core/models_db.py` -- `MODELS_DB` (depuis `data/models.json`, local, absent de la VM) ; `benchmark_stats.avg_tokens_per_second` quand il existe (lu par `tabs/inference/manager.py:173,202`) : seule donnée de vitesse disponible à l'exécution.
- `src/core/resource_manager.py:42-80` -- `get_available_ram_gb()` (psutil), `estimate_model_ram` ; `src/core/config.py:25` `SYSTEM_RAM_BUFFER_GB = 0.5`.
- `src/app/tabs/inference/manager.py:22-49` -- `_parse_params_to_float` (« 8X7B », « 1.5B », « 350M »), `_parse_size_to_float` : à déplacer vers un module partagé plutôt que dupliquer.
- `src/app/tabs/inference/chat.py:94-102`, `lab.py:111`, `rag/chat.py:49-54` -- défaut = premier de la liste triée.
- `src/app/tabs/inference/arena.py:368-416` -- multiselect par défaut `sorted_display_names[:2]` ; juge par sous-chaîne « mistral »/« llama » ; bouton `disabled=not selected_arena_tags` (actif avec 1 modèle).
- `src/app/tabs/rag/eval.py:97-112` -- candidat par défaut = premier ; juge par sous-chaîne « mistral »/« gpt »/« large », dernier trouvé.
- `src/app/views/04_Agent_Lab.py:226-253` -- tri propre (outils vérifiés d'abord, puis cloud avant local) ; `tabs/agent/crew.py:208,245,371` -- `default_tag = installed_models_list[0]` (ordre brut du fournisseur).
- Tests à mettre à jour sur la nouvelle cible (sans affaiblir) : `tests/unit/test_ui.py:29-70` (ordre « cloud d'abord »), `tests/app/test_theme.py:281-326` (ordre de l'Agent Lab). Banc : `tests/app/conftest.py` (`FAKE_LOCAL_MODELS`, `three_models`, `fake_inference`), `tests/fixtures/models_catalog_test.json` (format plat de `MODELS_DB`, sans `measured_loaded_gb`).

## Tasks & Acceptance

**Execution:**
- `src/core/model_defaults.py` (nouveau) -- chargement du catalogue versionné (chemin défini dans ce module, sans toucher `config.py`), empreinte (mesure, puis repli), « tient », vitesse connue, taille en paramètres, clé de tri, défaut, juge par défaut, présélection de l'Arène.
- `src/app/ui.py` -- `model_options` trié par la règle ; fonction pour la mémoire disponible injectable dans les tests.
- `src/app/tabs/inference/{chat,lab,arena}.py`, `src/app/tabs/rag/{chat,eval}.py`, `src/app/views/04_Agent_Lab.py`, `src/app/tabs/agent/crew.py` -- défauts, juges, présélection, bouton désactivé sous 2 modèles, avertissement du juge.
- `tests/unit/test_model_defaults.py` -- chaque ligne de la matrice avec un catalogue et une mémoire simulés.
- `tests/app/` -- Arène : présélection, juge par défaut, avertissement, bouton désactivé à 1 modèle ; Discussion et chat : modèle par défaut.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given `git diff` de la story, when on le lit, then `config/models_catalog.json` et `src/core/config.py` sont inchangés.

## Spec Change Log

### 2026-09-27 — Boucle 1 : définition du juge et de « tient »
- Déclencheur : revue (intention, relecteur à l'aveugle, cas limites). Sur le vrai catalogue, « le plus gros » compté en paramètres désignait `bonsai:27b-q1_0` (27B en 1 bit), le défaut même que F10 dénonce ; le juge était aussi présélectionné comme candidat ; la marge `FIT_MARGIN` de `bench_here.py` manquait ; une vitesse mesurée sur une autre machine battait toujours une vitesse inconnue ; un juge de taille inconnue échappait à l'avertissement ; deux modèles au même nom : l'un disparaissait.
- Amendement : Design Notes réécrites (juge par empreinte, marge 1,10, modèles déjà chargés, vitesse comparée seulement si toutes connues, paramètres actifs d'abord, robustesse du catalogue, tags distants, libellés désambiguïsés).
- État évité : juge 1 bit par défaut ; juge qui se note lui-même ; présélection en limite de mémoire.
- KEEP : module pur `src/core/model_defaults.py` et `model_menu()` dans `src/app/ui.py` ; mémoire mesurée une fois par session (plus le rajout des modèles chargés) pour ne pas réordonner les listes en pleine conversation ; bouton « Lancer la comparaison » désactivé sous 2 modèles avec la légende ; avertissement du juge hors de l'expander et texte partagé dans `states.py` ; tri de l'Agent Lab (outils vérifiés d'abord, puis la règle) ; `default_tag` de l'équipe = premier de la liste triée ; réutilisation de `extract_params_billions` et d'un `parse_size_gb` partagé dans `manager.py` ; `tests/app/conftest.py` qui fixe la mémoire et remplace le catalogue versionné. Tentative précédente conservée hors dépôt : `/tmp/nuit/s7-tentative-1.patch`.
- Tests à ajouter en plus : avertissement du juge faible dans « Évaluation de la qualité » (AppTest) ; « Ajouter un agent » de l'équipe prend le modèle de la règle ; règle appliquée au vrai `config/models_catalog.json` (6,5 Go et 20 Go disponibles) sans erreur, juge hors de la présélection ; « 350 MB » lu comme 0,35 Go dans la gestion des modèles.

## Review Triage Log

### 2026-09-27 — Review pass (boucle 1)
- verdicts: 34 findings — high 1, medium 11, low 13, false 2, maybe-false 7
- findings:
  - `[high]` `[bad_spec]` (intent, blind) juge par défaut = Bonsai 27B 1 bit sur le vrai catalogue (défaut de F10) — Design Notes : juge par empreinte.
  - `[medium]` `[bad_spec]` (intent, blind) juge présélectionné comme candidat de l'Arène — exclu de la présélection.
  - `[medium]` `[bad_spec]` (blind, edge) vitesse mesurée qui bat toujours une vitesse inconnue — comparaison seulement si toutes connues.
  - `[medium]` `[bad_spec]` (blind) marge `FIT_MARGIN` absente, valeurs recopiées sans contrôle — marge 1,10 et test de concordance.
  - `[medium]` `[defer]` (blind) troisième règle d'empreinte à côté de `ResourceManager.estimate_model_ram` (garde-fou) — unification hors périmètre (garde-fou de la story 5).
  - `[medium]` `[bad_spec]` (blind, edge) modèle déjà chargé dans Ollama compté comme mémoire utilisée — rajout de la mémoire des modèles chargés.
  - `[medium]` `[bad_spec]` (blind, edge) deux modèles au même libellé : l'un disparaît — libellé désambiguïsé.
  - `[low]` `[bad_spec]` (blind, edge) `model_options` gardé seulement par les tests — à migrer ou justifier lors de la ré-implémentation.
  - `[low]` `[reject]` (blind) unités Go/Gio mêlées (~7 %) — sous la marge de 10 %.
  - `[low]` `[reject]` (blind) catalogue gardé en cache pendant la vie du processus — régénéré hors session de démo.
  - `[medium]` `[bad_spec]` (verification-gap, blind) avertissement du juge faible de l'évaluation non testé — test demandé.
  - `[medium]` `[bad_spec]` (verification-gap) « Ajouter un agent » non testé — test demandé.
  - `[low]` `[bad_spec]` (blind) « 350 MB » non testé dans la gestion des modèles — test demandé.
  - `[low]` `[bad_spec]` (blind) test du catalogue versionné fragile (entrée API future) — test sur le vrai catalogue robuste.
  - `[medium]` `[bad_spec]` (blind, edge) juge de taille inconnue sans avertissement — avertissement.
  - `[medium]` `[bad_spec]` (edge) MoE hors catalogue jugé sur ses paramètres totaux ; `params_tot` préféré à `params_act` d'une autre source — ordre des sources.
  - `[low]` `[bad_spec]` (edge) tag distant servi par Ollama traité comme local — traité comme cloud.
  - `[low]` `[bad_spec]` (edge) catalogue au format inattendu : exception — ignoré.
  - `[maybe-false]` `[reject]` (intent) mémoire vidéo non prise en compte (A2) — contrat : mémoire vive disponible ; noté au rapport.
  - `[maybe-false]` `[reject]` (intent) défauts à choix unique hors mémoire quand rien ne tient — ligne de la matrice « aucun local ne tient ».
  - `[low]` `[reject]` (intent, edge) Agents : outils vérifiés avant local — ligne du contrat d'intention (lecture seule) ; noté au rapport.
  - `[maybe-false]` `[reject]` (intent) « petits » modèles de l'Arène — les plus rapides qui tiennent, hors juge.
  - `[low]` `[reject]` (intent) mesure de vitesse testée seulement en unitaire — suffisant pour une fonction pure.
  - `[maybe-false]` `[reject]` (blind) juge cloud en repli quand rien ne tient — contraire à « local » (D1).
  - `[false]` `[reject]` (verification-gap) `model_selector.py` — code mort.
  - `[maybe-false]` `[reject]` (intent) Granite 350M dans la présélection — U19 vise le juge, pas les candidats.
  - `[low]` `[reject]` (intent) changement de `open_crew_library` — interne.
  - `[low]` `[reject]` (blind) lecture de la mémoire vivante dans la barre de l'Agent Lab vs instantané — affichages distincts, instantané voulu (KEEP).
  - `[maybe-false]` `[reject]` (verification-gap) bibliothèque d'équipes (dialogue) — couverte par le même `default_tag`.
  - `[low]` `[reject]` (edge) collision de noms de repli hors catalogue — doublon de la désambiguïsation.
  - `[false]` `[reject]` (blind) snapshot figé sans remise à zéro — doublon.
  - `[low]` `[reject]` (intent) seuil sur paramètres inconnus — doublon.
  - `[low]` `[reject]` (blind) fil du repli cloud — doublon.
  - `[maybe-false]` `[reject]` (intent) critère « premier proposé » sur les Agents — doublon du contrat.

### 2026-09-27 — Review pass (après boucle 1)
- verdicts: 41 findings — high 1, medium 12, low 17, false 2, maybe-false 9
- findings:
  - `[high]` `[patch]` (edge) tag Ollama distant `x:cloud` traité comme local et proposé par défaut (données hors de la machine) — `:cloud` et `-cloud` reconnus ; test.
  - `[medium]` `[patch]` (intent, edge) juge par défaut = MoE que la règle déclare faible alors qu'un juge ≥ 4B tient — juges fiables d'abord.
  - `[medium]` `[patch]` (edge, verification-gap) nom désambiguïsé passé à `get_model_info` : outils vérifiés et carbone perdus — recherches par le tag.
  - `[medium]` `[patch]` (intent, blind, edge) Agents : un cloud vérifié ou un local qui ne tient pas devient le défaut — tri (cloud, ne tient pas, non vérifié, règle) ; s'écarte de la ligne « Agents » de la matrice au profit de la clause « locaux avant le cloud dans toutes les listes » et de D1 ; choix noté au rapport.
  - `[low]` `[patch]` (edge) entrée sans `model` : exception — ignorée.
  - `[low]` `[patch]` (edge, blind) échec de lecture du catalogue mis en cache ; dict partagé modifiable — échec non mis en cache, copie renvoyée.
  - `[medium]` `[patch]` (blind) juge qui note sa propre réponse sans le dire — légende quand le juge est comparé.
  - `[medium]` `[patch]` (blind) avertissement du juge faible absent des résultats (U19) — répété au-dessus des résultats et du podium.
  - `[medium]` `[patch]` (blind) rien ne tient : juge par défaut hors mémoire avec une aide fausse — avertissement et aide conditionnelle.
  - `[low]` `[reject]` (blind) marqueur « trop gros » dans les libellés — libellés = clés de sélection ; l'ordre et les avertissements suffisent.
  - `[low]` `[patch]` (blind) mémoire unifiée (Apple Silicon) — limite documentée.
  - `[low]` `[patch]` (blind) hôte Ollama distant mêlé à la RAM locale — modèles chargés ajoutés seulement pour un hôte local.
  - `[low]` `[patch]` (blind) instantané jamais rafraîchi — effacé après « Ajouter le modèle » et « Rafraîchir ».
  - `[low]` `[reject]` (blind) lecture de `ps()` dupliquée — deux lecteurs courts, hors périmètre.
  - `[medium]` `[patch]` (blind) test sur le vrai catalogue dépendant de son contenu — invariants seulement.
  - `[low]` `[patch]` (blind, verification-gap) chemins non testés (`LLMProvider.loaded_models_ram_gb`, juge absent, `-cloud`) — tests ajoutés.
  - `[low]` `[patch]` (blind) catalogue en cache partagé modifiable — doublon, corrigé.
  - `[low]` `[patch]` (blind) un seul texte d'avertissement pour deux situations — textes et conseils distincts.
  - `[medium]` `[patch]` (verification-gap) candidat par défaut de l'évaluation qui exclut le juge, jamais exercé — test à 1 Go.
  - `[medium]` `[patch]` (verification-gap) « Charger une équipe » non testé — test en deux temps (limite d'AppTest sur les dialogues).
  - `[medium]` `[patch]` (verification-gap) enveloppe `LLMProvider.loaded_models_ram_gb` toujours simulée — test.
  - `[low]` `[patch]` (verification-gap) contrat « ne lève jamais » troué — appel dans le `try`.
  - `[maybe-false]` `[defer]` (intent) VRAM ignorée : sur la machine de référence (6 Go de VRAM), le juge peut dépasser la VRAM — contrat : mémoire vive ; noté au rapport.
  - `[maybe-false]` `[reject]` (intent) « le plus rapide » ramené à « le plus petit » sans mesures — indicateur de vitesse documenté.
  - `[maybe-false]` `[reject]` (intent) Granite 350M présélectionné — U19 vise le juge.
  - `[maybe-false]` `[reject]` (intent) Arène à 0 ou 1 modèle présélectionné quand peu tiennent — « présélectionnés quand ils tiennent » ; bouton désactivé.
  - `[maybe-false]` `[reject]` (intent) empreinte mesurée jamais atteinte au niveau des pages — correspondance par `ollama_tag` testée en unitaire.
  - `[low]` `[reject]` (intent) comparaison côte à côte d'U-07 — hors contrat.
  - `[maybe-false]` `[reject]` (intent) instantané testé avec des simulations — conforme à la décision KEEP.
  - `[low]` `[reject]` (intent) `manager.py` : équivalence des paramètres — vérifiée sur les entrées testées.
  - `[false]` `[reject]` (blind) tous les modèles présélectionnés sont petits — doublon.
  - `[low]` `[reject]` (edge) collision de noms hors catalogue — doublon.
  - `[low]` `[reject]` (verification-gap) désambiguïsation latente — doublon, corrigé.
  - `[maybe-false]` `[defer]` (orchestrateur) juge avec seulement du cloud : le sélecteur affiche le premier modèle cloud (index 0) — aide « aucun modèle local installé » ; à revoir avec la story 8.
  - `[low]` `[defer]` (orchestrateur) `chat.py:218` : `_calculate_metrics` reçoit le libellé au lieu du nom — préexistant.
  - `[low]` `[reject]` (edge) claim « local d'abord » sur les Agents — doublon, corrigé.
  - `[low]` `[reject]` (edge) claim `:cloud` — doublon, corrigé.
  - `[false]` `[reject]` (verification-gap) `model_selector.py` — code mort.
  - `[low]` `[reject]` (blind) ps() au premier affichage (≤ 2 s) — accepté.
  - `[low]` `[reject]` (intent) aide « outils vérifiés » lue dans `data/models.json` — source existante.
  - `[low]` `[reject]` (blind) GiB/Go — sous la marge.

## Design Notes

« Le plus rapide » : aucune vitesse n'est versionnée ; utiliser `benchmark_stats.avg_tokens_per_second` de `MODELS_DB` seulement pour départager des modèles qui en ont tous une ; sinon la plus petite empreinte sert d'indicateur de vitesse (un modèle plus petit génère plus vite sur une même machine). Une vitesse connue ne passe jamais devant une vitesse inconnue par défaut.

« Tient en mémoire » : `empreinte × 1,10 ≤ mémoire vive disponible − SYSTEM_RAM_BUFFER_GB`, avec la marge `FIT_MARGIN = 1.10` et le repli `SIZE_TO_LOADED = 1.25` de `scripts/bench_here.py` (un test lit ce script en texte, sans l'importer, et vérifie que les deux valeurs concordent). La mémoire des modèles déjà chargés dans Ollama (`ps()`) est rajoutée à la mémoire disponible, pour qu'un modèle déjà résident ne soit pas déclassé.

« Le plus gros » (juge) : la plus grande **empreinte** mesurée ou estimée parmi les locaux qui tiennent, départagée par les paramètres actifs. L'empreinte reflète paramètres × précision : un 27B quantifié en 1 bit (4,9 Go) ne passe pas devant un 9B en 3 bits (5,4 Go), et un MoE n'est pas jugé sur ses paramètres totaux. Le juge par défaut est exclu de la présélection de l'Arène (il ne note pas sa propre réponse). Avertissement « note peu fiable » quand les paramètres actifs sont < 4B **ou inconnus** pour un juge local.

Paramètres : `params_act` (catalogue, puis `MODELS_DB`) avant `params_tot` ; `details.parameter_size` d'Ollama est un total, utilisé en dernier recours.

Robustesse : catalogue dont `models` n'est pas un dictionnaire → ignoré ; tag distant servi par Ollama (`remote_host`, suffixe `-cloud`) traité comme cloud ; deux tags au même nom affiché → libellé désambiguïsé par le tag (aucun modèle masqué).

Exemple de clé de tri : `(is_cloud, not fits, speed_rank_if_all_known, footprint_or_inf, friendly)`.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `git diff --stat 1b91fa2cc25b51db42b25ab144297044e1697036 -- config/models_catalog.json src/core/config.py` -- expected: vide

## Auto Run Result

Status: done

**Résumé :** règle de choix par défaut explicite et testée (`src/core/model_defaults.py`) : empreinte = `measured_loaded_gb` du catalogue versionné, sinon taille × 1,25 ; « tient » = empreinte × 1,10 ≤ RAM disponible (plus les modèles déjà chargés) − réserve ; locaux d'abord, le premier proposé est le plus rapide qui tient (vitesse mesurée seulement si toutes connues, sinon plus petite empreinte) ; juge = juge fiable (≥ 4B actifs) à la plus grande empreinte qui tient, sinon avertissement ; Arène : 2 à 3 locaux qui tiennent présélectionnés hors juge, bouton désactivé sous 2 modèles ; tags distants (`:cloud`, `-cloud`) traités comme cloud. Sur le vrai catalogue à 6,5 Go : premier `gemma3:1b`, juge `qwen3.5-ud:9b-q3_k_xl` (plus Bonsai 27B 1 bit).

**Fichiers :** `src/core/model_defaults.py` (nouveau), `src/core/providers/ollama_provider.py`, `src/core/llm_provider.py` ; `src/app/ui.py` (`model_menu`), `src/app/states.py`, `src/app/tabs/inference/{arena,manager}.py`, `src/app/tabs/rag/{eval,chat}.py`, `src/app/tabs/agent/crew.py`, `src/app/views/{02,03,04}_*.py` ; tests `tests/unit/test_model_defaults.py`, `tests/app/test_defaults.py`, `tests/unit/test_ui.py`, `tests/app/test_theme.py`, `tests/app/conftest.py`.

**Revue :** boucle 1 (bad_spec : juge Bonsai 1 bit) puis 23 correctifs (1 high, 11 medium, 11 low), 3 différés, 15 rejetés.

**Suivi recommandé :** false — le correctif high (`:cloud`) est couvert par un test ; aucun autre high.

**Vérification :** `pytest tests/unit tests/app` : 571 réussis ; `config/models_catalog.json`, `src/core/config.py`, `scripts/`, `benchmarks/` inchangés.

**Risques :** VRAM ignorée (la règle compare à la RAM) ; Agents : tri local d'abord qui s'écarte de la ligne « outils vérifiés d'abord » de la matrice ; défauts réels à vérifier sur les machines d'audit.
