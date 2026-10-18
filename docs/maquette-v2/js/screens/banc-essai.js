// Banc d'essai, `#/arene/banc[/<run_id>]` (UX-DR13, UX-DR17, UX-DR29, story 7.4) : lancer un scénario
// prédéfini et savoir si la sortie respecte le format attendu.
//
// - Scénario (liste, description d'une ligne, « Format attendu » lu du schéma, « Entrée » préremplie
//   et modifiable : changer de scénario ne remplace l'entrée que si elle n'a pas été modifiée, sinon
//   « Remplacer par l'exemple du scénario » est proposé).
// - Réglages : `wl-model-picker`, interrupteurs « Format imposé » et « Réponse concise » avec leur aide ;
//   un modèle qui ne peut pas imposer un format désactive l'interrupteur, avec la raison en légende.
// - Résultat : réponse en flux (`wl-run-status` piloté), puis verdict de format en clair, « Sortie mise
//   en forme » et rangée de métriques (débit D3, CO₂, durée). Le verdict est lu dans l'instantané du run
//   à `run_ended` (le serveur valide la sortie, le front ne valide rien) ; l'essai est conservé et se
//   rouvre par `#/arene/banc/<run_id>`.

import { element, icon } from "../core/dom.js";
import { errorEnvelope } from "../core/errors.js";
import { formatDuration, formatNumber } from "../core/format.js";
import { co2Display } from "../core/co2.js";
import { t } from "../core/i18n.js";
import { renderMarkdown } from "../core/markdown.js";
import { setMaquette, store } from "../core/store.js";
import { findModel } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";
import { dataTable } from "../components/data-table.js";

const BASE_PATH = "/arene/banc";
let counter = 0;
let view = null;
const saved = new Map(); // essais terminés pendant cette visite : rouvrables par leur adresse
let pending = null;

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

// --- Ce que le « serveur » rend (le front ne valide ni ne mesure rien) ----------------------------

function outcomeFor(data, scenario, model, force) {
  if (!scenario.schema) return "ok";
  if (force && !data.no_structured_output.includes(model.tag)) return "ok";
  return data.free_outcome[model.tag] ?? "ok";
}

function simulate(data, { scenario, model, force, concise, outcome, loading }) {
  const output = scenario.outputs[outcome] ?? scenario.outputs.ok;
  const full = concise && output.text_concise ? output.text_concise : output.text;
  const base = data.base_metrics[model.tag] ?? data.base_metrics.default;
  const tokens = Math.max(8, Math.round(full.length / 4));
  const evalS = Math.round((tokens / base.tps) * 100) / 100;
  const load = base.origin === "cloud" ? null : loading ? base.load_s : null;
  const mg = Math.round(base.co2_mg_per_s * (base.ttft_s + evalS + (load ?? 0)) * 100) / 100;
  let co2 = { mg, method: "codecarbon", estimated: false, range_mg: null, allocation: "direct", reason: null };
  if (base.co2 === "estimated") co2 = { mg, method: "ecologits", estimated: true, range_mg: { low: Math.round(mg * 70) / 100, high: Math.round(mg * 160) / 100 }, allocation: "direct", reason: null };
  if (base.co2 === "unmeasurable") co2 = { mg: null, method: "unmeasurable", estimated: false, range_mg: null, allocation: "direct", reason: "Anthropic ne publie pas la taille de ce modèle : son empreinte ne peut pas être calculée." };
  return {
    text: full,
    verdict: scenario.schema ? output.verdict : null,
    metrics: { lane: model.tag, ttft_s: base.ttft_s, load_s: load, eval_tokens: tokens, eval_s: evalS, tps: base.tps, tps_source: base.origin === "cloud" ? "wallclock" : "ollama_eval", total_s: Math.round((base.ttft_s + evalS + (load ?? 0)) * 100) / 100, origin: base.origin, co2 },
    partial: output.text.slice(0, Math.max(12, Math.round(output.text.length * 0.4))),
    tps: base.tps,
    loadS: base.load_s,
  };
}

// --- Écran ----------------------------------------------------------------------------------------

export async function mount(host, ctx) {
  const uid = `bc-${++counter}`;
  const data = await ctx.data("banc-essai.json");
  const slug = ctx.route.slug;
  const reopenId = slug === "banc-essai-resultat" ? ctx.params.run_id : null;
  if (!reopenId && /^#\/arene\/banc\/./.test(location.hash)) history.replaceState(null, "", `#${BASE_PATH}`);

  const state = { mode: "config", scenario: data.scenarios[0], text: "", metrics: null, verdict: undefined, status: null, runId: null, model: null, force: false, concise: false, startedAt: null };
  let run = null;
  let attachment = null;
  let lastSeq = 0;
  let wasHidden = host.hidden;
  let provisional = null;
  let chars = 0;
  let firstTokenAt = null;
  const loaded = new Set();

  const guard = ctx.states.ollamaGuard();

  // --- Formulaire --------------------------------------------------------------------------------
  const select = element("select", "bc-select");
  select.id = `${uid}-scenario`;
  for (const scenario of data.scenarios) {
    const option = element("option", "", scenario.label);
    option.value = scenario.id;
    select.append(option);
  }
  select.setAttribute("aria-describedby", `${uid}-scenario-help`);
  const selectLabel = element("label", "bc-label", t("banc.scenario.label"));
  selectLabel.htmlFor = select.id;
  const scenarioHelp = element("p", "help", "");
  scenarioHelp.id = `${uid}-scenario-help`;

  const formatBox = element("details", "bc-details");
  const formatSummary = element("summary", "", t("banc.format.title"));
  const formatBody = element("div", "bc-format-body");
  formatBox.append(formatSummary, formatBody);

  const input = element("textarea", "bc-input");
  input.id = `${uid}-input`;
  input.rows = 3;
  const inputLabel = element("label", "bc-label", t("banc.input.label"));
  inputLabel.htmlFor = input.id;
  const replaceRow = element("div", "bc-replace");
  const replaceNote = element("p", "help", t("banc.input.kept"));
  const replaceButton = element("button", "btn", t("banc.input.replace"));
  replaceButton.type = "button";
  replaceRow.append(replaceNote, replaceButton);
  replaceRow.hidden = true;

  const picker = document.createElement("wl-model-picker");
  picker.setAttribute("purpose", "chat");
  picker.setAttribute("label", t("banc.model"));

  function makeSwitch(key) {
    const row = element("div", "bc-switch");
    const box = element("input", "bc-switch-input");
    box.type = "checkbox";
    box.setAttribute("role", "switch");
    box.id = `${uid}-${key}`;
    box.setAttribute("aria-describedby", `${uid}-${key}-help`);
    const label = element("label", "bc-switch-label", t(`banc.${key}.label`));
    label.htmlFor = box.id;
    const help = element("p", "help bc-switch-help", t(`banc.${key}.help`));
    help.id = `${uid}-${key}-help`;
    const reason = element("p", "bc-switch-reason");
    reason.hidden = true;
    reason.id = `${uid}-${key}-reason`;
    row.append(box, label, help, reason);
    return { row, box, help, reason };
  }
  const forceSwitch = makeSwitch("force");
  const conciseSwitch = makeSwitch("concise");
  const switches = element("div", "bc-switches");
  switches.append(forceSwitch.row, conciseSwitch.row);

  const launch = element("button", "btn btn-primary bc-launch", t("banc.launch"));
  launch.type = "submit";
  const legend = element("p", "help bc-legend");
  legend.id = `${uid}-legend`;
  launch.setAttribute("aria-describedby", legend.id);
  const launchRow = element("div", "bc-launch-row");
  launchRow.append(launch, legend);
  const formError = document.createElement("wl-error");
  formError.setAttribute("alert", "");
  const notices = element("div", "bc-notices");

  const form = element("form", "bc-form");
  form.noValidate = true;
  const settingsGrid = element("div", "bc-settings");
  settingsGrid.append(picker, switches);
  form.append(
    element("h2", "", t("banc.scenario.title")),
    selectLabel,
    select,
    scenarioHelp,
    formatBox,
    inputLabel,
    input,
    replaceRow,
    element("h2", "", t("banc.settings.title")),
    settingsGrid,
    formError,
    launchRow,
  );

  // --- Résultat ----------------------------------------------------------------------------------
  const holder = element("div", "bc-holder");
  const resultSection = element("section", "bc-result");
  const resultTitle = element("h2", "", t("banc.result.title"));
  const status = document.createElement("wl-run-status");
  status.setAttribute("driven", "");
  const firstLoad = element("p", "help", t("states.slow_loading"));
  firstLoad.hidden = true;
  const runError = document.createElement("wl-error");
  runError.setAttribute("alert", "");
  const streamLabel = element("h3", "", t("banc.result.answer"));
  const stream = element("pre", "bc-stream");
  stream.tabIndex = 0;
  stream.setAttribute("aria-labelledby", `${uid}-stream-title`);
  streamLabel.id = `${uid}-stream-title`;
  const verdictBox = element("div", "bc-verdict");
  const formatted = element("div", "bc-formatted");
  const metricsRow = element("div", "bc-metrics");
  const actions = element("div", "bc-actions");
  resultSection.append(resultTitle, status, firstLoad, runError, streamLabel, stream, verdictBox, formatted, metricsRow, actions);

  host.replaceChildren(element("h1", "", ctx.route.title), ctx.tabs(), element("p", "lead", t("banc.lead")), guard, form, notices, holder, resultSection);

  // --- Formulaire : comportement -----------------------------------------------------------------
  function renderScenario() {
    const scenario = state.scenario;
    scenarioHelp.textContent = scenario.description;
    if (scenario.schema) {
      const table = dataTable({
        caption: t("banc.format.caption"),
        className: "bc",
        columns: [
          { key: "field", label: t("banc.format.field"), header: true, cell: (row) => row.field },
          { key: "type", label: t("banc.format.type"), cell: (row) => row.type },
          { key: "required", label: t("banc.format.required"), cell: (row) => t(row.required ? "banc.format.yes" : "banc.format.no") },
        ],
        rows: scenario.schema,
      });
      formatBody.replaceChildren(table);
    } else {
      formatBody.replaceChildren(element("p", "help", t("banc.format.none")));
    }
    updateSwitches();
    updateLaunch();
  }

  function updateSwitches() {
    const model = picker.selected;
    let reason = null;
    if (!state.scenario.schema) reason = t("banc.force.no_schema");
    else if (model && data.no_structured_output.includes(model.tag)) reason = t("banc.force.unsupported", { name: model.name });
    forceSwitch.box.disabled = reason !== null;
    if (reason) forceSwitch.box.checked = false;
    forceSwitch.reason.hidden = reason === null;
    forceSwitch.reason.textContent = reason ?? "";
    forceSwitch.box.setAttribute("aria-describedby", reason ? `${forceSwitch.help.id} ${forceSwitch.reason.id}` : forceSwitch.help.id);
  }

  function updateLaunch() {
    let reason = null;
    if (state.mode === "running") reason = t("banc.legend.running");
    else if (!picker.value) reason = t("banc.legend.model");
    else if (!input.value.trim()) reason = t("banc.legend.input");
    launch.disabled = reason !== null;
    legend.textContent = reason ?? t("banc.legend.ready", { name: picker.selected?.name ?? picker.value, scenario: state.scenario.label });
  }

  const entryModified = () => input.value !== state.scenario.input;

  select.addEventListener("change", () => {
    const next = data.scenarios.find((scenario) => scenario.id === select.value);
    const modified = entryModified();
    state.scenario = next;
    if (modified) replaceRow.hidden = false;
    else {
      input.value = next.input;
      replaceRow.hidden = true;
    }
    renderScenario();
  });
  replaceButton.addEventListener("click", () => {
    input.value = state.scenario.input;
    replaceRow.hidden = true;
    updateLaunch();
    input.focus();
  });
  input.addEventListener("input", updateLaunch);
  picker.addEventListener("wl-model-change", () => {
    updateSwitches();
    updateLaunch();
  });

  const pickerReady = () => waitUntil(() => picker.selected !== null || picker.querySelector("wl-error:not([hidden])"), 5000).catch(() => {});

  // --- Résultat : rendu --------------------------------------------------------------------------
  function metric(label, value, unit, help, { isProvisional = false } = {}) {
    const node = document.createElement("wl-metric");
    node.setAttribute("label", label);
    node.setAttribute("value", value);
    if (unit) node.setAttribute("unit", unit);
    if (help) node.setAttribute("help", help);
    if (isProvisional) node.setAttribute("provisional", "");
    return node;
  }

  function renderMetrics() {
    const m = state.metrics;
    const nodes = [];
    if (m) {
      nodes.push(metric(t("banc.metric.rate"), formatNumber(m.tps), "tokens/s", t("banc.metric.rate_help")));
      const co2 = co2Display(m.co2);
      nodes.push(metric(t("banc.metric.co2"), co2.value, "", co2.help));
      nodes.push(metric(t("banc.metric.total"), formatDuration(m.total_s), "", t("banc.metric.total_help")));
      if (m.origin !== "cloud") nodes.push(metric(t("banc.metric.load"), m.load_s == null ? t("banc.metric.already") : formatDuration(m.load_s), "", t("banc.metric.load_help")));
    } else if (provisional) {
      nodes.push(metric(t("banc.metric.rate"), formatNumber(provisional), "tokens/s", t("banc.metric.rate_help"), { isProvisional: true }));
    }
    metricsRow.replaceChildren(...nodes);
    metricsRow.hidden = nodes.length === 0;
  }

  function verdictLine() {
    const verdict = state.verdict;
    if (verdict === undefined) return [];
    if (verdict === null) return [ctx.states.notice(t("banc.verdict.none"), { tone: "info" })];
    const line = element("p", "bc-verdict-line");
    line.dataset.ok = String(verdict.ok);
    line.setAttribute("role", "status");
    let text;
    if (verdict.ok) text = t("banc.verdict.ok");
    else if (verdict.kind === "missing_field") text = t("banc.verdict.missing", { field: verdict.field });
    else text = t("banc.verdict.not_json");
    line.append(icon(verdict.ok ? "check-circle" : "cancel"), element("span", "", text));
    return [element("h3", "", t("banc.verdict.title")), line];
  }

  function renderFormatted() {
    if (state.mode !== "done" || !state.text || state.status !== "ok") {
      formatted.replaceChildren();
      formatted.hidden = true;
      return;
    }
    formatted.hidden = false;
    const title = element("h3", "", t("banc.formatted.title"));
    let body;
    if (state.scenario.schema && state.verdict && state.verdict.kind !== "not_json") {
      body = element("pre", "bc-json");
      body.tabIndex = 0;
      body.setAttribute("aria-label", t("banc.formatted.title"));
      try {
        body.textContent = JSON.stringify(JSON.parse(state.text), null, 2);
      } catch {
        body.textContent = state.text;
      }
    } else if (state.scenario.schema) {
      body = element("div", "bc-raw");
      body.append(element("p", "help", t("banc.formatted.raw")), element("pre", "bc-json", state.text));
      body.querySelector("pre").tabIndex = 0;
      body.querySelector("pre").setAttribute("aria-label", t("banc.formatted.title"));
    } else {
      body = element("div", "bc-md wl-md");
      body.append(renderMarkdown(state.text));
    }
    formatted.replaceChildren(title, body);
  }

  function renderResult() {
    const live = state.mode === "running" || state.mode === "done";
    resultSection.hidden = !live;
    stream.textContent = state.text;
    stream.hidden = !state.text;
    streamLabel.hidden = !state.text;
    verdictBox.replaceChildren(...(state.mode === "done" && state.status === "ok" ? verdictLine() : []));
    renderFormatted();
    renderMetrics();
    renderActions();
    updateLaunch();
    host.dataset.mode = state.mode;
  }

  function renderActions() {
    actions.hidden = state.mode !== "done";
    if (state.mode !== "done") return;
    const again = element("button", "btn", "");
    again.type = "button";
    again.append(icon("replay"), element("span", "", t("banc.actions.rerun")));
    again.addEventListener("click", () => resume(true));
    const edit = element("button", "btn", "");
    edit.type = "button";
    edit.append(icon("edit"), element("span", "", t("banc.actions.edit")));
    edit.addEventListener("click", () => resume(false));
    actions.replaceChildren(again, edit);
  }

  // --- Lancer ------------------------------------------------------------------------------------
  function currentConfig() {
    return { scenario: state.scenario.id, model: picker.value, input: input.value, force: forceSwitch.box.checked, concise: conciseSwitch.box.checked };
  }

  function applyConfig(cfg) {
    const scenario = data.scenarios.find((candidate) => candidate.id === cfg.scenario) ?? data.scenarios[0];
    state.scenario = scenario;
    select.value = scenario.id;
    input.value = cfg.input;
    replaceRow.hidden = true;
    if (cfg.model) picker.value = cfg.model;
    renderScenario();
    forceSwitch.box.checked = cfg.force && !forceSwitch.box.disabled;
    conciseSwitch.box.checked = cfg.concise;
    updateLaunch();
  }

  async function submit(options = {}) {
    if (state.mode === "running") return null;
    const model = picker.selected ?? (picker.value ? await findModel(picker.value) : null);
    if (!model || !input.value.trim()) return null;
    formError.error = null;
    notices.replaceChildren();
    const refused = sim.precheck({ origin: model.origin, kind: "bench", model });
    if (refused?.code === "run_busy") {
      const other = sim.get(refused.detail.run_id);
      const vars = other?.options.vars ?? {};
      const joinedScenario = data.scenarios.find((candidate) => candidate.id === vars.scenario) ?? state.scenario;
      applyConfig({ scenario: joinedScenario.id, model: vars.tag ?? model.tag, input: vars.input ?? input.value, force: !!vars.force_format, concise: !!vars.concise });
      notices.replaceChildren(ctx.states.joinedNotice());
      return follow(other, { scenario: joinedScenario, model: (await findModel(vars.tag)) ?? model, force: !!vars.force_format, concise: !!vars.concise });
    }
    if (refused) {
      formError.error = refused;
      return null;
    }
    const force = forceSwitch.box.checked && !forceSwitch.box.disabled;
    const concise = conciseSwitch.box.checked;
    const scenario = state.scenario;
    const timeout = options.outcome === "timeout";
    const outcome = timeout ? "ok" : outcomeFor(data, scenario, model, force);
    const loading = model.origin === "local" && !loaded.has(model.tag);
    const sample = simulate(data, { scenario, model, force, concise, outcome, loading });
    const vars = {
      tag: model.tag,
      scenario: scenario.id,
      input: input.value,
      force_format: force,
      concise,
      loading,
      load_s: sample.loadS,
      text: timeout ? sample.partial : sample.text,
      tps: timeout ? 6 : sample.tps,
      metrics: sample.metrics,
      ok: !timeout,
      timed_out: timeout,
      error: timeout ? errorEnvelope("timeout", { detail: { timeout_s: data.lane_timeout_s } }) : null,
      verdict: sample.verdict,
    };
    const simRun = sim.play("banc-essai-reponse", null, { vars, kind: "bench", origin: model.origin, module: "bench", error: options.error, errorAfter: options.errorAfter });
    return follow(simRun, { scenario, model, force, concise });
  }

  function follow(simRun, config, { after = 0 } = {}) {
    run = simRun;
    Object.assign(state, { mode: "running", runId: simRun.id, text: "", metrics: null, verdict: undefined, status: null, model: config.model, force: config.force, concise: config.concise, startedAt: null });
    provisional = null;
    chars = 0;
    firstTokenAt = null;
    lastSeq = after;
    runError.error = null;
    status.runId = simRun.id;
    attachment = simRun.attach(handlers, { after });
    renderResult();
    return simRun;
  }

  const handlers = {
    "*": (_payload, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (_payload, envelope) => {
      status.feed(envelope);
    },
    model_loading: (_payload, envelope) => {
      firstLoad.hidden = false;
      status.feed(envelope);
    },
    model_loaded: (payload, envelope) => {
      firstLoad.hidden = true;
      loaded.add(payload.tag);
      status.feed(envelope);
    },
    token: (payload, envelope) => {
      if (payload.channel === "thought") return;
      state.text += payload.text;
      chars += payload.text.length;
      firstTokenAt ??= performance.now();
      const seconds = ((performance.now() - firstTokenAt) / 1000) * speedOf();
      provisional = seconds > 0.3 ? chars / 4 / seconds : null;
      stream.textContent = state.text;
      stream.hidden = false;
      streamLabel.hidden = false;
      stream.scrollTop = stream.scrollHeight;
      renderMetrics();
      status.feed(envelope);
    },
    metrics: (payload) => {
      state.metrics = payload;
      provisional = null;
    },
    run_ended: (payload, envelope) => {
      status.feed(envelope);
      finish(payload?.status ?? "error", payload ?? {}, simRunVars());
    },
  };

  const simRunVars = () => run?.options.vars ?? {};

  function finish(finalStatus, payload, vars) {
    firstLoad.hidden = true;
    state.status = finalStatus;
    state.mode = "done";
    runError.error = payload.error ?? null;
    // Instantané du run : le serveur a validé la sortie (verdict) ; absent d'un run arrêté ou en erreur.
    state.verdict = finalStatus === "ok" ? (vars.verdict === undefined ? null : vars.verdict) : undefined;
    attachment?.close();
    attachment = null;
    const simRun = run;
    run = null;
    renderResult();
    if (simRun) snapshot(simRun.id);
    const verdict = state.verdict;
    ctx.announce(
      finalStatus === "ok"
        ? verdict === null || verdict === undefined
          ? t("banc.announce.done")
          : verdict.ok
            ? t("banc.announce.ok")
            : t("banc.announce.ko")
        : finalStatus === "cancelled"
          ? t("banc.announce.cancelled")
          : t("banc.announce.failed"),
    );
  }

  function snapshot(id) {
    if (reopenId) return;
    saved.set(id, { scenario: state.scenario.id, model: state.model?.tag, input: input.value, force: state.force, concise: state.concise, text: state.text, metrics: state.metrics, verdict: state.verdict, status: state.status, error: runError.error });
    if (slug === "banc-essai") history.replaceState(null, "", `#${BASE_PATH}/${id}`);
  }

  function resume(launchNow) {
    const cfg = currentConfig();
    if (reopenId) {
      pending = { ...cfg, launch: launchNow };
      ctx.navigate(BASE_PATH);
      return;
    }
    if (location.hash !== `#${BASE_PATH}`) history.replaceState(null, "", `#${BASE_PATH}`);
    Object.assign(state, { mode: "config", text: "", metrics: null, verdict: undefined, status: null });
    runError.error = null;
    renderResult();
    if (launchNow) submit();
    else input.focus();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit();
  });

  formError.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "allow_cloud") {
      store.set({ allowCloud: true });
      formError.error = null;
    } else if (id === "use_local" || id === "choose_other") {
      picker.value = "qwen3.5:2b";
      formError.error = null;
    } else if (id === "retry" || id === "join") {
      formError.error = null;
      submit();
    } else if (id === "smaller") {
      const suggested = formError.error?.detail?.suggested_model;
      if (suggested) picker.value = suggested;
      setMaquette({ ramGuard: false });
      formError.error = null;
      notices.replaceChildren(ctx.states.notice(t("banc.notice.smaller", { name: (await findModel(suggested))?.name ?? suggested ?? "" }), { tone: "success" }));
      updateSwitches();
      updateLaunch();
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      formError.error = null;
      notices.replaceChildren(ctx.states.notice(t("banc.notice.unloaded"), { tone: "success" }));
    } else if (id === "open_models") {
      ctx.navigate("/modeles");
    }
  });

  // Une erreur de run (délai, coupure d'Ollama, fournisseur cloud) : bouton « Réessayer » du catalogue.
  runError.addEventListener("wl-error-action", (event) => {
    if (event.detail.id === "retry") {
      runError.error = null;
      submit();
    } else if (event.detail.id === "use_local") {
      picker.value = "qwen3.5:2b";
      resume(false);
    }
  });

  async function stopRun() {
    if (run) await status.cancel();
  }

  // --- Essai rouvert ------------------------------------------------------------------------------
  async function reconstruct(id) {
    const record = data.runs[id];
    if (!record) return null;
    const scenario = data.scenarios.find((candidate) => candidate.id === record.scenario);
    const model = await findModel(record.model);
    const timeout = record.outcome === "timeout";
    const sample = simulate(data, { scenario, model, force: record.force_format, concise: record.concise, outcome: timeout ? "ok" : record.outcome, loading: true });
    return {
      scenario: scenario.id,
      model: model.tag,
      input: record.input,
      force: record.force_format,
      concise: record.concise,
      text: timeout ? sample.partial : sample.text,
      metrics: timeout ? null : sample.metrics,
      verdict: timeout ? undefined : sample.verdict,
      status: record.status,
      error: timeout ? errorEnvelope("timeout", { detail: { timeout_s: data.lane_timeout_s } }) : null,
    };
  }

  async function reopen() {
    const snap = saved.get(reopenId) ?? (await reconstruct(reopenId));
    if (!snap) {
      holder.replaceChildren(
        ctx.states.errorBox("run_not_found", {
          detail: { run_id: reopenId },
          vars: { what: t("banc.missing.what"), new_label: t("banc.missing.action"), new_href: `#${BASE_PATH}` },
        }),
      );
      form.hidden = true;
      state.mode = "missing";
      renderResult();
      resultSection.hidden = true;
      return;
    }
    await pickerReady();
    applyConfig(snap);
    status.preview(snap.status === "ok" ? "ok" : snap.status === "cancelled" ? "cancelled" : "error", snap.metrics?.total_s ?? 0);
    state.model = await findModel(snap.model);
    Object.assign(state, { mode: "done", text: snap.text, metrics: snap.metrics, verdict: snap.verdict, status: snap.status, runId: reopenId, force: snap.force, concise: snap.concise });
    runError.error = snap.error;
    renderResult();
    notices.replaceChildren(ctx.states.notice(t("banc.notice.reopened"), { tone: "info" }));
  }

  // --- Écran masqué puis revu ---------------------------------------------------------------------
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
    slug,
    host,
    picker,
    input,
    select,
    forceSwitch: forceSwitch.box,
    conciseSwitch: conciseSwitch.box,
    submit,
    stop: stopRun,
    get mode() {
      return state.mode;
    },
    get run() {
      return run;
    },
    get text() {
      return state.text;
    },
    get status() {
      return state.status;
    },
    whenReady: pickerReady,
    async setModel(tag) {
      await waitUntil(() => picker.knows(tag), 5000);
      picker.value = tag;
    },
    chooseScenario(id) {
      select.value = id;
      select.dispatchEvent(new Event("change"));
    },
    setInput(text) {
      input.value = text;
      input.dispatchEvent(new Event("input"));
    },
    setSwitch(key, on) {
      const box = key === "force" ? forceSwitch.box : conciseSwitch.box;
      box.checked = on;
    },
    openFormat() {
      formatBox.open = true;
    },
  };

  state.scenario = data.scenarios[0];
  input.value = state.scenario.input;
  renderScenario();
  renderResult();
  if (reopenId) await reopen();
  else if (pending) {
    const cfg = pending;
    pending = null;
    await pickerReady();
    applyConfig(cfg);
    if (cfg.launch) submit();
    else input.focus();
  }

  return () => {
    view = null;
    visibility.disconnect();
    guard.dispose?.();
    attachment?.close();
  };
}

// --- Scénarios ----------------------------------------------------------------------------------

async function fresh(ctx, setup = () => {}) {
  await ctx.reset();
  setup();
  if (view && view.slug !== "banc-essai") {
    await ctx.navigate(BASE_PATH);
    await waitUntil(() => view !== null && view.slug === "banc-essai");
  }
  await waitUntil(() => view !== null);
  await view.whenReady();
}

async function test(options = {}) {
  if (options.model) await view.setModel(options.model);
  if (options.scenario) view.chooseScenario(options.scenario);
  if (options.input) view.setInput(options.input);
  if ("force" in options) view.setSwitch("force", options.force);
  if ("concise" in options) view.setSwitch("concise", options.concise);
  return view.submit(options);
}

const untilDone = async (simRun) => {
  await simRun?.done;
  await waitUntil(() => view !== null && view.mode === "done");
};
const untilText = (count = 20) => waitUntil(() => view.text.length >= count);

async function reopened(ctx, runId) {
  await ctx.reset();
  await ctx.navigate(`${BASE_PATH}/${runId}`);
  await waitUntil(() => view !== null && view.slug === "banc-essai-resultat");
  await waitUntil(() => view.mode !== "config");
}

export const scenarios = [
  { id: "vide", label: "Scénario prédéfini et entrée préremplie, avant tout essai", run: (ctx) => fresh(ctx) },
  {
    id: "format-attendu",
    label: "« Format attendu » déplié : champs, type, obligatoire",
    async run(ctx) {
      await fresh(ctx);
      view.chooseScenario("extraction");
      view.openFormat();
    },
  },
  {
    id: "entree-modifiee",
    label: "Entrée modifiée puis changement de scénario : « Remplacer par l'exemple du scénario »",
    async run(ctx) {
      await fresh(ctx);
      view.setInput("Ma propre entrée, écrite à la main.");
      view.chooseScenario("traduction");
    },
  },
  {
    id: "format-respecte",
    label: "Format imposé : réponse en flux, « Format respecté », sortie mise en forme, métriques",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await test({ scenario: "extraction", model: "qwen3.5:2b", force: true }));
    },
  },
  {
    id: "format-non-respecte",
    label: "Format non imposé : « Format non respecté : le champ « date » manque »",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await test({ scenario: "extraction", model: "lfm2.5:1.2b", force: false }));
    },
  },
  {
    id: "sortie-non-json",
    label: "Sortie qui n'est pas du JSON : « la sortie n'est pas du JSON valide »",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await test({ scenario: "classification", model: "gemma4:1b" }));
    },
  },
  {
    id: "format-impose-indisponible",
    label: "Modèle sans sortie structurée : « Format imposé » désactivé, raison en légende",
    async run(ctx) {
      await fresh(ctx);
      await view.setModel("gemma4:1b");
    },
  },
  {
    id: "scenario-sans-format",
    label: "Scénario sans format attendu : pas de verdict, sortie en Markdown",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await test({ scenario: "resume", model: "qwen3.5:2b" }));
    },
  },
  {
    id: "reponse-concise",
    label: "Réponse concise : sortie plus courte, durée et CO₂ en baisse",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await test({ scenario: "raisonnement", model: "qwen3.5:2b", concise: true }));
    },
  },
  {
    id: "essai-en-cours",
    label: "Essai en cours : flux, débit provisoire, Arrêter",
    async run(ctx) {
      await fresh(ctx);
      await test({ scenario: "code", model: "qwen3.5:2b" });
      await untilText(60);
    },
  },
  {
    id: "premier-chargement-lent",
    label: "Premier chargement lent du modèle (8 à 26 s)",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ slowLoad: true }));
      await test({ model: "qwen3.5:2b" });
      await waitUntil(() => view.host.querySelector("wl-run-status")?.dataset.stage === "loading");
    },
  },
  {
    id: "arret",
    label: "Arrêter pendant la génération : sortie partielle gardée, « Arrêté »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await test({ scenario: "code", model: "qwen3.5:2b" });
      await untilText(80);
      await view.stop();
      await untilDone(simRun);
    },
  },
  {
    id: "delai-depasse",
    label: "Délai dépassé : sortie partielle et erreur « Délai dépassé »",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await test({ scenario: "extraction", model: "qwen3.6:35b-a3b", outcome: "timeout" }));
    },
  },
  {
    id: "reponse-cloud-non-mesurable",
    label: "Modèle cloud : CO₂ « non mesurable » avec sa raison",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await test({ scenario: "classification", model: "claude-haiku-4-5", force: true }));
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant l'essai, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await test({ scenario: "code", model: "qwen3.5:2b" });
      await untilText(40);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate(BASE_PATH);
      await untilDone(simRun);
    },
  },
  {
    id: "rejoint-409",
    label: "Un essai tourne déjà (autre onglet) : 409 rejoint",
    async run(ctx) {
      await fresh(ctx);
      const data = await ctx.data("banc-essai.json");
      const scenario = data.scenarios[0];
      const model = await findModel("qwen3.5:2b");
      const sample = simulate(data, { scenario, model, force: false, concise: false, outcome: "ok", loading: true });
      sim.play("banc-essai-reponse", null, {
        kind: "bench",
        module: "bench",
        vars: { tag: model.tag, scenario: scenario.id, input: scenario.input, force_format: false, concise: false, loading: true, load_s: sample.loadS, text: sample.text, tps: sample.tps, metrics: sample.metrics, ok: true, timed_out: false, error: null, verdict: sample.verdict },
      });
      await pause(400);
      await view.submit();
      await untilText(10);
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant l'essai, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await test({ scenario: "code", model: "qwen3.5:2b" });
      await untilText(40);
      simRun.cut(4000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant l'essai : « Interrompu »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await test({ scenario: "code", model: "qwen3.5:2b" });
      await untilText(40);
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
    id: "erreur-cloud-injoignable",
    label: "Fournisseur cloud injoignable en cours d'essai",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await untilDone(await test({ scenario: "classification", model: "claude-haiku-4-5", error: "cloud_unreachable", errorAfter: 3 }));
    },
  },
  {
    id: "erreur-cle-absente",
    label: "Clé d'API absente (Mistral)",
    async run(ctx) {
      await fresh(ctx, () => ctx.store.set({ allowCloud: true }));
      await test({ model: "mistral-small-latest" });
    },
  },
  {
    id: "cloud-non-autorise",
    label: "Modèle cloud choisi, cloud désactivé juste avant l'envoi : « Autoriser le cloud »",
    async run(ctx) {
      await fresh(ctx);
      ctx.store.set({ allowCloud: true });
      await view.setModel("gpt-5-mini");
      ctx.store.set({ allowCloud: false });
      await view.submit();
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire : entrée gardée, deux issues",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ ramGuard: true }));
      await test({ model: "qwen3.6:7b" });
    },
  },
  {
    id: "aucun-modele",
    label: "Aucun modèle de conversation installé",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ noLocalModel: true }));
    },
  },
  {
    id: "resultat-rouvert",
    label: "Essai rouvert depuis son adresse : format non respecté, conservé",
    async run(ctx) {
      await reopened(ctx, "run-banc-demo");
    },
  },
  {
    id: "resultat-delai",
    label: "Essai rouvert qui a dépassé le délai",
    async run(ctx) {
      await reopened(ctx, "run-banc-delai");
    },
  },
  {
    id: "resultat-introuvable",
    label: "Adresse d'un essai inconnu : « Essai introuvable »",
    async run(ctx) {
      await reopened(ctx, "run-banc-inconnu");
    },
  },
];
