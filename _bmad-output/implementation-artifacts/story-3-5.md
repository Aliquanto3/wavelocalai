---
title: "Le verdict local/cloud est chiffré (table de prix datée, instantané du run, écran)"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '71cfbf3'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-3-4.md'
warnings: []
deferred:
  - summary: >-
      La table de prix cloud est vide : aucune table de prix datée et sourcée n'existe dans le dépôt (la v1 n'en a pas ; l'ancienne v2 archivée n'a qu'un prix Google hors de `[cloud.models]` et des tables jugées périmées, sans source relevée pour les modèles de `[cloud.models]`). Aucun prix ni aucune date n'a été inventé : tant que la table est vide, le coût d'un modèle cloud s'affiche « inconnu » avec sa raison. À remplir par Anaël : pour chaque modèle de `[cloud.models]` qu'il veut chiffrer, les prix publics par million de tokens d'entrée et de sortie, la date du relevé et l'URL de la source (`[cloud.prices]` de `wavelocalai.toml`, mode d'emploi en commentaire).
    evidence: |-
      `wavelocalai.toml` (`[cloud.prices]`), `src/wavelocalai/config.py` (`PriceTable`, qui refuse une entrée sans `retrieved_at` ni `source`).
    location: wavelocalai.toml
    severity: medium
  - summary: >-
      Le verdict est calculé à la lecture de l'instantané (notes lues dans `run_events`, mesures des feuilles, table de prix courante), non figé en base à la fin du run. Une table de prix remplacée plus tard change donc le coût d'une comparaison rouverte (la date affichée est celle de la table courante). Figer le verdict demanderait une migration (colonne ou événement) : non demandée.
    evidence: |-
      `src/wavelocalai/runs/snapshot.py` (`run_snapshot`), `runs/verdict.py`.
    location: src/wavelocalai/runs/snapshot.py
    severity: low
  - summary: >-
      Le coût d'un modèle cloud se calcule sur les tokens de la lane (entrée et sortie) comptés par le fournisseur ; un fournisseur qui n'en rend pas (`input_tokens` ou `output_tokens` nul) donne « inconnu » avec la raison. Les tokens de raisonnement facturés à part ne sont pas distingués (l'événement `metrics` n'en porte pas).
    evidence: |-
      `runs/verdict.py` (`_cost`), `contrat-api.md` (`metrics`).
    location: src/wavelocalai/runs/verdict.py
    severity: low
---

# Story 3.5 : le verdict local/cloud est chiffré

## Objectif

À la fin d'une Arène qui compte au moins un modèle local et un modèle cloud notés, le serveur chiffre l'écart de note entre le meilleur local et le meilleur cloud, le coût de 1 000 requêtes de même taille, le CO₂ de chacun et les données restées sur le poste ; il le rend dans l'instantané `GET /api/runs/{id}` (champ `verdict`, AD-5). L'écran le lit à `run_ended` et à la réouverture, n'en calcule rien et affiche la date de la table de prix avec le coût. Aucun nouvel événement.

## Critères d'acceptation et preuves

Preuves : `tests/v2/unit/test_verdict.py` (calcul, config), `tests/v2/web/test_arena_verdict_api.py` (instantané de bout en bout), `tests/v2/unit/test_arena_verdict_static.py` (écran, sans navigateur) et `tests/v2/e2e/test_arena_verdict.py` (Edge, axe-core clair et sombre, 320 px).

1. **Table de prix datée, lue par `Settings`.** `[cloud.prices]` de `wavelocalai.toml` : `currency`, `retrieved_at` (date), `source` (texte) et `[cloud.prices.models]` (`"fournisseur/modèle" = { input_per_mtok, output_per_mtok }`, par million de tokens). `PriceTable` (`config.py`) refuse une entrée sans date de relevé ni source, un prix négatif, une devise qui n'a pas trois lettres. L'application n'écrit jamais le `.toml` (AD-15). Preuve : `test_a_price_table_needs_a_date_and_a_source`, `test_the_shipped_toml_loads_with_its_price_table`.
2. **Verdict à la fin du run, dans l'instantané.** Un run `arena` terminé `ok` avec au moins un local et un cloud notés rend `verdict` : `leader` (`local`, `cloud` ou `tie`) et `score_gap` (points, positif), `local` et `cloud` (`model`, `score`, `co2` d'AD-10 ou `null`, `cost` `{amount, currency, reason}`), `requests: 1000`, `price_table {retrieved_at, source, currency}` et `data_on_device {models, count, judge_off_device}`. Le meilleur de chaque origine est celui de plus haute note (à égalité, le premier lancé). Coût local : 0 ; coût cloud : 1 000 × (tokens d'entrée × prix d'entrée + tokens de sortie × prix de sortie) / 10⁶ avec le prix daté de la table. Aucun événement nouveau (`GET /api/runs/{id}` seul). Preuve : `test_the_verdict_compares_the_best_local_with_the_best_cloud`, `test_the_cost_of_1000_requests_uses_the_dated_price_of_the_cloud_model`, `test_the_snapshot_of_an_arena_carries_the_verdict`.
3. **Modèle absent de la table : « inconnu », jamais 0.** `cost.amount` est `null` et `cost.reason` dit pourquoi : table vide, modèle absent de la table, tokens non comptés. Preuve : `test_a_cloud_model_missing_from_the_price_table_has_an_unknown_cost_with_a_reason`, `test_an_empty_price_table_gives_an_unknown_cost`, `test_a_cloud_model_without_counted_tokens_has_an_unknown_cost`.
4. **Arène sans cloud, sans local noté ou non terminée : pas de verdict.** `verdict` vaut `null` (clé présente pour un run `arena`, absente pour les autres genres). Un run arrêté, interrompu ou en échec n'a pas de verdict (variante conservatrice : le classement ne vaut alors que pour les modèles déjà notés). Preuve : `test_no_verdict_without_a_scored_cloud_and_a_scored_local_model`, `test_a_cancelled_arena_has_no_verdict`.
5. **Données restées sur le poste.** `data_on_device` liste les modèles locaux de la comparaison ; si le juge est un modèle cloud, `judge_off_device` est vrai et l'écran ne dit pas que les réponses sont restées sur le poste (elles ont été envoyées au juge). Preuve : `test_a_cloud_judge_means_the_local_answers_left_the_device`, `test_the_verdict_is_read_from_the_snapshot_at_the_end_and_on_reopening` (phrase « n'ont pas quitté ce poste »).
6. **Écran.** `screens/arena-verdict.js` lit l'instantané (`api.run`) à `run_ended` (statut `ok`) et à la réouverture par l'adresse (même chemin : le rejeu finit par `run_ended`), n'en calcule rien (il choisit la phrase selon `leader`, met en forme montants, points et CO₂). Quatre lignes : écart de note, coût pour 1 000 requêtes de même taille avec « Prix relevés le … » (la source en légende), CO₂ par réponse (une seule unité), données restées sur le poste. « Coût inconnu » affiche la raison du serveur, jamais 0 ni « — ». Arène sans verdict : la section n'apparaît pas. Preuve : `test_the_verdict_is_read_from_the_snapshot_at_the_end_and_on_reopening`, `test_the_verdict_shows_the_price_table_date_with_the_cost`, `test_an_unknown_cost_says_why_and_is_never_zero`, `test_a_comparison_without_cloud_has_no_verdict_section`.
7. **Accessibilité.** axe-core sans violation (clair et sombre, 320 px et 1 440 px), aucun défilement horizontal de la page, aucune couleur en dur. Preuve : `test_axe_finds_no_violation_on_the_verdict`, `test_the_verdict_is_styled_from_tokens_only`.

## Fichiers

- `wavelocalai.toml` (`[cloud.prices]`, vide, avec mode d'emploi), `src/wavelocalai/config.py` (`ModelPrice`, `PriceTable`, `CloudSettings.prices`)
- `src/wavelocalai/runs/verdict.py` (nouveau, fonctions pures) ; `runs/snapshot.py` (`run_snapshot(store, run_id, prices)`, notes lues dans `run_events`) ; `web/routes_runs.py` (passe la table)
- `src/wavelocalai/web/static/screens/arena-verdict.js` (nouveau) ; `screens/arena-results.js` (monte la section, `end(state, runId)`) ; `screens/arena.js` (`results.end(state, runId)`, une ligne) ; `core/api.js` (`run`) ; `core/format.js` (`formatMoney`) ; `arena-results.css` ; `i18n/fr.json` (`arena.verdict`)
- Tests : voir les preuves ; `tests/v2/e2e/conftest.py` (`Backend` accepte un `.toml` de réglages), `tests/v2/unit/test_arena_static.py` et `test_arena_results_static.py` (scripts de l'écran)

## Écarts

- **Écarts §7(d)** : aucun ne touche la 3.5 (le §7(c) n'y change rien) ; ceux des stories voisines restent comme les 3.2 à 3.4 les ont laissés.
- **Devise** : la table déclare sa devise (« EUR » par défaut) et le montant local « 0 » est dans la même ; aucune conversion de change n'est inventée.
- **Verdict seulement pour un run `ok`** : le critère dit « à la fin du run » ; un run arrêté ou interrompu n'a pas de verdict (voir 4).
- **Verdict calculé à la lecture** : voir `deferred`.

## Reports

Voir `deferred` : table de prix à remplir par Anaël (source et date à relever), verdict non figé en base, tokens de raisonnement.

Tests : `tests/v2` 1010 réussis (hors E2E, désélectionnés par défaut) ; E2E sur Edge : `-m e2e -k "arena or core or home"` 153 réussis (dont les 11 de `test_arena_verdict.py`, axe-core clair et sombre à 320 px et 1 440 px) ; contrôle rapide propre.

## Revue

Revue Opus (une passe) sur 763a122, avec la liste du second avis (Haiku).

- medium · second avis · corrigé : le hub publie `run_ended` avant d'écrire le statut final (`runs/hub.py`, `_close`), et l'instantané ne donne `verdict` que pour `ok` ; une lecture à `run_ended` pouvait voir `running` et cacher la section jusqu'à la réouverture. Correctif côté écran (le hub, partagé, n'est pas touché) : `arena-verdict.js` relit l'instantané tant que son statut est actif (20 fois au plus, toutes les 150 ms), puis dit « n'a pas pu être lu » s'il l'est encore. Preuve : `test_a_snapshot_read_before_the_final_status_is_written_is_read_again` (E2E, échoue sans le correctif).
- low · second avis · corrigé : une devise de trois chiffres passait `PriceTable` et `Intl.NumberFormat` aurait levé, section cachée sans message. `currency` exige désormais un code ISO 4217 en majuscules (`^[A-Z]{3}$`) ; le rendu passe aussi dans le `try` de `load` (une erreur de mise en forme affiche « n'a pas pu être lu »). Preuve : `test_a_price_table_needs_a_date_and_a_source` (« 978 », « eur »).
- low · second avis · rejeté : le garde-fou statique « l'écran ne calcule rien » est une heuristique, mais la relecture d'`arena-verdict.js` confirme qu'il ne fait aucune opération sur montants, notes ou prix, et `test_the_screen_shows_what_the_server_says_and_computes_nothing` (instantané réécrit) le prouve au navigateur ; un analyseur JS n'apporterait rien de plus ici.
- Relecture propre : critères 1 à 7 couverts ; couches respectées (`runs/verdict.py` pur, aucune importation web) ; aucun appel réseau nouveau ; `_scores` lit les `judge_score` du run une fois par lecture (O(n), pas de structure qui grossit par événement). Complexité : 0 constat. `screens/arena.js` est à 600 lignes (une ligne modifiée, taille inchangée) : à découper avant d'y ajouter quoi que ce soit.
