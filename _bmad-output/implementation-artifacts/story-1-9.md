---
title: 'La barre haute dit l''état d''Ollama, du cloud et du CO₂, en direct'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '54e43c5'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-7.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-8.md'
warnings: []
deferred:
  - summary: >-
      « Réessayer » (panneau Ollama) n'interroge pas Ollama de force : il rouvre le flux si la connexion est perdue, sinon il attend le prochain état du flux (2 s au plus). Une route qui force la sonde n'existe pas et `models/` n'est pas touché par cette story.
    evidence: |-
      `OllamaProbe.status()` ne sait que servir son cache ou relancer une sonde ; `core/system.js` `recheck()`.
    location: src/wavelocalai/web/static/core/system.js
    severity: low
  - summary: >-
      Le flux système ne se met pas en pause quand l'onglet est masqué (`visibilitychange`). La pause est demandée pour les cartes d'état de l'Accueil (UX-DR24, story suivante) ; la barre haute, elle, reste branchée (un seul flux, 2 s).
    evidence: |-
      Critères de la story 1.9 : pas de pause demandée ; UX-DR24 la place sur les cartes de l'Accueil.
    location: src/wavelocalai/web/static/core/sse.js
    severity: low
  - summary: >-
      Les textes de `errors.ollama_down` sont recopiés dans `fr.json` (le panneau Ollama n'a pas d'enveloppe d'API à afficher : l'état vient du flux). Un test compare la copie à `errors.py`, mais deux sources existent tant qu'aucune route n'expose le catalogue d'erreurs.
    evidence: |-
      `test_the_ollama_down_text_mirrors_errors_py` ; AD-20 « textes dans fr.json ».
    location: src/wavelocalai/web/static/i18n/fr.json
    severity: low
---

# Story 1.9 : la barre haute dit l'état d'Ollama, du cloud et du CO₂, en direct

## Objectif

La barre haute de la coquille (story 1.8) montre, depuis n'importe quel écran et sans rechargement : la pastille Ollama (libellé et panneau), l'interrupteur « Autoriser le cloud » avec son aide, le CO₂ de la session (total, Local et Cloud, non mesurables) et, quand le serveur se tait ou redémarre, un bandeau. Tout vient d'**un seul flux** `GET /api/system/stream` lu par `core/sse.js` et gardé dans **un seul store** `core/store.js` ; la bascule cloud n'existe que dans ce store. La story livre aussi les briques partagées de la suite : `core/api.js`, `core/format.js` (`fr-FR`), `wl-badge`, `wl-metric` et `wl-error`.

## Critères d'acceptation et preuves

1. **Client SSE unique.** `core/sse.js` lit le flux par `fetch` (pas d'`EventSource`, qui se reconnecte sans fin), découpe les trames (`SseParser`, lignes `\n`, `\r\n`, `\r`, coupures n'importe où), aiguille par `type`, ignore un type inconnu, écarte tout `seq` déjà vu sur un flux de run (dernier `seq` dans le store), reprend par `?after=<seq>` et ferme à `run_ended` ou sur `204`. Preuves : `test_the_parser_rebuilds_frames_split_anywhere_in_the_stream`, `test_a_run_stream_routes_by_type_drops_seen_seq_and_closes_at_run_ended`, `test_a_dropped_run_stream_resumes_after_the_last_seq`, `test_a_204_closes_the_run_stream_and_an_unknown_run_gives_up`, `test_a_scripted_run_of_the_real_server_streams_to_run_ended`, `test_only_one_system_stream_is_open_for_the_whole_page`.
2. **Connexion perdue, serveur redémarré.** Après 3 échecs de suite, l'état passe à `lost` et le bandeau « Connexion au serveur perdue, nouvelle tentative… » s'affiche (les essais continuent, délai croissant) ; à chaque ouverture du flux, `/api/health` est relu et un `instance_id` qui change affiche « Le serveur a redémarré. Les exécutions en cours sont perdues. » avec « Recharger ». Pendant la perte, la pastille dit « Ollama, état inconnu ». Preuves : `test_banner_appears_after_three_failures_and_goes_when_the_server_is_back`, `test_a_restarted_server_is_announced_with_a_reload_button` (serveur coupé puis relancé dans le test).
3. **Pastille Ollama.** Libellé « Ollama ne répond pas » / « Ollama disponible » (icône et couleur en plus, jamais seules), annonce polie du changement, et panneau : état (« Disponible » / « Indisponible »), version, modèles chargés, mémoire, « Réessayer », et l'erreur `ollama_down` (message, action) quand Ollama est arrêté. Ollama « démarré » en moins de 3 s : un `FakeOllama` du banc E2E (port dédié, jamais le vrai Ollama) est allumé puis éteint. Côté serveur, la sonde du flux garde l'état au plus `SAMPLE_INTERVAL_S / 2` (1 s) au lieu de 5 s ; les routes de lecture gardent le cache d'AD-15. Preuves : `test_ollama_stopped_the_pill_says_it_in_words_and_the_panel_explains`, `test_ollama_started_then_stopped_the_pill_follows_in_under_3_s`, `test_retry_asks_again_and_reports_the_new_state`, `test_the_stream_probe_keeps_the_state_for_less_than_the_stream_interval`.
4. **Interrupteur « Autoriser le cloud ».** `<input type="checkbox" role="switch">` relié par `aria-describedby` à l'aide « Désactivé à chaque ouverture de la page. Activé, les données envoyées aux modèles cloud quittent la machine. » (bouton d'aide qui l'affiche). État dans le store seul : conservé d'un écran à l'autre, jamais dans `localStorage` ni `sessionStorage`, faux au rechargement ; le pied de page dit « Le cloud est autorisé… » quand il est actif. Preuves : `test_cloud_choice_survives_a_change_of_screen_and_never_a_reload`, `test_cloud_switch_is_off_by_default_with_its_help`, `test_cloud_switch_works_from_the_keyboard`, `test_no_script_reads_or_writes_the_cloud_switch_in_storage` (seul `theme.js` touche le stockage).
5. **CO₂ de session.** Pastille « CO₂ session <total> » et panneau : total, Local, Cloud, non mesurables (« Aucune réponse », « 1 réponse », « N réponses »), au format `core/format.js` (mg sous 1 g, g, kg, une seule unité pour le total et ses parts, espace insécable), mis à jour sur `carbon_updated`, relu par `GET /api/carbon/session` au chargement. Lien « Détails dans Sobriété » désactivé (`aria-disabled`, raison visible, focalisable) tant que l'écran est `planned`, actif dès qu'il est `available`. Pour tester sans service de mesure, la route `POST /api/test/runs` (mode test) accepte `origin` et `co2` et publie `carbon_updated` après le run, comme le feront les services. Preuves : `test_co2_panel_follows_carbon_updated_in_milligrams_then_grams`, `test_co2_survives_a_reload_from_the_session_endpoint`, `test_co2_badges_and_the_disabled_sobriety_link`, `test_the_sobriety_link_goes_live_once_the_screen_is_available`, `tests/v2/web/test_topbar_support.py`.
6. **Formats.** `core/format.js` : `fr-FR` par `Intl`, trois chiffres significatifs, CO₂ sans « 1 000 mg », un inconnu jamais 0 (« inconnu », score « non évalué »), Go, débit, durées (« 1 min 12 s »), dates (« 18 oct. 2026 »). Preuves : `test_co2_picks_mg_g_or_kg_and_never_shows_a_zero_for_an_unknown`, `test_a_comparison_of_co2_values_uses_a_single_unit`, `test_numbers_use_the_french_locale_with_three_significant_digits`, `test_durations_dates_and_scores`, `test_the_front_computes_no_measure_and_names_no_host`.
7. **Composants `wl-badge`, `wl-metric`, `wl-error`** (Custom Elements sans Shadow DOM) sur la page d'essai `tests/v2/e2e/fixtures/components.html`, servie par interception E2E seulement : Local (`computer`, vert), Cloud (`cloud`, orange), Origine inconnue (`help`, gris, aussi sans attribut), étiquettes « indicatif », « un seul juge », « estimé », « non mesurable », toujours un texte ; métrique avec unité, aide par `<button aria-describedby>`, « provisoire » en italique et dit en toutes lettres ; erreur : `message`, puis `action`, `detail` replié sous « Détails techniques ». Preuves : `tests/v2/e2e/test_components.py` (8 cas dont axe en clair et en sombre, sans exclusion).
8. **Accessibilité et trafic.** axe-core, zéro violation et aucune exclusion : barre haute fermée, chaque panneau ouvert, cloud autorisé, bandeaux de connexion et de redémarrage, en clair et en sombre ; aucun défilement horizontal de 320 à 1 440 px, panneaux dans la fenêtre ; menu repliable sous 1 024 px conservé ; toute requête reste sur `127.0.0.1` (le contexte E2E bloque et relève le reste). Preuves : `test_axe_finds_no_violation_on_the_top_bar_in_every_state`, `test_axe_finds_no_violation_with_the_connection_banners`, `test_top_bar_has_no_horizontal_scroll_and_panels_stay_in_the_window`, `test_the_top_bar_never_leaves_127_0_0_1`.
9. **Cohérence.** La coquille se rend sans attendre l'API : le flux se branche après le repère `shell-ready`, et `test_shell_renders_under_300_ms_without_waiting_for_the_api_ollama_stopped` vérifie qu'aucune requête `/api/` ne part avant lui. `test_layers.py` et le budget de lecture restent verts ; aucun nouveau code dans `errors.py` ; `src/core/`, `src/app/`, `scripts/`, `models/`, `runs/hub.py` non touchés.

## Fichiers

- `web/static/core/` : `api.js`, `sse.js`, `store.js`, `format.js`, `system.js` (flux, santé et CO₂ vers le store), `topbar.js` (store vers la barre), `disclosure.js` (panneaux), `dom.js` ; `shell.js` (menu Affichage sur `disclosure.js`) ; `main.js` (branche le flux après `shell-ready`, charge les composants après les textes)
- `web/static/components/` : `wl-badge.js`, `wl-metric.js`, `wl-error.js`, `index.js` ; `index.html`, `components.css`, `i18n/fr.json`
- `web/app.py` (sonde du flux plus fraîche), `web/routes_test.py` (`origin`, `co2`, `carbon_updated`)
- Tests : `tests/v2/e2e/{conftest,test_shell}.py` (banc : `Backend` arrêtable, `FakeOllama`, `fixtures_url`), `test_{topbar,core,components}.py`, `fixtures/components.{html,js}` ; `tests/v2/web/test_topbar_support.py`, `tests/v2/unit/test_shell_static.py` (5 cas)

## Choix notables

- `fetch` plutôt que `EventSource` : reprise, comptage des échecs et arrêt à `run_ended` sous contrôle (AD-6) ; le même module sert le flux système et les flux de run.
- Le panneau Ollama et la pastille lisent l'état du flux ; `/api/health` n'amorce que l'identité du serveur (et l'état avant le premier tick). Une réponse de `/api/health` ne réécrit jamais l'état d'Ollama une fois connu, pour ne pas faire revenir un état en cache de 5 s.
- Les composants sont chargés par `import()` après les textes : ils lisent `fr.json` à l'affichage.
- Le libellé de la pastille suit les critères (« Ollama ne répond pas » / « Ollama disponible ») ; le mot « Indisponible » d'UX-DR24 est celui de la ligne d'état du panneau.
- Les tests de CO₂ qui comptent des totaux prennent un serveur neuf (`Backend`) : chaque run scripté ajoute une feuille à la session du serveur du module.
- Fichiers existants de la 1.8 passés en fins de ligne LF (le dépôt normalise à l'ajout).

## Reports

Voir l'en-tête `deferred` : « Réessayer » sans sonde forcée, pause du flux masqué (cartes de l'Accueil), double source des textes `ollama_down`.

## Revue

À faire : second avis (Haiku), puis passe de revue (Opus).
