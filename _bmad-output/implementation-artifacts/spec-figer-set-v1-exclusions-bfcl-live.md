---
title: 'Figer set-v1 : exclusion versionnée des 5 cibles bfcl-live défectueuses'
type: 'chore'
created: '2026-10-12'
status: 'done'
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

## Implementation Notes

- Construction réelle du 2026-10-12 (deux fois, dossiers déplacés au scratchpad entre les deux) : empreinte du jeu `7fb574ec6082a19c576af6066d14bfe9f2e5ffb911f7f794db5c666d0d0ee5dc`, `index.jsonl` `90f21ec540fdf0894c34acdfd7e26dcd5bc8fe06e133f0c1fb660d1dd0fdc990`, identiques aux deux passes. Index : 800 lignes, 180 privées sans `prompt_hash` ni `target_hash`, aucun des 5 ids exclus.
- Correspondance id de question → id BFCL vérifiée sur les vrais candidats (`grader.params.bfcl_id`) ; aucune question `tools-fr` n'est dérivée d'une des 5 cibles (`derived_from`).
- `core.autocrlf=true` sur la tour, sans `.gitattributes` : le blob commité est en LF, mais un checkout Windows neuf réécrit l'index en CRLF (empreinte sur disque différente).

## Review Triage Log

| # | Constat (relecteur) | Verdict | Preuve / route |
|---|---|---|---|
| 1 | L'index manque au diff relu (blind) | false | Exclu volontairement du diff de relecture (800 lignes d'empreintes générées) ; commité dans cfa7713 et audité à part : 800 lignes, 0 id exclu, 180 privées sans hash. |
| 2 | Empreintes non consignées dans la spec (blind) | low | Rejeté (correctif = éditer la spec) ; consignées malgré tout dans Implementation Notes. |
| 3 | Une traduction `tools-fr` d'une cible exclue contournerait l'exclusion (blind, edge, verification) | low | Réel en théorie, absent aujourd'hui (0 `derived_from` vers les 5 ids) ; set-v1 s'écrit une fois. Correctif = garde supplémentaire sur les groupes : rejeté (peu probable, ajoute une branche). |
| 4 | Journal « N questions exclues » écrit avant le contrôle de présence (blind, edge) | low | patch : libellé « identifiants à exclure ». |
| 5 | `test_exclusion_applies_before_the_draw` prend tous les candidats, aucun vrai tirage (blind) | low | patch : effectif bien inférieur au disponible. |
| 6 | Id entouré d'espaces ou d'une autre source : code 1 au lieu de 2 (blind) | low | Rejeté : le message nomme la source et l'id fautif ; correctif = gardes de format supplémentaires. |
| 7 | Entrées retirées de `deferred-work.md` sans trace (blind) | false | Retrait décidé par Anaël (bloc figé, « entrées tranchées ») ; l'historique git garde le texte. |
| 8 | Correspondance id ↔ id BFCL vérifiée à la main seulement (blind) | low | Rejeté : un test exigerait `data/` (interdit) ; vérifiée à la construction (Implementation Notes). |
| 9 | `SOURCES.md` ne dit pas que `review-sample` applique `exclude` (blind) | low | patch : une incise. |
| 10 | Fabrique : id reconstruit non comparé à l'id du YAML (blind, edge) | low | patch : assertion d'égalité. |
| 11 | La CI ne lance pas `tests/quality_bench` (verification) | medium | defer, antérieur : déjà suivi dans `deferred-work.md` (entrée de la story 1), pas de doublon ajouté. |
