---
title: 'Découper les fichiers partagés du front et jouer les E2E en CI'
type: 'chore'
created: '2026-10-19'
status: 'ready-for-dev'
baseline_commit: '8d70302'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/run-autonome-mvp.md'
---

# Story 5.0 : Découper les fichiers partagés du front et jouer les E2E en CI

Story technique décidée par Anaël le 2026-10-19 (`run-autonome-mvp.md`, « Périmètre étendu », décision de 7 h, point 2), avant l'Epic 5. Elle n'apporte aucune fonction visible : **aucun changement de comportement, de texte affiché, de style rendu ni d'API**. But : les stories des Epics 5 à 8 se développent en parallèle sans se marcher dessus. Aujourd'hui chaque écran ajoute ses textes dans `i18n/fr.json` (714 lignes), son style dans `components.css` (1 308 lignes) ou un CSS d'écran, ses appels dans `core/api.js` et sa route dans `core/registry.js` : chaque fusion parallèle y entre en conflit.

## Critères d'acceptation

1. **Textes par écran.** `static/i18n/fr.json` est remplacé par un fichier par domaine dans `static/i18n/fr/` (au moins : coquille et commun — `app`, `shell`, `modules`, `screens`, `router`, `format`, `errors`, `tabs`, `topbar` —, `home`, `components`, `chat`, `discussion`, `docs`, `arena`, et les clés restantes dans le fichier du domaine qui les utilise). `core/i18n.js` les charge en parallèle et les fusionne sous les **mêmes clés** qu'aujourd'hui (aucun appel `t("…")` ne change). La liste des fichiers est déclarée à un seul endroit ; une story qui ajoute un écran ajoute son fichier (ex. `fr/sobriety.json`) et une ligne. Deux fichiers qui déclarent la même clé de premier niveau : erreur détectée par un test unitaire (pas d'écrasement silencieux). Les tests qui lisent `fr.json` (espaces insécables, clés utilisées, etc.) lisent désormais l'ensemble fusionné. Le budget de 300 ms de la coquille (AD-15, `shell-ready`) reste tenu.
2. **CSS par composant.** `components.css` est découpé en un fichier par composant (`static/css/components/<composant>.css` ou équivalent cohérent avec l'existant) ; les CSS d'écran (`chat.css`, `arena.css`, `arena-results.css`, `documents.css`, `screens.css`) restent par écran, rangés au même endroit si c'est plus lisible. Ordre de cascade inchangé (vérifier qu'aucune règle ne change de priorité : même ordre de chargement relatif). `index.html` les liste, ou un fichier d'entrée par `@import` — choisir ce qui garde le premier rendu rapide (pas de cascade d'`@import` en chaîne sur plusieurs niveaux). Les tests de dérive (`test_shell_static.py` : aucune couleur en dur, accolades équilibrées, etc.) parcourent tous les fichiers CSS, nouveaux compris.
3. **`api.js` par domaine.** `core/api.js` garde le transport (`request`, `ApiError`, `uploadDocuments` ou son déplacement) ; les appels sont rangés par domaine (`core/api/<domaine>.js` : système, modèles, conversations, arène, rag…). L'objet `api` exporté reste disponible avec la même forme (aucun écran à réécrire), assemblé depuis les domaines ; une story qui ajoute un domaine ajoute un fichier et une ligne.
4. **Routes déclarées par écran.** Les entrées de `core/registry.js` (`MODULES`) sont déclarées par module dans des fichiers séparés (`core/routes/<module>.js` ou équivalent) ; `registry.js` les assemble dans l'ordre actuel de la navigation et garde `findScreen` et ses exports. Passer un écran `planned` à `available` ne touche plus que le fichier de son module.
5. **`components/wl-model-picker.js` sous 600 lignes** (666 aujourd'hui) : sortir un module voisin cohérent (filtrage, rendu des lignes ou clavier), sans changement de comportement. Aucun fichier JS du front au-delà de 600 lignes (contrat partagé) ; si un test garde déjà cette limite, il couvre les nouveaux dossiers, sinon en ajouter un.
6. **Job E2E dans la CI.** `.github/workflows/tests.yml` gagne un job qui joue `pytest tests/v2 -m e2e` sur `ubuntu-latest` (une version de Python, 3.12), avec `uv sync --locked` et l'installation du navigateur de Playwright par la version déjà verrouillée dans `uv.lock` (aucune nouvelle dépendance ; ne rien figer de mémoire). Si la durée dépasse ~15 min, le partager en 2 ou 3 morceaux par fichiers (matrice), sans ajouter de dépendance (pas de pytest-xdist s'il n'est pas déjà verrouillé). Le job doit être bloquant comme les autres jobs de tests (pas `continue-on-error`). Les E2E qui demandent Ollama ou un vrai modèle restent `integration` et ne tournent pas en CI. Vérifier le job sur la PR (on ne peut pas le jouer en local : le décrire dans le rapport ; l'orchestrateur suit la CI).
7. **Couches.** `tests/v2/unit/test_layers.py` et les tests statiques passent ; aucun import de `src.*`.
8. **Non-régression.** Contrôle rapide vert ; `pytest tests/v2` vert ; suite E2E **complète** verte en local (`$env:WAVELOCALAI_E2E_CHROMIUM = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`, `$env:PYTHONUTF8 = "1"`) : toutes les pages s'affichent avec les mêmes textes et styles, axe-core sans violation en clair et en sombre.
9. **Mode d'emploi.** Une note courte (en tête de `core/registry.js`, `core/i18n.js`, `core/api.js` et dans le fichier d'entrée CSS, au style des commentaires existants) dit où une story ajoute ses textes, son CSS, ses appels et sa route.

## Hors périmètre

- Toute modification de comportement, de texte affiché ou de contrat d'API ; la dette de la 8.1 (sauf `wl-model-picker.js`).
- `_bmad-output/` hors de ce fichier de story (la passe « Report au contrat » modifie les documents de contrat en parallèle) ; les fichiers d'état du run (`sprint-status.yaml`, `run-autonome*.md`).

## Notes de développement

- Faire les déplacements avec `git mv` quand un fichier garde son contenu, pour garder l'historique.
- Découper `fr.json` par un petit script jetable (dans le scratchpad, pas dans le dépôt) qui vérifie que l'ensemble fusionné est **identique** à l'ancien (même dictionnaire), et le dire dans le rapport.
- Pour le CSS, vérifier l'équivalence : même concaténation dans le même ordre que l'ancien fichier (aux commentaires de tête près).
- Les écrans des Epics 5 à 7 à venir (Sobriété, Modèles, Usages, Agent, Équipe, Évaluation, Banc) n'ont pas à être créés ici ; les fichiers par domaine existent pour ce qui existe déjà.
