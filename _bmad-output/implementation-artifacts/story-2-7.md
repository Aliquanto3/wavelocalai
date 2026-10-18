---
title: 'Le Chat prend la créativité du modèle et s''exporte sur écran étroit'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '72137a4'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-2.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-6.md'
warnings: []
deferred:
  - summary: >-
      Le catalogue `config/models_catalog.json` ne porte aucun champ `default_temperature` : le registre le lit s'il existe (entrée de 0 à 2, sinon ignorée), mais le générateur `scripts/build_catalog.py` ne l'écrit pas (fichier hors périmètre : AGENTS.md l'interdit à la main, et un changement du générateur est une PR dédiée). Aujourd'hui la valeur ne vient que d'Ollama ; sans paramètre publié, `null` et repli du front à 0,2. À décider par Anaël : ajouter la température conseillée au catalogue (par un lot du générateur) ou s'en tenir à Ollama.
    evidence: |-
      `test_the_versioned_catalog_needs_no_temperature_field` (granite4:350m, au catalogue, rend `null`).
    location: src/wavelocalai/models/catalog.py
    severity: low
  - summary: >-
      Le menu « Exporter » est livré sans icône « download » : le sprite `icons.svg` de la v2 n'en contient pas (la maquette l'ajoute, D-2). Les boutons gardent leur texte seul, comme avant ; l'icône viendra avec l'élargissement du sprite aux icônes de la maquette.
    evidence: |-
      `components/export-menu.js` (seule `expand-more` sur le bouton replié).
    location: src/wavelocalai/web/static/components/export-menu.js
    severity: low
---

# Story 2.7 : le Chat prend la créativité du modèle et s'exporte sur écran étroit

## Objectif

Pour chaque modèle, le curseur « Créativité » part de la valeur que son fabricant recommande (D-12) ; sous 768 px, les deux boutons de téléchargement cèdent la place à un menu « Exporter » (D-3), composant que l'Arène (3.6) reprendra ; le premier appel d'un modèle prévient qu'il charge en mémoire (UX-DR17) ; un `409 run_busy` rejoint garde le message tapé (D-13, test E2E dédié). Aucune version à changer (préversion suivante).

## Critères d'acceptation et preuves

1. **`default_temperature` de `GET /api/models`.** `ModelInfo.default_temperature` (`float | null`) : ligne `temperature` des paramètres de `/api/show` d'Ollama (lue avec les faits du modèle, en cache `model_facts`), sinon champ `default_temperature` de l'entrée du catalogue, sinon `null` ; hors de 0 à 2 (borne du curseur), la valeur est ignorée ; un modèle cloud rend `null`. La route reste servie depuis le cache (aucun appel Ollama nouveau) ; Ollama arrêté, elle répond sous 300 ms avec la température des faits en cache. Preuve : `test_the_temperature_is_read_from_the_parameters_text`, `test_the_registry_serves_the_ollama_temperature_then_the_catalog_then_null`, `test_ollama_wins_over_the_catalog_and_bad_catalog_values_are_ignored`, `test_a_cloud_model_has_no_default_temperature` ; web `test_default_temperature_is_served_from_ollama_parameters_and_null_otherwise`, `test_default_temperature_comes_from_the_cache_under_300_ms_with_ollama_down` (et `test_read_budget.py`, inchangé : la route y est déjà). Integration : `test_real_default_temperature_is_what_ollama_publishes_or_null` (vrai Ollama, `qwen2.5:1.5b` ne publie rien : `null`).
2. **`wavelocalai.toml` inchangé.** Ni la lecture de la température, ni le choix d'un modèle, ni l'envoi d'un message n'écrivent le `.toml`. Preuve : `test_the_toml_is_unchanged_after_choosing_a_model_and_reading_its_default` (empreinte SHA-256 avant et après).
3. **Curseur « Créativité ».** Il prend la `default_temperature` du modèle choisi, ou 0,2 si `null` ; changer de modèle le remet au défaut du nouveau tant que la personne ne l'a pas déplacé dans cette conversation ; « Effacer la conversation » le rend au modèle ; une conversation rouverte garde la créativité de son dernier run. La valeur affichée est celle envoyée dans `POST /api/chat/runs`. Une ligne d'aide dit le conseil (« Valeur conseillée pour X : 0,7. » ou « Valeur par défaut : 0,2 (ce modèle n'en conseille pas). »). Preuve E2E : `test_the_slider_takes_the_default_of_the_chosen_model_and_the_fallback_when_unknown`, `test_a_moved_slider_stays_while_the_model_changes_and_the_sent_value_is_the_shown_one`, `test_an_untouched_slider_sends_the_model_default`, `test_clearing_the_conversation_gives_the_slider_back_to_the_model`, `test_a_reopened_conversation_keeps_its_own_creativity`.
4. **Menu « Exporter » sous 768 px.** Composant partagé `components/export-menu.js` (`exportMenu({items, label})` : `root`, `setDisabled`, `setHidden`, `open`, `close`). Dès 768 px, les deux boutons existants ; en dessous, un bouton « Exporter » (`aria-haspopup="menu"`, `aria-expanded`) qui ouvre la liste des deux formats. Clavier : Entrée, Espace ou Flèche bas ouvrent sur le premier format, Flèches haut et bas, Début et Fin parcourent en boucle, Entrée ou Espace choisit, Échap ferme et rend le focus à « Exporter » (sans arrêter une réponse en cours), un clic ailleurs ou la sortie du focus ferme. Chaque entrée suit la route d'export du serveur (`GET /api/conversations/{id}.json|.md`, lien `Content-Disposition`), jamais de `blob:`. Désactivé sans conversation, comme les deux boutons. Preuve E2E : `test_two_buttons_from_768_px_and_one_export_menu_below` (1440, 768, 767, 320), `test_the_export_menu_is_driven_by_keyboard_and_gives_the_focus_back`, `test_escape_closes_the_menu_without_stopping_a_running_answer`, `test_a_menu_entry_downloads_from_the_server_route_without_blob` (JSON et Markdown, URL du serveur, aucun `blob:` dans le trafic), `test_a_click_elsewhere_closes_the_menu`, `test_the_narrow_export_is_disabled_without_a_conversation`.
5. **Premier chargement lent (UX-DR17).** `wl-run-status` affiche « Le premier appel charge le modèle en mémoire : de 8 à 26 secondes. » pendant l'étape `model_loading`, et lui seul : elle disparaît à la génération, à la fin et à l'arrêt. Le déclenchement sur `model_loading` est celui des stories 2.1 et 2.2. Preuve E2E : `test_the_first_load_message_shows_during_model_loading_only`, `test_the_first_load_message_goes_away_when_the_run_is_stopped`.
6. **409 rejoint.** Preuve E2E : `test_the_typed_message_stays_in_the_field_after_a_409_run_busy` (message resté dans le champ pendant et après le run rejoint, brouillon gardé, « Envoyer » de nouveau actif ; complète `test_a_busy_chat_is_joined_instead_of_showing_an_error` de la 2.2).
7. **Accessibilité.** axe-core, clair et sombre, sans violation ni exclusion : écran étroit (320 px) menu fermé puis ouvert, écran large, projection large et étroite, état « premier chargement lent » ; 320 px sans défilement horizontal (menu ouvert). Preuve : `test_axe_finds_no_violation_on_the_export_menu_at_320_px`, `test_axe_finds_no_violation_on_the_slow_first_load_state`.

## Choix de conception

- **Cache `model_facts`** : migration additive `0004_model_parameters.sql` (`ALTER TABLE ... ADD COLUMN parameters TEXT`, instantané `schema_v4.sql` ; aucune migration fusionnée ne change, AD-12). `parameters` est le texte brut de `/api/show` : `NULL` = détails jamais lus (lignes d'avant la migration), chaîne vide = lus sans paramètre. Une ligne en cache à `NULL` est relue une fois à l'actualisation suivante (`ModelRegistry.refresh`), et gardée telle quelle si Ollama ne répond pas. La température se déduit à la lecture (`ModelFacts.default_temperature`) : pas de colonne dérivée.
- **Source** : Ollama d'abord (la valeur du fabricant pour ce poids), puis le catalogue, puis `null`. Les exports de Chat n'en dépendent pas.
- **Front** : `picker.selected` porte la fiche de l'API (donc `default_temperature`) ; l'écran suit `wl-model-change` (choix) et un nouvel événement `wl-models-loaded` du sélecteur (liste relue : la fiche du modèle restauré arrive après la conversation). `creativityTouched` est local à l'écran, remis à zéro par « Effacer ».
- **Menu** : utilitaire plutôt que Custom Element (comme le `exportMenu` de la maquette) ; il construit les deux jeux de boutons et la bascule est faite en CSS (`@media (max-width: 767.98px)`), sans lecture de la largeur en JavaScript. Les couleurs viennent des jetons.

## Écarts au contrat et à la maquette

- **Libellés des boutons** : le code livré (2.2, 2.6) dit « Télécharger (JSON) » et « Télécharger (Markdown) » ; epics.md et la maquette disent « Télécharger en JSON » et « … en Markdown ». Libellés existants gardés (les E2E de 2.6 les lisent) ; à aligner d'un coup si Anaël le veut.
- **Message de premier chargement** : texte d'epics.md et d'EXPERIENCE.md (« … de 8 à 26 secondes. ») ; la maquette ajoute « sur ce type de poste. Les suivants sont plus rapides. », non repris.
- **Ligne d'aide du curseur** : « Valeur conseillée pour X : v. » vient de la maquette, absente d'epics.md ; ajoutée (elle rend le conseil lisible) ; à retirer si le contrat la refuse.
- **Icône « download »** de la maquette : non reprise (voir `deferred`).
- **Écrans « au moins un échange »** : sans conversation, le menu et les deux boutons restent affichés mais désactivés (comportement de 2.6) ; la maquette les masque. Variante conservatrice gardée.
- **Écarts du §7 (d) du correct course** : aucun ne touche cette story ; aucun n'est tranché ici.

## Fichiers

- Serveur : `models/facts.py` (`parameters`, `parse_temperature`), `models/facts_store.py`, `models/catalog.py` (`default_temperature` facultatif), `models/registry.py` (`ModelInfo.default_temperature`, relecture d'une ligne sans `parameters`), `store/migrations/0004_model_parameters.sql`
- Front : `components/export-menu.js` (nouveau), `components/index.js`, `components/wl-run-status.js`, `components/wl-model-picker.js` (`wl-models-loaded`), `screens/chat.js`, `components.css`, `i18n/fr.json`
- Tests : `tests/v2/unit/test_default_temperature.py` (nouveau), `tests/v2/unit/snapshots/schema_v4.sql`, `tests/v2/unit/test_model_helpers.py`, `tests/v2/web/test_models.py`, `tests/v2/integration/test_models_ollama.py`, `tests/v2/e2e/test_chat_creativity_export.py` (nouveau), `tests/v2/fake_ollama.py` (`parameters`)

## Journal

- 2026-10-19 · dev (Sonnet) · livré sur `feat/v2-chat-creativite` ; pas de revue ni de fusion ici (orchestrateur).
