---
title: 'Jouer le Flow 2 de bout en bout et clore le MVP (préversion 2.0.0a4)'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '8e1ff2f'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-4-7.md'
warnings: []
deferred:
  - summary: >-
      Écarts de la §7 (d) de `sprint-change-proposal-2026-10-19.md` qui touchent la 4.9, non tranchés : variante la plus conservatrice gardée. (13) Base documentaire, « Supprimer » et « Vider » pendant un import : le contrat est gardé (le `409 base_in_use` du serveur s'affiche par `wl-error`, les boutons ne sont pas désactivés), comme livré en 4.3 ; le Flow 2 ne clique « Vider » qu'à l'arrêt. Le message de `ram_guard` n'est pas adapté à l'import : le Flow 2 ne joue le garde-fou que dans la Discussion, avec le message du serveur. (12) Discussion : aucun de ses points (avertissement cloud, « Télécharger », marqueur `[n]`, moment de `retrieval_step`) ne change le Flow 2. Aucun autre écart du §7 (d) ne concerne la 4.9 (§7 (a) : carte « Documents » et passage surligné, faits).
    evidence: |-
      `tests/v2/e2e/test_flow2.py` (étapes 6 et 7), `test_documents_manage.py::test_*409*`, `screens/documents-base.js`.
    location: _bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md
    severity: low
  - summary: >-
      Choix de conception à confirmer. (1) L'Accueil fait désormais **un** appel à l'API (`GET /api/rag/documents`, `totals`) pour le résumé de la carte « Documents » ; AD-6 voulait des cartes qui ne lisent que le store du flux système. Variante conservatrice : aucune route ni aucun champ du flux n'est ajouté (le contrat ne bouge pas), l'appel est unique (au montage, au retour sur l'Accueil et au retour de l'onglet, jamais en boucle) et son échec laisse la phrase d'accroche. Alternative, plus lourde : un champ `rag` dans l'état du flux système. (2) Une base vide dit « 0 document indexé · 0 extrait » (le critère d'`epics.md` donne le format `N documents indexés · M extraits`, sans cas vide) ; le singulier vaut pour 0 et 1, comme la Discussion. Le compte est celui des documents `ready` (`totals`, D-26) : un document en échec ou en cours d'indexation n'y figure pas. (3) La « carte » de l'Accueil est le lien du module (`a.home-module-link`), seul élément cliquable, avec le nom court, le nom long et le résumé de D-10 ; aucune autre carte n'est créée. (4) Le tag annoté `v2.0.0-alpha.4` et la release GitHub ne sont pas créés (consigne du run) : ils suivent la recette humaine, notes et recette dans le rapport de la story.
    evidence: |-
      `screens/home.js::refreshBase`, `baseSummary`, `tests/v2/e2e/test_home.py::test_the_documents_card_*`, `tests/v2/unit/test_shell_static.py::test_the_home_screen_reads_the_store_and_one_base_summary_*`.
    location: src/wavelocalai/web/static/screens/home.js
    severity: medium
  - summary: >-
      Rien n'a été joué avec le vrai reranker (aucun téléchargement) ni sur le PC pro de 16 Go sans GPU installé par `uv sync` seul : la recette humaine (Flow 1 puis Flow 2) reste le signal de succès de la spec. Le test d'intégration du Flow 2 a tourné sur le vrai Ollama de ce poste (`qwen2.5:1.5b`, `nomic-embed-text`) et couvre pour la première fois Self-RAG sur un vrai modèle (report de la revue de la 4.6) : la boucle `embedding`, `search`, `grade` tourne et la réponse part avec ses sources.
    evidence: |-
      `tests/v2/integration/test_flow2_ollama.py`.
    location: tests/v2/integration/test_flow2_ollama.py
    severity: low
---

# Story 4.9 : jouer le Flow 2 de bout en bout et clore le MVP (préversion 2.0.0a4)

## Objectif

Un consultant, depuis l'Accueil, importe un document, l'interroge et retrouve sa source sans aide ; un test E2E joue ce Flow 2 de bout en bout, et la version `2.0.0a4` clôt le MVP.

## Critères d'acceptation et preuves

1. **Carte « Documents » de l'Accueil** : « Documents » en titre, « Assistant documentaire » en sous-titre (D-10) et « N documents indexés · M extraits » (résumé de la base, documents `ready`), relu à chaque retour sur l'Accueil (le routeur le garde monté) ; sans réponse du serveur, la phrase d'accroche reste. Le lien mène à la Discussion. Preuve : E2E `test_flow2.py::test_flow_2_...` (étapes 1 et 3), `test_home.py::test_the_documents_card_counts_the_indexed_documents_and_their_extracts`, `::test_the_documents_card_keeps_its_tagline_when_the_base_cannot_be_read`, `::test_an_available_module_gets_a_link_with_its_summary` ; statique `test_shell_static.py::test_the_home_screen_reads_the_store_and_one_base_summary_...` (le seul appel de l'Accueil est `api.documents`, aucun texte orphelin).
2. **Flow 2 joué sur une base de test** (dossier temporaire, jamais `data/`), avec un `.docx` de test (`tests/v2/workshop_note.py`, 14 paragraphes, 14 extraits) et un modèle simulé : base vide affichée (Discussion et Base), import suivi par fichier (« Vectorisation n/14 extraits »), « 14 extraits ajoutés depuis 1 document », compteur « 1 document prêt · 14 extraits », question posée, sources avant la réponse (étape « Génération… » alors que la réponse est vide), extrait retrouvé mot pour mot (`blockquote` = le paragraphe) avec son passage surligné (`mark` = la phrase qui répond, D-21) ; « Vider » cliqué par erreur, le dialogue annonce « 14 extraits de 1 document seront supprimés. », « Annuler » ne supprime rien (la base garde 1 document et 14 extraits) ; garde-fou simulé : la question reste dans le champ et l'alerte chiffre le besoin (« Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres. »). Preuve : `test_flow2.py::test_flow_2_from_the_home_to_the_source_the_mistaken_clear_and_the_memory_guard`.
3. **Aucune requête hors de `127.0.0.1`** pendant le Flow 2 (le contexte du banc les bloque et les relève, le test vérifie en plus chaque URL). **axe-core sans violation** sur chaque écran `available` du registre (Accueil, Chat, Arène, Discussion, Base), base vide puis base de 14 extraits, thèmes clair et sombre. Preuve : `test_flow2.py::test_axe_finds_no_violation_on_every_screen_of_the_mvp[light|dark]` (la liste vient du registre : un écran livré plus tard y entre seul). Les états profonds (dialogue, garde-fou, sources, 320 px, Système) restent prouvés par les E2E de leur story.
4. **Version `2.0.0a4`** dans `pyproject.toml`, `uv.lock` (`uv lock --offline`) et `CITATION.cff` (`date-released` inchangée) ; le tag annoté et la release suivent la recette (hors de cette story, voir le premier report). Preuve : `tests/v2/unit/test_version.py` (les trois fichiers disent la même préversion `2.0.0aN`).
5. **Flow 2 sur un vrai Ollama** (integration, saute sans Ollama ni modèles) : import du `.docx` par un vrai modèle d'embedding, `naive` (sources avant la réponse, passage = la phrase qui répond) puis `self_rag` (étapes `embedding`, `search`, `grade`, réponse non vide), puis « Vider » avec le nombre d'extraits affiché. Preuve : `tests/v2/integration/test_flow2_ollama.py`.

## Règles écrites

- **Résumé de la base** : `plural("home.documents_indexed", totals.documents) · plural("docs.chunks", totals.chunks)` ; `totals` = documents `ready` seulement. Relu au montage de l'Accueil, au retour sur l'écran (`MutationObserver` sur `hidden`, comme la Discussion) et au retour de l'onglet ; une réponse tardive d'un Accueil démonté ne touche à rien.
- **Document de test** : chaque paragraphe fait environ 400 caractères, deux ne tiennent pas dans un extrait de 800 : un paragraphe = un extrait, donc 14 extraits. Un seul paragraphe répond à la question ; sa phrase est la seule à partager les termes de la question, c'est le passage désigné par `pick_passage`.

## Notes de développement

- `screens/home.js` : `modulesSection()` rend `{section, summaries}` ; `refreshBase()`, `baseSummary()`. Fichier de 300 lignes environ, aucun JS au-delà de 600.
- Aucun changement de serveur, de contrat (`contrat-api.md`) ni de `errors.py`.
- Réaligné : `test_home.py::test_an_available_module_gets_a_link_with_its_summary` (le résumé de la carte « Documents » est celui de la base) et le test statique de l'Accueil (un seul appel d'API permis, un texte au pluriel compte par sa base).
- Contrats partagés (`core/ram-guard.js`, `rag/strategies.py`, `rag/settings.py`, `rag/rerank.py`, `components/wl-confirm-dialog.js`, `core/format.js`) : non modifiés.

## Fichiers

- `src/wavelocalai/web/static/screens/home.js`, `i18n/fr.json` (`home.documents_indexed`)
- `pyproject.toml`, `uv.lock`, `CITATION.cff` (2.0.0a4)
- Tests : `tests/v2/e2e/test_flow2.py`, `tests/v2/integration/test_flow2_ollama.py`, `tests/v2/unit/test_version.py`, `tests/v2/workshop_note.py` (nouveaux) ; `tests/v2/e2e/test_home.py`, `tests/v2/unit/test_shell_static.py` (complétés ou réalignés)

## Vérification

Ciblée (la suite complète est lancée par la CI). Unitaires et statiques : `tests/v2/unit` et `tests/v2/web/test_static.py` verts. Intégration sur le vrai Ollama : `test_flow2_ollama.py` vert (17 s). E2E sur Edge (`-m e2e`) : `test_flow2.py` 3, `test_home.py` 31, `test_documents_manage.py` 20, `test_discussion.py` 19, `test_discussion_rerank.py` 8, `test_discussion_strategies.py` 14 et `test_documents.py` 30, soit 125 verts. Contrôle rapide propre.

## Journal

- 2026-10-19 · dev : spec, carte « Documents » de l'Accueil, E2E du Flow 2 et axe sur les écrans du MVP, test d'intégration (naive et self_rag), version 2.0.0a4.

## Revue

Revue Opus du 2026-10-19, sur la branche fusionnée avec la 4.7 et la 3.6 (merge `c82d742` : `home.js` garde la carte « Démo recommandée » de la 3.6 et la carte « Documents » de la 4.9 ; le test statique de l'Accueil est réuni en un seul : `home.js` n'appelle que `api.documents`, `home-demo.js` que `api.models` et `api.modelDefaults`, les deux attendent `shell-ready`).

- HIGH · second avis · corrigé : le résumé de la base partait pendant `router.start()`, avant le repère `shell-ready` (AD-15, `test_shell.py::test_shell_renders_under_300_ms_*`). `shellReady()` de la 3.6 passe dans `core/shell-ready.js`, partagé par `home-demo.js` et `home.js` (`refreshBase` l'attend).
- MEDIUM · second avis · corrigé : deux lectures au premier affichage (montage, puis l'observateur de `hidden` quand le routeur affiche l'écran). Une lecture par affichage (observateur, ou montage si l'écran est déjà affiché) et une par retour d'onglet si l'Accueil est affiché. Preuve : `test_home.py::test_the_base_summary_is_read_once_per_display_and_once_per_tab_return` (échoue sur l'ancien code : 2 lectures au lieu d'une).
- LOW · second avis · rejeté (sans changement) : écart AD-6, un appel d'API sur l'Accueil ; variante conservatrice déjà consignée au deuxième report.
- LOW · revue · reporté : `components/wl-model-picker.js` fait 666 lignes (> 600), hérité de la 4.8 sur `master`, hors du périmètre de la 4.9 ; à découper dans une story de dette.
- Vérifié sans constat : E2E du Flow 2 (chaque étape assertée, trafic local seulement, axe sur les écrans du registre), intégration qui saute proprement sans Ollama ni modèles, aucun écouteur laissé au démontage (observateur et `visibilitychange` retirés), textes `home.*` tous utilisés, couches (`test_layers`). Complexité : 0 constat (aucune structure qui grossit à l'exécution).
