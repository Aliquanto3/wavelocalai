# Synthèse des audits du frontend (septembre 2026)

- **Date :** 2026-09-26
- **Sources :**

  | Machine | Profil | Dossier |
  |---|---|---|
  | `poste-rtx3060` | RTX 3060 Laptop 6 Go, Ryzen 7 5800H, 32 Go | [`poste-rtx3060/RAPPORT.md`](poste-rtx3060/RAPPORT.md) (fonctionnel), [`poste-rtx3060/UX.md`](poste-rtx3060/UX.md) (design, accessibilité, rédaction) |
  | `pro-elitebook-x360` | i5-1145G7, 16 Go, sans GPU dédié | [`pro-elitebook-x360/rapport.md`](pro-elitebook-x360/rapport.md) (fonctionnel et lisibilité) |

- **Code audité :** `src/` identique sur les deux machines (`d954bd6`).
- **Rôle de ce document :** l'entrée unique de `bmad-ux` et `bmad-spec` (voir [`NUIT.md`](NUIT.md)). Il remplace les deux plans d'origine, qui restent en trace. Les preuves, captures et reproductions restent dans les rapports de chaque machine : ce document ne les recopie pas.

## 1. Décisions prises avant l'implémentation

Elles lèvent les points d'arrêt que les plans d'origine réservaient à une validation humaine, pour que l'implémentation puisse tourner sans surveillance.

| ID | Décision | Raison |
|---|---|---|
| D1 | **Mode local par défaut.** Le cloud est désactivé au démarrage, et un badge Local ou Cloud apparaît sur chaque modèle et chaque réponse. | Le README promet « 0 appel API par défaut » ; la démo est « souveraine » |
| D2 | **Outil email décoché par défaut.** Une fois activé, l'agent prépare le message et un humain valide avant l'envoi. | Action externe irréversible |
| D3 | **Le débit affiché est `eval_count / eval_duration` d'Ollama**, comme `scripts/benchmark_slm.py`. Le temps de chargement et la durée totale sont affichés à part. | Rendre l'interface comparable aux benchmarks publiés |
| D4 | **Le design est implémenté dans la même série, puis validé visuellement au matin.** Le thème part de la direction de `poste-rtx3060/UX.md` §4, formalisée par `bmad-ux` avant la nuit. | Le thème et le lexique touchent toutes les pages : les faire en premier évite de retoucher chaque correctif |
| D5 | **Le serveur écoute sur `localhost` par défaut** (`.streamlit/config.toml`). L'ouverture au réseau est documentée comme un choix explicite. | Cohérence avec D1 |
| D6 | **Versions figées dans un fichier de contraintes.** La combinaison retenue doit passer `import ragas` et lancer les 5 pages. L'environnement de benchmark n'est pas touché. | La même commande d'installation donne un Ragas cassé sur une machine et fonctionnel sur l'autre (constat E1) |
| D7 | **La suite de tests de l'app est en Python (pytest).** Les parcours navigateur sont marqués `e2e` et exclus par défaut, car ils exigent Ollama. Les scripts d'audit (Python et Node) servent de modèle, puis sont remplacés. | Le repo et la CI sont en Python |

## 2. Environnements constatés

Aucune version n'est figée, et les deux machines ont installé des combinaisons différentes :

| | `poste-rtx3060` (`.venv-app`) | `pro-elitebook-x360` (`.venv`) |
|---|---|---|
| Python | 3.12.13 | 3.13.5 |
| streamlit | 1.64.0 | 1.52.1 |
| ragas / langchain-community | 0.4.3 / 0.4.2 : **`import ragas` échoue** | 0.4.1 / 0.4.1 : **`import ragas` réussit** |
| langchain / langchain-core | 1.4.2 / 1.6.5 | 1.1.3 / 1.2.0 |
| chromadb | 1.1.1 | 1.3.7 |
| crewai | 1.15.22 | 0.193.2 |
| torch | 2.14.0+cpu | 2.9.1 |

Sur `poste-rtx3060`, le `.venv` du dépôt est celui du benchmark (Python 3.14, sans Streamlit). Sur `pro-elitebook-x360`, un seul `.venv` sert aux deux usages.

## 3. Constats unifiés

**Gravité** (échelle de `poste-rtx3060`) :

- **bloquant :** la fonction est inutilisable ;
- **majeur :** l'interface ment, plante, ou expose ;
- **moyen :** chiffre ou comportement trompeur ;
- **mineur / cosmétique.**

Quand les deux audits divergent, la gravité la plus haute l'emporte. La colonne « Vu sur » indique où le constat a été reproduit ; un constat lié au code vaut pour toutes les machines, même s'il n'a été vu que sur une.

### 3.1 Environnement et fonctionnement

| ID | Constat | Gravité | Vu sur | Origine | Story |
|---|---|---|---|---|---|
| E1 | Installation non reproductible. Aucune version figée, des doublons dans `requirements.txt`, et le `.venv` documenté ne lance pas l'app sur `poste-rtx3060`. Ragas est cassé ou non selon les versions (§2) | bloquant | les deux | rtx:F0, rtx:F2 (cause 1) | 1 |
| F1 | Import de documents RAG factice : `time.sleep` à la place de l'ingestion, puis « Indexation terminée avec succès ! » | bloquant | les deux | rtx:F1, elite:F-03 | 4 |
| F2 | Benchmark RAG à 0/100 affiché comme un succès quand Ragas est indisponible | majeur | rtx | rtx:F2 (cause 2) | 5 |
| F3 | Timeout d'inférence affiché comme une trace Python (`'NoneType' … 'output_tokens'`) : chat, labo et arena ne testent pas `result.error` | majeur | rtx (arena) | rtx:F3 | 5 |
| F4 | Le débit affiché inclut le chargement et le prefill : 0,6 contre 78,5 t/s (rtx), 1,3 contre 7,9 t/s (elite) | moyen | les deux | rtx:F4, elite (§2) | 6 |
| F5 | CO₂ de session du Cockpit affiché ×1000 : des grammes présentés en kg | majeur | elite | elite:F-01 | 6 |
| F6 | L'historique d'émissions ne lit pas le fichier où le suivi écrit | moyen | elite | elite:F-02 | 6 |
| F7 | La réponse finale de l'agent Solo disparaît au rerun suivant, sans CO₂ | majeur | elite | elite:F-04 | 9 |
| F8 | Serveur exposé sur le réseau : pas de `.streamlit/config.toml`, une « External URL » est annoncée | majeur | elite | elite:F-05 | 1 |
| F9 | Le reranker choisi est ignoré | moyen | elite | elite:F-06 | 9 |
| F10 | Défauts de modèles inadaptés : premier par ordre alphabétique, modèle cloud en tête (le tri place « ☁️ » avant « 💻 »), Bonsai 27B dans l'Arena, juges choisis par nom | moyen | les deux | rtx:F5, elite:F-07 | 7 |
| F11 | Accélérateur mal détecté : « CPU Only » avec un GPU (roue torch CPU), et « Actif » affiché même sans accélérateur | mineur | les deux | rtx:F6, elite:F-08 | 5 |
| F12 | Deux collections Chroma pour le même embedding | mineur | rtx | rtx:F7 | 4 |
| F13 | L'Arena démarre avec un seul modèle | mineur | elite | elite:F-09 | 7 |
| F14 | `use_container_width` déprécié, 32 occurrences | moyen | elite (logs) | elite:F-10 | 2 |
| F15 | CodeCarbon relève 112 W constants sur un processeur de 28 W | moyen | elite | elite:F-11 | hors nuit (§6) |
| F16 | L'agent Solo oublie le modèle choisi après un passage par Crew | mineur | elite | elite:F-12 | 9 |
| F17 | Quand le garde-fou RAM bloque l'agent, la question est perdue et le besoin estimé n'est pas expliqué | mineur | elite | elite:F-13 | 5 |

### 3.2 Design, rédaction et vérité de l'interface

Les constats U1 à U18 reprennent ceux de `poste-rtx3060/UX.md`, avec la même numérotation et le détail dans ce fichier. Ceux de `pro-elitebook-x360` y sont rattachés, ou ajoutés en U19 et U20.

| ID | Constat | Gravité | Rattachés (elite) | Story |
|---|---|---|---|---|
| U1 | Aucune identité Wavestone (thème Streamlit par défaut) | moyen | U-01 | 2 |
| U2 | Emojis en guise d'icônes, doublés (« 📂 📂 »), 🧠 partagé, emojis en `<h1>` | moyen | U-03 | 2 |
| U3 | Barre d'outils de développement visible | mineur | U-01 | 2 |
| U4 | Sémantique des couleurs inversée : rouge pour l'action principale, gris pour le Reset | majeur | | 2 |
| U5 | Contrastes AA en échec en thème clair : bouton principal 3,30:1, légendes 3,68:1 | majeur | | 2 |
| U6 | Encart « base vide » en `#262730` codé en dur, titre à 1,18:1 en clair | majeur | U-05 (= rtx:F8) | 2 |
| U7 | Bouton à icône seule sans nom accessible | mineur | | 2 |
| U8 | Un module, quatre noms ; interrupteur cloud en 4 exemplaires avec 3 libellés | moyen | U-02, U-04 | 3 |
| U9 | Français et anglais mêlés, jargon exposé (« chunks », « Crew ») | moyen | | 3 |
| U10 | Formats anglais (8.1%, Sep 26), *Title Case*, pluriels, « © 2025 … v2.0.0 » | mineur | F-08 (pied de page) | 3 |
| U11 | « Opérationnel 🟢 » écrit en dur | majeur | F-08 | 5 |
| U12 | Mode cloud actif par défaut | majeur | | 8 (D1) |
| U13 | Deltas de `st.metric` détournés en étiquettes (« ↑ API Active ») | moyen | | 8 |
| U14 | L'agent peut envoyer des emails sans confirmation | majeur | | 8 (D2) |
| U15 | Reset de la base sans confirmation | moyen | | 8 |
| U16 | Historique d'émissions : « Cumul » qui redescend, unités en µ kg, trous masqués | moyen | | 10 |
| U17 | Matrices de l'Arena et du benchmark RAG : légende manquante, échelles incohérentes, noms tronqués, axe resserré | mineur | U-06 | 10 |
| U18 | Outils de l'agent masqués dès 1440 px (5 sur 9 invisibles) | moyen | | 2 |
| U19 | Juge de l'Arena trop faible : un 1B note 90/100 une réponse qui boucle | moyen | U-07 | 7 |
| U20 | Premier chargement de 8 à 26 s sans retour visuel | mineur | U-08 | 5 |

### 3.3 Questions ouvertes (pour `open_questions` de la spec)

- Badge « 💾 0.0 GB » sous les réponses du chat RAG (rtx, non investigué).
- 771 mg de CO₂ pour Qwen 3.5 0.8B dans l'Arena, contre ~100 mg pour les autres : raisonnement long probable (rtx, non vérifié).
- Le garde-fou RAM tient-il compte d'un modèle déjà chargé dans Ollama ? Il a laissé passer un modèle de 2B avec 1,7 Go libres, puis l'a bloqué avec 2,8 Go libres (elite, F17).

## 4. Stories

C'est l'ordre d'exécution proposé pour la *Story Breakdown* de `bmad-spec`. **Pour la nuit, `spec_checkpoint` et `done_checkpoint` valent `false` partout** : les décisions du §1 remplacent les validations prévues, et la revue a lieu au matin.

| id | Titre | Constats | Taille | Dépend de |
|---|---|---|---|---|
| 1 | Socle : installation figée, serveur local, banc de test sans Ollama | E1, F8 | M | — |
| 2 | Thème Wavestone, icônes et accessibilité | U1–U7, U18, F14 | L | 1 |
| 3 | Vocabulaire, rédaction et formats `fr-FR` | U8–U10 | M | 1 |
| 4 | Ingestion RAG réelle | F1, F12 | M | 2, 3 |
| 5 | Échecs visibles et états vrais | F2, F3, F11, F17, U11, U20 | M | 2, 3 |
| 6 | Chiffres justes : débit et carbone | F4, F5, F6 | M | 2, 3 |
| 7 | Choix par défaut adaptés à la machine | F10, F13, U19 | M | 2, 3 |
| 8 | Souveraineté visible et actions sensibles | U12–U15 | M | 2, 3 |
| 9 | Rien ne se perd : agent Solo et réglages RAG | F7, F9, F16 | S | 2, 3 |
| 10 | Graphiques lisibles et justes | U16, U17 | M | 6 |
| 11 | Suite e2e navigateur et accessibilité | tous (non-régression) | L | 1 à 10 |

Les stories 4 à 10 touchent souvent les mêmes fichiers (`arena.py`, `chat.py`, `solo.py`, les pages). Elles s'enchaînent dans l'ordre, sans parallélisme.

### Notes pour `invoke_dev_with`

1. **Socle.**
   - Écrire un fichier de contraintes pour l'app, sans toucher au `.venv` du benchmark ni à `scripts/benchmark_slm.py`. La combinaison doit réussir `import ragas`, et la version de Streamlit doit supporter les réglages de thème de la story 2 : le vérifier dans la documentation de cette version, pas de mémoire. Supprimer les doublons de `requirements.txt`.
   - Créer `.streamlit/config.toml` avec `server.address = "localhost"` et documenter l'ouverture au réseau (D5).
   - Poser le banc de test : `streamlit.testing.v1.AppTest` sur les 5 pages, avec un `LLMProvider` simulé, dans `tests/app/`. Déclarer le marqueur `e2e`.
   - Mettre à jour le README et `docs/TROUBLESHOOT.md`.
2. **Thème.**
   - Partir de `DESIGN.md` (issu de `bmad-ux`) et de l'ébauche de `poste-rtx3060/UX.md` §4 : `[theme.light]`, `[theme.dark]`, `chartCategoricalColors`, `toolbarMode`, `st.logo`.
   - Remplacer les emojis par des icônes `:material/…:` et supprimer tout hex en dur (encart « base vide »).
   - Rendre visibles tous les outils de l'agent, nommer les boutons à icône seule, et remplacer `use_container_width` par `width=`.
   - Police servie localement, sans CDN.
3. **Vocabulaire.**
   - Appliquer le lexique d'`EXPERIENCE.md` : un seul nom par module, identique dans la navigation (`st.navigation`/`st.Page`), la carte d'accueil, le titre et l'onglet.
   - Un seul contrôle cloud global.
   - Utilitaire de formats `fr-FR` (nombres, unités, dates) et pluriels accordés.
4. **RAG.**
   - `UploadedFile` → fichier temporaire → `RAGEngine.ingest_file`, puis afficher le nombre d'extraits réellement ajoutés ; un échec affiche une erreur.
   - Aligner le nom d'embedding par défaut de `RAGEngine` sur celui de la page.
   - Les tests écrivent dans une collection dédiée, jamais dans `data/chroma` réel.
5. **États.**
   - Tester `result.error` avant `result.metrics` dans le chat, le labo et l'arena. `EvalResult` doit pouvoir porter « non évalué ».
   - Brancher l'indicateur « Système » sur `LLMProvider.health_check()` (`src/core/llm_provider.py`).
   - Détecter l'accélérateur via NVML ou Ollama, pas via torch.
   - Quand le garde-fou RAM bloque : garder la question et expliquer le besoin.
   - Indicateur explicite pendant les premiers chargements.
6. **Chiffres.**
   - Débit selon D3.
   - Afficher `GreenTracker.stop()`, qui renvoie des grammes, dans l'unité annoncée. Test unitaire de la conversion.
   - Un seul fichier d'émissions pour le suivi et l'historique.
7. **Défauts.**
   - Modèle local en premier (D1). Choisir le plus rapide qui tient en mémoire, d'après `measured_loaded_gb` dans `config/models_catalog.json`.
   - Juge par défaut : le plus gros modèle local qui tient ; avertissement sous ~4B.
   - Bouton de l'Arena désactivé sous 2 modèles.
8. **Souveraineté.**
   - D1 et D2.
   - Remplacer les deltas détournés par des légendes ou `st.badge`.
   - Confirmation avant le Reset de la base.
9. **Persistance.**
   - Ajouter la réponse finale et son CO₂ à `agent_messages` (`solo.py:292-309`).
   - Persister le modèle choisi avec une `key` et une valeur dans `st.session_state` (`solo.py:95`).
   - Reranker : l'appliquer, ou retirer la liste.
10. **Graphiques.**
    - Suivre le skill `dataviz`. Historique : vrai cumul ou barres par session, en mg, trous visibles, fenêtre de temps.
    - Arena : légende de taille, noms complets et vue tableau. Benchmark RAG : même échelle que le podium.
11. **e2e.**
    - Convertir en `tests/e2e/` (pytest, Playwright, marqueur `e2e`) les parcours de `poste-rtx3060/playwright/` et de `pro-elitebook-x360/e2e/`.
    - Ingérer via l'interface (piège Chroma inter-processus), n'utiliser que de petits modèles configurables par variable d'environnement, et lancer axe-core en clair et en sombre.
    - Chaque constat de §3 a une assertion ou un test qui l'aurait détecté.

## 5. Capacités proposées pour `SPEC.md`

Elles reprennent CAP-1 à CAP-7 de `poste-rtx3060`, enrichies de l'audit `pro-elitebook-x360`, et ajoutent CAP-8.

- **CAP-1 Installation reproductible, app confinée.**
  - *Intent :* un environnement créé à neuf lance toutes les pages avec toutes leurs fonctions, sans rien exposer au réseau.
  - *Success :* installation depuis le fichier de contraintes, puis `import ragas` réussit, les 5 pages passent `AppTest`, et le démarrage n'annonce que `localhost`.
- **CAP-2 Ingestion RAG réelle.**
  - *Intent :* un document importé depuis l'interface est indexé et interrogeable.
  - *Success :* après l'upload d'un `.md`, le compteur augmente, et la question du document de test obtient la bonne réponse avec sa source.
- **CAP-3 Échecs visibles, états vrais.**
  - *Intent :* aucun échec n'est présenté comme un succès ni comme une trace, et aucun indicateur n'est écrit en dur.
  - *Success :*
    - un timeout affiche « Délai dépassé » et l'Arena continue ;
    - une évaluation impossible affiche « non évalué » ;
    - Ollama arrêté fait passer l'accueil à « Indisponible ».
- **CAP-4 Chiffres justes.**
  - *Intent :* le débit et le carbone affichés sont exacts et comparables au benchmark.
  - *Success :*
    - le premier message affiche un débit à ±15 % des suivants ;
    - le CO₂ de session s'écarte de moins de 5 % de la ligne du CSV de CodeCarbon ;
    - une session apparaît dans l'historique.
- **CAP-5 Défauts adaptés à la machine.**
  - *Intent :* un utilisateur qui ne touche à rien obtient une démo rapide et locale.
  - *Success :* aucun modèle présélectionné ne dépasse la mémoire disponible ; le juge par défaut fait au moins ~4B quand un tel modèle tient.
- **CAP-6 Interface à la charte, accessible et cohérente.**
  - *Success :*
    - zéro violation axe `color-contrast` ou `heading-order`, en clair comme en sombre ;
    - un seul nom par module et par commande ;
    - des formats `fr-FR` ;
    - aucun emoji décoratif ;
    - aucun avertissement de dépréciation au démarrage.
- **CAP-7 Souveraineté visible, actions sensibles maîtrisées.**
  - *Success :*
    - local par défaut, avec un badge Local ou Cloud partout ;
    - envoi d'email et Reset soumis à confirmation.
- **CAP-8 Rien ne se perd.**
  - *Intent :* ce que l'utilisateur a saisi, choisi ou obtenu survit aux reruns.
  - *Success :*
    - la réponse de l'agent et le modèle choisi survivent à un changement d'architecture ;
    - une question bloquée par le garde-fou RAM reste visible ;
    - le reranker choisi change l'ordre des sources, ou n'est plus proposé.

**Contraintes :**
- ne pas modifier `scripts/benchmark_slm.py`, `benchmarks/` ni l'environnement du benchmark ;
- tests unitaires et `AppTest` sans Ollama (providers simulés) ;
- aucun téléchargement de modèle dans les tests ;
- ne jamais écrire dans la collection Chroma réelle ;
- pas de framework CSS : `config.toml` et composants natifs ;
- polices servies localement ;
- textes d'interface en français.

**Non-objectifs :**
- nouveaux formats d'import ;
- nouvelles fonctionnalités d'agent ;
- refonte de l'architecture des pages ;
- page « Résultats de benchmark », compatibilité modèle / RAM dans la gestion des modèles, export de session (elite:N-01 à N-03, voir §6) ;
- toute modification de la v2.

## 6. Hors de la série de nuit

- **F15 (112 W de CodeCarbon)** demande le portable réel et ses sondes : c'est un spike à mener sur `pro-elitebook-x360`, pas dans une VM cloud.
- **elite:N-01 à N-03** (page de résultats de benchmark, compatibilité mémoire dans la gestion des modèles, export de session) : il faut d'abord décider si elles vont dans la v1 ou dans la v2.
- **La validation visuelle** du thème et du lexique (D4) et **l'exécution de la suite e2e** avec de vrais modèles se font au matin, sur une machine avec Ollama.

## 7. Correspondance des identifiants

| Synthèse | poste-rtx3060 | pro-elitebook-x360 |
|---|---|---|
| E1 | F0, F2 (cause 1) | — (Ragas fonctionne) |
| F1 | F1 | F-03 |
| F2 | F2 (cause 2) | — |
| F3 | F3 | — |
| F4 | F4 | observé (§2 du rapport) |
| F5 à F9 | — | F-01, F-02, F-04, F-05, F-06 |
| F10 | F5 | F-07 |
| F11 | F6 | F-08 (« Actif ») |
| F12 | F7 | — |
| F13, F14, F15, F16, F17 | — | F-09, F-10, F-11, F-12, F-13 |
| U1 à U18 | U1 à U18 (F8 = U6) | U-01 → U1 et U3 ; U-02 et U-04 → U8 ; U-03 → U2 ; U-05 → U6 ; U-06 → U17 ; F-08 → U10 et U11 |
| U19, U20 | — | U-07, U-08 |
| story 11 | story 10 | N-04 |
