# Correctifs du frontend en session cloud de nuit

Mode d'emploi pour implémenter [`SYNTHESE.md`](SYNTHESE.md) avec Claude Code dans le cloud, sans surveillance, puis vérifier au matin.

Vérifié le 2026-09-26 sur les sources suivantes :

- `bmad-method` **6.12.0**, dernière version sur npm, avec les skills installés dans `agentic-harness-training-demo` ;
- la documentation de Claude Code on the web (`code.claude.com/docs/en/claude-code-on-the-web`, `cloud-environments`, `routines`).

## Ce qui conditionne l'organisation

- **Le découpage en stories de `bmad-spec` est interactif uniquement** (« Headless runs never do this »). `SPEC.md` et `stories.yaml` se préparent donc avec toi, **avant** la nuit.
- **`bmad-build-auto` traite une seule story par appel.** On lui donne le dossier de la spec et un identifiant de story. Il exige un arbre de travail propre et une branche cohérente avec l'epic. Il commite, mais **ne pousse pas**. Il écrit le résultat dans `stories/<id>-*.md` (`status` et `## Auto Run Result`). Il ne lit ni les *checkpoints* ni `invoke_dev_with` : c'est à l'appelant de les gérer. La boucle sur les stories revient donc au prompt de nuit ci-dessous.
- **La VM cloud :**
  - Ubuntu 24.04, 4 vCPU, 16 Go de RAM, sans GPU ;
  - `uv`, Python et Node préinstallés ;
  - réseau « Trusted » par défaut, avec PyPI, npm et GitHub autorisés ;
  - elle ne pousse que sur des branches `claude/…` et continue quand tu fermes ton navigateur.
- **Pas d'Ollama dans la VM.** On pourrait l'y installer, mais il faudrait ouvrir le réseau et télécharger des modèles. La nuit vérifie donc avec les tests unitaires et `AppTest` (providers simulés). Les parcours avec de vrais modèles se font au matin.

## A. Avant la nuit (en local, interactif, ~1 h)

1. **Fusionner la PR de synthèse** dans `master`.
2. **Installer BMAD :** `npx bmad-method@6.12.0 install`.
   - Réponses : langue française, dossier de sortie `_bmad-output`, module `bmm`, outil Claude Code.
   - Commiter `_bmad/` et `.claude/skills/bmad-*`, comme dans `agentic-harness-training-demo`. La session cloud ne voit que ce qui est dans le dépôt.
3. **`bmad-project-context`** : le dépôt n'a ni `AGENTS.md` ni `CLAUDE.md`.
4. **`bmad-ux`**, avec en entrée `SYNTHESE.md` (§1 et §3.2) et `poste-rtx3060/UX.md` (§3 et §4). Il produit `DESIGN.md` et `EXPERIENCE.md`, dont le lexique des modules. C'est le seul moment où tu fixes le design ; le rendu se valide au matin (D4).
5. **`bmad-spec`** avec le *slug* `fiabilisation-frontend` et `SYNTHESE.md` en entrée.
   - Faire adopter `DESIGN.md` et `EXPERIENCE.md` comme *companions*.
   - Demander la *Story Breakdown* et reprendre le §4 de la synthèse : 11 stories, `spec_checkpoint: false` et `done_checkpoint: false` partout, et les notes du §4 dans `invoke_dev_with`.
   - Résultat : `_bmad-output/specs/spec-fiabilisation-frontend/` avec `SPEC.md` et `stories.yaml`.
6. **Commiter et pousser** sur `master` : la session cloud clone la branche par défaut.

## B. Environnement cloud

Dans les réglages de l'environnement, sur claude.ai/code :

- **Réseau :** « Trusted » suffit (PyPI, npm, GitHub).
- **Script d'installation**, exécuté avant le démarrage de Claude :

  ```bash
  uv venv .venv-app --python 3.12
  uv pip install --python .venv-app/bin/python -r requirements.txt pytest pytest-mock
  ```

  La story 1 introduit un fichier de contraintes. Après elle, le prompt de nuit réinstalle depuis ce fichier.

  L'installation est longue : `torch` arrive par `sentence-transformers`. Le résultat du script est mis en cache par l'environnement, il vaut donc mieux lancer une session de test la veille.
- **Aucun secret :** pas de clé Mistral, OpenAI, Anthropic ni SMTP. Les tests n'en ont pas besoin, et leur absence garantit qu'aucun appel ne sort.

## C. Prompt de nuit

À coller dans une nouvelle session cloud sur le dépôt, en mode « Accept edits » ou « Auto ». Une routine *one-off* planifiée fonctionne aussi.

```text
Tu travailles seul cette nuit : personne ne répondra à tes questions. Ne pose aucune question ;
en cas de doute, choisis l'option la plus prudente et note-la dans le rapport de nuit.

Contexte : docs/audits/frontend-2026-09/SYNTHESE.md et la spec
_bmad-output/specs/spec-fiabilisation-frontend/ (SPEC.md, companions, stories.yaml).
Si SPEC.md ou stories.yaml manque, arrête-toi et écris seulement le rapport de nuit.

Préparation :
- Crée la branche claude/fiabilisation-frontend depuis master (ou reprends-la si elle existe).
- Environnement Python : .venv-app. Commande de tests : `.venv-app/bin/python -m pytest tests/unit -q`,
  puis, dès que la story 1 les a créés, `tests/app` et la commande qu'elle documente.
  Lint : `ruff check src tests`.

Boucle, pour chaque entrée de stories.yaml, dans l'ordre :
1. Si stories/<id>-*.md existe déjà avec status: done, passe à la suivante (reprise).
2. Si une story dont elle dépend (tableau du §4 de SYNTHESE.md) n'est pas done, ne la lance pas :
   note-la « sautée (dépendance <id>) » et continue.
3. Invoque le skill bmad-build-auto avec ce prompt, en ajoutant le texte invoke_dev_with de l'entrée :
   « Dossier de spec : _bmad-output/specs/spec-fiabilisation-frontend — story id : <id> ».
4. Au retour, lis le status de stories/<id>-*.md. S'il vaut done :
   - si la story a changé les dépendances, réinstalle .venv-app depuis le fichier de contraintes ;
   - lance les tests et ruff ;
   - si c'est vert, `git push` ;
   - si c'est rouge, tente au plus une correction dans une nouvelle invocation de bmad-build-auto
     sur la même story. Si c'est toujours rouge, `git revert` des commits de la story, pousse,
     et note « annulée : tests rouges » avec la sortie.
   Sinon (blocked, etc.), note la condition bloquante et pousse ce qui est commité.

Interdits :
- merger une PR, forcer un push, réécrire l'historique de master ;
- modifier scripts/benchmark_slm.py, benchmarks/, ou un environnement autre que .venv-app ;
- télécharger un modèle, appeler une API de LLM, envoyer un email ;
- écrire dans data/chroma ;
- éditer SPEC.md ou stories.yaml à la main : bmad-spec en est le seul auteur ;
- désactiver, marquer skip ou affaiblir un test pour le faire passer.

Fin de nuit :
- Écris docs/audits/frontend-2026-09/RAPPORT-NUIT.md avec :
  - un tableau (story, statut, commits, tests, durée) ;
  - pour chaque story, ce qui reste à vérifier à la main ;
  - les choix faits sans validation ;
  - les questions ouvertes.
- Commite, pousse, puis ouvre une PR en brouillon vers master, avec ce rapport en description.
```

## D. Au matin

1. **Lire `RAPPORT-NUIT.md`** et la PR en brouillon : statut de chaque story, choix faits seul, stories sautées ou annulées. Dans le dossier de la spec, `stories/<id>-*.md` donne le plan et la revue de chaque story.
2. **Récupérer la branche en local :**
   - `git fetch origin claude/fiabilisation-frontend`, puis `git switch claude/fiabilisation-frontend` ;
   - recréer l'environnement depuis le fichier de contraintes ;
   - lancer les tests.
3. **Parcours avec de vrais modèles** (Ollama démarré) :
   - la suite `tests/e2e` de la story 11, si elle a abouti ;
   - sinon, les scripts d'audit `pro-elitebook-x360/e2e/` (`node e2e.js --with-upload`, qui doit désormais passer les étapes 1, 7 et 8) et `poste-rtx3060/playwright/` ;
   - `--with-upload` indexe un document de test : le faire sur une collection de test, ou supprimer le document ensuite.
4. **Revue visuelle**, en thème clair et sombre, à comparer avec `DESIGN.md` : accueil, Cockpit, Inférence, RAG et Agent Lab. Vérifier le lexique d'`EXPERIENCE.md` sur la navigation et les titres.
5. **Sur `pro-elitebook-x360` seulement :** mener le spike F15 (CodeCarbon à 112 W). Il demande les sondes du portable réel.
6. **Décider story par story :** chaque story a ses propres commits. On garde, on corrige (`bmad-build` en interactif) ou on revert, puis on sort la PR du brouillon.
