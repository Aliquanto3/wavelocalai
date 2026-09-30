---
title: 'Souveraineté visible et actions sensibles'
type: 'feature'
created: '2026-09-27'
status: 'done'
baseline_revision: 'f7b0df9ef3a2acff0c326fde587859aabc547063'
review_loop_iteration: 0
followup_review_recommended: false
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
warnings: []
deferred:
  - summary: >-
      Badge de la réponse de l'agent seul perdu au rerun (réponse non conservée).
    evidence: |-
      La réponse finale n'est pas ajoutée à agent_messages (story 9).
    location: >-
      src/app/tabs/agent/solo.py
    severity: medium
  - summary: >-
      Points du graphique de l'Arène sans badge Local/Cloud.
    evidence: |-
      Graphiques confiés à la story 10.
    location: >-
      src/app/tabs/inference/arena.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** Le mode cloud est actif au démarrage (U12), l'utilisateur ne voit pas si un modèle ou une réponse sort de la machine (aucun badge ; les tags Ollama distants restent proposés quand le cloud est désactivé), l'agent peut envoyer un email sans confirmation (U14) et « Vider la base documentaire » supprime tout au premier clic (U15). Les deltas détournés (U13) ont déjà disparu ; seul un garde-fou manque.

**Approach:** Appliquer D1 et D2 : local à chaque démarrage, aucun modèle cloud proposé quand le cloud est désactivé, badge Local (vert) ou Cloud (orange) sur chaque modèle et chaque réponse ; « Envoi d'email » décoché par défaut, l'agent prépare un brouillon et rien ne part sans validation humaine ; confirmation chiffrée avant de vider la base documentaire.

## Boundaries & Constraints

**Always:** DESIGN.md (`badge-local` : `st.badge("Local", icon=":material/computer:", color="green")`, `badge-cloud` : `color="orange"`, `:material/cloud:` ; jamais de rouge) et EXPERIENCE.md (Souveraineté visible, `confirm-dialog`, Interaction Primitives) ; badge dérivé du fournisseur réel du modèle ; confirmation qui nomme la conséquence chiffrée, « Annuler » sans effet, succès au même verbe ; tests sans réseau ni envoi réel (SMTP simulé).

**Never:** conserver la réponse finale de l'agent ou le modèle choisi entre les reruns (story 9) ; changer les graphiques (story 10) ; emoji, hex ou CSS ; envoyer un email sans action explicite de l'utilisateur, y compris depuis l'équipe d'agents ; toucher `src/core/config.py` ou le benchmark.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Démarrage | nouvelle session, clés d'API présentes | « Autoriser le cloud » désactivé ; Mode « Local » (badge vert) | — |
| Cloud désactivé | Ollama liste `glm-4.6:cloud` et un local | Seul le local est proposé, dans tous les sélecteurs | — |
| Cloud activé | modèle cloud choisi | Badge « Cloud » orange sur le modèle choisi et sur chaque réponse | — |
| Badges des réponses | Chat libre, Banc d'essai, Arène (tableau, vainqueur, réponses), Discussion, évaluation (podium), agent seul | Badge Local ou Cloud selon le fournisseur réel | — |
| Email par défaut | premier affichage de l'agent seul | « Envoi d'email » non sélectionné, les 8 autres oui | — |
| Email demandé | outil email activé, l'agent appelle l'outil | Aucun envoi ; `confirm-dialog` avec destinataire, objet et corps ; « Envoyer l'email » envoie, « Annuler » n'envoie rien | erreur SMTP → `alert-error`, rien d'autre |
| SMTP absent | variables SMTP vides | Pastille « Envoi d'email » visible, non sélectionnable, aide « Configuration SMTP absente » | — |
| Équipe d'agents | un agent a l'outil email | Brouillon seulement, jamais d'envoi | — |
| Vider la base | 42 extraits de 3 documents | Premier clic : avertissement « 42 extraits de 3 documents seront supprimés » ; « Annuler » ne supprime rien ; la confirmation vide la base et affiche un succès au même verbe | base vide → bouton désactivé |
| Deltas | toute page | Aucun `delta` de `st.metric` non numérique | — |

</intent-contract>

## Code Map

- `src/app/Accueil.py:29-33,62-68` -- toggle unique `key="cloud_enabled"`, défaut `True` (l.64-65, commentaire « story 8 »), aide. Lecteurs avec repli `True` : `home.py:45`, `views/01_Socle_Hardware.py:102`, `views/02_Inference_Arena.py:17`, `views/03_RAG_Knowledge.py:260`, `views/04_Agent_Lab.py:97` : centraliser la lecture (une fonction, repli `False`).
- `src/core/llm_provider.py:39-50`, `src/core/providers/provider_factory.py:128-130` -- `list_all_models(include_cloud)` n'écarte que les fournisseurs non locaux ; les tags Ollama distants (`is_remote_tag` de `src/core/model_defaults.py:231-243`) passent : les écarter quand `include_cloud=False`.
- `src/app/ui.py:41-123` -- `model_label` (« Nom · Local/Cloud »), `model_menu` → `menu.choices[label].is_cloud` : source du badge. Ajouter un rendu de badge partagé (`st.badge` ou directive Markdown `:green-badge[:material/computer: Local]` / `:orange-badge[:material/cloud: Cloud]`, disponibles dans Streamlit 1.64 : `st.badge(label, *, icon, color, width, help)`).
- Réponses sans badge : `tabs/inference/chat.py:67-79,201,228` (pied ; `model_friendly` stocké, non rendu), `lab.py:59,187-188`, `arena.py:166-201,233-235,601-622` (lignes sans tag ni type : conserver le type dans la ligne), `rag/chat.py:73-106,238-247` (message sans modèle : stocker tag et type), `rag/eval.py:244,310-316,443`, `agent/solo.py:322-333` (réponse finale), `agent/crew.py:269-274,473-489`.
- Mode : `home.py:70-71`, `views/01_Socle_Hardware.py:130-131` (`st.metric("Mode", …)`) : ajouter le badge.
- `src/core/agent_tools.py:49-53,180-232,642-664,790-829` -- SMTP lu à l'import ; `_send_email_impl` envoie immédiatement ; `@tool send_email` l'appelle ; `TOOLS_METADATA["send_email"]` (`requires_config`, `config_vars`). Faire préparer un brouillon à l'outil (sans envoi), garder `_send_email_impl` comme envoi réel appelé par l'interface après confirmation ; exposer `smtp_configured()`.
- `src/core/agent_engine.py:59,124-200` -- `create_react_agent`, événements `tool_call` (`tool`, `args`), `tool_result`, `final_answer` : `solo.py` capte `tool_call` de `send_email` et garde le brouillon en session.
- `src/app/tabs/agent/solo.py:115-143` -- `selected_tools` = les 9 outils par défaut ; pastilles.
- `src/app/tabs/agent/crew.py:42-106,326-355` -- outils par agent ; `crew_engine.py:31-37` adapte les outils LangChain : le brouillon neutralise l'envoi.
- `src/app/views/03_RAG_Knowledge.py:95-151` -- dialogue `open_knowledge_manager` : « Vider la base documentaire » (l.148-150) sans confirmation. Pas de dialogue imbriqué possible : confirmation en deux temps dans le dialogue (drapeau de session, `st.warning` chiffré avec `_base_summary`, « Confirmer la suppression » / « Annuler »), drapeau remis à zéro à l'ouverture.
- Tests qui figent le défaut `True` : `tests/app/test_navigation.py:187,210-223,226-265` (à corriger sur la cible D1). Libellés « · Local/· Cloud » : `tests/app/test_defaults.py`, `tests/unit/test_ui.py`, `tests/app/test_theme.py` (inchangés). Email : `tests/unit/test_agent_tools.py:47-69,278-300`, `tests/integration/test_agent_engine.py:182`.

## Tasks & Acceptance

**Execution:**
- `src/app/Accueil.py` et les pages -- défaut local, lecture centralisée ; badge sur la métrique Mode.
- `src/core/providers/provider_factory.py` (ou `llm_provider.py`) -- tags distants écartés sans cloud.
- `src/app/ui.py` -- badge partagé ; `src/app/tabs/**` -- badges sur les réponses et le modèle choisi.
- `src/core/agent_tools.py`, `src/app/tabs/agent/solo.py` -- brouillon, confirmation, défaut décoché, pastille non sélectionnable sans SMTP.
- `src/app/views/03_RAG_Knowledge.py` -- confirmation du vidage.
- `tests/` -- chaque ligne de la matrice (AppTest et unitaires, SMTP et Ollama simulés) ; garde-fou : aucun `delta=` non numérique dans `src/app`.

**Acceptance Criteria:**
- Given `pytest tests/unit tests/app`, when la suite se termine, then 0 échec et aucun envoi SMTP réel.
- Given l'app lancée avec les providers simulés, when on ouvre l'accueil au navigateur, then « Autoriser le cloud » est désactivé et le badge « Local » est visible, sans requête hors localhost.

## Spec Change Log

## Review Triage Log

### 2026-09-27 — Review pass
- verdicts: 44 findings — high 0, medium 12, low 21, false 3, maybe-false 8
- findings:
  - `[medium]` `[patch]` (blind, intent, edge, verification-gap) équipe : l'outil annonce une validation dans une interface inexistante, corps absent du rapport — outil propre à l'équipe qui rend le brouillon complet et dit qu'aucun email ne part.
  - `[medium]` `[patch]` (blind) brouillons non vidés par « Effacer la conversation » ni au passage en équipe — vidés.
  - `[medium]` `[patch]` (blind, edge) aperçu en texte brut, envoi en HTML — envoi en texte brut, identique à l'aperçu.
  - `[low]` `[patch]` (blind) succès déduit d'un préfixe de chaîne via une fonction privée — `send_validated_email()` publique, résultat structuré.
  - `[low]` `[patch]` (blind) aide SMTP incomplète (redémarrage, port, serveur par défaut) — aide complétée.
  - `[medium]` `[patch]` (blind) `gpt-oss:20b` local badgé Cloud — un tag Ollama `nom:variante` est local sauf distant.
  - `[medium]` `[defer]` (blind, intent) badge de la réponse de l'agent seul non conservé au rerun — conservation de la réponse : story 9.
  - `[low]` `[patch]` (blind) contenu supprimé encore affiché après le vidage — réponses de la Discussion vidées.
  - `[medium]` `[patch]` (blind, verification-gap) code de production façonné pour un double de test — logique extraite dans `src/app/rag_clear.py`, testée avec `pending=True`.
  - `[low]` `[patch]` (blind) aide du badge sous « Mode » qui parle d'un modèle — aide propre au mode.
  - `[low]` `[patch]` (blind, edge) badge « Modèle principal » calculé avant les sélecteurs ; bascule silencieuse d'un agent cloud — badge rendu après, légende de bascule.
  - `[low]` `[reject]` (blind) `FakeSMTP` dupliqué, badges codés en dur dans les tests — sans effet sur le comportement.
  - `[low]` `[patch]` (blind) adaptateur de l'équipe testé avec un seul outil, appels mixtes cassés — fusion des arguments, test avec la calculatrice.
  - `[medium]` `[patch]` (edge) confirmation d'email ouverte alors que l'outil est désactivé ou SMTP absent — mise en file conditionnelle.
  - `[low]` `[patch]` (edge) deux appels identiques, deux confirmations — dédoublonnage.
  - `[low]` `[patch]` (edge) SMTP sans délai — `timeout=15`, spinner.
  - `[low]` `[patch]` (edge) `clear_database()` qui lève : trace brute — `render_error`, drapeau remis à zéro.
  - `[medium]` `[patch]` (edge) tag inconnu badgé « Local » (échec ouvert) — badge gris « Origine inconnue ».
  - `[medium]` `[patch]` (verification-gap) badge Cloud du rapport de l'équipe non testé — `crew_is_cloud` testé.
  - `[low]` `[patch]` (verification-gap) fermeture du dialogue d'email non testée — `_dismiss_email` testé.
  - `[low]` `[patch]` (verification-gap) arguments invalides de l'outil email non testés côté file — `email_draft` paramétré.
  - `[low]` `[patch]` (verification-gap) garde « un dialogue à la fois » non testée — AppTest bibliothèque + brouillon.
  - `[maybe-false]` `[reject]` (intent) badges vérifiés en chaînes, pas au rendu — critère navigateur vérifié : interrupteur désactivé, badge Local visible, aucune requête externe ; couleurs natives de `st.badge` à mesurer au matin (axe).
  - `[low]` `[defer]` (intent) points du graphique de l'Arène sans badge — story 10.
  - `[low]` `[reject]` (intent) tableaux avec « Exécution » en texte — les tableaux n'acceptent pas de badge.
  - `[low]` `[reject]` (intent) « Mode » affiché en métrique plus badge — lisible, sans ambiguïté.
  - `[low]` `[reject]` (intent) barre « Santé du système » de l'Agent Lab sans badge — la section « Santé du système » d'EXPERIENCE.md est sur Sobriété et matériel.
  - `[maybe-false]` `[reject]` (intent) D2 « un humain valide » pour l'équipe — l'équipe ne peut pas envoyer du tout, plus prudent.
  - `[low]` `[patch]` (intent) « Confirmer la suppression » contre le verbe « Vider » — « Vider définitivement ».
  - `[maybe-false]` `[reject]` (intent) forme du `confirm-dialog` dans le dialogue existant — dialogues imbriqués impossibles.
  - `[false]` `[reject]` (intent) défaut local testé sans lecture de l'environnement — le défaut est une constante indépendante des clés, c'est l'exigence.
  - `[maybe-false]` `[reject]` (intent) sélecteurs trouvés par libellé — suffisant.
  - `[maybe-false]` `[reject]` (intent) dialogue d'email rouvert à chaque rerun tant qu'un brouillon attend — voulu ; fermeture testée.
  - `[low]` `[reject]` (verification-gap) séquence réelle du dialogue non rejouée par AppTest — logique extraite et testée ; parcours navigateur au matin.
  - `[false]` `[reject]` (verification-gap) « Other findings » équipe — doublon.
  - `[maybe-false]` `[reject]` (edge) badge principal lu depuis l'état — doublon.
  - `[low]` `[reject]` (blind) `is_cloud_tag` recopie un défaut de `get_provider` — `get_provider` hors périmètre, noté.
  - `[low]` `[reject]` (blind) adaptateur affecte tous les outils — testé avec deux outils.
  - `[false]` `[reject]` (blind) SMTP_SERVER jamais signalé manquant — défaut documenté.
  - `[maybe-false]` `[reject]` (intent) U13 sans changement de code — garde-fou statique ajouté.
  - `[low]` `[reject]` (intent) correctif `crew_engine.py` hors liste — nécessaire pour que l'équipe reçoive le brouillon ; noté au rapport.
  - `[low]` `[reject]` (edge) HTML caché dans le corps — doublon, envoi en texte brut.
  - `[low]` `[reject]` (verification-gap) doublon du garde « dialogue ».
  - `[low]` `[reject]` (blind) `cloud_enabled()` appelé deux fois — doublon, corrigé.

## Verification

**Commands:**
- `.venv-app/bin/python -m pytest tests/unit tests/app -q -p no:cacheprovider` -- expected: 0 failed
- `grep -rn "delta=" src/app --include=*.py` -- expected: seulement des variations chiffrées

## Auto Run Result

Status: done

**Résumé :** D1 et D2 appliqués : local à chaque démarrage (lecture centralisée `cloud_enabled()`, repli local), tags Ollama distants écartés sans cloud, badge Local (vert) / Cloud (orange) / Origine inconnue (gris) sur chaque modèle et chaque réponse ; « Envoi d'email » décoché, l'agent seul prépare un brouillon envoyé seulement après « Envoyer l'email » (texte brut, identique à l'aperçu) ; l'équipe ne peut pas envoyer ; pastille non sélectionnable sans SMTP ; confirmation chiffrée avant de vider la base documentaire.

**Fichiers :** `src/app/{Accueil,home,ui,rag_clear}.py`, `src/app/views/*.py`, `src/app/tabs/**` ; `src/core/agent_tools.py`, `src/core/crew_engine.py`, `src/core/providers/provider_factory.py` ; tests `tests/app/test_sovereignty.py` et mises à jour (`test_navigation`, `test_figures`, `test_theme`, `test_ui`, `test_llm_provider`, `test_agent_tools`).

**Revue :** 23 correctifs (10 medium, 13 low), 2 différés, 19 rejetés.

**Suivi recommandé :** false — aucun correctif high ; les medium sont couverts par des tests ajoutés.

**Vérification :** `pytest tests/unit tests/app` : 638 réussis, aucun envoi SMTP réel ; navigateur (providers simulés) : interrupteur « Autoriser le cloud » désactivé au démarrage, badge Local visible, 0 exception, aucune requête hors localhost.

**Risques :** contraste des couleurs natives de `st.badge` (vert, orange, gris) à mesurer au matin ; correctif de l'adaptateur d'outils de l'équipe (`crew_engine.py`) : les outils de l'équipe s'exécutent désormais ; envoi SMTP réel non essayé.
