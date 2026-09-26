# Audit du front Streamlit : pro-elitebook-x360

> **Date :** 2026-09-26
> **Machine :** `pro-elitebook-x360` (HP EliteBook x360 1030 G8, i5-1145G7, 16 Go, sans GPU dédié)
> **Code testé :** `src/` identique entre `e7412f0` et `master` `d954bd6`
> **Outil :** Playwright 1.63 piloté depuis Chrome, parcours rejouable dans [`e2e/`](e2e/)

## 1. Méthode

- **Mode local strict.** Le bouton « Autoriser les API Cloud » est désactivé dès l'accueil : aucun appel Mistral, OpenAI ou Anthropic n'est fait.
- **Petits modèles**, parce que la machine n'avait que **1,7 Go de RAM libre** (91 % occupée) :
  - Gemma 3 1B pour le chat, le labo, la RAG et le juge de l'Arena ;
  - Granite 4.0 350M comme second combattant de l'Arena ;
  - Qwen 3.5 2B pour l'agent Solo au premier passage, puis Qwen 3.5 0.8B quand le garde-fou RAM de l'app a bloqué le 2B (F-13).
- **Navigation par la barre latérale** pour garder la session Streamlit. Un `page.goto` en ouvre une nouvelle et perd `st.session_state`.
- **Contrôle d'erreurs à chaque étape :** recherche des exceptions Python et des `st.error` affichés, puis capture d'écran.
- **Vérification dans le code :** chaque défaut ci-dessous a été contrôlé dans le code, puis reproduit dans l'app quand c'était possible.
- **Aucune action destructive.** Le bouton « Tout supprimer (Reset) » de la RAG n'a pas été cliqué. Les 83 chunks indexés sont intacts.

## 2. Résultats par module

| Étape | Résultat | Observé |
|---|---|---|
| Accueil, passage en local | OK | « Confidentialité : 100 % Local », répercuté sur toutes les pages |
| Cockpit GreenOps | **Défaut** | Arrêt et reprise du suivi OK, mais valeur affichée ×1000 (F-01) |
| Chat libre | OK | « La capitale de la France est Paris », 1,3 t/s, 8,2 s, badge CO₂ affiché |
| Labo de tests | OK | 5,7 t/s, 5,7 s, 32 tokens, 4 métriques |
| Arena | OK | Verdict, graphique et copies en 3,5 min. Juge peu fiable (U-07) |
| Gestion des modèles | OK | Tableau et fenêtre d'installation |
| RAG, discussion | OK | Réponse avec 4 sources en 39 s |
| RAG, ajout de documents | **Défaut** | « Indexation terminée avec succès ! » mais toujours 83 chunks (F-03) |
| Agent Solo + outil Time | **Défaut** | L'outil est appelé et la réponse s'affiche, puis disparaît au rerun suivant (F-04). Le modèle choisi revient aussi à la valeur par défaut (F-12) |
| Agent Crew | Non lancé | L'app exige ~2,5 Go de RAM libre et la machine en avait 1,7. Le schéma d'équipe et l'avertissement s'affichent |
| RAG, Benchmark & Qualité | Non testé | Ragas 0.4.1 est installé. Le test a été écarté faute de RAM |

Temps de premier chargement : 26 s pour Inférence, 24 s pour RAG, 8 s pour Agent Lab (imports lourds), moins de 3 s ensuite.

### Parcours automatisé

Le script [`e2e/e2e.js`](e2e/e2e.js) a été rejoué après consolidation. Chaque étape vérifie le comportement attendu : un défaut connu fait donc échouer son étape avec un message explicite.

| Étape | Passage complet | Passage ciblé | Message |
|---|---|---|---|
| 0-accueil-local | OK | | |
| 1-socle | KO | | F-01 : UI "0.03332 kgCO₂" / CSV 0.0000333 kg |
| 2-chat, 3-lab | OK | | |
| 4-arena | OK (122 s) | | |
| 5-gestion-modeles, 6-rag-chat | OK | | |
| 7-rag-upload | KO | | F-03 : 83 chunks avant, 83 après l'indexation annoncée réussie |
| 8-agent-solo | Bloqué par le garde-fou RAM avec Qwen 3.5 2B | KO avec Qwen 3.5 0.8B | F-04 : seul le log de l'outil reste après le rerun |
| 9-crew-rendu | OK | | Avertissement RAM rapporté, non compté comme erreur |

Tant que les défauts ne sont pas corrigés, le script sort en KO (code 1) sur les étapes 1, 7 et 8. C'est l'état de référence attendu par l'entrée 01 du plan.

## 3. Défauts

Gravité : **haute** = résultat faux ou fonction annoncée absente ; **moyenne** = incohérence visible ou dette bloquante ; **basse** = cosmétique.

### F-01 : CO₂ de session affiché 1000 fois trop haut (haute)

- **Preuve :** à l'arrêt du suivi, l'écran affiche « 0.03328 kgCO₂ ». CodeCarbon a écrit `0.0000333` kg dans `data/logs/emissions.csv` pour la même session de 17,5 s.
- **Cause :** `GreenTracker.stop()` renvoie des **grammes** (`src/core/green_monitor.py:225-232`). `src/app/pages/01_Socle_Hardware.py:148-158` les stocke puis les affiche en **kg** ; l'équivalent en km de voiture (`get_co2_equivalencies`, l.55) est donc faux du même facteur.
- **Portée :** seul appelant touché. `src/app/tabs/agent/crew.py:439` convertit correctement en mg.

### F-02 : l'historique du Cockpit ne montre jamais les sessions de l'interface (moyenne)

- **Preuve :** le suivi écrit dans `data/logs/emissions.csv`. Le graphique lit `data/logs/emissions/emissions.csv` via `get_emissions_path()` (`src/core/config.py:35-36`), qui ne contient que 2 lignes de benchmark du 2026-09-25.
- **Détail :** il existe en fait trois fichiers `emissions.csv` sous `data/logs/`. Le tracker les écrit avec `output_dir=str(LOGS_DIR)` (`green_monitor.py:202-204`).

### F-03 : l'ajout de documents RAG n'indexe rien (haute)

- **Preuve :** après upload de `e2e/sample_doc.md` puis « Indexer maintenant », le message de succès s'affiche, mais le compteur reste à 83 chunks.
- **Cause :** `src/app/pages/03_RAG_Knowledge.py:101-113` ne fait qu'un `time.sleep(0.5)` par fichier, et l'appel d'ingestion est commenté. `RAGEngine.ingest_file(path, name)` existe mais n'est jamais appelé. Les fichiers ne sont jamais écrits sur disque.
- **Conséquence :** sur une base vide, les onglets Discussion et Benchmark ne sont pas atteignables depuis l'interface.

### F-04 : la réponse finale de l'agent Solo est perdue (haute)

- **Preuve :** « Il est actuellement 22:31:39 le 26 septembre 2026. » s'affiche. Après un aller-retour sur le choix d'architecture, il ne reste que la question et le log de l'outil.
- **Cause :** dans `src/app/tabs/agent/solo.py:292-309`, la réponse est affichée mais jamais ajoutée à `agent_messages`. La ligne 309 est un commentaire resté à la place du code : `# ... (Carbon Calc et st.rerun inchangés) ...`.
- **Conséquence :** pas de calcul CO₂, et le badge `carbon_mg` (l.198) ne s'affiche jamais.

### F-05 : l'app est exposée sur le réseau (haute)

- **Preuve :** au lancement, Streamlit annonce une « Network URL » (192.168.x) et une « External URL » (IP publique). Il n'existe aucun `.streamlit/config.toml`, donc le serveur écoute sur toutes les interfaces.
- **Pourquoi c'est grave :** c'est contradictoire avec la promesse affichée « Aucune donnée ne sort ». N'importe qui sur le même réseau peut interroger la RAG et les agents, qui ont des outils d'envoi d'e-mail et d'accès aux fichiers.

### F-06 : le reranker choisi est ignoré (moyenne)

`03_RAG_Knowledge.py:183-201` : la liste « Modèle » du reranker est affichée, mais la sélection n'est appliquée nulle part (« Reranker change logic would go here »).

### F-07 : un modèle cloud est proposé par défaut (moyenne)

- **Preuve :** avec le cloud activé, le chat et la RAG présélectionnent « Claude-3-5-haiku-20241022 ».
- **Cause :** la liste est triée sur le libellé affiché, et « ☁️ » (U+2601) passe avant « 💻 » (U+1F4BB) (`02_Inference_Arena.py:69,92`). Le défaut devrait être un modèle local.

### F-08 : indicateurs écrits en dur (basse)

- « Système : Opérationnel 🟢 » est écrit en dur (`Accueil.py:88`) et tronqué à l'écran.
- « Accélérateur AI : Actif » s'affiche même en CPU seul (`01_Socle_Hardware.py:121`).
- Le pied de page affiche « © 2025 … v2.0.0 (Stable) » (`Accueil.py:167`).

### F-09 : l'Arena accepte de lancer un combat avec un seul modèle (basse)

`src/app/tabs/inference/arena.py:177-185` : le bouton n'est désactivé qu'avec zéro modèle, alors que la légende en demande au moins 2.

### F-10 : `use_container_width` déprécié, 32 occurrences (moyenne)

Les logs Streamlit répètent : « `use_container_width` will be removed after 2025-12-31 ». Une montée de version de Streamlit cassera ces appels. Le remplacement est `width="stretch"` / `width="content"`.

### F-11 : puissance CPU de CodeCarbon suspecte, à investiguer (moyenne)

- **Preuve :** toutes les lignes CodeCarbon de cette machine indiquent `cpu_power = 112.0` W, constant. L'i5-1145G7 est un processeur de 28 W.
- `docs/METHODOLOGIE_CARBONE.md` annonce une mesure par « Sondes Intel RAPL ». Une valeur constante évoque plutôt une estimation par défaut.
- **Cause non établie.** Si l'hypothèse se confirme, les mesures carbone locales seraient surestimées sur cette machine.

### F-12 : l'agent Solo oublie le modèle choisi (basse)

- **Preuve :** avec Qwen 3.5 0.8B sélectionné, un aller-retour Solo → Crew → Solo ramène la liste sur « Bonsai 8B (1-bit) », le premier de la liste.
- **Cause :** `src/app/tabs/agent/solo.py:95` crée la liste sans `key` ni valeur persistée dans `st.session_state`. Streamlit abandonne l'état d'un widget qui n'est pas affiché pendant un rerun.

### F-13 : quand le garde-fou RAM bloque, la question est perdue (basse)

- **Preuve :** avec Qwen 3.5 2B, l'agent refuse de démarrer : « ⛔ RAM Insuffisante ! Risque de crash. Besoin: 3.70GB. Dispo réelle: 2.82GB ». Le champ de saisie est vidé, la question n'entre pas dans l'historique, et le message est un simple `st.warning`.
- **Problèmes :**
  - l'utilisateur doit retaper sa demande ;
  - le besoin estimé (3,7 Go) dépasse nettement la taille du modèle sur disque (2,7 Go) : l'estimation mérite d'être expliquée dans l'interface ;
  - le même agent avait tourné une demi-heure plus tôt avec 1,7 Go libres, sans doute parce que le modèle était déjà chargé dans Ollama. Le garde-fou ne semble donc pas en tenir compte, mais ce point n'est pas vérifié.

## 4. Lisibilité et esthétique

- **U-01 : pas de thème.** Sans `.streamlit/config.toml`, l'app garde le rouge Streamlit par défaut. Les actions principales (« Gérer les Documents », « FIGHT ! ») et les pastilles d'outils de l'Agent Lab ressemblent à des erreurs. Proposition : thème au violet Wavestone `#451DC7`, et `client.toolbarMode = "minimal"` pour masquer « Deploy ».
- **U-02 : trois noms pour un même module.** La barre latérale affiche les noms de fichiers (« Socle Hardware », « RAG Knowledge »). Les cartes de l'accueil disent « Cockpit GreenOps », « Base de Connaissance », et les titres « Assistant Documentaire ». Proposition : `st.navigation` / `st.Page` avec un titre et une icône par module.
- **U-03 : emojis dans tous les titres.** Inférence et RAG partagent le même 🧠. Proposition : icônes `:material/…:`, et un seul pictogramme par module, repris partout.
- **U-04 : le bouton cloud existe 4 fois, avec 2 libellés** (`Accueil.py:156`, `02:36`, `03:138`, `04:36`). Proposition : un seul contrôle global, avec l'état (Local / Hybride) toujours visible.
- **U-05 : CSS injecté en dur.** 16 `unsafe_allow_html`, dont un fond sombre `#262730` pour l'écran vide de la RAG (`03_RAG_Knowledge.py:43`), qui détonne avec le thème clair.
- **U-06 : la page Arena déborde.**
  - Les noms de modèles sont tronqués dans le multiselect (« Granite 4.0 3… »).
  - L'étiquette du point du haut sort du graphique.
  - L'axe des vitesses est resserré sur 5,8 à 6 t/s, ce qui exagère un écart négligeable.
- **U-07 : juge trop faible dans l'Arena.** Gemma 3 1B a noté 90/100 les deux copies, y compris celle de Granite 350M, qui répète la même phrase en boucle. Proposition : avertir quand le juge fait moins de ~4B paramètres, proposer par défaut le plus gros modèle local, et comparer les deux copies côte à côte plutôt que les noter séparément.
- **U-08 : premier chargement lent sans retour visuel.** Proposition : un `st.spinner` explicite pendant les imports lourds, ou un préchargement depuis l'accueil.

## 5. Fonctionnalités proposées

- **N-01 : page « Résultats de benchmark ».** Le repo contient les résultats multi-machines (`benchmarks/results/*.json`, PR #5 à #13), mais l'interface ne les montre nulle part. Proposition : une comparaison machine × modèle (t/s, gCO₂ pour 1 000 tokens, qualité) avec les profils matériels. C'est la démonstration la plus directe de la thèse « un SLM utile sur un poste bureautique ».
- **N-02 : « Ce modèle tient-il sur ce PC ? ».** Dans Gestion des modèles, signaler les modèles qui dépassent la RAM libre, comme pendant ce test.
- **N-03 : export de session.** Un rapport Markdown ou PDF (questions, modèles, t/s, CO₂) à laisser au client après une démo.
- **N-04 : parcours e2e en non-régression.** Intégrer [`e2e/`](e2e/) au repo (lancement manuel ou CI locale), avec une collection Chroma de test pour ne pas toucher aux données réelles.

## 6. Limites de cet audit

- Tout a été testé en local strict : les chemins cloud (Mistral, OpenAI, Anthropic) n'ont pas été exercés.
- La RAM était trop juste pour Crew, pour le benchmark Ragas et pour des modèles de plus de 2B : ces chemins restent à tester sur une machine mieux dotée.
- Les temps et débits sont indicatifs. Ils ont été mesurés sur une machine chargée à 91 % de RAM, et ne sont pas comparables aux campagnes de `benchmarks/`.

## 7. Fusion avec les autres audits

Pour combiner ce rapport avec celui d'une autre machine :

1. Rapprocher les constats par leur identifiant quand ils décrivent la même cause (même fichier et même ligne), et non par leur libellé.
2. Un défaut vu sur les deux machines garde sa gravité. S'il n'est vu que sur une, noter sur quel matériel.
3. Garder les preuves des deux côtés : captures, valeurs relevées, numéros de ligne.
4. Le plan [`plan-bmad.md`](plan-bmad.md) référence ces identifiants dans ses `covers:`. Après la fusion, il suffit de renuméroter les exigences une seule fois.
