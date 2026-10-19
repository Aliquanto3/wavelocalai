---
title: 'Dette de l''Epic 8 : budget de rendu de la coquille'
type: 'fix'
created: '2026-10-19'
status: 'review'
baseline_commit: '33d97a1'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
warnings: []
deferred:
  - 'Autres points de la story 8.1 (écarts n° 1, 4, 5, 7, 12, 13, Self-RAG, copies .db.bak, wl-model-picker, sprite) : à venir dans cette spec.'
  - 'Les ~35 feuilles de style restent liées dans index.html (35 requêtes, 10 à 60 ms en parallèle, hors du chemin critique une fois les modules préchargés) : à regrouper si le budget se resserre.'
  - 'tests/v2/e2e/test_chat.py::test_the_arena_module_is_available_and_its_other_tabs_are_disabled_with_their_reason attend « Références » désactivé alors que l''écran est livré (7.x) : test périmé, hors périmètre de ce correctif.'
---

# Story 8.1 : dette (en cours)

## Budget de la coquille

Test : `test_shell_renders_under_300_ms_without_waiting_for_the_api_ollama_stopped` (AD-15, deuxième meilleur de 5 chargements, Edge headless, Windows).

**Mesure avant** (branche `feat/v2-dette`, toutes les stories des Epics 5 à 7) : `shell-ready` 320 à 342 ms, `first-contentful-paint` 80 à 104 ms. Le test échoue.

**Cause** (onglet ressources `performance`) : le temps n'est pas dans le nombre de feuilles de style (35 feuilles terminées en 60 ms) ni dans l'API, mais dans une cascade de découvertes de modules, chaque saut coûtant 45 à 50 ms :

1. modules listés par `index.html` (`main.js`, `core/*`) : fin vers 77 ms ;
2. quatorze `GET /static/i18n/fr/<écran>.json`, lancés seulement à l'exécution de `main.js` (97 ms) ;
3. `import("./components/index.js")` n'a lieu qu'après les textes : quinze composants découverts à 118 ms ;
4. leurs propres imports (`model-card-*`, `chart-*`, `markdown.js`, `shell-ready.js`) à 170, 222, 225 ms ;
5. enfin `screens/home-demo.js` et `home-references.js`, imports de l'écran d'accueil, à 279 ms, fin à 325 ms.

Chaque story livrée a ajouté des composants et des textes : la cascade s'est allongée de 100 ms depuis la 4.x.

**Correctif** (`web/routes_static.py`, `static/core/i18n.js`) :

- `GET /static/i18n/fr.json` : les textes en un seul document, assemblé au démarrage depuis `i18n/fr/*.json`, qui restent la source ; une clé de premier niveau en double lève une erreur au démarrage (le test `test_static_split.py` garde le même contrôle). `loadTexts` le lit d'abord, et se replie sur les fichiers de `TEXT_FILES` si le document manque (fixtures E2E, serveur ancien).
- `GET /` sert `index.html` enrichi à la volée (assemblé une fois au démarrage, le fichier n'est pas modifié) : `preload` du document de textes et `modulepreload` de tout le graphe des imports (statiques, plus les `import()` littéraux de `main.js`) à partir de `main.js` et des modules déjà listés. Les écrans chargés à la demande par le routeur ne sont pas préchargés. Une story qui ajoute un composant ou un import n'a rien à déclarer.
- Aucun outil de build, aucune dépendance ; seul `web/` change côté Python (couches respectées) ; rien de `/api/` avant `shell-ready` (AD-6 amendé).

**Mesure après** : `shell-ready` 143 ms (une sonde), `first-contentful-paint` inchangé ; le test passe 5 fois de suite. Toutes les requêtes de modules partent dès le HTML ; il ne reste que `fr.json`, `main.js`, `home.js` et ses deux imports sur le chemin de rendu.

**Sur master** : le correctif est générique (aucune liste d'écrans ni de feuilles) ; sur master il aurait moins de modules à précharger et le gain serait moindre, mais le code est identique. Les tests ajoutés utilisent le dossier `static/` réel (`wl-badge.js` et `screens/chat.js`, présents sur master).

## Tests

`tests/v2/web/test_static.py` : document de textes (contenu, en-têtes), clé en double, parcours du graphe (statique, `import()` de `main.js` seul), préchargement dans `GET /` sans écran à la demande ni doublon.
