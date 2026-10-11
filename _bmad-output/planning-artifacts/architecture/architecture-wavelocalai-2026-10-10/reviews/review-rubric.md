---
reviewed: ../ARCHITECTURE-SPINE.md
date: 2026-10-10
reviewer: relecteur indépendant (grille « good spine »)
verdict: à réviser avant les stories : socle solide, 1 point critique et 7 points hauts à corriger
---

# Revue de la spine « Banc de qualité difficile (bench_qualite) »

## Verdict

La spine est dense, bien ancrée dans la spec et presque partout applicable : un écrivain par fichier, une clé et un JSON canonique uniques, des contrats de ligne explicites, un client Ollama propriétaire unique, des statistiques pures et une reprise rigoureuse. Elle traite la plupart des vrais points de divergence entre les 10 stories.

Il reste un point critique, la confidentialité. Les exports versionnés sont définis par **liste d'exclusion**, ce qui laisse passer du contenu privé. Il reste aussi plusieurs trous de contrat entre stories : empreintes incomplètes, score strict par problème, emplacement de la calibration, propriétaire des schémas de ligne et de la configuration, verrou machine. Enfin, deux hypothèses sur le dépôt sont fausses : `python-dotenv` manque au venv dédié, et `.venv-qualite` n'est pas ignoré par git.

## Vérifications effectuées sur le dépôt

| Point | Constat |
| --- | --- |
| `python -m scripts.bench_qualite` sans `scripts/__init__.py` | **Fonctionne** : `scripts` se résout en paquet d'espace de noms (vérifié : `find_spec('scripts')` → origine `None`, emplacement `…/wavelocalai/scripts`). Seul risque résiduel : un paquet *régulier* `scripts` installé dans `site-packages` du venv l'emporterait (PEP 420). |
| `src/` | Pas d'`__init__.py` dans `src/` ni dans `src/core/` : `from src.core.telemetry import disable_telemetry` marche depuis la racine. Mais `telemetry.py` importe `dotenv`. |
| `data/` ignoré | Oui (`.gitignore:69`, motif `data/` **à toute profondeur**). |
| `benchmarks/qualite/…`, `scripts/bench_qualite/campagnes/*.yaml` | Non ignorés (correct). |
| `.venv-qualite/` | **Non ignoré** : `git check-ignore -q .venv-qualite/pyvenv.cfg` → 1. Seuls `.venv/` et `.venv-app/` le sont. |
| Test AST de télémétrie | Il parcourt `src/**/*.py` et `scripts/**/*.py`, donc il couvre le paquet. Mais il **exige** que tout importeur figure dans `TELEMETRY_IMPORTERS`, ce qui impose de modifier le test. `datasets` n'est pas dans `TELEMETRY_ROOTS`. L'appel doit être un `disable_telemetry()` nu, au niveau module, placé avant toute ligne d'import de la bibliothèque, y compris dans une fonction. |
| `pytest.ini` | `testpaths = tests` : un `pytest` nu collecte `tests/bench_qualite`. `addopts` n'exclut que `e2e`, pas `integration`. `--strict-markers` : seul `integration` existe déjà. |
| pre-commit | `detect-secrets` (HexHighEntropyString, limite 3.0) et `check-added-large-files --maxkb=5000` tournent sur tout fichier hors `_bmad/` et `.claude/skills/bmad-*`. L'exclusion de `_bmad/` a été posée parce que des SHA y étaient pris pour des secrets. black, isort et `ruff --fix` tournent sur tout le Python. |
| Mermaid | Les 3 diagrammes sont syntaxiquement valides (formes `[( )]` et `[[ ]]`, chaînage `&`, nœud isolé `stats`, `subgraph id[titre]`, texte de lien `-- x -->`). |

## Critique

### C1 — Fuite de contenu privé par les exports versionnés définis en liste d'exclusion
- **Où :** AD-5 (index versionné « sans `messages`, `tours`, `tools`, `format`, `cible` ni `criteres` ») ; AD-14 (« scores par question **sans** `sortie` »).
- **Problème :** l'index garde `env` (dont `etat_initial`) et `correcteur.params`. Pour une question privée d'outils ou d'extraction, `etat_initial` contient le contenu FR privé (fichiers, documents), et `params` peut porter la réponse attendue. Côté scores, une jointure « génération sans `sortie` » garde `reponse_parsee`, c'est-à-dire le JSON extrait d'un document privé, ainsi que `erreur`, qui peut citer la réponse. Le dépôt est public : une fuite poussée ne se rattrape pas (AGENTS.md : « aucun extrait de réponse RAG »).
- **Correctif :** remplacer les listes d'exclusion par des **listes blanches** fixées dans la spine :
  - index : `schema, id, usage, groupe, source, licence, prive, generateur, graine, num_ctx, env.nom, correcteur.nom, empreinte_prompt, empreinte_cible` ;
  - score versionné (nommer son schéma, par ex. `bq.score/1`) : `cle, question_id, modele, piste, seed, usage, groupe, statut, score, reussite, metriques numériques, tokens, durees_ns, manifeste`.
  - Ajouter un test de `tests/bench_qualite/` qui vérifie que tout fichier écrit sous `benchmarks/qualite/` ne contient que ces clés.

## Haut

### H1 — Les empreintes ne couvrent pas tout ce qui change la génération ou la note
- **Où :** AD-4 (`empreinte_prompt` = `{messages, tools, format}` ; `empreinte_cible` = `cible`) ; AD-5 (empreinte du jeu) ; AD-7 (le jeu bloque par son empreinte).
- **Problème :** une modification de `tours` (tours suivants d'une conversation), de `env` (`nom`, `etat_initial`), de `num_ctx`, de `correcteur` (`nom@version`, `params`) ou de `criteres` ne change ni l'empreinte de la question ni celle du jeu. Une reprise accepterait donc un jeu modifié et mélangerait deux versions d'une question sous la même clé, ce qu'AD-7 doit justement empêcher.
- **Correctif :**
  - `empreinte_prompt` = empreinte de `{messages, tours, tools, format, env, num_ctx}` ;
  - `empreinte_cible` = empreinte de `{cible, correcteur, criteres}` ;
  - ou une troisième empreinte `empreinte_question` sur la ligne entière moins les empreintes, reprise dans l'empreinte du jeu.

### H2 — Score strict par problème (VAR-MATH) et unité de tirage absents du contrat
- **Où :** AD-9 (correcteur pur **par question**) ; AD-5 (`pistes.json`, « tirage stratifié par usage ») ; AD-16. La source est `pistes-et-questions.md` : « un problème n'est réussi que si toutes ses variantes le sont ».
- **Problème :** cette règle porte sur un groupe de questions, pas sur une question. Rien ne dit qui l'applique. Le correcteur ne voit qu'une question ; `stats/` ne sait pas qu'un usage se compte par problème ; la paire McNemar devient alors le problème. De plus, un tirage par question pour la piste activée peut casser un groupe (variantes, conversation multi-tours), ce qui rend le score strict incalculable et fausse le N compté en groupes.
- **Correctif :** ajouter à AD-5 un champ `agregation: "question" | "groupe_strict"` (ou une propriété du correcteur dans le registre). Ajouter à AD-16 la règle : pour `groupe_strict`, l'unité statistique est le groupe, réussi si toutes ses questions le sont, et elle est calculée dans `stats/` depuis `correction.jsonl`. Ajouter à AD-5 que le tirage de `activee` se fait **par groupe** au sein de chaque usage.

### H3 — Pas de propriétaire pour les schémas de ligne ni pour la configuration résolue ; le graphe des dépendances l'interdit de fait
- **Où :** graphe « Sens des dépendances » (aucune flèche `__main__ → commun`) ; liste de `commun/` (« canonique, jsonl, manifeste, verrou, arret, veille, chemins ») ; AD-6, AD-9, AD-15 ; Conventions « Schémas » (« le lecteur refuse un `<n>` inconnu »).
- **Problème :** `correction/` lit `generation.jsonl` et `jugement.jsonl` mais n'a le droit d'importer ni `generation/` ni `juge/`. `rapport/` lit `correction.jsonl` sans pouvoir importer `correction/`. Chaque story écrira donc son propre lecteur de `bq.generation/1` et de `bq.jugement/1`, et son propre contrôle de version de schéma : c'est exactement la divergence qu'une spine doit empêcher. Il en va de même pour le chargement du YAML de campagne et le calcul de `config.empreinte` sur la configuration *résolue* (AD-7), dont `generer`, `juger` et `corriger` ont tous besoin et qui n'ont aucun module attitré. Enfin, `__main__` doit importer `commun` (chemins, journal, configuration) et le graphe l'interdit.
- **Correctif :**
  - ajouter `commun/schemas.py`, seul lieu des types et validateurs `bq.question/1`, `bq.generation/1`, `bq.jugement/1`, `bq.correction/1`, `bq.manifeste/1` et du refus de version inconnue ;
  - ajouter `commun/config.py`, seul lieu du chargement YAML, des valeurs par défaut et de l'empreinte ;
  - ajouter la flèche `main --> commun` et `stats` comme seule exception sans dépendance.

### H4 — Aucun verrou au niveau de la machine : deux générations, ou Winnow et Ollama, peuvent tourner ensemble
- **Où :** AD-2 (verrous `campagnes/<c>/.verrou` et `jugement-<juge>/.verrou`, par campagne) ; AD-13 (« un seul processus de génération à la fois sur la machine ») ; AD-15 (`/api/ps` vérifié **au démarrage** seulement).
- **Problème :** rien n'applique AD-13. `pilote-X` et `pilote-X-rejeu` peuvent tourner en même temps, ce qui fausse les durées et sature la VRAM. Un `generer` lancé après un `juger` local charge un modèle pendant que Winnow occupe la VRAM, alors que le contrôle `/api/ps` est déjà passé. Un juge cloud lancé pendant `generer` fait du réseau pendant la génération, ce que la spec interdit (« Hors ligne »).
- **Correctif :** ajouter un verrou exclusif `BENCH_QUALITE_DATA/.verrou-machine`, pris par `generer` et par tout `juger`, local ou cloud, pendant toute leur durée. `corriger` et `rapport` ne le prennent pas.

### H5 — `python-dotenv` absent du venv dédié : l'exception d'AD-1 casse à l'import
- **Où :** AD-1 et AD-14 (`from src.core.telemetry import disable_telemetry`) ; Stack.
- **Problème :** `src/core/telemetry.py` fait `from dotenv import load_dotenv`. Dans `.venv-qualite`, construit depuis `scripts/bench_qualite/requirements.txt`, cet import lève `ModuleNotFoundError` dès la story 2. La Stack omet aussi `pydantic` (dépendance d'IFBench listée dans `pistes-et-questions.md`), `datasets` (cité par AD-14) et les données `nltk` (`punkt` / `punkt_tab`), alors que la spec exige que « toutes les dépendances [soient] installées avant la campagne ».
- **Correctif :** ajouter à la Stack `python-dotenv`, `pydantic` et `datasets` (ou retirer `datasets` d'AD-14), avec des bornes vérifiées sur PyPI. Ajouter aussi « données nltk à télécharger avant la campagne », à côté des modèles spaCy.

### H6 — Recorrection non déterministe et téléchargement implicite dans le code emprunté
- **Où :** AD-9 et la convention « Code emprunté » ; succès de CAP-4 (« recorriger un JSONL donne des scores identiques »).
- **Problème :** les vérificateurs IFBench et M-IFEval utilisent `langdetect`, qui est aléatoire tant que `DetectorFactory.seed` n'est pas fixé : deux corrections du même JSONL peuvent différer sur les consignes de langue. Leurs `instructions_util` appellent aussi `nltk.download(...)` à l'import quand les données manquent, ce qui fait un appel réseau caché.
- **Correctif :** ajouter à AD-9 « `correction/registre.py` fixe `langdetect.DetectorFactory.seed = 0` avant tout chargement de correcteur ». Ajouter à « Code emprunté » : les téléchargements faits à l'import sont retirés du code emprunté et consignés dans `PROVENANCE.md`. Prévoir un test qui corrige deux fois le même JSONL synthétique et compare les sorties octet par octet.

### H7 — La calibration (CAP-6) n'a pas de lieu cohérent
- **Où :** carte CAP-6 → `juge/calibration.py`, `rapport/` ; AD-3 (« `stats/` et `rapport/` ne lisent que `correction.jsonl` [+ `generation.jsonl`] ») ; graphe (pas de `juge → stats`).
- **Problème :** le rapport de calibration a besoin de l'accord et du coût (`cout_usd`), de la part d'escalades (`escalade`) et de l'écart Qwen, soit des champs de `jugement.jsonl` des 4 configurations et des étiquettes humaines. AD-3 interdit à `rapport/` de lire `jugement.jsonl`. Placé dans `juge/`, le calcul n'a pas accès à `stats/` (Wilson, bootstrap). Les stories 7 et 9 trancheront donc chacune à leur façon.
- **Correctif :** au choix :
  - (a) AD-3 autorise `rapport/` à lire `jugement-*/jugement.jsonl` et `calibration/` **pour le seul rapport de calibration**, et `juge/calibration.py` disparaît au profit de `rapport/calibration.py` ;
  - (b) ajouter la flèche `juge --> stats`.
  
  Fixer aussi dès maintenant la clé des étiquettes humaines (`cle` de jugement = `cle_generation|critere`), même si le format du fichier reste différé.

## Moyen

### M1 — `.venv-qualite` n'est pas ignoré par git, contrairement à ce qu'affirme la Stack
- **Où :** Stack (« venv dédié `.venv-qualite`, ignoré par git ») ; `.gitignore`.
- **Correctif :** la story 1 ajoute `.venv-qualite/` à `.gitignore`. Inscrire ce point dans la Structural Seed.

### M2 — Le test AST de télémétrie demande une modification et ne voit pas `datasets`
- **Où :** AD-14 ; `tests/unit/test_telemetry.py` (`TELEMETRY_ROOTS`, `TELEMETRY_IMPORTERS`, `_module_level_call_line`).
- **Problème :** un module de `questions/import_publics/` qui importe `huggingface_hub` fait échouer `test_every_telemetry_importer_is_listed` tant qu'il n'est pas ajouté au dictionnaire. Un module qui n'importe que `datasets`, qui charge `huggingface_hub`, n'est pas détecté du tout. Le test exige aussi un appel `disable_telemetry()` **nu, au niveau module**. Un appel qualifié (`telemetry.disable_telemetry()`) ou placé dans `main()` échoue.
- **Correctif :** préciser dans AD-14 :
  - « chaque fichier qui importe une de ces bibliothèques appelle `disable_telemetry()` (nom nu, niveau module) avant l'import et figure dans `TELEMETRY_IMPORTERS` » ;
  - « la story 2 ajoute `datasets` à `TELEMETRY_ROOTS` » (modification d'un test de `tests/unit`, sans toucher à `src/core`).

### M3 — Hooks pre-commit incompatibles avec les fichiers versionnés du banc
- **Où :** AD-14 et AD-5 (index et manifestes chargés d'empreintes sha256 en hexadécimal) ; convention « Code emprunté » ; `.pre-commit-config.yaml`.
- **Problème :** `detect-secrets` (HexHighEntropyString 3.0) signale chaque empreinte, comme cela s'est produit sur `_bmad/` (d'où son exclusion). Les PR de jeu (story 3) et de résultats (story 10) bloquent donc. `black`, `isort` et `ruff --fix` reformatent le code emprunté, ce qui fausse `PROVENANCE.md` et la comparaison avec l'amont. Le fichier de scores par question d'une campagne complète (environ 22 000 lignes) peut aussi dépasser `--maxkb=5000`.
- **Correctif :**
  - ajouter à la convention Git : exclure `benchmarks/qualite/` de `detect-secrets` (exclusion dans la configuration, ou `.secrets.baseline` régénérée sans BOM, cf. AGENTS.md) ;
  - exclure `scripts/bench_qualite/correction/vendored/` de black, isort et ruff ;
  - découper les scores par modèle (`benchmarks/qualite/<c>/scores/<modele>.jsonl`).

### M4 — La commande `pilote` et le sous-ensemble rejoué ne sont pas définis
- **Où :** Conventions « Commandes » (`pilote`) ; AD-4 (`<campagne>-rejeu`) ; CAP-8.
- **Problème :** faute de définition, la story 8 peut faire de `pilote` un orchestrateur qui enchaîne génération, jugement et rapport dans un même processus. Cela contredit le paradigme (« aucune phase n'appelle une autre en mémoire »), AD-12 (veille) et AD-15 (Winnow pendant qu'Ollama est chargé). Le **sous-ensemble** rejoué n'a pas non plus de mécanisme. Il peut s'agir d'un nouveau jeu dérivé, donc d'une autre empreinte de jeu, ou d'un filtre de configuration : la story 3 (jeu) et la story 8 n'en décideront pas de la même façon.
- **Correctif :**
  - `pilote` = rapport de pilote seulement, qui lit `pilote-X` et `pilote-X-rejeu` déjà générés et corrigés ;
  - le rejeu utilise un champ de configuration `sous_ensemble: {graine, n_par_usage}`, inclus dans `config.empreinte`, et le même jeu.

### M5 — `juger` ne sait pas quel juge lancer, et la configuration du juge n'a pas de place
- **Où :** Conventions « Commandes » (seul `--campagne`) ; AD-15 (« le juge retenu est désigné dans la configuration de correction ») ; AD-7 (`bloquant.juge`, `config.empreinte`).
- **Problème :** quatre configurations s'exécutent sur la même campagne, sans argument pour en choisir une. Si le juge retenu est écrit dans le YAML de campagne, il entre dans `config.empreinte` de la génération : le choisir après la génération du pilote impose alors un nouvel identifiant, ce qui empêche la reprise.
- **Correctif :**
  - `juger --campagne <c> --juge <winnow|winnow-cascade-haiku|mimo|haiku>` ;
  - les paramètres des juges vivent dans `scripts/bench_qualite/juges.yaml`, dont l'empreinte va dans `bloquant.juge` ;
  - `corriger --campagne <c> --juge <nom>` ;
  - le YAML de campagne reste hors juge.

### M6 — `reponse_parsee` est calculée par le runner, ce qui contredit la recorrection hors ligne
- **Où :** AD-6 (`reponse_parsee`) et AD-3.
- **Problème :** avec `think` actif, `format` peut être ignoré (#18774) et le contenu arrive alors entouré de balises de code. Si le décodage du runner est faux, la seule correction possible est de régénérer, ce qui viole CAP-4.
- **Correctif :** `reponse_parsee` devient informative. `correction/` redécode toujours le dernier `content` de `sortie` avec un analyseur unique (par ex. `commun/json_sortie.py`), sans jamais lire `reponse_parsee`.

### M7 — Lecteurs de JSONL en cours d'écriture : risque de troncature par un non-propriétaire
- **Où :** AD-11 (« un fragment final sans `\n` est **tronqué physiquement** ») ; AD-2.
- **Problème :** `corriger` ou `juger` peuvent lire `generation.jsonl` pendant que `generer` l'écrit. Si le lecteur de `commun/jsonl.py` applique la même ouverture, il tronque le fichier d'un autre écrivain.
- **Correctif :** prévoir deux API distinctes dans `commun/jsonl.py` :
  - `ouvrir_en_ecriture` (propriétaire seul, tronque) ;
  - `lire` (lecture seule, ignore le fragment final sans `\n`, ne modifie jamais rien).

### M8 — Verrou orphelin après un plantage
- **Où :** AD-2 (`.verrou` contenant un PID) ; CAP-3 (reprise après arrêt brutal).
- **Problème :** après un arrêt brutal, `.verrou` reste en place. Ni sa détection d'obsolescence ni la réutilisation de PID sous Windows ne sont décidées, ce qui laisse deux comportements possibles : la reprise est bloquée, ou un verrou réellement actif est écrasé.
- **Correctif :** le verrou contient `{pid, heure_de_creation_du_processus, machine}`. Il est obsolète si aucun processus ne correspond à ce couple PID et heure. La reprise le remplace alors en le journalisant.

### M9 — `num_ctx` face à la capacité du modèle et à la troncature silencieuse du prompt
- **Où :** AD-5 (`num_ctx` choisi parmi les paliers) ; AD-8 ; spec : « contexte long plafonné entre 8K et 32K selon la mémoire » et « surveiller le préremplissage ».
- **Problème :**
  - Les tokeniseurs diffèrent : un prompt RAG de 16K pour un modèle peut dépasser `num_ctx - num_predict` pour un autre, et Ollama tronque alors le prompt sans erreur.
  - Un modèle dont le contexte maximal (`/api/show`) ou la mémoire (`qwen3.6:35b-a3b`, RAM limite) est sous le palier n'a pas de traitement défini. Sauter la question, la mettre en `erreur` ou la passer en échec change les comparaisons appariées.
- **Correctif :**
  - règle du jeu : palier ≥ (tokens estimés × 1,25) + plafond maximal de `num_predict` ;
  - règle du runner : `statut = erreur` et `erreur = "contexte"` si `prompt_eval_count` atteint `num_ctx - num_predict`, ou si le palier dépasse le contexte maximal déclaré ou un `num_ctx_max` par modèle dans la configuration ;
  - les statistiques traitent ce cas comme `erreur` (AD-9).

### M10 — Dépendances implicites de l'environnement Ollama absentes du manifeste
- **Où :** AD-7 ; Deferred (`OLLAMA_NUM_PARALLEL`).
- **Problème :** `OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`, `OLLAMA_CONTEXT_LENGTH` et la version du pilote GPU changent les sorties à graine fixée. Ils ne sont ni bloquants ni consignés.
- **Correctif :** relire l'environnement du service, avec la même méthode que celle retenue pour `NUM_PARALLEL`, et le placer dans `bloquant`. La version du pilote NVIDIA va dans `informatif`.

### M11 — Enveloppe d'exploitation : mises à jour automatiques d'Ollama et de Windows
- **Où :** AD-7 (« un changement de version arrête la campagne ») ; AD-12 ; Deferred « exploitation ».
- **Problème :**
  - Ollama sous Windows télécharge ses mises à jour seul et les applique au redémarrage. Un plantage suivi d'un redémarrage peut donc changer la version, ce qui rend la campagne **irreprenable** (`bloquant.version_ollama`) et provoque un téléchargement pendant la génération.
  - `SetThreadExecutionState` n'empêche pas un redémarrage de Windows Update sur 5 à 6 jours.
- **Correctif :** ajouter à AD-12 une liste de contrôle avant campagne, vérifiée par `generer` quand c'est possible et sinon consignée dans `informatif` :
  - mises à jour automatiques d'Ollama coupées ;
  - Windows Update en pause pour la durée de la campagne ;
  - reprise manuelle après tout redémarrage.

### M12 — Encodage sous Windows
- **Où :** Conventions (aucune règle d'encodage hors du JSON canonique).
- **Problème :** `open()` sans `encoding` utilise cp1252 sous Windows. Les YAML de campagne, les questions de rédaction en français et le journal avec `≥`, `→` ou des accents s'y corrompent, ou lèvent `UnicodeEncodeError` sur la console.
- **Correctif :** ajouter la convention « tout `open()` passe `encoding="utf-8"` (sauf binaire) ; le `StreamHandler` est reconfiguré en UTF-8 ».

### M13 — L'écart d'AD-3 avec la spec n'est pas tranché
- **Où :** AD-3 [ASSUMPTION] ; succès de CAP-2 (« chaque ligne JSONL porte les champs de `campagne-et-reprise.md` », dont « score par métrique »).
- **Correctif :** faire confirmer le choix par Anaël, puis mettre à jour `campagne-et-reprise.md`. Sinon, la vérification d'acceptation de la story 5 échouera sur la lettre du critère.

### M14 — Le code du harnais ne bloque pas la reprise
- **Où :** AD-7 (`informatif.code`).
- **Problème :** on retrouve le piège signalé par AGENTS.md pour le banc de vitesse : une modification de `ollama/client.py`, de `generation/` ou de `envs/` en cours de campagne change les requêtes sans bloquer la reprise.
- **Correctif :** ajouter à `bloquant` l'empreinte du contenu des fichiers `ollama/`, `generation/` et `envs/`, ou au minimum refuser la reprise si l'arbre de ces dossiers est sale.

## Bas

- **B1 — `integration` tourne par défaut** (Conventions « Tests » ; `pytest.ini`) : `addopts` n'exclut que `e2e`. Le conftest de `tests/bench_qualite` doit sauter `integration` sauf variable explicite, ou la commande documentée doit passer `-m "not integration"`.
- **B2 — Saut du dossier quand les dépendances manquent :** il doit passer par `collect_ignore_glob` dans le `conftest.py`, et non par `pytest.importorskip` au niveau module du conftest. Ajouter un `tests/bench_qualite/__init__.py` pour éviter les collisions de noms de base avec `tests/integration`, qui n'en a pas.
- **B3 — Pièges de `.gitignore`** (Structural Seed) : `data/`, `lib/`, `models/` sont ignorés à toute profondeur, et `tests/fixtures/*` aussi. Les JSONL synthétiques de test et tout sous-dossier `data/` ou `lib/` du code emprunté seraient silencieusement non versionnés. Les placer sous `tests/bench_qualite/donnees/` et vérifier le code emprunté avec `git check-ignore`.
- **B4 — `journal.log` à écrivains multiples** (Conventions « Journal » contre AD-2) : `generer`, `corriger`, `juger` et `rapport` écrivent le même fichier. Le remplacer par `journal-<commande>.log`, ou exempter explicitement le journal d'AD-2.
- **B5 — `STOP` pour `juger`** (AD-12) : seul `campagnes/<c>/STOP` est nommé. Préciser `jugement-<juge>/STOP`.
- **B6 — Diagramme 1 incomplet par rapport aux AD** : il manque `JEU → COR` (correction lit la question, AD-9), `JEU → JUG` (critères et `prive`, AD-14 et AD-15), `JEU → RAP` (index) et `GEN → RAP` (tokens et durées, AD-3). Le graphe de dépendances, lui, est cohérent pour `juge → ollama` (`/api/ps`) et `juge → questions`.
- **B7 — Référence de l'ancien banc non épinglée** (AD-1 et CAP-8) : `benchmarks/results/*.json` est réécrit par `bench_here.py export`. Consigner dans le rapport de pilote le chemin et l'empreinte du fichier lu, `tour-rtx3050-a2b6baf5.json`, et vérifier qu'il est postérieur au correctif d'agrégation b36cb8c.
- **B8 — Erreur du juge et correction** (AD-9 et AD-15) : le `statut` de correction d'une rédaction dont un critère est en `erreur` chez le juge n'est pas défini. Proposer `erreur`, exclue comme en AD-9.
- **B9 — `allow_nan=False`** à ajouter au JSON canonique (AD-4) : un `NaN` produirait du JSON non standard et une empreinte instable entre lecteurs.
- **B10 — Gel du jeu** (AD-2 « écrit une fois, puis gelé ») : `jeu` doit refuser d'écraser `jeux/<jeu>/` existant.
- **B11 — Étiquettes incohérentes** : seul AD-1 porte `[ADOPTED]` et seul AD-3 `[ASSUMPTION]`. Étiqueter toutes les AD ou aucune.
- **B12 — Mermaid** : la syntaxe est valide. Par robustesse entre versions, mettre entre guillemets les libellés qui contiennent `/`, `→` ou `·` (par ex. `G[("benchmarks/qualite → PR bench/")]`).
- **B13 — Ombre de paquet `scripts`** : la commande `python -m` marche, mais un paquet régulier `scripts` dans le `site-packages` de `.venv-qualite` l'emporterait sur le dossier du dépôt. Ajouter à la story 1 un test qui vérifie `scripts.bench_qualite.__file__` sous la racine.

## Couverture

| Critère de la grille | État |
| --- | --- |
| Points de divergence des 10 stories | Couverts pour les stories 1, 2, 4 à 7 et 10. Manquent : schémas partagés et configuration (H3), score strict (H2), calibration (H7, stories 7 et 9), pilote et rejeu (M4, story 8), choix du juge (M5). |
| Règles applicables et efficaces | Oui dans l'ensemble. Exceptions : les listes d'exclusion (C1), les empreintes (H1), AD-13 sans mécanisme (H4), l'exception d'AD-1 non installable (H5). |
| Deferred sans risque de divergence | Oui, sauf le « format du fichier d'étiquettes » : sa clé doit être fixée maintenant (H7). |
| Ratifie le dépôt existant | Partiellement : `python -m` correct, `data/` correct. Faux sur `.venv-qualite` (M1), `dotenv` (H5), le test de télémétrie « sans modification » (M2) et pre-commit (M3). |
| 8 CAP couvertes | Toutes cartographiées. CAP-4 est fragilisée (H6, M6), CAP-6 n'a pas de lieu cohérent (H7). |
| Toutes les dimensions décidées, différées ou ouvertes | Sans statut : verrou machine (H4), encodage (M12), environnement d'Ollama (M10), mises à jour automatiques (M11), dépassement de contexte (M9). |
| Diagrammes | Syntaxe valide. Le graphe de dépendances est cohérent avec les AD sauf `main → commun` (H3) et la calibration (H7). Le diagramme 1 omet des lectures (B6). |
