---
title: 'Décharger, supprimer un modèle et choisir ses défauts'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '2dbb19d'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-5-3.md'
warnings: []
deferred:
  - summary: >-
      Écart nouveau, non couvert par les décisions du 2026-10-19 : variante conservatrice gardée. (1) Les critères d'`epics.md` disent « Définir par défaut » ; EXPERIENCE.md (qui prime pour le comportement) et la maquette disent « Changer » puis « Enregistrer » / « Annuler » et « Revenir au choix automatique » : ce sont ces libellés. (2) Éligibilité à l'usage (décision n° 17) : `epics.md` ne la définit pas ; la maquette la donne (`agent` : outils vérifiés et 3 B actifs, `rag` : 3 B actifs). Reprise telle quelle, calculée par le serveur (`models/defaults.py::is_eligible`), sans regard à la mémoire (un modèle qui ne tient pas se choisit) ; les modèles cloud sont éligibles sauf pour l'Arène ; `arena` demande 2 à 3 modèles locaux. (3) Le filtre du sélecteur est un attribut facultatif `eligible-only` : le Chat, l'Arène et la Discussion gardent leur sélecteur inchangé (tout modèle de conversation) ; les sélecteurs des Epics 6 et 7 (Agent, Évaluation) décideront de l'employer. (4) Le serveur écrit un défaut avec `PUT /api/models/defaults/{purpose}` `{tags, allow_cloud}` ; sans `allow_cloud`, un tag cloud est refusé (`403 cloud_not_allowed`). La raison du choix est « Choisi par vous » (le texte précédent, « Votre choix enregistré pour cet usage. », n'était lu par aucun test v2). (5) `GET /api/models/defaults` gagne `eligible` et `inactive` : un choix cloud enregistré tant que le cloud n'est pas autorisé tombe sur la règle et l'écran le dit (« inactif tant que le cloud n'est pas autorisé », EXPERIENCE.md), « Revenir » restant offert.
    evidence: |-
      `models/defaults.py` (`is_eligible`, `ModelDefaults.choose`, `.get`), `web/routes_models.py`, `screens/models-defaults.js`, `components/wl-model-picker.js` (`eligible-only`), `tests/v2/web/test_models_manage_api.py::test_the_defaults_say_*`, `::test_an_ineligible_model_*`, `::test_a_cloud_choice_*`, `tests/v2/e2e/test_models_manage.py::test_the_picker_proposes_*`.
    location: src/wavelocalai/models/defaults.py
    severity: medium
  - summary: >-
      Choix de conception à confirmer, variante conservatrice dans chaque cas. (1) « Utilisé par un run actif » vient d'un champ ajouté au flux système, `models_in_use` (`{tag: run_id}`, `hub.active_models()`), plutôt que d'un champ de `runs_active` (que `test_system` fige) ; un run `pull` d'un modèle installé l'emploie aussi. (2) Supprimer décharge d'abord le modèle (sinon il reste en mémoire) et traite le `404` d'Ollama comme une suppression réussie ; le contrôle d'usage est refait entre le déchargement et l'appel d'Ollama. (3) Les préférences qui visaient le modèle sont effacées (pas seulement ignorées à la lecture) : réinstallé, il ne redevient pas un défaut sans un nouveau geste (« jamais retenu sans geste », décision Q2) ; le critère « retombe sur la règle » est tenu dans les deux cas. (4) Le dialogue ne nomme que les usages dont le défaut est un choix de la personne (liste lue à la dernière relecture de l'écran), pas ceux que la règle donne. (5) « Décharger » annonce « 2 modèles déchargés. » puis, s'il y a lieu, les modèles gardés (un run les emploie) et ceux qu'Ollama a refusés. (6) La liste de l'écran suit le mode cloud (relue quand il change) pour nommer un défaut cloud ; « Sur ce poste » ne montre toujours que les modèles locaux. (7) Dans le tableau des défauts, la liste du sélecteur s'ouvre dans la cellule (la zone du tableau, qui défile, rognerait une liste flottante) ; la ligne s'agrandit. (8) Nom accessible des boutons : « Changer le modèle de l'usage Agent », « Revenir au choix automatique pour l'usage Agent », « Supprimer <nom> ».
    evidence: |-
      `runs/hub.py::active_models`, `web/system_state.py`, `inference/delete.py`, `models-delete.js`, `models-unload.js`, `models.css`, `tests/v2/e2e/test_models_manage.py`.
    location: src/wavelocalai/inference/delete.py
    severity: low
  - summary: >-
      Rien n'a été supprimé ni déchargé pour de vrai : la suppression passe par un faux Ollama (`FakeOllama`, `ThreadedOllama`), jamais par le vrai `http://127.0.0.1:11434`. L'appel `DELETE /api/delete` avec `{"model": tag}` est celui que documente Ollama ; le `404` d'un modèle absent et le texte d'erreur d'un refus (disque, droits) sont à vérifier à la recette sur un modèle jetable, comme l'effet sur la mémoire (déchargé avant la suppression).
    evidence: |-
      `models/ollama_delete.py`, `tests/v2/unit/test_model_delete.py`, `tests/v2/pull_fake.py::ThreadedOllama.do_DELETE`.
    location: src/wavelocalai/models/ollama_delete.py
    severity: medium
---

# Story 5.4 : décharger, supprimer un modèle et choisir ses défauts

## Objectif

Sur `#/modeles`, un consultant libère la mémoire avant une démo (« Décharger les modèles inactifs »), supprime un modèle après confirmation chiffrée, et choisit le modèle proposé par défaut pour chaque usage (Conversation, Arène, Juge, Agent, Documents) ; ses choix survivent d'une séance à l'autre.

## Critères d'acceptation et preuves

1. **Décharger** : le bouton appelle `POST /api/models/unload` (4.8) ; la colonne « Chargé » et la mémoire libre suivent le flux système (publié aussitôt), le résultat est annoncé (« 2 modèles déchargés. »). Désactivé (`aria-disabled`, raison visible) quand Ollama est muet, qu'aucun modèle n'est chargé ou que tous servent à un run ; un modèle employé par un run est gardé. Preuve : `e2e/test_models_manage.py::test_unload_*`.
2. **Supprimer** : « Supprimer » ouvre `wl-confirm-dialog` (« Supprimer qwen3.5:2b ? », « … sera supprimé de ce poste (2,7 Go libérés). », focus sur « Annuler », bouton « Supprimer le modèle ») ; « Annuler » ne supprime rien ; la confirmation appelle `DELETE /api/models/{tag}` : Ollama supprime, les lignes `model_facts` sont purgées (pas de retour au démarrage à froid), le modèle quitte la liste (et revient au catalogue s'il en est), l'issue est annoncée (« Modèle supprimé : … »). Preuve : `web/test_models_manage_api.py::test_deleting_a_model_*`, `unit/test_model_delete.py::test_a_deleted_model_does_not_come_back_*`, `e2e/test_models_manage.py::test_deleting_asks_first_*`.
3. **Défaut supprimé** : le dialogue dit « C'est le modèle par défaut pour : Agent et Documents. Ces usages reviendront à la règle automatique. » (D-41) ; après la suppression, ces usages retombent sur la règle avec sa raison. Preuve : `test_a_deleted_default_falls_back_*` (API et E2E), `e2e::test_the_dialog_names_*`.
4. **Modèle employé** : `409 model_in_use` (`detail.tag`, `detail.run_id`), aussi pour un run démarré pendant le dialogue ; à l'écran « Supprimer » est `aria-disabled` avec « Utilisé par une réponse en cours ». Preuve : `test_a_model_used_by_an_active_run_*`, `e2e::test_a_model_used_by_a_run_*`, `::test_a_run_that_starts_while_*`.
5. **Choisir un défaut** : `PUT /api/models/defaults/{purpose}` écrit `preferences` (jamais le `.toml`) ; `GET` le rend avec « Choisi par vous » ; cloud refusé sans `allow_cloud` ; `DELETE` (« Revenir au choix automatique ») l'efface. Preuve : `test_a_choice_is_written_*`, `test_reverting_*`, `test_a_cloud_choice_*`, `e2e::test_choosing_a_default_*`.
6. **« Changer »** ouvre `wl-model-picker` filtré sur les modèles éligibles à l'usage (décision n° 17) : un modèle inéligible n'est pas proposé ; l'Arène en demande 2 ou 3 ; l'API refuse malgré tout (`422 model_not_eligible`). Preuve : `test_the_defaults_say_which_models_are_eligible_*`, `test_an_ineligible_model_*`, `e2e::test_the_picker_proposes_only_*`, `::test_the_arena_asks_*`.
7. **Accessibilité et structure** : axe-core sans violation (clair, sombre, sélecteur ouvert, dialogue), 320 px sans défilement horizontal de la page, aucune écriture par une lecture, aucun JS au-delà de 600 lignes. Preuve : `e2e::test_axe_*`, `::test_the_new_actions_*`, `::test_reading_the_screen_*`, `unit/test_models_manage_static.py`.

## Hors périmètre

Reranker (5.5), fiche du modèle et bouton « Fiche du modèle » à côté du sélecteur (décision n° 17, 5.6).

## Notes de développement

- Serveur : `errors.py` (`model_in_use`, `model_not_eligible`, `model_delete_failed`, en fin de liste), `models/ollama_delete.py`, `models/facts.py` et `facts_store.py` (`delete_tag`), `models/registry.py` (`forget`), `models/defaults.py` (`is_eligible`, `choose`, `clear`, `forget_model`, champs `eligible` et `inactive`), `inference/delete.py`, `web/routes_models.py` (`PUT`/`DELETE` des défauts, `DELETE /api/models/{tag:path}` déclarée après eux), `web/system_state.py` (`models_in_use`).
- Front : `screens/models-unload.js`, `models-delete.js`, `models-defaults.js`, colonne « Actions » de `models-installed.js`, assemblage dans `models.js`, `core/api/models.js`, `core/system.js` et `store.js` (`modelsInUse`), `i18n/fr/models.json` et `components.json`, `models.css`, `components/wl-model-picker.js` (`eligible-only`, 594 lignes).
- Contrat : sous-section « Modèles : gestion (story 5.4) » de `contrat-api.md` et lignes « Flux système », « Défauts », « Déchargement », « Modèles » mises à jour.
- Tests réalignés : `e2e/test_models_install.py` (trois `h2`, colonne « Actions », défauts simulés), `unit/test_models_static.py` (nouveaux fichiers, `api.models(allowCloud)`, pluriel). Faux Ollama : `DELETE /api/delete` et déchargement (`fake_ollama.py`, `pull_fake.py`).

## Rapport de dev

- Joué (poste partagé : jamais `tests/v2` en entier) : `tests/v2/unit` en entier (927 réussis, 1 sauté + 17 nouveaux comptés dedans) ; `tests/v2/web` ciblé (`test_models_manage_api` 20, `test_models_install_api`, `test_models`, `test_read_budget`, `test_system`, `test_static`, `test_errors_envelope`, `test_memory_guard_api`, `test_lifecycle`, `test_runs_api`, `test_defaults`, `test_security`, `test_arena*`, `test_health` : 196 réussis) ; E2E `test_models_manage.py` (16, deux passes), `test_picker.py` (27), `test_shell.py` (42), `test_models_install.py` (19).
- Découvert en route : un sélecteur dans une cellule de tableau était rogné par la zone qui défile (liste ouverte dans la cellule) ; le tri de « Chargé » ne se rouvrait pas pour une liste vide quand la clé de relecture a été étendue aux runs (clé `?` tant que le flux est muet).
- Aucune dépendance nouvelle, aucun fichier d'état touché.
