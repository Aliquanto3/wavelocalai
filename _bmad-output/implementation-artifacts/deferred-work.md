# Travail différé

- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md`
  summary: Une seule règle de CO₂ par réponse, dans src/core, à la place des copies de chat.py, solo.py (answer_carbon_mg) et des autres onglets.
  evidence: Les copies divergent déjà (repli params_tot, tokens NaN ou négatifs) ; question ouverte 8 du rapport de nuit (formule recopiée dans 7 onglets).
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md`
  summary: Arène, Banc d'essai, Discussion documentaire et évaluation RAG choisissent encore la formule de CO₂ d'après le seul type du catalogue, pas d'après l'origine réelle du modèle.
  evidence: arena.py:604-617, lab.py:75-85, rag/chat.py:231-249, rag/eval.py:322-338 ne testent que info.get("type") == "api" ; un tag distant d'Ollama y affiche un badge Cloud et un CO₂ local. Antérieur à la story 12.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md`
  summary: Les points d'entrée hors app (scripts/setup_rag_models.py, imports directs de crew_engine ou vector_store) n'appellent pas disable_telemetry().
  evidence: setup_rag_models.py importe huggingface_hub.snapshot_download sans couper la télémétrie Hugging Face ; seule l'app et eval_engine se protègent.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md`
  summary: Documenter dans README.md et AGENTS.md les télémétries coupées par défaut et la façon d'en réactiver une (variable dans l'environnement ou le .env).
  evidence: Rien n'indique à l'utilisateur que LANGSMITH_TRACING et les autres sont forcés ; la modification d'AGENTS.md est hors d'une story de code.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/13-tests-e2e-fiables-vrai-poste.md`
  summary: Attendre le rerun du serveur au niveau des helpers e2e (select_option, multiselect_add, multiselect_clear) au lieu d'un état du navigateur, par exemple avec un compteur d'exécutions du script.
  evidence: Ces helpers passent encore un `until` vrai côté navigateur, contre la règle de leur propre docstring ; la story 13 corrige les appels qui échouaient, pas la cause commune. Un test a encore échoué une fois sur une option détachée du DOM (test_arena_timeout_does_not_block_others), puis réussi deux fois.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/13-tests-e2e-fiables-vrai-poste.md`
  summary: Réponse d'Ollama parfois tronquée sans erreur : le flux se termine sans son dernier fragment (done), l'app affiche un texte partiel et un débit « estimé ».
  evidence: Vu deux fois le 27/09 sur poste-rtx3060 avec gemma3:1b (e2e : 39 tokens, débit estimé, pas de chargement ; appel direct d'InferenceService : 35 tokens = 143 caractères // 4), jamais en trois essais suivants ni avec le client Ollama seul. maybe-false, medium si confirmé : journaliser dans ollama_provider.chat_stream la fin de flux sans `done` pour le prouver.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/14-couleur-primaire-sombre-lisible.md`
  summary: Liste explicite d'écarts de contraste acceptés dans test_accessibility.py (couleurs exactes, ratio, renvoi à DESIGN.md), pour que le test Agent_Lab sombre passe sur l'écart connu et échoue sur tout écart nouveau ; et classer le texte blanc sur primaryColor comme couleur du thème.
  evidence: Le test échoue désormais à chaque passage sur les pastilles à 4,24:1 (compromis accepté le 27/09) : une nouvelle régression sur cette page s'y confondrait. Le blanc des boutons principaux (4,26:1) n'est pas relevé : boutons dans des onglets masqués, et le blanc n'est pas une couleur de [theme.dark].
