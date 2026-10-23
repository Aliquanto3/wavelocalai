---
workflow: bmad-correct-course
date: '2026-10-21'
mode: 'batch (décisions prises par Anaël en session le 2026-10-21)'
trigger: 'Premiers retours de recette d''Anaël sur la v2 (2.0.0a7, master 5e2da08)'
status: 'Approuvé par Anaël le 2026-10-21 ; exécution une story à la fois (run-autonome.md)'
scope: 'Modéré : une Epic 9 de neuf stories, insérée avant la story 8.4 ; AD-17 et DESIGN.md amendés'
---

# Proposition de changement de sprint : retours de la recette du 2026-10-21

## 1. Résumé du problème

Anaël a utilisé la v2 (préversion 2.0.0a7) et remonte six retours. Ils ont été vérifiés dans le code et sur des captures en 1920 px, prises avec un dossier de données temporaire. L'Arène n'a pas été rejouée, pour ne charger que Granite 350M.

| # | Retour | Constat dans le code ou à l'écran |
|---|---|---|
| R1 | `uv run` devrait ouvrir le navigateur | `wavelocalai/__main__.py` démarre le serveur sans jamais ouvrir de navigateur. |
| R2 | Arène : un modèle qui tourne en boucle (`tev1:0.8b`, question sur la photosynthèse) bloque la comparaison | La requête de l'Arène ne fixe aucun `max_tokens` (`inference/arena.py:286`). Le seul garde-fou est `delays.lane_timeout_s = 300`. Seule la comparaison entière s'annule (`POST /api/runs/{id}/cancel`) : on ne peut pas arrêter une colonne seule. |
| R3 | Arène : on ne voit pas le juge travailler | Les colonnes passent bien à `judging`. Mais le juge note les réponses l'une après l'autre, avec une seule place locale, sans rien publier entre l'entrée en notation et `judge_score` : ni chargement, ni rang dans la file. |
| R4 | Interface peu engageante, l'œil n'est pas guidé, une seule colonne sur grand écran (vaut pour tous les écrans) | Le contenu tient en une colonne d'environ 1 400 px, avec de larges marges vides en 1920 px. Les intertitres (« Scénario », « Réglages ») sont plus visibles que les choix eux-mêmes : prompt en petite police à chasse fixe, modèle sous un libellé discret. Le bouton de lancement du Banc d'essai est sous la ligne de flottaison. L'écran Modèles fait 3 900 px de haut. |
| R5 | Documents : installer le modèle d'embedding depuis l'application | L'écran ne dit rien avant l'import. L'erreur renvoie ensuite à `ollama pull nomic-embed-text` (`errors.py:225`), alors que l'écran Modèles sait installer un modèle Ollama en run `pull`. |
| R6 | Modèles : le bouton du reranker est bloqué et renvoie à une commande | Sans l'extra `rerank` (fastembed), le bouton est désactivé avec « uv sync --extra rerank » (`screens/models-rerank.js`), conformément à AD-17. |

Décisions d'Anaël en session :
- **D-R4-a** : pas d'emojis. Des icônes Material **colorées** et des aplats de la palette Wavestone. Cela amende DESIGN.md, où les icônes étaient monochromes et héritaient de la couleur du texte.
- **D-R6** : fastembed passe en dépendance par défaut.
- **D-suite** : les stories sont écrites, puis exécutées en run autonome. La refonte visuelle passe d'abord par une maquette validée par Anaël.

## 2. Analyse d'impact

### Checklist

| Section | Statut | Constat |
|---|---|---|
| 1. Déclencheur | [x] | Recette humaine sur la préversion a7. Des écarts d'usage, pas un échec technique. |
| 2. Impact sur les epics | [x] | Epics 1 à 8 : aucune story livrée n'est rouverte. Les correctifs vont dans une **Epic 9 « Retours de recette »**, jouée **avant la story 8.4** : la bascule exige une recette humaine de Flow 1 et Flow 2, que R2 et R4 gênent. |
| 3. Conflits d'artefacts | [!] | **Spine AD-17** (extra `rerank`) à amender. **DESIGN.md** à amender : §Brand 4 (icônes monochromes), §Layout (une colonne, pas de grille), §Typography (titres sans couleur). **EXPERIENCE.md** : nouvel état « arrêté » d'une colonne de l'Arène, encart Documents. **contrat-api.md** : route d'arrêt d'une colonne, événement `judge_progress`, champ `stopped_reason`. SPEC.md : périmètre inchangé. |
| 4. Voie retenue | [x] | Ajustement direct (option 1). Pas de retour arrière, pas de révision du MVP. |
| 5. Proposition | [x] | Ce document. |
| 6. Revue et passage de main | [!] | Approbation d'Anaël attendue (§5). |

### Impact technique

- `pyproject.toml` et `uv.lock` (R6) : l'installation de base grossit d'onnxruntime, de tokenizers et de huggingface-hub. Il faut mesurer la taille du `.venv` et la consigner. Les imports restent paresseux (test AST de `test_layers.py` inchangé), et `disable_telemetry()` est toujours appelé avant fastembed.
- Modèle de l'Arène (R2, R3) : une colonne peut finir « arrêtée » avec une réponse partielle **notée**. Ce n'est pas `cancelled`, où rien n'est noté. Les tests de `tests/v2/web/test_arena*` et `tests/v2/e2e/test_arena*` sont à réaligner.
- Front (R4) : feuilles `tokens.css`, `base.css` et `screens.css`, puis la feuille de chaque écran. Les tests de captures et d'accessibilité de la story 8.2 (contrastes, `h1`, contenu coupé) restent la porte de fusion.

## 3. Voie recommandée

**Ajustement direct** : neuf stories dans une Epic 9, avant la story 8.4.
- **Effort** : environ deux journées de run autonome.
  - Petites : 9.1, 9.5.
  - Moyennes : 9.2, 9.3, 9.4.
  - Une maquette à valider par Anaël : 9.6.
  - Trois stories de refonte : 9.7, 9.8, 9.9.
- **Risque** :
  - La refonte (R4) est la plus risquée : elle touche tous les écrans. D'où la maquette d'abord, puis une story de fondation qui porte la grille, les jetons et la hiérarchie, avant les écrans.
  - La détection de boucle doit éviter les faux positifs (listes, tableaux, code) : elle n'agit qu'au-delà d'un seuil élevé et reste réglable.
- **Préversion** : 2.0.0a8 en fin d'Epic 9.

## 4. Propositions de changement détaillées

### 4.1 Stories (ajout à `epics.md`, nouvelle section avant « À ajouter aux stories du MVP »)

```
## Epic 9 : Retours de la recette du 2026-10-21

Corrige ce que la première recette humaine de la v2 a relevé, avant la bascule (story 8.4).
```

**Story 9.1 : Le lanceur ouvre l'application dans le navigateur**
- *Given* `uv run wavelocalai-v2` (le nom passe à `wavelocalai` à la story 8.4), *When* le serveur écoute, *Then* le navigateur par défaut s'ouvre sur `http://127.0.0.1:<port>/`. L'ouverture a lieu une seule fois, après que le port répond, jamais avant.
- *And* `--no-browser` et le réglage `[server] open_browser = false` l'empêchent. Les tests, la CI et les E2E lancent le serveur sans navigateur.
- *And* un échec d'ouverture (aucun navigateur, session sans affichage) écrit l'URL dans la console et le journal, sans arrêter le serveur.
- Gouverné par AD-23.

**Story 9.2 : L'Arène arrête un modèle qui tourne en boucle, automatiquement ou à la demande (serveur et écran)**
- *Given* une comparaison, *When* une colonne génère, *Then* la requête porte un plafond `arena.max_tokens` (réglable dans `wavelocalai.toml`). Une colonne qui l'atteint finit avec `stopped_reason: "max_tokens"`, sa réponse partielle est gardée et **notée**.
- *Given* une sortie qui se répète (même fragment final répété au-delà d'un seuil, par exemple 4 fois au moins sur une fenêtre de 200 caractères ou plus), *When* le détecteur la voit, *Then* la génération s'arrête avec `stopped_reason: "loop"`, et la colonne affiche « Arrêté : le modèle se répétait ».
  - Le seuil et la fenêtre sont réglables.
  - Un jeu de tests garde les faux positifs à zéro sur des listes, des tableaux Markdown et du code.
- *Given* une colonne en cours, *When* l'utilisateur clique « Arrêter ce modèle », *Then* `POST /api/runs/{lane_run_id}/stop` arrête cette colonne seule, avec `stopped_reason: "user"`. Les autres continuent.
  - Cet arrêt garde la réponse partielle et la fait noter. Il se distingue de l'annulation, qui ne note rien.
  - Le CO₂ et le débit de la colonne arrêtée restent mesurés (AD-10).
- *And* `contrat-api.md` documente la route, `stopped_reason` dans `lane_status`, et l'état « arrêté » dans EXPERIENCE.md. Les exports CSV et Markdown de l'Arène portent la raison.
- *And* tests réalignés : `tests/v2/web/` et `tests/v2/e2e/` de l'Arène, composant `wl-arena-lane`.

**Story 9.3 : On voit le juge de l'Arène travailler**
- *Given* des colonnes terminées, *When* le juge note, *Then* le serveur publie `judge_progress` `{judge, phase: queued|loading|scoring, lane, position, total}`.
- *And* un bandeau du juge, au-dessus des colonnes, affiche « Juge : <modèle> · chargement » puis « Notation 2 sur 3 · <colonne> », avec le temps écoulé.
- *And* dans chaque colonne, l'état « En file pour la notation » se distingue de « Notation en cours ».
- *And* une comparaison sans juge le dit dans le bandeau, sans compteur. Un juge en panne laisse les notes à « non évalué » avec la raison, comme aujourd'hui.
- *And* `contrat-api.md` documente l'événement. Tests de l'Arène réalignés.
- Après 9.2 : mêmes fichiers.

**Story 9.4 : Installer le modèle de représentation depuis la Base documentaire**
- *Given* aucun modèle d'embedding installé, *When* on ouvre la Base documentaire, *Then* un encart d'alerte l'annonce **avant tout import**. Il propose le bouton « Installer nomic-embed-text », avec sa taille et le fait qu'il télécharge, et la zone d'import est désactivée avec sa raison.
- *When* on clique, *Then* le run `pull` de l'écran Modèles (même route, même composant de progression, « Annuler » compris) installe le modèle. L'encart disparaît à la fin, et le modèle devient le défaut de représentation.
- *And* le tag proposé est vérifié par une installation réelle pendant la story, pas de mémoire. Le message de `errors.py:225` renvoie désormais à ce bouton plutôt qu'à une commande.
- *And* Ollama absent : le bouton est désactivé, avec la raison existante.

**Story 9.5 : fastembed est installé d'office, le bouton du reranker fonctionne**
- *Given* `uv sync` seul, *When* on ouvre l'écran Modèles, *Then* « Installer le reranker » est actif et ne fait que télécharger le modèle (run `pull`, AD-17).
- *And* fastembed passe de l'extra `rerank` aux `dependencies`, à une version vérifiée sur PyPI et par installation réelle. `uv.lock` est régénéré. La taille du `.venv` avant et après est consignée dans la story.
- *And* l'extra `rerank` est retiré, ainsi que tout texte d'interface, toute doc (README) et tout test qui citent `uv sync --extra rerank`. Les imports restent paresseux, `disable_telemetry()` reste avant fastembed, et `test_layers.py` est vert.
- *And* la spine AD-17 est amendée (voir §4.2).

**Story 9.6 : Maquette de la nouvelle mise en page (humaine)**
- *Given* les retours R4, *When* la maquette est produite, *Then* elle montre en 1920, 1440 et 1280 px, en clair et en sombre, au moins le Banc d'essai, l'Arène (formulaire et résultats), la Base documentaire et Modèles. Elle couvre aussi le mobile (390 px).
- La maquette porte :
  - une grille à **deux colonnes au-delà de 1 400 px environ** : saisie et choix du modèle à gauche ; réglages repliés, aperçu et résultats à droite ;
  - une **hiérarchie qui met en avant** le prompt (police normale, grand champ), le ou les modèles (cartes de choix) et le bouton principal, visible sans défilement ;
  - des **réglages secondaires discrets**, avec des intertitres plus petits que les champs qu'ils regroupent ;
  - une **couleur qui guide l'œil** : icônes Material colorées par module, aplats légers de la palette Wavestone sur les zones d'action, sans emojis ;
  - des contrastes conformes à la story 8.2.
- *And* Anaël valide la maquette. Les décisions sont consignées, puis DESIGN.md et EXPERIENCE.md sont amendés avant 9.7.

**Story 9.7 : Fondation de la mise en page et écrans de l'Arène**
- *Given* la maquette validée, *When* on l'implémente, *Then* `tokens.css` et `base.css` portent la grille responsive, la nouvelle échelle de titres et de libellés, et les couleurs d'icônes. Chat libre, Arène, Banc d'essai et Références suivent la maquette.
- *And* les tests de la story 8.2 (contrastes calculés, `h1` focalisé, contenu coupé, projection) restent verts. Les captures E2E sont réalignées.

**Stories 9.8 et 9.9 : les autres écrans suivent la maquette**
- 9.8 couvre Documents (Discussion, Base, Évaluation) et Agents (seul, équipe).
- 9.9 couvre Modèles, Sobriété et Accueil, et inclut la préversion 2.0.0a8 en fin d'epic (tag annoté et release GitHub).
- Même critère que 9.7 pour chaque écran. Elles se jouent en parallèle : les écrans sont disjoints.

### 4.2 Architecture (spine AD-17, via `bmad-architecture` dans la story 9.5)

```
OLD : … le reranker est fastembed (extra `rerank`), chargé avec `local_files_only=True` …
NEW : … le reranker est fastembed (dépendance de base depuis la recette du 2026-10-21, décision D-R6),
      chargé avec `local_files_only=True` … Modèle absent ou `ValueError` au chargement : le RAG tourne
      sans reranker et l'écran dit pourquoi.
```
Il faut aussi retirer « fastembed dans l'extra `rerank` » de la règle de coexistence (AD-1) et de `.memlog.md`, où la décision est datée.

### 4.3 UX (DESIGN.md, EXPERIENCE.md ; dans la story 9.6, après validation)

- DESIGN.md §Brand 4 : « Icônes monochromes, qui héritent de la couleur du texte » devient « Icônes Material Symbols Rounded, colorées par module selon la palette ; jamais d'emoji » (D-R4-a).
- DESIGN.md §Layout : la règle « une colonne » et « pas de grille de cartes » devient une grille à deux colonnes au-delà d'environ 1 400 px, avec les cartes de choix de modèle admises. Les valeurs exactes viennent de la maquette.
- DESIGN.md §Typography : le libellé d'un champ principal (prompt, modèle) est au moins aussi visible que l'intertitre de sa section.
- EXPERIENCE.md :
  - état « arrêté » d'une colonne de l'Arène (9.2) et bandeau du juge (9.3) ;
  - encart « Aucun modèle de représentation » de la Base documentaire (9.4) ;
  - ouverture automatique du navigateur (9.1).

### 4.4 Sprint status

Ajout de `epic-9: backlog` et des stories `9-1` à `9-9` en `backlog`. La story 8.4 reste après l'Epic 9.

## 5. Passage de main

- **Portée** : modérée. Réorganisation du backlog et deux artefacts de conception amendés.
- **Ordre du run** :

| Vague | Stories en parallèle | Après |
|---|---|---|
| V0 | 9.1 · 9.4 · 9.5 · 9.2 · 9.6 (humaine) | — |
| V1 | 9.3 | 9.3 ← 9.2 |
| V2 | 9.7 ★ | 9.7 ← 9.3 ; 9.7 ← 9.6 |
| V3 | 9.8 · 9.9 | 9.8 ← 9.7 ; 9.9 ← 9.7 |

  9.4 et 9.5 touchent toutes deux `models-pull.js` à la lecture seulement. Si l'une doit le modifier, elle passe après l'autre.
- **Exécution** : run autonome, avec dev-story (Sonnet), second avis (Haiku) et revue (Opus). Le run s'arrête seulement à la validation de la maquette 9.6.
- **Critères de réussite** :
  - un modèle en boucle ne retient plus l'Arène plus de quelques secondes après le seuil ;
  - le juge est visible du début à la fin de la notation ;
  - embedding et reranker s'installent sans terminal ;
  - en 1920 px, prompt, modèle et bouton de lancement tiennent sans défilement sur le Banc d'essai et l'Arène ;
  - `tests/v2` est vert, et la suite E2E nocturne aussi.
