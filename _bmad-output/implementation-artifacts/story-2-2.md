---
title: 'L''écran Chat libre affiche la réponse en flux et la reprend au retour'
type: 'feature'
created: '2026-10-18'
status: 'review'
baseline_commit: '1bc73e8'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/planning-artifacts/ux-designs/ux-wavelocalai-2026-09-26/DESIGN.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-2-1.md'
warnings: []
deferred:
  - summary: >-
      « Télécharger » (JSON, Markdown) de UX-DR21 n'est pas livré : le serveur n'a ni `GET /api/conversations/{id}` ni export `.json`/`.md`. « Effacer la conversation » est donc locale (le fil est vidé, la suivante ouvre une nouvelle conversation) ; la conversation reste en base. À reprendre avec les routes de conversation.
    evidence: |-
      `grep conversations src/wavelocalai/web/*.py` : aucune route ; `test_the_real_route_continues_the_same_conversation` (effacement local).
    location: src/wavelocalai/web/static/screens/chat.js
    severity: medium
  - summary: >-
      Le débit provisoire estime les tokens à 1 pour 4 caractères : les événements `token` sont groupés par 50 ms et ne donnent pas un compte exact. Le chiffre est dit « provisoire » (italique) et remplacé par `metrics` (débit d'Ollama, D3).
    evidence: |-
      `test_the_footer_is_provisional_and_italic_until_the_metrics_arrive`.
    location: src/wavelocalai/web/static/components/wl-chat-thread.js
    severity: low
  - summary: >-
      Les tableaux Markdown ne sont pas rendus (le texte reste affiché tel quel) ; les titres du modèle sont rendus en paragraphe gras (un seul `h1` par écran, la structure ne vient pas du modèle). Pas de reprise d'une réponse en cours après un rechargement complet de la page (seul l'aller-retour d'écran est couvert, `runs_active` du flux système le permettrait plus tard).
    evidence: |-
      `test_the_markdown_subset`.
    location: src/wavelocalai/web/static/core/markdown.js
    severity: low
  - summary: >-
      Le nom du modèle sur une réponse d'un run rejoint (`409 run_busy`) vient de `run_started.models` (le tag), son badge d'origine reste « Origine inconnue » jusqu'à `metrics`.
    evidence: |-
      `test_a_busy_chat_is_joined_instead_of_showing_an_error`.
    location: src/wavelocalai/web/static/screens/chat.js
    severity: low
---

# Story 2.2 : l'écran Chat libre affiche la réponse en flux et la reprend au retour

## Objectif

`#/arene/chat` : un écran de chat qui affiche le premier token dès réception, s'arrête en moins d'une seconde, et reprend le flux par `?after=<seq>` quand on revient d'un autre écran. Front seulement ; le serveur de la story 2.1 n'est pas modifié. Ferme le critère E2E de reprise de CAP-4.

## Critères d'acceptation et preuves

1. Module Arène `available` (entrée `#/arene/chat`), onglets « Arène » et « Banc d'essai » désactivés avec leur raison en texte visible (`core/screen-tabs.js`). L'écran monte `wl-model-picker` (défaut `chat` et sa raison), le curseur « Créativité » (0 à 2, température), le champ « Écrivez votre message » et l'aide « Entrée : envoyer · Maj+Entrée : nouvelle ligne · Échap : arrêter ». Preuve : `test_the_screen_shows_the_picker_...`, `test_the_arena_module_is_available_and_its_other_tabs_are_disabled_...`.
2. `wl-chat-thread` (`role="log"`, `aria-live="off"`) : les tokens vont dans un nœud tampon dès réception, le Markdown (`core/markdown.js`, sans `innerHTML`, sous-ensemble sûr, liens `http(s)`/`mailto` seulement) est rendu au plus toutes les 150 ms et à la fin ; raisonnement replié ; défilement qui suit seulement en bas, sinon « Aller à la fin » ; annonce `aria-live="polite"` à la fin seulement (« Réponse de <modèle> terminée, N tokens. »). Preuve : `test_tokens_are_shown_as_safe_markdown_and_the_footer_turns_final` (HTML du modèle affiché en texte, `window.__pwned` jamais posé, rien d'annoncé pendant le flux), `test_the_markdown_subset`, `test_scrolling_follows_only_from_the_bottom_...`, `test_chat_static.py`.
3. Pied de réponse : badge, « Débit N tokens/s (provisoire) » en italique calculé par le client, durée, tokens ; à `metrics`, débit du serveur (aide D3), « Chargement x s » et « Durée totale y s » à part, badge « estimé » si `tps_source = wallclock`. Preuve : `test_the_footer_is_provisional_and_italic_until_the_metrics_arrive`, test du critère 2.
4. Arrêter ou Échap : flux arrêté en moins d'une seconde, partiel gardé et marqué « Arrêté » ; le run est `cancelled`. Preuve : `test_the_stop_button_ends_the_stream_in_under_a_second_and_keeps_the_partial`, `test_the_escape_key_stops_the_generation_in_under_a_second`.
5. Reprise : l'écran masqué ferme son flux en gardant le dernier `seq` (`close({keepSeq})`) et le rouvre au retour par `?after=<seq>` ; aucune perte ni doublon, génération non interrompue (run `ok`). `409 run_busy` : le run actif est rejoint, sans erreur, le message reste dans le champ. `allow_cloud` du store sur chaque commande ; brouillon de saisie dans `localStorage` seulement (`core/drafts.js`). Preuve : `test_the_stream_resumes_by_after_without_loss_or_duplicate_after_a_visit_to_home` (deux requêtes de flux, la seconde en `?after=`), `test_a_busy_chat_is_joined_instead_of_showing_an_error`, `test_the_cloud_switch_is_not_stored_and_the_commands_carry_the_store_value`, `test_the_draft_survives_a_reload_and_is_cleared_once_sent`, `test_the_real_route_continues_the_same_conversation`.
6. Accessibilité : axe-core, clair et sombre, zéro violation sans exclusion (écran vide, réponse en cours, réponse terminée avec aide ouverte, réponse arrêtée) ; aucune requête hors 127.0.0.1. Preuve : `test_axe_finds_no_violation_on_the_chat_screen`, `..._on_a_stopped_answer`, `test_every_request_stays_on_127_0_0_1`.
7. A19 (décision Q1) : le bouton plein « Envoyer » est sur `var(--color-primary-fill)` avec `--color-on-primary` ; désactivé, fond `surface-alt`, bordure `line`, texte `ink-secondary`, opacité 1. `--color-primary` ne reste que pour les bordures, contours et l'interrupteur coché ; aucun composant existant (barre haute, sélecteur, `wl-run-status`) ne pose de texte blanc sur `--color-primary`. Preuve : `test_the_first_filled_button_uses_primary_fill_with_white_text_and_passes_color_contrast` (clair et sombre, règle `color-contrast`, sans exclusion), `test_a_disabled_filled_button_is_told_by_colors_not_by_opacity`, dérive de `tokens.css` verte (`test_shell_static.py`).

## Choix de conception

- Un seul lecteur du flux d'un run (le dernier `seq` est unique par run dans le store) : l'écran lit le flux et alimente `wl-run-status` en mode piloté (`driven`, `feed()`, `abandon()`). Échap n'agit que si le composant est visible (un écran gardé en mémoire est masqué).
- Le code d'erreur de coupure est `generation_interrupted` (AD-5) ; le front affiche le message de l'enveloppe, sans nom de code en dur.

## Fichiers

- `src/wavelocalai/web/static/screens/chat.js`, `components/wl-chat-thread.js`, `core/markdown.js`, `core/drafts.js`, `core/screen-tabs.js`, `chat.css`
- Ajouts : `core/sse.js` (`close({keepSeq})`), `core/api.js` (`startChat`), `components/wl-run-status.js` (mode piloté), `components/wl-model-picker.js` (`selected`), `core/registry.js`, `i18n/fr.json`, `index.html`
- Tests : `tests/v2/e2e/test_chat.py`, `tests/v2/unit/test_chat_static.py`, `tests/v2/unit/test_shell_static.py`

## Revue

Revue Opus, une passe, sur 67042f2 (avec la liste du second avis Haiku).

- medium, second avis 1 : corrigé. La fin était annoncée deux fois (« Terminé » par l'étape `role="status"` de `wl-run-status`, puis la phrase du fil) et l'étape réécrivait le même texte à chaque rendu (« Démarrage… » deux fois). En mode piloté, l'état final passe en `aria-live="off"` (l'écran annonce la fin), et l'étape n'est réécrite que si son texte change. Le changement d'étape (« Génération… ») reste annoncé : c'est le contrat de `wl-run-status` (UX-DR8, EXPERIENCE.md, trace des agents), pas le contenu du flux. Preuve : `test_only_the_stage_change_and_one_end_announcement_are_spoken` (compte les écritures dans les régions vivantes : « Génération… » puis une seule phrase de fin).
- medium, second avis 2 : corrigé. Confirmé dans Edge : `suspend()` lisait `scrollTop` après le masquage (0), la personne remontée revenait en haut. La position vue est mémorisée à chaque défilement visible. Preuve : `test_a_scrolled_up_position_is_kept_after_a_visit_to_home`.
- low, second avis 3 : corrigé. Pendant `startChat`, Entrée relançait un POST et Effacer restait actif ; un drapeau `pending` bloque les deux, et un texte tapé pendant la requête n'est plus effacé. Preuve : `test_enter_pressed_again_while_the_command_is_pending_sends_nothing_more`.
- low, second avis 4 : corrigé. Mesuré dans Edge : « [a](b » répété (50 Ko) prenait 260 ms par rendu (« [a » seul : 17 ms, pas quadratique en pratique). Libellé borné à 500 caractères, adresse à 2 048 sans parenthèse : 0,2 ms. Preuve : `test_a_pathological_link_pattern_renders_in_linear_time`.
- low, second avis 5 : corrigé. Un run lancé pendant que l'écran est masqué n'ouvre plus de flux ; il s'ouvre au retour (AD-6).
- low, second avis 6 : rejeté. La pause de 1,8 s du test de reprise est l'absence elle-même (la génération doit avancer sans lecteur) et les durées de moins d'une seconde sont le critère mesuré ; les attentes de fin passent par `wait_for`.
