# Run autonome — plan et état (MVP v2, Epics 1 à 4)

Fichier lu par `/agent-cost-kit:avancement-run`. Le détail du run (règles, outils, décisions, préversions et recettes, reports par story) reste dans `run-autonome-mvp.md` ; ce fichier-ci porte le périmètre, les vagues et le journal daté.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 1 à 4 | MVP de la v2 ; préversions 2.0.0a1 à 2.0.0a4, une par epic (tag et release par Anaël après recette) |
| Dans le run | Epics 5 à 8 | après le MVP, seulement après fusion de la PR `bmad-correct-course` ; préversions 2.0.0a5 à a7 sans tag ni release (confirmé par Anaël) |
| Hors run | Story 8.4 | « La v2 remplace la v1 » : revient à Anaël |

## Règles fixes

Voir `run-autonome-mvp.md`, sections « Reprise après /clear » et « État courant ». Par story : dev-story (Sonnet, effort high, worktree `..\wavelocalai-wt\<clé>`) → second-avis (Haiku) → reviewer (Opus) → fusion de la branche précédente ou de `origin/master` par l'orchestrateur → contrôles complets (`_outils/checks.sh`) → `_outils/finalize.sh` → PR → merge commit quand la CI est verte.

## Parallélisme

- **Au plus 3 stories en développement à la fois**, chacune dans son worktree.
- Fusion sur master dans l'ordre des dépendances ; master est fusionné dans les branches suivantes (jamais de rebase).

## Sprint 1 — MVP (Epics 1 à 4)

Dépendances des Epics 3 et 4 au-delà de 3.3 et 4.2 : estimées d'après epics.md, à ajuster.

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 1.1 ★ | — |
| V1 | 1.2 | 1.1 |
| V2 | 1.3 · 1.5 · 1.8 | 1.2 |
| V3 | 1.4 · 1.6 | 1.4 ← 1.3 ; 1.6 ← 1.5 |
| V4 | 1.7 | 1.4 |
| V5 | 1.9 · 1.10 · 1.11 ★ | 1.9 ← 1.7, 1.8 ; 1.10 ← 1.6, 1.8 ; 1.11 ← 1.7, 1.8 |
| V6 | 2.1 | 1.10 |
| V7 | 2.2 · 2.3 · 2.4 | 2.2 ← 2.1, 1.10 ; 2.3 ← 2.1 ; 2.4 ← 2.1 |
| V8 | 2.5 · 2.6 ★ · 3.1 | 2.5 ← 2.4, 2.3 ; 2.6 ← 2.2 ; 3.1 ← 2.4, 2.3 |
| V9 | 3.2 · 3.3 · 4.1 | 3.2 ← 3.1 ; 3.3 ← 3.1 ; 4.1 ← 2.3 |
| V10 | 3.4 · 4.2 | 3.4 ← 3.2, 3.3 ; 4.2 ← 4.1 |
| V11 | 3.5 · 4.3 · 4.4 | 3.5 ← 3.4 ; 4.3 ← 4.2 ; 4.4 ← 4.1, 2.1 |
| V12 | 3.6 ★ · 4.5 · 4.6 | 3.6 ← 3.5, 2.6 ; 4.5 ← 4.4, 4.2 ; 4.6 ← 4.4 |
| V13 | 4.7 · 4.8 | 4.7 ← 4.4 ; 4.8 ← 4.4 |
| V14 | 4.9 ★ | 4.9 ← 4.3, 4.5, 4.6, 4.7, 4.8, 3.6 |

## Journal

Convention : `- AAAA-MM-JJ HH:MM · story · étape · résultat · commit`. Étapes : `dev` (lancé / fini), `second-avis`, `review`, `fusion` (PR fusionnée sur master), `CI`, `report`, `décision`, `blocked`, `attente humaine`. Lignes reconstituées le 2026-10-18 à 22:25 depuis `git log` (heures des merge commits des PR) ; les étapes intermédiaires des stories fusionnées ne sont pas reprises.

- 2026-10-18 15:55 · 1.1 · fusion · PR #39 fusionnée · 428c7e6
- 2026-10-18 16:58 · 1.2 · fusion · PR #40 fusionnée · 4e33370
- 2026-10-18 17:20 · 1.3 · fusion · PR #41 fusionnée · e9af784
- 2026-10-18 17:28 · 1.4 · fusion · PR #42 fusionnée · d922c13
- 2026-10-18 17:57 · 1.5 · fusion · PR #43 fusionnée · 59c2aa2
- 2026-10-18 18:08 · 1.6 · fusion · PR #44 fusionnée · 220c15f
- 2026-10-18 18:18 · 1.7 · fusion · PR #45 fusionnée · 2936e3f
- 2026-10-18 18:31 · 1.8 · fusion · PR #46 fusionnée · 89e20e1
- 2026-10-18 18:46 · 1.9 · fusion · PR #47 fusionnée · 422aa59
- 2026-10-18 19:27 · 1.10 · fusion · PR #50 fusionnée · bcc11ef
- 2026-10-18 20:07 · 1.11 · fusion · PR #51 fusionnée, version 2.0.0a1, Epic 1 terminée (tag et release en attente d'Anaël) · ac9c593
- 2026-10-18 20:10 · 2.1 · fusion · PR #52 fusionnée · f77d1f0
- 2026-10-18 20:31 · 3.1 · dev · fini · de64a0d
- 2026-10-18 20:46 · 2.2 · fusion · PR #53 fusionnée · 3f84605
- 2026-10-18 20:59 · 3.1 · review · faite, attend la fusion de 2.6 · 125ba68
- 2026-10-18 21:22 · 2.3 · fusion · PR #54 fusionnée · a7ab77b
- 2026-10-18 21:40 · 2.4 · fusion · PR #55 fusionnée · 33adc49
- 2026-10-18 · 3.2 · dev · lancé (Sonnet high, worktree v2-3-2) · —
- 2026-10-18 · 3.3 · dev · lancé, partie serveur (Sonnet high, worktree v2-3-3) · —
- 2026-10-18 · 4.1 · dev · lancé (Sonnet high, worktree v2-4-1) · —
- 2026-10-18 21:54 · 3.3 · dev · fini, partie serveur, 643 tests v2 · 2c6f54f
- 2026-10-18 22:01 · 4.1 · dev · fini, 646 tests v2 · 64181e4
- 2026-10-18 22:03 · 2.5 · fusion · PR #56 fusionnée · a5585c3
- 2026-10-18 22:05 · 3.3 · second-avis · 4 low · —
- 2026-10-18 22:07 · 3.3 · review · aucun medium, 3 low corrigés ; reste la seconde passe écran après 3.2 · a0b60de
- 2026-10-18 22:10 · 4.1 · second-avis · 2 medium, 3 low · —
- 2026-10-18 22:11 · 3.2 · dev · fini, 618 tests v2, 176 E2E · 1612fe2
- 2026-10-18 22:15 · 2.6 · review · faite plus tôt (bd1ff0e) ; master fusionné, version 2.0.0a2, test E2E stabilisé · 4a2f8e1
- 2026-10-18 22:17 · 4.1 · review · 1 medium corrigé (annulation pendant l'écriture), fusion de master résolue · f3536cb
- 2026-10-18 22:20 · 4.2 · dev · lancé (Sonnet high, worktree v2-4-2, depuis 4.1 revue) · —
- 2026-10-18 22:20 · 3.2 · second-avis · 2 low · —
- 2026-10-18 22:25 · 2.6 · contrôles · contrôles locaux verts (649 v2, 172 E2E, 5 integration, 1286 v1) ; PR à ouvrir · 4a2f8e1
- 2026-10-18 22:24 · 2.6 · contrôles · finalisée, PR #57 ouverte avec la version 2.0.0a2 · 4a2f8e1
- 2026-10-18 · 3.2 · review · 2 medium corrigés (échec d'orchestration avec sa cause, focus en onglets), 178 E2E · d104fc4
- 2026-10-18 22:38 · 2.6 · fusion · PR #57 fusionnée, version 2.0.0a2, Epic 2 terminée (tag et release en attente d'Anaël) · 8963e14
- 2026-10-18 · 4.2 · dev · fini, 787 tests v2, 179 E2E · 8b73a5b
- 2026-10-18 23:02 · run · reprise · reprise après /clear (ordre : 3.1 → 4.1 → 3.2 → 3.3 ; 4.2 en second avis) · —
- 2026-10-18 23:02 · 4.2 · second-avis · lancé (Haiku) · —
- 2026-10-18 23:02 · 3.1 · fusion master · conflits `streaming.py` et `web/app.py` résolus ; lanes cloud de l'Arène estimées par ecologits (`cloud_estimator` partagé, test) ; contrôles lancés · 784ff71
- 2026-10-18 23:05 · 4.1 · fusion master · master actuel fusionné d'avance (conflits garder les deux), 785 tests v2 unit+web · 6384545
- 2026-10-18 23:05 · 4.2 · second-avis · 2 medium (Annuler à 100 % d'envoi alors que l'index tourne ; focus perdu au rafraîchissement du tableau), 5 low · —
- 2026-10-18 23:05 · 4.2 · review · lancée (Opus) · —
- 2026-10-18 23:10 · 3.2 · fusion 3.1 · 3.1 à jour de master fusionnée d'avance (conflits `routes_test.py`, `wl-chat-thread.js`, `api.js`), 671 tests v2 unit+web · 16774d8
- 2026-10-18 23:10 · 3.3 · fusion 3.2 · 3.2 fusionnée (conflits `streaming.py`, `arena.py`, `contrat-api.md`), 705 tests v2 unit+web · 0dce811
- 2026-10-18 23:10 · 3.3 · dev · lancé, seconde passe écran (Sonnet high, worktree v2-3-3) · —
- 2026-10-18 23:22 · run · décision · Ollama laissé au run pour la nuit (Anaël) · —
- 2026-10-18 23:22 · 3.1 · contrôles · verts (668 v2, 172 E2E dont topbar relancé seul, 6 integration, 1286 v1) ; finalisation et PR · 784ff71
- 2026-10-18 23:24 · run · décision · périmètre étendu aux Epics 5 à 8 sauf 8.4 (confirmé par Anaël) ; garde-fou : PR correct-course fusionnée avant l'Epic 5 · —
- 2026-10-18 23:24 · run · décision · second message de périmètre de wavelocalai-d7 attendu dans la nuit, à prendre en compte (Anaël) · —
- 2026-10-18 23:25 · 4.2 · review · 2 medium et 5 low corrigés, 1 low reporté (plafonds avant lecture du multipart) · 5a77b2a
- 2026-10-18 23:27 · 4.2 · fusion 4.1 · 4.1 à jour de master fusionnée d'avance (conflits garder les deux), 804 tests v2 unit+web · bac487f
- 2026-10-18 23:36 · 3.1 · fusion · PR #59 fusionnée · 5ab78e4
- 2026-10-18 23:38 · 4.1 · fusion master · master avec 3.1 fusionné (conflit `web/app.py`), 803 tests v2 unit+web ; contrôles lancés · f65e592
- 2026-10-18 23:46 · 3.3 · dev · fini, seconde passe écran (critères, juge, note /100, non évalué, peu fiable ; CO₂ du juge cloud estimé), 717 tests v2, 207 E2E · 2a8f225
- 2026-10-18 23:46 · 3.3 · second-avis · lancé (Haiku) · —
- 2026-10-18 23:51 · 3.3 · second-avis · 1 medium (colonne en notation figée « Non évalué » si le flux tombe), 5 low · —
- 2026-10-18 23:51 · 3.3 · review · lancée (Opus) · —
- 2026-10-18 23:55 · 4.1 · contrôles · verts (810 v2, 172 E2E, 7 integration, 1286 v1 ; black de `errors.py` corrigé) ; finalisation et PR · def67ea
- 2026-10-18 23:59 · 3.3 · review · 1 medium corrigé (colonne en notation figée si le flux tombe), fixture E2E attend la fin du run ; rattachement au run reporté · ef39f97
- 2026-10-19 00:10 · 4.1 · CI · rouge (Linux : dossier de transit restant après annulation ; macOS : `vec0` absent, extension non chargée) ; correctif lancé (Sonnet high) · def67ea
- 2026-10-19 00:10 · run · décision · 3.2 fusionnée avant 4.1 (indépendantes ; 4.1 en correctif CI) · —
- 2026-10-19 00:10 · 3.2 · fusion master · master avec 3.1 fusionné (sans conflit) ; contrôles lancés · 74286f2
- 2026-10-19 00:19 · 4.1 · CI · correctif poussé (course du test d'annulation ; index numpy si sqlite-vec absent, `select_index`) ; report : index numpy en mémoire perdu au redémarrage (4.3) · 2d4b0b6
- 2026-10-19 00:25 · 3.2 · contrôles · verts (677 v2, 195 E2E, 6 integration, 1286 v1) ; finalisation et PR · 74286f2
- 2026-10-19 00:42 · run · décision · second message de wavelocalai-d7 appliqué : #58 et #61 fusionnées, garde-fou Epic 5 levé, 1.12 et 2.7 ajoutées, ajustements 3.2/3.3/4.1/4.2 avant PR, écarts §7(d) en variante conservatrice · 72137a4
- 2026-10-19 00:42 · run · report · incident b7703cd (fichiers d'état poussés sur master par l'autre session) : version locale gardée, aucune ligne perdue ; annulation à décider par Anaël · b7703cd
- 2026-10-19 00:44 · 4.1 · fusion master · correct course fusionné ; ajustement §7(a) : `ingest_progress` et `ingest_file_done` consignés dans `contrat-api.md` ; 805 tests v2 unit+web ; poussé · 6d17a04
- 2026-10-19 00:45 · 3.2 · fusion master · correct course fusionné ; PR #62 retenue pour les ajustements §7(a) · 02f092b
- 2026-10-19 00:45 · 3.2 · dev · lancé, ajustements du correct course (Sonnet high) · —
- 2026-10-19 00:45 · 2.7 · dev · lancé (Sonnet high, worktree v2-2-7, depuis master 72137a4) · —
- 2026-10-19 00:57 · 4.1 · fusion · PR #60 fusionnée · bb272a5
- 2026-10-19 00:58 · 4.4 · dev · lancé (Sonnet high, worktree v2-4-4, depuis master bb272a5) · —
- 2026-10-19 00:59 · 4.2 · fusion master · 4.1 et correct course fusionnés (conflit `contrat-api.md` : ligne Base documentaire avec D-26) ; ajustements §7(a) à lancer au prochain créneau · 48bc374
- 2026-10-19 01:05 · 3.2 · dev · fini, ajustements D-15, D-16, légendes, D-11 ; écarts §7(d) n° 1, 4, 7 en variante actuelle ; 680 v2, 204 E2E · 142b9c7
- 2026-10-19 01:05 · 3.2 · second-avis · lancé (Haiku), ajustements · —
- 2026-10-19 01:05 · 4.2 · dev · lancé, ajustements du correct course (Sonnet high) · —
- 2026-10-19 01:09 · 2.7 · dev · fini, 694 v2, 104 E2E ciblés, 3 integration · 6904013
- 2026-10-19 01:09 · 2.7 · fusion master · migration renumérotée 0005 (0004 prise par la 4.1), `schema_v5.sql` · 8f5efd7
- 2026-10-19 01:09 · 2.7 · second-avis · lancé (Haiku) · —
- 2026-10-19 01:09 · 1.12 · dev · lancé (Sonnet high, worktree v2-1-12, depuis master bb272a5) · —
- 2026-10-19 01:11 · 3.2 · second-avis · 3 medium (focus à la fin, D-11 avec Ollama arrêté, « Modifier la question »), 5 low · —
- 2026-10-19 01:11 · 3.2 · review · lancée (Opus), ajustements · —
- 2026-10-19 01:12 · 2.7 · second-avis · 1 medium rejeté (E2E hors CI = règle du dépôt), 5 low · —
- 2026-10-19 01:12 · 2.7 · review · lancée (Opus) · —
- 2026-10-19 01:18 · 4.2 · dev · fini, ajustements D-25 (un seul « Annuler l'import ») et D-26 (échecs dans le tableau, hors compte) ; écart §7(d) n° 13 en variante actuelle ; 832 v2, 27 E2E écran · 214c206
- 2026-10-19 01:18 · 4.2 · second-avis · lancé (Haiku), ajustements · —
- 2026-10-19 01:21 · 4.2 · second-avis · 3 medium (focus à la fin du lot, E2E trivial, annulation perdue sur échec d'envoi), 1 low · —
- 2026-10-19 01:21 · 4.2 · review · lancée (Opus), ajustements · —
- 2026-10-19 01:22 · 4.4 · dev · fini, 859 v2, integration verte (`qwen2.5:1.5b`, `nomic-embed-text`) ; écarts §7(d) n° 12 en variante conservatrice · 9bacb17
- 2026-10-19 01:22 · 4.4 · second-avis · lancé (Haiku) · —
- 2026-10-19 01:24 · 2.7 · review · pas du curseur à 0,05 (défaut publié envoyé tel quel), spec réalignée ; 838 v2, 95 E2E · f424965
- 2026-10-19 01:24 · 2.7 · contrôles · lancés · f424965
- 2026-10-19 01:29 · 3.2 · review · focus rendu partout, D-11 avec Ollama arrêté, repli `6em`, jeton primary ; « Modifier la question » rejeté (3.6) ; lien vers Modèles reporté (écran planned) · f983f4b
- 2026-10-19 01:29 · 3.2 · contrôles · lancés · f983f4b
- 2026-10-19 01:29 · 4.4 · second-avis · 1 medium (KNN plafonné quand beaucoup d'extraits en indexation), 4 low · —
- 2026-10-19 01:29 · 4.4 · review · lancée (Opus) · —
- 2026-10-19 01:38 · 4.2 · review · 3 medium et 1 low corrigés (focus clavier après annulation, E2E réels, run rejoint après réponse d'envoi perdue, bouton visible au rechargement) ; 30 E2E écran · 7e5a119
- 2026-10-19 01:39 · 4.4 · review · medium corrigé (recherche filtrée sur les documents prêts, plus de plafond 4096), 2 low corrigés ; 862 v2, integration verte · eea4abc
- 2026-10-19 01:43 · 1.12 · dev · fini, 819 v2, 196 E2E ; écarts §7(d) n° 3 et 9 en variante actuelle · 5382c7d
- 2026-10-19 01:43 · 1.12 · attente humaine · sprite Material Symbols Rounded officiel (18 symboles de la maquette + 5 de DESIGN.md) à fournir par Anaël ; aucun téléchargement fait · —
- 2026-10-19 01:43 · 1.12 · second-avis · lancé (Haiku) · —
- 2026-10-19 01:44 · 2.7 · contrôles · verts (838 v2, 192 E2E, 8 integration, 1286 v1) ; PR ouverte, fusion après 3.2 · f424965
- 2026-10-19 01:47 · 1.12 · second-avis · 2 medium (dont 1 rejeté : E2E hors CI), 3 low · —
- 2026-10-19 01:47 · 1.12 · review · lancée (Opus) · —
- 2026-10-19 01:48 · 3.2 · contrôles · verts après ajustements (680 v2, 206 E2E, 6 integration, 1286 v1) ; PR #62 mise à jour · f983f4b
- 2026-10-19 02:01 · 1.12 · review · empreintes des 19 symboles du sprite, CSS `aria-disabled` mort retiré ; flash de thème hors Chromium reporté ; 821 v2 · 1cdca6a
- 2026-10-19 02:01 · run · report · `test_topbar.py::test_a_restarted_server_is_announced_with_a_reload_button` instable sous charge (4 fois cette nuit, vert seul) : à stabiliser en 8.1 · —
- 2026-10-19 02:04 · 4.4 · contrôles · verts (862 v2, 172 E2E, 8 integration, 1286 v1) ; PR ouverte · eea4abc
- 2026-10-19 02:21 · 4.2 · contrôles · verts (832 v2, 202 E2E, 7 integration, 1286 v1) ; PR ouverte · 7e5a119
- 2026-10-19 02:41 · 3.2 · fusion master · master (4.1) fusionné, fichiers d'état en conflit seulement ; 824 v2, 36 E2E Arène ; poussé · 5f90bc7
- 2026-10-19 02:41 · 4.2 · CI · rouge macOS (test d'annulation web de la 4.1, même course) ; test corrigé et poussé · daa31c6
- 2026-10-19 02:41 · 1.12 · contrôles · verts (821 v2, 196 E2E, 7 integration, 1286 v1) · 1cdca6a
- 2026-10-19 02:55 · 3.2 · fusion · PR #62 fusionnée · cc37f7b
- 2026-10-19 02:55 · run · décision · après une fusion de master sans conflit de code (fichiers d'état seulement), suite v2 + E2E de l'écran touché en local, la CI couvre les 3 systèmes ; `checks.sh` complet si un conflit de code est résolu · —
- 2026-10-19 02:56 · 3.3 · fusion master · 3.2 ajustée : conflits de fond (`arena.js` 659 lignes, `arena.css`, tests, contrat) confiés au dev avec l'ajustement « Choisissez un juge » (Sonnet high) · —
- 2026-10-19 02:59 · 4.4 · fusion master · 3.2 fusionnée, fichiers d'état seulement ; 874 v2 ; poussé · 5e087cf
- 2026-10-19 03:13 · 3.3 · fusion master · fusion résolue (arena.js 600 lignes : `arena-form.js`, `arena-summary.js`) · d5f6ff0
- 2026-10-19 03:13 · 3.3 · dev · ajustement « Choisissez un juge », juge dans le résumé ; 865 v2, 55 E2E Arène, integration juge · 18e4824
- 2026-10-19 03:13 · 3.3 · second-avis · lancé (Haiku), fusion et ajustement · —
- 2026-10-19 03:14 · 4.4 · fusion · PR #64 fusionnée · 4635302
- 2026-10-19 03:15 · run · décision · ordre de l'Epic 4 : 4.8 maintenant, 4.5 après fusion de 4.2, puis 4.6 et 4.7 (leur partie écran vit dans la Discussion de 4.5) · —
- 2026-10-19 03:16 · 4.8 · dev · lancé (Sonnet high, worktree v2-4-8, depuis master 4635302) · —
- 2026-10-19 03:16 · 4.2 · fusion master · 3.2 et 4.4 sur master : conflits dans 11 fichiers, résolution confiée au relecteur (Opus) · —
- 2026-10-19 03:17 · 2.7 · fusion master · 3.2 et 4.4 : conflits `components/index.js` et commentaire de `wl-model-picker.js` (un seul `wl-models-loaded`) ; contrôles lancés · f6ac4bc
- 2026-10-19 03:18 · 3.3 · second-avis · aucun medium, 5 low (dont juge local indisponible non bloquant) · —
- 2026-10-19 03:18 · 3.3 · review · lancée (Opus), fusion et ajustement · —
- 2026-10-19 03:32 · 3.3 · review · juge indisponible ou cloud coupé = « Choisissez un juge », juge lu avant l'envoi ; 865 v2, 57 E2E Arène · a9215b3
- 2026-10-19 03:37 · 2.7 · contrôles · verts après fusion (900 v2, 226 E2E, 9 integration, 1286 v1) ; poussé · f6ac4bc
- 2026-10-19 03:37 · 3.3 · fusion master · 4.4 : conflits `streaming.py` (`capture` et `metrics_extra`) et contrat ; 915 v2 ; contrôles lancés · c79c074
- 2026-10-19 03:37 · 4.2 · fusion master · résolue par le relecteur (11 fichiers, garder les deux) + route planifiée de `test_shell.py` réalignée ; 894 v2 · 869893c
- 2026-10-19 03:52 · 2.7 · fusion · PR #63 fusionnée · f6e3841
- 2026-10-19 03:53 · 4.2 · fusion master · 2.7 fusionnée sans conflit de code ; contrôles lancés · 5e1d995
- 2026-10-19 03:53 · 4.8 · dev · fini, 916 v2, 74 E2E chat/Arène, integration verte ; §7(d) n° 13 en variante conservatrice · b7f6fc6
- 2026-10-19 03:53 · 4.8 · second-avis · lancé (Haiku) · —
- 2026-10-19 03:57 · 4.8 · second-avis · 1 high (Arène : modèle de la lane précédente compté comme occupé, refus à tort), 4 medium, 3 low · —
- 2026-10-19 03:57 · 4.8 · review · lancée (Opus, effort high) · —
- 2026-10-19 04:05 · 3.3 · contrôles · verts (915 v2, E2E 228 + 1 erreur Playwright passagère, 229/229 relancés, 9 integration, 1286 v1) ; PR ouverte · c79c074
- 2026-10-19 04:15 · 4.2 · contrôles · verts après fusions (920 v2, 256 E2E, 9 integration, 1286 v1) ; poussé · 5e1d995
- 2026-10-19 04:17 · 4.8 · review · high corrigé (mémoire des modèles chargés inactifs comptée comme libre), modèle proposé plus petit, `required_gb` partagé sélecteur/refus, déchargement relit les runs actifs ; 921 v2, 108 E2E · 67fb239
- 2026-10-19 04:17 · 4.8 · décision · pour Anaël : bouton « Décharger les modèles inactifs » gardé tel quel lors d'un refus (critère), à masquer ou non ; vérification Linux 16 Go (mmap) à faire · —
- 2026-10-19 04:31 · 4.2 · fusion · PR #65 fusionnée · fff8faa
- 2026-10-19 04:33 · 3.3 · fusion master · 2.7 et 4.2 fusionnées sans conflit de code ; tests v2 et E2E lancés · —
- 2026-10-19 04:33 · 4.3 · dev · lancé (Sonnet high, worktree v2-4-3, depuis master fff8faa) · —
- 2026-10-19 04:33 · 4.5 · dev · lancé (Sonnet high, worktree v2-4-5, depuis master fff8faa) · —
- 2026-10-19 04:47 · 3.3 · contrôles · après fusion : 961 v2, 278 E2E + 1 erreur Playwright passagère (relancé seul : vert) ; poussé · a38bbbb
- 2026-10-19 04:47 · run · report · `test_arena.py::test_the_panel_opens_and_works_from_the_keyboard` : « Browser.new_context: Response has been disposed » sous charge, 3 fois (8.1) · —
- 2026-10-19 04:59 · 3.3 · fusion · PR #67 fusionnée · 2567e44
- 2026-10-19 05:00 · 3.4 · dev · lancé (Sonnet high, worktree v2-3-4, depuis master 2567e44) · —
- 2026-10-19 05:01 · 1.12 · fusion master · conflits `core/registry.js` (écrans Arène et Base disponibles + routes planned de la maquette) et `test_shell.py` ; contrôles lancés · e3f5886
- 2026-10-19 05:23 · 4.3 · dev · fini, 971 v2, 41 E2E documents, integration verte ; résidu vectoriel : aucun (sqlite-vec 0.1.9) ; §7(d) n° 13 en variante contrat (409 affiché) · 974925c
- 2026-10-19 05:23 · 4.3 · second-avis · lancé (Haiku) · —
- 2026-10-19 05:24 · 4.8 · fusion master · conflits de fond (streaming, Arène, chat, app, faux Ollama) confiés au relecteur (Opus) · —
- 2026-10-19 05:27 · 4.3 · second-avis · 3 medium (`chunk_size: null` en 500, embedding remis au .toml sans contrôle, résidu vec0 sans sqlite-vec), 3 low · —
- 2026-10-19 05:27 · 4.3 · review · lancée (Opus) · —
- 2026-10-19 05:28 · 1.12 · contrôles · 2 échecs statiques (8 icônes Material Icons de la 3.2 refusées par le test Rounded) + 1 E2E Accueil (écrans devenus disponibles) ; correctif lancé (Sonnet) · —
- 2026-10-19 05:28 · run · décision · icônes : test strict gardé avec une liste nommée des 8 symboles Material Icons de la 3.2 en attente du sprite officiel (variante conservatrice, aucun téléchargement) · —
- 2026-10-19 05:36 · 3.4 · dev · fini, 971 v2, 83 E2E Arène ; §7(d) n° 4 à 8 en variante actuelle (« le plus petit des trois » non livré) · ecf58f6
- 2026-10-19 05:36 · 3.4 · second-avis · lancé (Haiku) · —
- 2026-10-19 05:42 · 4.5 · dev · fini, 932 v2, E2E par lots verts (Discussion 17) ; §7(d) n° 12 en variante conservatrice · 90cfc80
- 2026-10-19 05:42 · 4.5 · second-avis · lancé (Haiku) · —
- 2026-10-19 05:45 · 3.4 · second-avis · 2 medium (étiquette longue hors du SVG, défilement du tableau remis à zéro), 1 medium rejeté (E2E hors CI), 2 low · —
- 2026-10-19 05:45 · 3.4 · review · lancée (Opus) · —
- 2026-10-19 05:50 · 1.12 · contrôles · correctifs (liste `PENDING_ROUNDED` de 8 symboles, test Accueil réaligné) : 971 v2, 188 E2E ; poussé · b80d0c2
- 2026-10-19 05:50 · 4.3 · review · `null` des réglages rendu au .toml sans 500, embedding `null` contrôlé, vec0 sans module : refus `vector_tables_unreachable` avant écriture, délai client 300 s ; 975 v2, 49 E2E · 0829e07
- 2026-10-19 05:51 · 4.3 · fusion master · 3.3 et 2.7 : conflit `fr.json` (clés `lane` et `confirm`) ; contrôles lancés · 9dc769d
- 2026-10-19 05:51 · 4.5 · second-avis · 1 medium (avertissement cloud absent à la réouverture), 6 low · —
- 2026-10-19 05:51 · 4.5 · review · lancée (Opus) · —
- 2026-10-19 05:52 · 4.8 · fusion master · résolue par le relecteur (garde-fou dans chat, Arène, RAG et juge ; arguments par mot-clé) ; medium corrigé : juge local gardé ; 1009 v2, 149 E2E · 8e2f758
- 2026-10-19 05:52 · run · report · E2E instables sous charge à stabiliser en 8.1 : axe-core du pied de message en sombre (1 fois sur 3) · —
- 2026-10-19 06:03 · 3.4 · review · étiquettes longues coupées, défilement du tableau gardé, gel à `run_ended` gardé, largeur d'étiquette mesurée ; 971 v2, 28 E2E résultats · 02fdaef
- 2026-10-19 06:03 · 3.4 · contrôles · lancés · 02fdaef
- 2026-10-19 06:11 · 1.12 · CI · rouge sur un seul job (`test_read_budget` « / » 303 ms > 300 ms, Windows 3.11, minutage) ; job relancé · b80d0c2
- 2026-10-19 06:11 · run · report · `test_read_budget` (budget 300 ms) instable sur les runners CI et sous charge locale : à stabiliser en 8.1 · —
- 2026-10-19 06:16 · 4.5 · review · medium corrigé (avertissement cloud à la réouverture), rejeu limité à 3 flux, test de reprise déterministe, test run_busy stabilisé ; report : `conversation_id` dans le détail de `run_busy` (Chat et Discussion) · e6ab8a7
- 2026-10-19 06:17 · 1.12 · fusion · PR #66 fusionnée · b90056e
- 2026-10-19 06:39 · 4.3 · contrôles · verts (1017 v2, 298 E2E, 11 integration, 1286 v1) ; master (1.12) fusionné sans conflit de code, 1027 v2, 123 E2E ; PR ouverte · 55a8715
- 2026-10-19 06:43 · 3.4 · contrôles · verts (971 v2, 307 E2E, 10 integration, 1286 v1) ; master (1.12) fusionné sans conflit de code, 981 v2, 159 E2E ; PR ouverte · a07ddbb
- 2026-10-19 06:54 · 4.3 · CI · rouge macOS (`index.persistent` attendu vrai sans sqlite-vec) ; test corrigé et poussé · a5aab5b
- 2026-10-19 07:00 · 3.4 · fusion · PR #69 fusionnée · 71cfbf3
- 2026-10-19 07:01 · 3.5 · dev · lancé (Sonnet high, worktree v2-3-5, depuis master 71cfbf3) ; consigne : aucun prix inventé · —
- 2026-10-19 07:07 · run · décision · Anaël : fichiers d'état hors des PR de story (PR `chore/etat-run`), story technique 5.0 avant l'Epic 5, vagues par fichiers, `rerere`, journal en `merge=union`, job E2E en CI (dans 5.0) · —
- 2026-10-19 07:08 · 4.8 · contrôles · verts après fusion (1019 v2, 317 E2E, 10 integration, 1286 v1) ; PR ouverte · 8e2f758
- 2026-10-19 07:09 · 4.3 · fusion · PR #68 fusionnée · 71cfbf3
