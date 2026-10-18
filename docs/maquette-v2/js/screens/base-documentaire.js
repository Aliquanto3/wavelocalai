// Base documentaire, `#/documents/base` (UX-DR12, UX-DR13, UX-DR16, UX-DR17, UX-DR22, stories 4.1 à 4.3) :
// écran de l'Assistant documentaire, à l'état livré. Remplace le dialogue « Gérer la base » de la v1.
//
// - La zone de dépôt « Déposez des fichiers ici ou Choisir des fichiers · PDF, TXT, MD, DOCX » est
//   visible tout de suite, sans aucun appel au serveur ; la liste des documents a son squelette.
// - Chaque fichier a sa ligne : envoi du navigateur (« Envoi 62 % »), puis `ingest_progress`
//   (« Extraction · Découpage · Vectorisation 18/40 extraits »), Annuler, échec par fichier avec
//   « Détails techniques » (`ingest_failed`), compteur inchangé pour un fichier en échec.
// - Succès : « N extraits ajoutés depuis M documents » ; documents `indexing` jamais présentés comme prêts.
// - Tableau des documents (nom, extraits, date, modèle de représentation, statut), tri au clavier,
//   filtre, Supprimer ; « Vider la base documentaire » passe par `wl-confirm-dialog` et chiffre la
//   conséquence ; réglages (représentation, découpe, extraits, stratégie), changer de modèle de
//   représentation oblige à vider.
// - Quitter l'écran pendant un import puis revenir reprend la progression après le dernier `seq`.
//
// La maquette ne lit jamais un fichier choisi : seuls son nom et sa taille servent à simuler l'import.
// Contournement local : `wl-data-table` n'existe pas encore dans les composants communs, le tableau
// est construit ici (tri au clavier par boutons d'en-tête, `aria-sort`).

import { element } from "../core/dom.js";
import { errorEnvelope } from "../core/errors.js";
import { formatInteger, formatPercent } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";
import {
  baseCounts,
  chunksLabel,
  documentsLabel,
  embeddingName,
  ensureBase,
  formatDateTime,
  getBase,
  pause,
  prepare,
  setBasePreset,
  speedOf,
  subscribeBase,
  updateBase,
  waitUntil,
} from "./documents-commun.js";

let counter = 0;
let newDocuments = 0;
let view = null; // l'instance montée, pour les scénarios

const ALLOWED = [".pdf", ".txt", ".md", ".docx"];
const FINAL = new Set(["ready", "failed", "duplicate", "cancelled", "interrupted"]);
const STEP_ORDER = ["extract", "split", "embed"];

// Un fichier déposé : nom et taille seulement ; pages, extraits et issue sont simulés.
function describeFile(file, base) {
  const out = { ...file };
  const ext = (/\.[^.]+$/.exec(out.name)?.[0] ?? "").toLowerCase();
  out.size_kb ??= 100;
  out.pages ??= Math.max(1, Math.round(out.size_kb / 45));
  out.chunks ??= Math.min(80, Math.max(3, Math.round(out.size_kb / 12)));
  if (!out.fail && !ALLOWED.includes(ext)) {
    out.fail = {
      reason: `le format « ${ext || "sans extension"} » n'est pas pris en charge`,
      technical: `ValueError: extension refusée : ${ext || "(aucune)"} (autorisées : ${ALLOWED.join(", ")})`,
    };
  }
  if (!out.fail && out.duplicate === undefined) {
    out.duplicate = base.documents.some((doc) => doc.status === "ready" && doc.name.toLowerCase() === out.name.toLowerCase());
  }
  return out;
}

// Les événements d'un lot, au format des scripts du simulateur ({wait, slow_wait?, type, data}).
function buildEvents(files, { loading, embedding }) {
  const events = [{ wait: 0, type: "run_started", data: { kind: "ingest", models: [embedding], params: { files: files.map((file) => file.name) } } }];
  if (loading) {
    events.push({ wait: 150, type: "model_loading", data: { tag: embedding } });
    events.push({ wait: 1800, slow_wait: 9000, type: "model_loaded", data: { tag: embedding, duration_s: 1.8 } });
  }
  for (const file of files) {
    const progress = (phase, done, total, wait, extra = {}) =>
      events.push({ wait, type: "ingest_progress", data: { file: file.name, phase, done, total, ...extra } });
    if (file.duplicate) {
      progress("extract", 0, 0, 300, { skipped: "duplicate" });
    } else if (file.fail) {
      const error = errorEnvelope("ingest_failed", { detail: { file: file.name, reason: file.fail.reason, technical: file.fail.technical } });
      progress("extract", 0, file.pages, 400, { error });
    } else {
      progress("extract", Math.ceil(file.pages / 2), file.pages, 350);
      progress("extract", file.pages, file.pages, 350);
      progress("split", file.chunks, file.chunks, 300);
      for (const share of [0.4, 0.75, 1]) progress("embed", Math.round(file.chunks * share), file.chunks, 450);
    }
  }
  events.push({ wait: 200, type: "run_ended", data: { status: "ok", error: null } });
  return events;
}

// Ce que « le serveur » écrit dans la base, que l'écran soit visible ou non (le flux de l'écran, lui,
// se détache quand l'écran est masqué).
function serverEffects(files) {
  const ids = new Map();
  return {
    ingest_progress(data) {
      const file = files.find((candidate) => candidate.name === data.file);
      if (!file || data.error || data.skipped) return;
      if (!ids.has(file.name)) {
        const id = `doc-new-${++newDocuments}`;
        ids.set(file.name, id);
        updateBase((base) => {
          base.documents.push({ id, name: file.name, chunks: 0, pages: file.pages, added_at: new Date().toISOString(), status: "indexing", embedding: base.settings.embedding });
        });
      }
      if (data.phase === "embed") {
        updateBase((base) => {
          const doc = base.documents.find((candidate) => candidate.id === ids.get(file.name));
          doc.chunks = data.done;
          if (data.done >= data.total) doc.status = "ready";
        });
      }
    },
    run_ended(data) {
      if (data.status === "ok") return;
      // Annulé ou interrompu : les extraits du document en cours sont retirés, les prêts restent.
      updateBase((base) => {
        base.documents = base.documents.filter((doc) => !(doc.status === "indexing" && [...ids.values()].includes(doc.id)));
      });
    },
  };
}

export async function mount(host, ctx) {
  await prepare();
  const uid = `base-${++counter}`;
  const [data] = await Promise.all([ctx.data("base-documentaire.json"), ensureBase()]);

  // --- Zone de dépôt (aucun appel au serveur pour l'afficher) -----------------------------
  const guard = ctx.states.ollamaGuard();
  const input = element("input");
  input.type = "file";
  input.multiple = true;
  input.accept = ALLOWED.join(",");
  input.hidden = true;
  input.tabIndex = -1;
  const choose = element("button", "btn btn-primary", t("baseDoc.drop_choose"));
  choose.type = "button";
  const dropText = element("p", "docs-drop-text");
  dropText.append(document.createTextNode(`${t("baseDoc.drop_text")} `), choose);
  const dropFormats = element("p", "help docs-drop-formats", t("baseDoc.drop_formats"));
  const dropzone = element("div", "docs-dropzone");
  dropzone.append(dropText, dropFormats, input);
  const dropTitle = element("h2", "", t("baseDoc.drop_title"));
  dropTitle.id = `${uid}-drop`;
  const drop = element("section", "docs-drop");
  drop.setAttribute("aria-labelledby", dropTitle.id);
  drop.append(dropTitle, dropzone);

  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const notices = element("div", "docs-base-notices");

  // --- Imports en cours --------------------------------------------------------------------
  const importsTitle = element("h2", "", t("baseDoc.imports_title"));
  importsTitle.id = `${uid}-imports`;
  const embedLoading = element("p", "help docs-embed-loading", t("baseDoc.embed_loading"));
  embedLoading.setAttribute("role", "status");
  embedLoading.hidden = true;
  const importList = element("ul", "docs-imports");
  importList.setAttribute("aria-label", t("baseDoc.imports_label"));
  const imports = element("section", "docs-imports-section");
  imports.setAttribute("aria-labelledby", importsTitle.id);
  imports.hidden = true;
  imports.append(importsTitle, embedLoading, importList);

  // --- Documents indexés -------------------------------------------------------------------
  const libraryTitle = element("h2", "docs-library-title");
  libraryTitle.id = `${uid}-library`;
  const filter = element("input", "docs-filter");
  filter.type = "search";
  filter.id = `${uid}-filter`;
  const filterLabel = element("label", "docs-field-label", t("baseDoc.filter"));
  filterLabel.htmlFor = filter.id;
  const filterField = element("div", "docs-filter-field");
  filterField.append(filterLabel, filter);
  const clearButton = element("button", "btn docs-clear", t("baseDoc.clear"));
  clearButton.type = "button";
  const clearReason = element("p", "help docs-clear-reason", t("baseDoc.busy_reason"));
  clearReason.id = `${uid}-clear-reason`;
  const clearField = element("div", "docs-clear-field");
  clearField.append(clearButton, clearReason);
  const toolbar = element("div", "docs-toolbar");
  toolbar.append(filterField, clearField);
  const liveCount = element("p", "help docs-count");
  liveCount.setAttribute("role", "status");
  const libraryBody = element("div", "docs-library-body");
  const library = element("section", "docs-library");
  library.setAttribute("aria-labelledby", libraryTitle.id);
  library.append(libraryTitle, toolbar, liveCount, libraryBody);

  // --- Réglages ----------------------------------------------------------------------------
  const embeddingSelect = element("select", "docs-select");
  embeddingSelect.id = `${uid}-embedding`;
  const embeddingLabel = element("label", "docs-field-label", t("baseDoc.embedding"));
  embeddingLabel.htmlFor = embeddingSelect.id;
  const embeddingHelp = element("p", "help", t("baseDoc.embedding_help"));
  embeddingHelp.id = `${uid}-embedding-help`;
  embeddingSelect.setAttribute("aria-describedby", embeddingHelp.id);
  const chunkSize = element("input", "docs-number");
  Object.assign(chunkSize, { type: "number", min: "200", max: "2000", step: "50", id: `${uid}-chunk` });
  const chunkLabel = element("label", "docs-field-label", t("baseDoc.chunk_size"));
  chunkLabel.htmlFor = chunkSize.id;
  const chunkHelp = element("p", "help", t("baseDoc.chunk_size_help"));
  chunkHelp.id = `${uid}-chunk-help`;
  chunkSize.setAttribute("aria-describedby", chunkHelp.id);
  const topK = element("input", "docs-number");
  Object.assign(topK, { type: "number", min: "1", max: "5", step: "1", id: `${uid}-topk` });
  const topKLabel = element("label", "docs-field-label", t("baseDoc.top_k"));
  topKLabel.htmlFor = topK.id;
  const topKHelp = element("p", "help", t("baseDoc.top_k_help"));
  topKHelp.id = `${uid}-topk-help`;
  topK.setAttribute("aria-describedby", topKHelp.id);
  const strategy = element("select", "docs-select");
  strategy.id = `${uid}-strategy`;
  for (const key of ["naive", "hyde", "self_rag"]) {
    const option = element("option", "", t(`baseDoc.strategy_${key}`));
    option.value = key;
    strategy.append(option);
  }
  const strategyLabel = element("label", "docs-field-label", t("baseDoc.strategy"));
  strategyLabel.htmlFor = strategy.id;
  const rerankLine = element("p", "docs-rerank");
  const rerankLink = element("a", "", t("baseDoc.rerank_link"));
  rerankLink.href = "#/modeles";
  const save = element("button", "btn btn-primary", t("baseDoc.save"));
  save.type = "submit";
  const settingsBusy = element("p", "help", t("baseDoc.settings_busy"));
  const fields = element("fieldset", "docs-settings-fields");
  fields.append(
    ...[
      [embeddingLabel, embeddingSelect, embeddingHelp],
      [chunkLabel, chunkSize, chunkHelp],
      [topKLabel, topK, topKHelp],
      [strategyLabel, strategy],
    ].map((parts) => {
      const field = element("div", "docs-field");
      field.append(...parts);
      return field;
    }),
    rerankLine,
    rerankLink,
  );
  const legend = element("legend", "sr-only", t("baseDoc.settings_legend"));
  fields.prepend(legend);
  const settingsForm = element("form", "docs-settings-form");
  settingsForm.append(fields, settingsBusy, save);
  const settingsSummary = element("summary");
  const settings = element("details", "docs-settings");
  settings.append(settingsSummary, settingsForm);
  const settingsNotices = element("div", "docs-base-notices");

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("baseDoc.lead")),
    guard,
    drop,
    error,
    notices,
    imports,
    library,
    settings,
    settingsNotices,
  );

  // --- État ------------------------------------------------------------------------------
  let batch = null; // { rows, run, attachment, lastSeq, timer, done }
  let listLoading = true;
  let frozenList = false;
  let embeddingLoaded = false;
  let confirming = false;
  let sort = { key: "added_at", dir: "desc" };
  let wasHidden = host.hidden;
  const rows = [];

  const ingestActive = () => store.get().runsActive.some((run) => run.kind === "ingest");

  function say(text, tone = "info", target = notices) {
    target.replaceChildren(ctx.states.notice(text, { tone }));
  }

  // --- Lignes d'import ---------------------------------------------------------------------
  function stepsOf(row) {
    const upload = t("baseDoc.upload", { percent: formatPercent(row.percent) });
    const extract = t("baseDoc.step_extract");
    const split = t("baseDoc.step_split");
    const embed = t("baseDoc.step_embed", { done: formatInteger(row.done), total: formatInteger(row.total) });
    switch (row.state) {
      case "uploading": return [upload];
      case "waiting": return [upload, t("baseDoc.waiting")];
      case "extract": return [upload, extract];
      case "split": return [upload, extract, split];
      case "embed": return [upload, extract, split, embed];
      case "ready": return [t("baseDoc.ready", { chunks: chunksLabel(row.chunks) })];
      case "duplicate": return [t("baseDoc.duplicate")];
      case "cancelled": return [t(row.started ? "baseDoc.cancelled" : "baseDoc.cancelled_waiting")];
      case "interrupted": return [t("baseDoc.interrupted")];
      default: return [];
    }
  }

  function renderRow(row) {
    const hadFocus = row.node?.contains(document.activeElement);
    const node = row.node ?? element("li", "docs-import");
    row.node = node;
    node.dataset.state = row.state;
    const head = element("div", "docs-import-head");
    const steps = element("span", "docs-import-steps");
    const parts = stepsOf(row);
    parts.forEach((part, index) => {
      const last = index === parts.length - 1;
      steps.append(element(last ? "strong" : "span", "", part));
      if (!last) steps.append(document.createTextNode(" · "));
    });
    head.append(element("span", "docs-import-name", row.file.name), steps);
    const children = [head];
    if (!FINAL.has(row.state)) {
      const cancel = element("button", "btn docs-import-cancel", t("baseDoc.cancel"));
      cancel.type = "button";
      cancel.setAttribute("aria-label", t("baseDoc.cancel_for", { name: row.file.name }));
      cancel.addEventListener("click", () => cancelRow(row));
      head.append(cancel);
      const bar = element("progress", "docs-progress");
      bar.setAttribute("aria-label", t("baseDoc.progress_for", { name: row.file.name }));
      if (row.state === "uploading") Object.assign(bar, { max: 100, value: row.percent });
      else if (row.state === "embed") Object.assign(bar, { max: row.total, value: row.done });
      else if (row.state === "waiting") Object.assign(bar, { max: 100, value: 100 });
      children.push(bar);
    }
    if (row.state === "failed" && row.error) {
      const box = document.createElement("wl-error");
      box.error = row.error;
      box.addEventListener("wl-error-action", (event) => {
        if (event.detail.id === "retry") retryRow(row);
      });
      children.push(box);
    }
    node.replaceChildren(...children);
    if (hadFocus) node.querySelector(".docs-import-cancel, .wl-error-buttons button")?.focus();
  }

  function renderRows() {
    imports.hidden = rows.length === 0;
    importList.replaceChildren(...rows.map((row) => row.node ?? (renderRow(row), row.node)));
  }

  function setRow(row, patch) {
    Object.assign(row, patch);
    renderRow(row);
  }

  // --- Flux d'un lot -----------------------------------------------------------------------
  function rowFor(name) {
    return batch?.rows.find((row) => row.file.name === name);
  }

  const handlers = {
    "*": (_data, envelope) => {
      if (batch) batch.lastSeq = envelope.seq;
    },
    model_loading: () => {
      embedLoading.hidden = false;
    },
    model_loaded: () => {
      embedLoading.hidden = true;
      embeddingLoaded = true;
    },
    ingest_progress: (payload) => {
      const row = rowFor(payload.file);
      if (!row) return;
      if (payload.error) return setRow(row, { state: "failed", error: payload.error, started: true });
      if (payload.skipped) return setRow(row, { state: "duplicate", started: true });
      const ready = payload.phase === "embed" && payload.done >= payload.total;
      setRow(row, {
        state: ready ? "ready" : payload.phase,
        done: payload.done,
        total: payload.total,
        chunks: ready ? payload.total : row.chunks,
        percent: 100,
        started: true,
      });
    },
    run_ended: (payload) => finishBatch(payload),
  };

  function finishBatch(payload) {
    if (!batch) return;
    embedLoading.hidden = true;
    for (const row of batch.rows) {
      if (FINAL.has(row.state)) continue;
      setRow(row, { state: payload.status === "interrupted" ? "interrupted" : "cancelled" });
    }
    const ready = batch.rows.filter((row) => row.state === "ready");
    if (payload.status === "ok" && ready.length) {
      const added = ready.reduce((sum, row) => sum + row.chunks, 0);
      const text = `${plural("baseDoc.added", added, { count: formatInteger(added) })} ${plural("baseDoc.from", ready.length, { count: formatInteger(ready.length) })}.`;
      say(text, "success");
    }
    if (payload.error) error.error = payload.error;
    batch.attachment?.close();
    batch.done = true;
    render();
  }

  function follow(simRun, files, { after = 0 } = {}) {
    batch.run = simRun;
    batch.lastSeq = after;
    batch.attachment = simRun.attach(handlers, { after });
    render();
  }

  // Envoi du navigateur (simulé) : un pourcentage par fichier, puis le run `ingest` démarre.
  function startUpload(options) {
    const tick = () => {
      const live = batch.rows.filter((row) => row.state === "uploading");
      for (const row of live) {
        const duration = Math.min(2500, Math.max(700, row.file.size_kb * 3)) / speedOf();
        row.percent = Math.min(options.holdAt ?? 100, row.percent + (100 * 100) / duration);
        renderRow(row);
      }
      if (options.holdAt !== undefined && live.every((row) => row.percent >= options.holdAt)) return clearInterval(batch.timer);
      if (live.every((row) => row.percent >= 100)) {
        clearInterval(batch.timer);
        startRun(options);
      }
    };
    batch.timer = setInterval(tick, 100);
  }

  function startRun(options) {
    const files = batch.rows.filter((row) => row.state === "uploading").map((row) => row.file);
    for (const row of batch.rows) if (row.state === "uploading") setRow(row, { state: "waiting", percent: 100 });
    if (!files.length) {
      batch.done = true;
      return render();
    }
    const base = getBase();
    const events = buildEvents(files, { loading: !embeddingLoaded, embedding: base.settings.embedding });
    // Lot construit à l'exécution (nombre de fichiers libre) : le simulateur le rejoue tel quel.
    const simRun = sim.play({ kind: "ingest", events }, serverEffects(files), {
      vars: { files }, // entrée de la commande (409 rejoint)
      kind: "ingest",
      origin: "local",
      module: "rag",
      speed: options.speed,
    });
    follow(simRun, files);
  }

  function cancelRow(row) {
    if (row.state === "uploading" && !batch.run) {
      setRow(row, { state: "cancelled", started: false });
      if (batch.rows.every((candidate) => FINAL.has(candidate.state))) {
        clearInterval(batch.timer);
        batch.done = true;
        render();
      }
      return;
    }
    // Un seul run pour tout le lot : annuler une ligne arrête les fichiers qui restent.
    batch?.run?.stop();
  }

  function retryRow(row) {
    rows.splice(rows.indexOf(row), 1);
    error.error = null;
    importFiles([{ ...row.file }]);
  }

  // --- Import ------------------------------------------------------------------------------
  async function importFiles(files, options = {}) {
    error.error = null;
    notices.replaceChildren();
    const base = getBase();
    if (batch && !batch.done) {
      error.error = { ...errorEnvelope("run_busy", { detail: { run_id: batch.run?.id ?? "" } }) };
      return null;
    }
    const refused = sim.precheck({ origin: "local", kind: "ingest" });
    if (refused?.code === "ram_guard") {
      const small = base.embeddingModels.find((model) => model.tag !== base.settings.embedding);
      const current = base.embeddingModels.find((model) => model.tag === base.settings.embedding);
      error.error = errorEnvelope("ram_guard", {
        detail: { needed_gb: current.needed_gb, free_gb: 0.9, suggested_model: small?.tag ?? current.tag, technical: "hardware.fits : besoin estimé 1,4 Go (poids 1,2 Go + contexte 0,2 Go), libre 0,9 Go" },
        vars: { suggested: small?.name ?? current.name },
      });
      error.error.action = t("baseDoc.ram_action", { suggested: small?.name ?? current.name });
      return null;
    }
    if (refused) {
      error.error = refused;
      return null;
    }
    const described = files.map((file) => describeFile(file, base));
    rows.length = 0;
    for (const file of described) rows.push({ file, state: "uploading", percent: options.startAt ?? 0, done: 0, total: 0, chunks: file.chunks, started: false });
    batch = { rows: [...rows], run: null, attachment: null, lastSeq: 0, timer: null, done: false };
    renderRows();
    startUpload(options);
    return batch;
  }

  function pickFiles(list) {
    const files = [...list].map((file) => ({ name: file.name, size_kb: Math.max(1, Math.round(file.size / 1024)) }));
    if (files.length) importFiles(files);
  }

  choose.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    pickFiles(input.files);
    input.value = "";
  });
  for (const type of ["dragenter", "dragover"]) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-active");
    });
  }
  for (const type of ["dragleave", "drop"]) dropzone.addEventListener(type, () => dropzone.classList.remove("is-active"));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    pickFiles(event.dataTransfer?.files ?? []);
  });

  // --- Tableau des documents ---------------------------------------------------------------
  const COLUMNS = [
    { key: "name", label: "col_name", sortable: true },
    { key: "chunks", label: "col_chunks", sortable: true, numeric: true },
    { key: "added_at", label: "col_date", sortable: true },
    { key: "embedding", label: "col_embedding" },
    { key: "status", label: "col_status" },
    { key: "actions", label: "col_actions" },
  ];

  function sortedDocuments(documents) {
    const factor = sort.dir === "asc" ? 1 : -1;
    return [...documents].sort((a, b) => {
      const left = a[sort.key];
      const right = b[sort.key];
      const order = typeof left === "number" ? left - right : String(left).localeCompare(String(right), "fr-FR", { numeric: true });
      return order * factor;
    });
  }

  function renderTable(base) {
    const query = filter.value.trim().toLocaleLowerCase("fr-FR");
    const shown = sortedDocuments(base.documents.filter((doc) => doc.name.toLocaleLowerCase("fr-FR").includes(query)));
    liveCount.textContent = query ? t("baseDoc.filter_count", { shown: formatInteger(shown.length), total: formatInteger(base.documents.length) }) : "";
    if (!shown.length) {
      const none = element("p", "docs-filter-none", t("baseDoc.filter_none", { query: filter.value.trim() }));
      return none;
    }
    const table = element("table", "docs-table");
    const caption = element("caption", "sr-only", t("baseDoc.library_label"));
    const head = element("tr");
    for (const column of COLUMNS) {
      const cell = element("th", `docs-col-${column.key}${column.numeric ? " is-numeric" : ""}`);
      cell.scope = "col";
      if (column.sortable) {
        const active = sort.key === column.key;
        cell.setAttribute("aria-sort", active ? (sort.dir === "asc" ? "ascending" : "descending") : "none");
        const button = element("button", "docs-sort", t(`baseDoc.${column.label}`));
        button.type = "button";
        button.dataset.key = column.key;
        button.setAttribute("aria-label", t("baseDoc.sort_by", { column: t(`baseDoc.${column.label}`) }));
        if (active) button.dataset.dir = sort.dir;
        button.addEventListener("click", () => {
          sort = { key: column.key, dir: sort.key === column.key && sort.dir === "asc" ? "desc" : "asc" };
          renderLibrary();
          libraryBody.querySelector(`.docs-sort[data-key="${column.key}"]`)?.focus();
          liveCount.textContent = t("baseDoc.sorted", { column: t(`baseDoc.${column.label}`), order: t(`baseDoc.${sort.dir}`) });
        });
        cell.append(button);
      } else {
        cell.textContent = t(`baseDoc.${column.label}`);
      }
      head.append(cell);
    }
    const thead = element("thead");
    thead.append(head);
    const tbody = element("tbody");
    for (const doc of shown) {
      const row = element("tr", "docs-row");
      const name = element("th", "docs-col-name", doc.name);
      name.scope = "row";
      const cells = [
        name,
        element("td", "docs-col-chunks is-numeric", formatInteger(doc.chunks)),
        element("td", "docs-col-added_at", formatDateTime(doc.added_at)),
        element("td", "docs-col-embedding", embeddingName(base, doc.embedding)),
        element("td", "docs-col-status", t(`baseDoc.status_${doc.status}`)),
      ];
      const action = element("td", "docs-col-actions");
      const remove = element("button", "btn docs-delete", t("baseDoc.delete"));
      remove.type = "button";
      remove.dataset.id = doc.id;
      remove.setAttribute("aria-label", t("baseDoc.delete_for", { name: doc.name }));
      remove.disabled = ingestActive();
      remove.addEventListener("click", () => deleteDocument(doc.id));
      action.append(remove);
      row.append(...cells, action);
      tbody.append(row);
    }
    table.append(caption, thead, tbody);
    const wrap = element("div", "docs-table-wrap");
    wrap.setAttribute("role", "region");
    wrap.setAttribute("aria-label", t("baseDoc.library_label"));
    wrap.tabIndex = 0;
    wrap.append(table);
    return wrap;
  }

  function renderLibrary() {
    const base = getBase();
    const counts = baseCounts(base);
    libraryTitle.textContent = t("baseDoc.library_title", { count: formatInteger(counts.documents) });
    const busy = ingestActive() || (batch && !batch.done);
    const hasDocs = base.documents.length > 0;
    clearButton.hidden = !hasDocs;
    clearButton.disabled = busy;
    clearReason.hidden = !(hasDocs && busy);
    if (hasDocs && busy) clearButton.setAttribute("aria-describedby", clearReason.id);
    else clearButton.removeAttribute("aria-describedby");
    filterField.hidden = !hasDocs;
    libraryBody.setAttribute("aria-busy", String(listLoading));
    if (listLoading) {
      libraryBody.replaceChildren(ctx.states.loading({ lines: 5, slowAfterMs: 2500, slowText: t("states.slow_loading") }));
      liveCount.textContent = "";
    } else if (!hasDocs) {
      const action = { label: t("baseDoc.empty_action"), onClick: () => input.click() };
      libraryBody.replaceChildren(
        ctx.states.emptyState({ title: t("baseDoc.empty_title"), text: t("baseDoc.empty_text"), action, level: 3, iconName: "description" }),
      );
      liveCount.textContent = "";
    } else {
      libraryBody.replaceChildren(renderTable(base));
    }
  }

  async function deleteDocument(id) {
    const doc = getBase().documents.find((candidate) => candidate.id === id);
    if (!doc || ingestActive()) return;
    updateBase((base) => {
      base.documents = base.documents.filter((candidate) => candidate.id !== id);
    });
    say(t("baseDoc.deleted", { name: doc.name, chunks: chunksLabel(doc.chunks) }), "success");
    (libraryBody.querySelector(".docs-delete") ?? choose).focus();
  }

  // « Vider la base documentaire » : jamais au premier clic, la conséquence est chiffrée (UX-DR12).
  async function clearBase() {
    const base = getBase();
    const chunks = base.documents.reduce((sum, doc) => sum + doc.chunks, 0);
    const vars = { chunks: chunksLabel(chunks), documents: documentsLabel(base.documents.length) };
    confirming = true;
    const confirmed = await ctx.states.confirmAction({
      title: t("baseDoc.clear_title"),
      consequence: t("baseDoc.clear_consequence", vars),
      confirmLabel: t("baseDoc.clear"),
    });
    confirming = false;
    if (!confirmed) {
      say(t("baseDoc.clear_cancelled"), "info");
      return false;
    }
    updateBase((next) => {
      next.documents = [];
    });
    settingsNotices.replaceChildren();
    say(t("baseDoc.cleared", vars), "success");
    choose.focus();
    return true;
  }

  filter.addEventListener("input", renderLibrary);
  clearButton.addEventListener("click", clearBase);

  // --- Réglages ----------------------------------------------------------------------------
  function renderSettings() {
    const base = getBase();
    const { embedding, chunk_size: size, top_k: k, strategy: chosen } = base.settings;
    settingsSummary.textContent = t("baseDoc.settings_summary", {
      embedding: embeddingName(base, embedding),
      rerank: t(base.reranker.available ? "baseDoc.rerank_on" : "baseDoc.rerank_off"),
      top_k: chunksLabel(k),
    });
    if (!embeddingSelect.options.length) {
      for (const model of base.embeddingModels) {
        const option = element("option", "", `${model.name} (${model.tag})`);
        option.value = model.tag;
        embeddingSelect.append(option);
      }
    }
    if (!settings.dataset.touched) {
      embeddingSelect.value = embedding;
      chunkSize.value = String(size);
      topK.value = String(k);
      strategy.value = chosen;
    }
    rerankLine.textContent = base.reranker.available
      ? t("baseDoc.rerank_line_on", { model: base.reranker.model })
      : t("baseDoc.rerank_line_off", { reason: base.reranker.reason });
    rerankLink.hidden = base.reranker.available;
    const busy = ingestActive() || (batch && !batch.done);
    fields.disabled = Boolean(busy);
    save.disabled = Boolean(busy);
    settingsBusy.hidden = !busy;
  }

  for (const field of [embeddingSelect, chunkSize, topK, strategy]) field.addEventListener("input", () => (settings.dataset.touched = "1"));

  settingsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const base = getBase();
    const next = {
      embedding: embeddingSelect.value,
      chunk_size: Math.min(2000, Math.max(200, Number(chunkSize.value) || 800)),
      top_k: Math.min(5, Math.max(1, Math.round(Number(topK.value) || 3))),
      strategy: strategy.value,
    };
    // Changer de modèle de représentation avec une base non vide : « Vider » d'abord (story 4.3).
    if (next.embedding !== base.settings.embedding && base.documents.length) {
      const total = base.documents.reduce((sum, doc) => sum + doc.chunks, 0);
      const message = ctx.states.notice(t("baseDoc.embed_conflict", { chunks: chunksLabel(total) }), { tone: "warning" });
      const button = element("button", "btn", t("baseDoc.clear"));
      button.type = "button";
      button.addEventListener("click", clearBase);
      message.append(button);
      settingsNotices.replaceChildren(message);
      embeddingSelect.value = base.settings.embedding;
      return;
    }
    updateBase((draft) => {
      Object.assign(draft.settings, next);
    });
    delete settings.dataset.touched;
    if (next.embedding !== base.settings.embedding) say(t("baseDoc.embed_changed", { name: embeddingName(getBase(), next.embedding) }), "success", settingsNotices);
    else say(t("baseDoc.saved"), "success", settingsNotices);
  });

  // --- Erreurs de commande : boutons d'action ---------------------------------------------
  error.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "retry") {
      error.error = null;
      const lastFiles = rows.map((row) => ({ ...row.file }));
      if (lastFiles.length) importFiles(lastFiles);
    } else if (id === "join") {
      const other = sim.active("ingest");
      error.error = null;
      if (other && batch?.run !== other) {
        const files = (other.options.vars?.files ?? []).map((file) => describeFile(file, getBase()));
        rows.length = 0;
        for (const file of files) rows.push({ file, state: "waiting", percent: 100, done: 0, total: 0, chunks: file.chunks, started: false });
        batch = { rows: [...rows], run: null, attachment: null, lastSeq: 0, timer: null, done: false };
        renderRows();
        follow(other, files);
      }
      say(t("baseDoc.joined"), "info");
    } else if (id === "smaller") {
      const base = getBase();
      const small = base.embeddingModels.find((model) => model.tag === error.error?.detail?.suggested_model);
      setMaquette({ ramGuard: false });
      error.error = null;
      if (small && !base.documents.length) {
        updateBase((draft) => {
          draft.settings.embedding = small.tag;
        });
        say(t("baseDoc.smaller", { name: small.name }), "success");
      }
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("baseDoc.unloaded"), "success");
    }
  });

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) --------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      batch?.attachment?.close();
      if (batch) batch.attachment = null;
    } else if (batch?.run && !batch.done) {
      batch.attachment = batch.run.attach(handlers, { after: batch.lastSeq });
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  function render() {
    renderLibrary();
    renderSettings();
  }

  const unsubscribeBase = subscribeBase(() => render());
  const unsubscribeRuns = store.select(
    (state) => state.runsActive.some((run) => run.kind === "ingest"),
    () => render(),
  );

  // Première lecture de la liste (`GET /api/rag/documents`) : le squelette s'affiche, la zone de dépôt non.
  const loadTimer = setTimeout(() => {
    if (frozenList) return;
    listLoading = false;
    renderLibrary();
  }, 700 / speedOf());

  view = {
    host,
    input,
    choose,
    get rows() {
      return rows;
    },
    get batch() {
      return batch;
    },
    get confirming() {
      return confirming;
    },
    get listLoading() {
      return listLoading;
    },
    importFiles,
    markEmbeddingLoaded() {
      embeddingLoaded = true;
    },
    sample: (name) => structuredClone(data.samples[name]),
    clearBase,
    deleteDocument,
    freezeList() {
      frozenList = true;
      listLoading = true;
      renderLibrary();
    },
    whenListReady: () => waitUntil(() => !listLoading),
    openSettings(value = true) {
      settings.open = value;
    },
    setFilter(value) {
      filter.value = value;
      renderLibrary();
    },
    sortBy(key) {
      libraryBody.querySelector(`.docs-sort[data-key="${key}"]`)?.click();
    },
    // Un import lancé depuis un autre onglet (409) : joué, mais non suivi par cet écran.
    startElsewhere(files) {
      const described = files.map((file) => describeFile(file, getBase()));
      const events = buildEvents(described, { loading: false, embedding: getBase().settings.embedding });
      return sim.play({ kind: "ingest", events }, serverEffects(described), {
        vars: { files: described },
        kind: "ingest",
        origin: "local",
        module: "rag",
      });
    },
    trySettings({ embedding } = {}) {
      settings.open = true;
      embeddingSelect.value = embedding;
      settings.dataset.touched = "1";
      settingsForm.requestSubmit();
    },
    saveSettings({ topK: k } = {}) {
      settings.open = true;
      topK.value = String(k);
      settings.dataset.touched = "1";
      settingsForm.requestSubmit();
    },
  };

  render();
  return () => {
    view = null;
    clearTimeout(loadTimer);
    clearInterval(batch?.timer);
    unsubscribeBase();
    unsubscribeRuns();
    visibility.disconnect();
    guard.dispose?.();
    batch?.attachment?.close();
    if (confirming) document.querySelector("wl-confirm-dialog dialog[open] button")?.click();
  };
}

// --- Scénarios ----------------------------------------------------------------------------

// Repart de l'état d'ouverture, pose la base attendue et attend la liste (sauf si `list: false`).
async function fresh(ctx, { base = "complet", setup = () => {}, list = true } = {}) {
  document.querySelector("wl-confirm-dialog dialog[open] button")?.click(); // un dialogue resté ouvert
  await ctx.reset();
  await setBasePreset(base);
  setup();
  await waitUntil(() => view !== null);
  if (list) await view.whenListReady();
}

const untilBatchDone = () => waitUntil(() => view.batch?.done);
const dialogOpen = () => Boolean(document.querySelector("wl-confirm-dialog dialog[open]"));

export const scenarios = [
  {
    id: "base-vide",
    label: "Base vide : « Votre base documentaire est vide » et la zone de dépôt (Flow 2)",
    run: (ctx) => fresh(ctx, { base: "vide" }),
  },
  {
    id: "base-remplie",
    label: "Base de 12 documents et 340 extraits, triée par date",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "chargement-liste",
    label: "Premier chargement de la liste : squelette, la zone de dépôt est déjà là",
    async run(ctx) {
      await fresh(ctx, { list: false });
      view.freezeList();
    },
  },
  {
    id: "import-un-document",
    label: "Import d'une note de cadrage fictive : « 14 extraits ajoutés depuis 1 document » (Flow 2)",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      await view.importFiles([view.sample("note")]);
      await untilBatchDone();
    },
  },
  {
    id: "import-plusieurs-fichiers",
    label: "Trois fichiers à la suite : « 45 extraits ajoutés depuis 3 documents »",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      await view.importFiles([view.sample("note"), view.sample("plan"), view.sample("retour")]);
      await untilBatchDone();
    },
  },
  {
    id: "envoi-en-cours",
    label: "Envoi du navigateur à 60 % (avant l'indexation)",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      await view.importFiles([view.sample("plan")], { holdAt: 60 });
      await waitUntil(() => view.rows[0]?.percent >= 60);
    },
  },
  {
    id: "import-en-cours",
    label: "Indexation en cours : « Vectorisation 18/40 extraits », Annuler",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      view.markEmbeddingLoaded();
      await view.importFiles([view.sample("plan"), view.sample("retour")], { speed: 0.5 });
      await waitUntil(() => view.rows[0]?.state === "embed");
    },
  },
  {
    id: "chargement-modele-representation",
    label: "Premier import : chargement du modèle de représentation (8 à 26 s)",
    async run(ctx) {
      await fresh(ctx, { base: "vide", setup: () => setMaquette({ slowLoad: true }) });
      await view.importFiles([view.sample("retour")]);
      await waitUntil(() => document.querySelector(".docs-embed-loading:not([hidden])"));
    },
  },
  {
    id: "import-avec-echec",
    label: "Un fichier échoue (PDF protégé) : raison, détails techniques, compteur inchangé pour lui",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      await view.importFiles([view.sample("note"), view.sample("protege"), view.sample("retour")]);
      await untilBatchDone();
    },
  },
  {
    id: "format-refuse",
    label: "Format refusé (.zip) : « Le fichier n'a pas pu être indexé »",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      await view.importFiles([view.sample("zip")]);
      await untilBatchDone();
    },
  },
  {
    id: "deja-present",
    label: "Fichier déjà dans la base (même empreinte) : non indexé une seconde fois",
    async run(ctx) {
      await fresh(ctx);
      await view.importFiles([view.sample("doublon")]);
      await untilBatchDone();
    },
  },
  {
    id: "annulation",
    label: "Annuler pendant la vectorisation : extraits du document en cours retirés, documents prêts intacts",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      view.markEmbeddingLoaded();
      await view.importFiles([view.sample("note"), view.sample("gros")], { speed: 0.7 });
      await waitUntil(() => view.rows[1]?.started);
      document.querySelector(".docs-import-cancel")?.click();
      await untilBatchDone();
    },
  },
  {
    id: "rejoint-409",
    label: "Un import tourne déjà (autre onglet) : 409, « Rejoindre l'exécution »",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      view.startElsewhere([view.sample("plan"), view.sample("retour")]);
      await pause(400);
      await view.importFiles([view.sample("note")]);
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau, l'import est refusé avec la marche à suivre",
    async run(ctx) {
      await fresh(ctx, { base: "vide", setup: () => setOllamaDown(true) });
      await view.importFiles([view.sample("note")]);
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire à l'import : besoin chiffré, deux issues",
    async run(ctx) {
      await fresh(ctx, { base: "vide", setup: () => setMaquette({ ramGuard: true }) });
      await view.importFiles([view.sample("note")]);
    },
  },
  {
    id: "document-en-indexation",
    label: "Un document est en cours d'indexation : « pas encore interrogeable », non compté",
    run: (ctx) => fresh(ctx, { base: "indexation" }),
  },
  {
    id: "filtrer",
    label: "Filtre « note » : 1 sur 12 affichés",
    async run(ctx) {
      await fresh(ctx);
      view.setFilter("note");
    },
  },
  {
    id: "filtre-sans-resultat",
    label: "Filtre sans résultat",
    async run(ctx) {
      await fresh(ctx);
      view.setFilter("budget");
    },
  },
  {
    id: "tri-par-extraits",
    label: "Tri par nombre d'extraits (Rapport-activite-2025.pdf, 52, en tête)",
    async run(ctx) {
      await fresh(ctx);
      view.sortBy("chunks");
      view.sortBy("chunks");
    },
  },
  {
    id: "suppression-document",
    label: "Supprimer un document : message au même verbe, compteur à jour",
    async run(ctx) {
      await fresh(ctx);
      await view.deleteDocument("doc-06");
    },
  },
  {
    id: "vider-confirmation",
    label: "« Vider la base documentaire » : « 340 extraits de 12 documents seront supprimés. »",
    async run(ctx) {
      await fresh(ctx);
      view.clearBase();
      await waitUntil(dialogOpen);
    },
  },
  {
    id: "vider-annule",
    label: "Vider cliqué par erreur, « Annuler » : rien n'est supprimé (Flow 2)",
    async run(ctx) {
      await fresh(ctx);
      const pending = view.clearBase();
      await waitUntil(dialogOpen);
      document.querySelector("wl-confirm-dialog .wl-dialog-actions .btn").click();
      await pending;
    },
  },
  {
    id: "vider-confirme",
    label: "Vider confirmé : base vide, « Base documentaire vidée »",
    async run(ctx) {
      await fresh(ctx);
      const pending = view.clearBase();
      await waitUntil(dialogOpen);
      document.querySelector("wl-confirm-dialog .wl-dialog-actions .btn-primary").click();
      await pending;
    },
  },
  {
    id: "reglages-ouverts",
    label: "Réglages ouverts : représentation, découpe, extraits, stratégie, reclassement indisponible",
    async run(ctx) {
      await fresh(ctx);
      view.openSettings();
    },
  },
  {
    id: "reglages-enregistres",
    label: "Réglages enregistrés : nombre d'extraits à 4",
    async run(ctx) {
      await fresh(ctx);
      view.saveSettings({ topK: 4 });
    },
  },
  {
    id: "changer-embedding",
    label: "Changer de modèle de représentation avec une base non vide : « Vider » d'abord",
    async run(ctx) {
      await fresh(ctx);
      view.trySettings({ embedding: "nomic-embed-text:latest" });
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant l'import, puis revenir : la progression reprend",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      view.markEmbeddingLoaded();
      await view.importFiles([view.sample("plan"), view.sample("retour")], { speed: 0.7 });
      await waitUntil(() => view.rows[0]?.started);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/documents/base");
      await waitUntil(() => view?.batch?.done);
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant l'import, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      view.markEmbeddingLoaded();
      await view.importFiles([view.sample("plan")]);
      await waitUntil(() => view.rows[0]?.started);
      view.batch.run.cut(1500);
      await pause(1500);
      await untilBatchDone();
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant l'import : « Interrompu », documents prêts intacts",
    async run(ctx) {
      await fresh(ctx, { base: "vide" });
      await view.importFiles([view.sample("note"), view.sample("plan")]);
      await waitUntil(() => view.rows[1]?.started);
      sim.restartServer();
      await untilBatchDone();
    },
  },
];
