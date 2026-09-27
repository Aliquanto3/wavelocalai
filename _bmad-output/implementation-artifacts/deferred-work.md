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
