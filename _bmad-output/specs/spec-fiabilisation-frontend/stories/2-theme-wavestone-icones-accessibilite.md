---
title: 'Thème Wavestone, icônes et accessibilité'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_revision: '8dfc946c24e2969d56023b13714421b4ac8a07fa'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
warnings: []
deferred:
  - summary: >-
      Pastilles d'outils de l'équipe d'agents sans wrap dans une colonne 1/3.
    evidence: |-
      crew.py : st.pills directement dans une colonne ; Streamlit 1.64 les garde alors sur une ligne défilante.
    location: >-
      src/app/tabs/agent/crew.py:322
    severity: medium
  - summary: >-
      Matrice de l'Arène sans contour ni légende ; Graphviz de l'équipe sur fond blanc en thème sombre.
    evidence: |-
      Couleurs en dur retirées ; distinction restante : forme étoile du vainqueur.
    location: >-
      src/app/tabs/inference/arena.py ; src/app/tabs/agent/crew.py
    severity: low
  - summary: >-
      AGENTS.md ne mentionne pas tests/app dans les commandes de test.
    evidence: |-
      « Running and verifying » ne cite que tests/unit.
    location: >-
      AGENTS.md
    severity: low
  - summary: >-
      Boutons texte dans des colonnes étroites (chat, agent seul, RAG) à contrôler visuellement.
    evidence: |-
      Non observé au navigateur avec des réponses réelles.
    severity: low (unverified)
  - summary: >-
      Agent Lab sans modèle : KeyError None (préexistant).
    evidence: |-
      solo.py : display_to_tag[None] quand la liste est vide.
    location: >-
      src/app/tabs/agent/solo.py:92
    severity: medium
  - summary: >-
      st.image reçoit tout le message de l'outil au lieu du chemin de l'image (préexistant).
    evidence: |-
      solo.py passe content.strip() ; generate_chart renvoie « Graphique créé : <chemin> ».
    location: >-
      src/app/tabs/agent/solo.py:277
    severity: low
  - summary: >-
      Filtre de capacités désélectionné (None) masque les modèles cloud (préexistant).
    evidence: |-
      selection != FILTER_ALL vaut True pour None.
    location: >-
      src/app/tabs/inference/manager.py:185
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le front a l'allure « prototype Streamlit » : thème par défaut (action principale rouge), barre « Deploy », emojis en guise d'icônes (doublés, en titre, en `<h1>`), CSS et couleurs hex injectés (encart « base vide » `#262730` illisible en clair, badges CO₂ colorés par seuil), boutons à icône seule sans nom, 5 outils de l'agent sur 9 invisibles à 1440 px, 26 `use_container_width` dépréciés (U1–U7, U18, F14).

**Approach:** Appliquer DESIGN.md par `.streamlit/config.toml` et composants natifs uniquement : thème clair et sombre, police locale, `st.logo`, icônes `:material/…:`, aucun hex ni `<style>` dans `src/app`, boutons nommés, pastilles d'outils repliées, `width=` à la place de `use_container_width`.

## Boundaries & Constraints

**Always:** DESIGN.md prime (tokens, composants, Do's and Don'ts) ; chaque clé de thème existe dans Streamlit 1.64.0 (`streamlit/config.py`) ; une seule icône Material par module, jamais partagée ; seule exception emoji : l'accueil « Bonjour ! » de l'agent ; un h1 par page (`st.title`), puis h2/h3 sans saut ; tout bouton a un libellé texte ; comportements inchangés hors rendu ; tests sans Ollama ni réseau.

**Never:** CSS injecté, `<style>`, `unsafe_allow_html` pour colorer ou titrer ; corriger par CSS un contraste dû à une couleur native sans clé de thème (légendes, `st.badge`) — le mesurer et le noter ; fichier Aptos versionné ou CDN ; renommer les modules, onglets ou libellés (story 3), changer l'état « Système » (story 5), ajouter les badges Local/Cloud (story 8), refaire les graphiques (story 10) ; toucher `src/core/config.py` ou le benchmark.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Thème clair | Démarrage, préférence claire | Action principale `#451DC7`, fond blanc, police Aptos/Inter | — |
| Thème sombre | Préférence sombre | Tokens `*-dark` de DESIGN.md | — |
| Titres | Les 5 pages | Un `st.title` sans emoji ; aucun `<h1>`–`<h6>` HTML ni titre markdown hors hiérarchie | — |
| Outils de l'agent | Agent seul, 1440 px | Les 9 pastilles visibles (repliées sur plusieurs lignes) | — |
| Bouton icône seule | Effacer, rafraîchir, télécharger | Libellé texte présent | — |
| Code source | `src/app/**/*.py` | Ni `use_container_width`, ni hex, ni `<style>`, ni emoji (sauf « 👋 Bonjour ! ») | — |

</intent-contract>

## Code Map

- `.streamlit/config.toml` -- créé en story 1 (`[server]`, `[browser]`). Ajouter `[client] toolbarMode = "viewer"`, `[server] enableStaticServing = true`, `[theme]` (`baseRadius = "12px"`, `font`/`headingFont = "Aptos, Inter, sans-serif"`, `[[theme.fontFaces]]` Inter), `[theme.light]` et `[theme.dark]` (primaryColor, backgroundColor, secondaryBackgroundColor, textColor, borderColor, linkColor, chartCategoricalColors) selon le tableau Colors de DESIGN.md. Clair par défaut : vérifier dans la source 1.64 comment le thème initial est choisi quand les deux sections existent. Options vérifiées présentes dans `streamlit/config.py` 1.64.0 : `font` (liste de repli acceptée), `fontFaces` (URL `app/static/…`), `baseRadius`, `chartCategoricalColors`, sections `theme.light`/`theme.dark`, `client.toolbarMode`, `server.enableStaticServing` (dossier `static` à côté du script principal, donc `src/app/static/`). Les légendes (`st.caption`) n'ont pas de clé native dans 1.64 (`grayTextColor` ne vise que la palette `:gray[]`) : couleur native, mesurée.
- `src/app/static/fonts/` (nouveau) -- `InterVariable.woff2`, `InterVariable-Italic.woff2` et `LICENSE.txt` (OFL 1.1) à copier depuis `/tmp/nuit/inter/web/` et `/tmp/nuit/inter/LICENSE.txt` (release officielle rsms/inter v4.1, déjà téléchargée).
- `src/app/static/wordmark.svg` (nouveau) -- wordmark texte « WaveLocalAI » pour `st.logo`, appelé sur chaque page.
- `src/app/Accueil.py` -- `page_icon="🌊"`, titre emoji, 4 `st.markdown("# 🔋")` (faux h1), `page_link` à emoji, métriques à emoji, `st.markdown("---")`.
- `src/app/pages/0[1-4]_*.py` -- `page_icon` et titres à emoji ; page 02 : `<style>` (l.16-24) ; page 03 : `<style>` et encart vide HTML `#262730`/`#cccccc` (l.32-48, 212-221) à remplacer par `st.container(border=True)`, bouton « 📂 » doublé par `icon="📂"` (l.150), deux boutons `primary` visibles sur l'état vide ; page 04 : `ram_color` inutilisé, `col_status` inutilisé.
- `src/app/tabs/inference/chat.py:57-72,110,119-127` -- badges CO₂ HTML colorés par seuil → `st.caption` texte ; bouton « 🗑️ » icône seule ; titre HTML `<h3>`.
- `src/app/tabs/inference/arena.py:36-43,71,81,95,108,178` -- `<h2 style=color:#F59E0B>`, `:{color}[…]` par seuil, couleurs Plotly en dur, « ⚔️ FIGHT ! » (libellé : story 3 ; ici retirer l'emoji).
- `src/app/tabs/inference/manager.py:69-84,130,136-173,196-200` -- options et pastilles comparées par valeur à des chaînes à emoji : changer valeurs et comparaisons ensemble ; bouton « 🔄 » icône seule.
- `src/app/tabs/inference/lab.py`, `src/app/tabs/rag/chat.py`, `src/app/tabs/rag/eval.py` -- emojis dans libellés, statuts, métriques, médailles ; `"📥 MD"`.
- `src/app/tabs/agent/solo.py:91-127,142-150,176,190-212,232` -- pastilles d'outils dans une colonne 4/7 sans `wrap` (défilent sur une ligne) ; `status_state` teste `"✅" in msg["content"]` (l.176, contenu posé l.281) : remplacer par un champ explicite ; badge CO₂ HTML coloré ; bouton « 📥 » icône seule ; `check.message` déjà préfixé d'emojis par `resource_manager`.
- `src/app/tabs/agent/crew.py:148-182,267,272-366` -- préfixes de logs emoji, Graphviz avec couleurs en dur, `"📂 Ouvrir"` + `icon="📚"`, titres `#####` sans niveaux au-dessus, pastilles d'outils dans une colonne 1/3.
- `src/core/agent_tools.py:805-861` -- `TOOLS_METADATA` : noms affichés en pastilles avec emoji ; retirer l'emoji du nom affiché seulement (les noms français viennent en story 3).
- `src/core/resource_manager.py:149-160`, `src/core/models_db.py:74` -- emojis dans des messages affichés (« ⛔ », « 💡 », « 📦 ») ; non importés par le benchmark.
- `src/app/components/*` -- non importés par les pages : hors périmètre.

## Tasks & Acceptance

**Execution:**
- `.streamlit/config.toml` -- thème clair/sombre, police, rayon, palette, `toolbarMode`, service statique.
- `src/app/static/` -- polices Inter et licence, wordmark SVG.
- `src/app/Accueil.py`, `src/app/pages/*.py` -- `st.logo`, `page_icon` Material (icônes d'EXPERIENCE.md : `home`, `eco`, `leaderboard`, `description`, `smart_toy`), titres sans emoji, suppression des `<style>`, encart vide en `card` natif, faux h1 retirés, un seul bouton `primary` par vue.
- `src/app/tabs/**/*.py` -- emojis → `icon=":material/…:"` ou rien ; HTML coloré → composants natifs ; titres markdown remis en hiérarchie h2/h3 ; boutons à icône seule nommés ; `use_container_width=True` → `width="stretch"` ; pastilles d'outils avec `wrap=True` ; `status_state` sans test d'emoji ; marqueurs de modèle ☁️/💻/✅/⚠️ remplacés par un suffixe texte (« · Local », « · Cloud ») sans changer les tags sous-jacents ; couleurs Plotly/Graphviz/Altair en dur retirées (le thème fournit la palette).
- `src/core/agent_tools.py`, `src/core/resource_manager.py`, `src/core/models_db.py` -- emojis retirés des textes affichés ; tests existants mis à jour sur la cible, pas sur l'assertion.
- `tests/app/test_theme.py` -- config : clés de thème et valeurs de DESIGN.md, `toolbarMode`, polices présentes ; source : aucun `use_container_width`, hex, `<style>`, `unsafe_allow_html` servant à colorer ou titrer, emoji dans `src/app` (exception « 👋 Bonjour ! ») ni dans les noms de `TOOLS_METADATA` ; AppTest : titres des 5 pages sans emoji, 9 options dans les pastilles de l'agent seul.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given l'app lancée, when on mesure axe-core `color-contrast` et `heading-order` sur les 5 pages en clair puis en sombre, then les violations restantes sont toutes dues à des couleurs natives sans clé de thème, et chacune est listée avec son ratio dans l'Auto Run Result.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 38 findings — high 0, medium 7, low 20, false 6, maybe-false 5
- findings:
  - `[medium]` `[patch]` (orchestrateur) `page_icon=":material/…"` télécharge le favicon depuis fonts.gstatic.com — favicon SVG local ; 0 requête externe mesurée ensuite.
  - `[maybe-false]` `[reject]` (intent) contraste mesuré hors diff — mesure consignée dans l'Auto Run Result.
  - `[medium]` `[defer]` (intent) pastilles d'outils de l'équipe d'agents sans `wrap` dans une colonne 1/3 — hors critère « 9 outils de l'agent seul » ; à vérifier au matin.
  - `[low]` `[reject]` (intent) ordre des titres non testé automatiquement — mesuré à l'axe : 0 violation `heading-order`.
  - `[low]` `[reject]` (intent) noms de boutons non testés — mesuré à l'axe, aucun bouton sans nom ; libellés texte présents.
  - `[low]` `[reject]` (intent) démarrage sans avertissement vérifié hors test — vérifié (0 avertissement).
  - `[low]` `[reject]` (intent) accueil en grille, pas en colonne — refonte de mise en page exclue par SPEC (non-goals).
  - `[medium]` `[patch]` (intent, blind) marqueur « outils vérifiés » perdu dans l'Agent Lab — suffixe « · outils vérifiés ».
  - `[medium]` `[patch]` (verification-gap) `model_options`/`model_label` non testés — tests/unit/test_ui.py.
  - `[medium]` `[patch]` (verification-gap) tri de l'Agent Lab non testé — AppTest de l'ordre des options.
  - `[medium]` `[patch]` (verification-gap) drapeau `done` non testé — AppTest des états ; a révélé que `with st.status(...)` forçait `complete` (corrigé).
  - `[false]` `[reject]` (blind) emoji dans « 👋 Bonjour ! » — exception explicite de DESIGN.md et de la spec ; à valider au matin (EXPERIENCE.md interdit l'emoji dans un titre).
  - `[medium]` `[patch]` (blind, edge) emojis encore renvoyés par agent_tools.py et les providers — retirés, test étendu.
  - `[low]` `[patch]` (blind) unité CO₂ perdue (arena, lab) — `mgCO₂`.
  - `[low]` `[reject]` (blind) `chart-4` `#C98A00` à 2,95:1 — valeur et règle d'étiquetage fixées par DESIGN.md.
  - `[low]` `[defer]` (blind) matrice de l'Arène sans contour ni distinction du vainqueur — story 10.
  - `[low]` `[patch]` (blind) wordmark étiré (`textLength`) avec une police de repli — attribut retiré ; contraste réel 3,58:1 sur `#0A0A14` et 3,23:1 sur la barre latérale `#16162A` (la note de conception disait ≈3,8:1).
  - `[low]` `[patch]` (blind, edge) `requirements.txt` `streamlit>=1.40.0` — `>=1.64.0`.
  - `[low]` `[reject]` (blind) import non protégé de `src.app.ui` avant le repli ImportError — le repli ne peut jouer que si `src` est absent, auquel cas la page elle-même n'existe pas.
  - `[low]` `[patch]` (blind) tests : regex de titres ligne à ligne, plages d'emoji — recherche sur le fichier entier, plages ajoutées.
  - `[low]` `[reject]` (blind) test lié à `_config_options_template` privé — seule source exhaustive des clés de la version installée.
  - `[low]` `[defer]` (blind) AGENTS.md ne cite pas tests/app — fichier d'instructions agent.
  - `[false]` `[reject]` (blind) polices et fichier de story non suivis — commités avec la story ; provenance (rsms/inter v4.1, OFL 1.1) dans le commit et `LICENSE.txt`.
  - `[maybe-false]` `[defer]` (blind) boutons texte dans des colonnes étroites (chat, solo, RAG) — à contrôler visuellement au matin.
  - `[low]` `[patch]` (blind) restes dans crew.py (commentaire périmé, espace avant « : ») — corrigés ; « Risqué » relève du lexique (story 3).
  - `[low]` `[defer]` (blind) Graphviz de l'équipe sur fond blanc en sombre — story 10 ou revue visuelle.
  - `[low]` `[patch]` (edge) onglet d'agent sans libellé si le rôle est vide — « Agent N ».
  - `[maybe-false]` `[reject]` (edge) collision de libellé `hf.co` sans préfixe — improbable ; les collisions de nom existaient déjà avec le préfixe.
  - `[maybe-false]` `[reject]` (edge) deux tags de même nom écrasent `display_to_tag` — préexistant (mêmes libellés avant).
  - `[false]` `[defer]` (edge) Agent Lab sans modèle : `KeyError` — préexistant, story 5.
  - `[low]` `[defer]` (edge) `st.image` reçoit tout le message de l'outil — préexistant (même code avant).
  - `[low]` `[defer]` (edge) pastille de filtre désélectionnée masque les modèles cloud — préexistant (même comparaison avant).
  - `[false]` `[reject]` (edge) contournement de l'ordre des icônes par la regex du test — test réécrit (icône unique par module).
  - `[low]` `[reject]` (edge) zones de texte plus en police à chasse fixe — conséquence voulue du retrait du CSS.
  - `[false]` `[reject]` (edge) `src/app/components` exclu des contrôles — code mort, exclu par la spec.
  - `[false]` `[reject]` (edge) plusieurs boutons `primary` sur la page Inférence — un par onglet, un onglet est une vue.
  - `[maybe-false]` `[reject]` (intent) « 390 px » d'U18 non traité — priorité basse d'EXPERIENCE.md, non exigée par la story.
  - `[low]` `[reject]` (intent) `greenTextColor` hors du tableau de DESIGN.md — clé native, pas de CSS ; noté comme choix à valider.

## Design Notes

Wordmark : DESIGN.md le veut en `{colors.ink}`, mais `st.logo` affiche une image unique pour les deux thèmes ; l'encre claire disparaîtrait en sombre. Choix de nuit : texte en `{colors.primary-dark}` `#6A4DE6` (5,5:1 sur blanc, ≈3,8:1 sur `#0A0A14`, suffisant pour du grand texte), à valider au matin. Le hex vit dans l'asset SVG, pas dans le code des pages.

Marqueur de modèle, exemple : `"Qwen 2.5 1.5B · Local"` au lieu de `"💻 Qwen 2.5 1.5B"` ; l'étiquette reste la clé de `display_to_tag`, donc construire la clé et la valeur ensemble.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `grep -rnE "use_container_width|unsafe_allow_html|<style|#[0-9A-Fa-f]{6}\b" src/app --include=*.py` -- expected: aucune ligne, sauf `unsafe_allow_html` justifié hors couleur et titre (à lister)
- `timeout 25 .venv-app/bin/python -m streamlit run src/app/Accueil.py --server.headless true` -- expected: démarrage sans avertissement de dépréciation ni d'option inconnue

**Manual checks (if no CLI):**
- Rendu navigateur (Playwright + axe-core hors dépôt, dans `/tmp`) des 5 pages en clair et en sombre : couleur primaire, police Inter chargée depuis `app/static`, logo visible, 9 pastilles d'outils à 1440 px ; contrastes mesurés.

## Auto Run Result

Status: done

**Résumé :** thème Wavestone clair et sombre par `.streamlit/config.toml` (couleurs, rayon, palette de graphiques, `toolbarMode = "viewer"`), police Inter servie localement, `st.logo` et favicon locaux, emojis remplacés par des icônes Material ou retirés (app et textes renvoyés par le cœur), CSS et hex retirés de `src/app`, encart « base vide » natif, titres en hiérarchie, boutons nommés, pastilles d'outils repliées, `width=` partout.

**Fichiers :** `.streamlit/config.toml` ; `src/app/static/` (polices Inter v4.1 + OFL, `wordmark.svg`, `favicon.svg`) ; `src/app/ui.py` (logo, favicon, libellés de modèles) ; `src/app/Accueil.py`, `src/app/pages/*.py`, `src/app/tabs/**/*.py` ; `src/core/agent_tools.py`, `resource_manager.py`, `models_db.py`, `llm_provider.py`, `providers/*.py` (emojis retirés des textes) ; `requirements.txt` (`streamlit>=1.64.0`) ; tests `tests/app/test_theme.py`, `tests/unit/test_ui.py`, `tests/unit/test_models_db.py`, `tests/unit/test_agent_tools.py`.

**Revue :** 17 correctifs (7 medium, 10 low), 9 différés, 12 rejetés (motifs au journal).

**Suivi recommandé :** false — aucun correctif high ; les medium corrigés sont couverts par des tests (libellés, tri, états) ou mesurés (requêtes externes).

**Vérification :** `pytest tests/unit tests/app` : 191 réussis ; grep : plus aucun `use_container_width`, hex, `<style>` ni `unsafe_allow_html` hors `components/` (code mort) ; démarrage sans avertissement ; navigateur (Playwright + axe-core, providers simulés, 1440 px) : aucune requête hors localhost, Inter chargée, fond `#FFFFFF` / `#0A0A14`.

**Contrastes mesurés (axe-core, `color-contrast` et `heading-order`) :**
- clair : 0 violation (avant : légendes 3,68:1, primaire `#ff4b4b` 3,30:1, deltas verts 4,03–4,49:1).
- sombre : 10 nœuds, tous dus à `primaryColor` `#6A4DE6` (valeur de DESIGN.md) employé comme couleur de texte par Streamlit : valeur du curseur 3,57:1 sur `#0A0A14`, pastilles sélectionnées 3,34:1 sur `#141129`. Clé de thème existante, mais valeur imposée : à trancher au matin (`#7A5FEA` : texte 4,36:1, blanc dessus 4,51:1 ; `#8468EC` : 4,85:1 et 4,06:1).
- `heading-order` : 0 violation en clair et en sombre (avant : 7).

**Risques :** `greenTextColor` clair `#0C6E3C` ajouté hors DESIGN.md ; wordmark `#6A4DE6` à 3,23:1 sur la barre latérale sombre ; RAG avec documents et écrans d'inférence réelle non vus au navigateur.
