---
title: 'Un jeu fixe de cas garde le juge honnête'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '75cbda1'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-7-1.md'
warnings:
  - 'Story mixte (décision Q4) : les verdicts attendus du jeu fixe sont proposés par la story, pas relus. La relecture humaine revient à Anaël (section « Relecture humaine »), sans bloquer le reste de l''Epic 7 côté code.'
deferred:
  - summary: >-
      Écart nouveau non couvert par les critères, variante la plus conservatrice gardée. (1) La décision Q4 (B) veut des verdicts « produits par un modèle cloud fort, relus par Anaël » et `epics.md` des cas « tirés d'un document du domaine public » : la consigne du run interdit tout appel payant et tout contenu qui ne soit pas inventé pour le dépôt. Les douze cas sont donc **inventés** et les verdicts attendus **proposés par la story elle-même** (Sonnet), à relire par Anaël ; aucun modèle cloud n'a été appelé. Un jeu tiré d'un document du domaine public reste possible plus tard (même format `cases.json`). (2) Le test de non-régression rejoue des sorties de juge **dérivées des verdicts attendus** (`judge-replay.json`, écrit par `record`), pas des sorties d'un vrai modèle enregistrées : il prouve que le code (invites, découpage, lecture, notes) rend les notes attendues, et il échoue si l'invite, le schéma ou le découpage changent (empreinte de l'invite). Il ne prouve pas que les verdicts attendus sont justes (c'est la relecture) ni qu'un vrai juge s'y accorde (le test `integration`). (3) Le seuil `minimum_agreement` (0,65 pour les verdicts et pour les extraits utiles) est fixé sur deux mesures du juge `qwen2.5:1.5b` à 72 et 75 % de verdicts identiques ; il vaut garde-fou contre un effondrement, pas objectif : il est révisable après la relecture, et le test `integration` n'échoue pas dessous (avertissement ; `WAVELOCALAI_JUDGE_STRICT=1` le rend bloquant). (4) La pertinence n'est pas mesurée avec un vrai juge (elle dépend d'un modèle d'embedding) : elle est rejouée avec un embedding déterministe de test (instantané, pas une annotation).
    evidence: |-
      `tests/v2/fixtures/eval/{cases,judge-replay}.json`, `tests/v2/eval_fixed_set.py`, `tests/v2/unit/test_eval_fixed_set.py`, `tests/v2/integration/test_eval_fixed_set_ollama.py`.
    location: tests/v2/fixtures/eval/cases.json
    severity: medium
  - summary: >-
      Constat de la première mesure : le juge `qwen2.5:1.5b` n'est **pas meilleur qu'un juge qui répondrait toujours « appuyée »** sur ce jeu (75 % de verdicts identiques contre 31/40 = 78 %) : tous ses écarts (10 à 11 sur 40) sont des « contredite » rendus pour une affirmation appuyée ou non appuyée : il voit des contradictions là où il n'y en a pas, et ne distingue pas « non appuyée » de « contredite ». Les notes de fidélité d'un juge de cette taille sont donc à peine informatives (écart moyen de 18 à 21 points avec la note attendue). L'avertissement « note peu fiable » sous ~4 B actifs (D-27, écran 7.3) est justifié ; un juge plus gros est à mesurer avec le même outil (`measure --model`) avant de le proposer comme défaut `judge`. Non traité ici : la 7.2 garde le juge, elle ne le règle pas (réglage des invites ou du modèle par défaut à décider après la relecture).
    evidence: |-
      Sortie de `python -m tests.v2.eval_fixed_set measure` (deux fois) et de `test_eval_fixed_set_ollama.py` : voir « Rapport de dev ».
    location: src/wavelocalai/evaluation/prompts.py
    severity: medium
  - summary: >-
      Refactorisation en passant, à relire : le calcul des trois notes (méthodes `_faithfulness`, `_relevance`, `_precision` du service) est sorti dans `evaluation/metrics.py` (fonctions qui prennent un juge et un embedding sous forme de fonctions), pour que le jeu fixe rejoue **le code livré** et non une copie ; le service les appelle par `functools.partial`. Comportement inchangé (`test_eval_api.py` et `test_eval_scoring.py` verts sans modification), sauf l'ajout des phrases de troncature dans `reason`. `Metric` et les raisons « non évalué » propres aux notes (`NOT_EVALUATED_NO_CLAIM`, `_NO_QUESTION`, `_EMBEDDING`) vivent désormais dans `metrics.py` ; `service.py` garde `_TIMEOUT` et `_FAILED`. Aucun code d'erreur ajouté à `errors.py` (rien n'est levé : un jeu de test ne crée pas d'erreur d'API).
    evidence: |-
      `git diff 75cbda1 -- src/wavelocalai/evaluation/service.py` ; `src/wavelocalai/evaluation/metrics.py`.
    location: src/wavelocalai/evaluation/metrics.py
    severity: low
---

# Story 7.2 : un jeu fixe de cas garde le juge honnête

## Objectif

Un mainteneur rejoue à chaque changement du juge (invite, découpage, modèle) un jeu fixe de questions, d'extraits, de réponses et de verdicts attendus : une régression de la notation se voit avant la démo. Le code livré est rejoué sans modèle (test unitaire) ; un vrai juge local est mesuré contre le même jeu (test `integration`).

## Critères d'acceptation et preuves

1. **Jeu fixe** de douze cas en français dans `tests/v2/fixtures/eval/cases.json`, **inventés pour le dépôt** (aucun document client, aucune réponse RAG réelle, rien de `data/`) : question, extraits numérotés, réponse, affirmations avec verdict attendu et extrait d'appui, extraits utiles. Couvre les trois verdicts, un chiffre faux, une négation inversée, une connaissance générale non appuyée, des marqueurs `[1]`, des affirmations impliquées, une réponse sans affirmation (fidélité « non évaluée », jamais 0), un vrai 0, plus de 10 affirmations, un seul extrait utile sur quatre. Preuve : `test_eval_fixed_set.py::test_the_set_has_about_a_dozen_cases_...`, `::test_every_expected_verdict_points_at_an_existing_extract`.
2. **Non-régression avec sorties de juge rejouées** : les scores et verdicts calculés par le code du service (`evaluation/metrics.py`) égalent les attendus (fidélité, précision du contexte, verdicts avec leur extrait d'appui ; pertinence : instantané avec un embedding déterministe). Une modification de l'invite, du schéma de sortie ou du découpage change l'empreinte de l'invite ou la note : le test échoue en disant quoi réenregistrer. Preuve : `::test_the_replayed_scores_and_verdicts_equal_the_expected_ones[*]`, `::test_a_changed_prompt_is_not_replayed_...`, `::test_another_cut_of_the_claims_changes_the_replayed_score`, `::test_a_changed_verdict_changes_the_replayed_score`, `::test_the_replay_file_matches_the_cases`.
3. **Report de la 7.1 : une réponse coupée ou plafonnée le dit** : une réponse de plus de 12 000 caractères (les trois notes) ou de plus de 10 affirmations (la fidélité) l'écrit dans sa `reason` (« Réponse tronquée à 12 000 caractères pour le juge : notée sur son début. », « Notée sur les 10 premières affirmations sur N. »). Consigné dans `contrat-api.md`. Preuve : `::test_a_very_long_answer_says_in_every_reason_that_it_was_cut`, `::test_more_than_ten_claims_say_how_many_were_left_out`, `::test_only_the_first_ten_claims_are_verified_and_the_reason_says_so`.
4. **Accord d'un vrai juge, mesuré et consigné** : part de verdicts identiques (chaque affirmation attendue est donnée telle quelle au juge), d'extraits d'appui et d'extraits utiles identiques, écart moyen de fidélité de bout en bout, avec le repère d'un juge qui répondrait toujours pareil. Seuil minimal `minimum_agreement` dans `cases.json` (0,65 et 0,65, voir `deferred`) ; sous le seuil, un avertissement (bloquant avec `WAVELOCALAI_JUDGE_STRICT=1`). Mesure : `python -m tests.v2.eval_fixed_set measure --model <tag>` ou `tests/v2/integration/test_eval_fixed_set_ollama.py -s`. Preuve : `test_eval_fixed_set_ollama.py` (vrai Ollama), `test_eval_fixed_set.py::test_a_judge_that_agrees_with_the_set_scores_full_agreement`, `::test_a_lenient_judge_agrees_only_on_the_supported_claims`, `::test_an_unusable_judge_output_is_never_an_agreement`, `::test_a_model_used_as_judge_gives_its_text_or_the_reason_it_could_not`.
5. **Relecture humaine tracée sans être inventée** : `cases.json` porte `review` (par cas : `proposed`, `confirmed`, `corrected` ; au niveau du fichier : `reviewed_by`, `reviewed_on`) ; tous les cas sont `proposed` et `reviewed_by` est vide. Un cas marqué relu sans relecteur signé fait échouer le test. Preuve : `::test_the_review_state_is_declared_and_never_claims_a_human_review_nobody_made`.

## Hors périmètre

Réglage des invites ou du juge par défaut, mesure de la pertinence avec un vrai embedding, jeu tiré d'un document du domaine public, appel d'un modèle cloud, intégration à la CI (le test `integration` reste local, comme les autres).

## Règles écrites

- **Un jeu de test ne touche ni `data/` ni le réseau** : seul le test `integration` parle à Ollama local, avec un modèle déjà installé, rien n'est téléchargé.
- **Les verdicts attendus s'éditent dans `cases.json` seul** ; `judge-replay.json` s'en déduit par `python -m tests.v2.eval_fixed_set record` (un test vérifie qu'il est à jour).
- **Le jeu rejoue le code du service** (`evaluation/metrics.py`), jamais une copie.

## Notes de développement

- `evaluation/metrics.py` (nouveau : `faithfulness`, `relevance`, `context_precision`, `Metric`, phrases de troncature) ; `prompts.py` (`read_claims` rend aussi le total d'affirmations, `answer_is_cut`) ; `service.py` (délègue à `metrics`).
- `tests/v2/eval_fixed_set.py` : chargement, attendus, sorties de référence, `ReplayJudge`, `HashingEmbedder`, `ModelAsker`, `measure`, ligne de commande `record` et `measure`.
- `contrat-api.md` : deux puces ajoutées à la sous-section « Évaluation (story 7.1) ».

## Fichiers

- `src/wavelocalai/evaluation/metrics.py` (nouveau), `prompts.py`, `service.py`
- `tests/v2/fixtures/eval/{cases.json,judge-replay.json,README.md}`, `tests/v2/eval_fixed_set.py`, `tests/v2/unit/test_eval_fixed_set.py`, `tests/v2/integration/test_eval_fixed_set_ollama.py` (nouveaux)

## Relecture humaine

**À relire par Anaël (prérequis de l'Epic 7, décision Q4), environ 30 minutes** : `tests/v2/fixtures/eval/cases.json`, douze cas, 40 verdicts. Procédure complète dans `tests/v2/fixtures/eval/README.md`. En bref :

1. Pour chaque affirmation (`claims`) : le `verdict` attendu est-il juste (`appuyée` = un extrait l'implique, `contredite` = un extrait dit le contraire, `non appuyée` = aucun extrait ne permet de conclure, même si c'est vrai dans le monde réel) et `support` est-il le bon extrait ? Pour chaque cas : `useful` (les extraits qui servent à répondre) est-il juste ?
2. Corriger dans `cases.json`, passer `review` du cas à `"confirmed"` ou `"corrected"`, puis renseigner `review.status`, `reviewed_by` et `reviewed_on`.
3. `python -m tests.v2.eval_fixed_set record`, relire le diff de `judge-replay.json`, lancer `pytest tests/v2/unit/test_eval_fixed_set.py`, commiter.
4. Optionnel : `python -m tests.v2.eval_fixed_set measure` pour une nouvelle mesure sur des verdicts relus, et réviser `minimum_agreement`.

Les verdicts les plus discutables : `sauvegarde-frequence`, `jardin-partage`, `frais-repas-negation`, `mediatheque-pret`, `chantier-fin-de-journee`. **Rien n'est validé tant que `reviewed_by` est vide** ; la relecture n'est consignée nulle part ailleurs.

## Rapport de dev

Ciblé (poste partagé : ni `tests/v2` complet ni E2E). `test_eval_fixed_set.py` : 28 verts ; `test_eval_scoring.py` et `test_eval_api.py` : 51 verts après la refactorisation (inchangés) ; `test_layers.py` verts. Intégration sur le vrai Ollama (`qwen2.5:1.5b` juge, 12 cas, 40 verdicts) : verdicts identiques 29 à 30 sur 40 (72 à 75 %), contre 31/40 pour un juge qui répondrait toujours « appuyée » ; extraits d'appui identiques 26 à 28 sur 36 ; extraits utiles identiques 23 sur 31 (74 %) ; écart moyen de fidélité de bout en bout 18 à 21 points (11 cas notés) ; aucune sortie invalide. Tous les écarts de verdict vont vers « contredite ». Contrôle rapide propre.

## Point pour Anaël : juge par défaut non informatif (à trancher, non tranché par la revue)

Le juge par défaut `qwen2.5:1.5b` est **non informatif sur ce jeu** : 29 à 30 verdicts identiques sur 40 (72 à 75 %, trois mesures dont celle de la revue), contre 31/40 (78 %) pour un juge qui répondrait toujours « appuyée ». Ses écarts vont tous vers « contredite ». Sur les extraits utiles, il fait mieux que le juge trivial (23/31 contre 16/31). La mesure l'écrit désormais (« juge non informatif ») et le test `integration` avertit (échoue avec `WAVELOCALAI_JUDGE_STRICT=1`).

Décisions à prendre : (a) garder `qwen2.5:1.5b` comme juge par défaut avec l'avertissement « note peu fiable » (D-27), ou en proposer un plus gros mesuré ; (b) règle de la garde : variante conservatrice écrite ici, **avertir par défaut, échouer en mode strict**, la garde exigeant un accord ≥ `minimum_agreement` **et** strictement meilleur que le juge trivial ; à durcir (échec par défaut) si le test `integration` entre un jour dans une campagne de mesure ; (c) réviser `minimum_agreement` (0,65) après relecture des verdicts.

Mesurer un autre juge (installé, rien n'est téléchargé) :

```
$env:PYTHONUTF8 = "1"
.venv\Scripts\python -m tests.v2.eval_fixed_set measure --model <tag> [--host http://127.0.0.1:11434]
```

ou, pour le juge du test : `.venv\Scripts\python -m pytest tests/v2/integration/test_eval_fixed_set_ollama.py -m integration -s` (ajouter `$env:WAVELOCALAI_JUDGE_STRICT = "1"` pour rendre la garde bloquante).

## Revue

Revue Opus (une passe), sur la base `origin/feat/v2-evaluation-serveur` fusionnée. Branchement vérifié : le service appelle `metrics.faithfulness`, `relevance` et `context_precision` (rien d'autre n'importait les noms déplacés), les phrases de troncature passent par le vrai service. Aucun appel réseau hors du test `integration` ; CI inchangée (le test `integration` n'y est pas joué).

- medium · second avis 1 · **corrigé** · seuil 0,65 sous le repère « toujours appuyée » (78 %) : la garde comparait l'accord à un seuil absolu seulement. Ajout de `Agreement.shortfalls` (seuil **et** juge trivial : verdict le plus fréquent, « tous utiles » / « aucun utile »), « juge non informatif » dans le résumé et la sortie de `measure`, test `integration` qui avertit ou échoue en strict ; règle écrite pour Anaël ci-dessus. Mesure réelle rejouée : 30/40 contre 31/40, avertissement « non informatif » émis. Tests unitaires ajoutés (juge d'accord, juge indulgent = juge trivial, juge « tous utiles », sorties invalides).
- low · second avis 2 · **rejeté** · `expected_precision` et `expected_faithfulness` passent par `scoring` : les formules ont leurs tests à valeurs littérales dans `test_eval_scoring.py` (un mutant de `percent` ou `context_precision` y échoue), et le jeu porte des littéraux (0, 80, 89, 100) ; des notes littérales dans `cases.json` seraient à recalculer à la main à chaque relecture des verdicts.
- low · second avis 3 · **corrigé** · garde de relecture : `reviewed_on` vide sans relecteur, date ISO (AAAA-MM-JJ) sinon, et plus aucun cas ni statut `proposed` une fois la relecture signée.
- low · second avis 4 · **rejeté** · la coupe d'une affirmation à 400 caractères et l'écart des questions au-delà des trois demandées ne réduisent pas ce que le juge voit de la réponse (l'invite demande trois questions ; une affirmation de plus de 400 caractères est anormale) : rien à dire dans `reason`.
- low · second avis 5 · **rejeté** · `OllamaChatModel` traduit toute panne du client (dont httpx) en `ProviderError` (`_translate`), et le vrai `JudgeGateway` ne rattrape lui aussi que `ProviderError` : une autre exception est un défaut à laisser remonter.
- Complexité : 0 constat (structures bornées par la taille du jeu fixe).

## Journal

- 2026-10-19 · dev : spec, `metrics.py` extrait du service, phrases de troncature, jeu fixe (12 cas), outil de rejeu et de mesure, tests, contrat.
