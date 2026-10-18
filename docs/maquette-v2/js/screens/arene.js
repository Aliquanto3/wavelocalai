// Arène, `#/arene/comparer[/<run_id>]` (UX-DR8, UX-DR9, UX-DR13 à UX-DR15, UX-DR17, UX-DR19, UX-DR20,
// stories 3.2 à 3.6) : l'écran du Flow 1, branché sur le simulateur (js/sim/sim.js).
//
// - Configuration : question et scénarios prédéfinis, `wl-model-picker` multi (défaut `arena`), juge
//   (défaut `judge` et sa raison, « note peu fiable » sous ~4B), critères repliés, phrase d'exécution,
//   « Lancer la comparaison » désactivé avec sa raison en légende.
// - Exécution : bandeau « Comparaison en cours · 2 sur 3 » (chronomètre, Arrêter, Échap), une colonne
//   par modèle (statut en texte et icône, débit provisoire puis final, réponse en flux, « Afficher
//   toute la réponse », mode focus), puis classement, matrice ou tableau, verdict local/cloud, actions.
// - Largeurs : 3-4 colonnes dès 1 440 px, 2 colonnes visibles avec défilement et en-têtes collants de
//   768 à 1 439 px, onglets par modèle sous 768 px.
// - Résultat conservé : à la fin, l'adresse devient `#/arene/comparer/<run_id>` ; l'adresse d'un run
//   se rouvre sans relancer de modèle (instantané). « Relancer » et « Modifier la question » reprennent
//   la configuration. Les exports contiennent la preuve de mesure et aucune clé d'API.
// - Le front ne calcule aucune mesure : seuls le chronomètre et le débit provisoire sont locaux. Le
//   verdict local/cloud, le « serveur » le rend dans l'instantané du run (`serverVerdict`, ci-dessous).

import { element, icon } from "../core/dom.js";
import { errorEnvelope } from "../core/errors.js";
import {
  co2Group,
  formatDate,
  formatDuration,
  formatInteger,
  formatNumber,
  formatRate,
  formatScore,
  formatTime,
} from "../core/format.js";
import { co2Display } from "../core/co2.js";
import { plural, t } from "../core/i18n.js";
import { renderMarkdown } from "../core/markdown.js";
import { setMaquette, store } from "../core/store.js";
import { findModel } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";

const MIN_MODELS = 2;
const MAX_MODELS = 4;
const WEAK_JUDGE_B = 4; // milliards de paramètres actifs
const TERMINAL = new Set(["done", "timeout", "failed", "cancelled", "interrupted"]);
const WORDS = ["", "un", "deux", "trois", "quatre"];
const CONFIG_PATH = "/arene/comparer";

let counter = 0;
let view = null; // l'instance montée, pour les scénarios
let pending = null; // configuration à appliquer au prochain montage (« Relancer », « Modifier »)
const saved = new Map(); // instantanés des comparaisons terminées pendant cette visite

// --- Icônes locales (le sprite commun n'a pas ces glyphes) ----------------------------------------
// Tracés Material Symbols (Apache 2.0, voir icons.LICENSE.txt), viewBox 24 : même rendu que `icon()`.

const SVG_NS = "http://www.w3.org/2000/svg";
const PATHS = {
  hourglass: "M6 2v6h.01L6 8.01 10 12l-4 4 .01.01H6V22h12v-5.99h-.01L18 16l-4-4 4-3.99-.01-.01H18V2H6zm10 14.5V20H8v-3.5l4-4 4 4zm-4-5l-4-4V4h8v3.5l-4 4z",
  check_circle: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
  cancel: "M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.59 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z",
  schedule: "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z",
  block: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zM4 12c0-4.42 3.58-8 8-8 1.85 0 3.55.63 4.9 1.69L5.69 16.9C4.63 15.55 4 13.85 4 12zm8 8c-1.85 0-3.55-.63-4.9-1.69L18.31 7.1C19.37 8.45 20 10.15 20 12c0 4.42-3.58 8-8 8z",
  autorenew: "M12 6v3l4-4-4-4v3c-4.42 0-8 3.58-8 8 0 1.57.46 3.03 1.24 4.26L6.7 14.8c-.45-.83-.7-1.79-.7-2.8 0-3.31 2.69-6 6-6zm6.76 1.74L17.3 9.2c.44.84.7 1.79.7 2.8 0 3.31-2.69 6-6 6v-3l-4 4 4 4v-3c4.42 0 8-3.58 8-8 0-1.57-.46-3.03-1.24-4.26z",
  download: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
  replay: "M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z",
  edit: "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
  open_in_full: "M21 11V3h-8l3.29 3.29-10 10L3 13v8h8l-3.29-3.29 10-10z",
  close_fullscreen: "M22 3.41 16.71 8.7 20 12h-8V4l3.29 3.29L20.59 2 22 3.41zM3.41 22l5.29-5.29L12 20v-8H4l3.29 3.29L2 20.59 3.41 22z",
};

export function localIcon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "icon");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", PATHS[name]);
  svg.append(path);
  return svg;
}

const STATUS_ICON = {
  waiting: () => localIcon("hourglass"),
  loading: () => icon("deployed-code"),
  generating: () => localIcon("autorenew"),
  judging: () => localIcon("autorenew"),
  done: () => localIcon("check_circle"),
  timeout: () => localIcon("schedule"),
  failed: () => localIcon("cancel"),
  cancelled: () => localIcon("block"),
  interrupted: () => icon("warning"),
};

// --- Composants locaux partagés avec le Banc d'essai et les Références ----------------------------

// Segments (EXPERIENCE.md, règles communes) : `radiogroup`, flèches pour changer, choisi en
// `wl-pill-selected` (icône `check`). `onChange(value)` est appelé au changement.
export function segments({ label, options, value, onChange, prefix = "ar" }) {
  const root = element("div", `${prefix}-seg`);
  root.setAttribute("role", "radiogroup");
  root.setAttribute("aria-label", label);
  const buttons = new Map();
  const select = (next, { focus = false, silent = false } = {}) => {
    value = next;
    for (const [id, button] of buttons) {
      const on = id === value;
      button.setAttribute("aria-checked", String(on));
      button.tabIndex = on ? 0 : -1;
      if (on && focus) button.focus();
    }
    if (!silent) onChange?.(value);
  };
  for (const option of options) {
    const button = element("button", `${prefix}-seg-button`);
    button.type = "button";
    button.setAttribute("role", "radio");
    button.append(icon("check"), element("span", "", option.label));
    button.addEventListener("click", () => select(option.value));
    button.addEventListener("keydown", (event) => {
      const keys = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
      if (!(event.key in keys)) return;
      event.preventDefault();
      const index = options.findIndex((candidate) => candidate.value === value);
      const target = options[(index + keys[event.key] + options.length) % options.length];
      select(target.value, { focus: true });
    });
    buttons.set(option.value, button);
    root.append(button);
  }
  select(value, { silent: true });
  return { root, select, get value() { return value; } };
}

// Tableau sémantique triable au clavier (UX-DR13) : `<table>` avec `scope`, en-têtes boutons,
// `aria-sort`. Colonnes : { key, label, value(row) (valeur de tri), cell(row) (nœud ou texte),
// header (cellule d'en-tête de ligne) }. Le conteneur défile (focusable) sans déborder de la page.
export function dataTable({ caption, columns, rows, sortKey = null, ascending = true, className = "ar", sortLabel = null }) {
  const wrap = element("div", `${className}-table-wrap`);
  wrap.tabIndex = 0;
  wrap.setAttribute("role", "region");
  wrap.setAttribute("aria-label", caption);
  const table = element("table", `${className}-table`);
  table.append(element("caption", "sr-only", caption));
  const head = element("tr");
  const headers = new Map();
  for (const column of columns) {
    const th = element("th");
    th.scope = "col";
    if (column.value) {
      const button = element("button", `${className}-sort`);
      button.type = "button";
      button.dataset.key = column.key;
      button.append(element("span", "", column.label), icon("expand-more"));
      if (sortLabel) button.setAttribute("aria-label", sortLabel(column.label));
      button.addEventListener("click", () => {
        if (sortKey === column.key) ascending = !ascending;
        else {
          sortKey = column.key;
          ascending = true;
        }
        renderBody();
      });
      th.append(button);
    } else {
      th.textContent = column.label;
    }
    headers.set(column.key, th);
    head.append(th);
  }
  const thead = element("thead");
  thead.append(head);
  const tbody = element("tbody");
  table.append(thead, tbody);
  wrap.append(table);

  function renderBody() {
    let list = [...rows];
    const column = columns.find((candidate) => candidate.key === sortKey);
    if (column?.value) {
      list.sort((a, b) => {
        const x = column.value(a);
        const y = column.value(b);
        if (x == null && y == null) return 0;
        if (x == null) return 1; // les valeurs inconnues restent en bas
        if (y == null) return -1;
        const order = typeof x === "string" ? x.localeCompare(y, "fr-FR") : x - y;
        return ascending ? order : -order;
      });
    }
    for (const [key, th] of headers) {
      th.setAttribute("aria-sort", key === sortKey ? (ascending ? "ascending" : "descending") : "none");
    }
    tbody.replaceChildren(
      ...list.map((row) => {
        const tr = element("tr");
        for (const columnItem of columns) {
          const cell = element(columnItem.header ? "th" : "td");
          if (columnItem.header) cell.scope = "row";
          const content = columnItem.cell(row);
          if (content instanceof Node) cell.append(content);
          else cell.textContent = content;
          tr.append(cell);
        }
        return tr;
      }),
    );
  }
  renderBody();
  return wrap;
}

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

const speedOf = () => store.get().maquette.speed || 1;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms / speedOf()));
const euro = (value) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(value);

// --- Ce que le « serveur » mesure (le front n'en calcule rien) ------------------------------------

const laneBase = (data, tag) => data.lanes[tag] ?? data.lanes.default;

function simulateLane(data, model, outcome) {
  const base = laneBase(data, model.tag);
  const empty = outcome === "empty";
  const partialOutcome = ["timeout", "failed", "cancelled"].includes(outcome);
  const metrics = { lane: model.tag, ...structuredClone(base.metrics) };
  if (empty) Object.assign(metrics, { ttft_s: null, eval_tokens: 0, eval_s: 0, tps: null, total_s: (metrics.load_s ?? 0) + 1.2 });
  return {
    text: empty ? "" : outcome === "failed" ? "" : partialOutcome ? base.partial : base.answer,
    metrics: partialOutcome ? null : metrics,
    score: outcome === "ok" ? base.score : null,
    reason: empty ? data.reasons.empty : base.reason,
  };
}

function laneError(data, model, outcome) {
  if (outcome === "timeout") return errorEnvelope("timeout", { detail: { timeout_s: data.lane_timeout_s } });
  if (outcome === "failed") {
    return model.origin === "cloud"
      ? errorEnvelope("cloud_unreachable", { detail: { provider: model.provider, provider_name: model.provider_name } })
      : errorEnvelope("interrupted");
  }
  return null;
}

// Variables du script `arene-comparaison` : les modèles cloud partent d'abord (en parallèle), les
// locaux suivent l'un après l'autre ; un emplacement `sN` par modèle.
export function buildVars({ data, models, judge, prompt, criteria, outcomes = {}, judgeDown = false, loaded = new Set() }) {
  const ordered = [...models.filter((m) => m.origin === "cloud"), ...models.filter((m) => m.origin !== "cloud")];
  const vars = { models: models.map((m) => m.tag), prompt, judge: judge.tag, criteria };
  for (let n = 1; n <= 4; n += 1) {
    const key = `s${n}`;
    const model = ordered[n - 1] ?? null;
    const slot = {
      [key]: model?.tag ?? null,
      [`${key}_first`]: "generating",
      [`${key}_loading`]: false,
      [`${key}_load_s`]: null,
      [`${key}_has_text`]: false,
      [`${key}_text`]: "",
      [`${key}_tps`]: 40,
      [`${key}_fail`]: false,
      [`${key}_fail_status`]: "failed",
      [`${key}_error`]: null,
      [`${key}_ok`]: false,
      [`${key}_metrics`]: null,
      [`${key}_score`]: null,
      [`${key}_reason`]: "",
    };
    if (model) {
      const outcome = outcomes[model.tag] ?? "ok";
      const lane = simulateLane(data, model, outcome);
      const base = laneBase(data, model.tag);
      const loading = model.origin !== "cloud" && !loaded.has(model.tag);
      const failing = outcome === "timeout" || outcome === "failed";
      Object.assign(slot, {
        [`${key}_first`]: loading ? "loading" : "generating",
        [`${key}_loading`]: loading,
        [`${key}_load_s`]: base.metrics.load_s,
        [`${key}_has_text`]: lane.text.length > 0,
        [`${key}_text`]: lane.text,
        [`${key}_tps`]: outcome === "timeout" ? 6 : (base.metrics.tps ?? 40),
        [`${key}_fail`]: failing,
        [`${key}_fail_status`]: outcome,
        [`${key}_error`]: laneError(data, model, outcome),
        [`${key}_ok`]: !failing,
        [`${key}_metrics`]: lane.metrics ? { ...lane.metrics, load_s: loading || model.origin === "cloud" ? lane.metrics.load_s : null } : null,
        [`${key}_score`]: judgeDown ? null : lane.score,
        [`${key}_reason`]: judgeDown ? data.reasons.judge_down : lane.reason,
      });
    }
    Object.assign(vars, slot);
  }
  return vars;
}

// Instantané du run (`GET /api/runs/{id}`) : le verdict local/cloud se calcule côté serveur (3.5).
function serverVerdict(data, lanes) {
  const rated = lanes.filter((lane) => typeof lane.score === "number");
  const best = (list) => [...list].sort((a, b) => b.score - a.score)[0] ?? null;
  const local = best(rated.filter((lane) => lane.origin !== "cloud"));
  const cloud = best(rated.filter((lane) => lane.origin === "cloud"));
  if (!local || !cloud) return null;
  const price = data.price_eur_per_1k[cloud.tag];
  return {
    local: { tag: local.tag, name: local.name, score: local.score, co2: local.metrics?.co2 ?? null },
    cloud: { tag: cloud.tag, name: cloud.name, score: cloud.score, co2: cloud.metrics?.co2 ?? null, cost_eur: price ?? null },
    local_models: lanes.filter((lane) => lane.origin !== "cloud").length,
    price_table_date: data.price_table_date,
  };
}

// --- Écran ----------------------------------------------------------------------------------------

export async function mount(host, ctx) {
  const uid = `ar-${++counter}`;
  const data = await ctx.data("arene.json");
  const slug = ctx.route.slug;
  const reopenId = slug === "arene-resultat" ? ctx.params.run_id : null;
  if (!reopenId && /^#\/arene\/comparer\/./.test(location.hash)) history.replaceState(null, "", `#${CONFIG_PATH}`);

  const state = {
    mode: "config", // config | running | done | missing | erased
    lanes: new Map(),
    order: [],
    prompt: "",
    judge: null,
    criteria: data.criteria_default,
    status: null,
    runId: null,
    startedAt: null,
    durationS: null,
    reopenedAt: null,
    verdict: null,
    error: null,
    segment: "matrix",
    focus: null,
    tab: null,
    stopping: false,
    erasedRows: [],
  };
  let run = null;
  let attachment = null;
  let lastSeq = 0;
  let timerId = null;
  let wasHidden = host.hidden;
  const loaded = new Set(); // modèles déjà chargés en mémoire pendant cette visite
  const compact = window.matchMedia("(max-width: 767px)");

  // --- Structure : configuration -----------------------------------------------------------------
  const guard = ctx.states.ollamaGuard();

  const questionLabel = element("label", "ar-label", t("arene.config.question"));
  questionLabel.htmlFor = `${uid}-question`;
  const question = element("textarea", "ar-question");
  question.id = `${uid}-question`;
  question.rows = 3;
  question.value = data.default_prompt;
  question.setAttribute("aria-describedby", `${uid}-question-help`);
  const questionHelp = element("p", "help", t("arene.config.question_help"));
  questionHelp.id = `${uid}-question-help`;

  const scenarioBox = element("fieldset", "ar-scenarios");
  scenarioBox.append(element("legend", "ar-legend", t("arene.config.scenarios")));
  const scenarioRow = element("div", "ar-scenario-row");
  for (const scenario of data.scenarios) {
    const button = element("button", "btn", scenario.label);
    button.type = "button";
    button.dataset.scenario = scenario.id;
    button.addEventListener("click", () => {
      question.value = scenario.prompt;
      updateLaunch();
      question.focus();
    });
    scenarioRow.append(button);
  }
  scenarioBox.append(scenarioRow, element("p", "help", t("arene.config.scenarios_help")));

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "arena");
  picker.setAttribute("multi", "");
  picker.setAttribute("label", t("arene.config.models"));
  const modelsHelp = element("p", "help", t("arene.config.models_help"));
  const judgePicker = document.createElement("wl-model-picker");
  judgePicker.setAttribute("purpose", "judge");
  judgePicker.setAttribute("label", t("arene.config.judge"));
  const judgeWarn = element("div", "ar-judge-warn");
  const judgeBox = element("div", "ar-judge");
  judgeBox.append(judgePicker, judgeWarn);
  const modelsBox = element("div", "ar-models");
  modelsBox.append(picker, modelsHelp);
  const settings = element("div", "ar-settings");
  settings.append(modelsBox, judgeBox);

  const criteria = element("textarea", "ar-criteria");
  criteria.id = `${uid}-criteria`;
  criteria.rows = 4;
  criteria.value = data.criteria_default;
  criteria.setAttribute("aria-describedby", `${uid}-criteria-help`);
  const criteriaLabel = element("label", "ar-label", t("arene.config.criteria_label"));
  criteriaLabel.htmlFor = criteria.id;
  const criteriaHelp = element("p", "help", t("arene.config.criteria_help"));
  criteriaHelp.id = `${uid}-criteria-help`;
  const criteriaBox = element("details", "ar-details");
  criteriaBox.append(element("summary", "", t("arene.config.criteria_title")), criteriaLabel, criteria, criteriaHelp);

  const execution = element("p", "help ar-execution", t("arene.config.execution"));
  const launch = element("button", "btn btn-primary ar-launch", t("arene.config.launch"));
  launch.type = "submit";
  const legend = element("p", "help ar-legend-text");
  legend.id = `${uid}-legend`;
  launch.setAttribute("aria-describedby", legend.id);
  const launchRow = element("div", "ar-launch-row");
  launchRow.append(launch, legend);

  const configError = document.createElement("wl-error");
  configError.setAttribute("alert", "");
  const notices = element("div", "ar-notices");
  const configTitle = element("h2", "", t("arene.config.title"));
  const config = element("form", "ar-config");
  config.noValidate = true;
  config.append(configTitle, questionLabel, question, questionHelp, scenarioBox, settings, criteriaBox, execution, configError, launchRow);

  // --- Structure : comparaison -------------------------------------------------------------------
  const holder = element("div", "ar-holder"); // introuvable, effacée
  const summary = element("section", "ar-summary");
  const summaryTitle = element("h2", "", t("arene.summary.title"));
  const summaryList = element("dl", "ar-summary-list");
  summary.append(summaryTitle, summaryList);

  const banner = element("div", "ar-banner");
  const bannerText = element("p", "ar-banner-text");
  const bannerTimer = element("span", "ar-banner-timer");
  bannerTimer.setAttribute("role", "timer");
  bannerTimer.setAttribute("aria-label", t("arene.banner.elapsed"));
  const stop = element("button", "btn ar-stop", t("arene.banner.stop"));
  stop.type = "button";
  stop.setAttribute("aria-keyshortcuts", "Escape");
  const stopHint = element("span", "help ar-stop-hint", t("arene.banner.stop_hint"));
  banner.append(bannerText, bannerTimer, stop, stopHint);
  const firstLoad = element("p", "help ar-first-load", t("states.slow_loading"));
  const runError = document.createElement("wl-error");
  runError.setAttribute("alert", "");

  const lanesSection = element("section", "ar-lanes-section");
  const lanesTitle = element("h2", "", t("arene.lanes.title"));
  const tablist = element("div", "ar-tabs");
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", t("arene.lanes.tabs"));
  const lanesBox = element("div", "ar-lanes");
  const lanesScroll = element("div", "ar-lanes-scroll");
  lanesScroll.tabIndex = 0;
  lanesScroll.setAttribute("role", "group");
  lanesScroll.setAttribute("aria-label", t("arene.lanes.group"));
  lanesScroll.append(lanesBox);
  lanesSection.append(lanesTitle, tablist, lanesScroll);

  const resultsSection = element("div", "ar-results");
  const rankingSection = element("section", "ar-ranking");
  const chartSection = element("section", "ar-chart-section");
  const verdictSection = element("section", "ar-verdict");
  const actionsSection = element("section", "ar-actions");
  resultsSection.append(rankingSection, chartSection, verdictSection, actionsSection);

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("arene.lead")),
    guard,
    config,
    notices,
    holder,
    summary,
    banner,
    firstLoad,
    runError,
    lanesSection,
    resultsSection,
  );

  // --- Configuration -----------------------------------------------------------------------------
  const chosenModels = () => picker.values;

  function updateJudge() {
    const model = judgePicker.selected;
    judgeWarn.replaceChildren();
    if (model && typeof model.params_active_b === "number" && model.params_active_b < WEAK_JUDGE_B) {
      judgeWarn.append(ctx.states.notice(t("arene.config.judge_weak"), { tone: "warning" }));
    }
  }

  function updateLaunch() {
    const count = chosenModels().length;
    let reason = null;
    if (count < MIN_MODELS) reason = t("arene.config.legend_min");
    else if (count > MAX_MODELS) reason = t("arene.config.legend_max");
    else if (!question.value.trim()) reason = t("arene.config.legend_question");
    else if (!judgePicker.value) reason = t("arene.config.legend_judge");
    launch.disabled = reason !== null || state.mode === "running";
    legend.textContent =
      reason ?? t("arene.config.legend_ready", { count, judge: judgePicker.selected?.name ?? judgePicker.value });
  }

  picker.addEventListener("wl-model-change", updateLaunch);
  judgePicker.addEventListener("wl-model-change", () => {
    updateJudge();
    updateLaunch();
  });
  question.addEventListener("input", updateLaunch);

  const pickersReady = () =>
    waitUntil(
      () =>
        (picker.values.length > 0 || picker.querySelector("wl-error:not([hidden])")) &&
        (judgePicker.selected !== null || judgePicker.querySelector("wl-error:not([hidden])")),
      5000,
    ).catch(() => {});

  function currentConfig() {
    return {
      prompt: state.prompt || question.value,
      models: state.order.length ? [...state.order] : chosenModels(),
      judge: state.judge?.tag ?? judgePicker.value,
      criteria: state.criteria ?? criteria.value,
    };
  }

  function applyConfig(cfg) {
    question.value = cfg.prompt;
    picker.values = cfg.models;
    if (cfg.judge) judgePicker.value = cfg.judge;
    criteria.value = cfg.criteria ?? data.criteria_default;
    updateJudge();
    updateLaunch();
  }

  // --- Modes -------------------------------------------------------------------------------------
  function setMode(mode) {
    state.mode = mode;
    const live = mode === "running" || mode === "done";
    config.hidden = mode !== "config";
    summary.hidden = !live;
    banner.hidden = !live;
    lanesSection.hidden = !live;
    resultsSection.hidden = !live;
    holder.hidden = mode !== "missing" && mode !== "erased";
    stop.hidden = mode !== "running";
    stopHint.hidden = mode !== "running";
    firstLoad.hidden = true;
    runError.hidden = !runError.error;
    host.dataset.mode = mode;
    updateLaunch();
  }

  // --- Lanes -------------------------------------------------------------------------------------
  function createLane(model, index) {
    const lane = {
      tag: model.tag,
      name: model.name,
      origin: model.origin,
      params: model.params_active_b ?? null,
      index,
      status: "waiting",
      text: "",
      metrics: null,
      score: undefined, // undefined : pas encore noté ; null : non évalué
      reason: "",
      error: null,
      erased: false,
      expanded: false,
      chars: 0,
      firstTokenAt: null,
      provisional: null,
      renderTimer: null,
      dom: {},
    };
    const article = element("div", "ar-lane");
    article.dataset.tag = model.tag;
    const head = element("div", "ar-lane-head");
    const title = element("h3", "ar-lane-name", model.name);
    title.id = `${uid}-lane-${index}`;
    const badge = document.createElement("wl-badge");
    badge.setAttribute("kind", ["local", "cloud"].includes(model.origin) ? model.origin : "unknown");
    const focusButton = element("button", "btn ar-focus");
    focusButton.type = "button";
    focusButton.addEventListener("click", () => {
      state.focus = state.focus === lane.tag ? null : lane.tag;
      layoutLanes();
    });
    const titleRow = element("div", "ar-lane-title");
    titleRow.append(title, badge, focusButton);
    const status = element("p", "ar-lane-status");
    head.append(titleRow, status);
    const metrics = element("div", "ar-lane-metrics");
    const body = element("div", "ar-lane-text wl-md");
    const more = element("button", "btn ar-more");
    more.type = "button";
    more.addEventListener("click", () => {
      lane.expanded = !lane.expanded;
      renderLane(lane);
    });
    const note = element("div", "ar-lane-note");
    article.append(head, metrics, body, more, note);
    lane.dom = { article, title, badge, status, metrics, body, more, note, focusButton };
    return lane;
  }

  async function ensureLanes(tags, params = {}) {
    if (state.order.join() === tags.join() && state.lanes.size) return;
    clearLanes();
    const models = await Promise.all(
      tags.map(async (tag) => (await findModel(tag)) ?? { tag, name: tag, origin: "unknown", params_active_b: null }),
    );
    models.forEach((model, index) => {
      const lane = createLane(model, index);
      state.lanes.set(model.tag, lane);
      state.order.push(model.tag);
      lanesBox.append(lane.dom.article);
    });
    if ("prompt" in params) state.prompt = params.prompt;
    if (params.judge) state.judge = (await findModel(params.judge)) ?? { tag: params.judge, name: params.judge, origin: "unknown" };
    if ("criteria" in params) state.criteria = params.criteria;
    lanesBox.style.setProperty("--ar-count", String(tags.length));
    state.lanes.forEach(renderLane);
    renderSummary();
    layoutLanes();
  }

  function clearLanes() {
    for (const lane of state.lanes.values()) clearTimeout(lane.renderTimer);
    state.lanes.clear();
    state.order = [];
    state.focus = null;
    state.tab = null;
    lanesBox.replaceChildren();
  }

  function metricRow(label, value, { provisional = false } = {}) {
    const row = element("div", "ar-m");
    const dd = element("dd", provisional ? "ar-provisional" : "");
    if (value instanceof Node) dd.append(value);
    else dd.textContent = value;
    row.append(element("dt", "", label), dd);
    return row;
  }

  function renderLane(lane) {
    const { dom } = lane;
    clearTimeout(lane.renderTimer);
    lane.renderTimer = null;
    dom.article.dataset.status = lane.status;
    dom.status.replaceChildren(STATUS_ICON[lane.status](), element("span", "", t(`arene.status.${lane.status}`)));

    const rows = [];
    const scoreStates = ["judging", "done"];
    if (lane.score !== undefined) {
      const judged = ctx.states.scoreValue(lane.score, lane.reason);
      rows.push(metricRow(t("arene.metric.score"), judged));
    } else if (scoreStates.includes(lane.status)) {
      rows.push(metricRow(t("arene.metric.score"), t("arene.lanes.score_running")));
    } else if (!["waiting"].includes(lane.status) && !["timeout", "failed", "cancelled", "interrupted"].includes(lane.status)) {
      rows.push(metricRow(t("arene.metric.score"), t("arene.lanes.score_pending")));
    }
    const m = lane.metrics;
    if (m) {
      rows.push(metricRow(t("arene.metric.rate"), formatRate(m.tps)));
      rows.push(metricRow(t("arene.metric.ttft"), m.ttft_s == null ? formatNumber(null) : formatDuration(m.ttft_s)));
      rows.push(metricRow(t("arene.metric.tokens"), formatInteger(m.eval_tokens)));
      if (lane.origin !== "cloud") {
        rows.push(metricRow(t("arene.metric.load"), m.load_s == null ? t("arene.lanes.already_loaded") : formatDuration(m.load_s)));
      }
      rows.push(metricRow(t("arene.metric.co2"), ctx.states.co2Value(m.co2)));
      rows.push(metricRow(t("arene.metric.total"), formatDuration(m.total_s)));
    } else if (lane.provisional) {
      rows.push(metricRow(t("arene.metric.rate"), `${formatRate(lane.provisional)} ${t("arene.lanes.provisional")}`, { provisional: true }));
    }
    const list = element("dl", "ar-m-list");
    list.append(...rows);
    dom.metrics.replaceChildren(...(rows.length ? [list] : []));
    if (lane.reason && typeof lane.score === "number") {
      dom.metrics.append(element("p", "help ar-reason", t("arene.lanes.judge_reason", { reason: lane.reason })));
    }

    // Réponse : Markdown rendu au plus toutes les 150 ms (ici à chaque appel) et à la fin.
    const clamp = !lane.expanded;
    dom.body.classList.toggle("is-clamped", clamp);
    if (lane.text) {
      dom.body.replaceChildren(renderMarkdown(lane.text));
      if (lane.status === "generating" && clamp) dom.body.scrollTop = dom.body.scrollHeight;
      else dom.body.scrollTop = 0;
    } else if (lane.erased) {
      dom.body.replaceChildren();
    } else {
      dom.body.replaceChildren(...(lane.status === "done" ? [element("p", "help", t("arene.lanes.no_answer"))] : []));
    }
    dom.more.hidden = !lane.text;
    dom.more.textContent = t(lane.expanded ? "arene.lanes.show_less" : "arene.lanes.show_all");
    dom.more.setAttribute("aria-expanded", String(lane.expanded));

    // Délai dépassé, échec, arrêt : dit dans la colonne, les autres continuent.
    const notes = [];
    if (lane.status === "timeout") {
      const line = element("p", "ar-lane-alert");
      line.append(STATUS_ICON.timeout(), element("span", "", t("arene.lanes.timeout")));
      notes.push(line);
    }
    if (lane.error && lane.status === "failed") {
      const box = document.createElement("wl-error");
      box.error = { ...lane.error, buttons: [] };
      notes.push(box);
    }
    if (["cancelled", "interrupted"].includes(lane.status) && lane.text) notes.push(element("p", "help", t("arene.lanes.partial_kept")));
    dom.note.replaceChildren(...notes);
    const focused = state.focus === lane.tag;
    dom.focusButton.replaceChildren(localIcon(focused ? "close_fullscreen" : "open_in_full"), element("span", "", t(focused ? "arene.lanes.unfocus" : "arene.lanes.focus")));
    dom.focusButton.setAttribute("aria-pressed", String(focused));
  }

  function scheduleLane(lane) {
    if (lane.renderTimer) return;
    lane.renderTimer = setTimeout(() => renderLane(lane), 150 / speedOf());
  }

  // Largeur : colonnes (mode focus compris) ou onglets par modèle sous 768 px.
  function layoutLanes() {
    const tabs = compact.matches && state.order.length > 0;
    tablist.hidden = !tabs;
    lanesBox.dataset.compact = String(tabs);
    if (tabs) {
      if (!state.tab || !state.lanes.has(state.tab)) state.tab = state.order[0];
      tablist.replaceChildren(
        ...state.order.map((tag) => {
          const lane = state.lanes.get(tag);
          const button = element("button", "ar-tab", `${lane.name} · ${t(`arene.status.${lane.status}`)}`);
          button.type = "button";
          button.id = `${uid}-tab-${state.order.indexOf(tag)}`;
          button.setAttribute("role", "tab");
          button.setAttribute("aria-selected", String(tag === state.tab));
          button.setAttribute("aria-controls", `${uid}-panel-${state.order.indexOf(tag)}`);
          button.tabIndex = tag === state.tab ? 0 : -1;
          button.addEventListener("click", () => {
            state.tab = tag;
            layoutLanes();
          });
          button.addEventListener("keydown", (event) => {
            const moves = { ArrowRight: 1, ArrowLeft: -1 };
            let target = null;
            if (event.key in moves) target = state.order[(state.order.indexOf(tag) + moves[event.key] + state.order.length) % state.order.length];
            if (event.key === "Home") target = state.order[0];
            if (event.key === "End") target = state.order[state.order.length - 1];
            if (!target) return;
            event.preventDefault();
            state.tab = target;
            layoutLanes();
            tablist.querySelector('[aria-selected="true"]')?.focus();
          });
          return button;
        }),
      );
    }
    state.order.forEach((tag, index) => {
      const lane = state.lanes.get(tag);
      const { article, focusButton } = lane.dom;
      if (tabs) {
        article.setAttribute("role", "tabpanel");
        article.id = `${uid}-panel-${index}`;
        article.setAttribute("aria-labelledby", `${uid}-tab-${index}`);
        article.hidden = tag !== state.tab;
      } else {
        article.setAttribute("role", "group");
        article.setAttribute("aria-labelledby", lane.dom.title.id);
        article.id = `${uid}-panel-${index}`;
        article.hidden = state.focus !== null && state.focus !== tag;
      }
      focusButton.hidden = tabs || state.order.length < 2;
      renderLane(lane);
    });
    lanesBox.dataset.focus = state.focus ? "true" : "false";
  }
  compact.addEventListener("change", layoutLanes);

  // --- Résumé, bandeau ---------------------------------------------------------------------------
  function renderSummary() {
    const items = [[t("arene.summary.question"), state.prompt]];
    const models = element("span", "ar-summary-models");
    for (const tag of state.order) {
      const lane = state.lanes.get(tag);
      const badge = document.createElement("wl-badge");
      badge.setAttribute("kind", ["local", "cloud"].includes(lane.origin) ? lane.origin : "unknown");
      const item = element("span", "ar-summary-model");
      item.append(element("span", "", lane.name), badge);
      models.append(item);
    }
    items.push([t("arene.summary.models"), models]);
    if (state.judge) {
      const judge = element("span", "ar-summary-model");
      const badge = document.createElement("wl-badge");
      badge.setAttribute("kind", ["local", "cloud"].includes(state.judge.origin) ? state.judge.origin : "unknown");
      judge.append(element("span", "", state.judge.name), badge);
      items.push([t("arene.summary.judge"), judge]);
    }
    const criteriaItem = element("details", "ar-details ar-summary-criteria");
    criteriaItem.append(element("summary", "", t("arene.summary.criteria")), element("p", "", state.criteria));
    items.push([t("arene.summary.criteria"), criteriaItem]);
    summaryList.replaceChildren(
      ...items.map(([label, value]) => {
        const row = element("div", "ar-summary-row");
        const dd = element("dd");
        if (value instanceof Node) dd.append(value);
        else dd.textContent = value;
        row.append(element("dt", "", label), dd);
        return row;
      }),
    );
    // Le critère est déjà une ligne repliée : pas de libellé en double.
    summaryList.lastElementChild.querySelector("dt").classList.add("sr-only");
  }

  const terminalCount = () => [...state.lanes.values()].filter((lane) => TERMINAL.has(lane.status)).length;

  // Le chronomètre est local (AD-20) ; la vitesse du simulateur l'accélère comme le reste.
  function tickTimer() {
    if (state.startedAt === null || state.mode !== "running") return;
    bannerTimer.textContent = formatDuration(Math.max(0, Math.floor(((Date.now() - state.startedAt) / 1000) * speedOf())));
  }

  function renderBanner() {
    const vars = { done: terminalCount(), total: state.order.length };
    let text;
    if (state.mode === "running") text = t(state.stopping ? "arene.banner.stopping" : "arene.banner.running", vars);
    else if (state.reopenedAt) {
      text = t("arene.banner.reopened", { date: formatDate(state.reopenedAt), time: formatTime(state.reopenedAt), count: state.order.length });
    } else if (state.status === "ok") text = t("arene.banner.ok", vars);
    else text = t(`arene.banner.${state.status === "cancelled" ? "cancelled" : state.status === "interrupted" ? "interrupted" : "error"}`, vars);
    bannerText.textContent = text;
    stop.disabled = state.stopping;
    banner.dataset.state = state.mode === "running" ? "running" : state.status ?? "";
    if (state.mode === "done") bannerTimer.textContent = state.durationS == null ? "" : formatDuration(state.durationS);
    else tickTimer();
    runError.hidden = !runError.error;
    firstLoad.hidden = state.mode !== "running" || ![...state.lanes.values()].some((lane) => lane.status === "loading");
  }

  // --- Résultats ---------------------------------------------------------------------------------
  const rankedLanes = () =>
    [...state.lanes.values()]
      .filter((lane) => typeof lane.score === "number")
      .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name, "fr-FR"));
  const unrankedLanes = () =>
    [...state.lanes.values()].filter((lane) => typeof lane.score !== "number" && (state.mode === "done" || TERMINAL.has(lane.status)));

  function smallestLabel(lane, ranked) {
    // « le plus petit des trois » : seulement quand tous les paramètres actifs sont connus.
    const all = [...state.lanes.values()];
    if (state.mode !== "done" || all.length < 2 || all.some((candidate) => candidate.params == null)) return null;
    const min = Math.min(...all.map((candidate) => candidate.params));
    const winner = ranked[0];
    if (winner !== lane || lane.params !== min || all.filter((candidate) => candidate.params === min).length > 1) return null;
    return t("arene.results.smallest", { count: WORDS[all.length] ?? String(all.length) });
  }

  function reasonFor(lane) {
    if (lane.score === null && lane.status === "done") return lane.reason;
    return t(`arene.results.reason_${lane.status === "waiting" || lane.status === "loading" || lane.status === "generating" || lane.status === "judging" ? "pending" : lane.status}`);
  }

  function renderRanking() {
    const ranked = rankedLanes();
    const others = unrankedLanes();
    const children = [element("h2", "", t("arene.results.ranking"))];
    children.push(element("p", "help", state.mode === "done" ? t("arene.results.frozen") : t("arene.results.ranking_help")));
    if (state.judge) {
      const line = element("p", "ar-judge-line");
      const badge = document.createElement("wl-badge");
      badge.setAttribute("kind", ["local", "cloud"].includes(state.judge.origin) ? state.judge.origin : "unknown");
      const single = document.createElement("wl-badge");
      single.setAttribute("kind", "single-judge");
      line.append(element("span", "", t("arene.results.judge_line", { name: state.judge.name })), badge, single);
      children.push(line);
      if (typeof state.judge.params_active_b === "number" && state.judge.params_active_b < WEAK_JUDGE_B) {
        children.push(ctx.states.notice(`${t("arene.config.judge_weak")}`, { tone: "warning" }));
      }
    }
    if (state.status === "cancelled" || state.status === "interrupted") children.push(ctx.states.notice(t("arene.results.partial"), { tone: "info" }));
    if (ranked.length) {
      const list = element("ol", "ar-rank");
      ranked.forEach((lane, index) => {
        const item = element("li", "ar-rank-item");
        item.dataset.tag = lane.tag;
        const badge = document.createElement("wl-badge");
        badge.setAttribute("kind", ["local", "cloud"].includes(lane.origin) ? lane.origin : "unknown");
        const rank = element("span", "ar-rank-n", String(index + 1));
        rank.setAttribute("aria-label", t("arene.results.rank", { rank: index + 1 }));
        const name = element("strong", "ar-rank-name", lane.name);
        const facts = element("span", "ar-rank-facts");
        facts.append(
          element("span", "ar-rank-score", formatScore(lane.score)),
          element("span", "", lane.metrics ? formatRate(lane.metrics.tps) : ""),
          lane.metrics ? ctx.states.co2Value(lane.metrics.co2) : element("span"),
        );
        item.append(rank, name, badge, facts);
        const label = smallestLabel(lane, ranked);
        if (label) item.append(element("span", "ar-tag", label));
        list.append(item);
      });
      children.push(list);
    } else {
      children.push(element("p", "help", t("arene.results.none_yet")));
    }
    if (others.length) {
      children.push(element("h3", "ar-unranked-title", t("arene.results.unranked")));
      const list = element("ul", "ar-unranked");
      for (const lane of others) {
        const item = element("li", "ar-unranked-item");
        const badge = document.createElement("wl-badge");
        badge.setAttribute("kind", ["local", "cloud"].includes(lane.origin) ? lane.origin : "unknown");
        const reason = lane.score === null && lane.status === "done"
          ? ctx.states.scoreValue(null, lane.reason)
          : element("span", "ar-unranked-reason", t("arene.results.unranked_line", { status: t(`arene.status.${lane.status}`), reason: reasonFor(lane) }));
        item.append(element("strong", "", lane.name), badge, reason);
        list.append(item);
      }
      children.push(list);
    }
    rankingSection.replaceChildren(...children);
  }

  // Matrice : nuage de points SVG fait main (UX-DR14), titre et description, lien vers le tableau.
  function buildChart(lanesList) {
    const plotted = lanesList.filter((lane) => typeof lane.score === "number" && typeof lane.metrics?.tps === "number");
    const missing = lanesList.filter((lane) => !plotted.includes(lane));
    const wrap = element("div", "ar-chart");
    if (!plotted.length) {
      wrap.append(element("p", "help", t("arene.chart.empty")));
      return wrap;
    }
    const W = 560;
    const H = 340;
    const M = { left: 58, right: 24, top: 18, bottom: 54 };
    const maxTps = Math.max(...plotted.map((lane) => lane.metrics.tps));
    const step = maxTps * 1.15 <= 100 ? 20 : maxTps * 1.15 <= 250 ? 50 : 100;
    const xMax = Math.max(step * 2, Math.ceil((maxTps * 1.15) / step) * step);
    const x = (value) => M.left + (value / xMax) * (W - M.left - M.right);
    const y = (value) => H - M.bottom - (value / 100) * (H - M.top - M.bottom);
    const co2Values = plotted.map((lane) => lane.metrics.co2?.mg).filter((value) => typeof value === "number");
    const group = co2Group(co2Values);
    const maxCo2 = Math.max(...co2Values, 0.0001);
    const minCo2 = Math.min(...co2Values, maxCo2);
    const radius = (mg) => 7 + 15 * Math.sqrt(mg / maxCo2);

    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("class", "ar-svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-labelledby", `${uid}-svg-title ${uid}-svg-desc`);
    const add = (tag, attrs = {}, text = null, parent = svg) => {
      const node = document.createElementNS(SVG_NS, tag);
      for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
      if (text !== null) node.textContent = text;
      parent.append(node);
      return node;
    };
    const points = plotted
      .map((lane) =>
        t("arene.chart.point", {
          name: lane.name,
          score: formatScore(lane.score),
          rate: formatRate(lane.metrics.tps),
          co2: co2Display(lane.metrics.co2).value,
        }),
      )
      .join(" ");
    add("title", { id: `${uid}-svg-title` }, t("arene.chart.svg_title"));
    add("desc", { id: `${uid}-svg-desc` }, t("arene.chart.svg_desc", { points }));
    // Axes et repères.
    for (let value = 0; value <= 100; value += 20) {
      add("line", { x1: M.left, x2: W - M.right, y1: y(value), y2: y(value), class: "ar-grid" });
      add("text", { x: M.left - 8, y: y(value) + 4, class: "ar-tick", "text-anchor": "end" }, formatInteger(value));
    }
    for (let value = 0; value <= xMax; value += step) {
      add("line", { x1: x(value), x2: x(value), y1: M.top, y2: H - M.bottom, class: "ar-grid" });
      add("text", { x: x(value), y: H - M.bottom + 18, class: "ar-tick", "text-anchor": "middle" }, formatInteger(value));
    }
    add("line", { x1: M.left, x2: W - M.right, y1: y(0), y2: y(0), class: "ar-axis" });
    add("line", { x1: M.left, x2: M.left, y1: M.top, y2: y(0), class: "ar-axis" });
    add("text", { x: (M.left + W - M.right) / 2, y: H - 10, class: "ar-axis-title", "text-anchor": "middle" }, t("arene.chart.x_axis"));
    add("text", { x: 14, y: (M.top + y(0)) / 2, class: "ar-axis-title", "text-anchor": "middle", transform: `rotate(-90 14 ${(M.top + y(0)) / 2})` }, t("arene.chart.y_axis"));
    // Points, étiquetés par le nom complet du modèle.
    const labels = [];
    plotted.forEach((lane) => {
      const mg = lane.metrics.co2?.mg;
      const known = typeof mg === "number";
      const r = known ? radius(mg) : 9;
      const cx = x(lane.metrics.tps);
      const cy = y(lane.score);
      const color = `var(--color-chart-${(lane.index % 4) + 1})`;
      add("circle", { cx, cy, r, class: known ? "ar-dot" : "ar-dot is-unknown", style: `--dot: ${color}` });
      labels.push({ lane, cx, cy, r });
    });
    labels.sort((a, b) => a.cy - b.cy);
    labels.forEach((label, index) => {
      const nearRight = label.cx > W - M.right - 150;
      label.ly = label.cy - label.r - 6;
      if (index > 0) {
        const previous = labels[index - 1];
        if (Math.abs(label.ly - previous.ly) < 15 && Math.abs(label.cx - previous.cx) < 150) label.ly = previous.ly + 15;
      }
      add("text", { x: nearRight ? label.cx + label.r : label.cx - label.r, y: label.ly, class: "ar-dot-label", "text-anchor": nearRight ? "end" : "start" }, label.lane.name);
    });
    wrap.append(svg);

    // Légende de taille (HTML : lisible par un lecteur d'écran) et lien vers le tableau.
    const legendBox = element("div", "ar-size-legend");
    legendBox.append(element("p", "ar-size-title", t("arene.chart.size_legend")));
    const sizes = element("ul", "ar-sizes");
    const sizeItem = (mg, dashed = false, text = null) => {
      const item = element("li", "ar-size");
      const dot = document.createElementNS(SVG_NS, "svg");
      dot.setAttribute("class", "ar-size-dot");
      dot.setAttribute("viewBox", "0 0 44 44");
      dot.setAttribute("aria-hidden", "true");
      add("circle", { cx: 22, cy: 22, r: dashed ? 9 : Math.min(21, radius(mg)), class: dashed ? "ar-dot is-unknown" : "ar-dot", style: "--dot: var(--color-gray-graphic)" }, null, dot);
      item.append(dot, element("span", "", text ?? group.format(mg)));
      return item;
    };
    if (co2Values.length) {
      sizes.append(sizeItem(minCo2));
      if (maxCo2 !== minCo2) sizes.append(sizeItem(maxCo2));
    }
    if (plotted.some((lane) => typeof lane.metrics.co2?.mg !== "number")) sizes.append(sizeItem(0, true, t("arene.chart.size_unmeasurable")));
    legendBox.append(sizes);
    if (co2Values.length) legendBox.append(element("p", "help", t("arene.chart.same_unit", { unit: group.unit })));
    const seeTable = element("button", "btn ar-see-table", t("arene.chart.see_table"));
    seeTable.type = "button";
    seeTable.addEventListener("click", () => {
      chartSegments.select("table");
      chartSection.querySelector(".ar-table-wrap")?.focus();
    });
    wrap.append(legendBox, seeTable);
    if (missing.length) wrap.append(element("p", "help", t("arene.chart.not_plotted", { names: missing.map((lane) => lane.name).join(", ") })));
    return wrap;
  }

  function buildTable(lanesList) {
    const group = co2Group(lanesList.map((lane) => lane.metrics?.co2?.mg).filter((value) => typeof value === "number"));
    const ranked = rankedLanes();
    const rows = [...ranked, ...unrankedLanes()];
    return dataTable({
      caption: t("arene.chart.caption"),
      columns: [
        { key: "name", label: t("arene.chart.col_model"), header: true, value: (lane) => lane.name, cell: (lane) => lane.name },
        {
          key: "origin",
          label: t("arene.chart.col_origin"),
          cell: (lane) => {
            const badge = document.createElement("wl-badge");
            badge.setAttribute("kind", ["local", "cloud"].includes(lane.origin) ? lane.origin : "unknown");
            return badge;
          },
        },
        {
          key: "score",
          label: t("arene.chart.col_score"),
          value: (lane) => (typeof lane.score === "number" ? lane.score : null),
          cell: (lane) => (lane.score === undefined ? t(`arene.status.${lane.status}`) : ctx.states.scoreValue(lane.score, lane.reason)),
        },
        { key: "rate", label: t("arene.chart.col_rate"), value: (lane) => lane.metrics?.tps ?? null, cell: (lane) => (lane.metrics ? formatRate(lane.metrics.tps) : t(`arene.status.${lane.status}`)) },
        {
          key: "co2",
          label: t("arene.chart.col_co2"),
          value: (lane) => lane.metrics?.co2?.mg ?? null,
          cell: (lane) => (lane.metrics ? tableCo2(lane.metrics.co2, group) : t(`arene.status.${lane.status}`)),
        },
        {
          key: "load",
          label: t("arene.chart.col_load"),
          value: (lane) => lane.metrics?.load_s ?? null,
          cell: (lane) => (lane.metrics ? (lane.origin === "cloud" ? t("arene.chart.not_applicable") : lane.metrics.load_s == null ? t("arene.lanes.already_loaded") : formatDuration(lane.metrics.load_s)) : t(`arene.status.${lane.status}`)),
        },
        { key: "total", label: t("arene.chart.col_total"), value: (lane) => lane.metrics?.total_s ?? null, cell: (lane) => (lane.metrics ? formatDuration(lane.metrics.total_s) : t(`arene.status.${lane.status}`)) },
      ],
      rows,
      className: "ar",
      sortLabel: (column) => t("arene.chart.sort_by", { column }),
    });
  }

  // CO₂ dans l'unité commune de la comparaison ; « non mesurable » et « estimé » en texte.
  function tableCo2(co2, group) {
    const display = co2Display(co2);
    if (display.kind === "unmeasurable") return ctx.states.co2Value(co2);
    const wrap = element("span", "wl-co2");
    wrap.dataset.kind = display.kind;
    wrap.append(element("span", "wl-co2-value", co2.estimated ? t("co2.estimated_value", { value: group.format(co2.mg) }) : group.format(co2.mg)));
    return wrap;
  }

  let chartSegments = null;
  function renderChartSection() {
    const lanesList = [...state.lanes.values()];
    const hasResult = lanesList.some((lane) => lane.metrics);
    const children = [element("h2", "", t("arene.chart.title"))];
    chartSegments = segments({
      label: t("arene.chart.segment_label"),
      options: [
        { value: "matrix", label: t("arene.chart.matrix") },
        { value: "table", label: t("arene.chart.table") },
      ],
      value: state.segment,
      onChange: (value) => {
        state.segment = value;
        renderChartBody();
      },
    });
    const body = element("div", "ar-chart-body");
    body.dataset.role = "chart-body";
    const defs = element("details", "ar-details");
    defs.append(
      element("summary", "", t("arene.chart.defs_title")),
      ...["score", "rate", "load", "co2"].map((key) => element("p", "help", t(`arene.chart.def_${key}`))),
    );
    children.push(chartSegments.root, body, defs);
    chartSection.replaceChildren(...children);
    chartSection.hidden = !hasResult && !lanesList.some((lane) => lane.score !== undefined);
    renderChartBody();
  }

  function renderChartBody() {
    const body = chartSection.querySelector('[data-role="chart-body"]');
    if (!body) return;
    const lanesList = [...state.lanes.values()];
    body.replaceChildren(state.segment === "matrix" ? buildChart(lanesList) : buildTable(lanesList));
  }

  function renderVerdict() {
    const verdict = state.verdict;
    verdictSection.hidden = !verdict || state.mode !== "done";
    if (verdictSection.hidden) {
      verdictSection.replaceChildren();
      return;
    }
    const gap = Math.abs(verdict.local.score - verdict.cloud.score);
    const scoreVars = { local: verdict.local.name, cloud: verdict.cloud.name, localScore: formatScore(verdict.local.score), cloudScore: formatScore(verdict.cloud.score), gap: plural("arene.verdict.points", gap, { count: formatInteger(gap) }) };
    const scoreText = gap === 0 ? t("arene.verdict.score_tie", scoreVars) : t(verdict.local.score > verdict.cloud.score ? "arene.verdict.score_local" : "arene.verdict.score_cloud", scoreVars);
    const costText =
      verdict.cloud.cost_eur == null
        ? `${t("arene.verdict.cost_text", { local: euro(0), cloud: t("arene.verdict.cost_unknown"), name: verdict.cloud.name })} ${t("arene.verdict.cost_unknown_reason", { name: verdict.cloud.name, date: formatDate(verdict.price_table_date) })}`
        : `${t("arene.verdict.cost_text", { local: euro(0), cloud: euro(verdict.cloud.cost_eur), name: verdict.cloud.name })} ${t("arene.verdict.price_date", { date: formatDate(verdict.price_table_date) })}`;
    const group = co2Group([verdict.local.co2?.mg, verdict.cloud.co2?.mg].filter((value) => typeof value === "number"));
    const co2Text = (co2) => (co2 && typeof co2.mg === "number" ? (co2.estimated ? t("co2.estimated_value", { value: group.format(co2.mg) }) : group.format(co2.mg)) : t("co2.unmeasurable"));
    const rows = [
      [t("arene.verdict.score"), scoreText],
      [t("arene.verdict.cost"), costText],
      [t("arene.verdict.co2"), t("arene.verdict.co2_text", { local: co2Text(verdict.local.co2), cloud: co2Text(verdict.cloud.co2), name: verdict.cloud.name })],
      [t("arene.verdict.data"), plural("arene.verdict.data", verdict.local_models, { count: formatInteger(verdict.local_models) })],
    ];
    const list = element("dl", "ar-verdict-list");
    for (const [label, value] of rows) {
      const row = element("div", "ar-verdict-row");
      row.append(element("dt", "", label), element("dd", "", value));
      list.append(row);
    }
    verdictSection.replaceChildren(element("h2", "", t("arene.verdict.title")), element("p", "help", t("arene.verdict.help")), list);
  }

  function renderActions() {
    actionsSection.hidden = state.mode !== "done";
    if (actionsSection.hidden) return;
    const rerun = element("button", "btn btn-primary", "");
    rerun.type = "button";
    rerun.append(localIcon("replay"), element("span", "", t("arene.actions.rerun")));
    rerun.addEventListener("click", () => resume({ launch: true }));
    const edit = element("button", "btn", "");
    edit.type = "button";
    edit.append(localIcon("edit"), element("span", "", t("arene.actions.edit")));
    edit.addEventListener("click", () => resume({ launch: false }));
    const exportRow = element("div", "ar-export");
    exportRow.setAttribute("role", "group");
    exportRow.setAttribute("aria-label", t("arene.actions.export_group"));
    for (const kind of ["csv", "md"]) {
      const button = element("button", "btn", "");
      button.type = "button";
      button.append(localIcon("download"), element("span", "", t(`arene.actions.export_${kind}`)));
      button.addEventListener("click", () => exportRun(kind));
      exportRow.append(button);
    }
    const status = element("p", "help ar-export-status");
    status.setAttribute("role", "status");
    status.dataset.role = "export-status";
    const row = element("div", "ar-actions-row");
    row.append(rerun, edit, exportRow);
    actionsSection.replaceChildren(element("h2", "sr-only", t("arene.actions.title")), row, status);
  }

  function renderResults() {
    renderRanking();
    renderChartSection();
    renderVerdict();
    renderActions();
    const any = [...state.lanes.values()].some((lane) => TERMINAL.has(lane.status) || lane.score !== undefined);
    resultsSection.hidden = !(state.mode === "done" || any) || !["running", "done"].includes(state.mode);
    rankingSection.hidden = resultsSection.hidden;
  }

  // --- Exports (story 3.6) : note et raison, débit et source, CO₂ et méthode, preuve, sans clé d'API
  function exportRun(kind) {
    const lanes = state.order.map((tag) => state.lanes.get(tag));
    const num = (value) => (value == null ? "" : String(value).replace(".", ","));
    const cell = (value) => {
      const text = String(value ?? "");
      return /[;"\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const model = (lane) => ({
      status: t(`arene.status.${lane.status}`),
      score: typeof lane.score === "number" ? num(lane.score) : t("format.not_evaluated"),
      reason: lane.reason ?? "",
    });
    const date = state.reopenedAt ?? (state.startedAt ? new Date(state.startedAt).toISOString() : "");
    const proof = [
      [t("arene.export.machine"), data.machine],
      [t("arene.export.ollama"), store.get().ollama.version ?? t("format.unknown")],
      [t("arene.export.digests"), lanes.filter((l) => l.origin !== "cloud").map((l) => `${l.tag} ${data.digests[l.tag] ?? t("format.unknown")}`).join(" ; ")],
      [t("arene.export.co2_method"), t("arene.export.co2_method_text")],
      [t("arene.export.judge"), state.judge?.name ?? ""],
      [t("arene.export.criteria"), state.criteria],
    ];
    let content;
    if (kind === "csv") {
      const head = [t("arene.chart.col_model"), t("arene.chart.col_origin"), t("arene.chart.col_score"), t("arene.export.col_reason"), t("arene.chart.col_rate"), t("arene.export.col_rate_source"), t("arene.chart.col_co2"), t("arene.export.col_method"), t("arene.chart.col_load"), t("arene.chart.col_total"), t("arene.export.col_status")];
      const body = lanes.map((lane) => {
        const info = model(lane);
        const m = lane.metrics;
        return [lane.name, lane.origin, info.score, info.reason, num(m?.tps), m?.tps_source ?? "", num(m?.co2?.mg), m?.co2?.method ?? "", num(m?.load_s), num(m?.total_s), info.status].map(cell).join(";");
      });
      content = [head.map(cell).join(";"), ...body, "", ...proof.map(([label, value]) => `${cell(label)};${cell(value)}`), t("arene.export.no_key")].join("\n");
    } else {
      const head = `| ${[t("arene.chart.col_model"), t("arene.chart.col_origin"), t("arene.chart.col_score"), t("arene.chart.col_rate"), t("arene.chart.col_co2"), t("arene.export.col_status")].join(" | ")} |`;
      const rule = "| --- | --- | --- | --- | --- | --- |";
      const body = lanes.map((lane) => {
        const info = model(lane);
        const m = lane.metrics;
        return `| ${[lane.name, lane.origin, info.score + (info.reason ? ` (${info.reason})` : ""), m ? formatRate(m.tps) : "", m ? co2Display(m.co2).value : "", info.status].join(" | ")} |`;
      });
      content = [`# ${t("arene.export.title")}`, "", `**${t("arene.export.question")}** : ${state.prompt}`, `**${t("arene.export.date")}** : ${date}`, "", head, rule, ...body, "", `## ${t("arene.export.proof")}`, ...proof.map(([label, value]) => `- **${label}** : ${value}`), `- ${t("arene.export.no_key")}`, ""].join("\n");
    }
    const blob = new Blob([content], { type: kind === "csv" ? "text/csv" : "text/markdown" });
    const link = element("a");
    link.href = URL.createObjectURL(blob);
    link.download = `comparaison.${kind}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    const status = actionsSection.querySelector('[data-role="export-status"]');
    if (status) status.textContent = t("arene.actions.export_done", { format: kind === "csv" ? "CSV" : "Markdown" });
  }

  // --- Flux --------------------------------------------------------------------------------------
  const lane = (data_) => state.lanes.get(data_?.lane);

  function refresh() {
    renderBanner();
    renderResults();
    layoutLanes();
  }

  const handlers = {
    "*": (_data, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (payload, envelope) => {
      const started = Date.parse(envelope.ts);
      state.startedAt = Number.isNaN(started) ? Date.now() : Math.min(started, Date.now());
      clearInterval(timerId);
      timerId = setInterval(tickTimer, 250);
      renderBanner();
    },
    lane_status: (payload) => {
      const target = lane(payload);
      if (!target) return;
      target.status = payload.status;
      if (payload.error) target.error = payload.error;
      if (payload.status === "loading") loaded.add(target.tag);
      renderLane(target);
      renderBanner();
      if (compact.matches) layoutLanes();
      if (TERMINAL.has(payload.status)) renderResults();
    },
    token: (payload) => {
      const target = lane(payload);
      if (!target || payload.channel === "thought") return;
      target.text += payload.text;
      target.chars += payload.text.length;
      target.firstTokenAt ??= performance.now();
      const seconds = ((performance.now() - target.firstTokenAt) / 1000) * speedOf();
      target.provisional = seconds > 0.3 ? target.chars / 4 / seconds : null;
      scheduleLane(target);
    },
    metrics: (payload) => {
      const target = lane(payload);
      if (!target) return;
      target.metrics = payload;
      target.provisional = null;
      renderLane(target);
    },
    judge_score: (payload) => {
      const target = lane(payload);
      if (!target) return;
      target.score = payload.score;
      target.reason = payload.reason ?? "";
      renderLane(target);
      renderResults();
    },
    run_ended: (payload) => finish(payload?.status ?? "error", payload ?? {}),
  };

  function finish(status, payload) {
    clearInterval(timerId);
    timerId = null;
    for (const item of state.lanes.values()) {
      if (!TERMINAL.has(item.status)) item.status = status === "interrupted" ? "interrupted" : "cancelled";
      clearTimeout(item.renderTimer);
    }
    state.status = status;
    state.stopping = false;
    state.durationS = state.startedAt ? Math.round(((Date.now() - state.startedAt) / 100) * speedOf()) / 10 : null;
    runError.error = payload.error ?? null;
    state.verdict = status === "ok" ? serverVerdict(data, [...state.lanes.values()]) : null;
    attachment?.close();
    attachment = null;
    run = null;
    setMode("done");
    refresh();
    snapshot();
    const ranked = rankedLanes();
    const base = status === "ok" ? t("arene.announce.done", { count: state.order.length }) : t(`arene.announce.${status === "cancelled" ? "cancelled" : status === "interrupted" ? "interrupted" : "failed"}`);
    ctx.announce(ranked.length && status === "ok" ? `${base} ${t("arene.announce.winner", { name: ranked[0].name, score: formatScore(ranked[0].score) })}` : base);
  }

  // Instantané conservé : la comparaison se rouvre par son adresse sans relancer de modèle.
  function snapshot() {
    if (!state.runId || reopenId) return;
    saved.set(state.runId, {
      status: state.status,
      startedAt: new Date(state.startedAt ?? Date.now()).toISOString(),
      durationS: state.durationS,
      prompt: state.prompt,
      judge: state.judge?.tag,
      criteria: state.criteria,
      models: [...state.order],
      lanes: Object.fromEntries(state.order.map((tag) => {
        const item = state.lanes.get(tag);
        return [tag, { status: item.status, text: item.text, metrics: item.metrics, score: item.score, reason: item.reason, error: item.error }];
      })),
      verdict: state.verdict,
    });
    if (slug === "arene") history.replaceState(null, "", `#${CONFIG_PATH}/${state.runId}`);
  }

  function follow(simRun, { after = 0 } = {}) {
    run = simRun;
    state.runId = simRun.id;
    lastSeq = after;
    state.stopping = false;
    runError.error = null;
    state.status = null;
    state.reopenedAt = null;
    state.verdict = null;
    state.startedAt = null;
    setMode("running");
    attachment = simRun.attach(handlers, { after });
    refresh();
    return simRun;
  }

  async function stopRun() {
    if (!run || state.stopping) return;
    state.stopping = true;
    renderBanner();
    await sim.cancel(run.id);
  }
  stop.addEventListener("click", stopRun);
  const onKey = (event) => {
    if (event.key !== "Escape" || event.defaultPrevented || state.mode !== "running" || host.hidden) return;
    if (document.querySelector("dialog[open]")) return;
    event.preventDefault();
    stopRun();
  };
  document.addEventListener("keydown", onKey);

  // --- Lancer ------------------------------------------------------------------------------------
  async function submit(options = {}) {
    if (state.mode === "running") return null;
    const tags = chosenModels();
    if (tags.length < MIN_MODELS || tags.length > MAX_MODELS) return null;
    const prompt = question.value.trim();
    if (!prompt) {
      question.focus();
      return null;
    }
    configError.error = null;
    notices.replaceChildren();
    const models = await Promise.all(tags.map((tag) => findModel(tag)));
    const judge = await findModel(judgePicker.value);
    if (models.some((m) => !m) || !judge) return null;
    // Ce que `POST /api/arena/runs` refuserait avant de créer le run (un seul run Arène à la fois).
    let refused = null;
    for (const candidate of [...models, judge]) {
      refused = sim.precheck({ origin: candidate.origin, kind: "arena", model: candidate });
      if (refused) break;
    }
    if (refused?.code === "run_busy") {
      const other = sim.get(refused.detail.run_id);
      const vars = other?.options.vars ?? {};
      await ensureLanes(vars.models ?? tags, { prompt: vars.prompt ?? prompt, judge: vars.judge ?? judge.tag, criteria: vars.criteria ?? criteria.value });
      notices.replaceChildren(ctx.states.joinedNotice());
      return follow(other);
    }
    if (refused) {
      configError.error = refused; // la question et le choix des modèles restent en place
      return null;
    }
    const cfg = { prompt, judge: judge.tag, criteria: criteria.value };
    await ensureLanes(tags, cfg);
    const vars = buildVars({ data, models, judge, prompt, criteria: criteria.value, outcomes: options.outcomes, judgeDown: options.judgeDown, loaded });
    const simRun = sim.play("arene-comparaison", null, {
      vars,
      kind: "arena",
      origin: models.some((m) => m.origin === "cloud") ? "cloud" : "local",
      module: "arena",
    });
    return follow(simRun);
  }

  // « Relancer » et « Modifier la question » reprennent la configuration.
  function resume({ launch: launchNow }) {
    const cfg = currentConfig();
    if (reopenId || state.reopenedAt) {
      pending = { ...cfg, launch: launchNow };
      ctx.navigate(CONFIG_PATH);
      return;
    }
    if (location.hash !== `#${CONFIG_PATH}`) history.replaceState(null, "", `#${CONFIG_PATH}`);
    runError.error = null;
    notices.replaceChildren();
    clearLanes();
    state.status = null;
    state.verdict = null;
    setMode("config");
    applyConfig(cfg);
    if (launchNow) submit();
    else question.focus();
  }

  config.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });

  configError.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "allow_cloud") {
      store.set({ allowCloud: true });
      configError.error = null;
    } else if (id === "use_local" || id === "choose_other") {
      const locals = (await Promise.all(["gemma4:1b", "qwen3.5:2b", "lfm2.5:1.2b"].map(findModel))).filter(Boolean);
      picker.values = locals.map((m) => m.tag);
      configError.error = null;
    } else if (id === "retry") {
      configError.error = null;
      submit();
    } else if (id === "join") {
      configError.error = null;
      submit();
    } else if (id === "smaller") {
      const suggested = configError.error?.detail?.suggested_model;
      const current = picker.values;
      const bigger = (await Promise.all(current.map(findModel))).filter((m) => m && m.origin !== "cloud").sort((a, b) => (b.needed_gb ?? 0) - (a.needed_gb ?? 0))[0];
      const next = current.filter((tag) => tag !== bigger?.tag);
      if (suggested && !next.includes(suggested)) next.push(suggested);
      picker.values = next;
      setMaquette({ ramGuard: false });
      configError.error = null;
      notices.replaceChildren(ctx.states.notice(t("arene.notice.smaller", { name: (await findModel(suggested))?.name ?? suggested ?? "" }), { tone: "success" }));
      updateLaunch();
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      configError.error = null;
      notices.replaceChildren(ctx.states.notice(t("arene.notice.unloaded"), { tone: "success" }));
    } else if (id === "open_models") {
      ctx.navigate("/modeles");
    }
  });

  // --- Comparaison rouverte ----------------------------------------------------------------------
  async function openSnapshot(snap, { id }) {
    await ensureLanes(snap.models, { prompt: snap.prompt, judge: snap.judge, criteria: snap.criteria });
    for (const tag of snap.models) {
      const item = state.lanes.get(tag);
      const stored = snap.lanes[tag];
      Object.assign(item, { status: stored.status, text: stored.text, metrics: stored.metrics, score: stored.score, reason: stored.reason, error: stored.error });
    }
    state.runId = id;
    state.status = snap.status;
    state.startedAt = Date.parse(snap.startedAt);
    state.durationS = snap.durationS;
    state.reopenedAt = reopenId ? snap.startedAt : null;
    state.verdict = snap.verdict ?? null;
    setMode("done");
    refresh();
    if (reopenId) notices.replaceChildren(ctx.states.notice(t("arene.notice.reopened"), { tone: "info" }));
  }

  async function reopen() {
    const snap = saved.get(reopenId) ?? (await reconstruct(reopenId));
    if (!snap) {
      // `GET /api/runs/{run_id}` répond 404 : enveloppe `run_not_found` du catalogue.
      holder.replaceChildren(
        ctx.states.errorBox("run_not_found", {
          detail: { run_id: reopenId },
          vars: { what: t("arene.missing.what"), new_label: t("arene.missing.action"), new_href: `#${CONFIG_PATH}` },
        }),
      );
      setMode("missing");
      return;
    }
    if (snap.erased) {
      const group = co2Group(snap.erased.map((row) => row.co2?.mg).filter((value) => typeof value === "number"));
      const table = dataTable({
        caption: t("arene.erased.caption"),
        className: "ar",
        columns: [
          { key: "name", label: t("arene.chart.col_model"), header: true, cell: (row) => row.name },
          { key: "co2", label: t("arene.chart.col_co2"), cell: (row) => (row.co2 && typeof row.co2.mg === "number" ? group.format(row.co2.mg) : ctx.states.co2Value(row.co2)) },
        ],
        rows: snap.erased,
      });
      holder.replaceChildren(
        ctx.states.emptyState({
          title: t("arene.erased.title"),
          text: t("arene.erased.text"),
          action: { label: t("arene.erased.action"), href: `#${CONFIG_PATH}` },
        }),
        table,
      );
      setMode("erased");
      return;
    }
    await openSnapshot(snap, { id: reopenId });
  }

  // La base du serveur : reconstruit l'instantané d'un run connu de `donnees/arene.json`.
  async function reconstruct(id) {
    const record = data.runs[id];
    if (!record) return null;
    const models = await Promise.all(record.models.map(async (tag) => (await findModel(tag)) ?? { tag, name: tag, origin: "unknown" }));
    const lanes = {};
    const rows = [];
    for (const m of models) {
      const outcome = record.outcomes[m.tag] ?? "ok";
      const simulated = simulateLane(data, m, outcome);
      const status = outcome === "ok" || outcome === "empty" ? "done" : outcome;
      lanes[m.tag] = { status, text: simulated.text, metrics: simulated.metrics, score: outcome === "ok" ? simulated.score : outcome === "empty" ? null : undefined, reason: simulated.reason, error: laneError(data, m, outcome) };
      rows.push({ name: m.name, co2: simulated.metrics?.co2 ?? null });
    }
    const snap = { status: record.status, startedAt: record.started_at, durationS: record.duration_s, prompt: record.prompt, judge: record.judge, criteria: record.criteria, models: record.models, lanes, verdict: null };
    if (record.erased) return { ...snap, erased: rows };
    if (record.status === "ok") {
      const rebuilt = record.models.map((tag) => {
        const m = models.find((candidate) => candidate.tag === tag);
        return { tag, name: m.name, origin: m.origin, score: lanes[tag].score, metrics: lanes[tag].metrics };
      });
      snap.verdict = serverVerdict(data, rebuilt);
    }
    return snap;
  }

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) ----------------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      attachment?.close();
      attachment = null;
    } else if (run) {
      attachment = run.attach(handlers, { after: lastSeq });
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  view = {
    host,
    slug,
    picker,
    judgePicker,
    question,
    submit,
    get mode() {
      return state.mode;
    },
    get run() {
      return run;
    },
    get status() {
      return state.status;
    },
    get segment() {
      return state.segment;
    },
    get launchDisabled() {
      return launch.disabled;
    },
    lane: (tag) => state.lanes.get(tag) ?? null,
    get lanes() {
      return [...state.lanes.values()];
    },
    textLength: () => [...state.lanes.values()].reduce((sum, item) => Math.max(sum, item.text.length), 0),
    whenReady: pickersReady,
    stop: stopRun,
    async setModels(tags) {
      await waitUntil(() => tags.every((tag) => picker.knows(tag)), 5000);
      picker.values = tags;
    },
    async setJudge(tag) {
      await waitUntil(() => judgePicker.knows(tag), 5000);
      judgePicker.value = tag;
    },
    setQuestion(text) {
      question.value = text;
      updateLaunch();
    },
    showSegment(value) {
      chartSegments?.select(value);
    },
    toggleExpanded(tag) {
      const item = state.lanes.get(tag);
      item.expanded = !item.expanded;
      renderLane(item);
    },
    setFocus(tag) {
      state.focus = tag;
      layoutLanes();
    },
  };

  setMode("config");
  updateJudge();
  updateLaunch();
  if (reopenId) {
    await reopen();
  } else if (pending) {
    const cfg = pending;
    pending = null;
    await pickersReady();
    applyConfig(cfg);
    if (cfg.launch) submit();
    else question.focus();
  }

  return () => {
    view = null;
    clearInterval(timerId);
    visibility.disconnect();
    document.removeEventListener("keydown", onKey);
    compact.removeEventListener("change", layoutLanes);
    guard.dispose?.();
    attachment?.close();
    for (const item of state.lanes.values()) clearTimeout(item.renderTimer);
  };
}

// --- Scénarios ----------------------------------------------------------------------------------

const LOCAL3 = ["gemma4:1b", "qwen3.5:2b", "lfm2.5:1.2b"];

// Repart de l'état d'ouverture, sur la route de configuration, pickers prêts.
async function fresh(ctx, setup = () => {}) {
  await ctx.reset();
  setup();
  if (view && view.slug !== "arene") {
    await ctx.navigate(CONFIG_PATH);
    await waitUntil(() => view !== null && view.slug === "arene");
  }
  await waitUntil(() => view !== null);
  await view.whenReady();
}

async function start(options = {}) {
  if (options.models) await view.setModels(options.models);
  if (options.judge) await view.setJudge(options.judge);
  if (options.prompt) view.setQuestion(options.prompt);
  return view.submit(options);
}

const untilDone = async (simRun) => {
  await simRun?.done;
  await waitUntil(() => view !== null && view.mode === "done");
};
const untilText = (count = 80) => waitUntil(() => view.textLength() >= count);
const untilRanked = (count = 1) => waitUntil(() => view.lanes.filter((item) => typeof item.score === "number").length >= count);

async function reopened(ctx, runId) {
  await ctx.reset();
  await ctx.navigate(`${CONFIG_PATH}/${runId}`);
  await waitUntil(() => view !== null && view.slug === "arene-resultat");
  await waitUntil(() => view.mode !== "config");
}

export const scenarios = [
  {
    id: "moins-de-deux-modeles",
    label: "Un seul modèle choisi : lancement désactivé, « Choisissez au moins 2 modèles »",
    async run(ctx) {
      await fresh(ctx);
      await view.setModels(["qwen3.5:2b"]);
    },
  },
  {
    id: "trop-de-modeles",
    label: "Cinq modèles choisis : lancement désactivé, « Choisissez 4 modèles au plus »",
    async run(ctx) {
      await fresh(ctx);
      await view.setModels([...LOCAL3, "lfm2.5:8b-a1b", "qwen3.6:7b"]);
    },
  },
  {
    id: "trois-locaux-preselectionnes",
    label: "Flow 1 : trois petits modèles locaux présélectionnés, juge local",
    async run(ctx) {
      await fresh(ctx);
    },
  },
  {
    id: "comparaison-en-cours",
    label: "Flow 1 : « Chargement du modèle en mémoire… », puis les colonnes en flux",
    async run(ctx) {
      await fresh(ctx);
      await start();
      await waitUntil(() => view.lanes.some((item) => item.status === "loading" || item.status === "generating"));
      await untilText(120);
    },
  },
  {
    id: "premier-chargement-lent",
    label: "Premier chargement lent du modèle (8 à 26 s)",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ slowLoad: true }));
      await start();
      await waitUntil(() => view.lanes.some((item) => item.status === "loading"));
    },
  },
  {
    id: "resultats-vainqueur-le-plus-petit",
    label: "Flow 1 : résultats, le vainqueur est le plus petit des trois (Local)",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start());
    },
  },
  {
    id: "resultats-tableau",
    label: "Résultats en « Tableau » (triable au clavier)",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start());
      view.showSegment("table");
    },
  },
  {
    id: "reponse-entiere",
    label: "« Afficher toute la réponse » dans une colonne",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start());
      view.toggleExpanded("qwen3.5:2b");
    },
  },
  {
    id: "mode-focus",
    label: "Mode focus : une colonne agrandie",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start());
      view.setFocus("gemma4:1b");
    },
  },
  {
    id: "un-modele-en-delai",
    label: "Un modèle dépasse le délai : « Délai dépassé », les autres continuent, classement sans lui",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start({ outcomes: { "lfm2.5:1.2b": "timeout" } }));
    },
  },
  {
    id: "un-modele-non-evalue",
    label: "Réponse vide : « non évalué (réponse vide) », ni 0/100 ni podium",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start({ outcomes: { "gemma4:1b": "empty" } }));
    },
  },
  {
    id: "juge-indisponible",
    label: "Juge indisponible : toutes les notes « non évalué »",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start({ judgeDown: true }));
    },
  },
  {
    id: "juge-peu-fiable",
    label: "Juge sous 4 milliards de paramètres : « note peu fiable »",
    async run(ctx) {
      await fresh(ctx);
      await view.setJudge("lfm2.5:1.2b");
      await untilDone(await start({ models: ["gemma4:1b", "qwen3.5:2b"] }));
    },
  },
  {
    id: "verdict-local-cloud",
    label: "Deux modèles locaux et un modèle cloud : verdict chiffré (note, coût, CO₂)",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await start({ models: ["gemma4:1b", "qwen3.5:2b", "gpt-5-mini"] }));
    },
  },
  {
    id: "cloud-non-mesurable",
    label: "Modèle Claude : CO₂ « non mesurable » avec sa raison, coût du verdict",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await start({ models: ["gemma4:1b", "claude-haiku-4-5"] }));
    },
  },
  {
    id: "colonne-en-echec",
    label: "Un modèle cloud injoignable : sa colonne dit l'échec, les autres continuent",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await start({ models: ["gemma4:1b", "qwen3.5:2b", "claude-haiku-4-5"], outcomes: { "claude-haiku-4-5": "failed" } }));
    },
  },
  {
    id: "arret",
    label: "Arrêter pendant la comparaison : réponses partielles gardées, « Arrêté »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await start();
      await untilRanked(1);
      await view.stop();
      await untilDone(simRun);
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant la comparaison, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await start();
      await untilText(60);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate(CONFIG_PATH);
      await untilDone(simRun);
    },
  },
  {
    id: "rejoint-409",
    label: "Une comparaison tourne déjà (autre onglet) : 409 rejoint",
    async run(ctx) {
      await fresh(ctx);
      const models = await Promise.all(LOCAL3.map(findModel));
      const judge = await findModel("qwen3.6:7b");
      const data = await ctx.data("arene.json");
      sim.play("arene-comparaison", null, {
        kind: "arena",
        module: "arena",
        vars: buildVars({ data, models, judge, prompt: data.default_prompt, criteria: data.criteria_default }),
      });
      await pause(400);
      await view.submit();
      await untilText(40);
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant la comparaison, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await start();
      await untilText(60);
      simRun.cut(4000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant la comparaison : « Interrompu »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await start();
      await untilText(60);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau et erreur au lancement",
    async run(ctx) {
      await fresh(ctx, () => setOllamaDown(true));
      await view.submit();
    },
  },
  {
    id: "cloud-non-autorise",
    label: "Modèle cloud choisi, cloud désactivé juste avant l'envoi : « Autoriser le cloud »",
    async run(ctx) {
      await fresh(ctx);
      ctx.store.set({ allowCloud: true });
      await view.setModels(["gemma4:1b", "gpt-5-mini"]);
      ctx.store.set({ allowCloud: false });
      await view.submit();
    },
  },
  {
    id: "cloud-retire",
    label: "Cloud désactivé pendant qu'un modèle cloud est choisi : le sélecteur le retire",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await view.setModels(["gemma4:1b", "gpt-5-mini"]);
      ctx.store.set({ allowCloud: false });
      await waitUntil(() => view.picker.querySelector(".wl-picker-notice:not([hidden])") !== null);
    },
  },
  {
    id: "erreur-cle-absente",
    label: "Clé d'API absente (Mistral)",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await view.setModels(["gemma4:1b", "mistral-small-latest"]);
      await view.submit();
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire : question gardée, deux issues",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ ramGuard: true }));
      await view.setModels(["qwen3.6:7b", "qwen3.5:2b"]);
      await view.submit();
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle local installé",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ noLocalModel: true }));
    },
  },
  {
    id: "resultat-rouvert",
    label: "Résultat rouvert depuis son adresse (quatre modèles, un « non évalué », verdict)",
    async run(ctx) {
      await reopened(ctx, "run-arene-demo");
    },
  },
  {
    id: "resultat-rouvert-arrete",
    label: "Résultat rouvert d'une comparaison arrêtée : classement partiel",
    async run(ctx) {
      await reopened(ctx, "run-arene-arrete");
    },
  },
  {
    id: "resultat-efface",
    label: "Résultat rouvert d'une comparaison effacée : seules les mesures de CO₂ restent",
    async run(ctx) {
      await reopened(ctx, "run-arene-efface");
    },
  },
  {
    id: "resultat-introuvable",
    label: "Adresse d'une comparaison inconnue : « Comparaison introuvable »",
    async run(ctx) {
      await reopened(ctx, "run-arene-inconnu");
    },
  },
  {
    id: "modifier-la-question",
    label: "« Modifier la question » depuis un résultat : configuration reprise",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await start());
      view.host.querySelectorAll(".ar-actions-row .btn")[1].click();
      await waitUntil(() => view.mode === "config");
    },
  },
  {
    id: "relancer",
    label: "« Relancer » depuis un résultat rouvert : même configuration, nouvelle exécution",
    async run(ctx) {
      await reopened(ctx, "run-arene-demo");
      ctx.store.set({ allowCloud: true });
      view.host.querySelectorAll(".ar-actions-row .btn")[0].click();
      await waitUntil(() => view !== null && view.slug === "arene" && view.mode === "running", 10000);
      await untilText(60);
    },
  },
];
