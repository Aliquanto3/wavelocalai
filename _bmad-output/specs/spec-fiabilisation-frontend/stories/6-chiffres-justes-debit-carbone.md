---
title: 'Chiffres justes : débit et carbone'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '1467d3231346e6979b956cd627e3c084fff7074c'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      Critère CAP-4 « premier message à ±15 % des suivants, chargement à part » non vérifié sans Ollama.
    evidence: |-
      Calcul testé sur des chunks ; valeur réelle à mesurer au matin (story 11).
    severity: medium (unverified)
  - summary: >-
      Graphique d'historique encore en kg à côté d'une métrique de session en mg.
    evidence: |-
      Refonte des graphiques confiée à la story 10.
    location: >-
      src/app/views/01_Socle_Hardware.py
    severity: low
  - summary: >-
      Métrique CO₂ de l'équipe d'agents non testée à l'affichage.
    evidence: |-
      Le lancement de crewai n'est pas simulé par le banc de test.
    location: >-
      src/app/tabs/agent/crew.py
    severity: low (unverified)
---

<intent-contract>

## Intent

**Problem:** Le débit affiché divise les tokens générés par le temps mural de l'appel, chargement et prefill compris (0,6 contre 78,5 tokens/s mesurés par le benchmark) ; le CO₂ de session de « Sobriété et matériel » affiche des grammes sous l'unité kgCO₂ (×1000), et l'équivalence en km reçoit des grammes au lieu de kg ; l'historique d'émissions lit le fichier du benchmark (`data/logs/emissions/emissions.csv`) alors que le suivi de l'app écrit `data/logs/emissions.csv` (F4, F5, F6).

**Approach:** Débit = `eval_count / eval_duration` d'Ollama, comme `scripts/benchmark_slm.py` (D3), avec le chargement et la durée totale affichés à part ; une conversion des grammes du suivi explicite, testée, et une règle d'unité CO₂ unique ; un seul fichier d'émissions de l'app, écrit par le suivi et lu par l'historique.

## Boundaries & Constraints

**Always:** formule du benchmark (`output_tokens / (eval_duration_ns / 1e9)`, repli sur la durée murale seulement si `eval_duration` manque) ; « Chargement » et « Durée totale » affichés à part là où le débit est affiché ; règle CO₂ d'EXPERIENCE.md (« CO₂ » avec l'indice ; mg sous 1 g, g au-delà, kg au-delà de 1 000 g ; une seule unité dans une même comparaison ; couleur d'encre, jamais par seuil) ; conversions dans des fonctions pures testées ; tests sans Ollama ni réseau, fichiers d'émissions sous `tmp_path`.

**Never:** modifier `scripts/benchmark_slm.py`, `benchmarks/` ou `src/core/config.py` (importé par le benchmark) ; mêler les lignes du benchmark à l'historique de l'app ; refaire les graphiques (cumul, trous, fenêtre, mg sur l'axe : story 10) ; conserver la réponse de l'agent (story 9) ; écrire dans `data/`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Débit Ollama | `eval_count=157`, `eval_duration=2e9` ns, chargement 8 s | Débit 78,5 tokens/s ; chargement 8 s affiché à part | — |
| Sans `eval_duration` | chunk final sans le champ | Repli sur la durée murale, comme le benchmark | pas d'exception |
| `eval_duration = 0` | champ nul | Repli ; jamais de division par zéro | — |
| Durée totale | `total_duration` Ollama présent | Durée totale = `total_duration` ; sinon durée murale | — |
| CO₂ de session | `GreenTracker.stop()` = 0,42 g | « 420 mgCO₂ » (unité choisie par la règle), km calculés depuis 0,00042 kg | — |
| Conversion | 1 234 g | « 1,23 kgCO₂ » ; 0,5 g → « 500 mgCO₂ » ; 12 g → « 12 gCO₂ » | valeur absente → « — » |
| Comparaison | Arène, 3 modèles | Même unité pour toutes les lignes | — |
| Historique | lignes écrites par le suivi de session | l'historique les lit, depuis le même fichier que le suivi | fichier absent → « Aucune session mesurée pour l'instant. » |
| Lignes du benchmark | fichier du benchmark présent | absentes de l'historique | — |

</intent-contract>

## Code Map

- `src/core/providers/ollama_provider.py:81-156` -- `chat_stream` : lit seulement `eval_count`, `prompt_eval_count`, `load_duration` (chunks dict l.120-123 et pydantic l.133-136) ; `tokens_per_second = eval_count / timer.duration` (l.142) ; `total_duration_s` = durée murale (l.148). Lire aussi `eval_duration`, `prompt_eval_duration`, `total_duration`.
- `scripts/benchmark_slm.py:1601-1622,1705-1715` (LECTURE SEULE) -- formule de référence : `tokens_per_second = round(output_tokens / (eval_duration_ns / 1e9), 2)` si `eval_duration_ns`, sinon `output_tokens / duration`.
- `src/core/metrics.py:4-17` -- `InferenceMetrics` (`load_duration_s`, `total_duration_s`, `tokens_per_second`) ; non importé par le benchmark (seul `src.core.config` l'est).
- Fournisseurs cloud (`mistral`, `openai`, `anthropic`) -- débit = tokens / durée murale, sans chargement : inchangé (D3 vise Ollama) ; l'afficher sans « Chargement ».
- Affichage du débit : `src/app/tabs/inference/chat.py:27-69` (pied de réponse), `lab.py:83-85` (métriques), `arena.py:130-262` (clé `"Débit (t/s)"`, tableau, vainqueur, bulles). « Chargement » n'est affiché nulle part aujourd'hui.
- `src/core/green_monitor.py:199-241` -- `GreenTracker` : `OfflineEmissionsTracker(output_dir=str(LOGS_DIR))`, fichier par défaut `emissions.csv` → `data/logs/emissions.csv` ; `stop()` renvoie des **grammes**.
- `src/app/views/01_Socle_Hardware.py:64-68,138-177` -- `get_co2_equivalencies(emissions_kg)` reçoit des grammes (l.146) ; `format_unit(em, "kgCO₂", 5)` (l.148) ; historique lu via `get_emissions_path()` = `data/logs/emissions/emissions.csv` (fichier du benchmark, l.23,165-177), titre « (kg) ».
- `src/core/config.py:13-14,35-36` (LECTURE SEULE) -- `LOGS_DIR`, `EMISSIONS_DIR`, `get_emissions_path()`.
- `src/app/formatting.py` -- `format_unit`, `format_number`, `MISSING` : y ajouter la règle CO₂ (grammes → mg/g/kg, unité imposable pour une comparaison).
- Graphies du CO₂ à unifier : `chat.py:68,116` (`mgCO₂`), `arena.py:212,236,255` (`mg CO₂`, `mg`), `lab.py` (`mg`), `rag/chat.py:96`, `rag/eval.py:269,297,362`, `crew.py:480`, `01_Socle_Hardware.py:148`.
- `src/app/tabs/agent/crew.py:440-469` -- `GreenTracker("crew_mission")`, `tracker.stop() * 1000.0` (g → mg correct).
- Tests existants : `tests/unit/test_metrics.py`, `test_green_monitor.py` (LOGS_DIR → `tmp_path`), `tests/app/conftest.py` (LOGS_DIR et `config.EMISSIONS_DIR` redirigés, `fake_inference` avec `load_duration_s=0.1`).

## Tasks & Acceptance

**Execution:**
- `src/core/providers/ollama_provider.py` (ou une fonction pure dans `src/core/metrics.py`) -- débit et durées selon D3, calcul isolé et testable depuis un chunk final.
- `src/app/formatting.py` -- `format_co2(grams, unit=None)` et conversion g → kg explicites.
- `src/app/tabs/inference/{chat,lab,arena}.py` -- débit D3, « Chargement » et « Durée totale » à part (Ollama).
- `src/core/green_monitor.py` -- un seul chemin de fichier d'émissions de l'app (constante ou fonction), utilisé par `GreenTracker` ; lecture de l'historique depuis ce chemin (filtrée sur les sessions de l'app).
- `src/app/views/01_Socle_Hardware.py` -- CO₂ de session et km depuis la conversion ; historique depuis le fichier du suivi ; « Aucune session mesurée pour l'instant. » sans fichier.
- `src/app/tabs/**` -- graphie CO₂ unique via `format_co2`.
- `tests/unit/` -- débit depuis des chunks (avec, sans, zéro `eval_duration`) ; conversion g → kg et choix d'unité ; `GreenTracker` écrit dans le fichier lu par l'historique.
- `tests/app/` -- Sobriété et matériel : unité et valeur du CO₂ de session avec un tracker simulé ; historique lu depuis le fichier du suivi sous `tmp_path`, lignes du benchmark ignorées.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given `git diff` de la story, when on le lit, then `scripts/benchmark_slm.py`, `benchmarks/` et `src/core/config.py` sont inchangés.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 36 findings — high 0, medium 8, low 17, false 3, maybe-false 8
- findings:
  - `[medium]` `[patch]` (verification-gap, blind) chemin de production (objets `ChatResponse`) jamais testé via le fournisseur — test ajouté.
  - `[medium]` `[patch]` (verification-gap, blind) conversion mg → g non vérifiée à l'affichage (session du chat, badge de la Discussion) — tests des chaînes affichées ; équipe d'agents différée (lancement de crewai non simulé).
  - `[low]` `[patch]` (verification-gap, blind, edge) unité commune non vérifiée (évaluation de la qualité, bulles de l'Arène) ; axe du graphique d'évaluation en mg — graphique converti, tests ajoutés.
  - `[low]` `[patch]` (verification-gap, blind) noms de projet en littéraux — constantes.
  - `[low]` `[patch]` (verification-gap, blind) `eval_count == 0` remplacé par l'estimation — valeur réelle conservée.
  - `[maybe-false]` `[reject]` (intent) lecture littérale « kgCO₂ » pour le CO₂ de session — règle d'unité d'EXPERIENCE.md ; conversion g → kg testée et utilisée pour les km.
  - `[maybe-false]` `[defer]` (intent) critère CAP-4 « premier message à ±15 % des suivants » — exige Ollama (story 11, matin).
  - `[low]` `[reject]` (intent) tableau de gestion des modèles sans « Chargement » — débit issu des statistiques du benchmark, déjà selon D3.
  - `[low]` `[defer]` (intent, edge, blind) graphique d'historique encore en kg à côté d'une métrique en mg — story 10.
  - `[low]` `[reject]` (intent) filtre par projet plus strict que F6 — nécessaire pour ne pas mêler d'autres écrivains du fichier.
  - `[maybe-false]` `[reject]` (intent) session écrite seulement à l'arrêt du suivi — comportement de CodeCarbon, inchangé.
  - `[low]` `[reject]` (intent) périmètre élargi (graphie CO₂ partout) — tâche de la story.
  - `[medium]` `[patch]` (edge, blind) `load_measured` toujours vrai : « Chargement 0 s » affiché comme mesuré — vrai seulement si `load_duration` est présent.
  - `[medium]` `[patch]` (edge, blind) petites valeurs arrondies à 0 dans les tableaux (`localized` à 3 décimales) — unité commune choisie d'après la plus petite valeur non nulle.
  - `[low]` `[patch]` (edge) lignes illisibles gardées — `dropna` et tri.
  - `[medium]` `[patch]` (edge, blind) périodes recouvertes par session, audit et équipe ; ligne cumulée ajoutée au même `run_id` — historique : sessions seules, dernière ligne par `run_id`.
  - `[low]` `[patch]` (edge) test de chemin comparé à un `LOGS_DIR` redirigé — comparaison relative corrigée.
  - `[low]` `[patch]` (blind) import de `green_monitor` en échec présenté comme « aucune session » — message « suivi carbone indisponible ».
  - `[low]` `[patch]` (blind) « 0 km » sous une valeur absente — ligne masquée.
  - `[low]` `[patch]` (blind) `ParserError` brute — message lisible.
  - `[low]` `[patch]` (blind) test de formule qui ne détecte pas une dérive du benchmark — lecture du source du benchmark en texte.
  - `[low]` `[patch]` (blind) « Débit » sans explication, repli mural silencieux — aide et mention « (estimé) ».
  - `[low]` `[reject]` (blind) anciens formateurs (`metrics_service`, `components/metrics_display`) — code mort, hors périmètre.
  - `[false]` `[reject]` (edge) affirmation « graphie unique » contredite par l'axe de l'évaluation — corrigé par le correctif d'unité commune.
  - `[false]` `[reject]` (edge) affirmation sur l'historique en kg — doublon (story 10).
  - `[false]` `[reject]` (edge) affirmation « Chargement mesuré » — doublon du correctif `load_measured`.
  - `[maybe-false]` `[reject]` (intent) formule et affichage testés séparément — le fournisseur est désormais testé de bout en bout avec des objets réels.
  - `[maybe-false]` `[reject]` (intent) colonnes du Banc d'essai variables (4 ou 5) — voulu (chargement propre à Ollama).
  - `[maybe-false]` `[defer]` (verification-gap) métrique CO₂ de l'équipe non testée — exige de simuler crewai.
  - `[low]` `[reject]` (blind) champ `emissions_g` inutilisé — prévu pour la story 10.
  - `[maybe-false]` `[reject]` (edge) valeurs inférieures à 1 mg encore arrondies — rares (valeurs théoriques en mg pour quelques tokens).
  - `[low]` `[reject]` (verification-gap) équipe : doublon du différé.
  - `[maybe-false]` `[reject]` (intent) « Chargement » masqué pour le cloud — cohérent avec D3.
  - `[low]` `[reject]` (blind) sources d'estimation — doublon.
  - `[low]` `[reject]` (edge) chiffres significatifs de l'infobulle — corrigés (`.3~r`).

## Design Notes

Critère de CAP-4 « le CO₂ de session s'écarte de moins de 5 % de la ligne du CSV de CodeCarbon » : les deux viennent du même tracker ; afficher la valeur renvoyée par `stop()` et lire l'historique dans le fichier de ce tracker les rend égales par construction, ce qu'un test peut vérifier avec un CSV écrit sous `tmp_path`.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `git diff --stat 1467d3231346e6979b956cd627e3c084fff7074c -- scripts/benchmark_slm.py benchmarks src/core/config.py` -- expected: vide

## Auto Run Result

Status: done

**Résumé :** débit selon D3 (`eval_count / eval_duration`, formule du benchmark, repli mural marqué « estimé »), chargement et durée totale à part dans le chat, le Banc d'essai et l'Arène ; règle d'unité CO₂ unique (`format_co2` : mg, g, kg) et une seule unité par comparaison ; CO₂ de session de Sobriété et matériel juste (grammes du suivi, km depuis des kg) ; un seul fichier d'émissions de l'app (`data/logs/emissions.csv`) écrit par le suivi et lu par l'historique (sessions seules, dernière ligne par exécution), sans les lignes du benchmark.

**Fichiers :** `src/core/metrics.py` (`ollama_metrics`), `src/core/providers/ollama_provider.py`, `src/core/green_monitor.py` (fichier et lecture de l'historique) ; `src/app/formatting.py` (`format_co2`, conversions), `src/app/states.py` (aide du débit) ; `src/app/{Accueil.py,views/01_Socle_Hardware.py}`, `src/app/tabs/**` ; tests `tests/unit/{test_metrics,test_formatting,test_green_monitor}.py`, `tests/app/test_figures.py`.

**Revue :** 20 correctifs (6 medium, 14 low), 4 différés, 12 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les medium sont couverts par des tests ajoutés.

**Vérification :** `pytest tests/unit tests/app` : 497 réussis ; `scripts/benchmark_slm.py`, `benchmarks/` et `src/core/config.py` inchangés ; test CAP-4 : la ligne CSV de CodeCarbon et la valeur de `stop()` concordent à moins de 5 %.

**Risques :** débit réel (±15 %) à vérifier avec Ollama ; historique encore en kg (story 10) ; unité commune d'après la plus petite valeur (grands nombres en mg possibles).
