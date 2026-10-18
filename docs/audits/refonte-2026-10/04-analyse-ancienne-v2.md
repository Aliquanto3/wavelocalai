# Analyse des spécifications de l'ancien dépôt `wave_local_ai_v2`

- **Date :** 2026-10-18
- **Dépôt analysé :** `Aliquanto3/wave_local_ai_v2`, clone en lecture seule. `main` au commit `c68b23e` (2026-10-02). La branche la plus avancée est `origin/feat/night-run-2026-10-02` (`d28c8a7`, 2026-10-04, 125 commits de plus, jamais fusionnée). Sauf mention contraire, les états viennent de cette branche.
- **Lu :** `context_input/*.md`, `aidd_docs/product/`, `aidd_docs/memory/`, le PRD (`aidd_docs/tasks/2026_08/2026_08_21-wave-local-ai-v2-benchmark-suite-prd.md`), les 12 épopées, 18 spikes et 117 stories (statuts et titres, détail des plus utiles), les journaux de nuit, l'audit du 2026-09-22, `aidd_docs/results/README.md`, `README.md`, `CHANGELOG.md`, `docs/`. Rien n'a été exécuté.
- **Comparé à :** `00-synthese.md` à `03-ux-front.md`, `../frontend-2026-09/SYNTHESE.md` (D1 à D7), `EXPERIENCE.md` et `DESIGN.md` (`_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/`), `slm-quality-bench` (`docs/spec/SPEC.md`, `docs/architecture/ARCHITECTURE-SPINE.md`).
- **Rapport voisin :** [`05-code-ancienne-v2.md`](05-code-ancienne-v2.md) analyse le code. Ce rapport-ci ne le répète pas : il traite des intentions, des spécifications et de la méthode.

## Résumé

1. **Les ambitions de l'utilisateur sont claires et stables** : un article de recherche court pour aider à anticiper ce que donnent beaucoup de petits modèles sur des PC ordinaires, dont un PC pro de 16 Go sans GPU ; une preuve « défendable » pour ses missions de conseil ; une démo lisible par un décideur. Elles tiennent en deux fichiers de `context_input/`.
2. **L'ancien dépôt a construit la machinerie de preuve, pas la preuve.** 76 stories `done` sur 117, 30 versions de schéma de ligne, mais une seule machine mesurée (le portable), 6 lignes de runtime, deux usages sur neuf (classification, traduction) et aucune note jugée publiée (les stories des juges sont restées `proposed`).
3. **Presque tout le contenu relève de `slm-quality-bench`.** Pour l'application, il reste surtout des idées d'écran : la réponse « quel modèle pour quel usage », le verdict local ou cloud, la projection sur d'autres machines, la fiche modèle dense ou MoE.
4. **Un trou de répartition est apparu.** Depuis le 2026-10-18, `slm-quality-bench` doit publier qualité **et** vitesse par machine (mémoire du projet, `migration-slm-quality-bench`). Or son `SPEC.md` exclut les autres machines, l'énergie et le banc de vitesse. Le contrat `qb.results/1` attendu par l'app n'existe pas encore : `ARCHITECTURE-SPINE.md` AD-6 ne publie que `qb.score/1`, `qb.set_index/1` et `qb.set_manifest/1`.
5. **À conserver avant suppression :** les cinq fichiers de `context_input/`, le brief produit, la reformulation du prompt fondateur (audit du 2026-08-21), le PRD, les décisions du propriétaire et les constats de mesure (§6).

---

## 1. Ambitions et brief de l'utilisateur

### 1.1 Qui a écrit quoi

| Fichier (branche `main`) | Indices | Verdict |
|---|---|---|
| `context_input/hardware.md` | Français sans accents, style télégraphique, mesures personnelles (« ~14 Go/s effectifs mesures ») ; commit `6c595aa` du 2026-08-21, sans co-auteur | **Manuel** (notes de l'utilisateur, peut-être issues d'une session de réglage) |
| `context_input/baseline_qwen36.md` | Même style ; commande `llama-server` validée, pièges, pistes écartées ; même commit | **Manuel** |
| `context_input/model_candidates.md` | Anglais structuré, tableaux, renvois à BenchLM et Artificial Analysis ; commit `e4c06b6` avec le brief | **Mixte** : sélection de l'utilisateur, rédaction assistée |
| `context_input/publication_ambitions.md` | En-tête : « Translated from the owner's French research notes (source: personal ambition statement, 2026-09) » ; commit `7e04a96`, co-auteur Claude Sonnet 5 | **Contenu manuel, texte traduit.** L'original français n'est pas dans le dépôt |
| `context_input/publication_gap_brief.md` | Même en-tête ; amendé par les décisions du 2026-09-06 ; même commit | **Contenu manuel, traduit et amendé** |
| `aidd_docs/product/wave-local-ai-v2.md` | Gabarit AIDD (front matter, tableau « Evidence and Assumptions », « User, this session ») | **Généré**, avec les décisions de l'utilisateur |
| `aidd_docs/memory/project-brief.md` | Gabarit AIDD ; périmé (juges Mistral et Google, abandonnés le 2026-09-06) | **Généré** |
| Prompt fondateur (Claude Chat, en français) | Absent du dépôt ; reformulé en attentes E1 à E16 dans `aidd_docs/tasks/2026_08/2026_08_21_expectations-gap-audit/audit-and-plan.md` | **Manuel à l'origine**, seule trace : la reformulation |

**À demander à l'utilisateur :** les notes françaises d'origine des deux textes de publication (septembre 2026) et le prompt fondateur de Claude Chat. Ce sont ses vrais textes manuels ; le dépôt n'en a que des traductions.

### 1.2 Ses intentions, fidèlement

| Thème | Ce qu'il veut | Source |
|---|---|---|
| Raison d'être | Aucun classement public ne trie par paramètres **actifs**, et aucun ne mesure des poids Q4 avec déport des experts sur CPU. « This gap is the project's reason to exist, and it should be stated as such to clients rather than hidden. » | `model_candidates.md`, « Selection rationale » |
| Produit | Une preuve défendable pour arbitrer local contre cloud. « That defensibility, not any single benchmark number, is the product. » Succès qualitatif, pas lié à une vente | `product/wave-local-ai-v2.md`, « Product Bet », « Success » |
| Publics | Le consultant (lui) ; les développeurs du client, qui lisent le dépôt ; les décideurs, qui ne voient que le front pendant un pitch ; depuis le 2026-09-06, un relecteur académique ; enfin « quelqu'un qui prépare l'IA locale sur un PC ordinaire » | brief, « Audience » ; `publication_gap_brief.md`, « Context » ; PRD, « User Stories » |
| Pitch client | Comparer depuis un navigateur, pas un terminal ; une carte par usage avec le meilleur modèle local, son comparateur cloud, débit et énergie ; un seul chiffre d'énergie, avec son calcul disponible si on le conteste ; le client peut taper une question à un modèle local | PRD, « Goals » et « User Stories » ; attentes E7, E8 |
| Publication | Un article court qui aide à anticiper les résultats de nombreux modèles sur PC personnels. Il sert aussi son activité de conseil et une entrée vers le monde académique (doctorat, enseignement : secondaire). Ordre : article de blog ou Wavestone, arXiv en option, JOSS plus tard | `publication_ambitions.md` ; `publication_gap_brief.md`, « Decisions taken 2026-09-06 » |
| Matériel | Trois PC : tour (Ryzen 5 7600, 32 Go DDR5-6000, RTX 3050 8 Go), portable (Ryzen 7 5800H, 32 Go DDR4-3200, RTX 3060 Laptop 6 Go), PC pro (16 Go, sans GPU). Le PC pro est « le cas le plus important pour la publication : presque absent de la littérature ». Tailles de modèles adaptées à chaque machine (Granite 350M sur le PC pro, classe Gemma 4 sur la tour) | `publication_ambitions.md` ; `publication_gap_brief.md`, écart 1 ; `hardware.md` |
| Constat matériel | « La bande passante mémoire détermine le débit de génération, la VRAM détermine quels modèles chargent. » Les mesures ne se transposent pas d'une machine à l'autre : chaque mesure porte sa fiche matérielle | `hardware.md`, « Implication de conception » |
| Capacités à anticiper | Catégorisation, traduction, correction de fautes, réécriture ; réponse RAG, voire RAG agentique ou Refrag ; appel d'outils, orchestration agentique, code (qualité, durée, tokens, énergie) ; langues EN, FR, DE et langages de programmation ; débits ; énergie et carbone | `publication_ambitions.md` ; `publication_gap_brief.md`, « Tasks » |
| Outils comparés | llama.cpp ou Ollama, LangGraph ou smolagents, meilleur harnais, meilleure paire SLM et harnais par tâche | `publication_ambitions.md` |
| Compression d'invite | Question qui le suit « depuis plusieurs mois » : la technique DSL (essayée dans Copilot Studio) et le skill « Caveman ». Est-ce qu'elles font gagner un SLM en précision et en vitesse ? | `publication_ambitions.md` |
| Périmètre des modèles | MoE à 4 B actifs au plus et 20 Go au plus en Q4 ; denses seulement quand ils sont le bon outil (petit classifieur, embeddings) ; MoE de centre de données exclus | `model_candidates.md` |
| Sobriété | Énergie et carbone mesurés et **étiquetés** (estimé ou mesuré) ; énergie CPU estimée sous Windows, limite assumée ; pas de wattmètre ; le banc rapporte, il ne recommande pas d'optimisation | `publication_gap_brief.md`, écart 6 et « Decisions » ; PRD, « Non-Goals » |
| Hors périmètre | Le retour d'expérience Claude Code, AIDD et SpecKit (publication séparée) ; la comparaison avec Budget_Tags (règles métier, KNN), dans son propre dépôt | `publication_ambitions.md` |
| Attentes d'ingénierie | Back Python et front React, scripts d'abord ; outillage à jour (uv) ; reproductible après clonage ; CI, versions, conteneur ; sécurité et clé d'API pour une démo entre deux machines ; code qui montre la qualité d'un développement assisté par IA | attentes E8 à E16 |

---

## 2. Inventaire des fonctionnalités spécifiées

États : **spécifiée** (épopée ou story `proposed` ou `ready` sans code), **implémentée** (code fusionné ou sur la branche de nuit), **testée** (tests et lignes réelles publiées). Destinations : **App** (wavelocalai), **Banc** (slm-quality-bench), **Les deux**, **Abandon**.

| # | Fonctionnalité | État dans l'ancien dépôt | Destination | Couverte par les plans actuels ? | Recommandation |
|---|---|---|---|---|---|
| 1 | Mesure runtime : TTFT, débit prompt et génération, RAM et VRAM, chauffe, N ≥ 5 répétitions, refroidissement | Testée (portable seul, 6 lignes) | Banc | Non : SPEC, non-goal « toute modification du banc existant de vitesse et d'énergie » | Ajouter au SPEC une capacité vitesse par machine (§4, idée 1) |
| 2 | Fiche matérielle hachée, citée par chaque ligne | Testée | Les deux | App : « Carte d'identité technique » (03 §3.5 Sobriété). Banc : manifeste qui bloque la reprise (AD-8) | App : afficher la fiche, sans hachage. Banc : citer la fiche dans `qb.results/1` |
| 3 | Énergie par canal (CPU, GPU, RAM) avec méthode, fenêtre active seule | Testée | Les deux | App : CodeCarbon par run, « estimé », « non mesurable » (00 §2, 03 §3.7). Banc : non-goal « mesure de l'énergie par question » | Banc : énergie par lot et par machine, hors refroidissement (§4) |
| 4 | Tables qualité et runtime jamais fusionnées | Testée | Banc | Sans objet pour l'app : l'Arène montre note, débit et CO₂ ensemble | Garder la règle dans le banc ; ne pas l'imposer à l'Arène |
| 5 | Suite de classification (20 items EN, FR, DE) et suite de publication MInDS-14 (300 items) | Testée | Banc | Non : les 7 usages du SPEC n'ont ni classification ni traduction (`SPEC.md` « Assumptions ») | Proposer l'usage au banc (§4, idée 4) |
| 6 | Traduction notée par chrF, suite WMT24++ | Testée | Banc | Non | Idem |
| 7 | Réécriture d'e-mail jugée | Spécifiée | Banc | En partie : « rédaction en français » (CAP-5) | Rattacher à la rédaction |
| 8 | Comparaison de documents | Spécifiée | Banc | Non | Basse priorité |
| 9 | Génération de code notée par ses tests en bac à sable | Implémentée, jamais lancée en conteneur | Banc | Non | À garder en idée ; coûteux |
| 10 | Planification agentique notée contre une liste d'étapes | Spécifiée | Banc | Non | Après les outils |
| 11 | Appel d'outils noté depuis la transcription, sans juge | Spécifiée | Banc | Oui : usage « outils », environnement simulé (CAP-1, AD-11) | Couvert |
| 12 | Recherche web avec réponses archivées, deux outils de recherche comparés | Spécifiée (spikes bloqués) | Abandon | Non | Abandonner : réseau pendant la campagne, contraire à « hors ligne » du SPEC |
| 13 | Réponse RAG sur un corpus local, sous un harnais nommé | Spécifiée | Les deux | Banc : « RAG long contexte » (CAP-1). App : Assistant documentaire (03 lot 2) | Couvert |
| 14 | Dimension de langue EN, FR, DE | Testée (2 suites) | Banc | En partie : le banc est surtout en français | Ajouter EN et DE à l'usage traduction |
| 15 | Deux juges de familles différentes, accord inter-juges, juge de calibration | Implémentée avec Mistral et Google ; paire GLM et DeepSeek spécifiée, jamais appelée | Banc | Oui, autrement : juge choisi sur ~100 étiquettes humaines, biais Qwen mesuré (CAP-6) | Couvert ; la méthode du banc est meilleure |
| 16 | Sujets cloud sur les mêmes suites (comparateur) | Testée (`mistral-small-2603`, 40 lignes) | Les deux | App : Arène avec cloud autorisé (D1, 03 §3.5). Banc : non, Ollama local seul | Banc : comparateur cloud sur questions publiques (§4, idée 3) |
| 17 | Intervalles par bootstrap, tests appariés, ensemble des modèles indiscernables du meilleur | Testée | Banc | Oui : Wilson, comparaisons corrigées, groupes indiscernables (CAP-7) | Couvert |
| 18 | Verdict de reproduction à trois états | Testée | Banc | En partie : manifeste et recorrection identique (CAP-3, CAP-4) | Suffisant |
| 19 | Registre de modèles épinglé (révision, fichier, sha256, drapeaux) | Testée | Banc | Oui : digest et version d'Ollama au manifeste (AD-8), `modeles.md` | Couvert |
| 20 | Profil par (modèle, machine, mode GPU ou CPU seul) | Testée (portable) | Banc | Non : SPEC limité à `tour-rtx3050` | À reprendre avec l'idée 1 du §4 |
| 21 | Trois machines, résultats renvoyés par PR, collision de hachage refusée | Implémentée ; tour et PC pro jamais mesurés (`machines.json` : `not_yet_declared`) | Banc | Non | Idem |
| 22 | Refus publié d'un modèle sous son minimum déclaré | Testée | Les deux | App : `model-picker` « tient en mémoire », avertissement (03 §3.4) | Banc : publier les refus par machine ; l'app les lit |
| 23 | Classes de taille à deux familles au moins, grille d'entrée d'un candidat | Testée (5 classes, 7 modèles) | Banc | Oui : 20 modèles choisis (`modeles.md`) | Couvert |
| 24 | Dimension moteur : llama.cpp contre Ollama | Spikes résolus, stories `proposed` | Banc | Non : Ollama seul (SPEC « Constraints ») | Option tardive du banc (§4, idée 6) ; pas dans l'app |
| 25 | Variantes d'invite : sortie concise, sortie contrainte par grammaire, compression d'entrée (LLMLingua-2) | Concise et contrainte testées (aucun effet mesurable) ; compression spécifiée | Les deux | Non | Banc : question de recherche (§4, idée 5). App : interrupteur dans le Banc d'essai (§3, idée 7) |
| 26 | Dimension harnais agentique (LangGraph, smolagents, appel direct) | Registre seul | Abandon | L'app a tranché : boucle maison (00 §6 décision 2) | Abandonner |
| 27 | Coût par ligne : prix catalogue cloud daté, kWh local | Testée | App | Non | Reprendre dans le verdict local ou cloud (§3, idée 2) |
| 28 | Service de lecture FastAPI, clé d'API, TLS, démo depuis un second portable | Testé | Abandon | Contraire à D5 (écoute sur `localhost`) et à 02 §5.5 | Abandonner |
| 29 | Tableau de bord React à 4 vues, contrat « absence déclarée » | Testé | App (le principe) | Oui pour le principe (03 §3.7, 05 §3.3) ; vues non reprises | Reprendre l'absence nommée, pas les vues |
| 30 | Vue d'ensemble : une carte par usage, meilleur local, comparateur cloud, débit et énergie | Implémentée sur fixtures | App | **Non** | Idée 1 du §3 |
| 31 | Vue dense contre MoE sur les mêmes items | Testée | App | **Non** | Idée 4 du §3 |
| 32 | Console : lancer une exécution du banc depuis le navigateur | Code fait, preuve attendue | Abandon | L'Arène montre déjà une exécution en direct (03 §3.5) | Abandonner |
| 33 | Bac à sable de chat : rien n'est enregistré ; le cloud prévient avant l'envoi | Code fait | App | Oui : Chat libre, D1, bascule cloud (03 §3.3) | Couvert |
| 34 | Chaque vue nomme la machine et le mode | Spécifiée | App | En partie : Sobriété montre la machine locale | Toute donnée du banc affichée nomme sa machine de référence |
| 35 | Journal des séances client et verdict de crédibilité d'une version | Testé | Abandon | Non | Abandonner ; une note hors dépôt suffit |
| 36 | Export en tables, Parquet, citation, archive de version, dépôt Zenodo, données en CC-BY 4.0 | Implémenté, jamais publié (pas de tag `v*`) | Banc | En partie : exports en liste blanche (AD-6), `CITATION.cff` | Garder pour la publication, plus tard |
| 37 | CI, règles de branche, image conteneur, installation depuis un clone | Testé | Les deux | App : CI à l'étape 1 (00 §4) | Garder léger |
| 38 | Comparaison de bande passante mémoire DDR4 contre DDR5 en CPU seul | Spécifiée (PRD, « Goals ») | Banc | Non | §4, idée 7 |

---

## 3. Idées nouvelles pour l'application

Classées par valeur pour l'utilisateur, absentes des plans actuels ou seulement effleurées. Les écrans renvoient à 03 §3.3. `qb.results/1` désigne le contrat de résultats que `slm-quality-bench` doit encore définir (§4, idée 2).

| Rang | Idée | Ce qu'elle apporte | Écran | Données et source | Effort |
|---|---|---|---|---|---|
| 1 | **« Quel modèle pour quel usage ? »** Une carte par usage : groupe des modèles indiscernables du meilleur, intervalle, débit sur la machine de référence la plus proche, licence | Répond en une vue à la question du DSI (Flow 1) ; c'est la vue d'ensemble que l'ancien dépôt n'a jamais branchée sur de vraies données | Nouveau sous-écran `#/arene/references`, avec une carte sur l'Accueil | `qb.results/1` : groupes et intervalles par usage et piste (CAP-7), débit par machine | M (front), plus le contrat |
| 2 | **Verdict local ou cloud** à la fin d'une comparaison : écart de note, coût pour 1 000 requêtes, CO₂, « données restées sur ce poste » | Conclut la démo par une phrase chiffrée ; reprend le PRD (« Cost », méthode 16) sans sa lourdeur | `#/arene/comparer`, sous le classement | L'app : notes du juge, tokens, CO₂ du run ; table de prix cloud **datée** dans `wavelocalai.toml` ; prix du kWh configurable | S à M |
| 3 | **« Sur d'autres postes »** : pour un modèle, débit et tenue en mémoire attendus sur la tour, le portable et le PC pro sans GPU | Sert le public « je prépare l'IA locale sur un PC ordinaire », cœur de son ambition ; montre le PC pro de 16 Go | `#/modeles` (détail d'un modèle) et Sobriété, « Carte d'identité technique » | `qb.results/1` (vitesse, mémoire, refus par machine) ; fiche locale lue par l'app | M |
| 4 | **Fiche modèle** : dense ou MoE, paramètres actifs sur totaux, quantification, famille, licence, langues revendiquées, outils et raisonnement vérifiés, scores du banc | Explique pourquoi un 35B-A3B va vite ; les champs viennent du registre de l'ancien dépôt (`architecture`, `family`, `licence`, `language_claim`) | `#/modeles`, et une pastille « MoE 3B actifs » dans le `model-picker` (03 §3.4) | L'app : `/api/show` d'Ollama ; catalogue ; `qb.results/1` pour les scores | M |
| 5 | **Export de preuve** : l'export prévu de l'Arène (CSV, Markdown) porte la fiche machine, la version d'Ollama, le digest des modèles, la date, la méthode CO₂ et le juge | Une comparaison montrée en rendez-vous devient rejouable et défendable après coup | `#/arene/comparer` (bouton « Exporter » déjà prévu en 03 §3.5) | L'app (table `runs`, 02 §5.4) | S |
| 6 | **Étiquettes de fiabilité partout** : « indicatif » (une seule question), « un seul juge », « estimé », « non mesurable », et **« bridage thermique »** quand le GPU ou le CPU ralentit | Évite qu'un débit en baisse passe pour une faiblesse du modèle pendant la démo | Composants `metric` et `badge` (03 §3.4), Santé du système (Sobriété) | L'app : NVML (températures, causes de bridage, idée de `machine_state.py`) | S |
| 7 | **Banc d'essai : « format imposé » et « réponse concise »** en interrupteurs, avec validité du format, tokens et durée avant et après | Rend tangible sa question sur la compression et le format contraint, sans attendre le banc | `#/arene/banc` (lot 5 de 03, qui vérifie déjà le JSON) | L'app : paramètre `format` (schéma JSON) d'Ollama, consigne de concision | S |
| 8 | **« Pourquoi ce débit ? »** : panneau qui relie le débit à la bande passante mémoire, aux paramètres actifs et à la VRAM, avec les chiffres de ce poste | Pédagogie de pitch tirée de `hardware.md` ; utile en atelier (Flow 2) | Sobriété, « Comment ces chiffres sont calculés » (03 §3.5), et fiche modèle | L'app : fiche locale, catalogue | S |
| 9 | **Moteur `llama-server` en option**, branché sur le port `ChatModel` par son point d'accès compatible OpenAI | Montre un gros MoE avec déport des experts (`--n-cpu-moe`, ~26 t/s sur le portable d'après `baseline_qwen36.md`) quand Ollama ne suit pas | `#/modeles` (badge de moteur) | L'app ; métriques à mapper (`timings` de llama.cpp au lieu de `eval_count`) | M ; pas avant l'étape 8 de 00 §4 |

Déjà couvert, donc non retenu : le mode présentation (03 §3.10), la bascule cloud qui prévient avant l'envoi (D1), l'absence nommée au lieu d'un zéro (03 §3.7, 05 §3.3).

Remarque sur 05 §7, leçon 13 : `slm-quality-bench` n'utilise pas llama.cpp. Son SPEC impose l'API native d'Ollama (`/api/chat`, « Constraints »). L'idée 9 est donc la seule porte vers llama.cpp, côté app.

---

## 4. Idées pour `slm-quality-bench` (à transmettre)

| # | Idée | Pourquoi | Ce que l'ancien dépôt apporte |
|---|---|---|---|
| 1 | **Capacité « vitesse, mémoire et énergie par machine »** sur les trois machines, avec un mode CPU seul | Décidé le 2026-10-18 (mémoire `migration-slm-quality-bench`) mais exclu par le SPEC (non-goals : autres machines, énergie, banc de vitesse). C'est le cœur de l'article (PC pro sans GPU) | Protocole : chauffe exclue, N ≥ 5, refroidissement **hors** fenêtre d'énergie (le biais trouvé le 2026-09-22 : 43 à 89 % d'inactivité dans la mesure), méthode par canal, origine du TTFT, causes de bridage, refus publié sous minimum |
| 2 | **Définir `qb.results/1`**, le contrat lu par l'app | Sans lui, ni l'Action GitHub ni les idées 1, 3 et 4 du §3 | Champs proposés : modèle et digest, usage, piste, score et intervalle de Wilson, groupe indiscernable, machine de référence et sa fiche, débit, mémoire crête, énergie et méthode, refus avec raison, absences nommées avec raison, version du banc |
| 3 | **Comparateur cloud** sur les seules questions publiques | Sans lui, pas de réponse « local ou cloud » ; aucune question privée ne doit partir (SPEC « Dépôt public ») | `mistral-small-2603` déjà passé sur les mêmes suites ; reprise par question sous limite de débit |
| 4 | **Usages du brief absents** : classification, traduction (chrF, WMT24++), correction de fautes, EN et DE, code en bac à sable | Listés dans `publication_ambitions.md` | Suites MInDS-14 (300) et WMT24++ avec licences vérifiées ; chrF sans dépendance |
| 5 | **Variantes d'invite** : concise, format contraint, compression d'entrée, DSL et « Caveman » | Question personnelle de l'utilisateur | Premiers résultats nuls sur Qwen3-0.6B et 20 items (« not distinguishable ») : un résultat négatif se publie ; spike LLMLingua-2 résolu (placement CPU, ~1,2 s par item, ~1,9 Go) |
| 6 | **Moteur llama.cpp contre Ollama**, en option | Question « llama.cpp ou Ollama ? » de l'utilisateur | Spike Ollama v0.35.1 : 60 des 61 tokens d'invite réutilisés d'une répétition à l'autre, aucun réglage pour l'empêcher. Rejoint le point « cache de préfixe » de la section « Deferred » du spine |
| 7 | **Bande passante mémoire** : DDR4-3200 contre DDR5-6000 en CPU seul | Résultat visé par le PRD (« Goals ») ; illustre `hardware.md` | Profils par (modèle, machine, mode) |

---

## 5. Leçons d'échec

Le rapport 05 §6 liste les signes visibles dans le code. Ceux-ci viennent des documents.

| Constat | Preuve | Garde-fou pour la prochaine version |
|---|---|---|
| **Le produit a changé de nature.** Le fondateur demandait une app (E7, E8 : front React, présentable en pitch). Le brief en a fait un banc ; le 2026-09-06, l'ajout du relecteur académique en a fait un projet de publication | `product/wave-local-ai-v2.md` ; `publication_gap_brief.md` ; 7 épopées ajoutées après | La répartition du 2026-10-18 tient : l'app ne porte aucune exigence de publication |
| **Le brief demandait de commencer étroit ; la décision n'a jamais été prise** | Brief, « Open Decisions » : « narrowing to classification, translation, and rewriting first ». Le PRD garde 9 usages, 24 règles de méthode, 4 publics | Un MVP écrit en une ligne (00 §4 : étapes 1 à 4) ; toute extension attend sa livraison |
| **La prémisse n'a jamais été vérifiée** | Brief, « Validation and Feedback » : vérifier que Q4 et le déport changent le classement. Aucun document ne tranche | Une hypothèse risquée par lot, vérifiée par une démo réelle avant le lot suivant |
| **Pilotage par questions** : 135 questions numérotées au propriétaire (Q1 à Q135), puis les décisions D1 à D8, sur trois sessions | `owner-questions.md` (2026-10-01, 10-02, 10-03), `run-log.md` | Un seul fichier de décisions, court ; une question n'est posée que si elle bloque le lot en cours |
| **Spécifications plus lourdes que le produit** : 117 stories aux titres en phrases, 18 spikes, épopées de 100 lignes avec tableaux d'inconnues | `aidd_docs/backlog/` | Au plus une page par lot ; pas de story sans écran ou commande vérifiable |
| **« Terminé » exigeait des preuves que l'agent ne peut pas produire** (second portable, appel payant, tag, conteneur Node) | 13 stories « code done, status stays ready » (`run-log.md`) | Séparer « code fait et testé » de « montré en vrai » ; la recette humaine se fait en fin de lot |
| **Choix de juges changés trois fois, jamais exécutés** | Mistral et Google, puis GLM et DeepSeek, plus GPT-5.6 Luna en calibration ; spikes `blocked` | Choisir un juge par mesure (CAP-6 du banc), puis le figer |
| **Contrat de données instable** : 30 versions de schéma, bundle publié en retard d'une version | `CHANGELOG.md`, `results/README.md` | App : schéma SQLite par migrations, contrat `qb.results/1` versionné et rarement changé |
| **Défauts de mesure trouvés tard**, après publication de résultats | Invites jamais passées au gabarit de conversation (défaut `local-subject-prompts-are-never-chat-templated`) ; énergie qui comptait le refroidissement (audit C3) | Une démo réelle et un contrôle à l'œil des sorties brutes dès le premier lot |
| **Langue et charte hors cible** : tout en anglais, interface hors charte, alors que les publics sont français | `architecture.md` « English in the repo » ; 05 §3.4 | Déjà corrigé par `AGENTS.md` (docs et interface en français, charte Wavestone) |
| **Exécutions de nuit perturbées** par la mise en veille Windows | `run-log.md`, « Root cause of the stalls » | Empêcher la veille pendant tout run long (déjà en mémoire du projet) |
| **Branche principale jamais fusionnée** | 125 commits sur `feat/night-run-2026-10-02`, PR n° 56 en brouillon | Un lot = une PR fusionnée sur `master` |

---

## 6. Documents à conserver avant la suppression

Cible : `wavelocalai/docs/archive/ancienne-v2/`. Copier avec `git show <branche>:<chemin>`. Priorité 1 : textes de l'utilisateur. Priorité 2 : ses décisions. Priorité 3 : savoir réutilisable par le banc.

| Priorité | Chemin | Branche | Raison |
|---|---|---|---|
| 1 | `context_input/publication_ambitions.md` | `main` | Ses ambitions de publication (traduction de ses notes) |
| 1 | `context_input/publication_gap_brief.md` | `main` | Son brief d'écarts et ses décisions du 2026-09-06 (machines, juges, licences, lieu de publication) |
| 1 | `context_input/hardware.md` | `main` | Ses trois machines et son constat sur la bande passante, de sa main |
| 1 | `context_input/baseline_qwen36.md` | `main` | Sa base llama.cpp validée : commande, pièges, pistes écartées |
| 1 | `context_input/model_candidates.md` | `main` | Sa sélection de modèles et la raison d'être du projet |
| 1 | `aidd_docs/product/wave-local-ai-v2.md` | `main` | Le brief produit (généré, mais porte ses décisions et ses publics) |
| 1 | `aidd_docs/tasks/2026_08/2026_08_21_expectations-gap-audit/audit-and-plan.md` | `origin/feat/night-run-2026-10-02` | Seule trace de son prompt fondateur (attentes E1 à E16) |
| 2 | `aidd_docs/tasks/2026_08/2026_08_21-wave-local-ai-v2-benchmark-suite-prd.md` | `origin/feat/night-run-2026-10-02` | Le PRD complet : objectifs, 24 règles de méthode, non-goals, stories |
| 2 | `aidd_docs/tasks/2026_10/2026_10_01_autonomous-slicing/owner-questions.md` | `origin/feat/night-run-2026-10-02` | Ses réponses aux questions de cadrage |
| 2 | `aidd_docs/tasks/2026_10/2026_10_02_backlog-refinement/owner-questions.md` | `origin/feat/night-run-2026-10-02` | Idem (Q100 à Q122) |
| 2 | `aidd_docs/tasks/2026_10/2026_10_03_owner-arbitration/owner-questions.md` | `origin/feat/night-run-2026-10-02` | Idem (Q123 à Q135) |
| 2 | `aidd_docs/tasks/2026_10/2026_10_02_night-run/run-log.md` | `origin/feat/night-run-2026-10-02` | Décisions D1 à D8, cause des blocages (veille), état final |
| 2 | `aidd_docs/tasks/2026_08/2026_08_26_google-ai-studio-spike/decision.md` | `origin/feat/night-run-2026-10-02` | Décision documentée sur Google AI Studio |
| 3 | `aidd_docs/results/README.md` | `origin/feat/night-run-2026-10-02` | Constats mesurés : fenêtre d'énergie, dense contre MoE, variantes concise et contrainte, classes de taille |
| 3 | `aidd_docs/memory/architecture.md` | `origin/feat/night-run-2026-10-02` | Pièges de llama.cpp, de l'énergie et de `detect-secrets` sous Windows |
| 3 | `aidd_docs/tasks/2026_09/2026_09_22_audit/report.md` | `origin/feat/night-run-2026-10-02` | Défauts de mesure trouvés (C1 à C3) : à éviter dans le banc |
| 3 | `aidd_docs/roster/models.json`, `machines.json`, `profiles.json`, `engines.json`, `candidate-records.jsonl` | `origin/feat/night-run-2026-10-02` | Modèles épinglés (sha256 des GGUF), faits du portable, profils par machine |
| 3 | `aidd_docs/backlog/spikes/can-a-pinned-ollama-build-serve-the-roster-gguf-under-the-runtime-protocol.md` et `does-ollama-expose-the-prompt-it-finally-rendered.md` | `origin/feat/night-run-2026-10-02` | Constat du cache d'invite d'Ollama, utile au banc |
| 3 | `aidd_docs/backlog/spikes/which-public-classification-benchmark-seeds-the-publication-suite-and-on-what-terms.md`, `which-public-translation-benchmark-seeds-the-publication-suite-and-on-what-terms.md`, `may-the-model-outputs-in-the-published-rows-be-redistributed-and-on-what-terms.md` | `origin/feat/night-run-2026-10-02` | Licences vérifiées (MInDS-14, WMT24++, sorties de modèles) pour la publication |
| 3 | `aidd_docs/backlog/spikes/which-llmlingua-2-class-compressor-fits-the-reference-machine-and-in-which-placement.md` | `origin/feat/night-run-2026-10-02` | Mesure du compresseur d'invite |
| 3 | `aidd_docs/results/quality-reference.jsonl` et `aidd_docs/results/fiches/` | `origin/feat/night-run-2026-10-02` | 926 lignes de qualité et leurs fiches ; référence brute, facultative |

Le code à récupérer est listé dans 05 §7, leçon 14. Hors dépôt : demander à l'utilisateur ses notes françaises d'origine et son prompt fondateur (§1.1).
