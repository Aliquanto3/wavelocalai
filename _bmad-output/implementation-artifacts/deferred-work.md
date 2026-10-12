# Travail différé

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
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/1-socle-quality-bench-client-ollama-jsonl-reprenable.md`
  summary: Lancer `tests/quality_bench` en CI (job qui installe `scripts/quality_bench/requirements.txt`, sous Windows et Linux) : aujourd'hui la suite ne tourne qu'à la main dans `.venv-quality`, et la branche `fcntl` des verrous n'est jamais exécutée.
  evidence: `.github/workflows/tests.yml` tourne sur les PR vers `master` mais ne lance que `tests/unit tests/app` ; le spine du banc range la CI hors périmètre et la SPEC exclut toute autre machine que la tour. Décision à prendre par Anaël. Relevé à la revue de la story 1.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/1-socle-quality-bench-client-ollama-jsonl-reprenable.md`
  summary: Corriger l'écueil d'AGENTS.md « la CI ne se déclenche que sur main et develop » : elle se déclenche sur push et PR vers `master`.
  evidence: `.github/workflows/tests.yml:3-7` (branches `[ master ]`) depuis le commit 8dfc946 ; fichier de contexte d'agent, hors du diff de la story. Relevé à la revue de la story 1.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/1-socle-quality-bench-client-ollama-jsonl-reprenable.md`
  summary: Story 5 (runner) : un `OllamaUnavailableError` que `/api/version` ne confirme pas (délai de lecture dépassé ou 5xx propre à la requête, service vivant) doit compter dans `max_attempts`, sinon la même question est rejouée sans borne.
  evidence: maybe-false, medium si vrai. Le client classe `ReadTimeout`, la coupure avant `done` et tout 5xx en panne de service (Design Notes de la story 1) ; `wait_for_ollama` rend alors la main aussitôt. Le dommage dépend de la politique du runner : à trancher dans la spec de la story 5.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/2-schema-question-import-jeux-publics-telechargements.md`
  summary: Contexte des questions multi-tours (bfcl-multi) : la règle d'AD-5 (`num_ctx ≥ est × 1,25 + plafond`) ignore l'historique des tours ; 89 conversations sont à 8192 et 111 à 16384 pour jusqu'à 7 tours.
  evidence: `base.choose_num_ctx` ; le runner (AD-7) écrira `context_exceeded` plutôt que de tronquer, mais une part de bfcl-multi risque de sortir des comparaisons. Règle multi-tours à trancher dans le spine, puis appliquée par set_builder (story 3) ou mesurée au pilote. Relevé à la revue de la story 2 (medium).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/2-schema-question-import-jeux-publics-telechargements.md`
  summary: Lancer `python -m pytest tests/unit` en entier (4 échecs préexistants attendus) sur une machine dotée d'un venv d'app, pour confirmer l'ajout de `datasets` à `TELEMETRY_ROOTS` et de `remote.py` à `TELEMETRY_IMPORTERS`.
  evidence: La tour n'a pas de venv d'app : seuls `tests/quality_bench` et `tests/unit/test_telemetry.py -k "every_telemetry_importer or precedes_library_import"` ont tourné dans `.venv-quality` (8 passés).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/2-schema-question-import-jeux-publics-telechargements.md`
  summary: Story 3 : télécharger avant campagne les fichiers bruts de OneRuler FR (livre, vocabulaire, gabarits) par le mécanisme épinglé de la story 2 (`RemoteFile`, empreintes, `machine.lock`).
  evidence: `mungg/OneRuler` @ `a3fe6af862dc4b30794afc0a8f3d4f60758cecfa` (`data/books/fr/les_miserables_fr.txt`, `data/prompt/fr/{niah,cwe}.txt`, `data/vocab/100_noun_list_translated.tsv`, `data/vocab/dictionaries/French/French.csv`). Code MIT ; aucune licence ni provenance déclarée pour le texte et les dictionnaires ; `niah.py` appelle `stanza.download` (réseau).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/3-generateurs-graine-questions-privees-construction-jeu.md`
  summary: Versionner la provenance d'un jeu (empreinte AD-4, graine, empreintes des fichiers d'entrée, commit) : aujourd'hui elle ne vit que dans `sets/log-build-set.log`, hors dépôt.
  evidence: `index.jsonl` ne porte que des lignes `qb.set_index/1` ; AD-6 n'admet aucun autre fichier sous `benchmarks/quality/sets/<set>/`. Amender AD-6 (manifeste de jeu en liste blanche), ou s'appuyer sur le manifeste de génération (story 5). Relevé à la revue de la story 3 (medium).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/3-generateurs-graine-questions-privees-construction-jeu.md`
  summary: Story 4 : vérifier que les identifiants et les kwargs M-IFEval FR des questions privées `instructions-fr` existent dans le registre réduit copié.
  evidence: `house.py` ne contrôle que le préfixe `fr:`, l'unicité et l'alignement des kwargs ; le registre n'existe pas encore. Relevé à la revue de la story 3 (low).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/3-generateurs-graine-questions-privees-construction-jeu.md`
  summary: 87 des 418 critères de `writing-fr.yaml` demandent au juge de compter (mots, phrases, paragraphes, répliques) : les réécrire, les corriger de façon déterministe ou mesurer leur accord à part.
  evidence: Les juges LLM comptent mal. À trancher à la relecture d'Anaël ou à la calibration (story 9). Relevé à la revue de la story 3 (medium).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/4-correcteurs-deterministes-environnements-outils-phase-grade.md`
  summary: Story 5 (runner) : fixer le contrat des outils à un seul tour (`bfcl-live`, `bfcl-parallel`, `bfcl-irrelevance`, `tools-fr`, `env` nul) ; `bfcl_ast` réunit aujourd'hui tous les pas du tour 0, alors que BFCL ne décode que la première réponse.
  evidence: maybe-false, medium si vrai. Si le runner renvoie un contenu d'outil factice et que le modèle rappelle un outil, `bfcl_ast` compterait deux appels. Trancher dans la spec de la story 5 (arrêt après la première réponse) ou limiter le correcteur au premier pas. Relevé à la revue de la story 4.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/4-correcteurs-deterministes-environnements-outils-phase-grade.md`
  summary: Décider si `conformity_error` doit vérifier les mots-clés `format` (date-time, email, uri…) des schémas JSONSchemaBench, aujourd'hui de simples annotations.
  evidence: maybe-false, medium si vrai. Lire le validateur du dépôt JSONSchemaBench (epfl-dlab) ; s'il active les formats, passer un `FormatChecker` et le consigner dans `SOURCES.md`. Relevé à la revue de la story 4.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/4-correcteurs-deterministes-environnements-outils-phase-grade.md`
  summary: Exclure de `set-v1`, avant de le figer, 5 cibles `bfcl-live` défectueuses dans BFCL lui-même (aucune réponse ne peut les passer).
  evidence: Exécution réelle : 1 306/1 311 cibles passent comme réponse du modèle ; `live_simple_106-63-0`, `live_simple_112-68-0`, `live_multiple_507-149-4`, `live_multiple_862-181-3`, `live_multiple_964-207-0` échouent aussi avec le correcteur amont (paramètre requis sans valeur possible, ou paramètre non déclaré).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/4-correcteurs-deterministes-environnements-outils-phase-grade.md`
  summary: `tools-fr` : 3 valeurs attendues (3 questions sur 30) présentes dans le prompt anglais d'origine mais plus dans la traduction (type « Californie » → CA) ; garder la valeur littérale ou accepter la difficulté, à la relecture d'Anaël.
  evidence: Mesure locale, comptes seulement : 63 paramètres chaîne attendus, 3 dont aucune valeur admise n'apparaît dans le prompt FR normalisé à la manière de BFCL. Les identifiants M-IFEval FR des 30 questions `instructions-fr` existent tous dans le registre réduit (report de la story 3 levé).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/5-generation-deux-pistes.md`
  summary: Borner les reprises non comptées par clé si le pilote montre qu'une question (ou une chauffe) fait tomber le serveur Ollama entier, relancé aussitôt : aujourd'hui la question est refaite sans fin.
  evidence: maybe-false, medium si vrai. Après un `OllamaUnavailableError` dont la sonde `/api/version` échoue, `Runner._process` et `Runner._ensure_warm` attendent puis refont sans compter l'essai (AD-13). Un plantage du runner llama rend un 5xx service vivant (essai compté) : la boucle n'existe que si le serveur entier tombe à chaque essai. À observer au pilote (story 8), puis amender AD-13 s'il le faut. Relevé à la revue de la story 5.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/5-generation-deux-pistes.md`
  summary: Confronter au vrai Ollama 0.40.2 les comportements figés dans `tests/quality_bench/ollama_fake.py` : `remote_host` (tags, show), capacités et `model_info.<arch>.context_length`, `size`/`size_vram` de `/api/ps`, `prompt_eval_cached_count`, `done_reason: "length"`, déchargement par `/api/generate` `keep_alive: 0`.
  evidence: maybe-false, medium si vrai. Aucune génération réelle n'a tourné (story 5 testée sur MockTransport seulement). À vérifier en interactif sur la tour au pilote (story 8) : préflight des 4 modèles, une chauffe, quelques questions, puis lecture de `manifest.json`, `warmups.jsonl` et `generation.jsonl`. Relevé à la revue de la story 5.
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/6-statistiques-rapport.md`
  summary: Rapport : meneur, rang approché, groupes et Spearman reposent sur la moyenne de chaque modèle sur ses seules unités définies ; un modèle privé des unités les plus dures (`context_exceeded` aux grands paliers) est noté sur un sous-ensemble plus facile.
  evidence: Règle d'AD-10 (unités nulles retirées des comparaisons du modèle, compte publié) ; les tests appariés sont justes, mais `leader_order`, `approximate_ranks` et `_spearman` comparent des moyennes non appariées. À trancher au pilote (story 8) avec les `context_exceeded` réels : meneur sur les unités communes, seuil d'exclusion ou avertissement (amendement d'AD-10 ou d'AD-17). Relevé à la revue de la story 6 (medium).
- source_spec: `_bmad-output/specs/spec-benchmark-qualite-difficile/stories/6-statistiques-rapport.md`
  summary: Fournir le fichier d'indices Artificial Analysis `benchmarks/quality/references/aa-<AAAA-MM-JJ>.json` (`qb.aa_reference/1`, tags Ollama de la campagne, `measured`/`estimated`, `reasoning`/`non_reasoning`) avant le rapport final (story 10) ; jamais récupéré en ligne par le banc.
  evidence: Aucun fichier réel n'existe : le rapport et ses tests ne s'appuient que sur des fixtures synthétiques ; sans fichier, la section Spearman est marquée « indice AA absent ». Format dans `scripts/quality_bench/questions/SOURCES.md` (section « Rapport »). À fournir par Anaël.
