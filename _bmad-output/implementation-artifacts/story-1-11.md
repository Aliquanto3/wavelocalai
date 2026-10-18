---
title: 'L''Accueil dit en 5 secondes si la démo peut partir'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: 'edb870e'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-9.md'
warnings: []
deferred:
  - summary: >-
      Le critère de publication de la story (`2.0.0a1` dans `pyproject.toml`, `uv.lock`, `CITATION.cff`, tag `v2.0.0-alpha.1`, release GitHub) n'est pas réalisé ici : il clôt l'Epic 1 entier et se fait après l'intégration des stories 1.10 et 1.11, suite verte, par l'orchestrateur.
    evidence: |-
      Dernier critère de la story 1.11 dans `epics.md` ; aucun fichier de version touché.
    location: pyproject.toml
    severity: medium
  - summary: >-
      « Aucun modèle local disponible » se lit sur l'état d'Ollama (arrêté = aucun modèle local), pas sur la liste des modèles installés : `GET /api/models` (registre, story 1.5) n'est pas dans la branche de base. Ollama démarré sans aucun modèle installé n'est donc pas encore dit sur l'Accueil ; la carte Système donne les modèles chargés en mémoire.
    evidence: |-
      `renderSystem` (`screens/home.js`) ; la branche part de `feat/v2-barre-haute`, sans `routes_models`.
    location: src/wavelocalai/web/static/screens/home.js
    severity: low
  - summary: >-
      Les cartes « Démo recommandée » (Epic 3, story 3.6) et « Assistant documentaire » avec le résumé de la base (Epic 4) ne sont pas livrées : chaque carte arrive avec son écran. L'Accueil ne liste que les modules dont un écran est `available`.
    evidence: |-
      Décision de structure du 2026-10-18 ; `test_planned_modules_have_no_card_on_the_home`.
    location: src/wavelocalai/web/static/screens/home.js
    severity: low
---

# Story 1.11 : l'Accueil dit en 5 secondes si la démo peut partir

## Objectif

L'écran `#/` (`screens/home.js`) montre le titre, l'accroche et quatre cartes d'état en direct : **Système** (Ollama), **Mode** (Local ou Cloud, avec le CO₂ de la session), **Processeur** et **Mémoire**. Elles lisent le store rempli par le flux système (AD-6) : l'écran ne fait aucun appel réseau, ne calcule aucune mesure (AD-20) et tous ses textes sont dans `fr.json`. Ollama arrêté, la carte Système dit « Indisponible », « Démarrez Ollama, puis cliquez sur Réessayer » et « Aucun modèle local disponible ». Onglet masqué, le flux se ferme et les cartes se figent ; au retour il se rouvre.

## Critères d'acceptation et preuves

1. **Titre, accroche, quatre cartes, squelette.** `h1` unique « Accueil », accroche « Le démonstrateur d'IA générative souveraine, frugale et sécurisée. », cartes Système, Mode, Processeur, Mémoire. Tant que le premier état du flux n'est pas arrivé (`store.systemSeen`), chaque carte montre un squelette (`aria-busy`, texte « Chargement… » pour les lecteurs d'écran) ; connexion perdue, « Inconnu » et « inconnu », jamais une valeur périmée ni un 0. Preuves : `test_home_shows_a_single_title_the_tagline_and_four_filled_cards`, `test_cards_show_a_skeleton_while_the_stream_has_not_answered_never_a_blank_page`, `test_mode_card_says_local_then_cloud_when_the_cloud_is_allowed`, `test_mode_card_follows_the_co2_of_the_session`.
2. **Budget « en 5 secondes ».** De l'ouverture de la page à trois cartes remplies, moins de 5 s (mesuré sur trois chargements, Ollama arrêté). Preuve : `test_the_cards_are_filled_in_under_5_seconds`.
3. **Ollama arrêté.** « Indisponible », « Démarrez Ollama, puis cliquez sur Réessayer », « Aucun modèle local disponible », bouton « Réessayer » (`aria-disabled` pendant la vérification, comme le panneau de la barre haute), liens actifs (marque, navigation). Ollama démarré : « Disponible », « Ollama 0.9.9 », « 1 modèle chargé en mémoire », la marche à suivre disparaît ; arrêté de nouveau, elle revient. Preuves : `test_ollama_stopped_the_system_card_says_it_and_what_to_do_while_links_stay_active`, `test_ollama_started_then_stopped_the_system_card_follows`, `test_retry_button_shows_the_wait_then_the_new_state` (`FakeOllama` du banc, jamais le vrai Ollama).
4. **Pause sur `visibilitychange`.** `core/system.js` ferme le flux système quand l'onglet est masqué et le rouvre au retour ; la réouverture relit `/api/health` et `GET /api/carbon/session` (contrat : un `carbon_updated` manqué pendant la pause est rattrapé). `screens/home.js` ne lit plus le store pendant la pause (`data-live`). Preuve : `test_a_hidden_tab_pauses_the_cards_and_the_return_resumes_them` (aucune nouvelle requête de flux pendant la pause, une seule au retour, état et CO₂ rattrapés).
5. **Aucune carte vers un écran absent.** Un module n'est listé (lien et résumé) que si un de ses écrans est `available` ; ni « Démo recommandée » ni « Assistant documentaire » avant les Epics 3 et 4. Preuves : `test_planned_modules_have_no_card_on_the_home`, `test_an_available_module_gets_a_link_with_its_summary`, `test_the_home_screen_reads_the_store_only_and_every_home_text_is_used`.
6. **Accessibilité, formats, trafic.** axe-core, zéro violation et aucune exclusion, en clair et en sombre : Ollama arrêté, cloud autorisé, lien de module, Ollama disponible, squelettes, connexion perdue ; aucun défilement horizontal à 320, 768 et 1 440 px ; formats `fr-FR` (« 12 % », « 14,3 Go », « sur 31,1 Go »), aucune requête hors de `127.0.0.1`. Preuves : `test_axe_finds_no_violation_on_the_home_in_every_state`, `…_with_ollama_up`, `…_on_the_skeleton_and_the_lost_connection`, `test_the_home_has_no_horizontal_scroll`, `test_the_home_never_leaves_127_0_0_1`, `formatPercent` dans `test_numbers_use_the_french_locale_with_three_significant_digits`.
7. **Cohérence.** `test_layers.py` et le budget de lecture restent verts ; `errors.py`, `src/core/`, `src/app/`, `scripts/` non touchés ; aucun code serveur ajouté.

## Fichiers

- `web/static/screens/home.js` (cartes, modules, pause), `screens.css` (nouveau, relié par `index.html`), `i18n/fr.json` (`home.*`)
- `web/static/core/system.js` (pause du flux sur `visibilitychange`, `recheckOllama()` pour les écrans), `core/store.js` (`systemSeen`), `core/format.js` (`formatPercent`, par ajout)
- Tests : `tests/v2/e2e/test_home.py` (21 cas), `test_core.py` (`formatPercent`), `tests/v2/unit/test_shell_static.py` (`screens.css` sans couleur en dur, Accueil sans appel d'API)

## Choix notables

- Les quatre cartes sont celles de l'epic et d'UX-DR24 (Système, Mode, Processeur, Mémoire) ; le CO₂ de la session s'affiche en ligne de détail de la carte Mode plutôt que dans une cinquième carte.
- Le `h1` reste « Accueil » (contrat de la 1.8 : titre de l'onglet, annonce et focus portent le nom de l'écran) ; la marque « WaveLocalAI » est dans la barre haute.
- La pause est dans `core/system.js` et non dans l'écran : il n'y a qu'un flux pour la page (barre haute comprise), le fermer onglet masqué ne coûte rien et la reconnexion rattrape l'identité du serveur et le CO₂.
- Les cartes mises à jour toutes les 2 s ne recréent jamais un bouton ni un nœud inchangé (le focus sur « Réessayer » ne bouge pas).
- Squelette animé par `@keyframes` ; `prefers-reduced-motion` est déjà neutralisé par `base.css`.

## Reports

Voir l'en-tête `deferred` : publication `2.0.0a1` (après 1.10 et 1.11), « Aucun modèle local disponible » sans le registre, cartes « Démo recommandée » et résumé de la base (Epics 3 et 4).

## Revue

À faire : second avis (Haiku), puis passe de revue (Opus).
