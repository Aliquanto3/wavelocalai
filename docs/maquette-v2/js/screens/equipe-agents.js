// Équipe d'agents, `#/agents/equipe` (UX-DR28, stories 6.5 et 6.6) : écran à l'état livré.
//
// - Équipe : bibliothèque (lecture seule), « Configurer » (panneau latéral : rôle, objectif, outils, modèle
//   de chaque agent, validation serveur simulée, erreurs sous leur champ), badge « Modifiée » et
//   « Revenir à l'équipe d'origine » (décision Q3).
// - Sujet de la mission (requis) et « Lancer la mission » (désactivé avec sa raison).
// - Schéma SVG fait main : les agents dans l'ordre, puis le rapport ; l'agent actif est marqué par un
//   contour et le libellé « en cours » (jamais la couleur seule) ; vertical sous 768 px.
// - Suivi : une ligne dépliable par agent (En attente, En cours · outil, Terminé · 3 outils · 41 s,
//   Arrêté…) sur sa trace d'étapes ; « Journal brut » replié ; « Arrêter » (et Échap).
// - Rapport : Markdown rendu au fil de la rédaction, pied (badge, CO₂, pic de mémoire, durée,
//   Télécharger) ; « Rapport partiel (mission arrêtée) » si la mission est arrêtée.
// - Un outil sensible (Envoi d'email) suit la validation de l'écran Agent seul (`confirmEmail`).
//
// Les événements d'une mission sont fabriqués ici à partir de la composition de l'équipe, puis joués
// par le simulateur comme script construit à l'exécution (`sim.play({kind, events})`).

import { co2Display } from "../core/co2.js";
import { element, icon } from "../core/dom.js";
import { errorEnvelope } from "../core/errors.js";
import { formatDuration, formatGb } from "../core/format.js";
import { plural, t } from "../core/i18n.js";
import { renderMarkdown } from "../core/markdown.js";
import { setMaquette, store } from "../core/store.js";
import { findModel, modelDefaults } from "../sim/modeles.js";
import { sim } from "../sim/sim.js";
import { setOllamaDown } from "../sim/systeme.js";
import {
  closeApprovalDialog,
  createAgentStatus,
  createStepTrace,
  decideInDialog,
  loadAgentTexts,
  pause,
  prepareEvents,
  waitUntil,
} from "./agent-seul.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const RENDER_MS = 150;
let counter = 0;
let view = null; // l'instance montée, pour les scénarios

function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}

function fillDeep(value, topic) {
  if (typeof value === "string") return value.replaceAll("{topic}", topic);
  if (Array.isArray(value)) return value.map((item) => fillDeep(item, topic));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, fillDeep(item, topic)]));
  }
  return value;
}

// La trace d'étapes est stylée par la feuille de l'écran Agent seul : on l'ajoute si le routeur ne l'a pas fait.
function ensureSharedCss() {
  if (document.head.querySelector('link[data-screen="agent-seul"]')) return Promise.resolve();
  return new Promise((resolve) => {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = new URL("../../css/screens/agent-seul.css", import.meta.url).href;
    link.dataset.screen = "agent-seul";
    link.onload = link.onerror = () => resolve();
    document.head.append(link);
  });
}

export async function mount(host, ctx) {
  await Promise.all([loadAgentTexts(), ensureSharedCss()]);
  const uid = `crew-${++counter}`;
  const data = await ctx.data("equipe-agents.json");
  const toolsData = await ctx.data("agent-seul.json");
  const wide = matchMedia("(min-width: 768px)");
  let disposed = false;

  const toolLabel = (id) => toolsData.tools.find((tool) => tool.id === id)?.label ?? id;

  // --- État de l'équipe --------------------------------------------------------------------------------
  let crew = null; // l'équipe affichée (copie de la bibliothèque, éventuellement modifiée)
  let original = null;
  let modified = false;
  let topic = "";
  let draft = null; // le brouillon du panneau « Configurer »
  const library = (id) => data.crews.find((candidate) => candidate.id === id);

  // --- Structure -------------------------------------------------------------------------------------
  const guard = ctx.states.ollamaGuard();

  const teamTitle = element("h2", "crew-title", t("crew.team.title"));
  const select = element("select", "crew-select");
  select.id = `${uid}-crew`;
  for (const item of data.crews) {
    const option = element("option", "", item.name);
    option.value = item.id;
    select.append(option);
  }
  const selectLabel = element("label", "crew-label", t("crew.team.label"));
  selectLabel.htmlFor = select.id;
  const loadButton = element("button", "btn", t("crew.team.load"));
  loadButton.type = "button";
  const configure = element("button", "btn", t("crew.team.configure"));
  configure.type = "button";
  const modifiedBadge = element("span", "crew-modified", t("crew.team.modified"));
  const revert = element("button", "btn", t("crew.team.revert"));
  revert.type = "button";
  const teamHelp = element("p", "help crew-description");
  const teamBusy = element("p", "help crew-busy", t("crew.team.busy"));
  const teamRow = element("div", "crew-row");
  const selectBox = element("div", "crew-select-box");
  selectBox.append(selectLabel, select);
  teamRow.append(selectBox, loadButton, configure);
  const modifiedRow = element("p", "crew-modified-row");
  modifiedRow.append(modifiedBadge, revert);
  const teamSection = element("section", "crew-section");
  teamSection.setAttribute("aria-labelledby", `${uid}-team`);
  teamTitle.id = `${uid}-team`;
  teamSection.append(teamTitle, teamRow, teamHelp, modifiedRow, teamBusy);

  const missionTitle = element("h2", "crew-title", t("crew.mission.title"));
  const topicInput = element("input", "crew-topic");
  topicInput.type = "text";
  topicInput.id = `${uid}-topic`;
  topicInput.setAttribute("aria-required", "true");
  topicInput.setAttribute("aria-describedby", `${uid}-reason`);
  topicInput.autocomplete = "off";
  const topicLabel = element("label", "crew-label", t("crew.mission.topic"));
  topicLabel.htmlFor = topicInput.id;
  const launch = element("button", "btn btn-primary", t("crew.mission.launch"));
  launch.type = "submit";
  launch.setAttribute("aria-describedby", `${uid}-reason`);
  const reason = element("p", "help crew-reason");
  reason.id = `${uid}-reason`;
  const topicRow = element("div", "crew-row crew-row-topic");
  const topicBox = element("div", "crew-select-box crew-topic-box");
  topicBox.append(topicLabel, topicInput);
  topicRow.append(topicBox, launch);
  const missionForm = element("form", "crew-mission");
  missionForm.setAttribute("novalidate", "");
  missionForm.append(topicRow, reason);
  const graphTitle = element("h3", "crew-subtitle", t("crew.graph.title"));
  const graphHost = element("div", "crew-graph");
  const missionSection = element("section", "crew-section");
  missionSection.setAttribute("aria-labelledby", `${uid}-mission`);
  missionTitle.id = `${uid}-mission`;
  missionSection.append(missionTitle, missionForm, graphTitle, graphHost);

  const notices = element("div", "crew-notices");
  const error = document.createElement("wl-error");
  error.setAttribute("alert", "");
  const firstLoad = element("p", "help crew-first-load", t("crew.first_load"));
  firstLoad.hidden = true;

  // Suivi de la mission
  const followTitle = element("h2", "crew-title", t("crew.follow.title"));
  followTitle.id = `${uid}-follow`;
  const status = createAgentStatus({ stoppable: true, onStop: () => requestStop() });
  const approvalNote = element("p", "help crew-approval-note", t("agent.approval.expiry", { minutes: toolsData.approval_expiry_min }));
  approvalNote.hidden = true;
  const agentList = element("ul", "crew-agents");
  const logPre = element("pre", "crew-log-text");
  logPre.tabIndex = 0;
  logPre.setAttribute("aria-label", t("crew.log.label"));
  const logDetails = element("details", "crew-log");
  logDetails.append(element("summary", "", t("crew.log.title")), logPre);
  const followSection = element("section", "crew-section");
  followSection.setAttribute("aria-labelledby", followTitle.id);
  followSection.hidden = true;
  followSection.append(followTitle, status.root, approvalNote, agentList, logDetails);

  // Rapport
  const reportTitle = element("h2", "crew-title", t("crew.report.title"));
  reportTitle.id = `${uid}-report`;
  const reportBody = element("div", "wl-md crew-report-body");
  const reportFoot = element("div", "wl-msg-foot crew-report-foot");
  const reportSection = element("section", "crew-section crew-report");
  reportSection.setAttribute("aria-labelledby", reportTitle.id);
  reportSection.hidden = true;
  reportSection.append(reportTitle, reportBody, reportFoot);

  // Panneau « Configurer l'équipe »
  const drawer = element("dialog", "crew-drawer");
  drawer.setAttribute("aria-labelledby", `${uid}-drawer-title`);
  const drawerTitle = element("h2", "crew-drawer-title", t("crew.config.title"));
  drawerTitle.id = `${uid}-drawer-title`;
  const drawerIntro = element("p", "help", t("crew.config.intro"));
  const globalError = element("p", "crew-field-error");
  globalError.id = `${uid}-config-error`;
  globalError.setAttribute("role", "alert");
  globalError.hidden = true;
  const agentsHost = element("div", "crew-config-agents");
  const addButton = element("button", "btn", t("crew.config.add"));
  addButton.type = "button";
  const addHelp = element("p", "help");
  const saveButton = element("button", "btn btn-primary", t("crew.config.save"));
  saveButton.type = "submit";
  const cancelButton = element("button", "btn", t("crew.config.cancel"));
  cancelButton.type = "button";
  const drawerActions = element("div", "crew-drawer-actions");
  drawerActions.append(saveButton, cancelButton);
  const drawerForm = element("form", "crew-config");
  drawerForm.setAttribute("novalidate", "");
  drawerForm.append(drawerIntro, globalError, agentsHost, addButton, addHelp, drawerActions);
  drawer.append(drawerTitle, drawerForm);

  host.replaceChildren(
    element("h1", "", ctx.route.title),
    ctx.tabs(),
    element("p", "lead", t("crew.lead")),
    guard,
    teamSection,
    missionSection,
    notices,
    error,
    firstLoad,
    followSection,
    reportSection,
    drawer,
  );

  // --- État de la mission ----------------------------------------------------------------------------
  let run = null;
  let attachment = null;
  let lastSeq = 0;
  const owned = new Map(); // run -> { input } : les runs que cet écran a lancés
  let approvalOpen = false;
  let expiring = false;
  let stopping = false;
  let mission = null; // { agents, rows: Map, report, started, ... }
  let wasHidden = host.hidden;
  let renderTimer = null;
  const loaded = new Set();
  const running = () => run !== null;

  function say(text, tone = "info") {
    notices.replaceChildren(ctx.states.notice(text, { tone }));
  }

  const roleOf = (id) => mission?.rows.get(id)?.agent.role ?? crew.agents.find((agent) => agent.id === id)?.role ?? id;

  // --- Schéma SVG --------------------------------------------------------------------------------------
  function nodeState(agentId) {
    return mission?.rows.get(agentId)?.state ?? "idle";
  }

  function wrapLabel(text, limit) {
    if (text.length <= limit) return [text];
    const words = text.split(" ");
    const lines = [""];
    for (const word of words) {
      const last = lines[lines.length - 1];
      if (last && `${last} ${word}`.length > limit) lines.push(word);
      else lines[lines.length - 1] = last ? `${last} ${word}` : word;
    }
    return lines.slice(0, 2);
  }

  function renderGraph() {
    const agents = mission ? mission.agents : crew.agents;
    if (!agents.length) {
      graphHost.replaceChildren(element("p", "crew-graph-empty", t("crew.graph.no_agent")));
      return;
    }
    const nodes = [...agents.map((agent) => ({ id: agent.id, label: agent.role, report: false })), { id: "report", label: t("crew.graph.report"), report: true }];
    const horizontal = wide.matches && nodes.length <= 5;
    const W = horizontal ? 132 : 240;
    const H = 64;
    const GAP = horizontal ? 36 : 30;
    const width = horizontal ? nodes.length * W + (nodes.length - 1) * GAP + 8 : W + 8;
    const height = horizontal ? H + 8 : nodes.length * H + (nodes.length - 1) * GAP + 8;
    const graph = svg("svg", { class: "crew-svg", "data-orientation": horizontal ? "horizontal" : "vertical", viewBox: `0 0 ${width} ${height}`, role: "img", "aria-labelledby": `${uid}-svg-title ${uid}-svg-desc`, focusable: "false" });
    const names = agents.map((agent) => agent.role);
    graph.append(
      svg("title", { id: `${uid}-svg-title` }, t("crew.graph.svg_title", { name: crew.name })),
      svg("desc", { id: `${uid}-svg-desc` }, t("crew.graph.svg_desc", { order: names.join(t("crew.graph.then")) + t("crew.graph.then_report") })),
    );
    nodes.forEach((node, index) => {
      const x = horizontal ? 4 + index * (W + GAP) : 4;
      const y = horizontal ? 4 : 4 + index * (H + GAP);
      const state = node.report ? reportState() : nodeState(node.id);
      const group = svg("g", { class: "tg-group", "data-state": state, "data-report": node.report });
      group.append(svg("rect", { class: "tg-node", x, y, width: W, height: H, rx: 12 }));
      const lines = wrapLabel(node.label, horizontal ? 14 : 30);
      lines.forEach((line, lineIndex) => {
        const base = lines.length === 1 ? y + 26 : y + 22 + lineIndex * 16;
        group.append(svg("text", { class: "tg-label", x: x + W / 2, y: base, "text-anchor": "middle" }, line));
      });
      const stateText = graphState(state, node.report);
      if (stateText) group.append(svg("text", { class: "tg-state", x: x + W / 2, y: y + H - 10, "text-anchor": "middle" }, stateText));
      graph.append(group);
      if (index < nodes.length - 1) {
        const arrow = svg("g", { class: "tg-arrow" });
        if (horizontal) {
          const ax = x + W + 4;
          const ay = y + H / 2;
          arrow.append(svg("line", { x1: ax, y1: ay, x2: ax + GAP - 12, y2: ay }), svg("polygon", { points: `${ax + GAP - 14},${ay - 5} ${ax + GAP - 4},${ay} ${ax + GAP - 14},${ay + 5}` }));
        } else {
          const ax = x + W / 2;
          const ay = y + H + 2;
          arrow.append(svg("line", { x1: ax, y1: ay, x2: ax, y2: ay + GAP - 10 }), svg("polygon", { points: `${ax - 5},${ay + GAP - 12} ${ax},${ay + GAP - 3} ${ax + 5},${ay + GAP - 12}` }));
        }
        graph.append(arrow);
      }
    });
    graphHost.replaceChildren(graph);
  }

  function graphState(state, isReport) {
    if (isReport) return { done: t("crew.graph.report_ready"), partial: t("crew.graph.report_partial"), running: t("crew.graph.report_writing") }[state] ?? "";
    const map = {
      waiting: "crew.graph.waiting",
      running: "crew.graph.running",
      approval: "crew.graph.approval",
      done: "crew.graph.done",
      cancelled: "crew.graph.cancelled",
      interrupted: "crew.graph.interrupted",
      failed: "crew.graph.failed",
      notrun: "crew.graph.notrun",
    };
    return map[state] ? t(map[state]) : "";
  }

  function reportState() {
    if (!mission) return "idle";
    if (mission.finalStatus === "ok") return "done";
    if (mission.finalStatus && mission.report) return "partial";
    const last = mission.agents[mission.agents.length - 1];
    return mission.rows.get(last?.id)?.state === "running" && mission.report ? "running" : "idle";
  }

  wide.addEventListener("change", renderGraph);

  // --- Suivi : une ligne par agent ---------------------------------------------------------------------
  function rowText(row) {
    switch (row.state) {
      case "waiting":
        return t("crew.agent.waiting");
      case "running":
        return row.label ? t("crew.agent.running_with", { label: row.label }) : t("crew.agent.running");
      case "approval":
        return t("crew.agent.approval");
      case "done": {
        const tools = row.totals?.tools ?? 0;
        const parts = [t("crew.agent.done"), tools ? plural("crew.tools_count", tools) : t("crew.agent.no_tool")];
        if (typeof row.totals?.duration_s === "number") parts.push(formatDuration(row.totals.duration_s));
        return parts.join(" · ");
      }
      case "cancelled":
        return t("components.run_status.cancelled");
      case "interrupted":
        return t("components.run_status.interrupted");
      case "failed":
        return t("components.run_status.error");
      default:
        return t("crew.agent.notrun");
    }
  }

  function paintRow(row) {
    row.li.dataset.state = row.state;
    row.statusNode.textContent = rowText(row);
    row.empty.hidden = row.trace.count > 0;
  }

  function setRowState(row, state, label = row.label) {
    row.state = state;
    row.label = label;
    paintRow(row);
    renderGraph();
  }

  function buildRows(agents) {
    agentList.replaceChildren();
    const rows = new Map();
    agents.forEach((agent, index) => {
      const li = element("li", "crew-agent");
      const bodyId = `${uid}-agent-${index}`;
      const button = element("button", "crew-agent-head");
      button.type = "button";
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", bodyId);
      const name = element("span", "crew-agent-name", agent.role);
      const statusNode = element("span", "crew-agent-status");
      button.append(name, statusNode, icon("expand-more"));
      const body = element("div", "crew-agent-body");
      body.id = bodyId;
      body.hidden = true;
      const trace = createStepTrace({ label: t("crew.agent.trace_label", { agent: agent.role }), toolLabel });
      const empty = element("p", "help", t("crew.agent.no_step"));
      body.append(empty, trace.root);
      button.addEventListener("click", () => toggleRow(row));
      li.append(button, body);
      const row = { agent, li, button, body, statusNode, trace, empty, state: "waiting", label: null, totals: null };
      rows.set(agent.id, row);
      agentList.append(li);
      paintRow(row);
    });
    return rows;
  }

  function toggleRow(row, open = row.button.getAttribute("aria-expanded") !== "true") {
    row.button.setAttribute("aria-expanded", String(open));
    row.body.hidden = !open;
  }

  // --- Journal brut ------------------------------------------------------------------------------------
  function log(envelope, text) {
    const time = new Date(envelope.ts).toLocaleTimeString("fr-FR");
    const lines = logPre.textContent ? logPre.textContent.split("\n") : [];
    lines.push(`${time}  ${text}`);
    logPre.textContent = lines.slice(-200).join("\n");
  }

  // --- Rapport ------------------------------------------------------------------------------------------
  function scheduleReport() {
    if (renderTimer) return;
    renderTimer = setTimeout(renderReport, RENDER_MS);
  }

  function renderReport() {
    clearTimeout(renderTimer);
    renderTimer = null;
    if (!mission) return;
    reportBody.replaceChildren(renderMarkdown(mission.report));
  }

  function reportTitleText(finalStatus) {
    if (!finalStatus || finalStatus === "ok") return t("crew.report.title");
    return t(`crew.report.partial_${finalStatus}`);
  }

  function markdownOf() {
    return `${mission?.report ?? ""}\n`;
  }

  function buildReportFoot(finalStatus, metrics) {
    const parts = [];
    if (finalStatus === "ok" && metrics) {
      const badge = document.createElement("wl-badge");
      badge.setAttribute("kind", ["local", "cloud"].includes(metrics.origin) ? metrics.origin : "unknown");
      const co2 = co2Display(metrics.co2);
      const co2Node = document.createElement("wl-metric");
      co2Node.setAttribute("label", t("components.thread.co2"));
      co2Node.setAttribute("value", co2.value);
      if (co2.help) co2Node.setAttribute("help", co2.help);
      const peak = document.createElement("wl-metric");
      peak.setAttribute("label", t("crew.report.peak"));
      peak.setAttribute("value", formatGb(metrics.peak_memory_gb));
      const duration = document.createElement("wl-metric");
      duration.setAttribute("label", t("components.thread.total"));
      duration.setAttribute("value", formatDuration(metrics.total_s));
      parts.push(badge, co2Node, peak, duration);
    }
    const download = element("button", "btn crew-download", t("agent.download"));
    download.type = "button";
    download.addEventListener("click", () => {
      const blob = new Blob([markdownOf()], { type: "text/markdown" });
      const link = element("a");
      link.href = URL.createObjectURL(blob);
      link.download = "rapport-mission.md";
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    parts.push(download);
    reportFoot.replaceChildren(...parts);
  }

  // --- Fabrication des événements d'une mission ---------------------------------------------------------
  // `decision` nul : la mission s'arrête (pause) sur `approval_required`, s'il y en a un.
  function buildMission({ agents, crewId, topicText, models, decision }) {
    const fill = (value) => fillDeep(value, topicText);
    const tags = [...new Set(agents.map((agent) => agent.model))];
    const cloud = tags.some((tag) => models.get(tag)?.origin === "cloud");
    const events = [
      { wait: 0, type: "run_started", data: { kind: "agent", models: tags, params: { mode: "crew", crew: crewId, topic: topicText } } },
    ];
    for (const tag of tags) {
      const model = models.get(tag);
      if (model && model.origin !== "cloud" && !loaded.has(tag)) {
        events.push(
          { wait: 150, type: "model_loading", data: { tag } },
          { wait: 3200, slow_wait: 14000, type: "model_loaded", data: { tag, duration_s: 6.8 } },
        );
      }
    }
    for (const [agentIndex, agent] of agents.entries()) {
      const play = data.plays[agent.play] ?? data.plays.generique;
      const isLast = agentIndex === agents.length - 1;
      const tools = play.steps.filter((step) => step.kind === "tool").length;
      let total = play.answer_s;
      let n = 0;
      for (const step of play.steps) {
        const id = `${agent.id}-s${++n}`;
        const base = { lane: agent.model, step_id: id, agent: agent.id, tool: step.tool ?? null, arguments: step.kind === "tool" ? fill(step.arguments) : null, summary: null, artifact_url: null, duration_s: null };
        events.push({ wait: 250, type: "step", data: { ...base, kind: step.kind === "think" ? "think" : "tool_call" } });
        if (step.approval) {
          events.push({ wait: 250, type: "approval_required", data: { approval_id: "apr-0001", kind: "email", to: data.email.to, subject: data.email.subject, body: data.email.body } });
          if (decision === null) {
            events.push({ pause: true });
            return events;
          }
          const seconds = { approved: 6.4, rejected: 4.8, expired: 600 }[decision];
          total += seconds;
          events.push({ wait: 0, type: "approval_resolved", data: { approval_id: "apr-0001", decision } });
          events.push({ wait: 300, type: "step", data: { ...base, kind: "tool_result", summary: data.results[decision], outcome: data.results[decision], duration_s: seconds } });
          continue;
        }
        total += step.duration_s;
        events.push({
          wait: step.wait,
          type: "step",
          data: { ...base, kind: step.kind === "think" ? "think" : "tool_result", summary: fill(step.summary), artifact_url: step.file ? `/api/outputs/${step.file}` : null, duration_s: step.duration_s },
        });
      }
      const answerId = `${agent.id}-answer`;
      const answerBase = { lane: agent.model, step_id: answerId, agent: agent.id, tool: null, arguments: null, artifact_url: null, kind: "answer" };
      events.push({ wait: 250, type: "step", data: { ...answerBase, summary: null, duration_s: null } });
      if (isLast) {
        const source = typeof crewReport(crewId) === "object" ? crewReport(crewId)[decision ?? "approved"] : crewReport(crewId);
        events.push({ wait: 200, tokens: { lane: agent.model, channel: "answer", text: fill(source), tps: 40 } });
      } else {
        events.push({ wait: 700, type: "noop" });
      }
      events.push({
        wait: 100,
        type: "step",
        data: { ...answerBase, summary: fill(play.handoff), duration_s: play.answer_s, agent_totals: { tools, duration_s: Math.round(total * 10) / 10 } },
      });
    }
    events.push({ wait: 120, type: "metrics", data: { lane: tags[0], ...data.metrics[cloud ? "cloud" : "local"] } });
    events.push({ wait: 40, type: "run_ended", data: { status: "ok", error: null } });
    return events.filter((event) => event.type !== "noop");
  }

  function crewReport(crewId) {
    const report = library(crewId)?.report;
    return report || data.generic_report;
  }

  // --- Flux --------------------------------------------------------------------------------------------
  function onStep(step) {
    const row = mission?.rows.get(step.agent);
    if (!row) return;
    if (row.state === "waiting") {
      toggleRow(row, true);
      row.auto = true; // ouverte par l'écran : elle se referme quand l'agent a fini
      setRowState(row, "running", null);
    }
    row.trace.apply(step);
    const open = step.duration_s === null || step.duration_s === undefined;
    const role = row.agent.role;
    if (open) {
      if (step.kind === "think") {
        status.set("thinking", { agent: role });
        setRowState(row, "running", t("components.run_status.thinking"));
      } else if (step.kind === "tool_call") {
        const label = toolLabel(step.tool);
        status.set("tool", { tool: label, agent: role });
        setRowState(row, "running", `${label}…`);
      } else {
        status.set("generating", { agent: role });
        setRowState(row, "running", t("crew.agent.writing"));
      }
    } else if (step.kind === "answer") {
      row.totals = step.agent_totals ?? null;
      setRowState(row, "done", null);
      if (row.auto) toggleRow(row, false);
    } else {
      paintRow(row);
    }
  }

  async function onApproval(approval) {
    const thisRun = run;
    if (!thisRun || !mission) return;
    const active = [...mission.rows.values()].find((candidate) => candidate.state === "running");
    active?.trace.waitOnLast();
    if (active) setRowState(active, "approval");
    status.set("waiting", { agent: active?.agent.role });
    approvalNote.hidden = false;
    ctx.announce(t("components.run_status.waiting"));
    approvalOpen = true;
    let approved = false;
    try {
      approved = await ctx.states.confirmEmail({ to: approval.to, subject: approval.subject, body: approval.body });
    } finally {
      approvalOpen = false;
      approvalNote.hidden = true;
    }
    if (disposed || thisRun !== run || thisRun.ended) return;
    const decision = expiring ? "expired" : approved ? "approved" : "rejected";
    expiring = false;
    const owner = owned.get(thisRun.id);
    if (!owner) return;
    const full = buildMission({ ...owner.input, decision });
    const index = full.findIndex((event) => event.type === "approval_required");
    thisRun.resume(prepareEvents(full.slice(index + 1)));
  }

  function finish(finalStatus, payload = {}) {
    closeApprovalDialog();
    approvalNote.hidden = true;
    clearTimeout(renderTimer);
    renderTimer = null;
    if (mission) {
      mission.finalStatus = finalStatus;
      const map = { cancelled: "cancelled", interrupted: "interrupted", error: "failed" };
      for (const row of mission.rows.values()) {
        row.trace.finish(finalStatus);
        if (finalStatus === "ok") continue;
        if (row.state === "running" || row.state === "approval") setRowState(row, map[finalStatus] ?? "failed");
        else if (row.state === "waiting") setRowState(row, "notrun");
      }
      reportBody.replaceChildren(renderMarkdown(mission.report));
      reportTitle.textContent = reportTitleText(finalStatus);
      reportSection.hidden = !mission.report;
      if (mission.report) buildReportFoot(finalStatus, mission.metrics);
      renderGraph();
    }
    status.end(finalStatus);
    firstLoad.hidden = true;
    if (payload.error) error.error = payload.error;
    attachment?.close();
    run = null;
    attachment = null;
    stopping = false;
    renderControls();
  }

  const handlers = {
    "*": (_payload, envelope) => {
      lastSeq = envelope.seq;
    },
    run_started: (payload, envelope) => {
      status.start(envelope.ts);
      log(envelope, t("crew.log.started", { crew: crew.name, topic: payload.params?.topic ?? "" }));
      renderControls();
    },
    model_loading: (payload, envelope) => {
      firstLoad.hidden = false;
      status.set("loading");
      log(envelope, t("crew.log.loading", { tag: payload.tag }));
    },
    model_loaded: (payload, envelope) => {
      firstLoad.hidden = true;
      loaded.add(payload.tag);
      status.set("thinking");
      log(envelope, t("crew.log.loaded", { tag: payload.tag }));
    },
    step: (payload, envelope) => {
      onStep(payload);
      const open = payload.duration_s === null || payload.duration_s === undefined;
      log(envelope, t(open ? "crew.log.step_start" : "crew.log.step_end", { agent: roleOf(payload.agent), step: stepName(payload) }));
    },
    token: (payload, envelope) => {
      if (!mission) return;
      const first = !mission.report;
      mission.report += payload.text;
      if (first) {
        log(envelope, t("crew.log.writing"));
        reportSection.hidden = false;
        reportTitle.textContent = t("crew.report.title");
        buildReportFoot(null, null);
        renderGraph();
      }
      scheduleReport();
    },
    approval_required: (payload, envelope) => {
      log(envelope, t("crew.log.approval", { to: payload.to }));
      onApproval(payload).catch((failure) => console.error(failure));
    },
    approval_resolved: (payload, envelope) => {
      ctx.announce(data.results[payload.decision]);
      log(envelope, data.results[payload.decision]);
      if (run && !run.ended) status.set("thinking", { agent: mission ? [...mission.rows.values()].find((row) => row.state === "approval")?.agent.role : undefined });
      const waiting = mission && [...mission.rows.values()].find((row) => row.state === "approval");
      if (waiting) setRowState(waiting, "running", t("components.run_status.thinking"));
    },
    metrics: (payload, envelope) => {
      if (mission) mission.metrics = payload;
      log(envelope, t("crew.log.metrics"));
    },
    run_ended: (payload, envelope) => {
      log(envelope, t("crew.log.ended", { status: t(`components.run_status.${payload?.status ?? "error"}`) }));
      finish(payload?.status ?? "error", payload ?? {});
    },
  };

  function stepName(step) {
    if (step.kind === "think") return t("agent.step.think");
    if (step.kind === "answer") return t("agent.step.answer");
    return toolLabel(step.tool);
  }

  function follow(simRun, { after = 0 } = {}) {
    run = simRun;
    lastSeq = after;
    attachment = simRun.attach(handlers, { after });
    renderControls();
  }

  // --- Lancement ---------------------------------------------------------------------------------------
  async function modelsOf(agents) {
    const map = new Map();
    for (const agent of agents) {
      const model = await findModel(agent.model);
      if (model) map.set(agent.model, model);
    }
    return map;
  }

  function resetMission() {
    mission = null;
    followSection.hidden = true;
    reportSection.hidden = true;
    agentList.replaceChildren();
    logPre.textContent = "";
    reportBody.replaceChildren();
    reportFoot.replaceChildren();
    status.reset();
    error.error = null;
    notices.replaceChildren();
  }

  function startRun(agents, models, options = {}) {
    const topicText = topic.trim();
    const cloud = agents.some((agent) => models.get(agent.model)?.origin === "cloud");
    const input = { agents, crewId: crew.id, topicText, models, decision: null };
    const events = prepareEvents(buildMission(input));
    // Script construit à l'exécution (la composition de l'équipe change) ; `{pause: true}` suspend
    // le run sur la validation d'email.
    const simRun = sim.play({ kind: "agent", events }, null, {
      vars: { mode: "crew", crew: structuredClone(crew), topic: topicText }, // entrée de la commande (409 rejoint)
      kind: "agent",
      origin: cloud ? "cloud" : "local",
      module: "agent",
      error: options.errorCode ?? undefined,
      errorAfter: options.errorAfter ?? 3,
      errorDetail: options.errorDetail,
    });
    owned.set(simRun.id, { input });
    return { simRun, input };
  }

  async function launchMission(options = {}) {
    if (running()) return null;
    if (!crew.agents.length) return null;
    if (!topic.trim()) {
      topicInput.focus();
      return null;
    }
    error.error = null;
    notices.replaceChildren();
    const agents = structuredClone(crew.agents);
    const models = await modelsOf(agents);
    if (disposed) return null;
    // Ce que `POST /api/agents/runs` refuserait avant de créer le run.
    const cloudModel = agents.map((agent) => models.get(agent.model)).find((model) => model?.origin === "cloud");
    const localModel = agents.map((agent) => models.get(agent.model)).find((model) => model && model.origin !== "cloud");
    let refused = null;
    if (cloudModel) refused = sim.precheck({ origin: "cloud", kind: "agent", model: cloudModel });
    if (!refused && localModel) refused = sim.precheck({ origin: "local", kind: "agent", model: localModel });
    if (!refused && localModel && store.get().maquette.noLocalModel) refused = errorEnvelope("no_model", { detail: { purpose: "agent" } });
    if (refused?.code === "run_busy") {
      const other = sim.get(refused.detail.run_id);
      if (other.options.vars?.mode !== "crew") {
        const link = element("a", "btn", t("crew.busy_solo_link"));
        link.href = "#/agents/seul";
        notices.replaceChildren(ctx.states.notice(t("crew.busy_solo"), { tone: "warning" }), link);
        return null;
      }
      joinMission(other);
      return run;
    }
    if (refused?.code === "ram_guard") {
      refused = errorEnvelope("ram_guard", {
        detail: {
          technical: "hardware.fits : besoin estimé 5,2 Go (poids 4,7 Go + contexte 0,5 Go), libre 2,8 Go",
          needed_gb: 5.2,
          free_gb: 2.8,
          suggested_model: "qwen3.5:2b",
        },
      });
    }
    if (refused) {
      error.error = refused;
      return null;
    }
    resetMission();
    mission = { agents, rows: buildRows(agents), report: "", metrics: null, finalStatus: null };
    followSection.hidden = false;
    const started = startRun(agents, models, options);
    renderGraph();
    follow(started.simRun);
    return started.simRun;
  }

  // 409 : une mission tourne déjà (autre onglet) : on la suit, trace rejouée depuis le début.
  function joinMission(other) {
    const snapshot = other.options.vars?.crew ?? crew;
    crew = structuredClone(snapshot);
    topic = other.options.vars?.topic ?? topic;
    resetMission();
    const agents = structuredClone(crew.agents);
    mission = { agents, rows: buildRows(agents), report: "", metrics: null, finalStatus: null };
    followSection.hidden = false;
    say(t("crew.joined"));
    renderAll();
    follow(other);
  }

  // Lance une mission sans la suivre (celle d'un autre onglet) : scénario « 409 rejoint ».
  async function launchElsewhere() {
    const agents = structuredClone(crew.agents);
    const models = await modelsOf(agents);
    const started = startRun(agents, models);
    return started.simRun;
  }

  function requestStop() {
    if (!running() || stopping) return;
    stopping = true;
    status.stopping();
    renderControls();
    sim.cancel(run.id);
  }

  // --- Contrôles ----------------------------------------------------------------------------------------
  function renderTeam() {
    select.value = crew.id;
    teamHelp.textContent = crew.description;
    modifiedRow.hidden = !modified;
    const busy = running();
    loadButton.disabled = busy || select.value === crew.id;
    select.disabled = busy;
    configure.disabled = busy;
    revert.disabled = busy;
    teamBusy.hidden = !busy;
  }

  function renderControls() {
    const busy = running();
    const text = busy ? t("crew.reason.running") : !crew.agents.length ? t("crew.reason.no_agent") : !topic.trim() ? t("crew.reason.no_topic") : "";
    launch.disabled = Boolean(text);
    reason.textContent = text;
    reason.hidden = !text;
    topicInput.disabled = false;
    renderTeam();
  }

  function renderAll() {
    topicInput.value = topic;
    renderTeam();
    renderGraph();
    renderControls();
  }

  function loadCrew(id) {
    const entry = library(id);
    original = structuredClone(entry);
    crew = structuredClone(entry);
    modified = false;
    topic = entry.default_topic;
    resetMission();
    renderAll();
  }

  loadButton.addEventListener("click", () => {
    if (running()) return;
    loadCrew(select.value);
    ctx.announce(t("crew.team.loaded", { name: crew.name }));
    say(t("crew.team.loaded", { name: crew.name }), "success");
  });
  select.addEventListener("change", renderTeam);
  revert.addEventListener("click", () => {
    if (running()) return;
    crew = structuredClone(original);
    modified = false;
    resetMission();
    renderAll();
    ctx.announce(t("crew.team.reverted"));
    say(t("crew.team.reverted"), "success");
  });
  topicInput.addEventListener("input", () => {
    topic = topicInput.value;
    renderControls();
  });
  missionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    launchMission();
  });
  const onKeydown = (event) => {
    if (event.key !== "Escape" || event.defaultPrevented || !running() || host.hidden) return;
    if (document.querySelector("dialog[open]")) return; // Échap ferme d'abord le dialogue ou le panneau
    event.preventDefault();
    requestStop();
  };
  document.addEventListener("keydown", onKeydown);

  // Boutons d'action des erreurs (AD-18 : tirés du code et de `detail`).
  error.addEventListener("wl-error-action", async (event) => {
    const id = event.detail.id;
    if (id === "retry") {
      error.error = null;
      launchMission();
    } else if (id === "allow_cloud") {
      store.set({ allowCloud: true });
      error.error = null;
    } else if (id === "use_local" || id === "choose_other") {
      const defaults = await modelDefaults("agent", false).catch(() => ({ tags: [] }));
      if (defaults.tags[0]) setAllModels(defaults.tags[0], (model) => model?.origin === "cloud");
      error.error = null;
    } else if (id === "smaller") {
      const suggested = error.error?.detail?.suggested_model;
      const model = suggested ? await findModel(suggested) : null;
      if (model) setAllModels(model.tag, (candidate) => candidate?.origin !== "cloud");
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("crew.smaller", { name: model?.name ?? suggested ?? "" }), "success");
    } else if (id === "unload") {
      setMaquette({ ramGuard: false });
      error.error = null;
      say(t("crew.unloaded"), "success");
    }
  });

  async function setAllModels(tag, predicate) {
    for (const agent of crew.agents) {
      const model = await findModel(agent.model);
      if (predicate(model)) agent.model = tag;
    }
    modified = JSON.stringify(crew.agents) !== JSON.stringify(original.agents);
    renderAll();
  }

  // --- Panneau « Configurer l'équipe » ------------------------------------------------------------------
  let configCounter = 0;

  function fieldError(key, node, inputNode) {
    const message = draft.errors[key];
    node.hidden = !message;
    node.textContent = message ?? "";
    if (inputNode) {
      if (message) inputNode.setAttribute("aria-invalid", "true");
      else inputNode.removeAttribute("aria-invalid");
    }
  }

  function configAgent(agent, index) {
    const base = `${uid}-cfg-${++configCounter}`;
    const fieldset = element("fieldset", "crew-config-agent");
    fieldset.append(element("legend", "", t("crew.config.agent_n", { n: index + 1 })));

    const roleLabel = element("label", "crew-label", t("crew.config.role"));
    const role = element("input", "crew-field");
    role.type = "text";
    role.id = `${base}-role`;
    role.value = agent.role;
    roleLabel.htmlFor = role.id;
    const roleError = element("p", "crew-field-error");
    roleError.id = `${base}-role-error`;
    role.setAttribute("aria-describedby", roleError.id);
    fieldError(`${index}.role`, roleError, role);
    role.addEventListener("input", () => {
      agent.role = role.value;
      delete draft.errors[`${index}.role`];
      fieldError(`${index}.role`, roleError, role);
    });

    const goalLabel = element("label", "crew-label", t("crew.config.goal"));
    const goal = element("textarea", "crew-field");
    goal.id = `${base}-goal`;
    goal.rows = 2;
    goal.value = agent.goal;
    goalLabel.htmlFor = goal.id;
    const goalError = element("p", "crew-field-error");
    goalError.id = `${base}-goal-error`;
    goal.setAttribute("aria-describedby", goalError.id);
    fieldError(`${index}.goal`, goalError, goal);
    goal.addEventListener("input", () => {
      agent.goal = goal.value;
      delete draft.errors[`${index}.goal`];
      fieldError(`${index}.goal`, goalError, goal);
    });

    const toolsSet = element("fieldset", "crew-config-tools");
    toolsSet.append(element("legend", "", t("crew.config.tools")));
    const toolsList = element("ul", "crew-config-tool-list");
    for (const tool of toolsData.tools) {
      const item = element("li");
      const box = element("input");
      box.type = "checkbox";
      box.id = `${base}-tool-${tool.id}`;
      box.checked = agent.tools.includes(tool.id);
      box.addEventListener("change", () => {
        agent.tools = box.checked ? [...agent.tools, tool.id] : agent.tools.filter((id) => id !== tool.id);
      });
      const label = element("label", "", tool.label);
      label.htmlFor = box.id;
      item.append(box, label);
      toolsList.append(item);
    }
    toolsSet.append(toolsList);

    const picker = document.createElement("wl-model-picker");
    picker.setAttribute("purpose", "agent");
    if (agent.model) picker.value = agent.model;
    const modelError = element("p", "crew-field-error");
    modelError.id = `${base}-model-error`;
    fieldError(`${index}.model`, modelError, null);
    picker.addEventListener("wl-model-change", (event) => {
      agent.model = event.detail.values[0] ?? "";
      if (agent.model) {
        delete draft.errors[`${index}.model`];
        fieldError(`${index}.model`, modelError, null);
      }
    });
    queueMicrotask(() => {
      const field = picker.querySelector("input");
      if (field && draft.errors[`${index}.model`]) {
        field.setAttribute("aria-describedby", modelError.id);
        field.setAttribute("aria-invalid", "true");
      }
    });

    const remove = element("button", "btn", t("crew.config.remove"));
    remove.type = "button";
    remove.setAttribute("aria-label", t("crew.config.remove_named", { name: agent.role || t("crew.config.agent_n", { n: index + 1 }) }));
    remove.addEventListener("click", () => {
      draft.agents.splice(index, 1);
      renderConfig();
      (agentsHost.querySelector("fieldset .crew-field") ?? addButton).focus();
    });

    fieldset.append(roleLabel, role, roleError, goalLabel, goal, goalError, toolsSet, picker, modelError, remove);
    return fieldset;
  }

  function renderConfig() {
    agentsHost.replaceChildren(...draft.agents.map((agent, index) => configAgent(agent, index)));
    const full = draft.agents.length >= data.max_agents;
    addButton.disabled = full;
    addHelp.textContent = full ? t("crew.config.max", { max: data.max_agents }) : "";
    addHelp.hidden = !full;
    globalError.hidden = !draft.errors.global;
    globalError.textContent = draft.errors.global ?? "";
    if (draft.errors.global) addButton.setAttribute("aria-describedby", globalError.id);
    else addButton.removeAttribute("aria-describedby");
  }

  function openConfig() {
    if (running() || drawer.open) return;
    draft = { agents: structuredClone(crew.agents), errors: {} };
    renderConfig();
    drawer.showModal();
    (agentsHost.querySelector(".crew-field") ?? addButton).focus();
  }

  // Validation « serveur » simulée (POST /api/agents/crews/validate) : un message par champ.
  function validateDraft() {
    const errors = {};
    if (!draft.agents.length) errors.global = data.validation.no_agent;
    draft.agents.forEach((agent, index) => {
      if (!agent.role.trim()) errors[`${index}.role`] = data.validation.role_required;
      if (!agent.goal.trim()) errors[`${index}.goal`] = data.validation.goal_required;
      if (!agent.model) errors[`${index}.model`] = data.validation.model_required;
    });
    return errors;
  }

  function saveConfig() {
    draft.errors = validateDraft();
    if (Object.keys(draft.errors).length) {
      renderConfig();
      const first = agentsHost.querySelector('[aria-invalid="true"]');
      (first ?? addButton).focus();
      ctx.announce(t("crew.config.errors"));
      return false;
    }
    crew.agents = structuredClone(draft.agents);
    modified = JSON.stringify(crew.agents) !== JSON.stringify(original.agents);
    drawer.close();
    resetMission();
    renderAll();
    ctx.announce(t("crew.config.saved"));
    say(t("crew.config.saved"), "success");
    return true;
  }

  configure.addEventListener("click", openConfig);
  cancelButton.addEventListener("click", () => drawer.close());
  addButton.addEventListener("click", async () => {
    if (!draft || draft.agents.length >= data.max_agents) return;
    const defaults = await modelDefaults("agent", store.get().allowCloud).catch(() => ({ tags: [] }));
    if (!draft) return;
    draft.agents.push({ id: `agent-${Date.now()}`, role: t("crew.config.new_role"), goal: t("crew.config.new_goal"), tools: [], model: defaults.tags[0] ?? "", play: "generique" });
    renderConfig();
    const fields = agentsHost.querySelectorAll(".crew-config-agent");
    fields[fields.length - 1]?.querySelector(".crew-field")?.focus();
  });
  drawerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveConfig();
  });
  drawer.addEventListener("close", () => {
    draft = null;
  });

  // --- Écran masqué puis revu (reprise par `?after=<seq>`) -------------------------------------------
  const visibility = new MutationObserver(() => {
    if (host.hidden === wasHidden) return;
    wasHidden = host.hidden;
    if (wasHidden) {
      attachment?.close();
      attachment = null;
    } else if (running()) {
      attachment = run.attach(handlers, { after: lastSeq });
    }
  });
  visibility.observe(host, { attributes: true, attributeFilter: ["hidden"] });

  // --- Mission rouverte (GET /api/runs/{id}) : rendue d'un coup, sans flux -----------------------------------
  async function reopen() {
    const agents = structuredClone(crew.agents);
    const models = await modelsOf(agents);
    loaded.clear();
    for (const model of models.values()) loaded.add(model.tag); // pas de chargement dans la trace d'archive
    resetMission();
    mission = { agents, rows: buildRows(agents), report: "", metrics: null, finalStatus: null };
    followSection.hidden = false;
    const events = prepareEvents(buildMission({ agents, crewId: crew.id, topicText: topic.trim(), models, decision: "approved" }));
    let seq = 0;
    for (const event of events) {
      const envelope = { seq: ++seq, run_id: "run-equipe-demo", type: event.type, ts: new Date().toISOString(), data: event.data ?? {} };
      handlers[event.type]?.(envelope.data, envelope);
    }
    renderReport();
    status.reset();
    say(t("crew.reopened"));
  }

  view = {
    host,
    status,
    launch: launchMission,
    launchElsewhere,
    reopen,
    loadCrew,
    openConfig,
    saveConfig,
    stop: requestStop,
    get run() {
      return run;
    },
    get approvalOpen() {
      return approvalOpen;
    },
    get reportLength() {
      return mission?.report.length ?? 0;
    },
    get drawerOpen() {
      return drawer.open;
    },
    get topic() {
      return topic;
    },
    stateOf: (id) => mission?.rows.get(id)?.state ?? null,
    traceCount: (id) => mission?.rows.get(id)?.trace.count ?? 0,
    expandRow(id, open = true) {
      const row = mission?.rows.get(id);
      if (row) toggleRow(row, open);
    },
    setTopic(text) {
      topic = text;
      renderAll();
    },
    // Modifie l'équipe affichée (comme le ferait « Configurer » puis « Enregistrer »).
    editAgent(index, patch) {
      Object.assign(crew.agents[index], patch);
      modified = JSON.stringify(crew.agents) !== JSON.stringify(original.agents);
      renderAll();
    },
    removeAllAgents() {
      crew.agents = [];
      modified = true;
      renderAll();
    },
    // Dans le panneau ouvert : vide le rôle du premier agent et l'objectif du deuxième.
    breakDraft() {
      draft.agents[0].role = "";
      if (draft.agents[1]) draft.agents[1].goal = "";
      renderConfig();
    },
    expireApproval() {
      expiring = true;
      closeApprovalDialog();
    },
    closeConfig: () => drawer.close(),
  };

  loadCrew("veille");
  return () => {
    disposed = true;
    view = null;
    visibility.disconnect();
    wide.removeEventListener("change", renderGraph);
    document.removeEventListener("keydown", onKeydown);
    guard.dispose?.();
    closeApprovalDialog();
    if (drawer.open) drawer.close();
    attachment?.close();
    status.dispose();
    clearTimeout(renderTimer);
  };
}

// =============================================================================================
// Scénarios
// =============================================================================================

async function fresh(ctx, setup = () => {}) {
  await ctx.reset();
  setup();
  await waitUntil(() => view !== null);
}

const untilDone = (simRun) => simRun?.done ?? Promise.resolve();

async function startMission(ctx, options = {}) {
  const simRun = await view.launch(options);
  return simRun;
}

export const scenarios = [
  {
    id: "equipe-prete",
    label: "Équipe chargée : schéma des trois agents et du rapport, sujet prérempli",
    run: (ctx) => fresh(ctx),
  },
  {
    id: "sans-agent",
    label: "Équipe sans agent : « Ajoutez au moins un agent », lancement désactivé",
    async run(ctx) {
      await fresh(ctx);
      view.loadCrew("vide");
      view.setTopic("Sujet de démonstration");
    },
  },
  {
    id: "sujet-vide",
    label: "Sujet vide : « Saisissez un sujet », lancement désactivé",
    async run(ctx) {
      await fresh(ctx);
      view.setTopic("");
    },
  },
  {
    id: "equipe-modifiee",
    label: "Équipe modifiée : badge « Modifiée » et « Revenir à l'équipe d'origine »",
    async run(ctx) {
      await fresh(ctx);
      view.editAgent(2, { goal: "Rédiger un rapport de synthèse de deux pages." });
    },
  },
  {
    id: "configurer",
    label: "Panneau « Configurer l'équipe » : rôle, objectif, outils, modèle de chaque agent",
    async run(ctx) {
      await fresh(ctx);
      view.openConfig();
      await waitUntil(() => view.drawerOpen);
    },
  },
  {
    id: "configurer-erreurs",
    label: "Enregistrer une équipe incomplète : une erreur sous chaque champ, focus sur la première",
    async run(ctx) {
      await fresh(ctx);
      view.openConfig();
      await waitUntil(() => view.drawerOpen);
      view.breakDraft();
      view.saveConfig();
    },
  },
  {
    id: "mission-en-cours",
    label: "Mission en cours : l'agent actif est marqué sur le schéma, trace par agent",
    async run(ctx) {
      await fresh(ctx);
      await startMission(ctx);
      await waitUntil(() => view.stateOf("analyste") === "running" && view.traceCount("analyste") >= 2);
    },
  },
  {
    id: "rapport-final",
    label: "Mission terminée : rapport rendu, CO₂, pic de mémoire, durée, Télécharger",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await startMission(ctx));
    },
  },
  {
    id: "mission-arretee",
    label: "Arrêter pendant la rédaction : « Rapport partiel (mission arrêtée) »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await startMission(ctx);
      await waitUntil(() => view.reportLength >= 120);
      view.stop();
      await untilDone(simRun);
    },
  },
  {
    id: "mission-arretee-tot",
    label: "Arrêter pendant le premier agent : les suivants restent « Non lancé », pas de rapport",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await startMission(ctx);
      await waitUntil(() => view.stateOf("chercheur") === "running" && view.traceCount("chercheur") >= 2);
      view.stop();
      await untilDone(simRun);
    },
  },
  {
    id: "mission-rouverte",
    label: "Mission rouverte depuis l'historique : trace, rapport et mesures sans flux",
    async run(ctx) {
      await fresh(ctx);
      await view.reopen();
    },
  },
  {
    id: "mission-validation-email",
    label: "Un agent prépare un email : dialogue de validation, la mission attend",
    async run(ctx) {
      await fresh(ctx);
      view.loadCrew("courrier");
      await startMission(ctx);
      await waitUntil(() => view.approvalOpen);
    },
  },
  {
    id: "mission-email-envoye",
    label: "Email approuvé en cours de mission : « Email envoyé. », rapport final",
    async run(ctx) {
      await fresh(ctx);
      view.loadCrew("courrier");
      const simRun = await startMission(ctx);
      await waitUntil(() => view.approvalOpen);
      decideInDialog(true);
      await untilDone(simRun);
      view.expandRow("redacteur");
    },
  },
  {
    id: "mission-email-annule",
    label: "Email refusé en cours de mission : « Envoi annulé : l'agent en est informé. »",
    async run(ctx) {
      await fresh(ctx);
      view.loadCrew("courrier");
      const simRun = await startMission(ctx);
      await waitUntil(() => view.approvalOpen);
      decideInDialog(false);
      await untilDone(simRun);
      view.expandRow("redacteur");
    },
  },
  {
    id: "validation-expiree",
    label: "Sans réponse en 10 min : « Validation expirée : email non envoyé. »",
    async run(ctx) {
      await fresh(ctx);
      view.loadCrew("courrier");
      const simRun = await startMission(ctx);
      await waitUntil(() => view.approvalOpen);
      view.expireApproval();
      await untilDone(simRun);
      view.expandRow("redacteur");
    },
  },
  {
    id: "serveur-redemarre-en-attente",
    label: "Le serveur redémarre pendant la validation : « Interrompu », l'email n'est jamais envoyé",
    async run(ctx) {
      await fresh(ctx);
      view.loadCrew("courrier");
      const simRun = await startMission(ctx);
      await waitUntil(() => view.approvalOpen);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
  {
    id: "premier-chargement-lent",
    label: "Premier chargement lent du modèle (8 à 26 s)",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ slowLoad: true }));
      await startMission(ctx);
      await waitUntil(() => view.status.stage === "loading");
    },
  },
  {
    id: "rejoint-409",
    label: "Une mission tourne déjà (autre onglet) : 409 rejoint, trace rejouée",
    async run(ctx) {
      await fresh(ctx);
      await view.launchElsewhere();
      await pause(400);
      await startMission(ctx);
      await waitUntil(() => view.stateOf("chercheur") === "running");
    },
  },
  {
    id: "agent-seul-en-cours",
    label: "Une tâche d'agent seul tourne déjà : message et lien vers Agent seul",
    async run(ctx) {
      await fresh(ctx);
      const model = await findModel("qwen3.6:7b");
      sim.play("agent-seul-poste", null, {
        kind: "agent",
        module: "agent",
        vars: { tag: model.tag, tools: [], loading: false, load_s: null, tps: 18, metrics: { lane: model.tag }, answer: "…", prompt: "Donne-moi l'état du poste.", mode: "solo" },
      });
      await pause(300);
      await startMission(ctx);
    },
  },
  {
    id: "reprise-au-retour",
    label: "Aller sur l'Accueil pendant la mission, puis revenir : reprise sans perte",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await startMission(ctx);
      await waitUntil(() => view.traceCount("chercheur") >= 2);
      await ctx.navigate("/");
      await pause(1500);
      await ctx.navigate("/agents/equipe");
      await untilDone(simRun);
    },
  },
  {
    id: "connexion-perdue",
    label: "Connexion perdue pendant la mission, puis reprise sans doublon",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await startMission(ctx);
      await waitUntil(() => view.traceCount("chercheur") >= 2);
      simRun.cut(4000);
      await pause(1500);
      await untilDone(simRun);
      await waitUntil(() => ctx.store.get().connection.status === "open");
    },
  },
  {
    id: "serveur-redemarre",
    label: "Le serveur redémarre pendant la mission : « Interrompu »",
    async run(ctx) {
      await fresh(ctx);
      const simRun = await startMission(ctx);
      await waitUntil(() => view.traceCount("chercheur") >= 2);
      sim.restartServer();
      await untilDone(simRun);
    },
  },
  {
    id: "erreur-interrompue",
    label: "Erreur « interrupted » en cours de mission : trace et rapport partiel gardés",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await startMission(ctx, { errorCode: "interrupted", errorAfter: 22 }));
    },
  },
  {
    id: "erreur-delai",
    label: "Erreur « timeout » pendant un agent",
    async run(ctx) {
      await fresh(ctx);
      await untilDone(await startMission(ctx, { errorCode: "timeout", errorAfter: 12 }));
    },
  },
  {
    id: "erreur-ollama-arrete",
    label: "Ollama arrêté : bandeau et erreur au lancement",
    async run(ctx) {
      await fresh(ctx, () => setOllamaDown(true));
      await startMission(ctx);
    },
  },
  {
    id: "garde-fou-memoire",
    label: "Garde-fou mémoire : sujet gardé, deux issues",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ ramGuard: true }));
      await startMission(ctx);
    },
  },
  {
    id: "aucun-modele-local",
    label: "Aucun modèle local installé : erreur au lancement",
    async run(ctx) {
      await fresh(ctx, () => setMaquette({ noLocalModel: true }));
      await startMission(ctx);
    },
  },
  {
    id: "cloud-non-autorise",
    label: "Un agent a un modèle cloud, cloud désactivé : « Autoriser le cloud »",
    async run(ctx) {
      await fresh(ctx);
      view.editAgent(1, { model: "gpt-5-mini" });
      await startMission(ctx);
    },
  },
];
