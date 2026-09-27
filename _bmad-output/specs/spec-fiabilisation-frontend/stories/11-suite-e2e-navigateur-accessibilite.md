---
title: 'Suite e2e navigateur et accessibilité'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_revision: '68437af1e7ad7ba207b520ee6de905949c96b551'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/docs/audits/frontend-2026-09/SYNTHESE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      Contraste sombre de la couleur primaire #6A4DE6 (curseur 3,57:1, pastilles sélectionnées 3,34:1) : le test axe en sombre échoue tant que DESIGN.md n'est pas tranché.
    evidence: |-
      Mesure axe-core sur l'app à fournisseurs simulés ; aucun skip ni xfail. Candidats : #7A5FEA ou #8468EC.
    location: >-
      .streamlit/config.toml ; DESIGN.md
    severity: medium
  - summary: >-
      Garde réseau limitée au processus du lanceur : sous-processus et Ollama non audités.
    evidence: |-
      Hook sys.audit dans le processus Streamlit ; documenté dans tests/e2e/README.md.
    location: >-
      tests/e2e/launch_app.py
    severity: low
  - summary: >-
      Texte du garde-fou mémoire recopié dans test_agents.py faute de constante exposée par src/.
    evidence: |-
      « Mémoire vive insuffisante » vient de src/core/resource_manager.py ; exposer une constante demanderait une modification de src/ hors périmètre.
    location: >-
      tests/e2e/test_agents.py ; src/core/resource_manager.py
    severity: low
  - summary: >-
      Test de l'accélérateur fondé sur nvidia-smi : faux échec possible si le GPU est visible par l'app mais nvidia-smi absent du PATH.
    evidence: |-
      Pas de poste GPU dans la VM pour valider.
    location: >-
      tests/e2e/test_pages.py
    severity: low
  - summary: >-
      AGENTS.md à mettre à jour (suite e2e, CI sur master, views/ au lieu de pages/, tests en échec obsolètes).
    evidence: |-
      Hors périmètre de la story ; noté pour le rapport de nuit.
    location: >-
      AGENTS.md
    severity: low
---

<intent-contract>

## Intent

**Problem:** Les parcours qui ont révélé les constats des audits (scripts `poste-rtx3060/playwright/` en Python et `pro-elitebook-x360/e2e/` en Node) sont des scripts manuels hors de la suite : rien n'empêche un constat corrigé par les stories 1 à 10 de revenir. Ces parcours exigent Ollama et de vrais petits modèles, absents de la VM.

**Approach:** Convertir ces parcours en tests pytest + Playwright sous `tests/e2e/`, marqués `e2e` et exclus par défaut, lancés contre l'app réelle avec de petits modèles configurables par variables d'environnement, avec un contrôle axe-core en clair et en sombre ; chaque constat du §3 de SYNTHESE.md a une assertion ou un test qui l'aurait détecté. Cette nuit : écrits, collectés, exclus par défaut ; exécutés au matin sur un poste avec Ollama.

## Boundaries & Constraints

**Always:** marqueur `e2e` sur chaque test de `tests/e2e/`, exclu par le `-m "not e2e"` de `pytest.ini` ; l'app testée tourne dans un sous-processus avec Chroma, journaux et émissions redirigés vers un dossier temporaire (jamais `data/chroma` ni `data/logs` réels) ; ingestion par l'interface (piège Chroma inter-processus) ; modèles choisis par variables d'environnement documentées, petits par défaut, jamais téléchargés par les tests (un modèle absent fait échouer le test avec un message qui dit quoi installer) ; aucune requête hors localhost (vérifiée) ; dépendances versionnées dans `requirements.txt` et `constraints.txt` (versions vérifiées sur PyPI ou par installation, jamais de mémoire) ; aucun CDN pour axe-core.

**Never:** exécuter les tests `e2e` dans la VM (pas d'Ollama) ; appeler un fournisseur cloud ou envoyer un email réel ; `skip` ou `xfail` pour masquer un échec ; télécharger un modèle ou un navigateur pendant les tests ; toucher le benchmark ou `src/core/config.py`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Suite par défaut | `pytest tests/unit tests/app` ou `pytest` sans `-m` | Aucun test e2e collecté comme sélectionné | — |
| Collecte e2e | `pytest tests/e2e -m e2e --collect-only` | Tous les tests collectés, sans erreur d'import | — |
| Poste avec Ollama | `pytest tests/e2e -m e2e` et les modèles de la variable d'environnement installés | Parcours exécutés contre l'app réelle | modèle absent → échec explicite nommant le modèle à installer |
| Accessibilité | 5 pages, clair puis sombre | Aucune violation `color-contrast` ni `heading-order` imputable au thème ; les couleurs natives sans clé de thème sont listées, pas masquées | — |
| Données de l'utilisateur | un `data/chroma` réel existe | Intact après la suite | — |
| Traçabilité | chaque constat E1–E3, F1–F17 (hors F15), U1–U20 | Au moins un test ou une assertion nommé dans la table de traçabilité | constat non testable en e2e → renvoi vers le test unitaire ou AppTest qui le couvre |

</intent-contract>

## Code Map

- `docs/audits/frontend-2026-09/poste-rtx3060/playwright/` -- `common.py` (`settle` : attendre la fin du rerun Streamlit, `select_option` : taper pour filtrer les listes virtualisées, `report` : exceptions et alertes), `t_inference.py`, `t_rag_upload.py`, `t_rag_chat.py`, `t_rag_eval.py`, `t_agent_solo.py`, `t_agent_crew.py`, `t_cleanup.py`, `ux_capture.py`, `doc_test_rag.txt` (document de test).
- `docs/audits/frontend-2026-09/pro-elitebook-x360/e2e/e2e.js` -- étapes `0-accueil-local`, `1-socle`, `2-chat`, `3-lab`, `4-arena`, `5-gestion-modeles`, `6-rag-chat`, `7-rag-upload`, `8-agent-solo`, `9-crew-rendu` ; `lastCsvEmissionKg` (lecture du CSV CodeCarbon) ; `sample_doc.md`.
- `/tmp/nuit/axe/launch_fake.py` (hors dépôt) -- exemple de lanceur qui redirige `vector_store.CHROMA_DIR`, `green_monitor.LOGS_DIR`, `config.EMISSIONS_DIR` vers un dossier temporaire puis appelle `streamlit.web.cli.main` ; le lanceur e2e fait la même redirection **sans** simuler les fournisseurs.
- Navigation (`src/app/modules.py`) : URL `/`, `/Socle_Hardware`, `/Inference_Arena`, `/RAG_Knowledge`, `/Agent_Lab` ; interrupteur « Autoriser le cloud » (désactivé au démarrage) ; libellés actuels des boutons et onglets dans `src/app/tabs/**` (à lire, ne pas recopier ceux des scripts d'audit, périmés).
- `pytest.ini` -- marqueur `e2e` déclaré, `-m "not e2e"` dans `addopts`.
- Dépendances candidates (PyPI, 2026-09-27) : `playwright` 1.63.0 (Python ≥ 3.10), `axe-playwright-python` 0.1.8 (embarque axe-core) ; à installer dans `.venv-app` et figer dans `constraints.txt` (commande de son en-tête, versions existantes gardées). Navigateurs : `PLAYWRIGHT_BROWSERS_PATH` dans la VM ; `playwright install chromium` documenté pour le poste.

## Tasks & Acceptance

**Execution:**
- `tests/e2e/conftest.py` -- lancement de l'app dans un sous-processus avec dossiers temporaires (port libre, attente de `/_stcore/health`, arrêt garanti), navigateur Playwright, contexte clair/sombre, garde « aucune requête hors localhost », lecture des variables d'environnement des modèles, vérification préalable qu'Ollama répond et que les modèles sont installés (échec explicite sinon).
- `tests/e2e/launch_app.py` -- lanceur avec redirection des dossiers de données.
- `tests/e2e/test_*.py` -- parcours : accueil (Local, Disponible), Sobriété et matériel (CO₂ de session dans la bonne unité, historique), Chat libre (réponse, débit, chargement à part, badge), Banc d'essai, Arène (2 modèles, juge, délai dépassé non bloquant si simulable par un délai court), gestion des modèles (lecture seule), Assistant documentaire (import du document de test par l'interface, compteur, question et source, confirmation du vidage sur la collection temporaire), agent seul (réponse conservée, email décoché et confirmation), équipe d'agents (rendu), axe-core en clair et en sombre sur les 5 pages.
- `tests/e2e/README.md` -- prérequis (Ollama, modèles, `playwright install chromium`), variables d'environnement, commande, et **table de traçabilité** constat → test (y compris renvois vers les tests unitaires ou AppTest pour les constats non observables au navigateur).
- `requirements.txt`, `constraints.txt` -- dépendances e2e ; installation dans `.venv-app`.
- `tests/app/` ou `tests/unit/` -- un test qui vérifie que tout `tests/e2e/test_*.py` porte le marqueur `e2e` et que la suite par défaut n'en sélectionne aucun.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.
- Given `pytest tests/e2e -m e2e --collect-only -q` dans la VM, when la collecte se termine, then tous les tests e2e sont collectés sans erreur.
- Given `pytest --collect-only -q` sans `-m`, when la collecte se termine, then aucun test de `tests/e2e/` n'est sélectionné.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 30 findings — high 0, medium 10, low 14, false 0, maybe-false 6
- findings:
  - `[medium]` `[patch]` (verification-gap) isolation Chroma non vérifiée avant « Vider définitivement » — test unitaire de `redirect_data` en sous-processus ; précondition dans `test_clear_needs_confirmation`.
  - `[medium]` `[patch]` (verification-gap, edge) garde « aucune requête hors localhost » jamais testée — cas `is_local_host`, `is_external_url`, hook d'audit en sous-processus.
  - `[medium]` `[patch]` (edge, blind) connexions externes au démarrage ou entre tests non contrôlées — journal complet vérifié à l'arrêt de l'app.
  - `[medium]` `[patch]` (edge, blind) WebSockets non interceptés — `route_web_socket` sur les URL externes.
  - `[medium]` `[patch]` (verification-gap, edge) contrastes estompés du thème classés « natifs » — mélange palette/fond à opacité quelconque ; composants désactivés exemptés (WCAG 1.4.3) et listés à part ; README corrigé.
  - `[medium]` `[patch]` (blind) sorties d'agents, exports et base de benchmark non redirigés ; instantané trop étroit — redirection et instantané élargis (outputs/, data/exports, data/benchmarks.db, data/models.json).
  - `[medium]` `[patch]` (intent) débit comparé sur des prompts différents, sans minimum de jetons ni état froid — `test_lab_throughput_excludes_loading` (même prompt, 30 jetons, /api/ps, ±15 %).
  - `[medium]` `[patch]` (intent) parcours d'évaluation RAG (t_rag_eval) non converti — `test_quality_evaluation_scores_or_not_evaluated`, table de traçabilité (F2).
  - `[medium]` `[patch]` (edge) sélection par sous-chaîne qui choisit un autre modèle — tag, puis nom exact, échec si ambigu.
  - `[medium]` `[defer]` (blind) axe en sombre en échec sur #6A4DE6 — décision DESIGN.md ; échec gardé, documenté.
  - `[low]` `[patch]` (edge, verification-gap) tags comparés bruts — `normalize_tag` des deux côtés.
  - `[low]` `[patch]` (edge, verification-gap) `WAVELOCALAI_E2E_TIMEOUT_S` à double sens — `WAVELOCALAI_E2E_SHORT_TIMEOUT_S`.
  - `[low]` `[patch]` (edge) délais nuls, négatifs ou non numériques — `pytest.fail` nommant la variable.
  - `[low]` `[patch]` (edge) IndexError sur message d'erreur vide — repli sur `repr(e)`.
  - `[low]` `[patch]` (edge) seul le processus meneur tué après SIGTERM — `killpg(SIGKILL)`.
  - `[low]` `[patch]` (edge) boucle de vidage du multiselect sans borne — 50 essais.
  - `[low]` `[patch]` (edge) `settle` à fenêtre fixe — argument `until` après chaque action vérifiée.
  - `[low]` `[patch]` (edge) tout avertissement pris pour le garde-fou mémoire — filtre sur le texte.
  - `[low]` `[patch]` (edge) police Inter non chargée si Aptos installée — `@font-face` déclaré et URL locale en 200.
  - `[low]` `[patch]` (edge) toute mention « deprecat » dans le journal — marqueurs Streamlit seulement.
  - `[low]` `[patch]` (blind) assertions sur code retour ou « ERROR » brut — messages de pytest.
  - `[low]` `[patch]` (blind) URL et modèle d'embedding codés en dur — importés de `src/app/modules.py` et `DEFAULT_EMBEDDING_MODEL`.
  - `[low]` `[patch]` (intent) test de l'accélérateur limité à la présence — comparaison au nom rendu par nvidia-smi, « Aucun » sans GPU.
  - `[low]` `[patch]` (intent) README muet sur l'absence d'exécution réelle — note en tête.
  - `[maybe-false]` `[reject]` (blind) xfail pour les deux échecs axe en sombre — interdit (aucun skip ni xfail pour masquer un échec).
  - `[maybe-false]` `[reject]` (blind) `requirements-e2e.txt` séparé — la spec demande `requirements.txt`.
  - `[maybe-false]` `[reject]` (edge, verification-gap) `constraints.txt` absent du patch revu — présent dans l'arbre de travail, commité avec la story.
  - `[low]` `[defer]` (edge) sous-processus et Ollama hors de la garde réseau — documenté.
  - `[low]` `[defer]` (intent) AGENTS.md périmé — rapport de nuit.
  - `[maybe-false]` `[reject]` (verification-gap) attribution « native » d'« Outil non configuré » — doublon du correctif de classification.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `.venv-app/bin/python -m pytest tests/e2e -m e2e --collect-only -q -p no:cacheprovider` -- expected: N tests collected, 0 errors
- `.venv-app/bin/python -m pytest --collect-only -q -p no:cacheprovider tests/e2e` -- expected: 0 selected (tous désélectionnés)

## Auto Run Result

Status: done

**Résumé :** suite `tests/e2e/` (pytest + Playwright, marqueur `e2e`, exclue par défaut) : lanceur à données redirigées vers un dossier temporaire, contrôle d'Ollama et des modèles (échec explicite nommant le modèle), garde réseau (navigateur, WebSocket, audit `socket.*` du serveur), parcours accueil, Sobriété, Chat, Banc d'essai (débit hors chargement), Arène (juge, délai dépassé), gestion des modèles, Assistant documentaire (import par l'interface, question et source, évaluation, vidage confirmé), agent seul, équipe ; axe-core clair et sombre sur les 5 pages ; table de traçabilité E1–E3, F1–F17, U1–U20.

**Fichiers :** `tests/e2e/` (lanceur, conftest, helpers, API Ollama, 7 modules, README, document de test) ; `tests/unit/test_e2e_suite.py` ; `tests/app/test_socle.py` ; `requirements.txt`, `constraints.txt` (`playwright` 1.63.0, `axe-playwright-python` 0.1.8).

**Revue :** 24 correctifs (9 medium, 15 low), 3 différés, 5 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les garanties de sécurité des données et de souveraineté sont désormais couvertes par des tests unitaires.

**Vérification :** `pytest tests/unit tests/app` : 763 réussis ; `pytest tests/e2e -m e2e --collect-only` : 35 collectés, 0 erreur ; `pytest --collect-only tests/e2e` : 35 désélectionnés. Suite jamais exécutée contre Ollama (VM sans Ollama).

**Risques :** premier passage réel au matin ; échec attendu d'axe en sombre (#6A4DE6) ; sélecteurs Streamlit (`data-testid`) sensibles aux montées de version ; test d'accélérateur dépendant de nvidia-smi.
