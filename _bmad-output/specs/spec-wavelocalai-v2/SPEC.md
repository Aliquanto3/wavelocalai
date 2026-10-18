---
id: SPEC-wavelocalai-v2
companions:
  - pile-technique.md
  - contrat-api.md
  - etapes-et-criteres.md
  - ../../planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md
  - ../../../docs/audits/refonte-2026-10/03-ux-front.md
  - ../../../AGENTS.md
  - ../../../docs/audits/frontend-2026-09/SYNTHESE.md
  - ../../planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md
  - ../../planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md
sources:
  - ../../../docs/audits/refonte-2026-10/00-synthese.md
  - ../../../docs/audits/refonte-2026-10/01-performance.md
  - ../../../docs/audits/refonte-2026-10/02-architecture-back.md
  - ../../../docs/audits/refonte-2026-10/04-analyse-ancienne-v2.md
  - ../../../docs/audits/refonte-2026-10/05-code-ancienne-v2.md
---

> **Contrat canonique.** Cette spec et ses `companions:` forment le contrat complet de ce qu'il faut construire, tester et valider. Les sources ne servent qu'à la traçabilité.
>
> **Priorités.** Les règles `AD-1` à `AD-23` d'`ARCHITECTURE-SPINE.md` priment sur `pile-technique.md`, `contrat-api.md` et `03-ux-front.md`. De `03-ux-front.md`, seul le §3 est contractuel ; il prime sur `EXPERIENCE.md` pour l'architecture d'information ; `DESIGN.md` reste la source des jetons (`tokens.css`, test de dérive).

# wavelocalai v2

## Why

**Douleur et vision.** La v1 Streamlit montre que de petits modèles locaux suffisent, mais elle dessert sa propre démonstration : chaque clic relance la page, les résultats de l'Arène, de l'Évaluation et de l'Équipe disparaissent, rien ne s'affiche en flux, le premier accès coûte 6 à 14 s, et le CO₂ local affiché est une constante (0,19 mg/token quel que soit le modèle). Quatre librairies instables (Ragas, LangGraph, CrewAI, Chroma) et 2,2 Go de `.venv` (dont torch) rendent la maintenance coûteuse. Les consultants Wavestone qui font la démo d'avant-vente ou l'atelier de formation (Flow 1 et Flow 2 d'`EXPERIENCE.md`) ont besoin d'un outil rapide, fidèle dans ses mesures et lisible du fond d'une salle. La v2 refait le serveur et le front dans ce dépôt, en réutilisant la logique métier saine de `src/core/` et le code du harnais `agentic-harness-training-demo`.

## Capabilities

Étape du plan entre parenthèses ; le MVP couvre CAP-1 à CAP-9 (étapes 1 à 4). Critères détaillés : `etapes-et-criteres.md`.

- **CAP-1** (étape 1)
  - **intent:** L'utilisateur ouvre l'app et dispose d'une coquille utilisable même Ollama arrêté, avec une barre haute (état d'Ollama, bascule cloud, CO₂ de session) et l'état du système en direct.
  - **success:** Coquille affichée en < 300 ms en local ; « Ollama ne répond pas » en < 3 s ; aucune requête du navigateur hors de `127.0.0.1` (E2E).
- **CAP-2** (étape 1, D1)
  - **intent:** Le cloud n'est utilisé que sur décision explicite, visible sur chaque modèle et chaque réponse.
  - **success:** Bascule désactivée à chaque chargement de page et conservée d'un écran à l'autre ; le serveur refuse un modèle cloud sans `allow_cloud` (test d'API) ; badge Local/Cloud présent sur chaque modèle et réponse.
- **CAP-3** (étape 1)
  - **intent:** L'utilisateur choisit un modèle dans une liste unifiée qui dit son origine, son type et pourquoi il est proposé par défaut.
  - **success:** Le sélecteur groupe Local et Cloud, se filtre au clavier, ne propose aucun modèle d'embedding ni reranker pour générer, affiche la pastille MoE (« MoE 3B actifs ») ; chaque défaut porte sa raison.
- **CAP-4** (étape 1)
  - **intent:** Toute génération est une exécution annulable dont le flux survit à la navigation et dont les erreurs s'expliquent en français.
  - **success:** Quitter un écran pendant une génération puis revenir reprend le flux sans perte ni doublon ; toute erreur suit `{code, message, action, detail}` ; « occupé » rend un 409 avec raison.
- **CAP-5** (étape 2)
  - **intent:** L'utilisateur converse en flux avec un modèle local ou cloud (Ollama, OpenAI/Groq, Anthropic, Mistral) et voit ses mesures.
  - **success:** Premier token affiché dès réception ; « Arrêter » coupe en < 1 s et garde le partiel ; débit final = `eval_count / eval_duration` (D3), provisoire marqué comme tel, chargement à part ; conversation persistée, exportable (JSON ou Markdown) et effaçable.
- **CAP-6** (étapes 2 et 5)
  - **intent:** Chaque réponse et la session affichent un CO₂ honnête sur sa méthode.
  - **success:** Une réponse locale affiche un CO₂ mesuré qui varie selon le modèle ; une réponse cloud affiche une estimation ecologits ou « non mesurable » avec sa raison, jamais 0 ni « — » nu ; CO₂ de session = somme des réponses mesurées, non-mesurables comptés à part.
- **CAP-7** (étape 3)
  - **intent:** L'utilisateur compare côte à côte plusieurs modèles sur une même question, notés par un juge, et conclut chiffres à l'appui.
  - **success:** 3 colonnes se remplissent en flux (locaux en séquence, cloud en parallèle) ; un délai dépassé n'arrête pas les autres ; « non évalué » n'est jamais 0 ; classement, matrice qualité/CO₂ et verdict local/cloud chiffré (écart de note, coût pour 1 000 requêtes, CO₂, données restées sur le poste) ; résultat rouvrable par URL et exportable (CSV, Markdown) avec preuve (fiche machine, version d'Ollama, digests, méthode CO₂, juge) ; Flow 1 joué en E2E avec modèles simulés.
- **CAP-8** (étape 4)
  - **intent:** L'utilisateur constitue et gère sa base documentaire locale.
  - **success:** Zone de dépôt visible sans délai ; progression par fichier ; un échec affiche sa raison et laisse le compteur inchangé ; suppression d'un document seul ; « Vider » annonce le nombre d'extraits et « Annuler » ne supprime rien.
- **CAP-9** (étape 4)
  - **intent:** L'utilisateur interroge ses documents et vérifie d'où vient la réponse.
  - **success:** Les sources (document, page, extrait entier) arrivent avant la réponse ; stratégies naïve, HyDE et Self-RAG disponibles ; le garde-fou mémoire garde la question et chiffre le besoin réel, modèle déjà chargé compris ; Flow 2 joué en E2E sur une base de test.
- **CAP-10** (étape 5)
  - **intent:** L'utilisateur suit la sobriété de sa session et administre ses modèles sur un écran « Modèles » à part de l'Arène.
  - **success:** Métriques en direct sans clic, arrêtées quand l'onglet est masqué ; historique carbone ; avant installation, le modèle dit s'il tient en mémoire, progression chiffrée ; décharger, supprimer ; fiche modèle, « Pourquoi ce débit ? » et « Sur d'autres postes » (`qb.results/1`).
- **CAP-11** (étape 6)
  - **intent:** L'utilisateur fait agir un agent seul ou une équipe d'agents et suit chaque étape.
  - **success:** Chaque étape apparaît en direct et se déplie ; aucun email envoyé sans validation explicite (D2) ; l'équipe affiche son schéma et sa trace par agent, s'arrête sur demande, garde son rapport ; parité avec l'agent seul et l'équipe v1.
- **CAP-12** (étape 7)
  - **intent:** L'utilisateur évalue la fidélité et la pertinence d'une réponse documentaire et teste le respect d'un format.
  - **success:** Sur un jeu fixe, scores et verdict par affirmation arrivent au fil de l'eau ; juge indisponible = « non évalué » avec raison ; le banc dit si la sortie respecte le format attendu, avec interrupteurs « format imposé » et « réponse concise ».
- **CAP-13** (après l'étape 5)
  - **intent:** L'utilisateur voit quel modèle convient à quel usage d'après le banc publié.
  - **success:** Sous-écran `#/arene/references` et carte d'Accueil : une carte par usage, groupe des meilleurs, intervalle, débit sur la machine de référence, lus depuis `qb.results/1`.
- **CAP-14** (étape 8)
  - **intent:** La v2 remplace la v1 sans perte visible.
  - **success:** Zéro violation axe-core sur tous les écrans, clair et sombre ; grille RGAA 4.1 remplie ; lisible à 200 % et à 320 px CSS sans défilement horizontal ; mode projection validé sur vidéoprojecteur réel ; parité listée page par page ; v1 archivée ; 2.0.0 publiée.

## Constraints

- Python 3.11 minimum (`>=3.11,<3.13`) pour tout le dépôt dès le premier lot (AD-1).
- Construite dans ce dépôt ; préversions `2.0.0-alpha.N`, `2.0.0` à la bascule ; la v1 reste lançable jusque-là, en maintenance stricte (`1.3.x`, correctifs bloquants et synchro du banc seulement).
- **MVP figé = étapes 1 à 4**, écrans Accueil, Chat libre, Arène, Base documentaire et Discussion : rien ne s'y ajoute avant sa livraison. Un lot = une PR fusionnée sur `master` en un à deux jours, pas de branche longue.
- « Terminé » = code et tests verts vérifiables par l'agent ; recette humaine en fin de lot sur une démo réelle ; contrôle à l'œil des sorties brutes dès le premier lot.
- Pas d'abstraction sans second cas ; fichiers de 600 lignes au plus ; une page de spec au plus par lot ; une question à Anaël seulement si elle bloque le lot.
- D1 à D7 de septembre en vigueur, dont D1 (local par défaut), D2 (email validé), D3 (débit `eval_count / eval_duration`), D5 (écoute locale), D7 (tests pytest, E2E marqués `e2e`).
- Tout local : serveur sur `127.0.0.1`, aucune requête navigateur hors de `127.0.0.1`, aucun CDN, installation par `uv sync` seul, ni Node ni téléchargement à l'exécution.
- Budgets : changement d'écran < 150 ms, premier rendu < 1 s, aucune route de lecture > 300 ms Ollama arrêté, aucun appel réseau ni import lourd dans le chemin de rendu.
- Pile imposée (détail `pile-technique.md`) : FastAPI + SSE ; front en modules JS natifs sans compilation dans une coquille unique ; port `ChatModel` maison, appel natif `/api/chat` pour Ollama ; boucle d'agents maison ; sqlite-vec et embeddings Ollama ; juge maison ; CodeCarbon par run et ecologits ; SQLite unique. Sans LangChain, LangGraph, CrewAI, pydantic-ai, Ragas, Chroma, sentence-transformers ni torch.
- Le benchmark reste dans `slm-quality-bench` : l'app ne lit que ses résultats publiés (contrat `qb.results/1`, depuis le fichier synchronisé, jamais par le réseau, AD-22), n'en produit pas et ne modifie ni `scripts/benchmark_slm.py` ni le `src/core/` de la v1.
- Charte Wavestone (primaire `#451DC7`, icônes Material, aucun emoji), typographie Aptos puis Inter servie localement ; textes en français avec clés i18n.
- Dépôt public : `data/` jamais commitée ; « Effacer » efface réellement (`secure_delete` + `VACUUM`).

## Non-goals

- Aucune exigence de publication ni mesure de banc dans l'app (c'est `slm-quality-bench`).
- Pas de moteur `llama-server` avant la fin de l'étape 8.
- Pas de migration des index Chroma : réindexation.
- Pas de nouvelle fonctionnalité dans la v1.
- Pas d'interface anglaise en 2.0 ; pas d'usage multi-utilisateur ni d'exposition réseau par défaut.
- Pas de dépôt séparé pour la v2.

## Success signal

Sur un PC pro de 16 Go sans GPU, avec `2.0.0-alpha` installée par `uv sync` seul, Flow 1 (Arène d'avant-vente) puis Flow 2 (atelier documentaire) se jouent de bout en bout devant un public, sans recharger la page ni perdre un résultat, avec débit D3 et CO₂ affichés pour chaque réponse.

## Assumptions

Aucune.

## Open Questions

Aucune.
