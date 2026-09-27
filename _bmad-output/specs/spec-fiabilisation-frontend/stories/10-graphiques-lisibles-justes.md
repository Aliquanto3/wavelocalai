---
title: 'Graphiques lisibles et justes'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_revision: 'b4e4ac59fa5623740249e521f5002050a6a9d106'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      Noms de modèles tronqués dans le multiselect de l'Arène (U-06).
    evidence: |-
      Largeur des pastilles du composant natif ; aucun CSS autorisé.
    location: >-
      src/app/tabs/inference/arena.py
    severity: medium
  - summary: >-
      Barres très fines sur 30 jours ou « Tout » quand des sessions sont rapprochées.
    evidence: |-
      Largeur plafonnée à 80 % de l'écart ; valeurs lisibles dans le tableau. Regroupement par jour à décider.
    location: >-
      src/app/charts.py
    severity: medium (unverified)
  - summary: >-
      Plage de l'axe des dates de l'historique non vérifiée au niveau de la page.
    evidence: |-
      Vérifiée sur prepare_emissions_history seulement.
    severity: low
---

<intent-contract>

## Intent

**Problem:** L'historique d'émissions est une aire en kg (« 20µ ») qui relie par une droite des périodes sans mesure et prend les 50 dernières lignes au lieu d'une fenêtre de temps (U16). La matrice de l'Arène encode le CO₂ par la taille des points sans légende de taille, sans légende des séries, avec un axe du débit resserré (5,8 à 6 tokens/s) et des étiquettes qui sortent du cadre ; la matrice de l'évaluation de la qualité a un axe CO₂ aux graduations excessives pour un seul point et des points sans étiquette (U17, U-06).

**Approach:** Suivre le skill `dataviz` et EXPERIENCE.md (Chiffres, Graphiques) : historique en barres par session, dans l'unité CO₂ de la règle (mg le plus souvent), trous visibles, fenêtre de temps ; matrices à l'échelle honnête, avec légende des séries et légende de taille, étiquettes directes lisibles et vue tableau ; palette du thème (`chartCategoricalColors`, validée par le script du skill) attribuée par entité.

## Boundaries & Constraints

**Always:** une seule unité CO₂ par graphique (règle `format_co2`/`common_co2_unit` de `src/app/formatting.py`) et l'unité dans le titre d'axe ; titre qui dit ce qui est tracé ; aucune donnée tracée entre deux mesures ; un seul axe y (jamais de double axe) ; légende présente dès 2 séries ; couleur liée à l'entité (même modèle, même couleur), jamais au rang ; `chart-4` clair (2,87:1 sur la surface) jamais seul porteur d'une valeur : étiquettes visibles ou vue tableau ; formats `fr-FR` (`PLOTLY_SEPARATORS`, `VEGA_LOCALE`, dates numériques « 26/09 09:15 ») ; aucune couleur en dur, aucun CSS ; tests sans Ollama.

**Never:** changer la mesure ou le fichier d'émissions (story 6) ; changer les notes, le juge ou le classement (stories 5 et 7) ; charger une bibliothèque ou une locale depuis un CDN ; ajouter un double axe ou un graphique « cumul » qui redescend.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Historique | 3 sessions de 0,42 g, 0,63 g et 1,2 g | Barres par session, titre « Émissions de CO₂ par session », axe « CO₂ (mg) », valeurs 420, 630, 1 200 | — |
| Trous | sessions à 09:00 et 11:00, rien entre | Deux barres séparées, aucune liaison entre elles | — |
| Fenêtre | sessions sur 40 jours ; fenêtre « 7 derniers jours » | Seules les sessions des 7 derniers jours ; fenêtre choisie par l'utilisateur (7 jours, 30 jours, tout) | fenêtre vide → « Aucune session sur cette période. » |
| Historique vide | aucun fichier | « Aucune session mesurée pour l'instant. » inchangé | — |
| Arène | 3 modèles à 5,8, 5,9 et 6,0 tokens/s | Axe du débit partant de 0 ; légende des modèles ; légende de taille (CO₂) ; étiquettes dans le cadre | — |
| Arène, noms | nom long « Granite 4.0 3B Instruct » | Nom complet dans le graphique, la légende et le tableau | — |
| Évaluation | un seul modèle noté | Axe CO₂ partant de 0 avec quelques graduations ; point étiqueté ; échelle /100 comme le podium | — |
| Couleurs | modèles A, B, C puis filtre sur B, C | B et C gardent leur couleur | — |

</intent-contract>

## Code Map

- `src/app/views/01_Socle_Hardware.py:188-218` -- historique : `px.area(df.tail(50), x="timestamp", y="emissions")` en kg, titre « Émissions de CO₂ par session (kg) », `tickformat="%d/%m %H:%M"`, `separators=PLOTLY_SEPARATORS`.
- `src/core/green_monitor.py:214-256` -- `read_app_emissions()` : colonnes `timestamp`, `project_name`, `emissions` (kg), `emissions_g` ; une ligne par session (`run_id`), triée ; vide ou `EmissionsHistoryError`.
- `src/app/formatting.py` -- `PLOTLY_SEPARATORS`, `co2_unit`, `common_co2_unit` (unité de la plus petite valeur non nulle), `co2_in_unit`, `format_co2`, `format_date`, `format_time`.
- `src/app/tabs/inference/arena.py:294-353` -- `_render_podium` : un `go.Scatter` par modèle noté, taille `max(15, min(50, co2_mg/2))`, étoile pour le vainqueur, `showlegend=False`, `yaxis.range=[0, 110]`, pas de plage x ; `_co2_label`, `format_throughput` ; tableau `_render_results_table` (l.180-220) déjà présent ; multiselect `label_visibility="collapsed"` (l.410-415).
- `src/app/tabs/rag/eval.py:339-379` -- Altair `mark_circle(size=150)`, `x=CO2` sans échelle, `y=Note` domaine [0, 100], `color="Modèle"`, info-bulles, `.configure(locale=VEGA_LOCALE)` ; tableau en dessous.
- `.streamlit/config.toml` -- `chartCategoricalColors` clair `#6A4DE6,#0E9F5E,#2F7FD8,#C98A00`, sombre `#7A5FEA,#12A564,#3B86DB,#B07800` ; résultat du validateur du skill `dataviz` (2026-09-27) : clair ALL PASS avec avertissement de contraste `#C98A00` 2,87:1 (étiquettes ou tableau obligatoires), sombre ALL PASS sur `#0A0A14`.
- Tests à mettre à jour sur la nouvelle cible : `tests/app/test_figures.py` (`_chart_values` lit y en kg : `test_history_reads_tracker_file_and_ignores_benchmark`, `test_history_matches_real_tracker` ; `_bubble_texts` suppose un `text` par trace ; `test_documents_evaluation_common_co2_unit` sur les titres d'axe).

## Tasks & Acceptance

**Execution:**
- `src/app/views/01_Socle_Hardware.py` (et une fonction pure de préparation des données, testable) -- barres par session dans l'unité de la règle, fenêtre de temps choisie (`st.segmented_control` ou `st.radio` horizontal), trous visibles, info-bulle date + CO₂, vue tableau repliée.
- `src/app/tabs/inference/arena.py` -- axe x depuis 0, légende des modèles, légende de taille, étiquettes dans le cadre, noms complets, couleur par entité.
- `src/app/tabs/rag/eval.py` -- axe CO₂ depuis 0 avec un nombre de graduations borné, étiquettes des points, légende.
- `tests/` -- chaque ligne de la matrice (spécifications Plotly et Vega-Lite lues dans AppTest) ; tests existants mis à jour sur la cible, sans affaiblissement.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given l'app lancée avec des données simulées, when on affiche Sobriété et matériel et l'Arène au navigateur en clair et en sombre, then les graphiques sont lisibles (aucune étiquette coupée) et aucune requête ne part hors localhost.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 42 findings — high 0, medium 9, low 22, false 2, maybe-false 9
- findings:
  - `[maybe-false]` `[reject]` (intent) lisibilité vérifiée sur les spécifications et non au rendu — rendu vérifié au navigateur (clair, sombre) par l'implémentation ; captures au matin.
  - `[medium]` `[defer]` (intent) noms tronqués dans le multiselect de l'Arène (U-06) — limite du composant natif sans CSS ; noms complets dans le graphique, la légende et le tableau.
  - `[low]` `[reject]` (intent) unité « mg » littérale contre la règle d'unité — règle d'EXPERIENCE.md, mg dans les cas courants.
  - `[low]` `[patch]` (intent, edge) info-bulle en date littérale — « 27/09/2026 09:00 ».
  - `[low]` `[patch]` (intent, blind) période de 7 jours vide qui cache des sessions plus anciennes — message avec le nombre et « Tout ».
  - `[low]` `[patch]` (intent, blind, edge) retrait de `.interactive()` non justifié — commentaire (étiquettes gardées dans le cadre).
  - `[low]` `[patch]` (blind) fuseau fixe (heure d'été) — `tzlocal()`, test à Paris en janvier et juillet.
  - `[medium]` `[patch]` (blind, edge) sessions au même horodatage superposées — barres côte à côte dans le créneau.
  - `[medium]` `[defer]` (blind) barres très fines sur 30 jours ou « Tout » — barres par session voulues (matrice) ; valeurs dans le tableau ; regroupement par jour à décider au matin.
  - `[medium]` `[patch]` (blind, edge, verification-gap) étiquettes superposées dans l'évaluation — `stacked_labels`, traits de liaison.
  - `[medium]` `[patch]` (blind, edge) couleurs répétées au-delà de 4 modèles dans l'évaluation — forme par emplacement, légende fusionnée.
  - `[low]` `[patch]` (blind) même modèle, couleurs différentes entre Arène et évaluation — registre partagé par tag.
  - `[medium]` `[patch]` (blind, edge) import privé de Streamlit qui peut casser trois pages — import protégé, repli sur les couleurs par défaut.
  - `[low]` `[patch]` (blind) fonctions non testées (`ink_expr`, `remember_entity_slots`, cas vides) — tests.
  - `[low]` `[patch]` (blind, edge) axe sans année — année sur « Tout » ou sur deux années.
  - `[low]` `[patch]` (blind) légende verticale qui réduit le tracé — légende horizontale sous le graphique.
  - `[low]` `[patch]` (blind) docstring du module inexacte — corrigée.
  - `[low]` `[patch]` (blind) légende qui masque les modèles au-delà de la palette — formes par emplacement.
  - `[medium]` `[patch]` (edge) `stacked_labels` sous l'axe pour (100, 5, 4) ou 9 étiquettes — écart resserré, remontée.
  - `[low]` `[patch]` (edge) `barcornerradius` et plotly 5.18 — `plotly>=5.19.0`.
  - `[low]` `[patch]` (edge) étoile du vainqueur à 10 px — minimum 25 px.
  - `[medium]` `[patch]` (verification-gap) étoile du vainqueur jamais vérifiée — test.
  - `[medium]` `[patch]` (verification-gap) orientation des étiquettes de l'évaluation non vérifiée — test.
  - `[low]` `[patch]` (verification-gap) contenu de `ink_expr` non vérifié — test exact.
  - `[low]` `[defer]` (verification-gap) plage de l'axe x de l'historique non vérifiée au niveau de la page — vérifiée sur la fonction.
  - `[maybe-false]` `[reject]` (intent) validateur non relancé dans la story — relancé en planification (clair ALL PASS avec avertissement 2,87:1 de `#C98A00`, sombre ALL PASS).
  - `[maybe-false]` `[reject]` (intent) `tickCount` indicatif pour Vega — domaine borné `nice` ; rendu vérifié.
  - `[low]` `[reject]` (intent) vue cumulée absente — barres par session, option permise.
  - `[low]` `[reject]` (intent) `fake_inference` enrichi — support de test.
  - `[false]` `[reject]` (edge) claims de la docstring — doublons corrigés.
  - `[false]` `[reject]` (edge) claim « jamais de recouvrement » — doublon corrigé.
  - `[maybe-false]` `[reject]` (blind) hauteur d'étiquettes réglée pour 420 px — relevée à 460, vérifiée au navigateur.
  - `[low]` `[reject]` (blind) mémoire des couleurs limitée à la session — suffisant pour une démo.
  - `[maybe-false]` `[reject]` (intent) « petits » écarts de pixels entre étiquettes — vérifiés au navigateur.
  - `[low]` `[reject]` (edge) claim info-bulle — doublon corrigé.
  - `[maybe-false]` `[reject]` (intent) jetons de thème vérifiés par recherche dans le paquet JS — rendu vérifié au navigateur.
  - `[low]` `[reject]` (blind) `test_palette_size_reads_theme` dépend du répertoire courant — la suite se lance depuis la racine (README, CI).
  - `[maybe-false]` `[reject]` (intent) texte d'encre Vega testé par présence — expression exacte désormais testée.
  - `[low]` `[reject]` (verification-gap) « Other findings » étiquettes — doublon.
  - `[low]` `[reject]` (blind) domaine Vega avec valeurs invisibles — remplacé par les formes et le registre.
  - `[maybe-false]` `[reject]` (intent) placement des étiquettes en pixels — doublon.

## Design Notes

Couleur par entité : construire l'ordre des couleurs à partir de l'ordre stable des modèles sélectionnés (pas du classement), et le passer explicitement à Plotly (`color_discrete_map` ou `marker.color` lu depuis la palette du thème actif via `st.get_option("theme.…")` si disponible) ; à défaut, s'appuyer sur `chartCategoricalColors` en conservant l'ordre des traces. Légende de taille : une trace fantôme par taille repère (par exemple minimum, médiane, maximum du CO₂) ou une légende textuelle sous le graphique (« taille du point = CO₂, de X à Y mgCO₂ »).

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed

**Manual checks (if no CLI):**
- Navigateur (lanceur à providers simulés `/tmp/nuit/axe/launch_fake.py`) : Sobriété et matériel avec un historique écrit sous le dossier temporaire du lanceur ; captures clair et sombre ; aucune requête externe.

## Auto Run Result

Status: done

**Résumé :** historique d'émissions en barres par session (unité de la règle, mg en pratique), trous visibles, fenêtre de temps (7 jours, 30 jours, tout), info-bulle et tableau ; matrice de l'Arène à l'échelle honnête (débit depuis 0), légende des modèles, légende de taille, étiquettes empilées dans le cadre, étoile du vainqueur ; matrice de l'évaluation avec axe CO₂ depuis 0, étiquettes, formes au-delà de la palette ; couleurs du thème (`chartCategoricalColors`) attribuées par modèle (registre partagé par tag).

**Fichiers :** `src/app/charts.py` (nouveau) ; `src/app/views/01_Socle_Hardware.py`, `src/app/tabs/inference/arena.py`, `src/app/tabs/rag/eval.py` ; `requirements.txt` (`plotly>=5.19.0`) ; tests `tests/unit/test_charts.py`, `tests/app/test_figures.py`, `tests/app/conftest.py`.

**Revue :** 21 correctifs (7 medium, 14 low), 3 différés, 18 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les medium sont couverts par des tests ajoutés.

**Vérification :** `pytest tests/unit tests/app` : 731 réussis ; navigateur (implémentation) : clair et sombre, aucune étiquette coupée, aucune requête externe ; palette validée par le script du skill `dataviz`.

**Risques :** jetons de couleur tirés d'un module privé de Streamlit (import protégé, test de remplacement) ; `python-dateutil` importé directement (dépendance de pandas, non déclarée) ; barres fines sur les longues périodes ; noms tronqués dans le multiselect natif.
