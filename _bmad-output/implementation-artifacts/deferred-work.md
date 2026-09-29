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
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/15-juge-modele-defaut-benchmark-poste.md`
  summary: Trier « le plus rapide » (premier modèle proposé, présélection de l'Arène) sur le débit prudent du benchmark de ce poste plutôt que sur benchmark_stats de data/models.json.
  evidence: rank_models lit encore avg_tokens_per_second de data/models.json, qui peut venir d'une autre machine ; le benchmark du poste est déjà chargé dans model_menu mais ne sert qu'au juge. Antérieur à la story 15 (règle de la story 7).
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/16-fournisseur-cloud-groq.md`
  summary: OpenAIProvider._get_client appelle AsyncOpenAI, importé seulement sous TYPE_CHECKING : le premier vrai appel OpenAI lève NameError.
  evidence: src/core/providers/openai_provider.py (import `_AsyncOpenAI` au runtime, `AsyncOpenAI` sous TYPE_CHECKING, `from __future__ import annotations`). Antérieur à la story 16 ; GroqProvider crée son propre client et n'est pas touché. Correction d'une ligne (`_AsyncOpenAI(...)`), à tester avec un client simulé.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/16-fournisseur-cloud-groq.md`
  summary: Les modèles OpenAI et Anthropic listés sur la page Agents partent encore vers Ollama (agent seul et équipe) ; le tag Ollama `gpt-oss:20b` est routé vers OpenAI par son préfixe `gpt-`.
  evidence: agent_engine._initialize_llm et crew_engine._get_native_llm ne connaissent que Mistral et Groq ; provider_factory.get_provider teste `startswith("gpt-")` avant le repli Ollama. Antérieur à la story 16.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/16-fournisseur-cloud-groq.md`
  summary: Débit des modèles gpt-oss de Groq peut-être surestimé : usage.completion_tokens compterait les jetons de raisonnement invisibles.
  evidence: maybe-false, medium si confirmé : vérifier `completion_tokens_details.reasoning_tokens` sur une vraie réponse de openai/gpt-oss-120b (appel réel, avec l'accord de l'utilisateur).
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/18-constats-recette-arene-agents.md`
  summary: Gras affiché avec ses astérisques dans la réponse de l'agent seul (GPT-OSS 120B, recette C5 du 29/09), non reproduit.
  evidence: Réponse réelle capturée le 29/09 (`**Résultat :** 7 006 652`, `---`, italique) rendue correctement par st.markdown dans Chrome ; la sortie du modèle varie. maybe-false : à la prochaine occurrence, copier le texte brut de la réponse (ou une capture) pour trouver le motif fautif.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/18-constats-recette-arene-agents.md`
  summary: Sur la page Agents, la mention « outils vérifiés » vient de la capacité `tools` du catalogue, même quand le benchmark de ce poste mesure un taux de réussite des outils de 0 (Gemma 3 1B, OLMo 3 7B).
  evidence: 04_Agent_Lab.py lit `capabilities` de data/models.json ; seul le modèle d'agent_default reçoit la mention d'après le benchmark. Antérieur à la story 18 : lire `tool_success` du benchmark du poste quand il existe, le catalogue sinon.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/19-constats-recette-discussion-flux-e2e.md`
  summary: L'évaluation de la qualité de l'Assistant documentaire envoie encore au juge (Ragas) une réponse vide, faite seulement de raisonnement (Qwen 3.5 0.8B).
  evidence: src/app/tabs/rag/eval.py (~l. 317) garde `clean_answer` d'`extract_thought` sans tester le vide ni lire les `ReasoningChunk` ; hors intention de la story 19 (Discussion seule). Même règle que l'Arène : « non évalué : réponse vide ».
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/19-constats-recette-discussion-flux-e2e.md`
  summary: Relancer automatiquement, une fois, une génération interrompue (flux Ollama fermé sans fragment `done`).
  evidence: Story 19 : la réponse interrompue est signalée (« Réponse interrompue… ») et jamais présentée comme complète, mais l'utilisateur doit relancer lui-même. Reproduit 1 flux sur 8 le 29/09 (Ollama 0.34.2, gemma3:1b). Relance automatique hors intention.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/19-constats-recette-discussion-flux-e2e.md`
  summary: Les autres tests e2e qui génèrent (premier message du Chat libre, Arène avec juge) restent exposés au flux tronqué d'Ollama 0.34.2 (environ 1 sur 8) et échouent alors sur « Réponse interrompue ».
  evidence: Story 19, décision A : seul `_lab_run` (Banc d'essai) relance une fois un passage interrompu. L'Arène avec juge fait 3 générations ; même relance à ajouter, ou attendre une version d'Ollama corrigée.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/19-constats-recette-discussion-flux-e2e.md`
  summary: Une génération interrompue ne produit plus de métriques : son énergie (durée murale jusqu'à la coupure) n'entre plus dans le CO₂ de la session.
  evidence: `OllamaProvider.chat_stream` lève `InterruptedResponseError` sans produire `InferenceMetrics` ; générations coupées courtes (~150 ms observés le 29/09), biais faible mais réel pour un démonstrateur carbone.
