# Audit du code de l'ancien dépôt `wave_local_ai_v2`

- **Date :** 2026-10-18
- **Dépôt analysé :** `Aliquanto3/wave_local_ai_v2`, clone en lecture seule. `main` au commit `c68b23e` (2026-10-02) et `origin/feat/night-run-2026-10-02` au commit `d28c8a7` (2026-10-04).
- **Méthode :** lecture du code, des tests, de la CI et du journal de la branche de nuit. Rien n'a été exécuté, installé ni lancé. Les chiffres de tests et de couverture des branches viennent des journaux du dépôt (`run-log.md`) et d'un comptage des fonctions `def test_` : ils n'ont pas été rejoués.
- **Hors périmètre :** les spécifications et le backlog (autre auditeur).

## Résumé

1. **Ce n'est pas une v2 de l'application.** C'est un banc de mesure publiable : llama.cpp seul, deux juges cloud (Mistral, Google), des lignes JSONL signées par une fiche matérielle, un tableau de bord de lecture. Il n'y a ni chat, ni Arène, ni RAG, ni agents, ni Ollama. Rien de ce que `wavelocalai` v1 montre à l'écran n'y existe.
2. **Le code est dense et très testé** : 24 080 lignes de Python, 28 740 lignes de tests, couverture imposée à 95 % (98,1 % mesurée sur `main`). Il est aussi hors de proportion avec la preuve produite : 80 lignes de qualité et 2 de runtime publiées sur `main`.
3. **Le front est un lecteur de tables.** React 19, Vite, TypeScript, 8 écrans, aucun graphique, aucun routeur, aucune icône, une seule feuille de 116 lignes, en anglais, hors charte (accent `#6c2bd9`).
4. **À reprendre : des idées et quelques modules de mesure, pas des écrans.** Le plus utile est la discipline « jamais de zéro à la place d'une absence » (`Absent`), la fiche matérielle hachée, le verdict à trois états, les intervalles par bootstrap et l'accord entre juges. Le tout relève surtout de `slm-quality-bench`.
5. **L'avancement décevant se lit dans le code** : un seul développeur et ses agents, 336 commits en six semaines, 112 stories et 596 fichiers de documentation (45 880 lignes) pour 24 080 lignes de code, des abstractions de registre pour des cas qui n'existent pas (un seul moteur, un seul harnais implémenté), et une branche de 125 commits jamais fusionnée.

---

## 1. Ce qui existe

### 1.1 Back (`src/wave_local_ai_v2/`)

Un paquet plat de 60 modules (aucun sous-paquet), `requests` synchrone, aucune base de données.

| Domaine | Modules principaux | Rôle | Lignes |
|---|---|---|---|
| Lancement du moteur | `server.py`, `engines.py`, `roster.py`, `build_probe.py` | Démarre `llama-server`, construit les drapeaux depuis un registre de modèles (`roster`) et un registre de moteurs (`engines`) | 287, 395, 712, 47 |
| Banc de runtime | `__init__.py` (CLI), `repetitions.py`, `timings.py`, `aggregation.py`, `energy.py`, `gpu.py`, `nvml.py`, `machine_state.py` | Un échauffement, N répétitions, refroidissement. Médiane, moyenne et écart type du TTFT, du débit de prompt et de génération. Crête de mémoire. Énergie CodeCarbon étiquetée par canal | 507, 184, 193, 158, 225, 28, 89, 98 |
| Banc de qualité | `quality_cli.py`, `local_client.py`, `mistral_client.py`, `google_client.py`, `scoring.py`, `scoring_rules.py`, `chrf.py`, `classification_suite.py`, `translation_suite.py`, `suite_*.py` | Deux suites écrites à la main (classification de 20 messages, traduction de 21 phrases) en données JSON, notation par correspondance exacte ou chrF | 1 360, 414, 274, 463, 382, 196, 142 |
| Juges | `judge.py`, `judge_protocol.py`, `judge_backends.py`, `judge_probe.py`, `agreement.py` | Deux juges de familles différentes, kappa de Cohen, désaccord signalé | 399, 300, 188, 1 371, 318 |
| Statistiques | `score_interval.py`, `subset_sampler.py`, `subset_replay.py`, `comparison.py`, `leader_set.py` | Intervalle bootstrap par note, tirage reproductible, tests de différence, ensemble des modèles indiscernables du meilleur | 387, 588, 136, 2 187, 867 |
| Contrat de données | `row_contract.py`, `results.py`, `fiche_registry.py`, `fiche_validator.py`, `hardware.py`, `verdict.py`, `provenance.py`, `build_info.py` | Schéma des lignes (version 8), refus des lignes incomplètes, fiche matérielle hachée, verdict de reproduction | 1 646, 290, 154, 198, 187, 364 |
| Publication | `bundle_export.py`, `use_case_coverage.py`, `composition_check.py`, `candidate_gate.py`, `cost.py` | Export en 7 CSV, couverture des cas d'usage, grille d'entrée d'un modèle candidat, coût en dollars | 2 229, 211, 315, 942, 288 |
| Service | `service.py`, `read_model.py`, `settings.py` | 7 routes `GET` en lecture seule, clé d'API, TLS, contrat « valeur ou absence déclarée » | 369, 1 423, 583 |

Le plus gros module du dépôt est `bundle_export.py` (2 229 lignes), suivi de `comparison.py` (2 187) et de `row_contract.py` (1 646).

### 1.2 Front (`frontend/`)

| Élément | Constat |
|---|---|
| Stack | React 19.2.8, Vite 8, TypeScript 6, Vitest 5, ESLint 10, Prettier. `tsc -b && vite build`. Aucune bibliothèque de composants, de graphiques ni de routage |
| Taille | 6 179 lignes de `.ts` et `.tsx`, tests et fixtures compris. 114 cas de test sur `main` |
| Service | FastAPI sert `frontend/dist/` en repli (`/{full_path:path}`). Pas de CORS, pas de schéma OpenAPI exposé |
| Accès | `KeyGate` demande une clé d'API (`X-API-Key`), la garde en stockage navigateur et l'efface sur un 401 |
| Navigation | Un état React (`overview`, `runs`, `selected`, `comparison`). Pas d'URL, pas de bouton Précédent, pas de lien profond |

### 1.3 Moteurs pris en charge

| Moteur ou fournisseur | Statut dans le code |
|---|---|
| llama.cpp (`llama-server`) | Seul moteur implémenté, version `b10537` fixée. Lancé et arrêté par le banc. Chat par `/v1/chat/completions`, gabarit par `/apply-template` |
| Ollama | **Absent du code.** Il n'apparaît que dans des tests du registre (un second moteur fictif) et dans un spike résolu à partir de captures sur la branche de nuit. L'architecture écrit : « llama.cpp over Ollama » |
| Cloud | Mistral (sujet et juge) et Google AI (juge). Pas d'Anthropic, pas d'OpenAI. `GOOGLE_API_KEY` est « réservé » à un juge à venir sur `main` |
| Harnais d'agents | Cinq identifiants figés (`direct`, `smolagents`, `langgraph`, `pydantic-ai`, `llamaindex`). Seul `direct` est implémenté, les quatre autres ne sont même pas des dépendances |

### 1.4 Persistance

| Donnée | Support |
|---|---|
| Lignes de runtime et de qualité | Fichiers JSONL en ajout seul (`runtime.jsonl`, `quality.jsonl`), non suivis par git. Des copies « de référence » sont versionnées |
| Fiches matérielles | Un fichier JSON par hachage SHA-256 dans `aidd_docs/results/fiches/` |
| Registres | `roster/models.json`, `roster/engines.json` (et `machines.json`, `profiles` sur la branche de nuit) |
| Suites | JSON dans `suite_data/` plus des instantanés par version |
| Base de données | Aucune. Ni SQLite, ni ORM |

### 1.5 CI, Docker, compose

| Élément | Constat |
|---|---|
| CI (`ci.yml`) | Trois jobs. `test` sur Ubuntu et Windows : `pre-commit` (ruff, ruff format, mypy, detect-secrets), `pytest` avec plancher de couverture, audit de dépendances. `frontend` : lint, format, typecheck, tests avec couverture. `build` : image Docker et trois tests de fumée. Actions épinglées par SHA |
| Dockerfile | Trois étages. Récupère `llama-server` CPU avec vérification SHA-256, installe le projet par `uv sync --locked`, tourne en utilisateur non root. L'image n'embarque pas le front |
| `compose.yaml` | Deux services (`runtime`, `quality`) sur l'image publiée, modèles montés en lecture seule. `compose.build.yaml` superpose la construction locale |
| Règles du dépôt | `.github/rulesets/main.json` : `main` n'accepte que des PR avec contrôles requis |
| Autre | `scripts/audit_dependencies.py` avec dérogations datées (`docs/dependency-waivers.yml`), `generate_dev_cert.py` pour le TLS auto-signé |

### 1.6 Branches

Toutes les branches sauf une ont 0 commit d'avance sur `main` : elles ont été fusionnées.

| Branche | Date | Ajoute par rapport à `main` |
|---|---|---|
| `main` | 2026-10-02 | Le socle décrit ci-dessus. 2 097 tests passés, 98,10 % de couverture (journal de nuit) |
| `chore/version-0.2.0`, `release/v0.2.0` | 2026-09-22 | Rien (déjà fusionnées). Version 0.2.0 |
| `feat/dense-moe-view` | 2026-09-21 | Rien (fusionnée). L'écran « Compare dense and MoE » |
| `feat/runtime-measurement-harness` | 2026-08-21 | Rien (fusionnée). Premier banc de runtime |
| `docs/slice-remaining-epics` | 2026-10-02 | Rien (fusionnée). Découpage du backlog en stories |
| `feat/ready-stories-unattended` | 2026-10-02 | Rien (fusionnée). Première exécution sans surveillance |
| **`feat/night-run-2026-10-02`** | 2026-10-04 | **125 commits, 143 fichiers de code et de test, +36 400 lignes. PR n°56 en brouillon, jamais fusionnée.** Détail ci-dessous |

Contenu de la branche de nuit :

| Ajout | Détail |
|---|---|
| Profils et machines | `profiles.py`, `machines.py`, `preflight.py`, `machine_results.py` : un profil par (modèle, machine, mode GPU ou CPU), refus publié quand la machine est sous le minimum déclaré, fusion des lignes de plusieurs machines (`bundle_merge.py`) |
| Campagnes | `campaigns.py` : moteurs, variantes d'invite, modèles et suites déclarés en données, cellule vide = échec |
| Variantes d'invite | `prompt_variants.py` : variantes « terse » et « contrainte par grammaire » |
| Nouvelles suites | MInDS-14 (classification, 3 661 lignes de JSON), WMT24++ (traduction, 4 867 lignes), génération de code avec bac à sable (`code_sandbox.py`) |
| Console de démo | `demo_console.py` + `ConsolePanel.tsx` : lance le CLI du banc depuis le navigateur, sortie en NDJSON, un seul lancement à la fois |
| Playground | `playground.py` + `PlaygroundPanel.tsx` : l'utilisateur écrit à un modèle local ou à un seul sujet cloud, **un tour à la fois, rien n'est enregistré, aucun chiffre affiché** |
| Réception client | `client_sessions.py` (873 lignes) : fichier de comptes rendus de séances de présentation, verdict de crédibilité par version |
| Publication | Archive de release, copies Parquet, mécanique de citation (`CITATION.cff` avec des champs `PLACEHOLDER-OWNER-*`), dépôt Zenodo |
| Résultats | 926 lignes de qualité et 6 de runtime dans le lot de référence, contre 80 et 2 sur `main` |
| Tests | 2 121 fonctions de test Python, 153 cas de test front, 3 183 tests passés et 20 ignorés selon le journal, 98,53 % de couverture |

---

## 2. État réel par fonctionnalité

Légende : **terminée** = code et tests présents ; **partielle** = code présent mais une exigence de l'issue manque ; **squelette** = structure ou déclaration sans comportement.

| Fonctionnalité | Branche | État | Preuve dans le code |
|---|---|---|---|
| Lancement de `llama-server` par registre | main | terminée | `server.py`, `roster.py` : tests de drapeaux octet pour octet (`test_launch_byte_identical.py`) |
| Banc de runtime avec répétitions | main | terminée | `repetitions.py`, `aggregation.py`, `timings.py`. Le TTFT vient du serveur (`server_reported`). Un TTFT mesuré côté client a été essayé puis retiré |
| Énergie par canal | main | terminée, mesure limitée | `energy.py` : sous Windows, le CPU et la RAM sont des estimations (pas de RAPL), seul le GPU est mesuré. Chaque canal porte son étiquette de méthode |
| Fiche matérielle hachée, verdict de reproduction | main | terminée | `hardware.py`, `fiche_registry.py`, `verdict.py` |
| Contrat de lignes et refus d'écriture | main | terminée | `row_contract.py` (1 646 lignes) |
| Suites de classification et de traduction | main | terminée mais petite | 20 et 21 éléments. Trop peu pour un classement : le dépôt le dit lui-même (intervalles de confiance larges) |
| Juges (deux familles, accord) | main | terminée en code, **non éprouvée** | `judge_protocol.py`, `agreement.py`. Le journal de nuit interdit tout appel payant : les chemins cloud sont prouvés sur des lignes construites ou du HTTP simulé |
| Intervalles, comparaisons, ensemble des indiscernables | main | terminée | `score_interval.py`, `comparison.py`, `leader_set.py` |
| Export en 7 CSV | main | terminée | `bundle_export.py`, `test_bundle_export.py` |
| Service de lecture et tableau de bord | main | terminée, minimal | 7 routes `GET`, 8 écrans en tables |
| Image Docker du banc | main | terminée | Trois tests de fumée en CI. Aucun test sur un vrai modèle |
| Ollama comme moteur | aucune | **absente** | Aucun client, aucun lancement. Un registre de moteurs prêt à en accueillir un second |
| Harnais d'agents comparés | main | **squelette** | Cinq identifiants, un seul implémenté. La fonction qui mesure le surcoût d'invite existe, aucun adaptateur ne l'appelle |
| Chat, Arène, RAG, agents, équipes | aucune | **absents** | Rien dans `src/` ni dans `frontend/` |
| Profils par machine, campagnes, pré-vol | nuit | terminée, non fusionnée | Modules et tests présents. Le laptop doit « republier le lot une fois » avant fusion |
| Console de démo | nuit | partielle | Code et tests faits. L'issue reste `ready` : preuves attendues sur un second laptop |
| Playground | nuit | partielle | Un seul tour, sans mémoire, sans chiffre. Le sujet cloud n'a jamais été exercé en vrai |
| Génération de code évaluée par tests | nuit | partielle | Le bac à sable JavaScript n'a jamais tourné dans un conteneur Node |
| Variantes d'invite (terse, grammaire) | nuit | terminée en code | Livrées, avec des questions ouvertes (compression d'entrée qui supprime des négations) |
| Release, Parquet, citation, Zenodo | nuit | partielle | Aucun tag `v*` poussé, identité de l'auteur en valeurs provisoires |
| Runtime Ollama comparé à llama.cpp | nuit | **non fait** | Journal : « no request field turns off » la réutilisation du cache de prompt d'Ollama |

### Ordre de grandeur des tests

| Mesure | `main` | Branche de nuit |
|---|---|---|
| Fichiers de test Python | 66 | non comptés |
| Fonctions `def test_` (hors paramétrage) | 1 468 | 2 121 |
| Tests exécutés (journal) | 2 097 | 3 183 passés, 20 ignorés |
| Lignes de test Python | 28 740 | non comptées |
| Cas de test front (`it`, `test`) | 114 | 153 |
| Plancher de couverture imposé | 95 % | 95 % (98,53 % mesuré) |
| Durée de la suite | environ 170 s | 282 s |

Ce que les tests couvrent vraiment :

- **Beaucoup de contrats.** Presque chaque test vérifie qu'un module refuse une entrée mal formée et nomme le champ fautif. C'est de la discipline de format, pas de la mesure.
- **Aucun test contre un modèle réel dans la CI.** `llama-server` n'y est qu'interrogé par `--version`. Les clients de juges sont testés par HTTP simulé.
- **Des invariants entre fichiers.** Par exemple `test_read_model.py` vérifie que l'ensemble des champs affichés est exactement la partition de `REQUIRED_FIELDS`. C'est solide et utile.
- **Le front se teste sur fixtures** : chaque vue a un fichier `fixtures/*.fixture.ts` ; aucun test de bout en bout, aucun navigateur réel.

---

## 3. Interface

### 3.1 Écrans et composants

| Écran | Fichier | Contenu |
|---|---|---|
| Accès par clé | `components/KeyGate.tsx` | Saisie de la clé d'API, effacée sur 401 |
| Vue d'ensemble | `views/overview/OverviewView.tsx` | Une carte par cas d'usage (suite), bandeau de couverture, panneaux qualité et runtime côte à côte |
| Liste des exécutions | `views/RunsList.tsx` | Tableau des exécutions de qualité et de runtime |
| Qualité | `views/quality/QualityView.tsx` | Tableau par modèle : note, intervalle, plafonds de génération, nombre d'échecs par cause |
| Runtime | `views/runtime/RuntimeView.tsx` | Tableau : TTFT (avec sa provenance), débits, crête de mémoire, fiche matérielle |
| Énergie | `views/energy/EnergyView.tsx` | Tableau : énergie et émissions par canal, étiquette de méthode, périmètre de comparaison |
| Comparaison dense contre MoE | `views/comparison/ComparisonView.tsx` | Une colonne par modèle, une ligne par élément de test, notes de chaque modèle côte à côte |
| Console (nuit) | `views/console/ConsolePanel.tsx` | Choix d'une suite et d'un profil, lancement, sortie en flux |
| Playground (nuit) | `views/playground/PlaygroundPanel.tsx` | Un modèle, une invite, une réponse en flux |

Composants transverses : `Absent`, onze étiquettes (`VerdictLabel`, `IndicativeLabel`, `UnreliableLabel`, `SingleJudgeLabel`, `ContestedLabel`, `ContaminationRiskLabel`, `EnergyMethodLabel`, `ScopeComparabilityLabel`, `DeclaredAbsenceLabel`, `PlaygroundLabel`), cellules `CapsCell`, `FailureCountsCell`, `TtftCell`.

### 3.2 Ce qui montre les résultats à un décideur

| Ce qu'un décideur cherche | Ce que le front offre | Jugement |
|---|---|---|
| Comparer des modèles | Le tableau de `ComparisonView`, réservé à dense contre MoE | Lisible pour un technicien, pas pour un décideur |
| Graphiques | **Aucun.** Ni SVG, ni canvas, ni bibliothèque. Une recherche de `svg`, `canvas`, `chart` dans `frontend/src` ne renvoie rien | Absent |
| Fiche d'un modèle | Aucune. Le modèle n'est qu'une colonne ou un identifiant de roster | Absent |
| Verdict | `VerdictLabel` : « reproduced », « not reproduced », « not comparable » (reproduction d'une exécution, pas verdict de choix de modèle) | Utile pour l'audit, pas pour décider |
| Réponse à « quel modèle prendre ? » | Le calcul existe côté back (`leader_set.py` : modèles indiscernables du meilleur) mais n'est montré qu'en table | Réponse juste, rendue à peine visible |

Le front est un outil d'auditeur, pas une vitrine. Le backlog prévoit un écran « une carte par cas d'usage lue depuis les lignes publiées » : la vue d'ensemble en est une première version.

### 3.3 Patterns à reprendre dans le front v2 (voir `03-ux-front.md` §3)

| Pattern | Où | Pourquoi le reprendre | Adaptation |
|---|---|---|---|
| Valeur ou absence nommée, jamais un tiret ni zéro | `components/Absent.tsx`, `api/types.ts` (`Maybe<T>`, `isAbsent`) | C'est le contrat exact de 03 §3.7 : « non mesurable » avec sa raison, jamais « — » seul, jamais 0. Trois raisons finies (`predates_schema`, `null_in_row`, `pointer_unresolved`) | À réécrire en JS natif (une fonction, 20 lignes). Les raisons de v2 seront d'autres : modèle cloud de taille inconnue, mesure indisponible |
| Étiquette qui accompagne une valeur fragile | `labels/*` (« indicatif », « peu fiable », « un seul juge », « contesté ») | Rend visible, au point de lecture, la fiabilité d'une note. Correspond à la note « peu fiable sous 4 milliards de paramètres » de l'Arène (03 §3.5) | Textes en français, icônes Material, pas seulement la couleur |
| Une étiquette de méthode sur chaque mesure d'énergie | `EnergyMethodLabel.tsx` | Écho direct de « estimé » sur le CO₂ cloud (03 §3.7) | Reprendre l'idée, pas le code |
| Le service refuse de démarrer sans clé | `service.py`, `KeyGate` | Utile pour une démo sur le réseau local, inutile en `127.0.0.1` | Garder la protection de 02 §5.5 (hôte local, origine) à la place |
| Provenance du TTFT affichée | `TtftCell.tsx` (« server_reported ») | Aide à la lecture du « débit provisoire » contre « final » (03 §3.7) | À adapter |
| Panneau « un seul à la fois » avec le nom de celui qui occupe | `console/holder.ts`, verrou de `demo_console` | Même besoin que le sémaphore Ollama (02 §5.6) : dire qui bloque | Le message, pas le mécanisme |
| Playground qui dit avant l'envoi si le texte quitte la machine | `PlaygroundLabel`, `sendControlText` | Cadre exact de D1 : le bouton d'envoi change de libellé quand le sujet est cloud | À reprendre tel quel dans le `model-picker` et le bouton d'envoi |
| Ne montrer aucun chiffre dans le playground | `playground.py` | « Tout chiffre à l'écran se lirait comme une mesure » : principe de 03 §3.2 (« le front ne calcule aucune mesure ») | Notre débit provisoire contredit cette règle : à trancher, voir leçon 7 |

### 3.4 Écarts à la charte Wavestone

| Règle | Constat |
|---|---|
| Primaire `#451DC7` | Accent `#6c2bd9` en clair, `#b083f0` en sombre. Aucune trace de `#451DC7`. Gris GitHub (`#24292f`, `#d0d7de`) pour le reste |
| Icônes Material | Aucune icône. Des flèches Unicode dans le texte (« Runs → », « ← Runs ») |
| Aucun emoji | Respecté |
| Thème sombre | Présent, par `prefers-color-scheme`, sans bascule manuelle |
| Police | `system-ui`. Ni Aptos ni Inter |
| Langue | Interface en anglais. La charte et `AGENTS.md` de wavelocalai demandent le français |
| Accessibilité | Boutons natifs et `aria-pressed` sur l'onglet. Pas de lien d'évitement, pas de `aria-live`, pas de mode projection, pas de test d'accessibilité |
| Jetons de design | Neuf variables CSS, pas de fichier de jetons, pas de test de dérive |

---

## 4. Code réutilisable pour la nouvelle version

Barème de qualité : **A** = directement lisible et testé ; **B** = bon mais lié à d'autres modules du dépôt ; **C** = utile seulement comme référence. Coût d'adaptation à la pile cible (FastAPI, SDK officiels, sqlite-vec, front natif) : **faible** (copie et retouche de noms), **moyen** (réécriture partielle), **élevé** (réécriture).

### 4.1 Pour `wavelocalai` (application)

Le périmètre réutilisable est mince, parce que l'application n'a pas d'équivalent dans cet ancien dépôt.

| Module | Ce qu'il fait | Qualité | Adaptation | Remarque |
|---|---|---|---|---|
| `local_client.py` | Appel de chat à `llama-server` après rendu du gabarit de conversation du modèle ; vérifie qu'un réglage de « réflexion » change vraiment le texte rendu | A | moyen | L'idée est précieuse (le défaut « invites jamais passées au gabarit » est documenté) mais ne concerne que llama.cpp. Ollama applique le gabarit lui-même |
| `hardware.py` (`capture_fiche`, `build_fiche`, `fiche_hash`) | Capture CPU, RAM, GPU, pilote, OS, plafond CUDA ; hachage normalisé | A | faible | Utilisable pour la carte d'identité technique de Sobriété et matériel. La partie « projection versionnée » est propre au banc |
| `nvml.py`, `gpu.py` | Session NVML à portée limitée, VRAM et puissance, jamais bloquant | A | faible | À comparer avec `accelerator.py` de la v1 (02 §5.7). Le gestionnaire de contexte `nvml_device` est plus propre |
| `machine_state.py` | Température GPU et CPU, causes de bridage | A | faible | Utile pour expliquer un débit en baisse pendant la démo |
| `energy.py` | Enveloppe CodeCarbon avec méthode par canal | B | moyen | Donne l'idée « jamais de zéro pour inconnu ». La v1 a déjà `answer_carbon` |
| `path_guard.py` | Garde de chemins | B | faible | Même rôle que `rag/ingestion._validate_path` |
| `retry.py` | Reprise avec pacing, limites de débit cloud | B | moyen | À remplacer par les reprises des SDK officiels |
| `mistral_client.py`, `google_client.py` | Clients HTTP à la main avec `requests` | C | élevé | Le plan prévoit les SDK officiels : ces deux fichiers sont à ne pas reprendre |
| `cost.py` | Prix par million de jetons, tables datées, deux calculs (cloud, kWh local) | C | moyen | Les tables sont des instantanés datés, périmés. Le principe « prix daté » est à garder |
| `service.py` | FastAPI, clé, TLS, repli vers le front | C | élevé | Lecture seule, synchrone, sans SSE. Rien à envoyer vers le back cible (02 §5) |

### 4.2 Pour `slm-quality-bench`

Ces modules relèvent du banc. Ils sont les meilleurs du dépôt.

| Module | Ce qu'il fait | Qualité | Adaptation | Remarque |
|---|---|---|---|---|
| `repetitions.py`, `aggregation.py`, `timings.py` | Échauffement, répétitions, refroidissement, médiane et écart type, crête | A | faible | Le harnais de mesure runtime demandé. Dépend de `llama-server` et de `requests` |
| `row_contract.py` | Schéma de ligne et refus des lignes incomplètes | B | moyen | 1 646 lignes, très lié aux règles du dépôt. Utile comme modèle de ce qu'une ligne doit porter |
| `fiche_registry.py`, `fiche_validator.py`, `verdict.py` | Magasin de fiches adressé par hachage, validation, verdict à trois états | A | faible | Le verdict ne compare que moteur, build, quantification, GPU et drapeaux : un champ nul des deux côtés ne correspond jamais |
| `engines.py`, `roster.py` | Registre de moteurs et de modèles en données, avec champ manquant nommé | B | moyen | Bon registre, mais conçu pour un seul moteur. À simplifier |
| `score_interval.py` | Intervalle par bootstrap, tirage reproductible | A | faible | Réutilisable pour toute note du banc |
| `agreement.py` | Kappa de Cohen, taux d'accord, seuil de « contesté » | A | faible | Court et testé |
| `chrf.py`, `scoring_rules.py` | chrF sans dépendance, règles de notation nommées | A | faible | |
| `subset_sampler.py`, `subset_replay.py` | Tirage reproductible d'un sous-ensemble depuis une règle consignée | B | moyen | |
| `leader_set.py`, `comparison.py` | Modèles indiscernables du meilleur, tests de différence avec correction | B | moyen | 867 et 2 187 lignes : à relire avant reprise |
| `bundle_export.py` | Export en CSV, licences et citation | B | élevé | 2 229 lignes d'un seul tenant |
| `suite_data/*.json`, `suite_registry.py`, `suite_gate.py` | Suites en données, avec licence, source et risque de contamination par élément | A | faible | Le format est le bon. Les 41 éléments sont trop peu |
| `judge_protocol.py`, `judge_probe.py` | Invite et grille de juge versionnées, sonde de disponibilité | B | moyen | `judge_probe.py` fait 1 371 lignes |
| `candidate_gate.py`, `composition_check.py` | Grille d'entrée d'un modèle, vérification de la composition par classe de taille | B | moyen | Spécifique au projet de publication |

### 4.3 Ce qui ne se reprend pas

`client_sessions.py` (comptes rendus de séances), `use_case_coverage.py`, `read_model.py` (1 423 lignes de vues), le Dockerfile du banc, les scripts de publication Zenodo et Parquet. Ils servent un projet de publication, pas une application.

---

## 5. Choix de stack comparés

### 5.1 React + Vite contre le front natif sans compilation (03 §3.1)

| Critère de 03 §3.1 | Leur expérience | Ce que ça apprend |
|---|---|---|
| Installation sans droits admin | Node épinglé par `.nvmrc`, `npm ci`, 20 paquets de développement directs, `package-lock.json` | Confirme le critère : il faut Node et un `npm ci` avant de voir l'écran. `README` : « the results dashboard needs Node » |
| Pas de Node à l'exécution | `frontend/dist/` n'est pas versionné. Un clone sans `npm run build` sert un écran vide (« nothing to mount ») | Dette réelle : le service démarre sans interface si le build manque. La CI construit, mais l'image Docker n'embarque pas le front |
| Maintenance par un petit binôme | Chaque version de paquet est épinglée à la main (React 19.2.8, TypeScript 6.0.2, Vite 8.3.0…). Deux jobs CI entiers (lint, format, types, tests) pour 3 000 lignes de composants | L'outillage JS coûte autant de CI que le code qu'il vérifie |
| Performance perçue | Rien à mesurer : tables statiques | Sans objet |
| Accessibilité | Aucune règle appliquée | React n'en apporte pas ; le natif n'en retire pas |
| Streaming | `fetch` + NDJSON dans la branche de nuit, lu à la main (`streamConsoleRun`, `streamPlaygroundChat`) | Montre que React n'aide pas au streaming : on écrit le même `ReadableStream` à la main. Le plan prévoit du SSE, plus simple à reprendre |
| Réutilisation du harnais | Aucune | |
| Types partagés | `types.ts` recopie à la main les constantes du Python (« restated here rather than inferred ») | Duplication reconnue. Sans OpenAPI exposé, le front et le back dérivent sans alerte |

Ce que l'expérience valide :

- **Le choix natif est confirmé.** Le front n'utilise de React que `useState`, `useEffect` et des composants sans état partagé. Aucune fonction de React ne manquerait en modules natifs.
- **Les types TypeScript ont un vrai apport** : les unions `Maybe<T>` et la vérification des `props`. En JS natif, on les remplace par des commentaires `@typedef` et `// @ts-check` (vérification par `tsc` sans compilation), pour garder le typage sans l'outillage de build.
- **Le routeur manque.** Leur navigation par état empêche les liens profonds : la décision de 03 §3.2 (routeur par `hash`) est la bonne.

### 5.2 Leur back contre le back cible (02 §5)

| Point | Ancien back | Back cible |
|---|---|---|
| Cadre | FastAPI, mais usage minimal : 7 routes `GET`, fonctions synchrones, sans OpenAPI | FastAPI asynchrone, SSE, OpenAPI |
| Client HTTP | `requests` synchrone, clients cloud écrits à la main | SDK officiels, `AsyncClient` Ollama partagé |
| Streaming | NDJSON sur `StreamingResponse` (branche de nuit seulement) | SSE par exécution, rejouable (03 §3.6) |
| Persistance | JSONL en ajout seul, JSON par hachage | SQLite unique (table `runs`), sqlite-vec |
| Concurrence | Un verrou global d'occupation (« un seul lancement ») | Sémaphore Ollama, appels cloud en parallèle, tâches annulables |
| Découpage | Paquet plat de 60 modules, tous au même niveau | Paquets par domaine (`models/`, `inference/`, `rag/`, …) avec `web/` seul à connaître FastAPI |
| Configuration | `settings.py` de 583 lignes (une fonction de chargement par service) | `Settings` pydantic unique, `wavelocalai.toml` |
| Sécurité locale | Clé d'API obligatoire, TLS auto-signé, refus des pairs non locaux | Écoute sur `127.0.0.1`, refus des POST d'une autre origine |
| Mesure carbone | CodeCarbon par canal, étiqueté | CodeCarbon local, `ecologits` cloud, table `runs` |

Constat : le back cible est plus simple et plus large. L'ancien back est plus profond sur la mesure et la provenance, et plus étroit sur tout le reste.

---

## 6. Signes de l'avancement insatisfaisant

| Signe | Preuve | Effet |
|---|---|---|
| **La portée a dérivé du produit vers la preuve.** Le dépôt vise une publication reproductible (citation, Zenodo, Parquet, archive de release, séances de réception client), pas un outil que l'on utilise | `client_sessions.py` (873 lignes), `bundle_merge.py`, `assemble_release_archive.py` (982 lignes), mécanique de citation avec `PLACEHOLDER-OWNER-*` | Beaucoup de code, aucun écran que l'on montre à un client |
| **Documentation supérieure au code.** 596 fichiers, 45 880 lignes sous `aidd_docs/`, contre 24 080 lignes de `src/` | 112 stories, 14 spikes, 12 épopées, 854 lignes de `CHANGELOG.md`, 7 fichiers de mémoire de projet | Le coût de tenue des textes dépasse celui du code. Le journal de nuit note des textes de stories périmés « per row » |
| **Preuve minuscule face à la mécanique.** `main` publie 80 lignes de qualité et 2 de runtime ; 20 et 21 éléments par suite | `aidd_docs/results/*.jsonl` | Les intervalles de confiance sont larges. Les statistiques sophistiquées (bootstrap, accord, correction de comparaisons multiples) s'appliquent à des échantillons trop petits |
| **Lot publié en retard d'un schéma.** Les lignes sont en schéma `"7"`, le code en `"8"` | `aidd_docs/results/README.md` : « one schema behind the code », régénération renvoyée à `tech-debt.md` | Chaque évolution du contrat rend la preuve existante obsolète. Les fichiers `*.schema-1.jsonl` en sont la trace |
| **Abstractions prématurées.** Registre de moteurs prévu pour un second moteur qui n'existe pas. Cinq harnais nommés, un seul implémenté. `GOOGLE_API_KEY` « réservé ». Un plafond de « trois harnais » codé avant le premier | `engines.py`, `harness.py`, `README.md` | Chaque abstraction est testée à 100 % et ne sert à rien |
| **Modules géants.** `bundle_export.py` 2 229 lignes, `comparison.py` 2 187, `row_contract.py` 1 646, `read_model.py` 1 423, `judge_probe.py` 1 371, `quality_cli.py` 1 360 | `wc -l` | Relecture humaine impossible. Le dépôt compte sur les agents pour les relire |
| **Branche de nuit jamais fusionnée.** 125 commits, +36 400 lignes, brouillon PR n°56 depuis le 2026-10-04 | `run-log.md` : « Merge or close PR #56 » | Le travail le plus avancé n'est pas sur `main`. 13 stories sont « code fait, preuves attendues » |
| **Stories closes sans preuve.** 13 stories restent `ready` après code fait, car leurs preuves exigent un second laptop, un appel payant, un conteneur Node ou un tag | Journal de nuit, tableau « waiting on the owner » | La définition de « terminé » exige des preuves matérielles qu'un agent ne peut pas produire seul |
| **Le gabarit de travail ralentit.** Les agents « bloquent » à répétition : 5 h 50 de silence sur la première story. Cause trouvée par la suite : la mise en veille Windows (Modern Standby) | Journal : « The stalls... were Modern Standby » | Une nuit d'exécution a servi à diagnostiquer l'outil plutôt qu'à construire |
| **Conflit d'exigences entre stories.** La story 3 retire `validated_host` du registre ; la ligne 7 exige que `test_launch_byte_identical.py` reste intact et lise ce champ | Journal : `ACCEPTANCE-CONFLICT`, résolu par décision du propriétaire D4 | Les critères d'acceptation se contredisent faute de relecture croisée |
| **Contraintes de mesure non résolues.** Ollama réutilise 60 jetons de prompt sur 61 à chaque répétition, et aucune option ne l'empêche. La compression d'entrée supprime des négations | Journal, « owner decisions » | Deux des fonctions les plus visées (Ollama, compression) ne tiennent pas leur promesse |
| **Tests fragiles.** Un test échoue sur Ubuntu parce qu'un chemin Windows est lu avec un `Path` POSIX (`test_token_counts_come_from_the_served_tokenizer`). Un fichier de test a paru « suspendu 20 minutes ». Suite de 282 s | Journal de nuit | Dépendance aux chemins et à la machine. La suite lente freine chaque story |
| **Aucun test de bout en bout du front.** Seules des fixtures. Aucun navigateur, aucun test de l'écran réel | `frontend/src/**/*.test.tsx` | Les vues peuvent passer 153 tests et ne pas s'afficher correctement |
| **Interface négligée.** Aucun graphique, anglais, hors charte, navigation par état | §3 | L'effort est allé au contrat de données, pas à ce que le décideur voit |
| **Aucun appel payant autorisé.** Les juges, cœur de la qualité, n'ont jamais tourné sur du cloud en production dans la dernière passe | Décision D2 | La fonction centrale du banc est « prouvée sur du simulé » |

---

## 7. Leçons pour la nouvelle version

1. **Écrire d'abord ce qu'on montre.** Partir d'un écran (l'Arène avec ses colonnes qui se remplissent) et remonter vers le back. L'ancien dépôt a fait l'inverse : contrat de lignes, puis lecture, puis écran.
2. **Une preuve avant une mécanique.** Ne pas ajouter de test statistique, de verdict ni de schéma tant qu'il n'existe pas de quoi les nourrir. Pour `slm-quality-bench` : 20 éléments par suite ne justifient ni bootstrap ni correction multiple.
3. **Livrer par lots fusionnables.** Pas de branche de 125 commits. Un lot = une PR sur `master` en moins d'une journée, avec un écran qui marche.
4. **Pas de registre sans second cas.** Un moteur = un module. Ajouter l'abstraction au moment du deuxième moteur réel (Ollama), pas avant. Même règle pour les harnais d'agents.
5. **Plafonner la taille des fichiers.** Règle de 03 §3.2 (environ 600 lignes) étendue au back. Aucun module de plus de 600 lignes sans justification écrite.
6. **Limiter la documentation de pilotage.** Un `CLAUDE.md` court et un seul plan à jour valent mieux que 112 stories. Les textes de stories périmés coûtent plus que ce qu'ils protègent.
7. **Garder les deux idées fortes de l'ancien dépôt.**
   - **Absence nommée plutôt que zéro** (`Absent`) : à implémenter dès le premier écran du CO₂ et du débit (03 §3.7).
   - **Provenance sur chaque mesure** (méthode d'énergie, origine du TTFT). Trancher la contradiction avec 03 §3.7 : afficher un débit provisoire en italique (notre choix) ou aucun chiffre pendant le flux (choix du playground). Le débit provisoire est utile en démo ; il doit porter l'étiquette « provisoire », comme l'ancien dépôt l'aurait exigé.
8. **Front natif, avec `@ts-check`.** Le typage de `Maybe<T>` est le seul vrai gain de TypeScript ici ; un fichier `types.js` en JSDoc suffit, sans Node en exécution ni en CI de build.
9. **Exposer le schéma de l'API.** Le front de l'ancien dépôt recopie les constantes du back à la main. Servir `/openapi.json` en local et générer un fichier de types, ou tester que les constantes concordent (comme le test de dérive des jetons du harnais).
10. **Tester l'écran réel.** Un test Playwright sur Edge (déjà prévu en 03 §2.2) par écran livré, plus des tests unitaires sur la mise en forme. Pas de fixtures seules.
11. **Rendre « terminé » vérifiable par l'agent.** Un critère qui exige un second laptop, un appel payant ou un tag ne peut pas bloquer l'état d'une story. Séparer « code fait et testé » de « preuve de terrain ».
12. **Désactiver la mise en veille pendant les runs longs** (`SetThreadExecutionState`) : déjà noté dans la mémoire du projet, la cause de la moitié des « blocages » de la nuit.
13. **Ne pas rouvrir llama.cpp.** Ollama reste le moteur de l'application (v1, 02 §5). Le banc `slm-quality-bench` garde llama.cpp et sa mesure précise ; les deux ne partagent qu'un contrat de données, comme le dit 00 §1 point 9.
14. **Avant de supprimer le dépôt**, récupérer : le dossier `suite_data/` (format des suites), `aidd_docs/roster/engines.json` et `models.json` (quantifications, empreintes SHA-256 de GGUF, utiles à `slm-quality-bench`), `score_interval.py`, `agreement.py`, `chrf.py`, `repetitions.py`, `aggregation.py`, `hardware.py`, `verdict.py`, et le journal de nuit (`run-log.md`) qui consigne les décisions D1 à D8 et les questions ouvertes sur Ollama. La branche `feat/night-run-2026-10-02` contient les 926 lignes de qualité les plus complètes : à ne pas perdre si elles servent de référence.
