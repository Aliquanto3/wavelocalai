---
title: 'Rien ne se perd : agent et réglages RAG'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_revision: '12215a92af855a2a3ea75b94794863add4072039'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      Rapport de l'équipe d'agents non conservé entre les reruns.
    evidence: |-
      Rendu seulement en direct après kickoff() ; EXPERIENCE.md vise les réponses des agents.
    location: >-
      src/app/tabs/agent/crew.py
    severity: medium (unverified)
  - summary: >-
      Formule de CO₂ par réponse recopiée dans sept onglets.
    evidence: |-
      rag/chat, rag/eval, inference/chat, lab, arena, solo, metrics_service.
    severity: low
---

<intent-contract>

## Intent

**Problem:** La réponse finale de l'agent seul disparaît au rerun suivant, sans CO₂ ni badge (F7) ; le modèle choisi pour l'agent seul revient au premier de la liste après un passage par l'équipe d'agents (F16) ; le reranker choisi dans l'Assistant documentaire n'est jamais appliqué, et changer d'embedding le désactive en silence (F9).

**Approach:** Ajouter la réponse finale (avec son CO₂, son modèle et son badge) à l'historique de l'agent ; conserver le modèle choisi dans l'état de session hors widget ; appliquer réellement le reranker choisi (ou « Aucun ») sans que les autres réglages le réinitialisent.

## Boundaries & Constraints

**Always:** l'historique envoyé au moteur ne contient que de vrais tours utilisateur/assistant (ni journaux d'outils, ni questions bloquées), et la question courante n'y figure qu'une fois ; CO₂ de la réponse calculé comme dans les autres onglets (`CarbonCalculator` : tokens de sortie, modèle cloud ou local) et affiché avec `format_co2` ; badge Local/Cloud de la réponse conservé (fonctions de `src/app/ui.py`) ; un réglage proposé agit réellement, sinon il est retiré (EXPERIENCE.md) ; tests sans Ollama ni téléchargement (moteur, reranker et embeddings simulés).

**Never:** changer les stratégies de recherche au-delà de ce qu'exige l'application du reranker ; refaire les graphiques (story 10) ; télécharger un modèle de reranking ; toucher `src/core/config.py` ou le benchmark.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Réponse conservée | agent seul, réponse finale, puis rerun | La réponse reste dans l'historique avec son CO₂, son modèle et son badge | — |
| Erreur de l'agent | événement `error` | Le tour en erreur reste visible comme une erreur, non envoyé au modèle comme réponse | — |
| Historique envoyé | 2ᵉ question après une réponse avec outils | Le moteur reçoit Q1, R1 puis Q2 une seule fois ; aucun journal d'outil | — |
| Modèle conservé | choix du 2ᵉ modèle, passage en équipe, retour en agent seul | Le 2ᵉ modèle reste sélectionné | modèle disparu de la liste → premier de la liste |
| Premier affichage | aucun choix enregistré | Défaut de la règle (premier de la liste) | — |
| Reranker choisi | reranker « R » disponible, choisi | `RAGEngine` utilise « R » ; l'ordre des sources suit ses scores | chargement en échec → message d'erreur, reranker « Aucun » |
| Reranker retiré | « Aucun » choisi | Aucun reranker appliqué | — |
| Changement d'embedding | reranker « R » actif, nouvel embedding choisi | « R » reste actif | — |
| Aucun reranker installé | dossier absent | Seul « Aucun » proposé, sans effet | — |
| Pertinence | sources reclassées | La pertinence affichée vient du score réel (`rerank_score`), pas une valeur fixe | score absent → « — » |

</intent-contract>

## Code Map

- `src/app/tabs/agent/solo.py:469-502` -- branche `final_answer` qui ne fait qu'afficher ; l.502 : commentaire orphelin « (Carbon Calc et st.rerun inchangés) » (l'ajout à `agent_messages` a disparu au commit f056a4f) ; `error` (l.489-493) non conservé.
- `src/app/tabs/agent/solo.py:332-362` -- rendu de l'historique : `role`, `type == "tool_log"` (`tool`, `content`, `done`), `thought`, `blocked`, bouton de téléchargement, `carbon_mg` (jamais renseigné) ; pas de badge dans l'historique. Modèle à suivre : `src/app/tabs/rag/chat.py:105-119,251-266` (stocke `model_tag`, `model_name`, `is_cloud`, rend `badge_markdown`).
- `src/app/tabs/agent/solo.py:382-383,414-415` et `src/core/agent_engine.py:124-161` -- `run_stream(user_query, chat_history, system_prompt)` convertit l'historique (user → `HumanMessage`, assistant → `AIMessage`, sans regarder `type`) puis ajoute toujours `user_query` : la question est envoyée deux fois et les journaux d'outils partent comme réponses. Les événements (`tool_call`, `tool_result`, `final_answer`, `error`) ne portent aucun compte de tokens : l'ajouter à `final_answer` depuis `AIMessage.usage_metadata` (sinon estimation par longueur, comme les fournisseurs).
- CO₂ dans les autres onglets : `src/app/tabs/rag/chat.py:224-248`, `inference/chat.py:28-45` (`get_model_info` → `CarbonCalculator.compute_mistral_impact_g` ou `compute_local_theoretical_g`, en grammes, `src/core/green_monitor.py:55-111`).
- `src/app/tabs/agent/solo.py:274` -- `st.selectbox("Modèle", sorted_labels, label_visibility="collapsed")` sans clé ni index : son état est nettoyé quand le mode équipe est affiché. Modèle : `crew.py:348-354` (tag gardé dans `crew_agents`, `index=` recalculé). Radio de mode : `views/04_Agent_Lab.py:41-46`.
- `src/app/views/03_RAG_Knowledge.py:81-86,195-196,213-226` -- reranker initial = premier dossier local ; `sel_rerank` jamais appliqué (commentaire « Reranker change logic would go here ») ; changement d'embedding via `set_models(embedding_name=…)` qui remet le reranker à `None`.
- `src/core/rag_engine.py:50-69,94-101` -- `set_models(embedding_name=None, reranker_name=None)` : `reranker_name` absent = `None` ≠ « inchangé » ; recharge tout même pour le seul reranker.
- `src/core/rag/strategies/{naive,hyde,self_rag}.py` -- appliquent déjà `reranker.predict` (`metadata["rerank_score"]`) ; `hyde.py:66-86` renvoie 2k extraits sans reranker.
- `src/app/tabs/rag/chat.py:93` -- pertinence affichée = `metadata.get("score", 0)`, jamais renseigné.
- Tests existants : `tests/app/test_states.py:608-696` (`FakeAgentEngine`, `histories`), `tests/app/test_theme.py:282-318` (défaut du sélecteur de l'agent), `tests/app/test_sovereignty.py:161-359` (bascule de mode), `tests/unit/test_rag_strategies.py`, `tests/app/conftest.py:90-100` (reranker simulé).

## Tasks & Acceptance

**Execution:**
- `src/core/agent_engine.py` -- tokens de sortie dans `final_answer` ; historique filtré sur les vrais tours.
- `src/app/tabs/agent/solo.py` -- réponse et erreur conservées (CO₂, modèle, badge, raisonnement) ; question courante non dupliquée ; modèle choisi gardé en session.
- `src/core/rag_engine.py` -- changement de reranker seul, sans toucher l'embedding ; `set_models` qui distingue « inchangé » de « Aucun ».
- `src/app/views/03_RAG_Knowledge.py` -- reranker choisi appliqué ; embedding changé sans perdre le reranker.
- `src/core/rag/strategies/hyde.py` -- k extraits sans reranker ; `src/app/tabs/rag/chat.py` -- pertinence réelle.
- `tests/` -- chaque ligne de la matrice.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 34 findings — high 0, medium 10, low 16, false 1, maybe-false 7
- findings:
  - `[maybe-false]` `[defer]` (intent) rapport de l'équipe d'agents non conservé entre les reruns (lecture large de CAP-8) — hors F7 ; noté.
  - `[low]` `[reject]` (intent) dédoublonnage de l'historique hors F7/F9/F16 — exigé par la Boundary « historique envoyé au moteur ».
  - `[maybe-false]` `[reject]` (intent) `usage_metadata` réel non prouvé avec Ollama — repli par estimation testé ; à vérifier au matin.
  - `[maybe-false]` `[reject]` (intent) CrossEncoder réel jamais chargé — pas de téléchargement autorisé.
  - `[medium]` `[patch]` (blind, edge) flux sans réponse : échec perdu au rerun — tour d'erreur conservé.
  - `[medium]` `[patch]` (blind) journaux d'outils « running » pour toujours après un échec — clos et marqués interrompus.
  - `[medium]` `[patch]` (blind) construction de `AgentEngine` hors du `try` — déplacée.
  - `[medium]` `[patch]` (blind) événement `error` sans conseil — même message que le chemin `except`, détail replié.
  - `[medium]` `[patch]` (blind, edge) formule CO₂ par le catalogue local alors que le badge suit le fournisseur — `is_cloud` du tour.
  - `[low]` `[defer]` (blind) formule CO₂ recopiée une septième fois dans l'interface — factorisation dans `src/core` hors périmètre.
  - `[low]` `[patch]` (blind, edge) estimation de tokens : appels d'outils à 0, blocs comptés en `repr` — JSON des appels, blocs texte seuls.
  - `[medium]` `[patch]` (blind) tri qui change l'embedding par défaut (autre collection) — tri limité aux rerankers.
  - `[low]` `[patch]` (blind, edge) `set_embedding` renomme avant de charger — chargement d'abord.
  - `[low]` `[patch]` (blind) `set_models` et `UNCHANGED` morts — supprimés.
  - `[low]` `[patch]` (blind, edge) score brut présenté comme « pertinence » — « score de reclassement ».
  - `[medium]` `[patch]` (blind, verification-gap) reranker par défaut en échec au démarrage non testé — AppTest ajouté.
  - `[low]` `[patch]` (blind) constante CO₂ codée en dur dans un test — `CarbonCalculator`.
  - `[low]` `[patch]` (blind, edge) tours d'erreur sans modèle ; réponse vide sans légende — légende affichée.
  - `[low]` `[patch]` (edge) `model_tag` None ou tokens non finis — `None`.
  - `[medium]` `[patch]` (edge) exception du calcul CO₂ qui fait perdre la réponse — réponse ajoutée d'abord.
  - `[medium]` `[patch]` (edge) modèle enregistré écrasé par le repli — écrit seulement par `on_change`, restauré au retour.
  - `[low]` `[patch]` (edge) reranker actif dont le dossier a disparu retombe sur « Aucun » — gardé dans les options.
  - `[low]` `[patch]` (verification-gap) tri non observable (ordre du disque déjà alphabétique) — `iterdir` inversé.
  - `[maybe-false]` `[reject]` (intent) CO₂ sur tous les tokens du tour, étapes d'outils comprises — total réel, documenté.
  - `[maybe-false]` `[reject]` (intent) ordre HyDE et Self-RAG testé seulement en unitaire — suffisant, même mécanisme.
  - `[low]` `[reject]` (intent) HyDE k extraits et `rerank_score` hors intention — condition pour que le reranker « change l'ordre des sources ».
  - `[false]` `[reject]` (intent) test du modèle échoue sur la base pour une autre raison — vérifié : la valeur revenait au premier modèle.
  - `[maybe-false]` `[reject]` (blind) Self-RAG note contre la question reformulée — comportement de la stratégie, inchangé.
  - `[low]` `[reject]` (edge) suppression de la légende en direct — doublon, corrigé.
  - `[low]` `[reject]` (blind) nom de collection par système de fichiers insensible à la casse — doublon du tri.
  - `[maybe-false]` `[reject]` (verification-gap) chargement réel de CrossEncoder — doublon.
  - `[low]` `[reject]` (blind) chemins de défaut d'embedding — doublon.
  - `[low]` `[reject]` (edge) repli de l'embedding — doublon.
  - `[low]` `[reject]` (blind) défaut reranker alphabétique — voulu (indépendant du disque).

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed

## Auto Run Result

Status: done

**Résumé :** la réponse finale de l'agent seul est conservée avec son raisonnement, son CO₂ (tokens de sortie du tour, formule selon Local/Cloud), son modèle et son badge ; les échecs (événement d'erreur, exception, flux sans réponse) restent visibles et ferment les journaux d'outils ; le moteur ne reçoit que les vrais tours, la question courante une seule fois ; le modèle choisi survit au passage par l'équipe ; le reranker choisi (ou « Aucun ») est réellement appliqué, conservé au changement d'embedding, avec un message en cas d'échec de chargement ; HyDE renvoie k extraits ; le score affiché est le score de reclassement réel.

**Fichiers :** `src/core/agent_engine.py`, `src/core/rag_engine.py`, `src/core/rag/strategies/{hyde,self_rag}.py` ; `src/app/tabs/agent/solo.py`, `src/app/views/{03_RAG_Knowledge,04_Agent_Lab}.py`, `src/app/tabs/rag/chat.py` ; tests `tests/unit/test_agent_history.py`, `tests/unit/test_rag_reranker.py`, `tests/app/test_nothing_lost.py`.

**Revue :** 20 correctifs (8 medium, 12 low), 2 différés, 12 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les medium sont couverts par des tests ajoutés.

**Vérification :** `pytest tests/unit tests/app` : 684 réussis.

**Risques :** `usage_metadata` réel d'Ollama via LangGraph non vérifié (repli par estimation) ; CrossEncoder réel jamais chargé ; rapport de l'équipe non conservé.
