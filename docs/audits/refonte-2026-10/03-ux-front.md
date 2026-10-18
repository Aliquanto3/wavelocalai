# Audit UX et conception du front web de la v2

- **Date :** 2026-10-18
- **Périmètre :** UX et front. La performance mesurée et l'API back font l'objet de deux autres rapports de la même série.
- **Sources lues :** `src/app/` (v1, branche `fix/anthropic-chat-temperature`, `5b5e2d1`), `docs/audits/frontend-2026-09/SYNTHESE.md` (D1 à D7), `_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/{DESIGN,EXPERIENCE}.md`, `_bmad-output/specs/spec-fiabilisation-frontend/`, captures de `docs/assets/` et des audits de septembre, front du harnais `agentic-harness-training-demo/src/wavestack/web` et son `ARCHITECTURE-SPINE.md` (AD-1, AD-3, AD-18, AD-28).
- **Méthode :** lecture du code et des captures. L'application n'a pas été lancée (Ollama arrêté exprès).
- **Hors de portée :** le dépôt `wavelocalai-v2` n'existe pas sur ce poste. Ce rapport décrit donc le front cible sans l'adosser à un code v2 existant.

## Résumé

1. La v1 a gagné en justesse depuis septembre : charte, lexique, badges Local et Cloud, états d'erreur, débit D3. Ses irritants restants viennent surtout de Streamlit : chaque clic relance toute la page, tous les onglets s'exécutent à chaque fois, et les résultats d'une action disparaissent au clic suivant.
2. Le front du harnais est un bon modèle : HTML, CSS et JavaScript en modules natifs, sans compilation ni Node, servis par FastAPI, avec un flux SSE rejouable, des jetons de design vérifiés par un test, une i18n et un thème sans dépendance. On reprend ses **patterns** et ses petits modules. On ne reprend pas ses gros fichiers (`app.js` fait 7 659 lignes), ni ses écarts à la charte (emoji dans la navigation, pas d'icônes Material).
3. Recommandation : **une coquille unique en modules natifs sans compilation**, avec un routeur côté client et des écrans chargés à la demande. Le streaming passe par une exécution côté serveur (`run`) et un flux SSE par exécution, rejouable.
4. MVP en trois lots : socle, Chat et Arène, Assistant documentaire. Ensuite : Sobriété et modèles, Agents, Évaluation, puis finition.

---

## 1. Inventaire des parcours et écrans de la v1

### 1.1 Carte des écrans

| Page (nom unique) | Onglets ou modes | But utilisateur | Fichiers |
|---|---|---|---|
| Accueil | — | Savoir si le système marche, en Local ou en Cloud, et aller à la démo | `src/app/Accueil.py` (routeur), `src/app/home.py` |
| Arène des modèles | Chat libre · Banc d'essai · Arène · Gestion des modèles | Converser, tester un scénario, comparer, installer | `views/02_Inference_Arena.py`, `tabs/inference/{chat,lab,arena,manager}.py` |
| Assistant documentaire | Discussion · Évaluation de la qualité, plus le dialogue « Gérer la base documentaire » | Interroger ses documents et voir les sources ; comparer des modèles sur le RAG | `views/03_RAG_Knowledge.py`, `tabs/rag/{chat,eval}.py`, `rag_upload.py`, `rag_clear.py` |
| Agents autonomes | Agent seul · Équipe d'agents (choix dans la barre latérale) | Confier une tâche outillée | `views/04_Agent_Lab.py`, `tabs/agent/{solo,crew}.py` |
| Sobriété et matériel | Santé du système · Empreinte carbone · Carte d'identité technique | Voir la machine, sa charge et le CO₂ mesuré | `views/01_Socle_Hardware.py`, `charts.py` |

Commun à toutes les pages : barre latérale avec le wordmark et la bascule « Autoriser le cloud » (`Accueil.py:76-80`), alerte « Ollama ne répond pas » en tête de module (`Accueil.py:85-86`), suivi CodeCarbon de session lancé par le routeur (`Accueil.py:64-67`).

### 1.2 Écran par écran

Légende des états : V = vide, C = chargement, E = erreur, O = Ollama absent, Cl = cloud.

#### Accueil

| Élément | Constat |
|---|---|
| Composants | Titre, accroche, quatre `metric` (Système, Mode, Processeur, Mémoire), carte « Démo recommandée », trois cartes de modules, pied de page (`home.py:188-248`) |
| États | O : « Indisponible » (`home.py:212`). Cl : badge Cloud. C : aucun indicateur, `psutil.cpu_percent(interval=0.1)` bloque 100 ms à chaque affichage (`home.py:174`) |
| Irritants | Processeur et mémoire figés à l'ouverture, sans mise à jour. L'accueil ne dit pas quels modèles sont installés ni lequel sera utilisé par défaut. Aucun lien direct vers l'action principale (« Lancer une comparaison ») : il faut ouvrir la page puis l'onglet |
| Limite Streamlit | Une métrique vivante exigerait `st.fragment(run_every=…)`, qui relance quand même du Python côté serveur |

#### Arène des modèles, onglet Chat libre

| Élément | Constat |
|---|---|
| Composants | Bandeau (sélecteur, curseur « Créativité », CO₂ de session, « Effacer »), `chat_message`, `chat_input`, statut de premier chargement, pied de réponse (badge, CO₂, débit, chargement, durée) (`tabs/inference/chat.py:188-358`) |
| États | V : titre centré. C : `st.status` « Chargement du modèle en mémoire… » (`chat.py:268`). E : alerte avec détail replié, tour gardé (`chat.py:302-324`). O : liste vide sans explication propre à l'onglet (`render_no_models` se tait si Ollama est absent, `states.py:253`) |
| Irritants | **Modèle d'embedding présélectionné** : aucun filtre par type dans la liste (`ui.py:473-517`, `model_defaults.py:424`). Le plus petit modèle installé, souvent `nomic-embed-text`, passe en tête. Correctif en cours sur la branche `fix/modeles-embedding-ollama-absent` (`e784e0f`). Le sélecteur n'a pas de `key` (`chat.py:193`) : le choix est perdu quand la liste change, par exemple à la bascule cloud. Aucun bouton « Arrêter » pendant la génération. `time.sleep(0.1)` puis `st.rerun()` après chaque réponse (`chat.py:357-358`) : la page entière se redessine, onglets compris. Le curseur « Créativité » a un libellé masqué, et sa valeur ne se lit pas sans survol |
| Limite Streamlit | Le streaming réécrit un `st.empty()` en Markdown à chaque token (`chat.py:276`) et bloque le script. Pendant ce temps, tout autre clic interrompt la génération. Pas d'annulation propre, pas de génération qui continue quand on change d'onglet |

#### Arène des modèles, onglet Banc d'essai

| Élément | Constat |
|---|---|
| Composants | Scénarios prédéfinis (`USE_CASES`, `lab.py:30`), un modèle, une réponse mesurée |
| États | Résultat conservé (`lab.py:218-237`) : c'est le seul onglet de l'Arène qui garde son résultat |
| Irritants | Les invites des scénarios (`lab.py:31-40`) mêlent consignes et format JSON, sans validation du JSON renvoyé : on ne voit pas si le modèle a respecté le format, alors que c'est le sujet du banc |

#### Arène des modèles, onglet Arène (démo recommandée)

| Élément | Constat |
|---|---|
| Composants | Multisélection des modèles, expander « Réglages du juge » (sélecteur et invite brute), question, « Lancer la comparaison », `st.status` avec barre de progression, podium, matrice Plotly qualité, débit et CO₂, tableau, réponses (`tabs/inference/arena.py:505-779`) |
| États | Moins de deux modèles : bouton désactivé avec une légende. E : la ligne dit « Délai dépassé », les autres continuent (`arena.py:623-645`). « non évalué » géré. Cl : badge par ligne |
| Irritants | **Pas de streaming** : les réponses n'apparaissent qu'à la fin de tous les modèles (`arena.py:615-620`, sans `on_token`). Pour 3 modèles locaux, la salle regarde une barre de progression pendant 30 à 90 s. **Résultats non conservés** : tout est rendu dans le `if start_btn` (`arena.py:593`), donc le premier clic suivant (déplier une réponse, changer d'onglet) efface la comparaison. Le juge s'édite en invite brute (`arena.py:552-560`). Pas d'affichage côte à côte au-delà de 2 modèles (`arena.py:762-779`). CO₂ « — » pour les modèles Claude (taille inconnue, `src/core/answer_carbon.py:31-33`) |
| Limite Streamlit | Exécution séquentielle dans le script. Impossible d'afficher N colonnes vivantes qui se remplissent pendant que l'utilisateur fait défiler ou déplie quelque chose |

#### Arène des modèles, onglet Gestion des modèles

| Élément | Constat |
|---|---|
| Composants | Tableau des modèles, « Rafraîchir », dialogue « Ajouter un modèle » avec un sélecteur et un tag libre, `st.status` d'installation (`tabs/inference/manager.py:36-275`) |
| Irritants | La progression de `pull` n'est pas chiffrée en continu. Aucune compatibilité mémoire affichée avant l'installation (elite:N-02, déjà repéré en septembre). Aucune suppression de modèle. L'onglet est calculé à chaque rerun de la page, même quand on discute dans le chat (`02_Inference_Arena.py:43-81`) |

#### Assistant documentaire, base, Discussion et Évaluation

| Élément | Constat |
|---|---|
| Composants | Barre latérale (« Gérer la base documentaire », résumé, « Réglages avancés » : embedding, stratégie, nombre d'extraits, reranker), état vide en carte, dialogue d'import, onglets Discussion et Évaluation (`views/03_RAG_Knowledge.py`) |
| États | V : carte « Votre base documentaire est vide » et trois encarts (`03_RAG_Knowledge.py:316-335`). C : spinner « Démarrage de l'assistant documentaire… » qui bloque la page entière au premier passage (`:97-116`). E : erreurs d'ingestion par fichier (`:297-306`). O : la page attend `LLMProvider.list_models` |
| Irritants | **Dialogue d'import qui ne s'ouvre pas tout de suite** : `st.dialog` est un appel de fonction exécuté pendant le script (`:131`, `:200`, `:321`). Il ne s'ouvre qu'une fois le script arrivé à cet endroit, après l'initialisation lourde de `RAGEngine` et d'`EvalEngine` (`:97-124`, Ragas importé même si on n'évalue jamais). Sources tronquées à 400 caractères, avec un « score de reclassement » brut (un logit, parfois négatif) en guise de pertinence (`tabs/rag/chat.py:106-115`). Aucun renvoi de la réponse vers la source (pas de [1], [2]). Les sources sont sous la réponse, dans un expander : la capture `docs/assets/rag.png` (ancienne version) les montrait en colonne à droite, une disposition plus lisible. Le résultat de l'évaluation n'est pas conservé (`tabs/rag/eval.py:273`) |
| Limite Streamlit | Pas d'upload avec progression par fichier. Le dialogue ne peut pas s'ouvrir côté navigateur sans aller-retour serveur |

#### Agents autonomes, Agent seul et Équipe d'agents

| Élément | Constat |
|---|---|
| Composants | Mode en radio latérale, « Santé du système » (mémoire), « Libérer la mémoire », « Effacer la conversation » (`views/04_Agent_Lab.py:36-97`) ; Agent seul : sélecteur, pastilles d'outils, scénarios en dialogue, flux d'événements `tool_call`, `tool_result` et `final_answer` (`tabs/agent/solo.py:529-600`), dialogue de confirmation d'email (`solo.py:264`) ; Équipe : configuration en onglets par agent, schéma Graphviz, lancement, journal stdout (`tabs/agent/crew.py`) |
| États | Garde-fou mémoire, email à valider (D2), « Bonjour ! » |
| Irritants | « Libérer la mémoire » importe `torch` et vide le cache CUDA (`04_Agent_Lab.py:73-87`) : sans effet sur Ollama, donc trompeur. Le budget carbone « gamifié » (`04_Agent_Lab.py:28-29`, `crew.py:522-524`) n'est affiché nulle part. Équipe : la trace est la sortie standard brute de CrewAI dans un expander (`crew.py:488-491`), sans étapes structurées ni agent courant. Le rapport n'est pas conservé (`crew.py:480`) et l'exécution ne s'arrête pas. Un agent seul montre ses outils, mais la réponse finale n'arrive pas en flux |
| Limite Streamlit | `redirect_stdout` et un thread de mesure dans le script. Une trace interactive (déplier une étape pendant que les suivantes arrivent) est impossible |

#### Sobriété et matériel

| Élément | Constat |
|---|---|
| Composants | Quatre `metric`, session CodeCarbon (arrêter et enregistrer), historique en barres Plotly, carte d'identité repliée, « Rafraîchir » (`views/01_Socle_Hardware.py`) |
| Irritants | Pas de mise à jour en direct : il faut cliquer sur « Rafraîchir » (`:301`). Le CO₂ de la session ne se relie pas aux réponses qui l'ont produit. Pas de ventilation par module, ni Local contre Cloud |

### 1.3 Irritants transverses

| ID | Irritant | Preuve | Gravité |
|---|---|---|---|
| T1 | Rerun complet à chaque interaction, tous les onglets exécutés | `02_Inference_Arena.py:43-81`, `03_RAG_Knowledge.py:349-369` ; un seul `st.cache_data` dans toute l'app (`states.py:107`), aucun `st.fragment` | majeur |
| T2 | Les résultats d'action disparaissent au clic suivant | Arène `arena.py:593`, Évaluation `eval.py:273`, Équipe `crew.py:480` | majeur |
| T3 | Page bloquée quand Ollama est arrêté, même en cloud | `ollama_provider.py:68` (`list()` sans délai) ; l'état « indisponible » n'est jamais mis en cache et se réinterroge à chaque rerun (`states.py:107-119`) ; `available_memory_gb` appelle `ps()` (`ui.py:405-408`). Correctif en cours : `93c5791` | majeur |
| T4 | Modèle d'embedding proposé pour converser | `ui.py:473`, `model_defaults.py:424`. Correctif en cours : `e784e0f` | majeur |
| T5 | Sélecteurs virtualisés difficiles à parcourir | `st.selectbox` et `st.multiselect` partout : pas de groupes, pas de filtres, pas de colonnes (taille, débit mesuré) | moyen |
| T6 | Bascule « Autoriser le cloud » perdue au rechargement | `Accueil.py:76-77` | voulu (D1) : à garder, mais à **dire** à l'utilisateur |
| T7 | CO₂ « — » pour les modèles cloud de taille inconnue | `answer_carbon.py:31-33`, `chat.py:131-143` | moyen : un tiret seul ne dit pas pourquoi |
| T8 | Aucune annulation d'une génération, d'une comparaison ou d'une mission | tous les onglets | moyen |
| T9 | Composants morts | `src/app/components/{chat_message,metrics_display,model_selector,source_expander}.py` ne sont importés par aucune page | mineur |
| T10 | Captures du README obsolètes (anciens noms, emojis, « Deploy ») | `docs/assets/*.png` | mineur, mais c'est la vitrine publique |

### 1.4 Ce que Streamlit empêche de bien faire

| Besoin | Pourquoi Streamlit bloque |
|---|---|
| Interface réactive | Modèle « script relancé de haut en bas » : chaque clic coûte un aller-retour et le recalcul de la page |
| Plusieurs flux en parallèle (Arène) | Un script ne peut écrire que dans un ordre séquentiel ; pas de rendu concurrent |
| Exécution qui survit à la navigation | Changer de page interrompt le script et la génération |
| Annuler | Pas de primitive ; un clic relance le script et coupe le flux de façon brutale |
| Dialogue ou panneau immédiat | `st.dialog` s'ouvre côté serveur, à l'endroit du script |
| Sélecteur riche (groupes, facettes, colonnes) | Pas de composant natif ; un composant personnalisé demande une chaîne Node |
| Accessibilité fine | `region` et `aria-allowed-attr` sont déjà exclus des contrôles faute de pouvoir les corriger (EXPERIENCE.md, Accessibility Floor) ; pas de contrôle des `aria-live` |
| Mise en page de démonstration | Pas de mode projection, pas de mise en page par volets |

---

## 2. Le front de référence : harnais `agentic-harness-training-demo`

### 2.1 Ce qu'il est

| Axe | Constat | Source |
|---|---|---|
| Stack | HTML, CSS et JS en modules ES natifs, **sans compilation, sans Node, sans CDN**. FastAPI sert les pages (`FileResponse`), `/static` et l'API | AD-18 ; `web/app.py:460-495` |
| Pages | Multi-pages : `/`, `/llm`, `/rag`, `/mcp`, `/security`, `/diagnostic`, chacune avec son HTML, son CSS et son JS | `web/static/*.html` |
| Jetons | `tokens.css` reprend les jetons de `DESIGN.md` sous les mêmes noms ; `tests/test_web_tokens.py` vérifie qu'ils ne dérivent pas. Thème sombre sous `[data-theme="dark"]` et `prefers-color-scheme` | `tokens.css:1-5` |
| Thème | `theme.js`, script classique en tête de page (pas de flash), choix Système, Clair ou Sombre en `localStorage`, accès protégés | `theme.js` |
| i18n | `GET /api/ui_texts` sert les textes (`content/ui.yaml`) ; `i18n.js` remplace `data-i18n`, `data-i18n-title`, `data-i18n-aria-label` ; pluriels par `Intl.PluralRules`, nombres et dates par `Intl`. Le HTML garde son texte français : la page reste lisible si la route échoue | `i18n.js:1-12` |
| Polices | Locales (woff2 OFL avec licence), `font-display: swap`. Aptos appelée par `local()`, jamais embarquée | `fonts.css`, AD-18 |
| Streaming | **Journal d'événements** et interface en projection (AD-1). Un seul flux `GET /api/stream`, enveloppes numérotées (`seq`), reprise par `Last-Event-ID`, `server_instance` pour détecter un redémarrage, keep-alive de 15 s. Côté client, lecture par `fetch` et parsing manuel, reconnexion toutes les 1 s, perte de connexion annoncée après 3 échecs | `app.py:1384-1428`, `app.js:200-260` |
| Commandes | « Intentions » en `POST` JSON, en trois classes : à tout moment, refusées hors `idle` avec la raison (409), préemptives (arrêt). La session émet `session_state{state, reason_text}`, que le front utilise pour désactiver ses commandes en affichant la raison | AD-3 |
| Sécurité locale | `TrustedHostMiddleware`, refus des `POST` d'une autre origine, JSON obligatoire, pas de CORS, écoute sur `127.0.0.1` | AD-18 |
| Modules partagés | `markdown.js` (sous-ensemble sûr, construit nœud par nœud, sans `innerHTML`), `diagram.js` (SVG), `panes.js` (volets masquables, focus, poignées clavier, mode projection), `bar.js` (barre commune : dépense et journal), `site-nav.js` | AD-28 |
| Accessibilité | `aria-live` (16 occurrences), `prefers-reduced-motion` (12), lien d'évitement, 62 règles `:focus-visible`, `<dialog>` natif, mode projection (rampe typographique ×9/7) | `static/*` |
| Tests | pytest (jetons, i18n, routes) et E2E Playwright sur **msedge** déjà installé (`uv run --with playwright…`), sans téléchargement de navigateur | `tools/e2e/README.md` |

### 2.2 Ce qu'on reprend

| Élément | Comment |
|---|---|
| Stack sans compilation (AD-18) | Telle quelle : rien à installer côté poste, rien à compiler, aucun droit admin. FastAPI sert tout |
| Jetons miroirs de `DESIGN.md` plus test de dérive | Tels quels, avec les valeurs de **notre** `DESIGN.md` (primaire `#451DC7`, `#7E65E9` en sombre, etc.) |
| `theme.js` | Tel quel (clé renommée) |
| `i18n.js` et textes en données | Tel quel, en **français seul** au départ : les clés coûtent peu et évitent les textes en dur dans le JS |
| Client SSE avec `Last-Event-ID`, `server_instance` et reconnexion | Repris, mais **par exécution** (voir §3.6) plutôt qu'en journal global |
| Classes d'intentions et `409` avec raison | Repris : un bouton désactivé dit toujours pourquoi |
| `markdown.js` | Repris **et étendu** : il laisse les tableaux en texte (`markdown.js:10-11`), or les agents et les modèles en produisent souvent |
| `panes.js` et mode projection | Repris pour l'Arène (colonnes) et pour la démo au vidéoprojecteur |
| Protection de l'API locale | Reprise telle quelle |
| E2E Playwright sur msedge | Repris |

### 2.3 Ce qu'on adapte ou qu'on écarte

| Élément du harnais | Décision | Raison |
|---|---|---|
| Emoji dans la navigation (« 🛠️ Diagnostic », `index.html:27`) et symboles Unicode du thème (`theme.js:14`) | **Écarté** | Charte : icônes Material, aucun emoji |
| Pas d'icônes Material | **Ajout** : sprite SVG local de Material Symbols (licence Apache 2.0), une trentaine d'icônes, `<svg><use href="#…">` | Charte, sans police de 300 Ko ni CDN |
| Polices Fredoka et Atkinson Hyperlegible | **Non reprises** : notre `DESIGN.md` fixe Aptos puis Inter (déjà servie en local, `src/app/static/fonts/`) | Ne pas contredire `DESIGN.md` ; voir décision U3 |
| Multi-pages, un HTML par écran | **Adapté** : une coquille unique avec un routeur client | D1 garde la bascule cloud en mémoire de page : elle serait perdue à chaque changement de page dans un site multi-pages. Une coquille garde aussi les flux en cours |
| Journal unique de session (AD-1) avec verrou global (AD-3) | **Adapté** : exécutions (`run`) indépendantes, chacune avec son flux | L'Arène, le RAG et l'agent sont des opérations distinctes ; un verrou global bloquerait le chat pendant une installation de modèle |
| Fichiers monolithes (`app.js` 7 659 lignes, `app.css` 4 800) | **Écarté** | Règle : un module par écran et par composant, environ 600 lignes au plus par fichier |
| Pages pédagogiques (tokens, logits, JSON-RPC) | Hors sujet | Notre démonstrateur montre des résultats, pas l'intérieur du modèle |

---

## 3. Proposition de front pour la v2

### 3.1 Choix de la stack

Critères : (1) installation sans droits admin sur un PC pro ; (2) pas de Node à l'exécution ; (3) performance perçue ; (4) maintenabilité par un petit binôme humain et agents ; (5) accessibilité ; (6) streaming ; (7) réutilisation du harnais.

| Option | Description | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| **A. Modules natifs sans compilation (harnais)** | HTML, CSS et JS ES modules servis par FastAPI ; composants en fonctions ou en Custom Elements ; aucun outillage JS | ++ | ++ | ++ | + (discipline de découpage exigée) | ++ (contrôle total) | ++ (`fetch` + SSE) | ++ |
| B. HTMX + Jinja2 rendu serveur | Fragments HTML rendus par le serveur ; `htmx` et son extension SSE recopiés dans `static/vendor/` | ++ | ++ | + (aller-retour par interaction) | + | + | + (SSE de fragments HTML, peu adapté à N colonnes de tokens) | – |
| C. SPA compilée (Svelte ou React avec Vite) | Composants avec outillage ; `dist/` versionné ou produit en CI ; Node seulement en développement | + (si `dist/` est versionné) | + | ++ | ++ pour un gros front, – pour les PR (artefacts compilés) | + | ++ | – |
| D. Rester sur Streamlit (fragments, onglets paresseux) | `st.fragment`, `st.navigation` par sous-page, caches | ++ | ++ | – | + | – | – | – |

**Recommandation : A.** Elle remplit tous les critères durs (pas d'admin, pas de Node), reprend un code qui tourne déjà sur les mêmes PC pro et garde la cohérence avec le harnais. Ses risques viennent de la discipline : découpage en modules, tests de composants, pas d'état métier côté front. Ils se traitent par des règles (§3.2) et non par un outil.

C devient pertinente seulement si le front dépasse une quinzaine d'écrans ou si une bibliothèque de composants tierce est requise. D ne règle ni T1 ni T2 : elle sert de solution d'attente pour la v1.

### 3.2 Architecture front

```
src/<paquet_v2>/web/
  app.py                 FastAPI : pages, /static, /api, SSE
  static/
    index.html           coquille unique (barre haute, navigation, <main>)
    tokens.css           miroir de DESIGN.md (test de dérive)
    base.css             reset, typographie, focus, mode projection
    components.css       composants partagés
    icons.svg            sprite Material Symbols (sous-ensemble)
    fonts/               Inter + licence (Aptos par local())
    core/
      theme.js  i18n.js  router.js  api.js  sse.js  store.js  format.js  markdown.js
    components/
      model-picker.js  badge.js  metric.js  run-status.js  chat-thread.js
      source-panel.js  step-trace.js  confirm-dialog.js  data-table.js  chart-svg.js
    screens/
      home.js  chat.js  arena.js  bench.js  models.js  documents.js  evaluation.js
      agent-solo.js  agent-crew.js  sobriety.js
content/ui.fr.yaml       textes d'interface
```

Règles :

- **Le front ne calcule aucune mesure.** Débit, CO₂, mémoire nécessaire, défauts de modèles, « tient en mémoire » viennent de l'API (principe AD-1 du harnais). Seuls sont permis la mise en forme, un chronomètre local et le débit **provisoire** pendant le flux (§3.7).
- **Routeur par `hash`** (`#/arene/comparer`) : liens profonds, bouton Précédent, aucune configuration serveur. Chaque écran est chargé par `import()` à la première visite, puis gardé en mémoire : revenir sur un onglet est instantané (T1).
- **Store** minimal (objet observable) pour l'état partagé : mode cloud, état d'Ollama, liste des modèles, exécutions en cours.
- **État navigateur limité à l'interface** : thème, mode projection, volets, brouillons. Les conversations, résultats et réglages métier vivent côté serveur (« Rien ne se perd », CAP-8).
- Fichiers d'environ 600 lignes au plus. Un composant = une fonction `render(host, props)` ou un Custom Element sans Shadow DOM, pour garder les jetons globaux et l'accessibilité simple.
- Aucune dépendance JS tierce au départ. Si une bibliothèque s'impose, elle est recopiée dans `static/vendor/` avec sa licence, à version vérifiée.

### 3.3 Architecture d'information

La navigation passe de 5 pages à **onglets internes** à 5 modules à **sous-écrans adressables**. Les noms uniques d'`EXPERIENCE.md` sont conservés.

| Module (menu) | Sous-écrans (URL) | Changement par rapport à `EXPERIENCE.md` |
|---|---|---|
| Accueil | `#/` | aucun |
| Arène des modèles | `#/arene/chat` Chat libre · `#/arene/comparer` Arène · `#/arene/banc` Banc d'essai | **« Gestion des modèles » sort de l'Arène** (décision U5) |
| Assistant documentaire | `#/documents` Discussion · `#/documents/base` Base documentaire · `#/documents/evaluation` Évaluation de la qualité | Le dialogue « Gérer la base » devient un écran à part entière |
| Agents autonomes | `#/agents/seul` · `#/agents/equipe` | Le mode passe de la radio latérale à des onglets |
| Sobriété et matériel | `#/sobriete` | aucun |
| Modèles (nouveau, en bas du menu) | `#/modeles` | ex-« Gestion des modèles » |

**Barre haute commune**, toujours visible, qui remplace la barre latérale de Streamlit :

```
+--------------------------------------------------------------------------------------------+
| WaveLocalAI | Accueil  Arène  Documents  Agents  Sobriété  Modèles |  [o] Ollama disponible |
|             |                                                      |  [ ] Autoriser le cloud |
|             |                                                      |  CO₂ session 412 mg  [Aff.]|
+--------------------------------------------------------------------------------------------+
```

- `[o]` : pastille d'état avec un libellé (jamais la couleur seule) : « Ollama disponible », « Ollama ne répond pas ». Un clic ouvre un panneau : version, modèles chargés, mémoire, « Réessayer ».
- « Autoriser le cloud » : interrupteur unique (D1). Son aide le dit : « Désactivé à chaque ouverture de la page. Activé, les données envoyées aux modèles cloud quittent la machine. » La perte au rechargement devient explicite, donc comprise (T6).
- « CO₂ session » ouvre un panneau, comme le bilan de la séance du harnais : total, part Local et Cloud, réponses non mesurables, lien vers Sobriété.
- « Aff. » ouvre le menu Affichage : thème, mode projection.
- À moins de 1 024 px, les liens passent dans un menu repliable.

### 3.4 Composants clés

| Composant | Comportement | Corrige |
|---|---|---|
| `model-picker` | Combobox ARIA (motif WAI-ARIA « combobox with listbox popup ») avec **saisie pour filtrer**, groupes « Sur cette machine » et « Cloud » (ce dernier visible seulement si le cloud est autorisé), et une ligne par modèle : nom, badge Local ou Cloud, taille, « tient en mémoire », débit mesuré sur ce poste, pastilles « outils vérifiés » ou « raisonnement ». Les modèles d'embedding et de reclassement ne sont jamais proposés pour générer. Un modèle qui ne tient pas reste choisissable, avec un avertissement. Le défaut vient de l'API, avec sa raison en aide. Mode multi (Arène) : cases à cocher et pastilles retirables | T4, T5, F10 |
| `badge` | Local (vert, `computer`), Cloud (orange, `cloud`), Origine inconnue (gris, `help`). Toujours un texte | D1 |
| `metric` | Libellé, valeur avec unité, aide (`<button aria-describedby>`), état « provisoire » en italique pendant un flux | D3 |
| `run-status` | Étapes nommées (« Chargement du modèle en mémoire… », « Recherche des extraits… », « Génération… »), chronomètre, bouton **Arrêter** | T8, U20 |
| `chat-thread` | `role="log"` ; flux de tokens dans un nœud tampon ; annonce lecteur d'écran à la fin seulement ; raisonnement replié ; pied de réponse | T1 |
| `source-panel` | Liste numérotée, document, page, **pertinence normalisée** (rang plus libellé « très proche », « proche », « éloignée », score brut en aide), extrait entier avec passage surligné, « Ouvrir l'extrait » | §1.2 RAG |
| `step-trace` | Liste ordonnée d'étapes dépliables (penser, outil, résultat, réponse, attente de validation), une icône et un libellé par type, durée, agent courant pour l'équipe | §1.2 Agents |
| `confirm-dialog` | `<dialog>` natif, focus sur « Annuler », conséquence chiffrée | U15, D2 |
| `data-table` | `<table>` sémantique, tri au clavier, en-têtes `scope` ; sert d'alternative à chaque graphique | U17 |
| `chart-svg` | Nuage de points (qualité, débit, CO₂ en taille, légende de taille) et barres d'historique en SVG fait main, sur les jetons `chart-*` ; `<title>` et `<desc>`, et un lien « Voir le tableau » | U16, U17 |

### 3.5 Parcours clés redessinés

#### Accueil

But : en 5 secondes, savoir si la démo peut partir et la lancer.

```
+--------------------------------------------------------------------------------------------+
| [barre haute]                                                                              |
+--------------------------------------------------------------------------------------------+
| WaveLocalAI                                                                                |
| Le démonstrateur d'IA générative souveraine, frugale et sécurisée.                         |
|                                                                                            |
| +-----------------+ +-----------------+ +-----------------+ +-----------------+            |
| | Système         | | Mode            | | Processeur      | | Mémoire         |            |
| | Disponible      | | (Local)         | | 12 %            | | 9,8 / 15,7 Go   |            |
| | Ollama 0.40.6   | | 0 appel cloud   | | en direct       | | en direct       |            |
| +-----------------+ +-----------------+ +-----------------+ +-----------------+            |
|                                                                                            |
| Démo recommandée                                                                           |
| +----------------------------------------------------------------------------------------+ |
| | [leaderboard] Arène des modèles                                                        | |
| | Comparez plusieurs petits modèles sur votre question : qualité, vitesse et CO₂.        | |
| | Prêts : Qwen 3.5 2B · Gemma 4 1B · LFM 2.5 1.2B (Local)   [ Lancer une comparaison ]   | |
| +----------------------------------------------------------------------------------------+ |
|                                                                                            |
| [description] Assistant documentaire   12 documents indexés · 340 extraits        Ouvrir > |
| [smart_toy]   Agents autonomes         9 outils, dont 1 désactivé (SMTP absent)  Ouvrir > |
| [eco]         Sobriété et matériel     CO₂ de cette session : 412 mg              Ouvrir > |
+--------------------------------------------------------------------------------------------+
```

- La coquille s'affiche tout de suite. Chaque carte se remplit seule, avec un squelette pendant le chargement.
- Ollama absent : la carte Système affiche « Indisponible » et « Démarrez Ollama, puis cliquez sur Réessayer ». Les liens restent actifs. La démo recommandée affiche « Aucun modèle local disponible » et, si le cloud est autorisé, propose des modèles cloud.
- Processeur et mémoire : rafraîchis toutes les 2 s par un flux léger, en pause quand l'onglet du navigateur est masqué (`visibilitychange`).

#### Chat libre

```
+--------------------------------------------------------------------------------------------+
| Arène des modèles     [Chat libre] [Arène] [Banc d'essai]                                  |
+--------------------------------------------------------------------------------------------+
| Modèle [ Qwen 3.5 2B · Local       v ]  Créativité 0,7 [----o---]   [Effacer la conversation]|
|        tient en mémoire · 41 tokens/s mesurés sur ce poste                                 |
+--------------------------------------------------------------------------------------------+
|  Vous : Résume la directive NIS2 en 5 points.                                              |
|                                                                                            |
|  Qwen 3.5 2B                                                                               |
|  > Raisonnement (replié)                                                                   |
|  1. Champ élargi ...                                                                       |
|  2. Gestion des risques ...|                                     <- curseur de flux        |
|  ----------------------------------------------------------------------------------------  |
|  (Local) · Débit 38 tokens/s (provisoire) · 1,4 s · 212 tokens                [Arrêter]    |
+--------------------------------------------------------------------------------------------+
| [ Écrivez votre message                                                        ] [Envoyer] |
|   Entrée : envoyer · Maj+Entrée : nouvelle ligne · Échap : arrêter                         |
+--------------------------------------------------------------------------------------------+
```

- À la fin, le pied devient définitif : « (Local) · CO₂ 1,8 mg · Débit 41 tokens/s · Chargement 3,2 s · Durée totale 6,1 s », avec en aide la définition D3 du débit.
- Changer d'écran pendant la génération ne l'arrête pas. La conversation et le flux reprennent au retour (rejeu SSE).
- Le choix du modèle est gardé par conversation et survit à la bascule cloud. Si le modèle choisi est un modèle cloud et que le cloud est désactivé, un message le dit et propose le meilleur modèle local.

#### Arène (comparaison côte à côte, métriques en direct)

C'est l'écran de la démo d'avant-vente (Flow 1). Il doit être lisible du fond de la salle en mode projection.

Configuration :

```
+--------------------------------------------------------------------------------------------+
| Arène des modèles     [Chat libre] [Arène] [Banc d'essai]                                  |
+--------------------------------------------------------------------------------------------+
| Question                                                                                   |
| [ Explique la dette technique à un enfant de 10 ans avec une métaphore filée.            ] |
| Scénarios : [Vulgarisation] [Extraction JSON] [Résumé] [Traduction]                        |
|                                                                                            |
| Modèles comparés (3)                                  Juge                                 |
| [x Qwen 3.5 2B · Local] [x Gemma 4 1B · Local]        [ Qwen 3.6 7B · Local      v ]      |
| [x LFM 2.5 1.2B · Local] [+ Ajouter un modèle]        Choisi d'après le benchmark de ce poste |
|                                                       > Critères de notation               |
| Exécution : les modèles locaux passent l'un après l'autre (mémoire) ; les modèles cloud    |
| en parallèle.                                         [ Lancer la comparaison ]            |
+--------------------------------------------------------------------------------------------+
```

Exécution, puis résultat (même écran, sans rechargement) :

```
+--------------------------------------------------------------------------------------------+
| Comparaison en cours · 2 sur 3 · 0:42                                    [Arrêter]         |
+------------------------------+------------------------------+------------------------------+
| Qwen 3.5 2B         (Local)  | Gemma 4 1B          (Local)  | LFM 2.5 1.2B        (Local)  |
| Terminé                      | Génération…                  | En attente                   |
| Note 82/100                  | Débit 52 t/s (provisoire)    |                              |
| Débit 41 t/s · CO₂ 1,8 mg    | 1er token 0,4 s · 118 tokens |                              |
| Chargement 3,2 s · 6,1 s     |                              |                              |
|------------------------------|------------------------------|------------------------------|
| Imagine que ton code est une | Pense à ta chambre. Chaque   |                              |
| maison en Lego. Chaque fois  | fois que tu ranges vite...|  |                              |
| que tu ...                   |                              |                              |
| [Afficher toute la réponse]  |                              |                              |
+------------------------------+------------------------------+------------------------------+
| Classement                     [Matrice] [Tableau]                                          |
| 1  LFM 2.5 1.2B   Local  88/100  61 t/s  0,9 mg   le plus petit des trois                  |
| 2  Qwen 3.5 2B    Local  82/100  41 t/s  1,8 mg                                            |
| 3  Gemma 4 1B     Local  non évalué (réponse vide)  52 t/s  1,1 mg                         |
| Juge : Qwen 3.6 7B (Local). Note peu fiable sous 4 milliards de paramètres actifs : —      |
| [Relancer] [Modifier la question] [Exporter (CSV, Markdown)]                               |
+--------------------------------------------------------------------------------------------+
```

- Une colonne par modèle, de 2 à 4 colonnes. Au-delà, défilement horizontal avec des en-têtes collants. Le mode focus (`panes.js`) agrandit une colonne.
- Statuts par colonne : En attente, Chargement du modèle en mémoire, Génération, Notation, Terminé, Délai dépassé, Échec, Arrêté. Chaque statut a un texte et une icône.
- La note arrive après la génération, colonne par colonne. Le classement se construit au fil des résultats et se fige à la fin.
- Le résultat est **conservé** côté serveur, avec son identifiant (`#/arene/comparer/<run_id>`) : on peut le rouvrir, le partager à l'écran ou l'exporter (T2).
- Le CO₂ d'un modèle cloud sans taille connue s'affiche « non mesurable », avec une aide (voir §3.7), jamais « — » seul.

#### Assistant documentaire : Discussion avec sources

```
+--------------------------------------------------------------------------------------------+
| Assistant documentaire   [Discussion] [Base documentaire] [Évaluation de la qualité]       |
| 12 documents · 340 extraits · Modèle [ Qwen 3.5 2B · Local v ]  > Réglages avancés          |
+-------------------------------------------------------+------------------------------------+
| Vous : Quels changements pour le projet Zero Trust ?  | Sources (3)                        |
|                                                       | [1] Notes_Zero_Trust.pdf, p. 2     |
| Qwen 3.5 2B                                           |     Très proche                    |
| Deux changements [1] : le correctif du pont SAML est  |     « SAML bridge hotfix applied,  |
| appliqué, mais le fournisseur exige [1][2] ... La     |     but vendor still requires ... »|
| fenêtre d'audit ISO 27001 est avancée [3].            |     [Ouvrir l'extrait]             |
| ----------------------------------------------------  | [2] Message_Teams.pdf, p. 1        |
| (Local) · CO₂ 2,4 mg · 39 t/s · Recherche 0,06 s ·    |     Proche                         |
| Génération 5,8 s                     [Télécharger]    | [3] Notes_Zero_Trust.pdf, p. 3     |
+-------------------------------------------------------+------------------------------------+
| [ Posez une question à vos documents                                         ] [Envoyer]   |
+--------------------------------------------------------------------------------------------+
```

- Les sources arrivent **avant** les tokens (événement `sources`), dans le panneau de droite. Survoler ou focaliser [n] dans la réponse met la source en évidence, et inversement.
- Les marqueurs [n] existent seulement si le back les fournit (consigne de citation dans l'invite, puis vérification). Sinon, le panneau suffit et la réponse ne porte aucun marqueur inventé par le front.
- Étapes du `run-status` : « Recherche des extraits… », « Rédaction d'une réponse hypothétique… » (HyDE), « Vérification de la pertinence… » (Self-RAG), « Reclassement… », « Génération… ».
- À moins de 1 024 px, le panneau passe sous la réponse, replié.

#### Assistant documentaire : Base documentaire (remplace le dialogue)

```
+--------------------------------------------------------------------------------------------+
| Base documentaire                                                                          |
| +----------------------------------------------------------------------------------------+ |
| |  Déposez des fichiers ici ou [Choisir des fichiers]   PDF, TXT, MD, DOCX               | |
| +----------------------------------------------------------------------------------------+ |
| Note_cadrage.docx   Envoi 100 % · Découpage · Vectorisation 18/40 extraits   [Annuler]     |
| Budget_2026.pdf     Échec : fichier protégé par un mot de passe.   > Détails techniques    |
|                                                                                            |
| Documents indexés (12)                         [Filtrer]       [Vider la base documentaire]|
| Nom                     Extraits  Ajouté le          Modèle de représentation              |
| Notes_Zero_Trust.pdf    35        18 oct. 2026 09:15 bge-m3              [Supprimer]       |
| ...                                                                                        |
| Réglages : représentation bge-m3 · reclassement bge-reranker-v2-m3 · 4 extraits            |
+--------------------------------------------------------------------------------------------+
```

- La zone de dépôt est visible tout de suite, sans aucun aller-retour serveur (corrige le dialogue qui ne s'ouvrait pas).
- Progression en deux temps : envoi (progression d'upload du navigateur), puis indexation (flux SSE par fichier).
- « Vider la base » ouvre `confirm-dialog` : « 340 extraits de 12 documents seront supprimés. »
- Ajout par rapport à la v1 : suppression d'un seul document. À confirmer avec l'auditeur back (décision U8).

#### Évaluation de la qualité

```
+--------------------------------------------------------------------------------------------+
| Évaluation de la qualité                                                                   |
| Question [ ................................................ ]  ou [Jeu de questions v]     |
| Modèles évalués [x Qwen 3.5 2B] [x Gemma 4 1B] [+]   Juge [ Qwen 3.6 7B · Local v ]        |
| Les mêmes extraits sont fournis à tous les modèles.            [ Lancer l'évaluation ]     |
+--------------------------------------------------------------------------------------------+
| Étape 1/3 Recherche des extraits communs · fait (4 extraits)          [Voir les extraits]  |
| Étape 2/3 Réponses : Qwen fait · Gemma en cours                                            |
| Étape 3/3 Notation Ragas : fidélité · pertinence de la réponse · précision du contexte     |
+--------------------------------------------------------------------------------------------+
| Modèle        Fidélité  Pertinence  Précision  Global  Débit   CO₂     [Matrice][Tableau]  |
| Qwen 3.5 2B   86/100    79/100      90/100     85/100  41 t/s  2,4 mg                      |
| Gemma 4 1B    non évalué : Ragas indisponible (voir Détails techniques)                     |
+--------------------------------------------------------------------------------------------+
```

- Une seule échelle /100 (EXPERIENCE.md). « non évalué » avec sa raison, jamais 0.
- Chaque métrique a une définition en une phrase, en aide.
- Le résultat est conservé et rouvrable comme pour l'Arène.

#### Agents autonomes : Agent seul, avec la trace des étapes

```
+--------------------------------------------------------------------------------------------+
| Agents autonomes   [Agent seul] [Équipe d'agents]                                          |
| Modèle [ Qwen 3.6 7B · Local · outils vérifiés v ]   Outils : [Heure] [Calculatrice]       |
| [Recherche interne Wavestone] [Analyse de données] ... [Envoi d'email: désactivé, SMTP absent]|
+-------------------------------------------------------+------------------------------------+
| Vous : Analyse ventes.csv et fais un graphique.       | Étapes                     0:18    |
|                                                       | 1 [psychology] Réflexion   0,9 s v |
| Qwen 3.6 7B                                           | 2 [table] Analyse de données 2,1 s v|
| Le chiffre d'affaires progresse de 12 % ...           |   Arguments : {"file": "ventes.csv"}|
| [graphique généré : ventes_par_mois.png]              |   Résultat : 12 lignes, 4 colonnes  |
| ----------------------------------------------------  | 3 [bar_chart] Graphique    1,4 s v |
| (Local) · CO₂ 6,2 mg · 4 étapes · 18,4 s [Télécharger]| 4 [chat] Réponse finale    en cours|
+-------------------------------------------------------+------------------------------------+
| [ Décrivez la tâche à confier à l'agent                                 ] [Envoyer][Arrêter]|
+--------------------------------------------------------------------------------------------+
```

- Chaque étape arrive en direct. On peut en déplier une pendant que les suivantes arrivent.
- Email (D2) : l'étape « Envoi d'email » passe en **« En attente de votre validation »**. `confirm-dialog` montre le destinataire, l'objet et le corps. L'agent attend la décision, et rien ne part sans « Envoyer l'email ».
- Garde-fou mémoire : la question reste. L'alerte chiffre la mémoire nécessaire et la mémoire libre et propose deux issues (modèle plus petit, libérer la mémoire **d'Ollama**, c'est-à-dire décharger les modèles inactifs). Le bouton actuel « Libérer la mémoire » (torch, CUDA) disparaît.

#### Équipe d'agents

```
+--------------------------------------------------------------------------------------------+
| Équipe : Veille concurrentielle   [Charger une équipe]  [Configurer]                       |
| Sujet [ IA souveraine en Europe                                              ]             |
| (Chercheur) ---> (Analyste) ---> (Rédacteur) ---> [Rapport]          [ Lancer la mission ] |
+--------------------------------------------------------------------------------------------+
| Chercheur   Terminé   3 outils · 41 s   v                                                  |
| Analyste    En cours  Analyse de données…                                                  |
| Rédacteur   En attente                                                                     |
| > Journal brut (repli)                                                     [Arrêter]       |
+--------------------------------------------------------------------------------------------+
| Rapport · (Local) · CO₂ 48 mg · Pic de mémoire 2,1 Go · 2 min 12 s  [Télécharger]          |
+--------------------------------------------------------------------------------------------+
```

- Le schéma de l'équipe est en SVG (fini Graphviz côté poste). L'agent actif est mis en évidence par un contour et un libellé « en cours », pas par la couleur seule.
- La trace structurée suppose que le back émette des événements par agent et par tâche (rappels de CrewAI). Le journal brut reste disponible, replié.

#### Sobriété et matériel

```
+--------------------------------------------------------------------------------------------+
| Sobriété et matériel                                                                       |
| Santé du système (en direct)                                                               |
| Processeur 34 %  Mémoire 9,8 / 15,7 Go  Accélérateur RTX 3060 6 Go  Ollama : 2 modèles chargés|
|                                                                                            |
| Empreinte carbone de cette session                     [Arrêter et enregistrer]            |
| Total 412 mg  (environ 3,7 m en voiture)                                                   |
| Par module : Arène 280 mg · Documents 96 mg · Agents 36 mg                                 |
| Local 398 mg · Cloud 14 mg (estimé) · 3 réponses non mesurables              [Détail]      |
|                                                                                            |
| Historique                    [7 jours] [30 jours] [Tout]         [Graphique] [Tableau]    |
|  mg |    #                                                                                 |
|     | #  #     #   (trou de mesure)  #                                                     |
|     +-------------------------------------- date                                         |
|                                                                                            |
| > Carte d'identité technique                                                               |
| > Comment ces chiffres sont calculés                                                       |
+--------------------------------------------------------------------------------------------+
```

### 3.6 Streaming : comportement attendu

| Règle | Détail |
|---|---|
| Une exécution = un `run_id` | `POST` qui démarre et renvoie `{run_id}` tout de suite, puis `GET /api/runs/{id}/events` en SSE |
| Rejouable | Événements numérotés, reprise par `Last-Event-ID` (motif du harnais). Revenir sur l'écran rejoue le flux, et l'exécution continue sans l'onglet |
| Annulable | `POST /api/runs/{id}/cancel`, bouton Arrêter et touche Échap. Le résultat partiel est gardé et marqué « Arrêté » |
| Tokens groupés | Le serveur envoie des tranches d'environ 50 ms. Le client les ajoute dans un nœud texte, puis rend le Markdown au plus toutes les 150 ms et à la fin : pas de reflow par token |
| Défilement | Suit le flux tant que l'utilisateur est en bas. S'il remonte, il n'est plus tiré vers le bas, et un bouton « Aller à la fin » apparaît |
| Lecteurs d'écran | Rien n'est annoncé pendant le flux. À la fin : « Réponse de Qwen 3.5 2B terminée, 212 tokens. » par une région `aria-live="polite"` |
| Perte de connexion | Après 3 essais, la barre haute dit « Connexion au serveur perdue, nouvelle tentative… » ; à la reprise, le flux continue sans doublon |
| Serveur redémarré | `server_instance` change : « Le serveur a redémarré. Les exécutions en cours sont perdues. » plus « Recharger » |

### 3.7 Affichage du carbone et du débit

| Grandeur | Pendant le flux | À la fin | Règle |
|---|---|---|---|
| Débit | « 38 t/s (provisoire) », calculé par le client sur les tranches reçues, en italique | `eval_count / eval_duration` d'Ollama (D3), qui remplace la valeur provisoire | La valeur finale vient toujours du serveur |
| Premier token | Chronomètre local | Valeur serveur | — |
| Chargement | « Chargement du modèle en mémoire… » | « Chargement 3,2 s », à part (D3) | — |
| CO₂ local | — | « 1,8 mg » | Formule du cœur, mg sous 1 g, une seule unité par comparaison |
| CO₂ cloud de taille connue | — | « 0,9 mg (estimé) » | Le mot « estimé » est toujours là |
| CO₂ cloud de taille inconnue (Claude) | — | **« non mesurable »** et une aide : « Anthropic ne publie pas la taille de ce modèle : son empreinte ne peut pas être calculée. » | Jamais « — » seul ; jamais 0. Option : fourchette EcoLogits (décision U6) |
| CO₂ de session | Mis à jour à chaque fin de réponse | — | Le compte des réponses non mesurables est affiché à côté du total |

Aucune couleur par seuil de CO₂ (`DESIGN.md`). Unités et formats en `fr-FR` via `Intl`, avec les règles de `EXPERIENCE.md` (Chiffres).

### 3.8 États et messages d'erreur

Format d'erreur unique, venu de l'API : `{code, message, action, detail}`. Le front affiche le message puis l'action, et le détail technique dans « Détails techniques », replié.

| Code | Où | Message (ce qui a échoué) | Action proposée |
|---|---|---|---|
| `ollama_down` | Barre haute ; écrans locaux | Ollama ne répond pas. | Démarrez Ollama, puis [Réessayer]. Si le cloud est autorisé : « Les modèles cloud restent disponibles. » |
| `no_model` | Sélecteurs | Aucun modèle de conversation installé. | [Installer un modèle] (vers Modèles) |
| `model_not_chat` | Défense en profondeur | Ce modèle sert à représenter les textes, pas à converser. | Choisir un autre modèle |
| `ram_guard` | Toute inférence | Mémoire insuffisante : 5,2 Go nécessaires, 2,8 Go libres. | [Prendre un modèle plus petit] [Décharger les modèles inactifs] |
| `cloud_not_allowed` | Cloud désactivé | Ce modèle est un modèle cloud : le cloud n'est pas autorisé. | [Autoriser le cloud] ou modèle local proposé |
| `cloud_unreachable` | Cloud | Le fournisseur Anthropic ne répond pas. | Vérifier la connexion, la clé et le quota, ou repasser en Local |
| `cloud_key_missing` | Cloud | Aucune clé d'API pour Mistral. | Où la configurer (`.env`) |
| `timeout` | Chat, Arène, Banc | Délai dépassé (2 min). | Réessayer, question plus courte, modèle plus petit |
| `interrupted` | Toute génération | Ollama a arrêté la génération avant la fin. | Relance automatique une fois, puis [Réessayer] |
| `not_evaluated` | Arène, Évaluation | non évalué : réponse vide / juge indisponible / Ragas indisponible. | — |
| `ingest_failed` | Base documentaire | Le fichier n'a pas pu être indexé : <raison>. | Compteur inchangé |
| `busy` (409) | Commandes | Une installation de modèle est en cours. | Bouton désactivé avec la raison |

États vides : ceux d'`EXPERIENCE.md` (State Patterns) sont repris tels quels. Chargement : squelettes dans les cartes, jamais d'écran blanc. **La coquille ne dépend d'aucun appel au back pour s'afficher.**

### 3.9 Accessibilité (RGAA 4.1, WCAG 2.2 AA)

| Exigence | Mise en œuvre |
|---|---|
| Structure | `lang="fr"`, repères (`header`, `nav`, `main`), lien d'évitement « Aller au contenu », un `h1` par écran (le nom du module), `h2`/`h3` sans saut |
| Titre de page | `document.title` mis à jour à chaque route (« Arène · WaveLocalAI ») ; focus déplacé sur le `h1` au changement d'écran ; annonce polie |
| Clavier | Tout au clavier ; ordre logique ; `:focus-visible` à 3:1 ; raccourcis documentés (Entrée, Maj+Entrée, Échap) sans touche unique |
| Contrastes | Jetons de `DESIGN.md`, déjà calculés en clair et en sombre ; écart connu de `#7E65E9` en sombre (4,26:1) consigné |
| Couleur | Aucune information par la couleur seule : badges, statuts et séries ont un libellé |
| Composants | Combobox, onglets (`tablist`), dialogues (`<dialog>` natif), arborescence des étapes : motifs WAI-ARIA APG |
| Flux | `role="log"`, annonce à la fin seulement (§3.6) |
| Graphiques | SVG avec `<title>` et `<desc>` ; tableau équivalent toujours accessible |
| Mouvement | `prefers-reduced-motion` : ni curseur clignotant ni animation de défilement |
| Zoom et reflow | Lisible à 200 % et à 320 px CSS de large sans défilement horizontal, hors tableaux larges qui défilent dans leur conteneur |
| Formulaires | Libellé visible pour chaque champ ; erreurs liées par `aria-describedby` |
| Vérification | axe-core en clair et en sombre sur chaque écran, en E2E ; zéro violation, **sans exclusion** (celles de Streamlit tombent) ; audit RGAA manuel au lot 6 |

### 3.10 Responsive et projection

| Largeur | Comportement |
|---|---|
| 1 440 px et plus (poste, vidéoprojecteur) | Cible principale : Arène à 3 ou 4 colonnes ; panneaux de sources et d'étapes à droite |
| 1 024 à 1 439 px | Arène à 2 colonnes visibles et défilement ; panneaux à droite plus étroits |
| 768 à 1 023 px | Panneaux sous le contenu, repliés ; navigation en menu |
| Moins de 768 px (priorité basse) | Une colonne ; Arène en onglets par modèle ; champ de saisie collant en bas |
| Mode projection | Menu Affichage : rampe typographique ×9/7 (motif du harnais), métriques agrandies, pied de page masqué. Mémorisé dans le navigateur |

---

## 4. Besoins du front envers l'API back

À aligner avec le rapport de l'auditeur back. Les noms de routes sont indicatifs ; ce qui compte, ce sont les données et les flux.

### 4.1 Transverse

| Besoin | Route proposée | Données |
|---|---|---|
| Santé | `GET /api/health` | version de l'app, `instance_id`, Ollama `{up, version, latency_ms}` (délai court, mis en cache côté serveur), fournisseurs cloud `{id, configured}` |
| Système en direct | `GET /api/system/stream` (SSE, 2 s) | processeur %, mémoire utilisée et totale, modèles chargés dans Ollama avec leur mémoire |
| Modèles | `GET /api/models?allow_cloud=` | par modèle : `tag`, nom, fournisseur, origine (`local`, `cloud`, `unknown`), **`kind` (`chat`, `embedding`, `reranker`)**, paramètres totaux et actifs, taille, mémoire nécessaire, `fits`, débit et précision mesurés sur ce poste, outils vérifiés, raisonnement, méthode de CO₂ disponible |
| Défauts | `GET /api/models/defaults?purpose=chat\|arena\|judge\|agent\|rag` | tags et **raison** (texte affiché en aide) |
| Mode cloud | En-tête ou champ `allow_cloud` sur chaque commande | Le back refuse un modèle cloud sans ce drapeau (D1). Absent = faux |
| Exécutions | `GET /api/runs/{id}/events` (SSE), `POST /api/runs/{id}/cancel`, `GET /api/runs/{id}` (instantané final) | enveloppe `{seq, run_id, type, ts, data}` |
| Erreurs | Toutes les routes | `{code, message, action, detail}` en français (§3.8) ; `409` avec raison quand c'est occupé |
| CO₂ de session | `GET /api/carbon/session` et événement `carbon_updated` | total, par module, Local et Cloud, nombre de non-mesurables |

### 4.2 Événements d'exécution

| Type | Données | Écrans |
|---|---|---|
| `run_started` | type d'exécution, modèles, paramètres | tous |
| `model_loading` / `model_loaded` | `tag`, durée | chat, Arène, RAG, agents |
| `token` | `lane` (tag du modèle pour l'Arène), `text`, `channel` (`answer` ou `thought`) | chat, Arène, RAG, agent (réponse finale) |
| `retry` | raison | chat, Arène, RAG |
| `metrics` | `ttft_s`, `load_s`, `eval_tokens`, `eval_s`, `tps` (D3), `tps_estimated`, `total_s`, `co2 {mg \| null, method: local\|cloud_formula\|ecologits\|unknown, reason}`, origine | tous |
| `lane_status` | `lane`, `status` (`waiting`, `loading`, `generating`, `judging`, `done`, `timeout`, `failed`, `cancelled`) | Arène, Évaluation |
| `judge_score` | `lane`, `score \| null`, `reason` | Arène |
| `sources` | liste `{n, doc_id, document, page, chunk_id, text, rank, relevance_label, raw_score}` | RAG, Évaluation |
| `citations` | correspondances [n] vers les sources, si le back les produit | RAG |
| `retrieval_step` | `strategy`, étape, durée | RAG |
| `eval_metric` | `lane`, métrique, `score \| null`, raison | Évaluation |
| `step` | `step_id`, `agent`, `kind` (`think`, `tool_call`, `tool_result`, `answer`), outil, arguments, résumé, `artifact_url`, durée | agents |
| `approval_required` | `approval_id`, `kind: email`, destinataire, objet, corps | agent seul ; réponse par `POST /api/runs/{id}/approvals/{approval_id}` |
| `ingest_progress` | fichier, phase (`extract`, `split`, `embed`), `done`, `total` | Base documentaire |
| `pull_progress` | tag, octets reçus et totaux, phase | Modèles |
| `run_ended` | `status` (`ok`, `error`, `cancelled`), erreur au format unique | tous |

### 4.3 Par écran

| Écran | Lectures | Commandes |
|---|---|---|
| Accueil | santé, système, modèles par défaut (`arena`), résumé de la base, outils disponibles, CO₂ de session | — |
| Chat libre | modèles, défaut `chat`, conversation `GET /api/conversations/{id}` | `POST /api/chat/runs {conversation_id?, model, message, temperature, allow_cloud}` ; `DELETE /api/conversations/{id}` |
| Arène | modèles, défauts `arena` et `judge`, scénarios, historique `GET /api/arena/runs` | `POST /api/arena/runs {models, prompt, judge, criteria, allow_cloud}` ; export `GET /api/arena/runs/{id}.csv` et `.md` |
| Banc d'essai | `GET /api/scenarios` (avec format attendu) | `POST /api/bench/runs` ; le back dit si le JSON attendu est valide |
| Modèles | modèles installés, catalogue installable avec mémoire nécessaire et `fits` | `POST /api/models/pull {tag}` ; `DELETE /api/models/{tag}` ; `POST /api/models/unload` |
| Discussion RAG | résumé de la base, réglages, défaut `rag` | `POST /api/rag/runs {conversation_id?, question, model, allow_cloud}` ; `GET /api/rag/chunks/{id}` (extrait entier) |
| Base documentaire | `GET /api/rag/documents`, réglages `GET /api/rag/settings` | `POST /api/rag/documents` (multipart) donne un `run_id` d'ingestion ; `DELETE /api/rag/documents/{id}` ; `DELETE /api/rag/base?expected_count=` ; `PUT /api/rag/settings` |
| Évaluation | jeux de questions, historique | `POST /api/rag/eval/runs {questions, models, judge, allow_cloud}` |
| Agent seul | `GET /api/agents/tools` (`id`, libellé, description, disponible, raison, sensible), scénarios, défaut `agent` | `POST /api/agents/runs {mode: solo, model, tools, prompt, conversation_id?}` ; approbations |
| Équipe d'agents | `GET /api/agents/crews` (bibliothèque) | `POST /api/agents/runs {mode: crew, crew, topic}` ; `POST /api/agents/crews/validate` |
| Sobriété | système en direct, identité `GET /api/system/identity`, `GET /api/carbon/history?window=`, méthode de calcul | `POST /api/carbon/session/stop` |

Exigences non fonctionnelles pour le back :

- Aucune route de lecture ne bloque plus de 300 ms quand Ollama est arrêté (délais courts et cache de l'état « indisponible » pendant quelques secondes, comme `93c5791`).
- Les imports lourds (Ragas, CrewAI, Chroma) se font à la première commande qui en a besoin, jamais au démarrage d'un écran.

---

## 5. Plan de livraison du front par lots

Tailles : S (2 à 3 jours), M (une semaine), L (deux semaines), pour un développeur assisté par agents.

| Lot | Contenu | Taille | Dépend de |
|---|---|---|---|
| 0. Socle | Coquille, routeur, `tokens.css` et son test, polices, sprite d'icônes, thème, i18n française, client SSE, format d'erreur, barre haute (état d'Ollama, bascule cloud, CO₂ de session), `model-picker`, `metric`, `badge`, `run-status`, protection de l'API locale | M | API transverse (§4.1) |
| 1. Chat et Arène (MVP démo) | Chat libre en flux avec arrêt ; Arène côte à côte avec métriques en direct, notation, classement, matrice et tableau, résultat conservé et exportable | L | Lot 0 ; runs chat et Arène |
| 2. Assistant documentaire (MVP atelier) | Base documentaire (dépôt, progression, liste, suppression, vidage confirmé), Discussion avec panneau de sources | M | Lot 0 ; RAG |
| 3. Sobriété et Modèles | Sobriété en direct, historique, ventilation ; Modèles (installer avec progression, décharger, supprimer, compatibilité mémoire) | M | Lot 0 |
| 4. Agents | Agent seul avec trace et validation d'email ; Équipe d'agents avec schéma SVG et trace par agent | L | Lot 0 ; événements `step` |
| 5. Évaluation et Banc d'essai | Évaluation Ragas en étapes, résultats conservés ; Banc d'essai avec contrôle du format | M | Lots 1 et 2 |
| 6. Finition | Mode projection, responsive, audit RGAA manuel, suite E2E complète, nouvelles captures du README et du GIF | M | Tous |

Le **MVP** regroupe les lots 0 à 2 : il couvre les deux parcours de référence d'`EXPERIENCE.md` (Flow 1 avant-vente, Flow 2 atelier).

### Critères d'acceptation

**Lot 0, Socle**

- Installation par `uv sync` seul. Aucun Node, aucun téléchargement à l'exécution. Le navigateur n'émet **aucune requête hors de `127.0.0.1`** (vérifié en E2E).
- La coquille s'affiche en moins de 300 ms en local et **reste utilisable avec Ollama arrêté**. La barre haute dit « Ollama ne répond pas » en moins de 3 s.
- La bascule cloud est désactivée à chaque chargement de page, conservée d'un écran à l'autre, et le back refuse un modèle cloud sans elle.
- Le `model-picker` ne propose aucun modèle d'embedding ni de reclassement pour générer. Il se filtre au clavier. Il groupe Local et Cloud.
- Le test de dérive des jetons passe. axe-core ne relève aucune violation sur la coquille, en clair et en sombre. Aucun emoji dans `static/`.

**Lot 1, Chat et Arène**

- Le premier token s'affiche dès sa réception. « Arrêter » coupe en moins de 1 s et garde le texte partiel.
- Changer d'écran pendant une génération, puis revenir : le flux reprend sans perte ni doublon.
- L'Arène affiche 3 colonnes qui se remplissent ; un délai dépassé n'arrête pas les autres ; « non évalué » n'est jamais 0.
- Le résultat survit à tout clic et se rouvre par son URL. Le débit final est égal à `eval_count / eval_duration` (D3), et le débit provisoire est marqué comme tel.
- Le CO₂ d'un modèle Claude s'affiche « non mesurable » avec son explication.
- Flow 1 joué de bout en bout en E2E avec des modèles simulés.

**Lot 2, Assistant documentaire**

- La zone de dépôt est visible sans délai. Une progression s'affiche par fichier. Un échec affiche sa raison et laisse le compteur inchangé.
- Les sources arrivent avant la réponse, avec document, page et extrait entier. Le score brut n'est plus le seul indicateur.
- « Vider la base documentaire » annonce le nombre d'extraits et « Annuler » ne supprime rien.
- Flow 2 joué de bout en bout en E2E sur une collection de test (jamais `data/chroma`).

**Lot 3, Sobriété et Modèles**

- Les métriques se mettent à jour sans clic et s'arrêtent quand l'onglet du navigateur est masqué.
- Le CO₂ de session est égal à la somme des réponses mesurées, et les non-mesurables sont comptés à part.
- Avant une installation, le modèle indique s'il tient en mémoire. La progression est chiffrée.

**Lot 4, Agents**

- Chaque étape apparaît en direct et se déplie pendant l'exécution. Un email n'est jamais envoyé sans validation explicite.
- Le garde-fou mémoire garde la question et chiffre le besoin.
- La mission d'équipe s'arrête sur demande, et son rapport est conservé.

**Lot 5, Évaluation et Banc d'essai**

- Les étapes et les scores arrivent au fil de l'eau. Ragas indisponible donne « non évalué » avec la raison.
- Le banc dit si la sortie respecte le format attendu.

**Lot 6, Finition**

- Zéro violation axe-core sur tous les écrans, en clair et en sombre. Grille RGAA 4.1 remplie pour les critères applicables.
- Lisible à 200 % de zoom et à 390 px de large.
- Le mode projection est validé sur un vidéoprojecteur réel.
- Les captures et le GIF du README sont refaits.

---

## Décisions à prendre par l'utilisateur

| ID | Question | Options | Recommandation |
|---|---|---|---|
| U1 | Stack du front v2 | A. modules natifs sans compilation (harnais) ; B. HTMX et Jinja2 ; C. SPA compilée (Svelte ou React) ; D. rester sur Streamlit | **A** : aucun Node, aucune installation, et la reprise directe du harnais. C seulement si le front dépasse une quinzaine d'écrans |
| U2 | Coquille unique ou multi-pages | Coquille avec routeur client ; une page HTML par module (harnais) | **Coquille** : D1 garde la bascule cloud en mémoire de page, et les flux survivent à la navigation |
| U3 | Typographie | Aptos puis Inter (`DESIGN.md` actuel) ; Fredoka et Atkinson Hyperlegible (harnais) | **Aptos puis Inter**, pour ne pas contredire `DESIGN.md`. À revoir seulement si une identité commune aux démonstrateurs Wavestone est voulue |
| U4 | Persistance des conversations et résultats | Mémoire du processus ; fichiers JSON dans `data/` (non versionné) ; aucune | **Fichiers dans `data/`**, avec un bouton « Effacer ». Le cloud reste désactivé à chaque ouverture (D1) |
| U5 | Place de « Gestion des modèles » | Onglet de l'Arène (`EXPERIENCE.md`) ; écran « Modèles » à part | **Écran à part** : c'est de l'administration, pas de la démo. Modifie l'IA d'`EXPERIENCE.md` |
| U6 | CO₂ des modèles cloud de taille inconnue | « non mesurable » expliqué ; fourchette EcoLogits (déjà utilisée par le harnais) marquée « estimé » | **« non mesurable » au MVP**, puis EcoLogits si la méthode est validée par l'auditeur back |
| U7 | Exécution des modèles dans l'Arène | Tout en séquence ; locaux en séquence et cloud en parallèle | **Locaux en séquence, cloud en parallèle** : la RAM borne les locaux |
| U8 | Suppression d'un document seul dans la base | Oui ; non (vidage complet seulement, comme en v1) | **Oui**, si le back peut retirer les extraits d'une source |
| U9 | Graphiques | SVG fait main (comme `bar.js` et `diagram.js`) ; bibliothèque recopiée (uPlot, Chart.js) | **SVG fait main** : deux types de graphiques seulement, et un contrôle total de l'accessibilité |
| U10 | Langues | Français seul avec des clés i18n ; français et anglais dès le départ | **Français seul avec clés** : l'anglais s'ajoute plus tard sans reprise |
| U11 | Sort de la v1 Streamlit pendant la refonte | Maintenance stricte (correctifs en cours seulement : `e784e0f`, `93c5791`) ; améliorations UX continues | **Maintenance stricte** : fusionner les deux correctifs en cours, ne plus investir dans l'UI Streamlit |
