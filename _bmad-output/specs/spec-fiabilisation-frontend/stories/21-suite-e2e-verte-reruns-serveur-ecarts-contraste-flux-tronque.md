---
title: 'Suite e2e au vert sur le poste : reruns attendus côté serveur, écarts de contraste acceptés, flux tronqué'
type: 'chore'
created: '2026-09-29'
status: 'done'
baseline_commit: '79aadc349b83693388388a5660db85093a69659a'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '{project-root}/tests/e2e/README.md'
warnings: []
deferred:
  - summary: >-
      Discussion et évaluation de l'Assistant documentaire (test_documents.py) génèrent sans h.generate : un flux Ollama tronqué y fait échouer le test au lieu de le relancer.
    evidence: |-
      rag/chat.py et rag/eval.py passent par OllamaProvider, qui lève InterruptedResponseError sur un flux sans done ; test_documents.py n'a aucune relance. Antérieur à la story 21 (l'entrée différée de la story 19 ne citait que le Chat libre et l'Arène).
    location: >-
      tests/e2e/test_documents.py
    severity: medium
  - summary: >-
      nav, click_tab et les appels de settle_after_action(until=...) attendent encore un état du navigateur, pas le compteur d'exécutions du serveur.
    evidence: |-
      Seuls select_option, multiselect_add, multiselect_clear et generate emploient wait_script_run ; test_agents.py, test_documents.py et test_sobriety.py gardent des attentes côté navigateur (docstring de helpers.py qualifiée en conséquence).
    location: >-
      tests/e2e/helpers.py
    severity: low
---

<intent-contract>

## Intent

**Problem:** Trois fragilités de la suite e2e, différées par les stories 13, 14 et 19 :
- `select_option`, `multiselect_add` et `multiselect_clear` (`tests/e2e/helpers.py`) attendent un état du navigateur (valeur affichée, étiquettes), vrai avant la fin du rerun du serveur. Un test lit alors une page périmée (échec observé sur une option détachée du DOM).
- `test_axe_no_theme_violation[Agent_Lab-dark]` échoue à chaque passage sur l'écart accepté le 27/09 (pastilles `#7E65E9` sur `#161329`, 4,24:1). Une régression nouvelle sur cette page s'y confondrait.
- Le premier message du Chat libre et l'Arène avec juge échouent quand Ollama 0.34.2 ferme le flux sans fragment `done` (~1 réponse française sur 5). Seul le Banc d'essai relance.

**Approach:**
- Compter les exécutions du script côté serveur : messages `new_session` et `script_finished` du WebSocket de la page, lus par Playwright. Les trois helpers attendent la fin d'une exécution commencée après leur action.
- `test_accessibility.py` reçoit une liste explicite d'écarts acceptés : page, thème, composant, couleurs exactes, ratio, renvoi à DESIGN.md. Seul un écart identique passe ; il reste listé en fin de session.
- Une relance commune (`generate`) sert au Chat libre, au Banc d'essai et aux deux Arènes avec juge. Jusqu'à 3 passages ; ensuite, `pytest.skip` avec le motif du bug d'Ollama 0.34.2.

## Boundaries & Constraints

**Always:**
- Tests seulement : aucun fichier de `src/`.
- Assertions inchangées ou renforcées : l'Arène avec juge n'accepte plus de modèle en échec.
- Un passage à froid relancé redécharge d'abord le modèle (`ensure_cold`).
- Les écarts acceptés figurent au résumé de session et au rapport JSON.
- Les tests unitaires restent sans réseau ni navigateur.

**Never:**
- `skip` ou `xfail` hors de l'épuisement des relances.
- Tolérance de ratio, liste d'écarts par motif ou par page entière.
- Changer `primaryColor` ou DESIGN.md.
- Lancer la suite e2e dans cette story : l'orchestrateur la lance deux fois à la fin de la série.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Choix d'une nouvelle valeur | `select_option`, `multiselect_add` | Retour après un `script_finished` (hors `FINISHED_EARLY_FOR_RERUN`) d'une exécution commencée après le clic | Aucune exécution dans le délai : `AssertionError` qui le dit |
| Valeur déjà choisie | `select_option` sur la valeur affichée | Pas d'attente de rerun (le serveur n'en lance pas) | N/A |
| Liste déjà vide | `multiselect_clear` | Retour immédiat | N/A |
| Écart accepté | pastilles, Agent_Lab sombre, `#7e65e9` sur `#161329`, 4,24 | Classé « écart accepté », test vert | N/A |
| Écart voisin | même page, autre ratio, autre couleur ou autre composant | Échec du test | Message avec couleurs et ratio |
| Génération interrompue | « Réponse interrompue » après le passage | Relance, jusqu'à 3 passages | 3 interruptions : `pytest.skip`, motif du bug d'Ollama 0.34.2 |

</intent-contract>

## Code Map

- `tests/e2e/helpers.py` -- `select_option` (~l.222), `multiselect_clear` (~l.247), `multiselect_add` (~l.265) : `until` côté navigateur à remplacer. `wait_rerun_started` (l.73) n'a qu'un appelant, `_lab_run` : le compteur le remplace. `settle` et `wait_until` sont réutilisables.
- Protocole (Streamlit 1.64) :
  - `runtime/app_session.py:803-873` : `new_session` part au début de chaque exécution, fragments compris, et `script_finished` à la fin. `FINISHED_EARLY_FOR_RERUN` signale une exécution coupée par une autre.
  - `web/server/starlette/starlette_websocket.py:383` : un `ForwardMsg` binaire par trame.
  - `ForwardMsg.WhichOneof("type")`. Les objets `Page` de Playwright acceptent les références faibles.
- `tests/e2e/conftest.py:460` fixture `page` : y installer le compteur avant toute navigation.
- `tests/e2e/test_arena.py` :
  - `_interrupted`, `LAB_ATTEMPTS`, `OLLAMA_TRUNCATED_STREAM_BUG` et `_lab_run` (l.114-157) : à migrer vers `h.generate`.
  - `test_chat_cold_start_load_and_badge` (l.89) : lit `nth(1)` et `nth(0)`. Après une relance, l'historique garde le tour en erreur (`chat.py:212-224`) : lire le dernier message.
  - `test_arena_two_local_models_with_judge` : les attentes sur la légende et sur l'avertissement du juge deviennent de simples assertions après les helpers.
- `tests/e2e/test_arena_timeout.py:80-116` : autre Arène avec juge. Le petit modèle y dépasse volontairement le délai.
- `src/app/tabs/inference/arena.py:611,483` : une interruption s'écrit « Réponse interrompue » dans le suivi (`st.status` replié, mais présent dans le DOM : `inert`) ou « (réponse interrompue) » dans la raison du juge. Lire `text_content()`, pas `inner_text()`.
- `tests/e2e/test_accessibility.py` : boucle de classement (l.130-145). Dernier rapport, `axe-dark-Agent_Lab.json` du 29/09 : 8 nœuds `<p>` sous `[data-variant="pills"]`, `#7e65e9` sur `#161329`, 4,24:1.
- `tests/e2e/conftest.py:117` `pytest_terminal_summary` : titre à compléter pour les écarts acceptés.
- `tests/unit/test_e2e_suite.py` : garde-fous sans navigateur, où tester le compteur, le classement et la relance.

## Tasks & Acceptance

**Execution:**
- [x] `tests/e2e/helpers.py` -- compteur `track_script_runs`, `script_runs`, `wait_script_run` ; les trois helpers l'emploient ; `generate(page, launch, interrupted, timeout_ms, before_retry=None, what=…)`, `GENERATION_ATTEMPTS = 3` et motif commun ; retrait de `wait_rerun_started` -- cause commune des reruns et relance partagée
- [x] `tests/e2e/conftest.py` -- compteur installé dans la fixture `page` ; titre du résumé -- compteur toujours présent
- [x] `tests/e2e/test_arena.py`, `tests/e2e/test_arena_timeout.py` -- Chat libre (relance à froid), Banc d'essai et Arènes avec juge par `h.generate` ; aucune Arène avec juge n'accepte de « modèle en échec » imprévu -- flux tronqué
- [x] `tests/e2e/test_accessibility.py` -- `ACCEPTED_CONTRAST_GAPS` et `accepted_gap(finding)`, catégorie à part dans le rapport ; docstring -- écart connu accepté, nouvel écart en échec
- [x] `tests/unit/test_e2e_suite.py` -- compteur (trames simulées), `accepted_gap` (écart exact, puis voisins), `generate` (succès au 2e passage, skip au 3e) -- vérifiable sans navigateur
- [x] `tests/e2e/README.md` -- compteur, relances, écart accepté -- documentation
- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- retirer les entrées traitées (helpers de la story 13, liste de la story 14, e2e générateurs de la story 19) ; garder à part le texte blanc des boutons, non traité -- traçabilité

**Acceptance Criteria:**
- Given la suite e2e sur poste-rtx3060, when elle tourne deux fois de suite, then aucun test n'échoue ; seuls sont permis les skips dus à 3 interruptions d'Ollama.
- Given `test_axe_no_theme_violation[Agent_Lab-dark]`, when axe relève les 8 pastilles à 4,24:1, then le test réussit et le résumé de session les liste comme écarts acceptés.

## Spec Change Log

## Review Triage Log

### 2026-09-29 — Review pass
- verdicts: 20 findings — high 0, medium 4, low 13, false 1, maybe-false 2
- findings:
  - `[maybe-false]` `[reject]` (intent) `since` lu sur des événements déjà relayés par Playwright — même question que la ligne blind sur l'ordre des trames ; à trancher en observant, dans une vraie session, un rerun commencé avant l'action.
  - `[low]` `[reject]` (intent) écart accepté par nœud, sans nombre de nœuds figé — une pastille de plus aux mêmes couleurs est le même compromis documenté (DESIGN.md : tout composant du même type) ; figer 8 nœuds lierait le test au nombre d'outils de l'agent.
  - `[low]` `[defer]` (intent) seuls trois helpers suivent le compteur, les autres attentes restent côté navigateur — intention limitée aux trois helpers ; différé (frontmatter `deferred`).
  - `[medium]` `[defer]` (blind) Discussion et évaluation documentaires sans relance du flux tronqué — antérieur, hors de l'intention (Chat libre et Arène seulement) ; différé.
  - `[medium]` `[patch]` (blind) `_lab_run` ne vérifie plus que les métriques ont changé — le Banc d'essai garde son dernier résultat (lab.py:201-212) : relevé avant `h.generate`, assertion de changement ajoutée.
  - `[low]` `[reject]` (blind) écart accepté non figé à 8 nœuds — même raison que la ligne d'intention.
  - `[low]` `[reject]` (blind) taux de skip des Arènes non rapporté — chaque skip figure au résumé de pytest avec son motif ; compter les relances ajouterait une surface de rapport pour un simple diagnostic.
  - `[low]` `[reject]` (blind) taux d'interruption contradictoires (1 sur 5, 1 sur 8) — deux mesures de l'utilisateur (29/09), sans effet sur le code ; la décision de la story 24 cite 1 sur 5.
  - `[maybe-false]` `[reject]` (blind) trames d'un rerun antérieur encore en file quand `since` est lu — le helper précédent finit par `settle` (idle du navigateur puis 300 ms qui pompent les événements), et clic et saisie pompent encore avant la lecture ; le seul cas concret, le repli tag par tag, est corrigé (ligne edge). Si réel ailleurs, il ne serait que low.
  - `[low]` `[defer]` (blind) `settle_after_action`, `nav`, `click_tab` encore sur l'état du navigateur — différé avec la ligne d'intention ; docstring du module qualifiée (patch).
  - `[low]` `[patch]` (blind) attente redondante après `select_option` dans le test de débit — remplacée par une assertion.
  - `[low]` `[patch]` (blind) détection d'interruption de l'Arène dupliquée — `h.arena_interrupted` partagé ; ancrage sur un texte plus précis rejeté (aides non rendues sans survol, phrase improbable dans une réponse).
  - `[low]` `[patch]` (blind) dérive du protocole Streamlit non signalée — `goto` vérifie une exécution comptée après le premier rendu, avec un message qui nomme l'hypothèse.
  - `[low]` `[patch]` (blind) tests unitaires manquants (repli de `multiselect_clear`, ordre de classement) — tests ajoutés ; échec de `select_option` sans valeur affichée rejeté (chemin d'échec de `wait_until`, déjà couvert).
  - `[low]` `[patch]` (blind) `AXE_NATIVE_FINDINGS` mal nommé, composant absent du résumé — renommé `AXE_NON_FAILING_FINDINGS`, composant imprimé.
  - `[false]` `[reject]` (blind) vérification de la spec non tracée — journal de revue et résultat sont écrits à la finalisation ; statut `in-review` attendu pendant la revue.
  - `[medium]` `[patch]` (verification-gap) classement des constats axe, rapport et résumé non testés — `classify`, `sort_findings` et `non_failing` extraits et testés sans navigateur.
  - `[low]` `[patch]` (edge) `new_session` d'un clic précédent pas encore relayé quand le repli tag par tag relit `since` — attente du rerun de chaque clic à la place des 200 ms.
  - `[low]` `[patch]` (edge) repli de `multiselect_clear` sans clic mais avec attente finale — plus d'attente sans clic ; test unitaire.
  - `[medium]` `[patch]` (edge) métriques périmées lues au passage à chaud — même correctif que la ligne blind de `_lab_run`.

## Design Notes

Compteur. Une exécution est comptée à son début (`new_session`). Elle est terminée quand un `script_finished` hors `FINISHED_EARLY_FOR_RERUN` arrive ; `finished` prend alors le numéro de la dernière exécution commencée. `wait_script_run(page, since)` attend `finished > since`, puis `settle`. Une exécution commencée avant l'action ne compte donc pas. Un `st.rerun()` (Chat libre) finit en `FINISHED_EARLY_FOR_RERUN` : l'attente porte sur l'exécution suivante.

```python
since = h.script_runs(page)
label = _pick(page, text, tag)
if label != current:
    h.wait_script_run(page, since)
```

## Verification

**Commands:**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` -- expected: tout réussit, hors les 4 échecs connus d'AGENTS.md s'ils se produisent
- `.venv-app\Scripts\python -m pytest tests/e2e -m e2e --collect-only -q` -- expected: collecte sans erreur
- `uvx ruff check tests/e2e tests/unit/test_e2e_suite.py` et `uvx black --check` sur les fichiers touchés -- expected: propres

**Manual checks (if no CLI):**
- Suite e2e complète deux fois de suite, en fin de série, par l'orchestrateur.

## Auto Run Result

Status: done

**Résumé.**
- Les helpers `select_option`, `multiselect_add` et `multiselect_clear` attendent la fin d'une exécution du script commencée après leur action. Le compteur lit les messages `new_session` et `script_finished` du WebSocket de la page ; `goto` vérifie qu'il compte.
- Le test axe accepte le seul écart listé : pastilles d'Agent_Lab en sombre, `#7e65e9` sur `#161329`, 4,24:1. Il le classe à part dans le rapport et dans le résumé.
- Le premier message du Chat libre, le Banc d'essai et les deux Arènes avec juge passent par `h.generate` : 3 passages au plus, puis un skip avec le motif du bug d'Ollama 0.34.2.

**Fichiers.**
- `tests/e2e/helpers.py` : compteur d'exécutions, helpers de sélection, `generate`, `arena_interrupted`, contrôle dans `goto`, `AXE_NON_FAILING_FINDINGS`.
- `tests/e2e/conftest.py` : compteur installé par la fixture `page`, résumé de session.
- `tests/e2e/test_accessibility.py` : `ACCEPTED_CONTRAST_GAPS`, `accepted_gap`, `classify`, `sort_findings`, `non_failing`.
- `tests/e2e/test_arena.py`, `tests/e2e/test_arena_timeout.py` : relances par `h.generate`, aucun modèle en échec imprévu, métriques nouvelles au Banc d'essai.
- `tests/unit/test_e2e_suite.py` : compteur, helpers, relance et classement testés sans navigateur.
- `tests/e2e/README.md` : section « Attentes et relances », écart accepté.
- `_bmad-output/implementation-artifacts/deferred-work.md` : entrées traitées retirées (story 13 ; liste de la story 14 ; e2e générateurs de la story 19). Ajouts : le texte blanc des boutons (reste de la story 14) et les deux points différés.

**Revue.** 20 constats :
- 10 corrigés, dont 3 medium ;
- 3 différés (2 entrées) ;
- 7 rejetés, dont 1 false, pour les raisons notées au journal.

Revue de suivi recommandée (`true`) : 3 constats medium et 7 low corrigés. Risque non vérifié : aucun changement e2e n'a encore tourné dans un vrai navigateur. Le compteur, la détection des interruptions et le classement « pills » sont éprouvés par la double exécution e2e de fin de série.

**Vérification.**
- `.venv-app\Scripts\python -m pytest tests/unit tests/app -q` : 944 réussis.
- `pytest tests/e2e -m e2e --collect-only` : 35 collectés.
- ruff et black propres.
- Suite e2e non lancée ici : elle tourne deux fois en fin de série.

**Risques résiduels.**
- Le protocole WebSocket de Streamlit 1.64 est supposé. S'il change, `goto` échoue tout de suite avec un message clair.
- Avec Ollama 0.34.2, le taux de skip des Arènes n'est pas nul.
