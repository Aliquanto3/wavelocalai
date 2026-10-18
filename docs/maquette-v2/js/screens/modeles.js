// Modèles, `#/modeles` et `#/modeles/<tag>` (UX-DR27, stories 5.3 à 5.6, EXPERIENCE.md « Modèles »).
// Écran à l'état livré, branché sur le simulateur (js/sim/sim.js, js/sim/modeles.js).
//
// - Barre d'actions : « Décharger les modèles inactifs » (sans confirmation), installation par nom.
// - « Sur ce poste » : tableau triable (tient en mémoire, chargé, débit mesuré), « Supprimer » avec
//   confirmation chiffrée ; « Modèles proposés par défaut » (Changer, Revenir au choix automatique) ;
//   « Catalogue installable » (mémoire nécessaire, « Ne tient pas : … » mais installable) ; « Reclassement
//   des extraits » (reranker).
// - Installation : run `pull` suivi par `pull_progress` (octets reçus et totaux, phase). Un seul à la
//   fois ; un 409 `run_busy` rejoint le run actif ; quitter l'écran puis revenir reprend la progression.
// - Fiche du modèle (`#/modeles/<tag>`, liste toujours visible) : caractéristiques, « Pourquoi ce
//   débit ? », « Sur d'autres postes » (qb.results/1, AD-22).
// Le front ne calcule aucune mesure (AD-20) : `fits`, la mémoire libre et les débits sont ceux que le
// serveur simulé publie (donnees/modeles.json, donnees/commun/modeles.json). L'état d'installation est
// gardé au niveau du module : il survit au passage liste -> fiche, et se remet à zéro avec la maquette.

import { element, icon } from "../core/dom.js";
import { formatGb, formatInteger, formatNumber, formatPercent, formatRate } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { listModels, modelDefaults } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";

const GB = 1e9;
const PURPOSES = ["chat", "arena", "judge", "agent", "rag"];
const RUN_KINDS = ["chat", "arena", "rag", "agent", "bench", "eval"];

let view = null; // l'instance montée, pour les scénarios
let hooked = false;

// --- État du module (survit au remontage de l'écran ; remis à zéro avec la maquette) ----------

function freshState() {
  return {
    deleted: new Set(), // tags supprimés du poste
    added: [], // modèles installés pendant la visite
    unloadedTags: new Set(),
    defaults: {}, // usage -> { tags, chosen: true }
    noAgent: false,
    rerankerInstalled: false,
    rerankerExtraMissing: false,
    noReferences: false,
    pull: null, // { runId, tag, name, reranker, total, received, phase, stopping, speed }
    result: null, // { tone, text } : dernier résultat, affiché jusqu'à la prochaine action
    error: null, // { envelope, tag, target }
  };
}

let state = freshState();

function hookReset() {
  const api = window.__maquette;
  if (!api || hooked || api.__modelesHook) return;
  const original = api.reset.bind(api);
  api.reset = async () => {
    state = freshState();
    return original();
  };
  api.__modelesHook = true;
  hooked = true;
}

// --- Petits utilitaires ------------------------------------------------------------------------

function fill(text, vars = {}) {
  return String(text ?? "").replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

// Les textes citent des commandes entre accents graves : rendues en <code>.
function richText(tag, className, text) {
  const node = element(tag, className);
  String(text ?? "")
    .split("`")
    .forEach((part, index, parts) => {
      if (!part) return;
      node.append(index % 2 === 1 && index < parts.length - 1 ? element("code", "", part) : document.createTextNode(part));
    });
  return node;
}

function paramsText(model) {
  const total = model.params_total_b;
  const active = model.params_active_b;
  if (total == null) return t("modeles.fiche.unknown");
  if (active != null && active !== total) {
    return t("modeles.installed.params_active", { total: formatNumber(total), active: formatNumber(active) });
  }
  return t("modeles.installed.params_total", { total: formatNumber(total) });
}

function inUse(tag) {
  return RUN_KINDS.some((kind) => {
    const run = sim.active(kind);
    const vars = run?.options?.vars ?? {};
    return run && (vars.tag === tag || (Array.isArray(vars.tags) && vars.tags.includes(tag)));
  });
}

function pullTarget(pull, catalogTags) {
  if (!pull) return null;
  if (pull.reranker) return "reranker";
  return catalogTags.has(pull.tag) ? `catalog:${pull.tag}` : "free";
}

// --- Tableau triable ----------------------------------------------------------------------------

function buildTable({ caption, regionLabel, columns, rows, sort, onSort, tableId, rowClass, extra }) {
  const table = element("table", "mod-table");
  table.append(element("caption", "sr-only", caption));
  const head = element("tr");
  for (const column of columns) {
    const th = element("th", column.numeric ? "is-numeric" : "");
    th.scope = "col";
    if (column.sortValue && onSort) {
      const button = element("button", "mod-sort");
      button.type = "button";
      button.dataset.fid = `sort:${tableId}:${column.key}`;
      button.append(element("span", "", column.label), icon("expand-more"));
      const active = sort.key === column.key;
      if (active) {
        th.setAttribute("aria-sort", sort.dir === "asc" ? "ascending" : "descending");
        button.dataset.dir = sort.dir;
      }
      button.setAttribute(
        "aria-label",
        `${t("modeles.installed.sort_by", { column: column.label })}${active ? `, ${t(sort.dir === "asc" ? "modeles.installed.sorted_asc" : "modeles.installed.sorted_desc")}` : ""}`,
      );
      button.addEventListener("click", () => onSort(column.key));
      th.append(button);
    } else {
      th.append(column.label);
    }
    head.append(th);
  }
  const thead = element("thead");
  thead.append(head);
  const body = element("tbody");
  for (const row of rows) {
    const tr = element("tr", rowClass?.(row) ?? "");
    for (const column of columns) {
      const td = element("td", column.numeric ? "is-numeric" : "");
      td.dataset.label = column.label;
      const cell = column.cell(row);
      if (cell !== null && cell !== undefined) td.append(cell);
      tr.append(td);
    }
    body.append(tr);
    const more = extra?.(row);
    if (more) {
      const trExtra = element("tr", "mod-extra");
      const td = element("td");
      td.colSpan = columns.length;
      td.append(more);
      trExtra.append(td);
      body.append(trExtra);
    }
  }
  table.append(thead, body);
  const region = element("div", "mod-scroll");
  region.tabIndex = 0;
  region.setAttribute("role", "region");
  region.setAttribute("aria-label", regionLabel);
  region.append(table);
  return region;
}

function sortRows(rows, column, dir, fallback) {
  const sorted = [...rows];
  if (!column) return sorted.sort(fallback);
  const sign = dir === "asc" ? 1 : -1;
  return sorted.sort((a, b) => {
    const left = column.sortValue(a);
    const right = column.sortValue(b);
    if (left == null && right == null) return 0;
    if (left == null) return 1; // une valeur absente reste en bas, quel que soit le sens
    if (right == null) return -1;
    if (typeof left === "string") return left.localeCompare(right, "fr-FR") * sign;
    return (left - right) * sign;
  });
}

// --- Écran --------------------------------------------------------------------------------------

export async function mount(host, ctx) {
  hookReset();
  const data = await ctx.data("modeles.json");
  const fixedTag = ctx.params.tag ?? null;

  let installed = []; // modèles installés (hors supprimés, avec ajouts)
  let modelIndex = new Map(); // tag -> modèle connu (installé, catalogue, cloud)
  let ollamaUp = true;
  let autoDefaults = {}; // usage -> { tags, reason } du serveur simulé
  let catalog = [];
  let loadingForced = false;
  let editing = null; // usage dont le sélecteur est ouvert
  let draft = "";
  let sortInstalled = { key: null, dir: "asc" };
  let sortCatalog = { key: null, dir: "asc" };
  let attachment = null;
  let progressNodes = [];
  let chain = Promise.resolve();
  let alive = true;
  let editMessage = null; // erreur d'éligibilité du sélecteur

  const guard = ctx.states.ollamaGuard();
  const notices = element("div", "mod-notices");
  const main = element("div", "mod-main");
  const fiche = element("section", "mod-fiche");
  fiche.setAttribute("aria-label", t("modeles.fiche.aria"));
  const layout = element("div", "mod-layout");
  layout.append(fiche, main);
  host.replaceChildren(element("h1", "", ctx.route.title), element("p", "lead", t("modeles.lead")), guard, notices, layout);

  // --- Données (réponses simulées de GET /api/models et des défauts) --------------------------
  const freeGb = () => {
    const base = store.get().maquette.ramGuard ? data.free_gb_ram_guard : data.free_gb;
    let free = base;
    for (const tag of state.unloadedTags) free += modelIndex.get(tag)?.size_gb ?? 0;
    return free;
  };

  const loadedTags = () => {
    const models = store.get().system.modelsLoaded;
    if (!ollamaUp || !Array.isArray(models)) return null;
    return models.map((model) => model.tag).filter((tag) => !state.unloadedTags.has(tag));
  };

  async function refresh() {
    const [local, all] = await Promise.all([listModels(false), listModels(true)]);
    ollamaUp = local.ollama_up;
    const none = store.get().maquette.noLocalModel;
    installed = none ? [] : [...local.models.filter((model) => !state.deleted.has(model.tag)), ...state.added];
    const installedTags = new Set(installed.map((model) => model.tag));
    modelIndex = new Map();
    for (const model of all.models) modelIndex.set(model.tag, model);
    for (const entry of data.catalog) if (!modelIndex.has(entry.tag)) modelIndex.set(entry.tag, entry);
    for (const model of state.added) modelIndex.set(model.tag, model);
    // Le catalogue : les modèles du catalogue non installés, et ceux que l'on a supprimés du poste.
    const returned = [...state.deleted]
      .map((tag) => modelIndex.get(tag))
      .filter((model) => model && model.origin === "local" && model.kind === "chat");
    catalog = [...data.catalog, ...returned].filter((entry) => !installedTags.has(entry.tag));
    // Défauts proposés par le serveur simulé.
    autoDefaults = {};
    for (const purpose of PURPOSES) {
      const found = await modelDefaults(purpose, false).catch(() => ({ tags: [], reason: data.purpose_none_reasons[purpose] }));
      let tags = (found.tags ?? []).filter((tag) => installedTags.has(tag) || !modelIndex.get(tag) || modelIndex.get(tag).origin === "cloud");
      let reason = found.reason;
      if (!tags.length && found.tags?.length) {
        const fallback = installed.find((model) => model.kind === "chat" && model.fits);
        tags = fallback ? [fallback.tag] : [];
        reason = fallback ? "Le modèle local le plus rapide qui tient en mémoire parmi ceux installés." : data.purpose_none_reasons[purpose];
      }
      if (purpose === "agent" && state.noAgent) {
        tags = [];
        reason = data.purpose_none_reasons.agent;
      }
      autoDefaults[purpose] = { tags, reason: reason || data.purpose_none_reasons[purpose] };
    }
  }

  function schedule() {
    chain = chain.then(async () => {
      if (!alive) return;
      await refresh();
      if (alive) render();
    });
    return chain;
  }

  // --- Sections --------------------------------------------------------------------------------
  function installBlockedReason() {
    if (!ollamaUp) return t("modeles.actions.install_ollama_down");
    if (state.pull) return t("modeles.actions.install_busy", { tag: state.pull.tag });
    return "";
  }

  function pullProgress(target) {
    const pull = state.pull;
    if (!pull) return null;
    const box = element("div", "mod-progress");
    box.dataset.target = target;
    const label = element("p", "mod-progress-label");
    const bar = document.createElement("progress");
    bar.className = "mod-progress-bar";
    bar.setAttribute("aria-label", t("modeles.pull.progress_label", { name: pull.name }));
    const cancel = element("button", "btn", t("modeles.pull.cancel"));
    cancel.type = "button";
    cancel.dataset.fid = `cancel:${pull.tag}`;
    cancel.setAttribute("aria-label", t("modeles.pull.cancel_aria", { name: pull.name }));
    cancel.addEventListener("click", () => cancelPull());
    box.append(label, bar, cancel);
    progressNodes.push({ label, bar, cancel });
    return box;
  }

  function updateProgress() {
    const pull = state.pull;
    if (!pull) return;
    for (const node of progressNodes) {
      let text = t("modeles.pull.starting");
      if (pull.phase === "downloading" || pull.phase === "verifying") {
        if (pull.phase === "verifying") text = t("modeles.pull.verifying");
        else {
          text = t("modeles.pull.downloading", {
            received: formatGb(pull.received / GB),
            total: formatGb(pull.total / GB),
            percent: formatPercent((100 * pull.received) / pull.total),
          });
        }
      }
      if (pull.stopping) text = `${text} · …`;
      if (node.label.textContent !== text) node.label.textContent = text;
      if (pull.phase === "preparing" || pull.phase === "verifying" || !pull.total) node.bar.removeAttribute("value");
      else {
        node.bar.max = pull.total;
        node.bar.value = pull.received;
      }
      node.cancel.setAttribute("aria-disabled", String(Boolean(pull.stopping)));
    }
  }

  function errorNode() {
    const { envelope, tag } = state.error;
    const box = document.createElement("wl-error");
    box.setAttribute("alert", "");
    box.error = envelope;
    box.addEventListener("wl-error-action", (event) => {
      if (event.detail.id === "retry") {
        state.error = null;
        install(tag);
      }
    });
    return box;
  }

  function sectionTitle(text, id) {
    const h2 = element("h2", "", text);
    h2.id = id;
    h2.tabIndex = -1;
    return h2;
  }

  function actionsBar() {
    const loaded = loadedTags();
    const bar = element("section", "mod-actions");
    bar.setAttribute("aria-label", t("modeles.actions.title"));

    // Décharger
    const unload = element("button", "btn", t("modeles.actions.unload"));
    unload.type = "button";
    unload.dataset.fid = "unload";
    const why = element("p", "help");
    why.id = "mod-unload-why";
    let reason = "";
    if (!ollamaUp) reason = t("modeles.actions.unload_ollama_down");
    else if (loaded && loaded.length === 0) reason = t("modeles.actions.unload_none");
    else if (loaded && loaded.every((tag) => inUse(tag))) reason = t("modeles.actions.unload_busy");
    why.textContent = reason;
    why.hidden = !reason;
    unload.setAttribute("aria-disabled", String(Boolean(reason)));
    if (reason) unload.setAttribute("aria-describedby", why.id);
    unload.addEventListener("click", () => {
      if (unload.getAttribute("aria-disabled") !== "true") unloadIdle();
    });
    const unloadBox = element("div", "mod-action");
    unloadBox.append(unload, why);

    // Installer par son nom
    const form = element("form", "mod-install");
    form.noValidate = true;
    const label = element("label", "mod-install-label", t("modeles.actions.install_label"));
    label.htmlFor = "mod-install-input";
    const input = element("input", "mod-install-input");
    input.id = "mod-install-input";
    input.type = "text";
    input.autocomplete = "off";
    input.spellcheck = false;
    input.value = draft;
    input.setAttribute("aria-describedby", "mod-install-help mod-install-why");
    input.addEventListener("input", () => {
      draft = input.value;
    });
    const help = element("p", "help", t("modeles.actions.install_help"));
    help.id = "mod-install-help";
    const submit = element("button", "btn btn-primary", t("modeles.actions.install"));
    submit.type = "submit";
    submit.dataset.fid = "install-free";
    const blocked = installBlockedReason();
    const installWhy = element("p", "help");
    installWhy.id = "mod-install-why";
    installWhy.textContent = blocked;
    installWhy.hidden = !blocked;
    submit.setAttribute("aria-disabled", String(Boolean(blocked)));
    const row = element("div", "mod-install-row");
    row.append(input, submit);
    form.append(label, row, help, installWhy);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (submit.getAttribute("aria-disabled") === "true") return;
      const tag = input.value.trim();
      if (!tag) {
        installWhy.textContent = t("modeles.actions.install_empty");
        installWhy.hidden = false;
        input.focus();
        return;
      }
      install(tag, { fromField: true });
    });
    const freeLine = element(
      "p",
      "help mod-free",
      t("modeles.actions.free", { free: formatGb(freeGb()), total: formatGb(store.get().system.memory?.total_gb ?? 15.7) }),
    );
    bar.append(unloadBox, form, freeLine);
    // Progression d'un nom saisi à la main (hors catalogue).
    const catalogTags = new Set(catalog.map((entry) => entry.tag));
    if (pullTarget(state.pull, catalogTags) === "free") bar.append(pullProgress("free"));
    if (state.error && state.error.target === "free") bar.append(errorNode());
    return bar;
  }

  function installedSection() {
    const section = element("section", "mod-section");
    section.setAttribute("aria-labelledby", "mod-installed-title");
    section.append(sectionTitle(t("modeles.installed.title"), "mod-installed-title"));
    if (installed.length === 0) {
      section.append(
        ctx.states.emptyState({
          title: t("modeles.installed.empty_title"),
          text: t("modeles.installed.empty_text"),
          level: 3,
          iconName: "deployed-code",
          action: {
            label: t("modeles.installed.empty_action"),
            primary: false,
            onClick: () => host.querySelector("#mod-catalog-title")?.focus(),
          },
        }),
      );
      return section;
    }
    const loaded = loadedTags();
    const columns = [
      {
        key: "name",
        label: t("modeles.installed.col_name"),
        sortValue: (m) => m.name,
        cell: (m) => {
          const link = element("a", "mod-name", m.name);
          link.href = `#/modeles/${encodeURIComponent(m.tag)}`;
          link.dataset.fid = `name:${m.tag}`;
          if (fixedTag === m.tag) link.setAttribute("aria-current", "page");
          const box = element("span", "mod-name-box");
          box.append(link, element("span", "mod-tag", m.tag));
          return box;
        },
      },
      {
        key: "origin",
        label: t("modeles.installed.col_origin"),
        cell: () => {
          const badge = document.createElement("wl-badge");
          badge.setAttribute("kind", "local");
          return badge;
        },
      },
      { key: "usage", label: t("modeles.installed.col_usage"), sortValue: (m) => data.usages[m.kind] ?? "", cell: (m) => data.usages[m.kind] ?? t("modeles.fiche.unknown") },
      { key: "params", label: t("modeles.installed.col_params"), numeric: true, sortValue: (m) => m.params_total_b, cell: (m) => paramsText(m) },
      { key: "size", label: t("modeles.installed.col_size"), numeric: true, sortValue: (m) => m.size_gb, cell: (m) => formatGb(m.size_gb) },
      {
        key: "fits",
        label: t("modeles.installed.col_fits"),
        sortValue: (m) => (m.fits === true ? 0 : m.fits === false ? 2 : 1),
        cell: (m) => {
          if (m.fits === true) return t("modeles.installed.fits_yes");
          if (m.fits === false) return t("modeles.installed.fits_no", { missing: formatGb(data.missing_gb[m.tag] ?? Math.max(0, m.needed_gb - freeGb())) });
          return t("modeles.fiche.unknown");
        },
      },
      {
        key: "loaded",
        label: t("modeles.installed.col_loaded"),
        sortValue: (m) => (loaded === null ? null : loaded.includes(m.tag) ? 1 : 0),
        cell: (m) => (loaded === null ? t("modeles.fiche.unknown") : loaded.includes(m.tag) ? t("modeles.installed.loaded_yes") : t("modeles.installed.loaded_no")),
      },
      {
        key: "rate",
        label: t("modeles.installed.col_rate"),
        numeric: true,
        sortValue: (m) => m.throughput_tps,
        cell: (m) => (m.throughput_tps == null ? t("modeles.installed.rate_none") : formatRate(m.throughput_tps)),
      },
      {
        key: "actions",
        label: t("modeles.installed.col_actions"),
        cell: (m) => {
          const box = element("span", "mod-cell-actions");
          const button = element("button", "btn", t("modeles.installed.delete"));
          button.type = "button";
          button.dataset.fid = `del:${m.tag}`;
          button.setAttribute("aria-label", t("modeles.installed.delete_aria", { name: m.name }));
          const used = inUse(m.tag);
          const disabled = used || !ollamaUp;
          button.setAttribute("aria-disabled", String(disabled));
          box.append(button);
          if (used) {
            const legend = element("span", "help", t("modeles.installed.in_use"));
            legend.id = `mod-use-${m.tag.replace(/\W/g, "-")}`;
            button.setAttribute("aria-describedby", legend.id);
            box.append(legend);
          }
          button.addEventListener("click", () => {
            if (button.getAttribute("aria-disabled") !== "true") deleteModel(m, button);
          });
          return box;
        },
      },
    ];
    const column = columns.find((candidate) => candidate.key === sortInstalled.key);
    const fallback = (a, b) => Number((loaded ?? []).includes(b.tag)) - Number((loaded ?? []).includes(a.tag)) || a.name.localeCompare(b.name, "fr-FR");
    section.append(
      buildTable({
        caption: t("modeles.installed.caption"),
        regionLabel: t("modeles.installed.region"),
        tableId: "installed",
        columns,
        rows: sortRows(installed, column, sortInstalled.dir, fallback),
        sort: sortInstalled,
        onSort: (key) => {
          sortInstalled = { key, dir: sortInstalled.key === key && sortInstalled.dir === "asc" ? "desc" : "asc" };
          render();
        },
        rowClass: (m) => (fixedTag === m.tag ? "is-current" : ""),
      }),
    );
    return section;
  }

  function defaultFor(purpose) {
    const chosen = state.defaults[purpose];
    if (chosen) return { tags: chosen.tags, reason: t("modeles.defaults.chosen"), chosen: true };
    return { ...autoDefaults[purpose], chosen: false };
  }

  function defaultsSection() {
    const section = element("section", "mod-section");
    section.setAttribute("aria-labelledby", "mod-defaults-title");
    section.append(sectionTitle(t("modeles.defaults.title"), "mod-defaults-title"));
    const rows = PURPOSES.map((purpose) => ({ purpose, ...defaultFor(purpose) }));
    const columns = [
      { key: "usage", label: t("modeles.defaults.col_usage"), cell: (row) => data.purposes[row.purpose] },
      {
        key: "model",
        label: t("modeles.defaults.col_model"),
        cell: (row) => {
          if (editing === row.purpose) return editor(row.purpose);
          const box = element("span", "mod-default-model");
          if (!row.tags.length) {
            box.append(element("span", "", t("modeles.defaults.none")));
            return box;
          }
          for (const tag of row.tags) {
            const model = modelIndex.get(tag);
            const item = element("span", "mod-default-item");
            item.append(element("span", "", model?.name ?? tag));
            const badge = document.createElement("wl-badge");
            badge.setAttribute("kind", model?.origin === "cloud" ? "cloud" : model ? "local" : "unknown");
            item.append(badge);
            box.append(item);
          }
          const cloud = row.tags.some((tag) => modelIndex.get(tag)?.origin === "cloud");
          if (cloud && !store.get().allowCloud) box.append(element("span", "help", t("modeles.defaults.cloud_inactive")));
          return box;
        },
      },
      { key: "reason", label: t("modeles.defaults.col_reason"), cell: (row) => element("span", "mod-reason", row.reason) },
      {
        key: "actions",
        label: t("modeles.defaults.col_actions"),
        cell: (row) => {
          const box = element("span", "mod-cell-actions");
          if (editing === row.purpose) {
            const save = element("button", "btn btn-primary", t("modeles.defaults.save"));
            save.type = "button";
            save.dataset.fid = `save:${row.purpose}`;
            save.addEventListener("click", () => saveDefault(row.purpose));
            const cancel = element("button", "btn", t("modeles.defaults.cancel"));
            cancel.type = "button";
            cancel.dataset.fid = `cancel-edit:${row.purpose}`;
            cancel.addEventListener("click", () => {
              editing = null;
              editMessage = null;
              render();
              host.querySelector(`[data-fid="change:${row.purpose}"]`)?.focus();
            });
            box.append(save, cancel);
            return box;
          }
          const change = element("button", "btn", t("modeles.defaults.change"));
          change.type = "button";
          change.dataset.fid = `change:${row.purpose}`;
          change.setAttribute("aria-label", t("modeles.defaults.change_aria", { usage: data.purposes[row.purpose] }));
          change.addEventListener("click", () => {
            editing = row.purpose;
            editMessage = null;
            render();
            host.querySelector(`[data-purpose-picker="${row.purpose}"] input`)?.focus();
          });
          box.append(change);
          if (row.chosen) {
            const revert = element("button", "btn", t("modeles.defaults.revert"));
            revert.type = "button";
            revert.dataset.fid = `revert:${row.purpose}`;
            revert.setAttribute("aria-label", t("modeles.defaults.revert_aria", { usage: data.purposes[row.purpose] }));
            revert.addEventListener("click", () => {
              delete state.defaults[row.purpose];
              state.result = { tone: "success", text: t("modeles.defaults.reverted", { usage: data.purposes[row.purpose] }) };
              render();
              host.querySelector(`[data-fid="change:${row.purpose}"]`)?.focus();
            });
            box.append(revert);
          }
          return box;
        },
      },
    ];
    section.append(
      buildTable({ caption: t("modeles.defaults.caption"), regionLabel: t("modeles.defaults.region"), tableId: "defaults", columns, rows }),
    );
    return section;
  }

  function editor(purpose) {
    const box = element("span", "mod-editor");
    box.dataset.purposePicker = purpose;
    const picker = document.createElement("wl-model-picker");
    picker.setAttribute("purpose", purpose === "arena" ? "chat" : purpose);
    picker.setAttribute("label", t("modeles.defaults.picker_label", { usage: data.purposes[purpose] }));
    const current = defaultFor(purpose).tags[0];
    if (current) picker.value = current;
    picker.addEventListener("wl-model-change", () => {
      editMessage = null;
      const note = box.querySelector(".mod-edit-message");
      if (note) note.hidden = true;
    });
    box.append(picker);
    const message = element("p", "wl-notice wl-notice-warning mod-edit-message");
    message.setAttribute("role", "alert");
    message.hidden = !editMessage;
    message.textContent = editMessage ?? "";
    box.append(message);
    box.picker = picker;
    return box;
  }

  function saveDefault(purpose) {
    const picker = host.querySelector(`[data-purpose-picker="${purpose}"] wl-model-picker`);
    const tag = picker?.value;
    const message = host.querySelector(`[data-purpose-picker="${purpose}"] .mod-edit-message`);
    const show = (text) => {
      editMessage = text;
      message.textContent = text;
      message.hidden = false;
    };
    if (!tag) return show(t("modeles.defaults.nothing_chosen"));
    const model = modelIndex.get(tag);
    if (purpose === "agent" && (!model?.tools_verified || (model?.params_active_b ?? 0) < 3)) {
      return show(t("modeles.defaults.not_eligible_agent", { name: model?.name ?? tag }));
    }
    if (purpose === "rag" && (model?.params_active_b ?? 0) < 3) {
      return show(t("modeles.defaults.not_eligible_rag", { name: model?.name ?? tag }));
    }
    state.defaults[purpose] = { tags: [tag], chosen: true };
    state.result = { tone: "success", text: t("modeles.defaults.saved", { usage: data.purposes[purpose], name: model?.name ?? tag }) };
    editing = null;
    editMessage = null;
    render();
    host.querySelector(`[data-fid="change:${purpose}"]`)?.focus();
  }

  function catalogSection() {
    const section = element("section", "mod-section");
    section.setAttribute("aria-labelledby", "mod-catalog-title");
    section.append(sectionTitle(t("modeles.catalog.title"), "mod-catalog-title"));
    if (catalog.length === 0) {
      section.append(element("p", "mod-empty", t("modeles.catalog.empty")));
      return section;
    }
    const free = freeGb();
    const blocked = installBlockedReason();
    const why = element("p", "help");
    why.id = "mod-catalog-why";
    why.textContent = blocked;
    why.hidden = !blocked;
    const catalogTags = new Set(catalog.map((entry) => entry.tag));
    const fits = (entry) => entry.needed_gb <= free;
    const columns = [
      {
        key: "name",
        label: t("modeles.catalog.col_name"),
        sortValue: (m) => m.name,
        cell: (m) => {
          const link = element("a", "mod-name", m.name);
          link.href = `#/modeles/${encodeURIComponent(m.tag)}`;
          link.dataset.fid = `cname:${m.tag}`;
          if (fixedTag === m.tag) link.setAttribute("aria-current", "page");
          const box = element("span", "mod-name-box");
          box.append(link, element("span", "mod-tag", m.tag));
          return box;
        },
      },
      { key: "params", label: t("modeles.catalog.col_params"), numeric: true, sortValue: (m) => m.params_total_b, cell: (m) => paramsText(m) },
      { key: "needed", label: t("modeles.catalog.col_needed"), numeric: true, sortValue: (m) => m.needed_gb, cell: (m) => formatGb(m.needed_gb) },
      {
        key: "fits",
        label: t("modeles.catalog.col_fits"),
        sortValue: (m) => (fits(m) ? 0 : 1),
        cell: (m) =>
          fits(m)
            ? t("modeles.catalog.fits_yes")
            : t("modeles.catalog.fits_no", { needed: formatGb(m.needed_gb), free: formatGb(free) }),
      },
      {
        key: "actions",
        label: t("modeles.catalog.col_actions"),
        cell: (m) => {
          if (pullTarget(state.pull, catalogTags) === `catalog:${m.tag}`) return pullProgress(`catalog:${m.tag}`);
          const button = element("button", "btn", t("modeles.catalog.install"));
          button.type = "button";
          button.dataset.fid = `install:${m.tag}`;
          button.setAttribute("aria-label", t("modeles.catalog.install_aria", { name: m.name }));
          const reason = installBlockedReason();
          button.setAttribute("aria-disabled", String(Boolean(reason)));
          if (reason) button.setAttribute("aria-describedby", "mod-catalog-why");
          button.addEventListener("click", () => {
            if (button.getAttribute("aria-disabled") !== "true") install(m.tag);
          });
          const box = element("span", "mod-cell-actions");
          box.append(button);
          return box;
        },
      },
    ];
    const column = columns.find((candidate) => candidate.key === sortCatalog.key);
    const fallback = (a, b) => Number(fits(b)) - Number(fits(a)) || a.needed_gb - b.needed_gb;
    section.append(
      why,
      buildTable({
        caption: t("modeles.catalog.caption"),
        regionLabel: t("modeles.catalog.region"),
        tableId: "catalog",
        columns,
        rows: sortRows(catalog, column, sortCatalog.dir, fallback),
        sort: sortCatalog,
        onSort: (key) => {
          sortCatalog = { key, dir: sortCatalog.key === key && sortCatalog.dir === "asc" ? "desc" : "asc" };
          render();
        },
        rowClass: (m) => (fixedTag === m.tag ? "is-current" : ""),
        extra: (m) => (state.error && state.error.target === `catalog:${m.tag}` ? errorNode() : null),
      }),
    );
    return section;
  }

  function rerankerSection() {
    const section = element("section", "mod-section mod-reranker");
    section.setAttribute("aria-labelledby", "mod-reranker-title");
    section.append(sectionTitle(t("modeles.reranker.title"), "mod-reranker-title"));
    const card = element("div", "mod-card");
    const stateLine = element("p", "mod-reranker-state");
    const running = state.pull?.reranker;
    if (state.rerankerInstalled) {
      stateLine.append(element("strong", "", t("modeles.reranker.state_installed")), ` · ${data.reranker.name}`);
      card.append(stateLine);
    } else {
      stateLine.append(element("strong", "", t("modeles.reranker.state_missing")));
      card.append(stateLine, richText("p", "help", data.reranker.not_installed_reason));
    }
    if (!state.rerankerInstalled) {
      if (running) card.append(pullProgress("reranker"));
      else {
        const button = element("button", "btn btn-primary", t("modeles.reranker.install"));
        button.type = "button";
        button.dataset.fid = "install-reranker";
        const legend = element("p", "help");
        legend.id = "mod-reranker-why";
        let reason = "";
        if (state.rerankerExtraMissing) reason = data.reranker.extra_missing_reason;
        else if (!ollamaUp) reason = t("modeles.actions.install_ollama_down");
        else if (state.pull) reason = t("modeles.reranker.busy", { tag: state.pull.tag });
        button.setAttribute("aria-disabled", String(Boolean(reason)));
        if (reason) {
          button.setAttribute("aria-describedby", legend.id);
          legend.replaceChildren(...richText("span", "", reason).childNodes);
        }
        legend.hidden = !reason;
        button.addEventListener("click", () => {
          if (button.getAttribute("aria-disabled") !== "true") installReranker();
        });
        card.append(button, legend);
      }
    }
    if (state.error && state.error.target === "reranker") card.append(errorNode());
    section.append(card);
    return section;
  }

  // --- Fiche du modèle -------------------------------------------------------------------------
  function ficheContent() {
    if (!fixedTag) return [];
    const model = installed.find((m) => m.tag === fixedTag) ?? catalog.find((m) => m.tag === fixedTag) ?? modelIndex.get(fixedTag);
    const close = element("a", "btn", t("modeles.fiche.close"));
    close.href = "#/modeles";
    if (!model) {
      return [
        ctx.states.emptyState({
          title: t("modeles.fiche.not_found_title"),
          text: t("modeles.fiche.not_found_text", { tag: fixedTag }),
          level: 2,
          action: { label: t("modeles.fiche.back"), href: "#/modeles", primary: false },
        }),
      ];
    }
    const isInstalled = installed.some((m) => m.tag === fixedTag);
    const facts = data.facts[fixedTag] ?? {};
    const parts = [];
    const head = element("div", "mod-fiche-head");
    const title = element("h2", "", model.name);
    title.id = "mod-fiche-title";
    title.tabIndex = -1;
    const badge = document.createElement("wl-badge");
    badge.setAttribute("kind", model.origin === "cloud" ? "cloud" : "local");
    head.append(title, badge);
    parts.push(head, element("p", "mod-tag", model.tag));
    if (!isInstalled) {
      const note = ctx.states.notice(t("modeles.fiche.not_installed"));
      parts.push(note);
      const button = element("button", "btn btn-primary", t("modeles.fiche.install_here"));
      button.type = "button";
      button.dataset.fid = "fiche-install";
      const reason = installBlockedReason();
      button.setAttribute("aria-disabled", String(Boolean(reason)));
      if (reason) {
        const legend = element("p", "help", reason);
        legend.id = "mod-fiche-why";
        button.setAttribute("aria-describedby", legend.id);
        parts.push(button, legend);
      } else parts.push(button);
      button.addEventListener("click", () => {
        if (button.getAttribute("aria-disabled") !== "true") install(model.tag);
      });
    }

    // Caractéristiques
    const unknown = t("modeles.fiche.unknown");
    const yesNo = (value) => (value === true ? t("modeles.fiche.yes") : value === false ? t("modeles.fiche.no") : unknown);
    const entries = [
      [t("modeles.fiche.arch"), facts.arch ? t(`modeles.fiche.arch_${facts.arch}`) : unknown],
      [t("modeles.fiche.params_total"), model.params_total_b == null ? unknown : `${formatNumber(model.params_total_b)} B`],
      [t("modeles.fiche.params_active"), model.params_active_b == null ? unknown : `${formatNumber(model.params_active_b)} B`],
      [t("modeles.fiche.quant"), facts.quant ?? unknown],
      [t("modeles.fiche.context"), facts.context == null ? unknown : t("modeles.fiche.context_value", { value: formatInteger(facts.context) })],
      [t("modeles.fiche.license"), facts.license ?? unknown],
      [t("modeles.fiche.tools"), yesNo(model.tools_verified)],
      [t("modeles.fiche.reasoning"), yesNo(model.reasoning)],
    ];
    const traits = element("h3", "", t("modeles.fiche.traits"));
    const dl = element("dl", "mod-dl");
    for (const [term, value] of entries) dl.append(element("dt", "", term), element("dd", "", value));
    parts.push(traits, dl);

    // Pourquoi ce débit ?
    const why = element("details", "mod-details");
    why.dataset.part = "why";
    why.append(element("summary", "", t("modeles.fiche.why_title")));
    const rate = model.throughput_tps;
    if (!isInstalled) why.append(element("p", "", t("modeles.fiche.why_not_installed")));
    else {
      why.append(element("p", "", rate == null ? t("modeles.fiche.why_none") : t("modeles.fiche.why_measured", { rate: formatRate(rate) })));
      if (rate != null && facts.why?.length) {
        const list = element("ul", "mod-why");
        for (const sentence of facts.why) list.append(element("li", "", sentence));
        why.append(list);
      } else why.append(element("p", "help", t("modeles.fiche.why_no_explanation")));
    }
    parts.push(why);

    // Sur d'autres postes
    const others = element("details", "mod-details");
    others.dataset.part = "others";
    others.append(element("summary", "", t("modeles.fiche.others_title")));
    const refs = data.references;
    const found = refs.results[fixedTag];
    if (state.noReferences) {
      others.append(element("p", "mod-strong", t("modeles.fiche.unavailable_title")), element("p", "", t("modeles.fiche.unavailable_reason")));
    } else if (!found) {
      others.append(element("p", "", t("modeles.fiche.not_published")));
    } else {
      if (found.digest_match === false) {
        others.append(
          ctx.states.notice(`${t("modeles.fiche.other_version")} : ${t("modeles.fiche.other_version_note")}`, { tone: "warning", role: null }),
        );
      }
      const machineName = (id) => refs.machines.find((machine) => machine.id === id)?.name ?? id;
      const columns = [
        { key: "machine", label: t("modeles.fiche.col_machine"), cell: (row) => machineName(row.machine) },
        { key: "rate", label: t("modeles.fiche.col_rate"), numeric: true, cell: (row) => (row.tps == null ? unknown : formatRate(row.tps)) },
        { key: "fits", label: t("modeles.fiche.col_fits"), numeric: true, cell: (row) => (row.fits_fraction == null ? unknown : formatPercent(row.fits_fraction * 100)) },
        {
          key: "energy",
          label: t("modeles.fiche.col_energy"),
          cell: (row) =>
            row.energy?.status === "measured"
              ? t("modeles.fiche.energy_value", { value: formatNumber(row.energy.wh_per_1k_tokens) })
              : t("modeles.fiche.energy_not_measured"),
        },
      ];
      others.append(
        buildTable({
          caption: t("modeles.fiche.others_caption", { name: model.name }),
          regionLabel: t("modeles.fiche.others_region"),
          tableId: "others",
          columns,
          rows: found.rows,
        }),
        element("p", "help", t("modeles.fiche.source", { source: refs.source })),
      );
    }
    parts.push(others, close);
    return parts;
  }

  // --- Rendu -----------------------------------------------------------------------------------
  function render() {
    if (!alive) return;
    const active = document.activeElement;
    const fid = active && host.contains(active) ? active.dataset?.fid : null;
    progressNodes = [];
    layout.dataset.fiche = fixedTag ? "true" : "false";
    fiche.hidden = !fixedTag;

    notices.replaceChildren();
    if (state.result) notices.append(ctx.states.notice(state.result.text, { tone: state.result.tone, role: null }));

    if (loadingForced) {
      main.replaceChildren(
        ctx.states.loading({ lines: 6, slowAfterMs: 1500, slowText: t("modeles.loading_slow") }),
      );
      fiche.replaceChildren();
      return;
    }
    const parts = [actionsBar()];
    if (store.get().maquette.ramGuard) parts.push(ctx.states.notice(t("modeles.ram_warning"), { tone: "warning" }));
    parts.push(installedSection(), defaultsSection(), catalogSection(), rerankerSection());
    main.replaceChildren(...parts);
    fiche.replaceChildren(...ficheContent());
    updateProgress();
    if (fid) host.querySelector(`[data-fid="${CSS.escape(fid)}"]`)?.focus();
  }

  // --- Actions ---------------------------------------------------------------------------------
  function say(tone, text) {
    state.result = { tone, text };
    ctx.announce(text);
  }

  function unloadIdle() {
    const loaded = loadedTags() ?? [];
    const idle = loaded.filter((tag) => !inUse(tag));
    if (!idle.length) return;
    for (const tag of idle) state.unloadedTags.add(tag);
    setMaquette({ ramGuard: false });
    state.result = { tone: "success", text: plural("modeles.actions.unloaded", idle.length, { count: formatInteger(idle.length) }) };
    ctx.announce(state.result.text);
    render();
    host.querySelector('[data-fid="unload"]')?.focus();
  }

  async function deleteModel(model, button) {
    state.result = null;
    state.error = null;
    const confirmed = await ctx.states.confirmAction({
      title: t("modeles.installed.delete_title", { tag: model.tag }),
      consequence: t("modeles.installed.delete_consequence", { tag: model.tag, size: formatGb(model.size_gb) }),
      confirmLabel: t("modeles.installed.delete_confirm"),
    });
    if (!alive) return;
    if (!confirmed) {
      button?.focus();
      return;
    }
    if (inUse(model.tag)) {
      // Un run a démarré entre-temps : 409, le modèle reste.
      state.error = { envelope: { ...data.errors.model_in_use, message: fill(data.errors.model_in_use.message, { name: model.name, tag: model.tag }), detail: data.errors.model_in_use.detail }, tag: model.tag, target: "free" };
      render();
      host.querySelector('[data-fid="unload"]')?.focus();
      return;
    }
    state.added = state.added.filter((m) => m.tag !== model.tag);
    state.deleted.add(model.tag);
    delete state.defaults[PURPOSES.find((purpose) => state.defaults[purpose]?.tags.includes(model.tag))];
    say("success", t("modeles.installed.deleted", { name: model.name, size: formatGb(model.size_gb) }));
    await schedule();
    host.querySelector("#mod-installed-title")?.focus();
  }

  function cancelPull() {
    const pull = state.pull;
    if (!pull || pull.stopping) return;
    pull.stopping = true;
    updateProgress();
    sim.cancel(pull.runId);
  }

  function resolveModel(tag) {
    const entry = catalog.find((candidate) => candidate.tag === tag) ?? modelIndex.get(tag);
    if (entry && entry.size_gb != null) return entry;
    if (data.registry_extra.includes(tag)) return { tag, name: tag, size_gb: 2.0, needed_gb: 2.8, kind: "chat", origin: "local", params_total_b: null, params_active_b: null, fits: null, throughput_tps: null, tools_verified: false, reasoning: false };
    return null;
  }

  function pullVars(model, extra = {}) {
    const total = Math.round((model?.size_gb ?? 2) * GB);
    const vars = { tag: model?.tag ?? extra.tag, reranker: extra.reranker ?? null, total_bytes: total, partial: false, error: null, ...extra };
    for (let i = 1; i <= 10; i += 1) vars[`b${i}`] = Math.round((total * i) / 10);
    return vars;
  }

  const handlers = {
    "*": (_data, envelope) => {
      if (state.pull) state.pull.lastSeq = envelope.seq;
    },
    pull_progress: (d) => {
      const pull = state.pull;
      if (!pull) return;
      pull.phase = d.phase;
      pull.received = d.received_bytes;
      pull.total = d.total_bytes;
      updateProgress();
    },
    run_ended: (d) => finishPull(d),
  };

  function follow(run) {
    attachment?.close();
    attachment = run.attach(handlers, { after: 0 });
  }

  function startPull({ tag, name, reranker = false, script, vars, speed }) {
    state.result = null;
    state.error = null;
    const run = sim.play(script, null, { vars, kind: "pull", origin: "local", module: "models", ...(speed ? { speed } : {}) });
    state.pull = { runId: run.id, tag, name, reranker, total: vars.total_bytes, received: 0, phase: "preparing", stopping: false, lastSeq: 0 };
    follow(run);
    render();
    return run;
  }

  // `fromField` : le nom vient de la saisie libre. Rend le run, ou null.
  function install(tag, { fromField = false, speed = null, script = null, vars: extraVars = {} } = {}) {
    if (!ollamaUp) return null;
    const other = sim.active("pull");
    if (other && (!state.pull || other.id !== state.pull.runId)) {
      // 409 run_busy : une installation tourne déjà (autre onglet) ; on la rejoint, sans erreur.
      const ovars = other.options.vars ?? {};
      state.result = null;
      state.error = null;
      state.pull = { runId: other.id, tag: ovars.tag, name: modelIndex.get(ovars.tag)?.name ?? ovars.tag, reranker: Boolean(ovars.reranker), total: ovars.total_bytes, received: 0, phase: "preparing", stopping: false, lastSeq: 0 };
      follow(other);
      render();
      notices.replaceChildren(ctx.states.joinedNotice());
      return other;
    }
    if (state.pull) return null;
    const model = resolveModel(tag);
    if (fromField) draft = "";
    if (installed.some((candidate) => candidate.tag === tag)) {
      say("info", t("modeles.pull.already", { name: modelIndex.get(tag)?.name ?? tag }));
      render();
      return null;
    }
    if (!model) {
      const error = { ...data.errors.pull_unknown, message: fill(data.errors.pull_unknown.message, { tag }) };
      state.pull = null;
      const vars = pullVars({ tag, size_gb: 1 }, { partial: false, error });
      const run = startPull({ tag, name: tag, script: "modeles-pull-echec", vars, speed });
      return run;
    }
    const vars = pullVars(model, extraVars);
    return startPull({ tag: model.tag, name: model.name, script: script ?? "modeles-pull", vars, speed });
  }

  function installReranker(options = {}) {
    if (!ollamaUp || state.pull || state.rerankerInstalled) return null;
    const model = { tag: data.reranker.name, name: t("modeles.reranker.name", { name: data.reranker.name }), size_gb: data.reranker.size_gb };
    const vars = pullVars(model, { reranker: data.reranker.name, ...(options.vars ?? {}) });
    return startPull({ tag: model.tag, name: model.name, reranker: true, script: options.script ?? "modeles-pull", vars, speed: options.speed });
  }

  function finishPull(d) {
    const pull = state.pull;
    if (!pull) return;
    attachment?.close();
    attachment = null;
    state.pull = null;
    const catalogTags = new Set(catalog.map((entry) => entry.tag));
    const target = pull.reranker ? "reranker" : catalogTags.has(pull.tag) ? `catalog:${pull.tag}` : "free";
    if (d.status === "ok") {
      if (pull.reranker) {
        state.rerankerInstalled = true;
        say("success", t("modeles.reranker.done"));
      } else {
        const model = resolveModel(pull.tag);
        if (model && !state.added.some((m) => m.tag === pull.tag)) {
          state.deleted.delete(pull.tag);
          state.added.push({ ...model, origin: "local", kind: "chat", provider: "ollama", available: true, fits: model.needed_gb <= freeGb(), throughput_tps: null });
        }
        say("success", t("modeles.pull.done", { name: pull.name }));
      }
    } else if (d.status === "cancelled") {
      say("info", t("modeles.pull.cancelled", { name: pull.name }));
    } else {
      const envelope = d.error?.code === "pull_failed" || d.error?.message ? d.error : { ...data.errors.pull_interrupted, message: fill(data.errors.pull_interrupted.message, { tag: pull.tag }) };
      state.error = { envelope, tag: pull.tag, target };
      ctx.announce(envelope.message);
    }
    schedule();
  }

  // --- Abonnements -----------------------------------------------------------------------------
  const key = () => {
    const s = store.get();
    return [
      s.allowCloud,
      s.maquette.ollamaDown,
      s.maquette.noLocalModel,
      s.maquette.ramGuard,
      s.system.modelsLoaded?.map((m) => m.tag).join(",") ?? "?",
      s.runsActive.filter((run) => run.kind !== "pull").map((run) => run.run_id).join(","),
    ].join("|");
  };
  let lastKey = key();
  const unsubscribe = store.subscribe(() => {
    const next = key();
    if (next === lastKey) return;
    lastKey = next;
    schedule();
  });

  // Écran masqué puis revu : le flux se détache et reprend là où il s'était arrêté.
  let wasHidden = host.hidden;
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      attachment?.close();
      attachment = null;
    } else if (state.pull) {
      const run = sim.get(state.pull.runId);
      if (run) follow(run);
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  view = {
    ready: false,
    tag: fixedTag,
    get state() {
      return state;
    },
    get pull() {
      return state.pull;
    },
    host,
    install,
    installReranker,
    cancelPull,
    unloadIdle,
    deleteModel: (tag) => {
      const model = installed.find((candidate) => candidate.tag === tag);
      return model ? deleteModel(model, null) : null;
    },
    settle: () => chain,
    render,
    refresh: schedule,
    setLoading(on) {
      loadingForced = on;
      render();
    },
    edit(purpose) {
      editing = purpose;
      render();
    },
    setNoReferences(on) {
      state.noReferences = on;
      render();
    },
    openPart(part) {
      const details = host.querySelector(`details[data-part="${part}"]`);
      if (details) details.open = true;
    },
    get installedTags() {
      return installed.map((model) => model.tag);
    },
    get catalogTags() {
      return catalog.map((entry) => entry.tag);
    },
    closeDialog() {
      document.querySelector("wl-confirm-dialog .btn-primary")?.click();
    },
  };

  // Reprise : un run `pull` encore actif (ou fini pendant que l'écran était fermé) est suivi à nouveau.
  await refresh();
  if (state.pull) {
    const run = sim.get(state.pull.runId);
    if (run) follow(run);
    else state.pull = null;
  } else {
    const other = sim.active("pull");
    if (other) {
      const ovars = other.options.vars ?? {};
      state.pull = { runId: other.id, tag: ovars.tag, name: modelIndex.get(ovars.tag)?.name ?? ovars.tag, reranker: Boolean(ovars.reranker), total: ovars.total_bytes, received: 0, phase: "preparing", stopping: false, lastSeq: 0 };
      follow(other);
    }
  }
  render();
  view.ready = true;

  return () => {
    alive = false;
    view = null;
    unsubscribe();
    visibility.disconnect();
    guard.dispose?.();
    attachment?.close();
  };
}

// --- Scénarios ----------------------------------------------------------------------------------

const speedOf = () => store.get().maquette.speed || 1;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms / speedOf()));

function waitUntil(condition, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    const started = performance.now();
    const check = () => {
      if (condition()) return resolve();
      if (performance.now() - started > timeoutMs) return reject(new Error("Scénario : état jamais atteint"));
      setTimeout(check, 30);
    };
    check();
  });
}

async function fresh(ctx, setup = () => {}) {
  // Un dialogue laissé ouvert par le scénario précédent est fermé (Annuler).
  document.querySelector("wl-confirm-dialog dialog[open] .btn:not(.btn-primary)")?.click();
  await ctx.reset();
  await waitUntil(() => view !== null && view.ready && ctx.store.get().systemSeen);
  setup();
  await view.settle();
  await view.refresh();
  await pause(60);
}

// Ouvre la fiche de `tag` (route `fiche-modele`) après avoir préparé l'état.
async function openFiche(ctx, tag, setup = () => {}, part = null) {
  await fresh(ctx, setup);
  await ctx.navigate(`/modeles/${encodeURIComponent(tag)}`);
  await waitUntil(() => view !== null && view.ready && view.tag === tag);
  await view.settle();
  if (part) view.openPart(part);
  await pause(60);
}

const untilProgress = (fraction) =>
  waitUntil(() => view.pull && view.pull.phase === "downloading" && view.pull.received / view.pull.total >= fraction);
const untilIdle = () => waitUntil(() => view.pull === null);

// Une réponse de chat lente qui occupe qwen3.5:2b (supprimer impossible, décharger inutile).
function startBusyChat(tag = "qwen3.5:2b") {
  return sim.play("chat-libre-reponse", null, {
    kind: "chat",
    module: "chat",
    origin: "local",
    speed: 1,
    vars: {
      tag,
      temperature: 0.7,
      loading: false,
      load_s: null,
      thought: "",
      answer: "Une réponse volontairement lente, pour que le modèle reste occupé le temps de la démonstration. ".repeat(10),
      partial: "",
      tps: 2,
      metrics: { lane: tag },
    },
  });
}

export const scenarios = [
  {
    id: "nominal",
    label: "Poste prêt : modèles installés, défauts, catalogue installable, reranker non installé",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "premier-chargement",
    label: "Premier chargement lent de la liste : squelette puis message d'attente",
    async run(ctx) {
      await fresh(ctx);
      view.setLoading(true);
      await waitUntil(() => view.host.querySelector(".wl-skeleton-slow:not([hidden])"));
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle installé : état vide et renvoi vers le catalogue",
    run: (ctx) => fresh(ctx, () => setMaquette({ noLocalModel: true })),
  },
  {
    id: "ollama-arrete",
    label: "Ollama arrêté : bandeau, actions désactivées avec leur raison",
    run: (ctx) => fresh(ctx, () => ctx.system.setOllamaDown(true)),
  },
  {
    id: "garde-fou-memoire",
    label: "Mémoire presque pleine : catalogue qui ne tient plus, « Décharger » proposé",
    run: (ctx) => fresh(ctx, () => setMaquette({ ramGuard: true })),
  },
  {
    id: "installation-en-cours",
    label: "Installation en cours : « Téléchargement 1,2 Go sur 4,9 Go · 26 % » et Annuler",
    async run(ctx) {
      await fresh(ctx);
      view.install("granite4.1:8b", { speed: 1 });
      await untilProgress(0.3);
    },
  },
  {
    id: "installation-terminee",
    label: "Installation terminée : « Installé », le modèle rejoint « Sur ce poste »",
    async run(ctx) {
      await fresh(ctx);
      view.install("granite4.1:8b");
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "installation-annulee",
    label: "Annuler l'installation : liste inchangée",
    async run(ctx) {
      await fresh(ctx);
      view.install("granite4.1:8b", { speed: 1 });
      await untilProgress(0.2);
      view.cancelPull();
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "installation-echec-tag",
    label: "Nom inexistant : pull_failed, liste inchangée",
    async run(ctx) {
      await fresh(ctx);
      view.install("qwen9:1b", { fromField: true });
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "installation-echec-ollama",
    label: "Ollama s'arrête pendant le téléchargement : pull_failed dans la ligne",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("modeles.json");
      const envelope = { ...data.errors.pull_ollama_stopped, message: data.errors.pull_ollama_stopped.message.replace("{tag}", "granite4.1:8b") };
      view.install("granite4.1:8b", { script: "modeles-pull-echec", vars: { partial: true, error: envelope } });
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "installation-connexion-perdue",
    label: "Connexion perdue pendant le téléchargement, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const run = view.install("granite4.1:8b", { speed: 2 });
      await untilProgress(0.2);
      run.cut(3000);
      await pause(1200);
      await untilIdle();
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant l'installation : « interrompue »",
    async run(ctx) {
      await fresh(ctx);
      view.install("granite4.1:8b", { speed: 2 });
      await untilProgress(0.2);
      sim.restartServer();
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "rejoint-409",
    label: "Une installation tourne déjà (autre onglet) : 409 rejoint sans erreur",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("modeles.json");
      const other = data.catalog.find((entry) => entry.tag === "llama4.2:3b");
      const total = Math.round(other.size_gb * 1e9);
      const vars = { tag: other.tag, reranker: null, total_bytes: total, partial: false, error: null };
      for (let i = 1; i <= 10; i += 1) vars[`b${i}`] = Math.round((total * i) / 10);
      sim.play("modeles-pull", null, { vars, kind: "pull", origin: "local", module: "models", speed: 1 });
      await pause(300);
      view.install("gemma4:4b");
      await untilProgress(0.1);
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant l'installation, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      view.install("granite4.1:8b", { speed: 2 });
      await untilProgress(0.2);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/modeles");
      await waitUntil(() => view !== null && view.ready);
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "decharger",
    label: "Décharger les modèles inactifs : annonce et mémoire libre mise à jour",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ ramGuard: true }));
      view.unloadIdle();
      await view.settle();
    },
  },
  {
    id: "decharger-rien",
    label: "Aucun modèle chargé : « Décharger » désactivé avec sa raison",
    run: (ctx) => fresh(ctx, () => view.state.unloadedTags.add("qwen3.5:2b")),
  },
  {
    id: "modele-utilise",
    label: "Un modèle sert à une réponse en cours : Supprimer désactivé, légende visible",
    async run(ctx) {
      await fresh(ctx);
      startBusyChat();
      await pause(200);
      view.render();
    },
  },
  {
    id: "supprimer-confirmation",
    label: "Supprimer : dialogue chiffré, focus sur « Annuler »",
    async run(ctx) {
      await fresh(ctx);
      view.deleteModel("qwen3.5:2b");
      await waitUntil(() => document.querySelector("wl-confirm-dialog dialog[open]"));
    },
  },
  {
    id: "supprimer-fait",
    label: "Supprimer confirmé : « Modèle supprimé », le modèle réapparaît au catalogue",
    async run(ctx) {
      await fresh(ctx);
      const done = view.deleteModel("qwen3.5:2b");
      await waitUntil(() => document.querySelector("wl-confirm-dialog dialog[open]"));
      view.closeDialog();
      await done;
      await view.settle();
    },
  },
  {
    id: "suppression-conflit-409",
    label: "Un run démarre pendant le dialogue : 409, le modèle n'est pas supprimé",
    async run(ctx) {
      await fresh(ctx);
      const done = view.deleteModel("qwen3.5:2b");
      await waitUntil(() => document.querySelector("wl-confirm-dialog dialog[open]"));
      startBusyChat();
      view.closeDialog();
      await done;
      await view.settle();
    },
  },
  {
    id: "defaut-changer",
    label: "Changer le modèle par défaut d'un usage : sélecteur, Enregistrer, Annuler",
    async run(ctx) {
      await fresh(ctx);
      view.edit("agent");
      await pause(100);
    },
  },
  {
    id: "defaut-choisi",
    label: "Défaut choisi : raison « Choisi par vous » et « Revenir au choix automatique »",
    async run(ctx) {
      await fresh(ctx, () => {
        view.state.defaults.judge = { tags: ["lfm2.5:8b-a1b"], chosen: true };
      });
    },
  },
  {
    id: "defaut-cloud-inactif",
    label: "Défaut cloud choisi, cloud désactivé : « inactif tant que le cloud n'est pas autorisé »",
    async run(ctx) {
      await fresh(ctx, () => {
        view.state.defaults.chat = { tags: ["gpt-5-mini"], chosen: true };
      });
    },
  },
  {
    id: "defaut-cloud-actif",
    label: "Défaut cloud choisi, cloud autorisé : plus de mention d'inactivité",
    async run(ctx) {
      await fresh(ctx, () => {
        view.state.defaults.chat = { tags: ["gpt-5-mini"], chosen: true };
        ctx.store.set({ allowCloud: true });
      });
    },
  },
  {
    id: "defaut-aucun-agent",
    label: "Aucun modèle éligible pour l'usage Agent : « Aucun » et les conditions",
    async run(ctx) {
      await fresh(ctx, () => {
        view.state.noAgent = true;
      });
    },
  },
  {
    id: "reranker-installation",
    label: "Installer le reranker : progression chiffrée, puis « Installé »",
    async run(ctx) {
      await fresh(ctx);
      view.installReranker({ speed: 1 });
      await untilProgress(0.3);
    },
  },
  {
    id: "reranker-installe",
    label: "Reranker installé : la recherche reclasse les extraits",
    async run(ctx) {
      await fresh(ctx);
      view.installReranker();
      await untilIdle();
      await view.settle();
    },
  },
  {
    id: "reranker-option-absente",
    label: "Option de reclassement absente : bouton désactivé, `uv sync --extra rerank`",
    run: (ctx) => fresh(ctx, () => (view.state.rerankerExtraMissing = true)),
  },
  {
    id: "fiche-modele",
    label: "Fiche d'un modèle installé (la liste reste visible)",
    run: (ctx) => openFiche(ctx, "qwen3.5:2b"),
  },
  {
    id: "fiche-pourquoi-debit",
    label: "Fiche : « Pourquoi ce débit ? » déplié",
    run: (ctx) => openFiche(ctx, "lfm2.5:8b-a1b", () => {}, "why"),
  },
  {
    id: "fiche-autres-postes",
    label: "Fiche : « Sur d'autres postes » (trois postes, énergie si mesurée, null = inconnu)",
    run: (ctx) => openFiche(ctx, "qwen3.6:14b", () => {}, "others"),
  },
  {
    id: "fiche-autre-version",
    label: "Fiche : mesures publiées pour « autre version » du modèle",
    run: (ctx) => openFiche(ctx, "lfm2.5:8b-a1b", () => {}, "others"),
  },
  {
    id: "fiche-valeurs-inconnues",
    label: "Fiche d'un modèle du catalogue : contexte et licence « inconnu », jamais 0",
    run: (ctx) => openFiche(ctx, "granite4.1:8b"),
  },
  {
    id: "fiche-non-installee",
    label: "Fiche d'un modèle non installé : débit non mesuré, « Installer ce modèle »",
    run: (ctx) => openFiche(ctx, "gemma4:4b", () => {}, "why"),
  },
  {
    id: "fiche-references-indisponibles",
    label: "Références du banc indisponibles : la raison, sans tableau vide",
    run: (ctx) => openFiche(ctx, "qwen3.5:2b", () => (view.state.noReferences = true), "others"),
  },
  {
    id: "fiche-introuvable",
    label: "Adresse d'un modèle inconnu : « Modèle introuvable » et retour à la liste",
    run: (ctx) => openFiche(ctx, "modele-inconnu:9b"),
  },
];
