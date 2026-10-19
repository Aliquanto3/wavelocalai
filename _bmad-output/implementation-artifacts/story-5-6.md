---
title: 'La fiche modèle explique son débit et ce qu''il donne sur d''autres postes'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '7dd7620'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-3.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-4.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-5.md'
warnings: []
deferred:
  - summary: >-
      Aucun résultat réel `qb.results/1` n'est synchronisé sur `master` (décision Q7 : la story part sans eux) : `benchmarks/slm-quality/` ne contient que son README, et la story n'y crée ni n'y édite rien (AGENTS.md). La lecture du format est faite contre le schéma publié par slm-quality-bench (`docs/schemas/qb.results-1.schema.json`, dépôt frère) et testée avec une fixture `tests/v2/fixtures/slm-quality-results.sample.json`, qui valide ce schéma (`jsonschema`). Variante conservatrice : sans résultat publié, la fiche dit « Références indisponibles » et ce qui manque ; `ModelInfo.accuracy` reste `null` (la règle du juge d'après la précision de la 1.6 ne s'active qu'avec un vrai fichier). À vérifier à la première synchro réelle : la jointure `(model, digest)` (empreinte complète d'Ollama contre empreinte du banc), le choix du poste « PC pro » et les unités (`*_mib`).
    evidence: |-
      `models/bench_results.py`, `tests/v2/unit/test_bench_results.py`, `tests/v2/web/test_model_card_api.py`, `tests/v2/e2e/test_models_card.py`.
    location: src/wavelocalai/models/bench_results.py
    severity: medium
  - summary: >-
      Écarts non couverts par les décisions du 2026-10-19 : variante conservatrice gardée. (1) Lecture dans `models/bench_results.py`, pas dans `models/catalog.py` (AD-22 le nomme, mais `catalog.py` lit `config/models_catalog.json` et le banc sert aussi les stories 5.7 et 5.8) ; `BenchReferences` se relit à la modification du fichier (date et taille), dans un fil. (2) « Les trois postes de référence » : le fichier publie une liste `machines[]` ; la fiche en montre six au plus, le PC pro d'abord, et dit quand aucun poste de 16 Go sans GPU n'est publié. « PC pro » = aucune carte graphique et de 14 à 18 Gio de mémoire vive. (3) Plusieurs résultats pour un même poste : la piste `think_off`, puis le résultat complet, puis la campagne la plus récente. (4) `accuracy` = médiane de `quality.global.score` sur les mêmes poids (même empreinte) seulement : jamais le score d'une autre version (AD-22) ; un modèle « autre version » a ses débits affichés avec la mention, pas de précision. (5) Licence : `/api/show` la publie en texte intégral, que `model_facts` ne garde pas (une colonne et une relecture des lignes déjà en cache seraient nécessaires) ; la fiche lit un champ facultatif `license` du catalogue (absent aujourd'hui : « inconnu »). À reprendre avec une migration si la licence doit s'afficher pour tout modèle installé. (6) Bande passante mémoire : aucune source sur ce poste ; `bandwidth_gb_s` reste `null` et la phrase de « Pourquoi ce débit ? » dit qu'elle n'est pas mesurée, sans plafond théorique. La VRAM vient de la dernière lecture du GPU du flux système (`SystemSampler.last_gpu`), `null` avant la première lecture ou sans GPU. (7) Routeur : `core/router.js` gagne un `update(host, params)` facultatif d'un écran, pour qu'un changement de `#/modeles/<tag>` ne remonte pas l'écran (installation, listes et défauts gardés) ; sans lui, le comportement est celui d'avant. (8) Le bouton « Fiche du modèle » est posé par un observateur du document (`components/model-card-launcher.js`) à côté de chaque `wl-model-picker`, y compris ceux des Epics 6 et 7 : `wl-model-picker.js` n'a pas grandi, et un sélecteur peut s'en passer avec `data-no-card`. En mode `multi` (l'Arène), un bouton « Fiche : <nom> » par modèle choisi. Le panneau est flottant et non modal (aside étiqueté, Échap le ferme et rend le focus) ; il ne porte pas « Installer » : l'installation reste dans l'écran Modèles, auquel un lien mène. (9) Un modèle du catalogue : les mémoires viennent de la même estimation que `GET /api/models/catalog` (modèles chargés comptés comme libres) ; un modèle cloud a une fiche presque vide, sans « Pourquoi ce débit ? ».
    evidence: |-
      `models/card.py`, `models/registry.py::card_source`, `web/routes_models.py::model_card`, `components/model-card-*.js`, `screens/models-card.js`, `core/router.js`, `contrat-api.md` (« Modèles : fiche »).
    location: src/wavelocalai/models/card.py
    severity: low
---

# Story 5.6 : la fiche modèle explique son débit et ce qu'il donne sur d'autres postes

## Objectif

Sur `#/modeles`, un clic sur un modèle ouvre sa fiche : dense ou MoE, paramètres totaux et actifs, quantification, licence, contexte, outils et raisonnement vérifiés, « Pourquoi ce débit ? » (le débit mesuré sur ce poste expliqué par les paramètres actifs, la quantification et la mémoire vidéo) et « Sur d'autres postes » (débit, tenue en mémoire et énergie publiés par le banc pour le PC pro de 16 Go sans GPU et les autres postes de référence). Le même panneau s'ouvre depuis le bouton « Fiche du modèle » de chaque sélecteur de modèle, sans changer d'URL.

## Critères d'acceptation et preuves

1. **Lecture des résultats** (AD-22) : `BenchReferences` lit `benchmarks/slm-quality/slm-quality-results.json` (jamais par le réseau, `extra="ignore"`), une fois puis à sa modification ; absent, illisible, `schema` autre que `qb.results/1` ou mal formé : références indisponibles avec une raison, sans échec de route. La jointure est `(model, digest)` ; un modèle installé correspond par `(tag, digest)`, à défaut par tag avec « autre version ». Preuve : `unit/test_bench_results.py`, `web/test_model_card_api.py::test_without_results_*`, `::test_a_file_of_another_schema_*`, `::test_the_card_follows_a_change_*`.
2. **Précision** : `ModelInfo.accuracy` est la médiane du score global des mêmes poids, `null` sans mesure ni pour une autre version (jamais 0). Preuve : `web/test_model_card_api.py::test_the_models_list_gets_the_published_accuracy_*`, `unit/test_bench_results.py::test_accuracy_*`.
3. **Budget** : `GET /api/models/card/{tag}` répond en moins de 300 ms Ollama injoignable (la route a un paramètre de chemin : le test de découverte ne la voit pas, d'où un test propre) ; aucun appel d'Ollama avant de répondre. Preuve : `web/test_model_card_api.py::test_the_card_answers_under_300_ms_*`.
4. **Fiche** : architecture, paramètres, quantification, licence, contexte, outils et raisonnement, « inconnu » pour une valeur absente (jamais 0, ni « non » pour une capacité qu'aucune source ne publie) ; panneau à droite dès 1 120 px, au-dessus en deçà, 320 px sans défilement de la page ; `#/modeles/<tag>` l'ouvre (tag à `/` encodé), un clic l'ouvre sans remonter l'écran ; un modèle non installé qui ne tient pas porte « Installer quand même » (D-42). Preuve : `web/test_model_card_api.py::test_an_installed_model_*`, `::test_a_catalog_model_*`, `e2e/test_models_card.py::test_clicking_a_model_*`, `::test_the_card_opens_directly_*`, `::test_the_card_shows_its_traits_*`, `::test_a_model_not_installed_*`, `::test_the_panel_is_on_the_right_*`, `::test_an_unknown_tag_*`.
5. **Bouton du sélecteur** : « Fiche du modèle » à côté du `wl-model-picker`, hors de sa liste d'options, ouvre la même fiche en panneau sans changer l'URL ; Échap le ferme et rend le focus. Preuve : `e2e/test_models_card.py::test_the_picker_has_a_card_button_*`, `::test_the_card_button_is_outside_*`, `unit/test_model_card_static.py::test_the_launcher_*`.
6. **« Pourquoi ce débit ? »** : phrases du serveur (paramètres actifs, quantification, VRAM ou mémoire vive, bande passante non mesurée, débit mesuré), aucun calcul à l'écran. Preuve : `web/test_model_card_api.py::test_the_throughput_is_explained_*`, `::test_a_model_larger_than_the_vram_*`, `::test_without_a_gpu_*`, `unit/test_model_card_static.py::test_the_front_calculates_nothing_*`, `e2e::test_why_this_throughput_*`.
7. **« Sur d'autres postes »** : le PC pro d'abord, débit, mémoire vive au pic, part en mémoire vidéo et énergie ; `null` « inconnu », fractions en pourcentage, énergie seulement si `status = "measured"`, mention « autre version », « pas dans les résultats publiés », « références indisponibles ». Preuve : `web/test_model_card_api.py::test_other_posts_*`, `::test_energy_is_given_only_*`, `::test_a_null_stays_unknown_*`, `::test_another_digest_*`, `e2e::test_other_posts_list_*`, `::test_a_null_is_unknown_*`, `::test_another_digest_says_*`, `::test_without_the_results_file_*`.
8. **Accessibilité et structure** : axe-core sans violation (fiche ouverte, « autre version », panneau d'un sélecteur, références indisponibles ; clair et sombre) ; aucun JS ni CSS au-delà de 600 lignes ; couches respectées. Preuve : `e2e::test_axe_*`, `unit/test_model_card_static.py`, `unit/test_models_static.py`, `unit/test_layers.py`.

## Hors périmètre

Les défauts `agent` et `rag` calés sur le banc (5.7), « Quel modèle pour quel usage » et la page des références (5.8) : ils réutilisent `models/bench_results.py`. Aucune synchro de résultats, aucun fichier sous `benchmarks/`.

## Notes de développement

- Serveur : `models/bench_results.py` (lecture, jointure, précision, résultat retenu par poste), `models/card.py` (`CardSource`, `ModelCard`, `why_lines`, `build_references`), `models/registry.py` (`bench`, `accuracy` de `list_models`, `card_source`), `models/catalog.py` (champ facultatif `license`), `web/routes_models.py` (`GET /api/models/card/{tag}`, `_reclaimable_gb` partagé avec le catalogue), `web/system_state.py` (`SystemSampler.last_gpu`).
- Front : `components/model-card-view.js` (rendu), `model-card-loader.js` (lecture après `shell-ready`, états), `model-card-drawer.js` (panneau d'un sélecteur), `model-card-launcher.js` (bouton posé par un observateur), `screens/models-card.js` (panneau de l'écran), `models.js` (disposition `.models-layout`, `update`), `models-format.js` (nom de modèle = lien vers la fiche), `core/router.js` (`update`), `core/routes/models.js` (`param: "tag"`), `core/api/models.js` (`modelCard`), `i18n/fr/models.json` (`models.card.*`), `models.css`.
- Contrat : sous-section « Modèles : fiche (story 5.6) » de `contrat-api.md` ; la ligne « Modèles » dit désormais que `accuracy` vient de `qb.results/1`.
- Tests réalignés : `unit/test_models_static.py` (nouveaux fichiers, `param: "tag"` du registre). Fixture : `tests/v2/fixtures/slm-quality-results.sample.json` (valide le schéma publié).

## Rapport de dev

- Joué (poste partagé : jamais la suite complète) : `tests/v2/unit` en entier ; `tests/v2/web` ciblé (`test_model_card_api`, `test_read_budget`, `test_models*`, `test_models_manage_api`) ; E2E Edge `test_models_card` (18), `test_models_install`, `test_models_manage`, `test_models_reranker`, `test_picker` (70), puis `test_chat`, `test_arena`, `test_documents`, `test_shell`, `test_components` (le bouton du sélecteur est posé sur tous les écrans).
- Aucune dépendance nouvelle, aucun fichier d'état touché, aucun fichier de `benchmarks/` créé.

## Revue

Revue Opus du 2026-10-19 sur `f095fea` (5.5 finale et `origin/master` fusionnées), avec le second avis Haiku.

- medium · second avis 1 · corrigé : un choix posé par le code (`picker.value(s) = …` : garde-fou mémoire, reprise d'Arène, Discussion, Documents) ne levait aucun événement, la fiche ouvrait le modèle écarté. `model-card-launcher.js` observe le sous-arbre de chaque sélecteur (qu'il redessine à chaque affectation) et ne refait les boutons que si le choix ou les noms changent ; `wl-model-picker.js` n'a pas grandi. Preuve : `e2e/test_models_card.py::test_the_card_button_follows_a_choice_made_by_code_*` (échoue sur l'ancien lanceur).
- medium · second avis 2 · corrigé : le débit de « Pourquoi ce débit ? » était arrondi à l'entier (12,7 → 13, 0,4 → 0) alors que le front écrit 12,7. `card._rate` garde trois chiffres significatifs comme `formatRate`. Preuve : `unit/test_model_card_why.py`.
- medium · second avis 3 · corrigé : la fiche d'un modèle du catalogue lisait `/api/ps` (jusqu'à 1 s) avant de répondre, contre AD-15 et le critère 3. Elle prend la mémoire des modèles chargés du dernier échantillon du flux système (`SystemSampler.last_loaded_gb`) ; le catalogue garde sa lecture. Preuve : `web/test_model_card_api.py::test_a_catalog_card_reads_the_sampled_loaded_models_*` (aucun appel, même `short_gb` et `fits` que le catalogue).
- low · second avis 4 · corrigé : « campagne la plus récente » = date de fin publiée (`last_line_at`, à défaut `first_line_at`), puis rang dans `campaigns[]`. Preuve : `unit/test_bench_results.py::test_the_most_recent_campaign_*`.
- low · second avis 5 · corrigé : un modèle installé sans empreinte lisait « n'est pas installé » ; nouvelle clé `models.card.unknown_version_installed_note`.
- low · second avis 6 · corrigé : espaces insécables dans `energy_value` (« Wh/1 000 tokens ») et `no_pc_pro` (« 16 Go »).
- low · second avis 7 · corrigé : un sélecteur déplacé garde ses boutons contre lui ; un sélecteur retiré rend aussi ses écouteurs et son observateur (relevé de la revue).
- low · revue, complexité · corrigé : `LoadedBench.find` parcourait tous les résultats du fichier pour chaque modèle de `GET /api/models` (O(modèles × résultats)) ; résultats groupés par tag de base au chargement.
- info · revue · rejeté : l'observateur du document coûte, par mutation, un `querySelectorAll` sur le sous-arbre ajouté, du même ordre que le rendu qui l'ajoute (Markdown de la Discussion déjà espacé) : pas de coût au-delà de O(n) par événement ; Arène, Discussion, Documents et sélecteur rejoués sans régression.
- info · revue · rejeté : le hook `update` du routeur est facultatif et ne change rien aux écrans qui ne l'exportent pas ; pas de nouvelle course (même absence de contrôle du jeton après `await` que le démontage d'avant).
- low · revue · reporté : avant le premier échantillon du flux système, la fiche d'un modèle du catalogue ne compte pas les modèles chargés comme libres (estimation prudente, « ne tient pas » possible alors que le catalogue dit « tient »). À vérifier en usage réel avec le shell ouvert (le flux est échantillonné en continu) ; sinon, amorcer un échantillon au démarrage.
- low · revue · corrigé : `e2e/test_models_card.py::test_an_unknown_tag_*` attendait des espaces ordinaires autour du tag, alors que `models.card.not_found_text` porte des espaces insécables : le test échouait. Assertion alignée sur le texte.
- Tests de la revue (poste partagé, ciblés) : `tests/v2/unit` en entier, `tests/v2/web` (`test_model_card_api`, `test_read_budget`, `test_system`, `test_models*`) : 1 236 passés, 6 ignorés ; E2E Edge `test_models_card`, `test_picker`, `test_chat*`, `test_arena*`, `test_documents*` : 266 passés après la correction ci-dessus.
