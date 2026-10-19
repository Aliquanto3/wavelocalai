---
title: 'Les outils de la v1 pour les agents, sans chemin libre (serveur)'
type: 'feature'
created: '2026-10-19'
status: 'review'
baseline_commit: '2f3db79'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/_bmad-output/planning-artifacts/decisions-2026-10-19.md'
  - '{project-root}/_bmad-output/planning-artifacts/reports-v2-inventaire.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-wavelocalai-2026-10-18/ARCHITECTURE-SPINE.md'
  - '{project-root}/_bmad-output/specs/spec-wavelocalai-v2/contrat-api.md'
  - '{project-root}/_bmad-output/implementation-artifacts/story-6-1.md'
warnings: []
deferred:
  - summary: >-
      Écart nouveau, variante conservatrice : l'épique parle d'un `_validate_path` de la v1 « copié », mais `src/core/agent_tools.py` n'en a pas (la v1 lit un chemin libre : `analyze_csv("data/sales.csv")`, et écrit dans `outputs/` relatif au dossier courant). Le confinement est donc écrit à neuf (`agents/tools/workspace.py`, `Workspace`) : racine fixe `<données>/agent_work`, noms relatifs seulement, refus de `..`, chemins absolus, lecteurs, UNC, `~`, flux Windows, périphériques réservés, noms cachés, liens symboliques, jonctions et sorties de la racine une fois résolu. Les fichiers produits sont à plat dans la racine ; la lecture admet un sous-dossier.
    evidence: |-
      `tests/v2/unit/test_workspace.py` (40 passés ; 5 sautés ici : ce poste Windows n'a pas le droit de créer un lien symbolique, ils tournent sur la CI Linux et macOS ; la jonction, elle, est jouée), `tests/v2/web/test_agent_tools_api.py::test_an_agent_cannot_read_outside_the_work_folder`, `::test_an_agent_cannot_write_outside_the_work_folder`, `::test_the_outputs_route_serves_only_flat_produced_files`.
    location: src/wavelocalai/agents/tools/workspace.py
    severity: medium
  - summary: >-
      Écarts nouveaux, variante conservatrice. (1) « Analyse de données » : l'épique dit « sans pandas si possible (`csv` standard) » avec « les mêmes résultats que la v1 ». Les tableaux de la v1 (`to_string`, `describe`, `value_counts`) ne se retrouvent octet pour octet qu'avec pandas, déjà verrouillé : il est gardé (importé dans la fonction, fil à part) et le test compare au texte exact de la v1 sur un jeu de test. Excel (`.xlsx`, `.xls`) n'est plus pris en charge (« Format non supporté. Utilisez .csv ») : l'épique ne parle que de CSV et la lecture d'Excel tirerait `openpyxl` et `xlrd`. (2) Un CSV à analyser se dépose à la main dans `<données>/agent_work` : l'envoi de fichier depuis l'écran n'existe pas (6.4 si Anaël le veut). (3) Aucun quota ni nettoyage du dossier de travail : les fichiers produits y restent (l'effacement AD-13 d'un run ne les touche pas) ; seule la taille d'un fichier lu est bornée (`agents.max_input_mb`).
    evidence: |-
      `agents/tools/files.py::analyze_csv`, `tests/v2/unit/test_builtin_tools.py::test_the_csv_analysis_gives_the_exact_text_of_the_v1` (cinq requêtes), `::test_the_csv_analysis_refuses_free_paths_and_other_formats`.
    location: src/wavelocalai/agents/tools/files.py
    severity: low
  - summary: >-
      Écarts nouveaux, variante conservatrice. (1) `send_email` est inscrit `sensitive` et indisponible sans SMTP, mais la 6.2 n'envoie rien : la boucle le refuse avant son exécution (6.1) et sa fonction ne prépare qu'un brouillon ; aucun code d'envoi (`smtplib`, socket, sous-processus) n'existe dans `agents/tools/` (test AST). L'envoi est la 6.3. (2) Les variables SMTP (`SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, noms de la v1) entrent dans `Settings.smtp` ; le serveur vaut `smtp.gmail.com` par défaut comme dans la v1, donc l'outil n'est indisponible que si `SMTP_USER` ou `SMTP_PASSWORD` manque, et le mot de passe est un secret masqué dans les étapes. (3) Disponibilité : un module Python requis absent (`find_spec`) rend aussi l'outil indisponible, avec sa raison. (4) La liste (`GET /api/agents/tools`) porte la ligne courte de l'écran (`summary`, celle de `TOOLS_METADATA` de la v1) dans `description` ; la consigne longue rendue au modèle reste dans `AgentTool.description` et n'est pas exposée.
    evidence: |-
      `tests/v2/unit/test_builtin_tools.py::test_the_email_tool_only_prepares_a_draft_and_the_module_cannot_send`, `::test_smtp_settings_come_from_the_environment_and_the_password_is_a_masked_secret`, `tests/v2/web/test_agent_tools_api.py::test_a_sensitive_tool_is_still_never_run_without_approval`, `::test_the_smtp_password_never_reaches_the_steps`.
    location: src/wavelocalai/agents/tools/builtin.py
    severity: low
  - summary: >-
      Report de la revue de la 6.1 traité en variante conservatrice : plafond d'appels d'outils **par tour** (`agents.max_tool_calls_per_turn`, 8) ; les appels au-delà sont publiés (`tool_call`) mais refusés en `tool_result` (`failed`, durée 0) sans être exécutés, car un fournisseur rejette un appel d'outil resté sans résultat. Restent sans plafond : un total par run (la borne reste `max_turns` fois le plafond, soit 80 appels au plus par défaut), le dédoublonnage d'appels identiques et un délai global de tâche. `tool_timeout_s` coupe l'attente d'un outil mais pas le fil qui calcule (pandas, matplotlib, `system_monitor` : bornés par la taille d'entrée ; la calculatrice a son propre délai de 2 s).
    evidence: |-
      `tests/v2/web/test_agent_tools_api.py::test_calls_beyond_the_per_turn_cap_are_refused_not_run`, `::test_the_cap_applies_to_each_turn_separately`, `agents/loop.py` (`TOO_MANY_CALLS`).
    location: src/wavelocalai/agents/loop.py
    severity: low
  - summary: >-
      Hors périmètre, pour la 6.4 : les reports B14 (étapes dans `wl-run-status`) et B15 (rendu Markdown du gras d'une réponse d'agent) de `reports-v2-inventaire.md` sont du front, portés par les « Reports » de la 6.4 dans `epics.md`. Un nom de fichier produit avec accents est cité en pourcentage dans `artifact_url` (`/api/outputs/bilan%20%C3%A9t%C3%A9.md`) : l'écran n'a qu'à suivre le lien. Rien n'a été joué sur un fournisseur cloud ; le test d'intégration a tourné sur le vrai Ollama (`qwen2.5:1.5b`) et a appelé la calculatrice puis le rapport Markdown du registre de production.
    evidence: |-
      `tests/v2/integration/test_agent_tools_ollama.py`.
    location: _bmad-output/planning-artifacts/reports-v2-inventaire.md
    severity: low
---

# Story 6.2 : les outils de la v1 pour les agents, sans chemin libre (serveur)

## Objectif

Un agent retrouve les neuf outils de la v1 (Heure, Calculatrice, Recherche interne Wavestone, Analyse de données, Génération de document, Génération de graphique, Rapport Markdown, Moniteur système, Envoi d'email), avec ce qui les rend disponibles, sans qu'aucun ne touche un chemin arbitraire du disque. Serveur seulement : l'écran est la 6.4, l'approbation de l'email la 6.3.

## Critères d'acceptation et preuves

1. **Outils copiés, un schéma par outil** : `agents/tools/{basic,files,builtin}.py` reprennent les fonctions `_*_impl` de `src/core/agent_tools.py` (sans `@tool`, sans `src.*`), chacune avec son schéma JSON neutre, et le registre de production (`build_registry`) les porte. Les résultats sont ceux de la v1 : calculatrice (`_calculate_safe` copiée : liste blanche, délai de 2 s), recherche interne, moniteur, et analyse de CSV comparée au texte exact de la v1. Preuve : `tests/v2/unit/test_builtin_tools.py` (34).
2. **`GET /api/agents/tools`** rend, par outil, `id`, `label` (lexique), `description`, `available`, `reason`, `sensitive`. « Envoi d'email » est `sensitive` et, sans SMTP dans `Settings`, indisponible avec « Configuration SMTP absente : renseignez SMTP_USER, SMTP_PASSWORD dans le fichier .env… » ; aucun `os.getenv` hors de `config.py` (`Settings.smtp`, le test AST de `test_config` le garde). Un outil indisponible demandé = `422 invalid_request` avant tout run. Preuve : `test_agent_tools_api.py::test_the_tools_are_listed_*`, `::test_the_email_is_listed_available_*`, `::test_an_unavailable_tool_is_refused_before_any_run`.
3. **Aucun chemin libre** : les outils ne reçoivent qu'un nom relatif au dossier de travail `<données>/agent_work` ; `..`, chemin absolu, lecteur, UNC, flux Windows, périphérique réservé, lien symbolique, jonction ou sortie de la racine = `tool_result` en échec (`failed: true`), rien n'est lu ni écrit hors de la racine. Preuve : `test_workspace.py` (évasions en lecture et en écriture), `test_builtin_tools.py::test_a_producing_tool_never_writes_outside_the_work_folder` (12), `test_agent_tools_api.py::test_an_agent_cannot_read_outside_the_work_folder` et `::test_an_agent_cannot_write_outside_the_work_folder`.
4. **Fichiers produits** : l'étape `tool_result` porte `artifact_url` (`/api/outputs/<nom>`) ; `GET /api/outputs/{name}` sert `.docx`, `.png` et `.md` en pièce jointe (`Content-Disposition`), nom validé (`422`), absent ou autre type (`404`). Preuve : `test_agent_tools_api.py::test_a_report_is_produced_then_downloaded_*`, `::test_a_csv_of_the_work_folder_is_analysed_and_a_chart_follows`, `::test_the_outputs_route_serves_only_flat_produced_files`.
5. **Plafond d'appels d'outils par tour** (report de la revue de la 6.1) : `agents.max_tool_calls_per_turn` (8) ; au-delà, refus en `tool_result` sans exécution. Preuve : `::test_calls_beyond_the_per_turn_cap_are_refused_not_run`, `::test_the_cap_applies_to_each_turn_separately`.
6. **Secrets et contrat** : le mot de passe SMTP est un secret masqué (`Settings.secret_values`, étapes et résultat rendu au modèle) ; protocole consigné dans `contrat-api.md` §« Agents (story 6.2) ». Preuve : `::test_the_smtp_password_never_reaches_the_steps`.

## Règles écrites

- **Un outil qui échoue de façon attendue** lève `ToolError` (nouveau, `agents/tools/registry.py`) : son message est le `tool_result` (`failed: true`) sans nom de classe ; `WorkspaceError` en dérive. Un résultat de la v1 qui commence par « Erreur » est un échec.
- **Aucun envoi d'email** dans `agents/tools/` : `send_email` ne prépare qu'un brouillon et la boucle le refuse (6.1) ; l'approbation et l'envoi sont la 6.3.
- **Couches** : `agents/tools/` n'importe que `config`, `errors` et ses voisins ; `pandas`, `numexpr`, `func_timeout`, `psutil`, `docx`, `matplotlib` dans les fonctions ; seul `web/` importe FastAPI (`tests/v2/unit/test_layers.py`). Le travail bloquant passe par `asyncio.to_thread`.

## Notes de développement

- Nouveaux : `agents/tools/{basic,files,builtin,workspace}.py`, `Settings.smtp`, `Settings.agent_work_dir`, `agents.max_tool_calls_per_turn` et `agents.max_input_mb` (`wavelocalai.toml`). Modifiés : `agents/loop.py` (plafond, `ToolError`), `agents/tools/registry.py` (`ToolError`, `summary`, `listing`), `web/routes_agents.py` (`GET /api/agents/tools`, `GET /api/outputs/{name}`), `web/app.py` (registre de production et `app.state.agent_workspace`), `contrat-api.md`.
- Aucune dépendance nouvelle (pandas, numexpr, func-timeout, psutil, python-docx et matplotlib sont déjà dans `uv.lock`). Aucun fichier du front. Aucun code d'erreur nouveau (`not_found`, `invalid_request`).

## Rapport de dev

- Tests : `tests/v2/unit` en entier, `test_agent_api`, `test_agent_tools_api` (14), `test_lifecycle`, `test_security`, `test_errors_envelope`, `test_chat_api` : 1052 passés, 6 sautés (5 liens symboliques non permis sur ce poste, 1 antérieur). Nouveaux : `test_workspace.py` (40 + 5 sautés), `test_builtin_tools.py` (34), `test_agent_tools_api.py` (14), `test_agent_tools_ollama.py` (1, vrai Ollama `qwen2.5:1.5b`, passé : calculatrice puis rapport téléchargé). Aucun E2E, aucune suite complète (poste partagé).
- Contrôle rapide propre. Ollama : modèle déjà installé, aucun téléchargement ; aucun appel cloud ni envoi d'email.

## Revue

Revue Opus, une passe, sur `2f3db79..f57f435` fusionné avec `origin/feat/v2-agent-serveur`. Aucune évasion du dossier de travail trouvée ; l'oracle de l'analyse CSV a été rejoué contre `_analyze_csv_impl` de la v1 : égal sur les cinq requêtes. Test d'intégration Ollama (`qwen2.5:1.5b`) rejoué : passé.

- low · second avis 1 · corrigé · `LAZY_ONLY` de `test_layers.py` ne gardait ni pandas, ni matplotlib, ni numexpr, ni func_timeout, ni psutil (docx y était) : ajoutés, aucun import au niveau module dans la v2.
- low · second avis 2 · corrigé · `_RESERVED` acceptait `COM¹`–`³`, `LPT¹`–`³`, `CONIN$`, `CONOUT$`, `CLOCK$` et `nul .md` (espace avant l'extension) : refusés, cas ajoutés à `test_an_output_name_is_one_plain_name`.
- low · second avis 3 · corrigé · une `OSError` (dossier non créable, sauvegarde refusée) passait au modèle et à l'écran avec le chemin absolu du dossier de données (et donc le nom du compte, y compris vers un fournisseur cloud) : `produced` la convertit en `ToolError`, et les messages d'erreur de `files.py` ne gardent que `strerror` (`test_a_disk_error_reaches_the_agent_without_the_data_folder_path`).
- low · second avis 4 · corrigé · `_is_junction` rendait toujours `False` sous Python 3.11 : repli sur `lstat().st_reparse_tag == IO_REPARSE_TAG_MOUNT_POINT`. Le confinement ne dépendait pas de lui (`resolve()` suit les jonctions, puis `_inside`), c'est une défense en profondeur.
- low · second avis 5 · corrigé · caractères invisibles (catégories Unicode `Cc`, `Cf`, `Zl`, `Zp` : bidi U+202E, largeur nulle) refusés dans les noms produits et les composants lus : un nom inversé trompait l'affichage du téléchargement.
- low · second avis 6 · rejeté · au délai, le fil (`asyncio.to_thread`) continue et peut écrire un fichier après un échec publié : limite inhérente à un fil Python, déjà consignée dans le report « plafond d'appels » ; le fichier reste dans le dossier de travail, sans `artifact_url`.
- low · second avis 7 · rejeté · un nom fourni écrase un fichier produit plus tôt : comportement de la v1 (`outputs/` écrasé), le fichier reste dans la racine confinée ; un horodatage ou un suffixe changerait le nom que l'agent a demandé. À revoir avec la 6.4 si l'écran garde des liens d'étapes anciennes.
- info · écart déclaré · pandas gardé pour `analyze_csv` : la justification tient, le texte de la v1 (`to_string`, `describe`, `value_counts`) n'est reproductible qu'avec pandas, déjà dépendance principale (installée par `uv sync --locked` en CI), importé dans la fonction.
- Complexité : 0 constat (aucune structure parcourue en entier à chaque événement ; la conversation d'un run est bornée par `max_turns` et le plafond d'appels par tour).
