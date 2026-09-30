---
title: 'Tests e2e fiables sur un vrai poste'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context:
  - '{project-root}/tests/e2e/README.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Au premier passage réel (poste-rtx3060, 27/09), quatre tests e2e échouent à chaque fois alors que l'app fonctionne : ils lisent la page juste après une action dont l'effet côté navigateur est immédiat (bouton radio coché, valeur de liste changée, liste vidée), avant que le serveur ait fini le rerun (`test_crew_renders_without_launching`, `test_arena_two_local_models_with_judge`, `test_arena_timeout_does_not_block_others`) ; et la mesure de débit du banc d'essai porte sur 22 tokens, parce que le scénario par défaut « Classification (JSON) » impose une réponse JSON courte (`test_lab_throughput_excludes_loading`).

**Approach:** Après chaque action, attendre un état que seul le rerun du serveur produit (élément rendu, bouton activé ou désactivé, avertissement affiché) avant de lire ou de cliquer ; vider la consigne système du banc d'essai avant la mesure de débit. Seuls les tests changent : aucun fichier de `src/`, aucune assertion affaiblie, aucun `skip` ni `xfail`.

</frozen-after-approval>

## Implementation Notes

- `test_agents.py` : `_switch_mode` attend un élément rendu par le serveur pour chaque mode (`MODE_MARKERS` : titre « Enchaînement des agents », champ de consigne de l'agent seul) ; l'équipe met environ 6 s à se rendre au premier passage (chargement de CrewAI).
- `test_arena.py` : après `multiselect_clear`, attente de la légende `MIN_MODELS_CAPTION` ; après l'ajout des modèles, du bouton activé ; après le choix du juge, du rerun puis de l'état attendu de « Note peu fiable ».
- Débit du banc d'essai : scénario « Raisonnement pas à pas » (prose) au lieu de vider la consigne système (le libellé « Consigne système » désignait deux éléments) ; la question par défaut du scénario, rendue par le serveur, est attendue avant la saisie.
- Écart à l'intention, assumé : la comparaison des débits devient unilatérale (à froid ≥ 85 % du débit à chaud). Mesuré : 187 tok/s à froid contre 160 à chaud ; un passage à froid plus rapide vient du plafond de puissance variable du GPU portable (80 à 95 W), et seul un débit à froid plus bas trahirait un chargement compté. README e2e et docstrings mis à jour.
- `test_arena_timeout.py` : attente du bouton activé avant d'ouvrir les réglages du juge.
- Vérifié sur poste-rtx3060 : `test_agents.py`, `test_arena.py`, `test_arena_timeout.py` réussis (la suite complète, relancée après la story 14).

## Review Triage Log

Revue Blind Hunter (10 constats) :

- Cause commune dans les helpers (`until` côté navigateur) — medium, différé (compteur d'exécutions à concevoir).
- Conditions `until` déjà vraies avant le rerun — medium pour l'avertissement du juge (corrigé : attente du rerun d'abord) ; low pour la légende quand ≤ 1 modèle est présélectionné, rejeté (jamais le cas avec deux modèles installés qui tiennent en mémoire).
- Saisies du banc validées sans état du serveur attendu — medium, corrigé (question du scénario attendue).
- Détour par les réglages avancés — corrigé (scénario en prose, plus simple).
- Messages d'échec pauvres et délai de 120 s — low, rejeté (rare, sans effet sur le résultat).
- Lancement juste après le choix du juge dans test_arena_timeout — false : Streamlit envoie l'état courant des widgets avec la demande de rerun du bouton.
- Assertions redondantes — low, rejeté (gardées explicites après les attentes).
- Textes codés en dur — low, corrigé pour `MIN_MODELS_CAPTION` ; le titre de l'équipe n'a pas de constante dans l'app.
- `MODE_MARKERS` (placement, `exact`, `.first`) — low, corrigé.
- Attente du radio redondante — low, gardée avec un commentaire (échec clair si le clic est manqué).

