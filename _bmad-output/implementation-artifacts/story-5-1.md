---
title: "L'écran Sobriété montre la machine et la session en direct"
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '13bcd36'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/docs/maquette-v2/notes/sobriete.md'
warnings: []
deferred:
  - summary: >-
      (1) Le bouton « Remettre le compteur à zéro » et sa désactivation avec sa raison quand la session est vide sont couverts par la décision n° 16 du 2026-10-19 (stories 5.1 et 5.2), livrés en 5.2 avec leur route `POST /api/carbon/session/reset` : la 5.1 n'a aucun contrôle sans effet (décision de l'orchestrateur, revue). Points (2) et (3) : écarts nouveaux, variante la plus conservatrice (le critère de la story). La 5.2 le place en tête de la section « Empreinte carbone » (`sobriety-carbon.js`, qui l'attend : le calcul « session vide » y est déjà fait par `measured_runs` et `unmeasurable_runs` à 0). (2) La carte « Santé du système » dit « Aucun » dès que le flux n'a pas de champ `gpu`, y compris sur un Mac à puce Apple (le flux ne lit que NVML) : c'est le critère (« sans NVML, ces champs sont absents et l'écran dit Aucun »), la fiche d'identité, elle, nomme « Apple Silicon ». (3) La mémoire « disponibles » de la carte Mémoire est `memory.available_gb` du serveur (celle que compare le garde-fou), non « totale moins utilisée » de la maquette : le front ne soustrait rien (AD-20).
    evidence: |-
      `screens/sobriety-carbon.js`, `screens/sobriety-health.js::renderMemory`, `renderGpu`, `tests/v2/e2e/test_sobriety.py`.
    location: src/wavelocalai/web/static/screens/sobriety-carbon.js
    severity: low
  - summary: >-
      Facteur de l'équivalence en voiture à confirmer par Anaël. Source vérifiée le 2026-10-19 sur impactco2.fr (ADEME, « Modélisation de l'empreinte carbone de la voiture - 2025 », voiture thermique moyenne) : la page donne 142 g de CO₂e par km (0,14225 kg/km : fabrication 31,7 g + usage 111 g), l'API publique du même site donne 110,6 g/km (usage seul) pour la même voiture, et rien ne date la modélisation au-delà de l'année. Retenu : 142 g/km, fabrication et usage compris, la valeur qui compte tout le cycle de vie ; changer de valeur ne touche que `wavelocalai.toml`. Aucune ligne de la base Empreinte de l'ADEME n'a pu être lue directement (le site ne répond pas aux outils de lecture).
    evidence: |-
      `wavelocalai.toml` (`[carbon.car_equivalence]`), `tests/v2/unit/test_sobriety_server.py::test_the_versioned_toml_carries_a_dated_and_sourced_factor`.
    location: wavelocalai.toml
    severity: medium
  - summary: >-
      Choix de conception à confirmer. (1) L'équivalence vient d'une route à part, `GET /api/carbon/method` (le contrat annonçait « méthode » sans la nommer) : `carbon_updated` et `GET /api/carbon/session` restent inchangés (cinq services publient la somme de session, aucun n'a la configuration). Panneau ouvert, chaque `carbon_updated` relit la route (une lecture par réponse, jamais en boucle). (2) Les deux panneaux repliés ne lisent l'API qu'à l'ouverture : l'identité n'est pas lue au montage de l'écran (aucun appel avant `shell-ready`, AD-15, et aucun si la personne ne l'ouvre pas). (3) `POST /api/test/gpu` (route de test, `WAVELOCALAI_TESTING`) règle l'état du GPU que publie le flux : la CI n'a pas de GPU et le poste de dev en a un, l'E2E ne peut pas dépendre du matériel. (4) `formatDistance` (m, km, cm, mm) est ajouté à `core/format.js` : le serveur donne des mètres, l'écran ne choisit que l'unité, comme `co2Unit`.
    evidence: |-
      `web/routes_system.py::carbon_method`, `screens/sobriety-details.js`, `web/routes_test.py::script_gpu`, `core/format.js::formatDistance`.
    location: src/wavelocalai/web/routes_system.py
    severity: low
---

# Story 5.1 : l'écran Sobriété montre la machine et la session en direct

## Objectif

Un consultant qui présente la sobriété ouvre `#/sobriete` et voit, sans cliquer sur « Rafraîchir », la charge du poste (processeur, mémoire, accélérateur, Ollama) et le CO₂ de la session, ventilé par module et par origine. L'historique et la remise à zéro du compteur sont ceux de la 5.2.

## Critères d'acceptation et preuves

1. **Santé du système** : quatre `wl-metric` (processeur %, mémoire utilisée / totale, accélérateur, Ollama), mises à jour par le flux système toutes les 2 s sans clic ; squelette avant le premier état, « inconnu » connexion perdue ; Ollama arrêté : « Ollama ne répond pas » et « Réessayer ». Sans `gpu` dans le flux : « Aucun » (jamais « Actif »). Version d'Ollama en légende de la section (écart n° 16). Preuve : `test_sobriety.py::test_the_four_health_cards_*`, `test_without_a_gpu_*`, `test_ollama_loaded_models_and_its_version_*`, `test_the_retry_button_*`.
2. **Onglet masqué** : `visibilitychange` ferme le flux, la légende le dit, les dernières valeurs restent ; au retour le flux est rouvert et `GET /api/carbon/session` relu (la réponse jouée pendant la pause est comptée). Preuve : `test_a_hidden_tab_closes_the_stream_and_the_return_reads_the_session_again`.
3. **GPU (serveur)** : le flux ajoute `gpu` (`name`, `memory_used_gb`, `memory_total_gb`, `temperature_c`, `thermal_throttle`, `throttle_reasons`), lu par `hardware/machine_state.py::read_gpu_state` dans un fil, hors de la boucle : l'échantillon n'attend la lecture que 50 ms et rend sinon la précédente ; sans NVML le champ est absent. Le bridage ne compte que les raisons thermiques. L'écran dit « Bridage thermique en cours » en texte avec une icône. Preuve : `unit/test_sobriety_server.py` (lecture, bridage thermique ou non, lecture lente, GPU disparu), `web/test_sobriety_api.py::test_the_stream_publishes_the_gpu_*`, `e2e::test_the_accelerator_shows_*`, `test_a_thermal_throttle_*`.
4. **Identité machine** : `GET /api/system/identity` lit la version d'Ollama dans l'état en cache de la sonde (`OllamaProbe.cached`), sans appel réseau. **Mesure** : 24 ms, premier appel juste après `/api/health`, serveur lancé à froid (processus neuf), tour RTX 3050 de ce poste (fiche préchauffée au démarrage ; capture à froid : 112 ms) ; budget 300 ms. La carte d'identité, repliée, lit la fiche à son ouverture. Preuve : `web/test_sobriety_api.py::test_identity_*`, `e2e::test_the_identity_card_*`.
5. **Empreinte carbone** : total, part par module (chat, arène, rag, agent, ingest ; module à 0 omis), Local et Cloud « (estimé) », réponses non mesurables à part, depuis `GET /api/carbon/session` puis `carbon_updated` ; une seule unité pour toute la section ; session vide : « Aucune réponse mesurée dans cette session », jamais « 0 mg » ; aucune couleur ni mot de jugement par seuil. « non mesurables » est un lien qui déplie « Comment ces chiffres sont calculés ». Preuve : `e2e::test_the_session_follows_carbon_updated_*`, `test_one_unit_for_the_whole_section_*`, `test_only_unmeasurable_*`, `test_the_unmeasurable_link_*`, `test_an_empty_session_*`.
6. **Équivalence en voiture (D-38)** : dans le panneau de méthode seulement, avec le facteur (g de CO₂ par km), sa source et sa date ; distance, facteur, source et date viennent de `GET /api/carbon/method` (réglage `[carbon.car_equivalence]` de `wavelocalai.toml`, `g_per_km`, `source` et `retrieved_at` requis, sinon `ConfigError`), le front n'a aucune constante. `distance_m` = `total_mg` / `g_per_km` ; sans réponse mesurée, nul (jamais 0 m). Panneau ouvert, une réponse de plus met la phrase à jour. Preuve : `unit/test_sobriety_server.py` (calcul, réglage daté, refus), `web/test_sobriety_api.py::test_carbon_method_*`, `e2e::test_the_method_panel_gives_the_car_equivalence_*`, `test_the_equivalence_appears_nowhere_but_in_the_method_panel`, `test_no_equivalence_sentence_without_a_server_setting`.
7. **Accessibilité et structure** : axe-core sans violation, clair et sombre, session vide, session mesurée, panneaux ouverts, sans GPU, squelettes et connexion perdue ; pas de défilement horizontal à 320, 768 et 1440 px ; aucune requête hors de `127.0.0.1` ; aucun appel d'API avant `shell-ready` (AD-15) ; aucun JS au-delà de 600 lignes. Preuve : `e2e::test_axe_finds_no_violation_*`, `test_the_screen_has_no_horizontal_scroll`, `test_the_screen_never_leaves_127_0_0_1`, `unit/test_sobriety_static.py`.

## Source du facteur d'équivalence

ADEME, « Modélisation de l'empreinte carbone de la voiture - 2025 », voiture thermique moyenne, fabrication et usage : 142 g de CO₂e par km (0,14225 kg), relevé le 2026-10-19 sur `impactco2.fr/outils/transport/voiturethermique` (fabrication 31,7 g, usage 111 g ; l'API publique du site donne 110,6 g/km, usage seul). Voir le deuxième report.

## Hors périmètre

« Remettre le compteur à zéro » et `POST /api/carbon/session/reset`, l'historique (`GET /api/carbon/history`, graphique, tableau, segments) : story 5.2. Écran Modèles : 5.3 et suivantes.

## Notes de développement

- Front : `screens/sobriety.js` (montage, pause sur `visibilitychange`), `sobriety-health.js`, `sobriety-carbon.js`, `sobriety-details.js` (panneaux repliés) ; textes `i18n/fr/sobriety.json` (déclaré dans `TEXT_FILES`), CSS `sobriety.css`, appel `core/api/system.js::carbonMethod`, route `core/routes/sobriety.js` (`available`). `core/system.js` et `core/store.js` gardent `gpu` dans `store.system`. Le routeur garde l'écran monté : masqué, il ne relit rien et relit ses panneaux ouverts quand il redevient visible.
- Serveur : `hardware/machine_state.py::read_gpu_state`, `web/system_state.py` (lecture du GPU hors de la boucle, version d'Ollama de la sonde), `models/ollama_probe.py::cached`, `greenops/equivalence.py`, `web/routes_system.py::carbon_method`, `config.py::CarEquivalence`, route de test `POST /api/test/gpu`. `contrat-api.md` : champ `gpu` du flux, fiche d'identité, route de méthode.
- Réalignés : `test_shell.py` (Sobriété disponible : sixième écran, lien actif, plus de redirection de `#/sobriete`), `test_home.py` (trois liens de module), `test_topbar.py` (le lien « Détails dans Sobriété » est actif ; le cas désactivé se joue en repassant l'écran à `planned`), `test_shell_static.py` (six écrans disponibles).

## Rapport de dev

- Joué en local : `tests/v2/unit` (901 passés, 1 sauté), `tests/v2/web` ciblé (`test_system`, `test_sobriety_api`, `test_read_budget`, `test_defaults` : 40 passés), E2E `test_sobriety.py` (27), `test_shell.py` et `test_topbar.py` (67), `test_home.py` (32). La suite complète est celle de la CI.
- Pas de dépendance nouvelle ; `pynvml` était déjà là. Les valeurs de la maquette (111 g/km) étaient fictives : la valeur réelle est celle du `.toml`, à confirmer (deuxième report).

## Revue

Revue Opus du 2026-10-19, une passe, sur `13bcd36..16e2d8a`.

- medium · second avis n° 1 · corrigé · l'écart n° 16 est attribué à 5.1 et 5.2 par les décisions : le premier report dit maintenant « couvert par la décision n° 16, livré en 5.2 avec sa route » ; `sobriety-carbon.js` calcule déjà la session vide (`measured_runs`, `unmeasurable_runs`) et annonce la 5.2 en tête.
- low · second avis n° 2 · corrigé en partie · `formatDistance(0)` donnait « 0 mm » (session de réponses mesurées à 0 mg) : rend « 0 m ». 999,5 m en « 1 km » est voulu (arrondi à trois chiffres avant le choix d'unité, comme `co2Unit`) : rejeté. Vérifié sous node : 0 → « 0 m », 0,004 → « 4 mm », 3,7 → « 3,7 m », 1 234 → « 1,23 km ».
- low · second avis n° 3 · rejeté · le test désactivé garde sa valeur : `bindSobrietyLink` traite toujours un écran `planned`, et l'ancien test du cas actif mutait déjà le registre de la même façon.
- low · second avis n° 4 · rejeté · `nvmlDeviceGetCurrentClocksEventReasons` existe dans le `pynvml` installé et répond sur la RTX 3050 du poste (`read_gpu_state()` réel : `throttle_reasons: ['gpu_idle']`) ; le repli `[]` est la lecture au mieux de `nvml.py`, antérieure à la story.
- low · second avis n° 5 · corrigé · `SystemSampler._read_gpu` rattrape une exception du lecteur : état GPU effacé (jamais périmé) et avertissement journalisé, plus d'exception de tâche jamais récupérée. Test `test_a_gpu_reader_that_raises_clears_the_state_and_logs_it`.
- info · revue · Complexité : 0 constat. Panneau de méthode ouvert : une lecture de `GET /api/carbon/method` par `carbon_updated` (une agrégation SQL de session, pas de boucle) ; le store est rendu toutes les 2 s sans parcours d'historique.
- info · revue · facteur voiture 142 g/km (ADEME 2025) : laissé à la décision d'Anaël (deuxième report).

