# Tests e2e navigateur et accessibilité

Ces parcours pilotent l'app réelle dans Chromium (Playwright), avec Ollama et de vrais petits modèles. Ils remplacent les scripts d'audit de `docs/audits/frontend-2026-09/` (`poste-rtx3060/playwright/`, `pro-elitebook-x360/e2e/`), qui restent en trace.

> **État au 2026-09-27 : jamais exécutée contre un vrai Ollama.** La suite a été écrite et collectée dans une VM sans Ollama (`pytest tests/e2e -m e2e --collect-only`). Seuls les sélecteurs et les helpers ont été essayés à la main, sur l'app avec des fournisseurs simulés. Le premier vrai passage se fait sur un poste avec Ollama : attendre des ajustements.

Chaque module est marqué `e2e`. Le `-m "not e2e"` de `pytest.ini` les exclut de toute exécution par défaut, CI comprise. `tests/unit/test_e2e_suite.py` vérifie ce marquage et cette exclusion.

## Prérequis

- **Ollama démarré** sur `http://localhost:11434` (`ollama serve`). Sans lui, chaque test échoue avec un message qui le dit.
- **Les modèles des variables ci-dessous, déjà installés.** Les tests ne téléchargent rien : un modèle absent fait échouer le test, avec la commande `ollama pull` à lancer avant la suite.
- **Un modèle d'embedding local** pour l'assistant documentaire : un dossier dans `data/models/embeddings/`, ou le modèle par défaut de l'app (`DEFAULT_EMBEDDING_MODEL` de `src/core/rag_engine.py`, `all-MiniLM-L6-v2`) déjà présent dans le cache Hugging Face. L'app de test tourne avec `HF_HUB_OFFLINE=1`.
- **Les dépendances e2e**, dans l'environnement de l'app (`.venv-app`), jamais dans le `.venv` du benchmark :

  ```bash
  uv pip install --python .venv-app/bin/python -r requirements.txt -c constraints.txt
  ```

  `playwright` et `axe-playwright-python` sont figés dans `constraints.txt`. `axe-playwright-python` embarque axe-core : aucun CDN.
- **Chromium pour Playwright**, installé une fois, hors des tests :

  ```bash
  .venv-app/bin/python -m playwright install chromium
  ```

  Pour un Chromium déjà présent ailleurs, indiquer son exécutable dans `WAVELOCALAI_E2E_CHROMIUM`.
- **L'app habituelle arrêtée.** La suite vérifie que les données réelles sont identiques avant et après : `data/chroma`, `data/logs`, `data/exports`, `data/benchmarks.db`, `data/models.json` et `outputs/`. Une app lancée à côté, qui écrit ses émissions dans `data/logs`, ferait échouer cette vérification.

## Lancer

```bash
.venv-app/bin/python -m pytest tests/e2e -m e2e
```

Sous Windows : `.venv-app\Scripts\python -m pytest tests/e2e -m e2e`.

Compter 10 à 20 minutes selon la machine. Chaque module lance sa propre instance de l'app (port libre, dossier temporaire). Pour un seul parcours : `.venv-app/bin/python -m pytest tests/e2e/test_documents.py -m e2e`.

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `WAVELOCALAI_E2E_MODEL_CHAT` | `gemma3:1b` | Chat libre, banc d'essai, Arène, assistant documentaire |
| `WAVELOCALAI_E2E_MODEL_SMALL` | `granite4:350m` | Second modèle de l'Arène. Dans `test_arena_timeout.py`, il reçoit un délai volontairement trop court. Il doit donc différer du modèle de chat et du juge. |
| `WAVELOCALAI_E2E_MODEL_AGENT` | `qwen3.5:0.8b` | Agent seul et équipe d'agents. Il doit savoir appeler des outils (calculatrice, email). |
| `WAVELOCALAI_E2E_MODEL_JUDGE` | le modèle de chat | Juge de l'Arène |
| `WAVELOCALAI_E2E_TIMEOUT_S` | `300` | Délai d'attente des tests pour une génération réelle, premier chargement compris (secondes, > 0) |
| `WAVELOCALAI_E2E_SHORT_TIMEOUT_S` | `0.05` | Délai d'inférence imposé par le lanceur au seul petit modèle dans `test_arena_timeout.py`, pour provoquer « Délai dépassé » (secondes, > 0) |
| `WAVELOCALAI_E2E_CHROMIUM` | Chromium de Playwright | Exécutable Chromium à utiliser |

Les tags sont ceux d'Ollama (`ollama list`). Les sélecteurs de l'app affichent le nom du catalogue (`data/models.json`). Les tests le retrouvent à partir du tag.

## Garanties

- **App isolée.** `launch_app.py` lance l'app dans un sous-processus et redirige vers un dossier temporaire tout ce qu'elle peut écrire pendant les parcours : Chroma, CodeCarbon et historique d'émissions, fichiers des outils de l'agent (`outputs/`), base et exports de benchmark. `tests/unit/test_e2e_suite.py` vérifie cette redirection sans navigateur. Avant « Vider définitivement », le test exige en plus que la collection du dossier temporaire contienne des données. L'import de documents passe par l'interface, car une écriture Chroma faite par un autre processus resterait invisible pour le serveur.
- **Aucun fournisseur simulé.** Seul `test_arena_timeout.py` raccourcit le délai d'inférence du petit modèle. L'appel à Ollama reste réel ; c'est le délai de l'application qui l'interrompt.
- **Rien ne quitte la machine, et voici exactement ce qui est vérifié.**
  - Navigateur : toute requête HTTP et tout WebSocket vers un hôte qui n'est pas la machine locale sont bloqués et relevés ; le test échoue.
  - Serveur : un hook d'audit Python consigne, dès le démarrage, toute connexion (`socket.connect`) et toute résolution DNS (`socket.getaddrinfo`) vers l'extérieur dans `external_connections.log`. Le journal est vérifié après chaque test, puis en entier (import, démarrage, entre les tests, arrêt) quand l'app s'arrête.
  - Limite : le hook ne couvre que le processus lancé par `launch_app.py`, pas ses éventuels sous-processus. Les requêtes faites par Ollama lui-même ne sont pas couvertes non plus. Les clés cloud et SMTP du `.env` sont neutralisées, les télémétries (Chroma, CrewAI, LangSmith, Hugging Face, Streamlit) coupées. Le cloud n'est jamais activé.
- **Aucun email réel.** Le parcours email vise un puits SMTP local. Le test clique « Annuler » et vérifie qu'aucune connexion SMTP n'a eu lieu.
- **Lecture seule sur Ollama.** « Gestion des modèles » ouvre la fenêtre d'ajout, puis la ferme sans rien installer ; la liste d'Ollama est comparée avant et après.
- **Accessibilité.** axe-core tourne sur les cinq pages, en clair puis en sombre, avec les règles `color-contrast`, `heading-order` et `button-name`.
  - `heading-order` et `button-name` : toute violation fait échouer le test.
  - Une violation de contraste est imputable au thème quand sa couleur de texte est une couleur de `.streamlit/config.toml`, telle quelle ou mélangée au fond avec une opacité quelconque (à 2 près par canal) : Streamlit dérive par exemple ses textes estompés (`fadedText40/60`) de `textColor` avec une transparence. Elle fait échouer le test.
  - Le texte d'un composant inactif (widget désactivé : `aria-disabled` ou `:disabled`) n'a pas d'exigence de contraste (WCAG 1.4.3). Il est listé à part, comme les couleurs natives de Streamlit sans rapport avec le thème : résumé de fin de session et `e2e-reports/` (dossier temporaire de pytest). Rien n'est masqué, aucun test n'est marqué `skip` ni `xfail`.

Au 2026-09-27, avec des fournisseurs simulés, axe relève deux cas :

- **En sombre, décision en attente dans DESIGN.md :** Streamlit emploie `primaryColor` `#6A4DE6` comme couleur de texte : valeur du curseur de l'Arène à 3,57:1, pastilles d'outils choisies de l'agent à 3,34:1. Ce contraste vient du thème : `test_axe_no_theme_violation[Inference_Arena-dark]` et `[Agent_Lab-dark]` échoueront tant que la valeur n'est pas tranchée (story 2, validation du matin).
- **En clair comme en sombre :** le libellé « Outil non configuré » (2,70:1 en clair, 3,57:1 en sombre) est `textColor` à 40 % d'opacité, donc une couleur du thème. Comme il appartient à un widget désactivé, il est listé comme composant inactif, sans faire échouer le test.

## Traçabilité des constats

Chaque constat de `docs/audits/frontend-2026-09/SYNTHESE.md` (§3) a au moins un test qui l'aurait détecté. Les noms `test_…` sans chemin désignent des tests de `tests/e2e/`. Quand un constat ne s'observe pas au navigateur, la table renvoie au test unitaire (`tests/unit/`) ou AppTest (`tests/app/`) qui le couvre.

### Environnement et fonctionnement

| Constat | Test e2e | Couverture hors navigateur |
|---|---|---|
| E1 Installation non reproductible | Toute la suite lance l'app depuis l'environnement figé | `tests/app/test_socle.py::test_pinned_dependencies_import`, `::test_constraints_cover_requirements` |
| E2 La CI ne tourne jamais | Non observable au navigateur | `tests/app/test_socle.py::test_ci_runs_unit_and_app_tests_on_master` |
| E3 Tests unitaires en échec sans Ollama | Non observable au navigateur | La suite `tests/unit` elle-même, lancée par la CI ; `tests/unit/test_llm_provider.py::…::test_get_langchain_model_mistral`, `::test_pull_model_cloud_raises_error`, `tests/unit/test_models_db.py::…::test_get_all_languages` |
| F1 Import RAG factice | `test_documents.py::test_import_then_ask_with_source` : compteur, fichiers Chroma écrits, réponse et source | `tests/app/test_rag_upload_page.py::test_import_indexes_and_shows_result` |
| F2 Benchmark RAG à 0/100 sans Ragas | `test_documents.py::test_quality_evaluation_scores_or_not_evaluated` : note sur 100 ou « non évalué », jamais un succès vide (Ragas indisponible : non déclenchable sans le casser) | `tests/app/test_states.py::test_documents_evaluation_without_ragas`, `tests/unit/test_eval_engine.py::…::test_evaluate_without_ragas` |
| F3 Timeout affiché comme une trace | `test_arena_timeout.py::test_chat_timeout_is_readable`, `::test_lab_timeout_is_readable`, `::test_arena_timeout_does_not_block_others` | `tests/app/test_states.py::test_arena_one_model_times_out` |
| F4 Débit qui inclut le chargement | `test_arena.py::test_lab_throughput_excludes_loading` : même consigne à froid (vérifié par `/api/ps`) puis à chaud, au moins 30 tokens, débits à ±15 % ; `::test_chat_cold_start_load_and_badge` : chargement à part | `tests/unit/test_metrics.py::…::test_throughput_excludes_load_and_prefill` |
| F5 CO₂ de session ×1000 | `test_sobriety.py::test_session_co2_matches_codecarbon_and_history` : écart de moins de 5 % avec le CSV | `tests/app/test_figures.py::test_session_co2_after_stop_button` |
| F6 Historique qui ne lit pas le bon fichier | `test_sobriety.py::test_session_co2_matches_codecarbon_and_history` : la session apparaît dans le graphique | `tests/unit/test_green_monitor.py::…::test_tracker_writes_file_read_by_history` |
| F7 Réponse de l'agent perdue au rerun | `test_agents.py::test_solo_answer_and_model_survive_mode_switch` | `tests/app/test_nothing_lost.py::test_agent_answer_kept_after_mode_switch` |
| F8 Serveur exposé sur le réseau | `test_pages.py::test_server_listens_on_localhost_only` | `tests/app/test_socle.py::test_server_listens_on_localhost_only` |
| F9 Reranker ignoré | Non observable sans reranker local installé | `tests/app/test_nothing_lost.py::test_reranker_default_and_choice_applied`, `::test_sources_follow_reranker_scores`, `tests/unit/test_rag_reranker.py::test_search_uses_chosen_reranker` |
| F10 Défauts de modèles inadaptés | `test_arena.py::test_chat_cold_start_load_and_badge` (options locales), `::test_arena_two_local_models_with_judge` (présélection et juge locaux) | `tests/app/test_defaults.py::test_chat_and_lab_default_to_fastest_fitting_local`, `::test_arena_default_judge_is_largest_local_with_warning` |
| F11 Accélérateur mal détecté | `test_sobriety.py::test_accelerator_is_detected_not_assumed` : nom du GPU comparé à `nvidia-smi`, « Aucun » sans GPU | `tests/unit/test_failure_states.py::test_nvidia_gpu_detected`, `tests/app/test_states.py::test_accelerator_none_without_gpu` |
| F12 Deux collections Chroma | `test_documents.py::test_import_then_ask_with_source` : la page interroge la collection où elle a indexé | `tests/unit/test_rag_upload.py::test_default_embedding_name_shared_by_engine_and_page`, `tests/app/test_rag_upload_page.py::test_default_embedding_fallback_matches_engine` |
| F13 Arène lancée avec un seul modèle | `test_arena.py::test_arena_two_local_models_with_judge` : bouton désactivé et légende sous 2 modèles | `tests/app/test_defaults.py::test_arena_launch_disabled_with_one_model` |
| F14 `use_container_width` déprécié | `test_pages.py::test_no_deprecation_warning_on_any_page` (journal du serveur) | `tests/app/test_theme.py::test_app_sources_have_no_deprecated_width_nor_injected_html` |
| F15 112 W constants | Hors de la série (spike sur la machine réelle, SYNTHESE.md §6) | — |
| F16 Modèle de l'agent oublié après l'équipe | `test_agents.py::test_solo_answer_and_model_survive_mode_switch` | `tests/app/test_nothing_lost.py::test_agent_model_kept_after_crew_mode` |
| F17 Question perdue au garde-fou mémoire | `test_agents.py` : si le garde-fou bloque, la question doit rester affichée (échec explicite ensuite). Le garde-fou n'est pas déclenchable à coup sûr. | `tests/app/test_states.py::test_memory_guard_keeps_question`, `::test_free_memory_keeps_blocked_question` |

### Design, rédaction et vérité de l'interface

| Constat | Test e2e | Couverture hors navigateur |
|---|---|---|
| U1 Aucune identité Wavestone | `test_pages.py::test_primary_action_uses_brand_color` (couleur, police Inter locale, fond), `test_accessibility.py` (fond clair et sombre) | `tests/app/test_theme.py::test_theme_colors_match_design` |
| U2 Emojis en guise d'icônes et de titres | `test_pages.py::test_page_structure` : aucun emoji dans h1–h4, hors « 👋 Bonjour ! » | `tests/app/test_theme.py::test_app_sources_have_no_emoji` |
| U3 Barre d'outils de développement | `test_pages.py::test_home_is_local_and_available` : pas de bouton Deploy | `tests/app/test_theme.py::test_toolbar_and_static_serving` |
| U4 Rouge pour l'action principale | `test_pages.py::test_primary_action_uses_brand_color` | — |
| U5 Contrastes AA en échec | `test_accessibility.py::test_axe_no_theme_violation` (10 cas) | — |
| U6 Encart « base vide » illisible | `test_accessibility.py::test_axe_no_theme_violation[RAG_Knowledge-*]` : l'app neuve affiche l'état vide ; `test_documents.py` | — |
| U7 Bouton à icône seule sans nom | `test_accessibility.py` : règle `button-name` | — |
| U8 Un module, quatre noms | `test_pages.py::test_home_is_local_and_available` (menu, cartes, contrôle cloud unique), `::test_page_structure` (h1 = onglet) | `tests/app/test_navigation.py::test_module_title_matches_menu`, `::test_single_cloud_toggle_per_page` |
| U9 Franglais et jargon | `test_pages.py::test_page_structure` : aucun libellé d'avant le lexique | `tests/app/test_navigation.py::test_no_legacy_names_in_displayed_texts` |
| U10 Formats anglais, pied de page faux | `test_pages.py::test_home_is_local_and_available` (année, pas de version), `test_arena.py::test_chat_cold_start_load_and_badge` (virgule décimale) | `tests/unit/test_formatting.py` |
| U11 « Opérationnel » écrit en dur | `test_pages.py::test_home_is_local_and_available` (« Disponible »), `::test_page_structure` (aucun « Opérationnel ») | `tests/app/test_states.py::test_home_system_unavailable_when_ollama_down` (Ollama arrêté) |
| U12 Cloud actif par défaut | `test_pages.py::test_home_is_local_and_available` | `tests/app/test_sovereignty.py::test_startup_is_local_even_with_api_keys` |
| U13 Deltas détournés en étiquettes | `test_pages.py::test_home_is_local_and_available`, `test_sobriety.py::test_session_co2_matches_codecarbon_and_history` | `tests/app/test_sovereignty.py::test_metric_deltas_are_numeric` |
| U14 Email sans confirmation | `test_agents.py::test_email_requires_confirmation`, `test_pages.py::test_agent_tools_all_visible_email_unconfigured` | `tests/app/test_sovereignty.py::test_email_cancel_sends_nothing` |
| U15 Reset sans confirmation | `test_documents.py::test_clear_needs_confirmation` | `tests/app/test_sovereignty.py::test_clear_cancel_deletes_nothing` |
| U16 Historique : faux cumul, unités | `test_sobriety.py::test_session_co2_matches_codecarbon_and_history` : titre, unité, pas de « Cumul » | `tests/app/test_figures.py::test_history_bars_per_session_in_rule_unit` |
| U17 Matrices sans légende | `test_arena.py::test_arena_two_local_models_with_judge` : légende de taille, tableau, une seule unité de CO₂ | `tests/app/test_figures.py::test_arena_matrix_axes_legends_and_labels` |
| U18 Outils de l'agent masqués | `test_pages.py::test_agent_tools_all_visible_email_unconfigured` : 9 outils visibles à 1440 px | `tests/app/test_theme.py::test_agent_solo_shows_all_nine_tools` |
| U19 Juge trop faible | `test_arena.py::test_arena_two_local_models_with_judge` : avertissement quand le juge fait moins de 4B | `tests/app/test_defaults.py::test_arena_default_judge_is_largest_local_with_warning` |
| U20 Premier chargement sans retour | `test_arena.py::test_chat_cold_start_load_and_badge` : « Chargement du modèle en mémoire… » à froid | `tests/app/test_states.py::test_loading_status_shown_before_generation` |
