---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/specs/spec-wavelocalai-v2/SPEC.md
  - _bmad-output/specs/spec-wavelocalai-v2/etapes-et-criteres.md
  - _bmad-output/specs/spec-wavelocalai-v2/contrat-api.md
  - _bmad-output/specs/spec-wavelocalai-v2/pile-technique.md
  - _bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md
  - docs/audits/refonte-2026-10/03-ux-front.md (§3 seul contractuel)
  - _bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md
  - _bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md
  - docs/maquette-v2/README.md (maquette validée, décisions D-1 à D-43 du 2026-10-18, reportées par sprint-change-proposal-2026-10-19.md)
scope: 'MVP (étapes 1 à 4, CAP-1 à CAP-9) et après le MVP (étapes 5 à 8, CAP-10 à CAP-14) détaillés ; reports du MVP intégrés depuis reports-v2-inventaire.md'
updated: '2026-10-19'
---

# wavelocalai v2 - Découpage en epics et stories

## Overview

Ce document découpe la spec `spec-wavelocalai-v2` (qui tient lieu de PRD), la spine d'architecture (AD-1 à AD-23) et le contrat UX (`03-ux-front.md` §3, `DESIGN.md`, `EXPERIENCE.md`) en epics et stories. Une story = un lot livrable en une PR fusionnée sur `master` en un à deux jours. Priorités : AD > `pile-technique.md` et `contrat-api.md` > `03-ux-front.md` §3 > `EXPERIENCE.md` pour l'architecture d'information ; `DESIGN.md` reste la source des jetons.

## Requirements Inventory

### Functional Requirements

**Étape 1 — Socle (CAP-1 à CAP-4)**

- FR1 : La coquille (barre haute, navigation, `<main>`) s'affiche sans dépendre d'aucun appel au back, même Ollama arrêté (CAP-1).
- FR2 : La barre haute montre l'état d'Ollama par une pastille avec libellé (« Ollama disponible » / « Ollama ne répond pas » en < 3 s), un panneau (version, modèles chargés, mémoire, « Réessayer »), la bascule « Autoriser le cloud » et le CO₂ de session (CAP-1).
- FR3 : `GET /api/health` rend version, `instance_id` (nouveau à chaque démarrage), Ollama `{up, version, latency_ms}` et fournisseurs cloud `{id, configured}` sans les appeler.
- FR4 : `GET /api/system/stream` publie toutes les 2 s (enveloppe AD-6, `run_id: null`, sans rejeu) l'état d'Ollama, CPU %, mémoire, modèles chargés, `carbon_updated`, `runs_active`.
- FR5 : `GET /api/system/identity` rend la fiche machine.
- FR6 : La bascule cloud est désactivée à chaque chargement de page, conservée d'un écran à l'autre ; le serveur refuse tout modèle `origin != "local"` sans `allow_cloud` (`cloud_not_allowed`), `allow_cloud` absent valant faux (CAP-2, D1).
- FR7 : Un badge Local / Cloud / Origine inconnue accompagne chaque modèle et chaque réponse, dérivé du fournisseur réel (CAP-2).
- FR8 : `GET /api/models?allow_cloud=` rend la liste unifiée depuis le cache (`tag`, nom, fournisseur, `origin`, `kind`, paramètres totaux et actifs, taille, mémoire nécessaire, `fits`, débit mesuré, outils vérifiés, raisonnement, `default_temperature`, méthode CO₂) (CAP-3).
- FR9 : `GET /api/models/defaults?purpose=chat|arena|judge|agent|rag` rend des tags et la raison de chaque défaut (CAP-3).
- FR10 : Le `model-picker` groupe Local et Cloud (Cloud seulement si autorisé), se filtre au clavier, n'offre aucun modèle d'embedding ni reranker pour générer, affiche la pastille MoE (« MoE 3B actifs ») et la raison du défaut ; un modèle qui ne tient pas reste choisissable avec avertissement ; mode multi pour l'Arène (CAP-3).
- FR11 : Toute génération est un run créé par `POST /api/<module>/runs` qui rend `{run_id}` (et `conversation_id`), suivi par `GET /api/runs/{id}/events`, annulable par `POST /api/runs/{id}/cancel`, avec instantané `GET /api/runs/{id}` (CAP-4).
- FR12 : Quitter un écran pendant une génération puis revenir reprend le flux sans perte ni doublon (`?after=` / `Last-Event-ID`) (CAP-4).
- FR13 : Toute erreur suit `{code, message, action, detail}` en français, codes fermés ; le front affiche message puis action, détail replié (CAP-4).
- FR14 : Un second run racine du même `kind` rend `409 run_busy` avec le `run_id` actif, que le front rejoint (CAP-4).
- FR15 : Au démarrage, chaque run non terminé reçoit un `run_ended {status: "interrupted"}` ; un changement d'`instance_id` est signalé au front (« Le serveur a redémarré… », « Recharger »).

**Étape 2 — Chat (CAP-5, CAP-6)**

- FR16 : Chat libre en flux avec un modèle Ollama, OpenAI/Groq, Anthropic ou Mistral (`POST /api/chat/runs {conversation_id?, model, message, temperature, allow_cloud}`) ; premier token affiché dès réception (CAP-5).
- FR17 : « Arrêter » (bouton ou Échap) coupe en < 1 s et garde le partiel marqué « Arrêté » (CAP-5).
- FR18 : Métriques : débit final = `eval_count / eval_duration` (D3, `tps_source`), débit provisoire marqué pendant le flux, chargement et durée totale à part, TTFT, tokens (CAP-5).
- FR19 : La conversation est persistée, rouvrable (`GET /api/conversations/{id}`), exportable en JSON et Markdown, effaçable (`DELETE`) ; « Effacer » retire le texte du fichier de base (CAP-5).
- FR20 : Le raisonnement (`channel: thought`) est affiché replié ; le modèle choisi est gardé par conversation ; modèle cloud choisi + cloud désactivé = message et meilleur modèle local proposé.
- FR21 : Une réponse locale affiche un CO₂ mesuré par CodeCarbon, propre au run et différent selon le modèle (CAP-6).
- FR22 : Une réponse cloud affiche une estimation ecologits « (estimé) » ou « non mesurable » avec sa raison (ex. Groq sans correspondance), jamais 0 ni « — » nu (CAP-6).
- FR23 : CO₂ de session (`GET /api/carbon/session`, `carbon_updated`) = somme des feuilles de l'`app_session` courante, par module, Local et Cloud, non-mesurables comptés à part ; panneau de la barre haute (CAP-6).

**Étape 3 — Arène (CAP-7)**

- FR24 : `POST /api/arena/runs {models, prompt, judge, criteria, allow_cloud}` lance un run composite (un enfant par modèle et par notation) ; 2 à 4 colonnes en flux, locaux en séquence (sémaphore), cloud en parallèle.
- FR25 : Statuts de lane (`waiting`, `loading`, `generating`, `judging`, `done`, `timeout`, `failed`, `cancelled`) avec texte et icône ; un délai dépassé ou un échec n'arrête pas les autres lanes.
- FR26 : Un juge note chaque réponse (/100) avec raison ; « non évalué » (avec raison) jamais 0 ; défaut juge = plus gros modèle local qui tient, alerte « note peu fiable » sous ~4B actifs.
- FR27 : Classement construit au fil des résultats, matrice qualité/CO₂ (SVG, légende de taille) affichée d'abord et vue tableau derrière « Voir le tableau » (D-14).
- FR28 : Verdict local/cloud chiffré : écart de note, coût pour 1 000 requêtes (table de prix datée de `wavelocalai.toml`), CO₂, données restées sur le poste.
- FR29 : Résultat conservé côté serveur, rouvrable par URL `#/arene/comparer/<run_id>`, liste `GET /api/arena/runs`, export CSV et Markdown avec preuve (fiche machine, version d'Ollama, digests, méthode CO₂, juge).
- FR30 : Scénarios prédéfinis de question (Vulgarisation, Extraction JSON, Résumé, Traduction) et critères de notation repliés.

**Étape 4 — Assistant documentaire (CAP-8, CAP-9)**

- FR31 : Zone de dépôt visible sans aller-retour serveur (PDF, TXT, MD, DOCX) ; `POST /api/rag/documents` (multipart) crée un run `ingest` (CAP-8).
- FR32 : Progression par fichier en deux temps (envoi navigateur, puis `ingest_progress` : `extract`, `split`, `embed`) ; annulation du lot par un seul « Annuler l'import » (D-25) (CAP-8).
- FR33 : Un échec d'ingestion affiche sa raison par fichier et laisse le compteur inchangé ; succès = « N extraits ajoutés depuis M documents » (CAP-8).
- FR34 : Liste des documents (`GET /api/rag/documents`, `status` `indexing`/`ready`/`failed`, un document en échec listé avec sa raison, D-26), suppression d'un document seul après confirmation (D-24) (CAP-8).
- FR35 : « Vider la base documentaire » ouvre `confirm-dialog` annonçant le nombre d'extraits et de documents ; « Annuler » ne supprime rien ; `DELETE /api/rag/base?expected_count=` (CAP-8).
- FR36 : Réglages (`GET`/`PUT /api/rag/settings`) : modèle d'embedding (changer impose « Vider »), stratégie, nombre d'extraits, reranker, en volet replié.
- FR37 : Discussion : `POST /api/rag/runs {conversation_id?, question, model, strategy, allow_cloud}` ; les sources (document, page, extrait entier, passage à surligner désigné par le serveur, rang, libellé de pertinence, score brut en aide) arrivent avant la réponse (CAP-9, D-21).
- FR38 : Stratégies naïve, HyDE et Self-RAG disponibles, chacune avec ses étapes nommées (`retrieval_step`) (CAP-9).
- FR39 : Citations [n] seulement si le back les fournit (`citations`) ; survol ou focus [n] ↔ source mise en évidence ; `GET /api/rag/chunks/{id}` ouvre l'extrait.
- FR40 : Garde-fou mémoire : question gardée, besoin et mémoire libre chiffrés par `hardware/` (vrais avec un modèle déjà chargé), modèle plus petit proposé et « Décharger les modèles inactifs » (CAP-9).
- FR41 : Reranker fastembed optionnel (extra `rerank`) ; absent = RAG sans reranker, l'écran dit pourquoi.
- FR42 : Accueil : cartes Système, Mode, Processeur, Mémoire en direct ; « Démo recommandée » Arène avec modèles prêts ; liens Assistant documentaire (résumé de la base), Agents, Sobriété (CO₂ de session).

**Après le MVP (détaillé par les Epics 5 à 8)**

- FR43 : Sobriété : métriques en direct sans clic arrêtées onglet masqué, historique carbone (sessions closes, D-37), bridage thermique (NVML), remise à zéro de session, équivalence parlante dans le panneau de méthode seulement (D-38) (CAP-10).
- FR44 : Écran `#/modeles` : compatibilité mémoire avant installation (« Installer quand même » si le modèle ne tient pas, D-42), run `pull` chiffré, décharger, supprimer, fiche modèle, « Pourquoi ce débit ? », « Sur d'autres postes » (CAP-10).
- FR45 : Agent seul : étapes en direct dépliables, outils, email validé (D2), garde-fou mémoire ; Équipe séquentielle : schéma SVG, trace par agent, arrêt, rapport ; parité v1 (CAP-11).
- FR46 : Évaluation : fidélité (verdict par affirmation) et pertinence au fil de l'eau, juge indisponible = « non évalué », résultat partiel d'une évaluation arrêtée conservé (D-28) ; Banc d'essai : validité du format, « format imposé », « réponse concise », consigne du scénario dans un bloc replié (D-18) (CAP-12).
- FR47 : Références `#/arene/references` (quatrième onglet de l'Arène) et carte d'Accueil depuis `qb.results/1`, scores en pourcentage « Part de … » (D-5), « Comparer ces modèles » vers l'Arène (D-19) (CAP-13).
- FR48 : Bascule : axe-core partout, RGAA 4.1, 200 % et 320 px, projection réelle, parité page par page, v1 archivée, 2.0.0 publiée (CAP-14).

### NonFunctional Requirements

- NFR1 : Coquille < 300 ms en local ; changement d'écran < 150 ms ; premier rendu < 1 s.
- NFR2 : Aucune route de lecture > 300 ms Ollama arrêté (test de budget) ; sonde Ollama ≤ 1 s, cache 5 s pour les routes de lecture, 1 s pour la sonde du flux système (AD-15 amendé).
- NFR3 : Aucun appel réseau ni import lourd dans le chemin de rendu ni au démarrage (`codecarbon`, `fastembed`, `pypdf`, `docx`, `ecologits`, SDK cloud importés dans la fonction).
- NFR4 : Tout local : écoute `127.0.0.1:8502`, aucune requête navigateur hors de `127.0.0.1` (E2E), aucun CDN, installation par `uv sync` seul, ni Node ni téléchargement à l'exécution.
- NFR5 : Sécurité de l'API locale : `Host` contrôlé, `Origin` étrangère refusée en écriture, aucun CORS, télémétrie FastAPI coupée.
- NFR6 : Python `>=3.11,<3.13` pour tout le dépôt dès le premier lot ; lint `py311` pour `src/wavelocalai/` et `tests/v2/`.
- NFR7 : Fichiers de 600 lignes au plus ; pas d'abstraction sans second cas.
- NFR8 : Accessibilité RGAA 4.1 / WCAG 2.2 AA : axe-core sans violation ni exclusion, clair et sombre, sur chaque écran livré.
- NFR9 : Charte Wavestone (primaire `#451DC7`, icônes Material, aucun emoji dans `static/`), Aptos puis Inter servie localement.
- NFR10 : Textes en français par clés i18n (`static/i18n/fr.json`) ; formats `fr-FR` (Intl).
- NFR11 : Confidentialité : `data/` jamais commitée ; « Effacer » efface réellement (`secure_delete`, `VACUUM`, test d'octets sur `.db` et `-wal`) ; journaux sans texte de prompt, réponse ou document au niveau INFO ; clés d'API masquées.
- NFR12 : Fiabilité des mesures : débit D3 issu d'Ollama seulement ; CO₂ jamais 0 pour un inconnu ; aucune mesure n'interrompt un run ; aucun appel réseau de mesure.
- NFR13 : Tests : `tests/v2/unit` (sans serveur), `tests/v2/web` (TestClient), `tests/v2/e2e` (Playwright, marqueur `e2e`), Ollama réel = `integration` ; base de test en dossier temporaire, jamais `data/`. Les E2E sont exclus par défaut (`pytest.ini`) et donc absents de la CI : chaque story qui en porte les lance en local (`-m e2e`) avant sa PR.
- NFR14 : « Terminé » = code et tests verts vérifiables par l'agent ; recette humaine en fin de lot ; v1 lançable et intacte jusqu'à la bascule.
- NFR15 : Exploitation : un seul serveur par dossier de données (verrou), port occupé = message clair, arrêt propre (runs actifs → `cancelled`), journaux en rotation 5 × 1 Mo dans `data/logs/`, alerte si le dossier est sous OneDrive.

### Additional Requirements

Issus de la spine d'architecture (AD-n) et de la pile technique. **Pas de starter template** : greenfield dans `src/wavelocalai/` selon le Structural Seed, à côté de la v1.

- AR1 (AD-1, AD-2, AD-3) : premier lot = squelette du paquet `src/wavelocalai/`, `requires-python = ">=3.11,<3.13"`, `dev-mode-dirs = [".", "src"]`, installation éditable, lanceur `wavelocalai-v2` (`wavelocalai.__main__:main`) sur 8502, dépendances v2 dans `dependencies`, fastembed dans l'extra `rerank` ; `version = "2.0.0.dev0"` dès ce lot, puis une préversion par epic du MVP : `2.0.0a1` (Epic 1), `a2` (Epic 2), `a3` (Epic 3), `a4` (Epic 4), chacune avec tag `v2.0.0-alpha.N` et release (AD-3).
- AR2 (ratification) : au premier lot, `AGENTS.md` (Python 3.11+, v1 en correctifs seulement, v2 décrite), `requirements.txt` et `constraints.txt` régénérés pour 3.11, Codecov 3.10 → 3.11, CI : job v2 (`setup-uv`, `uv sync --locked`, `pytest tests/v2`, 3.11 et 3.12, trois OS), job v1 sans 3.10.
- AR3 (AD-4) : test AST `tests/v2/unit/test_layers.py` : sens des imports du diagramme, aucun `src.*`, seul `web/` importe fastapi/starlette/uvicorn, imports lourds paresseux.
- AR4 (AD-5) : hub `runs/` seul à attribuer `seq`, publier, persister, annuler, fixer le statut, créer la conversation et écrire `messages` ; runs composites (`parent_run_id`), métriques et CO₂ sur les feuilles seulement ; `hub.finish_leaf(result, co2)`.
- AR5 (AD-6) : trame SSE `id:` + `data:` sans `event:`, enveloppe `{seq, run_id, type, ts, data}`, `seq` contigu dès 1, `run_started` premier, `run_ended` dernier, reprise `Last-Event-ID`/`?after=`, `204` en fin, maintien 15 s, `token` groupé 50 ms par `lane` ; `fastapi.sse.EventSourceResponse` natif.
- AR6 (AD-7) : événements en mémoire pour un run actif, écrits par lots ≤ 1 s, dernier lot + statut + message assistant dans une transaction ; `sources` persisté sans `text`, réhydraté au rejeu ; `runs.params` sans texte saisi.
- AR7 (AD-8) : ports `ChatModel` / `Embedder` (`ChatRequest`, `ChatChunk`, `ChatResult` figés), annulation par tâche asyncio avec `finally`, `ProviderError(code)`, adaptateur Ollama natif `/api/chat` seul `ollama_eval`, embeddings locaux `/api/embed`, adaptateur `fake` seulement si `Settings.testing`.
- AR8 (AD-9) : `registry.resolve(tag, allow_cloud)` et `registry.resolve_embedder(tag)` seuls accès aux modèles ; approbations du hub (étape 6).
- AR9 (AD-10, AD-11) : champ `co2` unique ; `OfflineEmissionsTracker` par feuille locale sous le sémaphore, un seul à la fois, `start`/`stop` dans le pool de threads, test sans socket ; ecologits `llm_impacts(...)` par arguments nommés, jamais `EcoLogits.init()`, correspondance Groq dans `wavelocalai.toml`, test de contrat de signature ; `app_session` par démarrage et remise à zéro ; `carbon_updated` sur `SystemBus`.
- AR4 bis (AD-5) : `kind` de feuille en liste close, figée par la migration du hub : `generation`, `judge`, `embedding` ; une feuille `embedding` est mesurée comme toute feuille locale ; le verdict d'Arène vit dans l'instantané `GET /api/runs/{id}`.
- AR10 (AD-12) : SQLite unique `data/wavelocalai.db`, WAL, `foreign_keys`, `secure_delete`, écrivain unique sur un fil, migrations `NNNN_*.sql` avant seulement avec `.bak-<user_version>`, base plus récente = refus de démarrer, test de schéma par instantané ; **la migration de la story du hub crée `runs`, `run_events`, `conversations`, `messages` et `app_sessions` en entier** ; exception : `store.ensure_vec_table(dim)`.
- AR11 (AD-13) : effacer une conversation/un run supprime `messages`, `run_events`, `evaluations` et garde `runs` sans texte (`conversation_id` NULL) ; document → `chunks` + lignes vec0 par `rowid` dans la même transaction ; « Vider » recrée la table vec0 ; séquence `DELETE`, `wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)` ; `409` si run actif.
- AR12 (AD-14) : client Ollama async partagé, sémaphore local à 1 pris par appel ; un run racine actif par `kind` ; délai de lane depuis l'acquisition du sémaphore (local) ou le départ (cloud) ; travail CPU dans le pool de threads.
- AR13 (AD-15) : `Settings` pydantic chargé une fois depuis `wavelocalai.toml` (`tomllib`) puis `.env`, aucun `os.getenv` hors `config.py` ; table `preferences` pour les réglages d'UI ; l'app n'écrit jamais le `.toml` ; cache de modèles rafraîchi en tâche de fond.
- AR14 (AD-16) : une base = un modèle d'embedding ; `chunks_vec_<dim>` (vec0, `rowid = chunks.id`) ; seuls les documents `ready` interrogés ; `VectorIndex` sqlite-vec + repli numpy ; 409 si `ingest`/`rag` actif au changement d'embedding ou au « Vider ».
- AR15 (AD-17) : aucun téléchargement implicite ; reranker fastembed `local_files_only=True` depuis le `cache_dir` des données.
- AR16 (AD-18) : `errors.py` liste fermée ; chaque story ajoute ses codes ; `detail` est un objet (`technical` replié, plus les clés machine déclarées avec le code) dont les valeurs texte passent par le masquage de clé.
- AR17 (AD-19, AD-21) : `wavelocalai/telemetry.py` copie adaptée, `FASTAPI_OTEL_AUTO_CONFIGURE=false`, `disable_telemetry()` avant fastembed et huggingface_hub, test AST.
- AR18 (AD-20) : front : Custom Elements `wl-` sans Shadow DOM, écrans `mount(host, params)` → `unmount` chargés par `import()`, un seul `core/sse.js` et un seul `core/store.js` (état et dernier `seq` des runs actifs), bascule cloud dans le store seulement, `localStorage` pour thème, projection, volets et brouillons ; aucune mesure calculée côté front hors chronomètre et débit provisoire ; aucune dépendance JS tierce hors `static/vendor/` avec licence.
- AR19 (AD-22) : lecture de `benchmarks/slm-quality/slm-quality-results.json` seulement, schéma `qb.results/1` (étape 5 et CAP-13).
- AR20 (AD-23) : verrou du dossier de données, message de port occupé, arrêt propre, journaux en rotation, CSV v1 non importé.
- AR21 (réutilisation) : copier puis adapter (jamais importer) `model_defaults.py`, `metrics.py`, `_validate_path`, `accelerator.py`, `HardwareMonitor`, `telemetry.py`, streaming des providers cloud, `retry_interrupted`, règle `answer_carbon`, fichiers du harnais (`openai_chat.py`, `anthropic_messages.py`, `greenops.py`, front `wavestack/web`), `hardware.py`/`nvml.py`/`machine_state.py` de l'archive.
- AR22 (versions) : versions de la spine §Stack (FastAPI 0.143.5, uvicorn 0.54.0, pydantic 2.12.x jusqu'à la bascule, ollama 0.6.3, sqlite-vec 0.1.9, ecologits `>=0.11.3,<0.12`, fastembed 0.9.0) ; SDK `openai`, `anthropic`, `mistralai`, `codecarbon`, `pypdf`, `python-docx` revérifiés à la story qui les utilise.
- AR23 (périmètre) : ne modifier ni `scripts/benchmark_slm.py` ni le `src/core/` de la v1 ; rien ne s'ajoute au MVP avant sa livraison.

### UX Design Requirements

- UX-DR1 : `static/tokens.css` miroir des jetons de `DESIGN.md` (couleurs clair/sombre dont `primary #451DC7` / `#7E65E9`, `surface`, `surface-alt`, `ink`, `ink-secondary`, `line`, `link`, `accent-green`, `risk`, `chart-1…4`, rayon 12 px, typographie `metric-value`, `heading`, `caption`, `body`) et un test de dérive qui les compare.
- UX-DR2 : `base.css` : reset, pile Aptos (par `local()`) → Inter servie depuis `static/fonts/` avec licence → `sans-serif`, `:focus-visible` à 3:1, `prefers-reduced-motion`, mode projection (rampe typographique ×9/7, métriques agrandies, pied masqué) ; thème « Clair » par défaut, « Sombre » et « Système » (suit `prefers-color-scheme`) (D-7) ; mode projection en interrupteur (D-6).
- UX-DR3 : sprite `icons.svg` (sous-ensemble des Material Symbols Rounded officiels, avec licence, D-2), icône propre à chaque module, aucun emoji (test sur `static/`).
- UX-DR4 : coquille `index.html` : `lang="fr"`, repères `header`/`nav`/`main`, lien d'évitement « Aller au contenu », routeur par `hash` (`#/`, `#/arene/chat`, `#/arene/comparer[/<run_id>]`, `#/arene/banc[/<run_id>]`, `#/arene/references`, `#/documents`, `#/documents/base`, `#/documents/evaluation[/<run_id>]`, `#/agents/seul`, `#/agents/equipe[/<run_id>]`, `#/sobriete`, `#/modeles[/<tag>]` ; D-8), écran gardé en mémoire après la première visite, `document.title` « <Écran> · WaveLocalAI », focus sur le `h1` et annonce polie à chaque route, un `h1` par écran.
- UX-DR5 : barre haute (FR2) : menu des modules, pastille Ollama avec libellé et panneau, interrupteur « Autoriser le cloud » avec son aide (« Désactivé à chaque ouverture de la page. Activé, les données envoyées aux modèles cloud quittent la machine. »), CO₂ session et son panneau (total, Local/Cloud, non mesurables, lien Sobriété), menu Affichage (thème, projection) ; menu repliable sous 1 024 px ; bandeau « Connexion au serveur perdue, nouvelle tentative… » après 3 essais.
- UX-DR6 : `wl-badge` : Local (vert, `computer`), Cloud (orange, `cloud`), Origine inconnue (gris, `help`), toujours un texte ; étiquettes « indicatif », « un seul juge », « estimé », « non mesurable ».
- UX-DR7 : `wl-metric` : libellé, valeur avec unité en `metric-value`, aide par `<button aria-describedby>`, état « provisoire » en italique.
- UX-DR8 : `wl-run-status` : étape nommée (« Chargement du modèle en mémoire… », « Recherche des extraits… », « Génération… »…), chronomètre local, bouton Arrêter, touche Échap.
- UX-DR9 : `wl-model-picker` : combobox ARIA APG avec listbox, saisie pour filtrer, groupes « Sur cette machine » / « Cloud », ligne par modèle (nom, badge, taille, « tient en mémoire », débit mesuré, pastilles outils/raisonnement/MoE), avertissement si ne tient pas, défaut et raison en aide, mode multi (cases et pastilles retirables) ; tri local d'abord par règle explicite.
- UX-DR10 : `wl-chat-thread` : `role="log"`, tokens ajoutés à un nœud tampon, Markdown rendu au plus toutes les 150 ms et à la fin (`core/markdown.js`), raisonnement replié, pied de réponse (badge, CO₂, débit, chargement, durée), défilement qui suit seulement si l'utilisateur est en bas + « Aller à la fin », annonce `aria-live="polite"` à la fin seulement (« Réponse de … terminée, N tokens. »).
- UX-DR11 : `wl-source-panel` : liste numérotée, document, page, pertinence normalisée (rang + « très proche »/« proche »/« éloignée », score brut en aide), extrait entier avec passage surligné (`passage {start, end}` fourni par le serveur, D-21), « Ouvrir l'extrait », « extrait supprimé » si `text: null` ; à droite ≥ 1 024 px et toujours ouvert, sans repli (D-22), dessous et replié en deçà ; un seul panneau pour plusieurs réponses, « Afficher les sources » par réponse dès la deuxième (D-23).
- UX-DR12 : `wl-confirm-dialog` : `<dialog>` natif, titre en question, conséquence chiffrée, focus sur « Annuler », confirmation soldée par un message au même verbe ; sert à « Vider », à l'email, à « Supprimer » un document (D-24) et un modèle.
- UX-DR13 : `wl-data-table` : `<table>` sémantique, en-têtes `scope`, tri au clavier ; alternative obligatoire à chaque graphique.
- UX-DR14 : `wl-chart-svg` : nuage de points (qualité, débit, CO₂ en taille, légende de taille) en SVG fait main sur `chart-*`, `<title>` et `<desc>`, lien « Voir le tableau », points étiquetés (`chart-4` jamais seul).
- UX-DR15 : `core/format.js` : formats `fr-FR` par `Intl` (virgule, espace fine insécable, ≤ 3 chiffres significatifs), CO₂ mg/g/kg une seule unité par comparaison, Go, durées « 1 min 12 s », dates « 18 oct. 2026 », notes de juge /100, références du banc en pourcentage avec le libellé « Part de … » (D-5), « non évalué »/« inconnu » jamais 0.
- UX-DR16 : affichage d'erreur unique : message, action (boutons d'action quand prévus, déduits du code et de `detail` par le front, D-4), « Détails techniques » replié ; codes `ollama_down`, `no_model`, `model_not_chat`, `ram_guard`, `cloud_not_allowed`, `cloud_unreachable`, `cloud_key_missing`, `timeout`, `generation_interrupted` (code livré par 2.1 : AD-5 interdit un code qui reprend un statut), `not_evaluated`, `ingest_failed`, `run_busy`, puis `run_not_found`, `pull_failed`, `model_in_use` (stories qui les introduisent).
- UX-DR17 : états vides et de chargement d'`EXPERIENCE.md` (base vide, aucun message, moins de 2 modèles, aucun modèle installé, premier chargement lent 8 à 26 s, délai dépassé, évaluation impossible, service indisponible, fournisseur cloud injoignable) ; squelettes dans les cartes, jamais d'écran blanc.
- UX-DR18 : microcopie et lexique d'`EXPERIENCE.md` (Voice and Tone) : casse de phrase, guillemets « », espaces insécables, infinitif + objet sur les boutons, pluriels accordés, noms techniques en aide seulement.
- UX-DR19 : responsive : ≥ 1 440 px Arène 3-4 colonnes et panneaux à droite ; 1 024-1 439 px 2 colonnes visibles et défilement ; 768-1 023 px panneaux dessous repliés, menu ; < 768 px une colonne, Arène en onglets par modèle, saisie collante ; lisible à 200 % et 320 px sans défilement horizontal (hors tableaux larges).
- UX-DR20 : Arène : colonnes à en-têtes collants, mode focus d'une colonne, « Afficher toute la réponse » (dès 1 440 px à 4 modèles, réponse repliée sur 4 lignes, D-15), configuration remplacée par un résumé pendant l'exécution (D-16), bandeau « Comparaison en cours · 2 sur 3 · 0:42 » + Arrêter, classement « Matrice / Tableau » avec la matrice d'abord (D-14), phrase d'exécution (« les modèles locaux passent l'un après l'autre… »), bouton désactivé avec sa raison (« Choisissez au moins 2 modèles », « Choisissez 4 modèles au plus », « Saisissez une question », « Choisissez un juge »), actions Relancer / Modifier la question / Exporter (deux boutons CSV et Markdown, menu « Exporter » sous 768 px, D-3).
- UX-DR21 : Chat libre : saisie Entrée / Maj+Entrée / Échap documentés, curseur « Créativité » (température, défaut = `default_temperature` du modèle, repli 0,2, D-12), « Effacer la conversation » sans confirmation, « Télécharger en JSON » et « Télécharger en Markdown » (menu « Exporter » sous 768 px, D-3), 409 rejoint sans perdre le message tapé (D-13).
- UX-DR22 : Base documentaire : zone de dépôt + « Choisir des fichiers », ligne de progression par fichier (« Envoi 100 % · Découpage · Vectorisation 18/40 extraits »), un seul « Annuler l'import » au-dessus des lignes (D-25), échec avec « Détails techniques », tableau des documents (nom, extraits, date, modèle de représentation, statut dont « Échec » avec sa raison, D-26, Supprimer confirmé par `wl-confirm-dialog`, D-24), ligne de réglages, état vide « Votre base documentaire est vide » + « Importer des documents ».
- UX-DR23 : Discussion : en-tête « N documents · M extraits · Modèle », « Réglages avancés » repliés, étapes du `run-status` par stratégie (« Rédaction d'une réponse hypothétique… », « Vérification de la pertinence… », « Reclassement… »), pied avec « Recherche 0,06 s · Génération 5,8 s ».
- UX-DR24 : Accueil : `h1` « Accueil » (D-9) et accroche, quatre cartes d'état en direct (pause sur `visibilitychange`), carte « Démo recommandée » Arène avec modèles prêts et « Lancer une comparaison » toujours actif (D-11), liens de modules avec nom court en titre, nom long en sous-titre et résumé (D-10), carte Références en pourcentage (D-5, D-8) ; Ollama absent = « Indisponible » + marche à suivre, liens actifs, « Aucun modèle local disponible ».
- UX-DR25 : vérification axe-core en E2E sur chaque écran livré, clair et sombre, zéro violation sans exclusion ; vérification E2E qu'aucune requête ne sort de `127.0.0.1`.

Après le MVP (`03-ux-front.md` §3.4 et §3.5, à préciser par la mise à jour `bmad-ux` d'avant l'Epic 5) :

- UX-DR26 : Sobriété : « Santé du système » en direct (pause onglet masqué), « Empreinte carbone de cette session » (total, par module, Local/Cloud, non-mesurables), historique 7 jours / 30 jours / Tout en barres par session et tableau (sessions closes seulement, D-37 ; tableau par défaut sous 640 px, D-39), carte d'identité et méthode repliées, équivalence parlante seulement dans la méthode avec la source du facteur (D-38).
- UX-DR27 : Modèles : tableau des installés (Usage et Origine repliées sous 1 024 px, D-43) et du catalogue installable (mémoire nécessaire, « tient en mémoire », « Installer quand même » pour un modèle qui ne tient pas, D-42), installer avec progression chiffrée, décharger, supprimer avec confirmation (défaut choisi signalé dans le dialogue, D-41), reranker, fiche modèle (à droite dès 1 120 px, au-dessus de la liste en deçà, D-40), « Pourquoi ce débit ? », « Sur d'autres postes ».
- UX-DR28 : Agents : `wl-step-trace` (liste ordonnée d'étapes dépliables pendant le flux, icône et libellé par type, durée, agent courant ; panneau « Étapes » toujours déplié, D-30), interrupteurs d'outils (D-6 ; email désactivé par défaut, indisponible non activable avec aide), avertissement sans bloquer pour un modèle sans outils vérifiés (D-32), pied de réponse réduit (badge, CO₂, étapes, durée, D-31), validation d'email par `wl-confirm-dialog`, schéma d'équipe en SVG avec agent actif marqué par contour et libellé, « Non lancé » (D-34), journal brut en lignes horaires (D-33), « Configurer » en volet non modal (D-35), 5 agents au plus (D-36), mission rouvrable par `#/agents/equipe/<run_id>` (D-8).
- UX-DR29 : Évaluation et Banc d'essai : étapes nommées, scores /100 et verdicts par affirmation dépliables, « non évalué » avec raison, modèles évalués présélectionnés sur le défaut `arena` (D-27), résultat partiel conservé (D-28), question vide = lancement désactivé avec sa raison (D-29) ; verdict de format en clair, consigne du scénario repliée (D-18), scénario sans format = « Format imposé » désactivé avec raison et sans verdict (D-17), interrupteurs en bascule « Format imposé » et « Réponse concise » avec aide (D-6).

### FR Coverage Map

FR1 à FR5 : Epic 1 - coquille, barre haute, santé, flux système, identité
FR6, FR7 : Epic 1 - cloud contrôlé et badge
FR8 à FR10 : Epic 1 - registre, défauts, `model-picker`
FR11 à FR15 : Epic 1 - hub des runs côté serveur (testé avec l'adaptateur `fake`) ; la reprise E2E dans le navigateur est fermée par la story 2.2
FR16 à FR20 : Epic 2 - chat en flux, arrêt, métriques D3, conversation
FR21 à FR23 : Epic 2 - CO₂ local, cloud et de session
FR24 à FR30 : Epic 3 - Arène, juge, classement, verdict, export
FR31 à FR36 : Epic 4 - base documentaire
FR37 à FR41 : Epic 4 - Discussion, stratégies, citations, garde-fou, reranker
FR42 : Epics 1, 3 et 4 - Accueil livré par morceaux : cartes d'état (Epic 1), « Démo recommandée » (Epic 3), résumé de la base (Epic 4)
FR2, FR6, FR42 (décisions de la maquette D-2, D-6, D-7, D-10) : story de suite 1.12 ; FR8, FR16, FR19 (D-3, D-12) : story de suite 2.7
FR43 : Epic 5 - Sobriété en direct (5.1), historique et remise à zéro (5.2)
FR44 : Epic 5 - écran Modèles : installer (5.3), décharger, supprimer, défauts (5.4), reranker (5.5), fiche modèle (5.6) ; défauts calés sur le banc (5.7)
FR47 : Epic 5 - références par usage (5.8)
FR45 : Epic 6 - boucle d'outils (6.1), outils (6.2), email validé (6.3), Agent seul (6.4), équipe (6.5, 6.6)
FR46 : Epic 7 - fidélité et pertinence (7.1), jeu fixe (7.2), écran Évaluation (7.3), Banc d'essai (7.4)
FR48 : Epic 8 - dette (8.1), accessibilité et projection (8.2), parité et E2E (8.3), bascule et 2.0.0 (8.4)

## Epic List

Décisions de structure (party mode du 2026-10-18) :
- CAP-4 se partage : l'Epic 1 livre le serveur du hub, vérifié par l'adaptateur `fake` ; la story 2.2 ferme le critère E2E de reprise du flux.
- La migration du hub porte dès maintenant tous les statuts et tous les `kind` d'AD-5, post-MVP compris : une migration fusionnée ne change jamais (AD-12).
- Chaque carte de l'Accueil arrive avec son écran. Les modules non livrés restent visibles dans la barre haute, désactivés, avec une raison en texte visible (« Pas encore disponible dans cette préversion ») ; même règle pour les onglets de sous-écran ; registre d'écrans `available` / `planned`.
- Les stories des Epics 5 à 8 sont écrites (2026-10-18) avec les reports du MVP (`reports-v2-inventaire.md`) ; elles se relisent avant chaque étape avec le retour de recette, les décisions Q1 à Q7 d'Anaël (2026-10-18) y sont reportées.
- Préversions après le MVP : `2.0.0a5` (Epic 5), `a6` (Epic 6), `a7` (Epic 7), `2.0.0` à la bascule (Epic 8, AD-3).
- Correct course du 2026-10-19 (`sprint-change-proposal-2026-10-19.md`) : la maquette validée `docs/maquette-v2/` et les décisions D-1 à D-43 d'Anaël sont reportées dans les UX-DR et les critères des stories non livrées ; deux stories de suite, 1.12 et 2.7, appliquent les décisions qui touchent les Epics 1 et 2 déjà livrées. La maquette est la référence visuelle des écrans ; les documents de contrat priment sur elle. Le registre `available` / `planned` reste en place jusqu'à la livraison de chaque écran ; après l'Epic 7, aucun lien « Pas encore disponible » ne subsiste (comme dans la maquette).

### Epic 1 : Une coquille rapide qui montre l'état du poste et protège les données
L'utilisateur ouvre l'app, même Ollama arrêté, voit tout de suite l'état d'Ollama, du processeur et de la mémoire et le CO₂ de session, garde la main sur le cloud et dispose d'un sélecteur de modèle qui dit l'origine et la raison du défaut. Côté serveur, toute exécution est un run annulable et rejouable.
**FRs couverts :** FR1 à FR15, FR42 (cartes d'état)

### Epic 2 : Converser avec un modèle et voir ce que la réponse coûte
L'utilisateur converse en flux avec un modèle local ou cloud (4 fournisseurs), arrête quand il veut, voit le débit D3, le chargement et un CO₂ honnête sur sa méthode, retrouve, exporte ou efface sa conversation.
**FRs couverts :** FR16 à FR23

### Epic 3 : Comparer des modèles côte à côte et conclure chiffres à l'appui
L'utilisateur lance l'Arène sur 2 à 4 modèles : colonnes en flux, notation par un juge, classement, matrice qualité/CO₂, verdict local/cloud chiffré, résultat rouvrable par URL et exportable avec preuve (Flow 1).
**FRs couverts :** FR24 à FR30, FR42 (« Démo recommandée »)

### Epic 4 : Interroger ses propres documents et vérifier la source
L'utilisateur constitue sa base documentaire et l'interroge en naïf, HyDE ou Self-RAG ; les sources arrivent avant la réponse ; le garde-fou mémoire chiffre le besoin (Flow 2).
**FRs couverts :** FR31 à FR41, FR42 (résumé de la base)

### Epic 5 : Suivre sa sobriété et administrer ses modèles (post-MVP)
Découpe des fichiers partagés du front (5.0, décision du 2026-10-19), sobriété en direct, historique carbone, écran `#/modeles`, fiche modèle, références par usage (`qb.results/1`).
**FRs couverts :** FR43, FR44, FR47

### Epic 6 : Confier une tâche à un agent ou à une équipe (post-MVP)
Agent seul avec trace, email validé (D2), équipe séquentielle.
**FRs couverts :** FR45

### Epic 7 : Évaluer la qualité d'une réponse documentaire (post-MVP)
Fidélité et pertinence avec verdict par affirmation, jeu fixe de non-régression, banc de format.
**FRs couverts :** FR46

### Epic 8 : Remplacer la v1 (post-MVP)
Dette technique du MVP soldée, accessibilité complète, parité, v1 archivée, `2.0.0` publiée.
**FRs couverts :** FR48

## Epic 1 : Une coquille rapide qui montre l'état du poste et protège les données

L'utilisateur ouvre l'app, même Ollama arrêté, voit l'état du poste et le CO₂ de session, garde la main sur le cloud et dispose d'un sélecteur de modèle honnête ; le serveur sait créer, diffuser, rejouer et annuler des runs.

### Story 1.1 : Le dépôt accueille la v2 (squelette, Python 3.11, CI, ratification)

As a mainteneur du dépôt,
I want un paquet `src/wavelocalai/` installable à côté de la v1, testé en CI et décrit dans `AGENTS.md`,
So that chaque lot suivant de la v2 se livre en une PR courte sans casser la v1.

**Gouverné par :** AD-1, AD-2, AD-3, AD-4 ; AR1, AR2, AR3, AR22, AR23.

**Acceptance Criteria:**

**Given** le dépôt à jour de `master`
**When** on lance `uv sync`
**Then** `requires-python = ">=3.11,<3.13"`, `[tool.hatch.build] dev-mode-dirs = [".", "src"]` et le script `wavelocalai-v2 = "wavelocalai.__main__:main"` sont dans le `pyproject.toml` unique, `uv.lock` est régénéré, et `import wavelocalai`, `import src.core` et le lanceur v1 `wavelocalai` résolvent tous trois
**And** les versions de FastAPI, uvicorn, pydantic et ollama sont celles de la spine §Stack, vérifiées par installation réelle
**And** `version = "2.0.0.dev0"` dans `pyproject.toml` et `uv.lock` (sans tag), pour que `master` n'annonce plus 1.3.x dès qu'il contient la v2 (AD-3)

**Given** l'arborescence du Structural Seed (paquets vides avec `__init__.py`)
**When** `tests/v2/unit/test_layers.py` s'exécute
**Then** il échoue si un module importe à rebours du diagramme d'AD-4, si un module v2 importe `src.*`, si un module hors `web/` importe `fastapi`, `starlette` ou `uvicorn`, ou si `codecarbon`, `fastembed`, `pypdf`, `docx`, `ecologits`, `openai`, `anthropic` ou `mistralai` est importé au niveau d'un module (vérifié par un module piège dans les tests du test)

**Given** une PR vers `master`
**When** la CI tourne
**Then** un job v2 (`setup-uv`, `uv sync --locked`, `pytest tests/v2`, Python 3.11 et 3.12, trois OS) passe, le job v1 tourne sans 3.10, la condition Codecov vise 3.11
**And** ruff cible `py311` pour `src/wavelocalai/` et `tests/v2/` seulement ; les réglages globaux et `scripts/benchmark_slm.py` ne changent pas

**Given** la PR de la story
**When** on la relit
**Then** `AGENTS.md` dit Python 3.11+, v1 en correctifs seulement, et décrit la v2 (lanceur `wavelocalai-v2`, port 8502, `tests/v2/{unit,web,e2e}`) ; `requirements.txt` et `constraints.txt` sont régénérés pour 3.11
**And** `python -m pytest tests/unit tests/app` (v1) reste vert

### Story 1.2 : Le serveur v2 démarre en local, protégé, et dit son état

As a consultant qui prépare une démo,
I want lancer `wavelocalai-v2` et obtenir un serveur local qui refuse les pages étrangères et dit en moins d'une seconde si Ollama répond,
So that je sais avant la démo si elle peut partir, sans risque qu'un site visité pilote mon poste.

**Gouverné par :** AD-15, AD-18, AD-19, AD-21, AD-23 ; AR13, AR16, AR17, AR20, AR21.

**Acceptance Criteria:**

**Given** `wavelocalai.toml` versionné (hôte Ollama, port, pays et PUE, délais) et un `.env` facultatif
**When** le serveur démarre
**Then** `Settings` (pydantic) est chargé une fois par `tomllib` puis `.env`, et un test AST vérifie qu'aucun `os.getenv` n'existe hors de `config.py`
**And** `wavelocalai/telemetry.py` (copie adaptée de la v1, avec `FASTAPI_OTEL_AUTO_CONFIGURE=false`) est appliqué avant la création de l'app, créée avec `tracing`, `metrics`, `logs`, `operation_spans` et `auto_configure` à `False`

**Given** le serveur lancé
**When** une requête arrive avec un `Host` autre que `127.0.0.1:<port>` ou `localhost:<port>`, ou une écriture avec une `Origin` étrangère
**Then** elle est refusée avec l'enveloppe `{code, message, action, detail}` et aucun en-tête CORS n'est jamais émis ; l'écoute est sur `127.0.0.1:8502` seulement

**Given** `errors.py` avec sa liste fermée initiale (au moins `ollama_down`, `forbidden_host`, `forbidden_origin`, `internal`)
**When** une route lève une erreur, y compris une exception non prévue
**Then** la réponse suit `{code, message, action, detail}` en français ; `detail` est un objet (`technical` plus les clés machine déclarées avec le code dans `errors.py`) dont les valeurs texte passent par le masquage de clé (test avec une fausse clé `sk-…`)

**Given** le test de budget `tests/v2/web/test_read_budget.py`, paramétré sur toutes les routes `GET` de l'app sans paramètre de chemin, hors flux SSE
**When** il s'exécute Ollama injoignable
**Then** chaque route répond en moins de 300 ms, et une route `GET` ajoutée par une story suivante y entre d'elle-même (AD-15)

**Given** Ollama arrêté
**When** on appelle `GET /api/health`
**Then** la réponse arrive en moins de 300 ms (test de budget) avec `version`, `instance_id` (nouveau à chaque démarrage), `ollama {up: false, version: null, latency_ms: null}` et les fournisseurs cloud `{id, configured}` lus depuis `Settings`, sans les appeler
**And** la sonde Ollama a un délai de 1 s au plus et son état reste en cache 5 s

**Given** un serveur déjà lancé sur le même dossier de données, ou le port occupé
**When** on relance `wavelocalai-v2`
**Then** le second refuse de démarrer avec un message clair (verrou dans le dossier de données ; « port 8502 occupé »)
**And** les journaux vont en rotation 5 × 1 Mo dans `data/logs/` ; une alerte est journalisée si le dossier de données est sous OneDrive ; les tests utilisent un dossier temporaire, jamais `data/`

### Story 1.3 : Le hub enregistre chaque exécution (store SQLite, migration du hub, cycle de vie)

As a utilisateur de l'app,
I want que chaque génération soit un run enregistré, numéroté et terminé proprement même après un redémarrage,
So that aucun résultat ne se perd et qu'un serveur relancé dit honnêtement ce qui a été interrompu.

**Gouverné par :** AD-5, AD-7, AD-10 (`app_sessions`), AD-12, AD-23 ; AR4, AR6, AR10.

**Acceptance Criteria:**

**Given** une base absente
**When** le serveur démarre
**Then** `store/db.py` ouvre `data/wavelocalai.db` (dossier configurable) en `journal_mode=WAL`, `foreign_keys=ON`, `secure_delete=ON`, avec **un seul écrivain** qui sérialise les écritures sur un fil, et les lectures sur connexions courtes
**And** la migration `store/migrations/0001_hub.sql` crée **en entier** `runs`, `run_events`, `conversations`, `messages` et `app_sessions`, `PRAGMA user_version` vaut 1

**Given** la migration `0001_hub.sql`
**When** on relit son schéma
**Then** `runs.status` admet exactement `running`, `awaiting_approval`, `ok`, `error`, `cancelled`, `interrupted` ; `runs.kind` admet les racines `chat`, `arena`, `rag`, `agent`, `ingest`, `pull`, `eval`, `bench` et les feuilles `generation`, `judge` et `embedding` (un run enfant par appel de modèle, liste close d'AD-5 : aucune autre valeur ne pourra s'ajouter sans migration) ; `runs` porte `parent_run_id`, `app_session`, `conversation_id` (nullable), modèle, début, fin, jetons entrée/sortie, TTFT, débit, `tps_source`, `energy_wh`, les colonnes du `co2` d'AD-10 et `params` ; `conversations.kind` admet `chat`, `rag`, `agent` ; `messages` porte rôle, contenu, raisonnement, appels d'outils, `run_id`
**And** un test applique toutes les migrations sur une base vide et compare le schéma à un instantané versionné

**Given** une base existante à `user_version` N et une migration N+1
**When** le serveur démarre
**Then** une copie `wavelocalai.db.bak-N` est faite avant la migration, appliquée dans une transaction
**And** une base dont `user_version` dépasse celle du code fait refuser le démarrage avec un message

**Given** le hub `runs/`
**When** un service crée un run, publie des événements puis appelle `hub.finish_leaf(result, co2)`
**Then** le hub seul attribue `seq` (contigu dès 1, `run_started` premier, `run_ended` dernier et unique), garde les événements en mémoire, les écrit dans `run_events` par lots d'au plus 1 s, et écrit le dernier lot, le statut final et le message assistant dans une seule transaction
**And** si le run ouvre une conversation, le hub la crée et écrit le message utilisateur à la création du run ; `runs.params` ne contient aucun texte saisi (test)

**Given** un run composite avec deux enfants
**When** on annule le parent
**Then** les enfants passent à `cancelled`, le parent aussi ; métriques et `co2` ne sont écrits que sur les feuilles

**Given** des runs `running` en base au démarrage
**When** le serveur démarre
**Then** chacun reçoit un `run_ended {status: "interrupted"}` synthétique, une nouvelle `app_session` est ouverte, et à l'arrêt propre les runs actifs passent à `cancelled`
**And** les tests du hub utilisent un producteur de test dans `tests/v2/`, sans dépendre d'aucun adaptateur de modèle

### Story 1.4 : Suivre, reprendre et annuler un run en flux (SSE)

As a utilisateur qui change d'écran pendant une génération,
I want que le flux d'un run reprenne exactement où je l'ai laissé et que « Arrêter » agisse aussitôt,
So that je ne perds ni ne vois en double aucun morceau de réponse.

**Gouverné par :** AD-5, AD-6, AD-7, AD-8 (adaptateur `fake`), AD-14, AD-18 ; AR5, AR7, AR12.

**Acceptance Criteria:**

**Given** le port `ChatModel` (`models/port.py`, types `ChatRequest`, `ChatChunk`, `ChatResult` d'AD-8) et l'adaptateur `models/fake.py` scriptable, enregistré seulement si `Settings.testing` est vrai
**When** un run de test produit des `TextDelta` via le `fake`
**Then** `GET /api/runs/{id}/events` émet des trames `id: <seq>` puis `data: {seq, run_id, type, ts, data}` sans champ `event:`, `ts` en ISO 8601 UTC avec `Z`, avec `fastapi.sse.EventSourceResponse` natif
**And** les `token` sont groupés par tranches d'au plus 50 ms et portent `lane`
**And** une commande de test `POST /api/test/runs` (enregistrée seulement si `Settings.testing`) lance un run scripté du `fake`, pour les tests E2E des composants avant le premier écran qui génère

**Given** un run actif ou terminé
**When** le client se reconnecte avec `Last-Event-ID: 7` ou `?after=7`
**Then** il reçoit les événements à partir de `seq` 8, depuis la mémoire du hub si le run est actif, depuis la base sinon, sans trou ni doublon (test de rejeu à cheval sur un lot persisté)
**And** un curseur au dernier `seq` d'un run terminé rend `204` ; un commentaire de maintien part toutes les 15 s

**Given** un run actif
**When** on appelle `POST /api/runs/{id}/cancel`
**Then** la tâche asyncio est annulée, l'adaptateur ferme son flux dans un `finally`, `run_ended {status: "cancelled"}` part en moins d'une seconde et le partiel est conservé
**And** `GET /api/runs/{id}` rend l'instantané (statut, métriques, erreur éventuelle)

**Given** un run racine actif de `kind` X
**When** on en demande un second du même `kind`
**Then** la réponse est `409 run_busy` avec le `run_id` actif dans `detail.run_id`

**Given** un run qui échoue sur une `ProviderError(code)`
**When** il se termine
**Then** `run_ended.data.error` suit `{code, message, action, detail}` et aucun code d'erreur ne reprend un nom de statut

### Story 1.5 : Le registre dit quels modèles sont disponibles, d'où ils viennent et s'ils tiennent en mémoire

As a consultant,
I want une liste unique de modèles, locaux et cloud, qui dit leur origine, leur type et s'ils tiennent sur mon poste, et qui refuse le cloud tant que je ne l'ai pas autorisé,
So that je choisis vite et que mes données ne quittent jamais la machine sans mon accord.

**Gouverné par :** AD-8, AD-9, AD-12, AD-15 ; AR8, AR13, AR21.

**Acceptance Criteria:**

**Given** Ollama démarré avec des modèles de conversation, un modèle d'embedding et un reranker installés
**When** on appelle `GET /api/models`
**Then** chaque entrée porte `tag`, nom, fournisseur, `origin` (`local`, `cloud`, `unknown`), `kind` (`chat`, `embedding`, `reranker`, règle d'`is_embedding_model` de la PR #30 recopiée), paramètres totaux et actifs (MoE), taille, mémoire nécessaire et `fits` calculés par `hardware/` (créé dans cette story : mémoire libre par psutil et estimation du besoin ; fiche machine et NVML en 1.7), outils vérifiés et raisonnement
**And** chaque entrée porte aussi le débit mesuré sur ce poste (médiane du `tps` des feuilles `ok` en `ollama_eval` de `runs` pour ce tag, absent sans run), la précision (`null` jusqu'à l'étape 5, qui la lira dans `qb.results/1`) et la méthode CO₂ disponible (`codecarbon` en local, `ecologits` pour un fournisseur direct ou un modèle Groq de la table de correspondance, `unmeasurable` sinon), sans importer ecologits (AD-15)
**And** les données de `/api/show` sont mises en cache dans la table `model_facts` par `(tag, digest)`, créée par la migration `0002_model_facts.sql` ; le catalogue versionné est `config/models_catalog.json`, en lecture seule

**Given** Ollama arrêté
**When** on appelle `GET /api/models`
**Then** la réponse vient du cache (dernière liste connue, `model_facts`, catalogue versionné) en moins de 300 ms (test de budget), le rafraîchissement se faisant en tâche de fond

**Given** des clés cloud configurées dans `.env`
**When** on appelle `GET /api/models` sans `allow_cloud`, puis avec `allow_cloud=true`
**Then** aucun modèle cloud n'apparaît dans le premier cas ; dans le second, ils apparaissent avec `origin: "cloud"` et id `fournisseur/modèle`

**Given** `registry.resolve(tag, allow_cloud)`, seul accès à un modèle
**When** on résout un modèle `origin != "local"` avec `allow_cloud` absent ou faux
**Then** il lève `cloud_not_allowed` (test d'API sur une commande factice), et résoudre un modèle `kind != "chat"` pour générer lève `model_not_chat`

### Story 1.6 : Chaque usage a un modèle par défaut, avec sa raison

As a consultant qui n'a rien réglé,
I want que l'app propose pour chaque usage un modèle par défaut qui marche, et me dise pourquoi,
So that la démo part sans configuration et que je peux expliquer le choix.

**Gouverné par :** AD-9, AD-15 ; AR13, AR21.

**Acceptance Criteria:**

**Given** les règles de `src/core/model_defaults.py` copiées puis adaptées dans `models/` (catalogue injecté, sans `config` ni `models_db`, jamais importées)
**When** on appelle `GET /api/models/defaults?purpose=chat|arena|judge|agent|rag`
**Then** chaque réponse rend des tags et une **raison** en français (ex. « Le plus rapide des modèles locaux qui tiennent en mémoire »), `arena` rend au moins 2 modèles quand ils tiennent, `judge` le plus gros modèle local qui tient
**And** un défaut n'est jamais un modèle cloud si le cloud n'est pas autorisé, ni un modèle d'embedding ou de reranker

**Given** aucun modèle de conversation installé
**When** on demande un défaut
**Then** la réponse porte le code `no_model` avec son message et son action

**Given** une préférence de défaut choisie par l'UI
**When** elle existe dans la table `preferences` (migration `0003_preferences.sql`)
**Then** elle prime sur la règle pour ce seul usage ; l'app n'écrit jamais `wavelocalai.toml`

### Story 1.7 : Le système publie son état en direct et la session carbone existe

As a consultant devant une salle,
I want voir en direct l'état d'Ollama, le processeur, la mémoire, les modèles chargés et le CO₂ de la session,
So that je sais à tout moment si le poste est prêt, sans cliquer.

**Gouverné par :** AD-6, AD-10, AD-15 ; AR9, AR21.

**Acceptance Criteria:**

**Given** le serveur lancé
**When** un client ouvre `GET /api/system/stream`
**Then** il reçoit toutes les 2 s une enveloppe d'AD-6 avec `run_id: null`, sans `id:` ni rejeu, portant l'état d'Ollama, CPU %, mémoire utilisée et totale, modèles chargés et leur mémoire (`/api/ps`) et `runs_active = [{run_id, kind, status}]`
**And** le port `SystemBus` défini dans `runs/` permet à tout service de publier un événement système (ex. `carbon_updated`) qui part sur ce flux

**Given** `hardware/` (copie adaptée de `accelerator.py`, `HardwareMonitor` et de `hardware.py`, `nvml.py`, `machine_state.py` de l'archive)
**When** on appelle `GET /api/system/identity`
**Then** la fiche machine (OS, processeur, mémoire, accélérateur, version d'Ollama) est rendue sans appel réseau

**Given** une `app_session` ouverte au démarrage
**When** on appelle `GET /api/carbon/session`
**Then** la réponse rend la somme des `co2.mg` des runs feuilles de la session courante, par module, Local et Cloud, et le nombre de non-mesurables à part ; sans aucun run, total 0 mg et 0 non-mesurable
**And** les runs parents ne sont jamais comptés (test avec un run composite)

### Story 1.8 : La coquille s'affiche tout de suite, aux couleurs de Wavestone

As a consultant qui ouvre l'app devant un client,
I want une coquille qui s'affiche en moins de 300 ms, avec la navigation des modules, même si Ollama est arrêté,
So that la première impression est celle d'un outil fini et rapide.

**Gouverné par :** AD-4, AD-19, AD-20, AD-21 ; AR18 ; UX-DR1 à UX-DR4, UX-DR18, UX-DR19, UX-DR25.

**Acceptance Criteria:**

**Given** `web/static/` (index.html, `tokens.css`, `base.css`, `components.css`, `icons.svg`, `fonts/` Inter avec licence, `i18n/fr.json`, `core/router.js`, `core/i18n.js`, `core/theme.js`)
**When** on ouvre `http://127.0.0.1:8502/`
**Then** la coquille (`lang="fr"`, `header`/`nav`/`main`, lien « Aller au contenu ») s'affiche en moins de 300 ms sans aucun appel à `/api/` nécessaire à son rendu (test E2E Ollama arrêté)
**And** aucune requête du navigateur ne sort de `127.0.0.1` (E2E), aucun CDN, aucune dépendance JS tierce hors `static/vendor/`

**Given** le registre d'écrans du routeur, chaque écran `available` ou `planned`
**When** la barre haute s'affiche
**Then** les six modules (Accueil, Arène, Documents, Agents, Sobriété, Modèles) sont visibles ; ceux en `planned` sont un `<a>` sans `href`, `aria-disabled="true"`, focalisable, avec le texte visible « Pas encore disponible dans cette préversion » (clé i18n) ; une route `planned` tapée à la main renvoie à l'Accueil
**And** à chaque route, `document.title` vaut « <Écran> · WaveLocalAI », le focus va sur le `h1` et un changement d'écran prend moins de 150 ms ; sous 1 024 px, les liens passent dans un menu repliable

**Given** `tokens.css` et les jetons de `DESIGN.md`
**When** le test de dérive s'exécute
**Then** il échoue si une valeur de couleur, de rayon ou de typographie diffère entre les deux
**And** un test échoue si un emoji apparaît dans `static/`

**Given** le menu Affichage
**When** on choisit le thème sombre ou le mode projection
**Then** le choix s'applique sans rechargement, est mémorisé dans `localStorage` (seul usage avec volets et brouillons), et la police suit la pile Aptos (`local()`) → Inter locale → `sans-serif`
**And** axe-core ne relève aucune violation sur la coquille, en clair et en sombre, sans exclusion ; la coquille reste lisible à 320 px CSS sans défilement horizontal

### Story 1.9 : La barre haute dit l'état d'Ollama, du cloud et du CO₂, en direct

As a consultant,
I want une barre haute qui me dit si Ollama répond, si le cloud est autorisé et combien la session a émis,
So that je contrôle la souveraineté de la démo d'un coup d'œil, depuis n'importe quel écran.

**Gouverné par :** AD-6, AD-9, AD-18, AD-20 ; AR18 ; UX-DR5, UX-DR6, UX-DR7, UX-DR15, UX-DR16.

**Acceptance Criteria:**

**Given** `core/api.js`, `core/sse.js` (client unique) et `core/store.js` (store observable unique)
**When** la coquille est montée
**Then** le client SSE s'abonne à `/api/system/stream`, aiguille par `type`, ignore un type inconnu, écarte tout `seq` déjà vu sur un flux de run et ferme à `run_ended`
**And** après 3 échecs de connexion, la barre haute affiche « Connexion au serveur perdue, nouvelle tentative… » ; un `instance_id` qui change affiche « Le serveur a redémarré. Les exécutions en cours sont perdues. » avec « Recharger »

**Given** Ollama arrêté puis démarré
**When** la barre haute se met à jour
**Then** la pastille passe de « Ollama ne répond pas » à « Ollama disponible » (libellé, jamais la couleur seule) en moins de 3 s après le changement, et un clic ouvre un panneau : version, modèles chargés, mémoire, « Réessayer »

**Given** l'interrupteur « Autoriser le cloud » avec son aide (« Désactivé à chaque ouverture de la page. Activé, les données envoyées aux modèles cloud quittent la machine. »)
**When** on l'active, change d'écran, puis recharge la page
**Then** l'état est conservé entre écrans (store seul), et revient à désactivé au rechargement (E2E) ; il n'est jamais écrit dans `localStorage`

**Given** le panneau « CO₂ session »
**When** on l'ouvre
**Then** il affiche total, part Local et Cloud, nombre de réponses non mesurables, au format `fr-FR` de `core/format.js` (mg sous 1 g, espace insécable), et se met à jour sur `carbon_updated`

**Given** les composants `wl-badge` (Local `computer` vert, Cloud `cloud` orange, Origine inconnue `help` gris, étiquettes « indicatif », « un seul juge », « estimé », « non mesurable ») et `wl-metric` (valeur et unité, aide par bouton `aria-describedby`, état « provisoire » en italique)
**When** on les monte sur une page d'essai des tests E2E (`tests/v2/e2e/fixtures/`, non servie en production)
**Then** chaque badge porte un texte, axe-core ne relève aucune violation, et un composant d'erreur affiche `message` puis `action`, avec `detail` replié sous « Détails techniques »

### Story 1.10 : Choisir un modèle au clavier, et suivre l'étape d'un run

As a consultant,
I want un sélecteur de modèle filtrable au clavier qui groupe Local et Cloud et dit pourquoi un modèle est proposé, et un indicateur d'étape avec Arrêter,
So that les écrans de chat, d'Arène et de documents réutiliseront les mêmes gestes.

**Gouverné par :** AD-8, AD-9, AD-15, AD-20 ; AR18 ; UX-DR8, UX-DR9.

**Acceptance Criteria:**

**Given** `wl-model-picker` alimenté par `/api/models` et `/api/models/defaults`
**When** on tape « qwen » au clavier
**Then** la liste se filtre selon le motif WAI-ARIA « combobox with listbox popup » ; les groupes « Sur cette machine » puis « Cloud » (ce dernier seulement si le cloud est autorisé) sont triés local d'abord par règle explicite ; aucun modèle d'embedding ni reranker n'est proposé
**And** chaque ligne montre nom, badge, taille, « tient en mémoire » ou un avertissement (le modèle reste choisissable), débit mesuré s'il existe, pastilles « outils vérifiés », « raisonnement » et « MoE 3B actifs » ; le défaut porte sa raison en aide

**Given** le mode multi du sélecteur
**When** on coche trois modèles puis en retire un
**Then** les choix apparaissent en pastilles retirables, un même modèle ne figure qu'une fois, et le composant expose la liste choisie

**Given** le cloud désactivé alors qu'un modèle cloud était choisi
**When** l'état du store change
**Then** le sélecteur retire le modèle, le dit en texte et propose le défaut local

**Given** `wl-run-status` relié à un run du `fake`
**When** le run publie `model_loading`, puis des `token`, puis `run_ended`
**Then** il affiche « Chargement du modèle en mémoire… », puis « Génération… », un chronomètre local, un bouton Arrêter (et la touche Échap) qui appelle `POST /api/runs/{id}/cancel`
**And** les deux composants sont vérifiés en E2E sur la page d'essai des tests, avec axe-core sans violation, au clavier seul

### Story 1.11 : L'Accueil dit en 5 secondes si la démo peut partir

As a consultant qui arrive en salle,
I want un Accueil qui montre l'état du système, le mode, le processeur et la mémoire en direct,
So that je sais en 5 secondes si la démo peut partir, et quoi faire sinon.

**Gouverné par :** AD-6, AD-15, AD-20 ; UX-DR17, UX-DR18, UX-DR24.

**Acceptance Criteria:**

**Given** l'écran `screens/home.js` (`mount(host, params)` qui rend `unmount`, chargé par `import()`)
**When** on ouvre `#/`
**Then** le titre et l'accroche s'affichent, puis quatre cartes (Système, Mode, Processeur, Mémoire) se remplissent depuis le flux système, avec un squelette pendant le chargement, jamais d'écran blanc

**Given** Ollama arrêté
**When** l'Accueil est affiché
**Then** la carte Système dit « Indisponible » et « Démarrez Ollama, puis cliquez sur Réessayer », et les liens restent actifs

**Given** l'onglet du navigateur masqué
**When** `visibilitychange` signale le masquage
**Then** les cartes cessent de se mettre à jour et reprennent au retour

**Given** les modules encore `planned`
**When** l'Accueil liste les modules
**Then** il n'affiche aucune carte qui mène à un écran absent (les cartes « Démo recommandée » et « Assistant documentaire » arrivent avec les Epics 3 et 4)
**And** axe-core ne relève aucune violation sur l'Accueil, en clair et en sombre ; un `h1` unique ; formats `fr-FR`

**Given** l'Epic 1 terminé et la suite `tests/v2` verte
**When** on publie
**Then** `version = "2.0.0a1"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.1`, release GitHub avec notes ; la recette humaine ouvre la coquille Ollama arrêté puis démarré

### Story 1.12 : La coquille et l'Accueil suivent la maquette validée (suite, correct course)

As a consultant qui présente la v2,
I want une coquille et un Accueil conformes à la maquette validée : thème qui suit le système, interrupteurs en bascule, icônes officielles, modules nommés comme dans le menu,
So that la v2 livrée ressemble à ce qui a été validé et que les écrans suivants s'y branchent sans retouche.

**Gouverné par :** AD-20 ; AR18 ; UX-DR2, UX-DR3, UX-DR4, UX-DR24, UX-DR25 ; décisions D-2, D-6, D-7, D-8, D-9, D-10 (`sprint-change-proposal-2026-10-19.md`). **Dépend de :** `master` (Epics 1 et 2 fusionnées) ; à fusionner avant 3.6 et 4.9, qui ajoutent des cartes à l'Accueil. Pas de version propre : elle part dans la préversion suivante.

**Acceptance Criteria:**

**Given** le menu Affichage
**When** on choisit « Système »
**Then** le thème appliqué suit `prefers-color-scheme`, y compris quand le réglage du système change pendant que la page est ouverte ; « Clair » reste le défaut ; le choix est gardé dans `localStorage` (E2E avec émulation du schéma de couleurs)
**And** axe-core ne relève aucune violation sur la coquille et l'Accueil en « Système » clair et sombre

**Given** le menu Affichage et la barre haute
**When** on les affiche
**Then** « Mode projection » est un interrupteur en bascule (`<input type="checkbox" role="switch">`, rendu `wl-switch` de `DESIGN.md`), comme « Autoriser le cloud », qui adopte le même rendu ; l'état se lit dans le libellé et la forme, jamais par la seule couleur (D-6)

**Given** le sprite `icons.svg`
**When** le test des icônes s'exécute
**Then** chaque symbole utilisé par le front existe dans le sprite et provient des Material Symbols Rounded officiels, provenance et licence notées dans `icons.LICENSE.txt` ; aucun tracé Material Icons (Filled) n'y entre (D-2)

**Given** l'Accueil
**When** il liste les modules disponibles
**Then** chaque lien porte le nom court du menu en titre (« Documents »), le nom long en sous-titre (« Assistant documentaire ») et sa phrase de résumé ; le `h1` reste « Accueil » (D-9, D-10 ; test E2E)

**Given** le registre d'écrans du routeur
**When** on y déclare les routes de la maquette
**Then** `#/arene/references`, `#/arene/banc/<run_id>`, `#/documents/evaluation/<run_id>`, `#/agents/equipe/<run_id>` et `#/modeles/<tag>` existent en `planned` (D-8), sans écran ni lien actif, et une route `planned` tapée à la main renvoie toujours à l'Accueil ; la story qui livre l'écran n'a plus qu'à la passer à `available`
**And** axe-core sans violation, clair et sombre, projection comprise ; 320 px sans défilement horizontal

## Epic 2 : Converser avec un modèle et voir ce que la réponse coûte

L'utilisateur converse en flux avec un modèle local ou cloud, arrête quand il veut, voit le débit D3, le chargement et un CO₂ honnête sur sa méthode, retrouve, exporte ou efface sa conversation. Premier vrai consommateur du hub ; se termine par la préversion `2.0.0a2`.

### Story 2.1 : Converser en flux avec un modèle Ollama (serveur)

As a consultant,
I want envoyer un message à un modèle local et recevoir sa réponse token par token avec un débit fidèle à Ollama,
So that la démo montre la vraie vitesse du poste, comparable au banc.

**Gouverné par :** AD-5, AD-6, AD-8, AD-9, AD-14 ; AR4, AR7, AR8, AR12, AR21.

**Acceptance Criteria:**

**Given** l'adaptateur `models/ollama.py` sur `/api/chat` natif, avec un client async partagé
**When** il diffuse une réponse
**Then** il émet `LoadState("loading"|"loaded", duration_s)`, des `TextDelta` (`channel` `answer` ou `thought`) puis un seul `Done(ChatResult)` dont `tps = eval_count / eval_duration` et `tps_source = "ollama_eval"` (D3), avec `load_s`, `ttft_s`, `eval_s`, `total_s` et jetons entrée/sortie (logique de `src/core/metrics.py` copiée, débit de génération et prefill séparés)
**And** une annulation de la tâche ferme le flux HTTP dans un `finally` ; un refus d'Ollama lève `ProviderError(code)`

**Given** `POST /api/chat/runs {conversation_id?, model, message, temperature, allow_cloud}`
**When** on l'appelle sans `conversation_id`
**Then** la réponse rend `{run_id, conversation_id}` aussitôt ; le hub crée la conversation `chat` et le message utilisateur ; le service `inference/chat` obtient le modèle par `registry.resolve(tag, allow_cloud)` seulement
**And** le flux publie `run_started`, `model_loading` / `model_loaded`, des `token` (`lane` = tag), `metrics` (`ttft_s`, `load_s`, `eval_tokens`, `eval_s`, `tps`, `tps_source`, `total_s`, origine) puis `run_ended`, et le hub écrit le message assistant avec le statut final

**Given** le sémaphore « Ollama local » à 1
**When** deux appels locaux arrivent
**Then** le second attend l'acquisition, prise par appel et non par run (test avec le `fake` et un faux client Ollama)

**Given** Ollama qui coupe la génération avant la fin
**When** l'adaptateur le détecte
**Then** le service relance une fois (événement `retry` avec la raison, logique de `retry_interrupted` copiée) puis termine en `error` avec le code `generation_interrupted` (nom du code livré)
**And** Ollama arrêté donne `ollama_down` ; un délai dépassé donne `timeout` avec le délai de `Settings` ; un test `integration` vérifie le flux réel sur `qwen2.5:1.5b`

### Story 2.2 : L'écran Chat libre affiche la réponse en flux et la reprend au retour

As a consultant,
I want un écran de chat qui affiche le premier token dès réception, s'arrête en moins d'une seconde et reprend le flux si je change d'écran,
So that la conversation reste fluide et rien ne se perd pendant la démo.

**Gouverné par :** AD-6, AD-20 ; AR18 ; UX-DR7, UX-DR8, UX-DR10, UX-DR15, UX-DR17, UX-DR21. **Ferme le critère E2E de reprise de CAP-4** laissé ouvert par l'Epic 1.

**Acceptance Criteria:**

**Given** l'écran `screens/chat.js` sur `#/arene/chat` (module Arène passé à `available`, onglets « Arène » et « Banc d'essai » désactivés avec leur raison)
**When** on l'ouvre
**Then** il monte `wl-model-picker` sur le défaut `chat` avec sa raison, un curseur « Créativité » (température), le champ « Écrivez votre message » et l'aide « Entrée : envoyer · Maj+Entrée : nouvelle ligne · Échap : arrêter »

**Given** une question envoyée
**When** les `token` arrivent
**Then** `wl-chat-thread` (`role="log"`) les ajoute à un nœud tampon dès réception et rend le Markdown (`core/markdown.js`) au plus toutes les 150 ms et à la fin ; le raisonnement (`thought`) est replié ; le défilement suit seulement si l'utilisateur est en bas, sinon « Aller à la fin » apparaît
**And** rien n'est annoncé pendant le flux ; à la fin, une région `aria-live="polite"` annonce « Réponse de <modèle> terminée, N tokens. »

**Given** une génération en cours
**When** on observe le pied de réponse
**Then** il affiche le badge, « Débit N tokens/s (provisoire) » en italique calculé par le client, la durée et les tokens ; à `metrics`, il devient définitif : débit serveur (D3, définition en aide), « Chargement x s » et « Durée totale y s » à part

**Given** une génération en cours
**When** on clique Arrêter ou appuie sur Échap
**Then** le flux s'arrête en moins d'une seconde, le partiel reste affiché et marqué « Arrêté »

**Given** une génération en cours
**When** on va sur l'Accueil puis revient sur `#/arene/chat`
**Then** l'écran reprend le flux par `?after=<dernier seq>`, sans perte ni doublon, et la génération n'a pas été interrompue (E2E avec le `fake`)
**And** un `409 run_busy` rejoint le run actif au lieu d'afficher une erreur ; axe-core sans violation, clair et sombre

### Story 2.3 : Chaque réponse locale affiche son CO₂ mesuré

As a consultant,
I want que chaque réponse locale affiche un CO₂ réellement mesuré, différent d'un modèle à l'autre,
So that je montre une sobriété chiffrée et non une constante.

**Gouverné par :** AD-10, AD-11, AD-14 ; AR9.

**Acceptance Criteria:**

**Given** le service `greenops/` (modèle de `wavestack/greenops.py`, `codecarbon` importé dans la fonction, version revérifiée)
**When** une feuille locale s'exécute
**Then** un `OfflineEmissionsTracker` (pays et PUE de `Settings`) est démarré et arrêté sous le sémaphore Ollama, un seul à la fois, `start`/`stop` dans le pool de threads, et la feuille se termine par `hub.finish_leaf(result, co2)` avec `co2 = {mg, method: "codecarbon", estimated: false, range_mg: null, allocation: "direct", reason: null}` et `energy_wh`
**And** un test sans socket (réseau coupé) vérifie qu'aucun appel réseau n'est fait

**Given** une erreur de CodeCarbon
**When** la mesure échoue
**Then** le run se termine normalement avec `co2 = {mg: null, method: "unmeasurable", reason: "<raison>"}` ; aucune mesure n'interrompt un run

**Given** deux réponses de deux modèles locaux de tailles différentes (test `integration`)
**When** on compare leurs `co2.mg`
**Then** les valeurs diffèrent et aucune n'est la constante de la v1 (0,19 mg/token)

**Given** une feuille terminée
**When** `greenops` a écrit son `co2`
**Then** il publie `carbon_updated` sur le `SystemBus`, le panneau CO₂ de la barre haute se met à jour, et le pied de réponse du chat affiche « CO₂ 1,8 mg » (format `fr-FR`, jamais de couleur par seuil)

### Story 2.4 : Converser avec un modèle cloud (OpenAI, Groq, Anthropic, Mistral)

As a consultant qui a autorisé le cloud,
I want converser avec un modèle OpenAI, Groq, Anthropic ou Mistral dans le même écran, avec des erreurs qui nomment le fournisseur,
So that je compare honnêtement local et cloud devant le client.

**Gouverné par :** AD-8, AD-9, AD-14, AD-18 ; AR7, AR8, AR16, AR21, AR22.

**Acceptance Criteria:**

**Given** les adaptateurs `models/openai_compat.py` (OpenAI, Groq), `models/anthropic.py` et `models/mistral.py` sur les SDK officiels (versions revérifiées, SDK importés dans la fonction), repris du streaming des `providers/` v1 et du harnais sans `get_langchain_model`
**When** ils diffusent une réponse
**Then** ils émettent `TextDelta` puis un seul `Done` avec `tps_source = "wallclock"` ; ils ne calculent pas de CO₂, n'écrivent pas en base et ne lisent pas `allow_cloud`

**Given** `allow_cloud: true` et un modèle cloud
**When** on lance un run de chat
**Then** l'appel part sans prendre le sémaphore local, et le badge Cloud accompagne la réponse

**Given** une clé absente, une clé refusée ou un fournisseur injoignable
**When** le run échoue
**Then** l'erreur porte `cloud_key_missing` (où configurer la clé dans `.env`), `cloud_unreachable` (nomme le fournisseur, propose de repasser en Local) ou le code de refus, et aucune clé n'apparaît dans `detail` ni dans les journaux (test)

**Given** `allow_cloud` absent ou faux
**When** on demande un modèle cloud
**Then** la commande rend `cloud_not_allowed` sans appeler le fournisseur (test d'API pour chacun des 4 fournisseurs)
**And** côté écran, un modèle cloud choisi puis le cloud désactivé affiche le message et propose le meilleur modèle local

### Story 2.5 : Une réponse cloud affiche une estimation ou « non mesurable », jamais 0

As a consultant,
I want que le CO₂ d'une réponse cloud soit estimé par ecologits ou déclaré « non mesurable » avec sa raison,
So that je ne présente jamais un chiffre inventé ni un zéro trompeur.

**Gouverné par :** AD-10, AD-11 ; AR9, AR22.

**Acceptance Criteria:**

**Given** `ecologits` épinglé `>=0.11.3,<0.12`, importé dans la fonction
**When** une feuille cloud se termine
**Then** `greenops` appelle `ecologits.tracers.utils.llm_impacts(provider=…, model_name=…, output_token_count=…, request_latency=…, electricity_mix_zone=…)` par arguments nommés, **jamais `EcoLogits.init()`**, et écrit `co2 = {mg, method: "ecologits", estimated: true, range_mg: {low, high}, allocation: "direct"}`
**And** un test de contrat fige la signature de `llm_impacts`

**Given** un modèle Groq
**When** il a une entrée dans la table de correspondance de `wavelocalai.toml` (vers l'entrée `huggingface_hub` du modèle ouvert, ex. `openai/gpt-oss-120b`)
**Then** l'estimation est faite sur cette entrée ; sans entrée, `co2 = {mg: null, method: "unmeasurable", reason: "<raison>"}`

**Given** un résultat ecologits avec `errors` non vide ou une exception
**When** la mesure échoue
**Then** `method` vaut `unmeasurable` avec la raison tirée du code d'erreur, et le run se termine normalement

**Given** le pied de réponse et le panneau CO₂ de session
**When** la réponse est cloud
**Then** il affiche « 0,9 mg (estimé) » ou « non mesurable » avec son aide (ex. « Anthropic ne publie pas la taille de ce modèle : son empreinte ne peut pas être calculée. »), jamais « — » seul ni 0 ; le total de session compte les non-mesurables à part

### Story 2.6 : Retrouver, exporter et effacer une conversation (préversion 2.0.0a2)

As a consultant,
I want rouvrir ma conversation, l'exporter en JSON ou Markdown et l'effacer pour de bon,
So that je garde une trace de la démo ou n'en laisse aucune sur le poste.

**Gouverné par :** AD-3, AD-5, AD-7, AD-13 ; AR11 ; UX-DR21.

**Acceptance Criteria:**

**Given** une conversation de plusieurs échanges
**When** on rouvre `#/arene/chat` ou appelle `GET /api/conversations/{id}`
**Then** les messages, le raisonnement, les métriques et le CO₂ de chaque réponse reviennent tels qu'affichés ; le modèle choisi est gardé par conversation

**Given** une conversation
**When** on appelle `GET /api/conversations/{id}.json` ou `.md` (bouton Télécharger)
**Then** l'export contient messages, modèle et origine, débit D3, CO₂ avec sa méthode, sans clé d'API

**Given** une conversation sans run actif
**When** on clique « Effacer la conversation » (sans confirmation) ou appelle `DELETE /api/conversations/{id}`
**Then** ses `messages` et `run_events` sont supprimés, ses lignes `runs` sont gardées sans texte avec `conversation_id` à `NULL`, puis `DELETE`, `wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)` passent dans la file de l'écrivain
**And** un test vérifie que le texte effacé est absent des octets du `.db` et du `-wal`, et que le CO₂ de session ne baisse pas

**Given** une conversation avec un run actif
**When** on demande de l'effacer
**Then** la réponse est `409` avec son message et son action

**Given** l'Epic 2 terminé et la suite `tests/v2` verte
**When** on publie
**Then** `version = "2.0.0a2"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.2`, release GitHub avec notes ; la recette humaine joue un chat local et un chat cloud sur une démo réelle

### Story 2.7 : Le Chat prend la créativité du modèle et s'exporte sur écran étroit (suite, correct course)

As a consultant,
I want que la créativité par défaut soit celle que le modèle recommande, et pouvoir exporter la conversation sur un écran étroit,
So that chaque modèle répond dans ses conditions prévues et que l'export reste accessible partout.

**Gouverné par :** AD-15, AD-20 ; AR13, AR18 ; FR8, FR16, FR19 ; UX-DR17, UX-DR21 ; décisions D-3, D-12, D-13 (`sprint-change-proposal-2026-10-19.md`). **Dépend de :** `master` (Epic 2 fusionnée) ; à fusionner avant 3.6, qui réutilise le menu « Exporter ». Pas de version propre : elle part dans la préversion suivante.

**Acceptance Criteria:**

**Given** `GET /api/models`
**When** on l'appelle
**Then** chaque modèle de conversation porte `default_temperature` (`float | null`) : la valeur des paramètres publiés par Ollama pour ce modèle (lus avec les faits du modèle, en cache `model_facts`) ou celle du catalogue, sinon `null` ; la route reste servie depuis le cache, sous le budget de 300 ms Ollama arrêté (test)
**And** `contrat-api.md` (Modèles) le décrit déjà (correct course) ; le fichier `wavelocalai.toml` est inchangé après le choix d'un modèle (test : empreinte avant et après)

**Given** l'écran Chat libre
**When** on choisit un modèle
**Then** le curseur « Créativité » prend sa `default_temperature`, ou 0,2 si elle est `null` (D-12) ; changer de modèle remet le curseur au défaut du nouveau modèle tant que la personne ne l'a pas déplacé dans cette conversation ; la valeur affichée est celle envoyée dans `POST /api/chat/runs`

**Given** une largeur sous 768 px
**When** la conversation a au moins un échange
**Then** les deux boutons « Télécharger en JSON » et « Télécharger en Markdown » cèdent la place à un bouton « Exporter » qui ouvre un menu des deux formats (clavier : flèches, Entrée, Échap qui ferme et rend le focus au bouton) ; chaque entrée suit la route d'export du serveur, sans `blob:` (D-3) ; dès 768 px, les deux boutons restent
**And** le menu est un composant ou un utilitaire partagé, que l'Arène (3.6) réutilise pour CSV et Markdown

**Given** l'état « Premier chargement lent » d'UX-DR17 (déclenchement sur `model_loading` déjà couvert par les stories 2.1 et 2.2)
**When** `wl-run-status` l'affiche
**Then** seul le message « Le premier appel charge le modèle en mémoire : de 8 à 26 secondes. » est nouveau ici

**Given** un `409 run_busy` rejoint
**When** le run actif est suivi
**Then** le message tapé reste dans le champ (D-13, déjà livré : un test E2E le garde)
**And** axe-core sans violation, clair et sombre, projection comprise ; 320 px sans défilement horizontal

## Epic 3 : Comparer des modèles côte à côte et conclure chiffres à l'appui

L'utilisateur lance l'Arène sur 2 à 4 modèles : colonnes en flux, notation par un juge, classement, matrice qualité/CO₂, verdict local/cloud chiffré, résultat rouvrable par URL et exportable avec preuve. C'est l'écran du Flow 1, lisible du fond d'une salle.

### Story 3.1 : L'Arène exécute plusieurs modèles sur une même question (serveur)

As a consultant en avant-vente,
I want lancer une même question sur plusieurs modèles, les locaux l'un après l'autre et les cloud en parallèle, sans qu'un modèle lent bloque les autres,
So that la comparaison aboutit toujours, même si un modèle échoue.

**Gouverné par :** AD-5, AD-6, AD-9, AD-10, AD-14 ; AR4, AR5, AR12.

**Acceptance Criteria:**

**Given** `POST /api/arena/runs {models, prompt, judge, criteria, allow_cloud}` avec 2 à 4 modèles distincts
**When** on l'appelle
**Then** le hub crée un run racine `arena` et un run enfant par modèle (`parent_run_id`) ; un même modèle ne figure qu'une fois ; moins de 2 ou plus de 4 modèles rend une erreur de validation ; un modèle cloud sans `allow_cloud` rend `cloud_not_allowed` avant tout appel
**And** seul le parent publie le flux ; `token`, `metrics` et `lane_status` portent `lane` = tag ; métriques et `co2` ne vivent que sur les enfants

**Given** deux modèles locaux et un modèle cloud
**When** le run s'exécute
**Then** les locaux passent en séquence par le sémaphore, le cloud part aussitôt en parallèle, et chaque lane publie `lane_status` (`waiting`, `loading`, `generating`, `done`, `timeout`, `failed`, `cancelled`)

**Given** une lane qui dépasse son délai ou échoue
**When** le délai court depuis l'acquisition du sémaphore (local) ou le départ de l'appel (cloud)
**Then** cette lane passe à `timeout` ou `failed` avec son erreur, les autres continuent, et le parent finit `ok` si l'orchestration aboutit (test avec le `fake` : une lane lente, une lane en échec)

**Given** une Arène en cours
**When** on annule le parent
**Then** toutes les lanes passent à `cancelled`, les partiels sont gardés ; une seconde Arène pendant ce temps rend `409 run_busy` avec le `run_id` actif

### Story 3.2 : L'écran Arène affiche les colonnes en flux

As a consultant devant un DSI,
I want configurer la comparaison en quelques gestes et voir chaque colonne se remplir en direct avec son statut,
So that la salle comprend ce qui se passe à chaque instant, y compris pendant les chargements.

**Gouverné par :** AD-6, AD-20 ; AR18 ; UX-DR8, UX-DR9, UX-DR17, UX-DR19, UX-DR20.

**Acceptance Criteria:**

**Given** l'écran `screens/arena.js` sur `#/arene/comparer` (onglet « Arène » passé à `available`)
**When** on l'ouvre
**Then** le champ Question, les scénarios prédéfinis (Vulgarisation, Extraction JSON, Résumé, Traduction) qui remplissent la question, `wl-model-picker` en mode multi présélectionné sur le défaut `arena`, et la phrase « Les modèles locaux passent l'un après l'autre (mémoire) ; les modèles cloud en parallèle. » sont affichés
**And** avec moins de 2 modèles, « Lancer la comparaison » est désactivé avec la légende « Choisissez au moins 2 modèles »

**Given** une comparaison lancée
**When** les événements arrivent
**Then** une colonne par modèle (2 à 4) affiche nom, badge, statut en texte et icône (En attente, Chargement du modèle en mémoire, Génération, Notation, Terminé, Délai dépassé, Échec, Arrêté), débit provisoire puis final, premier token, tokens, chargement et durée, et la réponse en flux avec « Afficher toute la réponse »
**And** le bandeau « Comparaison en cours · 2 sur 3 · 0:42 » porte Arrêter (et Échap)

**Given** une lane en délai dépassé
**When** les autres continuent
**Then** sa colonne affiche « Délai dépassé pour ce modèle. Les autres continuent. » et le reste de l'écran n'est pas affecté

**Given** une largeur de 1 024 à 1 439 px, puis moins de 768 px
**When** l'Arène s'affiche
**Then** 2 colonnes restent visibles avec défilement horizontal et en-têtes collants, puis l'Arène passe en onglets par modèle ; le mode focus agrandit une colonne
**And** quitter l'écran pendant la comparaison puis revenir reprend le flux par `?after=` sans perte ni doublon ; axe-core sans violation, clair et sombre, en mode projection compris

*Ajouts du correct course (2026-10-19), maquette validée :*

**Given** 4 modèles et une largeur d'au moins 1 440 px
**When** les colonnes s'affichent
**Then** les 4 colonnes sont visibles, la réponse de chacune est repliée sur 4 lignes et se déplie par « Afficher toute la réponse » (D-15)

**Given** une comparaison lancée
**When** elle s'exécute
**Then** la configuration est remplacée par un résumé (question, modèles, juge) jusqu'à `run_ended` (D-16)

**Given** la configuration
**When** un prérequis manque
**Then** « Lancer la comparaison » est désactivé avec la raison visible : « Choisissez au moins 2 modèles », « Choisissez 4 modèles au plus » ou « Saisissez une question »

**Given** aucun modèle local prêt (par exemple en arrivant depuis l'Accueil, dont le bouton reste actif, D-11)
**When** l'Arène s'ouvre
**Then** un `alert-info` dit quoi faire (installer un modèle depuis Modèles, ou autoriser le cloud) et le lancement reste désactivé avec sa raison

### Story 3.3 : Un juge note chaque réponse, et « non évalué » n'est jamais 0

As a consultant,
I want qu'un modèle juge note chaque réponse sur 100 avec sa raison, et que l'app dise quand la note est peu fiable ou impossible,
So that je conclus sur la qualité sans tromper la salle.

**Gouverné par :** AD-5, AD-8 (`response_schema`), AD-9, AD-14 ; AR7, AR16.

**Acceptance Criteria:**

**Given** le champ `response_schema` du port `ChatModel`
**When** un adaptateur le reçoit
**Then** Ollama le passe en `format`, Anthropic en `tool_use`, OpenAI-compatible et Mistral en schéma JSON, et chaque adaptateur rend une sortie structurée validée (test par adaptateur avec un faux client)

**Given** une lane terminée
**When** le service `evaluation/` note la réponse avec le juge (run enfant à part, sous le sémaphore si local) selon les critères choisis
**Then** l'Arène publie `lane_status: judging` puis `judge_score {lane, score, reason}` (/100)
**And** une réponse vide, une sortie de juge invalide ou un juge indisponible donnent `score: null` et une raison (« non évalué : réponse vide », « juge indisponible »), jamais 0

**Given** le défaut `judge` (plus gros modèle local qui tient)
**When** le juge choisi a moins d'environ 4 milliards de paramètres actifs
**Then** l'écran affiche l'avertissement « note peu fiable » et l'étiquette « un seul juge » accompagne les notes

**Given** l'écran Arène
**When** on ouvre « Critères de notation » (replié)
**Then** on peut ajuster les critères envoyés au juge ; le juge porte son badge Local ou Cloud et le cloud n'est jamais choisi comme juge sans `allow_cloud`
**And** sans juge choisi (aucun modèle éligible, ou juge retiré), « Lancer la comparaison » est désactivé avec la raison visible « Choisissez un juge » (correct course, maquette validée) ; les notes restent sur /100 (D-5)

### Story 3.4 : Le classement, la matrice qualité/CO₂ et le tableau se construisent au fil des résultats

As a consultant,
I want un classement qui se construit pendant la comparaison, puis une matrice qualité/CO₂ et son tableau,
So that la salle voit d'un coup d'œil que le plus petit modèle peut gagner.

**Gouverné par :** AD-10, AD-20 ; AR18 ; UX-DR13, UX-DR14, UX-DR15.

**Acceptance Criteria:**

**Given** des lanes notées au fil de l'eau
**When** chaque `judge_score` et `metrics` arrive
**Then** le classement se met à jour (note, badge, débit, CO₂) et se fige à `run_ended` ; une lane « non évalué » est listée avec sa raison sous les lanes notées, sans rang de podium

**Given** `wl-chart-svg`
**When** la comparaison est finie (segments « Matrice · Tableau », Matrice choisie par défaut, D-14)
**Then** la matrice s'affiche d'abord, le tableau derrière « Voir le tableau » ; un nuage de points SVG fait main place la qualité (/100) et le débit, le CO₂ en taille avec une légende de taille, noms complets en étiquette, couleurs `chart-*` ; `<title>` et `<desc>` décrivent le graphique, et un lien « Voir le tableau » y mène
**And** aucun axe n'est resserré sur un seul point, aucune couleur ne porte seule une information

**Given** `wl-data-table`
**When** on choisit « Tableau »
**Then** un `<table>` sémantique (en-têtes `scope`) liste modèle, origine, note, débit, CO₂, chargement et durée, triable au clavier
**And** les CO₂ d'une même comparaison sont dans une seule unité ; « non mesurable » et « non évalué » s'affichent en texte, jamais 0 ni « — »

### Story 3.5 : Le verdict local/cloud est chiffré

As a consultant face à un DSI qui hésite entre une API cloud et un modèle local,
I want un verdict qui chiffre l'écart de note, le coût pour 1 000 requêtes, le CO₂ et les données restées sur le poste,
So that la conclusion repose sur des chiffres et pas sur une impression.

**Gouverné par :** AD-10, AD-15 ; AR13.

**Acceptance Criteria:**

**Given** une table de prix cloud datée dans `wavelocalai.toml` (prix par million de tokens d'entrée et de sortie, date de relevé)
**When** une Arène comprend au moins un modèle local et un modèle cloud, tous deux notés
**Then** le serveur calcule le verdict à la fin du run et le rend dans l'instantané `GET /api/runs/{id}` (champ `verdict`, AD-5) : écart de note entre le meilleur local et le meilleur cloud, coût pour 1 000 requêtes de même taille (0 € pour le local, prix daté pour le cloud), CO₂ de chacun, et « données restées sur le poste » pour le local
**And** le front lit cet instantané à `run_ended` et à la réouverture, et n'en calcule rien ; aucun nouveau type d'événement n'est créé

**Given** un modèle cloud absent de la table de prix
**When** le verdict est calculé
**Then** le coût s'affiche « inconnu » avec la raison, jamais 0

**Given** une Arène sans modèle cloud
**When** elle se termine
**Then** le verdict local/cloud n'apparaît pas ; le classement suffit
**And** la date de la table de prix est affichée avec le coût

### Story 3.6 : Rouvrir, exporter et lancer l'Arène depuis l'Accueil (Flow 1)

As a consultant,
I want rouvrir une comparaison par son URL, l'exporter avec la preuve de la mesure et la lancer depuis la carte « Démo recommandée » de l'Accueil,
So that je peux rejouer le Flow 1 de bout en bout et laisser une trace vérifiable au client.

**Gouverné par :** AD-5, AD-7, AD-13, AD-20 ; AR6, AR11 ; UX-DR20, UX-DR24.

**Acceptance Criteria:**

**Given** une Arène terminée
**When** on ouvre `#/arene/comparer/<run_id>` ou la liste `GET /api/arena/runs`
**Then** l'écran se reconstruit depuis la base (colonnes, notes, classement, matrice, verdict) sans relancer de modèle ; « Relancer » et « Modifier la question » reprennent la configuration
**And** un identifiant inconnu rend `404 run_not_found` (code ajouté à `errors.py`, `detail.run_id`) et l'écran affiche « Résultat introuvable » avec un lien vers une nouvelle comparaison (correct course) ; l'affichage d'un résultat effacé reste à trancher (écart ouvert de `contrat-api.md`), seul l'identifiant inconnu rend `run_not_found`

**Given** une Arène terminée
**When** on appelle `GET /api/arena/runs/{id}.csv` ou `.md` (boutons « Exporter en CSV » et « Exporter en Markdown » ; sous 768 px, un seul « Exporter » qui ouvre le menu des formats livré par 2.7, D-3)
**Then** l'export contient, par modèle, note et raison, débit D3 et `tps_source`, CO₂ avec méthode, chargement, durée, et la preuve : fiche machine, version d'Ollama, digests des modèles, méthode CO₂, juge et ses critères ; aucune clé d'API

**Given** une Arène sans run actif
**When** on l'efface
**Then** ses `run_events` et `messages` sont supprimés, ses `runs` gardés sans texte comme registre carbone (AD-13), et une Arène en cours rend `409`

**Given** l'Accueil
**When** l'Arène est `available`
**Then** la carte « Démo recommandée » montre « Arène » en titre et « Arène des modèles » en sous-titre (D-10), sa phrase, les modèles prêts du défaut `arena` avec leur badge et « Lancer une comparaison » qui ouvre l'Arène présélectionnée ; sans modèle local, « Aucun modèle local disponible » et, si le cloud est autorisé, des modèles cloud proposés
**And** « Lancer une comparaison » reste actif même sans modèle local prêt : l'Arène dit alors quoi faire (D-11, critère de 3.2)

**Given** le Flow 1 d'`EXPERIENCE.md`
**When** le test E2E le joue avec trois modèles simulés (`fake`, dont un en délai dépassé et un « non évalué »)
**Then** l'Accueil dit « Disponible », la comparaison se lance depuis la carte, les colonnes se remplissent, le classement vaut pour les modèles notés, l'export contient la preuve, et la page n'est jamais rechargée
**And** axe-core sans violation sur l'Arène et l'Accueil, clair et sombre ; la recette humaine joue le Flow 1 sur une démo réelle

**Given** l'Epic 3 terminé et la suite `tests/v2` verte
**When** on publie
**Then** `version = "2.0.0a3"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.3`, release GitHub avec notes

## Epic 4 : Interroger ses propres documents et vérifier la source

L'utilisateur constitue sa base documentaire locale, l'interroge en naïf, HyDE ou Self-RAG et vérifie d'où vient chaque réponse ; le garde-fou mémoire chiffre le besoin. C'est l'écran du Flow 2 ; l'epic clôt le MVP.

### Story 4.1 : Indexer un document dans la base locale (serveur)

As a consultante en atelier,
I want importer un PDF, un DOCX, un TXT ou un MD et le voir indexé en local, fichier par fichier, avec la raison d'un échec,
So that ma base documentaire se construit sans rien envoyer hors du poste.

**Gouverné par :** AD-4, AD-5, AD-8 (`Embedder`), AD-9, AD-10, AD-11, AD-12, AD-14, AD-16 ; AR4 bis, AR7, AR9, AR10, AR12, AR14, AR21.

**Acceptance Criteria:**

**Given** la migration `0004_documents.sql` (tables `documents` avec source, empreinte, modèle d'embedding, `status` `indexing` / `ready` / `failed`, et `chunks` avec texte et position)
**When** le premier embedding est calculé
**Then** `store.ensure_vec_table(dim)` crée `chunks_vec_<dim>` (vec0, `rowid = chunks.id`), de façon idempotente, seule exception écrite aux migrations
**And** le port `VectorIndex` a deux implémentations, sqlite-vec et un repli numpy utilisé par les tests
**And** `models/fake.py` gagne un `Embedder` scriptable (vecteurs déterministes dérivés du texte, dimension fixe), enregistré seulement si `Settings.testing` est vrai, pour les tests et l'E2E du Flow 2 (AD-8)

**Given** `POST /api/rag/documents` (multipart, plusieurs fichiers)
**When** on l'appelle
**Then** la réponse rend le `run_id` d'un run `ingest` ; chaque fichier passe par `_validate_path` (copié de la v1), l'extraction (`pypdf`, `python-docx` importés dans la fonction, versions revérifiées) et la découpe dans le pool de threads, puis l'embedding par `registry.resolve_embedder(tag)` (Ollama `/api/embed`, sémaphore pris par lot)
**And** le flux publie `ingest_progress {fichier, phase: extract|split|embed, done, total}` par fichier
**And** chaque lot d'embedding est une feuille `embedding` du run `ingest`, mesurée par CodeCarbon sous le sémaphore comme toute feuille locale, et comptée dans le CO₂ de session (taille de lot dans `Settings`)

**Given** un fichier protégé par mot de passe, vide ou d'un format refusé
**When** son ingestion échoue
**Then** ce document passe à `failed` avec la raison (`ingest_failed`), ses extraits partiels ne sont pas interrogeables, les autres fichiers du lot continuent, et le nombre de documents `ready` ne change pas pour lui

**Given** une ingestion en cours
**When** on l'annule, ou qu'un chat local tourne en même temps
**Then** l'annulation laisse les documents déjà `ready` intacts et retire les extraits du document en cours ; le chat et l'ingestion s'intercalent par le sémaphore pris par appel
**And** un document déjà présent (même empreinte) n'est pas indexé deux fois

*Ajouts du correct course (2026-10-19), maquette validée :*

**Given** un document en échec
**When** on appelle `GET /api/rag/documents`
**Then** il figure avec `status: "failed"` et sa raison (message d'`ingest_failed`), et n'entre pas dans le nombre de documents prêts (D-26, test)
**And** la façon dont l'échec ou le doublon d'un fichier voyage dans le flux du run `ingest` (champ de `ingest_progress` ou autre) est consignée dans `contrat-api.md` (Événements) par la PR de la story

### Story 4.2 : L'écran Base documentaire suit chaque fichier

As a consultante en atelier,
I want déposer mes fichiers dans une zone visible tout de suite et suivre leur progression un par un,
So that je sais quand ma base est prête et pourquoi un fichier a échoué.

**Gouverné par :** AD-6, AD-20 ; AR18 ; UX-DR13, UX-DR16, UX-DR17, UX-DR22.

**Acceptance Criteria:**

**Given** l'écran `screens/documents-base.js` sur `#/documents/base` (module Documents passé à `available`, onglet « Évaluation de la qualité » désactivé avec sa raison)
**When** on l'ouvre
**Then** la zone de dépôt « Déposez des fichiers ici ou Choisir des fichiers · PDF, TXT, MD, DOCX » est visible sans attendre aucun appel au serveur
**And** base vide : la carte « Votre base documentaire est vide » avec « Importer des documents »

**Given** des fichiers déposés
**When** l'envoi puis l'indexation avancent
**Then** chaque fichier a sa ligne : progression d'envoi du navigateur, puis « Découpage · Vectorisation 18/40 extraits » depuis `ingest_progress` ; un seul bouton « Annuler l'import », au-dessus des lignes, annule le lot entier (le run `ingest`, ou l'envoi s'il n'est pas fini), les documents déjà prêts restant (D-25 : remplace l'« Annuler » par ligne)
**And** un échec affiche « Le fichier n'a pas pu être indexé : <raison>. » avec « Détails techniques » replié ; un succès affiche « N extraits ajoutés depuis M documents » (pluriels accordés)

**Given** `GET /api/rag/documents`
**When** la liste s'affiche
**Then** `wl-data-table` montre nom, extraits, date d'ajout (`fr-FR`), modèle de représentation et statut ; un document `indexing` n'est pas présenté comme prêt ; un document `failed` figure aussi, statut « Échec » avec sa raison, sans compter dans « N documents indexés », et survit au rechargement (D-26, correct course ; son « Supprimer » arrive avec 4.3)
**And** quitter l'écran pendant une ingestion puis revenir reprend la progression par `?after=` ; axe-core sans violation, clair et sombre

### Story 4.3 : Supprimer un document, vider la base, changer de réglages

As a consultante,
I want supprimer un seul document, vider toute la base après une confirmation chiffrée et régler la découpe ou le modèle de représentation,
So that je maîtrise ce que contient ma base et qu'une erreur de clic ne détruit rien.

**Gouverné par :** AD-13, AD-15, AD-16 ; AR11, AR13, AR14 ; UX-DR12.

**Acceptance Criteria:**

**Given** un document `ready` ou `failed` sans run actif
**When** on clique Supprimer
**Then** `wl-confirm-dialog` s'ouvre comme pour « Vider » (D-24) : « Supprimer « note-cadrage.docx » ? », « 14 extraits seront retirés de la base. Cette action est irréversible. » (document en échec : « Ce document n'a pas été indexé : aucun extrait n'est retiré. »), focus sur « Annuler » ; « Annuler » ne supprime rien et annonce « Suppression annulée » ; confirmer appelle `DELETE /api/rag/documents/{id}` et se solde par « Document supprimé : note-cadrage.docx. 14 extraits retirés de la base. »

**Given** `DELETE /api/rag/documents/{id}` sur un document sans run actif
**When** on l'appelle
**Then** ses `chunks` et, dans la même transaction, leurs lignes vec0 par `rowid` sont supprimés, puis `DELETE`, `wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)` passent dans la file de l'écrivain
**And** un test vérifie l'absence du texte du document dans les octets du `.db` et du `-wal`, et consigne l'état du résidu vectoriel dans le blob vec0 (point différé de la spine)

**Given** une base de 12 documents et 340 extraits
**When** on clique « Vider la base documentaire »
**Then** `wl-confirm-dialog` (`<dialog>` natif, focus sur « Annuler ») annonce « 340 extraits de 12 documents seront supprimés. » ; « Annuler » ne supprime rien (test) ; confirmer appelle `DELETE /api/rag/base?expected_count=340`, qui supprime puis recrée la table vec0, et le résultat se solde par un message au même verbe
**And** un `expected_count` qui ne correspond plus au contenu réel rend une erreur sans rien supprimer

**Given** `GET` et `PUT /api/rag/settings` (modèle de représentation, découpe, nombre d'extraits, stratégie par défaut) stockés dans `preferences`
**When** on change de modèle d'embedding alors que la base n'est pas vide
**Then** la réponse impose « Vider » d'abord ; l'app n'écrit jamais `wavelocalai.toml`

**Given** un run `ingest` ou `rag` actif
**When** on demande de supprimer un document visé, de vider ou de changer d'embedding
**Then** la réponse est `409` avec son message et son action
**And** ces refus (changement d'embedding sur une base non vide, `expected_count` périmé, document visé par un run actif) ont chacun leur code dans `errors.py` (AD-18), que le front affiche par `wl-error`

### Story 4.4 : Poser une question à ses documents et recevoir les sources d'abord (serveur)

As a consultante,
I want poser une question et recevoir les extraits utilisés avant la réponse, avec document, page et extrait entier,
So that je peux vérifier la réponse pendant qu'elle s'écrit.

**Gouverné par :** AD-5, AD-6, AD-7, AD-9, AD-14, AD-16 ; AR4, AR6, AR14.

**Acceptance Criteria:**

**Given** `POST /api/rag/runs {conversation_id?, question, model, strategy: "naive", allow_cloud}`
**When** on l'appelle
**Then** la réponse rend `{run_id, conversation_id}` (conversation `rag` créée par le hub) ; seuls les documents `ready` sont interrogés ; `retrieval_step {strategy, étape, durée}` puis `sources` partent **avant** le premier `token`
**And** l'embedding de la question est une feuille `embedding`, la génération une feuille `generation`, chacune avec son `co2`

**Given** l'événement `sources`
**When** il est publié
**Then** chaque source porte `{n, doc_id, document, page, chunk_id, text, rank, relevance_label, raw_score, passage}`, `relevance_label` parmi « très proche », « proche », « éloignée » selon une règle de normalisation testée, et l'extrait entier
**And** `passage` vaut `{start, end}` (positions en caractères dans `text`) du passage que le serveur désigne pour le surlignage, selon une règle écrite dans la story et testée (par exemple la phrase de l'extrait la plus proche de la question), ou `null` (D-21, correct course) ; `null` signifie « pas de surlignage » : l'extrait s'affiche entier, sans passage mis en valeur (comme `contrat-api.md` et EXPERIENCE.md)
**And** il est persisté **sans `text`** (les positions de `passage` sont persistées) ; au rejeu, le hub le réhydrate depuis `chunks`, avec `text: null` si le document a été supprimé (test)

**Given** `GET /api/rag/chunks/{id}`
**When** on ouvre un extrait
**Then** il rend le texte entier, le document et la page, ou une erreur claire si l'extrait n'existe plus

**Given** une réponse terminée
**When** `metrics` est publié
**Then** il porte le débit D3, la durée de recherche à part et le `co2` de la feuille de génération ; une base vide rend une erreur qui mène à la Base documentaire

### Story 4.5 : L'écran Discussion montre la réponse à côté de ses sources

As a consultante en atelier,
I want lire la réponse à gauche et ses sources à droite, avec l'extrait entier et sa pertinence en clair,
So that je retrouve mot pour mot le paragraphe de mon document qui fonde la réponse.

**Gouverné par :** AD-6, AD-7, AD-20 ; AR18 ; UX-DR8, UX-DR10, UX-DR11, UX-DR17, UX-DR19, UX-DR23.

**Acceptance Criteria:**

**Given** l'écran `screens/documents.js` sur `#/documents`
**When** on l'ouvre
**Then** l'en-tête dit « N documents · M extraits », `wl-model-picker` est sur le défaut `rag` avec sa raison, « Réglages avancés » est replié, et le champ dit « Posez une question à vos documents »
**And** base vide : un message mène à la Base documentaire

**Given** une question envoyée
**When** le run avance
**Then** `wl-run-status` affiche « Recherche des extraits… » puis « Génération… », `wl-source-panel` se remplit avant la réponse (liste numérotée, document, page, libellé de pertinence, score brut en aide, extrait entier avec le passage `passage` surligné quand il est fourni, D-21, « Ouvrir l'extrait »), puis `wl-chat-thread` affiche la réponse et son pied (badge, CO₂, débit, « Recherche 0,06 s · Génération 5,8 s »)
**And** dès 1 024 px, le panneau des sources est toujours ouvert, sans bouton de repli (D-22)

**Given** une conversation de plusieurs réponses
**When** la deuxième réponse arrive
**Then** chaque réponse porte « Afficher les sources », qui charge ses sources dans l'unique panneau ; le panneau montre par défaut celles de la dernière réponse (D-23)

**Given** une conversation rouverte dont un document a été supprimé
**When** les sources sont rejouées
**Then** la source concernée affiche « extrait supprimé »

**Given** une largeur sous 1 024 px
**When** l'écran s'affiche
**Then** le panneau des sources passe sous la réponse, replié
**And** quitter et revenir reprend le flux par `?after=` ; axe-core sans violation, clair et sombre

### Story 4.6 : Chercher autrement (HyDE, Self-RAG) et citer ses sources

As a consultante,
I want choisir une stratégie de recherche plus fine et voir, quand le modèle cite, quelle phrase vient de quelle source,
So that je montre en atelier qu'une meilleure recherche change la réponse.

**Gouverné par :** AD-5, AD-6, AD-8 ; AR7 ; UX-DR11, UX-DR23.

**Acceptance Criteria:**

**Given** `strategy: "hyde"`
**When** le run s'exécute
**Then** une réponse hypothétique est générée (fonction async, appel de modèle en run enfant), puis sert à la recherche ; `retrieval_step` et le `run-status` disent « Rédaction d'une réponse hypothétique… »

**Given** `strategy: "self_rag"`
**When** le run s'exécute
**Then** une boucle bornée (nombre d'itérations dans `Settings`) vérifie la pertinence des extraits et reformule au besoin ; le `run-status` dit « Vérification de la pertinence… » ; la borne atteinte termine proprement avec les meilleurs extraits trouvés

**Given** une consigne de citation dans l'invite
**When** la réponse contient des marqueurs [n]
**Then** le back les vérifie contre les sources et publie `citations` ; seules les citations vérifiées sont affichées, et survoler ou focaliser [n] met la source en évidence, et inversement
**And** sans `citations`, la réponse ne porte aucun marqueur inventé par le front

**Given** les « Réglages avancés »
**When** on change de stratégie ou de nombre d'extraits
**Then** le réglage agit réellement sur le run suivant ; les noms techniques (HyDE, Self-RAG, Top-K) ne figurent qu'en aide

### Story 4.7 : Reclasser les extraits avec un reranker local, s'il est là

As a consultante,
I want que la recherche reclasse les extraits avec un reranker local quand il est installé, et que l'écran dise pourquoi sinon,
So that j'obtiens de meilleurs extraits sans jamais déclencher de téléchargement pendant l'atelier.

**Gouverné par :** AD-4, AD-17, AD-21 ; AR15, AR17.

**Acceptance Criteria:**

**Given** l'extra `rerank` installé (`uv sync --extra rerank`, fastembed 0.9.0) et le modèle présent dans le `cache_dir` du dossier de données
**When** une recherche s'exécute
**Then** `disable_telemetry()` est appelé juste avant l'import de fastembed, ce que vérifie un test AST créé par cette story dans `tests/v2/unit/` (sur le modèle de `tests/unit/test_telemetry.py`, il relève tout module v2 qui importe fastembed ou huggingface_hub et vérifie l'ordre, AD-21), le modèle est chargé avec `local_files_only=True` dans le pool de threads, les extraits sont reclassés et `run-status` dit « Reclassement… »

**Given** l'extra absent, le modèle absent du cache, ou une `ValueError` au chargement
**When** une recherche s'exécute
**Then** le RAG tourne sans reranker, `GET /api/rag/settings` et l'écran disent pourquoi (« Reclassement indisponible : <raison> »), et aucun téléchargement n'est tenté (test sans réseau)
**And** la récupération explicite du modèle de reranker (run `pull`) reste à l'écran Modèles (Epic 5) ; d'ici là, le README dit comment remplir le `cache_dir` hors de l'app (AD-17)

### Story 4.8 : Le garde-fou mémoire chiffre le besoin réel et garde la question

As a consultante sur un portable de 16 Go sans GPU,
I want que l'app m'arrête avant de saturer la mémoire, me dise combien il faut et combien j'ai, et me propose une issue,
So that la démo ne gèle jamais le poste et que je ne perds pas ma question.

**Gouverné par :** AD-14, AD-18, AD-20 ; AR12, AR16 ; UX-DR16.

**Acceptance Criteria:**

**Given** `hardware/` qui calcule la mémoire nécessaire d'un modèle et la mémoire libre
**When** le modèle demandé est **déjà chargé** dans Ollama (`/api/ps`)
**Then** le besoin compté est nul ou réduit à l'écart, et aucun blocage n'a lieu à tort (test avec un modèle chargé simulé)

**Given** une inférence locale (chat, Arène, Discussion) dont le besoin dépasse la mémoire libre
**When** on lance le run
**Then** il se termine en `error` avec `ram_guard` : « Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres. », et deux actions : « Prendre un modèle plus petit » (le plus gros modèle local qui tient, proposé par le serveur) et « Décharger les modèles inactifs »
**And** `detail` porte `needed_gb`, `free_gb` et `suggested_model` (clés déclarées avec `ram_guard` dans `errors.py`, AD-18), dont le front tire ses deux boutons
**And** la question reste dans le champ et dans l'historique ; le front ne calcule rien
**And** « Prendre un modèle plus petit » sélectionne `detail.suggested_model` dans `wl-model-picker` sans relancer : la personne renvoie sa question (précision du correct course)

**Given** « Décharger les modèles inactifs »
**When** on clique
**Then** `POST /api/models/unload` décharge les modèles Ollama sans run actif, et la mémoire libre se met à jour sur le flux système

### Story 4.9 : Jouer le Flow 2 de bout en bout et clore le MVP (préversion 2.0.0a4)

As a formateur qui anime un atelier,
I want que chaque consultant puisse, depuis l'Accueil, importer un document, l'interroger et retrouver sa source sans aide,
So that l'atelier documentaire se déroule sans incident.

**Gouverné par :** AD-3, AD-20 ; UX-DR24, UX-DR25.

**Acceptance Criteria:**

**Given** l'Accueil
**When** l'Assistant documentaire est `available`
**Then** sa carte montre « Documents » en titre, « Assistant documentaire » en sous-titre (D-10) et « N documents indexés · M extraits » (résumé de la base), et ouvre le module

**Given** le Flow 2 d'`EXPERIENCE.md`
**When** le test E2E le joue sur une base de test en dossier temporaire (jamais `data/`) avec un `.docx` de test et un modèle simulé
**Then** base vide affichée, import suivi par fichier, « 14 extraits ajoutés depuis 1 document », question posée, sources avant la réponse, extrait retrouvé mot pour mot avec son passage surligné (D-21) ; puis « Vider » cliqué par erreur, « Annuler » ne supprime rien ; puis garde-fou simulé : la question reste et l'alerte chiffre le besoin
**And** aucune requête du navigateur ne sort de `127.0.0.1` pendant le Flow 2 ; axe-core sans violation sur tous les écrans du MVP, clair et sombre

**Given** les Epics 1 à 4 terminés et `tests/v2` vert
**When** on publie
**Then** `version = "2.0.0a4"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.4`, release GitHub avec notes ; la recette humaine joue Flow 1 puis Flow 2 sur un PC pro de 16 Go sans GPU installé par `uv sync` seul (signal de succès de la spec)

## Epic 5 : Suivre sa sobriété et administrer ses modèles

L'utilisateur suit en direct la charge du poste et l'empreinte de sa session, retrouve l'historique carbone, installe, décharge et supprime ses modèles en sachant s'ils tiennent, consulte la fiche d'un modèle et voit quel modèle convient à quel usage d'après le banc publié. **Prérequis :** mise à jour `bmad-ux` (écrans Sobriété et Modèles, spine §Deferred) et retour de recette du MVP ; 5.6 et 5.8 se développent sur un fichier `qb.results/1` de test ; 5.7 attend une release de slm-quality-bench synchronisée sur `master`, et la préversion `a5` part sans elle si les données manquent (décision Q7). Se termine par la préversion `2.0.0a5`.

### Story 5.0 : Découper les fichiers partagés du front

Story technique, avant la 5.1 (décision du 2026-10-19).

As a mainteneur qui fait avancer plusieurs écrans en parallèle,
I want que les fichiers du front partagés par tous les écrans soient découpés par écran, par composant ou par domaine,
So that deux stories d'écrans différents ne se mettent plus en conflit et que les parcours du navigateur soient vérifiés en CI.

**Gouverné par :** AD-20 ; NFR10.

**Acceptance Criteria:**

**Given** `static/i18n/fr.json`, les feuilles CSS communes, `core/api.js` et la déclaration des routes (`core/registry.js`)
**When** la story est livrée
**Then** les textes sont rangés par écran, le CSS par composant, `api.js` par domaine, et chaque écran déclare ses propres routes ; aucun changement visible (mêmes clés de texte, mêmes routes, E2E existants verts sans modification de leurs attentes)
**And** `components/wl-model-picker.js` passe sous 600 lignes
**And** `test_layers.py`, `test_shell_static.py`, le budget de lecture et le budget de la coquille (300 ms) restent verts

**Given** `.github/workflows/tests.yml`
**When** une PR vise `master`
**Then** un job lance les E2E navigateur de `tests/v2/e2e` (Ollama simulé, sans réseau), et un E2E rouge fait échouer la CI

### Story 5.1 : L'écran Sobriété montre la machine et la session en direct

As a consultant qui présente la sobriété,
I want un écran qui montre en direct le processeur, la mémoire, l'accélérateur et le CO₂ de la session, ventilé par module et par origine,
So that je relie la charge du poste aux réponses qui l'ont produite, sans cliquer sur « Rafraîchir ».

**Gouverné par :** AD-6, AD-10, AD-15, AD-20, AD-22 ; AR9, AR18 ; UX-DR13, UX-DR15, UX-DR17, UX-DR26. **Reports :** B10, B11, B13.

**Acceptance Criteria:**

**Given** l'écran `screens/sobriety.js` sur `#/sobriete` (module Sobriété passé à `available`)
**When** on l'ouvre
**Then** la section « Santé du système » affiche processeur %, mémoire utilisée et totale, accélérateur (« Aucun » si aucun n'est détecté, jamais « Actif » sans détection) et modèles chargés dans Ollama, mis à jour par le flux système sans clic
**And** le flux de l'écran se ferme quand l'onglet est masqué (`visibilitychange`) et se rouvre au retour en relisant `GET /api/carbon/session` (E2E)
**And** la version d'Ollama s'affiche en légende de « Santé du système » (décision du 2026-10-19)

**Given** un GPU NVIDIA présent (NVML)
**When** le flux système publie son état
**Then** il ajoute mémoire GPU utilisée et totale, température et bridage thermique (`hardware/machine_state.py`, déjà copié), lus hors de la boucle, sans ralentir l'échantillon de 2 s ; sans NVML, ces champs sont absents et l'écran dit « Aucun »
**And** le bridage thermique s'affiche en texte (« Bridage thermique en cours »), jamais par la couleur seule

**Given** `GET /api/system/identity`
**When** on l'appelle juste après le lancement, NVML froid, sur la tour RTX 3050
**Then** il répond en moins de 300 ms (mesure consignée dans la story) ; la carte d'identité technique, repliée, affiche la fiche machine et la version d'Ollama lue dans l'état en cache de la sonde

**Given** des réponses mesurées et non mesurables dans la session
**When** la section « Empreinte carbone de cette session » s'affiche
**Then** elle montre le total, la part par module (chat, arène, rag, agent, ingest), Local et Cloud « (estimé) », et le nombre de réponses non mesurables à part, depuis `GET /api/carbon/session` puis `carbon_updated` ; « Comment ces chiffres sont calculés », replié, cite CodeCarbon, ecologits et le D3
**And** axe-core sans violation, clair et sombre ; formats `fr-FR` ; aucune couleur par seuil de CO₂

**Given** le panneau « Comment ces chiffres sont calculés » (D-38, correct course)
**When** on l'ouvre
**Then** il donne l'équivalence parlante du CO₂ de la session en distance parcourue en voiture, avec le facteur (g de CO₂ par km), sa source publique et sa date ; facteur et valeur viennent du serveur (réglage daté de `wavelocalai.toml`, source vérifiée et citée par la story), jamais d'une constante du front
**And** l'équivalence n'apparaît nulle part ailleurs (ni section session, ni barre haute, ni Accueil)

### Story 5.2 : Retrouver l'historique carbone et ouvrir une nouvelle session

As a consultant,
I want voir l'historique des émissions par session sur 7 jours, 30 jours ou tout, et remettre le compteur de session à zéro,
So that je montre l'empreinte cumulée d'un atelier et repars d'un compteur propre pour la démo suivante.

**Gouverné par :** AD-10, AD-13, AD-20 ; AR9 ; UX-DR13, UX-DR14, UX-DR15, UX-DR26. **Reports :** B9.

**Acceptance Criteria:**

**Given** `GET /api/carbon/history?window=7d|30d|all`
**When** on l'appelle
**Then** il rend une ligne par `app_session` **close** de la fenêtre (début, fin, total en mg, Local, Cloud, nombre de non-mesurables), calculée depuis les feuilles de `runs`, conversations effacées comprises (AD-13 : le registre carbone ne baisse pas) ; la session en cours n'y figure qu'une fois close, et une phrase le dit sous le graphique : « La session en cours n'apparaît qu'une fois close. » (D-37)
**And** la route entre dans le test de budget de lecture (< 300 ms Ollama arrêté, base de 1 000 runs de test)

**Given** l'historique
**When** on choisit « Graphique » puis « Tableau »
**Then** `wl-chart-svg` trace des barres par session titrées « Émissions par session » (mg, une seule unité, trous de mesure visibles, aucune donnée tracée entre deux mesures) avec `<title>`, `<desc>` et « Voir le tableau » ; `wl-data-table` donne le même contenu, triable au clavier
**And** sans historique : « Aucune session mesurée pour l'instant. », sans graphique vide
**And** sous 640 px, « Tableau » est choisi par défaut (D-39)

**Given** `POST /api/carbon/session/reset` (écriture, `Origin` contrôlée)
**When** on clique « Remettre le compteur à zéro »
**Then** le hub ouvre une nouvelle `app_session` (`hub.new_app_session("reset")`), le total de la barre haute et de Sobriété repart de 0 par `carbon_updated`, et la session close apparaît dans l'historique
**And** un run actif pendant la remise à zéro reste compté dans la session où il a commencé (test)
**And** session vide (aucun run compté) : « Remettre le compteur à zéro » est désactivé avec sa raison visible (décision du 2026-10-19)

### Story 5.3 : Installer un modèle en sachant s'il tient en mémoire

As a consultant qui prépare son poste,
I want voir avant l'installation si un modèle tient en mémoire, puis suivre son téléchargement chiffré,
So that je n'installe pas un modèle inutilisable et sais quand il sera prêt.

**Gouverné par :** AD-5, AD-6, AD-14, AD-15, AD-17, AD-18, AD-20 ; AR4, AR15, AR16, AR18 ; UX-DR13, UX-DR16, UX-DR17, UX-DR27. **Reports :** B6.

**Acceptance Criteria:**

**Given** l'écran `screens/models.js` sur `#/modeles` (module Modèles passé à `available`)
**When** on l'ouvre
**Then** `wl-data-table` liste les modèles installés (nom, badge, type, paramètres totaux et actifs, taille, « tient en mémoire », débit mesuré sur ce poste) depuis `GET /api/models`, et le catalogue installable (`config/models_catalog.json`, lecture seule, moins les modèles installés : un modèle supprimé y revient) avec la mémoire nécessaire et `fits`
**And** sous 1 024 px, les colonnes Usage et Origine de « Sur ce poste » sont repliées et un bouton au-dessus du tableau les affiche (D-43)
**And** `hardware/` calcule `fits` avec la RAM libre, la VRAM (NVML) quand un GPU est présent, la mémoire des modèles déjà chargés et une marge de contexte (taille du cache KV au contexte par défaut, formule testée) ; le front ne calcule rien

**Given** `POST /api/models/pull {tag}` (écriture, `Origin` contrôlée)
**When** on clique « Installer » sur un modèle du catalogue ou un tag saisi
**Then** un run racine `pull` démarre (`409 run_busy` si un autre `pull` tourne, que l'écran rejoint), publie `pull_progress {tag, octets reçus, octets totaux, phase}` depuis `/api/pull` d'Ollama, et la ligne affiche « Téléchargement 1,2 Go sur 4,7 Go » puis « Installé »
**And** un modèle qui ne tient pas reste installable avec l'avertissement chiffré, par un bouton libellé « Installer quand même » (nom accessible « Installer <tag> quand même : il ne tient pas dans la mémoire libre »), dans le catalogue comme dans la fiche (D-42) ; l'installation est la seule action qui télécharge (AD-17) et part d'un clic

**Given** une installation en cours
**When** on l'annule, qu'Ollama s'arrête ou que le tag n'existe pas
**Then** le run finit `cancelled` ou `error` avec un code de la liste fermée (`pull_failed` ajouté à `errors.py`, message et action, `detail.tag` et `detail.cause` parmi `not_found`, `ollama_down`, `interrupted`), la liste des modèles reste inchangée, et le registre se rafraîchit en tâche de fond après un succès
**And** quitter l'écran puis revenir reprend la progression par `?after=` ; axe-core sans violation, clair et sombre

### Story 5.4 : Décharger, supprimer un modèle et choisir ses défauts

As a consultant,
I want décharger les modèles inactifs, supprimer un modèle et choisir le modèle proposé par défaut pour un usage,
So that je libère la mémoire avant une démo et retrouve mes choix d'une séance à l'autre.

**Gouverné par :** AD-9, AD-13, AD-15, AD-18, AD-20 ; AR13, AR16 ; UX-DR12, UX-DR27. **Reports :** B8 (décision Q2), B12.

**Acceptance Criteria:**

**Given** « Décharger les modèles inactifs » (`POST /api/models/unload`, livré par 4.8)
**When** on clique depuis l'écran Modèles
**Then** les modèles Ollama sans run actif sont déchargés, la colonne « chargé » et la mémoire libre se mettent à jour par le flux système

**Given** un modèle installé sans run actif
**When** on clique « Supprimer » puis confirme dans `wl-confirm-dialog` (« qwen3.5:2b sera supprimé de ce poste (2,7 Go libérés). », focus sur « Annuler ») ou appelle `DELETE /api/models/{tag}`
**Then** Ollama supprime le modèle, ses lignes `model_facts` sont purgées (le modèle ne réapparaît plus au démarrage à froid, test), et le résultat se solde par « Modèle supprimé » ; « Annuler » ne supprime rien
**And** si le modèle est un défaut choisi pour un ou plusieurs usages, le dialogue le dit avant la confirmation : « C'est le modèle par défaut pour : Agent. Ces usages reviendront à la règle automatique. » (D-41)
**And** un modèle utilisé par un run actif rend `409 model_in_use` (code ajouté à `errors.py`, `detail.tag`) avec son message et son action ; à l'écran, « Supprimer » est désactivé avec « Utilisé par une réponse en cours »

**Given** le bouton « Définir par défaut » sur l'écran Modèles (décision Q2 : choix explicite, jamais retenu sans geste)
**When** on choisit un modèle comme défaut d'un usage (`chat`, `arena`, `judge`, `agent`, `rag`) par `PUT /api/models/defaults/{purpose}` (écriture, `Origin` contrôlée)
**Then** le choix est écrit dans `preferences` (jamais dans `wavelocalai.toml`), `GET /api/models/defaults` le rend avec la raison « Choisi par vous », un modèle cloud n'est gardé qu'avec `allow_cloud`, et « Revenir au choix automatique » efface la préférence
**And** un défaut choisi puis supprimé du poste retombe sur la règle avec sa raison (test)
**And** « Changer » ouvre `wl-model-picker` filtré sur les modèles éligibles à l'usage : un modèle inéligible n'est pas proposé, plutôt que refusé à « Enregistrer » (décision du 2026-10-19)

### Story 5.5 : Récupérer le reranker depuis l'écran Modèles

As a consultante,
I want installer le reranker local d'un clic, avec sa progression,
So that la recherche documentaire reclasse les extraits sans manipulation hors de l'app.

**Gouverné par :** AD-5, AD-17, AD-21 ; AR15, AR17 ; UX-DR27. **Reports :** B19.

**Acceptance Criteria:**

**Given** l'extra `rerank` installé et le modèle absent du `cache_dir` du dossier de données
**When** l'écran Modèles s'affiche
**Then** la ligne « Reclassement des extraits » dit « Non installé » avec la raison de `GET /api/rag/settings` et un bouton « Installer le reranker »

**Given** le clic sur « Installer le reranker »
**When** le run `pull` démarre
**Then** `disable_telemetry()` précède l'import de fastembed et de huggingface_hub (test AST de 4.7), le téléchargement va dans le `cache_dir`, `pull_progress` porte `reranker` et les octets, et un `pull` de modèle en cours rend `409 run_busy`
**And** une fois installé, la recherche suivante reclasse (« Reclassement… ») sans redémarrage, et le chargement reste en `local_files_only=True`

**Given** l'extra `rerank` absent
**When** l'écran s'affiche
**Then** le bouton est désactivé avec la raison « Installez l'option de reclassement : `uv sync --extra rerank` » ; aucun téléchargement n'est tenté (test sans réseau)

### Story 5.6 : La fiche modèle explique son débit et ce qu'il donne sur d'autres postes

As a consultant face à un client qui hésite sur le matériel,
I want la fiche d'un modèle (dense ou MoE, paramètres actifs, quantification, licence, outils et raisonnement vérifiés), « Pourquoi ce débit ? » et « Sur d'autres postes »,
So that j'explique la vitesse observée et ce qu'elle serait sur un PC pro de 16 Go sans GPU.

**Gouverné par :** AD-15, AD-20, AD-22 ; AR19 ; UX-DR15, UX-DR27. **Reports :** B5.

**Acceptance Criteria:**

**Given** `models/catalog.py` qui lit `benchmarks/slm-quality/slm-quality-results.json` (modèle pydantic `extra="ignore"`, jamais par le réseau)
**When** le fichier manque ou que `schema` ne vaut pas `qb.results/1`
**Then** les références sont indisponibles avec une raison affichée, et aucune route ne dépasse 300 ms (test de budget) ; le fichier est lu une fois au démarrage et à sa modification
**And** `results[]` se joint à `models[]` sur `(model, digest)` ; un modèle installé correspond par `(tag, digest)`, à défaut par tag avec la mention « autre version » ; `ModelInfo.accuracy` est renseignée depuis ces résultats, ce qui active la règle du juge d'après la précision (1.6)

**Given** un clic sur un modèle de l'écran Modèles ou de `wl-model-picker`
**When** la fiche s'ouvre
**Then** elle montre dense ou MoE, paramètres totaux et actifs, quantification, licence, contexte, outils et raisonnement vérifiés (`/api/show` en cache `model_facts`, catalogue), avec « inconnu » pour une valeur absente, jamais 0
**And** le panneau est à droite dès 1 120 px, au-dessus de la liste en deçà, et `#/modeles/<tag>` l'ouvre directement (D-40, D-8) ; la fiche d'un modèle non installé qui ne tient pas porte « Installer quand même » (D-42)
**And** à côté de `wl-model-picker` (hors de la liste d'options), un bouton « Fiche du modèle » ouvre la même fiche en panneau sur l'écran courant, sans changer d'URL (décision du 2026-10-19)

**Given** « Pourquoi ce débit ? »
**When** on l'ouvre
**Then** il explique le débit mesuré sur ce poste par les paramètres actifs, la quantification, la bande passante mémoire et la VRAM (fiche locale, catalogue), sans calcul côté front

**Given** « Sur d'autres postes »
**When** on l'ouvre
**Then** il affiche, pour les trois postes de référence (dont le PC pro de 16 Go sans GPU), le débit et la tenue en mémoire publiés ; `null` s'affiche « inconnu », les fractions en pourcentage, `energy` seulement si `status = "measured"` (AD-22)
**And** axe-core sans violation, clair et sombre

### Story 5.7 : Les défauts `agent` et `rag` s'appuient sur le banc

As a consultant,
I want que les modèles proposés pour l'agent et la discussion documentaire suivent les mesures publiées du banc,
So that le défaut n'est pas un seuil choisi à la main mais un modèle qui réussit ces usages.

**Gouverné par :** AD-15, AD-22 ; AR19. **Reports :** B7 (décision Q7).

**Acceptance Criteria:**

**Given** les résultats `qb.results/1` lus par 5.6 et les usages qu'ils publient (appel d'outils, réponse sur documents)
**When** on recalcule les défauts `agent` et `rag`
**Then** les seuils `AGENT_MIN_PARAMS_B` et `RAG_MIN_PARAMS_B` sont remplacés ou complétés par une règle sur les scores publiés pour ces usages, écrite dans `contrat-api.md` (Défauts) par `bmad-spec`, et la raison du défaut cite la mesure (« meilleur score d'appel d'outils publié parmi les modèles qui tiennent »)
**And** sans résultat publié pour un modèle installé, la règle provisoire s'applique et la raison le dit

**Given** aucun modèle local n'atteint la règle `agent`
**When** on demande le défaut
**Then** `tags: []` et une raison qui donne les conditions, comme au MVP ; le repli de `rag` sur le défaut `chat` est gardé tant que le banc ne publie pas d'usage documentaire (décision Q7), avec un test par cas
**And** la story ne démarre qu'avec un fichier `qb.results/1` réel synchronisé sur `master` (décision Q7) ; sinon elle reste à faire après la préversion `a5`

### Story 5.8 : Quel modèle pour quel usage (préversion 2.0.0a5)

As a consultant en avant-vente,
I want une carte par usage qui dit quels modèles le banc recommande, avec intervalle et débit sur la machine de référence,
So that je réponds à « lequel prendre pour mon cas ? » sans relancer de comparaison.

**Gouverné par :** AD-3, AD-20, AD-22 ; AR19 ; UX-DR13, UX-DR24, UX-DR25.

**Acceptance Criteria:**

**Given** le sous-écran `#/arene/references` (onglet « Références » de l'Arène passé à `available`)
**When** on l'ouvre
**Then** une carte par usage publié dans `qb.results/1` montre le groupe des meilleurs (désigné par le serveur ; intervalle, sans rang inventé dans un groupe à égalité, tri par nom), le score en pourcentage de réussite avec le libellé « Part de … » en tête (D-5), le débit sur la machine de référence et la marque « installé » ou « autre version » pour les modèles du poste ; les cartes sont la vue par défaut, un segment « Cartes · Tableau » donne le tableau équivalent (D-20)
**And** références indisponibles : la raison s'affiche, sans carte vide ; Ollama arrêté : les références restent lisibles, les marques « installé » sont retirées avec un message
**And** ni bloc « Autres modèles mesurés », ni lien vers le tableau du banc, ni légende des marques (décision du 2026-10-19)

**Given** une carte d'usage
**When** on clique « Comparer ces modèles »
**Then** l'Arène s'ouvre présélectionnée sur les modèles du groupe installés sur ce poste ; sans modèle installé du groupe, le bouton est désactivé avec la raison visible (D-19)

**Given** l'Accueil
**When** les références sont disponibles
**Then** une carte « Références » (nom long « Quel modèle pour quel usage ? », D-10) affiche le meilleur score en pourcentage « Part de … » (D-5) et ouvre `#/arene/references` ; sinon elle n'apparaît pas
**And** la carte a sa propre icône Material, jamais partagée, distincte de `swords` (Arène) (décision du 2026-10-19) ; elle lit ses données en un appel au plus, après le repère `shell-ready` (AD-6 amendé)

**Given** le parcours Sobriété puis Modèles
**When** le test E2E le joue (Ollama simulé, fichier `qb.results/1` de test)
**Then** les métriques vivent sans clic, une installation simulée progresse jusqu'à « Installé », la fiche s'ouvre, et aucune requête ne sort de `127.0.0.1`
**And** axe-core sans violation sur Sobriété, Modèles et Références, clair et sombre

**Given** l'Epic 5 terminé et la suite `tests/v2` verte
**When** on publie
**Then** `version = "2.0.0a5"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.5`, release GitHub avec notes ; la recette humaine installe un vrai modèle et lit sa fiche

## Epic 6 : Confier une tâche à un agent ou à une équipe

L'utilisateur confie une tâche outillée à un agent seul, suit chaque étape en direct, valide tout email avant envoi (D2), puis lance une équipe séquentielle dont il voit le schéma, la trace par agent et le rapport. Remplace LangGraph et CrewAI par une boucle maison. Se termine par la préversion `2.0.0a6`.

### Story 6.1 : Un agent appelle des outils et publie chaque étape (serveur)

As a consultant,
I want qu'un modèle local ou cloud puisse appeler des outils en boucle et que chaque réflexion, appel et résultat soit publié,
So that l'écran montre ce que fait l'agent, étape par étape, quel que soit le fournisseur.

**Gouverné par :** AD-5, AD-6, AD-8, AD-9, AD-14 ; AR4, AR7, AR8, AR12. **Reports :** B3, B4.

**Acceptance Criteria:**

**Given** le port `ChatModel` (AD-8 : `tools` en schéma JSON neutre, messages avec appels d'outils et id d'appel, `ToolCall` dans le flux)
**When** les quatre adaptateurs reçoivent des outils
**Then** Ollama et OpenAI-compatible les passent au format OpenAI, Anthropic en `tool_use`, Mistral en son format, et chacun rend des `ToolCall(id, name, arguments)` puis accepte le résultat au tour suivant (test par adaptateur avec un faux client, trois formats couverts)
**And** `stream_into_run` ne jette plus les `ToolCall`

**Given** `POST /api/agents/runs {mode: "solo", model, tools, prompt, conversation_id?, allow_cloud}`
**When** on l'appelle
**Then** il rend `{run_id, conversation_id}` (conversation `agent` créée par le hub), le modèle passe par `registry.resolve` et chaque appel de modèle est une feuille `generation` avec son `co2`
**And** la boucle `agents/loop.py` publie `step {lane, step_id, agent, kind: think|tool_call|tool_result|answer, outil, arguments, résumé, durée}` et la réponse finale en `token`, avec un nombre de tours borné par `Settings` (borne atteinte = fin propre avec la raison)

**Given** un outil qui lève une exception ou dépasse son délai
**When** la boucle continue
**Then** l'étape `tool_result` porte l'erreur en texte, l'agent la reçoit et peut poursuivre ; l'annulation du run coupe l'appel de modèle et l'outil en cours (test avec le `fake`)
**And** le protocole d'appel d'outils et le format des étapes sont consignés dans la spine §Deferred (« Formats d'appel d'outils ») levée par `bmad-architecture`

### Story 6.2 : L'agent dispose des outils de la v1, sans chemin libre

As a consultant,
I want retrouver les outils de la v1 (Heure, Calculatrice, Recherche interne Wavestone, Analyse de données, Génération de document, Génération de graphique, Rapport Markdown, Moniteur système, Envoi d'email) avec ce qui les rend disponibles,
So that je refais les démos d'agent de la v1 sans risque pour le poste.

**Gouverné par :** AD-2, AD-4, AD-9, AD-18 ; AR21.

**Acceptance Criteria:**

**Given** `agents/tools/` (fonctions `_*_impl` de `src/core/agent_tools.py` copiées, sans `@tool`, un schéma JSON par outil)
**When** on appelle `GET /api/agents/tools`
**Then** chaque outil rend `id`, libellé du lexique, description, `available`, raison et `sensitive` ; « Envoi d'email » est `sensitive` et, sans SMTP configuré dans `Settings`, indisponible avec « Configuration SMTP absente : renseignez … dans le fichier .env »
**And** aucun `os.getenv` hors de `config.py` (variables SMTP lues par `Settings`)

**Given** un outil qui lit ou écrit un fichier
**When** l'agent lui passe un chemin
**Then** le chemin est confiné au dossier de travail des agents dans le dossier de données (`_validate_path` copié) ; une traversée (`..`, chemin absolu) est refusée en `tool_result` d'erreur (test)
**And** les fichiers produits sont servis par `GET /api/outputs/{name}` (nom validé, `Content-Disposition`), référencés par `artifact_url` dans l'étape

**Given** la calculatrice et l'analyse de données
**When** l'agent les appelle
**Then** l'expression passe par l'évaluateur sûr de la v1 (`_calculate_safe`) et l'analyse lit un CSV du dossier de travail sans pandas si possible (`csv` standard), avec les mêmes résultats que la v1 sur un jeu de test

### Story 6.3 : Aucun email ne part sans validation explicite

As a consultant,
I want que l'agent prépare l'email et attende ma décision, avec destinataire, objet et corps sous les yeux,
So that rien ne quitte le poste sans mon accord (D2).

**Gouverné par :** AD-5, AD-6, AD-9, AD-15, AD-18 ; AR8. **Reports :** B1, B2.

**Acceptance Criteria:**

**Given** un appel de l'outil sensible « Envoi d'email »
**When** l'agent le demande
**Then** le hub crée une approbation, publie `approval_required {approval_id, kind: "email", destinataire, objet, corps}` et passe le run en `awaiting_approval` (nouvelle transition du hub, testée), qui garde sa place de `kind`
**And** l'email n'est pas envoyé tant que `approval_resolved {decision: "approved"}` n'est pas publié

**Given** `POST /api/runs/{id}/approvals/{approval_id} {decision}` (écriture, `Origin` contrôlée)
**When** on approuve, refuse, ou ne répond pas dans `approval_expiry_s` (`Settings`, 600 s, valeur confirmée par la story)
**Then** `approval_resolved` porte `approved`, `rejected` ou `expired` ; seul `approved` envoie, `rejected` et `expired` rendent à l'agent un refus qu'il peut annoncer ; annuler le run vaut refus
**And** aucun chemin d'approbation automatique n'existe hors de l'adaptateur `fake` (test qui cherche toute approbation sans requête)

**Given** un redémarrage du serveur pendant l'attente
**When** le serveur repart
**Then** le run passe à `interrupted` et l'email n'est jamais envoyé

### Story 6.4 : L'écran Agent seul montre chaque étape et demande la validation

As a consultant en démo,
I want suivre l'agent étape par étape, déplier une étape pendant que les suivantes arrivent et valider l'email dans un dialogue,
So that la salle voit le raisonnement outillé et que je garde la main sur ce qui part.

**Gouverné par :** AD-6, AD-9, AD-20 ; AR18 ; UX-DR8, UX-DR10, UX-DR12, UX-DR16, UX-DR17, UX-DR28. **Reports :** B14, B15.

**Acceptance Criteria:**

**Given** l'écran `screens/agents-solo.js` sur `#/agents/seul` (module Agents passé à `available`, onglet « Équipe d'agents » désactivé avec sa raison)
**When** on l'ouvre
**Then** `wl-model-picker` est sur le défaut `agent` avec sa raison (sans défaut : la raison et un choix demandé, lancement désactivé), les neuf outils sont visibles en interrupteurs en bascule (D-6), tous activés sauf « Envoi d'email », un outil indisponible est non activable (`aria-disabled`, focalisable) avec son aide, et l'accueil dit « Bonjour ! L'agent est prêt. » avec des actions rapides
**And** un modèle choisi sans outils vérifiés affiche l'avertissement « Ce modèle n'a pas d'outils vérifiés : l'agent risque de mal appeler ses outils. Préférez un modèle marqué « Outils vérifiés ». » et le lancement reste permis (D-32)
**And** le panneau « Étapes » est à droite dès 1 024 px ; en deçà, sous la réponse et toujours déplié, sans bouton de repli (D-30)
**And** le `h1` de l'écran est « Agent seul » (décision du 2026-10-19)

**Given** une tâche lancée
**When** les `step` arrivent
**Then** `wl-step-trace` (liste ordonnée, motif APG) ajoute chaque étape avec icône, libellé, durée et agent ; on peut en déplier une pendant que les suivantes arrivent sans perdre le focus ; `wl-run-status` dit « Réflexion… », « Appel de l'outil <libellé>… », « En attente de votre validation », « Génération… »
**And** la réponse finale arrive en flux dans `wl-chat-thread` avec un pied réduit (badge, CO₂, nombre d'étapes, durée ; ni débit, ni tokens, ni chargement, D-31), suivi de « Télécharger » (route d'export du serveur, sans `blob:`), et un Markdown rendu sans astérisques visibles (test sur une réponse réelle de la v1 : gras, séparateur, italique)

**Given** `approval_required`
**When** il arrive
**Then** l'étape passe à « En attente de votre validation » et `wl-confirm-dialog` montre destinataire, objet et corps, focus sur « Annuler » ; « Envoyer l'email » approuve, « Annuler » refuse, et le résultat se solde par un message au même verbe

**Given** un modèle local dont le besoin dépasse la mémoire libre
**When** on lance la tâche
**Then** le garde-fou `ram_guard` de 4.8 s'applique (question gardée, besoin chiffré, deux actions), sans bouton « Libérer la mémoire » de la v1
**And** quitter et revenir reprend la trace par `?after=` ; axe-core sans violation, clair et sombre

### Story 6.5 : Une équipe d'agents mène une mission l'un après l'autre (serveur)

As a consultant,
I want lancer une équipe d'agents (chercheur, analyste, rédacteur…) sur un sujet, chacun avec ses outils, et l'arrêter quand je veux,
So that je montre une collaboration d'agents sans CrewAI, avec un rapport conservé.

**Gouverné par :** AD-5, AD-6, AD-9, AD-14 ; AR4, AR21. **Reports :** B4 (protocole d'équipe), décision Q3.

**Acceptance Criteria:**

**Given** la bibliothèque d'équipes (décision Q3 : équipes de la v1 dans un fichier versionné en lecture seule, modifications de l'utilisateur dans `preferences`, « Revenir à l'équipe d'origine » efface la modification)
**When** on appelle `GET /api/agents/crews` et `POST /api/agents/crews/validate`
**Then** chaque équipe rend ses agents (rôle, objectif, outils, modèle) et ses tâches ordonnées ; `validate` rejette une équipe sans agent, de plus de 5 agents (D-36), un outil inconnu ou un modèle cloud sans `allow_cloud`, avec un message par champ

**Given** `POST /api/agents/runs {mode: "crew", crew, topic, allow_cloud}`
**When** la mission s'exécute
**Then** un run racine `agent` enchaîne les agents en séquence (la sortie d'un agent est l'entrée du suivant), chaque agent réutilise la boucle de 6.1 et publie ses `step` avec `agent` renseigné, et chaque appel de modèle est une feuille avec son `co2`
**And** l'étape `answer` qui clôt un agent porte `agent_totals {tools, duration_s}` (ligne « Terminé · 3 outils · 41 s », D-34) ; un agent que la mission n'atteint pas (arrêt, erreur) ne publie aucune étape, ce que l'écran affiche « Non lancé »
**And** un outil sensible dans une équipe suit l'approbation de 6.3 (aucun email sans validation)

**Given** une mission en cours
**When** on l'annule
**Then** l'agent courant s'arrête, le rapport partiel est gardé et marqué « Arrêté » ; une mission terminée garde son rapport final dans `messages`, rouvrable
**And** le pic de mémoire de la mission et sa durée sont dans l'instantané `GET /api/runs/{id}`

### Story 6.6 : L'écran Équipe d'agents montre le schéma, la trace et le rapport (préversion 2.0.0a6)

As a consultant,
I want voir le schéma de l'équipe, l'agent en cours, la trace par agent et le rapport à télécharger,
So that la mission se lit d'un coup d'œil et laisse une trace, à parité avec la v1.

**Gouverné par :** AD-3, AD-6, AD-20 ; AR18 ; UX-DR13, UX-DR14, UX-DR17, UX-DR25, UX-DR28.

**Acceptance Criteria:**

**Given** l'écran `screens/agents-crew.js` sur `#/agents/equipe` (onglet passé à `available`)
**When** on charge une équipe
**Then** un schéma SVG fait main relie les agents puis le rapport (`<title>`, `<desc>`), horizontal dès 768 px jusqu'à 4 agents, vertical en deçà ou à 5 agents ; l'agent actif est marqué par un contour et le libellé « en cours », jamais par la couleur seule ; « Configurer » ouvre un volet **non modal** qui laisse le schéma visible (colonne de droite dès 1 024 px, sous le schéma en deçà, D-35) avec les agents (rôle, objectif, outils en interrupteurs, modèle) et enregistre la modification dans `preferences` (décision Q3) ; sans agent, « Lancer la mission » est désactivé avec « Ajoutez au moins un agent »
**And** à 5 agents, « Ajouter un agent » est désactivé avec la raison visible, reliée au bouton : « Une équipe compte 5 agents au plus : retirez un agent pour en ajouter un autre. » (D-36)

**Given** une mission lancée
**When** les `step` arrivent
**Then** une ligne par agent dit son statut (En attente, En cours avec l'étape, Terminé avec outils et durée lus dans `agent_totals`, Arrêté, Non lancé pour un agent que la mission n'a pas atteint, D-34) et se déplie sur sa trace ; le journal brut est replié, en lignes horaires lisibles, jamais en JSON (D-33) ; Arrêter (et Échap) annule
**And** une mission terminée ou arrêtée se rouvre par `#/agents/equipe/<run_id>` (route passée à `available`, D-8) ; un identifiant inconnu affiche `run_not_found`
**And** à la fin du run, l'adresse est réécrite vers `#/agents/equipe/<run_id>` (`history.replaceState`), comme à l'Arène ; le `h1` de l'écran est « Équipe d'agents » (décision du 2026-10-19)
**And** le rapport s'affiche avec son pied (badge, CO₂, pic de mémoire, durée, Télécharger en Markdown par la route d'export, sans `blob:`)

**Given** l'agent seul et l'équipe de la v1
**When** on compare les parcours
**Then** la liste de parité (outils, validation d'email, garde-fou, équipe chargée, configurée, lancée, arrêtée, rapport conservé) est cochée dans la story, chaque écart nommé
**And** les E2E jouent un agent seul avec un email approuvé puis refusé et une mission arrêtée en cours (modèles `fake`), axe-core sans violation, clair et sombre

**Given** l'Epic 6 terminé et la suite `tests/v2` verte
**When** on publie
**Then** `version = "2.0.0a6"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.6`, release GitHub avec notes ; la recette humaine joue un agent seul avec un vrai email de test et une mission d'équipe

## Epic 7 : Évaluer la qualité d'une réponse documentaire

L'utilisateur mesure la fidélité et la pertinence des réponses de plusieurs modèles sur ses documents, avec un verdict par affirmation, et vérifie au Banc d'essai qu'un modèle respecte un format attendu. Remplace Ragas par un juge maison. **Prérequis :** relecture par Anaël des verdicts du jeu fixe (story 7.2, décision Q4). Se termine par la préversion `2.0.0a7`.

### Story 7.1 : Noter la fidélité et la pertinence d'une réponse (serveur)

As a consultante,
I want que chaque réponse soit découpée en affirmations vérifiées une à une contre les extraits, et que sa pertinence soit mesurée,
So that je sais si un modèle invente, affirmation par affirmation.

**Gouverné par :** AD-5, AD-6, AD-8 (`response_schema`), AD-9, AD-10, AD-12, AD-13, AD-14 ; AR4, AR7, AR10, AR11.

**Acceptance Criteria:**

**Given** une nouvelle migration qui crée `evaluations` (run, métrique, score, verdicts par affirmation en JSON) et le test d'instantané de schéma à jour
**When** `POST /api/rag/eval/runs {questions, models, judge, allow_cloud}` est appelé
**Then** un run racine `eval` cherche une fois les extraits communs (feuille `embedding`), fait répondre chaque modèle sur ces mêmes extraits (une lane et une feuille `generation` par modèle), puis note (feuilles `judge`) ; locaux en séquence, cloud en parallèle (AD-14)

**Given** une réponse et ses extraits
**When** le juge évalue la fidélité
**Then** les affirmations sont extraites puis vérifiées une à une par sortie structurée (`response_schema`), chacune avec son verdict (« appuyée », « non appuyée », « contredite ») et l'extrait qui l'appuie ; le score /100 est la part d'affirmations appuyées
**And** la pertinence génère des questions depuis la réponse et prend le cosinus moyen avec la question, par l'`Embedder` de la base (AD-16) ; la précision du contexte note les extraits utiles

**Given** le flux
**When** chaque métrique est prête
**Then** `eval_metric {lane, métrique, score|null, raison, verdicts}` est publié au fil de l'eau ; juge indisponible, sortie invalide ou réponse vide donnent `score: null` et `not_evaluated` avec la raison, jamais 0
**And** pour un jeu de questions, `eval_metric` porte de quoi afficher « sur 8 questions (1 non évaluée) » et le détail par question (noms de champs fixés par la story et consignés dans `contrat-api.md`)
**And** effacer l'évaluation supprime ses `evaluations` et `run_events` et garde ses `runs` (AD-13)

**Given** une évaluation annulée ou interrompue par un redémarrage (D-28, correct course)
**When** le run se termine `cancelled` ou `interrupted`
**Then** les métriques déjà notées restent dans `evaluations`, l'instantané `GET /api/runs/{id}` porte `partial: true`, et les métriques non notées sont « non évaluées (évaluation arrêtée) », jamais 0 (test)

### Story 7.2 : Un jeu fixe de cas garde le juge honnête

As a mainteneur,
I want un jeu fixe de questions, de réponses et de verdicts attendus, rejoué à chaque changement du juge,
So that une régression de la notation se voit avant d'arriver en démo.

**Gouverné par :** AD-8, NFR12, NFR13 ; décision Q4.

**Acceptance Criteria:**

**Given** le jeu fixe (décision Q4 : une dizaine de cas en français tirés d'un document du domaine public, verdicts produits par un modèle cloud fort puis relus et corrigés par Anaël, la relecture consignée dans la story) dans `tests/v2/fixtures/eval/`, sans document client (dépôt public)
**When** le test de non-régression tourne avec le `fake` (sorties de juge enregistrées)
**Then** les scores et verdicts calculés égalent les attendus ; une modification de l'invite ou du découpage qui change un verdict fait échouer le test

**Given** un vrai juge local (test `integration`)
**When** le jeu est rejoué
**Then** l'accord avec les verdicts annotés est mesuré et consigné (part de verdicts identiques), avec un seuil minimal fixé par la story après une première mesure

### Story 7.3 : L'écran Évaluation de la qualité montre les étapes et garde le résultat

As a consultante en atelier,
I want lancer une évaluation sur une question ou un jeu de questions et voir les étapes, puis les scores et les verdicts arriver,
So that je compare la fiabilité des modèles sur mes documents et retrouve le résultat plus tard.

**Gouverné par :** AD-6, AD-7, AD-20 ; AR18 ; UX-DR11, UX-DR13, UX-DR14, UX-DR17, UX-DR29.

**Acceptance Criteria:**

**Given** l'écran `screens/documents-eval.js` sur `#/documents/evaluation` (onglet passé à `available`)
**When** on l'ouvre
**Then** il propose Question ou Jeu de questions, `wl-model-picker` en mode multi présélectionné sur le défaut `arena` (les trois petits modèles locaux de l'Arène, D-27), le juge sur le défaut `judge` avec sa raison et l'avertissement « note peu fiable » sous ~4B actifs, et la phrase « Les mêmes extraits sont fournis à tous les modèles. »
**And** question vide : « Lancer l'évaluation » est désactivé avec la raison visible « Saisissez une question » (D-29)
**And** 4 modèles évalués au plus : au-delà, lancement désactivé avec « Choisissez 4 modèles au plus » ; le serveur refuse plus de 4 modèles en `422 invalid_request` (décision du 2026-10-19)

**Given** une évaluation lancée
**When** les événements arrivent
**Then** trois étapes nommées avancent (« Recherche des extraits communs » avec « Voir les extraits », « Réponses » par modèle, « Notation : fidélité · pertinence · précision ») et le tableau se remplit (/100, débit, CO₂) ; une ligne « non évalué » dit sa raison, sans 0
**And** chaque métrique a sa définition en une phrase en aide, la méthode « inspirée de Ragas » est citée en aide seulement ; chaque score se déplie sur ses verdicts par affirmation, avec l'extrait d'appui

**Given** une évaluation terminée
**When** on revient sur l'écran ou ouvre son URL `#/documents/evaluation/<run_id>`
**Then** le résultat se reconstruit depuis la base sans relancer de modèle ; « Matrice » et « Tableau » sont proposés comme dans l'Arène, sans colonne « Global » (décision du 2026-10-19)
**And** l'écran liste les évaluations passées (les plus récentes d'abord, comme l'historique de l'Arène), chacune rouvrable par son adresse (décision du 2026-10-19)
**And** un résultat partiel (instantané `partial: true`) se rouvre titré « Résultat partiel conservé », ses cellules non notées en « non évalué (évaluation arrêtée) » (D-28) ; un identifiant inconnu affiche `run_not_found`
**And** axe-core sans violation, clair et sombre

### Story 7.4 : Le Banc d'essai dit si la sortie respecte le format (préversion 2.0.0a7)

As a consultant,
I want lancer un scénario prédéfini et savoir si le modèle a respecté le format attendu, avec ou sans format imposé et réponse concise,
So that je montre qu'un petit modèle sait produire un JSON exploitable.

**Gouverné par :** AD-3, AD-5, AD-8 (`response_schema`), AD-20 ; AR7, AR18 ; UX-DR13, UX-DR17, UX-DR25, UX-DR29.

**Acceptance Criteria:**

**Given** le registre des modèles
**When** `GET /api/models` rend un modèle
**Then** il porte le champ `structured_output` (booléen : le modèle peut imposer un format de sortie), consigné dans `contrat-api.md` ; un modèle qui ne le peut pas rend « Format imposé » désactivé avec sa raison (décision du 2026-10-19)

**Given** `GET /api/scenarios`
**When** on l'appelle
**Then** il rend les scénarios de la v1 (`USE_CASES` de `lab.py`, consignes séparées du format) avec leur consigne système (`instruction`, D-18) et leur format attendu en schéma JSON, ou `null` pour un scénario sans format (D-17)

**Given** `POST /api/bench/runs {scenario, model, input, force_format, concise, allow_cloud}`
**When** le run `bench` se termine
**Then** le serveur dit si la sortie respecte le schéma (« Format respecté » ou la première violation en clair) dans l'instantané `GET /api/runs/{id}` (`format_verdict`, absent pour un scénario sans format) ; `force_format` passe le schéma par `response_schema` (`format` d'Ollama), `concise` ajoute la consigne de réponse concise ; débit D3, CO₂ et durée accompagnent le résultat

**Given** l'écran `screens/bench.js` sur `#/arene/banc` (onglet passé à `available`)
**When** on lance un scénario
**Then** la réponse arrive en flux, le verdict de format s'affiche à `run_ended` avec la sortie mise en forme, et les interrupteurs en bascule (D-6) « Format imposé » et « Réponse concise » ont leur aide ; le résultat est conservé et rouvrable par `#/arene/banc/<run_id>` (identifiant inconnu : `run_not_found`)
**And** la consigne système du scénario est dans un bloc « Consigne » replié (D-18) ; un scénario sans format n'a pas de « Format attendu », « Format imposé » est désactivé avec la raison visible, et aucun verdict n'est affiché (D-17)
**And** un délai dépassé affiche « Délai dépassé (120 s) », le délai réel cité ; axe-core sans violation, clair et sombre
**And** à la fin, « Relancer le test » et « Modifier le test » (comme « Relancer » et « Modifier la question » de l'Arène), et l'écran liste les tests passés, chacun rouvrable par son adresse (décision du 2026-10-19)

**Given** les parcours Évaluation et Banc d'essai
**When** les E2E les jouent (`fake`, base de test en dossier temporaire)
**Then** les scores arrivent au fil de l'eau, un « non évalué » garde sa raison, un format violé est signalé ; aucune requête ne sort de `127.0.0.1`

**Given** l'Epic 7 terminé et la suite `tests/v2` verte
**When** on publie
**Then** `version = "2.0.0a7"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0-alpha.7`, release GitHub avec notes ; la recette humaine évalue deux modèles sur un vrai document

## Epic 8 : Remplacer la v1

La v2 devient l'application : dette technique soldée, accessibilité complète vérifiée, parité avec la v1 listée page par page, v1 archivée, `2.0.0` publiée. Décisions Q5 et Q6 appliquées par 8.3 et 8.4.

### Story 8.1 : Solder la dette technique relevée pendant le MVP

As a mainteneur,
I want corriger les angles morts des garde-fous et les cas d'arrêt relevés aux revues du MVP,
So that les tests qui protègent la v2 ne laissent rien passer avant la bascule.

**Gouverné par :** AD-4, AD-12, AD-15, AD-18, AD-23 ; AR3, AR20. **Reports :** C1 à C9.

**Acceptance Criteria:**

**Given** `tests/v2/unit/test_layers.py`
**When** un module importe un composant par `import wavelocalai` puis accès d'attribut, par `importlib.import_module` ou par `__import__`
**Then** le test relève la violation (modules pièges ajoutés) (C1)

**Given** le test de budget de lecture
**When** une route `GET` est posée avec `include_in_schema=False` dans un routeur inclus, ou sert des fichiers par `Mount`
**Then** elle est découverte et mesurée, sans dépendre d'une classe interne de FastAPI (C2, C3)
**And** un test vérifie qu'aucune route ne prend de texte saisi dans son chemin ou sa requête, pour que `uvicorn.access` n'en journalise jamais (C4)

**Given** le lanceur
**When** le verrou échoue pour une autre raison qu'un serveur vivant (droits, disque), ou qu'on lance un second serveur
**Then** le message dit la vraie cause, et le second lancement n'écrit rien dans le journal du serveur vivant (`setup_logging` après le verrou) (C5)
**And** sous Windows, Ctrl+Break ferme le store et relâche le verrou (test en sous-processus) (C7)

**Given** l'échec de la transaction de clôture d'un run (disque plein simulé)
**When** l'exception remonte
**Then** la racine est purgée de la mémoire du hub, l'erreur est journalisée, sa place de `kind` est libérée, et le run passe à `interrupted` au démarrage suivant (C6)

**Given** le panneau Ollama de la barre haute
**When** on clique « Réessayer »
**Then** une sonde est forcée sans attendre l'échéance du cache (route d'écriture ou paramètre, sous le budget de 300 ms), et l'état s'affiche aussitôt (C8)
**And** les textes de `ollama_down` n'ont qu'une source : le front les lit de l'API ou d'un catalogue généré depuis `errors.py`, le test miroir disparaît (C9)

Ajouts du 2026-10-19 (décisions d'Anaël, écarts du §7(d) de `sprint-change-proposal-2026-10-19.md` sur le code livré) :

**Given** un `timeout` dans l'Arène, le Banc ou le chat
**When** le message s'affiche
**Then** il cite le délai (« Délai dépassé (120 s) »), partout (écart n° 1)

**Given** l'Arène livrée
**When** un run tourne puis se termine
**Then** le chronomètre est au format « 0:42 » (UX-DR20, écart n° 4) ; « un seul juge » s'affiche toujours avec les notes (écart n° 5) ; à la fin, l'adresse est réécrite vers `…/<run_id>` par `history.replaceState` (écart n° 7) ; chaque point est corrigé seulement si l'existant diffère, avec un E2E

**Given** la Discussion avec un modèle cloud
**When** on l'utilise
**Then** l'avertissement « les extraits de vos documents lui sont envoyés » s'affiche (AD-9, écart n° 12)
**And** avec la stratégie vérifiée (Self-RAG) et un modèle de moins de ~3 B paramètres actifs, l'avertissement « vérification peu fiable » s'affiche, comme pour le juge de l'Arène

**Given** un import en cours dans la Base documentaire
**When** l'écran s'affiche
**Then** « Supprimer » et « Vider » sont désactivés avec leur raison visible au lieu d'afficher le `409` ; le `409 base_in_use` reste côté serveur (écart n° 13)

**Given** les copies `.db.bak-N` laissées par les migrations
**When** une migration réussit, puis qu'un effacement (AD-13) a lieu
**Then** une seule copie est gardée et elle est supprimée après la migration suivante réussie ; un effacement purge aussi le texte de la copie ou la supprime (test)

**Given** `components/wl-model-picker.js` (666 lignes)
**When** la story 5.0 ne l'a pas déjà fait
**Then** il passe sous 600 lignes

**Given** le sprite d'icônes
**When** Anaël a fourni le fichier officiel Material Symbols Rounded (aucun téléchargement par un agent)
**Then** `icons.svg` en reprend le sous-ensemble utilisé, avec sa licence (D-2)

### Story 8.2 : Tous les écrans sont accessibles et lisibles en projection

As a consultant qui présente à un public varié,
I want que chaque écran passe axe-core, la grille RGAA 4.1, le zoom à 200 % et 320 px de large, et soit lisible au vidéoprojecteur,
So that la v2 remplace la v1 sans exclure personne.

**Gouverné par :** AD-20 ; NFR8 ; UX-DR2, UX-DR19, UX-DR25. **Reports :** B16.

**Acceptance Criteria:**

**Given** toutes les routes du registre (UX-DR4, routes de la maquette comprises), toutes `available`
**When** les E2E d'accessibilité tournent
**Then** axe-core ne relève aucune violation, sans exclusion, sur chaque écran en clair, en sombre (thème « Système » compris, qui applique l'un ou l'autre) et en mode projection, panneaux et dialogues ouverts compris
**And** aucun défilement horizontal à 320 px CSS et à 200 % de zoom (hors tableaux larges qui défilent dans leur conteneur)

**Given** la grille RGAA 4.1
**When** l'audit manuel est fait (clavier seul, lecteur d'écran NVDA)
**Then** `docs/accessibilite/grille-rgaa-v2.md` liste chaque critère applicable (conforme, non conforme avec correctif, non applicable) ; le focus au premier chargement (B16) y est tranché et appliqué
**And** les non-conformités trouvées sont corrigées dans la story ou listées avec leur story de correctif

**Given** le mode projection
**When** la recette humaine l'essaie sur un vidéoprojecteur réel
**Then** Flow 1 se lit du fond de la salle ; les écarts relevés sont corrigés ou consignés

### Story 8.3 : La parité avec la v1 est listée et la suite E2E est complète

As a mainteneur,
I want une liste de parité page par page et une suite E2E qui joue tous les parcours,
So that l'archivage de la v1 ne perd aucune fonction sans le dire.

**Gouverné par :** NFR13, NFR14 ; décision Q6. **Reports :** B21.

**Acceptance Criteria:**

**Given** les pages et onglets de la v1 (03 §1.1)
**When** la liste de parité est écrite dans `docs/parite-v1-v2.md`
**Then** chaque fonction de la v1 est marquée « reprise », « remplacée par » (avec l'écran) ou « abandonnée » (avec le motif), et aucune n'est sans statut

**Given** la suite `tests/v2/e2e`
**When** on la lance
**Then** elle joue Flow 1, Flow 2, Sobriété et Modèles, Agents et Évaluation et Banc d'essai sans recharger la page, et vérifie qu'aucune requête ne sort de `127.0.0.1`
**And** elle tourne dans un job CI Linux nocturne (Chromium de Playwright installé par la CI) et en local sur Edge par `WAVELOCALAI_E2E_CHROMIUM`, mode d'emploi dans `AGENTS.md` ; les PR n'attendent pas ce job (décision Q6)

**Given** le README
**When** la story se termine
**Then** les captures et le GIF du README montrent la v2 (sans données réelles indexées, dépôt public), et le README décrit l'installation par `uv sync` et le lanceur

### Story 8.4 : La v2 remplace la v1 (2.0.0)

As a utilisateur de wavelocalai,
I want lancer `wavelocalai` et obtenir la v2,
So that il n'existe plus qu'une application à installer et à maintenir.

**Gouverné par :** AD-1, AD-2, AD-3 ; AR1, AR22, AR23 ; décision Q5. **Reports :** B17, B18.

**Acceptance Criteria:**

**Given** la décision Q5 : `src/app`, `src/core`, les tests v1 (`tests/unit`, `tests/app`, `tests/integration`) et les scripts qui importent `src.core` retirés de `master`, la v1 conservée par son dernier tag `v1.3.x` cité dans le README
**When** on bascule
**Then** le script `wavelocalai` lance la v2 (`wavelocalai.__main__:main`), `wavelocalai-v2` disparaît, `packages` passe à `src/wavelocalai`, `dev-mode-dirs` est retiré, et une installation non éditable (`uv build` puis installation de la roue dans un venv propre) lance le serveur
**And** les dépendances de la v1 (Streamlit, LangChain, LangGraph, CrewAI, Ragas, Chroma, torch…) sortent du `pyproject.toml`, `uv.lock` est régénéré, et la taille du `.venv` est mesurée et consignée

**Given** pydantic contraint sous 2.13 par crewai
**When** crewai est retiré
**Then** pydantic passe à la dernière version vérifiée sur PyPI et par installation réelle, la spine §Stack est mise à jour par `bmad-architecture`, et `tests/v2` reste vert
**And** la borne haute de Python est relevée si 3.13 est vérifiée par la CI, sinon gardée avec la raison (spine §Deferred)

**Given** la CI, `requirements.txt`, `constraints.txt` et `AGENTS.md`
**When** la bascule est faite
**Then** le job v1 disparaît, le job v2 devient le seul, `requirements.txt` et `constraints.txt` (chemin pip de la v1) sont retirés, l'installation passant par `uv sync` seul (Q5), et `AGENTS.md` décrit la seule application (lanceur, port, tests)
**And** les scripts qui importent `src.core` (`benchmark_slm.py`, `audit_and_update.py`, `setup_models.py`, `setup_rag_models.py`) sont retirés avec la v1, les règles d'`AGENTS.md` sur `benchmark_slm.py` aussi (Q5) ; `scripts/sync_slm_results.py` et `scripts/build_catalog.py` restent fonctionnels

**Given** la suite complète verte et la recette humaine de Flow 1 et Flow 2 sur un PC pro de 16 Go sans GPU installé par `uv sync` seul
**When** on publie
**Then** `version = "2.0.0"` dans `pyproject.toml`, `uv.lock` et `CITATION.cff`, tag annoté `v2.0.0`, release GitHub avec notes ; le topic GitHub du projet passe à `status-deployed`

## À ajouter aux stories du MVP

Critères proposés pour les stories 2.x à 4.x, tirés des reports (a) de `reports-v2-inventaire.md`. Le run autonome du MVP les implémente en ce moment : il décide de les intégrer à la story concernée avant son développement, ou de les laisser à la story 8.1. Les éléments (a) déjà couverts par un critère existant (A2, A3, A5 à A9, A11, A12, A15, A17, A22, A23, A27, A31) ne sont pas répétés.

| Story | Critère proposé | Report |
|---|---|---|
| 2.1 | **Given** un service qui publie un `token` **When** il appelle `hub.publish("token", …)` **Then** le hub refuse (seul `publish_token` émet ce type, groupé par 50 ms et par `lane`), test | A10 |
| 2.1 | **Given** une génération coupée puis relancée **When** la seconde tentative aboutit **Then** la tentative coupée est une feuille close avec son `co2`, comptée dans le CO₂ de session | A28 |
| 2.1 | **Given** Ollama rendu au run **When** la story se termine **Then** `pytest tests/v2 -m integration` (Epic 1 compris) est rejoué et son résultat consigné dans la story | A16 |
| 2.2 | **Given** un panneau de la barre haute ouvert pendant une génération **When** on appuie sur Échap **Then** seul le panneau se ferme (`preventDefault`), le run continue (E2E) | A24 |
| 2.2 | **Given** une erreur dont l'action contient du balisage (`no_model` : « `ollama pull …` ») **When** `wl-error` l'affiche **Then** aucun accent grave ni astérisque n'est visible, pour tous les codes (test sur le catalogue d'`errors.py`) | A25 |
| 2.2 | **Given** un événement `retry` **When** la seconde tentative démarre **Then** le partiel est remplacé et la relance annoncée (« Nouvelle tentative… »), E2E avec le `fake` | A29 |
| 2.2 | **Given** le premier bouton plein de la v2 (« Envoyer ») **When** axe-core tourne en sombre **Then** zéro violation : le fond du bouton plein en sombre utilise le nouveau jeton de `DESIGN.md` posé par la mise à jour `bmad-ux` (décision Q1), repris dans `tokens.css` et son test de dérive. **Prérequis de 2.2** | A19 |
| 2.4 | **Given** chaque identifiant de `[cloud.models]` **When** la recette fait un premier appel réel **Then** il est accepté par le fournisseur ; un identifiant refusé donne un code de la liste fermée, jamais `internal` | A14 |
| 2.5 | **Given** `[cloud.groq_ecologits]` **When** le test de contrat d'ecologits tourne **Then** chaque entrée est confirmée ou corrigée contre la version installée | A13 |
| 2.6 | **Given** « Télécharger (JSON, Markdown) » **When** on clique **Then** le navigateur suit la route d'export (`Content-Disposition: attachment`), sans `blob:` ni élargissement de la politique de contenu | A20 |
| 3.1 | **Given** `lane_timeout_s` de `wavelocalai.toml` **When** une lane dépasse le délai **Then** la valeur est lue dans `Settings` et confirmée ou corrigée par la story (300 s provisoires) | A4 |
| 3.6 | **Given** l'export de preuve **When** Ollama est joignable **Then** la version d'Ollama vient de l'état en cache de la sonde et n'est jamais `null` | A18 |
| 3.6 | **Given** `#/arene/comparer/<a>` puis `<b>` pendant un `mount` asynchrone **When** les deux `mount` se chevauchent **Then** seul `<b>` est monté (E2E) | A21 |
| 3.6 | **Given** Ollama démarré sans aucun modèle de conversation **When** l'Accueil s'affiche **Then** la carte « Démo recommandée » dit « Aucun modèle local disponible » et mène à l'installation | A26 |
| 3.6 | **Given** l'export CSV ou Markdown de l'Arène **When** on le télécharge **Then** même règle que 2.6 (route serveur, sans `blob:`) | A20 |
| 4.1 | **Given** `uv sync` **When** la story ajoute sqlite-vec **Then** la version de la spine §Stack est vérifiée par installation réelle et verrouillée dans `uv.lock` | A1 |
| 4.8 | **Given** un modèle `origin != "local"` **When** on lance une inférence **Then** le garde-fou mémoire ne s'applique pas (test) | A30 |
