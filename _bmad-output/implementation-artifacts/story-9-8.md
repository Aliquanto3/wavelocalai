---
title: 'Story 9.8 : Documents et Agents suivent la nouvelle mise en page'
type: 'feature'
created: '2026-10-22'
status: 'review'
baseline_commit: '633bf1b'
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/docs/maquette-v2-mise-en-page/DECISIONS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-9-7.md'
warnings: []
deferred: []
---

# Story 9.8 : Documents et Agents suivent la nouvelle mise en page

Critères : `epics.md`, story 9.8. Maquette : `docs/maquette-v2-mise-en-page/` (DECISIONS.md §4 à §6).
Contrat de jetons et de classes posé par la story 9.7 (`story-9-7.md`) : tout était déjà en place
(`tokens.css`, `base.css`) — cette story ne fait que les appliquer aux écrans de Documents et
d'Agents.

## Périmètre

| Écran | Fichier(s) | Traitement |
|---|---|---|
| Discussion | `screens/documents.js` | Icône de module (`.icon-mod.docs`) devant le `h1` ; pas de grille (fil de discussion, comme Chat libre en 9.7) |
| Base documentaire | `screens/documents-base.js`, `screens/documents-embedding-alert.js` | Icône de module ; grille `.two-col` (dépôt + liste à gauche, réglages repliés à droite), conforme à `docs/maquette-v2-mise-en-page/index.html` (`screenDocsBase`) ; encart d'alerte en `.alert-warning` ; zone de dépôt en `.zone-disabled` quand bloquée ; intertitre « Documents de la base » en `.section-label` |
| Évaluation de la qualité | `screens/documents-eval.js`, `screens/eval-form.js` | Icône de module ; grille `.two-col` (question/modèles à gauche, juge et lancement à droite) |
| Agent seul | `screens/agents-solo.js` | Icône de module (voir ci-dessous) ; grille `.two-col` sur les réglages (modèle à gauche, outils à droite) |
| Équipe d'agents | `screens/agents-crew.js` | Icône de module ; grille `.two-col` sur le formulaire de lancement (équipe/sujet à gauche, modèle de repli et lancement à droite) |

## Icône du module Agents

La maquette validée (DECISIONS.md §6) ne couvre que Banc d'essai, Arène, Base documentaire et
Modèles : aucun jeton n'est prévu pour le module Agents. Choix retenu par cohérence avec l'Arène
(une tâche confiée à un ou plusieurs modèles, comme une comparaison) : `moduleTitle("smart-toy",
"arena", …)` réutilise `.icon-mod.arena` (violet, `--color-icon-arena`) tel quel, sans nouvelle
classe ni nouveau jeton. Le test de contraste de la pastille (`test_accessibilite.py`,
`RENDERED_MODULE_ICONS`) n'a donc pas eu besoin d'entrée `agents` : elle hériterait des mêmes
valeurs que `arena`.

## Base documentaire : fidélité à la maquette

`docs/maquette-v2-mise-en-page/index.html` (`screenDocsBase`) donne la disposition exacte : colonne
de gauche avec l'encart d'alerte, la zone de dépôt (désactivée si l'encart est visible) et la liste
des documents ; colonne de droite avec les réglages repliés (`<details>` existant,
`documents-settings.js`, non touché). `documents-embedding-alert.js` a été restructuré : l'icône et
le texte (titre, bouton, aide, progression) sont désormais dans un seul bloc, pour que la section
porte `.alert-warning` (liseré et fond ambre, base.css) sans entrer en conflit avec la mise en page
interne (`.docs-embedding-alert-body`, `documents.css`, structurelle seulement). `drop.dataset.
blocked` reste posé (lu par `tests/v2/e2e/test_documents_embedding.py`) ; `.zone-disabled` est
ajoutée/retirée en même temps.

## Plafond de 600 lignes (`documents-base.js`)

Le fichier était déjà à 600 lignes. Pour ajouter la grille sans le dépasser, deux fonctions ont été
extraites vers `documents-import-row.js` (déjà le foyer des éléments d'import) : `spreadProgress`
(répartition de la progression d'envoi sur les fichiers) et `importSentence` (ex-`sentence`, la
phrase de fin d'import). `documents-base.js` : 576 lignes après la story (il était à 600).

## Grilles en conflit avec `.two-col`

Trois feuilles de style posaient déjà `display: grid` avec leur propre `grid-template-columns` sur
le conteneur devenu `.two-col`, à un point de bascule différent (768 px au lieu de 1400 px) :
`.eval-form` (`evaluation.css`), `.agents-settings` (`agents.css`). Chargées après `base.css`, ces
règles auraient gagné la cascade et empêché la grille à deux colonnes de s'appliquer. Dans les deux
cas, `display` et `grid-template-columns` ont été retirés de la règle d'écran (qui ne garde que
l'espacement propre à l'écran) ; `.eval-form` a aussi été retiré de la liste `grid-template-columns:
minmax(0, 1fr)` partagée avec `.eval-run`/`.eval-results`/… (ce rôle est maintenant tenu par
`.two-col`). `.crew-controls` (`agents-crew.css`) n'avait pas de `grid-template-columns` propre :
aucun conflit.

## Tests

Unitaires et web ciblés (`tests/v2/unit tests/v2/web -k "static or i18n or layers or tokens or
documents or eval or agents"`) : 423 passés.

E2E (Edge, un fichier à la fois) :

| Fichier | Résultat |
|---|---|
| `test_documents.py` | 30 passés |
| `test_documents_embedding.py` | 3 passés |
| `test_documents_manage.py` | 21 passés |
| `test_evaluation.py` | 24 passés |
| `test_agents_solo.py` | 28 passés |
| `test_agents_crew.py` | 19 passés (1 échec transitoire à la première passe complète du fichier — `shell-ready` jamais atteint —, vert en isolation et vert à la deuxième passe complète : flaky, pas une régression) |
| `test_parcours_agents.py`, `test_parcours_evaluation_banc.py` | 2 passés |
| `test_accessibilite.py` (33 min, hors `*-1440` et `*-320` déjà signalés instables hors story) | 26 passés, 3 échecs à la passe complète (`axe` systeme-clair sur `/documents/base`, défilement horizontal zoom 200 % sombre projection, focus clavier du `h1` du Banc d'essai) — les trois verts en isolation : flakiness du poste après 30+ minutes d'automatisation continue (mémoire/temporisations), pas de régression liée à la story (aucun des trois ne touche les écrans de 9.8 sauf le premier, dont la cause — `wl-confirm-dialog` déjà présent avant la story — est indépendante de la grille ajoutée) |

Aucun des trois critères de la story 8.2 (contrastes, `h1` focalisé, contenu coupé, projection) n'a
de régression reproductible. Aucune réalignement d'E2E (`inner_text()` → `text_content()`) n'a été
nécessaire : aucun intertitre `.section-label` nouveau ne porte de texte lu par un test existant
(seul ajout, « Documents de la base », n'est asserté nulle part en `inner_text()`).

Contrôle rapide (`controle_rapide.py`) : rien à signaler (aucun fichier Python modifié, la story est
front seulement).

## Report

Rien : le périmètre de la story est couvert en entier (les 5 écrans listés par `epics.md` et
`DECISIONS.md` §6).
