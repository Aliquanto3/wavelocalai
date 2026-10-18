---
title: 'La coquille s''affiche tout de suite, aux couleurs de Wavestone'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '68de3ef'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-2.md'
warnings: []
deferred:
  - summary: >-
      La barre haute ne porte que les modules et le menu Affichage. La pastille Ollama, l'interrupteur « Autoriser le cloud », le CO₂ de session et la bannière « Connexion au serveur perdue » (UX-DR5) arrivent avec la story 1.9, qui lit `/api/health` et le flux système ; le conteneur `.topbar-tools` les attend.
    evidence: |-
      Critères de la story 1.8 : coquille sans appel `/api/` ; story 1.9 : « La barre haute dit l'état d'Ollama, du cloud et du CO₂ ».
    location: src/wavelocalai/web/static/index.html
    severity: low
  - summary: >-
      Le focus ne va pas sur le `h1` au premier chargement de la page, seulement aux changements de route : le premier Tab doit atteindre le lien d'évitement, puis la navigation. `document.title` et l'annonce polie, eux, sont posés dès le premier rendu.
    evidence: |-
      Critère « à chaque route » lu comme « à chaque changement d'écran » ; test `test_each_route_sets_title_focuses_the_h1_announces_and_is_fast`.
    location: src/wavelocalai/web/static/core/router.js
    severity: low
  - summary: >-
      Blanc sur `primary-dark` (#7E65E9) fait 4,26:1, sous le 4,5:1 d'AA (écart consigné par DESIGN.md). La coquille n'a aucun bouton plein : l'état actif de la navigation est un trait, le lien d'évitement est en `ink` sur `surface`. Les stories à boutons principaux devront traiter l'écart (axe les signalera en sombre).
    evidence: |-
      DESIGN.md, note `primary-dark` ; axe sans violation sur la coquille, clair et sombre.
    location: src/wavelocalai/web/static/tokens.css
    severity: medium
  - summary: >-
      La politique de contenu (`script-src 'self'`, `style-src 'self'`, `img-src 'self' data:`) interdit les styles et scripts en ligne et les `blob:`. Un écran qui télécharge un fichier généré (export JSON, Markdown) devra l'élargir (`blob:`) dans `routes_static.py`, avec son test.
    evidence: |-
      `tests/v2/web/test_static.py::test_page_and_files_forbid_any_resource_outside_the_origin`.
    location: src/wavelocalai/web/routes_static.py
    severity: low
  - summary: >-
      `pyyaml` (lu par le test de dérive des jetons) n'est pas déclaré au `pyproject` : il vient de LangChain. À déclarer dans le groupe de test si LangChain quitte les dépendances.
    evidence: |-
      `tests/v2/unit/test_shell_static.py` (`import yaml`).
    location: pyproject.toml
    severity: low
---

# Story 1.8 : la coquille s'affiche tout de suite, aux couleurs de Wavestone

## Objectif

`http://127.0.0.1:8502/` rend en moins de 300 ms, Ollama arrêté et sans aucun appel `/api/`, une coquille française accessible : barre haute avec les six modules (Accueil seul actif, les cinq autres visibles, désactivés, avec leur raison), routeur par `hash`, thème clair par défaut aux jetons de `DESIGN.md`, thème sombre et mode projection mémorisés. Modules JS natifs, aucune compilation, aucune requête hors de `127.0.0.1`.

## Critères d'acceptation et preuves

1. **Fichiers et service.** `web/static/` : `index.html`, `tokens.css`, `base.css`, `components.css`, `icons.svg`, `fonts/` (Inter, droite et italique, `LICENSE.txt` OFL), `i18n/fr.json`, `core/{router,i18n,theme}.js` (plus `registry.js`, `shell.js`), `main.js`, `screens/home.js`, `vendor/` (vide, règle dans son `README.md`). `GET /` rend `index.html`, `/static/` sert le reste (`web/routes_static.py`, appelé par `create_app`). Types fixés (`.js` en `text/javascript` : le registre Windows le donne parfois en `text/plain`), `Cache-Control: no-cache` (revalidation par ETag, 304), `nosniff`, et une politique de contenu `default-src 'self'` : le navigateur lui-même refuse toute ressource externe. Preuve : `tests/v2/web/test_static.py` (15 cas : types, 304, en-têtes, tout fichier servi, 404 en enveloppe, traversée de chemin, Host étranger refusé), `test_read_budget.py` (la route `/` entre dans le budget de 300 ms).
2. **Coquille en moins de 300 ms, sans `/api/`, Ollama arrêté.** `lang="fr"`, `header`/`nav`/`main`/`footer`, lien « Aller au contenu » (premier arrêt de Tab, focus sur `main`, sans changer de route). Le serveur E2E pointe Ollama sur un port fermé. Preuve : `tests/v2/e2e/test_shell.py` : médiane de cinq chargements après un chauffage, premier rendu (FCP) et repère `shell-ready` sous 300 ms (mesuré 40 à 80 ms), aucune requête dont l'URL contient `/api/`.
3. **Aucune requête hors de `127.0.0.1`.** Le contexte E2E abort et relève toute URL qui n'est pas `http://127.0.0.1:…` (ni `data:`, `blob:`, `about:`), et vérifie en fin de test que la liste de toutes les requêtes ne contient que le serveur. Test statique : aucune URL `http(s)://` (hors espace de noms SVG), `@import`, Google Fonts ou CDN dans `static/`. Preuve : `test_every_request_stays_on_127_0_0_1`, `test_no_external_url_cdn_or_third_party_script_outside_vendor`.
4. **Registre d'écrans et barre haute.** `core/registry.js` : six modules, onze routes de UX-DR4, chaque écran `available` (a un `load`) ou `planned`. Un module `planned` est un `<a role="link">` sans `href`, `aria-disabled="true"`, `tabindex="0"`, relié par `aria-describedby` au texte visible « Pas encore disponible dans cette préversion » (clé `router.planned`). Une route `planned` ou inconnue tapée à la main renvoie à l'Accueil (`history.replaceState`, pas d'entrée d'historique en plus) avec une annonce de la raison. Preuve : `test_six_modules_planned_ones_are_disabled_focusable_links_with_a_visible_reason`, `test_planned_or_unknown_route_goes_back_to_home` (3 routes), `test_registry_declares_the_routes_of_the_contract_and_the_six_modules`.
5. **Routeur.** `mount(host, params)` rend `unmount`, écran chargé par `import()` à la première visite puis gardé (nœud masqué, non détruit), nouveau `mount` si le paramètre de chemin change. À chaque changement de route : `document.title` « <Écran> · WaveLocalAI », focus sur le `h1`, annonce polie « Écran <Écran> » (`role="status"`), moins de 150 ms. Preuve : `test_each_route_sets_title_focuses_the_h1_announces_and_is_fast` (écran de test branché sur le vrai registre : un seul `load` et un seul `mount` au retour, `unmount` puis `mount` avec `run_id`).
6. **Menu repliable.** Sous 1 024 px, les liens passent derrière un bouton « Menu » (`aria-expanded`, `aria-controls`), Échap le ferme et rend le focus. Preuve : `test_links_fold_into_a_menu_under_1024_px`.
7. **Jetons et dérive.** `tokens.css` reprend couleurs (clair et sombre), rayons et familles de police de `DESIGN.md` ; `test_tokens_css_mirrors_design_md` compare chaque valeur au front matter, et quatre cas (couleur, couleur sombre, rayon, police) plus un jeton manquant prouvent que le test échoue à la moindre différence. `base.css` et `components.css` n'ont aucune couleur en dur. Pas d'emoji dans `static/` (test, avec le détecteur lui-même vérifié).
8. **Menu Affichage.** Thème clair par défaut ; « Sombre » et « Mode projection » (rampe ×9/7, métriques agrandies, pied masqué) s'appliquent sans rechargement et se mémorisent dans `localStorage` (`wl.theme`, `wl.projection`), accès gardés par `try/catch` (stockage bloqué : le choix tient pour la page). `core/theme.js` est chargé en tête avec `blocking="render"` : pas d'éclair clair avant le sombre. Preuve : `test_dark_theme_applies_without_reload_and_is_remembered`, `test_projection_mode_scales_type_hides_the_footer_and_is_remembered`, `test_theme_still_applies_when_storage_is_blocked`, `test_display_menu_closes_with_escape_and_returns_the_focus`.
9. **Police.** Pile `Aptos, Inter, sans-serif` (Aptos appelée par son nom, Inter servie depuis `static/fonts/`, sans CDN). Preuve : `test_font_stack_is_aptos_then_local_inter_then_sans_serif`.
10. **Accessibilité.** axe-core (axe-playwright-python), zéro violation et aucune exclusion : coquille en clair et en sombre, avec le menu Affichage ouvert, menu replié ouvert à 320 px en clair et en sombre, mode projection. Pas de défilement horizontal à 320, 375, 768, 1 024 et 1 440 px (menus ouverts compris). Icônes : sprite `icons.svg` (Material Symbols Rounded, Apache 2.0, `icons.LICENSE.txt`), une icône propre par module. Preuve : `test_axe_finds_no_violation_*` (5 cas), `test_shell_has_no_horizontal_scroll` (5 largeurs), `test_each_module_has_its_own_icon_in_the_sprite`.
11. **Cohérence.** `tests/v2/unit/test_layers.py` et le budget de lecture restent verts ; aucun code de `src/core/`, `src/app/`, `scripts/` touché ; `errors.py` inchangé (aucun nouveau code) ; `controle_rapide.py` sans erreur.

## Fichiers

- `src/wavelocalai/web/routes_static.py` (nouveau), `web/app.py` (deux lignes : import et `mount_shell(app)`)
- `src/wavelocalai/web/static/` : `index.html`, `main.js`, `tokens.css`, `base.css`, `components.css`, `icons.svg`, `icons.LICENSE.txt`, `favicon.svg` (copie de la v1), `fonts/` (copie de la v1), `i18n/fr.json`, `core/{registry,router,shell,i18n,theme}.js`, `screens/home.js`, `vendor/README.md`
- `tests/v2/unit/test_shell_static.py` (21 cas), `tests/v2/web/test_static.py` (15 cas), `tests/v2/e2e/{conftest,test_shell}.py` (24 cas, marqueur `e2e` posé par le conftest)

## Choix notables

- Le sprite vient des glyphes de la police Material Symbols Rounded embarquée par Streamlit (contours extraits avec `fontTools`, hors dépendances du projet, remis en grille 960) : aucun téléchargement d'icône, 19 symboles.
- Le HTML garde le texte français et `data-i18n` le remplace par le catalogue ; un test compare les deux, donc le HTML ne dérive pas de `fr.json`. La navigation, elle, est tirée du registre par JS (`shell.js`).
- Le lien d'évitement ne change pas le `hash` : il est intercepté, sinon `#main` serait lu comme une route. Le routeur ignore tout `hash` qui ne commence pas par `#/`.
- Le serveur E2E écrit sa sortie dans un fichier : un tube non lu se remplit (journaux d'accès uvicorn) et fige le serveur. `wait_for_function` n'est pas utilisable (il évalue une chaîne, ce que la politique de contenu refuse) : les attentes passent par `page.evaluate` de fonctions.
- Navigateur : Edge via `WAVELOCALAI_E2E_CHROMIUM`, comme pour la v1 ; aucun téléchargement.

## Reports

Voir l'en-tête `deferred` : barre haute d'état (story 1.9), focus au premier chargement, écart de contraste de `primary-dark` pour les boutons pleins, politique de contenu et `blob:`, `pyyaml` non déclaré.
