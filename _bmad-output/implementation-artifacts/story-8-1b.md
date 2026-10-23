---
title: 'Dette de l''Epic 8, lot b : Arène et délais'
type: 'fix'
created: '2026-10-19'
status: 'done'
baseline_commit: 'ce1aac9'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
warnings: []
deferred: []
---

## Objectif

Lot b de la story 8.1 (écarts nos 1, 4, 5 et 7 de `decisions-2026-10-19.md`, sur le code livré) :
chaque point n'est corrigé que si l'existant diffère, avec une preuve E2E.

## Constat et correctif

| Point | Existant | Fait |
|---|---|---|
| Écart n° 1, `timeout` cite le délai | Le Banc le faisait déjà (`withDelay`), pas le serveur, ni le chat, ni la colonne de l'Arène (« Délai dépassé pour ce modèle ») | Serveur : `message` de `timeout` = « Délai dépassé ({timeout_s} s) : … » (`errors.py`, délai entier sans décimale). Chat : lit ce message. Arène : la note de la colonne lit `detail.timeout_s` (`wl-arena-lane.js`, `components.lane.timeout_note_delay`). Banc : inchangé (même texte). Contrat : `contrat/8-1b.md` |
| Écart n° 4, chronomètre « 0:42 » | Déjà fait (`formatClock`, `core/format.js`), E2E déjà présent | Rien ; E2E ajouté pour le bandeau en cours (`test_arena_address.py`) |
| Écart n° 5, « un seul juge » avec les notes | Déjà fait : le badge accompagne chaque note, en direct et à la réouverture | Rien ; E2E ajouté pour la réouverture |
| Écart n° 7, adresse réécrite | Absente | `screens/arena-run.js` (`showRunAddress`) appelé par `finish` d'`arena.js`, sauf flux perdu (`interrupted`) ; jamais hors de l'Arène |
| `onSmallerModel` retiré au démontage | `onSmallerModel` rendait déjà la fonction de retrait (7.3), l'Arène ne l'appelait pas | `unwatchSmaller()` au démontage de l'Arène (Discussion et Base : lot c) |
| `wl-model-picker.js` sous 600 lignes | Déjà fait (596 lignes, `model-picker-option.js` voisin) | Rien |

`arena.js` : 600 lignes avant, 594 après ; l'arrêt d'un run (`stopFailure`) est sorti dans `arena-run.js`
pour faire la place.

## Écarts

- Le correctif de l'adresse contredit la variante conservatrice de la 3.6 (« changer le `hash`
  démonterait l'écran ») : `history.replaceState` ne déclenche pas `hashchange`, l'écran reste monté
  (prouvé par E2E : colonnes intactes, `history.length` inchangé).
- Évaluation (7.x) : son message `timeout` vient du même serveur, donc cite aussi le délai ; hors du
  périmètre « Arène, Banc, chat », non testé à part.

## Tests

- `tests/v2/unit/test_errors.py` (message du délai), `test_arena_static.py` (module, démontage, taille).
- `tests/v2/web/test_{bench,chat,arena}_api.py` : le message cite le délai réel.
- E2E : `tests/v2/e2e/test_arena_address.py` (adresse, pas de réécriture en cours de run, chronomètre,
  « un seul juge » en direct et rouvert) ; `test_arena.py` (note de délai de la colonne).

## Revue

Revue Opus, une passe, sur 141a89c (base ce1aac9, à jour de `master`), avec le second avis Haiku.

| Sévérité | Source | Constat | Suite |
|---|---|---|---|
| medium | second avis | `replaceState` laissait la clé du routeur à l'ancienne adresse : après un run fini (adresse `…/R1`, clé `{}`), relancer, aller à l'Accueil puis revenir par l'historique démontait l'Arène et son run en cours (reproduit par E2E) | Corrigé : `replaceAddress` (`core/router.js`) réécrit l'adresse et accorde la clé de l'écran monté ; E2E `test_a_return_by_history_to_the_rewritten_address_keeps_the_screen_mounted` |
| low | second avis | `formatNumber` (3 chiffres significatifs) arrondissait le délai cité (1234 s → « 1 230 s ») dans la colonne de l'Arène et le Banc | Corrigé : `formatDelay` (`core/format.js`), exact, écrit comme le serveur |
| low | second avis | Émetteur sans `timeout_s` : « Délai dépassé (timeout_s s) » | Corrigé : repli « Délai dépassé : le modèle n'a pas fini de répondre. » (`errors.py`), test unitaire ; les émetteurs réels (`streaming.py`, `embedding_leaf.py`) posent toujours le délai |
| low | second avis | Message et action de `timeout` peu adaptés à un embedding | Rejeté : l'action (`lane_timeout_s`) n'a pas changé dans ce lot, et le message parle du « modèle », ce qui reste vrai pour un modèle d'embedding |
| low | second avis | `run_ended` part avant l'écriture en base : un rechargement immédiat peut ne pas trouver le résultat | Rejeté : fenêtre de quelques millisecondes (une seule transaction après `_wake`), hors de portée d'un rechargement humain ; conception du hub antérieure au lot |
| low | second avis | Pendant un run relancé depuis une comparaison rouverte, l'adresse reste l'ancienne jusqu'à la fin | Rejeté : comportement voulu par l'écart n° 7 (réécriture à la fin seulement) ; la clé du routeur est désormais cohérente, aucun remontage |
| low | second avis | Regex du chronomètre sur `innerText` fragile | Rejeté : ancrée sur la fin du texte du bandeau, que le lot définit ; elle a passé en direct et en fin de run |
| low | revue | `agents-crew.js` réécrit son adresse par `history.replaceState` direct, avec le même défaut de clé | Reporté au lot de l'écran Agents : y appeler `replaceAddress` (son test statique compte les `history.replaceState(`) |

Complexité : 0 constat (aucune structure qui grossit n'est parcourue à chaque événement par ce lot).

Tests de la revue : `tests/v2/unit/test_errors.py`, `test_arena_static.py`, `test_bench_static.py`, `test_layers.py`, `tests/v2/web/test_{arena,bench,chat,agent}_api.py`, `test_static.py` (176 passés) ; E2E `test_arena_address.py`, `test_arena.py`, `test_arena_reopen.py`, `test_bench.py` (délai), `test_shell.py`, `test_core.py`, `test_flow1.py` (tous passés).

## Reports d'intégration

- `agents-crew.js` passe par `replaceAddress` (clé du routeur accordée) ; `chat.js` retire son écouteur `onSmallerModel` au démontage (`bench.js` le faisait déjà par `cleanups`). Tests : `test_agents_crew.py` (retour par l'historique), `test_agents_crew_static.py`, `test_memory_guard_static.py`.
