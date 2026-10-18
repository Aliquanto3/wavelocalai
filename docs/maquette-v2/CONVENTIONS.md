# Maquette v2 : conventions pour les agents d'écran

Maquette HTML interactive du front définitif de wavelocalai v2 : modules ES natifs, sans Node, sans compilation, sans CDN. Ouvrir : double-clic sur `ouvrir.cmd` (ou `python serveur.py`). En `file://`, le navigateur bloque les modules : la page le dit. Contenus 100 % fictifs, textes en français, formats `fr-FR` (`js/core/format.js`), charte de `tokens.css` (aucune couleur en dur), aucun emoji.

## Ajouter un écran (aucun fichier partagé à modifier)

Les données simulées sont dans `donnees/` (pas `data/`, ignoré par le `.gitignore` du dépôt). La route existe déjà dans `donnees/routes.json` (`slug`, `path`, `title`, `module`, `screen`, `tab`, `example`). Remplacez les fichiers de votre écran `<s>` (= `screen`, ou `slug`) :

- `js/screens/<s>.js` : `export async function mount(host, ctx)` qui rend `host.replaceChildren(h1, …)` (un seul `h1`, puis `h2`/`h3` sans saut) et retourne la fonction de démontage ; `export const scenarios = [{id, label, run(ctx), routes?}]`.
- `css/screens/<s>.css` (jetons seulement), `i18n/screens/<s>.fr.json` (textes sous une clé propre à l'écran), `donnees/<s>*.json`, `donnees/flux/<s>-*.json`, `notes/<s>.md`.
- Une sous-route (`arene-resultat`, `fiche-modele`…) partage le module de son écran : lisez `ctx.params` (`run_id`, `tag`) et `ctx.route.slug`. Un scénario limité à certaines routes déclare `routes: ["arene-resultat"]`.
- Écran modèle à copier : `js/screens/chat-libre.js` (flux, erreurs, reprise) et `js/screens/accueil.js` (cartes en direct).

`ctx` : `route`, `params`, `host`, `store`, `sim`, `states`, `system`, `t`, `plural`, `data(path)` (JSON de `donnees/`, en cache : ne le modifiez pas, `structuredClone` si besoin), `tabs()` (onglets du module), `announce(texte)` (annonce polie), `navigate(path)`, `reset()` (état d'ouverture de la maquette puis remontage de l'écran), `remount()`.

L'écran reste en mémoire quand on navigue (nœud masqué) : observez `host.hidden` pour détacher puis rattacher un flux (voir chat-libre).

## Scénarios

Chaque scénario repart de `await ctx.reset()`, pose ses états globaux, puis attend un état stable avant de rendre la main (les tests passent axe juste après, à vitesse × 50). Couvrez tous les états d'EXPERIENCE.md et de 03 §3.8 qui concernent l'écran. États globaux pilotables : `window.__maquette.setGlobal(id, valeur)` (`ollama-arrete`, `cloud`, `connexion-perdue`, `serveur-redemarre`, `garde-fou-memoire`, `chargement-lent`, `aucun-modele-local`, `onglet-masque`, `theme`, `projection`, `vitesse`) ou les fonctions de `js/sim/systeme.js` et `setMaquette()` de `js/core/store.js`.

Parcours : `donnees/parcours.json` nomme déjà les étapes attendues (Flow 1, Flow 2, Flow 3, mission d'équipe, évaluation). Exportez les scénarios portant ces `id` sur la bonne route, ou corrigez uniquement l'entrée de votre parcours. Une étape sans scénario est sautée et signalée « à construire ».

## États communs (`ctx.states`, js/components/states.js)

`emptyState({title, text, action:{label, onClick|href}, level})` · `loading({lines, slowAfterMs, slowText})` · `runStatus(stage, secondes)` (`starting|loading|generating|stopping|ok|cancelled|error|interrupted`) · `errorBox(code, {detail, vars, alert, onAction(id)})` · `ramGuardBox(detail, onAction)` · `notice(texte, {tone: info|success|warning})` · `joinedNotice()` · `ollamaGuard()` (bandeau relié au store) · `cloudGuard({onAllowed, onUseLocal})` · `scoreValue(score, raison)` · `co2Value(co2)` · `confirmAction({title, consequence, confirmLabel, details}) → Promise<bool>` · `confirmEmail({to, subject, body, expiryMin = 10}) → Promise<bool>` (mention « Sans réponse dans 10 min… ») · `closeDialog()` (ferme le dialogue ouvert comme « Annuler »).

Composants : `wl-badge`, `wl-metric`, `wl-error` (`el.error = enveloppe` ; boutons du catalogue, événement `wl-error-action`), `wl-model-picker` (`purpose`, `multi`, `value(s)`, `selected`, `knows(tag)` ; poser `value(s)` par le code émet aussi `wl-model-change` si la liste change), `wl-run-status`, `wl-chat-thread`, `wl-confirm-dialog` (`ask(…)`, `close(valeur = false)`), `wl-skeleton`. Toutes les erreurs viennent de `donnees/erreurs.json` (`errorEnvelope(code, {detail, vars})` dans `js/core/errors.js`) : n'inventez pas de message ; un code manquant va dans vos notes. `detail.cause` choisit une variante du code (`pull_failed` : `not_found`, `ollama_down`, `interrupted`) ; `vars` remplit aussi le libellé et l'adresse des boutons (`run_not_found` : `what`, `new_label`, `new_href`).

`wl-run-status` : `driven` + `feed(envelope)` (le flux nomme l'étape : `model_loading`, `token`, `retrieval_step` → « Recherche des extraits… » selon `step`, `step` → « Réflexion… » / « Appel de l'outil … », `approval_required` → « En attente de votre validation », `lane_status: judging`, `judge_score`, `eval_metric` → « Notation des réponses… ») ; `setStage(stage, {tool, step, agent, label})` pour nommer l'étape soi-même (`label` remplace le texte, `agent` préfixe « Rédacteur : … ») ; pilotage sans enveloppe : `begin(ts)`, `markStopping()`, `finish(statut)`, `reset()`, `stage` ; attribut `no-stop`, propriété `onStop` (Arrêter et Échap appellent l'écran au lieu d'annuler le run) ; `cancel()`, `preview(stage)`. Le chronomètre suit la vitesse du simulateur.

## Composants communs (js/components/, styles dans css/components.css)

Importez-les plutôt que d'en recopier une version locale :

- `dataTable({caption, regionLabel, columns, rows, sort, onSort, sortLabel, className, id, rowClass, extra})` (`data-table.js`) : tableau triable au clavier. Colonnes `{key, label, value?, cell, header?, numeric?, className?}` ; une colonne avec `value` est triable. Sans `onSort` le tableau trie seul ; avec `onSort(key)` l'écran garde `sort = {key, dir}` et reconstruit (`sortRows(rows, columns, sort)` aide). `className` ajoute `<p>-table-wrap`, `<p>-table`, `<p>-sort` aux classes `wl-*` ; `id` pose `data-fid="sort:<id>:<key>"` ; `extra(row)` ajoute une ligne pleine largeur.
- `segments({label, options: [{value, label}], value, onChange, className})` (`segments.js`) : radiogroup, flèches, icône `check` sur le choix ; `seg.root`, `seg.select(v, {focus, silent})`, `seg.value`.
- `bubbleMatrix({title, desc, points: [{name, x, y, mg}], x: {label, log?, min?, max?, ticks?}, y: {label, max, ticks}, size: {title, format, unmeasurable, note}, seeTable: {label, onClick}, missing, className})` et `svgNode(tag, attrs, text)` (`charts.js`) : matrice note × débit × CO₂ accessible (`role="img"`, titre, description, légende HTML, lien vers le tableau).
- `createStepTrace({label, showAgent, agentName, toolLabel, openFile})` et `stepIcon(type)` (`step-trace.js`) : trace d'étapes d'un agent (`apply(step)`, `waitOnLast()`, `finish(statut)`, `expand(id)`, `entries()`, `clear()`).
- `createSourcePanel({prefix, autoOpen})` (`source-panel.js`) : panneau de sources (`setSources`, `highlight(n)`, `open(n)`, `onLink`) ; `helpToggle(libellé, texte)` (`help-toggle.js`) : aide en bouton.
- Icônes : `icon(nom)` de `js/core/dom.js`, sprite `icons.svg` (37 symboles, liste et provenance dans `icons.LICENSE.txt`). Pas de tracé SVG local : un symbole manquant s'ajoute au sprite.

Restés propres à un écran (un seul utilisateur) : barre de progression d'octets (Modèles), schéma d'équipe (Équipe d'agents), histogramme de session (Sobriété), tableau des scores avec aides d'en-tête (Évaluation), bandeau de comparaison « N sur M » (Arène).

Catalogue visuel de tous les états : `#/maquette/etats`.

## Simulateur (js/sim/sim.js)

`const run = sim.play(scriptId, handlers, {vars, kind, origin, module, speed, error, errorAfter})` rejoue `donnees/flux/<scriptId>.json` avec l'enveloppe exacte d'AD-6 `{seq, run_id, type, ts, data}`. `handlers` : `{<type>: (data, envelope) => …, "*": …}`. Méthodes : `run.stop()`, `run.fail(code, detail)`, `run.cut(ms)`, `run.attach(handlers, {after})`, `run.detach()`, `run.resume(events)`, `run.paused`, `run.done`, `run.lastSeq`. Un run qui se termine pendant une coupure livre ses derniers événements au retour de la connexion. `scriptId` peut être un script construit à l'exécution, `{kind, events}` (équipe composée, lot de fichiers, modèles évalués) ; `vars` reste l'entrée de la commande, relue par un autre onglet (409 rejoint). Avant de lancer : `sim.precheck({origin, kind, model})` rend l'enveloppe qu'un `POST` refuserait (`run_busy` à rejoindre, `ollama_down`, `ram_guard` sauf pour un `pull`, `cloud_not_allowed`, `cloud_key_missing`) ou `null`. Aussi `sim.prepare(events, vars)`, `sim.get(id)`, `sim.active(kind)`, `sim.cancel(id)`, `sim.restartServer()`.

Script : `events: [{wait, type, data}]` ; `{wait, tokens: {lane, channel, text, tps}}` est découpé en `token` de 50 ms ; `slow_wait` remplace `wait` en premier chargement lent ; `"{{nom}}"` vaut `vars.nom` (type gardé) ; `"when": "{{nom}}"` omet l'événement si faux ; `{pause: true}` suspend le run jusqu'à `run.resume(sim.prepare(suite, vars))` (attente d'une décision, validation d'email). Noms et données des événements : ceux de `contrat-api.md` (`token`, `metrics`, `lane_status`, `judge_score`, `sources`, `step`, `approval_required`, `eval_metric`, `ingest_progress`, `pull_progress`, `run_ended`…), `lane` toujours présent là où la spine l'exige, `co2` au format d'AD-10. Modèles simulés : `js/sim/modeles.js` (`listModels`, `modelDefaults`, `findModel`) ; ce que l'écran Modèles change (`installModel`, `deleteModel`, `unloadModels`, `localModelsState`) vit dans le store (`maquette.localModels`) et se voit partout (sélecteur, Accueil, flux système).

## Notes par écran (obligatoire)

Chaque agent écrit `notes/<s>.md` : (a) états couverts (id des scénarios) ; (b) écarts entre la maquette et epics.md, DESIGN.md ou EXPERIENCE.md, sans les trancher ; (c) questions pour Anaël : choix visuel ou d'interaction non fixé par le contrat, 2 ou 3 options, une recommandation.

## Vérifier

`C:\Users\Utilisateur\Documents\GitHub\wavelocalai\.venv\Scripts\python.exe -m pytest docs/maquette-v2/tests -q --tb=short` (Edge via `WAVELOCALAI_E2E_CHROMIUM`, sinon Edge à son emplacement habituel). Les tests lisent `donnees/routes.json` et les `scenarios` de chaque module : axe sans exclusion (clair, sombre, projection), 320 à 1 440 px sans défilement horizontal, clavier, aucune erreur ni avertissement de console, aucune requête hors de 127.0.0.1.
