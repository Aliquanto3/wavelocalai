# Rapport de nuit — fiabilisation du frontend (2026-09-27)

Session autonome, du 27/09 à 03:18 UTC au 27/09 à 12:25 UTC, sur la branche `claude/fiabilisation-frontend` créée depuis `master` (e3f684f). Chaque story est passée par `bmad-build-auto` : plan, implémentation, revue en 4 couches (blind hunter, edge case hunter, verification gap, alignement sur l'intention), correctifs, puis vérification. Environnement : VM Linux, Python 3.12, `.venv-app`, Streamlit 1.64.0, **sans Ollama**.

Les 11 stories sont `done`. Aucune n'a été annulée ni bloquée.

## Base de tests au départ

Sur `master` e3f684f, `pytest tests/unit` donnait **153 réussis et 9 échecs** (`tests/app` n'existait pas) :

- les 4 échecs connus (E3) : `test_inference_reelle_ollama`, `test_get_langchain_model_mistral`, `test_pull_model_cloud_raises_error`, `test_get_all_languages` ;
- 5 échecs propres à la VM, dans `test_models_db.py`, faute de `data/models.json` : `test_models_db_loaded`, `test_get_model_info_exists`, `test_get_all_friendly_names`, `test_exact_match`, `test_tag_with_latest`.

`ruff` relevait 18 remarques, à titre informatif.

À la fin de la nuit, `pytest tests/unit tests/app` donne **763 réussis et 0 échec**. `tests/e2e` compte 35 tests, collectés sans erreur et exclus par défaut.

## Stories

| Story | Statut | Commit | Tests (unit + app) | Durée |
|---|---|---|---|---|
| 1 — Socle figé, serveur local, CI, tests au vert | done | 8dfc946 | 171 | 36 min |
| 2 — Thème Wavestone, icônes Material, accessibilité | done | dad907a | 191 | 58 min |
| 3 — Navigation, vocabulaire unique, formats fr-FR | done | c3df9c6 | 308 | 39 min |
| 4 — Ingestion réelle des documents | done | 8b07942 | 336 | 21 min |
| 5 — Échecs visibles et états vrais | done | 1467d32 | 439 | 46 min |
| 6 — Débit selon D3, carbone dans la bonne unité | done | 1b91fa2 | 497 | 35 min |
| 7 — Choix par défaut adaptés à la machine | done (1 boucle `bad_spec`) | f7b0df9 | 571 | 62 min |
| 8 — Souveraineté visible, actions sensibles confirmées | done | 12215a9 | 638 | 68 min |
| 9 — Agent, modèle choisi et reranker conservés | done | b4e4ac5 | 684 | 41 min |
| 10 — Graphiques lisibles et justes | done | 68437af | 731 | 67 min |
| 11 — Suite e2e navigateur et accessibilité | done | d0efcdf | 763 (+35 e2e exclus) | 67 min |

Pour chaque story, le fichier `_bmad-output/specs/spec-fiabilisation-frontend/stories/<id>-*.md` contient le journal de triage de la revue, le résultat et les éléments différés.

## À vérifier à la main, par story

Toutes les stories demandent de vérifier le rendu en clair et en sombre. La VM ne dispose ni d'Ollama ni de modèles : aucune inférence réelle n'a été lancée.

- **1** :
  - la CI de la PR : Windows, macOS, Python 3.10 et 3.11 (`constraints.txt` universel, installé réellement sur Linux 3.12 seulement) ;
  - le lancement depuis la racine du dépôt, obligatoire (`.streamlit/config.toml` est lu dans le dossier courant) ;
  - la télémétrie Chroma, active par défaut dans l'app (coupée seulement en test) ;
  - `docs/COMMANDES_UTILES.md`, qui cite encore `.venv`.
- **2** :
  - la police Inter, le logo et le favicon locaux ;
  - aucune requête vers fonts.gstatic.com ;
  - l'apparence du thème sur un vrai écran, dans les deux modes.
- **3** :
  - la navigation `st.navigation` (URL conservées) ;
  - les formats de nombres et de dates, qui suivent la langue du navigateur.
- **4** :
  - l'import d'un vrai PDF et d'un .docx sous Windows (`docx2txt` 0.9, `followup_review_recommended: true`) ;
  - question, réponse et sources dans la Discussion, avec Ollama.
- **5** :
  - l'accueil avec Ollama démarré puis arrêté ;
  - l'accélérateur affiché sur un poste GPU ;
  - l'état « non évalué » du juge avec de vrais modèles.
- **6** :
  - le débit (D3), à comparer au benchmark sur un même modèle (tolérance ±15 %) ;
  - le CO₂ de session, dans la bonne unité après une vraie génération.
- **7** : les choix par défaut sur 2 postes de mémoire différente. Sur le vrai catalogue à 6,5 Go, le résultat attendu est :
  - premier modèle `gemma3:1b` ;
  - juge `qwen3.5-ud:9b-q3_k_xl` ;
  - Arène : `gemma3:1b`, `lfm2.5-thinking:1.2b` et `granite4:350m`.
- **8** :
  - le cloud désactivé au démarrage ;
  - les badges Local, Cloud et Origine inconnue ;
  - le brouillon d'email et l'envoi seulement après confirmation, à tester avec un SMTP de test ;
  - le vidage de la base après confirmation ;
  - les outils de l'équipe d'agents, qui s'exécutent désormais (correctif de l'adaptateur de `crew_engine`).
- **9** :
  - la réponse de l'agent conservée après un rerun ;
  - `usage_metadata` réel d'Ollama via LangGraph (jetons de sortie) ;
  - le score d'un vrai CrossEncoder.
- **10** :
  - l'historique des émissions, la matrice de l'Arène et celle de l'évaluation, sur de vraies données ;
  - la lisibilité des étiquettes et des légendes, en clair et en sombre.
- **11** :
  - le **premier passage réel** : `pytest tests/e2e -m e2e` après `playwright install chromium`, avec les modèles définis par les variables d'environnement (voir `tests/e2e/README.md`) ;
  - le test axe en sombre échouera tant que la couleur primaire `#6A4DE6` n'est pas tranchée (voir plus bas) ;
  - le test de l'accélérateur suppose `nvidia-smi` dans le PATH.

## Choix faits sans validation

**Story 1**
- `constraints.txt` est universel (`uv pip compile --universal --python-version 3.10`).
- Les actions GitHub sont en v7, dernier tag majeur vérifié par `git ls-remote`.
- La télémétrie Streamlit est coupée (`gatherUsageStats = false`).
- `langchain-community` 0.4.2 est exclu.
- La CI tourne désormais sur `master`.

**Story 2**
- `greenTextColor` vaut `#0C6E3C` en clair, une valeur hors DESIGN.md (le défaut était à 4,03–4,49:1).
- Le wordmark est en `#6A4DE6` (3,23:1 sur la barre latérale sombre).
- Le favicon est un « W » blanc sur `#451DC7`.
- « 👋 Bonjour ! » reste en titre : c'est l'exception de DESIGN.md, contraire à EXPERIENCE.md.
- Le thème suit la préférence système.

**Story 3**
- `src/app/pages/` est déplacé en `src/app/views/`, parce qu'un dossier `pages/` maintient le mode multipage v1.
- Le pied de page n'affiche pas de version.
- Les tableaux sont au format « localized ».
- Les noms d'outils sont ceux d'EXPERIENCE.md.

**Story 4**
- Un document déjà présent est refusé à l'import, pas remplacé.
- Les erreurs de lecture remontent par `DocumentReadError`, ce qui change le comportement de `process_file`.

**Story 5**
- L'état « Système » ne repose que sur la sonde Ollama : `health_check_all` appellerait le cloud, et l'appel à Anthropic est payant.
- Le juge ne donne une note que si elle est explicite ; sinon, il affiche « non évalué ».
- `test_evaluate_handles_ragas_exception` n'attend plus 0.0 mais « non évalué » : l'ancien test figeait le défaut F2.
- « Libérer la mémoire » ne vide plus la conversation.

**Story 6**
- Une comparaison utilise une seule unité, celle de la plus petite valeur non nulle.
- L'historique ne contient que les sessions de l'app.
- « (estimé) » s'affiche sans `eval_duration`.
- Le débit est arrondi à 2 décimales.

**Story 7**
- Le juge est choisi par empreinte mémoire parmi les juges fiables, et non par nombre de paramètres, qui donnait Bonsai 27B 1 bit. C'est une correction de spec issue de la revue.
- « Le plus rapide » est le modèle à la plus petite empreinte, faute de mesures de vitesse.
- La marge est de 1,10, avec un repli ×1,25.
- Les agents sont triés local d'abord, ce qui s'écarte de la matrice au profit de D1.
- Les tags `:cloud` et `-cloud` sont traités comme cloud.

**Story 8**
- Un tag inconnu reçoit un badge gris « Origine inconnue ».
- L'équipe d'agents n'envoie jamais d'email : le brouillon est rendu dans son rapport.
- L'envoi se fait en texte brut seulement.
- Le vidage de la base vide aussi l'historique de la Discussion.

**Story 9**
- Le CO₂ de l'agent compte tous les jetons du tour.
- Le libellé est « score de reclassement » (valeur brute), pas « pertinence ».
- Les rerankers sont triés par ordre alphabétique.

**Story 10**
- L'historique affiche une barre par session, sans cumul, sur une fenêtre de 7 jours par défaut.
- Au-delà de 4 modèles, des formes s'ajoutent aux couleurs.
- Les jetons de couleur viennent d'un module privé de Streamlit (import protégé, avec repli).
- `python-dateutil` est importé sans être déclaré.

**Story 11**
- Les dépendances e2e sont dans `requirements.txt` et non dans un fichier séparé, comme le demande la spec.
- Les composants désactivés sont exemptés du contraste (WCAG 1.4.3) et listés à part.
- La garde réseau ne couvre que le processus de l'app : ni ses sous-processus, ni Ollama.

**Pour toute la nuit**
- `data/` a été créé par la suite de tests de base (`config.py` crée les dossiers à l'import). Sa suppression a été refusée par le garde-fou, donc il reste en place ; il est ignoré par git.

## Écarts de contraste mesurés

Mesures faites avec axe-core dans Chromium, fenêtre de 1440 px, fournisseurs simulés.

| Mode | Élément | Couleurs | Ratio | Origine |
|---|---|---|---|---|
| clair (avant) | légendes `st.caption` | #83858c / #fff | 3,68:1 | thème par défaut, corrigé en story 2 |
| clair (avant) | curseur, couleur primaire | #ff4b4b / #fff | 3,30:1 | corrigé en story 2 |
| clair (avant) | texte gris | #808080 / #fff | 3,94:1 | corrigé en story 2 |
| clair (avant) | deltas verts | #158237 | 4,03 à 4,49:1 | corrigé (`greenTextColor`) |
| clair (après) | pastille désactivée « Outil non configuré » | #9d9da1 / #fff | 2,70:1 | `textColor` à 40 % d'opacité (dérivé par Streamlit) ; composant inactif, exempté par WCAG |
| sombre (après) | valeur du curseur | #6A4DE6 / #0a0a14 | 3,57:1 | `primaryColor` de DESIGN.md utilisé comme couleur de texte |
| sombre (après) | pastilles d'outils sélectionnées | #6A4DE6 / #141129 | 3,34:1 | idem |
| sombre (après) | pastille désactivée | #686870 / #0a0a14 | 3,56:1 | `textColor` estompé ; composant inactif |

La nuit a aussi fait passer les violations `heading-order` de 7 à 0. Les badges (vert, orange, gris) ne présentent aucune violation.

Correction par rapport aux notes de la nuit : la revue de la story 11 a montré que la pastille désactivée n'a pas une couleur native. C'est `textColor` à 40 % d'opacité, et les ratios mesurés correspondent exactement.

Aucun contraste n'a été corrigé par du CSS.

**Décision à prendre :** en mode sombre, `#7A5FEA` donne 4,36:1 en texte et 4,51:1 sous du blanc ; `#8468EC` donne 4,85:1 et 4,06:1. C'est à trancher dans DESIGN.md.

La palette des graphiques a été validée par le script `dataviz` : tout passe en clair comme en sombre, avec un avertissement en clair sur `#C98A00` (2,87:1). C'est pourquoi les étiquettes et le tableau sont obligatoires.

## Questions ouvertes

1. Quelle couleur primaire retenir pour le mode sombre (`#6A4DE6`, `#7A5FEA` ou `#8468EC`) ? C'est la seule chose qui bloque le test axe en sombre.
2. `greenTextColor` `#0C6E3C` et « 👋 Bonjour ! » en titre : faut-il les inscrire dans DESIGN.md ou les revoir ?
3. Faut-il mettre à jour AGENTS.md ? Il est périmé : CI sur `master`, `tests/app` et `tests/e2e`, `views/` au lieu de `pages/`, et les 4 tests en échec connus passent désormais.
4. Benchmark : mistralai 2.x rend `MISTRAL_AVAILABLE` faux dans `benchmark_slm.py`. C'est hors périmètre et demande une PR dédiée au benchmark.
5. Les tests écrivent encore dans `data/logs` et les benchmarks, via l'import de `benchmark_slm.py` et `config.py`.
6. « Libérer la mémoire » ne décharge pas les modèles d'Ollama. Faut-il ajouter un `keep_alive: 0` ?
7. La VRAM n'est pas prise en compte dans le choix du juge : il peut déborder sur une carte de 6 Go.
8. La formule du CO₂ est recopiée dans 7 onglets. Faut-il la factoriser dans `src/core` (v1 ou v2) ?
9. Autres points différés :
   - `chat.py:218` : `_calculate_metrics` reçoit le libellé au lieu du nom du modèle ;
   - le rapport de l'équipe d'agents n'est pas conservé ;
   - les noms sont tronqués dans le multiselect natif ;
   - les barres de l'historique sont fines sur les longues périodes.

La liste complète des éléments différés se trouve dans le champ `deferred:` de chaque story.
