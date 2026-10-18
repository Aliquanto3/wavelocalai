// Base documentaire, `#/documents/base` (UX-DR22, AD-6, AD-14, AD-20) : déposer des fichiers, suivre
// leur indexation un par un, lire la liste des documents de la base.
//
// - La zone de dépôt est construite avant tout appel au serveur : elle est visible tout de suite.
// - Un seul lecteur du flux d'un run : cet écran (`connectRun`). Les événements `ingest_progress`
//   et `ingest_file_done` nourrissent une ligne par fichier, repérée par `file_index` (l'ordre
//   d'envoi). Une ligne ne perd pas son nœud entre deux événements (le focus reste sur Annuler).
// - L'envoi passe par `XMLHttpRequest` (seul à donner la progression d'envoi) : les octets envoyés
//   sont répartis sur les fichiers dans l'ordre du formulaire. Annuler pendant l'envoi l'abandonne ;
//   ensuite, Annuler arrête le run `ingest` (les fichiers non commencés ne le sont pas).
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son
//   flux en gardant le dernier `seq` ; de retour, il le rouvre par `?after=<seq>` (AD-6). Rechargée,
//   la page retrouve l'import en cours par le `run_id` d'un document `indexing` et le rejoue.
// - `409 run_busy` : l'import actif est rejoint, sans erreur affichée.
// - La fin de l'import est annoncée une seule fois (zone polie), par une phrase qui dit le nombre
//   d'extraits ajoutés, de documents, et de fichiers en échec.

import { api, ApiError, request, uploadDocuments } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatDate, formatInteger } from "../core/format.js";
import { t } from "../core/i18n.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import "../components/index.js";

const MB = 1024 * 1024;
const FINAL = new Set(["ready", "duplicate", "failed", "cancelled", "interrupted"]);
const STATUS_ORDER = { ready: 0, indexing: 1, failed: 2 };

const plural = (base, n, vars = {}) =>
  t(`${base}_${n < 2 ? "one" : "other"}`, { n: formatInteger(n), ...vars });

function failureMessage(error) {
  // « Le fichier n'a pas pu être indexé : <raison>. » (l'enveloppe fournit le message et la raison).
  const base = String(error?.message ?? t("docs.failed_default")).replace(/[.\s]+$/, "");
  const reason = error?.detail?.reason;
  return reason ? t("docs.failed_with", { message: base, reason }) : `${base}.`;
}

function failureEnvelope(error) {
  const technical = error?.detail?.technical;
  const reason = error?.detail?.reason;
  return {
    code: error?.code ?? "ingest_failed",
    message: failureMessage(error),
    action: error?.action,
    detail: technical && technical !== reason ? { technical } : null,
  };
}

// Une ligne par fichier : nœuds créés une fois, mis à jour sur place.
class ImportRow {
  constructor(key, name, onCancel) {
    this.key = key;
    this.name = name;
    this.state = "waiting";
    this.listed = false; // le document de ce fichier figure dans la liste du serveur
    this.uploaded = false; // l'envoi du navigateur est terminé (ligne née de cet écran)
    this.percent = 0;
    this.done = 0;
    this.total = 0;
    this.chunks = 0;
    this.error = null;
    this.el = element("li", "docs-import");
    this.title = element("p", "docs-import-name", name);
    this.line = element("p", "docs-import-state");
    this.bar = element("progress", "docs-import-progress");
    this.bar.max = 100;
    this.bar.setAttribute("aria-label", t("docs.row_progress", { file: name }));
    this.cancel = element("button", "btn docs-import-cancel", t("docs.cancel"));
    this.cancel.type = "button";
    this.cancel.setAttribute("aria-label", t("docs.cancel_import"));
    this.cancel.addEventListener("click", onCancel);
    this.failure = document.createElement("wl-error");
    this.el.append(this.title, this.line, this.cancel, this.bar, this.failure);
    this.render();
  }

  get final() {
    return FINAL.has(this.state);
  }

  trail() {
    const parts = [];
    if (this.uploaded) parts.push(t("docs.row_sent"));
    if (this.state === "waiting") parts.push(t("docs.row_waiting"));
    if (this.state === "extract") parts.push(t("docs.row_extract"));
    if (this.state === "split" || this.state === "embed") parts.push(t("docs.row_split"));
    if (this.state === "embed") {
      parts.push(
        t("docs.row_embed", { done: formatInteger(this.done), total: formatInteger(this.total) }),
      );
    }
    return parts.join(" · ");
  }

  text() {
    switch (this.state) {
      case "uploading":
        return t("docs.row_sending", { percent: formatInteger(Math.round(this.percent)) });
      case "ready":
        return plural("docs.row_done", this.chunks);
      case "duplicate":
        return t("docs.row_duplicate");
      case "cancelled":
        return t("docs.row_cancelled");
      case "interrupted":
        return t("docs.row_interrupted");
      case "failed":
        return "";
      default:
        return this.trail();
    }
  }

  render() {
    this.el.dataset.state = this.state;
    this.line.textContent = this.text();
    this.line.hidden = this.state === "failed";
    this.failure.error = this.state === "failed" ? failureEnvelope(this.error) : null;
    const active = !this.final;
    this.bar.hidden = !active;
    this.cancel.hidden = !active;
    if (this.state === "uploading") this.bar.value = this.percent;
    else if (this.state === "embed" && this.total > 0) this.bar.value = (100 * this.done) / this.total;
    else this.bar.removeAttribute("value"); // progression indéterminée
  }
}

export function mount(host) {
  // --- Structure -------------------------------------------------------------------------
  const input = element("input", "docs-file-input");
  input.type = "file";
  input.multiple = true;
  input.accept = ".pdf,.txt,.md,.docx";
  input.tabIndex = -1;
  input.setAttribute("aria-hidden", "true");

  const choose = element("button", "btn docs-choose", t("docs.choose"));
  choose.type = "button";
  const dropLine = element("p", "docs-drop-line");
  dropLine.append(
    document.createTextNode(`${t("docs.drop_text")} `),
    choose,
    document.createTextNode(` · ${t("docs.formats")}`),
  );
  const limitsHelp = element("p", "help");
  limitsHelp.hidden = true;
  const busyHelp = element("p", "help", t("docs.busy"));
  busyHelp.hidden = true;
  const drop = element("div", "docs-drop");
  drop.setAttribute("role", "group");
  drop.setAttribute("aria-label", t("docs.drop_label"));
  drop.append(dropLine, limitsHelp, busyHelp, input);

  const notice = element("p", "docs-notice");
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const problem = document.createElement("wl-error");
  const summary = element("p", "docs-count docs-summary");
  summary.setAttribute("role", "status");

  const importsTitle = element("h2", "", t("docs.imports_title"));
  const importList = element("ul", "docs-imports");
  const imports = element("section", "docs-section");
  imports.hidden = true;
  imports.append(importsTitle, importList);

  const loading = element("p", "help", t("docs.loading"));
  loading.setAttribute("role", "status");
  const emptyAction = element("button", "btn docs-primary", t("docs.empty_action"));
  emptyAction.type = "button";
  const empty = element("section", "docs-card");
  empty.hidden = true;
  empty.append(
    element("h2", "", t("docs.empty_title")),
    element("p", "", t("docs.empty_text")),
    emptyAction,
  );

  const tableTitle = element("h2", "", t("docs.table_title"));
  const count = element("p", "docs-count");
  const table = document.createElement("wl-data-table");
  const tableSection = element("section", "docs-section");
  tableSection.hidden = true;
  tableSection.append(tableTitle, count, table);

  host.replaceChildren(
    element("h1", "", t("screens.documents-base")),
    screenTabs("documents", "documents-base"),
    element("p", "lead", t("docs.lead")),
    drop,
    notice,
    problem,
    summary,
    imports,
    loading,
    empty,
    tableSection,
  );

  // --- État ------------------------------------------------------------------------------
  const rows = new Map(); // file_index -> ImportRow
  let data = null; // dernière réponse de GET /api/rag/documents
  let runId = null; // l'import suivi, tant qu'il n'est pas terminé
  let stream = null;
  let uploading = null; // AbortController de l'envoi en cours
  let tally = { docs: 0, chunks: 0, failed: 0 };
  let wasHidden = host.hidden;
  let listFailed = false; // la liste n'a pas pu être lue (le message d'erreur le dit)
  let refreshing = false;
  let refreshAgain = false;

  const busy = () => uploading !== null || runId !== null;

  // --- Rendu -----------------------------------------------------------------------------
  function renderLimits() {
    const limits = data?.limits;
    limitsHelp.hidden = !limits;
    if (!limits) return;
    limitsHelp.textContent = t("docs.limits", {
      file: formatInteger(limits.max_file_mb),
      files: formatInteger(limits.max_files),
      total: formatInteger(limits.max_import_mb),
    });
  }

  function statusCell(doc) {
    const cell = element("span", "docs-status");
    cell.dataset.status = doc.status;
    cell.append(document.createTextNode(t(`docs.status_${doc.status}`)));
    const reason = doc.error?.detail?.reason;
    if (doc.status === "failed" && reason) cell.append(element("span", "docs-status-reason", reason));
    return cell;
  }

  const COLUMNS = [
    { key: "source", label: t("docs.col_name"), sortable: true, value: (doc) => doc.source },
    {
      key: "chunks",
      label: t("docs.col_chunks"),
      sortable: true,
      numeric: true,
      value: (doc) => (doc.status === "ready" ? doc.chunks : null),
      cell: (doc) => {
        if (doc.status === "indexing") return t("docs.chunks_pending");
        return doc.status === "failed" ? t("docs.chunks_none") : formatInteger(doc.chunks);
      },
    },
    {
      key: "created_at",
      label: t("docs.col_added"),
      sortable: true,
      value: (doc) => Date.parse(doc.created_at),
      cell: (doc) => formatDate(doc.created_at),
    },
    {
      key: "embedding_model",
      label: t("docs.col_model"),
      sortable: true,
      value: (doc) => doc.embedding_model,
    },
    {
      key: "status",
      label: t("docs.col_status"),
      sortable: true,
      value: (doc) => STATUS_ORDER[doc.status] ?? 3,
      cell: statusCell,
    },
  ];
  table.caption = t("docs.table_caption");
  table.columns = COLUMNS;
  table.sort = { key: "created_at", dir: "desc" };

  function render() {
    const documents = data?.documents ?? [];
    renderLimits();
    const locked = busy();
    choose.disabled = locked;
    emptyAction.disabled = locked;
    busyHelp.hidden = !locked;
    loading.hidden = data !== null || listFailed;
    empty.hidden = data === null || documents.length > 0 || locked;
    tableSection.hidden = documents.length === 0;
    imports.hidden = rows.size === 0;
    if (documents.length > 0) {
      table.rows = documents;
      count.textContent = [
        plural("docs.docs", data.totals.documents),
        plural("docs.chunks", data.totals.chunks),
      ].join(" · ");
    }
  }

  async function refresh() {
    // Une lecture à la fois ; une demande arrivée pendant la lecture en déclenche une de plus.
    if (refreshing) {
      refreshAgain = true;
      return;
    }
    refreshing = true;
    try {
      do {
        refreshAgain = false;
        try {
          data = await api.documents();
          listFailed = false;
          if (problem.error?.code === "list_failed") problem.error = null;
        } catch {
          problem.error = {
            code: "list_failed",
            message: t("docs.list_failed"),
            action: t("docs.list_failed_action"),
          };
          listFailed = true; // ni « base vide » ni liste périmée présentée comme à jour
        }
        render();
      } while (refreshAgain);
    } finally {
      refreshing = false;
    }
    return data;
  }

  function addRow(key, name) {
    const row = new ImportRow(key, name, cancel);
    rows.set(key, row);
    importList.append(row.el);
    return row;
  }

  function rowFor(payload) {
    const key = Number(payload?.file_index) || rows.size + 1;
    return rows.get(key) ?? addRow(key, String(payload?.file ?? ""));
  }

  function resetRows() {
    rows.clear();
    importList.replaceChildren();
    tally = { docs: 0, chunks: 0, failed: 0 };
    summary.textContent = "";
  }

  // --- Fin d'un import -------------------------------------------------------------------
  function sentence(status) {
    const parts = [];
    if (tally.docs > 0) {
      parts.push(`${plural("docs.added", tally.chunks)} ${plural("docs.from", tally.docs)}.`);
    }
    if (tally.failed > 0) parts.push(plural("docs.failed_count", tally.failed));
    if (status === "cancelled") parts.push(t("docs.cancelled"));
    else if (status !== "ok") parts.push(t("docs.interrupted"));
    return parts.join(" ");
  }

  function endRun(status) {
    for (const row of rows.values()) {
      if (row.final) continue;
      row.state = status === "cancelled" ? "cancelled" : "interrupted";
      row.render();
    }
    stream?.close();
    stream = null;
    runId = null;
    summary.textContent = sentence(status); // une seule annonce, à la fin
    render();
    refresh();
  }

  // --- Flux ------------------------------------------------------------------------------
  const handlers = {
    ingest_progress: (payload) => {
      const row = rowFor(payload);
      if (row.final) return;
      if (!row.listed) {
        row.listed = true;
        refresh(); // le document existe désormais : `indexing` dans le tableau, jamais « prêt »
      }
      row.state = payload.phase;
      row.done = payload.done ?? 0;
      row.total = payload.total ?? 0;
      row.render();
    },
    ingest_file_done: (payload) => {
      const row = rowFor(payload);
      row.state = payload.status;
      row.chunks = payload.chunks ?? 0;
      row.error = payload.error ?? null;
      row.render();
      if (payload.status === "ready") {
        tally.docs += 1;
        tally.chunks += row.chunks;
      } else if (payload.status === "failed") {
        tally.failed += 1;
      }
      refresh();
    },
    run_ended: (payload) => endRun(payload?.status ?? "error"),
  };

  function openStream(id) {
    stream?.close({ keepSeq: true });
    stream = connectRun(id, handlers, async ({ status }) => {
      if (runId !== id || !["closed", "failed"].includes(status)) return;
      // Fin du flux sans `run_ended` (rien à rejouer, ou run introuvable) : l'état vient du run.
      let ended = "interrupted";
      try {
        ended = (await request(`/api/runs/${encodeURIComponent(id)}`)).status;
      } catch {
        // Run inconnu : l'import est dit interrompu.
      }
      if (runId === id) endRun(ended === "running" ? "interrupted" : ended);
    });
  }

  function follow(id) {
    runId = id;
    if (!host.hidden) openStream(id); // masqué : le flux s'ouvrira au retour (AD-6)
    render();
  }

  // --- Actions ---------------------------------------------------------------------------
  function refuse(message) {
    problem.error = { code: "invalid_request", message, action: t("docs.limit_action") };
  }

  async function startImport(list) {
    const files = Array.from(list ?? []);
    if (files.length === 0 || busy()) return;
    problem.error = null;
    notice.hidden = true;
    const limits = data?.limits;
    if (limits && files.length > limits.max_files) {
      return refuse(t("docs.too_many", { max: formatInteger(limits.max_files) }));
    }
    const total = files.reduce((sum, file) => sum + file.size, 0);
    if (limits && total > limits.max_import_mb * MB) {
      return refuse(t("docs.too_big", { max: formatInteger(limits.max_import_mb) }));
    }

    resetRows();
    files.forEach((file, index) => {
      const row = addRow(index + 1, file.name);
      row.state = "uploading";
      row.render();
    });
    const controller = new AbortController();
    uploading = controller;
    render();
    try {
      const started = await uploadDocuments(files, {
        signal: controller.signal,
        onProgress: (loaded, size) => spreadProgress(files, loaded, size),
      });
      uploading = null;
      for (const row of rows.values()) {
        row.uploaded = true;
        row.state = "waiting";
        row.render();
      }
      follow(started.run_id);
    } catch (failure) {
      uploading = null;
      if (failure?.name === "AbortError") {
        for (const row of rows.values()) {
          row.state = "cancelled";
          row.render();
        }
        summary.textContent = t("docs.cancelled");
      } else if (failure instanceof ApiError && failure.status === 409 && failure.envelope?.detail?.run_id) {
        // Un import tourne déjà : on le rejoint (rejoué depuis le début), sans erreur.
        resetRows();
        notice.textContent = t("docs.joined");
        notice.hidden = false;
        follow(failure.envelope.detail.run_id);
      } else {
        resetRows();
        problem.error =
          failure instanceof ApiError && failure.envelope
            ? failure.envelope
            : { code: "upload_failed", message: t("docs.upload_failed"), action: t("docs.upload_failed_action") };
      }
      render();
    }
  }

  // Les octets envoyés (formulaire entier, en-têtes compris) répartis sur les fichiers, dans l'ordre.
  function spreadProgress(files, loaded) {
    let start = 0;
    files.forEach((file, index) => {
      const row = rows.get(index + 1);
      if (!row || row.state !== "uploading") return;
      row.percent = file.size === 0 ? (loaded > start ? 100 : 0) : Math.min(100, Math.max(0, ((loaded - start) / file.size) * 100));
      row.render();
      start += file.size;
    });
  }

  function cancel() {
    for (const row of rows.values()) row.cancel.disabled = true; // un seul arrêt à la fois
    if (uploading) {
      uploading.abort();
    } else if (runId) {
      api.cancelRun(runId).catch(() => {
        for (const row of rows.values()) row.cancel.disabled = false;
      });
    }
  }

  choose.addEventListener("click", () => input.click());
  emptyAction.addEventListener("click", () => input.click());
  input.addEventListener("change", () => {
    const files = Array.from(input.files ?? []);
    input.value = ""; // le même fichier peut être choisi de nouveau
    startImport(files);
  });

  // Glisser-déposer : la zone reçoit les fichiers ; ailleurs, le navigateur n'ouvre pas le fichier
  // à la place de l'écran.
  const hasFiles = (event) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
  drop.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    drop.dataset.active = "true";
  });
  drop.addEventListener("dragover", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    drop.dataset.active = "true";
  });
  drop.addEventListener("dragleave", (event) => {
    if (!drop.contains(event.relatedTarget)) drop.dataset.active = "false";
  });
  drop.addEventListener("drop", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    drop.dataset.active = "false";
    startImport(event.dataTransfer.files);
  });
  const guard = (event) => {
    if (!host.hidden && hasFiles(event) && !drop.contains(event.target)) event.preventDefault();
  };
  document.addEventListener("dragover", guard);
  document.addEventListener("drop", guard);

  // --- Écran masqué puis revu ------------------------------------------------------------
  // Le routeur masque l'écran sans le démonter : on ferme le flux (l'indexation continue sur le
  // serveur), et au retour on reprend après le dernier `seq` reçu.
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      stream?.close({ keepSeq: true });
      stream = null;
    } else {
      if (runId) openStream(runId);
      refresh();
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  // --- Premier affichage -----------------------------------------------------------------
  render();
  refresh().then((loaded) => {
    // Page rechargée pendant un import : le `run_id` d'un document `indexing` le retrouve.
    const active = loaded?.documents.find((doc) => doc.status === "indexing" && doc.run_id);
    if (active && !busy()) follow(active.run_id);
  });

  return () => {
    visibility.disconnect();
    document.removeEventListener("dragover", guard);
    document.removeEventListener("drop", guard);
    uploading?.abort();
    stream?.close();
    stream = null;
  };
}
