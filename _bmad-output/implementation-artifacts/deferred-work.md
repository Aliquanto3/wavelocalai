# Travail différé

- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md`
  summary: Les points d'entrée hors app (scripts/setup_rag_models.py, imports directs de crew_engine ou vector_store) n'appellent pas disable_telemetry().
  evidence: setup_rag_models.py importe huggingface_hub.snapshot_download sans couper la télémétrie Hugging Face ; seule l'app et eval_engine se protègent.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/12-souverainete-telemetries-co2-cloud.md`
  summary: Documenter dans README.md et AGENTS.md les télémétries coupées par défaut et la façon d'en réactiver une (variable dans l'environnement ou le .env).
  evidence: Rien n'indique à l'utilisateur que LANGSMITH_TRACING et les autres sont forcés ; la modification d'AGENTS.md est hors d'une story de code.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/14-couleur-primaire-sombre-lisible.md`
  summary: Classer le texte blanc sur primaryColor (boutons principaux, 4,26:1 en sombre) comme couleur du thème dans test_accessibility.py, pour qu'axe le fasse échouer s'il le relève hors de l'écart accepté.
  evidence: La liste explicite des écarts acceptés est faite (story 21, pastilles d'Agent_Lab à 4,24:1). Le blanc des boutons principaux n'est pas relevé : boutons dans des onglets masqués au moment de l'analyse, et le blanc n'est pas une couleur de [theme.dark], donc classé couleur native s'il l'était.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/18-constats-recette-arene-agents.md`
  summary: Gras affiché avec ses astérisques dans la réponse de l'agent seul (GPT-OSS 120B, recette C5 du 29/09), non reproduit.
  evidence: Réponse réelle capturée le 29/09 (`**Résultat :** 7 006 652`, `---`, italique) rendue correctement par st.markdown dans Chrome ; la sortie du modèle varie. maybe-false : à la prochaine occurrence, copier le texte brut de la réponse (ou une capture) pour trouver le motif fautif.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/21-suite-e2e-verte-reruns-serveur-ecarts-contraste-flux-tronque.md`
  summary: Les tests e2e de l'Assistant documentaire (Discussion, évaluation de la qualité) génèrent sans `h.generate` : depuis la story 24, l'app relance une fois, mais une double coupure d'Ollama fait encore échouer ces tests au lieu de les relancer.
  evidence: rag/chat.py et rag/eval.py passent par OllamaProvider, qui lève InterruptedResponseError sur un flux sans `done` ; test_documents.py n'a aucune relance. Relevé à la revue de la story 21.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/21-suite-e2e-verte-reruns-serveur-ecarts-contraste-flux-tronque.md`
  summary: `nav`, `click_tab` et les appels de `settle_after_action(until=…)` attendent encore un état du navigateur, pas le compteur d'exécutions du serveur (`wait_script_run`).
  evidence: Story 21 : seuls select_option, multiselect_add, multiselect_clear et generate emploient le compteur ; test_agents.py, test_documents.py et test_sobriety.py gardent des attentes côté navigateur.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/22-modeles-cloud-routes-bon-fournisseur.md`
  summary: Page Agents : le garde-fou mémoire (`ResourceManager.check_resources`) s'applique aussi à un modèle cloud (4 Go estimés par défaut) et peut libérer la mémoire d'Ollama ou bloquer la demande.
  evidence: solo.py appelle check_resources(selected_tag) avant le moteur ; estimate_model_ram renvoie 4,0 Go pour un tag absent de MODELS_DB. Antérieur à la story 22, relevé par la revue.
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/23-une-seule-regle-co2-origine-reelle-modele.md`
  summary: `MetricsService.calculate_carbon` (src/core/metrics_service.py) garde sa propre règle de CO₂, sans appelant dans les pages : la brancher sur `answer_carbon_mg` ou la supprimer, puis étendre la garde `test_only_the_core_calls_carbon_formulas` à tout `src/`.
  evidence: Relevé à la revue de la story 23 ; exporté par src/app/components/metrics_display.py, qu'aucune page n'appelle (params d'abord, taille devinée d'après le tag, booléen is_local).
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/24-reponse-interrompue-relance-co2-message.md`
  summary: Deux coupures de suite : le CO₂ des tentatives coupées n'est compté que dans le Chat libre (total de session), pas dans le Banc d'essai, l'Arène, la Discussion ni l'évaluation de l'Assistant documentaire.
  evidence: Ces onglets n'ont pas de total de session ; relevé à la revue de la story 24 (lab.py sort sur erreur, ligne d'Arène en échec sans CO₂, e.output_tokens jeté dans rag/chat.py et rag/eval.py).
- source_spec: `_bmad-output/specs/spec-fiabilisation-frontend/stories/24-reponse-interrompue-relance-co2-message.md`
  summary: Vérifier au navigateur (recette) que le texte partiel s'efface et que la relance est annoncée pendant la seconde tentative ; AppTest ne voit que l'état final. Les agents (`ChatOllama`) ne sont pas relancés.
  evidence: Story 24 : l'annonce est remplacée par la nouvelle réponse dans le Chat libre et le Banc d'essai ; relance des agents hors intention (flux LangChain, sans détection de coupure).
