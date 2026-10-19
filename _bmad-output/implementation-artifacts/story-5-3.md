---
title: 'Installer un modèle en sachant s''il tient en mémoire'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '13bcd36'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-9.md'
warnings: []
deferred:
  - summary: >-
      Écart nouveau, non couvert par les décisions du 2026-10-19 : variante conservatrice gardée. Le critère d'`epics.md` veut que `hardware/` calcule `fits` avec la RAM libre, **la VRAM (NVML)** et **une marge de contexte (cache KV)**. Livré : la RAM libre et la mémoire des modèles chargés (que le garde-fou de la 4.8 compte comme libre, Ollama les déchargeant à la demande), sur la même règle que le garde-fou (besoin × 1,1 + 0,5 Go). La VRAM n'entre pas dans `fits` : le garde-fou ne la lit pas, et un « Oui » du catalogue que le garde-fou refuserait au premier message serait une fausse promesse ; l'élargir aux deux demande de toucher au garde-fou (story 4.8, déjà relue). La marge de contexte n'est pas ajoutée à part : l'empreinte mesurée du catalogue (`measured_loaded_gb`, 23 modèles sur 31) l'est déjà au contexte de 16 384 (`measured_at_ctx`), et l'estimation par la taille du téléchargement garde le facteur 1,25 de la v1 ; une formule du cache KV exigerait couches, têtes et dimensions de `/api/show`, que `model_facts` ne garde pas (migration). À trancher : VRAM et KV dans `fits` et dans le garde-fou ensemble, ou rester sur la règle actuelle.
    evidence: |-
      `hardware/memory.py::MemoryAdvisor.assess` (`reclaimable_gb`), `models/registry.py::installable`, `tests/v2/web/test_models_install_api.py::test_a_loaded_model_counts_as_free_memory_like_the_guard_does`, `tests/v2/unit/test_pull.py`.
    location: src/wavelocalai/hardware/memory.py
    severity: medium
  - summary: >-
      Choix de conception à confirmer, variante conservatrice dans chaque cas. (1) La colonne « Mémoire nécessaire » du catalogue montre `required_gb` (mémoire à avoir de libre, marge et réserve comprises : le chiffre de `ram_guard` et du sélecteur), pas l'empreinte brute `needed_gb` ; « Ne tient pas : 6,1 Go nécessaires, 4,8 Go libres » dit le même chiffre. (2) Un modèle chargé s'affiche « Oui » à « Tient en mémoire » (il est en mémoire : la RAM libre ne le compte plus) ; la règle est d'affichage, le chargé vient du flux système. (3) Nom accessible de « Installer » : « Installer <tag> » (le critère ne fixe que celui d'« Installer quand même », en tag aussi). (4) `wl-progress-bytes` n'est pas un composant partagé enregistré : c'est `screens/models-progress.js`, que la 5.5 (reranker) importe, avec son CSS dans `models.css` (aucune feuille de composant ajoutée, donc aucune ligne en commun avec la 5.1 dans `index.html`, `components/index.js` et les fixtures). (5) Pas de raccourci Échap pour annuler : « Annuler » est un bouton (la règle « Action longue » d'EXPERIENCE.md parle de `wl-run-status`, que cette ligne de tableau n'utilise pas). (6) Les tags distants (`…:cloud`, `…-cloud`) sont refusés par `POST /api/models/pull` (`403 cloud_not_allowed`) : « installer » un modèle distant n'est pas un téléchargement et ferait sortir les données du poste. (7) `#/modeles/<tag>` n'a plus de paramètre de chemin en attendant la fiche (5.6) : l'adresse renvoie à l'Accueil comme une route inconnue. (8) Le disque libre n'est pas contrôlé avant l'installation : Ollama refuse (cause `interrupted`, message technique replié). (9) `run_ended` d'un run `pull` interrompu par un redémarrage porte l'enveloppe `pull_failed` (cause `interrupted`), les autres genres gardent `error: null` : changement de `runs/repo.py::interrupt_orphans`.
    evidence: |-
      `screens/models-catalog.js`, `screens/models-installed.js`, `screens/models-progress.js`, `inference/pull.py::clean_tag`, `runs/repo.py::_interruption_error`, `tests/v2/e2e/test_models_install.py`, `tests/v2/web/test_models_install_api.py::test_a_pull_interrupted_by_a_restart_says_why_when_it_is_replayed`.
    location: src/wavelocalai/web/static/screens/models.js
    severity: low
  - summary: >-
      Rien n'a été installé pour de vrai (aucun téléchargement, consigne du run) : l'installation d'un vrai modèle par le vrai Ollama reste à jouer par une personne (Flow 3). Le flux de `/api/pull` d'Ollama est celui que la documentation d'Ollama décrit (lignes `pulling manifest`, `pulling <empreinte>` avec `total` et `completed`, `verifying sha256 digest`, `writing manifest`, `success`, ou `{"error": …}`) ; le faux Ollama des tests le reproduit, pas le serveur réel. À vérifier à la recette : les couches déjà reçues sont reprises, et le texte d'erreur d'un nom inconnu contient « file does not exist » (c'est ce qui le range en `not_found`).
    evidence: |-
      `models/ollama_pull.py` (`NOT_FOUND_MARKERS`, `parse_line`), `tests/v2/pull_fake.py`.
    location: src/wavelocalai/models/ollama_pull.py
    severity: medium
---

# Story 5.3 : installer un modèle en sachant s'il tient en mémoire

## Objectif

Sur `#/modeles`, un consultant voit ce qui est installé sur son poste, ce qui tient en mémoire, et le catalogue de ce qu'il peut encore installer avec la mémoire nécessaire ; il installe un modèle d'un clic (ou par son nom), suit un téléchargement chiffré (« Téléchargement 1,2 Go sur 4,7 Go · 26 % »), l'annule, ou lit pourquoi il a échoué.

## Critères d'acceptation et preuves

1. **Écran `#/modeles`** (module Modèles passé à `available`). « Sur ce poste » (`wl-data-table` : nom, origine, usage, paramètres totaux et actifs, taille, « tient en mémoire », « chargé », débit mesuré sur ce poste ; tri initial chargés d'abord puis nom) et « Catalogue installable » (nom, paramètres, mémoire nécessaire, « tient en mémoire », « Installer »). Sous 1 024 px, Usage et Origine sont repliées et un bouton au-dessus du tableau les affiche (D-43). Preuve : `tests/v2/e2e/test_models_install.py::test_the_screen_lists_*`, `::test_usage_and_origin_columns_fold_*`.
2. **Catalogue installable** : `GET /api/models/catalog` rend les entrées de `config/models_catalog.json` (lecture seule) moins les modèles installés (un modèle supprimé y revient, `:latest` ignoré), avec `needed_gb`, `required_gb`, `short_gb`, `fits`, dans l'ordre « ceux qui tiennent d'abord, puis la mémoire croissante » ; `hardware/` calcule `fits` (RAM libre et modèles chargés comptés comme libres, comme le garde-fou) ; le front ne calcule rien. `GET /api/models` porte `short_gb` (« Non : il manque 1,2 Go »). Preuve : `tests/v2/web/test_models_install_api.py::test_the_catalog_*`, `::test_a_model_deleted_*`, `::test_installed_models_say_*`, `tests/v2/unit/test_pull.py::test_the_missing_memory_*`, `::test_memory_of_loaded_models_*`. **Écart** : ni VRAM ni cache KV dans `fits` (premier report).
3. **Installer** : `POST /api/models/pull {tag}` (écriture, `Origin` contrôlée) crée un run racine `pull` (`409 run_busy` avec `detail.run_id` si un autre tourne ; l'écran le rejoint sans erreur), publie `pull_progress {tag, received_bytes, total_bytes, percent, phase}` d'après `/api/pull` d'Ollama, et la ligne dit « Téléchargement 2 Go sur 4 Go · 50 % » puis « Installé » ; le registre est relu avant `run_ended`. Un modèle qui ne tient pas reste installable avec « Installer quand même » (nom accessible « Installer <tag> quand même : il ne tient pas dans la mémoire libre ») et la ligne « Ne tient pas : 22,5 Go nécessaires, 4,8 Go libres » (D-42) ; pendant une installation, les autres « Installer » sont `aria-disabled` avec « Une installation est en cours (<tag>). » visible. Preuve : `tests/v2/web/test_models_install_api.py::test_pull_runs_to_installed_*`, `::test_a_second_pull_*`, `::test_the_last_progress_*`, `tests/v2/e2e/test_models_install.py::test_installing_*`, `::test_a_model_that_does_not_fit_*`, `::test_a_second_install_*`.
4. **Annuler, échec, reprise** : annuler ferme le flux vers Ollama (le run finit `cancelled`, la liste est inchangée) ; Ollama arrêté ou nom inconnu finit `error` avec `pull_failed` (code ajouté à `errors.py`, `detail.tag`, `detail.cause` parmi `not_found`, `ollama_down`, `interrupted`, message et action propres à la cause) dans un `wl-error` de la ligne ; quitter l'écran puis revenir, ou recharger la page, reprend la progression par `?after=` (le flux système dit qu'un run `pull` est actif). axe-core sans violation, clair et sombre. Preuve : `tests/v2/web/test_models_install_api.py::test_cancelling_*`, `::test_a_failed_pull_*`, `::test_a_pull_interrupted_*`, `tests/v2/e2e/test_models_install.py::test_cancelling_*`, `::test_a_name_that_does_not_exist_*`, `::test_ollama_stopping_*`, `::test_leaving_the_screen_*`, `::test_a_page_reloaded_*`, `::test_axe_*`.
5. **Aucun téléchargement hors du clic** : lire l'écran, le catalogue ou la liste ne demande jamais `/api/pull` à Ollama ; aucun appel d'API avant `shell-ready`. Aucun vrai téléchargement n'a eu lieu pour cette story : Ollama est simulé partout. Preuve : `tests/v2/web/test_models_install_api.py::test_the_pull_route_is_the_only_one_*`, `tests/v2/e2e/test_models_install.py::test_no_api_call_leaves_*`, `::test_reading_the_screen_*`.

## Hors périmètre

« Décharger les modèles inactifs », « Supprimer » (colonne « Actions ») et les modèles par défaut (story 5.4), « Reclassement des extraits » (5.5), fiche du modèle et bouton « Fiche du modèle » du sélecteur (5.6). Le nom d'un modèle installé est un texte, pas encore le bouton qui ouvre la fiche.

## Règles écrites

- **Un seul `pull` à la fois** (AD-14) ; le téléchargement ne prend pas la place « Ollama local » (il ne charge aucun modèle et ne doit pas bloquer une réponse).
- **Progression** : au plus quatre `pull_progress` par seconde, un changement de phase toujours, la dernière mise à jour jamais perdue (échéance si Ollama se tait). Les couches sont additionnées ; le total ne baisse jamais ; `percent` est calculé par le serveur.
- **Tag** : forme d'un nom d'Ollama seulement (`[A-Za-z0-9._-/:@]`, 200 caractères, pas de `..`), jamais un tag distant.
- **Fin de run** : `ok` à la ligne `success` ; une fin de flux sans `success` est `ollama_down` ; une ligne `error` contenant « does not exist » ou « not found » est `not_found`, toute autre `interrupted`.

## Notes de développement

- Serveur : `models/ollama_pull.py` (flux `/api/pull`), `inference/pull.py` (`PullService`, `_Throttle`), `hardware/memory.py` (`assess(reclaimable_gb=…)`, `short_gb`), `models/registry.py` (`installable()`, `ModelInfo.short_gb`, `ollama_up`), `models/catalog.py` (`entries()`), `web/routes_models.py` (`GET /api/models/catalog`, `POST /api/models/pull`), `web/app.py` (`app.state.pull`), `errors.py` (`pull_failed`, `pull_failed_envelope`), `runs/repo.py` (run `pull` interrompu).
- Front : `screens/models.js` (assemblage, cycle de vie) et un fichier par bloc (`models-installed.js`, `models-catalog.js`, `models-pull.js`, `models-progress.js`, `models-format.js`) ; `core/routes/models.js` (écran `available`, sans `param`), `core/api/models.js` (`installableModels`, `pullModel`), `i18n/fr/models.json` (déclaré dans `TEXT_FILES`), `models.css`, `components/wl-data-table.js` (`column.className`). Aucun JS au-delà de 600 lignes.
- Contrat : sous-section « Modèles : installation (story 5.3) » de `contrat-api.md`, et lignes `pull_progress` et « Modèles » mises à jour.
- Tests réalignés : `test_shell_static.py` (6 écrans disponibles, `/modeles` sans `param`), `e2e/test_shell.py` (le module Modèles a un lien actif).
- Faux Ollama : `tests/v2/pull_fake.py` (`PullOllama` sous `httpx.MockTransport`, `ThreadedOllama` en HTTP pour le navigateur).

## Rapport de dev

- Joué (poste partagé : jamais `tests/v2` en entier) : `tests/v2/unit` en entier et `tests/v2/web/{test_models_install_api,test_read_budget,test_models}.py`, 962 réussis, 1 sauté ; `tests/v2/web` ciblé (`test_static`, `test_errors_envelope`, `test_memory_guard_api`, `test_system`, `test_lifecycle`, `test_runs_api`) : 82 réussis avec le budget de lecture ; E2E `test_models_install.py` (19), `test_shell.py` (42) et `test_home.py` (32, dont 2 réalignés) ; intégration `test_models_install_ollama.py` (1, vrai Ollama en lecture seule, aucun `pull`).
- Réaligné dans le même commit : `test_shell_static.py` (6 écrans disponibles, `/modeles` sans `param`), `e2e/test_shell.py` (lien actif du module Modèles, une raison « pas disponible » de moins), `e2e/test_home.py` (trois cartes de module au lieu de deux).
- Découvert en route : la première version de la progression perdait la dernière mise à jour quand Ollama se taisait après une rafale (le groupage à 4 par seconde jetait l'état en attente) : `_Throttle` la garde et la publie à l'échéance (test `test_the_last_progress_is_never_lost_when_ollama_goes_quiet`). L'écran relit ses listes une fois de plus si une relecture est déjà en vol quand une installation finit (sinon la ligne installée restait au catalogue).
- Aucune dépendance nouvelle, aucun fichier d'état touché. Contrôle rapide propre (ruff, black, isort).
