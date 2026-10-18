---
title: 'La coquille et l''Accueil suivent la maquette validée'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: 'bb272a5'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/sprint-change-proposal-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/EXPERIENCE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-8.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-1-11.md'
warnings: []
deferred:
  - summary: >-
      Le sprite `icons.svg` du front garde ses 19 symboles Material Symbols Rounded d'origine ; les 18 symboles que la maquette y a ajoutés (hourglass, check-circle, cancel, schedule, block, autorenew, download, upload, replay, edit, delete, folder, open-in-full, close-fullscreen, lightbulb, terminal, chat, stop) sont des tracés Material Icons (Filled) et n'entrent pas. Les versions Rounded officielles de ces symboles (et celles que DESIGN.md nomme sans que le sprite les ait : `build`, `psychology`, `output`, `pending_actions`, `leaderboard`) sont à fournir par Anaël ; la story qui a besoin d'une icône la demande au test des icônes, qui échoue tant qu'elle manque.
    evidence: |-
      Aucun téléchargement pendant le run (consigne) ; `docs/maquette-v2/icons.svg` n'a que des tracés Filled en plus des 19 d'origine ; `test_every_icon_the_front_uses_is_in_the_sprite_and_the_sprite_is_rounded_only`.
    location: src/wavelocalai/web/static/icons.svg
    severity: medium
  - summary: >-
      Écarts ouverts du §7 (d) du correct course rencontrés ici, non tranchés, variante la plus conservatrice gardée : n° 3 (l'Arène garde l'icône `swords` du code livré et de la maquette, pas `leaderboard` de DESIGN.md ; aucune carte Références n'est créée) et n° 9 (la carte Mode de l'Accueil garde son état actuel, sans compteur « N appels cloud dans cette session »).
    evidence: |-
      `sprint-change-proposal-2026-10-19.md` §7 (d) ; `core/registry.js` (icône `swords`), `screens/home.js` (carte Mode inchangée).
    location: src/wavelocalai/web/static/core/registry.js
    severity: low
  - summary: >-
      Nom long du module Modèles sur l'Accueil : le tableau d'EXPERIENCE.md n'en donne pas (le module y est « nouveau »). « Installation et choix par usage » est celui de la maquette (`accueil.modules.models.long`) ; « Arène des modèles » (Arène) vient du tableau d'EXPERIENCE.md. À confirmer par Anaël avec la livraison des écrans.
    evidence: |-
      `docs/maquette-v2/i18n/screens/accueil.fr.json` ; `i18n/fr.json` (`home.modules_long`).
    location: src/wavelocalai/web/static/i18n/fr.json
    severity: low
---

# Story 1.12 : la coquille et l'Accueil suivent la maquette validée

## Objectif

Story de suite du correct course du 2026-10-19 : appliquer à la coquille (1.8, 1.9) et à l'Accueil (1.11), déjà livrés, les décisions de la maquette validée qui les touchent (D-2, D-6, D-7, D-8, D-9, D-10), pour que les écrans suivants s'y branchent sans retouche. Front seul, sans Ollama, aucun code serveur, aucune version changée (elle part dans la préversion suivante).

## Critères d'acceptation et preuves

1. **Thème « Système » (D-7).** Le menu Affichage propose Clair (défaut), Sombre, Système. `core/theme.js` garde le choix (`light`, `dark` ou `system`) dans `localStorage` (`wl.theme`) et pose sur `<html>` le jeu appliqué `data-theme="light|dark"` (aucun troisième jeu de jetons : `tokens.css` est inchangé) et le choix `data-theme-choice`. En « Système », il lit `prefers-color-scheme` et se met à jour quand le réglage du système change, page ouverte. Preuves : `test_the_system_theme_follows_prefers_color_scheme_live_and_is_remembered`, `test_an_explicit_choice_ignores_the_system_and_light_stays_the_default`, `test_the_system_theme_still_applies_when_storage_is_blocked`, `test_axe_finds_no_violation_on_the_shell_and_the_home_in_system_theme` (clair et sombre).
2. **Interrupteurs en bascule (D-6).** « Mode projection » est `<input type="checkbox" role="switch">`, au même rendu `wl-switch` que « Autoriser le cloud » : piste bordée `ink-secondary` sur `surface-alt`, curseur `surface`, activée en `primary-fill` avec l'icône `check` dans le curseur ; libellé texte toujours à côté. Preuves : `test_projection_and_cloud_are_switches_with_the_same_wl_switch_rendering`, `test_switch_state_reads_in_the_shape_not_only_in_the_color`, `test_the_switch_css_follows_the_wl_switch_tokens_of_design_md` et `test_every_checkbox_of_the_shell_is_a_wl_switch_with_the_check_in_its_thumb` (`test_shell_static.py`).
3. **Icônes (D-2).** Chaque symbole utilisé par le front (HTML, `icon("…")`, registre, composants) existe dans le sprite, et le sprite ne contient que des symboles Material Symbols Rounded (`viewBox="0 -960 960 960"`) ; provenance et licence dans `icons.LICENSE.txt`. Les tracés Filled de la maquette n'y entrent pas (voir `deferred`). Preuves : `test_every_icon_the_front_uses_is_in_the_sprite_and_the_sprite_is_rounded_only`, `test_the_icon_check_sees_a_filled_symbol_and_a_missing_one`, `test_icons_license_names_the_provenance`.
4. **Liens de l'Accueil (D-9, D-10).** Chaque lien de module porte le nom court du menu en titre, le nom long en sous-titre et la phrase de résumé ; le `h1` reste « Accueil ». Preuves : `test_an_available_module_gets_a_link_with_short_name_long_name_and_summary`, `test_the_home_keeps_a_single_h1_accueil`.
5. **Routes de la maquette (D-8).** Le registre déclare `planned` : `#/arene/references`, `#/arene/banc/<run_id>`, `#/documents/evaluation/<run_id>`, `#/agents/equipe/<run_id>`, `#/modeles/<tag>`. Aucun lien actif ni écran ; une route `planned` tapée à la main renvoie à l'Accueil. Preuves : `test_registry_declares_the_routes_of_the_contract_and_the_six_modules`, `test_the_mockup_routes_are_planned_with_their_path_parameter`, `test_planned_or_unknown_route_goes_back_to_home` (les cinq adresses tapées à la main), `test_a_planned_mockup_route_has_no_active_link_anywhere`.
6. **Accessibilité et mise en page.** axe-core, zéro violation et aucune exclusion, en clair, sombre, Système, projection ; 320 px sans défilement horizontal, menu Affichage ouvert compris. Preuves : `test_axe_finds_no_violation_in_projection_mode_with_every_theme` (clair et sombre, interrupteurs activés, 320 px), `test_axe_finds_no_violation_on_the_home_in_system_theme_with_every_module`, `test_the_home_with_every_module_link_has_no_horizontal_scroll` (320, 768, 1 440 px), et les tests existants de la coquille, de la barre haute et de l'Accueil.
   Deux débordements à 320 px en projection, jusque-là non testés, sont corrigés : valeur de métrique réduite sous 480 px (`base.css`, `overflow-wrap` de `wl-metric`) et grilles `minmax(min(16rem, 100%), 1fr)` (`screens.css`).

## Fichiers

- `web/static/core/theme.js` (choix, thème appliqué, écoute de `prefers-color-scheme`), `core/shell.js` (menu Affichage), `index.html` (rendu `wl-switch` des deux interrupteurs, option Système), `components.css` (`.switch`), `core/registry.js` (cinq routes), `screens/home.js` (liens à trois niveaux ; un module dont le premier écran porte un paramètre de chemin facultatif, comme Modèles, reste listé) et `screens.css`, `base.css` (projection étroite), `i18n/fr.json` (`shell.display.system`, `screens.arena-references`, `home.modules_long`), `icons.LICENSE.txt`
- Tests : `tests/v2/e2e/test_shell.py`, `test_home.py`, `test_topbar.py`, `tests/v2/unit/test_shell_static.py`

## Choix notables

- `data-theme` reste le jeu appliqué (`light` ou `dark`) : tout le CSS, les composants, axe et les tests existants le lisent ainsi ; `data-theme-choice` porte le choix de la personne.
- Le défaut reste « Clair » : « Système » n'est appliqué qu'après avoir été choisi (décision n° 7 : « Clair (défaut) »).
- L'icône de l'Arène reste `swords` et la carte Mode reste telle quelle (écarts ouverts n° 3 et n° 9, variante conservatrice).

## Reports

Voir l'en-tête `deferred` : sprite officiel complet (à fournir), écarts n° 3 et n° 9, noms longs d'Arène et de Modèles. Les stories 3.6 et 4.9 retouchent `screens/home.js` ensuite (cartes « Démo recommandée » et « Assistant documentaire »).
