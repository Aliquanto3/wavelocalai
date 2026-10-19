---
title: 'Dette de l''Epic 8, lot b : Arène et délais'
type: 'fix'
created: '2026-10-19'
status: 'review'
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
