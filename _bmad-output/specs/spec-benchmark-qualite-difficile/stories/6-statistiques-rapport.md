---
title: 'Statistiques et rapport'
type: 'feature'
created: '2026-10-11'
status: 'done'
baseline_revision: 'bbbe3f9ef931a0627b56f36330c7befcb9ef041d'
route: 'dispatch'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-10/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-benchmark-qualite-difficile/statistiques.md'
warnings:
  - oversized
deferred:
  - summary: >-
      Meneur, rang approché, groupes et Spearman reposent sur la moyenne de chaque modèle calculée sur ses seules unités définies : un modèle privé des unités les plus dures (context_exceeded aux grands paliers) est noté sur un sous-ensemble plus facile.
    evidence: |-
      Règle d'AD-10 du spine (« les statistiques retirent la question des comparaisons qui impliquent ce modèle et publient le compte ») : les tests appariés sont justes, mais leader_order, approximate_ranks et _spearman comparent des moyennes non appariées. Le compte « Exclues » est publié. À trancher au pilote (story 8) quand les context_exceeded réels seront connus : meneur choisi sur les unités communes, seuil d'exclusion, ou avertissement dans le rapport (amendement d'AD-10 ou d'AD-17).
    location: >-
      scripts/quality_bench/report/campaign.py (scope_stats, _spearman) ; scripts/quality_bench/stats/groups.py
    severity: medium
---

<intent-contract>

## Intent

**Problem:** Le banc sait générer (story 5) et corriger (story 4), mais rien ne dit quels modèles se distinguent vraiment : pas de statistiques, pas de contrôle de complétude, pas d'export versionné des scores ni de rapport. CAP-7 (Wilson, McNemar exact apparié, Holm, erreurs-types groupées, groupes indiscernables, troncature, Spearman contre l'indice AA) reste sans code.

**Approach:** Ajouter le noyau pur `stats/` (fonctions sur tableaux, `numpy`, `scipy`, `statsmodels` seulement) et la coquille `report/` avec la sous-commande `report --campaign <c> [--partial] [--aa-date AAAA-MM-JJ]`. Elle lit `grading.jsonl` et `generation.jsonl` (plus le manifeste, le jeu et un fichier de référence AA local), vérifie la complétude, agrège par unité statistique (`model`, `track`, `unit`), puis réécrit `benchmarks/quality/<c>/` en liste blanche : scores `qb.score/1`, résumé `qb.report/1`, copie du manifeste, rapport Markdown en français et graphiques SVG à la charte Wavestone. Règles AD-6 et AD-17 du spine (et AD-2, AD-3, AD-4, AD-10).

## Boundaries & Constraints

**Always:**
- **Pureté (AD-17) :** `stats/` ne contient que des fonctions pures sur des tableaux ou des séquences, sans I/O ni état global, et n'importe que la bibliothèque standard, `numpy`, `scipy`, `statsmodels` et ses propres modules ; aucun import du paquet. Toute méthode de `statistiques.md` est normative ; Holm par `multipletests(..., method="holm")` explicite, BH (`"fdr_bh"`) réservé à la matrice exploratoire ; ni Friedman/Nemenyi, ni test non apparié.
- **Unité statistique (AD-17) :** (`model`, `track`, `unit`). Les questions d'une `unit` sont agrégées par minimum de `score`, puis les seeds par moyenne. Une question au score nul (`error`, `context_exceeded`, et `awaiting_judgment` sous `--partial`) rend son unité nulle pour ce modèle ; une unité nulle est retirée des seules comparaisons qui impliquent ce modèle, et comptée.
- **Choix de méthode :** il dépend de `generation.request.k` du manifeste et des usages du périmètre, jamais des valeurs observées. Périmètre binaire = `k == 1` et aucun usage `writing` : McNemar exact (`scipy.stats.binomtest(b, b+c)`, `p = 1` si `b+c = 0`) et intervalle de Wilson. Sinon (`k > 1`, rédaction, ou score global d'une piste qui la contient) : test z sur la différence appariée avec erreur-type groupée, intervalle moyenne ± z·ET groupée borné à [0, 1], et IC bootstrap apparié de la différence.
- **Publié par périmètre** (chaque piste en global, puis chaque usage) : par modèle, moyenne, effectif, unités exclues, ET groupée par `group`, IC à 95 %, IC simultané (Bonferroni sur les modèles du périmètre), rang approché (1 + nombre de modèles dont l'IC simultané est entièrement au-dessus), groupe indiscernable, taux de troncature (lignes `truncated` sur lignes notées) ; comparaisons au meneur (différence, ET appariée groupée, IC à 95 %, corrélation entre modèles, b et c en binaire, p brute, p de Holm, rejet) ; matrice exploratoire « qui bat qui » corrigée par BH. Usages à métrique continue (`instructions_followed`, `f1`) : moyenne par modèle et IC bootstrap apparié de la différence au meneur. Par piste, k̂_Bonferroni : nombre d'usages où le meneur global bat chaque modèle à α/m.
- **Spearman (statistiques.md) :** score global de chaque piste contre l'indice AA `measured` de la variante appariée (`think_on` ↔ `reasoning`, `think_off` ↔ `non_reasoning`), modèles appariés par `tag` ; ρ, p unilatérale (`alternative="greater"`), IC bootstrap de ρ à graine fixée ; conclusion : moins de 8 modèles → sans conclusion ; ρ < 0 → enquête ; p < 0,05 → concordant ; sinon non significatif.
- **Complétude (AD-17) :** clés attendues = `models_resolved` × pistes du modèle × questions de la piste restreintes à `selection` × seeds (`seed_base + epoch`, `epoch < k`), calculées depuis le `blocking` du manifeste et le jeu. Le rapport refuse de publier (code 1, rien d'écrit) s'il manque une clé dans `generation.jsonl` ou dans `grading.jsonl`, s'il reste un `awaiting_judgment`, ou si une empreinte de manifeste ne concorde pas (ligne de génération, `generation_manifest` ou `judgment_manifest` de correction, empreinte de configuration), sauf avec `--partial` : les lignes manquantes ou discordantes sont alors écartées et comptées, et le rapport est marqué partiel.
- **Exports (AD-6) :** `benchmarks/quality/<c>/` (`$QUALITY_BENCH_EXPORTS`) réécrit en entier, sans date, octets identiques d'une passe à l'autre : `scores/<modèle>.jsonl` (`qb.score/1` exactement : `schema, question_hash, model, digest, track, seed, status, score, success, metrics`, `metrics` en flottants finis), `summary.json` (`qb.report/1`, schéma fermé), `manifest.json` (copie du manifeste de génération), `report.md` et `charts/*.svg`, tous produits depuis les agrégats seuls : ni texte de question, ni sortie de modèle, ni `question_id`. Chaque enregistrement est validé par `common/schemas.py` avant écriture ; un champ hors liste est une erreur.
- **Références hors ligne :** indices AA lus dans `benchmarks/quality/references/aa-<AAAA-MM-JJ>.json` (`qb.aa_reference/1` : `schema, date, source, entries: [{tag, index, status: measured|estimated, variant: reasoning|non_reasoning}]`) ; par défaut le plus récent, sinon `--aa-date`. Chemin et `sha256` consignés dans `summary.json`. Aucun fichier : section Spearman marquée « indice AA absent », sans échec.
- **Rendu :** graphiques SVG écrits à la main (aucune bibliothèque de tracé), charte Wavestone (primaire `#451DC7`, aucun emoji), titre et `aria-label` en français, nombres au format français ; `report.md` en français.
- `report` ne prend aucun verrou machine, n'accède pas au réseau ; journal `campaigns/<c>/log-report.log` sans contenu de question ni de réponse.

**Never:**
- Lire `judgment.jsonl` ou `labels.jsonl` (seul `report/calibration.py` le fera, story 9) ; écrire ailleurs que sous `benchmarks/quality/<c>/` et le journal ; modifier `generation.jsonl`, `grading.jsonl` ou le jeu.
- Récupérer un indice AA en ligne, ou commiter un fichier sous `benchmarks/` dans cette story (le fichier de référence réel est fourni par Anaël).
- Importer depuis `report/` : `generation/`, `grading/`, `judge/`, `ollama/`, `questions/importers/`, une bibliothèque réseau ; depuis `stats/` : tout module du paquet hors `stats/`.
- Coder le pilote, la calibration ou le juge (stories 7 à 9) ; modifier `scripts/benchmark_slm.py`, `src/`, `benchmarks/results/`, `.venv`, `.venv-app`, `SPEC.md`, `stories.yaml`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Campagne complète | 3 modèles, 2 pistes, usages binaires et rédaction, `k = 1` | exports écrits et validés ; McNemar par usage binaire, test z en rédaction et en global ; code 0 | N/A |
| Deux passes | mêmes entrées | `benchmarks/quality/<c>/` identique octet pour octet | N/A |
| Clé manquante | une clé attendue absente de `generation.jsonl` ou de `grading.jsonl` | rien n'est écrit, compte journalisé | code 1 |
| Attente du juge | une ligne `awaiting_judgment` | rien n'est écrit | code 1 |
| Manifeste discordant | ligne d'un autre manifeste, `judgment_manifest` différents, configuration modifiée | rien n'est écrit, premier écart nommé | code 1 |
| `--partial` | l'un des trois cas ci-dessus | rapport marqué partiel, lignes écartées comptées | code 0 |
| Erreur du banc | ligne `error` ou `context_exceeded` | unité nulle pour ce modèle, retirée de ses comparaisons, comptée | N/A |
| Unité multi-questions | 3 variantes VAR-MATH dont une ratée | unité ratée (minimum) | N/A |
| `k = 2` | deux seeds par question | moyenne des seeds, test z, pas de McNemar | N/A |
| Référence AA | fichier avec ≥ 8 modèles `measured` | ρ, p unilatérale, IC bootstrap, conclusion | moins de 8 : sans conclusion ; aucun fichier : section absente |
| Entrées incohérentes | manifeste absent, empreinte du jeu différente, ligne hors schéma, clé de correction inconnue de la génération, référence AA hors schéma | rien n'est écrit | `ReportError`, code 1 (jamais levée par `--partial`) |
| Configuration | `campaigns/<c>.yaml` absent ou invalide | rien n'est écrit | code 2 |

</intent-contract>

## Code Map

- `scripts/quality_bench/common/config.py:279` -- `load_campaign(path)` → `CampaignConfig(set_id, generation, generation_hash, grading)` ; `campaign_config_path` est appelé par l'attribut du module `paths` (les tests le redirigent).
- `scripts/quality_bench/common/manifest.py:165` -- `blocking_hash(manifest)` ; `blocking.generation.resolved` = section `generation` résolue (`request.seed_base`, `request.k`, `selection`), `blocking.models_resolved[].{tag, digest, tracks}`, `blocking.set.{id, hash}` (`generation/commands.py:169-181`).
- `scripts/quality_bench/generation/runner.py:79-160` -- `_sample` et la résolution de `selection` dans `build_plan` : à déplacer dans un module neutre `common/selection.py` (`selected_ids(selection, questions, think_off_ids) -> set | None`), appelé par `build_plan` et par le rapport, pour que les clés attendues soient exactement celles du runner. Comportement inchangé : `test_selection_sample_draw_is_pinned` (`tests/quality_bench/test_generate_command.py:581`) le garde. `common/` est dans `harness_hash` : aucune campagne n'existe encore.
- `scripts/quality_bench/grading/commands.py` -- modèle de sous-commande (`_read_manifest`, `_validated` sans valeur dans les messages, `_load_set` avec contrôle de `set_hash`, codes 0/1/2, `setup_logging`). `report/` ne peut pas l'importer : reprendre le motif dans `report/inputs.py`.
- `scripts/quality_bench/common/schemas.py` -- registre `SCHEMAS` (`_closed`, `_HASH`, `validate`, `validate_with`) ; `GRADING_V1:253` (statuts, `score`/`success`) ; ajouter `qb.score/1`, `qb.report/1`, `qb.aa_reference/1`.
- `scripts/quality_bench/common/paths.py` -- `exports_root()`, `grading_path`, `generation_path`, `generation_manifest_path`, `judgment_manifest_path`, `log_path`, `set_questions_path`, `set_tracks_path`, `check_id` ; ajouter `campaign_exports_dir(c)`, `references_dir()`.
- `scripts/quality_bench/common/{jsonl,canonical}.py` -- `read_jsonl`, `rewrite_jsonl`, `canonical_bytes`, `pretty_bytes`, `sha256_bytes`, `sha256_hex`.
- `scripts/quality_bench/questions/schema.py:281` -- `set_hash(questions, tracks)` ; `report/` peut importer `questions/schema.py`.
- `scripts/quality_bench/grading/{base,extraction,instructions,rag}.py` -- métriques produites : `f1` (extraction avec cible, `squad_f1`), `instructions_followed`, `inline_thinking` ; rédaction : `success = null`, score continu.
- `scripts/quality_bench/__main__.py` -- `SUBCOMMANDS`, éditée dans ce fichier seulement (ajouter `REPORT`).
- `tests/quality_bench/test_exports.py` -- `ALLOWED` (chemin → schéma) et `export_problems` : à étendre aux nouveaux chemins ; parcourt le vrai `benchmarks/quality/`.
- `tests/quality_bench/test_package.py:62` -- propriétaires uniques : ajouter `numpy`, `scipy`, `statsmodels` (`stats/` seulement). `tests/quality_bench/test_vendored.py:129-225` -- `_graph`, `_module_path`, `_rel` (graphe d'import AST). `conftest.py` -- `REQUIRED_MODULES` += `numpy`, `scipy`, `statsmodels` ; la fixture `autouse` redirige `QUALITY_BENCH_EXPORTS`.
- `tests/quality_bench/factories.py` -- `generation_record`, `manifest`, `model_resolved`, `question` (empreintes recalculées) : base des campagnes synthétiques.
- PyPI (2026-10-11) : numpy 2.5.4, scipy 1.18.1, statsmodels 0.15.0 (installés sur Python 3.14) ; bornes du spine `numpy>=2.2`, `scipy>=1.15`, `statsmodels>=0.14.4` (compatibles 3.10).
- `benchmarks/quality/` n'existe pas encore sur la branche ; aucun fichier `aa-*.json` réel.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/quality_bench/requirements.txt` -- `numpy>=2.2`, `scipy>=1.15`, `statsmodels>=0.14.4` (story 6, vérifiées sur PyPI) ; installation dans `.venv-quality`.
- [x] `scripts/quality_bench/common/selection.py`, `generation/runner.py` -- déplacement de la sélection (Code Map), sans changement de comportement.
- [x] `scripts/quality_bench/common/schemas.py`, `common/paths.py` -- schémas fermés `qb.score/1`, `qb.report/1`, `qb.aa_reference/1` (flottants finis, `null` pour une valeur indéfinie) ; chemins d'export et de références.
- [x] `scripts/quality_bench/stats/` -- `__init__.py`, `units.py` (agrégation minimum puis moyenne des seeds), `wilson.py`, `clustered.py` (moyenne et ET groupée), `mcnemar.py` (McNemar exact, différence appariée, ET, IC, corrélation, test z), `multiple.py` (Holm, BH, k̂_Bonferroni), `bootstrap.py` (bootstrap apparié par groupes, graine fixée), `groups.py` (groupes indiscernables, IC simultanés, rang approché), `spearman.py` (ρ, p unilatérale, IC bootstrap, conclusion).
- [x] `scripts/quality_bench/report/` -- `inputs.py` (lecture, contrôles, clés attendues, complétude), `campaign.py` (périmètres, agrégats, résumé), `export.py` (scores, résumé, manifeste, écriture atomique du dossier), `markdown.py`, `charts.py` (SVG), `commands.py` (sous-commande et codes) ; `__main__.py`.
- [x] `scripts/quality_bench/questions/SOURCES.md` -- section « Rapport » : commande, refus, `--partial`, format du fichier AA à fournir.
- [x] `tests/quality_bench/` -- `test_stats.py` (valeurs de référence calculées à la main ou par une formule indépendante : Wilson, McNemar, Holm ≠ Holm-Šidák, BH, ET groupée, bootstrap reproductible, groupes, rang, Spearman et ses seuils), `test_report_command.py` (matrice I/O sur JSONL synthétiques, deux passes identiques, aucun texte de question ni `question_id` dans les exports), `test_report_imports.py` (graphes AST de `stats/` et `report/`), ajouts à `test_exports.py`, `test_schemas.py`, `test_package.py`, `conftest.py`.

**Acceptance Criteria:**
- Given une campagne synthétique complète, when on lance deux fois `python -m scripts.quality_bench report --campaign <c>`, then le code est 0, `export_problems` ne relève rien sur le dossier écrit, et les deux arborescences sont identiques octet pour octet.
- Given `stats/`, when on analyse ses imports (AST), then il n'importe que la bibliothèque standard, `numpy`, `scipy`, `statsmodels` et `stats/` ; et `report/` n'atteint ni `generation/`, ni `grading/`, ni `judge/`, ni `ollama/`, ni `questions/importers/`, ni une bibliothèque réseau.
- Given des p-valeurs où Holm et Holm-Šidák diffèrent, when `stats` les corrige, then le résultat est celui de Holm.
- Given le vrai `benchmarks/quality/`, when `test_exports.py` le parcourt, then chaque fichier suit un chemin permis et chaque ligne ou document valide son schéma.
- Given `.venv-quality\Scripts\python -m pytest tests/quality_bench` et `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"`, then tout passe sans Ollama ni réseau.

## Spec Change Log

## Review Triage Log

### 2026-10-12 — Review pass
- verdicts: 43 findings — high 0, medium 13, low 24, false 6, maybe-false 0
- findings:
  - `[false]` `[reject]` (IA) Le test qui parcourt le vrai `benchmarks/quality/` passe à vide — le dossier n'existe pas encore sur la branche ; le test le vérifiera dès le premier export, et la liste blanche est exercée sur des exports synthétiques produits par `report`.
  - `[medium]` `[patch]` (IA) `manifest.json` publie les `question_id` d'une sélection `ids` — copie exportée réduite à `{ids_count, ids_sha256}` (`report/export.py:exported_manifest`), documenté dans SOURCES.md, test `test_selection_ids_never_leak_into_the_exported_manifest` ; le `created_at` du manifeste est fixe d'une passe à l'autre (copie), sans effet sur l'identité des octets.
  - `[medium]` `[patch]` (IA) Sous `--partial`, une ligne `awaiting_judgment` reste dans les scores et gonfle `retained` — `continue` après le comptage ; test : `retained == expected − 1`, aucune ligne `awaiting_judgment` exportée.
  - `[false]` `[reject]` (IA) `--partial` marque le rapport partiel même sans écart — la spec dit « avec `--partial` … le rapport est marqué partiel » : comportement voulu.
  - `[low]` `[reject]` (IA) Famille de Holm réduite aux p définies, Wilson sans regroupement, pas de garde « pas au pilote » pour Spearman — choix imposés par la spec (Wilson et ET groupée publiées côte à côte, conclusion « sans conclusion » sous 8 modèles) ; la réduction de famille n'arrive que sur une paire sans unité.
  - `[false]` `[reject]` (IA) Le test k = 2 ne distingue pas « minimum puis moyenne » de l'ordre inverse — `test_seeds_are_averaged_after_the_minimum` (test_stats) les distingue ; l'ordre est celui de l'intention.
  - `[medium]` `[patch]` (IA) Charte Wavestone jamais vérifiée dans le SVG — même cause que l'entrée VG « rendu non testé » : `test_report_render.py` (couleur `#451DC7`, aria-label et titre en français, aucun emoji).
  - `[low]` `[reject]` (IA) Jeu synthétique sans extraction, outils ni abstention — le chemin `f1` d'extraction est le même que celui du RAG, couvert ; les usages binaires suivent un code unique.
  - `[medium]` `[patch]` (VG) Le test du nom de campagne réservé passe sans la garde (code 2 par configuration absente) — test paramétré (`references`, `References`, `SETS`) avec configuration présente : code 1, dossier intact, « dossier réservé » au journal ; test unitaire de `paths`.
  - `[medium]` `[patch]` (VG) Clés attendues jamais calculées avec une `selection` — `make_campaign(selection=…)` et `test_selection_sample_gives_a_complete_campaign` (`expected == retained`), plus le cas `ids`.
  - `[medium]` `[patch]` (VG) Refus d'incohérence non testés (doublons, `prompt_hash`, `unit`, clé, digest, manifeste de jugement) — `test_incoherent_lines_are_refused_even_partial` (6 cas) et `test_judgment_manifest_of_another_generation_is_refused`.
  - `[low]` `[patch]` (VG) Gains k̂_Bonferroni jamais vérifiés — recalculés depuis les périmètres d'usage du même résumé dans `test_leader_comparisons_use_holm_and_groups`.
  - `[medium]` `[patch]` (VG) Aucune valeur rendue de `report.md` ni du SVG n'est testée — nouveau `test_report_render.py` (formats `fr_*`, ligne du meneur, ligne de comparaison, Spearman, k̂, bandeau partiel, `cx` d'une moyenne connue).
  - `[low]` `[reject]` (VG) Chemin de restauration de l'échange atomique non testé — exports régénérables depuis les entrées ; le test demanderait de simuler un échec d'`os.replace`, défaut improbable.
  - `[low]` `[patch]` (VG) Garde des dossiers réservés sensible à la casse sous Windows — comparaison en `casefold()` (`paths.campaign_exports_dir`), test.
  - `[medium]` `[patch]` (BH) `awaiting_judgment` gardée sous `--partial` — même cause et même correctif que l'entrée IA.
  - `[medium]` `[patch]` (BH) `manifest.json` peut publier des `question_id` — même cause et même correctif que l'entrée IA.
  - `[low]` `[reject]` (BH) `write_export_dir` supprime un `.old` resté seul après un arrêt entre les deux renommages — fenêtre de quelques millisecondes ; exports régénérables ; le correctif ajoute une branche de reprise.
  - `[medium]` `[patch]` (BH) ET groupée nulle avec un seul groupe : p = 0 et comparaison « distinguée » à tort — `clustered_mean_se` rend `se = nan` sous 2 groupes ; test.
  - `[false]` `[reject]` (BH) Un périmètre binaire ne vérifie pas que les scores valent 0 ou 1 — `qb.grading/1` impose `success` booléen hors rédaction et `score = 1`/`0` selon `success` ; chaque ligne est validée à la lecture.
  - `[low]` `[reject]` (BH) McNemar et Wilson indépendants à côté d'une ET groupée dans la même ligne — publication côte à côte imposée par la spec et statistiques.md.
  - `[medium]` `[defer]` (BH) Meneur, rang, groupes et Spearman comparent des moyennes sur des ensembles d'unités différents (unités nulles retirées par modèle) — règle d'AD-10 du spine antérieure à la story ; à trancher au pilote (frontmatter `deferred`, `deferred-work.md`).
  - `[low]` `[reject]` (BH) Octets identiques garantis dans un seul environnement (flux numpy) — une seule machine de campagne ; consigner les versions ajouterait des champs au schéma.
  - `[low]` `[reject]` (BH) Pas de contrôle croisé statut de correction / statut de génération — `grade`, seul écrivain, dérive l'un de l'autre ; garde supplémentaire.
  - `[low]` `[reject]` (BH) Les comptes de complétude n'expliquent pas tout refus (jugement d'un autre manifeste sans compteur) — les lignes concernées sortent en `grading_discordant` sous `--partial`, et le journal nomme l'écart ; un compteur ajouterait un champ.
  - `[false]` `[reject]` (BH) Date AA lâche (`2026-13-45`) et fichier le plus récent pris par défaut — une date invalide ne trouve aucun fichier (code 1) ; « le plus récent par défaut » est la règle de la spec.
  - `[low]` `[patch]` (BH) Tests plus faibles que le contrat (code 1 ou 2, collision de casse, paire sans unité) — mêmes correctifs que les entrées VG « nom réservé », EC « collision de casse » et EC « b et c sans unité ».
  - `[low]` `[patch]` (BH) « k » désigne trois choses dans le rapport — texte « Holm sur les m − 1 comparaisons au meneur (m modèles du périmètre) » (markdown.py, SOURCES.md).
  - `[low]` `[patch]` (BH) Un modèle sans score n'a aucune marque dans le graphique — « sans score » dans la colonne des valeurs (charts.py), test ; pas de graphique pour les métriques continues (non demandé).
  - `[medium]` `[patch]` (EC) ET groupée nulle avec un seul groupe — même correctif que l'entrée BH.
  - `[medium]` `[patch]` (EC) `awaiting_judgment` gardée sous `--partial` — même correctif que l'entrée IA.
  - `[low]` `[patch]` (EC) Nom de campagne réservé en autre casse sous Windows — même correctif que l'entrée VG.
  - `[low]` `[patch]` (EC) Deux tags qui ne diffèrent que par la casse donnent le même fichier sous NTFS — collision détectée en `casefold()` (`ReportError`), test.
  - `[low]` `[reject]` (EC) `OSError` (disque plein, fichier verrouillé) non rattrapée par la commande — rare ; le dossier temporaire est supprimé dans le `finally`, rien n'est publié ; garde supplémentaire.
  - `[low]` `[reject]` (EC) Échec de `rmtree` de l'ancien dossier après l'échange — rare ; le rapport est déjà en place ; garde supplémentaire.
  - `[low]` `[reject]` (EC) Deux `report` simultanés sur la même campagne — un seul opérateur, commande manuelle ; un verrou ajouterait de l'état.
  - `[low]` `[patch]` (EC) Index AA `NaN` ou `Infinity` accepté — `parse_constant` refuse les constantes non finies (`ReportError`), test.
  - `[low]` `[reject]` (EC) Un modèle sans unité appariée avec le meneur est rangé dans son groupe — cas `--partial` extrême ; « indiscernable » reste exact faute de comparaison.
  - `[false]` `[reject]` (EC) `selection.sample.per_usage` négatif fait planter `random.sample` — `load_campaign` impose `per_usage ≥ 1` et le manifeste est écrit depuis la configuration résolue : inatteignable sans manifeste altéré à la main.
  - `[low]` `[patch]` (EC) Paire binaire sans unité appariée publiée avec b = c = 0 — `b = c = None` et `p = nan` quand n = 0.
  - `[low]` `[reject]` (EC) Ligne de correction recopiée sur une autre clé acceptée — même raison que l'entrée BH « contrôle croisé ».
  - `[low]` `[reject]` (EC) « Écriture atomique » : deux renommages laissent une fenêtre sans dossier — même cause que l'entrée BH `.old`.
  - `[low]` `[patch]` (EC) Les schémas « flottants finis » acceptent NaN à la validation — même correctif que l'entrée EC « index AA » ; les exports sont écrits par `canonical_bytes` (`allow_nan=False`).

## Design Notes

- **Groupes indiscernables :** meneurs successifs. Le premier groupe = meneur + modèles que Holm (k−1 comparaisons au meneur) ne distingue pas ; on retire ce groupe et on recommence sur le reste. Égalité de moyenne : ordre de la configuration.
- **ET groupée** (Miller, « Adding Error Bars to Evals ») : `ET = sqrt(Σ_g (Σ_{i∈g} (x_i − x̄))²) / n` ; même formule sur les différences appariées `d_i = a_i − b_i`.
- **Score global d'une piste mêlant binaire et rédaction (report du spine) :** moyenne des scores d'unité sur tous les usages, test z apparié à ET groupée ; McNemar reste la méthode des usages binaires.
- **Métrique continue absente :** valeur 0 pour `truncated` et `non_compliant`, unité nulle sinon (ex. NIAH sans `f1`).
- **Nom de fichier d'un modèle :** caractère hors `[A-Za-z0-9._-]` remplacé par `_` (`qwen3.5:4b` → `qwen3.5_4b.jsonl`) ; deux modèles qui donneraient le même nom : `ReportError`.

## Verification

**Commands:**
- `.venv-quality\Scripts\python -m pip install -r scripts/quality_bench/requirements.txt` -- expected : installation sans erreur.
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` -- expected : tout passe, sans réseau ni Ollama.
- `.venv-quality\Scripts\python -m pytest tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` -- expected : passe (pas de venv d'app sur la tour).
- `uvx ruff@0.14.9 check scripts/quality_bench tests/quality_bench`, `uvx black@25.12.0 --check scripts/quality_bench tests/quality_bench`, `uvx isort@7.0.0 --profile black --check scripts/quality_bench tests/quality_bench` -- expected : vert.
- `.venv-quality\Scripts\python -m scripts.quality_bench report --help` -- expected : code 0.
- `git status --porcelain` -- expected : aucun chemin sous `data/` ni `benchmarks/`.

## Auto Run Result

Status: done

**Résumé :** noyau pur `stats/` (unités par minimum puis moyenne des seeds, Wilson, ET groupée, McNemar exact, différence appariée et test z, Holm explicite, BH pour la matrice, k̂_Bonferroni, bootstrap apparié par groupes, groupes indiscernables par meneurs successifs, IC simultanés et rang approché, Spearman et sa conclusion) et sous-commande `report --campaign <c> [--partial] [--aa-date AAAA-MM-JJ]`. Elle contrôle la complétude (clés attendues depuis le manifeste et le jeu, même sélection que le runner), refuse une campagne incomplète, en attente du juge ou discordante sauf `--partial`, puis réécrit `benchmarks/quality/<c>/` en liste blanche : `scores/<modèle>.jsonl` (`qb.score/1`), `summary.json` (`qb.report/1`), `manifest.json`, `report.md` en français et graphiques SVG à la charte Wavestone.

**Fichiers modifiés :**
- `scripts/quality_bench/stats/` -- noyau statistique pur (numpy, scipy, statsmodels seulement).
- `scripts/quality_bench/report/` (`inputs`, `campaign`, `export`, `markdown`, `charts`, `commands`) -- lecture et contrôles, agrégats, exports, rapport, graphiques, sous-commande.
- `scripts/quality_bench/common/selection.py`, `generation/runner.py` -- résolution de `selection` partagée par le runner et le rapport.
- `scripts/quality_bench/common/schemas.py`, `common/paths.py` -- `qb.score/1`, `qb.report/1`, `qb.aa_reference/1` ; chemins d'export et de références, dossiers réservés.
- `scripts/quality_bench/__main__.py`, `requirements.txt`, `questions/SOURCES.md` -- sous-commande, dépendances, section « Rapport » et format du fichier AA.
- `tests/quality_bench/` -- `test_stats`, `test_report_command`, `test_report_imports`, `test_report_render`, `report_factories` ; ajouts à `test_exports`, `test_schemas`, `test_package`, `test_paths`, `conftest`.

**Revue :** 43 constats (medium 13, low 24, false 6). Patchs : 7 entrées medium (attente du juge écartée, `question_id` retirés du manifeste exporté, ET groupée indéfinie sous 2 groupes, tests du nom réservé, de la sélection, des refus et du rendu) et 7 entrées low (casse des dossiers réservés et des fichiers de scores, gains k̂, libellé m − 1, « sans score », index AA non fini, b et c d'une paire vide). Reporté : 1 entrée medium (moyennes non appariées pour le meneur, règle d'AD-10). Rejetés : 6 false et 14 low, raisons dans le journal ci-dessus.

**Revue de suivi recommandée :** oui. Sept entrées medium ont été patchées dans cette passe (patchés par verdict : medium 7, low 7). Risque non vérifié : la réduction de `selection.ids` dans la copie exportée du manifeste et l'ET groupée rendue indéfinie sous deux groupes changent des valeurs publiées ; aucune passe de revue ne les a relues.

**Vérification :**
- `.venv-quality\Scripts\python -m pytest tests/quality_bench` : 1 051 passés, sans réseau ni Ollama.
- `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` : 8 passés. Le reste de `tests/unit` n'a pas tourné, faute de venv d'app sur la tour.
- ruff 0.14.9, black 25.12.0, isort 7.0.0 (par `uvx --offline`) : verts.
- `report --help` : code 0. Aucune génération ni aucun appel réseau.
- `git status` : aucun chemin sous `data/` ni `benchmarks/`.

**Risques résiduels :**
- Aucun fichier réel `benchmarks/quality/references/aa-<AAAA-MM-JJ>.json` : le code et les tests ne s'appuient que sur des fixtures synthétiques ; le fichier est à fournir par Anaël (format dans SOURCES.md).
- p de Spearman par l'approximation t de `spearmanr` : sur petit effectif, elle diffère un peu des seuils exacts cités dans statistiques.md.
- Moyennes non appariées pour le meneur et le rang (reporté).
