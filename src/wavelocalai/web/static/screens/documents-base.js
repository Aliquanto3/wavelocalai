// Base documentaire, `#/documents/base` (UX-DR22, AD-6, AD-14, AD-20) : déposer des fichiers, suivre
// leur indexation un par un, lire la liste des documents de la base.
//
// - La zone de dépôt est construite avant tout appel au serveur : elle est visible tout de suite.
// - Un seul lecteur du flux d'un run : cet écran (`connectRun`). Les événements `ingest_progress`
//   et `ingest_file_done` nourrissent une ligne par fichier, repérée par `file_index` (l'ordre
//   d'envoi). Une ligne ne perd pas son nœud entre deux événements.
// - Un seul « Annuler l'import », au-dessus des lignes (D-25) : il annule le lot, jamais un fichier.
// - L'envoi passe par `XMLHttpRequest` (seul à donner la progression d'envoi) : les octets envoyés
//   sont répartis sur les fichiers dans l'ordre du formulaire. Annuler pendant l'envoi l'abandonne ;
//   le corps parti (le serveur crée peut-être déjà le run), Annuler attend le `run_id` et arrête le
//   run ; ensuite, Annuler arrête le run `ingest` (les fichiers non commencés ne le sont pas, les
//   documents déjà prêts restent).
// - L'écran reste en mémoire quand on va ailleurs (le routeur le masque) : masqué, il ferme son
//   flux en gardant le dernier `seq` ; de retour, il le rouvre par `?after=<seq>` (AD-6). Rechargée,
//   la page retrouve l'import en cours par le `run_id` d'un document `indexing` et le rejoue.
// - `409 run_busy` : l'import actif est rejoint, sans erreur affichée.
// - La fin de l'import est annoncée une seule fois (zone polie), par une phrase qui dit le nombre
//   d'extraits ajoutés, de documents, et de fichiers en échec.
// - Supprimer un document, vider la base (`wl-confirm-dialog`) : `documents-manage.js` ; réglages :
//   `documents-settings.js` (story 4.3).

import { api, ApiError, request, uploadDocuments } from "../core/api.js";
import { element } from "../core/dom.js";
import { formatDate, formatInteger } from "../core/format.js";
import { t } from "../core/i18n.js";
import { screenTabs } from "../core/screen-tabs.js";
import { connectRun } from "../core/sse.js";
import "../components/index.js";
import { createManage } from "./documents-manage.js";
import { createSettings } from "./documents-settings.js";
import { ImportRow, plural } from "./documents-import-row.js";

const MB = 1024 * 1024;
const STATUS_ORDER = { ready: 0, indexing: 1, failed: 2 };

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
  const importCancel = element("button", "btn docs-imports-cancel", t("docs.cancel_import"));
  importCancel.type = "button";
  importCancel.hidden = true;
  const importList = element("ul", "docs-imports");
  const imports = element("section", "docs-section");
  imports.hidden = true;
  imports.append(importsTitle, importCancel, importList);

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
  const clearButton = element("button", "btn docs-clear", t("docs.clear"));
  clearButton.type = "button";
  const tableHead = element("div", "docs-table-head");
  tableHead.append(count, clearButton);
  const table = document.createElement("wl-data-table");
  const tableSection = element("section", "docs-section");
  tableSection.hidden = true;
  tableSection.append(tableTitle, tableHead, table);

  // Supprimer, vider, régler (story 4.3) : les fonctions lues plus bas ne servent qu'à l'usage.
  const dialog = document.createElement("wl-confirm-dialog");
  const manage = createManage({
    dialog,
    problem,
    getData: () => data,
    refresh: () => refresh(),
    fallbackFocus: () => choose,
  });
  const settings = createSettings({ onClear: () => clearBase(), say: manage.say });

  host.replaceChildren(
    element("h1", "", t("screens.documents-base")),
    screenTabs("documents", "documents-base"),
    element("p", "lead", t("docs.lead")),
    drop,
    notice,
    problem,
    manage.status,
    summary,
    imports,
    loading,
    empty,
    tableSection,
    settings.el,
    dialog,
  );

  // --- État ------------------------------------------------------------------------------
  const rows = new Map(); // file_index -> ImportRow
  let data = null; // dernière réponse de GET /api/rag/documents
  let runId = null; // l'import suivi, tant qu'il n'est pas terminé
  let stream = null;
  let uploading = null; // AbortController de l'envoi en cours
  let sent = false; // le corps de l'envoi en cours est parti : l'abandonner n'arrêterait pas le run
  let cancelPending = false; // Annuler demandé après l'envoi du corps : le run sera arrêté
  let cancelFocused = false; // Annuler activé avec le focus (désactivé, le bouton le perd)
  let tally = { docs: 0, chunks: 0, failed: 0, duplicate: 0 };
  let wasHidden = host.hidden;
  let listFailed = false; // la liste n'a pas pu être lue (le message d'erreur le dit)
  let refreshing = null; // la lecture en cours (une promesse), sinon `null`
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
  COLUMNS.push({
    key: "actions",
    label: t("docs.col_actions"),
    sortable: false,
    cell: (doc) => manage.deleteButton(doc),
  });
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
    tableSection.hidden = listFailed || documents.length === 0; // jamais une liste périmée
    imports.hidden = rows.size === 0 && !locked; // le bouton d'annulation dès que le run est connu
    // Le lot fini, le bouton disparaît : le focus qu'il avait (ou qu'il a perdu en se désactivant)
    // passe à « Choisir des fichiers », pas à la page.
    const active = document.activeElement;
    const refocus =
      !locked && !importCancel.hidden &&
      (active === importCancel || (cancelFocused && (active === document.body || active === null)));
    importCancel.hidden = !locked;
    if (!locked) {
      importCancel.disabled = false;
      cancelFocused = false;
    }
    if (refocus) choose.focus();
    table.rows = documents; // vide : plus aucune ligne (donc plus de bouton « Supprimer » caché)
    if (documents.length > 0) {
      count.textContent = [
        plural("docs.docs", data.totals.documents),
        plural("docs.chunks", data.totals.chunks),
      ].join(" · ");
    }
  }

  function refresh() {
    // Une lecture à la fois ; une demande arrivée pendant la lecture en déclenche une de plus, et
    // son appelant attend la fin de toutes (le rendu est alors à jour).
    if (refreshing) {
      refreshAgain = true;
      return refreshing;
    }
    refreshing = (async () => {
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
        refreshing = null;
      }
      return data;
    })();
    return refreshing;
  }

  function addRow(key, name) {
    const row = new ImportRow(key, name);
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
    tally = { docs: 0, chunks: 0, failed: 0, duplicate: 0 };
    summary.textContent = "";
  }

  // --- Fin d'un import -------------------------------------------------------------------
  function sentence(status) {
    const parts = [];
    if (tally.docs > 0) {
      parts.push(`${plural("docs.added", tally.chunks)} ${plural("docs.from", tally.docs)}.`);
    }
    if (tally.duplicate > 0) parts.push(plural("docs.duplicate_count", tally.duplicate));
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
    settings.load(); // le modèle de la base est celui du premier import
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
      if (row.final) return; // flux rejoué depuis le début : déjà compté
      row.state = payload.status;
      row.chunks = payload.chunks ?? 0;
      row.error = payload.error ?? null;
      row.render();
      if (payload.status === "ready") {
        tally.docs += 1;
        tally.chunks += row.chunks;
      } else if (payload.status === "failed") {
        tally.failed += 1;
      } else if (payload.status === "duplicate") {
        tally.duplicate += 1;
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
      if (runId !== id) return;
      // Flux perdu mais run actif : on le suit de nouveau (événements rejoués écartés par ligne).
      if (ended !== "running") endRun(ended);
      else if (!host.hidden) openStream(id);
    });
  }

  // Page rechargée pendant un import (ou réponse d'envoi perdue) : le `run_id` d'un document
  // `indexing` retrouve le run.
  function adoptActiveRun(loaded, stop) {
    const active = loaded?.documents.find((doc) => doc.status === "indexing" && doc.run_id);
    if (!active || busy()) return;
    follow(active.run_id);
    if (stop) cancel();
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
    sent = false;
    cancelPending = false;
    render();
    try {
      const started = await uploadDocuments(files, {
        signal: controller.signal,
        onProgress: (loaded, size) => spreadProgress(files, loaded, size),
        onSent: () => (sent = true),
      });
      uploading = null;
      for (const row of rows.values()) {
        row.uploaded = true;
        row.state = "waiting";
        row.render();
      }
      follow(started.run_id);
      if (cancelPending) stopRun(started.run_id); // Annuler demandé pendant que le run naissait
    } catch (failure) {
      uploading = null;
      // Pas de réponse alors que le corps est parti (`status` 0) : le run existe peut-être.
      const lost = sent && failure instanceof ApiError && failure.status === 0;
      const stopAdopted = lost && cancelPending;
      cancelPending = false;
      importCancel.disabled = false;
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
        // Réponse perdue après l'envoi du corps : le serveur a peut-être créé le run. On le retrouve
        // comme au rechargement, et on l'arrête si Annuler avait été demandé.
        if (lost) refresh().then((loaded) => adoptActiveRun(loaded, stopAdopted));
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

  // « Vider » (bouton du tableau ou de l'erreur de réglage) ; les réglages se relisent ensuite.
  async function clearBase() {
    const cleared = await manage.clearBase();
    if (cleared) settings.load();
    return cleared;
  }
  clearButton.addEventListener("click", clearBase);

  const stopRun = (id) =>
    api.cancelRun(id).catch(() => (importCancel.disabled = false));

  function cancel() {
    cancelFocused = document.activeElement === importCancel;
    importCancel.disabled = true; // un seul arrêt à la fois
    if (uploading && sent) {
      cancelPending = true; // le serveur a le corps : abandonner la requête laisserait le run indexer
    } else if (uploading) {
      uploading.abort();
    } else if (runId) {
      stopRun(runId);
    }
  }

  importCancel.addEventListener("click", cancel);
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
      settings.load();
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  // --- Premier affichage -----------------------------------------------------------------
  render();
  refresh().then((loaded) => adoptActiveRun(loaded, false));
  settings.load();

  return () => {
    visibility.disconnect();
    document.removeEventListener("dragover", guard);
    document.removeEventListener("drop", guard);
    uploading?.abort();
    stream?.close();
    stream = null;
  };
}
