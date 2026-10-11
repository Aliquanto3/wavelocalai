---
type: architecture-review
lens: adversarial (paires d'unités conformes mais incompatibles)
cible: ../ARCHITECTURE-SPINE.md
unites: stories 1 à 10 de ../../../../specs/spec-benchmark-qualite-difficile/stories.yaml
date: 2026-10-10
---

# Revue adversariale de l'épine — banc de qualité difficile

## Verdict

L'épine est solide sur la propriété des fichiers de génération et la reprise. Elle laisse pourtant des trous où deux stories qui respectent chaque AD à la lettre produisent des artefacts incompatibles. Le plus grave : l'**empreinte du jeu ne couvre pas les champs qui changent la mesure** (`num_ctx`, `correcteur`, `env`, `criteres`, `usage`, `groupe`). Le manifeste, censé bloquer toute reprise sur un jeu différent, laisse donc passer un jeu modifié. Viennent ensuite six trous de gravité haute : le format de la configuration, l'agrégation entre questions (score strict VAR-MATH), le contenu de `sortie` en multi-tours, ce qui est versionné dans `benchmarks/qualite/`, la lecture d'un JSONL par un processus qui n'en est pas propriétaire, et l'occupation partagée du GPU.

Bilan : 1 critique, 9 hautes, 9 moyennes, 4 basses. Il faut resserrer l'épine avant la story 2 (schéma) et la story 4 (correcteurs), au plus tard.

Notation : « S2 » désigne la story 2, etc. Chaque trou donne la paire d'unités, la façon dont chacune respecte les AD, la divergence, la gravité et le resserrement proposé.

---

## Critique

### T1 — L'empreinte du jeu est aveugle à ce qui change la mesure

- **Paire :** S3 (générateurs, qui fixent `num_ctx`, `criteres` et `correcteur`) contre S1/S5 (manifeste et reprise de la génération), puis S7 (jugement).
- **Conformité aux AD :** AD-5 définit l'empreinte du jeu comme `{"questions": [[id, empreinte_prompt, empreinte_cible]…], "pistes": …}`. AD-4 fait porter `empreinte_prompt` sur `messages`, `tools` et `format` seulement, et `empreinte_cible` sur `cible` seulement.
- **Divergence :** S3 régénère le jeu après le pilote : elle change le palier `num_ctx` d'une botte de foin RAG, réécrit un critère de rédaction (`criteres`), passe `correcteur` de `exact@1` à `numerique@1` ou change `env.etat_initial`. L'empreinte du jeu ne bouge pas, donc AD-7 accepte la reprise. La génération reprend alors avec deux `num_ctx` dans le même fichier, le jugement reprend avec deux formulations du même critère `c1`, et la correction applique un autre correcteur. Le manifeste ne détecte rien, alors que c'est exactement ce que AD-7 « Prevents ». Même chose pour `tours` (multi-tours) : il ne fait pas partie de `empreinte_prompt`, donc une conversation BFCL modifiée au-delà du premier tour passe inaperçue.
- **Gravité :** critique (corruption silencieuse de la campagne de 5 à 6 jours).
- **Resserrement (AD-4/AD-5) :**
  - `empreinte_prompt` = empreinte de `{"messages", "tours", "tools", "format", "num_ctx"}` (tout ce qui part vers Ollama).
  - Ajouter `empreinte_question` = empreinte de la ligne canonique entière (hors `empreinte_*`).
  - Empreinte du jeu = empreinte de `{"questions": [[id, empreinte_question] triés par id], "pistes": …}`.
  - Le manifeste de jugement porte en plus l'empreinte des seuls `criteres` des questions de rédaction.
  - L'index public garde `empreinte_prompt` et `empreinte_cible` (voir T9 pour les questions privées).

---

## Haute

### T2 — Version du correcteur figée dans le jeu contre recorrection après correction d'un bug

- **Paire :** S3 (le jeu inscrit `correcteur: {"nom": "ast_bfcl@1"}`) contre S4 (registre `nom@version`, recorrection hors ligne).
- **Conformité :** AD-5 met `correcteur` avec sa version dans la question, AD-9 enregistre `nom@version`, et AD-3 veut qu'une recorrection après bug change les scores sans régénérer.
- **Divergence :** S4 corrige un bug d'`ast_bfcl`. Soit elle le corrige en place sous `@1` (même nom, scores différents, aucune trace : AD-9 trahi dans l'esprit), soit elle crée `@2`, mais la question gelée dit `@1`. Pour l'appliquer, il faut alors régénérer le jeu, ce qui change son empreinte (après T1) et invalide la campagne. Même conflit pour `env.nom` (AD-10) : si l'environnement passe en `@2`, le rejeu du correcteur ne retrouve plus les résultats d'outils enregistrés dans `sortie`.
- **Gravité :** haute.
- **Resserrement (AD-5/AD-9/AD-10) :**
  - La question ne porte que le **nom** du correcteur (`"correcteur": {"nom": "ast_bfcl", "params": {}}`). La version vient de la configuration de correction (voir T4), qui associe à chaque nom une version, et `correction.jsonl` écrit la version effectivement appliquée.
  - Une version d'un correcteur ne change jamais une fois publiée : un bug corrigé donne `@n+1`.
  - Pour `env`, la version reste dans la question, et donc dans l'empreinte, car elle conditionne la génération. Le correcteur rejoue avec **cette** version et vérifie que chaque résultat rejoué est égal au message `tool` enregistré. Sinon : `statut = erreur` (erreur du banc), jamais un score.

### T3 — Agrégation entre questions : le score strict VAR-MATH n'a pas de propriétaire

- **Paire :** S3 (générateur VAR-MATH : plusieurs variantes d'un même problème) contre S4 (correcteur `corriger(question, generation)`) et S6 (statistiques).
- **Conformité :** `pistes-et-questions.md` exige qu'un problème ne soit réussi que si **toutes** ses variantes le sont. AD-9 impose un correcteur pur **par question**, et AD-16 des statistiques par question.
- **Divergence :**
  - S3 écrit une question par variante (seul moyen de respecter AD-5).
  - S4 ne peut pas voir les autres variantes : elle note chaque variante seule.
  - S6, qui ne connaît que `groupe`, compte chaque variante comme une question. Le score strict disparaît sans qu'aucune unité ne viole d'AD.
  - Variante : S6 décide de prendre le minimum par `groupe`. Elle agrège alors aussi les questions RAG qui partagent une botte de foin, ce qui est faux, car `groupe` sert à la fois au regroupement des erreurs-types et à l'unité de score.
- **Gravité :** haute.
- **Resserrement (AD-5, AD-9, AD-16) :**
  - Ajouter au schéma un champ `unite` (défaut : `id`), distinct de `groupe` : c'est l'unité de notation.
  - Règle de `stats/` : `reussite(unite) = ET` des `reussite` de ses questions, `score(unite) = min`. Une `unite` dont une question est en `erreur` est en `erreur`.
  - McNemar, Wilson et les erreurs-types se comptent sur les unités, et les grappes sur `groupe`.
  - Le tirage de `pistes.json` se fait par `groupe` entier (voir T15).

### T4 — Le schéma de la configuration de campagne n'est défini nulle part, et le choix du juge y casse la génération

- **Paire :** S1/S5 (lecture de `campagnes/<id>.yaml` et calcul de `config.empreinte`) contre S7/S9/S10 (configuration du juge et « configuration de correction » qui désigne le juge retenu, AD-15).
- **Conformité :** AD-7 montre la configuration **résolue** dans le manifeste. AD-15 désigne le juge retenu « dans la configuration de correction ». La convention « Commandes » impose un nouvel id à toute modification de la configuration.
- **Divergence :**
  - S7 ajoute une section `juge:` au même YAML. S5 calcule `config.empreinte` sur toute la configuration résolue. Pour S10, désigner le juge retenu ou corriger ses seuils après le début de la génération change l'empreinte : la génération ne reprend plus, ou il faut un nouvel id, donc une nouvelle campagne.
  - À l'inverse, si S5 n'empreinte que ses propres champs, `essais_max` et le « nombre maximal d'appels par tour » (AD-10), absents de l'exemple de `bloquant`, peuvent changer en cours de campagne sans blocage.
  - Les champs de sélection (sous-ensemble du rejeu, voir T13) n'ont pas de place.
  - Rien ne dit qui lit le YAML : chaque phase risque d'avoir son propre analyseur avec ses propres valeurs par défaut.
- **Gravité :** haute.
- **Resserrement (nouvel AD « Configuration », propriétaire `commun/config.py`) :**
  - Un seul module lit et résout le YAML, avec un schéma typé et des valeurs par défaut uniques.
  - Trois sections : `generation`, `jugement` (une entrée par `<juge>`) et `correction` (juge retenu, version de chaque correcteur).
  - `bloquant.config` de la génération = la section `generation` résolue **entière** (liste exhaustive des champs, dont `essais_max`, `appels_max_par_tour`, la sélection des questions et `seed_base`, `k`).
  - Le manifeste de jugement n'emprunte que sa sous-section.
  - La section `correction` n'est empreintée nulle part en bloquant : elle se change librement et chaque passe la consigne (voir T8).
  - La règle « modifier une configuration impose un nouvel id » ne vaut que pour la section `generation`.

### T5 — `sortie` en multi-tours : frontières de tours et tours utilisateur non spécifiés

- **Paire :** S5 (boucle de conversation du runner) contre S4 (correcteur BFCL multi-turn, qui vérifie l'état et les appels **après chaque tour**).
- **Conformité :** AD-6 définit `sortie` comme les « messages produits pendant la question (réponses du modèle, résultats d'outils) ». AD-10 dit que le correcteur rejoue depuis `sortie`. AD-5 dit que `tours` est réservé au multi-tours.
- **Divergence :**
  - S5 lit AD-6 à la lettre : les messages `user` injectés depuis `tours` ne sont pas « produits », donc absents de `sortie`. S4 ne peut plus découper par tour, ni vérifier l'état intermédiaire attendu par `ast_checker` multi-turn.
  - Rien ne dit si `tours[0]` répète le premier message de `messages` ou le suit. Deux implémentations envoient donc des conversations différentes à partir de la même question.
  - Quand la borne d'appels par tour est atteinte, aucun `statut` de génération ne convient (`ok | tronque | erreur`). S5 écrit `ok`, S4 ne trouve pas de réponse finale et écrit `non_conforme` ou `erreur` selon l'auteur.
  - Rien ne dit si un appel d'outil inconnu de l'environnement arrête la conversation ou renvoie un message d'erreur au modèle.
- **Gravité :** haute.
- **Resserrement (AD-5, AD-6, AD-10) :**
  - `messages` contient le système et le premier tour utilisateur. `tours[i]` (i ≥ 0) sont les tours **suivants**.
  - `sortie` contient **tous** les messages postérieurs à `messages`, y compris les `user` injectés, chacun annoté de `"tour": i`.
  - Un tour se termine sur un message `assistant` sans `tool_calls`, ou quand `appels_max_par_tour` est atteint. Dans ce second cas, le runner ajoute `"borne_atteinte": true` sur le tour, et le correcteur en fait `non_conforme`.
  - Un appel inconnu ou mal formé produit un message `tool` d'erreur déterministe généré par `envs/` (même texte au rejeu), et la conversation continue.

### T6 — Le fichier de scores versionné n'a pas de forme, et `metriques` peut fuiter

- **Paire :** S6/S8/S10 (`rapport/`, qui écrit `benchmarks/qualite/<c>/…`) contre S4 (correcteurs, qui remplissent `metriques`) et S3 (questions privées).
- **Conformité :** AD-14 versionne « scores par question **sans** `sortie` ». AD-2 donne `benchmarks/qualite/<c>/…` à `rapport/` sans nom ni schéma. AD-9 montre `metriques: {"f1": 0.92}` sans en contraindre le type. La spec dit « indexés par empreinte ».
- **Divergence :**
  - S4 met dans `metriques` un diagnostic utile (`"attendu": "Lyon"`, `"extrait": "…"`, la liste des champs manquants). S6 copie la ligne de correction telle quelle vers le versionné, en respectant AD-14 puisque ce n'est pas `sortie`. Une cible ou une réponse privée part sur GitHub.
  - `erreur` (texte d'exception) dans la ligne de génération peut contenir un fragment de réponse, par exemple un message de `json.JSONDecodeError`.
  - S8 et S10 écrivent `scores.jsonl` indexé par `cle` (qui contient `campagne`), S6 l'attend indexé par `empreinte_prompt`. Deux rapports ne se comparent pas.
- **Gravité :** haute (dépôt public).
- **Resserrement (AD-9, AD-14, nouveau schéma `bq.score/1`) :**
  - `metriques: dict[str, float]` finis, sans aucune chaîne. Les diagnostics vont dans un champ `diagnostic` du seul `correction.jsonl` (hors dépôt).
  - Fichier versionné `benchmarks/qualite/<c>/scores.jsonl`, schéma `bq.score/1`, une ligne par `cle`. Champs **listés de façon fermée** : `cle, modele, piste, question_id, unite, groupe, usage, seed, statut, score, reussite, metriques, correcteur, tokens, durees_ns, empreinte_prompt`.
  - Liste blanche appliquée par `rapport/`, et test qui échoue si un champ texte libre apparaît.
  - Fichiers voisins nommés : `manifeste-generation.json`, `manifeste-jugement-<juge>.json`, `agregats.json`, `rapport.md`.

### T7 — Un lecteur peut tronquer un JSONL qui ne lui appartient pas

- **Paire :** S1 (`commun/jsonl.py`, reprise avec troncature physique du fragment final) contre S7 (le juge lit `generation.jsonl` pendant que la génération écrit) et S4/S6 (correction et rapport lancés sur une campagne en cours).
- **Conformité :** AD-11 dit qu'« à l'ouverture pour reprise, un fragment final sans `\n` est tronqué physiquement ». AD-2 donne un seul écrivain par fichier. Rien n'interdit de lire une campagne en cours (le pilote le fait naturellement).
- **Divergence :**
  - S7 réutilise la fonction de chargement de S1 (chargement des clés, tolérance au fragment). Elle tronque le `generation.jsonl` en cours d'écriture par le runner, dont le prochain `write` en `"ab"` colle une ligne valide derrière une ligne amputée.
  - Ou bien S6 lève une exception sur la « ligne illisible » finale, alors que S7 l'ignore.
- **Gravité :** haute (corruption du fichier source de vérité).
- **Resserrement (AD-11) :**
  - Deux API distinctes. `lire(chemin)` : lecture seule, ignore un fragment final, n'écrit jamais. `ouvrir_en_reprise(chemin)` : réservée au propriétaire, n'est appelable que si le processus détient `.verrou`.
  - Un lecteur qui trouve un `.verrou` vivant journalise « campagne en cours » et ne traite que les lignes complètes.

### T8 — `correction.jsonl` ne dit pas de quelle génération ni de quel juge il dérive

- **Paire :** S1 (« chaque ligne JSONL porte `manifeste` », AD-7) contre S4 (ligne `bq.correction/1` d'AD-9, sans champ `manifeste`), puis S8/S9 (le pilote est corrigé avec un juge, puis le juge retenu change).
- **Conformité :** les deux AD sont respectés selon celui qu'on lit, puisque l'exemple d'AD-9 omet `manifeste`.
- **Divergence :**
  - Deux passes de correction, l'une avec `jugement-winnow/`, l'autre avec `jugement-haiku/`, donnent deux `correction.jsonl` indiscernables. Le rapport ne peut ni dire quel juge a noté la rédaction, ni vérifier que les verdicts portent sur la génération courante (`jugement/manifeste.generation` = empreinte du manifeste de génération).
  - La correction peut joindre des verdicts d'un jugement fait sur une autre génération, celle d'une campagne recréée sous le même id après suppression.
- **Gravité :** haute.
- **Resserrement (AD-3/AD-9) :**
  - `correction/` écrit, à côté de `correction.jsonl`, un `correction-manifeste.json` (`bq.manifeste/1`, `phase = correction`). Il contient l'empreinte du manifeste de génération, l'identifiant et l'empreinte du manifeste du juge retenu, et la table `nom → version` des correcteurs.
  - Chaque ligne porte `manifeste` = empreinte de ce bloc.
  - Le correcteur refuse un jugement dont `bloquant.generation` ≠ empreinte courante.
  - Le rapport recopie ce manifeste dans `benchmarks/qualite/<c>/`.

### T9 — L'empreinte de cible d'une question privée se retrouve par force brute

- **Paire :** S3 (questions privées FR : abstention, extraction, réponses numériques) contre S2/S3 (index public `benchmarks/qualite/jeux/<jeu>/index.jsonl`).
- **Conformité :** AD-5 met `empreinte_cible` dans l'index public, AD-14 ne versionne que les empreintes, et CAP-1 dit « aucune question privée dans le dépôt, seulement son empreinte ».
- **Divergence :** une cible de faible entropie (`"non"`, `42`, `{"ville": "Lyon"}`, une étiquette d'abstention) a un SHA-256 qui se retrouve par dictionnaire en quelques secondes. Le dépôt public publie donc les réponses des questions privées, justement ce que la confidentialité devait protéger de la contamination.
- **Gravité :** haute.
- **Resserrement (AD-4/AD-5) :**
  - Pour `prive = true`, les empreintes publiées sont des HMAC-SHA-256 avec un sel secret (`BENCH_QUALITE_SEL`, hors dépôt, consigné dans `data/`), ou bien `empreinte_cible` est omise de l'index.
  - Les empreintes internes (manifeste, clé) restent des SHA-256 nus.
  - Un test vérifie qu'aucune ligne privée de l'index ne porte d'empreinte non salée.

### T10 — Prompt plus long que `num_ctx` et contexte propre à chaque modèle

- **Paire :** S3 (générateur OneRuler, qui choisit un palier `num_ctx` pour une botte de foin de N tokens) contre S5 (runner avec 20 tokenizers différents, et `qwen3.6:35b-a3b` serré en RAM).
- **Conformité :** AD-5 met `num_ctx` dans la question et le fige. AD-6 ne marque `tronque` que sur `done_reason == "length"` (la sortie). AD-8 envoie `options.num_ctx`.
- **Divergence :**
  - La botte de foin de 15 500 tokens comptée par S3 avec un tokenizer en fait 17 000 pour un autre modèle. Ollama tronque alors le prompt **en silence** (par le début, donc l'aiguille peut disparaître). Le modèle échoue avec `statut = ok`, et l'échec est imputé au modèle.
  - S5, voulant protéger un modèle qui manque de mémoire, plafonne `num_ctx` par modèle : la ligne porte un `num_ctx` différent de la question sans que la clé change. Les modèles ne sont plus comparés sur la même tâche.
- **Gravité :** haute.
- **Resserrement (AD-6/AD-8) :**
  - `num_ctx` envoyé = celui de la question, sans exception par modèle. Un modèle incapable d'un palier est exclu de ce palier **dans la configuration** (bloquant), et ces clés n'existent pas.
  - Le runner compare `prompt_eval_count` (premier appel) + `num_predict` à `num_ctx`. En cas de dépassement, nouveau statut de génération `contexte_depasse`, échec du banc compté à part et jamais noté comme réponse.
  - Revérifier à la story 1 si Ollama 0.40.2 accepte une option qui refuse la troncature au lieu de l'appliquer. Le générateur garde une marge de 25 % sous le palier.

---

## Moyenne

### T11 — Deux chemins d'analyse de la réponse (`reponse_parsee`, balises de réflexion en ligne)

- **Paire :** S5 (remplit `reponse_parsee` par `json.loads` du dernier `content`) contre S4 (correcteur d'extraction et correspondance exacte).
- **Divergence :**
  - Un modèle répond en bloc de code Markdown, ou glisse `<think>…</think>` dans `content` malgré `think=false` (modèles « thinking » sans interrupteur effectif). S5 laisse `reponse_parsee = null`. S4, plus tolérante, réextrait depuis `sortie` en retirant les clôtures et obtient un score. La recorrection et la génération divergent sur la même question.
  - Inversement, si S4 se fie à `reponse_parsee`, un correctif d'analyse impose de régénérer, ce qui contredit AD-3.
- **Resserrement (AD-6/AD-9) :**
  - Supprimer `reponse_parsee` de `bq.generation/1` (la génération reste brute).
  - Une seule fonction `correction/reponse.py: reponse_finale(sortie) -> str` et `json_de(texte)`, avec une règle unique et documentée pour les clôtures et les balises `<think>`.
  - Tout texte de réflexion trouvé dans `content` en piste coupée est compté dans un indicateur `reflexion_en_ligne` (métrique publiée).

### T12 — Rédaction : agrégation des critères avec verdicts manquants, réponses tronquées ou en erreur

- **Paire :** S7 (juge) contre S4 (correction de la rédaction) et S6.
- **Divergence :**
  - S7 juge toutes les lignes de rédaction, y compris `tronque` et `erreur`, et paie des jugements inutiles. Certaines de ses lignes ont `erreur ≠ null` et `verdict = null`.
  - S4 calcule « moyenne des critères vrais » sur les critères présents (3 sur 5), alors qu'une autre lecture met `en_attente_jugement`.
  - S6 traite `en_attente_jugement` comme absent, ou comme 0.
- **Resserrement (AD-9/AD-15) :**
  - Le juge ne traite que les lignes `usage = redaction` et `statut = ok`.
  - En correction : `tronque` donne 0 sans lire de verdict. Un critère sans ligne de verdict donne `en_attente_jugement`. Un critère dont la ligne porte une erreur donne `erreur`. Le score est la moyenne sur **tous** les `criteres` de la question.
  - Le rapport refuse de produire les agrégats d'une piste tant qu'il reste des `en_attente_jugement`, sauf avec `--partiel`, qui marque le rapport comme partiel.

### T13 — Rejeu du pilote : sous-ensemble sans place dans la configuration, jointure entre campagnes non définie

- **Paire :** S8 (campagne `pilote-…-rejeu` sur un sous-ensemble) contre S6 (statistiques jointes par `cle`).
- **Divergence :**
  - S8 crée un jeu `jeu-v1-rejeu` (autre id, autre empreinte), ou filtre en mémoire par une option de ligne de commande que le manifeste ignore.
  - S6 joint pilote et rejeu par `cle`, qui contient `campagne` : aucune correspondance, donc taux de réponses changeantes de 0 %.
  - Ou bien S6 joint par `question_id` sans vérifier `empreinte_prompt` ni `digest` : elle compare des choses différentes.
- **Resserrement :**
  - Champ `selection` dans la section `generation` de la configuration (`{"ids": [...]}` ou `{"tirage": {"n", "graine", "strates": "usage"}}`), inclus dans le bloquant. Le jeu reste le même.
  - Jointure entre campagnes définie une seule fois dans `rapport/` : (`modele`, `digest`, `piste`, `question_id`, `seed`), avec égalité exigée de `empreinte_prompt`.

### T14 — K > 1 : qui agrège les époques

- **Paire :** S4 (une ligne de correction par `cle`, donc par seed) contre S6 (McNemar par question).
- **Divergence :** avec K = 3, S6 prend chaque `cle` pour une question et triple N (fausse puissance). Une autre implémentation prend la première seed.
- **Resserrement (AD-16) :** l'unité statistique est (`modele`, `piste`, `unite`). `stats/` agrège les seeds par moyenne avant tout test. Avec K > 1, McNemar est remplacé par l'erreur-type appariée sur les moyennes (`statistiques.md`), et le choix se fait sur `bloquant.config.requete.k`, pas sur ce qu'on observe dans les lignes.

### T15 — Tirage stratifié de `pistes.json` qui coupe les groupes et les variantes

- **Paire :** S3 (tirage stratifié « la moitié de chaque usage ») contre S6 (erreurs-types groupées et score strict).
- **Divergence :** S3 tire des **questions**. La piste activée reçoit 2 variantes sur 4 d'un problème VAR-MATH, ou 1 question sur 5 d'une même botte de foin. Le score strict de T3 change de définition entre pistes, et la comparaison entre pistes d'un même modèle est biaisée.
- **Resserrement (AD-5) :** tirage stratifié par usage **au niveau du `groupe`** (groupes entiers), graine dans la configuration du jeu. `activee` est l'union de groupes entiers, avec un effectif visé ± la taille du plus grand groupe.

### T16 — Deux producteurs écrivent dans `jeux/<jeu>/questions.jsonl` ; espace de noms des sources et des groupes

- **Paire :** S2 (`questions/import_publics/`) contre S3 (`questions/generateurs/`, questions privées, rédaction).
- **Conformité :** AD-2 donne le fichier au paquet `questions/` (commande `jeu`), donc aux deux stories.
- **Divergence :**
  - S2 écrit `questions.jsonl` dès l'import. S3 l'écrase ou y ajoute des lignes, alors que le fichier est « gelé ».
  - S2 numérote `outils/bfcl/0001…` et S3 aussi pour ses traductions FR de BFCL : les ids entrent en collision.
  - La traduction FR de `conv-17` reçoit le groupe `bfcl-fr/conv-17`, indépendant de l'original anglais : les erreurs-types sont sous-estimées.
- **Resserrement (AD-2/AD-5) :**
  - Importeurs et générateurs écrivent seulement des **candidats** sous `sources/<slug>/` (ou sont des fonctions pures). Seul `questions/jeu.py` assemble, tire, numérote et écrit `jeux/<jeu>/*` et l'index. La configuration du jeu (sources, effectifs, graines) a un fichier versionné et un schéma.
  - Liste fermée des `slug` de source dans `questions/schema.py`, chacun avec un seul producteur.
  - Une question dérivée (traduction, variante) reprend le `groupe` de son origine.

### T17 — Capacités lues à l'exécution, pistes effectives et `think` (null, false ou chaîne)

- **Paire :** S1 (manifeste écrit au premier lancement, `n` global par piste) contre S5 (lecture de `/api/show` et omission silencieuse de la piste activée).
- **Divergence :**
  - La configuration liste `pistes: ["coupee", "activee"]` pour un modèle sans capacité thinking. S5 saute la piste (AD-8). S6 et le rapport attendent pourtant 400 clés activées pour ce modèle et concluent à un trou, ou bien à un modèle présent avec N = 0.
  - Un modèle dont `think` n'accepte que des chaînes (`low|medium|high`) refuse `false`. S5 envoie `"low"` en piste coupée et le consigne dans `think`, ce qui change la nature de la piste coupée sans trace au manifeste.
- **Resserrement (AD-7/AD-8) :**
  - Au premier lancement, le manifeste résout et fige `modeles[].capacites` (depuis `/api/show`) et `modeles[].pistes_effectives`. Tout écart avec la configuration **refuse le lancement** (pas d'omission silencieuse).
  - `think_coupee` et `think_activee` explicites par modèle, validés contre les valeurs déclarées. `think = null` signifie seulement « capacité absente ».
  - Le nombre de clés attendues se calcule à partir de `pistes_effectives`.

### T18 — Absence de ligne contre `erreur` dans les statistiques

- **Paire :** S6 (statistiques sur des JSONL synthétiques) contre S8 et S10 (campagnes réelles, éventuellement incomplètes).
- **Divergence :** S6 assimile une clé absente (campagne interrompue) à une `erreur` et l'exclut des comparaisons comme le veut AD-9. Un rapport sur une campagne incomplète se publie alors sans alerte, avec un N qui diffère selon les modèles.
- **Resserrement (AD-9/AD-16) :** le rapport calcule l'ensemble des clés attendues (manifeste × `pistes_effectives` × `selection` × seeds) et refuse de publier s'il en manque, sauf `--partiel` (marqué dans le rapport). Les comptes `erreur`, `contexte_depasse`, `tronque`, `non_conforme` et `en_attente_jugement` sont publiés par modèle et par usage.

### T19 — Juge local et génération en même temps sur le GPU

- **Paire :** S5 (`generer`) contre S7 (`juger` avec Winnow local), lancés sur deux campagnes différentes, par exemple le jugement du pilote pendant la campagne `complete-…`.
- **Conformité :** les verrous d'AD-2 sont **par campagne**. AD-15 ne vérifie `/api/ps` qu'**au démarrage** du juge. AD-13 interdit deux générations, pas une génération et un jugement.
- **Divergence :** le juge démarre pendant un déchargement entre deux modèles (`/api/ps` vide), puis la génération charge le modèle suivant. Les deux partagent les 8 Go de VRAM : débordement en RAM partagée, préremplissage effondré, durées faussées, alors que la projection du pilote s'en sert.
- **Resserrement (AD-13/AD-15) :** un verrou machine `BENCH_QUALITE_DATA/.gpu.verrou` (PID) tenu pendant toute la durée de `generer` et de `juger` en local. `juger` cloud ne le prend pas.

---

## Basse

### T20 — Cascade : nom du dossier de jugement et réglage des seuils à la calibration

- **Paire :** S7 (`jugement-winnow-cascade-haiku/` avec les seuils dans le bloquant) contre S9 (calibration qui essaie plusieurs couples de seuils).
- **Divergence :** S9 relance `juger` pour chaque couple de seuils dans le même dossier, et le manifeste le refuse. Ou bien S9 crée des dossiers nommés à sa façon, que `correction/` ne retrouve pas. Au passage, une reprise de cascade recalcule la probabilité de Winnow d'un lot en attente, ce qui n'est pas garanti identique sur GPU.
- **Resserrement (AD-15) :**
  - `<juge>` = identifiant complet de la configuration (par exemple `winnow-cascade-haiku@b020-h080`).
  - La calibration simule la cascade **hors ligne** à partir des dossiers `jugement-winnow/` et `jugement-haiku/`, sans relancer de jugement.
  - `lots.jsonl` consigne la probabilité Winnow qui a motivé l'escalade.

### T21 — Pilote et calibration : quel juge pour le rapport de pilote, quelle famille « Qwen »

- **Paire :** S8 (rapport de pilote, qui dépend de S7) contre S9 (choix du juge, qui dépend de S8).
- **Divergence :** S8 doit publier les usages au plafond et la discordance, rédaction comprise, avant que le juge ne soit choisi. S8 prend Winnow, puis S9 retient Haiku : le rapport de pilote versionné contredit la campagne. S9 repère par ailleurs les « candidats Qwen » par préfixe de tag (`qwen`), alors qu'un autre lecteur inclurait les dérivés de Qwen.
- **Resserrement :** le rapport de pilote calcule la rédaction séparément, pour chaque juge disponible, et l'étiquette comme provisoire (après T8, le manifeste de correction dit lequel). Un champ `famille` est déclaré par modèle dans la configuration, et c'est lui qui définit le biais Qwen.

### T22 — JSON canonique : NaN, flottants et normalisation Unicode

- **Paire :** S2 (import Hugging Face, textes en NFD possibles, nombres en flottants) contre S3 (générateurs en NFC, nombres entiers) ; S4 et S7 contre S6.
- **Divergence :**
  - `json.dumps` accepte `NaN` par défaut. Un F1 de 0/0 ou une probabilité NaN s'écrit `NaN`, qui n'est pas du JSON : un autre lecteur échoue, et `stats/` propage la valeur.
  - `42` et `42.0` n'ont pas la même empreinte.
  - « é » en NFD et en NFC n'a pas la même empreinte et fait échouer la correspondance exacte.
- **Resserrement (AD-4) :**
  - `commun/canonique.py` utilise `allow_nan=False` (exception).
  - Toutes les chaînes sont en NFC à l'entrée du jeu.
  - Les cibles numériques sont des chaînes ou des entiers, selon une règle écrite dans `questions/schema.py`.
  - F1 de 0/0 vaut 1 si cible et réponse sont vides, 0 sinon.
  - Le correcteur exact normalise en NFC et ignore la casse et les espaces selon une règle unique.

### T23 — Nouvel essai en multi-appels, cache de préfixe et sens de `tokens.prompt`

- **Paire :** S1 (essais, AD-12) contre S5 (conversation multi-appels) et S8 (projection, stabilité).
- **Divergence :**
  - Après un plantage à l'appel 3, S1 refait l'appel 3, alors que S5 refait toute la question. Les tokens et durées des essais ratés sont additionnés, ou non.
  - Ollama réutilise le préfixe en cache entre questions consécutives qui partagent une botte de foin. `prompt_eval_count` et le préremplissage diffèrent donc entre la campagne (ordre complet) et le rejeu (sous-ensemble), ce qui fausse la projection et peut gonfler le taux de « réponses changeantes ».
- **Resserrement (AD-6/AD-12/AD-13) :**
  - Un essai refait **toute** la question, et `tokens` et `durees_ns` ne portent que l'essai réussi.
  - Le rejeu suit le même ordre relatif que la campagne d'origine.
  - Le rapport de pilote signale que `tokens.prompt` exclut le préfixe en cache et projette le préremplissage sur le prompt complet. Savoir s'il est possible de désactiver ce cache par requête dans Ollama 0.40.2 reste à vérifier à la story 1.

---

## Points vérifiés sans trou

- La propriété de `generation.jsonl`, de `jugement.jsonl` et de `lots.jsonl` est nette (AD-2, AD-11, AD-15).
- La clé de génération et la séparation `seed` / `graine` sont sans ambiguïté (AD-4), à la réserve de T14 près.
- Le sens des dépendances interdit à `generation/` d'importer `correction/`, ce qui protège AD-3.

## Resserrements à appliquer, par ordre

1. T1 et T2 (AD-4, AD-5, AD-9) : empreinte complète du jeu, version du correcteur sortie de la question.
2. T4 et T8 (nouvel AD « Configuration », manifeste de correction).
3. T3, T15 et T14 (champ `unite`, tirage par groupe, agrégation des seeds).
4. T5 et T10 (contrat de `sortie` multi-tours, statut `contexte_depasse`).
5. T6 et T9 (schéma `bq.score/1` en liste blanche, HMAC des empreintes privées).
6. T7 et T19 (API de lecture seule, verrou GPU).
7. Les autres trous, au fil des stories concernées.
