# Orchestration autonome : revue 4 à 6, stories 7 à 9 et pilote

Prompt d'un run sans Anaël, préparé le 2026-10-12 sur la tour (tour-rtx3050), branche `feat/quality-bench-suite`. Il fait suite à `RAPPORT-STORIES-2-6.md`.

## Avant tout

1. Commiter ce fichier seul (`Docs: prompt d'orchestration des stories 7 à 9`), pour que `bmad-build-auto` parte d'un arbre propre.
2. Lire `AGENTS.md`, `SPEC.md` et ses compagnons, `stories.yaml` (stories 7 à 9), le spine d'architecture (AD-13, AD-14, AD-16, AD-17), `RAPPORT-STORIES-2-6.md` et `_bmad-output/implementation-artifacts/deferred-work.md`.
3. Relever, sans les afficher, la présence de `ANTHROPIC_API_KEY` et `MIMO_API_KEY`. Elles peuvent venir de l'environnement ou du `.env` de la racine (ignoré par git, chargé par `disable_telemetry()` en tête de la CLI, sans écraser l'environnement). Pour le savoir sans lire le fichier : `.venv-quality\Scripts\python -c "from src.core.telemetry import disable_telemetry; disable_telemetry(); import os; print({k: bool(os.environ.get(k)) for k in ('ANTHROPIC_API_KEY', 'MIMO_API_KEY')})"`. Une clé absente ne bloque pas le run : le juge concerné est codé et testé sur un faux serveur, et l'absence figure dans le rapport.
4. Vérifier la base : `.venv-quality\Scripts\python -m pytest tests/quality_bench -q` (1 059 verts attendus, filtre télémétrie compris), Ollama en 0.40.2, les 4 modèles du pilote présents.

## Décisions déjà prises par Anaël

- **Serveur du juge local :** Winnow-E4B (`EldanRing/Winnow-E4B`, GGUF Q8_0) importé dans Ollama 0.40.2 comme modèle `decision`. Repli : Perplexity Decider hébergé, seulement si une clé existe ; sinon le consigner et continuer avec les juges cloud. WSL n'est pas installé sur la tour : option écartée. Le téléchargement du GGUF (8 Go) est autorisé, **avant** toute génération du pilote.
- **Budget cloud :** 5 $ au plus pour tout le run (essais et jugement du pilote). Coût consigné par appel et par lot ; arrêter les appels cloud avant de dépasser. Revérifier les prix avant de coder.
- **Git :** commits locaux seulement, ni push ni PR.
- **Périmètre :** jusqu'au rapport de pilote et à l'échantillon d'étiquettes prêt. Arrêt ensuite.
- **Pauses :** aucune pause de relecture. Le `spec_checkpoint` de la story 7 ne s'arrête pas : le choix du serveur se fait par mesure et se consigne. Ne s'arrêter que sur un vrai blocage.

## Mode

Comme au run précédent (mode A) : un sous-agent `general-purpose` par story, qui invoque `bmad-build-auto`. L'appel reprend l'`invoke_dev_with` de `stories.yaml`, complété par :
- les permis et interdits de ce fichier ;
- la tour n'a pas de venv d'app : seuls `tests/quality_bench` et `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` tournent, dans `.venv-quality` ; rien ne s'installe ailleurs ;
- les points de `deferred-work.md` qui concernent la story.

Après chaque story, l'orchestrateur relance lui-même les tests. Il réinstalle aussi `scripts/quality_bench/requirements.txt` dans `.venv-quality` si la story le modifie. Une story qui fait régresser un test vert n'est pas acceptée : la renvoyer au même sous-agent.

Si un sous-agent bute deux fois sur le même problème, l'arrêter et passer à ce qui n'en dépend pas, puis le consigner dans le rapport.

## Phases

### 1. Revue de suivi des stories 4 à 6

`bmad-code-review` sur `8c42d53..HEAD` : les stories 4, 5 et 6 ont 5, 2 et 7 corrections medium qu'aucune passe n'a relues. Appliquer les constats retenus, tests verts, commit `Fix:`. Ce qui touche à une décision d'Anaël va dans `deferred-work.md`, pas dans le code.

### 2. Story 7, jugement découplé

- Télécharger le GGUF de Winnow-E4B sous `data/` (hors dépôt), l'importer dans Ollama, mesurer la VRAM et le déport en CPU sur la RTX 3050. Vérifier que `/v1/systemone` répond et que Winnow tient en français sur quelques critères de `writing-fr.yaml`, avec des réponses synthétiques bonnes et mauvaises. Consigner le choix dans la story et dans `juge-et-calibration.md`.
- Commande `judge` selon AD-16 : `winnow`, `haiku` (Message Batches, sortie structurée, aucune température), `mimo`, `decider`. Lots consignés dans `batches.jsonl` avant l'attente ; exception sur toute question `private`.
- Si les clés existent : quelques vrais appels Haiku et MiMo sur des questions de rédaction publiques, réponses synthétiques, coût consigné.
- Décharger Winnow à la fin (`keep_alive: 0`) : le GPU doit être libre pour le pilote.

### 3. Story 8, code seulement

Commande `pilot` (lecture et rapport seuls) et YAML des campagnes `pilot-*` et `pilot-*-replay`. Le sous-agent s'arrête au code testé et commité : la story reste `in-progress`. L'orchestrateur lance lui-même la campagne aux phases 5 et 6, puis passe la story à `done`.

### 4. Story 9, code seulement

Commande `calibrate` : accord, coût, part escaladée de la cascade simulée, biais Qwen, stabilité par rejeu. Le sous-agent propose le format de `calibration/labels.jsonl` (même clé que les jugements) et le teste sur des étiquettes synthétiques. Seuils d'accord et biais Qwen maximal : des paramètres, sans valeur par défaut choisie à la place d'Anaël. La story reste `in-progress`, en attente des étiquettes.

### 5. Essai sur le vrai Ollama

- Liste de contrôle d'AD-13 : version 0.40.2, `OLLAMA_NUM_PARALLEL` absent ou à 1, GPU libre (`nvidia-smi`, `/api/ps` vide, Overwolf fermé), données NLTK présentes. Ce qui relève d'Anaël (mises à jour d'Ollama coupées, Windows Update en pause) se relève dans le manifeste ; une anomalie bloquante (GPU occupé, autre version) arrête le run avant la génération.
- Préflight des 4 modèles, une chauffe, quelques questions par piste dans une campagne d'essai jetable. Comparer à `tests/quality_bench/ollama_fake.py` : `remote_host`, capacités, `context_length`, `/api/ps`, `prompt_eval_cached_count`, `done_reason: "length"`, déchargement. Corriger le faux Ollama et le code au besoin, tests verts, commit.
- Ces corrections changent l'empreinte du harnais : **aucune modification du code après le lancement de la phase 6**.

### 6. Génération du pilote

- Lancer la génération `pilot-*` en tâche de fond. Mesurer le débit sur la première demi-heure et consigner la durée projetée.
- La machine reste au repos : ni développement, ni tests, ni téléchargement pendant la génération. L'orchestrateur ne fait que surveiller, à 20 minutes d'intervalle au moins.
- Panne d'Ollama : la reprise suit AD-13. Si la génération s'arrête, la relancer avec le même manifeste et vérifier qu'il n'y a ni doublon ni trou. Si le manifeste diffère, ne pas forcer : le consigner et s'arrêter.
- Puis la campagne `pilot-*-replay`.

### 7. Correction, jugement et rapport de pilote

- `grade` sur les deux campagnes.
- `judge` : Winnow d'abord (le GPU est libre), puis Haiku en batch, puis MiMo dans la limite du budget restant. Rédaction marquée provisoire.
- Commande `pilot` : discordance, usages au plafond ou au plancher, stabilité, tokens de réflexion, troncature, projection de durée des 20 modèles, cohérence d'ordre avec l'ancien banc. Si la projection dépasse 6 jours, appliquer l'ordre de réduction de `SPEC.md` **en proposition seulement** : la décision revient à Anaël.
- Échantillon d'environ 100 critères à étiqueter, sous `data/quality_bench/calibration/` (jamais commité), qui mêle candidats Qwen et non-Qwen, avec le format de la phase 4 et une consigne courte pour Anaël.
- Points de `deferred-work.md` « à trancher au pilote » : y ajouter les mesures réelles (`context_exceeded` de `bfcl-multi`, unités non appariées du meneur, reprises non comptées, cache de préfixe). Ne pas trancher.

## Interdits

- Aucun push, aucune PR, aucun commit sur `master`.
- Rien de `data/` dans un commit ; aucune question privée ni réponse à une question privée dans un commit ou un journal versionné ; aucune question privée envoyée à un juge cloud.
- Ne toucher ni `scripts/benchmark_slm.py`, ni `src/core/`, ni `.venv`, ni `_bmad/`, ni `.claude/skills/bmad-*`.
- Aucun téléchargement une fois la phase 6 lancée.
- Aucune clé d'API dans un fichier versionné. Le `.env` de la racine est admis (ignoré par git), mais ni l'orchestrateur ni les sous-agents ne le lisent, ne l'affichent ou ne le modifient. Le juge lit les clés dans `os.environ`, une fois `disable_telemetry()` appelé. La story 7 peut ajouter `MIMO_API_KEY` en commentaire dans `.env.example`.
- Commits en `Préfixe: description en français`, avec la ligne d'attribution habituelle.

## Arrêt et rapport

Écrire `RAPPORT-STORIES-7-9.md` à côté de ce fichier, sur le modèle de `RAPPORT-STORIES-2-6.md`, puis le commiter (`Docs:`). Il contient :
- les phases, statuts, commits, tests après chaque phase et durées ;
- le choix du serveur du juge et ses mesures (VRAM, tenue en français) ;
- le budget cloud dépensé, par juge ;
- les choix faits seul ;
- les chiffres clés du rapport de pilote et la projection de la campagne complète ;
- ce qu'il reste à Anaël : nombre de questions, plafonds de tokens et nombre de tirages par question (story 8), les ~100 étiquettes, le seuil d'accord et le biais Qwen maximal (story 9), le fichier `aa-<date>.json`, les licences encore à confirmer, la remise en veille normale de la tour (`powercfg`) et la relance d'Overwolf.
