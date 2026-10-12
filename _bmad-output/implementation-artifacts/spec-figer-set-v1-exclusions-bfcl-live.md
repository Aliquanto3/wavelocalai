---
title: 'Figer set-v1 : exclusion versionnée des 5 cibles bfcl-live défectueuses'
type: 'chore'
created: '2026-10-12'
status: 'in-progress'
route: 'dispatch'
baseline_commit: '89c93318c43bb5999e9fedd31e5c21bfa47b5069'
review_loop_iteration: 0
context:
  - '{project-root}/scripts/quality_bench/questions/SOURCES.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `set-v1` n'est pas encore figé : 5 cibles `bfcl-live` sont défectueuses dans BFCL lui-même (aucune réponse ne peut les passer) et peuvent être tirées. Anaël a relu et validé les questions privées et de rédaction ; il reste à exclure ces cibles, construire le jeu et versionner son index.

**Approach:** Ajouter au YAML de jeu une liste d'exclusion facultative par source (`exclude`, identifiants de questions), contrôlée au chargement et à l'assemblage, la renseigner dans `set-v1.yaml` pour les 5 cibles, puis lancer `build-set --set set-v1` deux fois (empreintes identiques) et commiter seulement `benchmarks/quality/sets/set-v1/index.jsonl`.

Décisions d'Anaël :
- Exclure de `set-v1` `live_simple_106-63-0`, `live_simple_112-68-0`, `live_multiple_507-149-4`, `live_multiple_862-181-3`, `live_multiple_964-207-0` (questions `tools/bfcl-live/0107`, `0113`, `0766`, `1121`, `1223` à la révision épinglée) par une liste versionnée et testée, jamais par édition des données.
- `tools-fr` : garder telles quelles les 3 questions dont la valeur attendue n'apparaît plus dans le prompt traduit (difficulté acceptée).
- Retirer de `deferred-work.md` les entrées tranchées : ces deux-là, identifiants M-IFEval FR (story 3), contrat outils à un seul tour (story 4), panne d'Ollama comptée comme essai (story 1).

## Boundaries & Constraints

**Always:** exclusion appliquée aux candidats de la source avant le tirage ; cœur `assemble` pur et déterministe ; journaux sans contenu de question privée ; tests sans réseau, sans Ollama ni fichier de `data/` ; textes et commit en français.

**Never:** éditer `candidates.jsonl`, les fichiers privés ou l'importeur BFCL ; commiter `questions.jsonl`, `tracks.json`, une question privée ou un échantillon de relecture ; toucher `scripts/benchmark_slm.py` ou `.venv` ; pousser sur `master`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Exclusion | `exclude: [tools/bfcl-live/0107, …]` sur `bfcl-live`, ids présents parmi les candidats | Aucun id exclu dans le jeu ; effectifs inchangés | N/A |
| Id exclu absent | id de `exclude` absent des candidats de la source | Rien n'est écrit | `SetBuildError` qui nomme la source et l'id, code 1 |
| YAML invalide | `exclude` non-liste, élément non-chaîne ou vide, doublon | Rien n'est lu plus loin | `ConfigError` qui nomme `sources[i].exclude`, code 2 |
| Sans exclusion | clé absente | Comportement actuel inchangé (même empreinte qu'avant pour un YAML sans `exclude`) | N/A |

</frozen-after-approval>

## Code Map

- `scripts/quality_bench/common/config.py` -- `_SET_SOURCE_KEYS` (l. 303), `SetSource` (l. 317), `_set_source` (l. 340) : ajouter `exclude: tuple[str, ...]` (défaut vide), validé comme les autres champs.
- `scripts/quality_bench/questions/set_builder.py` -- `assemble` (l. ~190) : filtrer `candidates` par `entry.exclude` avant `taken_groups` ; refuser un id exclu absent. Docstring du module à compléter.
- `scripts/quality_bench/sets/set-v1.yaml` -- entrée `bfcl-live` : ajouter `exclude` (5 ids) avec un commentaire qui donne l'id BFCL de chacun et la raison.
- `tests/quality_bench/set_factories.py` -- `synthetic_candidates` : ajouter aux candidats de chaque source les questions de `entry.exclude` (numéro tiré du suffixe de l'id), pour que le vrai `set-v1.yaml` s'assemble.
- `tests/quality_bench/test_config.py` -- `test_load_set_refuses_invalid_yaml` / `test_load_set_refuses_malformed_values` (paramétrés), `test_real_set_v1_loads` : cas `exclude`.
- `tests/quality_bench/test_set_builder.py` -- `test_set_v1_composition`, `assembled` : vérifier la liste exacte et l'absence des ids exclus ; nouveau test d'id absent.
- `scripts/quality_bench/questions/SOURCES.md` (l. 158) -- format du YAML : ajouter `exclude?`.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les 5 entrées tranchées.
- Données : candidats réels sous `data/quality_bench/sources/<s>/candidates.jsonl`, fichiers privés sous `data/quality_bench/private/` (ne pas modifier) ; sorties `data/quality_bench/sets/set-v1/` et `benchmarks/quality/sets/set-v1/index.jsonl`.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/common/config.py` -- clé `exclude` facultative : liste de chaînes non vides et uniques -> `SetSource.exclude` -- liste versionnée et validée.
- [x] `scripts/quality_bench/questions/set_builder.py` -- appliquer et contrôler l'exclusion dans `assemble` ; journaliser le nombre d'exclusions par source dans `load_candidates` ou `prepare_set` -- exclusion avant tirage, refus d'un id inconnu.
- [x] `scripts/quality_bench/sets/set-v1.yaml` -- `exclude` des 5 ids sur `bfcl-live` -- décision d'Anaël.
- [x] `tests/quality_bench/set_factories.py`, `test_config.py`, `test_set_builder.py` -- couvrir la matrice ci-dessus et la liste exacte de `set-v1` -- liste testée.
- [x] `scripts/quality_bench/questions/SOURCES.md` -- documenter `exclude`.
- [x] Construction réelle : `build-set --set set-v1`, noter les empreintes, déplacer les deux dossiers produits vers le scratchpad, relancer, comparer les empreintes (jeu, `questions.jsonl`, `tracks.json`, `index.jsonl`) ; vérifier que les 5 ids sont absents de l'index.
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les 5 entrées tranchées.
- [x] Commit `Feat:` sur `feat/quality-bench-suite` : code, tests, YAML, docs, spec, `deferred-work.md` et `benchmarks/quality/sets/set-v1/index.jsonl` seul.

**Acceptance Criteria:**
- Given le vrai `set-v1.yaml`, when on le charge, then `bfcl-live.exclude` vaut exactement les 5 ids décidés.
- Given deux `build-set --set set-v1` successifs, when on compare les journaux, then l'empreinte du jeu et les trois empreintes de fichiers sont identiques.
- Given l'index commité, when on le lit, then 800 lignes `qb.set_index/1`, aucune des 5 questions exclues, aucune ligne privée avec `prompt_hash` ou `target_hash`.
- Given le commit, when on liste ses fichiers, then aucun `questions.jsonl`, `tracks.json`, fichier privé ni échantillon de relecture.

## Design Notes

Ids de questions plutôt qu'ids BFCL : la clé reste générique (toute source), et l'id d'une question est stable à révision épinglée. Le commentaire du YAML garde la correspondance avec les ids BFCL. Un id exclu absent des candidats est une erreur (faute de frappe, ou renumérotation après changement de révision) plutôt qu'un filtre silencieux.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` -- expected: tout passe.
- `.venv-quality\Scripts\python -m ruff check scripts/quality_bench tests/quality_bench` et `black --check` sur les fichiers touchés -- expected: propre.
- `.venv-quality\Scripts\python -m scripts.quality_bench build-set --set set-v1` (deux fois) -- expected: code 0, empreintes identiques.
