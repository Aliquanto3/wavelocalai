# Campagne et reprise

Ce fichier porte le contrat. Les schémas exacts des lignes et du manifeste sont dans le spine d'architecture : AD-7 (génération), AD-8 (manifeste), AD-10 (correction), AD-12 et AD-13 (écriture, arrêt, panne), AD-16 (jugement).

## Hygiène Ollama

- API native `/api/chat` seulement. Sur `/v1`, ni `num_ctx`, ni `think`, ni le schéma natif de `format` ne se règlent.
- Une seule version d'Ollama, épinglée pour toute la campagne. La numérotation des releases n'est pas chronologique : la v0.35.1 est sortie après la v0.40.0.
- `OLLAMA_NUM_PARALLEL` absent ou à 1. Il peut retomber en silence à une file : à vérifier.
- Une requête de chauffe, jetée, à chaque nouveau couple (modèle, `num_ctx`). Elle est consignée dans `warmups.jsonl`.
- À chaque requête : `seed`, `temperature=0`, `num_ctx`, `num_predict`, `think` et `format` fixés explicitement.
- Lire les capacités via `/api/show` avant d'envoyer `tools` ou `think`. Une valeur chaîne de `think` doit correspondre exactement à l'une de celles listées. Les modèles qui déclarent la capacité `decision` sont exclus du chat, des outils et de la réflexion.
- Valider chaque sortie JSON contre le schéma côté client : `format` peut être ignoré quand `think` est actif (issue #18774). Une sortie non conforme est un échec du modèle, pas une erreur du banc.
- Revérifier l'API d'Ollama (`format` avec `think`, issue #18774, logprobs) le 2026-11-01, ou avant de figer le harnais si c'est plus tôt.
- Les logprobs ne sont pas utilisés (documentation contradictoire).
- Surveiller le temps de préremplissage : un modèle trop gros déborde en RAM partagée sans OOM, et le préremplissage s'effondre.

## Ligne de génération (`generation.jsonl`)

Une ligne par (modèle, piste, question, `seed`), écrite en ajout seul et forcée sur disque (`fsync`) sitôt la question terminée. Elle est brute : ni score, ni réponse analysée (AD-3).

**Champs :** `key`, `manifest`, `campaign`, `model`, `digest`, `track`, `question_id`, `usage`, `group`, `unit`, `prompt_hash`, `seed`, `epoch`, `think`, `backend`, `ollama_version`, `num_ctx`, `num_predict`, `status` (`ok`, `truncated`, `context_exceeded`, `error`), `context_limit` (`model` ou `bench`, seulement avec `context_exceeded`), `output` (sortie brute, tous tours compris), `call_cap_reached`, `tokens`, `durations_ns`, `wall_s`, `calls`, `attempts`, `error`, `created_at`.

- `tokens` : prompt, prompt en cache et complétion font foi. Les tokens de réflexion et de réponse sont des estimations, car Ollama ne les compte pas à part (issue #17843).
- `status = truncated` signale la troncature.

**Clé de reprise :** `campaign|model|track|question_id|seed`.

## Correction (`grading.jsonl`)

C'est une phase séparée (`grade`), sans réseau ni GPU. Elle lit `generation.jsonl` et, pour la rédaction, les verdicts du juge retenu, puis réécrit `grading.jsonl` en entier. C'est le seul fichier qui porte `score` et `success`.

- `truncated` et `non_compliant` (JSON hors schéma, appel d'outil invalide, borne d'appels atteinte) sont des échecs du modèle : score 0, comptés à part.
- `error` est une erreur du banc : sans score, écartée des comparaisons, et comptée.
- `context_exceeded` suit sa cause `context_limit` (décision d'Anaël, 2026-10-17 ; règle précisée à la revue du même jour) : `model` si le prompt seul ne tient pas dans le contexte maximal déclaré du modèle (`models_resolved[].context_length`, lu dans `/api/show` au préflight) moins une marge fixe de 256 tokens (`CONTEXT_LIMIT_MARGIN`) : prompt mesuré par Ollama sur l'appel en dépassement (`prompt_eval_count + prompt_eval_cached_count`), ou, pour un palier écarté sans requête, estimation `est_prompt_tokens` de la question (AD-5) ; `bench` sinon (le prompt tient, mais pas avec le plafond de réponse `num_predict`, le palier ou le plafond `num_ctx_max` de la configuration) ; un contexte déclaré illisible donne toujours `bench`. `model` : échec du modèle, score 0, compté comme une troncature. `bench` : erreur du banc, sans score, écartée et comptée.

## Manifeste

Il est écrit au premier lancement et comparé à chaque reprise. Sa partie bloquante contient :
- l'empreinte du jeu de questions et des pistes ;
- la configuration de génération résolue (paramètres de requête, plafonds, paliers de `num_ctx`, liste des modèles) et son empreinte ;
- pour chaque modèle : digest (`/api/tags`), famille et capacités, figés au premier lancement ;
- la version d'Ollama ;
- la machine ;
- l'empreinte du harnais : code de `common/`, `ollama/`, `generation/` et `envs/`.

Si l'une de ces valeurs diffère, la reprise est refusée, avec un message qui nomme le premier champ différent. Un modèle retéléchargé ou un harnais modifié bloque donc la reprise. Une partie informative (Python, paquets, commit, pilote NVIDIA, liste de contrôle) ne bloque jamais.

**Campagne antérieure à `context_limit` :** les schémas `qb.manifest/1`, `qb.generation/1` et `qb.grading/1` ont gagné `models_resolved[].context_length` et `context_limit` sans changer de version (aucune campagne de cette époque n'est conservée : la campagne d'essai `pilot-20261012` repart de zéro). `grade`, `report`, `pilot` et `judge` refusent une telle campagne avant toute validation de schéma, code 2, avec le message « campagne antérieure à context_limit (2026-10-17) : relancer la génération dans une nouvelle campagne ». La seule issue est une nouvelle campagne.

Le manifeste de jugement ajoute le juge (configuration, réglages, empreinte du gabarit de prompt et, pour un juge local, des poids) et l'empreinte du manifeste de génération lu.

## Arrêt et reprise

- **Arrêt propre :** Ctrl+C ou création d'un fichier `STOP`. La question en cours se termine et s'enregistre, le modèle est déchargé, puis le processus sort.
- **Arrêt brutal :** à la reprise, une ligne partielle en fin de fichier est tronquée et sa question rejouée.
- **Reprise :** toute clé déjà présente est sautée. Aucune clé n'est écrite deux fois.
- **Panne d'Ollama :**
  - le banc ne redémarre pas Ollama : il attend que le service réponde (jusqu'à `ollama_wait_s`), revérifie sa version, puis refait toute la question ;
  - si le service reste absent, le processus sort avec un code non nul, sans écrire de ligne ;
  - le statut `error` est réservé à l'échec propre à une question, service vivant, après `max_attempts` essais (3 par défaut) ;
  - 5 erreurs de suite arrêtent la campagne.
- **Maintien en éveil :** la campagne empêche la mise en veille de Windows pendant toute sa durée et rend la main à la sortie.

## Jugement

C'est une phase séparée, lancée après la génération. Elle lit `generation.jsonl` (lignes de rédaction au statut `ok`) et écrit `judgment.jsonl` en ajout seul, une ligne par critère. La clé est celle de génération complétée de `|<critère>`. Elle a la même mécanique de manifeste, d'arrêt et de reprise que la génération. Elle seule a le droit au réseau. Un lot cloud soumis est consigné avant l'attente des résultats : une reprise le relit au lieu de le payer deux fois.

## Pilote

Il tourne sur les 4 modèles de `modeles.md` et produit les mesures de CAP-8 avant toute campagne complète :
- il rejoue un sous-ensemble pour mesurer le taux de réponses qui changent, dans une campagne distincte `<c>-replay` ;
- il mesure la distribution des tokens de réflexion par usage et le taux de troncature aux plafonds ;
- il projette la durée de la campagne en divisant les tokens mesurés par le débit de chacun des 20 modèles. Le préremplissage est compris : la dégradation mesurée par palier (`warmups.jsonl`) s'applique aux débits de l'ancien banc.

Si la projection dépasse 6 jours, on applique l'ordre de réduction des Constraints de `SPEC.md`.

## Jugement local

Le juge local est défini par le contrat `POST /v1/systemone` (questions `noul`, probabilité de vrai) sur `localhost`, pas par un serveur précis. Il ne tourne que pendant la phase de jugement. Il prend le verrou machine et refuse de démarrer si `/api/ps` liste un modèle de génération chargé (VRAM de 8 Go). Le choix du serveur est décrit dans `juge-et-calibration.md`.
