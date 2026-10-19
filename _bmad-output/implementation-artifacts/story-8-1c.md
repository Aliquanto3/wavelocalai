---
title: 'Dette de l''Epic 8, lot c : Discussion, Base, Agent seul et coquille'
type: 'fix'
created: '2026-10-19'
status: 'review'
baseline_commit: 'ce1aac9'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat/8-1c.md'
warnings: []
deferred:
  - 'Le chat (`screens/chat.js`) et le Banc (`screens/bench.js`) n''appellent pas non plus le retrait de `onSmallerModel` au démontage : le Banc est dans le lot Banc, `chat.js` est touché par le lot b (message `timeout`) ; à traiter à l''intégration.'
  - 'Autres points de la 8.1 : lots a et b, sprite officiel (en attente du fichier d''Anaël).'
---

# Story 8.1, lot c : Discussion, Base, Agent seul, coquille

Lot de la story 8.1 (« Solder la dette technique relevée pendant le MVP ») sur des fichiers disjoints des lots a (serveur et garde-fous) et b (Arène et délais). Chaque point n'est corrigé que si l'existant diffère.

## 1. Discussion : avertissements du modèle (AD-9, écart n° 12, ajout Self-RAG)

- **Cloud** : l'avertissement existait déjà (`discussion.cloud_warning`, « … les extraits retrouvés dans vos documents lui sont envoyés, hors de ce poste. ») et un E2E le prouvait (`test_discussion.py::test_a_cloud_model_warns_...`). Aucun changement de comportement ; le code passe dans le nouveau module `screens/documents-notes.js` (`documents.js` dépassait 600 lignes avec le point suivant).
- **Stratégie vérifiée (Self-RAG) avec un petit modèle** : sous le sélecteur, « Vérification peu fiable avec {modèle} : … moins de 3 milliards de paramètres actifs (ou sa taille est inconnue) … » (`docs-verify-note`, même style que l'avertissement cloud : icône et texte). Conditions : stratégie `self_rag`, modèle **non cloud** (local, ou d'origine `unknown` : local sans digest), `params_active_b` absent ou inférieur au seuil. Même règle que le juge de l'Arène (`is_weak_judge`) et même source de taille (la fiche du modèle, `GET /api/models`). Le seuil n'est pas écrit dans le front : `GET /api/rag/settings` gagne `verify_min_params_b` (= `RAG_MIN_PARAMS_B`, 3,0 ; voir `contrat/8-1c.md`). Remis à jour au changement de modèle, de stratégie, à « Prendre un modèle plus petit » et à l'arrivée des réglages.
- Preuves : `e2e/test_discussion_strategies.py::test_self_rag_with_a_small_or_unmeasured_model_warns_that_the_check_is_unreliable` ; `web/test_rag_manage_api.py` (champ du serveur).

## 2. Base documentaire : pas de `409` à l'écran (écart n° 13)

- Pendant un import (suivi par l'écran, ou document `indexing` lancé depuis un autre onglet), « Supprimer » (chaque ligne) et « Vider la base documentaire » (celui du tableau et celui que le panneau Réglages offre après `embedding_change_needs_clear`) sont désactivés ; une phrase visible au-dessus du tableau dit pourquoi (« « Supprimer » et « Vider » sont indisponibles pendant un import : attendez sa fin ou annulez-le. ») et est reliée aux boutons par `aria-describedby`. Tout se réactive à la fin de l'import.
- Le serveur reste juge : `409 base_in_use` inchangé (import ou question en cours, y compris lancée depuis un autre onglet : `wl-error` l'affiche alors comme avant). Preuves serveur : `web/test_rag_manage_api.py`, `web/test_eval_api.py`.
- Preuve écran : `e2e/test_documents_manage.py::test_delete_and_clear_are_disabled_with_their_reason_during_an_import` (remplace le test qui attendait le `409` affiché) et `::test_the_settings_clear_button_is_disabled_too_during_an_import`.

## 3. `onSmallerModel` rend son retrait : appel au démontage

`core/ram-guard.js` rendait déjà la fonction de retrait ; la Discussion (`documents.js`) et l'Agent seul (`agents-solo.js`) ne la gardaient pas. Ils l'appellent maintenant dans leur fonction de démontage ; `documents-eval.js` le faisait déjà. L'Arène est dans le lot b. La Base n'écoute pas `wl-use-model` : rien à retirer. Preuve : `unit/test_memory_guard_static.py::test_the_screens_that_listen_for_the_smaller_model_stop_listening_when_unmounted`.

## 4. Agent seul : ne rejoindre qu'un Agent seul (revue 6.6)

Sur `409 run_busy`, l'écran lit le run (`GET /api/runs/{id}`) et ne le rejoint que si `params.mode === "solo"`. Une mission d'équipe active (même genre `agent` au hub) n'est pas rejointe : l'écran le dit (« Une mission d'équipe travaille en ce moment : … ») avec un lien « Voir la mission d'équipe » vers `#/agents/equipe`, comme l'Équipe le fait pour un Agent seul ; le texte reste dans le champ. Preuve : `e2e/test_agents_solo.py::test_a_running_team_mission_is_said_with_a_link_and_not_joined_as_a_solo_task` ; la jonction d'un Agent seul reste prouvée par `::test_a_task_already_running_elsewhere_is_joined_without_an_error`.

## 5. Tests de la coquille : comptes lus dans le registre

Décision d'Anaël (21 h 30) : moins de conflits entre stories parallèles.

- `unit/test_shell_static.py` : plus de `len(ROUTES)` ni de `== 0` pour les écrans `available` et les routes `planned` ; le test lit le registre (`core/routes/*.js`) : chaque écran est `available` ou `planned`, et chaque `available` a son `load`. La liste `ROUTES` (adresses du contrat) reste.
- `e2e/test_shell.py` : `registry_modules(page)` lit les modules du registre réel dans le navigateur (`entry`, écrans `available` et `planned`) ; le test des liens de modules (qui comptait « six » et indexait chaque module) devient générique : un module avec un écran disponible mène à son premier écran, un module sans écran est un lien désactivé avec sa raison, et le nombre de raisons visibles est celui des modules à venir.
- `e2e/test_home.py` : les liens de modules de l'Accueil sont ceux du registre (`home_module_entries`), plus de `== 5` ; les noms courts et longs (contenu) restent écrits.
- `unit/test_chat_static.py` : l'assertion « aucun `planned` dans `routes/arena.js` » est retirée (un compte de plus).
- **Budget de 300 ms** (`test_shell_renders_under_300_ms_...`) : inchangé (une manche, deuxième meilleur de cinq). Les manches répétées du dev ont été retirées à la revue : la relance d'un test instable revient à l'outillage (`checks.sh` relance une fois un test en échec).

## Écarts

- **Self-RAG, taille inconnue** : un modèle local sans `params_active_b` est signalé, comme le juge de l'Arène (variante conservatrice : « peu fiable » plutôt que silence). Un modèle cloud n'est jamais signalé.
- **Base, verrou** : seul un import visible (ou un document `indexing`) désactive les boutons. Un run `rag` lancé depuis la Discussion n'est pas connu de l'écran Base : le `409 base_in_use` du serveur s'affiche alors, comme avant (le serveur reste juge).
- **Budget** : aucune tolérance au bruit dans le test (revue) ; la relance est celle de l'outillage.
- **`documents-notes.js`** : module ajouté pour tenir la limite de 600 lignes ; l'avertissement cloud y a été déplacé sans changement de texte.

## Revue

Revue Opus du 2026-10-19 sur 17c14b3 (branche à jour de master, fusion fe73a80).

- medium · second avis n° 1 · corrigé : le « Vider » du panneau Réglages (après `embedding_change_needs_clear`) restait actif pendant un import et envoyait la requête (`409` à l'écran, écart n° 13). Il suit maintenant le verrou (`setLocked`, même raison en `aria-describedby`) ; `clearBase` et `deleteDocument` refusent aussi pendant le verrou. Preuve : `e2e/test_documents_manage.py::test_the_settings_clear_button_is_disabled_too_during_an_import`.
- medium · second avis n° 2 · corrigé : la boucle `SHELL_ROUNDS` passait dès qu'une manche sur trois tenait le budget, ce qui laissait passer une régression proche de 300 ms. Retour à une manche unique (deuxième meilleur de cinq) ; la relance reste à `checks.sh`.
- low · second avis n° 3 · rejeté : sans `GET /api/rag/settings`, le seuil est inconnu, et l'écrire dans le front contredirait AD-20. La même panne prive déjà la Discussion de ses réglages (comportement documenté : le serveur applique les siens).
- low · second avis n° 4 · corrigé : un modèle d'origine `unknown` (local sans digest) n'était jamais signalé ; il l'est maintenant, comme dans `is_weak_judge` (`not is_cloud`). Preuve : ajout « Inconnu 8B » dans `e2e/test_discussion_strategies.py`.
- low · second avis n° 5 · rejeté : la fenêtre où `run_busy` porte un run réservé non encore écrit dure une écriture SQLite (`hub.create_run`) ; le cas exige deux lancements dans la même milliseconde, et l'erreur affichée (`run_not_found`) reste juste. L'ancien `join` suivait le même identifiant sans plus de garantie.
- Complexité : 0 constat (`locked()` parcourt la liste des documents à chaque rendu, comme le rendu du tableau lui-même : O(n) par rendu, sans surcoût d'ordre).

