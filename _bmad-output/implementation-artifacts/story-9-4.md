---
title: 'Story 9.4 : Installer le modèle de représentation depuis la Base documentaire'
type: 'feature'
created: '2026-10-21'
status: 'review'
baseline_commit: '4472c5c'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
warnings: []
deferred: []
---

# Story 9.4 : Installer le modèle de représentation depuis la Base documentaire

## Objectif

Sans modèle d'embedding installé, importer un document échouait avec un message qui renvoyait à
une commande à taper dans un terminal (`ollama pull nomic-embed-text`). La maquette validée
(story 9.6, décision d'Anaël du 2026-10-21) propose un encart d'alerte, avant tout le reste de
l'écran Base documentaire, avec un bouton qui installe le modèle par le même run `pull` que l'écran
Modèles (AD-17).

## Critères d'acceptation et preuves

1. **Encart avant tout import, zone désactivée avec sa raison** : `documents-embedding-alert.js`
   (nouveau), monté par `documents-base.js` juste après le fil d'Ariane, avant la zone de dépôt.
   Visible seulement si `GET /api/rag/settings.embedding_models` est vide ; alors la zone de dépôt
   (`choose`, `Importer des documents`, le champ fichier) est désactivée et `#docs-drop-embedding-reason`
   dit pourquoi (`documents.css` : `.docs-drop[data-blocked="true"]`, fond et texte du thème, jamais
   la seule opacité). Preuve : `tests/v2/e2e/test_documents_embedding.py::test_the_alert_precedes_the_screen_and_disables_the_drop_zone`.
2. **Même run `pull`, même composant de progression, « Annuler » compris** : `documents-embedding-alert.js`
   crée son propre `pull` avec `createPull` de `models-pull.js` (celui de l'écran Modèles), tag fixe
   `nomic-embed-text` ; `api.pullModel("nomic-embed-text")` est la même route `POST /api/models/pull`.
   À la fin (succès), l'encart relit les réglages et disparaît dès que `embedding_models` n'est plus
   vide ; aucun autre modèle n'étant installé, c'est déjà le seul embedding disponible et
   `rag/ingest.py._pick_model` le prend par défaut (son choix de repli, sans réglage explicite) :
   « Par défaut (le premier modèle installé) » dans le menu des réglages de la base. Preuve :
   `test_clicking_installs_through_the_models_pull_route_and_the_alert_disappears` (octets scriptés
   par le faux Ollama HTTP `ThreadedOllama`, comme `test_models_install.py` ; `GET /api/rag/settings`
   relu après le run rend `embedding_models == [{"tag": "nomic-embed-text", "name": "nomic-embed-text"}]`).
3. **Tag et taille vérifiés par une installation réelle, pas de mémoire** : `ollama pull nomic-embed-text`
   exécuté pendant la story sur le poste de développement (Ollama local 0.35.1, aucun modèle
   d'embedding installé au départ). Résultat : `nomic-embed-text:latest` installé, **274 302 450
   octets** (`ollama list` : 274 MB ; `/api/tags` : `size: 274302450`, soit ≈ 0,274 Go), repris tel
   quel dans `i18n/fr/docs.json` (`embedding_alert_size: "274 Mo"`). Le modèle a été désinstallé
   (`ollama rm nomic-embed-text`) avant l'implémentation pour ne garder, pendant la story, que
   `granite4:350m` (déjà présent) comme seul modèle de conversation touché — aucun autre
   téléchargement.
4. **`errors.py` (`no_embedding_model`) renvoie au bouton, pas à une commande** : action remplacée par
   « Installez-le depuis le bouton « Installer nomic-embed-text » de la Base documentaire, puis
   réessayez. » (plus de `` `ollama pull nomic-embed-text` `` dans le texte). Testé par
   `tests/v2/web/test_rag_api.py` (présence `message`/`action` non vide pour ce code, inchangé).
5. **Ollama absent → bouton désactivé avec la raison existante** : `createEmbeddingAlert` suit
   `state.ollama.known/up` du store global (même mécanisme que l'écran Modèles,
   `models.actions.install_ollama_down`) ; sans Ollama, le bouton porte `aria-disabled="true"` et
   `#docs-embedding-alert-reason` dit « Ollama ne répond pas : démarrez-le pour installer un
   modèle. ». Preuve : `test_without_ollama_the_install_button_is_disabled_with_the_reason`.
6. **Textes français, icônes Material, contrastes de la story 8.2** : `i18n/fr/docs.json`
   (`embedding_alert_*`), icône `warning` du sprite partagé (`core/dom.js :icon`), liseré
   `var(--color-chart-4)` sur fond `var(--color-surface-alt)` — le même jeton que les encarts
   d'avertissement existants (`.models-card-warning`, `.arena-judge-alert`) ; `amber-strong` (jeton
   dédié visé par EXPERIENCE.md) est hors périmètre, réservé à la story 9.7 qui pose les jetons de
   `tokens.css`/`screens.css` pour toute la refonte visuelle — ici l'encart reprend les composants
   existants, comme demandé. `test_catalog_and_index_use_non_breaking_spaces_before_high_punctuation`
   (espaces insécables avant `:`/`»`/après `«`) est vert sur les nouveaux textes.
7. **Tests unitaires/web/E2E** :
   - `tests/v2/unit/test_rag_manage_settings_view.py` (nouveau) : `offline_settings_view` sans
     registre ni `fallback_model` rend `embedding_models == []` ; avec `fallback_model`, le modèle y
     figure.
   - `tests/v2/unit/test_embedder.py` : `test_testing_no_fake_embedder_simulates_a_machine_without_any_embedding`
     (nouveau réglage `WAVELOCALAI_TESTING_NO_FAKE_EMBEDDER`, E2E seulement — voir « Fichiers »).
   - `tests/v2/web/test_rag_manage_api.py::test_the_settings_start_from_the_toml_defaults` : réaligné
     (`embedding_models` n'est plus `[]` en mode `testing` ordinaire, le `fake` sert de dernier
     recours — voir point suivant).
   - `tests/v2/e2e/test_documents_embedding.py` (nouveau, 3 tests) : encart + zone désactivée ;
     installation réelle du mécanisme (faux Ollama HTTP, octets scriptés) et disparition de l'encart ;
     Ollama absent. `assert_no_axe_violations` sur le premier.
   - Aucun test existant de `test_documents.py`/`test_rag_*` n'était à réaligner pour un « embedding
     déjà présent » : ils tournent tous avec `WAVELOCALAI_TESTING=1` sans Ollama (port fermé), où le
     `fake-embed:16` servait déjà de dernier recours à l'ingestion (`IngestService.fallback_model`,
     story 4.2) **mais n'apparaissait pas** dans `GET /api/rag/settings.embedding_models` (il n'est
     pas dans `registry.list_models()`, qui ne connaît qu'Ollama). Avec le nouvel encart, ce décalage
     aurait rendu l'écran Base documentaire inutilisable dans toute la suite E2E existante (encart
     affiché, import bloqué) alors que l'ingestion fonctionnait réellement derrière. Corrigé en
     prolongeant le même mécanisme de dernier recours jusqu'à la vue des réglages
     (`RagBaseService.fallback_model`, point 8) : le `fake` y figure désormais aussi, comme à
     l'ingestion — aucun test de `test_documents.py` n'a donc eu besoin d'être changé. Le nouveau
     réglage `WAVELOCALAI_TESTING_NO_FAKE_EMBEDDER` (E2E seulement, jamais en `testing` ordinaire)
     retire ce filet pour les 3 tests qui prouvent justement l'état « aucun embedding ».
8. **Pas d'autre comportement changé** : `RagBaseService` et `offline_settings_view` gagnent un
   paramètre optionnel `fallback_model` (le `fake` des tests, comme `IngestService` le fait déjà
   depuis la story 4.2) ; `None` partout en production (`next(iter(app.state.embedders), None)` est
   toujours `None` hors `Settings.testing`), donc aucun effet hors tests.

## Règles écrites

- Périmètre strict story 9.4 : un seul écran (Base documentaire), un seul modèle proposé
  (`nomic-embed-text`), aucun changement à l'écran Modèles ni au reranker (stories 5.3/5.5).
- `amber-strong` et la refonte visuelle complète de l'encart restent à la story 9.7/9.8 (consigne de
  la story) : l'encart reprend `var(--color-chart-4)` et les classes déjà posées par `.agents-warning`
  / `.models-card-warning`.
- `documents-base.js` reste sous la limite de 600 lignes (`test_new_front_files_stay_under_the_size_budget`,
  `test_no_front_script_exceeds_600_lines`) : la logique de l'encart (état, `pull`, abonnement au
  flux système, relecture des réglages) vit entièrement dans `documents-embedding-alert.js`, que
  `documents-base.js` instancie avec quatre callbacks (`host`, `say`, `onChange`, `onInstalled`).

## Fichiers

- Code : `src/wavelocalai/errors.py` (`no_embedding_model`), `src/wavelocalai/config.py`
  (`testing_no_fake_embedder`, E2E seulement), `src/wavelocalai/models/fake.py` (`fake_embedders`),
  `src/wavelocalai/rag/manage.py` (`RagBaseService.fallback_model`, `_settings_view`,
  `offline_settings_view`), `src/wavelocalai/web/app.py`, `src/wavelocalai/web/routes_rag_base.py`.
- Front : `src/wavelocalai/web/static/screens/documents-embedding-alert.js` (nouveau),
  `documents-base.js`, `documents.css`, `i18n/fr/docs.json`.
- Tests : `tests/v2/unit/test_rag_manage_settings_view.py` (nouveau), `tests/v2/unit/test_embedder.py`,
  `tests/v2/unit/test_documents_static.py`, `tests/v2/web/test_rag_manage_api.py`,
  `tests/v2/e2e/test_documents_embedding.py` (nouveau).

## Rapport de dev

- Essai réel (seul téléchargement autorisé) : `ollama pull nomic-embed-text` en ligne de commande,
  Ollama 0.35.1 déjà démarré sur le poste. Tag et taille au paragraphe 3 ci-dessus. Modèle retiré
  (`ollama rm`) avant le reste du développement ; aucun autre modèle téléchargé (le mécanisme du
  bouton est prouvé en E2E par un faux Ollama HTTP, octets scriptés, comme l'installation d'un
  modèle de l'écran Modèles).
- Tests ciblés : `tests/v2/unit tests/v2/web -k "embed or documents or rag or pull or errors"` →
  387 passed (1 échec préexistant hors périmètre : `test_rag_run_api.py::test_a_cloud_model_needs_allow_cloud`,
  confirmé identique sur la base non modifiée — `git stash` puis relance). `tests/v2/unit` complet :
  1313 passed, 5 skipped. `tests/v2/web` complet : 5 échecs, tous des budgets de lecture à 300 ms
  (`test_read_budget.py`, `test_references_api.py`, `test_system.py`) sous charge du poste pendant
  des lancements concurrents de la suite ; aucun ne touche la Base documentaire ni l'embedding.
  E2E ciblés (`tests/v2/e2e/test_documents_embedding.py -m e2e`, Edge) : 3 passed.
- Contrôle rapide (ruff, black, isort sur les fichiers Python touchés) : propre après reformatage
  (`uvx black@25.12.0`) de `rag/manage.py` et `test_rag_manage_settings_view.py`.
- Reports : aucun — le périmètre de l'AC est couvert dans cette story.

## Revue

Revue Opus du 2026-10-21, sur `origin/master` à jour (4472c5c, pas de rebase nécessaire), second avis Haiku repris point par point.

- medium · second avis 1 · corrigé : le modèle installé ne devenait le défaut que par la règle implicite « premier installé » (et un modèle du `.toml` absent du poste l'emportait). À la fin du `pull`, l'encart enregistre `embedding_model = nomic-embed-text` par `PUT /api/rag/settings` (API existante, préférence AD-15), puis relit ; base déjà liée à un autre modèle : le 409 est ignoré et la relecture montre l'état réel.
- medium · second avis 2 · corrigé : l'E2E assert `settings["embedding_model"] == "nomic-embed-text"` ; vérifié qu'il échoue sans le correctif.
- low · second avis 3 · rejeté : avant la première lecture des réglages, un import resterait refusé par le serveur (`no_embedding_model`, `ingest._pick_model`) ; bloquer la zone de dépôt pendant cette lecture désactiverait l'import à chaque ouverture de l'écran pour tous les postes équipés.
- low · second avis 5 · rejeté : « Annuler » vient du composant partagé `models-pull.js`, déjà cliqué dans `test_models_install.py` ; l'E2E prouve qu'il est présent dans l'encart.
- low · second avis 8 · noté : « 274 Mo » est un texte fixe de `docs.json` (le modèle n'est pas dans le catalogue), mesuré par l'installation réelle ci-dessus ; à remesurer si le tag proposé change.
- low · second avis 9 · corrigé : le message `no_embedding_model` (reçu aussi par la Discussion) dit où trouver le bouton : « Ouvrez la Base documentaire et cliquez sur « Installer nomic-embed-text », puis réessayez. »
- low · second avis 10 · corrigé : le filtre `is_baseline_file` de `.secrets.baseline` n'était pas nécessaire (hook detect-secrets vert sur les fichiers de la story avec la baseline de master) ; baseline remise à l'identique de master. Le `pragma: allowlist secret` du test reste nécessaire (le hook signale la ligne sans lui).
- info · second avis 11 · reporté à l'orchestrateur : `test_rag_run_api.py::test_a_cloud_model_needs_allow_cloud` échoue seul aussi sur `origin/master` en local (délai de 5 s de `_ended` dépassé) ; CI de master verte, sans lien avec la story.
- Complexité : 0 constat (aucune structure qui grossit pendant l'exécution).
