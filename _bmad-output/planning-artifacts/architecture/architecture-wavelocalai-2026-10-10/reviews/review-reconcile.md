# Revue de réconciliation : spine contre spec

- **Spine :** `ARCHITECTURE-SPINE.md` (draft du 2026-10-10)
- **Entrées :** `SPEC.md`, `campagne-et-reprise.md`, `pistes-et-questions.md`, `juge-et-calibration.md`, `statistiques.md`, `modeles.md`, `stories.yaml`, `AGENTS.md`
- **Vérifications faites dans le dépôt :** `.gitignore`, `pytest.ini`, `src/core/telemetry.py`, `benchmarks/results/tour-rtx3050-a2b6baf5.json`
- **Hors périmètre, comme demandé :** le déplacement du « score par métrique » vers `correction.jsonl` (AD-3) n'est relevé que là où il casse autre chose (H-2, M-4). Les reports légitimes de la section Deferred ne sont pas relevés.

## Verdict

Le spine couvre bien l'essentiel (client Ollama unique, JSONL en ajout seul, manifeste bloquant, juge découplé, isolement des imports). Deux défauts critiques peuvent toutefois ruiner une campagne de 5 à 6 jours sans alerte : la boucle d'erreurs définitives quand Ollama ne revient pas, et une empreinte de jeu qui ignore des champs qui changent la génération. Six points hauts affaiblissent des contraintes explicites de la spec (hors ligne, dépôt public, contexte, reprise après arrêt brutal). Il faut les corriger avant la story 1.

---

## Critique

### C-1. Une panne durable d'Ollama transforme toute la suite de la campagne en `erreur` définitive

- **Spine :** AD-12 (plantage : « attend que `/api/version` réponde (délai borné) […] au-delà de `essais_max`, ligne `statut = erreur` et question suivante ») ; AD-11 (« Une question en `erreur` est définitive ») ; Deferred (rejeu des erreurs reporté).
- **Source :** `campagne-et-reprise.md` § Arrêt et reprise (« nouvel essai après redémarrage ou attente du service ») ; SPEC Assumptions (« une question dont Ollama plante est enregistrée en erreur ») ; convention du spine lui-même, « Erreur du banc ≠ échec du modèle ».
- **Problème :** le spine ne dit pas ce qui se passe quand le délai borné expire. Lu tel quel, si Ollama ne revient pas la nuit, chaque question restante épuise ses essais et s'écrit en `erreur`. Ces lignes sont définitives et rien ne permet de les rejouer, puisque le rejeu est reporté. Une seule panne de service détruit le reste de la campagne. Le spine viole ainsi sa propre règle : une indisponibilité du service est une erreur du banc, pas un échec de la question.
- **Correctif :** distinguer deux cas dans AD-12.
  1. **Service indisponible** (connexion refusée, `/api/version` muet au-delà du délai borné) : le processus s'arrête avec un code non nul, sans écrire de ligne. La reprise rejoue la question.
  2. **Échec propre à la question**, le service répondant (5xx sur cette requête, OOM au chargement) : essais, puis `erreur` au-delà de `essais_max`.

  Ajouter un garde-fou : N `erreur` consécutives (par exemple 3) arrêtent la campagne.

### C-2. L'empreinte du jeu ne couvre pas tous les champs qui changent la génération

- **Spine :** AD-4 (`empreinte_prompt` = empreinte de `{"messages", "tools", "format"}`) ; AD-5 (empreinte du jeu = `[id, empreinte_prompt, empreinte_cible]` + `pistes`) ; AD-7 (`bloquant.jeu.empreinte`).
- **Source :** `campagne-et-reprise.md` § Manifeste (« les empreintes de l'ensemble des questions […] Si l'une diffère, la reprise est refusée ») ; CAP-3 (« un manifeste différent (questions, …) bloque la reprise »).
- **Problème :** `tours` (tours utilisateur suivants en multi-tours), `env` (nom@version et `etat_initial`, qui produisent les résultats d'outils pendant la génération), `num_ctx` et `usage` (qui fixent le plafond `num_predict`) ne sont dans aucune empreinte. Les `criteres`, lus par le jugement, n'y sont pas non plus. Modifier l'un d'eux laisse l'empreinte du jeu inchangée : la reprise accepte de mêler deux jeux dans le même `generation.jsonl`, et le jugement accepte des critères changés.
- **Correctif :** définir l'empreinte de la question sur la ligne canonique entière de `questions.jsonl`, hors champs d'empreinte. Ajouter `tours`, `env`, `num_ctx` et `usage` à `empreinte_prompt`, et garder `empreinte_cible` à part pour l'index public. Empreinte du jeu = empreinte de la liste triée des empreintes de lignes, plus `pistes`. Ajouter une empreinte des `criteres` au bloc `bloquant.juge` du manifeste de jugement.

---

## Haute

### H-1. La règle « hors ligne pendant la génération » est réduite à un isolement d'imports

- **Spine :** AD-14 (test AST sur le graphe d'import de `generation/`) ; AD-15 (le juge local vérifie `/api/ps` au démarrage) ; AD-13 (« Un seul processus de génération à la fois sur la machine », sans mécanisme) ; AD-2 (verrous par campagne seulement).
- **Source :** SPEC Constraints, Hors ligne (« aucun téléchargement ni appel réseau **pendant** la génération […] Le juge local tourne sous llama.cpp, jamais en même temps que la génération ») ; `campagne-et-reprise.md` § Jugement (« lancée après la génération […] Elle seule a le droit au réseau ») ; AGENTS.md / `docs/PROMPT_NOUVELLE_MACHINE.md` (aucun téléchargement pendant une campagne, qui coûte jusqu'à 30 % de débit).
- **Problème :** la contrainte de la spec est temporelle, à l'échelle de la machine. Rien n'empêche de lancer `juger` en cloud, ou `jeu` avec téléchargements, pendant que `generer` tourne. Rien n'empêche non plus `generer` de démarrer alors que le serveur Winnow occupe la VRAM, puisque le contrôle `/api/ps` ne joue que dans un sens et seulement au démarrage. Le verrou par campagne n'empêche pas deux campagnes simultanées.
- **Correctif :** poser un verrou machine sous `BENCH_QUALITE_DATA` (par exemple `.generation-active`), pris par `generer`. Avec ce verrou :
  - `juger` (toutes configurations) et les téléchargements de `jeu` refusent de démarrer tant qu'il est tenu ;
  - `generer` refuse de démarrer si le verrou du juge est tenu ou si le port du serveur Winnow répond.

### H-2. L'export versionné n'interdit pas explicitement la réponse parsée ni la réflexion des questions privées

- **Spine :** AD-14 (versionné : « scores par question **sans** `sortie` ») ; AD-3 (score dans `correction.jsonl`, jointure par `cle`) ; AD-6 (`reponse_parsee`, `erreur`) ; AD-9 (`metriques`).
- **Source :** SPEC Constraints, Dépôt public (« aucune réponse brute à une question privée […] dans un commit ou une PR ») ; story 10 (« Seuls les scores par question indexés par empreinte, les agrégats et le manifeste entrent dans le dépôt ») ; AGENTS.md (aucun extrait de réponse dans un commit).
- **Problème :** l'export se définit par exclusion (« sans `sortie` »). Or l'export joint génération et correction (conséquence d'AD-3), et la ligne de génération porte aussi `reponse_parsee`, soit le JSON extrait d'un document privé, ainsi que `erreur`, qui peut citer le contenu. `metriques` est libre. Une liste noire laisse fuir tout champ ajouté plus tard.
- **Correctif :** décrire l'export par une **liste blanche** de champs (`cle`, `question_id`, `empreinte_prompt`, `empreinte_cible`, `modele`, `piste`, `usage`, `groupe`, `statut`, `score`, `reussite`, `metriques` numériques seulement, `tokens`, `durees_ns`, `essais`), avec un schéma `bq.export/1`. Ajouter un test qui échoue si l'export contient une chaîne issue de `sortie` ou de `reponse_parsee`.

### H-3. Le score strict de VAR-MATH (toutes les variantes) n'a pas de place dans le contrat

- **Spine :** AD-9 (`corriger(question, generation, verdicts)` par question) ; AD-16 (McNemar par question).
- **Source :** `pistes-et-questions.md`, ligne Raisonnement (« score strict : un problème n'est réussi que si toutes ses variantes le sont »).
- **Problème :** un correcteur pur par question ne peut pas exprimer une réussite définie sur un groupe de variantes. L'unité d'analyse (question ou problème) change le N, la table de McNemar et la puissance. Laissé à chaque story, ce point sera tranché différemment par `correction/` et par `stats/`.
- **Correctif :** ajouter au schéma de question un champ d'agrégation (par exemple `unite: "question" | "groupe_strict"`, ou `correcteur.params.strict = true`), et fixer dans AD-9 ou AD-16 où se calcule la réussite de groupe (dans `stats/`, à partir des `reussite` par question). L'unité de McNemar devient alors le problème, pas la variante.

### H-4. Pas de garde contre la troncature silencieuse du prompt, ni contre un `num_ctx` hors des moyens du modèle

- **Spine :** AD-5 (`num_ctx` pris parmi `paliers_num_ctx`) ; AD-8 (`options.num_ctx`, `options.num_predict`) ; AD-13 (paliers).
- **Source :** SPEC Constraints, Machine (« Contexte long plafonné entre 8K et 32K **selon la mémoire** ») ; `pistes-et-questions.md` (OneRuler « de 8K à 32K selon la mémoire ») ; `campagne-et-reprise.md` (surveiller le préremplissage).
- **Problème :**
  - Aucune règle n'impose `num_ctx ≥ tokens du prompt + num_predict`. Les conversations multi-tours grossissent à chaque appel. Si la condition n'est pas tenue, Ollama tronque ou décale le contexte en silence et fausse les questions RAG et outils.
  - Rien ne traite un `num_ctx` de 32K pour un modèle dont la longueur de contexte native (lue dans `/api/show`) est plus courte, ou qui ne tient pas en mémoire (`qwen3.6:35b-a3b`, pic à 27,5 Go).
  - Une question sautée pour un seul modèle casse l'appariement.
- **Correctif :**
  1. À la construction du jeu, vérifier `num_ctx ≥ prompt estimé + plafond maximal + marge`.
  2. À la génération, contrôler `prompt_eval_count` de chaque appel contre `num_ctx - num_predict` et marquer la ligne (statut dédié, par exemple `contexte_depasse`, compté comme erreur du banc).
  3. Lire la longueur de contexte native dans `/api/show` et refuser au lancement (préflight) tout couple (modèle, palier) impossible, avec une décision consignée : palier commun abaissé ou modèle exclu de l'usage RAG pour tous.

### H-5. Un verrou PID resté après un arrêt brutal bloque la reprise

- **Spine :** AD-2 (« `campagnes/<c>/.verrou` (PID) »).
- **Source :** CAP-3 (« un arrêt brutal du processus puis une reprise donnent un JSONL sans doublon ni trou ») ; story 1 (test d'arrêt brutal puis reprise).
- **Problème :** un processus tué laisse `.verrou`. Le spine ne dit ni comment reconnaître un verrou périmé ni comment traiter la réutilisation des PID sous Windows. Selon l'implémentation, la reprise est refusée à tort, ou un verrou est volé à tort.
- **Correctif :** utiliser un verrou de fichier du système (`msvcrt.locking` sous Windows, `fcntl.flock` ailleurs), que le système libère à la mort du processus. Garder le PID et l'heure de démarrage dans le fichier, à titre informatif seulement. Ajouter le test au plan de la story 1.

### H-6. Un modèle « cloud » d'Ollama ferait sortir des questions privées malgré l'URL limitée à `localhost`

- **Spine :** AD-8 (« URL de base limitée à `localhost` / `127.0.0.1` ») ; AD-14.
- **Source :** SPEC Constraints (aucun appel réseau pendant la génération ; aucune question privée ne quitte la machine, `juge-et-calibration.md` § Critères) ; AGENTS.md (le dépôt connaît déjà les modèles cloud : `test_pull_model_cloud_raises_error`).
- **Problème :** les versions récentes d'Ollama servent des modèles distants (tags `…-cloud`, champs `remote_host` / `remote_model` dans `/api/show`) par le serveur local. Une requête vers `localhost` peut donc partir sur le réseau. Aucun des 20 modèles n'est concerné aujourd'hui, mais rien ne l'interdit dans la configuration.
- **Correctif :** dans AD-8, refuser au préflight tout modèle dont `/api/show` déclare un hôte distant ou dont le tag porte le suffixe cloud. Exiger un `digest` présent dans `/api/tags`, donc des poids locaux.

---

## Moyenne

### M-1. L'arrêt propre de la phase de jugement n'est pas spécifié

- **Spine :** AD-15 (renvoie à AD-7 et AD-11, pas à AD-12) ; AD-12 (ne nomme que `campagnes/<c>/STOP`).
- **Source :** `campagne-et-reprise.md` § Jugement (« la même mécanique de manifeste, **d'arrêt** et de reprise ») ; story 7.
- **Correctif :** étendre AD-12 à `juger`, avec un fichier `jugement-<juge>/STOP` et un drapeau lu entre deux items. Pendant l'attente d'un lot cloud, l'arrêt sort sans annuler le lot, qui sera relu depuis `lots.jsonl`.

### M-2. Aucune règle pour lire un JSONL qu'un autre processus est en train d'écrire

- **Spine :** AD-11 (règles du seul écrivain : troncature du fragment final ; « une ligne illisible […] arrête le processus »).
- **Source :** CAP-5 (le jugement relit le JSONL de génération) ; CAP-4 (recorrection).
- **Problème :** `juger` ou `corriger` peuvent lire `generation.jsonl` pendant une génération ou après un arrêt brutal. S'ils appliquent la règle de l'écrivain, ils tronquent un fichier qui ne leur appartient pas (violation d'AD-2) ou s'arrêtent sur le fragment final.
- **Correctif :** ajouter à `commun/jsonl.py` une règle de lecteur : ignorer sans tronquer un fragment final sans `\n`, s'arrêter sur toute autre ligne illisible.

### M-3. Le juge retenu n'est pas figé « avant la campagne », et le manifeste de jugement est incomplet

- **Spine :** AD-15 (« désigné dans la configuration de correction ») ; AD-7 (`bloquant.juge` = identifiant, modèle, seuils ; `juge: null` pour la génération).
- **Source :** CAP-6 (« le choix du juge est consigné avant la campagne ») ; `juge-et-calibration.md` § Décision (« consigné avant la campagne et figé dans le manifeste du jugement »).
- **Correctif :**
  - consigner `juge_retenu` dans `complete-AAAAMMJJ.yaml`, donc dans le bloc `bloquant` du manifeste de génération de la campagne complète ;
  - ajouter à `bloquant.juge` l'identifiant exact du modèle cloud (version datée), l'empreinte du gabarit de prompt du juge, l'empreinte du GGUF de Winnow et la version du serveur `winnow-inference`.

### M-4. `correction.jsonl` ne porte ni manifeste ni juge source (effet de bord d'AD-3)

- **Spine :** AD-9 (ligne `bq.correction/1` sans `manifeste`) ; AD-7 (« Chaque ligne JSONL porte `manifeste` ») ; AD-3.
- **Problème :** il y a contradiction interne. Comme le score ne vit plus que dans `correction.jsonl`, une recorrection faite contre un autre `generation.jsonl` ou un autre dossier `jugement-<juge>/` ne laisse aucune trace, et le rapport peut joindre des fichiers incohérents.
- **Correctif :** ajouter `manifeste` (empreinte du bloc bloquant de génération) et `jugement` (empreinte du manifeste de jugement lu, ou `null`) à chaque ligne de correction, ou un en-tête de manifeste de correction. Le rapport refuse une jointure aux empreintes discordantes.

### M-5. AD-16 ne reprend qu'une partie des méthodes de `statistiques.md`

- **Spine :** AD-16.
- **Source :** `statistiques.md` (Entre modèles, Classement, Troncature, Validation externe) ; CAP-7.
- **Manquent :**
  - la différence avec son erreur-type appariée et son IC à 95 % ;
  - la corrélation entre modèles, à publier en plus de la valeur p ;
  - Holm sur les k−1 comparaisons au meneur ;
  - le rang approché par IC simultanés ;
  - k̂_Bonferroni pour les conclusions transversales ;
  - l'exclusion de Friedman/Nemenyi et du test non apparié de deux proportions ;
  - le taux de troncature par modèle et par usage, publié séparément ;
  - les règles de Spearman : seulement les indices AA mesurés, test unilatéral à α = 0,05, IC bootstrap de ρ, aucune conclusion sous 8 modèles, et aucun Spearman au pilote (story 8).
- **Correctif :** écrire « toutes les méthodes de `statistiques.md` sont normatives », puis lister celles-ci, ou les reporter explicitement dans Deferred vers la story 6.

### M-6. `reussite` n'est pas défini pour les usages à F1 (RAG, extraction)

- **Spine :** AD-9 (« `reussite` booléen pour les usages binaires, `null` pour la rédaction »).
- **Source :** `pistes-et-questions.md` (RAG : correspondance exacte et F1 ; extraction : schéma puis valeurs) ; `statistiques.md` (bootstrap apparié pour le F1 d'extraction).
- **Problème :** le spine ne dit pas si RAG et extraction sont binaires, ni sur quel seuil. McNemar contre bootstrap, et Wilson contre moyenne, se décideront correcteur par correcteur.
- **Correctif :** ajouter un tableau usage → métrique principale (binaire ou continue) → test, et un seuil explicite de `reussite` si un usage continu doit aussi entrer dans McNemar.

### M-7. Le préremplissage n'est pas surveillé

- **Spine :** absent (AD-6 consigne `prompt_eval`, sans règle d'alerte).
- **Source :** `campagne-et-reprise.md` § Hygiène (« Surveiller le temps de préremplissage : un modèle trop gros déborde en RAM partagée sans OOM, et le préremplissage s'effondre »).
- **Correctif :** après la chauffe de chaque couple (modèle, `num_ctx`), lire `/api/ps` (`size` contre `size_vram`) et le débit de préremplissage. Journaliser un avertissement sous un seuil de la configuration, et garder la valeur dans une ligne de journal ou un fichier `chauffes.jsonl` pour la projection.

### M-8. La projection de durée hérite d'un débit de préremplissage mesuré à ~2,3K tokens

- **Spine :** CAP-8 → `rapport/` (projection) ; diagramme (`REF (ancien banc)`).
- **Source :** `campagne-et-reprise.md` § Pilote et story 8 (« préremplissage compris ») ; SPEC Assumptions (prompt RAG de 16K en moyenne). Dans le dépôt, `tour-rtx3050-a2b6baf5.json` mesure `prefill_tokens_per_second` à `prefill_prompt_tokens` ≈ 2 265.
- **Problème :** le spine ne dit pas d'où vient le débit de préremplissage des 16 modèles absents du pilote. Celui de l'ancien banc, mesuré sur des prompts courts, surestime fortement le débit à 16K–32K.
- **Correctif :** nommer la source dans le spine. Par exemple : ratio de dégradation du préremplissage par palier mesuré sur les 4 modèles du pilote, appliqué au débit de l'ancien banc ; ou sonde de chauffe par (modèle, palier) hors campagne, sans téléchargement.

### M-9. Le sous-ensemble du rejeu de stabilité n'a pas de représentation

- **Spine :** AD-4 (campagne `<campagne>-rejeu`) ; AD-7 (`bloquant.jeu` = jeu complet).
- **Source :** CAP-8 (« taux de réponses changeantes sur un sous-ensemble rejoué ») ; `campagne-et-reprise.md` § Pilote.
- **Correctif :** ajouter à la configuration de campagne un champ `sous_ensemble`, soit une liste d'id, soit un tirage stratifié avec sa graine et sa taille, inclus dans `bloquant.config`.

### M-10. `.venv-qualite` n'est pas ignoré par git, contrairement à ce qu'affirme le spine

- **Spine :** Stack (« venv dédié `.venv-qualite`, ignoré par git »).
- **Constat :** `.gitignore` ne contient que `.venv/`, `.venv-app/`, `venv/` et `data/`.
- **Correctif :** ajouter `.venv-qualite/` à `.gitignore` dans la story 1, et corriger la formulation du spine (« à ajouter à `.gitignore` »).

### M-11. Il manque des dépendances, et le code emprunté peut télécharger pendant la correction

- **Spine :** Stack ; AD-1 (exception `src.core.telemetry`).
- **Source :** `pistes-et-questions.md` (dépendances IFBench, `pydantic` compris) ; SPEC Constraints, Python (« toutes les dépendances installées avant la campagne ») ; CAP-4 (« se rejoue hors ligne »).
- **Problème :**
  - `src/core/telemetry.py` importe `dotenv` : `python-dotenv` doit figurer dans `scripts/bench_qualite/requirements.txt`.
  - `pydantic` manque à la pile.
  - Les vérificateurs IFBench s'appuient sur des données NLTK (tokeniseur `punkt`/`punkt_tab`). Le code d'origine peut appeler `nltk.download` à l'import, ce qui ferait du réseau pendant `corriger`.
- **Correctif :**
  - ajouter `python-dotenv` et `pydantic`, versions vérifiées sur PyPI ;
  - lister les données NLTK à installer avant la campagne ;
  - exiger dans `PROVENANCE.md` le retrait de tout téléchargement à l'import du code emprunté ;
  - étendre le test AST d'AD-14 à `correction/` (pas de `nltk.download` ni de `huggingface_hub`).

### M-12. Des identifiants de code sont en français, contre AGENTS.md et la convention du spine lui-même

- **Spine :** Consistency Conventions, Langue (« Identifiants de code en anglais sauf les noms de champs JSON et de commandes ») ; Structural Seed et AD-9 / AD-15 (`commun/`, `juge/`, `rapport/`, `registre.py`, `corriger()`, `Juge.juger()`, `Note`, `Verdict`).
- **Source :** AGENTS.md Policy (« identifiants de code en anglais »).
- **Correctif :** renommer les paquets et l'API (`common/`, `judge/`, `grading/`, `report/`, `registry.py`, `grade()`, `Judge.judge()`, `Grade`) en gardant le français pour les champs JSON et les commandes CLI. Autre option : déclarer l'exception explicitement et la faire valider par Anaël.

### M-13. Des conditions de mesure ne sont ni consignées ni bloquantes

- **Spine :** AD-7 (`informatif.machine` ; pas de variables d'environnement d'Ollama) ; Deferred (méthode de vérification de `OLLAMA_NUM_PARALLEL`).
- **Source :** SPEC Constraints (« tour-rtx3050 seule » ; une seule version d'Ollama « épinglée ») ; `campagne-et-reprise.md` (`OLLAMA_NUM_PARALLEL=1`).
- **Problème :**
  - Une reprise sur une autre machine mêlerait durées et non-déterminisme GPU sans blocage.
  - `OLLAMA_NUM_PARALLEL`, `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE` et `OLLAMA_CONTEXT_LENGTH` changent les sorties ou les durées, mais ne sont pas relevés.
  - La mise à jour automatique de l'application Ollama sous Windows peut changer la version au redémarrage. Le spine la détecte (arrêt), mais ne la prévient pas.
- **Correctif :**
  - passer `machine` dans `bloquant` ;
  - relever dans le manifeste les variables `OLLAMA_*` lisibles depuis l'environnement du service, sans attendre la méthode de la story 1 pour le relevé lui-même ;
  - ajouter au préflight (ou à la checklist de campagne) la neutralisation de la mise à jour automatique d'Ollama.

---

## Basse

- **B-1. Plafond par appel ou par question.** AD-8 fixe `num_predict` par requête. Une question outils multi-appels peut cumuler plusieurs plafonds. *Source :* `pistes-et-questions.md` (raison du plafond : ~2 min par réponse). *Correctif :* dire si le plafond est par appel (et si `tronque` se déclenche par appel), ou ajouter un budget de tokens par question.
- **B-2. « `format` fixé explicitement ».** La spec demande de fixer `format` à chaque requête ; le spine écrit « schéma ou absent ». Il faut aussi détecter un modèle qui réfléchit quand même en piste coupée. *Correctif :* consigner dans la ligne la présence de `thinking` en piste coupée, et compter ces cas au rapport de pilote.
- **B-3. Politique git incomplète.** Il manque la fusion par merge commit (jamais de squash) et le préfixe `Bench:` pour les commits de résultats (AGENTS.md). *Correctif :* compléter la ligne Git des Conventions.
- **B-4. Charte Wavestone.** Si `rapport/` produit des graphiques ou du HTML, il doit suivre la charte (primaire `#451DC7`, icônes Material, aucun emoji décoratif ; AGENTS.md). *Correctif :* une ligne dans les Conventions.
- **B-5. « Cinq phases ».** Le Design Paradigm annonce cinq phases et n'en nomme que quatre (jeu, génération, correction et jugement, rapport). *Correctif :* aligner le compte.
- **B-6. Versions de la pile.** Les dépendances IFBench sont données en valeurs exactes alors que le texte annonce des bornes inférieures. *Correctif :* écrire `≥`.
- **B-7. Emplacement de `STOP`.** Deux dossiers `campagnes/` coexistent : les YAML versionnés sous `scripts/` et les données sous `data/bench_qualite/`. AD-2 et AD-12 écrivent `campagnes/<c>/` sans racine. Un `STOP` présent au lancement n'est pas traité. *Correctif :* écrire `$BENCH_QUALITE_DATA/campagnes/<c>/STOP`, et supprimer (avec journalisation) un `STOP` trouvé au lancement, ou refuser de démarrer.
- **B-8. Tests et `data/`.** AGENTS.md interdit de vider ou réinitialiser `data/`. *Correctif :* tous les tests de `tests/bench_qualite/` fixent `BENCH_QUALITE_DATA` sur `tmp_path` ; ajouter une fixture `autouse`.
- **B-9. `pytest.ini`.** Il fixe `asyncio_mode = auto` et `testpaths = tests`. Sans `pytest-asyncio` dans `.venv-qualite`, on obtient un avertissement de configuration ; un `pytest` nu dans `.venv` collecte `tests/bench_qualite` (le `conftest.py` de saut le couvre). *Correctif :* ajouter `pytest-asyncio` à la pile de test ou documenter l'avertissement.
- **B-10. Licences et exclusions.** Valeurs manquantes : domaine public (bottes de foin de OneRuler), traductions de le-leadboard. Les exclusions ne sont pas imposées par la structure. Les traductions de le-leadboard exigent une relecture de 30 items. *Correctif :* fermer la liste des licences dans les Conventions et ajouter une liste de sources refusées dans `questions/`.
- **B-11. Déchargement à l'arrêt propre.** AD-13 décharge un modèle seulement en fin de modèle. Après Ctrl+C, le modèle reste chargé jusqu'à 5 min, et `juger` en local refuse alors de démarrer. *Correctif :* `keep_alive: 0` aussi à la sortie sur arrêt propre.
- **B-12. Repli Perplexity Decider.** AD-15 énumère quatre implémentations, et le repli en ajouterait une cinquième. *Correctif :* ajouter « + repli `decider` si Winnow est écarté » à la liste.
- **B-13. Téléchargement du GGUF de Winnow.** Le spine ne dit pas qui le télécharge, alors que `huggingface_hub` est réservé à `questions/import_publics/`. *Correctif :* téléchargement manuel documenté, ou commande dédiée hors `juge/`.
- **B-14. Biais Qwen.** Aucun attribut ne marque un candidat comme Qwen. *Correctif :* ajouter `famille` aux modèles de la configuration.
- **B-15. Clé de reprise.** La spec écrit « graine » ; le spine utilise `seed` et réserve `graine` au générateur. La décision est bonne mais mérite une phrase de correspondance explicite dans AD-4.

---

## Points vérifiés sans écart

- Champs de la ligne de génération : tous présents (hors score, voir AD-3), avec `statut = tronque` pour l'indicateur de troncature.
- Contenu du manifeste : jeu, configuration, version d'Ollama, et message qui nomme la différence.
- `fsync` après chaque ligne, saut des clés présentes, ligne partielle finale rejouée.
- Requête de chauffe, `/api/show` avant `tools` et `think`, exclusion des modèles qui déclarent `decision`, validation `jsonschema` côté client.
- Juge cloud interdit sur les questions privées, clés d'API par l'environnement.
- Isolement de `benchmark_slm.py` et de `src/core/`, avec la seule exception `disable_telemetry` (story 1).
- Python 3.10+, versions relevées sur PyPI, aucune installation dans `.venv` ni `.venv-app`.
- PR de résultats limitée à `benchmarks/qualite/`.
- Indices AA lus hors ligne depuis un fichier daté (mesuré ou estimé, variante).
- Holm via `method="holm"`, BH réservé à la matrice exploratoire.
- Veille Windows par `SetThreadExecutionState`.
