# Run autonome — plan et état (MVP v2, Epics 1 à 4)

Fichier lu par `/agent-cost-kit:avancement-run`. Le détail du run (règles, outils, décisions, préversions et recettes, reports par story) reste dans `run-autonome-mvp.md` ; ce fichier-ci porte le périmètre, les vagues et le journal daté.

## Périmètre

| Périmètre | Epics | Note |
|---|---|---|
| Dans le run | Epics 1 à 4 | MVP de la v2 ; préversions 2.0.0a1 à 2.0.0a4, une par epic (tag et release par Anaël après recette) |
| Hors run | Epics 5 à 8 | reportés à un run ultérieur (décision d'Anaël du 2026-10-19 vers 8 h 40 : budget de tokens ; projet non urgent). Plan des vagues V15 à V25 gardé ci-dessous pour la reprise |
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
| V14b | 1.12 · 2.7 | stories de suite du correct course (§7(b)), fusionnées avant 3.6 et 4.9 |

## Sprint 2 — Après le MVP (Epics 5 à 8, sauf 8.4)

Vagues planifiées par fichiers touchés (décision d'Anaël du 2026-10-19) : deux stories du même écran ne vont jamais dans la même vague ; une story serveur d'un epic suivant peut prendre une place libre. Écrans : Sobriété (5.1, 5.2), Modèles (5.3 à 5.6), Usages (5.8), Agent (6.4), Équipe (6.6), Évaluation (7.3), Banc d'essai (7.4). La 5.0 découpe d'abord les fichiers partagés du front (textes par écran, CSS par composant, `api.js` par domaine, routes par écran) et ajoute le job E2E à la CI.

| Vague | Stories en parallèle | Après |
|---|---|---|
| V15 | 5.0 ★ · report au contrat (`bmad-spec`, Opus, docs seulement) | 5.0 ← 4.9 ; report ← décisions-2026-10-19 (PR #82) |
| V16 | 5.1 · 5.3 · 6.1 | 5.1 ← 5.0, report ; 5.3 ← 5.0, report ; 6.1 ← 5.0, report |
| V17 | 5.2 · 5.4 · 6.2 | 5.2 ← 5.1 ; 5.4 ← 5.3 ; 6.2 ← 6.1 |
| V18 | 5.5 · 5.7 (mixte) · 6.3 | 5.5 ← 5.4 ; 5.7 ← 5.4 ; 6.3 ← 6.2 |
| V19 | 5.6 · 6.5 · 7.1 | 5.6 ← 5.5 ; 6.5 ← 6.1 ; 7.1 ← 4.4 |
| V20 | 5.8 ★ · 6.4 · 7.2 (mixte) | 5.8 ← 5.6, 5.7 ; 6.4 ← 6.3 ; 7.2 ← 7.1 |
| V21 | 6.6 ★ · 7.3 | 6.6 ← 6.4, 6.5 ; 7.3 ← 7.1 |
| V22 | 7.4 ★ | 7.4 ← 7.2, 7.3 |
| V23 | 8.1 | 8.1 ← 7.4 |
| V24 | 8.2 | 8.2 ← 8.1 |
| V25 | 8.3 | 8.3 ← 8.2 |

Étapes humaines prévues : 5.3 et 5.5 téléchargements simulés (un vrai téléchargement attend Anaël) ; 5.7 attend une release de slm-quality-bench synchronisée sur master (sinon 5.8 et a5 partent sans elle, décision Q7) ; 7.2 relecture par Anaël des verdicts du jeu fixe (décision Q4), le reste avance en attendant ; 6.3 SMTP factice seulement.

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
- 2026-10-19 07:09 · 4.3 · fusion · refusée (PR #68 en conflit après la fusion de la 3.4) ; master à fusionner dans la branche · —
- 2026-10-19 07:09 · run · état · PR `chore/etat-run` ouverte (#71) avec `.gitattributes` (journal en `merge=union`) · —
- 2026-10-19 07:15 · 4.8 · CI · PR #70 ouverte · 8e2f758
- 2026-10-19 07:15 · 4.3 · fusion master · conflits `components.css` et `components/index.js` (3.4) gardés des deux côtés ; 1037 v2 ; poussé · a1b411c
- 2026-10-19 07:15 · run · décision · pause demandée par Anaël pour un /clear ; file de fusion #71 → #68 → #70 lancée · —
- 2026-10-19 07:21 · 3.5 · dev · fini, 1010 v2, 153 E2E ; table de prix cloud livrée vide (aucune source datée dans le dépôt) : coût cloud « inconnu » avec raison · 763a122
- 2026-10-19 07:21 · 3.5 · attente humaine · table `[cloud.prices]` de `wavelocalai.toml` à remplir par Anaël (prix par million de tokens entrée/sortie, `retrieved_at`, `source`) · —
- 2026-10-19 07:33 · run · état · PR #71 fusionnée (fichiers d'état + `.gitattributes`) · 644eb47
- 2026-10-19 07:33 · 4.3 · CI · rouge Windows (`test_read_budget` /api/models 440 ms, minutage) ; job relancé · a1b411c
- 2026-10-19 07:33 · 4.8 · CI · rouge (fusion avec 3.4 : `arena.js` 606 lignes > 600) ; à la reprise : fusionner master dans la branche et alléger `arena.js` · 8e2f758
- 2026-10-19 07:38 · run · reprise · après /clear (périmètre Epics 3 à 8 sauf 8.4) · —
- 2026-10-19 07:38 · 4.3 · CI · rouge une 2e fois (`test_read_budget` /api/models 438 ms, Windows 3.11 seul) ; 3e relance · a1b411c
- 2026-10-19 07:38 · 4.8 · fusion master · 3.4 avait aussi sorti `nextTab` (`arena-tabs.js`) : doublon `core/tab-keys.js` retiré, `moveTab`, `arena.js` 598 lignes ; contrôles lancés · f029b6d
- 2026-10-19 07:38 · 4.5 · fusion master · conflit `components.css` gardé des deux côtés · 2f7a323
- 2026-10-19 07:38 · 3.5 · second-avis · lancé (Haiku) · —
- 2026-10-19 07:39 · 4.6 · dev · lancé (Sonnet high, worktree v2-4-6, depuis 4.5 revue 2f7a323 ; 4.7 attendra la 4.6 : mêmes fichiers) · —
- 2026-10-19 07:40 · run · décision · reprise des apprentissages d'agent-cost-kit (`docs/amelioration-continue.md`) : contrôles locaux allégés (CI = suite complète), échecs relancés seuls, plafond de 5 agents, file de fusion à 60 s · —
- 2026-10-19 07:41 · 3.5 · second-avis · 1 medium (`run_ended` publié avant l'écriture du statut : verdict lu null), 2 low (devise numérique, garde-fou statique faible) · —
- 2026-10-19 07:41 · 3.5 · review · lancée (Opus) · —
- 2026-10-19 07:45 · 3.5 · review · medium corrigé côté écran (relecture tant que le run est actif, test E2E), devise ISO 4217 ; regex statique écartée · ba68f14
- 2026-10-19 07:46 · 4.3 · fusion · CI verte à la 3e relance (minutage Windows 3.11) ; PR #68 fusionnée · f25f398
- 2026-10-19 07:47 · 4.5 · fusion master · 4.3 : conflit `documents.css` (deux blocs ajoutés en fin de fichier, gardés l'un après l'autre) · cbe054d
- 2026-10-19 07:53 · run · décision · Anaël : Epics 5 à 8 (sauf 8.4) ajoutés au plan du run, vagues V15 à V25 par fichiers touchés · —
- 2026-10-19 07:55 · 4.8 · contrôles · verts (1029 v2, 345 E2E, 10 integration) ; poussé, file de fusion · f029b6d
- 2026-10-19 08:05 · run · décision · Anaël : E2E ciblés par story + suite E2E complète sur master par lots, correctif des tests instables avancé (8.1, worktree fix-instables, Sonnet), section « Contrats partagés », base à jour pour second avis et revue ; Defender en attente de sa décision · —
- 2026-10-19 08:07 · run · décision · Anaël : Defender laissé tel quel (aucune exclusion) ; propositions 1 à 4 appliquées · —
- 2026-10-19 08:11 · 4.8 · fusion master · PR #70 en conflit après la 4.3 : `errors.py`, `rag/query.py`, `web/app.py`, `contrat-api.md` gardés des deux côtés ; tests ciblés verts (1 test RAG instable sous charge, vert seul) ; poussé · 8ab741a
- 2026-10-19 08:16 · 4.6 · dev · fini ; écarts : `strategy`/`top_k` dans `POST /api/rag/runs`, étapes de `retrieval_step`, `citations` (§7(d) n° 18 forme maquette), n° 12 en variante conservatrice · 94ec8bb
- 2026-10-19 08:16 · 4.6 · fusion 4.5 à jour (4.3) · conflits `documents-settings.js` (add/add), `rag/query.py`, `contrat-api.md` ; résolution confiée à Sonnet · —
- 2026-10-19 08:16 · fix-instables · dev · lancé (Sonnet high, worktree fix-instables) : `test_read_budget`, topbar, Arène clavier, axe sombre · —
- 2026-10-19 08:29 · 4.8 · fusion · PR #70 fusionnée · 3a36f55
- 2026-10-19 08:32 · 3.5 · fusion master · 4.8 : conflit `api.js` gardé des deux côtés · cf2e079
- 2026-10-19 08:32 · 3.6 · dev · lancé (Sonnet high, worktree v2-3-6, depuis 3.5 revue cf2e079 ; version 2.0.0a3) · —
- 2026-10-19 09:00 · run · décision · Anaël : run limité aux Epics 1 à 4 (fin à la 4.9, a4) ; Epics 5 à 8 reportés ; Ollama rendu après les contrôles de la 4.9 · —
- 2026-10-19 09:02 · fix-instables · dev · fini (tests seuls : budget meilleur de 3, redémarrage 90 s, attente du POST Arène, attente du pied avant axe) ; relu par l'orchestrateur ; PR #72 ouverte, file de fusion · 1db6592
- 2026-10-19 09:02 · 3.5 · prix cloud · recherche des prix publics lancée à la demande d'Anaël (Opus, lecture seule, proposition dans le scratchpad) · —
- 2026-10-19 09:03 · 4.5 · contrôles · faussés (script réécrit en cours d'exécution, poste saturé : 2 échecs + 47 erreurs de démarrage E2E) ; integration verte (11) ; échecs relancés seuls · 29ed7f1
- 2026-10-19 09:09 · 3.5 · prix cloud · 8 modèles relevés sur les pages officielles (USD) ; Anaël : intégrés à la PR 3.5, mistral-large-latest laissé « inconnu » ; Groq llama sans prix public · a9f0dab
- 2026-10-19 09:09 · 4.6 · fusion 4.5 à jour · résolue (Sonnet) : réglages de la Discussion dans `documents-chat-settings.js`, priorité `top_k` question > préférence > .toml, palliatif `search` retiré au profit de `GET /api/rag/settings` ; E2E relancés seuls verts · 2cc063f
- 2026-10-19 09:11 · 4.6 · second-avis · lancé (Haiku) · —
- 2026-10-19 09:11 · 4.7 · dev · lancé (Sonnet high, worktree v2-4-7, empilée sur la 4.6 2cc063f ; aucun téléchargement de reranker) · —
- 2026-10-19 09:19 · fix-instables · fusion · PR #72 fusionnée · a96db2e
- 2026-10-19 09:19 · 4.6 · second-avis · 2 medium (notation Self-RAG tronquée à 64 tokens : extraits non notés gardés ; appels HyDE/notation/reformulation hors garde-fou mémoire après la 4.8), 2 low · —
- 2026-10-19 09:19 · 4.6 · fusion master · 4.8 sans conflit · —
- 2026-10-19 09:19 · 4.5 · contrôles · E2E relancés seuls : 84 verts, 1 rouge réel (contour des points de l'Arène 1 px) : `components.css` cassé par la résolution « garder les deux » (règle coupée) ; reconstruit + test d'accolades équilibrées ; 4.6 et 4.7 portent la même casse (corrigée par fusion de la 4.5) · ad38c42
- 2026-10-19 09:19 · 4.5 · fusion master · 4.8 et #72 sans conflit ; branchement du garde-fou dans la Discussion confié à Sonnet · —
- 2026-10-19 09:19 · 3.5 · contrôles · lancés · a9f0dab
- 2026-10-19 09:32 · 4.5 · contrôles · garde-fou mémoire branché dans la Discussion (E2E Discussion 19 verts) ; PR #73 ouverte, file de fusion · 23357db
- 2026-10-19 09:32 · 4.6 · fusion 4.5 finale · sans conflit, CSS équilibrés · 5bd6a5b
- 2026-10-19 09:32 · 4.6 · review · lancée (Opus, liste du second avis) · —
- 2026-10-19 09:36 · 3.5 · contrôles · verts (244 E2E ciblés, 1 erreur connue corrigée par #72 ; 11 integration) ; PR #74 ouverte, file de fusion · a9f0dab
- 2026-10-19 09:47 · 4.5 · fusion · PR #73 fusionnée · 3e11106
- 2026-10-19 09:48 · 4.6 · review · 2 medium corrigés (budget et gabarit de notation : 20 verdicts sur 20 sur qwen2.5:1.5b ; garde-fou sur HyDE/notation/reformulation), préambule de reformulation retiré, 1 low rejeté ; report : integration HyDE/Self-RAG de bout en bout · cb98d39
- 2026-10-19 09:50 · 3.5 · fusion · PR #74 fusionnée · 03243e5
- 2026-10-19 09:53 · 3.6 · dev · fini (version 2.0.0a3, réouverture, exports CSV/MD, effacement AD-13, carte démo) ; §7(d) n° 3, 7, 8 en variante conservatrice · 1978ab7
- 2026-10-19 09:53 · run · incident · `git stash` partagé entre worktrees : l'agent de la 3.6 a appliqué le stash d'un autre agent, puis rétabli son travail par SHA ; 4.7 prévenue ; consigne : plus de `git stash` dans les agents · —
- 2026-10-19 09:53 · 3.6 · fusion master · 3.5 et 4.5 sans conflit, `arena.js` 589 lignes · af15af8
- 2026-10-19 09:53 · 3.6 · second-avis · lancé (Haiku) · —
- 2026-10-19 09:57 · 4.7 · dev · fini (reranker hors ligne seulement, raison affichée sinon ; 54 E2E Discussion/Base) ; écarts `reranker` dans `GET /api/rag/settings`, champs de `retrieval_step` · 6d8ab31
- 2026-10-19 09:57 · 4.7 · fusion 4.6 revue · conflits `rag/query.py`, `web/app.py` gardés des deux côtés (`reranker` + `guard`) ; 439 tests ciblés verts · 8e1ff2f
- 2026-10-19 09:57 · 4.7 · second-avis · lancé (Haiku) · —
- 2026-10-19 09:58 · 4.9 · dev · lancé (Sonnet high, worktree v2-4-9, empilée sur 4.7 8e1ff2f ; version 2.0.0a4) · —
- 2026-10-19 10:00 · 3.6 · second-avis · aucun high/medium ; 3 low (codes `run_not_found`/`not_found`, réouverture d'un run non Arène, « (effacée) » à tort) · —
- 2026-10-19 10:00 · 3.6 · review · lancée (Opus) · —
- 2026-10-19 10:03 · 4.7 · second-avis · aucun high/medium ; 4 low (requêtes Hub de fastembed avant le chargement hors ligne, test réseau sur un faux, double chargement après annulation, fusion Self-RAG sans score) ; API fastembed 0.9.0 vérifiée · —
- 2026-10-19 10:03 · 4.7 · review · lancée (Opus) · —
- 2026-10-19 10:05 · run · état · PR #75 fusionnée (`mergeable` UNKNOWN passager à la 1re tentative) · cc7e1bf
- 2026-10-19 10:14 · 3.6 · review · medium corrigé (question effacée restée dans le champ et le brouillon), run non Arène « Résultat introuvable », libellés export/arena_busy ; 2 low rejetés · 0c907bc
- 2026-10-19 10:15 · 3.6 · PR · #76 ouverte (CI) ; contrôles locaux après ceux de la 4.6 · 0c907bc
- 2026-10-19 10:15 · 4.7 · review · medium corrigé (chargement unique partagé, annulation sans double chargement) ; test réseau sur le vrai fastembed (venv jetable hors ligne) ; requêtes Hub réfutées ; reports : nom de cache vs dépôt source (5.5), énergie du reclassement (AD-10) · 15d461e
- 2026-10-19 10:19 · 4.6 · contrôles · verts (230 E2E ciblés, 11 integration) ; PR #77 ouverte, file de fusion · 23233ef
- 2026-10-19 10:19 · 3.6 · contrôles · lancés · 0c907bc
- 2026-10-19 10:36 · 4.6 · fusion · PR #77 fusionnée · 8d6210d
- 2026-10-19 10:36 · 3.6 · contrôles · 279 E2E verts, 1 rouge réel (`test_shell` : la carte démo appelait `/api/models` avant `shell-ready`, AD-15) corrigé (58 E2E coquille/démo/Flow 1 verts) ; integration 11 ; master (4.6) fusionné sans conflit ; poussé · e96be54
- 2026-10-19 10:36 · run · outil · `checks.sh` : la relance seule précise le marqueur (`-m`), sinon un E2E relancé était désélectionné · —
- 2026-10-19 10:36 · 4.7 · fusion master · 4.6 sans conflit ; contrôles lancés · d5237c7
- 2026-10-19 10:46 · 4.9 · dev · fini (E2E Flow 2, integration naive + self_rag sur Ollama 17 s, carte Documents de l'Accueil, version 2.0.0a4) ; écart : appel `GET /api/rag/documents` sur l'Accueil (AD-6, variante conservatrice) · c935eff
- 2026-10-19 10:46 · 4.9 · fusion 4.7 puis 3.6 · 4.7 sans conflit ; 3.6 : versions gardées à a4, `home.js` et `test_shell_static.py` en conflit de fond (laissés au relecteur) · —
- 2026-10-19 10:46 · 4.9 · second-avis · lancé (Haiku) · —
- 2026-10-19 10:51 · 3.6 · fusion · PR #76 fusionnée ; Epic 3 terminé, préversion 2.0.0a3 (tag et release en attente d'Anaël) · 360c6a4
- 2026-10-19 10:51 · 4.9 · second-avis · 1 high (l'Accueil appelle `/api/rag/documents` avant `shell-ready`, AD-15, même défaut que la 3.6), 1 medium (double appel au premier passage) · —
- 2026-10-19 10:51 · 4.9 · review · lancée (Opus) avec fin de fusion de la 3.6 (`home.js`, `test_shell_static.py`) · —
- 2026-10-19 10:55 · 4.7 · contrôles · verts (206 E2E ciblés, 11 integration) ; PR #78 ouverte, file de fusion ; `e2e_cibles.sh` : écrans documents → aussi `test_discussion*` · d5237c7
- 2026-10-19 11:05 · 4.9 · review · high corrigé (`core/shell-ready.js` partagé, Accueil après `shell-ready`), medium corrigé (une lecture par affichage, E2E), fusion 3.6 terminée ; report : `wl-model-picker.js` 666 lignes (dette 8.1) · 50ef444
- 2026-10-19 11:05 · 4.9 · contrôles · lancés en complet (tous E2E, v2, v1, integration ; passe E2E complète du lot) · b46254b
- 2026-10-19 11:09 · 4.7 · fusion · PR #78 fusionnée · 4fb98c8
- 2026-10-19 11:51 · 4.9 · contrôles · verts en complet (459 E2E, 12 integration, 1238 v2, 1286 v1) ; Ollama rendu à Anaël · —
- 2026-10-19 11:52 · 4.9 · PR · #79 ouverte (master avec 4.7 finale fusionné, 408 tests ciblés verts), file de fusion · 47ee04f
- 2026-10-19 12:06 · 4.9 · fusion · PR #79 fusionnée ; Epic 4 terminé, MVP terminé, préversion 2.0.0a4 (tag et release en attente d'Anaël) · de1288c
- 2026-10-19 12:06 · run · fin · run arrêté à la fin de l'Epic 4 (décision d'Anaël) ; Epics 5 à 8 reportés · —
- 2026-10-19 12:29 · run · décision · Anaël : Ollama disponible (pauses ponctuelles), Groq à 0 et mistral-large-latest vérifié par l'API (PR #81), sprite accepté, `uv sync` du dépôt principal fait · —
- 2026-10-19 12:32 · run · décision · Anaël : recommandations acceptées, consignées dans `decisions-2026-10-19.md` (PR #82) ; passe « report au contrat » ajoutée en V15 · —
