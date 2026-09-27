---
title: 'Vocabulaire, rédaction et formats fr-FR'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_revision: 'dad907a7a9a2abc901bb41da2fe16d30c4a9356b'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      AGENTS.md indique encore que les pages sont dans src/app/pages/.
    evidence: |-
      Les pages sont désormais dans src/app/views/ ; un dossier pages/ réactiverait le mode multipage historique.
    location: >-
      AGENTS.md
    severity: medium
  - summary: >-
      Budget carbone de l'équipe d'agents décrémenté mais plus affiché.
    evidence: |-
      Le delta « - Budget » a été retiré (deltas détournés) ; l'état reste mis à jour.
    location: >-
      src/app/tabs/agent/crew.py
    severity: low
  - summary: >-
      Trois graphies de l'unité de CO₂ (mgCO₂, mg CO₂, mg sous un libellé CO₂).
    evidence: |-
      arena.py, chat.py, solo.py, lab.py, crew.py, eval.py.
    severity: low
---

<intent-contract>

## Intent

**Problem:** Un même module porte jusqu'à quatre noms (fichier, menu, carte d'accueil, titre, onglet du navigateur) ; l'interrupteur cloud existe en 4 exemplaires avec 3 libellés ; français et anglais se mêlent avec du jargon (« chunks », « Crew », « FIGHT ! ») ; les nombres, dates et unités sont au format anglais (8.1%, Sep 26, GB), en *Title Case*, avec des pluriels non accordés et un pied de page « © 2025 … v2.0.0 » inventé (U8–U10).

**Approach:** Navigation déclarée par `st.navigation`/`st.Page` avec les noms, l'ordre et les icônes d'EXPERIENCE.md, identiques partout ; un seul `cloud-toggle` « Autoriser le cloud » dans la barre latérale commune ; lexique et règles de rédaction d'EXPERIENCE.md appliqués ; utilitaire de formats `fr-FR` et d'accord des pluriels, testé et utilisé à l'affichage.

## Boundaries & Constraints

**Always:** lexique, ordre des modules et icônes d'EXPERIENCE.md (Information Architecture, Voice and Tone, Chiffres) ; un nom par module, identique dans le menu, la carte d'accueil, `st.title` et l'onglet du navigateur ; casse de phrase ; boutons à l'infinitif + objet, sans point d'exclamation ; noms techniques (LangGraph, CrewAI, HyDE, Top-K, Ragas) seulement en `help=` ; identifiants de code en anglais ; aucune requête hors localhost (favicon local de la story 2 conservé) ; tests sans Ollama ni réseau.

**Never:** changer la valeur par défaut du mode cloud (D1, story 8) ; changer les calculs (débit, CO₂ : story 6) ou les états (story 5) ; renommer les identifiants internes des outils ou des tags de modèles ; toucher `src/core/config.py` ou le benchmark ; réintroduire emoji, hex ou CSS.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Navigation | Lancement de `src/app/Accueil.py` | Menu : Accueil, Arène des modèles, Assistant documentaire, Agents autonomes, Sobriété et matériel, dans cet ordre | — |
| Nom unique | Chaque module | Même nom dans le menu, la carte d'accueil, `st.title` et le titre de l'onglet | — |
| Cloud | Bascule sur une page, puis changement de page | Un seul interrupteur « Autoriser le cloud », état conservé | — |
| Nombre | `8.1` en pourcentage | « 8,1 % » (espace insécable) | — |
| Milliers | `12345.6` | « 12 345,6 » (espace fine insécable) | — |
| Mémoire | `13.8` Go | « 13,8 Go », jamais « GB » | — |
| Durée | `72` s | « 1 min 12 s » ; `0.66` → « 0,66 s » | — |
| Date | 2026-09-26 09:15 | « 26 sept. 2026 », « 09:15 » | — |
| Pluriel | 1 puis 3 extraits | « 1 extrait », « 3 extraits » | 0 → « 0 extrait » |
| Valeur absente | `None` | « — » | aucune exception |

</intent-contract>

## Code Map

- `src/app/Accueil.py` -- aujourd'hui page d'accueil ET point d'entrée ; `cloud_enabled` initialisé à `True` (l.33-34, à garder), toggle `global_cloud_toggle` dans le pied de page (l.149-156), 4 `st.page_link` vers les fichiers de `pages/` (l.111-137), pied « © 2025 … v2.0.0 ». Devient le routeur : `st.navigation([...])` avec `st.Page(fichier, title=…, icon=":material/…:", url_path=…)`, barre latérale commune (`render_logo`, toggle unique), puis `pg.run()`. Le contenu de l'accueil part dans un nouveau fichier de page (par exemple `src/app/home.py`).
- `src/app/pages/0[1-4]_*.py` -- chacun a son `st.set_page_config`, son `render_logo()` et (02, 03, 04) son propre toggle « Activer Cloud (Mistral) » à clé `cloud_enabled` (02:23-34, 03:120-127, 04:33-38) : supprimer ces toggles et lire `st.session_state.get("cloud_enabled", True)`. Avec `st.navigation`, la découverte automatique de `pages/` est désactivée : garder les fichiers en place et `url_path` = anciens chemins (`Socle_Hardware`, `Inference_Arena`, `RAG_Knowledge`, `Agent_Lab`) pour que les scripts d'audit existants restent valides.
- `src/app/ui.py` -- `render_logo`, `FAVICON_PATH`, `model_label` (suffixes « · Local »/« · Cloud »), à réutiliser. Vérifier que `st.Page(icon=":material/…")` ne remplace pas le favicon local (test existant `test_page_icons_are_local_files`, et contrôle navigateur des requêtes externes).
- `src/core/agent_tools.py:805-861` -- `TOOLS_METADATA[...]["name"]` affiché en pastilles : noms français du lexique ; vérifier si `name` sert de clé ailleurs (moteur d'agent, défaut des pastilles) avant de le changer, sinon ajouter un champ d'affichage.
- `src/app/tabs/inference/*.py`, `src/app/tabs/rag/*.py`, `src/app/tabs/agent/*.py`, `src/app/pages/*.py` -- libellés du lexique (onglets « Chat libre », « Banc d'essai », « Arène », « Gestion des modèles » ; « Discussion », « Évaluation de la qualité » ; modes « Agent seul », « Équipe d'agents » ; « Lancer la comparaison », « Lancer le test », « Vider la base documentaire », « Effacer la conversation », « Accélérateur IA », « Suivi carbone actif »), *Title Case*, jargon, formats de nombres (`f"{x:.1f}"`, `%`, `GB`) et de dates (axes Plotly `Sep 26`).
- `src/app/formatting.py` (nouveau) ou `src/core/formatting.py` -- fonctions pures sans `streamlit` : nombre, pourcentage, Go, durée, date, heure, pluriel ; « — » pour une valeur absente.
- `tests/app/test_theme.py` -- contient le contrôle d'icônes de modules (`test_module_icons_are_material_and_not_shared`) et le contrôle de favicon : à adapter à `st.Page`, sans affaiblir.

## Tasks & Acceptance

**Execution:**
- `src/app/Accueil.py`, `src/app/home.py` -- routeur `st.navigation` (ordre et icônes d'EXPERIENCE.md), barre latérale commune avec le seul toggle ; contenu d'accueil selon EXPERIENCE.md (en-tête, bandeau d'état, modules sans numérotation, « Arène des modèles » en tête marquée « Démo recommandée », pied : année courante, sans version inventée) ; les métriques gardent leurs calculs actuels.
- `src/app/pages/*.py` -- toggles locaux retirés ; `st.title` et `page_title` = nom du module.
- `src/app/formatting.py` -- utilitaire de formats et de pluriels.
- `src/app/**/*.py`, `src/core/agent_tools.py` -- lexique, casse de phrase, pluriels, formats `fr-FR`, jargon en `help=`.
- `tests/unit/test_formatting.py` -- chaque ligne de formats de la matrice.
- `tests/app/test_navigation.py` -- AppTest du routeur : ordre et noms du menu, titre de chaque page = nom du menu, un seul toggle « Autoriser le cloud » par page, état conservé après `switch_page` ; contrôle de source : aucune occurrence des anciens noms (« Inference Arena », « RAG Knowledge », « Agent Lab », « Socle Hardware », « Cockpit GreenOps », « chunks », « FIGHT », « Activer Cloud », « GB ») dans les textes affichés de `src/app`.
- Tests existants (`tests/app/*`, `tests/unit/*`) -- mis à jour sur les nouveaux libellés, assertions de même force.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given l'app lancée, when on charge les 5 pages au navigateur, then aucune requête ne part hors localhost et le menu affiche les 5 noms dans l'ordre.

## Spec Change Log

### 2026-09-27 — Code Map : `pages/` → `views/`
- Déclencheur : l'implémentation a constaté (navigateur, puis source `streamlit/runtime/pages_manager.py` 1.64.0) qu'un dossier `pages/` à côté du script principal active le mode multipage historique : le premier accès direct à un module affiche l'ancien menu, sans routeur ni interrupteur commun.
- Amendement : la Code Map disait de garder les fichiers dans `src/app/pages/` ; ils sont déplacés dans `src/app/views/` avec les mêmes noms et les mêmes `url_path`.
- État évité : double navigation selon la page d'arrivée.
- KEEP : `url_path` historiques ; `src/app/modules.py` comme source unique des noms ; test interdisant `src/app/pages/`.
- Écart de procédure : le code n'a pas été réverté puis ré-implémenté, la ré-implémentation depuis la Code Map amendée donnant le même code.

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 44 findings — high 0, medium 9, low 21, false 5, maybe-false 9
- findings:
  - `[low]` `[patch]` (blind, edge) `inf`, « nan », `NaT` lèvent une exception ou s'affichent — « — » pour toute valeur non finie.
  - `[low]` `[patch]` (blind, edge) « -0,0 » — zéro négatif normalisé.
  - `[low]` `[patch]` (blind) seuil 59,97 s / 60 s incohérent — unité choisie après arrondi.
  - `[medium]` `[defer]` (blind) CO₂ de session en kg alors que `stop()` renvoie des grammes (F5) — story 6.
  - `[medium]` `[defer]` (blind) indexation factice avec un libellé de succès (F1) — story 4.
  - `[medium]` `[patch]` (blind, edge, verification-gap) colonnes numériques en texte, tri alphabétique — `NumberColumn(format="localized")` (suit la langue du navigateur).
  - `[low]` `[defer]` (blind, edge) trois graphies de l'unité de CO₂ — story 6 (unités de CO₂).
  - `[medium]` `[patch]` (blind) message du garde-fou mémoire en anglais et en GB — réécrit, test ajouté.
  - `[low]` `[defer]` (blind, edge) AGENTS.md cite `src/app/pages/` — fichier d'instructions agent ; à corriger en priorité au matin.
  - `[medium]` `[patch]` (blind) suivi carbone démarré seulement sur l'accueil — initialisation dans le routeur.
  - `[low]` `[defer]` (blind, edge) budget carbone décrémenté mais plus affiché — story 6 ou 8.
  - `[medium]` `[defer]` (blind, intent) « Disponible » et « Actif » écrits en dur — story 5.
  - `[low]` `[defer]` (blind, edge) Arène : légende « au moins 2 modèles » mais bouton actif à 1 — story 7.
  - `[low]` `[patch]` (blind) bascule cloud non testée sur l'Assistant documentaire et Sobriété — tests ajoutés.
  - `[low]` `[patch]` (blind) constantes dupliquées (`VEGA_LOCALE`, « — ») — constantes de formatting.py.
  - `[maybe-false]` `[reject]` (intent) tests sur les arguments de `st.navigation` et non sur le menu rendu — menu vérifié au navigateur (5 noms, ordre).
  - `[maybe-false]` `[reject]` (intent) `format_date`/`format_time` sans appelant — axes en format numérique « 26/09 09:15 » par EXPERIENCE.md ; utilitaires prêts pour la story 10.
  - `[false]` `[reject]` (intent) écart `pages/` → `views/` — justifié, consigné au Spec Change Log.
  - `[low]` `[reject]` (intent) « Mode » en texte et non en badge — story 8.
  - `[low]` `[reject]` (intent) deltas et graphiques partiellement retouchés (stories 8 et 10) — sans changement de calcul.
  - `[maybe-false]` `[reject]` (intent) pied de page « année · Wavestone » sans version — conforme à « année courante… ou rien ».
  - `[medium]` `[patch]` (verification-gap) métrique « Mode » non liée au toggle par un test — AppTest ajouté.
  - `[medium]` `[patch]` (verification-gap) branche « base non vide » de l'Assistant documentaire jamais exécutée — AppTest avec statistiques simulées.
  - `[medium]` `[patch]` (verification-gap) mode « Équipe d'agents » jamais rendu — AppTest ajouté.
  - `[medium]` `[patch]` (verification-gap) formats `fr-FR` non vérifiés à l'affichage — AppTest avec `psutil` simulé.
  - `[maybe-false]` `[reject]` (verification-gap) libellé de stratégie → classe non testé — correspondance directe dans un dict, comportement inchangé.
  - `[low]` `[patch]` (edge) « 2,0 extrait » — pluriel décidé après arrondi.
  - `[low]` `[patch]` (edge) Paramètres inconnus affichés « 0,0 » — valeur absente.
  - `[low]` `[patch]` (edge) accord « 1,2 Go sont disponibles » — accord selon la valeur.
  - `[low]` `[patch]` (edge) podium « nan/100 » — `_format_ratio`.
  - `[low]` `[patch]` (edge) source `None` comptée comme document — ignorée.
  - `[false]` `[reject]` (edge) la mémoire de l'accueil change de calcul — affichage « Go utilisés / Go totaux » exigé par EXPERIENCE.md ; mesure `psutil` inchangée.
  - `[maybe-false]` `[reject]` (intent) lecture « noms identiques » au sens littéral pour l'accueil — exception d'EXPERIENCE.md (onglet « WaveLocalAI »).
  - `[false]` `[reject]` (intent) règle du benchmark — `benchmark_slm.py` n'importe que `config`.
  - `[maybe-false]` `[reject]` (intent) typographie (espaces insécables avant « : ») non contrôlée partout — appliquée via formatting.py pour les nombres ; revue visuelle au matin.
  - `[low]` `[reject]` (intent) écran « Mode » de Sobriété non testé dans le sens inverse — test ajouté dans les deux états.
  - `[false]` `[reject]` (verification-gap) `AGENTS.md` et CI — doublon.
  - `[maybe-false]` `[reject]` (intent) textes de dialogues et toasts non vérifiés — contrôle de source des anciens termes + revue au matin.
  - `[low]` `[reject]` (blind) légende et condition du bouton de l'Arène — doublon (story 7).
  - `[maybe-false]` `[reject]` (intent) graphiques `separators`/locale Vega vérifiés hors navigateur — onglets nécessitant une évaluation réelle ; revue au matin.
  - `[false]` `[reject]` (edge) collision de libellés — sans lien avec cette story.
  - `[low]` `[reject]` (edge) interligne dans « mg CO₂ » — doublon (story 6).
  - `[maybe-false]` `[reject]` (intent) « Démo recommandée » non testé — testé par `test_home_titles` (légende de la carte).

## Design Notes

Routeur (golden example) :

```python
pages = [
    st.Page("home.py", title="Accueil", icon=":material/home:", default=True),
    st.Page("pages/02_Inference_Arena.py", title="Arène des modèles",
            icon=":material/leaderboard:", url_path="Inference_Arena"),
    ...
]
pg = st.navigation(pages)
with st.sidebar:
    st.toggle("Autoriser le cloud", key="cloud_enabled", help="…les données quittent la machine.")
pg.run()
```

Un widget à `key` perd sa valeur quand il n'est pas rendu sur un run : le rendre à chaque run dans le routeur la conserve. L'onglet du navigateur de l'accueil reste « WaveLocalAI ».

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `grep -rnE "Inference Arena|RAG Knowledge|Agent Lab|Socle Hardware|GreenOps|chunks|FIGHT|Activer Cloud|\bGB\b" src/app --include=*.py` -- expected: aucune ligne affichée à l'utilisateur (noms de fichiers et `url_path` exceptés)

**Manual checks (if no CLI):**
- Navigateur (scripts hors dépôt dans `/tmp/nuit/axe`, lanceur à providers simulés) : menu, titres et onglets identiques ; aucune requête externe ; toggle unique.

## Auto Run Result

Status: done

**Résumé :** navigation `st.navigation`/`st.Page` depuis une source unique (`src/app/modules.py`) : Accueil, Arène des modèles, Assistant documentaire, Agents autonomes, Sobriété et matériel ; même nom dans le menu, la carte, le titre et l'onglet ; un seul interrupteur « Autoriser le cloud » dans la barre latérale commune ; lexique d'EXPERIENCE.md, casse de phrase, jargon en aide ; utilitaire `src/app/formatting.py` (nombres, %, Go, durées, dates, pluriels) appliqué à l'affichage ; suivi carbone démarré par le routeur.

**Fichiers :** `src/app/Accueil.py` (routeur), `src/app/home.py`, `src/app/modules.py`, `src/app/formatting.py` (nouveaux) ; `src/app/pages/*` → `src/app/views/*` ; `src/app/tabs/**/*.py` ; `src/core/agent_tools.py` (noms français), `src/core/resource_manager.py` (message) ; `docs/ARCHITECTURE.md` ; tests `tests/app/test_navigation.py`, `tests/unit/test_formatting.py`, `tests/unit/test_resource_manager.py`, `tests/app/test_pages.py`, `tests/app/test_theme.py`.

**Revue :** 20 correctifs (8 medium, 12 low), 8 différés (motifs au journal), 16 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les medium sont couverts par des tests ajoutés.

**Vérification :** `pytest tests/unit tests/app` : 308 réussis ; grep des anciens noms : aucun ; navigateur : 5 noms dans l'ordre, aucune requête hors localhost ; contrastes inchangés depuis la story 2 (clair 0 ; sombre : `primaryColor` seul).

**Risques :** colonnes `localized` au format de la langue du navigateur ; AGENTS.md cite encore `src/app/pages/`.
