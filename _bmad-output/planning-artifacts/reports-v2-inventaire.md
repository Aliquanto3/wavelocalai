---
title: 'Inventaire des reports de la v2 (MVP en cours)'
created: '2026-10-18'
scope: 'Reports des stories 1.1 à 1.11, du run autonome, de deferred-work.md et de la §Deferred de la spine'
sources:
  - _bmad-output/implementation-artifacts/story-1-1.md à story-1-7.md (master, 2936e3f)
  - origin/feat/v2-coquille:_bmad-output/implementation-artifacts/story-1-8.md
  - worktrees du run, en lecture : story-1-9.md et story-1-10.md (feat/v2-selecteur), story-1-11.md (feat/v2-accueil), branches non poussées au 2026-10-18
  - _bmad-output/implementation-artifacts/run-autonome-mvp.md (copie de travail du 2026-10-18, sections « Stories » et « Décisions »)
  - _bmad-output/implementation-artifacts/deferred-work.md
  - ARCHITECTURE-SPINE.md §Deferred
---

# Inventaire des reports de la v2

Relevé en lecture seule le 2026-10-18, pendant le run autonome du MVP. Chaque ligne cite sa source (`S1.3-d2` = 2ᵉ élément de l'en-tête `deferred` de la story 1.3 ; `S1.3-R` = section `## Revue` ; `RUN` = `run-autonome-mvp.md` ; `DW` = `deferred-work.md` ; `SP` = spine §Deferred).

Classes :

- **(a)** va dans une story des Epics 2 à 4 encore à faire : critère proposé dans `epics.md`, section « À ajouter aux stories du MVP » ; le run en cours décide de l'intégrer.
- **(b)** va dans une story des Epics 5 à 8 : intégré aux stories de ces epics.
- **(c)** correctif technique : groupé dans la story de dette 8.1.
- **(d)** écarté, avec le motif.

Les stories 1.9 à 1.11 n'étaient pas encore relues (second avis et revue à faire) : leurs reports peuvent changer à la revue.

## (a) Vers les stories des Epics 2 à 4

| # | Élément | Source | Story | Déjà couvert par un critère ? |
|---|---|---|---|---|
| A1 | sqlite-vec absent du verrou | S1.1-d1 | 4.1 | non : ajouter « sqlite-vec à la version de la spine §Stack, ajouté au verrou par installation réelle » |
| A2 | ecologits absent du verrou | S1.1-d1 | 2.5 | oui (« ecologits épinglé `>=0.11.3,<0.12` ») |
| A3 | Extra `rerank` (fastembed) déclaré mais jamais exercé | S1.1-d1 | 4.7 | oui (`uv sync --extra rerank`) |
| A4 | `lane_timeout_s = 300` provisoire, lu par aucun code | S1.2-d2 | 3.1 | non : le délai de lane est lu dans `Settings` et sa valeur est confirmée ou corrigée par la story |
| A5 | Réhydratation de `sources` depuis `chunks` au rejeu | S1.3-d1 | 4.4 | oui |
| A6 | Effacement AD-13, `ensure_vec_table(dim)`, sqlite-vec | S1.3-d4 | 2.6, 4.1, 4.3 | oui |
| A7 | Adaptateur `fake` de l'`Embedder` | S1.4-d1 | 4.1 | oui |
| A8 | `verdict` d'Arène dans l'instantané | S1.4-d2 | 3.5 | oui |
| A9 | CO₂ des runs de test `unmeasurable` faute de `greenops/` | S1.4-d3 | 2.3 | oui (le service passe un vrai `co2`) |
| A10 | `hub.publish("token")` brut contourne le groupage par 50 ms, sans garde-fou | S1.4-d4, S1.4-R | 2.1 | non : `publish` refuse le type `token` (seul `publish_token` l'émet), test |
| A11 | Reprise E2E dans le navigateur ; sémaphore Ollama ; délai de lane | S1.4-d5 | 2.1, 2.2, 3.1 | oui |
| A12 | Ports et adaptateurs absents de `models/port.py` | S1.5-d1 | 2.1 | oui |
| A13 | Table Groq → ecologits (deux entrées) à confirmer | S1.5-d2 | 2.5 | non : le test de contrat confirme ou corrige chaque entrée de `[cloud.groq_ecologits]` |
| A14 | Identifiants cloud de `[cloud.models]` non vérifiés (`available` = clé présente) | S1.5-R | 2.4 | non : la recette vérifie chaque identifiant contre la liste du fournisseur au premier appel réel ; un identifiant refusé donne un code d'erreur, pas un `internal` |
| A15 | « Tient en mémoire » ignore le modèle déjà chargé (`/api/ps`) | S1.5-d3 | 4.8 | oui (modèle déjà chargé) ; VRAM et contexte en B6 |
| A16 | Tests `integration` d'Epic 1 sautés sans Ollama, à rejouer | S1.6-d4, RUN | 2.1 | non : la story rejoue `pytest tests/v2 -m integration` (Epic 1 compris) et consigne le résultat |
| A17 | Personne ne publie `carbon_updated` | S1.7-d1 | 2.3 | oui |
| A18 | Version d'Ollama `null` dans la fiche machine tant que la sonde ne l'a pas vue | S1.7-d3 | 3.6 | non : l'export lit l'état en cache de la sonde ; Ollama joignable, la version n'est jamais `null` |
| A19 | Blanc sur `primary-dark` (4,26:1) pour les boutons pleins | S1.8-d3, DW | 2.2 | non, **et à trancher** (décision Q1) : axe relèvera le premier bouton plein en sombre |
| A20 | Politique de contenu sans `blob:` pour les exports | S1.8-d4 | 2.6, 3.6 | non : export par lien vers la route serveur (`Content-Disposition: attachment`), sans `blob:` ni élargissement de la politique |
| A21 | Deux `mount` concurrents d'un écran à `mount` asynchrone quand le paramètre change | S1.8-R | 3.6 | non : `#/arene/comparer/<a>` puis `<b>` pendant le `mount` ne monte que `<b>` (E2E) |
| A22 | Étapes « Recherche des extraits… » et RAG de `wl-run-status` | S1.10-d1 | 4.5, 4.6 | oui |
| A23 | Aucun écran ne monte `wl-model-picker` ni `wl-run-status` | S1.10-d2 | 2.2 | oui |
| A24 | Échap ferme un panneau de la barre haute sans `preventDefault` et arrête aussi le run | S1.10-d3 | 2.2 | non : Échap avec un panneau ouvert ferme le panneau seulement (E2E) |
| A25 | `wl-error` affiche les accents graves Markdown de l'action (`no_model`) | S1.10-d4 | 2.2 | non : `wl-error` rend l'action sans balisage Markdown visible, pour tous les codes |
| A26 | « Aucun modèle local disponible » lu sur l'état d'Ollama, pas sur la liste des modèles | S1.11-d2 | 3.6 | en partie : ajouter le cas Ollama démarré sans aucun modèle de conversation |
| A27 | Cartes « Démo recommandée » et « Assistant documentaire » | S1.11-d3 | 3.6, 4.9 | oui |
| A28 | Tentative coupée puis relancée : CO₂ compté partout | DW (story 24) | 2.1 | non : la tentative coupée est une feuille close avec son `co2`, comptée dans la session |
| A29 | Texte partiel effacé et relance annoncée pendant la seconde tentative | DW (story 24) | 2.2 | non : à `retry`, le partiel est remplacé et la relance annoncée (E2E avec le `fake`) |
| A30 | Garde-fou mémoire appliqué à un modèle cloud | DW (story 22) | 4.8 | non : le garde-fou ne s'applique qu'aux modèles `origin = "local"` |
| A31 | Résidu vectoriel dans le blob vec0 | SP | 4.3 | oui |

## (b) Vers les Epics 5 à 8

| # | Élément | Source | Story |
|---|---|---|---|
| B1 | `approval_expiry_s = 600` provisoire, lu par aucun code | S1.2-d2 | 6.3 |
| B2 | Transitions vers `awaiting_approval` absentes du hub | S1.3-d5 | 6.3 |
| B3 | `ToolCall` ignoré par `stream_into_run` | S1.4-d2 | 6.1 |
| B4 | Formats d'appel d'outils et protocole d'équipe | SP | 6.1, 6.5 |
| B5 | Précision (`accuracy`) nulle tant que `qb.results/1` n'est pas lu | S1.6-d2 | 5.6 |
| B6 | « Tient en mémoire » sans VRAM (NVML) ni contexte (KV cache) | S1.5-d3 | 5.3 |
| B7 | Règles `agent` et `rag` provisoires, `rag` replié sur `chat` | S1.6-d3, S1.6-R, RUN | 5.7 |
| B8 | Pas de route d'écriture d'un défaut choisi | S1.6-d1 | 5.4, **à trancher** (décision Q2) |
| B9 | `POST /api/carbon/session/reset` et historique carbone | S1.7-d2 | 5.1, 5.2 |
| B10 | GPU (mémoire, température, bridage) hors du flux de 2 s | S1.7-d4 | 5.1 |
| B11 | Budget de `/api/system/identity` à froid (NVML) non chronométré sur la tour RTX 3050 | S1.7-R | 5.1 |
| B12 | `model_facts` rend des modèles supprimés au démarrage à froid | S1.5-R | 5.4 |
| B13 | Pause du flux système onglet masqué | S1.9-d2 | 5.1 (Sobriété) ; Accueil couvert par 1.11 |
| B14 | Étapes des agents dans `wl-run-status` | S1.10-d1 | 6.2 |
| B15 | Gras affiché avec ses astérisques dans une réponse d'agent (v1) | DW (story 18) | 6.2 (test de rendu Markdown d'une réponse d'agent) |
| B16 | Focus non placé sur le `h1` au premier chargement | S1.8-d2 | 8.2 (grille RGAA : critère 12.x à confirmer) |
| B17 | `constraints.txt` fige starlette 1.7.0 quand `uv.lock` résout 1.8.0 | S1.1-R | 8.4 (requirements et constraints régénérés à la bascule) |
| B18 | Borne haute de Python | SP | 8.4 |
| B19 | Récupération du reranker (run `pull`) | AD-17, story 4.7 | 5.5 |
| B20 | Passage `bmad-ux` avant l'écran Modèles | SP | prérequis de l'Epic 5 (déjà décidé par la spine §Deferred), à lancer avant le run de l'Epic 5 |
| B21 | E2E sur Edge par `WAVELOCALAI_E2E_CHROMIUM`, hors CI | RUN (Décisions) | 8.3 (suite E2E complète, mode d'emploi dans `AGENTS.md`) |

## (c) Correctifs techniques (story de dette 8.1)

| # | Élément | Source |
|---|---|---|
| C1 | `import wavelocalai` puis accès d'attribut, `importlib.import_module` et `__import__` échappent au test AST des couches | S1.1-R |
| C2 | Le test de budget de lecture ne voit pas une route `include_in_schema=False` posée par `include_router` | S1.2-d3 |
| C3 | Les `Mount` (`/static/`) échappent à la découverte du test de budget | S1.2-R |
| C4 | `uvicorn.access` journalise méthode et chemin au niveau INFO : garde qu'aucune route ne porte de texte saisi dans son chemin ou sa requête | S1.2-d4 |
| C5 | Verrou : toute `OSError` lue comme « un autre wavelocalai-v2 » ; `setup_logging` avant le verrou écrit dans le journal du serveur vivant | S1.2-R |
| C6 | Échec de la transaction de clôture (disque plein) : racine restée en mémoire, `run_ended` diffusé mais non persisté ; purger la racine et journaliser | S1.3-d6, S1.4-R |
| C7 | Windows, Ctrl+Break : SIGBREAK termine le processus sans `store.close` ni `lock.release` | S1.7-R |
| C8 | « Réessayer » (panneau Ollama) ne force pas la sonde | S1.9-d1 |
| C9 | Textes de `ollama_down` recopiés dans `fr.json` (deux sources, gardées par un test miroir) | S1.9-d3 |

## (d) Écartés

| # | Élément | Source | Motif |
|---|---|---|---|
| D1 | `CITATION.cff` en 1.3.0 | S1.1-d2 | couvert par le critère de publication de 1.11 (préversion `2.0.0a1`) |
| D2 | Arrêt propre : runs actifs → `cancelled` | S1.2-d1 | fait par 1.7 (`hub.stop()` dans `_Server.shutdown`, `test_real_shutdown.py`) |
| D3 | `Origin` non contrôlée sur une poignée de main WebSocket | S1.2-R | aucune route WebSocket au contrat (SSE seulement) |
| D4 | `409 run_busy` absent | S1.3-d2 | fait par 1.4 (`active_root`, `run_busy`) ; les écrans le rejoignent (2.2) |
| D5 | Flux SSE, reprise, routes de runs | S1.3-d3 | fait par 1.4 |
| D6 | Racine créée pendant `stop()` finie `interrupted` au démarrage suivant | S1.3-R | même effet qu'un arrêt brutal, prévu par AD-5 ; accepté au MVP |
| D7 | `test_real_launch.py` en cp1252 sous Windows | S1.3-d7, S1.4-d6, S1.5-d4 | corrigé sur `master` (`PYTHONIOENCODING=utf-8`, story 1.2) |
| D8 | Modèle sans indice MoE (famille hors catalogue, `/api/show` en échec) : actifs = total | S1.5-R | faute de signal ; le catalogue (`scripts/build_catalog.py`) corrige le cas |
| D9 | Client lent du flux système : perte des plus anciens événements | S1.7-d5 | voulu ; `carbon_updated` porte la somme complète |
| D10 | Pastilles de la barre haute | S1.8-d1 | livrées par 1.9 |
| D11 | Route inconnue renvoyée à l'Accueil sans annonce de raison | S1.8-R | hors critère ; seule une route `planned` a une raison |
| D12 | Aptos appelée par son nom et non par `local()` | S1.8-R | effet identique, aucune requête |
| D13 | `pyyaml` non déclaré | S1.8-R | corrigé par 1.8 |
| D14 | Préversion `2.0.0a1` non publiée par 1.11 | S1.11-d1 | publication par l'orchestrateur en fin d'Epic 1 |
| D15 | `models/port.py` en double (1.4 et 1.5) | RUN | réconcilié à la fusion (décision du run) |
| D16 | `PreferenceStore`, `SqliteFactsStore`, médiane `tps` à brancher | RUN | branchés (`web/app.py`, `SqliteRunStats`, `SqlitePreferenceStore`) |
| D17 | pydantic 2.12.x, cache de sonde, défauts `agent`/`rag` | RUN | décisions d'Anaël du 2026-10-18, intégrées à la spec et à la spine |
| D18 | Ollama par `127.0.0.1` (IPv6 de `localhost`) | RUN | déjà le défaut de `wavelocalai.toml` |
| D19 | Sept reports de `deferred-work.md` propres à la v1 (couleur primaire dans `test_accessibility.py`, attentes E2E Streamlit, `MetricsService.calculate_carbon`, relance des tests de l'Assistant documentaire, CO₂ des coupures dans les onglets v1, relance des agents LangChain) | DW | v1 en correctifs seulement ; leurs leçons transposables sont reprises en A19, A28, A29, A30 et B15 |
| D20 | Détail des colonnes, liste des codes d'erreur | SP | règles de processus déjà appliquées par chaque story |
| D21 | Moteur `llama-server` | SP | hors plan jusqu'à la fin de l'étape 8 (spec) |

## Décisions à prendre par Anaël

Ni la spec ni la spine ne les tranchent ; les stories citent leur numéro et portent la recommandation, à confirmer ou remplacer.

| # | Question | Bloque | Options | Recommandation |
|---|---|---|---|---|
| Q1 | Texte des boutons pleins en thème sombre : blanc sur `primary-dark` (#7E65E9) fait 4,26:1, sous AA | **2.2 (en cours de run)**, puis tout bouton plein | A. fond `primary` (#451DC7) avec texte blanc dans les deux thèmes (≈ 9,3:1 ; bouton moins détaché du fond sombre). B. texte quasi noir sur `primary-dark` (≈ 4,9:1 ; inhabituel pour la charte). C. nouveau jeton plus sombre pour les fonds de bouton en sombre, via `bmad-ux` (propre, mais une passe UX avant 2.2) | **A**, consigné dans `DESIGN.md` par `bmad-ux` au plus tôt (test de dérive des jetons) |
| Q2 | Où l'utilisateur choisit-il un modèle par défaut (AD-15 prévoit des « défauts choisis » dans `preferences`, aucune route n'existe) | 5.4 | A. aucun choix persistant (défaut calculé, choix gardé par conversation seulement). B. « Définir par défaut » sur l'écran Modèles (`PUT /api/models/defaults/{purpose}`). C. le sélecteur retient le dernier choix par usage, sans geste | **B** : geste explicite, raison « Choisi par vous », réversible ; C rend le défaut imprévisible en démo |
| Q3 | Bibliothèque d'équipes d'agents | 6.5, 6.6 | A. équipes figées dans un fichier versionné, seul le sujet change. B. équipes versionnées + modifications de l'utilisateur dans `preferences`. C. équipes entièrement éditables, stockées en base (nouvelle table) | **B** : parité avec « Configurer » de la v1 sans nouvelle table ; A perd une fonction de la v1 |
| Q4 | Jeu fixe de non-régression de l'évaluation | 7.2 | A. une dizaine de cas tirés d'un document du domaine public, verdicts annotés par Anaël (≈ 1 h). B. verdicts produits par un modèle cloud fort puis relus. C. jeu synthétique sans annotation, test de stabilité seulement | **A** : seule source de vérité humaine ; demande une session d'annotation d'Anaël |
| Q5 | Forme de l'archivage de la v1 à la bascule | 8.4 | A. retirer de `master` `src/app`, `src/core`, tests v1 et scripts qui importent `src.core` (`benchmark_slm.py`, `audit_and_update.py`, `setup_models.py`, `setup_rag_models.py`), v1 gardée par le tag `v1.3.x`. B. déplacer la v1 dans `legacy/` hors CI. C. garder la v1 lançable avec ses dépendances jusqu'à une 2.1 | **A** : le banc vit dans slm-quality-bench ; B garde les dépendances lourdes, C annule le gain de la refonte |
| Q6 | E2E en CI | 8.3 | A. local seulement (Edge), comme au MVP. B. job CI Linux nocturne avec Chromium de Playwright, plus local. C. E2E dans chaque PR | **B** : filet automatique sans ralentir les PR ; C triple la durée de la CI |
| Q7 | `benchmarks/slm-quality/slm-quality-results.json` absent de `master` (aucune release synchronisée) : calage des défauts `agent`/`rag` et références | 5.6 à 5.8 | A. attendre une release de slm-quality-bench avant l'Epic 5, 5.6 à 5.8 en dernier. B. développer 5.6 et 5.8 sur un fichier de test, reporter 5.7 jusqu'aux données. C. garder la règle provisoire pour 2.0.0 et retirer 5.7 | **B**, et pour `rag` : garder le repli sur `chat` tant que le banc ne publie pas d'usage documentaire |
