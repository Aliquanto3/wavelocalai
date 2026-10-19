---
title: 'Le Banc d''essai dit si la sortie respecte le format'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '3caae87'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-7-3.md'
warnings: []
deferred: []
---

# Story 7.4 : le Banc d'essai

## Objectif

Sur `#/arene/banc`, une consultante choisit un scénario prédéfini et un modèle, lance le test, voit la réponse arriver en flux puis le **verdict de format** (« Format respecté » ou la première violation en clair), la sortie mise en forme et les mesures (débit D3, CO₂, durée). Avec ou sans « Format imposé », avec ou sans « Réponse concise ». L'essai est conservé (`#/arene/banc/<run_id>`) et listé parmi les tests passés. Le serveur calcule tout (AD-20). La préversion `2.0.0a7` n'est pas posée ici (l'orchestrateur la pose après les stories 5 et 6).

## Critères d'acceptation et preuves

1. **Registre** : `GET /api/models` porte `structured_output` (vrai pour un modèle de conversation, faux pour un embedder), consigné dans `contrat-api.md` ; un modèle qui ne le peut pas désactive « Format imposé » avec sa raison. Preuve : `web/test_bench_api.py::test_models_carry_structured_output`, `e2e/test_bench.py::test_a_model_that_cannot_force_a_format_...`.
2. **Scénarios** : `GET /api/scenarios` rend les six scénarios de la v1 avec leur consigne système (`instruction`, D-18) et leur format attendu en schéma JSON, `null` sans format (D-17). Preuve : `::test_scenarios_carry_instruction_and_schema_or_null`.
3. **Run** : `POST /api/bench/runs {scenario, model, input, force_format, concise, allow_cloud}` ; l'instantané porte `format_verdict` (absent sans format), `bench` (entrée, sortie, options), les mesures D3, CO₂ et durée ; `force_format` passe le schéma par `response_schema` (`format` d'Ollama) ; `concise` ajoute la consigne. Preuves : `web/test_bench_api.py` (format respecté, violation en clair, sortie illisible, sans format, format imposé et concise, refus, violation levée par l'adaptateur, délai, liste et réouverture, `run_busy`), `unit/test_bench_verdict.py`.
4. **Écran** : réponse en flux, verdict à `run_ended` (lu de l'instantané), sortie mise en forme, interrupteurs « Format imposé » et « Réponse concise » avec leur aide (D-6), « Consigne » repliée (D-18), pas de « Format attendu » ni de verdict pour un scénario sans format, « Format imposé » désactivé avec la raison visible (D-17). Preuve : `e2e/test_bench.py` (formulaire, respecté, violé, illisible, sans format, interrupteurs).
5. **Rouvrir et lister** : `#/arene/banc/<run_id>` relit le résultat sans relancer de modèle ; inconnu : `run_not_found` ; liste des tests passés, les plus récents d'abord, chacun rouvrable. « Relancer le test » rejoue la configuration, « Modifier le test » la reprend dans le formulaire. Preuve : `::test_the_result_is_kept_reopens_...`, `::test_an_unknown_run_...`, `::test_rerun_and_edit_...`.
6. **Délai** : « Délai dépassé (120 s) », le délai réel (`detail.timeout_s`) cité. Preuve : `::test_a_timeout_cites_the_real_delay_...` (flux fixé par le test : le serveur réel a un délai de 300 s) ; côté serveur `web/test_bench_api.py::test_timeout_names_the_real_delay`.
7. **Accessibilité** : axe-core sans violation, clair et sombre, 1 440 et 390 px, formulaire, résultat et essai introuvable. Preuve : `::test_axe_...`.
8. **E2E de bout en bout** : les parcours jouent le vrai service avec le modèle `fake` (script par `POST /api/test/chat-model`), base de test en dossier temporaire, aucune requête hors de `127.0.0.1` (fixture `context`).

## Règles écrites

- Le serveur valide : le verdict, le JSON mis en forme et les mesures viennent de l'instantané ; le front ne fait ni `JSON.parse` ni `JSON.stringify`, ni calcul (test statique).
- `bench_input` porte le texte saisi dans le flux ; `runs.params` n'a que le scénario et les options (AD-7).
- Un banc à la fois (`run_busy`, AD-14) : un essai en cours est rejoint, depuis son adresse ou depuis le flux système.
- `onSmallerModel` rend la fonction de retrait de l'écouteur ; l'écran la rappelle au démontage.

## Écarts et variantes conservatrices

- **Format imposé violé** : un adaptateur qui lève `invalid_output` ferait finir le run en erreur ; le Banc le transforme en fin de flux ordinaire (`_Tee`, `inference/bench.py`) et le verdict dit la violation, sans débit (jetons inconnus). Variante conservatrice : on garde la sortie et le verdict plutôt qu'une panne.
- **Clôture Markdown** : un JSON entouré de ```` ``` ```` est jugé respecté (comme par les adaptateurs).
- **Extraction** : la consigne de la v1 ne nommait pas ses champs ; elle les nomme (`date`, `montant`, `vendeur`) pour que le format attendu soit précis.
- **Température** : fixe à 0,2 (curseur de la v1 à sa valeur par défaut, non repris : hors du critère).
- **« Format attendu »** : tableau des champs (nom, type, obligatoire) tiré du schéma, valeurs permises dites en texte ; pas d'affichage du schéma JSON brut.
- **Pas d'effacement ni d'export** d'un essai (non demandés) ; pas de graphique.
- **Modèle non chat** : `structured_output` n'est vrai que pour `kind == chat` ; aucune liste de modèles cloud exclus (variante conservatrice : le fournisseur dira l'erreur si son schéma est refusé).
- **Brouillon** : l'entrée n'est pas gardée dans `localStorage` (non demandé).

## Fichiers

- Serveur : `inference/scenarios.py`, `inference/bench.py` (service, verdict, `_Tee`), `runs/bench_snapshot.py`, `web/routes_bench.py` ; `models/registry.py` (`structured_output`), `models/structured.py` (`strip_fence`), `runs/snapshot.py`, `web/app.py`.
- Écran : `screens/bench.js`, `bench-form.js`, `bench-result.js`, `bench-history.js` ; `core/api/bench.js` ; `i18n/fr/bench.json` ; `bench.css` ; route `core/routes/arena.js` ; `wl-chat-thread.js` exporte `metric` et `co2Metric`.
- Tests : `web/test_bench_api.py`, `unit/test_bench_verdict.py`, `unit/test_bench_static.py`, `e2e/test_bench.py` ; réalignés : `unit/test_shell_static.py`, `unit/test_chat_static.py`, `unit/test_evaluation_static.py`, `e2e/test_shell.py`, `e2e/test_chat.py`.

## Rapport de dev

Ciblé (poste partagé : ni `tests/v2` complet, ni les autres E2E). Serveur : `test_bench_api.py` 14 verts, `test_bench_verdict.py` 7 verts, `test_layers.py`, `test_registry.py`, `test_structured_output.py`, `test_models.py`, `test_runs_api.py`, `test_chat_api.py`, `test_read_budget.py` verts. Statiques : `test_bench_static.py`, `test_shell_static.py`, `test_chat_static.py`, `test_evaluation_static.py`, `test_static_split.py`, `test_arena_static.py`, `test_picker_static.py` verts. E2E : `test_bench.py` 18 verts (Edge, `-m e2e`), E2E de la coquille et du Chat touchés par le passage à `available` verts.

## Journal

- 2026-10-19 · dev : spec, serveur (scénarios, service, verdict, instantané, liste, `structured_output`), écran en quatre modules, textes, CSS, route `available`, tests, réalignement des tests de la coquille.

## Points pour la revue

- `_Tee` enveloppe le modèle pour lire le texte de la tentative en cours : le verdict est calculé dans `metrics_extra`, avant la clôture du run, donc sans `finish_leaf` supplémentaire.
- Un banc en erreur (délai, `ram_guard`) n'a pas de `format_verdict` ni de mesures ; la sortie partielle reste dans `bench.output`.
- La story ne pose ni version ni tag (`2.0.0a7` par l'orchestrateur).

## Revue

Revue Opus du 2026-10-19, sur la branche fusionnée avec `origin/master` (7.1) sans conflit.

| Sévérité | Source | Constat | Suite | Motif |
|---|---|---|---|---|
| medium | second avis | Conflits avec `master` | rejeté | fusion d'`origin/master` faite sans conflit avant la revue |
| low | second avis n° 1 | « Scénario inconnu : » avec espace ASCII | rejeté | texte technique d'`invalid_request` ; les messages serveur (`errors.py`, `conversation_export.py`) gardent l'espace ASCII, l'insécable vaut pour le verdict affiché |
| low | second avis n° 2 | Texte après une clôture Markdown : « pas du JSON valide (ligne 1, colonne 1) » | corrigé | « La sortie a du texte autour de son bloc JSON » ; texte après le JSON : « La sortie a du texte après son JSON (ligne, colonne) » ; tests `unit/test_bench_verdict.py` |
| low | second avis n° 3 | « Délai dépassé (N s) » formé au front | rejeté | le front met en forme `detail.timeout_s` du serveur, sans calcul (AD-20) : la décision n° 1 est tenue pour le Banc ; changer l'enveloppe partagée de `timeout` toucherait le chat et l'Arène (8.1) |
| low | second avis n° 4 | Violation d'`enum` sans les valeurs permises | corrigé | `schema_errors` les cite (« valeur hors de la liste permise (Positif, Neutre, Négatif) »), aussi dans le message technique d'`invalid_output` ; contrat mis à jour |
| low | revue | `_plain` traduisait les noms de type partout dans la raison : une valeur permise « string » ou « object » aurait été traduite | corrigé | seuls les types de « type attendu » sont traduits ; test `test_enum_violation_names_the_allowed_values_untranslated` |
| low | revue | `NaN` et `Infinity` acceptés par `json.loads` : « Format » jugé lisible et `formatted` qui n'est pas du JSON | corrigé | refusés (`parse_constant`), « La sortie n'est pas du JSON valide (NaN ou Infinity) » |
| low | revue | `_Tee` : format imposé violé, run `ok` sans jetons ni débit (l'adaptateur lève avant `Done`) | rejeté | variante déclarée et consignée au contrat ; le CO₂ local reste mesuré (tracker), le cloud est dit non mesurable sans jetons |
| low | revue | Complexité : `list_bench_runs` parcourt les événements de chaque run pour trouver `metrics` (clé primaire `(run_id, seq)`, sans index sur `type`) ; flux : `textContent` réécrit une fois par image | rejeté | 20 runs au plus par appel, quelques milliers d'événements : sans impact mesurable sur un poste local ; le rendu en flux est groupé par `requestAnimationFrame` (Complexité : 0 constat à impact réel) |
| — | revue | `structured_output` (registre, local et cloud), exports `metric`/`co2Metric` de `wl-chat-thread.js`, branche `bench` de `runs/snapshot.py` après fusion (7.1, 6.4, 6.5), consigne d'extraction nommant ses champs | vérifié | tests statiques et API verts ; écart d'extraction déclaré |
