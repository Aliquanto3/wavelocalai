# Refonte de wavelocalai : synthèse des audits (octobre 2026)

- **Date :** 2026-10-18
- **Code audité :** `master` au 2026-10-18, avec les correctifs des PR #28 (juge Claude de Ragas) et #30 (modèles d'embedding, client Ollama sur `127.0.0.1`).
- **Rapports sources :**

  | Rapport | Objet | Auditeur |
  |---|---|---|
  | [`01-performance.md`](01-performance.md) | Temps d'import, temps par page, stabilité, mesurés | Sonnet |
  | [`02-architecture-back.md`](02-architecture-back.md) | Carte de `src/core/`, dépendances, back cible, API | Opus |
  | [`03-ux-front.md`](03-ux-front.md) | Parcours, irritants, front cible, wireframes, lots | Opus |
  | [`04-analyse-ancienne-v2.md`](04-analyse-ancienne-v2.md) | Ancien dépôt `wave_local_ai_v2` : ambitions, fonctionnalités, idées, leçons | Opus |
  | [`05-code-ancienne-v2.md`](05-code-ancienne-v2.md) | Ancien dépôt : ce qui a été construit, front React, code réutilisable | Sonnet |

- **Rôle de ce document :** l'entrée unique de la session qui conçoit la v2 (`bmad-product-brief` ou `bmad-spec`, puis `bmad-architecture` et `bmad-ux`). Il arbitre les écarts entre les rapports et liste les décisions. Les preuves restent dans les rapports.
- **Décisions de septembre maintenues :** D1 à D7 de [`../frontend-2026-09/SYNTHESE.md`](../frontend-2026-09/SYNTHESE.md), dont D1 (local par défaut, cloud désactivé à chaque ouverture) et D3 (débit `eval_count / eval_duration`).

## 1. Diagnostic en dix lignes

1. **La lenteur vient du back, pas des onglets.** Changer d'onglet coûte 3 à 5 ms. Un rerun de l'Arène coûtait 2,2 s, dont 2,16 s dans un seul appel Ollama sur `localhost` (repli IPv6 sous Windows). Corrigé dans la PR #30 : 0,11 s.
2. **Le premier accès coûte 6 à 14 s** : le tracker CodeCarbon du routeur (6,5 à 11,5 s, dont 9 s de `py-cpuinfo`), créé par session et jamais arrêté.
3. **Les imports pèsent** : 6,1 s pour la page RAG (sentence-transformers et torch), 4,1 s pour les Agents (CrewAI), 2,3 s pour le routeur (SDK Anthropic et OpenAI importés sans clé).
4. **Le `.venv` fait 2,2 Go.** torch seul pèse 509 Mo pour un modèle d'embedding de 90 Mo. `docling`, `einops`, `timeout_decorator` et `GPUtil` ne sont importés nulle part.
5. **Quatre librairies sont instables** : Ragas (sans version depuis janvier 2026), LangGraph (`create_react_agent` déprécié), CrewAI (API différente selon la machine) et Chroma (écritures concurrentes par session). Le mode Équipe est cassé avec Mistral cloud.
6. **Le CO₂ local affiché est une constante** (0,19 mg par token, quel que soit le modèle). La formule cloud recopie EcoLogits à la main.
7. **Streamlit limite l'UX** : chaque clic relance la page, les résultats de l'Arène, de l'Évaluation et de l'Équipe disparaissent au clic suivant, l'Arène n'affiche rien en flux.
8. **La logique métier utile se réutilise** : règles de choix des modèles, métriques, outils d'agents, sécurité des chemins, streaming des providers cloud.
9. **Le lien avec le banc se réduit à un contrat de données** : `scripts/benchmark_slm.py` n'importe que `src/core/config.py`, et l'app lit les JSON du banc.
10. **Les tests tiennent** : 867 tests unitaires passent, couverture de `src/core` à 81,65 %. Les 4 échecs signalés dans `AGENTS.md` ne se reproduisent plus.

## 2. Cible v2 retenue

Les deux auditeurs convergent sur la même pile, reprise du dépôt `agentic-harness-training-demo` :

| Couche | Choix | Remplace |
|---|---|---|
| Serveur | FastAPI + uvicorn, flux SSE, écoute sur `127.0.0.1` | Streamlit |
| Front | Une coquille HTML unique, modules JS natifs sans compilation ni Node, routeur par `hash`, écrans chargés à la demande, servis par FastAPI | Pages et onglets Streamlit |
| Modèles | Un port `ChatModel` sur les SDK officiels (Ollama, OpenAI et Groq, Anthropic, Mistral) ; un registre unique qui dit `origin` et `kind` | LangChain, `llm_provider`, `model_detector` et 5 fonctions de détection |
| Agents | Boucle d'outils maison, équipe séquentielle maison | LangGraph, CrewAI |
| RAG | sqlite-vec (repli numpy), embeddings servis par Ollama, reranker fastembed en option | Chroma, sentence-transformers, torch |
| Évaluation | Juge maison à sortie structurée, verdict par affirmation | Ragas |
| Carbone | CodeCarbon par exécution, hors du fil de requête ; EcoLogits pour le cloud | Tracker par session, constante par token |
| Persistance | Une base SQLite `data/wavelocalai.db` (runs, messages, documents, évaluations, jobs) | CSV d'émissions, état de session |
| Configuration | `wavelocalai.toml` versionné + `.env` pour les secrets, objet `Settings` sans effet de bord à l'import | `config.py` à effets de bord |

Gain attendu : environ 1,8 Go de dépendances en moins, quatre librairies instables en moins, aucune fonctionnalité visible perdue. Trois changements à annoncer aux utilisateurs : embeddings issus d'Ollama, évaluation « méthode Ragas » sans la librairie, schéma d'équipe dessiné par le front.

Budgets de performance (01, « Ce que la v2 doit éviter ») : changement d'écran < 150 ms, premier rendu < 1 s, aucune route de lecture > 300 ms avec Ollama arrêté, aucun appel réseau ni import lourd dans le chemin de rendu.

## 3. Écarts entre les rapports, arbitrés

| Sujet | Back (02) | Front (03) | Arbitrage |
|---|---|---|---|
| Forme des flux | Un `POST` SSE par fonction (`/api/chat`, `/api/arena`…) | Un `POST` crée une exécution et rend un `run_id` ; un flux `GET /api/runs/{id}/events` rejouable par `Last-Event-ID` ; annulation par `POST /api/runs/{id}/cancel` | **Modèle « run » du front.** Il fait survivre un flux à la navigation (critère du lot 1), et c'est le motif du harnais. La table `runs` du back le porte déjà. Les noms d'événements suivent la liste du front (03 §4.2) |
| Type de modèle | Registre avec `origin` | Champ `kind` (`chat`, `embedding`, `reranker`) exigé | **Le registre porte `origin` et `kind`.** Le filtre de la PR #30 (`is_embedding_model`) en donne la règle |
| Persistance des conversations | SQLite unique | Fichiers JSON dans `data/` (U4) | **SQLite**, table `messages`. Un seul stockage, et le bouton « Effacer » du front reste |
| CO₂ des modèles cloud | EcoLogits | « non mesurable » au MVP, EcoLogits ensuite (U6) | **EcoLogits dès qu'il connaît le modèle, marqué « estimation » ; sinon « non mesurable » avec sa raison.** Jamais 0, jamais « — » sans explication |
| Mode cloud | Non traité | Le back refuse un modèle cloud sans `allow_cloud` (D1) | **Retenu** : contrôle côté serveur, absent = faux |
| Concurrence dans l'Arène | Sémaphore Ollama à 1, cloud en parallèle | Locaux en séquence, cloud en parallèle (U7) | **Identiques** |

## 4. Plan de construction

La v2 se construit **dans ce dépôt** (décision du 2026-10-18), versionnée en SemVer ; il n'y aura pas de dépôt séparé. L'ancien dépôt `wave_local_ai_v2` est abandonné (§7). Le benchmark reste dans `slm-quality-bench`, dont l'app lit les résultats publiés (PR #32).

| Étape | Back | Front | Livrable vérifiable |
|---|---|---|---|
| 1. Socle | FastAPI, `Settings`, SQLite et migrations, `/api/health`, `/api/system/stream`, `/api/models` avec `origin` et `kind`, `/api/models/defaults`, modèle « run », format d'erreur unique, CI | Lot 0 : coquille, routeur, `tokens.css` et son test, icônes Material, barre haute (Ollama, bascule cloud, CO₂ de session), `model-picker` | Coquille en < 300 ms, utilisable Ollama arrêté ; aucun modèle d'embedding proposé pour générer |
| 2. Chat | Port `ChatModel` (4 fournisseurs), métriques D3, carbone par run | Lot 1, partie Chat | Premier token affiché dès réception, arrêt < 1 s, débit et CO₂ mesurés |
| 3. Arène | Exécutions multiplexées, file Ollama, juge | Lot 1, partie Arène | 3 colonnes en flux, résultat conservé et rouvrable par URL |
| 4. Assistant documentaire | Ingestion en job, embeddings Ollama, sqlite-vec, reranker, stratégies naïve, HyDE et Self-RAG | Lot 2 | Sources avant la réponse ; dépôt avec progression ; suppression d'un document |
| — | **MVP = étapes 1 à 4** (parcours 1 avant-vente et 2 atelier d'`EXPERIENCE.md`) | | |
| 5. Sobriété et Modèles | Historique carbone, installation avec progression | Lot 3 | CO₂ de session = somme des réponses mesurées |
| 6. Agents | Boucle d'outils, outils repris de `agent_tools`, email validé, équipe séquentielle | Lot 4 | Parité avec l'agent seul et l'équipe v1 |
| 7. Évaluation et Banc d'essai | Juge maison | Lot 5 | Scores par affirmation sur un jeu fixe |
| 8. Finition et bascule | Contrat JSON du banc en lecture seule | Lot 6 : projection, responsive, RGAA | Parité listée page par page ; v1 archivée |

Tailles indicatives (03 §5) : environ 8 à 10 semaines pour un développeur assisté par agents, MVP en 4 à 5 semaines.

## 5. La v1 pendant la refonte

Déjà fait le 2026-10-18 : PR #28 (juge Claude de Ragas, chat Claude sans temperature) et PR #30 (modèles d'embedding filtrés, Ollama injoignable sans blocage, client sur `127.0.0.1`, -2 s par interaction).

Restent des gains rapides, tous d'ordre UX donc admis par la règle de la v1, et hors du périmètre du banc :

| Gain | Effort | Effet mesuré |
|---|---|---|
| Tracker CodeCarbon unique par processus, démarré en fond | M | -6 à -11 s au premier accès |
| Imports `anthropic` et `openai` seulement avec une clé | S | -1,5 s au démarrage |
| `st.cache_data` court sur la liste des modèles et `model_menu` | S | reruns plus courts |
| `crew_engine.py:130` : hôte Ollama codé en dur | S | -2 s par mission d'équipe |
| Étape 0 du back : retirer `docling`, `einops`, `timeout_decorator`, `GPUtil` ; corriger la route Mistral du Crew | S | `.venv` plus léger, mode Équipe réparé |
| Note des tests d'`AGENTS.md` à jour (plus d'échec connu) | S | — |

## 6. Décisions à prendre

Les rapports en listent 21 (10 côté back, 11 côté front). Celles-ci engagent la conception ; les autres suivent leur recommandation par défaut.

| # | Décision | Recommandation | Source |
|---|---|---|---|
| 1 | Stack du front | Modules JS natifs sans compilation, coquille unique | 03 U1, U2 |
| 2 | Orchestration des agents | Boucle maison sur les SDK, sans LangChain ni CrewAI | 02 #1 |
| 3 | Base vectorielle et embeddings | sqlite-vec, embeddings Ollama, plus de torch | 02 #2, #3 |
| 4 | Évaluation RAG | Juge maison à sortie structurée | 02 #4 |
| 5 | CO₂ | CodeCarbon par run en local, EcoLogits en cloud, « non mesurable » expliqué sinon | 02 #5, 03 U6, §3 ci-dessus |
| 6 | Persistance | SQLite unique, conversations comprises | 02 §5.4, §3 ci-dessus |
| 7 | « Gestion des modèles » | Écran « Modèles » à part, hors de l'Arène (modifie `EXPERIENCE.md`) | 03 U5 |
| 8 | Typographie | Aptos puis Inter, comme `DESIGN.md` | 03 U3 |
| 9 | Dépôt de la v2 | **Tranché le 2026-10-18 :** ce dépôt, versions SemVer ; benchmark dans `slm-quality-bench` | Anaël |
| 10 | Investissement dans la v1 | Une dernière PR de gains rapides (§5), puis maintenance stricte | 03 U11, 01 |

## 7. Apports de l'ancien dépôt `wave_local_ai_v2`

L'ancien dépôt (août à octobre 2026) n'était pas une v2 de l'app : c'était un banc de mesure publiable (llama.cpp, juges cloud, front React en tableaux), sans chat, Arène, RAG ni agents (05 §1). Ses documents utiles sont copiés dans [`../../archive/ancienne-v2/`](../../archive/ancienne-v2/README.md) ; une copie complète est gardée hors dépôt.

### 7.1 Idées retenues pour l'app

| Idée (04 §3) | Où dans le plan | Données |
|---|---|---|
| « Quel modèle pour quel usage ? » : une carte par usage, groupe des meilleurs, intervalle, débit sur la machine de référence | Nouveau sous-écran `#/arene/references` et carte sur l'Accueil, après l'étape 5 | `qb.results/1` |
| Verdict local ou cloud chiffré à la fin d'une comparaison (écart de note, coût pour 1 000 requêtes, CO₂, données restées sur le poste) | Étape 3 (Arène) | L'app ; table de prix cloud datée dans `wavelocalai.toml` |
| « Sur d'autres postes » : débit et tenue en mémoire attendus sur les trois postes de référence, dont le PC pro de 16 Go sans GPU | Étape 5 (écran Modèles, Sobriété) | `qb.results/1` |
| Fiche modèle (dense ou MoE, paramètres actifs, quantification, licence, outils et raisonnement vérifiés) et pastille « MoE 3B actifs » dans le sélecteur | Étapes 1 (pastille) et 5 (fiche) | Ollama `/api/show`, catalogue, `qb.results/1` |
| Export de preuve : fiche machine, version d'Ollama, digest des modèles, méthode CO₂, juge | Étape 3 (export de l'Arène) | Table `runs` |
| Étiquettes de fiabilité (« indicatif », « un seul juge », « estimé », « non mesurable ») et « bridage thermique » | Étape 1 (composants `metric`, `badge`), Sobriété | NVML (idée de `machine_state.py`) |
| Banc d'essai : interrupteurs « format imposé » et « réponse concise » | Étape 7 | Paramètre `format` d'Ollama |
| Panneau « Pourquoi ce débit ? » (bande passante mémoire, paramètres actifs, VRAM) | Étape 5 | Fiche locale, catalogue |
| Moteur `llama-server` en option | Après l'étape 8 | Port `ChatModel` compatible OpenAI |

Déjà couverts : mode présentation, avertissement avant un envoi cloud (D1), absence nommée plutôt qu'un zéro (03 §3.7). Code à consulter pour l'étape 1 : `hardware.py`, `nvml.py`, `machine_state.py` (archive).

### 7.2 À transmettre à `slm-quality-bench`

Idées de 04 §4, dont la plus urgente : le contrat `qb.results/1` n'existe pas encore, et la vitesse par machine (décidée le 2026-10-18) est hors du périmètre de son `SPEC.md`. Le reste : comparateur cloud sur questions publiques, usages absents (classification, traduction, correction, code), variantes d'invite, llama.cpp contre Ollama, bande passante mémoire. Modules statistiques et suites de l'ancien dépôt : dans la copie complète.

### 7.3 Garde-fous tirés de son échec (04 §5, 05 §6)

- L'app ne porte aucune exigence de publication ; le MVP est fixé (§4, étapes 1 à 4) et rien ne s'y ajoute avant sa livraison.
- Un lot = une PR fusionnée sur `master` en un jour ou deux ; pas de branche longue.
- « Terminé » = code et tests verts, vérifiables par l'agent ; la recette humaine se fait en fin de lot, sur une démo réelle.
- Pas d'abstraction sans second cas (registre de moteurs à un seul moteur) ; fichiers de 600 lignes au plus.
- Une page de spec au plus par lot ; une question à l'utilisateur seulement si elle bloque le lot en cours.
- Contrôle à l'œil des sorties brutes dès le premier lot (défauts de mesure trouvés trop tard).
