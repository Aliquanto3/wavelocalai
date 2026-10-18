// Sobriété et matériel, `#/sobriete` (UX-DR26, story 5.1 et 5.2, EXPERIENCE.md « Sobriété et matériel »).
// Écran à l'état livré, branché sur le store du simulateur (flux système, CO₂ de session).
//
// - « Santé du système » : quatre métriques en direct (processeur, mémoire, accélérateur, Ollama),
//   squelettes au premier chargement, pause quand l'onglet est masqué, « inconnu » si la connexion
//   est perdue. « Aucun » accélérateur tant qu'aucun n'est détecté ; bridage thermique dit en texte.
// - « Empreinte carbone de cette session » : total, par module, Local / Cloud (estimé), réponses non
//   mesurables à part (lien vers la méthode). Une seule unité dans toute la section (UX-DR15).
//   « Remettre le compteur à zéro » sans confirmation : la session close rejoint l'historique.
// - « Historique » : 7 jours / 30 jours / Tout, Graphique (barres SVG par session, trous de mesure
//   visibles) ou Tableau triable au clavier. Sans historique : « Aucune session mesurée pour l'instant. ».
// - Carte d'identité technique et « Comment ces chiffres sont calculés », repliées.
// Le front ne calcule aucune mesure (AD-20) : il met en forme ce que le simulateur publie. Les sommes
// de la session viennent de `store.carbon` ; l'historique est lu dans donnees/sobriete.json.

import { dataTable, sortRows } from "../components/data-table.js";
import { segments } from "../components/segments.js";
import { element, icon } from "../core/dom.js";
import { co2Group, formatCo2, formatDate, formatGb, formatInteger, formatNumber, formatPercent, formatTime } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { setMaquette, store } from "../core/store.js";
import { loseConnection, recheck, recordLeaf, resetCarbon, setOllamaDown } from "../sim/systeme.js";

const NBSP = " ";
const SVG_NS = "http://www.w3.org/2000/svg";
const DAY_MS = 86_400_000;

let view = null; // l'instance montée, pour les scénarios
let hardwareMode = "present"; // present | none | throttled : le GPU n'est pas dans le flux simulé
let counter = 0;

// « Réinitialiser la maquette » (panneau) remet aussi le matériel simulé à son état d'ouverture.
function hookReset() {
  const api = window.__maquette;
  if (!api || api.__sobrieteHook) return;
  const original = api.reset.bind(api);
  api.reset = async () => {
    hardwareMode = "present";
    return original();
  };
  api.__sobrieteHook = true;
}

const dayMonth = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit" });

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

function setAttr(node, name, value) {
  if (node.getAttribute(name) !== value) node.setAttribute(name, value);
}

function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

// --- Santé du système ---------------------------------------------------------------------

function metricCard(id, label, help) {
  const root = element("article", "sob-card");
  root.dataset.card = id;
  const metric = document.createElement("wl-metric");
  metric.setAttribute("label", label);
  if (help) metric.setAttribute("help", help);
  const bar = element("span", "sob-skeleton");
  bar.append(element("span", "sr-only", t("sobriete.loading")));
  const detail = element("div", "sob-card-detail");
  root.append(metric, bar, detail);
  return { root, metric, bar, detail };
}

function buildHealth() {
  const cpu = metricCard("cpu", t("sobriete.health.cpu_label"), t("sobriete.health.cpu_help"));

  const memory = metricCard("memory", t("sobriete.health.memory_label"), t("sobriete.health.memory_help"));
  memory.free = element("p", "sob-line sob-hint");
  memory.detail.append(memory.free);

  const gpu = metricCard("accelerator", t("sobriete.health.accelerator_label"), t("sobriete.health.accelerator_help"));
  gpu.name = element("p", "sob-line");
  gpu.temperature = element("p", "sob-line");
  gpu.throttled = element("p", "sob-line sob-warn");
  gpu.throttled.append(icon("warning"), element("span", "", t("sobriete.health.throttled")));
  gpu.none = element("p", "sob-line sob-hint", t("sobriete.health.accelerator_none_line"));
  gpu.detail.append(gpu.name, gpu.temperature, gpu.throttled, gpu.none);

  const ollama = metricCard("ollama", t("sobriete.health.ollama_label"), t("sobriete.health.ollama_help"));
  ollama.hint = element("p", "sob-line sob-hint", t("sobriete.health.ollama_down_hint"));
  ollama.retry = element("button", "btn", t("sobriete.health.ollama_retry"));
  ollama.retry.type = "button";
  ollama.retry.setAttribute("aria-disabled", "false");
  ollama.retry.addEventListener("click", () => {
    if (ollama.retry.getAttribute("aria-disabled") !== "true") recheck();
  });
  ollama.version = element("p", "sob-line sob-hint");
  ollama.detail.append(ollama.version, ollama.hint, ollama.retry);

  const grid = element("div", "sob-cards");
  grid.append(cpu.root, memory.root, gpu.root, ollama.root);
  return { grid, cpu, memory, gpu, ollama };
}

function setBusy(card, busy) {
  setAttr(card.root, "aria-busy", String(busy));
  card.bar.hidden = !busy;
}

function gpuSnapshot(data, state) {
  if (hardwareMode === "none") return null;
  const loaded = state.system.modelsLoaded;
  const used = Array.isArray(loaded) && loaded.length === 0 ? 0.3 : data.gpu.vram_used_gb;
  const throttled = hardwareMode === "throttled";
  return { name: data.gpu.name, used, total: data.gpu.vram_total_gb, temperature: throttled ? 84 : data.gpu.temperature_c, throttled };
}

function renderHealth(health, data, state, forced) {
  const lost = state.connection.status === "lost";
  const waiting = forced === "loading" || (!state.systemSeen && !lost);
  const unknown = t("sobriete.health.unknown");
  const pick = (card, value) => {
    setBusy(card, waiting);
    setAttr(card.metric, "value", waiting ? "" : lost ? unknown : value);
  };

  pick(health.cpu, formatPercent(state.system.cpuPercent));

  const memory = state.system.memory;
  pick(health.memory, memory ? `${formatNumber(memory.used_gb)} / ${formatGb(memory.total_gb)}` : unknown);
  setText(
    health.memory.free,
    waiting || lost || !memory ? "" : t("sobriete.health.memory_free", { value: formatGb(Math.max(0, memory.total_gb - memory.used_gb)) }),
  );

  const gpu = gpuSnapshot(data, state);
  const showGpu = !waiting && !lost && gpu !== null;
  pick(health.gpu, gpu ? `${formatNumber(gpu.used)} / ${formatGb(gpu.total)}` : t("sobriete.health.accelerator_none"));
  setText(health.gpu.name, showGpu ? gpu.name : "");
  setText(health.gpu.temperature, showGpu ? `${formatInteger(gpu.temperature)}${NBSP}°C` : "");
  health.gpu.throttled.hidden = !(showGpu && gpu.throttled);
  health.gpu.none.hidden = waiting || lost || gpu !== null;

  // Ollama
  const down = !state.ollama.up && state.ollama.known;
  const models = state.system.modelsLoaded;
  let value = unknown;
  let help = t("sobriete.health.ollama_help");
  if (down) value = t("sobriete.health.ollama_down");
  else if (Array.isArray(models)) {
    value = models.length === 0 ? t("sobriete.health.ollama_none") : plural("sobriete.health.ollama_loaded", models.length, { count: formatInteger(models.length) });
    if (models.length) {
      const names = models.map((model) => `${model.tag} (${formatGb(model.size_gb)})`).join(", ");
      help = `${t("sobriete.health.ollama_help")} ${plural("sobriete.health.ollama_names", models.length, { names })}`;
    }
  }
  pick(health.ollama, value);
  setAttr(health.ollama.metric, "help", help);
  const showDown = !waiting && !lost && down;
  health.ollama.hint.hidden = !showDown;
  health.ollama.retry.hidden = !showDown;
  if (!showDown && document.activeElement === health.ollama.retry) {
    health.ollama.root.tabIndex = -1;
    health.ollama.root.focus();
  }
  setAttr(health.ollama.retry, "aria-disabled", String(state.ollamaChecking));
  setText(health.ollama.retry, state.ollamaChecking ? t("sobriete.health.ollama_retrying") : t("sobriete.health.ollama_retry"));
  setText(health.ollama.version, !waiting && !lost && !down && state.ollama.version ? t("sobriete.health.ollama_version", { version: state.ollama.version }) : "");
}

// --- Empreinte carbone --------------------------------------------------------------------

function buildCarbon(ctx) {
  const total = document.createElement("wl-metric");
  total.setAttribute("label", t("sobriete.carbon.total_label"));
  total.setAttribute("help", t("sobriete.carbon.total_help"));
  const bar = element("span", "sob-skeleton");
  bar.append(element("span", "sr-only", t("sobriete.loading")));
  const empty = ctx.states.emptyState({
    title: t("sobriete.carbon.empty_title"),
    text: t("sobriete.carbon.empty_text"),
    level: 3,
    iconName: "eco",
  });
  const onlyUnmeasurable = ctx.states.notice(t("sobriete.carbon.only_unmeasurable"));
  const byModule = element("p", "sob-line");
  const origin = element("p", "sob-line");
  const originText = element("span");
  const methodLink = element("button", "link-button");
  methodLink.type = "button";
  methodLink.setAttribute("aria-controls", "sob-method");
  const unmeasurableNone = element("span");
  origin.append(originText, " · ", methodLink, unmeasurableNone);
  const content = element("div", "sob-carbon-content");
  content.append(total, byModule, origin);

  const reset = element("button", "btn", t("sobriete.carbon.reset"));
  reset.type = "button";
  const resetWhy = element("p", "help");
  resetWhy.id = "sob-reset-why";
  reset.setAttribute("aria-describedby", resetWhy.id);
  const notices = element("div", "sob-notices");
  const actions = element("div", "sob-carbon-actions");
  actions.append(reset, resetWhy);

  const box = element("div", "sob-carbon");
  box.append(bar, empty, onlyUnmeasurable, content, notices);
  return { box, bar, empty, onlyUnmeasurable, content, total, byModule, origin, originText, methodLink, unmeasurableNone, reset, resetWhy, notices, actions };
}

function renderCarbon(carbon, data, state, forced) {
  const waiting = forced === "loading" || !state.carbon;
  carbon.bar.hidden = !waiting;
  setAttr(carbon.box, "aria-busy", String(waiting));
  const c = state.carbon;
  if (waiting || !c) {
    carbon.empty.hidden = true;
    carbon.onlyUnmeasurable.hidden = true;
    carbon.content.hidden = true;
    carbon.reset.disabled = true;
    setText(carbon.resetWhy, t("sobriete.loading"));
    return;
  }
  const measured = c.measured_runs > 0;
  const unmeasurable = c.unmeasurable_runs ?? 0;
  carbon.empty.hidden = measured || unmeasurable > 0;
  carbon.onlyUnmeasurable.hidden = measured || unmeasurable === 0;
  carbon.content.hidden = !measured && unmeasurable === 0;

  const modules = Object.entries(c.by_module ?? {}).filter(([, value]) => value.mg > 0);
  const local = c.by_origin?.local;
  const cloud = c.by_origin?.cloud;
  const group = co2Group([c.total_mg, local?.mg, cloud?.mg, ...modules.map(([, value]) => value.mg)]);

  carbon.total.hidden = !measured;
  if (measured) setAttr(carbon.total, "value", group.format(c.total_mg));
  carbon.byModule.hidden = !measured || modules.length === 0;
  setText(
    carbon.byModule,
    `${t("sobriete.carbon.by_module")} : ${modules.map(([id, value]) => `${data.modules[id] ?? id} ${group.format(value.mg)}`).join(" · ")}`,
  );

  const originParts = [];
  if (measured) {
    originParts.push(local?.runs ? t("sobriete.carbon.local", { value: group.format(local.mg) }) : t("sobriete.carbon.local_none"));
    originParts.push(cloud?.runs ? t("sobriete.carbon.cloud", { value: group.format(cloud.mg) }) : t("sobriete.carbon.cloud_none"));
  }
  setText(carbon.originText, originParts.join(" · "));
  // La séparation « · » ne précède le compte des non mesurables que s'il y a quelque chose avant.
  carbon.origin.childNodes[1].textContent = originParts.length ? " · " : "";
  if (unmeasurable > 0) {
    carbon.methodLink.hidden = false;
    carbon.unmeasurableNone.hidden = true;
    setText(carbon.methodLink, `${plural("sobriete.carbon.unmeasurable", unmeasurable, { count: formatInteger(unmeasurable) })} ${plural("sobriete.carbon.unmeasurable_suffix", unmeasurable)}`);
  } else {
    carbon.methodLink.hidden = true;
    carbon.unmeasurableNone.hidden = false;
    setText(carbon.unmeasurableNone, t("sobriete.carbon.unmeasurable_none"));
  }

  const nothing = !measured && unmeasurable === 0;
  carbon.reset.disabled = nothing;
  setText(carbon.resetWhy, nothing ? t("sobriete.carbon.reset_nothing") : "");
}

// --- Historique ---------------------------------------------------------------------------

function niceStep(max) {
  const raw = max / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const factor of [1, 2, 5, 10]) if (raw <= factor * power) return factor * power;
  return 10 * power;
}

function sessionLabel(session) {
  return dayMonth.format(new Date(session.start));
}

function buildChart(sessions) {
  const step = 52;
  const left = 64;
  const top = 36;
  const plotHeight = 190;
  const bottom = 56;
  const width = Math.max(left + sessions.length * step + 16, 420);
  const height = top + plotHeight + bottom;
  const max = Math.max(1, ...sessions.map((session) => session.total_mg ?? 0));
  const tick = niceStep(max);
  const ceiling = Math.ceil(max / tick) * tick;
  const y = (value) => top + plotHeight - (value / ceiling) * plotHeight;

  const id = `sob-chart-${++counter}`;
  const root = svg("svg", { class: "sob-chart", viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-labelledby": `${id}-title ${id}-desc` });
  root.append(svg("title", { id: `${id}-title` }, t("sobriete.history.chart_title")), svg("desc", { id: `${id}-desc` }, t("sobriete.history.chart_desc")));
  root.append(svg("text", { class: "sob-axis-title", x: 0, y: 14 }, t("sobriete.history.axis_y")));
  for (let value = 0; value <= ceiling; value += tick) {
    root.append(svg("line", { class: "sob-grid", x1: left, x2: width - 8, y1: y(value), y2: y(value) }));
    root.append(svg("text", { class: "sob-tick", x: left - 8, y: y(value) + 4, "text-anchor": "end" }, formatInteger(value)));
  }
  sessions.forEach((session, index) => {
    const x = left + index * step + 8;
    const barWidth = step - 16;
    const label = svg("text", { class: "sob-tick", x: x + barWidth / 2, y: top + plotHeight + 18, "text-anchor": "middle" }, sessionLabel(session));
    root.append(label);
    if (session.total_mg === null) {
      root.append(svg("line", { class: "sob-gap", x1: x, x2: x + barWidth, y1: y(0) - 1, y2: y(0) - 1 }));
      const cx = x + barWidth / 2 + 4;
      root.append(svg("text", { class: "sob-tick", x: cx, y: y(0) - 8, transform: `rotate(-90 ${cx} ${y(0) - 8})` }, t("sobriete.history.unmeasured")));
      return;
    }
    const barTop = y(session.total_mg);
    root.append(svg("rect", { class: "sob-bar", x, y: barTop, width: barWidth, height: Math.max(1, y(0) - barTop), rx: 3 }));
    root.append(svg("text", { class: "sob-value", x: x + barWidth / 2, y: barTop - 6, "text-anchor": "middle" }, formatNumber(session.total_mg)));
  });
  root.append(svg("text", { class: "sob-axis-title", x: left, y: height - 6 }, t("sobriete.history.axis_x")));
  return root;
}

function dateCell(iso) {
  const time = element("time", "", `${formatDate(iso)} ${formatTime(iso)}`);
  time.dateTime = iso;
  return time;
}

const mgOrGap = (value) => (value === null ? t("sobriete.history.not_measured") : formatCo2(value, { unit: "mg" }));

const COLUMNS = [
  { key: "start", label: "col_start", sort: (s) => Date.parse(s.start), cell: (s) => dateCell(s.start) },
  { key: "end", label: "col_end", sort: (s) => Date.parse(s.end), cell: (s) => dateCell(s.end) },
  { key: "total", label: "col_total", numeric: true, sort: (s) => s.total_mg, cell: (s) => mgOrGap(s.total_mg) },
  { key: "local", label: "col_local", numeric: true, sort: (s) => s.local_mg, cell: (s) => mgOrGap(s.local_mg) },
  {
    key: "cloud",
    label: "col_cloud",
    numeric: true,
    sort: (s) => s.cloud_mg,
    cell: (s) => (s.cloud_mg === null ? t("sobriete.history.not_measured") : s.cloud_mg === 0 ? t("sobriete.history.no_cloud") : formatCo2(s.cloud_mg, { unit: "mg" })),
  },
  { key: "unmeasurable", label: "col_unmeasurable", numeric: true, sort: (s) => s.unmeasurable, cell: (s) => formatInteger(s.unmeasurable) },
];

// Tableau de l'historique (composant commun) : l'écran garde le tri, une date se trie d'abord par la
// plus récente.
function buildTable(sessions, sort, onSort) {
  const columns = COLUMNS.map((column) => ({ ...column, label: t(`sobriete.history.${column.label}`), value: column.sort }));
  return dataTable({
    caption: t("sobriete.history.table_caption"),
    regionLabel: t("sobriete.history.table_region"),
    columns,
    rows: sortRows(sessions, columns, sort),
    sort,
    onSort,
    className: "sob",
  });
}

// --- Écran --------------------------------------------------------------------------------

export async function mount(host, ctx) {
  hookReset();
  const data = await ctx.data("sobriete.json");
  let history = structuredClone(data.history);
  const now = Date.parse(data.now);

  let forced = null; // « loading » : squelettes forcés par un scénario
  let windowId = "w7";
  let viewId = "chart";
  let sort = { key: "start", dir: "desc" };

  // Santé
  const health = buildHealth();
  const live = element("p", "help");
  live.setAttribute("role", "status");
  const healthSection = element("section", "sob-section");
  healthSection.setAttribute("aria-labelledby", "sob-health-title");
  const healthTitle = element("h2", "", t("sobriete.health.title"));
  healthTitle.id = "sob-health-title";
  healthSection.append(healthTitle, live, health.grid);

  // Carbone
  const carbon = buildCarbon(ctx);
  const carbonSection = element("section", "sob-section");
  carbonSection.setAttribute("aria-labelledby", "sob-carbon-title");
  const carbonTitle = element("h2", "", t("sobriete.carbon.title"));
  carbonTitle.id = "sob-carbon-title";
  const carbonHead = element("div", "sob-section-head");
  carbonHead.append(carbonTitle, carbon.actions);
  carbonSection.append(carbonHead, carbon.box);

  // Historique
  const windowSegment = segments({
    label: t("sobriete.history.window_label"),
    options: [
      { value: "w7", label: t("sobriete.history.w7") },
      { value: "w30", label: t("sobriete.history.w30") },
      { value: "wall", label: t("sobriete.history.wall") },
    ],
    value: windowId,
    onChange: (id) => {
      windowId = id;
      renderHistory();
    },
  });
  const viewSegment = segments({
    label: t("sobriete.history.view_label"),
    options: [
      { value: "chart", label: t("sobriete.history.chart") },
      { value: "table", label: t("sobriete.history.table") },
    ],
    value: viewId,
    onChange: (id) => {
      viewId = id;
      renderHistory();
    },
  });
  const controls = element("div", "sob-controls");
  controls.append(windowSegment.root, viewSegment.root);
  const historyBody = element("div", "sob-history-body");
  const historyTitle = element("h2", "", t("sobriete.history.title"));
  historyTitle.id = "sob-history-title";
  const historySection = element("section", "sob-section");
  historySection.setAttribute("aria-labelledby", "sob-history-title");
  historySection.append(historyTitle, controls, historyBody);

  // Repliés
  const identity = element("details", "sob-details");
  identity.append(element("summary", "", t("sobriete.identity.title")));
  const identityList = element("dl", "sob-dl");
  identity.append(identityList);
  const method = element("details", "sob-details");
  method.id = "sob-method";
  method.append(element("summary", "", t("sobriete.method.title")));
  const methodList = element("ul", "sob-method-list");
  for (const key of ["local", "cloud", "throughput", "unmeasurable", "no_threshold"]) {
    methodList.append(element("li", "", t(`sobriete.method.${key}`)));
  }
  method.append(methodList);

  host.replaceChildren(element("h1", "", ctx.route.title), element("p", "lead", t("sobriete.lead")), healthSection, carbonSection, historySection, identity, method);

  // --- Rendu -----------------------------------------------------------------------------
  function sessionsInWindow() {
    if (windowId === "wall") return history;
    const days = windowId === "w7" ? 7 : 30;
    return history.filter((session) => Date.parse(session.start) >= now - days * DAY_MS);
  }

  function renderHistory() {
    windowSegment.select(windowId, { silent: true });
    viewSegment.select(viewId, { silent: true });
    const active = document.activeElement;
    const focusKey = active?.closest?.(".sob-history-body") ? active.dataset?.key : null;
    controls.hidden = history.length === 0;
    if (history.length === 0) {
      historyBody.replaceChildren(element("p", "sob-empty", t("sobriete.history.empty")));
      return;
    }
    const sessions = sessionsInWindow().sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
    if (sessions.length === 0) {
      historyBody.replaceChildren(element("p", "sob-empty", t("sobriete.history.empty_window")));
      return;
    }
    if (viewId === "chart") {
      const heading = element("h3", "sob-chart-title", t("sobriete.history.chart_title"));
      const region = element("div", "sob-scroll");
      region.tabIndex = 0;
      region.setAttribute("role", "region");
      region.setAttribute("aria-label", t("sobriete.history.chart_region"));
      region.append(buildChart(sessions));
      const toTable = element("button", "btn", t("sobriete.history.see_table"));
      toTable.type = "button";
      toTable.addEventListener("click", () => {
        viewId = "table";
        renderHistory();
        historyBody.querySelector(".sob-table-wrap")?.focus();
      });
      historyBody.replaceChildren(heading, region, element("p", "help", t("sobriete.history.current_note")), toTable);
      return;
    }
    const region = buildTable(sessions, sort, (key) => {
      sort = { key, dir: sort.key === key && sort.dir === "desc" ? "asc" : "desc" };
      renderHistory();
    });
    const toChart = element("button", "btn", t("sobriete.history.see_chart"));
    toChart.type = "button";
    toChart.addEventListener("click", () => {
      viewId = "chart";
      renderHistory();
      historyBody.querySelector(".sob-scroll")?.focus();
    });
    historyBody.replaceChildren(region, element("p", "help", t("sobriete.history.current_note")), toChart);
    if (focusKey) historyBody.querySelector(`[data-key="${focusKey}"]`)?.focus();
  }

  function renderIdentity(state) {
    const down = !state.ollama.up && state.ollama.known;
    const entries = [
      [t("sobriete.identity.cpu"), data.identity.cpu],
      [t("sobriete.identity.memory"), t("sobriete.identity.memory_value", { total: formatGb(state.system.memory?.total_gb ?? data.identity.memory_gb) })],
      [t("sobriete.identity.accelerator"), hardwareMode === "none" ? t("sobriete.health.accelerator_none") : `${data.gpu.name}`],
      [t("sobriete.identity.os"), data.identity.os],
      [t("sobriete.identity.ollama"), down || !state.ollama.version ? t("sobriete.identity.ollama_unknown") : state.ollama.version],
      [t("sobriete.identity.app"), state.version],
      [t("sobriete.identity.country"), data.identity.country],
    ];
    const key = JSON.stringify(entries);
    if (identityList.dataset.key === key) return;
    identityList.dataset.key = key;
    identityList.replaceChildren(...entries.flatMap(([term, value]) => [element("dt", "", term), element("dd", "", value)]));
  }

  function renderAll(state = store.get()) {
    renderHealth(health, data, state, forced);
    renderCarbon(carbon, data, state, forced);
    renderIdentity(state);
    const paused = state.maquette.livePaused || document.hidden;
    const lost = state.connection.status === "lost";
    setText(live, lost ? t("sobriete.health.lost") : paused ? t("sobriete.health.paused") : t("sobriete.health.live"));
  }

  // --- Flux : en pause quand l'onglet est masqué (réel, simulé ou écran masqué) -------------
  let unsubscribe = null;
  const paused = () => document.hidden || store.get().maquette.livePaused || host.hidden;
  function pause() {
    unsubscribe?.();
    unsubscribe = null;
    host.dataset.live = "false";
    renderAll();
  }
  function resume() {
    if (unsubscribe) return;
    host.dataset.live = "true";
    unsubscribe = store.subscribe((state) => renderAll(state));
    renderAll();
  }
  const sync = () => (paused() ? pause() : resume());
  document.addEventListener("visibilitychange", sync);
  const unwatchPause = store.select((state) => state.maquette.livePaused, sync);
  const hiddenObserver = new MutationObserver(sync);
  hiddenObserver.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  // --- Actions ---------------------------------------------------------------------------
  carbon.reset.addEventListener("click", () => {
    const c = store.get().carbon;
    if (!c || (c.measured_runs === 0 && c.unmeasurable_runs === 0)) return;
    const measured = c.measured_runs > 0;
    history.push({
      start: data.closed_session_start,
      end: data.now,
      total_mg: measured ? c.total_mg : null,
      local_mg: measured ? c.by_origin.local.mg : null,
      cloud_mg: measured ? c.by_origin.cloud.mg : null,
      unmeasurable: c.unmeasurable_runs ?? 0,
    });
    resetCarbon();
    carbon.notices.replaceChildren(ctx.states.notice(t("sobriete.carbon.reset_done"), { tone: "success" }));
    renderHistory();
  });
  carbon.methodLink.addEventListener("click", () => {
    method.open = true;
    const summary = method.querySelector("summary");
    summary.focus();
    method.scrollIntoView({ block: "nearest" });
  });

  view = {
    ready: true,
    force(state) {
      forced = state;
      renderAll();
    },
    setHardware(mode) {
      hardwareMode = mode;
      renderAll();
    },
    setHistory(next) {
      history = structuredClone(next);
      renderHistory();
    },
    setHistoryView({ window: nextWindow = windowId, view: nextView = viewId } = {}) {
      windowId = nextWindow;
      viewId = nextView;
      renderHistory();
    },
    get data() {
      return data;
    },
    resetButton: carbon.reset,
    methodLink: carbon.methodLink,
    method,
    carbonNotices: carbon.notices,
  };

  renderHistory();
  sync();
  return () => {
    view = null;
    document.removeEventListener("visibilitychange", sync);
    unwatchPause();
    hiddenObserver.disconnect();
    unsubscribe?.();
    host.replaceChildren();
  };
}

// --- Scénarios ----------------------------------------------------------------------------

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

// Repart de l'état d'ouverture, remet le CO₂ de session à sa valeur de départ, applique `setup`.
async function fresh(ctx, setup = () => {}) {
  await ctx.reset();
  ctx.store.set({ carbon: structuredClone(ctx.system.systemConfig().carbon) });
  await waitUntil(() => view !== null && view.ready);
  setup();
  await waitUntil(() => ctx.store.get().systemSeen);
  await pause(60);
}

const carbonWith = (overrides) => ({
  total_mg: 0,
  by_origin: { local: { mg: 0, runs: 0 }, cloud: { mg: 0, runs: 0 } },
  by_module: {},
  measured_runs: 0,
  unmeasurable_runs: 0,
  ...overrides,
});

export const scenarios = [
  {
    id: "nominal",
    label: "Poste en direct, session avec Local, Cloud (estimé) et une réponse non mesurable",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "premier-chargement",
    label: "Premier chargement : squelettes des cartes et du total",
    run: (ctx) => fresh(ctx, () => view.force("loading")),
  },
  {
    id: "ollama-arrete",
    label: "Ollama arrêté : « Ollama ne répond pas » et Réessayer",
    run: (ctx) => fresh(ctx, () => setOllamaDown(true)),
  },
  {
    id: "aucun-modele-local",
    label: "Aucun modèle chargé (aucun modèle local installé)",
    run: (ctx) => fresh(ctx, () => setMaquette({ noLocalModel: true })),
  },
  {
    id: "sans-accelerateur",
    label: "Aucune carte graphique détectée : « Aucun »",
    run: (ctx) => fresh(ctx, () => view.setHardware("none")),
  },
  {
    id: "bridage-thermique",
    label: "Carte graphique chaude : « Bridage thermique en cours » en texte",
    run: (ctx) => fresh(ctx, () => view.setHardware("throttled")),
  },
  {
    id: "memoire-haute",
    label: "Mémoire presque pleine (garde-fou mémoire armé)",
    run: (ctx) => fresh(ctx, () => setMaquette({ ramGuard: true })),
  },
  {
    id: "connexion-perdue",
    label: "Connexion au serveur perdue : valeurs « inconnu »",
    async run(ctx) {
      await fresh(ctx);
      loseConnection();
      await pause(1500);
    },
  },
  {
    id: "onglet-masque",
    label: "Onglet masqué : mises à jour en pause, dernières valeurs gardées",
    run: (ctx) => fresh(ctx, () => setMaquette({ livePaused: true })),
  },
  {
    id: "session-vide",
    label: "Aucune réponse dans la session : pas de 0 mg, bouton de remise à zéro désactivé avec sa raison",
    run: (ctx) => fresh(ctx, () => ctx.store.set({ carbon: carbonWith({}) })),
  },
  {
    id: "session-non-mesurable",
    label: "Seulement des réponses non mesurables : comptées à part, jamais 0",
    run: (ctx) => fresh(ctx, () => ctx.store.set({ carbon: carbonWith({ unmeasurable_runs: 2 }) })),
  },
  {
    id: "session-en-grammes",
    label: "Session plus lourde : une seule unité (g) pour toute la section",
    run: (ctx) =>
      fresh(ctx, () =>
        ctx.store.set({
          carbon: carbonWith({
            total_mg: 1730,
            by_origin: { local: { mg: 1612, runs: 24 }, cloud: { mg: 118, runs: 5 } },
            by_module: { chat: { mg: 410 }, arena: { mg: 982 }, rag: { mg: 247 }, agent: { mg: 91 } },
            measured_runs: 29,
            unmeasurable_runs: 1,
          }),
        }),
      ),
  },
  {
    id: "reponse-en-direct",
    label: "Une réponse se termine : le total suit sans clic (carbon_updated)",
    async run(ctx) {
      await fresh(ctx);
      recordLeaf({ co2: { mg: 41.7, method: "codecarbon", estimated: false, range_mg: null, allocation: "direct", reason: null }, origin: "local", module: "agent" });
      await pause(300);
    },
  },
  {
    id: "non-mesurables-lien",
    label: "Clic sur « non mesurable » : « Comment ces chiffres sont calculés » se déplie",
    async run(ctx) {
      await fresh(ctx);
      view.methodLink.click();
      await waitUntil(() => view.method.open);
    },
  },
  {
    id: "remise-a-zero",
    label: "Remettre le compteur à zéro : la session close rejoint l'historique",
    async run(ctx) {
      await fresh(ctx);
      view.resetButton.click();
      await waitUntil(() => view.carbonNotices.children.length > 0);
      view.setHistoryView({ window: "w7", view: "table" });
    },
  },
  {
    id: "historique-30-jours",
    label: "Historique sur 30 jours (graphique, trous de mesure visibles)",
    async run(ctx) {
      await fresh(ctx);
      view.setHistoryView({ window: "w30", view: "chart" });
    },
  },
  {
    id: "historique-tout",
    label: "Historique complet (graphique)",
    async run(ctx) {
      await fresh(ctx);
      view.setHistoryView({ window: "wall", view: "chart" });
    },
  },
  {
    id: "historique-tableau",
    label: "Historique en tableau triable (tout)",
    async run(ctx) {
      await fresh(ctx);
      view.setHistoryView({ window: "wall", view: "table" });
    },
  },
  {
    id: "historique-periode-vide",
    label: "Aucune session sur 7 jours : message et renvoi vers « Tout »",
    async run(ctx) {
      await fresh(ctx);
      view.setHistory(view.data.history.filter((session) => session.start < "2026-10-05"));
      view.setHistoryView({ window: "w7", view: "chart" });
    },
  },
  {
    id: "historique-vide",
    label: "Aucun historique : « Aucune session mesurée pour l'instant. », pas de graphique vide",
    async run(ctx) {
      await fresh(ctx);
      view.setHistory([]);
    },
  },
];
